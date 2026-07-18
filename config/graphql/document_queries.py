"""Generated strawberry GraphQL module (graphene migration).

Shape-generated from the graphene schema; stub functions marked PORT(...)
carry the ported business logic. See config/graphql_new/manifest.json.
"""

# mypy: disable-error-code="name-defined, valid-type, arg-type"
#   Code-generation artifacts of the strawberry schema bindings that
#   mypy's static pass cannot resolve, NOT real typing defects:
#     name-defined / valid-type — ``Annotated["XType", strawberry.lazy(...)]``
#       forward-reference strings + the runtime-generated ``*Connection``
#       types (``make_connection_types``).
#     arg-type — resolvers construct result types with ``to_global_id()``
#       (``str``) for ``strawberry.ID`` fields and return Django MODEL
#       instances where the field annotation names the strawberry type
#       (the graphene-django resolver contract). Both are correct at
#       runtime. Hand-written config/graphql/core/* stays fully checked.
# flake8: noqa: E501, F821 — generated strawberry schema module.
# E501: long GraphQL field/argument ``description=`` strings and the
# single-line generated resolver signatures (black cannot split string
# literals). F821: ``Annotated["XType", strawberry.lazy(...)]`` /
# ``cast("QuerySet", ...)`` forward-reference STRINGS that pyflakes
# resolves as names — the whole point of strawberry.lazy is to avoid the
# import (which would then be F401). Both are code-generation artifacts,
# not defects; hand-written modules (config/graphql/core/*, security.py,
# testing.py, filters.py, …) stay fully linted.

from __future__ import annotations

import logging
from typing import Annotated, Any

import strawberry
from django.conf import settings
from django.core.cache import cache
from django.db.models import Count, Q, Sum
from django.db.models.functions import Coalesce
from graphql import GraphQLError
from graphql_relay import from_global_id, to_global_id

from config.graphql import enums
from config.graphql._util import strip_unset
from config.graphql.core.auth import login_required
from config.graphql.core.filtering import setup_filterset
from config.graphql.core.relay import (
    get_node_from_global_id,
    resolve_django_connection,
)
from config.graphql.custom_resolvers import requests_doc_type_labels
from config.graphql.document_types import (
    INGESTION_SOURCE_GLOBAL_ID_TYPE,
    DocumentStatsType,
)
from config.graphql.filters import DocumentFilter, DocumentRelationshipFilter
from config.graphql.ratelimits import get_user_tier_rate, graphql_ratelimit_dynamic
from config.graphql.user_types import BulkDocumentUploadStatusType
from opencontractserver.constants.annotations import (
    DOCUMENT_RELATIONSHIP_QUERY_MAX_LIMIT,
)
from opencontractserver.constants.search import MAX_SELECT_ALL_DOCUMENT_IDS
from opencontractserver.constants.zip_import import BULK_UPLOAD_OWNER_CACHE_PREFIX
from opencontractserver.documents.models import (
    Document,
    DocumentRelationship,
    IngestionSource,
)
from opencontractserver.documents.services import DocumentRelationshipService
from opencontractserver.shared.services.base import BaseService

logger = logging.getLogger(__name__)


def _make_bulk_upload_status(**fields) -> BulkDocumentUploadStatusType:
    """Construct a ``BulkDocumentUploadStatusType`` payload.

    ``job_id``, ``document_ids`` and ``errors`` are resolver-backed fields on
    the strawberry type (excluded from the generated ``__init__``), so they
    are attached as instance attributes after construction — the field
    resolvers read them back via ``getattr``.
    """
    resolver_fields = ("job_id", "document_ids", "errors")
    init_kwargs = {k: v for k, v in fields.items() if k not in resolver_fields}
    obj = BulkDocumentUploadStatusType(**init_kwargs)
    for k in resolver_fields:
        if k in fields:
            setattr(obj, k, fields[k])
    return obj


