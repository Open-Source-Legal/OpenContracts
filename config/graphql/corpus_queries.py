"""
GraphQL query mixin for corpus, category, folder, and stats queries.
"""

import logging
from typing import Any

import graphene
from django.db.models import Count, Q, Subquery
from django.db.models.functions import Coalesce
from graphene_django.filter import DjangoFilterConnectionField
from graphql_relay import from_global_id

from config.graphql.base import OpenContractsNode
from config.graphql.filters import CorpusCategoryFilter, CorpusFilter
from config.graphql.graphene_types import (
    CorpusCategoryType,
    CorpusFilterCountsType,
    CorpusFolderType,
    CorpusStatsType,
    CorpusType,
    DocumentPathType,
)
from config.graphql.ratelimits import get_user_tier_rate, graphql_ratelimit_dynamic
from opencontractserver.constants.document_processing import MARKDOWN_MIME_TYPE
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.feedback.models import UserFeedback

logger = logging.getLogger(__name__)


def _corpus_count_subqueries() -> tuple[Any, Any]:
    """
    Build subqueries for efficient document and annotation counting on Corpus
    querysets. Used by resolve_corpuses and resolve_corpus_by_slugs to annotate
    _document_count and _annotation_count without N+1 queries.
    """
    from django.db.models import Count, OuterRef

    from opencontractserver.annotations.models import Annotation
    from opencontractserver.documents.models import DocumentPath

    document_count_sq = (
        DocumentPath.objects.filter(
            corpus_id=OuterRef("id"),
            is_current=True,
            is_deleted=False,
        )
        .exclude(document__file_type=MARKDOWN_MIME_TYPE)
        .values("corpus_id")
        .annotate(count=Count("document_id", distinct=True))
        .values("count")
    )
    annotation_count_sq = (
        Annotation.objects.filter(
            document__path_records__corpus_id=OuterRef("id"),
            document__path_records__is_current=True,
            document__path_records__is_deleted=False,
        )
        .values("document__path_records__corpus_id")
        .annotate(count=Count("id", distinct=True))
        .values("count")
    )
    return document_count_sq, annotation_count_sq


