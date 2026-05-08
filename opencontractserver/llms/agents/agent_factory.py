"""Unified agent factory that can create agents for different frameworks."""

import logging
from typing import Any, Callable, Optional, Union

from channels.db import database_sync_to_async
from django.conf import settings

from opencontractserver.conversations.models import ChatMessage, Conversation
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.llms.agents.core_agents import (
    CoreAgent,
    _is_public,
    get_default_config,
)
from opencontractserver.llms.tools.tool_factory import (
    CoreTool,
    UnifiedToolFactory,
    build_inject_params_for_context,
)
from opencontractserver.llms.types import AgentFramework
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import user_has_permission_for_obj

logger = logging.getLogger(__name__)


async def _user_has_write_permission(
    user_id: Optional[int],
    resource: Optional[Union[Document, Corpus]],
) -> bool:
    """
    Check if user has WRITE (CRUD) permission on the resource.

    Args:
        user_id: The user's ID, or None for anonymous users
        resource: The Document or Corpus to check permissions on

    Returns:
        True if user has write permission, False otherwise
    """
    if resource is None:
        return False

    if user_id is None:
        # Anonymous users never have write permission
        return False

    from django.contrib.auth import get_user_model

    User = get_user_model()

    try:
        user = await User.objects.aget(pk=user_id)
    except User.DoesNotExist:
        return False

    # Use database_sync_to_async since user_has_permission_for_obj is synchronous
    return await database_sync_to_async(user_has_permission_for_obj)(
        user, resource, PermissionTypes.CRUD
    )


async def _inject_corpus_memory(corpus_obj, config) -> None:
    """Inject corpus memory into the agent's system prompt if available.

    Reads the memory document for the given corpus and appends the
    formatted memory content to ``config.system_prompt``.  Silently
    logs and skips on any failure so agent creation is never blocked.

    Note: ``query=config.system_prompt`` is used as the relevance signal
    for section selection.  The user's actual question would be a better
    signal, but it is not available at factory-creation time.

    **Security / prompt-injection warning**: Memory content is a user-editable
    markdown Document.  Any corpus member can modify it via the UI, which means
    its contents are untrusted user input injected verbatim into the system
    prompt.  This is a prompt-injection vector: a malicious user could craft
    memory entries that override agent behaviour.  The ToggleCorpusMemory
    mutation warns users about this risk.  Future hardening should consider
    sandboxing or sanitising memory content before injection.

    Args:
        corpus_obj: The Corpus instance (must have ``memory_enabled=True``).
        config: The AgentConfig whose ``system_prompt`` will be mutated.
    """
    try:
        from opencontractserver.agents.memory import (
            format_memory_for_prompt,
            get_memory_for_injection,
        )

        memory_content = await get_memory_for_injection(
            corpus_obj, query=config.system_prompt or ""
        )
        if memory_content:
            config.system_prompt = (
                config.system_prompt or ""
            ) + format_memory_for_prompt(memory_content)
    except Exception:
        logger.warning(
            "Failed to inject corpus memory for corpus %s",
            corpus_obj.id,
            exc_info=True,
        )


