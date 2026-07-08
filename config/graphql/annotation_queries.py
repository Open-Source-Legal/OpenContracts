"""Generated strawberry GraphQL module (graphene migration).

Shape-generated from the graphene schema; stub functions marked PORT(...)
carry the ported business logic. See config/graphql_new/manifest.json.
"""
from __future__ import annotations

import datetime
import decimal
import uuid
from typing import Annotated, Any, Optional

import strawberry

from config.graphql.core import permissions as core_permissions
from config.graphql.core.filtering import filterset_factory, setup_filterset
from config.graphql.core.mutations import drf_deletion, drf_mutation
from config.graphql.core.relay import (
    Node,
    get_node_from_global_id,
    make_connection_types,
    register_type,
    resolve_django_connection,
    resolve_django_list,
)
from config.graphql.core.scalars import BigInt, GenericScalar, JSONString
from config.graphql._util import coerce_enum, coerce_str, strip_unset
from config.graphql import enums

from config.graphql.filters import LabelFilter
from config.graphql.filters import LabelsetFilter
from config.graphql.filters import RelationshipFilter
from opencontractserver.annotations.models import Annotation
from opencontractserver.annotations.models import AnnotationLabel
from opencontractserver.annotations.models import CorpusReference
from opencontractserver.annotations.models import LabelSet
from opencontractserver.annotations.models import Note
from opencontractserver.annotations.models import Relationship


@strawberry.input(name="BBoxInputType", description='Map bounding-box input shared by both geographic queries.\n\nFields use standard map conventions: ``south <= north`` (degenerate\n``south > north`` boxes are rejected with a ``GraphQLError``); ``west``\nmay exceed ``east`` for boxes that cross the antimeridian (180°/-180°\nlongitude seam) and the resolver handles the wrap-around explicitly.')
class BBoxInputType:
    south: float = strawberry.field(name="south")
    west: float = strawberry.field(name="west")
    north: float = strawberry.field(name="north")
    east: float = strawberry.field(name="east")


def _resolve_GeographicAnnotationPinType_sample_document_ids(root, info, **kwargs):
    """PORT: config/graphql/annotation_queries.py:1302

    Port of GeographicAnnotationPinType.resolve_sample_document_ids
    """
    raise NotImplementedError("_resolve_GeographicAnnotationPinType_sample_document_ids not yet ported — see manifest")


@strawberry.type(name="GeographicAnnotationPinType", description='A single aggregated geographic pin returned to the map UI.\n\nMirrors :class:`GeographicPin` from the service layer one-to-one — the\nresolver projects the dataclass directly into this type via field\nresolvers below. ``label_type`` is a literal string ("country" /\n"state" / "city") rather than an enum so a future label-type expansion\ndoesn\'t break the schema.')
class GeographicAnnotationPinType:
    @strawberry.field(name="canonicalName")
    def canonical_name(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "canonical_name", None))
    @strawberry.field(name="labelType")
    def label_type(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "label_type", None))
    lat: float = strawberry.field(name="lat", default=None)
    lng: float = strawberry.field(name="lng", default=None)
    document_count: int = strawberry.field(name="documentCount", default=None)
    @strawberry.field(name="sampleDocumentIds")
    def sample_document_ids(self, info: strawberry.Info) -> Optional[list[Optional[strawberry.ID]]]:
        kwargs = strip_unset({})
        return _resolve_GeographicAnnotationPinType_sample_document_ids(self, info, **kwargs)


register_type("GeographicAnnotationPinType", GeographicAnnotationPinType, model=None)


def _resolve_Query_corpus_references(root, info, **kwargs):
    """PORT: config/graphql/annotation_queries.py:88

    Port of AnnotationQueryMixin.resolve_corpus_references
    """
    raise NotImplementedError("_resolve_Query_corpus_references not yet ported — see manifest")


