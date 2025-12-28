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

import json
import logging
import urllib.parse
import uuid
from typing import Any

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.conf import settings
from graphql_relay import from_global_id

from config.websocket.middleware import WS_CLOSE_UNAUTHENTICATED
from config.websocket.ratelimits import (
    WebSocketRateLimits,
    check_rate_limit_async,
    parse_rate,
    period_to_name,
)
from config.websocket.utils.auth_helpers import check_auth_and_close_if_failed
from opencontractserver.agents.models import AgentConfiguration
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


class UnifiedAgentConsumer(AsyncWebsocketConsumer):
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

            # 4. Load and validate corpus (if provided)
            if self.corpus_id:
                try:
                    self.corpus = await Corpus.objects.aget(id=self.corpus_id)
                    if is_authenticated:
                        has_perm = await database_sync_to_async(
                            user_has_permission_for_obj
                        )(user, self.corpus, PermissionTypes.READ)
                        if not has_perm:
                            logger.warning(
                                f"[Session {self.session_id}] User {user.id} "
                                f"lacks read permission on Corpus {self.corpus_id}"
                            )
                            await self.close(code=4003)
                            return
                    elif not self.corpus.is_public:
                        logger.warning(
                            f"[Session {self.session_id}] Anonymous user "
                            f"accessing non-public Corpus {self.corpus_id}"
                        )
                        await self.close(code=4003)
                        return
                except Corpus.DoesNotExist:
                    logger.error(
                        f"[Session {self.session_id}] Corpus not found: {self.corpus_id}"
                    )
                    await self.close(code=4004)
                    return

            # 5. Load and validate document (if provided)
            if self.document_id:
                try:
                    self.document = await Document.objects.aget(id=self.document_id)
                    if is_authenticated:
                        has_perm = await database_sync_to_async(
                            user_has_permission_for_obj
                        )(user, self.document, PermissionTypes.READ)
                        if not has_perm:
                            logger.warning(
                                f"[Session {self.session_id}] User {user.id} "
                                f"lacks read permission on Document {self.document_id}"
                            )
                            await self.close(code=4003)
                            return
                    elif not self.document.is_public:
                        logger.warning(
                            f"[Session {self.session_id}] Anonymous user "
                            f"accessing non-public Document {self.document_id}"
                        )
                        await self.close(code=4003)
                        return
                except Document.DoesNotExist:
                    logger.error(
                        f"[Session {self.session_id}] Document not found: {self.document_id}"
                    )
                    await self.close(code=4004)
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

            # 7. Accept connection
            await self.accept()
            logger.debug(f"[Session {self.session_id}] Connection accepted.")

        except Exception as e:
            logger.error(
                f"[Session {self.session_id}] Error during connection: {e}",
                exc_info=True,
            )
            await self.close(code=WS_CLOSE_UNAUTHENTICATED)

    async def disconnect(self, close_code: int) -> None:
        """Clean up on socket close."""
        logger.debug(
            f"[UnifiedAgent {self.consumer_id} | Session {self.session_id}] "
            f"disconnect() called. Code={close_code}"
        )
        self.agent = None

    # -------------------------------------------------------------------------
    #  Rate limiting
    # -------------------------------------------------------------------------

    async def _check_message_rate_limit(self) -> bool:
        """
        Check if the current message is within rate limits.

        Uses WS_AI_QUERY rate for AI agent queries.

        Returns:
            True if message is allowed, False if rate limited
        """
        if getattr(settings, "RATELIMIT_DISABLE", False):
            return True

        user = self.scope.get("user")
        rate = WebSocketRateLimits.get_rate_for_user("WS_AI_QUERY", user)

        is_limited, info = await check_rate_limit_async(
            self.scope, "ws_ai_query", rate, increment=True
        )

        if is_limited:
            count, period = parse_rate(rate)
            period_name_str = period_to_name(period)

            error_msg = (
                f"Rate limit exceeded: Max {count} AI queries per {period_name_str}. "
                "Please wait before sending another query."
            )

            logger.warning(
                f"[Session {self.session_id}] Message rate limited - "
                f"Key: {info.get('key', 'unknown')}, Rate: {rate}"
            )

            await self.send_standard_message(
                msg_type="RATE_LIMITED",
                content=error_msg,
                data={
                    "limit": info.get("limit", 0),
                    "remaining": 0,
                    "retry_after": info.get("reset_time", 60),
                },
            )
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

    # -------------------------------------------------------------------------
    #  Main message handler
    # -------------------------------------------------------------------------

    async def receive(self, text_data: str) -> None:
        """
        Handle incoming WebSocket messages.

        Expected payloads:
        - Query: {"query": "user question"}
        - Approval: {"approval_decision": true/false, "llm_message_id": 123}
        """
        logger.debug(f"[Session {self.session_id}] receive(): {text_data[:200]}...")

        # Check message rate limit
        if not await self._check_message_rate_limit():
            return

        try:
            payload: dict[str, Any] = json.loads(text_data)

            # Handle approval workflow
            if "approval_decision" in payload:
                await self._handle_approval_decision(payload)
                return

            # Handle user query
            user_query: str = payload.get("query", "").strip()
            if not user_query:
                logger.warning(f"[Session {self.session_id}] Empty query received.")
                await self.send_standard_message(
                    msg_type="SYNC_CONTENT",
                    content="No query provided.",
                )
                return

            logger.debug(
                f"[Session {self.session_id}] Received query: '{user_query[:100]}...'"
            )

            # Initialize agent if needed
            if self.agent is None:
                await self._initialize_agent()

            # Stream the response
            await self._stream_agent_response(user_query)

        except json.JSONDecodeError:
            await self.send_standard_message(
                msg_type="SYNC_CONTENT",
                data={"error": "Malformed JSON payload."},
            )
        except Exception as e:
            logger.error(
                f"[Session {self.session_id}] Error during message processing: {e}",
                exc_info=True,
            )
            await self.send_standard_message(
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
            logger.debug(
                f"[Session {self.session_id}] No existing embedder found, using default"
            )
            return settings.DEFAULT_EMBEDDER

    # -------------------------------------------------------------------------
    #  Response streaming
    # -------------------------------------------------------------------------

    async def _stream_agent_response(self, user_query: str) -> None:
        """Stream the agent's response to the client."""
        try:
            async for event in self.agent.stream(user_query):
                await self._handle_agent_event(event)

            logger.debug(f"[Session {self.session_id}] Streaming complete.")

        except Exception as e:
            logger.error(
                f"[Session {self.session_id}] Error during streaming: {e}",
                exc_info=True,
            )
            await self.send_standard_message(
                msg_type="SYNC_CONTENT",
                data={"error": f"Error during processing: {e}"},
            )

    async def _handle_agent_event(self, event: Any) -> None:
        """Handle a single agent event and send appropriate WebSocket message."""

        # Ensure ASYNC_START is sent once we have message IDs
        if getattr(event, "user_message_id", None) is not None and not hasattr(
            self, "_sent_start"
        ):
            await self.send_standard_message(
                msg_type="ASYNC_START",
                content="",
                data={"message_id": event.llm_message_id},
            )
            self._sent_start = True

        # Handle event types
        if isinstance(event, ThoughtEvent):
            await self.send_standard_message(
                msg_type="ASYNC_THOUGHT",
                content=event.thought,
                data={"message_id": event.llm_message_id, **event.metadata},
            )

        elif isinstance(event, ContentEvent):
            if event.content:
                await self.send_standard_message(
                    msg_type="ASYNC_CONTENT",
                    content=event.content,
                    data={"message_id": event.llm_message_id},
                )

        elif isinstance(event, SourceEvent):
            if event.sources:
                await self.send_standard_message(
                    msg_type="ASYNC_SOURCES",
                    content="",
                    data={
                        "message_id": event.llm_message_id,
                        "sources": [s.to_dict() for s in event.sources],
                    },
                )

        elif isinstance(event, ApprovalNeededEvent):
            await self.send_standard_message(
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
            await self.send_standard_message(
                msg_type="ASYNC_APPROVAL_RESULT",
                content="",
                data={
                    "message_id": event.llm_message_id,
                    "decision": event.decision,
                    "pending_tool_call": event.pending_tool_call,
                },
            )

        elif isinstance(event, ResumeEvent):
            await self.send_standard_message(
                msg_type="ASYNC_RESUME",
                content="",
                data={"message_id": event.llm_message_id},
            )

        elif isinstance(event, ErrorEvent):
            await self.send_standard_message(
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
            await self.send_standard_message(
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
                },
            )
            if hasattr(self, "_sent_start"):
                delattr(self, "_sent_start")

        else:
            # Legacy path for frameworks yielding UnifiedStreamResponse
            if hasattr(event, "content") and event.content:
                await self.send_standard_message(
                    msg_type="ASYNC_CONTENT",
                    content=str(event.content),
                    data={"message_id": getattr(event, "llm_message_id", None)},
                )

            if getattr(event, "is_complete", False):
                sources_payload = []
                if hasattr(event, "sources") and event.sources:
                    sources_payload = [s.to_dict() for s in event.sources]

                await self.send_standard_message(
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
            await self.send_standard_message(
                msg_type="SYNC_CONTENT",
                data={"error": "llm_message_id missing in approval payload"},
            )
            return

        if self.agent is None:
            await self.send_standard_message(
                msg_type="SYNC_CONTENT",
                data={"error": "Agent not initialized for approval"},
            )
            return

        try:
            # Stream the resumed answer
            async for event in self.agent.resume_with_approval(
                llm_msg_id, approved, stream=True
            ):
                await self._handle_agent_event(event)

        except Exception as e:
            logger.error(
                f"[Session {self.session_id}] Approval resume error: {e}",
                exc_info=True,
            )
            await self.send_standard_message(
                msg_type="SYNC_CONTENT",
                data={"error": f"Failed to resume after approval: {e}"},
            )
