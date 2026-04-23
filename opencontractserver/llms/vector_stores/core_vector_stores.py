"""Core vector store functionality independent of any specific agent framework."""

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Optional, Union

from asgiref.sync import async_to_sync, sync_to_async
from django.contrib.auth import get_user_model
from django.db.models import Q, QuerySet

from opencontractserver.annotations.models import Annotation
from opencontractserver.constants.search import (
    FTS_CONFIG,
    HYBRID_SEARCH_OVERSAMPLE_FACTOR,
    RERANK_MAX_CANDIDATES,
    RERANK_OVERSAMPLE_FACTOR,
    VALID_EMBEDDING_DIMS,
)
from opencontractserver.pipeline.base.reranker import (
    BaseReranker,
    safe_arerank,
    safe_rerank,
)
from opencontractserver.utils.embeddings import (
    agenerate_embeddings_from_text,
    generate_embeddings_from_text,
    get_embedder,
)
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
        return await sync_to_async(list)(queryset)
    else:
        return list(queryset)


@dataclass
class VectorSearchQuery:
    """Framework-agnostic vector search query."""

    query_text: Optional[str] = None
    query_embedding: Optional[list[float]] = None
    similarity_top_k: int = 100
    filters: Optional[dict[str, Any]] = None


@dataclass
class VectorSearchResult:
    """Framework-agnostic vector search result."""

    annotation: Annotation
    similarity_score: float = 1.0


