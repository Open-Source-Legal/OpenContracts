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
from django.db.models import Q, QuerySet

from config.graphql.base_types import build_flat_tree
from config.graphql.core import permissions as core_permissions
from config.graphql.core.permissions import get_anonymous_user_id
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
from config.graphql.filters import AuthorityFrontierFilter
from config.graphql.filters import AuthorityKeyEquivalenceFilter
from config.graphql.filters import AuthorityNamespaceFilter
from config.graphql.filters import LabelFilter
from opencontractserver.annotations.models import Annotation
from opencontractserver.annotations.models import AnnotationLabel
from opencontractserver.annotations.models import AuthorityFrontier
from opencontractserver.annotations.models import AuthorityKeyEquivalence
from opencontractserver.annotations.models import AuthorityNamespace
from opencontractserver.annotations.models import CorpusReference
from opencontractserver.annotations.models import LabelSet
from opencontractserver.annotations.models import Note
from opencontractserver.annotations.models import NoteRevision
from opencontractserver.annotations.models import Relationship
from opencontractserver.enrichment.services.authority_mapping_service import (
    MANUAL as MANUAL_SOURCE,
)
from opencontractserver.enrichment.services.authority_permissions import (
    is_authority_admin,
)
from opencontractserver.shared.services.base import BaseService
from opencontractserver.utils.permissioning import get_users_permissions_for_obj


@strawberry.input(name="RelationInputType")
class RelationInputType:
    my_permissions: Optional[GenericScalar] = strawberry.field(name="myPermissions", default=strawberry.UNSET)
    is_published: Optional[bool] = strawberry.field(name="isPublished", default=strawberry.UNSET)
    object_shared_with: Optional[GenericScalar] = strawberry.field(name="objectSharedWith", default=strawberry.UNSET)
    id: Optional[str] = strawberry.field(name="id", default=strawberry.UNSET)
    source_ids: Optional[list[Optional[str]]] = strawberry.field(name="sourceIds", default=strawberry.UNSET)
    target_ids: Optional[list[Optional[str]]] = strawberry.field(name="targetIds", default=strawberry.UNSET)
    relationship_label_id: Optional[str] = strawberry.field(name="relationshipLabelId", default=strawberry.UNSET)
    corpus_id: Optional[str] = strawberry.field(name="corpusId", default=strawberry.UNSET)
    document_id: Optional[str] = strawberry.field(name="documentId", default=strawberry.UNSET)


