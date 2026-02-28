import json
import logging

from celery.exceptions import Retry
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from opencontractserver.analyzer.models import Analysis, Analyzer
from opencontractserver.annotations.models import (
    DOC_TYPE_LABEL,
    SPAN_LABEL,
    TOKEN_LABEL,
    Annotation,
)
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.shared.decorators import doc_analyzer_task
from opencontractserver.tests.fixtures import (
    SAMPLE_PAWLS_FILE_ONE_PATH,
    SAMPLE_PDF_FILE_ONE_PATH,
    SAMPLE_TXT_FILE_ONE_PATH,
)
from opencontractserver.types.dicts import TextSpan

User = get_user_model()
logger = logging.getLogger(__name__)


@doc_analyzer_task(max_retries=10)
def sample_task(*args, **kwargs):
    return (
        ["IMPORTANT_DOCUMENT"],
        [
            (
                TextSpan(id="1", start=0, end=29, text="This is a sample PDF document"),
                "IMPORTANT!",
            )
        ],
        [{"data": {"processed": True}}],
        True,
    )


dummy_pawls_bytes = (
    b'[{"page": {"width": 612, "height": 792, "index": 0}, "tokens": [{"x": 72, "y": 72, "width": 50, '
    b'"height": 12, "text": "This"}, {"x": 130, "y": 72, "width": 20, "height": 12, "text": "is"}, '
    b'{"x": 158, "y": 72, "width": 40, "height": 12, "text": "a"}, {"x": 206, "y": 72, "width": 60, '
    b'"height": 12, "text": "sample"}, {"x": 274, "y": 72, "width": 50, "height": 12, "text": "PDF"}, '
    b'{"x": 332, "y": 72, "width": 80, "height": 12, "text": "document."}]}]'
)
dummy_pawls_data = json.loads(dummy_pawls_bytes)


