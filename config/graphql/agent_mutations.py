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
from config.graphql.core.scalars import GenericScalar
from config.graphql.ratelimits import RateLimits, graphql_ratelimit
from opencontractserver.agents.services import AgentConfigurationService
from opencontractserver.corpuses.models import Corpus
from opencontractserver.shared.services.base import BaseService
from opencontractserver.types.enums import PermissionTypes

logger = logging.getLogger(__name__)

# NOTE on decorators: the graphene mutations were decorated with
# ``@login_required`` + ``@graphql_ratelimit(...)`` on ``mutate(root, info, …)``.
# Mutate stubs here take ``payload_cls`` as their first positional argument,
# which does not match those decorators' ``(root, info, ...)`` calling
# convention — so ``login_required`` is inlined (see user_mutations.py) and
# ``graphql_ratelimit`` is applied to an inner function named ``mutate`` so
# the rate-limit cache group (defaults to the decorated function's
# ``__name__``) stays "mutate", exactly as in the graphene layer.


@strawberry.type(
    name="CreateAgentConfigurationMutation",
    description="Create a new agent configuration (admin/corpus owner only).",
)
class CreateAgentConfigurationMutation:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    agent: None | (
        Annotated[AgentConfigurationType, strawberry.lazy("config.graphql.agent_types")]
    ) = strawberry.field(name="agent", default=None)


register_type(
    "CreateAgentConfigurationMutation", CreateAgentConfigurationMutation, model=None
)


@strawberry.type(
    name="UpdateAgentConfigurationMutation",
    description="Update an existing agent configuration.",
)
class UpdateAgentConfigurationMutation:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    agent: None | (
        Annotated[AgentConfigurationType, strawberry.lazy("config.graphql.agent_types")]
    ) = strawberry.field(name="agent", default=None)


register_type(
    "UpdateAgentConfigurationMutation", UpdateAgentConfigurationMutation, model=None
)


@strawberry.type(
    name="DeleteAgentConfigurationMutation",
    description="Delete an agent configuration.",
)
class DeleteAgentConfigurationMutation:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)


register_type(
    "DeleteAgentConfigurationMutation", DeleteAgentConfigurationMutation, model=None
)


def _mutate_CreateAgentConfigurationMutation(
    payload_cls,
    root,
    info,
    name,
    description,
    system_instructions,
    scope,
    slug=None,
    available_tools=None,
    permission_required_tools=None,
    badge_config=None,
    avatar_url=None,
    corpus_id=None,
    is_public=True,
    preferred_llm=None,
):
    """PORT: /home/user/oc-graphene-ref/config/graphql/agent_mutations.py:77

    Port of CreateAgentConfigurationMutation.mutate
    """
    # @login_required — inlined (see module NOTE above).
    if not info.context.user.is_authenticated:
        raise PermissionDenied()

    @graphql_ratelimit(rate=RateLimits.WRITE_MEDIUM)
    def mutate(
        root,
        info,
        name,
        description,
        system_instructions,
        scope,
        slug=None,
        available_tools=None,
        permission_required_tools=None,
        badge_config=None,
        avatar_url=None,
        corpus_id=None,
        is_public=True,
        preferred_llm=None,
    ):
        user = info.context.user

        try:
            # Resolve and gate the parent corpus (if any). Unified message
            # blocks IDOR enumeration: bad id / missing / no-perm all surface
            # the same string.
            corpus = None
            if corpus_id:
                try:
                    corpus_pk = from_global_id(corpus_id)[1]
                except Exception:
                    return CreateAgentConfigurationMutation(
                        ok=False,
                        message="Corpus not found",
                        agent=None,
                    )
                corpus = BaseService.get_or_none(
                    Corpus, corpus_pk, user, request=info.context
                )
                if corpus is None or BaseService.require_permission(
                    corpus,
                    user,
                    PermissionTypes.CRUD,
                    request=info.context,
                ):
                    return CreateAgentConfigurationMutation(
                        ok=False,
                        message="Corpus not found",
                        agent=None,
                    )

            result = AgentConfigurationService.create_agent(
                user,
                name=name,
                slug=slug,
                description=description,
                system_instructions=system_instructions,
                available_tools=available_tools,
                permission_required_tools=permission_required_tools,
                badge_config=badge_config,
                avatar_url=avatar_url,
                scope=scope,
                corpus=corpus,
                is_public=is_public,
                preferred_llm=preferred_llm,
                request=info.context,
            )
            if not result.ok:
                return CreateAgentConfigurationMutation(
                    ok=False,
                    message=result.error,
                    agent=None,
                )

            return CreateAgentConfigurationMutation(
                ok=True,
                message="Agent configuration created successfully",
                agent=result.value,
            )

        except Exception as e:
            logger.exception("Error creating agent configuration")
            return CreateAgentConfigurationMutation(
                ok=False,
                message=f"Failed to create agent configuration: {str(e)}",
                agent=None,
            )

    return mutate(
        root,
        info,
        name,
        description,
        system_instructions,
        scope,
        slug=slug,
        available_tools=available_tools,
        permission_required_tools=permission_required_tools,
        badge_config=badge_config,
        avatar_url=avatar_url,
        corpus_id=corpus_id,
        is_public=is_public,
        preferred_llm=preferred_llm,
    )


