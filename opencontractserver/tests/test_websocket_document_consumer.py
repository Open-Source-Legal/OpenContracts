from __future__ import annotations

import json
import logging
from typing import Any
from unittest.mock import patch
from urllib.parse import quote

import vcr
from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from django.conf import settings
from django.db.models import Q
from django.test.utils import override_settings
from graphql_relay import to_global_id

from opencontractserver.conversations.models import ChatMessage, Conversation  # noqa
from opencontractserver.llms.agents import for_document
from opencontractserver.llms.agents.timeline_schema import TIMELINE_ENTRY_SCHEMA
from opencontractserver.llms.types import AgentFramework
from opencontractserver.tests.base import WebsocketFixtureBaseTestCase

logging.basicConfig()
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
vcr_log = logging.getLogger("vcr")
vcr_log.setLevel(logging.WARNING)


@override_settings(USE_AUTH0=False)
class DocumentConversationWebsocketTestCase(WebsocketFixtureBaseTestCase):
    """
    End-to-end websocket test for the refactored DocumentQueryConsumer.
    Tests both new and loaded conversations, and a two-turn interaction.
    """

    maxDiff = None

    # Expected responses for new (not loaded from history) conversations
    expected_responses_new = {
        AgentFramework.PYDANTIC_AI.value: [
            'According to **U.S. Code Title 1**, the rule of construction for "words importing the masculine gender" is as follows:\n\n- "Words importing the masculine gender include the feminine as well."\n\nThis means that any references made using masculine terms are intended to be inclusive of feminine references unless the context specifies otherwise. This is part of a broader set of rules concerning the interpretation of legislation, emphasizing inclusivity in legal language.\n\n**Citation:** U.S. Code Title 1, Chapter 1, Section 1 (page 2).',  # noqa: E501
            'According to **U.S. Code Title 1, Section 3**, the term "vessel" is defined as follows:\n\n- The term "vessel" includes all means of water transportation.\n\nThis broad definition ensures that various types of watercraft, such as boats, ships, and other floating structures, are encompassed under the term "vessel" for legal and regulatory purposes.\n\n**Citation:** U.S. Code Title 1, Section 3.',  # noqa: E501
        ],
    }

    # Expected responses for conversations loaded from history
    expected_responses_loaded = {
        AgentFramework.PYDANTIC_AI.value: [
            'According to U.S. Code Title 1, the rule of construction states that "words importing the masculine gender include the feminine as well." This means that any references made using masculine terms are intended to be inclusive of feminine references unless the context indicates otherwise.',  # noqa: E501
            'U.S. Code Title 1, Section 3 defines the term "vessel" as follows: \n\nThe term "vessel" includes every description of watercraft or other artificial contrivance used, or capable of being used, as a means of transportation on water.\n\nThis definition is broad and encompasses various types of watercraft, highlighting their function as vehicles for transportation over water.',  # noqa: E501
        ],
    }

    async def _assert_streaming_flow(
        self,
        communicator: WebsocketCommunicator,
        query_text: str,
        expected_response_key: str,
        is_loaded_conversation: bool = False,  # For logging purposes
    ) -> str:
        """
        Sends a query on an existing communicator and verifies the streaming response flow.
        """
        if is_loaded_conversation:
            logger.info(
                f"[_assert_streaming_flow] Testing with LOADED conversation. Query: '{query_text}'"
            )
        else:
            logger.info(
                f"[_assert_streaming_flow] Testing with NEW/ANONYMOUS conversation. Query: '{query_text}'"
            )

        # ------------------------------------------------------------------
        # Log outgoing user message (for clarity in CI logs)
        # ------------------------------------------------------------------
        current_framework_setting = str(
            getattr(settings, "LLMS_DOCUMENT_AGENT_FRAMEWORK", "pydantic_ai")
        )
        logger.info(
            f"[TEST][framework={current_framework_setting}][loaded={is_loaded_conversation}] USER → '{query_text}'"
        )

        await communicator.send_to(json.dumps({"query": query_text}))

        received: list[dict[str, Any]] = []
        while True:
            try:
                msg = await communicator.receive_from(
                    timeout=60
                )  # Increased timeout for agentic workflows with multiple tool calls
            except Exception as e:
                self.fail(
                    f"Timed-out waiting for websocket messages for query '{query_text}': {e}"
                )

            payload = json.loads(msg)
            logger.debug(f"Payload for query '{query_text}': {payload}")
            received.append(payload)

            if payload.get("type") == "ASYNC_FINISH":
                break

        self.assertGreaterEqual(
            len(received),
            3,
            f"For query '{query_text}', consumer should emit at least START, one CONTENT, FINISH.",
        )
        self.assertEqual(
            received[0]["type"],
            "ASYNC_START",
            f"First message for '{query_text}' should be ASYNC_START",
        )
        self.assertEqual(
            received[-1]["type"],
            "ASYNC_FINISH",
            f"Last message for '{query_text}' should be ASYNC_FINISH",
        )

        content_msgs = [m for m in received if m["type"] == "ASYNC_CONTENT"]

        # Enhanced diagnostics for troubleshooting
        if not content_msgs:
            all_message_types = [m.get("type") for m in received]
            logger.error(
                f"[DIAGNOSTIC] No ASYNC_CONTENT messages found for query '{query_text}'"
            )
            logger.error(f"[DIAGNOSTIC] Total messages received: {len(received)}")
            logger.error(f"[DIAGNOSTIC] All message types: {all_message_types}")
            logger.error(f"[DIAGNOSTIC] First 3 messages (full): {received[:3]}")

        self.assertTrue(
            content_msgs,
            f"At least one ASYNC_CONTENT expected for query '{query_text}'. "
            f"Received {len(received)} messages with types: {[m.get('type') for m in received]}",
        )

        full_text = "".join(msg["content"] for msg in content_msgs).strip()
        logger.info(
            f"[_assert_streaming_flow] Full LLM response text for query '{query_text}': {full_text}"
        )

        # Log assistant response for easier debugging in CI logs
        logger.info(
            f"[TEST][framework={current_framework_setting}][loaded={is_loaded_conversation}] ASSISTANT ← '{full_text}'"
        )

        # ------------------------------------------------------------------
        # Enhanced validation: Check for granular event types in pydantic-ai
        # ------------------------------------------------------------------
        expected_canonical_msg_types = {"ASYNC_START", "ASYNC_CONTENT", "ASYNC_FINISH"}
        all_message_types = {m["type"] for m in received}

        if current_framework_setting == AgentFramework.PYDANTIC_AI.value:
            # For pydantic-ai we expect **at least one** non-canonical type –
            # e.g. ASYNC_THOUGHT, ASYNC_TOOL, ASYNC_SOURCES …
            other_types = all_message_types - expected_canonical_msg_types
            self.assertTrue(
                other_types,
                "Expected at least one granular event type (e.g. ASYNC_THOUGHT) "
                "in the websocket stream for pydantic-ai but found only the "
                "canonical message types.",
            )
            logger.info(
                f"[_assert_streaming_flow] Detected new event types for pydantic-ai: {sorted(other_types)}"
            )
        else:
            # For legacy frameworks we assert the legacy contract remains unchanged
            self.assertTrue(
                all_message_types.issubset(expected_canonical_msg_types),
                "Legacy frameworks should *not* emit the new granular event types.",
            )

        # The expected_response_key ("query1_response" or "query2_response") is used directly
        # with the selected dictionary.

        start_msg_id = received[0]["data"]["message_id"]
        self.assertTrue(
            start_msg_id, f"START message for '{query_text}' must contain a message_id."
        )

        for msg in received[1:]:
            if "data" in msg and "message_id" in msg["data"]:
                self.assertEqual(
                    msg["data"]["message_id"],
                    start_msg_id,
                    f"message_id for '{query_text}' must remain constant.",
                )

        return full_text

    async def _create_and_populate_conversation(self) -> Conversation:
        """Helper to create a conversation with a couple of messages."""
        conversation = await Conversation.objects.acreate(
            title="Pre-existing Test Conversation",
            creator=self.user,
            chat_with_document=self.doc,
        )
        await ChatMessage.objects.acreate(
            conversation=conversation,
            msg_type="HUMAN",
            content="This is a previous user message about general topics.",
            creator=self.user,
        )
        await ChatMessage.objects.acreate(
            conversation=conversation,
            msg_type="LLM",
            content="Acknowledged. I am a helpful assistant.",
            creator=self.user,  # LLM messages are also created by the user in current model
        )
        logger.info(
            f"[_create_and_populate_conversation] Created "
            f"Conversation ID: {conversation.id} with 2 messages "
            f"for Document ID: {self.doc.id}"
        )
        return conversation

    @vcr.use_cassette(
        "fixtures/vcr_cassettes/test_document_conversation_ws.yaml",
        filter_headers=["authorization"],
        record_mode="none",
    )
    async def test_multiturn_streaming_flow__all_default_frameworks(self) -> None:
        """
        Tests a two-turn streaming flow for new conversations.
        """
        print("--------------------------------")
        print(
            "\n\nXOXO - [_test_multiturn_streaming_flow__all_default_frameworks] "
            "Tests a two-turn streaming flow for new conversations."
        )
        print("--------------------------------")

        for framework in ("pydantic_ai",):
            print(f"XOXO: {framework}")
            with self.subTest(default_framework=framework):
                with override_settings(
                    LLMS_DEFAULT_AGENT_FRAMEWORK=framework,
                    LLMS_DOCUMENT_AGENT_FRAMEWORK=framework,
                    LLMS_CORPUS_AGENT_FRAMEWORK=framework,
                ):
                    await self._run_full_conversation_flow(framework)

    @vcr.use_cassette(
        "fixtures/vcr_cassettes/test_document_conversation_ws_loaded.yaml",
        filter_headers=["authorization"],
        record_mode="once",
    )
    async def test_multiturn_streaming_flow_with_loaded_conversation__all_default_frameworks(
        self,
    ) -> None:
        """
        Tests a two-turn streaming flow when loading an existing conversation.
        """
        print("--------------------------------")
        print(
            "\n\nXOXO - [_test_multiturn_streaming_flow_with_loaded_conversation] "
            "Tests a two-turn streaming flow when loading an existing conversation."
        )
        print("--------------------------------")

        for framework in ("pydantic_ai",):
            print(f"XOXO: {framework}")
            with self.subTest(default_framework=framework):
                with override_settings(
                    LLMS_DEFAULT_AGENT_FRAMEWORK=framework,
                    LLMS_DOCUMENT_AGENT_FRAMEWORK=framework,
                    LLMS_CORPUS_AGENT_FRAMEWORK=framework,
                ):
                    await self._run_loaded_conversation_flow(framework)

    # --- Negative-path helpers and tests remain unchanged from your previous version ---
    async def _assert_invalid_token(self) -> None:
        """Connection should be rejected (code 4000) when the JWT is invalid."""
        graphql_id = to_global_id("DocumentType", self.doc.id)
        encoded_graphql_id = quote(graphql_id)
        encoded_corpus_id = quote(to_global_id("CorpusType", self.corpus.id))

        communicator = WebsocketCommunicator(
            self.application,
            f"ws/document/{encoded_graphql_id}/query/"
            f"corpus/{encoded_corpus_id}/?token=not_a_real_token",
        )
        connected, close_code = await communicator.connect()
        self.assertFalse(connected)
        self.assertEqual(close_code, 4000)

    async def _assert_missing_token(self) -> None:
        """Omitting the token entirely must also yield close 4000."""
        graphql_id = to_global_id("DocumentType", self.doc.id)
        encoded_graphql_id = quote(graphql_id)
        encoded_corpus_id = quote(to_global_id("CorpusType", self.corpus.id))

        communicator = WebsocketCommunicator(
            self.application,
            f"ws/document/{encoded_graphql_id}/query/" f"corpus/{encoded_corpus_id}/",
        )
        connected, close_code = await communicator.connect()
        self.assertFalse(connected)
        self.assertEqual(close_code, 4000)

    async def _assert_invalid_document(self) -> None:
        """
        A non-existent document ID should result in:
        • WebSocket *accepted*
        • Immediate `SYNC_CONTENT` error payload
        • Close code 4000
        """
        bad_doc_gid = to_global_id("DocumentType", 999_999)
        encoded_bad_doc = quote(bad_doc_gid)
        encoded_corpus_id = quote(to_global_id("CorpusType", self.corpus.id))

        communicator = WebsocketCommunicator(
            self.application,
            f"ws/document/{encoded_bad_doc}/query/"
            f"corpus/{encoded_corpus_id}/?token={self.token}",
        )
        connected, _ = await communicator.connect()
        self.assertTrue(connected)

        raw = await communicator.receive_from(timeout=30)
        payload = json.loads(raw)
        self.assertEqual(payload["type"], "SYNC_CONTENT")
        self.assertIn("error", payload["data"])
        self.assertEqual(payload["data"]["error"], "Requested Document not found.")

        # The consumer should now close the websocket with code 4000.
        close_event = await communicator.receive_output(timeout=30)
        self.assertEqual(close_event["type"], "websocket.close")
        self.assertEqual(close_event["code"], 4000)

        # Ensure the communicator is fully shut down
        await communicator.wait()

    async def test_invalid_token(self) -> None:  # noqa: D401
        """Connection rejected with an **invalid** JWT token."""
        await self._assert_invalid_token()

    async def test_missing_token(self) -> None:  # noqa: D401
        """Connection rejected when **no** JWT token is supplied."""
        await self._assert_missing_token()

    async def test_invalid_document_id(self) -> None:  # noqa: D401
        """Proper SYNC_CONTENT error for a non-existent document ID."""
        await self._assert_invalid_document()

    # ------------------------------------------------------------------ #
    # Utility helpers for conversation-history inspection / assertions   #
    # ------------------------------------------------------------------ #

    async def _fetch_last_conversation(self) -> Conversation:
        """
        Returns the most-recent conversation started by *this* test user
        for the current document.
        """
        return await (
            Conversation.objects.filter(creator=self.user, chat_with_document=self.doc)
            .order_by("-created_at")
            .afirst()
        )

    async def _log_and_assert_history(
        self,
        conversation: Conversation,
        expected_queries: list[str],
        expected_llm_replies: list[str],
        expect_prepopulated_messages: bool = False,
    ) -> None:
        """
        1. Dumps the complete message history to the test log.
        2. Performs a few high-level assertions to guarantee that the agent
           actually *stored* what was exchanged over the websocket.

        Args:
            conversation:   The Conversation instance to inspect.
            expected_queries:  The HUMAN contents we sent in the test.
            expected_llm_replies:  The LLM responses we asserted on.
        """
        # Pull messages – oldest first
        messages = await database_sync_to_async(list)(
            ChatMessage.objects.filter(conversation=conversation)
            .order_by("created_at")
            .all()
        )

        # --- Pretty print to console / CI logs -------------------------
        logger.info("\n====== Conversation %s – full history ======", conversation.pk)
        logger.info(f"expected_queries {len(expected_queries)}: {expected_queries}")
        logger.info(
            f"expected_llm_replies {len(expected_llm_replies)}: {expected_llm_replies}"
        )
        logger.info(f"expect_prepopulated_messages: {expect_prepopulated_messages}")
        for msg in messages:
            logger.info(
                "[%s] %s: %s",
                msg.created_at.isoformat(timespec="seconds"),
                msg.msg_type,
                msg.content.replace("\n", " ")[:200]
                + ("…" if len(msg.content) > 200 else ""),
            )
        logger.info("============================================================\n")

        # --- Basic structural checks -----------------------------------
        # For a *new* conversation we expect 2 HUMAN + 2 LLM messages
        # For a *loaded* conversation we already pre-populated 2 messages.
        expected_msg_count = len(expected_queries) + len(expected_llm_replies)
        self.assertEqual(
            len(messages),
            expected_msg_count + (2 if expect_prepopulated_messages else 0),
            "Unexpected number of messages stored for conversation %s"
            % conversation.pk,
        )

        # # Assert the queries were stored exactly as HUMAN messages
        # human_contents = [m.content.strip() for m in messages if m.msg_type == "HUMAN"]
        # self.assertEqual(human_contents, expected_queries)

        # # Assert LLM replies were stored exactly
        # llm_contents = [m.content.strip() for m in messages if m.msg_type == "LLM"]
        # self.assertEqual(llm_contents, expected_llm_replies)

    # --- Start of new helper method ---
    async def _run_full_conversation_flow(self, framework: str) -> Conversation:
        """Runs the full new conversation flow and returns the conversation."""
        graphql_doc_id = to_global_id("DocumentType", self.doc.id)
        encoded_graphql_doc_id = quote(graphql_doc_id)
        encoded_corpus_id = quote(to_global_id("CorpusType", self.corpus.id))
        ws_path = f"ws/document/{encoded_graphql_doc_id}/query/corpus/{encoded_corpus_id}/?token={self.token}"

        communicator = WebsocketCommunicator(self.application, ws_path)
        connected, _ = await communicator.connect()
        self.assertTrue(connected, "WebSocket for new conversation should connect.")

        response_1 = await self._assert_streaming_flow(
            communicator=communicator,
            query_text="Please stream something",
            expected_response_key="query1_response",
            is_loaded_conversation=False,
        )
        response_2 = await self._assert_streaming_flow(
            communicator=communicator,
            query_text="Ok, please summarize the document.",
            expected_response_key="query2_response",
            is_loaded_conversation=False,
        )

        self.assertEqual(
            [response_1, response_2], self.expected_responses_new[framework]
        )

        await communicator.disconnect()

        conversation = await self._fetch_last_conversation()
        await self._log_and_assert_history(
            conversation,
            expected_queries=[
                "Please stream something",
                "Ok, please summarize the document.",
            ],
            expected_llm_replies=[response_1, response_2],
        )
        return conversation

    # --- End of new helper method ---

    # --- Start of new helper method for loaded conversation ---
    async def _run_loaded_conversation_flow(self, framework: str) -> Conversation:
        """Runs the full loaded conversation flow and returns the conversation."""
        conversation = await self._create_and_populate_conversation()

        history_check_agent = await for_document(
            document=self.doc,
            corpus=self.corpus,
            user_id=self.user.id,
            conversation_id=conversation.id,
        )
        actual_history_for_log = await history_check_agent.get_conversation_messages()
        print(
            f"Fetched {len(actual_history_for_log)} messages via agent API for "
            f"conversation {conversation.id} for logging."
        )

        graphql_doc_id = to_global_id("DocumentType", self.doc.id)
        encoded_graphql_doc_id = quote(graphql_doc_id)
        encoded_corpus_id = quote(to_global_id("CorpusType", self.corpus.id))
        graphql_convo_id = to_global_id("ConversationType", conversation.id)
        encoded_graphql_convo_id = quote(graphql_convo_id)
        ws_path = f"ws/document/{encoded_graphql_doc_id}/query/corpus/{encoded_corpus_id}/?token={self.token}&load_from_conversation_id={encoded_graphql_convo_id}"  # noqa: E501

        communicator = WebsocketCommunicator(self.application, ws_path)
        connected, _ = await communicator.connect()
        self.assertTrue(connected, "WebSocket for loaded conversation should connect.")

        response_1 = await self._assert_streaming_flow(
            communicator=communicator,
            query_text="Please stream something",
            expected_response_key="query1_response",
            is_loaded_conversation=True,
        )
        response_2 = await self._assert_streaming_flow(
            communicator=communicator,
            query_text="Ok, please summarize the document.",
            expected_response_key="query2_response",
            is_loaded_conversation=True,
        )
        self.assertEqual(
            [response_1, response_2],
            self.expected_responses_loaded[framework],
        )

        await communicator.disconnect()

        # The conversation object 'conversation' here refers to the one created by _create_and_populate_conversation.
        # Messages are added to this existing conversation.
        await self._log_and_assert_history(
            conversation,  # Use the existing conversation object
            expected_queries=[
                "Please stream something",
                "Ok, please summarize the document.",
            ],
            expected_llm_replies=[response_1, response_2],
            expect_prepopulated_messages=True,
        )
        return conversation

    # --- End of new helper method for loaded conversation ---


