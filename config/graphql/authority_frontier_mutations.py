"""GraphQL admin row-action mutations for the AuthorityFrontier discovery queue.

Superuser-only requeue / reset / reroute / approve / delete of frontier rows.
All transition + permission logic lives in ``AuthorityFrontierService`` (each
verb is a thin wrapper over the single ``mark()`` primitive); the mutations only
decode global IDs and forward, then translate the service's
``FrontierActionResult`` into the GraphQL payload. Mirrors
``authority_namespace_mutations`` (same superuser gate + opaque ``DENIED``).
"""

import logging

import graphene
from graphql_jwt.decorators import login_required
from graphql_relay import from_global_id

from config.graphql.graphene_types import AuthorityFrontierNode
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


class RequeueAuthorityFrontierMutation(graphene.Mutation):
    """Re-queue a row (clears document + error) — un-sticks deferred_cap/failed."""

    class Arguments:
        id = graphene.ID(required=True)

    ok = graphene.Boolean()
    message = graphene.String()
    obj = graphene.Field(AuthorityFrontierNode)

    @login_required
    def mutate(root, info, id):
        return _run_verb(RequeueAuthorityFrontierMutation, "requeue", info, id)


class ResetAuthorityFrontierMutation(graphene.Mutation):
    """Hard reset (clears document + provider + error) and re-queue."""

    class Arguments:
        id = graphene.ID(required=True)

    ok = graphene.Boolean()
    message = graphene.String()
    obj = graphene.Field(AuthorityFrontierNode)

    @login_required
    def mutate(root, info, id):
        return _run_verb(ResetAuthorityFrontierMutation, "reset", info, id)


class ApproveAuthorityFrontierMutation(graphene.Mutation):
    """Approve a pending_approval candidate so it re-enters the queue."""

    class Arguments:
        id = graphene.ID(required=True)

    ok = graphene.Boolean()
    message = graphene.String()
    obj = graphene.Field(AuthorityFrontierNode)

    @login_required
    def mutate(root, info, id):
        return _run_verb(ApproveAuthorityFrontierMutation, "approve", info, id)


class RerouteAuthorityFrontierMutation(graphene.Mutation):
    """Re-assign the provider (validated against the registry) and re-queue."""

    class Arguments:
        id = graphene.ID(required=True)
        provider = graphene.String(
            required=True, description="Registry provider class name to route to."
        )

    ok = graphene.Boolean()
    message = graphene.String()
    obj = graphene.Field(AuthorityFrontierNode)

    @login_required
    def mutate(root, info, id, provider):
        return _run_verb(
            RerouteAuthorityFrontierMutation, "reroute", info, id, provider=provider
        )


class DeleteAuthorityFrontierMutation(graphene.Mutation):
    """Delete one or more frontier rows (superuser-only bulk action)."""

    class Arguments:
        ids = graphene.List(
            graphene.NonNull(graphene.ID),
            required=True,
            description="Global IDs of the frontier rows to delete.",
        )

    ok = graphene.Boolean()
    message = graphene.String()
    count = graphene.Int()

    @login_required
    def mutate(root, info, ids):
        pks = [pk for pk in (_decode_pk(i) for i in ids) if pk is not None]
        result = AuthorityFrontierService.delete_rows(info.context.user, pks=pks)
        return DeleteAuthorityFrontierMutation(
            ok=result.ok,
            message=(result.error or "SUCCESS"),
            count=result.count,
        )
