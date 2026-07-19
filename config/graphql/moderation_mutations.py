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
from config.graphql.ratelimits import graphql_ratelimit
from opencontractserver.conversations.models import (
    ChatMessage,
    Conversation,
    CorpusModerator,
)
from opencontractserver.corpuses.models import Corpus

logger = logging.getLogger(__name__)

# NOTE on decorators: the graphene mutations were decorated with
# ``@login_required`` + ``@graphql_ratelimit(...)`` on ``mutate(root, info, …)``.
# Mutate stubs here take ``payload_cls`` as their first positional argument,
# which does not match those decorators' ``(root, info, ...)`` calling
# convention — so ``login_required`` is inlined (see user_mutations.py) and
# ``graphql_ratelimit`` is applied to an inner function named ``mutate`` so
# the rate-limit cache group (defaults to the decorated function's
# ``__name__``) stays "mutate", exactly as in the graphene layer.


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


@strawberry.type(
    name="LockThreadMutation",
    description="Lock a conversation/thread to prevent new messages.\nOnly corpus owners or moderators with lock_threads permission can lock threads.",
)
class LockThreadMutation:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    obj: None | (
        Annotated[
            ConversationType, strawberry.lazy("config.graphql.conversation_types")
        ]
    ) = strawberry.field(name="obj", default=None)


register_type("LockThreadMutation", LockThreadMutation, model=None)


@strawberry.type(
    name="UnlockThreadMutation",
    description="Unlock a conversation/thread to allow new messages.\nOnly corpus owners or moderators with lock_threads permission can unlock threads.",
)
class UnlockThreadMutation:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    obj: None | (
        Annotated[
            ConversationType, strawberry.lazy("config.graphql.conversation_types")
        ]
    ) = strawberry.field(name="obj", default=None)


register_type("UnlockThreadMutation", UnlockThreadMutation, model=None)


@strawberry.type(
    name="PinThreadMutation",
    description="Pin a conversation/thread to the top of the list.\nOnly corpus owners or moderators with pin_threads permission can pin threads.",
)
class PinThreadMutation:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    obj: None | (
        Annotated[
            ConversationType, strawberry.lazy("config.graphql.conversation_types")
        ]
    ) = strawberry.field(name="obj", default=None)


register_type("PinThreadMutation", PinThreadMutation, model=None)


@strawberry.type(
    name="UnpinThreadMutation",
    description="Unpin a conversation/thread from the top of the list.\nOnly corpus owners or moderators with pin_threads permission can unpin threads.",
)
class UnpinThreadMutation:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    obj: None | (
        Annotated[
            ConversationType, strawberry.lazy("config.graphql.conversation_types")
        ]
    ) = strawberry.field(name="obj", default=None)


register_type("UnpinThreadMutation", UnpinThreadMutation, model=None)


@strawberry.type(
    name="DeleteThreadMutation",
    description="Soft delete a thread (conversation).\nOnly moderators or thread creators can delete threads.",
)
class DeleteThreadMutation:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    conversation: None | (
        Annotated[
            ConversationType, strawberry.lazy("config.graphql.conversation_types")
        ]
    ) = strawberry.field(name="conversation", default=None)


register_type("DeleteThreadMutation", DeleteThreadMutation, model=None)


@strawberry.type(
    name="RestoreThreadMutation",
    description="Restore a soft-deleted thread.\nOnly moderators or thread creators can restore threads.",
)
class RestoreThreadMutation:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    conversation: None | (
        Annotated[
            ConversationType, strawberry.lazy("config.graphql.conversation_types")
        ]
    ) = strawberry.field(name="conversation", default=None)


register_type("RestoreThreadMutation", RestoreThreadMutation, model=None)


@strawberry.type(
    name="AddModeratorMutation",
    description="Add a moderator to a corpus with specific permissions.\nOnly corpus owners can add moderators.",
)
class AddModeratorMutation:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)


