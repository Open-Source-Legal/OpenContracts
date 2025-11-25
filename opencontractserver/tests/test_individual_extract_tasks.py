"""
Tests to synchronously invoke and verify the doc_extract_query_task Celery task
using TransactionTestCase, ensuring that the Extract models and related objects
(Fieldset, Column, Datacell) are set up correctly.
"""

import logging

import vcr
from django.contrib.auth import get_user_model
from django.test import TransactionTestCase

from opencontractserver.documents.models import DocumentAnalysisRow
from opencontractserver.extracts.models import Column, Datacell, Extract, Fieldset
from opencontractserver.tasks.data_extract_tasks import (
    doc_extract_query_task,
)
from opencontractserver.tests.base import BaseFixtureTestCase

vcr_log = logging.getLogger("vcr")
vcr_log.setLevel(logging.WARNING)

User = get_user_model()


class TestDocExtractQueryTask(TransactionTestCase):
    """
    Tests doc_extract_query_task by creating an Extract along with the
    Datacell, Column, and Fieldset models, then invoking the Celery task
    synchronously to confirm its behavior.
    """

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(username="testuser", password="testpass")

        # Create corpus
        from opencontractserver.corpuses.models import Corpus

        self.corpus = Corpus.objects.create(title="Test Corpus", creator=self.user)

        # Create document
        from opencontractserver.documents.models import Document

        self.doc = Document.objects.create(
            title="Test Document", creator=self.user, file_type="text/plain"
        )
        self.corpus.add_document(document=self.doc, user=self.user)

    @vcr.use_cassette(
        "fixtures/vcr_cassettes/test_doc_extract_query_task_synchronously.yaml",
        record_mode="once",
        filter_headers=["authorization"],
    )
    def test_doc_extract_query_task_synchronously(self) -> None:
        """
        Ensures that doc_extract_query_task can be called with a valid Datacell (and
        related models) synchronously. The resulting output is asserted for
        correctness and to confirm synchronous operation.
        """
        # Create a Fieldset
        fieldset: Fieldset = Fieldset.objects.create(
            name="Test Fieldset",
            description="Used to group columns for extraction.",
            creator=self.user,
        )

        # Create a Column (which references the Fieldset)
        column: Column = Column.objects.create(
            name="Test Column",
            fieldset=fieldset,
            output_type="str",
            query="What is the title of this document?",
            match_text=None,
            must_contain_text=None,
            creator=self.user,
        )

        # Create an Extract (which references a Corpus and Fieldset)
        extract: Extract = Extract.objects.create(
            corpus=self.corpus,
            name="Test Extract",
            fieldset=fieldset,
            creator=self.user,
        )

        # Create a Datacell referencing our Document, Extract, and Column
        datacell: Datacell = Datacell.objects.create(
            extract=extract,
            column=column,
            document=self.doc,
            data_definition="Test definition for extraction",
            creator=self.user,
        )

        try:
            # Invoke the Celery task synchronously
            doc_extract_query_task.si(
                cell_id=datacell.id, similarity_top_k=3, max_token_length=1000
            ).apply()

            # Refresh datacell from database
            datacell.refresh_from_db()
            result = datacell.data

            # Assert the result is valid
            self.assertIsNotNone(
                result, "Expected a non-None result from doc_extract_query_task."
            )

            # Optionally, assert structure/contents of 'result' as appropriate for your logic
            self.assertIn("data", result, "Expected 'data' key in result")

            print(f"Synchronous doc_extract_query_task result: {result}")
        except Exception as e:
            logging.error(
                f"Exception in test_doc_extract_query_task_synchronously: {e}"
            )
            import traceback

            logging.error(traceback.format_exc())
            raise


