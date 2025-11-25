"""Core vector store functionality for conversations and messages."""

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Optional, Union

from asgiref.sync import sync_to_async
from django.db.models import QuerySet

from opencontractserver.conversations.models import ChatMessage, Conversation
from opencontractserver.utils.embeddings import (
    agenerate_embeddings_from_text,
    generate_embeddings_from_text,
    get_embedder,
)

_logger = logging.getLogger(__name__)


def _is_async_context() -> bool:
    """Check if we're currently running in an async context."""
    try:
        asyncio.current_task()
        return True
    except RuntimeError:
        return False


async def _safe_queryset_info(queryset: QuerySet, description: str) -> str:
    """Safely log queryset information in both sync and async contexts."""
    try:
        if _is_async_context():
            count = await sync_to_async(queryset.count)()
            return f"{description}: {count} results"
        else:
            return f"{description}: {queryset.count()} results"
    except Exception as e:
        return f"{description}: unable to count results ({e})"


def _safe_queryset_info_sync(queryset: QuerySet, description: str) -> str:
    """Safely log queryset information in sync context only."""
    if _is_async_context():
        return f"{description}: queryset (async context - count not available)"
    else:
        try:
            return f"{description}: {queryset.count()} results"
        except Exception as e:
            return f"{description}: unable to count results ({e})"


async def _safe_execute_queryset(queryset: QuerySet) -> list:
    """Safely execute a queryset in both sync and async contexts."""
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
class ConversationSearchResult:
    """Framework-agnostic conversation search result."""

    conversation: Conversation
    similarity_score: float = 1.0


@dataclass
class MessageSearchResult:
    """Framework-agnostic message search result."""

    message: ChatMessage
    similarity_score: float = 1.0


