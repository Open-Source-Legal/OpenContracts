"""Generated strawberry GraphQL module (graphene migration).

Shape-generated from the graphene schema; stub functions marked PORT(...)
carry the ported business logic. See config/graphql_new/manifest.json.
"""

# mypy: disable-error-code="name-defined, valid-type, arg-type"
#   Code-generation artifacts of the strawberry schema bindings that
#   mypy's static pass cannot resolve, NOT real typing defects:
#     name-defined / valid-type — ``Annotated["XType", strawberry.lazy(...)]``
#       forward-reference strings + the runtime-generated ``*Connection``
#       types (``make_connection_types``).
#     arg-type — resolvers construct result types with ``to_global_id()``
#       (``str``) for ``strawberry.ID`` fields and return Django MODEL
#       instances where the field annotation names the strawberry type
#       (the graphene-django resolver contract). Both are correct at
#       runtime. Hand-written config/graphql/core/* stays fully checked.
# flake8: noqa: E501, F821 — generated strawberry schema module.
# E501: long GraphQL field/argument ``description=`` strings and the
# single-line generated resolver signatures (black cannot split string
# literals). F821: ``Annotated["XType", strawberry.lazy(...)]`` /
# ``cast("QuerySet", ...)`` forward-reference STRINGS that pyflakes
# resolves as names — the whole point of strawberry.lazy is to avoid the
# import (which would then be F401). Both are code-generation artifacts,
# not defects; hand-written modules (config/graphql/core/*, security.py,
# testing.py, filters.py, …) stay fully linted.

from __future__ import annotations

import logging
from typing import Annotated

import strawberry
from graphql_relay import from_global_id

from config.graphql._util import strip_unset
from config.graphql.core.auth import PermissionDenied
from config.graphql.core.relay import (
    register_type,
)
from config.graphql.ratelimits import RateLimits, graphql_ratelimit
from opencontractserver.notifications.services import NotificationService

logger = logging.getLogger(__name__)

# NOTE on decorators: the graphene mutations were decorated with
# ``@login_required`` + ``@graphql_ratelimit(...)`` on ``mutate(root, info, …)``.
# Mutate stubs here take ``payload_cls`` as their first positional argument,
# which does not match those decorators' ``(root, info, ...)`` calling
# convention — so ``login_required`` is inlined (see user_mutations.py) and
# ``graphql_ratelimit`` is applied to an inner function named ``mutate`` so
# the rate-limit cache group (defaults to the decorated function's
# ``__name__``) stays "mutate", exactly as in the graphene layer.


@strawberry.type(
    name="MarkNotificationReadMutation",
    description="Mark a single notification as read.",
)
class MarkNotificationReadMutation:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    notification: None | (
        Annotated[NotificationType, strawberry.lazy("config.graphql.social_types")]
    ) = strawberry.field(name="notification", default=None)


register_type("MarkNotificationReadMutation", MarkNotificationReadMutation, model=None)


@strawberry.type(
    name="MarkNotificationUnreadMutation",
    description="Mark a single notification as unread.",
)
class MarkNotificationUnreadMutation:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    notification: None | (
        Annotated[NotificationType, strawberry.lazy("config.graphql.social_types")]
    ) = strawberry.field(name="notification", default=None)


register_type(
    "MarkNotificationUnreadMutation", MarkNotificationUnreadMutation, model=None
)


@strawberry.type(
    name="MarkAllNotificationsReadMutation",
    description="Mark all of the current user's notifications as read.",
)
class MarkAllNotificationsReadMutation:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    count: int | None = strawberry.field(
        name="count", description="Number of notifications marked as read", default=None
    )


register_type(
    "MarkAllNotificationsReadMutation", MarkAllNotificationsReadMutation, model=None
)


@strawberry.type(
    name="DeleteNotificationMutation", description="Delete a notification."
)
class DeleteNotificationMutation:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)


register_type("DeleteNotificationMutation", DeleteNotificationMutation, model=None)


def _mutate_MarkNotificationReadMutation(payload_cls, root, info, notification_id):
    """PORT: /home/user/oc-graphene-ref/config/graphql/notification_mutations.py:39

    Port of MarkNotificationReadMutation.mutate
    """
    # @login_required — inlined (see module NOTE above).
    if not info.context.user.is_authenticated:
        raise PermissionDenied()

    @graphql_ratelimit(rate=RateLimits.WRITE_LIGHT)
    def mutate(root, info, notification_id):
        user = info.context.user

        try:
            notification_pk = from_global_id(notification_id)[1]
            result = NotificationService.mark_read(
                user, notification_pk, request=info.context
            )
            if not result.ok:
                return MarkNotificationReadMutation(
                    ok=False,
                    message=result.error,
                    notification=None,
                )

            return MarkNotificationReadMutation(
                ok=True,
                message="Notification marked as read",
                notification=result.value,
            )

        except Exception as e:
            logger.exception("Error marking notification as read")
            return MarkNotificationReadMutation(
                ok=False,
                message=f"Failed to mark notification as read: {str(e)}",
                notification=None,
            )

    return mutate(root, info, notification_id)


def m_mark_notification_read(
    info: strawberry.Info,
    notification_id: Annotated[
        strawberry.ID,
        strawberry.argument(
            name="notificationId", description="Notification ID to mark as read"
        ),
    ] = strawberry.UNSET,
) -> MarkNotificationReadMutation | None:
    kwargs = strip_unset({"notification_id": notification_id})
    return _mutate_MarkNotificationReadMutation(
        MarkNotificationReadMutation, None, info, **kwargs
    )


