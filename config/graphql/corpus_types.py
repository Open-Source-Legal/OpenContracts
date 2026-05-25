"""GraphQL type definitions for corpus-related types."""

import logging
from typing import Any

import graphene
from django.contrib.auth import get_user_model
from graphene import relay
from graphene_django import DjangoObjectType
from graphql_relay import from_global_id

from config.graphql.annotation_types import AnnotationType
from config.graphql.base import CountableConnection
from config.graphql.base_types import LabelTypeEnum
from config.graphql.document_types import DocumentTypeConnection
from config.graphql.permissioning.permission_annotator.mixins import (
    AnnotatePermissionsForReadMixin,
)
from opencontractserver.annotations.models import Annotation
from opencontractserver.corpuses.models import (
    Corpus,
    CorpusCategory,
    CorpusDescriptionRevision,
    CorpusEngagementMetrics,
    CorpusFolder,
)
from opencontractserver.shared.services.base import BaseService

User = get_user_model()
logger = logging.getLogger(__name__)


# ---------------- Corpus Category Types ----------------
class CorpusCategoryType(DjangoObjectType):
    """
    GraphQL type for corpus categories.

    NOTE: This type does NOT use AnnotatePermissionsForReadMixin because
    corpus categories are admin-provisioned structural data that is globally
    visible to all users. Categories are managed via Django Admin only and
    do not have per-user permissions.

    See docs/permissioning/consolidated_permissioning_guide.md for details.
    """

    corpus_count = graphene.Int(description="Number of corpuses in this category")

    class Meta:
        model = CorpusCategory
        interfaces = (relay.Node,)
        connection_class = CountableConnection
        fields = (
            "id",
            "name",
            "description",
            "icon",
            "color",
            "sort_order",
            "creator",
            "is_public",
            "created",
            "modified",
        )

    def resolve_corpus_count(self, info) -> Any:
        """
        Return count of corpuses visible to user in this category.

        NOTE: This resolver could cause N+1 queries if many categories are fetched.
        The resolve_corpus_categories query uses annotation to pre-compute counts
        to avoid this issue.
        """
        # If the count was pre-annotated by the query resolver, use it
        if hasattr(self, "_corpus_count"):
            return self._corpus_count
        # Fallback to dynamic count (used when accessed individually)
        user = info.context.user
        visible_corpus_ids = BaseService.filter_visible(
            Corpus, user, request=info.context
        ).values("pk")
        return self.corpuses.filter(pk__in=visible_corpus_ids).count()


# ---------------- Engagement Metrics Types (Epic #565) ----------------
class CorpusEngagementMetricsType(graphene.ObjectType):
    """
    GraphQL type for corpus engagement metrics.

    This type does NOT use AnnotatePermissionsForReadMixin because
    engagement metrics are read-only and permissions are checked on
    the parent Corpus object.

    Epic: #565 - Corpus Engagement Metrics & Analytics
    Issue: #568 - Create GraphQL queries for engagement metrics and leaderboards
    """

    # Thread counts
    total_threads = graphene.Int(
        description="Total number of discussion threads in this corpus"
    )
    active_threads = graphene.Int(
        description="Number of active (not locked/deleted) threads"
    )

    # Message counts
    total_messages = graphene.Int(
        description="Total number of messages across all threads"
    )
    messages_last_7_days = graphene.Int(
        description="Number of messages posted in the last 7 days"
    )
    messages_last_30_days = graphene.Int(
        description="Number of messages posted in the last 30 days"
    )

    # Contributor counts
    unique_contributors = graphene.Int(
        description="Total number of unique users who have posted messages"
    )
    active_contributors_30_days = graphene.Int(
        description="Number of users who posted in the last 30 days"
    )

    # Engagement metrics
    total_upvotes = graphene.Int(
        description="Total upvotes across all messages in this corpus"
    )
    avg_messages_per_thread = graphene.Float(
        description="Average number of messages per thread"
    )

    # Metadata
    last_updated = graphene.DateTime(
        description="Timestamp when metrics were last calculated"
    )


