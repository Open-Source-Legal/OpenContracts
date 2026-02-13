"""PydanticAI-specific vector store implementations."""

import logging
from typing import Any, Optional, Union

from asgiref.sync import sync_to_async
from channels.db import database_sync_to_async
from pydantic import BaseModel
from pydantic_ai.tools import RunContext

from opencontractserver.llms.tools.pydantic_ai_tools import PydanticAIDependencies
from opencontractserver.llms.vector_stores.core_vector_stores import (
    CoreAnnotationVectorStore,
    VectorSearchQuery,
    VectorSearchResult,
)

logger = logging.getLogger(__name__)


class PydanticAIVectorSearchRequest(BaseModel):
    """Pydantic model for vector search requests in PydanticAI context."""

    query_text: Optional[str] = None
    query_embedding: Optional[list[float]] = None
    similarity_top_k: int = 10
    filters: Optional[dict[str, Any]] = None


class PydanticAIVectorSearchResponse(BaseModel):
    """Pydantic model for vector search responses in PydanticAI context."""

    results: list[dict[str, Any]]
    total_results: int

    @classmethod
    def from_core_results(
        cls, results: list[VectorSearchResult]
    ) -> "PydanticAIVectorSearchResponse":
        """Create response from core vector search results.

        Args:
            results: List of VectorSearchResult instances

        Returns:
            PydanticAIVectorSearchResponse instance
        """
        formatted_results = []
        for result in results:
            formatted_result = {
                "annotation_id": result.annotation.id,
                "content": result.annotation.raw_text,
                "document_id": result.annotation.document_id,
                "corpus_id": result.annotation.corpus_id,
                "page": result.annotation.page,
                "annotation_label": (
                    result.annotation.annotation_label.text
                    if result.annotation.annotation_label
                    else None
                ),
                "label": (
                    result.annotation.annotation_label.text
                    if result.annotation.annotation_label
                    else None
                ),
                "label_id": (
                    result.annotation.annotation_label.id
                    if result.annotation.annotation_label
                    else None
                ),
                "json": result.annotation.json,
                "bounding_box": result.annotation.bounding_box,
                "similarity_score": result.similarity_score,
            }
            formatted_results.append(formatted_result)

        return cls(results=formatted_results, total_results=len(formatted_results))

    @classmethod
    async def async_from_core_results(
        cls, results: list[VectorSearchResult]
    ) -> "PydanticAIVectorSearchResponse":
        """Async version that safely accesses Django model attributes.

        Args:
            results: List of VectorSearchResult instances

        Returns:
            PydanticAIVectorSearchResponse instance
        """

        @database_sync_to_async
        def extract_annotation_data(annotation) -> dict[str, Any]:
            """Extract annotation data safely in async context."""
            return {
                "annotation_id": annotation.id,
                "content": annotation.raw_text,
                "document_id": annotation.document_id,
                "corpus_id": annotation.corpus_id,
                "page": annotation.page,
                "annotation_label": (
                    annotation.annotation_label.text
                    if annotation.annotation_label
                    else None
                ),
                "label": (
                    annotation.annotation_label.text
                    if annotation.annotation_label
                    else None
                ),
                "label_id": (
                    annotation.annotation_label.id
                    if annotation.annotation_label
                    else None
                ),
                "json": annotation.json,
                "bounding_box": annotation.bounding_box,
            }

        formatted_results = []
        for result in results:
            annotation_data = await extract_annotation_data(result.annotation)
            annotation_data["similarity_score"] = result.similarity_score
            formatted_results.append(annotation_data)

        return cls(results=formatted_results, total_results=len(formatted_results))