class UnifiedAgentFactory:
    """Factory that creates agents using different frameworks with a common interface."""

    @staticmethod
    async def create_document_agent(
        document: Union[str, int, Document],
        corpus: Optional[Union[str, int, Corpus]] = None,
        framework: AgentFramework = AgentFramework.PYDANTIC_AI,
        user_id: Optional[int] = None,
        # Enhanced conversation management
        conversation: Optional[Conversation] = None,
        conversation_id: Optional[int] = None,
        loaded_messages: Optional[list[ChatMessage]] = None,
        # Configuration options
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        streaming: Optional[bool] = None,
        embedder_path: Optional[str] = None,
        tools: Optional[list[Union[CoreTool, Callable, str]]] = None,
        store_user_messages: Optional[bool] = None,
        store_llm_messages: Optional[bool] = None,
        # Legacy compatibility
        override_conversation: Optional[Conversation] = None,
        override_system_prompt: Optional[str] = None,
        **kwargs,
    ) -> CoreAgent:
        """Create a document agent using the specified framework.

        Args:
            document: Document ID or instance
            framework: Which agent framework to use
            user_id: Optional user ID for message attribution
            conversation: Optional existing conversation object
            conversation_id: Optional existing conversation ID
            loaded_messages: Optional existing messages to load
            model: Optional model name (e.g., "gpt-4o-mini")
            system_prompt: Optional custom system prompt
            temperature: Optional temperature for response generation
            max_tokens: Optional maximum tokens in response
            streaming: Optional enable/disable streaming
            embedder_path: Optional embedder path
            tools: Optional list of tools (CoreTool instances, functions, or tool names)
            store_user_messages: Optional enable/disable storing user messages
            store_llm_messages: Optional enable/disable storing LLM messages
            override_conversation: Legacy parameter (use 'conversation' instead)
            override_system_prompt: Legacy parameter (use 'system_prompt' instead)
            **kwargs: Additional framework-specific arguments

        Returns:
            CoreAgent: Framework-specific agent implementing the CoreAgent protocol
        """
        # Handle legacy parameter names
        if override_conversation and not conversation:
            conversation = override_conversation
        if override_system_prompt and not system_prompt:
            system_prompt = override_system_prompt

        persistence_flags: dict[str, bool] = {}
        if store_user_messages is not None:
            persistence_flags["store_user_messages"] = store_user_messages
        if store_llm_messages is not None:
            persistence_flags["store_llm_messages"] = store_llm_messages

        # Extract deps-specific kwargs that shouldn't go to AgentConfig
        # These are passed directly to the agent's create method
        deps_kwargs: dict[str, Any] = {}
        if "skip_approval_gate" in kwargs:
            deps_kwargs["skip_approval_gate"] = kwargs.pop("skip_approval_gate")

        # Extract create-specific kwargs that control tool selection mode.
        # restrict_tool_names: when provided, the agent is restricted to ONLY
        # these tool names (plus their runtime-context versions built by the
        # factory).  This prevents tool overload for automated corpus actions.
        create_kwargs: dict[str, Any] = {}
        if "restrict_tool_names" in kwargs:
            create_kwargs["restrict_tool_names"] = kwargs.pop("restrict_tool_names")
        # Back-compat: `restrict_tools=True` without names does nothing useful
        kwargs.pop("restrict_tools", None)

        config = get_default_config(
            user_id=user_id,
            model_name=model or kwargs.get("model_name"),
            system_prompt=system_prompt,
            temperature=temperature or kwargs.get("temperature", 0.7),
            max_tokens=max_tokens,
            streaming=(
                streaming if streaming is not None else kwargs.get("streaming", True)
            ),
            conversation=conversation,
            conversation_id=conversation_id,
            loaded_messages=loaded_messages,
            embedder_path=embedder_path,
            tools=tools or [],
            **persistence_flags,
            **kwargs,
        )

        # --------------------------------------------------------------
        # Public corpus/document ⇒ strip approval-gated tools
        # --------------------------------------------------------------

        # Resolve privacy status (best-effort – failures default to private)
        try:
            doc_obj = (
                document
                if isinstance(document, Document)
                else await Document.objects.aget(id=document)
            )
            corpus_obj = None
            if corpus is not None:
                corpus_obj = (
                    corpus
                    if isinstance(corpus, Corpus)
                    else await Corpus.objects.aget(id=corpus)
                )
        except (Document.DoesNotExist, Corpus.DoesNotExist):
            # Re-raise these exceptions so callers can handle them appropriately
            raise
        except Exception:
            # For other exceptions (e.g., network errors), default to private
            doc_obj = None
            corpus_obj = None

        # Corpus memory injection
        if corpus_obj and getattr(corpus_obj, "memory_enabled", False):
            await _inject_corpus_memory(corpus_obj, config)

        public_context = _is_public(doc_obj) or (corpus_obj and _is_public(corpus_obj))

        # Check user's write permission on document (for filtering write tools)
        has_write_permission = await _user_has_write_permission(user_id, doc_obj)

        filtered_tools: list[Union[CoreTool, Callable, str]] = []
        if tools:
            for t in tools:
                if public_context and isinstance(t, CoreTool) and t.requires_approval:
                    logger.warning(
                        "Skipping approval-required tool '%s' for public context",
                        t.name,
                    )
                    continue
                # Filter out corpus-dependent tools when no corpus provided
                if corpus is None and isinstance(t, CoreTool) and t.requires_corpus:
                    logger.info(
                        "Skipping corpus-required tool '%s' - no corpus provided for document agent",
                        t.name,
                    )
                    continue
                # Filter out write tools if user lacks write permission
                if (
                    not has_write_permission
                    and isinstance(t, CoreTool)
                    and t.requires_write_permission
                ):
                    logger.info(
                        "Skipping write tool '%s' - user %s lacks WRITE permission on document %s",
                        t.name,
                        user_id,
                        doc_obj.id if doc_obj else "unknown",
                    )
                    continue
                filtered_tools.append(t)
        tools = filtered_tools

        # Keep config in sync so downstream logic respects the filtered list
        config.tools = tools

        # Convert tools to framework-specific format with context injection
        framework_tools = (
            _convert_tools_for_framework(
                tools,
                framework,
                document_id=doc_obj.id if doc_obj else None,
                corpus_id=corpus_obj.id if corpus_obj else None,
                user_id=user_id,
                corpus_action_id=config.corpus_action_id,
            )
            if tools
            else []
        )

        if framework == AgentFramework.PYDANTIC_AI:
            from opencontractserver.llms.agents.pydantic_ai_agents import (
                PydanticAIDocumentAgent,
            )

            return await PydanticAIDocumentAgent.create(
                document,
                corpus,
                config,
                framework_tools,
                **deps_kwargs,
                **create_kwargs,
            )
        else:
            raise ValueError(f"Unsupported framework: {framework}")

    @staticmethod
    async def create_corpus_agent(
        corpus: Union[str, int, Corpus],
        framework: AgentFramework = AgentFramework.PYDANTIC_AI,
        user_id: Optional[int] = None,
        # Enhanced conversation management
        conversation: Optional[Conversation] = None,
        conversation_id: Optional[int] = None,
        loaded_messages: Optional[list[ChatMessage]] = None,
        # Configuration options
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        streaming: Optional[bool] = None,
        embedder_path: Optional[str] = None,
        tools: Optional[list[Union[CoreTool, Callable, str]]] = None,
        store_user_messages: Optional[bool] = None,
        store_llm_messages: Optional[bool] = None,
        # Legacy compatibility
        override_conversation: Optional[Conversation] = None,
        override_system_prompt: Optional[str] = None,
        **kwargs,
    ) -> CoreAgent:
        """Create a corpus agent using the specified framework.

        Args:
            corpus: Corpus ID or instance
            framework: Which agent framework to use
            user_id: Optional user ID for message attribution
            conversation: Optional existing conversation object
            conversation_id: Optional existing conversation ID
            loaded_messages: Optional existing messages to load
            model: Optional model name (e.g., "gpt-4o-mini")
            system_prompt: Optional custom system prompt
            temperature: Optional temperature for response generation
            max_tokens: Optional maximum tokens in response
            streaming: Optional enable/disable streaming
            embedder_path: Optional embedder path
            tools: Optional list of tools (CoreTool instances, functions, or tool names)
            store_user_messages: Optional enable/disable storing user messages
            store_llm_messages: Optional enable/disable storing LLM messages
            override_conversation: Legacy parameter (use 'conversation' instead)
            override_system_prompt: Legacy parameter (use 'system_prompt' instead)
            **kwargs: Additional framework-specific arguments

        Returns:
            CoreAgent: Framework-specific agent implementing the CoreAgent protocol
        """
        # Handle legacy parameter names
        if override_conversation and not conversation:
            conversation = override_conversation
        if override_system_prompt and not system_prompt:
            system_prompt = override_system_prompt

        persistence_flags = {}
        if store_user_messages is not None:
            persistence_flags["store_user_messages"] = store_user_messages
        if store_llm_messages is not None:
            persistence_flags["store_llm_messages"] = store_llm_messages

        # Extract deps-specific kwargs that shouldn't go to AgentConfig
        # These are passed directly to the agent's create method
        deps_kwargs: dict[str, Any] = {}
        if "skip_approval_gate" in kwargs:
            deps_kwargs["skip_approval_gate"] = kwargs.pop("skip_approval_gate")

        config = get_default_config(
            user_id=user_id,
            model_name=model or kwargs.get("model_name"),
            system_prompt=system_prompt,
            temperature=temperature or kwargs.get("temperature", 0.7),
            max_tokens=max_tokens,
            streaming=(
                streaming if streaming is not None else kwargs.get("streaming", True)
            ),
            conversation=conversation,
            conversation_id=conversation_id,
            loaded_messages=loaded_messages,
            embedder_path=embedder_path,
            tools=tools or [],
            **persistence_flags,
            **kwargs,
        )

        # --------------------------------------------------------------
        # Public corpus/document ⇒ strip approval-gated tools
        # --------------------------------------------------------------

        # Resolve privacy status (best-effort – failures default to private)
        try:
            corpus_obj = (
                corpus
                if isinstance(corpus, Corpus)
                else await Corpus.objects.aget(id=corpus)
            )
        except Corpus.DoesNotExist:
            # Re-raise this exception so callers can handle it appropriately
            raise
        except Exception:
            # For other exceptions (e.g., network errors), default to private
            corpus_obj = None

        # Corpus memory injection
        if corpus_obj and getattr(corpus_obj, "memory_enabled", False):
            await _inject_corpus_memory(corpus_obj, config)

        public_context = _is_public(corpus_obj)

        # Check user's write permission on corpus (for filtering write tools)
        has_write_permission = await _user_has_write_permission(user_id, corpus_obj)

        filtered_tools: list[Union[CoreTool, Callable, str]] = []
        if tools:
            for t in tools:
                if public_context and isinstance(t, CoreTool) and t.requires_approval:
                    logger.warning(
                        "Skipping approval-required tool '%s' for public context",
                        t.name,
                    )
                    continue
                # Filter out write tools if user lacks write permission
                if (
                    not has_write_permission
                    and isinstance(t, CoreTool)
                    and t.requires_write_permission
                ):
                    logger.info(
                        "Skipping write tool '%s' - user %s lacks WRITE permission on corpus %s",
                        t.name,
                        user_id,
                        corpus_obj.id if corpus_obj else "unknown",
                    )
                    continue
                filtered_tools.append(t)
        tools = filtered_tools

        # Keep config in sync so downstream logic respects the filtered list
        config.tools = tools

        # Convert tools to framework-specific format with context injection
        # Note: document_id is None for corpus agents (no specific document)
        framework_tools = (
            _convert_tools_for_framework(
                tools,
                framework,
                document_id=None,
                corpus_id=corpus_obj.id if corpus_obj else None,
                user_id=user_id,
                corpus_action_id=config.corpus_action_id,
            )
            if tools
            else []
        )

        if framework == AgentFramework.PYDANTIC_AI:
            from opencontractserver.llms.agents.pydantic_ai_agents import (
                PydanticAICorpusAgent,
            )

            return await PydanticAICorpusAgent.create(
                corpus, config, framework_tools, **deps_kwargs
            )
        else:
            raise ValueError(f"Unsupported framework: {framework}")