register_type("AddModeratorMutation", AddModeratorMutation, model=None)


@strawberry.type(
    name="RemoveModeratorMutation",
    description="Remove a moderator from a corpus.\nOnly corpus owners can remove moderators.",
)
class RemoveModeratorMutation:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)


register_type("RemoveModeratorMutation", RemoveModeratorMutation, model=None)


@strawberry.type(
    name="UpdateModeratorPermissionsMutation",
    description="Update a moderator's permissions for a corpus.\nOnly corpus owners can update moderator permissions.",
)
class UpdateModeratorPermissionsMutation:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)


register_type(
    "UpdateModeratorPermissionsMutation", UpdateModeratorPermissionsMutation, model=None
)


@strawberry.type(
    name="RollbackModerationActionMutation",
    description="Rollback a moderation action by executing its inverse.\n- delete_message -> restore_message\n- delete_thread -> restore_thread\n- lock_thread -> unlock_thread\n- pin_thread -> unpin_thread\n\nOnly moderators with appropriate permissions can rollback.\nCreates a new ModerationAction record for the rollback.",
)
class RollbackModerationActionMutation:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    rollback_action: None | (
        Annotated[
            ModerationActionType, strawberry.lazy("config.graphql.conversation_types")
        ]
    ) = strawberry.field(name="rollbackAction", default=None)


register_type(
    "RollbackModerationActionMutation", RollbackModerationActionMutation, model=None
)


def _mutate_LockThreadMutation(payload_cls, root, info, conversation_id, reason=""):
    """PORT: /home/user/oc-graphene-ref/config/graphql/moderation_mutations.py:83

    Port of LockThreadMutation.mutate
    """
    # @login_required — inlined (see module NOTE above).
    if not info.context.user.is_authenticated:
        raise PermissionDenied()

    @graphql_ratelimit(rate="20/m")
    def mutate(root, info, conversation_id, reason=""):
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

    return mutate(root, info, conversation_id, reason=reason)


def m_lock_thread(
    info: strawberry.Info,
    conversation_id: Annotated[
        str,
        strawberry.argument(
            name="conversationId", description="ID of the conversation to lock"
        ),
    ] = strawberry.UNSET,
    reason: Annotated[
        str | None,
        strawberry.argument(name="reason", description="Optional reason for locking"),
    ] = strawberry.UNSET,
) -> LockThreadMutation | None:
    kwargs = strip_unset({"conversation_id": conversation_id, "reason": reason})
    return _mutate_LockThreadMutation(LockThreadMutation, None, info, **kwargs)


def _mutate_UnlockThreadMutation(payload_cls, root, info, conversation_id, reason=""):
    """PORT: /home/user/oc-graphene-ref/config/graphql/moderation_mutations.py:135

    Port of UnlockThreadMutation.mutate
    """
    # @login_required — inlined (see module NOTE above).
    if not info.context.user.is_authenticated:
        raise PermissionDenied()

    @graphql_ratelimit(rate="20/m")
    def mutate(root, info, conversation_id, reason=""):
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

    return mutate(root, info, conversation_id, reason=reason)


def m_unlock_thread(
    info: strawberry.Info,
    conversation_id: Annotated[
        str,
        strawberry.argument(
            name="conversationId", description="ID of the conversation to unlock"
        ),
    ] = strawberry.UNSET,
    reason: Annotated[
        str | None,
        strawberry.argument(name="reason", description="Optional reason for unlocking"),
    ] = strawberry.UNSET,
) -> UnlockThreadMutation | None:
    kwargs = strip_unset({"conversation_id": conversation_id, "reason": reason})
    return _mutate_UnlockThreadMutation(UnlockThreadMutation, None, info, **kwargs)


