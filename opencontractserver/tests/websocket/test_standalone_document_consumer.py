"""
Tests for StandaloneDocumentQueryConsumer using realistic data and fixtures.

We rely on BaseFixtureTestCase/WebsocketFixtureBaseTestCase to load realistic
documents and users.
"""

from __future__ import annotations

import json
import logging
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import quote

import pytest
import vcr
from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from django.conf import settings
from django.test.utils import override_settings
from graphql_relay import to_global_id

from config.websocket.consumers.standalone_document_conversation import (
    StandaloneDocumentQueryConsumer,
)
from opencontractserver.annotations.models import Annotation, Embedding
from opencontractserver.conversations.models import Conversation
from opencontractserver.llms.agents.core_agents import (
    ContentEvent,
    FinalEvent,
    SourceEvent,
    ThoughtEvent,
)
from opencontractserver.llms.types import AgentFramework
from opencontractserver.tests.base import WebsocketFixtureBaseTestCase

logger = logging.getLogger(__name__)


@override_settings(USE_AUTH0=False)
@pytest.mark.django_db(transaction=True)
class StandaloneDocumentConsumerTestCase(WebsocketFixtureBaseTestCase):
    """End-to-end tests for the stand-alone (corpus-less) document chat consumer."""

    class _StubAgent:
        def __init__(self, gen_factory):
            self._gen_factory = gen_factory
            self.get_conversation = MagicMock(return_value=None)

        def stream(self, user_query: str):
            return self._gen_factory()

        def resume_with_approval(
            self, llm_msg_id: int, approved: bool, stream: bool = True
        ):
            return self._gen_factory()

        def get_conversation_id(self):
            return None

    async def test_authenticated_user_with_permission(self) -> None:
        """Authenticated user with read permission can connect and chat."""
        # Ensure the document is readable (public) for the authenticated user
        self.doc.is_public = True
        await database_sync_to_async(self.doc.save)(update_fields=["is_public"])

        graphql_doc_id = to_global_id("DocumentType", self.doc.id)
        encoded_doc_id = quote(graphql_doc_id)
        ws_path = f"ws/standalone/document/{encoded_doc_id}/query/?token={self.token}"

        communicator = WebsocketCommunicator(self.application, ws_path)
        connected, _ = await communicator.connect()
        self.assertTrue(connected)

        # Patch agent to avoid external LLM calls
        with patch(
            "config.websocket.consumers.standalone_document_conversation.agents.for_document"
        ) as mock_agent:
            mock_agent.return_value = self._StubAgent(self._mock_stream_events)

            await communicator.send_to(json.dumps({"query": "Hello"}))

            # Receive START, CONTENT, FINISH at minimum
            msgs = []
            while True:
                payload = json.loads(await communicator.receive_from(timeout=10))
                msgs.append(payload)
                if payload.get("type") == "ASYNC_FINISH":
                    break

            self.assertTrue(any(m["type"] == "ASYNC_START" for m in msgs))
            self.assertTrue(any(m["type"] == "ASYNC_CONTENT" for m in msgs))
            self.assertEqual(msgs[-1]["type"], "ASYNC_FINISH")

            # Ensure corpus=None passed to agent factory
            mock_agent.assert_called_once()
            self.assertIsNone(mock_agent.call_args.kwargs.get("corpus"))

        await communicator.disconnect()

    async def test_authenticated_user_without_permission(self) -> None:
        """Authenticated user without read permission should be rejected (private doc not owned by user)."""
        from django.contrib.auth import get_user_model

        OtherUser = get_user_model()
        other_user = await database_sync_to_async(OtherUser.objects.create_user)(
            username="someoneelse", password="pw123456!", email="x@example.com"
        )
        # Create a private document owned by someone else
        from opencontractserver.documents.models import Document

        other_doc = await Document.objects.acreate(
            title="Private Other Doc", creator=other_user, is_public=False
        )

        graphql_doc_id = to_global_id("DocumentType", other_doc.id)
        encoded_doc_id = quote(graphql_doc_id)
        ws_path = f"ws/standalone/document/{encoded_doc_id}/query/?token={self.token}"

        communicator = WebsocketCommunicator(self.application, ws_path)
        connected, code = await communicator.connect()
        self.assertFalse(connected)
        self.assertEqual(code, 4000)

    async def test_anonymous_user_public_document(self) -> None:
        """Anonymous users can connect only if document is public."""
        # Ensure doc is public
        self.doc.is_public = True
        await database_sync_to_async(self.doc.save)(update_fields=["is_public"])

        graphql_doc_id = to_global_id("DocumentType", self.doc.id)
        encoded_doc_id = quote(graphql_doc_id)
        ws_path = f"ws/standalone/document/{encoded_doc_id}/query/"  # no token

        communicator = WebsocketCommunicator(self.application, ws_path)
        connected, _ = await communicator.connect()
        self.assertTrue(connected)
        await communicator.disconnect()

    async def test_anonymous_user_private_document(self) -> None:
        """Anonymous user should be denied for private documents."""
        self.doc.is_public = False
        await database_sync_to_async(self.doc.save)(update_fields=["is_public"])

        graphql_doc_id = to_global_id("DocumentType", self.doc.id)
        encoded_doc_id = quote(graphql_doc_id)
        ws_path = f"ws/standalone/document/{encoded_doc_id}/query/"  # no token

        communicator = WebsocketCommunicator(self.application, ws_path)
        connected, close_code = await communicator.connect()
        self.assertFalse(connected)
        self.assertEqual(close_code, 4000)

    async def test_pick_document_embedder_with_existing_embeddings(self) -> None:
        """Embedder picker should use existing structural annotation embedder."""
        # Delete any pre-existing structural embeddings for this document from fixtures
        await database_sync_to_async(
            lambda: Embedding.objects.filter(
                annotation__document=self.doc, annotation__structural=True
            ).delete()
        )()

        # Create a structural annotation for this document
        annotation = await Annotation.objects.acreate(
            document=self.doc,
            structural=True,
            json={},  # defaultable, but explicit for clarity
            creator=self.user,
        )
        # Link an embedding to that annotation
        chosen_path = "local/test-embedder"
        await Embedding.objects.acreate(
            annotation=annotation, embedder_path=chosen_path, creator=self.user
        )

        consumer = StandaloneDocumentQueryConsumer()
        consumer.document = self.doc
        consumer.session_id = "test-session"
        result = await consumer.pick_document_embedder()
        self.assertEqual(result, chosen_path)

    async def test_pick_document_embedder_fallback(self) -> None:
        """If no embeddings exist, fall back to settings.DEFAULT_EMBEDDER."""
        from django.conf import settings

        # Ensure no embeddings linked to this document
        await database_sync_to_async(
            lambda: Embedding.objects.filter(annotation__document=self.doc).delete()
        )()

        consumer = StandaloneDocumentQueryConsumer()
        consumer.document = self.doc
        consumer.session_id = "test-session"
        result = await consumer.pick_document_embedder()
        self.assertEqual(result, settings.DEFAULT_EMBEDDER)

    async def test_agent_called_with_embedder(self) -> None:
        """Ensure the consumer passes the chosen embedder to the agent factory."""
        # Ensure the document is readable for the authenticated user to allow connection
        self.doc.is_public = True
        await database_sync_to_async(self.doc.save)(update_fields=["is_public"])

        graphql_doc_id = to_global_id("DocumentType", self.doc.id)
        encoded_doc_id = quote(graphql_doc_id)
        ws_path = f"ws/standalone/document/{encoded_doc_id}/query/?token={self.token}"

        communicator = WebsocketCommunicator(self.application, ws_path)
        connected, _ = await communicator.connect()
        self.assertTrue(connected)

        # Patch agent factory and embedder picker after connection
        with patch(
            "config.websocket.consumers.standalone_document_conversation.agents.for_document"
        ) as mock_agent, patch(
            "config.websocket.consumers.standalone_document_conversation.StandaloneDocumentQueryConsumer.pick_document_embedder"  # noqa: E501
        ) as mock_picker:
            embedder_path = "test/embedder/path"
            mock_picker.return_value = embedder_path
            mock_agent.return_value = self._StubAgent(self._mock_stream_events)

            await communicator.send_to(json.dumps({"query": "Hi"}))

            # Drain messages
            while True:
                payload = json.loads(await communicator.receive_from(timeout=10))
                if payload.get("type") == "ASYNC_FINISH":
                    break

            mock_agent.assert_called_once()
            self.assertEqual(mock_agent.call_args.kwargs.get("embedder"), embedder_path)

        await communicator.disconnect()

    async def test_missing_document_id(self) -> None:
        """Missing document ID should reject connection with 4000."""
        # With Channels routing, an empty segment does not match any route at all,
        # so expect 'No route found' rather than a handled 4000 from the consumer.
        with self.assertRaises(ValueError):
            communicator = WebsocketCommunicator(
                self.application, "ws/standalone/document//query/"
            )
            await communicator.connect()

    @override_settings(
        LLM_CLIENT_PROVIDER="openai",
        LLM_CLIENT_MODEL="gpt-4o-mini",
        OPENAI_API_KEY="test-key",
    )
    async def test_conversation_title_generation(self) -> None:
        """Title generation should succeed; on failure returns a fallback title."""
        # Patch the client factory used by the consumer
        with patch(
            "opencontractserver.llms.client.create_client"
        ) as mock_create_client:
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.content = "Doc Chat"
            mock_client.chat.return_value = mock_response
            mock_create_client.return_value = mock_client

            consumer = StandaloneDocumentQueryConsumer()
            consumer.session_id = "test-session"
            title = await consumer.generate_conversation_title("What is this?")
            self.assertEqual(title, "Doc Chat")

            # Verify that create_client was called without arguments (uses settings)
            mock_create_client.assert_called_once_with()

        with patch(
            "opencontractserver.llms.client.create_client"
        ) as mock_create_client:
            mock_create_client.side_effect = Exception("boom")
            consumer = StandaloneDocumentQueryConsumer()
            consumer.session_id = "test-session"
            title = await consumer.generate_conversation_title("What is this?")
            self.assertTrue(title.startswith("Conversation "))

    # Helpers
    async def _mock_stream_events(self):
        yield ContentEvent(content="Hello ", llm_message_id=1, metadata={})
        yield ContentEvent(content="world", llm_message_id=1, metadata={})
        yield FinalEvent(
            content="",
            accumulated_content="Hello world",
            sources=[],
            llm_message_id=1,
            metadata={"timeline": []},
        )

    async def _mock_stream_events_with_thought_and_sources(self):
        yield ThoughtEvent(
            thought="Considering context", llm_message_id=42, metadata={}
        )
        yield ContentEvent(content="Answer part 1 ", llm_message_id=42, metadata={})
        yield SourceEvent(llm_message_id=42, sources=[], metadata={})
        yield ContentEvent(content="Answer part 2", llm_message_id=42, metadata={})
        yield FinalEvent(
            content="",
            accumulated_content="Answer part 1 Answer part 2",
            sources=[],
            llm_message_id=42,
            metadata={"timeline": ["t1", "t2"]},
        )

    async def _mock_resume_events(self):
        yield ThoughtEvent(
            thought="Resuming after approval", llm_message_id=7, metadata={}
        )
        yield ContentEvent(content="Approved content", llm_message_id=7, metadata={})
        yield FinalEvent(
            content="",
            accumulated_content="Approved content",
            sources=[],
            llm_message_id=7,
            metadata={"timeline": []},
        )

    async def test_loaded_conversation_flow_authenticated(self) -> None:
        """Authenticated user can load an existing conversation via query string."""
        self.doc.is_public = True
        await database_sync_to_async(self.doc.save)(update_fields=["is_public"])

        # Create a persistent conversation for this document/user
        conv = await Conversation.objects.acreate(
            title="Existing Conv",
            creator=self.user,
            chat_with_document=self.doc,
        )
        conv_gid = to_global_id("ConversationType", conv.id)
        doc_gid = to_global_id("DocumentType", self.doc.id)
        ws_path = f"ws/standalone/document/{quote(doc_gid)}/query/?token={self.token}&load_from_conversation_id={quote(conv_gid)}"  # noqa: E501

        with patch(
            "config.websocket.consumers.standalone_document_conversation.agents.for_document"
        ) as mock_agent:
            # Use stub agent and ensure conversation_id passed correctly
            mock_agent.return_value = self._StubAgent(self._mock_stream_events)

            communicator = WebsocketCommunicator(self.application, ws_path)
            connected, _ = await communicator.connect()
            self.assertTrue(connected)
            await communicator.send_to(json.dumps({"query": "Load test"}))

            msgs = []
            while True:
                payload = json.loads(await communicator.receive_from(timeout=10))
                msgs.append(payload)
                if payload.get("type") == "ASYNC_FINISH":
                    break

            # Assert message_id consistency
            msg_id = msgs[0]["data"]["message_id"]
            self.assertTrue(msg_id)
            for m in msgs:
                if "data" in m and "message_id" in m["data"]:
                    self.assertEqual(m["data"]["message_id"], msg_id)

            # Verify agent factory call captured conversation_id
            call_kwargs = mock_agent.call_args.kwargs
            self.assertEqual(call_kwargs.get("conversation_id"), conv.id)
            await communicator.disconnect()

    async def test_stream_includes_thought_sources_and_message_id_consistency(
        self,
    ) -> None:
        """Standalone stream should surface THOUGHT and SOURCES events with consistent message_id."""
        self.doc.is_public = True
        await database_sync_to_async(self.doc.save)(update_fields=["is_public"])

        doc_gid = to_global_id("DocumentType", self.doc.id)
        ws_path = f"ws/standalone/document/{quote(doc_gid)}/query/?token={self.token}"

        with patch(
            "config.websocket.consumers.standalone_document_conversation.agents.for_document"
        ) as mock_agent:
            mock_agent.return_value = self._StubAgent(
                self._mock_stream_events_with_thought_and_sources
            )

            communicator = WebsocketCommunicator(self.application, ws_path)
            connected, _ = await communicator.connect()
            self.assertTrue(connected)
            await communicator.send_to(
                json.dumps({"query": "Thought and sources please"})
            )

            msgs = []
            while True:
                payload = json.loads(await communicator.receive_from(timeout=10))
                msgs.append(payload)
                if payload.get("type") == "ASYNC_FINISH":
                    break

            self.assertTrue(any(m["type"] == "ASYNC_THOUGHT" for m in msgs))
            self.assertTrue(any(m["type"] == "ASYNC_SOURCES" for m in msgs))
            # Consistent message_id
            start_id = msgs[0]["data"]["message_id"]
            for m in msgs:
                if "data" in m and "message_id" in m["data"]:
                    self.assertEqual(m["data"]["message_id"], start_id)
            await communicator.disconnect()

    async def test_invalid_token_private_document_rejected(self) -> None:
        """Invalid token should be treated as anonymous; private doc must be rejected."""
        self.doc.is_public = False
        await database_sync_to_async(self.doc.save)(update_fields=["is_public"])
        doc_gid = to_global_id("DocumentType", self.doc.id)
        ws_path = (
            f"ws/standalone/document/{quote(doc_gid)}/query/?token=not_a_real_token"
        )
        communicator = WebsocketCommunicator(self.application, ws_path)
        connected, code = await communicator.connect()
        self.assertFalse(connected)
        self.assertEqual(code, 4000)

    async def test_invalid_token_public_document_connects_as_anonymous(self) -> None:
        """Invalid token is anonymous; public doc should connect and stream."""
        self.doc.is_public = True
        await database_sync_to_async(self.doc.save)(update_fields=["is_public"])
        doc_gid = to_global_id("DocumentType", self.doc.id)
        ws_path = (
            f"ws/standalone/document/{quote(doc_gid)}/query/?token=not_a_real_token"
        )

        with patch(
            "config.websocket.consumers.standalone_document_conversation.agents.for_document"
        ) as mock_agent:
            mock_agent.return_value = self._StubAgent(self._mock_stream_events)
            communicator = WebsocketCommunicator(self.application, ws_path)
            connected, _ = await communicator.connect()
            self.assertTrue(connected)
            await communicator.send_to(json.dumps({"query": "Hi"}))
            # Drain
            while True:
                payload = json.loads(await communicator.receive_from(timeout=10))
                if payload.get("type") == "ASYNC_FINISH":
                    break
            await communicator.disconnect()

    async def test_approval_resume_event_mapping(self) -> None:
        """Approval resume should map events to websocket types."""
        consumer = StandaloneDocumentQueryConsumer()
        consumer.session_id = "test-session"
        consumer.send = AsyncMock()

        # Attach stub agent that yields events for resume
        class _ResumeStub:
            def resume_with_approval(
                self, llm_message_id: int, approved: bool, stream: bool = True
            ):
                return self._gen()

            def __init__(self, gen):
                self._gen = gen

        consumer.agent = _ResumeStub(self._mock_resume_events)

        await consumer._handle_approval_decision(
            {"approval_decision": True, "llm_message_id": 7}
        )
        # Ensure messages sent include ASYNC_THOUGHT and ASYNC_FINISH
        sent_types = [
            json.loads(call.args[0]).get("type")
            for call in consumer.send.call_args_list
        ]
        self.assertIn("ASYNC_THOUGHT", sent_types)
        self.assertIn("ASYNC_FINISH", sent_types)

    async def test_anonymous_no_conversation_persistence(self) -> None:
        """Anonymous standalone chat should not try to persist conversations."""
        self.doc.is_public = True
        await database_sync_to_async(self.doc.save)(update_fields=["is_public"])
        doc_gid = to_global_id("DocumentType", self.doc.id)
        ws_path = f"ws/standalone/document/{quote(doc_gid)}/query/"

        with patch(
            "config.websocket.consumers.standalone_document_conversation.agents.for_document"
        ) as mock_agent:
            stub = self._StubAgent(self._mock_stream_events)
            # get_conversation is a MagicMock on stub
            mock_agent.return_value = stub
            communicator = WebsocketCommunicator(self.application, ws_path)
            connected, _ = await communicator.connect()
            self.assertTrue(connected)
            await communicator.send_to(json.dumps({"query": "Anon query"}))
            # Drain
            while True:
                payload = json.loads(await communicator.receive_from(timeout=10))
                if payload.get("type") == "ASYNC_FINISH":
                    break
            # Since anonymous, consumer should not have attempted to set title (which calls get_conversation)
            self.assertFalse(stub.get_conversation.called)
            await communicator.disconnect()

    async def test_agent_called_with_default_embedder_when_picker_not_mocked(
        self,
    ) -> None:
        """If picker isn't mocked, ensure embedder is still provided (DEFAULT or from embeddings)."""
        self.doc.is_public = True
        await database_sync_to_async(self.doc.save)(update_fields=["is_public"])
        doc_gid = to_global_id("DocumentType", self.doc.id)
        ws_path = f"ws/standalone/document/{quote(doc_gid)}/query/?token={self.token}"

        with patch(
            "config.websocket.consumers.standalone_document_conversation.agents.for_document"
        ) as mock_agent:
            mock_agent.return_value = self._StubAgent(self._mock_stream_events)
            communicator = WebsocketCommunicator(self.application, ws_path)
            connected, _ = await communicator.connect()
            self.assertTrue(connected)
            await communicator.send_to(json.dumps({"query": "Hi"}))
            while True:
                payload = json.loads(await communicator.receive_from(timeout=10))
                if payload.get("type") == "ASYNC_FINISH":
                    break
            # Embedder should be present (either DEFAULT or discovered)
            self.assertIn("embedder", mock_agent.call_args.kwargs)
            await communicator.disconnect()


