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

from config.graphql.filters import DocumentFilter
from config.graphql.filters import DocumentRelationshipFilter
from opencontractserver.documents.models import Document
from opencontractserver.documents.models import DocumentRelationship


def _resolve_Query_documents(root, info, **kwargs):
    """PORT: config/ratelimit/decorators.py:57

    Port of DocumentQueryMixin.resolve_documents
    """
    raise NotImplementedError("_resolve_Query_documents not yet ported — see manifest")


def q_documents(info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET, description: Annotated[Optional[str], strawberry.argument(name="description")] = strawberry.UNSET, description__contains: Annotated[Optional[str], strawberry.argument(name="description_Contains")] = strawberry.UNSET, id: Annotated[Optional[strawberry.ID], strawberry.argument(name="id")] = strawberry.UNSET, title: Annotated[Optional[str], strawberry.argument(name="title")] = strawberry.UNSET, title__contains: Annotated[Optional[str], strawberry.argument(name="title_Contains")] = strawberry.UNSET, company_search: Annotated[Optional[str], strawberry.argument(name="companySearch")] = strawberry.UNSET, has_pdf: Annotated[Optional[bool], strawberry.argument(name="hasPdf")] = strawberry.UNSET, has_annotations_with_ids: Annotated[Optional[str], strawberry.argument(name="hasAnnotationsWithIds")] = strawberry.UNSET, in_corpus_with_id: Annotated[Optional[str], strawberry.argument(name="inCorpusWithId")] = strawberry.UNSET, in_folder_id: Annotated[Optional[str], strawberry.argument(name="inFolderId")] = strawberry.UNSET, has_label_with_title: Annotated[Optional[str], strawberry.argument(name="hasLabelWithTitle")] = strawberry.UNSET, has_label_with_id: Annotated[Optional[str], strawberry.argument(name="hasLabelWithId")] = strawberry.UNSET, text_search: Annotated[Optional[str], strawberry.argument(name="textSearch")] = strawberry.UNSET, include_caml: Annotated[Optional[bool], strawberry.argument(name="includeCaml")] = strawberry.UNSET) -> Optional[Annotated["DocumentTypeConnection", strawberry.lazy("config.graphql.document_types")]]:
    kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last, "description": description, "description__contains": description__contains, "id": id, "title": title, "title__contains": title__contains, "company_search": company_search, "has_pdf": has_pdf, "has_annotations_with_ids": has_annotations_with_ids, "in_corpus_with_id": in_corpus_with_id, "in_folder_id": in_folder_id, "has_label_with_title": has_label_with_title, "has_label_with_id": has_label_with_id, "text_search": text_search, "include_caml": include_caml})
    resolved = _resolve_Query_documents(None, info, **kwargs)
    return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="DocumentType", default_manager=Document._default_manager, filterset_class=setup_filterset(DocumentFilter), filter_args={"description": "description", "description__contains": "description__contains", "id": "id", "title": "title", "title__contains": "title__contains", "company_search": "company_search", "has_pdf": "has_pdf", "has_annotations_with_ids": "has_annotations_with_ids", "in_corpus_with_id": "in_corpus_with_id", "in_folder_id": "in_folder_id", "has_label_with_title": "has_label_with_title", "has_label_with_id": "has_label_with_id", "text_search": "text_search", "include_caml": "include_caml"}, )


def _resolve_Query_document(root, info, **kwargs):
    """PORT: config/graphql/document_queries.py:79

    Port of DocumentQueryMixin.resolve_document
    """
    raise NotImplementedError("_resolve_Query_document not yet ported — see manifest")


def q_document(info: strawberry.Info, id: Annotated[Optional[strawberry.ID], strawberry.argument(name="id")] = strawberry.UNSET) -> Optional[Annotated["DocumentType", strawberry.lazy("config.graphql.document_types")]]:
    kwargs = strip_unset({"id": id})
    return _resolve_Query_document(None, info, **kwargs)


