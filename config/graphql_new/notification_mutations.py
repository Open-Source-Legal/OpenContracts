"""Generated strawberry GraphQL module (graphene migration).

Shape-generated from the graphene schema; stub functions marked PORT(...)
carry the ported business logic. See config/graphql_new/manifest.json.
"""
from __future__ import annotations

import datetime
import decimal
import uuid
from typing import Annotated, Any, Optional

import strawberry

from config.graphql.core import permissions as core_permissions
from config.graphql.core.filtering import filterset_factory, setup_filterset
from config.graphql.core.mutations import drf_deletion, drf_mutation
from config.graphql.core.relay import (
    Node,
    get_node_from_global_id,
    make_connection_types,
    register_type,
    resolve_django_connection,
    resolve_django_list,
)
from config.graphql.core.scalars import BigInt, GenericScalar, JSONString
from config.graphql_new._util import coerce_enum, coerce_str, strip_unset
from config.graphql_new import enums




@strawberry.type(name="MarkNotificationReadMutation", description='Mark a single notification as read.')
class MarkNotificationReadMutation:
    ok: Optional[bool] = strawberry.field(name="ok")
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))
    notification: Optional[Annotated["NotificationType", strawberry.lazy("config.graphql_new.social_types")]] = strawberry.field(name="notification")


register_type("MarkNotificationReadMutation", MarkNotificationReadMutation, model=None)


@strawberry.type(name="MarkNotificationUnreadMutation", description='Mark a single notification as unread.')
class MarkNotificationUnreadMutation:
    ok: Optional[bool] = strawberry.field(name="ok")
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))
    notification: Optional[Annotated["NotificationType", strawberry.lazy("config.graphql_new.social_types")]] = strawberry.field(name="notification")


register_type("MarkNotificationUnreadMutation", MarkNotificationUnreadMutation, model=None)


@strawberry.type(name="MarkAllNotificationsReadMutation", description="Mark all of the current user's notifications as read.")
class MarkAllNotificationsReadMutation:
    ok: Optional[bool] = strawberry.field(name="ok")
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))
    count: Optional[int] = strawberry.field(name="count", description='Number of notifications marked as read')


register_type("MarkAllNotificationsReadMutation", MarkAllNotificationsReadMutation, model=None)


@strawberry.type(name="DeleteNotificationMutation", description='Delete a notification.')
class DeleteNotificationMutation:
    ok: Optional[bool] = strawberry.field(name="ok")
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))


register_type("DeleteNotificationMutation", DeleteNotificationMutation, model=None)


def _mutate_MarkNotificationReadMutation(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:39

    Port of MarkNotificationReadMutation.mutate
    """
    raise NotImplementedError("_mutate_MarkNotificationReadMutation not yet ported — see manifest")


def m_mark_notification_read(info: strawberry.Info, notification_id: Annotated[strawberry.ID, strawberry.argument(name="notificationId", description='Notification ID to mark as read')] = strawberry.UNSET) -> Optional["MarkNotificationReadMutation"]:
    kwargs = strip_unset({"notification_id": notification_id})
    return _mutate_MarkNotificationReadMutation(MarkNotificationReadMutation, None, info, **kwargs)


def _mutate_MarkNotificationUnreadMutation(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:83

    Port of MarkNotificationUnreadMutation.mutate
    """
    raise NotImplementedError("_mutate_MarkNotificationUnreadMutation not yet ported — see manifest")


def m_mark_notification_unread(info: strawberry.Info, notification_id: Annotated[strawberry.ID, strawberry.argument(name="notificationId", description='Notification ID to mark as unread')] = strawberry.UNSET) -> Optional["MarkNotificationUnreadMutation"]:
    kwargs = strip_unset({"notification_id": notification_id})
    return _mutate_MarkNotificationUnreadMutation(MarkNotificationUnreadMutation, None, info, **kwargs)


def _mutate_MarkAllNotificationsReadMutation(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:122

    Port of MarkAllNotificationsReadMutation.mutate
    """
    raise NotImplementedError("_mutate_MarkAllNotificationsReadMutation not yet ported — see manifest")


def m_mark_all_notifications_read(info: strawberry.Info) -> Optional["MarkAllNotificationsReadMutation"]:
    kwargs = strip_unset({})
    return _mutate_MarkAllNotificationsReadMutation(MarkAllNotificationsReadMutation, None, info, **kwargs)


def _mutate_DeleteNotificationMutation(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:162

    Port of DeleteNotificationMutation.mutate
    """
    raise NotImplementedError("_mutate_DeleteNotificationMutation not yet ported — see manifest")


def m_delete_notification(info: strawberry.Info, notification_id: Annotated[strawberry.ID, strawberry.argument(name="notificationId", description='Notification ID to delete')] = strawberry.UNSET) -> Optional["DeleteNotificationMutation"]:
    kwargs = strip_unset({"notification_id": notification_id})
    return _mutate_DeleteNotificationMutation(DeleteNotificationMutation, None, info, **kwargs)



MUTATION_FIELDS = {
    "mark_notification_read": strawberry.field(resolver=m_mark_notification_read, name="markNotificationRead", description='Mark a single notification as read.'),
    "mark_notification_unread": strawberry.field(resolver=m_mark_notification_unread, name="markNotificationUnread", description='Mark a single notification as unread.'),
    "mark_all_notifications_read": strawberry.field(resolver=m_mark_all_notifications_read, name="markAllNotificationsRead", description="Mark all of the current user's notifications as read."),
    "delete_notification": strawberry.field(resolver=m_delete_notification, name="deleteNotification", description='Delete a notification.'),
}
