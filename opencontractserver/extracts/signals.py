"""
Signal handlers for Extract models.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

if TYPE_CHECKING:
    from opencontractserver.extracts.models import Datacell

logger = logging.getLogger(__name__)

# Signal UIDs for Extract/Datacell
DATACELL_SAVE_UID = "process_datacell_on_save_uid_v1"
DATACELL_DELETE_UID = "process_datacell_on_delete_uid_v1"


@receiver(post_save, sender="extracts.Datacell", dispatch_uid=DATACELL_SAVE_UID)
def handle_datacell_save(
    sender: type[Datacell],
    instance: Datacell,
    **kwargs: Any,
) -> None:
    """Handle datacell save."""
    # Currently a no-op as we use direct queries without caching
    pass


@receiver(post_delete, sender="extracts.Datacell", dispatch_uid=DATACELL_DELETE_UID)
def handle_datacell_delete(
    sender: type[Datacell],
    instance: Datacell,
    **kwargs: Any,
) -> None:
    """Handle datacell delete."""
    # Currently a no-op as we use direct queries without caching
    pass
