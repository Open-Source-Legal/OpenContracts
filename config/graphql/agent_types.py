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

from config.graphql.filters import AnnotationFilter
from opencontractserver.agents.models import AgentActionResult
from opencontractserver.agents.models import AgentConfiguration
from opencontractserver.corpuses.models import CorpusAction
from opencontractserver.corpuses.models import CorpusActionExecution
from opencontractserver.corpuses.models import CorpusActionTemplate


def _resolve_CorpusActionType_pre_authorized_tools(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/agent_types.py:42

    Port of CorpusActionType.resolve_pre_authorized_tools
    """
    raise NotImplementedError("_resolve_CorpusActionType_pre_authorized_tools not yet ported — see manifest")


@strawberry.type(name="CorpusActionType")
class CorpusActionType(Node):
    user_lock: Optional[Annotated["UserType", strawberry.lazy("config.graphql.user_types")]] = strawberry.field(name="userLock", default=None)
    backend_lock: bool = strawberry.field(name="backendLock", default=None)
    is_public: bool = strawberry.field(name="isPublic", default=None)
    creator: Annotated["UserType", strawberry.lazy("config.graphql.user_types")] = strawberry.field(name="creator", default=None)
    created: datetime.datetime = strawberry.field(name="created", default=None)
    modified: datetime.datetime = strawberry.field(name="modified", default=None)
    @strawberry.field(name="name")
    def name(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "name", None))
    corpus: Annotated["CorpusType", strawberry.lazy("config.graphql.corpus_types")] = strawberry.field(name="corpus", default=None)
    fieldset: Optional[Annotated["FieldsetType", strawberry.lazy("config.graphql.extract_types")]] = strawberry.field(name="fieldset", default=None)
    analyzer: Optional[Annotated["AnalyzerType", strawberry.lazy("config.graphql.extract_types")]] = strawberry.field(name="analyzer", default=None)
    agent_config: Optional["AgentConfigurationType"] = strawberry.field(name="agentConfig", description='Optional agent configuration for persona/tool defaults. Not required for agent actions — task_instructions alone is sufficient.', default=None)
    @strawberry.field(name="taskInstructions", description="What the agent should do (e.g., 'Read this document and update its description with a one-paragraph summary'). This is the single required field for agent-based actions.")
    def task_instructions(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "task_instructions", None))
    @strawberry.field(name="preAuthorizedTools")
    def pre_authorized_tools(self, info: strawberry.Info) -> Optional[list[Optional[str]]]:
        kwargs = strip_unset({})
        return _resolve_CorpusActionType_pre_authorized_tools(self, info, **kwargs)
    @strawberry.field(name="trigger")
    def trigger(self, info: strawberry.Info) -> enums.CorpusesCorpusActionTriggerChoices:
        return coerce_enum(enums.CorpusesCorpusActionTriggerChoices, getattr(self, "trigger", None))
    disabled: bool = strawberry.field(name="disabled", default=None)
    run_on_all_corpuses: bool = strawberry.field(name="runOnAllCorpuses", default=None)
    source_template: Optional["CorpusActionTemplateType"] = strawberry.field(name="sourceTemplate", default=None)
    @strawberry.field(name="executions", description='The corpus action configuration that was executed')
    def executions(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET, id: Annotated[Optional[strawberry.ID], strawberry.argument(name="id")] = strawberry.UNSET, corpus__id: Annotated[Optional[strawberry.ID], strawberry.argument(name="corpus_Id")] = strawberry.UNSET, corpus_action__id: Annotated[Optional[strawberry.ID], strawberry.argument(name="corpusAction_Id")] = strawberry.UNSET, document__id: Annotated[Optional[strawberry.ID], strawberry.argument(name="document_Id")] = strawberry.UNSET, status: Annotated[Optional[enums.CorpusesCorpusActionExecutionStatusChoices], strawberry.argument(name="status")] = strawberry.UNSET, action_type: Annotated[Optional[enums.CorpusesCorpusActionExecutionActionTypeChoices], strawberry.argument(name="actionType")] = strawberry.UNSET, trigger: Annotated[Optional[enums.CorpusesCorpusActionExecutionTriggerChoices], strawberry.argument(name="trigger")] = strawberry.UNSET, creator__id: Annotated[Optional[strawberry.ID], strawberry.argument(name="creator_Id")] = strawberry.UNSET) -> "CorpusActionExecutionTypeConnection":
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last, "id": id, "corpus__id": corpus__id, "corpus_action__id": corpus_action__id, "document__id": document__id, "status": status, "action_type": action_type, "trigger": trigger, "creator__id": creator__id})
        resolved = getattr(self, "executions", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="CorpusActionExecutionType", filterset_class=filterset_factory(CorpusActionExecution, fields={'id': ['exact'], 'corpus__id': ['exact'], 'corpus_action__id': ['exact'], 'document__id': ['exact'], 'status': ['exact'], 'action_type': ['exact'], 'trigger': ['exact'], 'creator__id': ['exact']}), filter_args={"id": "id", "corpus__id": "corpus__id", "corpus_action__id": "corpus_action__id", "document__id": "document__id", "status": "status", "action_type": "action_type", "trigger": "trigger", "creator__id": "creator__id"}, )
    @strawberry.field(name="createdAnnotations", description='If set, this annotation was created by a corpus action agent')
    def created_annotations(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET, raw_text__contains: Annotated[Optional[str], strawberry.argument(name="rawText_Contains")] = strawberry.UNSET, annotation_label_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="annotationLabelId")] = strawberry.UNSET, annotation_label__text: Annotated[Optional[str], strawberry.argument(name="annotationLabel_Text")] = strawberry.UNSET, annotation_label__text__contains: Annotated[Optional[str], strawberry.argument(name="annotationLabel_Text_Contains")] = strawberry.UNSET, annotation_label__description__contains: Annotated[Optional[str], strawberry.argument(name="annotationLabel_Description_Contains")] = strawberry.UNSET, annotation_label__label_type: Annotated[Optional[enums.AnnotationsAnnotationLabelLabelTypeChoices], strawberry.argument(name="annotationLabel_LabelType")] = strawberry.UNSET, analysis__isnull: Annotated[Optional[bool], strawberry.argument(name="analysis_Isnull")] = strawberry.UNSET, document_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="documentId")] = strawberry.UNSET, corpus_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="corpusId")] = strawberry.UNSET, structural: Annotated[Optional[bool], strawberry.argument(name="structural")] = strawberry.UNSET, uses_label_from_labelset_id: Annotated[Optional[str], strawberry.argument(name="usesLabelFromLabelsetId")] = strawberry.UNSET, created_by_analysis_ids: Annotated[Optional[str], strawberry.argument(name="createdByAnalysisIds")] = strawberry.UNSET, created_with_analyzer_id: Annotated[Optional[str], strawberry.argument(name="createdWithAnalyzerId")] = strawberry.UNSET, order_by: Annotated[Optional[str], strawberry.argument(name="orderBy", description='Ordering')] = strawberry.UNSET) -> Annotated["AnnotationTypeConnection", strawberry.lazy("config.graphql.annotation_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last, "raw_text__contains": raw_text__contains, "annotation_label_id": annotation_label_id, "annotation_label__text": annotation_label__text, "annotation_label__text__contains": annotation_label__text__contains, "annotation_label__description__contains": annotation_label__description__contains, "annotation_label__label_type": annotation_label__label_type, "analysis__isnull": analysis__isnull, "document_id": document_id, "corpus_id": corpus_id, "structural": structural, "uses_label_from_labelset_id": uses_label_from_labelset_id, "created_by_analysis_ids": created_by_analysis_ids, "created_with_analyzer_id": created_with_analyzer_id, "order_by": order_by})
        resolved = getattr(self, "created_annotations", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="AnnotationType", filterset_class=setup_filterset(AnnotationFilter), filter_args={"raw_text__contains": "raw_text__contains", "annotation_label_id": "annotation_label_id", "annotation_label__text": "annotation_label__text", "annotation_label__text__contains": "annotation_label__text__contains", "annotation_label__description__contains": "annotation_label__description__contains", "annotation_label__label_type": "annotation_label__label_type", "analysis__isnull": "analysis__isnull", "document_id": "document_id", "corpus_id": "corpus_id", "structural": "structural", "uses_label_from_labelset_id": "uses_label_from_labelset_id", "created_by_analysis_ids": "created_by_analysis_ids", "created_with_analyzer_id": "created_with_analyzer_id", "order_by": "order_by"}, )
    @strawberry.field(name="analyses")
    def analyses(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["AnalysisTypeConnection", strawberry.lazy("config.graphql.extract_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "analyses", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="AnalysisType", )
    @strawberry.field(name="extracts")
    def extracts(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["ExtractTypeConnection", strawberry.lazy("config.graphql.extract_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "extracts", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="ExtractType", )
    @strawberry.field(name="agentResults", description='The corpus action that triggered this execution')
    def agent_results(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET, id: Annotated[Optional[strawberry.ID], strawberry.argument(name="id")] = strawberry.UNSET, corpus_action__id: Annotated[Optional[strawberry.ID], strawberry.argument(name="corpusAction_Id")] = strawberry.UNSET, document__id: Annotated[Optional[strawberry.ID], strawberry.argument(name="document_Id")] = strawberry.UNSET, status: Annotated[Optional[enums.AgentsAgentActionResultStatusChoices], strawberry.argument(name="status")] = strawberry.UNSET, creator__id: Annotated[Optional[strawberry.ID], strawberry.argument(name="creator_Id")] = strawberry.UNSET) -> "AgentActionResultTypeConnection":
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last, "id": id, "corpus_action__id": corpus_action__id, "document__id": document__id, "status": status, "creator__id": creator__id})
        resolved = getattr(self, "agent_results", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="AgentActionResultType", filterset_class=filterset_factory(AgentActionResult, fields={'id': ['exact'], 'corpus_action__id': ['exact'], 'document__id': ['exact'], 'status': ['exact'], 'creator__id': ['exact']}), filter_args={"id": "id", "corpus_action__id": "corpus_action__id", "document__id": "document__id", "status": "status", "creator__id": "creator__id"}, )
    @strawberry.field(name="myPermissions")
    def my_permissions(self, info: strawberry.Info) -> Optional[GenericScalar]:
        return core_permissions.resolve_my_permissions(self, info)
    @strawberry.field(name="isPublished")
    def is_published(self, info: strawberry.Info) -> Optional[bool]:
        return core_permissions.resolve_is_published(self, info)
    @strawberry.field(name="objectSharedWith")
    def object_shared_with(self, info: strawberry.Info) -> Optional[GenericScalar]:
        return core_permissions.resolve_object_shared_with(self, info)


register_type("CorpusActionType", CorpusActionType, model=CorpusAction)


CorpusActionTypeConnection = make_connection_types(CorpusActionType, type_name="CorpusActionTypeConnection", countable=True, pdf_page_aware=False)


def _resolve_CorpusActionExecutionType_affected_objects(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/agent_types.py:113

    Port of CorpusActionExecutionType.resolve_affected_objects
    """
    raise NotImplementedError("_resolve_CorpusActionExecutionType_affected_objects not yet ported — see manifest")


def _resolve_CorpusActionExecutionType_execution_metadata(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/agent_types.py:117

    Port of CorpusActionExecutionType.resolve_execution_metadata
    """
    raise NotImplementedError("_resolve_CorpusActionExecutionType_execution_metadata not yet ported — see manifest")


def _resolve_CorpusActionExecutionType_duration_seconds(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/agent_types.py:105

    Port of CorpusActionExecutionType.resolve_duration_seconds
    """
    raise NotImplementedError("_resolve_CorpusActionExecutionType_duration_seconds not yet ported — see manifest")


def _resolve_CorpusActionExecutionType_wait_time_seconds(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/agent_types.py:109

    Port of CorpusActionExecutionType.resolve_wait_time_seconds
    """
    raise NotImplementedError("_resolve_CorpusActionExecutionType_wait_time_seconds not yet ported — see manifest")


@strawberry.type(name="CorpusActionExecutionType", description='GraphQL type for CorpusActionExecution - action execution tracking records.')
class CorpusActionExecutionType(Node):
    user_lock: Optional[Annotated["UserType", strawberry.lazy("config.graphql.user_types")]] = strawberry.field(name="userLock", default=None)
    backend_lock: bool = strawberry.field(name="backendLock", default=None)
    is_public: bool = strawberry.field(name="isPublic", default=None)
    creator: Annotated["UserType", strawberry.lazy("config.graphql.user_types")] = strawberry.field(name="creator", default=None)
    created: datetime.datetime = strawberry.field(name="created", default=None)
    modified: datetime.datetime = strawberry.field(name="modified", default=None)
    corpus_action: "CorpusActionType" = strawberry.field(name="corpusAction", description='The corpus action configuration that was executed', default=None)
    document: Optional[Annotated["DocumentType", strawberry.lazy("config.graphql.document_types")]] = strawberry.field(name="document", description='The document this action was executed on (null for thread-based actions)', default=None)
    conversation: Optional[Annotated["ConversationType", strawberry.lazy("config.graphql.conversation_types")]] = strawberry.field(name="conversation", description='The thread that triggered this execution (for thread-based actions)', default=None)
    message: Optional[Annotated["MessageType", strawberry.lazy("config.graphql.conversation_types")]] = strawberry.field(name="message", description='The message that triggered this execution (for NEW_MESSAGE trigger)', default=None)
    corpus: Annotated["CorpusType", strawberry.lazy("config.graphql.corpus_types")] = strawberry.field(name="corpus", description='Denormalized corpus reference for fast queries', default=None)
    @strawberry.field(name="actionType", description='Type of action (fieldset/analyzer/agent)')
    def action_type(self, info: strawberry.Info) -> enums.CorpusesCorpusActionExecutionActionTypeChoices:
        return coerce_enum(enums.CorpusesCorpusActionExecutionActionTypeChoices, getattr(self, "action_type", None))
    @strawberry.field(name="status")
    def status(self, info: strawberry.Info) -> enums.CorpusesCorpusActionExecutionStatusChoices:
        return coerce_enum(enums.CorpusesCorpusActionExecutionStatusChoices, getattr(self, "status", None))
    queued_at: datetime.datetime = strawberry.field(name="queuedAt", description='When the execution was queued (set explicitly for bulk_create)', default=None)
    started_at: Optional[datetime.datetime] = strawberry.field(name="startedAt", description='When execution actually started', default=None)
    completed_at: Optional[datetime.datetime] = strawberry.field(name="completedAt", description='When execution completed (success or failure)', default=None)
    @strawberry.field(name="trigger", description='What triggered this execution')
    def trigger(self, info: strawberry.Info) -> enums.CorpusesCorpusActionExecutionTriggerChoices:
        return coerce_enum(enums.CorpusesCorpusActionExecutionTriggerChoices, getattr(self, "trigger", None))
    @strawberry.field(name="affectedObjects")
    def affected_objects(self, info: strawberry.Info) -> Optional[list[Optional[JSONString]]]:
        kwargs = strip_unset({})
        return _resolve_CorpusActionExecutionType_affected_objects(self, info, **kwargs)
    agent_result: Optional["AgentActionResultType"] = strawberry.field(name="agentResult", description='Detailed agent result (for agent actions only)', default=None)
    extract: Optional[Annotated["ExtractType", strawberry.lazy("config.graphql.extract_types")]] = strawberry.field(name="extract", description='Extract created (for fieldset actions only)', default=None)
    analysis: Optional[Annotated["AnalysisType", strawberry.lazy("config.graphql.extract_types")]] = strawberry.field(name="analysis", description='Analysis created (for analyzer actions only)', default=None)
    @strawberry.field(name="errorMessage", description='Error message if status is FAILED')
    def error_message(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "error_message", None))
    @strawberry.field(name="errorTraceback", description='Full traceback for debugging (truncated to 10KB)')
    def error_traceback(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "error_traceback", None))
    @strawberry.field(name="executionMetadata")
    def execution_metadata(self, info: strawberry.Info) -> Optional[JSONString]:
        kwargs = strip_unset({})
        return _resolve_CorpusActionExecutionType_execution_metadata(self, info, **kwargs)
    @strawberry.field(name="myPermissions")
    def my_permissions(self, info: strawberry.Info) -> Optional[GenericScalar]:
        return core_permissions.resolve_my_permissions(self, info)
    @strawberry.field(name="isPublished")
    def is_published(self, info: strawberry.Info) -> Optional[bool]:
        return core_permissions.resolve_is_published(self, info)
    @strawberry.field(name="objectSharedWith")
    def object_shared_with(self, info: strawberry.Info) -> Optional[GenericScalar]:
        return core_permissions.resolve_object_shared_with(self, info)
    @strawberry.field(name="durationSeconds")
    def duration_seconds(self, info: strawberry.Info) -> Optional[float]:
        kwargs = strip_unset({})
        return _resolve_CorpusActionExecutionType_duration_seconds(self, info, **kwargs)
    @strawberry.field(name="waitTimeSeconds")
    def wait_time_seconds(self, info: strawberry.Info) -> Optional[float]:
        kwargs = strip_unset({})
        return _resolve_CorpusActionExecutionType_wait_time_seconds(self, info, **kwargs)


register_type("CorpusActionExecutionType", CorpusActionExecutionType, model=CorpusActionExecution)


CorpusActionExecutionTypeConnection = make_connection_types(CorpusActionExecutionType, type_name="CorpusActionExecutionTypeConnection", countable=True, pdf_page_aware=False)


def _resolve_AgentConfigurationType_available_tools(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/agent_types.py:192

    Port of AgentConfigurationType.resolve_available_tools
    """
    raise NotImplementedError("_resolve_AgentConfigurationType_available_tools not yet ported — see manifest")


def _resolve_AgentConfigurationType_permission_required_tools(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/agent_types.py:196

    Port of AgentConfigurationType.resolve_permission_required_tools
    """
    raise NotImplementedError("_resolve_AgentConfigurationType_permission_required_tools not yet ported — see manifest")


def _resolve_AgentConfigurationType_mention_format(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/agent_types.py:186

    Port of AgentConfigurationType.resolve_mention_format
    """
    raise NotImplementedError("_resolve_AgentConfigurationType_mention_format not yet ported — see manifest")


@strawberry.type(name="AgentConfigurationType", description='GraphQL type for agent configurations.')
class AgentConfigurationType(Node):
    is_public: bool = strawberry.field(name="isPublic", default=None)
    creator: Annotated["UserType", strawberry.lazy("config.graphql.user_types")] = strawberry.field(name="creator", default=None)
    created: datetime.datetime = strawberry.field(name="created", default=None)
    modified: datetime.datetime = strawberry.field(name="modified", default=None)
    @strawberry.field(name="name", description='Display name for this agent')
    def name(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "name", None))
    @strawberry.field(name="slug", description="URL-friendly identifier for mentions (e.g., 'research-assistant')")
    def slug(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "slug", None))
    @strawberry.field(name="description", description="Description of agent's purpose and capabilities")
    def description(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "description", None))
    @strawberry.field(name="systemInstructions", description='System prompt/instructions for this agent')
    def system_instructions(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "system_instructions", None))
    @strawberry.field(name="availableTools", description='List of tool identifiers this agent can use')
    def available_tools(self, info: strawberry.Info) -> Optional[list[Optional[str]]]:
        kwargs = strip_unset({})
        return _resolve_AgentConfigurationType_available_tools(self, info, **kwargs)
    @strawberry.field(name="permissionRequiredTools", description='Subset of tools that require explicit user permission to use')
    def permission_required_tools(self, info: strawberry.Info) -> Optional[list[Optional[str]]]:
        kwargs = strip_unset({})
        return _resolve_AgentConfigurationType_permission_required_tools(self, info, **kwargs)
    @strawberry.field(name="preferredLlm", description="Optional pydantic-ai model spec to use when this agent runs (e.g. 'anthropic:claude-haiku-4-5'). Overrides Corpus.preferred_llm. Empty falls back to the corpus default, then settings.")
    def preferred_llm(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "preferred_llm", None))
    badge_config: JSONString = strawberry.field(name="badgeConfig", description="Visual config: {'icon': 'bot', 'color': '#4A90E2', 'label': 'AI Assistant'}", default=None)
    @strawberry.field(name="avatarUrl", description="URL to agent's avatar image")
    def avatar_url(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "avatar_url", None))
    @strawberry.field(name="scope")
    def scope(self, info: strawberry.Info) -> enums.AgentsAgentConfigurationScopeChoices:
        return coerce_enum(enums.AgentsAgentConfigurationScopeChoices, getattr(self, "scope", None))
    corpus: Optional[Annotated["CorpusType", strawberry.lazy("config.graphql.corpus_types")]] = strawberry.field(name="corpus", description='Corpus this agent belongs to (if scope=CORPUS)', default=None)
    is_active: bool = strawberry.field(name="isActive", description='Whether this agent is active and can be used', default=None)
    @strawberry.field(name="myPermissions")
    def my_permissions(self, info: strawberry.Info) -> Optional[GenericScalar]:
        return core_permissions.resolve_my_permissions(self, info)
    @strawberry.field(name="isPublished")
    def is_published(self, info: strawberry.Info) -> Optional[bool]:
        return core_permissions.resolve_is_published(self, info)
    @strawberry.field(name="objectSharedWith")
    def object_shared_with(self, info: strawberry.Info) -> Optional[GenericScalar]:
        return core_permissions.resolve_object_shared_with(self, info)
    @strawberry.field(name="mentionFormat", description="The @ mention format for this agent (e.g., '@agent:research-assistant')")
    def mention_format(self, info: strawberry.Info) -> Optional[str]:
        kwargs = strip_unset({})
        return _resolve_AgentConfigurationType_mention_format(self, info, **kwargs)