class CoreAnnotationVectorStore:
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
        # ------------------------------------------------------------------ #
        # Validation – we need a corpus context unless the caller overrides
        # the embedder explicitly.
        # ------------------------------------------------------------------ #
        if embedder_path is None and corpus_id is None:
            raise ValueError(
                "CoreAnnotationVectorStore requires either 'corpus_id' to "
                "derive an embedder or an explicit 'embedder_path' override."
            )
        self.user_id = user_id
        self.corpus_id = corpus_id
        self.document_id = document_id
        self.must_have_text = must_have_text
        self.embed_dim = embed_dim
        self.only_current_versions = only_current_versions
        self.check_corpus_deletion = check_corpus_deletion
        self.modalities = modalities
        # Caller may inject a specific reranker (useful for tests) or leave
        # it ``None`` to pick up the global ``PipelineSettings.default_reranker``
        # on every search call. Lazy resolution keeps store construction
        # cheap even on the hot path.
        self._reranker_override: Optional[BaseReranker] = reranker
        self.rerank_oversample_factor = max(1, int(rerank_oversample_factor))

        # Auto-detect embedder configuration
        embedder_class, detected_embedder_path = get_embedder(
            corpus_id=corpus_id,
            embedder_path=embedder_path,
        )
        self.embedder_path = detected_embedder_path
        _logger.debug(f"Configured embedder path: {self.embedder_path}")

        # Validate or fallback dimension
        if self.embed_dim not in VALID_EMBEDDING_DIMS:
            self.embed_dim = getattr(embedder_class, "vector_size", 768)

    async def _build_base_queryset(self) -> QuerySet[Annotation]:
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

        # -------------------------------------------------------------------------
        # SECURITY: Verify user has access to requested document/corpus (IDOR prevention)
        # This check ensures callers cannot access annotations from documents/corpuses
        # they don't have permission to view. We use visible_to_user() which returns
        # empty queryset for both "not found" and "no permission" cases to prevent
        # enumeration attacks.
        # -------------------------------------------------------------------------
        from opencontractserver.corpuses.models import Corpus
        from opencontractserver.documents.models import Document

        user = None
        if self.user_id:
            try:
                user = await sync_to_async(User.objects.get)(id=self.user_id)
            except User.DoesNotExist:
                _logger.warning(f"User ID {self.user_id} not found")
                return Annotation.objects.none()

        if self.document_id is not None:
            # Check if user can access this document
            has_access = await sync_to_async(
                lambda: Document.objects.visible_to_user(user)
                .filter(id=self.document_id)
                .exists()
            )()
            if not has_access:
                _logger.warning(
                    f"User {self.user_id} denied access to document {self.document_id} "
                    "in vector search (not found or no permission)"
                )
                return Annotation.objects.none()

        if self.corpus_id is not None:
            # Check if user can access this corpus
            has_access = await sync_to_async(
                lambda: Corpus.objects.visible_to_user(user)
                .filter(id=self.corpus_id)
                .exists()
            )()
            if not has_access:
                _logger.warning(
                    f"User {self.user_id} denied access to corpus {self.corpus_id} "
                    "in vector search (not found or no permission)"
                )
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
            # Note: sync_to_async already imported at module level
            from opencontractserver.documents.models import DocumentPath

            # Get documents with active (non-deleted) paths in corpus
            active_doc_ids = await sync_to_async(
                lambda: list(
                    DocumentPath.objects.filter(
                        corpus_id=self.corpus_id, is_current=True, is_deleted=False
                    ).values_list("document_id", flat=True)
                )
            )()

            if active_doc_ids:
                # Ensure we only search documents with active paths
                active_filters &= Q(document_id__in=active_doc_ids)
                _logger.debug(f"Found {len(active_doc_ids)} active documents in corpus")
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
            document = await sync_to_async(
                lambda: Document.objects.select_related(
                    "structural_annotation_set"
                ).get(pk=self.document_id)
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
            # a) Structural (their Annotation.corpus_id might be null, included by nature)
            # b) Non-structural AND directly linked to this corpus via Annotation.corpus_id.
            active_filters &= Q(structural=True) | Q(
                structural=False, corpus_id=self.corpus_id
            )

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
        self, queryset: QuerySet[Annotation], filters: Optional[dict[str, Any]]
    ) -> QuerySet[Annotation]:
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

    def _generate_query_embedding(self, query_text: str) -> Optional[list[float]]:
        """Generate embeddings from query text synchronously."""
        _logger.debug(f"Generating embeddings from query string: '{query_text}'")
        _logger.debug(f"Using embedder path: {self.embedder_path}")

        embedder_path, vector = generate_embeddings_from_text(
            query_text,
            embedder_path=self.embedder_path,
        )

        _logger.debug(f"Generated embeddings using embedder: {embedder_path}")
        if vector is not None:
            _logger.debug(f"Vector dimension: {len(vector)}")
        else:
            _logger.warning("Failed to generate embeddings - vector is None")

        return vector

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

    def _apply_rerank(
        self,
        results: list["VectorSearchResult"],
        query_text: Optional[str],
        top_k: int,
        reranker: Optional[BaseReranker],
    ) -> list["VectorSearchResult"]:
        """Apply the reranker (sync) if configured; otherwise trim to ``top_k``."""
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

    async def _agenerate_query_embedding(
        self, query_text: str
    ) -> Optional[list[float]]:
        """Generate embeddings from query text asynchronously."""
        _logger.debug(f"Async generating embeddings from query string: '{query_text}'")
        _logger.debug(f"Using embedder path: {self.embedder_path}")

        embedder_path, vector = await agenerate_embeddings_from_text(
            query_text,
            embedder_path=self.embedder_path,
        )

        _logger.debug(f"Generated embeddings using embedder: {embedder_path}")
        if vector is not None:
            _logger.debug(f"Vector dimension: {len(vector)}")
        else:
            _logger.warning("Failed to generate embeddings - vector is None")

        return vector

    def search(self, query: VectorSearchQuery) -> list[VectorSearchResult]:
        """Execute a vector search query and return results.

        When a global reranker is configured (``PipelineSettings.default_reranker``)
        the first-stage retrieval oversamples candidates
        (``top_k * rerank_oversample_factor``) and the reranker re-orders
        them before the final ``top_k`` slice is returned. Reranker failures
        degrade gracefully to the first-stage ordering.

        Args:
            query: The search query containing text/embedding and filters

        Returns:
            List of search results with annotations and similarity scores
        """
        reranker = self._get_reranker()
        first_stage_top_k = self._effective_first_stage_top_k(
            query.similarity_top_k, reranker
        )

        # Build base queryset with filters
        queryset = async_to_sync(self._build_base_queryset)()

        # Apply metadata filters
        queryset = self._apply_metadata_filters(queryset, query.filters)

        # Determine the query vector
        vector = query.query_embedding
        if vector is None and query.query_text is not None:
            vector = self._generate_query_embedding(query.query_text)

        # Perform vector search if we have a valid embedding
        if vector is not None and len(vector) in VALID_EMBEDDING_DIMS:
            _logger.debug(f"Using vector search with dimension: {len(vector)}")
            _logger.debug(
                f"Performing vector search with embedder: {self.embedder_path}"
            )

            queryset = queryset.search_by_embedding(
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

            queryset = queryset[:first_stage_top_k]
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
        return self._apply_rerank(
            results, query.query_text, query.similarity_top_k, reranker
        )

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

    def _run_fts_query(self, queryset, query_text: str, oversample_k: int) -> list:
        """Execute the full-text search arm of hybrid search (sync).

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

        # RRF oversample applies to each arm *before* fusion; when a reranker
        # is active we scale it further so the pool stays rich.
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
        return self._apply_rerank(
            fused, query.query_text, query.similarity_top_k, reranker
        )

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
        reranker = self._get_reranker()
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
        return await self._aapply_rerank(
            fused, query.query_text, query.similarity_top_k, reranker
        )

    @classmethod
    def global_search(
        cls,
        user_id: Union[str, int],
        query_text: str,
        top_k: int = 100,
        modalities: Optional[list[str]] = None,
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

        Returns:
            List of VectorSearchResult with annotations and similarity scores
        """
        from opencontractserver.documents.models import Document
        from opencontractserver.pipeline.utils import (
            get_default_embedder,
            get_default_embedder_path,
            get_default_reranker_instance,
        )

        _logger.info(f"Global search for user {user_id}: '{query_text[:50]}...'")

        # Resolve global reranker (if configured) so we know how much to
        # oversample from the first-stage vector search.
        reranker = get_default_reranker_instance()
        if reranker is not None:
            first_stage_top_k = max(
                top_k, min(top_k * RERANK_OVERSAMPLE_FACTOR, RERANK_MAX_CANDIDATES)
            )
        else:
            first_stage_top_k = top_k

        # Get default embedder configuration
        default_embedder_path = get_default_embedder_path()
        default_embedder_class = get_default_embedder()

        if not default_embedder_class:
            _logger.error("Could not get default embedder for global search")
            return []

        # Generate query embedding using default embedder
        default_embedder = default_embedder_class()
        query_vector = default_embedder.embed_text(query_text)

        if query_vector is None:
            _logger.warning("Failed to generate query embedding for global search")
            return []

        embed_dim = len(query_vector)
        _logger.debug(
            f"Generated query embedding with dimension {embed_dim} "
            f"using {default_embedder_path}"
        )

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
        queryset = Annotation.objects.select_related(
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
        queryset = queryset.filter(visibility_q)

        # Apply modality filter if specified
        if modalities:
            modality_q = Q()
            for modality in modalities:
                modality_q |= Q(content_modalities__contains=[modality])
            queryset = queryset.filter(modality_q)

        _logger.debug("Global search queryset built, searching by embedding")

        # Perform vector search using DEFAULT_EMBEDDER embeddings.
        # TODO: This path uses vector-only search. Integrate full-text search
        # with RRF fusion (like hybrid_search) for improved result quality.
        queryset = queryset.search_by_embedding(
            query_vector=query_vector,
            embedder_path=default_embedder_path,
            top_k=first_stage_top_k,
        )

        # Execute and convert to results
        annotations = list(queryset)
        _logger.info(f"Global search returned {len(annotations)} annotations")

        results = []
        for annotation in annotations:
            similarity_score = getattr(annotation, "similarity_score", 1.0)
            if similarity_score != similarity_score:  # NaN check
                similarity_score = 1.0
            results.append(
                VectorSearchResult(
                    annotation=annotation, similarity_score=similarity_score
                )
            )

        # Second-stage reranking (opt-in via PipelineSettings.default_reranker).
        if reranker is not None and query_text and results:
            passages = [getattr(r.annotation, "raw_text", "") or "" for r in results]
            rerank_output = safe_rerank(reranker, query_text, passages, top_k=top_k)
            if rerank_output is not None:
                return [
                    VectorSearchResult(
                        annotation=results[r.index].annotation,
                        similarity_score=r.score,
                    )
                    for r in rerank_output
                ]

        return results[:top_k]

    @classmethod
    async def async_global_search(
        cls,
        user_id: Union[str, int],
        query_text: str,
        top_k: int = 100,
        modalities: Optional[list[str]] = None,
    ) -> list["VectorSearchResult"]:
        """
        Async version of global_search.

        Search across ALL documents the user has access to using DEFAULT_EMBEDDER.

        Args:
            user_id: ID of the user performing the search
            query_text: The text query to search for
            top_k: Maximum number of results to return
            modalities: Optional filter by content modalities

        Returns:
            List of VectorSearchResult with annotations and similarity scores
        """
        # Wrap sync method for async context
        return await sync_to_async(cls.global_search)(
            user_id=user_id,
            query_text=query_text,
            top_k=top_k,
            modalities=modalities,
        )

    async def async_search(self, query: VectorSearchQuery) -> list[VectorSearchResult]:
        """Async version of search that properly handles Django ORM in async context.

        When a text query is provided, delegates to ``async_hybrid_search()``
        which combines vector similarity with full-text search via RRF fusion.
        This mirrors the sync ``resolve_semantic_search`` resolver behaviour
        so callers going through ``async_search`` get the same hybrid benefit.

        Args:
            query: The search query containing text/embedding and filters

        Returns:
            List of search results with annotations and similarity scores
        """
        # Delegate to hybrid search when a text query is present — mirrors
        # the sync GraphQL resolver logic in resolve_semantic_search.
        if query.query_text and query.query_text.strip():
            return await self.async_hybrid_search(query)

        # Vector-only / no-text path: embedding lookup without FTS overhead.
        reranker = self._get_reranker()
        first_stage_top_k = self._effective_first_stage_top_k(
            query.similarity_top_k, reranker
        )

        # Build base queryset with filters
        queryset = await self._build_base_queryset()

        # Apply metadata filters
        queryset = self._apply_metadata_filters(queryset, query.filters)

        # Determine the query vector
        vector = query.query_embedding
        if vector is None and query.query_text is not None:
            vector = await self._agenerate_query_embedding(query.query_text)

        # Perform vector search if we have a valid embedding
        if vector is not None and len(vector) in VALID_EMBEDDING_DIMS:
            _logger.debug(f"Using vector search with dimension: {len(vector)}")
            _logger.debug(
                f"Performing vector search with embedder: {self.embedder_path}"
            )

            # search_by_embedding is a sync method that materializes the queryset
            # Wrap it with sync_to_async to make it safe for async contexts
            queryset = await sync_to_async(
                lambda: queryset.search_by_embedding(
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

            queryset = queryset[:first_stage_top_k]
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

        # Vector-only path has no query_text — reranking is skipped unless
        # the caller separately supplies ``query.query_text`` (handled above).
        return await self._aapply_rerank(
            results, query.query_text, query.similarity_top_k, reranker
        )
