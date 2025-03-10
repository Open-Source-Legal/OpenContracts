import inspect
import logging
import re
from typing import Optional

import graphene
from django.conf import settings
from django.db.models import Q
from graphene import relay
from graphene.types.generic import GenericScalar
from graphene_django.fields import DjangoConnectionField
from graphene_django.filter import DjangoFilterConnectionField
from graphql_jwt.decorators import login_required
from graphql_relay import from_global_id

from config.graphql.base import OpenContractsNode
from config.graphql.filters import (
    AnalysisFilter,
    AnalyzerFilter,
    AssignmentFilter,
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
)
from config.graphql.graphene_types import (
    AnalysisType,
    AnalyzerType,
    AnnotationLabelType,
    AnnotationType,
    AssignmentType,
    ColumnType,
    ConversationType,
    CorpusActionType,
    CorpusQueryType,
    CorpusStatsType,
    CorpusType,
    DatacellType,
    DocumentCorpusActionsType,
    DocumentRelationshipType,
    DocumentType,
    ExtractType,
    FieldsetType,
    FileTypeEnum,
    GremlinEngineType_READ,
    LabelSetType,
    MessageType,
    NoteType,
    PageAwareAnnotationType,
    PdfPageInfoType,
    PipelineComponentsType,
    PipelineComponentType,
    RelationshipType,
    UserExportType,
    UserImportType,
)
from opencontractserver.analyzer.models import Analysis, Analyzer, GremlinEngine
from opencontractserver.annotations.models import (
    Annotation,
    AnnotationLabel,
    LabelSet,
    Note,
    Relationship,
)
from opencontractserver.conversations.models import ChatMessage
from opencontractserver.corpuses.models import Corpus, CorpusAction, CorpusQuery
from opencontractserver.documents.models import Document, DocumentRelationship
from opencontractserver.extracts.models import Column, Datacell, Extract, Fieldset
from opencontractserver.feedback.models import UserFeedback
from opencontractserver.pipeline.utils import (
    get_all_embedders,
    get_all_parsers,
    get_all_post_processors,
    get_all_thumbnailers,
    get_components_by_mimetype,
    get_metadata_for_component,
)
from opencontractserver.types.enums import LabelType
from opencontractserver.users.models import Assignment, UserExport, UserImport

logger = logging.getLogger(__name__)


