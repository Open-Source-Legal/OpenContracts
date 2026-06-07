"""
Shared document-import services used by both the GraphQL upload
mutations (``config/graphql/document_mutations.py``) and the multipart
REST endpoints in this app.

Centralising the logic here avoids duplicating permission, validation,
and storage handling across two transport surfaces, and keeps the only
real difference the way bytes are obtained (base64 string vs. uploaded
file stream).

Both transports terminate in the same place — staging documents into a
corpus or queueing ``process_documents_zip`` (see
``opencontractserver/tasks/import_tasks.py``) — hence the "import"
naming. "Upload" survives only as the name of the transport verb on
the legacy GraphQL mutations.
"""

from __future__ import annotations

import logging
import math
import os
import tempfile
import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from celery import chain
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.base import ContentFile, File
from django.core.files.uploadedfile import UploadedFile
from django.db import models, transaction
from django.db.models.functions import Coalesce
from django.utils import timezone
from filetype import filetype
from graphql_relay import from_global_id

from opencontractserver.constants.zip_import import (
    BULK_UPLOAD_OWNER_CACHE_PREFIX,
    get_bulk_upload_owner_cache_ttl_seconds,
)
from opencontractserver.corpuses.models import Corpus, CorpusFolder, TemporaryFileHandle
from opencontractserver.document_imports.models import (
    ChunkedUploadKind,
    ChunkedUploadPart,
    ChunkedUploadSession,
    ChunkedUploadStatus,
)
from opencontractserver.documents.models import Document
from opencontractserver.pipeline.registry import get_allowed_mime_types
from opencontractserver.shared.services.conventions import ServiceResult
from opencontractserver.tasks import (
    import_corpus,
    import_zip_with_folder_structure,
    process_documents_zip,
)
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.files import is_plaintext_content
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

logger = logging.getLogger(__name__)

User = get_user_model()

# Generic message returned for any corpus access failure (does-not-exist OR
# missing edit permission) so callers cannot enumerate corpus IDs they cannot
# see by comparing error strings.
CORPUS_NOT_FOUND_MSG = (
    "Corpus not found or you do not have permission to add documents to it"
)


class DocumentImportPermissionError(PermissionError):
    """PermissionError raised by the import service layer.

    Carries a stable ``code`` so transports can map it to a fixed,
    public-safe response message instead of echoing ``str(e)`` —
    breaks the data flow CodeQL flags as ``py/stack-trace-exposure``.
    Inherits :class:`PermissionError` so existing GraphQL callers that
    let it propagate continue to see the same error type and ``str(e)``.
    """

    USAGE_CAP = "usage_cap"
    BULK_UPLOAD_DENIED = "bulk_upload_denied"

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass
class ImportResult:
    """Result of a single-document import."""

    document: Document | None
    error: str | None
    status: str | None = None  # 'created' | 'updated' from import_content


@dataclass
class ZipImportResult:
    """Result of a bulk zip import."""

    job_id: str | None
    error: str | None


@dataclass
class CorpusImportResult:
    """Result of an OpenContracts corpus-export zip import.

    Unlike the bulk-zip path, the corpus-export import creates a brand-new
    corpus synchronously (as a placeholder) and then asynchronously
    hydrates it from the zip. We surface the placeholder corpus so callers
    can deep-link or refresh their corpus list.
    """

    corpus: Corpus | None
    error: str | None


def _resolve_pk(global_or_pk_id: Any) -> str | None:
    """
    Accept either a Relay global id (``base64(Type:pk)``) or a raw pk and
    return the underlying primary key string.

    REST callers may submit raw PKs, GraphQL callers always submit global ids.

    Note that ``from_global_id`` is permissive: a non-base64 input like
    ``"1"`` does not raise — it returns ``ResolvedGlobalId(type='', id='')``.
    We treat any empty/blank decode result as a signal that the caller
    sent a raw PK and fall back to the original string.
    """
    if global_or_pk_id is None:
        return None
    raw = str(global_or_pk_id)
    try:
        type_name, pk = from_global_id(raw)
    except Exception:
        logger.debug("[IMPORT] _resolve_pk: malformed global id %r — using raw", raw)
        return raw
    if not type_name or not pk:
        return raw
    return pk


def normalise_optional(value: Any) -> str | None:
    """
    Treat blank/whitespace-only string fields as omitted.

    Shared by the REST views (multipart form fields) and the chunked
    services (JSON metadata values) so "" and "   " collapse to ``None``
    identically on both transports.
    """
    if value is None:
        return None
    if isinstance(value, str) and value.strip() == "":
        return None
    return value


def _resolve_corpus_for_edit(user, corpus_id: Any) -> tuple[Corpus | None, str | None]:
    """
    Resolve ``corpus_id`` (a Relay global id or a raw pk) to a corpus the
    ``user`` is allowed to EDIT.

    Returns ``(corpus, None)`` on success or ``(None, message)`` when the
    corpus is missing, invisible, or read-only — deliberately collapsing
    the does-not-exist and permission-denied cases into one IDOR-safe
    message so callers cannot enumerate corpus ids by diffing error
    strings. Centralised here because four import paths (single-document,
    bulk-zip, zip-to-corpus, and the chunked-upload pre-check) need the
    exact same visibility + EDIT gate.
    """
    corpus_pk = _resolve_pk(corpus_id)
    try:
        corpus = Corpus.objects.visible_to_user(user).get(id=corpus_pk)
    except (Corpus.DoesNotExist, ValueError, TypeError):
        return None, CORPUS_NOT_FOUND_MSG
    if not corpus.user_can(user, PermissionTypes.EDIT):
        return None, CORPUS_NOT_FOUND_MSG
    return corpus, None


