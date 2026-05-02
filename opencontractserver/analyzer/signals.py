import logging
from typing import Any

from celery import chain
from django.db import transaction

from opencontractserver.tasks.analyzer_tasks import (
    install_analyzer_task,
    request_gremlin_manifest,
)

logger = logging.getLogger(__name__)


def install_gremlin_on_creation(
    sender: Any, instance: Any, created: bool, **kwargs: Any
) -> None:
    # When we create a Gremlin object in DB, need to run async task to set it up
    if created:
        transaction.on_commit(
            lambda: chain(
                *[
                    request_gremlin_manifest.si(gremlin_id=instance.id),
                    install_analyzer_task.s(
                        gremlin_id=instance.id,
                    ),
                ]
            ).apply_async()
        )


def handle_analysis_completion(sender: Any, instance: Any, **kwargs: Any) -> None:
    """Handle analysis completion."""
    if hasattr(instance, "status") and instance.status == "COMPLETE":
        logger.info(f"Analysis {instance.id} completed")