def m_create_agent_configuration(
    info: strawberry.Info,
    available_tools: Annotated[
        list[str | None] | None,
        strawberry.argument(
            name="availableTools", description="List of tools available to the agent"
        ),
    ] = strawberry.UNSET,
    avatar_url: Annotated[
        str | None, strawberry.argument(name="avatarUrl", description="Avatar URL")
    ] = strawberry.UNSET,
    badge_config: Annotated[
        GenericScalar | None,
        strawberry.argument(
            name="badgeConfig", description="Badge display configuration"
        ),
    ] = strawberry.UNSET,
    corpus_id: Annotated[
        strawberry.ID | None,
        strawberry.argument(
            name="corpusId", description="Corpus ID for corpus-specific agents"
        ),
    ] = strawberry.UNSET,
    description: Annotated[
        str, strawberry.argument(name="description", description="Agent description")
    ] = strawberry.UNSET,
    is_public: Annotated[
        bool | None,
        strawberry.argument(
            name="isPublic", description="Whether agent is publicly visible"
        ),
    ] = True,
    name: Annotated[
        str, strawberry.argument(name="name", description="Agent name")
    ] = strawberry.UNSET,
    permission_required_tools: Annotated[
        list[str | None] | None,
        strawberry.argument(
            name="permissionRequiredTools",
            description="List of tools requiring explicit permission",
        ),
    ] = strawberry.UNSET,
    preferred_llm: Annotated[
        str | None,
        strawberry.argument(
            name="preferredLlm",
            description="Optional pydantic-ai model spec to use when this agent runs (e.g. 'anthropic:claude-haiku-4-5'). Overrides Corpus.preferred_llm. Empty falls back to the corpus default.",
        ),
    ] = strawberry.UNSET,
    scope: Annotated[
        str, strawberry.argument(name="scope", description="Scope: GLOBAL or CORPUS")
    ] = strawberry.UNSET,
    slug: Annotated[
        str | None,
        strawberry.argument(
            name="slug",
            description="URL-friendly slug for @mentions (auto-generated from name if not provided)",
        ),
    ] = strawberry.UNSET,
    system_instructions: Annotated[
        str,
        strawberry.argument(
            name="systemInstructions", description="System instructions for the agent"
        ),
    ] = strawberry.UNSET,
) -> CreateAgentConfigurationMutation | None:
    kwargs = strip_unset(
        {
            "available_tools": available_tools,
            "avatar_url": avatar_url,
            "badge_config": badge_config,
            "corpus_id": corpus_id,
            "description": description,
            "is_public": is_public,
            "name": name,
            "permission_required_tools": permission_required_tools,
            "preferred_llm": preferred_llm,
            "scope": scope,
            "slug": slug,
            "system_instructions": system_instructions,
        }
    )
    return _mutate_CreateAgentConfigurationMutation(
        CreateAgentConfigurationMutation, None, info, **kwargs
    )


