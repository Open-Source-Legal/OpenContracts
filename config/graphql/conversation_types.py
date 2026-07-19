"""Generated strawberry GraphQL module (graphene migration).

Shape-generated from the graphene schema; stub functions marked PORT(...)
carry the ported business logic. See config/graphql_new/manifest.json.
"""

# mypy: disable-error-code="name-defined, valid-type, arg-type"
#   Code-generation artifacts of the strawberry schema bindings that
#   mypy's static pass cannot resolve, NOT real typing defects:
#     name-defined / valid-type — ``Annotated["XType", strawberry.lazy(...)]``
#       forward-reference strings + the runtime-generated ``*Connection``
#       types (``make_connection_types``).
#     arg-type — resolvers construct result types with ``to_global_id()``
#       (``str``) for ``strawberry.ID`` fields and return Django MODEL
#       instances where the field annotation names the strawberry type
#       (the graphene-django resolver contract). Both are correct at
#       runtime. Hand-written config/graphql/core/* stays fully checked.
# flake8: noqa: E501, F821 — generated strawberry schema module.
# E501: long GraphQL field/argument ``description=`` strings and the
# single-line generated resolver signatures (black cannot split string
# literals). F821: ``Annotated["XType", strawberry.lazy(...)]`` /
# ``cast("QuerySet", ...)`` forward-reference STRINGS that pyflakes
# resolves as names — the whole point of strawberry.lazy is to avoid the
# import (which would then be F401). Both are code-generation artifacts,
# not defects; hand-written modules (config/graphql/core/*, security.py,
# testing.py, filters.py, …) stay fully linted.

from __future__ import annotations

import datetime
import logging
from typing import Annotated, Any

import strawberry
from graphql_relay import to_global_id

from config.graphql import enums
from config.graphql._util import coerce_enum, coerce_str, strip_unset
from config.graphql.core import permissions as core_permissions
from config.graphql.core.filtering import filterset_factory, setup_filterset
from config.graphql.core.relay import (
    Node,
    get_node_from_global_id,
    make_connection_types,
    register_type,
    resolve_django_connection,
    resolve_visible_fk,
)
from config.graphql.core.scalars import BigInt, GenericScalar
from config.graphql.filters import AnnotationFilter
from opencontractserver.agents.models import AgentActionResult, AgentConfiguration
from opencontractserver.conversations.models import (
    ChatMessage,
    Conversation,
    ModerationAction,
)
from opencontractserver.corpuses.models import CorpusActionExecution
from opencontractserver.llms.agents.mention_extractor import (
    ExtractedMention,
    extract_mentions,
)
from opencontractserver.notifications.models import Notification
from opencontractserver.shared.services.base import BaseService

logger = logging.getLogger(__name__)


