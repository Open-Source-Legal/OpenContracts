"""
Corpus forking task v2 - modular, enumerable forking system.

This module provides an improved corpus forking implementation that:
1. Is configuration-driven via ForkableModelType enum
2. Forks all relevant models (documents, annotations, relationships, extracts, etc.)
3. Uses proper permission handling per consolidated_permissioning_guide.md
4. Provides better performance via batching where possible
5. Has comprehensive error handling and logging

Usage:
    from opencontractserver.tasks.fork_tasks_v2 import fork_corpus_v2

    # Trigger async forking
    fork_corpus_v2.delay(
        new_corpus_id=123,
        source_corpus_id=456,
        user_id=1,
    )
"""

import logging
from typing import Optional

from django.contrib.auth import get_user_model
from django.db import transaction

from config import celery_app
from opencontractserver.annotations.models import Annotation
from opencontractserver.corpuses.models import Corpus
from opencontractserver.utils.fork_handlers import (
    fork_annotation_labels,
    fork_annotations,
    fork_chat_messages,
    fork_columns,
    fork_conversations,
    fork_corpus_folders,
    fork_datacells,
    fork_documents,
    fork_extracts,
    fork_fieldsets,
    fork_label_set,
    fork_note_revisions,
    fork_notes,
    fork_relationships,
)
from opencontractserver.utils.fork_utils import ForkContext, ForkResult

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

User = get_user_model()


