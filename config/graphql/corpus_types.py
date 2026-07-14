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
from typing import Annotated

import strawberry
from django.contrib.auth import get_user_model
from django.db.models import OuterRef, Q, Subquery
from graphql_relay import from_global_id

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
from config.graphql.core.scalars import GenericScalar, JSONString
from config.graphql.filters import AnnotationFilter
from opencontractserver.agents.models import AgentConfiguration
from opencontractserver.annotations.models import Annotation
from opencontractserver.corpuses.models import (
    Corpus,
    CorpusAction,
    CorpusActionExecution,
    CorpusCategory,
    CorpusEngagementMetrics,
    CorpusFolder,
    CorpusGroup,
    CorpusVote,
)
from opencontractserver.shared.services.base import BaseService
from opencontractserver.utils.auth import is_authenticated_user

User = get_user_model()
logger = logging.getLogger(__name__)


def _resolve_CorpusType_md_description(root, info):
    """Resolve to the URL of the Readme.CAML Document's body file.

    Ported from the graphene ``CorpusType.resolve_md_description``. This was
    an orphaned resolver in graphene (no ``md_description`` field was ever
    declared, so it never appeared in the schema) but is exercised directly
    by ``test_corpus_description_cache``. Kept as a module function — NOT a
    GraphQL field — so schema parity is preserved.

    Returns ``None`` when no CAML doc exists for the corpus.
    """
    doc = root.readme_caml_document
    if doc is None:
        return None
    file_field = doc.txt_extract_file
    if not file_field or not file_field.name:
        return None
    if info is None or getattr(info, "context", None) is None:
        return file_field.url
    return info.context.build_absolute_uri(file_field.url)


def _resolve_CorpusType_readme_caml_document(root, info):
    """Optional rich-object access to the canonical Readme.CAML doc.

    Existing clients use mdDescription (URL) or descriptionPreview
    (text). New clients that need revision history or any other
    Document field can fetch it here. Resolves from the cached FK
    — see spec §4.5.
    """
    return root.readme_caml_document


def _resolve_CorpusType_icon(root, info):
    return "" if not root.icon else info.context.build_absolute_uri(root.icon.url)


def _resolve_CorpusType_categories(root, info):
    """Get all categories assigned to this corpus."""
    return root.categories.all()


def _resolve_CorpusType_label_set(root, info):
    """
    Return label_set with count annotations copied from corpus.

    When resolve_corpuses annotates label counts on the Corpus, we need
    to copy those annotations to the label_set instance so that its
    count resolvers can use them instead of hitting the database.
    """
    if root.label_set is None:
        return None

    # Copy annotated counts to the label_set instance
    if hasattr(root, "_label_doc_count"):
        root.label_set._doc_label_count = root._label_doc_count
    if hasattr(root, "_label_span_count"):
        root.label_set._span_label_count = root._label_span_count
    if hasattr(root, "_label_token_count"):
        root.label_set._token_label_count = root._label_token_count

    return root.label_set


def _resolve_CorpusType_engagement_metrics(root, info):
    """
    Resolve engagement metrics for this corpus.

    Returns None if metrics haven't been calculated yet.

    Epic: #565 - Corpus Engagement Metrics & Analytics
    Issue: #568 - Create GraphQL queries for engagement metrics and leaderboards
    """
    try:
        return root.engagement_metrics
    except CorpusEngagementMetrics.DoesNotExist:
        return None


def _resolve_CorpusType_folders(root, info):
    """Get all folders in this corpus with service-layer visibility filtering."""
    return BaseService.filter_visible_qs(
        root.folders, info.context.user, request=info.context
    )


def _resolve_CorpusType_annotations(root, info, **kwargs):
    """
    Custom resolver for annotations field that properly computes permissions.
    Uses AnnotationService to ensure permission flags are set.
    """
    from opencontractserver.annotations.models import Annotation
    from opencontractserver.annotations.services import AnnotationService

    user = getattr(info.context, "user", None)

    # Get all document IDs in this corpus via DocumentPath. Corpus READ is
    # already gated by the parent query that resolved ``root`` — see the
    # equivalent note in ``_resolve_CorpusType_documents`` below. The internal
    # helper avoids the deprecated user-facing wrapper's runtime warning.
    document_ids = root._get_active_documents().values_list("id", flat=True)

    # Collect annotations for all documents with proper permission computation
    all_annotations = Annotation.objects.none()
    for doc_id in document_ids:
        annotations = AnnotationService.get_document_annotations(
            document_id=doc_id, user=user, corpus_id=root.id
        )
        all_annotations = all_annotations | annotations

    return all_annotations.distinct()


def _resolve_CorpusType_all_annotation_summaries(root, info, **kwargs):

    analysis_id = kwargs.get("analysis_id", None)
    label_types = kwargs.get("label_types", None)

    annotation_set = root.annotations.all()

    if label_types and isinstance(label_types, list):
        logger.info(f"Filter to label_types: {label_types}")
        annotation_set = annotation_set.filter(
            annotation_label__label_type__in=[
                label_type.value for label_type in label_types
            ]
        )

    if analysis_id:
        try:
            analysis_pk = from_global_id(analysis_id)[1]
            annotation_set = annotation_set.filter(analysis_id=analysis_pk)
        except Exception as e:
            logger.warning(
                f"Failed resolving analysis pk for corpus {root.id} with input graphene id"
                f" {analysis_id}: {e}"
            )

    return annotation_set


def _resolve_CorpusType_documents(root, info, **kwargs):
    """
    Custom resolver for documents field that uses DocumentPath.
    Returns documents with active paths in this corpus, filtered by
    document-level visibility.

    Delegates to
    ``CorpusDocumentService.get_corpus_documents_visible_to_user``, which
    enforces the MIN-permission semantic::

        Effective Permission = MIN(document_permission, corpus_permission)

    A private document in a public (or shared) corpus stays hidden from
    users without document-level access — keeping this user-facing
    GraphQL field aligned with the permission model documented in
    ``CLAUDE.md`` rather than the corpus-as-gate semantic that
    pipeline-facing callers (MCP, discovery) use. See issue #1682.

    CAML/markdown files are included here since this resolver serves
    corpus views that need to display the article landing page.
    """
    from django.contrib.auth.models import AnonymousUser

    from opencontractserver.corpuses.services import CorpusDocumentService

    user = getattr(info.context, "user", None) or AnonymousUser()
    return CorpusDocumentService.get_corpus_documents_visible_to_user(
        user, root, include_caml=True, request=info.context
    )


def _resolve_CorpusType_applied_analyzer_ids(root, info):
    return list(root.analyses.all().values_list("analyzer_id", flat=True).distinct())


def _resolve_CorpusType_description_revisions(root, info):
    """List Readme.CAML version-tree siblings as revisions, newest first.

    Resolves via the cached ``readme_caml_document`` FK and the
    Document ``version_tree_id``; returns ``[]`` when the corpus has
    no canonical CAML document yet. Filtering on the canonical title
    + markdown mime is defensive — a Readme.CAML version tree only
    ever contains Readme.CAML siblings — and keeps the contract
    explicit.

    Annotates each sibling with ``_version_index`` (1-based, oldest
    first) so ``CorpusDescriptionRevisionType.resolve_version`` can
    read the position off the instance instead of re-querying the
    full tree per row (avoids an N+1 storm on the revisions modal).
    """
    if root.readme_caml_document_id is None:
        return []
    from opencontractserver.constants.document_processing import (
        CAML_ARTICLE_TITLE,
        MARKDOWN_MIME_TYPE,
    )
    from opencontractserver.documents.models import Document

    tree_id = root.readme_caml_document.version_tree_id
    oldest_first = list(
        Document.objects.filter(
            version_tree_id=tree_id,
            title=CAML_ARTICLE_TITLE,
            file_type=MARKDOWN_MIME_TYPE,
        )
        .select_related("creator")
        .order_by("created", "pk")
    )
    for index, doc in enumerate(oldest_first, start=1):
        doc._version_index = index
    return list(reversed(oldest_first))


def _resolve_CorpusType_memory_active_warning(root, info):
    if not root.memory_enabled:
        return None
    return (
        "Agent memory is enabled for this corpus. Generalised patterns "
        "from conversations (not specific content) may be distilled into "
        "the corpus memory document. Review the memory document in your "
        "corpus to see what has been recorded."
    )


def _resolve_CorpusType_document_count(root, info):
    """
    Return document count from annotation or fallback to model method.

    For list queries, resolve_corpuses annotates _document_count.
    For single corpus queries, falls back to model.document_count().
    """
    if hasattr(root, "_document_count") and root._document_count is not None:
        return root._document_count
    return root.document_count()