class CorpusFolderType(AnnotatePermissionsForReadMixin, DjangoObjectType):
    """
    GraphQL type for corpus folders.
    Folders inherit permissions from their parent corpus.
    """

    path = graphene.String(description="Full path from root to this folder")
    document_count = graphene.Int(
        description="Number of documents directly in this folder"
    )
    descendant_document_count = graphene.Int(
        description="Number of documents in this folder and all subfolders"
    )
    children = graphene.List(
        lambda: CorpusFolderType, description="Immediate child folders"
    )

    def resolve_path(self, info) -> Any:
        """Get full path from root to this folder."""
        return self.get_path()

    def resolve_document_count(self, info) -> Any:
        """Get count of documents directly in this folder."""
        return self.get_document_count()

    def resolve_descendant_document_count(self, info) -> Any:
        """Get count of documents in this folder and all subfolders."""
        return self.get_descendant_document_count()

    def resolve_children(self, info) -> Any:
        """Get immediate child folders (service-layer visibility)."""
        return BaseService.filter_visible_qs(
            self.children, info.context.user, request=info.context
        )

    class Meta:
        model = CorpusFolder
        interfaces = [relay.Node]
        connection_class = CountableConnection

    @classmethod
    def get_queryset(cls, queryset, info) -> Any:
        """Filter folders to only those the user can see (via corpus permissions)."""
        # Chain ``visible_to_user`` on the incoming queryset/manager so the
        # filter is a single ``WHERE`` expression tree (no ``pk__in``
        # subquery over the full table).
        return BaseService.filter_visible_qs(
            queryset, info.context.user, request=info.context
        )