def q_corpus_references(info: strawberry.Info, corpus_id: Annotated[strawberry.ID, strawberry.argument(name="corpusId")] = strawberry.UNSET, reference_type: Annotated[Optional[str], strawberry.argument(name="referenceType")] = strawberry.UNSET, canonical_key: Annotated[Optional[str], strawberry.argument(name="canonicalKey")] = strawberry.UNSET, document_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="documentId", description="Restrict to references touching this document on EITHER side (source mention's document or resolved target document) — the single-fetch shape the document References panel needs.")] = strawberry.UNSET, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Optional[Annotated["CorpusReferenceTypeConnection", strawberry.lazy("config.graphql.annotation_types")]]:
    kwargs = strip_unset({"corpus_id": corpus_id, "reference_type": reference_type, "canonical_key": canonical_key, "document_id": document_id, "offset": offset, "before": before, "after": after, "first": first, "last": last})
    resolved = _resolve_Query_corpus_references(None, info, **kwargs)
    return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="CorpusReferenceType", default_manager=CorpusReference._default_manager, )


def _resolve_Query_governance_graph(root, info, **kwargs):
    """PORT: config/ratelimit/decorators.py:151

    Port of AnnotationQueryMixin.resolve_governance_graph
    """
    raise NotImplementedError("_resolve_Query_governance_graph not yet ported — see manifest")


def q_governance_graph(info: strawberry.Info, corpus_id: Annotated[strawberry.ID, strawberry.argument(name="corpusId")] = strawberry.UNSET, limit: Annotated[Optional[int], strawberry.argument(name="limit")] = strawberry.UNSET) -> Optional[Annotated["GovernanceGraphType", strawberry.lazy("config.graphql.annotation_types")]]:
    kwargs = strip_unset({"corpus_id": corpus_id, "limit": limit})
    return _resolve_Query_governance_graph(None, info, **kwargs)


def _resolve_Query_wanted_authorities(root, info, **kwargs):
    """PORT: config/ratelimit/decorators.py:270

    Port of AnnotationQueryMixin.resolve_wanted_authorities
    """
    raise NotImplementedError("_resolve_Query_wanted_authorities not yet ported — see manifest")


def q_wanted_authorities(info: strawberry.Info, corpus_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="corpusId", description='Restrict the backlog to one corpus; omit for all visible.')] = strawberry.UNSET) -> list[Annotated["WantedAuthorityType", strawberry.lazy("config.graphql.annotation_types")]]:
    kwargs = strip_unset({"corpus_id": corpus_id})
    return _resolve_Query_wanted_authorities(None, info, **kwargs)


def _resolve_Query_authority_frontier_stats(root, info, **kwargs):
    """PORT: config/ratelimit/decorators.py:314

    Port of AnnotationQueryMixin.resolve_authority_frontier_stats
    """
    raise NotImplementedError("_resolve_Query_authority_frontier_stats not yet ported — see manifest")


def q_authority_frontier_stats(info: strawberry.Info, jurisdiction: Annotated[Optional[str], strawberry.argument(name="jurisdiction")] = strawberry.UNSET, authority_type: Annotated[Optional[str], strawberry.argument(name="authorityType")] = strawberry.UNSET, provider: Annotated[Optional[str], strawberry.argument(name="provider")] = strawberry.UNSET, authority: Annotated[Optional[str], strawberry.argument(name="authority")] = strawberry.UNSET, search: Annotated[Optional[str], strawberry.argument(name="search")] = strawberry.UNSET) -> Annotated["AuthorityFrontierStatsType", strawberry.lazy("config.graphql.annotation_types")]:
    kwargs = strip_unset({"jurisdiction": jurisdiction, "authority_type": authority_type, "provider": provider, "authority": authority, "search": search})
    return _resolve_Query_authority_frontier_stats(None, info, **kwargs)


def _resolve_Query_authority_mapping_stats(root, info, **kwargs):
    """PORT: config/ratelimit/decorators.py:360

    Port of AnnotationQueryMixin.resolve_authority_mapping_stats
    """
    raise NotImplementedError("_resolve_Query_authority_mapping_stats not yet ported — see manifest")


def q_authority_mapping_stats(info: strawberry.Info, search: Annotated[Optional[str], strawberry.argument(name="search")] = strawberry.UNSET) -> Annotated["AuthorityMappingStatsType", strawberry.lazy("config.graphql.annotation_types")]:
    kwargs = strip_unset({"search": search})
    return _resolve_Query_authority_mapping_stats(None, info, **kwargs)


