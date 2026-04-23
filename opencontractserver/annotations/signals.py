from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from opencontractserver.tasks.embeddings_task import (
    calculate_embedding_for_annotation_text,
    calculate_embedding_for_note_text,
)

if TYPE_CHECKING:
    from opencontractserver.annotations.models import Annotation, Note, Relationship

# Direct queries without caching

logger = logging.getLogger(__name__)

# Define static dispatch UIDs for signals
ANNOT_CREATE_UID = (
    "process_annot_on_create_atomic_uid_v1"  # Added _v1 for potential future changes
)
NOTE_CREATE_UID = "process_note_on_create_atomic_uid_v1"  # Added _v1

# Relationship signal UIDs
REL_CREATE_UPDATE_UID = "process_relationship_on_change_atomic_uid_v1"
REL_DELETE_UID = "process_relationship_on_delete_atomic_uid_v1"
REL_M2M_SOURCES_UID = "process_relationship_m2m_sources_changed_uid_v1"
REL_M2M_TARGETS_UID = "process_relationship_m2m_targets_changed_uid_v1"


def process_annot_on_create_atomic(
    sender: type[Annotation],
    instance: Annotation,
    created: bool,
    **kwargs: Any,
) -> None:
    """
    Signal handler to process an annotation after it is created.
    Queues tasks to calculate embeddings for the annotation.

    DUAL EMBEDDING STRATEGY:
    The embedding task now automatically creates both:
    - DEFAULT_EMBEDDER embedding (for global search)
    - Corpus-specific embedding (if corpus uses different embedder)

    Args:
        sender: The model class.
        instance: The annotation being saved.
        created (bool): True if a new record was created.
        **kwargs: Additional keyword arguments.
    """
    # When a new annotation is created *AND* no embeddings are present at creation,
    # hit the embeddings microservice. Since embeddings can be an array, need to test for None
    if created and instance.embedding is None:
        # Get corpus_id from annotation's corpus
        # Note: structural_set doesn't have a corpus field, so we only use direct corpus_id
        corpus_id: int | None = instance.corpus_id if instance.corpus_id else None

        logger.debug(
            f"Calculating embeddings for newly created annotation {instance.id} "
            f"(corpus_id={corpus_id})"
        )
        # Use task_id for deduplication to prevent duplicate embedding tasks
        # if two annotations are created simultaneously
        calculate_embedding_for_annotation_text.si(
            annotation_id=instance.id,
            corpus_id=corpus_id,
        ).apply_async(task_id=f"embed-annot-{instance.id}")

    # No cache invalidation needed - using direct queries


def process_note_on_create_atomic(
    sender: type[Note],
    instance: Note,
    created: bool,
    **kwargs: Any,
) -> None:
    """
    Signal handler to process a note after it is created.
    Queues tasks to calculate embeddings for the note.

    DUAL EMBEDDING STRATEGY:
    The embedding task now automatically creates both:
    - DEFAULT_EMBEDDER embedding (for global search)
    - Corpus-specific embedding (if corpus uses different embedder)

    Args:
        sender: The model class.
        instance: The note being saved.
        created (bool): True if a new record was created.
        **kwargs: Additional keyword arguments.
    """
    if created and instance.embedding is None:
        corpus_id: int | None = instance.corpus_id if instance.corpus else None
        logger.debug(
            f"Calculating embeddings for newly created note {instance.id} "
            f"(corpus_id={corpus_id})"
        )
        # Use task_id for deduplication to prevent duplicate embedding tasks
        calculate_embedding_for_note_text.si(
            note_id=instance.id,
            corpus_id=corpus_id,
        ).apply_async(task_id=f"embed-note-{instance.id}")


# NOTE: process_structural_annotation_for_corpuses is no longer needed with the new
# corpus-isolated structural annotation architecture and dual embedding strategy.
# The embedding task now automatically creates:
# 1. DEFAULT_EMBEDDER embedding (always, for global search)
# 2. Corpus-specific embedding (if corpus.preferred_embedder differs)
#
# With corpus-isolated StructuralAnnotationSets, each annotation belongs to exactly
# one corpus context, so there's no need to iterate over multiple corpuses.


def process_relationship_on_change_atomic(
    sender: type[Relationship],
    instance: Relationship,
    created: bool,
    **kwargs: Any,
) -> None:
    """
    Signal handler for Relationship create/update.
    Currently a no-op as we use direct queries without caching.
    """
    pass


def process_relationship_on_delete(
    sender: type[Relationship],
    instance: Relationship,
    **kwargs: Any,
) -> None:
    """
    Signal handler for Relationship delete.
    Currently a no-op as we use direct queries without caching.
    """
    pass


def process_relationship_m2m_changed(
    sender: type[Any],
    instance: Relationship,
    action: str,
    reverse: bool,
    model: type[Any],
    pk_set: set[int] | None,
    **kwargs: Any,
) -> None:
    """
    Signal handler for Relationship M2M (source/target annotations) changes.
    Currently a no-op as we use direct queries without caching.
    """
    pass
