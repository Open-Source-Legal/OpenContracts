"""Generated strawberry GraphQL module (graphene migration).

Shape-generated from the graphene schema; stub functions marked PORT(...)
carry the ported business logic. See config/graphql_new/manifest.json.
"""

# mypy: disable-error-code="name-defined, valid-type, arg-type"
#   Code-generation artifacts of the strawberry schema bindings that
#   mypy's static pass cannot resolve, NOT real typing defects:
#     name-defined / valid-type — ``Annotated["XType", strawberry.lazy(...)]``
#       forward-reference strings + the runtime-generated ``*Connection``
#       types (``make_connection_types``).
#     arg-type — resolvers construct result types with ``to_global_id()``
#       (``str``) for ``strawberry.ID`` fields and return Django MODEL
#       instances where the field annotation names the strawberry type
#       (the graphene-django resolver contract). Both are correct at
#       runtime. Hand-written config/graphql/core/* stays fully checked.
# flake8: noqa: E501, F821 — generated strawberry schema module.
# E501: long GraphQL field/argument ``description=`` strings and the
# single-line generated resolver signatures (black cannot split string
# literals). F821: ``Annotated["XType", strawberry.lazy(...)]`` /
# ``cast("QuerySet", ...)`` forward-reference STRINGS that pyflakes
# resolves as names — the whole point of strawberry.lazy is to avoid the
# import (which would then be F401). Both are code-generation artifacts,
# not defects; hand-written modules (config/graphql/core/*, security.py,
# testing.py, filters.py, …) stay fully linted.

from __future__ import annotations

import datetime
import warnings
from typing import Annotated

import strawberry
from django.db.models import Q

from config.graphql._util import strip_unset
from config.graphql.core.auth import login_required
from config.graphql.core.filtering import setup_filterset
from config.graphql.core.relay import (
    get_node_from_global_id,
    resolve_django_connection,
)
from config.graphql.filters import AssignmentFilter, ExportFilter
from opencontractserver.shared.services.base import BaseService
from opencontractserver.users.models import Assignment, UserExport, UserImport


