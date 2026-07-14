"""Cross-corpus retrieval over a :class:`CorpusGroup` (issue #2056).

``search_across_corpora`` lets one orchestrator agent fan a semantic query
out across every corpus in a named :class:`CorpusGroup` and synthesize a
unified answer with per-corpus citations. All access goes through
``CorpusGroupService`` (the canonical service-layer entry point):

* The group is resolved IDOR-safely — an invisible group and a missing
  group raise the identical error.
* The group's ``corpora`` M2M is resolved at *call time* and filtered to
  the corpora the calling user can READ, so membership changes apply on
  the next query and a private corpus inside a shared group is never
  searched on behalf of a user who cannot see it. The count of hidden
  members is intentionally NOT reported (it would leak their existence).

Each visible corpus is searched with its own
:class:`CoreAnnotationVectorStore` (its own ``preferred_embedder``), and
hits stay **grouped per corpus**: similarity scores from different
embedding spaces are not comparable, so no cross-corpus score merge is
attempted.

Parameter naming follows ``build_inject_params_for_context`` in
``opencontractserver.llms.tools.tool_factory`` — ``user_id`` is
auto-injected by the tool wrapper and hidden from the LLM's schema. The
tool deliberately has no ``corpus_id`` parameter: it is corpus-agnostic
and usable from any chat context.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from opencontractserver.constants.tools import (
    MULTI_CORPUS_SEARCH_DEFAULT_TOP_K,
    MULTI_CORPUS_SEARCH_MAX_CORPORA,
    MULTI_CORPUS_SEARCH_MAX_TOP_K,
    MULTI_CORPUS_SEARCH_SNIPPET_MAX_CHARS,
)
from opencontractserver.utils.text import truncate

from ._helpers import _db_sync_to_async, clamp_limit, get_user_or_none

logger = logging.getLogger(__name__)


def _resolve_group_corpora(
    corpus_group: str, user_id: int | None
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Resolve the group + its READ-visible member corpora (sync ORM part).

    Returns ``(group_info, corpus_rows)`` where each corpus row carries the
    fields needed to build that corpus's vector store. Raises ``ValueError``
    with an IDOR-uniform message when the group is missing or invisible.
    """
    from opencontractserver.corpuses.services import CorpusGroupService

    user = get_user_or_none(user_id)

    group = CorpusGroupService.get_group_by_ref(user, corpus_group)
    if group is None:
        raise ValueError(
            f"Corpus group '{corpus_group}' does not exist or is not accessible."
        )

    corpora = CorpusGroupService.get_group_corpora_visible_to_user(user, group)
    corpus_rows = [
        {
            "corpus_id": c.pk,
            "corpus_title": c.title,
            "embedder_path": c.preferred_embedder,
        }
        for c in corpora.order_by("id")
    ]
    group_info = {
        "corpus_group_id": group.pk,
        "corpus_group_slug": group.slug,
        "corpus_group_title": group.title,
    }
    return group_info, corpus_rows


async def _search_one_corpus(
    corpus_row: dict[str, Any], query: str, k: int, user_id: int | None
) -> dict[str, Any]:
    """Vector-search a single member corpus, isolating operational failures.

    A failing corpus (e.g. missing embedder) contributes an ``error`` entry
    instead of aborting the whole cross-corpus call.
    """
    from opencontractserver.llms.vector_stores.core_vector_stores import (
        CoreAnnotationVectorStore,
        VectorSearchQuery,
    )

    entry: dict[str, Any] = {
        "corpus_id": corpus_row["corpus_id"],
        "corpus_title": corpus_row["corpus_title"],
        "results": [],
    }
    try:
        store = CoreAnnotationVectorStore(
            user_id=user_id,
            corpus_id=corpus_row["corpus_id"],
            embedder_path=corpus_row["embedder_path"],
        )
        results = await store.async_search(
            VectorSearchQuery(query_text=query, similarity_top_k=k)
        )

        def _serialise() -> list[dict[str, Any]]:
            # ``annotation_label`` / ``document`` are select_related by the
            # store's base queryset, but attribute access is wrapped anyway
            # so a queryset-shape change can never raise
            # SynchronousOnlyOperation from inside the event loop.
            rows: list[dict[str, Any]] = []
            for result in results:
                annotation = result.annotation
                rows.append(
                    {
                        "annotation_id": annotation.id,
                        "document_id": annotation.document_id,
                        "document_title": (
                            annotation.document.title if annotation.document else None
                        ),
                        "page": annotation.page,
                        "label": (
                            annotation.annotation_label.text
                            if annotation.annotation_label
                            else None
                        ),
                        "content": truncate(
                            annotation.raw_text or "",
                            MULTI_CORPUS_SEARCH_SNIPPET_MAX_CHARS,
                        ),
                        "similarity_score": result.similarity_score,
                    }
                )
            return rows

        entry["results"] = await _db_sync_to_async(_serialise)()
    except Exception as exc:  # operational: isolate per corpus (issue #820)
        logger.warning(
            "search_across_corpora: corpus %s failed: %s",
            corpus_row["corpus_id"],
            exc,
        )
        entry["error"] = f"Search failed for this corpus: {exc}"
    return entry


async def asearch_across_corpora(
    query: str,
    corpus_group: str,
    k: int | None = None,
    user_id: int | None = None,
) -> dict[str, Any]:
    """Semantic search across every corpus in a corpus group.

    Fans the query out to each corpus the calling user can read in the
    named :class:`CorpusGroup` and returns the hits grouped per corpus so
    answers can cite each source corpus explicitly. Group membership is
    resolved at call time — corpora added to the group are searchable on
    the very next query.

    Args:
        query: The semantic search query text.
        corpus_group: Slug or numeric ID of the corpus group to search
            (e.g. 'bolivian-laws').
        k: Max results per corpus (default 5, capped at 25).

    Returns:
        A dict with the group identity (``corpus_group_id`` / ``_slug`` /
        ``_title``), ``searched_corpora`` (count), ``corpora_truncated``
        (visible members beyond the per-call corpus cap, 0 when none) and
        ``results_by_corpus`` — one entry per searched corpus with
        ``corpus_id``, ``corpus_title`` and ``results`` (each hit carries
        ``annotation_id``, ``document_id``, ``document_title``, ``page``,
        ``label``, ``content`` and ``similarity_score``).
    """
    group_info, corpus_rows = await _db_sync_to_async(_resolve_group_corpora)(
        corpus_group, user_id
    )

    top_k = clamp_limit(
        k, MULTI_CORPUS_SEARCH_DEFAULT_TOP_K, MULTI_CORPUS_SEARCH_MAX_TOP_K
    )

    truncated = max(0, len(corpus_rows) - MULTI_CORPUS_SEARCH_MAX_CORPORA)
    if truncated:
        logger.warning(
            "search_across_corpora: group %s has %d visible corpora; "
            "searching the first %d.",
            group_info["corpus_group_id"],
            len(corpus_rows),
            MULTI_CORPUS_SEARCH_MAX_CORPORA,
        )
        corpus_rows = corpus_rows[:MULTI_CORPUS_SEARCH_MAX_CORPORA]

    results_by_corpus = list(
        await asyncio.gather(
            *(_search_one_corpus(row, query, top_k, user_id) for row in corpus_rows)
        )
    )

    return {
        **group_info,
        "searched_corpora": len(corpus_rows),
        "corpora_truncated": truncated,
        "results_by_corpus": results_by_corpus,
    }
