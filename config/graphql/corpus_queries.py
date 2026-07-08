"""
GraphQL query mixin for corpus, category, folder, and stats queries.
"""

import logging
from typing import Any

import graphene
from django.db.models import Count, Q, Subquery
from django.db.models.functions import Coalesce
from graphene_django.filter import DjangoFilterConnectionField
from graphql_relay import from_global_id, to_global_id

from config.graphql.base import OpenContractsNode
from config.graphql.corpus_types import (
    ArtifactTemplateType,
    ArtifactType,
    CorpusDataStoryProfileType,
    CorpusDataStoryType,
    CorpusDocumentGraphEdgeType,
    CorpusDocumentGraphNodeType,
    CorpusDocumentGraphType,
    CorpusIntelligenceAggregatesType,
    CorpusIntelligenceSetupStatusType,
    LabelDistributionEntryType,
)
from config.graphql.filters import CorpusCategoryFilter, CorpusFilter
from config.graphql.graphene_types import (
    CorpusCategoryType,
    CorpusFilterCountsType,
    CorpusFolderType,
    CorpusGroupType,
    CorpusStatsType,
    CorpusType,
    DocumentPathType,
)
from config.graphql.ratelimits import get_user_tier_rate, graphql_ratelimit_dynamic
from opencontractserver.constants.annotations import OC_RESERVED_LABEL_PREFIX
from opencontractserver.constants.document_processing import MARKDOWN_MIME_TYPE
from opencontractserver.constants.stats import (
    CORPUS_DOCUMENT_GRAPH_MAX_NODES,
    CORPUS_INTELLIGENCE_LABEL_DISTRIBUTION_TOP_N,
)
from opencontractserver.corpuses.models import Corpus
from opencontractserver.corpuses.services.corpus_documents import (
    CorpusDocumentService,
)
from opencontractserver.documents.models import Document
from opencontractserver.feedback.models import UserFeedback
from opencontractserver.shared.services.base import BaseService

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


