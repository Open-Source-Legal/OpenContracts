"""
Tests for UnifiedAgentConsumer - the unified WebSocket consumer for all agent contexts.

This consumer replaces the legacy DocumentQueryConsumer, CorpusQueryConsumer, and
StandaloneDocumentQueryConsumer with a single, secure endpoint that properly
validates user permissions.

Test categories:
1. Permission Tests - validate access control for authenticated and anonymous users
2. Context Tests - validate agent selection based on corpus/document/agent IDs
3. Auth Tests - validate token handling
4. Streaming Tests - validate message streaming contract
"""

from __future__ import annotations

import json
import logging
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from urllib.parse import quote

import pytest
from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from django.test.utils import override_settings
from graphql_relay import to_global_id

from config.websocket.consumers.unified_agent_conversation import (
    UnifiedAgentConsumer,
)
from config.websocket.middleware import (
    WS_AUTH_SUBPROTOCOL,
    WS_CLOSE_TOKEN_INVALID,
    WS_CLOSE_UNAUTHENTICATED,
)
from opencontractserver.agents.models import AgentConfiguration
from opencontractserver.conversations.models import Conversation
from opencontractserver.llms.agents.core_agents import (
    ContentEvent,
    FinalEvent,
    SourceEvent,
    SourceNode,
    ThoughtEvent,
)
from opencontractserver.tests.base import WebsocketFixtureBaseTestCase

logger = logging.getLogger(__name__)


class _StubAgent:
    """Stub agent for testing WebSocket message flow without actual LLM calls."""

    def __init__(self, gen_factory, conversation_id=None):
        self._gen_factory = gen_factory
        self._conversation_id = conversation_id
        self.conversation_manager = SimpleNamespace(context_exhausted=False)

    def stream(self, user_query: str):
        return self._gen_factory()

    def resume_with_approval(
        self, llm_msg_id: int, approved: bool, stream: bool = True
    ):
        return self._gen_factory()

    def get_conversation_id(self):
        return self._conversation_id


