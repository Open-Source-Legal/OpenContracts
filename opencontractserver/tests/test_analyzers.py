# Create your tests here.
import json
import logging

import factory.django
import responses
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models.signals import post_save
from django.test import TestCase
from rest_framework.test import APIClient

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
    SAMPLE_GREMLIN_OUTPUT_FOR_PUBLIC_DOCS,
    SAMPLE_PDF_FILE_ONE_PATH,
    SAMPLE_PDF_FILE_TWO_PATH,
    create_mock_submission_response,
    generate_random_analyzer_return_values,
)

logger = logging.getLogger(__name__)

User = get_user_model()


class TestOpenContractsAnalyzers(TestCase):
    @factory.django.mute_signals(post_save)
    def setUp(self):

        Group.objects.get_or_create(name=settings.DEFAULT_PERMISSIONS_GROUP)

        # We're turning off signals so we can more easily test the async gremlin
        # install logic without having to patch into the signal handlers.
        # Disconnect all signals for GremlinEngine

        # We need a user to tie everything back to.
        with transaction.atomic():
            self.user = User.objects.create_user(username="bob", password="12345678")

        # Let's load our mock gremlin details
        self.gremlin_manifest = json.loads(
            SAMPLE_GREMLIN_ENGINE_MANIFEST_PATH.open("r").read()
        )
        self.gremlin_url = "http://localhost:8000"
        self.gremlin = GremlinEngine.objects.create(
            url=self.gremlin_url, creator=self.user
        )

        # Now, we want to create a corpus that we can send to Gremlin for analysis...
        # and we're going to do it using docs we can mock responses for.
        self.corpus = Corpus.objects.create(
            title="Test Analysis Corpus", creator=self.user, backend_lock=False
        )

        sample_pdfs = [SAMPLE_PDF_FILE_ONE_PATH, SAMPLE_PDF_FILE_TWO_PATH]

        for index, pdf_path in enumerate(sample_pdfs):
            with pdf_path.open("rb") as pdf_file:
                pdf_contents = ContentFile(
                    pdf_file.read(), name=f"test_doc_{index}.pdf"
                )
                Document.objects.create(
                    title=f"TestDoc{index}",
                    description="Sample PDF Document",
                    pdf_file=pdf_contents,
                    creator=self.user,
                    page_count=1,
                )
        logger.info(f"{len(sample_pdfs)} pdfs loaded for analysis")

    @factory.django.mute_signals(post_save)
    def test_analyzer_constraints(self):

        # Test that we can't create an Analyzer with both host_gremlin and task_name
        with self.assertRaises(ValidationError):
            invalid_analyzer = Analyzer(
                description="Invalid Analyzer",
                host_gremlin=self.gremlin,
                task_name="some.task.name",
                creator=self.user,
                manifest={},
            )
            invalid_analyzer.full_clean()

        # Test that we can't create an Analyzer with neither host_gremlin nor task_name
        with self.assertRaises(ValidationError):
            invalid_analyzer = Analyzer(
                description="Invalid Analyzer", creator=self.user, manifest={}
            )
            invalid_analyzer.full_clean()

        # Test that we can create an Analyzer with only host_gremlin
        Analyzer(
            description="Valid Analyzer with Gremlin",
            host_gremlin=self.gremlin,
            creator=self.user,
            manifest={},
        )

        # Test that we can create an Analyzer with only task_name
        Analyzer(
            description="Valid Analyzer with Task",
            task_name="opencontractserver.tasks.data_extract_tasks.doc_extract_query_task",
            creator=self.user,
            manifest={},
        )

    @factory.django.mute_signals(post_save)
    @responses.activate
    def __test_install_gremlin(self):

        # The timing tracking vars should be None initially...
        self.assertIsNone(self.gremlin.install_started)
        self.assertIsNone(self.gremlin.install_completed)

        # Get manifest from our mock Gremlin
        with responses.RequestsMock() as rsps:
            rsps.add(
                responses.GET,
                self.gremlin.url + "/api/analyzers",
                json=self.gremlin_manifest,
                status=200,
            )
            analyzer_manifests = (
                request_gremlin_manifest.si(gremlin_id=self.gremlin.id).apply().get()
            )

        # Need to refresh the in-memory obj from db
        self.gremlin.refresh_from_db()

        # Upon requesting the manifest... install_started should have value
        self.assertIsNotNone(self.gremlin.install_started)
        self.assertIsNone(self.gremlin.install_completed)

        # We should have manifests
        self.assertIsNotNone(analyzer_manifests)

        # Install mock data
        install_analyzer_task.si(
            analyzer_manifests=analyzer_manifests, gremlin_id=self.gremlin.id
        ).apply().get()

        # Need to refresh the in-memory obj from db
        self.gremlin.refresh_from_db()

        # Upon completing install, the timing fields should not be None
        self.assertIsNotNone(self.gremlin.install_completed)
        self.assertIsNotNone(self.gremlin.install_started)
        # The fixture contains 1 analyzer, but auto-created analyzers may also exist
        # Just verify at least the expected analyzer was created
        self.assertGreaterEqual(Analyzer.objects.all().count(), 1)

    def __test_submit_analysis(self):

        analyzer = Analyzer.objects.all()[0]

        # It is possible to use responses with regex url pattern (Though that's not necessary... yet). Keep this for
        # later:
        # https://stackoverflow.com/questions/62452119/python-responses-library-prepends-part-of-the-url-to-the-
        # request-params
        with responses.RequestsMock() as rsps:
            rsps.add(
                responses.POST,
                f"{self.gremlin.url}/api/jobs/submit",
                body=json.dumps(create_mock_submission_response(analyzer.id)),
                status=200,
                content_type="application/json",
            )

            with transaction.atomic():
                analysis = Analysis.objects.create(
                    analyzer_id=analyzer.id,
                    analyzed_corpus_id=self.corpus.id,
                    creator=self.user,
                )

            analysis_result = (
                start_analysis.si(
                    analysis_id=analysis.id,
                )
                .apply()
                .get()
            )

        self.assertTrue(analysis_result)

    def __test_receive_callback_with_gremlin_results(self):
        # First let's get our analysis... there should only be one
        analyses = Analysis.objects.all()
        self.assertTrue(analyses.count() == 1)
        analysis_obj = analyses[0]

        # Get the mock data from fixtures
        mock_gremlin_response_data = json.loads(
            SAMPLE_GREMLIN_OUTPUT_FOR_PUBLIC_DOCS.open().read()
        )

        # SAMPLE_GREMLIN_OUTPUT_FOR_PUBLIC_DOCS
        # When a Gremlin job completes, it's going to send the results to the callback
        # WITH the one-time authorization code Open Contracts provided.
        # The DB only stores the SHA-256 hash, so we mint and use the
        # plaintext here to mirror what ``submit_corpus_documents_to_analyzer``
        # would have sent to the gremlin in production.
        # rotate_callback_token() auto-saves because analysis_obj has a pk.
        plaintext_token = analysis_obj.rotate_callback_token()
        authenticated_client = APIClient()
        authenticated_client.credentials(HTTP_CALLBACK_TOKEN=plaintext_token)

        response = authenticated_client.post(
            f"{settings.CALLBACK_ROOT_URL_FOR_ANALYZER}/analysis/{analysis_obj.id}/complete",
            mock_gremlin_response_data,
            format="json",
        )
        logger.info(
            f"__test_receive_callback_with_gremlin_results - response - {response.content}"
        )

    def __test_analysis_import_logic(self):

        analyzer = Analyzer.objects.all()[0]

        # I'm not sure that there's a way to wait for celery async tasks to complete as part of the test...
        # so let's run the login inside the async task synchronously, so we can test it
        with responses.RequestsMock() as rsps:
            rsps.add(
                responses.POST,
                f"{self.gremlin.url}/api/jobs/submit",
                body=json.dumps(create_mock_submission_response(analyzer.id)),
                status=200,
                content_type="application/json",
            )

            with transaction.atomic():
                analysis = Analysis.objects.create(
                    analyzer_id=analyzer.id,
                    analyzed_corpus_id=self.corpus.id,
                    creator=self.user,
                )

            analysis_started = (
                start_analysis.si(
                    analysis_id=analysis.id,
                )
                .apply()
                .get()
            )

        self.assertTrue(analysis_started)

        # Here's where we deviate from the callback test... we actually just manually
        # call the import_analysis task *synchronously*
        doc_ids = list(Document.objects.all().values_list("id", flat=True))
        logger.info(f"Doc_ids is {doc_ids}")
        mock_gremlin_response_data = generate_random_analyzer_return_values(
            doc_ids=doc_ids
        )

        analysis_result = (
            import_analysis.si(
                creator_id=self.user.id,
                analysis_id=analysis.id,
                analysis_results=mock_gremlin_response_data,
            )
            .apply()
            .get()
        )

        self.assertTrue(analysis_result)

        # Rough and ready test of imports - count database objs
        annotation_count = Annotation.objects.all().count()
        self.assertTrue(annotation_count > 0)

        label_set_count = LabelSet.objects.all().count()
        self.assertEqual(label_set_count, 1)

        label_count = AnnotationLabel.objects.all().count()
        self.assertEqual(label_count, 18)

    def test_analyzerz(self):
        self.__test_install_gremlin()
        self.__test_submit_analysis()
        self.__test_receive_callback_with_gremlin_results()
        self.__test_analysis_import_logic()
