"""Generated strawberry GraphQL module (graphene migration).

Shape-generated from the graphene schema; stub functions marked PORT(...)
carry the ported business logic. See config/graphql_new/manifest.json.
"""
from __future__ import annotations

import datetime
import decimal
import uuid
from typing import Annotated, Any, Optional

import strawberry

from config.graphql.core import permissions as core_permissions
from config.graphql.core.filtering import filterset_factory, setup_filterset
from config.graphql.core.mutations import drf_deletion, drf_mutation
from config.graphql.core.relay import (
    Node,
    get_node_from_global_id,
    make_connection_types,
    register_type,
    resolve_django_connection,
    resolve_django_list,
)
from config.graphql.core.scalars import BigInt, GenericScalar, JSONString
from config.graphql._util import coerce_enum, coerce_str, strip_unset
from config.graphql import enums




@strawberry.type(name="CreateAgentConfigurationMutation", description='Create a new agent configuration (admin/corpus owner only).')
class CreateAgentConfigurationMutation:
    ok: Optional[bool] = strawberry.field(name="ok", default=None)
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))
    agent: Optional[Annotated["AgentConfigurationType", strawberry.lazy("config.graphql.agent_types")]] = strawberry.field(name="agent", default=None)


register_type("CreateAgentConfigurationMutation", CreateAgentConfigurationMutation, model=None)


@strawberry.type(name="UpdateAgentConfigurationMutation", description='Update an existing agent configuration.')
class UpdateAgentConfigurationMutation:
    ok: Optional[bool] = strawberry.field(name="ok", default=None)
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))
    agent: Optional[Annotated["AgentConfigurationType", strawberry.lazy("config.graphql.agent_types")]] = strawberry.field(name="agent", default=None)


register_type("UpdateAgentConfigurationMutation", UpdateAgentConfigurationMutation, model=None)


@strawberry.type(name="DeleteAgentConfigurationMutation", description='Delete an agent configuration.')
class DeleteAgentConfigurationMutation:
    ok: Optional[bool] = strawberry.field(name="ok", default=None)
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))


register_type("DeleteAgentConfigurationMutation", DeleteAgentConfigurationMutation, model=None)


