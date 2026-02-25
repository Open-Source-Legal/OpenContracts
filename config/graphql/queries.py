import inspect
import logging
import re
from typing import Optional

import graphene
from django.conf import settings
from django.db.models import Count, OuterRef, Prefetch, Q, Subquery
from django.db.models.functions import Coalesce
from graphene import relay
from graphene.types.generic import GenericScalar
from graphene_django.debug import DjangoDebug
from graphene_django.fields import DjangoConnectionField
from graphene_django.filter import DjangoFilterConnectionField
from graphql import GraphQLError
from graphql_jwt.decorators import login_required
from graphql_relay import from_global_id

from config.graphql.base import OpenContractsNode
from config.graphql.filters import (
    AgentConfigurationFilter,
    AnalysisFilter,
    AnalyzerFilter,
    AssignmentFilter,
    BadgeFilter,
    ColumnFilter,
    ConversationFilter,
    CorpusCategoryFilter,
    CorpusFilter,
    DatacellFilter,
    DocumentFilter,
    DocumentRelationshipFilter,
    ExportFilter,
    ExtractFilter,
    FieldsetFilter,
    GremlinEngineFilter,
    LabelFilter,
    LabelsetFilter,
    ModerationActionFilter,
    RelationshipFilter,
    UserBadgeFilter,
)
from config.graphql.graphene_types import (
    AgentActionResultType,
    AgentConfigurationType,
    AnalysisType,
    AnalyzerType,
    AnnotationLabelType,
    AnnotationType,
    AssignmentType,
    AvailableToolType,
    BadgeDistributionType,
    BadgeType,
    BulkDocumentUploadStatusType,
    ColumnType,
    CommunityStatsType,
    ComponentSettingSchemaType,
    ConversationType,
    CorpusActionExecutionType,
    CorpusActionTrailStatsType,
    CorpusActionType,
    CorpusCategoryType,
    CorpusFolderType,
    CorpusStatsType,
    CorpusType,
    CriteriaTypeDefinitionType,
    DatacellType,
    DocumentCorpusActionsType,
    DocumentPathType,
    DocumentRelationshipType,
    DocumentType,
    ExtractType,
    FieldsetType,
    FileTypeEnum,
    GremlinEngineType_READ,
    LabelSetType,
    LeaderboardEntryType,
    LeaderboardMetricEnum,
    LeaderboardScopeEnum,
    LeaderboardType,
    MessageType,
    ModerationActionType,
    ModerationMetricsType,
    NoteType,
    NotificationType,
    PageAwareAnnotationType,
    PdfPageInfoType,
    PipelineComponentsType,
    PipelineComponentType,
    RelationshipType,
    SemanticSearchResultType,
    UserBadgeType,
    UserExportType,
    UserImportType,
    UserType,
)
from config.graphql.og_metadata_types import (
    OGCorpusMetadataType,
    OGDocumentMetadataType,
    OGExtractMetadataType,
    OGThreadMetadataType,
)
from config.graphql.ratelimits import (
    get_user_tier_rate,
    graphql_ratelimit,
    graphql_ratelimit_dynamic,
)
from config.graphql.worker_mutations import (
    CorpusAccessTokenType,
    WorkerAccountType,
    WorkerDocumentUploadType,
)
from opencontractserver.analyzer.models import Analyzer, GremlinEngine
from opencontractserver.annotations.models import (
    Annotation,
    AnnotationLabel,
    LabelSet,
    Note,
    Relationship,
)
from opencontractserver.badges.criteria_registry import BadgeCriteriaRegistry
from opencontractserver.badges.models import Badge, UserBadge
from opencontractserver.conversations.models import (
    ChatMessage,
    Conversation,
    MessageTypeChoices,
    ModerationAction,
)
from opencontractserver.corpuses.models import (
    Corpus,
    CorpusAction,
)
from opencontractserver.documents.models import Document, DocumentRelationship
from opencontractserver.documents.query_optimizer import (
    DocumentRelationshipQueryOptimizer,
)
from opencontractserver.extracts.models import Column, Datacell, Fieldset
from opencontractserver.feedback.models import UserFeedback
from opencontractserver.notifications.models import Notification
from opencontractserver.types.enums import LabelType
from opencontractserver.users.models import Assignment, UserExport, UserImport
from opencontractserver.worker_uploads.models import (
    CorpusAccessToken,
    WorkerAccount,
    WorkerDocumentUpload,
)

logger = logging.getLogger(__name__)


