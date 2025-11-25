#  Copyright (C) 2022  John Scrudato
#  License: Apache 2

import django_filters
from django.contrib.auth import get_user_model
from django.db.models import Q
from django_filters import OrderingFilter
from django_filters import rest_framework as filters
from graphql_relay import from_global_id

from opencontractserver.analyzer.models import Analysis, Analyzer, GremlinEngine
from opencontractserver.annotations.models import (
    Annotation,
    AnnotationLabel,
    LabelSet,
    Relationship,
)
from opencontractserver.badges.models import Badge, UserBadge
from opencontractserver.conversations.models import ChatMessage, Conversation
from opencontractserver.corpuses.models import Corpus, CorpusQuery
from opencontractserver.documents.models import Document, DocumentRelationship
from opencontractserver.extracts.models import Column, Datacell, Extract, Fieldset
from opencontractserver.users.models import Assignment, UserExport

User = get_user_model()


class GremlinEngineFilter(django_filters.FilterSet):
    class Meta:
        model = GremlinEngine
        fields = {"url": ["exact"]}


class AnalyzerFilter(django_filters.FilterSet):
    analyzer_id = filters.CharFilter(method="filter_by_analyzer_id")

    def filter_by_analyzer_id(self, queryset, info, value):
        return queryset.filter(id=value)

    hosted_by_gremlin_engine_id = filters.CharFilter(
        method="filter_by_host_gremlin_engine"
    )

    used_in_analysis_ids = filters.CharFilter(method="filter_by_used_in_analysis_ids")

    def filter_by_used_in_analysis_ids(self, queryset, info, value):
        analysis_pks = [
            int(from_global_id(value)[1])
            for value in list(filter(lambda raw_id: len(raw_id) > 0, value.split(",")))
        ]
        return queryset.filter(analysis__in=analysis_pks)

    def filter_by_host_gremlin_engine(self, queryset, name, value):
        django_pk = from_global_id(value)[1]
        return queryset.filter(host_gremlin_id=django_pk)

    class Meta:
        model = Analyzer
        fields = {
            "id": ["contains", "exact"],
            "description": ["contains"],
            "disabled": ["exact"],
        }


class AnalysisFilter(django_filters.FilterSet):
    #####################################################################
    # Filter by analyses that have received callbacks
    received_callback_results = filters.BooleanFilter(
        method="filter_by_received_callback_results"
    )

    def filter_by_received_callback_results(self, queryset, info, value):
        return queryset.filter(received_callback_file__isnull=value)

    ######################################################################
    # Filter by the corpus the analysis was performed on
    analyzed_corpus_id = filters.CharFilter(method="filter_by_analyzed_corpus_id")

    def filter_by_analyzed_corpus_id(self, queryset, info, value):
        corpus_pk = from_global_id(value)[1]
        return queryset.filter(analyzed_corpus_id=corpus_pk)

    #####################################################################
    # Filter to analyses that include a certain document
    analyzed_document_id = filters.CharFilter(method="filter_by_analyzed_document_id")

    def filter_by_analyzed_document_id(self, queryset, info, value):
        doc_pk = from_global_id(value)[1]
        return queryset.filter(analyzed_documents__id=doc_pk)

    #####################################################################
    # Text Search
    search_text = django_filters.CharFilter(method="filter_by_search_text")

    def filter_by_search_text(self, queryset, info, value):
        return queryset.filter(
            Q(analyzer__description__icontains=value)
            | Q(analyzer__manifest__metadata__id__icontains=value)
        )

    class Meta:
        model = Analysis
        fields = {
            "analyzed_corpus": ["isnull"],
            "analysis_started": ["gte", "lte"],
            "analysis_completed": ["gte", "lte"],
            "status": ["exact"],
        }