# Standard ZIP local-file-header signatures. ``PK\x03\x04`` is the normal
# header; ``PK\x05\x06`` is an empty archive; ``PK\x07\x08`` is a spanned
# archive. We accept any of them so legitimate edge-case archives still pass.
_ZIP_MAGIC_PREFIXES: tuple[bytes, ...] = (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")


def _peek_zip_magic(zip_source: File | bytes) -> bool:
    """
    Return True iff ``zip_source`` begins with a recognised ZIP magic
    signature. For ``UploadedFile`` the stream is rewound after peeking
    so the subsequent storage write sees the full archive.
    """
    if isinstance(zip_source, (bytes, bytearray)):
        head = bytes(zip_source[:4])
    else:
        try:
            head = zip_source.read(4)
        finally:
            try:
                zip_source.seek(0)
            except Exception as exc:
                # If the stream cannot be rewound, the subsequent storage
                # write will be missing the first 4 magic bytes. Surface
                # this clearly rather than silently truncating the archive.
                logger.warning(
                    "Failed to rewind upload stream after ZIP magic peek; "
                    "subsequent write will be truncated: %s",
                    exc,
                )
    return any(head.startswith(prefix) for prefix in _ZIP_MAGIC_PREFIXES)


# Bytes sampled from the head of a streamed single-document upload for MIME
# detection. ``detect_mime_type`` only inspects a binary signature (filetype:
# <=261 bytes) and a plaintext sample (``is_plaintext_content``: first 1024
# bytes), so a header this size yields the exact same verdict as sniffing the
# whole file — while keeping peak memory negligible for a multi-GB upload.
DOCUMENT_MIME_SNIFF_BYTES = 8192


def _read_stream_header(file_obj: File, num_bytes: int) -> bytes:
    """
    Read up to ``num_bytes`` from the start of ``file_obj`` for content
    sniffing, then rewind so the subsequent full stream/store sees every byte.

    A failure to rewind would silently truncate the import, so it is surfaced
    loudly at WARNING rather than swallowed.
    """
    try:
        return file_obj.read(num_bytes)
    finally:
        try:
            file_obj.seek(0)
        except Exception as exc:  # pragma: no cover - non-seekable stream
            logger.warning(
                "Failed to rewind upload stream after header peek; subsequent "
                "import may be truncated: %s",
                exc,
            )


def detect_mime_type(file_bytes: bytes, filename: str | None) -> str | None:
    """
    Detect the MIME type of ``file_bytes`` using the same logic as the
    GraphQL upload path: prefer a binary signature match, then fall back
    to plaintext detection (with ``.md``/``.markdown``/``.caml``
    extensions promoted to ``text/markdown``).

    Returns the MIME string, or ``None`` if undetectable.
    """
    kind = filetype.guess(file_bytes)
    if kind is None:
        if is_plaintext_content(file_bytes):
            if filename and filename.lower().endswith((".caml", ".md", ".markdown")):
                return "text/markdown"
            return "text/plain"
        return None
    return kind.mime


def check_usage_cap(user) -> None:
    """
    Raise :class:`PermissionError` if ``user`` has hit the per-user
    document cap. Public so transports can run this check before any
    transport-specific resolution (e.g. ``ingestion_source_id`` lookup
    in the GraphQL upload mutation) — keeping the cap error visible to
    capped users even when other inputs are invalid.
    """
    if (
        user.is_usage_capped
        and user.document_set.count() > settings.USAGE_CAPPED_USER_DOC_CAP_COUNT - 1
    ):
        raise DocumentImportPermissionError(
            DocumentImportPermissionError.USAGE_CAP,
            f"Your usage is capped at {settings.USAGE_CAPPED_USER_DOC_CAP_COUNT} "
            f"documents. Try deleting an existing document first or contact "
            f"the admin for a higher limit.",
        )


def import_document_for_user(
    *,
    user,
    file_bytes: bytes | None = None,
    file_obj: File | None = None,
    filename: str,
    title: str,
    description: str,
    custom_meta: dict | None = None,
    make_public: bool = False,
    add_to_corpus_id: Any = None,
    add_to_folder_id: Any = None,
    slug: str | None = None,
    lineage_kwargs: dict | None = None,
) -> ImportResult:
    """
    Core upload path for a single document.

    Performs:
      - usage-cap enforcement
      - mime-type detection + allowlist check
      - corpus/folder resolution (visibility + EDIT permission)
      - ``corpus.import_content()`` storage
      - object-level CRUD permission grant to ``user``

    The content is provided either as ``file_bytes`` (the in-memory path used
    by the base64 GraphQL mutation and the multipart REST view) or as a Django
    ``file_obj`` (a seekable file-like). The ``file_obj`` path streams the
    document straight to storage and computes its hash by streaming, so a large
    upload never has to be buffered whole in RAM — exactly one of the two must
    be supplied (issue #1843).

    Both ``add_to_corpus_id`` and ``add_to_folder_id`` accept either a Relay
    global id or a raw primary key — REST callers may use either.

    Returns an :class:`ImportResult`. On failure, ``document`` is ``None`` and
    ``error`` carries a user-safe message; the caller is responsible for
    mapping that to the appropriate transport response.
    """
    if (file_bytes is None) == (file_obj is None):
        raise ValueError(
            "import_document_for_user requires exactly one of file_bytes or file_obj"
        )

    check_usage_cap(user)

    # MIME detection — sniff only a header when streaming so a multi-GB upload
    # isn't pulled into memory just to read its magic bytes.
    if file_bytes is not None:
        sniff_bytes = file_bytes
    elif file_obj is not None:
        # Narrows file_obj for _read_stream_header without an ``assert`` (which
        # ``python -O`` strips). The exactly-one-of guard above guarantees this
        # branch runs whenever file_bytes is None.
        sniff_bytes = _read_stream_header(file_obj, DOCUMENT_MIME_SNIFF_BYTES)
    else:  # pragma: no cover - unreachable given the exactly-one-of guard above
        raise AssertionError("exactly one of file_bytes or file_obj must be set")
    kind = detect_mime_type(sniff_bytes, filename)
    if kind is None:
        return ImportResult(document=None, error="Unable to determine file type")
    if kind not in get_allowed_mime_types():
        return ImportResult(document=None, error=f"Unallowed filetype: {kind}")

    # Corpus + folder resolution
    folder = None
    if add_to_corpus_id is not None:
        corpus, corpus_error = _resolve_corpus_for_edit(user, add_to_corpus_id)
        if corpus is None:
            return ImportResult(document=None, error=corpus_error)

        if add_to_folder_id is not None:
            folder_pk = _resolve_pk(add_to_folder_id)
            try:
                folder = CorpusFolder.objects.get(pk=folder_pk, corpus=corpus)
            except (CorpusFolder.DoesNotExist, ValueError, TypeError):
                return ImportResult(
                    document=None,
                    error="Folder not found in the specified corpus",
                )
    else:
        corpus = Corpus.get_or_create_personal_corpus(user)

    try:
        document, status, _ = corpus.import_content(
            content=file_bytes,
            content_file=file_obj,
            user=user,
            filename=filename,
            folder=folder,
            file_type=kind,
            title=title,
            description=description,
            custom_meta=custom_meta or {},
            backend_lock=True,
            is_public=make_public,
            slug=slug,
            **(lineage_kwargs or {}),
        )
    except Exception as e:  # noqa: BLE001
        logger.error(f"[IMPORT] Error importing document: {e}")
        return ImportResult(document=None, error=f"Import failed due to error: {e}")

    set_permissions_for_obj_to_user(user, document, [PermissionTypes.CRUD])
    logger.info(
        f"[IMPORT] Document {document.id} ({status}) imported into corpus {corpus.id}"
    )
    return ImportResult(document=document, error=None, status=status)


def import_documents_zip_for_user(
    *,
    user,
    zip_source: File | bytes,
    zip_filename: str | None = None,
    title_prefix: str | None = None,
    description: str | None = None,
    custom_meta: dict | None = None,
    make_public: bool = False,
    add_to_corpus_id: Any = None,
) -> ZipImportResult:
    """
    Stage a zip archive in a :class:`TemporaryFileHandle` and queue
    ``process_documents_zip`` to ingest it.

    ``zip_source`` may be raw bytes (legacy GraphQL/base64 path) or an
    :class:`UploadedFile` (REST/multipart path). The latter is preferred
    because it streams to storage without buffering the full archive in
    memory.

    Returns :class:`ZipImportResult`. On failure, ``job_id`` is ``None``.
    """
    if user.is_usage_capped and not settings.USAGE_CAPPED_USER_CAN_IMPORT_CORPUS:
        raise DocumentImportPermissionError(
            DocumentImportPermissionError.BULK_UPLOAD_DENIED,
            "By default, usage-capped users cannot bulk upload documents. "
            "Please contact the admin to authorize your account.",
        )

    # Reject non-zip uploads up front: the downstream
    # ``process_documents_zip`` task will fail in confusing ways if handed
    # a PDF, so we'd rather surface an explicit error to the caller.
    if not _peek_zip_magic(zip_source):
        return ZipImportResult(
            job_id=None,
            error="Uploaded file does not appear to be a valid ZIP archive",
        )

    job_id = str(uuid.uuid4())

    # Validate corpus before we stage anything: avoids creating an orphan
    # TemporaryFileHandle row for a request we're going to reject anyway.
    corpus_id: int | None = None
    if add_to_corpus_id is not None:
        corpus, corpus_error = _resolve_corpus_for_edit(user, add_to_corpus_id)
        if corpus is None:
            return ZipImportResult(job_id=None, error=corpus_error)
        corpus_id = corpus.id

    # IDOR protection: bind this job_id to the requesting user so the
    # status resolver can refuse cross-user reads. Cache miss in the
    # status resolver fails closed.
    cache.set(
        f"{BULK_UPLOAD_OWNER_CACHE_PREFIX}{job_id}",
        user.id,
        get_bulk_upload_owner_cache_ttl_seconds(),
    )

    storage_filename = f"documents_zip_import_{job_id}.zip"

    try:
        with transaction.atomic():
            temporary_file = TemporaryFileHandle.objects.create()
            if isinstance(zip_source, (bytes, bytearray)):
                temporary_file.file = ContentFile(
                    bytes(zip_source), name=storage_filename
                )
                temporary_file.save()
            else:
                # UploadedFile / File-like — write through Django storage
                # without loading the full archive into memory.
                temporary_file.file.save(storage_filename, zip_source, save=True)
    except Exception as e:  # noqa: BLE001
        logger.error(f"[IMPORT-ZIP] Failed to stage zip: {e}")
        return ZipImportResult(job_id=None, error=f"Failed to stage zip: {e}")

    # Launch async task. In test/eager mode the task runs synchronously
    # before the response is returned (matches the GraphQL mutation behaviour).
    task_signature = process_documents_zip.s(
        temporary_file.id,
        user.id,
        job_id,
        title_prefix,
        description,
        custom_meta,
        make_public,
        corpus_id,
    )
    if getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False):
        chain(task_signature).apply_async()
    else:
        transaction.on_commit(lambda: chain(task_signature).apply_async())

    logger.info(f"[IMPORT-ZIP] Zip job {job_id} staged for user {user.id}")
    return ZipImportResult(job_id=job_id, error=None)


