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

from config.graphql.serializers import DocumentSerializer
from opencontractserver.documents.models import Document
from opencontractserver.users.models import UserExport


@strawberry.type(name="UploadDocument")
class UploadDocument:
    ok: Optional[bool] = strawberry.field(name="ok")
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))
    document: Optional[Annotated["DocumentType", strawberry.lazy("config.graphql_new.document_types")]] = strawberry.field(name="document")


register_type("UploadDocument", UploadDocument, model=None)


@strawberry.type(name="UpdateDocument")
class UpdateDocument:
    ok: Optional[bool] = strawberry.field(name="ok")
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))
    @strawberry.field(name="objId")
    def obj_id(self, info: strawberry.Info) -> Optional[strawberry.ID]:
        return coerce_str(getattr(self, "obj_id", None))


register_type("UpdateDocument", UpdateDocument, model=None)


@strawberry.type(name="UpdateDocumentSummary", description="Mutation to update a document's markdown summary for a specific corpus, creating a new version in the process.\nUsers can create/update summaries if:\n- No summary exists yet and they have permission on the corpus (public or their corpus)\n- A summary exists and they are the original author")
class UpdateDocumentSummary:
    ok: Optional[bool] = strawberry.field(name="ok")
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))
    obj: Optional[Annotated["DocumentType", strawberry.lazy("config.graphql_new.document_types")]] = strawberry.field(name="obj")
    version: Optional[int] = strawberry.field(name="version", description='The new version number after update')


register_type("UpdateDocumentSummary", UpdateDocumentSummary, model=None)


@strawberry.type(name="DeleteDocument")
class DeleteDocument:
    ok: Optional[bool] = strawberry.field(name="ok")
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))


register_type("DeleteDocument", DeleteDocument, model=None)


@strawberry.type(name="DeleteMultipleDocuments")
class DeleteMultipleDocuments:
    ok: Optional[bool] = strawberry.field(name="ok")
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))


register_type("DeleteMultipleDocuments", DeleteMultipleDocuments, model=None)


@strawberry.type(name="UploadDocumentsZip", description='Mutation for uploading multiple documents via a zip file.\nThe zip is stored as a temporary file and processed asynchronously.\nOnly files with allowed MIME types will be created as documents.')
class UploadDocumentsZip:
    ok: Optional[bool] = strawberry.field(name="ok")
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))
    @strawberry.field(name="jobId", description='ID to track the processing job')
    def job_id(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "job_id", None))


register_type("UploadDocumentsZip", UploadDocumentsZip, model=None)


@strawberry.type(name="RetryDocumentProcessing", description="Retry processing for a failed document.\n\nThis mutation allows users to manually trigger reprocessing of a document\nthat failed during the parsing pipeline. It's useful when transient errors\n(like network timeouts or service unavailability) have been resolved.\n\nRequirements:\n- Document must be in FAILED processing state\n- User must have UPDATE permission on the document")
class RetryDocumentProcessing:
    ok: Optional[bool] = strawberry.field(name="ok")
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))
    document: Optional[Annotated["DocumentType", strawberry.lazy("config.graphql_new.document_types")]] = strawberry.field(name="document")


register_type("RetryDocumentProcessing", RetryDocumentProcessing, model=None)


@strawberry.type(name="RestoreDeletedDocument", description='Restore a soft-deleted document path within a corpus.\n\nDelegates to DocumentLifecycleService.restore_document() for:\n- Permission checking (corpus UPDATE permission)\n- Creating new DocumentPath with is_deleted=False')
class RestoreDeletedDocument:
    ok: Optional[bool] = strawberry.field(name="ok")
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))
    document: Optional[Annotated["DocumentType", strawberry.lazy("config.graphql_new.document_types")]] = strawberry.field(name="document")


register_type("RestoreDeletedDocument", RestoreDeletedDocument, model=None)


@strawberry.type(name="RestoreDocumentToVersion", description='Restore a document to a previous content version.\nCreates a new version that is a copy of the specified version.')
class RestoreDocumentToVersion:
    ok: Optional[bool] = strawberry.field(name="ok")
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))
    document: Optional[Annotated["DocumentType", strawberry.lazy("config.graphql_new.document_types")]] = strawberry.field(name="document")
    new_version_number: Optional[int] = strawberry.field(name="newVersionNumber")


