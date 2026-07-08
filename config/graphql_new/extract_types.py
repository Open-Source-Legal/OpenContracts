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
from config.graphql_new._util import coerce_enum, coerce_str, strip_unset
from config.graphql_new import enums

from config.graphql.filters import AnnotationFilter
from opencontractserver.analyzer.models import Analysis
from opencontractserver.analyzer.models import Analyzer
from opencontractserver.analyzer.models import GremlinEngine
from opencontractserver.corpuses.models import CorpusAction
from opencontractserver.corpuses.models import CorpusActionExecution
from opencontractserver.extracts.models import Column
from opencontractserver.extracts.models import Datacell
from opencontractserver.extracts.models import Extract
from opencontractserver.extracts.models import Fieldset
from opencontractserver.notifications.models import Notification


def _resolve_AnalyzerType_icon(root, info, **kwargs):
    """PORT: config/graphql/extract_types.py:275

    Port of AnalyzerType.resolve_icon
    """
    raise NotImplementedError("_resolve_AnalyzerType_icon not yet ported — see manifest")


def _resolve_AnalyzerType_analyzer_id(root, info, **kwargs):
    """PORT: config/graphql/extract_types.py:261

    Port of AnalyzerType.resolve_analyzer_id
    """
    raise NotImplementedError("_resolve_AnalyzerType_analyzer_id not yet ported — see manifest")


def _resolve_AnalyzerType_full_label_list(root, info, **kwargs):
    """PORT: config/graphql/extract_types.py:272

    Port of AnalyzerType.resolve_full_label_list
    """
    raise NotImplementedError("_resolve_AnalyzerType_full_label_list not yet ported — see manifest")


