"""
Shared upload services used by both the GraphQL upload mutations
(``config/graphql/document_mutations.py``) and the multipart REST
endpoints in this app.

Centralising the logic here avoids duplicating permission, validation,
and storage handling across two transport surfaces, and keeps the only
real difference the way bytes are obtained (base64 string vs. uploaded
file stream).
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any, Optional

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
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
from opencontractserver.utils.permissioning import (
    set_permissions_for_obj_to_user,
    user_has_permission_for_obj,
)

logger = logging.getLogger(__name__)

User = get_user_model()

# Generic message returned for any corpus access failure (does-not-exist OR
# missing edit permission) so callers cannot enumerate corpus IDs they cannot
# see by comparing error strings.
CORPUS_NOT_FOUND_MSG = (
    "Corpus not found or you do not have permission to add documents to it"
)


@dataclass
class UploadResult:
    """Result of a single-document upload."""

    document: Optional[Document]
    error: Optional[str]
    status: Optional[str] = None  # 'created' | 'updated' from import_content


@dataclass
class ZipUploadResult:
    """Result of a bulk zip upload."""

    job_id: Optional[str]
    error: Optional[str]


def _resolve_pk(global_or_pk_id: Any) -> str:
    """
    Accept either a Relay global id (``base64(Type:pk)``) or a raw pk and
    return the underlying primary key string.

    REST callers may submit raw PKs, GraphQL callers always submit global ids.
    """
    if global_or_pk_id is None:
        return None
    raw = str(global_or_pk_id)
    try:
        # Will raise if not base64 / not Relay-encoded.
        _, pk = from_global_id(raw)
        return pk
    except Exception:
        return raw


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


def _check_usage_cap(user) -> None:
    if (
        user.is_usage_capped
        and user.document_set.count() > settings.USAGE_CAPPED_USER_DOC_CAP_COUNT - 1
    ):
        raise PermissionError(
            f"Your usage is capped at {settings.USAGE_CAPPED_USER_DOC_CAP_COUNT} "
            f"documents. Try deleting an existing document first or contact "
            f"the admin for a higher limit."
        )


def upload_document_for_user(
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
) -> UploadResult:
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

    Returns an :class:`UploadResult`. On failure, ``document`` is ``None`` and
    ``error`` carries a user-safe message; the caller is responsible for
    mapping that to the appropriate transport response.
    """
    _check_usage_cap(user)

    # MIME detection
    kind = detect_mime_type(file_bytes, filename)
    if kind is None:
        return UploadResult(document=None, error="Unable to determine file type")
    if kind not in get_allowed_mime_types():
        return UploadResult(document=None, error=f"Unallowed filetype: {kind}")

    # Corpus + folder resolution
    folder = None
    if add_to_corpus_id is not None:
        corpus_pk = _resolve_pk(add_to_corpus_id)
        try:
            corpus = Corpus.objects.visible_to_user(user).get(id=corpus_pk)
        except (Corpus.DoesNotExist, ValueError, TypeError):
            return UploadResult(document=None, error=CORPUS_NOT_FOUND_MSG)

        if not user_has_permission_for_obj(user, corpus, PermissionTypes.EDIT):
            return UploadResult(document=None, error=CORPUS_NOT_FOUND_MSG)

        if add_to_folder_id is not None:
            folder_pk = _resolve_pk(add_to_folder_id)
            try:
                folder = CorpusFolder.objects.get(pk=folder_pk, corpus=corpus)
            except (CorpusFolder.DoesNotExist, ValueError, TypeError):
                return UploadResult(
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
        logger.error(f"[UPLOAD] Error importing document: {e}")
        return UploadResult(document=None, error=f"Upload failed due to error: {e}")

    set_permissions_for_obj_to_user(user, document, [PermissionTypes.CRUD])
    logger.info(
        f"[UPLOAD] Document {document.id} ({status}) uploaded to corpus {corpus.id}"
    )
    return UploadResult(document=document, error=None, status=status)


def upload_documents_zip_for_user(
    *,
    user,
    zip_source: UploadedFile | bytes,
    zip_filename: str | None = None,
    title_prefix: str | None = None,
    description: str | None = None,
    custom_meta: dict | None = None,
    make_public: bool = False,
    add_to_corpus_id: Any = None,
) -> ZipUploadResult:
    """
    Stage a zip archive in a :class:`TemporaryFileHandle` and queue
    ``process_documents_zip`` to ingest it.

    ``zip_source`` may be raw bytes (legacy GraphQL/base64 path) or an
    :class:`UploadedFile` (REST/multipart path). The latter is preferred
    because it streams to storage without buffering the full archive in
    memory.

    Returns :class:`ZipUploadResult`. On failure, ``job_id`` is ``None``.
    """
    if user.is_usage_capped and not settings.USAGE_CAPPED_USER_CAN_IMPORT_CORPUS:
        raise PermissionError(
            "By default, usage-capped users cannot bulk upload documents. "
            "Please contact the admin to authorize your account."
        )

    job_id = str(uuid.uuid4())

    # Validate corpus before we stage anything: avoids creating an orphan
    # TemporaryFileHandle row for a request we're going to reject anyway.
    corpus_id: Optional[int] = None
    if add_to_corpus_id is not None:
        corpus_pk = _resolve_pk(add_to_corpus_id)
        try:
            corpus = Corpus.objects.visible_to_user(user).get(id=corpus_pk)
        except (Corpus.DoesNotExist, ValueError, TypeError):
            return ZipUploadResult(job_id=None, error=CORPUS_NOT_FOUND_MSG)
        if not user_has_permission_for_obj(user, corpus, PermissionTypes.EDIT):
            return ZipUploadResult(job_id=None, error=CORPUS_NOT_FOUND_MSG)
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
                from django.core.files.base import ContentFile

                temporary_file.file = ContentFile(
                    bytes(zip_source), name=storage_filename
                )
                temporary_file.save()
            else:
                # UploadedFile / File-like — write through Django storage
                # without loading the full archive into memory.
                temporary_file.file.save(storage_filename, zip_source, save=True)
    except Exception as e:  # noqa: BLE001
        logger.error(f"[UPLOAD-ZIP] Failed to stage zip: {e}")
        return ZipUploadResult(job_id=None, error=f"Failed to stage zip: {e}")

    # Launch async task. In test/eager mode the task runs synchronously
    # before the response is returned (matches the GraphQL mutation behaviour).
    if getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False):
        from celery import chain

        chain(
            process_documents_zip.s(
                temporary_file.id,
                user.id,
                job_id,
                title_prefix,
                description,
                custom_meta,
                make_public,
                corpus_id,
            )
        ).apply_async()
    else:
        from celery import chain

        transaction.on_commit(
            lambda: chain(
                process_documents_zip.s(
                    temporary_file.id,
                    user.id,
                    job_id,
                    title_prefix,
                    description,
                    custom_meta,
                    make_public,
                    corpus_id,
                )
            ).apply_async()
        )

    logger.info(f"[UPLOAD-ZIP] Zip job {job_id} staged for user {user.id}")
    return ZipUploadResult(job_id=job_id, error=None)
