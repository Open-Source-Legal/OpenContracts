"""
UnifiedAgentConsumer

A single WebSocket consumer that handles all agent conversation contexts:
- Corpus-level queries (replaces CorpusQueryConsumer)
- Document queries with corpus context (replaces DocumentQueryConsumer)
- Standalone document queries (replaces StandaloneDocumentQueryConsumer)

This DRY refactoring reduces ~1500 lines of duplicated code into a single,
maintainable consumer that supports dynamic agent selection.

Query Parameters:
    corpus_id: Optional GraphQL ID for corpus context
    document_id: Optional GraphQL ID for document context
    conversation_id: Optional GraphQL ID for existing conversation
    agent_id: Optional GraphQL ID for specific agent (uses default if omitted)

Agent Selection Logic:
    1. If agent_id provided → use that specific agent configuration
    2. If document_id provided → use default-document-agent (GLOBAL)
    3. If corpus_id provided → use default-corpus-agent (GLOBAL)
    4. Otherwise → reject connection (no context)
"""

from __future__ import annotations

import asyncio
import json
import logging
import urllib.parse
import uuid
from typing import Any

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.conf import settings
from graphql_relay import from_global_id

from config.ratelimit.decorators import check_ws_rate_limit
from config.websocket.auth_handshake import AuthHandshakeMixin
from config.websocket.middleware import WS_CLOSE_RATE_LIMITED, WS_CLOSE_UNAUTHENTICATED
from config.websocket.utils.auth_helpers import check_auth_and_close_if_failed
from opencontractserver.agents.models import AgentConfiguration
from opencontractserver.constants.context_guardrails import WS_ERROR_CONTEXT_EXHAUSTED
from opencontractserver.conversations.models import MessageType
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.llms import agents
from opencontractserver.llms.agents.core_agents import (
    ApprovalNeededEvent,
    ApprovalResultEvent,
    ContentEvent,
    ErrorEvent,
    FinalEvent,
    ResumeEvent,
    SourceEvent,
    ThoughtEvent,
)
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import user_has_permission_for_obj

logger = logging.getLogger(__name__)


