"""PydanticAI-specific vector store implementations for conversations and messages."""

import logging
from typing import Any, Optional, Union

from channels.db import database_sync_to_async
from pydantic import BaseModel
from pydantic_ai.tools import RunContext

from opencontractserver.llms.tools.pydantic_ai_tools import PydanticAIDependencies
from opencontractserver.llms.vector_stores.core_conversation_vector_stores import (
    ConversationSearchResult,
    CoreChatMessageVectorStore,
    CoreConversationVectorStore,
    MessageSearchResult,
    VectorSearchQuery,
)

logger = logging.getLogger(__name__)


class PydanticAIConversationSearchRequest(BaseModel):
    """Pydantic model for conversation search requests in PydanticAI context."""

    query_text: Optional[str] = None
    query_embedding: Optional[list[float]] = None
    similarity_top_k: int = 10
    filters: Optional[dict[str, Any]] = None


class PydanticAIConversationSearchResponse(BaseModel):
    """Pydantic model for conversation search responses in PydanticAI context."""

    results: list[dict[str, Any]]
    total_results: int

    @classmethod
    async def async_from_core_results(
        cls, results: list[ConversationSearchResult]
    ) -> "PydanticAIConversationSearchResponse":
        """Create response from core conversation search results.

        Args:
            results: List of ConversationSearchResult instances

        Returns:
            PydanticAIConversationSearchResponse instance
        """

        @database_sync_to_async
        def extract_conversation_data(conversation) -> dict[str, Any]:
            """Extract conversation data safely in async context."""
            return {
                "conversation_id": conversation.id,
                "title": conversation.title,
                "description": conversation.description,
                "conversation_type": conversation.conversation_type,
                "corpus_id": (
                    conversation.chat_with_corpus_id
                    if conversation.chat_with_corpus
                    else None
                ),
                "document_id": (
                    conversation.chat_with_document_id
                    if conversation.chat_with_document
                    else None
                ),
                "creator_id": conversation.creator_id if conversation.creator else None,
                "is_public": conversation.is_public,
                "is_locked": conversation.is_locked,
                "is_pinned": conversation.is_pinned,
                "created_at": (
                    conversation.created_at.isoformat()
                    if conversation.created_at
                    else None
                ),
                "updated_at": (
                    conversation.updated_at.isoformat()
                    if conversation.updated_at
                    else None
                ),
            }

        formatted_results = []
        for result in results:
            conversation_data = await extract_conversation_data(result.conversation)
            conversation_data["similarity_score"] = result.similarity_score
            formatted_results.append(conversation_data)

        return cls(results=formatted_results, total_results=len(formatted_results))


class PydanticAIMessageSearchRequest(BaseModel):
    """Pydantic model for message search requests in PydanticAI context."""

    query_text: Optional[str] = None
    query_embedding: Optional[list[float]] = None
    similarity_top_k: int = 10
    filters: Optional[dict[str, Any]] = None


class PydanticAIMessageSearchResponse(BaseModel):
    """Pydantic model for message search responses in PydanticAI context."""

    results: list[dict[str, Any]]
    total_results: int

    @classmethod
    async def async_from_core_results(
        cls, results: list[MessageSearchResult]
    ) -> "PydanticAIMessageSearchResponse":
        """Create response from core message search results.

        Args:
            results: List of MessageSearchResult instances

        Returns:
            PydanticAIMessageSearchResponse instance
        """

        @database_sync_to_async
        def extract_message_data(message) -> dict[str, Any]:
            """Extract message data safely in async context."""
            return {
                "message_id": message.id,
                "conversation_id": message.conversation_id,
                "content": message.content,
                "msg_type": message.msg_type,
                "agent_type": message.agent_type,
                "creator_id": message.creator_id if message.creator else None,
                "state": message.state,
                "upvote_count": message.upvote_count,
                "downvote_count": message.downvote_count,
                "created_at": (
                    message.created_at.isoformat() if message.created_at else None
                ),
            }

        formatted_results = []
        for result in results:
            message_data = await extract_message_data(result.message)
            message_data["similarity_score"] = result.similarity_score
            formatted_results.append(message_data)

        return cls(results=formatted_results, total_results=len(formatted_results))