def _resolve_AnnotationType_annotation_type(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/annotation_types.py:732

    Port of AnnotationType.resolve_annotation_type
    """
    raise NotImplementedError("_resolve_AnnotationType_annotation_type not yet ported — see manifest")


def _resolve_AnnotationType_document(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/annotation_types.py:656

    Port of AnnotationType.resolve_document
    """
    raise NotImplementedError("_resolve_AnnotationType_document not yet ported — see manifest")


def _resolve_AnnotationType_content_modalities(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/annotation_types.py:736

    Port of AnnotationType.resolve_content_modalities
    """
    raise NotImplementedError("_resolve_AnnotationType_content_modalities not yet ported — see manifest")


def _resolve_AnnotationType_feedback_count(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/annotation_types.py:742

    Port of AnnotationType.resolve_feedback_count
    """
    raise NotImplementedError("_resolve_AnnotationType_feedback_count not yet ported — see manifest")


def _resolve_AnnotationType_all_source_node_in_relationship(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/annotation_types.py:760

    Port of AnnotationType.resolve_all_source_node_in_relationship
    """
    raise NotImplementedError("_resolve_AnnotationType_all_source_node_in_relationship not yet ported — see manifest")


def _resolve_AnnotationType_all_target_node_in_relationship(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/annotation_types.py:765

    Port of AnnotationType.resolve_all_target_node_in_relationship
    """
    raise NotImplementedError("_resolve_AnnotationType_all_target_node_in_relationship not yet ported — see manifest")


def _resolve_AnnotationType_descendants_tree(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/annotation_types.py:784

    Port of AnnotationType.resolve_descendants_tree
    """
    raise NotImplementedError("_resolve_AnnotationType_descendants_tree not yet ported — see manifest")


def _resolve_AnnotationType_full_tree(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/annotation_types.py:809

    Port of AnnotationType.resolve_full_tree
    """
    raise NotImplementedError("_resolve_AnnotationType_full_tree not yet ported — see manifest")


def _resolve_AnnotationType_subtree(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/annotation_types.py:839

    Port of AnnotationType.resolve_subtree
    """
    raise NotImplementedError("_resolve_AnnotationType_subtree not yet ported — see manifest")


@strawberry.type(name="AnnotationType")
class AnnotationType(Node):
    user_lock: Optional[Annotated["UserType", strawberry.lazy("config.graphql.user_types")]] = strawberry.field(name="userLock", default=None)
    backend_lock: bool = strawberry.field(name="backendLock", default=None)
    page: int = strawberry.field(name="page", default=None)
    @strawberry.field(name="rawText")
    def raw_text(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "raw_text", None))
    @strawberry.field(name="longDescription", description='Optional markdown description for this annotation, e.g. a section summary in a document index.')
    def long_description(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "long_description", None))
    json: Optional[GenericScalar] = strawberry.field(name="json", default=None)
    parent: Optional["AnnotationType"] = strawberry.field(name="parent", default=None)
    @strawberry.field(name="annotationType", description='Annotation type (e.g. TOKEN_LABEL, SPAN_LABEL). Returns raw DB value to avoid enum serialization errors on invalid data.')
    def annotation_type(self, info: strawberry.Info) -> Optional[str]:
        kwargs = strip_unset({})
        return _resolve_AnnotationType_annotation_type(self, info, **kwargs)
    annotation_label: Optional["AnnotationLabelType"] = strawberry.field(name="annotationLabel", default=None)
    @strawberry.field(name="document", description='The document this annotation belongs to. Structural annotations (document_id=NULL) resolve it via the shared structural set, scoped to the queried corpus by AnnotationService.structural_document_prefetch.')
    def document(self, info: strawberry.Info) -> Optional[Annotated["DocumentType", strawberry.lazy("config.graphql.document_types")]]:
        kwargs = strip_unset({})
        return _resolve_AnnotationType_document(self, info, **kwargs)
    corpus: Optional[Annotated["CorpusType", strawberry.lazy("config.graphql.corpus_types")]] = strawberry.field(name="corpus", default=None)
    analysis: Optional[Annotated["AnalysisType", strawberry.lazy("config.graphql.extract_types")]] = strawberry.field(name="analysis", default=None)
    created_by_analysis: Optional[Annotated["AnalysisType", strawberry.lazy("config.graphql.extract_types")]] = strawberry.field(name="createdByAnalysis", description='If set, this annotation is private to the analysis that created it', default=None)
    created_by_extract: Optional[Annotated["ExtractType", strawberry.lazy("config.graphql.extract_types")]] = strawberry.field(name="createdByExtract", description='If set, this annotation is private to the extract that created it', default=None)
    corpus_action: Optional[Annotated["CorpusActionType", strawberry.lazy("config.graphql.agent_types")]] = strawberry.field(name="corpusAction", description='If set, this annotation was created by a corpus action agent', default=None)
    structural: bool = strawberry.field(name="structural", default=None)
    @strawberry.field(name="linkUrl", description='Target URL opened when the annotation is clicked. Only meaningful for annotations labelled OC_URL.')
    def link_url(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "link_url", None))
    data: Optional[GenericScalar] = strawberry.field(name="data", default=None)
    is_grounding_source: bool = strawberry.field(name="isGroundingSource", default=None)
    @strawberry.field(name="contentModalities", description='Content modalities present in this annotation: TEXT, IMAGE, etc.')
    def content_modalities(self, info: strawberry.Info) -> Optional[list[Optional[str]]]:
        kwargs = strip_unset({})
        return _resolve_AnnotationType_content_modalities(self, info, **kwargs)
    @strawberry.field(name="imageContentFile", description='JSON file containing extracted image data for IMAGE modality annotations')
    def image_content_file(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "image_content_file", None))
    is_public: bool = strawberry.field(name="isPublic", default=None)
    creator: Annotated["UserType", strawberry.lazy("config.graphql.user_types")] = strawberry.field(name="creator", default=None)
    created: datetime.datetime = strawberry.field(name="created", default=None)
    modified: datetime.datetime = strawberry.field(name="modified", default=None)
    @strawberry.field(name="assignmentSet")
    def assignment_set(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["AssignmentTypeConnection", strawberry.lazy("config.graphql.user_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "assignment_set", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="AssignmentType", )
    @strawberry.field(name="rows")
    def rows(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["DocumentAnalysisRowTypeConnection", strawberry.lazy("config.graphql.document_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "rows", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="DocumentAnalysisRowType", )
    @strawberry.field(name="sourceNodeInRelationships")
    def source_node_in_relationships(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> "RelationshipTypeConnection":
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "source_node_in_relationships", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="RelationshipType", )
    @strawberry.field(name="targetNodeInRelationships")
    def target_node_in_relationships(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> "RelationshipTypeConnection":
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "target_node_in_relationships", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="RelationshipType", )
    @strawberry.field(name="children")
    def children(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET, raw_text__contains: Annotated[Optional[str], strawberry.argument(name="rawText_Contains")] = strawberry.UNSET, annotation_label_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="annotationLabelId")] = strawberry.UNSET, annotation_label__text: Annotated[Optional[str], strawberry.argument(name="annotationLabel_Text")] = strawberry.UNSET, annotation_label__text__contains: Annotated[Optional[str], strawberry.argument(name="annotationLabel_Text_Contains")] = strawberry.UNSET, annotation_label__description__contains: Annotated[Optional[str], strawberry.argument(name="annotationLabel_Description_Contains")] = strawberry.UNSET, annotation_label__label_type: Annotated[Optional[enums.AnnotationsAnnotationLabelLabelTypeChoices], strawberry.argument(name="annotationLabel_LabelType")] = strawberry.UNSET, analysis__isnull: Annotated[Optional[bool], strawberry.argument(name="analysis_Isnull")] = strawberry.UNSET, document_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="documentId")] = strawberry.UNSET, corpus_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="corpusId")] = strawberry.UNSET, structural: Annotated[Optional[bool], strawberry.argument(name="structural")] = strawberry.UNSET, uses_label_from_labelset_id: Annotated[Optional[str], strawberry.argument(name="usesLabelFromLabelsetId")] = strawberry.UNSET, created_by_analysis_ids: Annotated[Optional[str], strawberry.argument(name="createdByAnalysisIds")] = strawberry.UNSET, created_with_analyzer_id: Annotated[Optional[str], strawberry.argument(name="createdWithAnalyzerId")] = strawberry.UNSET, order_by: Annotated[Optional[str], strawberry.argument(name="orderBy", description='Ordering')] = strawberry.UNSET) -> "AnnotationTypeConnection":
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last, "raw_text__contains": raw_text__contains, "annotation_label_id": annotation_label_id, "annotation_label__text": annotation_label__text, "annotation_label__text__contains": annotation_label__text__contains, "annotation_label__description__contains": annotation_label__description__contains, "annotation_label__label_type": annotation_label__label_type, "analysis__isnull": analysis__isnull, "document_id": document_id, "corpus_id": corpus_id, "structural": structural, "uses_label_from_labelset_id": uses_label_from_labelset_id, "created_by_analysis_ids": created_by_analysis_ids, "created_with_analyzer_id": created_with_analyzer_id, "order_by": order_by})
        resolved = getattr(self, "children", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="AnnotationType", filterset_class=setup_filterset(AnnotationFilter), filter_args={"raw_text__contains": "raw_text__contains", "annotation_label_id": "annotation_label_id", "annotation_label__text": "annotation_label__text", "annotation_label__text__contains": "annotation_label__text__contains", "annotation_label__description__contains": "annotation_label__description__contains", "annotation_label__label_type": "annotation_label__label_type", "analysis__isnull": "analysis__isnull", "document_id": "document_id", "corpus_id": "corpus_id", "structural": "structural", "uses_label_from_labelset_id": "uses_label_from_labelset_id", "created_by_analysis_ids": "created_by_analysis_ids", "created_with_analyzer_id": "created_with_analyzer_id", "order_by": "order_by"}, )
    @strawberry.field(name="notes")
    def notes(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> "NoteTypeConnection":
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "notes", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="NoteType", )
    @strawberry.field(name="outboundReferences")
    def outbound_references(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> "CorpusReferenceTypeConnection":
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "outbound_references", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="CorpusReferenceType", )
    @strawberry.field(name="inboundReferences")
    def inbound_references(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> "CorpusReferenceTypeConnection":
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "inbound_references", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="CorpusReferenceType", )
    @strawberry.field(name="referencingCells")
    def referencing_cells(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["DatacellTypeConnection", strawberry.lazy("config.graphql.extract_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "referencing_cells", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="DatacellType", )
    @strawberry.field(name="userFeedback")
    def user_feedback(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["UserFeedbackTypeConnection", strawberry.lazy("config.graphql.user_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "user_feedback", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="UserFeedbackType", )
    @strawberry.field(name="chatMessages", description='Annotations that this chat message is based on')
    def chat_messages(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["MessageTypeConnection", strawberry.lazy("config.graphql.conversation_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "chat_messages", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="MessageType", )
    @strawberry.field(name="createdByChatMessage", description='Annotations that this chat message created')
    def created_by_chat_message(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["MessageTypeConnection", strawberry.lazy("config.graphql.conversation_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "created_by_chat_message", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="MessageType", )
    @strawberry.field(name="citedInResearchReports", description='Annotations cited in the final report')
    def cited_in_research_reports(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["ResearchReportTypeConnection", strawberry.lazy("config.graphql.research_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "cited_in_research_reports", None)
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
    @strawberry.field(name="feedbackCount", description='Count of user feedback')
    def feedback_count(self, info: strawberry.Info) -> Optional[int]:
        kwargs = strip_unset({})
        return _resolve_AnnotationType_feedback_count(self, info, **kwargs)
    @strawberry.field(name="allSourceNodeInRelationship")
    def all_source_node_in_relationship(self, info: strawberry.Info) -> Optional[list[Optional["RelationshipType"]]]:
        kwargs = strip_unset({})
        return _resolve_AnnotationType_all_source_node_in_relationship(self, info, **kwargs)
    @strawberry.field(name="allTargetNodeInRelationship")
    def all_target_node_in_relationship(self, info: strawberry.Info) -> Optional[list[Optional["RelationshipType"]]]:
        kwargs = strip_unset({})
        return _resolve_AnnotationType_all_target_node_in_relationship(self, info, **kwargs)
    @strawberry.field(name="descendantsTree", description="List of descendant annotations, each with immediate children's IDs.")
    def descendants_tree(self, info: strawberry.Info) -> Optional[list[Optional[GenericScalar]]]:
        kwargs = strip_unset({})
        return _resolve_AnnotationType_descendants_tree(self, info, **kwargs)
    @strawberry.field(name="fullTree", description="List of annotations from the root ancestor, each with immediate children's IDs.")
    def full_tree(self, info: strawberry.Info) -> Optional[list[Optional[GenericScalar]]]:
        kwargs = strip_unset({})
        return _resolve_AnnotationType_full_tree(self, info, **kwargs)
    @strawberry.field(name="subtree", description='List representing the path from the root ancestor to this annotation and its descendants.')
    def subtree(self, info: strawberry.Info) -> Optional[list[Optional[GenericScalar]]]:
        kwargs = strip_unset({})
        return _resolve_AnnotationType_subtree(self, info, **kwargs)


def _get_queryset_AnnotationType(queryset, info):
    """PORT: config.graphql.annotation_types.AnnotationType.get_queryset

    Port of AnnotationType.get_queryset
    """
    raise NotImplementedError("_get_queryset_AnnotationType not yet ported — see manifest")


register_type("AnnotationType", AnnotationType, model=Annotation, get_queryset=_get_queryset_AnnotationType)


AnnotationTypeConnection = make_connection_types(AnnotationType, type_name="AnnotationTypeConnection", countable=True, pdf_page_aware=False)


def _resolve_AnnotationLabelType_my_permissions(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/annotation_types.py:930

    Port of AnnotationLabelType.resolve_my_permissions
    """
    raise NotImplementedError("_resolve_AnnotationLabelType_my_permissions not yet ported — see manifest")


@strawberry.type(name="AnnotationLabelType")
class AnnotationLabelType(Node):
    user_lock: Optional[Annotated["UserType", strawberry.lazy("config.graphql.user_types")]] = strawberry.field(name="userLock", default=None)
    backend_lock: bool = strawberry.field(name="backendLock", default=None)
    created: datetime.datetime = strawberry.field(name="created", default=None)
    modified: datetime.datetime = strawberry.field(name="modified", default=None)
    @strawberry.field(name="labelType")
    def label_type(self, info: strawberry.Info) -> enums.AnnotationsAnnotationLabelLabelTypeChoices:
        return coerce_enum(enums.AnnotationsAnnotationLabelLabelTypeChoices, getattr(self, "label_type", None))
    analyzer: Optional[Annotated["AnalyzerType", strawberry.lazy("config.graphql.extract_types")]] = strawberry.field(name="analyzer", default=None)
    read_only: bool = strawberry.field(name="readOnly", default=None)
    @strawberry.field(name="color")
    def color(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "color", None))
    @strawberry.field(name="description")
    def description(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "description", None))
    @strawberry.field(name="icon")
    def icon(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "icon", None))
    @strawberry.field(name="text")
    def text(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "text", None))
    is_public: bool = strawberry.field(name="isPublic", default=None)
    creator: Annotated["UserType", strawberry.lazy("config.graphql.user_types")] = strawberry.field(name="creator", default=None)
    @strawberry.field(name="documentRelationships")
    def document_relationships(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["DocumentRelationshipTypeConnection", strawberry.lazy("config.graphql.document_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "document_relationships", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="DocumentRelationshipType", )
    @strawberry.field(name="relationships")
    def relationships(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> "RelationshipTypeConnection":
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "relationships", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="RelationshipType", )
    @strawberry.field(name="annotationSet")
    def annotation_set(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET, raw_text__contains: Annotated[Optional[str], strawberry.argument(name="rawText_Contains")] = strawberry.UNSET, annotation_label_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="annotationLabelId")] = strawberry.UNSET, annotation_label__text: Annotated[Optional[str], strawberry.argument(name="annotationLabel_Text")] = strawberry.UNSET, annotation_label__text__contains: Annotated[Optional[str], strawberry.argument(name="annotationLabel_Text_Contains")] = strawberry.UNSET, annotation_label__description__contains: Annotated[Optional[str], strawberry.argument(name="annotationLabel_Description_Contains")] = strawberry.UNSET, annotation_label__label_type: Annotated[Optional[enums.AnnotationsAnnotationLabelLabelTypeChoices], strawberry.argument(name="annotationLabel_LabelType")] = strawberry.UNSET, analysis__isnull: Annotated[Optional[bool], strawberry.argument(name="analysis_Isnull")] = strawberry.UNSET, document_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="documentId")] = strawberry.UNSET, corpus_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="corpusId")] = strawberry.UNSET, structural: Annotated[Optional[bool], strawberry.argument(name="structural")] = strawberry.UNSET, uses_label_from_labelset_id: Annotated[Optional[str], strawberry.argument(name="usesLabelFromLabelsetId")] = strawberry.UNSET, created_by_analysis_ids: Annotated[Optional[str], strawberry.argument(name="createdByAnalysisIds")] = strawberry.UNSET, created_with_analyzer_id: Annotated[Optional[str], strawberry.argument(name="createdWithAnalyzerId")] = strawberry.UNSET, order_by: Annotated[Optional[str], strawberry.argument(name="orderBy", description='Ordering')] = strawberry.UNSET) -> "AnnotationTypeConnection":
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last, "raw_text__contains": raw_text__contains, "annotation_label_id": annotation_label_id, "annotation_label__text": annotation_label__text, "annotation_label__text__contains": annotation_label__text__contains, "annotation_label__description__contains": annotation_label__description__contains, "annotation_label__label_type": annotation_label__label_type, "analysis__isnull": analysis__isnull, "document_id": document_id, "corpus_id": corpus_id, "structural": structural, "uses_label_from_labelset_id": uses_label_from_labelset_id, "created_by_analysis_ids": created_by_analysis_ids, "created_with_analyzer_id": created_with_analyzer_id, "order_by": order_by})
        resolved = getattr(self, "annotation_set", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="AnnotationType", filterset_class=setup_filterset(AnnotationFilter), filter_args={"raw_text__contains": "raw_text__contains", "annotation_label_id": "annotation_label_id", "annotation_label__text": "annotation_label__text", "annotation_label__text__contains": "annotation_label__text__contains", "annotation_label__description__contains": "annotation_label__description__contains", "annotation_label__label_type": "annotation_label__label_type", "analysis__isnull": "analysis__isnull", "document_id": "document_id", "corpus_id": "corpus_id", "structural": "structural", "uses_label_from_labelset_id": "uses_label_from_labelset_id", "created_by_analysis_ids": "created_by_analysis_ids", "created_with_analyzer_id": "created_with_analyzer_id", "order_by": "order_by"}, )
    @strawberry.field(name="includedInLabelsets")
    def included_in_labelsets(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> "LabelSetTypeConnection":
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "included_in_labelsets", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="LabelSetType", )
    @strawberry.field(name="myPermissions")
    def my_permissions(self, info: strawberry.Info) -> Optional[GenericScalar]:
        kwargs = strip_unset({})
        return _resolve_AnnotationLabelType_my_permissions(self, info, **kwargs)
    @strawberry.field(name="isPublished")
    def is_published(self, info: strawberry.Info) -> Optional[bool]:
        return core_permissions.resolve_is_published(self, info)
    @strawberry.field(name="objectSharedWith")
    def object_shared_with(self, info: strawberry.Info) -> Optional[GenericScalar]:
        return core_permissions.resolve_object_shared_with(self, info)


