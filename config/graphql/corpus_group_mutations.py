"""GraphQL mutations for corpus groups (issue #2056).

Permission and CRUD logic lives in
:class:`opencontractserver.corpuses.services.CorpusGroupService`; the
mutations decode global IDs, fetch the target via the service's IDOR-safe
lookup, and forward the change to the service. All failure branches surface
the unified "Corpus group not found" message so callers cannot distinguish
"does not exist" from "exists but forbidden".
"""

from __future__ import annotations

import logging
from typing import Annotated

import strawberry
from graphql_relay import from_global_id

from config.graphql._util import strip_unset
from config.graphql.core.auth import PermissionDenied
from config.graphql.core.relay import register_type
from config.graphql.corpus_types import CorpusGroupType
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
    ``ValueError`` on garbage input or an empty decoded pk. Requires a
    non-empty ``global_id``; callers guard ``None``/absent arguments before
    calling (``... if default_agent_id else None``).
    """
    return _decode_pks([global_id])[0]  # type: ignore[index]  # non-None input


@strawberry.type(
    name="CreateCorpusGroupMutation",
    description="Create a corpus group bundling N corpora for multi-corpus retrieval.",
)
class CreateCorpusGroupMutation:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    corpus_group: None | (
        Annotated[CorpusGroupType, strawberry.lazy("config.graphql.corpus_types")]
    ) = strawberry.field(name="corpusGroup", default=None)


register_type("CreateCorpusGroupMutation", CreateCorpusGroupMutation, model=None)


@strawberry.type(
    name="UpdateCorpusGroupMutation",
    description="Update a corpus group (title, membership, default agent, visibility).",
)
class UpdateCorpusGroupMutation:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    corpus_group: None | (
        Annotated[CorpusGroupType, strawberry.lazy("config.graphql.corpus_types")]
    ) = strawberry.field(name="corpusGroup", default=None)


register_type("UpdateCorpusGroupMutation", UpdateCorpusGroupMutation, model=None)


@strawberry.type(
    name="DeleteCorpusGroupMutation",
    description="Delete a corpus group (member corpora are untouched).",
)
class DeleteCorpusGroupMutation:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)


register_type("DeleteCorpusGroupMutation", DeleteCorpusGroupMutation, model=None)


def _mutate_CreateCorpusGroupMutation(
    payload_cls,
    root,
    info,
    title,
    slug=None,
    description=None,
    corpus_ids=None,
    default_agent_id=None,
    is_public=False,
):
    """Port of CreateCorpusGroupMutation.mutate (issue #2056)."""
    if not info.context.user.is_authenticated:
        raise PermissionDenied()

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
    ):
        user = info.context.user
        try:
            try:
                corpus_pks = _decode_pks(corpus_ids)
                agent_pk = _decode_pk(default_agent_id) if default_agent_id else None
            except Exception:
                return payload_cls(
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
                return payload_cls(ok=False, message=result.error, corpus_group=None)
            return payload_cls(
                ok=True,
                message="Corpus group created successfully",
                corpus_group=result.value,
            )
        except Exception as e:
            logger.exception("Error creating corpus group")
            return payload_cls(
                ok=False,
                message=f"Failed to create corpus group: {str(e)}",
                corpus_group=None,
            )

    return mutate(
        root,
        info,
        title=title,
        slug=slug,
        description=description,
        corpus_ids=corpus_ids,
        default_agent_id=default_agent_id,
        is_public=is_public,
    )


def m_create_corpus_group(
    info: strawberry.Info,
    title: Annotated[
        str, strawberry.argument(name="title", description="Group title")
    ] = strawberry.UNSET,
    slug: Annotated[
        str | None,
        strawberry.argument(
            name="slug",
            description="URL-friendly identifier (auto-generated from title if not provided)",
        ),
    ] = strawberry.UNSET,
    description: Annotated[
        str | None, strawberry.argument(name="description")
    ] = strawberry.UNSET,
    corpus_ids: Annotated[
        list[strawberry.ID | None] | None,
        strawberry.argument(
            name="corpusIds",
            description="Corpora to bundle (each must be readable by you)",
        ),
    ] = strawberry.UNSET,
    default_agent_id: Annotated[
        strawberry.ID | None,
        strawberry.argument(
            name="defaultAgentId",
            description="Orchestrator AgentConfiguration to bind to this group",
        ),
    ] = strawberry.UNSET,
    is_public: Annotated[
        bool | None, strawberry.argument(name="isPublic")
    ] = False,
) -> CreateCorpusGroupMutation | None:
    kwargs = strip_unset(
        {
            "title": title,
            "slug": slug,
            "description": description,
            "corpus_ids": corpus_ids,
            "default_agent_id": default_agent_id,
            "is_public": is_public,
        }
    )
    return _mutate_CreateCorpusGroupMutation(
        CreateCorpusGroupMutation, None, info, **kwargs
    )


def _mutate_UpdateCorpusGroupMutation(
    payload_cls,
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
):
    """Port of UpdateCorpusGroupMutation.mutate (issue #2056)."""
    if not info.context.user.is_authenticated:
        raise PermissionDenied()

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
    ):
        user = info.context.user
        try:
            # A malformed TARGET id is indistinguishable from a missing
            # group (IDOR-uniform NOT_FOUND); malformed ARGUMENT ids get the
            # same "Malformed id argument" envelope as the create mutation.
            try:
                group_pk = from_global_id(corpus_group_id)[1]
            except Exception:
                return payload_cls(
                    ok=False, message=GROUP_NOT_FOUND_MESSAGE, corpus_group=None
                )
            try:
                corpus_pks = _decode_pks(corpus_ids)
                agent_pk = _decode_pk(default_agent_id) if default_agent_id else None
            except Exception:
                return payload_cls(
                    ok=False, message="Malformed id argument", corpus_group=None
                )

            group = CorpusGroupService.get_group_by_id(
                user, group_pk, request=info.context
            )
            if group is None:
                return payload_cls(
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
                return payload_cls(ok=False, message=result.error, corpus_group=None)
            return payload_cls(
                ok=True,
                message="Corpus group updated successfully",
                corpus_group=result.value,
            )
        except Exception as e:
            logger.exception("Error updating corpus group")
            return payload_cls(
                ok=False,
                message=f"Failed to update corpus group: {str(e)}",
                corpus_group=None,
            )

    return mutate(
        root,
        info,
        corpus_group_id=corpus_group_id,
        title=title,
        slug=slug,
        description=description,
        corpus_ids=corpus_ids,
        default_agent_id=default_agent_id,
        clear_default_agent=clear_default_agent,
        is_public=is_public,
    )


def m_update_corpus_group(
    info: strawberry.Info,
    corpus_group_id: Annotated[
        strawberry.ID, strawberry.argument(name="corpusGroupId")
    ] = strawberry.UNSET,
    title: Annotated[str | None, strawberry.argument(name="title")] = strawberry.UNSET,
    slug: Annotated[str | None, strawberry.argument(name="slug")] = strawberry.UNSET,
    description: Annotated[
        str | None, strawberry.argument(name="description")
    ] = strawberry.UNSET,
    corpus_ids: Annotated[
        list[strawberry.ID | None] | None,
        strawberry.argument(
            name="corpusIds",
            description="REPLACES the group's membership when provided",
        ),
    ] = strawberry.UNSET,
    default_agent_id: Annotated[
        strawberry.ID | None,
        strawberry.argument(
            name="defaultAgentId",
            description="Set/replace the bound orchestrator agent. Pass null "
            "to leave unchanged; pass clearDefaultAgent=true to unbind.",
        ),
    ] = strawberry.UNSET,
    clear_default_agent: Annotated[
        bool | None,
        strawberry.argument(
            name="clearDefaultAgent",
            description="When true, unbinds the default agent.",
        ),
    ] = False,
    is_public: Annotated[
        bool | None, strawberry.argument(name="isPublic")
    ] = strawberry.UNSET,
) -> UpdateCorpusGroupMutation | None:
    kwargs = strip_unset(
        {
            "corpus_group_id": corpus_group_id,
            "title": title,
            "slug": slug,
            "description": description,
            "corpus_ids": corpus_ids,
            "default_agent_id": default_agent_id,
            "clear_default_agent": clear_default_agent,
            "is_public": is_public,
        }
    )
    return _mutate_UpdateCorpusGroupMutation(
        UpdateCorpusGroupMutation, None, info, **kwargs
    )


def _mutate_DeleteCorpusGroupMutation(payload_cls, root, info, corpus_group_id):
    """Port of DeleteCorpusGroupMutation.mutate (issue #2056)."""
    if not info.context.user.is_authenticated:
        raise PermissionDenied()

    @graphql_ratelimit(rate=RateLimits.WRITE_LIGHT)
    def mutate(root, info, corpus_group_id):
        user = info.context.user
        try:
            try:
                group_pk = from_global_id(corpus_group_id)[1]
            except Exception:
                return payload_cls(ok=False, message=GROUP_NOT_FOUND_MESSAGE)

            group = CorpusGroupService.get_group_by_id(
                user, group_pk, request=info.context
            )
            if group is None:
                return payload_cls(ok=False, message=GROUP_NOT_FOUND_MESSAGE)

            result = CorpusGroupService.delete_group(user, group, request=info.context)
            if not result.ok:
                return payload_cls(ok=False, message=result.error)
            return payload_cls(ok=True, message="Corpus group deleted successfully")
        except Exception as e:
            logger.exception("Error deleting corpus group")
            return payload_cls(
                ok=False, message=f"Failed to delete corpus group: {str(e)}"
            )

    return mutate(root, info, corpus_group_id=corpus_group_id)


def m_delete_corpus_group(
    info: strawberry.Info,
    corpus_group_id: Annotated[
        strawberry.ID, strawberry.argument(name="corpusGroupId")
    ] = strawberry.UNSET,
) -> DeleteCorpusGroupMutation | None:
    kwargs = strip_unset({"corpus_group_id": corpus_group_id})
    return _mutate_DeleteCorpusGroupMutation(
        DeleteCorpusGroupMutation, None, info, **kwargs
    )


MUTATION_FIELDS = {
    "create_corpus_group": strawberry.field(
        resolver=m_create_corpus_group,
        name="createCorpusGroup",
        description="Create a corpus group bundling N corpora for multi-corpus retrieval.",
    ),
    "update_corpus_group": strawberry.field(
        resolver=m_update_corpus_group,
        name="updateCorpusGroup",
        description="Update a corpus group (title, membership, default agent, visibility).",
    ),
    "delete_corpus_group": strawberry.field(
        resolver=m_delete_corpus_group,
        name="deleteCorpusGroup",
        description="Delete a corpus group (member corpora are untouched).",
    ),
}
