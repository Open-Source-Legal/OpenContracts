"""
Signal handlers for the badges app.

These handlers automatically trigger badge checks when relevant user actions occur.
This file is imported in apps.py ready() method to ensure signals are connected.
"""

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


@receiver(post_save, sender="conversations.ChatMessage")
def check_message_badges(sender, instance, created, **kwargs):
    """
    Check message-related badges when a new message is created.

    Triggers checks for:
    - first_post: User's first message
    - message_count: User reaches N messages

    Args:
        sender: The ChatMessage model class
        instance: The ChatMessage instance that was saved
        created: Boolean indicating if this is a new instance
        **kwargs: Additional keyword arguments
    """
    if not created:
        return

    # Skip signal during tests/fixtures if needed
    if hasattr(instance, "_skip_signals"):
        return

    message = instance

    # Import here to avoid circular dependencies
    from opencontractserver.tasks.badge_tasks import check_auto_badges

    user_id = message.creator.id

    # Check global badges
    check_auto_badges.delay(user_id=user_id)
    logger.debug(
        f"Triggered global badge checks for user {message.creator.username} "
        f"after creating message {message.id}"
    )

    # Check corpus-specific badges if message is in a corpus conversation
    if message.conversation and message.conversation.chat_with_corpus:
        corpus_id = message.conversation.chat_with_corpus.id
        check_auto_badges.delay(user_id=user_id, corpus_id=corpus_id)
        logger.debug(
            f"Triggered corpus badge checks for user {message.creator.username} "
            f"in corpus {message.conversation.chat_with_corpus.title}"
        )


@receiver(post_save, sender="annotations.Annotation")
def check_annotation_badges(sender, instance, created, **kwargs):
    """
    Check annotation-related badges when a new annotation is created.

    Triggers checks for:
    - corpus_contribution: User contributes documents/annotations to corpus

    Args:
        sender: The Annotation model class
        instance: The Annotation instance that was saved
        created: Boolean indicating if this is a new instance
        **kwargs: Additional keyword arguments
    """
    if not created:
        return

    # Skip signal during tests/fixtures if needed
    if hasattr(instance, "_skip_signals"):
        return

    annotation = instance

    # Import here to avoid circular dependencies
    from opencontractserver.tasks.badge_tasks import check_auto_badges

    user_id = annotation.creator.id

    # Check corpus-specific badges if annotation has corpus
    if annotation.corpus:
        corpus_id = annotation.corpus.id
        check_auto_badges.delay(user_id=user_id, corpus_id=corpus_id)
        logger.debug(
            f"Triggered corpus badge checks for user {annotation.creator.username} "
            f"after creating annotation in corpus {annotation.corpus.title}"
        )


# Note: Document-corpus relationship badges
#
# The Corpus model has a ManyToManyField to Document (corpus.documents), so we need to
# listen to the through table's m2m_changed signal to detect when documents are added.
# This is more complex and can be added in the future if needed:
#
# from django.db.models.signals import m2m_changed
#
# @receiver(m2m_changed, sender=Corpus.documents.through)
# def check_document_contribution_badges(sender, instance, action, **kwargs):
#     if action == "post_add":
#         # Determine which user added the documents
#         # Trigger check_auto_badges for corpus_contribution
#         pass