class CorpusType(AnnotatePermissionsForReadMixin, DjangoObjectType):
    all_annotation_summaries = graphene.List(
        AnnotationType,
        analysis_id=graphene.ID(),
        label_types=graphene.List(LabelTypeEnum),
    )

    # Explicit documents field to use custom resolver via DocumentPath
    # This is necessary because Corpus model no longer has M2M documents field
    # (corpus isolation moved to DocumentPath-based relationships)
    documents = relay.ConnectionField(
        DocumentTypeConnection, description="Documents in this corpus via DocumentPath"
    )

    def resolve_documents(self, info, **kwargs) -> Any:
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
            user, self, include_caml=True, request=info.context
        )

    def resolve_annotations(self, info) -> Any:
        """
        Custom resolver for annotations field that properly computes permissions.
        Uses AnnotationService to ensure permission flags are set.
        """
        from opencontractserver.annotations.models import Annotation
        from opencontractserver.annotations.services import AnnotationService

        user = getattr(info.context, "user", None)

        # Get all document IDs in this corpus via DocumentPath. Corpus READ is
        # already gated by the parent query that resolved ``self`` — see the
        # equivalent note in ``resolve_documents`` above. The internal helper
        # avoids the deprecated user-facing wrapper's runtime warning.
        document_ids = self._get_active_documents().values_list("id", flat=True)

        # Collect annotations for all documents with proper permission computation
        all_annotations = Annotation.objects.none()
        for doc_id in document_ids:
            annotations = AnnotationService.get_document_annotations(
                document_id=doc_id, user=user, corpus_id=self.id
            )
            all_annotations = all_annotations | annotations

        return all_annotations.distinct()

    def resolve_all_annotation_summaries(self, info, **kwargs) -> Any:

        analysis_id = kwargs.get("analysis_id", None)
        label_types = kwargs.get("label_types", None)

        annotation_set = self.annotations.all()

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
                    f"Failed resolving analysis pk for corpus {self.id} with input graphene id"
                    f" {analysis_id}: {e}"
                )

        return annotation_set

    applied_analyzer_ids = graphene.List(graphene.String)

    def resolve_applied_analyzer_ids(self, info) -> Any:
        return list(
            self.analyses.all().values_list("analyzer_id", flat=True).distinct()
        )

    def resolve_icon(self, info) -> Any:
        return "" if not self.icon else info.context.build_absolute_uri(self.icon.url)

    # File link resolver for markdown description
    def resolve_md_description(self, info) -> Any:
        return (
            ""
            if not self.md_description
            else info.context.build_absolute_uri(self.md_description.url)
        )

    # Optional list of description revisions
    description_revisions = graphene.List(lambda: CorpusDescriptionRevisionType)

    def resolve_description_revisions(self, info) -> Any:
        # Returns all revisions, ordered by version asc by default from model ordering
        return (
            self.revisions.select_related("author").all()
            if hasattr(self, "revisions")
            else []
        )

    # Folder structure
    folders = graphene.List(
        CorpusFolderType, description="All folders in this corpus (flat list)"
    )

    def resolve_folders(self, info) -> Any:
        """Get all folders in this corpus with service-layer visibility filtering."""
        return BaseService.filter_visible_qs(
            self.folders, info.context.user, request=info.context
        )

    # Engagement metrics (Epic #565)
    engagement_metrics = graphene.Field(CorpusEngagementMetricsType)

    def resolve_engagement_metrics(self, info) -> Any:
        """
        Resolve engagement metrics for this corpus.

        Returns None if metrics haven't been calculated yet.

        Epic: #565 - Corpus Engagement Metrics & Analytics
        Issue: #568 - Create GraphQL queries for engagement metrics and leaderboards
        """
        try:
            return self.engagement_metrics
        except CorpusEngagementMetrics.DoesNotExist:
            return None

    # Agent memory privacy warning
    memory_active_warning = graphene.String(
        description=(
            "When memory is enabled, returns a privacy notice explaining "
            "that conversation patterns may be stored. Null when disabled."
        ),
    )

    def resolve_memory_active_warning(self, info) -> Any:
        if not self.memory_enabled:
            return None
        return (
            "Agent memory is enabled for this corpus. Generalised patterns "
            "from conversations (not specific content) may be distilled into "
            "the corpus memory document. Review the memory document in your "
            "corpus to see what has been recorded."
        )

    # Categories
    categories = graphene.List(lambda: CorpusCategoryType)

    def resolve_categories(self, info) -> Any:
        """Get all categories assigned to this corpus."""
        return self.categories.all()

    # Efficient document count field - uses annotation from resolver
    document_count = graphene.Int(
        description="Count of active documents in this corpus (optimized)"
    )

    def resolve_document_count(self, info) -> Any:
        """
        Return document count from annotation or fallback to model method.

        For list queries, resolve_corpuses annotates _document_count.
        For single corpus queries, falls back to model.document_count().
        """
        if hasattr(self, "_document_count") and self._document_count is not None:
            return self._document_count
        return self.document_count()

    # Efficient annotation count field - uses annotation from resolver
    annotation_count = graphene.Int(
        description="Count of annotations in this corpus (optimized)"
    )

    def resolve_annotation_count(self, info) -> Any:
        """
        Return annotation count from annotation or fallback to database query.

        For list queries, resolve_corpuses annotates _annotation_count.
        For single corpus queries, falls back to counting via DocumentPath.
        """
        if hasattr(self, "_annotation_count") and self._annotation_count is not None:
            return self._annotation_count
        from opencontractserver.documents.models import DocumentPath

        doc_ids = DocumentPath.objects.filter(
            corpus=self, is_current=True, is_deleted=False
        ).values_list("document_id", flat=True)
        return Annotation.objects.filter(document_id__in=doc_ids).count()

    def resolve_label_set(self, info) -> Any:
        """
        Return label_set with count annotations copied from corpus.

        When resolve_corpuses annotates label counts on the Corpus, we need
        to copy those annotations to the label_set instance so that its
        count resolvers can use them instead of hitting the database.
        """
        if self.label_set is None:
            return None

        # Copy annotated counts to the label_set instance
        if hasattr(self, "_label_doc_count"):
            self.label_set._doc_label_count = self._label_doc_count
        if hasattr(self, "_label_span_count"):
            self.label_set._span_label_count = self._label_span_count
        if hasattr(self, "_label_token_count"):
            self.label_set._token_label_count = self._label_token_count

        return self.label_set

    class Meta:
        model = Corpus
        interfaces = [relay.Node]
        connection_class = CountableConnection

    @classmethod
    def get_queryset(cls, queryset, info) -> Any:
        # Chain ``visible_to_user`` on the incoming queryset/manager so the
        # filter is a single ``WHERE`` expression tree (no ``pk__in``
        # subquery over the full table).
        return BaseService.filter_visible_qs(
            queryset, info.context.user, request=info.context
        )


class CorpusStatsType(graphene.ObjectType):
    total_docs = graphene.Int()
    total_annotations = graphene.Int()
    total_comments = graphene.Int()
    total_analyses = graphene.Int()
    total_extracts = graphene.Int()
    total_threads = graphene.Int()
    total_chats = graphene.Int()
    total_relationships = graphene.Int()


class CorpusFilterCountsType(graphene.ObjectType):
    """Counts of corpuses visible to the user, broken down by tab filter.

    Each count respects guardian permissions (matches BaseService.filter_visible(Corpus, user))
    so tab badges in the corpus list view stay accurate without paginating every
    page on the client.
    """

    all = graphene.Int(required=True)
    mine = graphene.Int(required=True)
    shared = graphene.Int(required=True)
    public = graphene.Int(required=True)


# ---------------- CorpusDescriptionRevisionType ----------------
class CorpusDescriptionRevisionType(AnnotatePermissionsForReadMixin, DjangoObjectType):
    """GraphQL type for corpus description revisions."""

    class Meta:
        model = CorpusDescriptionRevision
        interfaces = [relay.Node]
        connection_class = CountableConnection