class CoreConversationVectorStore:
    """Core conversation vector store functionality independent of agent frameworks.

    This class encapsulates the business logic for searching conversations using
    vector embeddings and various filters. It operates directly with Django
    models and can be wrapped by different agent framework adapters.

    Args:
        user_id: Filter by user ID
        corpus_id: Filter by corpus ID
        document_id: Filter by document ID (conversations linked to specific document)
        conversation_type: Filter by conversation type (chat/thread)
        embedder_path: Path to embedder model to use
        embed_dim: Embedding dimension (384, 768, 1536, or 3072)
        exclude_deleted: Whether to exclude soft-deleted conversations
    """

    def __init__(
        self,
        user_id: Union[str, int, None] = None,
        corpus_id: Union[str, int, None] = None,
        document_id: Union[str, int, None] = None,
        conversation_type: Optional[str] = None,
        embedder_path: Optional[str] = None,
        embed_dim: int = 384,
        exclude_deleted: bool = True,
    ):
        # Validation – we need a corpus context unless the caller overrides embedder
        if embedder_path is None and corpus_id is None:
            raise ValueError(
                "CoreConversationVectorStore requires either 'corpus_id' to "
                "derive an embedder or an explicit 'embedder_path' override."
            )

        self.user_id = user_id
        self.corpus_id = corpus_id
        self.document_id = document_id
        self.conversation_type = conversation_type
        self.embed_dim = embed_dim
        self.exclude_deleted = exclude_deleted

        # Use explicit embedder_path if provided, otherwise auto-detect
        if embedder_path is not None:
            # Trust the explicitly provided embedder_path (useful for testing and overrides)
            self.embedder_path = embedder_path
            _logger.debug(f"Using explicit embedder path: {self.embedder_path}")
            # Try to get embedder class for dimension validation, but don't override path
            try:
                embedder_class, _ = get_embedder(
                    corpus_id=corpus_id,
                    embedder_path=embedder_path,
                )
            except Exception:
                # If embedder resolution fails (e.g., test mock), use default dimension
                embedder_class = None
        else:
            # Auto-detect embedder from corpus
            embedder_class, detected_embedder_path = get_embedder(
                corpus_id=corpus_id,
                embedder_path=None,
            )
            self.embedder_path = detected_embedder_path
            _logger.debug(f"Auto-detected embedder path: {self.embedder_path}")

        # Validate or fallback dimension
        if self.embed_dim not in [384, 768, 1536, 3072]:
            if embedder_class:
                self.embed_dim = getattr(embedder_class, "vector_size", 768)
            else:
                # Default to 384 if no embedder class available
                self.embed_dim = 384

    def search(self, query: VectorSearchQuery) -> list[ConversationSearchResult]:
        """Synchronous search for conversations."""
        _logger.debug(f"Starting sync conversation search with query: {query}")

        # Get user object for visible_to_user pattern
        from django.contrib.auth import get_user_model

        User = get_user_model()

        user = None
        if self.user_id:
            try:
                user = User.objects.get(id=self.user_id)
            except User.DoesNotExist:
                _logger.warning(f"User ID {self.user_id} not found")
                return []

        # Use standard visible_to_user() pattern for permission filtering
        # This handles: superuser bypass, public conversations, creator conversations,
        # guardian object permissions (explicitly shared), and soft-delete filtering
        queryset = Conversation.objects.visible_to_user(user)

        # Apply additional context filters
        if self.document_id is not None:
            queryset = queryset.filter(chat_with_document_id=self.document_id)
        elif self.corpus_id is not None:
            queryset = queryset.filter(chat_with_corpus_id=self.corpus_id)

        if self.conversation_type:
            queryset = queryset.filter(conversation_type=self.conversation_type)

        # Generate embedding if query text provided
        if query.query_text:
            embedder_path, query_embedding = generate_embeddings_from_text(
                query.query_text, embedder_path=self.embedder_path
            )
            _logger.debug(f"Generated embedding using: {embedder_path}")
        elif query.query_embedding:
            query_embedding = query.query_embedding
        else:
            raise ValueError("Either query_text or query_embedding must be provided")

        # Perform vector search
        results_qs = queryset.search_by_embedding(
            query_vector=query_embedding,
            embedder_path=self.embedder_path,
            top_k=query.similarity_top_k,
        )

        # Note: query.filters cannot be applied here because search_by_embedding
        # returns a sliced queryset, and Django doesn't allow filtering after slicing.
        # All filtering must be done before the vector search operation above.

        # Convert to result objects
        results = [
            ConversationSearchResult(
                conversation=conv,
                similarity_score=getattr(conv, "similarity_score", 1.0),
            )
            for conv in results_qs
        ]

        _logger.info(f"Sync search completed with {len(results)} results")
        return results

    async def async_search(
        self, query: VectorSearchQuery
    ) -> list[ConversationSearchResult]:
        """Asynchronous search for conversations."""
        _logger.debug(f"Starting async conversation search with query: {query}")

        # Get user object for visible_to_user pattern
        from django.contrib.auth import get_user_model

        User = get_user_model()

        user = None
        if self.user_id:
            try:
                user = await sync_to_async(User.objects.get)(id=self.user_id)
            except User.DoesNotExist:
                _logger.warning(f"User ID {self.user_id} not found")
                return []

        # Use standard visible_to_user() pattern (wrapped for async)
        queryset = await sync_to_async(
            lambda: Conversation.objects.visible_to_user(user)
        )()

        # Apply additional context filters
        if self.document_id is not None:
            queryset = queryset.filter(chat_with_document_id=self.document_id)
        elif self.corpus_id is not None:
            queryset = queryset.filter(chat_with_corpus_id=self.corpus_id)

        if self.conversation_type:
            queryset = queryset.filter(conversation_type=self.conversation_type)

        # Generate embedding if query text provided
        if query.query_text:
            embedder_path, query_embedding = await agenerate_embeddings_from_text(
                query.query_text, embedder_path=self.embedder_path
            )
            _logger.debug(f"Generated embedding using: {embedder_path}")
        elif query.query_embedding:
            query_embedding = query.query_embedding
        else:
            raise ValueError("Either query_text or query_embedding must be provided")

        # Perform vector search (sync operation wrapped)
        results_qs = await sync_to_async(
            lambda: queryset.search_by_embedding(
                query_vector=query_embedding,
                embedder_path=self.embedder_path,
                top_k=query.similarity_top_k,
            )
        )()

        # Note: query.filters cannot be applied here because search_by_embedding
        # returns a sliced queryset, and Django doesn't allow filtering after slicing.
        # All filtering must be done before the vector search operation above.

        # Execute queryset and convert to result objects
        conversations = await _safe_execute_queryset(results_qs)
        results = [
            ConversationSearchResult(
                conversation=conv,
                similarity_score=getattr(conv, "similarity_score", 1.0),
            )
            for conv in conversations
        ]

        _logger.info(f"Async search completed with {len(results)} results")
        return results


