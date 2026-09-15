"""Stable receipt ownership, idempotent admission, and bounded retry."""

import hashlib
import re
from uuid import UUID

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from opencontractserver.utils.upload_identity import upload_payload_digest
from opencontractserver.worker_uploads.models import (
    UploadStatus,
    WorkerAccount,
    WorkerDocumentUpload,
)
from opencontractserver.worker_uploads.run_models import IngestionRun
from opencontractserver.worker_uploads.run_policy import (
    RunPolicyError,
    validate_preparation,
)
from opencontractserver.worker_uploads.run_services import runs_for_token

MAX_PROCESSING_ATTEMPTS = 3


class UploadConflict(ValueError):
    """A stable, safe conflict code for an upload operation."""


def receipts_for_token(token):
    return WorkerDocumentUpload.objects.filter(corpus_id=token.corpus_id).filter(
        Q(worker_account_id=token.worker_account_id)
        | Q(
            worker_account__isnull=True,
            corpus_access_token__worker_account_id=token.worker_account_id,
        )
    )


def stage_upload(token, file, metadata, client_key=None):
    if client_key is not None and not re.fullmatch(
        r"[A-Za-z0-9._:-]{1,128}", client_key
    ):
        raise ValueError("invalid_idempotency_key")
    identity = ""
    if client_key:
        sha = hashlib.sha256()
        for chunk in file.chunks():
            sha.update(chunk)
        file.seek(0)
        identity = upload_payload_digest(sha.hexdigest(), metadata)
    with transaction.atomic():
        if client_key:
            # Serialize admission for this account before FileField.save writes
            # a blob. The unique constraint is the final database guarantee.
            WorkerAccount.objects.select_for_update().get(pk=token.worker_account_id)
            existing = receipts_for_token(token).filter(client_key=client_key).first()
            if existing:
                if existing.payload_digest != identity:
                    raise UploadConflict("idempotency_conflict")
                return existing, False
        run = None
        if metadata.get("ingestion_run_id"):
            if not client_key:
                raise RunPolicyError("run_requires_idempotency_key")
            try:
                run = (
                    runs_for_token(token)
                    .select_for_update()
                    .get(pk=UUID(str(metadata["ingestion_run_id"])))
                )
            except (IngestionRun.DoesNotExist, ValueError, TypeError):
                raise RunPolicyError("run_not_found") from None
            if run.status != IngestionRun.Status.ACTIVE:
                raise RunPolicyError("run_not_active")
            validate_preparation(run, metadata)
        upload = WorkerDocumentUpload.objects.create(
            ingestion_run=run,
            corpus_access_token=token,
            worker_account=token.worker_account,
            corpus=token.corpus,
            file=file,
            metadata=metadata,
            client_key=client_key,
            payload_digest=identity,
        )
        return upload, True


def record_failure(upload, message):
    message = message[:1000]
    upload.error_message = message
    upload.error_history = [
        *upload.error_history,
        {
            "attempt": upload.processing_attempts,
            "message": message,
            "at": timezone.now().isoformat(),
        },
    ][-MAX_PROCESSING_ATTEMPTS:]


def retry_upload(token, upload_id):
    with transaction.atomic():
        upload = (
            receipts_for_token(token).select_for_update(of=("self",)).get(pk=upload_id)
        )
        if upload.status != UploadStatus.FAILED:
            return upload, False
        if upload.processing_attempts >= MAX_PROCESSING_ATTEMPTS:
            raise UploadConflict("retry_exhausted")
        if not upload.file or not upload.file.storage.exists(upload.file.name):
            raise UploadConflict("retry_artifact_unavailable")
        upload.corpus_access_token = token
        upload.status = UploadStatus.PENDING
        upload.processing_started = None
        upload.processing_finished = None
        upload.processing_token = None
        upload.save(
            update_fields=[
                "corpus_access_token",
                "status",
                "processing_started",
                "processing_finished",
                "processing_token",
            ]
        )
        return upload, True
