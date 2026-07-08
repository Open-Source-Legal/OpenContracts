"""Generated strawberry GraphQL module (graphene migration).

Shape-generated from the graphene schema; stub functions marked PORT(...)
carry the ported business logic. See config/graphql_new/manifest.json.
"""
from __future__ import annotations

import datetime
import decimal
import uuid
from typing import Annotated, Any, Optional

import strawberry

from config.graphql.core import permissions as core_permissions
from config.graphql.core.filtering import filterset_factory, setup_filterset
from config.graphql.core.mutations import drf_deletion, drf_mutation
from config.graphql.core.relay import (
    Node,
    get_node_from_global_id,
    make_connection_types,
    register_type,
    resolve_django_connection,
    resolve_django_list,
)
from config.graphql.core.scalars import BigInt, GenericScalar, JSONString
from config.graphql._util import coerce_enum, coerce_str, strip_unset
from config.graphql import enums

import functools
import logging

from django.contrib.postgres.search import SearchQuery
from django.db.models import Q, QuerySet
from django.db.models.functions import Left

from config.graphql.ratelimits import get_user_tier_rate, graphql_ratelimit_dynamic
from opencontractserver.annotations.models import Annotation, Note
from opencontractserver.constants.annotations import SEMANTIC_SEARCH_MAX_RESULTS
from opencontractserver.constants.search import (
    DISCOVER_CORPUS_CONTENT_OVERSAMPLE,
    DISCOVER_DEFAULT_LIMIT,
    DISCOVER_OVERSAMPLE,
    DISCOVER_QUERY_VECTOR_CACHE_SIZE,
    DISCOVER_TEXT_SEARCH_MAX_LENGTH,
    FTS_CONFIG,
    RRF_K,
)
from opencontractserver.conversations.models import (
    Conversation,
    ConversationTypeChoices,
)
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document, DocumentPath
from opencontractserver.shared.services.base import BaseService

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Fusion / ranking helpers
# --------------------------------------------------------------------------- #
def _dedupe(seq: list[Any]) -> list[Any]:
    """Return ``seq`` with duplicates removed, preserving first-seen order.

    Used instead of ``QuerySet.distinct()`` for the text arm because the text
    filters join to-many relations (e.g. ``chat_messages``), and ``DISTINCT``
    combined with an ``ORDER BY`` on a non-selected column is rejected by
    PostgreSQL. Deduping the materialised id list in Python sidesteps that.
    """
    seen: set[Any] = set()
    out: list[Any] = []
    for item in seq:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _rrf(rankings: list[list[Any]], limit: int) -> list[Any]:
    """Reciprocal Rank Fusion over several ranked id lists.

    Each input list is one arm's results in descending relevance order. The
    fused score for an id is ``sum(1 / (RRF_K + rank))`` across the arms it
    appears in, so an id ranked highly by multiple arms beats one ranked highly
    by a single arm. Ties break on the id for determinism.
    """
    scores: dict[Any, float] = {}
    for ids in rankings:
        for rank, _id in enumerate(ids):
            scores[_id] = scores.get(_id, 0.0) + 1.0 / (RRF_K + rank + 1)
    # Tie-break on ``str(i)`` rather than ``i``: ``(-float, value)`` tuples are
    # only comparable when every ``value`` is mutually comparable. Integer PKs
    # work today, but a model migrating to UUID PKs would make ``uuid < uuid``
    # the only comparable path and mixing types would raise TypeError. Casting
    # to str keeps the sort total-orderable regardless of PK type.
    ordered = sorted(scores.keys(), key=lambda i: (-scores[i], str(i)))
    return ordered[:limit]


def _default_embedder_path() -> Optional[str]:
    """Resolve the install-wide default embedder path.

    The import is deferred to module-call time to avoid a circular import at
    load (``pipeline.utils`` pulls in models that import this module's
    siblings). Centralising it here removes the five identical deferred imports
    that previously lived inside each resolver body.
    """
    from opencontractserver.pipeline.utils import get_default_embedder_path

    return get_default_embedder_path()


def _normalise_text_search(text_search: Optional[str]) -> Optional[str]:
    """Strip and validate a Discover search string before any search arm runs."""
    text = (text_search or "").strip()
    if not text or len(text) > DISCOVER_TEXT_SEARCH_MAX_LENGTH:
        return None
    return text


class _UncacheableQueryVector(Exception):
    """Raised inside the LRU wrapper so failed embeddings are not cached."""


def _query_vector(query_text: str, embedder_path: Optional[str]) -> Optional[list]:
    """Embed ``query_text`` with the default embedder, or ``None`` on failure.

    ``generate_embeddings_from_text`` already swallows embedder errors and
    returns ``(None, None)``; we additionally guard against an unconfigured
    embedder path so the semantic arm is a no-op rather than an exception.
    """
    if not embedder_path:
        return None
    from opencontractserver.utils.embeddings import generate_embeddings_from_text

    _used_path, vector = generate_embeddings_from_text(
        query_text, embedder_path=embedder_path
    )
    return vector


