"""
Telemetry tasks for collecting and sending usage statistics.

These tasks run periodically to send anonymous usage metrics to PostHog,
helping guide development priorities without collecting any personal data.
"""

import logging

from django.conf import settings
from django.utils import timezone

from config import celery_app
from config.telemetry import record_event
from opencontractserver import __version__
from opencontractserver.users.models import Installation, SystemStats

logger = logging.getLogger(__name__)


@celery_app.task()
def send_usage_heartbeat() -> dict | None:
    """
    Send daily usage statistics heartbeat.

    Collects aggregate counts of users, documents, corpuses, annotations,
    and conversations, along with installation metadata.

    Returns:
        dict: The stats that were sent, or None if telemetry is disabled.
    """
    # Respect telemetry settings
    if settings.MODE == "TEST":
        logger.debug("Telemetry disabled in TEST mode")
        return None

    if not settings.TELEMETRY_ENABLED:
        logger.debug("Telemetry disabled via TELEMETRY_ENABLED setting")
        return None

    try:
        # Get installation metadata
        installation = Installation.get()
        age_days = (timezone.now() - installation.created).days

        # Collect usage statistics. The aggregate counts share a single
        # definition with the materialised SystemStats snapshot
        # (``SystemStats.compute_values()``) so telemetry and the in-app
        # headline tiles can never drift apart.
        stats = {
            # Usage counts (user_count, document_count, corpus_count,
            # annotation_count, conversation_count, message_count)
            **SystemStats.compute_values(),
            # Installation metadata
            "version": __version__,
            "installation_age_days": age_days,
        }

        record_event("usage_heartbeat", stats)
        logger.info(f"Usage heartbeat sent: {stats}")
        return stats

    except Exception as e:
        logger.warning(f"Failed to send usage heartbeat: {e}")
        return None