@override_settings(USE_AUTH0=False)
@pytest.mark.django_db(transaction=True)
class UnifiedAgentConsumerPermissionTestCase(WebsocketFixtureBaseTestCase):
    """Test permission enforcement for the unified agent consumer."""

    # -------------------------------------------------------------------------
    # Corpus Permission Tests
    # -------------------------------------------------------------------------

    async def test_authenticated_user_with_corpus_permission(self) -> None:
        """Authenticated user with corpus read permission can connect."""
        # User owns the corpus (from fixture setup), so has permission
        corpus_gid = to_global_id("CorpusType", self.corpus.id)
        ws_path = f"ws/agent-chat/?corpus_id={quote(corpus_gid)}"

        communicator = WebsocketCommunicator(
            self.application,
            ws_path,
            subprotocols=[WS_AUTH_SUBPROTOCOL, self.token],
        )
        connected, _ = await communicator.connect()
        self.assertTrue(connected)
        await communicator.disconnect()

    async def test_authenticated_user_without_corpus_permission(self) -> None:
        """Authenticated user without corpus read permission should be rejected."""
        from django.contrib.auth import get_user_model

        # Create another user who doesn't own the corpus
        OtherUser = get_user_model()
        other_user = await database_sync_to_async(OtherUser.objects.create_user)(
            username="otheruser_corpus",
            password="pw123456!",
            email="other_corpus@example.com",
        )
        from graphql_jwt.shortcuts import get_token

        other_token = await database_sync_to_async(get_token)(user=other_user)

        # Make corpus private
        self.corpus.is_public = False
        await database_sync_to_async(self.corpus.save)(update_fields=["is_public"])

        corpus_gid = to_global_id("CorpusType", self.corpus.id)
        ws_path = f"ws/agent-chat/?corpus_id={quote(corpus_gid)}"

        communicator = WebsocketCommunicator(
            self.application,
            ws_path,
            subprotocols=[WS_AUTH_SUBPROTOCOL, other_token],
        )
        connected, code = await communicator.connect()
        self.assertFalse(connected)
        self.assertEqual(code, 4003)  # Permission denied code

    async def test_anonymous_user_public_corpus(self) -> None:
        """Anonymous user can access public corpus."""
        self.corpus.is_public = True
        await database_sync_to_async(self.corpus.save)(update_fields=["is_public"])

        corpus_gid = to_global_id("CorpusType", self.corpus.id)
        ws_path = f"ws/agent-chat/?corpus_id={quote(corpus_gid)}"  # No token

        communicator = WebsocketCommunicator(self.application, ws_path)
        connected, _ = await communicator.connect()
        self.assertTrue(connected)
        await communicator.disconnect()

    async def test_anonymous_user_private_corpus(self) -> None:
        """Anonymous user should be denied for private corpus."""
        self.corpus.is_public = False
        await database_sync_to_async(self.corpus.save)(update_fields=["is_public"])

        corpus_gid = to_global_id("CorpusType", self.corpus.id)
        ws_path = f"ws/agent-chat/?corpus_id={quote(corpus_gid)}"  # No token

        communicator = WebsocketCommunicator(self.application, ws_path)
        connected, code = await communicator.connect()
        self.assertFalse(connected)
        self.assertEqual(code, 4003)

    # -------------------------------------------------------------------------
    # Document Permission Tests
    # -------------------------------------------------------------------------

    async def test_authenticated_user_with_document_permission(self) -> None:
        """Authenticated user with document read permission can connect."""
        # Make doc public to ensure permission
        self.doc.is_public = True
        await database_sync_to_async(self.doc.save)(update_fields=["is_public"])

        doc_gid = to_global_id("DocumentType", self.doc.id)
        ws_path = f"ws/agent-chat/?document_id={quote(doc_gid)}"

        communicator = WebsocketCommunicator(
            self.application,
            ws_path,
            subprotocols=[WS_AUTH_SUBPROTOCOL, self.token],
        )
        connected, _ = await communicator.connect()
        self.assertTrue(connected)
        await communicator.disconnect()

    async def test_authenticated_user_without_document_permission(self) -> None:
        """Authenticated user without document read permission should be rejected."""
        from django.contrib.auth import get_user_model

        # Create another user and a private document they don't own
        OtherUser = get_user_model()
        other_user = await database_sync_to_async(OtherUser.objects.create_user)(
            username="otheruser_doc",
            password="pw123456!",
            email="other_doc@example.com",
        )
        from graphql_jwt.shortcuts import get_token

        other_token = await database_sync_to_async(get_token)(user=other_user)

        # Make doc private (owned by self.user, not other_user)
        self.doc.is_public = False
        await database_sync_to_async(self.doc.save)(update_fields=["is_public"])

        doc_gid = to_global_id("DocumentType", self.doc.id)
        ws_path = f"ws/agent-chat/?document_id={quote(doc_gid)}"

        communicator = WebsocketCommunicator(
            self.application,
            ws_path,
            subprotocols=[WS_AUTH_SUBPROTOCOL, other_token],
        )
        connected, code = await communicator.connect()
        self.assertFalse(connected)
        self.assertEqual(code, 4003)

    async def test_anonymous_user_public_document(self) -> None:
        """Anonymous user can access public document."""
        self.doc.is_public = True
        await database_sync_to_async(self.doc.save)(update_fields=["is_public"])

        doc_gid = to_global_id("DocumentType", self.doc.id)
        ws_path = f"ws/agent-chat/?document_id={quote(doc_gid)}"  # No token

        communicator = WebsocketCommunicator(self.application, ws_path)
        connected, _ = await communicator.connect()
        self.assertTrue(connected)
        await communicator.disconnect()

    async def test_anonymous_user_private_document(self) -> None:
        """Anonymous user should be denied for private document."""
        self.doc.is_public = False
        await database_sync_to_async(self.doc.save)(update_fields=["is_public"])

        doc_gid = to_global_id("DocumentType", self.doc.id)
        ws_path = f"ws/agent-chat/?document_id={quote(doc_gid)}"  # No token

        communicator = WebsocketCommunicator(self.application, ws_path)
        connected, code = await communicator.connect()
        self.assertFalse(connected)
        self.assertEqual(code, 4003)


