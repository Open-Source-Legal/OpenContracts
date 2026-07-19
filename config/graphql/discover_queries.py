"""Generated strawberry GraphQL module (graphene migration).

Shape-generated from the graphene schema; stub functions marked PORT(...)
carry the ported business logic. See config/graphql_new/manifest.json.
"""

# mypy: disable-error-code="name-defined, valid-type, arg-type"
#   Code-generation artifacts of the strawberry schema bindings that
#   mypy's static pass cannot resolve, NOT real typing defects:
#     name-defined / valid-type — ``Annotated["XType", strawberry.lazy(...)]``
#       forward-reference strings + the runtime-generated ``*Connection``
#       types (``make_connection_types``).
#     arg-type — resolvers construct result types with ``to_global_id()``
#       (``str``) for ``strawberry.ID`` fields and return Django MODEL
#       instances where the field annotation names the strawberry type
#       (the graphene-django resolver contract). Both are correct at
#       runtime. Hand-written config/graphql/core/* stays fully checked.
# flake8: noqa: E501, F821 — generated strawberry schema module.
# E501: long GraphQL field/argument ``description=`` strings and the
# single-line generated resolver signatures (black cannot split string
# literals). F821: ``Annotated["XType", strawberry.lazy(...)]`` /
# ``cast("QuerySet", ...)`` forward-reference STRINGS that pyflakes
# resolves as names — the whole point of strawberry.lazy is to avoid the
# import (which would then be F401). Both are code-generation artifacts,
# not defects; hand-written modules (config/graphql/core/*, security.py,
# testing.py, filters.py, …) stay fully linted.

from __future__ import annotations

import functools
import logging
from typing import Annotated, Any

import strawberry
from django.contrib.postgres.search import SearchQuery
from django.db.models import Q, QuerySet
from django.db.models.functions import Left

from config.graphql._util import strip_unset
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


def _default_embedder_path() -> str | None:
    """Resolve the install-wide default embedder path.

    The import is deferred to module-call time to avoid a circular import at
    load (``pipeline.utils`` pulls in models that import this module's
    siblings). Centralising it here removes the five identical deferred imports
    that previously lived inside each resolver body.
    """
    from opencontractserver.pipeline.utils import get_default_embedder_path

    return get_default_embedder_path()


def _normalise_text_search(text_search: str | None) -> str | None:
    """Strip and validate a Discover search string before any search arm runs."""
    text = (text_search or "").strip()
    if not text or len(text) > DISCOVER_TEXT_SEARCH_MAX_LENGTH:
        return None
    return text


class _UncacheableQueryVector(Exception):
    """Raised inside the LRU wrapper so failed embeddings are not cached."""


def _query_vector(query_text: str, embedder_path: str | None) -> list | None:
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
def _cached_query_vector(query_text: str, embedder_path: str) -> list | None:
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
    embedder_path: str | None,
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


def _clamp_limit(limit: int | None) -> int:
    if not limit or limit < 1:
        return DISCOVER_DEFAULT_LIMIT
    return min(limit, SEMANTIC_SEARCH_MAX_RESULTS)


@graphql_ratelimit_dynamic(get_rate=get_user_tier_rate("READ_LIGHT"))
def _resolve_Query_discover_annotations(
    root, info, text_search, limit=DISCOVER_DEFAULT_LIMIT
):
    """Port of DiscoverSearchQueryMixin.resolve_discover_annotations."""
    text = _normalise_text_search(text_search)
    if not text:
        return []
    limit = _clamp_limit(limit)
    fetch_k = limit * DISCOVER_OVERSAMPLE
    user = info.context.user

    visible = BaseService.filter_visible(Annotation, user, request=info.context)
    # Substring (label + raw_text) catches prefixes/fragments; search_vector
    # adds stemmed full-text matching. See resolve_search_annotations_for_mention.
    text_q = (
        Q(annotation_label__text__icontains=text)
        | Q(raw_text__icontains=text)
        | Q(search_vector=SearchQuery(text, config=FTS_CONFIG))
    )
    text_ids = _text_ids(visible, text_q, "created", fetch_k)
    semantic_ids = _semantic_ids(visible, text, _default_embedder_path(), fetch_k)
    ids = _rrf([text_ids, semantic_ids], limit)

    # ``_order_by_ids`` applies the ``id__in=ids`` filter itself.
    qs = visible.select_related(
        "annotation_label",
        "document",
        "document__creator",
        "corpus",
        "corpus__creator",
    )
    return _order_by_ids(qs, ids)


def q_discover_annotations(
    info: strawberry.Info,
    text_search: Annotated[
        str, strawberry.argument(name="textSearch")
    ] = strawberry.UNSET,
    limit: Annotated[int | None, strawberry.argument(name="limit")] = 25,
) -> None | (
    list[
        None
        | (
            Annotated[
                AnnotationType, strawberry.lazy("config.graphql.annotation_types")
            ]
        )
    ]
):
    kwargs = strip_unset({"text_search": text_search, "limit": limit})
    return _resolve_Query_discover_annotations(None, info, **kwargs)