def _convert_tools_for_framework(
    tools: list[Union[CoreTool, Callable, str]],
    framework: AgentFramework,
    *,
    document_id: int | None = None,
    corpus_id: int | None = None,
    user_id: int | None = None,
    corpus_action_id: int | None = None,
) -> list:
    """Convert tools to framework-specific format with context injection.

    Args:
        tools: List of CoreTool instances, functions, or tool names
        framework: Target framework
        document_id: Document ID to inject into tools that accept it
        corpus_id: Corpus ID to inject into tools that accept it
        user_id: User ID to inject for author_id/creator_id params
        corpus_action_id: CorpusAction ID to inject into tools that accept it

    Returns:
        List of framework-specific tools
    """
    framework_tools = []

    for tool in tools:
        if isinstance(tool, CoreTool):
            inject_params = build_inject_params_for_context(
                tool, document_id, corpus_id, user_id, corpus_action_id
            )
            framework_tools.append(
                UnifiedToolFactory.create_tool(
                    tool, framework, inject_params=inject_params
                )
            )
        elif callable(tool):
            # Convert function to CoreTool
            ct = CoreTool.from_function(tool)
            inject_params = build_inject_params_for_context(
                ct, document_id, corpus_id, user_id, corpus_action_id
            )
            framework_tools.append(
                UnifiedToolFactory.create_tool(
                    ct, framework, inject_params=inject_params
                )
            )
        elif isinstance(tool, str):
            # Handle tool names - these will be resolved by the tool factory
            # For now, we'll pass them through and let the framework handle them
            logger.debug(f"Tool name '{tool}' will be resolved by framework")
            continue
        else:
            logger.warning(f"Ignoring invalid tool: {tool}")

    return framework_tools