@override_settings(USE_AUTH0=False)
@pytest.mark.django_db(transaction=True)
class UnifiedAgentConsumerContextTestCase(WebsocketFixtureBaseTestCase):
    """Test context resolution for the unified agent consumer."""

    async def test_no_context_rejected(self) -> None:
        """Connection without corpus_id or document_id should be rejected."""
        ws_path = "ws/agent-chat/"  # No context params

        communicator = WebsocketCommunicator(
            self.application,
            ws_path,
            subprotocols=[WS_AUTH_SUBPROTOCOL, self.token],
        )
        connected, code = await communicator.connect()
        self.assertFalse(connected)
        self.assertEqual(code, WS_CLOSE_UNAUTHENTICATED)

    async def test_corpus_only_context_uses_corpus_agent(self) -> None:
        """Corpus-only context should use default-corpus-agent."""
        # Ensure agent config exists
        await database_sync_to_async(AgentConfiguration.objects.get_or_create)(
            slug="default-corpus-agent",
            defaults={
                "name": "Default Corpus Agent",
                "is_active": True,
                "creator": self.user,
            },
        )

        corpus_gid = to_global_id("CorpusType", self.corpus.id)
        ws_path = f"ws/agent-chat/?corpus_id={quote(corpus_gid)}"

        communicator = WebsocketCommunicator(
            self.application,
            ws_path,
            subprotocols=[WS_AUTH_SUBPROTOCOL, self.token],
        )
        connected, _ = await communicator.connect()
        self.assertTrue(connected)
        await communicator.disconnect()

    async def test_document_only_context_uses_document_agent(self) -> None:
        """Document-only context should use default-document-agent."""
        # Ensure agent config exists
        await database_sync_to_async(AgentConfiguration.objects.get_or_create)(
            slug="default-document-agent",
            defaults={
                "name": "Default Document Agent",
                "is_active": True,
                "creator": self.user,
            },
        )

        self.doc.is_public = True
        await database_sync_to_async(self.doc.save)(update_fields=["is_public"])

        doc_gid = to_global_id("DocumentType", self.doc.id)
        ws_path = f"ws/agent-chat/?document_id={quote(doc_gid)}"

        communicator = WebsocketCommunicator(
            self.application,
            ws_path,
            subprotocols=[WS_AUTH_SUBPROTOCOL, self.token],
        )
        connected, _ = await communicator.connect()
        self.assertTrue(connected)
        await communicator.disconnect()

    async def test_document_with_corpus_context(self) -> None:
        """Document with corpus context should connect and use document agent."""
        # Ensure agent config exists
        await database_sync_to_async(AgentConfiguration.objects.get_or_create)(
            slug="default-document-agent",
            defaults={
                "name": "Default Document Agent",
                "is_active": True,
                "creator": self.user,
            },
        )

        self.doc.is_public = True
        await database_sync_to_async(self.doc.save)(update_fields=["is_public"])

        doc_gid = to_global_id("DocumentType", self.doc.id)
        corpus_gid = to_global_id("CorpusType", self.corpus.id)
        ws_path = (
            f"ws/agent-chat/?document_id={quote(doc_gid)}"
            f"&corpus_id={quote(corpus_gid)}"
        )

        communicator = WebsocketCommunicator(
            self.application,
            ws_path,
            subprotocols=[WS_AUTH_SUBPROTOCOL, self.token],
        )
        connected, _ = await communicator.connect()
        self.assertTrue(connected)
        await communicator.disconnect()

    async def test_explicit_agent_id_overrides_default(self) -> None:
        """Explicit agent_id should use that specific agent."""
        # Create a custom agent
        custom_agent = await database_sync_to_async(AgentConfiguration.objects.create)(
            slug="custom-test-agent",
            name="Custom Test Agent",
            is_active=True,
            creator=self.user,
        )

        corpus_gid = to_global_id("CorpusType", self.corpus.id)
        agent_gid = to_global_id("AgentConfigurationType", custom_agent.id)
        ws_path = (
            f"ws/agent-chat/?corpus_id={quote(corpus_gid)}"
            f"&agent_id={quote(agent_gid)}"
        )

        communicator = WebsocketCommunicator(
            self.application,
            ws_path,
            subprotocols=[WS_AUTH_SUBPROTOCOL, self.token],
        )
        connected, _ = await communicator.connect()
        self.assertTrue(connected)
        await communicator.disconnect()