register_type("AnnotationLabelType", AnnotationLabelType, model=AnnotationLabel)


AnnotationLabelTypeConnection = make_connection_types(AnnotationLabelType, type_name="AnnotationLabelTypeConnection", countable=True, pdf_page_aware=False)


def _resolve_LabelSetType_icon(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/annotation_types.py:1024

    Port of LabelSetType.resolve_icon
    """
    raise NotImplementedError("_resolve_LabelSetType_icon not yet ported — see manifest")


def _resolve_LabelSetType_doc_label_count(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/annotation_types.py:989

    Port of LabelSetType.resolve_doc_label_count
    """
    raise NotImplementedError("_resolve_LabelSetType_doc_label_count not yet ported — see manifest")


def _resolve_LabelSetType_span_label_count(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/annotation_types.py:996

    Port of LabelSetType.resolve_span_label_count
    """
    raise NotImplementedError("_resolve_LabelSetType_span_label_count not yet ported — see manifest")


def _resolve_LabelSetType_token_label_count(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/annotation_types.py:1002

    Port of LabelSetType.resolve_token_label_count
    """
    raise NotImplementedError("_resolve_LabelSetType_token_label_count not yet ported — see manifest")


def _resolve_LabelSetType_corpus_count(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/annotation_types.py:1011

    Port of LabelSetType.resolve_corpus_count
    """
    raise NotImplementedError("_resolve_LabelSetType_corpus_count not yet ported — see manifest")


def _resolve_LabelSetType_all_annotation_labels(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/annotation_types.py:1020

    Port of LabelSetType.resolve_all_annotation_labels
    """
    raise NotImplementedError("_resolve_LabelSetType_all_annotation_labels not yet ported — see manifest")


@strawberry.type(name="LabelSetType")
class LabelSetType(Node):
    user_lock: Optional[Annotated["UserType", strawberry.lazy("config.graphql.user_types")]] = strawberry.field(name="userLock", default=None)
    backend_lock: bool = strawberry.field(name="backendLock", default=None)
    is_public: bool = strawberry.field(name="isPublic", default=None)
    creator: Annotated["UserType", strawberry.lazy("config.graphql.user_types")] = strawberry.field(name="creator", default=None)
    created: datetime.datetime = strawberry.field(name="created", default=None)
    modified: datetime.datetime = strawberry.field(name="modified", default=None)
    @strawberry.field(name="title")
    def title(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "title", None))
    @strawberry.field(name="description")
    def description(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "description", None))
    @strawberry.field(name="icon")
    def icon(self, info: strawberry.Info) -> str:
        kwargs = strip_unset({})
        return _resolve_LabelSetType_icon(self, info, **kwargs)
    @strawberry.field(name="annotationLabels")
    def annotation_labels(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET, description__contains: Annotated[Optional[str], strawberry.argument(name="description_Contains")] = strawberry.UNSET, text: Annotated[Optional[str], strawberry.argument(name="text")] = strawberry.UNSET, text__contains: Annotated[Optional[str], strawberry.argument(name="text_Contains")] = strawberry.UNSET, label_type: Annotated[Optional[enums.AnnotationsAnnotationLabelLabelTypeChoices], strawberry.argument(name="labelType")] = strawberry.UNSET, used_in_labelset_id: Annotated[Optional[str], strawberry.argument(name="usedInLabelsetId")] = strawberry.UNSET, used_in_labelset_for_corpus_id: Annotated[Optional[str], strawberry.argument(name="usedInLabelsetForCorpusId")] = strawberry.UNSET, used_in_analysis_ids: Annotated[Optional[str], strawberry.argument(name="usedInAnalysisIds")] = strawberry.UNSET) -> Optional["AnnotationLabelTypeConnection"]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last, "description__contains": description__contains, "text": text, "text__contains": text__contains, "label_type": label_type, "used_in_labelset_id": used_in_labelset_id, "used_in_labelset_for_corpus_id": used_in_labelset_for_corpus_id, "used_in_analysis_ids": used_in_analysis_ids})
        resolved = getattr(self, "annotation_labels", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="AnnotationLabelType", filterset_class=setup_filterset(LabelFilter), filter_args={"description__contains": "description__contains", "text": "text", "text__contains": "text__contains", "label_type": "label_type", "used_in_labelset_id": "used_in_labelset_id", "used_in_labelset_for_corpus_id": "used_in_labelset_for_corpus_id", "used_in_analysis_ids": "used_in_analysis_ids"}, )
    analyzer: Optional[Annotated["AnalyzerType", strawberry.lazy("config.graphql.extract_types")]] = strawberry.field(name="analyzer", default=None)
    is_default: bool = strawberry.field(name="isDefault", default=None)
    @strawberry.field(name="usedByCorpuses")
    def used_by_corpuses(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["CorpusTypeConnection", strawberry.lazy("config.graphql.corpus_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "used_by_corpuses", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="CorpusType", )
    @strawberry.field(name="myPermissions")
    def my_permissions(self, info: strawberry.Info) -> Optional[GenericScalar]:
        return core_permissions.resolve_my_permissions(self, info)
    @strawberry.field(name="isPublished")
    def is_published(self, info: strawberry.Info) -> Optional[bool]:
        return core_permissions.resolve_is_published(self, info)
    @strawberry.field(name="objectSharedWith")
    def object_shared_with(self, info: strawberry.Info) -> Optional[GenericScalar]:
        return core_permissions.resolve_object_shared_with(self, info)
    @strawberry.field(name="docLabelCount", description='Count of document-level type labels')
    def doc_label_count(self, info: strawberry.Info) -> Optional[int]:
        kwargs = strip_unset({})
        return _resolve_LabelSetType_doc_label_count(self, info, **kwargs)
    @strawberry.field(name="spanLabelCount", description='Count of span-based labels')
    def span_label_count(self, info: strawberry.Info) -> Optional[int]:
        kwargs = strip_unset({})
        return _resolve_LabelSetType_span_label_count(self, info, **kwargs)
    @strawberry.field(name="tokenLabelCount", description='Count of token-level labels')
    def token_label_count(self, info: strawberry.Info) -> Optional[int]:
        kwargs = strip_unset({})
        return _resolve_LabelSetType_token_label_count(self, info, **kwargs)
    @strawberry.field(name="corpusCount", description='Number of corpuses using this label set')
    def corpus_count(self, info: strawberry.Info) -> Optional[int]:
        kwargs = strip_unset({})
        return _resolve_LabelSetType_corpus_count(self, info, **kwargs)
    @strawberry.field(name="allAnnotationLabels")
    def all_annotation_labels(self, info: strawberry.Info) -> Optional[list[Optional["AnnotationLabelType"]]]:
        kwargs = strip_unset({})
        return _resolve_LabelSetType_all_annotation_labels(self, info, **kwargs)


register_type("LabelSetType", LabelSetType, model=LabelSet)


LabelSetTypeConnection = make_connection_types(LabelSetType, type_name="LabelSetTypeConnection", countable=True, pdf_page_aware=False)


@strawberry.type(name="RelationshipType")
class RelationshipType(Node):
    user_lock: Optional[Annotated["UserType", strawberry.lazy("config.graphql.user_types")]] = strawberry.field(name="userLock", default=None)
    backend_lock: bool = strawberry.field(name="backendLock", default=None)
    relationship_label: Optional["AnnotationLabelType"] = strawberry.field(name="relationshipLabel", default=None)
    corpus: Optional[Annotated["CorpusType", strawberry.lazy("config.graphql.corpus_types")]] = strawberry.field(name="corpus", default=None)
    document: Optional[Annotated["DocumentType", strawberry.lazy("config.graphql.document_types")]] = strawberry.field(name="document", default=None)
    @strawberry.field(name="sourceAnnotations")
    def source_annotations(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET, raw_text__contains: Annotated[Optional[str], strawberry.argument(name="rawText_Contains")] = strawberry.UNSET, annotation_label_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="annotationLabelId")] = strawberry.UNSET, annotation_label__text: Annotated[Optional[str], strawberry.argument(name="annotationLabel_Text")] = strawberry.UNSET, annotation_label__text__contains: Annotated[Optional[str], strawberry.argument(name="annotationLabel_Text_Contains")] = strawberry.UNSET, annotation_label__description__contains: Annotated[Optional[str], strawberry.argument(name="annotationLabel_Description_Contains")] = strawberry.UNSET, annotation_label__label_type: Annotated[Optional[enums.AnnotationsAnnotationLabelLabelTypeChoices], strawberry.argument(name="annotationLabel_LabelType")] = strawberry.UNSET, analysis__isnull: Annotated[Optional[bool], strawberry.argument(name="analysis_Isnull")] = strawberry.UNSET, document_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="documentId")] = strawberry.UNSET, corpus_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="corpusId")] = strawberry.UNSET, structural: Annotated[Optional[bool], strawberry.argument(name="structural")] = strawberry.UNSET, uses_label_from_labelset_id: Annotated[Optional[str], strawberry.argument(name="usesLabelFromLabelsetId")] = strawberry.UNSET, created_by_analysis_ids: Annotated[Optional[str], strawberry.argument(name="createdByAnalysisIds")] = strawberry.UNSET, created_with_analyzer_id: Annotated[Optional[str], strawberry.argument(name="createdWithAnalyzerId")] = strawberry.UNSET, order_by: Annotated[Optional[str], strawberry.argument(name="orderBy", description='Ordering')] = strawberry.UNSET) -> "AnnotationTypeConnection":
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last, "raw_text__contains": raw_text__contains, "annotation_label_id": annotation_label_id, "annotation_label__text": annotation_label__text, "annotation_label__text__contains": annotation_label__text__contains, "annotation_label__description__contains": annotation_label__description__contains, "annotation_label__label_type": annotation_label__label_type, "analysis__isnull": analysis__isnull, "document_id": document_id, "corpus_id": corpus_id, "structural": structural, "uses_label_from_labelset_id": uses_label_from_labelset_id, "created_by_analysis_ids": created_by_analysis_ids, "created_with_analyzer_id": created_with_analyzer_id, "order_by": order_by})
        resolved = getattr(self, "source_annotations", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="AnnotationType", filterset_class=setup_filterset(AnnotationFilter), filter_args={"raw_text__contains": "raw_text__contains", "annotation_label_id": "annotation_label_id", "annotation_label__text": "annotation_label__text", "annotation_label__text__contains": "annotation_label__text__contains", "annotation_label__description__contains": "annotation_label__description__contains", "annotation_label__label_type": "annotation_label__label_type", "analysis__isnull": "analysis__isnull", "document_id": "document_id", "corpus_id": "corpus_id", "structural": "structural", "uses_label_from_labelset_id": "uses_label_from_labelset_id", "created_by_analysis_ids": "created_by_analysis_ids", "created_with_analyzer_id": "created_with_analyzer_id", "order_by": "order_by"}, )
    @strawberry.field(name="targetAnnotations")
    def target_annotations(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET, raw_text__contains: Annotated[Optional[str], strawberry.argument(name="rawText_Contains")] = strawberry.UNSET, annotation_label_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="annotationLabelId")] = strawberry.UNSET, annotation_label__text: Annotated[Optional[str], strawberry.argument(name="annotationLabel_Text")] = strawberry.UNSET, annotation_label__text__contains: Annotated[Optional[str], strawberry.argument(name="annotationLabel_Text_Contains")] = strawberry.UNSET, annotation_label__description__contains: Annotated[Optional[str], strawberry.argument(name="annotationLabel_Description_Contains")] = strawberry.UNSET, annotation_label__label_type: Annotated[Optional[enums.AnnotationsAnnotationLabelLabelTypeChoices], strawberry.argument(name="annotationLabel_LabelType")] = strawberry.UNSET, analysis__isnull: Annotated[Optional[bool], strawberry.argument(name="analysis_Isnull")] = strawberry.UNSET, document_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="documentId")] = strawberry.UNSET, corpus_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="corpusId")] = strawberry.UNSET, structural: Annotated[Optional[bool], strawberry.argument(name="structural")] = strawberry.UNSET, uses_label_from_labelset_id: Annotated[Optional[str], strawberry.argument(name="usesLabelFromLabelsetId")] = strawberry.UNSET, created_by_analysis_ids: Annotated[Optional[str], strawberry.argument(name="createdByAnalysisIds")] = strawberry.UNSET, created_with_analyzer_id: Annotated[Optional[str], strawberry.argument(name="createdWithAnalyzerId")] = strawberry.UNSET, order_by: Annotated[Optional[str], strawberry.argument(name="orderBy", description='Ordering')] = strawberry.UNSET) -> "AnnotationTypeConnection":
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last, "raw_text__contains": raw_text__contains, "annotation_label_id": annotation_label_id, "annotation_label__text": annotation_label__text, "annotation_label__text__contains": annotation_label__text__contains, "annotation_label__description__contains": annotation_label__description__contains, "annotation_label__label_type": annotation_label__label_type, "analysis__isnull": analysis__isnull, "document_id": document_id, "corpus_id": corpus_id, "structural": structural, "uses_label_from_labelset_id": uses_label_from_labelset_id, "created_by_analysis_ids": created_by_analysis_ids, "created_with_analyzer_id": created_with_analyzer_id, "order_by": order_by})
        resolved = getattr(self, "target_annotations", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="AnnotationType", filterset_class=setup_filterset(AnnotationFilter), filter_args={"raw_text__contains": "raw_text__contains", "annotation_label_id": "annotation_label_id", "annotation_label__text": "annotation_label__text", "annotation_label__text__contains": "annotation_label__text__contains", "annotation_label__description__contains": "annotation_label__description__contains", "annotation_label__label_type": "annotation_label__label_type", "analysis__isnull": "analysis__isnull", "document_id": "document_id", "corpus_id": "corpus_id", "structural": "structural", "uses_label_from_labelset_id": "uses_label_from_labelset_id", "created_by_analysis_ids": "created_by_analysis_ids", "created_with_analyzer_id": "created_with_analyzer_id", "order_by": "order_by"}, )
    analyzer: Optional[Annotated["AnalyzerType", strawberry.lazy("config.graphql.extract_types")]] = strawberry.field(name="analyzer", default=None)
    analysis: Optional[Annotated["AnalysisType", strawberry.lazy("config.graphql.extract_types")]] = strawberry.field(name="analysis", default=None)
    created_by_analysis: Optional[Annotated["AnalysisType", strawberry.lazy("config.graphql.extract_types")]] = strawberry.field(name="createdByAnalysis", description='If set, this relationship is private to the analysis that created it', default=None)
    created_by_extract: Optional[Annotated["ExtractType", strawberry.lazy("config.graphql.extract_types")]] = strawberry.field(name="createdByExtract", description='If set, this relationship is private to the extract that created it', default=None)
    structural: bool = strawberry.field(name="structural", default=None)
    is_public: bool = strawberry.field(name="isPublic", default=None)
    creator: Annotated["UserType", strawberry.lazy("config.graphql.user_types")] = strawberry.field(name="creator", default=None)
    created: datetime.datetime = strawberry.field(name="created", default=None)
    modified: datetime.datetime = strawberry.field(name="modified", default=None)
    @strawberry.field(name="assignmentSet")
    def assignment_set(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["AssignmentTypeConnection", strawberry.lazy("config.graphql.user_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "assignment_set", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="AssignmentType", )
    @strawberry.field(name="myPermissions")
    def my_permissions(self, info: strawberry.Info) -> Optional[GenericScalar]:
        return core_permissions.resolve_my_permissions(self, info)
    @strawberry.field(name="isPublished")
    def is_published(self, info: strawberry.Info) -> Optional[bool]:
        return core_permissions.resolve_is_published(self, info)
    @strawberry.field(name="objectSharedWith")
    def object_shared_with(self, info: strawberry.Info) -> Optional[GenericScalar]:
        return core_permissions.resolve_object_shared_with(self, info)


register_type("RelationshipType", RelationshipType, model=Relationship)


RelationshipTypeConnection = make_connection_types(RelationshipType, type_name="RelationshipTypeConnection", countable=True, pdf_page_aware=False)


@strawberry.type(name="CorpusReferenceType", description='Read-only view of an enrichment cross-reference.\n\nNo ``AnnotatePermissionsForReadMixin``: ``CorpusReference`` has no guardian\npermission tables — visibility derives from the parent corpus and is\nenforced by ``CorpusReferenceService`` in the resolver.')
class CorpusReferenceType(Node):
    user_lock: Optional[Annotated["UserType", strawberry.lazy("config.graphql.user_types")]] = strawberry.field(name="userLock", default=None)
    backend_lock: bool = strawberry.field(name="backendLock", default=None)
    is_public: bool = strawberry.field(name="isPublic", default=None)
    creator: Annotated["UserType", strawberry.lazy("config.graphql.user_types")] = strawberry.field(name="creator", default=None)
    created: datetime.datetime = strawberry.field(name="created", default=None)
    modified: datetime.datetime = strawberry.field(name="modified", default=None)
    corpus: Annotated["CorpusType", strawberry.lazy("config.graphql.corpus_types")] = strawberry.field(name="corpus", default=None)
    @strawberry.field(name="referenceType")
    def reference_type(self, info: strawberry.Info) -> enums.AnnotationsCorpusReferenceReferenceTypeChoices:
        return coerce_enum(enums.AnnotationsCorpusReferenceReferenceTypeChoices, getattr(self, "reference_type", None))
    source_annotation: "AnnotationType" = strawberry.field(name="sourceAnnotation", default=None)
    target_annotation: Optional["AnnotationType"] = strawberry.field(name="targetAnnotation", default=None)
    target_document: Optional[Annotated["DocumentType", strawberry.lazy("config.graphql.document_types")]] = strawberry.field(name="targetDocument", default=None)
    target_corpus: Optional[Annotated["CorpusType", strawberry.lazy("config.graphql.corpus_types")]] = strawberry.field(name="targetCorpus", default=None)
    @strawberry.field(name="canonicalKey")
    def canonical_key(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "canonical_key", None))
    normalized_data: Optional[GenericScalar] = strawberry.field(name="normalizedData", default=None)
    confidence: float = strawberry.field(name="confidence", default=None)
    @strawberry.field(name="jurisdiction")
    def jurisdiction(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "jurisdiction", None))
    @strawberry.field(name="authorityType")
    def authority_type(self, info: strawberry.Info) -> Optional[enums.AnnotationsCorpusReferenceAuthorityTypeChoices]:
        return coerce_enum(enums.AnnotationsCorpusReferenceAuthorityTypeChoices, getattr(self, "authority_type", None))
    @strawberry.field(name="detectionTier")
    def detection_tier(self, info: strawberry.Info) -> enums.AnnotationsCorpusReferenceDetectionTierChoices:
        return coerce_enum(enums.AnnotationsCorpusReferenceDetectionTierChoices, getattr(self, "detection_tier", None))
    detection_confidence: float = strawberry.field(name="detectionConfidence", default=None)
    @strawberry.field(name="resolutionStatus")
    def resolution_status(self, info: strawberry.Info) -> enums.AnnotationsCorpusReferenceResolutionStatusChoices:
        return coerce_enum(enums.AnnotationsCorpusReferenceResolutionStatusChoices, getattr(self, "resolution_status", None))
    created_by_analysis: Optional[Annotated["AnalysisType", strawberry.lazy("config.graphql.extract_types")]] = strawberry.field(name="createdByAnalysis", default=None)
    is_provisional: bool = strawberry.field(name="isProvisional", default=None)


register_type("CorpusReferenceType", CorpusReferenceType, model=CorpusReference)


CorpusReferenceTypeConnection = make_connection_types(CorpusReferenceType, type_name="CorpusReferenceTypeConnection", countable=True, pdf_page_aware=False)


def _resolve_NoteType_revisions(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/annotation_types.py:1073

    Port of NoteType.resolve_revisions
    """
    raise NotImplementedError("_resolve_NoteType_revisions not yet ported — see manifest")


def _resolve_NoteType_descendants_tree(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/annotation_types.py:1083

    Port of NoteType.resolve_descendants_tree
    """
    raise NotImplementedError("_resolve_NoteType_descendants_tree not yet ported — see manifest")


def _resolve_NoteType_full_tree(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/annotation_types.py:1108

    Port of NoteType.resolve_full_tree
    """
    raise NotImplementedError("_resolve_NoteType_full_tree not yet ported — see manifest")


def _resolve_NoteType_subtree(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/annotation_types.py:1136

    Port of NoteType.resolve_subtree
    """
    raise NotImplementedError("_resolve_NoteType_subtree not yet ported — see manifest")


def _resolve_NoteType_current_version(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/annotation_types.py:1077

    Port of NoteType.resolve_current_version
    """
    raise NotImplementedError("_resolve_NoteType_current_version not yet ported — see manifest")


def _resolve_NoteType_content_preview(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/annotation_types.py:1067

    Port of NoteType.resolve_content_preview
    """
    raise NotImplementedError("_resolve_NoteType_content_preview not yet ported — see manifest")


@strawberry.type(name="NoteType", description='GraphQL type for the Note model with tree-based functionality.')
class NoteType(Node):
    user_lock: Optional[Annotated["UserType", strawberry.lazy("config.graphql.user_types")]] = strawberry.field(name="userLock", default=None)
    backend_lock: bool = strawberry.field(name="backendLock", default=None)
    @strawberry.field(name="title")
    def title(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "title", None))
    @strawberry.field(name="content")
    def content(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "content", None))
    parent: Optional["NoteType"] = strawberry.field(name="parent", default=None)
    corpus: Optional[Annotated["CorpusType", strawberry.lazy("config.graphql.corpus_types")]] = strawberry.field(name="corpus", default=None)
    document: Annotated["DocumentType", strawberry.lazy("config.graphql.document_types")] = strawberry.field(name="document", default=None)
    annotation: Optional["AnnotationType"] = strawberry.field(name="annotation", default=None)
    is_public: bool = strawberry.field(name="isPublic", default=None)
    creator: Annotated["UserType", strawberry.lazy("config.graphql.user_types")] = strawberry.field(name="creator", default=None)
    created: datetime.datetime = strawberry.field(name="created", default=None)
    modified: datetime.datetime = strawberry.field(name="modified", default=None)
    @strawberry.field(name="children")
    def children(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> "NoteTypeConnection":
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "children", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="NoteType", )
    @strawberry.field(name="revisions", description='List of all revisions/versions of this note, ordered by version.')
    def revisions(self, info: strawberry.Info) -> Optional[list[Optional["NoteRevisionType"]]]:
        kwargs = strip_unset({})
        return _resolve_NoteType_revisions(self, info, **kwargs)
    @strawberry.field(name="myPermissions")
    def my_permissions(self, info: strawberry.Info) -> Optional[GenericScalar]:
        return core_permissions.resolve_my_permissions(self, info)
    @strawberry.field(name="isPublished")
    def is_published(self, info: strawberry.Info) -> Optional[bool]:
        return core_permissions.resolve_is_published(self, info)
    @strawberry.field(name="objectSharedWith")
    def object_shared_with(self, info: strawberry.Info) -> Optional[GenericScalar]:
        return core_permissions.resolve_object_shared_with(self, info)
    @strawberry.field(name="descendantsTree", description="List of descendant notes, each with immediate children's IDs.")
    def descendants_tree(self, info: strawberry.Info) -> Optional[list[Optional[GenericScalar]]]:
        kwargs = strip_unset({})
        return _resolve_NoteType_descendants_tree(self, info, **kwargs)
    @strawberry.field(name="fullTree", description="List of notes from the root ancestor, each with immediate children's IDs.")
    def full_tree(self, info: strawberry.Info) -> Optional[list[Optional[GenericScalar]]]:
        kwargs = strip_unset({})
        return _resolve_NoteType_full_tree(self, info, **kwargs)
    @strawberry.field(name="subtree", description='List representing the path from the root ancestor to this note and its descendants.')
    def subtree(self, info: strawberry.Info) -> Optional[list[Optional[GenericScalar]]]:
        kwargs = strip_unset({})
        return _resolve_NoteType_subtree(self, info, **kwargs)
    @strawberry.field(name="currentVersion", description='Current version number of the note')
    def current_version(self, info: strawberry.Info) -> Optional[int]:
        kwargs = strip_unset({})
        return _resolve_NoteType_current_version(self, info, **kwargs)
    @strawberry.field(name="contentPreview", description='First 400 characters of the note body for list/search previews. Resolvers may annotate the queryset with `content_preview` to avoid shipping the full body over the wire.')
    def content_preview(self, info: strawberry.Info) -> Optional[str]:
        kwargs = strip_unset({})
        return _resolve_NoteType_content_preview(self, info, **kwargs)


def _get_queryset_NoteType(queryset, info):
    """PORT: config.graphql.annotation_types.NoteType.get_queryset

    Port of NoteType.get_queryset
    """
    raise NotImplementedError("_get_queryset_NoteType not yet ported — see manifest")


register_type("NoteType", NoteType, model=Note, get_queryset=_get_queryset_NoteType)


NoteTypeConnection = make_connection_types(NoteType, type_name="NoteTypeConnection", countable=True, pdf_page_aware=False)


@strawberry.type(name="NoteRevisionType", description='GraphQL type for the NoteRevision model to expose note version history.')
class NoteRevisionType(Node):
    note: "NoteType" = strawberry.field(name="note", default=None)
    author: Optional[Annotated["UserType", strawberry.lazy("config.graphql.user_types")]] = strawberry.field(name="author", default=None)
    version: int = strawberry.field(name="version", default=None)
    @strawberry.field(name="diff")
    def diff(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "diff", None))
    @strawberry.field(name="snapshot")
    def snapshot(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "snapshot", None))
    @strawberry.field(name="checksumBase")
    def checksum_base(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "checksum_base", None))
    @strawberry.field(name="checksumFull")
    def checksum_full(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "checksum_full", None))
    created: datetime.datetime = strawberry.field(name="created", default=None)


