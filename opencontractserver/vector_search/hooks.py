"""
Write-path fan-out: mirror every stored embedding into the object-storage
index when the backend is enabled.

``Embedding.objects.store_embedding`` is the single chokepoint through which
ALL embedding writes flow (Celery embedding tasks, ``HasEmbeddingMixin
.add_embedding``, backfill commands), so hooking here covers every producer.

The sync is queued on transaction commit so the Celery task can always load
the committed ``Embedding`` row, and it is fire-and-forget: an object-index
sync failure never breaks the Postgres write (pgvector data is ground truth
and the index can be rebuilt).
"""

from __future__ import annotations

import logging

from django.db import transaction

from .router import object_storage_backend_enabled

logger = logging.getLogger(__name__)


def enqueue_embedding_index_sync(embedding, dimension: int) -> None:
    """
    Queue the object-index upsert for ``embedding`` after the surrounding
    transaction commits. No-op when the object-storage backend is disabled.
    """
    if not object_storage_backend_enabled():
        return
    if embedding is None or embedding.pk is None:
        return
    embedding_pk = embedding.pk
    # Late import: opencontractserver.tasks imports models which import
    # shared.Managers which imports this module.
    from opencontractserver.tasks.vector_index_tasks import (
        sync_embedding_to_object_index,
    )

    transaction.on_commit(
        lambda: sync_embedding_to_object_index.si(embedding_pk, dimension).apply_async()
    )