def _mutate_CreateAgentConfigurationMutation(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:75

    Port of CreateAgentConfigurationMutation.mutate
    """
    raise NotImplementedError("_mutate_CreateAgentConfigurationMutation not yet ported — see manifest")


def m_create_agent_configuration(info: strawberry.Info, available_tools: Annotated[Optional[list[Optional[str]]], strawberry.argument(name="availableTools", description='List of tools available to the agent')] = strawberry.UNSET, avatar_url: Annotated[Optional[str], strawberry.argument(name="avatarUrl", description='Avatar URL')] = strawberry.UNSET, badge_config: Annotated[Optional[GenericScalar], strawberry.argument(name="badgeConfig", description='Badge display configuration')] = strawberry.UNSET, corpus_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="corpusId", description='Corpus ID for corpus-specific agents')] = strawberry.UNSET, description: Annotated[str, strawberry.argument(name="description", description='Agent description')] = strawberry.UNSET, is_public: Annotated[Optional[bool], strawberry.argument(name="isPublic", description='Whether agent is publicly visible')] = True, name: Annotated[str, strawberry.argument(name="name", description='Agent name')] = strawberry.UNSET, permission_required_tools: Annotated[Optional[list[Optional[str]]], strawberry.argument(name="permissionRequiredTools", description='List of tools requiring explicit permission')] = strawberry.UNSET, preferred_llm: Annotated[Optional[str], strawberry.argument(name="preferredLlm", description="Optional pydantic-ai model spec to use when this agent runs (e.g. 'anthropic:claude-haiku-4-5'). Overrides Corpus.preferred_llm. Empty falls back to the corpus default.")] = strawberry.UNSET, scope: Annotated[str, strawberry.argument(name="scope", description='Scope: GLOBAL or CORPUS')] = strawberry.UNSET, slug: Annotated[Optional[str], strawberry.argument(name="slug", description='URL-friendly slug for @mentions (auto-generated from name if not provided)')] = strawberry.UNSET, system_instructions: Annotated[str, strawberry.argument(name="systemInstructions", description='System instructions for the agent')] = strawberry.UNSET) -> Optional["CreateAgentConfigurationMutation"]:
    kwargs = strip_unset({"available_tools": available_tools, "avatar_url": avatar_url, "badge_config": badge_config, "corpus_id": corpus_id, "description": description, "is_public": is_public, "name": name, "permission_required_tools": permission_required_tools, "preferred_llm": preferred_llm, "scope": scope, "slug": slug, "system_instructions": system_instructions})
    return _mutate_CreateAgentConfigurationMutation(CreateAgentConfigurationMutation, None, info, **kwargs)


def _mutate_UpdateAgentConfigurationMutation(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:198

    Port of UpdateAgentConfigurationMutation.mutate
    """
    raise NotImplementedError("_mutate_UpdateAgentConfigurationMutation not yet ported — see manifest")


def m_update_agent_configuration(info: strawberry.Info, agent_id: Annotated[strawberry.ID, strawberry.argument(name="agentId", description='Agent ID to update')] = strawberry.UNSET, available_tools: Annotated[Optional[list[Optional[str]]], strawberry.argument(name="availableTools")] = strawberry.UNSET, avatar_url: Annotated[Optional[str], strawberry.argument(name="avatarUrl")] = strawberry.UNSET, badge_config: Annotated[Optional[GenericScalar], strawberry.argument(name="badgeConfig")] = strawberry.UNSET, clear_preferred_llm: Annotated[Optional[bool], strawberry.argument(name="clearPreferredLlm", description='When true, clears any per-agent LLM override so the agent falls back to the corpus default.')] = False, description: Annotated[Optional[str], strawberry.argument(name="description")] = strawberry.UNSET, is_active: Annotated[Optional[bool], strawberry.argument(name="isActive")] = strawberry.UNSET, is_public: Annotated[Optional[bool], strawberry.argument(name="isPublic")] = strawberry.UNSET, name: Annotated[Optional[str], strawberry.argument(name="name")] = strawberry.UNSET, permission_required_tools: Annotated[Optional[list[Optional[str]]], strawberry.argument(name="permissionRequiredTools")] = strawberry.UNSET, preferred_llm: Annotated[Optional[str], strawberry.argument(name="preferredLlm", description="Set/replace the per-agent LLM override (e.g. 'anthropic:claude-haiku-4-5'). Pass null to leave the existing value unchanged; pass clearPreferredLlm=true to reset back to the corpus default.")] = strawberry.UNSET, slug: Annotated[Optional[str], strawberry.argument(name="slug", description='URL-friendly slug for @mentions')] = strawberry.UNSET, system_instructions: Annotated[Optional[str], strawberry.argument(name="systemInstructions")] = strawberry.UNSET) -> Optional["UpdateAgentConfigurationMutation"]:
    kwargs = strip_unset({"agent_id": agent_id, "available_tools": available_tools, "avatar_url": avatar_url, "badge_config": badge_config, "clear_preferred_llm": clear_preferred_llm, "description": description, "is_active": is_active, "is_public": is_public, "name": name, "permission_required_tools": permission_required_tools, "preferred_llm": preferred_llm, "slug": slug, "system_instructions": system_instructions})
    return _mutate_UpdateAgentConfigurationMutation(UpdateAgentConfigurationMutation, None, info, **kwargs)


def _mutate_DeleteAgentConfigurationMutation(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:290

    Port of DeleteAgentConfigurationMutation.mutate
    """
    raise NotImplementedError("_mutate_DeleteAgentConfigurationMutation not yet ported — see manifest")


def m_delete_agent_configuration(info: strawberry.Info, agent_id: Annotated[strawberry.ID, strawberry.argument(name="agentId", description='Agent ID to delete')] = strawberry.UNSET) -> Optional["DeleteAgentConfigurationMutation"]:
    kwargs = strip_unset({"agent_id": agent_id})
    return _mutate_DeleteAgentConfigurationMutation(DeleteAgentConfigurationMutation, None, info, **kwargs)



MUTATION_FIELDS = {
    "create_agent_configuration": strawberry.field(resolver=m_create_agent_configuration, name="createAgentConfiguration", description='Create a new agent configuration (admin/corpus owner only).'),
    "update_agent_configuration": strawberry.field(resolver=m_update_agent_configuration, name="updateAgentConfiguration", description='Update an existing agent configuration.'),
    "delete_agent_configuration": strawberry.field(resolver=m_delete_agent_configuration, name="deleteAgentConfiguration", description='Delete an agent configuration.'),
}
