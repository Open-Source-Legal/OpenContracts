#  Copyright (C) 2022  John Scrudato
#  License: MIT

from __future__ import annotations

from typing import Any

import django_filters
from django.contrib.auth import get_user_model
from django.db.models import Q, QuerySet
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
from opencontractserver.constants.annotations import MANUAL_ANNOTATION_SENTINEL
from opencontractserver.constants.document_processing import MARKDOWN_MIME_TYPE
from opencontractserver.conversations.models import (
    ChatMessage,
    Conversation,
    ModerationAction,
)
from opencontractserver.corpuses.models import Corpus, CorpusCategory
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

    def filter_by_analyzer_id(
        self, queryset: QuerySet, name: str, value: Any
    ) -> QuerySet:
        return queryset.filter(id=value)

    hosted_by_gremlin_engine_id = filters.CharFilter(
        method="filter_by_host_gremlin_engine"
    )

    used_in_analysis_ids = filters.CharFilter(method="filter_by_used_in_analysis_ids")

    def filter_by_used_in_analysis_ids(
        self, queryset: QuerySet, name: str, value: Any
    ) -> QuerySet:
        analysis_pks = [
            int(from_global_id(value)[1])
            for value in list(filter(lambda raw_id: len(raw_id) > 0, value.split(",")))
        ]
        return queryset.filter(analysis__in=analysis_pks)

    def filter_by_host_gremlin_engine(
        self, queryset: QuerySet, name: str, value: Any
    ) -> QuerySet:
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

    def filter_by_received_callback_results(
        self, queryset: QuerySet, name: str, value: Any
    ) -> QuerySet:
        return queryset.filter(received_callback_file__isnull=value)

    ######################################################################
    # Filter by the corpus the analysis was performed on
    analyzed_corpus_id = filters.CharFilter(method="filter_by_analyzed_corpus_id")

    def filter_by_analyzed_corpus_id(
        self, queryset: QuerySet, name: str, value: Any
    ) -> QuerySet:
        corpus_pk = from_global_id(value)[1]
        return queryset.filter(analyzed_corpus_id=corpus_pk)

    #####################################################################
    # Filter to analyses that include a certain document
    analyzed_document_id = filters.CharFilter(method="filter_by_analyzed_document_id")

    def filter_by_analyzed_document_id(
        self, queryset: QuerySet, name: str, value: Any
    ) -> QuerySet:
        doc_pk = from_global_id(value)[1]
        return queryset.filter(analyzed_documents__id=doc_pk)

    #####################################################################
    # Text Search
    search_text = django_filters.CharFilter(method="filter_by_search_text")

    def filter_by_search_text(
        self, queryset: QuerySet, name: str, value: Any
    ) -> QuerySet:
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

    def text_search_method(self, queryset: QuerySet, name: str, value: Any) -> QuerySet:
        return queryset.filter(
            Q(description__contains=value) | Q(title__contains=value)
        )

    uses_labelset_id = filters.CharFilter(method="uses_labelset_id_method")

    def uses_labelset_id_method(
        self, queryset: QuerySet, name: str, value: Any
    ) -> QuerySet:
        django_pk = from_global_id(value)[1]
        return queryset.filter(label_set_id=django_pk)

    categories = django_filters.ModelMultipleChoiceFilter(
        queryset=CorpusCategory.objects.all(),
        field_name="categories",
    )

    # Tab filters used by the Corpuses view. The base queryset is already
    # restricted to corpuses visible to the requesting user (via
    # Corpus.objects.visible_to_user(user) in the resolver), so these flags
    # only need to narrow that visible set.
    #
    # Contract: each flag is treated as opt-in only. Passing `False` is a
    # no-op (returns the unfiltered queryset) — these methods do NOT invert
    # the filter. The Corpuses tab UI sends exactly one flag per request, so
    # combining flags is undefined and intentionally not supported. Treating
    # `False` as a no-op (rather than raising) keeps the GraphQL surface
    # forgiving for older clients that may serialize defaults explicitly.
    mine = filters.BooleanFilter(method="mine_method")
    is_public = filters.BooleanFilter(method="is_public_method")
    shared_with_me = filters.BooleanFilter(method="shared_with_me_method")

    def mine_method(self, queryset: QuerySet, name: str, value: Any) -> QuerySet:
        if not value:
            return queryset
        user = getattr(self.request, "user", None)
        if user is None or not user.is_authenticated:
            return queryset.none()
        return queryset.filter(creator=user)

    def is_public_method(self, queryset: QuerySet, name: str, value: Any) -> QuerySet:
        if not value:
            return queryset
        return queryset.filter(is_public=True)

    def shared_with_me_method(
        self, queryset: QuerySet, name: str, value: Any
    ) -> QuerySet:
        if not value:
            return queryset
        user = getattr(self.request, "user", None)
        if user is None or not user.is_authenticated:
            return queryset.none()
        # "Shared" = visible to me, but neither created by me nor public.
        return queryset.exclude(creator=user).exclude(is_public=True)

    class Meta:
        model = Corpus
        fields = {
            "description": ["exact", "contains"],
            "id": ["exact"],
            "title": ["contains"],
        }


