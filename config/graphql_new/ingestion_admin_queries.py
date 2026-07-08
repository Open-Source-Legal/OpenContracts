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




def _resolve_Query_admin_document_ingestion(root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:141

    Port of IngestionAdminQueryMixin.resolve_admin_document_ingestion
    """
    raise NotImplementedError("_resolve_Query_admin_document_ingestion not yet ported — see manifest")


def q_admin_document_ingestion(info: strawberry.Info, status: Annotated[Optional[str], strawberry.argument(name="status", description='Filter by processing status (pending/processing/completed/failed).')] = strawberry.UNSET, limit: Annotated[Optional[int], strawberry.argument(name="limit")] = strawberry.UNSET, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET) -> Optional[Annotated["AdminDocumentIngestionPageType", strawberry.lazy("config.graphql_new.ingestion_admin_types")]]:
    kwargs = strip_unset({"status": status, "limit": limit, "offset": offset})
    return _resolve_Query_admin_document_ingestion(None, info, **kwargs)


def _resolve_Query_admin_worker_uploads(root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:192

    Port of IngestionAdminQueryMixin.resolve_admin_worker_uploads
    """
    raise NotImplementedError("_resolve_Query_admin_worker_uploads not yet ported — see manifest")


def q_admin_worker_uploads(info: strawberry.Info, status: Annotated[Optional[str], strawberry.argument(name="status")] = strawberry.UNSET, limit: Annotated[Optional[int], strawberry.argument(name="limit")] = strawberry.UNSET, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET) -> Optional[Annotated["AdminWorkerUploadPageType", strawberry.lazy("config.graphql_new.ingestion_admin_types")]]:
    kwargs = strip_unset({"status": status, "limit": limit, "offset": offset})
    return _resolve_Query_admin_worker_uploads(None, info, **kwargs)


def _resolve_Query_admin_corpus_imports(root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:250

    Port of IngestionAdminQueryMixin.resolve_admin_corpus_imports
    """
    raise NotImplementedError("_resolve_Query_admin_corpus_imports not yet ported — see manifest")


def q_admin_corpus_imports(info: strawberry.Info, status: Annotated[Optional[str], strawberry.argument(name="status")] = strawberry.UNSET, limit: Annotated[Optional[int], strawberry.argument(name="limit")] = strawberry.UNSET, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET) -> Optional[Annotated["AdminCorpusImportPageType", strawberry.lazy("config.graphql_new.ingestion_admin_types")]]:
    kwargs = strip_unset({"status": status, "limit": limit, "offset": offset})
    return _resolve_Query_admin_corpus_imports(None, info, **kwargs)


def _resolve_Query_admin_bulk_import_sessions(root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:305

    Port of IngestionAdminQueryMixin.resolve_admin_bulk_import_sessions
    """
    raise NotImplementedError("_resolve_Query_admin_bulk_import_sessions not yet ported — see manifest")


def q_admin_bulk_import_sessions(info: strawberry.Info, status: Annotated[Optional[str], strawberry.argument(name="status")] = strawberry.UNSET, limit: Annotated[Optional[int], strawberry.argument(name="limit")] = strawberry.UNSET, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET) -> Optional[Annotated["AdminBulkImportSessionPageType", strawberry.lazy("config.graphql_new.ingestion_admin_types")]]:
    kwargs = strip_unset({"status": status, "limit": limit, "offset": offset})
    return _resolve_Query_admin_bulk_import_sessions(None, info, **kwargs)



QUERY_FIELDS = {
    "admin_document_ingestion": strawberry.field(resolver=q_admin_document_ingestion, name="adminDocumentIngestion", description='Per-document parsing-pipeline status across all users. Superuser only.'),
    "admin_worker_uploads": strawberry.field(resolver=q_admin_worker_uploads, name="adminWorkerUploads", description='Worker/pipeline upload queue across all corpuses. Superuser only.'),
    "admin_corpus_imports": strawberry.field(resolver=q_admin_corpus_imports, name="adminCorpusImports", description='Corpus-export ZIP re-import runs with per-document failure counts. Superuser only.'),
    "admin_bulk_import_sessions": strawberry.field(resolver=q_admin_bulk_import_sessions, name="adminBulkImportSessions", description='Bulk document-zip import sessions across all users. Superuser only.'),
}
