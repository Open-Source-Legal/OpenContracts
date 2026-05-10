"""
Quick test for the new structured extraction implementation (synchronous version).
"""

import vcr
from django.contrib.auth import get_user_model
from django.test import TransactionTestCase

from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.extracts.models import Column, Datacell, Extract, Fieldset
from opencontractserver.tasks.data_extract_tasks import doc_extract_query_task
from opencontractserver.tasks.extract_orchestrator_tasks import run_extract
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()


class NewExtractionTestCase(TransactionTestCase):
    """Test the new agent-based extraction pipeline (sync)."""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")

        # Create corpus
        self.corpus = Corpus.objects.create(title="Test Corpus", creator=self.user)

        # Create document
        self.document = Document.objects.create(
            title="Test Document", creator=self.user, file_type="text/plain"
        )
        self.corpus.add_document(document=self.document, user=self.user)

        # Create fieldset
        self.fieldset = Fieldset.objects.create(
            name="Test Fieldset",
            description="Test extraction fields",
            creator=self.user,
        )

    @vcr.use_cassette(
        "fixtures/vcr_cassettes/test_simple_string_extraction.yaml",
        record_mode="once",
        filter_headers=["authorization"],
    )
    def test_simple_string_extraction(self):
        """Test extracting a simple string value."""
        # Create column
        column = Column.objects.create(
            name="Document Title",
            fieldset=self.fieldset,
            query="What is the title of this document?",
            output_type="str",
            extract_is_list=False,
            creator=self.user,
        )

        # Create extract
        extract = Extract.objects.create(
            name="Test Extract", fieldset=self.fieldset, creator=self.user
        )

        extract.documents.add(self.document)

        # Create datacell
        datacell = Datacell.objects.create(
            extract=extract,
            column=column,
            document=self.document,
            data_definition="str",
            creator=self.user,
        )

        # Run extraction
        doc_extract_query_task.si(datacell.id).apply()

        datacell.refresh_from_db()

        completed = datacell.completed
        failed = datacell.failed
        data = datacell.data

        assert completed is not None
        assert failed is None
        assert data is not None
        assert "data" in data

    @vcr.use_cassette(
        "fixtures/vcr_cassettes/test_list_extraction.yaml",
        record_mode="once",
        filter_headers=["authorization"],
    )
    def test_list_extraction(self):
        """Test extracting a list of values."""
        column = Column.objects.create(
            name="Key Terms",
            fieldset=self.fieldset,
            query="List all the key terms mentioned in this document",
            output_type="str",
            extract_is_list=True,
            creator=self.user,
        )

        extract = Extract.objects.create(
            name="Test Extract", fieldset=self.fieldset, creator=self.user
        )
        extract.documents.add(self.document)

        datacell = Datacell.objects.create(
            extract=extract,
            column=column,
            document=self.document,
            data_definition="list[str]",
            creator=self.user,
        )

        # Run extraction
        doc_extract_query_task.si(datacell.id).apply()

        datacell.refresh_from_db()

        completed = datacell.completed
        data = datacell.data

        assert completed is not None
        assert data is not None
        assert isinstance(data.get("data"), list)

    @vcr.use_cassette(
        "fixtures/vcr_cassettes/test_with_constraints.yaml",
        record_mode="once",
        filter_headers=["authorization"],
    )
    def test_with_constraints(self):
        """Test extraction with must_contain_text and limit_to_label."""
        column = Column.objects.create(
            name="Payment Terms",
            fieldset=self.fieldset,
            query="What are the payment terms?",
            output_type="str",
            must_contain_text="payment",
            limit_to_label="contract_clause",
            instructions="Focus on payment schedules and amounts",
            creator=self.user,
        )

        extract = Extract.objects.create(
            name="Test Extract", fieldset=self.fieldset, creator=self.user
        )
        extract.documents.add(self.document)

        datacell = Datacell.objects.create(
            extract=extract,
            column=column,
            document=self.document,
            data_definition="str",
            creator=self.user,
        )

        # Run extraction
        doc_extract_query_task.si(datacell.id).apply()

        datacell.refresh_from_db()

        started = datacell.started
        failed = datacell.failed
        completed = datacell.completed

        # Should complete (might return None if constraints not met)
        assert started is not None
        assert failed is None or completed is not None


