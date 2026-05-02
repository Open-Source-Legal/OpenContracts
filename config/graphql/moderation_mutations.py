"""
GraphQL mutations for moderation actions.

This module provides mutations for moderating threads and messages:
- LockThreadMutation: Lock conversation to prevent new messages
- UnlockThreadMutation: Unlock conversation
- PinThreadMutation: Pin conversation to top
- UnpinThreadMutation: Unpin conversation
- DeleteThreadMutation: Soft delete conversation/thread
- RestoreThreadMutation: Restore soft-deleted conversation/thread
- AddModeratorMutation: Add moderator to corpus
- RemoveModeratorMutation: Remove moderator from corpus
- UpdateModeratorPermissionsMutation: Update moderator permissions
- RollbackModerationActionMutation: Rollback a moderation action
"""

from __future__ import annotations

import logging

import graphene
from graphql_jwt.decorators import login_required
from graphql_relay import from_global_id

from config.graphql.graphene_types import ConversationType
from config.graphql.ratelimits import graphql_ratelimit
from opencontractserver.conversations.models import (
    ChatMessage,
    Conversation,
    CorpusModerator,
)
from opencontractserver.corpuses.models import Corpus

logger = logging.getLogger(__name__)


def get_conversation_with_moderation_check(conversation_id, user):
    """
    Get conversation with moderation verification (IDOR-safe).

    Returns the same error message whether the conversation doesn't exist
    or the user lacks permission, preventing enumeration of valid conversation IDs.

    Args:
        conversation_id: Global relay ID of the conversation
        user: User requesting access

    Returns:
        tuple: (conversation_object, error_message)
            - On success: (Conversation, None)
            - On failure: (None, "Conversation not found")
    """
    try:
        pk = from_global_id(conversation_id)[1]
        conversation = Conversation.objects.get(pk=pk)
        if not conversation.can_moderate(user):
            # User doesn't have permission - same message as DoesNotExist
            return None, "Conversation not found"
        return conversation, None
    except Conversation.DoesNotExist:
        # Conversation doesn't exist - same message as permission denied
        return None, "Conversation not found"


class LockThreadMutation(graphene.Mutation):
    """
    Lock a conversation/thread to prevent new messages.
    Only corpus owners or moderators with lock_threads permission can lock threads.
    """

    class Arguments:
        conversation_id = graphene.String(
            required=True, description="ID of the conversation to lock"
        )
        reason = graphene.String(
            required=False, description="Optional reason for locking"
        )

    ok = graphene.Boolean()
    message = graphene.String()
    obj = graphene.Field(ConversationType)

    @login_required
    @graphql_ratelimit(rate="20/m")
    def mutate(root, info, conversation_id, reason="") -> LockThreadMutation:
        ok = False
        obj = None
        message_text = ""

        try:
            user = info.context.user

            # Get conversation with IDOR-safe permission check
            conversation, error = get_conversation_with_moderation_check(
                conversation_id, user
            )
            if error:
                # Either not found or no permission - same message
                return LockThreadMutation(ok=False, message=error, obj=None)

            # Lock the conversation
            conversation.lock(user, reason)

            ok = True
            obj = conversation
            message_text = "Conversation locked successfully"

        except PermissionError as e:
            message_text = str(e)
        except Exception as e:
            logger.error(f"Error locking conversation: {e}", exc_info=True)
            message_text = f"Failed to lock conversation: {str(e)}"

        return LockThreadMutation(ok=ok, message=message_text, obj=obj)


class UnlockThreadMutation(graphene.Mutation):
    """
    Unlock a conversation/thread to allow new messages.
    Only corpus owners or moderators with lock_threads permission can unlock threads.
    """

    class Arguments:
        conversation_id = graphene.String(
            required=True, description="ID of the conversation to unlock"
        )
        reason = graphene.String(
            required=False, description="Optional reason for unlocking"
        )

    ok = graphene.Boolean()
    message = graphene.String()
    obj = graphene.Field(ConversationType)

    @login_required
    @graphql_ratelimit(rate="20/m")
    def mutate(root, info, conversation_id, reason="") -> UnlockThreadMutation:
        ok = False
        obj = None
        message_text = ""

        try:
            user = info.context.user

            # Get conversation with IDOR-safe permission check
            conversation, error = get_conversation_with_moderation_check(
                conversation_id, user
            )
            if error:
                # Either not found or no permission - same message
                return UnlockThreadMutation(ok=False, message=error, obj=None)

            # Unlock the conversation
            conversation.unlock(user, reason)

            ok = True
            obj = conversation
            message_text = "Conversation unlocked successfully"

        except PermissionError as e:
            message_text = str(e)
        except Exception as e:
            logger.error(f"Error unlocking conversation: {e}", exc_info=True)
            message_text = f"Failed to unlock conversation: {str(e)}"

        return UnlockThreadMutation(ok=ok, message=message_text, obj=obj)