class CoreChatMessageVectorStore:
    """Core message vector store functionality independent of agent frameworks.

    This class encapsulates the business logic for searching chat messages using
    vector embeddings and various filters. It operates directly with Django
    models and can be wrapped by different agent framework adapters.

    Args:
        user_id: Filter by user ID
        corpus_id: Filter by corpus ID (via conversation's corpus)
        conversation_id: Filter by specific conversation
        msg_type: Filter by message type (HUMAN/LLM/SYSTEM)
        embedder_path: Path to embedder model to use
        embed_dim: Embedding dimension (384, 768, 1536, or 3072)
        exclude_deleted: Whether to exclude soft-deleted messages
    """

    def __init__(
        self,
        user_id: Union[str, int, None] = None,
        corpus_id: Union[str, int, None] = None,
        conversation_id: Union[str, int, None] = None,
        msg_type: Optional[str] = None,
        embedder_path: Optional[str] = None,
        embed_dim: int = 384,
        exclude_deleted: bool = True,
    ):
        # Validation
        if embedder_path is None and corpus_id is None:
            raise ValueError(
                "CoreChatMessageVectorStore requires either 'corpus_id' to "
                "derive an embedder or an explicit 'embedder_path' override."
            )

        self.user_id = user_id
        self.corpus_id = corpus_id
        self.conversation_id = conversation_id
        self.msg_type = msg_type
        self.embed_dim = embed_dim
        self.exclude_deleted = exclude_deleted

        # Use explicit embedder_path if provided, otherwise auto-detect
        if embedder_path is not None:
            # Trust the explicitly provided embedder_path (useful for testing and overrides)
            self.embedder_path = embedder_path
            _logger.debug(f"Using explicit embedder path: {self.embedder_path}")
            # Try to get embedder class for dimension validation, but don't override path
            try:
                embedder_class, _ = get_embedder(
                    corpus_id=corpus_id,
                    embedder_path=embedder_path,
                )
            except Exception:
                # If embedder resolution fails (e.g., test mock), use default dimension
                embedder_class = None
        else:
            # Auto-detect embedder from corpus
            embedder_class, detected_embedder_path = get_embedder(
                corpus_id=corpus_id,
                embedder_path=None,
            )
            self.embedder_path = detected_embedder_path
            _logger.debug(f"Auto-detected embedder path: {self.embedder_path}")

        # Validate or fallback dimension
        if self.embed_dim not in [384, 768, 1536, 3072]:
            if embedder_class:
                self.embed_dim = getattr(embedder_class, "vector_size", 768)
            else:
                # Default to 384 if no embedder class available
                self.embed_dim = 384

    def search(self, query: VectorSearchQuery) -> list[MessageSearchResult]:
        """Synchronous search for messages."""
        _logger.debug(f"Starting sync message search with query: {query}")

        # Get user object for visible_to_user pattern
        from django.contrib.auth import get_user_model

        User = get_user_model()

        user = None
        if self.user_id:
            try:
                user = User.objects.get(id=self.user_id)
            except User.DoesNotExist:
                _logger.warning(f"User ID {self.user_id} not found")
                return []

        # Get visible conversations using standard visible_to_user() pattern
        # This ensures messages are filtered by conversation permissions
        visible_conversations = Conversation.objects.visible_to_user(user)

        # Start with messages in visible conversations only
        queryset = ChatMessage.objects.filter(
            conversation__in=visible_conversations
        ).select_related(
            "conversation",
            "conversation__chat_with_corpus",
            "conversation__chat_with_document",
            "creator",
        )

        # Apply additional context filters
        if self.conversation_id is not None:
            queryset = queryset.filter(conversation_id=self.conversation_id)
        elif self.corpus_id is not None:
            queryset = queryset.filter(conversation__chat_with_corpus_id=self.corpus_id)

        if self.msg_type:
            queryset = queryset.filter(msg_type=self.msg_type)

        # Exclude soft-deleted messages (conversations already filtered by manager)
        if self.exclude_deleted:
            queryset = queryset.filter(deleted_at__isnull=True)

        # Generate embedding if query text provided
        if query.query_text:
            embedder_path, query_embedding = generate_embeddings_from_text(
                query.query_text, embedder_path=self.embedder_path
            )
            _logger.debug(f"Generated embedding using: {embedder_path}")
        elif query.query_embedding:
            query_embedding = query.query_embedding
        else:
            raise ValueError("Either query_text or query_embedding must be provided")

        # Perform vector search
        results_qs = queryset.search_by_embedding(
            query_vector=query_embedding,
            embedder_path=self.embedder_path,
            top_k=query.similarity_top_k,
        )

        # Note: query.filters cannot be applied here because search_by_embedding
        # returns a sliced queryset, and Django doesn't allow filtering after slicing.
        # All filtering must be done before the vector search operation above.

        # Convert to result objects
        results = [
            MessageSearchResult(
                message=msg,
                similarity_score=getattr(msg, "similarity_score", 1.0),
            )
            for msg in results_qs
        ]

        _logger.info(f"Sync search completed with {len(results)} results")
        return results

    async def async_search(self, query: VectorSearchQuery) -> list[MessageSearchResult]:
        """Asynchronous search for messages."""
        _logger.debug(f"Starting async message search with query: {query}")

        # Get user object for visible_to_user pattern
        from django.contrib.auth import get_user_model

        User = get_user_model()

        user = None
        if self.user_id:
            try:
                user = await sync_to_async(User.objects.get)(id=self.user_id)
            except User.DoesNotExist:
                _logger.warning(f"User ID {self.user_id} not found")
                return []

        # Get visible conversations using standard visible_to_user() pattern (async)
        visible_conversations = await sync_to_async(
            lambda: Conversation.objects.visible_to_user(user)
        )()

        # Start with messages in visible conversations only
        queryset = ChatMessage.objects.filter(
            conversation__in=visible_conversations
        ).select_related(
            "conversation",
            "conversation__chat_with_corpus",
            "conversation__chat_with_document",
            "creator",
        )

        # Apply additional context filters
        if self.conversation_id is not None:
            queryset = queryset.filter(conversation_id=self.conversation_id)
        elif self.corpus_id is not None:
            queryset = queryset.filter(conversation__chat_with_corpus_id=self.corpus_id)

        if self.msg_type:
            queryset = queryset.filter(msg_type=self.msg_type)

        # Exclude soft-deleted messages
        if self.exclude_deleted:
            queryset = queryset.filter(deleted_at__isnull=True)

        # Generate embedding if query text provided
        if query.query_text:
            embedder_path, query_embedding = await agenerate_embeddings_from_text(
                query.query_text, embedder_path=self.embedder_path
            )
            _logger.debug(f"Generated embedding using: {embedder_path}")
        elif query.query_embedding:
            query_embedding = query.query_embedding
        else:
            raise ValueError("Either query_text or query_embedding must be provided")

        # Perform vector search (sync operation wrapped)
        results_qs = await sync_to_async(
            lambda: queryset.search_by_embedding(
                query_vector=query_embedding,
                embedder_path=self.embedder_path,
                top_k=query.similarity_top_k,
            )
        )()

        # Note: query.filters cannot be applied here because search_by_embedding
        # returns a sliced queryset, and Django doesn't allow filtering after slicing.
        # All filtering must be done before the vector search operation above.

        # Execute queryset and convert to result objects
        messages = await _safe_execute_queryset(results_qs)
        results = [
            MessageSearchResult(
                message=msg,
                similarity_score=getattr(msg, "similarity_score", 1.0),
            )
            for msg in messages
        ]

        _logger.info(f"Async search completed with {len(results)} results")
        return results