def _resolve_Query_authority_namespace_stats(root, info, **kwargs):
    """PORT: config/ratelimit/decorators.py:404

    Port of AnnotationQueryMixin.resolve_authority_namespace_stats
    """
    raise NotImplementedError("_resolve_Query_authority_namespace_stats not yet ported — see manifest")


def q_authority_namespace_stats(info: strawberry.Info, search: Annotated[Optional[str], strawberry.argument(name="search")] = strawberry.UNSET) -> Annotated["AuthorityNamespaceStatsType", strawberry.lazy("config.graphql.annotation_types")]:
    kwargs = strip_unset({"search": search})
    return _resolve_Query_authority_namespace_stats(None, info, **kwargs)


def _resolve_Query_authority_namespace_detail(root, info, **kwargs):
    """PORT: config/ratelimit/decorators.py:410

    Port of AnnotationQueryMixin.resolve_authority_namespace_detail
    """
    raise NotImplementedError("_resolve_Query_authority_namespace_detail not yet ported — see manifest")


def q_authority_namespace_detail(info: strawberry.Info, prefix: Annotated[str, strawberry.argument(name="prefix")] = strawberry.UNSET) -> Optional[Annotated["AuthorityDetailType", strawberry.lazy("config.graphql.annotation_types")]]:
    kwargs = strip_unset({"prefix": prefix})
    return _resolve_Query_authority_namespace_detail(None, info, **kwargs)


def _resolve_Query_authority_source_providers(root, info, **kwargs):
    """PORT: config/ratelimit/decorators.py:428

    Port of AnnotationQueryMixin.resolve_authority_source_providers
    """
    raise NotImplementedError("_resolve_Query_authority_source_providers not yet ported — see manifest")


def q_authority_source_providers(info: strawberry.Info) -> list[Annotated["AuthoritySourceProviderType", strawberry.lazy("config.graphql.annotation_types")]]:
    kwargs = strip_unset({})
    return _resolve_Query_authority_source_providers(None, info, **kwargs)


def _resolve_Query_annotations(root, info, **kwargs):
    """PORT: config/ratelimit/decorators.py:459

    Port of AnnotationQueryMixin.resolve_annotations
    """
    raise NotImplementedError("_resolve_Query_annotations not yet ported — see manifest")


def q_annotations(info: strawberry.Info, raw_text_contains: Annotated[Optional[str], strawberry.argument(name="rawTextContains")] = strawberry.UNSET, annotation_label_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="annotationLabelId")] = strawberry.UNSET, annotation_label__text: Annotated[Optional[str], strawberry.argument(name="annotationLabel_Text")] = strawberry.UNSET, annotation_label__text_contains: Annotated[Optional[str], strawberry.argument(name="annotationLabel_TextContains")] = strawberry.UNSET, annotation_label__description_contains: Annotated[Optional[str], strawberry.argument(name="annotationLabel_DescriptionContains")] = strawberry.UNSET, annotation_label__label_type: Annotated[Optional[str], strawberry.argument(name="annotationLabel_LabelType")] = strawberry.UNSET, analysis_isnull: Annotated[Optional[bool], strawberry.argument(name="analysisIsnull")] = strawberry.UNSET, corpus_action_isnull: Annotated[Optional[bool], strawberry.argument(name="corpusActionIsnull")] = strawberry.UNSET, agent_created: Annotated[Optional[bool], strawberry.argument(name="agentCreated")] = strawberry.UNSET, document_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="documentId")] = strawberry.UNSET, corpus_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="corpusId")] = strawberry.UNSET, structural: Annotated[Optional[bool], strawberry.argument(name="structural")] = strawberry.UNSET, uses_label_from_labelset_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="usesLabelFromLabelsetId")] = strawberry.UNSET, created_by_analysis_ids: Annotated[Optional[str], strawberry.argument(name="createdByAnalysisIds")] = strawberry.UNSET, created_with_analyzer_id: Annotated[Optional[str], strawberry.argument(name="createdWithAnalyzerId")] = strawberry.UNSET, order_by: Annotated[Optional[str], strawberry.argument(name="orderBy")] = strawberry.UNSET, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Optional[Annotated["AnnotationTypeConnection", strawberry.lazy("config.graphql.annotation_types")]]:
    kwargs = strip_unset({"raw_text_contains": raw_text_contains, "annotation_label_id": annotation_label_id, "annotation_label__text": annotation_label__text, "annotation_label__text_contains": annotation_label__text_contains, "annotation_label__description_contains": annotation_label__description_contains, "annotation_label__label_type": annotation_label__label_type, "analysis_isnull": analysis_isnull, "corpus_action_isnull": corpus_action_isnull, "agent_created": agent_created, "document_id": document_id, "corpus_id": corpus_id, "structural": structural, "uses_label_from_labelset_id": uses_label_from_labelset_id, "created_by_analysis_ids": created_by_analysis_ids, "created_with_analyzer_id": created_with_analyzer_id, "order_by": order_by, "offset": offset, "before": before, "after": after, "first": first, "last": last})
    resolved = _resolve_Query_annotations(None, info, **kwargs)
    return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="AnnotationType", default_manager=Annotation._default_manager, )


