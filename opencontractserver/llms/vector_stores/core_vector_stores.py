"""Core vector store functionality independent of any specific agent framework."""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Literal, Optional, Union

from asgiref.sync import async_to_sync, sync_to_async
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.db.models import Q

from opencontractserver.annotations.models import (
    Annotation,
    Relationship,
    StructuralAnnotationSet,
)
from opencontractserver.constants.annotations import (
    OC_SUBTREE_GROUP_LABEL_NAME,
)
from opencontractserver.constants.search import (
    FTS_CONFIG,
    HYBRID_SEARCH_OVERSAMPLE_FACTOR,
    RERANK_MAX_CANDIDATES,
    RERANK_OVERSAMPLE_FACTOR,
    VALID_EMBEDDING_DIMS,
)
from opencontractserver.llms.vector_stores.base_vector_store import BaseVectorStore
from opencontractserver.pipeline.base.reranker import (
    BaseReranker,
    safe_arerank,
    safe_rerank,
)
from opencontractserver.shared.QuerySets import AnnotationQuerySet
from opencontractserver.types.protocols import VectorStoreProtocol
from opencontractserver.utils.embeddings import join_block_text_parts
from opencontractserver.utils.search import reciprocal_rank_fusion

User = get_user_model()

_logger = logging.getLogger(__name__)


def _is_async_context() -> bool:
    """Check if we're currently running in an async context."""
    try:
        asyncio.current_task()
        return True
    except RuntimeError:
        return False


async def _safe_queryset_info(queryset, description: str) -> str:
    """Safely log queryset/list information in both sync and async contexts.

    Args:
        queryset: Either a Django QuerySet or a list (after search_by_embedding deduplication)
        description: Description for logging
    """
    try:
        # Handle lists (from search_by_embedding which materializes for deduplication)
        if isinstance(queryset, list):
            return f"{description}: {len(queryset)} results"

        # Handle QuerySets
        if _is_async_context():
            count = await sync_to_async(queryset.count)()
            return f"{description}: {count} results"
        else:
            return f"{description}: {queryset.count()} results"
    except Exception as e:
        return f"{description}: unable to count results ({e})"


def _safe_queryset_info_sync(queryset, description: str) -> str:
    """Safely log queryset/list information in sync context only.

    Args:
        queryset: Either a Django QuerySet or a list (after search_by_embedding deduplication)
        description: Description for logging
    """
    if _is_async_context():
        return f"{description}: queryset (async context - count not available)"
    else:
        try:
            # Handle lists (from search_by_embedding which materializes for deduplication)
            if isinstance(queryset, list):
                return f"{description}: {len(queryset)} results"

            # Handle QuerySets
            return f"{description}: {queryset.count()} results"
        except Exception as e:
            return f"{description}: unable to count results ({e})"


async def _safe_execute_queryset(queryset) -> list:
    """Safely execute a queryset/list in both sync and async contexts.

    Args:
        queryset: Either a Django QuerySet or a list (after search_by_embedding deduplication)

    Returns:
        List of results
    """
    # If already a list (from search_by_embedding deduplication), return as-is
    if isinstance(queryset, list):
        return queryset

    # Execute QuerySet
    if _is_async_context():
        return await sync_to_async(lambda: list(queryset))()
    else:
        return list(queryset)


SearchMode = Literal["vector", "fts", "hybrid"]
"""Retrieval mode for :class:`VectorSearchQuery`.

- ``"vector"``: pgvector cosine similarity only.
- ``"fts"``: PostgreSQL full-text search (``tsvector``) only.
- ``"hybrid"``: both arms fused via Reciprocal Rank Fusion. *Default.*

``"fts"`` and ``"hybrid"`` degrade to ``"vector"`` when no ``query_text`` is
supplied; ``"hybrid"`` degrades to text-only when embedding generation fails.
"""


@dataclass
class VectorSearchQuery:
    """Framework-agnostic vector search query."""

    query_text: Optional[str] = None
    query_embedding: Optional[list[float]] = None
    similarity_top_k: int = 100
    filters: Optional[dict[str, Any]] = None
    mode: SearchMode = "hybrid"


@dataclass
class BlockContext:
    """Smallest enclosing ``OC_SUBTREE_GROUP`` for a vector hit."""

    relationship_id: int
    source_annotation_id: int
    source_text: str
    target_annotation_ids: list[int] = field(default_factory=list)
    # Same bounded string the embedder saw — consumers can render a
    # snippet without re-fetching annotations.
    block_text: str = ""


@dataclass
class VectorSearchResult:
    """Framework-agnostic vector search result."""

    annotation: Annotation
    similarity_score: float = 1.0
    # None when the hit isn't inside a materialised OC_SUBTREE_GROUP.
    block_context: Optional[BlockContext] = None