class PinThreadMutation(graphene.Mutation):
    """
    Pin a conversation/thread to the top of the list.
    Only corpus owners or moderators with pin_threads permission can pin threads.
    """

    class Arguments:
        conversation_id = graphene.String(
            required=True, description="ID of the conversation to pin"
        )
        reason = graphene.String(
            required=False, description="Optional reason for pinning"
        )

    ok = graphene.Boolean()
    message = graphene.String()
    obj = graphene.Field(ConversationType)

    @login_required
    @graphql_ratelimit(rate="20/m")
    def mutate(root, info, conversation_id, reason="") -> PinThreadMutation:
        ok = False
        obj = None
        message_text = ""

        try:
            user = info.context.user

            # Get conversation with IDOR-safe permission check
            conversation, error = get_conversation_with_moderation_check(
                conversation_id, user
            )
            if error:
                # Either not found or no permission - same message
                return PinThreadMutation(ok=False, message=error, obj=None)

            # Pin the conversation
            conversation.pin(user, reason)

            ok = True
            obj = conversation
            message_text = "Conversation pinned successfully"

        except PermissionError as e:
            message_text = str(e)
        except Exception as e:
            logger.error(f"Error pinning conversation: {e}", exc_info=True)
            message_text = f"Failed to pin conversation: {str(e)}"

        return PinThreadMutation(ok=ok, message=message_text, obj=obj)


class UnpinThreadMutation(graphene.Mutation):
    """
    Unpin a conversation/thread from the top of the list.
    Only corpus owners or moderators with pin_threads permission can unpin threads.
    """

    class Arguments:
        conversation_id = graphene.String(
            required=True, description="ID of the conversation to unpin"
        )
        reason = graphene.String(
            required=False, description="Optional reason for unpinning"
        )

    ok = graphene.Boolean()
    message = graphene.String()
    obj = graphene.Field(ConversationType)

    @login_required
    @graphql_ratelimit(rate="20/m")
    def mutate(root, info, conversation_id, reason="") -> UnpinThreadMutation:
        ok = False
        obj = None
        message_text = ""

        try:
            user = info.context.user

            # Get conversation with IDOR-safe permission check
            conversation, error = get_conversation_with_moderation_check(
                conversation_id, user
            )
            if error:
                # Either not found or no permission - same message
                return UnpinThreadMutation(ok=False, message=error, obj=None)

            # Unpin the conversation
            conversation.unpin(user, reason)

            ok = True
            obj = conversation
            message_text = "Conversation unpinned successfully"

        except PermissionError as e:
            message_text = str(e)
        except Exception as e:
            logger.error(f"Error unpinning conversation: {e}", exc_info=True)
            message_text = f"Failed to unpin conversation: {str(e)}"

        return UnpinThreadMutation(ok=ok, message=message_text, obj=obj)


class DeleteThreadMutation(graphene.Mutation):
    """
    Soft delete a thread (conversation).
    Only moderators or thread creators can delete threads.
    """

    class Arguments:
        conversation_id = graphene.ID(
            required=True, description="ID of thread to delete"
        )
        reason = graphene.String(description="Reason for deletion")

    ok = graphene.Boolean()
    message = graphene.String()
    conversation = graphene.Field(ConversationType)

    @login_required
    @graphql_ratelimit(rate="10/m")
    def mutate(root, info, conversation_id, reason=None) -> DeleteThreadMutation:
        user = info.context.user
        ok = False
        message_text = ""
        conversation_obj = None

        try:
            thread_pk = from_global_id(conversation_id)[1]
            conversation = Conversation.objects.get(pk=thread_pk)

            # IDOR-safe: same error for not found and no permission
            if not conversation.can_moderate(user):
                return DeleteThreadMutation(
                    ok=False,
                    message="Thread not found or access denied",
                    conversation=None,
                )

            conversation.soft_delete_thread(moderator=user, reason=reason)
            ok = True
            message_text = "Thread deleted successfully"
            conversation_obj = conversation

        except Conversation.DoesNotExist:
            message_text = "Thread not found or access denied"

        except Exception as e:
            logger.error(f"Error deleting thread: {e}", exc_info=True)
            message_text = f"Failed to delete thread: {str(e)}"

        return DeleteThreadMutation(
            ok=ok, message=message_text, conversation=conversation_obj
        )