def _mutate_MarkNotificationUnreadMutation(payload_cls, root, info, notification_id):
    """PORT: /home/user/oc-graphene-ref/config/graphql/notification_mutations.py:83

    Port of MarkNotificationUnreadMutation.mutate
    """
    # @login_required — inlined (see module NOTE above).
    if not info.context.user.is_authenticated:
        raise PermissionDenied()

    @graphql_ratelimit(rate=RateLimits.WRITE_LIGHT)
    def mutate(root, info, notification_id):
        user = info.context.user

        try:
            notification_pk = from_global_id(notification_id)[1]
            result = NotificationService.mark_unread(
                user, notification_pk, request=info.context
            )
            if not result.ok:
                return MarkNotificationUnreadMutation(
                    ok=False,
                    message=result.error,
                    notification=None,
                )

            return MarkNotificationUnreadMutation(
                ok=True,
                message="Notification marked as unread",
                notification=result.value,
            )

        except Exception as e:
            logger.exception("Error marking notification as unread")
            return MarkNotificationUnreadMutation(
                ok=False,
                message=f"Failed to mark notification as unread: {str(e)}",
                notification=None,
            )

    return mutate(root, info, notification_id)


def m_mark_notification_unread(
    info: strawberry.Info,
    notification_id: Annotated[
        strawberry.ID,
        strawberry.argument(
            name="notificationId", description="Notification ID to mark as unread"
        ),
    ] = strawberry.UNSET,
) -> MarkNotificationUnreadMutation | None:
    kwargs = strip_unset({"notification_id": notification_id})
    return _mutate_MarkNotificationUnreadMutation(
        MarkNotificationUnreadMutation, None, info, **kwargs
    )


def _mutate_MarkAllNotificationsReadMutation(payload_cls, root, info):
    """PORT: /home/user/oc-graphene-ref/config/graphql/notification_mutations.py:122

    Port of MarkAllNotificationsReadMutation.mutate
    """
    # @login_required — inlined (see module NOTE above).
    if not info.context.user.is_authenticated:
        raise PermissionDenied()

    @graphql_ratelimit(rate=RateLimits.WRITE_LIGHT)
    def mutate(root, info):
        user = info.context.user

        try:
            result = NotificationService.mark_all_read(user, request=info.context)
            if not result.ok:
                return MarkAllNotificationsReadMutation(
                    ok=False,
                    message=result.error,
                    count=0,
                )
            count = result.value
            return MarkAllNotificationsReadMutation(
                ok=True,
                message=f"Marked {count} notification(s) as read",
                count=count,
            )

        except Exception as e:
            logger.exception("Error marking all notifications as read")
            return MarkAllNotificationsReadMutation(
                ok=False,
                message=f"Failed to mark all notifications as read: {str(e)}",
                count=0,
            )

    return mutate(root, info)


def m_mark_all_notifications_read(
    info: strawberry.Info,
) -> MarkAllNotificationsReadMutation | None:
    kwargs = strip_unset({})
    return _mutate_MarkAllNotificationsReadMutation(
        MarkAllNotificationsReadMutation, None, info, **kwargs
    )


def _mutate_DeleteNotificationMutation(payload_cls, root, info, notification_id):
    """PORT: /home/user/oc-graphene-ref/config/graphql/notification_mutations.py:162

    Port of DeleteNotificationMutation.mutate
    """
    # @login_required — inlined (see module NOTE above).
    if not info.context.user.is_authenticated:
        raise PermissionDenied()

    @graphql_ratelimit(rate=RateLimits.WRITE_LIGHT)
    def mutate(root, info, notification_id):
        user = info.context.user

        try:
            notification_pk = from_global_id(notification_id)[1]
            result = NotificationService.delete_for_user(
                user, notification_pk, request=info.context
            )
            if not result.ok:
                return DeleteNotificationMutation(ok=False, message=result.error)
            return DeleteNotificationMutation(
                ok=True,
                message="Notification deleted successfully",
            )

        except Exception as e:
            logger.exception("Error deleting notification")
            return DeleteNotificationMutation(
                ok=False,
                message=f"Failed to delete notification: {str(e)}",
            )

    return mutate(root, info, notification_id)


def m_delete_notification(
    info: strawberry.Info,
    notification_id: Annotated[
        strawberry.ID,
        strawberry.argument(
            name="notificationId", description="Notification ID to delete"
        ),
    ] = strawberry.UNSET,
) -> DeleteNotificationMutation | None:
    kwargs = strip_unset({"notification_id": notification_id})
    return _mutate_DeleteNotificationMutation(
        DeleteNotificationMutation, None, info, **kwargs
    )


MUTATION_FIELDS = {
    "mark_notification_read": strawberry.field(
        resolver=m_mark_notification_read,
        name="markNotificationRead",
        description="Mark a single notification as read.",
    ),
    "mark_notification_unread": strawberry.field(
        resolver=m_mark_notification_unread,
        name="markNotificationUnread",
        description="Mark a single notification as unread.",
    ),
    "mark_all_notifications_read": strawberry.field(
        resolver=m_mark_all_notifications_read,
        name="markAllNotificationsRead",
        description="Mark all of the current user's notifications as read.",
    ),
    "delete_notification": strawberry.field(
        resolver=m_delete_notification,
        name="deleteNotification",
        description="Delete a notification.",
    ),
}
