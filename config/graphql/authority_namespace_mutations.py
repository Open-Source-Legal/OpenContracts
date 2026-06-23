"""GraphQL CRUD mutations for the AuthorityNamespace registry.

Superuser-only create / update / delete / alias-edit of ``AuthorityNamespace``
rows (the registry of bodies of law whose aliases drive Tier-1 extraction).
Rows written here are stamped ``source="manual"`` so the loader never clobbers
them. All permission + validation logic lives in ``AuthorityNamespaceService``
— the mutations only decode global IDs and forward, then translate the service's
``NamespaceResult`` into the GraphQL payload. Mirrors
``authority_mapping_mutations`` (same superuser gate + opaque ``DENIED``).

Partial-update contract: an omitted optional arg (arriving as ``None``) means
"leave unchanged"; to CLEAR a nullable field send an empty string ``""`` (the
service's ``_clean`` collapses it to ``NULL``). ``aliases=[]`` clears all aliases
(``[]`` is distinct from an omitted ``None``).
"""

import logging

import graphene
from graphql_jwt.decorators import login_required
from graphql_relay import from_global_id

from config.graphql.graphene_types import AuthorityNamespaceNode
from opencontractserver.enrichment.services import AuthorityNamespaceService
from opencontractserver.enrichment.services.authority_permissions import DENIED

logger = logging.getLogger(__name__)


def _decode_pk(global_id: str) -> int | None:
    try:
        return int(from_global_id(global_id)[1])
    except (ValueError, TypeError, IndexError):
        return None


def _partial(**kwargs):
    """Drop ``None`` (omitted) args; keep ``""`` / ``[]`` (explicit clears)."""
    return {k: v for k, v in kwargs.items() if v is not None}


class CreateAuthorityNamespaceMutation(graphene.Mutation):
    """Create a manual AuthorityNamespace (superuser-only)."""

    class Arguments:
        prefix = graphene.String(
            required=True, description="Canonical-key prefix, e.g. 'usc-15' or 'dgcl'."
        )
        display_name = graphene.String(required=True)
        jurisdiction = graphene.String(required=False)
        authority_type = graphene.String(required=False)
        aliases = graphene.List(graphene.String, required=False)
        is_global = graphene.Boolean(required=False, default_value=True)
        authority_corpus_id = graphene.ID(required=False)
        provider = graphene.String(required=False)
        source_root_url = graphene.String(required=False)
        license = graphene.String(required=False)

    ok = graphene.Boolean()
    message = graphene.String()
    obj = graphene.Field(AuthorityNamespaceNode)

    @login_required
    def mutate(
        root,
        info,
        prefix,
        display_name,
        jurisdiction=None,
        authority_type=None,
        aliases=None,
        is_global=True,
        authority_corpus_id=None,
        provider=None,
        source_root_url=None,
        license=None,
    ):
        # A non-empty corpus id must decode; a truthy-but-undecodable value is a
        # caller error, not a silent fall-through to "global namespace".
        corpus_pk = None
        if authority_corpus_id:
            corpus_pk = _decode_pk(authority_corpus_id)
            if corpus_pk is None:
                return CreateAuthorityNamespaceMutation(
                    ok=False, message="Invalid authority_corpus_id.", obj=None
                )
        result = AuthorityNamespaceService.create(
            info.context.user,
            prefix=prefix,
            display_name=display_name,
            jurisdiction=jurisdiction,
            authority_type=authority_type,
            aliases=aliases,
            is_global=is_global,
            authority_corpus_id=corpus_pk,
            provider=provider,
            source_root_url=source_root_url,
            license=license,
        )
        return CreateAuthorityNamespaceMutation(
            ok=result.ok, message=(result.error or "SUCCESS"), obj=result.obj
        )


class UpdateAuthorityNamespaceMutation(graphene.Mutation):
    """Edit an AuthorityNamespace (superuser-only; stamps source='manual')."""

    class Arguments:
        id = graphene.ID(required=True)
        display_name = graphene.String(required=False)
        jurisdiction = graphene.String(required=False)
        authority_type = graphene.String(required=False)
        aliases = graphene.List(graphene.String, required=False)
        is_global = graphene.Boolean(required=False)
        authority_corpus_id = graphene.ID(required=False)
        provider = graphene.String(required=False)
        source_root_url = graphene.String(required=False)
        license = graphene.String(required=False)

    ok = graphene.Boolean()
    message = graphene.String()
    obj = graphene.Field(AuthorityNamespaceNode)

    @login_required
    def mutate(
        root,
        info,
        id,
        display_name=None,
        jurisdiction=None,
        authority_type=None,
        aliases=None,
        is_global=None,
        authority_corpus_id=None,
        provider=None,
        source_root_url=None,
        license=None,
    ):
        pk = _decode_pk(id)
        if pk is None:
            return UpdateAuthorityNamespaceMutation(ok=False, message=DENIED, obj=None)
        partial = _partial(
            display_name=display_name,
            jurisdiction=jurisdiction,
            authority_type=authority_type,
            aliases=aliases,
            is_global=is_global,
            provider=provider,
            source_root_url=source_root_url,
            license=license,
        )
        if authority_corpus_id is not None:
            if authority_corpus_id == "":
                # Explicit unlink (the partial-update "clear" sentinel for ids).
                partial["authority_corpus_id"] = None
            else:
                corpus_pk = _decode_pk(authority_corpus_id)
                if corpus_pk is None:
                    return UpdateAuthorityNamespaceMutation(
                        ok=False, message="Invalid authority_corpus_id.", obj=None
                    )
                partial["authority_corpus_id"] = corpus_pk
        result = AuthorityNamespaceService.update(info.context.user, pk=pk, **partial)
        return UpdateAuthorityNamespaceMutation(
            ok=result.ok, message=(result.error or "SUCCESS"), obj=result.obj
        )


class SetAuthorityNamespaceAliasesMutation(graphene.Mutation):
    """Replace a namespace's alias set (superuser-only)."""

    class Arguments:
        id = graphene.ID(required=True)
        aliases = graphene.List(
            graphene.String,
            required=True,
            description="Full replacement alias list (lowercased + de-duped).",
        )

    ok = graphene.Boolean()
    message = graphene.String()
    obj = graphene.Field(AuthorityNamespaceNode)

    @login_required
    def mutate(root, info, id, aliases):
        pk = _decode_pk(id)
        if pk is None:
            return SetAuthorityNamespaceAliasesMutation(
                ok=False, message=DENIED, obj=None
            )
        result = AuthorityNamespaceService.set_aliases(
            info.context.user, pk=pk, aliases=aliases
        )
        return SetAuthorityNamespaceAliasesMutation(
            ok=result.ok, message=(result.error or "SUCCESS"), obj=result.obj
        )


class DeleteAuthorityNamespaceMutation(graphene.Mutation):
    """Delete an AuthorityNamespace (superuser-only; guarded against orphaning)."""

    class Arguments:
        id = graphene.ID(required=True)

    ok = graphene.Boolean()
    message = graphene.String()

    @login_required
    def mutate(root, info, id):
        pk = _decode_pk(id)
        if pk is None:
            return DeleteAuthorityNamespaceMutation(ok=False, message=DENIED)
        result = AuthorityNamespaceService.delete(info.context.user, pk=pk)
        return DeleteAuthorityNamespaceMutation(
            ok=result.ok, message=(result.error or "SUCCESS")
        )
