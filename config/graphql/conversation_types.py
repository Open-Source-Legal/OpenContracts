"""GraphQL type definitions for conversation, message, and moderation types."""

import logging
from typing import Any

import graphene
from django.db.models import QuerySet
from graphene import relay
from graphene.types.generic import GenericScalar
from graphene_django import DjangoObjectType
from graphql_relay import to_global_id

from config.graphql.agent_types import AgentConfigurationType
from config.graphql.base import CountableConnection
from config.graphql.base_types import AgentTypeEnum, ConversationTypeEnum
from config.graphql.permissioning.permission_annotator.mixins import (
    AnnotatePermissionsForReadMixin,
)
from opencontractserver.conversations.models import (
    ChatMessage,
    Conversation,
    ModerationAction,
)
from opencontractserver.llms.agents.mention_extractor import (
    ExtractedMention,
    extract_mentions,
)

logger = logging.getLogger(__name__)


class MentionedResourceType(graphene.ObjectType):
    """
    Represents a corpus, document, annotation, or agent mentioned in a message.

    Mention patterns:
      @corpus:legal-contracts
      @document:contract-template
      @corpus:legal-contracts/document:contract-template
      [text](/d/.../doc?ann=id) -> Annotation mention via markdown link
      [text](/agents/{slug}) -> Global agent mention via markdown link
      [text](/c/.../agents/{slug}) -> Corpus-scoped agent mention via markdown link

    For annotations, includes full metadata for rich tooltip display.
    Permission-safe: Only returns resources visible to the requesting user.
    """

    type = graphene.String(
        required=True,
        description='Resource type: "corpus", "document", "annotation", or "agent"',
    )
    id = graphene.ID(required=True, description="Global ID of the resource")
    slug = graphene.String(description="URL-safe slug (null for annotations)")
    title = graphene.String(required=True, description="Display title of the resource")
    url = graphene.String(
        required=True, description="Frontend URL path to navigate to the resource"
    )
    corpus = graphene.Field(
        lambda: MentionedResourceType,
        description="Parent corpus context (for documents within a corpus)",
    )

    # Annotation-specific fields (Issue #689)
    raw_text = graphene.String(description="Full annotation text content")
    annotation_label = graphene.String(
        description="Annotation label name (e.g., 'Section Header', 'Definition')"
    )
    document = graphene.Field(
        lambda: MentionedResourceType,
        description="Parent document (for annotations)",
    )


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
            for c in Corpus.objects.visible_to_user(user)
            .filter(slug__in=corpus_slugs)
            .select_related("creator")
        }
        if corpus_slugs
        else {}
    )

    document_by_slug: dict[str, Any] = (
        {
            d.slug: d
            for d in Document.objects.visible_to_user(user)
            .filter(slug__in=document_slugs)
            .select_related("creator")
        }
        if document_slugs
        else {}
    )

    annotation_by_id: dict[int, Any] = (
        {
            a.id: a
            for a in Annotation.objects.visible_to_user(user)
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
    # the user might not have visibility on directly).  We honour that
    # visibility filter — ``visible_to_user`` is the gate that decides
    # whether a corpus is surfaced as a parent.
    standalone_corpus_ids = set(standalone_corpus_id_by_doc.values())
    extra_corpus_ids = standalone_corpus_ids - {c.id for c in corpus_by_slug.values()}
    corpus_by_id: dict[int, Any] = {c.id: c for c in corpus_by_slug.values()}
    if extra_corpus_ids:
        for c in (
            Corpus.objects.visible_to_user(user)
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


class MessageType(AnnotatePermissionsForReadMixin, DjangoObjectType):

    data = GenericScalar()
    agent_type = graphene.Field(
        AgentTypeEnum, description="Type of agent that generated this message"
    )
    agent_configuration = graphene.Field(
        AgentConfigurationType,
        description="Agent configuration that generated this message",
    )
    mentioned_resources = graphene.List(
        MentionedResourceType,
        description="Corpuses and documents mentioned in this message using @ syntax. "
        "Only includes resources visible to the requesting user.",
    )
    user_vote = graphene.String(
        description="Current user's vote on this message: 'UPVOTE', 'DOWNVOTE', or null"
    )

    def resolve_msg_type(self, info) -> Any:
        """Convert msg_type to string for GraphQL enum compatibility."""
        if self.msg_type:
            # Handle both string values and enum members
            if hasattr(self.msg_type, "value"):
                return self.msg_type.value
            return self.msg_type
        return None

    def resolve_agent_type(self, info) -> Any:
        """Convert string agent_type from model to enum."""
        if self.agent_type:
            return AgentTypeEnum.get(self.agent_type)
        return None

    def resolve_agent_configuration(self, info) -> Any:
        """Resolve agent_configuration field."""
        return self.agent_configuration

    def resolve_user_vote(self, info) -> Any:
        """
        Returns the current user's vote on this message.

        Returns:
            'UPVOTE' if the user has upvoted the message
            'DOWNVOTE' if the user has downvoted the message
            None if the user has not voted or is not authenticated
        """
        user = info.context.user
        if not user or not user.is_authenticated:
            return None

        from opencontractserver.conversations.models import MessageVote

        vote = MessageVote.objects.filter(message=self, creator=user).first()
        if vote:
            return vote.vote_type.upper()  # Return 'UPVOTE' or 'DOWNVOTE'
        return None

    def resolve_mentioned_resources(self, info) -> Any:
        """Resolve @-mentions and markdown-link mentions in this message.

        Parsing is delegated to the shared
        :func:`opencontractserver.llms.agents.mention_extractor.extract_mentions`
        function; DB lookup + permission gating is delegated to
        :func:`resolve_mentions_for_user`.

        SECURITY: ``resolve_mentions_for_user`` uses ``visible_to_user()`` for
        every model and silently drops inaccessible resources, so a mention
        of a resource the requester cannot see is indistinguishable from a
        mention of a resource that does not exist.
        """
        mentions = extract_mentions(self.content or "")
        return resolve_mentions_for_user(mentions, info.context.user)

    class Meta:
        model = ChatMessage
        interfaces = [relay.Node]
        connection_class = CountableConnection


class ConversationType(AnnotatePermissionsForReadMixin, DjangoObjectType):

    all_messages = graphene.List(MessageType)
    conversation_type = graphene.Field(
        ConversationTypeEnum, description="Type of conversation (chat or thread)"
    )
    user_vote = graphene.String(
        description="Current user's vote on this conversation: 'UPVOTE', 'DOWNVOTE', or null"
    )

    def resolve_all_messages(self, info) -> Any:
        return self.chat_messages.all()

    def resolve_conversation_type(self, info) -> Any:
        """Convert string conversation_type from model to enum."""
        if self.conversation_type:
            return ConversationTypeEnum.get(self.conversation_type)
        return None

    def resolve_user_vote(self, info) -> Any:
        """
        Returns the current user's vote on this conversation/thread.

        Returns:
            'UPVOTE' if the user has upvoted the conversation
            'DOWNVOTE' if the user has downvoted the conversation
            None if the user has not voted or is not authenticated
        """
        user = info.context.user
        if not user or not user.is_authenticated:
            return None

        from opencontractserver.conversations.models import ConversationVote

        vote = ConversationVote.objects.filter(conversation=self, creator=user).first()
        if vote:
            return vote.vote_type.upper()  # Return 'UPVOTE' or 'DOWNVOTE'
        return None

    @classmethod
    def get_node(cls, info, id) -> Any:
        """
        Override the default node resolution to apply permission checks.
        Anonymous users can only see public conversations.
        Authenticated users can see public, their own, or explicitly shared.
        """
        if id is None:
            return None

        try:
            queryset = Conversation.objects.visible_to_user(info.context.user)
            return queryset.get(pk=id)
        except Conversation.DoesNotExist:
            return None

    class Meta:
        model = Conversation
        interfaces = [relay.Node]
        connection_class = CountableConnection

    @classmethod
    def get_queryset(cls, queryset, info) -> Any:
        if issubclass(type(queryset), QuerySet):
            return queryset.visible_to_user(info.context.user)
        elif "RelatedManager" in str(type(queryset)):
            # https://stackoverflow.com/questions/11320702/import-relatedmanager-from-django-db-models-fields-related
            return queryset.all().visible_to_user(info.context.user)
        else:
            return queryset


# Explicit Connection class for ConversationType to use in relay.ConnectionField
class ConversationConnection(CountableConnection):
    """Connection class for ConversationType used in searchConversations query."""

    class Meta:
        node = ConversationType


# ==============================================================================
# MODERATION TYPES
# ==============================================================================


class ModerationActionType(DjangoObjectType):
    """GraphQL type for ModerationAction audit records."""

    class Meta:
        model = ModerationAction
        interfaces = (relay.Node,)
        fields = [
            "id",
            "conversation",
            "message",
            "action_type",
            "moderator",
            "reason",
            "created",
            "modified",
        ]

    # Additional computed fields
    corpus_id = graphene.ID(description="Corpus ID if action is on a corpus thread")
    is_automated = graphene.Boolean(description="Whether this was an automated action")
    can_rollback = graphene.Boolean(
        description="Whether this action can be rolled back"
    )

    def resolve_corpus_id(self, info) -> Any:
        """Get corpus ID from conversation if linked."""
        if self.conversation and self.conversation.chat_with_corpus:
            return to_global_id("CorpusType", self.conversation.chat_with_corpus.pk)
        return None

    def resolve_is_automated(self, info) -> Any:
        """Check if this was an automated (agent) action - no human moderator."""
        return self.moderator is None

    def resolve_can_rollback(self, info) -> Any:
        """Check if this action can be rolled back."""
        rollback_types = {
            "delete_message",
            "delete_thread",
            "lock_thread",
            "pin_thread",
        }
        return self.action_type in rollback_types


class ModerationMetricsType(graphene.ObjectType):
    """Aggregated moderation metrics for monitoring."""

    total_actions = graphene.Int()
    automated_actions = graphene.Int()
    manual_actions = graphene.Int()
    actions_by_type = GenericScalar()  # Dict[action_type, count]
    hourly_action_rate = graphene.Float()
    is_above_threshold = graphene.Boolean()
    threshold_exceeded_types = graphene.List(graphene.String)
    time_range_hours = graphene.Int()
    start_time = graphene.DateTime()
    end_time = graphene.DateTime()