register_type("AgentConfigurationType", AgentConfigurationType, model=AgentConfiguration)


AgentConfigurationTypeConnection = make_connection_types(AgentConfigurationType, type_name="AgentConfigurationTypeConnection", countable=True, pdf_page_aware=False)


def _resolve_AgentActionResultType_tools_executed(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/agent_types.py:66

    Port of AgentActionResultType.resolve_tools_executed
    """
    raise NotImplementedError("_resolve_AgentActionResultType_tools_executed not yet ported — see manifest")


def _resolve_AgentActionResultType_execution_metadata(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/agent_types.py:70

    Port of AgentActionResultType.resolve_execution_metadata
    """
    raise NotImplementedError("_resolve_AgentActionResultType_execution_metadata not yet ported — see manifest")


def _resolve_AgentActionResultType_duration_seconds(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/agent_types.py:74

    Port of AgentActionResultType.resolve_duration_seconds
    """
    raise NotImplementedError("_resolve_AgentActionResultType_duration_seconds not yet ported — see manifest")


@strawberry.type(name="AgentActionResultType", description='GraphQL type for AgentActionResult - results from agent-based corpus actions.')
class AgentActionResultType(Node):
    user_lock: Optional[Annotated["UserType", strawberry.lazy("config.graphql.user_types")]] = strawberry.field(name="userLock", default=None)
    backend_lock: bool = strawberry.field(name="backendLock", default=None)
    is_public: bool = strawberry.field(name="isPublic", default=None)
    creator: Annotated["UserType", strawberry.lazy("config.graphql.user_types")] = strawberry.field(name="creator", default=None)
    created: datetime.datetime = strawberry.field(name="created", default=None)
    modified: datetime.datetime = strawberry.field(name="modified", default=None)
    corpus_action: "CorpusActionType" = strawberry.field(name="corpusAction", description='The corpus action that triggered this execution', default=None)
    document: Optional[Annotated["DocumentType", strawberry.lazy("config.graphql.document_types")]] = strawberry.field(name="document", description='The document this action was run on (null for thread-based actions)', default=None)
    conversation: Optional[Annotated["ConversationType", strawberry.lazy("config.graphql.conversation_types")]] = strawberry.field(name="conversation", description='Conversation record containing the full agent interaction', default=None)
    triggering_conversation: Optional[Annotated["ConversationType", strawberry.lazy("config.graphql.conversation_types")]] = strawberry.field(name="triggeringConversation", description='Thread that triggered this agent action (for thread-based triggers)', default=None)
    triggering_message: Optional[Annotated["MessageType", strawberry.lazy("config.graphql.conversation_types")]] = strawberry.field(name="triggeringMessage", description='Message that triggered this agent action (for NEW_MESSAGE trigger)', default=None)
    @strawberry.field(name="status")
    def status(self, info: strawberry.Info) -> enums.AgentsAgentActionResultStatusChoices:
        return coerce_enum(enums.AgentsAgentActionResultStatusChoices, getattr(self, "status", None))
    started_at: Optional[datetime.datetime] = strawberry.field(name="startedAt", default=None)
    completed_at: Optional[datetime.datetime] = strawberry.field(name="completedAt", default=None)
    @strawberry.field(name="agentResponse", description='Final response content from the agent')
    def agent_response(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "agent_response", None))
    @strawberry.field(name="toolsExecuted")
    def tools_executed(self, info: strawberry.Info) -> Optional[list[Optional[JSONString]]]:
        kwargs = strip_unset({})
        return _resolve_AgentActionResultType_tools_executed(self, info, **kwargs)
    @strawberry.field(name="errorMessage", description='Error message if status is FAILED')
    def error_message(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "error_message", None))
    @strawberry.field(name="executionMetadata")
    def execution_metadata(self, info: strawberry.Info) -> Optional[JSONString]:
        kwargs = strip_unset({})
        return _resolve_AgentActionResultType_execution_metadata(self, info, **kwargs)
    @strawberry.field(name="executionRecord", description='Detailed agent result (for agent actions only)')
    def execution_record(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET, id: Annotated[Optional[strawberry.ID], strawberry.argument(name="id")] = strawberry.UNSET, corpus__id: Annotated[Optional[strawberry.ID], strawberry.argument(name="corpus_Id")] = strawberry.UNSET, corpus_action__id: Annotated[Optional[strawberry.ID], strawberry.argument(name="corpusAction_Id")] = strawberry.UNSET, document__id: Annotated[Optional[strawberry.ID], strawberry.argument(name="document_Id")] = strawberry.UNSET, status: Annotated[Optional[enums.CorpusesCorpusActionExecutionStatusChoices], strawberry.argument(name="status")] = strawberry.UNSET, action_type: Annotated[Optional[enums.CorpusesCorpusActionExecutionActionTypeChoices], strawberry.argument(name="actionType")] = strawberry.UNSET, trigger: Annotated[Optional[enums.CorpusesCorpusActionExecutionTriggerChoices], strawberry.argument(name="trigger")] = strawberry.UNSET, creator__id: Annotated[Optional[strawberry.ID], strawberry.argument(name="creator_Id")] = strawberry.UNSET) -> "CorpusActionExecutionTypeConnection":
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last, "id": id, "corpus__id": corpus__id, "corpus_action__id": corpus_action__id, "document__id": document__id, "status": status, "action_type": action_type, "trigger": trigger, "creator__id": creator__id})
        resolved = getattr(self, "execution_record", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="CorpusActionExecutionType", filterset_class=filterset_factory(CorpusActionExecution, fields={'id': ['exact'], 'corpus__id': ['exact'], 'corpus_action__id': ['exact'], 'document__id': ['exact'], 'status': ['exact'], 'action_type': ['exact'], 'trigger': ['exact'], 'creator__id': ['exact']}), filter_args={"id": "id", "corpus__id": "corpus__id", "corpus_action__id": "corpus_action__id", "document__id": "document__id", "status": "status", "action_type": "action_type", "trigger": "trigger", "creator__id": "creator__id"}, )
    @strawberry.field(name="myPermissions")
    def my_permissions(self, info: strawberry.Info) -> Optional[GenericScalar]:
        return core_permissions.resolve_my_permissions(self, info)
    @strawberry.field(name="isPublished")
    def is_published(self, info: strawberry.Info) -> Optional[bool]:
        return core_permissions.resolve_is_published(self, info)
    @strawberry.field(name="objectSharedWith")
    def object_shared_with(self, info: strawberry.Info) -> Optional[GenericScalar]:
        return core_permissions.resolve_object_shared_with(self, info)
    @strawberry.field(name="durationSeconds")
    def duration_seconds(self, info: strawberry.Info) -> Optional[float]:
        kwargs = strip_unset({})
        return _resolve_AgentActionResultType_duration_seconds(self, info, **kwargs)


register_type("AgentActionResultType", AgentActionResultType, model=AgentActionResult)


AgentActionResultTypeConnection = make_connection_types(AgentActionResultType, type_name="AgentActionResultTypeConnection", countable=True, pdf_page_aware=False)


def _resolve_CorpusActionTemplateType_pre_authorized_tools(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/agent_types.py:267

    Port of CorpusActionTemplateType.resolve_pre_authorized_tools
    """
    raise NotImplementedError("_resolve_CorpusActionTemplateType_pre_authorized_tools not yet ported — see manifest")


@strawberry.type(name="CorpusActionTemplateType", description='GraphQL type for CorpusActionTemplate — read-only, system-level.')
class CorpusActionTemplateType(Node):
    created: datetime.datetime = strawberry.field(name="created", default=None)
    @strawberry.field(name="name")
    def name(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "name", None))
    @strawberry.field(name="description")
    def description(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "description", None))
    agent_config: Optional["AgentConfigurationType"] = strawberry.field(name="agentConfig", description='Optional agent configuration for persona/tool defaults.', default=None)
    @strawberry.field(name="preAuthorizedTools")
    def pre_authorized_tools(self, info: strawberry.Info) -> Optional[list[Optional[str]]]:
        kwargs = strip_unset({})
        return _resolve_CorpusActionTemplateType_pre_authorized_tools(self, info, **kwargs)
    @strawberry.field(name="trigger")
    def trigger(self, info: strawberry.Info) -> enums.CorpusesCorpusActionTemplateTriggerChoices:
        return coerce_enum(enums.CorpusesCorpusActionTemplateTriggerChoices, getattr(self, "trigger", None))
    is_active: bool = strawberry.field(name="isActive", description='Whether this template appears in the Action Library for users to add.', default=None)
    disabled_on_clone: bool = strawberry.field(name="disabledOnClone", description='If True, cloned actions start disabled (user must opt-in).', default=None)
    sort_order: int = strawberry.field(name="sortOrder", description='Display ordering in template lists.', default=None)


