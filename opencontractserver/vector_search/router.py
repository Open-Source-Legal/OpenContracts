"""
Backend selection and queryset integration for pluggable vector search.

``VectorSearchViaEmbeddingMixin.search_by_embedding`` (the single pgvector
similarity call site) consults this module first. When
``settings.VECTOR_SEARCH_BACKEND == "object_storage"`` the similarity ranking
is served from the object-storage engine and the resulting candidate ids are
re-filtered through the *caller's own queryset* — so every permission /
visibility / corpus-scoping rule already applied to that queryset (e.g. by
``CoreAnnotationVectorStore._build_base_queryset``) is preserved verbatim.

Any engine failure, or a namespace that has never been indexed, falls back to
the pgvector path — flipping the flag on can never make search *worse* than
pgvector, only faster/cheaper at scale.
"""

from __future__ import annotations

import hashlib
import logging
import re
from typing import Any

from django.conf import settings

from opencontractserver.constants.search import (
    EMBEDDABLE_PARENT_KINDS,
    OBJECT_INDEX_FILTER_OVERSAMPLE,
    OBJECT_INDEX_MAX_FETCH_CANDIDATES,
    VECTOR_SEARCH_BACKEND_OBJECT_STORAGE,
    VECTOR_SEARCH_BACKEND_PGVECTOR,
)

from .engine import ObjectStorageVectorEngine
from .object_store import DjangoStorageObjectStore

logger = logging.getLogger(__name__)

# Maps Django model_name -> namespace parent-kind segment, derived from the
# shared EMBEDDABLE_PARENT_KINDS taxonomy (single source of truth with the
# write-path map in opencontractserver/tasks/vector_index_tasks.py). Only
# models that can own Embedding rows (Embedding's parent FKs) are searchable.
PARENT_KIND_BY_MODEL_NAME: dict[str, str] = {
    model_name: kind for model_name, (_fk_attr, kind) in EMBEDDABLE_PARENT_KINDS.items()
}

_default_engine: ObjectStorageVectorEngine | None = None


def get_vector_search_backend() -> str:
    return getattr(settings, "VECTOR_SEARCH_BACKEND", VECTOR_SEARCH_BACKEND_PGVECTOR)


def object_storage_backend_enabled() -> bool:
    return get_vector_search_backend() == VECTOR_SEARCH_BACKEND_OBJECT_STORAGE


def get_default_engine() -> ObjectStorageVectorEngine:
    """
    Process-wide engine over the default Django storage (lazy proxy, so test
    ``override_settings(STORAGES=...)`` is honoured). Shared so that the
    artifact LRU cache survives across requests.

    Deliberately unlocked lazy init: a racing double-construction just makes
    one engine's (empty) LRU cache unreachable — the engine holds no other
    state. Revisit if the engine ever grows stateful fields.
    """
    global _default_engine
    if _default_engine is None:
        _default_engine = ObjectStorageVectorEngine(DjangoStorageObjectStore())
    return _default_engine


def reset_default_engine() -> None:
    """Drop the cached engine (tests switching storage locations)."""
    global _default_engine
    _default_engine = None


def build_namespace(parent_kind: str, embedder_path: str, dimension: int) -> str:
    """
    One namespace per (parent kind, embedder, dimension) — mirroring the
    filters the pgvector path applies (embedder_path + vector_<dim> column).
    The embedder slug is suffixed with a short digest so distinct embedder
    paths can never collide after sanitisation.
    """
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", embedder_path).strip("-").lower()[:80]
    digest = hashlib.md5(
        embedder_path.encode("utf-8"), usedforsecurity=False
    ).hexdigest()[:8]
    return f"{parent_kind}/{slug}-{digest}/{dimension}"


def namespace_for_queryset(queryset, embedder_path: str, dimension: int) -> str | None:
    parent_kind = PARENT_KIND_BY_MODEL_NAME.get(queryset.model._meta.model_name)
    if parent_kind is None:
        return None
    return build_namespace(parent_kind, embedder_path, dimension)


def search_via_object_index(
    queryset,
    query_vector: list[float],
    embedder_path: str,
    top_k: int,
) -> list[Any] | None:
    """
    Serve ``search_by_embedding`` from the object-storage index.

    Returns a list of model instances annotated with ``similarity_score``
    (same contract as the pgvector path), or ``None`` to signal the caller to
    fall back to pgvector (unsupported model, unindexed namespace, or any
    engine error).

    Because permission filtering happens *after* ANN retrieval here (post-ANN
    filtering), the engine is asked for ``top_k * OBJECT_INDEX_FILTER_OVERSAMPLE``
    candidates so heavily-filtered querysets still fill ``top_k`` results —
    and if even that is not enough (see the shortfall rule below), the caller
    falls back to pgvector rather than under-filling.
    """
    namespace = namespace_for_queryset(queryset, embedder_path, len(query_vector))
    if namespace is None:
        return None
    try:
        engine = get_default_engine()
        # Capped independent of caller top_k: bounds the in-memory ranking
        # and the pk__in re-filter. A cap-truncated candidate set that can't
        # fill top_k takes the shortfall fallback below.
        fetch_n = min(
            top_k * OBJECT_INDEX_FILTER_OVERSAMPLE,
            max(top_k, OBJECT_INDEX_MAX_FETCH_CANDIDATES),
        )
        hits = engine.search(namespace, query_vector, fetch_n)
    except Exception:
        logger.exception(
            "Object-storage vector search failed for namespace %s; "
            "falling back to pgvector.",
            namespace,
        )
        return None
    if hits is None:
        logger.info(
            "Namespace %s has no object-storage index yet; falling back to "
            "pgvector. Run `manage.py rebuild_object_vector_index` to build it.",
            namespace,
        )
        return None

    # Re-filter candidates through the caller's queryset: this re-applies all
    # visibility/corpus scoping AND drops ids whose rows were deleted after
    # indexing (the index tolerates staleness; Postgres is ground truth).
    candidate_ids = [doc_id for doc_id, _ in hits]
    instances_by_id = {obj.pk: obj for obj in queryset.filter(pk__in=candidate_ids)}
    results: list[Any] = []
    for doc_id, similarity in hits:
        instance = instances_by_id.get(doc_id)
        if instance is None:
            continue
        instance.similarity_score = max(0.0, min(1.0, similarity))
        results.append(instance)
        if len(results) >= top_k:
            break

    # Shortfall rule: if filtering consumed a TRUNCATED candidate set without
    # filling top_k, deeper matches may exist beyond fetch_n — fall back to
    # pgvector, whose SQL filter+limit has no such recall cliff. If the
    # engine returned fewer than fetch_n hits it exhausted the namespace, so
    # a short result list is genuinely complete and is returned as-is. This
    # keeps "enabling the backend never returns worse results than pgvector"
    # true even for heavily-filtered querysets. Accepted false positive: a
    # namespace holding EXACTLY fetch_n matching vectors is indistinguishable
    # from a truncated set, so that boundary pays one unnecessary (harmless)
    # pgvector fallback.
    if len(results) < top_k and len(hits) >= fetch_n:
        logger.info(
            "Object-storage candidates for namespace %s were exhausted by "
            "filtering (%d/%d after re-filter); falling back to pgvector.",
            namespace,
            len(results),
            top_k,
        )
        return None
    return results
