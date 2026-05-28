"""
Elegant top-level API for OpenContracts LLM framework.

This module provides a simple interface for creating document or corpus agents.
"""

import logging
from typing import Any, Callable, Literal, Optional, TypeVar, Union, cast

from django.conf import settings

from opencontractserver.conversations.models import ChatMessage, Conversation
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.llms.agents.agent_factory import UnifiedAgentFactory
from opencontractserver.llms.agents.core_agents import CoreAgent
from opencontractserver.llms.tools.tool_factory import CoreTool, create_document_tools
from opencontractserver.llms.types import AgentFramework
from opencontractserver.llms.vector_stores.vector_store_factory import (
    UnifiedVectorStoreFactory,
)
from opencontractserver.utils.embeddings import generate_embeddings_from_text

logger = logging.getLogger(__name__)

# Type aliases for cleaner API
FrameworkType = Union[AgentFramework, Literal["pydantic_ai"]]
DocumentType = Union[str, int, Document]
CorpusType = Union[str, int, Corpus]
ToolType = Union[str, CoreTool, Callable[..., Any]]

# Type variable for structured responses
T = TypeVar("T")


class AgentAPI:
    """Simple API for creating document and corpus agents."""

    @staticmethod
    async def for_document(
        document: DocumentType,
        corpus: Optional[CorpusType] = None,
        *,
        framework: Optional[FrameworkType] = None,
        user_id: Optional[int] = None,
        model: Optional[str] = None,
        agent_preferred_llm: Optional[str] = None,
        system_prompt: Optional[str] = None,
        conversation: Optional[Conversation] = None,
        conversation_id: Optional[int] = None,
        messages: Optional[list[ChatMessage]] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        streaming: bool = True,
        tools: Optional[list[ToolType]] = None,
        embedder: Optional[str] = None,
        verbose: bool = False,
        persist: Optional[bool] = None,
        **kwargs,
    ) -> CoreAgent:
        """
        Create a document agent with minimal configuration.

        Args:
            document: Document ID, instance, or path
            framework: "pydantic_ai"
            user_id: User ID for message attribution (None = anonymous/ephemeral session)
            model: LLM model name (e.g., "gpt-4", "claude-3-sonnet").  Per-call
                override — wins over every persisted default.
            agent_preferred_llm: Per-agent override
                (``AgentConfiguration.preferred_llm``).  Wins over the corpus
                default but loses to a per-call ``model=``.
            system_prompt: Custom system prompt (auto-generated if None)
            conversation: Existing conversation object to continue
            conversation_id: Existing conversation ID to load
            messages: Pre-loaded chat messages
            temperature: Temperature for response generation (0.0-2.0)
            max_tokens: Maximum tokens in response
            streaming: Enable streaming responses
            tools: List of tool names, CoreTool instances, or functions
            embedder: Custom embedder path
            verbose: Enable verbose logging
            persist: Optional persistence flag
            **kwargs: Additional framework-specific options

        Returns:
            CoreAgent: Ready-to-use agent implementing the CoreAgent protocol

        Examples:
            # Anonymous conversation (ephemeral, not stored)
            agent = await agents.for_document(123)
            response = await agent.chat("What is this about?")
            # conversation_id will be None - nothing persisted

            # Persistent conversation with user tracking
            agent = await agents.for_document(
                document=my_doc,
                user_id=456,  # Required for persistence
                conversation_id=789,  # Continue existing conversation
                framework="pydantic_ai"
            )

            # Continue persistent conversation later
            conversation_id = agent.get_conversation_id()  # Real ID if user_id provided
            new_agent = await agents.for_document(123, user_id=456, conversation_id=conversation_id)

            # With custom configuration
            agent = await agents.for_document(
                document=my_doc,
                framework="pydantic_ai",
                model="gpt-4",
                temperature=0.3,
                system_prompt="You are a legal expert...",
                tools=["summarize", "extract_entities"],
                user_id=456  # Include for persistence
            )
        """
        # Resolve default framework if caller did not specify one
        resolved_framework = _resolve_framework(framework)

        # Convert tool names to CoreTool instances
        # ``_resolve_tools`` returns ``list[CoreTool]``; the factory parameter
        # is the wider ``list[Union[CoreTool, Callable, str]]`` so it can also
        # accept un-resolved tool spec lists from other callers. ``list`` is
        # invariant in the type system, so we cast through the wider alias.
        resolved_tools: Optional[list[Union[CoreTool, Callable[..., Any], str]]] = (
            cast(
                "list[Union[CoreTool, Callable[..., Any], str]]",
                _resolve_tools(tools),
            )
            if tools
            else None
        )

        # If caller explicitly disabled persistence we propagate the flags via **kwargs
        persistence_overrides: dict[str, Any] = {}
        if persist is False:
            persistence_overrides = {
                "store_user_messages": False,
                "store_llm_messages": False,
            }

        return await UnifiedAgentFactory.create_document_agent(
            document,
            corpus,
            framework=resolved_framework,
            user_id=user_id,
            conversation=conversation,
            conversation_id=conversation_id,
            loaded_messages=messages,
            model=model,
            agent_preferred_llm=agent_preferred_llm,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            streaming=streaming,
            embedder_path=embedder,
            tools=resolved_tools,
            verbose=verbose,
            **persistence_overrides,
            **kwargs,
        )

    @staticmethod
    async def for_corpus(
        corpus: Union[str, int, Corpus],
        *,
        framework: Optional[FrameworkType] = None,
        user_id: Optional[int] = None,
        model: Optional[str] = None,
        agent_preferred_llm: Optional[str] = None,
        system_prompt: Optional[str] = None,
        conversation: Optional[Conversation] = None,
        conversation_id: Optional[int] = None,
        messages: Optional[list[ChatMessage]] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        streaming: bool = True,
        tools: Optional[list[ToolType]] = None,
        embedder: Optional[str] = None,
        verbose: bool = False,
        persist: Optional[bool] = None,
        **kwargs,
    ) -> CoreAgent:
        """
        Create a corpus agent with minimal configuration.

        Args:
            corpus_id: Corpus ID
            framework: "pydantic_ai"
            user_id: User ID for message attribution (None = anonymous/ephemeral session)
            model: LLM model name (e.g., "gpt-4", "claude-3-sonnet").  Per-call
                override — wins over every persisted default.
            agent_preferred_llm: Per-agent override
                (``AgentConfiguration.preferred_llm``).  Wins over the corpus
                default but loses to a per-call ``model=``.
            system_prompt: Custom system prompt (auto-generated if None)
            conversation: Existing conversation object to continue
            conversation_id: Existing conversation ID to load
            messages: Pre-loaded chat messages
            temperature: Temperature for response generation (0.0-2.0)
            max_tokens: Maximum tokens in response
            streaming: Enable streaming responses
            tools: List of tool names, CoreTool instances, or functions
            embedder: Custom embedder path (uses corpus default if None)
            verbose: Enable verbose logging
            persist: Optional persistence flag
            **kwargs: Additional framework-specific options

        Returns:
            CoreAgent: Ready-to-use agent implementing the CoreAgent protocol

        Examples:
            # Anonymous conversation (ephemeral, not stored)
            agent = await agents.for_corpus(456)
            response = await agent.chat("What are the key themes?")
            # conversation_id will be None - nothing persisted

            # Persistent conversation with user tracking
            agent = await agents.for_corpus(
                corpus=456,
                user_id=123,  # Required for persistence
                conversation_id=789  # Continue existing conversation
            )

            # Continue persistent conversation later
            conversation_id = agent.get_conversation_id()  # Real ID if user_id provided
            new_agent = await agents.for_corpus(456, user_id=123, conversation_id=conversation_id)

            # With streaming and custom model
            agent = await agents.for_corpus(
                corpus_id=456,
                framework="pydantic_ai",
                model="claude-3-sonnet",
                temperature=0.5,
                streaming=True,
                user_id=123  # Include for persistence
            )
            async for chunk in agent.stream("Summarize findings"):
                print(chunk.content, end="")
        """
        # Resolve default framework if caller did not specify one
        resolved_framework = _resolve_framework(
            framework, setting_name="LLMS_CORPUS_AGENT_FRAMEWORK"
        )

        # Convert tool names to CoreTool instances
        # ``_resolve_tools`` returns ``list[CoreTool]``; the factory parameter
        # is the wider ``list[Union[CoreTool, Callable, str]]`` so it can also
        # accept un-resolved tool spec lists from other callers. ``list`` is
        # invariant in the type system, so we cast through the wider alias.
        resolved_tools: Optional[list[Union[CoreTool, Callable[..., Any], str]]] = (
            cast(
                "list[Union[CoreTool, Callable[..., Any], str]]",
                _resolve_tools(tools),
            )
            if tools
            else None
        )

        # If caller explicitly disabled persistence we propagate the flags via **kwargs
        persistence_overrides: dict[str, Any] = {}
        if persist is False:
            persistence_overrides = {
                "store_user_messages": False,
                "store_llm_messages": False,
            }

        return await UnifiedAgentFactory.create_corpus_agent(
            corpus,
            framework=resolved_framework,
            user_id=user_id,
            conversation=conversation,
            conversation_id=conversation_id,
            loaded_messages=messages,
            model=model,
            agent_preferred_llm=agent_preferred_llm,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            streaming=streaming,
            embedder_path=embedder,
            tools=resolved_tools,
            verbose=verbose,
            **persistence_overrides,
            **kwargs,
        )

    @staticmethod
    async def get_structured_response_from_document(
        document: DocumentType,
        corpus: Optional[CorpusType],
        prompt: str,
        target_type: type[T],
        *,
        framework: Optional[FrameworkType] = None,
        user_id: Optional[int] = None,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        tools: Optional[list[ToolType]] = None,
        embedder: Optional[str] = None,
        **kwargs,
    ) -> Optional[T]:
        """
        Extract structured data from a document in a one-shot, ephemeral manner.

        This method creates a temporary agent, performs the extraction, and returns
        the result without storing any conversation history.

        Args:
            document: Document ID, instance, or path
            corpus: Corpus ID, instance, or path (optional - None for documents not in a corpus)
            prompt: Natural language prompt for data extraction
            target_type: Python type for the desired output (e.g., int, str, list[str], MyPydanticModel)
            framework: "pydantic_ai" (defaults to pydantic_ai for structured extraction)
            user_id: User ID (not used for persistence in this method)
            model: LLM model name (e.g., "gpt-4", "claude-3-sonnet")
            temperature: Temperature for response generation (0.0-2.0)
            max_tokens: Maximum tokens in response
            tools: List of tools to use during extraction
            embedder: Custom embedder path
            **kwargs: Additional framework-specific options

        Returns:
            Instance of target_type if successful, None if extraction failed

        Examples:
            # Extract a simple type
            page_count = await agents.get_structured_response_from_document(
                document=123,
                corpus=456,
                prompt="How many pages are in this document?",
                target_type=int
            )

            # Extract a list
            parties = await agents.get_structured_response_from_document(
                document=doc,
                corpus=corpus,
                prompt="List all parties mentioned in this contract",
                target_type=list[str]
            )

            # Extract structured data using Pydantic
            from pydantic import BaseModel

            class ContractTerms(BaseModel):
                start_date: str
                end_date: str
                total_value: float
                parties: list[str]

            terms = await agents.get_structured_response_from_document(
                document=doc,
                corpus=corpus,
                prompt="Extract the key contract terms",
                target_type=ContractTerms,
                model="gpt-4",
                temperature=0.3
            )
        """
        # Default to pydantic_ai for structured extraction
        if framework is None:
            framework = AgentFramework.PYDANTIC_AI

        # Create ephemeral agent with persistence disabled
        agent = await AgentAPI.for_document(
            document=document,
            corpus=corpus,
            framework=framework,
            user_id=user_id,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            streaming=False,  # No streaming for structured responses
            tools=tools,
            embedder=embedder,
            persist=False,  # Ensure no persistence
            **kwargs,
        )

        # Use the structured_response method
        return await agent.structured_response(
            prompt=prompt,
            target_type=target_type,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )

    @staticmethod
    async def get_structured_response_and_sources_from_document(
        document: DocumentType,
        corpus: Optional[CorpusType],
        prompt: str,
        target_type: type[T],
        *,
        framework: Optional[FrameworkType] = None,
        user_id: Optional[int] = None,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        tools: Optional[list[ToolType]] = None,
        embedder: Optional[str] = None,
        **kwargs,
    ) -> tuple[Optional[T], list[int]]:
        """Like :meth:`get_structured_response_from_document`, plus citations.

        Returns a tuple of ``(result, annotation_ids)`` where
        ``annotation_ids`` is the deduplicated list of real Annotation PKs
        that the agent's retrieval tools (similarity_search, …) returned
        during this run.  Callers use the IDs to populate M2M source links
        on the owning object (``Datacell.sources`` for extraction,
        ``ChatMessage.source_annotations`` for chat).

        Synthetic / negative IDs produced by ad-hoc match tools are filtered
        out inside the retrieval tools themselves.
        """
        if framework is None:
            framework = AgentFramework.PYDANTIC_AI

        # Config-time kwargs (vector store / agent construction) belong on
        # ``for_document``; ``structured_response`` only accepts run-time
        # kwargs (filtered through its own allowlist), so don't double-pass.
        config_only_keys = {"similarity_top_k"}
        run_kwargs = {k: v for k, v in kwargs.items() if k not in config_only_keys}

        agent = await AgentAPI.for_document(
            document=document,
            corpus=corpus,
            framework=framework,
            user_id=user_id,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            streaming=False,
            tools=tools,
            embedder=embedder,
            persist=False,
            **kwargs,
        )

        result = await agent.structured_response(
            prompt=prompt,
            target_type=target_type,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            **run_kwargs,
        )

        # The tool implementations appended to this list during the run.
        # Dedupe while preserving order of first occurrence so the most
        # relevant (earliest retrieved) citations come first.
        agent_deps = getattr(agent, "agent_deps", None)
        raw_ids = getattr(agent_deps, "retrieved_annotation_ids", []) or []
        seen: set[int] = set()
        annotation_ids: list[int] = []
        for aid in raw_ids:
            if isinstance(aid, int) and aid > 0 and aid not in seen:
                seen.add(aid)
                annotation_ids.append(aid)

        return result, annotation_ids

    @staticmethod
    async def get_structured_response_from_corpus(
        corpus: CorpusType,
        prompt: str,
        target_type: type[T],
        *,
        framework: Optional[FrameworkType] = None,
        user_id: Optional[int] = None,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        tools: Optional[list[ToolType]] = None,
        embedder: Optional[str] = None,
        **kwargs,
    ) -> Optional[T]:
        """
        Extract structured data from a corpus in a one-shot, ephemeral manner.

        This method creates a temporary agent, performs the extraction, and returns
        the result without storing any conversation history.

        Args:
            corpus: Corpus ID, instance, or path
            prompt: Natural language prompt for data extraction
            target_type: Python type for the desired output (e.g., int, str, list[str], MyPydanticModel)
            framework: "pydantic_ai" (defaults to pydantic_ai for structured extraction)
            user_id: User ID (not used for persistence in this method)
            model: LLM model name (e.g., "gpt-4", "claude-3-sonnet")
            temperature: Temperature for response generation (0.0-2.0)
            max_tokens: Maximum tokens in response
            tools: List of tools to use during extraction
            embedder: Custom embedder path
            **kwargs: Additional framework-specific options

        Returns:
            Instance of target_type if successful, None if extraction failed

        Examples:
            # Extract a count across documents
            doc_count = await agents.get_structured_response_from_corpus(
                corpus=456,
                prompt="How many documents contain confidentiality clauses?",
                target_type=int
            )

            # Extract a summary structure
            from pydantic import BaseModel

            class CorpusSummary(BaseModel):
                main_themes: list[str]
                document_count: int
                key_entities: list[str]
                date_range: dict[str, str]

            summary = await agents.get_structured_response_from_corpus(
                corpus=corpus,
                prompt="Provide a comprehensive summary of this corpus",
                target_type=CorpusSummary,
                model="gpt-4",
                temperature=0.5
            )
        """
        # Default to pydantic_ai for structured extraction
        if framework is None:
            framework = AgentFramework.PYDANTIC_AI

        # Create ephemeral agent with persistence disabled
        agent = await AgentAPI.for_corpus(
            corpus=corpus,
            framework=framework,
            user_id=user_id,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            streaming=False,  # No streaming for structured responses
            tools=tools,
            embedder=embedder,
            persist=False,  # Ensure no persistence
            **kwargs,
        )

        # Use the structured_response method
        return await agent.structured_response(
            prompt=prompt,
            target_type=target_type,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,  # Pass through any additional kwargs like extra_context
        )