def _mutate_UpdateAgentConfigurationMutation(
    payload_cls,
    root,
    info,
    agent_id,
    name=None,
    slug=None,
    description=None,
    system_instructions=None,
    available_tools=None,
    permission_required_tools=None,
    badge_config=None,
    avatar_url=None,
    is_active=None,
    is_public=None,
    preferred_llm=None,
    clear_preferred_llm=False,
):
    """PORT: /home/user/oc-graphene-ref/config/graphql/agent_mutations.py:200

    Port of UpdateAgentConfigurationMutation.mutate
    """
    # @login_required — inlined (see module NOTE above).
    if not info.context.user.is_authenticated:
        raise PermissionDenied()

    @graphql_ratelimit(rate=RateLimits.WRITE_LIGHT)
    def mutate(
        root,
        info,
        agent_id,
        name=None,
        slug=None,
        description=None,
        system_instructions=None,
        available_tools=None,
        permission_required_tools=None,
        badge_config=None,
        avatar_url=None,
        is_active=None,
        is_public=None,
        preferred_llm=None,
        clear_preferred_llm=False,
    ):
        user = info.context.user

        try:
            # ``from_global_id`` can raise a bare ``Exception`` (via
            # ``binascii.Error``) on malformed base64 — catch it so a bad
            # id surfaces through the unified IDOR-safe envelope rather
            # than the generic "Failed to update" outer-handler message.
            try:
                agent_pk = from_global_id(agent_id)[1]
            except Exception:
                return UpdateAgentConfigurationMutation(
                    ok=False,
                    message="Agent configuration not found",
                    agent=None,
                )
            agent = AgentConfigurationService.get_agent_by_id(
                user, agent_pk, request=info.context
            )
            if agent is None:
                return UpdateAgentConfigurationMutation(
                    ok=False,
                    message="Agent configuration not found",
                    agent=None,
                )

            result = AgentConfigurationService.update_agent(
                user,
                agent,
                name=name,
                slug=slug,
                description=description,
                system_instructions=system_instructions,
                available_tools=available_tools,
                permission_required_tools=permission_required_tools,
                badge_config=badge_config,
                avatar_url=avatar_url,
                is_active=is_active,
                is_public=is_public,
                preferred_llm=preferred_llm,
                clear_preferred_llm=clear_preferred_llm,
                request=info.context,
            )
            if not result.ok:
                return UpdateAgentConfigurationMutation(
                    ok=False,
                    message=result.error,
                    agent=None,
                )

            return UpdateAgentConfigurationMutation(
                ok=True,
                message="Agent configuration updated successfully",
                agent=result.value,
            )

        except Exception as e:
            logger.exception("Error updating agent configuration")
            return UpdateAgentConfigurationMutation(
                ok=False,
                message=f"Failed to update agent configuration: {str(e)}",
                agent=None,
            )

    return mutate(
        root,
        info,
        agent_id,
        name=name,
        slug=slug,
        description=description,
        system_instructions=system_instructions,
        available_tools=available_tools,
        permission_required_tools=permission_required_tools,
        badge_config=badge_config,
        avatar_url=avatar_url,
        is_active=is_active,
        is_public=is_public,
        preferred_llm=preferred_llm,
        clear_preferred_llm=clear_preferred_llm,
    )


