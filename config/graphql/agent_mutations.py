"""
GraphQL mutations for the agent configuration system.

Permission and CRUD logic lives in
:class:`opencontractserver.agents.services.AgentConfigurationService`;
the mutations decode global IDs, fetch the target via the service's
IDOR-safe lookup, and forward the change to the service.
"""

import logging

import graphene
from graphene.types.generic import GenericScalar
from graphql_jwt.decorators import login_required
from graphql_relay import from_global_id

from config.graphql.graphene_types import AgentConfigurationType
from config.graphql.ratelimits import RateLimits, graphql_ratelimit
from opencontractserver.agents.services import AgentConfigurationService
from opencontractserver.corpuses.models import Corpus
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import get_for_user_or_none

logger = logging.getLogger(__name__)


class CreateAgentConfigurationMutation(graphene.Mutation):
    """Create a new agent configuration (admin/corpus owner only)."""

    class Arguments:
        name = graphene.String(required=True, description="Agent name")
        slug = graphene.String(
            required=False,
            description="URL-friendly slug for @mentions (auto-generated from name if not provided)",
        )
        description = graphene.String(required=True, description="Agent description")
        system_instructions = graphene.String(
            required=True, description="System instructions for the agent"
        )
        available_tools = graphene.List(
            graphene.String,
            required=False,
            description="List of tools available to the agent",
        )
        permission_required_tools = graphene.List(
            graphene.String,
            required=False,
            description="List of tools requiring explicit permission",
        )
        badge_config = GenericScalar(
            required=False,
            description="Badge display configuration",
        )
        avatar_url = graphene.String(required=False, description="Avatar URL")
        scope = graphene.String(required=True, description="Scope: GLOBAL or CORPUS")
        corpus_id = graphene.ID(
            required=False, description="Corpus ID for corpus-specific agents"
        )
        is_public = graphene.Boolean(
            required=False,
            description="Whether agent is publicly visible",
            default_value=True,
        )

    ok = graphene.Boolean()
    message = graphene.String()
    agent = graphene.Field(AgentConfigurationType)

    @login_required
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
    ) -> "CreateAgentConfigurationMutation":
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
                corpus = get_for_user_or_none(Corpus, corpus_pk, user)
                if corpus is None or not corpus.user_can(
                    user, PermissionTypes.CRUD, request=info.context
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


class UpdateAgentConfigurationMutation(graphene.Mutation):
    """Update an existing agent configuration."""

    class Arguments:
        agent_id = graphene.ID(required=True, description="Agent ID to update")
        name = graphene.String(required=False)
        slug = graphene.String(
            required=False,
            description="URL-friendly slug for @mentions",
        )
        description = graphene.String(required=False)
        system_instructions = graphene.String(required=False)
        available_tools = graphene.List(graphene.String, required=False)
        permission_required_tools = graphene.List(graphene.String, required=False)
        badge_config = GenericScalar(required=False)
        avatar_url = graphene.String(required=False)
        is_active = graphene.Boolean(required=False)
        is_public = graphene.Boolean(required=False)

    ok = graphene.Boolean()
    message = graphene.String()
    agent = graphene.Field(AgentConfigurationType)

    @login_required
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
    ) -> "UpdateAgentConfigurationMutation":
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


class DeleteAgentConfigurationMutation(graphene.Mutation):
    """Delete an agent configuration."""

    class Arguments:
        agent_id = graphene.ID(required=True, description="Agent ID to delete")

    ok = graphene.Boolean()
    message = graphene.String()

    @login_required
    @graphql_ratelimit(rate=RateLimits.WRITE_LIGHT)
    def mutate(root, info, agent_id) -> "DeleteAgentConfigurationMutation":
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
