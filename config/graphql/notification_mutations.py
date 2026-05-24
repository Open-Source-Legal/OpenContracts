"""
GraphQL mutations for the notification system.

This module implements Epic #562: Notification System
Sub-issue #564: Create GraphQL queries and mutations for notifications.

Mutation bodies are thin wrappers around
:class:`opencontractserver.notifications.services.NotificationService` —
all ownership / IDOR-safety logic lives in the service.
"""

import logging

import graphene
from django.contrib.auth import get_user_model
from graphql_jwt.decorators import login_required
from graphql_relay import from_global_id

from config.graphql.graphene_types import NotificationType
from config.graphql.ratelimits import RateLimits, graphql_ratelimit
from opencontractserver.notifications.services import NotificationService

User = get_user_model()
logger = logging.getLogger(__name__)


class MarkNotificationReadMutation(graphene.Mutation):
    """Mark a single notification as read."""

    class Arguments:
        notification_id = graphene.ID(
            required=True, description="Notification ID to mark as read"
        )

    ok = graphene.Boolean()
    message = graphene.String()
    notification = graphene.Field(NotificationType)

    @login_required
    @graphql_ratelimit(rate=RateLimits.WRITE_LIGHT)
    def mutate(root, info, notification_id) -> "MarkNotificationReadMutation":
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


class MarkNotificationUnreadMutation(graphene.Mutation):
    """Mark a single notification as unread."""

    class Arguments:
        notification_id = graphene.ID(
            required=True, description="Notification ID to mark as unread"
        )

    ok = graphene.Boolean()
    message = graphene.String()
    notification = graphene.Field(NotificationType)

    @login_required
    @graphql_ratelimit(rate=RateLimits.WRITE_LIGHT)
    def mutate(root, info, notification_id) -> "MarkNotificationUnreadMutation":
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


class MarkAllNotificationsReadMutation(graphene.Mutation):
    """Mark all of the current user's notifications as read."""

    ok = graphene.Boolean()
    message = graphene.String()
    count = graphene.Int(description="Number of notifications marked as read")

    @login_required
    @graphql_ratelimit(rate=RateLimits.WRITE_LIGHT)
    def mutate(root, info) -> "MarkAllNotificationsReadMutation":
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


class DeleteNotificationMutation(graphene.Mutation):
    """Delete a notification."""

    class Arguments:
        notification_id = graphene.ID(
            required=True, description="Notification ID to delete"
        )

    ok = graphene.Boolean()
    message = graphene.String()

    @login_required
    @graphql_ratelimit(rate=RateLimits.WRITE_LIGHT)
    def mutate(root, info, notification_id) -> "DeleteNotificationMutation":
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
