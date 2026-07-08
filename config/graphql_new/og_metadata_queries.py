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
from config.graphql_new._util import coerce_enum, coerce_str, strip_unset
from config.graphql_new import enums




def _resolve_Query_og_corpus_metadata(root, info, **kwargs):
    """PORT: config/ratelimit/decorators.py:72

    Port of OGMetadataQueryMixin.resolve_og_corpus_metadata
    """
    raise NotImplementedError("_resolve_Query_og_corpus_metadata not yet ported — see manifest")


def q_og_corpus_metadata(info: strawberry.Info, user_slug: Annotated[str, strawberry.argument(name="userSlug")] = strawberry.UNSET, corpus_slug: Annotated[str, strawberry.argument(name="corpusSlug")] = strawberry.UNSET) -> Optional[Annotated["OGCorpusMetadataType", strawberry.lazy("config.graphql_new.og_metadata_types")]]:
    kwargs = strip_unset({"user_slug": user_slug, "corpus_slug": corpus_slug})
    return _resolve_Query_og_corpus_metadata(None, info, **kwargs)


def _resolve_Query_og_document_metadata(root, info, **kwargs):
    """PORT: config/ratelimit/decorators.py:112

    Port of OGMetadataQueryMixin.resolve_og_document_metadata
    """
    raise NotImplementedError("_resolve_Query_og_document_metadata not yet ported — see manifest")


def q_og_document_metadata(info: strawberry.Info, user_slug: Annotated[str, strawberry.argument(name="userSlug")] = strawberry.UNSET, document_slug: Annotated[str, strawberry.argument(name="documentSlug")] = strawberry.UNSET) -> Optional[Annotated["OGDocumentMetadataType", strawberry.lazy("config.graphql_new.og_metadata_types")]]:
    kwargs = strip_unset({"user_slug": user_slug, "document_slug": document_slug})
    return _resolve_Query_og_document_metadata(None, info, **kwargs)


def _resolve_Query_og_document_in_corpus_metadata(root, info, **kwargs):
    """PORT: config/ratelimit/decorators.py:147

    Port of OGMetadataQueryMixin.resolve_og_document_in_corpus_metadata
    """
    raise NotImplementedError("_resolve_Query_og_document_in_corpus_metadata not yet ported — see manifest")


def q_og_document_in_corpus_metadata(info: strawberry.Info, user_slug: Annotated[str, strawberry.argument(name="userSlug")] = strawberry.UNSET, corpus_slug: Annotated[str, strawberry.argument(name="corpusSlug")] = strawberry.UNSET, document_slug: Annotated[str, strawberry.argument(name="documentSlug")] = strawberry.UNSET) -> Optional[Annotated["OGDocumentMetadataType", strawberry.lazy("config.graphql_new.og_metadata_types")]]:
    kwargs = strip_unset({"user_slug": user_slug, "corpus_slug": corpus_slug, "document_slug": document_slug})
    return _resolve_Query_og_document_in_corpus_metadata(None, info, **kwargs)


def _resolve_Query_og_thread_metadata(root, info, **kwargs):
    """PORT: config/ratelimit/decorators.py:201

    Port of OGMetadataQueryMixin.resolve_og_thread_metadata
    """
    raise NotImplementedError("_resolve_Query_og_thread_metadata not yet ported — see manifest")


def q_og_thread_metadata(info: strawberry.Info, user_slug: Annotated[str, strawberry.argument(name="userSlug")] = strawberry.UNSET, corpus_slug: Annotated[str, strawberry.argument(name="corpusSlug")] = strawberry.UNSET, thread_id: Annotated[str, strawberry.argument(name="threadId")] = strawberry.UNSET) -> Optional[Annotated["OGThreadMetadataType", strawberry.lazy("config.graphql_new.og_metadata_types")]]:
    kwargs = strip_unset({"user_slug": user_slug, "corpus_slug": corpus_slug, "thread_id": thread_id})
    return _resolve_Query_og_thread_metadata(None, info, **kwargs)


def _resolve_Query_og_extract_metadata(root, info, **kwargs):
    """PORT: config/ratelimit/decorators.py:252

    Port of OGMetadataQueryMixin.resolve_og_extract_metadata
    """
    raise NotImplementedError("_resolve_Query_og_extract_metadata not yet ported — see manifest")


def q_og_extract_metadata(info: strawberry.Info, extract_id: Annotated[str, strawberry.argument(name="extractId")] = strawberry.UNSET) -> Optional[Annotated["OGExtractMetadataType", strawberry.lazy("config.graphql_new.og_metadata_types")]]:
    kwargs = strip_unset({"extract_id": extract_id})
    return _resolve_Query_og_extract_metadata(None, info, **kwargs)



QUERY_FIELDS = {
    "og_corpus_metadata": strawberry.field(resolver=q_og_corpus_metadata, name="ogCorpusMetadata", description='Public OG metadata for corpus - no auth required'),
    "og_document_metadata": strawberry.field(resolver=q_og_document_metadata, name="ogDocumentMetadata", description='Public OG metadata for standalone document - no auth required'),
    "og_document_in_corpus_metadata": strawberry.field(resolver=q_og_document_in_corpus_metadata, name="ogDocumentInCorpusMetadata", description='Public OG metadata for document in corpus - no auth required'),
    "og_thread_metadata": strawberry.field(resolver=q_og_thread_metadata, name="ogThreadMetadata", description='Public OG metadata for discussion thread - no auth required'),
    "og_extract_metadata": strawberry.field(resolver=q_og_extract_metadata, name="ogExtractMetadata", description='Public OG metadata for data extract - no auth required'),
}
