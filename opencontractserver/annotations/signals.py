import logging

from opencontractserver.tasks.embeddings_task import (
    calculate_embedding_for_annotation_text,
    calculate_embedding_for_note_text,
)

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


def process_annot_on_create_atomic(sender, instance, created, **kwargs):
    """
    Signal handler to process an annotation after it is created.
    Queues tasks to calculate embeddings for the annotation.

    Args:
        sender: The model class.
        instance: The annotation being saved.
        created (bool): True if a new record was created.
        **kwargs: Additional keyword arguments.
    """
    # When a new annotation is created *AND* no embeddings are present at creation,
    # hit the embeddings microservice. Since embeddings can be an array, need to test for None
    if created and instance.embedding is None:
        logger.debug(
            f"Calculating default embeddings for newly created annotation {instance.id}"
        )
        calculate_embedding_for_annotation_text.si(
            annotation_id=instance.id
        ).apply_async()

    # No cache invalidation needed - using direct queries


def process_note_on_create_atomic(sender, instance, created, **kwargs):
    """
    Signal handler to process a note after it is created.
    Queues tasks to calculate embeddings for the note.

    Args:
        sender: The model class.
        instance: The note being saved.
        created (bool): True if a new record was created.
        **kwargs: Additional keyword arguments.
    """
    if created and instance.embedding is None:
        logger.debug(f"Calculating embeddings for newly created note {instance.id}")
        calculate_embedding_for_note_text.si(note_id=instance.id).apply_async()


# NOTE: The embedding task automatically creates:
# 1. DEFAULT_EMBEDDER embedding (always, for global search)
# 2. Corpus-specific embedding (if corpus.preferred_embedder differs)
#
# Structural annotations are copied per-corpus, so each annotation belongs to
# exactly one corpus context - no need to iterate over multiple corpuses.


def process_relationship_on_change_atomic(sender, instance, created, **kwargs):
    """
    Signal handler for Relationship create/update.
    Currently a no-op as we use direct queries without caching.
    """
    pass


def process_relationship_on_delete(sender, instance, **kwargs):
    """
    Signal handler for Relationship delete.
    Currently a no-op as we use direct queries without caching.
    """
    pass


def process_relationship_m2m_changed(
    sender, instance, action, reverse, model, pk_set, **kwargs
):
    """
    Signal handler for Relationship M2M (source/target annotations) changes.
    Currently a no-op as we use direct queries without caching.
    """
    pass