def _resolve_CorpusType_my_vote(root, info):
    """Return the viewer's vote on this corpus, if any.

    Prefer the ``_viewer_vote`` annotation that ``get_queryset`` attaches
    to every row of a list query — that's a single ``Subquery`` per page
    instead of N per-row lookups. Fall back to a per-row service call
    only when the annotation isn't present (e.g. a nested fetch path
    that bypasses our list resolver). The Subquery returns ``None`` for
    rows the viewer hasn't voted on; ``hasattr`` distinguishes "no
    annotation attached" from "annotated with no vote".
    """
    if hasattr(root, "_viewer_vote"):
        annotated = root._viewer_vote
        return annotated.upper() if annotated else None

    from opencontractserver.corpuses.services import CorpusVoteService

    request = info.context
    user = getattr(request, "user", None)
    session_key = None
    session = getattr(request, "session", None)
    if session is not None:
        session_key = session.session_key

    vote_type = CorpusVoteService.get_user_vote_type(
        user, root, session_key=session_key
    )
    return vote_type.upper() if vote_type else None


def _resolve_CorpusType_annotation_count(root, info):
    """
    Return annotation count from annotation or fallback to database query.

    For list queries, resolve_corpuses annotates _annotation_count.
    For single corpus queries, falls back to counting via DocumentPath.
    """
    if hasattr(root, "_annotation_count") and root._annotation_count is not None:
        return root._annotation_count
    from opencontractserver.documents.models import DocumentPath

    doc_ids = DocumentPath.objects.filter(
        corpus=root, is_current=True, is_deleted=False
    ).values_list("document_id", flat=True)
    return Annotation.objects.filter(document_id__in=doc_ids).count()


