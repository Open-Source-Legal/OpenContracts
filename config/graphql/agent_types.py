"""GraphQL type definitions for agent and action types."""

from typing import Any

import graphene
from graphene import relay
from graphene_django import DjangoObjectType

from config.graphql.base import CountableConnection
from config.graphql.permissioning.permission_annotator.mixins import (
    AnnotatePermissionsForReadMixin,
)
from opencontractserver.agents.models import AgentActionResult, AgentConfiguration
from opencontractserver.corpuses.models import (
    CorpusAction,
    CorpusActionExecution,
    CorpusActionTemplate,
)


class CorpusActionType(AnnotatePermissionsForReadMixin, DjangoObjectType):
    # Expose agent-related fields explicitly
    pre_authorized_tools = graphene.List(graphene.String)
    source_template = graphene.Field(lambda: CorpusActionTemplateType)

    class Meta:
        model = CorpusAction
        interfaces = [relay.Node]
        connection_class = CountableConnection
        filter_fields = {
            "id": ["exact"],
            "name": ["exact", "icontains", "istartswith"],
            "corpus__id": ["exact"],
            "fieldset__id": ["exact"],
            "analyzer__id": ["exact"],
            "agent_config__id": ["exact"],
            "trigger": ["exact"],
            "creator__id": ["exact"],
            "source_template__id": ["exact"],
        }

    def resolve_pre_authorized_tools(self, info) -> Any:
        """Resolve pre_authorized_tools as a list of strings."""
        return self.pre_authorized_tools or []


class AgentActionResultType(AnnotatePermissionsForReadMixin, DjangoObjectType):
    """GraphQL type for AgentActionResult - results from agent-based corpus actions."""

    tools_executed = graphene.List(graphene.JSONString)
    execution_metadata = graphene.JSONString()
    duration_seconds = graphene.Float()

    class Meta:
        model = AgentActionResult
        interfaces = [relay.Node]
        connection_class = CountableConnection
        filter_fields = {
            "id": ["exact"],
            "corpus_action__id": ["exact"],
            "document__id": ["exact"],
            "status": ["exact"],
            "creator__id": ["exact"],
        }

    def resolve_tools_executed(self, info) -> Any:
        """Resolve tools_executed as a list of JSON objects."""
        return self.tools_executed or []

    def resolve_execution_metadata(self, info) -> Any:
        """Resolve execution_metadata as JSON dict."""
        return self.execution_metadata or {}

    def resolve_duration_seconds(self, info) -> Any:
        """Resolve duration from the model property."""
        return self.duration_seconds


class CorpusActionExecutionType(AnnotatePermissionsForReadMixin, DjangoObjectType):
    """GraphQL type for CorpusActionExecution - action execution tracking records."""

    # Computed fields
    duration_seconds = graphene.Float()
    wait_time_seconds = graphene.Float()

    # JSON fields
    affected_objects = graphene.List(graphene.JSONString)
    execution_metadata = graphene.JSONString()

    class Meta:
        model = CorpusActionExecution
        interfaces = [relay.Node]
        connection_class = CountableConnection
        filter_fields = {
            "id": ["exact"],
            "corpus__id": ["exact"],
            "corpus_action__id": ["exact"],
            "document__id": ["exact"],
            "status": ["exact"],
            "action_type": ["exact"],
            "trigger": ["exact"],
            "creator__id": ["exact"],
        }

    def resolve_duration_seconds(self, info) -> Any:
        """Resolve duration from the model property."""
        return self.duration_seconds

    def resolve_wait_time_seconds(self, info) -> Any:
        """Resolve wait time from the model property."""
        return self.wait_time_seconds

    def resolve_affected_objects(self, info) -> Any:
        """Resolve affected_objects as a list of JSON objects."""
        return self.affected_objects or []

    def resolve_execution_metadata(self, info) -> Any:
        """Resolve execution_metadata as JSON dict."""
        return self.execution_metadata or {}