class EmbeddingAPI:
    """Simple API for generating embeddings."""

    @staticmethod
    def generate(
        text: str,
        *,
        corpus_id: Optional[int] = None,
        mimetype: Optional[str] = None,
        embedder: Optional[str] = None,
    ) -> tuple[Optional[str], Optional[list[float]]]:
        """
        Generate embeddings for text using the OpenContracts pipeline.

        Args:
            text: Text to embed
            corpus_id: Optional corpus ID for context-specific embedding
            mimetype: Optional mimetype for context
            embedder: Optional custom embedder path

        Returns:
            Tuple of (embedder_path, embedding_vector)

        Examples:
            # Simple embedding
            embedder_path, vector = embeddings.generate("Hello world")

            # With corpus context
            embedder_path, vector = embeddings.generate(
                "Legal document text",
                corpus_id=123,
                mimetype="application/pdf"
            )
        """
        return generate_embeddings_from_text(
            text=text, corpus_id=corpus_id, mimetype=mimetype, embedder_path=embedder
        )


class ToolAPI:
    """Simple API for working with tools."""

    @staticmethod
    def document_tools() -> list[CoreTool]:
        """Get standard document-related tools."""
        return create_document_tools()

    @staticmethod
    def from_function(
        func: Callable[..., Any],
        *,
        name: Optional[str] = None,
        description: Optional[str] = None,
        parameter_descriptions: Optional[dict[str, str]] = None,
    ) -> CoreTool:
        """
        Create a CoreTool from a Python function.

        Args:
            func: Python function to wrap
            name: Optional custom name
            description: Optional custom description
            parameter_descriptions: Optional parameter descriptions

        Returns:
            CoreTool instance

        Examples:
            def my_tool(query: str) -> str:
                '''Search for information.'''
                return f"Results for: {query}"

            tool = tools.from_function(my_tool)
        """
        return CoreTool.from_function(
            func=func,
            name=name,
            description=description,
            parameter_descriptions=parameter_descriptions,
        )


