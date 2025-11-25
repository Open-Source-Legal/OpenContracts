"""
GraphQL mutations for the agent configuration system.
"""

import logging

import graphene
from graphql_jwt.decorators import login_required
from graphql_relay import from_global_id

from config.graphql.graphene_types import AgentConfigurationType
from config.graphql.ratelimits import RateLimits, graphql_ratelimit
from opencontractserver.agents.models import AgentConfiguration
from opencontractserver.corpuses.models import Corpus
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import (
    set_permissions_for_obj_to_user,
    user_has_permission_for_obj,
)

logger = logging.getLogger(__name__)


class CreateAgentConfigurationMutation(graphene.Mutation):
    """Create a new agent configuration (admin/corpus owner only)."""

    class Arguments:
        name = graphene.String(required=True, description="Agent name")
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
        badge_config = graphene.JSONString(
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
        available_tools=None,
        permission_required_tools=None,
        badge_config=None,
        avatar_url=None,
        corpus_id=None,
        is_public=True,
    ):
        user = info.context.user

        try:
            # Permission check: must be superuser or corpus owner
            corpus = None
            if corpus_id:
                corpus_pk = from_global_id(corpus_id)[1]
                # Use visible_to_user to prevent IDOR - returns same error whether
                # corpus doesn't exist or user lacks permission
                try:
                    corpus = Corpus.objects.visible_to_user(user).get(pk=corpus_pk)
                except Corpus.DoesNotExist:
                    return CreateAgentConfigurationMutation(
                        ok=False,
                        message="Corpus not found",
                        agent=None,
                    )

                # Check if user has permission for this corpus
                if not user.is_superuser and not user_has_permission_for_obj(
                    user, corpus, PermissionTypes.CRUD, include_group_permissions=True
                ):
                    return CreateAgentConfigurationMutation(
                        ok=False,
                        message="Corpus not found",
                        agent=None,
                    )
            elif scope == "CORPUS":
                return CreateAgentConfigurationMutation(
                    ok=False,
                    message="corpus_id is required for CORPUS scope agents.",
                    agent=None,
                )
            elif not user.is_superuser:
                return CreateAgentConfigurationMutation(
                    ok=False,
                    message="You must be a superuser to create global agents.",
                    agent=None,
                )

            # Validate scope
            if scope not in ["GLOBAL", "CORPUS"]:
                return CreateAgentConfigurationMutation(
                    ok=False,
                    message="Scope must be GLOBAL or CORPUS.",
                    agent=None,
                )

            # Create the agent
            agent = AgentConfiguration.objects.create(
                name=name,
                description=description,
                system_instructions=system_instructions,
                available_tools=available_tools or [],
                permission_required_tools=permission_required_tools or [],
                badge_config=badge_config if badge_config is not None else {},
                avatar_url=avatar_url,
                scope=scope,
                corpus=corpus,
                creator=user,
                is_public=is_public,
                is_active=True,
            )

            # Set permissions
            set_permissions_for_obj_to_user(user, agent, [PermissionTypes.CRUD])

            return CreateAgentConfigurationMutation(
                ok=True,
                message="Agent configuration created successfully",
                agent=agent,
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
        description = graphene.String(required=False)
        system_instructions = graphene.String(required=False)
        available_tools = graphene.List(graphene.String, required=False)
        permission_required_tools = graphene.List(graphene.String, required=False)
        badge_config = graphene.JSONString(required=False)
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
        description=None,
        system_instructions=None,
        available_tools=None,
        permission_required_tools=None,
        badge_config=None,
        avatar_url=None,
        is_active=None,
        is_public=None,
    ):
        user = info.context.user

        try:
            agent_pk = from_global_id(agent_id)[1]
            # Use visible_to_user to prevent IDOR
            try:
                agent = AgentConfiguration.objects.visible_to_user(user).get(
                    pk=agent_pk
                )
            except AgentConfiguration.DoesNotExist:
                return UpdateAgentConfigurationMutation(
                    ok=False,
                    message="Agent configuration not found",
                    agent=None,
                )

            # Permission check
            if not user.is_superuser and not user_has_permission_for_obj(
                user, agent, PermissionTypes.CRUD, include_group_permissions=True
            ):
                return UpdateAgentConfigurationMutation(
                    ok=False,
                    message="Agent configuration not found",
                    agent=None,
                )

            # Update fields
            if name is not None:
                agent.name = name
            if description is not None:
                agent.description = description
            if system_instructions is not None:
                agent.system_instructions = system_instructions
            if available_tools is not None:
                agent.available_tools = available_tools
            if permission_required_tools is not None:
                agent.permission_required_tools = permission_required_tools
            if badge_config is not None:
                agent.badge_config = badge_config
            if avatar_url is not None:
                agent.avatar_url = avatar_url
            if is_active is not None:
                agent.is_active = is_active
            if is_public is not None:
                agent.is_public = is_public

            agent.save()

            return UpdateAgentConfigurationMutation(
                ok=True,
                message="Agent configuration updated successfully",
                agent=agent,
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
    def mutate(root, info, agent_id):
        user = info.context.user

        try:
            agent_pk = from_global_id(agent_id)[1]
            # Use visible_to_user to prevent IDOR
            try:
                agent = AgentConfiguration.objects.visible_to_user(user).get(
                    pk=agent_pk
                )
            except AgentConfiguration.DoesNotExist:
                return DeleteAgentConfigurationMutation(
                    ok=False,
                    message="Agent configuration not found",
                )

            # Permission check
            if not user.is_superuser and not user_has_permission_for_obj(
                user, agent, PermissionTypes.CRUD, include_group_permissions=True
            ):
                return DeleteAgentConfigurationMutation(
                    ok=False,
                    message="Agent configuration not found",
                )

            agent.delete()

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