class DocAnalyzerTaskTestCase(TestCase):
    def setUp(self):
        super().setUp()
        self.user = get_user_model().objects.create(username="test")
        self.corpus = Corpus.objects.create(title="Test Corpus", creator=self.user)

        # Create analyzer with required fields
        self.task_name_analyzer = Analyzer.objects.create(
            id="test.analyzer.1",  # Required primary key
            description="Test description",
            creator=self.user,
            task_name="test_analyzer",  # Either task_name or host_gremlin must be set
        )

        # Create a document with properly encoded file content
        pdf_content = SAMPLE_PDF_FILE_ONE_PATH.read_bytes()
        txt_content = SAMPLE_TXT_FILE_ONE_PATH.read_bytes()
        pawls_content = SAMPLE_PAWLS_FILE_ONE_PATH.read_bytes()

        self.document = Document.objects.create(
            title="Test Document",
            creator=self.user,
            backend_lock=True,
            pdf_file=SimpleUploadedFile("test.pdf", pdf_content),
            txt_extract_file=SimpleUploadedFile("test.txt", txt_content),
            pawls_parse_file=SimpleUploadedFile("test.json", pawls_content),
        )

        self.unlocked_document = Document.objects.create(
            title="Test Document Unlocked",
            creator=self.user,
            backend_lock=False,
            pdf_file=SimpleUploadedFile("test2.pdf", pdf_content),
            txt_extract_file=SimpleUploadedFile("test2.txt", txt_content),
            pawls_parse_file=SimpleUploadedFile("test2.json", pawls_content),
        )

        self.txt_document = Document.objects.create(
            title="Test TXT Document",
            creator=self.user,
            file_type="text/plain",
            txt_extract_file=SimpleUploadedFile("test3.txt", txt_content),
        )

        self.analysis = Analysis.objects.create(
            analyzer=self.task_name_analyzer,
            analyzed_corpus=self.corpus,
            creator=self.user,
        )

    def test_doc_analyzer_task_backend_lock_retry_cycle(self):
        with self.assertRaises(Retry):
            sample_task.s(doc_id=self.document.id, analysis_id=self.analysis.id).apply()

    def test_doc_analyzer_task_no_backend_lock(self):
        @doc_analyzer_task()
        def test_no_lock(*args, pdf_text_extract, **kwargs):
            return (
                ["TEST_DOC"],
                [(TextSpan(id="1", start=0, end=10, text="Exhibit 10"), "TEXT_SPAN")],
                [{"data": pdf_text_extract}],
                True,
            )

        # Ensure document is not locked
        self.unlocked_document.backend_lock = False
        self.unlocked_document.save()

        test_no_lock.si(
            doc_id=self.unlocked_document.id, analysis_id=self.analysis.id
        ).apply().get()

        # Verify annotations were created
        annotations = Annotation.objects.filter(
            document=self.unlocked_document, annotation_type=DOC_TYPE_LABEL
        )

        # Verify doc label annotation exists and has correct label
        doc_annotation = annotations.first()
        self.assertIsNotNone(doc_annotation, "Doc type annotation was not created")
        self.assertEqual(doc_annotation.annotation_label.text, "TEST_DOC")

        # Verify span annotation
        span_annotation = Annotation.objects.filter(annotation_type=TOKEN_LABEL).first()
        self.assertEqual(span_annotation.raw_text, "Exhibit 10")
        self.assertIn("0", span_annotation.json)
        self.assertIn("bounds", span_annotation.json["0"])
        self.assertIn("rawText", span_annotation.json["0"])
        self.assertIn("tokensJsons", span_annotation.json["0"])
        self.assertEqual(span_annotation.annotation_label.text, "TEXT_SPAN")

    def test_function_has_access_to_pdf_text(self):
        @doc_analyzer_task()
        def test_pdf_text_received(*args, pdf_text_extract, **kwargs):
            return [], [], [{"data": pdf_text_extract}], True

        expected_text = SAMPLE_TXT_FILE_ONE_PATH.read_text()
        processed_text = (
            test_pdf_text_received.si(
                doc_id=self.unlocked_document.id, analysis_id=self.analysis.id
            )
            .apply()
            .get()[2][0]["data"]
        )

        # Normalize line endings before comparison
        self.assertEqual(
            processed_text.replace("\r\n", "\n").strip(),
            expected_text.replace("\r\n", "\n").strip(),
        )

    def test_function_has_access_to_txt_text(self):
        @doc_analyzer_task()
        def test_txt_text_received(*args, pdf_text_extract, **kwargs):
            return [], [], [{"data": pdf_text_extract}], True

        expected_text = SAMPLE_TXT_FILE_ONE_PATH.read_text()
        processed_text = (
            test_txt_text_received.si(
                doc_id=self.txt_document.id, analysis_id=self.analysis.id
            )
            .apply()
            .get()[2][0]["data"]
        )
        # Normalize line endings before comparison
        self.assertEqual(
            processed_text.replace("\r\n", "\n"), expected_text.replace("\r\n", "\n")
        )

    def test_function_has_access_to_txt_text_no_analysis(self):
        @doc_analyzer_task()
        def test_txt_text_received(*args, pdf_text_extract, **kwargs):
            return [], [], [{"data": pdf_text_extract}], True  # noqa

        with self.assertRaisesRegex(
            ValueError, r"analysis_id is required for doc_analyzer_task"
        ):
            test_txt_text_received.si(doc_id=self.txt_document.id).apply().get()

    def test_function_has_access_to_txt_text_invalid_analysis(self):
        @doc_analyzer_task()
        def test_txt_text_received(*args, pdf_text_extract, **kwargs):
            return [], [], [{"data": pdf_text_extract}], True  # noqa

        with self.assertRaisesRegex(ValueError, r"Analysis with id -1 does not exist"):
            test_txt_text_received.si(
                doc_id=self.txt_document.id, analysis_id=-1
            ).apply().get()

    def test_function_has_access_to_pawls_tokens(self):
        @doc_analyzer_task()
        def test_pdf_tokens_received(*args, pdf_pawls_extract, **kwargs):
            return [], [], [{"data": pdf_pawls_extract}], True

        received_tokens = (
            test_pdf_tokens_received.si(
                doc_id=self.unlocked_document.id, analysis_id=self.analysis.id
            )
            .apply()
            .get()[2][0]["data"]
        )

        # Load expected data from fixture
        expected_tokens = json.loads(SAMPLE_PAWLS_FILE_ONE_PATH.read_text())
        self.assertEqual(received_tokens, expected_tokens)

    def test_doc_analyzer_task_missing_doc_id(self):
        with self.assertRaisesRegex(
            ValueError, "doc_id is required for doc_analyzer_task"
        ):
            sample_task.si().apply().get()

    def test_doc_analyzer_task_nonexistent_document(self):
        non_existent_id = self.document.id + 1000  # Ensure this ID doesn't exist
        with self.assertRaisesRegex(
            ValueError, f"Document with id {non_existent_id} does not exist"
        ):
            sample_task.si(
                doc_id=non_existent_id, analysis_id=self.analysis.id
            ).apply().get()

    def test_doc_analyzer_task_nonexistent_corpus(self):
        non_existent_corpus_id = self.corpus.id + 1000  # Ensure this ID doesn't exist
        with self.assertRaisesRegex(
            ValueError, f"Corpus with id {non_existent_corpus_id} does not exist"
        ):
            sample_task.si(
                doc_id=self.document.id,
                analysis_id=self.analysis.id,
                corpus_id=non_existent_corpus_id,
            ).apply().get()

    def test_doc_analyzer_task_invalid_return_value(self):
        self.document.backend_lock = False
        self.document.save()

        @doc_analyzer_task()
        def invalid_return_task(*args, **kwargs):
            return "Invalid return value"

        with self.assertRaisesRegex(ValueError, "Function must return a tuple"):
            invalid_return_task.s(
                doc_id=self.document.id, analysis_id=self.analysis.id
            ).apply().get()

    def test_doc_analyzer_task_invalid_return_tuple_length(self):
        self.document.backend_lock = False
        self.document.save()

        @doc_analyzer_task()
        def invalid_return_task(*args, **kwargs):
            return [], []

        with self.assertRaisesRegex(ValueError, "Function must return a tuple"):
            invalid_return_task.s(
                doc_id=self.document.id, analysis_id=self.analysis.id
            ).apply().get()

    def test_doc_analyzer_task_invalid_annotation(self):
        self.document.backend_lock = False
        self.document.save()

        @doc_analyzer_task()
        def invalid_annotation_task(*args, **kwargs):
            return "Not a list", [], [{"data": {}}], True

        with self.assertRaisesRegex(
            ValueError, "First element of the tuple must be a list of doc labels"
        ):
            invalid_annotation_task.si(
                doc_id=self.document.id, analysis_id=self.analysis.id
            ).apply().get()

    def test_doc_analyzer_task_invalid_text_annotations(self):
        self.document.backend_lock = False
        self.document.save()

        @doc_analyzer_task(max_retries=10)
        def invalid_text_annotations_task(*args, **kwargs):
            return [], "Not a list", [{"data": {}}], True

        with self.assertRaisesRegex(ValueError, "Second element of the tuple must be"):
            invalid_text_annotations_task.si(
                doc_id=self.document.id, analysis_id=self.analysis.id
            ).apply().get()

    def test_other_error_handling(self):
        @doc_analyzer_task()
        def other_error_task(*args, **kwargs):
            raise ZeroDivisionError(
                "Oops! Someone divided by zero in a parallel universe."
            )

        result = (
            other_error_task.si(
                doc_id=self.unlocked_document.id, analysis_id=self.analysis.id
            )
            .apply()
            .get()
        )

        self.assertEqual(result[0], [])  # Empty list for doc labels
        self.assertEqual(result[1], [])  # Empty list for text annotations
        self.assertEqual(len(result[2]), 1)  # One metadata item
        self.assertIn("data", result[2][0])
        self.assertIn("error", result[2][0]["data"])
        self.assertIn(
            "Oops! Someone divided by zero in a parallel universe.",
            result[2][0]["data"]["error"],
        )
        self.assertFalse(result[3])  # Last element should be False

    def test_doc_analyzer_task_invalid_metadata(self):
        self.document.backend_lock = False
        self.document.save()

        @doc_analyzer_task()
        def invalid_metadata_task(*args, **kwargs):
            return [], [], "Not a list", True

        with self.assertRaisesRegex(
            ValueError,
            "Third element of the tuple must be a list of dictionaries with 'data' key",
        ):
            invalid_metadata_task.si(
                doc_id=self.document.id, analysis_id=self.analysis.id
            ).apply().get()

    def test_doc_analyzer_task_invalid_text_annotation_schema(self):
        self.document.backend_lock = False
        self.document.save()

        @doc_analyzer_task()
        def invalid_text_annotation_schema_task(*args, **kwargs):
            return [], [{"random_key": "I am lazy", "wishlist?": "RTFD"}], [], True

        with self.assertRaisesRegex(
            ValueError, r"Second element must be a list of \(TextSpan, str\) tuples"
        ):
            invalid_text_annotation_schema_task.si(
                doc_id=self.document.id, analysis_id=self.analysis.id
            ).apply().get()

    def test_doc_analyzer_task_missing_data_key(self):
        self.document.backend_lock = False
        self.document.save()

        @doc_analyzer_task()
        def missing_data_key_task(*args, **kwargs):
            return [], [], [{"not_data": {}}], True

        with self.assertRaisesRegex(
            ValueError,
            "Third element of the tuple must be a list of dictionaries with "
            "'data' key",
        ):
            missing_data_key_task.si(
                doc_id=self.document.id, analysis_id=self.analysis.id
            ).apply().get()

    def test_doc_analyzer_task_no_analysis_id(self):
        @doc_analyzer_task()
        def test_no_analysis(*args, **kwargs):
            return [], [], [{"data": {}}], True

        with self.assertRaisesRegex(
            ValueError, "analysis_id is required for doc_analyzer_task"
        ):
            test_no_analysis.si(doc_id=self.unlocked_document.id).apply().get()

    def test_doc_analyzer_task_non_boolean_task_pass(self):
        @doc_analyzer_task()
        def test_invalid_task_pass(*args, **kwargs):
            return [], [], [{"data": {}}], "not a boolean"

        with self.assertRaisesRegex(
            ValueError, "Fourth element of the return value must be true/false"
        ):
            test_invalid_task_pass.si(
                doc_id=self.unlocked_document.id, analysis_id=self.analysis.id
            ).apply().get()

    def test_doc_analyzer_task_txt_file_annotations(self):
        @doc_analyzer_task()
        def test_txt_annotations(*args, **kwargs):
            return (
                ["TEXT_DOC"],
                [(TextSpan(id="1", start=0, end=10, text="Exhibit 10"), "TEXT_SPAN")],
                [{"data": {"processed": True}}],
                True,
            )

        task = test_txt_annotations.si(
            doc_id=self.txt_document.id, analysis_id=self.analysis.id
        ).apply()
        result = task.get()

        # Verify results
        self.assertEqual(result[0], ["TEXT_DOC"])
        self.assertEqual(len(result[1]), 1)
        self.assertEqual(result[2], [{"data": {"processed": True}}])
        self.assertTrue(result[3])

        # Verify annotations were created correctly
        annotations = Annotation.objects.filter(document=self.txt_document)
        self.assertEqual(annotations.count(), 2)  # 1 doc type + 1 span annotation

        span_annotation = annotations.filter(annotation_type=SPAN_LABEL).first()
        self.assertEqual(span_annotation.raw_text, "Exhibit 10")
        self.assertEqual(span_annotation.json, {"start": 0, "end": 10})
        self.assertEqual(span_annotation.annotation_label.text, "TEXT_SPAN")
