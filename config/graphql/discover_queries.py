"""GraphQL query mixin for the Discover cross-content search view.

These resolvers back the unified Discover search bar
(``frontend/src/views/DiscoverSearchResults.tsx``). Unlike the
``*ForMention`` autocomplete resolvers in ``search_queries.py`` — which are
permission-tuned for @mention semantics and text-only — every Discover
resolver here is **hybrid**: it fuses a text arm (case-insensitive substring +
PostgreSQL full-text search) with a semantic arm (pgvector cosine similarity
over the same embeddings the rest of the platform already generates), ranked
together with Reciprocal Rank Fusion (RRF).

Design notes:
- Each resolver returns a plain ``graphene.List`` of the relevant
  ``DjangoObjectType`` (not a Relay connection) so results can be ranked by
  relevance rather than by a single ORDER BY column. This mirrors the existing
  ``semantic_search`` resolver's shape.
- Permission filtering is always done through ``BaseService.filter_visible``
  *before* either arm runs, so both the text and semantic candidate sets are
  already scoped to what the user may read. The final fetch re-filters through
  the same visible queryset, so a stale/!visible id can never leak.
- The semantic arm degrades gracefully: if no default embedder is configured,
  the query string cannot be embedded, or the content has no embeddings yet,
  the arm simply contributes nothing and the text arm still returns results.
"""

import logging
from typing import Any, Optional

import graphene
from django.contrib.postgres.search import SearchQuery
from django.db.models import Q, QuerySet
from django.db.models.functions import Left

from config.graphql.graphene_types import (
    AnnotationType,
    ConversationType,
    CorpusType,
    DocumentType,
    NoteType,
)
from config.graphql.ratelimits import get_user_tier_rate, graphql_ratelimit_dynamic
from opencontractserver.annotations.models import Annotation, Note
from opencontractserver.constants.annotations import SEMANTIC_SEARCH_MAX_RESULTS
from opencontractserver.constants.search import FTS_CONFIG, RRF_K
from opencontractserver.conversations.models import (
    Conversation,
    ConversationTypeChoices,
)
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document, DocumentPath
from opencontractserver.shared.services.base import BaseService

logger = logging.getLogger(__name__)

# Default number of results per category. The frontend caps this per tab
# (preview vs. entity tab) via the ``limit`` argument.
DISCOVER_DEFAULT_LIMIT = 25

# How many candidates each arm fetches relative to the requested ``limit``
# before fusion — a small oversample so RRF has room to reorder.
DISCOVER_OVERSAMPLE = 4


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
    ordered = sorted(scores.keys(), key=lambda i: (-scores[i], i))
    return ordered[:limit]


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


def _text_ids(
    visible_qs: QuerySet, text_q: Q, order_field: str, fetch_k: int
) -> list[Any]:
    """Materialise the text arm: filter ``visible_qs`` by ``text_q``, ordered.

    ``order_field`` (e.g. ``"created"`` / ``"modified"``) is selected alongside
    ``pk`` and ordered descending. It must appear in the SELECT list because
    ``visible_to_user`` querysets are ``DISTINCT`` and PostgreSQL rejects an
    ``ORDER BY`` on a column that isn't selected under ``SELECT DISTINCT``.
    The text filters also join to-many relations (``chat_messages``, label/doc
    joins), so ``.distinct()`` collapses the resulting row duplicates.
    """
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
    vector = _query_vector(query_text, embedder_path)
    if not vector:
        return []
    try:
        results = visible_qs.search_by_embedding(  # type: ignore[attr-defined]
            vector, embedder_path, top_k=fetch_k
        )
    except Exception:  # noqa: BLE001 - semantic arm is best-effort
        logger.warning("Discover semantic arm failed; falling back to text-only.")
        return []
    return [obj.pk for obj in results]


def _order_by_ids(qs: QuerySet, ids: list[Any]) -> list[Any]:
    """Fetch ``qs`` rows for ``ids`` and return them in ``ids`` order.

    Builds the id->object map by iterating ``filter(id__in=...)`` rather than
    ``QuerySet.in_bulk`` because ``visible_to_user`` querysets apply
    ``.distinct()`` and ``in_bulk`` refuses to run on a distinct queryset.
    """
    by_id = {obj.pk: obj for obj in qs.filter(id__in=ids)}
    return [by_id[i] for i in ids if i in by_id]