def _resolve_Query_bulk_doc_relationships_in_corpus(root, info, **kwargs):
    """PORT: config/graphql/annotation_queries.py:682

    Port of AnnotationQueryMixin.resolve_bulk_doc_relationships_in_corpus
    """
    raise NotImplementedError("_resolve_Query_bulk_doc_relationships_in_corpus not yet ported — see manifest")


def q_bulk_doc_relationships_in_corpus(info: strawberry.Info, corpus_id: Annotated[strawberry.ID, strawberry.argument(name="corpusId")] = strawberry.UNSET, document_id: Annotated[strawberry.ID, strawberry.argument(name="documentId")] = strawberry.UNSET) -> Optional[list[Optional[Annotated["RelationshipType", strawberry.lazy("config.graphql.annotation_types")]]]]:
    kwargs = strip_unset({"corpus_id": corpus_id, "document_id": document_id})
    return _resolve_Query_bulk_doc_relationships_in_corpus(None, info, **kwargs)


def _resolve_Query_bulk_doc_annotations_in_corpus(root, info, **kwargs):
    """PORT: config/graphql/annotation_queries.py:717

    Port of AnnotationQueryMixin.resolve_bulk_doc_annotations_in_corpus
    """
    raise NotImplementedError("_resolve_Query_bulk_doc_annotations_in_corpus not yet ported — see manifest")


def q_bulk_doc_annotations_in_corpus(info: strawberry.Info, corpus_id: Annotated[strawberry.ID, strawberry.argument(name="corpusId")] = strawberry.UNSET, document_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="documentId")] = strawberry.UNSET, for_analysis_ids: Annotated[Optional[str], strawberry.argument(name="forAnalysisIds")] = strawberry.UNSET, label_type: Annotated[Optional[enums.LabelType], strawberry.argument(name="labelType")] = strawberry.UNSET) -> Optional[list[Optional[Annotated["AnnotationType", strawberry.lazy("config.graphql.annotation_types")]]]]:
    kwargs = strip_unset({"corpus_id": corpus_id, "document_id": document_id, "for_analysis_ids": for_analysis_ids, "label_type": label_type})
    return _resolve_Query_bulk_doc_annotations_in_corpus(None, info, **kwargs)


def _resolve_Query_page_annotations(root, info, **kwargs):
    """PORT: config/ratelimit/decorators.py:784

    Port of AnnotationQueryMixin.resolve_page_annotations
    """
    raise NotImplementedError("_resolve_Query_page_annotations not yet ported — see manifest")