class PydanticAIAnnotationVectorStore:
    """PydanticAI-compatible wrapper for CoreAnnotationVectorStore.

    This class adapts the core vector store functionality for use with PydanticAI
    agents, providing async methods and proper type hints.
    """

    def __init__(
        self,
        user_id: Optional[Union[str, int]] = None,
        corpus_id: Optional[Union[str, int]] = None,
        document_id: Optional[Union[str, int]] = None,
        embedder_path: Optional[str] = None,
        must_have_text: Optional[str] = None,
        embed_dim: int = 384,
        modalities: Optional[list[str]] = None,
        **kwargs,
    ):
        """Initialize the PydanticAI vector store wrapper.

        Args:
            user_id: Filter by user ID
            corpus_id: Filter by corpus ID
            document_id: Filter by document ID
            embedder_path: Path to embedder model to use
            must_have_text: Filter by text content
            embed_dim: Embedding dimension (384, 768, 1536, or 3072)
            modalities: Filter by content modalities (e.g., ["TEXT"], ["IMAGE"],
                       ["TEXT", "IMAGE"]). With multimodal embedders, all embeddings
                       are in the same vector space so cross-modal search is possible.
            **kwargs: Additional arguments passed to core store
        """
        self.core_store = CoreAnnotationVectorStore(
            user_id=user_id,
            corpus_id=corpus_id,
            document_id=document_id,
            embedder_path=embedder_path,
            must_have_text=must_have_text,
            embed_dim=embed_dim,
            modalities=modalities,
        )

        # Store initialization parameters for tool use
        self.user_id = user_id
        self.corpus_id = corpus_id
        self.document_id = document_id
        self.embedder_path = embedder_path
        self.modalities = modalities

    async def search_annotations(
        self,
        query_text: Optional[str] = None,
        query_embedding: Optional[list[float]] = None,
        similarity_top_k: int = 10,
        filters: Optional[dict[str, Any]] = None,
    ) -> PydanticAIVectorSearchResponse:
        """Search annotations using vector similarity.

        Args:
            query_text: Text query for semantic search
            query_embedding: Pre-computed embedding vector
            similarity_top_k: Maximum number of results to return
            filters: Additional metadata filters

        Returns:
            PydanticAIVectorSearchResponse with search results
        """
        logger.debug(
            f"PydanticAI vector search: query_text='{query_text}', top_k={similarity_top_k}"
        )

        # Create search query
        search_query = VectorSearchQuery(
            query_text=query_text,
            query_embedding=query_embedding,
            similarity_top_k=similarity_top_k,
            filters=filters,
        )

        # Execute search using core store's async method
        results = await self.core_store.async_search(search_query)

        logger.debug(f"Found {len(results)} annotations")

        # Convert to PydanticAI response format using async method
        return await PydanticAIVectorSearchResponse.async_from_core_results(results)

    def search_sync(
        self,
        query_text: Optional[str] = None,
        query_embedding: Optional[list[float]] = None,
        similarity_top_k: int = 10,
        filters: Optional[dict[str, Any]] = None,
    ) -> PydanticAIVectorSearchResponse:
        """Synchronous search method for backward compatibility.

        Args:
            query_text: Text query for semantic search
            query_embedding: Pre-computed embedding vector
            similarity_top_k: Maximum number of results to return
            filters: Additional metadata filters

        Returns:
            PydanticAIVectorSearchResponse with search results
        """
        # Create search query
        search_query = VectorSearchQuery(
            query_text=query_text,
            query_embedding=query_embedding,
            similarity_top_k=similarity_top_k,
            filters=filters,
        )

        # Execute search using core store
        results = self.core_store.search(search_query)

        # Convert to PydanticAI response format
        return PydanticAIVectorSearchResponse.from_core_results(results)

    # ------------------------------------------------------------------
    # Compatibility: implement the minimal protocol expected by
    # VectorStoreSearchTool (pydantic-ai built-in).
    # ------------------------------------------------------------------

    async def similarity_search(
        self,
        query: str,
        *,
        k: int = 8,
        modalities: Optional[list[str]] = None,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        """Async wrapper that adapts to pydantic-ai's expected signature.

        VectorStoreSearchTool looks for a coroutine / function
        `vector_store.similarity_search(query, k=…)` and returns a raw list
        of dicts.  We delegate to ``search_annotations`` and then expose the
        list of hits so that the tool can feed them directly to the model
        (and propagate them to ``result.sources``).

        With multimodal embedders (CLIP), all embeddings are in the same vector
        space, so text queries can find image annotations and vice versa.

        Args:
            query: Text query for semantic search
            k: Maximum number of results to return (default 8)
            modalities: Optional filter by content type: ["TEXT"], ["IMAGE"], or
                       ["TEXT", "IMAGE"]. If not provided, searches all modalities.
        """
        # If modalities filter provided, create a temporary store with that filter
        if modalities is not None:
            temp_store = CoreAnnotationVectorStore(
                user_id=self.user_id,
                corpus_id=self.corpus_id,
                document_id=self.document_id,
                embedder_path=self.embedder_path,
                embed_dim=self.core_store.embed_dim,
                modalities=modalities,
            )
            search_query = VectorSearchQuery(
                query_text=query,
                similarity_top_k=k,
            )
            results = await temp_store.async_search(search_query)
            return (
                await PydanticAIVectorSearchResponse.async_from_core_results(results)
            ).results

        # Use the default store
        response = await self.search_annotations(query_text=query, similarity_top_k=k)
        return response.results

    def get_store_info(self) -> dict[str, Any]:
        """Get information about the vector store configuration.

        Returns:
            Dictionary with store configuration details
        """
        return {
            "user_id": self.user_id,
            "corpus_id": self.corpus_id,
            "document_id": self.document_id,
            "embedder_path": self.embedder_path,
            "embed_dim": self.core_store.embed_dim,
            "modalities": self.modalities,
        }

    async def create_vector_search_tool(self) -> callable:
        """Create a PydanticAI-compatible tool function for vector search.

        Returns:
            Async function that can be used as a PydanticAI tool
        """

        async def vector_search_tool(
            ctx: RunContext[PydanticAIDependencies],  # Updated annotation
            query_text: str,
            similarity_top_k: int = 10,
            filters: Optional[dict[str, Any]] = None,
        ) -> dict[str, Any]:
            """Search annotations using vector similarity.

            Args:
                ctx: PydanticAI run context. Provides access to dependencies via ctx.deps.
                query_text: Text query for semantic search
                similarity_top_k: Maximum number of results to return
                filters: Additional metadata filters

            Returns:
                Dictionary containing search results
            """
            response = await self.search_annotations(
                query_text=query_text,
                similarity_top_k=similarity_top_k,
                filters=filters,
            )
            response_dict = response.model_dump()
            # Provide a top-level "sources" key so PydanticAI RunResult exposes .sources
            response_dict["sources"] = response_dict.get("results", [])
            return response_dict

        # Set proper metadata for PydanticAI
        vector_search_tool.__name__ = "vector_search"
        vector_search_tool.__doc__ = (
            "Search document annotations using vector similarity"
        )

        return vector_search_tool

    def __repr__(self) -> str:
        """String representation of the vector store."""
        return (
            f"PydanticAIAnnotationVectorStore("
            f"document_id={self.document_id}, "
            f"corpus_id={self.corpus_id}, "
            f"user_id={self.user_id})"
        )


# Convenience function for creating PydanticAI vector search tools
async def create_vector_search_tool(
    user_id: Optional[Union[str, int]] = None,
    corpus_id: Optional[Union[str, int]] = None,
    document_id: Optional[Union[str, int]] = None,
    embedder_path: Optional[str] = None,
    modalities: Optional[list[str]] = None,
    **kwargs,
) -> callable:
    """Create a vector search tool for PydanticAI agents.

    Args:
        user_id: Filter by user ID
        corpus_id: Filter by corpus ID
        document_id: Filter by document ID
        embedder_path: Path to embedder model to use
        modalities: Filter by content modalities (e.g., ["TEXT"], ["IMAGE"],
                   ["TEXT", "IMAGE"]). With multimodal embedders (CLIP), all
                   embeddings are in the same vector space for cross-modal search.
        **kwargs: Additional arguments

    Returns:
        Async function that can be used as a PydanticAI tool
    """
    vector_store = await sync_to_async(PydanticAIAnnotationVectorStore)(
        user_id=user_id,
        corpus_id=corpus_id,
        document_id=document_id,
        embedder_path=embedder_path,
        modalities=modalities,
        **kwargs,
    )

    return await vector_store.create_vector_search_tool()


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #


def _bb_value(bb: object | None, key: str):
    """
    Robustly extract a single coordinate from a bounding-box that may be a
    plain dict **or** an object with attributes.
    """
    if bb is None:
        return None
    if isinstance(bb, dict):
        return bb.get(key)
    # Fall-back to attribute access
    return getattr(bb, key, None)