register_type("RestoreDocumentToVersion", RestoreDocumentToVersion, model=None)


@strawberry.type(name="PermanentlyDeleteDocument", description='Permanently delete a soft-deleted document from a corpus.\n\nThis is IRREVERSIBLE and removes:\n- All DocumentPath history for the document in this corpus\n- User annotations (non-structural) on the document\n- Relationships involving those annotations\n- DocumentSummaryRevision records\n- The Document itself if no other corpus references it\n\nRequires DELETE permission on the corpus.')
class PermanentlyDeleteDocument:
    ok: Optional[bool] = strawberry.field(name="ok")
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))


register_type("PermanentlyDeleteDocument", PermanentlyDeleteDocument, model=None)


@strawberry.type(name="EmptyTrash", description='Permanently delete ALL soft-deleted documents in a corpus (empty trash).\n\nThis is IRREVERSIBLE and removes all documents currently in the corpus trash.\n\nRequires DELETE permission on the corpus.')
class EmptyTrash:
    ok: Optional[bool] = strawberry.field(name="ok")
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))
    deleted_count: Optional[int] = strawberry.field(name="deletedCount")


register_type("EmptyTrash", EmptyTrash, model=None)


@strawberry.type(name="EmptyCorpus", description='Move EVERY document in a corpus to Trash and remove ALL of its folders.\n\nThis is the "empty everything" action. Documents are soft-deleted (they\nremain in the trash and are restorable until the trash is emptied); the\nfolder tree is removed. Nothing is permanently deleted here — callers can\nfollow up with ``emptyTrash`` to purge.\n\nRequires DELETE permission on the corpus.')
class EmptyCorpus:
    ok: Optional[bool] = strawberry.field(name="ok")
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))
    trashed_count: Optional[int] = strawberry.field(name="trashedCount")


register_type("EmptyCorpus", EmptyCorpus, model=None)


@strawberry.type(name="UploadAnnotatedDocument")
class UploadAnnotatedDocument:
    ok: Optional[bool] = strawberry.field(name="ok")
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))


register_type("UploadAnnotatedDocument", UploadAnnotatedDocument, model=None)


@strawberry.type(name="StartCorpusExport", description='Mutation entrypoint for starting a corpus export.\nNow refactored to optionally accept a list of Analysis IDs (analyses_ids)\nthat should be included in the export. If analyses_ids are provided, then\nonly annotations/labels from those analyses are included. Otherwise, all\nannotations/labels for the corpus are included.')
class StartCorpusExport:
    ok: Optional[bool] = strawberry.field(name="ok")
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))
    export: Optional[Annotated["UserExportType", strawberry.lazy("config.graphql_new.user_types")]] = strawberry.field(name="export")


register_type("StartCorpusExport", StartCorpusExport, model=None)


@strawberry.type(name="DeleteExport")
class DeleteExport:
    ok: Optional[bool] = strawberry.field(name="ok")
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))


register_type("DeleteExport", DeleteExport, model=None)


