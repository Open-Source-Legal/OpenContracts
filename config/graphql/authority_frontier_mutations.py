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

import logging
from typing import Annotated

import strawberry
from graphql_relay import from_global_id

from config.graphql._util import strip_unset
from config.graphql.core.auth import PermissionDenied
from config.graphql.core.relay import (
    register_type,
)
from opencontractserver.enrichment.services import AuthorityFrontierService
from opencontractserver.enrichment.services.authority_permissions import DENIED

logger = logging.getLogger(__name__)


def _decode_pk(global_id: str) -> int | None:
    try:
        return int(from_global_id(global_id)[1])
    except (ValueError, TypeError, IndexError):
        return None


def _run_verb(make_payload, verb: str, info, id, **extra):
    """Decode ``id``, call the named service verb, build the mutation payload."""
    pk = _decode_pk(id)
    if pk is None:
        return make_payload(ok=False, message=DENIED, obj=None)
    method = getattr(AuthorityFrontierService, verb)
    result = method(info.context.user, pk=pk, **extra)
    return make_payload(
        ok=result.ok, message=(result.error or "SUCCESS"), obj=result.obj
    )


@strawberry.type(
    name="RequeueAuthorityFrontierMutation",
    description="Re-queue a row (clears document + error) — un-sticks deferred_cap/failed.",
)
class RequeueAuthorityFrontierMutation:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    obj: None | (
        Annotated[
            AuthorityFrontierNode, strawberry.lazy("config.graphql.annotation_types")
        ]
    ) = strawberry.field(name="obj", default=None)


register_type(
    "RequeueAuthorityFrontierMutation", RequeueAuthorityFrontierMutation, model=None
)


@strawberry.type(
    name="ResetAuthorityFrontierMutation",
    description="Hard reset (clears document + provider + error) and re-queue.",
)
class ResetAuthorityFrontierMutation:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    obj: None | (
        Annotated[
            AuthorityFrontierNode, strawberry.lazy("config.graphql.annotation_types")
        ]
    ) = strawberry.field(name="obj", default=None)


register_type(
    "ResetAuthorityFrontierMutation", ResetAuthorityFrontierMutation, model=None
)


@strawberry.type(
    name="RerouteAuthorityFrontierMutation",
    description="Re-assign the provider (validated against the registry) and re-queue.",
)
class RerouteAuthorityFrontierMutation:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    obj: None | (
        Annotated[
            AuthorityFrontierNode, strawberry.lazy("config.graphql.annotation_types")
        ]
    ) = strawberry.field(name="obj", default=None)


register_type(
    "RerouteAuthorityFrontierMutation", RerouteAuthorityFrontierMutation, model=None
)


@strawberry.type(
    name="ApproveAuthorityFrontierMutation",
    description="Approve a pending_approval candidate so it re-enters the queue.",
)
class ApproveAuthorityFrontierMutation:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    obj: None | (
        Annotated[
            AuthorityFrontierNode, strawberry.lazy("config.graphql.annotation_types")
        ]
    ) = strawberry.field(name="obj", default=None)


register_type(
    "ApproveAuthorityFrontierMutation", ApproveAuthorityFrontierMutation, model=None
)


@strawberry.type(
    name="DeleteAuthorityFrontierMutation",
    description="Delete one or more frontier rows (superuser-only bulk action).",
)
class DeleteAuthorityFrontierMutation:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    count: int | None = strawberry.field(name="count", default=None)


register_type(
    "DeleteAuthorityFrontierMutation", DeleteAuthorityFrontierMutation, model=None
)


def _mutate_RequeueAuthorityFrontierMutation(payload_cls, root, info, id):
    """PORT: config/graphql/authority_frontier_mutations.py:54

    Port of RequeueAuthorityFrontierMutation.mutate
    """
    # @login_required (graphql_jwt) — inlined because mutate stubs take
    # ``payload_cls`` as their first positional argument, which does not
    # match core.auth's ``(root, info, ...)`` calling convention.
    if not info.context.user.is_authenticated:
        raise PermissionDenied()
    return _run_verb(payload_cls, "requeue", info, id)


def m_requeue_authority_frontier(
    info: strawberry.Info,
    id: Annotated[strawberry.ID, strawberry.argument(name="id")] = strawberry.UNSET,
) -> RequeueAuthorityFrontierMutation | None:
    kwargs = strip_unset({"id": id})
    return _mutate_RequeueAuthorityFrontierMutation(
        RequeueAuthorityFrontierMutation, None, info, **kwargs
    )


def _mutate_ResetAuthorityFrontierMutation(payload_cls, root, info, id):
    """PORT: config/graphql/authority_frontier_mutations.py:69

    Port of ResetAuthorityFrontierMutation.mutate
    """
    # @login_required (graphql_jwt) — inlined; see _mutate_RequeueAuthorityFrontierMutation.
    if not info.context.user.is_authenticated:
        raise PermissionDenied()
    return _run_verb(payload_cls, "reset", info, id)


