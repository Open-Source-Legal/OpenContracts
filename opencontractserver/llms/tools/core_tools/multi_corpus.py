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


def _resolve_group_document(
    corpus_group: str, document_id: int, user_id: int | None
) -> tuple[Any, Any]:
    """Resolve one active document through a group's current visibility gate.

    This is the document-level companion to :func:`asearch_across_corpora`.
    A cross-corpus search result is not enough authority to load its whole
    document: the target must still be reachable through the same named group
    and the caller must currently have READ access to that member corpus.

    The deliberately uniform error keeps both missing and inaccessible group
    members from becoming a document-ID probe.
    """
    from opencontractserver.corpuses.services import CorpusGroupService
    from opencontractserver.documents.models import DocumentPath

    user = get_user_or_none(user_id)
    group = CorpusGroupService.get_group_by_ref(user, corpus_group)
    if group is None:
        raise ValueError(
            f"Corpus group '{corpus_group}' does not exist or is not accessible."
        )

    visible_corpora = CorpusGroupService.get_group_corpora_visible_to_user(user, group)
    path = (
        DocumentPath.objects.select_related("document", "corpus")
        .filter(
            corpus__in=visible_corpora,
            document_id=document_id,
            is_current=True,
            is_deleted=False,
        )
        .order_by("corpus_id", "id")
        .first()
    )
    if path is None:
        raise ValueError("Document is not available in the selected corpus group.")
    return path.document, path.corpus


async def aresolve_group_document(
    corpus_group: str, document_id: int, user_id: int | None
) -> tuple[Any, Any]:
    """Async wrapper for securely resolving a document from a corpus group."""
    return await _db_sync_to_async(_resolve_group_document)(
        corpus_group, document_id, user_id
    )


def _documents_by_structural_set(
    structural_set_ids: set[int], corpus_id: int
) -> dict[int, Any]:
    """Map ``structural_set_id`` → the document CURRENT in this corpus.

    Authority corpora annotate structurally: every hit carries
    ``document_id=None`` and reaches its document through the shared
    ``StructuralAnnotationSet``. Without this resolution the tool hands the
    model a hit with no document at all, which is why cross-corpus answers
    cited "paragraph p.0" instead of a rule section.

    Resolving through the *current* ``DocumentPath`` is the load-bearing part.
    A structural set is shared by every sibling in a version tree, so taking
    the set's first document can name a superseded version — citing the prior
    Planning Guide § 9 for a question about what applies today is precisely the
    error this whole corpus design exists to prevent.
    """
    from opencontractserver.documents.models import DocumentPath

    if not structural_set_ids:
        return {}
    paths = DocumentPath.objects.filter(
        corpus_id=corpus_id,
        is_current=True,
        is_deleted=False,
        document__structural_annotation_set_id__in=structural_set_ids,
    ).select_related("document")
    return {
        set_id: path.document
        for path in paths
        if path.document is not None
        and (set_id := path.document.structural_annotation_set_id) is not None
    }


# Authority metadata worth citing, copied from the document's ``custom_meta``
# onto every hit. Names match the ingestion vocabulary so a citation can be
# checked against the source record without a translation table.
_AUTHORITY_CITATION_FIELDS = (
    "canonical_key",
    "authority_weight",
    "instrument_type",
    "publisher",
    "status",
    "effective_from",
    "effective_until",
    "version_label",
    "current_version",
    "source_url",
)


def _authority_citation_fields(document: Any) -> dict[str, Any]:
    """Extract the citable authority identity of a document, if it has one.

    Returns only keys that are actually present: a corpus of ordinary uploads
    has no authority metadata, and emitting nulls would invite the model to
    cite empty fields as though they were real.
    """
    meta = getattr(document, "custom_meta", None)
    if not isinstance(meta, dict):
        return {}
    fields = {
        key: meta[key]
        for key in _AUTHORITY_CITATION_FIELDS
        if meta.get(key) not in (None, "")
    }
    # ``instrument_type`` is nested under ``metadata`` for records written by
    # the authority-pack builder; surface it either way.
    nested = meta.get("metadata")
    if "instrument_type" not in fields and isinstance(nested, dict):
        if nested.get("instrument_type"):
            fields["instrument_type"] = nested["instrument_type"]
    # A canonical key like ``ercot-planning:9.2.1.1`` carries the section.
    canonical_key = fields.get("canonical_key")
    if isinstance(canonical_key, str) and ":" in canonical_key:
        fields["section"] = canonical_key.split(":", 1)[1]
    return fields


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
            # Structural annotations reach their document through the shared
            # set; resolve them in one query rather than per row.
            set_ids = {
                result.annotation.structural_set_id
                for result in results
                if result.annotation.document_id is None
                and result.annotation.structural_set_id
            }
            by_set = _documents_by_structural_set(set_ids, corpus_row["corpus_id"])

            rows: list[dict[str, Any]] = []
            for result in results:
                annotation = result.annotation
                document = annotation.document
                if document is None and annotation.structural_set_id is not None:
                    document = by_set.get(annotation.structural_set_id)
                row: dict[str, Any] = {
                    "annotation_id": annotation.id,
                    "document_id": (document.pk if document else None),
                    "document_title": (document.title if document else None),
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
                # Authority identity travels with the hit. Without it the model
                # can only cite what it was handed — label plus page — which is
                # how a conclusion ends up sourced to "paragraph p.0" instead of
                # a rule section with an effective date. These fields are also
                # what makes a citation machine-verifiable after the fact:
                # canonical_key + annotation_id pin an exact span of an exact
                # authority version.
                row.update(_authority_citation_fields(document))
                rows.append(row)
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