def q_page_annotations(info: strawberry.Info, current_page: Annotated[Optional[int], strawberry.argument(name="currentPage")] = strawberry.UNSET, page_number_list: Annotated[Optional[str], strawberry.argument(name="pageNumberList")] = strawberry.UNSET, page_containing_annotation_with_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="pageContainingAnnotationWithId")] = strawberry.UNSET, corpus_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="corpusId")] = strawberry.UNSET, document_id: Annotated[strawberry.ID, strawberry.argument(name="documentId")] = strawberry.UNSET, for_analysis_ids: Annotated[Optional[str], strawberry.argument(name="forAnalysisIds")] = strawberry.UNSET, label_type: Annotated[Optional[enums.LabelType], strawberry.argument(name="labelType")] = strawberry.UNSET) -> Optional[Annotated["PageAwareAnnotationType", strawberry.lazy("config.graphql.base_types")]]:
    kwargs = strip_unset({"current_page": current_page, "page_number_list": page_number_list, "page_containing_annotation_with_id": page_containing_annotation_with_id, "corpus_id": corpus_id, "document_id": document_id, "for_analysis_ids": for_analysis_ids, "label_type": label_type})
    return _resolve_Query_page_annotations(None, info, **kwargs)


def q_annotation(info: strawberry.Info, id: Annotated[strawberry.ID, strawberry.argument(name="id", description='The ID of the object')] = strawberry.UNSET) -> Optional[Annotated["AnnotationType", strawberry.lazy("config.graphql.annotation_types")]]:
    return get_node_from_global_id(info, id, only_type_name="AnnotationType")


def _resolve_Query_relationships(root, info, **kwargs):
    """PORT: config/graphql/annotation_queries.py:977

    Port of AnnotationQueryMixin.resolve_relationships
    """
    raise NotImplementedError("_resolve_Query_relationships not yet ported — see manifest")


def q_relationships(info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET, relationship_label: Annotated[Optional[strawberry.ID], strawberry.argument(name="relationshipLabel")] = strawberry.UNSET, corpus_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="corpusId")] = strawberry.UNSET, document_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="documentId")] = strawberry.UNSET) -> Optional[Annotated["RelationshipTypeConnection", strawberry.lazy("config.graphql.annotation_types")]]:
    kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last, "relationship_label": relationship_label, "corpus_id": corpus_id, "document_id": document_id})
    resolved = _resolve_Query_relationships(None, info, **kwargs)
    return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="RelationshipType", default_manager=Relationship._default_manager, filterset_class=setup_filterset(RelationshipFilter), filter_args={"relationship_label": "relationship_label", "corpus_id": "corpus_id", "document_id": "document_id"}, )


def q_relationship(info: strawberry.Info, id: Annotated[strawberry.ID, strawberry.argument(name="id", description='The ID of the object')] = strawberry.UNSET) -> Optional[Annotated["RelationshipType", strawberry.lazy("config.graphql.annotation_types")]]:
    return get_node_from_global_id(info, id, only_type_name="RelationshipType")


def _resolve_Query_annotation_labels(root, info, **kwargs):
    """PORT: config/graphql/annotation_queries.py:1016

    Port of AnnotationQueryMixin.resolve_annotation_labels
    """
    raise NotImplementedError("_resolve_Query_annotation_labels not yet ported — see manifest")


def q_annotation_labels(info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET, description__contains: Annotated[Optional[str], strawberry.argument(name="description_Contains")] = strawberry.UNSET, text: Annotated[Optional[str], strawberry.argument(name="text")] = strawberry.UNSET, text__contains: Annotated[Optional[str], strawberry.argument(name="text_Contains")] = strawberry.UNSET, label_type: Annotated[Optional[enums.AnnotationsAnnotationLabelLabelTypeChoices], strawberry.argument(name="labelType")] = strawberry.UNSET, used_in_labelset_id: Annotated[Optional[str], strawberry.argument(name="usedInLabelsetId")] = strawberry.UNSET, used_in_labelset_for_corpus_id: Annotated[Optional[str], strawberry.argument(name="usedInLabelsetForCorpusId")] = strawberry.UNSET, used_in_analysis_ids: Annotated[Optional[str], strawberry.argument(name="usedInAnalysisIds")] = strawberry.UNSET) -> Optional[Annotated["AnnotationLabelTypeConnection", strawberry.lazy("config.graphql.annotation_types")]]:
    kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last, "description__contains": description__contains, "text": text, "text__contains": text__contains, "label_type": label_type, "used_in_labelset_id": used_in_labelset_id, "used_in_labelset_for_corpus_id": used_in_labelset_for_corpus_id, "used_in_analysis_ids": used_in_analysis_ids})
    resolved = _resolve_Query_annotation_labels(None, info, **kwargs)
    return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="AnnotationLabelType", default_manager=AnnotationLabel._default_manager, filterset_class=setup_filterset(LabelFilter), filter_args={"description__contains": "description__contains", "text": "text", "text__contains": "text__contains", "label_type": "label_type", "used_in_labelset_id": "used_in_labelset_id", "used_in_labelset_for_corpus_id": "used_in_labelset_for_corpus_id", "used_in_analysis_ids": "used_in_analysis_ids"}, )