class UnifiedAgentConsumer(AuthHandshakeMixin, AsyncWebsocketConsumer):
    """
    Unified WebSocket consumer for all agent conversation contexts.

    Supports corpus queries, document queries (with or without corpus),
    and dynamic agent selection via query parameters.
    """

    # Instance state
    agent = None
    agent_config: AgentConfiguration | None = None
    corpus: Corpus | None = None
    document: Document | None = None
    session_id: str | None = None
    user_id: int | None = None

    # IDs extracted from query params
    corpus_id: int | None = None
    document_id: int | None = None
    agent_config_id: int | None = None
    conversation_id: int | None = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.consumer_id = uuid.uuid4()
        self._is_connected = False
        logger.debug(f"[UnifiedAgent {self.consumer_id}] __init__ called.")

    # -------------------------------------------------------------------------
    #  WebSocket lifecycle
    # -------------------------------------------------------------------------

    async def connect(self) -> None:
        """
        Authenticate, extract context from query params, validate permissions,
        resolve agent configuration, and accept the connection.
        """
        self.session_id = str(uuid.uuid4())
        logger.debug(
            f"[UnifiedAgent {self.consumer_id} | Session {self.session_id}] "
            f"connect() called. Path: {self.scope['path']}"
        )

        try:
            # 0. Rate limit new connections (skip JSON message — connection
            #    is about to be closed so the client won't see it)
            if await check_ws_rate_limit(self, "WS_CONNECT", send_message=False):
                await self.close(code=WS_CLOSE_RATE_LIMITED)
                return

            # 1. Parse query parameters
            await self._parse_query_params()

            # 2. Validate we have at least some context
            if not self.corpus_id and not self.document_id:
                err_msg = (
                    "No context provided. Must specify corpus_id or document_id "
                    "in query parameters."
                )
                logger.error(f"[Session {self.session_id}] {err_msg}")
                await self.close(code=WS_CLOSE_UNAUTHENTICATED)
                return

            # 3. Check authentication
            # allow_anonymous=True since we allow access to public documents/corpora
            if await check_auth_and_close_if_failed(
                self, self.session_id, allow_anonymous=True
            ):
                return

            user = self.scope.get("user")
            is_authenticated = user and user.is_authenticated

            if is_authenticated:
                self.user_id = user.id

            # 4. Load corpus (if provided) — existence check only
            if self.corpus_id:
                try:
                    self.corpus = await Corpus.objects.aget(id=self.corpus_id)
                except Corpus.DoesNotExist:
                    logger.error(
                        f"[Session {self.session_id}] Corpus not found: {self.corpus_id}"
                    )
                    await self.close(code=4004)
                    return

            # 5. Load document (if provided) — existence check only
            if self.document_id:
                try:
                    self.document = await Document.objects.aget(id=self.document_id)
                except Document.DoesNotExist:
                    logger.error(
                        f"[Session {self.session_id}] Document not found: {self.document_id}"
                    )
                    await self.close(code=4004)
                    return

            # 5a. Validate access rights for the loaded resources
            if not await self._validate_resource_permissions(user):
                logger.warning(
                    f"[Session {self.session_id}] Permission denied for user "
                    f"{getattr(user, 'id', 'anonymous')} on requested resources."
                )
                await self.close(code=4003)
                return

            # 6. Resolve agent configuration
            self.agent_config = await self._resolve_agent_config()
            if not self.agent_config:
                logger.error(
                    f"[Session {self.session_id}] Could not resolve agent configuration"
                )
                await self.close(code=4004)
                return

            logger.debug(
                f"[Session {self.session_id}] Using agent: {self.agent_config.name} "
                f"(slug={self.agent_config.slug})"
            )

            # 7. Accept connection (echoes subprotocol + sends initial AUTH_OK)
            await self.accept_with_auth()
            self._is_connected = True
            logger.debug(f"[Session {self.session_id}] Connection accepted.")

        except Exception as e:
            logger.error(
                f"[Session {self.session_id}] Error during connection: {e}",
                exc_info=True,
            )
            await self.close(code=WS_CLOSE_UNAUTHENTICATED)

    async def disconnect(self, close_code: int) -> None:
        """Clean up on socket close."""
        await self.cleanup_auth_handshake()
        self._is_connected = False
        logger.debug(
            f"[UnifiedAgent {self.consumer_id} | Session {self.session_id}] "
            f"disconnect() called. Code={close_code}"
        )
        self.agent = None

    # -------------------------------------------------------------------------
    #  Resource permission validation (AuthHandshakeMixin override)
    # -------------------------------------------------------------------------

    async def _validate_resource_permissions(self, user) -> bool:
        """
        Re-run the same checks performed in connect() for the resources
        this consumer is currently bound to. Used by AuthHandshakeMixin on
        refresh to detect mid-connection access revocation.
        """
        is_authenticated = user is not None and user.is_authenticated

        if self.corpus is not None:
            if is_authenticated:
                has_perm = await database_sync_to_async(user_has_permission_for_obj)(
                    user, self.corpus, PermissionTypes.READ
                )
                if not has_perm:
                    return False
            else:
                # Anonymous fallback: re-fetch is_public from the DB rather
                # than trusting the in-memory object loaded at connect time.
                # If the owner flips the corpus to private mid-connection, an
                # anonymous AUTH refresh would otherwise pass on stale state.
                fresh_corpus = await Corpus.objects.aget(pk=self.corpus.pk)
                if not fresh_corpus.is_public:
                    return False

        if self.document is not None:
            if is_authenticated:
                has_perm = await database_sync_to_async(user_has_permission_for_obj)(
                    user, self.document, PermissionTypes.READ
                )
                if not has_perm:
                    return False
            else:
                # Same anonymous-refresh stale-read concern as the corpus
                # branch above.
                fresh_document = await Document.objects.aget(pk=self.document.pk)
                if not fresh_document.is_public:
                    return False

        return True

    # -------------------------------------------------------------------------
    #  Query param parsing
    # -------------------------------------------------------------------------

    async def _parse_query_params(self) -> None:
        """Extract and decode IDs from query string parameters."""
        query_string = self.scope.get("query_string", b"").decode("utf-8")
        params = urllib.parse.parse_qs(query_string)

        # Helper to extract and decode GraphQL global ID
        def decode_id(param_name: str) -> int | None:
            raw = params.get(param_name, [None])[0]
            if not raw:
                return None
            try:
                # Try GraphQL global ID first
                _, pk = from_global_id(raw)
                return int(pk)
            except Exception:
                # Fall back to raw integer
                try:
                    return int(raw)
                except ValueError:
                    return None

        self.corpus_id = decode_id("corpus_id")
        self.document_id = decode_id("document_id")
        self.agent_config_id = decode_id("agent_id")
        self.conversation_id = decode_id("conversation_id") or decode_id(
            "load_from_conversation_id"
        )

        logger.debug(
            f"[Session {self.session_id}] Parsed params: "
            f"corpus_id={self.corpus_id}, document_id={self.document_id}, "
            f"agent_id={self.agent_config_id}, conversation_id={self.conversation_id}"
        )

    # -------------------------------------------------------------------------
    #  Agent configuration resolution
    # -------------------------------------------------------------------------

    async def _resolve_agent_config(self) -> AgentConfiguration | None:
        """
        Resolve which agent configuration to use.

        Priority:
        1. Explicit agent_id → use that agent
        2. document_id present → default-document-agent
        3. corpus_id present → default-corpus-agent
        """
        # Priority 1: Explicit agent_id
        if self.agent_config_id:
            try:
                return await AgentConfiguration.objects.aget(
                    pk=self.agent_config_id, is_active=True
                )
            except AgentConfiguration.DoesNotExist:
                logger.error(
                    f"[Session {self.session_id}] "
                    f"Specified agent not found: {self.agent_config_id}"
                )
                return None

        # Priority 2: Document context → default document agent
        if self.document_id:
            try:
                return await AgentConfiguration.objects.aget(
                    slug="default-document-agent", is_active=True
                )
            except AgentConfiguration.DoesNotExist:
                logger.error(
                    f"[Session {self.session_id}] "
                    "Default document agent not found (slug=default-document-agent)"
                )
                return None

        # Priority 3: Corpus context → default corpus agent
        if self.corpus_id:
            try:
                return await AgentConfiguration.objects.aget(
                    slug="default-corpus-agent", is_active=True
                )
            except AgentConfiguration.DoesNotExist:
                logger.error(
                    f"[Session {self.session_id}] "
                    "Default corpus agent not found (slug=default-corpus-agent)"
                )
                return None

        return None

    # -------------------------------------------------------------------------
    #  Message sending
    # -------------------------------------------------------------------------

    async def send_standard_message(
        self,
        msg_type: MessageType,
        content: str = "",
        data: dict[str, Any] | None = None,
    ) -> None:
        """Send a standardized JSON message over the WebSocket."""
        if data is None:
            data = {}

        await self.send(
            json.dumps({"type": msg_type, "content": content, "data": data})
        )

    async def _send_safe(
        self,
        msg_type: MessageType,
        content: str = "",
        data: dict[str, Any] | None = None,
    ) -> bool:
        """
        Send a message, returning False (instead of raising) when the
        socket is already closed.  This prevents cascading exceptions
        through PydanticAI's async generators during mid-stream disconnects.
        """
        if not self._is_connected:
            return False
        try:
            await self.send_standard_message(msg_type, content, data)
            return True
        except Exception:
            self._is_connected = False
            logger.debug(
                f"[Session {self.session_id}] Send failed (client disconnected)."
            )
            return False

    # -------------------------------------------------------------------------
    #  Main message handler
    # -------------------------------------------------------------------------

    async def receive(self, text_data: str) -> None:
        """
        Handle incoming WebSocket messages.

        Expected payloads:
        - Auth refresh: {"type": "AUTH", "token": "..."}
        - Query: {"query": "user question"}
        - Approval: {"approval_decision": true/false, "llm_message_id": 123}
        """
        logger.debug(f"[Session {self.session_id}] receive(): {text_data[:200]}...")

        try:
            payload: dict[str, Any] = json.loads(text_data)
        except json.JSONDecodeError:
            await self._send_safe(
                msg_type="SYNC_CONTENT",
                data={"error": "Malformed JSON payload."},
            )
            return

        # Route AUTH refresh frames before anything else (per-connection
        # cooldown + DB-backed token validation live in handle_auth_message).
        if isinstance(payload, dict) and payload.get("type") == "AUTH":
            await self.handle_auth_message(payload)
            return

        try:
            # Handle approval workflow
            if "approval_decision" in payload:
                if await check_ws_rate_limit(
                    self, "WRITE_LIGHT", group_suffix="approval"
                ):
                    return
                await self._handle_approval_decision(payload)
                return

            # Rate limit agent queries
            if await check_ws_rate_limit(self, "AI_QUERY", group_suffix="agent_query"):
                return

            # Handle user query
            user_query: str = payload.get("query", "").strip()
            if not user_query:
                logger.warning(f"[Session {self.session_id}] Empty query received.")
                await self._send_safe(
                    msg_type="SYNC_CONTENT",
                    content="No query provided.",
                )
                return

            logger.debug(
                f"[Session {self.session_id}] Received query: '{user_query[:100]}...'"
            )

            # Initialize agent if needed
            is_new_conversation = self.agent is None and not self.conversation_id
            if self.agent is None:
                await self._initialize_agent()

            # Check for context exhaustion (anonymous ephemeral sessions only)
            if (
                self.user_id is None
                and self.agent
                and getattr(self.agent, "conversation_manager", None) is not None
                and self.agent.conversation_manager.context_exhausted
            ):
                await self._send_safe(
                    msg_type="ASYNC_ERROR",
                    content="This conversation has reached its context limit. "
                    "Please start a new chat to continue.",
                    data={
                        "error_type": WS_ERROR_CONTEXT_EXHAUSTED,
                    },
                )
                return

            # Generate title for new conversations (authenticated users only) in background
            if is_new_conversation and self.user_id:
                asyncio.create_task(self._async_set_conversation_title(user_query))

            # Stream the response
            await self._stream_agent_response(user_query)

        except Exception as e:
            logger.error(
                f"[Session {self.session_id}] Error during message processing: {e}",
                exc_info=True,
            )
            await self._send_safe(
                msg_type="SYNC_CONTENT",
                data={"error": f"Error during message processing: {e}"},
            )

    # -------------------------------------------------------------------------
    #  Agent initialization
    # -------------------------------------------------------------------------

    async def _initialize_agent(self) -> None:
        """Create the agent instance based on context and agent configuration."""
        logger.debug(f"[Session {self.session_id}] Initializing agent...")

        # Build kwargs for agent factory
        agent_kwargs: dict[str, Any] = {
            "user_id": self.user_id,
        }

        if self.conversation_id:
            agent_kwargs["conversation_id"] = self.conversation_id

        # Use system instructions from agent config if available
        if self.agent_config and self.agent_config.system_instructions:
            # Note: The agent factory methods don't currently accept custom instructions
            # This will be a future enhancement. For now, the default instructions apply.
            pass

        # Choose factory method based on context
        if self.document:
            # Document-level agent (with or without corpus)
            agent_kwargs["document"] = self.document
            agent_kwargs["corpus"] = self.corpus  # May be None for standalone

            # For standalone documents, pick embedder from existing embeddings
            if not self.corpus:
                embedder_path = await self._pick_document_embedder()
                if embedder_path:
                    agent_kwargs["embedder"] = embedder_path

            self.agent = await agents.for_document(
                **agent_kwargs, framework=settings.LLMS_DEFAULT_AGENT_FRAMEWORK
            )
        elif self.corpus:
            # Corpus-level agent
            agent_kwargs["corpus"] = self.corpus_id

            if (
                hasattr(self.corpus, "preferred_embedder")
                and self.corpus.preferred_embedder
            ):
                agent_kwargs["embedder"] = self.corpus.preferred_embedder

            self.agent = await agents.for_corpus(
                **agent_kwargs, framework=settings.LLMS_DEFAULT_AGENT_FRAMEWORK
            )
        else:
            raise ValueError("No valid context for agent initialization")

        logger.debug(
            f"[Session {self.session_id}] Agent initialized. "
            f"Conversation ID: {self.agent.get_conversation_id() if self.agent else 'N/A'}"
        )

    async def _pick_document_embedder(self) -> str | None:
        """
        For standalone documents, choose an embedder that already exists
        on the document's structural annotations.
        """
        if not self.document:
            return None

        from opencontractserver.annotations.models import Embedding

        document_id = self.document.id

        def get_embedder_paths():
            return list(
                Embedding.objects.filter(
                    annotation__document_id=document_id,
                    annotation__structural=True,
                )
                .values_list("embedder_path", flat=True)
                .distinct()
            )

        paths = await database_sync_to_async(get_embedder_paths)()

        if paths:
            logger.debug(
                f"[Session {self.session_id}] Using existing embedder: {paths[0]}"
            )
            return paths[0]
        else:
            from opencontractserver.pipeline.utils import get_default_embedder_path

            logger.debug(
                f"[Session {self.session_id}] No existing embedder found, using default"
            )
            return await database_sync_to_async(get_default_embedder_path)()

    # -------------------------------------------------------------------------
    #  Conversation title generation
    # -------------------------------------------------------------------------

    async def _generate_conversation_title(self, user_query: str) -> str:
        """
        Generate a concise conversation title based on the initial user query.
        """
        try:
            from opencontractserver.llms.client import ChatMessage, create_client

            system_prompt = (
                "You are a helpful assistant that creates very concise chat titles. "
                "Create a brief (maximum 5 words) title that captures the essence "
                "of what the user is asking about."
            )

            user_prompt = (
                f"Create a brief title for a conversation starting with this query: "
                f"{user_query}"
            )

            client = create_client()  # Uses settings defaults

            messages = [
                ChatMessage(role="system", content=system_prompt),
                ChatMessage(role="user", content=user_prompt),
            ]

            response = client.chat(messages)
            return response.content.strip()
        except Exception as e:
            logger.error(
                f"[Session {self.session_id}] Error generating conversation title: {e}"
            )
            return f"Conversation {uuid.uuid4()}"

    async def _async_set_conversation_title(self, user_query: str) -> None:
        """
        Generate and persist a title for the current conversation without
        blocking the stream.
        """
        try:
            if self.agent is None:
                return

            convo_id = self.agent.get_conversation_id()
            if convo_id:
                from opencontractserver.conversations.models import Conversation

                conversation = await Conversation.objects.aget(id=convo_id)
                if conversation and not getattr(conversation, "title", None):
                    title = await self._generate_conversation_title(user_query)
                    conversation.title = title
                    await conversation.asave(update_fields=["title"])
        except Exception as e:
            logger.error(
                f"[Session {self.session_id}] Async title generation failed: {e}",
                exc_info=True,
            )

    # -------------------------------------------------------------------------
    #  Response streaming
    # -------------------------------------------------------------------------

    async def _stream_agent_response(self, user_query: str) -> None:
        """Stream the agent's response to the client."""
        # When OC_LLM_VCR_MODE is set, wrap the LLM HTTP traffic in a vcr.py
        # cassette so the e2e websocket-auth workflow can replay a recorded
        # conversation rather than making real OpenAI/Anthropic calls.
        # In production (env vars unset) the helper is a no-op context manager.
        # Lazy import: vcrpy is a dev/CI dependency and we don't want it
        # touched on the production cold path until this code branch
        # actually runs (which itself is gated on a chat being initiated).
        from opencontractserver.utils.vcr_replay import maybe_vcr_cassette

        try:
            with maybe_vcr_cassette():
                async for event in self.agent.stream(user_query):
                    if not self._is_connected:
                        logger.debug(
                            f"[Session {self.session_id}] Client disconnected mid-stream, "
                            "stopping iteration."
                        )
                        break
                    await self._handle_agent_event(event)

            logger.debug(f"[Session {self.session_id}] Streaming complete.")

        except Exception as e:
            if not self._is_connected:
                logger.debug(
                    f"[Session {self.session_id}] Streaming interrupted by disconnect: {e}"
                )
                return
            logger.error(
                f"[Session {self.session_id}] Error during streaming: {e}",
                exc_info=True,
            )
            await self._send_safe(
                msg_type="SYNC_CONTENT",
                data={"error": f"Error during processing: {e}"},
            )

    async def _handle_agent_event(self, event: Any) -> None:
        """Handle a single agent event and send appropriate WebSocket message."""

        # Ensure ASYNC_START is sent once we have message IDs
        if getattr(event, "user_message_id", None) is not None and not hasattr(
            self, "_sent_start"
        ):
            await self._send_safe(
                msg_type="ASYNC_START",
                content="",
                data={"message_id": event.llm_message_id},
            )
            self._sent_start = True

        # Handle event types
        if isinstance(event, ThoughtEvent):
            await self._send_safe(
                msg_type="ASYNC_THOUGHT",
                content=event.thought,
                data={"message_id": event.llm_message_id, **event.metadata},
            )

        elif isinstance(event, ContentEvent):
            if event.content:
                await self._send_safe(
                    msg_type="ASYNC_CONTENT",
                    content=event.content,
                    data={"message_id": event.llm_message_id},
                )

        elif isinstance(event, SourceEvent):
            if event.sources:
                await self._send_safe(
                    msg_type="ASYNC_SOURCES",
                    content="",
                    data={
                        "message_id": event.llm_message_id,
                        "sources": [s.to_dict() for s in event.sources],
                    },
                )

        elif isinstance(event, ApprovalNeededEvent):
            await self._send_safe(
                msg_type="ASYNC_APPROVAL_NEEDED",
                content="",
                data={
                    "message_id": event.llm_message_id,
                    "pending_tool_call": event.pending_tool_call,
                    "tool_name": getattr(event, "tool_name", None),
                    "tool_description": getattr(event, "tool_description", None),
                    "tool_arguments": getattr(event, "tool_arguments", None),
                },
            )

        elif isinstance(event, ApprovalResultEvent):
            await self._send_safe(
                msg_type="ASYNC_APPROVAL_RESULT",
                content="",
                data={
                    "message_id": event.llm_message_id,
                    "decision": event.decision,
                    "pending_tool_call": event.pending_tool_call,
                },
            )

        elif isinstance(event, ResumeEvent):
            await self._send_safe(
                msg_type="ASYNC_RESUME",
                content="",
                data={"message_id": event.llm_message_id},
            )

        elif isinstance(event, ErrorEvent):
            await self._send_safe(
                msg_type="ASYNC_ERROR",
                content="",
                data={
                    "error": event.error or "Unknown error",
                    "message_id": event.llm_message_id,
                    "metadata": event.metadata,
                },
            )
            if hasattr(self, "_sent_start"):
                delattr(self, "_sent_start")

        elif isinstance(event, FinalEvent):
            sources_payload = [s.to_dict() for s in event.sources]
            await self._send_safe(
                msg_type="ASYNC_FINISH",
                content=event.accumulated_content or event.content,
                data={
                    "sources": sources_payload,
                    "message_id": event.llm_message_id,
                    "timeline": (
                        event.metadata.get("timeline", [])
                        if isinstance(event.metadata, dict)
                        else []
                    ),
                    "context_status": (
                        event.metadata.get("context_status")
                        if isinstance(event.metadata, dict)
                        else None
                    ),
                },
            )
            if hasattr(self, "_sent_start"):
                delattr(self, "_sent_start")

        else:
            # Legacy path for frameworks yielding UnifiedStreamResponse
            if hasattr(event, "content") and event.content:
                await self._send_safe(
                    msg_type="ASYNC_CONTENT",
                    content=str(event.content),
                    data={"message_id": getattr(event, "llm_message_id", None)},
                )

            if getattr(event, "is_complete", False):
                sources_payload = []
                if hasattr(event, "sources") and event.sources:
                    sources_payload = [s.to_dict() for s in event.sources]

                await self._send_safe(
                    msg_type="ASYNC_FINISH",
                    content=getattr(event, "accumulated_content", ""),
                    data={
                        "sources": sources_payload,
                        "message_id": getattr(event, "llm_message_id", None),
                        "timeline": (
                            event.metadata.get("timeline", [])
                            if isinstance(getattr(event, "metadata", None), dict)
                            else []
                        ),
                    },
                )
                if hasattr(self, "_sent_start"):
                    delattr(self, "_sent_start")

    # -------------------------------------------------------------------------
    #  Approval workflow
    # -------------------------------------------------------------------------

    async def _handle_approval_decision(self, payload: dict[str, Any]) -> None:
        """
        Process an approval/rejection from the frontend.

        Expected payload:
        {
            "approval_decision": true | false,
            "llm_message_id": 123
        }
        """
        approved: bool = bool(payload.get("approval_decision"))
        llm_msg_id = payload.get("llm_message_id")

        if llm_msg_id is None:
            await self._send_safe(
                msg_type="SYNC_CONTENT",
                data={"error": "llm_message_id missing in approval payload"},
            )
            return

        if self.agent is None:
            await self._send_safe(
                msg_type="SYNC_CONTENT",
                data={"error": "Agent not initialized for approval"},
            )
            return

        # Same VCR wrap as _stream_agent_response so the approval-resume
        # leg also replays cassette traffic when OC_LLM_VCR_MODE is set.
        # Lazy import: see _stream_agent_response for rationale (vcrpy is a
        # dev/CI dep we don't want imported on the production cold path).
        from opencontractserver.utils.vcr_replay import maybe_vcr_cassette

        try:
            with maybe_vcr_cassette():
                # Stream the resumed answer
                async for event in self.agent.resume_with_approval(
                    llm_msg_id, approved, stream=True
                ):
                    if not self._is_connected:
                        logger.debug(
                            f"[Session {self.session_id}] Client disconnected during approval stream."
                        )
                        break
                    await self._handle_agent_event(event)

        except Exception as e:
            if not self._is_connected:
                logger.debug(
                    f"[Session {self.session_id}] Approval stream interrupted by disconnect."
                )
                return
            logger.error(
                f"[Session {self.session_id}] Approval resume error: {e}",
                exc_info=True,
            )
            await self._send_safe(
                msg_type="SYNC_CONTENT",
                data={"error": f"Failed to resume after approval: {e}"},
            )