def _artifact_to_type(a: Any) -> "ArtifactType":
    """Build the GraphQL ``ArtifactType`` from an ``Artifact`` model row."""
    return ArtifactType(
        id=to_global_id("ArtifactType", a.id),
        slug=a.slug,
        template=a.template,
        title=a.title or None,
        subtitle=a.subtitle or None,
        byline=a.byline or None,
        config=a.config or {},
        corpus_id=to_global_id("CorpusType", a.corpus_id),
        corpus_slug=a.corpus.slug if a.corpus_id else None,
        creator_slug=getattr(a.creator, "slug", None) if a.creator_id else None,
        image_url=(a.image.url if a.image else None),
        created=a.created,
    )


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
            CorpusDocumentService.with_readme_caml_doc(
                BaseService.filter_visible(
                    Corpus, info.context.user, request=info.context
                )
            )
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
            "Each total respects the same service-layer permission filtering "
            "used by the corpuses connection, so badges stay accurate without "
            "paginating every page on the client."
        ),
    )

    @graphql_ratelimit_dynamic(get_rate=get_user_tier_rate("READ_LIGHT"))
    def resolve_corpus_filter_counts(
        self, info, text_search: str | None = None, **kwargs
    ) -> dict[str, int]:
        user = info.context.user
        visible = BaseService.filter_visible(Corpus, user, request=info.context)
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

    # CORPUS GROUP RESOLVERS (issue #2056) ##########################
    corpus_groups = DjangoFilterConnectionField(
        CorpusGroupType,
        description=(
            "Corpus groups visible to the viewer (creator, public, or "
            "explicitly shared). Member corpora are filtered per-viewer."
        ),
    )

    @graphql_ratelimit_dynamic(get_rate=get_user_tier_rate("READ_LIGHT"))
    def resolve_corpus_groups(self, info, **kwargs) -> Any:
        from opencontractserver.corpuses.services import CorpusGroupService

        return CorpusGroupService.list_visible_groups(
            info.context.user, request=info.context
        )

    corpus_group = OpenContractsNode.Field(CorpusGroupType)

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

        Uses ``BaseService.filter_visible(Corpus, user)`` to ensure guardian
        permissions are respected - users with explicit READ permissions on
        private corpuses will see them in counts.
        """
        from opencontractserver.corpuses.models import Corpus, CorpusCategory

        user = info.context.user

        # Use a subquery instead of materializing all visible corpus IDs
        # into a Python list — keeps filtering in the database.
        visible_corpus_subquery = BaseService.filter_visible(
            Corpus, user, request=info.context
        ).values("id")

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

        Delegates to ``FolderCRUDService.get_visible_folders_with_aggregates``
        so ``path`` / ``documentCount`` / ``descendantDocumentCount`` arrive
        pre-attached on each folder instance. Without this the per-folder
        resolvers in ``CorpusFolderType`` fire a recursive ancestor CTE plus
        a recursive descendant CTE plus two ``COUNT``s per folder, which
        fans out to hundreds of round-trips on a corpus with ~100 folders
        and was the root cause of the 10-20 s folder-browser load.
        """
        from opencontractserver.corpuses.services import FolderCRUDService

        _, corpus_pk = from_global_id(corpus_id)
        return FolderCRUDService.get_visible_folders_with_aggregates(
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
    corpus_intelligence_setup_status = graphene.Field(
        CorpusIntelligenceSetupStatusType,
        corpus_id=graphene.ID(required=True),
        description=(
            "Which pieces of the default collection-intelligence bundle "
            "(reference-web action + description/summary templates) are "
            "already installed on the corpus. Null when the corpus is not "
            "visible to the requesting user."
        ),
    )

    @graphql_ratelimit_dynamic(get_rate=get_user_tier_rate("READ_LIGHT"))
    def resolve_corpus_intelligence_setup_status(self, info, corpus_id) -> Any:
        """Visibility-scoped via ``CorpusIntelligenceSetupService.status``.

        Deliberately NOT ``@login_required``: the setup banner reads this on the
        intelligence overview and the ``insight-panel`` CAML embed, both of which
        anonymous users can reach for a public corpus. There is no privilege
        escalation — ``status`` filters the corpus through ``visible_to_user``
        (returning ``None`` for an invisible corpus) and reports ``can_setup``
        from CRUD, which an anonymous user never has. Anonymous viewers of a
        public corpus therefore see read-only status and no actionable button.
        """
        from opencontractserver.corpuses.services import (
            CorpusIntelligenceSetupService,
        )

        try:
            corpus_pk = int(from_global_id(corpus_id)[1])
        except Exception:
            return None
        result = CorpusIntelligenceSetupService.status(
            info.context.user, corpus_pk, request=info.context
        )
        return result.value if result.ok else None

    corpus_stats = graphene.Field(CorpusStatsType, corpus_id=graphene.ID(required=True))

    @graphql_ratelimit_dynamic(get_rate=get_user_tier_rate("READ_MEDIUM"))
    def resolve_corpus_stats(self, info, corpus_id) -> Any:
        """
        Resolve corpus statistics with proper permission filtering.

        SECURITY: All counts respect the permission model:
        - Documents: Uses BaseService.filter_visible() + DocumentPath filtering
        - Annotations: Filtered by visible documents (inherit doc+corpus permissions)
        - Analyses: Uses AnalysisService (hybrid permission model)
        - Extracts: Uses ExtractService (hybrid permission model)
        - Relationships: Uses DocumentRelationshipService (inherit doc+corpus)
        - Threads/Chats: Uses ConversationService (single visibility query)
        """
        from opencontractserver.analyzer.services import AnalysisService
        from opencontractserver.conversations.services import ConversationService
        from opencontractserver.documents.services import DocumentRelationshipService
        from opencontractserver.extracts.services import ExtractService

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
            # A malformed / empty global id (e.g. the client sent corpusId="")
            # decodes to a non-numeric pk. ``filter(id="")`` would raise
            # "Field 'id' expected a number but got ''" inside this open
            # transaction, aborting it for the rest of the request. Treat a bad
            # id like a not-found / not-visible corpus (empty queryset) and fall
            # through to the zeroed stats below. Note ``isdigit()`` also rejects
            # signed values like "-1", so negative ids are treated as
            # not-found too (no corpus ever has a negative pk).
            if str(corpus_pk).isdigit():
                corpuses = BaseService.filter_visible(
                    Corpus, user, request=info.context
                ).filter(id=int(corpus_pk))
            else:
                corpuses = Corpus.objects.none()

            if corpuses.count() == 1:
                corpus = corpuses[0]

                # Get visible document IDs in this corpus (for filtering annotations)
                # Uses DocumentPath to respect folder structure and versioning
                # Note: path_records is the related_name for Document FK in DocumentPath
                visible_doc_ids = (
                    BaseService.filter_visible(Document, user, request=info.context)
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
                total_analyses = AnalysisService.get_visible_analyses(
                    user, corpus_id=corpus.id, context=info.context
                ).count()

                # total_extracts: Uses hybrid permission model (extract perm + corpus perm)
                total_extracts = ExtractService.get_visible_extracts(
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

    # CORPUS INTELLIGENCE RESOLVERS #####################################
    # Power the "Corpus Intelligence" home: a document-relationship graph and
    # an insight-framed aggregates panel. Both go through the service layer
    # (DocumentRelationshipService / BaseService.filter_visible) so they honor
    # the permission model and the config/graphql Tier-0 invariant (E001).

    corpus_document_graph = graphene.Field(
        CorpusDocumentGraphType,
        corpus_id=graphene.ID(required=True),
        limit=graphene.Int(required=False),
        description=(
            "Document-relationship graph (nodes = documents, edges = "
            "DocumentRelationships) for a corpus, ranked by degree and capped "
            "for the landing-page glimpse."
        ),
    )

    @graphql_ratelimit_dynamic(get_rate=get_user_tier_rate("READ_MEDIUM"))
    def resolve_corpus_document_graph(self, info, corpus_id, limit=None) -> Any:
        # Service imports stay function-local: the ``services`` packages import
        # GraphQL types transitively, so importing them at module load time
        # would create an import cycle. Constants / relay helpers are safe at
        # module level and are hoisted there.
        from opencontractserver.documents.services import DocumentRelationshipService

        user = info.context.user
        corpus_pk = from_global_id(corpus_id)[1]

        empty = CorpusDocumentGraphType(
            nodes=[], edges=[], total_node_count=0, total_edge_count=0, truncated=False
        )

        # Bound the node cap to the configured maximum (defensive against a
        # client requesting an unbounded payload).
        node_cap = CORPUS_DOCUMENT_GRAPH_MAX_NODES
        if limit is not None and 0 < limit < node_cap:
            node_cap = limit

        # A malformed/empty global id decodes to a non-numeric pk; treat it as
        # a not-found corpus (empty graph) rather than aborting the transaction.
        if not str(corpus_pk).isdigit():
            return empty

        corpus = (
            BaseService.filter_visible(Corpus, user, request=info.context)
            .filter(id=int(corpus_pk))
            .first()
        )
        if corpus is None:
            return empty

        # Permission-filtered relationships (both endpoints visible) + degree.
        relationships = DocumentRelationshipService.get_visible_relationships(
            user, corpus_id=corpus.id, request=info.context
        )
        degree_by_doc = DocumentRelationshipService.get_relationship_counts_by_document(
            user, corpus_id=corpus.id, request=info.context
        )

        # Rank documents by degree and keep the top ``node_cap``. A document
        # with no edges never appears here (it isn't in degree_by_doc), which is
        # exactly what we want for a "how docs interact" glimpse.
        ranked_doc_ids = [
            doc_id
            for doc_id, _ in sorted(
                degree_by_doc.items(), key=lambda kv: kv[1], reverse=True
            )
        ]
        total_node_count = len(ranked_doc_ids)
        kept_doc_ids = set(ranked_doc_ids[:node_cap])

        # Count the full edge set with a single COUNT(*), then materialise only
        # the edges among kept documents — the node cap exists to keep the
        # payload small, so the edge fetch must be scoped to it rather than
        # pulling every relationship row into Python and discarding most.
        total_edge_count = relationships.count()
        rel_rows = list(
            relationships.filter(
                source_document_id__in=kept_doc_ids,
                target_document_id__in=kept_doc_ids,
            ).values(
                "id",
                "source_document_id",
                "source_document__title",
                "source_document__file_type",
                "target_document_id",
                "target_document__title",
                "target_document__file_type",
                "relationship_type",
                "annotation_label__text",
            )
        )

        node_meta: dict[int, dict] = {}
        edges = []
        for row in rel_rows:
            src = row["source_document_id"]
            tgt = row["target_document_id"]
            node_meta.setdefault(
                src,
                {
                    "title": row["source_document__title"],
                    "file_type": row["source_document__file_type"],
                },
            )
            node_meta.setdefault(
                tgt,
                {
                    "title": row["target_document__title"],
                    "file_type": row["target_document__file_type"],
                },
            )
            edges.append(
                CorpusDocumentGraphEdgeType(
                    id=str(row["id"]),
                    source=to_global_id("DocumentType", src),
                    target=to_global_id("DocumentType", tgt),
                    label=row["annotation_label__text"],
                    relationship_type=row["relationship_type"],
                )
            )

        # Emit nodes in degree-rank order (the API contract) rather than the
        # incidental edge-traversal order node_meta was built in.
        #
        # ``if doc_id in node_meta`` deliberately drops a top-ranked document
        # whose every edge lands on a partner outside ``kept_doc_ids``: such a
        # document has no *kept* edge, so it would render as an unconnected dot
        # with no line — visual noise that contradicts a "how these documents
        # interconnect" glimpse. It still counts toward ``total_node_count``
        # (so ``truncated`` stays true and the meta line stays honest); the user
        # follows "Explore the full graph" to see it. See the regression test
        # ``test_graph_top_ranked_node_dropped_when_edges_are_capped_out``.
        nodes = [
            CorpusDocumentGraphNodeType(
                id=to_global_id("DocumentType", doc_id),
                title=node_meta[doc_id]["title"],
                file_type=node_meta[doc_id]["file_type"],
                degree=degree_by_doc.get(doc_id, 0),
            )
            for doc_id in ranked_doc_ids
            if doc_id in node_meta
        ]

        truncated = total_node_count > len(nodes) or total_edge_count > len(edges)

        return CorpusDocumentGraphType(
            nodes=nodes,
            edges=edges,
            total_node_count=total_node_count,
            total_edge_count=total_edge_count,
            truncated=truncated,
        )

    corpus_intelligence_aggregates = graphene.Field(
        CorpusIntelligenceAggregatesType,
        corpus_id=graphene.ID(required=True),
        description=(
            "Insight-framed corpus aggregates (label distribution, summary "
            "coverage) for the Corpus Intelligence home."
        ),
    )

    @graphql_ratelimit_dynamic(get_rate=get_user_tier_rate("READ_MEDIUM"))
    def resolve_corpus_intelligence_aggregates(self, info, corpus_id) -> Any:
        # Service import stays function-local to avoid an import cycle (see
        # resolve_corpus_document_graph); the constant is hoisted to module top.
        from opencontractserver.annotations.services import AnnotationService

        user = info.context.user
        corpus_pk = from_global_id(corpus_id)[1]

        empty = CorpusIntelligenceAggregatesType(
            label_distribution=[],
            documents_with_summary=0,
            total_documents=0,
        )

        if not str(corpus_pk).isdigit():
            return empty

        corpus = (
            BaseService.filter_visible(Corpus, user, request=info.context)
            .filter(id=int(corpus_pk))
            .first()
        )
        if corpus is None:
            return empty

        # Visible documents with an active path in this corpus (mirrors
        # resolve_corpus_stats so the numbers agree). Kept as a queryset so the
        # ``__in`` clauses below push a subquery to SQL rather than materialising
        # every id into a Python ``IN (1,2,...,N)`` literal (matters at 1k+ docs).
        visible_docs = BaseService.filter_visible(
            Document, user, request=info.context
        ).filter(
            path_records__corpus=corpus,
            path_records__is_current=True,
            path_records__is_deleted=False,
        )
        visible_doc_ids = visible_docs.values_list("id", flat=True)
        total_documents = visible_doc_ids.count()

        # Summary coverage: visible docs that carry a markdown summary file.
        documents_with_summary = (
            visible_docs.exclude(md_summary_file="")
            .exclude(md_summary_file__isnull=True)
            .count()
        )

        # Label distribution across the corpus's visible annotations, via the
        # service layer (config/graphql code never touches the ORM directly).
        #
        # OC_-prefixed labels are platform scaffolding (OC_SECTION, OC_URL,
        # OC_EXTRACT_SOURCE, …) — pipeline internals that drive built-in
        # features, not human-meaningful tags. Surfacing them in a user-facing
        # "dominant labels" insight reads as jargon and crowds out real labels,
        # so exclude the reserved namespace here. Provider/custom labels (even
        # structural ones a parser emits) are intentionally kept — see
        # ``test_aggregates_structural_label_counted_once_across_shared_docs``.
        label_rows = AnnotationService.get_label_distribution_for_corpus(
            corpus=corpus,
            visible_doc_ids=visible_doc_ids,
            top_n=CORPUS_INTELLIGENCE_LABEL_DISTRIBUTION_TOP_N,
            exclude_label_prefix=OC_RESERVED_LABEL_PREFIX,
            user=info.context.user,
        )
        label_distribution = [
            LabelDistributionEntryType(
                label=row["annotation_label__text"],
                color=row["annotation_label__color"],
                count=row["count"],
            )
            for row in label_rows
        ]

        return CorpusIntelligenceAggregatesType(
            label_distribution=label_distribution,
            documents_with_summary=documents_with_summary,
            total_documents=total_documents,
        )

    # CORPUS DATA STORY RESOLVER ###########################################
    corpus_data_story = graphene.Field(
        CorpusDataStoryType,
        corpus_id=graphene.ID(required=True),
        description=(
            "Per-document structured profiles (type / counterparty / effective "
            "date / value) for the corpus-home data story. Null until the default "
            "Collection Profile extract has run; corpus-as-gate (public corpus → "
            "anonymous-visible)."
        ),
    )

    @graphql_ratelimit_dynamic(get_rate=get_user_tier_rate("READ_MEDIUM"))
    def resolve_corpus_data_story(self, info, corpus_id) -> Any:
        from opencontractserver.corpuses.services.data_story import (
            CorpusDataStoryService,
        )

        corpus_pk = from_global_id(corpus_id)[1]
        if not str(corpus_pk).isdigit():
            return None
        story = CorpusDataStoryService.build(
            info.context.user, int(corpus_pk), request=info.context
        )
        if story is None:
            return None
        return CorpusDataStoryType(
            total_documents=story.total_documents,
            profiles=[
                CorpusDataStoryProfileType(
                    document_id=to_global_id("DocumentType", p.document_id),
                    title=p.title,
                    slug=p.slug,
                    type=p.type,
                    party=p.party,
                    effective_date=p.effective_date,
                    value=p.value,
                )
                for p in story.profiles
            ],
        )

    # CORPUS ARTIFACTS RESOLVERS ###########################################
    artifact_by_slug = graphene.Field(
        ArtifactType,
        slug=graphene.String(required=True),
        description=(
            "A shareable corpus poster by its /a/<slug>. Corpus-as-gate: visible "
            "iff the source corpus is READ-visible (public corpus → anonymous)."
        ),
    )

    @graphql_ratelimit_dynamic(get_rate=get_user_tier_rate("READ_LIGHT"))
    def resolve_artifact_by_slug(self, info, slug) -> Any:
        from opencontractserver.corpuses.services.artifact_service import (
            ArtifactService,
        )

        artifact = ArtifactService.get_by_slug(
            info.context.user, slug, request=info.context
        )
        return _artifact_to_type(artifact) if artifact is not None else None

    corpus_artifacts = graphene.List(
        graphene.NonNull(ArtifactType),
        corpus_id=graphene.ID(required=True),
        description="All shareable artifacts of a corpus (corpus-as-gate).",
    )

    @graphql_ratelimit_dynamic(get_rate=get_user_tier_rate("READ_LIGHT"))
    def resolve_corpus_artifacts(self, info, corpus_id) -> Any:
        from opencontractserver.corpuses.services.artifact_service import (
            ArtifactService,
        )

        pk = from_global_id(corpus_id)[1]
        if not str(pk).isdigit():
            return []
        return [
            _artifact_to_type(a)
            for a in ArtifactService.list_for_corpus(
                info.context.user, int(pk), request=info.context
            )
        ]

    corpus_artifact_templates = graphene.List(
        graphene.NonNull(ArtifactTemplateType),
        corpus_id=graphene.ID(required=True),
        description="Templates this corpus's data can fill (data-gated picker).",
    )

    @graphql_ratelimit_dynamic(get_rate=get_user_tier_rate("READ_LIGHT"))
    def resolve_corpus_artifact_templates(self, info, corpus_id) -> Any:
        from opencontractserver.corpuses.services.artifact_service import (
            ArtifactService,
        )

        pk = from_global_id(corpus_id)[1]
        if not str(pk).isdigit():
            return []
        return [
            ArtifactTemplateType(
                id=t.id,
                label=t.label,
                description=t.description,
                eligible=t.eligible,
                reason=t.reason,
            )
            for t in ArtifactService.templates_for_corpus(
                info.context.user, int(pk), request=info.context
            )
        ]

    # CORPUS METADATA COLUMNS RESOLVERS #####################################
    corpus_metadata_columns = graphene.List(
        "config.graphql.graphene_types.ColumnType",
        corpus_id=graphene.ID(required=True),
        description="Get metadata columns for a corpus",
    )

    def resolve_corpus_metadata_columns(self, info, corpus_id) -> Any:
        """Get metadata columns for a corpus using MetadataService."""
        from opencontractserver.extracts.services import MetadataService

        user = info.context.user
        local_corpus_id = int(from_global_id(corpus_id)[1])

        return MetadataService.get_corpus_metadata_columns(
            user, local_corpus_id, manual_only=True
        )