def _mutate_PinThreadMutation(payload_cls, root, info, conversation_id, reason=""):
    """PORT: /home/user/oc-graphene-ref/config/graphql/moderation_mutations.py:187

    Port of PinThreadMutation.mutate
    """
    # @login_required — inlined (see module NOTE above).
    if not info.context.user.is_authenticated:
        raise PermissionDenied()

    @graphql_ratelimit(rate="20/m")
    def mutate(root, info, conversation_id, reason=""):
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

    return mutate(root, info, conversation_id, reason=reason)


def m_pin_thread(
    info: strawberry.Info,
    conversation_id: Annotated[
        str,
        strawberry.argument(
            name="conversationId", description="ID of the conversation to pin"
        ),
    ] = strawberry.UNSET,
    reason: Annotated[
        str | None,
        strawberry.argument(name="reason", description="Optional reason for pinning"),
    ] = strawberry.UNSET,
) -> PinThreadMutation | None:
    kwargs = strip_unset({"conversation_id": conversation_id, "reason": reason})
    return _mutate_PinThreadMutation(PinThreadMutation, None, info, **kwargs)


def _mutate_UnpinThreadMutation(payload_cls, root, info, conversation_id, reason=""):
    """PORT: /home/user/oc-graphene-ref/config/graphql/moderation_mutations.py:239

    Port of UnpinThreadMutation.mutate
    """
    # @login_required — inlined (see module NOTE above).
    if not info.context.user.is_authenticated:
        raise PermissionDenied()

    @graphql_ratelimit(rate="20/m")
    def mutate(root, info, conversation_id, reason=""):
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

    return mutate(root, info, conversation_id, reason=reason)


def m_unpin_thread(
    info: strawberry.Info,
    conversation_id: Annotated[
        str,
        strawberry.argument(
            name="conversationId", description="ID of the conversation to unpin"
        ),
    ] = strawberry.UNSET,
    reason: Annotated[
        str | None,
        strawberry.argument(name="reason", description="Optional reason for unpinning"),
    ] = strawberry.UNSET,
) -> UnpinThreadMutation | None:
    kwargs = strip_unset({"conversation_id": conversation_id, "reason": reason})
    return _mutate_UnpinThreadMutation(UnpinThreadMutation, None, info, **kwargs)


def _mutate_DeleteThreadMutation(payload_cls, root, info, conversation_id, reason=None):
    """PORT: /home/user/oc-graphene-ref/config/graphql/moderation_mutations.py:289

    Port of DeleteThreadMutation.mutate
    """
    # @login_required — inlined (see module NOTE above).
    if not info.context.user.is_authenticated:
        raise PermissionDenied()

    @graphql_ratelimit(rate="10/m")
    def mutate(root, info, conversation_id, reason=None):
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

    return mutate(root, info, conversation_id, reason=reason)


def m_delete_thread(
    info: strawberry.Info,
    conversation_id: Annotated[
        strawberry.ID,
        strawberry.argument(
            name="conversationId", description="ID of thread to delete"
        ),
    ] = strawberry.UNSET,
    reason: Annotated[
        str | None,
        strawberry.argument(name="reason", description="Reason for deletion"),
    ] = strawberry.UNSET,
) -> DeleteThreadMutation | None:
    kwargs = strip_unset({"conversation_id": conversation_id, "reason": reason})
    return _mutate_DeleteThreadMutation(DeleteThreadMutation, None, info, **kwargs)


def _mutate_RestoreThreadMutation(
    payload_cls, root, info, conversation_id, reason=None
):
    """PORT: /home/user/oc-graphene-ref/config/graphql/moderation_mutations.py:342

    Port of RestoreThreadMutation.mutate
    """
    # @login_required — inlined (see module NOTE above).
    if not info.context.user.is_authenticated:
        raise PermissionDenied()

    @graphql_ratelimit(rate="10/m")
    def mutate(root, info, conversation_id, reason=None):
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

    return mutate(root, info, conversation_id, reason=reason)


