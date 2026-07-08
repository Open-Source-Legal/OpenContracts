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




def _resolve_Query_discover_annotations(root, info, **kwargs):
    """PORT: config/ratelimit/decorators.py:303

    Port of DiscoverSearchQueryMixin.resolve_discover_annotations
    """
    raise NotImplementedError("_resolve_Query_discover_annotations not yet ported — see manifest")


def q_discover_annotations(info: strawberry.Info, text_search: Annotated[str, strawberry.argument(name="textSearch")] = strawberry.UNSET, limit: Annotated[Optional[int], strawberry.argument(name="limit")] = 25) -> Optional[list[Optional[Annotated["AnnotationType", strawberry.lazy("config.graphql.annotation_types")]]]]:
    kwargs = strip_unset({"text_search": text_search, "limit": limit})
    return _resolve_Query_discover_annotations(None, info, **kwargs)


def _resolve_Query_discover_documents(root, info, **kwargs):
    """PORT: config/ratelimit/decorators.py:339

    Port of DiscoverSearchQueryMixin.resolve_discover_documents
    """
    raise NotImplementedError("_resolve_Query_discover_documents not yet ported — see manifest")


def q_discover_documents(info: strawberry.Info, text_search: Annotated[str, strawberry.argument(name="textSearch")] = strawberry.UNSET, limit: Annotated[Optional[int], strawberry.argument(name="limit")] = 25) -> Optional[list[Optional[Annotated["DocumentType", strawberry.lazy("config.graphql.document_types")]]]]:
    kwargs = strip_unset({"text_search": text_search, "limit": limit})
    return _resolve_Query_discover_documents(None, info, **kwargs)


def _resolve_Query_discover_notes(root, info, **kwargs):
    """PORT: config/ratelimit/decorators.py:363

    Port of DiscoverSearchQueryMixin.resolve_discover_notes
    """
    raise NotImplementedError("_resolve_Query_discover_notes not yet ported — see manifest")


def q_discover_notes(info: strawberry.Info, text_search: Annotated[str, strawberry.argument(name="textSearch")] = strawberry.UNSET, limit: Annotated[Optional[int], strawberry.argument(name="limit")] = 25) -> Optional[list[Optional[Annotated["NoteType", strawberry.lazy("config.graphql.annotation_types")]]]]:
    kwargs = strip_unset({"text_search": text_search, "limit": limit})
    return _resolve_Query_discover_notes(None, info, **kwargs)


def _resolve_Query_discover_corpuses(root, info, **kwargs):
    """PORT: config/ratelimit/decorators.py:395

    Port of DiscoverSearchQueryMixin.resolve_discover_corpuses
    """
    raise NotImplementedError("_resolve_Query_discover_corpuses not yet ported — see manifest")


def q_discover_corpuses(info: strawberry.Info, text_search: Annotated[str, strawberry.argument(name="textSearch")] = strawberry.UNSET, limit: Annotated[Optional[int], strawberry.argument(name="limit")] = 25) -> Optional[list[Optional[Annotated["CorpusType", strawberry.lazy("config.graphql.corpus_types")]]]]:
    kwargs = strip_unset({"text_search": text_search, "limit": limit})
    return _resolve_Query_discover_corpuses(None, info, **kwargs)


def _resolve_Query_discover_discussions(root, info, **kwargs):
    """PORT: config/ratelimit/decorators.py:478

    Port of DiscoverSearchQueryMixin.resolve_discover_discussions
    """
    raise NotImplementedError("_resolve_Query_discover_discussions not yet ported — see manifest")


def q_discover_discussions(info: strawberry.Info, text_search: Annotated[str, strawberry.argument(name="textSearch")] = strawberry.UNSET, limit: Annotated[Optional[int], strawberry.argument(name="limit")] = 25) -> Optional[list[Optional[Annotated["ConversationType", strawberry.lazy("config.graphql.conversation_types")]]]]:
    kwargs = strip_unset({"text_search": text_search, "limit": limit})
    return _resolve_Query_discover_discussions(None, info, **kwargs)



QUERY_FIELDS = {
    "discover_annotations": strawberry.field(resolver=q_discover_annotations, name="discoverAnnotations", description='Hybrid (text + semantic) annotation search for Discover.'),
    "discover_documents": strawberry.field(resolver=q_discover_documents, name="discoverDocuments", description='Hybrid (text + semantic) document search for Discover.'),
    "discover_notes": strawberry.field(resolver=q_discover_notes, name="discoverNotes", description='Hybrid (text + semantic) note search for Discover.'),
    "discover_corpuses": strawberry.field(resolver=q_discover_corpuses, name="discoverCorpuses", description='Collection search for Discover: matches corpus title/description and collections whose documents or annotations match the query.'),
    "discover_discussions": strawberry.field(resolver=q_discover_discussions, name="discoverDiscussions", description='Hybrid (title + message body + semantic) discussion-thread search for Discover.'),
}
