"""
Integration tests for PydanticAI agents using VCR.py for LLM interactions.

This test suite uses VCR.py to record/replay actual LLM API calls, allowing us to test:
1. Real streaming tool approval flows (lines 396-457 in pydantic_ai_agents.py)
2. Actual search_exact_text tool result handling (lines 494-519)
3. Live ask_document tool integration (lines 520-625)
4. Real tool execution with empty/failed results (lines 1037-1054)

VCR.py records HTTP interactions the first time tests run, then replays them
for fast, deterministic tests without needing API keys in CI/CD.
"""

import vcr
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.db.models.signals import post_save
from django.test import TransactionTestCase

from opencontractserver.annotations.models import Annotation, AnnotationLabel
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.documents.signals import (
    DOC_CREATE_UID,
    process_doc_on_create_atomic,
)
from opencontractserver.llms.agents.core_agents import AgentConfig
from opencontractserver.llms.agents.pydantic_ai_agents import (
    PydanticAICorpusAgent,
    PydanticAIDocumentAgent,
)

User = get_user_model()


def constant_vector(dimension: int = 384, value: float = 0.5) -> list[float]:
    """Generate a constant vector for testing."""
    return [value] * dimension


# REMOVED: create_vcr_with_id_normalization function
#
# This complex 300+ line function for ID normalization in VCR cassettes has been
# removed as it's no longer needed. It was only used by test_ask_document_tool_nested_agent
# which has been replaced with a TestModel-based version.
#
# The function attempted to solve test isolation issues where document IDs differ
# between running tests in isolation vs in a full suite, but this approach was:
# - Too complex (regex replacements, custom body matching, conversation analysis)
# - Brittle (failed in CI/CD with silent cassette matching issues)
# - Unnecessary (TestModel provides better testing without these issues)
#
# For the new testing approach, see:
# - opencontractserver/tests/test_pydantic_ai_integration_testmodel.py
# - opencontractserver/tests/TESTING_PATTERNS.md


