import asyncio
import gc
import json
import logging
from typing import Any

import factory.django
from celery.exceptions import Retry
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import close_old_connections, connection, connections, transaction
from django.db.models.signals import post_save
from django.test import TransactionTestCase, override_settings

from opencontractserver.analyzer.models import Analysis, Analyzer
from opencontractserver.annotations.models import (
    DOC_TYPE_LABEL,
    SPAN_LABEL,
    TOKEN_LABEL,
    Annotation,
)
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.shared.decorators import async_doc_analyzer_task
from opencontractserver.tests.fixtures import (
    SAMPLE_PAWLS_FILE_ONE_PATH,
    SAMPLE_PDF_FILE_ONE_PATH,
    SAMPLE_TXT_FILE_ONE_PATH,
)
from opencontractserver.types.dicts import TextSpan

User = get_user_model()
logger = logging.getLogger(__name__)


@override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
class AsyncDocAnalyzerTaskTestCase(TransactionTestCase):
    """
    Tests for the async_doc_analyzer_task decorator ensuring parity with the
    doc_analyzer_task test cases, but using async methods.
    Celery tasks are run synchronously (eagerly) for these tests.
    """

    @factory.django.mute_signals(post_save)
    def setUp(self):

        with transaction.atomic():

            # I hate that I can't fully explain why this is needed, but with these async tests
            # I regularly see issue where this Group isn't found in database in setUp.
            Group.objects.get_or_create(name=settings.DEFAULT_PERMISSIONS_GROUP)

            self.user = get_user_model().objects.create(username="async_tester")

            # Create all the test data
            self.corpus = Corpus.objects.create(
                title="Async Test Corpus", creator=self.user
            )

            self.async_analyzer = Analyzer.objects.create(
                id="test.analyzer.async",
                description="Async Analyzer Test",
                creator=self.user,
                task_name="test_async_analyzer",
            )

            # Create documents with properly encoded file content
            pdf_content = SAMPLE_PDF_FILE_ONE_PATH.read_bytes()
            txt_content = SAMPLE_TXT_FILE_ONE_PATH.read_bytes()
            pawls_content = SAMPLE_PAWLS_FILE_ONE_PATH.read_bytes()

            self.locked_pdf_doc = Document.objects.create(
                title="Test Locked Document",
                creator=self.user,
                backend_lock=True,
                pdf_file=SimpleUploadedFile("test.pdf", pdf_content),
                txt_extract_file=SimpleUploadedFile("test.txt", txt_content),
                pawls_parse_file=SimpleUploadedFile("test.json", pawls_content),
            )

            self.unlocked_pdf_doc = Document.objects.create(
                title="Test Unlocked Document",
                creator=self.user,
                backend_lock=False,
                pdf_file=SimpleUploadedFile("test2.pdf", pdf_content),
                txt_extract_file=SimpleUploadedFile("test2.txt", txt_content),
                pawls_parse_file=SimpleUploadedFile("test2.json", pawls_content),
            )

            self.txt_doc = Document.objects.create(
                title="Test TXT Document",
                creator=self.user,
                file_type="text/plain",
                txt_extract_file=SimpleUploadedFile("test3.txt", txt_content),
            )

            self.analysis = Analysis.objects.create(
                analyzer=self.async_analyzer,
                analyzed_corpus=self.corpus,
                creator=self.user,
            )

        logger.info(
            "[TEST CLASS SETUP] Created test documents: "
            f"{[self.locked_pdf_doc.id, self.unlocked_pdf_doc.id, self.txt_doc.id]}"
        )
        all_docs = Document.objects.all()
        logger.info(
            f"[TEST CLASS SETUP] All document IDs in test DB: {[d.id for d in all_docs]}"
        )

    @classmethod
    def tearDownClass(cls):
        """
        Ensure ALL database connections are closed before the test class is torn down.
        This runs once after all tests in the class complete.
        """
        # First close any old/stale connections
        close_old_connections()

        # Force close all remaining connections
        for conn in connections.all():
            conn.close()

        # Force terminate any remaining PostgreSQL connections to the test DB
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT pg_terminate_backend(pid)
                FROM pg_stat_activity
                WHERE datname = %s AND pid <> pg_backend_pid();
                """,
                [connection.settings_dict["NAME"]],
            )

        # Force garbage collection
        gc.collect()

        # Finally, call parent's teardown
        super().tearDownClass()

    @async_doc_analyzer_task(max_retries=10)
    async def sample_async_task(
        *args: Any, **kwargs: Any
    ) -> tuple[list[str], list[tuple[TextSpan, str]], list[dict[str, Any]], bool]:
        """
        Simple async task used to test basic doc and analysis retrieval,
        and returning the correct data shape to ensure no exceptions.
        """
        # Just a quick await to confirm it is genuinely async
        await asyncio.sleep(0.01)

        return (
            ["IMPORTANT_DOCUMENT_ASYNC"],
            [
                (
                    TextSpan(id="1", start=0, end=23, text="This is an async doc test"),
                    "ASYNC_LABEL",
                )
            ],
            [{"data": {"processed_async": True}}],
            True,
        )

    def test_async_doc_analyzer_task_backend_lock_retry_cycle(self) -> None:
        """
        Ensure that if the Document is locked, a Retry is raised as expected.
        """
        logger.info(f"[TEST] Number of documents in DB: {Document.objects.count()}")
        with self.assertRaises(Retry):
            self.sample_async_task.s(
                doc_id=self.locked_pdf_doc.id, analysis_id=self.analysis.id
            ).apply()

    def test_async_doc_analyzer_task_no_backend_lock(self) -> None:
        """
        Test a Document that is not locked processes immediately without Retry.
        """
        logger.info(f"[TEST] Number of documents in DB: {Document.objects.count()}")

        @async_doc_analyzer_task()
        async def test_async_no_lock(
            *args: Any, pdf_text_extract: str, **kwargs: Any
        ) -> tuple[list[str], list[tuple[TextSpan, str]], list[dict[str, Any]], bool]:
            await asyncio.sleep(0.01)
            return (
                ["TEST_DOC_ASYNC"],
                [
                    (
                        TextSpan(id="1", start=0, end=11, text="Exhibit 10."),
                        "TEXT_SPAN_ASYNC",
                    )
                ],
                [{"data": pdf_text_extract}],
                True,
            )

        # Unlock doc
        self.unlocked_pdf_doc.backend_lock = False
        self.unlocked_pdf_doc.save()

        result = (
            test_async_no_lock.si(
                doc_id=self.unlocked_pdf_doc.id, analysis_id=self.analysis.id
            )
            .apply()
            .get()
        )

        # Verify the structure of the returned data
        logger.info(f"test_async_doc_analyzer_task_no_backend_lock: {result[1][0][0]}")
        self.assertEqual(result[0], ["TEST_DOC_ASYNC"])
        self.assertEqual(len(result[1]), 1)
        self.assertEqual(result[1][0][0]["text"], "Exhibit 10.")  # The TextSpan text
        self.assertEqual(result[1][0][1], "TEXT_SPAN_ASYNC")
        self.assertIsInstance(result[2], list)
        self.assertTrue(result[3])

        # Verify created annotations
        doc_annotation = Annotation.objects.filter(
            document=self.unlocked_pdf_doc, annotation_type=DOC_TYPE_LABEL
        ).first()
        self.assertIsNotNone(doc_annotation)
        self.assertEqual(doc_annotation.annotation_label.text, "TEST_DOC_ASYNC")

        span_annotation = Annotation.objects.filter(
            document=self.unlocked_pdf_doc, annotation_type=TOKEN_LABEL
        ).first()
        self.assertIsNotNone(span_annotation)
        self.assertEqual(span_annotation.raw_text, "Exhibit 10.")

    def test_async_function_has_access_to_pdf_text(self) -> None:
        """
        Validates that the async task has access to the PDF text extract.
        """
        logger.info(f"[TEST] Number of documents in DB: {Document.objects.count()}")

        @async_doc_analyzer_task()
        async def test_pdf_text_received(
            *args: Any, pdf_text_extract: str, **kwargs: Any
        ) -> tuple[list[str], list[tuple[TextSpan, str]], list[dict[str, Any]], bool]:
            return [], [], [{"data": pdf_text_extract}], True

        expected_text = SAMPLE_TXT_FILE_ONE_PATH.read_text()
        processed_text = (
            test_pdf_text_received.si(
                doc_id=self.unlocked_pdf_doc.id, analysis_id=self.analysis.id
            )
            .apply()
            .get()[2][0]["data"]
        )

        self.assertIn(
            "Exhibit 10.1 Certain information identified by bracketed asterisks",
            processed_text,
        )
        self.assertEqual(
            processed_text.replace("\r\n", "\n").strip(),
            expected_text.replace("\r\n", "\n").strip(),
        )

    def test_async_function_has_access_to_txt_text(self) -> None:
        """
        Validates that an async task can read text from a text/plain Document.
        """
        logger.info(f"[TEST] Number of documents in DB: {Document.objects.count()}")

        @async_doc_analyzer_task()
        async def test_txt_text_received(
            *args: Any, pdf_text_extract: str, **kwargs: Any
        ) -> tuple[list[str], list[tuple[TextSpan, str]], list[dict[str, Any]], bool]:
            return [], [], [{"data": pdf_text_extract}], True

        expected_text = SAMPLE_TXT_FILE_ONE_PATH.read_text()
        processed_text = (
            test_txt_text_received.si(
                doc_id=self.txt_doc.id, analysis_id=self.analysis.id
            )
            .apply()
            .get()[2][0]["data"]
        )
        self.assertEqual(
            processed_text.replace("\r\n", "\n"), expected_text.replace("\r\n", "\n")
        )

    def test_async_function_has_access_to_txt_text_no_analysis(self) -> None:
        """
        Validate that the async decorator raises if `analysis_id` is missing.
        """
        logger.info(
            "[test_async_function_has_access_to_txt_text_no_analysis][TEST] "
            f"Number of documents in DB: {Document.objects.count()}"
        )

        @async_doc_analyzer_task()
        async def test_txt_text_received(
            *args: Any, pdf_text_extract: str, **kwargs: Any
        ) -> tuple[list[str], list[tuple[TextSpan, str]], list[dict[str, Any]], bool]:
            return [], [], [{"data": pdf_text_extract}], True

        with self.assertRaisesRegex(
            ValueError, r"analysis_id is required for doc_analyzer_task"
        ):
            test_txt_text_received.si(doc_id=self.txt_doc.id).apply().get()

    def test_async_function_has_access_to_txt_text_invalid_analysis(self) -> None:
        """
        Validate that an invalid analysis_id triggers a ValueError for nonexistent analysis.
        """
        logger.info(
            "[test_async_function_has_access_to_txt_text_invalid_analysis][TEST] "
            f"Number of documents in DB: {Document.objects.count()}"
        )

        @async_doc_analyzer_task()
        async def test_txt_text_received(
            *args: Any, pdf_text_extract: str, **kwargs: Any
        ) -> tuple[list[str], list[tuple[TextSpan, str]], list[dict[str, Any]], bool]:
            return [], [], [{"data": pdf_text_extract}], True

        with self.assertRaisesRegex(ValueError, r"Analysis with id -1 does not exist"):
            test_txt_text_received.si(
                doc_id=self.txt_doc.id, analysis_id=-1
            ).apply().get()

    def test_async_function_has_access_to_pawls_tokens(self) -> None:
        """
        Ensures that the async task can read and parse the PAWLS JSON data.
        """
        logger.info(
            "[test_async_function_has_access_to_pawls_tokens][TEST] "
            "Number of documents in DB: {Document.objects.count()}"
        )

        @async_doc_analyzer_task()
        async def test_pawls_received(
            *args: Any, pdf_pawls_extract: Any, **kwargs: Any
        ) -> tuple[list[str], list[tuple[TextSpan, str]], list[dict[str, Any]], bool]:
            return [], [], [{"data": pdf_pawls_extract}], True

        expected_tokens = json.loads(SAMPLE_PAWLS_FILE_ONE_PATH.read_text())
        received_tokens = (
            test_pawls_received.si(
                doc_id=self.unlocked_pdf_doc.id, analysis_id=self.analysis.id
            )
            .apply()
            .get()[2][0]["data"]
        )
        self.assertEqual(received_tokens, expected_tokens)

    def test_async_doc_analyzer_task_missing_doc_id(self) -> None:
        """
        Asserts correct error if doc_id is missing.
        """
        logger.info(
            "[test_async_doc_analyzer_task_missing_doc_id][TEST] Number of "
            f"documents in DB: {Document.objects.count()}"
        )
        with self.assertRaisesRegex(
            ValueError, "doc_id is required for doc_analyzer_task"
        ):
            self.sample_async_task.si().apply().get()

    def test_async_doc_analyzer_task_nonexistent_document(self) -> None:
        """
        Asserts that a ValueError is raised if the document ID doesn't exist.
        """
        logger.info(
            "[test_async_doc_analyzer_task_nonexistent_document][TEST] Number of "
            f"documents in DB: {Document.objects.count()}"
        )
        non_existent_id = self.unlocked_pdf_doc.id + 9999
        with self.assertRaisesRegex(
            ValueError, f"Document with id {non_existent_id} does not exist"
        ):
            self.sample_async_task.si(
                doc_id=non_existent_id, analysis_id=self.analysis.id
            ).apply().get()

    def test_async_doc_analyzer_task_nonexistent_corpus(self) -> None:
        """
        Asserts an error occurs when an invalid corpus_id is provided.
        """
        logger.info(
            "[test_async_doc_analyzer_task_nonexistent_corpus][TEST] Number of "
            f"documents in DB: {Document.objects.count()}"
        )
        non_existent_corpus_id = self.corpus.id + 9999
        with self.assertRaisesRegex(
            ValueError, f"Corpus with id {non_existent_corpus_id} does not exist"
        ):
            self.sample_async_task.si(
                doc_id=self.unlocked_pdf_doc.id,
                analysis_id=self.analysis.id,
                corpus_id=non_existent_corpus_id,
            ).apply().get()

    def test_async_doc_analyzer_task_invalid_return_value(self) -> None:
        """
        Asserts the async decorator enforces return type shape.
        """
        logger.info(
            "[test_async_doc_analyzer_task_invalid_return_value][TEST]"
            f" Number of documents in DB: {Document.objects.count()}"
        )
        self.unlocked_pdf_doc.backend_lock = False
        self.unlocked_pdf_doc.save()

        @async_doc_analyzer_task()
        async def invalid_return_value(*args: Any, **kwargs: Any) -> Any:
            return "Not the correct shape"

        with self.assertRaisesRegex(ValueError, "Function must return a tuple"):
            invalid_return_value.s(
                doc_id=self.unlocked_pdf_doc.id, analysis_id=self.analysis.id
            ).apply().get()

    def test_async_doc_analyzer_task_invalid_return_tuple_length(self) -> None:
        """
        Asserts that the decorator enforces exactly 4 items in the returned tuple.
        """
        logger.info(
            "[test_async_doc_analyzer_task_invalid_return_tuple_length][TEST] "
            f"Number of documents in DB: {Document.objects.count()}"
        )
        self.unlocked_pdf_doc.backend_lock = False
        self.unlocked_pdf_doc.save()

        @async_doc_analyzer_task()
        async def invalid_tuple_length(
            *args: Any, **kwargs: Any
        ) -> tuple[list[str], list[tuple[TextSpan, str]]]:
            return [], []

        with self.assertRaisesRegex(ValueError, "Function must return a tuple"):
            invalid_tuple_length.s(
                doc_id=self.unlocked_pdf_doc.id, analysis_id=self.analysis.id
            ).apply().get()

    def test_async_doc_analyzer_task_invalid_annotation(self) -> None:
        """
        Asserts that a non-list doc_label element triggers a ValueError.
        """
        logger.info(
            "[test_async_doc_analyzer_task_invalid_annotation][TEST]"
            f" Number of documents in DB: {Document.objects.count()}"
        )
        self.unlocked_pdf_doc.backend_lock = False
        self.unlocked_pdf_doc.save()

        @async_doc_analyzer_task()
        async def invalid_annotation(
            *args: Any, **kwargs: Any
        ) -> tuple[str, list[tuple[TextSpan, str]], list[dict[str, Any]], bool]:
            return "Invalid doc labels", [], [{"data": {}}], True

        with self.assertRaisesRegex(
            ValueError, "First element of the tuple must be a list of doc labels"
        ):
            invalid_annotation.s(
                doc_id=self.unlocked_pdf_doc.id, analysis_id=self.analysis.id
            ).apply().get()

    def test_async_doc_analyzer_task_invalid_text_annotations(self) -> None:
        """
        Asserts that a non-list second element triggers a ValueError.
        """
        logger.info(
            "[test_async_doc_analyzer_task_invalid_text_annotations][TEST] Number "
            f"of documents in DB: {Document.objects.count()}"
        )
        self.unlocked_pdf_doc.backend_lock = False
        self.unlocked_pdf_doc.save()

        @async_doc_analyzer_task(max_retries=10)
        async def invalid_text_annotations(
            *args: Any, **kwargs: Any
        ) -> tuple[list[str], str, list[dict[str, Any]], bool]:
            return [], "Not a list", [{"data": {}}], True

        with self.assertRaisesRegex(ValueError, "Second element of the tuple must be"):
            invalid_text_annotations.s(
                doc_id=self.unlocked_pdf_doc.id, analysis_id=self.analysis.id
            ).apply().get()

    def test_async_doc_analyzer_task_other_error_handling(self) -> None:
        """
        Ensures that unexpected exceptions return the fallback structure.
        """
        logger.info(
            "[test_async_doc_analyzer_task_other_error_handling][TEST] "
            f"Number of documents in DB: {Document.objects.count()}"
        )

        @async_doc_analyzer_task()
        async def fail_task(
            *args: Any, **kwargs: Any
        ) -> tuple[list[str], list[tuple[TextSpan, str]], list[dict[str, Any]], bool]:
            raise ZeroDivisionError("Oops! Another zero division in async land.")

        result = (
            fail_task.si(doc_id=self.unlocked_pdf_doc.id, analysis_id=self.analysis.id)
            .apply()
            .get()
        )

        self.assertEqual(result[0], [])
        self.assertEqual(result[1], [])
        self.assertEqual(len(result[2]), 1)
        self.assertIn("error", result[2][0]["data"])
        self.assertIn(
            "Oops! Another zero division in async land.", result[2][0]["data"]["error"]
        )
        self.assertFalse(result[3])

    def test_async_doc_analyzer_task_invalid_metadata(self) -> None:
        """
        Verifies that metadata must be a list of dicts with 'data' keys.
        """
        logger.info(
            "[test_async_doc_analyzer_task_invalid_metadata][TEST]"
            f" Number of documents in DB: {Document.objects.count()}"
        )
        self.unlocked_pdf_doc.backend_lock = False
        self.unlocked_pdf_doc.save()

        @async_doc_analyzer_task()
        async def invalid_metadata(
            *args: Any, **kwargs: Any
        ) -> tuple[list[str], list[tuple[TextSpan, str]], str, bool]:
            return [], [], "Not a valid list", True

        with self.assertRaisesRegex(
            ValueError,
            "Third element of the tuple must be a list of dictionaries with 'data' key",
        ):
            invalid_metadata.s(
                doc_id=self.unlocked_pdf_doc.id, analysis_id=self.analysis.id
            ).apply().get()

    def test_async_doc_analyzer_task_invalid_text_annotation_schema(self) -> None:
        """
        Verifies that text annotation schema must match a tuple of (TextSpan, str).
        """
        logger.info(
            "[test_async_doc_analyzer_task_invalid_text_annotation_schema][TEST]"
            f" Number of documents in DB: {Document.objects.count()}"
        )
        self.unlocked_pdf_doc.backend_lock = False
        self.unlocked_pdf_doc.save()

        @async_doc_analyzer_task()
        async def invalid_text_annotation_schema(
            *args: Any, **kwargs: Any
        ) -> tuple[list[str], list[dict], list[dict[str, Any]], bool]:
            return [], [{"not_span": "Nope"}], [], True

        with self.assertRaisesRegex(
            ValueError, "Second element of the tuple must be a list of"
        ):
            invalid_text_annotation_schema.s(
                doc_id=self.unlocked_pdf_doc.id, analysis_id=self.analysis.id
            ).apply().get()

    def test_async_doc_analyzer_task_missing_data_key(self) -> None:
        """
        Verifies that each metadata item must contain a 'data' key.
        """
        logger.info(
            "[test_async_doc_analyzer_task_missing_data_key][TEST] "
            f"Number of documents in DB: {Document.objects.count()}"
        )
        self.unlocked_pdf_doc.backend_lock = False
        self.unlocked_pdf_doc.save()

        @async_doc_analyzer_task()
        async def missing_data_key(
            *args: Any, **kwargs: Any
        ) -> tuple[list[str], list[tuple[TextSpan, str]], list[dict], bool]:
            return [], [], [{"not_data": {}}], True

        with self.assertRaisesRegex(
            ValueError,
            "Third element of the tuple must be a list of dictionaries with 'data' key",
        ):
            missing_data_key.s(
                doc_id=self.unlocked_pdf_doc.id, analysis_id=self.analysis.id
            ).apply().get()

    def test_async_doc_analyzer_task_no_analysis_id(self) -> None:
        """
        Verifies we fail if analysis_id is not provided.
        """
        logger.info(
            "[test_async_doc_analyzer_task_no_analysis_id][TEST] Number "
            f"of documents in DB: {Document.objects.count()}"
        )

        @async_doc_analyzer_task()
        async def no_analysis(
            *args: Any, **kwargs: Any
        ) -> tuple[list[str], list[tuple[TextSpan, str]], list[dict[str, Any]], bool]:
            return [], [], [{"data": {}}], True

        with self.assertRaisesRegex(
            ValueError, "analysis_id is required for doc_analyzer_task"
        ):
            no_analysis.si(doc_id=self.unlocked_pdf_doc.id).apply().get()

    def test_async_doc_analyzer_task_non_boolean_task_pass(self) -> None:
        """
        Verifies the final boolean in the 4-tuple must be a boolean, not a string or anything else.
        """
        logger.info(
            "[test_async_doc_analyzer_task_non_boolean_task_pass][TEST]"
            f" Number of documents in DB: {Document.objects.count()}"
        )

        @async_doc_analyzer_task()
        async def non_boolean_pass(
            *args: Any, **kwargs: Any
        ) -> tuple[list[str], list[tuple[TextSpan, str]], list[dict[str, Any]], Any]:
            return [], [], [{"data": {}}], "not a boolean"

        with self.assertRaisesRegex(
            ValueError, "Fourth element of the return value must be true/false"
        ):
            non_boolean_pass.si(
                doc_id=self.unlocked_pdf_doc.id, analysis_id=self.analysis.id
            ).apply().get()

    def test_async_doc_analyzer_task_txt_file_annotations(self) -> None:
        """
        Confirms that for a text/plain Document, span annotations are recorded properly.
        """
        logger.info(
            "[test_async_doc_analyzer_task_txt_file_annotations][TEST] Number "
            f"of documents in DB: {Document.objects.count()}"
        )

        @async_doc_analyzer_task()
        async def txt_annotations(
            *args: Any, **kwargs: Any
        ) -> tuple[list[str], list[tuple[TextSpan, str]], list[dict[str, Any]], bool]:
            return (
                ["TEXT_DOC_ASYNC"],
                [
                    (
                        TextSpan(id="1", start=0, end=12, text="Async Span!"),
                        "TEXT_SPAN_ASYNC",
                    )
                ],
                [{"data": {"processed_async": True}}],
                True,
            )

        task = txt_annotations.si(
            doc_id=self.txt_doc.id, analysis_id=self.analysis.id
        ).apply()
        result = task.get()

        self.assertEqual(result[0], ["TEXT_DOC_ASYNC"])
        self.assertEqual(len(result[1]), 1)
        self.assertTrue(result[3])

        # Check created annotations
        annotations = Annotation.objects.filter(document=self.txt_doc)
        self.assertEqual(annotations.count(), 2)  # doc-level + span-level annotation

        span_annotation = annotations.filter(annotation_type=SPAN_LABEL).first()
        self.assertEqual(span_annotation.raw_text, "Async Span!")
        self.assertDictEqual(span_annotation.json, {"start": 0, "end": 12})
        self.assertEqual(span_annotation.annotation_label.text, "TEXT_SPAN_ASYNC")