class CorpusFilter(django_filters.FilterSet):
    text_search = filters.CharFilter(method="text_search_method")

    def text_search_method(self, queryset, name, value):
        return queryset.filter(
            Q(description__contains=value) | Q(title__contains=value)
        )

    uses_labelset_id = filters.CharFilter(method="uses_labelset_id_method")

    def uses_labelset_id_method(self, queryset, name, value):
        django_pk = from_global_id(value)[1]
        return queryset.filter(label_set_id=django_pk)

    class Meta:
        model = Corpus
        fields = {
            "description": ["exact", "contains"],
            "id": ["exact"],
            "title": ["contains"],
        }


class AnnotationFilter(django_filters.FilterSet):
    uses_label_from_labelset_id = django_filters.CharFilter(
        method="filter_by_label_from_labelset_id"
    )

    def filter_by_label_from_labelset_id(self, queryset, info, value):
        django_pk = from_global_id(value)[1]
        return queryset.filter(annotation_label__included_in_labelset=django_pk)

    created_by_analysis_ids = django_filters.CharFilter(
        method="filter_by_created_by_analysis_ids"
    )

    def filter_by_created_by_analysis_ids(self, queryset, info, value):

        # print(f"filter_by_created_by_analysis_ids - value: {value}")

        analysis_ids = value.split(",")
        if "~~MANUAL~~" in analysis_ids:
            analysis_ids = filter(lambda id: id != "~~MANUAL~~", analysis_ids)
            analysis_pks = [int(from_global_id(value)[1]) for value in analysis_ids]
            return queryset.filter(
                Q(analysis__isnull=True) | Q(analysis_id__in=analysis_pks)
            )
        else:
            analysis_pks = [int(from_global_id(value)[1]) for value in analysis_ids]
            return queryset.filter(analysis_id__in=analysis_pks)

    created_with_analyzer_id = django_filters.CharFilter(
        method="filter_by_created_with_analyzer_id"
    )

    def filter_by_created_with_analyzer_id(self, queryset, info, value):
        analyzer_ids = value.split(",")
        if "~~MANUAL~~" in analyzer_ids:
            analyzer_ids = filter(
                lambda analyzer_id: analyzer_id != "~~MANUAL~~", analyzer_ids
            )
            return queryset.filter(
                Q(analysis__isnull=True) | Q(analysis__analyzer_id__in=analyzer_ids)
            )
        elif len(analyzer_ids) > 0:
            return queryset.filter(analysis__analyzer_id__in=analyzer_ids)
        else:
            return queryset

    order_by = OrderingFilter(fields=(("modified", "modified"),))

    class Meta:
        model = Annotation
        fields = {
            "raw_text": ["contains"],
            "annotation_label_id": ["exact"],
            "annotation_label__text": ["exact", "contains"],
            "annotation_label__description": ["contains"],
            "annotation_label__label_type": ["exact"],
            "analysis": ["isnull"],
            "document_id": ["exact"],
            "corpus_id": ["exact"],
            "structural": ["exact"],
        }


class LabelFilter(django_filters.FilterSet):
    used_in_labelset_id = django_filters.CharFilter(method="filter_by_labelset_id")
    used_in_labelset_for_corpus_id = django_filters.CharFilter(
        method="filter_by_used_in_labelset_for_corpus_id"
    )
    used_in_analysis_ids = django_filters.CharFilter(
        method="filter_by_used_in_analysis_ids"
    )

    def filter_by_used_in_analysis_ids(self, queryset, info, value):
        analysis_pks = [from_global_id(value)[1] for value in value.split(",")]
        analyzer_pks = list(
            Analysis.objects.filter(id__in=analysis_pks)
            .values_list("analyzer_id", flat=True)
            .distinct()
        )
        return queryset.filter(analyzer_id__in=analyzer_pks)

    def filter_by_created_by_analysis_ids(self, queryset, info, value):
        analysis_pks = [from_global_id(value)[1] for value in value.split(",")]
        return queryset.filter(analysis_id__in=analysis_pks)

    def filter_by_labelset_id(self, queryset, name, value):
        django_pk = from_global_id(value)[1]
        return queryset.filter(included_in_labelset__pk=django_pk)

    def filter_by_used_in_labelset_for_corpus_id(self, queryset, name, value):

        # print(f"Raw corpus id: {value}")
        django_pk = from_global_id(value)[1]
        # print("Lookup labels for pk", django_pk)
        queryset = queryset.filter(Q(included_in_labelset__used_by_corpus=django_pk))
        # print(
        #     "Filtered to values",
        #     queryset,
        # )
        return queryset.filter(included_in_labelset__used_by_corpus=django_pk)

    class Meta:
        model = AnnotationLabel
        fields = {
            "description": ["contains"],
            "text": ["exact", "contains"],
            "label_type": ["exact"],
        }


