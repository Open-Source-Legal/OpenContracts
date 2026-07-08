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
from config.graphql._util import coerce_enum, coerce_str, strip_unset
from config.graphql import enums




@strawberry.type(name="LockThreadMutation", description='Lock a conversation/thread to prevent new messages.\nOnly corpus owners or moderators with lock_threads permission can lock threads.')
class LockThreadMutation:
    ok: Optional[bool] = strawberry.field(name="ok", default=None)
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))
    obj: Optional[Annotated["ConversationType", strawberry.lazy("config.graphql.conversation_types")]] = strawberry.field(name="obj", default=None)


register_type("LockThreadMutation", LockThreadMutation, model=None)


@strawberry.type(name="UnlockThreadMutation", description='Unlock a conversation/thread to allow new messages.\nOnly corpus owners or moderators with lock_threads permission can unlock threads.')
class UnlockThreadMutation:
    ok: Optional[bool] = strawberry.field(name="ok", default=None)
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))
    obj: Optional[Annotated["ConversationType", strawberry.lazy("config.graphql.conversation_types")]] = strawberry.field(name="obj", default=None)


register_type("UnlockThreadMutation", UnlockThreadMutation, model=None)


@strawberry.type(name="PinThreadMutation", description='Pin a conversation/thread to the top of the list.\nOnly corpus owners or moderators with pin_threads permission can pin threads.')
class PinThreadMutation:
    ok: Optional[bool] = strawberry.field(name="ok", default=None)
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))
    obj: Optional[Annotated["ConversationType", strawberry.lazy("config.graphql.conversation_types")]] = strawberry.field(name="obj", default=None)


register_type("PinThreadMutation", PinThreadMutation, model=None)


@strawberry.type(name="UnpinThreadMutation", description='Unpin a conversation/thread from the top of the list.\nOnly corpus owners or moderators with pin_threads permission can unpin threads.')
class UnpinThreadMutation:
    ok: Optional[bool] = strawberry.field(name="ok", default=None)
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))
    obj: Optional[Annotated["ConversationType", strawberry.lazy("config.graphql.conversation_types")]] = strawberry.field(name="obj", default=None)


register_type("UnpinThreadMutation", UnpinThreadMutation, model=None)


@strawberry.type(name="DeleteThreadMutation", description='Soft delete a thread (conversation).\nOnly moderators or thread creators can delete threads.')
class DeleteThreadMutation:
    ok: Optional[bool] = strawberry.field(name="ok", default=None)
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))
    conversation: Optional[Annotated["ConversationType", strawberry.lazy("config.graphql.conversation_types")]] = strawberry.field(name="conversation", default=None)


register_type("DeleteThreadMutation", DeleteThreadMutation, model=None)


@strawberry.type(name="RestoreThreadMutation", description='Restore a soft-deleted thread.\nOnly moderators or thread creators can restore threads.')
class RestoreThreadMutation:
    ok: Optional[bool] = strawberry.field(name="ok", default=None)
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))
    conversation: Optional[Annotated["ConversationType", strawberry.lazy("config.graphql.conversation_types")]] = strawberry.field(name="conversation", default=None)


register_type("RestoreThreadMutation", RestoreThreadMutation, model=None)


@strawberry.type(name="AddModeratorMutation", description='Add a moderator to a corpus with specific permissions.\nOnly corpus owners can add moderators.')
class AddModeratorMutation:
    ok: Optional[bool] = strawberry.field(name="ok", default=None)
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))


register_type("AddModeratorMutation", AddModeratorMutation, model=None)


@strawberry.type(name="RemoveModeratorMutation", description='Remove a moderator from a corpus.\nOnly corpus owners can remove moderators.')
class RemoveModeratorMutation:
    ok: Optional[bool] = strawberry.field(name="ok", default=None)
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))


register_type("RemoveModeratorMutation", RemoveModeratorMutation, model=None)


@strawberry.type(name="UpdateModeratorPermissionsMutation", description="Update a moderator's permissions for a corpus.\nOnly corpus owners can update moderator permissions.")
class UpdateModeratorPermissionsMutation:
    ok: Optional[bool] = strawberry.field(name="ok", default=None)
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))


register_type("UpdateModeratorPermissionsMutation", UpdateModeratorPermissionsMutation, model=None)


@strawberry.type(name="RollbackModerationActionMutation", description='Rollback a moderation action by executing its inverse.\n- delete_message -> restore_message\n- delete_thread -> restore_thread\n- lock_thread -> unlock_thread\n- pin_thread -> unpin_thread\n\nOnly moderators with appropriate permissions can rollback.\nCreates a new ModerationAction record for the rollback.')
class RollbackModerationActionMutation:
    ok: Optional[bool] = strawberry.field(name="ok", default=None)
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))
    rollback_action: Optional[Annotated["ModerationActionType", strawberry.lazy("config.graphql.conversation_types")]] = strawberry.field(name="rollbackAction", default=None)


register_type("RollbackModerationActionMutation", RollbackModerationActionMutation, model=None)