def q_annotation_label(info: strawberry.Info, id: Annotated[strawberry.ID, strawberry.argument(name="id", description='The ID of the object')] = strawberry.UNSET) -> Optional[Annotated["AnnotationLabelType", strawberry.lazy("config.graphql.annotation_types")]]:
    return get_node_from_global_id(info, id, only_type_name="AnnotationLabelType")


def _resolve_Query_labelsets(root, info, **kwargs):
    """PORT: config/ratelimit/decorators.py:1035

    Port of AnnotationQueryMixin.resolve_labelsets
    """
    raise NotImplementedError("_resolve_Query_labelsets not yet ported — see manifest")


def q_labelsets(info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET, id: Annotated[Optional[strawberry.ID], strawberry.argument(name="id")] = strawberry.UNSET, description__contains: Annotated[Optional[str], strawberry.argument(name="description_Contains")] = strawberry.UNSET, title: Annotated[Optional[str], strawberry.argument(name="title")] = strawberry.UNSET, text_search: Annotated[Optional[str], strawberry.argument(name="textSearch")] = strawberry.UNSET, title__contains: Annotated[Optional[str], strawberry.argument(name="title_Contains")] = strawberry.UNSET, labelset_id: Annotated[Optional[str], strawberry.argument(name="labelsetId")] = strawberry.UNSET) -> Optional[Annotated["LabelSetTypeConnection", strawberry.lazy("config.graphql.annotation_types")]]:
    kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last, "id": id, "description__contains": description__contains, "title": title, "text_search": text_search, "title__contains": title__contains, "labelset_id": labelset_id})
    resolved = _resolve_Query_labelsets(None, info, **kwargs)
    return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="LabelSetType", default_manager=LabelSet._default_manager, filterset_class=setup_filterset(LabelsetFilter), filter_args={"id": "id", "description__contains": "description__contains", "title": "title", "text_search": "text_search", "title__contains": "title__contains", "labelset_id": "labelset_id"}, )


def q_labelset(info: strawberry.Info, id: Annotated[strawberry.ID, strawberry.argument(name="id", description='The ID of the object')] = strawberry.UNSET) -> Optional[Annotated["LabelSetType", strawberry.lazy("config.graphql.annotation_types")]]:
    return get_node_from_global_id(info, id, only_type_name="LabelSetType")


def _resolve_Query_default_labelset(root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:1058

    Port of AnnotationQueryMixin.resolve_default_labelset
    """
    raise NotImplementedError("_resolve_Query_default_labelset not yet ported — see manifest")


def q_default_labelset(info: strawberry.Info) -> Optional[Annotated["LabelSetType", strawberry.lazy("config.graphql.annotation_types")]]:
    kwargs = strip_unset({})
    return _resolve_Query_default_labelset(None, info, **kwargs)


def _resolve_Query_notes(root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:1078

    Port of AnnotationQueryMixin.resolve_notes
    """
    raise NotImplementedError("_resolve_Query_notes not yet ported — see manifest")


def q_notes(info: strawberry.Info, title_contains: Annotated[Optional[str], strawberry.argument(name="titleContains")] = strawberry.UNSET, content_contains: Annotated[Optional[str], strawberry.argument(name="contentContains")] = strawberry.UNSET, document_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="documentId")] = strawberry.UNSET, annotation_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="annotationId")] = strawberry.UNSET, order_by: Annotated[Optional[str], strawberry.argument(name="orderBy")] = strawberry.UNSET, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Optional[Annotated["NoteTypeConnection", strawberry.lazy("config.graphql.annotation_types")]]:
    kwargs = strip_unset({"title_contains": title_contains, "content_contains": content_contains, "document_id": document_id, "annotation_id": annotation_id, "order_by": order_by, "offset": offset, "before": before, "after": after, "first": first, "last": last})
    resolved = _resolve_Query_notes(None, info, **kwargs)
    return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="NoteType", default_manager=Note._default_manager, )