class PydanticAIConversationVectorStore:
    """PydanticAI-compatible wrapper for CoreConversationVectorStore.

    This class adapts the core conversation vector store functionality for use with
    PydanticAI agents, providing async methods and proper type hints.
    """

    def __init__(
        self,
        user_id: Optional[Union[str, int]] = None,
        corpus_id: Optional[Union[str, int]] = None,
        document_id: Optional[Union[str, int]] = None,
        conversation_type: Optional[str] = None,
        embedder_path: Optional[str] = None,
        embed_dim: int = 384,
        exclude_deleted: bool = True,
        **kwargs,
    ):
        """Initialize the PydanticAI conversation vector store wrapper.

        Args:
            user_id: Filter by user ID
            corpus_id: Filter by corpus ID
            document_id: Filter by document ID
            conversation_type: Filter by conversation type (chat/thread)
            embedder_path: Path to embedder model
            embed_dim: Embedding dimension
            exclude_deleted: Whether to exclude soft-deleted conversations
        """
        self.core_store = CoreConversationVectorStore(
            user_id=user_id,
            corpus_id=corpus_id,
            document_id=document_id,
            conversation_type=conversation_type,
            embedder_path=embedder_path,
            embed_dim=embed_dim,
            exclude_deleted=exclude_deleted,
        )

    async def search_conversations(
        self,
        query_text: Optional[str] = None,
        query_embedding: Optional[list[float]] = None,
        similarity_top_k: int = 10,
        filters: Optional[dict[str, Any]] = None,
    ) -> PydanticAIConversationSearchResponse:
        """Search for conversations using vector similarity.

        Args:
            query_text: Text to search for (will be embedded)
            query_embedding: Pre-computed embedding vector
            similarity_top_k: Number of results to return
            filters: Additional filters to apply

        Returns:
            PydanticAIConversationSearchResponse with results
        """
        query = VectorSearchQuery(
            query_text=query_text,
            query_embedding=query_embedding,
            similarity_top_k=similarity_top_k,
            filters=filters,
        )

        # Perform async search
        results = await self.core_store.async_search(query)

        # Convert to Pydantic response
        return await PydanticAIConversationSearchResponse.async_from_core_results(
            results
        )


class PydanticAIChatMessageVectorStore:
    """PydanticAI-compatible wrapper for CoreChatMessageVectorStore.

    This class adapts the core message vector store functionality for use with
    PydanticAI agents, providing async methods and proper type hints.
    """

    def __init__(
        self,
        user_id: Optional[Union[str, int]] = None,
        corpus_id: Optional[Union[str, int]] = None,
        conversation_id: Optional[Union[str, int]] = None,
        msg_type: Optional[str] = None,
        embedder_path: Optional[str] = None,
        embed_dim: int = 384,
        exclude_deleted: bool = True,
        **kwargs,
    ):
        """Initialize the PydanticAI message vector store wrapper.

        Args:
            user_id: Filter by user ID
            corpus_id: Filter by corpus ID
            conversation_id: Filter by conversation ID
            msg_type: Filter by message type (HUMAN/LLM/SYSTEM)
            embedder_path: Path to embedder model
            embed_dim: Embedding dimension
            exclude_deleted: Whether to exclude soft-deleted messages
        """
        self.core_store = CoreChatMessageVectorStore(
            user_id=user_id,
            corpus_id=corpus_id,
            conversation_id=conversation_id,
            msg_type=msg_type,
            embedder_path=embedder_path,
            embed_dim=embed_dim,
            exclude_deleted=exclude_deleted,
        )

    async def search_messages(
        self,
        query_text: Optional[str] = None,
        query_embedding: Optional[list[float]] = None,
        similarity_top_k: int = 10,
        filters: Optional[dict[str, Any]] = None,
    ) -> PydanticAIMessageSearchResponse:
        """Search for messages using vector similarity.

        Args:
            query_text: Text to search for (will be embedded)
            query_embedding: Pre-computed embedding vector
            similarity_top_k: Number of results to return
            filters: Additional filters to apply

        Returns:
            PydanticAIMessageSearchResponse with results
        """
        query = VectorSearchQuery(
            query_text=query_text,
            query_embedding=query_embedding,
            similarity_top_k=similarity_top_k,
            filters=filters,
        )

        # Perform async search
        results = await self.core_store.async_search(query)

        # Convert to Pydantic response
        return await PydanticAIMessageSearchResponse.async_from_core_results(results)