class LabelsetFilter(django_filters.FilterSet):
    text_search = filters.CharFilter(method="text_search_method")

    def text_search_method(self, queryset, name, value):
        return queryset.filter(
            Q(description__contains=value) | Q(title__contains=value)
        )

    labelset_id = filters.CharFilter(method="labelset_id_method")

    def labelset_id_method(self, queryset, name, value):
        django_pk = from_global_id(value)[1]
        return queryset.filter(id=django_pk)

    class Meta:
        model = LabelSet
        fields = {
            "id": ["exact"],
            "description": ["contains"],
            "title": ["exact", "contains"],
        }


class RelationshipFilter(django_filters.FilterSet):
    # Old-style filter when relationships let you cross documents. Think this creates too taxing a query on the
    # Database. If we need document-level relationships, we can create a new model for that.
    # document_id = django_filters.CharFilter(method='filter_document_id')
    # def filter_document_id(self, queryset, name, value):
    #     document_pk = from_global_id(value)[1]
    #     return queryset.filter((Q(creator=self.request.user) | Q(is_public=True)) &
    #                            (Q(source_annotations__source_node_in_relationship__document_id=document_pk) |
    #                             Q(target_annotations__source_node_in_relationship__document_id=document_pk)))

    class Meta:
        model = Relationship
        fields = {
            "relationship_label": ["exact"],
            "corpus_id": ["exact"],
            "document_id": ["exact"],
        }


class AssignmentFilter(django_filters.FilterSet):
    document_id = django_filters.CharFilter(method="filter_document_id")

    def filter_document_id(self, queryset, name, value):
        django_pk = from_global_id(value)[1]
        return queryset.filter(document_id=django_pk)

    class Meta:
        model = Assignment
        fields = {"assignor__email": ["exact"], "assignee__email": ["exact"]}


class ExportFilter(django_filters.FilterSet):
    # This uses the django-filters ordering capabilities. Following filters available:
    #   1) created (earliest to latest)
    #   2) -created (latest to earliest)
    #   3) started (earliest to latest)
    #   4) -started (latest to earliest)
    #   5) finished (earliest to latest)
    #   6) -finished (latest to earliest)

    order_by_created = django_filters.OrderingFilter(
        # tuple-mapping retains order
        fields=(("created", "created"),)
    )

    order_by_started = django_filters.OrderingFilter(
        # tuple-mapping retains order
        fields=(("started", "started"),)
    )

    order_by_finished = django_filters.OrderingFilter(
        # tuple-mapping retains order
        fields=(("finished", "finished"),)
    )

    class Meta:
        model = UserExport
        fields = {
            "name": ["contains"],
            "id": ["exact"],
            "created": ["lte"],
            "started": ["lte"],
            "finished": ["lte"],
        }