# Enhanced convenience functions that maintain backward compatibility
async def create_document_agent(
    document: Union[str, int, Document],
    framework: Union[AgentFramework, str, None] = None,
    user_id: Optional[int] = None,
    conversation: Optional[Conversation] = None,
    conversation_id: Optional[int] = None,
    loaded_messages: Optional[list[ChatMessage]] = None,
    embedder_path: Optional[str] = None,
    # Legacy compatibility
    override_conversation: Optional[Conversation] = None,
    override_system_prompt: Optional[str] = None,
    **kwargs,
) -> CoreAgent:
    """Create a document agent (enhanced backward compatibility wrapper).

    Args:
        document: Document ID or instance
        framework: Agent framework to use
        user_id: Optional user ID for message attribution
        conversation: Optional existing conversation object
        conversation_id: Optional existing conversation ID
        loaded_messages: Optional existing messages to load
        embedder_path: Optional embedder path
        override_conversation: Legacy parameter (use 'conversation' instead)
        override_system_prompt: Legacy parameter (use 'system_prompt' instead)
        **kwargs: Additional arguments passed to factory

    Returns:
        CoreAgent: Framework-specific agent
    """
    if framework is None:
        framework = getattr(
            settings, "LLMS_DOCUMENT_AGENT_FRAMEWORK", AgentFramework.PYDANTIC_AI
        )
    if isinstance(framework, str):
        framework = AgentFramework(framework)

    return await UnifiedAgentFactory.create_document_agent(
        document=document,
        framework=framework,
        user_id=user_id,
        conversation=conversation,
        conversation_id=conversation_id,
        loaded_messages=loaded_messages,
        embedder_path=embedder_path,
        override_conversation=override_conversation,
        override_system_prompt=override_system_prompt,
        **kwargs,
    )


