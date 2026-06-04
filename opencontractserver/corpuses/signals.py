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
    from opencontractserver.documents.models import Document, DocumentPath

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
# Corpus auto-branding trigger (logo + Readme.CAML on creation)
# =============================================================================
#
# Fires once when a corpus is first created. Gated so it only runs for genuine
# user-facing corpora that opted in and did not upload their own icon:
#
#   * ``created`` only (never on update)
#   * not a fixture/test save (``_skip_signals``)
#   * install-wide kill-switch ``settings.CORPUS_AUTO_BRANDING_ENABLED``
#   * not a personal "My Documents" corpus (auto-provisioned per user)
#   * the per-corpus opt-out flag ``auto_branding_enabled``
#   * no icon uploaded at creation (uploading one opts the corpus out)
#
# The work is deferred to a Celery task via ``transaction.on_commit`` so the
# corpus row (and its creator-permission grant) is durable first. The task is
# fire-and-forget — branding never blocks corpus creation.


@receiver(post_save, sender="corpuses.Corpus")
def trigger_corpus_branding_on_creation(
    sender: type[Corpus],
    instance: Corpus,
    created: bool,
    **kwargs: Any,
) -> None:
    """Queue logo + Readme.CAML generation for a newly-created corpus."""
    from django.conf import settings

    if not created:
        return
    if hasattr(instance, "_skip_signals"):
        return
    if not getattr(settings, "CORPUS_AUTO_BRANDING_ENABLED", False):
        return
    if instance.is_personal:
        return
    if not instance.auto_branding_enabled:
        return
    if instance.icon:
        # User uploaded their own image — opt out of auto-branding entirely.
        return
    if instance.creator_id is None:
        return

    corpus_id = instance.pk
    user_id = instance.creator_id

    def _queue() -> None:
        from opencontractserver.tasks.corpus_tasks import generate_corpus_branding

        generate_corpus_branding.delay(corpus_id=corpus_id, user_id=user_id)
        logger.info(
            "[CorpusBranding] Queued auto-branding for corpus %s (creator %s)",
            corpus_id,
            user_id,
        )

    transaction.on_commit(_queue)


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


# =============================================================================
# Readme.CAML description cache refresh
# =============================================================================
#
# The Readme.CAML Document body is the canonical source of truth for a
# corpus's description (spec §4.2). ``Corpus.description``,
# ``Corpus.description_preview``, and ``Corpus.readme_caml_document_id``
# are auto-maintained projections refreshed by these receivers whenever
# the underlying Readme.CAML Document (or its DocumentPath head) changes.
#
# Implementation notes:
#
# * All cache writes use ``Corpus.objects.filter(pk=...).update(...)``
#   so this refresh does NOT re-fire ``Corpus.post_save``.  That keeps
#   the loop-free / no-over-notify invariant from spec §4.4.
# * The actual work is deferred via ``transaction.on_commit`` so the
#   originating CAML write is durable before we read the file back.
#   Tests must wrap the trigger code in ``captureOnCommitCallbacks``.
# * Each handler iterates the corpus IDs owning the doc via a
#   ``DocumentPath`` join — normally there's exactly one corpus, but the
#   design handles ≥0 defensively per spec §4.4 / risk table.
# * Errors are logged but never raised.  Cache failure must NOT block
#   the underlying Document save (spec §6).


def _is_readme_caml_document(doc: Document) -> bool:
    """Return ``True`` iff ``doc`` is a corpus Readme.CAML article.

    KNOWN FRAGILITY: this keys on the user-editable ``title`` + ``file_type``
    rather than a structural marker. A user who renames their Readme.CAML doc
    (or creates an unrelated ``text/markdown`` doc titled "Readme.CAML") would
    trip these signals into a spurious cache refresh. The refresh is
    idempotent and corpus-scoped (it re-derives from the current CAML head via
    DocumentPath), so a false positive is wasteful but not corrupting. A
    model-level flag (e.g. a ``Document.is_corpus_readme`` boolean) would
    harden this; tracked as TODO(#1848).
    """
    from opencontractserver.constants.document_processing import (
        CAML_ARTICLE_TITLE,
        MARKDOWN_MIME_TYPE,
    )

    return doc.title == CAML_ARTICLE_TITLE and doc.file_type == MARKDOWN_MIME_TYPE


# Cache-refresh + body-read helpers live in
# ``corpuses/services/description_cache`` so non-signal callers (V2
# import shim, GraphQL descriptionRevisions facade) can share the same
# I/O + atomic-update contract.
from opencontractserver.corpuses.services.description_cache import (  # noqa: E402
    refresh_description_cache_for_corpus,
)


