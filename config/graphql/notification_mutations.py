"""
GraphQL mutations for the notification system.

This module implements Epic #562: Notification System
Sub-issue #564: Create GraphQL queries and mutations for notifications
"""

import logging

import graphene
from django.contrib.auth import get_user_model
from graphql_jwt.decorators import login_required
from graphql_relay import from_global_id

from config.graphql.graphene_types import NotificationType
from config.graphql.ratelimits import RateLimits, graphql_ratelimit
from opencontractserver.notifications.models import Notification

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
    def mutate(root, info, notification_id):
        user = info.context.user

        try:
            notification_pk = from_global_id(notification_id)[1]

            # Query by both ID and recipient in one query to prevent IDOR enumeration
            # This returns same error whether notification doesn't exist or belongs to another user
            notification = Notification.objects.get(pk=notification_pk, recipient=user)

            notification.mark_as_read()

            return MarkNotificationReadMutation(
                ok=True,
                message="Notification marked as read",
                notification=notification,
            )

        except Notification.DoesNotExist:
            # Same error whether notification doesn't exist or belongs to another user
            # This prevents enumeration of valid notification IDs
            return MarkNotificationReadMutation(
                ok=False,
                message="Notification not found",
                notification=None,
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
    def mutate(root, info, notification_id):
        user = info.context.user

        try:
            notification_pk = from_global_id(notification_id)[1]

            # Query by both ID and recipient in one query to prevent IDOR enumeration
            # This returns same error whether notification doesn't exist or belongs to another user
            notification = Notification.objects.get(pk=notification_pk, recipient=user)

            notification.mark_as_unread()

            return MarkNotificationUnreadMutation(
                ok=True,
                message="Notification marked as unread",
                notification=notification,
            )

        except Notification.DoesNotExist:
            # Same error whether notification doesn't exist or belongs to another user
            # This prevents enumeration of valid notification IDs
            return MarkNotificationUnreadMutation(
                ok=False,
                message="Notification not found",
                notification=None,
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
    def mutate(root, info):
        user = info.context.user

        try:
            # Update all unread notifications for the current user
            count = Notification.objects.filter(recipient=user, is_read=False).update(
                is_read=True
            )

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
    def mutate(root, info, notification_id):
        user = info.context.user

        try:
            notification_pk = from_global_id(notification_id)[1]

            # Query by both ID and recipient in one query to prevent IDOR enumeration
            # This returns same error whether notification doesn't exist or belongs to another user
            notification = Notification.objects.get(pk=notification_pk, recipient=user)

            notification.delete()

            return DeleteNotificationMutation(
                ok=True,
                message="Notification deleted successfully",
            )

        except Notification.DoesNotExist:
            # Same error whether notification doesn't exist or belongs to another user
            # This prevents enumeration of valid notification IDs
            return DeleteNotificationMutation(
                ok=False,
                message="Notification not found",
            )
        except Exception as e:
            logger.exception("Error deleting notification")
            return DeleteNotificationMutation(
                ok=False,
                message=f"Failed to delete notification: {str(e)}",
            )