@override_settings(USE_AUTH0=False)
@pytest.mark.django_db(transaction=True)
class StandaloneConversationVCRTestCase(WebsocketFixtureBaseTestCase):
    """VCR-backed integration tests for standalone document conversation."""

    async def _assert_stream_contract(
        self, communicator: WebsocketCommunicator, query_text: str
    ) -> list[dict]:
        await communicator.send_to(json.dumps({"query": query_text}))
        received: list[dict] = []
        while True:
            payload = json.loads(await communicator.receive_from(timeout=60))
            received.append(payload)
            if payload.get("type") == "ASYNC_FINISH":
                break
        # Basic contract
        assert any(m["type"] == "ASYNC_START" for m in received)
        assert any(m["type"] == "ASYNC_CONTENT" for m in received)
        assert received[-1]["type"] == "ASYNC_FINISH"
        # message_id consistency
        start_id = received[0]["data"]["message_id"]
        for m in received:
            if "data" in m and "message_id" in m["data"]:
                assert m["data"]["message_id"] == start_id
        return received

    async def _fetch_last_conversation(self) -> Conversation | None:
        return await (
            Conversation.objects.filter(creator=self.user, chat_with_document=self.doc)
            .order_by("-created_at")
            .afirst()
        )

    async def _assert_sources_and_timeline_persisted(
        self, conversation: Conversation
    ) -> None:
        from opencontractserver.conversations.models import ChatMessage

        llm_messages = await database_sync_to_async(
            lambda: list(
                ChatMessage.objects.filter(conversation=conversation, msg_type="LLM")
            )
        )()
        assert llm_messages, "No LLM messages persisted"
        saw_timeline = False
        for msg in llm_messages:
            data = msg.data or {}
            tl = data.get("timeline")
            if isinstance(tl, list):
                saw_timeline = True
        assert saw_timeline, "Expected 'timeline' list on at least one LLM message"

    @vcr.use_cassette(
        "fixtures/vcr_cassettes/test_standalone_document_conversation_ws.yaml",
        filter_headers=["authorization"],
        record_mode="once",
    )
    @override_settings(
        LLMS_DEFAULT_AGENT_FRAMEWORK="pydantic_ai",
        LLMS_DOCUMENT_AGENT_FRAMEWORK="pydantic_ai",
        LLMS_CORPUS_AGENT_FRAMEWORK="pydantic_ai",
    )
    async def test_multiturn_streaming_flow_new_vcr(self) -> None:
        """Two-turn streaming flow for standalone route with VCR."""
        # Ensure readability and persistence
        self.doc.is_public = True
        await database_sync_to_async(self.doc.save)(update_fields=["is_public"])

        doc_gid = to_global_id("DocumentType", self.doc.id)
        ws_path = f"ws/standalone/document/{quote(doc_gid)}/query/?token={self.token}"
        communicator = WebsocketCommunicator(self.application, ws_path)
        connected, _ = await communicator.connect()
        self.assertTrue(connected)

        await self._assert_stream_contract(communicator, "Please stream something")
        await self._assert_stream_contract(
            communicator, "Ok, please summarize the document."
        )
        await communicator.disconnect()

        # Verify persistence and timeline
        if (
            getattr(settings, "LLMS_DOCUMENT_AGENT_FRAMEWORK", "pydantic_ai")
            == AgentFramework.PYDANTIC_AI.value
        ):
            conv = await self._fetch_last_conversation()
            self.assertIsNotNone(conv)
            if conv:
                await self._assert_sources_and_timeline_persisted(conv)

    @vcr.use_cassette(
        "fixtures/vcr_cassettes/test_standalone_document_conversation_ws_loaded.yaml",
        filter_headers=["authorization"],
        record_mode="once",
    )
    @override_settings(
        LLMS_DEFAULT_AGENT_FRAMEWORK="pydantic_ai",
        LLMS_DOCUMENT_AGENT_FRAMEWORK="pydantic_ai",
        LLMS_CORPUS_AGENT_FRAMEWORK="pydantic_ai",
    )
    async def test_multiturn_streaming_flow_loaded_vcr(self) -> None:
        """Two-turn streaming flow for standalone route when loading existing conversation (VCR)."""
        # Ensure readability and persistence
        self.doc.is_public = True
        await database_sync_to_async(self.doc.save)(update_fields=["is_public"])

        # Create an existing conversation
        conv = await Conversation.objects.acreate(
            title="Pre-existing Standalone Conversation",
            creator=self.user,
            chat_with_document=self.doc,
        )
        conv_gid = to_global_id("ConversationType", conv.id)

        doc_gid = to_global_id("DocumentType", self.doc.id)
        ws_path = f"ws/standalone/document/{quote(doc_gid)}/query/?token={self.token}&load_from_conversation_id={quote(conv_gid)}"  # noqa: E501
        communicator = WebsocketCommunicator(self.application, ws_path)
        connected, _ = await communicator.connect()
        self.assertTrue(connected)

        await self._assert_stream_contract(communicator, "Please stream something")
        await self._assert_stream_contract(
            communicator, "Ok, please summarize the document."
        )
        await communicator.disconnect()

        # Verify persistence and timeline
        if (
            getattr(settings, "LLMS_DOCUMENT_AGENT_FRAMEWORK", "pydantic_ai")
            == AgentFramework.PYDANTIC_AI.value
        ):
            conv_reloaded = await self._fetch_last_conversation()
            self.assertIsNotNone(conv_reloaded)
            if conv_reloaded:
                await self._assert_sources_and_timeline_persisted(conv_reloaded)