class RestoreThreadMutation(graphene.Mutation):
    """
    Restore a soft-deleted thread.
    Only moderators or thread creators can restore threads.
    """

    class Arguments:
        conversation_id = graphene.ID(
            required=True, description="ID of thread to restore"
        )
        reason = graphene.String(description="Reason for restoration")

    ok = graphene.Boolean()
    message = graphene.String()
    conversation = graphene.Field(ConversationType)

    @login_required
    @graphql_ratelimit(rate="10/m")
    def mutate(root, info, conversation_id, reason=None) -> RestoreThreadMutation:
        user = info.context.user
        ok = False
        message_text = ""
        conversation_obj = None

        try:
            thread_pk = from_global_id(conversation_id)[1]
            # Use all_objects to include deleted threads
            conversation = Conversation.all_objects.get(pk=thread_pk)

            # IDOR-safe: same error for not found and no permission
            if not conversation.can_moderate(user):
                return RestoreThreadMutation(
                    ok=False,
                    message="Thread not found or access denied",
                    conversation=None,
                )

            conversation.restore_thread(moderator=user, reason=reason)
            ok = True
            message_text = "Thread restored successfully"
            conversation_obj = conversation

        except Conversation.DoesNotExist:
            message_text = "Thread not found or access denied"

        except Exception as e:
            logger.error(f"Error restoring thread: {e}", exc_info=True)
            message_text = f"Failed to restore thread: {str(e)}"

        return RestoreThreadMutation(
            ok=ok, message=message_text, conversation=conversation_obj
        )


class AddModeratorMutation(graphene.Mutation):
    """
    Add a moderator to a corpus with specific permissions.
    Only corpus owners can add moderators.
    """

    class Arguments:
        corpus_id = graphene.String(required=True, description="ID of the corpus")
        user_id = graphene.String(
            required=True, description="ID of the user to add as moderator"
        )
        permissions = graphene.List(
            graphene.String,
            required=True,
            description="List of permissions: lock_threads, pin_threads, delete_messages, delete_threads",
        )

    ok = graphene.Boolean()
    message = graphene.String()

    @login_required
    @graphql_ratelimit(rate="20/m")
    def mutate(root, info, corpus_id, user_id, permissions) -> AddModeratorMutation:
        ok = False
        message_text = ""

        try:
            user = info.context.user

            # Get corpus - use creator check to prevent IDOR
            # This returns same error whether corpus doesn't exist or user isn't owner
            corpus_pk = from_global_id(corpus_id)[1]
            try:
                corpus = Corpus.objects.get(pk=corpus_pk, creator=user)
            except Corpus.DoesNotExist:
                return AddModeratorMutation(ok=False, message="Corpus not found")

            # Get target user
            try:
                from django.contrib.auth import get_user_model

                User = get_user_model()
                target_user_pk = from_global_id(user_id)[1]
                target_user = User.objects.get(pk=target_user_pk)
            except User.DoesNotExist:
                return AddModeratorMutation(ok=False, message="User not found")

            # Validate permissions
            valid_permissions = [
                "lock_threads",
                "pin_threads",
                "delete_messages",
                "delete_threads",
            ]
            for perm in permissions:
                if perm not in valid_permissions:
                    return AddModeratorMutation(
                        ok=False,
                        message=f"Invalid permission: {perm}. Valid options: {', '.join(valid_permissions)}",
                    )

            # Create or update moderator
            moderator, created = CorpusModerator.objects.update_or_create(
                corpus=corpus,
                user=target_user,
                defaults={
                    "permissions": list(
                        permissions
                    ),  # Store as list for has_permission() checks
                    "assigned_by": user,  # Correct field name per CorpusModerator model
                    "creator": user,
                },
            )

            ok = True
            message_text = f"Moderator {'added' if created else 'updated'} successfully"

        except Exception as e:
            logger.error(f"Error adding moderator: {e}", exc_info=True)
            message_text = f"Failed to add moderator: {str(e)}"

        return AddModeratorMutation(ok=ok, message=message_text)


