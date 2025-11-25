"""
GraphQL mutations for moderation actions.

This module provides mutations for moderating threads and messages:
- LockThreadMutation: Lock conversation to prevent new messages
- UnlockThreadMutation: Unlock conversation
- PinThreadMutation: Pin conversation to top
- UnpinThreadMutation: Unpin conversation
- AddModeratorMutation: Add moderator to corpus
- RemoveModeratorMutation: Remove moderator from corpus
- UpdateModeratorPermissionsMutation: Update moderator permissions
"""

import logging

import graphene
from graphql_jwt.decorators import login_required
from graphql_relay import from_global_id

from config.graphql.graphene_types import ConversationType
from config.graphql.ratelimits import graphql_ratelimit
from opencontractserver.conversations.models import Conversation, CorpusModerator
from opencontractserver.corpuses.models import Corpus

logger = logging.getLogger(__name__)


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
    def mutate(root, info, conversation_id, reason=""):
        ok = False
        obj = None
        message_text = ""

        try:
            user = info.context.user

            # Get conversation
            try:
                conversation_pk = from_global_id(conversation_id)[1]
                conversation = Conversation.objects.get(pk=conversation_pk)
            except Conversation.DoesNotExist:
                return LockThreadMutation(
                    ok=False, message="Conversation not found", obj=None
                )

            # Check if user can moderate
            if not conversation.can_moderate(user):
                return LockThreadMutation(
                    ok=False,
                    message="You do not have permission to lock this conversation",
                    obj=None,
                )

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
    def mutate(root, info, conversation_id, reason=""):
        ok = False
        obj = None
        message_text = ""

        try:
            user = info.context.user

            # Get conversation
            try:
                conversation_pk = from_global_id(conversation_id)[1]
                conversation = Conversation.objects.get(pk=conversation_pk)
            except Conversation.DoesNotExist:
                return UnlockThreadMutation(
                    ok=False, message="Conversation not found", obj=None
                )

            # Check if user can moderate
            if not conversation.can_moderate(user):
                return UnlockThreadMutation(
                    ok=False,
                    message="You do not have permission to unlock this conversation",
                    obj=None,
                )

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
    def mutate(root, info, conversation_id, reason=""):
        ok = False
        obj = None
        message_text = ""

        try:
            user = info.context.user

            # Get conversation
            try:
                conversation_pk = from_global_id(conversation_id)[1]
                conversation = Conversation.objects.get(pk=conversation_pk)
            except Conversation.DoesNotExist:
                return PinThreadMutation(
                    ok=False, message="Conversation not found", obj=None
                )

            # Check if user can moderate
            if not conversation.can_moderate(user):
                return PinThreadMutation(
                    ok=False,
                    message="You do not have permission to pin this conversation",
                    obj=None,
                )

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
    def mutate(root, info, conversation_id, reason=""):
        ok = False
        obj = None
        message_text = ""

        try:
            user = info.context.user

            # Get conversation
            try:
                conversation_pk = from_global_id(conversation_id)[1]
                conversation = Conversation.objects.get(pk=conversation_pk)
            except Conversation.DoesNotExist:
                return UnpinThreadMutation(
                    ok=False, message="Conversation not found", obj=None
                )

            # Check if user can moderate
            if not conversation.can_moderate(user):
                return UnpinThreadMutation(
                    ok=False,
                    message="You do not have permission to unpin this conversation",
                    obj=None,
                )

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
    def mutate(root, info, corpus_id, user_id, permissions):
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
    def mutate(root, info, corpus_id, user_id):
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
    def mutate(root, info, corpus_id, user_id, permissions):
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
