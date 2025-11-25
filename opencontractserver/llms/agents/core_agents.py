"""Core agent functionality independent of any specific agent framework."""

import logging
from abc import ABC
from collections.abc import AsyncGenerator, Awaitable
from dataclasses import dataclass, field
from typing import (
    Any,
    Callable,
    Literal,
    Optional,
    Protocol,
    TypeVar,
    Union,
    runtime_checkable,
)

from asgiref.sync import sync_to_async
from django.conf import settings
from django.utils import timezone

from opencontractserver.conversations.models import (
    ChatMessage,
    Conversation,
    MessageStateChoices,
)
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.llms.tools.tool_factory import CoreTool
from opencontractserver.llms.vector_stores.core_vector_stores import (
    CoreAnnotationVectorStore,
)
from opencontractserver.utils.embeddings import aget_embedder

logger = logging.getLogger(__name__)

# Generic type variable for structured responses
T = TypeVar("T")


class MessageState:
    """Constants for message states."""

    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ERROR = "error"
    CANCELLED = "cancelled"
    AWAITING_APPROVAL = "awaiting_approval"


@dataclass
class SourceNode:
    """Framework-agnostic representation of a source node with metadata."""

    annotation_id: int
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    similarity_score: float = 1.0

    @classmethod
    def from_annotation(cls, annotation, similarity_score: float = 1.0) -> "SourceNode":
        """Create a SourceNode from an Annotation object."""
        return cls(
            annotation_id=annotation.id,
            content=annotation.raw_text,
            metadata={
                "annotation_id": annotation.id,
                "document_id": annotation.document_id,
                "corpus_id": annotation.corpus_id,
                "page": annotation.page,
                "annotation_label": (
                    annotation.annotation_label.text
                    if annotation.annotation_label
                    else None
                ),
            },
            similarity_score=similarity_score,
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage in message data."""
        # Start with base fields
        result = {
            "annotation_id": self.annotation_id,
            "rawText": self.content,  # Frontend expects rawText
            "similarity_score": self.similarity_score,
        }

        # Construct json field based on document type:
        # - PDF sources have annotation_json (full MultipageAnnotationJson from PlasmaPDF)
        # - Text sources have char_start/char_end (simple {start, end} format)
        if "annotation_json" in self.metadata:
            # PDF case: use full MultipageAnnotationJson from PlasmaPDF
            result["json"] = self.metadata["annotation_json"]
        elif "char_start" in self.metadata and "char_end" in self.metadata:
            # Text case: construct simple format
            result["json"] = {
                "start": self.metadata["char_start"],
                "end": self.metadata["char_end"],
            }

        # Flatten remaining metadata fields (skip annotation_json to avoid duplication)
        for key, value in self.metadata.items():
            if key != "annotation_json":
                result[key] = value

        return result


@dataclass
class UnifiedChatResponse:
    """Framework-agnostic chat response with sources and metadata."""

    content: str
    sources: list[SourceNode] = field(default_factory=list)
    user_message_id: Optional[int] = None
    llm_message_id: Optional[int] = None
    metadata: dict[str, Any] = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# DRY helper – shared fields for every streamed event                         #
# --------------------------------------------------------------------------- #


@dataclass
class _BaseStreamEvt:
    """Common fields shared by *all* stream-event dataclasses (old & new)."""

    # Legacy / convenience fields so consumers can treat every event the same
    content: str = ""
    accumulated_content: str = ""
    sources: list[SourceNode] = field(default_factory=list)
    user_message_id: Optional[int] = None
    llm_message_id: Optional[int] = None
    metadata: dict[str, Any] = field(default_factory=dict)
    is_complete: bool = False


# ------------------------------------------------------------------
# Concrete event types
# ------------------------------------------------------------------


@dataclass
class ThoughtEvent(_BaseStreamEvt):
    """An intermediate reasoning step emitted while the agent is running."""

    type: Literal["thought"] = "thought"
    thought: str = ""


@dataclass
class ContentEvent(_BaseStreamEvt):
    """A delta (token or chunk) of the assistant's final textual answer."""

    type: Literal["content"] = "content"


@dataclass
class SourceEvent(_BaseStreamEvt):
    """One or more sources discovered during the agent run."""

    type: Literal["sources"] = "sources"


@dataclass
class FinalEvent(_BaseStreamEvt):
    """The final, complete event – always the last one."""

    type: Literal["final"] = "final"
    is_complete: bool = True


@dataclass
class ErrorEvent(_BaseStreamEvt):
    """Emitted when the run terminates with an unrecoverable error."""

    type: Literal["error"] = "error"
    is_complete: bool = True
    error: str = ""


# ------------------------------------------------------------------
# Approval gating – emitted when execution pauses for human approval.
# ------------------------------------------------------------------


@dataclass
class ApprovalNeededEvent(_BaseStreamEvt):
    """Stream event indicating the agent is waiting for tool approval."""

    type: Literal["approval_needed"] = "approval_needed"
    pending_tool_call: dict[str, Any] = field(default_factory=dict)


# ------------------------------------------------------------------
# New events for post-approval workflow
# ------------------------------------------------------------------


@dataclass
class ApprovalResultEvent(_BaseStreamEvt):
    """Emitted as soon as the user decision (approve/reject) is recorded."""

    type: Literal["approval_result"] = "approval_result"
    decision: Literal["approved", "rejected"] = "approved"
    pending_tool_call: dict[str, Any] = field(default_factory=dict)


@dataclass
class ResumeEvent(_BaseStreamEvt):
    """Marks the actual resumption of execution after approval."""

    type: Literal["resume"] = "resume"


# A discriminated union over all event types. The Literal strings defined in each
# dataclass act as simple runtime markers that make it easy for downstream code
# (e.g. WebSocket serializers) to switch on the `.type` attribute without costly
# ``isinstance`` checks.
UnifiedStreamEvent = Union[
    ThoughtEvent,
    ContentEvent,
    SourceEvent,
    ApprovalNeededEvent,
    ApprovalResultEvent,
    ResumeEvent,
    FinalEvent,
    ErrorEvent,
]


@dataclass
class UnifiedStreamResponse:
    """Framework-agnostic streaming response chunk."""

    content: str
    accumulated_content: str = ""
    sources: list[SourceNode] = field(default_factory=list)
    user_message_id: Optional[int] = None
    llm_message_id: Optional[int] = None
    is_complete: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentConfig:
    """Framework-agnostic agent configuration with enhanced conversation management."""

    # Basic configuration
    user_id: Optional[int] = None
    model_name: str = "gpt-4o-mini"
    api_key: Optional[str] = None
    embedder_path: Optional[str] = None
    similarity_top_k: int = 10
    streaming: bool = True
    verbose: bool = True
    system_prompt: Optional[str] = None
    temperature: float = 0.7
    max_tokens: Optional[int] = None
    # NEW ➜ frequency (in tokens) for interim DB updates during streaming
    stream_update_freq: int = 50

    # Optional callback – every emitted UnifiedStreamEvent will also be
    # forwarded here.  Useful for bubbling nested streams up to the
    # WebSocket layer while a tool call blocks the parent LLM.
    stream_observer: Optional[Callable[[Any], Awaitable[None]]] = None

    # Enhanced conversation management
    conversation: Optional[Conversation] = None
    conversation_id: Optional[int] = None
    loaded_messages: Optional[list[ChatMessage]] = None
    store_user_messages: bool = True
    store_llm_messages: bool = True

    # Tool configuration
    tools: list[Any] = field(default_factory=list)


@dataclass
class DocumentAgentContext:
    """Context for document-specific agents (corpus may be absent for standalone mode)."""

    corpus: Optional[Corpus]
    document: Document
    config: AgentConfig
    vector_store: Optional[CoreAnnotationVectorStore] = None

    def __post_init__(self):
        """Initialize vector store if not provided."""
        if self.vector_store is None:
            self.vector_store = CoreAnnotationVectorStore(
                user_id=self.config.user_id,
                document_id=self.document.id,
                corpus_id=self.corpus.id if self.corpus is not None else None,
                embedder_path=self.config.embedder_path,
            )


@dataclass
class CorpusAgentContext:
    """Context for corpus-specific agents."""

    corpus: Corpus
    config: AgentConfig
    documents: Optional[list[Document]] = None

    async def __post_init__(self):
        """Initialize documents list if not provided."""
        if self.documents is None:
            # Use DocumentPath-based method to get active documents
            self.documents = await sync_to_async(list)(self.corpus.get_documents())


@runtime_checkable
class CoreAgent(Protocol):
    """Enhanced protocol defining the interface for framework-agnostic agents."""

    # Core conversation methods
    async def chat(self, message: str, **kwargs) -> UnifiedChatResponse:
        """Send a message and get a complete response with sources."""
        ...

    async def stream(
        self, message: str, **kwargs
    ) -> AsyncGenerator[UnifiedStreamEvent, None]:
        """Send a message and receive a typed stream of events (thoughts, content, sources, final)."""
        ...

    # Message management methods
    async def create_placeholder_message(self, msg_type: str = "LLM") -> int:
        """Create a placeholder message and return its ID."""
        ...

    async def update_message(
        self,
        message_id: int,
        content: str,
        sources: list[SourceNode] = None,
        metadata: dict[str, Any] = None,
    ) -> None:
        """Update a stored message with content, sources, and metadata."""
        ...

    async def complete_message(
        self,
        message_id: int,
        content: str,
        sources: list[SourceNode] = None,
        metadata: dict[str, Any] = None,
    ) -> None:
        """Complete a message atomically with content, sources, and metadata."""
        ...

    async def cancel_message(self, message_id: int, reason: str = "Cancelled") -> None:
        """Cancel a placeholder message."""
        ...

    async def store_user_message(self, content: str) -> int:
        """Store a user message in the conversation."""
        ...

    async def store_llm_message(
        self,
        content: str,
        sources: list[SourceNode] = None,
        metadata: dict[str, Any] = None,
    ) -> int:
        """Store an LLM message in the conversation."""
        ...

    # Conversation metadata methods
    def get_conversation_id(self) -> Optional[int]:
        """Get the current conversation ID for session continuity."""
        ...

    def get_conversation_info(self) -> dict[str, Any]:
        """Get conversation metadata including ID, title, and user info."""
        ...

    async def get_conversation_messages(self) -> list[ChatMessage]:
        """Get all messages in the current conversation."""
        ...

    # ------------------------------------------------------------------
    # Structured response extraction
    # ------------------------------------------------------------------

    async def structured_response(
        self,
        prompt: str,
        target_type: type[T],
        *,
        model: Optional[str] = None,
        tools: Optional[list[Union["CoreTool", Callable, str]]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> Optional[T]:
        """Performs a one-shot query to extract structured data matching the target_type.

        This method is non-conversational and does not store messages.

        Args:
            prompt: The natural language prompt for data extraction.
            target_type: The Python type for the desired output (e.g., int, str, list[str], MyPydanticModel).
            model: An optional, single-use LLM model override.
            tools: An optional, single-use list of tools for this call.
            temperature: An optional, single-use temperature setting.
            max_tokens: An optional, single-use max_tokens setting.
            **kwargs: Additional framework-specific options.

        Returns:
            An instance of target_type if successful, otherwise None.
        """
        ...

    # ------------------------------------------------------------------
    # Human-in-the-loop: approve / resume
    # ------------------------------------------------------------------

    async def resume_with_approval(
        self,
        llm_message_id: int,
        approved: bool,
        **kwargs,
    ) -> Union[UnifiedChatResponse, AsyncGenerator[UnifiedStreamEvent, None]]:
        """Resume a paused conversation after an approval decision.

        Args:
            llm_message_id: The message that is currently *awaiting* approval.
            approved: ``True`` if the user approved execution; ``False`` if
                rejected.
            **kwargs: Forwarded to the underlying ``chat`` / ``stream``.
        """
        ...


class CoreAgentBase(ABC):
    """Base implementation of CoreAgent with common functionality.

    Sub-classes **must** implement the framework-specific low-level hooks

        async def _chat_raw(self, message: str, **kw) -> tuple[str, list[SourceNode], dict]:
        async def _stream_raw(self, message: str, **kw) -> AsyncGenerator[UnifiedStreamEvent, None]:

    All DB-persistence, approval gating and incremental message updates are
    handled by the concrete ``chat`` / ``stream`` wrappers defined here.
    """

    def __init__(
        self, config: AgentConfig, conversation_manager: "CoreConversationManager"
    ):
        self.config = config
        self.conversation_manager = conversation_manager

    async def create_placeholder_message(self, msg_type: str = "LLM") -> int:
        """Create a placeholder message and return its ID."""
        # For anonymous conversations, don't store messages
        if not self.conversation_manager.conversation:
            return 0  # Return a placeholder ID for anonymous conversations

        from opencontractserver.conversations.models import (
            ChatMessage,
        )

        message = await ChatMessage.objects.acreate(
            conversation=self.conversation_manager.conversation,
            content="",
            msg_type=msg_type,
            creator_id=self.conversation_manager.user_id,
            data={
                "state": MessageState.IN_PROGRESS,
                "created_at": timezone.now().isoformat(),
            },
            state=MessageState.IN_PROGRESS,
        )
        return message.id

    async def update_message(
        self,
        message_id: int,
        content: str,
        sources: list[SourceNode] = None,
        metadata: dict[str, Any] = None,
    ) -> None:
        """Update a stored message with content, sources, and metadata."""
        if metadata and "timeline" not in metadata:
            metadata["timeline"] = []
        await self.conversation_manager.update_message(
            message_id, content, sources, metadata
        )

    async def complete_message(
        self,
        message_id: int,
        content: str,
        sources: list[SourceNode] = None,
        metadata: dict[str, Any] = None,
    ) -> None:
        """Complete a message atomically with content, sources, and metadata."""
        logger.error("[DIAGNOSTIC complete_message] Called with:")
        logger.error(f"[DIAGNOSTIC complete_message]   message_id: {message_id}")
        logger.error(f"[DIAGNOSTIC complete_message]   content length: {len(content)}")
        logger.error(
            f"[DIAGNOSTIC complete_message]   sources: {sources is not None} (count: {len(sources) if sources else 0})"
        )
        if sources:
            logger.error(
                f"[DIAGNOSTIC complete_message]   First source: {sources[0].to_dict()}"
            )
        logger.error(
            f"[DIAGNOSTIC complete_message]   metadata keys: {metadata.keys() if metadata else 'None'}"
        )
        logger.error(
            "[DIAGNOSTIC complete_message]   Calling conversation_manager.complete_message()..."
        )
        await self.conversation_manager.complete_message(
            message_id, content, sources, metadata
        )
        logger.error(
            "[DIAGNOSTIC complete_message]   conversation_manager.complete_message() returned successfully"
        )

    async def cancel_message(self, message_id: int, reason: str = "Cancelled") -> None:
        """Cancel a placeholder message."""
        await self.conversation_manager.cancel_message(message_id, reason)

    async def store_user_message(self, content: str) -> int:
        """Store a user message in the conversation."""
        return await self.conversation_manager.store_user_message(content)

    async def store_llm_message(
        self,
        content: str,
        sources: list[SourceNode] = None,
        metadata: dict[str, Any] = None,
    ) -> int:
        """Store an LLM message in the conversation."""
        return await self.conversation_manager.store_llm_message(
            content, sources, metadata
        )

    def get_conversation_id(self) -> Optional[int]:
        """Get the current conversation ID for session continuity."""
        return (
            self.conversation_manager.conversation.id
            if self.conversation_manager.conversation
            else None
        )

    def get_conversation_info(self) -> dict[str, Any]:
        """Get conversation metadata including ID, title, and user info."""
        if not self.conversation_manager.conversation:
            return {"conversation_id": None, "title": None, "user_id": None}

        conv = self.conversation_manager.conversation
        return {
            "conversation_id": conv.id,
            "title": conv.title,
            "user_id": self.conversation_manager.user_id,
            "created": conv.created.isoformat() if conv.created else None,
            "description": conv.description,
        }

    async def get_conversation_messages(self) -> list[ChatMessage]:
        """Get all messages in the current conversation."""
        return await self.conversation_manager.get_conversation_messages()

    # Legacy compatibility methods
    async def stream_chat(
        self, message: str, **kwargs
    ) -> AsyncGenerator[UnifiedStreamEvent, None]:
        """Legacy compatibility wrapper that simply forwards to ``stream`` and yields its events."""
        async for chunk in self.stream(message, **kwargs):
            yield chunk

    async def store_message(self, content: str, msg_type: str = "LLM") -> int:
        """Legacy method - delegates to appropriate store method."""
        if msg_type.upper() == "USER":
            return await self.store_user_message(content)
        else:
            return await self.store_llm_message(content)

    # ------------------------------------------------------------------
    # Structured response extraction
    # ------------------------------------------------------------------

    async def structured_response(
        self,
        prompt: str,
        target_type: type[T],
        *,
        model: Optional[str] = None,
        tools: Optional[list[Union["CoreTool", Callable, str]]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> Optional[T]:
        """Framework-agnostic wrapper for structured response extraction.

        This method provides ephemeral, one-shot data extraction without
        persisting any messages to the conversation history.

        Args:
            prompt: The natural language prompt for data extraction.
            target_type: The Python type for the desired output.
            model: Optional model override.
            tools: Optional tools override.
            temperature: Optional temperature override.
            max_tokens: Optional max_tokens override.
            **kwargs: Additional framework-specific options.

        Returns:
            An instance of target_type if successful, otherwise None.
        """
        try:
            # Call the framework-specific implementation
            result = await self._structured_response_raw(
                prompt=prompt,
                target_type=target_type,
                model=model,
                tools=tools,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs,
            )
            return result
        except Exception as e:
            # Log the error but don't raise - return None per spec
            print(f"Error in structured_response: {e}")
            return None

    # ------------------------------------------------------------------
    # Framework-specific hooks – **must** be implemented by adapters.
    # ------------------------------------------------------------------

    async def _chat_raw(
        self, message: str, **kwargs
    ) -> tuple[str, list[SourceNode], dict]:  # pragma: no cover – abstract
        """Return *(content, sources, metadata)*.

        Default implementation raises ``NotImplementedError`` so sub-classes
        are forced to provide their own version.
        """
        raise NotImplementedError

    async def _stream_raw(
        self, message: str, **kwargs
    ) -> AsyncGenerator[UnifiedStreamEvent, None]:  # pragma: no cover – abstract
        """Yield framework-native events (ThoughtEvent / ContentEvent / …).

        The base wrapper will take care of DB side-effects.
        """
        raise NotImplementedError

    async def _structured_response_raw(
        self,
        prompt: str,
        target_type: type[T],
        *,
        model: Optional[str] = None,
        tools: Optional[list[Union["CoreTool", Callable, str]]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> Optional[T]:  # pragma: no cover – abstract
        """Framework-specific structured response extraction.

        This method must be implemented by framework adapters to perform
        the actual structured extraction using their native capabilities.

        Args:
            prompt: The natural language prompt for data extraction.
            target_type: The Python type for the desired output.
            model: Optional model override.
            tools: Optional tools override.
            temperature: Optional temperature override.
            max_tokens: Optional max_tokens override.
            **kwargs: Additional framework-specific options.

        Returns:
            An instance of target_type if successful, otherwise None.
        """
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Public chat / stream wrappers – universal across frameworks.
    # ------------------------------------------------------------------

    async def chat(self, message: str, **kwargs) -> UnifiedChatResponse:  # type: ignore[override]
        """Framework-agnostic chat wrapper that transparently persists state."""

        from opencontractserver.llms.exceptions import ToolConfirmationRequired

        # Honour per-call override for message persistence
        store_messages: bool = kwargs.pop("store_messages", True)

        # 1️⃣  Persist user prompt (if configured)
        user_msg_id: int | None = None
        llm_msg_id: int | None = None

        if store_messages and self.conversation_manager.config.store_user_messages:
            user_msg_id = await self.store_user_message(message)

        if store_messages and self.conversation_manager.config.store_llm_messages:
            llm_msg_id = await self.create_placeholder_message("LLM")

        try:
            # 2️⃣  Delegate to framework
            content, sources, meta = await self._chat_raw(message, **kwargs)

            # 3️⃣  Finalise message
            if llm_msg_id:
                await self.complete_message(llm_msg_id, content, sources, meta)

            return UnifiedChatResponse(
                content=content,
                sources=sources,
                user_message_id=user_msg_id,
                llm_message_id=llm_msg_id,
                metadata=meta or {},
            )

        except ToolConfirmationRequired as e:
            # Mark message as awaiting approval and bubble up light response
            if llm_msg_id is None:
                # We may reach here if placeholder wasn't created (anonymous?), create one now
                llm_msg_id = await self.create_placeholder_message("LLM")

            await self.pause_for_approval(
                llm_msg_id,
                tool_name=e.tool_name,
                tool_args=e.tool_args,
                tool_call_id=e.tool_call_id,
            )

            return UnifiedChatResponse(
                content="Action required: approval needed to run tool.",
                sources=[],
                user_message_id=user_msg_id,
                llm_message_id=llm_msg_id,
                metadata={
                    "state": MessageState.AWAITING_APPROVAL,
                    "pending_tool_call": {
                        "name": e.tool_name,
                        "arguments": e.tool_args,
                        "tool_call_id": e.tool_call_id,
                    },
                },
            )

        except Exception as exc:
            if llm_msg_id:
                await self.conversation_manager.mark_message_error(llm_msg_id, str(exc))
            # Return an error response so callers can surface the failure gracefully
            return UnifiedChatResponse(
                content="Error: " + str(exc),
                sources=[],
                user_message_id=user_msg_id,
                llm_message_id=llm_msg_id,
                metadata={"error": str(exc)},
            )

    # NOTE: Streaming wrapper is more involved but follows same pattern
    async def stream(self, message: str, **kwargs):  # type: ignore[override]
        """Framework-agnostic streaming wrapper with persistence."""

        from opencontractserver.llms.exceptions import ToolConfirmationRequired

        store_messages: bool = kwargs.pop("store_messages", True)

        user_msg_id: int | None = None
        llm_msg_id: int | None = None

        if store_messages and self.conversation_manager.config.store_user_messages:
            user_msg_id = await self.store_user_message(message)

        if store_messages and self.conversation_manager.config.store_llm_messages:
            llm_msg_id = await self.create_placeholder_message("LLM")

        accumulated_content: str = ""
        accumulated_sources: list[SourceNode] = []
        token_counter = 0

        try:
            async for evt in self._stream_raw(message, **kwargs):

                # ➊ Ensure every event carries the DB message identifiers so the
                #    websocket consumer can reliably emit the mandatory
                #    `ASYNC_START` envelope *before* any granular event.
                if isinstance(evt, dict):
                    # Events coming from legacy adapters might still be plain dicts –
                    # skip automatic augmentation to avoid type errors.
                    pass
                else:
                    # Set identifiers only if the adapter has not already done so.
                    if getattr(evt, "user_message_id", None) is None:
                        evt.user_message_id = user_msg_id
                    if getattr(evt, "llm_message_id", None) is None:
                        evt.llm_message_id = llm_msg_id

                # Merge sources for later finalisation
                if hasattr(evt, "sources") and evt.sources:
                    accumulated_sources.extend(evt.sources)

                # Track accumulating content for incremental updates
                if hasattr(evt, "content") and evt.content:
                    accumulated_content += evt.content
                    token_counter += 1

                # Periodic DB update
                if (
                    llm_msg_id
                    and token_counter % self.config.stream_update_freq == 0
                    and accumulated_content
                ):
                    await self.conversation_manager.update_message_content(
                        llm_msg_id, accumulated_content
                    )

                # Side-channel: forward to observer if configured.
                await self._emit_observer_event(evt)

                yield evt  # Pass through

            # After generator exhausted – finalise message
            if llm_msg_id:
                await self.complete_message(
                    llm_msg_id,
                    accumulated_content,
                    accumulated_sources,
                    {},
                )

        except ToolConfirmationRequired as e:
            # Finalise as awaiting approval and emit ApprovalNeededEvent
            await self.pause_for_approval(
                llm_msg_id,
                tool_name=e.tool_name,
                tool_args=e.tool_args,
                tool_call_id=e.tool_call_id,
            )

            yield ApprovalNeededEvent(
                pending_tool_call={
                    "name": e.tool_name,
                    "arguments": e.tool_args,
                    "tool_call_id": e.tool_call_id,
                },
                user_message_id=user_msg_id,
                llm_message_id=llm_msg_id,
            )

        except Exception as exc:
            if llm_msg_id:
                await self.conversation_manager.mark_message_error(llm_msg_id, str(exc))

            # Emit error event so front-end can conclude the stream cleanly
            yield ErrorEvent(
                error=str(exc),
                content="",  # no delta
                is_complete=True,
                user_message_id=user_msg_id,
                llm_message_id=llm_msg_id,
                metadata={"error": str(exc)},
            )
            return

    # ------------------------------------------------------------------
    # Helper for lightweight source normalisation (framework-agnostic)
    # ------------------------------------------------------------------
    @staticmethod
    def _normalise_source(raw: Any) -> SourceNode:
        """Best-effort conversion of *raw* into a SourceNode instance."""
        if isinstance(raw, SourceNode):
            return raw

        # Attempt to treat *raw* like a mapping
        if hasattr(raw, "model_dump"):
            raw = raw.model_dump()
        if isinstance(raw, dict):
            return SourceNode(
                annotation_id=int(raw.get("annotation_id", 0)),
                content=raw.get("content", raw.get("text", "")),
                metadata=raw,
                similarity_score=float(raw.get("similarity_score", 1.0)),
            )

        # Fallback: string or unknown – wrap in dummy SourceNode
        return SourceNode(
            annotation_id=0, content=str(raw), metadata={}, similarity_score=1.0
        )

    # ------------------------------------------------------------------
    # Human-in-the-loop helpers
    # ------------------------------------------------------------------

    async def pause_for_approval(
        self,
        llm_message_id: int,
        *,
        tool_name: str,
        tool_args: dict[str, Any],
        tool_call_id: str | None = None,
        framework: str = "pydantic_ai",
    ) -> None:
        """Mark an LLM message as *awaiting approval*.

        Adapters that implement dangerous or privileged tools can call this
        one-liner instead of re-implementing the same bookkeeping.
        """
        await self.complete_message(
            llm_message_id,
            content="Awaiting user approval for tool execution.",
            metadata={
                "state": MessageState.AWAITING_APPROVAL,
                "pending_tool_call": {
                    "name": tool_name,
                    "arguments": tool_args,
                    "tool_call_id": tool_call_id,
                },
                "framework": framework,
            },
        )

    async def mark_message_error(self, message_id: int, error: str) -> None:
        """Delegate to the conversation manager's implementation.

        The original inlined code used the undefined attribute
        ``self.conversation`` which raises ``AttributeError``.  To avoid
        duplication and keep a single source-of-truth, this wrapper now
        forwards the call to :pymeth:`CoreConversationManager.mark_message_error`.
        """

        await self.conversation_manager.mark_message_error(message_id, error)

    # ------------------------------------------------------------------
    # Observer helper
    # ------------------------------------------------------------------

    async def _emit_observer_event(self, evt: Any) -> None:
        """Forward *evt* to the ``stream_observer`` if one is configured."""
        cb = getattr(self.config, "stream_observer", None)
        if cb and callable(cb):
            try:
                await cb(evt)
            except Exception:  # pragma: no cover – observer must not kill run
                logger.exception("Stream observer raised an exception")


class CoreDocumentAgentFactory:
    """Factory for creating document agents with framework-agnostic configuration."""

    @staticmethod
    def get_default_system_prompt(
        document: Document, corpus: Optional[Corpus] = None
    ) -> str:
        """Generate default system prompt for document agent.

        Uses custom instructions from corpus if available, otherwise falls back to
        DEFAULT_DOCUMENT_AGENT_INSTRUCTIONS from settings.
        """
        from django.conf import settings

        # Check for custom instructions on the corpus
        if corpus and corpus.document_agent_instructions:
            base_instructions = corpus.document_agent_instructions
        else:
            base_instructions = settings.DEFAULT_DOCUMENT_AGENT_INSTRUCTIONS

        # Prepend document context to the instructions
        return (
            f"You are analyzing the document titled '{document.title}' (ID: {document.id}).\n\n"
            f"{base_instructions}"
        )

    @staticmethod
    async def create_context(
        document: Union[str, int, Document],
        corpus: Union[str, int, Corpus, None],
        config: AgentConfig,
    ) -> DocumentAgentContext:
        """Create document agent context with all necessary components. Supports corpus-less mode."""
        if not isinstance(document, Document):
            document = await Document.objects.aget(id=document)

        corpus_obj: Optional[Corpus]
        if corpus is None:
            corpus_obj = None
        else:
            corpus_obj = (
                corpus
                if isinstance(corpus, Corpus)
                else await Corpus.objects.aget(id=corpus)
            )

        # ------------------------------------------------------------------
        # Basic permission check – anonymous sessions cannot access private docs
        # ------------------------------------------------------------------
        if corpus_obj is not None:
            _assert_access(corpus_obj, config.user_id)
        _assert_access(document, config.user_id)

        # ------------------------------------------------------------------
        # Ensure an embedder is configured
        # ------------------------------------------------------------------
        if config.embedder_path is None:
            if corpus_obj is not None:
                _, name = await aget_embedder(corpus_obj.id)
                config.embedder_path = name
            else:
                # Fall back to default embedder when no corpus available
                config.embedder_path = getattr(settings, "DEFAULT_EMBEDDER", None)

        # Set default system prompt if not provided
        if config.system_prompt is None:
            config.system_prompt = CoreDocumentAgentFactory.get_default_system_prompt(
                document, corpus_obj
            )

        return DocumentAgentContext(corpus=corpus_obj, document=document, config=config)


class CoreCorpusAgentFactory:
    """Factory for creating corpus agents with framework-agnostic configuration."""

    @staticmethod
    def get_default_system_prompt(corpus: Corpus) -> str:
        """Generate default system prompt for corpus agent.

        Uses custom instructions from corpus if available, otherwise falls back to
        DEFAULT_CORPUS_AGENT_INSTRUCTIONS from settings.
        """
        from django.conf import settings

        # Check for custom instructions on the corpus
        if corpus.corpus_agent_instructions:
            base_instructions = corpus.corpus_agent_instructions
        else:
            base_instructions = settings.DEFAULT_CORPUS_AGENT_INSTRUCTIONS

        # Prepend corpus context to the instructions
        return (
            f"You are analyzing the corpus titled '{corpus.title}' (ID: {corpus.id}).\n\n"
            f"{base_instructions}"
        )

    @staticmethod
    async def create_context(
        corpus: Union[str, int, Corpus],
        config: AgentConfig,
    ) -> CorpusAgentContext:
        """Create corpus agent context with all necessary components."""
        if not isinstance(corpus, Corpus):
            corpus = await Corpus.objects.aget(id=corpus)

        # Permission check – anonymous sessions cannot access private corpuses
        _assert_access(corpus, config.user_id)

        # Use DocumentPath-based method to get active documents
        documents = await sync_to_async(list)(corpus.get_documents())

        # Set default system prompt if not provided
        if config.system_prompt is None:
            config.system_prompt = CoreCorpusAgentFactory.get_default_system_prompt(
                corpus
            )

        # Use corpus preferred embedder if not specified
        if config.embedder_path is None:
            config.embedder_path = corpus.preferred_embedder

        context = CorpusAgentContext(corpus=corpus, config=config, documents=documents)
        await context.__post_init__()
        return context


class CoreConversationManager:
    """Enhanced conversation manager with full message lifecycle support and atomic operations."""

    def __init__(
        self,
        conversation: Optional[Conversation],
        user_id: Optional[int],
        config: AgentConfig,
    ):
        self.conversation = conversation
        self.user_id = user_id
        self.config = config

    @classmethod
    async def create_for_document(
        cls,
        corpus: Optional[Corpus],
        document: Document,
        user_id: Optional[int],
        config: AgentConfig,
        override_conversation: Optional[Conversation] = None,
        conversation_id: Optional[int] = None,
        loaded_messages: Optional[list[ChatMessage]] = None,
    ) -> "CoreConversationManager":
        """Create conversation manager for document agent with enhanced options."""
        conversation = None

        # For anonymous users, public corpuses, or when caller disabled storage, avoid DB persistence.
        if user_id is None or (
            not config.store_user_messages and not config.store_llm_messages
        ):
            logger.debug(
                f"Creating ephemeral (non-stored) conversation for public/anonymous user on document {document.id}"
            )
            # Override config to ensure no message storage for anonymous conversations
            config.store_user_messages = False
            config.store_llm_messages = False
            # Return manager with no conversation - everything will be in-memory only
            return cls(None, None, config)

        # For authenticated users, handle conversation persistence normally
        if override_conversation:
            conversation = override_conversation
        elif config.conversation:
            conversation = config.conversation
        elif conversation_id or config.conversation_id:
            cid = conversation_id or config.conversation_id
            try:
                conversation = await Conversation.objects.aget(id=cid)
            except Conversation.DoesNotExist:
                logger.warning(f"Conversation {cid} not found, creating new one")

        if not conversation:
            # Create new conversation for authenticated user
            conversation = await Conversation.objects.acreate(
                title=f"Chat about {document.title}",
                description=f"Conversation about document: {document.title}",
                creator_id=user_id,
                chat_with_document=document,
            )
            logger.debug(
                f"Created new conversation {conversation.id} for document {document.id} (user: {user_id})"
            )

        manager = cls(conversation, user_id, config)

        # Load existing messages if provided
        if loaded_messages or config.loaded_messages:
            messages = loaded_messages or config.loaded_messages
            logger.debug(
                f"Loaded {len(messages)} existing messages for conversation {conversation.id}"
            )

        return manager

    @classmethod
    async def create_for_corpus(
        cls,
        corpus: Corpus,
        user_id: Optional[int],
        config: AgentConfig,
        override_conversation: Optional[Conversation] = None,
        conversation_id: Optional[int] = None,
        loaded_messages: Optional[list[ChatMessage]] = None,
    ) -> "CoreConversationManager":
        """Create conversation manager for corpus agent with enhanced options."""
        conversation = None

        # For anonymous users, public corpuses, or when caller disabled storage, avoid DB persistence.
        if user_id is None or (
            not config.store_user_messages and not config.store_llm_messages
        ):
            logger.debug(
                f"Creating ephemeral (non-stored) conversation for public/anonymous user on corpus {corpus.id}"
            )
            # Override config to ensure no message storage for anonymous conversations
            config.store_user_messages = False
            config.store_llm_messages = False
            # Return manager with no conversation - everything will be in-memory only
            return cls(None, None, config)

        # For authenticated users, handle conversation persistence normally
        if override_conversation:
            conversation = override_conversation
        elif config.conversation:
            conversation = config.conversation
        elif conversation_id or config.conversation_id:
            cid = conversation_id or config.conversation_id
            try:
                conversation = await Conversation.objects.aget(id=cid)
            except Conversation.DoesNotExist:
                logger.warning(f"Conversation {cid} not found, creating new one")

        if not conversation:
            # Create new conversation for authenticated user
            conversation = await Conversation.objects.acreate(
                title=f"Chat about {corpus.title}",
                description=f"Conversation about corpus: {corpus.title}",
                creator_id=user_id,
                chat_with_corpus=corpus,
            )
            logger.debug(
                f"Created new conversation {conversation.id} for corpus {corpus.id} (user: {user_id})"
            )

        manager = cls(conversation, user_id, config)

        # Load existing messages if provided
        if loaded_messages or config.loaded_messages:
            messages = loaded_messages or config.loaded_messages
            logger.debug(
                f"Loaded {len(messages)} existing messages for conversation {conversation.id}"
            )

        return manager

    async def get_conversation_messages(self) -> list[ChatMessage]:
        """Get all messages in the conversation."""
        # For anonymous conversations, return empty list since nothing is stored
        if not self.conversation:
            return []

        return [
            msg
            async for msg in ChatMessage.objects.filter(
                conversation=self.conversation
            ).order_by("created")
        ]

    async def create_placeholder_message(self, msg_type: str = "LLM") -> int:
        """Create a placeholder message with state tracking."""
        # For anonymous conversations, don't store messages
        if not self.conversation:
            return 0  # Return a placeholder ID for anonymous conversations

        from opencontractserver.conversations.models import (
            ChatMessage,
        )

        message = await ChatMessage.objects.acreate(
            conversation=self.conversation,
            content="",
            msg_type=msg_type,
            creator_id=self.user_id,
            data={
                "state": MessageState.IN_PROGRESS,
                "created_at": timezone.now().isoformat(),
            },
            state=MessageState.IN_PROGRESS,
        )
        return message.id

    async def update_message_content(self, message_id: int, content: str) -> None:
        """Update only the content of a message."""
        # For anonymous conversations, don't store messages
        if not self.conversation or message_id == 0:
            return

        message = await ChatMessage.objects.aget(id=message_id)
        message.content = content
        message.state = MessageState.COMPLETED
        await message.asave(update_fields=["content", "state"])

    async def complete_message(
        self,
        message_id: int,
        content: str,
        sources: list[SourceNode] = None,
        metadata: dict[str, Any] = None,
    ) -> None:
        """Complete a message with content, sources, and metadata in one operation."""

        # For anonymous conversations, don't store messages
        if not self.conversation or message_id == 0:
            return

        message = await ChatMessage.objects.aget(id=message_id)

        message.content = content
        message.state = MessageState.COMPLETED

        data = message.data or {}
        data["completed_at"] = timezone.now().isoformat()

        if sources:
            data["sources"] = [source.to_dict() for source in sources]

        # Ensure a timeline key exists even if adapter didn't supply one
        if metadata:
            if "timeline" not in metadata:
                metadata["timeline"] = []
            data.update(metadata)
        else:
            data.setdefault("timeline", [])

        message.data = data
        await message.asave()

    async def cancel_message(self, message_id: int, reason: str = "Cancelled") -> None:
        """Cancel a placeholder message."""
        # For anonymous conversations, don't store messages
        if not self.conversation or message_id == 0:
            return

        message = await ChatMessage.objects.aget(id=message_id)
        message.content = reason
        message.state = MessageState.CANCELLED
        data = message.data or {}
        data["cancelled_at"] = timezone.now().isoformat()
        message.data = data
        await message.asave()

    async def store_user_message(self, content: str) -> int:
        """Store a user message in the conversation."""
        # For anonymous conversations, don't store messages
        if not self.conversation:
            return 0  # Return a placeholder ID for anonymous conversations

        message = await ChatMessage.objects.acreate(
            conversation=self.conversation,
            content=content,
            msg_type="HUMAN",
            creator_id=self.user_id,
            data={
                "state": MessageState.COMPLETED,
                "created_at": timezone.now().isoformat(),
            },
            state=MessageStateChoices.COMPLETED,
        )
        return message.id

    async def store_llm_message(
        self,
        content: str,
        sources: list[SourceNode] = None,
        metadata: dict[str, Any] = None,
    ) -> int:
        """Store an LLM message in the conversation."""
        # For anonymous conversations, don't store messages
        if not self.conversation:
            return 0  # Return a placeholder ID for anonymous conversations

        data = {
            "state": MessageState.COMPLETED,
            "created_at": timezone.now().isoformat(),
        }

        if sources:
            data["sources"] = [source.to_dict() for source in sources]
        if metadata:
            data.update(metadata)

        message = await ChatMessage.objects.acreate(
            conversation=self.conversation,
            content=content,
            msg_type="LLM",
            creator_id=self.user_id,
            data=data,
            state=MessageStateChoices.COMPLETED,
        )
        return message.id

    async def update_message(
        self,
        message_id: int,
        content: str,
        sources: list[SourceNode] = None,
        metadata: dict[str, Any] = None,
    ) -> None:
        """Update an existing message with content, sources, and metadata."""
        # For anonymous conversations, don't store messages
        if not self.conversation or message_id == 0:
            return

        message = await ChatMessage.objects.aget(id=message_id)
        message.content = content
        message.state = MessageState.COMPLETED

        data = message.data or {}
        data["updated_at"] = timezone.now().isoformat()

        if sources:
            data["sources"] = [source.to_dict() for source in sources]
        if metadata:
            data.update(metadata)

        message.data = data
        await message.asave()

    async def mark_message_error(self, message_id: int, error: str) -> None:
        """Mark an existing message as errored along with the error text.

        This mirrors the helper available on ``CoreAgentBase`` so that agent
        wrappers can consistently delegate the persistence step to the
        conversation manager.  Front-end code relies on the ``state`` and
        ``error`` fields to detect failed runs and render a proper error
        bubble instead of crashing the stream.
        """
        # Anonymous (non-persistent) conversations – nothing to store.
        if not self.conversation or message_id == 0:
            return

        from opencontractserver.conversations.models import ChatMessage

        message = await ChatMessage.objects.aget(id=message_id)
        message.content = error
        message.state = MessageState.ERROR

        data = message.data or {}
        data["error"] = error
        data["errored_at"] = timezone.now().isoformat()
        message.data = data

        await message.asave()


def get_default_config(**overrides) -> AgentConfig:
    """Get default agent configuration with optional overrides."""
    defaults = {
        "model_name": "gpt-4o-mini",
        "api_key": getattr(settings, "OPENAI_API_KEY", None),
        "similarity_top_k": 10,
        "streaming": True,
        "verbose": True,
        "temperature": 0.7,
    }
    defaults.update(overrides)
    return AgentConfig(**defaults)


# ------------------------------------------------------------------
# Visibility & permission helpers (public/private corpuses & documents)
# ------------------------------------------------------------------


def _is_public(obj: Any) -> bool:  # noqa: ANN401 – generic helper
    """Return ``True`` if a *Document* or *Corpus* is publicly visible.

    The helper is intentionally lenient – we merely look for the most
    common attributes that encode visibility so the core framework does
    *not* depend on a particular field name.  If no recognisable public
    flag is found we conservatively assume the object is *private*.
    """

    if obj is None:
        return False

    # 1. Explicit boolean ``is_public`` field – preferred convention.
    if hasattr(obj, "is_public"):
        try:
            return bool(getattr(obj, "is_public"))
        except Exception:  # pragma: no cover – defensive
            return False

    # 2. String/enum ``visibility`` field.
    if hasattr(obj, "visibility"):
        try:
            visibility = getattr(obj, "visibility")
            # Accept both enum or plain string representations.
            if isinstance(visibility, str):
                return visibility.lower() == "public"
            # Enum – rely on ``name`` attr.
            return getattr(visibility, "name", "").lower() == "public"
        except Exception:  # pragma: no cover – defensive
            return False

    return False  # default: not public


def _assert_access(obj: Any, user_id: int | None) -> None:  # noqa: ANN401
    """Raise *PermissionError* if *user_id* may not access *obj*.

    Current policy: anonymous users (``user_id is None``) may only access
    *public* corpuses/documents.  Authenticated access control beyond
    that is expected to be enforced at the application layer.
    """

    if not _is_public(obj) and user_id is None:
        raise PermissionError(
            "Access denied – private resource requires authentication."
        )