class RemoveModeratorMutation(graphene.Mutation):
    """
    Remove a moderator from a corpus.
    Only corpus owners can remove moderators.
    """

    class Arguments:
        corpus_id = graphene.String(required=True, description="ID of the corpus")
        user_id = graphene.String(
            required=True, description="ID of the user to remove as moderator"
        )

    ok = graphene.Boolean()
    message = graphene.String()

    @login_required
    @graphql_ratelimit(rate="20/m")
    def mutate(root, info, corpus_id, user_id) -> RemoveModeratorMutation:
        ok = False
        message_text = ""

        try:
            user = info.context.user

            # Get corpus - use creator check to prevent IDOR
            # This returns same error whether corpus doesn't exist or user isn't owner
            corpus_pk = from_global_id(corpus_id)[1]
            try:
                corpus = Corpus.objects.get(pk=corpus_pk, creator=user)
            except Corpus.DoesNotExist:
                return RemoveModeratorMutation(ok=False, message="Corpus not found")

            # Get target user
            try:
                from django.contrib.auth import get_user_model

                User = get_user_model()
                target_user_pk = from_global_id(user_id)[1]
                target_user = User.objects.get(pk=target_user_pk)
            except User.DoesNotExist:
                return RemoveModeratorMutation(ok=False, message="User not found")

            # Remove moderator
            try:
                moderator = CorpusModerator.objects.get(corpus=corpus, user=target_user)
                moderator.delete()
                ok = True
                message_text = "Moderator removed successfully"
            except CorpusModerator.DoesNotExist:
                message_text = "User is not a moderator of this corpus"
                ok = True  # Not an error, just already not a moderator

        except Exception as e:
            logger.error(f"Error removing moderator: {e}", exc_info=True)
            message_text = f"Failed to remove moderator: {str(e)}"

        return RemoveModeratorMutation(ok=ok, message=message_text)


class UpdateModeratorPermissionsMutation(graphene.Mutation):
    """
    Update a moderator's permissions for a corpus.
    Only corpus owners can update moderator permissions.
    """

    class Arguments:
        corpus_id = graphene.String(required=True, description="ID of the corpus")
        user_id = graphene.String(required=True, description="ID of the moderator user")
        permissions = graphene.List(
            graphene.String,
            required=True,
            description="List of permissions: lock_threads, pin_threads, delete_messages, delete_threads",
        )

    ok = graphene.Boolean()
    message = graphene.String()

    @login_required
    @graphql_ratelimit(rate="20/m")
    def mutate(
        root, info, corpus_id, user_id, permissions
    ) -> UpdateModeratorPermissionsMutation:
        ok = False
        message_text = ""

        try:
            user = info.context.user

            # Get corpus - use creator check to prevent IDOR
            # This returns same error whether corpus doesn't exist or user isn't owner
            corpus_pk = from_global_id(corpus_id)[1]
            try:
                corpus = Corpus.objects.get(pk=corpus_pk, creator=user)
            except Corpus.DoesNotExist:
                return UpdateModeratorPermissionsMutation(
                    ok=False, message="Corpus not found"
                )

            # Get target user
            try:
                from django.contrib.auth import get_user_model

                User = get_user_model()
                target_user_pk = from_global_id(user_id)[1]
                target_user = User.objects.get(pk=target_user_pk)
            except User.DoesNotExist:
                return UpdateModeratorPermissionsMutation(
                    ok=False, message="User not found"
                )

            # Validate permissions
            valid_permissions = [
                "lock_threads",
                "pin_threads",
                "delete_messages",
                "delete_threads",
            ]
            for perm in permissions:
                if perm not in valid_permissions:
                    return UpdateModeratorPermissionsMutation(
                        ok=False,
                        message=f"Invalid permission: {perm}. Valid options: {', '.join(valid_permissions)}",
                    )

            # Update moderator permissions
            try:
                moderator = CorpusModerator.objects.get(corpus=corpus, user=target_user)
                moderator.permissions = list(
                    permissions
                )  # Store as list for has_permission() checks
                moderator.save(update_fields=["permissions"])
                ok = True
                message_text = "Moderator permissions updated successfully"
            except CorpusModerator.DoesNotExist:
                return UpdateModeratorPermissionsMutation(
                    ok=False,
                    message="User is not a moderator of this corpus",
                )

        except Exception as e:
            logger.error(f"Error updating moderator permissions: {e}", exc_info=True)
            message_text = f"Failed to update moderator permissions: {str(e)}"

        return UpdateModeratorPermissionsMutation(ok=ok, message=message_text)