@functools.lru_cache(maxsize=DISCOVER_QUERY_VECTOR_CACHE_SIZE)
def _cached_query_vector(query_text: str, embedder_path: str) -> Optional[list]:
    """Per-process memoised wrapper around :func:`_query_vector`.

    Discover's "All" tab fires all five category resolvers as five independent
    HTTP requests (Apollo uses a non-batching link), each of which would embed
    the *same* query string with the same default embedder. Embedding is
    deterministic for a given ``(query_text, embedder_path)``, so caching the
    result lets those requests share one embedding call instead of five.

    Caveats (acceptable for a best-effort arm): there is no TTL, so a vector
    lives until LRU-evicted — fine, because the same inputs always produce the
    same vector. Failed embeddings are deliberately not cached: callers catch
    ``_UncacheableQueryVector`` and fall back to text-only results so transient
    failures do not pin attacker-controlled query strings in worker memory.
    Tests reset the cache in ``setUp`` (``_cached_query_vector.cache_clear()``).
    """
    vector = _query_vector(query_text, embedder_path)
    if not vector:
        raise _UncacheableQueryVector
    return vector


def _text_ids(
    visible_qs: QuerySet, text_q: Q, order_field: str, fetch_k: int
) -> list[Any]:
    """Materialise the text arm: filter ``visible_qs`` by ``text_q``, ordered.

    ``order_field`` (e.g. ``"created"`` / ``"modified"``) is selected alongside
    ``pk`` and ordered descending. It must appear in the SELECT list because
    this helper applies its own ``.distinct()`` (below) and PostgreSQL rejects
    an ``ORDER BY`` on a column that isn't selected under ``SELECT DISTINCT``.
    That ``.distinct()`` is warranted because the text filters join to-many
    relations (``chat_messages``, label/doc joins) which would otherwise yield
    duplicate rows. The helper does NOT rely on the incoming ``visible_qs``
    being distinct — Annotation's predicate was de-joined in #1906 (no longer
    distinct), while Note/Document/Conversation remain distinct; either way the
    explicit ``.distinct()`` here keeps the result correct.
    """
    # Over-fetch 2× before the application-side ``_dedupe`` + ``[:fetch_k]``
    # slice. ``order_field`` is a model field (constant per pk), so the
    # ``DISTINCT (pk, order_field)`` above already collapses pk duplicates and
    # ``_dedupe`` is normally a no-op — the 2× headroom is a cheap safety margin
    # so the final list still reaches ``fetch_k`` even if a future filter shape
    # ever lets a pk slip through DISTINCT. fetch_k is already small (limit ×
    # oversample), so the extra rows are negligible.
    rows = list(
        visible_qs.filter(text_q)
        .values_list("pk", order_field)
        .distinct()
        .order_by(f"-{order_field}")[: fetch_k * 2]
    )
    return _dedupe([row[0] for row in rows])[:fetch_k]


def _semantic_ids(
    visible_qs: QuerySet,
    query_text: str,
    embedder_path: Optional[str],
    fetch_k: int,
) -> list[Any]:
    """Materialise the semantic arm via ``QuerySet.search_by_embedding``.

    ``visible_qs`` must be a queryset whose model mixes in
    ``VectorSearchViaEmbeddingMixin`` (Annotation, Note, Document,
    Conversation). Returns ``[]`` if the query can't be embedded.
    """
    if not embedder_path:
        # No embedder configured → semantic arm is a no-op. Guard here (rather
        # than relying on the cache) so we never seed the LRU with a null key.
        return []
    try:
        vector = _cached_query_vector(query_text, embedder_path)
    except _UncacheableQueryVector:
        return []
    try:
        results = visible_qs.search_by_embedding(  # type: ignore[attr-defined]
            vector, embedder_path, top_k=fetch_k
        )
    except Exception:  # noqa: BLE001 - semantic arm is best-effort
        logger.warning(
            "Discover semantic arm failed; falling back to text-only.",
            exc_info=True,
        )
        return []
    return [obj.pk for obj in results]


def _order_by_ids(qs: QuerySet, ids: list[Any]) -> list[Any]:
    """Fetch ``qs`` rows for ``ids`` and return them in ``ids`` order.

    ``_order_by_ids`` *owns* the ``id__in`` predicate — callers pass the bare
    visible queryset (already carrying ``select_related`` / ``annotate``) and
    must NOT pre-filter by ``ids`` themselves, to avoid a redundant double
    ``id__in`` clause.

    Builds the id->object map by iterating ``filter(id__in=...)`` rather than
    ``QuerySet.in_bulk`` because several ``visible_to_user`` querysets apply
    ``.distinct()`` (Note/Document/Conversation; Annotation's was de-joined in
    #1906) and ``in_bulk`` refuses to run on a distinct queryset. Iterating is
    equally correct for the non-distinct (de-joined) case.
    """
    by_id = {obj.pk: obj for obj in qs.filter(id__in=ids)}
    return [by_id[i] for i in ids if i in by_id]