def m_reset_authority_frontier(
    info: strawberry.Info,
    id: Annotated[strawberry.ID, strawberry.argument(name="id")] = strawberry.UNSET,
) -> ResetAuthorityFrontierMutation | None:
    kwargs = strip_unset({"id": id})
    return _mutate_ResetAuthorityFrontierMutation(
        ResetAuthorityFrontierMutation, None, info, **kwargs
    )


def _mutate_RerouteAuthorityFrontierMutation(payload_cls, root, info, id, provider):
    """PORT: config/graphql/authority_frontier_mutations.py:102

    Port of RerouteAuthorityFrontierMutation.mutate
    """
    # @login_required (graphql_jwt) — inlined; see _mutate_RequeueAuthorityFrontierMutation.
    if not info.context.user.is_authenticated:
        raise PermissionDenied()
    return _run_verb(payload_cls, "reroute", info, id, provider=provider)


def m_reroute_authority_frontier(
    info: strawberry.Info,
    id: Annotated[strawberry.ID, strawberry.argument(name="id")] = strawberry.UNSET,
    provider: Annotated[
        str,
        strawberry.argument(
            name="provider", description="Registry provider class name to route to."
        ),
    ] = strawberry.UNSET,
) -> RerouteAuthorityFrontierMutation | None:
    kwargs = strip_unset({"id": id, "provider": provider})
    return _mutate_RerouteAuthorityFrontierMutation(
        RerouteAuthorityFrontierMutation, None, info, **kwargs
    )


def _mutate_ApproveAuthorityFrontierMutation(payload_cls, root, info, id):
    """PORT: config/graphql/authority_frontier_mutations.py:84

    Port of ApproveAuthorityFrontierMutation.mutate
    """
    # @login_required (graphql_jwt) — inlined; see _mutate_RequeueAuthorityFrontierMutation.
    if not info.context.user.is_authenticated:
        raise PermissionDenied()
    return _run_verb(payload_cls, "approve", info, id)


def m_approve_authority_frontier(
    info: strawberry.Info,
    id: Annotated[strawberry.ID, strawberry.argument(name="id")] = strawberry.UNSET,
) -> ApproveAuthorityFrontierMutation | None:
    kwargs = strip_unset({"id": id})
    return _mutate_ApproveAuthorityFrontierMutation(
        ApproveAuthorityFrontierMutation, None, info, **kwargs
    )


def _mutate_DeleteAuthorityFrontierMutation(payload_cls, root, info, ids):
    """PORT: config/graphql/authority_frontier_mutations.py:123

    Port of DeleteAuthorityFrontierMutation.mutate
    """
    # @login_required (graphql_jwt) — inlined; see _mutate_RequeueAuthorityFrontierMutation.
    if not info.context.user.is_authenticated:
        raise PermissionDenied()
    pks = [pk for pk in (_decode_pk(i) for i in ids) if pk is not None]
    result = AuthorityFrontierService.delete_rows(info.context.user, pks=pks)
    return payload_cls(
        ok=result.ok,
        message=(result.error or "SUCCESS"),
        count=result.count,
    )


def m_delete_authority_frontier(
    info: strawberry.Info,
    ids: Annotated[
        list[strawberry.ID],
        strawberry.argument(
            name="ids", description="Global IDs of the frontier rows to delete."
        ),
    ] = strawberry.UNSET,
) -> DeleteAuthorityFrontierMutation | None:
    kwargs = strip_unset({"ids": ids})
    return _mutate_DeleteAuthorityFrontierMutation(
        DeleteAuthorityFrontierMutation, None, info, **kwargs
    )


MUTATION_FIELDS = {
    "requeue_authority_frontier": strawberry.field(
        resolver=m_requeue_authority_frontier,
        name="requeueAuthorityFrontier",
        description="Re-queue a row (clears document + error) — un-sticks deferred_cap/failed.",
    ),
    "reset_authority_frontier": strawberry.field(
        resolver=m_reset_authority_frontier,
        name="resetAuthorityFrontier",
        description="Hard reset (clears document + provider + error) and re-queue.",
    ),
    "reroute_authority_frontier": strawberry.field(
        resolver=m_reroute_authority_frontier,
        name="rerouteAuthorityFrontier",
        description="Re-assign the provider (validated against the registry) and re-queue.",
    ),
    "approve_authority_frontier": strawberry.field(
        resolver=m_approve_authority_frontier,
        name="approveAuthorityFrontier",
        description="Approve a pending_approval candidate so it re-enters the queue.",
    ),
    "delete_authority_frontier": strawberry.field(
        resolver=m_delete_authority_frontier,
        name="deleteAuthorityFrontier",
        description="Delete one or more frontier rows (superuser-only bulk action).",
    ),
}