def resolve_mentions_for_user(
    mentions: list[ExtractedMention],
    user: Any,
) -> list[MentionedResourceType]:
    """Permission-gated resolver for a parsed list of mentions.

    Single chokepoint for both ``MessageType`` (threads) and
    ``ChatMessageType`` (chat). For every mention type it uses the model's
    ``visible_to_user()`` manager. Silent omission for inaccessible
    resources — never raises, never leaks existence.

    URLs are recomputed from the resolved DB objects so legacy text-pattern
    mentions (e.g. ``@corpus:slug``) get real ``/c/{creator}/{slug}`` URLs
    rather than the synthetic ``/c/_/{slug}`` placeholders the extractor
    emits for those patterns. For annotations the original markdown-link
    URL (``m.url``) is preserved since it already encodes the navigation
    target including the ``?ann=...`` query.

    Query plan: ``mentions`` is scanned once to collect the distinct
    (type, slug/id) keys, then a single batched ``slug__in=`` / ``id__in=``
    query per type pulls every needed row in one round-trip. The per-mention
    loop below performs lookup-only operations against the pre-fetched
    dicts — no further DB hits in the common case. ``DocumentPath`` lookups
    (corpus-scope verification + best-effort corpus context for standalone
    document mentions) are likewise pre-fetched in two batched queries.
    Replaces the previous N+1 implementation where every mention drove its
    own ``visible_to_user().filter(...).first()`` call.
    """
    from opencontractserver.agents.services import AgentConfigurationService
    from opencontractserver.annotations.models import Annotation
    from opencontractserver.corpuses.models import Corpus
    from opencontractserver.documents.models import Document, DocumentPath

    # ------------------------------------------------------------------
    # 1. Collect the keys we need to fetch.
    # ------------------------------------------------------------------
    corpus_slugs: set[str] = set()
    document_slugs: set[str] = set()
    annotation_ids: set[int] = set()
    agent_slugs: set[str] = set()

    for m in mentions:
        if m.type == "corpus" and m.slug:
            corpus_slugs.add(m.slug)
        elif m.type == "document":
            if m.slug:
                document_slugs.add(m.slug)
            if m.corpus_slug:
                corpus_slugs.add(m.corpus_slug)
        elif m.type == "annotation" and m.id is not None:
            annotation_ids.add(m.id)
        elif m.type == "agent":
            if m.slug:
                agent_slugs.add(m.slug)
            if m.corpus_slug:
                corpus_slugs.add(m.corpus_slug)

    # ------------------------------------------------------------------
    # 2. Batch-fetch (one query per type at most).
    # ------------------------------------------------------------------
    corpus_by_slug: dict[str, Any] = (
        {
            c.slug: c
            for c in BaseService.filter_visible(Corpus, user)
            .filter(slug__in=corpus_slugs)
            .select_related("creator")
        }
        if corpus_slugs
        else {}
    )

    document_by_slug: dict[str, Any] = (
        {
            d.slug: d
            for d in BaseService.filter_visible(Document, user)
            .filter(slug__in=document_slugs)
            .select_related("creator")
        }
        if document_slugs
        else {}
    )

    annotation_by_id: dict[int, Any] = (
        {
            a.id: a
            for a in BaseService.filter_visible(Annotation, user)
            .filter(id__in=annotation_ids)
            .select_related(
                "document",
                "document__creator",
                "annotation_label",
            )
        }
        if annotation_ids
        else {}
    )

    # Agents: a slug can resolve to either a GLOBAL row or a CORPUS-scoped
    # row; the per-mention disambiguation happens below.  Group results by
    # slug so each mention picks the right one in O(1).
    agents_by_slug: dict[str, list[Any]] = {}
    if agent_slugs:
        for a in AgentConfigurationService.get_active_agents_by_slugs(
            user, list(agent_slugs)
        ):
            agents_by_slug.setdefault(a.slug, []).append(a)

    # ``DocumentPath`` (corpus-scope confirmation for ``@corpus/doc`` mentions
    # plus best-effort context for standalone ``@document`` mentions): pull
    # both sets in one query each, keyed by (document_id, corpus_id) for the
    # confirmation map and (document_id,) for the standalone fallback.
    doc_corpus_pairs: set[tuple[int, int]] = set()
    standalone_doc_ids: set[int] = set()
    for m in mentions:
        if m.type != "document" or not m.slug:
            continue
        document = document_by_slug.get(m.slug)
        if document is None:
            continue
        if m.corpus_slug:
            corpus_obj = corpus_by_slug.get(m.corpus_slug)
            if corpus_obj is not None:
                doc_corpus_pairs.add((document.id, corpus_obj.id))
        else:
            standalone_doc_ids.add(document.id)

    valid_doc_corpus_pairs: set[tuple[int, int]] = set()
    if doc_corpus_pairs:
        doc_ids = {pair[0] for pair in doc_corpus_pairs}
        corpus_ids = {pair[1] for pair in doc_corpus_pairs}
        for doc_id, corpus_id in DocumentPath.objects.filter(
            document_id__in=doc_ids, corpus_id__in=corpus_ids
        ).values_list("document_id", "corpus_id"):
            valid_doc_corpus_pairs.add((doc_id, corpus_id))

    standalone_corpus_id_by_doc: dict[int, int] = {}
    if standalone_doc_ids:
        # Pick any DocumentPath per doc for the best-effort context lookup;
        # ``first()`` semantics from the original implementation is preserved
        # by iterating the queryset in id order and keeping the first hit.
        for doc_id, corpus_id in (
            DocumentPath.objects.filter(document_id__in=standalone_doc_ids)
            .order_by("document_id", "id")
            .values_list("document_id", "corpus_id")
        ):
            standalone_corpus_id_by_doc.setdefault(doc_id, corpus_id)

    # Materialise any corpus ids surfaced only via DocumentPath (i.e. ones
    # the user might not have visibility on directly). We honour that
    # visibility filter — ``BaseService.filter_visible`` is the gate that
    # decides whether a corpus is surfaced as a parent.
    standalone_corpus_ids = set(standalone_corpus_id_by_doc.values())
    extra_corpus_ids = standalone_corpus_ids - {c.id for c in corpus_by_slug.values()}
    corpus_by_id: dict[int, Any] = {c.id: c for c in corpus_by_slug.values()}
    if extra_corpus_ids:
        for c in (
            BaseService.filter_visible(Corpus, user)
            .filter(id__in=extra_corpus_ids)
            .select_related("creator")
        ):
            corpus_by_id[c.id] = c

    # ------------------------------------------------------------------
    # 3. Build the resolved list using only dict lookups.
    # ------------------------------------------------------------------
    resolved: list[MentionedResourceType] = []

    for mention in mentions:
        try:
            if mention.type == "corpus":
                if not mention.slug:
                    continue
                corpus = corpus_by_slug.get(mention.slug)
                if corpus is None:
                    continue
                resolved.append(
                    MentionedResourceType(
                        type="corpus",
                        id=corpus.id,
                        slug=corpus.slug,
                        title=corpus.title,
                        url=f"/c/{corpus.creator.slug}/{corpus.slug}",
                    )
                )

            elif mention.type == "document":
                if not mention.slug:
                    continue
                document = document_by_slug.get(mention.slug)
                if document is None:
                    continue

                corpus = None
                if mention.corpus_slug:
                    # Corpus-scoped mention: confirm the doc lives in that
                    # corpus via the prebuilt ``valid_doc_corpus_pairs``
                    # set, and that the corpus itself is visible to the
                    # user.  If either check fails, silently drop.
                    corpus = corpus_by_slug.get(mention.corpus_slug)
                    if corpus is None:
                        continue
                    if (document.id, corpus.id) not in valid_doc_corpus_pairs:
                        continue
                else:
                    # Standalone @document:slug mention — best-effort lookup
                    # of any corpus context the document lives in (via the
                    # prebuilt ``standalone_corpus_id_by_doc`` map, then
                    # ``corpus_by_id`` for the visible-to-user instance).
                    standalone_cid = standalone_corpus_id_by_doc.get(document.id)
                    corpus = (
                        corpus_by_id.get(standalone_cid)
                        if standalone_cid is not None
                        else None
                    )

                if corpus is not None:
                    url = f"/d/{corpus.creator.slug}/{corpus.slug}/{document.slug}"
                    corpus_resource = MentionedResourceType(
                        type="corpus",
                        id=corpus.id,
                        slug=corpus.slug,
                        title=corpus.title,
                        url=f"/c/{corpus.creator.slug}/{corpus.slug}",
                    )
                else:
                    url = f"/d/{document.creator.slug}/{document.slug}"
                    corpus_resource = None

                resolved.append(
                    MentionedResourceType(
                        type="document",
                        id=document.id,
                        slug=document.slug,
                        title=document.title,
                        url=url,
                        corpus=corpus_resource,
                    )
                )

            elif mention.type == "annotation":
                if mention.id is None:
                    continue
                annotation = annotation_by_id.get(mention.id)
                if annotation is None:
                    continue
                doc = annotation.document
                label = annotation.annotation_label
                resolved.append(
                    MentionedResourceType(
                        type="annotation",
                        id=annotation.id,
                        slug=None,  # Annotations don't have slugs
                        title=label.text if label else "Annotation",
                        url=mention.url,  # Preserve original URL for navigation
                        raw_text=annotation.raw_text,
                        annotation_label=label.text if label else None,
                        document=MentionedResourceType(
                            type="document",
                            id=doc.id,
                            slug=doc.slug,
                            title=doc.title,
                            url=f"/d/{doc.creator.slug}/{doc.slug}",
                        ),
                    )
                )

            elif mention.type == "agent":
                if not mention.slug:
                    continue
                candidates = agents_by_slug.get(mention.slug, [])
                if mention.corpus_slug:
                    # The URL was a corpus-scoped agent path
                    # (/c/.../agents/{slug}). Require the agent to actually
                    # live inside that corpus, otherwise silently drop.
                    candidates = [
                        a
                        for a in candidates
                        if a.corpus is not None and a.corpus.slug == mention.corpus_slug
                    ]
                if not candidates:
                    continue
                agent = candidates[0]
                resolved.append(
                    MentionedResourceType(
                        type="agent",
                        id=agent.id,
                        slug=agent.slug,
                        title=agent.name,
                        # Preserve original URL so the frontend can match it
                        # against the same link emitted by the popover.
                        url=mention.url,
                    )
                )

            # NOTE: user mentions are parsed by the extractor but are not
            # (yet) surfaced through ``MentionedResourceType``. They will be
            # wired up in a follow-up task; for now they're silently ignored
            # here so the resolver shape stays unchanged.
        except Exception:
            # Silent omission: never leak existence via error.
            logger.exception("Mention resolution failed for url=%s", mention.url)
            continue

    return resolved