@override_settings(USE_AUTH0=False)
@pytest.mark.django_db(transaction=True)
class UnifiedAgentConsumerAuthTestCase(WebsocketFixtureBaseTestCase):
    """Test authentication handling for the unified agent consumer."""

    async def test_valid_token_authenticates(self) -> None:
        """Valid token should authenticate the user."""
        corpus_gid = to_global_id("CorpusType", self.corpus.id)
        ws_path = f"ws/agent-chat/?corpus_id={quote(corpus_gid)}"

        communicator = WebsocketCommunicator(
            self.application,
            ws_path,
            subprotocols=[WS_AUTH_SUBPROTOCOL, self.token],
        )
        connected, _ = await communicator.connect()
        self.assertTrue(connected)
        await communicator.disconnect()

    async def test_invalid_token_rejected(self) -> None:
        """Invalid token should be rejected with WS_CLOSE_TOKEN_INVALID."""
        self.corpus.is_public = False
        await database_sync_to_async(self.corpus.save)(update_fields=["is_public"])

        corpus_gid = to_global_id("CorpusType", self.corpus.id)
        ws_path = f"ws/agent-chat/?corpus_id={quote(corpus_gid)}"

        communicator = WebsocketCommunicator(
            self.application,
            ws_path,
            subprotocols=[WS_AUTH_SUBPROTOCOL, "invalid_token"],
        )
        connected, code = await communicator.connect()
        self.assertFalse(connected)
        self.assertEqual(code, WS_CLOSE_TOKEN_INVALID)

    async def test_invalid_token_public_resource_rejected(self) -> None:
        """Invalid token should be rejected even for public resources."""
        self.corpus.is_public = True
        await database_sync_to_async(self.corpus.save)(update_fields=["is_public"])

        corpus_gid = to_global_id("CorpusType", self.corpus.id)
        ws_path = f"ws/agent-chat/?corpus_id={quote(corpus_gid)}"

        communicator = WebsocketCommunicator(
            self.application,
            ws_path,
            subprotocols=[WS_AUTH_SUBPROTOCOL, "invalid_token"],
        )
        connected, code = await communicator.connect()
        self.assertFalse(connected)
        self.assertEqual(code, WS_CLOSE_TOKEN_INVALID)

    async def test_no_token_public_resource_connects_anonymous(self) -> None:
        """No token with public resource should connect as anonymous."""
        self.corpus.is_public = True
        await database_sync_to_async(self.corpus.save)(update_fields=["is_public"])

        corpus_gid = to_global_id("CorpusType", self.corpus.id)
        ws_path = f"ws/agent-chat/?corpus_id={quote(corpus_gid)}"  # No token

        communicator = WebsocketCommunicator(self.application, ws_path)
        connected, _ = await communicator.connect()
        self.assertTrue(connected)
        await communicator.disconnect()


