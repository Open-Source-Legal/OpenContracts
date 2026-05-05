"""
GraphQL query mixin for annotation, relationship, label, labelset, and note queries.
"""

import logging
import re
from typing import Any

import graphene
from django.db.models import Prefetch, Q
from graphene import relay
from graphene_django.fields import DjangoConnectionField
from graphene_django.filter import DjangoFilterConnectionField
from graphql_jwt.decorators import login_required
from graphql_relay import from_global_id

from config.graphql.filters import LabelFilter, LabelsetFilter, RelationshipFilter
from config.graphql.graphene_types import (
    AnnotationLabelType,
    AnnotationType,
    LabelSetType,
    NoteType,
    PageAwareAnnotationType,
    PdfPageInfoType,
    RelationshipType,
)
from config.graphql.ratelimits import get_user_tier_rate, graphql_ratelimit_dynamic
from opencontractserver.annotations.models import (
    Annotation,
    AnnotationLabel,
    LabelSet,
    Note,
    Relationship,
)
from opencontractserver.constants.annotations import (
    DOCUMENT_ANNOTATION_INDEX_LIMIT,
    MANUAL_ANNOTATION_SENTINEL,
)
from opencontractserver.documents.models import Document
from opencontractserver.types.enums import LabelType

logger = logging.getLogger(__name__)


class AnnotationQueryMixin:
    """Query fields and resolvers for annotation, relationship, label, labelset, and note queries."""

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
        corpus_action_isnull=graphene.Boolean(),
        agent_created=graphene.Boolean(),
        document_id=graphene.ID(),
        corpus_id=graphene.ID(),
        structural=graphene.Boolean(),
        uses_label_from_labelset_id=graphene.ID(),
        created_by_analysis_ids=graphene.String(),
        created_with_analyzer_id=graphene.String(),
        order_by=graphene.String(),
        # Higher limit for Document Annotation Index which needs full hierarchy
        max_limit=DOCUMENT_ANNOTATION_INDEX_LIMIT,
    )

    @graphql_ratelimit_dynamic(get_rate=get_user_tier_rate("READ_MEDIUM"))
    def resolve_annotations(
        self,
        info,
        analysis_isnull=None,
        structural=None,
        corpus_action_isnull=None,
        agent_created=None,
        **kwargs,
    ) -> Any:
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
            "document__creator",
            "corpus",
            "analysis",
            "analysis__analyzer",
            "corpus_action",
            "structural_set",
        ).prefetch_related(
            Prefetch(
                "structural_set__documents",
                queryset=Document.objects.select_related("creator"),
            ),
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
            if MANUAL_ANNOTATION_SENTINEL in analysis_id_list:
                logger.info("Including manual annotations in filter")
                analysis_id_list = [
                    id for id in analysis_id_list if id != MANUAL_ANNOTATION_SENTINEL
                ]
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
            if MANUAL_ANNOTATION_SENTINEL in analyzer_id_list:
                logger.info("Including manual annotations in filter")
                analyzer_id_list = [
                    id for id in analyzer_id_list if id != MANUAL_ANNOTATION_SENTINEL
                ]
                analyzer_pks = [
                    int(from_global_id(id)[1])
                    for id in analyzer_id_list
                    if id != MANUAL_ANNOTATION_SENTINEL
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

        # Filter by corpus_action
        if corpus_action_isnull is not None:
            queryset = queryset.filter(corpus_action__isnull=corpus_action_isnull)

        # Combined agent filter: annotations created by analysis OR corpus action
        if agent_created is not None:
            agent_q = Q(analysis__isnull=False) | Q(corpus_action__isnull=False)
            if agent_created:
                queryset = queryset.filter(agent_q)
            else:
                queryset = queryset.exclude(agent_q)

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

    def resolve_bulk_doc_relationships_in_corpus(
        self, info, corpus_id, document_id
    ) -> Any:
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

    def resolve_bulk_doc_annotations_in_corpus(self, info, corpus_id, **kwargs) -> Any:

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
    def resolve_page_annotations(
        self, info, document_id, corpus_id=None, **kwargs
    ) -> Any:

        doc_django_pk = int(from_global_id(document_id)[1])

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
        pages: list[int] = []  # Parsed page list from page_number_list (1-indexed)

        # Always parse page_number_list when provided so `pages` is available
        # for the filtering step below, regardless of which branch sets current_page.
        if page_number_list is not None:
            if re.search(r"^(?:\d+,)*\d+$", page_number_list):
                pages = [int(page) for page in page_number_list.split(",")]
            else:
                logger.warning(
                    f"Invalid format for page_number_list: {page_number_list}"
                )

        if kwargs.get("current_page", None) is not None:
            current_page = int(kwargs["current_page"])
            logger.info(
                f"resolve_page_annotations - Using provided current_page: {current_page}"
            )
        elif pages:
            current_page = pages[-1]
            logger.info(
                f"resolve_page_annotations - Using last page from page_number_list: {current_page}"
            )
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

    def resolve_annotation(self, info, **kwargs) -> Any:
        django_pk = from_global_id(kwargs["id"])[1]
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

    def resolve_relationships(self, info, **kwargs) -> Any:
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

    def resolve_relationship(self, info, **kwargs) -> Any:
        django_pk = from_global_id(kwargs["id"])[1]
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

    def resolve_annotation_labels(self, info, **kwargs) -> Any:
        return AnnotationLabel.objects.visible_to_user(info.context.user)

    annotation_label = relay.Node.Field(AnnotationLabelType)

    def resolve_annotation_label(self, info, **kwargs) -> Any:
        django_pk = from_global_id(kwargs["id"])[1]
        return AnnotationLabel.objects.visible_to_user(info.context.user).get(
            id=django_pk
        )

    # LABEL SET RESOLVERS #####################################

    labelsets = DjangoFilterConnectionField(
        LabelSetType, filterset_class=LabelsetFilter
    )

    @graphql_ratelimit_dynamic(get_rate=get_user_tier_rate("READ_LIGHT"))
    def resolve_labelsets(self, info, **kwargs) -> Any:
        return LabelSet.objects.visible_to_user(info.context.user)

    labelset = relay.Node.Field(LabelSetType)

    def resolve_labelset(self, info, **kwargs) -> Any:
        django_pk = from_global_id(kwargs["id"])[1]
        return LabelSet.objects.visible_to_user(info.context.user).get(id=django_pk)

    default_labelset = graphene.Field(
        LabelSetType,
        description=(
            "The install-wide default LabelSet (is_default=True), or null if "
            "none has been seeded yet or the current user cannot see it. "
            "Used by the new-corpus modal to pre-fill the label set field."
        ),
    )

    @login_required
    def resolve_default_labelset(self, info, **kwargs) -> Any:
        return (
            LabelSet.objects.visible_to_user(info.context.user)
            .filter(is_default=True)
            .first()
        )

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
    def resolve_notes(self, info, **kwargs) -> Any:
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
    def resolve_note(self, info, **kwargs) -> Any:
        django_pk = from_global_id(kwargs["id"])[1]
        return Note.objects.visible_to_user(info.context.user).get(id=django_pk)
