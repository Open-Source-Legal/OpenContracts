"""Core vector store functionality independent of any specific agent framework."""

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Optional, Union

from asgiref.sync import async_to_sync, sync_to_async
from django.contrib.auth import get_user_model
from django.db.models import Q, QuerySet

from opencontractserver.annotations.models import Annotation
from opencontractserver.utils.embeddings import (
    agenerate_embeddings_from_text,
    generate_embeddings_from_text,
    get_embedder,
)

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

        # Auto-detect embedder configuration
        embedder_class, detected_embedder_path = get_embedder(
            corpus_id=corpus_id,
            embedder_path=embedder_path,
        )
        self.embedder_path = detected_embedder_path
        _logger.debug(f"Configured embedder path: {self.embedder_path}")

        # Validate or fallback dimension
        if self.embed_dim not in [384, 768, 1024, 1536, 2048, 3072, 4096]:
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

        Args:
            query: The search query containing text/embedding and filters

        Returns:
            List of search results with annotations and similarity scores
        """
        # Build base queryset with filters
        queryset = async_to_sync(self._build_base_queryset)()

        # Apply metadata filters
        queryset = self._apply_metadata_filters(queryset, query.filters)

        # Determine the query vector
        vector = query.query_embedding
        if vector is None and query.query_text is not None:
            vector = self._generate_query_embedding(query.query_text)

        # Perform vector search if we have a valid embedding
        if vector is not None and len(vector) in [384, 768, 1536, 3072]:
            _logger.debug(f"Using vector search with dimension: {len(vector)}")
            _logger.debug(
                f"Performing vector search with embedder: {self.embedder_path}"
            )

            queryset = queryset.search_by_embedding(
                query_vector=vector,
                embedder_path=self.embedder_path,
                top_k=query.similarity_top_k,
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

            queryset = queryset[: query.similarity_top_k]
            _logger.debug(_safe_queryset_info_sync(queryset, "After limiting results"))

        # Execute query and convert to results
        _logger.debug("Fetching annotations from database")

        # Safe queryset execution for both sync and async contexts
        if _is_async_context():
            _logger.warning(
                "Sync method called from async context - this may cause issues"
            )
            # For now, we'll try the sync approach and let it fail gracefully
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
                f"[CoreAnnotationVectorStore.search] Vector store returned {len(annotations)} annotations for query."
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

        return results

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
        )

        _logger.info(f"Global search for user {user_id}: '{query_text[:50]}...'")

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

        # Perform vector search using DEFAULT_EMBEDDER embeddings
        queryset = queryset.search_by_embedding(
            query_vector=query_vector,
            embedder_path=default_embedder_path,
            top_k=top_k,
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

        return results

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

        Args:
            query: The search query containing text/embedding and filters

        Returns:
            List of search results with annotations and similarity scores
        """
        # Build base queryset with filters
        queryset = await self._build_base_queryset()

        # Apply metadata filters
        queryset = self._apply_metadata_filters(queryset, query.filters)

        # Determine the query vector
        vector = query.query_embedding
        if vector is None and query.query_text is not None:
            vector = await self._agenerate_query_embedding(query.query_text)

        # Perform vector search if we have a valid embedding
        if vector is not None and len(vector) in [384, 768, 1536, 3072]:
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
                    top_k=query.similarity_top_k,
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

            queryset = queryset[: query.similarity_top_k]
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

        return results