register_type("CorpusActionTemplateType", CorpusActionTemplateType, model=CorpusActionTemplate)


CorpusActionTemplateTypeConnection = make_connection_types(CorpusActionTemplateType, type_name="CorpusActionTemplateTypeConnection", countable=True, pdf_page_aware=False)


@strawberry.type(name="CorpusActionTrailStatsType", description='Aggregated statistics for corpus action trail.')
class CorpusActionTrailStatsType:
    total_executions: Optional[int] = strawberry.field(name="totalExecutions", default=None)
    completed: Optional[int] = strawberry.field(name="completed", default=None)
    failed: Optional[int] = strawberry.field(name="failed", default=None)
    running: Optional[int] = strawberry.field(name="running", default=None)
    queued: Optional[int] = strawberry.field(name="queued", default=None)
    skipped: Optional[int] = strawberry.field(name="skipped", default=None)
    avg_duration_seconds: Optional[float] = strawberry.field(name="avgDurationSeconds", default=None)
    fieldset_count: Optional[int] = strawberry.field(name="fieldsetCount", default=None)
    analyzer_count: Optional[int] = strawberry.field(name="analyzerCount", default=None)
    agent_count: Optional[int] = strawberry.field(name="agentCount", default=None)


register_type("CorpusActionTrailStatsType", CorpusActionTrailStatsType, model=None)