async def create_corpus_agent(
    corpus: Union[str, int, Corpus],
    framework: Union[AgentFramework, str, None] = None,
    user_id: Optional[int] = None,
    conversation: Optional[Conversation] = None,
    conversation_id: Optional[int] = None,
    loaded_messages: Optional[list[ChatMessage]] = None,
    # Legacy compatibility
    override_conversation: Optional[Conversation] = None,
    override_system_prompt: Optional[str] = None,
    **kwargs,
) -> CoreAgent:
    """Create a corpus agent (enhanced backward compatibility wrapper).

    Args:
        corpus: Corpus ID or instance
        framework: Agent framework to use
        user_id: Optional user ID for message attribution
        conversation: Optional existing conversation object
        conversation_id: Optional existing conversation ID
        loaded_messages: Optional existing messages to load
        override_conversation: Legacy parameter (use 'conversation' instead)
        override_system_prompt: Legacy parameter (use 'system_prompt' instead)
        **kwargs: Additional arguments passed to factory

    Returns:
        CoreAgent: Framework-specific agent
    """
    if framework is None:
        framework = getattr(
            settings, "LLMS_CORPUS_AGENT_FRAMEWORK", AgentFramework.PYDANTIC_AI
        )
    if isinstance(framework, str):
        framework = AgentFramework(framework)

    return await UnifiedAgentFactory.create_corpus_agent(
        corpus=corpus,
        framework=framework,
        user_id=user_id,
        conversation=conversation,
        conversation_id=conversation_id,
        loaded_messages=loaded_messages,
        override_conversation=override_conversation,
        override_system_prompt=override_system_prompt,
        **kwargs,
    )