@strawberry.type(name="AnalyzerType")
class AnalyzerType(Node):
    user_lock: Optional[Annotated["UserType", strawberry.lazy("config.graphql_new.user_types")]] = strawberry.field(name="userLock")
    backend_lock: bool = strawberry.field(name="backendLock")
    creator: Annotated["UserType", strawberry.lazy("config.graphql_new.user_types")] = strawberry.field(name="creator")
    created: datetime.datetime = strawberry.field(name="created")
    modified: datetime.datetime = strawberry.field(name="modified")
    manifest: Optional[GenericScalar] = strawberry.field(name="manifest")
    @strawberry.field(name="description")
    def description(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "description", None))
    disabled: bool = strawberry.field(name="disabled")
    is_public: bool = strawberry.field(name="isPublic")
    @strawberry.field(name="icon")
    def icon(self, info: strawberry.Info) -> str:
        kwargs = strip_unset({})
        return _resolve_AnalyzerType_icon(self, info, **kwargs)
    host_gremlin: Optional["GremlinEngineType_WRITE"] = strawberry.field(name="hostGremlin")
    @strawberry.field(name="taskName")
    def task_name(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "task_name", None))
    input_schema: Optional[GenericScalar] = strawberry.field(name="inputSchema", description="JSONSchema describing the analyzer's expected input if provided.")
    @strawberry.field(name="corpusactionSet")
    def corpusaction_set(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET, id: Annotated[Optional[strawberry.ID], strawberry.argument(name="id")] = strawberry.UNSET, name: Annotated[Optional[str], strawberry.argument(name="name")] = strawberry.UNSET, name__icontains: Annotated[Optional[str], strawberry.argument(name="name_Icontains")] = strawberry.UNSET, name__istartswith: Annotated[Optional[str], strawberry.argument(name="name_Istartswith")] = strawberry.UNSET, corpus__id: Annotated[Optional[strawberry.ID], strawberry.argument(name="corpus_Id")] = strawberry.UNSET, fieldset__id: Annotated[Optional[strawberry.ID], strawberry.argument(name="fieldset_Id")] = strawberry.UNSET, analyzer__id: Annotated[Optional[strawberry.ID], strawberry.argument(name="analyzer_Id")] = strawberry.UNSET, agent_config__id: Annotated[Optional[strawberry.ID], strawberry.argument(name="agentConfig_Id")] = strawberry.UNSET, trigger: Annotated[Optional[enums.CorpusesCorpusActionTriggerChoices], strawberry.argument(name="trigger")] = strawberry.UNSET, creator__id: Annotated[Optional[strawberry.ID], strawberry.argument(name="creator_Id")] = strawberry.UNSET, source_template__id: Annotated[Optional[strawberry.ID], strawberry.argument(name="sourceTemplate_Id")] = strawberry.UNSET) -> Annotated["CorpusActionTypeConnection", strawberry.lazy("config.graphql_new.agent_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last, "id": id, "name": name, "name__icontains": name__icontains, "name__istartswith": name__istartswith, "corpus__id": corpus__id, "fieldset__id": fieldset__id, "analyzer__id": analyzer__id, "agent_config__id": agent_config__id, "trigger": trigger, "creator__id": creator__id, "source_template__id": source_template__id})
        resolved = getattr(self, "corpusaction_set", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="CorpusActionType", filterset_class=filterset_factory(CorpusAction, fields={'id': ['exact'], 'name': ['exact', 'icontains', 'istartswith'], 'corpus__id': ['exact'], 'fieldset__id': ['exact'], 'analyzer__id': ['exact'], 'agent_config__id': ['exact'], 'trigger': ['exact'], 'creator__id': ['exact'], 'source_template__id': ['exact']}), filter_args={"id": "id", "name": "name", "name__icontains": "name__icontains", "name__istartswith": "name__istartswith", "corpus__id": "corpus__id", "fieldset__id": "fieldset__id", "analyzer__id": "analyzer__id", "agent_config__id": "agent_config__id", "trigger": "trigger", "creator__id": "creator__id", "source_template__id": "source_template__id"}, )
    @strawberry.field(name="annotationLabels")
    def annotation_labels(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["AnnotationLabelTypeConnection", strawberry.lazy("config.graphql_new.annotation_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "annotation_labels", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="AnnotationLabelType", )
    @strawberry.field(name="relationshipSet")
    def relationship_set(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["RelationshipTypeConnection", strawberry.lazy("config.graphql_new.annotation_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "relationship_set", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="RelationshipType", )
    @strawberry.field(name="labelsetSet")
    def labelset_set(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["LabelSetTypeConnection", strawberry.lazy("config.graphql_new.annotation_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "labelset_set", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="LabelSetType", )
    @strawberry.field(name="analysisSet")
    def analysis_set(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> "AnalysisTypeConnection":
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "analysis_set", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="AnalysisType", )
    @strawberry.field(name="myPermissions")
    def my_permissions(self, info: strawberry.Info) -> Optional[GenericScalar]:
        return core_permissions.resolve_my_permissions(self, info)
    @strawberry.field(name="isPublished")
    def is_published(self, info: strawberry.Info) -> Optional[bool]:
        return core_permissions.resolve_is_published(self, info)
    @strawberry.field(name="objectSharedWith")
    def object_shared_with(self, info: strawberry.Info) -> Optional[GenericScalar]:
        return core_permissions.resolve_object_shared_with(self, info)
    @strawberry.field(name="analyzerId")
    def analyzer_id(self, info: strawberry.Info) -> Optional[str]:
        kwargs = strip_unset({})
        return _resolve_AnalyzerType_analyzer_id(self, info, **kwargs)
    @strawberry.field(name="fullLabelList")
    def full_label_list(self, info: strawberry.Info) -> Optional[list[Optional[Annotated["AnnotationLabelType", strawberry.lazy("config.graphql_new.annotation_types")]]]]:
        kwargs = strip_unset({})
        return _resolve_AnalyzerType_full_label_list(self, info, **kwargs)


register_type("AnalyzerType", AnalyzerType, model=Analyzer)


AnalyzerTypeConnection = make_connection_types(AnalyzerType, type_name="AnalyzerTypeConnection", countable=True, pdf_page_aware=False)


@strawberry.type(name="GremlinEngineType_WRITE")
class GremlinEngineType_WRITE(Node):
    user_lock: Optional[Annotated["UserType", strawberry.lazy("config.graphql_new.user_types")]] = strawberry.field(name="userLock")
    backend_lock: bool = strawberry.field(name="backendLock")
    creator: Annotated["UserType", strawberry.lazy("config.graphql_new.user_types")] = strawberry.field(name="creator")
    created: datetime.datetime = strawberry.field(name="created")
    modified: datetime.datetime = strawberry.field(name="modified")
    @strawberry.field(name="url")
    def url(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "url", None))
    last_synced: Optional[datetime.datetime] = strawberry.field(name="lastSynced")
    install_started: Optional[datetime.datetime] = strawberry.field(name="installStarted")
    install_completed: Optional[datetime.datetime] = strawberry.field(name="installCompleted")
    is_public: bool = strawberry.field(name="isPublic")
    @strawberry.field(name="analyzerSet")
    def analyzer_set(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> "AnalyzerTypeConnection":
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "analyzer_set", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="AnalyzerType", )
    @strawberry.field(name="apiKey")
    def api_key(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "api_key", None))
    @strawberry.field(name="myPermissions")
    def my_permissions(self, info: strawberry.Info) -> Optional[GenericScalar]:
        return core_permissions.resolve_my_permissions(self, info)
    @strawberry.field(name="isPublished")
    def is_published(self, info: strawberry.Info) -> Optional[bool]:
        return core_permissions.resolve_is_published(self, info)
    @strawberry.field(name="objectSharedWith")
    def object_shared_with(self, info: strawberry.Info) -> Optional[GenericScalar]:
        return core_permissions.resolve_object_shared_with(self, info)


register_type("GremlinEngineType_WRITE", GremlinEngineType_WRITE, model=GremlinEngine)


GremlinEngineType_WRITEConnection = make_connection_types(GremlinEngineType_WRITE, type_name="GremlinEngineType_WRITEConnection", countable=True, pdf_page_aware=False)


def _resolve_ExtractType_full_datacell_list(root, info, **kwargs):
    """PORT: config/graphql/extract_types.py:178

    Port of ExtractType.resolve_full_datacell_list
    """
    raise NotImplementedError("_resolve_ExtractType_full_datacell_list not yet ported — see manifest")


def _resolve_ExtractType_full_document_list(root, info, **kwargs):
    """PORT: config/graphql/extract_types.py:226

    Port of ExtractType.resolve_full_document_list
    """
    raise NotImplementedError("_resolve_ExtractType_full_document_list not yet ported — see manifest")


def _resolve_ExtractType_document_count(root, info, **kwargs):
    """PORT: config/graphql/extract_types.py:200

    Port of ExtractType.resolve_document_count
    """
    raise NotImplementedError("_resolve_ExtractType_document_count not yet ported — see manifest")


def _resolve_ExtractType_datacell_count(root, info, **kwargs):
    """PORT: config/graphql/extract_types.py:194

    Port of ExtractType.resolve_datacell_count
    """
    raise NotImplementedError("_resolve_ExtractType_datacell_count not yet ported — see manifest")


def _resolve_ExtractType_iteration_axis(root, info, **kwargs):
    """PORT: config/graphql/extract_types.py:240

    Port of ExtractType.resolve_iteration_axis
    """
    raise NotImplementedError("_resolve_ExtractType_iteration_axis not yet ported — see manifest")


def _resolve_ExtractType_full_iteration_list(root, info, **kwargs):
    """PORT: config/graphql/extract_types.py:234

    Port of ExtractType.resolve_full_iteration_list
    """
    raise NotImplementedError("_resolve_ExtractType_full_iteration_list not yet ported — see manifest")


@strawberry.type(name="ExtractType")
class ExtractType(Node):
    user_lock: Optional[Annotated["UserType", strawberry.lazy("config.graphql_new.user_types")]] = strawberry.field(name="userLock")
    backend_lock: bool = strawberry.field(name="backendLock")
    is_public: bool = strawberry.field(name="isPublic")
    creator: Annotated["UserType", strawberry.lazy("config.graphql_new.user_types")] = strawberry.field(name="creator")
    modified: datetime.datetime = strawberry.field(name="modified")
    corpus: Optional[Annotated["CorpusType", strawberry.lazy("config.graphql_new.corpus_types")]] = strawberry.field(name="corpus")
    @strawberry.field(name="documents")
    def documents(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["DocumentTypeConnection", strawberry.lazy("config.graphql_new.document_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "documents", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="DocumentType", )
    @strawberry.field(name="name")
    def name(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "name", None))
    fieldset: "FieldsetType" = strawberry.field(name="fieldset")
    created: datetime.datetime = strawberry.field(name="created")
    started: Optional[datetime.datetime] = strawberry.field(name="started")
    finished: Optional[datetime.datetime] = strawberry.field(name="finished")
    @strawberry.field(name="error")
    def error(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "error", None))
    corpus_action: Optional[Annotated["CorpusActionType", strawberry.lazy("config.graphql_new.agent_types")]] = strawberry.field(name="corpusAction")
    parent_extract: Optional["ExtractType"] = strawberry.field(name="parentExtract", description='Extract this iteration was forked from. Null for the root of an iteration series.')
    model_config: Optional[GenericScalar] = strawberry.field(name="modelConfig", description='Captured model/run configuration for this iteration.')
    @strawberry.field(name="rows")
    def rows(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["DocumentAnalysisRowTypeConnection", strawberry.lazy("config.graphql_new.document_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "rows", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="DocumentAnalysisRowType", )
    @strawberry.field(name="executionRecords", description='Extract created (for fieldset actions only)')
    def execution_records(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET, id: Annotated[Optional[strawberry.ID], strawberry.argument(name="id")] = strawberry.UNSET, corpus__id: Annotated[Optional[strawberry.ID], strawberry.argument(name="corpus_Id")] = strawberry.UNSET, corpus_action__id: Annotated[Optional[strawberry.ID], strawberry.argument(name="corpusAction_Id")] = strawberry.UNSET, document__id: Annotated[Optional[strawberry.ID], strawberry.argument(name="document_Id")] = strawberry.UNSET, status: Annotated[Optional[enums.CorpusesCorpusActionExecutionStatusChoices], strawberry.argument(name="status")] = strawberry.UNSET, action_type: Annotated[Optional[enums.CorpusesCorpusActionExecutionActionTypeChoices], strawberry.argument(name="actionType")] = strawberry.UNSET, trigger: Annotated[Optional[enums.CorpusesCorpusActionExecutionTriggerChoices], strawberry.argument(name="trigger")] = strawberry.UNSET, creator__id: Annotated[Optional[strawberry.ID], strawberry.argument(name="creator_Id")] = strawberry.UNSET) -> Annotated["CorpusActionExecutionTypeConnection", strawberry.lazy("config.graphql_new.agent_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last, "id": id, "corpus__id": corpus__id, "corpus_action__id": corpus_action__id, "document__id": document__id, "status": status, "action_type": action_type, "trigger": trigger, "creator__id": creator__id})
        resolved = getattr(self, "execution_records", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="CorpusActionExecutionType", filterset_class=filterset_factory(CorpusActionExecution, fields={'id': ['exact'], 'corpus__id': ['exact'], 'corpus_action__id': ['exact'], 'document__id': ['exact'], 'status': ['exact'], 'action_type': ['exact'], 'trigger': ['exact'], 'creator__id': ['exact']}), filter_args={"id": "id", "corpus__id": "corpus__id", "corpus_action__id": "corpus_action__id", "document__id": "document__id", "status": "status", "action_type": "action_type", "trigger": "trigger", "creator__id": "creator__id"}, )
    @strawberry.field(name="createdRelationships", description='If set, this relationship is private to the extract that created it')
    def created_relationships(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["RelationshipTypeConnection", strawberry.lazy("config.graphql_new.annotation_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "created_relationships", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="RelationshipType", )
    @strawberry.field(name="createdAnnotations", description='If set, this annotation is private to the extract that created it')
    def created_annotations(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET, raw_text__contains: Annotated[Optional[str], strawberry.argument(name="rawText_Contains")] = strawberry.UNSET, annotation_label_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="annotationLabelId")] = strawberry.UNSET, annotation_label__text: Annotated[Optional[str], strawberry.argument(name="annotationLabel_Text")] = strawberry.UNSET, annotation_label__text__contains: Annotated[Optional[str], strawberry.argument(name="annotationLabel_Text_Contains")] = strawberry.UNSET, annotation_label__description__contains: Annotated[Optional[str], strawberry.argument(name="annotationLabel_Description_Contains")] = strawberry.UNSET, annotation_label__label_type: Annotated[Optional[enums.AnnotationsAnnotationLabelLabelTypeChoices], strawberry.argument(name="annotationLabel_LabelType")] = strawberry.UNSET, analysis__isnull: Annotated[Optional[bool], strawberry.argument(name="analysis_Isnull")] = strawberry.UNSET, document_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="documentId")] = strawberry.UNSET, corpus_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="corpusId")] = strawberry.UNSET, structural: Annotated[Optional[bool], strawberry.argument(name="structural")] = strawberry.UNSET, uses_label_from_labelset_id: Annotated[Optional[str], strawberry.argument(name="usesLabelFromLabelsetId")] = strawberry.UNSET, created_by_analysis_ids: Annotated[Optional[str], strawberry.argument(name="createdByAnalysisIds")] = strawberry.UNSET, created_with_analyzer_id: Annotated[Optional[str], strawberry.argument(name="createdWithAnalyzerId")] = strawberry.UNSET, order_by: Annotated[Optional[str], strawberry.argument(name="orderBy", description='Ordering')] = strawberry.UNSET) -> Annotated["AnnotationTypeConnection", strawberry.lazy("config.graphql_new.annotation_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last, "raw_text__contains": raw_text__contains, "annotation_label_id": annotation_label_id, "annotation_label__text": annotation_label__text, "annotation_label__text__contains": annotation_label__text__contains, "annotation_label__description__contains": annotation_label__description__contains, "annotation_label__label_type": annotation_label__label_type, "analysis__isnull": analysis__isnull, "document_id": document_id, "corpus_id": corpus_id, "structural": structural, "uses_label_from_labelset_id": uses_label_from_labelset_id, "created_by_analysis_ids": created_by_analysis_ids, "created_with_analyzer_id": created_with_analyzer_id, "order_by": order_by})
        resolved = getattr(self, "created_annotations", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="AnnotationType", filterset_class=setup_filterset(AnnotationFilter), filter_args={"raw_text__contains": "raw_text__contains", "annotation_label_id": "annotation_label_id", "annotation_label__text": "annotation_label__text", "annotation_label__text__contains": "annotation_label__text__contains", "annotation_label__description__contains": "annotation_label__description__contains", "annotation_label__label_type": "annotation_label__label_type", "analysis__isnull": "analysis__isnull", "document_id": "document_id", "corpus_id": "corpus_id", "structural": "structural", "uses_label_from_labelset_id": "uses_label_from_labelset_id", "created_by_analysis_ids": "created_by_analysis_ids", "created_with_analyzer_id": "created_with_analyzer_id", "order_by": "order_by"}, )
    @strawberry.field(name="iterations", description='Extract this iteration was forked from. Null for the root of an iteration series.')
    def iterations(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> "ExtractTypeConnection":
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "iterations", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="ExtractType", )
    @strawberry.field(name="extractedDatacells")
    def extracted_datacells(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> "DatacellTypeConnection":
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "extracted_datacells", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="DatacellType", )
    @strawberry.field(name="myPermissions")
    def my_permissions(self, info: strawberry.Info) -> Optional[GenericScalar]:
        return core_permissions.resolve_my_permissions(self, info)
    @strawberry.field(name="isPublished")
    def is_published(self, info: strawberry.Info) -> Optional[bool]:
        return core_permissions.resolve_is_published(self, info)
    @strawberry.field(name="objectSharedWith")
    def object_shared_with(self, info: strawberry.Info) -> Optional[GenericScalar]:
        return core_permissions.resolve_object_shared_with(self, info)
    @strawberry.field(name="fullDatacellList")
    def full_datacell_list(self, info: strawberry.Info, limit: Annotated[Optional[int], strawberry.argument(name="limit", description='Maximum number of datacells to return. Clamped to the server maximum of 500 even when omitted; callers that need all cells must paginate using `offset`.')] = strawberry.UNSET, offset: Annotated[Optional[int], strawberry.argument(name="offset", description='Number of datacells to skip before applying `limit`. Use together with `limit` for client-driven pagination.')] = strawberry.UNSET) -> Optional[list[Optional["DatacellType"]]]:
        kwargs = strip_unset({"limit": limit, "offset": offset})
        return _resolve_ExtractType_full_datacell_list(self, info, **kwargs)
    @strawberry.field(name="fullDocumentList")
    def full_document_list(self, info: strawberry.Info) -> Optional[list[Optional[Annotated["DocumentType", strawberry.lazy("config.graphql_new.document_types")]]]]:
        kwargs = strip_unset({})
        return _resolve_ExtractType_full_document_list(self, info, **kwargs)
    @strawberry.field(name="documentCount", description='Number of documents associated with this extract. Use instead of `fullDocumentList { id }` when only the count is needed — the full-list resolver runs a per-row permission check that turns into an N+1 on list pages.')
    def document_count(self, info: strawberry.Info) -> Optional[int]:
        kwargs = strip_unset({})
        return _resolve_ExtractType_document_count(self, info, **kwargs)
    @strawberry.field(name="datacellCount", description="Total number of datacells in this extract visible to the current user, ignoring any `limit`/`offset` applied to `fullDatacellList`. Use together with `fullDatacellList(limit: ...)` to display 'showing N of M' indicators when the payload is bounded.")
    def datacell_count(self, info: strawberry.Info) -> Optional[int]:
        kwargs = strip_unset({})
        return _resolve_ExtractType_datacell_count(self, info, **kwargs)
    @strawberry.field(name="iterationAxis", description="Best-effort axis label inferred from the iteration relationship: 'MODEL' if model_config differs from parent, 'FIELDSET' if fieldset differs, 'DOCUMENT_VERSIONS' if doc set differs, else null. Useful for badging the Iterations tab.")
    def iteration_axis(self, info: strawberry.Info) -> Optional[str]:
        kwargs = strip_unset({})
        return _resolve_ExtractType_iteration_axis(self, info, **kwargs)
    @strawberry.field(name="fullIterationList", description='Direct iterations forked from this extract (one level deep). Walk recursively for the full subtree.')
    def full_iteration_list(self, info: strawberry.Info) -> Optional[list[Optional["ExtractType"]]]:
        kwargs = strip_unset({})
        return _resolve_ExtractType_full_iteration_list(self, info, **kwargs)


def _get_node_ExtractType(info, pk):
    """PORT: config.graphql.extract_types.ExtractType.get_node

    Port of ExtractType.get_node
    """
    raise NotImplementedError("_get_node_ExtractType not yet ported — see manifest")


register_type("ExtractType", ExtractType, model=Extract, get_node=_get_node_ExtractType)


ExtractTypeConnection = make_connection_types(ExtractType, type_name="ExtractTypeConnection", countable=True, pdf_page_aware=False)


def _resolve_FieldsetType_in_use(root, info, **kwargs):
    """PORT: config/graphql/extract_types.py:51

    Port of FieldsetType.resolve_in_use
    """
    raise NotImplementedError("_resolve_FieldsetType_in_use not yet ported — see manifest")


def _resolve_FieldsetType_full_column_list(root, info, **kwargs):
    """PORT: config/graphql/extract_types.py:57

    Port of FieldsetType.resolve_full_column_list
    """
    raise NotImplementedError("_resolve_FieldsetType_full_column_list not yet ported — see manifest")


def _resolve_FieldsetType_column_count(root, info, **kwargs):
    """PORT: config/graphql/extract_types.py:60

    Port of FieldsetType.resolve_column_count
    """
    raise NotImplementedError("_resolve_FieldsetType_column_count not yet ported — see manifest")


@strawberry.type(name="FieldsetType")
class FieldsetType(Node):
    user_lock: Optional[Annotated["UserType", strawberry.lazy("config.graphql_new.user_types")]] = strawberry.field(name="userLock")
    backend_lock: bool = strawberry.field(name="backendLock")
    is_public: bool = strawberry.field(name="isPublic")
    creator: Annotated["UserType", strawberry.lazy("config.graphql_new.user_types")] = strawberry.field(name="creator")
    created: datetime.datetime = strawberry.field(name="created")
    modified: datetime.datetime = strawberry.field(name="modified")
    @strawberry.field(name="name")
    def name(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "name", None))
    @strawberry.field(name="description")
    def description(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "description", None))
    corpus: Optional[Annotated["CorpusType", strawberry.lazy("config.graphql_new.corpus_types")]] = strawberry.field(name="corpus", description='If set, this fieldset defines the metadata schema for the corpus')
    @strawberry.field(name="corpusactionSet")
    def corpusaction_set(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET, id: Annotated[Optional[strawberry.ID], strawberry.argument(name="id")] = strawberry.UNSET, name: Annotated[Optional[str], strawberry.argument(name="name")] = strawberry.UNSET, name__icontains: Annotated[Optional[str], strawberry.argument(name="name_Icontains")] = strawberry.UNSET, name__istartswith: Annotated[Optional[str], strawberry.argument(name="name_Istartswith")] = strawberry.UNSET, corpus__id: Annotated[Optional[strawberry.ID], strawberry.argument(name="corpus_Id")] = strawberry.UNSET, fieldset__id: Annotated[Optional[strawberry.ID], strawberry.argument(name="fieldset_Id")] = strawberry.UNSET, analyzer__id: Annotated[Optional[strawberry.ID], strawberry.argument(name="analyzer_Id")] = strawberry.UNSET, agent_config__id: Annotated[Optional[strawberry.ID], strawberry.argument(name="agentConfig_Id")] = strawberry.UNSET, trigger: Annotated[Optional[enums.CorpusesCorpusActionTriggerChoices], strawberry.argument(name="trigger")] = strawberry.UNSET, creator__id: Annotated[Optional[strawberry.ID], strawberry.argument(name="creator_Id")] = strawberry.UNSET, source_template__id: Annotated[Optional[strawberry.ID], strawberry.argument(name="sourceTemplate_Id")] = strawberry.UNSET) -> Annotated["CorpusActionTypeConnection", strawberry.lazy("config.graphql_new.agent_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last, "id": id, "name": name, "name__icontains": name__icontains, "name__istartswith": name__istartswith, "corpus__id": corpus__id, "fieldset__id": fieldset__id, "analyzer__id": analyzer__id, "agent_config__id": agent_config__id, "trigger": trigger, "creator__id": creator__id, "source_template__id": source_template__id})
        resolved = getattr(self, "corpusaction_set", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="CorpusActionType", filterset_class=filterset_factory(CorpusAction, fields={'id': ['exact'], 'name': ['exact', 'icontains', 'istartswith'], 'corpus__id': ['exact'], 'fieldset__id': ['exact'], 'analyzer__id': ['exact'], 'agent_config__id': ['exact'], 'trigger': ['exact'], 'creator__id': ['exact'], 'source_template__id': ['exact']}), filter_args={"id": "id", "name": "name", "name__icontains": "name__icontains", "name__istartswith": "name__istartswith", "corpus__id": "corpus__id", "fieldset__id": "fieldset__id", "analyzer__id": "analyzer__id", "agent_config__id": "agent_config__id", "trigger": "trigger", "creator__id": "creator__id", "source_template__id": "source_template__id"}, )
    @strawberry.field(name="columns")
    def columns(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> "ColumnTypeConnection":
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "columns", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="ColumnType", )
    @strawberry.field(name="extracts")
    def extracts(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> "ExtractTypeConnection":
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "extracts", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="ExtractType", )
    @strawberry.field(name="myPermissions")
    def my_permissions(self, info: strawberry.Info) -> Optional[GenericScalar]:
        return core_permissions.resolve_my_permissions(self, info)
    @strawberry.field(name="isPublished")
    def is_published(self, info: strawberry.Info) -> Optional[bool]:
        return core_permissions.resolve_is_published(self, info)
    @strawberry.field(name="objectSharedWith")
    def object_shared_with(self, info: strawberry.Info) -> Optional[GenericScalar]:
        return core_permissions.resolve_object_shared_with(self, info)
    @strawberry.field(name="inUse", description='True if the fieldset is used in any extract that has started.')
    def in_use(self, info: strawberry.Info) -> Optional[bool]:
        kwargs = strip_unset({})
        return _resolve_FieldsetType_in_use(self, info, **kwargs)
    @strawberry.field(name="fullColumnList")
    def full_column_list(self, info: strawberry.Info) -> Optional[list[Optional["ColumnType"]]]:
        kwargs = strip_unset({})
        return _resolve_FieldsetType_full_column_list(self, info, **kwargs)
    @strawberry.field(name="columnCount", description='Number of columns in this fieldset. Use instead of `fullColumnList { id }` when only the count is needed — list-view queries pay for full Column rows otherwise.')
    def column_count(self, info: strawberry.Info) -> Optional[int]:
        kwargs = strip_unset({})
        return _resolve_FieldsetType_column_count(self, info, **kwargs)


register_type("FieldsetType", FieldsetType, model=Fieldset)


FieldsetTypeConnection = make_connection_types(FieldsetType, type_name="FieldsetTypeConnection", countable=True, pdf_page_aware=False)


@strawberry.type(name="ColumnType")
class ColumnType(Node):
    user_lock: Optional[Annotated["UserType", strawberry.lazy("config.graphql_new.user_types")]] = strawberry.field(name="userLock")
    backend_lock: bool = strawberry.field(name="backendLock")
    is_public: bool = strawberry.field(name="isPublic")
    creator: Annotated["UserType", strawberry.lazy("config.graphql_new.user_types")] = strawberry.field(name="creator")
    created: datetime.datetime = strawberry.field(name="created")
    modified: datetime.datetime = strawberry.field(name="modified")
    @strawberry.field(name="name")
    def name(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "name", None))
    fieldset: "FieldsetType" = strawberry.field(name="fieldset")
    @strawberry.field(name="query")
    def query(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "query", None))
    @strawberry.field(name="matchText")
    def match_text(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "match_text", None))
    @strawberry.field(name="mustContainText")
    def must_contain_text(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "must_contain_text", None))
    @strawberry.field(name="outputType")
    def output_type(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "output_type", None))
    @strawberry.field(name="limitToLabel")
    def limit_to_label(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "limit_to_label", None))
    @strawberry.field(name="instructions")
    def instructions(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "instructions", None))
    extract_is_list: bool = strawberry.field(name="extractIsList")
    @strawberry.field(name="taskName")
    def task_name(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "task_name", None))
    @strawberry.field(name="dataType", description='Structured data type for manual entry fields')
    def data_type(self, info: strawberry.Info) -> Optional[enums.ExtractsColumnDataTypeChoices]:
        return coerce_enum(enums.ExtractsColumnDataTypeChoices, getattr(self, "data_type", None))
    validation_config: Optional[GenericScalar] = strawberry.field(name="validationConfig")
    is_manual_entry: bool = strawberry.field(name="isManualEntry", description='True for manual metadata, False for extraction')
    default_value: Optional[GenericScalar] = strawberry.field(name="defaultValue")
    @strawberry.field(name="helpText", description='Help text to display for manual entry fields')
    def help_text(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "help_text", None))
    display_order: int = strawberry.field(name="displayOrder", description='Order in which to display manual entry fields')
    @strawberry.field(name="extractedDatacells")
    def extracted_datacells(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> "DatacellTypeConnection":
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "extracted_datacells", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="DatacellType", )
    @strawberry.field(name="myPermissions")
    def my_permissions(self, info: strawberry.Info) -> Optional[GenericScalar]:
        return core_permissions.resolve_my_permissions(self, info)
    @strawberry.field(name="isPublished")
    def is_published(self, info: strawberry.Info) -> Optional[bool]:
        return core_permissions.resolve_is_published(self, info)
    @strawberry.field(name="objectSharedWith")
    def object_shared_with(self, info: strawberry.Info) -> Optional[GenericScalar]:
        return core_permissions.resolve_object_shared_with(self, info)


register_type("ColumnType", ColumnType, model=Column)


ColumnTypeConnection = make_connection_types(ColumnType, type_name="ColumnTypeConnection", countable=True, pdf_page_aware=False)


def _resolve_DatacellType_full_source_list(root, info, **kwargs):
    """PORT: config/graphql/extract_types.py:76

    Port of DatacellType.resolve_full_source_list
    """
    raise NotImplementedError("_resolve_DatacellType_full_source_list not yet ported — see manifest")


@strawberry.type(name="DatacellType")
class DatacellType(Node):
    user_lock: Optional[Annotated["UserType", strawberry.lazy("config.graphql_new.user_types")]] = strawberry.field(name="userLock")
    backend_lock: bool = strawberry.field(name="backendLock")
    is_public: bool = strawberry.field(name="isPublic")
    creator: Annotated["UserType", strawberry.lazy("config.graphql_new.user_types")] = strawberry.field(name="creator")
    created: datetime.datetime = strawberry.field(name="created")
    modified: datetime.datetime = strawberry.field(name="modified")
    extract: Optional["ExtractType"] = strawberry.field(name="extract")
    column: "ColumnType" = strawberry.field(name="column")
    document: Annotated["DocumentType", strawberry.lazy("config.graphql_new.document_types")] = strawberry.field(name="document")
    @strawberry.field(name="sources")
    def sources(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET, raw_text__contains: Annotated[Optional[str], strawberry.argument(name="rawText_Contains")] = strawberry.UNSET, annotation_label_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="annotationLabelId")] = strawberry.UNSET, annotation_label__text: Annotated[Optional[str], strawberry.argument(name="annotationLabel_Text")] = strawberry.UNSET, annotation_label__text__contains: Annotated[Optional[str], strawberry.argument(name="annotationLabel_Text_Contains")] = strawberry.UNSET, annotation_label__description__contains: Annotated[Optional[str], strawberry.argument(name="annotationLabel_Description_Contains")] = strawberry.UNSET, annotation_label__label_type: Annotated[Optional[enums.AnnotationsAnnotationLabelLabelTypeChoices], strawberry.argument(name="annotationLabel_LabelType")] = strawberry.UNSET, analysis__isnull: Annotated[Optional[bool], strawberry.argument(name="analysis_Isnull")] = strawberry.UNSET, document_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="documentId")] = strawberry.UNSET, corpus_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="corpusId")] = strawberry.UNSET, structural: Annotated[Optional[bool], strawberry.argument(name="structural")] = strawberry.UNSET, uses_label_from_labelset_id: Annotated[Optional[str], strawberry.argument(name="usesLabelFromLabelsetId")] = strawberry.UNSET, created_by_analysis_ids: Annotated[Optional[str], strawberry.argument(name="createdByAnalysisIds")] = strawberry.UNSET, created_with_analyzer_id: Annotated[Optional[str], strawberry.argument(name="createdWithAnalyzerId")] = strawberry.UNSET, order_by: Annotated[Optional[str], strawberry.argument(name="orderBy", description='Ordering')] = strawberry.UNSET) -> Annotated["AnnotationTypeConnection", strawberry.lazy("config.graphql_new.annotation_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last, "raw_text__contains": raw_text__contains, "annotation_label_id": annotation_label_id, "annotation_label__text": annotation_label__text, "annotation_label__text__contains": annotation_label__text__contains, "annotation_label__description__contains": annotation_label__description__contains, "annotation_label__label_type": annotation_label__label_type, "analysis__isnull": analysis__isnull, "document_id": document_id, "corpus_id": corpus_id, "structural": structural, "uses_label_from_labelset_id": uses_label_from_labelset_id, "created_by_analysis_ids": created_by_analysis_ids, "created_with_analyzer_id": created_with_analyzer_id, "order_by": order_by})
        resolved = getattr(self, "sources", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="AnnotationType", filterset_class=setup_filterset(AnnotationFilter), filter_args={"raw_text__contains": "raw_text__contains", "annotation_label_id": "annotation_label_id", "annotation_label__text": "annotation_label__text", "annotation_label__text__contains": "annotation_label__text__contains", "annotation_label__description__contains": "annotation_label__description__contains", "annotation_label__label_type": "annotation_label__label_type", "analysis__isnull": "analysis__isnull", "document_id": "document_id", "corpus_id": "corpus_id", "structural": "structural", "uses_label_from_labelset_id": "uses_label_from_labelset_id", "created_by_analysis_ids": "created_by_analysis_ids", "created_with_analyzer_id": "created_with_analyzer_id", "order_by": "order_by"}, )
    data: Optional[GenericScalar] = strawberry.field(name="data")
    @strawberry.field(name="dataDefinition")
    def data_definition(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "data_definition", None))
    started: Optional[datetime.datetime] = strawberry.field(name="started")
    completed: Optional[datetime.datetime] = strawberry.field(name="completed")
    failed: Optional[datetime.datetime] = strawberry.field(name="failed")
    @strawberry.field(name="stacktrace")
    def stacktrace(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "stacktrace", None))
    approved_by: Optional[Annotated["UserType", strawberry.lazy("config.graphql_new.user_types")]] = strawberry.field(name="approvedBy")
    rejected_by: Optional[Annotated["UserType", strawberry.lazy("config.graphql_new.user_types")]] = strawberry.field(name="rejectedBy")
    corrected_data: Optional[GenericScalar] = strawberry.field(name="correctedData")
    @strawberry.field(name="llmCallLog", description='Captured LLM message history for debugging extraction issues')
    def llm_call_log(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "llm_call_log", None))
    @strawberry.field(name="rows")
    def rows(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["DocumentAnalysisRowTypeConnection", strawberry.lazy("config.graphql_new.document_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "rows", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="DocumentAnalysisRowType", )
    @strawberry.field(name="myPermissions")
    def my_permissions(self, info: strawberry.Info) -> Optional[GenericScalar]:
        return core_permissions.resolve_my_permissions(self, info)
    @strawberry.field(name="isPublished")
    def is_published(self, info: strawberry.Info) -> Optional[bool]:
        return core_permissions.resolve_is_published(self, info)
    @strawberry.field(name="objectSharedWith")
    def object_shared_with(self, info: strawberry.Info) -> Optional[GenericScalar]:
        return core_permissions.resolve_object_shared_with(self, info)
    @strawberry.field(name="fullSourceList")
    def full_source_list(self, info: strawberry.Info) -> Optional[list[Optional[Annotated["AnnotationType", strawberry.lazy("config.graphql_new.annotation_types")]]]]:
        kwargs = strip_unset({})
        return _resolve_DatacellType_full_source_list(self, info, **kwargs)


register_type("DatacellType", DatacellType, model=Datacell)


DatacellTypeConnection = make_connection_types(DatacellType, type_name="DatacellTypeConnection", countable=True, pdf_page_aware=False)


def _resolve_AnalysisType_full_annotation_list(root, info, **kwargs):
    """PORT: config/graphql/extract_types.py:305

    Port of AnalysisType.resolve_full_annotation_list
    """
    raise NotImplementedError("_resolve_AnalysisType_full_annotation_list not yet ported — see manifest")


@strawberry.type(name="AnalysisType")
class AnalysisType(Node):
    user_lock: Optional[Annotated["UserType", strawberry.lazy("config.graphql_new.user_types")]] = strawberry.field(name="userLock")
    backend_lock: bool = strawberry.field(name="backendLock")
    created: datetime.datetime = strawberry.field(name="created")
    modified: datetime.datetime = strawberry.field(name="modified")
    is_public: bool = strawberry.field(name="isPublic")
    creator: Annotated["UserType", strawberry.lazy("config.graphql_new.user_types")] = strawberry.field(name="creator")
    analyzer: "AnalyzerType" = strawberry.field(name="analyzer")
    @strawberry.field(name="callbackTokenHash")
    def callback_token_hash(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "callback_token_hash", None))
    @strawberry.field(name="receivedCallbackFile")
    def received_callback_file(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "received_callback_file", None))
    analyzed_corpus: Optional[Annotated["CorpusType", strawberry.lazy("config.graphql_new.corpus_types")]] = strawberry.field(name="analyzedCorpus")
    corpus_action: Optional[Annotated["CorpusActionType", strawberry.lazy("config.graphql_new.agent_types")]] = strawberry.field(name="corpusAction")
    @strawberry.field(name="importLog")
    def import_log(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "import_log", None))
    @strawberry.field(name="analyzedDocuments")
    def analyzed_documents(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["DocumentTypeConnection", strawberry.lazy("config.graphql_new.document_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "analyzed_documents", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="DocumentType", )
    @strawberry.field(name="errorMessage")
    def error_message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "error_message", None))
    @strawberry.field(name="errorTraceback")
    def error_traceback(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "error_traceback", None))
    @strawberry.field(name="resultMessage")
    def result_message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "result_message", None))
    analysis_started: Optional[datetime.datetime] = strawberry.field(name="analysisStarted")
    analysis_completed: Optional[datetime.datetime] = strawberry.field(name="analysisCompleted")
    @strawberry.field(name="status")
    def status(self, info: strawberry.Info) -> enums.AnalyzerAnalysisStatusChoices:
        return coerce_enum(enums.AnalyzerAnalysisStatusChoices, getattr(self, "status", None))
    @strawberry.field(name="rows")
    def rows(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["DocumentAnalysisRowTypeConnection", strawberry.lazy("config.graphql_new.document_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "rows", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="DocumentAnalysisRowType", )
    @strawberry.field(name="executionRecords", description='Analysis created (for analyzer actions only)')
    def execution_records(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET, id: Annotated[Optional[strawberry.ID], strawberry.argument(name="id")] = strawberry.UNSET, corpus__id: Annotated[Optional[strawberry.ID], strawberry.argument(name="corpus_Id")] = strawberry.UNSET, corpus_action__id: Annotated[Optional[strawberry.ID], strawberry.argument(name="corpusAction_Id")] = strawberry.UNSET, document__id: Annotated[Optional[strawberry.ID], strawberry.argument(name="document_Id")] = strawberry.UNSET, status: Annotated[Optional[enums.CorpusesCorpusActionExecutionStatusChoices], strawberry.argument(name="status")] = strawberry.UNSET, action_type: Annotated[Optional[enums.CorpusesCorpusActionExecutionActionTypeChoices], strawberry.argument(name="actionType")] = strawberry.UNSET, trigger: Annotated[Optional[enums.CorpusesCorpusActionExecutionTriggerChoices], strawberry.argument(name="trigger")] = strawberry.UNSET, creator__id: Annotated[Optional[strawberry.ID], strawberry.argument(name="creator_Id")] = strawberry.UNSET) -> Annotated["CorpusActionExecutionTypeConnection", strawberry.lazy("config.graphql_new.agent_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last, "id": id, "corpus__id": corpus__id, "corpus_action__id": corpus_action__id, "document__id": document__id, "status": status, "action_type": action_type, "trigger": trigger, "creator__id": creator__id})
        resolved = getattr(self, "execution_records", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="CorpusActionExecutionType", filterset_class=filterset_factory(CorpusActionExecution, fields={'id': ['exact'], 'corpus__id': ['exact'], 'corpus_action__id': ['exact'], 'document__id': ['exact'], 'status': ['exact'], 'action_type': ['exact'], 'trigger': ['exact'], 'creator__id': ['exact']}), filter_args={"id": "id", "corpus__id": "corpus__id", "corpus_action__id": "corpus_action__id", "document__id": "document__id", "status": "status", "action_type": "action_type", "trigger": "trigger", "creator__id": "creator__id"}, )
    @strawberry.field(name="relationships")
    def relationships(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["RelationshipTypeConnection", strawberry.lazy("config.graphql_new.annotation_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "relationships", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="RelationshipType", )
    @strawberry.field(name="createdRelationships", description='If set, this relationship is private to the analysis that created it')
    def created_relationships(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["RelationshipTypeConnection", strawberry.lazy("config.graphql_new.annotation_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "created_relationships", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="RelationshipType", )
    @strawberry.field(name="annotations")
    def annotations(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET, raw_text__contains: Annotated[Optional[str], strawberry.argument(name="rawText_Contains")] = strawberry.UNSET, annotation_label_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="annotationLabelId")] = strawberry.UNSET, annotation_label__text: Annotated[Optional[str], strawberry.argument(name="annotationLabel_Text")] = strawberry.UNSET, annotation_label__text__contains: Annotated[Optional[str], strawberry.argument(name="annotationLabel_Text_Contains")] = strawberry.UNSET, annotation_label__description__contains: Annotated[Optional[str], strawberry.argument(name="annotationLabel_Description_Contains")] = strawberry.UNSET, annotation_label__label_type: Annotated[Optional[enums.AnnotationsAnnotationLabelLabelTypeChoices], strawberry.argument(name="annotationLabel_LabelType")] = strawberry.UNSET, analysis__isnull: Annotated[Optional[bool], strawberry.argument(name="analysis_Isnull")] = strawberry.UNSET, document_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="documentId")] = strawberry.UNSET, corpus_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="corpusId")] = strawberry.UNSET, structural: Annotated[Optional[bool], strawberry.argument(name="structural")] = strawberry.UNSET, uses_label_from_labelset_id: Annotated[Optional[str], strawberry.argument(name="usesLabelFromLabelsetId")] = strawberry.UNSET, created_by_analysis_ids: Annotated[Optional[str], strawberry.argument(name="createdByAnalysisIds")] = strawberry.UNSET, created_with_analyzer_id: Annotated[Optional[str], strawberry.argument(name="createdWithAnalyzerId")] = strawberry.UNSET, order_by: Annotated[Optional[str], strawberry.argument(name="orderBy", description='Ordering')] = strawberry.UNSET) -> Annotated["AnnotationTypeConnection", strawberry.lazy("config.graphql_new.annotation_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last, "raw_text__contains": raw_text__contains, "annotation_label_id": annotation_label_id, "annotation_label__text": annotation_label__text, "annotation_label__text__contains": annotation_label__text__contains, "annotation_label__description__contains": annotation_label__description__contains, "annotation_label__label_type": annotation_label__label_type, "analysis__isnull": analysis__isnull, "document_id": document_id, "corpus_id": corpus_id, "structural": structural, "uses_label_from_labelset_id": uses_label_from_labelset_id, "created_by_analysis_ids": created_by_analysis_ids, "created_with_analyzer_id": created_with_analyzer_id, "order_by": order_by})
        resolved = getattr(self, "annotations", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="AnnotationType", filterset_class=setup_filterset(AnnotationFilter), filter_args={"raw_text__contains": "raw_text__contains", "annotation_label_id": "annotation_label_id", "annotation_label__text": "annotation_label__text", "annotation_label__text__contains": "annotation_label__text__contains", "annotation_label__description__contains": "annotation_label__description__contains", "annotation_label__label_type": "annotation_label__label_type", "analysis__isnull": "analysis__isnull", "document_id": "document_id", "corpus_id": "corpus_id", "structural": "structural", "uses_label_from_labelset_id": "uses_label_from_labelset_id", "created_by_analysis_ids": "created_by_analysis_ids", "created_with_analyzer_id": "created_with_analyzer_id", "order_by": "order_by"}, )
    @strawberry.field(name="createdAnnotations", description='If set, this annotation is private to the analysis that created it')
    def created_annotations(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET, raw_text__contains: Annotated[Optional[str], strawberry.argument(name="rawText_Contains")] = strawberry.UNSET, annotation_label_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="annotationLabelId")] = strawberry.UNSET, annotation_label__text: Annotated[Optional[str], strawberry.argument(name="annotationLabel_Text")] = strawberry.UNSET, annotation_label__text__contains: Annotated[Optional[str], strawberry.argument(name="annotationLabel_Text_Contains")] = strawberry.UNSET, annotation_label__description__contains: Annotated[Optional[str], strawberry.argument(name="annotationLabel_Description_Contains")] = strawberry.UNSET, annotation_label__label_type: Annotated[Optional[enums.AnnotationsAnnotationLabelLabelTypeChoices], strawberry.argument(name="annotationLabel_LabelType")] = strawberry.UNSET, analysis__isnull: Annotated[Optional[bool], strawberry.argument(name="analysis_Isnull")] = strawberry.UNSET, document_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="documentId")] = strawberry.UNSET, corpus_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="corpusId")] = strawberry.UNSET, structural: Annotated[Optional[bool], strawberry.argument(name="structural")] = strawberry.UNSET, uses_label_from_labelset_id: Annotated[Optional[str], strawberry.argument(name="usesLabelFromLabelsetId")] = strawberry.UNSET, created_by_analysis_ids: Annotated[Optional[str], strawberry.argument(name="createdByAnalysisIds")] = strawberry.UNSET, created_with_analyzer_id: Annotated[Optional[str], strawberry.argument(name="createdWithAnalyzerId")] = strawberry.UNSET, order_by: Annotated[Optional[str], strawberry.argument(name="orderBy", description='Ordering')] = strawberry.UNSET) -> Annotated["AnnotationTypeConnection", strawberry.lazy("config.graphql_new.annotation_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last, "raw_text__contains": raw_text__contains, "annotation_label_id": annotation_label_id, "annotation_label__text": annotation_label__text, "annotation_label__text__contains": annotation_label__text__contains, "annotation_label__description__contains": annotation_label__description__contains, "annotation_label__label_type": annotation_label__label_type, "analysis__isnull": analysis__isnull, "document_id": document_id, "corpus_id": corpus_id, "structural": structural, "uses_label_from_labelset_id": uses_label_from_labelset_id, "created_by_analysis_ids": created_by_analysis_ids, "created_with_analyzer_id": created_with_analyzer_id, "order_by": order_by})
        resolved = getattr(self, "created_annotations", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="AnnotationType", filterset_class=setup_filterset(AnnotationFilter), filter_args={"raw_text__contains": "raw_text__contains", "annotation_label_id": "annotation_label_id", "annotation_label__text": "annotation_label__text", "annotation_label__text__contains": "annotation_label__text__contains", "annotation_label__description__contains": "annotation_label__description__contains", "annotation_label__label_type": "annotation_label__label_type", "analysis__isnull": "analysis__isnull", "document_id": "document_id", "corpus_id": "corpus_id", "structural": "structural", "uses_label_from_labelset_id": "uses_label_from_labelset_id", "created_by_analysis_ids": "created_by_analysis_ids", "created_with_analyzer_id": "created_with_analyzer_id", "order_by": "order_by"}, )
    @strawberry.field(name="createdReferences")
    def created_references(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["CorpusReferenceTypeConnection", strawberry.lazy("config.graphql_new.annotation_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "created_references", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="CorpusReferenceType", )
    @strawberry.field(name="notifications", description='Related analysis job, if applicable.')
    def notifications(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET, is_read: Annotated[Optional[bool], strawberry.argument(name="isRead")] = strawberry.UNSET, notification_type: Annotated[Optional[enums.NotificationsNotificationNotificationTypeChoices], strawberry.argument(name="notificationType")] = strawberry.UNSET, created_at__lte: Annotated[Optional[datetime.datetime], strawberry.argument(name="createdAt_Lte")] = strawberry.UNSET, created_at__gte: Annotated[Optional[datetime.datetime], strawberry.argument(name="createdAt_Gte")] = strawberry.UNSET) -> Annotated["NotificationTypeConnection", strawberry.lazy("config.graphql_new.social_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last, "is_read": is_read, "notification_type": notification_type, "created_at__lte": created_at__lte, "created_at__gte": created_at__gte})
        resolved = getattr(self, "notifications", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="NotificationType", filterset_class=filterset_factory(Notification, fields={'is_read': ['exact'], 'notification_type': ['exact'], 'created_at': ['lte', 'gte']}), filter_args={"is_read": "is_read", "notification_type": "notification_type", "created_at__lte": "created_at__lte", "created_at__gte": "created_at__gte"}, )
    @strawberry.field(name="myPermissions")
    def my_permissions(self, info: strawberry.Info) -> Optional[GenericScalar]:
        return core_permissions.resolve_my_permissions(self, info)
    @strawberry.field(name="isPublished")
    def is_published(self, info: strawberry.Info) -> Optional[bool]:
        return core_permissions.resolve_is_published(self, info)
    @strawberry.field(name="objectSharedWith")
    def object_shared_with(self, info: strawberry.Info) -> Optional[GenericScalar]:
        return core_permissions.resolve_object_shared_with(self, info)
    @strawberry.field(name="fullAnnotationList")
    def full_annotation_list(self, info: strawberry.Info, document_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="documentId")] = strawberry.UNSET) -> Optional[list[Optional[Annotated["AnnotationType", strawberry.lazy("config.graphql_new.annotation_types")]]]]:
        kwargs = strip_unset({"document_id": document_id})
        return _resolve_AnalysisType_full_annotation_list(self, info, **kwargs)


def _get_node_AnalysisType(info, pk):
    """PORT: config.graphql.extract_types.AnalysisType.get_node

    Port of AnalysisType.get_node
    """
    raise NotImplementedError("_get_node_AnalysisType not yet ported — see manifest")


register_type("AnalysisType", AnalysisType, model=Analysis, get_node=_get_node_AnalysisType)


AnalysisTypeConnection = make_connection_types(AnalysisType, type_name="AnalysisTypeConnection", countable=True, pdf_page_aware=False)


@strawberry.type(name="GremlinEngineType_READ")
class GremlinEngineType_READ(Node):
    user_lock: Optional[Annotated["UserType", strawberry.lazy("config.graphql_new.user_types")]] = strawberry.field(name="userLock")
    backend_lock: bool = strawberry.field(name="backendLock")
    creator: Annotated["UserType", strawberry.lazy("config.graphql_new.user_types")] = strawberry.field(name="creator")
    created: datetime.datetime = strawberry.field(name="created")
    modified: datetime.datetime = strawberry.field(name="modified")
    @strawberry.field(name="url")
    def url(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "url", None))
    last_synced: Optional[datetime.datetime] = strawberry.field(name="lastSynced")
    install_started: Optional[datetime.datetime] = strawberry.field(name="installStarted")
    install_completed: Optional[datetime.datetime] = strawberry.field(name="installCompleted")
    is_public: bool = strawberry.field(name="isPublic")
    @strawberry.field(name="analyzerSet")
    def analyzer_set(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> "AnalyzerTypeConnection":
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "analyzer_set", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="AnalyzerType", )
    @strawberry.field(name="myPermissions")
    def my_permissions(self, info: strawberry.Info) -> Optional[GenericScalar]:
        return core_permissions.resolve_my_permissions(self, info)
    @strawberry.field(name="isPublished")
    def is_published(self, info: strawberry.Info) -> Optional[bool]:
        return core_permissions.resolve_is_published(self, info)
    @strawberry.field(name="objectSharedWith")
    def object_shared_with(self, info: strawberry.Info) -> Optional[GenericScalar]:
        return core_permissions.resolve_object_shared_with(self, info)


register_type("GremlinEngineType_READ", GremlinEngineType_READ, model=GremlinEngine)


GremlinEngineType_READConnection = make_connection_types(GremlinEngineType_READ, type_name="GremlinEngineType_READConnection", countable=True, pdf_page_aware=False)