def _resolve_Query_corpus_document_ids(root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:128

    Port of DocumentQueryMixin.resolve_corpus_document_ids
    """
    raise NotImplementedError("_resolve_Query_corpus_document_ids not yet ported — see manifest")


def q_corpus_document_ids(info: strawberry.Info, in_corpus_with_id: Annotated[str, strawberry.argument(name="inCorpusWithId")] = strawberry.UNSET, in_folder_id: Annotated[Optional[str], strawberry.argument(name="inFolderId")] = strawberry.UNSET, text_search: Annotated[Optional[str], strawberry.argument(name="textSearch")] = strawberry.UNSET, has_label_with_id: Annotated[Optional[str], strawberry.argument(name="hasLabelWithId")] = strawberry.UNSET, has_annotations_with_ids: Annotated[Optional[str], strawberry.argument(name="hasAnnotationsWithIds")] = strawberry.UNSET, include_caml: Annotated[Optional[bool], strawberry.argument(name="includeCaml")] = strawberry.UNSET) -> Optional[list[strawberry.ID]]:
    kwargs = strip_unset({"in_corpus_with_id": in_corpus_with_id, "in_folder_id": in_folder_id, "text_search": text_search, "has_label_with_id": has_label_with_id, "has_annotations_with_ids": has_annotations_with_ids, "include_caml": include_caml})
    return _resolve_Query_corpus_document_ids(None, info, **kwargs)


def _resolve_Query_document_stats(root, info, **kwargs):
    """PORT: config/ratelimit/decorators.py:200

    Port of DocumentQueryMixin.resolve_document_stats
    """
    raise NotImplementedError("_resolve_Query_document_stats not yet ported — see manifest")


def q_document_stats(info: strawberry.Info, in_corpus_with_id: Annotated[Optional[str], strawberry.argument(name="inCorpusWithId")] = strawberry.UNSET, has_label_with_id: Annotated[Optional[str], strawberry.argument(name="hasLabelWithId")] = strawberry.UNSET, text_search: Annotated[Optional[str], strawberry.argument(name="textSearch")] = strawberry.UNSET, include_caml: Annotated[Optional[bool], strawberry.argument(name="includeCaml")] = strawberry.UNSET) -> Optional[Annotated["DocumentStatsType", strawberry.lazy("config.graphql.document_types")]]:
    kwargs = strip_unset({"in_corpus_with_id": in_corpus_with_id, "has_label_with_id": has_label_with_id, "text_search": text_search, "include_caml": include_caml})
    return _resolve_Query_document_stats(None, info, **kwargs)


def _resolve_Query_document_relationships(root, info, **kwargs):
    """PORT: config/ratelimit/decorators.py:250

    Port of DocumentQueryMixin.resolve_document_relationships
    """
    raise NotImplementedError("_resolve_Query_document_relationships not yet ported — see manifest")


def q_document_relationships(info: strawberry.Info, corpus_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="corpusId")] = strawberry.UNSET, document_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="documentId")] = strawberry.UNSET, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET, relationship_type: Annotated[Optional[enums.DocumentsDocumentRelationshipRelationshipTypeChoices], strawberry.argument(name="relationshipType")] = strawberry.UNSET, source_document: Annotated[Optional[strawberry.ID], strawberry.argument(name="sourceDocument")] = strawberry.UNSET, target_document: Annotated[Optional[strawberry.ID], strawberry.argument(name="targetDocument")] = strawberry.UNSET, annotation_label: Annotated[Optional[strawberry.ID], strawberry.argument(name="annotationLabel")] = strawberry.UNSET, creator: Annotated[Optional[strawberry.ID], strawberry.argument(name="creator")] = strawberry.UNSET, is_public: Annotated[Optional[bool], strawberry.argument(name="isPublic")] = strawberry.UNSET, annotation_label_text: Annotated[Optional[str], strawberry.argument(name="annotationLabelText")] = strawberry.UNSET) -> Optional[Annotated["DocumentRelationshipTypeConnection", strawberry.lazy("config.graphql.document_types")]]:
    kwargs = strip_unset({"corpus_id": corpus_id, "document_id": document_id, "offset": offset, "before": before, "after": after, "first": first, "last": last, "relationship_type": relationship_type, "source_document": source_document, "target_document": target_document, "annotation_label": annotation_label, "creator": creator, "is_public": is_public, "annotation_label_text": annotation_label_text})
    resolved = _resolve_Query_document_relationships(None, info, **kwargs)
    return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="DocumentRelationshipType", default_manager=DocumentRelationship._default_manager, filterset_class=setup_filterset(DocumentRelationshipFilter), filter_args={"relationship_type": "relationship_type", "source_document": "source_document", "target_document": "target_document", "annotation_label": "annotation_label", "creator": "creator", "is_public": "is_public", "annotation_label_text": "annotation_label_text"}, )


def q_document_relationship(info: strawberry.Info, id: Annotated[strawberry.ID, strawberry.argument(name="id", description='The ID of the object')] = strawberry.UNSET) -> Optional[Annotated["DocumentRelationshipType", strawberry.lazy("config.graphql.document_types")]]:
    return get_node_from_global_id(info, id, only_type_name="DocumentRelationshipType")


def _resolve_Query_bulk_doc_relationships(root, info, **kwargs):
    """PORT: config/ratelimit/decorators.py:319

    Port of DocumentQueryMixin.resolve_bulk_doc_relationships
    """
    raise NotImplementedError("_resolve_Query_bulk_doc_relationships not yet ported — see manifest")


def q_bulk_doc_relationships(info: strawberry.Info, corpus_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="corpusId")] = strawberry.UNSET, document_id: Annotated[strawberry.ID, strawberry.argument(name="documentId")] = strawberry.UNSET, relationship_type: Annotated[Optional[str], strawberry.argument(name="relationshipType")] = strawberry.UNSET) -> Optional[list[Optional[Annotated["DocumentRelationshipType", strawberry.lazy("config.graphql.document_types")]]]]:
    kwargs = strip_unset({"corpus_id": corpus_id, "document_id": document_id, "relationship_type": relationship_type})
    return _resolve_Query_bulk_doc_relationships(None, info, **kwargs)


def _resolve_Query_bulk_document_upload_status(root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:358

    Port of DocumentQueryMixin.resolve_bulk_document_upload_status
    """
    raise NotImplementedError("_resolve_Query_bulk_document_upload_status not yet ported — see manifest")


def q_bulk_document_upload_status(info: strawberry.Info, job_id: Annotated[str, strawberry.argument(name="jobId")] = strawberry.UNSET) -> Optional[Annotated["BulkDocumentUploadStatusType", strawberry.lazy("config.graphql.user_types")]]:
    kwargs = strip_unset({"job_id": job_id})
    return _resolve_Query_bulk_document_upload_status(None, info, **kwargs)


def _resolve_Query_ingestion_sources(root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:488

    Port of DocumentQueryMixin.resolve_ingestion_sources
    """
    raise NotImplementedError("_resolve_Query_ingestion_sources not yet ported — see manifest")


def q_ingestion_sources(info: strawberry.Info, active_only: Annotated[Optional[bool], strawberry.argument(name="activeOnly", description='If true, only return active sources')] = False) -> Optional[list[Optional[Annotated["IngestionSourceType", strawberry.lazy("config.graphql.document_types")]]]]:
    kwargs = strip_unset({"active_only": active_only})
    return _resolve_Query_ingestion_sources(None, info, **kwargs)


def _resolve_Query_ingestion_source(root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:509

    Port of DocumentQueryMixin.resolve_ingestion_source
    """
    raise NotImplementedError("_resolve_Query_ingestion_source not yet ported — see manifest")


def q_ingestion_source(info: strawberry.Info, id: Annotated[strawberry.ID, strawberry.argument(name="id")] = strawberry.UNSET) -> Optional[Annotated["IngestionSourceType", strawberry.lazy("config.graphql.document_types")]]:
    kwargs = strip_unset({"id": id})
    return _resolve_Query_ingestion_source(None, info, **kwargs)



QUERY_FIELDS = {
    "documents": strawberry.field(resolver=q_documents, name="documents"),
    "document": strawberry.field(resolver=q_document, name="document"),
    "corpus_document_ids": strawberry.field(resolver=q_corpus_document_ids, name="corpusDocumentIds", description="Global IDs of every document matching the given corpus / folder / search filters, ignoring pagination. Powers the document grid's 'Select All' so a bulk remove acts on every matching document, not just the page the virtualized list happens to have loaded. The folder filter is descendant-aware and the same DocumentFilter that backs the paginated ``documents`` connection is applied, so the id set always matches the visible list under identical filters."),
    "document_stats": strawberry.field(resolver=q_document_stats, name="documentStats", description="Aggregate counts (total docs, total pages, processed, processing) over documents visible to the requesting user. Accepts the same filter args as the ``documents`` connection so the stat tiles on the Documents view stay accurate regardless of how many pages have been loaded into Apollo's cache."),
    "document_relationships": strawberry.field(resolver=q_document_relationships, name="documentRelationships"),
    "document_relationship": strawberry.field(resolver=q_document_relationship, name="documentRelationship"),
    "bulk_doc_relationships": strawberry.field(resolver=q_bulk_doc_relationships, name="bulkDocRelationships"),
    "bulk_document_upload_status": strawberry.field(resolver=q_bulk_document_upload_status, name="bulkDocumentUploadStatus", description='Check the status of a bulk document upload job by job ID'),
    "ingestion_sources": strawberry.field(resolver=q_ingestion_sources, name="ingestionSources", description='List ingestion sources owned by the current user'),
    "ingestion_source": strawberry.field(resolver=q_ingestion_source, name="ingestionSource", description='Get a single ingestion source by ID'),
}