@graphql_ratelimit_dynamic(get_rate=get_user_tier_rate("READ_LIGHT"))
def _resolve_Query_discover_documents(
    root, info, text_search, limit=DISCOVER_DEFAULT_LIMIT
):
    """Port of DiscoverSearchQueryMixin.resolve_discover_documents."""
    text = _normalise_text_search(text_search)
    if not text:
        return []
    limit = _clamp_limit(limit)
    fetch_k = limit * DISCOVER_OVERSAMPLE
    user = info.context.user

    visible = BaseService.filter_visible(Document, user, request=info.context)
    text_q = Q(title__icontains=text) | Q(description__icontains=text)
    text_ids = _text_ids(visible, text_q, "modified", fetch_k)
    semantic_ids = _semantic_ids(visible, text, _default_embedder_path(), fetch_k)
    ids = _rrf([text_ids, semantic_ids], limit)

    # ``_order_by_ids`` applies the ``id__in=ids`` filter itself.
    qs = visible.select_related("creator")
    return _order_by_ids(qs, ids)


def q_discover_documents(
    info: strawberry.Info,
    text_search: Annotated[
        str, strawberry.argument(name="textSearch")
    ] = strawberry.UNSET,
    limit: Annotated[int | None, strawberry.argument(name="limit")] = 25,
) -> None | (
    list[
        None
        | (Annotated[DocumentType, strawberry.lazy("config.graphql.document_types")])
    ]
):
    kwargs = strip_unset({"text_search": text_search, "limit": limit})
    return _resolve_Query_discover_documents(None, info, **kwargs)


@graphql_ratelimit_dynamic(get_rate=get_user_tier_rate("READ_LIGHT"))
def _resolve_Query_discover_notes(
    root, info, text_search, limit=DISCOVER_DEFAULT_LIMIT
):
    """Port of DiscoverSearchQueryMixin.resolve_discover_notes."""
    text = _normalise_text_search(text_search)
    if not text:
        return []
    limit = _clamp_limit(limit)
    fetch_k = limit * DISCOVER_OVERSAMPLE
    user = info.context.user

    visible = BaseService.filter_visible(Note, user, request=info.context)
    # Note now has a trigger-maintained search_vector (migration 0076), so
    # full-text (stemmed) matching joins the substring fallback.
    text_q = (
        Q(title__icontains=text)
        | Q(content__icontains=text)
        | Q(search_vector=SearchQuery(text, config=FTS_CONFIG))
    )
    text_ids = _text_ids(visible, text_q, "modified", fetch_k)
    semantic_ids = _semantic_ids(visible, text, _default_embedder_path(), fetch_k)
    ids = _rrf([text_ids, semantic_ids], limit)

    # ``_order_by_ids`` applies the ``id__in=ids`` filter itself.
    qs = visible.select_related(
        "document", "document__creator", "corpus", "creator"
    ).annotate(content_preview=Left("content", 400))
    return _order_by_ids(qs, ids)


def q_discover_notes(
    info: strawberry.Info,
    text_search: Annotated[
        str, strawberry.argument(name="textSearch")
    ] = strawberry.UNSET,
    limit: Annotated[int | None, strawberry.argument(name="limit")] = 25,
) -> None | (
    list[
        None | (Annotated[NoteType, strawberry.lazy("config.graphql.annotation_types")])
    ]
):
    kwargs = strip_unset({"text_search": text_search, "limit": limit})
    return _resolve_Query_discover_notes(None, info, **kwargs)


@graphql_ratelimit_dynamic(get_rate=get_user_tier_rate("READ_LIGHT"))
def _resolve_Query_discover_corpuses(
    root, info, text_search, limit=DISCOVER_DEFAULT_LIMIT
):
    """Port of DiscoverSearchQueryMixin.resolve_discover_corpuses."""
    text = _normalise_text_search(text_search)
    if not text:
        return []
    limit = _clamp_limit(limit)
    fetch_k = limit * DISCOVER_OVERSAMPLE
    user = info.context.user

    visible = BaseService.filter_visible(Corpus, user, request=info.context)

    # NOTE: this resolver is intentionally heavier than the others (≈4–5
    # queries vs 2). A corpus is discoverable not just by its own
    # title/description (Arm 1) but by the documents and annotations it
    # contains (Arm 2), and each contained model carries its own
    # permission scope — hence the separate ``filter_visible`` calls for
    # Corpus, Document and Annotation plus the DocumentPath join. The
    # annotation arm in particular surfaces collections that the document
    # arm would miss (a query matching only annotation text), which is the
    # whole point of "search inside collections", so its cost is deliberate.

    # Arm 1: corpus metadata (title/description) match.
    meta_q = Q(title__icontains=text) | Q(description__icontains=text)
    meta_ids = _text_ids(visible, meta_q, "modified", fetch_k)

    # Arm 2: collections whose *contents* match — documents (title/desc) or
    # annotations (raw_text / FTS) the user can read. Corpus has no
    # embeddings of its own, so "semantic" coverage for a collection comes
    # transitively from its annotations matching the query.
    # ``.order_by()`` clears each model's default ``Meta.ordering`` before
    # the ``DISTINCT`` ``values_list`` so PostgreSQL doesn't reject an
    # ORDER BY column that isn't in the (distinct) select list.
    matching_doc_ids = (
        BaseService.filter_visible(Document, user, request=info.context)
        .filter(Q(title__icontains=text) | Q(description__icontains=text))
        .order_by()
        .values_list("id", flat=True)[: fetch_k * DISCOVER_CORPUS_CONTENT_OVERSAMPLE]
    )
    corpus_ids_from_docs = DocumentPath.objects.filter(
        document_id__in=list(matching_doc_ids),
        is_current=True,
        is_deleted=False,
    ).values_list("corpus_id", flat=True)
    corpus_ids_from_annots = (
        BaseService.filter_visible(Annotation, user, request=info.context)
        .filter(
            Q(raw_text__icontains=text)
            | Q(search_vector=SearchQuery(text, config=FTS_CONFIG))
        )
        .order_by()
        .values_list("corpus_id", flat=True)[
            : fetch_k * DISCOVER_CORPUS_CONTENT_OVERSAMPLE
        ]
    )
    # Collapse the two content-match id streams to a distinct corpus set.
    content_corpus_ids = {
        cid
        for cid in list(corpus_ids_from_docs) + list(corpus_ids_from_annots)
        if cid is not None
    }
    content_ids = _text_ids(visible, Q(id__in=content_corpus_ids), "modified", fetch_k)

    ids = _rrf([meta_ids, content_ids], limit)
    # ``_order_by_ids`` applies the ``id__in=ids`` filter itself.
    qs = visible.select_related("creator")
    return _order_by_ids(qs, ids)


