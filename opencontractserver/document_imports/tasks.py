"""
Celery tasks for the document-imports app.

Currently just the periodic garbage collector for abandoned chunked-upload
sessions (see ``services.purge_stale_chunked_uploads``). Scheduled hourly via
``CELERY_BEAT_SCHEDULE`` in ``config/settings/base.py``.
"""

from __future__ import annotations

import logging

from celery import shared_task

from opencontractserver.document_imports.services import (
    purge_stale_chunked_uploads as _purge_stale_chunked_uploads,
)

logger = logging.getLogger(__name__)


@shared_task
def purge_stale_chunked_uploads(
    stale_hours: int | None = None,
    completed_retention_days: int | None = None,
) -> int:
    """
    Delete chunked-upload sessions (and their stored parts) abandoned for
    longer than the staleness window. Thin Celery wrapper around the
    service function so the deletion logic stays testable without Celery.

    Both windows fall back to their ``settings`` defaults when ``None``;
    exposing them here lets an operator override either at enqueue time
    (e.g. a one-off manual purge) without editing ``settings.py``.
    """
    purged = _purge_stale_chunked_uploads(stale_hours, completed_retention_days)
    logger.info("purge_stale_chunked_uploads removed %s session(s)", purged)
    return purged