class CoreAnnotationVectorStore(BaseVectorStore):
    """Core annotation vector store functionality independent of agent frameworks.

    This class encapsulates the business logic for searching annotations using
    vector embeddings and various filters. It operates directly with Django
    models and can be wrapped by different agent framework adapters.

    Args:
        user_id: Filter by user ID
        corpus_id: Filter by corpus ID
        document_id: Filter by document ID
        must_have_text: Filter by text content
        embedder_path: Path to embedder model to use
        embed_dim: Embedding dimension (384, 768, 1536, or 3072)
        modalities: Filter by content modalities (e.g., ["TEXT"], ["IMAGE"],
                   ["TEXT", "IMAGE"]). If provided, only annotations containing
                   ANY of the specified modalities will be returned.
    """

    def __init__(
        self,
        user_id: Union[str, int, None] = None,
        corpus_id: Union[str, int, None] = None,
        document_id: Union[str, int, None] = None,
        embedder_path: Optional[str] = None,
        must_have_text: Optional[str] = None,
        embed_dim: int = 384,
        only_current_versions: bool = True,  # NEW: Default to current versions only
        check_corpus_deletion: bool = True,  # NEW: Check DocumentPath for deletion status
        modalities: Optional[list[str]] = None,
        reranker: Optional[BaseReranker] = None,
        rerank_oversample_factor: int = RERANK_OVERSAMPLE_FACTOR,
    ):
        # Embedder resolution + corpus/embedder_path validation lives in BaseVectorStore.
        super().__init__(
            user_id=user_id,
            corpus_id=corpus_id,
            document_id=document_id,
            embedder_path=embedder_path,
            embed_dim=embed_dim,
        )
        self.must_have_text = must_have_text
        self.only_current_versions = only_current_versions
        self.check_corpus_deletion = check_corpus_deletion
        self.modalities = modalities
        # Caller may inject a specific reranker (useful for tests) or leave
        # it ``None`` to pick up the global ``PipelineSettings.default_reranker``
        # on every search call. Lazy resolution keeps store construction
        # cheap even on the hot path.
        self._reranker_override: Optional[BaseReranker] = reranker
        self.rerank_oversample_factor = max(1, int(rerank_oversample_factor))
        _logger.debug(f"Configured embedder path: {self.embedder_path}")

    async def _build_base_queryset(self) -> AnnotationQuerySet:
        """Build the base annotation queryset applying the following rules.

        1. Scope by document or corpus if those identifiers were supplied.
        2. Optionally filter annotations whose ``raw_text`` contains the
           ``must_have_text`` substring provided at construction time.  The
           match is case-insensitive (``icontains``).
        3. Visibility rules:

           • *Structural* annotations are **always** returned.

           • *Non-structural* annotations:
               – When ``user_id`` **is provided** ⇒ limit to annotations the
                 user created (``creator_id == user_id``).
               – When ``user_id`` is **not provided** ⇒ limit to annotations
                 that are public (``is_public=True``).

        These rules mirror the expectations captured in the Django test suite
        (``tests/test_django_annotation_vector_store.py``).
        """
        _logger.debug("Building base queryset for vector search")

        # IDOR pre-check via BaseVectorStore: deny by empty result for both
        # "user not found" and "no permission on document/corpus" cases.
        from opencontractserver.documents.models import Document, DocumentPath

        user, user_invalid = await self._aresolve_user()
        if user_invalid:
            return Annotation.objects.none()
        if await self._acheck_idor(user):
            return Annotation.objects.none()

        # Select related for fields directly on Annotation or accessed often.
        # Document's M2M to Corpus (corpus_set) is handled by JOINs in filters.
        queryset = Annotation.objects.select_related(
            "annotation_label", "document", "corpus"
        ).all()
        _logger.info(
            await _safe_queryset_info(queryset, "Initial: Total annotations in DB")
        )

        active_filters = Q()

        # ------------------------------------------------------------------ #
        # Filter to current document versions if requested
        # ------------------------------------------------------------------ #
        # CRITICAL: This filter must preserve structural annotations!
        #
        # Background:
        # - Regular annotations have document_id FK → can filter via document__is_current
        # - Structural annotations from StructuralAnnotationSet have document_id=NULL
        #   (they're linked via structural_set_id instead)
        #
        # Problem:
        # - Q(document__is_current=True) creates INNER JOIN on document table
        # - Annotations with document_id=NULL fail the JOIN and are excluded
        # - This happens BEFORE document/corpus scoping (lines 196-228)
        # - Result: Structural annotations are filtered out before scoping can include them
        #
        # Solution:
        # - For annotations WITH document FK: require document.is_current=True
        # - For structural annotations (document_id=NULL): allow through to scoping
        # - Later scoping logic (lines 196-228) will filter by structural_set_id
        #   to ensure only structural annotations from the relevant document are included
        #
        if self.only_current_versions:
            active_filters &= Q(document__is_current=True) | Q(
                document_id__isnull=True, structural=True
            )
            _logger.debug(
                "Filtering to current document versions (preserving structural annotations)"
            )

        # Check for deleted documents in corpus
        if self.check_corpus_deletion and self.corpus_id and not self.document_id:
            # Lazy subquery — never round-trips through Python, so the
            # generated SQL stays a single statement with a real subquery
            # rather than a giant ``IN (val, val, ...)`` literal even for
            # corpora with tens of thousands of documents.
            active_doc_ids_qs = (
                DocumentPath.objects.filter(
                    corpus_id=self.corpus_id, is_current=True, is_deleted=False
                )
                .values("document_id")
                .distinct()
            )
            # Trade-off: this ``EXISTS`` adds one extra round-trip on the
            # happy path, but lets us short-circuit the entire vector search
            # for empty/all-deleted corpora (returning ``Annotation.none()``
            # spares a downstream HNSW probe and keeps the existing
            # operational warning). For corpora with at least one active
            # document the cost is a single boolean SELECT and is dwarfed
            # by the main query. Removing the check would also remove the
            # debug log of the active-doc count that the materialised list
            # used to provide.
            has_active_docs = await sync_to_async(active_doc_ids_qs.exists)()

            if has_active_docs:
                # Two annotation shapes pass this filter:
                #   1. Direct: Annotation.document_id is in the active set.
                #   2. Structural: Annotation.document_id is NULL but the
                #      structural_set links to one of those active documents.
                #      ``document_id__in`` cannot match NULL on its own, so
                #      structural annotations need an explicit OR clause —
                #      otherwise every parser-produced structural row is
                #      silently dropped on this corpus-wide path.
                active_struct_set_ids = (
                    StructuralAnnotationSet.objects.filter(
                        documents__in=active_doc_ids_qs
                    )
                    .values("id")
                    .distinct()
                )
                active_filters &= Q(document_id__in=active_doc_ids_qs) | Q(
                    structural=True, structural_set_id__in=active_struct_set_ids
                )
            else:
                _logger.warning(f"No active documents found in corpus {self.corpus_id}")
                return Annotation.objects.none()

        # ------------------------------------------------------------------ #
        # Document/Corpus scoping
        # ------------------------------------------------------------------ #
        # This section filters annotations by document and/or corpus context.
        # IMPORTANT: Structural annotations allowed through by the version filter above
        # (lines 190-196) are now scoped to only include those from the relevant
        # document's structural_annotation_set.
        #
        if self.document_id is not None:
            # --- Document-specific context ---
            _logger.debug(
                f"Document context: document_id={self.document_id}, corpus_id={self.corpus_id}"
            )

            # Get document to check for structural_annotation_set
            # Note: Document already imported at top of _build_base_queryset
            # Bind to a local so mypy can narrow inside the lambda closure.
            doc_pk = self.document_id
            document = await sync_to_async(
                lambda: Document.objects.select_related(
                    "structural_annotation_set"
                ).get(pk=doc_pk)
            )()

            # Build filter for annotations from BOTH sources:
            # 1. Direct document annotations (user-created, corpus-specific)
            #    - Have document_id=self.document_id
            #    - Have corpus_id set (if corpus-isolated) or NULL (if standalone)
            # 2. Structural annotations from document's structural_annotation_set
            #    - Have document_id=NULL (stored in StructuralAnnotationSet)
            #    - Have structural_set_id=document.structural_annotation_set_id
            #    - Have structural=True
            #    - Shared across all corpus copies of this document
            #
            doc_filters = Q(document_id=self.document_id)

            if document.structural_annotation_set_id:
                # Include structural annotations from the shared set.
                # These annotations were preserved by the version filter above
                # (lines 190-196) and are now scoped to this specific document.
                doc_filters |= Q(
                    structural_set_id=document.structural_annotation_set_id,
                    structural=True,
                )
                _logger.debug(
                    f"Including structural annotations from set {document.structural_annotation_set_id}"
                )

            active_filters &= doc_filters

        elif self.corpus_id is not None:
            # --- Corpus-only context (no document_id specified) ---
            _logger.debug(f"Corpus-only context: corpus_id={self.corpus_id}")
            # Annotations must be either:
            # a) Structural — restricted to ``structural_set``s reachable from
            #    a document in this corpus that is *visible to the requesting
            #    user*. This collapses two checks into one filter:
            #
            #      • Corpus boundary (was missing): a parser-produced
            #        structural annotation has ``document_id = corpus_id =
            #        NULL``; its corpus membership is only knowable via
            #        ``structural_set → Document.structural_annotation_set
            #        (reverse FK) → DocumentPath.corpus_id``.
            #      • Per-document permission (was bypassed): structural rows
            #        previously matched ``Q(structural=True)`` unconditionally,
            #        so a user with permission on the *corpus* could be served
            #        rows whose underlying documents they have no permission
            #        on.
            #
            #    Without this, the corpus-wide path leaked structural rows from
            #    every other corpus in the database (and from inaccessible
            #    documents within the same corpus).
            # b) Non-structural — directly linked to this corpus via
            #    ``Annotation.corpus_id``. Per-document visibility for these
            #    rows is enforced by the visibility filter further below
            #    plus the upfront IDOR check on ``corpus_id``.
            # Both subqueries below stay lazy so the SQL planner sees a
            # nested ``IN (SELECT ...)`` rather than a Python-materialised
            # ``IN (val, val, ...)`` literal — important for corpora with
            # tens of thousands of documents.
            visible_corpus_doc_ids_qs = (
                Document.objects.visible_to_user(user)
                .filter(path_records__corpus_id=self.corpus_id)
                .values("id")
                .distinct()
            )
            visible_corpus_set_ids = (
                StructuralAnnotationSet.objects.filter(
                    documents__in=visible_corpus_doc_ids_qs
                )
                .values("id")
                .distinct()
            )
            active_filters &= Q(
                structural=True, structural_set_id__in=visible_corpus_set_ids
            ) | Q(structural=False, corpus_id=self.corpus_id)

        # ------------------------------------------------------------------ #
        # Apply accumulated document/corpus scope filters if any were added
        if active_filters != Q():  # Check if any conditions were actually added
            queryset = queryset.filter(active_filters)
            _logger.info(
                await _safe_queryset_info(queryset, "After document/corpus scoping")
            )
        else:
            _logger.info(
                "No document/corpus scope filters applied (e.g., "
                "neither document_id nor corpus_id provided for scoping)."
            )

        # ------------------------------------------------------------------ #
        # Text substring filtering (must_have_text)
        # ------------------------------------------------------------------ #
        if self.must_have_text:
            queryset = queryset.filter(raw_text__icontains=self.must_have_text)
            _logger.info(
                await _safe_queryset_info(
                    queryset, f"After must_have_text='{self.must_have_text}' filter"
                )
            )

        # -------------------------------------------------------------- #
        # Visibility rules
        # -------------------------------------------------------------- #
        # For document-specific queries we want ALL structural annotations
        # from that document irrespective of user/public flags **plus**
        # the usual visibility logic for *non-structural* annotations.
        #
        #   structural annotations → always visible (document filtered above)
        #   non-structural annotations → visible if public OR owned by user
        #
        # This translates to:
        #     (structural=True) OR
        #     (structural=False AND (is_public=True OR creator_id=<user>))
        #
        # For non-document contexts we keep similar behaviour but tighten
        # non-structural visibility when a user_id is supplied.

        if self.user_id is not None:
            # User-specific request → include ALL structural annotations plus
            # the requesting user's non-structural annotations.
            visibility_q = Q(structural=True) | Q(
                structural=False, creator_id=self.user_id
            )
        else:
            # Anonymous / system request → structural annotations plus any
            # non-structural annotations explicitly made public.
            visibility_q = Q(structural=True) | Q(structural=False, is_public=True)

        _logger.debug(f"Applying visibility filter: {visibility_q}")
        queryset = queryset.filter(visibility_q)
        _logger.debug(f"Query after visibility filter: {queryset.query}")
        _logger.info(
            await _safe_queryset_info(
                queryset, "Annotations after visibility filtering"
            )
        )

        # ------------------------------------------------------------------ #
        # Content modality filtering
        # ------------------------------------------------------------------ #
        # Filter annotations by content_modalities if specified.
        # This enables filtering for specific content types:
        #   - ["TEXT"] - only text annotations
        #   - ["IMAGE"] - only image annotations
        #   - ["TEXT", "IMAGE"] - annotations with either text OR images
        #
        # The filter uses ArrayField contains lookup to find annotations
        # that contain ANY of the specified modalities.
        if self.modalities:
            modality_q = Q()
            for modality in self.modalities:
                # content_modalities__contains checks if array contains the value
                modality_q |= Q(content_modalities__contains=[modality])
            queryset = queryset.filter(modality_q)
            _logger.info(
                await _safe_queryset_info(
                    queryset, f"After modalities={self.modalities} filter"
                )
            )

        _logger.debug("Generated SQL query: %s", queryset.query)

        return queryset

    def _apply_metadata_filters(
        self, queryset: AnnotationQuerySet, filters: Optional[dict[str, Any]]
    ) -> AnnotationQuerySet:
        """Apply additional metadata filters to the queryset."""
        if not filters:
            return queryset

        _logger.debug(f"Applying metadata filters: {filters}")

        for key, value in filters.items():
            if key == "annotation_label":
                queryset = queryset.filter(annotation_label__text__icontains=value)
            elif key == "label":
                queryset = queryset.filter(annotation_label__text__iexact=value)
            else:
                # Generic filter fallback
                queryset = queryset.filter(**{f"{key}__icontains": value})

        _logger.debug(f"After metadata filters: {queryset.query}")
        return queryset

    # ------------------------------------------------------------------ #
    # Block-context (OC_SUBTREE_GROUP) augmentation
    # ------------------------------------------------------------------ #
    @staticmethod
    def _attach_block_context_sync(
        results: list["VectorSearchResult"],
        user_id: Union[str, int, None] = None,
    ) -> list["VectorSearchResult"]:
        """Populate ``result.block_context`` for hits inside a subtree group.

        Security gate is mechanical: the relationship lookup runs through
        ``Relationship.objects.visible_to_user`` using ``user_id`` (or
        ``AnonymousUser`` when ``None``), so the helper cannot leak a
        block whose parent doc/corpus the caller can't read — even if the
        annotation-level filter upstream is later loosened or bypassed.
        Defense in depth complementing the store's visibility queryset.
        """
        if not results:
            return results

        hit_ids = {r.annotation.id for r in results if r.annotation is not None}
        if not hit_ids:
            return results

        # Resolve user up front so the manager can apply MIN(doc, corpus)
        # visibility via ``Document``/``Corpus`` visible_to_user lookups.
        # ``None`` → ``AnonymousUser`` matches the manager's normalisation.
        if user_id is None:
            user: Any = AnonymousUser()
        else:
            user = User.objects.filter(id=user_id).first() or AnonymousUser()

        # ``OC_SUBTREE_GROUP`` rows are always structural; filter both on
        # the label text AND ``structural=True`` so a hypothetical
        # non-structural relationship with the same label text (e.g. an
        # analyzer copying the label) cannot pollute block context. The
        # ``target_annotations__in=hit_ids`` filter is the small side of
        # the join — typical hit sets are <= ``similarity_top_k`` (≤200).
        groups = (
            Relationship.objects.visible_to_user(user)
            .filter(
                relationship_label__text=OC_SUBTREE_GROUP_LABEL_NAME,
                structural=True,
                target_annotations__in=hit_ids,
            )
            .prefetch_related("source_annotations", "target_annotations")
            .distinct()
        )

        # Two passes: build hit→best-group map, then fetch every annotation
        # referenced by a winning group in a single query.
        #
        # ``best_for_hit`` keys on annotation_id; value is (descendant_count,
        # relationship_obj). Tie-break on relationship pk for determinism so
        # snapshot tests don't flake when two groups share a descendant count.
        #
        # We deliberately compute ``descendant_count`` from the prefetched
        # ``target_annotations`` rather than via ``Count("target_annotations")``
        # in the queryset. With ``target_annotations__in=hit_ids`` already
        # joined, Django's COUNT on the same M2M is restricted by the join
        # and would return only the matching subset (i.e. always 1 here),
        # collapsing the "smallest enclosing" tie-break to the lowest pk.
        best_for_hit: dict[int, tuple[int, Relationship]] = {}
        for group in groups:
            target_ids_in_group = {a.id for a in group.target_annotations.all()}
            descendant_count = len(target_ids_in_group)
            for hit_id in hit_ids & target_ids_in_group:
                existing = best_for_hit.get(hit_id)
                if existing is None:
                    best_for_hit[hit_id] = (descendant_count, group)
                    continue
                existing_count, existing_group = existing
                # Smaller descendant count wins (most-specific enclosing
                # block). Tie-break by lower relationship pk for stable
                # ordering across runs.
                if descendant_count < existing_count or (
                    descendant_count == existing_count and group.pk < existing_group.pk
                ):
                    best_for_hit[hit_id] = (descendant_count, group)

        if not best_for_hit:
            return results

        # Single fetch for every annotation referenced by a winning group's
        # source or target set — keyed by ID so block_text assembly is O(N).
        referenced_ann_ids: set[int] = set()
        for _, winner_group in best_for_hit.values():
            referenced_ann_ids.update(
                a.id for a in winner_group.source_annotations.all()
            )
            referenced_ann_ids.update(
                a.id for a in winner_group.target_annotations.all()
            )
        ann_text_map = dict(
            Annotation.objects.filter(id__in=referenced_ann_ids).values_list(
                "id", "raw_text"
            )
        )

        for r in results:
            if r.annotation is None:
                continue
            winner = best_for_hit.get(r.annotation.id)
            if winner is None:
                continue
            _, hit_group = winner
            source_ann = next(iter(hit_group.source_annotations.all()), None)
            if source_ann is None:
                # An OC_SUBTREE_GROUP without a source annotation is
                # malformed (the materialiser always sets one). Skip
                # silently rather than fabricate a context.
                continue
            target_ann_ids = sorted(a.id for a in hit_group.target_annotations.all())
            source_text = ann_text_map.get(source_ann.id, "") or ""
            # Order targets by ID for deterministic snapshots; the
            # materialiser doesn't preserve a semantic ordering so any
            # stable choice is fine. ``join_block_text_parts`` enforces
            # SUBTREE_GROUP_BLOCK_TEXT_MAX_CHARS identically to the
            # embedder so block_text matches what was indexed.
            chunks: list[str] = [source_text]
            chunks.extend(ann_text_map.get(tid, "") or "" for tid in target_ann_ids)
            block_text = join_block_text_parts(chunks)

            r.block_context = BlockContext(
                relationship_id=hit_group.pk,
                source_annotation_id=source_ann.id,
                source_text=source_text,
                target_annotation_ids=target_ann_ids,
                block_text=block_text,
            )

        return results

    async def _aattach_block_context(
        self, results: list["VectorSearchResult"]
    ) -> list["VectorSearchResult"]:
        """Async wrapper around :meth:`_attach_block_context_sync`."""
        # One sync_to_async per call — the whole pass shares the same
        # M2M joins, so splitting would buy nothing.
        return await sync_to_async(self._attach_block_context_sync)(
            results, self.user_id
        )

    # Sync + async query-embedding generation are inherited from BaseVectorStore.

    # ------------------------------------------------------------------ #
    # Reranker plumbing
    # ------------------------------------------------------------------ #
    def _get_reranker(self) -> Optional[BaseReranker]:
        """Return the active reranker for this store, or ``None``.

        Resolution order:
        1. Constructor-provided override (``reranker=`` kwarg).
        2. ``PipelineSettings.default_reranker`` (process-cached).

        Returns ``None`` when no reranker is configured — callers should
        treat this as "reranking disabled" and use first-stage ordering.
        """
        if self._reranker_override is not None:
            return self._reranker_override
        # Lazy import to avoid pulling the Django model at module import time
        # and to support hot-reloading after settings changes in tests.
        from opencontractserver.pipeline.utils import get_default_reranker_instance

        return get_default_reranker_instance()

    def _effective_first_stage_top_k(
        self, requested_top_k: int, reranker: Optional[BaseReranker]
    ) -> int:
        """Compute how many candidates first-stage retrieval should fetch.

        When a reranker is active we oversample by ``rerank_oversample_factor``,
        bounded above by :data:`RERANK_MAX_CANDIDATES` so cross-encoder cost
        stays bounded even when a caller requests a very large ``top_k``.
        """
        if reranker is None:
            return requested_top_k
        oversampled = requested_top_k * self.rerank_oversample_factor
        return max(requested_top_k, min(oversampled, RERANK_MAX_CANDIDATES))

    @staticmethod
    def _rerank_results(
        results: list["VectorSearchResult"],
        query_text: Optional[str],
        top_k: int,
        reranker: Optional[BaseReranker],
    ) -> list["VectorSearchResult"]:
        """Shared sync rerank helper used by both instance and classmethod paths."""
        if reranker is None or not query_text or not query_text.strip():
            return results[:top_k]
        if not results:
            return results

        passages = [getattr(r.annotation, "raw_text", "") or "" for r in results]
        rerank_output = safe_rerank(reranker, query_text, passages, top_k=top_k)
        if rerank_output is None:
            return results[:top_k]

        reordered: list[VectorSearchResult] = []
        for r in rerank_output:
            src = results[r.index]
            reordered.append(
                VectorSearchResult(annotation=src.annotation, similarity_score=r.score)
            )
        return reordered

    def _apply_rerank(
        self,
        results: list["VectorSearchResult"],
        query_text: Optional[str],
        top_k: int,
        reranker: Optional[BaseReranker],
    ) -> list["VectorSearchResult"]:
        """Apply the reranker (sync) if configured; otherwise trim to ``top_k``."""
        return self._rerank_results(results, query_text, top_k, reranker)

    async def _aapply_rerank(
        self,
        results: list["VectorSearchResult"],
        query_text: Optional[str],
        top_k: int,
        reranker: Optional[BaseReranker],
    ) -> list["VectorSearchResult"]:
        """Async variant of :meth:`_apply_rerank`."""
        if reranker is None or not query_text or not query_text.strip():
            return results[:top_k]
        if not results:
            return results

        passages = [getattr(r.annotation, "raw_text", "") or "" for r in results]
        rerank_output = await safe_arerank(reranker, query_text, passages, top_k=top_k)
        if rerank_output is None:
            return results[:top_k]

        reordered: list[VectorSearchResult] = []
        for r in rerank_output:
            src = results[r.index]
            reordered.append(
                VectorSearchResult(annotation=src.annotation, similarity_score=r.score)
            )
        return reordered

    @staticmethod
    def _degrade_mode(mode: SearchMode, has_text: bool, log_prefix: str) -> SearchMode:
        """Degrade ``"fts"``/``"hybrid"`` to ``"vector"`` when ``query_text`` is missing.

        Shared by :meth:`_resolve_mode` (instance path) and :meth:`global_search`
        (classmethod path, which doesn't have a ``VectorSearchQuery`` in scope)
        so the rule lives in exactly one place.
        """
        if mode in ("fts", "hybrid") and not has_text:
            _logger.info(
                "%s mode '%s' requested without query_text; degrading to 'vector'.",
                log_prefix,
                mode,
            )
            return "vector"
        return mode

    @staticmethod
    def _generate_global_query_vector(
        mode: SearchMode,
        query_text: str,
        embedder_path: str,
    ) -> tuple[SearchMode, Optional[list[float]]]:
        """Generate an embedding for the vector arm of :meth:`global_search`.

        Only meaningful when ``mode`` is ``"vector"`` or ``"hybrid"`` (the modes
        that need an embedding). Returns ``(effective_mode, query_vector)``
        after applying embedding-availability degradation:

        - Embedder unavailable / ``embed_text`` returns ``None``:
            - ``"hybrid"`` → ``"fts"`` (the text arm can still run)
            - ``"vector"`` → ``"vector"`` (caller MUST detect the ``None`` vector
              and return ``[]`` — there is nothing to fall back to).
        - Embedding successfully generated: ``mode`` unchanged.

        Extracting this from :meth:`global_search` keeps the
        ``effective_mode`` state transition (a) explicit at a single call site
        and (b) testable in isolation rather than buried in nested ``if/else``.
        """
        from opencontractserver.pipeline.utils import (
            get_default_embedder,
            get_embedder_instance,
        )

        default_embedder_class = get_default_embedder()
        if not default_embedder_class:
            _logger.error("Could not get default embedder for global search")
            return ("fts" if mode == "hybrid" else mode, None)

        # Process-cached instance: avoid paying the per-instantiation DB read +
        # PBKDF2 secret decryption on every global search query.
        query_vector = get_embedder_instance(default_embedder_class).embed_text(
            query_text
        )
        if query_vector is None:
            _logger.warning("Failed to generate query embedding for global search")
            return ("fts" if mode == "hybrid" else mode, None)

        _logger.debug(
            "Generated query embedding with dimension %d using %s",
            len(query_vector),
            embedder_path,
        )
        return (mode, query_vector)

    @staticmethod
    def _resolve_mode(query: VectorSearchQuery) -> SearchMode:
        """Resolve the effective search mode, degrading gracefully when inputs disallow it.

        ``"fts"`` and ``"hybrid"`` require ``query_text``; without it they
        fall back to ``"vector"`` so the caller still gets results when an
        embedding is provided.
        """
        has_text = bool(query.query_text and query.query_text.strip())
        return CoreAnnotationVectorStore._degrade_mode(query.mode, has_text, "Search")

    def search(self, query: VectorSearchQuery) -> list[VectorSearchResult]:
        """Execute a search query, dispatching on ``query.mode``.

        Modes:
            - ``"hybrid"`` (default): RRF fusion of vector + full-text arms
              via :meth:`hybrid_search`.
            - ``"vector"``: pgvector cosine similarity only.
            - ``"fts"``: PostgreSQL full-text search only.

        When a global reranker is configured (``PipelineSettings.default_reranker``)
        the first-stage retrieval oversamples candidates
        (``top_k * rerank_oversample_factor``) and the reranker re-orders
        them before the final ``top_k`` slice is returned. Reranker failures
        degrade gracefully to the first-stage ordering.

        Args:
            query: The search query containing text/embedding, filters, and mode.

        Returns:
            List of search results with annotations and similarity scores.
        """
        mode = self._resolve_mode(query)
        # DEBUG (not INFO): fires on every search call; reserve INFO for
        # state transitions and configuration events.
        _logger.debug("CoreAnnotationVectorStore.search mode=%s", mode)
        if mode == "hybrid":
            return self.hybrid_search(query)
        if mode == "fts":
            return self._run_fts_only_sync(query)
        return self._run_vector_only_sync(query)

    def _run_vector_only_sync(
        self, query: VectorSearchQuery
    ) -> list[VectorSearchResult]:
        """Vector-only sync search path (pgvector cosine similarity)."""
        reranker = self._get_reranker()
        first_stage_top_k = self._effective_first_stage_top_k(
            query.similarity_top_k, reranker
        )

        # Build base queryset with filters
        base_queryset = async_to_sync(self._build_base_queryset)()

        # Apply metadata filters
        base_queryset = self._apply_metadata_filters(base_queryset, query.filters)

        # Determine the query vector
        vector = query.query_embedding
        if vector is None and query.query_text is not None:
            vector = self._generate_query_embedding(query.query_text)

        # ``search_by_embedding`` materialises results into a list while the
        # fallback branch keeps a sliced QuerySet. The downstream code accepts
        # either via the safe queryset helpers.
        queryset: Union[AnnotationQuerySet, list[Any]]

        # Perform vector search if we have a valid embedding
        if vector is not None and len(vector) in VALID_EMBEDDING_DIMS:
            _logger.debug(f"Using vector search with dimension: {len(vector)}")
            _logger.debug(
                f"Performing vector search with embedder: {self.embedder_path}"
            )

            queryset = base_queryset.search_by_embedding(
                query_vector=vector,
                embedder_path=self.embedder_path,
                top_k=first_stage_top_k,
            )
            _logger.debug(_safe_queryset_info_sync(queryset, "After vector search"))
        else:
            # Fallback to standard filtering with limit
            if vector is None:
                _logger.debug(
                    "No vector available for search, using standard filtering"
                )
            else:
                _logger.warning(
                    f"Invalid vector dimension: {len(vector)}, using standard filtering"
                )

            queryset = base_queryset[:first_stage_top_k]
            _logger.debug(_safe_queryset_info_sync(queryset, "After limiting results"))

        # Execute query and convert to results
        _logger.debug("Fetching annotations from database")

        # Safe queryset execution for both sync and async contexts
        if _is_async_context():
            _logger.warning(
                "Sync method called from async context - this may cause issues"
            )
            try:
                annotations = list(queryset)
            except Exception as e:
                _logger.error(f"Failed to execute queryset in async context: {e}")
                return []
        else:
            annotations = list(queryset)

        _logger.debug(f"Retrieved {len(annotations)} annotations")

        if annotations:
            _logger.debug(f"First annotation ID: {annotations[0].id}")
            _logger.info(
                f"[CoreAnnotationVectorStore.search] Vector store returned "
                f"{len(annotations)} annotations for query."
            )
        else:
            _logger.warning("No annotations found for the query")

        # Convert to result objects
        results = []
        for annotation in annotations:
            similarity_score = getattr(annotation, "similarity_score", 1.0)
            # Handle NaN values (can occur when annotations lack computed similarity)
            if similarity_score != similarity_score:  # NaN check (NaN != NaN is True)
                similarity_score = 1.0
            results.append(
                VectorSearchResult(
                    annotation=annotation, similarity_score=similarity_score
                )
            )

        # Second-stage reranking (opt-in via PipelineSettings.default_reranker).
        reranked = self._apply_rerank(
            results, query.query_text, query.similarity_top_k, reranker
        )
        # Attach containing-subtree block context AFTER reranking so the
        # extra DB hop is bounded by the final top_k count rather than the
        # oversampled first-stage pool.
        return self._attach_block_context_sync(reranked, self.user_id)

    def _run_fts_only_sync(self, query: VectorSearchQuery) -> list[VectorSearchResult]:
        """Full-text-only sync search path (PostgreSQL ``tsvector`` ranking).

        Caller is expected to have ensured ``query.query_text`` is non-empty
        (see :meth:`_resolve_mode`); otherwise this returns an empty list.
        """
        if not (query.query_text and query.query_text.strip()):
            return []

        reranker = self._get_reranker()
        first_stage_top_k = self._effective_first_stage_top_k(
            query.similarity_top_k, reranker
        )

        base_queryset = async_to_sync(self._build_base_queryset)()
        base_queryset = self._apply_metadata_filters(base_queryset, query.filters)

        text_results = self._run_fts_query(
            base_queryset, query.query_text, first_stage_top_k
        )
        _logger.debug("FTS-only: arm returned %d results", len(text_results))

        results = [
            VectorSearchResult(
                annotation=ann,
                similarity_score=getattr(ann, "text_rank", 1.0),
            )
            for ann in text_results
        ]

        reranked = self._apply_rerank(
            results, query.query_text, query.similarity_top_k, reranker
        )
        return self._attach_block_context_sync(reranked, self.user_id)

    @staticmethod
    def _fuse_results(
        vector_results: list,
        text_results: list,
        top_k: int,
    ) -> list[VectorSearchResult]:
        """Merge vector and full-text search results via Reciprocal Rank Fusion.

        Handles three cases:
        - Both arms have results: fuse with RRF
        - Only one arm has results: return that arm's results (up to *top_k*)
        - Neither arm has results: return empty list

        Args:
            vector_results: Annotation instances from vector similarity search,
                each expected to have a ``similarity_score`` attribute.
            text_results: Annotation instances from full-text search,
                each expected to have a ``text_rank`` attribute.
            top_k: Maximum number of results to return.

        Returns:
            List of :class:`VectorSearchResult` with fused scores.
        """
        if vector_results and text_results:
            fused = reciprocal_rank_fusion(
                vector_results,
                text_results,
                top_n=top_k,
            )
            _logger.info(
                f"Hybrid search: fused {len(vector_results)} vector + "
                f"{len(text_results)} text -> {len(fused)} results"
            )
            return [
                VectorSearchResult(annotation=ann, similarity_score=score)
                for ann, score in fused
            ]
        elif vector_results:
            # Trim from oversample_k down to the final top_k requested
            # by the caller (search_by_embedding already fetched oversample_k).
            return [
                VectorSearchResult(
                    annotation=ann,
                    similarity_score=getattr(ann, "similarity_score", 1.0),
                )
                for ann in vector_results[:top_k]
            ]
        elif text_results:
            return [
                VectorSearchResult(
                    annotation=ann,
                    similarity_score=getattr(ann, "text_rank", 1.0),
                )
                for ann in text_results[:top_k]
            ]
        else:
            _logger.warning("Hybrid search: no results from either arm")
            return []

    @staticmethod
    def _run_fts_query(queryset, query_text: str, oversample_k: int) -> list:
        """Execute the full-text search arm of hybrid/fts search (sync).

        Args:
            queryset: Base annotation queryset (already filtered).
            query_text: User query string for full-text matching.
            oversample_k: Number of results to retrieve before fusion.

        Returns:
            List of Annotation instances annotated with ``text_rank``.
        """
        from django.contrib.postgres.search import SearchQuery, SearchRank

        search_query = SearchQuery(query_text, config=FTS_CONFIG)
        text_qs = (
            queryset.filter(search_vector=search_query)
            .annotate(text_rank=SearchRank("search_vector", search_query))
            .order_by("-text_rank")[:oversample_k]
        )
        return list(text_qs)

    def hybrid_search(self, query: VectorSearchQuery) -> list[VectorSearchResult]:
        """Execute a hybrid search combining vector similarity and full-text search.

        Uses Reciprocal Rank Fusion (RRF) to merge results from:
        1. Vector similarity search (via HNSW index)
        2. Full-text search (via GIN index on search_vector)

        Falls back to vector-only search when no query text is available,
        or to text-only search when no embedding can be generated.

        This is a sync-only method (calls ``async_to_sync`` internally).
        From async contexts, use ``async_hybrid_search()`` instead.

        Args:
            query: The search query containing text/embedding and filters

        Returns:
            List of search results with annotations and RRF-fused scores
        """
        if _is_async_context():
            _logger.warning(
                "Sync method called from async context - this may cause issues"
            )

        reranker = self._get_reranker()
        # When a reranker is active, fusion returns oversampled candidates so
        # the reranker has more signal to work with; otherwise fuse straight
        # to the final top_k.
        fusion_top_k = self._effective_first_stage_top_k(
            query.similarity_top_k, reranker
        )

        # Build base queryset with filters
        queryset = async_to_sync(self._build_base_queryset)()
        queryset = self._apply_metadata_filters(queryset, query.filters)

        # RRF oversample applies to each arm *before* fusion. The oversample
        # factors compound intentionally when a reranker is active:
        # ``fusion_top_k`` is already ``top_k * RERANK_OVERSAMPLE_FACTOR`` so
        # each arm fetches ``top_k * RERANK_OVERSAMPLE_FACTOR *
        # HYBRID_SEARCH_OVERSAMPLE_FACTOR`` candidates. Compounding keeps the
        # pool rich enough that RRF + rerank has meaningful choices even
        # after fusion dedupes; bounded overall by ``RERANK_MAX_CANDIDATES``
        # on the reranker side.
        oversample_k = fusion_top_k * HYBRID_SEARCH_OVERSAMPLE_FACTOR

        # --- Vector search arm ---
        vector = query.query_embedding
        if vector is None and query.query_text is not None:
            vector = self._generate_query_embedding(query.query_text)

        vector_results: list = []
        if vector is not None and len(vector) in VALID_EMBEDDING_DIMS:
            vector_results = queryset.search_by_embedding(
                query_vector=vector,
                embedder_path=self.embedder_path,
                top_k=oversample_k,
            )
            _logger.debug(f"Hybrid: vector arm returned {len(vector_results)} results")

        # --- Full-text search arm ---
        text_results: list = []
        if query.query_text:
            text_results = self._run_fts_query(queryset, query.query_text, oversample_k)
            _logger.debug(f"Hybrid: full-text arm returned {len(text_results)} results")

        fused = self._fuse_results(vector_results, text_results, fusion_top_k)
        reranked = self._apply_rerank(
            fused, query.query_text, query.similarity_top_k, reranker
        )
        return self._attach_block_context_sync(reranked, self.user_id)

    async def async_hybrid_search(
        self, query: VectorSearchQuery
    ) -> list[VectorSearchResult]:
        """Async-native hybrid search combining vector similarity and full-text search.

        Uses Reciprocal Rank Fusion (RRF) to merge results from:
        1. Vector similarity search (via HNSW index)
        2. Full-text search (via GIN index on search_vector)

        Falls back to vector-only search when no query text is available,
        or to text-only search when no embedding can be generated.

        Unlike ``hybrid_search()`` which wraps async calls via
        ``async_to_sync``, this method ``await``s async operations directly,
        avoiding nested sync->async->sync event-loop issues.

        Args:
            query: The search query containing text/embedding and filters

        Returns:
            List of search results with annotations and RRF-fused scores
        """
        # `_get_reranker` resolves the default reranker via
        # `PipelineSettings.get_instance()`, which opens `transaction.atomic()`
        # — a sync Django ORM call. From an async tool path this raises
        # `SynchronousOnlyOperation`, which pydantic-ai swallows and turns
        # into an empty `ASYNC_FINISH`. Run the lookup in a thread.
        reranker = await sync_to_async(self._get_reranker, thread_sensitive=True)()
        fusion_top_k = self._effective_first_stage_top_k(
            query.similarity_top_k, reranker
        )

        # Build base queryset (natively async)
        queryset = await self._build_base_queryset()
        queryset = self._apply_metadata_filters(queryset, query.filters)

        oversample_k = fusion_top_k * HYBRID_SEARCH_OVERSAMPLE_FACTOR

        # --- Vector search arm ---
        vector = query.query_embedding
        if vector is None and query.query_text is not None:
            vector = await self._agenerate_query_embedding(query.query_text)

        vector_results: list = []
        if vector is not None and len(vector) in VALID_EMBEDDING_DIMS:
            # Lambda captures are safe here: the lambda is immediately awaited,
            # so captured variables (queryset, vector, etc.) cannot change
            # between capture and execution.
            vector_results = await sync_to_async(
                lambda: queryset.search_by_embedding(
                    query_vector=vector,
                    embedder_path=self.embedder_path,
                    top_k=oversample_k,
                )
            )()
            _logger.debug(f"Hybrid: vector arm returned {len(vector_results)} results")

        # --- Full-text search arm ---
        text_results: list = []
        if query.query_text:
            text_results = await sync_to_async(self._run_fts_query)(
                queryset, query.query_text, oversample_k
            )
            _logger.debug(f"Hybrid: full-text arm returned {len(text_results)} results")

        fused = self._fuse_results(vector_results, text_results, fusion_top_k)
        reranked = await self._aapply_rerank(
            fused, query.query_text, query.similarity_top_k, reranker
        )
        return await self._aattach_block_context(reranked)

    @classmethod
    def global_search(
        cls,
        user_id: Union[str, int],
        query_text: str,
        top_k: int = 100,
        modalities: Optional[list[str]] = None,
        mode: SearchMode = "hybrid",
    ) -> list["VectorSearchResult"]:
        """
        Search across ALL documents the user has access to using DEFAULT_EMBEDDER.

        This method enables global cross-corpus search by using the default embedder
        embeddings that are created for every annotation (as part of the dual embedding
        strategy).

        PERMISSION MODEL (follows consolidated_permissioning_guide.md):
        - Uses Document.objects.visible_to_user(user) for document access control
        - Structural annotations are always visible if document is accessible
        - Non-structural annotations follow: visible if public OR owned by user
        - Corpus permissions are respected via document visibility

        Args:
            user_id: ID of the user performing the search
            query_text: The text query to search for
            top_k: Maximum number of results to return
            modalities: Optional filter by content modalities (e.g., ["TEXT"], ["IMAGE"])
            mode: Retrieval mode — ``"vector"``, ``"fts"``, or ``"hybrid"``
                (default). ``"hybrid"`` fuses pgvector + ``tsvector`` arms via
                Reciprocal Rank Fusion. ``"fts"`` requires non-empty
                ``query_text``; ``"hybrid"`` degrades to vector-only when text is
                missing and to text-only when embedding generation fails.

        Returns:
            List of VectorSearchResult with annotations and similarity scores
        """
        from opencontractserver.documents.models import Document
        from opencontractserver.pipeline.utils import (
            get_default_embedder_path,
            get_default_reranker_instance,
        )

        # ----- Pass 1: degrade fts/hybrid → vector when no query_text. -----
        has_text = bool(query_text and query_text.strip())
        effective_mode: SearchMode = cls._degrade_mode(mode, has_text, "global_search")

        _logger.info(
            "Global search for user %s (mode=%s): '%s...'",
            user_id,
            effective_mode,
            (query_text or "")[:50],
        )

        # Resolve global reranker (if configured) so we know how much to
        # oversample from the first-stage retrieval.
        reranker = get_default_reranker_instance()
        if reranker is not None:
            first_stage_top_k = max(
                top_k, min(top_k * RERANK_OVERSAMPLE_FACTOR, RERANK_MAX_CANDIDATES)
            )
        else:
            first_stage_top_k = top_k

        default_embedder_path = get_default_embedder_path()

        # Get all documents visible to user using the canonical visible_to_user pattern
        # This respects document permissions, is_public flag, and corpus membership
        user = User.objects.get(id=user_id)
        accessible_doc_ids = list(
            Document.objects.visible_to_user(user)
            .filter(is_current=True)
            .values_list("id", flat=True)
        )

        if not accessible_doc_ids:
            _logger.info("User has no accessible documents for global search")
            return []

        _logger.debug(
            f"User {user_id} has access to {len(accessible_doc_ids)} documents"
        )

        # Build annotation queryset - filter to accessible documents
        # This implicitly respects corpus permissions since Document.visible_to_user
        # already considers corpus membership and permissions
        base_queryset = Annotation.objects.select_related(
            "annotation_label", "document", "corpus"
        ).filter(
            Q(document_id__in=accessible_doc_ids)
            | Q(
                structural=True,
                structural_set__documents__in=accessible_doc_ids,
            )
        )

        # Apply visibility rules per consolidated_permissioning_guide.md:
        # - Structural annotations: ALWAYS visible if document is readable (READ-ONLY)
        # - Non-structural annotations: visible if public OR owned by user
        visibility_q = (
            Q(structural=True)
            | Q(structural=False, creator_id=user_id)
            | Q(structural=False, is_public=True)
        )
        base_queryset = base_queryset.filter(visibility_q)

        # Apply modality filter if specified
        if modalities:
            modality_q = Q()
            for modality in modalities:
                modality_q |= Q(content_modalities__contains=[modality])
            base_queryset = base_queryset.filter(modality_q)

        # ----- Pass 2: generate embedding for the vector arm. -----
        # Helper returns the post-degradation mode (hybrid → fts on embedder
        # failure) so the only mutation of ``effective_mode`` lives at this
        # single call site.
        query_vector: Optional[list[float]] = None
        if effective_mode in ("vector", "hybrid"):
            effective_mode, query_vector = cls._generate_global_query_vector(
                effective_mode, query_text, default_embedder_path
            )
            # Vector-only with no embedding has nothing to fall back to.
            if effective_mode == "vector" and query_vector is None:
                return []

        # ``oversample_k`` is computed after the embedding pass so it reflects
        # the FINAL ``effective_mode`` (hybrid can demote to fts when the
        # embedder is unavailable). Otherwise the FTS arm would silently
        # over-fetch ``first_stage_top_k * HYBRID_SEARCH_OVERSAMPLE_FACTOR``
        # rows after a demotion.
        oversample_k = (
            first_stage_top_k * HYBRID_SEARCH_OVERSAMPLE_FACTOR
            if effective_mode == "hybrid"
            else first_stage_top_k
        )

        # --- Vector arm. ---
        vector_results: list = []
        if effective_mode in ("vector", "hybrid") and query_vector is not None:
            vector_results = list(
                base_queryset.search_by_embedding(
                    query_vector=query_vector,
                    embedder_path=default_embedder_path,
                    top_k=oversample_k,
                )
            )
            _logger.debug(
                "Global search vector arm returned %d results", len(vector_results)
            )

        # --- FTS arm. ---
        text_results: list = []
        if effective_mode in ("fts", "hybrid") and has_text:
            text_results = cls._run_fts_query(base_queryset, query_text, oversample_k)
            _logger.debug(
                "Global search FTS arm returned %d results", len(text_results)
            )

        # --- Combine. ---
        if effective_mode == "hybrid":
            results = cls._fuse_results(vector_results, text_results, first_stage_top_k)
        elif effective_mode == "fts":
            # ``text_results`` is bounded by ``oversample_k`` which equals
            # ``first_stage_top_k`` in fts mode, so the slice is a defensive
            # guard rather than active truncation — kept so a future change
            # to ``oversample_k`` can't accidentally bleed extra rows through.
            results = [
                VectorSearchResult(
                    annotation=ann,
                    similarity_score=getattr(ann, "text_rank", 1.0),
                )
                for ann in text_results[:first_stage_top_k]
            ]
        else:  # vector
            results = []
            for annotation in vector_results[:first_stage_top_k]:
                similarity_score = getattr(annotation, "similarity_score", 1.0)
                if similarity_score != similarity_score:  # NaN check
                    similarity_score = 1.0
                results.append(
                    VectorSearchResult(
                        annotation=annotation, similarity_score=similarity_score
                    )
                )

        _logger.info(
            "Global search returned %d results (mode=%s)",
            len(results),
            effective_mode,
        )

        # Second-stage reranking (opt-in via PipelineSettings.default_reranker).
        # Applied uniformly across all modes so vector/fts/hybrid go through
        # the same rerank → attach-block-context pipeline.
        reranked = cls._rerank_results(results, query_text, top_k, reranker)
        # Block-context attach is independent of the per-instance store
        # state, so the classmethod path can call the @staticmethod helper
        # directly. Pass user_id so the helper's mechanical visibility
        # gate uses the same user as the global_search permission filter.
        return cls._attach_block_context_sync(reranked, user_id)

    @classmethod
    async def async_global_search(
        cls,
        user_id: Union[str, int],
        query_text: str,
        top_k: int = 100,
        modalities: Optional[list[str]] = None,
        mode: SearchMode = "hybrid",
    ) -> list["VectorSearchResult"]:
        """
        Async version of global_search.

        Search across ALL documents the user has access to using DEFAULT_EMBEDDER.

        Args:
            user_id: ID of the user performing the search
            query_text: The text query to search for
            top_k: Maximum number of results to return
            modalities: Optional filter by content modalities
            mode: Retrieval mode — see :meth:`global_search`.

        Returns:
            List of VectorSearchResult with annotations and similarity scores
        """
        # Wrap sync method for async context
        return await sync_to_async(cls.global_search)(
            user_id=user_id,
            query_text=query_text,
            top_k=top_k,
            modalities=modalities,
            mode=mode,
        )

    async def async_search(self, query: VectorSearchQuery) -> list[VectorSearchResult]:
        """Async search dispatching on ``query.mode``.

        Modes:
            - ``"hybrid"`` (default): RRF fusion of vector + full-text arms
              via :meth:`async_hybrid_search`. Mirrors the sync
              ``resolve_semantic_search`` resolver behaviour so callers going
              through ``async_search`` get the same hybrid benefit.
            - ``"vector"``: pgvector cosine similarity only.
            - ``"fts"``: PostgreSQL full-text search only.

        Args:
            query: The search query containing text/embedding, filters, and mode.

        Returns:
            List of search results with annotations and similarity scores.
        """
        mode = self._resolve_mode(query)
        # DEBUG (not INFO): fires on every search call; reserve INFO for
        # state transitions and configuration events.
        _logger.debug("CoreAnnotationVectorStore.async_search mode=%s", mode)
        if mode == "hybrid":
            return await self.async_hybrid_search(query)
        if mode == "fts":
            return await self._async_fts_only(query)
        return await self._async_vector_only(query)

    async def _async_vector_only(
        self, query: VectorSearchQuery
    ) -> list[VectorSearchResult]:
        """Vector-only async search path (pgvector cosine similarity)."""
        # See `async_hybrid_search` above — `_get_reranker` opens a sync DB
        # transaction via `PipelineSettings.get_instance()` and must be
        # awaited through `sync_to_async` from an async context.
        reranker = await sync_to_async(self._get_reranker, thread_sensitive=True)()
        first_stage_top_k = self._effective_first_stage_top_k(
            query.similarity_top_k, reranker
        )

        # Build base queryset with filters
        base_queryset = await self._build_base_queryset()

        # Apply metadata filters
        base_queryset = self._apply_metadata_filters(base_queryset, query.filters)

        # Determine the query vector
        vector = query.query_embedding
        if vector is None and query.query_text is not None:
            vector = await self._agenerate_query_embedding(query.query_text)

        # ``search_by_embedding`` materialises results into a list while the
        # fallback branch keeps a sliced QuerySet. The downstream code accepts
        # either via the safe queryset helpers.
        queryset: Union[AnnotationQuerySet, list[Any]]

        # Perform vector search if we have a valid embedding
        if vector is not None and len(vector) in VALID_EMBEDDING_DIMS:
            _logger.debug(f"Using vector search with dimension: {len(vector)}")
            _logger.debug(
                f"Performing vector search with embedder: {self.embedder_path}"
            )

            # search_by_embedding is a sync method that materializes the queryset
            # Wrap it with sync_to_async to make it safe for async contexts
            queryset = await sync_to_async(
                lambda: base_queryset.search_by_embedding(
                    query_vector=vector,
                    embedder_path=self.embedder_path,
                    top_k=first_stage_top_k,
                )
            )()
            _logger.debug(await _safe_queryset_info(queryset, "After vector search"))
        else:
            # Fallback to standard filtering with limit
            if vector is None:
                _logger.debug(
                    "No vector available for search, using standard filtering"
                )
            else:
                _logger.warning(
                    f"Invalid vector dimension: {len(vector)}, using standard filtering"
                )

            queryset = base_queryset[:first_stage_top_k]
            _logger.debug(await _safe_queryset_info(queryset, "After limiting results"))

        # Execute query and convert to results
        _logger.debug("Fetching annotations from database")
        annotations = await _safe_execute_queryset(queryset)
        _logger.debug(f"Retrieved {len(annotations)} annotations")

        # Convert to result objects
        results = []
        for annotation in annotations:
            similarity_score = getattr(annotation, "similarity_score", 1.0)
            # Handle NaN values (can occur when annotations lack computed similarity)
            if similarity_score != similarity_score:  # NaN check (NaN != NaN is True)
                similarity_score = 1.0
            results.append(
                VectorSearchResult(
                    annotation=annotation, similarity_score=similarity_score
                )
            )

        # _aapply_rerank is still called so it can trim to top_k; it short-
        # circuits on empty query_text without invoking the reranker.
        reranked = await self._aapply_rerank(
            results, query.query_text, query.similarity_top_k, reranker
        )
        return await self._aattach_block_context(reranked)

    async def _async_fts_only(
        self, query: VectorSearchQuery
    ) -> list[VectorSearchResult]:
        """Full-text-only async search path (PostgreSQL ``tsvector`` ranking).

        Caller is expected to have ensured ``query.query_text`` is non-empty
        (see :meth:`_resolve_mode`); otherwise this returns an empty list.
        """
        if not (query.query_text and query.query_text.strip()):
            return []

        reranker = await sync_to_async(self._get_reranker, thread_sensitive=True)()
        first_stage_top_k = self._effective_first_stage_top_k(
            query.similarity_top_k, reranker
        )

        base_queryset = await self._build_base_queryset()
        base_queryset = self._apply_metadata_filters(base_queryset, query.filters)

        text_results = await sync_to_async(CoreAnnotationVectorStore._run_fts_query)(
            base_queryset, query.query_text, first_stage_top_k
        )
        _logger.debug("FTS-only async: arm returned %d results", len(text_results))

        results = [
            VectorSearchResult(
                annotation=ann,
                similarity_score=getattr(ann, "text_rank", 1.0),
            )
            for ann in text_results
        ]

        reranked = await self._aapply_rerank(
            results, query.query_text, query.similarity_top_k, reranker
        )
        return await self._aattach_block_context(reranked)


# Re-exported so downstream callers can annotate against the protocol.
__all__ = [
    "CoreAnnotationVectorStore",
    "SearchMode",
    "VectorSearchQuery",
    "VectorSearchResult",
    "VectorStoreProtocol",
]
