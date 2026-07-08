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
from opencontractserver.agents.models import AgentConfiguration
from opencontractserver.corpuses.models import Corpus
from opencontractserver.corpuses.models import CorpusAction
from opencontractserver.corpuses.models import CorpusActionExecution
from opencontractserver.corpuses.models import CorpusCategory
from opencontractserver.corpuses.models import CorpusFolder


def _resolve_CorpusType_readme_caml_document(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/corpus_types.py:458

    Port of CorpusType.resolve_readme_caml_document
    """
    raise NotImplementedError("_resolve_CorpusType_readme_caml_document not yet ported — see manifest")


def _resolve_CorpusType_icon(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/corpus_types.py:420

    Port of CorpusType.resolve_icon
    """
    raise NotImplementedError("_resolve_CorpusType_icon not yet ported — see manifest")


def _resolve_CorpusType_categories(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/corpus_types.py:570

    Port of CorpusType.resolve_categories
    """
    raise NotImplementedError("_resolve_CorpusType_categories not yet ported — see manifest")


def _resolve_CorpusType_label_set(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/corpus_types.py:652

    Port of CorpusType.resolve_label_set
    """
    raise NotImplementedError("_resolve_CorpusType_label_set not yet ported — see manifest")


def _resolve_CorpusType_engagement_metrics(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/corpus_types.py:535

    Port of CorpusType.resolve_engagement_metrics
    """
    raise NotImplementedError("_resolve_CorpusType_engagement_metrics not yet ported — see manifest")


def _resolve_CorpusType_folders(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/corpus_types.py:526

    Port of CorpusType.resolve_folders
    """
    raise NotImplementedError("_resolve_CorpusType_folders not yet ported — see manifest")


def _resolve_CorpusType_annotations(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/corpus_types.py:360

    Port of CorpusType.resolve_annotations
    """
    raise NotImplementedError("_resolve_CorpusType_annotations not yet ported — see manifest")


def _resolve_CorpusType_all_annotation_summaries(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/corpus_types.py:386

    Port of CorpusType.resolve_all_annotation_summaries
    """
    raise NotImplementedError("_resolve_CorpusType_all_annotation_summaries not yet ported — see manifest")


def _resolve_CorpusType_documents(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/corpus_types.py:330

    Port of CorpusType.resolve_documents
    """
    raise NotImplementedError("_resolve_CorpusType_documents not yet ported — see manifest")


def _resolve_CorpusType_applied_analyzer_ids(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/corpus_types.py:415

    Port of CorpusType.resolve_applied_analyzer_ids
    """
    raise NotImplementedError("_resolve_CorpusType_applied_analyzer_ids not yet ported — see manifest")


def _resolve_CorpusType_description_revisions(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/corpus_types.py:484

    Port of CorpusType.resolve_description_revisions
    """
    raise NotImplementedError("_resolve_CorpusType_description_revisions not yet ported — see manifest")


def _resolve_CorpusType_memory_active_warning(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/corpus_types.py:557

    Port of CorpusType.resolve_memory_active_warning
    """
    raise NotImplementedError("_resolve_CorpusType_memory_active_warning not yet ported — see manifest")


def _resolve_CorpusType_document_count(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/corpus_types.py:579

    Port of CorpusType.resolve_document_count
    """
    raise NotImplementedError("_resolve_CorpusType_document_count not yet ported — see manifest")


def _resolve_CorpusType_my_vote(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/corpus_types.py:602

    Port of CorpusType.resolve_my_vote
    """
    raise NotImplementedError("_resolve_CorpusType_my_vote not yet ported — see manifest")


def _resolve_CorpusType_annotation_count(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/corpus_types.py:636

    Port of CorpusType.resolve_annotation_count
    """
    raise NotImplementedError("_resolve_CorpusType_annotation_count not yet ported — see manifest")


@strawberry.type(name="CorpusType")
class CorpusType(Node):
    parent: Optional["CorpusType"] = strawberry.field(name="parent", default=None)
    @strawberry.field(name="title")
    def title(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "title", None))
    @strawberry.field(name="description")
    def description(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "description", None))
    @strawberry.field(name="descriptionPreview", description='Auto-generated truncated plain-text preview derived from ``description``. Used by card layouts, list snippets, and hero subtitles so users never see a wall of raw text. Capped at ``MAX_CORPUS_DESCRIPTION_PREVIEW_LENGTH`` characters.')
    def description_preview(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "description_preview", None))
    @strawberry.field(name="readmeCamlDocument", description="The corpus's canonical Readme.CAML Document — the source of truth for the rich description. Use this for revision history, permissions, and direct content access. The mdDescription string field exposes the same body as a file URL.")
    def readme_caml_document(self, info: strawberry.Info) -> Optional[Annotated["DocumentType", strawberry.lazy("config.graphql.document_types")]]:
        kwargs = strip_unset({})
        return _resolve_CorpusType_readme_caml_document(self, info, **kwargs)
    @strawberry.field(name="slug", description='Case-sensitive slug unique per creator. Allowed: A-Z, a-z, 0-9, hyphen (-).')
    def slug(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "slug", None))
    @strawberry.field(name="icon")
    def icon(self, info: strawberry.Info) -> Optional[str]:
        kwargs = strip_unset({})
        return _resolve_CorpusType_icon(self, info, **kwargs)
    auto_branding_enabled: bool = strawberry.field(name="autoBrandingEnabled", description='When True, auto-generate a logo and Readme.CAML article on creation if no icon was uploaded. Set False to opt this corpus out of auto-branding.', default=None)
    @strawberry.field(name="categories")
    def categories(self, info: strawberry.Info) -> Optional[list[Optional["CorpusCategoryType"]]]:
        kwargs = strip_unset({})
        return _resolve_CorpusType_categories(self, info, **kwargs)
    @strawberry.field(name="labelSet")
    def label_set(self, info: strawberry.Info) -> Optional[Annotated["LabelSetType", strawberry.lazy("config.graphql.annotation_types")]]:
        kwargs = strip_unset({})
        return _resolve_CorpusType_label_set(self, info, **kwargs)
    post_processors: JSONString = strawberry.field(name="postProcessors", description='List of fully qualified Python paths to post-processor functions', default=None)
    @strawberry.field(name="preferredEmbedder", description='Fully qualified Python path to the embedder class to use for this corpus. Auto-populated from DEFAULT_EMBEDDER at creation if not set. Immutable after documents are added (use re-embed to change).')
    def preferred_embedder(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "preferred_embedder", None))
    @strawberry.field(name="createdWithEmbedder", description='The embedder that was active when this corpus was created. Set automatically and never changes (audit trail).')
    def created_with_embedder(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "created_with_embedder", None))
    @strawberry.field(name="preferredLlm", description="Preferred pydantic-ai model spec for agents in this corpus (e.g. 'anthropic:claude-opus-4-6'). Overridable per-agent via AgentConfiguration.preferred_llm. Falls back to settings.DEFAULT_LLM / settings.OPENAI_MODEL when unset.")
    def preferred_llm(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "preferred_llm", None))
    @strawberry.field(name="createdWithLlm", description='The LLM model spec that was active when this corpus was created. Set automatically and never changes (audit trail).')
    def created_with_llm(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "created_with_llm", None))
    @strawberry.field(name="corpusAgentInstructions", description='Custom system instructions for the corpus-level agent. If not set, uses DEFAULT_CORPUS_AGENT_INSTRUCTIONS from settings.')
    def corpus_agent_instructions(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "corpus_agent_instructions", None))
    @strawberry.field(name="documentAgentInstructions", description='Custom system instructions for document-level agents in this corpus. If not set, uses DEFAULT_DOCUMENT_AGENT_INSTRUCTIONS from settings.')
    def document_agent_instructions(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "document_agent_instructions", None))
    memory_enabled: bool = strawberry.field(name="memoryEnabled", description='Enable agent memory system for this corpus. When enabled, agents accumulate reusable insights from conversations into a memory document.', default=None)
    memory_document: Optional[Annotated["DocumentType", strawberry.lazy("config.graphql.document_types")]] = strawberry.field(name="memoryDocument", description='The Document storing accumulated agent memory for this corpus.', default=None)
    @strawberry.field(name="license", description='SPDX identifier of the license applied to this corpus.')
    def license(self, info: strawberry.Info) -> Optional[enums.CorpusesCorpusLicenseChoices]:
        return coerce_enum(enums.CorpusesCorpusLicenseChoices, getattr(self, "license", None))
    @strawberry.field(name="licenseLink", description="URL to the full license text. Required when license is 'CUSTOM', optional for standard CC licenses.")
    def license_link(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "license_link", None))
    allow_comments: bool = strawberry.field(name="allowComments", default=None)
    is_public: bool = strawberry.field(name="isPublic", default=None)
    creator: Annotated["UserType", strawberry.lazy("config.graphql.user_types")] = strawberry.field(name="creator", default=None)
    backend_lock: bool = strawberry.field(name="backendLock", default=None)
    user_lock: Optional[Annotated["UserType", strawberry.lazy("config.graphql.user_types")]] = strawberry.field(name="userLock", default=None)
    error: bool = strawberry.field(name="error", default=None)
    is_personal: bool = strawberry.field(name="isPersonal", description="True if this is the user's personal 'My Documents' corpus", default=None)
    upvote_count: int = strawberry.field(name="upvoteCount", description='Cached count of upvotes for this corpus', default=None)
    downvote_count: int = strawberry.field(name="downvoteCount", description='Cached count of downvotes for this corpus', default=None)
    score: int = strawberry.field(name="score", description='upvote_count - downvote_count, denormalized for sorting', default=None)
    created: datetime.datetime = strawberry.field(name="created", default=None)
    modified: datetime.datetime = strawberry.field(name="modified", default=None)
    @strawberry.field(name="assignmentSet")
    def assignment_set(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["AssignmentTypeConnection", strawberry.lazy("config.graphql.user_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "assignment_set", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="AssignmentType", )
    @strawberry.field(name="documentRelationships")
    def document_relationships(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["DocumentRelationshipTypeConnection", strawberry.lazy("config.graphql.document_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "document_relationships", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="DocumentRelationshipType", )
    @strawberry.field(name="documentPaths", description='Corpus owning this path')
    def document_paths(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["DocumentPathTypeConnection", strawberry.lazy("config.graphql.document_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "document_paths", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="DocumentPathType", )
    @strawberry.field(name="documentSummaryRevisions")
    def document_summary_revisions(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["DocumentSummaryRevisionTypeConnection", strawberry.lazy("config.graphql.document_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "document_summary_revisions", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="DocumentSummaryRevisionType", )
    @strawberry.field(name="children")
    def children(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> "CorpusTypeConnection":
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "children", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="CorpusType", )
    @strawberry.field(name="actions")
    def actions(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET, id: Annotated[Optional[strawberry.ID], strawberry.argument(name="id")] = strawberry.UNSET, name: Annotated[Optional[str], strawberry.argument(name="name")] = strawberry.UNSET, name__icontains: Annotated[Optional[str], strawberry.argument(name="name_Icontains")] = strawberry.UNSET, name__istartswith: Annotated[Optional[str], strawberry.argument(name="name_Istartswith")] = strawberry.UNSET, corpus__id: Annotated[Optional[strawberry.ID], strawberry.argument(name="corpus_Id")] = strawberry.UNSET, fieldset__id: Annotated[Optional[strawberry.ID], strawberry.argument(name="fieldset_Id")] = strawberry.UNSET, analyzer__id: Annotated[Optional[strawberry.ID], strawberry.argument(name="analyzer_Id")] = strawberry.UNSET, agent_config__id: Annotated[Optional[strawberry.ID], strawberry.argument(name="agentConfig_Id")] = strawberry.UNSET, trigger: Annotated[Optional[enums.CorpusesCorpusActionTriggerChoices], strawberry.argument(name="trigger")] = strawberry.UNSET, creator__id: Annotated[Optional[strawberry.ID], strawberry.argument(name="creator_Id")] = strawberry.UNSET, source_template__id: Annotated[Optional[strawberry.ID], strawberry.argument(name="sourceTemplate_Id")] = strawberry.UNSET) -> Annotated["CorpusActionTypeConnection", strawberry.lazy("config.graphql.agent_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last, "id": id, "name": name, "name__icontains": name__icontains, "name__istartswith": name__istartswith, "corpus__id": corpus__id, "fieldset__id": fieldset__id, "analyzer__id": analyzer__id, "agent_config__id": agent_config__id, "trigger": trigger, "creator__id": creator__id, "source_template__id": source_template__id})
        resolved = getattr(self, "actions", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="CorpusActionType", filterset_class=filterset_factory(CorpusAction, fields={'id': ['exact'], 'name': ['exact', 'icontains', 'istartswith'], 'corpus__id': ['exact'], 'fieldset__id': ['exact'], 'analyzer__id': ['exact'], 'agent_config__id': ['exact'], 'trigger': ['exact'], 'creator__id': ['exact'], 'source_template__id': ['exact']}), filter_args={"id": "id", "name": "name", "name__icontains": "name__icontains", "name__istartswith": "name__istartswith", "corpus__id": "corpus__id", "fieldset__id": "fieldset__id", "analyzer__id": "analyzer__id", "agent_config__id": "agent_config__id", "trigger": "trigger", "creator__id": "creator__id", "source_template__id": "source_template__id"}, )
    @strawberry.field(name="engagementMetrics")
    def engagement_metrics(self, info: strawberry.Info) -> Optional["CorpusEngagementMetricsType"]:
        kwargs = strip_unset({})
        return _resolve_CorpusType_engagement_metrics(self, info, **kwargs)
    @strawberry.field(name="folders", description='All folders in this corpus (flat list)')
    def folders(self, info: strawberry.Info) -> Optional[list[Optional["CorpusFolderType"]]]:
        kwargs = strip_unset({})
        return _resolve_CorpusType_folders(self, info, **kwargs)
    @strawberry.field(name="actionExecutions", description='Denormalized corpus reference for fast queries')
    def action_executions(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET, id: Annotated[Optional[strawberry.ID], strawberry.argument(name="id")] = strawberry.UNSET, corpus__id: Annotated[Optional[strawberry.ID], strawberry.argument(name="corpus_Id")] = strawberry.UNSET, corpus_action__id: Annotated[Optional[strawberry.ID], strawberry.argument(name="corpusAction_Id")] = strawberry.UNSET, document__id: Annotated[Optional[strawberry.ID], strawberry.argument(name="document_Id")] = strawberry.UNSET, status: Annotated[Optional[enums.CorpusesCorpusActionExecutionStatusChoices], strawberry.argument(name="status")] = strawberry.UNSET, action_type: Annotated[Optional[enums.CorpusesCorpusActionExecutionActionTypeChoices], strawberry.argument(name="actionType")] = strawberry.UNSET, trigger: Annotated[Optional[enums.CorpusesCorpusActionExecutionTriggerChoices], strawberry.argument(name="trigger")] = strawberry.UNSET, creator__id: Annotated[Optional[strawberry.ID], strawberry.argument(name="creator_Id")] = strawberry.UNSET) -> Annotated["CorpusActionExecutionTypeConnection", strawberry.lazy("config.graphql.agent_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last, "id": id, "corpus__id": corpus__id, "corpus_action__id": corpus_action__id, "document__id": document__id, "status": status, "action_type": action_type, "trigger": trigger, "creator__id": creator__id})
        resolved = getattr(self, "action_executions", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="CorpusActionExecutionType", filterset_class=filterset_factory(CorpusActionExecution, fields={'id': ['exact'], 'corpus__id': ['exact'], 'corpus_action__id': ['exact'], 'document__id': ['exact'], 'status': ['exact'], 'action_type': ['exact'], 'trigger': ['exact'], 'creator__id': ['exact']}), filter_args={"id": "id", "corpus__id": "corpus__id", "corpus_action__id": "corpus_action__id", "document__id": "document__id", "status": "status", "action_type": "action_type", "trigger": "trigger", "creator__id": "creator__id"}, )
    @strawberry.field(name="relationships")
    def relationships(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["RelationshipTypeConnection", strawberry.lazy("config.graphql.annotation_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "relationships", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="RelationshipType", )
    @strawberry.field(name="annotations")
    def annotations(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET, raw_text__contains: Annotated[Optional[str], strawberry.argument(name="rawText_Contains")] = strawberry.UNSET, annotation_label_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="annotationLabelId")] = strawberry.UNSET, annotation_label__text: Annotated[Optional[str], strawberry.argument(name="annotationLabel_Text")] = strawberry.UNSET, annotation_label__text__contains: Annotated[Optional[str], strawberry.argument(name="annotationLabel_Text_Contains")] = strawberry.UNSET, annotation_label__description__contains: Annotated[Optional[str], strawberry.argument(name="annotationLabel_Description_Contains")] = strawberry.UNSET, annotation_label__label_type: Annotated[Optional[enums.AnnotationsAnnotationLabelLabelTypeChoices], strawberry.argument(name="annotationLabel_LabelType")] = strawberry.UNSET, analysis__isnull: Annotated[Optional[bool], strawberry.argument(name="analysis_Isnull")] = strawberry.UNSET, document_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="documentId")] = strawberry.UNSET, corpus_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="corpusId")] = strawberry.UNSET, structural: Annotated[Optional[bool], strawberry.argument(name="structural")] = strawberry.UNSET, uses_label_from_labelset_id: Annotated[Optional[str], strawberry.argument(name="usesLabelFromLabelsetId")] = strawberry.UNSET, created_by_analysis_ids: Annotated[Optional[str], strawberry.argument(name="createdByAnalysisIds")] = strawberry.UNSET, created_with_analyzer_id: Annotated[Optional[str], strawberry.argument(name="createdWithAnalyzerId")] = strawberry.UNSET, order_by: Annotated[Optional[str], strawberry.argument(name="orderBy", description='Ordering')] = strawberry.UNSET) -> Annotated["AnnotationTypeConnection", strawberry.lazy("config.graphql.annotation_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last, "raw_text__contains": raw_text__contains, "annotation_label_id": annotation_label_id, "annotation_label__text": annotation_label__text, "annotation_label__text__contains": annotation_label__text__contains, "annotation_label__description__contains": annotation_label__description__contains, "annotation_label__label_type": annotation_label__label_type, "analysis__isnull": analysis__isnull, "document_id": document_id, "corpus_id": corpus_id, "structural": structural, "uses_label_from_labelset_id": uses_label_from_labelset_id, "created_by_analysis_ids": created_by_analysis_ids, "created_with_analyzer_id": created_with_analyzer_id, "order_by": order_by})
        resolved = _resolve_CorpusType_annotations(self, info, **kwargs)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="AnnotationType", filterset_class=setup_filterset(AnnotationFilter), filter_args={"raw_text__contains": "raw_text__contains", "annotation_label_id": "annotation_label_id", "annotation_label__text": "annotation_label__text", "annotation_label__text__contains": "annotation_label__text__contains", "annotation_label__description__contains": "annotation_label__description__contains", "annotation_label__label_type": "annotation_label__label_type", "analysis__isnull": "analysis__isnull", "document_id": "document_id", "corpus_id": "corpus_id", "structural": "structural", "uses_label_from_labelset_id": "uses_label_from_labelset_id", "created_by_analysis_ids": "created_by_analysis_ids", "created_with_analyzer_id": "created_with_analyzer_id", "order_by": "order_by"}, )
    @strawberry.field(name="notes")
    def notes(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["NoteTypeConnection", strawberry.lazy("config.graphql.annotation_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "notes", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="NoteType", )
    @strawberry.field(name="references")
    def references(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["CorpusReferenceTypeConnection", strawberry.lazy("config.graphql.annotation_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "references", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="CorpusReferenceType", )
    @strawberry.field(name="inboundReferences")
    def inbound_references(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["CorpusReferenceTypeConnection", strawberry.lazy("config.graphql.annotation_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "inbound_references", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="CorpusReferenceType", )
    @strawberry.field(name="authorityNamespaces")
    def authority_namespaces(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["AuthorityNamespaceNodeConnection", strawberry.lazy("config.graphql.annotation_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "authority_namespaces", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="AuthorityNamespaceNode", )
    @strawberry.field(name="analyses")
    def analyses(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["AnalysisTypeConnection", strawberry.lazy("config.graphql.extract_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "analyses", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="AnalysisType", )
    metadata_schema: Optional[Annotated["FieldsetType", strawberry.lazy("config.graphql.extract_types")]] = strawberry.field(name="metadataSchema", default=None)
    @strawberry.field(name="extracts")
    def extracts(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["ExtractTypeConnection", strawberry.lazy("config.graphql.extract_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "extracts", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="ExtractType", )
    @strawberry.field(name="conversations", description='The corpus to which this conversation belongs')
    def conversations(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["ConversationTypeConnection", strawberry.lazy("config.graphql.conversation_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "conversations", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="ConversationType", )
    @strawberry.field(name="badges", description='If badge_type is CORPUS, the corpus this badge belongs to')
    def badges(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["BadgeTypeConnection", strawberry.lazy("config.graphql.social_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "badges", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="BadgeType", )
    @strawberry.field(name="userBadges", description='For corpus-specific badges, the context in which it was awarded')
    def user_badges(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["UserBadgeTypeConnection", strawberry.lazy("config.graphql.social_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "user_badges", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="UserBadgeType", )
    @strawberry.field(name="agents", description='Corpus this agent belongs to (if scope=CORPUS)')
    def agents(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET, scope: Annotated[Optional[enums.AgentsAgentConfigurationScopeChoices], strawberry.argument(name="scope")] = strawberry.UNSET, is_active: Annotated[Optional[bool], strawberry.argument(name="isActive")] = strawberry.UNSET, corpus: Annotated[Optional[strawberry.ID], strawberry.argument(name="corpus")] = strawberry.UNSET) -> Annotated["AgentConfigurationTypeConnection", strawberry.lazy("config.graphql.agent_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last, "scope": scope, "is_active": is_active, "corpus": corpus})
        resolved = getattr(self, "agents", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="AgentConfigurationType", filterset_class=filterset_factory(AgentConfiguration, fields={'scope': ['exact'], 'is_active': ['exact'], 'corpus': ['exact']}), filter_args={"scope": "scope", "is_active": "is_active", "corpus": "corpus"}, )
    @strawberry.field(name="researchReports")
    def research_reports(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["ResearchReportTypeConnection", strawberry.lazy("config.graphql.research_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "research_reports", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="ResearchReportType", )
    @strawberry.field(name="myPermissions")
    def my_permissions(self, info: strawberry.Info) -> Optional[GenericScalar]:
        return core_permissions.resolve_my_permissions(self, info)
    @strawberry.field(name="isPublished")
    def is_published(self, info: strawberry.Info) -> Optional[bool]:
        return core_permissions.resolve_is_published(self, info)
    @strawberry.field(name="objectSharedWith")
    def object_shared_with(self, info: strawberry.Info) -> Optional[GenericScalar]:
        return core_permissions.resolve_object_shared_with(self, info)
    @strawberry.field(name="allAnnotationSummaries")
    def all_annotation_summaries(self, info: strawberry.Info, analysis_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="analysisId")] = strawberry.UNSET, label_types: Annotated[Optional[list[Optional[enums.LabelTypeEnum]]], strawberry.argument(name="labelTypes")] = strawberry.UNSET) -> Optional[list[Optional[Annotated["AnnotationType", strawberry.lazy("config.graphql.annotation_types")]]]]:
        kwargs = strip_unset({"analysis_id": analysis_id, "label_types": label_types})
        return _resolve_CorpusType_all_annotation_summaries(self, info, **kwargs)
    @strawberry.field(name="documents", description='Documents in this corpus via DocumentPath')
    def documents(self, info: strawberry.Info, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Optional[Annotated["DocumentTypeConnection", strawberry.lazy("config.graphql.document_types")]]:
        kwargs = strip_unset({"before": before, "after": after, "first": first, "last": last})
        resolved = _resolve_CorpusType_documents(self, info, **kwargs)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="DocumentType", )
    @strawberry.field(name="appliedAnalyzerIds")
    def applied_analyzer_ids(self, info: strawberry.Info) -> Optional[list[Optional[str]]]:
        kwargs = strip_unset({})
        return _resolve_CorpusType_applied_analyzer_ids(self, info, **kwargs)
    @strawberry.field(name="descriptionRevisions", description="Revision history for the corpus description. After the canonical-CAML refactor each entry is a sibling Document on the corpus's Readme.CAML version_tree, newest first. The field shape preserves the legacy CorpusDescriptionRevision API so the frontend revision-history viewer renders without changes.")
    def description_revisions(self, info: strawberry.Info) -> Optional[list[Optional["CorpusDescriptionRevisionType"]]]:
        kwargs = strip_unset({})
        return _resolve_CorpusType_description_revisions(self, info, **kwargs)
    @strawberry.field(name="memoryActiveWarning", description='When memory is enabled, returns a privacy notice explaining that conversation patterns may be stored. Null when disabled.')
    def memory_active_warning(self, info: strawberry.Info) -> Optional[str]:
        kwargs = strip_unset({})
        return _resolve_CorpusType_memory_active_warning(self, info, **kwargs)
    @strawberry.field(name="documentCount", description='Count of active documents in this corpus (optimized)')
    def document_count(self, info: strawberry.Info) -> Optional[int]:
        kwargs = strip_unset({})
        return _resolve_CorpusType_document_count(self, info, **kwargs)
    @strawberry.field(name="myVote", description="Current viewer's vote on this corpus: 'UPVOTE', 'DOWNVOTE', or null. Resolved against the authenticated user when present, otherwise against the Django session id for guest voters.")
    def my_vote(self, info: strawberry.Info) -> Optional[str]:
        kwargs = strip_unset({})
        return _resolve_CorpusType_my_vote(self, info, **kwargs)
    @strawberry.field(name="annotationCount", description='Count of annotations in this corpus (optimized)')
    def annotation_count(self, info: strawberry.Info) -> Optional[int]:
        kwargs = strip_unset({})
        return _resolve_CorpusType_annotation_count(self, info, **kwargs)


def _get_queryset_CorpusType(queryset, info):
    """PORT: config.graphql.corpus_types.CorpusType.get_queryset

    Port of CorpusType.get_queryset
    """
    raise NotImplementedError("_get_queryset_CorpusType not yet ported — see manifest")


def _get_node_CorpusType(info, pk):
    """PORT: config.graphql.corpus_types.CorpusType.get_node

    Port of CorpusType.get_node
    """
    raise NotImplementedError("_get_node_CorpusType not yet ported — see manifest")


register_type("CorpusType", CorpusType, model=Corpus, get_queryset=_get_queryset_CorpusType, get_node=_get_node_CorpusType)


CorpusTypeConnection = make_connection_types(CorpusType, type_name="CorpusTypeConnection", countable=True, pdf_page_aware=False)


def _resolve_CorpusCategoryType_corpus_count(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/corpus_types.py:72

    Port of CorpusCategoryType.resolve_corpus_count
    """
    raise NotImplementedError("_resolve_CorpusCategoryType_corpus_count not yet ported — see manifest")


@strawberry.type(name="CorpusCategoryType", description='GraphQL type for corpus categories.\n\nNOTE: This type does NOT use AnnotatePermissionsForReadMixin because\ncorpus categories are admin-provisioned structural data that is globally\nvisible to all users and do not have per-user permissions.\n\nCategories are managed by superusers either via Django Admin or at\nruntime through the create/update/deleteCorpusCategory GraphQL mutations\n(see config/graphql/corpus_category_mutations.py) and the in-app\n"Corpus Categories" admin panel.\n\nSee docs/permissioning/consolidated_permissioning_guide.md for details.')
class CorpusCategoryType(Node):
    is_public: bool = strawberry.field(name="isPublic", default=None)
    creator: Annotated["UserType", strawberry.lazy("config.graphql.user_types")] = strawberry.field(name="creator", default=None)
    created: datetime.datetime = strawberry.field(name="created", default=None)
    modified: datetime.datetime = strawberry.field(name="modified", default=None)
    @strawberry.field(name="name")
    def name(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "name", None))
    @strawberry.field(name="description")
    def description(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "description", None))
    @strawberry.field(name="icon", description="Lucide icon name (e.g., 'scroll', 'file-text', 'building-2')")
    def icon(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "icon", None))
    @strawberry.field(name="color", description='Hex color code for the category badge')
    def color(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "color", None))
    sort_order: int = strawberry.field(name="sortOrder", description='Order in which categories appear in UI', default=None)
    @strawberry.field(name="corpusCount", description='Number of corpuses in this category')
    def corpus_count(self, info: strawberry.Info) -> Optional[int]:
        kwargs = strip_unset({})
        return _resolve_CorpusCategoryType_corpus_count(self, info, **kwargs)


register_type("CorpusCategoryType", CorpusCategoryType, model=CorpusCategory)


CorpusCategoryTypeConnection = make_connection_types(CorpusCategoryType, type_name="CorpusCategoryTypeConnection", countable=True, pdf_page_aware=False)


def _resolve_CorpusFolderType_parent(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/corpus_types.py:205

    Port of CorpusFolderType.resolve_parent
    """
    raise NotImplementedError("_resolve_CorpusFolderType_parent not yet ported — see manifest")


def _resolve_CorpusFolderType_children(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/corpus_types.py:199

    Port of CorpusFolderType.resolve_children
    """
    raise NotImplementedError("_resolve_CorpusFolderType_children not yet ported — see manifest")


def _resolve_CorpusFolderType_my_permissions(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/corpus_types.py:238

    Port of CorpusFolderType.resolve_my_permissions
    """
    raise NotImplementedError("_resolve_CorpusFolderType_my_permissions not yet ported — see manifest")


def _resolve_CorpusFolderType_is_published(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/corpus_types.py:290

    Port of CorpusFolderType.resolve_is_published
    """
    raise NotImplementedError("_resolve_CorpusFolderType_is_published not yet ported — see manifest")


def _resolve_CorpusFolderType_path(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/corpus_types.py:162

    Port of CorpusFolderType.resolve_path
    """
    raise NotImplementedError("_resolve_CorpusFolderType_path not yet ported — see manifest")


def _resolve_CorpusFolderType_document_count(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/corpus_types.py:175

    Port of CorpusFolderType.resolve_document_count
    """
    raise NotImplementedError("_resolve_CorpusFolderType_document_count not yet ported — see manifest")


def _resolve_CorpusFolderType_descendant_document_count(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/corpus_types.py:187

    Port of CorpusFolderType.resolve_descendant_document_count
    """
    raise NotImplementedError("_resolve_CorpusFolderType_descendant_document_count not yet ported — see manifest")


@strawberry.type(name="CorpusFolderType", description='GraphQL type for corpus folders.\nFolders inherit permissions from their parent corpus.')
class CorpusFolderType(Node):
    @strawberry.field(name="parent")
    def parent(self, info: strawberry.Info) -> Optional["CorpusFolderType"]:
        kwargs = strip_unset({})
        return _resolve_CorpusFolderType_parent(self, info, **kwargs)
    @strawberry.field(name="name", description='Folder name (not full path)')
    def name(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "name", None))
    corpus: "CorpusType" = strawberry.field(name="corpus", description='Parent corpus this folder belongs to', default=None)
    @strawberry.field(name="description")
    def description(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "description", None))
    @strawberry.field(name="color", description='Hex color for UI display')
    def color(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "color", None))
    @strawberry.field(name="icon", description='Icon identifier for UI')
    def icon(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "icon", None))
    tags: JSONString = strawberry.field(name="tags", description='List of tags for categorization', default=None)
    is_public: bool = strawberry.field(name="isPublic", default=None)
    created: datetime.datetime = strawberry.field(name="created", default=None)
    modified: datetime.datetime = strawberry.field(name="modified", default=None)
    creator: Annotated["UserType", strawberry.lazy("config.graphql.user_types")] = strawberry.field(name="creator", default=None)
    @strawberry.field(name="documentPaths", description='Current folder (null if folder deleted or at root)')
    def document_paths(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["DocumentPathTypeConnection", strawberry.lazy("config.graphql.document_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "document_paths", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="DocumentPathType", )
    @strawberry.field(name="children", description='Immediate child folders')
    def children(self, info: strawberry.Info) -> Optional[list[Optional["CorpusFolderType"]]]:
        kwargs = strip_unset({})
        return _resolve_CorpusFolderType_children(self, info, **kwargs)
    @strawberry.field(name="myPermissions")
    def my_permissions(self, info: strawberry.Info) -> Optional[GenericScalar]:
        kwargs = strip_unset({})
        return _resolve_CorpusFolderType_my_permissions(self, info, **kwargs)
    @strawberry.field(name="isPublished")
    def is_published(self, info: strawberry.Info) -> Optional[bool]:
        kwargs = strip_unset({})
        return _resolve_CorpusFolderType_is_published(self, info, **kwargs)
    @strawberry.field(name="objectSharedWith")
    def object_shared_with(self, info: strawberry.Info) -> Optional[GenericScalar]:
        return core_permissions.resolve_object_shared_with(self, info)
    @strawberry.field(name="path", description='Full path from root to this folder')
    def path(self, info: strawberry.Info) -> Optional[str]:
        kwargs = strip_unset({})
        return _resolve_CorpusFolderType_path(self, info, **kwargs)
    @strawberry.field(name="documentCount", description='Number of documents directly in this folder')
    def document_count(self, info: strawberry.Info) -> Optional[int]:
        kwargs = strip_unset({})
        return _resolve_CorpusFolderType_document_count(self, info, **kwargs)
    @strawberry.field(name="descendantDocumentCount", description='Number of documents in this folder and all subfolders')
    def descendant_document_count(self, info: strawberry.Info) -> Optional[int]:
        kwargs = strip_unset({})
        return _resolve_CorpusFolderType_descendant_document_count(self, info, **kwargs)


def _get_queryset_CorpusFolderType(queryset, info):
    """PORT: config.graphql.corpus_types.CorpusFolderType.get_queryset

    Port of CorpusFolderType.get_queryset
    """
    raise NotImplementedError("_get_queryset_CorpusFolderType not yet ported — see manifest")


register_type("CorpusFolderType", CorpusFolderType, model=CorpusFolder, get_queryset=_get_queryset_CorpusFolderType)


CorpusFolderTypeConnection = make_connection_types(CorpusFolderType, type_name="CorpusFolderTypeConnection", countable=True, pdf_page_aware=False)


@strawberry.type(name="CorpusEngagementMetricsType", description='GraphQL type for corpus engagement metrics.\n\nThis type does NOT use AnnotatePermissionsForReadMixin because\nengagement metrics are read-only and permissions are checked on\nthe parent Corpus object.\n\nEpic: #565 - Corpus Engagement Metrics & Analytics\nIssue: #568 - Create GraphQL queries for engagement metrics and leaderboards')
class CorpusEngagementMetricsType:
    total_threads: Optional[int] = strawberry.field(name="totalThreads", description='Total number of discussion threads in this corpus', default=None)
    active_threads: Optional[int] = strawberry.field(name="activeThreads", description='Number of active (not locked/deleted) threads', default=None)
    total_messages: Optional[int] = strawberry.field(name="totalMessages", description='Total number of messages across all threads', default=None)
    messages_last_7_days: Optional[int] = strawberry.field(name="messagesLast7Days", description='Number of messages posted in the last 7 days', default=None)
    messages_last_30_days: Optional[int] = strawberry.field(name="messagesLast30Days", description='Number of messages posted in the last 30 days', default=None)
    unique_contributors: Optional[int] = strawberry.field(name="uniqueContributors", description='Total number of unique users who have posted messages', default=None)
    active_contributors_30_days: Optional[int] = strawberry.field(name="activeContributors30Days", description='Number of users who posted in the last 30 days', default=None)
    total_upvotes: Optional[int] = strawberry.field(name="totalUpvotes", description='Total upvotes across all messages in this corpus', default=None)
    avg_messages_per_thread: Optional[float] = strawberry.field(name="avgMessagesPerThread", description='Average number of messages per thread', default=None)
    last_updated: Optional[datetime.datetime] = strawberry.field(name="lastUpdated", description='Timestamp when metrics were last calculated', default=None)


register_type("CorpusEngagementMetricsType", CorpusEngagementMetricsType, model=None)


def _resolve_CorpusDescriptionRevisionType_id(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/corpus_types.py:917

    Port of CorpusDescriptionRevisionType.resolve_id
    """
    raise NotImplementedError("_resolve_CorpusDescriptionRevisionType_id not yet ported — see manifest")


def _resolve_CorpusDescriptionRevisionType_version(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/corpus_types.py:921

    Port of CorpusDescriptionRevisionType.resolve_version
    """
    raise NotImplementedError("_resolve_CorpusDescriptionRevisionType_version not yet ported — see manifest")


def _resolve_CorpusDescriptionRevisionType_author(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/corpus_types.py:955

    Port of CorpusDescriptionRevisionType.resolve_author
    """
    raise NotImplementedError("_resolve_CorpusDescriptionRevisionType_author not yet ported — see manifest")


def _resolve_CorpusDescriptionRevisionType_snapshot(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/corpus_types.py:959

    Port of CorpusDescriptionRevisionType.resolve_snapshot
    """
    raise NotImplementedError("_resolve_CorpusDescriptionRevisionType_snapshot not yet ported — see manifest")


def _resolve_CorpusDescriptionRevisionType_created(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/corpus_types.py:987

    Port of CorpusDescriptionRevisionType.resolve_created
    """
    raise NotImplementedError("_resolve_CorpusDescriptionRevisionType_created not yet ported — see manifest")


@strawberry.type(name="CorpusDescriptionRevisionType", description="Backwards-compatible facade over a Readme.CAML version-tree sibling.\n\nThe legacy ``CorpusDescriptionRevision`` model was dropped in\nmigration 0055. The GraphQL shape is preserved by mapping each\nDocument sibling's metadata onto the historical fields, so the\nfrontend revision-history viewer renders without changes. The\ninstance bound to each resolver is a\n``opencontractserver.documents.models.Document`` row (a Readme.CAML\nversion-tree sibling), NOT a ``CorpusDescriptionRevision``.\n\nThe legacy ``diff`` field is dropped: clients that need a unified\ndiff compute it on the fly from successive ``snapshot`` values via\n``difflib`` rather than reading a pre-stored payload. Queries that\nstill reference ``diff`` will fail GraphQL validation — remove it\nfrom the frontend query to eliminate the field entirely.\n\nSpec: ``docs/superpowers/specs/2026-05-27-canonical-caml-description-refactor-design.md`` §4.5")
class CorpusDescriptionRevisionType:
    @strawberry.field(name="id")
    def id(self, info: strawberry.Info) -> strawberry.ID:
        kwargs = strip_unset({})
        return _resolve_CorpusDescriptionRevisionType_id(self, info, **kwargs)
    @strawberry.field(name="version")
    def version(self, info: strawberry.Info) -> Optional[int]:
        kwargs = strip_unset({})
        return _resolve_CorpusDescriptionRevisionType_version(self, info, **kwargs)
    @strawberry.field(name="author")
    def author(self, info: strawberry.Info) -> Optional[Annotated["UserType", strawberry.lazy("config.graphql.user_types")]]:
        kwargs = strip_unset({})
        return _resolve_CorpusDescriptionRevisionType_author(self, info, **kwargs)
    @strawberry.field(name="snapshot")
    def snapshot(self, info: strawberry.Info) -> Optional[str]:
        kwargs = strip_unset({})
        return _resolve_CorpusDescriptionRevisionType_snapshot(self, info, **kwargs)
    @strawberry.field(name="created")
    def created(self, info: strawberry.Info) -> Optional[datetime.datetime]:
        kwargs = strip_unset({})
        return _resolve_CorpusDescriptionRevisionType_created(self, info, **kwargs)


register_type("CorpusDescriptionRevisionType", CorpusDescriptionRevisionType, model=None)


@strawberry.type(name="CorpusFilterCountsType", description='Counts of corpuses visible to the user, broken down by tab filter.\n\nEach count respects guardian permissions (matches BaseService.filter_visible(Corpus, user))\nso tab badges in the corpus list view stay accurate without paginating every\npage on the client.')
class CorpusFilterCountsType:
    all: int = strawberry.field(name="all", default=None)
    mine: int = strawberry.field(name="mine", default=None)
    shared: int = strawberry.field(name="shared", default=None)
    public: int = strawberry.field(name="public", default=None)


register_type("CorpusFilterCountsType", CorpusFilterCountsType, model=None)


@strawberry.type(name="CorpusIntelligenceSetupStatusType", description='Which intelligence-bundle pieces a corpus already has installed.')
class CorpusIntelligenceSetupStatusType:
    reference_available: bool = strawberry.field(name="referenceAvailable", description='The reference-enrichment analyzer is registered on this deployment.', default=None)
    reference_action_installed: bool = strawberry.field(name="referenceActionInstalled", default=None)
    installed_template_names: list[str] = strawberry.field(name="installedTemplateNames", default=None)
    missing_template_names: list[str] = strawberry.field(name="missingTemplateNames", default=None)
    is_fully_set_up: bool = strawberry.field(name="isFullySetUp", description='Every deployment-installable bundle piece is installed (unavailable pieces — unregistered analyzer, inactive template — are excluded).', default=None)
    can_setup: bool = strawberry.field(name="canSetup", description="The requesting user holds the permission setupCorpusIntelligence requires (CRUD) — drives the setup CTA's visibility.", default=None)


register_type("CorpusIntelligenceSetupStatusType", CorpusIntelligenceSetupStatusType, model=None)


@strawberry.type(name="CorpusStatsType")
class CorpusStatsType:
    total_docs: Optional[int] = strawberry.field(name="totalDocs", default=None)
    total_annotations: Optional[int] = strawberry.field(name="totalAnnotations", default=None)
    total_comments: Optional[int] = strawberry.field(name="totalComments", default=None)
    total_analyses: Optional[int] = strawberry.field(name="totalAnalyses", default=None)
    total_extracts: Optional[int] = strawberry.field(name="totalExtracts", default=None)
    total_threads: Optional[int] = strawberry.field(name="totalThreads", default=None)
    total_chats: Optional[int] = strawberry.field(name="totalChats", default=None)
    total_relationships: Optional[int] = strawberry.field(name="totalRelationships", default=None)


register_type("CorpusStatsType", CorpusStatsType, model=None)


@strawberry.type(name="CorpusDocumentGraphType", description='The corpus document-relationship graph (node-link form).\n\nBuilt entirely from permission-filtered ``DocumentRelationship`` rows via\n``DocumentRelationshipService`` — documents that participate in at least\none visible relationship, ranked by degree and capped for the glimpse.')
class CorpusDocumentGraphType:
    nodes: list["CorpusDocumentGraphNodeType"] = strawberry.field(name="nodes", default=None)
    edges: list["CorpusDocumentGraphEdgeType"] = strawberry.field(name="edges", default=None)
    total_node_count: int = strawberry.field(name="totalNodeCount", description='Distinct documents participating in any visible relationship.', default=None)
    total_edge_count: int = strawberry.field(name="totalEdgeCount", description='Total visible relationships in the corpus.', default=None)
    truncated: bool = strawberry.field(name="truncated", description='True when nodes/edges were dropped to honor the limit.', default=None)


register_type("CorpusDocumentGraphType", CorpusDocumentGraphType, model=None)


@strawberry.type(name="CorpusDocumentGraphNodeType", description='A single document node in the corpus document-relationship graph.\n\nPowers the ``DocumentGraphGlimpse`` on the Corpus Intelligence home — a\nnode is a document, sized by ``degree`` (its visible relationship count).')
class CorpusDocumentGraphNodeType:
    id: strawberry.ID = strawberry.field(name="id", description='Global DocumentType id (navigable).', default=None)
    title: Optional[str] = strawberry.field(name="title", default=None)
    file_type: Optional[str] = strawberry.field(name="fileType", default=None)
    degree: int = strawberry.field(name="degree", description='Number of visible relationships touching this document.', default=None)


register_type("CorpusDocumentGraphNodeType", CorpusDocumentGraphNodeType, model=None)


@strawberry.type(name="CorpusDocumentGraphEdgeType", description='A labeled directed edge between two document nodes.')
class CorpusDocumentGraphEdgeType:
    id: strawberry.ID = strawberry.field(name="id", default=None)
    source: strawberry.ID = strawberry.field(name="source", description='Global id of the source document.', default=None)
    target: strawberry.ID = strawberry.field(name="target", description='Global id of the target document.', default=None)
    label: Optional[str] = strawberry.field(name="label", description='Relationship label text (null for NOTES).', default=None)
    relationship_type: Optional[str] = strawberry.field(name="relationshipType", default=None)


register_type("CorpusDocumentGraphEdgeType", CorpusDocumentGraphEdgeType, model=None)


@strawberry.type(name="CorpusIntelligenceAggregatesType", description='At-a-glance corpus intelligence framed as insight, not raw counts.\n\nFeeds the ``IntelligencePanel`` on the Corpus Intelligence home. Counts\nrespect the permission model (visible documents only).')
class CorpusIntelligenceAggregatesType:
    label_distribution: list["LabelDistributionEntryType"] = strawberry.field(name="labelDistribution", description='Top annotation labels by frequency across visible documents.', default=None)
    documents_with_summary: int = strawberry.field(name="documentsWithSummary", description='Visible documents that have a markdown summary.', default=None)
    total_documents: int = strawberry.field(name="totalDocuments", description='Visible documents with an active path in the corpus.', default=None)


register_type("CorpusIntelligenceAggregatesType", CorpusIntelligenceAggregatesType, model=None)


@strawberry.type(name="LabelDistributionEntryType", description="One label and how often it appears across the corpus's visible annotations.")
class LabelDistributionEntryType:
    label: str = strawberry.field(name="label", default=None)
    color: Optional[str] = strawberry.field(name="color", default=None)
    count: int = strawberry.field(name="count", default=None)


register_type("LabelDistributionEntryType", LabelDistributionEntryType, model=None)


@strawberry.type(name="CorpusDataStoryType", description='Per-document structured profiles for the corpus-home data story.\n\nThe frontend aggregates these rows into composition / timeline / value views.\nBuilt corpus-as-gate from the default ``Collection Profile`` extract (the\nsource corpus must be READ-visible); ``null`` when no profile extract exists\nyet, so the embed self-hides until the extraction has run.')
class CorpusDataStoryType:
    total_documents: int = strawberry.field(name="totalDocuments", default=None)
    profiles: list["CorpusDataStoryProfileType"] = strawberry.field(name="profiles", default=None)


register_type("CorpusDataStoryType", CorpusDataStoryType, model=None)


@strawberry.type(name="CorpusDataStoryProfileType", description="One document's normalised structured profile for the corpus data story.\n\nValues are cleaned server-side (markdown stripped, dates parsed to ISO out of\nLLM prose, value coerced to a positive float) so the frontend only renders.")
class CorpusDataStoryProfileType:
    document_id: strawberry.ID = strawberry.field(name="documentId", default=None)
    title: str = strawberry.field(name="title", default=None)
    slug: Optional[str] = strawberry.field(name="slug", default=None)
    type: Optional[str] = strawberry.field(name="type", description='Short document/agreement category.', default=None)
    party: Optional[str] = strawberry.field(name="party", description='Primary counterparty / organisation.', default=None)
    effective_date: Optional[str] = strawberry.field(name="effectiveDate", description='Effective date, ISO YYYY-MM-DD.', default=None)
    value: Optional[float] = strawberry.field(name="value", description='Primary dollar value, positive or null.', default=None)


register_type("CorpusDataStoryProfileType", CorpusDataStoryProfileType, model=None)


@strawberry.type(name="ArtifactType", description='A shareable, data-driven corpus poster (an :class:`Artifact`).\n\nBuilt corpus-as-gate by ``ArtifactService`` — exposed only when the source\ncorpus is READ-visible to the caller. Carries the template id + configurable\ncaptions the public ``/a/<slug>`` poster route renders from live corpus data.')
class ArtifactType:
    id: strawberry.ID = strawberry.field(name="id", default=None)
    slug: str = strawberry.field(name="slug", default=None)
    template: str = strawberry.field(name="template", default=None)
    title: Optional[str] = strawberry.field(name="title", default=None)
    subtitle: Optional[str] = strawberry.field(name="subtitle", default=None)
    byline: Optional[str] = strawberry.field(name="byline", default=None)
    config: Optional[GenericScalar] = strawberry.field(name="config", default=None)
    corpus_id: strawberry.ID = strawberry.field(name="corpusId", default=None)
    corpus_slug: Optional[str] = strawberry.field(name="corpusSlug", default=None)
    creator_slug: Optional[str] = strawberry.field(name="creatorSlug", default=None)
    image_url: Optional[str] = strawberry.field(name="imageUrl", default=None)
    created: Optional[datetime.datetime] = strawberry.field(name="created", default=None)


register_type("ArtifactType", ArtifactType, model=None)


@strawberry.type(name="ArtifactTemplateType", description='A template the artifact gallery can offer a corpus, with data-gated\neligibility (a corpus only sees templates its own data can fill).')
class ArtifactTemplateType:
    id: str = strawberry.field(name="id", default=None)
    label: str = strawberry.field(name="label", default=None)
    description: Optional[str] = strawberry.field(name="description", default=None)
    eligible: bool = strawberry.field(name="eligible", default=None)
    reason: Optional[str] = strawberry.field(name="reason", default=None)


register_type("ArtifactTemplateType", ArtifactTemplateType, model=None)


@strawberry.type(name="CorpusIntelligenceSetupSummaryType", description="Result envelope for ``setupCorpusIntelligence``.\n\nMirrors ``IntelligenceSetupSummary`` from\n``opencontractserver.corpuses.services.intelligence_setup`` — graphene's\ndefault resolver reads the dataclass attributes directly.")
class CorpusIntelligenceSetupSummaryType:
    reference_available: bool = strawberry.field(name="referenceAvailable", description='The reference-enrichment analyzer is registered on this deployment.', default=None)
    reference_action_installed_now: bool = strawberry.field(name="referenceActionInstalledNow", default=None)
    reference_action_already_installed: bool = strawberry.field(name="referenceActionAlreadyInstalled", default=None)
    reference_analysis_started: bool = strawberry.field(name="referenceAnalysisStarted", description='An immediate reference-web weave was started.', default=None)
    total_active_documents: int = strawberry.field(name="totalActiveDocuments", default=None)
    templates: list["IntelligenceTemplateOutcomeType"] = strawberry.field(name="templates", default=None)


register_type("CorpusIntelligenceSetupSummaryType", CorpusIntelligenceSetupSummaryType, model=None)


@strawberry.type(name="IntelligenceTemplateOutcomeType", description='Per-template result from the one-click intelligence setup.')
class IntelligenceTemplateOutcomeType:
    template_name: str = strawberry.field(name="templateName", default=None)
    installed_now: bool = strawberry.field(name="installedNow", description='Template was cloned into the corpus by this call.', default=None)
    already_installed: bool = strawberry.field(name="alreadyInstalled", description="The corpus already had this template's action.", default=None)
    queued_count: int = strawberry.field(name="queuedCount", description='Documents queued for an agent run by this call.', default=None)
    skipped_already_run_count: int = strawberry.field(name="skippedAlreadyRunCount", description='Documents skipped because they already ran.', default=None)
    error: str = strawberry.field(name="error", description='Per-template failure (empty string when the step succeeded).', default=None)
    remaining_count: int = strawberry.field(name="remainingCount", description='Documents deferred past the per-call batch cap — re-run setup (or wait for the add_document trigger) to process them.', default=None)


register_type("IntelligenceTemplateOutcomeType", IntelligenceTemplateOutcomeType, model=None)


def q_corpus(info: strawberry.Info, id: Annotated[strawberry.ID, strawberry.argument(name="id", description='The ID of the object')] = strawberry.UNSET) -> Optional["CorpusType"]:
    return get_node_from_global_id(info, id, only_type_name="CorpusType")



QUERY_FIELDS = {
    "corpus": strawberry.field(resolver=q_corpus, name="corpus"),
}
