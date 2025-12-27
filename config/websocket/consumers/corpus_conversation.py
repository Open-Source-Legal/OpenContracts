from __future__ import annotations

"""
CorpusQueryConsumer

Channels WebSocket consumer that lets the frontend query a corpus via an
LLM-backed agent.  Uses the new unified LLM agent API (`opencontractserver.llms.agents`)
so the consumer is framework-agnostic (Pydantic-AI, …).

The consumer keeps the websocket protocol identical to the old version, emitting
four message-types expected by the UI:

• ASYNC_START
• ASYNC_CONTENT
• ASYNC_FINISH
• SYNC_CONTENT
"""

import json
import logging
import urllib.parse
import uuid
from typing import Any

from channels.generic.websocket import AsyncWebsocketConsumer
from django.conf import settings
from graphql_relay import from_global_id

from config.websocket.middleware import WS_CLOSE_UNAUTHENTICATED
from config.websocket.ratelimits import (
    WebSocketRateLimits,
    check_rate_limit_async,
    parse_rate,
)
from config.websocket.utils.auth_helpers import check_auth_and_close_if_failed
from config.websocket.utils.extract_ids import extract_websocket_path_id
from opencontractserver.conversations.models import MessageType
from opencontractserver.corpuses.models import Corpus
from opencontractserver.llms import agents

logger = logging.getLogger(__name__)


class CorpusQueryConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer that streams answers to corpus-level questions.

    The first request initialises an agent (lazy); subsequent requests reuse the
    same agent so that conversation context is preserved across websocket
    messages.
    """

    agent = None
    corpus: Corpus | None = None
    session_id: str | None = None

    # --------------------------------------------------------------------- #
    #  WebSocket lifecycle                                                  #
    # --------------------------------------------------------------------- #
    async def connect(self) -> None:
        """
        Authenticate the user, load the target corpus, then accept the socket.
        """
        self.session_id = str(uuid.uuid4())
        logger.debug(
            "[Session %s] connect() called.  Scope: %s",
            self.session_id,
            self.scope,
        )

        # ------------------------------------------------------------------ #
        #  Authentication                                                    #
        # ------------------------------------------------------------------ #
        if await check_auth_and_close_if_failed(self, self.session_id):
            return

        try:
            graphql_corpus_id = extract_websocket_path_id(self.scope["path"], "corpus")
            self.corpus_id = int(from_global_id(graphql_corpus_id)[1])
            self.corpus = await Corpus.objects.aget(id=self.corpus_id)
        except (ValueError, Corpus.DoesNotExist) as err:
            logger.error("[Session %s] Invalid corpus: %s", self.session_id, err)
            await self.accept()
            await self.send_standard_message(
                msg_type="SYNC_CONTENT",
                data={"error": "Requested corpus not found."},
            )
            await self.close(code=WS_CLOSE_UNAUTHENTICATED)
            return

        await self.accept()
        logger.debug("[Session %s] WebSocket accepted.", self.session_id)

    async def disconnect(self, close_code: int) -> None:
        """Clean up on socket close."""
        logger.debug(
            "[Session %s] WebSocket disconnected.  Code=%s", self.session_id, close_code
        )
        self.agent = None  # allow GC

    # --------------------------------------------------------------------- #
    #  Rate limiting                                                        #
    # --------------------------------------------------------------------- #
    async def _check_message_rate_limit(self) -> bool:
        """
        Check if the current message is within rate limits.

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
            period_name = {1: "second", 60: "minute", 3600: "hour", 86400: "day"}.get(
                period, "period"
            )

            error_msg = (
                f"Rate limit exceeded: Max {count} AI queries per {period_name}. "
                "Please wait before sending another query."
            )

            logger.warning(
                "[Session %s] Message rate limited - Key: %s, Rate: %s",
                self.session_id,
                info.get("key", "unknown"),
                rate,
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

    # --------------------------------------------------------------------- #
    #  Public helpers                                                       #
    # --------------------------------------------------------------------- #
    async def send_standard_message(
        self,
        msg_type: MessageType,
        content: str = "",
        data: dict[str, Any] | None = None,
    ) -> None:
        """
        Send a JSON-encoded message with a fixed envelope understood by the UI.
        """
        await self.send(
            json.dumps(
                {
                    "type": msg_type,
                    "content": content,
                    "data": data or {},
                }
            )
        )

    # --------------------------------------------------------------------- #
    #  Main message handler                                                 #
    # --------------------------------------------------------------------- #
    async def receive(self, text_data: str) -> None:
        """
        Expected client payload::

            { "query": "some user question" }
        """
        logger.debug("[Session %s] <- %s", self.session_id, text_data)

        # Check message rate limit
        if not await self._check_message_rate_limit():
            return

        try:
            payload: dict[str, Any] = json.loads(text_data)
            user_query: str = payload.get("query", "").strip()
        except Exception:
            await self.send_standard_message(
                msg_type="SYNC_CONTENT",
                data={"error": "Malformed JSON payload."},
            )
            return

        if not user_query:
            await self.send_standard_message(
                msg_type="SYNC_CONTENT",
                data={"error": "No query provided."},
            )
            return

        # -------------------------------------------------------------- #
        #  Lazy agent creation                                           #
        # -------------------------------------------------------------- #
        if self.agent is None:
            logger.debug("[Session %s] Creating corpus agent…", self.session_id)

            # Optional conversation id passed via query-string
            conversation_id: int | None = None
            query_string = self.scope.get("query_string", b"").decode()
            qs_params = urllib.parse.parse_qs(query_string)
            convo_gid = qs_params.get("load_from_conversation_id", [None])[0]
            if convo_gid:
                try:
                    conversation_id = int(from_global_id(convo_gid)[1])
                    logger.debug(
                        "[Session %s] Resuming conversation %s",
                        self.session_id,
                        conversation_id,
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.error(
                        "[Session %s] Failed to parse conversation id: %s",
                        self.session_id,
                        exc,
                    )

            agent_kwargs: dict[str, Any] = {
                "corpus": self.corpus_id,
                "user_id": self.scope["user"].id,
            }
            if conversation_id:
                agent_kwargs["conversation_id"] = conversation_id

            if getattr(self.corpus, "preferred_embedder", None):
                agent_kwargs["embedder"] = self.corpus.preferred_embedder

            self.agent = await agents.for_corpus(
                **agent_kwargs, framework=settings.LLMS_DEFAULT_AGENT_FRAMEWORK
            )
            logger.debug("[Session %s] Agent ready.", self.session_id)

        # -------------------------------------------------------------- #
        #  Stream the LLM response                                       #
        # -------------------------------------------------------------- #
        try:
            # Import event classes locally to avoid heavy imports at top
            from opencontractserver.llms.agents.core_agents import (
                ApprovalNeededEvent,
                ContentEvent,
                ErrorEvent,
                FinalEvent,
                SourceEvent,
                ThoughtEvent,
            )

            async for event in self.agent.stream(user_query):
                # Ensure START message once we have IDs
                if getattr(event, "user_message_id", None) is not None and not hasattr(
                    self, "_sent_start"
                ):
                    await self.send_standard_message(
                        msg_type="ASYNC_START",
                        data={"message_id": event.llm_message_id},
                    )
                    self._sent_start = True

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
                        },
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
                    # Reset flag
                    if hasattr(self, "_sent_start"):
                        delattr(self, "_sent_start")

                elif isinstance(event, FinalEvent):
                    await self.send_standard_message(
                        msg_type="ASYNC_FINISH",
                        content=event.accumulated_content or event.content,
                        data={
                            "sources": [s.to_dict() for s in event.sources],
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
                    # ------------------------------------------------------------------
                    # Legacy path: some adapters still yield the
                    # unified *response objects* directly instead of the granular
                    # ThoughtEvent / ContentEvent / FinalEvent hierarchy.  To maintain
                    # backward-compatibility we treat those objects similarly to the
                    # document consumer: every delta with ``content`` becomes an
                    # ASYNC_CONTENT frame and when ``is_complete`` flips to ``True`` we
                    # dispatch the mandatory ASYNC_FINISH so the front-end can close
                    # the stream gracefully. NOTE - removed LlamaIndex adapters but leaving this.
                    # ------------------------------------------------------------------
                    if hasattr(event, "content") and event.content:
                        await self.send_standard_message(
                            msg_type="ASYNC_CONTENT",
                            content=str(event.content),
                            data={"message_id": event.llm_message_id},
                        )

                    if getattr(event, "is_complete", False):
                        sources_payload: list[dict[str, Any]] = []
                        if hasattr(event, "sources") and event.sources:
                            sources_payload = [s.to_dict() for s in event.sources]

                        await self.send_standard_message(
                            msg_type="ASYNC_FINISH",
                            content=getattr(event, "accumulated_content", ""),
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

            logger.debug("[Session %s] Streaming complete.", self.session_id)

        except Exception as llm_err:  # noqa: BLE001
            logger.error(
                "[Session %s] LLM error while streaming: %s",
                self.session_id,
                llm_err,
                exc_info=True,
            )
            await self.send_standard_message(
                msg_type="SYNC_CONTENT",
                data={"error": f"Error during processing: {llm_err}"},
            )