class CorpusActionTrailStatsType(graphene.ObjectType):
    """Aggregated statistics for corpus action trail."""

    total_executions = graphene.Int()
    completed = graphene.Int()
    failed = graphene.Int()
    running = graphene.Int()
    queued = graphene.Int()
    skipped = graphene.Int()
    avg_duration_seconds = graphene.Float()
    fieldset_count = graphene.Int()
    analyzer_count = graphene.Int()
    agent_count = graphene.Int()


# ---------------- Agent Configuration Types ----------------
class AgentConfigurationType(AnnotatePermissionsForReadMixin, DjangoObjectType):
    """GraphQL type for agent configurations."""

    # Explicit field declarations for JSONField arrays to ensure proper typing
    # Without these, JSONField converts to GenericScalar which may not serialize arrays correctly
    available_tools = graphene.List(
        graphene.String,
        description="List of tool identifiers this agent can use",
    )
    permission_required_tools = graphene.List(
        graphene.String,
        description="Subset of tools that require explicit user permission to use",
    )

    mention_format = graphene.String(
        description="The @ mention format for this agent (e.g., '@agent:research-assistant')"
    )

    class Meta:
        model = AgentConfiguration
        interfaces = [relay.Node]
        connection_class = CountableConnection
        fields = (
            "id",
            "name",
            "slug",
            "description",
            "system_instructions",
            "available_tools",
            "permission_required_tools",
            "badge_config",
            "avatar_url",
            "scope",
            "corpus",
            "is_active",
            "creator",
            "is_public",
            "preferred_llm",
            "created",
            "modified",
            "mention_format",
        )
        filter_fields = {
            "scope": ["exact"],
            "is_active": ["exact"],
            "corpus": ["exact"],
        }

    def resolve_mention_format(self, info) -> Any:
        """Return the @ mention format for this agent."""
        if self.slug:
            return f"@agent:{self.slug}"
        return None

    def resolve_available_tools(self, info) -> Any:
        """Resolve available_tools as a list of strings, ensuring proper array type."""
        return self.available_tools if self.available_tools else []

    def resolve_permission_required_tools(self, info) -> Any:
        """Resolve permission_required_tools as a list of strings, ensuring proper array type."""
        return self.permission_required_tools if self.permission_required_tools else []


# ---------------- Agent Tool Types ----------------
class ToolParameterType(graphene.ObjectType):
    """GraphQL type for tool parameter definitions."""

    name = graphene.String(required=True, description="Parameter name")
    description = graphene.String(required=True, description="Parameter description")
    required = graphene.Boolean(
        required=True, description="Whether the parameter is required"
    )


class AvailableToolType(graphene.ObjectType):
    """
    GraphQL type for available tools that can be assigned to agents.

    This provides metadata about each tool, including its description,
    category, and requirements.
    """

    name = graphene.String(
        required=True, description="Tool name (used in configuration)"
    )
    description = graphene.String(
        required=True, description="Human-readable description of the tool"
    )
    category = graphene.String(
        required=True,
        description="Tool category (search, document, corpus, notes, annotations, coordination)",
    )
    # Use camelCase names to match GraphQL conventions (ObjectType doesn't auto-convert)
    requiresCorpus = graphene.Boolean(
        required=True, description="Whether this tool requires a corpus context"
    )
    requiresApproval = graphene.Boolean(
        required=True,
        description="Whether this tool requires user approval before execution",
    )
    parameters = graphene.List(
        graphene.NonNull(ToolParameterType),
        required=True,
        description="List of parameters accepted by this tool",
    )


class CorpusActionTemplateType(DjangoObjectType):
    """GraphQL type for CorpusActionTemplate — read-only, system-level."""

    pre_authorized_tools = graphene.List(graphene.String)

    class Meta:
        model = CorpusActionTemplate
        interfaces = [relay.Node]
        connection_class = CountableConnection
        fields = (
            "id",
            "name",
            "description",
            "trigger",
            "is_active",
            "disabled_on_clone",
            "sort_order",
            "agent_config",
            "pre_authorized_tools",
            "created",
        )

    def resolve_pre_authorized_tools(self, info) -> Any:
        return self.pre_authorized_tools or []