class Query(graphene.ObjectType):

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

    def resolve_annotations(
        self, info, analysis_isnull=None, structural=None, **kwargs
    ):
        # Use the central permission system to filter annotations
        # This ensures consistent handling of permissions, including corpus inheritance
        queryset = Annotation.objects.visible_to_user(info.context.user)

        print(f"Annotations queryset: {queryset}")

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

        logger.info(f"Final queryset: {queryset}")

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
        # Get the base queryset first (only stuff given user CAN see)
        queryset = DocumentRelationship.objects.visible_to_user(info.context.user)

        # Always filter by document
        doc_pk = from_global_id(document_id)[1]
        queryset = queryset.filter(
            Q(source_document_id=doc_pk) | Q(target_document_id=doc_pk)
        )

        # Apply optional filters
        corpus_pk = from_global_id(corpus_id)[1]
        queryset = queryset.filter(corpus_id=corpus_pk)

        return queryset.order_by("created")

    bulk_doc_annotations_in_corpus = graphene.Field(
        graphene.List(AnnotationType),
        corpus_id=graphene.ID(required=True),
        document_id=graphene.ID(required=False),
        for_analysis_ids=graphene.String(required=False),
        label_type=graphene.Argument(label_type_enum),
    )

    def resolve_bulk_doc_annotations_in_corpus(self, info, corpus_id, **kwargs):

        corpus_django_pk = from_global_id(corpus_id)[1]

        # Get the base queryset first (only stuff given user CAN see)
        queryset = Annotation.objects.visible_to_user(info.context.user)

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

        return queryset.filter(q_objects).order_by("created", "page")

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

    def resolve_page_annotations(self, info, document_id, corpus_id=None, **kwargs):

        doc_django_pk = from_global_id(document_id)[1]

        document = Document.objects.get(id=doc_django_pk)

        # Get the base queryset first (only stuff given user CAN see)
        queryset = Annotation.objects.visible_to_user(info.context.user)

        # Now build query to stuff they want to see
        q_objects = Q(document_id=doc_django_pk)
        if corpus_id is not None:
            q_objects.add(Q(corpus_id=from_global_id(corpus_id)[1]), Q.AND)

        # If for_analysis_ids is passed in, only show annotations from those analyses, otherwise only show human
        # annotations.
        for_analysis_ids = kwargs.get("for_analysis_ids", None)
        if for_analysis_ids is not None:
            logger.info(
                f"resolve_page_annotations - for_analysis_ids is not none and split ids:"
                f" {for_analysis_ids.split(',')}"
            )
            analysis_pks = [
                int(from_global_id(value)[1])
                for value in list(
                    filter(lambda raw_id: len(raw_id) > 0, for_analysis_ids.split(","))
                )
            ]
            logger.info(
                f"resolve_page_annotations - for_analysis_ids is not none and Analysis pks: {analysis_pks}"
            )
            q_objects.add(Q(analysis_id__in=analysis_pks), Q.AND)
        else:
            logger.info("resolve_page_annotations - for_analysis_ids is None")
            q_objects.add(Q(analysis__isnull=True), Q.AND)

        label_type = kwargs.get("label_type", None)
        if label_type is not None:
            logger.info(
                f"resolve_page_annotations - label_type is not none: {label_type}"
            )
            q_objects.add(Q(annotation_label__label_type=label_type), Q.AND)

        # Get total page count before filtering by page.
        all_pages_annotations = queryset.filter(q_objects).order_by("page")

        # Now filter down to page we want to view / request values for
        page_containing_annotation_with_id = kwargs.get(
            "page_containing_annotation_with_id", None
        )
        page_number_list = kwargs.get("page_number_list", None)
        if kwargs.get("current_page", None) is not None:
            logger.info(
                f"resolve_page_annotations - current_page is not None: {page_containing_annotation_with_id}"
            )
            current_page = kwargs.get("current_page")  # 1 -indexed
            logger.info(f"resolve_page_annotations- q_objects: {q_objects}")
        elif page_number_list is not None:
            if re.search(r"((\d,{0,1})*)", page_number_list) is not None:
                logger.info(
                    f"resolve_page_annotations - page_number_list is not none: {page_number_list}"
                )
                pages = [eval(page) for page in page_number_list.split(",")]
                logger.info(f"resolve_page_annotations - pages is: {pages}")
                current_page = pages[-1]
            else:
                raise ValueError(
                    f"Value provided is not a comma-seprated list of page numbers: {page_number_list}"
                )
        elif page_containing_annotation_with_id:
            logger.info(
                "resolve_page_annotations - page_containing_annotation_with_id is not None"
            )
            annotation_pk = int(from_global_id(page_containing_annotation_with_id)[1])
            logger.info(f"resolve_page_annotations - Annotation pk {annotation_pk}")
            current_page = (
                Annotation.objects.get(id=annotation_pk).page + 1
            )  # DB is 0-indexed, but make 1-indexed
            logger.info(
                f"resolve_page_annotations - Current page: {current_page} ({type(current_page)})"
            )
        else:
            logger.info("Current page and resolve_page_annotation are NOT set")
            current_page = 1  # Don't forget, we're using 0 index in gremlin. This is not cleanly followed on frontend
            # and backend. Need to fix. For now, everything coming IN from frontend is treated as 1-indexed

        # Convert 1-indexed inputs to 0-indexed page values for DB / backend
        current_page = current_page - 1

        if page_number_list is not None:
            page_annotations = all_pages_annotations.filter(
                page__in=[page - 1 for page in pages]
            ).order_by("page", "created")
        else:
            page_annotations = all_pages_annotations.filter(page=current_page).order_by(
                "page", "created"
            )
        logger.info(f"resolve_page_annotations - page annotations: {page_annotations}")

        pdf_page_info = PdfPageInfoType(
            page_count=document.page_count,
            current_page=current_page,  # convert to DB 0-index
            has_next_page=current_page < document.page_count - 1,
            has_previous_page=current_page > 0,
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
        return Annotation.objects.visible_to_user(info.context.user).get(id=django_pk)

    # RELATIONSHIP RESOLVERS #####################################
    relationships = DjangoFilterConnectionField(
        RelationshipType, filterset_class=RelationshipFilter
    )

    def resolve_relationships(self, info, **kwargs):
        return Relationship.objects.visible_to_user(info.context.user)

    relationship = relay.Node.Field(RelationshipType)

    def resolve_relationship(self, info, **kwargs):
        django_pk = from_global_id(kwargs.get("id", None))[1]
        return Relationship.objects.visible_to_user(info.context.user).get(id=django_pk)

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

    def resolve_labelsets(self, info, **kwargs):
        return LabelSet.objects.visible_to_user(info.context.user)

    labelset = relay.Node.Field(LabelSetType)

    def resolve_labelset(self, info, **kwargs):
        django_pk = from_global_id(kwargs.get("id", None))[1]
        return LabelSet.objects.visible_to_user(info.context.user).get(id=django_pk)

    # CORPUS RESOLVERS #####################################
    corpuses = DjangoFilterConnectionField(CorpusType, filterset_class=CorpusFilter)

    def resolve_corpuses(self, info, **kwargs):
        return Corpus.objects.visible_to_user(info.context.user)

    corpus = OpenContractsNode.Field(CorpusType)  # relay.Node.Field(CorpusType)

    # DOCUMENT RESOLVERS #####################################

    documents = DjangoFilterConnectionField(
        DocumentType, filterset_class=DocumentFilter
    )

    def resolve_documents(self, info, **kwargs):
        return Document.objects.visible_to_user(info.context.user)

    document = graphene.Field(DocumentType, id=graphene.String())

    def resolve_document(self, info, **kwargs):
        django_pk = from_global_id(kwargs.get("id", None))[1]
        return Document.objects.visible_to_user(info.context.user).get(id=django_pk)

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
            django_pk = from_global_id(kwargs.get("id", None))[1]
            return Analysis.objects.visible_to_user(info.context.user).get(id=django_pk)

        analyses = DjangoFilterConnectionField(
            AnalysisType, filterset_class=AnalysisFilter
        )

        def resolve_analyses(self, info, **kwargs):
            return Analysis.objects.visible_to_user(info.context.user)

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
        django_pk = from_global_id(kwargs.get("id", None))[1]
        return Extract.objects.visible_to_user(info.context.user).get(id=django_pk)

    extracts = DjangoFilterConnectionField(
        ExtractType, filterset_class=ExtractFilter, max_limit=15
    )

    def resolve_extracts(self, info, **kwargs):
        return Extract.objects.visible_to_user(info.context.user)

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

        # Saving for reference... but I don't think it's necessary ATM and it's much higher latency.
        # Try to get tasks from workers
        # try:
        #     i = celery_app.control.inspect(timeout=5.0, connect_timeout=5.0)
        #     registered_tasks = i.registered()
        #     if registered_tasks:
        #         for worker_tasks in registered_tasks.values():
        #             for task_name in worker_tasks:
        #                 if not task_name.startswith('celery.') and task_name not in tasks:
        #                     # For tasks only found on workers, we can't easily get the docstring
        #                     tasks[task_name] = "Docstring not available for worker-only task"
        # except CeleryError as e:
        #     logger.warning(f"Celery error while inspecting workers: {str(e)}")
        # except Exception as e:
        #     logger.warning(f"Unexpected error while inspecting workers: {str(e)}")

        # Filter out Celery's internal tasks
        return {
            task: description
            for task, description in tasks.items()
            if task.startswith("opencontractserver.tasks.data_extract_tasks")
        }

    corpus_stats = graphene.Field(CorpusStatsType, corpus_id=graphene.ID(required=True))

    def resolve_corpus_stats(self, info, corpus_id):

        total_docs = 0
        total_annotations = 0
        total_comments = 0
        total_analyses = 0
        total_extracts = 0

        corpus_pk = from_global_id(corpus_id)[1]
        corpuses = Corpus.objects.visible_to_user(info.context.user).filter(
            id=corpus_pk
        )

        if corpuses.count() == 1:
            corpus = corpuses[0]
            total_docs = corpus.documents.all().count()
            total_annotations = corpus.annotations.all().count()
            total_comments = UserFeedback.objects.filter(
                commented_annotation__corpus=corpus
            ).count()
            total_analyses = corpus.analyses.all().count()
            total_extracts = corpus.extracts.all().count()

        return CorpusStatsType(
            total_docs=total_docs,
            total_annotations=total_annotations,
            total_comments=total_comments,
            total_analyses=total_analyses,
            total_extracts=total_extracts,
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

    @login_required
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
            # If mimetype is provided, get compatible components
            components_data = get_components_by_mimetype(mimetype.value, detailed=True)
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
                    component_info = PipelineComponentType(
                        name=component_cls.__name__,
                        title=metadata.get("title", ""),
                        module_name=metadata.get("module_name", ""),
                        description=metadata.get("description", ""),
                        author=metadata.get("author", ""),
                        dependencies=metadata.get("dependencies", []),
                        supported_file_types=[
                            FileTypeEnumModel(ft).value
                            for ft in metadata.get("supported_file_types", [])
                        ],
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

    @login_required
    def resolve_conversations(self, info, **kwargs):
        """
        Resolver to fetch Conversations along with their Messages.

        Args:
            info: GraphQL execution info.
            **kwargs: Filter arguments passed through DjangoFilterConnectionField

        Returns:
            QuerySet[Conversation]: Filtered queryset of conversations
        """
        from django.db.models import Prefetch

        from opencontractserver.conversations.models import ChatMessage, Conversation

        return (
            Conversation.objects.visible_to_user(info.context.user)
            .prefetch_related(
                Prefetch(
                    "chat_messages",
                    queryset=ChatMessage.objects.order_by("created_at"),
                )
            )
            .order_by("-created")
        )

    # DOCUMENT RELATIONSHIP RESOLVERS #####################################
    document_relationships = DjangoFilterConnectionField(
        DocumentRelationshipType,
        filterset_class=DocumentRelationshipFilter,
        corpus_id=graphene.ID(required=False),
        document_id=graphene.ID(required=False),
    )

    @login_required
    def resolve_document_relationships(self, info, **kwargs):
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

    def resolve_documentrelationship(self, info, **kwargs):
        django_pk = from_global_id(kwargs.get("id", None))[1]
        try:
            return DocumentRelationship.objects.visible_to_user(info.context.user).get(
                id=django_pk
            )
        except DocumentRelationship.DoesNotExist:
            return None

    # Also add a bulk resolver similar to bulk_doc_relationships_in_corpus
    bulk_doc_relationships = graphene.Field(
        graphene.List(DocumentRelationshipType),
        corpus_id=graphene.ID(required=False),
        document_id=graphene.ID(required=True),
        relationship_type=graphene.String(required=False),
    )

    @login_required
    def resolve_bulk_doc_relationships(self, info, document_id, **kwargs):
        # Start with base queryset based on user permissions
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
        """
        Resolver for notes that returns notes visible to the current user.
        Can be filtered by title, content, document_id, and annotation_id.
        """
        from opencontractserver.annotations.models import Note

        # Start with base queryset using consistent permission filtering
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
        try:
            return Note.objects.visible_to_user(info.context.user).get(id=django_pk)
        except Note.DoesNotExist:
            return None

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
            order_by (Optional[str]): Field to order by. Defaults to "created_at"
                Supported fields: created_at, -created_at, msg_type, -msg_type,
                modified, -modified
            **kwargs: Additional filter arguments

        Returns:
            QuerySet[ChatMessage]: Filtered and ordered chat messages
        """
        from opencontractserver.conversations.models import ChatMessage

        # Use consistent permission filtering
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

    @login_required
    def resolve_chat_message(self, info, **kwargs):
        try:
            django_pk = from_global_id(kwargs.get("id", None))[1]
            user = info.context.user

            if user.is_superuser:
                return ChatMessage.objects.get(pk=django_pk)
            elif user.is_anonymous:
                return ChatMessage.objects.get(Q(pk=django_pk) & Q(is_public=True))
            else:
                return ChatMessage.objects.get(
                    Q(pk=django_pk) & (Q(creator=user) | Q(is_public=True))
                )
        except ChatMessage.DoesNotExist:
            return None

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
        from opencontractserver.corpuses.models import CorpusAction

        # Use consistent permission filtering
        queryset = CorpusAction.objects.visible_to_user(info.context.user)

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
