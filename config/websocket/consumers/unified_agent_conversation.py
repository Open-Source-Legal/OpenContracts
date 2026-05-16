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
from opencontractserver.llms.agents.mention_extractor import (
    ExtractedMention,
    extract_agent_mentions,
)
from opencontractserver.llms.tools.delegation_tools import (
    StreamRelay,
    build_delegation_tool,
    filter_by_scope,
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
        # Pending approval futures keyed by
        # ``(llm_message_id, requesting_agent_id_or_None)``.  The conductor's
        # own approval uses ``None`` as the agent component; sub-agent
        # approvals use the AgentConfiguration's pk.  Routing in
        # ``_handle_approval_decision`` checks the future map first; on a hit
        # it fulfils the future (resuming the sub-agent) and on a miss it
        # falls through to the legacy ``self.agent.resume_with_approval``
        # path.
        self._pending_approvals: dict[tuple[int, int | None], asyncio.Future] = {}
        # Tracks whether the conductor was built with ``delegate_to_<slug>``
        # tools on the previous turn.  Used to force a clean rebuild on the
        # next turn-without-mentions so stale delegation tools don't leak
        # into a turn the user didn't intend them for.
        self._had_delegation_tools_last_turn: bool = False
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
        """Clean up on socket close.

        Cancels any in-flight sub-agent approval futures BEFORE clearing the
        agent reference so awaiting delegation tool bodies unwind cleanly
        instead of leaking asyncio tasks and leaving ``AWAITING_APPROVAL``
        rows pinned forever.  ``on_approval``'s ``CancelledError`` handler
        already pops each entry, so cancellation propagates without leaks.
        """
        await self.cleanup_auth_handshake()
        self._is_connected = False
        logger.debug(
            f"[UnifiedAgent {self.consumer_id} | Session {self.session_id}] "
            f"disconnect() called. Code={close_code}"
        )
        for future in list(self._pending_approvals.values()):
            if not future.done():
                future.cancel()
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
        1. Explicit agent_id → use that agent (gated by ``visible_to_user``)
        2. document_id present → default-document-agent
        3. corpus_id present → default-corpus-agent

        The explicit-agent path uses ``visible_to_user`` rather than a bare
        ``aget(pk=...)`` so a caller can't load another user's private agent
        by guessing the pk. The default agents are GLOBAL/active so the
        guard isn't load-bearing for paths 2/3.
        """
        # Priority 1: Explicit agent_id (visibility-gated)
        if self.agent_config_id:
            user = self.scope.get("user")

            def _visible_agent_lookup() -> AgentConfiguration | None:
                return (
                    AgentConfiguration.objects.visible_to_user(user)
                    .filter(pk=self.agent_config_id, is_active=True)
                    .first()
                )

            agent_config = await database_sync_to_async(_visible_agent_lookup)()
            if agent_config is None:
                logger.error(
                    f"[Session {self.session_id}] "
                    f"Specified agent not found or not visible: {self.agent_config_id}"
                )
                return None
            return agent_config

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

            # Resolve @-mentioned delegation targets BEFORE we touch the
            # agent so the conductor can be rebuilt with the right tool set
            # for this turn.  Silent fallback: invisible / out-of-scope
            # mentions are dropped without surfacing to the user.
            mentions = extract_agent_mentions(user_query)
            delegation_targets: list[AgentConfiguration] = (
                await self._resolve_delegation_targets(mentions) if mentions else []
            )

            # Track whether the conductor is being created fresh on this turn
            # for downstream title-generation gating.
            is_new_conversation = self.agent is None and not self.conversation_id

            # Per-turn conductor (re)build whenever delegation tools are
            # needed.  Even if the agent was created on a previous turn
            # without delegation tools, we rebuild here so the conductor
            # gets fresh ``delegate_to_<slug>`` tools wired in.  Conversation
            # state is preserved because we pass ``conversation_id=``
            # through ``_initialize_agent`` (cached after first build).
            relay_factory: Any = None
            parent_message_id_box: dict[str, int | None] | None = None
            if delegation_targets:
                # Allocate the shared one-slot ``parent_message_id`` box and
                # pass it through the factory AND into ``_stream_agent_response``;
                # the stream helper latches the conductor's message id into it
                # on the first streamed event so sub-agent relay closures see
                # the right ``parent_message_id`` for attribution.
                parent_message_id_box = self._make_parent_message_id_box()
                relay_factory = self._build_stream_relay_factory(
                    parent_message_id_box=parent_message_id_box,
                )
                # Build the delegation tools.  Sub-agents do not share history
                # with the conductor per the spec; the body builds an
                # ephemeral sub-agent on invocation.
                delegation_tools = [
                    build_delegation_tool(
                        agent,
                        relay_factory=relay_factory,
                        user=self.scope.get("user"),
                        corpus=self.corpus,
                        document=self.document,
                    )
                    for agent in delegation_targets
                ]
                # Snake-case normalization of slugs (``my-agent`` and
                # ``my_agent`` both → ``delegate_to_my_agent``) means two
                # in-scope agents could in principle produce the same tool
                # name.  ``AgentConfiguration.slug`` is ``SlugField(unique=True)``
                # and ``save()`` normalizes to ``-`` so the normal path can't
                # produce a collision, but admin/fixture/management-command
                # writes that bypass ``save()`` can.  Dedup defensively here so
                # the conductor never sees two ``CoreTool`` instances with
                # identical names (which would silently shadow each other in
                # pydantic-ai's tool registry).  Keep the first; warn loud on
                # the rest so the underlying data issue is visible.
                seen_tool_names: dict[str, Any] = {}
                for tool in delegation_tools:
                    if tool.name in seen_tool_names:
                        logger.warning(
                            "[delegate] Duplicate delegation tool name %r — "
                            "dropping later instance. This indicates two "
                            "AgentConfiguration slugs collide after "
                            "snake-case normalization (e.g. 'my-agent' and "
                            "'my_agent'); fix the slug in the DB.",
                            tool.name,
                        )
                        continue
                    seen_tool_names[tool.name] = tool
                delegation_tools = list(seen_tool_names.values())
                # Recreate the conductor with the augmented tool list.  The
                # cached ``self.conversation_id`` (set in ``_initialize_agent``)
                # threads the existing chat state through so we don't fork a
                # new conversation per turn.
                await self._initialize_agent(extra_tools=delegation_tools)
                self._had_delegation_tools_last_turn = True
            elif self.agent is None or self._had_delegation_tools_last_turn:
                # Rebuild clean if either (a) we have no agent yet, or
                # (b) the previous turn attached ``delegate_to_<slug>`` tools.
                # Without this, stale delegation tools would remain wired to
                # the conductor across turns the user did NOT intend them for,
                # letting the LLM silently invoke a previously-mentioned agent.
                await self._initialize_agent()
                self._had_delegation_tools_last_turn = False

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

            # Stream the response.  When delegation is active for this turn,
            # ``parent_message_id_box`` is the shared one-slot box the stream
            # helper latches the conductor's first ``llm_message_id`` into so
            # sub-agent relay closures see the right ``parent_message_id`` for
            # attribution. ``None`` otherwise — the helper is no-op for the box.
            await self._stream_agent_response(
                user_query, parent_message_id_box=parent_message_id_box
            )

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

    async def _initialize_agent(
        self,
        *,
        extra_tools: list[Any] | None = None,
    ) -> None:
        """Create the agent instance based on context and agent configuration.

        Args:
            extra_tools: Per-turn tools to append to the conductor's tool
                list (used for ``delegate_to_<slug>`` injection).  The base
                agent factory still resolves its standard tool set; these are
                appended on top.  Tools must be ``CoreTool`` instances or
                callables — strings are not supported here.

        Note:
            ``PydanticAIDocumentAgent.create`` / ``PydanticAICorpusAgent.create``
            build the registry-derived "auto" tools (vector search,
            note retrieval, custom budget-aware tools, etc.) into the agent's
            ``effective_tools`` and then merge any caller-supplied ``tools``
            via ``deduplicate_tools(effective_tools, tools, context="Caller")``.
            That is — passing ``extra_tools=[...]`` here MERGES with the
            default tool set, it does NOT replace it.  Document and corpus
            retrieval tools remain available on delegation turns.
        """
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

        if extra_tools:
            agent_kwargs["tools"] = list(extra_tools)

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

        # Cache the live conversation_id once so subsequent per-turn rebuilds
        # (for delegation tool injection) reuse the same conversation
        # without us having to re-thread it through the connect-time params.
        try:
            live_convo_id = self.agent.get_conversation_id()
        except Exception:
            live_convo_id = None
        if live_convo_id and not self.conversation_id:
            self.conversation_id = live_convo_id

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
    #  Delegation: scope resolution + StreamRelay factory
    # -------------------------------------------------------------------------

    async def _resolve_delegation_targets(
        self, mentions: list[ExtractedMention]
    ) -> list[AgentConfiguration]:
        """Filter mentions to the agents visible AND in-scope for this chat.

        Silently drops any mention whose target is invisible to the current
        user or out-of-scope for the chat (corpus-scoped agent referenced
        from a different corpus, etc.).  Returns the AgentConfiguration
        rows in the order their slugs appear in ``mentions``; duplicates
        are removed.
        """
        slugs = [m.slug for m in mentions if m.slug]
        if not slugs:
            return []

        user = self.scope.get("user")
        corpus_id = self.corpus_id
        document_id = self.document_id

        def _lookup() -> list[AgentConfiguration]:
            qs = AgentConfiguration.objects.visible_to_user(user).filter(
                slug__in=slugs, is_active=True
            )
            scoped = filter_by_scope(qs, corpus_id=corpus_id, document_id=document_id)
            by_slug = {a.slug: a for a in scoped}
            ordered: list[AgentConfiguration] = []
            seen: set[str] = set()
            for slug in slugs:
                if slug in by_slug and slug not in seen:
                    seen.add(slug)
                    ordered.append(by_slug[slug])
            return ordered

        return await database_sync_to_async(_lookup)()

    def _make_parent_message_id_box(self) -> dict[str, int | None]:
        """Allocate a one-slot dict used to share the conductor's message id
        with the delegation tool's relay closure once the conductor starts
        streaming.  ``_handle_agent_event`` fills this slot when it sees
        the first event with an ``llm_message_id``.
        """
        return {"value": None}

    def _build_stream_relay_factory(
        self,
        *,
        parent_message_id_box: dict[str, int | None],
    ):
        """Return a callable that produces a ``StreamRelay`` per delegation.

        The relay forwards sub-agent events through ``self._send_safe`` with
        ``data.agent_id`` / ``data.parent_message_id`` /
        ``data.requesting_agent`` enrichment so the frontend can attribute
        sub-agent frames to the right pinned bubble (when ``pin=True``) or
        timeline entry (when ``pin=False``).
        """
        consumer = self

        def _factory(agent: AgentConfiguration, pin: bool) -> StreamRelay:
            # ``slug`` + ``name`` only — the internal DB pk is intentionally not
            # part of the wire chip; consumers attribute by slug.
            agent_chip = {
                "slug": agent.slug,
                "name": agent.name,
            }

            async def on_token(text: str) -> None:
                # Only pinned sub-agents emit ASYNC_CONTENT (their pinned
                # bubble is the visual target).  Timeline-only delegations
                # surface as the conductor's tool_call/tool_result and don't
                # need a separate token stream.
                if not pin or not text:
                    return
                await consumer._send_safe(
                    msg_type="ASYNC_CONTENT",
                    content=text,
                    data={
                        "agent_id": agent.pk,
                        "parent_message_id": parent_message_id_box.get("value"),
                    },
                )

            async def on_thought(thought_text: str, metadata: dict) -> None:
                # Forward sub-agent thoughts only for pinned delegations
                # (so the pinned bubble can show progress); unpinned
                # delegations surface the conductor's own tool call
                # via timeline, so we don't double-emit here.
                if not pin:
                    return
                await consumer._send_safe(
                    msg_type="ASYNC_THOUGHT",
                    content=thought_text or "",
                    data={
                        "agent_id": agent.pk,
                        "parent_message_id": parent_message_id_box.get("value"),
                        **(metadata or {}),
                    },
                )

            async def on_approval(pending_tool_call: dict) -> dict[str, Any]:
                """Bridge sub-agent approval requests through the WebSocket.

                Registers a future keyed by ``(parent_message_id, agent.pk)``
                so ``_handle_approval_decision`` can resolve it when the user
                responds.  Emits ``ASYNC_APPROVAL_NEEDED`` carrying
                ``requesting_agent`` attribution and returns the decision
                payload to the delegation tool body, which then drives
                ``sub_agent.resume_with_approval(...)``.
                """
                parent_id = parent_message_id_box.get("value")
                if parent_id is None:
                    # Should not happen — conductor must have emitted at
                    # least one event before its tool can fire — but guard
                    # against a misuse where the relay is invoked too early.
                    # Tag the decision with ``_error`` so the delegation
                    # body's error guard surfaces this as a proper tool-call
                    # failure (`Sub-agent error: ...`) rather than a silent
                    # empty result that the conductor LLM could
                    # mis-interpret as a successful no-op.
                    logger.warning(
                        "[Session %s] Sub-agent approval requested before "
                        "conductor message id was known; aborting delegation.",
                        consumer.session_id,
                    )
                    return {
                        "approved": False,
                        "llm_message_id": None,
                        "_error": (
                            "Sub-agent approval was requested before the "
                            "conductor emitted its first event; cannot route "
                            "the request to the user."
                        ),
                    }

                future: asyncio.Future = asyncio.get_running_loop().create_future()
                key = (parent_id, agent.pk)
                # Invariant: two sub-agents of the same conductor turn cannot
                # simultaneously hold the same ``(parent_message_id, agent.pk)``
                # key — each sub-agent is built fresh per turn and ``key``
                # collapses to one future at most.  Guard with an explicit
                # check (rather than a comment-only assumption) so a future
                # refactor that re-enters this path twice gets a loud error
                # instead of silently leaking the previous pending future.
                if key in consumer._pending_approvals:
                    logger.error(
                        "[Session %s] Duplicate approval future for "
                        "(parent=%s, agent=%s); cancelling the previous one "
                        "to avoid a leaked Future.",
                        consumer.session_id,
                        parent_id,
                        agent.pk,
                    )
                    consumer._pending_approvals[key].cancel()
                consumer._pending_approvals[key] = future

                await consumer._send_safe(
                    msg_type="ASYNC_APPROVAL_NEEDED",
                    content="",
                    data={
                        "message_id": parent_id,
                        "pending_tool_call": pending_tool_call,
                        "tool_name": (pending_tool_call or {}).get("name"),
                        "tool_arguments": (pending_tool_call or {}).get("arguments"),
                        "requesting_agent": agent_chip,
                    },
                )

                try:
                    decision = await future
                except asyncio.CancelledError:
                    consumer._pending_approvals.pop(key, None)
                    raise
                finally:
                    consumer._pending_approvals.pop(key, None)

                return decision

            async def on_finish(final_text: str) -> int | None:
                """Persist the sub-agent's reply (pinned only) and emit ASYNC_FINISH.

                Single control path keyed off ``pin``:
                  - ``pin=False``: skip persistence AND skip the
                    ASYNC_FINISH frame entirely — the conductor's own
                    tool_call/tool_result pair already captures the
                    delegation in the parent's timeline.
                  - ``pin=True``: emit ASYNC_FINISH so the pinned bubble
                    closes cleanly.  Persistence is attempted only when
                    ``conversation_id`` AND ``user_id`` are set (i.e. an
                    authenticated, conversation-backed turn).  Anonymous
                    ephemeral sessions can't persist a ChatMessage row but
                    the FINISH frame is still useful for the in-memory
                    chat state on the client.
                """
                if not pin:
                    return None

                pinned_message_id: int | None = None
                persistence_failed: bool = False
                if consumer.conversation_id and consumer.user_id is not None:
                    from opencontractserver.conversations.models import (
                        ChatMessage as _ChatMessage,
                    )
                    from opencontractserver.conversations.models import (
                        MessageStateChoices as _MessageStateChoices,
                    )
                    from opencontractserver.conversations.models import (
                        MessageTypeChoices as _MessageTypeChoices,
                    )

                    conversation_id = consumer.conversation_id
                    user_id = consumer.user_id
                    parent_id = parent_message_id_box.get("value")

                    def _persist() -> int | None:
                        message = _ChatMessage.objects.create(
                            conversation_id=conversation_id,
                            msg_type=_MessageTypeChoices.LLM,
                            content=final_text or "",
                            agent_configuration=agent,
                            parent_message_id=parent_id,
                            creator_id=user_id,
                            state=_MessageStateChoices.COMPLETED,
                            data={
                                "pinned": True,
                                "delegated_from": parent_id,
                                "agent_slug": agent.slug,
                            },
                        )
                        return message.id

                    try:
                        pinned_message_id = await database_sync_to_async(_persist)()
                    except Exception:  # pragma: no cover - defensive
                        logger.warning(
                            "[Session %s] Failed to persist pinned sub-agent "
                            "ChatMessage for agent %s",
                            consumer.session_id,
                            agent.slug,
                            exc_info=True,
                        )
                        pinned_message_id = None
                        persistence_failed = True

                # Surface persistence failure as a distinct flag so the UI can
                # warn the user that the pinned bubble exists only in-memory
                # for this session and will not survive a reload. Without
                # this flag the frontend sees a complete-looking response
                # and the discrepancy is only discovered on reload.
                await consumer._send_safe(
                    msg_type="ASYNC_FINISH",
                    content=final_text or "",
                    data={
                        "agent_id": agent.pk,
                        "parent_message_id": parent_message_id_box.get("value"),
                        "pinned_message_id": pinned_message_id,
                        "persistence_failed": persistence_failed,
                        "sources": [],
                        "timeline": [],
                    },
                )

                return pinned_message_id

            return StreamRelay(
                agent=agent,
                pin=pin,
                on_token=on_token,
                on_thought=on_thought,
                on_approval=on_approval,
                on_finish=on_finish,
            )

        return _factory

    # -------------------------------------------------------------------------
    #  Response streaming
    # -------------------------------------------------------------------------

    async def _stream_agent_response(
        self,
        user_query: str,
        *,
        parent_message_id_box: dict[str, int | None] | None = None,
    ) -> None:
        """Stream the agent's response to the client.

        Args:
            user_query: The user's text query.
            parent_message_id_box: Optional one-slot shared box (typically
                produced by ``_make_parent_message_id_box`` and also passed
                into ``_build_stream_relay_factory`` for the same turn).
                When provided, the conductor's first streamed ``llm_message_id``
                is latched into ``box["value"]`` so sub-agent relay closures
                can attribute their frames to this ``parent_message_id``.
                Passing this directly (rather than reading it back off the
                relay factory) keeps the contract explicit and dodges the
                fragile monkey-patch pattern that hid the box on a private
                attribute of the factory callable.
        """
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
                    # Latch the conductor's id into the relay box on the
                    # first event that carries one (typically the first
                    # ContentEvent / ThoughtEvent).  Sub-agent frames are
                    # then attributed to this parent_message_id.
                    if (
                        parent_message_id_box is not None
                        and parent_message_id_box.get("value") is None
                        and getattr(event, "llm_message_id", None) is not None
                    ):
                        parent_message_id_box["value"] = event.llm_message_id
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

        The pending-approval map is keyed by ``(llm_message_id,
        requesting_agent_id_or_None)``.  Conductor approvals use ``None`` for
        the agent component; sub-agent approvals use the AgentConfiguration
        pk.  We first look for ANY future keyed under the supplied message
        id — a sub-agent future wins because its presence implies the
        conductor is currently blocked inside a delegate_to_<slug> tool call
        waiting on this decision — and fall through to
        ``self.agent.resume_with_approval`` for the conductor path.

        Safety: conductor + sub-agent approvals cannot collide under the
        same ``llm_message_id``.  Sub-agent approvals are awaited inside
        the delegation tool body (see
        ``opencontractserver.llms.tools.delegation_tools.build_delegation_tool``);
        because that body runs synchronously inside the conductor's tool
        call, the conductor cannot proceed to its OWN approval-gated tool
        call until all sub-agents have either resolved or errored.  Hence
        the sub-agent future is always drained from
        ``self._pending_approvals`` before the conductor can register one
        of its own, making the routing unambiguous by construction.
        """
        approved: bool = bool(payload.get("approval_decision"))
        llm_msg_id = payload.get("llm_message_id")

        if llm_msg_id is None:
            await self._send_safe(
                msg_type="SYNC_CONTENT",
                data={"error": "llm_message_id missing in approval payload"},
            )
            return

        # Sub-agent path: find any sub-agent future registered under this
        # message id and fulfil it.  The delegation tool body is awaiting
        # the resolved decision and will call
        # ``sub_agent.resume_with_approval`` itself.
        # The first-match break is sound under our asyncio single-threaded
        # invariant: a sub-agent's ``relay.on_approval`` awaits the future
        # synchronously inside the delegation tool body, which itself blocks
        # the conductor's tool call. Two sub-agents from the same turn
        # therefore can't both be awaiting approval simultaneously; only one
        # entry will ever match ``(llm_msg_id, *)`` here.
        sub_agent_key: tuple[int, int | None] | None = None
        for key in list(self._pending_approvals.keys()):
            if key[0] == llm_msg_id and key[1] is not None:
                sub_agent_key = key
                break

        if sub_agent_key is not None:
            future = self._pending_approvals.pop(sub_agent_key, None)
            if future is not None and not future.done():
                # Emit ASYNC_APPROVAL_RESULT so the UI can clear the
                # pending state on the requesting agent's chip.  We don't
                # know the real sub-agent message id, so we echo the
                # conductor's parent id.
                await self._send_safe(
                    msg_type="ASYNC_APPROVAL_RESULT",
                    content="",
                    data={
                        "message_id": llm_msg_id,
                        "decision": "approved" if approved else "rejected",
                        "requesting_agent_id": sub_agent_key[1],
                    },
                )
                future.set_result({"approved": approved, "llm_message_id": llm_msg_id})
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
