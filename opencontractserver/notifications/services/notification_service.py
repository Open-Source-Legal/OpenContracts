"""``Notification`` service — simple-ownership notification queries + mutations.

``Notification`` uses a **simple ownership model**: a notification belongs to
its ``recipient`` and is visible / mutable only to that user. There is no
``AnnotatePermissionsForReadMixin``, no guardian permission table, and no
``user_can`` manager method. Accordingly this service inherits ``BaseService``
for the shared ``log_action`` helper and architectural conformance, but does
not — and cannot — use ``get_or_none`` / ``filter_visible`` /
``require_permission`` (those delegate to ``user_can`` / ``visible_to_user``
which ``Notification`` does not implement).

The service is the canonical entry point for the
``config/graphql/notification_mutations.py`` mutations and the notification
resolvers in ``config/graphql/social_queries.py``.

Phase 5 of the service-layer centralization roadmap — see
``docs/refactor_plans/2026-05-19-service-layer-centralization-design.md``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from opencontractserver.shared.services.base import BaseService
from opencontractserver.shared.services.conventions import ServiceResult

if TYPE_CHECKING:
    from django.db.models import QuerySet

    from opencontractserver.notifications.models import Notification


class NotificationService(BaseService):
    """Ownership-gated ``Notification`` queries and mutations.

    Every public method that touches a single notification is **IDOR-safe**:
    it filters by ``recipient=user`` and returns ``None`` (read) /
    ``ServiceResult.failure("Notification not found")`` (write) for both
    not-found and another-user-owned rows. Callers cannot distinguish the
    two branches.
    """

    _NOT_FOUND_MSG = "Notification not found"

    # --- reads --------------------------------------------------------------

    @classmethod
    def list_for_user(
        cls,
        user: Any,
        *,
        request: Any = None,
    ) -> QuerySet:
        """Return the user's notifications with the standard prefetch shape.

        Returns an empty queryset for anonymous users (the resolver always
        gates auth, but the empty-queryset fallback keeps the service safe
        for internal callers).
        """
        from opencontractserver.notifications.models import Notification

        if user is None or not getattr(user, "is_authenticated", False):
            return Notification.objects.none()

        return (
            Notification.objects.filter(recipient=user)
            .select_related("actor", "message", "conversation", "recipient")
            .order_by("-created_at")
        )

    @classmethod
    def get_for_user(
        cls,
        user: Any,
        notification_pk: Any,
        *,
        request: Any = None,
    ) -> Notification | None:
        """IDOR-safe single-notification lookup.

        Returns ``None`` for both not-found and another-user-owned rows.
        Returns ``None`` immediately for anonymous users.
        """
        from opencontractserver.notifications.models import Notification

        if user is None or not getattr(user, "is_authenticated", False):
            return None

        try:
            return Notification.objects.get(pk=notification_pk, recipient=user)
        except Notification.DoesNotExist:
            return None

    @classmethod
    def unread_count(
        cls,
        user: Any,
        *,
        request: Any = None,
    ) -> int:
        """Return the number of unread notifications for ``user`` (0 if anon)."""
        from opencontractserver.notifications.models import Notification

        if user is None or not getattr(user, "is_authenticated", False):
            return 0
        return Notification.objects.filter(recipient=user, is_read=False).count()

    # --- writes -------------------------------------------------------------

    @classmethod
    def mark_read(
        cls,
        user: Any,
        notification_pk: Any,
        *,
        request: Any = None,
    ) -> ServiceResult[Notification]:
        """Mark a single notification as read.

        Returns the unified IDOR-safe failure when the notification doesn't
        exist or belongs to another user.
        """
        notification = cls.get_for_user(user, notification_pk, request=request)
        if notification is None:
            return ServiceResult.failure(cls._NOT_FOUND_MSG)
        notification.mark_as_read()
        cls.log_action("Marked read", notification, user)
        return ServiceResult.success(notification)

    @classmethod
    def mark_unread(
        cls,
        user: Any,
        notification_pk: Any,
        *,
        request: Any = None,
    ) -> ServiceResult[Notification]:
        """Mark a single notification as unread.

        Returns the unified IDOR-safe failure when the notification doesn't
        exist or belongs to another user.
        """
        notification = cls.get_for_user(user, notification_pk, request=request)
        if notification is None:
            return ServiceResult.failure(cls._NOT_FOUND_MSG)
        notification.mark_as_unread()
        cls.log_action("Marked unread", notification, user)
        return ServiceResult.success(notification)

    @classmethod
    def mark_all_read(
        cls,
        user: Any,
        *,
        request: Any = None,
    ) -> ServiceResult[int]:
        """Mark all unread notifications for ``user`` as read.

        Returns ``ServiceResult.success`` with the number of rows updated.
        Anonymous callers short-circuit to ``success(0)`` so the service is
        safe to call from non-GraphQL contexts without an external auth
        gate (matches the rest of the class).
        """
        from opencontractserver.notifications.models import Notification

        if user is None or not getattr(user, "is_authenticated", False):
            return ServiceResult.success(0)

        count = Notification.objects.filter(recipient=user, is_read=False).update(
            is_read=True
        )
        return ServiceResult.success(count)

    @classmethod
    def delete_for_user(
        cls,
        user: Any,
        notification_pk: Any,
        *,
        request: Any = None,
    ) -> ServiceResult[None]:
        """Delete a single notification.

        Returns the unified IDOR-safe failure when the notification doesn't
        exist or belongs to another user.
        """
        notification = cls.get_for_user(user, notification_pk, request=request)
        if notification is None:
            return ServiceResult.failure(cls._NOT_FOUND_MSG)
        cls.log_action("Deleted", notification, user)
        notification.delete()
        return ServiceResult.success(None)