def q_note(info: strawberry.Info, id: Annotated[strawberry.ID, strawberry.argument(name="id", description='The ID of the object')] = strawberry.UNSET) -> Optional[Annotated["NoteType", strawberry.lazy("config.graphql.annotation_types")]]:
    return get_node_from_global_id(info, id, only_type_name="NoteType")


def _resolve_Query_geographic_annotations_for_corpus(root, info, **kwargs):
    """PORT: config/ratelimit/decorators.py:1166

    Port of AnnotationQueryMixin.resolve_geographic_annotations_for_corpus
    """
    raise NotImplementedError("_resolve_Query_geographic_annotations_for_corpus not yet ported — see manifest")


def q_geographic_annotations_for_corpus(info: strawberry.Info, corpus_id: Annotated[strawberry.ID, strawberry.argument(name="corpusId")] = strawberry.UNSET, bbox: Annotated[Optional["BBoxInputType"], strawberry.argument(name="bbox")] = strawberry.UNSET, zoom: Annotated[Optional[float], strawberry.argument(name="zoom", description='Optional map zoom level used by the consumer to pick a label type. Not currently consumed server-side — the resolver returns every label type and lets the client decide which to render at the current zoom. ``Float`` accommodates the fractional zoom levels (e.g. 12.5) that Mapbox / MapLibre use natively.')] = strawberry.UNSET, label_types: Annotated[Optional[list[Optional[str]]], strawberry.argument(name="labelTypes", description="Optional subset of label types to include: 'country', 'state', 'city'. Defaults to all three.")] = strawberry.UNSET) -> Optional[list[Optional["GeographicAnnotationPinType"]]]:
    kwargs = strip_unset({"corpus_id": corpus_id, "bbox": bbox, "zoom": zoom, "label_types": label_types})
    return _resolve_Query_geographic_annotations_for_corpus(None, info, **kwargs)


def _resolve_Query_global_geographic_annotations(root, info, **kwargs):
    """PORT: config/ratelimit/decorators.py:1229

    Port of AnnotationQueryMixin.resolve_global_geographic_annotations
    """
    raise NotImplementedError("_resolve_Query_global_geographic_annotations not yet ported — see manifest")


def q_global_geographic_annotations(info: strawberry.Info, bbox: Annotated[Optional["BBoxInputType"], strawberry.argument(name="bbox")] = strawberry.UNSET, zoom: Annotated[Optional[float], strawberry.argument(name="zoom")] = strawberry.UNSET, label_types: Annotated[Optional[list[Optional[str]]], strawberry.argument(name="labelTypes")] = strawberry.UNSET) -> Optional[list[Optional["GeographicAnnotationPinType"]]]:
    kwargs = strip_unset({"bbox": bbox, "zoom": zoom, "label_types": label_types})
    return _resolve_Query_global_geographic_annotations(None, info, **kwargs)