class VectorStoreAPI:
    """Simple API for working with vector stores."""

    @staticmethod
    def create(
        *,
        framework: Optional[FrameworkType] = None,
        user_id: Optional[Union[str, int]] = None,
        corpus_id: Optional[Union[str, int]] = None,
        document_id: Optional[Union[str, int]] = None,
        embedder_path: Optional[str] = None,
        must_have_text: Optional[str] = None,
        embed_dim: int = 384,
        **kwargs,
    ) -> Any:
        """
        Create a vector store using the specified framework.

        Args:
            framework: "pydantic_ai"
            user_id: Filter by user ID
            corpus_id: Filter by corpus ID
            document_id: Filter by document ID
            embedder_path: Path to embedder model to use
            must_have_text: Filter by text content
            embed_dim: Embedding dimension to use (384, 768, 1024, 1536, 3072, or 4096)
            **kwargs: Additional framework-specific arguments

        Returns:
            Framework-specific vector store instance

        Examples:
            # Pydantic AI vector store
            store = vector_stores.create("pydantic_ai", corpus_id=123)

            # Pydantic AI vector store
            store = vector_stores.create("pydantic_ai", document_id=456)
        """
        # Resolve default framework if caller did not specify one. Vector
        # stores have their own dedicated setting — the document-agent
        # default would have been a leaky abstraction that surprised
        # operators who wanted to tune the two independently. When the
        # setting is absent ``_resolve_framework`` falls through to
        # ``AgentFramework.PYDANTIC_AI``, the same default the agent paths
        # use, so existing deployments continue to work without a settings
        # change.
        resolved_framework = _resolve_framework(
            framework, setting_name="LLMS_VECTOR_STORE_FRAMEWORK"
        )

        return UnifiedVectorStoreFactory.create_vector_store(
            framework=resolved_framework,
            user_id=user_id,
            corpus_id=corpus_id,
            document_id=document_id,
            embedder_path=embedder_path,
            must_have_text=must_have_text,
            embed_dim=embed_dim,
            **kwargs,
        )