class DocumentFilter(django_filters.FilterSet):
    company_search = filters.CharFilter(method="company_name_search")
    has_pdf = filters.BooleanFilter(method="has_pdf_search")
    has_annotations_with_ids = filters.CharFilter(
        method="handle_has_annotations_with_ids"
    )
    in_corpus_with_id = filters.CharFilter(method="in_corpus")
    in_folder_id = filters.CharFilter(method="in_folder")
    has_label_with_title = filters.CharFilter(method="has_label_title")
    has_label_with_id = filters.CharFilter(method="has_label_id")
    text_search = filters.CharFilter(method="naive_text_search")

    def handle_has_annotations_with_ids(self, queryset, info, value):
        annotation_pks = [from_global_id(val)[1] for val in value.split(",")]
        return queryset.filter(doc_annotation__in=annotation_pks)

    def filter_queryset(self, queryset):
        return super().filter_queryset(queryset).distinct()

    def naive_text_search(self, queryset, name, value):
        return queryset.filter(Q(description__contains=value)).distinct()

    def has_pdf_search(self, queryset, name, value):
        # Filter to analyzed docs only (has meta_data value)
        if value:
            return queryset.exclude(Q(pdf_file="") | Q(pdf_file__exact=None))
        # Filter to un-analyzed docs only (has no meta_data value)
        else:
            return queryset.filter(Q(pdf_file="") | Q(pdf_file__exact=None))

    def in_corpus(self, queryset, name, value):
        return queryset.filter(corpus=from_global_id(value)[1]).distinct()

    def in_folder(self, queryset, name, value):
        """
        Filter documents by folder assignment.
        Special handling: value="__root__" returns documents in corpus root (no folder).
        Otherwise filters to specific folder ID.
        """
        import logging

        from opencontractserver.corpuses.models import CorpusDocumentFolder

        logger = logging.getLogger(__name__)

        logger.info(f"[QUERY] in_folder filter called with value: {value}")

        if value == "__root__":
            # Get corpus_id from earlier filter (must have in_corpus_with_id set)
            # For root documents, we need to exclude documents that have folder assignments
            # This requires knowing the corpus context
            result = queryset.filter(
                ~Q(
                    id__in=CorpusDocumentFolder.objects.filter(
                        folder__isnull=False
                    ).values_list("document_id", flat=True)
                )
            )
            logger.info(f"[QUERY] Filtered to root folder, count: {result.count()}")
            return result
        else:
            folder_pk = from_global_id(value)[1]
            doc_ids = list(
                CorpusDocumentFolder.objects.filter(folder_id=folder_pk).values_list(
                    "document_id", flat=True
                )
            )
            logger.info(
                f"[QUERY] Filtering to folder {folder_pk}, found {len(doc_ids)} document assignments"
            )
            result = queryset.filter(id__in=doc_ids).distinct()
            logger.info(f"[QUERY] After filter, result count: {result.count()}")
            return result

    def has_label_title(self, queryset, name, value):
        return queryset.filter(annotation__annotation_label__title__contains=value)

    def has_label_id(self, queryset, name, value):
        return queryset.filter(
            doc_annotation__annotation_label_id=from_global_id(value)[1]
        )

    class Meta:
        model = Document
        fields = {
            "description": ["exact", "contains"],
            "id": ["exact"],
        }


class FieldsetFilter(django_filters.FilterSet):
    class Meta:
        model = Fieldset
        fields = {
            "name": ["exact", "contains"],
            "description": ["contains"],
        }


class ColumnFilter(django_filters.FilterSet):
    class Meta:
        model = Column
        fields = {
            "query": ["contains"],
            "match_text": ["contains"],
            "output_type": ["exact"],
            "limit_to_label": ["exact"],
        }


class ExtractFilter(django_filters.FilterSet):
    class Meta:
        model = Extract
        fields = {
            "corpus_action": ["isnull"],
            "name": ["exact", "contains"],
            "created": ["lte", "gte"],
            "started": ["lte", "gte"],
            "finished": ["lte", "gte"],
            "corpus": ["exact"],
        }


class CorpusQueryFilter(django_filters.FilterSet):
    class Meta:
        model = CorpusQuery
        fields = {"corpus_id": ["exact"]}


class DatacellFilter(django_filters.FilterSet):

    in_corpus_with_id = filters.CharFilter(method="in_corpus")
    for_document_with_id = filters.CharFilter(method="for_document")

    def in_corpus(self, queryset, name, value):
        return queryset.filter(corpus=from_global_id(value)[1]).distinct()

    def for_document(self, queryset, name, value):
        return queryset.filter(documents_id=from_global_id(value)[1]).distinct()

    class Meta:
        model = Datacell
        fields = {
            "data_definition": ["exact"],
            "started": ["lte", "gte"],
            "completed": ["lte", "gte"],
            "failed": ["lte", "gte"],
        }


