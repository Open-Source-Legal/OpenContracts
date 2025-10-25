"""
StandaloneDocumentQueryConsumer

Provides a Channels WebSocket consumer for querying documents WITHOUT a corpus.
This consumer allows users to chat with documents directly, without requiring
them to be part of a corpus.

Key differences from DocumentQueryConsumer:
- No corpus_id in the WebSocket path
- Supports both authenticated and anonymous users (if document is public)
- Automatically filters out corpus-dependent tools
- Uses embedder fallback strategy for vector search
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

from config.websocket.utils.extract_ids import extract_websocket_path_id
from opencontractserver.conversations.models import MessageType
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


class StandaloneDocumentQueryConsumer(AsyncWebsocketConsumer):
    """
    A Channels WebSocket consumer for querying documents without a corpus.
    Supports both authenticated and anonymous users (for public documents).
    """

    agent = None
    document: Document | None = None
    session_id: str | None = None
    user_id: int | None = None  # Will be None for anonymous users

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.consumer_id = uuid.uuid4()
        logger.debug(f"[StandaloneConsumer {self.consumer_id}] __init__ called.")

    async def connect(self) -> None:
        """
        Handles the WebSocket connection event.
        Allows both authenticated and anonymous users (for public documents).
        """
        self.session_id = str(uuid.uuid4())
        logger.debug(
            f"[StandaloneConsumer {self.consumer_id} | Session {self.session_id}] connect() called. "
            f"Scope: {self.scope}"
        )

        try:
            # 1. Extract document_id from path
            graphql_doc_id = extract_websocket_path_id(self.scope["path"], "document")
            if not graphql_doc_id:
                err_msg = "Missing document_id in WebSocket path."
                logger.error(f"[Session {self.session_id}] {err_msg}")
                await self.close(code=4000)
                return

            self.document_id = int(from_global_id(graphql_doc_id)[1])

            # 2. Fetch the document
            self.document = await Document.objects.aget(id=self.document_id)
            logger.debug(
                f"[Session {self.session_id}] Loaded Document {self.document_id}"
            )

            # 3. Check permissions
            user = self.scope.get("user")
            is_authenticated = user and user.is_authenticated

            if is_authenticated:
                # Authenticated user - check read permission
                has_permission = await database_sync_to_async(
                    user_has_permission_for_obj
                )(user, self.document, PermissionTypes.READ)
                if not has_permission:
                    logger.warning(
                        f"[Session {self.session_id}] User {user.id} lacks read permission on Document {self.document_id}"  # noqa: E501
                    )
                    await self.close(code=4000)
                    return
                self.user_id = user.id
                logger.debug(
                    f"[Session {self.session_id}] Authenticated user {user.id} has permission"
                )
            else:
                # Anonymous user - only allow if document is public
                if not self.document.is_public:
                    logger.warning(
                        f"[Session {self.session_id}] Anonymous user trying to access non-public Document {self.document_id}"  # noqa: E501
                    )
                    await self.close(code=4000)
                    return
                logger.debug(
                    f"[Session {self.session_id}] Anonymous user accessing public document"
                )

            # 4. Accept the connection
            await self.accept()
            logger.debug(f"[Session {self.session_id}] Connection accepted.")

        except Document.DoesNotExist:
            err_msg = f"Document not found: {self.document_id}"
            logger.error(f"[Session {self.session_id}] {err_msg}")
            await self.close(code=4000)

        except Exception as e:
            logger.error(
                f"[Session {self.session_id}] Error during connection: {str(e)}",
                exc_info=True,
            )
            await self.close(code=4000)

    async def disconnect(self, close_code: int) -> None:
        """
        Handles the WebSocket disconnection event.
        """
        logger.debug(
            f"[StandaloneConsumer {self.consumer_id} | Session {self.session_id}] disconnect() called with code {close_code}."  # noqa: E501
        )
        self.agent = None

    async def send_standard_message(
        self,
        msg_type: MessageType,
        content: str = "",
        data: dict[str, Any] | None = None,
    ) -> None:
        """
        Sends a standardized message over the WebSocket in JSON format.
        """
        if data is None:
            data = {}

        await self.send(
            json.dumps({"type": msg_type, "content": content, "data": data})
        )

    async def pick_document_embedder(self) -> str:
        """
        Choose an embedder_path that already exists on the document's structural
        annotations; fall back to settings.DEFAULT_EMBEDDER if none.
        """
        from opencontractserver.annotations.models import Embedding

        document_id = self.document.id

        # Use async iteration to query in the same transaction context
        # This avoids transaction isolation issues with database_sync_to_async
        embeddings = [
            e
            async for e in Embedding.objects.filter(
                annotation__document_id=document_id,
                annotation__structural=True,
            ).only("embedder_path")
        ]

        # Get unique embedder paths
        paths = list({e.embedder_path for e in embeddings})

        if paths:
            logger.info(
                f"[Session {self.session_id}] Using existing embedder: {paths[0]} for Document {document_id}"
            )
            return paths[0]
        else:
            logger.warning(
                f"[Session {self.session_id}] No existing embedder found for Document {document_id}, "
                f"falling back to DEFAULT_EMBEDDER: {settings.DEFAULT_EMBEDDER}"
            )
            return settings.DEFAULT_EMBEDDER

    async def generate_conversation_title(self, user_query: str) -> str:
        """
        Generates a concise conversation title based on the initial user query.
        """
        try:
            from opencontractserver.llms.client import ChatMessage, create_client

            system_prompt = (
                "You are a helpful assistant that creates very concise chat titles. "
                "Create a brief (maximum 5 words) title that captures the essence "
                "of what the user is asking about."
            )

            user_prompt = f"Create a brief title for a conversation starting with this query: {user_query}"

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
        """Generate and persist a title for the current conversation without blocking the stream."""
        try:
            if self.agent is None:
                return
            convo_id = self.agent.get_conversation_id()
            if convo_id:
                from opencontractserver.conversations.models import Conversation

                conversation = await Conversation.objects.aget(id=convo_id)
                if conversation and not getattr(conversation, "title", None):
                    title = await self.generate_conversation_title(user_query)
                    conversation.title = title
                    await conversation.asave(update_fields=["title"])
        except Exception as e:
            logger.error(
                f"[Session {self.session_id}] Async title generation failed: {e}",
                exc_info=True,
            )

    async def receive(self, text_data: str) -> None:
        """
        Receives a message from the WebSocket and processes a user query.
        """
        logger.debug(
            f"[Session {self.session_id}] receive() called with text_data: {text_data}"
        )

        try:
            text_data_json: dict[str, Any] = json.loads(text_data)

            # Handle approval workflow messages
            if "approval_decision" in text_data_json:
                await self._handle_approval_decision(text_data_json)
                return

            user_query: str = text_data_json.get("query", "").strip()

            if not user_query:
                logger.warning(f"[Session {self.session_id}] Empty query received.")
                await self.send_standard_message(
                    msg_type="SYNC_CONTENT",
                    content="No query provided.",
                )
                return

            logger.debug(
                f"[Session {self.session_id}] Received user query: '{user_query}'"
            )

            # Initialize agent if not already created
            if self.agent is None:
                logger.debug(
                    f"[Session {self.session_id}] No agent loaded yet, initializing..."
                )

                # Parse conversation ID from query string if provided
                query_string = self.scope.get("query_string", b"").decode("utf-8")
                query_params = urllib.parse.parse_qs(query_string)
                load_convo_id_str = query_params.get(
                    "load_from_conversation_id", [None]
                )[0]

                conversation_id_from_query = None
                if load_convo_id_str:
                    try:
                        conversation_id_from_query = int(
                            from_global_id(load_convo_id_str)[1]
                        )
                        logger.debug(
                            f"[Session {self.session_id}] Loading conversation ID {conversation_id_from_query}"
                        )
                    except Exception as e:
                        logger.warning(
                            f"[Session {self.session_id}] Failed to parse conversation ID: {e}"
                        )

                # Choose an embedder path (from document embeddings if available; else default)
                embedder_path = await self.pick_document_embedder()

                # Create the agent - pass corpus=None; tool filtering occurs inside factory
                self.agent = await agents.for_document(
                    document=self.document,
                    corpus=None,
                    user_id=self.user_id,
                    conversation_id=conversation_id_from_query,
                    embedder=embedder_path,
                )

                # Generate title for new conversations (authenticated users only) in background
                if self.user_id and not conversation_id_from_query:
                    asyncio.create_task(self._async_set_conversation_title(user_query))

            # Stream the response
            logger.debug(f"[Session {self.session_id}] Starting streaming response...")

            try:
                async for event in self.agent.stream(user_query):
                    # Handle different event types
                    if isinstance(event, ApprovalNeededEvent):
                        await self.send_standard_message(
                            msg_type="ASYNC_APPROVAL_NEEDED",
                            content="",
                            data={
                                "tool_name": event.tool_name,
                                "tool_description": event.tool_description,
                                "tool_arguments": event.tool_arguments,
                                "message_id": event.llm_message_id,
                            },
                        )

                    elif isinstance(event, ApprovalResultEvent):
                        pass  # No need to send anything for this event

                    elif isinstance(event, ResumeEvent):
                        pass  # No need to send anything for this event

                    elif isinstance(event, ThoughtEvent):
                        if not hasattr(self, "_sent_start"):
                            await self.send_standard_message(
                                msg_type="ASYNC_START",
                                content="",
                                data={"message_id": event.llm_message_id},
                            )
                            self._sent_start = True

                        await self.send_standard_message(
                            msg_type="ASYNC_THOUGHT",
                            content=event.thought,
                            data={"message_id": event.llm_message_id, **event.metadata},
                        )

                    elif isinstance(event, ContentEvent):
                        if not hasattr(self, "_sent_start"):
                            await self.send_standard_message(
                                msg_type="ASYNC_START",
                                content="",
                                data={"message_id": event.llm_message_id},
                            )
                            self._sent_start = True

                        if event.content:
                            await self.send_standard_message(
                                msg_type="ASYNC_CONTENT",
                                content=event.content,
                                data={"message_id": event.llm_message_id},
                            )

                    elif isinstance(event, SourceEvent):
                        await self.send_standard_message(
                            msg_type="ASYNC_SOURCES",
                            content="",
                            data={
                                "message_id": event.llm_message_id,
                                "sources": [s.to_dict() for s in event.sources],
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

                logger.debug(
                    f"[Session {self.session_id}] Completed streaming response"
                )

            except Exception as api_error:
                logger.error(
                    f"[Session {self.session_id}] Error during API call: {str(api_error)}",
                    exc_info=True,
                )

        except Exception as e:
            logger.error(
                f"[Session {self.session_id}] Error during message processing: {e}",
                exc_info=True,
            )
            await self.send_standard_message(
                msg_type="SYNC_CONTENT",
                content="",
                data={"error": f"Error during message processing: {e}"},
            )

    async def _handle_approval_decision(self, payload: dict[str, Any]) -> None:
        """Process an approval/rejection coming from the front-end.

        Expected JSON payload:
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
                content="",
                data={"error": "llm_message_id missing in approval payload"},
            )
            return

        if self.agent is None:
            await self.send_standard_message(
                msg_type="SYNC_CONTENT",
                content="",
                data={"error": "Agent not initialised for approval"},
            )
            return

        try:
            # Stream the resumed answer
            async for event in self.agent.resume_with_approval(
                llm_msg_id, approved, stream=True
            ):
                # Re-use the same event -> websocket mapping logic
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
                    await self.send_standard_message(
                        msg_type="ASYNC_SOURCES",
                        content="",
                        data={
                            "message_id": event.llm_message_id,
                            "sources": [s.to_dict() for s in event.sources],
                        },
                    )
                elif isinstance(event, FinalEvent):
                    await self.send_standard_message(
                        msg_type="ASYNC_FINISH",
                        content=event.accumulated_content or event.content,
                        data={
                            "sources": [s.to_dict() for s in event.sources],
                            "message_id": event.llm_message_id,
                            "timeline": event.metadata.get("timeline", []),
                        },
                    )

        except Exception as e:
            logger.error("Approval resume error: %s", e, exc_info=True)
            await self.send_standard_message(
                msg_type="SYNC_CONTENT",
                content="",
                data={"error": f"Failed to resume after approval: {e}"},
            )