QUERY_FIELDS = {
    "corpus_references": strawberry.field(resolver=q_corpus_references, name="corpusReferences"),
    "governance_graph": strawberry.field(resolver=q_governance_graph, name="governanceGraph", description='The corpus-scoped reference web in node-link form: documents, statute sections, and external-citation ghost nodes, with mention-weighted LAW / LAW_EXTERNAL / DOCUMENT edges. Powers the Governance Graph panel on the Corpus Intelligence home.'),
    "wanted_authorities": strawberry.field(resolver=q_wanted_authorities, name="wantedAuthorities", description='The missing-authority backlog: EXTERNAL law citations visible to the user, aggregated by authority prefix and ranked by mention volume — what to bootstrap next to resolve the most references.'),
    "authority_frontier_stats": strawberry.field(resolver=q_authority_frontier_stats, name="authorityFrontierStats", description="Facet-aware per-discovery_state row counts for the authority-sources monitor's summary chips. Honours the non-state facets but not a state filter. SUPERUSER-ONLY (empty otherwise)."),
    "authority_mapping_stats": strawberry.field(resolver=q_authority_mapping_stats, name="authorityMappingStats", description="Facet-aware per-source row counts for the authority-mappings panel's summary chips. Honours the search facet but not a source filter. SUPERUSER-ONLY (empty otherwise)."),
    "authority_namespace_stats": strawberry.field(resolver=q_authority_namespace_stats, name="authorityNamespaceStats", description="Faceted per-jurisdiction / authority_type / scope row counts for the registry panel's summary chips. Honours the search facet but not the facet selects. SUPERUSER-ONLY (empty otherwise)."),
    "authority_namespace_detail": strawberry.field(resolver=q_authority_namespace_detail, name="authorityNamespaceDetail", description='Everything about one body of law, string-joined across the authority models: the namespace + its aliases, in/out key-equivalences, discovery-queue rows, and reference demand. SUPERUSER-ONLY (null otherwise or for an unknown prefix).'),
    "authority_source_providers": strawberry.field(resolver=q_authority_source_providers, name="authoritySourceProviders", description='The registered authority source providers (scrapers): US Code / eCFR / Federal Register / agentic web locator, with their supported prefixes, license, priority, enabled flag and whether the secrets vault holds credentials. SUPERUSER-ONLY (empty otherwise).'),
    "annotations": strawberry.field(resolver=q_annotations, name="annotations"),
    "bulk_doc_relationships_in_corpus": strawberry.field(resolver=q_bulk_doc_relationships_in_corpus, name="bulkDocRelationshipsInCorpus"),
    "bulk_doc_annotations_in_corpus": strawberry.field(resolver=q_bulk_doc_annotations_in_corpus, name="bulkDocAnnotationsInCorpus"),
    "page_annotations": strawberry.field(resolver=q_page_annotations, name="pageAnnotations"),
    "annotation": strawberry.field(resolver=q_annotation, name="annotation"),
    "relationships": strawberry.field(resolver=q_relationships, name="relationships"),
    "relationship": strawberry.field(resolver=q_relationship, name="relationship"),
    "annotation_labels": strawberry.field(resolver=q_annotation_labels, name="annotationLabels"),
    "annotation_label": strawberry.field(resolver=q_annotation_label, name="annotationLabel"),
    "labelsets": strawberry.field(resolver=q_labelsets, name="labelsets"),
    "labelset": strawberry.field(resolver=q_labelset, name="labelset"),
    "default_labelset": strawberry.field(resolver=q_default_labelset, name="defaultLabelset", description='The install-wide default LabelSet (is_default=True), or null if none has been seeded yet or the current user cannot see it. Used by the new-corpus modal to pre-fill the label set field.'),
    "notes": strawberry.field(resolver=q_notes, name="notes"),
    "note": strawberry.field(resolver=q_note, name="note"),
    "geographic_annotations_for_corpus": strawberry.field(resolver=q_geographic_annotations_for_corpus, name="geographicAnnotationsForCorpus", description='Aggregated geographic pins for a single corpus. Pins are deduplicated by ``(label_type, canonical_name, lat, lng)`` and ship a bounded ``sample_document_ids`` preview rather than the full annotation row set. Document visibility uses MIN(document, corpus) so private documents inside a public corpus stay hidden.'),
    "global_geographic_annotations": strawberry.field(resolver=q_global_geographic_annotations, name="globalGeographicAnnotations", description='Aggregated geographic pins across every annotation visible to the requesting user (the Discover map surface). Same shape as ``geographicAnnotationsForCorpus``.'),
}