class CorpusQueryMixin:
    """Query fields and resolvers for corpus, category, folder, and stats queries."""

    # CORPUS RESOLVERS #####################################
    corpuses = DjangoFilterConnectionField(CorpusType, filterset_class=CorpusFilter)

    @graphql_ratelimit_dynamic(get_rate=get_user_tier_rate("READ_LIGHT"))
    def resolve_corpuses(self, info, **kwargs) -> Any:
        from opencontractserver.annotations.models import AnnotationLabel

        doc_sq, annot_sq = _corpus_count_subqueries()

        # Subqueries for label counts (via corpus.label_set_id)
        # Note: 'included_in_labelset' is the related_query_name for filtering
        def label_count_subquery(label_type: str) -> Any:
            from django.db.models import OuterRef

            return (
                AnnotationLabel.objects.filter(
                    included_in_labelset=OuterRef("label_set_id"),
                    label_type=label_type,
                )
                .values("included_in_labelset")
                .annotate(count=Count("id"))
                .values("count")
            )

        return (
            Corpus.objects.visible_to_user(info.context.user)
            .select_related("creator", "engagement_metrics", "label_set", "parent")
            .prefetch_related("categories")
            .annotate(
                _document_count=Coalesce(Subquery(doc_sq), 0),
                _annotation_count=Coalesce(Subquery(annot_sq), 0),
                _label_doc_count=Coalesce(
                    Subquery(label_count_subquery("DOC_TYPE_LABEL")), 0
                ),
                _label_span_count=Coalesce(
                    Subquery(label_count_subquery("SPAN_LABEL")), 0
                ),
                _label_token_count=Coalesce(
                    Subquery(label_count_subquery("TOKEN_LABEL")), 0
                ),
            )
        )

    corpus = OpenContractsNode.Field(CorpusType)  # relay.Node.Field(CorpusType)

    corpus_filter_counts = graphene.Field(
        CorpusFilterCountsType,
        text_search=graphene.String(
            required=False,
            description=(
                "Optional text search to apply alongside the tab counts so badges "
                "match the result set the user actually sees when searching."
            ),
        ),
        description=(
            "Tab-filter totals for the corpus list view (all/mine/shared/public). "
            "Each total respects the same visible_to_user permission filtering "
            "used by the corpuses connection, so badges stay accurate without "
            "paginating every page on the client."
        ),
    )

    @graphql_ratelimit_dynamic(get_rate=get_user_tier_rate("READ_LIGHT"))
    def resolve_corpus_filter_counts(
        self, info, text_search: str | None = None, **kwargs
    ) -> dict[str, int]:
        user = info.context.user
        visible = Corpus.objects.visible_to_user(user)
        if text_search:
            # icontains to mirror CorpusFilter.text_search_method — the tab
            # badge counts must agree with the case-insensitive result set
            # the user actually sees when searching.
            visible = visible.filter(
                Q(description__icontains=text_search) | Q(title__icontains=text_search)
            )

        # Single aggregation produces all four counts in one query plan
        # rather than four separate COUNT(*) round-trips against the same
        # (non-trivial, guardian-filtered) visible queryset.
        is_authed = user is not None and user.is_authenticated
        aggregations: dict[str, Any] = {
            "all": Count("id"),
            "public": Count("id", filter=Q(is_public=True)),
        }
        if is_authed:
            aggregations["mine"] = Count("id", filter=Q(creator=user))
            aggregations["shared"] = Count(
                "id", filter=Q(is_public=False) & ~Q(creator=user)
            )
        counts = visible.aggregate(**aggregations)
        return {
            "all": counts["all"],
            "mine": counts.get("mine", 0),
            "shared": counts.get("shared", 0),
            "public": counts["public"],
        }

    # CORPUS CATEGORY RESOLVERS #####################################
    corpus_categories = DjangoFilterConnectionField(
        CorpusCategoryType,
        filterset_class=CorpusCategoryFilter,
        description="List all corpus categories",
    )

    @graphql_ratelimit_dynamic(get_rate=get_user_tier_rate("READ_LIGHT"))
    def resolve_corpus_categories(self, info, **kwargs) -> Any:
        """
        Get all corpus categories, ordered by sort_order and name.

        Annotates corpus_count to avoid N+1 queries when rendering category lists.
        For anonymous users, counts only public corpuses. For authenticated users,
        counts all corpuses the user can see (public + those with permissions).

        Uses Corpus.objects.visible_to_user() to ensure guardian permissions are
        respected - users with explicit READ permissions on private corpuses will
        see them in counts.
        """
        from opencontractserver.corpuses.models import Corpus, CorpusCategory

        user = info.context.user

        # Use a subquery instead of materializing all visible corpus IDs
        # into a Python list — keeps filtering in the database.
        visible_corpus_subquery = Corpus.objects.visible_to_user(user).values("id")

        # Count corpuses per category, filtering to only visible ones
        categories = CorpusCategory.objects.annotate(
            _corpus_count=Count(
                "corpuses",
                filter=Q(corpuses__id__in=visible_corpus_subquery),
                distinct=True,
            )
        ).order_by("sort_order", "name")

        return categories

    # CORPUS FOLDER RESOLVERS #####################################

    corpus_folders = graphene.List(
        CorpusFolderType,
        corpus_id=graphene.ID(required=True),
        description="Get all folders in a corpus (flat list for tree construction)",
    )

    @graphql_ratelimit_dynamic(get_rate=get_user_tier_rate("READ_LIGHT"))
    def resolve_corpus_folders(self, info, corpus_id) -> Any:
        """
        Get all folders in a corpus.
        Returns flat list - frontend reconstructs tree from parentId relationships.

        Delegates to FolderCRUDService.get_visible_folders() for
        permission checking and query optimization.
        """
        from opencontractserver.corpuses.services import FolderCRUDService

        _, corpus_pk = from_global_id(corpus_id)
        return FolderCRUDService.get_visible_folders(
            user=info.context.user,
            corpus_id=int(corpus_pk),
            request=info.context,
        )

    corpus_folder = graphene.Field(
        CorpusFolderType,
        id=graphene.ID(required=True),
        description="Get a single folder by ID",
    )

    @graphql_ratelimit_dynamic(get_rate=get_user_tier_rate("READ_LIGHT"))
    def resolve_corpus_folder(self, info, id) -> Any:
        """
        Get a single folder by ID with permission check.

        Delegates to FolderCRUDService.get_folder_by_id() for
        permission checking and IDOR protection.
        """
        from opencontractserver.corpuses.services import FolderCRUDService

        _, folder_pk = from_global_id(id)
        return FolderCRUDService.get_folder_by_id(
            user=info.context.user,
            folder_id=int(folder_pk),
            request=info.context,
        )

    deleted_documents_in_corpus = graphene.List(
        DocumentPathType,
        corpus_id=graphene.ID(required=True),
        description="Get all soft-deleted documents in a corpus (trash folder view)",
    )

    @graphql_ratelimit_dynamic(get_rate=get_user_tier_rate("READ_LIGHT"))
    def resolve_deleted_documents_in_corpus(self, info, corpus_id) -> Any:
        """
        Get all soft-deleted documents in a corpus for trash folder view.

        Delegates to DocumentLifecycleService.get_deleted_documents() for
        permission checking and query optimization.
        """
        from opencontractserver.corpuses.services import DocumentLifecycleService

        _, corpus_pk = from_global_id(corpus_id)
        return DocumentLifecycleService.get_deleted_documents(
            user=info.context.user,
            corpus_id=int(corpus_pk),
            request=info.context,
        )

    # CORPUS STATS RESOLVERS #####################################
    corpus_stats = graphene.Field(CorpusStatsType, corpus_id=graphene.ID(required=True))

    @graphql_ratelimit_dynamic(get_rate=get_user_tier_rate("READ_MEDIUM"))
    def resolve_corpus_stats(self, info, corpus_id) -> Any:
        """
        Resolve corpus statistics with proper permission filtering.

        SECURITY: All counts respect the permission model:
        - Documents: Uses visible_to_user() + DocumentPath filtering
        - Annotations: Filtered by visible documents (inherit doc+corpus permissions)
        - Analyses: Uses AnalysisQueryOptimizer (hybrid permission model)
        - Extracts: Uses ExtractQueryOptimizer (hybrid permission model)
        - Relationships: Uses DocumentRelationshipService (inherit doc+corpus)
        - Threads/Chats: Uses ConversationService (single visibility query)
        """
        from opencontractserver.annotations.query_optimizer import (
            AnalysisQueryOptimizer,
            ExtractQueryOptimizer,
        )
        from opencontractserver.conversations.services import ConversationService
        from opencontractserver.documents.services import DocumentRelationshipService

        total_docs = 0
        total_annotations = 0
        total_comments = 0
        total_analyses = 0
        total_extracts = 0
        total_threads = 0
        total_chats = 0
        total_relationships = 0

        user = info.context.user
        corpus_pk = from_global_id(corpus_id)[1]

        try:
            corpuses = Corpus.objects.visible_to_user(user).filter(id=corpus_pk)

            if corpuses.count() == 1:
                corpus = corpuses[0]

                # Get visible document IDs in this corpus (for filtering annotations)
                # Uses DocumentPath to respect folder structure and versioning
                # Note: path_records is the related_name for Document FK in DocumentPath
                visible_doc_ids = (
                    Document.objects.visible_to_user(user)
                    .filter(
                        path_records__corpus=corpus,
                        path_records__is_current=True,
                        path_records__is_deleted=False,
                    )
                    .values_list("id", flat=True)
                )

                # total_docs: Count of visible documents with active paths in corpus
                total_docs = visible_doc_ids.count()

                # total_annotations: Annotations inherit permissions from document + corpus
                # Since user has corpus permission, filter by visible documents
                # Include both document-attached and structural annotations
                # Note: structural_set.documents is the reverse FK from Document to StructuralAnnotationSet
                total_annotations = corpus.annotations.filter(
                    Q(document_id__in=visible_doc_ids)
                    | Q(
                        structural_set__documents__in=visible_doc_ids,
                        structural=True,
                    )
                ).count()

                # total_comments: Comments on visible annotations
                total_comments = UserFeedback.objects.filter(
                    commented_annotation__corpus=corpus,
                    commented_annotation__document_id__in=visible_doc_ids,
                ).count()

                # total_analyses: Uses hybrid permission model (analysis perm + corpus perm)
                total_analyses = AnalysisQueryOptimizer.get_visible_analyses(
                    user, corpus_id=corpus.id, context=info.context
                ).count()

                # total_extracts: Uses hybrid permission model (extract perm + corpus perm)
                total_extracts = ExtractQueryOptimizer.get_visible_extracts(
                    user, corpus_id=corpus.id, context=info.context
                ).count()

                # total_threads and total_chats: Use ConversationService
                # to execute visibility subqueries once instead of twice
                total_threads, total_chats = (
                    ConversationService.get_corpus_conversation_counts(
                        user, corpus.id, request=info.context
                    )
                )

                # total_relationships: Uses DocumentRelationshipService
                # Relationships inherit from source_doc + target_doc + corpus
                total_relationships = (
                    DocumentRelationshipService.get_visible_relationships(
                        user, corpus_id=corpus.id, request=info.context
                    ).count()
                )
        except Exception as e:
            logger.error(f"Error in resolve_corpus_stats: {e}", exc_info=True)
            raise

        return CorpusStatsType(
            total_docs=total_docs,
            total_annotations=total_annotations,
            total_comments=total_comments,
            total_analyses=total_analyses,
            total_extracts=total_extracts,
            total_threads=total_threads,
            total_chats=total_chats,
            total_relationships=total_relationships,
        )

    # CORPUS METADATA COLUMNS RESOLVERS #####################################
    corpus_metadata_columns = graphene.List(
        "config.graphql.graphene_types.ColumnType",
        corpus_id=graphene.ID(required=True),
        description="Get metadata columns for a corpus",
    )

    def resolve_corpus_metadata_columns(self, info, corpus_id) -> Any:
        """Get metadata columns for a corpus using MetadataQueryOptimizer."""
        from opencontractserver.extracts.query_optimizer import MetadataQueryOptimizer

        user = info.context.user
        local_corpus_id = int(from_global_id(corpus_id)[1])

        return MetadataQueryOptimizer.get_corpus_metadata_columns(
            user, local_corpus_id, manual_only=True
        )
