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

from config.graphql.filters import CorpusCategoryFilter
from config.graphql.filters import CorpusFilter
from opencontractserver.corpuses.models import Corpus
from opencontractserver.corpuses.models import CorpusCategory


def _resolve_Query_corpuses(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/ratelimit/decorators.py:113

    Port of CorpusQueryMixin.resolve_corpuses
    """
    raise NotImplementedError("_resolve_Query_corpuses not yet ported — see manifest")


def q_corpuses(info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET, description: Annotated[Optional[str], strawberry.argument(name="description")] = strawberry.UNSET, description__contains: Annotated[Optional[str], strawberry.argument(name="description_Contains")] = strawberry.UNSET, id: Annotated[Optional[strawberry.ID], strawberry.argument(name="id")] = strawberry.UNSET, text_search: Annotated[Optional[str], strawberry.argument(name="textSearch")] = strawberry.UNSET, title__contains: Annotated[Optional[str], strawberry.argument(name="title_Contains")] = strawberry.UNSET, uses_labelset_id: Annotated[Optional[str], strawberry.argument(name="usesLabelsetId")] = strawberry.UNSET, categories: Annotated[Optional[list[Optional[strawberry.ID]]], strawberry.argument(name="categories")] = strawberry.UNSET, mine: Annotated[Optional[bool], strawberry.argument(name="mine")] = strawberry.UNSET, is_public: Annotated[Optional[bool], strawberry.argument(name="isPublic")] = strawberry.UNSET, shared_with_me: Annotated[Optional[bool], strawberry.argument(name="sharedWithMe")] = strawberry.UNSET, order_by: Annotated[Optional[str], strawberry.argument(name="orderBy", description='Ordering')] = strawberry.UNSET) -> Optional[Annotated["CorpusTypeConnection", strawberry.lazy("config.graphql.corpus_types")]]:
    kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last, "description": description, "description__contains": description__contains, "id": id, "text_search": text_search, "title__contains": title__contains, "uses_labelset_id": uses_labelset_id, "categories": categories, "mine": mine, "is_public": is_public, "shared_with_me": shared_with_me, "order_by": order_by})
    resolved = _resolve_Query_corpuses(None, info, **kwargs)
    return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="CorpusType", default_manager=Corpus._default_manager, filterset_class=setup_filterset(CorpusFilter), filter_args={"description": "description", "description__contains": "description__contains", "id": "id", "text_search": "text_search", "title__contains": "title__contains", "uses_labelset_id": "uses_labelset_id", "categories": "categories", "mine": "mine", "is_public": "is_public", "shared_with_me": "shared_with_me", "order_by": "order_by"}, )


def _resolve_Query_corpus_filter_counts(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/ratelimit/decorators.py:176

    Port of CorpusQueryMixin.resolve_corpus_filter_counts
    """
    raise NotImplementedError("_resolve_Query_corpus_filter_counts not yet ported — see manifest")


def q_corpus_filter_counts(info: strawberry.Info, text_search: Annotated[Optional[str], strawberry.argument(name="textSearch", description='Optional text search to apply alongside the tab counts so badges match the result set the user actually sees when searching.')] = strawberry.UNSET) -> Optional[Annotated["CorpusFilterCountsType", strawberry.lazy("config.graphql.corpus_types")]]:
    kwargs = strip_unset({"text_search": text_search})
    return _resolve_Query_corpus_filter_counts(None, info, **kwargs)


def _resolve_Query_corpus_categories(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/ratelimit/decorators.py:218

    Port of CorpusQueryMixin.resolve_corpus_categories
    """
    raise NotImplementedError("_resolve_Query_corpus_categories not yet ported — see manifest")


def q_corpus_categories(info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET, name: Annotated[Optional[str], strawberry.argument(name="name")] = strawberry.UNSET, name__contains: Annotated[Optional[str], strawberry.argument(name="name_Contains")] = strawberry.UNSET, description__contains: Annotated[Optional[str], strawberry.argument(name="description_Contains")] = strawberry.UNSET) -> Optional[Annotated["CorpusCategoryTypeConnection", strawberry.lazy("config.graphql.corpus_types")]]:
    kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last, "name": name, "name__contains": name__contains, "description__contains": description__contains})
    resolved = _resolve_Query_corpus_categories(None, info, **kwargs)
    return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="CorpusCategoryType", default_manager=CorpusCategory._default_manager, filterset_class=setup_filterset(CorpusCategoryFilter), filter_args={"name": "name", "name__contains": "name__contains", "description__contains": "description__contains"}, )


def _resolve_Query_corpus_folders(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/ratelimit/decorators.py:260

    Port of CorpusQueryMixin.resolve_corpus_folders
    """
    raise NotImplementedError("_resolve_Query_corpus_folders not yet ported — see manifest")


def q_corpus_folders(info: strawberry.Info, corpus_id: Annotated[strawberry.ID, strawberry.argument(name="corpusId")] = strawberry.UNSET) -> Optional[list[Optional[Annotated["CorpusFolderType", strawberry.lazy("config.graphql.corpus_types")]]]]:
    kwargs = strip_unset({"corpus_id": corpus_id})
    return _resolve_Query_corpus_folders(None, info, **kwargs)


def _resolve_Query_corpus_folder(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/ratelimit/decorators.py:289

    Port of CorpusQueryMixin.resolve_corpus_folder
    """
    raise NotImplementedError("_resolve_Query_corpus_folder not yet ported — see manifest")


def q_corpus_folder(info: strawberry.Info, id: Annotated[strawberry.ID, strawberry.argument(name="id")] = strawberry.UNSET) -> Optional[Annotated["CorpusFolderType", strawberry.lazy("config.graphql.corpus_types")]]:
    kwargs = strip_unset({"id": id})
    return _resolve_Query_corpus_folder(None, info, **kwargs)


def _resolve_Query_deleted_documents_in_corpus(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/ratelimit/decorators.py:312

    Port of CorpusQueryMixin.resolve_deleted_documents_in_corpus
    """
    raise NotImplementedError("_resolve_Query_deleted_documents_in_corpus not yet ported — see manifest")


def q_deleted_documents_in_corpus(info: strawberry.Info, corpus_id: Annotated[strawberry.ID, strawberry.argument(name="corpusId")] = strawberry.UNSET) -> Optional[list[Optional[Annotated["DocumentPathType", strawberry.lazy("config.graphql.document_types")]]]]:
    kwargs = strip_unset({"corpus_id": corpus_id})
    return _resolve_Query_deleted_documents_in_corpus(None, info, **kwargs)


def _resolve_Query_corpus_intelligence_setup_status(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/ratelimit/decorators.py:341

    Port of CorpusQueryMixin.resolve_corpus_intelligence_setup_status
    """
    raise NotImplementedError("_resolve_Query_corpus_intelligence_setup_status not yet ported — see manifest")


def q_corpus_intelligence_setup_status(info: strawberry.Info, corpus_id: Annotated[strawberry.ID, strawberry.argument(name="corpusId")] = strawberry.UNSET) -> Optional[Annotated["CorpusIntelligenceSetupStatusType", strawberry.lazy("config.graphql.corpus_types")]]:
    kwargs = strip_unset({"corpus_id": corpus_id})
    return _resolve_Query_corpus_intelligence_setup_status(None, info, **kwargs)


def _resolve_Query_corpus_stats(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/ratelimit/decorators.py:368

    Port of CorpusQueryMixin.resolve_corpus_stats
    """
    raise NotImplementedError("_resolve_Query_corpus_stats not yet ported — see manifest")


def q_corpus_stats(info: strawberry.Info, corpus_id: Annotated[strawberry.ID, strawberry.argument(name="corpusId")] = strawberry.UNSET) -> Optional[Annotated["CorpusStatsType", strawberry.lazy("config.graphql.corpus_types")]]:
    kwargs = strip_unset({"corpus_id": corpus_id})
    return _resolve_Query_corpus_stats(None, info, **kwargs)


def _resolve_Query_corpus_document_graph(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/ratelimit/decorators.py:508

    Port of CorpusQueryMixin.resolve_corpus_document_graph
    """
    raise NotImplementedError("_resolve_Query_corpus_document_graph not yet ported — see manifest")


def q_corpus_document_graph(info: strawberry.Info, corpus_id: Annotated[strawberry.ID, strawberry.argument(name="corpusId")] = strawberry.UNSET, limit: Annotated[Optional[int], strawberry.argument(name="limit")] = strawberry.UNSET) -> Optional[Annotated["CorpusDocumentGraphType", strawberry.lazy("config.graphql.corpus_types")]]:
    kwargs = strip_unset({"corpus_id": corpus_id, "limit": limit})
    return _resolve_Query_corpus_document_graph(None, info, **kwargs)


def _resolve_Query_corpus_intelligence_aggregates(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/ratelimit/decorators.py:654

    Port of CorpusQueryMixin.resolve_corpus_intelligence_aggregates
    """
    raise NotImplementedError("_resolve_Query_corpus_intelligence_aggregates not yet ported — see manifest")


def q_corpus_intelligence_aggregates(info: strawberry.Info, corpus_id: Annotated[strawberry.ID, strawberry.argument(name="corpusId")] = strawberry.UNSET) -> Optional[Annotated["CorpusIntelligenceAggregatesType", strawberry.lazy("config.graphql.corpus_types")]]:
    kwargs = strip_unset({"corpus_id": corpus_id})
    return _resolve_Query_corpus_intelligence_aggregates(None, info, **kwargs)


def _resolve_Query_corpus_data_story(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/ratelimit/decorators.py:745

    Port of CorpusQueryMixin.resolve_corpus_data_story
    """
    raise NotImplementedError("_resolve_Query_corpus_data_story not yet ported — see manifest")


def q_corpus_data_story(info: strawberry.Info, corpus_id: Annotated[strawberry.ID, strawberry.argument(name="corpusId")] = strawberry.UNSET) -> Optional[Annotated["CorpusDataStoryType", strawberry.lazy("config.graphql.corpus_types")]]:
    kwargs = strip_unset({"corpus_id": corpus_id})
    return _resolve_Query_corpus_data_story(None, info, **kwargs)


def _resolve_Query_artifact_by_slug(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/ratelimit/decorators.py:785

    Port of CorpusQueryMixin.resolve_artifact_by_slug
    """
    raise NotImplementedError("_resolve_Query_artifact_by_slug not yet ported — see manifest")


def q_artifact_by_slug(info: strawberry.Info, slug: Annotated[str, strawberry.argument(name="slug")] = strawberry.UNSET) -> Optional[Annotated["ArtifactType", strawberry.lazy("config.graphql.corpus_types")]]:
    kwargs = strip_unset({"slug": slug})
    return _resolve_Query_artifact_by_slug(None, info, **kwargs)


def _resolve_Query_corpus_artifacts(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/ratelimit/decorators.py:802

    Port of CorpusQueryMixin.resolve_corpus_artifacts
    """
    raise NotImplementedError("_resolve_Query_corpus_artifacts not yet ported — see manifest")


def q_corpus_artifacts(info: strawberry.Info, corpus_id: Annotated[strawberry.ID, strawberry.argument(name="corpusId")] = strawberry.UNSET) -> Optional[list[Annotated["ArtifactType", strawberry.lazy("config.graphql.corpus_types")]]]:
    kwargs = strip_unset({"corpus_id": corpus_id})
    return _resolve_Query_corpus_artifacts(None, info, **kwargs)


def _resolve_Query_corpus_artifact_templates(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/ratelimit/decorators.py:824

    Port of CorpusQueryMixin.resolve_corpus_artifact_templates
    """
    raise NotImplementedError("_resolve_Query_corpus_artifact_templates not yet ported — see manifest")


def q_corpus_artifact_templates(info: strawberry.Info, corpus_id: Annotated[strawberry.ID, strawberry.argument(name="corpusId")] = strawberry.UNSET) -> Optional[list[Annotated["ArtifactTemplateType", strawberry.lazy("config.graphql.corpus_types")]]]:
    kwargs = strip_unset({"corpus_id": corpus_id})
    return _resolve_Query_corpus_artifact_templates(None, info, **kwargs)


def _resolve_Query_corpus_metadata_columns(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/corpus_queries.py:853

    Port of CorpusQueryMixin.resolve_corpus_metadata_columns
    """
    raise NotImplementedError("_resolve_Query_corpus_metadata_columns not yet ported — see manifest")


def q_corpus_metadata_columns(info: strawberry.Info, corpus_id: Annotated[strawberry.ID, strawberry.argument(name="corpusId")] = strawberry.UNSET) -> Optional[list[Optional[Annotated["ColumnType", strawberry.lazy("config.graphql.extract_types")]]]]:
    kwargs = strip_unset({"corpus_id": corpus_id})
    return _resolve_Query_corpus_metadata_columns(None, info, **kwargs)



QUERY_FIELDS = {
    "corpuses": strawberry.field(resolver=q_corpuses, name="corpuses"),
    "corpus_filter_counts": strawberry.field(resolver=q_corpus_filter_counts, name="corpusFilterCounts", description='Tab-filter totals for the corpus list view (all/mine/shared/public). Each total respects the same service-layer permission filtering used by the corpuses connection, so badges stay accurate without paginating every page on the client.'),
    "corpus_categories": strawberry.field(resolver=q_corpus_categories, name="corpusCategories", description='List all corpus categories'),
    "corpus_folders": strawberry.field(resolver=q_corpus_folders, name="corpusFolders", description='Get all folders in a corpus (flat list for tree construction)'),
    "corpus_folder": strawberry.field(resolver=q_corpus_folder, name="corpusFolder", description='Get a single folder by ID'),
    "deleted_documents_in_corpus": strawberry.field(resolver=q_deleted_documents_in_corpus, name="deletedDocumentsInCorpus", description='Get all soft-deleted documents in a corpus (trash folder view)'),
    "corpus_intelligence_setup_status": strawberry.field(resolver=q_corpus_intelligence_setup_status, name="corpusIntelligenceSetupStatus", description='Which pieces of the default collection-intelligence bundle (reference-web action + description/summary templates) are already installed on the corpus. Null when the corpus is not visible to the requesting user.'),
    "corpus_stats": strawberry.field(resolver=q_corpus_stats, name="corpusStats"),
    "corpus_document_graph": strawberry.field(resolver=q_corpus_document_graph, name="corpusDocumentGraph", description='Document-relationship graph (nodes = documents, edges = DocumentRelationships) for a corpus, ranked by degree and capped for the landing-page glimpse.'),
    "corpus_intelligence_aggregates": strawberry.field(resolver=q_corpus_intelligence_aggregates, name="corpusIntelligenceAggregates", description='Insight-framed corpus aggregates (label distribution, summary coverage) for the Corpus Intelligence home.'),
    "corpus_data_story": strawberry.field(resolver=q_corpus_data_story, name="corpusDataStory", description='Per-document structured profiles (type / counterparty / effective date / value) for the corpus-home data story. Null until the default Collection Profile extract has run; corpus-as-gate (public corpus → anonymous-visible).'),
    "artifact_by_slug": strawberry.field(resolver=q_artifact_by_slug, name="artifactBySlug", description='A shareable corpus poster by its /a/<slug>. Corpus-as-gate: visible iff the source corpus is READ-visible (public corpus → anonymous).'),
    "corpus_artifacts": strawberry.field(resolver=q_corpus_artifacts, name="corpusArtifacts", description='All shareable artifacts of a corpus (corpus-as-gate).'),
    "corpus_artifact_templates": strawberry.field(resolver=q_corpus_artifact_templates, name="corpusArtifactTemplates", description="Templates this corpus's data can fill (data-gated picker)."),
    "corpus_metadata_columns": strawberry.field(resolver=q_corpus_metadata_columns, name="corpusMetadataColumns", description='Get metadata columns for a corpus'),
}