def import_zip_to_corpus_for_user(
    *,
    user,
    zip_source: File | bytes,
    corpus_id: Any,
    target_folder_id: Any = None,
    title_prefix: str | None = None,
    description: str | None = None,
    custom_meta: dict | None = None,
    make_public: bool = False,
) -> ZipImportResult:
    """
    Stage a zip in a :class:`TemporaryFileHandle` and queue
    ``import_zip_with_folder_structure`` to ingest it into ``corpus_id``,
    preserving the zip's folder hierarchy. Sidecar JSON / labels.json /
    relationships.csv handling lives in the celery task — this service is
    only responsible for permission gating, staging, and IDOR-safe
    enqueuing.

    ``zip_source`` may be raw bytes (legacy/test paths) or an
    :class:`UploadedFile` (REST/multipart path). The latter is preferred:
    Django streams it through storage without buffering the whole archive
    in memory.

    Both ``corpus_id`` and ``target_folder_id`` accept either a Relay
    global id or a raw primary key.

    Returns :class:`ZipImportResult`. On failure, ``job_id`` is ``None``
    and ``error`` carries a user-safe message.
    """
    if user.is_usage_capped and not settings.USAGE_CAPPED_USER_CAN_IMPORT_CORPUS:
        raise DocumentImportPermissionError(
            DocumentImportPermissionError.BULK_UPLOAD_DENIED,
            "By default, usage-capped users cannot bulk import documents. "
            "Please contact the admin to authorize your account.",
        )

    if not _peek_zip_magic(zip_source):
        return ZipImportResult(
            job_id=None,
            error="Uploaded file does not appear to be a valid ZIP archive",
        )

    corpus, corpus_error = _resolve_corpus_for_edit(user, corpus_id)
    if corpus is None:
        return ZipImportResult(job_id=None, error=corpus_error)

    target_folder_pk: int | None = None
    if target_folder_id is not None:
        folder_pk = _resolve_pk(target_folder_id)
        try:
            folder = CorpusFolder.objects.get(pk=folder_pk, corpus=corpus)
        except (CorpusFolder.DoesNotExist, ValueError, TypeError):
            return ZipImportResult(
                job_id=None,
                error="Target folder not found or does not belong to this corpus",
            )
        target_folder_pk = folder.id

    job_id = str(uuid.uuid4())
    cache.set(
        f"{BULK_UPLOAD_OWNER_CACHE_PREFIX}{job_id}",
        user.id,
        get_bulk_upload_owner_cache_ttl_seconds(),
    )

    storage_filename = f"zip_import_{job_id}.zip"
    try:
        with transaction.atomic():
            temporary_file = TemporaryFileHandle.objects.create()
            if isinstance(zip_source, (bytes, bytearray)):
                temporary_file.file = ContentFile(
                    bytes(zip_source), name=storage_filename
                )
                temporary_file.save()
            else:
                temporary_file.file.save(storage_filename, zip_source, save=True)
    except Exception as e:  # noqa: BLE001
        logger.error(
            f"[IMPORT-ZIP-FOLDERS] Failed to stage zip for user {user.id}: {e}"
        )
        # Generic user-facing message — the detailed exception only
        # appears in the server log so storage-backend internals (paths,
        # bucket names, DB errors) don't leak into the HTTP response.
        return ZipImportResult(
            job_id=None,
            error="Failed to stage the upload. Please try again.",
        )

    task_signature = import_zip_with_folder_structure.s(
        temporary_file.id,
        user.id,
        job_id,
        corpus.id,
        target_folder_pk,
        title_prefix,
        description,
        custom_meta,
        make_public,
    )
    if getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False):
        chain(task_signature).apply_async()
    else:
        transaction.on_commit(lambda: chain(task_signature).apply_async())

    logger.info(
        f"[IMPORT-ZIP-FOLDERS] Zip job {job_id} staged for user {user.id} "
        f"into corpus {corpus.id}"
    )
    return ZipImportResult(job_id=job_id, error=None)