def _resolve_tools(tools: list[ToolType]) -> list[CoreTool]:
    """Convert tool specifications to CoreTool instances.

    String names are resolved via :class:`ToolFunctionRegistry`, which is
    the single source of truth for tool name -> function mapping.
    """
    from opencontractserver.llms.tools.tool_registry import ToolFunctionRegistry

    registry = ToolFunctionRegistry.get()
    resolved: list[CoreTool] = []

    for tool in tools:
        if isinstance(tool, str):
            core_tool = registry.to_core_tool(tool)
            if core_tool is not None:
                resolved.append(core_tool)
            else:
                logger.warning("Unknown tool: %s", tool)
        elif isinstance(tool, CoreTool):
            resolved.append(tool)
        elif callable(tool):
            resolved.append(CoreTool.from_function(tool))
        else:
            logger.warning("Invalid tool specification: %s", tool)

    return resolved


def _resolve_framework(
    framework: Optional[FrameworkType],
    *,
    setting_name: str = "LLMS_DOCUMENT_AGENT_FRAMEWORK",
) -> AgentFramework:
    """Coerce a caller-supplied framework spec into a concrete ``AgentFramework``.

    Accepts ``None`` (falls back to the named Django setting / pydantic-ai
    default), the literal framework name, or an ``AgentFramework`` member.
    """
    resolved: Any = framework
    if resolved is None:
        resolved = getattr(settings, setting_name, AgentFramework.PYDANTIC_AI)
    if isinstance(resolved, str):
        resolved = AgentFramework(resolved)
    if not isinstance(resolved, AgentFramework):
        raise TypeError(
            f"Could not resolve framework {framework!r} to an AgentFramework"
        )
    return resolved


# Create singleton instances for the agent API
agents = AgentAPI()
embeddings = EmbeddingAPI()
tools = ToolAPI()
vector_stores = VectorStoreAPI()
