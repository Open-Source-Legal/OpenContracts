import inspect
import logging
import re
from typing import Optional

import graphene
from django.conf import settings
from django.db.models import Prefetch, Q
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
    CorpusFilter,
    CorpusQueryFilter,
    DatacellFilter,
    DocumentFilter,
    DocumentRelationshipFilter,
    ExportFilter,
    ExtractFilter,
    FieldsetFilter,
    GremlinEngineFilter,
    LabelFilter,
    LabelsetFilter,
    RelationshipFilter,
    UserBadgeFilter,
)
from config.graphql.graphene_types import (
    AgentConfigurationType,
    AnalysisType,
    AnalyzerType,
    AnnotationLabelType,
    AnnotationType,
    AssignmentType,
    BadgeDistributionType,
    BadgeType,
    BulkDocumentUploadStatusType,
    ColumnType,
    CommunityStatsType,
    ConversationType,
    CorpusActionType,
    CorpusFolderType,
    CorpusQueryType,
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
    NoteType,
    NotificationType,
    PageAwareAnnotationType,
    PdfPageInfoType,
    PipelineComponentsType,
    PipelineComponentType,
    RelationshipType,
    UserBadgeType,
    UserExportType,
    UserImportType,
    UserType,
)
from config.graphql.ratelimits import (
    get_user_tier_rate,
    graphql_ratelimit_dynamic,
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
from opencontractserver.conversations.models import ChatMessage, Conversation
from opencontractserver.corpuses.models import (
    Corpus,
    CorpusAction,
    CorpusFolder,
    CorpusQuery,
)
from opencontractserver.documents.models import Document, DocumentRelationship
from opencontractserver.extracts.models import Column, Datacell, Fieldset
from opencontractserver.feedback.models import UserFeedback
from opencontractserver.notifications.models import Notification
from opencontractserver.pipeline.utils import (
    get_all_embedders,
    get_all_parsers,
    get_all_post_processors,
    get_all_thumbnailers,
    get_components_by_mimetype,
    get_metadata_for_component,
)
from opencontractserver.types.enums import LabelType, PermissionTypes
from opencontractserver.users.models import Assignment, UserExport, UserImport
from opencontractserver.utils.permissioning import user_has_permission_for_obj

logger = logging.getLogger(__name__)


class MetadataCompletionStatusType(graphene.ObjectType):
    """Type for metadata completion status information."""

    total_fields = graphene.Int()
    filled_fields = graphene.Int()
    missing_fields = graphene.Int()
    percentage = graphene.Float()
    missing_required = graphene.List(graphene.String)


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
        from django.contrib.auth import get_user_model

        User = get_user_model()
        try:
            return User.objects.get(slug=slug)
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
        # Check if we should use the query optimizer (when document_id is provided)
        document_id = kwargs.get("document_id")
        corpus_id = kwargs.get("corpus_id")

        if document_id:
            # Import the query optimizer
            from opencontractserver.annotations.query_optimizer import (
                AnnotationQueryOptimizer,
            )

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

        else:
            # Fallback to old behavior for non-document queries
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
        return Corpus.objects.visible_to_user(info.context.user).select_related(
            "creator", "engagement_metrics"
        )

    corpus = OpenContractsNode.Field(CorpusType)  # relay.Node.Field(CorpusType)

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
        """
        _, corpus_pk = from_global_id(corpus_id)
        return CorpusFolder.objects.filter(corpus_id=corpus_pk).visible_to_user(
            info.context.user
        )

    corpus_folder = graphene.Field(
        CorpusFolderType,
        id=graphene.ID(required=True),
        description="Get a single folder by ID",
    )

    @graphql_ratelimit_dynamic(get_rate=get_user_tier_rate("READ_LIGHT"))
    def resolve_corpus_folder(self, info, id):
        """Get a single folder by ID with permission check."""
        _, folder_pk = from_global_id(id)
        try:
            return CorpusFolder.objects.visible_to_user(info.context.user).get(
                pk=folder_pk
            )
        except CorpusFolder.DoesNotExist:
            return None

    deleted_documents_in_corpus = graphene.List(
        DocumentPathType,
        corpus_id=graphene.ID(required=True),
        description="Get all soft-deleted documents in a corpus (trash folder view)",
    )

    @graphql_ratelimit_dynamic(get_rate=get_user_tier_rate("READ_LIGHT"))
    def resolve_deleted_documents_in_corpus(self, info, corpus_id):
        """
        Get all soft-deleted documents in a corpus for trash folder view.

        Returns DocumentPath records where is_deleted=True and is_current=True,
        which represents the current soft-deleted state in the path tree.
        """
        from opencontractserver.documents.models import DocumentPath

        _, corpus_pk = from_global_id(corpus_id)

        # First check user has access to the corpus
        try:
            corpus = Corpus.objects.visible_to_user(info.context.user).get(pk=corpus_pk)
        except Corpus.DoesNotExist:
            return []

        # Return soft-deleted documents (is_deleted=True, is_current=True)
        return (
            DocumentPath.objects.filter(corpus=corpus, is_current=True, is_deleted=True)
            .select_related("document", "folder", "creator")
            .order_by("-modified")
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
    def resolve_search_documents_for_mention(self, info, text_search=None, **kwargs):
        """
        Search documents for @ mention autocomplete.

        SECURITY: Only returns documents where user can meaningfully contribute.
        Requires one of:
        - User is creator
        - User has write permission on document
        - Document is in a corpus where user has write permission
        - Document is public AND (no corpus OR public corpus OR user has corpus access)

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
        if corpus_id:
            qs = qs.filter(corpus_id=corpus_id)

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

        SECURITY: All authenticated users can search for other users.
        This is necessary for @mentions to work in collaborative contexts.
        User data exposed is minimal (username, email) - no sensitive info.

        PERFORMANCE NOTES:
        - Searches username (indexed, fast)
        - Searches email (indexed, fast)
        - Limits to 10 results to prevent overwhelming UI

        Rationale: Mentioning users is fundamental to collaboration.
        Users can already see each other in shared corpuses, so this doesn't
        expose additional information.

        @param text_search: Search query for username or email
        """
        from django.contrib.auth import get_user_model

        User = get_user_model()
        user = info.context.user

        # Anonymous users cannot mention (must be authenticated)
        if user.is_anonymous:
            return User.objects.none()

        # All authenticated users can search for users
        qs = User.objects.filter(is_active=True)

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
        return Document.objects.visible_to_user(info.context.user)

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
        if info.context.user.is_superuser:
            return Assignment.objects.all()
        else:
            return Assignment.objects.filter(assignor=info.context.user)

    assignment = relay.Node.Field(AssignmentType)

    @login_required
    def resolve_assignment(self, info, **kwargs):
        django_pk = from_global_id(kwargs.get("id", None))[1]
        return Assignment.objects.visible_to_user(info.context.user).get(id=django_pk)

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

    corpus_query = relay.Node.Field(CorpusQueryType)

    @login_required
    def resolve_corpus_query(self, info, **kwargs):
        django_pk = from_global_id(kwargs.get("id", None))[1]
        return CorpusQuery.objects.visible_to_user(info.context.user).get(id=django_pk)

    corpus_queries = DjangoFilterConnectionField(
        CorpusQueryType, filterset_class=CorpusQueryFilter
    )

    @login_required
    def resolve_corpus_queries(self, info, **kwargs):
        return CorpusQuery.objects.visible_to_user(info.context.user)

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

        total_docs = 0
        total_annotations = 0
        total_comments = 0
        total_analyses = 0
        total_extracts = 0
        total_threads = 0

        corpus_pk = from_global_id(corpus_id)[1]
        corpuses = Corpus.objects.visible_to_user(info.context.user).filter(
            id=corpus_pk
        )

        if corpuses.count() == 1:
            corpus = corpuses[0]
            # Use DocumentPath-based method for accurate count
            total_docs = corpus.document_count()
            total_annotations = corpus.annotations.all().count()
            total_comments = UserFeedback.objects.filter(
                commented_annotation__corpus=corpus
            ).count()
            total_analyses = corpus.analyses.all().count()
            total_extracts = corpus.extracts.all().count()
            total_threads = (
                Conversation.objects.filter(
                    conversation_type="thread", chat_with_corpus=corpus
                )
                .visible_to_user(info.context.user)
                .count()
            )

        return CorpusStatsType(
            total_docs=total_docs,
            total_annotations=total_annotations,
            total_comments=total_comments,
            total_analyses=total_analyses,
            total_extracts=total_extracts,
            total_threads=total_threads,
        )

    document_corpus_actions = graphene.Field(
        DocumentCorpusActionsType,
        document_id=graphene.ID(required=True),
        corpus_id=graphene.ID(required=False),
    )

    def resolve_document_corpus_actions(self, info, document_id, corpus_id=None):

        user = info.context.user
        if user.is_anonymous:
            user = None

        document_pk = from_global_id(document_id)[1]

        if corpus_id is not None:
            corpus_pk = from_global_id(corpus_id)[1]
            corpus = Corpus.objects.get(id=corpus_pk)
            corpus_actions = CorpusAction.objects.filter(
                Q(corpus=corpus), Q(creator=user) | Q(is_public=True)
            )

        else:
            corpus = None
            corpus_actions = []

        try:
            document = Document.objects.get(
                Q(id=document_pk), Q(creator=user) | Q(is_public=True)
            )
            extracts = document.extracts.filter(
                Q(is_public=True) | Q(creator=user), corpus=corpus
            )
            analysis_rows = document.rows.filter(
                Q(analysis__is_public=True) | Q(analysis__creator=user)
            )

        except Document.DoesNotExist:
            logger.error("ERROR!")
            extracts = []
            analysis_rows = []

        return DocumentCorpusActionsType(
            corpus_actions=corpus_actions,
            extracts=extracts,
            analysis_rows=analysis_rows,
        )

    pipeline_components = graphene.Field(
        PipelineComponentsType,
        mimetype=graphene.Argument(FileTypeEnum, required=False),
        description="Retrieve all registered pipeline components, optionally filtered by MIME type.",
    )

    def resolve_pipeline_components(
        self, info, mimetype: Optional[FileTypeEnum] = None
    ) -> PipelineComponentsType:
        """
        Resolver for the pipeline_components query.

        Args:
            info: GraphQL execution info.
            mimetype (Optional[FileTypeEnum]): MIME type to filter pipeline components.

        Returns:
            PipelineComponentsType: The pipeline components grouped by type.
        """
        from opencontractserver.pipeline.base.file_types import (
            FileTypeEnum as FileTypeEnumModel,
        )

        if mimetype:
            # Convert the GraphQL enum value to the appropriate MIME type string
            mime_type_mapping = {
                "pdf": "application/pdf",
                "txt": "text/plain",
                "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            }
            mime_type_str = mime_type_mapping.get(mimetype.value)

            # If mimetype is provided, get compatible components
            components_data = get_components_by_mimetype(mime_type_str, detailed=True)
        else:
            # Get all components
            components_data = {
                "parsers": get_all_parsers(),
                "embedders": get_all_embedders(),
                "thumbnailers": get_all_thumbnailers(),
                "post_processors": get_all_post_processors(),
            }

        components = {
            "parsers": [],
            "embedders": [],
            "thumbnailers": [],
            "post_processors": [],
        }

        for component_type in [
            "parsers",
            "embedders",
            "thumbnailers",
            "post_processors",
        ]:
            for component in components_data.get(component_type, []):
                if isinstance(component, dict):
                    # If detailed=True, component is a dict with metadata
                    metadata = component
                    component_cls = metadata.get("class")
                else:
                    component_cls = component
                    metadata = get_metadata_for_component(component_cls)
                if component_cls:
                    # Filter out any file types that are no longer supported
                    supported_file_types = []
                    for ft in metadata.get("supported_file_types", []):
                        try:
                            # Only include file types that are still defined in FileTypeEnum
                            supported_file_types.append(FileTypeEnumModel(ft).value)
                        except (ValueError, AttributeError):
                            # Skip file types that are no longer supported
                            pass

                    component_info = PipelineComponentType(
                        name=component_cls.__name__,
                        class_name=f"{component_cls.__module__}.{component_cls.__name__}",
                        title=metadata.get("title", ""),
                        module_name=metadata.get("module_name", ""),
                        description=metadata.get("description", ""),
                        author=metadata.get("author", ""),
                        dependencies=metadata.get("dependencies", []),
                        supported_file_types=supported_file_types,
                        component_type=component_type[:-1],
                        input_schema=metadata.get("input_schema", {}),
                    )
                    if component_type == "embedders":
                        component_info.vector_size = metadata.get("vector_size", 0)
                    components[component_type].append(component_info)

        return PipelineComponentsType(
            parsers=components["parsers"],
            embedders=components["embedders"],
            thumbnailers=components["thumbnailers"],
            post_processors=components["post_processors"],
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

    # DOCUMENT RELATIONSHIP RESOLVERS #####################################
    document_relationships = DjangoFilterConnectionField(
        DocumentRelationshipType,
        filterset_class=DocumentRelationshipFilter,
        corpus_id=graphene.ID(required=False),
        document_id=graphene.ID(required=False),
    )

    @login_required
    def resolve_document_relationships(self, info, **kwargs):
        # Start with base queryset using visible_to_user
        queryset = DocumentRelationship.objects.visible_to_user(info.context.user)

        # Apply filters if provided
        corpus_id = kwargs.get("corpus_id")
        if corpus_id:
            corpus_pk = from_global_id(corpus_id)[1]
            queryset = queryset.filter(
                Q(source_document__corpus=corpus_pk)
                | Q(target_document__corpus=corpus_pk)
            )

        document_id = kwargs.get("document_id")
        if document_id:
            doc_pk = from_global_id(document_id)[1]
            queryset = queryset.filter(
                Q(source_document_id=doc_pk) | Q(target_document_id=doc_pk)
            )

        return queryset.distinct().order_by("-created")

    document_relationship = relay.Node.Field(DocumentRelationshipType)

    @login_required
    def resolve_document_relationship(self, info, **kwargs):
        django_pk = from_global_id(kwargs.get("id", None))[1]
        queryset = DocumentRelationship.objects.visible_to_user(info.context.user)
        queryset = queryset.select_related(
            "source_document",
            "target_document",
            "relationship_label",
            "creator",
            "analyzer",
            "analysis",
        ).prefetch_related(  # Prefetch might be overkill for a single object, but harmless
            "relationship_label",
            "corpus",
            "document",
            "creator",
            "analyzer",
            "analysis",
        )
        return queryset.get(id=django_pk)

    # Also add a bulk resolver similar to bulk_doc_relationships_in_corpus
    bulk_doc_relationships = graphene.Field(
        graphene.List(DocumentRelationshipType),
        corpus_id=graphene.ID(required=False),
        document_id=graphene.ID(required=True),
        relationship_type=graphene.String(required=False),
    )

    @login_required
    def resolve_bulk_doc_relationships(self, info, document_id, **kwargs):
        # Start with base queryset using visible_to_user
        queryset = DocumentRelationship.objects.visible_to_user(info.context.user)

        # Always filter by document
        doc_pk = from_global_id(document_id)[1]
        queryset = queryset.filter(
            Q(source_document_id=doc_pk) | Q(target_document_id=doc_pk)
        )

        # Apply optional filters
        corpus_id = kwargs.get("corpus_id")
        if corpus_id:
            corpus_pk = from_global_id(corpus_id)[1]
            queryset = queryset.filter(
                Q(source_document__corpus=corpus_pk)
                | Q(target_document__corpus=corpus_pk)
            )

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
            # Validate msg_type against ChatMessage.TYPE_CHOICES
            valid_types = [choice[0] for choice in ChatMessage.TYPE_CHOICES]
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

    conversation = relay.Node.Field(ConversationType)

    def resolve_conversation(self, info, **kwargs):
        """
        Resolver to fetch a single Conversation by ID.

        Anonymous users can see public conversations.
        Authenticated users see public conversations, their own, or explicitly shared.
        """
        import logging

        logger = logging.getLogger(__name__)

        conversation_id = kwargs.get("id", None)
        logger.info(f"🔍 resolve_conversation called with id: {conversation_id}")
        logger.info(f"   User: {info.context.user}")
        is_auth = (
            info.context.user.is_authenticated
            if hasattr(info.context.user, "is_authenticated")
            else "N/A"
        )
        logger.info(f"   Is authenticated: {is_auth}")

        try:
            django_pk = from_global_id(conversation_id)[1]
            logger.info(f"   Decoded django_pk: {django_pk}")

            queryset = Conversation.objects.visible_to_user(info.context.user)
            logger.info(f"   Visible conversations count: {queryset.count()}")

            conversation = queryset.get(id=django_pk)
            logger.info(
                f"   ✅ Found conversation: {conversation.id} - {conversation.title}"
            )
            return conversation
        except Conversation.DoesNotExist:
            logger.warning(
                f"   ❌ Conversation {django_pk} not found or not visible to user"
            )
            return None
        except Exception as e:
            logger.error(f"   ❌ Error resolving conversation: {e}", exc_info=True)
            return None

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

    def resolve_corpus_metadata_columns(self, info, corpus_id):
        """Get metadata columns for a corpus."""
        from opencontractserver.corpuses.models import Corpus

        try:
            user = info.context.user
            corpus = Corpus.objects.get(pk=from_global_id(corpus_id)[1])

            # Check permissions
            if not user_has_permission_for_obj(user, corpus, PermissionTypes.READ):
                return []

            # Get metadata fieldset
            if hasattr(corpus, "metadata_schema") and corpus.metadata_schema:
                return corpus.metadata_schema.columns.filter(
                    is_manual_entry=True
                ).order_by("display_order")

            return []

        except Corpus.DoesNotExist:
            return []

    def resolve_document_metadata_datacells(self, info, document_id, corpus_id):
        """Get metadata datacells for a document in a corpus."""
        from opencontractserver.corpuses.models import Corpus

        try:
            user = info.context.user
            document = Document.objects.get(pk=from_global_id(document_id)[1])
            corpus = Corpus.objects.get(pk=from_global_id(corpus_id)[1])

            # Check permissions
            if not user_has_permission_for_obj(user, document, PermissionTypes.READ):
                return []

            # Get metadata datacells
            if hasattr(corpus, "metadata_schema") and corpus.metadata_schema:
                return Datacell.objects.filter(
                    document=document,
                    column__fieldset=corpus.metadata_schema,
                    column__is_manual_entry=True,
                ).select_related("column")

            return []

        except (Document.DoesNotExist, Corpus.DoesNotExist):
            return []

    def resolve_metadata_completion_status_v2(self, info, document_id, corpus_id):
        """Get metadata completion status using column/datacell system."""
        from opencontractserver.corpuses.models import Corpus

        try:
            user = info.context.user
            document = Document.objects.get(pk=from_global_id(document_id)[1])
            corpus = Corpus.objects.get(pk=from_global_id(corpus_id)[1])

            # Check permissions
            if not user_has_permission_for_obj(user, document, PermissionTypes.READ):
                return None

            # Get metadata columns and datacells
            if not hasattr(corpus, "metadata_schema") or not corpus.metadata_schema:
                return {
                    "total_fields": 0,
                    "filled_fields": 0,
                    "missing_fields": 0,
                    "percentage": 100.0,
                    "missing_required": [],
                }

            columns = corpus.metadata_schema.columns.filter(is_manual_entry=True)
            total_fields = columns.count()

            if total_fields == 0:
                return {
                    "total_fields": 0,
                    "filled_fields": 0,
                    "missing_fields": 0,
                    "percentage": 100.0,
                    "missing_required": [],
                }

            # Get filled datacells
            filled_datacells = Datacell.objects.filter(
                document=document, column__in=columns
            ).exclude(data__value__isnull=True)

            filled_count = filled_datacells.count()
            filled_column_ids = set(
                filled_datacells.values_list("column_id", flat=True)
            )

            # Find missing required fields
            missing_required = []
            for column in columns:
                if column.id not in filled_column_ids:
                    config = column.validation_config or {}
                    if config.get("required", False):
                        missing_required.append(column.name)

            # Calculate percentage
            percentage = (filled_count / total_fields * 100) if total_fields > 0 else 0

            return {
                "total_fields": total_fields,
                "filled_fields": filled_count,
                "missing_fields": total_fields - filled_count,
                "percentage": percentage,
                "missing_required": missing_required,
            }

        except (Corpus.DoesNotExist, Document.DoesNotExist):
            return None

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
        """Resolve user badge awards."""
        return UserBadge.objects.all().select_related(
            "user", "badge", "awarded_by", "corpus"
        )

    def resolve_user_badge(self, info, **kwargs):
        """Resolve a single user badge by ID."""
        django_pk = from_global_id(kwargs.get("id", None))[1]
        return UserBadge.objects.get(id=django_pk)

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
    agent = relay.Node.Field(AgentConfigurationType)

    def resolve_agents(self, info, **kwargs):
        """Resolve agent configurations visible to the user."""
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
                .prefetch_related("user__user_badges__badge")
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

        Epic: #565 - Corpus Engagement Metrics & Analytics
        Issue: #568 - Create GraphQL queries for engagement metrics and leaderboards
        """
        from opencontractserver.conversations.models import UserReputation

        # Get top users by global reputation (corpus__isnull=True)
        # Prefetch user badges to avoid N+1 queries when frontend requests userBadges
        top_reputations = (
            UserReputation.objects.filter(corpus__isnull=True)
            .select_related("user")
            .prefetch_related("user__user_badges__badge")
            .order_by("-reputation_score")[:limit]
        )

        # Return user objects (badges are already prefetched)
        return [rep.user for rep in top_reputations]

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
        from datetime import datetime, timedelta

        from django.contrib.auth import get_user_model
        from django.db.models import Count, Q

        from opencontractserver.annotations.models import Annotation

        User = get_user_model()

        # Calculate date cutoff based on scope
        cutoff_date = None
        if scope == "weekly":
            cutoff_date = datetime.now() - timedelta(days=7)
        elif scope == "monthly":
            cutoff_date = datetime.now() - timedelta(days=30)

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
            # Count badges per user
            from opencontractserver.badges.models import UserBadge

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
                msg_type="HUMAN",
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
        from datetime import datetime, timedelta

        from django.contrib.auth import get_user_model
        from django.db.models import Count, Q

        from opencontractserver.annotations.models import Annotation
        from opencontractserver.badges.models import UserBadge

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
        week_ago = datetime.now() - timedelta(days=7)
        month_ago = datetime.now() - timedelta(days=30)

        # Get visible users
        users = User.objects.visible_to_user(info.context.user).filter(is_active=True)
        total_users = users.count()

        # Total messages
        # Filter by visible conversations since ChatMessage doesn't inherit conversation visibility
        visible_conversations_stats = Conversation.objects.visible_to_user(
            info.context.user
        )
        message_query = ChatMessage.objects.filter(
            msg_type="HUMAN", conversation__in=visible_conversations_stats
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

    # DEBUG FIELD ########################################
    if settings.ALLOW_GRAPHQL_DEBUG:
        debug = graphene.Field(DjangoDebug, name="_debug")