def import_corpus_export_for_user(
    *,
    user,
    zip_source: File | bytes,
    reingest_and_remap: bool = True,
) -> CorpusImportResult:
    """
    Create a placeholder :class:`Corpus`, stage the OpenContracts export
    zip in a :class:`TemporaryFileHandle`, and queue ``import_corpus`` to
    hydrate the corpus from the export.

    The placeholder corpus is created synchronously (so the caller has
    something to deep-link / show in their corpus list immediately); the
    background task rewrites its title/description/etc. from the import.

    ``reingest_and_remap`` defaults to ``True`` here — this is the opt-out
    boundary for the **user-facing** corpus-export import (the REST
    ``CorpusExportImportView`` and the chunked-upload completion path both call
    this without overriding it). Re-parsing each document through the current
    pipeline and re-anchoring its non-structural annotations is the default
    behaviour for a user uploading an export; pass ``False`` to trust the
    export's baked PAWLs / structural layer instead. The lower-level
    ``import_corpus`` / ``import_corpus_v2`` tasks keep this **off** by default
    (explicit opt-in for direct/programmatic callers and fork); this function
    threads the flag through to them explicitly. See
    ``docs/development/2026-06-06-v2-import-reingest-remap.md``.

    Returns :class:`CorpusImportResult`. On failure, ``corpus`` is
    ``None`` and ``error`` carries a user-safe message. On a permission
    denial (``USAGE_CAPPED``) the function raises
    :class:`DocumentImportPermissionError` so the caller can map it to a
    403 rather than a generic 400.
    """
    if user.is_usage_capped and not settings.USAGE_CAPPED_USER_CAN_IMPORT_CORPUS:
        raise DocumentImportPermissionError(
            DocumentImportPermissionError.BULK_UPLOAD_DENIED,
            "By default, usage-capped users cannot import corpuses. "
            "Please contact the admin to authorize your account.",
        )

    if not _peek_zip_magic(zip_source):
        return CorpusImportResult(
            corpus=None,
            error="Uploaded file does not appear to be a valid ZIP archive",
        )

    storage_filename = f"corpus_import_{uuid.uuid4()}.zip"
    try:
        with transaction.atomic():
            corpus_obj = Corpus.objects.create(
                title="New Import",
                creator=user,
                backend_lock=False,
            )
            set_permissions_for_obj_to_user(user, corpus_obj, [PermissionTypes.CRUD])

            temporary_file = TemporaryFileHandle.objects.create()
            if isinstance(zip_source, (bytes, bytearray)):
                temporary_file.file = ContentFile(
                    bytes(zip_source), name=storage_filename
                )
                temporary_file.save()
            else:
                temporary_file.file.save(storage_filename, zip_source, save=True)
    except Exception as e:  # noqa: BLE001
        logger.error(
            f"[IMPORT-CORPUS] Failed to stage corpus export for user {user.id}: {e}"
        )
        # Generic user-facing message — see import_zip_to_corpus_for_user
        # for the rationale.
        return CorpusImportResult(
            corpus=None,
            error="Failed to stage the corpus export. Please try again.",
        )

    task_signature = import_corpus.s(
        temporary_file.id,
        user.id,
        corpus_obj.id,
        reingest_and_remap=reingest_and_remap,
    )
    if getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False):
        chain(task_signature).apply_async()
    else:
        transaction.on_commit(lambda: chain(task_signature).apply_async())

    logger.info(
        f"[IMPORT-CORPUS] Corpus export staged into corpus {corpus_obj.id} "
        f"for user {user.id}"
    )
    return CorpusImportResult(corpus=corpus_obj, error=None)