class ConversationSourceLoggingTestCase(DocumentConversationWebsocketTestCase):
    """
    Verifies that LLM replies written during the websocket flow
    have their `sources` persisted in the Message.metadata column.
    """

    async def _run_full_conversation_flow(self, framework: str) -> Conversation:
        """Override parent method with retrieval-oriented prompts to ensure sources are generated."""
        graphql_doc_id = to_global_id("DocumentType", self.doc.id)
        encoded_graphql_doc_id = quote(graphql_doc_id)
        encoded_corpus_id = quote(to_global_id("CorpusType", self.corpus.id))
        ws_path = (
            f"ws/document/{encoded_graphql_doc_id}/query/"
            f"corpus/{encoded_corpus_id}/?token={self.token}"
        )

        communicator = WebsocketCommunicator(self.application, ws_path)
        connected, _ = await communicator.connect()
        self.assertTrue(connected, "WebSocket for new conversation should connect.")

        # Use retrieval-oriented queries that will trigger vector store search
        response_1 = await self._assert_streaming_flow(
            communicator=communicator,
            query_text="Regarding US Code Title 1, what is the rule of construction for 'words importing the masculine gender'?",  # noqa: E501
            expected_response_key="query1_response",
            is_loaded_conversation=False,
        )
        response_2 = await self._assert_streaming_flow(
            communicator=communicator,
            query_text="What does US Code Title 1, Section 3 state about the term 'vessel'?",
            expected_response_key="query2_response",
            is_loaded_conversation=False,
        )

        await communicator.disconnect()

        conversation = await self._fetch_last_conversation()
        # Don't assert on specific response content since we only care about sources
        await self._log_and_assert_history(
            conversation,
            expected_queries=[
                "Regarding US Code Title 1, what is the rule of construction for 'words importing the masculine gender'?",  # noqa: E501
                "What does US Code Title 1, Section 3 state about the term 'vessel'?",
            ],
            expected_llm_replies=[response_1, response_2],
        )
        return conversation

    async def _run_loaded_conversation_flow(self, framework: str) -> Conversation:
        """Override parent method with retrieval-oriented prompts for loaded conversations."""
        conversation = await self._create_and_populate_conversation()

        history_check_agent = await for_document(
            document=self.doc,
            corpus=self.corpus,
            user_id=self.user.id,
            conversation_id=conversation.id,
        )
        actual_history_for_log = await history_check_agent.get_conversation_messages()
        print(
            f"Fetched {len(actual_history_for_log)} messages via agent API for "
            f"conversation {conversation.id} for logging."
        )

        graphql_doc_id = to_global_id("DocumentType", self.doc.id)
        encoded_graphql_doc_id = quote(graphql_doc_id)
        encoded_corpus_id = quote(to_global_id("CorpusType", self.corpus.id))
        graphql_convo_id = to_global_id("ConversationType", conversation.id)
        encoded_graphql_convo_id = quote(graphql_convo_id)
        ws_path = (
            f"ws/document/{encoded_graphql_doc_id}/query/corpus/{encoded_corpus_id}/"
            f"?token={self.token}&load_from_conversation_id={encoded_graphql_convo_id}"
        )

        communicator = WebsocketCommunicator(self.application, ws_path)
        connected, _ = await communicator.connect()
        self.assertTrue(connected, "WebSocket for loaded conversation should connect.")

        # Use retrieval-oriented queries
        response_1 = await self._assert_streaming_flow(
            communicator=communicator,
            query_text="Regarding US Code Title 1, what is the rule of construction for 'words importing the masculine gender'?",  # noqa: E501
            expected_response_key="query1_response",
            is_loaded_conversation=True,
        )
        response_2 = await self._assert_streaming_flow(
            communicator=communicator,
            query_text="What does US Code Title 1, Section 3 state about the term 'vessel'?",
            expected_response_key="query2_response",
            is_loaded_conversation=True,
        )

        await communicator.disconnect()

        await self._log_and_assert_history(
            conversation,
            expected_queries=[
                "Regarding US Code Title 1, what is the rule of construction for 'words importing the masculine gender'?",  # noqa: E501
                "What does US Code Title 1, Section 3 state about the term 'vessel'?",
            ],
            expected_llm_replies=[response_1, response_2],
            expect_prepopulated_messages=True,
        )
        return conversation

    def _assert_bbox(self, box: dict[str, Any], *, msg_prefix: str = "") -> None:
        """Assert a four-float/int bounding-box dictionary."""
        self.assertIsInstance(box, dict, msg_prefix + "must be dict")
        for edge in ("top", "left", "right", "bottom"):
            self.assertIn(edge, box, msg_prefix + f"missing '{edge}'")
            self.assertIsInstance(
                box[edge], (int, float), msg_prefix + f"'{edge}' not numeric"
            )

    async def _assert_sources_persisted(
        self, conversation: Conversation, framework: str
    ) -> None:
        # First, fetch ALL LLM messages to see what we have
        all_llm_messages = await database_sync_to_async(
            lambda: list(conversation.chat_messages.filter(msg_type="LLM"))
        )()

        # Enhanced diagnostics
        logger.error(
            f"[DIAGNOSTIC] Total LLM messages in conversation: {len(all_llm_messages)}"
        )
        for idx, msg in enumerate(all_llm_messages):
            logger.error(
                f"[DIAGNOSTIC] Message {idx}: id={msg.id}, msg_type={msg.msg_type}"
            )
            logger.error(
                f"[DIAGNOSTIC]   content preview: {msg.content[:100] if msg.content else 'NONE'}..."
            )
            logger.error(f"[DIAGNOSTIC]   data field type: {type(msg.data)}")
            logger.error(
                f"[DIAGNOSTIC]   data field keys: {msg.data.keys() if isinstance(msg.data, dict) else 'NOT A DICT'}"
            )
            if isinstance(msg.data, dict):
                logger.error(
                    f"[DIAGNOSTIC]   data['sources'] exists: {'sources' in msg.data}"
                )
                if "sources" in msg.data:
                    logger.error(
                        f"[DIAGNOSTIC]   data['sources'] value: {msg.data['sources']}"
                    )
                else:
                    logger.error(f"[DIAGNOSTIC]   Full data field: {msg.data}")

        # Fetch only LLM messages created in the conversation
        llm_messages = await database_sync_to_async(
            lambda: list(
                conversation.chat_messages.filter(msg_type="LLM").exclude(
                    Q(data__sources=None) | Q(data__sources=[])
                )
            )
        )()

        logger.error(
            f"[DIAGNOSTIC] LLM messages with non-empty sources: {len(llm_messages)}"
        )

        self.assertTrue(
            llm_messages,
            f"Expected at least one LLM message with non-empty `data['sources']`. "
            f"Found {len(all_llm_messages)} total LLM messages, {len(llm_messages)} with sources.",
        )

        # Make sure every retrieved message has a sources list **and** a reasoning timeline.
        try:
            import jsonschema  # type: ignore
        except ModuleNotFoundError:
            jsonschema = None  # Runtime validation becomes a no-op if lib missing

        for msg in llm_messages:
            sources = msg.data["sources"]
            self.assertIsInstance(sources, list)
            self.assertGreater(
                len(sources), 0, f"Message {msg.id} has empty sources list"
            )

            # ---------------- timeline presence ----------------
            timeline = msg.data.get("timeline")
            self.assertIsNotNone(
                timeline,
                f"Message {msg.id} is missing 'timeline' in data JSONField",
            )
            self.assertIsInstance(timeline, list)

            # Only frameworks the emit detailed events will have a timeline... currently only pydantic-ai
            if framework in [AgentFramework.PYDANTIC_AI.value]:
                self.assertGreater(
                    len(timeline), 0, f"Message {msg.id} has empty timeline list"
                )
                # Basic structural check – every entry must at least have a 'type'.
                for entry in timeline:
                    self.assertIn(
                        "type", entry, f"Timeline entry lacks 'type': {entry}"
                    )

                    # Optional: validate against JSON schema if jsonschema available
                    if jsonschema is not None:
                        try:
                            jsonschema.validate(entry, TIMELINE_ENTRY_SCHEMA)
                        except jsonschema.ValidationError as err:  # type: ignore[attr-defined]
                            self.fail(
                                f"Timeline entry schema validation failed for message {msg.id}: {err}"
                            )

    async def _test_sources_for_framework(
        self, framework: str, cassette_name: str, test_type: str
    ) -> None:
        """Helper method to test sources for a specific framework."""

        # Create fake 384-dimensional embedding to avoid VCR issues with embedder microservice
        fake_embedding = [0.0] * 384

        @vcr.use_cassette(
            cassette_name,
            filter_headers=["authorization", "x-api-key"],
            match_on=["method", "scheme", "host", "port", "path"],
            record_mode="none",
        )
        async def run_test():
            # Patch the embedder's _embed_text_impl to return fake embeddings
            # This avoids VCR interception issues with requests to local Docker services
            with patch(
                "opencontractserver.pipeline.embedders.sent_transformer_microservice."
                "MicroserviceEmbedder._embed_text_impl",
                return_value=fake_embedding,
            ):
                with override_settings(
                    LLMS_DEFAULT_AGENT_FRAMEWORK=framework,
                    LLMS_DOCUMENT_AGENT_FRAMEWORK=framework,
                    LLMS_CORPUS_AGENT_FRAMEWORK=framework,
                ):
                    if test_type == "new":
                        conversation = await self._run_full_conversation_flow(framework)
                    elif test_type == "loaded":
                        conversation = await self._run_loaded_conversation_flow(
                            framework
                        )
                    else:
                        raise ValueError(f"Unknown test_type: {test_type}")

                    await self._assert_sources_persisted(conversation, framework)

        await run_test()

    async def test_sources_are_logged_for_new_conversation(self) -> None:
        """Test sources are logged for new conversation across all frameworks."""
        for framework in ("pydantic_ai",):
            with self.subTest(framework=framework):
                await self._test_sources_for_framework(
                    framework=framework,
                    cassette_name=f"fixtures/vcr_cassettes/test_document_conversation_sources_ws_{framework}.yaml",
                    test_type="new",
                )

    async def test_sources_are_logged_for_loaded_conversation(self) -> None:
        """Test sources are logged for loaded conversation across all frameworks."""
        for framework in ("pydantic_ai",):
            with self.subTest(framework=framework):
                await self._test_sources_for_framework(
                    framework=framework,
                    cassette_name=f"fixtures/vcr_cassettes/test_document_conversation_sources_ws_loaded_{framework}.yaml",  # noqa: E501
                    test_type="loaded",
                )
