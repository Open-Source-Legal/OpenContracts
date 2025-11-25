#  Copyright (C) 2022  John Scrudato

import json
import logging

import factory
import responses
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models.signals import post_save
from django.test import TestCase
from django.test.client import Client as DjangoClient
from graphene.test import Client
from graphql_relay import from_global_id, to_global_id
from rest_framework.test import APIClient

from config.graphql.schema import schema
from opencontractserver.analyzer.models import Analysis, Analyzer, GremlinEngine
from opencontractserver.annotations.models import Annotation, AnnotationLabel, LabelSet
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.tasks.analyzer_tasks import (
    import_analysis,
    install_analyzer_task,
    request_gremlin_manifest,
    start_analysis,
)
from opencontractserver.tests.fixtures import (
    SAMPLE_GREMLIN_ENGINE_MANIFEST_PATH,
    SAMPLE_PDF_FILE_ONE_PATH,
    SAMPLE_PDF_FILE_TWO_PATH,
    create_mock_submission_response,
    generate_random_analyzer_return_values,
)

User = get_user_model()

logger = logging.getLogger(__name__)


class TestContext:
    def __init__(self, user):
        self.user = user


class GraphQLAnalyzerTestCase(TestCase):
    @factory.django.mute_signals(post_save)
    def setUp(self):
        logger.info("Starting setUp method")

        # Setup a test user
        with transaction.atomic():
            self.user = User.objects.create_user(username="bob", password="12345678")
        logger.info(f"Created test user: {self.user}")

        self.graphene_client = Client(schema, context_value=TestContext(self.user))
        logger.info("Created graphene client")

        # Setup a test JWT token for user
        executed_login_data = self.graphene_client.execute(
            """
            mutation ($username: String!, $password: String!) {
                tokenAuth(username: $username, password: $password) {
                      token
                      refreshExpiresIn
                      payload
                }
            }
            """,
            variable_values={"username": "bob", "password": "12345678"},
        )
        logger.info(f"Executed login: {executed_login_data}")

        self.jwt_token = executed_login_data["data"]["tokenAuth"]["token"]
        logger.info(f"JWT token retrieved: {self.jwt_token}")

        # Create a test client to make GraphQL requests
        self.client_header = {"HTTP_AUTHORIZATION": f"Bearer {self.jwt_token}"}
        self.django_client = DjangoClient()
        self.authenticated_client = APIClient()
        self.authenticated_client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {self.jwt_token}"
        )
        logger.info("Created test clients")

        # Create a test corpus
        with transaction.atomic():
            self.corpus = Corpus.objects.create(
                title="Test Analysis Corpus", creator=self.user, backend_lock=False
            )
        self.global_corpus_id = to_global_id("CorpusType", self.corpus.id)
        logger.info(f"Created test corpus: {self.corpus}")

        self.doc_ids = []
        sample_pdfs = [SAMPLE_PDF_FILE_ONE_PATH, SAMPLE_PDF_FILE_TWO_PATH]

        for index, pdf_path in enumerate(sample_pdfs):
            with pdf_path.open("rb") as pdf_file:
                pdf_contents = ContentFile(pdf_file.read())
                with transaction.atomic():
                    document = Document.objects.create(
                        title=f"TestDoc{index}",
                        description="Sample PDF Document",
                        creator=self.user,
                    )
                    document.pdf_file.save(f"dummy_file_{index}.pdf", pdf_contents)

                    self.doc_ids.append(document.id)
                    logger.info(f"Created document with id: {document.id}")

        logger.info(f"{len(self.doc_ids)} pdfs loaded for analysis")

        # Link docs to corpus
        for doc_id in self.doc_ids:
            doc = Document.objects.get(id=doc_id)
            self.corpus.add_document(document=doc, user=self.user)
        logger.info("Linked documents to corpus")

        # Setup a test gremlin + analyzers
        with transaction.atomic():
            self.gremlin = GremlinEngine.objects.create(
                url="http://localhost:8000", creator=self.user
            )
        logger.info(f"Created GremlinEngine: {self.gremlin}")

        with responses.RequestsMock() as rsps:
            rsps.add(
                responses.GET,
                self.gremlin.url + "/api/analyzers",
                json=json.loads(SAMPLE_GREMLIN_ENGINE_MANIFEST_PATH.open("r").read()),
                status=200,
            )
            analyzer_manifests = (
                request_gremlin_manifest.si(gremlin_id=self.gremlin.id).apply().get()
            )
            self.assertIsNotNone(analyzer_manifests)
        logger.info(f"Retrieved analyzer manifests: {analyzer_manifests}")

        with transaction.atomic():
            install_analyzer_task.si(
                gremlin_id=self.gremlin.id,
                analyzer_manifests=analyzer_manifests,
            ).apply().get()

        # The fixture contains 1 analyzer, but auto-created analyzers may also exist
        # Just verify at least the expected analyzer was created
        self.assertGreaterEqual(Analyzer.objects.all().count(), 1)
        logger.info(f"Installed {Analyzer.objects.all().count()} analyzers")

        # Import a faux analysis
        # Try to select a Gremlin-based analyzer first
        self.analyzer = Analyzer.objects.filter(host_gremlin=self.gremlin).first()
        if self.analyzer:
            # Only set up HTTP mocks for Gremlin-based analyzers
            self.analyzer_global_id = to_global_id("AnalyzerType", self.analyzer.id)
            logger.info(f"Selected Gremlin analyzer for faux analysis: {self.analyzer}")

            with responses.RequestsMock() as rsps:
                rsps.add(
                    responses.POST,
                    f"{self.gremlin.url}/api/jobs/submit",
                    body=json.dumps(create_mock_submission_response(self.analyzer.id)),
                    status=200,
                    content_type="application/json",
                )

                with transaction.atomic():
                    self.analysis = Analysis.objects.create(
                        analyzer_id=self.analyzer.id,
                        analyzed_corpus_id=self.corpus.id,
                        creator=self.user,
                    )
                logger.info(f"Created Analysis object: {self.analysis}")

                start_analysis.si(analysis_id=self.analysis.id).apply().get()
        else:
            # Use a task-based analyzer if no Gremlin analyzers found
            self.analyzer = Analyzer.objects.filter(host_gremlin__isnull=True).first()
            if not self.analyzer:
                # Fallback to any analyzer
                self.analyzer = Analyzer.objects.first()
            self.analyzer_global_id = to_global_id("AnalyzerType", self.analyzer.id)
            logger.info(
                f"Selected non-Gremlin analyzer for faux analysis: {self.analyzer}"
            )

            with transaction.atomic():
                self.analysis = Analysis.objects.create(
                    analyzer_id=self.analyzer.id,
                    analyzed_corpus_id=self.corpus.id,
                    creator=self.user,
                )
            logger.info(f"Created Analysis object: {self.analysis}")

            # No HTTP mocking needed for task-based analyzers
            start_analysis.si(analysis_id=self.analysis.id).apply().get()

        logger.info(f"Started analysis with ID: {self.analysis.id}")

        # Mock callback results to actually create data
        mock_gremlin_response_data = generate_random_analyzer_return_values(
            doc_ids=self.doc_ids
        )
        logger.info("Generated mock gremlin response data")

        analysis_result = (
            import_analysis.si(
                creator_id=self.user.id,
                analysis_id=self.analysis.id,
                analysis_results=mock_gremlin_response_data,
            )
            .apply()
            .get()
        )
        logger.info(f"Imported analysis result: {analysis_result}")

        self.assertTrue(analysis_result)

        # Rough and ready test of imports - count database objs
        annotation_count = Annotation.objects.all().count()
        label_set_count = LabelSet.objects.all().count()
        label_count = AnnotationLabel.objects.all().count()

        logger.info(f"Created {annotation_count} annotations")
        logger.info(f"Created {label_set_count} label sets")
        logger.info(f"Created {label_count} labels")

        self.assertTrue(annotation_count > 0)
        self.assertTrue(label_set_count > 0)
        self.assertTrue(label_count > 0)

        logger.info("setUp method completed successfully")

    def test_start_document_extract(self):
        logger.info("Test start extract for single document...")

        # First, create a fieldset
        CREATE_FIELDSET_MUTATION = """
        mutation createFieldset($name: String!, $description: String!) {
          createFieldset(name: $name, description: $description) {
            ok
            message
            obj {
              id
            }
          }
        }
        """

        fieldset_response = self.graphene_client.execute(
            CREATE_FIELDSET_MUTATION,
            variables={
                "name": "Test Fieldset",
                "description": "A test fieldset for document extract",
            },
        )

        self.assertTrue(fieldset_response["data"]["createFieldset"]["ok"])
        fieldset_id = fieldset_response["data"]["createFieldset"]["obj"]["id"]

        # Now, start an extract for a single document
        START_DOCUMENT_EXTRACT_MUTATION = """
        mutation startExtractForDoc($documentId: ID!, $fieldsetId: ID!) {
          startExtractForDoc(documentId: $documentId, fieldsetId: $fieldsetId) {
            ok
            message
            obj {
              id
              name
              started
            }
          }
        }
        """

        document_id = to_global_id(
            "DocumentType", self.doc_ids[0]
        )  # Use the first document

        extract_response = self.graphene_client.execute(
            START_DOCUMENT_EXTRACT_MUTATION,
            variables={"documentId": document_id, "fieldsetId": fieldset_id},
        )

        logger.info(f"Start document extract response: {extract_response}")

        self.assertTrue(extract_response["data"]["startExtractForDoc"]["ok"])
        self.assertIsNotNone(
            extract_response["data"]["startExtractForDoc"]["obj"]["id"]
        )
        self.assertIsNotNone(
            extract_response["data"]["startExtractForDoc"]["obj"]["started"]
        )

        # Verify that an Extract object was created in the database
        from opencontractserver.extracts.models import Extract

        extract_id = from_global_id(
            extract_response["data"]["startExtractForDoc"]["obj"]["id"]
        )[1]
        extract = Extract.objects.get(id=extract_id)

        self.assertEqual(extract.documents.count(), 1)
        self.assertEqual(extract.documents.first().id, self.doc_ids[0])

        logger.info("SUCCESS - Document extract started successfully")

    def test_start_document_analysis(self):
        logger.info("Test start analysis for single document...")

        START_DOCUMENT_ANALYSIS_MUTATION = """
        mutation startAnalysisOnDoc($documentId: ID!, $analyzerId: ID!) {
          startAnalysisOnDoc(documentId: $documentId, analyzerId: $analyzerId) {
            ok
            message
            obj {
              id
              analysisStarted
              analyzer {
                id
                analyzerId
              }
            }
          }
        }
        """

        document_id = to_global_id(
            "DocumentType", self.doc_ids[0]
        )  # Use the first document

        analysis_response = self.graphene_client.execute(
            START_DOCUMENT_ANALYSIS_MUTATION,
            variables={
                "documentId": document_id,
                "analyzerId": self.analyzer_global_id,
            },
        )

        logger.info(f"Start document analysis response: {analysis_response}")

        self.assertTrue(analysis_response["data"]["startAnalysisOnDoc"]["ok"])
        self.assertIsNotNone(
            analysis_response["data"]["startAnalysisOnDoc"]["obj"]["id"]
        )
        self.assertIsNotNone(
            analysis_response["data"]["startAnalysisOnDoc"]["obj"]["analysisStarted"]
        )
        self.assertEqual(
            analysis_response["data"]["startAnalysisOnDoc"]["obj"]["analyzer"][
                "analyzerId"
            ],
            self.analyzer.id,
        )

        # Verify that an Analysis object was created in the database
        analysis_id = from_global_id(
            analysis_response["data"]["startAnalysisOnDoc"]["obj"]["id"]
        )[1]
        analysis = Analysis.objects.get(id=analysis_id)
        self.assertIsNotNone(analysis)

        logger.info("SUCCESS - Document analysis started successfully")

    def test_start_document_analysis_permissions(self):
        logger.info("Test start analysis permissions for single document...")

        START_DOCUMENT_ANALYSIS_MUTATION = """
        mutation startAnalysisOnDoc($documentId: ID!, $analyzerId: ID!) {
          startAnalysisOnDoc(documentId: $documentId, analyzerId: $analyzerId) {
            ok
            message
            obj {
              id
            }
          }
        }
        """

        # Test with a document owned by the user (should succeed)
        owned_document_id = to_global_id("DocumentType", self.doc_ids[0])
        owned_response = self.graphene_client.execute(
            START_DOCUMENT_ANALYSIS_MUTATION,
            variables={
                "documentId": owned_document_id,
                "analyzerId": self.analyzer_global_id,
            },
        )
        self.assertTrue(owned_response["data"]["startAnalysisOnDoc"]["ok"])

        # Create a document owned by another user
        other_user = User.objects.create_user(username="alice", password="87654321")
        with transaction.atomic():
            other_document = Document.objects.create(
                title="Other User's Document",
                description="Document owned by another user",
                creator=other_user,
            )

        # Test with a document not owned by the user (should fail)
        other_document_id = to_global_id("DocumentType", other_document.id)
        other_response = self.graphene_client.execute(
            START_DOCUMENT_ANALYSIS_MUTATION,
            variables={
                "documentId": other_document_id,
                "analyzerId": self.analyzer_global_id,
            },
        )
        self.assertFalse(other_response["data"]["startAnalysisOnDoc"]["ok"])
        self.assertIn(
            "permission", other_response["data"]["startAnalysisOnDoc"]["message"]
        )

        # Make the other user's document public
        other_document.is_public = True
        other_document.save()

        # Test with a public document not owned by the user (should succeed)
        public_response = self.graphene_client.execute(
            START_DOCUMENT_ANALYSIS_MUTATION,
            variables={
                "documentId": other_document_id,
                "analyzerId": self.analyzer_global_id,
            },
        )
        self.assertTrue(public_response["data"]["startAnalysisOnDoc"]["ok"])

        logger.info("SUCCESS - Document analysis permission checks passed")

    def test_create_extract_permissions(self):
        logger.info("Test create extract permissions...")

        CREATE_EXTRACT_MUTATION = """
        mutation createExtract($name: String!, $corpusId: ID, $fieldsetName: String!) {
          createExtract(name: $name, corpusId: $corpusId, fieldsetName: $fieldsetName) {
            ok
            msg
            obj {
              id
            }
          }
        }
        """

        # Test with a corpus owned by the user (should succeed)
        owned_response = self.graphene_client.execute(
            CREATE_EXTRACT_MUTATION,
            variables={
                "name": "Owned Extract",
                "corpusId": self.global_corpus_id,
                "fieldsetName": "Owned Fieldset",
            },
        )
        self.assertTrue(owned_response["data"]["createExtract"]["ok"])

        # Create a corpus owned by another user
        other_user = User.objects.create_user(username="charlie", password="87654321")
        with transaction.atomic():
            other_corpus = Corpus.objects.create(
                title="Other User's Corpus",
                creator=other_user,
                backend_lock=False,
            )

        # Test with a corpus not owned by the user (should fail)
        other_corpus_id = to_global_id("CorpusType", other_corpus.id)
        other_response = self.graphene_client.execute(
            CREATE_EXTRACT_MUTATION,
            variables={
                "name": "Other Extract",
                "corpusId": other_corpus_id,
                "fieldsetName": "Other Fieldset",
            },
        )
        self.assertFalse(other_response["data"]["createExtract"]["ok"])
        self.assertIn("permission", other_response["data"]["createExtract"]["msg"])

        # Make the other user's corpus public
        other_corpus.is_public = True
        other_corpus.save()

        # Test with a public corpus not owned by the user (should succeed)
        public_response = self.graphene_client.execute(
            CREATE_EXTRACT_MUTATION,
            variables={
                "name": "Public Extract",
                "corpusId": other_corpus_id,
                "fieldsetName": "Public Fieldset",
            },
        )
        self.assertTrue(public_response["data"]["createExtract"]["ok"])

        logger.info("SUCCESS - Extract creation permission checks passed")
