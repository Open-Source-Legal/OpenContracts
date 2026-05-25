"""
Corpus signals for corpus action triggering.

## Document-based triggers (DEPRECATED):

As of the document versioning architecture update (Issue #654), document-based
corpus action triggering has moved to direct invocation in:

- add_document() in corpuses/models.py - triggers if doc is ready
- import_document() in documents/versioning.py - triggers if doc is ready
- set_doc_lock_state() in tasks/doc_tasks.py - triggers when processing completes

This approach uses DocumentPath as the source of truth for corpus membership.

## Thread/Message-based triggers (ACTIVE):

This file contains signal handlers for NEW_THREAD and NEW_MESSAGE corpus action
triggers, which fire when:

- A new THREAD conversation is created in a corpus
- A new HUMAN message is posted to a THREAD conversation in a corpus

These handlers use transaction.on_commit to ensure proper persistence before
queuing async tasks.

See docs/corpus_actions/ for the full architecture.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

if TYPE_CHECKING:
    from opencontractserver.conversations.models import ChatMessage, Conversation
    from opencontractserver.corpuses.models import Corpus, CorpusVote

logger = logging.getLogger(__name__)


# NOTE: Document-based signal handlers have been removed as corpus action
# triggering is now handled directly in:
#
# 1. add_document() - triggers actions if document is ready (backend_lock=False)
# 2. import_document() - triggers actions if document is ready
# 3. set_doc_lock_state() - triggers actions when document processing completes
#
# This ensures DocumentPath (not M2M) is used as the source of truth for
# determining which corpuses a document belongs to.


# =============================================================================
# Thread/Message Corpus Action Triggers
# =============================================================================


@receiver(post_save, sender="conversations.Conversation")
def trigger_corpus_actions_on_thread_creation(
    sender: type[Conversation],
    instance: Conversation,
    created: bool,
    **kwargs: Any,
) -> None:
    """
    Trigger NEW_THREAD corpus actions when a discussion thread is created.

    Only triggers for:
    - Newly created conversations (not updates)
    - THREAD type conversations (not CHAT)
    - Conversations linked to a corpus

    Uses transaction.on_commit to ensure the thread is fully persisted
    before queuing the async task.
    """
    # Import here to avoid circular imports
    from opencontractserver.conversations.models import ConversationTypeChoices

    conversation = instance

    # Log entry point for debugging
    logger.info(
        f"[ThreadSignal] post_save fired: id={conversation.pk}, "
        f"created={created}, type={conversation.conversation_type}, "
        f"corpus_id={conversation.chat_with_corpus_id}"
    )

    if not created:
        logger.debug("[ThreadSignal] Skipping - not a new conversation")
        return

    # Only process discussion threads
    if conversation.conversation_type != ConversationTypeChoices.THREAD:
        logger.debug(
            f"[ThreadSignal] Skipping - not THREAD type "
            f"(got {conversation.conversation_type})"
        )
        return

    # Skip if no corpus linkage
    if not conversation.chat_with_corpus_id:
        logger.info(
            f"[ThreadSignal] Thread {conversation.pk} has no corpus linkage, "
            f"skipping corpus actions"
        )
        return

    # Skip signal during tests/fixtures
    if hasattr(instance, "_skip_signals"):
        logger.debug("[ThreadSignal] Skipping - _skip_signals set")
        return

    def queue_thread_action() -> None:
        from opencontractserver.tasks.corpus_tasks import process_thread_corpus_action

        process_thread_corpus_action.delay(
            corpus_id=conversation.chat_with_corpus_id,
            conversation_id=conversation.pk,
            user_id=conversation.creator_id,
            trigger="new_thread",
        )
        logger.info(
            f"Queued NEW_THREAD corpus actions for thread {conversation.pk} "
            f"in corpus {conversation.chat_with_corpus_id}"
        )

    transaction.on_commit(queue_thread_action)


@receiver(post_save, sender="conversations.ChatMessage")
def trigger_corpus_actions_on_message_creation(
    sender: type[ChatMessage],
    instance: ChatMessage,
    created: bool,
    **kwargs: Any,
) -> None:
    """
    Trigger NEW_MESSAGE corpus actions when a message is posted.

    Only triggers for:
    - Newly created messages (not updates)
    - HUMAN type messages (not system or LLM messages to avoid loops)
    - Messages in THREAD type conversations
    - Threads linked to a corpus

    Uses transaction.on_commit to ensure the message is fully persisted.
    """
    # Import here to avoid circular imports
    from opencontractserver.conversations.models import (
        ConversationTypeChoices,
        MessageTypeChoices,
    )

    message = instance

    # Log entry point for debugging
    logger.info(
        f"[MessageSignal] post_save fired: id={message.pk}, "
        f"created={created}, type={message.msg_type}, "
        f"conversation_id={message.conversation_id}"
    )

    if not created:
        logger.debug("[MessageSignal] Skipping - not a new message")
        return

    # Only process human messages (avoid infinite loops with agent messages)
    if message.msg_type != MessageTypeChoices.HUMAN:
        logger.debug(
            f"[MessageSignal] Skipping - not HUMAN type (got {message.msg_type})"
        )
        return

    # Skip signal during tests/fixtures
    if hasattr(instance, "_skip_signals"):
        logger.debug("[MessageSignal] Skipping - _skip_signals set")
        return

    # Access the conversation FK - this may trigger a single DB query if not already
    # loaded on the instance. This is acceptable since signals fire once per message
    # save, not in a loop (so it's not an N+1 issue).
    conversation = message.conversation

    # Only process messages in discussion threads
    if conversation.conversation_type != ConversationTypeChoices.THREAD:
        logger.debug(
            f"[MessageSignal] Skipping - conversation not THREAD type "
            f"(got {conversation.conversation_type})"
        )
        return

    # Skip if no corpus linkage
    if not conversation.chat_with_corpus_id:
        logger.info(
            f"[MessageSignal] Thread {conversation.pk} has no corpus linkage, "
            f"skipping corpus actions"
        )
        return

    def queue_message_action() -> None:
        from opencontractserver.tasks.corpus_tasks import process_message_corpus_action

        process_message_corpus_action.delay(
            corpus_id=conversation.chat_with_corpus_id,
            conversation_id=conversation.pk,
            message_id=message.pk,
            user_id=message.creator_id,
            trigger="new_message",
        )
        logger.info(
            f"Queued NEW_MESSAGE corpus actions for message {message.pk} "
            f"in thread {conversation.pk}, corpus {conversation.chat_with_corpus_id}"
        )

    transaction.on_commit(queue_message_action)


# =============================================================================
# Corpus vote count denormalization
# =============================================================================
#
# Mirrors the ``MessageVote`` count-maintenance pattern in
# ``opencontractserver/conversations/signals.py``: every save/delete of a
# ``CorpusVote`` row recomputes the parent corpus's ``upvote_count``,
# ``downvote_count``, and ``score`` from scratch.  Recompute-from-scratch is
# deliberate over the cheaper incremental ``+= / -=`` form — it makes the
# counts self-healing if a vote ever lands without firing this signal (data
# import, raw SQL, lost transaction), and the aggregate is a single indexed
# ``COUNT(*) ... GROUP BY vote_type`` against the small per-corpus vote set.


def _recalculate_corpus_vote_counts(corpus: Corpus) -> None:
    """Refresh ``upvote_count`` / ``downvote_count`` / ``score`` on ``corpus``.

    Computed in one aggregate query against the corpus's own votes; uses
    ``QuerySet.update`` so the parent ``Corpus.save()`` override (which
    bumps ``modified`` and runs the public-visibility propagation logic)
    does not fire on every vote.
    """
    from django.db.models import Count, Q

    from opencontractserver.corpuses.models import Corpus, CorpusVoteType

    counts = corpus.votes.aggregate(
        upvotes=Count("id", filter=Q(vote_type=CorpusVoteType.UPVOTE)),
        downvotes=Count("id", filter=Q(vote_type=CorpusVoteType.DOWNVOTE)),
    )
    upvotes = counts["upvotes"] or 0
    downvotes = counts["downvotes"] or 0

    # ``filter(pk=...).update(...)`` avoids the full Corpus.save() override
    # (which would re-bump ``modified`` and run the public-flip propagation
    # check on every vote). Voting must not look like a corpus content edit.
    Corpus.objects.filter(pk=corpus.pk).update(
        upvote_count=upvotes,
        downvote_count=downvotes,
        score=upvotes - downvotes,
    )


@receiver(post_save, sender="corpuses.CorpusVote")
def update_corpus_vote_counts_on_save(
    sender: type[CorpusVote],
    instance: CorpusVote,
    created: bool,
    **kwargs: Any,
) -> None:
    """Recompute corpus vote counts whenever a vote is created or changed."""
    _recalculate_corpus_vote_counts(instance.corpus)


@receiver(post_delete, sender="corpuses.CorpusVote")
def update_corpus_vote_counts_on_delete(
    sender: type[CorpusVote],
    instance: CorpusVote,
    **kwargs: Any,
) -> None:
    """Recompute corpus vote counts whenever a vote is removed.

    Wrapped in a try/except guard because cascade-deleting a Corpus also
    cascade-deletes its CorpusVote rows; recomputing counts after the
    parent is gone would raise ``Corpus.DoesNotExist``.
    """
    from opencontractserver.corpuses.models import Corpus

    try:
        corpus = Corpus.objects.get(pk=instance.corpus_id)
    except Corpus.DoesNotExist:
        # The parent corpus is gone — nothing to refresh.
        return
    _recalculate_corpus_vote_counts(corpus)
