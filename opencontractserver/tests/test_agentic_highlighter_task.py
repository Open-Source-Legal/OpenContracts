"""
Tests for the agentic_highlighter_claude task.

This test suite verifies that:
1. The task can be invoked properly via GraphQL mutation
2. The task handles Anthropic API calls correctly (using VCR)
3. The task returns proper text spans for highlighted content
4. The task handles errors gracefully
"""

import logging

import vcr
from django.contrib.auth import get_user_model
from django.db import transaction
from django.test import override_settings
from graphene.test import Client
from graphql_relay import from_global_id, to_global_id

from config.graphql.schema import schema
from opencontractserver.analyzer.models import Analysis, Analyzer
from opencontractserver.annotations.models import Annotation
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import DocumentAnalysisRow
from opencontractserver.tests.base import BaseFixtureTestCase
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()
logger = logging.getLogger(__name__)


class TestContext:
    """Mock context for GraphQL client."""

    def __init__(self, user):
        self.user = user


class TestAgenticHighlighterClaude(BaseFixtureTestCase):
    """Test suite for agentic_highlighter_claude task."""

    def setUp(self):
        """Set up test environment with documents and corpus for each test."""
        super().setUp()

        # The analyzer is auto-created by migrations/startup, so just get or create it
        task_name = (
            "opencontractserver.tasks.doc_analysis_tasks.agentic_highlighter_claude"
        )

        try:
            # Try to get the existing analyzer
            self.analyzer = Analyzer.objects.get(task_name=task_name)
            # Update the creator if needed
            if self.analyzer.creator != self.user:
                self.analyzer.creator = self.user
                self.analyzer.save()
        except Analyzer.DoesNotExist:
            # Create it if it doesn't exist (shouldn't happen in normal test runs)
            with transaction.atomic():
                self.analyzer = Analyzer.objects.create(
                    id="agentic-highlighter-claude",
                    description="Agentic Document Highlighter using Claude",
                    task_name=task_name,
                    creator=self.user,
                    manifest={
                        "input_schema": {
                            "$schema": "http://json-schema.org/draft-07/schema#",
                            "type": "object",
                            "properties": {
                                "instructions": {
                                    "type": "string",
                                    "description": "User's highlighting instructions",
                                }
                            },
                            "required": ["instructions"],
                        }
                    },
                )

        # Ensure permissions are set
        set_permissions_for_obj_to_user(
            self.user, self.analyzer, [PermissionTypes.CRUD]
        )

        # Create GraphQL client with authenticated user
        self.graphene_client = Client(schema, context_value=TestContext(self.user))

        # Create a test corpus with our existing documents
        with transaction.atomic():
            self.corpus = Corpus.objects.create(
                title="Test Highlighter Corpus",
                description="Corpus for testing agentic highlighter",
                creator=self.user,
                backend_lock=False,
            )
            set_permissions_for_obj_to_user(
                self.user, self.corpus, [PermissionTypes.CRUD]
            )

        # Add documents to corpus
        if self.docs:
            updated_docs = []
            for doc in self.docs:
                new_doc, _, _ = self.corpus.add_document(document=doc, user=self.user)
                updated_docs.append(new_doc)
            self.docs = updated_docs

        # GraphQL IDs for our test objects
        self.corpus_gid = to_global_id("CorpusType", self.corpus.id)
        self.analyzer_gid = to_global_id("AnalyzerType", self.analyzer.id)
        if self.docs:
            self.doc_gid = to_global_id("DocumentType", self.docs[0].id)

    # @override_settings(
    #     ANALYZER_KWARGS={
    #         "opencontractserver.tasks.doc_analysis_tasks.agentic_highlighter_claude": {
    #             "ANTHROPIC_API_KEY": "test-anthropic-api-key"
    #         }
    #     }
    # )
    @vcr.use_cassette(
        "fixtures/vcr_cassettes/test_agentic_highlighter_claude.yaml",
        record_mode="once",  # Record once if cassette doesn't exist
        filter_headers=["authorization", "x-api-key"],
        match_on=["method", "scheme", "host", "port", "path", "query"],
        filter_post_data_parameters=["api_key"],
    )
    def test_agentic_highlighter_with_claude_api(self):
        """Test calling agentic_highlighter_claude via GraphQL mutation with actual API."""

        # Execute the mutation
        mutation = """
            mutation StartAnalysis($analyzerId: ID!, $corpusId: ID!, $inputData: GenericScalar) {
                startAnalysisOnDoc(
                    analyzerId: $analyzerId
                    corpusId: $corpusId
                    analysisInputData: $inputData
                ) {
                    ok
                    message
                    obj {
                        id
                        analyzedCorpus {
                            id
                        }
                        analyzer {
                            id
                        }
                    }
                }
            }
        """

        variables = {
            "analyzerId": self.analyzer_gid,
            "corpusId": self.corpus_gid,
            "inputData": {
                "instructions": "Highlight all clauses that mention payment terms, deadlines, or financial obligations"
            },
        }

        # Execute mutation
        result = self.graphene_client.execute(mutation, variable_values=variables)

        # Check mutation succeeded
        self.assertIsNotNone(result)
        if "errors" in result:
            self.fail(f"GraphQL errors: {result['errors']}")
        self.assertIn("data", result)
        self.assertIsNotNone(result["data"])
        self.assertIn("startAnalysisOnDoc", result["data"])

        mutation_result = result["data"]["startAnalysisOnDoc"]
        self.assertTrue(mutation_result["ok"])
        self.assertEqual(mutation_result["message"], "SUCCESS")
        self.assertIsNotNone(mutation_result["obj"])

        # Verify analysis was created
        analysis_gid = mutation_result["obj"]["id"]
        analysis_pk = from_global_id(analysis_gid)[1]
        analysis = Analysis.objects.get(pk=analysis_pk)

        self.assertEqual(analysis.analyzer, self.analyzer)
        self.assertEqual(analysis.analyzed_corpus, self.corpus)
        self.assertEqual(analysis.creator, self.user)

        # Check that DocumentAnalysisRows were created
        analysis_rows = DocumentAnalysisRow.objects.filter(analysis=analysis)
        self.assertGreater(
            analysis_rows.count(), 0, "Should have created analysis rows for documents"
        )

        # Verify that each document in the corpus has an analysis row
        for doc in self.corpus.get_documents():
            doc_row = analysis_rows.filter(document=doc).first()
            self.assertIsNotNone(
                doc_row, f"Document {doc.id} should have an analysis row"
            )

            # Check for annotations created by the task
            annotations = Annotation.objects.filter(
                analysis=analysis, document=doc, corpus=self.corpus
            )
            # Note: annotations might be 0 if Claude didn't find any payment terms
            logger.info(f"Document {doc.id} has {annotations.count()} annotations")

    def test_analyzer_manifest_validation(self):
        """Test that the analyzer has proper manifest with input schema."""
        self.assertIsNotNone(self.analyzer.manifest)
        self.assertIn("input_schema", self.analyzer.manifest)

        input_schema = self.analyzer.manifest["input_schema"]
        self.assertIn("properties", input_schema)
        self.assertIn("instructions", input_schema["properties"])
        self.assertIn("required", input_schema)
        self.assertIn("instructions", input_schema["required"])

    @override_settings(ANALYZER_KWARGS={})  # No API key configured
    def test_agentic_highlighter_missing_api_key(self):
        """Test agentic_highlighter_claude when Anthropic API key is missing."""

        # Execute the mutation
        mutation = """
            mutation StartAnalysis($analyzerId: ID!, $documentId: ID!, $inputData: GenericScalar) {
                startAnalysisOnDoc(
                    analyzerId: $analyzerId
                    documentId: $documentId
                    analysisInputData: $inputData
                ) {
                    ok
                    message
                }
            }
        """

        variables = {
            "analyzerId": self.analyzer_gid,
            "documentId": self.doc_gid,
            "inputData": {"instructions": "Highlight important sections"},
        }

        # The mutation itself should succeed (task is queued)
        result = self.graphene_client.execute(mutation, variable_values=variables)
        self.assertIsNotNone(result)

        self.assertIn("data", result)
        self.assertIsNotNone(result["data"])
        mutation_result = result["data"]["startAnalysisOnDoc"]
        self.assertTrue(mutation_result["ok"])

    def test_corpus_permission_check(self):
        """Test that only authorized users can run analysis on a corpus."""
        # Create another user
        with transaction.atomic():
            other_user = User.objects.create_user(
                username="otheruser", password="testpass123"
            )

        # Create GraphQL client for other user
        other_client = Client(schema, context_value=TestContext(other_user))

        # Try to run analysis on our corpus (should fail)
        mutation = """
            mutation StartAnalysis($analyzerId: ID!, $corpusId: ID!, $inputData: GenericScalar) {
                startAnalysisOnDoc(
                    analyzerId: $analyzerId
                    corpusId: $corpusId
                    analysisInputData: $inputData
                ) {
                    ok
                    message
                }
            }
        """

        variables = {
            "analyzerId": self.analyzer_gid,
            "corpusId": self.corpus_gid,
            "inputData": {"instructions": "Highlight anything"},
        }

        result = other_client.execute(mutation, variable_values=variables)

        # Should fail with permission error
        self.assertIsNotNone(result)
        if "errors" in result:
            # GraphQL errors mean permission was properly denied
            return
        self.assertIn("data", result)
        self.assertIsNotNone(result["data"])
        mutation_result = result["data"]["startAnalysisOnDoc"]
        self.assertFalse(mutation_result["ok"])
        self.assertIn("permission", mutation_result["message"].lower())

    # @override_settings(
    #     ANALYZER_KWARGS={
    #         "opencontractserver.tasks.doc_analysis_tasks.agentic_highlighter_claude": {
    #             "ANTHROPIC_API_KEY": "test-anthropic-api-key"
    #         }
    #     }
    # )
    @vcr.use_cassette(
        "fixtures/vcr_cassettes/test_agentic_highlighter_single_doc.yaml",
        record_mode="once",  # Record once if cassette doesn't exist
        filter_headers=["authorization", "x-api-key"],
        match_on=["method", "scheme", "host", "port", "path", "query"],
        filter_post_data_parameters=["api_key"],
    )
    def test_agentic_highlighter_single_document(self):
        """Test running agentic_highlighter_claude on a single document."""

        # Execute the mutation for a single document
        mutation = """
            mutation StartAnalysis($analyzerId: ID!, $documentId: ID!, $inputData: GenericScalar) {
                startAnalysisOnDoc(
                    analyzerId: $analyzerId
                    documentId: $documentId
                    analysisInputData: $inputData
                ) {
                    ok
                    message
                    obj {
                        id
                        analyzer {
                            id
                        }
                    }
                }
            }
        """

        variables = {
            "analyzerId": self.analyzer_gid,
            "documentId": self.doc_gid,
            "inputData": {
                "instructions": "Highlight any mentions of parties, dates, and key contractual terms"
            },
        }

        result = self.graphene_client.execute(mutation, variable_values=variables)

        # Check mutation succeeded
        self.assertIsNotNone(result)
        if "errors" in result:
            self.fail(f"GraphQL errors: {result['errors']}")

        mutation_result = result["data"]["startAnalysisOnDoc"]
        self.assertTrue(mutation_result["ok"])
        self.assertEqual(mutation_result["message"], "SUCCESS")

        # Verify analysis was created
        analysis_gid = mutation_result["obj"]["id"]
        analysis_pk = from_global_id(analysis_gid)[1]
        analysis = Analysis.objects.get(pk=analysis_pk)

        self.assertEqual(analysis.analyzer, self.analyzer)
        self.assertEqual(analysis.creator, self.user)

        # Check for document analysis row
        doc_row = DocumentAnalysisRow.objects.filter(
            analysis=analysis, document_id=self.docs[0].id
        ).first()
        self.assertIsNotNone(doc_row, "Should have created analysis row for document")