register_type("NoteRevisionType", NoteRevisionType, model=NoteRevision)


NoteRevisionTypeConnection = make_connection_types(NoteRevisionType, type_name="NoteRevisionTypeConnection", countable=True, pdf_page_aware=False)


def _resolve_AuthorityNamespaceNode_aliases(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/annotation_types.py:479

    Port of AuthorityNamespaceNode.resolve_aliases
    """
    raise NotImplementedError("_resolve_AuthorityNamespaceNode_aliases not yet ported — see manifest")


def _resolve_AuthorityNamespaceNode_scope(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/annotation_types.py:482

    Port of AuthorityNamespaceNode.resolve_scope
    """
    raise NotImplementedError("_resolve_AuthorityNamespaceNode_scope not yet ported — see manifest")


def _resolve_AuthorityNamespaceNode_equivalence_count(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/annotation_types.py:485

    Port of AuthorityNamespaceNode.resolve_equivalence_count
    """
    raise NotImplementedError("_resolve_AuthorityNamespaceNode_equivalence_count not yet ported — see manifest")


def _resolve_AuthorityNamespaceNode_frontier_count(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/annotation_types.py:491

    Port of AuthorityNamespaceNode.resolve_frontier_count
    """
    raise NotImplementedError("_resolve_AuthorityNamespaceNode_frontier_count not yet ported — see manifest")


def _resolve_AuthorityNamespaceNode_reference_count(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/annotation_types.py:494

    Port of AuthorityNamespaceNode.resolve_reference_count
    """
    raise NotImplementedError("_resolve_AuthorityNamespaceNode_reference_count not yet ported — see manifest")


def _resolve_AuthorityNamespaceNode_effective_provider(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/annotation_types.py:499

    Port of AuthorityNamespaceNode.resolve_effective_provider
    """
    raise NotImplementedError("_resolve_AuthorityNamespaceNode_effective_provider not yet ported — see manifest")


def _resolve_AuthorityNamespaceNode_created_by_username(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/annotation_types.py:504

    Port of AuthorityNamespaceNode.resolve_created_by_username
    """
    raise NotImplementedError("_resolve_AuthorityNamespaceNode_created_by_username not yet ported — see manifest")


@strawberry.type(name="AuthorityNamespaceNode", description='One ``AuthorityNamespace`` row: a body of law (canonical-key prefix) whose\n``aliases`` drive Tier-1 citation extraction.\n\nGlobal reference data with no per-object permissions, so the connection is\n**superuser-only**: ``get_queryset`` returns nothing for everyone else and\norders by ``prefix``. The ``*_count`` and ``effective_provider`` fields are\nstring-joined to the other authority models on demand (graphene resolves\nthem only when selected, so the master list pays only for what it shows).')
class AuthorityNamespaceNode(Node):
    @strawberry.field(name="prefix")
    def prefix(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "prefix", None))
    @strawberry.field(name="displayName")
    def display_name(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "display_name", None))
    @strawberry.field(name="jurisdiction")
    def jurisdiction(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "jurisdiction", None))
    @strawberry.field(name="provider")
    def provider(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "provider", None))
    @strawberry.field(name="sourceRootUrl")
    def source_root_url(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "source_root_url", None))
    @strawberry.field(name="license")
    def license(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "license", None))
    @strawberry.field(name="baselineOrigin")
    def baseline_origin(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "baseline_origin", None))
    is_global: bool = strawberry.field(name="isGlobal", default=None)
    authority_corpus: Optional[Annotated["CorpusType", strawberry.lazy("config.graphql.corpus_types")]] = strawberry.field(name="authorityCorpus", default=None)
    created: datetime.datetime = strawberry.field(name="created", default=None)
    modified: datetime.datetime = strawberry.field(name="modified", default=None)
    @strawberry.field(name="aliases", description='Lowercased surface forms feeding extraction.')
    def aliases(self, info: strawberry.Info) -> Optional[list[Optional[str]]]:
        kwargs = strip_unset({})
        return _resolve_AuthorityNamespaceNode_aliases(self, info, **kwargs)
    @strawberry.field(name="source", description="'baseline' or 'manual' (ownership).")
    def source(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "source", None))
    @strawberry.field(name="authorityType", description='Raw authority_type value.')
    def authority_type(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "authority_type", None))
    @strawberry.field(name="scope", description="'global' or 'corpus' (derived).")
    def scope(self, info: strawberry.Info) -> Optional[str]:
        kwargs = strip_unset({})
        return _resolve_AuthorityNamespaceNode_scope(self, info, **kwargs)
    @strawberry.field(name="equivalenceCount", description='Key-equivalences whose from/to key is under this prefix.')
    def equivalence_count(self, info: strawberry.Info) -> Optional[int]:
        kwargs = strip_unset({})
        return _resolve_AuthorityNamespaceNode_equivalence_count(self, info, **kwargs)
    @strawberry.field(name="frontierCount", description='Discovery-queue rows for this authority.')
    def frontier_count(self, info: strawberry.Info) -> Optional[int]:
        kwargs = strip_unset({})
        return _resolve_AuthorityNamespaceNode_frontier_count(self, info, **kwargs)
    @strawberry.field(name="referenceCount", description='CorpusReferences whose canonical_key is under this prefix.')
    def reference_count(self, info: strawberry.Info) -> Optional[int]:
        kwargs = strip_unset({})
        return _resolve_AuthorityNamespaceNode_reference_count(self, info, **kwargs)
    @strawberry.field(name="effectiveProvider", description="Registry class-name that would actually handle this prefix (by can_handle/priority) — contrast with the advisory 'provider' column. Null when no provider can handle it.")
    def effective_provider(self, info: strawberry.Info) -> Optional[str]:
        kwargs = strip_unset({})
        return _resolve_AuthorityNamespaceNode_effective_provider(self, info, **kwargs)
    @strawberry.field(name="createdByUsername", description='Curator who created/edited this manual row (else null).')
    def created_by_username(self, info: strawberry.Info) -> Optional[str]:
        kwargs = strip_unset({})
        return _resolve_AuthorityNamespaceNode_created_by_username(self, info, **kwargs)


def _get_queryset_AuthorityNamespaceNode(queryset, info):
    """PORT: config.graphql.annotation_types.AuthorityNamespaceNode.get_queryset

    Port of AuthorityNamespaceNode.get_queryset
    """
    raise NotImplementedError("_get_queryset_AuthorityNamespaceNode not yet ported — see manifest")


register_type("AuthorityNamespaceNode", AuthorityNamespaceNode, model=AuthorityNamespace, get_queryset=_get_queryset_AuthorityNamespaceNode)


AuthorityNamespaceNodeConnection = make_connection_types(AuthorityNamespaceNode, type_name="AuthorityNamespaceNodeConnection", countable=True, pdf_page_aware=False)


def _resolve_AuthorityFrontierNode_ingestable(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/annotation_types.py:302

    Port of AuthorityFrontierNode.resolve_ingestable
    """
    raise NotImplementedError("_resolve_AuthorityFrontierNode_ingestable not yet ported — see manifest")


def _resolve_AuthorityFrontierNode_predicted_provider(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/annotation_types.py:305

    Port of AuthorityFrontierNode.resolve_predicted_provider
    """
    raise NotImplementedError("_resolve_AuthorityFrontierNode_predicted_provider not yet ported — see manifest")


@strawberry.type(name="AuthorityFrontierNode", description="One ``AuthorityFrontier`` row: the discovery/ingestion state of a wanted\nsection-root canonical key (e.g. ``usc-15:78j``), aggregated instance-wide\nacross all corpora.\n\n``AuthorityFrontier`` is a system-managed global queue with no per-object\npermissions, so the connection is **superuser-only**: ``get_queryset``\nreturns nothing for everyone else and sets the backlog-first default order\n(``-mention_count``, matching the model's index).")
class AuthorityFrontierNode(Node):
    @strawberry.field(name="canonicalKey")
    def canonical_key(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "canonical_key", None))
    @strawberry.field(name="authority")
    def authority(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "authority", None))
    @strawberry.field(name="jurisdiction")
    def jurisdiction(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "jurisdiction", None))
    @strawberry.field(name="authorityType")
    def authority_type(self, info: strawberry.Info) -> Optional[enums.AnnotationsAuthorityFrontierAuthorityTypeChoices]:
        return coerce_enum(enums.AnnotationsAuthorityFrontierAuthorityTypeChoices, getattr(self, "authority_type", None))
    mention_count: int = strawberry.field(name="mentionCount", default=None)
    distinct_corpus_count: int = strawberry.field(name="distinctCorpusCount", default=None)
    @strawberry.field(name="discoveryState")
    def discovery_state(self, info: strawberry.Info) -> enums.AnnotationsAuthorityFrontierDiscoveryStateChoices:
        return coerce_enum(enums.AnnotationsAuthorityFrontierDiscoveryStateChoices, getattr(self, "discovery_state", None))
    depth: int = strawberry.field(name="depth", default=None)
    @strawberry.field(name="provider")
    def provider(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "provider", None))
    @strawberry.field(name="lastError")
    def last_error(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "last_error", None))
    last_attempt: Optional[datetime.datetime] = strawberry.field(name="lastAttempt", default=None)
    created: datetime.datetime = strawberry.field(name="created", default=None)
    modified: datetime.datetime = strawberry.field(name="modified", default=None)
    candidate_sources: Optional[GenericScalar] = strawberry.field(name="candidateSources", description='Per-corpus demand breakdown: [{corpus_id, mention_count, top_detection_tier}].', default=None)
    ingested_document: Optional[Annotated["DocumentType", strawberry.lazy("config.graphql.document_types")]] = strawberry.field(name="ingestedDocument", description='The Document imported for this key once ingested (else null).', default=None)
    @strawberry.field(name="ingestable", description="True if a source provider can_handle this key directly or via an AuthorityKeyEquivalence bridge (i.e. discovery could ingest it). False keys would record 'unsupported' if run.")
    def ingestable(self, info: strawberry.Info) -> Optional[bool]:
        kwargs = strip_unset({})
        return _resolve_AuthorityFrontierNode_ingestable(self, info, **kwargs)
    @strawberry.field(name="predictedProvider", description='Registry class name of the provider that would handle this key, or null when none can.')
    def predicted_provider(self, info: strawberry.Info) -> Optional[str]:
        kwargs = strip_unset({})
        return _resolve_AuthorityFrontierNode_predicted_provider(self, info, **kwargs)


def _get_queryset_AuthorityFrontierNode(queryset, info):
    """PORT: config.graphql.annotation_types.AuthorityFrontierNode.get_queryset

    Port of AuthorityFrontierNode.get_queryset
    """
    raise NotImplementedError("_get_queryset_AuthorityFrontierNode not yet ported — see manifest")


register_type("AuthorityFrontierNode", AuthorityFrontierNode, model=AuthorityFrontier, get_queryset=_get_queryset_AuthorityFrontierNode)


AuthorityFrontierNodeConnection = make_connection_types(AuthorityFrontierNode, type_name="AuthorityFrontierNodeConnection", countable=True, pdf_page_aware=False)


def _resolve_AuthorityKeyEquivalenceNode_editable(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/annotation_types.py:374

    Port of AuthorityKeyEquivalenceNode.resolve_editable
    """
    raise NotImplementedError("_resolve_AuthorityKeyEquivalenceNode_editable not yet ported — see manifest")


def _resolve_AuthorityKeyEquivalenceNode_created_by_username(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/annotation_types.py:377

    Port of AuthorityKeyEquivalenceNode.resolve_created_by_username
    """
    raise NotImplementedError("_resolve_AuthorityKeyEquivalenceNode_created_by_username not yet ported — see manifest")


@strawberry.type(name="AuthorityKeyEquivalenceNode", description='One ``AuthorityKeyEquivalence`` row (canonical-key synonym) for the\nruntime authority-mappings admin panel.\n\nGlobal system data with no per-object permissions, so the connection is\n**superuser-only**: ``get_queryset`` returns nothing for everyone else and\nsets the default order (most-recently-modified first). ``editable`` is True\nonly for ``source="manual"`` rows — loader/importer-owned rows\n(``baseline`` / ``popular_name`` / ``uslm``) are read-only.')
class AuthorityKeyEquivalenceNode(Node):
    @strawberry.field(name="fromKey")
    def from_key(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "from_key", None))
    @strawberry.field(name="toKey")
    def to_key(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "to_key", None))
    @strawberry.field(name="source")
    def source(self, info: strawberry.Info) -> enums.AnnotationsAuthorityKeyEquivalenceSourceChoices:
        return coerce_enum(enums.AnnotationsAuthorityKeyEquivalenceSourceChoices, getattr(self, "source", None))
    confidence: float = strawberry.field(name="confidence", default=None)
    @strawberry.field(name="note")
    def note(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "note", None))
    created: datetime.datetime = strawberry.field(name="created", default=None)
    modified: datetime.datetime = strawberry.field(name="modified", default=None)
    @strawberry.field(name="editable", description='True iff this is a manual row the curator may edit/delete.')
    def editable(self, info: strawberry.Info) -> Optional[bool]:
        kwargs = strip_unset({})
        return _resolve_AuthorityKeyEquivalenceNode_editable(self, info, **kwargs)
    @strawberry.field(name="createdByUsername", description='Username of the curator who created this manual row (else null).')
    def created_by_username(self, info: strawberry.Info) -> Optional[str]:
        kwargs = strip_unset({})
        return _resolve_AuthorityKeyEquivalenceNode_created_by_username(self, info, **kwargs)


def _get_queryset_AuthorityKeyEquivalenceNode(queryset, info):
    """PORT: config.graphql.annotation_types.AuthorityKeyEquivalenceNode.get_queryset

    Port of AuthorityKeyEquivalenceNode.get_queryset
    """
    raise NotImplementedError("_get_queryset_AuthorityKeyEquivalenceNode not yet ported — see manifest")


register_type("AuthorityKeyEquivalenceNode", AuthorityKeyEquivalenceNode, model=AuthorityKeyEquivalence, get_queryset=_get_queryset_AuthorityKeyEquivalenceNode)


AuthorityKeyEquivalenceNodeConnection = make_connection_types(AuthorityKeyEquivalenceNode, type_name="AuthorityKeyEquivalenceNodeConnection", countable=True, pdf_page_aware=False)


@strawberry.type(name="GovernanceGraphType", description='The corpus-scoped reference web in node-link form.\n\nBuilt by ``GovernanceGraphService`` from corpus-as-gate ``CorpusReference``\nrows + permission-filtered ``DocumentRelationship`` rows, with every\nsurfaced document independently READ-checked (invisible targets degrade to\nexternal ghost nodes). Counts describe the full visible graph; the\nnode/edge lists may be degree-capped (``truncated``).')
class GovernanceGraphType:
    corpora: list["GovernanceGraphCorpusType"] = strawberry.field(name="corpora", default=None)
    nodes: list["GovernanceGraphNodeType"] = strawberry.field(name="nodes", default=None)
    edges: list["GovernanceGraphEdgeType"] = strawberry.field(name="edges", default=None)
    document_count: int = strawberry.field(name="documentCount", description='Distinct visible document nodes (pre-cap).', default=None)
    external_key_count: int = strawberry.field(name="externalKeyCount", description='Distinct external ghost nodes (pre-cap).', default=None)
    edge_count: int = strawberry.field(name="edgeCount", description='Distinct edges in the full graph (pre-cap).', default=None)
    mention_count: int = strawberry.field(name="mentionCount", description='Total reference mentions across all edges.', default=None)
    truncated: bool = strawberry.field(name="truncated", description='True when nodes/edges were dropped to honor the node cap.', default=None)


register_type("GovernanceGraphType", GovernanceGraphType, model=None)


@strawberry.type(name="GovernanceGraphCorpusType", description='A corpus participating in the governance graph (filing or authority).')
class GovernanceGraphCorpusType:
    id: strawberry.ID = strawberry.field(name="id", description='Global CorpusType id.', default=None)
    title: Optional[str] = strawberry.field(name="title", default=None)
    kind: str = strawberry.field(name="kind", description='"filing" or "authority" (cited body of law).', default=None)


register_type("GovernanceGraphCorpusType", GovernanceGraphCorpusType, model=None)


@strawberry.type(name="GovernanceGraphNodeType", description='One governance-graph node: a document or an external-citation ghost.')
class GovernanceGraphNodeType:
    id: str = strawberry.field(name="id", description='Node id: the global DocumentType id for document nodes, or "key:<canonical_key>" for external ghost nodes.', default=None)
    document_id: Optional[strawberry.ID] = strawberry.field(name="documentId", description='Global DocumentType id (null for external ghost nodes).', default=None)
    title: Optional[str] = strawberry.field(name="title", description='Document title, or the canonical key for ghost nodes.', default=None)
    kind: str = strawberry.field(name="kind", description='"primary", "exhibit", "statute" or "external".', default=None)
    corpus_id: Optional[strawberry.ID] = strawberry.field(name="corpusId", description="Global CorpusType id of the node's corpus (null for ghosts).", default=None)
    authority: Optional[str] = strawberry.field(name="authority", description='Body-of-law key prefix (e.g. "dgcl") for statute/ghost nodes.', default=None)
    jurisdiction: Optional[str] = strawberry.field(name="jurisdiction", description='Jurisdiction code, e.g. "us-de", "us-federal" (null if unknown).', default=None)
    authority_type: Optional[str] = strawberry.field(name="authorityType", description='Authority type: "statute", "regulation", etc. (null if unknown).', default=None)
    discovery_state: Optional[str] = strawberry.field(name="discoveryState", description='Authority-frontier crawl status for ghost nodes: "queued", "in_progress", "ingested", "failed", "unsupported", "blocked_license", "blocked_domain", "unlocated", "pending_approval", "deferred_cap" — or null when not tracked.', default=None)
    degree: int = strawberry.field(name="degree", description='Summed mention weight of edges touching the node.', default=None)


register_type("GovernanceGraphNodeType", GovernanceGraphNodeType, model=None)


@strawberry.type(name="GovernanceGraphEdgeType", description='One weighted reference edge between two governance-graph nodes.')
class GovernanceGraphEdgeType:
    source: str = strawberry.field(name="source", description='Source node id.', default=None)
    target: str = strawberry.field(name="target", description='Target node id.', default=None)
    edge_type: str = strawberry.field(name="edgeType", description='"LAW", "LAW_EXTERNAL" or "DOCUMENT".', default=None)
    weight: int = strawberry.field(name="weight", description='Mention count.', default=None)


register_type("GovernanceGraphEdgeType", GovernanceGraphEdgeType, model=None)


@strawberry.type(name="WantedAuthorityType", description="One authority worth bootstrapping, ranked by citation demand.\n\nAggregated by ``CorpusReferenceService.wanted_authorities`` from EXTERNAL\nlaw references visible to the requesting user — the actionable backlog\nbehind the governance graph's ghost nodes.")
class WantedAuthorityType:
    authority: str = strawberry.field(name="authority", description='Authority prefix, e.g. "dgcl".', default=None)
    mention_count: int = strawberry.field(name="mentionCount", description='Total EXTERNAL mentions for this authority.', default=None)
    key_count: int = strawberry.field(name="keyCount", description='Distinct section-root keys cited.', default=None)
    corpus_count: int = strawberry.field(name="corpusCount", description='Distinct corpora with unresolved citations.', default=None)
    top_keys: list["WantedAuthorityKeyType"] = strawberry.field(name="topKeys", description='Most-cited missing keys (capped server-side).', default=None)


register_type("WantedAuthorityType", WantedAuthorityType, model=None)


@strawberry.type(name="WantedAuthorityKeyType", description='One missing canonical key (rolled up to its section root).')
class WantedAuthorityKeyType:
    canonical_key: str = strawberry.field(name="canonicalKey", description='Section-root canonical key, e.g. "dgcl:145".', default=None)
    mention_count: int = strawberry.field(name="mentionCount", description='EXTERNAL mentions citing this key.', default=None)
    corpus_count: int = strawberry.field(name="corpusCount", description='Distinct corpora citing this key.', default=None)


register_type("WantedAuthorityKeyType", WantedAuthorityKeyType, model=None)


@strawberry.type(name="AuthorityFrontierStatsType", description="Facet-aware summary counts for the authority-sources monitor's chips.\n\nCounts honour the non-state facets (jurisdiction / authority_type /\nprovider / search) but NOT the state filter, so the chips always show the\nfull state breakdown for the current facet selection.")
class AuthorityFrontierStatsType:
    total_count: int = strawberry.field(name="totalCount", description='Total frontier rows matching the non-state facets.', default=None)
    by_state: list["AuthorityFrontierStateCountType"] = strawberry.field(name="byState", description='Row count per discovery_state (only non-empty states).', default=None)


register_type("AuthorityFrontierStatsType", AuthorityFrontierStatsType, model=None)


@strawberry.type(name="AuthorityFrontierStateCountType", description='One ``discovery_state`` and how many frontier rows are in it.')
class AuthorityFrontierStateCountType:
    state: str = strawberry.field(name="state", description='discovery_state value.', default=None)
    count: int = strawberry.field(name="count", default=None)


register_type("AuthorityFrontierStateCountType", AuthorityFrontierStateCountType, model=None)


@strawberry.type(name="AuthorityMappingStatsType", description='Per-``source`` summary counts for the authority-mappings panel chips.\n\nHonours the ``search`` facet but NOT a source filter, so the chips always\nshow the full source breakdown for the current search.')
class AuthorityMappingStatsType:
    total_count: int = strawberry.field(name="totalCount", description='Total equivalence rows matching the search.', default=None)
    by_source: list["AuthorityMappingSourceCountType"] = strawberry.field(name="bySource", description='Row count per source (only non-empty sources).', default=None)


register_type("AuthorityMappingStatsType", AuthorityMappingStatsType, model=None)


@strawberry.type(name="AuthorityMappingSourceCountType", description='One ``source`` value and how many equivalence rows carry it.')
class AuthorityMappingSourceCountType:
    source: str = strawberry.field(name="source", description='source value.', default=None)
    count: int = strawberry.field(name="count", default=None)


register_type("AuthorityMappingSourceCountType", AuthorityMappingSourceCountType, model=None)


@strawberry.type(name="AuthorityNamespaceStatsType", description="Faceted summary counts for the registry panel's chips.\n\nHonours ``search`` but not the facet selects, so chips show the full\nbreakdown for the current search (mirrors ``AuthorityMappingStatsType``).")
class AuthorityNamespaceStatsType:
    total_count: int = strawberry.field(name="totalCount", default=None)
    by_jurisdiction: list["AuthorityNamespaceFacetCountType"] = strawberry.field(name="byJurisdiction", default=None)
    by_authority_type: list["AuthorityNamespaceFacetCountType"] = strawberry.field(name="byAuthorityType", default=None)
    by_scope: list["AuthorityNamespaceFacetCountType"] = strawberry.field(name="byScope", default=None)


register_type("AuthorityNamespaceStatsType", AuthorityNamespaceStatsType, model=None)


@strawberry.type(name="AuthorityNamespaceFacetCountType", description='One facet value (jurisdiction / authority_type / scope) and its row count.')
class AuthorityNamespaceFacetCountType:
    value: Optional[str] = strawberry.field(name="value", description="The facet value (null collapses to '').", default=None)
    count: int = strawberry.field(name="count", default=None)


register_type("AuthorityNamespaceFacetCountType", AuthorityNamespaceFacetCountType, model=None)


@strawberry.type(name="AuthorityDetailType", description="Everything about one body of law, string-joined across the authority models.\n\nThe console's single-authority view. Superuser-gated at the service layer\n(``AuthorityNamespaceService.detail``); the nested node types are returned as\npre-fetched instances, so their own connection gates are not re-applied (the\nservice already enforced access).")
class AuthorityDetailType:
    namespace: "AuthorityNamespaceNode" = strawberry.field(name="namespace", default=None)
    equivalences_out: list["AuthorityKeyEquivalenceNode"] = strawberry.field(name="equivalencesOut", description='Equivalences FROM a key under this prefix.', default=None)
    equivalences_in: list["AuthorityKeyEquivalenceNode"] = strawberry.field(name="equivalencesIn", description='Equivalences TO a key under this prefix.', default=None)
    frontier_rows: list["AuthorityFrontierNode"] = strawberry.field(name="frontierRows", default=None)
    frontier_state_counts: list["AuthorityFrontierStateCountType"] = strawberry.field(name="frontierStateCounts", default=None)
    reference_total: int = strawberry.field(name="referenceTotal", default=None)
    reference_status_counts: list["AuthorityReferenceStatusCountType"] = strawberry.field(name="referenceStatusCounts", default=None)
    reference_sample: list["CorpusReferenceType"] = strawberry.field(name="referenceSample", description='Most-recent references under this prefix (capped).', default=None)
    effective_provider: Optional[str] = strawberry.field(name="effectiveProvider", default=None)


register_type("AuthorityDetailType", AuthorityDetailType, model=None)


@strawberry.type(name="AuthorityReferenceStatusCountType", description='One ``resolution_status`` and how many references under a prefix carry it.')
class AuthorityReferenceStatusCountType:
    status: str = strawberry.field(name="status", default=None)
    count: int = strawberry.field(name="count", default=None)


register_type("AuthorityReferenceStatusCountType", AuthorityReferenceStatusCountType, model=None)


@strawberry.type(name="AuthoritySourceProviderType", description='One registered authority source provider (a "scraper").\n\nThe auto-discovered provider classes (US Code / eCFR / Federal Register /\nagentic web locator) surfaced read-only for the console\'s Scrapers tab —\nthey have no DB row, so this is a registry projection. ``has_credentials``\nreflects whether the encrypted-secrets vault holds anything for this\nprovider\'s class path (credentials are edited via the existing\n``updateComponentSecrets`` mutation, not here).')
class AuthoritySourceProviderType:
    name: str = strawberry.field(name="name", description='Registry class name.', default=None)
    class_name: Optional[str] = strawberry.field(name="className", description='Full module.ClassName path.', default=None)
    title: Optional[str] = strawberry.field(name="title", default=None)
    supported_prefixes: list[Optional[str]] = strawberry.field(name="supportedPrefixes", default=None)
    license: Optional[str] = strawberry.field(name="license", default=None)
    priority: Optional[int] = strawberry.field(name="priority", default=None)
    requires_approval: bool = strawberry.field(name="requiresApproval", default=None)
    enabled: bool = strawberry.field(name="enabled", default=None)
    has_credentials: bool = strawberry.field(name="hasCredentials", default=None)


register_type("AuthoritySourceProviderType", AuthoritySourceProviderType, model=None)


def q_authority_frontier(info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET, jurisdiction: Annotated[Optional[str], strawberry.argument(name="jurisdiction")] = strawberry.UNSET, provider: Annotated[Optional[str], strawberry.argument(name="provider")] = strawberry.UNSET, authority: Annotated[Optional[str], strawberry.argument(name="authority")] = strawberry.UNSET, discovery_state: Annotated[Optional[str], strawberry.argument(name="discoveryState")] = strawberry.UNSET, authority_type: Annotated[Optional[str], strawberry.argument(name="authorityType")] = strawberry.UNSET, search: Annotated[Optional[str], strawberry.argument(name="search")] = strawberry.UNSET) -> Optional["AuthorityFrontierNodeConnection"]:
    kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last, "jurisdiction": jurisdiction, "provider": provider, "authority": authority, "discovery_state": discovery_state, "authority_type": authority_type, "search": search})
    resolved = None
    return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="AuthorityFrontierNode", default_manager=AuthorityFrontier._default_manager, filterset_class=setup_filterset(AuthorityFrontierFilter), filter_args={"jurisdiction": "jurisdiction", "provider": "provider", "authority": "authority", "discovery_state": "discovery_state", "authority_type": "authority_type", "search": "search"}, )


def q_authority_key_equivalences(info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET, source: Annotated[Optional[str], strawberry.argument(name="source")] = strawberry.UNSET, search: Annotated[Optional[str], strawberry.argument(name="search")] = strawberry.UNSET) -> Optional["AuthorityKeyEquivalenceNodeConnection"]:
    kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last, "source": source, "search": search})
    resolved = None
    return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="AuthorityKeyEquivalenceNode", default_manager=AuthorityKeyEquivalence._default_manager, filterset_class=setup_filterset(AuthorityKeyEquivalenceFilter), filter_args={"source": "source", "search": "search"}, )


def q_authority_namespaces(info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET, jurisdiction: Annotated[Optional[str], strawberry.argument(name="jurisdiction")] = strawberry.UNSET, authority_type: Annotated[Optional[str], strawberry.argument(name="authorityType")] = strawberry.UNSET, scope: Annotated[Optional[str], strawberry.argument(name="scope")] = strawberry.UNSET, search: Annotated[Optional[str], strawberry.argument(name="search")] = strawberry.UNSET) -> Optional["AuthorityNamespaceNodeConnection"]:
    kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last, "jurisdiction": jurisdiction, "authority_type": authority_type, "scope": scope, "search": search})
    resolved = None
    return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="AuthorityNamespaceNode", default_manager=AuthorityNamespace._default_manager, filterset_class=setup_filterset(AuthorityNamespaceFilter), filter_args={"jurisdiction": "jurisdiction", "authority_type": "authority_type", "scope": "scope", "search": "search"}, )



QUERY_FIELDS = {
    "authority_frontier": strawberry.field(resolver=q_authority_frontier, name="authorityFrontier", description="Global authority-source discovery queue (AuthorityFrontier): the crawl/ingestion state of every wanted section-root key across all corpora, ranked by citation demand. SUPERUSER-ONLY (empty otherwise) — gating + default order live on the node's get_queryset."),
    "authority_key_equivalences": strawberry.field(resolver=q_authority_key_equivalences, name="authorityKeyEquivalences", description="Runtime authority key-equivalence registry (AuthorityKeyEquivalence): act-section ↔ USC/CFR codification synonyms used to bridge citations across namespaces. SUPERUSER-ONLY (empty otherwise) — gating + default order live on the node's get_queryset."),
    "authority_namespaces": strawberry.field(resolver=q_authority_namespaces, name="authorityNamespaces", description="The registry of bodies of law (AuthorityNamespace): one row per canonical-key prefix (e.g. 'usc-15', 'dgcl') whose aliases drive Tier-1 citation extraction. SUPERUSER-ONLY (empty otherwise) — gating + default order live on the node's get_queryset."),
}