@override_settings(USE_AUTH0=False)
@pytest.mark.django_db(transaction=True)
class UnifiedAgentConsumerStreamingTestCase(WebsocketFixtureBaseTestCase):
    """Test streaming behavior for the unified agent consumer."""

    async def _mock_stream_events(self):
        """Mock event generator for testing."""
        yield ContentEvent(
            content="Hello ",
            llm_message_id=1,
            user_message_id=1,
            metadata={},
        )
        yield ContentEvent(
            content="world",
            llm_message_id=1,
            user_message_id=1,
            metadata={},
        )
        yield FinalEvent(
            content="",
            accumulated_content="Hello world",
            sources=[],
            llm_message_id=1,
            user_message_id=1,
            metadata={"timeline": []},
        )

    async def _mock_stream_events_with_thought_and_sources(self):
        """Mock event generator with thought and source events."""
        yield ThoughtEvent(
            thought="Considering context",
            llm_message_id=42,
            user_message_id=1,
            metadata={},
        )
        yield ContentEvent(
            content="Answer part 1 ",
            llm_message_id=42,
            user_message_id=1,
            metadata={},
        )
        yield SourceEvent(
            llm_message_id=42,
            user_message_id=1,
            sources=[
                SourceNode(
                    annotation_id=1,
                    content="Test source content",
                    metadata={},
                    similarity_score=0.95,
                )
            ],
            metadata={},
        )
        yield ContentEvent(
            content="Answer part 2",
            llm_message_id=42,
            user_message_id=1,
            metadata={},
        )
        yield FinalEvent(
            content="",
            accumulated_content="Answer part 1 Answer part 2",
            sources=[],
            llm_message_id=42,
            user_message_id=1,
            metadata={"timeline": ["t1", "t2"]},
        )

    async def test_streaming_contract(self) -> None:
        """Streaming should follow the expected message contract."""
        # Ensure agent config exists
        await database_sync_to_async(AgentConfiguration.objects.get_or_create)(
            slug="default-corpus-agent",
            defaults={
                "name": "Default Corpus Agent",
                "is_active": True,
                "creator": self.user,
            },
        )

        corpus_gid = to_global_id("CorpusType", self.corpus.id)
        ws_path = f"ws/agent-chat/?corpus_id={quote(corpus_gid)}"

        communicator = WebsocketCommunicator(
            self.application,
            ws_path,
            subprotocols=[WS_AUTH_SUBPROTOCOL, self.token],
        )
        connected, _ = await communicator.connect()
        self.assertTrue(connected)

        # Drain initial AUTH_OK frame from auth handshake mixin
        raw = await communicator.receive_from(timeout=5)
        self.assertEqual(json.loads(raw)["type"], "AUTH_OK")

        with patch(
            "config.websocket.consumers.unified_agent_conversation.agents.for_corpus"
        ) as mock_agent:
            mock_agent.return_value = _StubAgent(self._mock_stream_events)

            await communicator.send_to(json.dumps({"query": "Hello"}))

            msgs = []
            while True:
                payload = json.loads(await communicator.receive_from(timeout=10))
                msgs.append(payload)
                if payload.get("type") == "ASYNC_FINISH":
                    break

            # Verify expected message types
            self.assertTrue(any(m["type"] == "ASYNC_START" for m in msgs))
            self.assertTrue(any(m["type"] == "ASYNC_CONTENT" for m in msgs))
            self.assertEqual(msgs[-1]["type"], "ASYNC_FINISH")

        await communicator.disconnect()

    async def test_stream_includes_thought_and_sources(self) -> None:
        """Stream should surface THOUGHT and SOURCES events."""
        # Ensure agent config exists
        await database_sync_to_async(AgentConfiguration.objects.get_or_create)(
            slug="default-corpus-agent",
            defaults={
                "name": "Default Corpus Agent",
                "is_active": True,
                "creator": self.user,
            },
        )

        corpus_gid = to_global_id("CorpusType", self.corpus.id)
        ws_path = f"ws/agent-chat/?corpus_id={quote(corpus_gid)}"

        communicator = WebsocketCommunicator(
            self.application,
            ws_path,
            subprotocols=[WS_AUTH_SUBPROTOCOL, self.token],
        )
        connected, _ = await communicator.connect()
        self.assertTrue(connected)

        # Drain initial AUTH_OK frame from auth handshake mixin
        raw = await communicator.receive_from(timeout=5)
        self.assertEqual(json.loads(raw)["type"], "AUTH_OK")

        with patch(
            "config.websocket.consumers.unified_agent_conversation.agents.for_corpus"
        ) as mock_agent:
            mock_agent.return_value = _StubAgent(
                self._mock_stream_events_with_thought_and_sources
            )

            await communicator.send_to(json.dumps({"query": "Analyze this"}))

            msgs = []
            while True:
                payload = json.loads(await communicator.receive_from(timeout=10))
                msgs.append(payload)
                if payload.get("type") == "ASYNC_FINISH":
                    break

            # Verify THOUGHT and SOURCES are present
            self.assertTrue(any(m["type"] == "ASYNC_THOUGHT" for m in msgs))
            self.assertTrue(any(m["type"] == "ASYNC_SOURCES" for m in msgs))

            # Verify message_id consistency
            start_msg = next(m for m in msgs if m["type"] == "ASYNC_START")
            msg_id = start_msg["data"]["message_id"]
            for m in msgs:
                if "data" in m and "message_id" in m["data"]:
                    self.assertEqual(m["data"]["message_id"], msg_id)

        await communicator.disconnect()

    async def test_load_existing_conversation(self) -> None:
        """Loading an existing conversation should pass conversation_id to agent."""
        # Ensure agent config exists
        await database_sync_to_async(AgentConfiguration.objects.get_or_create)(
            slug="default-corpus-agent",
            defaults={
                "name": "Default Corpus Agent",
                "is_active": True,
                "creator": self.user,
            },
        )

        # Create an existing conversation
        conv = await Conversation.objects.acreate(
            title="Existing Conversation",
            creator=self.user,
            chat_with_corpus=self.corpus,
        )

        corpus_gid = to_global_id("CorpusType", self.corpus.id)
        conv_gid = to_global_id("ConversationType", conv.id)
        ws_path = (
            f"ws/agent-chat/?corpus_id={quote(corpus_gid)}"
            f"&conversation_id={quote(conv_gid)}"
        )

        communicator = WebsocketCommunicator(
            self.application,
            ws_path,
            subprotocols=[WS_AUTH_SUBPROTOCOL, self.token],
        )
        connected, _ = await communicator.connect()
        self.assertTrue(connected)

        # Drain initial AUTH_OK frame from auth handshake mixin
        raw = await communicator.receive_from(timeout=5)
        self.assertEqual(json.loads(raw)["type"], "AUTH_OK")

        with patch(
            "config.websocket.consumers.unified_agent_conversation.agents.for_corpus"
        ) as mock_agent:
            mock_agent.return_value = _StubAgent(
                self._mock_stream_events,
                conversation_id=conv.id,
            )

            await communicator.send_to(json.dumps({"query": "Continue"}))

            # Drain messages
            while True:
                payload = json.loads(await communicator.receive_from(timeout=10))
                if payload.get("type") == "ASYNC_FINISH":
                    break

            # Verify conversation_id was passed
            mock_agent.assert_called_once()
            call_kwargs = mock_agent.call_args.kwargs
            self.assertEqual(call_kwargs.get("conversation_id"), conv.id)

        await communicator.disconnect()