# Tool creation helpers for PydanticAI agents


async def create_conversation_search_tool(
    user_id: Union[str, int],
    corpus_id: Optional[Union[str, int]] = None,
    document_id: Optional[Union[str, int]] = None,
    conversation_type: Optional[str] = None,
    embed_dim: int = 384,
):
    """Create a conversation search tool for PydanticAI agents.

    Args:
        user_id: User performing the search
        corpus_id: Optional corpus to filter by
        document_id: Optional document to filter by
        conversation_type: Optional conversation type to filter by (chat/thread)
        embed_dim: Embedding dimension to use

    Returns:
        Async function that can be used as a PydanticAI tool
    """
    vector_store = PydanticAIConversationVectorStore(
        user_id=user_id,
        corpus_id=corpus_id,
        document_id=document_id,
        conversation_type=conversation_type,
        embed_dim=embed_dim,
    )

    async def search_conversations(
        ctx: RunContext[PydanticAIDependencies],
        query: str,
        top_k: int = 10,
    ) -> str:
        """Search for relevant conversations based on a query.

        Args:
            ctx: PydanticAI run context
            query: The search query
            top_k: Number of results to return

        Returns:
            Formatted string with search results
        """
        results = await vector_store.search_conversations(
            query_text=query, similarity_top_k=top_k
        )

        if results.total_results == 0:
            return "No relevant conversations found."

        # Format results as text
        output_lines = [f"Found {results.total_results} relevant conversations:\n"]
        for i, result in enumerate(results.results[:top_k], 1):
            output_lines.append(
                f"{i}. [{result['conversation_type'].upper()}] {result['title'] or 'Untitled'}"
            )
            if result["description"]:
                output_lines.append(f"   Description: {result['description'][:200]}")
            output_lines.append(
                f"   Similarity: {result['similarity_score']:.3f} | ID: {result['conversation_id']}\n"
            )

        return "\n".join(output_lines)

    return search_conversations


async def create_message_search_tool(
    user_id: Union[str, int],
    corpus_id: Optional[Union[str, int]] = None,
    conversation_id: Optional[Union[str, int]] = None,
    embed_dim: int = 384,
):
    """Create a message search tool for PydanticAI agents.

    Args:
        user_id: User performing the search
        corpus_id: Optional corpus to filter by
        conversation_id: Optional conversation to filter by
        embed_dim: Embedding dimension to use

    Returns:
        Async function that can be used as a PydanticAI tool
    """
    vector_store = PydanticAIChatMessageVectorStore(
        user_id=user_id,
        corpus_id=corpus_id,
        conversation_id=conversation_id,
        embed_dim=embed_dim,
    )

    async def search_messages(
        ctx: RunContext[PydanticAIDependencies],
        query: str,
        top_k: int = 10,
    ) -> str:
        """Search for relevant messages based on a query.

        Args:
            ctx: PydanticAI run context
            query: The search query
            top_k: Number of results to return

        Returns:
            Formatted string with search results
        """
        results = await vector_store.search_messages(
            query_text=query, similarity_top_k=top_k
        )

        if results.total_results == 0:
            return "No relevant messages found."

        # Format results as text
        output_lines = [f"Found {results.total_results} relevant messages:\n"]
        for i, result in enumerate(results.results[:top_k], 1):
            content_preview = result["content"][:200]
            if len(result["content"]) > 200:
                content_preview += "..."

            output_lines.append(f"{i}. [{result['msg_type']}] {content_preview}")
            output_lines.append(
                f"   Upvotes: {result['upvote_count']} | Downvotes: {result['downvote_count']}"
            )
            output_lines.append(
                f"   Similarity: {result['similarity_score']:.3f} | Message ID: {result['message_id']}\n"
            )

        return "\n".join(output_lines)

    return search_messages