def _mutate_UploadDocument(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:119

    Port of UploadDocument.mutate
    """
    raise NotImplementedError("_mutate_UploadDocument not yet ported — see manifest")


def m_upload_document(info: strawberry.Info, add_to_corpus_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="addToCorpusId", description='If provided, successfully uploaded document will be uploaded to corpus with specified id')] = strawberry.UNSET, add_to_extract_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="addToExtractId", description='If provided, successfully uploaded document will be added to extract with specified id')] = strawberry.UNSET, add_to_folder_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="addToFolderId", description='If provided along with add_to_corpus_id, the document will be assigned to this folder within the corpus')] = strawberry.UNSET, base64_file_string: Annotated[str, strawberry.argument(name="base64FileString", description='Base64-encoded file string for the file.')] = strawberry.UNSET, custom_meta: Annotated[Optional[GenericScalar], strawberry.argument(name="customMeta")] = strawberry.UNSET, description: Annotated[str, strawberry.argument(name="description", description='Description of the document.')] = strawberry.UNSET, external_id: Annotated[Optional[str], strawberry.argument(name="externalId", description="Identifier in the external system (e.g. 'alpha:contract-123')")] = strawberry.UNSET, filename: Annotated[str, strawberry.argument(name="filename", description='Filename of the document.')] = strawberry.UNSET, ingestion_metadata: Annotated[Optional[GenericScalar], strawberry.argument(name="ingestionMetadata", description='Arbitrary source-specific metadata (URL, crawl job ID, etc.)')] = strawberry.UNSET, ingestion_source_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="ingestionSourceId", description='Global ID of the IngestionSource that produced this document')] = strawberry.UNSET, make_public: Annotated[bool, strawberry.argument(name="makePublic", description='If True, document is immediately public. Defaults to False.')] = strawberry.UNSET, slug: Annotated[Optional[str], strawberry.argument(name="slug")] = strawberry.UNSET, title: Annotated[str, strawberry.argument(name="title", description='Title of the document.')] = strawberry.UNSET) -> Optional["UploadDocument"]:
    kwargs = strip_unset({"add_to_corpus_id": add_to_corpus_id, "add_to_extract_id": add_to_extract_id, "add_to_folder_id": add_to_folder_id, "base64_file_string": base64_file_string, "custom_meta": custom_meta, "description": description, "external_id": external_id, "filename": filename, "ingestion_metadata": ingestion_metadata, "ingestion_source_id": ingestion_source_id, "make_public": make_public, "slug": slug, "title": title})
    return _mutate_UploadDocument(UploadDocument, None, info, **kwargs)


def m_update_document(info: strawberry.Info, custom_meta: Annotated[Optional[GenericScalar], strawberry.argument(name="customMeta")] = strawberry.UNSET, description: Annotated[Optional[str], strawberry.argument(name="description")] = strawberry.UNSET, id: Annotated[str, strawberry.argument(name="id")] = strawberry.UNSET, pdf_file: Annotated[Optional[str], strawberry.argument(name="pdfFile")] = strawberry.UNSET, slug: Annotated[Optional[str], strawberry.argument(name="slug")] = strawberry.UNSET, title: Annotated[Optional[str], strawberry.argument(name="title")] = strawberry.UNSET) -> Optional["UpdateDocument"]:
    kwargs = strip_unset({"custom_meta": custom_meta, "description": description, "id": id, "pdf_file": pdf_file, "slug": slug, "title": title})
    return drf_mutation(payload_cls=UpdateDocument, model=Document, serializer=DocumentSerializer, type_name="DocumentType", pk_fields=(), lookup_field="id", root=None, info=info, kwargs=kwargs)


def _mutate_UpdateDocumentSummary(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:266

    Port of UpdateDocumentSummary.mutate
    """
    raise NotImplementedError("_mutate_UpdateDocumentSummary not yet ported — see manifest")


def m_update_document_summary(info: strawberry.Info, corpus_id: Annotated[strawberry.ID, strawberry.argument(name="corpusId", description='ID of the corpus this summary is for')] = strawberry.UNSET, document_id: Annotated[strawberry.ID, strawberry.argument(name="documentId", description='ID of the document to update')] = strawberry.UNSET, new_content: Annotated[str, strawberry.argument(name="newContent", description='New markdown content for the document summary')] = strawberry.UNSET) -> Optional["UpdateDocumentSummary"]:
    kwargs = strip_unset({"corpus_id": corpus_id, "document_id": document_id, "new_content": new_content})
    return _mutate_UpdateDocumentSummary(UpdateDocumentSummary, None, info, **kwargs)


def m_delete_document(info: strawberry.Info, id: Annotated[str, strawberry.argument(name="id")] = strawberry.UNSET) -> Optional["DeleteDocument"]:
    kwargs = strip_unset({"id": id})
    return drf_deletion(payload_cls=DeleteDocument, model=Document, lookup_field="id", root=None, info=info, kwargs=kwargs)


def _mutate_DeleteMultipleDocuments(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:389

    Port of DeleteMultipleDocuments.mutate
    """
    raise NotImplementedError("_mutate_DeleteMultipleDocuments not yet ported — see manifest")


def m_delete_multiple_documents(info: strawberry.Info, document_ids_to_delete: Annotated[list[Optional[str]], strawberry.argument(name="documentIdsToDelete", description='List of ids of the documents to delete')] = strawberry.UNSET) -> Optional["DeleteMultipleDocuments"]:
    kwargs = strip_unset({"document_ids_to_delete": document_ids_to_delete})
    return _mutate_DeleteMultipleDocuments(DeleteMultipleDocuments, None, info, **kwargs)


def _mutate_UploadDocumentsZip(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:447

    Port of UploadDocumentsZip.mutate
    """
    raise NotImplementedError("_mutate_UploadDocumentsZip not yet ported — see manifest")


def m_upload_documents_zip(info: strawberry.Info, add_to_corpus_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="addToCorpusId", description='If provided, successfully uploaded documents will be added to corpus with specified id')] = strawberry.UNSET, base64_file_string: Annotated[str, strawberry.argument(name="base64FileString", description='Base64-encoded zip file containing documents to upload')] = strawberry.UNSET, custom_meta: Annotated[Optional[GenericScalar], strawberry.argument(name="customMeta", description='Optional metadata to apply to all documents')] = strawberry.UNSET, description: Annotated[Optional[str], strawberry.argument(name="description", description='Optional description to apply to all documents')] = strawberry.UNSET, make_public: Annotated[bool, strawberry.argument(name="makePublic", description='If True, documents are immediately public. Defaults to False.')] = strawberry.UNSET, title_prefix: Annotated[Optional[str], strawberry.argument(name="titlePrefix", description='Optional prefix for document titles (will be combined with filename)')] = strawberry.UNSET) -> Optional["UploadDocumentsZip"]:
    kwargs = strip_unset({"add_to_corpus_id": add_to_corpus_id, "base64_file_string": base64_file_string, "custom_meta": custom_meta, "description": description, "make_public": make_public, "title_prefix": title_prefix})
    return _mutate_UploadDocumentsZip(UploadDocumentsZip, None, info, **kwargs)