@celery_app.task(bind=True, max_retries=3)
def fork_corpus_v2(
    self,
    new_corpus_id: int,
    source_corpus_id: int,
    user_id: int,
    fork_extracts_flag: bool = True,
    fork_conversations_flag: bool = True,
    fork_notes_flag: bool = True,
) -> Optional[dict]:
    """
    Fork a corpus with all its content using modular handlers.

    This is an improved version of fork_corpus that:
    - Forks all relevant models (relationships, extracts, conversations, notes)
    - Uses proper permission handling per the permission guide
    - Provides better error handling and logging
    - Returns detailed statistics

    Args:
        new_corpus_id: ID of the new (target) corpus (already created, locked)
        source_corpus_id: ID of the source corpus to fork from
        user_id: ID of the user performing the fork
        fork_extracts_flag: Whether to fork extracts and datacells
        fork_conversations_flag: Whether to fork conversations and messages
        fork_notes_flag: Whether to fork notes and revisions

    Returns:
        Dictionary with fork results and statistics, or None on failure
    """
    logger.info(
        f"Starting fork_corpus_v2:\n"
        f"  source_corpus_id: {source_corpus_id}\n"
        f"  new_corpus_id: {new_corpus_id}\n"
        f"  user_id: {user_id}\n"
        f"  fork_extracts: {fork_extracts_flag}\n"
        f"  fork_conversations: {fork_conversations_flag}\n"
        f"  fork_notes: {fork_notes_flag}"
    )

    # Get the target corpus (already created by mutation, locked)
    try:
        target_corpus = Corpus.objects.get(pk=new_corpus_id)
    except Corpus.DoesNotExist:
        logger.error(f"Target corpus {new_corpus_id} not found")
        return None

    try:
        source_corpus = Corpus.objects.get(pk=source_corpus_id)
    except Corpus.DoesNotExist:
        logger.error(f"Source corpus {source_corpus_id} not found")
        target_corpus.backend_lock = False
        target_corpus.error = True
        target_corpus.save()
        return None

    # Initialize fork context
    ctx = ForkContext(
        source_corpus_id=source_corpus_id,
        target_corpus_id=new_corpus_id,
        user_id=user_id,
    )

    result = ForkResult(success=False, new_corpus_id=new_corpus_id, context=ctx)

    try:
        with transaction.atomic():
            # ========== Phase 1: Organization Models ==========
            logger.info("Phase 1: Forking organization models...")

            # Fork LabelSet
            source_label_set_id = source_corpus.label_set_id
            new_label_set_id = fork_label_set(ctx, source_label_set_id)

            # Fork AnnotationLabels
            labels_forked = fork_annotation_labels(
                ctx, source_label_set_id, new_label_set_id
            )
            logger.info(f"Forked {labels_forked} annotation labels")

            # Fork CorpusFolders
            result.folders_forked = fork_corpus_folders(ctx)

            # ========== Phase 2: Documents ==========
            logger.info("Phase 2: Forking documents...")

            # Get document IDs that user has read access to
            doc_ids = list(
                source_corpus.get_documents().values_list("id", flat=True)
            )
            result.documents_forked = fork_documents(ctx, doc_ids)

            # ========== Phase 3: Annotations ==========
            logger.info("Phase 3: Forking annotations...")

            # Get annotation IDs (non-analysis only)
            annotation_ids = list(
                Annotation.objects.filter(
                    corpus_id=source_corpus_id,
                    analysis__isnull=True,
                ).values_list("id", flat=True)
            )
            result.annotations_forked = fork_annotations(ctx, annotation_ids)

            # ========== Phase 4: Relationships ==========
            logger.info("Phase 4: Forking relationships...")
            result.relationships_forked = fork_relationships(ctx)

            # ========== Phase 5: Extracts (optional) ==========
            if fork_extracts_flag:
                logger.info("Phase 5: Forking extracts...")
                result.fieldsets_forked = fork_fieldsets(ctx)
                fork_columns(ctx)  # Columns don't count separately
                result.extracts_forked = fork_extracts(ctx)
                result.datacells_forked = fork_datacells(ctx)
            else:
                logger.info("Phase 5: Skipping extracts (disabled)")

            # ========== Phase 6: Conversations (optional) ==========
            if fork_conversations_flag:
                logger.info("Phase 6: Forking conversations...")
                result.conversations_forked = fork_conversations(ctx)
                result.messages_forked = fork_chat_messages(ctx)
            else:
                logger.info("Phase 6: Skipping conversations (disabled)")

            # ========== Phase 7: Notes (optional) ==========
            if fork_notes_flag:
                logger.info("Phase 7: Forking notes...")
                result.notes_forked = fork_notes(ctx)
                fork_note_revisions(ctx)  # Revisions don't count separately
            else:
                logger.info("Phase 7: Skipping notes (disabled)")

            # ========== Finalize ==========
            target_corpus.backend_lock = False
            target_corpus.save()

            result.success = True
            logger.info(
                f"Fork completed successfully:\n"
                f"  Documents: {result.documents_forked}\n"
                f"  Annotations: {result.annotations_forked}\n"
                f"  Relationships: {result.relationships_forked}\n"
                f"  Fieldsets: {result.fieldsets_forked}\n"
                f"  Extracts: {result.extracts_forked}\n"
                f"  Datacells: {result.datacells_forked}\n"
                f"  Conversations: {result.conversations_forked}\n"
                f"  Messages: {result.messages_forked}\n"
                f"  Notes: {result.notes_forked}\n"
                f"  Folders: {result.folders_forked}"
            )

            return {
                "success": True,
                "new_corpus_id": new_corpus_id,
                "documents_forked": result.documents_forked,
                "annotations_forked": result.annotations_forked,
                "relationships_forked": result.relationships_forked,
                "fieldsets_forked": result.fieldsets_forked,
                "extracts_forked": result.extracts_forked,
                "datacells_forked": result.datacells_forked,
                "conversations_forked": result.conversations_forked,
                "messages_forked": result.messages_forked,
                "notes_forked": result.notes_forked,
                "folders_forked": result.folders_forked,
            }

    except Exception as e:
        logger.error(f"Error during fork: {e}", exc_info=True)

        # Mark corpus as errored
        target_corpus.backend_lock = False
        target_corpus.error = True
        target_corpus.save()

        result.success = False
        result.error_message = str(e)

        return {
            "success": False,
            "new_corpus_id": new_corpus_id,
            "error": str(e),
        }


# Backwards compatibility alias
def fork_corpus_legacy(
    new_corpus_id: str,
    doc_ids: list[str],
    label_set_id: str,
    annotation_ids: list[str],
    user_id: str,
) -> Optional[str]:
    """
    Legacy fork_corpus signature for backwards compatibility.

    Converts string IDs to ints and calls fork_corpus_v2.
    """
    from opencontractserver.corpuses.models import Corpus

    # Get source corpus from new corpus's parent
    target_corpus = Corpus.objects.get(pk=int(new_corpus_id))
    source_corpus_id = target_corpus.parent_id

    if not source_corpus_id:
        logger.error("Cannot determine source corpus from parent")
        return None

    result = fork_corpus_v2(
        new_corpus_id=int(new_corpus_id),
        source_corpus_id=source_corpus_id,
        user_id=int(user_id),
    )

    if result and result.get("success"):
        return str(result["new_corpus_id"])
    return None
