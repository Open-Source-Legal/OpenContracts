"""
Celery tasks maintaining the object-storage vector index
(``VECTOR_SEARCH_BACKEND=object_storage``).

Writes are fire-and-forget WAL appends fanned out from
``Embedding.objects.store_embedding`` (see ``vector_search/hooks.py``);
compaction folds the WAL into a new indexed generation and is serialised
per-namespace with a cache lock.
"""

import logging

from celery import shared_task
from django.core.cache import cache

from opencontractserver.constants.search import (
    DIM_TO_FIELD_MAP,
    OBJECT_INDEX_COMPACT_LOCK_TIMEOUT_SECONDS,
    OBJECT_INDEX_COMPACT_MIN_WAL_FILES,
)
from opencontractserver.vector_search.router import (
    build_namespace,
    get_default_engine,
    object_storage_backend_enabled,
)

logger = logging.getLogger(__name__)

# Mirrors Embedding's parent FK columns -> namespace parent-kind segment.
PARENT_FK_TO_KIND = {
    "document_id": "document",
    "annotation_id": "annotation",
    "note_id": "note",
    "conversation_id": "conversation",
    "message_id": "message",
    "relationship_id": "relationship",
}


def _parent_ref(embedding) -> tuple[str, int] | None:
    """Return (parent_kind, parent_pk) for the single populated parent FK."""
    for fk_attr, kind in PARENT_FK_TO_KIND.items():
        parent_pk = getattr(embedding, fk_attr)
        if parent_pk:
            return kind, parent_pk
    return None


@shared_task
def sync_embedding_to_object_index(embedding_id: int, dimension: int) -> str:
    """
    Upsert one stored embedding into its object-storage namespace, then
    trigger compaction when the WAL tail has grown past the threshold.
    """
    if not object_storage_backend_enabled():
        return "skipped: backend disabled"
    from opencontractserver.annotations.models import Embedding

    embedding = Embedding.objects.filter(pk=embedding_id).first()
    if embedding is None:
        # Row deleted between commit and task execution — nothing to sync;
        # a stale index entry (if any) is dropped at query time by the ORM
        # re-filter and removed for good on the next rebuild.
        return f"skipped: embedding {embedding_id} no longer exists"

    vector = getattr(embedding, DIM_TO_FIELD_MAP[dimension], None)
    if vector is None:
        return f"skipped: embedding {embedding_id} has no vector_{dimension}"
    parent = _parent_ref(embedding)
    if parent is None:
        return f"skipped: embedding {embedding_id} has no parent reference"

    parent_kind, parent_pk = parent
    namespace = build_namespace(parent_kind, embedding.embedder_path, dimension)
    engine = get_default_engine()
    engine.upsert(namespace, [(parent_pk, list(vector))])

    if engine.wal_tail_count(namespace) >= OBJECT_INDEX_COMPACT_MIN_WAL_FILES:
        # Pending-marker gate: during a sustained write burst every write past
        # the threshold would otherwise enqueue its own (no-op) compaction
        # task. Only the writer that claims the marker enqueues; the marker is
        # cleared when compaction finishes (or by TTL if the queued task is
        # lost), letting the next threshold crossing re-trigger.
        if cache.add(
            _compact_pending_key(namespace),
            "1",
            timeout=OBJECT_INDEX_COMPACT_LOCK_TIMEOUT_SECONDS,
        ):
            compact_object_vector_namespace.si(namespace).apply_async()
    return f"upserted {parent_kind} {parent_pk} into {namespace}"


def _compact_pending_key(namespace: str) -> str:
    return f"object-vector-index-compact-pending:{namespace}"


@shared_task
def compact_object_vector_namespace(namespace: str) -> str:
    """
    Fold the namespace's WAL tail into a new segment generation. A cache lock
    guarantees a single compactor per namespace; contenders skip (the next
    threshold crossing re-triggers).
    """
    lock_key = f"object-vector-index-compact:{namespace}"
    if not cache.add(lock_key, "1", timeout=OBJECT_INDEX_COMPACT_LOCK_TIMEOUT_SECONDS):
        return f"skipped: compaction already running for {namespace}"
    try:
        stats = get_default_engine().compact(namespace)
        logger.info("Compacted object vector namespace: %s", stats)
        return f"compacted {namespace}: {stats}"
    finally:
        cache.delete(lock_key)
        cache.delete(_compact_pending_key(namespace))
