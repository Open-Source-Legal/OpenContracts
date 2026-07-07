"""GraphQL mutations for corpus groups (issue #2056).

Permission and CRUD logic lives in
:class:`opencontractserver.corpuses.services.CorpusGroupService`; the
mutations decode global IDs, fetch the target via the service's IDOR-safe
lookup, and forward the change to the service. All failure branches surface
the unified "Corpus group not found" message so callers cannot distinguish
"does not exist" from "exists but forbidden".
"""

import logging

import graphene
from graphql_jwt.decorators import login_required
from graphql_relay import from_global_id

from config.graphql.graphene_types import CorpusGroupType
from config.graphql.ratelimits import RateLimits, graphql_ratelimit
from opencontractserver.corpuses.services import CorpusGroupService
from opencontractserver.corpuses.services.corpus_groups import GROUP_NOT_FOUND_MESSAGE

logger = logging.getLogger(__name__)


def _decode_pks(global_ids: list[str] | None) -> list[str] | None:
    """Decode a list of GraphQL global ids to raw pks (None passes through).

    A malformed id raises ``ValueError`` so the caller can surface the
    unified not-found envelope. ``from_global_id`` never raises on garbage
    input — it returns an empty pk (``graphql_relay`` decodes with
    ``partition``, swallowing base64 errors) — so an empty decode is
    treated as malformed too; otherwise the empty string would leak a raw
    Django ``Field 'id' expected a number`` error out of the service layer.
    """
    if global_ids is None:
        return None
    pks: list[str] = []
    for gid in global_ids:
        try:
            pk = from_global_id(gid)[1]
        except Exception as exc:
            raise ValueError(f"Malformed id: {gid}") from exc
        if not pk:
            raise ValueError(f"Malformed id: {gid}")
        pks.append(pk)
    return pks


def _decode_pk(global_id: str) -> str:
    """Decode a single GraphQL global id to a raw pk.

    Same malformed-input contract as :func:`_decode_pks` — raises
    ``ValueError`` on garbage input or an empty decoded pk.
    """
    return _decode_pks([global_id])[0]  # type: ignore[index]  # non-None input


class CreateCorpusGroupMutation(graphene.Mutation):
    """Create a corpus group bundling N corpora for multi-corpus retrieval."""

    class Arguments:
        title = graphene.String(required=True, description="Group title")
        slug = graphene.String(
            required=False,
            description="URL-friendly identifier (auto-generated from title "
            "if not provided)",
        )
        description = graphene.String(required=False)
        corpus_ids = graphene.List(
            graphene.ID,
            required=False,
            description="Corpora to bundle (each must be readable by you)",
        )
        default_agent_id = graphene.ID(
            required=False,
            description="Orchestrator AgentConfiguration to bind to this group",
        )
        is_public = graphene.Boolean(required=False, default_value=False)

    ok = graphene.Boolean()
    message = graphene.String()
    corpus_group = graphene.Field(CorpusGroupType)

    @login_required
    @graphql_ratelimit(rate=RateLimits.WRITE_MEDIUM)
    def mutate(
        root,
        info,
        title,
        slug=None,
        description=None,
        corpus_ids=None,
        default_agent_id=None,
        is_public=False,
    ) -> "CreateCorpusGroupMutation":
        user = info.context.user
        try:
            try:
                corpus_pks = _decode_pks(corpus_ids)
                agent_pk = _decode_pk(default_agent_id) if default_agent_id else None
            except Exception:
                return CreateCorpusGroupMutation(
                    ok=False, message="Malformed id argument", corpus_group=None
                )

            result = CorpusGroupService.create_group(
                user,
                title=title,
                slug=slug,
                description=description or "",
                corpus_pks=corpus_pks,
                default_agent_pk=agent_pk,
                is_public=is_public,
                request=info.context,
            )
            if not result.ok:
                return CreateCorpusGroupMutation(
                    ok=False, message=result.error, corpus_group=None
                )
            return CreateCorpusGroupMutation(
                ok=True,
                message="Corpus group created successfully",
                corpus_group=result.value,
            )
        except Exception as e:
            logger.exception("Error creating corpus group")
            return CreateCorpusGroupMutation(
                ok=False,
                message=f"Failed to create corpus group: {str(e)}",
                corpus_group=None,
            )