def m_restore_thread(
    info: strawberry.Info,
    conversation_id: Annotated[
        strawberry.ID,
        strawberry.argument(
            name="conversationId", description="ID of thread to restore"
        ),
    ] = strawberry.UNSET,
    reason: Annotated[
        str | None,
        strawberry.argument(name="reason", description="Reason for restoration"),
    ] = strawberry.UNSET,
) -> RestoreThreadMutation | None:
    kwargs = strip_unset({"conversation_id": conversation_id, "reason": reason})
    return _mutate_RestoreThreadMutation(RestoreThreadMutation, None, info, **kwargs)


def _mutate_AddModeratorMutation(
    payload_cls, root, info, corpus_id, user_id, permissions
):
    """PORT: /home/user/oc-graphene-ref/config/graphql/moderation_mutations.py:400

    Port of AddModeratorMutation.mutate
    """
    # @login_required — inlined (see module NOTE above).
    if not info.context.user.is_authenticated:
        raise PermissionDenied()

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

    return mutate(root, info, corpus_id, user_id, permissions)


def m_add_moderator(
    info: strawberry.Info,
    corpus_id: Annotated[
        str, strawberry.argument(name="corpusId", description="ID of the corpus")
    ] = strawberry.UNSET,
    permissions: Annotated[
        list[str | None],
        strawberry.argument(
            name="permissions",
            description="List of permissions: lock_threads, pin_threads, delete_messages, delete_threads",
        ),
    ] = strawberry.UNSET,
    user_id: Annotated[
        str,
        strawberry.argument(
            name="userId", description="ID of the user to add as moderator"
        ),
    ] = strawberry.UNSET,
) -> AddModeratorMutation | None:
    kwargs = strip_unset(
        {"corpus_id": corpus_id, "permissions": permissions, "user_id": user_id}
    )
    return _mutate_AddModeratorMutation(AddModeratorMutation, None, info, **kwargs)


def _mutate_RemoveModeratorMutation(payload_cls, root, info, corpus_id, user_id):
    """PORT: /home/user/oc-graphene-ref/config/graphql/moderation_mutations.py:479

    Port of RemoveModeratorMutation.mutate
    """
    # @login_required — inlined (see module NOTE above).
    if not info.context.user.is_authenticated:
        raise PermissionDenied()

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

    return mutate(root, info, corpus_id, user_id)


def m_remove_moderator(
    info: strawberry.Info,
    corpus_id: Annotated[
        str, strawberry.argument(name="corpusId", description="ID of the corpus")
    ] = strawberry.UNSET,
    user_id: Annotated[
        str,
        strawberry.argument(
            name="userId", description="ID of the user to remove as moderator"
        ),
    ] = strawberry.UNSET,
) -> RemoveModeratorMutation | None:
    kwargs = strip_unset({"corpus_id": corpus_id, "user_id": user_id})
    return _mutate_RemoveModeratorMutation(
        RemoveModeratorMutation, None, info, **kwargs
    )


def _mutate_UpdateModeratorPermissionsMutation(
    payload_cls, root, info, corpus_id, user_id, permissions
):
    """PORT: /home/user/oc-graphene-ref/config/graphql/moderation_mutations.py:541

    Port of UpdateModeratorPermissionsMutation.mutate
    """
    # @login_required — inlined (see module NOTE above).
    if not info.context.user.is_authenticated:
        raise PermissionDenied()

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

    return mutate(root, info, corpus_id, user_id, permissions)


def m_update_moderator_permissions(
    info: strawberry.Info,
    corpus_id: Annotated[
        str, strawberry.argument(name="corpusId", description="ID of the corpus")
    ] = strawberry.UNSET,
    permissions: Annotated[
        list[str | None],
        strawberry.argument(
            name="permissions",
            description="List of permissions: lock_threads, pin_threads, delete_messages, delete_threads",
        ),
    ] = strawberry.UNSET,
    user_id: Annotated[
        str, strawberry.argument(name="userId", description="ID of the moderator user")
    ] = strawberry.UNSET,
) -> UpdateModeratorPermissionsMutation | None:
    kwargs = strip_unset(
        {"corpus_id": corpus_id, "permissions": permissions, "user_id": user_id}
    )
    return _mutate_UpdateModeratorPermissionsMutation(
        UpdateModeratorPermissionsMutation, None, info, **kwargs
    )


