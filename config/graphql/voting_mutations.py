"""
GraphQL mutations for voting system.

This module provides mutations for upvoting/downvoting messages:
- VoteMessageMutation: Create or update vote on a message
- RemoveVoteMutation: Remove user's vote from a message
"""

import logging

import graphene
from graphql_jwt.decorators import login_required
from graphql_relay import from_global_id

from config.graphql.graphene_types import MessageType
from config.graphql.ratelimits import graphql_ratelimit
from opencontractserver.conversations.models import ChatMessage, MessageVote
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import (
    set_permissions_for_obj_to_user,
    user_has_permission_for_obj,
)

logger = logging.getLogger(__name__)


class VoteMessageMutation(graphene.Mutation):
    """
    Create or update a vote on a message.
    Users can upvote or downvote messages. Changing vote type updates the existing vote.
    Users cannot vote on their own messages.
    """

    class Arguments:
        message_id = graphene.String(
            required=True, description="ID of the message to vote on"
        )
        vote_type = graphene.String(
            required=True, description="Vote type: 'upvote' or 'downvote'"
        )

    ok = graphene.Boolean()
    message = graphene.String()
    obj = graphene.Field(MessageType)

    @login_required
    @graphql_ratelimit(rate="60/m")
    def mutate(root, info, message_id, vote_type):
        ok = False
        obj = None
        message_text = ""

        try:
            user = info.context.user

            # Validate vote_type
            vote_type_lower = vote_type.lower()
            if vote_type_lower not in ["upvote", "downvote"]:
                return VoteMessageMutation(
                    ok=False,
                    message="Invalid vote_type. Must be 'upvote' or 'downvote'",
                    obj=None,
                )

            # Get message
            try:
                message_pk = from_global_id(message_id)[1]
                chat_message = ChatMessage.objects.get(pk=message_pk)
            except ChatMessage.DoesNotExist:
                return VoteMessageMutation(
                    ok=False, message="Message not found", obj=None
                )

            # Check if user has permission to read the conversation
            conversation = chat_message.conversation
            if not user_has_permission_for_obj(
                user, conversation, PermissionTypes.READ
            ):
                return VoteMessageMutation(
                    ok=False,
                    message="You do not have permission to vote on messages in this conversation",
                    obj=None,
                )

            # Prevent users from voting on their own messages
            if chat_message.creator == user:
                return VoteMessageMutation(
                    ok=False, message="You cannot vote on your own messages", obj=None
                )

            # Check if vote already exists
            existing_vote = MessageVote.objects.filter(
                message=chat_message, creator=user
            ).first()

            if existing_vote:
                # Update existing vote if vote type changed
                if existing_vote.vote_type != vote_type_lower:
                    existing_vote.vote_type = vote_type_lower
                    existing_vote.save(update_fields=["vote_type"])
                    message_text = f"Vote updated to {vote_type_lower}"
                else:
                    message_text = f"Vote already set to {vote_type_lower}"
            else:
                # Create new vote
                existing_vote = MessageVote.objects.create(
                    message=chat_message, vote_type=vote_type_lower, creator=user
                )
                # Set permissions for the creator
                set_permissions_for_obj_to_user(
                    user, existing_vote, [PermissionTypes.CRUD]
                )
                message_text = f"Vote ({vote_type_lower}) added successfully"

            ok = True
            obj = chat_message

        except Exception as e:
            logger.error(f"Error voting on message: {e}", exc_info=True)
            message_text = f"Failed to vote on message: {str(e)}"

        return VoteMessageMutation(ok=ok, message=message_text, obj=obj)


class RemoveVoteMutation(graphene.Mutation):
    """
    Remove user's vote from a message.
    """

    class Arguments:
        message_id = graphene.String(
            required=True, description="ID of the message to remove vote from"
        )

    ok = graphene.Boolean()
    message = graphene.String()
    obj = graphene.Field(MessageType)

    @login_required
    @graphql_ratelimit(rate="60/m")
    def mutate(root, info, message_id):
        ok = False
        obj = None
        message_text = ""

        try:
            user = info.context.user

            # Get message
            try:
                message_pk = from_global_id(message_id)[1]
                chat_message = ChatMessage.objects.get(pk=message_pk)
            except ChatMessage.DoesNotExist:
                return RemoveVoteMutation(
                    ok=False, message="Message not found", obj=None
                )

            # Check if user has permission to read the conversation
            conversation = chat_message.conversation
            if not user_has_permission_for_obj(
                user, conversation, PermissionTypes.READ
            ):
                return RemoveVoteMutation(
                    ok=False,
                    message="You do not have permission to access this conversation",
                    obj=None,
                )

            # Check if vote exists
            existing_vote = MessageVote.objects.filter(
                message=chat_message, creator=user
            ).first()

            if existing_vote:
                existing_vote.delete()
                message_text = "Vote removed successfully"
            else:
                message_text = "No vote found to remove"

            ok = True
            obj = chat_message

        except Exception as e:
            logger.error(f"Error removing vote: {e}", exc_info=True)
            message_text = f"Failed to remove vote: {str(e)}"

        return RemoveVoteMutation(ok=ok, message=message_text, obj=obj)