# ---------------------------------------------------------------------------
# Chunked (resumable) uploads
# ---------------------------------------------------------------------------
#
# Upstream proxies (Cloudflare) cap a single proxied request body at 100 MB.
# To upload anything larger the client slices the file into sub-ceiling parts,
# POSTs each part, then asks the server to reassemble and import. The three
# verbs below back the ``/api/imports/chunked/*`` endpoints; reassembly funnels
# straight back into the same ``import_*_for_user`` services the non-chunked
# endpoints use, so there is exactly one import code path per kind.

# Block size used when streaming stored parts into the reassembled temp file.
# Bounds peak memory during assembly to O(block), independent of file size.
# Operator-tunable via the ``CHUNK_ASSEMBLY_BLOCK_SIZE`` setting (env-backed).
CHUNK_ASSEMBLY_BLOCK_SIZE = settings.CHUNK_ASSEMBLY_BLOCK_SIZE

# Grace window (hours) before an ``ASSEMBLING`` session is treated as a crashed
# worker and made eligible for GC. Deliberately far larger than any real
# reassembly (which streams parts in a single synchronous ``complete`` request
# and finishes in seconds-to-minutes) so the staleness GC can never delete
# parts out from under a live assembly, while a worker that died mid-assembly
# is still eventually reclaimed. Operator-tunable via the
# ``CHUNKED_UPLOAD_ASSEMBLING_GRACE_HOURS`` setting (env-backed).
# See ``purge_stale_chunked_uploads``.
CHUNKED_UPLOAD_ASSEMBLING_GRACE_HOURS = settings.CHUNKED_UPLOAD_ASSEMBLING_GRACE_HOURS