def q_discover_corpuses(
    info: strawberry.Info,
    text_search: Annotated[
        str, strawberry.argument(name="textSearch")
    ] = strawberry.UNSET,
    limit: Annotated[int | None, strawberry.argument(name="limit")] = 25,
) -> None | (
    list[None | (Annotated[CorpusType, strawberry.lazy("config.graphql.corpus_types")])]
):
    kwargs = strip_unset({"text_search": text_search, "limit": limit})
    return _resolve_Query_discover_corpuses(None, info, **kwargs)


@graphql_ratelimit_dynamic(get_rate=get_user_tier_rate("READ_LIGHT"))
def _resolve_Query_discover_discussions(
    root, info, text_search, limit=DISCOVER_DEFAULT_LIMIT
):
    """Port of DiscoverSearchQueryMixin.resolve_discover_discussions."""
    text = _normalise_text_search(text_search)
    if not text:
        return []
    limit = _clamp_limit(limit)
    fetch_k = limit * DISCOVER_OVERSAMPLE
    user = info.context.user

    # Discover "Discussions" == collaborative THREADs (never personal CHATs).
    visible = BaseService.filter_visible(
        Conversation, user, request=info.context
    ).filter(
        conversation_type=ConversationTypeChoices.THREAD,
        deleted_at__isnull=True,
    )

    text_q = Q(title__icontains=text) | Q(chat_messages__content__icontains=text)
    text_ids = _text_ids(visible, text_q, "created", fetch_k)
    semantic_ids = _semantic_ids(visible, text, _default_embedder_path(), fetch_k)
    ids = _rrf([text_ids, semantic_ids], limit)

    # ``_order_by_ids`` applies the ``id__in=ids`` filter itself.
    qs = visible.select_related(
        "creator",
        "chat_with_corpus",
        "chat_with_corpus__creator",
        "chat_with_document",
        "locked_by",
        "pinned_by",
    )
    return _order_by_ids(qs, ids)


def q_discover_discussions(
    info: strawberry.Info,
    text_search: Annotated[
        str, strawberry.argument(name="textSearch")
    ] = strawberry.UNSET,
    limit: Annotated[int | None, strawberry.argument(name="limit")] = 25,
) -> None | (
    list[
        None
        | (
            Annotated[
                ConversationType, strawberry.lazy("config.graphql.conversation_types")
            ]
        )
    ]
):
    kwargs = strip_unset({"text_search": text_search, "limit": limit})
    return _resolve_Query_discover_discussions(None, info, **kwargs)


QUERY_FIELDS = {
    "discover_annotations": strawberry.field(
        resolver=q_discover_annotations,
        name="discoverAnnotations",
        description="Hybrid (text + semantic) annotation search for Discover.",
    ),
    "discover_documents": strawberry.field(
        resolver=q_discover_documents,
        name="discoverDocuments",
        description="Hybrid (text + semantic) document search for Discover.",
    ),
    "discover_notes": strawberry.field(
        resolver=q_discover_notes,
        name="discoverNotes",
        description="Hybrid (text + semantic) note search for Discover.",
    ),
    "discover_corpuses": strawberry.field(
        resolver=q_discover_corpuses,
        name="discoverCorpuses",
        description="Collection search for Discover: matches corpus title/description and collections whose documents or annotations match the query.",
    ),
    "discover_discussions": strawberry.field(
        resolver=q_discover_discussions,
        name="discoverDiscussions",
        description="Hybrid (title + message body + semantic) discussion-thread search for Discover.",
    ),
}