def _mutate_RollbackModerationActionMutation(
    payload_cls, root, info, action_id, reason=None
):
    """PORT: /home/user/oc-graphene-ref/config/graphql/moderation_mutations.py:632

    Port of RollbackModerationActionMutation.mutate
    """
    # @login_required — inlined (see module NOTE above).
    if not info.context.user.is_authenticated:
        raise PermissionDenied()

    @graphql_ratelimit(rate="10/m")
    def mutate(root, info, action_id, reason=None):
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

    return mutate(root, info, action_id, reason=reason)


def m_rollback_moderation_action(
    info: strawberry.Info,
    action_id: Annotated[
        strawberry.ID,
        strawberry.argument(name="actionId", description="ID of action to rollback"),
    ] = strawberry.UNSET,
    reason: Annotated[
        str | None,
        strawberry.argument(name="reason", description="Reason for rollback"),
    ] = strawberry.UNSET,
) -> RollbackModerationActionMutation | None:
    kwargs = strip_unset({"action_id": action_id, "reason": reason})
    return _mutate_RollbackModerationActionMutation(
        RollbackModerationActionMutation, None, info, **kwargs
    )


MUTATION_FIELDS = {
    "lock_thread": strawberry.field(
        resolver=m_lock_thread,
        name="lockThread",
        description="Lock a conversation/thread to prevent new messages.\nOnly corpus owners or moderators with lock_threads permission can lock threads.",
    ),
    "unlock_thread": strawberry.field(
        resolver=m_unlock_thread,
        name="unlockThread",
        description="Unlock a conversation/thread to allow new messages.\nOnly corpus owners or moderators with lock_threads permission can unlock threads.",
    ),
    "pin_thread": strawberry.field(
        resolver=m_pin_thread,
        name="pinThread",
        description="Pin a conversation/thread to the top of the list.\nOnly corpus owners or moderators with pin_threads permission can pin threads.",
    ),
    "unpin_thread": strawberry.field(
        resolver=m_unpin_thread,
        name="unpinThread",
        description="Unpin a conversation/thread from the top of the list.\nOnly corpus owners or moderators with pin_threads permission can unpin threads.",
    ),
    "delete_thread": strawberry.field(
        resolver=m_delete_thread,
        name="deleteThread",
        description="Soft delete a thread (conversation).\nOnly moderators or thread creators can delete threads.",
    ),
    "restore_thread": strawberry.field(
        resolver=m_restore_thread,
        name="restoreThread",
        description="Restore a soft-deleted thread.\nOnly moderators or thread creators can restore threads.",
    ),
    "add_moderator": strawberry.field(
        resolver=m_add_moderator,
        name="addModerator",
        description="Add a moderator to a corpus with specific permissions.\nOnly corpus owners can add moderators.",
    ),
    "remove_moderator": strawberry.field(
        resolver=m_remove_moderator,
        name="removeModerator",
        description="Remove a moderator from a corpus.\nOnly corpus owners can remove moderators.",
    ),
    "update_moderator_permissions": strawberry.field(
        resolver=m_update_moderator_permissions,
        name="updateModeratorPermissions",
        description="Update a moderator's permissions for a corpus.\nOnly corpus owners can update moderator permissions.",
    ),
    "rollback_moderation_action": strawberry.field(
        resolver=m_rollback_moderation_action,
        name="rollbackModerationAction",
        description="Rollback a moderation action by executing its inverse.\n- delete_message -> restore_message\n- delete_thread -> restore_thread\n- lock_thread -> unlock_thread\n- pin_thread -> unpin_thread\n\nOnly moderators with appropriate permissions can rollback.\nCreates a new ModerationAction record for the rollback.",
    ),
}