def _corpus_ids_owning_caml_doc(doc_id: int) -> list[int]:
    """Return corpus IDs whose current Readme.CAML path points at ``doc_id``.

    Only considers active (``is_current=True, is_deleted=False``)
    ``DocumentPath`` rows — a soft-deleted or historical path no longer
    owns the doc as the corpus's CAML head.
    """
    from opencontractserver.documents.models import DocumentPath

    return list(
        DocumentPath.objects.filter(
            document_id=doc_id,
            is_current=True,
            is_deleted=False,
        ).values_list("corpus_id", flat=True)
    )


@receiver(post_save, sender="documents.Document")
def refresh_corpus_description_cache_on_caml_save(
    sender: type[Document],
    instance: Document,
    **kwargs: Any,
) -> None:
    """Refresh corpus description cache whenever a Readme.CAML Document
    is saved.

    Cheap pre-check on title/file_type filters out every non-CAML
    Document save before we look at DocumentPath. The actual refresh is
    deferred via ``transaction.on_commit`` so the saved instance (and
    its txt_extract_file bytes) are durable before we read them back.
    """
    if not _is_readme_caml_document(instance):
        return
    doc_id = instance.pk

    def _kickoff() -> None:
        for corpus_id in _corpus_ids_owning_caml_doc(doc_id):
            refresh_description_cache_for_corpus(corpus_id)

    transaction.on_commit(_kickoff)


@receiver(post_delete, sender="documents.Document")
def clear_corpus_description_cache_on_caml_delete(
    sender: type[Document],
    instance: Document,
    **kwargs: Any,
) -> None:
    """Clear / refresh corpus description cache on Readme.CAML hard
    delete.

    Resolves the affected corpus IDs *now* (before the on_commit fires)
    because the ``DocumentPath`` FK to Document is ``PROTECT`` — by the
    time the Document row is gone, all of its paths must already have
    been removed too. Capturing the IDs at signal time keeps the refresh
    pointed at the right set of corpuses.
    """
    if not _is_readme_caml_document(instance):
        return

    affected = _corpus_ids_owning_caml_doc(instance.pk)

    def _kickoff() -> None:
        for corpus_id in affected:
            refresh_description_cache_for_corpus(corpus_id)

    transaction.on_commit(_kickoff)


@receiver(post_save, sender="documents.DocumentPath")
def refresh_corpus_description_cache_on_path_save(
    sender: type[DocumentPath],
    instance: DocumentPath,
    **kwargs: Any,
) -> None:
    """Refresh on DocumentPath save.

    Catches:
    * version-up edits (new DocumentPath flipping ``is_current``),
    * soft-delete edits (``is_deleted`` toggled to True),
    * restore edits (``is_deleted`` toggled back to False).

    Filtered to paths named ``Readme.CAML`` whose Document is a
    Readme.CAML markdown doc — every other path save is a no-op for the
    cache.
    """
    from opencontractserver.constants.document_processing import (
        CAML_ARTICLE_TITLE,
    )
    from opencontractserver.documents.models import Document

    if instance.path != CAML_ARTICLE_TITLE:
        return
    if instance.document_id is None:
        return

    doc = (
        Document.objects.filter(pk=instance.document_id)
        .only("title", "file_type")
        .first()
    )
    if doc is None or not _is_readme_caml_document(doc):
        return

    corpus_id = instance.corpus_id
    transaction.on_commit(lambda: refresh_description_cache_for_corpus(corpus_id))


@receiver(post_delete, sender="documents.DocumentPath")
def refresh_corpus_description_cache_on_path_delete(
    sender: type[DocumentPath],
    instance: DocumentPath,
    **kwargs: Any,
) -> None:
    """Refresh on DocumentPath delete (hard delete or
    ``permanently_delete_document`` cascade).

    The ``path`` filter is cheap — only ``Readme.CAML`` rows trigger a
    refresh. We don't try to confirm the Document is a CAML doc here
    because the Document may be already gone (PROTECT means the path
    row is deleted before the Document, but the
    ``permanently_delete_document`` cleanup path can fire path deletes
    independently). Recomputing for a non-CAML path is a no-op anyway
    because the head-resolution query will return ``None``.
    """
    from opencontractserver.constants.document_processing import (
        CAML_ARTICLE_TITLE,
    )

    if instance.path != CAML_ARTICLE_TITLE:
        return

    corpus_id = instance.corpus_id
    transaction.on_commit(lambda: refresh_description_cache_for_corpus(corpus_id))