class TestDocExtractQueryTaskDirect(BaseFixtureTestCase):
    """
    A test class that uses the same fixture setup as our orchestrator-based test
    but calls the doc_extract_query_task task directly on newly created Datacells.
    """

    def setUp(self) -> None:
        """
        Sets up test data similarly to ExtractsTaskTestCase, using the same test fixtures
        to ensure we're able to test doc_extract_query_task in isolation with identical
        environment conditions.
        """
        super().setUp()

        logging.info("Setting up TestDocExtractQueryTaskDirect data.")

        self.fieldset: Fieldset = Fieldset.objects.create(
            name="TestFieldsetForDirectTask",
            description="Test description for direct extraction task invocation",
            creator=self.user,
        )

        # Create first column with a designated task name
        self.column1: Column = Column.objects.create(
            fieldset=self.fieldset,
            query="What is the name of this document?",
            output_type="str",
            creator=self.user,
            task_name="opencontractserver.tasks.data_extract_tasks.doc_extract_query_task",
        )

        # Create a second column (just to match the multi-column scenario)
        self.column2: Column = Column.objects.create(
            fieldset=self.fieldset,
            query="Provide a list of the defined terms",
            match_text="A defined term is defined as a term that is defined...",
            output_type="str",
            creator=self.user,
        )

        # Create the Extract that references our Fieldset
        self.extract: Extract = Extract.objects.create(
            name="TestExtractDirectTask",
            fieldset=self.fieldset,
            creator=self.user,
        )

        # Add documents (from BaseFixtureTestCase) to the Corpus (required for new agent API)
        self.corpus.add_document(document=self.doc, user=self.user)
        self.corpus.add_document(document=self.doc2, user=self.user)
        self.corpus.add_document(document=self.doc3, user=self.user)

        # Add documents to the Extract
        self.extract.documents.add(self.doc, self.doc2, self.doc3)
        self.extract.save()

        logging.info("Fixture data set up complete for TestDocExtractQueryTaskDirect.")

    @vcr.use_cassette(
        "fixtures/vcr_cassettes/test_doc_extract_query_task_directly.yaml",
        record_mode="once",
        filter_headers=["authorization"],
    )
    def test_doc_extract_query_task_directly(self) -> None:
        """
        Tests doc_extract_query_task by creating new Datacells for each document
        in the extract and calling the task directly against them. This allows more
        focused testing without the extracts orchestration layer.
        """
        logging.info("Starting test_doc_extract_query_task_directly.")

        for doc in self.extract.documents.all():

            cell = Datacell.objects.create(
                extract=self.extract,
                column=self.column1,
                document=doc,
                data_definition="Testing doc_extract_query_task directly",
                creator=self.user,
            )

            try:
                # Call the task synchronously
                doc_extract_query_task.si(cell.id).apply()

                # Reload the Datacell from DB
                cell.refresh_from_db()
                result = cell.data
                logging.debug(f"Result for cell {cell.id}: {result}")

                # Basic checks
                self.assertIsNotNone(
                    result, f"Expected a non-None result from cell {cell.id}"
                )
                self.assertIsNotNone(
                    cell.data,
                    f"The Datacell's data (ID: {cell.id}) should not be None after the extraction.",
                )

                # Verify the result has the expected structure
                self.assertIn(
                    "data", result, "Expected 'data' key in extraction result"
                )

                # Verify completion status
                self.assertIsNotNone(
                    cell.completed, f"Cell {cell.id} should be marked as completed"
                )
                self.assertIsNone(
                    cell.failed, f"Cell {cell.id} should not be marked as failed"
                )

            except Exception as e:
                logging.error(
                    f"Exception in test_doc_extract_query_task_directly for cell {cell.id}: {e}"
                )
                import traceback

                logging.error(traceback.format_exc())
                raise

        # Double-check the number of DocumentAnalysisRows if desired
        rows = DocumentAnalysisRow.objects.filter(extract=self.extract)
        self.assertEqual(
            rows.count(),
            0,
            "No DocumentAnalysisRow objects should be created here since we're only calling the single task directly.",
        )

        logging.info("Completed test_doc_extract_query_task_directly.")