class ChunkedUploadError(Exception):
    """
    Raised by the chunked-upload services for a client-correctable problem.

    Carries the HTTP status the transport should surface. Messages are
    fixed literals (never exception-derived) so nothing sensitive flows
    into the response body.
    """

    def __init__(self, message: str, http_status: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.http_status = http_status


@dataclass
class ChunkedSessionInfo:
    """Lightweight view of a session, returned by ``store_chunk`` / status."""

    session_id: str
    kind: str
    status: str
    total_chunks: int
    received_chunks: int
    total_size: int
    received_size: int


def _chunked_total_cap() -> int:
    """Total-size ceiling for a chunked upload (0 disables the check)."""
    return settings.MAX_DOCUMENT_IMPORT_SIZE_BYTES


def _chunked_part_cap() -> int:
    """
    Per-part ceiling. Must stay below the smallest upstream proxy body
    limit (Cloudflare: 100 MB) — a part that exceeds the proxy cap could
    never have reached us, so this mainly bounds abuse / misconfiguration.
    """
    return settings.CHUNKED_UPLOAD_PART_MAX_BYTES


def _chunked_max_parts() -> int:
    return settings.CHUNKED_UPLOAD_MAX_PARTS


def _session_info(session: ChunkedUploadSession) -> ChunkedSessionInfo:
    agg = session.parts.aggregate(count=models.Count("id"), total=models.Sum("size"))
    return ChunkedSessionInfo(
        session_id=str(session.id),
        kind=session.kind,
        status=session.status,
        total_chunks=session.total_chunks,
        received_chunks=agg["count"] or 0,
        total_size=session.total_size,
        received_size=agg["total"] or 0,
    )


def _check_bulk_upload_allowed(user) -> None:
    """Mirror the usage-cap gate the zip import services apply."""
    if user.is_usage_capped and not settings.USAGE_CAPPED_USER_CAN_IMPORT_CORPUS:
        raise DocumentImportPermissionError(
            DocumentImportPermissionError.BULK_UPLOAD_DENIED,
            "By default, usage-capped users cannot bulk upload documents. "
            "Please contact the admin to authorize your account.",
        )


def start_chunked_upload(
    *,
    user,
    kind: str,
    filename: str,
    total_size: int,
    chunk_size: int,
    total_chunks: int,
    metadata: dict | None = None,
) -> ChunkedUploadSession:
    """
    Validate a chunked-upload request and create a ``PENDING`` session.

    Runs every cheap check we can *before* the client streams hundreds of
    MB of parts: kind validity, size/part arithmetic, the per-endpoint
    total-size cap, the usage cap, and (where the target is known up
    front) the corpus EDIT gate. Expensive content validation
    (MIME-type, zip magic) still happens at ``complete`` time.

    Raises :class:`ChunkedUploadError` (client error, carries HTTP status)
    or :class:`DocumentImportPermissionError` (permission, 403).
    """
    metadata = metadata or {}

    if kind not in ChunkedUploadKind.values:
        raise ChunkedUploadError(f"Unknown upload kind: {kind}")

    # --- size / part arithmetic -------------------------------------------------
    if total_size <= 0 or chunk_size <= 0 or total_chunks <= 0:
        raise ChunkedUploadError("total_size, chunk_size and total_chunks must be > 0")
    if chunk_size > _chunked_part_cap():
        raise ChunkedUploadError("Declared chunk_size exceeds the per-part limit")
    if total_chunks > _chunked_max_parts():
        raise ChunkedUploadError("Too many parts for a single upload")
    if math.ceil(total_size / chunk_size) != total_chunks:
        raise ChunkedUploadError(
            "total_chunks is inconsistent with total_size and chunk_size"
        )

    cap = _chunked_total_cap()
    if cap > 0 and total_size > cap:
        raise ChunkedUploadError("File too large.", http_status=413)

    # --- per-kind fast-fail permission gates ------------------------------------
    if kind == ChunkedUploadKind.DOCUMENT:
        check_usage_cap(user)
        if not (metadata.get("title") or "").strip():
            raise ChunkedUploadError("title is required for a document upload")
        corpus_ref = normalise_optional(metadata.get("add_to_corpus_id"))
        if corpus_ref is not None:
            _, corpus_error = _resolve_corpus_for_edit(user, corpus_ref)
            if corpus_error is not None:
                raise ChunkedUploadError(corpus_error, http_status=403)
    else:
        _check_bulk_upload_allowed(user)
        if kind == ChunkedUploadKind.ZIP_TO_CORPUS:
            corpus_ref = normalise_optional(metadata.get("corpus_id"))
            if corpus_ref is None:
                raise ChunkedUploadError("corpus_id is required for zip_to_corpus")
            _, corpus_error = _resolve_corpus_for_edit(user, corpus_ref)
            if corpus_error is not None:
                raise ChunkedUploadError(corpus_error, http_status=403)
        elif kind == ChunkedUploadKind.DOCUMENTS_ZIP:
            corpus_ref = normalise_optional(metadata.get("add_to_corpus_id"))
            if corpus_ref is not None:
                _, corpus_error = _resolve_corpus_for_edit(user, corpus_ref)
                if corpus_error is not None:
                    raise ChunkedUploadError(corpus_error, http_status=403)

    session = ChunkedUploadSession.objects.create(
        creator=user,
        kind=kind,
        filename=filename or "upload",
        total_size=total_size,
        chunk_size=chunk_size,
        total_chunks=total_chunks,
        metadata=metadata,
        status=ChunkedUploadStatus.PENDING,
    )
    logger.info(
        "[CHUNKED] Session %s started by user %s (kind=%s, %s bytes / %s parts)",
        session.id,
        user.id,
        kind,
        total_size,
        total_chunks,
    )
    return session


def _get_owned_session(user, upload_id) -> ChunkedUploadSession:
    """
    Fetch a session the requester owns, or raise a generic 404.

    Filtering by ``creator`` (rather than fetching then comparing) closes
    the IDOR: a cross-user id is indistinguishable from a missing one.
    """
    try:
        return ChunkedUploadSession.objects.get(id=upload_id, creator=user)
    except (ChunkedUploadSession.DoesNotExist, ValueError, TypeError):
        raise ChunkedUploadError("Upload session not found", http_status=404)


def store_chunk(
    *,
    user,
    upload_id,
    index: int,
    chunk_file: UploadedFile,
) -> ChunkedSessionInfo:
    """
    Persist one part of a chunked upload (idempotent on ``index``).

    Re-uploading an index overwrites the previous part (deleting its
    storage object first) so a client can safely retry a failed part.
    """
    session = _get_owned_session(user, upload_id)
    if session.status != ChunkedUploadStatus.PENDING:
        raise ChunkedUploadError(
            "Upload session is not accepting parts", http_status=409
        )
    if index < 0 or index >= session.total_chunks:
        raise ChunkedUploadError("Part index out of range")

    size = chunk_file.size or 0
    if size <= 0:
        raise ChunkedUploadError("Empty part")
    if size > _chunked_part_cap():
        raise ChunkedUploadError("Part too large", http_status=413)
    # Every part is produced by ``Blob.slice`` and is therefore <= the
    # declared chunk_size; a larger part means a malformed client.
    if size > session.chunk_size:
        raise ChunkedUploadError("Part exceeds the declared chunk size")

    # Lock the session row for the duration of the check-then-write so two
    # concurrent uploads of the SAME (session, index) cannot both observe
    # ``existing is None`` and then race ``create()`` into the
    # ``uniq_chunk_part_per_session`` unique constraint (an unhandled
    # IntegrityError / 500). Serialising per session is coarse but the parts
    # of one session are rarely written in true parallel.
    with transaction.atomic():
        locked = ChunkedUploadSession.objects.select_for_update().get(pk=session.pk)
        existing = locked.parts.filter(index=index).first()
        if existing is not None:
            existing.file.delete(save=False)
            existing.file = chunk_file
            existing.size = size
            existing.save(update_fields=["file", "size"])
        else:
            ChunkedUploadPart.objects.create(
                session=locked, index=index, file=chunk_file, size=size
            )

        # Bump ``modified`` so the staleness GC measures time-since-last-activity.
        locked.save(update_fields=["modified"])
    # Report from ``locked`` (the freshly re-fetched, post-write row) rather
    # than the pre-transaction ``session`` snapshot. The immutable fields read
    # here (``total_chunks`` / ``total_size``) are identical on both, but using
    # ``locked`` keeps the source of truth unambiguous.
    return _session_info(locked)


def get_chunked_session_status(*, user, upload_id) -> ChunkedSessionInfo:
    """Return progress for a session the requester owns (resumability)."""
    return _session_info(_get_owned_session(user, upload_id))


def _safe_unlink(path: str) -> None:
    """
    Best-effort delete of an assembly temp file.

    A failure here is non-fatal: the file simply lingers in the OS temp
    directory (reclaimed by the OS/tmpreaper) and, crucially, in the
    assembler's error path the *original* exception is being re-raised, so
    we must not let an unlink error mask it. We therefore swallow
    ``OSError`` but record it at debug level rather than silently passing.
    """
    try:
        os.unlink(path)
    except OSError as exc:
        logger.debug("[CHUNKED] Could not remove temp file %s: %s", path, exc)


def _assemble_session_to_tempfile(session: ChunkedUploadSession):
    """
    Stream every part, in index order, into a single on-disk temp file.

    Returns an open, rewound :class:`tempfile.NamedTemporaryFile`. Peak
    memory is one ``CHUNK_ASSEMBLY_BLOCK_SIZE`` block regardless of total
    size; the caller owns closing + unlinking the returned file.
    """
    tmp = tempfile.NamedTemporaryFile(suffix="_chunked_upload", delete=False)
    try:
        for part in session.parts.order_by("index"):
            with part.file.open("rb") as fh:
                while True:
                    block = fh.read(CHUNK_ASSEMBLY_BLOCK_SIZE)
                    if not block:
                        break
                    tmp.write(block)
        tmp.flush()
        tmp.seek(0)
        return tmp
    except Exception:
        tmp.close()
        _safe_unlink(tmp.name)
        raise


def _delete_session_parts(session: ChunkedUploadSession) -> None:
    """Delete a session's part files from storage and their rows."""
    for part in session.parts.all():
        try:
            part.file.delete(save=False)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "[CHUNKED] Failed to delete part %s of session %s: %s",
                part.index,
                session.id,
                exc,
            )
    session.parts.all().delete()


