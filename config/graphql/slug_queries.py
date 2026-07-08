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




def _resolve_Query_corpus_by_slugs(root, info, **kwargs):
    """PORT: config/graphql/slug_queries.py:47

    Port of SlugQueryMixin.resolve_corpus_by_slugs
    """
    raise NotImplementedError("_resolve_Query_corpus_by_slugs not yet ported — see manifest")


def q_corpus_by_slugs(info: strawberry.Info, user_slug: Annotated[str, strawberry.argument(name="userSlug")] = strawberry.UNSET, corpus_slug: Annotated[str, strawberry.argument(name="corpusSlug")] = strawberry.UNSET) -> Optional[Annotated["CorpusType", strawberry.lazy("config.graphql.corpus_types")]]:
    kwargs = strip_unset({"user_slug": user_slug, "corpus_slug": corpus_slug})
    return _resolve_Query_corpus_by_slugs(None, info, **kwargs)


def _resolve_Query_document_by_slugs(root, info, **kwargs):
    """PORT: config/graphql/slug_queries.py:72

    Port of SlugQueryMixin.resolve_document_by_slugs
    """
    raise NotImplementedError("_resolve_Query_document_by_slugs not yet ported — see manifest")


def q_document_by_slugs(info: strawberry.Info, user_slug: Annotated[str, strawberry.argument(name="userSlug")] = strawberry.UNSET, document_slug: Annotated[str, strawberry.argument(name="documentSlug")] = strawberry.UNSET) -> Optional[Annotated["DocumentType", strawberry.lazy("config.graphql.document_types")]]:
    kwargs = strip_unset({"user_slug": user_slug, "document_slug": document_slug})
    return _resolve_Query_document_by_slugs(None, info, **kwargs)


def _resolve_Query_document_in_corpus_by_slugs(root, info, **kwargs):
    """PORT: config/graphql/slug_queries.py:90

    Port of SlugQueryMixin.resolve_document_in_corpus_by_slugs
    """
    raise NotImplementedError("_resolve_Query_document_in_corpus_by_slugs not yet ported — see manifest")


def q_document_in_corpus_by_slugs(info: strawberry.Info, user_slug: Annotated[str, strawberry.argument(name="userSlug")] = strawberry.UNSET, corpus_slug: Annotated[str, strawberry.argument(name="corpusSlug")] = strawberry.UNSET, document_slug: Annotated[str, strawberry.argument(name="documentSlug")] = strawberry.UNSET, version_number: Annotated[Optional[int], strawberry.argument(name="versionNumber", description='Optional version number to resolve a specific historical version. When omitted, returns the current (latest) version.')] = strawberry.UNSET) -> Optional[Annotated["DocumentType", strawberry.lazy("config.graphql.document_types")]]:
    kwargs = strip_unset({"user_slug": user_slug, "corpus_slug": corpus_slug, "document_slug": document_slug, "version_number": version_number})
    return _resolve_Query_document_in_corpus_by_slugs(None, info, **kwargs)



QUERY_FIELDS = {
    "corpus_by_slugs": strawberry.field(resolver=q_corpus_by_slugs, name="corpusBySlugs"),
    "document_by_slugs": strawberry.field(resolver=q_document_by_slugs, name="documentBySlugs"),
    "document_in_corpus_by_slugs": strawberry.field(resolver=q_document_in_corpus_by_slugs, name="documentInCorpusBySlugs"),
}