def m_update_agent_configuration(
    info: strawberry.Info,
    agent_id: Annotated[
        strawberry.ID,
        strawberry.argument(name="agentId", description="Agent ID to update"),
    ] = strawberry.UNSET,
    available_tools: Annotated[
        list[str | None] | None, strawberry.argument(name="availableTools")
    ] = strawberry.UNSET,
    avatar_url: Annotated[
        str | None, strawberry.argument(name="avatarUrl")
    ] = strawberry.UNSET,
    badge_config: Annotated[
        GenericScalar | None, strawberry.argument(name="badgeConfig")
    ] = strawberry.UNSET,
    clear_preferred_llm: Annotated[
        bool | None,
        strawberry.argument(
            name="clearPreferredLlm",
            description="When true, clears any per-agent LLM override so the agent falls back to the corpus default.",
        ),
    ] = False,
    description: Annotated[
        str | None, strawberry.argument(name="description")
    ] = strawberry.UNSET,
    is_active: Annotated[
        bool | None, strawberry.argument(name="isActive")
    ] = strawberry.UNSET,
    is_public: Annotated[
        bool | None, strawberry.argument(name="isPublic")
    ] = strawberry.UNSET,
    name: Annotated[str | None, strawberry.argument(name="name")] = strawberry.UNSET,
    permission_required_tools: Annotated[
        list[str | None] | None,
        strawberry.argument(name="permissionRequiredTools"),
    ] = strawberry.UNSET,
    preferred_llm: Annotated[
        str | None,
        strawberry.argument(
            name="preferredLlm",
            description="Set/replace the per-agent LLM override (e.g. 'anthropic:claude-haiku-4-5'). Pass null to leave the existing value unchanged; pass clearPreferredLlm=true to reset back to the corpus default.",
        ),
    ] = strawberry.UNSET,
    slug: Annotated[
        str | None,
        strawberry.argument(name="slug", description="URL-friendly slug for @mentions"),
    ] = strawberry.UNSET,
    system_instructions: Annotated[
        str | None, strawberry.argument(name="systemInstructions")
    ] = strawberry.UNSET,
) -> UpdateAgentConfigurationMutation | None:
    kwargs = strip_unset(
        {
            "agent_id": agent_id,
            "available_tools": available_tools,
            "avatar_url": avatar_url,
            "badge_config": badge_config,
            "clear_preferred_llm": clear_preferred_llm,
            "description": description,
            "is_active": is_active,
            "is_public": is_public,
            "name": name,
            "permission_required_tools": permission_required_tools,
            "preferred_llm": preferred_llm,
            "slug": slug,
            "system_instructions": system_instructions,
        }
    )
    return _mutate_UpdateAgentConfigurationMutation(
        UpdateAgentConfigurationMutation, None, info, **kwargs
    )


def _mutate_DeleteAgentConfigurationMutation(payload_cls, root, info, agent_id):
    """PORT: /home/user/oc-graphene-ref/config/graphql/agent_mutations.py:292

    Port of DeleteAgentConfigurationMutation.mutate
    """
    # @login_required — inlined (see module NOTE above).
    if not info.context.user.is_authenticated:
        raise PermissionDenied()

    @graphql_ratelimit(rate=RateLimits.WRITE_LIGHT)
    def mutate(root, info, agent_id):
        user = info.context.user

        try:
            # ``from_global_id`` can raise a bare ``Exception`` (via
            # ``binascii.Error``) on malformed base64 — catch it so a bad
            # id surfaces through the unified IDOR-safe envelope rather
            # than the generic "Failed to delete" outer-handler message.
            try:
                agent_pk = from_global_id(agent_id)[1]
            except Exception:
                return DeleteAgentConfigurationMutation(
                    ok=False,
                    message="Agent configuration not found",
                )
            agent = AgentConfigurationService.get_agent_by_id(
                user, agent_pk, request=info.context
            )
            if agent is None:
                return DeleteAgentConfigurationMutation(
                    ok=False,
                    message="Agent configuration not found",
                )

            result = AgentConfigurationService.delete_agent(
                user, agent, request=info.context
            )
            if not result.ok:
                return DeleteAgentConfigurationMutation(
                    ok=False,
                    message=result.error,
                )

            return DeleteAgentConfigurationMutation(
                ok=True,
                message="Agent configuration deleted successfully",
            )

        except Exception as e:
            logger.exception("Error deleting agent configuration")
            return DeleteAgentConfigurationMutation(
                ok=False,
                message=f"Failed to delete agent configuration: {str(e)}",
            )

    return mutate(root, info, agent_id)


def m_delete_agent_configuration(
    info: strawberry.Info,
    agent_id: Annotated[
        strawberry.ID,
        strawberry.argument(name="agentId", description="Agent ID to delete"),
    ] = strawberry.UNSET,
) -> DeleteAgentConfigurationMutation | None:
    kwargs = strip_unset({"agent_id": agent_id})
    return _mutate_DeleteAgentConfigurationMutation(
        DeleteAgentConfigurationMutation, None, info, **kwargs
    )


MUTATION_FIELDS = {
    "create_agent_configuration": strawberry.field(
        resolver=m_create_agent_configuration,
        name="createAgentConfiguration",
        description="Create a new agent configuration (admin/corpus owner only).",
    ),
    "update_agent_configuration": strawberry.field(
        resolver=m_update_agent_configuration,
        name="updateAgentConfiguration",
        description="Update an existing agent configuration.",
    ),
    "delete_agent_configuration": strawberry.field(
        resolver=m_delete_agent_configuration,
        name="deleteAgentConfiguration",
        description="Delete an agent configuration.",
    ),
}
