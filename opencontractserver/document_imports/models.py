"""
Models backing the chunked (resumable) multipart upload endpoints.

These exist to work around the per-request body ceiling imposed by
upstream proxies (Cloudflare caps proxied request bodies at 100 MB). A
client that needs to upload a file larger than that slices it into
sub-ceiling parts, ``POST``\\s each part independently, and then asks the
server to reassemble the parts and hand the whole file to the existing
single-document / zip import services.

Parts are persisted *through Django storage* (not local disk) for the
same reason ``worker_uploads`` stages to storage: in a multi-process /
multi-container deployment the process that reassembles a session is not
necessarily the one that received any given part, so every part must be
reachable from shared storage.

Orchestration lives in
``opencontractserver/document_imports/services.py`` (``start_chunked_upload``
/ ``store_chunk`` / ``complete_chunked_upload``); the transport lives in
``views.py``.
"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


def _chunk_part_path(instance: ChunkedUploadPart, filename: str) -> str:
    """
    Storage path for a single part.

    Grouping every part under its session id keeps cleanup cheap (delete
    the prefix) and avoids collisions between concurrent sessions. The
    zero-padded index keeps a natural lexical ordering for debugging.
    """
    return f"chunked_uploads/{instance.session_id}/part_{instance.index:06d}.bin"


class ChunkedUploadKind(models.TextChoices):
    """Which downstream import service a completed session is handed to."""

    DOCUMENT = "document", "Single document"
    DOCUMENTS_ZIP = "documents_zip", "Bulk documents zip"
    ZIP_TO_CORPUS = "zip_to_corpus", "Zip into corpus (folders preserved)"
    CORPUS_EXPORT = "corpus_export", "OpenContracts corpus export"


class ChunkedUploadStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"  # accepting parts
    ASSEMBLING = "ASSEMBLING", "Assembling"  # reassembly + import in flight
    COMPLETED = "COMPLETED", "Completed"
    FAILED = "FAILED", "Failed"


class ChunkedUploadSession(models.Model):
    """
    A single resumable, chunked upload.

    The row is created by ``start`` (status ``PENDING``), accumulates
    :class:`ChunkedUploadPart` rows as the client uploads parts, and is
    finalised by ``complete`` (status ``ASSEMBLING`` -> ``COMPLETED`` /
    ``FAILED``). ``metadata`` carries the import parameters that would
    otherwise be multipart form fields on the non-chunked endpoints
    (title, description, target corpus id, ...).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    creator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="chunked_upload_sessions",
        help_text="User who owns this upload (enforces per-user isolation).",
    )
    kind = models.CharField(max_length=32, choices=ChunkedUploadKind.choices)
    filename = models.CharField(max_length=512)
    total_size = models.BigIntegerField(
        help_text="Expected total assembled size in bytes (declared at start)."
    )
    chunk_size = models.BigIntegerField(
        help_text="Client part size in bytes (every part except the last)."
    )
    total_chunks = models.PositiveIntegerField(
        help_text="Number of parts the client will upload."
    )
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "Import parameters for the target service (title, description, "
            "corpus id, ...). Shape depends on ``kind``."
        ),
    )
    status = models.CharField(
        max_length=20,
        choices=ChunkedUploadStatus.choices,
        default=ChunkedUploadStatus.PENDING,
        db_index=True,
    )
    error_message = models.TextField(blank=True, default="")
    created = models.DateTimeField(default=timezone.now, db_index=True)
    modified = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created"]
        indexes = [
            # Explicit names (<=30 chars) keep the model + hand-written
            # initial migration in lockstep so makemigrations sees no drift.
            models.Index(
                fields=["creator", "status"], name="chunkup_creator_status_idx"
            ),
            models.Index(
                fields=["status", "created"], name="chunkup_status_created_idx"
            ),
        ]

    def __str__(self) -> str:
        return f"ChunkedUploadSession({self.id}, {self.kind}, {self.status})"


class ChunkedUploadPart(models.Model):
    """One uploaded slice of a :class:`ChunkedUploadSession`."""

    session = models.ForeignKey(
        ChunkedUploadSession,
        on_delete=models.CASCADE,
        related_name="parts",
    )
    index = models.PositiveIntegerField(help_text="Zero-based part index.")
    file = models.FileField(upload_to=_chunk_part_path)
    size = models.BigIntegerField(default=0, help_text="Part size in bytes.")
    created = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["index"]
        constraints = [
            models.UniqueConstraint(
                fields=["session", "index"], name="uniq_chunk_part_per_session"
            )
        ]

    def __str__(self) -> str:
        return f"ChunkedUploadPart(session={self.session_id}, index={self.index})"