@override_settings(USE_AUTH0=False)
@pytest.mark.django_db(transaction=True)
class UnifiedAgentConsumerTitleGenerationTestCase(WebsocketFixtureBaseTestCase):
    """Test conversation title generation for the unified agent consumer."""

    @override_settings(
        LLM_CLIENT_PROVIDER="openai",
        LLM_CLIENT_MODEL="gpt-4o-mini",
        OPENAI_API_KEY="test-key",
    )
    async def test_title_generation_success(self) -> None:
        """Title generation should produce a title from the initial query."""
        with patch(
            "opencontractserver.llms.client.create_client"
        ) as mock_create_client:
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.content = "Corpus Analysis"
            mock_client.chat.return_value = mock_response
            mock_create_client.return_value = mock_client

            consumer = UnifiedAgentConsumer()
            consumer.session_id = "test-session"
            title = await consumer._generate_conversation_title(
                "What is this corpus about?"
            )
            self.assertEqual(title, "Corpus Analysis")

    @override_settings(
        LLM_CLIENT_PROVIDER="openai",
        LLM_CLIENT_MODEL="gpt-4o-mini",
        OPENAI_API_KEY="test-key",
    )
    async def test_title_generation_fallback_on_error(self) -> None:
        """Title generation should return fallback on error."""
        with patch(
            "opencontractserver.llms.client.create_client"
        ) as mock_create_client:
            mock_create_client.side_effect = Exception("API error")

            consumer = UnifiedAgentConsumer()
            consumer.session_id = "test-session"
            title = await consumer._generate_conversation_title("Test query")
            self.assertTrue(title.startswith("Conversation "))


@override_settings(USE_AUTH0=False)
@pytest.mark.django_db(transaction=True)
class UnifiedAgentConsumerDisconnectTestCase(WebsocketFixtureBaseTestCase):
    """Tests for graceful disconnect handling."""

    async def test_disconnect_sets_connected_flag(self):
        """After disconnect(), _is_connected should be False."""
        consumer = UnifiedAgentConsumer()
        consumer.session_id = "test-session"
        consumer._is_connected = True

        await consumer.disconnect(close_code=1000)

        self.assertFalse(consumer._is_connected)
        self.assertIsNone(consumer.agent)

    async def test_send_safe_returns_false_when_disconnected(self):
        """_send_safe should return False when _is_connected is False."""
        consumer = UnifiedAgentConsumer()
        consumer.session_id = "test-session"
        consumer._is_connected = False

        result = await consumer._send_safe(
            msg_type="ASYNC_CONTENT",
            content="test",
        )
        self.assertFalse(result)


