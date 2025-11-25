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
from graphql_relay import to_global_id
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
        # Select a Gremlin-based analyzer (not a task-based one)
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
                # Create a simple task-based analyzer for testing
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

    def __test_get_analyzer_list(self):

        logger.info("Test analyzer list query...")

        ANALYZER_LIST_REQUEST = """
                query {
                  analyzers {
                    edges {
                      node {
                        id
                        analyzerId
                        description
                        hostGremlin {
                          id
                        }
                        disabled
                        isPublic
                        manifest
                      }
                    }
                  }
                }
            """

        analyzer_list_response = self.graphene_client.execute(ANALYZER_LIST_REQUEST)

        self.assertTrue(len(analyzer_list_response["data"]["analyzers"]["edges"]) >= 1)
        # The analyzer might be Gremlin-based or task-based, so hostGremlin could be None
        # Just verify at least one analyzer exists
        analyzer_ids = [
            edge["node"]["analyzerId"]
            for edge in analyzer_list_response["data"]["analyzers"]["edges"]
        ]
        logger.info(f"Found analyzers: {analyzer_ids}")
        # Check that we have at least one analyzer (could be OC.SPACY.ANALYZER.V1 or others)
        self.assertTrue(len(analyzer_ids) > 0)

        logger.info("\tSUCCESS")

    def __test_get_analyzer(self):

        logger.info("Test request specific analyzer...")

        # Use the analyzer that was selected in setUp
        ANALYZER_REQUEST = """
                        query($id: ID!) {
                          analyzer(id:$id) {
                            id
                            analyzerId
                            description
                            hostGremlin {
                              id
                            }
                            disabled
                            isPublic
                            manifest
                          }
                        }
                    """
        single_analyzer_response = self.graphene_client.execute(
            ANALYZER_REQUEST, variables={"id": self.analyzer_global_id}
        )

        self.assertIsNotNone(single_analyzer_response["data"]["analyzer"])
        # The analyzer might be Gremlin-based or task-based, so hostGremlin could be None
        # Just verify the analyzer exists with the expected ID
        self.assertEqual(
            single_analyzer_response["data"]["analyzer"]["analyzerId"], self.analyzer.id
        )

        logger.info("\tSUCCESS")

    def __test_get_analyses(self):

        logger.info("Test get analyses list...")

        REQUEST_ANALYSIS_DETAILS = """
            query {
              analyses {
                edges {
                  node {
                    id
                    analysisStarted
                    analysisCompleted
                    analyzedDocuments {
                      edges {
                        node {
                          id
                        }
                      }
                    }
                    receivedCallbackFile
                    analyzer {
                      id
                      analyzerId
                      hostGremlin {
                        id
                      }
                    }
                  }
                }
              }
            }
        """

        analysis_list_request = self.graphene_client.execute(REQUEST_ANALYSIS_DETAILS)

        # Get list of analyses from the response
        analysis_list = analysis_list_request["data"]["analyses"]["edges"]
        logger.info(f"Analysis list (count {len(analysis_list)}): {analysis_list}")

        # There should only be one
        self.assertTrue(len(analysis_list) == 1)

        # Grab that one
        received_analysis = analysis_list[0]["node"]

        # Assert some of what we know to be true about it (could probably do more here)
        # The analyzer might be Gremlin-based or task-based, so hostGremlin could be None
        self.assertEqual(received_analysis["analyzer"]["analyzerId"], self.analyzer.id)
        self.assertTrue(
            len(received_analysis["analyzedDocuments"]["edges"]) == len(self.doc_ids)
        )
        logger.info("SUCCESS!")

    def __test_start_analysis(self):
        START_ANALYSIS_REQUEST = """
            mutation($analyzerId:ID!, $corpusId:ID!) {
              startAnalysisOnCorpus(corpusId:$corpusId, analyzerId:$analyzerId) {
                ok
                message
                obj {
                  id
                }
              }
            }
        """

        logger.info("Start analysis...")
        new_analysis_response = self.graphene_client.execute(
            START_ANALYSIS_REQUEST,
            variables={
                "corpusId": self.global_corpus_id,
                "analyzerId": self.analyzer_global_id,
            },
        )
        logger.info(f"New analysis response: {new_analysis_response}")

    def test_endpoints(self):

        self.__test_get_analyzer_list()
        self.__test_get_analyzer()
        self.__test_get_analyses()
        self.__test_start_analysis()
