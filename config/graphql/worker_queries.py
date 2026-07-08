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




def _resolve_Query_worker_accounts(root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:64

    Port of WorkerQueryMixin.resolve_worker_accounts
    """
    raise NotImplementedError("_resolve_Query_worker_accounts not yet ported — see manifest")


def q_worker_accounts(info: strawberry.Info, name_contains: Annotated[Optional[str], strawberry.argument(name="nameContains")] = strawberry.UNSET, is_active: Annotated[Optional[bool], strawberry.argument(name="isActive")] = strawberry.UNSET) -> Optional[list[Optional[Annotated["WorkerAccountQueryType", strawberry.lazy("config.graphql.worker_types")]]]]:
    kwargs = strip_unset({"name_contains": name_contains, "is_active": is_active})
    return _resolve_Query_worker_accounts(None, info, **kwargs)


def _resolve_Query_corpus_access_tokens(root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:99

    Port of WorkerQueryMixin.resolve_corpus_access_tokens
    """
    raise NotImplementedError("_resolve_Query_corpus_access_tokens not yet ported — see manifest")


def q_corpus_access_tokens(info: strawberry.Info, corpus_id: Annotated[int, strawberry.argument(name="corpusId")] = strawberry.UNSET, is_active: Annotated[Optional[bool], strawberry.argument(name="isActive")] = strawberry.UNSET) -> Optional[list[Optional[Annotated["CorpusAccessTokenQueryType", strawberry.lazy("config.graphql.worker_types")]]]]:
    kwargs = strip_unset({"corpus_id": corpus_id, "is_active": is_active})
    return _resolve_Query_corpus_access_tokens(None, info, **kwargs)


def _resolve_Query_worker_document_uploads(root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:136

    Port of WorkerQueryMixin.resolve_worker_document_uploads
    """
    raise NotImplementedError("_resolve_Query_worker_document_uploads not yet ported — see manifest")


def q_worker_document_uploads(info: strawberry.Info, corpus_id: Annotated[int, strawberry.argument(name="corpusId")] = strawberry.UNSET, status: Annotated[Optional[str], strawberry.argument(name="status")] = strawberry.UNSET, limit: Annotated[Optional[int], strawberry.argument(name="limit", description='Max results (default/max 100)')] = strawberry.UNSET, offset: Annotated[Optional[int], strawberry.argument(name="offset", description='Pagination offset')] = strawberry.UNSET) -> Optional[Annotated["WorkerDocumentUploadPageType", strawberry.lazy("config.graphql.worker_types")]]:
    kwargs = strip_unset({"corpus_id": corpus_id, "status": status, "limit": limit, "offset": offset})
    return _resolve_Query_worker_document_uploads(None, info, **kwargs)



QUERY_FIELDS = {
    "worker_accounts": strawberry.field(resolver=q_worker_accounts, name="workerAccounts", description='List all worker accounts. Superuser only.'),
    "corpus_access_tokens": strawberry.field(resolver=q_corpus_access_tokens, name="corpusAccessTokens", description='List access tokens for a corpus. Superuser or corpus creator.'),
    "worker_document_uploads": strawberry.field(resolver=q_worker_document_uploads, name="workerDocumentUploads", description='List worker uploads for a corpus. Superuser or corpus creator.'),
}
