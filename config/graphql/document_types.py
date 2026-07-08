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
from opencontractserver.corpuses.models import CorpusActionExecution
from opencontractserver.documents.models import Document
from opencontractserver.documents.models import DocumentAnalysisRow
from opencontractserver.documents.models import DocumentPath
from opencontractserver.documents.models import DocumentRelationship
from opencontractserver.documents.models import DocumentSummaryRevision
from opencontractserver.documents.models import IngestionSource


def _resolve_DocumentType_icon(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/optimized_file_resolvers.py:38

    Port of DocumentType.resolve_icon
    """
    raise NotImplementedError("_resolve_DocumentType_icon not yet ported — see manifest")


def _resolve_DocumentType_pdf_file(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/optimized_file_resolvers.py:38

    Port of DocumentType.resolve_pdf_file
    """
    raise NotImplementedError("_resolve_DocumentType_pdf_file not yet ported — see manifest")


def _resolve_DocumentType_txt_extract_file(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/optimized_file_resolvers.py:38

    Port of DocumentType.resolve_txt_extract_file
    """
    raise NotImplementedError("_resolve_DocumentType_txt_extract_file not yet ported — see manifest")


def _resolve_DocumentType_md_summary_file(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/optimized_file_resolvers.py:38

    Port of DocumentType.resolve_md_summary_file
    """
    raise NotImplementedError("_resolve_DocumentType_md_summary_file not yet ported — see manifest")


def _resolve_DocumentType_pawls_parse_file(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/optimized_file_resolvers.py:38

    Port of DocumentType.resolve_pawls_parse_file
    """
    raise NotImplementedError("_resolve_DocumentType_pawls_parse_file not yet ported — see manifest")


def _resolve_DocumentType_processing_status(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/document_types.py:1032

    Port of DocumentType.resolve_processing_status
    """
    raise NotImplementedError("_resolve_DocumentType_processing_status not yet ported — see manifest")


def _resolve_DocumentType_processing_error(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/document_types.py:1042

    Port of DocumentType.resolve_processing_error
    """
    raise NotImplementedError("_resolve_DocumentType_processing_error not yet ported — see manifest")


def _resolve_DocumentType_summary_revisions(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/document_types.py:583

    Port of DocumentType.resolve_summary_revisions
    """
    raise NotImplementedError("_resolve_DocumentType_summary_revisions not yet ported — see manifest")


def _resolve_DocumentType_doc_annotations(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/custom_resolvers.py:83

    Port of DocumentType.resolve_doc_annotations
    """
    raise NotImplementedError("_resolve_DocumentType_doc_annotations not yet ported — see manifest")


def _resolve_DocumentType_doc_type_labels(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/document_types.py:303

    Port of DocumentType.resolve_doc_type_labels
    """
    raise NotImplementedError("_resolve_DocumentType_doc_type_labels not yet ported — see manifest")


def _resolve_DocumentType_all_structural_annotations(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/document_types.py:334

    Port of DocumentType.resolve_all_structural_annotations
    """
    raise NotImplementedError("_resolve_DocumentType_all_structural_annotations not yet ported — see manifest")


def _resolve_DocumentType_all_annotations(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/document_types.py:355

    Port of DocumentType.resolve_all_annotations
    """
    raise NotImplementedError("_resolve_DocumentType_all_annotations not yet ported — see manifest")


def _resolve_DocumentType_all_relationships(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/document_types.py:384

    Port of DocumentType.resolve_all_relationships
    """
    raise NotImplementedError("_resolve_DocumentType_all_relationships not yet ported — see manifest")


def _resolve_DocumentType_all_structural_relationships(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/document_types.py:424

    Port of DocumentType.resolve_all_structural_relationships
    """
    raise NotImplementedError("_resolve_DocumentType_all_structural_relationships not yet ported — see manifest")


def _resolve_DocumentType_all_doc_relationships(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/document_types.py:505

    Port of DocumentType.resolve_all_doc_relationships
    """
    raise NotImplementedError("_resolve_DocumentType_all_doc_relationships not yet ported — see manifest")


def _resolve_DocumentType_doc_relationship_count(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/document_types.py:470

    Port of DocumentType.resolve_doc_relationship_count
    """
    raise NotImplementedError("_resolve_DocumentType_doc_relationship_count not yet ported — see manifest")


def _resolve_DocumentType_all_notes(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/document_types.py:545

    Port of DocumentType.resolve_all_notes
    """
    raise NotImplementedError("_resolve_DocumentType_all_notes not yet ported — see manifest")


def _resolve_DocumentType_current_summary_version(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/document_types.py:602

    Port of DocumentType.resolve_current_summary_version
    """
    raise NotImplementedError("_resolve_DocumentType_current_summary_version not yet ported — see manifest")


def _resolve_DocumentType_summary_content(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/document_types.py:627

    Port of DocumentType.resolve_summary_content
    """
    raise NotImplementedError("_resolve_DocumentType_summary_content not yet ported — see manifest")


def _resolve_DocumentType_version_number(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/document_types.py:694

    Port of DocumentType.resolve_version_number
    """
    raise NotImplementedError("_resolve_DocumentType_version_number not yet ported — see manifest")


def _resolve_DocumentType_has_version_history(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/document_types.py:703

    Port of DocumentType.resolve_has_version_history
    """
    raise NotImplementedError("_resolve_DocumentType_has_version_history not yet ported — see manifest")


def _resolve_DocumentType_version_count(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/document_types.py:712

    Port of DocumentType.resolve_version_count
    """
    raise NotImplementedError("_resolve_DocumentType_version_count not yet ported — see manifest")


def _resolve_DocumentType_is_latest_version(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/document_types.py:743

    Port of DocumentType.resolve_is_latest_version
    """
    raise NotImplementedError("_resolve_DocumentType_is_latest_version not yet ported — see manifest")


def _resolve_DocumentType_last_modified(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/document_types.py:747

    Port of DocumentType.resolve_last_modified
    """
    raise NotImplementedError("_resolve_DocumentType_last_modified not yet ported — see manifest")


def _resolve_DocumentType_version_history(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/document_types.py:756

    Port of DocumentType.resolve_version_history
    """
    raise NotImplementedError("_resolve_DocumentType_version_history not yet ported — see manifest")


def _resolve_DocumentType_path_history(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/document_types.py:819

    Port of DocumentType.resolve_path_history
    """
    raise NotImplementedError("_resolve_DocumentType_path_history not yet ported — see manifest")


def _resolve_DocumentType_corpus_versions(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/document_types.py:884

    Port of DocumentType.resolve_corpus_versions
    """
    raise NotImplementedError("_resolve_DocumentType_corpus_versions not yet ported — see manifest")


def _resolve_DocumentType_can_restore(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/document_types.py:972

    Port of DocumentType.resolve_can_restore
    """
    raise NotImplementedError("_resolve_DocumentType_can_restore not yet ported — see manifest")


def _resolve_DocumentType_can_view_history(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/document_types.py:1001

    Port of DocumentType.resolve_can_view_history
    """
    raise NotImplementedError("_resolve_DocumentType_can_view_history not yet ported — see manifest")


def _resolve_DocumentType_can_retry(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/document_types.py:1048

    Port of DocumentType.resolve_can_retry
    """
    raise NotImplementedError("_resolve_DocumentType_can_retry not yet ported — see manifest")


def _resolve_DocumentType_page_annotations(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/document_types.py:1100

    Port of DocumentType.resolve_page_annotations
    """
    raise NotImplementedError("_resolve_DocumentType_page_annotations not yet ported — see manifest")


def _resolve_DocumentType_page_relationships(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/document_types.py:1145

    Port of DocumentType.resolve_page_relationships
    """
    raise NotImplementedError("_resolve_DocumentType_page_relationships not yet ported — see manifest")


def _resolve_DocumentType_relationship_summary(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/document_types.py:1195

    Port of DocumentType.resolve_relationship_summary
    """
    raise NotImplementedError("_resolve_DocumentType_relationship_summary not yet ported — see manifest")


def _resolve_DocumentType_extract_annotation_summary(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/document_types.py:1206

    Port of DocumentType.resolve_extract_annotation_summary
    """
    raise NotImplementedError("_resolve_DocumentType_extract_annotation_summary not yet ported — see manifest")


def _resolve_DocumentType_folder_in_corpus(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/document_types.py:1224

    Port of DocumentType.resolve_folder_in_corpus
    """
    raise NotImplementedError("_resolve_DocumentType_folder_in_corpus not yet ported — see manifest")


@strawberry.type(name="DocumentType")
class DocumentType(Node):
    parent: Optional["DocumentType"] = strawberry.field(name="parent", default=None)
    user_lock: Optional[Annotated["UserType", strawberry.lazy("config.graphql.user_types")]] = strawberry.field(name="userLock", default=None)
    backend_lock: bool = strawberry.field(name="backendLock", default=None)
    is_public: bool = strawberry.field(name="isPublic", default=None)
    creator: Annotated["UserType", strawberry.lazy("config.graphql.user_types")] = strawberry.field(name="creator", default=None)
    created: datetime.datetime = strawberry.field(name="created", default=None)
    modified: datetime.datetime = strawberry.field(name="modified", default=None)
    @strawberry.field(name="title")
    def title(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "title", None))
    @strawberry.field(name="description")
    def description(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "description", None))
    @strawberry.field(name="slug", description='Case-sensitive slug unique per creator. Allowed: A-Z, a-z, 0-9, hyphen (-).')
    def slug(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "slug", None))
    custom_meta: Optional[JSONString] = strawberry.field(name="customMeta", default=None)
    @strawberry.field(name="fileType")
    def file_type(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "file_type", None))
    @strawberry.field(name="icon")
    def icon(self, info: strawberry.Info) -> str:
        kwargs = strip_unset({})
        return _resolve_DocumentType_icon(self, info, **kwargs)
    @strawberry.field(name="pdfFile")
    def pdf_file(self, info: strawberry.Info) -> Optional[str]:
        kwargs = strip_unset({})
        return _resolve_DocumentType_pdf_file(self, info, **kwargs)
    @strawberry.field(name="txtExtractFile")
    def txt_extract_file(self, info: strawberry.Info) -> Optional[str]:
        kwargs = strip_unset({})
        return _resolve_DocumentType_txt_extract_file(self, info, **kwargs)
    @strawberry.field(name="mdSummaryFile")
    def md_summary_file(self, info: strawberry.Info) -> Optional[str]:
        kwargs = strip_unset({})
        return _resolve_DocumentType_md_summary_file(self, info, **kwargs)
    page_count: int = strawberry.field(name="pageCount", default=None)
    @strawberry.field(name="pawlsParseFile")
    def pawls_parse_file(self, info: strawberry.Info) -> Optional[str]:
        kwargs = strip_unset({})
        return _resolve_DocumentType_pawls_parse_file(self, info, **kwargs)
    @strawberry.field(name="originalFileType", description='MIME type of the original upload before PDF conversion')
    def original_file_type(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "original_file_type", None))
    @strawberry.field(name="pdfFileHash", description='SHA-256 hash of the PDF file content for caching and integrity checks')
    def pdf_file_hash(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "pdf_file_hash", None))
    version_tree_id: uuid.UUID = strawberry.field(name="versionTreeId", description='Groups all content versions of same logical document. Implements Rule C1.', default=None)
    is_current: bool = strawberry.field(name="isCurrent", description='True for newest content in this version tree. Implements Rule C3.', default=None)
    source_document: Optional["DocumentType"] = strawberry.field(name="sourceDocument", description='Original document this was copied from (cross-corpus provenance). Implements Rule I2.', default=None)
    processing_started: Optional[datetime.datetime] = strawberry.field(name="processingStarted", default=None)
    processing_finished: Optional[datetime.datetime] = strawberry.field(name="processingFinished", default=None)
    @strawberry.field(name="processingStatus", description='Current processing status of the document in the parsing pipeline')
    def processing_status(self, info: strawberry.Info) -> Optional[enums.DocumentProcessingStatusEnum]:
        kwargs = strip_unset({})
        return _resolve_DocumentType_processing_status(self, info, **kwargs)
    @strawberry.field(name="processingError", description='Error message if processing failed (truncated for display)')
    def processing_error(self, info: strawberry.Info) -> Optional[str]:
        kwargs = strip_unset({})
        return _resolve_DocumentType_processing_error(self, info, **kwargs)
    @strawberry.field(name="processingErrorTraceback", description='Full traceback if processing failed')
    def processing_error_traceback(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "processing_error_traceback", None))
    @strawberry.field(name="assignmentSet")
    def assignment_set(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["AssignmentTypeConnection", strawberry.lazy("config.graphql.user_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "assignment_set", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="AssignmentType", )
    @strawberry.field(name="corpusCopies", description='Original document this was copied from (cross-corpus provenance). Implements Rule I2.')
    def corpus_copies(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> "DocumentTypeConnection":
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "corpus_copies", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="DocumentType", )
    @strawberry.field(name="children")
    def children(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> "DocumentTypeConnection":
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "children", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="DocumentType", )
    @strawberry.field(name="rows")
    def rows(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> "DocumentAnalysisRowTypeConnection":
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "rows", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="DocumentAnalysisRowType", )
    @strawberry.field(name="sourceRelationships")
    def source_relationships(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> "DocumentRelationshipTypeConnection":
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "source_relationships", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="DocumentRelationshipType", )
    @strawberry.field(name="targetRelationships")
    def target_relationships(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> "DocumentRelationshipTypeConnection":
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "target_relationships", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="DocumentRelationshipType", )
    @strawberry.field(name="pathRecords", description='Specific content version this path points to')
    def path_records(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> "DocumentPathTypeConnection":
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "path_records", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="DocumentPathType", )
    @strawberry.field(name="summaryRevisions", description='List of all summary revisions/versions for a specific corpus, ordered by version.')
    def summary_revisions(self, info: strawberry.Info, corpus_id: Annotated[strawberry.ID, strawberry.argument(name="corpusId")] = strawberry.UNSET) -> Optional[list[Optional["DocumentSummaryRevisionType"]]]:
        kwargs = strip_unset({"corpus_id": corpus_id})
        return _resolve_DocumentType_summary_revisions(self, info, **kwargs)
    memory_for_corpus: Optional[Annotated["CorpusType", strawberry.lazy("config.graphql.corpus_types")]] = strawberry.field(name="memoryForCorpus", default=None)
    @strawberry.field(name="corpusActionExecutions", description='The document this action was executed on (null for thread-based actions)')
    def corpus_action_executions(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET, id: Annotated[Optional[strawberry.ID], strawberry.argument(name="id")] = strawberry.UNSET, corpus__id: Annotated[Optional[strawberry.ID], strawberry.argument(name="corpus_Id")] = strawberry.UNSET, corpus_action__id: Annotated[Optional[strawberry.ID], strawberry.argument(name="corpusAction_Id")] = strawberry.UNSET, document__id: Annotated[Optional[strawberry.ID], strawberry.argument(name="document_Id")] = strawberry.UNSET, status: Annotated[Optional[enums.CorpusesCorpusActionExecutionStatusChoices], strawberry.argument(name="status")] = strawberry.UNSET, action_type: Annotated[Optional[enums.CorpusesCorpusActionExecutionActionTypeChoices], strawberry.argument(name="actionType")] = strawberry.UNSET, trigger: Annotated[Optional[enums.CorpusesCorpusActionExecutionTriggerChoices], strawberry.argument(name="trigger")] = strawberry.UNSET, creator__id: Annotated[Optional[strawberry.ID], strawberry.argument(name="creator_Id")] = strawberry.UNSET) -> Annotated["CorpusActionExecutionTypeConnection", strawberry.lazy("config.graphql.agent_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last, "id": id, "corpus__id": corpus__id, "corpus_action__id": corpus_action__id, "document__id": document__id, "status": status, "action_type": action_type, "trigger": trigger, "creator__id": creator__id})
        resolved = getattr(self, "corpus_action_executions", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="CorpusActionExecutionType", filterset_class=filterset_factory(CorpusActionExecution, fields={'id': ['exact'], 'corpus__id': ['exact'], 'corpus_action__id': ['exact'], 'document__id': ['exact'], 'status': ['exact'], 'action_type': ['exact'], 'trigger': ['exact'], 'creator__id': ['exact']}), filter_args={"id": "id", "corpus__id": "corpus__id", "corpus_action__id": "corpus_action__id", "document__id": "document__id", "status": "status", "action_type": "action_type", "trigger": "trigger", "creator__id": "creator__id"}, )
    @strawberry.field(name="relationships")
    def relationships(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["RelationshipTypeConnection", strawberry.lazy("config.graphql.annotation_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "relationships", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="RelationshipType", )
    @strawberry.field(name="docAnnotations")
    def doc_annotations(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET, raw_text__contains: Annotated[Optional[str], strawberry.argument(name="rawText_Contains")] = strawberry.UNSET, annotation_label_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="annotationLabelId")] = strawberry.UNSET, annotation_label__text: Annotated[Optional[str], strawberry.argument(name="annotationLabel_Text")] = strawberry.UNSET, annotation_label__text__contains: Annotated[Optional[str], strawberry.argument(name="annotationLabel_Text_Contains")] = strawberry.UNSET, annotation_label__description__contains: Annotated[Optional[str], strawberry.argument(name="annotationLabel_Description_Contains")] = strawberry.UNSET, annotation_label__label_type: Annotated[Optional[enums.AnnotationsAnnotationLabelLabelTypeChoices], strawberry.argument(name="annotationLabel_LabelType")] = strawberry.UNSET, analysis__isnull: Annotated[Optional[bool], strawberry.argument(name="analysis_Isnull")] = strawberry.UNSET, document_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="documentId")] = strawberry.UNSET, corpus_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="corpusId")] = strawberry.UNSET, structural: Annotated[Optional[bool], strawberry.argument(name="structural")] = strawberry.UNSET, uses_label_from_labelset_id: Annotated[Optional[str], strawberry.argument(name="usesLabelFromLabelsetId")] = strawberry.UNSET, created_by_analysis_ids: Annotated[Optional[str], strawberry.argument(name="createdByAnalysisIds")] = strawberry.UNSET, created_with_analyzer_id: Annotated[Optional[str], strawberry.argument(name="createdWithAnalyzerId")] = strawberry.UNSET, order_by: Annotated[Optional[str], strawberry.argument(name="orderBy", description='Ordering')] = strawberry.UNSET) -> Annotated["AnnotationTypeConnection", strawberry.lazy("config.graphql.annotation_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last, "raw_text__contains": raw_text__contains, "annotation_label_id": annotation_label_id, "annotation_label__text": annotation_label__text, "annotation_label__text__contains": annotation_label__text__contains, "annotation_label__description__contains": annotation_label__description__contains, "annotation_label__label_type": annotation_label__label_type, "analysis__isnull": analysis__isnull, "document_id": document_id, "corpus_id": corpus_id, "structural": structural, "uses_label_from_labelset_id": uses_label_from_labelset_id, "created_by_analysis_ids": created_by_analysis_ids, "created_with_analyzer_id": created_with_analyzer_id, "order_by": order_by})
        resolved = _resolve_DocumentType_doc_annotations(self, info, **kwargs)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="AnnotationType", filterset_class=setup_filterset(AnnotationFilter), filter_args={"raw_text__contains": "raw_text__contains", "annotation_label_id": "annotation_label_id", "annotation_label__text": "annotation_label__text", "annotation_label__text__contains": "annotation_label__text__contains", "annotation_label__description__contains": "annotation_label__description__contains", "annotation_label__label_type": "annotation_label__label_type", "analysis__isnull": "analysis__isnull", "document_id": "document_id", "corpus_id": "corpus_id", "structural": "structural", "uses_label_from_labelset_id": "uses_label_from_labelset_id", "created_by_analysis_ids": "created_by_analysis_ids", "created_with_analyzer_id": "created_with_analyzer_id", "order_by": "order_by"}, )
    @strawberry.field(name="notes")
    def notes(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["NoteTypeConnection", strawberry.lazy("config.graphql.annotation_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "notes", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="NoteType", )
    @strawberry.field(name="inboundReferences")
    def inbound_references(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["CorpusReferenceTypeConnection", strawberry.lazy("config.graphql.annotation_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "inbound_references", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="CorpusReferenceType", )
    @strawberry.field(name="frontierEntries")
    def frontier_entries(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["AuthorityFrontierNodeConnection", strawberry.lazy("config.graphql.annotation_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "frontier_entries", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="AuthorityFrontierNode", )
    @strawberry.field(name="includedInAnalyses")
    def included_in_analyses(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["AnalysisTypeConnection", strawberry.lazy("config.graphql.extract_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "included_in_analyses", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="AnalysisType", )
    @strawberry.field(name="extracts")
    def extracts(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["ExtractTypeConnection", strawberry.lazy("config.graphql.extract_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "extracts", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="ExtractType", )
    @strawberry.field(name="extractedDatacells")
    def extracted_datacells(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["DatacellTypeConnection", strawberry.lazy("config.graphql.extract_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "extracted_datacells", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="DatacellType", )
    @strawberry.field(name="conversations", description='The document to which this conversation belongs')
    def conversations(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["ConversationTypeConnection", strawberry.lazy("config.graphql.conversation_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "conversations", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="ConversationType", )
    @strawberry.field(name="chatMessages", description='A document that this chat message is based on')
    def chat_messages(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["MessageTypeConnection", strawberry.lazy("config.graphql.conversation_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "chat_messages", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="MessageType", )
    @strawberry.field(name="agentActionResults", description='The document this action was run on (null for thread-based actions)')
    def agent_action_results(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET, id: Annotated[Optional[strawberry.ID], strawberry.argument(name="id")] = strawberry.UNSET, corpus_action__id: Annotated[Optional[strawberry.ID], strawberry.argument(name="corpusAction_Id")] = strawberry.UNSET, document__id: Annotated[Optional[strawberry.ID], strawberry.argument(name="document_Id")] = strawberry.UNSET, status: Annotated[Optional[enums.AgentsAgentActionResultStatusChoices], strawberry.argument(name="status")] = strawberry.UNSET, creator__id: Annotated[Optional[strawberry.ID], strawberry.argument(name="creator_Id")] = strawberry.UNSET) -> Annotated["AgentActionResultTypeConnection", strawberry.lazy("config.graphql.agent_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last, "id": id, "corpus_action__id": corpus_action__id, "document__id": document__id, "status": status, "creator__id": creator__id})
        resolved = getattr(self, "agent_action_results", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="AgentActionResultType", filterset_class=filterset_factory(AgentActionResult, fields={'id': ['exact'], 'corpus_action__id': ['exact'], 'document__id': ['exact'], 'status': ['exact'], 'creator__id': ['exact']}), filter_args={"id": "id", "corpus_action__id": "corpus_action__id", "document__id": "document__id", "status": "status", "creator__id": "creator__id"}, )
    @strawberry.field(name="citedInResearchReports", description='Documents touched (vector-search hits, summaries loaded, etc.)')
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
    @strawberry.field(name="docTypeLabels", description="Flat list of distinct ``DOC_TYPE_LABEL`` annotation labels for this document — the corpus list view's per-card badges. Resolved from a single batched prefetch when the parent ``documents`` resolver opts in via ``requests_doc_type_labels``; falls back to one targeted SELECT per document otherwise. Skipping the Relay connection wrapper avoids the per-document COUNT + SELECT + FK descriptor storm the old ``docAnnotations`` shape forced.")
    def doc_type_labels(self, info: strawberry.Info) -> Optional[list[Annotated["AnnotationLabelType", strawberry.lazy("config.graphql.annotation_types")]]]:
        kwargs = strip_unset({})
        return _resolve_DocumentType_doc_type_labels(self, info, **kwargs)
    @strawberry.field(name="allStructuralAnnotations")
    def all_structural_annotations(self, info: strawberry.Info, annotation_ids: Annotated[Optional[list[strawberry.ID]], strawberry.argument(name="annotationIds")] = strawberry.UNSET) -> Optional[list[Optional[Annotated["AnnotationType", strawberry.lazy("config.graphql.annotation_types")]]]]:
        kwargs = strip_unset({"annotation_ids": annotation_ids})
        return _resolve_DocumentType_all_structural_annotations(self, info, **kwargs)
    @strawberry.field(name="allAnnotations")
    def all_annotations(self, info: strawberry.Info, corpus_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="corpusId")] = strawberry.UNSET, analysis_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="analysisId")] = strawberry.UNSET, is_structural: Annotated[Optional[bool], strawberry.argument(name="isStructural")] = strawberry.UNSET) -> Optional[list[Optional[Annotated["AnnotationType", strawberry.lazy("config.graphql.annotation_types")]]]]:
        kwargs = strip_unset({"corpus_id": corpus_id, "analysis_id": analysis_id, "is_structural": is_structural})
        return _resolve_DocumentType_all_annotations(self, info, **kwargs)
    @strawberry.field(name="allRelationships")
    def all_relationships(self, info: strawberry.Info, corpus_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="corpusId")] = strawberry.UNSET, analysis_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="analysisId")] = strawberry.UNSET, is_structural: Annotated[Optional[bool], strawberry.argument(name="isStructural")] = strawberry.UNSET) -> Optional[list[Optional[Annotated["RelationshipType", strawberry.lazy("config.graphql.annotation_types")]]]]:
        kwargs = strip_unset({"corpus_id": corpus_id, "analysis_id": analysis_id, "is_structural": is_structural})
        return _resolve_DocumentType_all_relationships(self, info, **kwargs)
    @strawberry.field(name="allStructuralRelationships")
    def all_structural_relationships(self, info: strawberry.Info, relationship_ids: Annotated[Optional[list[strawberry.ID]], strawberry.argument(name="relationshipIds")] = strawberry.UNSET) -> Optional[list[Optional[Annotated["RelationshipType", strawberry.lazy("config.graphql.annotation_types")]]]]:
        kwargs = strip_unset({"relationship_ids": relationship_ids})
        return _resolve_DocumentType_all_structural_relationships(self, info, **kwargs)
    @strawberry.field(name="allDocRelationships")
    def all_doc_relationships(self, info: strawberry.Info, corpus_id: Annotated[Optional[str], strawberry.argument(name="corpusId")] = strawberry.UNSET) -> Optional[list[Optional["DocumentRelationshipType"]]]:
        kwargs = strip_unset({"corpus_id": corpus_id})
        return _resolve_DocumentType_all_doc_relationships(self, info, **kwargs)
    @strawberry.field(name="docRelationshipCount", description='Count of document relationships for this document in the given corpus')
    def doc_relationship_count(self, info: strawberry.Info, corpus_id: Annotated[Optional[str], strawberry.argument(name="corpusId")] = strawberry.UNSET) -> Optional[int]:
        kwargs = strip_unset({"corpus_id": corpus_id})
        return _resolve_DocumentType_doc_relationship_count(self, info, **kwargs)
    @strawberry.field(name="allNotes")
    def all_notes(self, info: strawberry.Info, corpus_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="corpusId")] = strawberry.UNSET) -> Optional[list[Optional[Annotated["NoteType", strawberry.lazy("config.graphql.annotation_types")]]]]:
        kwargs = strip_unset({"corpus_id": corpus_id})
        return _resolve_DocumentType_all_notes(self, info, **kwargs)
    @strawberry.field(name="currentSummaryVersion", description='Current version number of the summary for a specific corpus')
    def current_summary_version(self, info: strawberry.Info, corpus_id: Annotated[strawberry.ID, strawberry.argument(name="corpusId")] = strawberry.UNSET) -> Optional[int]:
        kwargs = strip_unset({"corpus_id": corpus_id})
        return _resolve_DocumentType_current_summary_version(self, info, **kwargs)
    @strawberry.field(name="summaryContent", description='Current summary content for a specific corpus')
    def summary_content(self, info: strawberry.Info, corpus_id: Annotated[strawberry.ID, strawberry.argument(name="corpusId")] = strawberry.UNSET) -> Optional[str]:
        kwargs = strip_unset({"corpus_id": corpus_id})
        return _resolve_DocumentType_summary_content(self, info, **kwargs)
    @strawberry.field(name="versionNumber", description='Content version number in this corpus (from DocumentPath)')
    def version_number(self, info: strawberry.Info, corpus_id: Annotated[strawberry.ID, strawberry.argument(name="corpusId")] = strawberry.UNSET) -> Optional[int]:
        kwargs = strip_unset({"corpus_id": corpus_id})
        return _resolve_DocumentType_version_number(self, info, **kwargs)
    @strawberry.field(name="hasVersionHistory", description='True if this document has multiple versions (parent exists)')
    def has_version_history(self, info: strawberry.Info) -> Optional[bool]:
        kwargs = strip_unset({})
        return _resolve_DocumentType_has_version_history(self, info, **kwargs)
    @strawberry.field(name="versionCount", description="Total number of versions in this document's version tree")
    def version_count(self, info: strawberry.Info) -> Optional[int]:
        kwargs = strip_unset({})
        return _resolve_DocumentType_version_count(self, info, **kwargs)
    @strawberry.field(name="isLatestVersion", description='True if this is the current version (Document.is_current)')
    def is_latest_version(self, info: strawberry.Info) -> Optional[bool]:
        kwargs = strip_unset({})
        return _resolve_DocumentType_is_latest_version(self, info, **kwargs)
    @strawberry.field(name="lastModified", description='When the document was last modified in this corpus')
    def last_modified(self, info: strawberry.Info, corpus_id: Annotated[strawberry.ID, strawberry.argument(name="corpusId")] = strawberry.UNSET) -> Optional[datetime.datetime]:
        kwargs = strip_unset({"corpus_id": corpus_id})
        return _resolve_DocumentType_last_modified(self, info, **kwargs)
    @strawberry.field(name="versionHistory", description='Complete version history (lazy-loaded on request)')
    def version_history(self, info: strawberry.Info) -> Optional[Annotated["VersionHistoryType", strawberry.lazy("config.graphql.base_types")]]:
        kwargs = strip_unset({})
        return _resolve_DocumentType_version_history(self, info, **kwargs)
    @strawberry.field(name="pathHistory", description='Path/location history in corpus (lazy-loaded on request)')
    def path_history(self, info: strawberry.Info, corpus_id: Annotated[strawberry.ID, strawberry.argument(name="corpusId")] = strawberry.UNSET) -> Optional[Annotated["PathHistoryType", strawberry.lazy("config.graphql.base_types")]]:
        kwargs = strip_unset({"corpus_id": corpus_id})
        return _resolve_DocumentType_path_history(self, info, **kwargs)
    @strawberry.field(name="corpusVersions", description='All versions of this document in a specific corpus. Used by the version selector UI to show available versions.')
    def corpus_versions(self, info: strawberry.Info, corpus_id: Annotated[strawberry.ID, strawberry.argument(name="corpusId")] = strawberry.UNSET) -> Optional[list[Annotated["CorpusVersionInfoType", strawberry.lazy("config.graphql.base_types")]]]:
        kwargs = strip_unset({"corpus_id": corpus_id})
        return _resolve_DocumentType_corpus_versions(self, info, **kwargs)
    @strawberry.field(name="canRestore", description='Whether user can restore this document (requires UPDATE permission)')
    def can_restore(self, info: strawberry.Info, corpus_id: Annotated[strawberry.ID, strawberry.argument(name="corpusId")] = strawberry.UNSET) -> Optional[bool]:
        kwargs = strip_unset({"corpus_id": corpus_id})
        return _resolve_DocumentType_can_restore(self, info, **kwargs)
    @strawberry.field(name="canViewHistory", description='Whether user can view version history (requires READ permission)')
    def can_view_history(self, info: strawberry.Info) -> Optional[bool]:
        kwargs = strip_unset({})
        return _resolve_DocumentType_can_view_history(self, info, **kwargs)
    @strawberry.field(name="canRetry", description='Whether the user can retry processing for this document (True if FAILED and user has permission)')
    def can_retry(self, info: strawberry.Info) -> Optional[bool]:
        kwargs = strip_unset({})
        return _resolve_DocumentType_can_retry(self, info, **kwargs)
    @strawberry.field(name="pageAnnotations", description="Get annots for spec. page(s) using opt. queries. Either 'page' (single) or 'pages' (multiple).")
    def page_annotations(self, info: strawberry.Info, corpus_id: Annotated[strawberry.ID, strawberry.argument(name="corpusId")] = strawberry.UNSET, page: Annotated[Optional[int], strawberry.argument(name="page")] = strawberry.UNSET, pages: Annotated[Optional[list[Optional[int]]], strawberry.argument(name="pages")] = strawberry.UNSET, structural: Annotated[Optional[bool], strawberry.argument(name="structural")] = strawberry.UNSET, analysis_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="analysisId")] = strawberry.UNSET) -> Optional[list[Optional[Annotated["AnnotationType", strawberry.lazy("config.graphql.annotation_types")]]]]:
        kwargs = strip_unset({"corpus_id": corpus_id, "page": page, "pages": pages, "structural": structural, "analysis_id": analysis_id})
        return _resolve_DocumentType_page_annotations(self, info, **kwargs)
    @strawberry.field(name="pageRelationships", description='Get relationships where source or target annotations are on the specified page(s).')
    def page_relationships(self, info: strawberry.Info, corpus_id: Annotated[strawberry.ID, strawberry.argument(name="corpusId")] = strawberry.UNSET, pages: Annotated[list[Optional[int]], strawberry.argument(name="pages")] = strawberry.UNSET, structural: Annotated[Optional[bool], strawberry.argument(name="structural")] = strawberry.UNSET, analysis_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="analysisId")] = strawberry.UNSET) -> Optional[list[Optional[Annotated["RelationshipType", strawberry.lazy("config.graphql.annotation_types")]]]]:
        kwargs = strip_unset({"corpus_id": corpus_id, "pages": pages, "structural": structural, "analysis_id": analysis_id})
        return _resolve_DocumentType_page_relationships(self, info, **kwargs)
    @strawberry.field(name="relationshipSummary", description='Get relationship summary statistics for this document and corpus (MV-backed).')
    def relationship_summary(self, info: strawberry.Info, corpus_id: Annotated[strawberry.ID, strawberry.argument(name="corpusId")] = strawberry.UNSET) -> Optional[GenericScalar]:
        kwargs = strip_unset({"corpus_id": corpus_id})
        return _resolve_DocumentType_relationship_summary(self, info, **kwargs)
    @strawberry.field(name="extractAnnotationSummary", description='Get summary of annotations used in specific extract.')
    def extract_annotation_summary(self, info: strawberry.Info, extract_id: Annotated[strawberry.ID, strawberry.argument(name="extractId")] = strawberry.UNSET) -> Optional[GenericScalar]:
        kwargs = strip_unset({"extract_id": extract_id})
        return _resolve_DocumentType_extract_annotation_summary(self, info, **kwargs)
    @strawberry.field(name="folderInCorpus", description='Get the folder this document is in within a specific corpus (null = root)')
    def folder_in_corpus(self, info: strawberry.Info, corpus_id: Annotated[strawberry.ID, strawberry.argument(name="corpusId")] = strawberry.UNSET) -> Optional[Annotated["CorpusFolderType", strawberry.lazy("config.graphql.corpus_types")]]:
        kwargs = strip_unset({"corpus_id": corpus_id})
        return _resolve_DocumentType_folder_in_corpus(self, info, **kwargs)


def _get_queryset_DocumentType(queryset, info):
    """PORT: config.graphql.document_types.DocumentType.get_queryset

    Port of DocumentType.get_queryset
    """
    raise NotImplementedError("_get_queryset_DocumentType not yet ported — see manifest")


register_type("DocumentType", DocumentType, model=Document, get_queryset=_get_queryset_DocumentType)


DocumentTypeConnection = make_connection_types(DocumentType, type_name="DocumentTypeConnection", countable=True, pdf_page_aware=False)


@strawberry.type(name="DocumentAnalysisRowType")
class DocumentAnalysisRowType(Node):
    user_lock: Optional[Annotated["UserType", strawberry.lazy("config.graphql.user_types")]] = strawberry.field(name="userLock", default=None)
    backend_lock: bool = strawberry.field(name="backendLock", default=None)
    is_public: bool = strawberry.field(name="isPublic", default=None)
    creator: Annotated["UserType", strawberry.lazy("config.graphql.user_types")] = strawberry.field(name="creator", default=None)
    created: datetime.datetime = strawberry.field(name="created", default=None)
    modified: datetime.datetime = strawberry.field(name="modified", default=None)
    document: "DocumentType" = strawberry.field(name="document", default=None)
    @strawberry.field(name="annotations")
    def annotations(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET, raw_text__contains: Annotated[Optional[str], strawberry.argument(name="rawText_Contains")] = strawberry.UNSET, annotation_label_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="annotationLabelId")] = strawberry.UNSET, annotation_label__text: Annotated[Optional[str], strawberry.argument(name="annotationLabel_Text")] = strawberry.UNSET, annotation_label__text__contains: Annotated[Optional[str], strawberry.argument(name="annotationLabel_Text_Contains")] = strawberry.UNSET, annotation_label__description__contains: Annotated[Optional[str], strawberry.argument(name="annotationLabel_Description_Contains")] = strawberry.UNSET, annotation_label__label_type: Annotated[Optional[enums.AnnotationsAnnotationLabelLabelTypeChoices], strawberry.argument(name="annotationLabel_LabelType")] = strawberry.UNSET, analysis__isnull: Annotated[Optional[bool], strawberry.argument(name="analysis_Isnull")] = strawberry.UNSET, document_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="documentId")] = strawberry.UNSET, corpus_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="corpusId")] = strawberry.UNSET, structural: Annotated[Optional[bool], strawberry.argument(name="structural")] = strawberry.UNSET, uses_label_from_labelset_id: Annotated[Optional[str], strawberry.argument(name="usesLabelFromLabelsetId")] = strawberry.UNSET, created_by_analysis_ids: Annotated[Optional[str], strawberry.argument(name="createdByAnalysisIds")] = strawberry.UNSET, created_with_analyzer_id: Annotated[Optional[str], strawberry.argument(name="createdWithAnalyzerId")] = strawberry.UNSET, order_by: Annotated[Optional[str], strawberry.argument(name="orderBy", description='Ordering')] = strawberry.UNSET) -> Annotated["AnnotationTypeConnection", strawberry.lazy("config.graphql.annotation_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last, "raw_text__contains": raw_text__contains, "annotation_label_id": annotation_label_id, "annotation_label__text": annotation_label__text, "annotation_label__text__contains": annotation_label__text__contains, "annotation_label__description__contains": annotation_label__description__contains, "annotation_label__label_type": annotation_label__label_type, "analysis__isnull": analysis__isnull, "document_id": document_id, "corpus_id": corpus_id, "structural": structural, "uses_label_from_labelset_id": uses_label_from_labelset_id, "created_by_analysis_ids": created_by_analysis_ids, "created_with_analyzer_id": created_with_analyzer_id, "order_by": order_by})
        resolved = getattr(self, "annotations", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="AnnotationType", filterset_class=setup_filterset(AnnotationFilter), filter_args={"raw_text__contains": "raw_text__contains", "annotation_label_id": "annotation_label_id", "annotation_label__text": "annotation_label__text", "annotation_label__text__contains": "annotation_label__text__contains", "annotation_label__description__contains": "annotation_label__description__contains", "annotation_label__label_type": "annotation_label__label_type", "analysis__isnull": "analysis__isnull", "document_id": "document_id", "corpus_id": "corpus_id", "structural": "structural", "uses_label_from_labelset_id": "uses_label_from_labelset_id", "created_by_analysis_ids": "created_by_analysis_ids", "created_with_analyzer_id": "created_with_analyzer_id", "order_by": "order_by"}, )
    @strawberry.field(name="data")
    def data(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["DatacellTypeConnection", strawberry.lazy("config.graphql.extract_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "data", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="DatacellType", )
    analysis: Optional[Annotated["AnalysisType", strawberry.lazy("config.graphql.extract_types")]] = strawberry.field(name="analysis", default=None)
    extract: Optional[Annotated["ExtractType", strawberry.lazy("config.graphql.extract_types")]] = strawberry.field(name="extract", default=None)
    @strawberry.field(name="myPermissions")
    def my_permissions(self, info: strawberry.Info) -> Optional[GenericScalar]:
        return core_permissions.resolve_my_permissions(self, info)
    @strawberry.field(name="isPublished")
    def is_published(self, info: strawberry.Info) -> Optional[bool]:
        return core_permissions.resolve_is_published(self, info)
    @strawberry.field(name="objectSharedWith")
    def object_shared_with(self, info: strawberry.Info) -> Optional[GenericScalar]:
        return core_permissions.resolve_object_shared_with(self, info)


register_type("DocumentAnalysisRowType", DocumentAnalysisRowType, model=DocumentAnalysisRow)


DocumentAnalysisRowTypeConnection = make_connection_types(DocumentAnalysisRowType, type_name="DocumentAnalysisRowTypeConnection", countable=True, pdf_page_aware=False)


@strawberry.type(name="DocumentRelationshipType", description='GraphQL type for DocumentRelationship model.')
class DocumentRelationshipType(Node):
    user_lock: Optional[Annotated["UserType", strawberry.lazy("config.graphql.user_types")]] = strawberry.field(name="userLock", default=None)
    backend_lock: bool = strawberry.field(name="backendLock", default=None)
    is_public: bool = strawberry.field(name="isPublic", default=None)
    creator: Annotated["UserType", strawberry.lazy("config.graphql.user_types")] = strawberry.field(name="creator", default=None)
    created: datetime.datetime = strawberry.field(name="created", default=None)
    modified: datetime.datetime = strawberry.field(name="modified", default=None)
    source_document: "DocumentType" = strawberry.field(name="sourceDocument", default=None)
    target_document: "DocumentType" = strawberry.field(name="targetDocument", default=None)
    @strawberry.field(name="relationshipType")
    def relationship_type(self, info: strawberry.Info) -> enums.DocumentsDocumentRelationshipRelationshipTypeChoices:
        return coerce_enum(enums.DocumentsDocumentRelationshipRelationshipTypeChoices, getattr(self, "relationship_type", None))
    annotation_label: Optional[Annotated["AnnotationLabelType", strawberry.lazy("config.graphql.annotation_types")]] = strawberry.field(name="annotationLabel", default=None)
    corpus: Optional[Annotated["CorpusType", strawberry.lazy("config.graphql.corpus_types")]] = strawberry.field(name="corpus", default=None)
    data: Optional[GenericScalar] = strawberry.field(name="data", default=None)
    @strawberry.field(name="myPermissions")
    def my_permissions(self, info: strawberry.Info) -> Optional[GenericScalar]:
        return core_permissions.resolve_my_permissions(self, info)
    @strawberry.field(name="isPublished")
    def is_published(self, info: strawberry.Info) -> Optional[bool]:
        return core_permissions.resolve_is_published(self, info)
    @strawberry.field(name="objectSharedWith")
    def object_shared_with(self, info: strawberry.Info) -> Optional[GenericScalar]:
        return core_permissions.resolve_object_shared_with(self, info)


def _get_queryset_DocumentRelationshipType(queryset, info):
    """PORT: config.graphql.document_types.DocumentRelationshipType.get_queryset

    Port of DocumentRelationshipType.get_queryset
    """
    raise NotImplementedError("_get_queryset_DocumentRelationshipType not yet ported — see manifest")


register_type("DocumentRelationshipType", DocumentRelationshipType, model=DocumentRelationship, get_queryset=_get_queryset_DocumentRelationshipType)


DocumentRelationshipTypeConnection = make_connection_types(DocumentRelationshipType, type_name="DocumentRelationshipTypeConnection", countable=True, pdf_page_aware=False)


def _resolve_DocumentPathType_action(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/document_types.py:153

    Port of DocumentPathType.resolve_action
    """
    raise NotImplementedError("_resolve_DocumentPathType_action not yet ported — see manifest")


@strawberry.type(name="DocumentPathType", description='GraphQL type for DocumentPath model - represents filesystem lifecycle events.')
class DocumentPathType(Node):
    parent: Optional["DocumentPathType"] = strawberry.field(name="parent", default=None)
    user_lock: Optional[Annotated["UserType", strawberry.lazy("config.graphql.user_types")]] = strawberry.field(name="userLock", default=None)
    backend_lock: bool = strawberry.field(name="backendLock", default=None)
    is_public: bool = strawberry.field(name="isPublic", default=None)
    creator: Annotated["UserType", strawberry.lazy("config.graphql.user_types")] = strawberry.field(name="creator", default=None)
    created: datetime.datetime = strawberry.field(name="created", default=None)
    modified: datetime.datetime = strawberry.field(name="modified", default=None)
    document: "DocumentType" = strawberry.field(name="document", description='Specific content version this path points to', default=None)
    corpus: Annotated["CorpusType", strawberry.lazy("config.graphql.corpus_types")] = strawberry.field(name="corpus", description='Corpus owning this path', default=None)
    folder: Optional[Annotated["CorpusFolderType", strawberry.lazy("config.graphql.corpus_types")]] = strawberry.field(name="folder", description='Current folder (null if folder deleted or at root)', default=None)
    @strawberry.field(name="path", description='Full path in corpus filesystem')
    def path(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "path", None))
    version_number: int = strawberry.field(name="versionNumber", description='Content version number (Rule P5: increments only on content changes)', default=None)
    is_deleted: bool = strawberry.field(name="isDeleted", description='Soft delete flag', default=None)
    is_current: bool = strawberry.field(name="isCurrent", description='True for current filesystem state (Rule P3)', default=None)
    ingestion_source: Optional["IngestionSourceType"] = strawberry.field(name="ingestionSource", description='Source integration that produced this version (null = manual upload)', default=None)
    @strawberry.field(name="externalId", description="Identifier in the external system (e.g. 'alpha:contract-123')")
    def external_id(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "external_id", None))
    ingestion_metadata: Optional[GenericScalar] = strawberry.field(name="ingestionMetadata", description='Arbitrary source-specific metadata (URL, crawl job ID, etc.)', default=None)
    @strawberry.field(name="children")
    def children(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> "DocumentPathTypeConnection":
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "children", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="DocumentPathType", )
    @strawberry.field(name="myPermissions")
    def my_permissions(self, info: strawberry.Info) -> Optional[GenericScalar]:
        return core_permissions.resolve_my_permissions(self, info)
    @strawberry.field(name="isPublished")
    def is_published(self, info: strawberry.Info) -> Optional[bool]:
        return core_permissions.resolve_is_published(self, info)
    @strawberry.field(name="objectSharedWith")
    def object_shared_with(self, info: strawberry.Info) -> Optional[GenericScalar]:
        return core_permissions.resolve_object_shared_with(self, info)
    @strawberry.field(name="action", description='Inferred action type')
    def action(self, info: strawberry.Info) -> Optional[enums.PathActionEnum]:
        kwargs = strip_unset({})
        return _resolve_DocumentPathType_action(self, info, **kwargs)


def _get_queryset_DocumentPathType(queryset, info):
    """PORT: config.graphql.document_types.DocumentPathType.get_queryset

    Port of DocumentPathType.get_queryset
    """
    raise NotImplementedError("_get_queryset_DocumentPathType not yet ported — see manifest")


register_type("DocumentPathType", DocumentPathType, model=DocumentPath, get_queryset=_get_queryset_DocumentPathType)


DocumentPathTypeConnection = make_connection_types(DocumentPathType, type_name="DocumentPathTypeConnection", countable=True, pdf_page_aware=False)


@strawberry.type(name="IngestionSourceType", description='GraphQL type for IngestionSource - a named integration that produces documents.')
class IngestionSourceType(Node):
    created: datetime.datetime = strawberry.field(name="created", default=None)
    modified: datetime.datetime = strawberry.field(name="modified", default=None)
    @strawberry.field(name="name", description="Human-readable name for this source (e.g. 'alpha_site_crawler')")
    def name(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "name", None))
    @strawberry.field(name="sourceType", description='Category of ingestion source')
    def source_type(self, info: strawberry.Info) -> enums.DocumentsIngestionSourceSourceTypeChoices:
        return coerce_enum(enums.DocumentsIngestionSourceSourceTypeChoices, getattr(self, "source_type", None))
    config: Optional[GenericScalar] = strawberry.field(name="config", description='Source configuration (connection details, etc.). WARNING: This field is returned to the owning user verbatim. Store secret-manager key paths or references here, never raw credentials (API keys, tokens, passwords).', default=None)
    active: bool = strawberry.field(name="active", description='Whether this source is actively ingesting documents', default=None)
    @strawberry.field(name="myPermissions")
    def my_permissions(self, info: strawberry.Info) -> Optional[GenericScalar]:
        return core_permissions.resolve_my_permissions(self, info)
    @strawberry.field(name="isPublished")
    def is_published(self, info: strawberry.Info) -> Optional[bool]:
        return core_permissions.resolve_is_published(self, info)
    @strawberry.field(name="objectSharedWith")
    def object_shared_with(self, info: strawberry.Info) -> Optional[GenericScalar]:
        return core_permissions.resolve_object_shared_with(self, info)


def _get_queryset_IngestionSourceType(queryset, info):
    """PORT: config.graphql.document_types.IngestionSourceType.get_queryset

    Port of IngestionSourceType.get_queryset
    """
    raise NotImplementedError("_get_queryset_IngestionSourceType not yet ported — see manifest")


register_type("IngestionSourceType", IngestionSourceType, model=IngestionSource, get_queryset=_get_queryset_IngestionSourceType)


IngestionSourceTypeConnection = make_connection_types(IngestionSourceType, type_name="IngestionSourceTypeConnection", countable=True, pdf_page_aware=False)


@strawberry.type(name="DocumentSummaryRevisionType", description='GraphQL type for document summary revisions.')
class DocumentSummaryRevisionType(Node):
    document: "DocumentType" = strawberry.field(name="document", default=None)
    corpus: Annotated["CorpusType", strawberry.lazy("config.graphql.corpus_types")] = strawberry.field(name="corpus", default=None)
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
    @strawberry.field(name="myPermissions")
    def my_permissions(self, info: strawberry.Info) -> Optional[GenericScalar]:
        return core_permissions.resolve_my_permissions(self, info)
    @strawberry.field(name="isPublished")
    def is_published(self, info: strawberry.Info) -> Optional[bool]:
        return core_permissions.resolve_is_published(self, info)
    @strawberry.field(name="objectSharedWith")
    def object_shared_with(self, info: strawberry.Info) -> Optional[GenericScalar]:
        return core_permissions.resolve_object_shared_with(self, info)


register_type("DocumentSummaryRevisionType", DocumentSummaryRevisionType, model=DocumentSummaryRevision)


DocumentSummaryRevisionTypeConnection = make_connection_types(DocumentSummaryRevisionType, type_name="DocumentSummaryRevisionTypeConnection", countable=True, pdf_page_aware=False)


@strawberry.type(name="DocumentCorpusActionsType")
class DocumentCorpusActionsType:
    corpus_actions: Optional[list[Optional[Annotated["CorpusActionType", strawberry.lazy("config.graphql.agent_types")]]]] = strawberry.field(name="corpusActions", default=None)
    extracts: Optional[list[Optional[Annotated["ExtractType", strawberry.lazy("config.graphql.extract_types")]]]] = strawberry.field(name="extracts", default=None)
    analysis_rows: Optional[list[Optional["DocumentAnalysisRowType"]]] = strawberry.field(name="analysisRows", default=None)


register_type("DocumentCorpusActionsType", DocumentCorpusActionsType, model=None)


@strawberry.type(name="DocumentStatsType", description='Permission-scoped aggregate counts for the Documents view tile counters.')
class DocumentStatsType:
    total_docs: int = strawberry.field(name="totalDocs", default=None)
    total_pages: int = strawberry.field(name="totalPages", default=None)
    processed_count: int = strawberry.field(name="processedCount", default=None)
    processing_count: int = strawberry.field(name="processingCount", default=None)


register_type("DocumentStatsType", DocumentStatsType, model=None)