def _clamp_limit(limit: Optional[int]) -> int:
    if not limit or limit < 1:
        return DISCOVER_DEFAULT_LIMIT
    return min(limit, SEMANTIC_SEARCH_MAX_RESULTS)


class DiscoverSearchQueryMixin:
    """Hybrid (text + semantic) resolvers for the Discover search view."""

    discover_annotations = graphene.List(
        AnnotationType,
        text_search=graphene.String(required=True),
        limit=graphene.Int(default_value=DISCOVER_DEFAULT_LIMIT),
        description="Hybrid (text + semantic) annotation search for Discover.",
    )
    discover_documents = graphene.List(
        DocumentType,
        text_search=graphene.String(required=True),
        limit=graphene.Int(default_value=DISCOVER_DEFAULT_LIMIT),
        description="Hybrid (text + semantic) document search for Discover.",
    )
    discover_notes = graphene.List(
        NoteType,
        text_search=graphene.String(required=True),
        limit=graphene.Int(default_value=DISCOVER_DEFAULT_LIMIT),
        description="Hybrid (text + semantic) note search for Discover.",
    )
    discover_corpuses = graphene.List(
        CorpusType,
        text_search=graphene.String(required=True),
        limit=graphene.Int(default_value=DISCOVER_DEFAULT_LIMIT),
        description=(
            "Collection search for Discover: matches corpus title/description "
            "and collections whose documents or annotations match the query."
        ),
    )
    discover_discussions = graphene.List(
        ConversationType,
        text_search=graphene.String(required=True),
        limit=graphene.Int(default_value=DISCOVER_DEFAULT_LIMIT),
        description=(
            "Hybrid (title + message body + semantic) discussion-thread search "
            "for Discover."
        ),
    )

    # ------------------------------------------------------------------ #
    # Annotations
    # ------------------------------------------------------------------ #
    @graphql_ratelimit_dynamic(get_rate=get_user_tier_rate("READ_LIGHT"))
    def resolve_discover_annotations(
        self, info, text_search, limit=DISCOVER_DEFAULT_LIMIT
    ) -> Any:
        text = (text_search or "").strip()
        if not text:
            return []
        limit = _clamp_limit(limit)
        fetch_k = limit * DISCOVER_OVERSAMPLE
        user = info.context.user

        from opencontractserver.pipeline.utils import get_default_embedder_path

        visible = BaseService.filter_visible(Annotation, user, request=info.context)
        # Substring (label + raw_text) catches prefixes/fragments; search_vector
        # adds stemmed full-text matching. See resolve_search_annotations_for_mention.
        text_q = (
            Q(annotation_label__text__icontains=text)
            | Q(raw_text__icontains=text)
            | Q(search_vector=SearchQuery(text, config=FTS_CONFIG))
        )
        text_ids = _text_ids(visible, text_q, "created", fetch_k)
        semantic_ids = _semantic_ids(
            visible, text, get_default_embedder_path(), fetch_k
        )
        ids = _rrf([text_ids, semantic_ids], limit)

        qs = visible.filter(id__in=ids).select_related(
            "annotation_label",
            "document",
            "document__creator",
            "corpus",
            "corpus__creator",
        )
        return _order_by_ids(qs, ids)

    # ------------------------------------------------------------------ #
    # Documents
    # ------------------------------------------------------------------ #
    @graphql_ratelimit_dynamic(get_rate=get_user_tier_rate("READ_LIGHT"))
    def resolve_discover_documents(
        self, info, text_search, limit=DISCOVER_DEFAULT_LIMIT
    ) -> Any:
        text = (text_search or "").strip()
        if not text:
            return []
        limit = _clamp_limit(limit)
        fetch_k = limit * DISCOVER_OVERSAMPLE
        user = info.context.user

        from opencontractserver.pipeline.utils import get_default_embedder_path

        visible = BaseService.filter_visible(Document, user, request=info.context)
        text_q = Q(title__icontains=text) | Q(description__icontains=text)
        text_ids = _text_ids(visible, text_q, "modified", fetch_k)
        semantic_ids = _semantic_ids(
            visible, text, get_default_embedder_path(), fetch_k
        )
        ids = _rrf([text_ids, semantic_ids], limit)

        qs = visible.filter(id__in=ids).select_related("creator")
        return _order_by_ids(qs, ids)

    # ------------------------------------------------------------------ #
    # Notes
    # ------------------------------------------------------------------ #
    @graphql_ratelimit_dynamic(get_rate=get_user_tier_rate("READ_LIGHT"))
    def resolve_discover_notes(
        self, info, text_search, limit=DISCOVER_DEFAULT_LIMIT
    ) -> Any:
        text = (text_search or "").strip()
        if not text:
            return []
        limit = _clamp_limit(limit)
        fetch_k = limit * DISCOVER_OVERSAMPLE
        user = info.context.user

        from opencontractserver.pipeline.utils import get_default_embedder_path

        visible = BaseService.filter_visible(Note, user, request=info.context)
        # Note now has a trigger-maintained search_vector (migration 0076), so
        # full-text (stemmed) matching joins the substring fallback.
        text_q = (
            Q(title__icontains=text)
            | Q(content__icontains=text)
            | Q(search_vector=SearchQuery(text, config=FTS_CONFIG))
        )
        text_ids = _text_ids(visible, text_q, "modified", fetch_k)
        semantic_ids = _semantic_ids(
            visible, text, get_default_embedder_path(), fetch_k
        )
        ids = _rrf([text_ids, semantic_ids], limit)

        qs = (
            visible.filter(id__in=ids)
            .select_related("document", "document__creator", "corpus", "creator")
            .annotate(content_preview=Left("content", 400))
        )
        return _order_by_ids(qs, ids)

    # ------------------------------------------------------------------ #
    # Collections (corpuses)
    # ------------------------------------------------------------------ #
    @graphql_ratelimit_dynamic(get_rate=get_user_tier_rate("READ_LIGHT"))
    def resolve_discover_corpuses(
        self, info, text_search, limit=DISCOVER_DEFAULT_LIMIT
    ) -> Any:
        text = (text_search or "").strip()
        if not text:
            return []
        limit = _clamp_limit(limit)
        fetch_k = limit * DISCOVER_OVERSAMPLE
        user = info.context.user

        visible = BaseService.filter_visible(Corpus, user, request=info.context)

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
            .values_list("id", flat=True)[: fetch_k * 4]
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
            .values_list("corpus_id", flat=True)[: fetch_k * 4]
        )
        content_corpus_ids = {
            cid
            for cid in list(corpus_ids_from_docs) + list(corpus_ids_from_annots)
            if cid is not None
        }
        content_ids = _text_ids(
            visible, Q(id__in=content_corpus_ids), "modified", fetch_k
        )

        ids = _rrf([meta_ids, content_ids], limit)
        qs = visible.filter(id__in=ids).select_related("creator")
        return _order_by_ids(qs, ids)

    # ------------------------------------------------------------------ #
    # Discussions (threads)
    # ------------------------------------------------------------------ #
    @graphql_ratelimit_dynamic(get_rate=get_user_tier_rate("READ_LIGHT"))
    def resolve_discover_discussions(
        self, info, text_search, limit=DISCOVER_DEFAULT_LIMIT
    ) -> Any:
        text = (text_search or "").strip()
        if not text:
            return []
        limit = _clamp_limit(limit)
        fetch_k = limit * DISCOVER_OVERSAMPLE
        user = info.context.user

        from opencontractserver.pipeline.utils import get_default_embedder_path

        # Discover "Discussions" == collaborative THREADs (never personal CHATs).
        visible = BaseService.filter_visible(
            Conversation, user, request=info.context
        ).filter(conversation_type=ConversationTypeChoices.THREAD)

        # Text arm now covers message *bodies*, not just the thread title — a
        # thread titled "Q3 sync" whose messages discuss "indemnification" is
        # now findable.
        text_q = Q(title__icontains=text) | Q(chat_messages__content__icontains=text)
        text_ids = _text_ids(visible, text_q, "created", fetch_k)
        semantic_ids = _semantic_ids(
            visible, text, get_default_embedder_path(), fetch_k
        )
        ids = _rrf([text_ids, semantic_ids], limit)

        qs = visible.filter(id__in=ids).select_related(
            "creator", "chat_with_corpus", "chat_with_corpus__creator"
        )
        return _order_by_ids(qs, ids)