def _mutate_RetryDocumentProcessing(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:515

    Port of RetryDocumentProcessing.mutate
    """
    raise NotImplementedError("_mutate_RetryDocumentProcessing not yet ported — see manifest")


def m_retry_document_processing(info: strawberry.Info, document_id: Annotated[str, strawberry.argument(name="documentId", description='ID of the failed document to retry processing')] = strawberry.UNSET) -> Optional["RetryDocumentProcessing"]:
    kwargs = strip_unset({"document_id": document_id})
    return _mutate_RetryDocumentProcessing(RetryDocumentProcessing, None, info, **kwargs)


def _mutate_RestoreDeletedDocument(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:884

    Port of RestoreDeletedDocument.mutate
    """
    raise NotImplementedError("_mutate_RestoreDeletedDocument not yet ported — see manifest")


def m_restore_deleted_document(info: strawberry.Info, corpus_id: Annotated[str, strawberry.argument(name="corpusId", description='Global ID of the corpus')] = strawberry.UNSET, document_id: Annotated[str, strawberry.argument(name="documentId", description='Global ID of the document to restore')] = strawberry.UNSET) -> Optional["RestoreDeletedDocument"]:
    kwargs = strip_unset({"corpus_id": corpus_id, "document_id": document_id})
    return _mutate_RestoreDeletedDocument(RestoreDeletedDocument, None, info, **kwargs)


def _mutate_RestoreDocumentToVersion(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:1185

    Port of RestoreDocumentToVersion.mutate
    """
    raise NotImplementedError("_mutate_RestoreDocumentToVersion not yet ported — see manifest")


def m_restore_document_to_version(info: strawberry.Info, corpus_id: Annotated[str, strawberry.argument(name="corpusId", description='Global ID of the corpus')] = strawberry.UNSET, document_id: Annotated[str, strawberry.argument(name="documentId", description='Global ID of the document version to restore to')] = strawberry.UNSET) -> Optional["RestoreDocumentToVersion"]:
    kwargs = strip_unset({"corpus_id": corpus_id, "document_id": document_id})
    return _mutate_RestoreDocumentToVersion(RestoreDocumentToVersion, None, info, **kwargs)


def _mutate_PermanentlyDeleteDocument(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:983

    Port of PermanentlyDeleteDocument.mutate
    """
    raise NotImplementedError("_mutate_PermanentlyDeleteDocument not yet ported — see manifest")


def m_permanently_delete_document(info: strawberry.Info, corpus_id: Annotated[str, strawberry.argument(name="corpusId", description='Global ID of the corpus')] = strawberry.UNSET, document_id: Annotated[str, strawberry.argument(name="documentId", description='Global ID of the document to permanently delete')] = strawberry.UNSET) -> Optional["PermanentlyDeleteDocument"]:
    kwargs = strip_unset({"corpus_id": corpus_id, "document_id": document_id})
    return _mutate_PermanentlyDeleteDocument(PermanentlyDeleteDocument, None, info, **kwargs)


def _mutate_EmptyTrash(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:1047

    Port of EmptyTrash.mutate
    """
    raise NotImplementedError("_mutate_EmptyTrash not yet ported — see manifest")


def m_empty_trash(info: strawberry.Info, corpus_id: Annotated[str, strawberry.argument(name="corpusId", description='Global ID of the corpus to empty trash for')] = strawberry.UNSET) -> Optional["EmptyTrash"]:
    kwargs = strip_unset({"corpus_id": corpus_id})
    return _mutate_EmptyTrash(EmptyTrash, None, info, **kwargs)


def _mutate_EmptyCorpus(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:1115

    Port of EmptyCorpus.mutate
    """
    raise NotImplementedError("_mutate_EmptyCorpus not yet ported — see manifest")


def m_empty_corpus(info: strawberry.Info, corpus_id: Annotated[str, strawberry.argument(name="corpusId", description='Global ID of the corpus to empty')] = strawberry.UNSET) -> Optional["EmptyCorpus"]:
    kwargs = strip_unset({"corpus_id": corpus_id})
    return _mutate_EmptyCorpus(EmptyCorpus, None, info, **kwargs)


def _mutate_UploadAnnotatedDocument(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:584

    Port of UploadAnnotatedDocument.mutate
    """
    raise NotImplementedError("_mutate_UploadAnnotatedDocument not yet ported — see manifest")


def m_import_annotated_doc_to_corpus(info: strawberry.Info, document_import_data: Annotated[str, strawberry.argument(name="documentImportData")] = strawberry.UNSET, target_corpus_id: Annotated[str, strawberry.argument(name="targetCorpusId")] = strawberry.UNSET) -> Optional["UploadAnnotatedDocument"]:
    kwargs = strip_unset({"document_import_data": document_import_data, "target_corpus_id": target_corpus_id})
    return _mutate_UploadAnnotatedDocument(UploadAnnotatedDocument, None, info, **kwargs)


def _mutate_StartCorpusExport(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:662

    Port of StartCorpusExport.mutate
    """
    raise NotImplementedError("_mutate_StartCorpusExport not yet ported — see manifest")


def m_export_corpus(info: strawberry.Info, analyses_ids: Annotated[Optional[list[Optional[str]]], strawberry.argument(name="analysesIds", description='Optional list of Graphene IDs for analyses that should be included in the export')] = strawberry.UNSET, annotation_filter_mode: Annotated[Optional[enums.AnnotationFilterMode], strawberry.argument(name="annotationFilterMode", description='How to filter annotations - from corpus label set only, plus analyses, or analyses only')] = enums.AnnotationFilterMode.CORPUS_LABELSET_ONLY, corpus_id: Annotated[str, strawberry.argument(name="corpusId", description='Graphene id of the corpus you want to package for export')] = strawberry.UNSET, export_format: Annotated[Optional[enums.ExportType], strawberry.argument(name="exportFormat")] = strawberry.UNSET, include_action_trail: Annotated[Optional[bool], strawberry.argument(name="includeActionTrail", description='Whether to include corpus action execution trail in the export (V2 format only)')] = False, include_conversations: Annotated[Optional[bool], strawberry.argument(name="includeConversations", description='Whether to include conversations and messages in the export (V2 format only)')] = False, input_kwargs: Annotated[Optional[GenericScalar], strawberry.argument(name="inputKwargs", description='Additional keyword arguments to pass to post-processors')] = strawberry.UNSET, post_processors: Annotated[Optional[list[Optional[str]]], strawberry.argument(name="postProcessors", description='List of fully qualified Python paths to post-processor functions to run')] = strawberry.UNSET) -> Optional["StartCorpusExport"]:
    kwargs = strip_unset({"analyses_ids": analyses_ids, "annotation_filter_mode": annotation_filter_mode, "corpus_id": corpus_id, "export_format": export_format, "include_action_trail": include_action_trail, "include_conversations": include_conversations, "input_kwargs": input_kwargs, "post_processors": post_processors})
    return _mutate_StartCorpusExport(StartCorpusExport, None, info, **kwargs)


def m_delete_export(info: strawberry.Info, id: Annotated[str, strawberry.argument(name="id")] = strawberry.UNSET) -> Optional["DeleteExport"]:
    kwargs = strip_unset({"id": id})
    return drf_deletion(payload_cls=DeleteExport, model=UserExport, lookup_field="id", root=None, info=info, kwargs=kwargs)



MUTATION_FIELDS = {
    "upload_document": strawberry.field(resolver=m_upload_document, name="uploadDocument"),
    "update_document": strawberry.field(resolver=m_update_document, name="updateDocument"),
    "update_document_summary": strawberry.field(resolver=m_update_document_summary, name="updateDocumentSummary", description="Mutation to update a document's markdown summary for a specific corpus, creating a new version in the process.\nUsers can create/update summaries if:\n- No summary exists yet and they have permission on the corpus (public or their corpus)\n- A summary exists and they are the original author"),
    "delete_document": strawberry.field(resolver=m_delete_document, name="deleteDocument"),
    "delete_multiple_documents": strawberry.field(resolver=m_delete_multiple_documents, name="deleteMultipleDocuments"),
    "upload_documents_zip": strawberry.field(resolver=m_upload_documents_zip, name="uploadDocumentsZip", description='Mutation for uploading multiple documents via a zip file.\nThe zip is stored as a temporary file and processed asynchronously.\nOnly files with allowed MIME types will be created as documents.'),
    "retry_document_processing": strawberry.field(resolver=m_retry_document_processing, name="retryDocumentProcessing", description="Retry processing for a failed document.\n\nThis mutation allows users to manually trigger reprocessing of a document\nthat failed during the parsing pipeline. It's useful when transient errors\n(like network timeouts or service unavailability) have been resolved.\n\nRequirements:\n- Document must be in FAILED processing state\n- User must have UPDATE permission on the document"),
    "restore_deleted_document": strawberry.field(resolver=m_restore_deleted_document, name="restoreDeletedDocument", description='Restore a soft-deleted document path within a corpus.\n\nDelegates to DocumentLifecycleService.restore_document() for:\n- Permission checking (corpus UPDATE permission)\n- Creating new DocumentPath with is_deleted=False'),
    "restore_document_to_version": strawberry.field(resolver=m_restore_document_to_version, name="restoreDocumentToVersion", description='Restore a document to a previous content version.\nCreates a new version that is a copy of the specified version.'),
    "permanently_delete_document": strawberry.field(resolver=m_permanently_delete_document, name="permanentlyDeleteDocument", description='Permanently delete a soft-deleted document from a corpus.\n\nThis is IRREVERSIBLE and removes:\n- All DocumentPath history for the document in this corpus\n- User annotations (non-structural) on the document\n- Relationships involving those annotations\n- DocumentSummaryRevision records\n- The Document itself if no other corpus references it\n\nRequires DELETE permission on the corpus.'),
    "empty_trash": strawberry.field(resolver=m_empty_trash, name="emptyTrash", description='Permanently delete ALL soft-deleted documents in a corpus (empty trash).\n\nThis is IRREVERSIBLE and removes all documents currently in the corpus trash.\n\nRequires DELETE permission on the corpus.'),
    "empty_corpus": strawberry.field(resolver=m_empty_corpus, name="emptyCorpus", description='Move EVERY document in a corpus to Trash and remove ALL of its folders.\n\nThis is the "empty everything" action. Documents are soft-deleted (they\nremain in the trash and are restorable until the trash is emptied); the\nfolder tree is removed. Nothing is permanently deleted here — callers can\nfollow up with ``emptyTrash`` to purge.\n\nRequires DELETE permission on the corpus.'),
    "import_annotated_doc_to_corpus": strawberry.field(resolver=m_import_annotated_doc_to_corpus, name="importAnnotatedDocToCorpus"),
    "export_corpus": strawberry.field(resolver=m_export_corpus, name="exportCorpus", description='Mutation entrypoint for starting a corpus export.\nNow refactored to optionally accept a list of Analysis IDs (analyses_ids)\nthat should be included in the export. If analyses_ids are provided, then\nonly annotations/labels from those analyses are included. Otherwise, all\nannotations/labels for the corpus are included.'),
    "delete_export": strawberry.field(resolver=m_delete_export, name="deleteExport"),
}
