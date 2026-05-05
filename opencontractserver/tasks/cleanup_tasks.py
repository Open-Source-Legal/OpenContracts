#  Copyright (C) 2022  John Scrudato

import logging

from django.contrib.auth import get_user_model
from django.core.files.storage import default_storage
from django.db.models import FileField, Q

from config import celery_app
from opencontractserver.utils.cleanup import delete_analysis_and_annotations

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

User = get_user_model()


@celery_app.task()
def delete_analysis_and_annotations_task(analysis_pk: int | str = -1) -> bool:

    return delete_analysis_and_annotations(
        analysis_pk=analysis_pk,
    )


@celery_app.task()
def cleanup_orphaned_document_blobs_task(blob_paths: list[str]) -> int:
    """Remove blobs from storage that are no longer referenced by any
    ``Document`` row.

    Issue #1492: when a ``Document`` is deleted, its file-field blobs
    must be reclaimed from storage to keep storage cost bounded. The
    primitive in PR #1487 (``unique_blob_paths`` /
    ``safe_delete_field_blob``) protects shared blobs (issue #1464); this
    task is the second half — actually freeing storage for blobs that
    became orphans.

    The signal handlers in ``opencontractserver.documents.signals``
    capture blob paths during ``pre_delete`` and schedule this task via
    ``transaction.on_commit``. Re-checking orphan status here (not in the
    signal) provides two safety properties:

    1. Transaction safety: ``on_commit`` callbacks do not fire if the
       outer transaction rolls back, so a failed delete never reaches
       this task.
    2. Race robustness: between scheduling and execution, another
       process may have created or migrated a row that references the
       same path. The orphan check at execution time is the source of
       truth — only paths with zero live references on any FileField
       are removed.

    Args:
        blob_paths: List of storage keys to evaluate for cleanup. May
            contain duplicates; they are de-duplicated here.

    Returns:
        Number of blobs actually removed from storage.
    """
    if not blob_paths:
        return 0

    # Imported here so the task module stays import-cheap at worker boot.
    from opencontractserver.documents.models import Document

    blob_fields: list[str] = [
        field.name
        for field in Document._meta.get_fields()
        if isinstance(field, FileField)
    ]

    # OR across every FileField so a blob counts as "still referenced"
    # even if the surviving Document points at it from a different field
    # than the one the originally-deleted Document used.
    deleted_count = 0
    seen: set[str] = set()
    for path in blob_paths:
        if not path or path in seen:
            continue
        seen.add(path)

        reference_q = Q()
        for field_name in blob_fields:
            reference_q |= Q(**{field_name: path})

        if Document.objects.filter(reference_q).exists():
            logger.debug(
                "Skipping orphan-cleanup for %s: still referenced by a "
                "Document row",
                path,
            )
            continue

        try:
            if default_storage.exists(path):
                default_storage.delete(path)
                deleted_count += 1
                logger.info("Reclaimed orphaned document blob: %s", path)
            else:
                logger.debug(
                    "Orphan blob %s already absent from storage; nothing to do",
                    path,
                )
        except Exception:
            # Storage failures must not poison the task. Log loudly so a
            # surviving orphan can be reaped by a future management
            # command (out of scope for #1492).
            logger.exception(
                "Failed to delete orphan document blob %s from storage", path
            )

    return deleted_count