def _corpus_count_subqueries():
    """
    Build subqueries for efficient document and annotation counting on Corpus
    querysets. Used by resolve_corpuses and resolve_corpus_by_slugs to annotate
    _document_count and _annotation_count without N+1 queries.
    """
    from opencontractserver.documents.models import DocumentPath

    document_count_sq = (
        DocumentPath.objects.filter(
            corpus_id=OuterRef("id"),
            is_current=True,
            is_deleted=False,
        )
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


class MetadataCompletionStatusType(graphene.ObjectType):
    """Type for metadata completion status information."""

    total_fields = graphene.Int()
    filled_fields = graphene.Int()
    missing_fields = graphene.Int()
    percentage = graphene.Float()
    missing_required = graphene.List(graphene.String)


class DocumentMetadataResultType(graphene.ObjectType):
    """Type for batch metadata query results - groups datacells by document."""

    document_id = graphene.ID(description="The document's global ID")
    datacells = graphene.List(
        DatacellType, description="Metadata datacells for this document"
    )


class Query(graphene.ObjectType):

    # USER RESOLVERS #####################################
    me = graphene.Field(UserType)
    # Slug-based resolvers
    user_by_slug = graphene.Field(UserType, slug=graphene.String(required=True))
    corpus_by_slugs = graphene.Field(
        CorpusType,
        user_slug=graphene.String(required=True),
        corpus_slug=graphene.String(required=True),
    )
    document_by_slugs = graphene.Field(
        DocumentType,
        user_slug=graphene.String(required=True),
        document_slug=graphene.String(required=True),
    )
    document_in_corpus_by_slugs = graphene.Field(
        DocumentType,
        user_slug=graphene.String(required=True),
        corpus_slug=graphene.String(required=True),
        document_slug=graphene.String(required=True),
    )

    def resolve_me(self, info):
        return info.context.user

    def resolve_user_by_slug(self, info, slug):
        """
        Resolve a user by their slug with profile privacy filtering.

        SECURITY: Respects is_profile_public and corpus membership visibility rules.
        Users are visible if:
        - Profile is public (is_profile_public=True)
        - Requesting user shares corpus membership with > READ permission
        - It's the requesting user's own profile
        """
        from django.contrib.auth import get_user_model

        from opencontractserver.users.query_optimizer import UserQueryOptimizer

        User = get_user_model()
        try:
            # Use visibility filtering instead of direct query
            return UserQueryOptimizer.get_visible_users(info.context.user).get(
                slug=slug
            )
        except User.DoesNotExist:
            return None

    def resolve_corpus_by_slugs(self, info, user_slug, corpus_slug):
        from django.contrib.auth import get_user_model

        User = get_user_model()
        try:
            owner = User.objects.get(slug=user_slug)
        except User.DoesNotExist:
            return None
        qs = Corpus.objects.filter(creator=owner, slug=corpus_slug)
        qs = qs.visible_to_user(info.context.user)

        # Add count annotations for efficient documentCount/annotationCount
        # resolution without N+1 queries. Coalesce ensures 0 instead of NULL.
        doc_sq, annot_sq = _corpus_count_subqueries()
        qs = qs.annotate(
            _document_count=Coalesce(Subquery(doc_sq), 0),
            _annotation_count=Coalesce(Subquery(annot_sq), 0),
        )

        return qs.first()

    def resolve_document_by_slugs(self, info, user_slug, document_slug):
        from django.contrib.auth import get_user_model

        User = get_user_model()
        try:
            owner = User.objects.get(slug=user_slug)
        except User.DoesNotExist:
            return None
        qs = Document.objects.filter(creator=owner, slug=document_slug)
        qs = qs.visible_to_user(info.context.user)
        return qs.first()

    def resolve_document_in_corpus_by_slugs(
        self, info, user_slug, corpus_slug, document_slug
    ):
        from django.contrib.auth import get_user_model

        from opencontractserver.documents.models import DocumentPath

        User = get_user_model()
        try:
            owner = User.objects.get(slug=user_slug)
        except User.DoesNotExist:
            return None
        corpus = (
            Corpus.objects.filter(creator=owner, slug=corpus_slug)
            .visible_to_user(info.context.user)
            .first()
        )
        if not corpus:
            return None
        doc = (
            Document.objects.filter(creator=owner, slug=document_slug)
            .visible_to_user(info.context.user)
            .first()
        )
        if not doc:
            return None
        # Validate membership via DocumentPath (dual-tree versioning model)
        if not DocumentPath.objects.filter(
            document=doc, corpus=corpus, is_current=True, is_deleted=False
        ).exists():
            return None
        return doc

    # ANNOTATION RESOLVERS #####################################
    annotations = DjangoConnectionField(
        AnnotationType,
        raw_text_contains=graphene.String(),
        annotation_label_id=graphene.ID(),
        annotation_label__text=graphene.String(),
        annotation_label__text_contains=graphene.String(),
        annotation_label__description_contains=graphene.String(),
        annotation_label__label_type=graphene.String(),
        analysis_isnull=graphene.Boolean(),
        document_id=graphene.ID(),
        corpus_id=graphene.ID(),
        structural=graphene.Boolean(),
        uses_label_from_labelset_id=graphene.ID(),
        created_by_analysis_ids=graphene.String(),
        created_with_analyzer_id=graphene.String(),
        order_by=graphene.String(),
    )

    @graphql_ratelimit_dynamic(get_rate=get_user_tier_rate("READ_MEDIUM"))
    def resolve_annotations(
        self, info, analysis_isnull=None, structural=None, **kwargs
    ):
        # Import the query optimizer
        from opencontractserver.annotations.query_optimizer import (
            AnnotationQueryOptimizer,
        )

        document_id = kwargs.get("document_id")
        corpus_id = kwargs.get("corpus_id")

        if document_id:
            # Use document-specific query optimizer
            doc_django_pk = int(from_global_id(document_id)[1])
            corpus_django_pk = int(from_global_id(corpus_id)[1]) if corpus_id else None

            # Use query optimizer which handles permissions properly
            queryset = AnnotationQueryOptimizer.get_document_annotations(
                document_id=doc_django_pk,
                user=info.context.user,
                corpus_id=corpus_django_pk,
                analysis_id=None,  # Will be handled below if needed
                extract_id=None,
                use_cache=False,
            )

        elif corpus_id:
            # Use corpus-wide query optimizer (handles structural annotations correctly)
            # This optimizer already applies structural, analysis_isnull, and corpus filters
            corpus_django_pk = int(from_global_id(corpus_id)[1])
            queryset = AnnotationQueryOptimizer.get_corpus_annotations(
                corpus_id=corpus_django_pk,
                user=info.context.user,
                structural=structural,
                analysis_isnull=analysis_isnull,
            )
            # Mark filters already applied by optimizer to prevent double-filtering
            corpus_id = None
            structural = None
            analysis_isnull = None

        else:
            # Fallback to visible_to_user for queries without document or corpus
            queryset = Annotation.objects.visible_to_user(info.context.user)
            logger.info(
                f"Using visible_to_user for annotations query, found {queryset.count()} annotations"
            )

        queryset = queryset.select_related(
            "annotation_label",
            "creator",
            "document",
            "corpus",
            "analysis",
            "analysis__analyzer",
        )

        # Filter by uses_label_from_labelset_id
        labelset_id = kwargs.get("uses_label_from_labelset_id")
        if labelset_id:
            logger.info(f"Filtering by labelset_id: {labelset_id}")
            django_pk = from_global_id(labelset_id)[1]
            queryset = queryset.filter(annotation_label__included_in_labelset=django_pk)

        # Filter by created_by_analysis_ids
        analysis_ids = kwargs.get("created_by_analysis_ids")
        if analysis_ids:
            logger.info(f"Filtering by analysis_ids: {analysis_ids}")
            analysis_id_list = analysis_ids.split(",")
            if "~~MANUAL~~" in analysis_id_list:
                logger.info("Including manual annotations in filter")
                analysis_id_list = [id for id in analysis_id_list if id != "~~MANUAL~~"]
                analysis_pks = [
                    int(from_global_id(value)[1]) for value in analysis_id_list
                ]
                queryset = queryset.filter(
                    Q(analysis__isnull=True) | Q(analysis_id__in=analysis_pks)
                )
            else:
                logger.info("Filtering only by specified analysis IDs")
                analysis_pks = [
                    int(from_global_id(value)[1]) for value in analysis_id_list
                ]
                queryset = queryset.filter(analysis_id__in=analysis_pks)

        # Filter by created_with_analyzer_id
        analyzer_ids = kwargs.get("created_with_analyzer_id")
        if analyzer_ids:
            logger.info(f"Filtering by analyzer_ids: {analyzer_ids}")
            analyzer_id_list = analyzer_ids.split(",")
            if "~~MANUAL~~" in analyzer_id_list:
                logger.info("Including manual annotations in filter")
                analyzer_id_list = [id for id in analyzer_id_list if id != "~~MANUAL~~"]
                analyzer_pks = [
                    int(from_global_id(id)[1])
                    for id in analyzer_id_list
                    if id != "~~MANUAL~~"
                ]
                queryset = queryset.filter(
                    Q(analysis__isnull=True) | Q(analysis__analyzer_id__in=analyzer_pks)
                )
            elif len(analyzer_id_list) > 0:
                logger.info("Filtering only by specified analyzer IDs")
                analyzer_pks = [int(from_global_id(id)[1]) for id in analyzer_id_list]
                queryset = queryset.filter(analysis__analyzer_id__in=analyzer_pks)

        # Filter by raw_text
        raw_text = kwargs.get("raw_text_contains")
        if raw_text:
            logger.info(f"Filtering by raw_text containing: {raw_text}")
            queryset = queryset.filter(raw_text__contains=raw_text)

        # Filter by annotation_label_id
        annotation_label_id = kwargs.get("annotation_label_id")
        if annotation_label_id:
            logger.info(f"Filtering by annotation_label_id: {annotation_label_id}")
            django_pk = from_global_id(annotation_label_id)[1]
            queryset = queryset.filter(annotation_label_id=django_pk)

        # Filter by annotation_label__text
        label_text = kwargs.get("annotation_label__text")
        if label_text:
            logger.info(f"Filtering by exact annotation_label__text: {label_text}")
            queryset = queryset.filter(annotation_label__text=label_text)

        label_text_contains = kwargs.get("annotation_label__text_contains")
        if label_text_contains:
            logger.info(
                f"Filtering by annotation_label__text containing: {label_text_contains}"
            )
            queryset = queryset.filter(
                annotation_label__text__contains=label_text_contains
            )

        # Filter by annotation_label__description
        label_description = kwargs.get("annotation_label__description_contains")
        if label_description:
            logger.info(
                f"Filtering by annotation_label__description containing: {label_description}"
            )
            queryset = queryset.filter(
                annotation_label__description__contains=label_description
            )

        # Filter by annotation_label__label_type
        logger.info(
            f"Queryset count before filtering by annotation_label__label_type: {queryset.count()}"
        )
        label_type = kwargs.get("annotation_label__label_type")
        if label_type:
            logger.info(f"Filtering by annotation_label__label_type: {label_type}")
            queryset = queryset.filter(annotation_label__label_type=label_type)
        logger.info(f"Queryset count after filtering by label type: {queryset.count()}")

        logger.info(f"Q Filter value for analysis_isnull: {analysis_isnull}")
        # Filter by analysis
        if analysis_isnull is not None:
            logger.info(
                f"QS count before filtering by analysis is null: {queryset.count()}"
            )
            queryset = queryset.filter(analysis__isnull=analysis_isnull)
            logger.info(f"Filtered by analysis_isnull: {queryset.count()}")

        # Skip document_id and corpus_id filtering if already handled by optimizer
        if not document_id:
            # Filter by document_id
            document_id = kwargs.get("document_id")
            if document_id:
                logger.info(f"Filtering by document_id: {document_id}")
                django_pk = from_global_id(document_id)[1]
                queryset = queryset.filter(document_id=django_pk)

            # Filter by corpus_id
            logger.info(f"{queryset.count()} annotations pre corpus_id filter...")
            corpus_id = kwargs.get("corpus_id")
            if corpus_id:
                django_pk = from_global_id(corpus_id)[1]
                logger.info(f"Filtering by corpus_id: {django_pk}")
                queryset = queryset.filter(corpus_id=django_pk)
                logger.info(f"{queryset.count()} annotations post corpus_id filter...")

        # Filter by structural
        if structural is not None:
            logger.info(f"Filtering by structural: {structural}")
            queryset = queryset.filter(structural=structural)

        # Ordering
        order_by = kwargs.get("order_by")
        if order_by:
            logger.info(f"Ordering by: {order_by}")
            queryset = queryset.order_by(order_by)
        else:
            logger.info("Ordering by default: -modified")
            queryset = queryset.order_by("-modified")

        return queryset

    label_type_enum = graphene.Enum.from_enum(LabelType)

    #############################################################################################
    # For some annotations, it's not clear exactly how to paginate them and, mostllikely        #
    # the total # of such annotations will be pretty minimal (specifically relationships and    #
    # doc types). The bulk_doc_annotations_in_corpus field allows you to request                #
    # full complement of annotations for a given doc in a given corpus as a list                #
    # rather than a Relay-style connection.                                                     #
    #############################################################################################

    bulk_doc_relationships_in_corpus = graphene.Field(
        graphene.List(RelationshipType),
        corpus_id=graphene.ID(required=True),
        document_id=graphene.ID(required=True),
    )

    def resolve_bulk_doc_relationships_in_corpus(self, info, corpus_id, document_id):
        # Get the base queryset using visible_to_user
        queryset = Relationship.objects.visible_to_user(info.context.user)

        doc_django_pk = from_global_id(document_id)[1]
        corpus_django_pk = from_global_id(corpus_id)[1]

        queryset = queryset.filter(
            corpus_id=corpus_django_pk, document_id=doc_django_pk
        )  # Existing filter
        queryset = queryset.select_related(
            "relationship_label",
            "corpus",
            "document",
            "creator",
            "analyzer",  # If needed
            "analysis",  # If needed
        ).prefetch_related(
            "source_annotations",  # If RelationshipType shows source annotations
            "target_annotations",  # If RelationshipType shows target annotations
        )
        return queryset

    bulk_doc_annotations_in_corpus = graphene.Field(
        graphene.List(AnnotationType),
        corpus_id=graphene.ID(required=True),
        document_id=graphene.ID(required=False),
        for_analysis_ids=graphene.String(required=False),
        label_type=graphene.Argument(label_type_enum),
    )

    def resolve_bulk_doc_annotations_in_corpus(self, info, corpus_id, **kwargs):

        corpus_django_pk = from_global_id(corpus_id)[1]

        # Get the base queryset using visible_to_user
        queryset = Annotation.objects.visible_to_user(info.context.user).order_by(
            "page"
        )

        # Now build query to stuff they want to see (filter to annotations in this corpus or with NO corpus FK, which
        # travel with document.
        q_objects = Q(corpus_id=corpus_django_pk) | Q(corpus_id__isnull=True)

        # If for_analysis_ids is passed in, only show annotations from those analyses, otherwise only show human
        # annotations.
        for_analysis_ids = kwargs.get("for_analysis_ids", None)
        if for_analysis_ids is not None and len(for_analysis_ids) > 0:
            logger.info(
                f"resolve_bulk_doc_annotations - Split ids: {for_analysis_ids.split(',')}"
            )
            analysis_pks = [
                int(from_global_id(value)[1])
                for value in list(
                    filter(lambda raw_id: len(raw_id) > 0, for_analysis_ids.split(","))
                )
            ]
            logger.info(f"resolve_bulk_doc_annotations - Analysis pks: {analysis_pks}")
            q_objects.add(Q(analysis_id__in=analysis_pks), Q.AND)
        # else:
        #     q_objects.add(Q(analysis__isnull=True), Q.AND)

        label_type = kwargs.get("label_type", None)
        if label_type is not None:
            q_objects.add(Q(annotation_label__label_type=label_type), Q.AND)

        document_id = kwargs.get("document_id", None)
        if document_id is not None:
            doc_pk = from_global_id(document_id)[1]
            q_objects.add(Q(document_id=doc_pk), Q.AND)

        logger.info(f"Filter queryset {queryset} bulk annotations: {q_objects}")

        final_queryset = queryset.filter(q_objects).order_by(
            "created", "page"
        )  # Existing filter/order
        final_queryset = final_queryset.select_related(
            "annotation_label",
            "creator",
            "document",
            "corpus",
            "analysis",
            "analysis__analyzer",
            # 'embeddings' # If needed
        )
        return final_queryset

    page_annotations = graphene.Field(
        PageAwareAnnotationType,
        current_page=graphene.Int(required=False),
        page_number_list=graphene.String(required=False),
        page_containing_annotation_with_id=graphene.ID(required=False),
        corpus_id=graphene.ID(required=False),
        document_id=graphene.ID(required=True),
        for_analysis_ids=graphene.String(required=False),
        label_type=graphene.Argument(label_type_enum),
    )

    @graphql_ratelimit_dynamic(get_rate=get_user_tier_rate("READ_MEDIUM"))
    def resolve_page_annotations(self, info, document_id, corpus_id=None, **kwargs):

        doc_django_pk = from_global_id(document_id)[1]

        # Fetch the document (consider select_related if creator/etc. are used elsewhere)
        # Using get_object_or_404 for better error handling if document not found/accessible
        # For simplicity, assuming simple get for now based on original code.
        try:
            # Add select_related if document creator/etc. needed later
            document = Document.objects.get(id=doc_django_pk)
        except Document.DoesNotExist:
            # Handle error appropriately, maybe return null or raise GraphQL error
            logger.error(f"Document with pk {doc_django_pk} not found.")
            return None  # Or raise appropriate GraphQL error

        # Get the base queryset using visible_to_user
        queryset = Annotation.objects.visible_to_user(info.context.user)

        # Apply select_related EARLY to the base queryset
        queryset = queryset.select_related(
            "annotation_label",
            "creator",
            "document",  # Document already fetched, but good practice if base queryset reused
            "corpus",
            "analysis",
            "analysis__analyzer",
        )

        # Now build query filters
        q_objects = Q(document_id=doc_django_pk)
        if corpus_id is not None:
            corpus_pk = from_global_id(corpus_id)[
                1
            ]  # Get corpus_pk only if corpus_id is present
            q_objects.add(Q(corpus_id=corpus_pk), Q.AND)

        # If for_analysis_ids is passed in, only show annotations from those analyses
        for_analysis_ids = kwargs.get("for_analysis_ids", None)
        if for_analysis_ids is not None:
            analysis_pks = [
                int(from_global_id(value)[1])
                for value in list(
                    filter(lambda raw_id: len(raw_id) > 0, for_analysis_ids.split(","))
                )
            ]
            if analysis_pks:  # Only add filter if there are valid PKs
                logger.info(
                    f"resolve_page_annotations - Filtering by Analysis pks: {analysis_pks}"
                )
                q_objects.add(Q(analysis_id__in=analysis_pks), Q.AND)
            else:
                # Handle case maybe? Or assume UI prevents empty string if filter applied
                logger.warning(
                    "resolve_page_annotations - for_analysis_ids provided but resulted in empty PK list."
                )
        else:
            logger.info(
                "resolve_page_annotations - for_analysis_ids is None, filtering for analysis__isnull=True"
            )
            q_objects.add(Q(analysis__isnull=True), Q.AND)

        label_type = kwargs.get("label_type", None)
        if label_type is not None:
            logger.info(
                f"resolve_page_annotations - Filtering by label_type: {label_type}"
            )
            q_objects.add(Q(annotation_label__label_type=label_type), Q.AND)

        # Apply filters to the optimized base queryset
        # Order by page first for potential pagination logic, then created
        all_pages_annotations = queryset.filter(q_objects).order_by("page", "created")

        # --- Determine the current page ---
        page_containing_annotation_with_id = kwargs.get(
            "page_containing_annotation_with_id", None
        )
        page_number_list = kwargs.get("page_number_list", None)
        current_page = 1  # Default to page 1 (1-indexed)

        if kwargs.get("current_page", None) is not None:
            current_page = kwargs.get("current_page")
            logger.info(
                f"resolve_page_annotations - Using provided current_page: {current_page}"
            )
        elif page_number_list is not None:
            if re.search(r"^(?:\d+,)*\d+$", page_number_list):  # Validate format better
                pages = [int(page) for page in page_number_list.split(",")]
                current_page = (
                    pages[-1] if pages else 1
                )  # Use last page in list, default 1 if empty
                logger.info(
                    f"resolve_page_annotations - Using last page from page_number_list: {current_page}"
                )
            else:
                # Handle invalid format - maybe raise error or log warning and default
                logger.warning(
                    f"Invalid format for page_number_list: {page_number_list}"
                )
                # Keep default current_page = 1
        elif page_containing_annotation_with_id:
            try:
                annotation_pk = int(
                    from_global_id(page_containing_annotation_with_id)[1]
                )
                # Optimized fetch for just the page number
                annotation_page_zero_indexed = (
                    Annotation.objects.filter(pk=annotation_pk)
                    .values_list("page", flat=True)
                    .first()
                )  # Use first() to avoid DoesNotExist

                if annotation_page_zero_indexed is not None:
                    current_page = (
                        annotation_page_zero_indexed + 1
                    )  # Convert 0-indexed DB value to 1-indexed page number
                    logger.info(
                        f"resolve_page_annotations - Found page {current_page} for annotation pk {annotation_pk}"
                    )
                else:
                    logger.warning(
                        f"resolve_page_annotations - Annotation pk {annotation_pk} not found for page lookup."
                    )
                    # Keep default current_page = 1
            except (ValueError, TypeError) as e:
                logger.error(
                    f"Error parsing annotation ID {page_containing_annotation_with_id}: {e}"
                )
                # Keep default current_page = 1

        # Convert 1-indexed current page to 0-indexed for DB filtering
        current_page_zero_indexed = max(0, current_page - 1)  # Ensure it's not negative

        # --- Filter annotations for the specific page(s) ---
        if page_number_list is not None and re.search(
            r"^(?:\d+,)*\d+$", page_number_list
        ):
            # Use validated page list from earlier
            pages_zero_indexed = [max(0, page - 1) for page in pages]
            page_annotations = all_pages_annotations.filter(
                page__in=pages_zero_indexed
            )  # Order already applied
        else:
            page_annotations = all_pages_annotations.filter(
                page=current_page_zero_indexed
            )  # Order already applied

        logger.info(
            f"resolve_page_annotations - final page annotations count: {page_annotations.count()}"
        )  # Use .count() carefully if queryset is large

        pdf_page_info = PdfPageInfoType(
            page_count=document.page_count,
            current_page=current_page_zero_indexed,  # Return 0-indexed as per original logic
            has_next_page=current_page_zero_indexed < document.page_count - 1,
            has_previous_page=current_page_zero_indexed > 0,
            corpus_id=corpus_id,
            document_id=document_id,
            for_analysis_ids=for_analysis_ids,
            label_type=label_type,
        )

        return PageAwareAnnotationType(
            page_annotations=page_annotations, pdf_page_info=pdf_page_info
        )

    annotation = relay.Node.Field(AnnotationType)

    def resolve_annotation(self, info, **kwargs):
        django_pk = from_global_id(kwargs.get("id", None))[1]
        queryset = Annotation.objects.visible_to_user(info.context.user)
        queryset = queryset.select_related(
            "annotation_label",
            "creator",
            "document",
            "corpus",
            "analysis",
            "analysis__analyzer",  # 'embeddings'
        )
        return queryset.get(id=django_pk)

    # RELATIONSHIP RESOLVERS #####################################
    relationships = DjangoFilterConnectionField(
        RelationshipType, filterset_class=RelationshipFilter
    )

    def resolve_relationships(self, info, **kwargs):
        queryset = Relationship.objects.visible_to_user(info.context.user)
        queryset = queryset.select_related(
            "relationship_label",
            "corpus",
            "document",
            "creator",
            "analyzer",
            "analysis",
        ).prefetch_related("source_annotations", "target_annotations")
        return queryset

    relationship = relay.Node.Field(RelationshipType)

    def resolve_relationship(self, info, **kwargs):
        django_pk = from_global_id(kwargs.get("id", None))[1]
        queryset = Relationship.objects.visible_to_user(info.context.user)
        queryset = queryset.select_related(
            "relationship_label",
            "corpus",
            "document",
            "creator",
            "analyzer",
            "analysis",
        ).prefetch_related(  # Prefetch might be overkill for a single object, but harmless
            "source_annotations", "target_annotations"
        )
        return queryset.get(id=django_pk)

    # LABEL RESOLVERS #####################################

    annotation_labels = DjangoFilterConnectionField(
        AnnotationLabelType, filterset_class=LabelFilter
    )

    def resolve_annotation_labels(self, info, **kwargs):
        return AnnotationLabel.objects.visible_to_user(info.context.user)

    annotation_label = relay.Node.Field(AnnotationLabelType)

    def resolve_annotation_label(self, info, **kwargs):
        django_pk = from_global_id(kwargs.get("id", None))[1]
        return AnnotationLabel.objects.visible_to_user(info.context.user).get(
            id=django_pk
        )

    # LABEL SET RESOLVERS #####################################

    labelsets = DjangoFilterConnectionField(
        LabelSetType, filterset_class=LabelsetFilter
    )

    @graphql_ratelimit_dynamic(get_rate=get_user_tier_rate("READ_LIGHT"))
    def resolve_labelsets(self, info, **kwargs):
        return LabelSet.objects.visible_to_user(info.context.user)

    labelset = relay.Node.Field(LabelSetType)

    def resolve_labelset(self, info, **kwargs):
        django_pk = from_global_id(kwargs.get("id", None))[1]
        return LabelSet.objects.visible_to_user(info.context.user).get(id=django_pk)

    # CORPUS RESOLVERS #####################################
    corpuses = DjangoFilterConnectionField(CorpusType, filterset_class=CorpusFilter)

    @graphql_ratelimit_dynamic(get_rate=get_user_tier_rate("READ_LIGHT"))
    def resolve_corpuses(self, info, **kwargs):
        from opencontractserver.annotations.models import AnnotationLabel

        doc_sq, annot_sq = _corpus_count_subqueries()

        # Subqueries for label counts (via corpus.label_set_id)
        # Note: 'included_in_labelset' is the related_query_name for filtering
        def label_count_subquery(label_type: str):
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

    # CORPUS CATEGORY RESOLVERS #####################################
    corpus_categories = DjangoFilterConnectionField(
        CorpusCategoryType,
        filterset_class=CorpusCategoryFilter,
        description="List all corpus categories",
    )

    @graphql_ratelimit_dynamic(get_rate=get_user_tier_rate("READ_LIGHT"))
    def resolve_corpus_categories(self, info, **kwargs):
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

        # Get IDs of all corpuses visible to this user
        # This properly respects guardian permissions for shared private corpuses
        visible_corpus_ids = list(
            Corpus.objects.visible_to_user(user).values_list("id", flat=True)
        )

        # Count corpuses per category, filtering to only visible ones
        categories = CorpusCategory.objects.annotate(
            _corpus_count=Count(
                "corpuses", filter=Q(corpuses__id__in=visible_corpus_ids), distinct=True
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
    def resolve_corpus_folders(self, info, corpus_id):
        """
        Get all folders in a corpus.
        Returns flat list - frontend reconstructs tree from parentId relationships.

        Delegates to DocumentFolderService.get_visible_folders() for
        permission checking and query optimization.
        """
        from opencontractserver.corpuses.folder_service import DocumentFolderService

        _, corpus_pk = from_global_id(corpus_id)
        return DocumentFolderService.get_visible_folders(
            user=info.context.user, corpus_id=int(corpus_pk)
        )

    corpus_folder = graphene.Field(
        CorpusFolderType,
        id=graphene.ID(required=True),
        description="Get a single folder by ID",
    )

    @graphql_ratelimit_dynamic(get_rate=get_user_tier_rate("READ_LIGHT"))
    def resolve_corpus_folder(self, info, id):
        """
        Get a single folder by ID with permission check.

        Delegates to DocumentFolderService.get_folder_by_id() for
        permission checking and IDOR protection.
        """
        from opencontractserver.corpuses.folder_service import DocumentFolderService

        _, folder_pk = from_global_id(id)
        return DocumentFolderService.get_folder_by_id(
            user=info.context.user, folder_id=int(folder_pk)
        )

    deleted_documents_in_corpus = graphene.List(
        DocumentPathType,
        corpus_id=graphene.ID(required=True),
        description="Get all soft-deleted documents in a corpus (trash folder view)",
    )

    @graphql_ratelimit_dynamic(get_rate=get_user_tier_rate("READ_LIGHT"))
    def resolve_deleted_documents_in_corpus(self, info, corpus_id):
        """
        Get all soft-deleted documents in a corpus for trash folder view.

        Delegates to DocumentFolderService.get_deleted_documents() for
        permission checking and query optimization.
        """
        from opencontractserver.corpuses.folder_service import DocumentFolderService

        _, corpus_pk = from_global_id(corpus_id)
        return DocumentFolderService.get_deleted_documents(
            user=info.context.user, corpus_id=int(corpus_pk)
        )

    # SEARCH RESOURCES FOR MENTIONS #####################################
    search_corpuses_for_mention = DjangoConnectionField(
        CorpusType,
        text_search=graphene.String(
            description="Search query to find corpuses by title or description"
        ),
    )
    search_documents_for_mention = DjangoConnectionField(
        DocumentType,
        text_search=graphene.String(
            description="Search query to find documents by title or description"
        ),
        corpus_id=graphene.ID(
            description="Optional corpus ID to scope search to documents in specific corpus"
        ),
    )
    search_annotations_for_mention = DjangoConnectionField(
        AnnotationType,
        text_search=graphene.String(
            description="Search query to find annotations by label text or raw content"
        ),
        corpus_id=graphene.ID(
            description="Optional corpus ID to scope search to specific corpus"
        ),
    )
    search_users_for_mention = DjangoConnectionField(
        UserType,
        text_search=graphene.String(
            description="Search query to find users by username or email"
        ),
    )

    @graphql_ratelimit_dynamic(get_rate=get_user_tier_rate("READ_LIGHT"))
    def resolve_search_corpuses_for_mention(self, info, text_search=None, **kwargs):
        """
        Search corpuses for @ mention autocomplete.

        SECURITY: Only returns corpuses where user can meaningfully contribute.
        Requires write permission (CREATE/UPDATE/DELETE), creator status, or public corpus.

        Rationale: Mentioning a corpus implies drawing attention to it for collaborative
        purposes. Read-only viewers shouldn't be mentioning corpuses since they can't
        contribute to them.

        See: docs/permissioning/mention_permissioning_spec.md
        """
        from guardian.shortcuts import get_objects_for_user

        user = info.context.user

        # Anonymous users cannot mention (must be authenticated)
        if user.is_anonymous:
            return Corpus.objects.none()

        # Superusers see all corpuses
        if user.is_superuser:
            qs = Corpus.objects.all()
        else:
            # Get corpuses user has write permission to
            writable_corpuses = get_objects_for_user(
                user,
                [
                    "corpuses.create_corpus",
                    "corpuses.update_corpus",
                    "corpuses.remove_corpus",  # Note: PermissionTypes.DELETE maps to "remove"
                ],
                klass=Corpus,
                accept_global_perms=False,
                any_perm=True,  # Has ANY of these permissions
            )

            # Combine: creator OR writable OR public
            qs = Corpus.objects.filter(
                Q(creator=user) | Q(id__in=writable_corpuses) | Q(is_public=True)
            ).distinct()

        if text_search:
            qs = qs.filter(
                Q(title__icontains=text_search) | Q(description__icontains=text_search)
            )

        # Order by most recently modified first
        return qs.order_by("-modified")

    @graphql_ratelimit_dynamic(get_rate=get_user_tier_rate("READ_LIGHT"))
    def resolve_search_documents_for_mention(
        self, info, text_search=None, corpus_id=None, **kwargs
    ):
        """
        Search documents for @ mention autocomplete.

        SECURITY: Only returns documents where user can meaningfully contribute.
        Requires one of:
        - User is creator
        - User has write permission on document
        - Document is in a corpus where user has write permission
        - Document is public AND (no corpus OR public corpus OR user has corpus access)

        When corpus_id is provided, results are further filtered to only include
        documents that belong to that specific corpus. This prevents cross-corpus
        document references in AI agent contexts (Issue #741).

        Rationale: Similar to corpuses, mentioning a document implies collaborative context.
        However, public documents are included to allow discussion/reference in open forums.

        See: docs/permissioning/mention_permissioning_spec.md
        """
        from guardian.shortcuts import get_objects_for_user

        user = info.context.user

        # Anonymous users cannot mention (must be authenticated)
        if user.is_anonymous:
            return Document.objects.none()

        # Superusers see all documents
        if user.is_superuser:
            qs = Document.objects.all()
        else:
            # Get documents user has write permission to
            writable_documents = get_objects_for_user(
                user,
                [
                    "documents.create_document",
                    "documents.update_document",
                    "documents.remove_document",  # Note: PermissionTypes.DELETE maps to "remove"
                ],
                klass=Document,
                accept_global_perms=False,
                any_perm=True,
            )

            # Get corpuses user has write permission to
            writable_corpuses = get_objects_for_user(
                user,
                [
                    "corpuses.create_corpus",
                    "corpuses.update_corpus",
                    "corpuses.remove_corpus",  # Note: PermissionTypes.DELETE maps to "remove"
                ],
                klass=Corpus,
                accept_global_perms=False,
                any_perm=True,
            )

            # Get corpuses user can at least read (for public document context)
            readable_corpuses = Corpus.objects.visible_to_user(user)

            # Get documents in writable corpuses via DocumentPath (corpus isolation)
            from opencontractserver.documents.models import DocumentPath

            docs_in_writable_corpuses = DocumentPath.objects.filter(
                corpus__in=writable_corpuses, is_current=True, is_deleted=False
            ).values_list("document_id", flat=True)

            # Get documents in readable corpuses for public document context
            docs_in_readable_corpuses = DocumentPath.objects.filter(
                corpus__in=readable_corpuses, is_current=True, is_deleted=False
            ).values_list("document_id", flat=True)

            # Get documents in public corpuses for public document context
            public_corpuses = Corpus.objects.filter(is_public=True)
            docs_in_public_corpuses = DocumentPath.objects.filter(
                corpus__in=public_corpuses, is_current=True, is_deleted=False
            ).values_list("document_id", flat=True)

            # Get standalone documents (not in any corpus via DocumentPath)
            docs_with_paths = (
                DocumentPath.objects.filter(is_current=True, is_deleted=False)
                .values_list("document_id", flat=True)
                .distinct()
            )

            # Build complex filter:
            # 1. User is creator
            # 2. User has write permission on document
            # 3. Document is in a writable corpus (via DocumentPath)
            # 4. Document is public AND (not in any corpus OR in public corpus OR user has corpus access)
            qs = Document.objects.filter(
                Q(creator=user)
                | Q(id__in=writable_documents)
                | Q(id__in=docs_in_writable_corpuses)  # Via DocumentPath
                | (
                    Q(is_public=True)
                    & (
                        ~Q(id__in=docs_with_paths)  # Not in any corpus (standalone)
                        | Q(id__in=docs_in_public_corpuses)  # In a public corpus
                        | Q(id__in=docs_in_readable_corpuses)  # In a readable corpus
                    )
                )
            ).distinct()

        if text_search:
            qs = qs.filter(
                Q(title__icontains=text_search) | Q(description__icontains=text_search)
            )

        # Filter by corpus if provided (Issue #741 - prevent cross-corpus references)
        if corpus_id:
            _, corpus_pk = from_global_id(corpus_id)
            docs_in_target_corpus = DocumentPath.objects.filter(
                corpus_id=int(corpus_pk),
                is_current=True,
                is_deleted=False,
            ).values_list("document_id", flat=True)
            qs = qs.filter(id__in=docs_in_target_corpus)

        # Note: corpus field exists in model but not in current DB schema for select_related
        # Documents use Many-to-Many relationship via Corpus.documents instead

        # Order by most recently modified first
        return qs.order_by("-modified")

    @graphql_ratelimit_dynamic(get_rate=get_user_tier_rate("READ_LIGHT"))
    def resolve_search_annotations_for_mention(
        self, info, text_search=None, corpus_id=None, **kwargs
    ):
        """
        Search annotations for @ mention autocomplete.

        SECURITY: Annotations inherit permissions from document + corpus.
        Uses .visible_to_user() which applies composite permission logic.

        PERFORMANCE NOTES:
        - Prioritizes annotation_label.text matches (indexed, fast)
        - Falls back to raw_text search (full-text, slower)
        - Corpus scoping significantly reduces search space
        - Limits to 10 results to prevent overwhelming UI

        Rationale: Mentioning annotations allows precise reference to specific
        content sections. Useful for discussions, citations, and cross-references.

        @param text_search: Search query for label text or content
        @param corpus_id: Optional corpus to scope search (recommended for performance)
        """
        from opencontractserver.annotations.models import Annotation

        user = info.context.user

        # Anonymous users cannot mention (must be authenticated)
        if user.is_anonymous:
            return Annotation.objects.none()

        # Use visible_to_user() which handles composite document+corpus permissions
        qs = Annotation.objects.visible_to_user(user)

        # Scope to specific corpus if provided (major performance boost)
        # Issue #741: Fix to properly convert GraphQL global ID to database primary key
        if corpus_id:
            _, corpus_pk = from_global_id(corpus_id)
            qs = qs.filter(corpus_id=int(corpus_pk))

        if text_search:
            # Search priority:
            # 1. annotation_label.text (indexed CharField - fast)
            # 2. raw_text (TextField - slower but comprehensive)
            qs = qs.filter(
                Q(annotation_label__text__icontains=text_search)
                | Q(raw_text__icontains=text_search)
            )

        # Select related for efficient queries
        qs = qs.select_related("annotation_label", "document", "corpus")

        # Order by label match first (more relevant), then by created date
        # Annotations matching label text are usually more specific/useful
        from django.db.models import Case, IntegerField, Value, When

        if text_search:
            qs = qs.annotate(
                label_match=Case(
                    When(
                        annotation_label__text__icontains=text_search,
                        then=Value(0),
                    ),
                    default=Value(1),
                    output_field=IntegerField(),
                )
            ).order_by("label_match", "-created")
        else:
            qs = qs.order_by("-created")

        # Note: DjangoConnectionField handles pagination automatically
        # Slicing here would prevent GraphQL from applying filters
        return qs

    @graphql_ratelimit_dynamic(get_rate=get_user_tier_rate("READ_LIGHT"))
    def resolve_search_users_for_mention(self, info, text_search=None, **kwargs):
        """
        Search users for @ mention autocomplete.

        SECURITY: Respects user profile privacy settings.
        Users are visible if:
        - Profile is public (is_profile_public=True)
        - Requesting user shares corpus membership with > READ permission
        - It's the requesting user's own profile

        PERFORMANCE NOTES:
        - Uses UserQueryOptimizer for efficient visibility filtering
        - Searches username (indexed, fast)
        - Searches email (indexed, fast)

        @param text_search: Search query for username or email
        """
        from django.contrib.auth import get_user_model

        from opencontractserver.users.query_optimizer import UserQueryOptimizer

        User = get_user_model()
        user = info.context.user

        # Anonymous users cannot mention (must be authenticated)
        if user.is_anonymous:
            return User.objects.none()

        # Use UserQueryOptimizer for visibility filtering
        qs = UserQueryOptimizer.get_visible_users(user)

        if text_search:
            # Search username and email
            qs = qs.filter(
                Q(username__icontains=text_search) | Q(email__icontains=text_search)
            )

        # Order by username for consistent results
        qs = qs.order_by("username")

        # Note: DjangoConnectionField handles pagination automatically
        return qs

    # DOCUMENT RESOLVERS #####################################

    documents = DjangoFilterConnectionField(
        DocumentType, filterset_class=DocumentFilter
    )

    @graphql_ratelimit_dynamic(get_rate=get_user_tier_rate("READ_LIGHT"))
    def resolve_documents(self, info, **kwargs):
        # Use lightweight mode to skip heavy prefetches (doc_annotations,
        # rows, relationships, notes) that are unnecessary for list/TOC
        # queries requesting only basic document fields.
        return Document.objects.visible_to_user(info.context.user, lightweight=True)

    document = graphene.Field(DocumentType, id=graphene.String())

    def resolve_document(self, info, **kwargs):
        document_id = kwargs.get("id")
        if not document_id:
            return None

        cache = getattr(info.context, "_resolver_cache", None)
        if cache is None:
            cache = {}
            info.context._resolver_cache = cache

        doc_cache = cache.setdefault("document", {})
        if document_id in doc_cache:
            return doc_cache[document_id]

        _, pk = from_global_id(document_id)
        document = Document.objects.visible_to_user(info.context.user).get(id=pk)

        doc_cache[document_id] = document
        return document

    # IMPORT RESOLVERS #####################################
    userimports = DjangoConnectionField(UserImportType)

    @login_required
    def resolve_userimports(self, info, **kwargs):
        return UserImport.objects.visible_to_user(info.context.user)

    userimport = relay.Node.Field(UserImportType)

    @login_required
    def resolve_userimport(self, info, **kwargs):
        django_pk = from_global_id(kwargs.get("id", None))[1]
        return UserImport.objects.visible_to_user(info.context.user).get(id=django_pk)

    # EXPORT RESOLVERS #####################################
    userexports = DjangoFilterConnectionField(
        UserExportType, filterset_class=ExportFilter
    )

    @login_required
    def resolve_userexports(self, info, **kwargs):
        return UserExport.objects.visible_to_user(info.context.user)

    userexport = relay.Node.Field(UserExportType)

    @login_required
    def resolve_userexport(self, info, **kwargs):
        django_pk = from_global_id(kwargs.get("id", None))[1]
        return UserExport.objects.visible_to_user(info.context.user).get(id=django_pk)

    # ASSIGNMENT RESOLVERS #####################################
    assignments = DjangoFilterConnectionField(
        AssignmentType, filterset_class=AssignmentFilter
    )

    @login_required
    def resolve_assignments(self, info, **kwargs):
        """
        Resolve assignments.

        DEPRECATED: Assignment feature is not currently used.
        See opencontractserver/users/models.py:202-206

        SECURITY: Users can only see assignments where they are the assignor or assignee.
        Superusers can see all assignments.
        """
        import warnings

        warnings.warn(
            "Assignment feature is deprecated and not in use", DeprecationWarning
        )

        user = info.context.user
        if user.is_superuser:
            return Assignment.objects.all()
        else:
            # User can see assignments they created or were assigned to
            return Assignment.objects.filter(Q(assignor=user) | Q(assignee=user))

    assignment = relay.Node.Field(AssignmentType)

    @login_required
    def resolve_assignment(self, info, **kwargs):
        """
        Resolve a single assignment by ID.

        DEPRECATED: Assignment feature is not currently used.

        SECURITY: Uses direct query instead of broken visible_to_user
        (Assignment model doesn't have this method - it inherits from
        django.db.models.Model, not BaseOCModel).
        """
        import warnings

        warnings.warn(
            "Assignment feature is deprecated and not in use", DeprecationWarning
        )

        user = info.context.user
        django_pk = from_global_id(kwargs.get("id", None))[1]

        # Use direct query - Assignment model doesn't have visible_to_user manager
        if user.is_superuser:
            try:
                return Assignment.objects.get(id=django_pk)
            except Assignment.DoesNotExist:
                raise GraphQLError("Assignment not found")

        # Regular users can only see their own assignments
        try:
            return Assignment.objects.get(
                Q(id=django_pk) & (Q(assignor=user) | Q(assignee=user))
            )
        except Assignment.DoesNotExist:
            # Same error whether doesn't exist or no permission (IDOR protection)
            raise GraphQLError("Assignment not found")

    if settings.USE_ANALYZER:

        # GREMLIN ENGINE RESOLVERS #####################################
        gremlin_engine = relay.Node.Field(GremlinEngineType_READ)

        def resolve_gremlin_engine(self, info, **kwargs):
            django_pk = from_global_id(kwargs.get("id", None))[1]
            return GremlinEngine.objects.visible_to_user(info.context.user).get(
                id=django_pk
            )

        gremlin_engines = DjangoFilterConnectionField(
            GremlinEngineType_READ, filterset_class=GremlinEngineFilter
        )

        def resolve_gremlin_engines(self, info, **kwargs):
            return GremlinEngine.objects.visible_to_user(info.context.user)

        # ANALYZER RESOLVERS #####################################
        analyzer = relay.Node.Field(AnalyzerType)

        def resolve_analyzer(self, info, **kwargs):

            if kwargs.get("id", None) is not None:
                django_pk = from_global_id(kwargs.get("id", None))[1]
            elif kwargs.get("analyzerId", None) is not None:
                django_pk = kwargs.get("analyzerId", None)
            else:
                return None

            return Analyzer.objects.visible_to_user(info.context.user).get(id=django_pk)

        analyzers = DjangoFilterConnectionField(
            AnalyzerType, filterset_class=AnalyzerFilter
        )

        def resolve_analyzers(self, info, **kwargs):
            return Analyzer.objects.visible_to_user(info.context.user)

        # ANALYSIS RESOLVERS #####################################
        analysis = relay.Node.Field(AnalysisType)

        def resolve_analysis(self, info, **kwargs):
            from opencontractserver.annotations.query_optimizer import (
                AnalysisQueryOptimizer,
            )

            django_pk = from_global_id(kwargs.get("id", None))[1]
            has_perm, analysis = AnalysisQueryOptimizer.check_analysis_permission(
                info.context.user, int(django_pk)
            )
            return analysis if has_perm else None

        analyses = DjangoFilterConnectionField(
            AnalysisType, filterset_class=AnalysisFilter
        )

        @graphql_ratelimit_dynamic(get_rate=get_user_tier_rate("READ_MEDIUM"))
        def resolve_analyses(self, info, **kwargs):
            from opencontractserver.annotations.query_optimizer import (
                AnalysisQueryOptimizer,
            )

            corpus_id = kwargs.get("corpus_id")
            if corpus_id:
                corpus_django_pk = int(from_global_id(corpus_id)[1])
            else:
                corpus_django_pk = None

            return AnalysisQueryOptimizer.get_visible_analyses(
                info.context.user, corpus_id=corpus_django_pk
            )

    fieldset = relay.Node.Field(FieldsetType)

    def resolve_fieldset(self, info, **kwargs):
        django_pk = from_global_id(kwargs.get("id", None))[1]
        return Fieldset.objects.visible_to_user(info.context.user).get(id=django_pk)

    fieldsets = DjangoFilterConnectionField(
        FieldsetType, filterset_class=FieldsetFilter
    )

    def resolve_fieldsets(self, info, **kwargs):
        return Fieldset.objects.visible_to_user(info.context.user)

    column = relay.Node.Field(ColumnType)

    def resolve_column(self, info, **kwargs):
        django_pk = from_global_id(kwargs.get("id", None))[1]
        return Column.objects.visible_to_user(info.context.user).get(id=django_pk)

    columns = DjangoFilterConnectionField(ColumnType, filterset_class=ColumnFilter)

    def resolve_columns(self, info, **kwargs):
        return Column.objects.visible_to_user(info.context.user)

    extract = relay.Node.Field(ExtractType)

    def resolve_extract(self, info, **kwargs):
        from opencontractserver.annotations.query_optimizer import ExtractQueryOptimizer

        django_pk = from_global_id(kwargs.get("id", None))[1]
        has_perm, extract = ExtractQueryOptimizer.check_extract_permission(
            info.context.user, int(django_pk)
        )
        return extract if has_perm else None

    extracts = DjangoFilterConnectionField(
        ExtractType, filterset_class=ExtractFilter, max_limit=15
    )

    def resolve_extracts(self, info, **kwargs):
        from opencontractserver.annotations.query_optimizer import ExtractQueryOptimizer

        corpus_id = kwargs.get("corpus_id")
        if corpus_id:
            corpus_django_pk = int(from_global_id(corpus_id)[1])
        else:
            corpus_django_pk = None

        return ExtractQueryOptimizer.get_visible_extracts(
            info.context.user, corpus_id=corpus_django_pk
        )

    datacell = relay.Node.Field(DatacellType)

    def resolve_datacell(self, info, **kwargs):
        django_pk = from_global_id(kwargs.get("id", None))[1]
        return Datacell.objects.visible_to_user(info.context.user).get(id=django_pk)

    datacells = DjangoFilterConnectionField(
        DatacellType, filterset_class=DatacellFilter
    )

    def resolve_datacells(self, info, **kwargs):
        return Datacell.objects.visible_to_user(info.context.user)

    registered_extract_tasks = graphene.Field(GenericScalar)

    @login_required
    def resolve_registered_extract_tasks(self, info, **kwargs):
        from config import celery_app

        tasks = {}

        # Try to get tasks from the app instance
        # Get tasks from the app instance
        try:
            for task_name, task in celery_app.tasks.items():
                if not task_name.startswith("celery."):
                    docstring = inspect.getdoc(task.run) or "No docstring available"
                    tasks[task_name] = docstring

        except AttributeError as e:
            logger.warning(f"Couldn't get tasks from app instance: {str(e)}")

        # Filter out Celery's internal tasks
        return {
            task: description
            for task, description in tasks.items()
            if task.startswith("opencontractserver.tasks.data_extract_tasks")
        }

    corpus_stats = graphene.Field(CorpusStatsType, corpus_id=graphene.ID(required=True))

    @graphql_ratelimit_dynamic(get_rate=get_user_tier_rate("READ_MEDIUM"))
    def resolve_corpus_stats(self, info, corpus_id):
        """
        Resolve corpus statistics with proper permission filtering.

        SECURITY: All counts respect the permission model:
        - Documents: Uses visible_to_user() + DocumentPath filtering
        - Annotations: Filtered by visible documents (inherit doc+corpus permissions)
        - Analyses: Uses AnalysisQueryOptimizer (hybrid permission model)
        - Extracts: Uses ExtractQueryOptimizer (hybrid permission model)
        - Relationships: Uses DocumentRelationshipQueryOptimizer (inherit doc+corpus)
        - Threads/Chats: Uses ConversationQueryOptimizer (single visibility query)
        """
        from opencontractserver.annotations.query_optimizer import (
            AnalysisQueryOptimizer,
            ExtractQueryOptimizer,
        )
        from opencontractserver.conversations.query_optimizer import (
            ConversationQueryOptimizer,
        )

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
                    user, corpus_id=corpus.id
                ).count()

                # total_extracts: Uses hybrid permission model (extract perm + corpus perm)
                total_extracts = ExtractQueryOptimizer.get_visible_extracts(
                    user, corpus_id=corpus.id
                ).count()

                # total_threads and total_chats: Use ConversationQueryOptimizer
                # to execute visibility subqueries once instead of twice
                conv_optimizer = ConversationQueryOptimizer(user)
                total_threads, total_chats = (
                    conv_optimizer.get_corpus_conversation_counts(corpus.id)
                )

                # total_relationships: Uses DocumentRelationshipQueryOptimizer
                # Relationships inherit from source_doc + target_doc + corpus
                total_relationships = (
                    DocumentRelationshipQueryOptimizer.get_visible_relationships(
                        user, corpus_id=corpus.id, context=info.context
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

    document_corpus_actions = graphene.Field(
        DocumentCorpusActionsType,
        document_id=graphene.ID(required=True),
        corpus_id=graphene.ID(required=False),
    )

    def resolve_document_corpus_actions(self, info, document_id, corpus_id=None):
        """
        Resolve document actions (corpus actions, extracts, analysis rows) with proper
        permission filtering.

        SECURITY: Uses DocumentActionsQueryOptimizer which follows the least-privilege model:
        - Document permissions are primary
        - Corpus permissions are secondary
        - Effective permission = MIN(document_permission, corpus_permission)

        This prevents unauthorized access to document-related data.
        """
        from opencontractserver.documents.query_optimizer import (
            DocumentActionsQueryOptimizer,
        )

        user = info.context.user

        # Guard against empty strings - from_global_id('') returns ('', '')
        document_pk = from_global_id(document_id)[1] if document_id else None
        corpus_pk = from_global_id(corpus_id)[1] if corpus_id else None

        # Validate document_id is required and not empty
        if not document_pk:
            raise Exception("documentId is required and must be a valid ID")

        # Use centralized permission-aware optimizer
        actions = DocumentActionsQueryOptimizer.get_document_actions(
            user=user,
            document_id=int(document_pk),
            corpus_id=int(corpus_pk) if corpus_pk else None,
        )

        return DocumentCorpusActionsType(
            corpus_actions=actions["corpus_actions"],
            extracts=actions["extracts"],
            analysis_rows=actions["analysis_rows"],
        )

    pipeline_components = graphene.Field(
        PipelineComponentsType,
        mimetype=graphene.Argument(FileTypeEnum, required=False),
        description="Retrieve all registered pipeline components, optionally filtered by MIME type.",
    )

    @login_required
    def resolve_pipeline_components(
        self, info, mimetype: Optional[FileTypeEnum] = None
    ) -> PipelineComponentsType:
        """
        Resolver for the pipeline_components query.

        Uses cached registry for fast response times. The registry is
        initialized once on first access and cached permanently.

        Args:
            info: GraphQL execution info.
            mimetype (Optional[FileTypeEnum]): MIME type to filter pipeline components.

        Returns:
            PipelineComponentsType: The pipeline components grouped by type.
        """
        from opencontractserver.pipeline.registry import (
            get_all_components_cached,
            get_components_by_mimetype_cached,
        )

        if mimetype:
            # Convert the GraphQL enum value to the appropriate MIME type string
            mime_type_mapping = {
                "pdf": "application/pdf",
                "txt": "text/plain",
                "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            }
            mime_type_str = mime_type_mapping.get(mimetype.value)

            # Get compatible components from cached registry
            components_data = get_components_by_mimetype_cached(mime_type_str)
        else:
            # Get all components from cached registry
            components_data = get_all_components_cached()

        user = info.context.user

        # Get PipelineSettings instance for configured component filtering
        from opencontractserver.documents.models import PipelineSettings

        settings_instance = PipelineSettings.get_instance()

        if not user.is_superuser:
            configured_components: set[str] = set()

            preferred_parsers = settings_instance.preferred_parsers or {}
            preferred_embedders = settings_instance.preferred_embedders or {}
            preferred_thumbnailers = settings_instance.preferred_thumbnailers or {}

            configured_components.update(preferred_parsers.values())
            configured_components.update(preferred_embedders.values())
            configured_components.update(preferred_thumbnailers.values())

            if settings_instance.default_embedder:
                configured_components.add(settings_instance.default_embedder)

            if settings_instance.parser_kwargs:
                configured_components.update(settings_instance.parser_kwargs.keys())

            if settings_instance.component_settings:
                configured_components.update(
                    settings_instance.component_settings.keys()
                )

            def filter_configured(definitions):
                return [
                    defn
                    for defn in definitions
                    if defn.class_name in configured_components
                ]

            components_data = {
                "parsers": filter_configured(components_data["parsers"]),
                "embedders": filter_configured(components_data["embedders"]),
                "thumbnailers": filter_configured(components_data["thumbnailers"]),
                "post_processors": filter_configured(
                    components_data["post_processors"]
                ),
            }

        # Convert PipelineComponentDefinition objects to GraphQL types
        def to_graphql_type(defn, component_type: str) -> PipelineComponentType:
            settings_schema = None
            if user.is_superuser:
                # Get schema augmented with has_value/current_value from DB
                augmented_schema = settings_instance.get_component_schema(
                    defn.class_name
                )
                if augmented_schema:
                    settings_schema = [
                        ComponentSettingSchemaType(
                            name=name,
                            setting_type=info.get("type", "optional"),
                            python_type=info.get("python_type"),
                            required=info.get("required", False),
                            description=info.get("description", ""),
                            default=info.get("default"),
                            env_var=info.get("env_var"),
                            has_value=info.get("has_value", False),
                            current_value=info.get("current_value"),
                        )
                        for name, info in augmented_schema.items()
                    ]

            component_info = PipelineComponentType(
                name=defn.name,
                class_name=defn.class_name,
                title=defn.title,
                module_name=defn.module_name,
                description=defn.description,
                author=defn.author,
                dependencies=list(defn.dependencies),
                supported_file_types=list(defn.supported_file_types),
                component_type=component_type,
                input_schema=defn.input_schema,
                settings_schema=settings_schema,
            )
            if defn.vector_size is not None:
                component_info.vector_size = defn.vector_size
            return component_info

        return PipelineComponentsType(
            parsers=[to_graphql_type(d, "parser") for d in components_data["parsers"]],
            embedders=[
                to_graphql_type(d, "embedder") for d in components_data["embedders"]
            ],
            thumbnailers=[
                to_graphql_type(d, "thumbnailer")
                for d in components_data["thumbnailers"]
            ],
            post_processors=[
                to_graphql_type(d, "post_processor")
                for d in components_data["post_processors"]
            ],
        )

    conversations = DjangoFilterConnectionField(
        ConversationType,
        filterset_class=ConversationFilter,
        description="Retrieve conversations, optionally filtered by document_id or corpus_id",
    )

    def resolve_conversations(self, info, **kwargs):
        """
        Resolver to fetch Conversations along with their Messages.

        Anonymous users can see public conversations.
        Authenticated users see public conversations, their own, or explicitly shared.

        Args:
            info: GraphQL execution info.
            **kwargs: Filter arguments passed through DjangoFilterConnectionField

        Returns:
            QuerySet[Conversation]: Filtered queryset of conversations
        """
        return (
            Conversation.objects.visible_to_user(info.context.user)
            .select_related("creator", "chat_with_corpus", "chat_with_corpus__creator")
            .prefetch_related(
                Prefetch(
                    "chat_messages",
                    queryset=ChatMessage.objects.order_by("created_at"),
                )
            )
            .order_by("-created")
        )

    # CONVERSATION SEARCH RESOLVERS #######################################
    search_conversations = relay.ConnectionField(
        "config.graphql.graphene_types.ConversationConnection",
        query=graphene.String(required=True, description="Search query text"),
        corpus_id=graphene.ID(required=False, description="Filter by corpus ID"),
        document_id=graphene.ID(required=False, description="Filter by document ID"),
        conversation_type=graphene.String(
            required=False, description="Filter by conversation type (chat/thread)"
        ),
        top_k=graphene.Int(
            default_value=100,
            description="Maximum number of results to fetch from vector store",
        ),
        description="Search conversations using vector similarity with pagination",
    )

    def resolve_search_conversations(
        self,
        info,
        query,
        corpus_id=None,
        document_id=None,
        conversation_type=None,
        top_k=100,
        **kwargs,
    ):
        """
        Search conversations using vector similarity with cursor-based pagination.

        Anonymous users can search public conversations.
        Authenticated users can search public, their own, or explicitly shared conversations.

        Args:
            info: GraphQL execution info
            query: Search query text
            corpus_id: Optional corpus ID filter
            document_id: Optional document ID filter
            conversation_type: Optional conversation type filter
            top_k: Maximum results to fetch from vector store (default 100)
            **kwargs: Pagination args (first, after, last, before) handled by ConnectionField

        Returns:
            Connection with edges and pageInfo for pagination
        """
        from opencontractserver.llms.vector_stores.core_conversation_vector_stores import (
            CoreConversationVectorStore,
            VectorSearchQuery,
        )

        # Convert global IDs to database IDs
        corpus_pk = from_global_id(corpus_id)[1] if corpus_id else None
        document_pk = from_global_id(document_id)[1] if document_id else None

        # Get embedder path from settings if no corpus specified
        embedder_path = None
        if not corpus_pk and not document_id:
            # Use default embedder from settings
            from django.conf import settings

            embedder_path = getattr(settings, "DEFAULT_EMBEDDER_PATH", None)
            if not embedder_path:
                # If still no embedder available, raise clear error
                raise ValueError(
                    "Either corpus_id, document_id, or DEFAULT_EMBEDDER_PATH setting is required"
                )

        # Handle anonymous users
        user_id = (
            None
            if not info.context.user or info.context.user.is_anonymous
            else info.context.user.id
        )

        # Create vector store
        vector_store = CoreConversationVectorStore(
            user_id=user_id,
            corpus_id=corpus_pk,
            document_id=document_pk,
            conversation_type=conversation_type,
            embedder_path=embedder_path,
        )

        # Create search query
        search_query = VectorSearchQuery(
            query_text=query,
            similarity_top_k=top_k,
        )

        # Perform search (sync in GraphQL context)
        results = vector_store.search(search_query)

        # Extract conversations from results and return as queryset-like list
        # ConnectionField will handle pagination automatically
        conversations = [result.conversation for result in results]
        return conversations

    search_messages = graphene.List(
        "config.graphql.graphene_types.MessageType",
        query=graphene.String(required=True, description="Search query text"),
        corpus_id=graphene.ID(required=False, description="Filter by corpus ID"),
        conversation_id=graphene.ID(
            required=False, description="Filter by conversation ID"
        ),
        msg_type=graphene.String(
            required=False, description="Filter by message type (HUMAN/LLM/SYSTEM)"
        ),
        top_k=graphene.Int(default_value=10, description="Number of results to return"),
        description="Search messages using vector similarity",
    )

    @login_required
    def resolve_search_messages(
        self, info, query, corpus_id=None, conversation_id=None, msg_type=None, top_k=10
    ):
        """
        Search messages using vector similarity.

        Args:
            info: GraphQL execution info
            query: Search query text
            corpus_id: Optional corpus ID filter
            conversation_id: Optional conversation ID filter
            msg_type: Optional message type filter
            top_k: Number of results to return

        Returns:
            List[ChatMessage]: List of matching messages
        """
        from opencontractserver.llms.vector_stores.core_conversation_vector_stores import (
            CoreChatMessageVectorStore,
            VectorSearchQuery,
        )

        # Convert global IDs to database IDs
        corpus_pk = from_global_id(corpus_id)[1] if corpus_id else None
        conversation_pk = (
            from_global_id(conversation_id)[1] if conversation_id else None
        )

        # Get embedder path from settings if no corpus specified
        embedder_path = None
        if not corpus_pk and not conversation_pk:
            # Use default embedder from settings
            from django.conf import settings

            embedder_path = getattr(settings, "DEFAULT_EMBEDDER_PATH", None)
            if not embedder_path:
                # If still no embedder available, raise clear error
                raise ValueError(
                    "Either corpus_id, conversation_id, or DEFAULT_EMBEDDER_PATH setting is required"
                )

        # Create vector store
        vector_store = CoreChatMessageVectorStore(
            user_id=info.context.user.id,
            corpus_id=corpus_pk,
            conversation_id=conversation_pk,
            msg_type=msg_type,
            embedder_path=embedder_path,
        )

        # Create search query
        search_query = VectorSearchQuery(
            query_text=query,
            similarity_top_k=top_k,
        )

        # Perform search (sync in GraphQL context)
        results = vector_store.search(search_query)

        # Extract messages from results
        return [result.message for result in results]

    # SEMANTIC SEARCH QUERIES #############################################
    semantic_search = graphene.List(
        SemanticSearchResultType,
        query=graphene.String(required=True, description="Search query text"),
        corpus_id=graphene.ID(
            required=False, description="Optional corpus ID to search within"
        ),
        document_id=graphene.ID(
            required=False, description="Optional document ID to search within"
        ),
        modalities=graphene.List(
            graphene.String,
            required=False,
            description="Filter by content modalities (TEXT, IMAGE)",
        ),
        label_text=graphene.String(
            required=False,
            description="Filter by annotation label text (case-insensitive substring match)",
        ),
        raw_text_contains=graphene.String(
            required=False,
            description="Filter by raw_text content (case-insensitive substring match)",
        ),
        limit=graphene.Int(
            default_value=50,
            description="Maximum number of results to return (default: 50, max: 200)",
        ),
        offset=graphene.Int(
            default_value=0,
            description="Number of results to skip for pagination",
        ),
        description=(
            "Hybrid search combining vector similarity with text filters. "
            "Uses the default embedder for global cross-corpus search. "
            "Results are first filtered by text criteria, then ranked by similarity."
        ),
    )

    @login_required
    def resolve_semantic_search(
        self,
        info,
        query,
        corpus_id=None,
        document_id=None,
        modalities=None,
        label_text=None,
        raw_text_contains=None,
        limit=50,
        offset=0,
    ):
        """
        Hybrid search combining vector similarity with text filters.

        This query enables semantic (meaning-based) search across all annotations
        the user has access to, using the default embedder embeddings that are
        created for every annotation as part of the dual embedding strategy.

        HYBRID SEARCH:
        - Vector similarity search ranks results by semantic relevance
        - Text filters (label_text, raw_text_contains) narrow down results
        - Filters are applied BEFORE vector search for efficiency

        PERMISSION MODEL (follows consolidated_permissioning_guide.md):
        - Uses Document.objects.visible_to_user() for document access control
        - Structural annotations are always visible if document is accessible
        - Non-structural annotations follow: visible if public OR owned by user
        - Corpus permissions are respected via document visibility

        Args:
            info: GraphQL execution info
            query: Search query text for vector similarity
            corpus_id: Optional corpus ID to limit search to (global ID)
            document_id: Optional document ID to limit search to (global ID)
            modalities: Optional list of modalities to filter by (TEXT, IMAGE)
            label_text: Optional filter by annotation label text (case-insensitive)
            raw_text_contains: Optional filter by raw_text substring (case-insensitive)
            limit: Maximum number of results (capped at 200)
            offset: Pagination offset

        Returns:
            List[SemanticSearchResultType]: List of matching annotations with scores
        """
        from opencontractserver.llms.vector_stores.core_vector_stores import (
            CoreAnnotationVectorStore,
        )

        # N+1 OPTIMIZATION NOTE: The CoreAnnotationVectorStore already applies
        # select_related("annotation_label", "document", "corpus") to the base
        # queryset (see core_vector_stores.py:200-202 and :639-641). This means
        # all related objects are eagerly loaded and no additional queries are
        # made when accessing annotation.document, annotation.corpus, or
        # annotation.annotation_label in the filter loops or result types below.
        # Cap limit to prevent abuse
        limit = min(limit, 200)

        # Convert global IDs to database IDs
        corpus_pk = int(from_global_id(corpus_id)[1]) if corpus_id else None
        document_pk = int(from_global_id(document_id)[1]) if document_id else None

        user = info.context.user

        # -------------------------------------------------------------------------
        # SECURITY: Verify user has access to requested document/corpus (IDOR prevention)
        # Uses visible_to_user() which returns empty queryset if no access.
        # We return empty results for both "not found" and "no permission" cases
        # to prevent enumeration attacks.
        # -------------------------------------------------------------------------
        if document_pk:
            if (
                not Document.objects.visible_to_user(user)
                .filter(id=document_pk)
                .exists()
            ):
                # Document doesn't exist or user lacks permission - return empty results
                return []

        if corpus_pk:
            if not Corpus.objects.visible_to_user(user).filter(id=corpus_pk).exists():
                # Corpus doesn't exist or user lacks permission - return empty results
                return []

        # Build metadata filters for hybrid search
        metadata_filters = {}
        if label_text:
            metadata_filters["annotation_label"] = label_text
        if raw_text_contains:
            metadata_filters["raw_text"] = raw_text_contains

        # If document_id or corpus_id provided, use the instance-based search
        # which respects corpus-specific embedders
        # Import here to avoid circular imports
        from opencontractserver.pipeline.utils import get_default_embedder_path

        if document_pk or corpus_pk:
            # Issue #437: Use corpus.preferred_embedder for corpus-scoped search
            # instead of the global default embedder. Each corpus has a frozen
            # embedder binding set at creation, and all annotations in the corpus
            # have embeddings for that embedder. This ensures consistent search
            # even if the default embedder changes after the corpus was created.
            # When no corpus_id is provided (document-only search), fall back to
            # the PipelineSettings default embedder.
            scoped_embedder_path = get_default_embedder_path()
            if corpus_pk:
                # Fetch the corpus's frozen embedder directly to avoid a
                # redundant DB lookup inside CoreAnnotationVectorStore.
                corpus_embedder = (
                    Corpus.objects.filter(pk=corpus_pk)
                    .values_list("preferred_embedder", flat=True)
                    .first()
                )
                if corpus_embedder:
                    scoped_embedder_path = corpus_embedder

            # Use instance-based CoreAnnotationVectorStore for scoped search
            # Permission already verified above
            vector_store = CoreAnnotationVectorStore(
                user_id=user.id,
                corpus_id=corpus_pk,
                document_id=document_pk,
                modalities=modalities,
                must_have_text=raw_text_contains,  # Additional text filter
                embedder_path=scoped_embedder_path,
            )

            from opencontractserver.llms.vector_stores.core_vector_stores import (
                VectorSearchQuery,
            )

            search_query = VectorSearchQuery(
                query_text=query,
                similarity_top_k=limit + offset,  # Fetch extra for pagination
                filters={"annotation_label": label_text} if label_text else None,
            )

            results = vector_store.search(search_query)

            # Apply pagination
            paginated_results = results[offset : offset + limit]
        else:
            # Use global_search for cross-corpus search
            # Then apply additional filters post-search
            results = CoreAnnotationVectorStore.global_search(
                user_id=user.id,
                query_text=query,
                top_k=(limit + offset) * 3,  # Fetch more for post-filtering
                modalities=modalities,
            )

            # Apply hybrid text filters post-search
            if label_text or raw_text_contains:
                filtered_results = []
                for result in results:
                    annotation = result.annotation
                    # Check label_text filter
                    if label_text:
                        label = getattr(annotation.annotation_label, "text", None)
                        if not label or label_text.lower() not in label.lower():
                            continue
                    # Check raw_text filter
                    if raw_text_contains:
                        raw_text = annotation.raw_text or ""
                        if raw_text_contains.lower() not in raw_text.lower():
                            continue
                    filtered_results.append(result)
                results = filtered_results

            # Apply pagination
            paginated_results = results[offset : offset + limit]

        # Defensive select_related: Re-fetch annotations with explicit prefetching
        # to guard against changes in CoreAnnotationVectorStore implementation
        if paginated_results:
            from opencontractserver.annotations.models import Annotation

            annotation_ids = [r.annotation.id for r in paginated_results]
            annotations_by_id = {
                a.id: a
                for a in Annotation.objects.filter(
                    id__in=annotation_ids
                ).select_related("annotation_label", "document", "corpus")
            }
            # Update results with explicitly prefetched annotations
            for result in paginated_results:
                if result.annotation.id in annotations_by_id:
                    result.annotation = annotations_by_id[result.annotation.id]

        # Convert to GraphQL result types
        return [
            SemanticSearchResultType(
                annotation=result.annotation,
                similarity_score=result.similarity_score,
            )
            for result in paginated_results
        ]

    # MODERATION QUERIES ##################################################
    moderation_actions = DjangoFilterConnectionField(
        ModerationActionType,
        filterset_class=ModerationActionFilter,
        corpus_id=graphene.ID(),
        thread_id=graphene.ID(),
        moderator_id=graphene.ID(),
        action_types=graphene.List(graphene.String),
        automated_only=graphene.Boolean(),
        description="Query moderation action audit logs with filtering",
    )

    @login_required
    def resolve_moderation_actions(
        self,
        info,
        corpus_id=None,
        thread_id=None,
        moderator_id=None,
        action_types=None,
        automated_only=None,
        **kwargs,
    ):
        """
        Resolve moderation action audit logs with optional filters.

        Permissions:
            - Superusers: can see all actions
            - Corpus owners: can see actions on their corpuses
            - Moderators: can see actions on corpuses they moderate

        Performance:
            Uses select_related for conversation, corpus, message, and moderator
            to avoid N+1 queries. Results are ordered by created descending.

        Args:
            corpus_id: Filter to specific corpus (global ID)
            thread_id: Filter to specific thread/conversation (global ID)
            moderator_id: Filter to specific moderator (global ID)
            action_types: List of action types to include (e.g., ["lock_thread"])
            automated_only: If True, only show automated actions (no moderator)
        """
        user = info.context.user

        # Start with base queryset
        qs = ModerationAction.objects.select_related(
            "conversation",
            "conversation__chat_with_corpus",
            "message",
            "moderator",
        )

        # Filter by corpus ownership or moderator status (unless superuser)
        if not user.is_superuser:
            qs = qs.filter(
                Q(conversation__chat_with_corpus__creator=user)
                | Q(conversation__chat_with_corpus__moderators__user=user)
            ).distinct()

        # Apply optional filters
        if corpus_id:
            corpus_pk = from_global_id(corpus_id)[1]
            qs = qs.filter(conversation__chat_with_corpus_id=corpus_pk)

        if thread_id:
            thread_pk = from_global_id(thread_id)[1]
            qs = qs.filter(conversation_id=thread_pk)

        if moderator_id:
            moderator_pk = from_global_id(moderator_id)[1]
            qs = qs.filter(moderator_id=moderator_pk)

        if action_types:
            qs = qs.filter(action_type__in=action_types)

        if automated_only:
            qs = qs.filter(moderator__isnull=True)

        return qs.order_by("-created")

    moderation_action = graphene.Field(
        ModerationActionType,
        id=graphene.ID(required=True),
        description="Get a specific moderation action by ID",
    )

    @login_required
    def resolve_moderation_action(self, info, id):
        """
        Resolve a single moderation action by ID.

        Permissions:
            - Superusers: can see any action
            - Corpus owners/moderators: can see actions on their corpuses
            - Returns None if user lacks permission (prevents ID enumeration)

        Args:
            id: Global ID of the moderation action
        """
        user = info.context.user
        pk = from_global_id(id)[1]

        try:
            action = ModerationAction.objects.select_related(
                "conversation",
                "conversation__chat_with_corpus",
                "message",
                "moderator",
            ).get(pk=pk)

            # Check permission
            if not user.is_superuser:
                corpus = (
                    action.conversation.chat_with_corpus
                    if action.conversation
                    else None
                )
                if corpus:
                    is_owner = corpus.creator == user
                    is_moderator = corpus.moderators.filter(user=user).exists()
                    if not is_owner and not is_moderator:
                        return None

            return action
        except ModerationAction.DoesNotExist:
            return None

    moderation_metrics = graphene.Field(
        ModerationMetricsType,
        corpus_id=graphene.ID(required=True),
        time_range_hours=graphene.Int(default_value=24),
        description="Get moderation metrics for a corpus",
    )

    @login_required
    def resolve_moderation_metrics(self, info, corpus_id, time_range_hours=24):
        """
        Resolve aggregated moderation metrics for a corpus.

        Computes summary statistics of moderation activity including total actions,
        automated vs manual breakdown, per-type counts, and threshold alerts.

        Permissions:
            - Superusers: can see metrics for any corpus
            - Corpus owners/moderators: can see metrics for their corpuses

        Performance:
            Uses database aggregation (Count) to compute metrics efficiently
            without loading all action records into memory.

        Args:
            corpus_id: Global ID of the corpus
            time_range_hours: Number of hours to look back (default: 24)

        Returns:
            ModerationMetricsType with counts, rates, and threshold warnings
        """
        from django.db.models import Count
        from django.utils import timezone

        user = info.context.user
        corpus_pk = from_global_id(corpus_id)[1]

        try:
            corpus = Corpus.objects.get(pk=corpus_pk)
        except Corpus.DoesNotExist:
            return None

        # Check permission
        if not user.is_superuser:
            is_owner = corpus.creator == user
            is_moderator = corpus.moderators.filter(user=user).exists()
            if not is_owner and not is_moderator:
                return None

        end_time = timezone.now()
        start_time = end_time - timezone.timedelta(hours=time_range_hours)

        # Get actions in time range
        actions = ModerationAction.objects.filter(
            conversation__chat_with_corpus=corpus,
            created__gte=start_time,
            created__lte=end_time,
        )

        total = actions.count()
        automated = actions.filter(moderator__isnull=True).count()
        manual = total - automated

        # Actions by type
        by_type = dict(
            actions.values("action_type")
            .annotate(count=Count("id"))
            .values_list("action_type", "count")
        )

        # Hourly rate
        hourly_rate = total / time_range_hours if time_range_hours > 0 else 0

        # Threshold check for high activity warning
        from opencontractserver.constants.moderation import (
            MODERATION_HOURLY_RATE_THRESHOLD,
        )

        exceeded_types = [
            action_type
            for action_type, count in by_type.items()
            if count / time_range_hours > MODERATION_HOURLY_RATE_THRESHOLD
        ]

        return {
            "total_actions": total,
            "automated_actions": automated,
            "manual_actions": manual,
            "actions_by_type": by_type,
            "hourly_action_rate": round(hourly_rate, 2),
            "is_above_threshold": len(exceeded_types) > 0,
            "threshold_exceeded_types": exceeded_types,
            "time_range_hours": time_range_hours,
            "start_time": start_time,
            "end_time": end_time,
        }

    # DOCUMENT RELATIONSHIP RESOLVERS #####################################
    document_relationships = DjangoFilterConnectionField(
        DocumentRelationshipType,
        filterset_class=DocumentRelationshipFilter,
        corpus_id=graphene.ID(required=False),
        document_id=graphene.ID(required=False),
        # Higher limit for Table of Contents which needs full hierarchy
        max_limit=500,
    )

    @login_required
    def resolve_document_relationships(self, info, **kwargs):
        """
        Resolve document relationships with proper permission filtering.
        Uses DocumentRelationshipQueryOptimizer for consistent eager loading.
        """
        user = info.context.user

        # Parse optional filters
        corpus_id = kwargs.get("corpus_id")
        corpus_pk = int(from_global_id(corpus_id)[1]) if corpus_id else None

        document_id = kwargs.get("document_id")
        doc_pk = int(from_global_id(document_id)[1]) if document_id else None

        # Use optimizer for visibility and eager loading
        # Pass context for request-level caching of visible IDs
        if doc_pk:
            # Get relationships for specific document
            queryset = (
                DocumentRelationshipQueryOptimizer.get_relationships_for_document(
                    user=user,
                    document_id=doc_pk,
                    corpus_id=corpus_pk,
                    context=info.context,
                )
            )
        else:
            # Get all visible relationships with optional corpus filter
            queryset = DocumentRelationshipQueryOptimizer.get_visible_relationships(
                user=user,
                corpus_id=corpus_pk,
                context=info.context,
            )

        return queryset.distinct().order_by("-created")

    document_relationship = relay.Node.Field(DocumentRelationshipType)

    @login_required
    def resolve_document_relationship(self, info, **kwargs):
        """
        Resolve a single document relationship by ID.
        Uses optimizer for IDOR-safe fetching with proper eager loading.
        """
        django_pk = from_global_id(kwargs.get("id", None))[1]
        result = DocumentRelationshipQueryOptimizer.get_relationship_by_id(
            user=info.context.user,
            relationship_id=int(django_pk),
        )
        if result is None:
            raise DocumentRelationship.DoesNotExist()
        return result

    # Also add a bulk resolver similar to bulk_doc_relationships_in_corpus
    bulk_doc_relationships = graphene.Field(
        graphene.List(DocumentRelationshipType),
        corpus_id=graphene.ID(required=False),
        document_id=graphene.ID(required=True),
        relationship_type=graphene.String(required=False),
    )

    @login_required
    def resolve_bulk_doc_relationships(self, info, document_id, **kwargs):
        """
        Bulk resolver for document relationships involving a specific document.
        Uses DocumentRelationshipQueryOptimizer for proper eager loading.
        """
        user = info.context.user

        # Parse document_id (required)
        doc_pk = int(from_global_id(document_id)[1])

        # Parse optional corpus filter
        corpus_id = kwargs.get("corpus_id")
        corpus_pk = int(from_global_id(corpus_id)[1]) if corpus_id else None

        # Use optimizer for visibility and eager loading
        queryset = DocumentRelationshipQueryOptimizer.get_relationships_for_document(
            user=user,
            document_id=doc_pk,
            corpus_id=corpus_pk,
        )

        # Apply optional relationship_type filter
        relationship_type = kwargs.get("relationship_type")
        if relationship_type:
            queryset = queryset.filter(relationship_type=relationship_type)

        return queryset.distinct().order_by("-created")

    # NOTE RESOLVERS #####################################
    notes = DjangoConnectionField(
        NoteType,
        title_contains=graphene.String(),
        content_contains=graphene.String(),
        document_id=graphene.ID(),
        annotation_id=graphene.ID(),
        order_by=graphene.String(),
    )

    @login_required
    def resolve_notes(self, info, **kwargs):
        # Base filtering for user permissions
        queryset = Note.objects.visible_to_user(info.context.user)

        # Filter by title
        title_contains = kwargs.get("title_contains")
        if title_contains:
            logger.info(f"Filtering by title containing: {title_contains}")
            queryset = queryset.filter(title__contains=title_contains)

        # Filter by content
        content_contains = kwargs.get("content_contains")
        if content_contains:
            logger.info(f"Filtering by content containing: {content_contains}")
            queryset = queryset.filter(content__contains=content_contains)

        # Filter by document_id
        document_id = kwargs.get("document_id")
        if document_id:
            logger.info(f"Filtering by document_id: {document_id}")
            django_pk = from_global_id(document_id)[1]
            queryset = queryset.filter(document_id=django_pk)

        # Filter by annotation_id
        annotation_id = kwargs.get("annotation_id")
        if annotation_id:
            logger.info(f"Filtering by annotation_id: {annotation_id}")
            django_pk = from_global_id(annotation_id)[1]
            queryset = queryset.filter(annotation_id=django_pk)

        # Ordering
        order_by = kwargs.get("order_by")
        if order_by:
            logger.info(f"Ordering by: {order_by}")
            queryset = queryset.order_by(order_by)
        else:
            logger.info("Ordering by default: -modified")
            queryset = queryset.order_by("-modified")

        logger.info(f"Final queryset: {queryset}")
        return queryset

    note = relay.Node.Field(NoteType)

    @login_required
    def resolve_note(self, info, **kwargs):
        django_pk = from_global_id(kwargs.get("id", None))[1]
        return Note.objects.visible_to_user(info.context.user).get(id=django_pk)

    chat_messages = graphene.Field(
        graphene.List(MessageType),
        conversation_id=graphene.ID(required=True),
        order_by=graphene.String(required=False),
    )

    @login_required
    def resolve_chat_messages(
        self,
        info: graphene.ResolveInfo,
        conversation_id: Optional[str],
        order_by: Optional[str] = None,
        **kwargs,
    ):
        """
        Resolver for fetching ChatMessage objects with optional filters.

        Args:
            info (graphene.ResolveInfo): GraphQL resolve info
            conversation_id (Optional[str]): Global Relay ID for Conversation filter
            order_by (Optional[str]): Field to order by. Defaults to "-created_at"
                Supported fields: created_at, -created_at, msg_type, -msg_type,
                modified, -modified
            **kwargs: Additional filter arguments

        Returns:
            QuerySet[ChatMessage]: Filtered and ordered chat messages
        """
        queryset = ChatMessage.objects.visible_to_user(info.context.user)

        # Apply conversation filter if provided
        conversation_pk = from_global_id(conversation_id)[1]
        queryset = queryset.filter(conversation_id=conversation_pk)

        # Apply ordering
        valid_order_fields = {
            "created_at",
            "-created_at",
            "msg_type",
            "-msg_type",
            "modified",
            "-modified",
        }

        order_field = order_by if order_by in valid_order_fields else "created_at"
        queryset = queryset.order_by(order_field)

        return queryset

    chat_message = relay.Node.Field(MessageType)

    # User messages query for profile/activity feeds
    user_messages = graphene.Field(
        graphene.List(MessageType),
        creator_id=graphene.ID(required=True),
        first=graphene.Int(required=False, default_value=10),
        msg_type=graphene.String(required=False),
        order_by=graphene.String(required=False),
        description="Get messages created by a specific user, with optional filtering and pagination",
    )

    @login_required
    def resolve_user_messages(
        self,
        info: graphene.ResolveInfo,
        creator_id: str,
        first: int = 10,
        msg_type: Optional[str] = None,
        order_by: Optional[str] = None,
        **kwargs,
    ):
        """
        Resolver for fetching ChatMessage objects by creator for user profiles.

        Args:
            info (graphene.ResolveInfo): GraphQL resolve info
            creator_id (str): Global Relay ID for User
            first (int): Number of messages to return (default 10)
            msg_type (Optional[str]): Filter by message type (HUMAN, AI_AGENT, SYSTEM)
            order_by (Optional[str]): Field to order by. Defaults to "-created"

        Returns:
            QuerySet[ChatMessage]: Filtered and ordered chat messages
        """
        queryset = (
            ChatMessage.objects.visible_to_user(info.context.user)
            .select_related("conversation", "creator")
            .prefetch_related("votes")
        )

        # Apply creator filter
        creator_pk = from_global_id(creator_id)[1]
        queryset = queryset.filter(creator_id=creator_pk)

        # Apply msg_type filter if provided
        if msg_type:
            # Validate msg_type against MessageTypeChoices
            valid_types = [choice.value for choice in MessageTypeChoices]
            if msg_type in valid_types:
                queryset = queryset.filter(msg_type=msg_type)

        # Apply ordering
        valid_order_fields = {
            "created",
            "-created",
            "modified",
            "-modified",
        }

        order_field = order_by if order_by in valid_order_fields else "-created"
        queryset = queryset.order_by(order_field)

        # Limit results
        return queryset[:first]

    @login_required
    def resolve_chat_message(self, info: graphene.ResolveInfo, **kwargs) -> ChatMessage:
        """
        Resolver for fetching a single ChatMessage by global Relay ID.

        Args:
            info (graphene.ResolveInfo): GraphQL resolve info.
            **kwargs: Any additional keyword arguments passed from the GraphQL query.

        Returns:
            ChatMessage: A single ChatMessage object visible to the current user.

        Raises:
            ChatMessage.DoesNotExist: If the object doesn't exist or is inaccessible.
        """
        django_pk = from_global_id(kwargs.get("id"))[1]
        return ChatMessage.objects.visible_to_user(info.context.user).get(pk=django_pk)

    corpus_actions = DjangoConnectionField(
        CorpusActionType,
        corpus_id=graphene.ID(required=False),
        trigger=graphene.String(required=False),
        disabled=graphene.Boolean(required=False),
    )

    @login_required
    def resolve_corpus_actions(self, info, **kwargs):
        """
        Resolver for corpus_actions that returns actions visible to the current user.
        Can be filtered by corpus_id, trigger type, and disabled status.
        """
        user = info.context.user
        queryset = CorpusAction.objects.visible_to_user(user)

        # Filter by corpus if provided
        corpus_id = kwargs.get("corpus_id")
        if corpus_id:
            corpus_pk = from_global_id(corpus_id)[1]
            queryset = queryset.filter(corpus_id=corpus_pk)

        # Filter by trigger type if provided
        trigger = kwargs.get("trigger")
        if trigger:
            queryset = queryset.filter(trigger=trigger)

        # Filter by disabled status if provided
        disabled = kwargs.get("disabled")
        if disabled is not None:
            queryset = queryset.filter(disabled=disabled)

        return queryset.order_by("-created")

    agent_action_results = DjangoConnectionField(
        AgentActionResultType,
        corpus_action_id=graphene.ID(required=False),
        document_id=graphene.ID(required=False),
        status=graphene.String(required=False),
    )

    @login_required
    def resolve_agent_action_results(self, info, **kwargs):
        """
        Resolver for agent_action_results that returns results visible to the current user.
        Can be filtered by corpus_action_id, document_id, and status.
        """
        from opencontractserver.agents.models import AgentActionResult
        from opencontractserver.corpuses.models import CorpusAction

        user = info.context.user
        queryset = AgentActionResult.objects.visible_to_user(user)

        # Filter by corpus_action if provided (with access check)
        corpus_action_id = kwargs.get("corpus_action_id")
        if corpus_action_id:
            corpus_action_pk = from_global_id(corpus_action_id)[1]
            # Defense-in-depth: verify user has access to this corpus action
            if (
                not CorpusAction.objects.visible_to_user(user)
                .filter(pk=corpus_action_pk)
                .exists()
            ):
                return queryset.none()
            queryset = queryset.filter(corpus_action_id=corpus_action_pk)

        # Filter by document if provided
        document_id = kwargs.get("document_id")
        if document_id:
            document_pk = from_global_id(document_id)[1]
            queryset = queryset.filter(document_id=document_pk)

        # Filter by status if provided
        status = kwargs.get("status")
        if status:
            queryset = queryset.filter(status=status)

        return queryset.order_by("-created")

    # CORPUS ACTION EXECUTION QUERIES ##############################################
    corpus_action_executions = DjangoConnectionField(
        CorpusActionExecutionType,
        corpus_id=graphene.ID(required=False),
        document_id=graphene.ID(required=False),
        corpus_action_id=graphene.ID(required=False),
        status=graphene.String(required=False),
        action_type=graphene.String(required=False),
        since=graphene.DateTime(required=False),
    )

    @login_required
    def resolve_corpus_action_executions(self, info, **kwargs):
        """
        Resolver for corpus_action_executions that returns executions visible to
        the current user.

        Can be filtered by corpus_id, document_id, corpus_action_id, status,
        action_type, and since (datetime).
        """
        from opencontractserver.corpuses.models import Corpus, CorpusActionExecution
        from opencontractserver.documents.models import Document

        user = info.context.user
        queryset = CorpusActionExecution.objects.visible_to_user(user)

        # Filter by corpus if provided (with access check)
        corpus_id = kwargs.get("corpus_id")
        if corpus_id:
            corpus_pk = from_global_id(corpus_id)[1]
            # Defense-in-depth: verify user has access to this corpus
            if not Corpus.objects.visible_to_user(user).filter(pk=corpus_pk).exists():
                return queryset.none()
            queryset = queryset.for_corpus(corpus_pk)

        # Filter by document if provided (with access check)
        document_id = kwargs.get("document_id")
        if document_id:
            document_pk = from_global_id(document_id)[1]
            # Defense-in-depth: verify user has access to this document
            if (
                not Document.objects.visible_to_user(user)
                .filter(pk=document_pk)
                .exists()
            ):
                return queryset.none()
            queryset = queryset.for_document(document_pk)

        # Filter by corpus_action if provided (with access check)
        corpus_action_id = kwargs.get("corpus_action_id")
        if corpus_action_id:
            from opencontractserver.corpuses.models import CorpusAction

            corpus_action_pk = from_global_id(corpus_action_id)[1]
            # Defense-in-depth: verify user has access to this corpus action
            if (
                not CorpusAction.objects.visible_to_user(user)
                .filter(pk=corpus_action_pk)
                .exists()
            ):
                return queryset.none()
            queryset = queryset.filter(corpus_action_id=corpus_action_pk)

        # Filter by status if provided
        status = kwargs.get("status")
        if status:
            queryset = queryset.filter(status=status)

        # Filter by action_type if provided
        action_type = kwargs.get("action_type")
        if action_type:
            queryset = queryset.by_type(action_type)

        # Filter by since datetime if provided
        since = kwargs.get("since")
        if since:
            queryset = queryset.filter(queued_at__gte=since)

        return queryset.select_related("corpus_action", "document", "corpus").order_by(
            "-queued_at"
        )

    corpus_action_trail_stats = graphene.Field(
        CorpusActionTrailStatsType,
        corpus_id=graphene.ID(required=True),
        since=graphene.DateTime(required=False),
    )

    @login_required
    def resolve_corpus_action_trail_stats(self, info, corpus_id, since=None):
        """
        Resolver for corpus_action_trail_stats that returns aggregated statistics
        for corpus action executions.
        """
        from django.db.models import Avg, Count, F, Q

        from opencontractserver.corpuses.models import Corpus, CorpusActionExecution

        user = info.context.user
        corpus_pk = from_global_id(corpus_id)[1]

        # Defense-in-depth: verify user has access to this corpus
        if not Corpus.objects.visible_to_user(user).filter(pk=corpus_pk).exists():
            return CorpusActionTrailStatsType(
                total_executions=0,
                completed=0,
                failed=0,
                running=0,
                queued=0,
                skipped=0,
                avg_duration_seconds=None,
                fieldset_count=0,
                analyzer_count=0,
                agent_count=0,
            )

        queryset = CorpusActionExecution.objects.visible_to_user(user)
        queryset = queryset.for_corpus(corpus_pk)

        if since:
            queryset = queryset.filter(queued_at__gte=since)

        stats = queryset.aggregate(
            total=Count("id"),
            completed=Count("id", filter=Q(status="completed")),
            failed=Count("id", filter=Q(status="failed")),
            running=Count("id", filter=Q(status="running")),
            queued=Count("id", filter=Q(status="queued")),
            skipped=Count("id", filter=Q(status="skipped")),
            avg_duration=Avg(
                F("completed_at") - F("started_at"),
                filter=Q(completed_at__isnull=False, started_at__isnull=False),
            ),
            fieldset_count=Count("id", filter=Q(action_type="fieldset")),
            analyzer_count=Count("id", filter=Q(action_type="analyzer")),
            agent_count=Count("id", filter=Q(action_type="agent")),
        )

        return CorpusActionTrailStatsType(
            total_executions=stats["total"],
            completed=stats["completed"],
            failed=stats["failed"],
            running=stats["running"],
            queued=stats["queued"],
            skipped=stats["skipped"],
            avg_duration_seconds=(
                stats["avg_duration"].total_seconds() if stats["avg_duration"] else None
            ),
            fieldset_count=stats["fieldset_count"],
            analyzer_count=stats["analyzer_count"],
            agent_count=stats["agent_count"],
        )

    conversation = relay.Node.Field(ConversationType)

    # BULK DOCUMENT UPLOAD STATUS QUERY ###########################################
    bulk_document_upload_status = graphene.Field(
        BulkDocumentUploadStatusType,
        job_id=graphene.String(required=True),
        description="Check the status of a bulk document upload job by job ID",
    )

    @login_required
    def resolve_bulk_document_upload_status(self, info, job_id):
        """
        Resolver for the bulk_document_upload_status query.

        This queries Redis for the status of a bulk document upload job.
        The status is stored as a result in Celery's backend.

        Args:
            info: GraphQL execution info
            job_id: The unique identifier for the upload job

        Returns:
            BulkDocumentUploadStatusType with the current job status
        """
        from config import celery_app

        try:
            # Try to get the task result from Celery
            async_result = celery_app.AsyncResult(job_id)

            # Special handling for tests with CELERY_TASK_ALWAYS_EAGER=True
            if settings.CELERY_TASK_ALWAYS_EAGER:
                logger.info(
                    f"CELERY_TASK_ALWAYS_EAGER is True, handling task {job_id} directly"
                )
                try:
                    if async_result.ready() and async_result.successful():
                        # In eager mode, even with task_store_eager_result, sometimes the result
                        # doesn't properly propagate to the backend. For tests, we'll assume completion.
                        result = async_result.get()
                        logger.info(f"Direct task result in eager mode: {result}")
                        return BulkDocumentUploadStatusType(
                            job_id=job_id,
                            success=result.get("success", True),
                            total_files=result.get("total_files", 0),
                            processed_files=result.get("processed_files", 0),
                            skipped_files=result.get("skipped_files", 0),
                            error_files=result.get("error_files", 0),
                            document_ids=result.get("document_ids", []),
                            errors=result.get("errors", []),
                            completed=result.get(
                                "completed", True
                            ),  # Use the passed completed value if available
                        )
                except Exception as e:
                    logger.info(f"Exception getting eager task result: {e}")
                    # Continue with normal flow

            if async_result.ready():
                # Task is finished
                if async_result.successful():
                    result = async_result.get()
                    # Ensure it has the right structure
                    return BulkDocumentUploadStatusType(
                        job_id=job_id,
                        success=result.get("success", False),
                        total_files=result.get("total_files", 0),
                        processed_files=result.get("processed_files", 0),
                        skipped_files=result.get("skipped_files", 0),
                        error_files=result.get("error_files", 0),
                        document_ids=result.get("document_ids", []),
                        errors=result.get("errors", []),
                        completed=result.get(
                            "completed", True
                        ),  # Use the completed field from result if available
                    )
                else:
                    # Task failed
                    return BulkDocumentUploadStatusType(
                        job_id=job_id,
                        success=False,
                        completed=True,
                        errors=["Task failed with an exception"],
                    )
            else:
                # Task is still running
                return BulkDocumentUploadStatusType(
                    job_id=job_id,
                    success=False,
                    completed=False,
                    errors=["Task is still running"],
                )

        except Exception as e:
            logger.error(f"Error checking bulk upload status: {str(e)}")
            return BulkDocumentUploadStatusType(
                job_id=job_id,
                success=False,
                completed=False,
                errors=[f"Error checking status: {str(e)}"],
            )

    # NEW METADATA QUERIES (Column/Datacell based) ################################
    corpus_metadata_columns = graphene.List(
        ColumnType,
        corpus_id=graphene.ID(required=True),
        description="Get metadata columns for a corpus",
    )

    document_metadata_datacells = graphene.List(
        DatacellType,
        document_id=graphene.ID(required=True),
        corpus_id=graphene.ID(required=True),
        description="Get metadata datacells for a document in a corpus",
    )

    metadata_completion_status_v2 = graphene.Field(
        MetadataCompletionStatusType,
        document_id=graphene.ID(required=True),
        corpus_id=graphene.ID(required=True),
        description="Get metadata completion status for a document using column/datacell system",
    )

    documents_metadata_datacells_batch = graphene.List(
        DocumentMetadataResultType,
        document_ids=graphene.List(graphene.ID, required=True),
        corpus_id=graphene.ID(required=True),
        description="Get metadata datacells for multiple documents in a single query (batch)",
    )

    def resolve_corpus_metadata_columns(self, info, corpus_id):
        """Get metadata columns for a corpus using MetadataQueryOptimizer."""
        from opencontractserver.extracts.query_optimizer import MetadataQueryOptimizer

        user = info.context.user
        local_corpus_id = int(from_global_id(corpus_id)[1])

        return MetadataQueryOptimizer.get_corpus_metadata_columns(
            user, local_corpus_id, manual_only=True
        )

    def resolve_document_metadata_datacells(self, info, document_id, corpus_id):
        """Get metadata datacells for a document using MetadataQueryOptimizer."""
        from opencontractserver.extracts.query_optimizer import MetadataQueryOptimizer

        user = info.context.user
        local_doc_id = int(from_global_id(document_id)[1])
        local_corpus_id = int(from_global_id(corpus_id)[1])

        return MetadataQueryOptimizer.get_document_metadata(
            user, local_doc_id, local_corpus_id, manual_only=True
        )

    def resolve_metadata_completion_status_v2(self, info, document_id, corpus_id):
        """Get metadata completion status using MetadataQueryOptimizer."""
        from opencontractserver.extracts.query_optimizer import MetadataQueryOptimizer

        user = info.context.user
        local_doc_id = int(from_global_id(document_id)[1])
        local_corpus_id = int(from_global_id(corpus_id)[1])

        return MetadataQueryOptimizer.get_metadata_completion_status(
            user, local_doc_id, local_corpus_id
        )

    def resolve_documents_metadata_datacells_batch(self, info, document_ids, corpus_id):
        """
        Get metadata datacells for multiple documents using MetadataQueryOptimizer.

        This batch query solves the N+1 problem when loading metadata for a grid view.
        Uses the centralized MetadataQueryOptimizer which applies proper permission
        filtering: Effective Permission = MIN(document_permission, corpus_permission)
        """
        from opencontractserver.extracts.query_optimizer import MetadataQueryOptimizer

        user = info.context.user
        local_corpus_id = int(from_global_id(corpus_id)[1])

        # Convert global IDs to local IDs (single pass)
        local_doc_ids = []
        local_id_by_global = {}  # global_id -> local_id
        for global_id in document_ids:
            _, local_id = from_global_id(global_id)
            local_id_int = int(local_id)
            local_doc_ids.append(local_id_int)
            local_id_by_global[global_id] = local_id_int

        # Use optimizer to get batch metadata with proper permissions
        datacells_by_doc = MetadataQueryOptimizer.get_documents_metadata_batch(
            user,
            local_doc_ids,
            local_corpus_id,
            manual_only=True,
            context=info.context,
        )

        # Build response - maintain order of requested document_ids
        # The optimizer returns a dict with keys for all readable documents,
        # so we only include documents the user has permission to read
        results = []
        for global_id in document_ids:
            local_id = local_id_by_global[global_id]

            # Only include documents that are in the result (user has permission)
            if local_id in datacells_by_doc:
                results.append(
                    {
                        "document_id": global_id,
                        "datacells": datacells_by_doc[local_id],
                    }
                )

        return results

    # BADGE RESOLVERS ####################################
    badges = DjangoFilterConnectionField(BadgeType, filterset_class=BadgeFilter)
    badge = relay.Node.Field(BadgeType)

    def resolve_badges(self, info, **kwargs):
        """Resolve badges visible to the user."""
        return Badge.objects.visible_to_user(info.context.user).select_related(
            "creator", "corpus"
        )

    def resolve_badge(self, info, **kwargs):
        """Resolve a single badge by ID."""
        django_pk = from_global_id(kwargs.get("id", None))[1]
        return Badge.objects.visible_to_user(info.context.user).get(id=django_pk)

    user_badges = DjangoFilterConnectionField(
        UserBadgeType, filterset_class=UserBadgeFilter
    )
    user_badge = relay.Node.Field(UserBadgeType)

    def resolve_user_badges(self, info, **kwargs):
        """
        Resolve user badge awards with profile privacy filtering.

        SECURITY: Badge visibility follows the recipient's profile visibility.
        Badges are visible if:
        - Recipient's profile is public
        - Requesting user shares corpus membership with recipient (> READ permission)
        - It's the requesting user's own badges
        - For corpus-specific badges: user has access to that corpus
        """
        from opencontractserver.badges.query_optimizer import BadgeQueryOptimizer

        return BadgeQueryOptimizer.get_visible_user_badges(info.context.user)

    def resolve_user_badge(self, info, **kwargs):
        """
        Resolve a single user badge by ID with visibility check and IDOR protection.

        SECURITY: Returns same error whether badge doesn't exist or user lacks permission.
        This prevents enumeration attacks.
        """
        from opencontractserver.badges.query_optimizer import BadgeQueryOptimizer

        django_pk = from_global_id(kwargs.get("id", None))[1]

        has_permission, user_badge = BadgeQueryOptimizer.check_user_badge_visibility(
            info.context.user, django_pk
        )

        if not has_permission:
            # Same error whether doesn't exist or no permission (IDOR protection)
            raise GraphQLError("User badge not found")

        return user_badge

    badge_criteria_types = graphene.List(
        CriteriaTypeDefinitionType,
        scope=graphene.String(
            required=False,
            description="Filter by scope: 'global', 'corpus', or 'both'",
        ),
        description="Get available badge criteria types from the registry",
    )

    def resolve_badge_criteria_types(self, info, scope=None):
        """
        Resolve available badge criteria types from the registry.

        Args:
            info: GraphQL resolve info
            scope: Optional scope filter ('global', 'corpus', or 'both')

        Returns:
            List of criteria type definitions with their field schemas
        """
        # Get criteria types from registry
        if scope:
            criteria_types = BadgeCriteriaRegistry.for_scope(scope)
        else:
            criteria_types = BadgeCriteriaRegistry.all()

        # Convert dataclass instances to dicts for GraphQL
        return [
            {
                "type_id": ct.type_id,
                "name": ct.name,
                "description": ct.description,
                "scope": ct.scope,
                "fields": [
                    {
                        "name": f.name,
                        "label": f.label,
                        "field_type": f.field_type,
                        "required": f.required,
                        "description": f.description,
                        "min_value": f.min_value,
                        "max_value": f.max_value,
                        "allowed_values": f.allowed_values,
                    }
                    for f in ct.fields
                ],
                "implemented": ct.implemented,
            }
            for ct in criteria_types
        ]

    # AGENT CONFIGURATION QUERIES ########################################
    agents = DjangoFilterConnectionField(
        AgentConfigurationType, filterset_class=AgentConfigurationFilter
    )
    # Alias for frontend compatibility
    agent_configurations = DjangoFilterConnectionField(
        AgentConfigurationType, filterset_class=AgentConfigurationFilter
    )
    agent = relay.Node.Field(AgentConfigurationType)

    search_agents_for_mention = DjangoConnectionField(
        AgentConfigurationType,
        text_search=graphene.String(
            description="Search query to find agents by name, slug, or description"
        ),
        corpus_id=graphene.ID(
            description="Corpus ID to scope agent search (includes global + corpus agents)"
        ),
    )

    def resolve_agents(self, info, **kwargs):
        """Resolve agent configurations visible to the user."""
        from opencontractserver.agents.models import AgentConfiguration

        return AgentConfiguration.objects.visible_to_user(
            info.context.user
        ).select_related("creator", "corpus")

    def resolve_agent_configurations(self, info, **kwargs):
        """Alias for resolve_agents - frontend compatibility."""
        from opencontractserver.agents.models import AgentConfiguration

        return AgentConfiguration.objects.visible_to_user(
            info.context.user
        ).select_related("creator", "corpus")

    def resolve_agent(self, info, **kwargs):
        """Resolve a single agent configuration by ID."""
        from opencontractserver.agents.models import AgentConfiguration

        django_pk = from_global_id(kwargs.get("id", None))[1]
        return AgentConfiguration.objects.visible_to_user(info.context.user).get(
            id=django_pk
        )

    @graphql_ratelimit_dynamic(get_rate=get_user_tier_rate("READ_LIGHT"))
    def resolve_search_agents_for_mention(
        self, info, text_search=None, corpus_id=None, **kwargs
    ):
        """
        Search agents for @ mention autocomplete.

        Returns:
        - All active global agents (GLOBAL scope)
        - Corpus-specific agents for the provided corpus (if user has access)

        SECURITY: Filters by visibility - users only see agents they can mention.
        Anonymous users cannot search agents.
        """
        from django.db.models import Q

        from opencontractserver.agents.models import AgentConfiguration

        user = info.context.user

        # Anonymous users cannot mention agents
        if not user or not user.is_authenticated:
            return AgentConfiguration.objects.none()

        # Build base queryset using visible_to_user (respects permissions)
        qs = AgentConfiguration.objects.visible_to_user(user).filter(is_active=True)

        # If corpus_id provided, filter to global + that corpus only
        if corpus_id:
            corpus_pk = from_global_id(corpus_id)[1]
            qs = qs.filter(Q(scope="GLOBAL") | Q(scope="CORPUS", corpus_id=corpus_pk))

        # Apply text search across name, slug, and description
        if text_search:
            qs = qs.filter(
                Q(name__icontains=text_search)
                | Q(description__icontains=text_search)
                | Q(slug__icontains=text_search)
            )

        # Order: Global first, then corpus-specific, then alphabetically by name
        return qs.select_related("creator", "corpus").order_by("scope", "name")

    # AGENT TOOLS QUERIES ########################################
    available_tools = graphene.List(
        graphene.NonNull(AvailableToolType),
        category=graphene.String(
            description="Filter by tool category (search, document, corpus, notes, annotations, coordination)"
        ),
        description="Get all available tools that can be assigned to agents",
    )

    available_tool_categories = graphene.List(
        graphene.NonNull(graphene.String),
        description="Get all available tool categories",
    )

    def resolve_available_tools(self, info, category=None, **kwargs):
        """
        Resolve available tools for agent configuration.

        This returns the list of tools that can be assigned to agents,
        optionally filtered by category.
        """
        from opencontractserver.llms.tools.tool_registry import (
            get_all_tools,
            get_tools_by_category,
        )

        if category:
            tools = get_tools_by_category(category)
        else:
            tools = get_all_tools()

        return tools

    def resolve_available_tool_categories(self, info, **kwargs):
        """Resolve all available tool categories."""
        from opencontractserver.llms.tools.tool_registry import ToolCategory

        return [cat.value for cat in ToolCategory]

    # NOTIFICATION QUERIES ########################################
    notifications = DjangoFilterConnectionField(
        NotificationType,
        description="Get user's notifications (paginated and filterable)",
    )
    notification = relay.Node.Field(NotificationType)

    unread_notification_count = graphene.Int(
        description="Get count of unread notifications for the current user"
    )

    def resolve_notifications(self, info, **kwargs):
        """
        Resolve notifications for the current user.

        Filters notifications to only show those belonging to the current user.
        Supports filtering by is_read and notification_type via DjangoFilterConnectionField.
        """
        user = info.context.user
        if not user or not user.is_authenticated:
            return Notification.objects.none()

        return (
            Notification.objects.filter(recipient=user)
            .select_related("actor", "message", "conversation", "recipient")
            .order_by("-created_at")
        )

    def resolve_notification(self, info, **kwargs):
        """
        Resolve a single notification by ID.

        Ensures user can only access their own notifications.
        Returns consistent error to prevent IDOR enumeration.
        """
        user = info.context.user
        if not user or not user.is_authenticated:
            raise GraphQLError("Notification not found")

        django_pk = from_global_id(kwargs.get("id", None))[1]

        # Use try/except to catch DoesNotExist and return same error
        # This prevents enumeration of valid notification IDs
        try:
            notification = Notification.objects.get(id=django_pk, recipient=user)
        except Notification.DoesNotExist:
            # Same error whether notification doesn't exist or belongs to another user
            raise GraphQLError("Notification not found")

        return notification

    def resolve_unread_notification_count(self, info):
        """Get count of unread notifications for the current user."""
        user = info.context.user
        if not user or not user.is_authenticated:
            return 0

        return Notification.objects.filter(recipient=user, is_read=False).count()

    # ENGAGEMENT METRICS & LEADERBOARD QUERIES (Epic #565) ########
    corpus_leaderboard = graphene.List(
        UserType,
        corpus_id=graphene.ID(required=True),
        limit=graphene.Int(default_value=10),
        description="Get top contributors for a specific corpus by reputation",
    )
    global_leaderboard = graphene.List(
        UserType,
        limit=graphene.Int(default_value=10),
        description="Get top contributors globally by reputation",
    )

    def resolve_corpus_leaderboard(self, info, corpus_id, limit=10):
        """
        Get top contributors for a corpus by reputation.

        Returns users ordered by corpus-specific reputation score.
        Requires read access to the corpus.

        Epic: #565 - Corpus Engagement Metrics & Analytics
        Issue: #568 - Create GraphQL queries for engagement metrics and leaderboards
        """
        from opencontractserver.conversations.models import UserReputation

        try:
            # Get corpus PK from global ID
            _, corpus_pk = from_global_id(corpus_id)

            # Check if user has access to this corpus
            Corpus.objects.visible_to_user(info.context.user).get(id=corpus_pk)

            # Get top users by reputation for this corpus
            # Prefetch user badges to avoid N+1 queries
            top_reputations = (
                UserReputation.objects.filter(corpus_id=corpus_pk)
                .select_related("user")
                .prefetch_related("user__badges__badge")
                .order_by("-reputation_score")[:limit]
            )

            # Return user objects (badges are already prefetched)
            return [rep.user for rep in top_reputations]

        except Corpus.DoesNotExist:
            raise GraphQLError("Corpus not found or access denied")
        except Exception as e:
            logger.error(f"Error resolving corpus leaderboard: {e}")
            return []

    def resolve_global_leaderboard(self, info, limit=10):
        """
        Get top contributors globally by reputation.

        Returns users ordered by global reputation score.
        Attaches _reputation_global to each user to avoid N+1 queries
        when resolving reputationGlobal on UserType.

        Epic: #565 - Corpus Engagement Metrics & Analytics
        Issue: #568 - Create GraphQL queries for engagement metrics and leaderboards
        """
        from opencontractserver.conversations.models import UserReputation

        # Get top users by global reputation (corpus__isnull=True)
        # Prefetch user badges to avoid N+1 queries when frontend requests userBadges
        top_reputations = (
            UserReputation.objects.filter(corpus__isnull=True)
            .select_related("user")
            .prefetch_related("user__badges__badge")
            .order_by("-reputation_score")[:limit]
        )

        # Attach reputation score to user objects to avoid N+1 queries
        users = []
        for rep in top_reputations:
            rep.user._reputation_global = rep.reputation_score
            users.append(rep.user)
        return users

    # LEADERBOARD QUERIES (Issue #613) ###################
    leaderboard = graphene.Field(
        LeaderboardType,
        metric=graphene.Argument(LeaderboardMetricEnum, required=True),
        scope=graphene.Argument(LeaderboardScopeEnum, default_value="all_time"),
        corpus_id=graphene.ID(),
        limit=graphene.Int(default_value=25),
        description="Get leaderboard for a specific metric and scope",
    )
    community_stats = graphene.Field(
        CommunityStatsType,
        corpus_id=graphene.ID(),
        description="Get overall community engagement statistics",
    )

    def resolve_leaderboard(
        self, info, metric, scope="all_time", corpus_id=None, limit=25
    ):
        """
        Get leaderboard for a specific metric and scope.

        Issue: #613 - Create leaderboard and community stats dashboard
        Epic: #572 - Social Features Epic

        Args:
            metric: The metric to rank by (BADGES, MESSAGES, THREADS, ANNOTATIONS, REPUTATION)
            scope: Time period (ALL_TIME, MONTHLY, WEEKLY)
            corpus_id: Optional corpus ID for corpus-specific leaderboards
            limit: Maximum number of entries to return (default 25)

        Returns:
            LeaderboardType with ranked entries
        """
        from datetime import timedelta

        from django.contrib.auth import get_user_model
        from django.db.models import Count, Q
        from django.utils import timezone

        from opencontractserver.annotations.models import Annotation

        User = get_user_model()

        # Calculate date cutoff based on scope
        cutoff_date = None
        if scope == "weekly":
            cutoff_date = timezone.now() - timedelta(days=7)
        elif scope == "monthly":
            cutoff_date = timezone.now() - timedelta(days=30)

        # Get corpus if specified
        corpus_django_pk = None
        if corpus_id:
            try:
                _, corpus_django_pk = from_global_id(corpus_id)
                # Verify user has access to this corpus
                Corpus.objects.visible_to_user(info.context.user).get(
                    id=corpus_django_pk
                )
            except Corpus.DoesNotExist:
                raise GraphQLError("Corpus not found or access denied")

        # Get visible users (respect privacy settings)
        users = User.objects.visible_to_user(info.context.user).filter(is_active=True)

        # Build query based on metric
        entries = []
        current_user = info.context.user

        if metric == "badges":
            # Count badges per user (UserBadge imported at top level)
            badge_query = UserBadge.objects.filter(user__in=users)
            if cutoff_date:
                badge_query = badge_query.filter(awarded_at__gte=cutoff_date)
            if corpus_django_pk:
                badge_query = badge_query.filter(
                    Q(corpus_id=corpus_django_pk) | Q(corpus__isnull=True)
                )

            user_badge_counts = (
                badge_query.values("user")
                .annotate(count=Count("id"))
                .order_by("-count")[:limit]
            )

            for idx, item in enumerate(user_badge_counts, start=1):
                user = User.objects.get(id=item["user"])
                entries.append(
                    LeaderboardEntryType(
                        user=user,
                        rank=idx,
                        score=item["count"],
                        badge_count=item["count"],
                    )
                )

        elif metric == "messages":
            # Count messages per user
            # Filter by visible conversations since ChatMessage doesn't inherit conversation visibility
            visible_conversations = Conversation.objects.visible_to_user(
                info.context.user
            )

            message_query = ChatMessage.objects.filter(
                creator__in=users,
                msg_type=MessageTypeChoices.HUMAN,
                conversation__in=visible_conversations,
            )

            if cutoff_date:
                message_query = message_query.filter(created__gte=cutoff_date)
            if corpus_django_pk:
                message_query = message_query.filter(
                    conversation__chat_with_corpus_id=corpus_django_pk
                )

            user_message_counts = (
                message_query.values("creator")
                .annotate(count=Count("id"))
                .order_by("-count")[:limit]
            )

            for idx, item in enumerate(user_message_counts, start=1):
                user = User.objects.get(id=item["creator"])
                entries.append(
                    LeaderboardEntryType(
                        user=user,
                        rank=idx,
                        score=item["count"],
                        message_count=item["count"],
                    )
                )

        elif metric == "threads":
            # Count threads created per user
            thread_query = Conversation.objects.filter(
                creator__in=users, conversation_type="thread"
            ).visible_to_user(info.context.user)

            if cutoff_date:
                thread_query = thread_query.filter(created__gte=cutoff_date)
            if corpus_django_pk:
                thread_query = thread_query.filter(chat_with_corpus_id=corpus_django_pk)

            user_thread_counts = (
                thread_query.values("creator")
                .annotate(count=Count("id"))
                .order_by("-count")[:limit]
            )

            for idx, item in enumerate(user_thread_counts, start=1):
                user = User.objects.get(id=item["creator"])
                entries.append(
                    LeaderboardEntryType(
                        user=user,
                        rank=idx,
                        score=item["count"],
                        thread_count=item["count"],
                    )
                )

        elif metric == "annotations":
            # Count annotations created per user
            annotation_query = Annotation.objects.filter(
                creator__in=users
            ).visible_to_user(info.context.user)

            if cutoff_date:
                annotation_query = annotation_query.filter(created__gte=cutoff_date)
            if corpus_django_pk:
                annotation_query = annotation_query.filter(
                    document__corpus__id=corpus_django_pk
                )

            user_annotation_counts = (
                annotation_query.values("creator")
                .annotate(count=Count("id"))
                .order_by("-count")[:limit]
            )

            for idx, item in enumerate(user_annotation_counts, start=1):
                user = User.objects.get(id=item["creator"])
                entries.append(
                    LeaderboardEntryType(
                        user=user,
                        rank=idx,
                        score=item["count"],
                        annotation_count=item["count"],
                    )
                )

        elif metric == "reputation":
            # Get reputation scores
            from opencontractserver.conversations.models import UserReputation

            rep_query = UserReputation.objects.filter(user__in=users)
            if corpus_django_pk:
                rep_query = rep_query.filter(corpus_id=corpus_django_pk)
            else:
                rep_query = rep_query.filter(corpus__isnull=True)

            top_reps = rep_query.select_related("user").order_by("-reputation_score")[
                :limit
            ]

            for idx, rep in enumerate(top_reps, start=1):
                entries.append(
                    LeaderboardEntryType(
                        user=rep.user,
                        rank=idx,
                        score=rep.reputation_score,
                        reputation=rep.reputation_score,
                    )
                )

        # Find current user's rank
        current_user_rank = None
        if current_user and current_user.is_authenticated:
            for entry in entries:
                if entry.user.id == current_user.id:
                    current_user_rank = entry.rank
                    break

        return LeaderboardType(
            metric=metric,
            scope=scope,
            corpus_id=corpus_id,
            total_users=len(entries),
            entries=entries,
            current_user_rank=current_user_rank,
        )

    def resolve_community_stats(self, info, corpus_id=None):
        """
        Get overall community engagement statistics.

        Issue: #613 - Create leaderboard and community stats dashboard
        Epic: #572 - Social Features Epic

        Args:
            corpus_id: Optional corpus ID for corpus-specific stats

        Returns:
            CommunityStatsType with engagement metrics
        """
        from datetime import timedelta

        from django.contrib.auth import get_user_model
        from django.db.models import Count, Q
        from django.utils import timezone

        from opencontractserver.annotations.models import Annotation

        # UserBadge is imported at top level

        User = get_user_model()

        # Get corpus if specified
        corpus_django_pk = None
        if corpus_id:
            try:
                _, corpus_django_pk = from_global_id(corpus_id)
                # Verify user has access to this corpus
                Corpus.objects.visible_to_user(info.context.user).get(
                    id=corpus_django_pk
                )
            except Corpus.DoesNotExist:
                raise GraphQLError("Corpus not found or access denied")

        # Calculate date cutoffs
        now = timezone.now()
        week_ago = now - timedelta(days=7)
        month_ago = now - timedelta(days=30)

        # Get visible users
        users = User.objects.visible_to_user(info.context.user).filter(is_active=True)
        total_users = users.count()

        # Total messages
        # Filter by visible conversations since ChatMessage doesn't inherit conversation visibility
        visible_conversations_stats = Conversation.objects.visible_to_user(
            info.context.user
        )
        message_query = ChatMessage.objects.filter(
            msg_type=MessageTypeChoices.HUMAN,
            conversation__in=visible_conversations_stats,
        )
        if corpus_django_pk:
            message_query = message_query.filter(
                conversation__chat_with_corpus_id=corpus_django_pk
            )
        total_messages = message_query.count()
        messages_this_week = message_query.filter(created__gte=week_ago).count()
        messages_this_month = message_query.filter(created__gte=month_ago).count()

        # Active users (users who posted messages)
        active_users_week = (
            message_query.filter(created__gte=week_ago)
            .values("creator")
            .distinct()
            .count()
        )
        active_users_month = (
            message_query.filter(created__gte=month_ago)
            .values("creator")
            .distinct()
            .count()
        )

        # Total threads
        thread_query = Conversation.objects.filter(
            conversation_type="thread"
        ).visible_to_user(info.context.user)
        if corpus_django_pk:
            thread_query = thread_query.filter(chat_with_corpus_id=corpus_django_pk)
        total_threads = thread_query.count()

        # Total annotations
        annotation_query = Annotation.objects.visible_to_user(info.context.user)
        if corpus_django_pk:
            annotation_query = annotation_query.filter(
                document__corpus__id=corpus_django_pk
            )
        total_annotations = annotation_query.count()

        # Total badges awarded
        badge_query = UserBadge.objects.all()
        if corpus_django_pk:
            badge_query = badge_query.filter(
                Q(corpus_id=corpus_django_pk) | Q(corpus__isnull=True)
            )
        total_badges_awarded = badge_query.count()

        # Badge distribution
        badge_distribution = []
        badge_stats = (
            badge_query.values("badge")
            .annotate(
                award_count=Count("id"), unique_recipients=Count("user", distinct=True)
            )
            .order_by("-award_count")[:10]
        )

        for stat in badge_stats:
            badge = Badge.objects.get(id=stat["badge"])
            badge_distribution.append(
                BadgeDistributionType(
                    badge=badge,
                    award_count=stat["award_count"],
                    unique_recipients=stat["unique_recipients"],
                )
            )

        return CommunityStatsType(
            total_users=total_users,
            total_messages=total_messages,
            total_threads=total_threads,
            total_annotations=total_annotations,
            total_badges_awarded=total_badges_awarded,
            badge_distribution=badge_distribution,
            messages_this_week=messages_this_week,
            messages_this_month=messages_this_month,
            active_users_this_week=active_users_week,
            active_users_this_month=active_users_month,
        )

    # OG METADATA RESOLVERS (PUBLIC - NO AUTH) ############
    # These queries are used by Cloudflare Workers to generate
    # Open Graph meta tags for social media link previews.
    # They only return data for public entities (is_public=True).
    # See: docs/architecture/social-media-previews.md

    og_corpus_metadata = graphene.Field(
        OGCorpusMetadataType,
        user_slug=graphene.String(required=True),
        corpus_slug=graphene.String(required=True),
        description="Public OG metadata for corpus - no auth required",
    )

    og_document_metadata = graphene.Field(
        OGDocumentMetadataType,
        user_slug=graphene.String(required=True),
        document_slug=graphene.String(required=True),
        description="Public OG metadata for standalone document - no auth required",
    )

    og_document_in_corpus_metadata = graphene.Field(
        OGDocumentMetadataType,
        user_slug=graphene.String(required=True),
        corpus_slug=graphene.String(required=True),
        document_slug=graphene.String(required=True),
        description="Public OG metadata for document in corpus - no auth required",
    )

    og_thread_metadata = graphene.Field(
        OGThreadMetadataType,
        user_slug=graphene.String(required=True),
        corpus_slug=graphene.String(required=True),
        thread_id=graphene.String(required=True),
        description="Public OG metadata for discussion thread - no auth required",
    )

    og_extract_metadata = graphene.Field(
        OGExtractMetadataType,
        extract_id=graphene.String(required=True),
        description="Public OG metadata for data extract - no auth required",
    )

    @graphql_ratelimit(key="ip", rate="60/m", group="og_metadata")
    def resolve_og_corpus_metadata(self, info, user_slug, corpus_slug):
        """
        Public OG metadata for corpus - no auth required.
        Only returns data for public corpuses (is_public=True).

        Used by Cloudflare Workers for social media link previews.
        Rate limited to 60 requests/minute per IP to prevent abuse.
        """
        from django.contrib.auth import get_user_model
        from django.db.models import Count

        User = get_user_model()
        try:
            user = User.objects.get(slug=user_slug)
            # Use annotate to count documents via DocumentPath instead of M2M
            corpus = (
                Corpus.objects.annotate(doc_count=Count("document_paths"))
                .select_related("creator")
                .get(creator=user, slug=corpus_slug, is_public=True)
            )

            # Build icon URL if available
            icon_url = None
            if corpus.icon:
                icon_url = info.context.build_absolute_uri(corpus.icon.url)

            return OGCorpusMetadataType(
                title=corpus.title,
                description=corpus.description or "",
                icon_url=icon_url,
                document_count=corpus.doc_count,
                creator_name=corpus.creator.username,
                is_public=True,
            )
        except (User.DoesNotExist, Corpus.DoesNotExist):
            return None

    @graphql_ratelimit(key="ip", rate="60/m", group="og_metadata")
    def resolve_og_document_metadata(self, info, user_slug, document_slug):
        """
        Public OG metadata for standalone document - no auth required.
        Only returns data for public documents (is_public=True).
        Rate limited to 60 requests/minute per IP to prevent abuse.
        """
        from django.contrib.auth import get_user_model

        User = get_user_model()
        try:
            user = User.objects.get(slug=user_slug)
            document = Document.objects.get(
                creator=user, slug=document_slug, is_public=True
            )

            # Build icon URL if available
            icon_url = None
            if document.icon:
                icon_url = info.context.build_absolute_uri(document.icon.url)

            return OGDocumentMetadataType(
                title=document.title,
                description=document.description or "",
                icon_url=icon_url,
                corpus_title=None,
                creator_name=document.creator.username,
                is_public=True,
            )
        except (User.DoesNotExist, Document.DoesNotExist):
            return None

    @graphql_ratelimit(key="ip", rate="60/m", group="og_metadata")
    def resolve_og_document_in_corpus_metadata(
        self, info, user_slug, corpus_slug, document_slug
    ):
        """
        Public OG metadata for document in corpus context - no auth required.
        Only returns data if both corpus and document are public.
        Rate limited to 60 requests/minute per IP to prevent abuse.
        """
        from django.contrib.auth import get_user_model

        User = get_user_model()
        try:
            user = User.objects.get(slug=user_slug)
            corpus = Corpus.objects.get(creator=user, slug=corpus_slug, is_public=True)
            document = (
                corpus.get_documents()
                .filter(slug=document_slug, is_public=True)
                .first()
            )
            if not document:
                raise Document.DoesNotExist()

            # Build icon URL if available
            icon_url = None
            if document.icon:
                icon_url = info.context.build_absolute_uri(document.icon.url)

            return OGDocumentMetadataType(
                title=document.title,
                description=document.description or "",
                icon_url=icon_url,
                corpus_title=corpus.title,
                creator_name=document.creator.username,
                is_public=True,
            )
        except (User.DoesNotExist, Corpus.DoesNotExist, Document.DoesNotExist):
            return None

    @graphql_ratelimit(key="ip", rate="60/m", group="og_metadata")
    def resolve_og_thread_metadata(self, info, user_slug, corpus_slug, thread_id):
        """
        Public OG metadata for discussion thread - no auth required.
        Only returns data if parent corpus is public.
        Rate limited to 60 requests/minute per IP to prevent abuse.
        """
        from django.contrib.auth import get_user_model
        from django.db.models import Count

        User = get_user_model()
        try:
            user = User.objects.get(slug=user_slug)
            corpus = Corpus.objects.get(creator=user, slug=corpus_slug, is_public=True)

            # Decode thread ID if base64 encoded (GraphQL relay ID)
            try:
                _, pk = from_global_id(thread_id)
                # from_global_id returns empty strings for invalid base64
                if not pk:
                    pk = thread_id
            except Exception:
                pk = thread_id

            # Use annotate to avoid N+1 query for message count
            thread = (
                Conversation.objects.annotate(msg_count=Count("chat_messages"))
                .select_related("creator")
                .get(pk=pk, chat_with_corpus=corpus)
            )

            return OGThreadMetadataType(
                title=thread.title or "Discussion",
                corpus_title=corpus.title,
                message_count=thread.msg_count,
                creator_name=thread.creator.username if thread.creator else "Anonymous",
                is_public=True,
            )
        except (User.DoesNotExist, Corpus.DoesNotExist, Conversation.DoesNotExist):
            return None

    @graphql_ratelimit(key="ip", rate="60/m", group="og_metadata")
    def resolve_og_extract_metadata(self, info, extract_id):
        """
        Public OG metadata for data extract - no auth required.
        Only returns data if parent corpus is public.
        Rate limited to 60 requests/minute per IP to prevent abuse.
        """
        from opencontractserver.extracts.models import Extract

        try:
            # Decode extract ID if base64 encoded (GraphQL relay ID)
            try:
                _, pk = from_global_id(extract_id)
                # from_global_id returns empty strings for invalid base64
                if not pk:
                    pk = extract_id
            except Exception:
                pk = extract_id

            extract = Extract.objects.select_related(
                "corpus", "fieldset", "creator"
            ).get(pk=pk)

            # Extracts inherit corpus visibility
            if not extract.corpus.is_public:
                return None

            return OGExtractMetadataType(
                name=extract.name,
                corpus_title=extract.corpus.title,
                fieldset_name=extract.fieldset.name if extract.fieldset else "Custom",
                creator_name=(
                    extract.creator.username if extract.creator else "System"
                ),
                is_public=True,
            )
        except Extract.DoesNotExist:
            return None

    # PIPELINE SETTINGS ########################################
    pipeline_settings = graphene.Field(
        "config.graphql.graphene_types.PipelineSettingsType",
        description="Retrieve the singleton pipeline settings for document processing configuration.",
    )

    @login_required
    def resolve_pipeline_settings(self, info):
        """
        Resolve the singleton PipelineSettings instance.

        This query returns the runtime-configurable document processing settings.
        Any authenticated user can read these settings, but only superusers can
        modify them via the UpdatePipelineSettings mutation.

        Returns:
            PipelineSettingsType: The singleton pipeline settings.
        """
        from config.graphql.graphene_types import PipelineSettingsType
        from opencontractserver.documents.models import PipelineSettings

        settings_instance = PipelineSettings.get_instance()

        # Get list of components that have secrets (don't expose actual secrets)
        components_with_secrets = list(settings_instance.get_secrets().keys())

        return PipelineSettingsType(
            preferred_parsers=settings_instance.preferred_parsers or {},
            preferred_embedders=settings_instance.preferred_embedders or {},
            preferred_thumbnailers=settings_instance.preferred_thumbnailers or {},
            parser_kwargs=settings_instance.parser_kwargs or {},
            component_settings=settings_instance.component_settings or {},
            default_embedder=settings_instance.default_embedder or "",
            components_with_secrets=components_with_secrets,
            modified=settings_instance.modified,
            modified_by=settings_instance.modified_by,
        )

    # WORKER UPLOAD QUERIES (Superuser only) #################
    worker_accounts = graphene.List(
        WorkerAccountType,
        description="List all worker accounts. Superuser only.",
    )
    corpus_access_tokens = graphene.List(
        CorpusAccessTokenType,
        corpus_id=graphene.Int(required=True),
        description="List access tokens scoped to a corpus. Superuser or corpus owner.",
    )
    worker_document_uploads = graphene.List(
        WorkerDocumentUploadType,
        corpus_id=graphene.Int(required=True),
        status=graphene.String(required=False),
        description="List worker document uploads for a corpus, with optional status filter.",
    )

    @login_required
    def resolve_worker_accounts(self, info):
        user = info.context.user
        if not user.is_superuser:
            raise GraphQLError("Permission denied. Superuser access required.")

        accounts = WorkerAccount.objects.select_related("creator", "user").all()
        result = []
        for account in accounts:
            token_count = CorpusAccessToken.objects.filter(
                worker_account=account
            ).count()
            result.append(
                WorkerAccountType(
                    id=account.id,
                    name=account.name,
                    description=account.description,
                    is_active=account.is_active,
                    created=account.created,
                    token_count=token_count,
                    creator_username=(
                        account.creator.username if account.creator else None
                    ),
                )
            )
        return result

    @login_required
    def resolve_corpus_access_tokens(self, info, corpus_id):
        user = info.context.user

        try:
            corpus = Corpus.objects.get(id=corpus_id)
        except Corpus.DoesNotExist:
            raise GraphQLError("Corpus not found.")

        # Allow superusers and corpus owners
        if not user.is_superuser and corpus.creator_id != user.id:
            raise GraphQLError("Permission denied.")

        tokens = (
            CorpusAccessToken.objects.filter(corpus=corpus)
            .select_related("worker_account", "corpus")
            .order_by("-created")
        )
        result = []
        for token in tokens:
            upload_count = WorkerDocumentUpload.objects.filter(
                corpus_access_token=token
            ).count()
            result.append(
                CorpusAccessTokenType(
                    id=token.id,
                    key_prefix=token.key_prefix,
                    worker_account_name=token.worker_account.name,
                    corpus_id=token.corpus_id,
                    corpus_title=token.corpus.title,
                    expires_at=token.expires_at,
                    is_active=token.is_active,
                    rate_limit_per_minute=token.rate_limit_per_minute,
                    created=token.created,
                    upload_count=upload_count,
                )
            )
        return result

    @login_required
    def resolve_worker_document_uploads(self, info, corpus_id, status=None):
        user = info.context.user

        try:
            corpus = Corpus.objects.get(id=corpus_id)
        except Corpus.DoesNotExist:
            raise GraphQLError("Corpus not found.")

        # Allow superusers and corpus owners
        if not user.is_superuser and corpus.creator_id != user.id:
            raise GraphQLError("Permission denied.")

        qs = WorkerDocumentUpload.objects.filter(corpus=corpus).select_related(
            "corpus_access_token__worker_account", "corpus"
        )
        if status:
            qs = qs.filter(status=status)
        qs = qs.order_by("-created")[:100]

        result = []
        for upload in qs:
            worker_name = None
            if upload.corpus_access_token and upload.corpus_access_token.worker_account:
                worker_name = upload.corpus_access_token.worker_account.name
            result.append(
                WorkerDocumentUploadType(
                    id=str(upload.id),
                    status=upload.status,
                    corpus_id=upload.corpus_id,
                    corpus_title=upload.corpus.title,
                    worker_account_name=worker_name,
                    error_message=upload.error_message,
                    created=upload.created,
                    processing_started=upload.processing_started,
                    processing_finished=upload.processing_finished,
                )
            )
        return result

    # DEBUG FIELD ########################################
    if settings.ALLOW_GRAPHQL_DEBUG:
        debug = graphene.Field(DjangoDebug, name="_debug")