def _mark_failed(session: ChunkedUploadSession, message: str) -> None:
    session.status = ChunkedUploadStatus.FAILED
    session.error_message = message
    session.save(update_fields=["status", "error_message", "modified"])


def complete_chunked_upload(
    *, user, upload_id
) -> tuple[str, ImportResult | ZipImportResult | CorpusImportResult]:
    """
    Reassemble a fully-uploaded session and run the matching import.

    Returns ``(kind, result)`` where ``result`` is the same dataclass the
    corresponding non-chunked service returns, so the transport can build
    an identical response. On a successful import the parts are deleted to
    reclaim storage; on failure they are left for the staleness GC so the
    client could re-attempt ``complete``.

    Raises :class:`ChunkedUploadError` (incomplete / bad state) or
    :class:`DocumentImportPermissionError` (propagated from the import
    service).
    """
    session = _get_owned_session(user, upload_id)
    if session.status != ChunkedUploadStatus.PENDING:
        raise ChunkedUploadError(
            f"Upload session is not completable (status={session.status})",
            http_status=409,
        )

    # Integrity: every part present exactly once, and the bytes add up.
    parts = list(session.parts.order_by("index"))
    if len(parts) != session.total_chunks or {p.index for p in parts} != set(
        range(session.total_chunks)
    ):
        raise ChunkedUploadError("Upload incomplete: missing one or more parts")
    received = sum(p.size for p in parts)
    if received != session.total_size:
        raise ChunkedUploadError(
            "Assembled size does not match the declared total_size"
        )

    # Atomically claim the session: a conditional UPDATE on status=PENDING is a
    # compare-and-swap, so only one of two simultaneous complete() calls flips
    # PENDING -> ASSEMBLING. A 0-row result means another request already
    # claimed it — refuse rather than assemble + import the same bytes twice
    # (which would create duplicate documents / jobs).
    claimed = ChunkedUploadSession.objects.filter(
        id=session.pk, creator=user, status=ChunkedUploadStatus.PENDING
    ).update(status=ChunkedUploadStatus.ASSEMBLING, modified=timezone.now())
    if claimed == 0:
        raise ChunkedUploadError(
            "Upload session is not completable (already being completed)",
            http_status=409,
        )
    session.refresh_from_db()

    md = session.metadata or {}
    tmp = _assemble_session_to_tempfile(session)
    try:
        kind = session.kind
        result: ImportResult | ZipImportResult | CorpusImportResult
        if kind == ChunkedUploadKind.DOCUMENT:
            # Hand the assembled temp file to the import service as a file-like
            # (issue #1843). Like the three ZIP kinds below, this streams the
            # document to storage and computes its hash by streaming, so peak
            # memory stays O(CHUNK_ASSEMBLY_BLOCK_SIZE) regardless of file size
            # instead of spiking to ~the whole file at ``complete`` time.
            result = import_document_for_user(
                user=user,
                file_obj=File(tmp, name=session.filename),
                filename=session.filename,
                title=md.get("title") or session.filename,
                description=normalise_optional(md.get("description")) or "",
                custom_meta=md.get("custom_meta") or {},
                make_public=bool(md.get("make_public", False)),
                add_to_corpus_id=normalise_optional(md.get("add_to_corpus_id")),
                add_to_folder_id=normalise_optional(md.get("add_to_folder_id")),
                slug=normalise_optional(md.get("slug")),
            )
        elif kind == ChunkedUploadKind.DOCUMENTS_ZIP:
            result = import_documents_zip_for_user(
                user=user,
                zip_source=File(tmp, name=session.filename),
                zip_filename=session.filename,
                title_prefix=normalise_optional(md.get("title_prefix")),
                description=normalise_optional(md.get("description")),
                custom_meta=md.get("custom_meta") or None,
                make_public=bool(md.get("make_public", False)),
                add_to_corpus_id=normalise_optional(md.get("add_to_corpus_id")),
            )
        elif kind == ChunkedUploadKind.ZIP_TO_CORPUS:
            result = import_zip_to_corpus_for_user(
                user=user,
                zip_source=File(tmp, name=session.filename),
                corpus_id=md.get("corpus_id"),
                target_folder_id=normalise_optional(md.get("target_folder_id")),
                title_prefix=normalise_optional(md.get("title_prefix")),
                description=normalise_optional(md.get("description")),
                custom_meta=md.get("custom_meta") or None,
                make_public=bool(md.get("make_public", False)),
            )
        else:  # ChunkedUploadKind.CORPUS_EXPORT
            result = import_corpus_export_for_user(
                user=user,
                zip_source=File(tmp, name=session.filename),
            )
    except DocumentImportPermissionError:
        _mark_failed(session, "Permission denied")
        raise
    except Exception as exc:  # noqa: BLE001
        logger.error("[CHUNKED] Assembly/import failed for %s: %s", session.id, exc)
        _mark_failed(session, "Import failed")
        raise ChunkedUploadError("Import failed", http_status=400)
    finally:
        tmp.close()
        _safe_unlink(tmp.name)

    if result.error:
        # A content-level rejection (bad MIME, not-a-zip, ...). Keep the row
        # for the client to read the reason; the GC reclaims the parts later.
        _mark_failed(session, result.error)
        return kind, result

    session.status = ChunkedUploadStatus.COMPLETED
    session.error_message = ""
    session.save(update_fields=["status", "error_message", "modified"])
    _delete_session_parts(session)
    logger.info("[CHUNKED] Session %s completed (kind=%s)", session.id, kind)
    return kind, result


