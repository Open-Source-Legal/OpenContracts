"""
Signal handlers for the conversations app.

Handles automatic updates of denormalized vote counts and user reputation
when votes are created, updated, or deleted.
"""

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from opencontractserver.conversations.models import (
    MessageVote,
    UserReputation,
    VoteType,
)


@receiver(post_save, sender=MessageVote)
def update_vote_counts_on_save(sender, instance, created, **kwargs):
    """
    Update denormalized vote counts on ChatMessage when a vote is created or changed.
    Always recalculate from scratch to ensure accuracy and avoid signal loops.
    """
    recalculate_message_vote_counts(instance.message)


@receiver(post_delete, sender=MessageVote)
def update_vote_counts_on_delete(sender, instance, **kwargs):
    """
    Update denormalized vote counts on ChatMessage when a vote is deleted.
    Recalculate from scratch to ensure accuracy.
    """
    recalculate_message_vote_counts(instance.message)


def recalculate_message_vote_counts(message):
    """
    Recalculate vote counts for a message from scratch.
    Used when a vote is changed to ensure accuracy.
    """
    from django.db.models import Count, Q

    vote_counts = message.votes.aggregate(
        upvotes=Count("id", filter=Q(vote_type=VoteType.UPVOTE)),
        downvotes=Count("id", filter=Q(vote_type=VoteType.DOWNVOTE)),
    )

    message.upvote_count = vote_counts["upvotes"] or 0
    message.downvote_count = vote_counts["downvotes"] or 0
    message.save(update_fields=["upvote_count", "downvote_count"])


@receiver(post_save, sender=MessageVote)
def update_reputation_on_vote_change(sender, instance, created, **kwargs):
    """
    Trigger reputation recalculation when a vote is created or changed.
    This can be made asynchronous with Celery for better performance.
    """
    message = instance.message
    message_author = message.creator

    # Update global reputation
    update_user_reputation(message_author, corpus=None)

    # Update corpus-specific reputation if message is in a corpus
    if message.conversation.chat_with_corpus:
        update_user_reputation(message_author, message.conversation.chat_with_corpus)


@receiver(post_delete, sender=MessageVote)
def update_reputation_on_vote_delete(sender, instance, **kwargs):
    """
    Trigger reputation recalculation when a vote is deleted.
    """
    message = instance.message
    message_author = message.creator

    # Update global reputation
    update_user_reputation(message_author, corpus=None)

    # Update corpus-specific reputation if message is in a corpus
    if message.conversation.chat_with_corpus:
        update_user_reputation(message_author, message.conversation.chat_with_corpus)


def update_user_reputation(user, corpus=None):
    """
    Calculate and update user reputation based on votes received.

    Args:
        user: The user whose reputation to update
        corpus: The corpus to calculate reputation for (None = global)
    """
    from django.db.models import Count, Q

    from opencontractserver.conversations.models import ChatMessage

    # Get all messages by this user in the relevant scope
    messages_query = ChatMessage.objects.filter(creator=user)

    if corpus:
        messages_query = messages_query.filter(conversation__chat_with_corpus=corpus)

    # Calculate vote counts across all user's messages
    vote_stats = messages_query.aggregate(
        total_upvotes=Count(
            "votes",
            filter=Q(votes__vote_type=VoteType.UPVOTE),
        ),
        total_downvotes=Count(
            "votes",
            filter=Q(votes__vote_type=VoteType.DOWNVOTE),
        ),
    )

    total_upvotes = vote_stats["total_upvotes"] or 0
    total_downvotes = vote_stats["total_downvotes"] or 0
    reputation_score = total_upvotes - total_downvotes

    # Create or update reputation record
    reputation, created = UserReputation.objects.update_or_create(
        user=user,
        corpus=corpus,
        defaults={
            "reputation_score": reputation_score,
            "total_upvotes_received": total_upvotes,
            "total_downvotes_received": total_downvotes,
            "creator": user,  # Set creator for BaseOCModel
        },
    )

    return reputation