class ExtractOrchestrationTestCase(TransactionTestCase):
    """Test the extract orchestration pipeline."""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")

        # Create corpus
        self.corpus = Corpus.objects.create(title="Test Corpus", creator=self.user)

        # Create multiple documents
        self.doc1 = Document.objects.create(
            title="Test Document 1",
            creator=self.user,
            file_type="text/plain",
            txt_extract_file=self._create_txt_file(
                "Document 1 content with payment terms"
            ),
        )
        self.doc2 = Document.objects.create(
            title="Test Document 2",
            creator=self.user,
            file_type="text/plain",
            txt_extract_file=self._create_txt_file(
                "Document 2 content with delivery terms"
            ),
        )
        self.doc3 = Document.objects.create(
            title="Test Document 3",
            creator=self.user,
            file_type="text/plain",
            txt_extract_file=self._create_txt_file(
                "Document 3 content with warranty terms"
            ),
        )

        # Add documents to corpus
        self.corpus.add_document(document=self.doc1, user=self.user)
        self.corpus.add_document(document=self.doc2, user=self.user)
        self.corpus.add_document(document=self.doc3, user=self.user)

        # Create fieldset with multiple columns
        self.fieldset = Fieldset.objects.create(
            name="Contract Terms Fieldset",
            description="Extract key contract terms",
            creator=self.user,
        )

        # Create columns for different data types
        self.title_column = Column.objects.create(
            name="Document Title",
            fieldset=self.fieldset,
            query="What is the title of this document?",
            output_type="str",
            extract_is_list=False,
            creator=self.user,
        )

        self.terms_column = Column.objects.create(
            name="Key Terms",
            fieldset=self.fieldset,
            query="List all important terms mentioned in this document",
            output_type="str",
            extract_is_list=True,
            creator=self.user,
        )

        self.has_payment_column = Column.objects.create(
            name="Has Payment Terms",
            fieldset=self.fieldset,
            query="Does this document contain payment terms?",
            output_type="bool",
            extract_is_list=False,
            must_contain_text="payment",
            creator=self.user,
        )

    def _create_txt_file(self, content):
        """Helper to create a simple text file for testing."""
        from django.core.files.base import ContentFile

        return ContentFile(content.encode("utf-8"), name="test.txt")

    @vcr.use_cassette(
        "fixtures/vcr_cassettes/test_run_extract_orchestration.yaml",
        record_mode="once",
        filter_headers=["authorization"],
    )
    def test_run_extract_orchestration(self):
        """Test the full extract orchestration with multiple documents and columns."""
        # Create extract
        extract = Extract.objects.create(
            name="Test Full Extract", fieldset=self.fieldset, creator=self.user
        )
        set_permissions_for_obj_to_user(self.user, extract, [PermissionTypes.ALL])

        # Add all documents
        extract.documents.add(self.doc1, self.doc2, self.doc3)

        # Get initial datacell count
        # initial_datacell_count = extract.extracted_datacells.count()

        # Run the orchestration task
        run_extract.si(extract.id, self.user.id).apply()

        # Refresh extract
        extract.refresh_from_db()

        # Verify extract was marked as started
        assert extract.started is not None

        # Verify correct number of datacells created
        # Should be: 3 documents × 3 columns = 9 datacells
        expected_count = len(extract.documents.all()) * len(self.fieldset.columns.all())
        actual_count = extract.extracted_datacells.count()

        assert (
            actual_count == expected_count
        ), f"Expected {expected_count} datacells, got {actual_count}"

        # Verify all datacells are associated correctly
        for doc in extract.documents.all():
            for column in self.fieldset.columns.all():
                datacell_exists = extract.extracted_datacells.filter(
                    document=doc, column=column
                ).exists()
                assert (
                    datacell_exists
                ), f"Missing datacell for doc {doc.title} and column {column.name}"

    def test_extract_with_vcr(self):
        """Test extraction with VCR for API call recording."""

        # Create a simple extract
        extract = Extract.objects.create(
            name="VCR Test Extract", fieldset=self.fieldset, creator=self.user
        )
        set_permissions_for_obj_to_user(self.user, extract, [PermissionTypes.ALL])
        extract.documents.add(self.doc1)  # Just one doc for VCR test

        with vcr.use_cassette(
            "fixtures/vcr_cassettes/test_new_extract_orchestration.yaml",
            record_mode="once",  # Change to "new_episodes" to record new calls
            filter_headers=["authorization"],
        ):
            # Run extraction
            run_extract.si(extract.id, self.user.id).apply()

            # Verify datacells were created
            assert extract.extracted_datacells.count() == len(
                self.fieldset.columns.all()
            )

    def test_extract_completion_callback(self):
        """Test that the extract completion callback is properly called."""
        from unittest.mock import patch

        extract = Extract.objects.create(
            name="Callback Test Extract", fieldset=self.fieldset, creator=self.user
        )
        set_permissions_for_obj_to_user(self.user, extract, [PermissionTypes.ALL])
        extract.documents.add(self.doc1)

        # In eager mode (test environment), mark_extract_complete is called directly.
        # We patch it to verify it gets called with the correct extract_id.
        with patch(
            "opencontractserver.tasks.extract_orchestrator_tasks.mark_extract_complete"
        ) as mock_callback:
            run_extract.si(extract.id, self.user.id).apply()

            # Verify the completion callback was called with correct extract_id
            mock_callback.assert_called_once_with(extract.id)

            # Verify the extract was started
            extract.refresh_from_db()
            assert extract.started is not None

    def test_run_extract_aborts_for_nonexistent_user(self):
        """run_extract should abort silently when user_id doesn't exist."""
        extract = Extract.objects.create(
            name="Abort Test Extract", fieldset=self.fieldset, creator=self.user
        )
        set_permissions_for_obj_to_user(self.user, extract, [PermissionTypes.ALL])

        # Use an ID that doesn't exist
        nonexistent_user_id = 999999

        # Should not raise — just return early
        run_extract.si(extract.id, nonexistent_user_id).apply()

        # Extract should NOT have a started timestamp (task aborted before setting it)
        extract.refresh_from_db()
        self.assertIsNone(extract.started)

    def test_run_extract_aborts_for_unauthorized_user(self):
        """run_extract should abort when user lacks UPDATE permission."""
        # Create a different user with no permissions on the extract
        other_user = User.objects.create_user(
            username="noperm_user", password="testpass123"
        )

        extract = Extract.objects.create(
            name="Permission Test Extract", fieldset=self.fieldset, creator=self.user
        )
        # Don't grant permissions to other_user

        run_extract.si(extract.id, other_user.id).apply()

        # Extract should NOT have a started timestamp (task aborted)
        extract.refresh_from_db()
        self.assertIsNone(extract.started)

    def test_run_extract_aborts_for_none_extract_id(self):
        """run_extract returns early when extract_id is None (PR #1482 typing fix)."""
        # Should not raise — guard at the top of the task aborts before any DB hit.
        result = run_extract.si(None, self.user.id).apply()

        # Eager-mode return value must be None (the guard ``return`` clause).
        self.assertIsNone(result.result)