class DocumentRelationshipFilter(django_filters.FilterSet):
    """Filter set for DocumentRelationship model."""

    class Meta:
        model = DocumentRelationship
        fields = [
            "relationship_type",
            "source_document",
            "target_document",
            "annotation_label",
            "creator",
            "is_public",
        ]


class ConversationFilter(django_filters.FilterSet):
    """Filter set for Conversation model."""

    document_id = filters.CharFilter(method="filter_by_document_id")
    corpus_id = filters.CharFilter(method="filter_by_corpus_id")

    def filter_by_document_id(self, queryset, name, value):
        """Filter conversations by document ID."""
        django_pk = from_global_id(value)[1]
        return queryset.filter(chat_with_document_id=django_pk)

    def filter_by_corpus_id(self, queryset, name, value):
        """Filter conversations by corpus ID."""
        django_pk = from_global_id(value)[1]
        return queryset.filter(chat_with_corpus_id=django_pk)

    class Meta:
        model = Conversation
        fields = {
            "created_at": ["gte", "lte"],
            "title": ["contains"],
            "conversation_type": ["exact"],
        }


class ChatMessageFilter(django_filters.FilterSet):
    """Filter set for ChatMessage model."""

    class Meta:
        model = ChatMessage
        fields = {
            "msg_type": ["exact"],
            "conversation_id": ["exact"],
            "source_document_id": ["exact"],
            "created_at": ["gte", "lte"],
            "creator_id": ["exact"],
            "is_public": ["exact"],
        }


class BadgeFilter(django_filters.FilterSet):
    """Filter set for Badge model."""

    corpus_id = filters.CharFilter(method="filter_by_corpus_id")

    def filter_by_corpus_id(self, queryset, name, value):
        """Filter badges by corpus ID."""
        if value:
            django_pk = from_global_id(value)[1]
            return queryset.filter(corpus_id=django_pk)
        return queryset

    class Meta:
        model = Badge
        fields = {
            "badge_type": ["exact"],
            "is_auto_awarded": ["exact"],
            "name": ["contains", "exact"],
        }


class UserBadgeFilter(django_filters.FilterSet):
    """Filter set for UserBadge model."""

    user_id = filters.CharFilter(method="filter_by_user_id")
    badge_id = filters.CharFilter(method="filter_by_badge_id")
    corpus_id = filters.CharFilter(method="filter_by_corpus_id")

    def filter_by_user_id(self, queryset, name, value):
        """Filter user badges by user ID."""
        if value:
            django_pk = from_global_id(value)[1]
            return queryset.filter(user_id=django_pk)
        return queryset

    def filter_by_badge_id(self, queryset, name, value):
        """Filter user badges by badge ID."""
        if value:
            django_pk = from_global_id(value)[1]
            return queryset.filter(badge_id=django_pk)
        return queryset

    def filter_by_corpus_id(self, queryset, name, value):
        """Filter user badges by corpus ID."""
        if value:
            django_pk = from_global_id(value)[1]
            return queryset.filter(corpus_id=django_pk)
        return queryset

    class Meta:
        model = UserBadge
        fields = {
            "awarded_at": ["gte", "lte"],
        }


class AgentConfigurationFilter(django_filters.FilterSet):
    """Filter set for AgentConfiguration model."""

    corpus_id = filters.CharFilter(method="filter_by_corpus_id")

    def filter_by_corpus_id(self, queryset, name, value):
        """Filter agent configurations by corpus ID."""
        if value:
            django_pk = from_global_id(value)[1]
            return queryset.filter(corpus_id=django_pk)
        return queryset

    class Meta:
        from opencontractserver.agents.models import AgentConfiguration

        model = AgentConfiguration
        fields = {
            "scope": ["exact"],
            "is_active": ["exact"],
            "name": ["contains", "exact"],
        }