def _mutate_LockThreadMutation(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:83

    Port of LockThreadMutation.mutate
    """
    raise NotImplementedError("_mutate_LockThreadMutation not yet ported — see manifest")


def m_lock_thread(info: strawberry.Info, conversation_id: Annotated[str, strawberry.argument(name="conversationId", description='ID of the conversation to lock')] = strawberry.UNSET, reason: Annotated[Optional[str], strawberry.argument(name="reason", description='Optional reason for locking')] = strawberry.UNSET) -> Optional["LockThreadMutation"]:
    kwargs = strip_unset({"conversation_id": conversation_id, "reason": reason})
    return _mutate_LockThreadMutation(LockThreadMutation, None, info, **kwargs)


def _mutate_UnlockThreadMutation(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:135

    Port of UnlockThreadMutation.mutate
    """
    raise NotImplementedError("_mutate_UnlockThreadMutation not yet ported — see manifest")


def m_unlock_thread(info: strawberry.Info, conversation_id: Annotated[str, strawberry.argument(name="conversationId", description='ID of the conversation to unlock')] = strawberry.UNSET, reason: Annotated[Optional[str], strawberry.argument(name="reason", description='Optional reason for unlocking')] = strawberry.UNSET) -> Optional["UnlockThreadMutation"]:
    kwargs = strip_unset({"conversation_id": conversation_id, "reason": reason})
    return _mutate_UnlockThreadMutation(UnlockThreadMutation, None, info, **kwargs)


def _mutate_PinThreadMutation(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:187

    Port of PinThreadMutation.mutate
    """
    raise NotImplementedError("_mutate_PinThreadMutation not yet ported — see manifest")


def m_pin_thread(info: strawberry.Info, conversation_id: Annotated[str, strawberry.argument(name="conversationId", description='ID of the conversation to pin')] = strawberry.UNSET, reason: Annotated[Optional[str], strawberry.argument(name="reason", description='Optional reason for pinning')] = strawberry.UNSET) -> Optional["PinThreadMutation"]:
    kwargs = strip_unset({"conversation_id": conversation_id, "reason": reason})
    return _mutate_PinThreadMutation(PinThreadMutation, None, info, **kwargs)


def _mutate_UnpinThreadMutation(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:239

    Port of UnpinThreadMutation.mutate
    """
    raise NotImplementedError("_mutate_UnpinThreadMutation not yet ported — see manifest")


def m_unpin_thread(info: strawberry.Info, conversation_id: Annotated[str, strawberry.argument(name="conversationId", description='ID of the conversation to unpin')] = strawberry.UNSET, reason: Annotated[Optional[str], strawberry.argument(name="reason", description='Optional reason for unpinning')] = strawberry.UNSET) -> Optional["UnpinThreadMutation"]:
    kwargs = strip_unset({"conversation_id": conversation_id, "reason": reason})
    return _mutate_UnpinThreadMutation(UnpinThreadMutation, None, info, **kwargs)


def _mutate_DeleteThreadMutation(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:289

    Port of DeleteThreadMutation.mutate
    """
    raise NotImplementedError("_mutate_DeleteThreadMutation not yet ported — see manifest")


def m_delete_thread(info: strawberry.Info, conversation_id: Annotated[strawberry.ID, strawberry.argument(name="conversationId", description='ID of thread to delete')] = strawberry.UNSET, reason: Annotated[Optional[str], strawberry.argument(name="reason", description='Reason for deletion')] = strawberry.UNSET) -> Optional["DeleteThreadMutation"]:
    kwargs = strip_unset({"conversation_id": conversation_id, "reason": reason})
    return _mutate_DeleteThreadMutation(DeleteThreadMutation, None, info, **kwargs)


def _mutate_RestoreThreadMutation(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:342

    Port of RestoreThreadMutation.mutate
    """
    raise NotImplementedError("_mutate_RestoreThreadMutation not yet ported — see manifest")


def m_restore_thread(info: strawberry.Info, conversation_id: Annotated[strawberry.ID, strawberry.argument(name="conversationId", description='ID of thread to restore')] = strawberry.UNSET, reason: Annotated[Optional[str], strawberry.argument(name="reason", description='Reason for restoration')] = strawberry.UNSET) -> Optional["RestoreThreadMutation"]:
    kwargs = strip_unset({"conversation_id": conversation_id, "reason": reason})
    return _mutate_RestoreThreadMutation(RestoreThreadMutation, None, info, **kwargs)


def _mutate_AddModeratorMutation(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:400

    Port of AddModeratorMutation.mutate
    """
    raise NotImplementedError("_mutate_AddModeratorMutation not yet ported — see manifest")


def m_add_moderator(info: strawberry.Info, corpus_id: Annotated[str, strawberry.argument(name="corpusId", description='ID of the corpus')] = strawberry.UNSET, permissions: Annotated[list[Optional[str]], strawberry.argument(name="permissions", description='List of permissions: lock_threads, pin_threads, delete_messages, delete_threads')] = strawberry.UNSET, user_id: Annotated[str, strawberry.argument(name="userId", description='ID of the user to add as moderator')] = strawberry.UNSET) -> Optional["AddModeratorMutation"]:
    kwargs = strip_unset({"corpus_id": corpus_id, "permissions": permissions, "user_id": user_id})
    return _mutate_AddModeratorMutation(AddModeratorMutation, None, info, **kwargs)


def _mutate_RemoveModeratorMutation(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:479

    Port of RemoveModeratorMutation.mutate
    """
    raise NotImplementedError("_mutate_RemoveModeratorMutation not yet ported — see manifest")


def m_remove_moderator(info: strawberry.Info, corpus_id: Annotated[str, strawberry.argument(name="corpusId", description='ID of the corpus')] = strawberry.UNSET, user_id: Annotated[str, strawberry.argument(name="userId", description='ID of the user to remove as moderator')] = strawberry.UNSET) -> Optional["RemoveModeratorMutation"]:
    kwargs = strip_unset({"corpus_id": corpus_id, "user_id": user_id})
    return _mutate_RemoveModeratorMutation(RemoveModeratorMutation, None, info, **kwargs)


def _mutate_UpdateModeratorPermissionsMutation(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:541

    Port of UpdateModeratorPermissionsMutation.mutate
    """
    raise NotImplementedError("_mutate_UpdateModeratorPermissionsMutation not yet ported — see manifest")


def m_update_moderator_permissions(info: strawberry.Info, corpus_id: Annotated[str, strawberry.argument(name="corpusId", description='ID of the corpus')] = strawberry.UNSET, permissions: Annotated[list[Optional[str]], strawberry.argument(name="permissions", description='List of permissions: lock_threads, pin_threads, delete_messages, delete_threads')] = strawberry.UNSET, user_id: Annotated[str, strawberry.argument(name="userId", description='ID of the moderator user')] = strawberry.UNSET) -> Optional["UpdateModeratorPermissionsMutation"]:
    kwargs = strip_unset({"corpus_id": corpus_id, "permissions": permissions, "user_id": user_id})
    return _mutate_UpdateModeratorPermissionsMutation(UpdateModeratorPermissionsMutation, None, info, **kwargs)


def _mutate_RollbackModerationActionMutation(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:632

    Port of RollbackModerationActionMutation.mutate
    """
    raise NotImplementedError("_mutate_RollbackModerationActionMutation not yet ported — see manifest")


def m_rollback_moderation_action(info: strawberry.Info, action_id: Annotated[strawberry.ID, strawberry.argument(name="actionId", description='ID of action to rollback')] = strawberry.UNSET, reason: Annotated[Optional[str], strawberry.argument(name="reason", description='Reason for rollback')] = strawberry.UNSET) -> Optional["RollbackModerationActionMutation"]:
    kwargs = strip_unset({"action_id": action_id, "reason": reason})
    return _mutate_RollbackModerationActionMutation(RollbackModerationActionMutation, None, info, **kwargs)



MUTATION_FIELDS = {
    "lock_thread": strawberry.field(resolver=m_lock_thread, name="lockThread", description='Lock a conversation/thread to prevent new messages.\nOnly corpus owners or moderators with lock_threads permission can lock threads.'),
    "unlock_thread": strawberry.field(resolver=m_unlock_thread, name="unlockThread", description='Unlock a conversation/thread to allow new messages.\nOnly corpus owners or moderators with lock_threads permission can unlock threads.'),
    "pin_thread": strawberry.field(resolver=m_pin_thread, name="pinThread", description='Pin a conversation/thread to the top of the list.\nOnly corpus owners or moderators with pin_threads permission can pin threads.'),
    "unpin_thread": strawberry.field(resolver=m_unpin_thread, name="unpinThread", description='Unpin a conversation/thread from the top of the list.\nOnly corpus owners or moderators with pin_threads permission can unpin threads.'),
    "delete_thread": strawberry.field(resolver=m_delete_thread, name="deleteThread", description='Soft delete a thread (conversation).\nOnly moderators or thread creators can delete threads.'),
    "restore_thread": strawberry.field(resolver=m_restore_thread, name="restoreThread", description='Restore a soft-deleted thread.\nOnly moderators or thread creators can restore threads.'),
    "add_moderator": strawberry.field(resolver=m_add_moderator, name="addModerator", description='Add a moderator to a corpus with specific permissions.\nOnly corpus owners can add moderators.'),
    "remove_moderator": strawberry.field(resolver=m_remove_moderator, name="removeModerator", description='Remove a moderator from a corpus.\nOnly corpus owners can remove moderators.'),
    "update_moderator_permissions": strawberry.field(resolver=m_update_moderator_permissions, name="updateModeratorPermissions", description="Update a moderator's permissions for a corpus.\nOnly corpus owners can update moderator permissions."),
    "rollback_moderation_action": strawberry.field(resolver=m_rollback_moderation_action, name="rollbackModerationAction", description='Rollback a moderation action by executing its inverse.\n- delete_message -> restore_message\n- delete_thread -> restore_thread\n- lock_thread -> unlock_thread\n- pin_thread -> unpin_thread\n\nOnly moderators with appropriate permissions can rollback.\nCreates a new ModerationAction record for the rollback.'),
}