class RollbackModerationActionMutation(graphene.Mutation):
    """
    Rollback a moderation action by executing its inverse.
    - delete_message -> restore_message
    - delete_thread -> restore_thread
    - lock_thread -> unlock_thread
    - pin_thread -> unpin_thread

    Only moderators with appropriate permissions can rollback.
    Creates a new ModerationAction record for the rollback.
    """

    class Arguments:
        action_id = graphene.ID(required=True, description="ID of action to rollback")
        reason = graphene.String(description="Reason for rollback")

    ok = graphene.Boolean()
    message = graphene.String()
    rollback_action = graphene.Field(
        "config.graphql.graphene_types.ModerationActionType"
    )

    @login_required
    @graphql_ratelimit(rate="10/m")
    def mutate(root, info, action_id, reason=None) -> RollbackModerationActionMutation:
        from opencontractserver.conversations.models import (
            ModerationAction,
        )
        from opencontractserver.conversations.models import (
            ModerationActionType as ModerationActionTypeEnum,
        )

        user = info.context.user

        try:
            action_pk = from_global_id(action_id)[1]
            original_action = ModerationAction.objects.select_related(
                "conversation", "conversation__chat_with_corpus", "message"
            ).get(pk=action_pk)
        except ModerationAction.DoesNotExist:
            return RollbackModerationActionMutation(
                ok=False,
                message="Moderation action not found",
                rollback_action=None,
            )

        # Define rollback mappings: action_type -> (rollback_action_type, method_name, target_attr)
        # - rollback_action_type: The action type for the new audit log entry
        # - method_name: The model method to call for the rollback operation
        # - target_attr: Which object the action operates on ('message' or 'conversation'),
        #   used for permission checking (message actions need message's conversation)
        #   and for invoking the correct method on the target object
        # Use string values for comparison since DB stores strings
        rollback_map = {
            ModerationActionTypeEnum.DELETE_MESSAGE.value: (
                ModerationActionTypeEnum.RESTORE_MESSAGE.value,
                "restore_message",
                "message",
            ),
            ModerationActionTypeEnum.DELETE_THREAD.value: (
                ModerationActionTypeEnum.RESTORE_THREAD.value,
                "restore_thread",
                "conversation",
            ),
            ModerationActionTypeEnum.LOCK_THREAD.value: (
                ModerationActionTypeEnum.UNLOCK_THREAD.value,
                "unlock",
                "conversation",
            ),
            ModerationActionTypeEnum.PIN_THREAD.value: (
                ModerationActionTypeEnum.UNPIN_THREAD.value,
                "unpin",
                "conversation",
            ),
        }

        if original_action.action_type not in rollback_map:
            return RollbackModerationActionMutation(
                ok=False,
                message=f"Action type '{original_action.action_type}' cannot be rolled back",
                rollback_action=None,
            )

        _rollback_action_type, method_name, target_attr = rollback_map[
            original_action.action_type
        ]

        # Determine the target for rollback and the conversation for permission check
        target: ChatMessage | Conversation | None
        if target_attr == "message":
            target = original_action.message
            # For message actions, use message's conversation for permission check
            permission_conversation = target.conversation if target else None
        else:
            target = original_action.conversation
            permission_conversation = target

        # Check if target exists
        if target is None:
            return RollbackModerationActionMutation(
                ok=False,
                message=f"Cannot rollback: target {target_attr} no longer exists",
                rollback_action=None,
            )

        # Check permissions - user must be able to moderate
        if permission_conversation is None:
            return RollbackModerationActionMutation(
                ok=False,
                message="Cannot rollback: conversation not found",
                rollback_action=None,
            )

        if not permission_conversation.can_moderate(user):
            return RollbackModerationActionMutation(
                ok=False,
                message="You don't have permission to rollback this action",
                rollback_action=None,
            )

        # Execute the rollback - methods now return the created ModerationAction
        try:
            rollback_action = getattr(target, method_name)(
                moderator=user, reason=reason or "Rollback"
            )

            return RollbackModerationActionMutation(
                ok=True,
                message=f"Successfully rolled back {original_action.action_type}",
                rollback_action=rollback_action,
            )

        except Exception as e:
            logger.error(f"Error rolling back moderation action: {e}", exc_info=True)
            return RollbackModerationActionMutation(
                ok=False,
                message=f"Failed to rollback: {str(e)}",
                rollback_action=None,
            )
