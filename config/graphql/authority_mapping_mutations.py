"""GraphQL CRUD mutations for runtime authority key-equivalence overrides.

Superuser-only create / update / delete of ``AuthorityKeyEquivalence`` rows
(forced ``source="manual"``, capturing ``created_by`` + ``note``). All
permission + validation logic lives in ``AuthorityKeyEquivalenceService`` — the
mutations only decode the global ID and forward, then translate the service's
``MappingResult`` into the GraphQL payload. The superuser gate + opaque denial
mirror ``RunAuthorityDiscoveryMutation`` (the mappings are global system data
with no per-object permissions, so there is no existence oracle).
"""

import logging

import graphene
from graphql_jwt.decorators import login_required
from graphql_relay import from_global_id

from config.graphql.graphene_types import AuthorityKeyEquivalenceNode
from opencontractserver.enrichment.services import AuthorityKeyEquivalenceService
from opencontractserver.enrichment.services.authority_mapping_service import DENIED

logger = logging.getLogger(__name__)


def _decode_pk(global_id: str) -> int | None:
    try:
        return int(from_global_id(global_id)[1])
    except (ValueError, TypeError, IndexError):
        return None


class CreateAuthorityKeyEquivalenceMutation(graphene.Mutation):
    """Create a manual canonical-key equivalence (superuser-only)."""

    class Arguments:
        from_key = graphene.String(
            required=True, description="Source canonical key, e.g. 'irc:401'."
        )
        to_key = graphene.String(
            required=True, description="Equivalent canonical key, e.g. 'usc-26:401'."
        )
        note = graphene.String(required=False, description="Why this mapping exists.")

    ok = graphene.Boolean()
    message = graphene.String()
    obj = graphene.Field(AuthorityKeyEquivalenceNode)

    @login_required
    def mutate(root, info, from_key, to_key, note=None):
        result = AuthorityKeyEquivalenceService.create(
            info.context.user, from_key=from_key, to_key=to_key, note=note
        )
        return CreateAuthorityKeyEquivalenceMutation(
            ok=result.ok, message=(result.error or "SUCCESS"), obj=result.obj
        )


class UpdateAuthorityKeyEquivalenceMutation(graphene.Mutation):
    """Edit a manual equivalence (superuser-only; managed rows are read-only)."""

    class Arguments:
        id = graphene.ID(required=True, description="Global ID of the row to edit.")
        from_key = graphene.String(required=False)
        to_key = graphene.String(required=False)
        note = graphene.String(required=False)

    ok = graphene.Boolean()
    message = graphene.String()
    obj = graphene.Field(AuthorityKeyEquivalenceNode)

    @login_required
    def mutate(root, info, id, from_key=None, to_key=None, note=None):
        pk = _decode_pk(id)
        if pk is None:
            return UpdateAuthorityKeyEquivalenceMutation(
                ok=False, message=DENIED, obj=None
            )
        result = AuthorityKeyEquivalenceService.update(
            info.context.user,
            pk=pk,
            from_key=from_key,
            to_key=to_key,
            note=note,
        )
        return UpdateAuthorityKeyEquivalenceMutation(
            ok=result.ok, message=(result.error or "SUCCESS"), obj=result.obj
        )


class DeleteAuthorityKeyEquivalenceMutation(graphene.Mutation):
    """Delete a manual equivalence (superuser-only; managed rows are read-only)."""

    class Arguments:
        id = graphene.ID(required=True, description="Global ID of the row to delete.")

    ok = graphene.Boolean()
    message = graphene.String()

    @login_required
    def mutate(root, info, id):
        pk = _decode_pk(id)
        if pk is None:
            return DeleteAuthorityKeyEquivalenceMutation(ok=False, message=DENIED)
        result = AuthorityKeyEquivalenceService.delete(info.context.user, pk=pk)
        return DeleteAuthorityKeyEquivalenceMutation(
            ok=result.ok, message=(result.error or "SUCCESS")
        )