@override_settings(USE_AUTH0=False)
@pytest.mark.django_db(transaction=True)
class UnifiedAgentConsumerContextExhaustionTestCase(WebsocketFixtureBaseTestCase):
    """Tests for context exhaustion guard in the receive() message handler."""

    async def test_context_exhausted_sends_error_and_skips_stream(self) -> None:
        """When context_exhausted is True, ASYNC_ERROR is sent and streaming is skipped."""
        consumer = UnifiedAgentConsumer()
        consumer.session_id = "test-session"
        consumer._is_connected = True
        consumer.user_id = None  # anonymous session

        # Build a minimal stub agent whose conversation_manager reports exhaustion.
        mock_conversation_manager = MagicMock()
        mock_conversation_manager.context_exhausted = True

        stub_agent = MagicMock()
        stub_agent.conversation_manager = mock_conversation_manager

        # Pre-assign the agent so _initialize_agent is not called.
        consumer.agent = stub_agent
        consumer.conversation_id = 1  # non-None prevents is_new_conversation flag

        sent_messages = []

        async def fake_send_safe(msg_type, content="", data=None):
            sent_messages.append(
                {"msg_type": msg_type, "content": content, "data": data or {}}
            )
            return True

        stream_called = False

        async def fake_stream_agent_response(user_query):
            nonlocal stream_called
            stream_called = True

        consumer._send_safe = fake_send_safe
        consumer._stream_agent_response = fake_stream_agent_response

        # Simulate receiving a normal query message.
        with patch(
            "config.websocket.consumers.unified_agent_conversation.check_ws_rate_limit",
            return_value=False,
        ):
            await consumer.receive(json.dumps({"query": "Hello, are you still there?"}))

        # Exactly one message must have been sent.
        self.assertEqual(len(sent_messages), 1)
        msg = sent_messages[0]
        self.assertEqual(msg["msg_type"], "ASYNC_ERROR")
        from opencontractserver.constants.context_guardrails import (
            WS_ERROR_CONTEXT_EXHAUSTED,
        )

        self.assertEqual(msg["data"].get("error_type"), WS_ERROR_CONTEXT_EXHAUSTED)

        # Streaming must NOT have been attempted.
        self.assertFalse(stream_called)

    async def test_context_not_exhausted_proceeds_to_stream(self) -> None:
        """When context_exhausted is False, _stream_agent_response is called normally."""
        consumer = UnifiedAgentConsumer()
        consumer.session_id = "test-session"
        consumer._is_connected = True
        consumer.user_id = None

        mock_conversation_manager = MagicMock()
        mock_conversation_manager.context_exhausted = False

        stub_agent = MagicMock()
        stub_agent.conversation_manager = mock_conversation_manager

        consumer.agent = stub_agent
        consumer.conversation_id = 1

        sent_messages = []

        async def fake_send_safe(msg_type, content="", data=None):
            sent_messages.append(
                {"msg_type": msg_type, "content": content, "data": data or {}}
            )
            return True

        stream_called = False

        async def fake_stream_agent_response(user_query):
            nonlocal stream_called
            stream_called = True

        consumer._send_safe = fake_send_safe
        consumer._stream_agent_response = fake_stream_agent_response

        with patch(
            "config.websocket.consumers.unified_agent_conversation.check_ws_rate_limit",
            return_value=False,
        ):
            await consumer.receive(json.dumps({"query": "Still within limits"}))

        # No ASYNC_ERROR should be present.
        error_msgs = [m for m in sent_messages if m["msg_type"] == "ASYNC_ERROR"]
        self.assertEqual(error_msgs, [])

        # Streaming must have been called.
        self.assertTrue(stream_called)

    async def test_agent_without_conversation_manager_proceeds_to_stream(self) -> None:
        """When agent has no conversation_manager attribute, the check is skipped."""
        consumer = UnifiedAgentConsumer()
        consumer.session_id = "test-session"
        consumer._is_connected = True
        consumer.user_id = None

        # Agent without conversation_manager (e.g. legacy stub).
        stub_agent = MagicMock(spec=[])  # empty spec — no attributes
        consumer.agent = stub_agent
        consumer.conversation_id = 1

        stream_called = False

        async def fake_stream_agent_response(user_query):
            nonlocal stream_called
            stream_called = True

        consumer._stream_agent_response = fake_stream_agent_response

        async def fake_send_safe(msg_type, content="", data=None):
            return True

        consumer._send_safe = fake_send_safe

        with patch(
            "config.websocket.consumers.unified_agent_conversation.check_ws_rate_limit",
            return_value=False,
        ):
            await consumer.receive(json.dumps({"query": "Legacy agent query"}))

        self.assertTrue(stream_called)