def _bulk_upload_status_from_task_result(
    job_id: str, result: dict[str, Any]
) -> BulkDocumentUploadStatusType:
    """Map both supported ZIP-task result schemas to the GraphQL contract.

    ``process_documents_zip`` predates the folder-preserving importer and
    reports ``total_files`` / ``processed_files`` / ``error_files``. The newer
    ``import_zip_with_folder_structure`` task intentionally has more specific
    keys. Keep that task's detailed result intact while presenting one stable
    status shape to clients polling either import path.
    """
    skipped_files = result.get("skipped_files")
    if skipped_files is None:
        skipped_files = sum(
            result.get(key, 0) or 0
            for key in (
                "files_skipped_type",
                "files_skipped_size",
                "files_skipped_hidden",
                "files_skipped_path",
            )
        )

    return _make_bulk_upload_status(
        job_id=job_id,
        success=result.get("success", False),
        total_files=result.get("total_files", result.get("total_files_in_zip", 0)),
        processed_files=result.get("processed_files", result.get("files_processed", 0)),
        skipped_files=skipped_files,
        error_files=result.get("error_files", result.get("files_errored", 0)),
        document_ids=result.get("document_ids", []),
        errors=result.get("errors", []),
        completed=result.get("completed", True),
    )


@graphql_ratelimit_dynamic(get_rate=get_user_tier_rate("READ_LIGHT"))
def _resolve_Query_documents(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/ratelimit/decorators.py:57

    Port of DocumentQueryMixin.resolve_documents
    """
    # Use lightweight mode to skip heavy prefetches (doc_annotations,
    # rows, relationships, notes) that are unnecessary for list/TOC
    # queries requesting only basic document fields.
    # When the client asks for the ``doc_label_annotations`` alias
    # (the corpus list view's DOC_TYPE_LABEL badge), opt in to a
    # focused prefetch so the per-document
    # AnnotationService.get_document_annotations fall-through
    # in resolve_doc_annotations_optimized doesn't fire N times.
    # ``requests_doc_type_labels`` walks graphene-style AST attributes
    # (``field_nodes``/``fragments``/``variable_values``); strawberry exposes
    # the underlying graphql-core ResolveInfo as ``info._raw_info``.
    return BaseService.filter_visible(
        Document,
        info.context.user,
        request=info.context,
        lightweight=True,
        with_doc_label_annotations=requests_doc_type_labels(info._raw_info),
    )


def q_documents(
    info: strawberry.Info,
    offset: Annotated[
        int | None, strawberry.argument(name="offset")
    ] = strawberry.UNSET,
    before: Annotated[
        str | None, strawberry.argument(name="before")
    ] = strawberry.UNSET,
    after: Annotated[str | None, strawberry.argument(name="after")] = strawberry.UNSET,
    first: Annotated[int | None, strawberry.argument(name="first")] = strawberry.UNSET,
    last: Annotated[int | None, strawberry.argument(name="last")] = strawberry.UNSET,
    description: Annotated[
        str | None, strawberry.argument(name="description")
    ] = strawberry.UNSET,
    description__contains: Annotated[
        str | None, strawberry.argument(name="description_Contains")
    ] = strawberry.UNSET,
    id: Annotated[
        strawberry.ID | None, strawberry.argument(name="id")
    ] = strawberry.UNSET,
    title: Annotated[str | None, strawberry.argument(name="title")] = strawberry.UNSET,
    title__contains: Annotated[
        str | None, strawberry.argument(name="title_Contains")
    ] = strawberry.UNSET,
    company_search: Annotated[
        str | None, strawberry.argument(name="companySearch")
    ] = strawberry.UNSET,
    has_pdf: Annotated[
        bool | None, strawberry.argument(name="hasPdf")
    ] = strawberry.UNSET,
    has_annotations_with_ids: Annotated[
        str | None, strawberry.argument(name="hasAnnotationsWithIds")
    ] = strawberry.UNSET,
    in_corpus_with_id: Annotated[
        str | None, strawberry.argument(name="inCorpusWithId")
    ] = strawberry.UNSET,
    in_folder_id: Annotated[
        str | None, strawberry.argument(name="inFolderId")
    ] = strawberry.UNSET,
    has_label_with_title: Annotated[
        str | None, strawberry.argument(name="hasLabelWithTitle")
    ] = strawberry.UNSET,
    has_label_with_id: Annotated[
        str | None, strawberry.argument(name="hasLabelWithId")
    ] = strawberry.UNSET,
    text_search: Annotated[
        str | None, strawberry.argument(name="textSearch")
    ] = strawberry.UNSET,
    include_caml: Annotated[
        bool | None, strawberry.argument(name="includeCaml")
    ] = strawberry.UNSET,
) -> None | (
    Annotated[DocumentTypeConnection, strawberry.lazy("config.graphql.document_types")]
):
    kwargs = strip_unset(
        {
            "offset": offset,
            "before": before,
            "after": after,
            "first": first,
            "last": last,
            "description": description,
            "description__contains": description__contains,
            "id": id,
            "title": title,
            "title__contains": title__contains,
            "company_search": company_search,
            "has_pdf": has_pdf,
            "has_annotations_with_ids": has_annotations_with_ids,
            "in_corpus_with_id": in_corpus_with_id,
            "in_folder_id": in_folder_id,
            "has_label_with_title": has_label_with_title,
            "has_label_with_id": has_label_with_id,
            "text_search": text_search,
            "include_caml": include_caml,
        }
    )
    resolved = _resolve_Query_documents(None, info, **kwargs)
    return resolve_django_connection(
        resolved=resolved,
        info=info,
        args=kwargs,
        node_type_name="DocumentType",
        default_manager=Document._default_manager,
        filterset_class=setup_filterset(DocumentFilter),
        filter_args={
            "description": "description",
            "description__contains": "description__contains",
            "id": "id",
            "title": "title",
            "title__contains": "title__contains",
            "company_search": "company_search",
            "has_pdf": "has_pdf",
            "has_annotations_with_ids": "has_annotations_with_ids",
            "in_corpus_with_id": "in_corpus_with_id",
            "in_folder_id": "in_folder_id",
            "has_label_with_title": "has_label_with_title",
            "has_label_with_id": "has_label_with_id",
            "text_search": "text_search",
            "include_caml": "include_caml",
        },
    )


def _resolve_Query_document(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/document_queries.py:79

    Port of DocumentQueryMixin.resolve_document
    """
    document_id = kwargs.get("id")
    if not document_id:
        return None

    cache = getattr(info.context, "_resolver_cache", None)
    if cache is None:
        cache = {}
        info.context._resolver_cache = cache

    doc_cache = cache.setdefault("document", {})
    if document_id in doc_cache:
        return doc_cache[document_id]

    _, pk = from_global_id(document_id)
    # IDOR-safe single-doc fetch via service layer — returns None for
    # both not-found and not-visible. Historical behavior raised
    # DoesNotExist via ``.get(id=pk)``; we now consistently return None
    # so the resolver surfaces a nullable Document field.
    document = BaseService.get_or_none(
        Document, pk, info.context.user, request=info.context
    )

    doc_cache[document_id] = document
    return document


def q_document(
    info: strawberry.Info,
    id: Annotated[
        strawberry.ID | None, strawberry.argument(name="id")
    ] = strawberry.UNSET,
) -> None | (Annotated[DocumentType, strawberry.lazy("config.graphql.document_types")]):
    kwargs = strip_unset({"id": id})
    return _resolve_Query_document(None, info, **kwargs)


@login_required
@graphql_ratelimit_dynamic(get_rate=get_user_tier_rate("READ_LIGHT"))
def _resolve_Query_corpus_document_ids(root, info, in_corpus_with_id, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:128

    Port of DocumentQueryMixin.resolve_corpus_document_ids
    """
    # Start from the user's visible documents (service layer = E001-safe),
    # then reuse DocumentFilter so corpus/folder/search/label scoping is
    # byte-for-byte identical to ``resolve_documents`` — including the
    # descendant-aware folder filter and the corpus CAML exclusion.
    base = BaseService.filter_visible(
        Document,
        info.context.user,
        request=info.context,
        lightweight=True,
    )
    filter_data: dict[str, Any] = {"in_corpus_with_id": in_corpus_with_id}
    for key in (
        "in_folder_id",
        "text_search",
        "has_label_with_id",
        "has_annotations_with_ids",
        "include_caml",
    ):
        value = kwargs.get(key)
        if value is not None:
            filter_data[key] = value

    filtered = DocumentFilter(data=filter_data, queryset=base, request=info.context).qs

    # Cap the response so a Select-All on a very large corpus cannot return
    # an unbounded multi-megabyte id list (the READ_LIGHT limiter throttles
    # frequency, not payload size). Raise rather than truncate: a truncated
    # id set would make the follow-up bulk-remove silently miss documents.
    #
    # Fetch one row beyond the cap in a SINGLE round-trip: the length of this
    # slice — not a separate COUNT(*) — decides whether we're over the limit,
    # so the cap decision comes from one consistent query (no count()/
    # values_list() TOCTOU drift) and the common under-cap path is one DB hit.
    pks = list(filtered.values_list("pk", flat=True)[: MAX_SELECT_ALL_DOCUMENT_IDS + 1])
    if len(pks) > MAX_SELECT_ALL_DOCUMENT_IDS:
        # Only the rare over-cap error path pays for an exact count, purely to
        # make the message actionable ("matches 31,234 documents").
        matched = filtered.count()
        raise GraphQLError(
            f"This selection matches {matched:,} documents, which exceeds "
            f"the {MAX_SELECT_ALL_DOCUMENT_IDS:,}-document Select-All limit. "
            "Narrow the filter (folder, search, or label) and try again."
        )

    return [to_global_id("DocumentType", pk) for pk in pks]


def q_corpus_document_ids(
    info: strawberry.Info,
    in_corpus_with_id: Annotated[
        str, strawberry.argument(name="inCorpusWithId")
    ] = strawberry.UNSET,
    in_folder_id: Annotated[
        str | None, strawberry.argument(name="inFolderId")
    ] = strawberry.UNSET,
    text_search: Annotated[
        str | None, strawberry.argument(name="textSearch")
    ] = strawberry.UNSET,
    has_label_with_id: Annotated[
        str | None, strawberry.argument(name="hasLabelWithId")
    ] = strawberry.UNSET,
    has_annotations_with_ids: Annotated[
        str | None, strawberry.argument(name="hasAnnotationsWithIds")
    ] = strawberry.UNSET,
    include_caml: Annotated[
        bool | None, strawberry.argument(name="includeCaml")
    ] = strawberry.UNSET,
) -> list[strawberry.ID] | None:
    kwargs = strip_unset(
        {
            "in_corpus_with_id": in_corpus_with_id,
            "in_folder_id": in_folder_id,
            "text_search": text_search,
            "has_label_with_id": has_label_with_id,
            "has_annotations_with_ids": has_annotations_with_ids,
            "include_caml": include_caml,
        }
    )
    return _resolve_Query_corpus_document_ids(None, info, **kwargs)


@graphql_ratelimit_dynamic(get_rate=get_user_tier_rate("READ_LIGHT"))
def _resolve_Query_document_stats(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/ratelimit/decorators.py:200

    Port of DocumentQueryMixin.resolve_document_stats

    Aggregate counts mirroring the ``documents`` list resolver.
    """
    user = info.context.user

    # Strip absent filter args so DocumentFilter doesn't apply them.
    filter_data = {
        key: value for key, value in kwargs.items() if value is not None and value != ""
    }

    # ``lightweight=True`` skips prefetches we don't need for an
    # aggregation; counts read scalar columns and don't traverse
    # relations, so paying for prefetches here would be pure waste.
    visible = BaseService.filter_visible(
        Document, user, request=info.context, lightweight=True
    )
    filtered = DocumentFilter(data=filter_data, queryset=visible).qs

    # ``DocumentFilter.has_label_id`` joins ``doc_annotation`` (one row
    # per matching annotation), which would inflate ``Count`` and — more
    # importantly — ``Sum(page_count)`` because ``Sum(distinct=True)``
    # sums distinct *values*, not distinct *rows*. Re-base the aggregate
    # on an ``id__in`` subquery so each Document is counted exactly once.
    counts = Document.objects.filter(id__in=filtered.values("id")).aggregate(
        total_docs=Count("id"),
        total_pages=Coalesce(Sum("page_count"), 0),
        processed_count=Count("id", filter=Q(backend_lock=False)),
        processing_count=Count("id", filter=Q(backend_lock=True)),
    )
    # graphene resolved this field from a plain dict; strawberry's default
    # resolver is attribute-based, so construct the payload type instead.
    return DocumentStatsType(
        total_docs=counts["total_docs"],
        total_pages=counts["total_pages"],
        processed_count=counts["processed_count"],
        processing_count=counts["processing_count"],
    )


def q_document_stats(
    info: strawberry.Info,
    in_corpus_with_id: Annotated[
        str | None, strawberry.argument(name="inCorpusWithId")
    ] = strawberry.UNSET,
    has_label_with_id: Annotated[
        str | None, strawberry.argument(name="hasLabelWithId")
    ] = strawberry.UNSET,
    text_search: Annotated[
        str | None, strawberry.argument(name="textSearch")
    ] = strawberry.UNSET,
    include_caml: Annotated[
        bool | None, strawberry.argument(name="includeCaml")
    ] = strawberry.UNSET,
) -> None | (
    Annotated[DocumentStatsType, strawberry.lazy("config.graphql.document_types")]
):
    kwargs = strip_unset(
        {
            "in_corpus_with_id": in_corpus_with_id,
            "has_label_with_id": has_label_with_id,
            "text_search": text_search,
            "include_caml": include_caml,
        }
    )
    return _resolve_Query_document_stats(None, info, **kwargs)


@graphql_ratelimit_dynamic(get_rate=get_user_tier_rate("READ_LIGHT"))
def _resolve_Query_document_relationships(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/ratelimit/decorators.py:250

    Port of DocumentQueryMixin.resolve_document_relationships

    Resolve document relationships with proper permission filtering.
    Uses DocumentRelationshipService for consistent eager loading.
    """
    user = info.context.user

    # Parse optional filters
    corpus_id = kwargs.get("corpus_id")
    corpus_pk = int(from_global_id(corpus_id)[1]) if corpus_id else None

    document_id = kwargs.get("document_id")
    doc_pk = int(from_global_id(document_id)[1]) if document_id else None

    # Use the relationship service for visibility and eager loading
    # Pass request for request-level caching of visible IDs
    if doc_pk:
        # Get relationships for specific document
        queryset = DocumentRelationshipService.get_relationships_for_document(
            user=user,
            document_id=doc_pk,
            corpus_id=corpus_pk,
            request=info.context,
        )
    else:
        # Get all visible relationships with optional corpus filter
        queryset = DocumentRelationshipService.get_visible_relationships(
            user=user,
            corpus_id=corpus_pk,
            request=info.context,
        )

    return queryset.distinct().order_by("-created")


def q_document_relationships(
    info: strawberry.Info,
    corpus_id: Annotated[
        strawberry.ID | None, strawberry.argument(name="corpusId")
    ] = strawberry.UNSET,
    document_id: Annotated[
        strawberry.ID | None, strawberry.argument(name="documentId")
    ] = strawberry.UNSET,
    offset: Annotated[
        int | None, strawberry.argument(name="offset")
    ] = strawberry.UNSET,
    before: Annotated[
        str | None, strawberry.argument(name="before")
    ] = strawberry.UNSET,
    after: Annotated[str | None, strawberry.argument(name="after")] = strawberry.UNSET,
    first: Annotated[int | None, strawberry.argument(name="first")] = strawberry.UNSET,
    last: Annotated[int | None, strawberry.argument(name="last")] = strawberry.UNSET,
    relationship_type: Annotated[
        enums.DocumentsDocumentRelationshipRelationshipTypeChoices | None,
        strawberry.argument(name="relationshipType"),
    ] = strawberry.UNSET,
    source_document: Annotated[
        strawberry.ID | None, strawberry.argument(name="sourceDocument")
    ] = strawberry.UNSET,
    target_document: Annotated[
        strawberry.ID | None, strawberry.argument(name="targetDocument")
    ] = strawberry.UNSET,
    annotation_label: Annotated[
        strawberry.ID | None, strawberry.argument(name="annotationLabel")
    ] = strawberry.UNSET,
    creator: Annotated[
        strawberry.ID | None, strawberry.argument(name="creator")
    ] = strawberry.UNSET,
    is_public: Annotated[
        bool | None, strawberry.argument(name="isPublic")
    ] = strawberry.UNSET,
    annotation_label_text: Annotated[
        str | None, strawberry.argument(name="annotationLabelText")
    ] = strawberry.UNSET,
) -> None | (
    Annotated[
        DocumentRelationshipTypeConnection,
        strawberry.lazy("config.graphql.document_types"),
    ]
):
    kwargs = strip_unset(
        {
            "corpus_id": corpus_id,
            "document_id": document_id,
            "offset": offset,
            "before": before,
            "after": after,
            "first": first,
            "last": last,
            "relationship_type": relationship_type,
            "source_document": source_document,
            "target_document": target_document,
            "annotation_label": annotation_label,
            "creator": creator,
            "is_public": is_public,
            "annotation_label_text": annotation_label_text,
        }
    )
    resolved = _resolve_Query_document_relationships(None, info, **kwargs)
    return resolve_django_connection(
        resolved=resolved,
        info=info,
        args=kwargs,
        node_type_name="DocumentRelationshipType",
        default_manager=DocumentRelationship._default_manager,
        filterset_class=setup_filterset(DocumentRelationshipFilter),
        filter_args={
            "relationship_type": "relationship_type",
            "source_document": "source_document",
            "target_document": "target_document",
            "annotation_label": "annotation_label",
            "creator": "creator",
            "is_public": "is_public",
            "annotation_label_text": "annotation_label_text",
        },
        # Higher limit for Table of Contents which needs full hierarchy
        # (graphene original: DjangoFilterConnectionField(..., max_limit=DOCUMENT_RELATIONSHIP_QUERY_MAX_LIMIT)).
        max_limit=DOCUMENT_RELATIONSHIP_QUERY_MAX_LIMIT,
    )


def q_document_relationship(
    info: strawberry.Info,
    id: Annotated[
        strawberry.ID,
        strawberry.argument(name="id", description="The ID of the object"),
    ] = strawberry.UNSET,
) -> None | (
    Annotated[
        DocumentRelationshipType, strawberry.lazy("config.graphql.document_types")
    ]
):
    return get_node_from_global_id(info, id, only_type_name="DocumentRelationshipType")


@graphql_ratelimit_dynamic(get_rate=get_user_tier_rate("READ_LIGHT"))
def _resolve_Query_bulk_doc_relationships(root, info, document_id, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/ratelimit/decorators.py:319

    Port of DocumentQueryMixin.resolve_bulk_doc_relationships

    Bulk resolver for document relationships involving a specific document.
    Uses DocumentRelationshipService for proper eager loading.
    """
    user = info.context.user

    # Parse document_id (required)
    doc_pk = int(from_global_id(document_id)[1])

    # Parse optional corpus filter
    corpus_id = kwargs.get("corpus_id")
    corpus_pk = int(from_global_id(corpus_id)[1]) if corpus_id else None

    # Use the relationship service for visibility and eager loading
    queryset = DocumentRelationshipService.get_relationships_for_document(
        user=user,
        document_id=doc_pk,
        corpus_id=corpus_pk,
        request=info.context,
    )

    # Apply optional relationship_type filter
    relationship_type = kwargs.get("relationship_type")
    if relationship_type:
        queryset = queryset.filter(relationship_type=relationship_type)

    return queryset.distinct().order_by("-created")


def q_bulk_doc_relationships(
    info: strawberry.Info,
    corpus_id: Annotated[
        strawberry.ID | None, strawberry.argument(name="corpusId")
    ] = strawberry.UNSET,
    document_id: Annotated[
        strawberry.ID, strawberry.argument(name="documentId")
    ] = strawberry.UNSET,
    relationship_type: Annotated[
        str | None, strawberry.argument(name="relationshipType")
    ] = strawberry.UNSET,
) -> None | (
    list[
        None
        | (
            Annotated[
                DocumentRelationshipType,
                strawberry.lazy("config.graphql.document_types"),
            ]
        )
    ]
):
    kwargs = strip_unset(
        {
            "corpus_id": corpus_id,
            "document_id": document_id,
            "relationship_type": relationship_type,
        }
    )
    return _resolve_Query_bulk_doc_relationships(None, info, **kwargs)


@login_required
def _resolve_Query_bulk_document_upload_status(root, info, job_id):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:358

    Port of DocumentQueryMixin.resolve_bulk_document_upload_status

    Resolver for the bulk_document_upload_status query.

    This queries Redis for the status of a bulk document upload job.
    The status is stored as a result in Celery's backend.

    Args:
        info: GraphQL execution info
        job_id: The unique identifier for the upload job

    Returns:
        BulkDocumentUploadStatusType with the current job status
    """
    from config import celery_app

    # IDOR protection: ensure the requesting user is the one who enqueued
    # this job. Cache miss (expired or unknown) fails closed with the
    # same opaque "not found" response so attackers cannot distinguish
    # missing-job from another-user's-job.
    owner_id = cache.get(f"{BULK_UPLOAD_OWNER_CACHE_PREFIX}{job_id}")
    # Coerce to int defensively: some Django cache backends (e.g. Redis
    # with a custom serializer) deserialize integers as strings, which
    # would silently break the legitimate-owner equality check.
    try:
        owner_id_int = int(owner_id) if owner_id is not None else None
    except (TypeError, ValueError):
        owner_id_int = None
    if owner_id_int is None or owner_id_int != info.context.user.id:
        return _make_bulk_upload_status(
            job_id=job_id,
            success=False,
            completed=False,
            errors=["Bulk upload job not found."],
        )

    try:
        # Try to get the task result from Celery
        async_result = celery_app.AsyncResult(job_id)

        # Special handling for tests with CELERY_TASK_ALWAYS_EAGER=True
        if settings.CELERY_TASK_ALWAYS_EAGER:
            logger.info(
                f"CELERY_TASK_ALWAYS_EAGER is True, handling task {job_id} directly"
            )
            try:
                if async_result.ready() and async_result.successful():
                    # In eager mode, even with task_store_eager_result, sometimes the result
                    # doesn't properly propagate to the backend. For tests, we'll assume completion.
                    result = async_result.get()
                    logger.info(f"Direct task result in eager mode: {result}")
                    return _bulk_upload_status_from_task_result(job_id, result)
            except Exception as e:
                logger.info(f"Exception getting eager task result: {e}")
                # Continue with normal flow

        if async_result.ready():
            # Task is finished
            if async_result.successful():
                result = async_result.get()
                # Ensure it has the right structure
                return _bulk_upload_status_from_task_result(job_id, result)
            else:
                # Task failed
                return _make_bulk_upload_status(
                    job_id=job_id,
                    success=False,
                    completed=True,
                    errors=["Task failed with an exception"],
                )
        else:
            # Task is still running
            return _make_bulk_upload_status(
                job_id=job_id,
                success=False,
                completed=False,
                errors=["Task is still running"],
            )

    except Exception as e:
        logger.error(f"Error checking bulk upload status: {str(e)}")
        return _make_bulk_upload_status(
            job_id=job_id,
            success=False,
            completed=False,
            errors=[f"Error checking status: {str(e)}"],
        )


def q_bulk_document_upload_status(
    info: strawberry.Info,
    job_id: Annotated[str, strawberry.argument(name="jobId")] = strawberry.UNSET,
) -> None | (
    Annotated[
        BulkDocumentUploadStatusType, strawberry.lazy("config.graphql.user_types")
    ]
):
    kwargs = strip_unset({"job_id": job_id})
    return _resolve_Query_bulk_document_upload_status(None, info, **kwargs)


@login_required
@graphql_ratelimit_dynamic(get_rate=get_user_tier_rate("READ_LIGHT"))
def _resolve_Query_ingestion_sources(root, info, active_only=False, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:488

    Port of DocumentQueryMixin.resolve_ingestion_sources
    """
    qs = BaseService.filter_visible(
        IngestionSource, info.context.user, request=info.context
    )
    if active_only:
        qs = qs.filter(active=True)
    return qs.order_by("name")


def q_ingestion_sources(
    info: strawberry.Info,
    active_only: Annotated[
        bool | None,
        strawberry.argument(
            name="activeOnly", description="If true, only return active sources"
        ),
    ] = False,
) -> None | (
    list[
        None
        | (
            Annotated[
                IngestionSourceType, strawberry.lazy("config.graphql.document_types")
            ]
        )
    ]
):
    kwargs = strip_unset({"active_only": active_only})
    return _resolve_Query_ingestion_sources(None, info, **kwargs)


@login_required
@graphql_ratelimit_dynamic(get_rate=get_user_tier_rate("READ_LIGHT"))
def _resolve_Query_ingestion_source(root, info, id, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:509

    Port of DocumentQueryMixin.resolve_ingestion_source
    """
    try:
        type_name, pk = from_global_id(id)
        if not pk or type_name != INGESTION_SOURCE_GLOBAL_ID_TYPE:
            return None
    except (ValueError, TypeError):
        return None
    return BaseService.get_or_none(
        IngestionSource, pk, info.context.user, request=info.context
    )


def q_ingestion_source(
    info: strawberry.Info,
    id: Annotated[strawberry.ID, strawberry.argument(name="id")] = strawberry.UNSET,
) -> None | (
    Annotated[IngestionSourceType, strawberry.lazy("config.graphql.document_types")]
):
    kwargs = strip_unset({"id": id})
    return _resolve_Query_ingestion_source(None, info, **kwargs)


QUERY_FIELDS = {
    "documents": strawberry.field(resolver=q_documents, name="documents"),
    "document": strawberry.field(resolver=q_document, name="document"),
    "corpus_document_ids": strawberry.field(
        resolver=q_corpus_document_ids,
        name="corpusDocumentIds",
        description="Global IDs of every document matching the given corpus / folder / search filters, ignoring pagination. Powers the document grid's 'Select All' so a bulk remove acts on every matching document, not just the page the virtualized list happens to have loaded. The folder filter is descendant-aware and the same DocumentFilter that backs the paginated ``documents`` connection is applied, so the id set always matches the visible list under identical filters.",
    ),
    "document_stats": strawberry.field(
        resolver=q_document_stats,
        name="documentStats",
        description="Aggregate counts (total docs, total pages, processed, processing) over documents visible to the requesting user. Accepts the same filter args as the ``documents`` connection so the stat tiles on the Documents view stay accurate regardless of how many pages have been loaded into Apollo's cache.",
    ),
    "document_relationships": strawberry.field(
        resolver=q_document_relationships, name="documentRelationships"
    ),
    "document_relationship": strawberry.field(
        resolver=q_document_relationship, name="documentRelationship"
    ),
    "bulk_doc_relationships": strawberry.field(
        resolver=q_bulk_doc_relationships, name="bulkDocRelationships"
    ),
    "bulk_document_upload_status": strawberry.field(
        resolver=q_bulk_document_upload_status,
        name="bulkDocumentUploadStatus",
        description="Check the status of a bulk document upload job by job ID",
    ),
    "ingestion_sources": strawberry.field(
        resolver=q_ingestion_sources,
        name="ingestionSources",
        description="List ingestion sources owned by the current user",
    ),
    "ingestion_source": strawberry.field(
        resolver=q_ingestion_source,
        name="ingestionSource",
        description="Get a single ingestion source by ID",
    ),
}
