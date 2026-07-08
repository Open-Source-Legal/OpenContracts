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

from config.graphql.filters import AssignmentFilter
from config.graphql.filters import ExportFilter
from opencontractserver.users.models import Assignment
from opencontractserver.users.models import UserExport
from opencontractserver.users.models import UserImport


def _resolve_Query_me(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/user_queries.py:40

    Port of UserQueryMixin.resolve_me
    """
    raise NotImplementedError("_resolve_Query_me not yet ported — see manifest")


def q_me(info: strawberry.Info) -> Optional[Annotated["UserType", strawberry.lazy("config.graphql.user_types")]]:
    kwargs = strip_unset({})
    return _resolve_Query_me(None, info, **kwargs)


def _resolve_Query_user_by_slug(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/user_queries.py:46

    Port of UserQueryMixin.resolve_user_by_slug
    """
    raise NotImplementedError("_resolve_Query_user_by_slug not yet ported — see manifest")


def q_user_by_slug(info: strawberry.Info, slug: Annotated[str, strawberry.argument(name="slug")] = strawberry.UNSET) -> Optional[Annotated["UserType", strawberry.lazy("config.graphql.user_types")]]:
    kwargs = strip_unset({"slug": slug})
    return _resolve_Query_user_by_slug(None, info, **kwargs)


def _resolve_Query_userimports(root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:74

    Port of UserQueryMixin.resolve_userimports
    """
    raise NotImplementedError("_resolve_Query_userimports not yet ported — see manifest")


def q_userimports(info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Optional[Annotated["UserImportTypeConnection", strawberry.lazy("config.graphql.user_types")]]:
    kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
    resolved = _resolve_Query_userimports(None, info, **kwargs)
    return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="UserImportType", default_manager=UserImport._default_manager, )


def q_userimport(info: strawberry.Info, id: Annotated[strawberry.ID, strawberry.argument(name="id", description='The ID of the object')] = strawberry.UNSET) -> Optional[Annotated["UserImportType", strawberry.lazy("config.graphql.user_types")]]:
    return get_node_from_global_id(info, id, only_type_name="UserImportType")


def _resolve_Query_userexports(root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:105

    Port of UserQueryMixin.resolve_userexports
    """
    raise NotImplementedError("_resolve_Query_userexports not yet ported — see manifest")


def q_userexports(info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET, name__contains: Annotated[Optional[str], strawberry.argument(name="name_Contains")] = strawberry.UNSET, id: Annotated[Optional[strawberry.ID], strawberry.argument(name="id")] = strawberry.UNSET, created__lte: Annotated[Optional[datetime.datetime], strawberry.argument(name="created_Lte")] = strawberry.UNSET, started__lte: Annotated[Optional[datetime.datetime], strawberry.argument(name="started_Lte")] = strawberry.UNSET, finished__lte: Annotated[Optional[datetime.datetime], strawberry.argument(name="finished_Lte")] = strawberry.UNSET, order_by_created: Annotated[Optional[str], strawberry.argument(name="orderByCreated", description='Ordering')] = strawberry.UNSET, order_by_started: Annotated[Optional[str], strawberry.argument(name="orderByStarted", description='Ordering')] = strawberry.UNSET, order_by_finished: Annotated[Optional[str], strawberry.argument(name="orderByFinished", description='Ordering')] = strawberry.UNSET) -> Optional[Annotated["UserExportTypeConnection", strawberry.lazy("config.graphql.user_types")]]:
    kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last, "name__contains": name__contains, "id": id, "created__lte": created__lte, "started__lte": started__lte, "finished__lte": finished__lte, "order_by_created": order_by_created, "order_by_started": order_by_started, "order_by_finished": order_by_finished})
    resolved = _resolve_Query_userexports(None, info, **kwargs)
    return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="UserExportType", default_manager=UserExport._default_manager, filterset_class=setup_filterset(ExportFilter), filter_args={"name__contains": "name__contains", "id": "id", "created__lte": "created__lte", "started__lte": "started__lte", "finished__lte": "finished__lte", "order_by_created": "order_by_created", "order_by_started": "order_by_started", "order_by_finished": "order_by_finished"}, )


def q_userexport(info: strawberry.Info, id: Annotated[strawberry.ID, strawberry.argument(name="id", description='The ID of the object')] = strawberry.UNSET) -> Optional[Annotated["UserExportType", strawberry.lazy("config.graphql.user_types")]]:
    return get_node_from_global_id(info, id, only_type_name="UserExportType")


def _resolve_Query_assignments(root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:135

    Port of UserQueryMixin.resolve_assignments
    """
    raise NotImplementedError("_resolve_Query_assignments not yet ported — see manifest")


def q_assignments(info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET, assignor__email: Annotated[Optional[str], strawberry.argument(name="assignor_Email")] = strawberry.UNSET, assignee__email: Annotated[Optional[str], strawberry.argument(name="assignee_Email")] = strawberry.UNSET, document_id: Annotated[Optional[str], strawberry.argument(name="documentId")] = strawberry.UNSET) -> Optional[Annotated["AssignmentTypeConnection", strawberry.lazy("config.graphql.user_types")]]:
    kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last, "assignor__email": assignor__email, "assignee__email": assignee__email, "document_id": document_id})
    resolved = _resolve_Query_assignments(None, info, **kwargs)
    return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="AssignmentType", default_manager=Assignment._default_manager, filterset_class=setup_filterset(AssignmentFilter), filter_args={"assignor__email": "assignor__email", "assignee__email": "assignee__email", "document_id": "document_id"}, )


def q_assignment(info: strawberry.Info, id: Annotated[strawberry.ID, strawberry.argument(name="id", description='The ID of the object')] = strawberry.UNSET) -> Optional[Annotated["AssignmentType", strawberry.lazy("config.graphql.user_types")]]:
    return get_node_from_global_id(info, id, only_type_name="AssignmentType")



QUERY_FIELDS = {
    "me": strawberry.field(resolver=q_me, name="me"),
    "user_by_slug": strawberry.field(resolver=q_user_by_slug, name="userBySlug"),
    "userimports": strawberry.field(resolver=q_userimports, name="userimports"),
    "userimport": strawberry.field(resolver=q_userimport, name="userimport"),
    "userexports": strawberry.field(resolver=q_userexports, name="userexports"),
    "userexport": strawberry.field(resolver=q_userexport, name="userexport"),
    "assignments": strawberry.field(resolver=q_assignments, name="assignments"),
    "assignment": strawberry.field(resolver=q_assignment, name="assignment"),
}