@strawberry.type(name="CorpusType")
class CorpusType(Node):
    @strawberry.field(name="parent")
    def parent(self, info: strawberry.Info) -> CorpusType | None:
        return resolve_visible_fk(self, info, "parent_id", "CorpusType")

    @strawberry.field(name="title")
    def title(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "title", None))

    @strawberry.field(name="description")
    def description(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "description", None))

    @strawberry.field(
        name="descriptionPreview",
        description="Auto-generated truncated plain-text preview derived from ``description``. Used by card layouts, list snippets, and hero subtitles so users never see a wall of raw text. Capped at ``MAX_CORPUS_DESCRIPTION_PREVIEW_LENGTH`` characters.",
    )
    def description_preview(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "description_preview", None))

    @strawberry.field(
        name="readmeCamlDocument",
        description="The corpus's canonical Readme.CAML Document — the source of truth for the rich description. Use this for revision history, permissions, and direct content access. The mdDescription string field exposes the same body as a file URL.",
    )
    def readme_caml_document(
        self, info: strawberry.Info
    ) -> None | (
        Annotated[DocumentType, strawberry.lazy("config.graphql.document_types")]
    ):
        kwargs = strip_unset({})
        return _resolve_CorpusType_readme_caml_document(self, info, **kwargs)

    @strawberry.field(
        name="slug",
        description="Case-sensitive slug unique per creator. Allowed: A-Z, a-z, 0-9, hyphen (-).",
    )
    def slug(self, info: strawberry.Info) -> str | None:
        return coerce_str(getattr(self, "slug", None))

    @strawberry.field(name="icon")
    def icon(self, info: strawberry.Info) -> str | None:
        kwargs = strip_unset({})
        return _resolve_CorpusType_icon(self, info, **kwargs)

    auto_branding_enabled: bool = strawberry.field(
        name="autoBrandingEnabled",
        description="When True, auto-generate a logo and Readme.CAML article on creation if no icon was uploaded. Set False to opt this corpus out of auto-branding.",
        default=None,
    )

    @strawberry.field(name="categories")
    def categories(
        self, info: strawberry.Info
    ) -> list[CorpusCategoryType | None] | None:
        kwargs = strip_unset({})
        return _resolve_CorpusType_categories(self, info, **kwargs)

    @strawberry.field(name="labelSet")
    def label_set(
        self, info: strawberry.Info
    ) -> None | (
        Annotated[LabelSetType, strawberry.lazy("config.graphql.annotation_types")]
    ):
        kwargs = strip_unset({})
        return _resolve_CorpusType_label_set(self, info, **kwargs)

    post_processors: JSONString = strawberry.field(
        name="postProcessors",
        description="List of fully qualified Python paths to post-processor functions",
        default=None,
    )

    @strawberry.field(
        name="preferredEmbedder",
        description="Fully qualified Python path to the embedder class to use for this corpus. Auto-populated from DEFAULT_EMBEDDER at creation if not set. Immutable after documents are added (use re-embed to change).",
    )
    def preferred_embedder(self, info: strawberry.Info) -> str | None:
        return coerce_str(getattr(self, "preferred_embedder", None))

    @strawberry.field(
        name="createdWithEmbedder",
        description="The embedder that was active when this corpus was created. Set automatically and never changes (audit trail).",
    )
    def created_with_embedder(self, info: strawberry.Info) -> str | None:
        return coerce_str(getattr(self, "created_with_embedder", None))

    @strawberry.field(
        name="preferredLlm",
        description="Preferred pydantic-ai model spec for agents in this corpus (e.g. 'anthropic:claude-opus-4-6'). Overridable per-agent via AgentConfiguration.preferred_llm. Falls back to settings.DEFAULT_LLM / settings.OPENAI_MODEL when unset.",
    )
    def preferred_llm(self, info: strawberry.Info) -> str | None:
        return coerce_str(getattr(self, "preferred_llm", None))

    @strawberry.field(
        name="createdWithLlm",
        description="The LLM model spec that was active when this corpus was created. Set automatically and never changes (audit trail).",
    )
    def created_with_llm(self, info: strawberry.Info) -> str | None:
        return coerce_str(getattr(self, "created_with_llm", None))

    @strawberry.field(
        name="corpusAgentInstructions",
        description="Custom system instructions for the corpus-level agent. If not set, uses DEFAULT_CORPUS_AGENT_INSTRUCTIONS from settings.",
    )
    def corpus_agent_instructions(self, info: strawberry.Info) -> str | None:
        return coerce_str(getattr(self, "corpus_agent_instructions", None))

    @strawberry.field(
        name="documentAgentInstructions",
        description="Custom system instructions for document-level agents in this corpus. If not set, uses DEFAULT_DOCUMENT_AGENT_INSTRUCTIONS from settings.",
    )
    def document_agent_instructions(self, info: strawberry.Info) -> str | None:
        return coerce_str(getattr(self, "document_agent_instructions", None))

    memory_enabled: bool = strawberry.field(
        name="memoryEnabled",
        description="Enable agent memory system for this corpus. When enabled, agents accumulate reusable insights from conversations into a memory document.",
        default=None,
    )

    @strawberry.field(
        name="memoryDocument",
        description="The Document storing accumulated agent memory for this corpus.",
    )
    def memory_document(
        self, info: strawberry.Info
    ) -> None | (
        Annotated[DocumentType, strawberry.lazy("config.graphql.document_types")]
    ):
        return resolve_visible_fk(self, info, "memory_document_id", "DocumentType")

    @strawberry.field(
        name="license",
        description="SPDX identifier of the license applied to this corpus.",
    )
    def license(
        self, info: strawberry.Info
    ) -> enums.CorpusesCorpusLicenseChoices | None:
        return coerce_enum(
            enums.CorpusesCorpusLicenseChoices, getattr(self, "license", None)
        )

    @strawberry.field(
        name="licenseLink",
        description="URL to the full license text. Required when license is 'CUSTOM', optional for standard CC licenses.",
    )
    def license_link(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "license_link", None))

    allow_comments: bool = strawberry.field(name="allowComments", default=None)
    is_public: bool = strawberry.field(name="isPublic", default=None)
    creator: Annotated[UserType, strawberry.lazy("config.graphql.user_types")] = (
        strawberry.field(name="creator", default=None)
    )
    backend_lock: bool = strawberry.field(name="backendLock", default=None)
    user_lock: None | (
        Annotated[UserType, strawberry.lazy("config.graphql.user_types")]
    ) = strawberry.field(name="userLock", default=None)
    error: bool = strawberry.field(name="error", default=None)
    is_personal: bool = strawberry.field(
        name="isPersonal",
        description="True if this is the user's personal 'My Documents' corpus",
        default=None,
    )
    upvote_count: int = strawberry.field(
        name="upvoteCount",
        description="Cached count of upvotes for this corpus",
        default=None,
    )
    downvote_count: int = strawberry.field(
        name="downvoteCount",
        description="Cached count of downvotes for this corpus",
        default=None,
    )
    score: int = strawberry.field(
        name="score",
        description="upvote_count - downvote_count, denormalized for sorting",
        default=None,
    )
    created: datetime.datetime = strawberry.field(name="created", default=None)
    modified: datetime.datetime = strawberry.field(name="modified", default=None)

    @strawberry.field(name="assignmentSet")
    def assignment_set(
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
        AssignmentTypeConnection, strawberry.lazy("config.graphql.user_types")
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
        resolved = getattr(self, "assignment_set", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="AssignmentType",
        )

    @strawberry.field(name="documentRelationships")
    def document_relationships(
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
        DocumentRelationshipTypeConnection,
        strawberry.lazy("config.graphql.document_types"),
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
        resolved = getattr(self, "document_relationships", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="DocumentRelationshipType",
        )

    @strawberry.field(name="documentPaths", description="Corpus owning this path")
    def document_paths(
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
        DocumentPathTypeConnection, strawberry.lazy("config.graphql.document_types")
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
        resolved = getattr(self, "document_paths", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="DocumentPathType",
        )

    @strawberry.field(name="documentSummaryRevisions")
    def document_summary_revisions(
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
        DocumentSummaryRevisionTypeConnection,
        strawberry.lazy("config.graphql.document_types"),
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
        resolved = getattr(self, "document_summary_revisions", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="DocumentSummaryRevisionType",
        )

    @strawberry.field(name="children")
    def children(
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
    ) -> CorpusTypeConnection:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "children", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="CorpusType",
        )

    @strawberry.field(name="actions")
    def actions(
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
        name: Annotated[
            str | None, strawberry.argument(name="name")
        ] = strawberry.UNSET,
        name__icontains: Annotated[
            str | None, strawberry.argument(name="name_Icontains")
        ] = strawberry.UNSET,
        name__istartswith: Annotated[
            str | None, strawberry.argument(name="name_Istartswith")
        ] = strawberry.UNSET,
        corpus__id: Annotated[
            strawberry.ID | None, strawberry.argument(name="corpus_Id")
        ] = strawberry.UNSET,
        fieldset__id: Annotated[
            strawberry.ID | None, strawberry.argument(name="fieldset_Id")
        ] = strawberry.UNSET,
        analyzer__id: Annotated[
            strawberry.ID | None, strawberry.argument(name="analyzer_Id")
        ] = strawberry.UNSET,
        agent_config__id: Annotated[
            strawberry.ID | None, strawberry.argument(name="agentConfig_Id")
        ] = strawberry.UNSET,
        trigger: Annotated[
            enums.CorpusesCorpusActionTriggerChoices | None,
            strawberry.argument(name="trigger"),
        ] = strawberry.UNSET,
        creator__id: Annotated[
            strawberry.ID | None, strawberry.argument(name="creator_Id")
        ] = strawberry.UNSET,
        source_template__id: Annotated[
            strawberry.ID | None, strawberry.argument(name="sourceTemplate_Id")
        ] = strawberry.UNSET,
    ) -> Annotated[
        CorpusActionTypeConnection, strawberry.lazy("config.graphql.agent_types")
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
                "id": id,
                "name": name,
                "name__icontains": name__icontains,
                "name__istartswith": name__istartswith,
                "corpus__id": corpus__id,
                "fieldset__id": fieldset__id,
                "analyzer__id": analyzer__id,
                "agent_config__id": agent_config__id,
                "trigger": trigger,
                "creator__id": creator__id,
                "source_template__id": source_template__id,
            }
        )
        resolved = getattr(self, "actions", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="CorpusActionType",
            filterset_class=filterset_factory(
                CorpusAction,
                fields={
                    "id": ["exact"],
                    "name": ["exact", "icontains", "istartswith"],
                    "corpus__id": ["exact"],
                    "fieldset__id": ["exact"],
                    "analyzer__id": ["exact"],
                    "agent_config__id": ["exact"],
                    "trigger": ["exact"],
                    "creator__id": ["exact"],
                    "source_template__id": ["exact"],
                },
            ),
            filter_args={
                "id": "id",
                "name": "name",
                "name__icontains": "name__icontains",
                "name__istartswith": "name__istartswith",
                "corpus__id": "corpus__id",
                "fieldset__id": "fieldset__id",
                "analyzer__id": "analyzer__id",
                "agent_config__id": "agent_config__id",
                "trigger": "trigger",
                "creator__id": "creator__id",
                "source_template__id": "source_template__id",
            },
        )

    @strawberry.field(name="engagementMetrics")
    def engagement_metrics(
        self, info: strawberry.Info
    ) -> CorpusEngagementMetricsType | None:
        kwargs = strip_unset({})
        return _resolve_CorpusType_engagement_metrics(self, info, **kwargs)

    @strawberry.field(
        name="folders", description="All folders in this corpus (flat list)"
    )
    def folders(self, info: strawberry.Info) -> list[CorpusFolderType | None] | None:
        kwargs = strip_unset({})
        return _resolve_CorpusType_folders(self, info, **kwargs)

    @strawberry.field(
        name="actionExecutions",
        description="Denormalized corpus reference for fast queries",
    )
    def action_executions(
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
        resolved = getattr(self, "action_executions", None)
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

    @strawberry.field(name="relationships")
    def relationships(
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
        RelationshipTypeConnection, strawberry.lazy("config.graphql.annotation_types")
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
        resolved = getattr(self, "relationships", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="RelationshipType",
        )

    @strawberry.field(name="annotations")
    def annotations(
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
        resolved = _resolve_CorpusType_annotations(self, info, **kwargs)
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

    @strawberry.field(name="notes")
    def notes(
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
        NoteTypeConnection, strawberry.lazy("config.graphql.annotation_types")
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
        resolved = getattr(self, "notes", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="NoteType",
        )

    @strawberry.field(name="references")
    def references(
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
        CorpusReferenceTypeConnection,
        strawberry.lazy("config.graphql.annotation_types"),
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
        resolved = getattr(self, "references", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="CorpusReferenceType",
        )

    @strawberry.field(name="inboundReferences")
    def inbound_references(
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
        CorpusReferenceTypeConnection,
        strawberry.lazy("config.graphql.annotation_types"),
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
        resolved = getattr(self, "inbound_references", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="CorpusReferenceType",
        )

    @strawberry.field(name="authorityNamespaces")
    def authority_namespaces(
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
        AuthorityNamespaceNodeConnection,
        strawberry.lazy("config.graphql.annotation_types"),
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
        resolved = getattr(self, "authority_namespaces", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="AuthorityNamespaceNode",
        )

    @strawberry.field(name="analyses")
    def analyses(
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
        AnalysisTypeConnection, strawberry.lazy("config.graphql.extract_types")
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
        resolved = getattr(self, "analyses", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="AnalysisType",
        )

    metadata_schema: None | (
        Annotated[FieldsetType, strawberry.lazy("config.graphql.extract_types")]
    ) = strawberry.field(name="metadataSchema", default=None)

    @strawberry.field(name="extracts")
    def extracts(
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
        ExtractTypeConnection, strawberry.lazy("config.graphql.extract_types")
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
        resolved = getattr(self, "extracts", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="ExtractType",
        )

    @strawberry.field(
        name="conversations",
        description="The corpus to which this conversation belongs",
    )
    def conversations(
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
        ConversationTypeConnection,
        strawberry.lazy("config.graphql.conversation_types"),
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
        resolved = getattr(self, "conversations", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="ConversationType",
        )

    @strawberry.field(
        name="badges",
        description="If badge_type is CORPUS, the corpus this badge belongs to",
    )
    def badges(
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
    ) -> Annotated[BadgeTypeConnection, strawberry.lazy("config.graphql.social_types")]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "badges", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="BadgeType",
        )

    @strawberry.field(
        name="userBadges",
        description="For corpus-specific badges, the context in which it was awarded",
    )
    def user_badges(
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
        UserBadgeTypeConnection, strawberry.lazy("config.graphql.social_types")
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
        resolved = getattr(self, "user_badges", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="UserBadgeType",
        )

    @strawberry.field(
        name="agents", description="Corpus this agent belongs to (if scope=CORPUS)"
    )
    def agents(
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
        resolved = getattr(self, "agents", None)
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

    @strawberry.field(name="researchReports")
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

    @strawberry.field(name="allAnnotationSummaries")
    def all_annotation_summaries(
        self,
        info: strawberry.Info,
        analysis_id: Annotated[
            strawberry.ID | None, strawberry.argument(name="analysisId")
        ] = strawberry.UNSET,
        label_types: Annotated[
            list[enums.LabelTypeEnum | None] | None,
            strawberry.argument(name="labelTypes"),
        ] = strawberry.UNSET,
    ) -> None | (
        list[
            None
            | (
                Annotated[
                    AnnotationType, strawberry.lazy("config.graphql.annotation_types")
                ]
            )
        ]
    ):
        kwargs = strip_unset({"analysis_id": analysis_id, "label_types": label_types})
        return _resolve_CorpusType_all_annotation_summaries(self, info, **kwargs)

    @strawberry.field(
        name="documents", description="Documents in this corpus via DocumentPath"
    )
    def documents(
        self,
        info: strawberry.Info,
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
    ) -> None | (
        Annotated[
            DocumentTypeConnection, strawberry.lazy("config.graphql.document_types")
        ]
    ):
        kwargs = strip_unset(
            {"before": before, "after": after, "first": first, "last": last}
        )
        resolved = _resolve_CorpusType_documents(self, info, **kwargs)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="DocumentType",
        )

    @strawberry.field(name="appliedAnalyzerIds")
    def applied_analyzer_ids(self, info: strawberry.Info) -> list[str | None] | None:
        kwargs = strip_unset({})
        return _resolve_CorpusType_applied_analyzer_ids(self, info, **kwargs)

    @strawberry.field(
        name="descriptionRevisions",
        description="Revision history for the corpus description. After the canonical-CAML refactor each entry is a sibling Document on the corpus's Readme.CAML version_tree, newest first. The field shape preserves the legacy CorpusDescriptionRevision API so the frontend revision-history viewer renders without changes.",
    )
    def description_revisions(
        self, info: strawberry.Info
    ) -> list[CorpusDescriptionRevisionType | None] | None:
        kwargs = strip_unset({})
        return _resolve_CorpusType_description_revisions(self, info, **kwargs)

    @strawberry.field(
        name="memoryActiveWarning",
        description="When memory is enabled, returns a privacy notice explaining that conversation patterns may be stored. Null when disabled.",
    )
    def memory_active_warning(self, info: strawberry.Info) -> str | None:
        kwargs = strip_unset({})
        return _resolve_CorpusType_memory_active_warning(self, info, **kwargs)

    @strawberry.field(
        name="documentCount",
        description="Count of active documents in this corpus (optimized)",
    )
    def document_count(self, info: strawberry.Info) -> int | None:
        kwargs = strip_unset({})
        return _resolve_CorpusType_document_count(self, info, **kwargs)

    @strawberry.field(
        name="myVote",
        description="Current viewer's vote on this corpus: 'UPVOTE', 'DOWNVOTE', or null. Resolved against the authenticated user when present, otherwise against the Django session id for guest voters.",
    )
    def my_vote(self, info: strawberry.Info) -> str | None:
        kwargs = strip_unset({})
        return _resolve_CorpusType_my_vote(self, info, **kwargs)

    @strawberry.field(
        name="annotationCount",
        description="Count of annotations in this corpus (optimized)",
    )
    def annotation_count(self, info: strawberry.Info) -> int | None:
        kwargs = strip_unset({})
        return _resolve_CorpusType_annotation_count(self, info, **kwargs)


def _get_queryset_CorpusType(queryset, info):
    # Chain ``visible_to_user`` on the incoming queryset/manager so the
    # filter is a single ``WHERE`` expression tree (no ``pk__in``
    # subquery over the full table).
    request = info.context
    user = getattr(request, "user", None)
    visible_qs = BaseService.filter_visible_qs(queryset, user, request=request)
    # Prefetch the Readme.CAML FK so mdDescription / readmeCamlDocument
    # resolve in O(1) per row. See spec §4.5.
    from opencontractserver.corpuses.services.corpus_documents import (
        CorpusDocumentService,
    )

    visible_qs = CorpusDocumentService.with_readme_caml_doc(visible_qs)

    # Annotate the viewer's vote in one Subquery per page so
    # ``resolve_my_vote`` doesn't fire N queries (one per corpus card)
    # on the public list view. Authenticated viewers key on creator;
    # anonymous viewers key on the Django session key — both branches
    # mirror ``CorpusVoteService.get_user_vote_type``.
    is_auth = is_authenticated_user(user)
    if is_auth:
        viewer_filter = Q(creator=user, session_key__isnull=True)
    else:
        session = getattr(request, "session", None)
        session_key = getattr(session, "session_key", None) if session else None
        if not session_key:
            # No session => no anonymous votes possible; skip the
            # annotation to avoid attaching a column of NULLs.
            return visible_qs
        viewer_filter = Q(session_key=session_key, creator__isnull=True)

    viewer_vote_subquery = CorpusVote.objects.filter(
        viewer_filter, corpus=OuterRef("pk")
    ).values("vote_type")[:1]
    return visible_qs.annotate(_viewer_vote=Subquery(viewer_vote_subquery))


def _get_node_CorpusType(info, pk):
    """Cache + visibility-check FK/relay-node ``Corpus`` lookups.

    ``Corpus`` is a ``with_tree_fields=True`` ``TreeNode``, so every
    ``Corpus.objects.get(pk=...)`` emits a recursive ``WITH __rank_table``
    CTE. Graphene's default ``DjangoObjectType.get_node`` fires that CTE
    once per FK-via-Node access AND does an unprotected lookup that
    bypasses visibility. This override caches the result on
    ``info.context._corpus_node_cache`` and routes the fetch through
    ``BaseService.get_or_none`` so visibility + the Tier-2 permission
    cache apply (also required by the ``opencontracts.E001`` system check).
    """
    try:
        pk = int(pk)
    except (TypeError, ValueError):
        return None

    cache = getattr(info.context, "_corpus_node_cache", None)
    if cache is None:
        cache = {}
        try:
            info.context._corpus_node_cache = cache
        except AttributeError:
            # ``info.context`` may be frozen in some test contexts; skip
            # caching but still apply visibility.
            cache = None

    if cache is not None and pk in cache:
        return cache[pk]

    corpus = BaseService.get_or_none(
        Corpus, pk, info.context.user, request=info.context
    )

    if cache is not None:
        cache[pk] = corpus
    return corpus


# NOTE: ``get_node`` is intentionally NOT registered here. graphene served the
# top-level ``corpus(id:)`` query via ``OpenContractsNode.Field`` — an
# UNCACHED ``BaseService.get_or_none`` fetched fresh on every request — while
# the cached ``CorpusType.get_node`` (``_get_node_CorpusType``) served
# FK-via-Node access. Routing ``corpus(id:)`` through the cached hook leaked a
# stale ``Corpus`` object across requests that reuse one context object (the
# permissioning tests do exactly this, changing perms between executes), so
# the top-level query uses the default node path (the visibility-filtered
# ``get_queryset`` + ``.get(pk)`` — equivalent to graphene's uncached
# ``get_or_none`` READ). ``_get_node_CorpusType`` is still installed on the
# class as a graphene-compat ``get_node`` (for the request-cache unit test)
# via ``_install_graphene_resolver_aliases``.
register_type(
    "CorpusType",
    CorpusType,
    model=Corpus,
    get_queryset=_get_queryset_CorpusType,
)


# ---------------- Corpus Group Types (issue #2056) ----------------
def _resolve_CorpusGroupType_corpora(root, info):
    """Return only the member corpora the viewer can READ."""
    from opencontractserver.corpuses.services import CorpusGroupService

    user = getattr(info.context, "user", None)
    return CorpusGroupService.get_group_corpora_visible_to_user(
        user, root, request=info.context
    )


@strawberry.type(
    name="CorpusGroupType",
    description="GraphQL type for CorpusGroup — a bundle of corpora for multi-corpus retrieval.\n\n``corpora`` is resolved through CorpusGroupService so members the viewer cannot READ are never listed (MIN(corpus_permission, group_membership) — the same call-time semantics the search_across_corpora agent tool uses).",
)
class CorpusGroupType(Node):
    @strawberry.field(name="title")
    def title(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "title", None))

    @strawberry.field(name="slug")
    def slug(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "slug", None))

    @strawberry.field(name="description")
    def description(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "description", None))

    is_public: bool = strawberry.field(name="isPublic", default=None)
    created: datetime.datetime = strawberry.field(name="created", default=None)
    modified: datetime.datetime = strawberry.field(name="modified", default=None)
    creator: Annotated[UserType, strawberry.lazy("config.graphql.user_types")] = (
        strawberry.field(name="creator", default=None)
    )

    @strawberry.field(
        name="corpora", description="Member corpora visible to the viewer"
    )
    def corpora(
        self,
        info: strawberry.Info,
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
    ) -> CorpusTypeConnection:
        kwargs = strip_unset(
            {"before": before, "after": after, "first": first, "last": last}
        )
        resolved = _resolve_CorpusGroupType_corpora(self, info)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="CorpusType",
        )

    @strawberry.field(
        name="defaultAgent",
        description="Orchestrator agent bound to this group, visible only if the viewer can READ it.",
    )
    def default_agent(
        self, info: strawberry.Info
    ) -> None | (
        Annotated[AgentConfigurationType, strawberry.lazy("config.graphql.agent_types")]
    ):
        return resolve_visible_fk(
            self, info, "default_agent_id", "AgentConfigurationType"
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


def _get_queryset_CorpusGroupType(queryset, info):
    return BaseService.filter_visible_qs(
        queryset, info.context.user, request=info.context
    )


register_type(
    "CorpusGroupType",
    CorpusGroupType,
    model=CorpusGroup,
    get_queryset=_get_queryset_CorpusGroupType,
)


CorpusGroupTypeConnection = make_connection_types(
    CorpusGroupType,
    type_name="CorpusGroupTypeConnection",
    countable=True,
    pdf_page_aware=False,
)


CorpusTypeConnection = make_connection_types(
    CorpusType, type_name="CorpusTypeConnection", countable=True, pdf_page_aware=False
)


def _resolve_CorpusCategoryType_corpus_count(root, info):
    """
    Return count of corpuses visible to user in this category.

    NOTE: This resolver could cause N+1 queries if many categories are fetched.
    The resolve_corpus_categories query uses annotation to pre-compute counts
    to avoid this issue.
    """
    # If the count was pre-annotated by the query resolver, use it
    if hasattr(root, "_corpus_count"):
        return root._corpus_count
    # Fallback to dynamic count (used when accessed individually)
    user = info.context.user
    visible_corpus_ids = BaseService.filter_visible(
        Corpus, user, request=info.context
    ).values("pk")
    return root.corpuses.filter(pk__in=visible_corpus_ids).count()


@strawberry.type(
    name="CorpusCategoryType",
    description='GraphQL type for corpus categories.\n\nNOTE: This type does NOT use AnnotatePermissionsForReadMixin because\ncorpus categories are admin-provisioned structural data that is globally\nvisible to all users and do not have per-user permissions.\n\nCategories are managed by superusers either via Django Admin or at\nruntime through the create/update/deleteCorpusCategory GraphQL mutations\n(see config/graphql/corpus_category_mutations.py) and the in-app\n"Corpus Categories" admin panel.\n\nSee docs/permissioning/consolidated_permissioning_guide.md for details.',
)
class CorpusCategoryType(Node):
    is_public: bool = strawberry.field(name="isPublic", default=None)
    creator: Annotated[UserType, strawberry.lazy("config.graphql.user_types")] = (
        strawberry.field(name="creator", default=None)
    )
    created: datetime.datetime = strawberry.field(name="created", default=None)
    modified: datetime.datetime = strawberry.field(name="modified", default=None)

    @strawberry.field(name="name")
    def name(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "name", None))

    @strawberry.field(name="description")
    def description(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "description", None))

    @strawberry.field(
        name="icon",
        description="Lucide icon name (e.g., 'scroll', 'file-text', 'building-2')",
    )
    def icon(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "icon", None))

    @strawberry.field(name="color", description="Hex color code for the category badge")
    def color(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "color", None))

    sort_order: int = strawberry.field(
        name="sortOrder",
        description="Order in which categories appear in UI",
        default=None,
    )

    @strawberry.field(
        name="corpusCount", description="Number of corpuses in this category"
    )
    def corpus_count(self, info: strawberry.Info) -> int | None:
        kwargs = strip_unset({})
        return _resolve_CorpusCategoryType_corpus_count(self, info, **kwargs)


register_type("CorpusCategoryType", CorpusCategoryType, model=CorpusCategory)


CorpusCategoryTypeConnection = make_connection_types(
    CorpusCategoryType,
    type_name="CorpusCategoryTypeConnection",
    countable=True,
    pdf_page_aware=False,
)


def _resolve_CorpusFolderType_parent(root, info):
    """Return the in-memory ``parent`` cached by ``select_related``.

    graphene-django's auto-generated FK resolver re-queried through
    ``CorpusFolderType.get_queryset`` (which chains
    ``visible_to_user().with_tree_fields()``), firing a recursive
    CTE plus two guardian-permission subqueries per row on the
    folder-list view — the exact ``N`` fan-out the
    :meth:`FolderCRUDService.get_visible_folders_with_aggregates`
    rewrite was supposed to kill. The parent is already
    ``select_related``-cached on the in-memory folder instance and
    the surrounding visibility filter authorised ``root``, so reading
    from the cache is equivalent and skips the per-row query. (The
    graphene ``_bypass_get_queryset`` shim flag is unnecessary here —
    the strawberry wrapper calls this resolver directly.)
    """
    if root.parent_id is None:
        return None
    cached = root._state.fields_cache.get("parent")
    if cached is not None:
        return cached
    # Single-folder reads (no select_related) fall back to the
    # auto-generated resolver semantics via the standard descriptor.
    return root.parent


def _resolve_CorpusFolderType_children(root, info):
    """Get immediate child folders (service-layer visibility)."""
    return BaseService.filter_visible_qs(
        root.children, info.context.user, request=info.context
    )


def _resolve_CorpusFolderType_my_permissions(root, info):
    """Permissions are inherited from the parent corpus.

    ``CorpusFolder`` rows never carry guardian permission rows (see
    ``opencontractserver/corpuses/models.py`` ``CorpusFolder`` class
    docstring), so the default
    :meth:`AnnotatePermissionsForReadMixin.resolve_my_permissions`
    would burn two empty ``.filter()`` queries per folder against
    ``corpusfolderuserobjectpermission_set`` and
    ``corpusfoldergroupobjectpermission_set`` — a ``2N`` fan-out on the
    folder-list view. Resolve once per ``(corpus, user)`` per request
    by delegating to the parent corpus's resolver and translating the
    permission strings.
    """
    context = info.context
    user = getattr(context, "user", None)
    if user is None or not is_authenticated_user(user):
        # Anonymous users get ``read_corpusfolder`` whenever the
        # *corpus* is public OR the folder is explicitly public.
        # ``CorpusFolder.user_can`` delegates to the corpus, so the
        # corpus's public-read grant authorises folder access; the
        # permissions list must mirror that decision (otherwise the
        # frontend disables folder-read UI for an anon viewer of a
        # public corpus). The mixin's bare ``self.is_public`` branch
        # would only consult the folder row.
        if root.corpus.is_public or root.is_public:
            return ["read_corpusfolder"]
        return []

    cache_attr = f"_corpus_folder_perms_{root.corpus_id}_{user.id}"
    cached = getattr(context, cache_attr, None)
    if cached is None:
        corpus_perms = core_permissions.resolve_my_permissions(root.corpus, info)
        # corpus_perms entries end in ``_corpus`` (e.g. ``read_corpus``);
        # rewrite to the folder model name so the API contract matches
        # what the AnnotatePermissionsForReadMixin would have returned.
        cached = [
            (
                f"{perm[: -len('corpus')]}corpusfolder"
                if perm.endswith("_corpus")
                else perm
            )
            for perm in corpus_perms
        ]
        setattr(context, cache_attr, cached)

    if root.is_public and "read_corpusfolder" not in cached:
        return [*cached, "read_corpusfolder"]
    return list(cached)


def _resolve_CorpusFolderType_is_published(root, info):
    """``CorpusFolder`` rows never carry guardian permission rows, so the
    ``DEFAULT_PERMISSIONS_GROUP`` is never granted on a folder; the
    answer is always ``False``. Override the mixin's
    :meth:`resolve_is_published` to skip the per-folder
    ``get_groups_with_perms`` + ``.filter().count()`` queries it would
    otherwise run on the folder-list view.
    """
    return False


def _resolve_CorpusFolderType_path(root, info):
    """Get full path from root to this folder.

    Prefers the ``_path`` attribute attached by
    :meth:`FolderCRUDService.get_visible_folders_with_aggregates` so the
    list-view resolver doesn't fire a recursive ancestor CTE per folder.
    Falls back to the per-folder ``get_path()`` for single-folder reads
    (e.g. the ``corpusFolder(id:)`` resolver).
    """
    if hasattr(root, "_path"):
        return root._path
    return root.get_path()


def _resolve_CorpusFolderType_document_count(root, info):
    """Get count of documents directly in this folder.

    Prefers the ``_doc_count`` attribute attached by
    :meth:`FolderCRUDService.get_visible_folders_with_aggregates` so the
    list-view resolver doesn't fire a per-folder ``COUNT`` on
    ``DocumentPath``.
    """
    if hasattr(root, "_doc_count"):
        return root._doc_count
    return root.get_document_count()


def _resolve_CorpusFolderType_descendant_document_count(root, info):
    """Get count of documents in this folder and all subfolders.

    Prefers the ``_descendant_doc_count`` attribute attached by
    :meth:`FolderCRUDService.get_visible_folders_with_aggregates` so the
    list-view resolver doesn't fire a recursive descendant CTE + COUNT
    per folder.
    """
    if hasattr(root, "_descendant_doc_count"):
        return root._descendant_doc_count
    return root.get_descendant_document_count()


@strawberry.type(
    name="CorpusFolderType",
    description="GraphQL type for corpus folders.\nFolders inherit permissions from their parent corpus.",
)
class CorpusFolderType(Node):
    @strawberry.field(name="parent")
    def parent(self, info: strawberry.Info) -> CorpusFolderType | None:
        kwargs = strip_unset({})
        return _resolve_CorpusFolderType_parent(self, info, **kwargs)

    @strawberry.field(name="name", description="Folder name (not full path)")
    def name(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "name", None))

    corpus: CorpusType = strawberry.field(
        name="corpus", description="Parent corpus this folder belongs to", default=None
    )

    @strawberry.field(name="description")
    def description(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "description", None))

    @strawberry.field(name="color", description="Hex color for UI display")
    def color(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "color", None))

    @strawberry.field(name="icon", description="Icon identifier for UI")
    def icon(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "icon", None))

    tags: JSONString = strawberry.field(
        name="tags", description="List of tags for categorization", default=None
    )
    is_public: bool = strawberry.field(name="isPublic", default=None)
    created: datetime.datetime = strawberry.field(name="created", default=None)
    modified: datetime.datetime = strawberry.field(name="modified", default=None)
    creator: Annotated[UserType, strawberry.lazy("config.graphql.user_types")] = (
        strawberry.field(name="creator", default=None)
    )

    @strawberry.field(
        name="documentPaths",
        description="Current folder (null if folder deleted or at root)",
    )
    def document_paths(
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
        DocumentPathTypeConnection, strawberry.lazy("config.graphql.document_types")
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
        resolved = getattr(self, "document_paths", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="DocumentPathType",
        )

    @strawberry.field(name="children", description="Immediate child folders")
    def children(self, info: strawberry.Info) -> list[CorpusFolderType | None] | None:
        kwargs = strip_unset({})
        return _resolve_CorpusFolderType_children(self, info, **kwargs)

    @strawberry.field(name="myPermissions")
    def my_permissions(self, info: strawberry.Info) -> GenericScalar | None:
        kwargs = strip_unset({})
        return _resolve_CorpusFolderType_my_permissions(self, info, **kwargs)

    @strawberry.field(name="isPublished")
    def is_published(self, info: strawberry.Info) -> bool | None:
        kwargs = strip_unset({})
        return _resolve_CorpusFolderType_is_published(self, info, **kwargs)

    @strawberry.field(name="objectSharedWith")
    def object_shared_with(self, info: strawberry.Info) -> GenericScalar | None:
        return core_permissions.resolve_object_shared_with(self, info)

    @strawberry.field(name="path", description="Full path from root to this folder")
    def path(self, info: strawberry.Info) -> str | None:
        kwargs = strip_unset({})
        return _resolve_CorpusFolderType_path(self, info, **kwargs)

    @strawberry.field(
        name="documentCount", description="Number of documents directly in this folder"
    )
    def document_count(self, info: strawberry.Info) -> int | None:
        kwargs = strip_unset({})
        return _resolve_CorpusFolderType_document_count(self, info, **kwargs)

    @strawberry.field(
        name="descendantDocumentCount",
        description="Number of documents in this folder and all subfolders",
    )
    def descendant_document_count(self, info: strawberry.Info) -> int | None:
        kwargs = strip_unset({})
        return _resolve_CorpusFolderType_descendant_document_count(self, info, **kwargs)


def _get_queryset_CorpusFolderType(queryset, info):
    """Filter folders to only those the user can see (via corpus permissions)."""
    # Chain ``visible_to_user`` on the incoming queryset/manager so the
    # filter is a single ``WHERE`` expression tree (no ``pk__in``
    # subquery over the full table).
    return BaseService.filter_visible_qs(
        queryset, info.context.user, request=info.context
    )


register_type(
    "CorpusFolderType",
    CorpusFolderType,
    model=CorpusFolder,
    get_queryset=_get_queryset_CorpusFolderType,
)


CorpusFolderTypeConnection = make_connection_types(
    CorpusFolderType,
    type_name="CorpusFolderTypeConnection",
    countable=True,
    pdf_page_aware=False,
)


@strawberry.type(
    name="CorpusEngagementMetricsType",
    description="GraphQL type for corpus engagement metrics.\n\nThis type does NOT use AnnotatePermissionsForReadMixin because\nengagement metrics are read-only and permissions are checked on\nthe parent Corpus object.\n\nEpic: #565 - Corpus Engagement Metrics & Analytics\nIssue: #568 - Create GraphQL queries for engagement metrics and leaderboards",
)
class CorpusEngagementMetricsType:
    total_threads: int | None = strawberry.field(
        name="totalThreads",
        description="Total number of discussion threads in this corpus",
        default=None,
    )
    active_threads: int | None = strawberry.field(
        name="activeThreads",
        description="Number of active (not locked/deleted) threads",
        default=None,
    )
    total_messages: int | None = strawberry.field(
        name="totalMessages",
        description="Total number of messages across all threads",
        default=None,
    )
    messages_last_7_days: int | None = strawberry.field(
        name="messagesLast7Days",
        description="Number of messages posted in the last 7 days",
        default=None,
    )
    messages_last_30_days: int | None = strawberry.field(
        name="messagesLast30Days",
        description="Number of messages posted in the last 30 days",
        default=None,
    )
    unique_contributors: int | None = strawberry.field(
        name="uniqueContributors",
        description="Total number of unique users who have posted messages",
        default=None,
    )
    active_contributors_30_days: int | None = strawberry.field(
        name="activeContributors30Days",
        description="Number of users who posted in the last 30 days",
        default=None,
    )
    total_upvotes: int | None = strawberry.field(
        name="totalUpvotes",
        description="Total upvotes across all messages in this corpus",
        default=None,
    )
    avg_messages_per_thread: float | None = strawberry.field(
        name="avgMessagesPerThread",
        description="Average number of messages per thread",
        default=None,
    )
    last_updated: datetime.datetime | None = strawberry.field(
        name="lastUpdated",
        description="Timestamp when metrics were last calculated",
        default=None,
    )


register_type("CorpusEngagementMetricsType", CorpusEngagementMetricsType, model=None)


def _resolve_CorpusDescriptionRevisionType_id(root, info):
    """Document primary key — used as the revision identity."""
    return root.pk


def _resolve_CorpusDescriptionRevisionType_version(root, info):
    """1-indexed position within the version_tree, oldest first.

    Mirrors the legacy ``CorpusDescriptionRevision.version`` counter
    so the frontend's "Version N" header keeps lining up. Reads the
    index pre-computed by the list resolver
    (``CorpusType.resolve_description_revisions``); falls back to a
    per-row query when the instance is resolved outside that list
    path (e.g. node(id:) — uncommon for this facade type).
    """
    precomputed = getattr(root, "_version_index", None)
    if precomputed is not None:
        return precomputed

    from opencontractserver.constants.document_processing import (
        CAML_ARTICLE_TITLE,
        MARKDOWN_MIME_TYPE,
    )
    from opencontractserver.documents.models import Document

    ordered_ids = list(
        Document.objects.filter(
            version_tree_id=root.version_tree_id,
            title=CAML_ARTICLE_TITLE,
            file_type=MARKDOWN_MIME_TYPE,
        )
        .order_by("created", "pk")
        .values_list("pk", flat=True)
    )
    try:
        return ordered_ids.index(root.pk) + 1
    except ValueError:
        return None


def _resolve_CorpusDescriptionRevisionType_author(root, info):
    """Document creator — historical revisions used ``author``."""
    return root.creator


def _resolve_CorpusDescriptionRevisionType_snapshot(root, info):
    """Read the Document's txt_extract_file body on demand.

    Each Readme.CAML version-tree sibling stores the full markdown
    in ``txt_extract_file``; the legacy ``snapshot`` column on
    ``CorpusDescriptionRevision`` carried the same content, so this
    is a 1:1 swap for the frontend rev viewer. Reads go through the
    shared ``read_caml_body`` helper (promoted from a private helper
    in ``corpuses/signals.py`` to ``description_cache.py`` for DRY) so the I/O
    contract — text-mode then binary-fallback — matches the
    cache-refresh signal handler exactly.

    Performance (accepted trade-off): each call opens one
    ``txt_extract_file`` blob, so requesting ``snapshot`` for every
    revision in one query is N storage round-trips. Pre-reading the
    bodies in the list resolver would not reduce that count (object
    storage has no batch read), so the effective fix is to fetch
    ``snapshot`` only on a single-revision drill-down rather than in
    the list query. The list path is the modal-only revision viewer,
    so the N reads
    are bounded by the revision count a human is browsing.
    """
    from opencontractserver.corpuses.services.description_cache import (
        read_caml_body,
    )

    return read_caml_body(root)


def _resolve_CorpusDescriptionRevisionType_created(root, info):
    """Document creation timestamp — historical revisions used the
    same field name."""
    return root.created


@strawberry.type(
    name="CorpusDescriptionRevisionType",
    description="Backwards-compatible facade over a Readme.CAML version-tree sibling.\n\nThe legacy ``CorpusDescriptionRevision`` model was dropped in\nmigration 0055. The GraphQL shape is preserved by mapping each\nDocument sibling's metadata onto the historical fields, so the\nfrontend revision-history viewer renders without changes. The\ninstance bound to each resolver is a\n``opencontractserver.documents.models.Document`` row (a Readme.CAML\nversion-tree sibling), NOT a ``CorpusDescriptionRevision``.\n\nThe legacy ``diff`` field is dropped: clients that need a unified\ndiff compute it on the fly from successive ``snapshot`` values via\n``difflib`` rather than reading a pre-stored payload. Queries that\nstill reference ``diff`` will fail GraphQL validation — remove it\nfrom the frontend query to eliminate the field entirely.\n\nSpec: ``docs/superpowers/specs/2026-05-27-canonical-caml-description-refactor-design.md`` §4.5",
)
class CorpusDescriptionRevisionType:
    @strawberry.field(name="id")
    def id(self, info: strawberry.Info) -> strawberry.ID:
        kwargs = strip_unset({})
        return _resolve_CorpusDescriptionRevisionType_id(self, info, **kwargs)

    @strawberry.field(name="version")
    def version(self, info: strawberry.Info) -> int | None:
        kwargs = strip_unset({})
        return _resolve_CorpusDescriptionRevisionType_version(self, info, **kwargs)

    @strawberry.field(name="author")
    def author(
        self, info: strawberry.Info
    ) -> Annotated[UserType, strawberry.lazy("config.graphql.user_types")] | None:
        kwargs = strip_unset({})
        return _resolve_CorpusDescriptionRevisionType_author(self, info, **kwargs)

    @strawberry.field(name="snapshot")
    def snapshot(self, info: strawberry.Info) -> str | None:
        kwargs = strip_unset({})
        return _resolve_CorpusDescriptionRevisionType_snapshot(self, info, **kwargs)

    @strawberry.field(name="created")
    def created(self, info: strawberry.Info) -> datetime.datetime | None:
        kwargs = strip_unset({})
        return _resolve_CorpusDescriptionRevisionType_created(self, info, **kwargs)


register_type(
    "CorpusDescriptionRevisionType", CorpusDescriptionRevisionType, model=None
)


@strawberry.type(
    name="CorpusFilterCountsType",
    description="Counts of corpuses visible to the user, broken down by tab filter.\n\nEach count respects guardian permissions (matches BaseService.filter_visible(Corpus, user))\nso tab badges in the corpus list view stay accurate without paginating every\npage on the client.",
)
class CorpusFilterCountsType:
    all: int = strawberry.field(name="all", default=None)
    mine: int = strawberry.field(name="mine", default=None)
    shared: int = strawberry.field(name="shared", default=None)
    public: int = strawberry.field(name="public", default=None)


register_type("CorpusFilterCountsType", CorpusFilterCountsType, model=None)


@strawberry.type(
    name="CorpusIntelligenceSetupStatusType",
    description="Which intelligence-bundle pieces a corpus already has installed.",
)
class CorpusIntelligenceSetupStatusType:
    reference_available: bool = strawberry.field(
        name="referenceAvailable",
        description="The reference-enrichment analyzer is registered on this deployment.",
        default=None,
    )
    reference_action_installed: bool = strawberry.field(
        name="referenceActionInstalled", default=None
    )
    installed_template_names: list[str] = strawberry.field(
        name="installedTemplateNames", default=None
    )
    missing_template_names: list[str] = strawberry.field(
        name="missingTemplateNames", default=None
    )
    is_fully_set_up: bool = strawberry.field(
        name="isFullySetUp",
        description="Every deployment-installable bundle piece is installed (unavailable pieces — unregistered analyzer, inactive template — are excluded).",
        default=None,
    )
    can_setup: bool = strawberry.field(
        name="canSetup",
        description="The requesting user holds the permission setupCorpusIntelligence requires (CRUD) — drives the setup CTA's visibility.",
        default=None,
    )


register_type(
    "CorpusIntelligenceSetupStatusType", CorpusIntelligenceSetupStatusType, model=None
)


@strawberry.type(name="CorpusStatsType")
class CorpusStatsType:
    total_docs: int | None = strawberry.field(name="totalDocs", default=None)
    total_annotations: int | None = strawberry.field(
        name="totalAnnotations", default=None
    )
    total_comments: int | None = strawberry.field(name="totalComments", default=None)
    total_analyses: int | None = strawberry.field(name="totalAnalyses", default=None)
    total_extracts: int | None = strawberry.field(name="totalExtracts", default=None)
    total_threads: int | None = strawberry.field(name="totalThreads", default=None)
    total_chats: int | None = strawberry.field(name="totalChats", default=None)
    total_relationships: int | None = strawberry.field(
        name="totalRelationships", default=None
    )


register_type("CorpusStatsType", CorpusStatsType, model=None)


@strawberry.type(
    name="CorpusDocumentGraphType",
    description="The corpus document-relationship graph (node-link form).\n\nBuilt entirely from permission-filtered ``DocumentRelationship`` rows via\n``DocumentRelationshipService`` — documents that participate in at least\none visible relationship, ranked by degree and capped for the glimpse.",
)
class CorpusDocumentGraphType:
    nodes: list[CorpusDocumentGraphNodeType] = strawberry.field(
        name="nodes", default=None
    )
    edges: list[CorpusDocumentGraphEdgeType] = strawberry.field(
        name="edges", default=None
    )
    total_node_count: int = strawberry.field(
        name="totalNodeCount",
        description="Distinct documents participating in any visible relationship.",
        default=None,
    )
    total_edge_count: int = strawberry.field(
        name="totalEdgeCount",
        description="Total visible relationships in the corpus.",
        default=None,
    )
    truncated: bool = strawberry.field(
        name="truncated",
        description="True when nodes/edges were dropped to honor the limit.",
        default=None,
    )


register_type("CorpusDocumentGraphType", CorpusDocumentGraphType, model=None)


@strawberry.type(
    name="CorpusDocumentGraphNodeType",
    description="A single document node in the corpus document-relationship graph.\n\nPowers the ``DocumentGraphGlimpse`` on the Corpus Intelligence home — a\nnode is a document, sized by ``degree`` (its visible relationship count).",
)
class CorpusDocumentGraphNodeType:
    id: strawberry.ID = strawberry.field(
        name="id", description="Global DocumentType id (navigable).", default=None
    )
    title: str | None = strawberry.field(name="title", default=None)
    file_type: str | None = strawberry.field(name="fileType", default=None)
    degree: int = strawberry.field(
        name="degree",
        description="Number of visible relationships touching this document.",
        default=None,
    )


register_type("CorpusDocumentGraphNodeType", CorpusDocumentGraphNodeType, model=None)


@strawberry.type(
    name="CorpusDocumentGraphEdgeType",
    description="A labeled directed edge between two document nodes.",
)
class CorpusDocumentGraphEdgeType:
    id: strawberry.ID = strawberry.field(name="id", default=None)
    source: strawberry.ID = strawberry.field(
        name="source", description="Global id of the source document.", default=None
    )
    target: strawberry.ID = strawberry.field(
        name="target", description="Global id of the target document.", default=None
    )
    label: str | None = strawberry.field(
        name="label",
        description="Relationship label text (null for NOTES).",
        default=None,
    )
    relationship_type: str | None = strawberry.field(
        name="relationshipType", default=None
    )


register_type("CorpusDocumentGraphEdgeType", CorpusDocumentGraphEdgeType, model=None)


@strawberry.type(
    name="CorpusIntelligenceAggregatesType",
    description="At-a-glance corpus intelligence framed as insight, not raw counts.\n\nFeeds the ``IntelligencePanel`` on the Corpus Intelligence home. Counts\nrespect the permission model (visible documents only).",
)
class CorpusIntelligenceAggregatesType:
    label_distribution: list[LabelDistributionEntryType] = strawberry.field(
        name="labelDistribution",
        description="Top annotation labels by frequency across visible documents.",
        default=None,
    )
    documents_with_summary: int = strawberry.field(
        name="documentsWithSummary",
        description="Visible documents that have a markdown summary.",
        default=None,
    )
    total_documents: int = strawberry.field(
        name="totalDocuments",
        description="Visible documents with an active path in the corpus.",
        default=None,
    )


register_type(
    "CorpusIntelligenceAggregatesType", CorpusIntelligenceAggregatesType, model=None
)


@strawberry.type(
    name="LabelDistributionEntryType",
    description="One label and how often it appears across the corpus's visible annotations.",
)
class LabelDistributionEntryType:
    label: str = strawberry.field(name="label", default=None)
    color: str | None = strawberry.field(name="color", default=None)
    count: int = strawberry.field(name="count", default=None)


register_type("LabelDistributionEntryType", LabelDistributionEntryType, model=None)


@strawberry.type(
    name="CorpusDataStoryType",
    description="Per-document structured profiles for the corpus-home data story.\n\nThe frontend aggregates these rows into composition / timeline / value views.\nBuilt corpus-as-gate from the default ``Collection Profile`` extract (the\nsource corpus must be READ-visible); ``null`` when no profile extract exists\nyet, so the embed self-hides until the extraction has run.",
)
class CorpusDataStoryType:
    total_documents: int = strawberry.field(name="totalDocuments", default=None)
    profiles: list[CorpusDataStoryProfileType] = strawberry.field(
        name="profiles", default=None
    )


register_type("CorpusDataStoryType", CorpusDataStoryType, model=None)


@strawberry.type(
    name="CorpusDataStoryProfileType",
    description="One document's normalised structured profile for the corpus data story.\n\nValues are cleaned server-side (markdown stripped, dates parsed to ISO out of\nLLM prose, value coerced to a positive float) so the frontend only renders.",
)
class CorpusDataStoryProfileType:
    document_id: strawberry.ID = strawberry.field(name="documentId", default=None)
    title: str = strawberry.field(name="title", default=None)
    slug: str | None = strawberry.field(name="slug", default=None)
    type: str | None = strawberry.field(
        name="type", description="Short document/agreement category.", default=None
    )
    party: str | None = strawberry.field(
        name="party", description="Primary counterparty / organisation.", default=None
    )
    effective_date: str | None = strawberry.field(
        name="effectiveDate",
        description="Effective date, ISO YYYY-MM-DD.",
        default=None,
    )
    value: float | None = strawberry.field(
        name="value",
        description="Primary dollar value, positive or null.",
        default=None,
    )


register_type("CorpusDataStoryProfileType", CorpusDataStoryProfileType, model=None)


@strawberry.type(
    name="ArtifactType",
    description="A shareable, data-driven corpus poster (an :class:`Artifact`).\n\nBuilt corpus-as-gate by ``ArtifactService`` — exposed only when the source\ncorpus is READ-visible to the caller. Carries the template id + configurable\ncaptions the public ``/a/<slug>`` poster route renders from live corpus data.",
)
class ArtifactType:
    id: strawberry.ID = strawberry.field(name="id", default=None)
    slug: str = strawberry.field(name="slug", default=None)
    template: str = strawberry.field(name="template", default=None)
    title: str | None = strawberry.field(name="title", default=None)
    subtitle: str | None = strawberry.field(name="subtitle", default=None)
    byline: str | None = strawberry.field(name="byline", default=None)
    config: GenericScalar | None = strawberry.field(name="config", default=None)
    corpus_id: strawberry.ID = strawberry.field(name="corpusId", default=None)
    corpus_slug: str | None = strawberry.field(name="corpusSlug", default=None)
    creator_slug: str | None = strawberry.field(name="creatorSlug", default=None)
    image_url: str | None = strawberry.field(name="imageUrl", default=None)
    created: datetime.datetime | None = strawberry.field(name="created", default=None)


register_type("ArtifactType", ArtifactType, model=None)


@strawberry.type(
    name="ArtifactTemplateType",
    description="A template the artifact gallery can offer a corpus, with data-gated\neligibility (a corpus only sees templates its own data can fill).",
)
class ArtifactTemplateType:
    id: str = strawberry.field(name="id", default=None)
    label: str = strawberry.field(name="label", default=None)
    description: str | None = strawberry.field(name="description", default=None)
    eligible: bool = strawberry.field(name="eligible", default=None)
    reason: str | None = strawberry.field(name="reason", default=None)


register_type("ArtifactTemplateType", ArtifactTemplateType, model=None)


@strawberry.type(
    name="CorpusIntelligenceSetupSummaryType",
    description="Result envelope for ``setupCorpusIntelligence``.\n\nMirrors ``IntelligenceSetupSummary`` from\n``opencontractserver.corpuses.services.intelligence_setup`` — graphene's\ndefault resolver reads the dataclass attributes directly.",
)
class CorpusIntelligenceSetupSummaryType:
    reference_available: bool = strawberry.field(
        name="referenceAvailable",
        description="The reference-enrichment analyzer is registered on this deployment.",
        default=None,
    )
    reference_action_installed_now: bool = strawberry.field(
        name="referenceActionInstalledNow", default=None
    )
    reference_action_already_installed: bool = strawberry.field(
        name="referenceActionAlreadyInstalled", default=None
    )
    reference_analysis_started: bool = strawberry.field(
        name="referenceAnalysisStarted",
        description="An immediate reference-web weave was started.",
        default=None,
    )
    total_active_documents: int = strawberry.field(
        name="totalActiveDocuments", default=None
    )
    templates: list[IntelligenceTemplateOutcomeType] = strawberry.field(
        name="templates", default=None
    )


register_type(
    "CorpusIntelligenceSetupSummaryType", CorpusIntelligenceSetupSummaryType, model=None
)


@strawberry.type(
    name="IntelligenceTemplateOutcomeType",
    description="Per-template result from the one-click intelligence setup.",
)
class IntelligenceTemplateOutcomeType:
    template_name: str = strawberry.field(name="templateName", default=None)
    installed_now: bool = strawberry.field(
        name="installedNow",
        description="Template was cloned into the corpus by this call.",
        default=None,
    )
    already_installed: bool = strawberry.field(
        name="alreadyInstalled",
        description="The corpus already had this template's action.",
        default=None,
    )
    queued_count: int = strawberry.field(
        name="queuedCount",
        description="Documents queued for an agent run by this call.",
        default=None,
    )
    skipped_already_run_count: int = strawberry.field(
        name="skippedAlreadyRunCount",
        description="Documents skipped because they already ran.",
        default=None,
    )
    error: str = strawberry.field(
        name="error",
        description="Per-template failure (empty string when the step succeeded).",
        default=None,
    )
    remaining_count: int = strawberry.field(
        name="remainingCount",
        description="Documents deferred past the per-call batch cap — re-run setup (or wait for the add_document trigger) to process them.",
        default=None,
    )


register_type(
    "IntelligenceTemplateOutcomeType", IntelligenceTemplateOutcomeType, model=None
)


def q_corpus(
    info: strawberry.Info,
    id: Annotated[
        strawberry.ID,
        strawberry.argument(name="id", description="The ID of the object"),
    ] = strawberry.UNSET,
) -> CorpusType | None:
    return get_node_from_global_id(info, id, only_type_name="CorpusType")


QUERY_FIELDS = {
    "corpus": strawberry.field(resolver=q_corpus, name="corpus"),
}