class UpdateCorpusGroupMutation(graphene.Mutation):
    """Update a corpus group (title, membership, default agent, visibility)."""

    class Arguments:
        corpus_group_id = graphene.ID(required=True)
        title = graphene.String(required=False)
        slug = graphene.String(required=False)
        description = graphene.String(required=False)
        corpus_ids = graphene.List(
            graphene.ID,
            required=False,
            description="REPLACES the group's membership when provided",
        )
        default_agent_id = graphene.ID(
            required=False,
            description="Set/replace the bound orchestrator agent. Pass null "
            "to leave unchanged; pass clearDefaultAgent=true to unbind.",
        )
        clear_default_agent = graphene.Boolean(
            required=False,
            default_value=False,
            description="When true, unbinds the default agent.",
        )
        is_public = graphene.Boolean(required=False)

    ok = graphene.Boolean()
    message = graphene.String()
    corpus_group = graphene.Field(CorpusGroupType)

    @login_required
    @graphql_ratelimit(rate=RateLimits.WRITE_LIGHT)
    def mutate(
        root,
        info,
        corpus_group_id,
        title=None,
        slug=None,
        description=None,
        corpus_ids=None,
        default_agent_id=None,
        clear_default_agent=False,
        is_public=None,
    ) -> "UpdateCorpusGroupMutation":
        user = info.context.user
        try:
            # A malformed TARGET id is indistinguishable from a missing
            # group (IDOR-uniform NOT_FOUND); malformed ARGUMENT ids get the
            # same "Malformed id argument" envelope as the create mutation.
            try:
                group_pk = from_global_id(corpus_group_id)[1]
            except Exception:
                return UpdateCorpusGroupMutation(
                    ok=False, message=GROUP_NOT_FOUND_MESSAGE, corpus_group=None
                )
            try:
                corpus_pks = _decode_pks(corpus_ids)
                agent_pk = _decode_pk(default_agent_id) if default_agent_id else None
            except Exception:
                return UpdateCorpusGroupMutation(
                    ok=False, message="Malformed id argument", corpus_group=None
                )

            group = CorpusGroupService.get_group_by_id(
                user, group_pk, request=info.context
            )
            if group is None:
                return UpdateCorpusGroupMutation(
                    ok=False, message=GROUP_NOT_FOUND_MESSAGE, corpus_group=None
                )

            result = CorpusGroupService.update_group(
                user,
                group,
                title=title,
                slug=slug,
                description=description,
                corpus_pks=corpus_pks,
                default_agent_pk=agent_pk,
                clear_default_agent=clear_default_agent,
                is_public=is_public,
                request=info.context,
            )
            if not result.ok:
                return UpdateCorpusGroupMutation(
                    ok=False, message=result.error, corpus_group=None
                )
            return UpdateCorpusGroupMutation(
                ok=True,
                message="Corpus group updated successfully",
                corpus_group=result.value,
            )
        except Exception as e:
            logger.exception("Error updating corpus group")
            return UpdateCorpusGroupMutation(
                ok=False,
                message=f"Failed to update corpus group: {str(e)}",
                corpus_group=None,
            )


class DeleteCorpusGroupMutation(graphene.Mutation):
    """Delete a corpus group (member corpora are untouched)."""

    class Arguments:
        corpus_group_id = graphene.ID(required=True)

    ok = graphene.Boolean()
    message = graphene.String()

    @login_required
    @graphql_ratelimit(rate=RateLimits.WRITE_LIGHT)
    def mutate(root, info, corpus_group_id) -> "DeleteCorpusGroupMutation":
        user = info.context.user
        try:
            try:
                group_pk = from_global_id(corpus_group_id)[1]
            except Exception:
                return DeleteCorpusGroupMutation(
                    ok=False, message=GROUP_NOT_FOUND_MESSAGE
                )

            group = CorpusGroupService.get_group_by_id(
                user, group_pk, request=info.context
            )
            if group is None:
                return DeleteCorpusGroupMutation(
                    ok=False, message=GROUP_NOT_FOUND_MESSAGE
                )

            result = CorpusGroupService.delete_group(user, group, request=info.context)
            if not result.ok:
                return DeleteCorpusGroupMutation(ok=False, message=result.error)
            return DeleteCorpusGroupMutation(
                ok=True, message="Corpus group deleted successfully"
            )
        except Exception as e:
            logger.exception("Error deleting corpus group")
            return DeleteCorpusGroupMutation(
                ok=False, message=f"Failed to delete corpus group: {str(e)}"
            )