def _resolve_ConversationType_conversation_type(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/conversation_types.py:473

    Port of ConversationType.resolve_conversation_type
    """
    # Convert string conversation_type from model to enum.
    if root.conversation_type:
        return coerce_enum(enums.ConversationTypeEnum, root.conversation_type)
    return None


def _resolve_ConversationType_all_messages(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/conversation_types.py:470

    Port of ConversationType.resolve_all_messages
    """
    return root.chat_messages.all()


def _resolve_ConversationType_user_vote(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/conversation_types.py:479

    Port of ConversationType.resolve_user_vote
    """
    user = info.context.user
    if not user or not user.is_authenticated:
        return None

    from opencontractserver.conversations.models import ConversationVote

    vote = ConversationVote.objects.filter(conversation=root, creator=user).first()
    if vote:
        return vote.vote_type.upper()  # Return 'UPVOTE' or 'DOWNVOTE'
    return None


@strawberry.type(name="ConversationType")
class ConversationType(Node):
    user_lock: None | (
        Annotated[UserType, strawberry.lazy("config.graphql.user_types")]
    ) = strawberry.field(name="userLock", default=None)
    backend_lock: bool = strawberry.field(name="backendLock", default=None)
    is_public: bool = strawberry.field(name="isPublic", default=None)
    creator: Annotated[UserType, strawberry.lazy("config.graphql.user_types")] = (
        strawberry.field(name="creator", default=None)
    )
    created: datetime.datetime = strawberry.field(name="created", default=None)
    modified: datetime.datetime = strawberry.field(name="modified", default=None)

    @strawberry.field(name="title", description="Optional title for the conversation")
    def title(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "title", None))

    @strawberry.field(
        name="description", description="Optional description for the conversation"
    )
    def description(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "description", None))

    created_at: datetime.datetime = strawberry.field(
        name="createdAt",
        description="Timestamp when the conversation was created",
        default=None,
    )
    updated_at: datetime.datetime = strawberry.field(
        name="updatedAt",
        description="Timestamp when the conversation was last updated",
        default=None,
    )

    @strawberry.field(
        name="conversationType", description="Type of conversation (chat or thread)"
    )
    def conversation_type(
        self, info: strawberry.Info
    ) -> enums.ConversationTypeEnum | None:
        kwargs = strip_unset({})
        return _resolve_ConversationType_conversation_type(self, info, **kwargs)

    deleted_at: datetime.datetime | None = strawberry.field(
        name="deletedAt",
        description="Timestamp when the conversation was soft-deleted",
        default=None,
    )
    is_locked: bool = strawberry.field(
        name="isLocked",
        description="Whether the thread is locked (prevents new messages)",
        default=None,
    )
    locked_at: datetime.datetime | None = strawberry.field(
        name="lockedAt",
        description="Timestamp when the thread was locked",
        default=None,
    )
    locked_by: None | (
        Annotated[UserType, strawberry.lazy("config.graphql.user_types")]
    ) = strawberry.field(
        name="lockedBy", description="Moderator who locked the thread", default=None
    )
    is_pinned: bool = strawberry.field(
        name="isPinned",
        description="Whether the thread is pinned (appears at top of list)",
        default=None,
    )
    pinned_at: datetime.datetime | None = strawberry.field(
        name="pinnedAt",
        description="Timestamp when the thread was pinned",
        default=None,
    )
    pinned_by: None | (
        Annotated[UserType, strawberry.lazy("config.graphql.user_types")]
    ) = strawberry.field(
        name="pinnedBy", description="Moderator who pinned the thread", default=None
    )
    upvote_count: int = strawberry.field(
        name="upvoteCount",
        description="Cached count of upvotes for this conversation/thread",
        default=None,
    )
    downvote_count: int = strawberry.field(
        name="downvoteCount",
        description="Cached count of downvotes for this conversation/thread",
        default=None,
    )

    @strawberry.field(
        name="chatWithCorpus",
        description="The corpus to which this conversation belongs",
    )
    def chat_with_corpus(
        self, info: strawberry.Info
    ) -> None | (Annotated[CorpusType, strawberry.lazy("config.graphql.corpus_types")]):
        # A public/shared conversation must not leak the private corpus it is
        # attached to (conversation visibility is not gated on corpus READ).
        return resolve_visible_fk(self, info, "chat_with_corpus_id", "CorpusType")

    @strawberry.field(
        name="chatWithDocument",
        description="The document to which this conversation belongs",
    )
    def chat_with_document(
        self, info: strawberry.Info
    ) -> None | (
        Annotated[DocumentType, strawberry.lazy("config.graphql.document_types")]
    ):
        return resolve_visible_fk(self, info, "chat_with_document_id", "DocumentType")

    @strawberry.field(
        name="compactionSummary",
        description="Summary of compacted (older) messages.  Empty when no compaction has occurred.",
    )
    def compaction_summary(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "compaction_summary", None))

    compacted_before_message_id: BigInt | None = strawberry.field(
        name="compactedBeforeMessageId",
        description="ID of the last message that was folded into compaction_summary.  Messages with id <= this value are excluded from LLM context (but kept in the DB).  Stored as a plain integer (not a ForeignKey) so the id__gt filter remains valid even if the cutoff message is deleted.",
        default=None,
    )
    memory_curated: bool = strawberry.field(
        name="memoryCurated",
        description="Whether this conversation has been curated for corpus memory.",
        default=None,
    )

    @strawberry.field(
        name="corpusActionExecutions",
        description="The thread that triggered this execution (for thread-based actions)",
    )
    def corpus_action_executions(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
        id: Annotated[
            strawberry.ID | None, strawberry.argument(name="id")
        ] = strawberry.UNSET,
        corpus__id: Annotated[
            strawberry.ID | None, strawberry.argument(name="corpus_Id")
        ] = strawberry.UNSET,
        corpus_action__id: Annotated[
            strawberry.ID | None, strawberry.argument(name="corpusAction_Id")
        ] = strawberry.UNSET,
        document__id: Annotated[
            strawberry.ID | None, strawberry.argument(name="document_Id")
        ] = strawberry.UNSET,
        status: Annotated[
            enums.CorpusesCorpusActionExecutionStatusChoices | None,
            strawberry.argument(name="status"),
        ] = strawberry.UNSET,
        action_type: Annotated[
            enums.CorpusesCorpusActionExecutionActionTypeChoices | None,
            strawberry.argument(name="actionType"),
        ] = strawberry.UNSET,
        trigger: Annotated[
            enums.CorpusesCorpusActionExecutionTriggerChoices | None,
            strawberry.argument(name="trigger"),
        ] = strawberry.UNSET,
        creator__id: Annotated[
            strawberry.ID | None, strawberry.argument(name="creator_Id")
        ] = strawberry.UNSET,
    ) -> Annotated[
        CorpusActionExecutionTypeConnection,
        strawberry.lazy("config.graphql.agent_types"),
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
                "id": id,
                "corpus__id": corpus__id,
                "corpus_action__id": corpus_action__id,
                "document__id": document__id,
                "status": status,
                "action_type": action_type,
                "trigger": trigger,
                "creator__id": creator__id,
            }
        )
        resolved = getattr(self, "corpus_action_executions", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="CorpusActionExecutionType",
            filterset_class=filterset_factory(
                CorpusActionExecution,
                fields={
                    "id": ["exact"],
                    "corpus__id": ["exact"],
                    "corpus_action__id": ["exact"],
                    "document__id": ["exact"],
                    "status": ["exact"],
                    "action_type": ["exact"],
                    "trigger": ["exact"],
                    "creator__id": ["exact"],
                },
            ),
            filter_args={
                "id": "id",
                "corpus__id": "corpus__id",
                "corpus_action__id": "corpus_action__id",
                "document__id": "document__id",
                "status": "status",
                "action_type": "action_type",
                "trigger": "trigger",
                "creator__id": "creator__id",
            },
        )

    @strawberry.field(
        name="chatMessages",
        description="The conversation to which this chat message belongs",
    )
    def chat_messages(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> MessageTypeConnection:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "chat_messages", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="MessageType",
        )

    @strawberry.field(
        name="moderationActions", description="The conversation that was moderated"
    )
    def moderation_actions(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> ModerationActionTypeConnection:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "moderation_actions", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="ModerationActionType",
        )

    @strawberry.field(
        name="notifications", description="Related conversation/thread if applicable"
    )
    def notifications(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
        is_read: Annotated[
            bool | None, strawberry.argument(name="isRead")
        ] = strawberry.UNSET,
        notification_type: Annotated[
            enums.NotificationsNotificationNotificationTypeChoices | None,
            strawberry.argument(name="notificationType"),
        ] = strawberry.UNSET,
        created_at__lte: Annotated[
            datetime.datetime | None, strawberry.argument(name="createdAt_Lte")
        ] = strawberry.UNSET,
        created_at__gte: Annotated[
            datetime.datetime | None, strawberry.argument(name="createdAt_Gte")
        ] = strawberry.UNSET,
    ) -> Annotated[
        NotificationTypeConnection, strawberry.lazy("config.graphql.social_types")
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
                "is_read": is_read,
                "notification_type": notification_type,
                "created_at__lte": created_at__lte,
                "created_at__gte": created_at__gte,
            }
        )
        resolved = getattr(self, "notifications", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="NotificationType",
            filterset_class=filterset_factory(
                Notification,
                fields={
                    "is_read": ["exact"],
                    "notification_type": ["exact"],
                    "created_at": ["lte", "gte"],
                },
            ),
            filter_args={
                "is_read": "is_read",
                "notification_type": "notification_type",
                "created_at__lte": "created_at__lte",
                "created_at__gte": "created_at__gte",
            },
        )

    @strawberry.field(
        name="corpusActionResults",
        description="Conversation record containing the full agent interaction",
    )
    def corpus_action_results(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
        id: Annotated[
            strawberry.ID | None, strawberry.argument(name="id")
        ] = strawberry.UNSET,
        corpus_action__id: Annotated[
            strawberry.ID | None, strawberry.argument(name="corpusAction_Id")
        ] = strawberry.UNSET,
        document__id: Annotated[
            strawberry.ID | None, strawberry.argument(name="document_Id")
        ] = strawberry.UNSET,
        status: Annotated[
            enums.AgentsAgentActionResultStatusChoices | None,
            strawberry.argument(name="status"),
        ] = strawberry.UNSET,
        creator__id: Annotated[
            strawberry.ID | None, strawberry.argument(name="creator_Id")
        ] = strawberry.UNSET,
    ) -> Annotated[
        AgentActionResultTypeConnection, strawberry.lazy("config.graphql.agent_types")
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
                "id": id,
                "corpus_action__id": corpus_action__id,
                "document__id": document__id,
                "status": status,
                "creator__id": creator__id,
            }
        )
        resolved = getattr(self, "corpus_action_results", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="AgentActionResultType",
            filterset_class=filterset_factory(
                AgentActionResult,
                fields={
                    "id": ["exact"],
                    "corpus_action__id": ["exact"],
                    "document__id": ["exact"],
                    "status": ["exact"],
                    "creator__id": ["exact"],
                },
            ),
            filter_args={
                "id": "id",
                "corpus_action__id": "corpus_action__id",
                "document__id": "document__id",
                "status": "status",
                "creator__id": "creator__id",
            },
        )

    @strawberry.field(
        name="triggeredAgentActionResults",
        description="Thread that triggered this agent action (for thread-based triggers)",
    )
    def triggered_agent_action_results(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
        id: Annotated[
            strawberry.ID | None, strawberry.argument(name="id")
        ] = strawberry.UNSET,
        corpus_action__id: Annotated[
            strawberry.ID | None, strawberry.argument(name="corpusAction_Id")
        ] = strawberry.UNSET,
        document__id: Annotated[
            strawberry.ID | None, strawberry.argument(name="document_Id")
        ] = strawberry.UNSET,
        status: Annotated[
            enums.AgentsAgentActionResultStatusChoices | None,
            strawberry.argument(name="status"),
        ] = strawberry.UNSET,
        creator__id: Annotated[
            strawberry.ID | None, strawberry.argument(name="creator_Id")
        ] = strawberry.UNSET,
    ) -> Annotated[
        AgentActionResultTypeConnection, strawberry.lazy("config.graphql.agent_types")
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
                "id": id,
                "corpus_action__id": corpus_action__id,
                "document__id": document__id,
                "status": status,
                "creator__id": creator__id,
            }
        )
        resolved = getattr(self, "triggered_agent_action_results", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="AgentActionResultType",
            filterset_class=filterset_factory(
                AgentActionResult,
                fields={
                    "id": ["exact"],
                    "corpus_action__id": ["exact"],
                    "document__id": ["exact"],
                    "status": ["exact"],
                    "creator__id": ["exact"],
                },
            ),
            filter_args={
                "id": "id",
                "corpus_action__id": "corpus_action__id",
                "document__id": "document__id",
                "status": "status",
                "creator__id": "creator__id",
            },
        )

    @strawberry.field(
        name="researchReports",
        description="Chat conversation that kicked this off, if any",
    )
    def research_reports(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> Annotated[
        ResearchReportTypeConnection, strawberry.lazy("config.graphql.research_types")
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "research_reports", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="ResearchReportType",
        )

    @strawberry.field(name="myPermissions")
    def my_permissions(self, info: strawberry.Info) -> GenericScalar | None:
        return core_permissions.resolve_my_permissions(self, info)

    @strawberry.field(name="isPublished")
    def is_published(self, info: strawberry.Info) -> bool | None:
        return core_permissions.resolve_is_published(self, info)

    @strawberry.field(name="objectSharedWith")
    def object_shared_with(self, info: strawberry.Info) -> GenericScalar | None:
        return core_permissions.resolve_object_shared_with(self, info)

    @strawberry.field(name="allMessages")
    def all_messages(self, info: strawberry.Info) -> list[MessageType | None] | None:
        kwargs = strip_unset({})
        return _resolve_ConversationType_all_messages(self, info, **kwargs)

    @strawberry.field(
        name="userVote",
        description="Current user's vote on this conversation: 'UPVOTE', 'DOWNVOTE', or null",
    )
    def user_vote(self, info: strawberry.Info) -> str | None:
        kwargs = strip_unset({})
        return _resolve_ConversationType_user_vote(self, info, **kwargs)


def _get_queryset_ConversationType(queryset, info):
    """PORT: config.graphql.conversation_types.ConversationType.get_queryset

    Port of ConversationType.get_queryset
    """
    # Chain ``visible_to_user`` on the incoming queryset/manager so the
    # filter is a single ``WHERE`` expression tree (no ``pk__in``
    # subquery over the full table).
    return BaseService.filter_visible_qs(
        queryset, info.context.user, request=info.context
    )


def _get_node_ConversationType(info, pk):
    """PORT: config.graphql.conversation_types.ConversationType.get_node

    Port of ConversationType.get_node
    """
    # Override the default node resolution to apply permission checks.
    # Anonymous users can only see public conversations.
    # Authenticated users can see public, their own, or explicitly shared.
    if pk is None:
        return None

    try:
        queryset = BaseService.filter_visible(
            Conversation, info.context.user, request=info.context
        )
        return queryset.get(pk=pk)
    except Conversation.DoesNotExist:
        return None


register_type(
    "ConversationType",
    ConversationType,
    model=Conversation,
    get_queryset=_get_queryset_ConversationType,
    get_node=_get_node_ConversationType,
)


ConversationTypeConnection = make_connection_types(
    ConversationType,
    type_name="ConversationTypeConnection",
    countable=True,
    pdf_page_aware=False,
)


ConversationConnection = make_connection_types(
    ConversationType,
    type_name="ConversationConnection",
    countable=True,
    pdf_page_aware=False,
)


def _resolve_MessageType_msg_type(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/conversation_types.py:399

    Port of MessageType.resolve_msg_type
    """
    # Convert msg_type to string for GraphQL enum compatibility.
    if root.msg_type:
        # Handle both string values and enum members
        if hasattr(root.msg_type, "value"):
            return root.msg_type.value
        return root.msg_type
    return None


def _resolve_MessageType_agent_type(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/conversation_types.py:408

    Port of MessageType.resolve_agent_type
    """
    # Convert string agent_type from model to enum.
    if root.agent_type:
        return coerce_enum(enums.AgentTypeEnum, root.agent_type)
    return None


def _resolve_MessageType_agent_configuration(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/conversation_types.py:414

    Port of MessageType.resolve_agent_configuration
    """
    # Resolve agent_configuration field.
    return root.agent_configuration


def _resolve_MessageType_mentioned_resources(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/conversation_types.py:438

    Port of MessageType.resolve_mentioned_resources
    """
    mentions = extract_mentions(root.content or "")
    return resolve_mentions_for_user(mentions, info.context.user)


def _resolve_MessageType_user_vote(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/conversation_types.py:418

    Port of MessageType.resolve_user_vote
    """
    user = info.context.user
    if not user or not user.is_authenticated:
        return None

    from opencontractserver.conversations.models import MessageVote

    vote = MessageVote.objects.filter(message=root, creator=user).first()
    if vote:
        return vote.vote_type.upper()  # Return 'UPVOTE' or 'DOWNVOTE'
    return None


@strawberry.type(name="MessageType")
class MessageType(Node):
    user_lock: None | (
        Annotated[UserType, strawberry.lazy("config.graphql.user_types")]
    ) = strawberry.field(name="userLock", default=None)
    backend_lock: bool = strawberry.field(name="backendLock", default=None)
    is_public: bool = strawberry.field(name="isPublic", default=None)
    creator: Annotated[UserType, strawberry.lazy("config.graphql.user_types")] = (
        strawberry.field(name="creator", default=None)
    )
    created: datetime.datetime = strawberry.field(name="created", default=None)
    modified: datetime.datetime = strawberry.field(name="modified", default=None)
    conversation: ConversationType = strawberry.field(
        name="conversation",
        description="The conversation to which this chat message belongs",
        default=None,
    )

    @strawberry.field(
        name="msgType", description="The type of message (SYSTEM, HUMAN, or LLM)"
    )
    def msg_type(
        self, info: strawberry.Info
    ) -> enums.ConversationsChatMessageMsgTypeChoices:
        kwargs = strip_unset({})
        return _resolve_MessageType_msg_type(self, info, **kwargs)

    @strawberry.field(
        name="agentType", description="Type of agent that generated this message"
    )
    def agent_type(self, info: strawberry.Info) -> enums.AgentTypeEnum | None:
        kwargs = strip_unset({})
        return _resolve_MessageType_agent_type(self, info, **kwargs)

    @strawberry.field(
        name="agentConfiguration",
        description="Agent configuration that generated this message",
    )
    def agent_configuration(
        self, info: strawberry.Info
    ) -> None | (
        Annotated[AgentConfigurationType, strawberry.lazy("config.graphql.agent_types")]
    ):
        kwargs = strip_unset({})
        return _resolve_MessageType_agent_configuration(self, info, **kwargs)

    parent_message: MessageType | None = strawberry.field(
        name="parentMessage",
        description="Parent message for threaded replies",
        default=None,
    )

    @strawberry.field(
        name="content", description="The textual content of the chat message"
    )
    def content(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "content", None))

    data: GenericScalar | None = strawberry.field(name="data", default=None)
    created_at: datetime.datetime = strawberry.field(
        name="createdAt",
        description="Timestamp when the chat message was created",
        default=None,
    )
    deleted_at: datetime.datetime | None = strawberry.field(
        name="deletedAt",
        description="Timestamp when the message was soft-deleted",
        default=None,
    )

    @strawberry.field(
        name="sourceDocument",
        description="A document that this chat message is based on",
    )
    def source_document(
        self, info: strawberry.Info
    ) -> None | (
        Annotated[DocumentType, strawberry.lazy("config.graphql.document_types")]
    ):
        return resolve_visible_fk(self, info, "source_document_id", "DocumentType")

    @strawberry.field(
        name="sourceAnnotations",
        description="Annotations that this chat message is based on",
    )
    def source_annotations(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
        raw_text__contains: Annotated[
            str | None, strawberry.argument(name="rawText_Contains")
        ] = strawberry.UNSET,
        annotation_label_id: Annotated[
            strawberry.ID | None, strawberry.argument(name="annotationLabelId")
        ] = strawberry.UNSET,
        annotation_label__text: Annotated[
            str | None, strawberry.argument(name="annotationLabel_Text")
        ] = strawberry.UNSET,
        annotation_label__text__contains: Annotated[
            str | None, strawberry.argument(name="annotationLabel_Text_Contains")
        ] = strawberry.UNSET,
        annotation_label__description__contains: Annotated[
            str | None,
            strawberry.argument(name="annotationLabel_Description_Contains"),
        ] = strawberry.UNSET,
        annotation_label__label_type: Annotated[
            enums.AnnotationsAnnotationLabelLabelTypeChoices | None,
            strawberry.argument(name="annotationLabel_LabelType"),
        ] = strawberry.UNSET,
        analysis__isnull: Annotated[
            bool | None, strawberry.argument(name="analysis_Isnull")
        ] = strawberry.UNSET,
        document_id: Annotated[
            strawberry.ID | None, strawberry.argument(name="documentId")
        ] = strawberry.UNSET,
        corpus_id: Annotated[
            strawberry.ID | None, strawberry.argument(name="corpusId")
        ] = strawberry.UNSET,
        structural: Annotated[
            bool | None, strawberry.argument(name="structural")
        ] = strawberry.UNSET,
        uses_label_from_labelset_id: Annotated[
            str | None, strawberry.argument(name="usesLabelFromLabelsetId")
        ] = strawberry.UNSET,
        created_by_analysis_ids: Annotated[
            str | None, strawberry.argument(name="createdByAnalysisIds")
        ] = strawberry.UNSET,
        created_with_analyzer_id: Annotated[
            str | None, strawberry.argument(name="createdWithAnalyzerId")
        ] = strawberry.UNSET,
        order_by: Annotated[
            str | None, strawberry.argument(name="orderBy", description="Ordering")
        ] = strawberry.UNSET,
    ) -> Annotated[
        AnnotationTypeConnection, strawberry.lazy("config.graphql.annotation_types")
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
                "raw_text__contains": raw_text__contains,
                "annotation_label_id": annotation_label_id,
                "annotation_label__text": annotation_label__text,
                "annotation_label__text__contains": annotation_label__text__contains,
                "annotation_label__description__contains": annotation_label__description__contains,
                "annotation_label__label_type": annotation_label__label_type,
                "analysis__isnull": analysis__isnull,
                "document_id": document_id,
                "corpus_id": corpus_id,
                "structural": structural,
                "uses_label_from_labelset_id": uses_label_from_labelset_id,
                "created_by_analysis_ids": created_by_analysis_ids,
                "created_with_analyzer_id": created_with_analyzer_id,
                "order_by": order_by,
            }
        )
        resolved = getattr(self, "source_annotations", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="AnnotationType",
            filterset_class=setup_filterset(AnnotationFilter),
            filter_args={
                "raw_text__contains": "raw_text__contains",
                "annotation_label_id": "annotation_label_id",
                "annotation_label__text": "annotation_label__text",
                "annotation_label__text__contains": "annotation_label__text__contains",
                "annotation_label__description__contains": "annotation_label__description__contains",
                "annotation_label__label_type": "annotation_label__label_type",
                "analysis__isnull": "analysis__isnull",
                "document_id": "document_id",
                "corpus_id": "corpus_id",
                "structural": "structural",
                "uses_label_from_labelset_id": "uses_label_from_labelset_id",
                "created_by_analysis_ids": "created_by_analysis_ids",
                "created_with_analyzer_id": "created_with_analyzer_id",
                "order_by": "order_by",
            },
        )

    @strawberry.field(
        name="createdAnnotations",
        description="Annotations that this chat message created",
    )
    def created_annotations(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
        raw_text__contains: Annotated[
            str | None, strawberry.argument(name="rawText_Contains")
        ] = strawberry.UNSET,
        annotation_label_id: Annotated[
            strawberry.ID | None, strawberry.argument(name="annotationLabelId")
        ] = strawberry.UNSET,
        annotation_label__text: Annotated[
            str | None, strawberry.argument(name="annotationLabel_Text")
        ] = strawberry.UNSET,
        annotation_label__text__contains: Annotated[
            str | None, strawberry.argument(name="annotationLabel_Text_Contains")
        ] = strawberry.UNSET,
        annotation_label__description__contains: Annotated[
            str | None,
            strawberry.argument(name="annotationLabel_Description_Contains"),
        ] = strawberry.UNSET,
        annotation_label__label_type: Annotated[
            enums.AnnotationsAnnotationLabelLabelTypeChoices | None,
            strawberry.argument(name="annotationLabel_LabelType"),
        ] = strawberry.UNSET,
        analysis__isnull: Annotated[
            bool | None, strawberry.argument(name="analysis_Isnull")
        ] = strawberry.UNSET,
        document_id: Annotated[
            strawberry.ID | None, strawberry.argument(name="documentId")
        ] = strawberry.UNSET,
        corpus_id: Annotated[
            strawberry.ID | None, strawberry.argument(name="corpusId")
        ] = strawberry.UNSET,
        structural: Annotated[
            bool | None, strawberry.argument(name="structural")
        ] = strawberry.UNSET,
        uses_label_from_labelset_id: Annotated[
            str | None, strawberry.argument(name="usesLabelFromLabelsetId")
        ] = strawberry.UNSET,
        created_by_analysis_ids: Annotated[
            str | None, strawberry.argument(name="createdByAnalysisIds")
        ] = strawberry.UNSET,
        created_with_analyzer_id: Annotated[
            str | None, strawberry.argument(name="createdWithAnalyzerId")
        ] = strawberry.UNSET,
        order_by: Annotated[
            str | None, strawberry.argument(name="orderBy", description="Ordering")
        ] = strawberry.UNSET,
    ) -> Annotated[
        AnnotationTypeConnection, strawberry.lazy("config.graphql.annotation_types")
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
                "raw_text__contains": raw_text__contains,
                "annotation_label_id": annotation_label_id,
                "annotation_label__text": annotation_label__text,
                "annotation_label__text__contains": annotation_label__text__contains,
                "annotation_label__description__contains": annotation_label__description__contains,
                "annotation_label__label_type": annotation_label__label_type,
                "analysis__isnull": analysis__isnull,
                "document_id": document_id,
                "corpus_id": corpus_id,
                "structural": structural,
                "uses_label_from_labelset_id": uses_label_from_labelset_id,
                "created_by_analysis_ids": created_by_analysis_ids,
                "created_with_analyzer_id": created_with_analyzer_id,
                "order_by": order_by,
            }
        )
        resolved = getattr(self, "created_annotations", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="AnnotationType",
            filterset_class=setup_filterset(AnnotationFilter),
            filter_args={
                "raw_text__contains": "raw_text__contains",
                "annotation_label_id": "annotation_label_id",
                "annotation_label__text": "annotation_label__text",
                "annotation_label__text__contains": "annotation_label__text__contains",
                "annotation_label__description__contains": "annotation_label__description__contains",
                "annotation_label__label_type": "annotation_label__label_type",
                "analysis__isnull": "analysis__isnull",
                "document_id": "document_id",
                "corpus_id": "corpus_id",
                "structural": "structural",
                "uses_label_from_labelset_id": "uses_label_from_labelset_id",
                "created_by_analysis_ids": "created_by_analysis_ids",
                "created_with_analyzer_id": "created_with_analyzer_id",
                "order_by": "order_by",
            },
        )

    @strawberry.field(
        name="mentionedAgents",
        description="Agents mentioned in this message that should respond",
    )
    def mentioned_agents(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
        scope: Annotated[
            enums.AgentsAgentConfigurationScopeChoices | None,
            strawberry.argument(name="scope"),
        ] = strawberry.UNSET,
        is_active: Annotated[
            bool | None, strawberry.argument(name="isActive")
        ] = strawberry.UNSET,
        corpus: Annotated[
            strawberry.ID | None, strawberry.argument(name="corpus")
        ] = strawberry.UNSET,
    ) -> Annotated[
        AgentConfigurationTypeConnection,
        strawberry.lazy("config.graphql.agent_types"),
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
                "scope": scope,
                "is_active": is_active,
                "corpus": corpus,
            }
        )
        resolved = getattr(self, "mentioned_agents", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="AgentConfigurationType",
            filterset_class=filterset_factory(
                AgentConfiguration,
                fields={
                    "scope": ["exact"],
                    "is_active": ["exact"],
                    "corpus": ["exact"],
                },
            ),
            filter_args={
                "scope": "scope",
                "is_active": "is_active",
                "corpus": "corpus",
            },
        )

    @strawberry.field(
        name="state", description="Lifecycle state of the message for quick filtering"
    )
    def state(
        self, info: strawberry.Info
    ) -> enums.ConversationsChatMessageStateChoices:
        return coerce_enum(
            enums.ConversationsChatMessageStateChoices, getattr(self, "state", None)
        )

    upvote_count: int = strawberry.field(
        name="upvoteCount",
        description="Cached count of upvotes for this message",
        default=None,
    )
    downvote_count: int = strawberry.field(
        name="downvoteCount",
        description="Cached count of downvotes for this message",
        default=None,
    )

    @strawberry.field(
        name="corpusActionExecutions",
        description="The message that triggered this execution (for NEW_MESSAGE trigger)",
    )
    def corpus_action_executions(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
        id: Annotated[
            strawberry.ID | None, strawberry.argument(name="id")
        ] = strawberry.UNSET,
        corpus__id: Annotated[
            strawberry.ID | None, strawberry.argument(name="corpus_Id")
        ] = strawberry.UNSET,
        corpus_action__id: Annotated[
            strawberry.ID | None, strawberry.argument(name="corpusAction_Id")
        ] = strawberry.UNSET,
        document__id: Annotated[
            strawberry.ID | None, strawberry.argument(name="document_Id")
        ] = strawberry.UNSET,
        status: Annotated[
            enums.CorpusesCorpusActionExecutionStatusChoices | None,
            strawberry.argument(name="status"),
        ] = strawberry.UNSET,
        action_type: Annotated[
            enums.CorpusesCorpusActionExecutionActionTypeChoices | None,
            strawberry.argument(name="actionType"),
        ] = strawberry.UNSET,
        trigger: Annotated[
            enums.CorpusesCorpusActionExecutionTriggerChoices | None,
            strawberry.argument(name="trigger"),
        ] = strawberry.UNSET,
        creator__id: Annotated[
            strawberry.ID | None, strawberry.argument(name="creator_Id")
        ] = strawberry.UNSET,
    ) -> Annotated[
        CorpusActionExecutionTypeConnection,
        strawberry.lazy("config.graphql.agent_types"),
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
                "id": id,
                "corpus__id": corpus__id,
                "corpus_action__id": corpus_action__id,
                "document__id": document__id,
                "status": status,
                "action_type": action_type,
                "trigger": trigger,
                "creator__id": creator__id,
            }
        )
        resolved = getattr(self, "corpus_action_executions", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="CorpusActionExecutionType",
            filterset_class=filterset_factory(
                CorpusActionExecution,
                fields={
                    "id": ["exact"],
                    "corpus__id": ["exact"],
                    "corpus_action__id": ["exact"],
                    "document__id": ["exact"],
                    "status": ["exact"],
                    "action_type": ["exact"],
                    "trigger": ["exact"],
                    "creator__id": ["exact"],
                },
            ),
            filter_args={
                "id": "id",
                "corpus__id": "corpus__id",
                "corpus_action__id": "corpus_action__id",
                "document__id": "document__id",
                "status": "status",
                "action_type": "action_type",
                "trigger": "trigger",
                "creator__id": "creator__id",
            },
        )

    @strawberry.field(name="replies", description="Parent message for threaded replies")
    def replies(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> MessageTypeConnection:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "replies", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="MessageType",
        )

    @strawberry.field(
        name="moderationActions", description="The message that was moderated"
    )
    def moderation_actions(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> ModerationActionTypeConnection:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "moderation_actions", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="ModerationActionType",
        )

    @strawberry.field(name="notifications", description="Related message if applicable")
    def notifications(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
        is_read: Annotated[
            bool | None, strawberry.argument(name="isRead")
        ] = strawberry.UNSET,
        notification_type: Annotated[
            enums.NotificationsNotificationNotificationTypeChoices | None,
            strawberry.argument(name="notificationType"),
        ] = strawberry.UNSET,
        created_at__lte: Annotated[
            datetime.datetime | None, strawberry.argument(name="createdAt_Lte")
        ] = strawberry.UNSET,
        created_at__gte: Annotated[
            datetime.datetime | None, strawberry.argument(name="createdAt_Gte")
        ] = strawberry.UNSET,
    ) -> Annotated[
        NotificationTypeConnection, strawberry.lazy("config.graphql.social_types")
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
                "is_read": is_read,
                "notification_type": notification_type,
                "created_at__lte": created_at__lte,
                "created_at__gte": created_at__gte,
            }
        )
        resolved = getattr(self, "notifications", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="NotificationType",
            filterset_class=filterset_factory(
                Notification,
                fields={
                    "is_read": ["exact"],
                    "notification_type": ["exact"],
                    "created_at": ["lte", "gte"],
                },
            ),
            filter_args={
                "is_read": "is_read",
                "notification_type": "notification_type",
                "created_at__lte": "created_at__lte",
                "created_at__gte": "created_at__gte",
            },
        )

    @strawberry.field(
        name="triggeredAgentActionResults",
        description="Message that triggered this agent action (for NEW_MESSAGE trigger)",
    )
    def triggered_agent_action_results(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
        id: Annotated[
            strawberry.ID | None, strawberry.argument(name="id")
        ] = strawberry.UNSET,
        corpus_action__id: Annotated[
            strawberry.ID | None, strawberry.argument(name="corpusAction_Id")
        ] = strawberry.UNSET,
        document__id: Annotated[
            strawberry.ID | None, strawberry.argument(name="document_Id")
        ] = strawberry.UNSET,
        status: Annotated[
            enums.AgentsAgentActionResultStatusChoices | None,
            strawberry.argument(name="status"),
        ] = strawberry.UNSET,
        creator__id: Annotated[
            strawberry.ID | None, strawberry.argument(name="creator_Id")
        ] = strawberry.UNSET,
    ) -> Annotated[
        AgentActionResultTypeConnection, strawberry.lazy("config.graphql.agent_types")
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
                "id": id,
                "corpus_action__id": corpus_action__id,
                "document__id": document__id,
                "status": status,
                "creator__id": creator__id,
            }
        )
        resolved = getattr(self, "triggered_agent_action_results", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="AgentActionResultType",
            filterset_class=filterset_factory(
                AgentActionResult,
                fields={
                    "id": ["exact"],
                    "corpus_action__id": ["exact"],
                    "document__id": ["exact"],
                    "status": ["exact"],
                    "creator__id": ["exact"],
                },
            ),
            filter_args={
                "id": "id",
                "corpus_action__id": "corpus_action__id",
                "document__id": "document__id",
                "status": "status",
                "creator__id": "creator__id",
            },
        )

    @strawberry.field(
        name="triggeredResearchReports",
        description="User chat message that triggered this run, if any",
    )
    def triggered_research_reports(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> Annotated[
        ResearchReportTypeConnection, strawberry.lazy("config.graphql.research_types")
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "triggered_research_reports", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="ResearchReportType",
        )

    @strawberry.field(name="myPermissions")
    def my_permissions(self, info: strawberry.Info) -> GenericScalar | None:
        return core_permissions.resolve_my_permissions(self, info)

    @strawberry.field(name="isPublished")
    def is_published(self, info: strawberry.Info) -> bool | None:
        return core_permissions.resolve_is_published(self, info)

    @strawberry.field(name="objectSharedWith")
    def object_shared_with(self, info: strawberry.Info) -> GenericScalar | None:
        return core_permissions.resolve_object_shared_with(self, info)

    @strawberry.field(
        name="mentionedResources",
        description="Corpuses and documents mentioned in this message using @ syntax. Only includes resources visible to the requesting user.",
    )
    def mentioned_resources(
        self, info: strawberry.Info
    ) -> list[MentionedResourceType | None] | None:
        kwargs = strip_unset({})
        return _resolve_MessageType_mentioned_resources(self, info, **kwargs)

    @strawberry.field(
        name="userVote",
        description="Current user's vote on this message: 'UPVOTE', 'DOWNVOTE', or null",
    )
    def user_vote(self, info: strawberry.Info) -> str | None:
        kwargs = strip_unset({})
        return _resolve_MessageType_user_vote(self, info, **kwargs)


def _get_node_MessageType(info, pk):
    """Permission-aware node resolution for the singular ``chatMessage(id:)``
    field (IDOR guard). The graphene resolver was ``@login_required`` +
    ``BaseService.get_or_none(ChatMessage, ...)``; ``get_or_none`` already
    filters to caller-visible rows (anonymous/unauthorised callers get None →
    standard not-found), so a forged ``base64("MessageType:<id>")`` can no
    longer fetch arbitrary private conversation messages. Without this hook,
    ``get_node_from_global_id`` falls back to an UNFILTERED ``.get(pk=pk)``.
    """
    if pk is None:
        return None
    return BaseService.get_or_none(
        ChatMessage, pk, info.context.user, request=info.context
    )


register_type(
    "MessageType",
    MessageType,
    model=ChatMessage,
    get_node=_get_node_MessageType,
)


MessageTypeConnection = make_connection_types(
    MessageType, type_name="MessageTypeConnection", countable=True, pdf_page_aware=False
)


def _resolve_ModerationActionType_corpus_id(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/conversation_types.py:569

    Port of ModerationActionType.resolve_corpus_id
    """
    # Get corpus ID from conversation if linked.
    if root.conversation and root.conversation.chat_with_corpus:
        return to_global_id("CorpusType", root.conversation.chat_with_corpus.pk)
    return None


def _resolve_ModerationActionType_is_automated(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/conversation_types.py:575

    Port of ModerationActionType.resolve_is_automated
    """
    # Check if this was an automated (agent) action - no human moderator.
    return root.moderator is None


def _resolve_ModerationActionType_can_rollback(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/conversation_types.py:579

    Port of ModerationActionType.resolve_can_rollback
    """
    # Check if this action can be rolled back.
    rollback_types = {
        "delete_message",
        "delete_thread",
        "lock_thread",
        "pin_thread",
    }
    return root.action_type in rollback_types


@strawberry.type(
    name="ModerationActionType",
    description="GraphQL type for ModerationAction audit records.",
)
class ModerationActionType(Node):
    created: datetime.datetime = strawberry.field(name="created", default=None)
    modified: datetime.datetime = strawberry.field(name="modified", default=None)

    @strawberry.field(
        name="conversation",
        description="The conversation that was moderated",
    )
    def conversation(self, info: strawberry.Info) -> ConversationType | None:
        return resolve_visible_fk(self, info, "conversation_id", "ConversationType")

    message: MessageType | None = strawberry.field(
        name="message", description="The message that was moderated", default=None
    )

    @strawberry.field(name="actionType", description="Type of moderation action taken")
    def action_type(
        self, info: strawberry.Info
    ) -> enums.ConversationsModerationActionActionTypeChoices:
        return coerce_enum(
            enums.ConversationsModerationActionActionTypeChoices,
            getattr(self, "action_type", None),
        )

    moderator: None | (
        Annotated[UserType, strawberry.lazy("config.graphql.user_types")]
    ) = strawberry.field(
        name="moderator", description="Moderator who took this action", default=None
    )

    @strawberry.field(
        name="reason", description="Optional reason for the moderation action"
    )
    def reason(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "reason", None))

    @strawberry.field(
        name="corpusId", description="Corpus ID if action is on a corpus thread"
    )
    def corpus_id(self, info: strawberry.Info) -> strawberry.ID | None:
        kwargs = strip_unset({})
        return _resolve_ModerationActionType_corpus_id(self, info, **kwargs)

    @strawberry.field(
        name="isAutomated", description="Whether this was an automated action"
    )
    def is_automated(self, info: strawberry.Info) -> bool | None:
        kwargs = strip_unset({})
        return _resolve_ModerationActionType_is_automated(self, info, **kwargs)

    @strawberry.field(
        name="canRollback", description="Whether this action can be rolled back"
    )
    def can_rollback(self, info: strawberry.Info) -> bool | None:
        kwargs = strip_unset({})
        return _resolve_ModerationActionType_can_rollback(self, info, **kwargs)


register_type("ModerationActionType", ModerationActionType, model=ModerationAction)


ModerationActionTypeConnection = make_connection_types(
    ModerationActionType,
    type_name="ModerationActionTypeConnection",
    countable=False,
    pdf_page_aware=False,
)


@strawberry.type(
    name="MentionedResourceType",
    description="Represents a corpus, document, annotation, or agent mentioned in a message.\n\nMention patterns:\n  @corpus:legal-contracts\n  @document:contract-template\n  @corpus:legal-contracts/document:contract-template\n  [text](/d/.../doc?ann=id) -> Annotation mention via markdown link\n  [text](/agents/{slug}) -> Global agent mention via markdown link\n  [text](/c/.../agents/{slug}) -> Corpus-scoped agent mention via markdown link\n\nFor annotations, includes full metadata for rich tooltip display.\nPermission-safe: Only returns resources visible to the requesting user.",
)
class MentionedResourceType:
    type: str = strawberry.field(
        name="type",
        description='Resource type: "corpus", "document", "annotation", or "agent"',
        default=None,
    )
    id: strawberry.ID = strawberry.field(
        name="id", description="Global ID of the resource", default=None
    )
    slug: str | None = strawberry.field(
        name="slug", description="URL-safe slug (null for annotations)", default=None
    )
    title: str = strawberry.field(
        name="title", description="Display title of the resource", default=None
    )
    url: str = strawberry.field(
        name="url",
        description="Frontend URL path to navigate to the resource",
        default=None,
    )
    corpus: MentionedResourceType | None = strawberry.field(
        name="corpus",
        description="Parent corpus context (for documents within a corpus)",
        default=None,
    )
    raw_text: str | None = strawberry.field(
        name="rawText", description="Full annotation text content", default=None
    )
    annotation_label: str | None = strawberry.field(
        name="annotationLabel",
        description="Annotation label name (e.g., 'Section Header', 'Definition')",
        default=None,
    )
    document: MentionedResourceType | None = strawberry.field(
        name="document", description="Parent document (for annotations)", default=None
    )


register_type("MentionedResourceType", MentionedResourceType, model=None)


@strawberry.type(
    name="ModerationMetricsType",
    description="Aggregated moderation metrics for monitoring.",
)
class ModerationMetricsType:
    total_actions: int | None = strawberry.field(name="totalActions", default=None)
    automated_actions: int | None = strawberry.field(
        name="automatedActions", default=None
    )
    manual_actions: int | None = strawberry.field(name="manualActions", default=None)
    actions_by_type: GenericScalar | None = strawberry.field(
        name="actionsByType", default=None
    )
    hourly_action_rate: float | None = strawberry.field(
        name="hourlyActionRate", default=None
    )
    is_above_threshold: bool | None = strawberry.field(
        name="isAboveThreshold", default=None
    )
    threshold_exceeded_types: list[str | None] | None = strawberry.field(
        name="thresholdExceededTypes", default=None
    )
    time_range_hours: int | None = strawberry.field(name="timeRangeHours", default=None)
    start_time: datetime.datetime | None = strawberry.field(
        name="startTime", default=None
    )
    end_time: datetime.datetime | None = strawberry.field(name="endTime", default=None)


register_type("ModerationMetricsType", ModerationMetricsType, model=None)


def q_conversation(
    info: strawberry.Info,
    id: Annotated[
        strawberry.ID,
        strawberry.argument(name="id", description="The ID of the object"),
    ] = strawberry.UNSET,
) -> ConversationType | None:
    return get_node_from_global_id(info, id, only_type_name="ConversationType")


QUERY_FIELDS = {
    "conversation": strawberry.field(resolver=q_conversation, name="conversation"),
}