def purge_stale_chunked_uploads(
    stale_hours: int | None = None,
    completed_retention_days: int | None = None,
) -> int:
    """
    Delete abandoned sessions (and their stored parts) older than the
    staleness window, plus COMPLETED sessions older than the retention
    window so the audit-trail rows don't accumulate unboundedly.

    PENDING/FAILED sessions are purged after ``stale_hours`` of inactivity.
    ASSEMBLING sessions are purged only after a longer grace window
    (``max(stale_hours, CHUNKED_UPLOAD_ASSEMBLING_GRACE_HOURS)``) so the GC
    never races a live ``complete`` reassembly. COMPLETED sessions — whose
    parts were already removed on completion, so only a small metadata row
    remains — are purged after ``completed_retention_days`` (0 keeps them
    forever).

    Returns the number of sessions purged.
    """
    hours = stale_hours
    if hours is None:
        hours = settings.CHUNKED_UPLOAD_STALE_HOURS
    retention_days = completed_retention_days
    if retention_days is None:
        retention_days = settings.CHUNKED_UPLOAD_COMPLETED_RETENTION_DAYS

    now = timezone.now()
    stale_cutoff = now - timedelta(hours=hours)
    # Purge abandoned PENDING/FAILED sessions after the stale window. ASSEMBLING
    # is excluded here: such a session is mid-reassembly inside a live
    # ``complete`` request whose ``_assemble_session_to_tempfile`` streams parts
    # WITHOUT holding the session row lock, so deleting its parts (even under
    # ``select_for_update``) could corrupt the in-flight assembly. ASSEMBLING is
    # reclaimed separately below on a much longer grace window.
    stale = (
        ChunkedUploadSession.objects.filter(modified__lt=stale_cutoff)
        .exclude(status=ChunkedUploadStatus.COMPLETED)
        .exclude(status=ChunkedUploadStatus.ASSEMBLING)
    )

    # A session still ASSEMBLING long past any plausible reassembly duration is
    # a crashed worker; reclaim it after the grace window (never less than the
    # configured stale window) so it cannot race a healthy in-progress assembly.
    assembling_grace_hours = max(hours, CHUNKED_UPLOAD_ASSEMBLING_GRACE_HOURS)
    assembling_cutoff = now - timedelta(hours=assembling_grace_hours)
    assembling_stale = ChunkedUploadSession.objects.filter(
        status=ChunkedUploadStatus.ASSEMBLING, modified__lt=assembling_cutoff
    )

    completed_stale = ChunkedUploadSession.objects.none()
    if retention_days > 0:
        completed_cutoff = now - timedelta(days=retention_days)
        completed_stale = ChunkedUploadSession.objects.filter(
            status=ChunkedUploadStatus.COMPLETED, modified__lt=completed_cutoff
        )

    # Stream each queryset with a bounded chunk size rather than materializing
    # every stale session into memory at once — the GC can run against a large
    # backlog (e.g. after a long outage) and must not load it all eagerly.
    purged = 0
    for qs in (stale, assembling_stale, completed_stale):
        for session in qs.iterator(chunk_size=100):
            _delete_session_parts(session)
            session.delete()
            purged += 1
    if purged:
        logger.info("[CHUNKED] Purged %s stale chunked-upload session(s)", purged)
    return purged


# Bulk document-zip import kinds surfaced on the admin ingestion monitor.
# CORPUS_EXPORT is intentionally excluded: corpus-export ZIP re-imports are
# tracked (with per-document failure counts) via PendingCorpusImport on the
# admin dashboard, so listing the upload-phase session here too would
# double-count that flow. DOCUMENT (single-file) is excluded as it is not a
# "bulk" import.
ADMIN_BULK_IMPORT_SESSION_KINDS = (
    ChunkedUploadKind.DOCUMENTS_ZIP,
    ChunkedUploadKind.ZIP_TO_CORPUS,
)


def list_chunked_sessions_for_admin(
    user: Any,
    *,
    status: str | None = None,
    limit: int | None = None,
    offset: int | None = None,
) -> ServiceResult[tuple[Any, int, int, int]]:
    """Install-wide bulk document-zip import sessions. **Superuser-only.**

    Diagnostics listing for the admin ingestion monitor: every
    :class:`ChunkedUploadSession` whose ``kind`` is a bulk document-zip import
    (``DOCUMENTS_ZIP`` / ``ZIP_TO_CORPUS``), across all users, newest first.
    Annotated with ``received_size`` / ``received_parts`` (summed from the
    session's stored parts) so the resolver can render upload progress without
    an extra round-trip — note these read 0 once a COMPLETED session's parts
    have been reclaimed.

    The superuser gate is enforced here (defence-in-depth) and the GraphQL
    resolver also gates before calling. ``status`` (case-insensitive) filters
    on ``ChunkedUploadStatus``. Returns a ``ServiceResult`` wrapping
    ``(page_queryset, total_count, effective_limit, effective_offset)`` — the
    same ``ServiceResult`` shape every other admin-ingestion service uses, so
    the resolver gates uniformly on ``result.ok`` instead of catching an
    exception.
    """
    from opencontractserver.constants.document_processing import (
        ADMIN_INGESTION_DEFAULT_PAGE_SIZE,
        ADMIN_INGESTION_MAX_PAGE_SIZE,
    )
    from opencontractserver.shared.services.base import BaseService

    if not getattr(user, "is_superuser", False):
        return ServiceResult.failure("Superuser privileges required.")

    qs = (
        ChunkedUploadSession.objects.filter(kind__in=ADMIN_BULK_IMPORT_SESSION_KINDS)
        .select_related("creator")
        .annotate(
            # Coalesce so a session with no parts annotates 0, not NULL —
            # safe-by-default for any caller that does arithmetic on it.
            received_size=Coalesce(models.Sum("parts__size"), 0),
            received_parts=models.Count("parts"),
        )
        .order_by("-created")
    )
    if status:
        qs = qs.filter(status=status.upper())

    total_count = qs.count()
    effective_limit, effective_offset = BaseService.clamp_pagination(
        limit,
        offset,
        default=ADMIN_INGESTION_DEFAULT_PAGE_SIZE,
        maximum=ADMIN_INGESTION_MAX_PAGE_SIZE,
    )
    page = qs[effective_offset : effective_offset + effective_limit]
    return ServiceResult.success((page, total_count, effective_limit, effective_offset))