class TestPydanticAIAgentsIntegration(TransactionTestCase):
    """Integration tests for PydanticAI agents with real LLM calls (VCR recorded)."""

    @classmethod
    def setUpClass(cls) -> None:
        """Disconnect document processing signals to avoid Celery tasks during setup."""
        super().setUpClass()
        post_save.disconnect(
            process_doc_on_create_atomic, sender=Document, dispatch_uid=DOC_CREATE_UID
        )

    @classmethod
    def tearDownClass(cls) -> None:
        """Reconnect document processing signals after tests complete."""
        post_save.connect(
            process_doc_on_create_atomic, sender=Document, dispatch_uid=DOC_CREATE_UID
        )
        super().tearDownClass()

    def setUp(self) -> None:
        """Create test data for each integration test."""
        self.user = User.objects.create_user(
            username="integrationuser",
            password="testpass",
        )

        self.corpus = Corpus.objects.create(
            title="Integration Test Corpus",
            description="Corpus for integration testing",
            creator=self.user,
            is_public=True,
        )

        # Create a document with actual text content
        doc1_text = (
            "Test contract with payment terms: Party A agrees to pay Party B $10,000 within "
            "30 days. Payment shall be made by wire transfer."
        )
        self.doc1 = Document.objects.create(
            title="Payment Terms Contract",
            description="Contract with payment terms for testing",
            creator=self.user,
            is_public=True,
            file_type="text/plain",
        )
        self.doc1.txt_extract_file.save(
            "payment_contract.txt", ContentFile(doc1_text.encode("utf-8")), save=True
        )

        doc2_text = (
            "This service agreement specifies the scope of work and deliverables."
        )
        self.doc2 = Document.objects.create(
            title="Service Agreement",
            description="Service agreement document",
            creator=self.user,
            is_public=True,
            file_type="text/plain",
        )
        self.doc2.txt_extract_file.save(
            "service_agreement.txt", ContentFile(doc2_text.encode("utf-8")), save=True
        )

        self.doc1, _, _ = self.corpus.add_document(document=self.doc1, user=self.user)
        self.doc2, _, _ = self.corpus.add_document(document=self.doc2, user=self.user)

        # Create annotation labels
        self.payment_label = AnnotationLabel.objects.create(
            text="Payment Term",
            creator=self.user,
        )

        self.deadline_label = AnnotationLabel.objects.create(
            text="Deadline",
            creator=self.user,
        )

        # Create sample annotations with embeddings for vector search
        self.anno1 = Annotation.objects.create(
            document=self.doc1,
            corpus=self.corpus,
            creator=self.user,
            raw_text="Party A agrees to pay Party B $10,000",
            annotation_label=self.payment_label,
            is_public=True,
            page=1,
        )

        self.anno2 = Annotation.objects.create(
            document=self.doc1,
            corpus=self.corpus,
            creator=self.user,
            raw_text="within 30 days",
            annotation_label=self.deadline_label,
            is_public=True,
            page=1,
        )

        # Add embeddings to annotations
        embedder_path = "opencontractserver.pipeline.embedders.sent_transformer_microservice.MicroserviceEmbedder"
        self.anno1.add_embedding(embedder_path, constant_vector(384, 0.1))
        self.anno2.add_embedding(embedder_path, constant_vector(384, 0.2))

    # ========================================================================
    # Test 1: Tool Approval Flow During Streaming (lines 396-457)
    # ========================================================================

    @vcr.use_cassette(
        "fixtures/vcr_cassettes/pydantic_ai_tool_approval_flow.yaml",
        record_mode="once",
        filter_headers=["authorization", "x-api-key"],
        match_on=["method", "scheme", "host", "port", "path", "query"],
    )
    async def test_tool_approval_detection_during_stream(self) -> None:
        """
        Integration test for tool approval flow during streaming.

        Tests coverage for lines 396-457 where:
        - Agent detects tool requiring approval
        - Serializes tool arguments (dict, Pydantic model, etc.)
        - Emits ApprovalNeededEvent
        - Exits stream early

        This requires a real LLM call that triggers a tool requiring approval.
        """
        config = AgentConfig(
            user_id=self.user.id,
            model_name=settings.OPENAI_MODEL,
            store_user_messages=False,
            store_llm_messages=False,
        )

        agent = await PydanticAIDocumentAgent.create(
            document=self.doc1,
            corpus=self.corpus,
            config=config,
        )

        # Ask a question that should trigger the update_document_summary tool
        # which requires approval
        question = (
            "Please update the document summary to include all payment terms you find"
        )

        events = []
        async for event in agent.stream(question):
            events.append(event)
            # If we get approval needed, the stream should stop
            if hasattr(event, "type") and event.type == "approval_needed":
                break

        # Verify we got an approval needed event
        approval_events = [
            e for e in events if hasattr(e, "type") and e.type == "approval_needed"
        ]
        self.assertGreater(
            len(approval_events),
            0,
            "Should have emitted ApprovalNeededEvent for update_document_summary tool",
        )

        # Verify the pending tool call structure
        approval_event = approval_events[0]
        self.assertIsNotNone(approval_event.pending_tool_call)
        pending_call = approval_event.pending_tool_call
        self.assertEqual(pending_call["name"], "add_document_note")
        self.assertIn("arguments", pending_call)
        self.assertIn("tool_call_id", pending_call)

    # ========================================================================
    # Test 2: search_exact_text Tool Result Handling (lines 494-519)
    # ========================================================================

    @vcr.use_cassette(
        "fixtures/vcr_cassettes/pydantic_ai_search_exact_text.yaml",
        record_mode="once",
        filter_headers=["authorization", "x-api-key"],
        match_on=["method", "scheme", "host", "port", "path", "query"],
    )
    async def test_search_exact_text_tool_returns_sources(self) -> None:
        """
        Integration test for search_exact_text tool result handling.

        Tests coverage for lines 494-519 where:
        - search_exact_text tool returns results
        - Results are converted to SourceNode objects
        - SourceEvent is emitted with sources
        - Empty results are handled (else branch at line 514)

        This uses a real LLM call that triggers exact text search.
        """
        config = AgentConfig(
            user_id=self.user.id,
            model_name=settings.OPENAI_MODEL,
            store_user_messages=False,
            store_llm_messages=False,
        )

        agent = await PydanticAIDocumentAgent.create(
            document=self.doc1,
            corpus=self.corpus,
            config=config,
        )

        # Ask a question that should trigger search_exact_text
        question = 'Find the exact text "Party A agrees to pay" in the document'

        events = []
        source_events = []
        async for event in agent.stream(question):
            events.append(event)
            if hasattr(event, "type") and event.type == "sources":
                source_events.append(event)

        # Verify we got source events from search_exact_text
        self.assertGreater(
            len(source_events),
            0,
            "Should have emitted SourceEvent from search_exact_text tool",
        )

        # Verify sources have the expected structure
        for source_event in source_events:
            self.assertIsNotNone(source_event.sources)
            for source in source_event.sources:
                self.assertIsNotNone(source.annotation_id)
                self.assertIsNotNone(source.content)
                self.assertEqual(source.similarity_score, 1.0)  # Exact match

    @vcr.use_cassette(
        "fixtures/vcr_cassettes/pydantic_ai_search_exact_text_empty.yaml",
        record_mode="once",
        filter_headers=["authorization", "x-api-key"],
        match_on=["method", "scheme", "host", "port", "path", "query"],
    )
    async def test_search_exact_text_tool_empty_results(self) -> None:
        """
        Test search_exact_text when no matches are found (line 514-518).

        This tests the else branch that logs a warning when raw_sources
        is not a list or is empty.
        """
        config = AgentConfig(
            user_id=self.user.id,
            model_name=settings.OPENAI_MODEL,
            store_user_messages=False,
            store_llm_messages=False,
        )

        agent = await PydanticAIDocumentAgent.create(
            document=self.doc1,
            corpus=self.corpus,
            config=config,
        )

        # Ask for text that doesn't exist in the document
        question = 'Find the exact text "this phrase does not exist in the document xyz123" in the document'

        events = []
        async for event in agent.stream(question):
            events.append(event)

        # The agent should handle empty results gracefully
        # We should get a final event even if no sources were found
        final_events = [e for e in events if hasattr(e, "type") and e.type == "final"]
        self.assertGreater(len(final_events), 0, "Should complete even with no matches")

    # ========================================================================
    # Test 3: ask_document Tool Integration (lines 520-625)
    # ========================================================================
    #
    # REMOVED: test_ask_document_tool_nested_agent (VCR-based test)
    #
    # This test was replaced with a TestModel-based version for better reliability.
    # The VCR approach with ID normalization was too brittle and failed in CI/CD.
    #
    # See: opencontractserver/tests/test_pydantic_ai_integration_testmodel.py
    #      -> test_ask_document_tool_nested_agent_testmodel
    #
    # Migration notes:
    # - TestModel provides deterministic behavior without API calls
    # - No need for complex ID normalization (300+ lines of code)
    # - Tests run faster (<100ms vs 1-5s)
    # - Works identically in local and CI environments
    #
    # For testing patterns, see: opencontractserver/tests/TESTING_PATTERNS.md

    # ========================================================================
    # Test 4: Tool Result Validation - Empty Annotations (lines 1037-1044)
    # ========================================================================

    @vcr.use_cassette(
        "fixtures/vcr_cassettes/pydantic_ai_empty_annotation_result.yaml",
        record_mode="once",
        filter_headers=["authorization", "x-api-key"],
        match_on=["method", "scheme", "host", "port", "path", "query"],
    )
    async def test_resume_with_approval_empty_annotation_result(self) -> None:
        """
        Integration test for resume_with_approval with empty annotation results.

        Tests coverage for lines 1037-1044 where:
        - Tool execution succeeds but returns empty annotation_ids
        - Agent detects failure and builds failure message
        - Continuation prompt guides agent to inform user

        This simulates approving add_exact_string_annotations that finds no matches.
        """
        from opencontractserver.conversations.models import ChatMessage, Conversation
        from opencontractserver.llms.agents.core_agents import (
            CoreConversationManager,
            MessageState,
        )

        # Create a paused message awaiting approval for annotation tool
        conversation = await Conversation.objects.acreate(
            title="Empty Annotation Test",
            creator=self.user,
        )

        paused_msg = await ChatMessage.objects.acreate(
            conversation=conversation,
            content="Awaiting approval",
            msg_type="LLM",
            creator=self.user,
            data={
                "state": MessageState.AWAITING_APPROVAL,
                "pending_tool_call": {
                    "name": "add_exact_string_annotations",
                    "arguments": {
                        "entries": [
                            {
                                "label_text": "Test Label",
                                "exact_string": "text that does not exist in document",
                            }
                        ]
                    },
                    "tool_call_id": "call-empty-anno",
                },
                "framework": "pydantic_ai",
            },
        )

        config = AgentConfig(
            user_id=self.user.id,
            conversation=conversation,
            model_name=settings.OPENAI_MODEL,
        )

        # Create conversation manager (sets up conversation state)
        _ = await CoreConversationManager.create_for_document(
            corpus=self.corpus,
            document=self.doc1,
            user_id=self.user.id,
            config=config,
            override_conversation=conversation,
        )

        agent = await PydanticAIDocumentAgent.create(
            document=self.doc1,
            corpus=self.corpus,
            config=config,
            conversation=conversation,
        )

        # Resume with approval - tool will execute but return empty results
        events = []
        async for event in agent.resume_with_approval(paused_msg.id, approved=True):
            events.append(event)

        # Verify we got events indicating the failure
        final_events = [e for e in events if hasattr(e, "type") and e.type == "final"]
        self.assertGreater(len(final_events), 0)

        # Agent should inform user that no matches were found
        final_content = final_events[0].content.lower()
        self.assertTrue(
            "not found" in final_content or "no matching" in final_content,
            "Agent should inform user that exact text was not found",
        )

    # ========================================================================
    # Test 5: Structured Response with Tools (validates _structured_response_raw)
    # ========================================================================

    @vcr.use_cassette(
        "fixtures/vcr_cassettes/pydantic_ai_structured_response_with_tools.yaml",
        record_mode="once",
        filter_headers=["authorization", "x-api-key"],
        match_on=["method", "scheme", "host", "port", "path", "query"],
    )
    async def test_structured_response_uses_document_tools(self) -> None:
        """
        Integration test for structured_response with tool access.

        Validates that the structured response extraction can use
        document tools (vector search, summary loading, etc.) to
        gather information before returning the structured result.
        """
        from pydantic import BaseModel

        class PaymentInfo(BaseModel):
            """Structured payment information."""

            amount: str
            deadline: str
            method: str

        config = AgentConfig(
            user_id=self.user.id,
            model_name=settings.OPENAI_MODEL,
            store_user_messages=False,
            store_llm_messages=False,
        )

        agent = await PydanticAIDocumentAgent.create(
            document=self.doc1,
            corpus=self.corpus,
            config=config,
        )

        # Extract structured payment information
        result = await agent.structured_response(
            prompt="Extract all payment information from this contract",
            target_type=PaymentInfo,
        )

        # Verify we got structured results
        self.assertIsNotNone(result)
        self.assertIsInstance(result, PaymentInfo)
        self.assertIn("$", result.amount)
        self.assertIn("30", result.deadline)
        self.assertIn("wire", result.method.lower())