class CorpusCategoryFilter(django_filters.FilterSet):
    """Filter for CorpusCategory."""

    class Meta:
        model = CorpusCategory
        fields = {
            "name": ["exact", "contains"],
            "description": ["contains"],
        }


class AnnotationFilter(django_filters.FilterSet):
    uses_label_from_labelset_id = django_filters.CharFilter(
        method="filter_by_label_from_labelset_id"
    )

    def filter_by_label_from_labelset_id(
        self, queryset: QuerySet, name: str, value: Any
    ) -> QuerySet:
        django_pk = from_global_id(value)[1]
        return queryset.filter(annotation_label__included_in_labelset=django_pk)

    created_by_analysis_ids = django_filters.CharFilter(
        method="filter_by_created_by_analysis_ids"
    )

    def filter_by_created_by_analysis_ids(
        self, queryset: QuerySet, name: str, value: Any
    ) -> QuerySet:

        # print(f"filter_by_created_by_analysis_ids - value: {value}")

        analysis_ids = value.split(",")
        if MANUAL_ANNOTATION_SENTINEL in analysis_ids:
            analysis_ids = filter(
                lambda id: id != MANUAL_ANNOTATION_SENTINEL, analysis_ids
            )
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

    def filter_by_created_with_analyzer_id(
        self, queryset: QuerySet, name: str, value: Any
    ) -> QuerySet:
        analyzer_ids = value.split(",")
        if MANUAL_ANNOTATION_SENTINEL in analyzer_ids:
            analyzer_ids = filter(
                lambda analyzer_id: analyzer_id != MANUAL_ANNOTATION_SENTINEL,
                analyzer_ids,
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

    def filter_by_used_in_analysis_ids(
        self, queryset: QuerySet, name: str, value: Any
    ) -> QuerySet:
        analysis_pks = [from_global_id(value)[1] for value in value.split(",")]
        analyzer_pks = list(
            Analysis.objects.filter(id__in=analysis_pks)
            .values_list("analyzer_id", flat=True)
            .distinct()
        )
        return queryset.filter(analyzer_id__in=analyzer_pks)

    def filter_by_created_by_analysis_ids(
        self, queryset: QuerySet, name: str, value: Any
    ) -> QuerySet:
        analysis_pks = [from_global_id(value)[1] for value in value.split(",")]
        return queryset.filter(analysis_id__in=analysis_pks)

    def filter_by_labelset_id(
        self, queryset: QuerySet, name: str, value: Any
    ) -> QuerySet:
        django_pk = from_global_id(value)[1]
        return queryset.filter(included_in_labelset__pk=django_pk)

    def filter_by_used_in_labelset_for_corpus_id(
        self, queryset: QuerySet, name: str, value: Any
    ) -> QuerySet:

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

    def text_search_method(self, queryset: QuerySet, name: str, value: Any) -> QuerySet:
        return queryset.filter(
            Q(description__contains=value) | Q(title__contains=value)
        )

    labelset_id = filters.CharFilter(method="labelset_id_method")

    def labelset_id_method(self, queryset: QuerySet, name: str, value: Any) -> QuerySet:
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

    def filter_document_id(self, queryset: QuerySet, name: str, value: Any) -> QuerySet:
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
    include_caml = filters.BooleanFilter(method="handle_include_caml")

    def handle_has_annotations_with_ids(
        self, queryset: QuerySet, name: str, value: Any
    ) -> QuerySet:
        annotation_pks = [from_global_id(val)[1] for val in value.split(",")]
        return queryset.filter(doc_annotation__in=annotation_pks)

    def filter_queryset(self, queryset: QuerySet) -> QuerySet:
        qs = super().filter_queryset(queryset).distinct()
        # When filtering by corpus, exclude CAML/markdown files by default.
        # Corpus views pass includeCaml=true to show them; extractors and
        # analyzers omit the flag so CAML articles stay out of pipelines.
        #
        # Note: self.data values are Python-typed (bool, not str) because
        # graphene-django deserializes GraphQL arguments before populating
        # the filterset. The falsy check on include_caml is therefore safe.
        if self.data.get("in_corpus_with_id") and not self.data.get("include_caml"):
            qs = qs.exclude(file_type=MARKDOWN_MIME_TYPE)
        return qs

    def handle_include_caml(
        self, queryset: QuerySet, name: str, value: Any
    ) -> QuerySet:
        # Intentional no-op: the actual CAML exclusion lives in
        # filter_queryset() which checks both in_corpus_with_id and
        # include_caml together.  Passing includeCaml=false without a
        # corpus filter has no effect because CAML exclusion only
        # applies to corpus-scoped queries.
        return queryset

    def naive_text_search(self, queryset: QuerySet, name: str, value: Any) -> QuerySet:
        return queryset.filter(Q(description__contains=value)).distinct()

    def has_pdf_search(self, queryset: QuerySet, name: str, value: Any) -> QuerySet:
        # Filter to analyzed docs only (has meta_data value)
        if value:
            return queryset.exclude(Q(pdf_file="") | Q(pdf_file__exact=None))
        # Filter to un-analyzed docs only (has no meta_data value)
        else:
            return queryset.filter(Q(pdf_file="") | Q(pdf_file__exact=None))

    def in_corpus(self, queryset: QuerySet, name: str, value: Any) -> QuerySet:
        """
        Filter documents by corpus membership via DocumentPath.
        """
        from opencontractserver.documents.models import DocumentPath

        corpus_pk = from_global_id(value)[1]

        doc_ids = DocumentPath.objects.filter(
            corpus_id=corpus_pk, is_current=True, is_deleted=False
        ).values_list("document_id", flat=True)

        return queryset.filter(id__in=doc_ids).distinct()

    def in_folder(self, queryset: QuerySet, name: str, value: Any) -> QuerySet:
        """
        Filter documents by folder assignment.

        Uses DocumentPath as the source of truth for folder assignments.

        Special handling: value="__root__" returns documents in corpus root
        (no folder). Otherwise filters to a specific folder ID.

        Note: This filter works in conjunction with ``in_corpus``. The queryset
        is already filtered to documents in a specific corpus, so we just need
        to intersect with the folder's DocumentPath rows.
        """
        from opencontractserver.documents.models import DocumentPath

        if value == "__root__":
            # Root documents: those whose DocumentPath has folder=NULL.
            # Use a lazy values queryset so Django emits a SQL subquery for
            # ``__in`` instead of materialising IDs into Python.
            root_doc_ids = DocumentPath.objects.filter(
                folder__isnull=True, is_current=True, is_deleted=False
            ).values("document_id")
            # ``.distinct()`` mirrors the non-root branch and guards against
            # any pathological case where the same ``document_id`` appears in
            # multiple matching ``DocumentPath`` rows.
            return queryset.filter(id__in=root_doc_ids).distinct()

        # ``from_global_id`` returns a ``str`` PK; coerce to int so the
        # ``folder_id`` lookup matches the FK type.
        folder_pk = int(from_global_id(value)[1])
        doc_ids = DocumentPath.objects.filter(
            folder_id=folder_pk, is_current=True, is_deleted=False
        ).values("document_id")
        return queryset.filter(id__in=doc_ids).distinct()

    def has_label_title(self, queryset: QuerySet, name: str, value: Any) -> QuerySet:
        return queryset.filter(annotation__annotation_label__title__contains=value)

    def has_label_id(self, queryset: QuerySet, name: str, value: Any) -> QuerySet:
        return queryset.filter(
            doc_annotation__annotation_label_id=from_global_id(value)[1]
        )

    class Meta:
        model = Document
        fields = {
            "description": ["exact", "contains"],
            "id": ["exact"],
            "title": ["exact", "contains"],
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


class DatacellFilter(django_filters.FilterSet):

    in_corpus_with_id = filters.CharFilter(method="in_corpus")
    for_document_with_id = filters.CharFilter(method="for_document")

    def in_corpus(self, queryset: QuerySet, name: str, value: Any) -> QuerySet:
        return queryset.filter(corpus=from_global_id(value)[1]).distinct()

    def for_document(self, queryset: QuerySet, name: str, value: Any) -> QuerySet:
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
    has_corpus = filters.BooleanFilter(method="filter_has_corpus")
    has_document = filters.BooleanFilter(method="filter_has_document")

    def filter_by_document_id(
        self, queryset: QuerySet, name: str, value: Any
    ) -> QuerySet:
        """Filter conversations by document ID."""
        django_pk = from_global_id(value)[1]
        return queryset.filter(chat_with_document_id=django_pk)

    def filter_by_corpus_id(
        self, queryset: QuerySet, name: str, value: Any
    ) -> QuerySet:
        """Filter conversations by corpus ID."""
        django_pk = from_global_id(value)[1]
        return queryset.filter(chat_with_corpus_id=django_pk)

    def filter_has_corpus(self, queryset: QuerySet, name: str, value: Any) -> QuerySet:
        """Filter conversations that have/don't have a corpus."""
        if value:
            return queryset.filter(chat_with_corpus__isnull=False)
        return queryset.filter(chat_with_corpus__isnull=True)

    def filter_has_document(
        self, queryset: QuerySet, name: str, value: Any
    ) -> QuerySet:
        """Filter conversations that have/don't have a document."""
        if value:
            return queryset.filter(chat_with_document__isnull=False)
        return queryset.filter(chat_with_document__isnull=True)

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

    def filter_by_corpus_id(
        self, queryset: QuerySet, name: str, value: Any
    ) -> QuerySet:
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

    def filter_by_user_id(self, queryset: QuerySet, name: str, value: Any) -> QuerySet:
        """Filter user badges by user ID."""
        if value:
            django_pk = from_global_id(value)[1]
            return queryset.filter(user_id=django_pk)
        return queryset

    def filter_by_badge_id(self, queryset: QuerySet, name: str, value: Any) -> QuerySet:
        """Filter user badges by badge ID."""
        if value:
            django_pk = from_global_id(value)[1]
            return queryset.filter(badge_id=django_pk)
        return queryset

    def filter_by_corpus_id(
        self, queryset: QuerySet, name: str, value: Any
    ) -> QuerySet:
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

    def filter_by_corpus_id(
        self, queryset: QuerySet, name: str, value: Any
    ) -> QuerySet:
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


class ModerationActionFilter(django_filters.FilterSet):
    """Filter set for ModerationAction model."""

    class Meta:
        model = ModerationAction
        fields = {
            "action_type": ["exact", "in"],
            "created": ["gte", "lte"],
        }
