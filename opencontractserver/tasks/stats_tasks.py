"""Periodic tasks that materialise install-wide statistics (issue #1908).

``refresh_system_stats`` recomputes the :class:`SystemStats` singleton on a
schedule (see ``CELERY_BEAT_SCHEDULE`` in ``config/settings/base.py``) so that
headline surfaces read pre-computed counts instead of running full-table
``COUNT``s on every page load.
"""

import logging

from config import celery_app
from opencontractserver.users.models import SystemStats

logger = logging.getLogger(__name__)


@celery_app.task()
def refresh_system_stats() -> dict | None:
    """Recompute and persist the materialised :class:`SystemStats` snapshot.

    Returns the freshly computed counts on success, or ``None`` if the refresh
    failed (logged as a warning — a transient failure just means the previous
    snapshot is served until the next run).
    """
    try:
        instance = SystemStats.refresh()
        # Read the counts back off the refreshed row rather than recomputing
        # them — ``refresh()`` already ran every COUNT once.
        result = {field: getattr(instance, field) for field in SystemStats.COUNT_FIELDS}
        # ``refresh()`` always stamps ``computed_at`` before saving, so it is
        # non-null here (the field is nullable only for the pre-first-run row).
        computed_at = instance.computed_at
        result["computed_at"] = computed_at.isoformat() if computed_at else None
        logger.info("System stats refreshed: %s", result)
        return result
    except Exception as e:  # noqa: BLE001 — beat task must never crash the worker
        logger.warning("Failed to refresh system stats: %s", e)
        return None