@strawberry.type(name="AvailableToolType", description='GraphQL type for available tools that can be assigned to agents.\n\nThis provides metadata about each tool, including its description,\ncategory, and requirements.')
class AvailableToolType:
    name: str = strawberry.field(name="name", description='Tool name (used in configuration)', default=None)
    description: str = strawberry.field(name="description", description='Human-readable description of the tool', default=None)
    category: str = strawberry.field(name="category", description='Tool category (search, document, corpus, notes, annotations, coordination)', default=None)
    requiresCorpus: bool = strawberry.field(name="requiresCorpus", description='Whether this tool requires a corpus context', default=None)
    requiresApproval: bool = strawberry.field(name="requiresApproval", description='Whether this tool requires user approval before execution', default=None)
    parameters: list["ToolParameterType"] = strawberry.field(name="parameters", description='List of parameters accepted by this tool', default=None)


register_type("AvailableToolType", AvailableToolType, model=None)


@strawberry.type(name="ToolParameterType", description='GraphQL type for tool parameter definitions.')
class ToolParameterType:
    name: str = strawberry.field(name="name", description='Parameter name', default=None)
    description: str = strawberry.field(name="description", description='Parameter description', default=None)
    required: bool = strawberry.field(name="required", description='Whether the parameter is required', default=None)


register_type("ToolParameterType", ToolParameterType, model=None)

