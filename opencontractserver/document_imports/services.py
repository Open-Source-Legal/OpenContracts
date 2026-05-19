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
import uuid
from dataclasses import dataclass
from typing import Any

from celery import chain
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import UploadedFile
from django.db import transaction
from filetype import filetype
from graphql_relay import from_global_id

from opencontractserver.constants.zip_import import (
    BULK_UPLOAD_OWNER_CACHE_PREFIX,
    BULK_UPLOAD_OWNER_CACHE_TTL_SECONDS,
)
from opencontractserver.corpuses.models import Corpus, CorpusFolder, TemporaryFileHandle
from opencontractserver.documents.models import Document
from opencontractserver.pipeline.registry import get_allowed_mime_types
from opencontractserver.tasks import process_documents_zip
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


# Standard ZIP local-file-header signatures. ``PK\x03\x04`` is the normal
# header; ``PK\x05\x06`` is an empty archive; ``PK\x07\x08`` is a spanned
# archive. We accept any of them so legitimate edge-case archives still pass.
_ZIP_MAGIC_PREFIXES: tuple[bytes, ...] = (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")


def _peek_zip_magic(zip_source: UploadedFile | bytes) -> bool:
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
    file_bytes: bytes,
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

    Both ``add_to_corpus_id`` and ``add_to_folder_id`` accept either a Relay
    global id or a raw primary key — REST callers may use either.

    Returns an :class:`ImportResult`. On failure, ``document`` is ``None`` and
    ``error`` carries a user-safe message; the caller is responsible for
    mapping that to the appropriate transport response.
    """
    check_usage_cap(user)

    # MIME detection
    kind = detect_mime_type(file_bytes, filename)
    if kind is None:
        return ImportResult(document=None, error="Unable to determine file type")
    if kind not in get_allowed_mime_types():
        return ImportResult(document=None, error=f"Unallowed filetype: {kind}")

    # Corpus + folder resolution
    folder = None
    if add_to_corpus_id is not None:
        corpus_pk = _resolve_pk(add_to_corpus_id)
        try:
            corpus = Corpus.objects.visible_to_user(user).get(id=corpus_pk)
        except (Corpus.DoesNotExist, ValueError, TypeError):
            return ImportResult(document=None, error=CORPUS_NOT_FOUND_MSG)

        if not corpus.user_can(user, PermissionTypes.EDIT):
            return ImportResult(document=None, error=CORPUS_NOT_FOUND_MSG)

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
    zip_source: UploadedFile | bytes,
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
        corpus_pk = _resolve_pk(add_to_corpus_id)
        try:
            corpus = Corpus.objects.visible_to_user(user).get(id=corpus_pk)
        except (Corpus.DoesNotExist, ValueError, TypeError):
            return ZipImportResult(job_id=None, error=CORPUS_NOT_FOUND_MSG)
        if not corpus.user_can(user, PermissionTypes.EDIT):
            return ZipImportResult(job_id=None, error=CORPUS_NOT_FOUND_MSG)
        corpus_id = corpus.id

    # IDOR protection: bind this job_id to the requesting user so the
    # status resolver can refuse cross-user reads. Cache miss in the
    # status resolver fails closed.
    cache.set(
        f"{BULK_UPLOAD_OWNER_CACHE_PREFIX}{job_id}",
        user.id,
        BULK_UPLOAD_OWNER_CACHE_TTL_SECONDS,
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