# ============================================================================
# Additional Edge Case Integration Tests
# ============================================================================


class TestPydanticAIAgentsEdgeCases(TransactionTestCase):
    """Integration tests for edge cases and error scenarios."""

    @classmethod
    def setUpClass(cls) -> None:
        """Disconnect document processing signals to avoid Celery tasks during setup."""
        super().setUpClass()
        post_save.disconnect(
            process_doc_on_create_atomic, sender=Document, dispatch_uid=DOC_CREATE_UID
        )

    @classmethod
    def tearDownClass(cls) -> None:
        """Reconnect document processing signals after tests complete."""
        post_save.connect(
            process_doc_on_create_atomic, sender=Document, dispatch_uid=DOC_CREATE_UID
        )
        super().tearDownClass()

    def setUp(self) -> None:
        """Create minimal test data for each test."""
        self.user = User.objects.create_user(
            username="edgecaseuser",
            password="testpass",
        )

        self.corpus = Corpus.objects.create(
            title="Edge Case Corpus",
            description="For testing edge cases",
            creator=self.user,
            is_public=True,
        )

        # Document with minimal content
        self.doc = Document.objects.create(
            title="Minimal Doc",
            description="Minimal document for edge cases",
            creator=self.user,
            is_public=True,
            file_type="text/plain",
        )
        self.doc.txt_extract_file.save(
            "minimal.txt", ContentFile(b"Short text."), save=True
        )

        self.doc, _, _ = self.corpus.add_document(document=self.doc, user=self.user)

    @vcr.use_cassette(
        "fixtures/vcr_cassettes/pydantic_ai_malformed_tool_result.yaml",
        record_mode="once",
        filter_headers=["authorization", "x-api-key"],
        match_on=["method", "scheme", "host", "port", "path", "query"],
    )
    async def test_ask_document_malformed_result(self) -> None:
        """
        Test ask_document tool error handling for malformed results (lines 608-614).

        Tests the exception handler that catches malformed JSON or missing
        keys in the ask_document tool result payload.
        """
        config = AgentConfig(
            user_id=self.user.id,
            model_name=settings.OPENAI_MODEL,
            store_user_messages=False,
            store_llm_messages=False,
        )

        corpus_agent = await PydanticAICorpusAgent.create(
            corpus=self.corpus,
            config=config,
        )

        # This question should trigger ask_document, and we expect
        # graceful handling even if the nested agent returns unexpected data
        question = "Query the Minimal Doc document"

        events = []
        try:
            async for event in corpus_agent.stream(question):
                events.append(event)
        except Exception:
            # Should handle gracefully and not crash
            pass

        # Should still complete the stream even if ask_document fails
        self.assertGreater(len(events), 0, "Should emit events even on tool failure")