def _resolve_Query_me(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/user_queries.py:40

    Port of UserQueryMixin.resolve_me
    """
    user = info.context.user
    if not user.is_authenticated:
        return None
    return user


def q_me(
    info: strawberry.Info,
) -> Annotated[UserType, strawberry.lazy("config.graphql.user_types")] | None:
    kwargs = strip_unset({})
    return _resolve_Query_me(None, info, **kwargs)


def _resolve_Query_user_by_slug(root, info, slug):
    """PORT: /home/user/oc-graphene-ref/config/graphql/user_queries.py:46

    Port of UserQueryMixin.resolve_user_by_slug

    Resolve a user by their slug with profile privacy filtering.

    SECURITY: Respects is_profile_public and corpus membership visibility rules.
    Users are visible if:
    - Profile is public (is_profile_public=True)
    - Requesting user shares corpus membership with > READ permission
    - It's the requesting user's own profile
    """
    from django.contrib.auth import get_user_model

    from opencontractserver.users.services import UserService

    User = get_user_model()
    try:
        # Use visibility filtering instead of direct query
        return UserService.get_visible_users(
            info.context.user, request=info.context
        ).get(slug=slug)
    except User.DoesNotExist:
        return None


def q_user_by_slug(
    info: strawberry.Info,
    slug: Annotated[str, strawberry.argument(name="slug")] = strawberry.UNSET,
) -> Annotated[UserType, strawberry.lazy("config.graphql.user_types")] | None:
    kwargs = strip_unset({"slug": slug})
    return _resolve_Query_user_by_slug(None, info, **kwargs)


@login_required
def _resolve_Query_userimports(root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:74

    Port of UserQueryMixin.resolve_userimports
    """
    return BaseService.filter_visible(
        UserImport, info.context.user, request=info.context
    )


def q_userimports(
    info: strawberry.Info,
    offset: Annotated[
        int | None, strawberry.argument(name="offset")
    ] = strawberry.UNSET,
    before: Annotated[
        str | None, strawberry.argument(name="before")
    ] = strawberry.UNSET,
    after: Annotated[str | None, strawberry.argument(name="after")] = strawberry.UNSET,
    first: Annotated[int | None, strawberry.argument(name="first")] = strawberry.UNSET,
    last: Annotated[int | None, strawberry.argument(name="last")] = strawberry.UNSET,
) -> None | (
    Annotated[UserImportTypeConnection, strawberry.lazy("config.graphql.user_types")]
):
    kwargs = strip_unset(
        {
            "offset": offset,
            "before": before,
            "after": after,
            "first": first,
            "last": last,
        }
    )
    resolved = _resolve_Query_userimports(None, info, **kwargs)
    return resolve_django_connection(
        resolved=resolved,
        info=info,
        args=kwargs,
        node_type_name="UserImportType",
        default_manager=UserImport._default_manager,
    )


def q_userimport(
    info: strawberry.Info,
    id: Annotated[
        strawberry.ID,
        strawberry.argument(name="id", description="The ID of the object"),
    ] = strawberry.UNSET,
) -> None | (Annotated[UserImportType, strawberry.lazy("config.graphql.user_types")]):
    return get_node_from_global_id(info, id, only_type_name="UserImportType")


@login_required
def _resolve_Query_userexports(root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:105

    Port of UserQueryMixin.resolve_userexports
    """
    return BaseService.filter_visible(
        UserExport, info.context.user, request=info.context
    )


def q_userexports(
    info: strawberry.Info,
    offset: Annotated[
        int | None, strawberry.argument(name="offset")
    ] = strawberry.UNSET,
    before: Annotated[
        str | None, strawberry.argument(name="before")
    ] = strawberry.UNSET,
    after: Annotated[str | None, strawberry.argument(name="after")] = strawberry.UNSET,
    first: Annotated[int | None, strawberry.argument(name="first")] = strawberry.UNSET,
    last: Annotated[int | None, strawberry.argument(name="last")] = strawberry.UNSET,
    name__contains: Annotated[
        str | None, strawberry.argument(name="name_Contains")
    ] = strawberry.UNSET,
    id: Annotated[
        strawberry.ID | None, strawberry.argument(name="id")
    ] = strawberry.UNSET,
    created__lte: Annotated[
        datetime.datetime | None, strawberry.argument(name="created_Lte")
    ] = strawberry.UNSET,
    started__lte: Annotated[
        datetime.datetime | None, strawberry.argument(name="started_Lte")
    ] = strawberry.UNSET,
    finished__lte: Annotated[
        datetime.datetime | None, strawberry.argument(name="finished_Lte")
    ] = strawberry.UNSET,
    order_by_created: Annotated[
        str | None,
        strawberry.argument(name="orderByCreated", description="Ordering"),
    ] = strawberry.UNSET,
    order_by_started: Annotated[
        str | None,
        strawberry.argument(name="orderByStarted", description="Ordering"),
    ] = strawberry.UNSET,
    order_by_finished: Annotated[
        str | None,
        strawberry.argument(name="orderByFinished", description="Ordering"),
    ] = strawberry.UNSET,
) -> None | (
    Annotated[UserExportTypeConnection, strawberry.lazy("config.graphql.user_types")]
):
    kwargs = strip_unset(
        {
            "offset": offset,
            "before": before,
            "after": after,
            "first": first,
            "last": last,
            "name__contains": name__contains,
            "id": id,
            "created__lte": created__lte,
            "started__lte": started__lte,
            "finished__lte": finished__lte,
            "order_by_created": order_by_created,
            "order_by_started": order_by_started,
            "order_by_finished": order_by_finished,
        }
    )
    resolved = _resolve_Query_userexports(None, info, **kwargs)
    return resolve_django_connection(
        resolved=resolved,
        info=info,
        args=kwargs,
        node_type_name="UserExportType",
        default_manager=UserExport._default_manager,
        filterset_class=setup_filterset(ExportFilter),
        filter_args={
            "name__contains": "name__contains",
            "id": "id",
            "created__lte": "created__lte",
            "started__lte": "started__lte",
            "finished__lte": "finished__lte",
            "order_by_created": "order_by_created",
            "order_by_started": "order_by_started",
            "order_by_finished": "order_by_finished",
        },
    )


def q_userexport(
    info: strawberry.Info,
    id: Annotated[
        strawberry.ID,
        strawberry.argument(name="id", description="The ID of the object"),
    ] = strawberry.UNSET,
) -> None | (Annotated[UserExportType, strawberry.lazy("config.graphql.user_types")]):
    return get_node_from_global_id(info, id, only_type_name="UserExportType")


@login_required
def _resolve_Query_assignments(root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:135

    Port of UserQueryMixin.resolve_assignments

    Resolve assignments.

    DEPRECATED: Assignment feature is not currently used.
    See opencontractserver/users/models.py:202-206

    SECURITY: Users can only see assignments where they are the assignor or assignee.
    Superusers can see all assignments.
    """
    warnings.warn("Assignment feature is deprecated and not in use", DeprecationWarning)

    user = info.context.user
    if user.is_superuser:
        return Assignment.objects.all()
    else:
        # User can see assignments they created or were assigned to
        return Assignment.objects.filter(Q(assignor=user) | Q(assignee=user))


def q_assignments(
    info: strawberry.Info,
    offset: Annotated[
        int | None, strawberry.argument(name="offset")
    ] = strawberry.UNSET,
    before: Annotated[
        str | None, strawberry.argument(name="before")
    ] = strawberry.UNSET,
    after: Annotated[str | None, strawberry.argument(name="after")] = strawberry.UNSET,
    first: Annotated[int | None, strawberry.argument(name="first")] = strawberry.UNSET,
    last: Annotated[int | None, strawberry.argument(name="last")] = strawberry.UNSET,
    assignor__email: Annotated[
        str | None, strawberry.argument(name="assignor_Email")
    ] = strawberry.UNSET,
    assignee__email: Annotated[
        str | None, strawberry.argument(name="assignee_Email")
    ] = strawberry.UNSET,
    document_id: Annotated[
        str | None, strawberry.argument(name="documentId")
    ] = strawberry.UNSET,
) -> None | (
    Annotated[AssignmentTypeConnection, strawberry.lazy("config.graphql.user_types")]
):
    kwargs = strip_unset(
        {
            "offset": offset,
            "before": before,
            "after": after,
            "first": first,
            "last": last,
            "assignor__email": assignor__email,
            "assignee__email": assignee__email,
            "document_id": document_id,
        }
    )
    resolved = _resolve_Query_assignments(None, info, **kwargs)
    return resolve_django_connection(
        resolved=resolved,
        info=info,
        args=kwargs,
        node_type_name="AssignmentType",
        default_manager=Assignment._default_manager,
        filterset_class=setup_filterset(AssignmentFilter),
        filter_args={
            "assignor__email": "assignor__email",
            "assignee__email": "assignee__email",
            "document_id": "document_id",
        },
    )


def q_assignment(
    info: strawberry.Info,
    id: Annotated[
        strawberry.ID,
        strawberry.argument(name="id", description="The ID of the object"),
    ] = strawberry.UNSET,
) -> None | (Annotated[AssignmentType, strawberry.lazy("config.graphql.user_types")]):
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