def _clamp_limit(limit: Optional[int]) -> int:
    if not limit or limit < 1:
        return DISCOVER_DEFAULT_LIMIT
    return min(limit, SEMANTIC_SEARCH_MAX_RESULTS)


def _resolve_Query_discover_annotations(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/ratelimit/decorators.py:303

    Port of DiscoverSearchQueryMixin.resolve_discover_annotations
    """
    raise NotImplementedError("_resolve_Query_discover_annotations not yet ported — see manifest")


def q_discover_annotations(info: strawberry.Info, text_search: Annotated[str, strawberry.argument(name="textSearch")] = strawberry.UNSET, limit: Annotated[Optional[int], strawberry.argument(name="limit")] = 25) -> Optional[list[Optional[Annotated["AnnotationType", strawberry.lazy("config.graphql.annotation_types")]]]]:
    kwargs = strip_unset({"text_search": text_search, "limit": limit})
    return _resolve_Query_discover_annotations(None, info, **kwargs)


def _resolve_Query_discover_documents(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/ratelimit/decorators.py:339

    Port of DiscoverSearchQueryMixin.resolve_discover_documents
    """
    raise NotImplementedError("_resolve_Query_discover_documents not yet ported — see manifest")


def q_discover_documents(info: strawberry.Info, text_search: Annotated[str, strawberry.argument(name="textSearch")] = strawberry.UNSET, limit: Annotated[Optional[int], strawberry.argument(name="limit")] = 25) -> Optional[list[Optional[Annotated["DocumentType", strawberry.lazy("config.graphql.document_types")]]]]:
    kwargs = strip_unset({"text_search": text_search, "limit": limit})
    return _resolve_Query_discover_documents(None, info, **kwargs)


def _resolve_Query_discover_notes(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/ratelimit/decorators.py:363

    Port of DiscoverSearchQueryMixin.resolve_discover_notes
    """
    raise NotImplementedError("_resolve_Query_discover_notes not yet ported — see manifest")


def q_discover_notes(info: strawberry.Info, text_search: Annotated[str, strawberry.argument(name="textSearch")] = strawberry.UNSET, limit: Annotated[Optional[int], strawberry.argument(name="limit")] = 25) -> Optional[list[Optional[Annotated["NoteType", strawberry.lazy("config.graphql.annotation_types")]]]]:
    kwargs = strip_unset({"text_search": text_search, "limit": limit})
    return _resolve_Query_discover_notes(None, info, **kwargs)


def _resolve_Query_discover_corpuses(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/ratelimit/decorators.py:395

    Port of DiscoverSearchQueryMixin.resolve_discover_corpuses
    """
    raise NotImplementedError("_resolve_Query_discover_corpuses not yet ported — see manifest")


def q_discover_corpuses(info: strawberry.Info, text_search: Annotated[str, strawberry.argument(name="textSearch")] = strawberry.UNSET, limit: Annotated[Optional[int], strawberry.argument(name="limit")] = 25) -> Optional[list[Optional[Annotated["CorpusType", strawberry.lazy("config.graphql.corpus_types")]]]]:
    kwargs = strip_unset({"text_search": text_search, "limit": limit})
    return _resolve_Query_discover_corpuses(None, info, **kwargs)


def _resolve_Query_discover_discussions(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/ratelimit/decorators.py:478

    Port of DiscoverSearchQueryMixin.resolve_discover_discussions
    """
    raise NotImplementedError("_resolve_Query_discover_discussions not yet ported — see manifest")


def q_discover_discussions(info: strawberry.Info, text_search: Annotated[str, strawberry.argument(name="textSearch")] = strawberry.UNSET, limit: Annotated[Optional[int], strawberry.argument(name="limit")] = 25) -> Optional[list[Optional[Annotated["ConversationType", strawberry.lazy("config.graphql.conversation_types")]]]]:
    kwargs = strip_unset({"text_search": text_search, "limit": limit})
    return _resolve_Query_discover_discussions(None, info, **kwargs)



QUERY_FIELDS = {
    "discover_annotations": strawberry.field(resolver=q_discover_annotations, name="discoverAnnotations", description='Hybrid (text + semantic) annotation search for Discover.'),
    "discover_documents": strawberry.field(resolver=q_discover_documents, name="discoverDocuments", description='Hybrid (text + semantic) document search for Discover.'),
    "discover_notes": strawberry.field(resolver=q_discover_notes, name="discoverNotes", description='Hybrid (text + semantic) note search for Discover.'),
    "discover_corpuses": strawberry.field(resolver=q_discover_corpuses, name="discoverCorpuses", description='Collection search for Discover: matches corpus title/description and collections whose documents or annotations match the query.'),
    "discover_discussions": strawberry.field(resolver=q_discover_discussions, name="discoverDiscussions", description='Hybrid (title + message body + semantic) discussion-thread search for Discover.'),
}
