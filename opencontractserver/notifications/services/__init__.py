"""Notifications service-layer package.

Re-exports the public service so callers import a stable path::

    from opencontractserver.notifications.services import NotificationService

Phase 5 of the service-layer centralization roadmap — see
``docs/refactor_plans/2026-05-19-service-layer-centralization-design.md``.
"""

from opencontractserver.notifications.services.notification_service import (
    NotificationService,
)

__all__ = ["NotificationService"]
