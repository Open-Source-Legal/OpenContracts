import logging

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TestCase, TransactionTestCase

from opencontractserver.annotations.models import TOKEN_LABEL, Annotation, Note
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.llms.agents.core_agents import SourceNode
from opencontractserver.llms.tools import (
    get_md_summary_token_length,
    get_notes_for_document_corpus,
    load_document_md_summary,
)
from opencontractserver.llms.tools.core_tools import (
    _token_count,
    add_document_note,
    aduplicate_annotations_with_label,
    aget_corpus_description,
    aload_document_txt_extract,
    asearch_document_notes,
    asearch_exact_text_as_sources,
    aupdate_corpus_description,
    aupdate_document_note,
    duplicate_annotations_with_label,
    get_corpus_description,
    get_document_summary,
    get_document_summary_at_version,
    get_document_summary_diff,
    get_document_summary_versions,
    load_document_txt_extract,
    search_document_notes,
    search_exact_text_as_sources,
    update_corpus_description,
    update_document_note,
    update_document_summary,
)

User = get_user_model()
logger = logging.getLogger(__name__)


class TestLLMTools(TestCase):
    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(username="testuser", password="12345")

        self.corpus = Corpus.objects.create(
            title="Test Corpus",
            creator=self.user,
        )

        # Create a test document with a summary file
        self.doc = Document.objects.create(
            creator=self.user,
            title="Test Document",
            description="Test Description",
        )

        # Create a mock summary file
        summary_content = (
            "This is a test summary.\nIt has multiple lines.\nAnd some content."
        )
        self.doc.md_summary_file.save(
            "test_summary.md", ContentFile(summary_content.encode())
        )

        # Create mock txt extract content and file
        self.txt_content = "This is test text extract content for document analysis."
        self.doc.txt_extract_file.save(
            "test_extract.txt", ContentFile(self.txt_content.encode())
        )

        # Create test notes
        self.note = Note.objects.create(
            document=self.doc,
            title="Test Note",
            content="Test note content that is longer than the typical preview length",
            creator=self.user,
        )

        # Prepare corpus markdown description via helper
        self.initial_corpus_md = "# Corpus\n\nInitial description"
        update_corpus_description(
            corpus_id=self.corpus.id,
            new_content=self.initial_corpus_md,
            author_id=self.user.id,
        )

        # Create second revision
        self.updated_corpus_md = "# Corpus\n\nUpdated description v2"
        update_corpus_description(
            corpus_id=self.corpus.id,
            new_content=self.updated_corpus_md,
            author_id=self.user.id,
        )

    def test_token_count_empty(self):
        """Test token counting with empty string."""
        result = _token_count("")
        self.assertEqual(result, 0)

    def test_token_count_whitespace(self):
        """Test token counting with only whitespace."""
        result = _token_count("   \n\t   ")
        self.assertEqual(result, 0)

    def test_load_document_md_summary_nonexistent_doc(self):
        """Test loading summary for non-existent document."""
        with self.assertRaisesRegex(
            ValueError, "Document with id=999999 does not exist."
        ):
            load_document_md_summary(999999)

    def test_load_document_md_summary_no_file(self):
        """Test loading summary when no summary file exists."""
        doc_without_summary = Document.objects.create(
            creator=self.user,
            title="No Summary Doc",
        )
        self.assertEqual(
            "NO SUMMARY PREPARED", load_document_md_summary(doc_without_summary.id)
        )

    def test_load_document_md_summary_truncate_from_end(self):
        """Test loading summary with truncation from end."""
        result = load_document_md_summary(
            self.doc.id, truncate_length=10, from_start=False
        )
        self.assertEqual(len(result), 10)

    def test_get_md_summary_token_length_nonexistent(self):
        """Test token length for non-existent document."""
        with self.assertRaisesRegex(
            ValueError, "Document with id=999999 does not exist."
        ):
            get_md_summary_token_length(999999)

    def test_get_md_summary_token_length_no_file(self):
        """Test token length when no summary file exists."""
        doc_without_summary = Document.objects.create(
            creator=self.user,
            title="No Summary Doc",
        )
        self.assertEqual(0, get_md_summary_token_length(doc_without_summary.id))

    def test_get_notes_for_document_corpus_with_truncation(self):
        """Test note retrieval with content truncation."""
        # Create a note with content longer than 512 characters
        long_content = "x" * 1000
        Note.objects.create(
            document=self.doc,
            title="Long Note",
            content=long_content,
            creator=self.user,
        )

        results = get_notes_for_document_corpus(
            document_id=self.doc.id, corpus_id=self.corpus.id
        )

        # Verify content truncation
        for note_dict in results:
            self.assertLessEqual(len(note_dict["content"]), 512)

        # Verify ordering by created date
        created_dates = [note["created"] for note in results]
        self.assertEqual(created_dates, sorted(created_dates))

    def test_load_document_txt_extract_success(self):
        """Test successful txt extract loading."""
        result = load_document_txt_extract(self.doc.id)
        self.assertEqual(result, self.txt_content)

    # ------------------------------------------------------------------
    # New tests for corpus description helpers
    # ------------------------------------------------------------------

    def test_get_corpus_description(self):
        """Should return the latest markdown description."""
        desc = get_corpus_description(self.corpus.id)
        self.assertEqual(desc, self.updated_corpus_md)

    def test_update_corpus_description_no_change_returns_none(self):
        """Updating with identical content should return None."""
        result = update_corpus_description(
            corpus_id=self.corpus.id,
            new_content=self.updated_corpus_md,
            author_id=self.user.id,
        )
        self.assertIsNone(result)

    # ------------------------------------------------------------------
    # New tests for note helpers
    # ------------------------------------------------------------------

    def test_add_and_search_document_note(self):
        """Add a new note and ensure it appears in search results."""

        new_note = add_document_note(
            document_id=self.doc.id,
            title="Searchable Note",
            content="This note contains keyword foobar in content.",
            creator_id=self.user.id,
        )

        results = search_document_notes(
            document_id=self.doc.id, search_term="foobar", limit=5
        )

        self.assertTrue(any(r["id"] == new_note.id for r in results))

    def test_update_document_note(self):
        """Version-up an existing note and verify content update."""

        old_revision_count = self.note.revisions.count()

        new_content = "Updated note content version 2"
        revision = update_document_note(
            note_id=self.note.id,
            new_content=new_content,
            author_id=self.user.id,
        )

        # Revision object is returned
        self.assertIsNotNone(revision)
        self.assertEqual(revision.version, old_revision_count + 1)

        # Note content updated
        self.note.refresh_from_db()
        self.assertEqual(self.note.content, new_content)

    # ------------------------------------------------------------------
    # New tests for annotation duplication helper
    # ------------------------------------------------------------------

    def test_duplicate_annotations_with_label(self):
        """Duplicate an annotation and ensure label/labelset are created."""

        # Create source annotation (no label-set on corpus yet).
        source_ann = Annotation.objects.create(
            page=1,
            raw_text="Sample annotation",
            document=self.doc,
            corpus=self.corpus,
            creator=self.user,
        )

        # Sanity: corpus should not have a label_set at this point.
        self.assertIsNone(self.corpus.label_set)

        new_ids = duplicate_annotations_with_label(
            [source_ann.id],
            new_label_text="NewLabel",
            creator_id=self.user.id,
        )

        # One duplicate should be produced.
        self.assertEqual(len(new_ids), 1)

        duplicate = Annotation.objects.get(pk=new_ids[0])

        # Corpus now has a label_set and the label inside it.
        self.corpus.refresh_from_db()
        self.assertIsNotNone(self.corpus.label_set)

        label = duplicate.annotation_label
        self.assertIsNotNone(label)
        self.assertEqual(label.text, "NewLabel")
        self.assertEqual(label.label_type, TOKEN_LABEL)
        self.assertIn(label, self.corpus.label_set.annotation_labels.all())

        # Duplicate keeps original fields.
        self.assertEqual(duplicate.page, source_ann.page)
        self.assertEqual(duplicate.raw_text, source_ann.raw_text)
        self.assertEqual(duplicate.document_id, source_ann.document_id)
        self.assertEqual(duplicate.corpus_id, source_ann.corpus_id)
        self.assertEqual(duplicate.creator_id, self.user.id)

    # ------------------------------------------------------------------
    # Tests for document summary helpers
    # ------------------------------------------------------------------

    def test_get_document_summary(self):
        """Test retrieving document summary content."""
        # Create document with summary
        summary_content = "# Document Summary\n\nThis is a test summary"
        self.doc.update_summary(
            new_content=summary_content, author=self.user, corpus=self.corpus
        )

        # Test basic retrieval
        result = get_document_summary(self.doc.id, self.corpus.id)
        self.assertEqual(result, summary_content)

        # Test truncation from start
        result = get_document_summary(
            self.doc.id, self.corpus.id, truncate_length=20, from_start=True
        )
        self.assertEqual(result, summary_content[:20])

        # Test truncation from end
        result = get_document_summary(
            self.doc.id, self.corpus.id, truncate_length=15, from_start=False
        )
        self.assertEqual(result, summary_content[-15:])

    def test_get_document_summary_no_summary(self):
        """Test retrieving summary when none exists."""
        # Create fresh document without summary
        doc_no_summary = Document.objects.create(
            creator=self.user,
            title="No Summary Doc",
        )
        self.corpus.add_document(document=doc_no_summary, user=self.user)

        result = get_document_summary(doc_no_summary.id, self.corpus.id)
        self.assertEqual(result, "")

    def test_get_document_summary_invalid_document(self):
        """Test retrieving summary for non-existent document."""
        with self.assertRaisesRegex(
            ValueError, "Document with id=999999 does not exist"
        ):
            get_document_summary(999999, self.corpus.id)

    def test_get_document_summary_invalid_corpus(self):
        """Test retrieving summary for non-existent corpus."""
        with self.assertRaisesRegex(ValueError, "Corpus with id=999999 does not exist"):
            get_document_summary(self.doc.id, 999999)

    def test_get_document_summary_versions(self):
        """Test retrieving version history."""
        # Create multiple versions
        self.doc.update_summary(
            new_content="Version 1", author=self.user, corpus=self.corpus
        )
        self.doc.update_summary(
            new_content="Version 2", author=self.user, corpus=self.corpus
        )
        self.doc.update_summary(
            new_content="Version 3", author=self.user, corpus=self.corpus
        )

        # Get all versions
        versions = get_document_summary_versions(self.doc.id, self.corpus.id)
        self.assertEqual(len(versions), 3)

        # Check ordering (newest first)
        self.assertEqual(versions[0]["version"], 3)
        self.assertEqual(versions[1]["version"], 2)
        self.assertEqual(versions[2]["version"], 1)

        # Check structure
        for version in versions:
            self.assertIn("id", version)
            self.assertIn("version", version)
            self.assertIn("author_id", version)
            self.assertIn("created", version)
            self.assertIn("checksum_base", version)
            self.assertIn("checksum_full", version)
            self.assertIn("has_snapshot", version)
            self.assertIn("has_diff", version)

    def test_get_document_summary_versions_with_limit(self):
        """Test retrieving limited version history."""
        # Create 5 versions
        for i in range(1, 6):
            self.doc.update_summary(
                new_content=f"Version {i}", author=self.user, corpus=self.corpus
            )

        # Get only 3 most recent
        versions = get_document_summary_versions(self.doc.id, self.corpus.id, limit=3)
        self.assertEqual(len(versions), 3)
        self.assertEqual(versions[0]["version"], 5)
        self.assertEqual(versions[1]["version"], 4)
        self.assertEqual(versions[2]["version"], 3)

    def test_get_document_summary_diff(self):
        """Test getting diff between versions."""
        # Create versions
        self.doc.update_summary(
            new_content="Line 1\nLine 2\nLine 3", author=self.user, corpus=self.corpus
        )
        self.doc.update_summary(
            new_content="Line 1\nLine 2 modified\nLine 3\nLine 4",
            author=self.user,
            corpus=self.corpus,
        )

        # Get diff
        diff_info = get_document_summary_diff(
            self.doc.id, self.corpus.id, from_version=1, to_version=2
        )

        # Check structure
        self.assertEqual(diff_info["from_version"], 1)
        self.assertEqual(diff_info["to_version"], 2)
        self.assertEqual(diff_info["from_author_id"], self.user.id)
        self.assertEqual(diff_info["to_author_id"], self.user.id)
        self.assertIn("from_created", diff_info)
        self.assertIn("to_created", diff_info)
        self.assertIn("diff", diff_info)
        self.assertIn("from_content", diff_info)
        self.assertIn("to_content", diff_info)

        # Check diff contains expected changes
        self.assertIn("-Line 2", diff_info["diff"])
        self.assertIn("+Line 2 modified", diff_info["diff"])
        self.assertIn("+Line 4", diff_info["diff"])

    def test_get_document_summary_diff_invalid_versions(self):
        """Test diff with non-existent versions."""
        self.doc.update_summary(
            new_content="Version 1", author=self.user, corpus=self.corpus
        )

        with self.assertRaisesRegex(ValueError, "Revision version .* not found"):
            get_document_summary_diff(
                self.doc.id, self.corpus.id, from_version=1, to_version=5
            )

    def test_update_document_summary(self):
        """Test creating/updating document summary."""
        # Create initial summary
        result = update_document_summary(
            document_id=self.doc.id,
            corpus_id=self.corpus.id,
            new_content="Initial summary",
            author_id=self.user.id,
        )

        self.assertTrue(result["created"])
        self.assertEqual(result["version"], 1)
        self.assertIn("revision_id", result)
        self.assertEqual(result["author_id"], self.user.id)

        # Update summary
        result = update_document_summary(
            document_id=self.doc.id,
            corpus_id=self.corpus.id,
            new_content="Updated summary",
            author_id=self.user.id,
        )

        self.assertTrue(result["created"])
        self.assertEqual(result["version"], 2)

        # No change update
        result = update_document_summary(
            document_id=self.doc.id,
            corpus_id=self.corpus.id,
            new_content="Updated summary",  # Same content
            author_id=self.user.id,
        )

        self.assertFalse(result["created"])
        self.assertEqual(result["version"], 2)
        self.assertEqual(result["message"], "No change in content")

    def test_update_document_summary_with_author_object(self):
        """Test updating summary with author object instead of ID."""
        result = update_document_summary(
            document_id=self.doc.id,
            corpus_id=self.corpus.id,
            new_content="Summary with author object",
            author=self.user,  # Pass object instead of ID
        )

        self.assertTrue(result["created"])
        self.assertEqual(result["author_id"], self.user.id)

    def test_update_document_summary_missing_author(self):
        """Test updating summary without author info."""
        with self.assertRaisesRegex(ValueError, "Provide either author or author_id"):
            update_document_summary(
                document_id=self.doc.id,
                corpus_id=self.corpus.id,
                new_content="No author",
            )

    def test_get_document_summary_at_version(self):
        """Test retrieving specific version content."""
        # Create multiple versions
        contents = ["Version 1 content", "Version 2 content", "Version 3 content"]
        for content in contents:
            self.doc.update_summary(
                new_content=content, author=self.user, corpus=self.corpus
            )

        # Retrieve each version
        for i, expected_content in enumerate(contents, 1):
            result = get_document_summary_at_version(self.doc.id, self.corpus.id, i)
            self.assertEqual(result, expected_content)

    def test_get_document_summary_at_version_invalid(self):
        """Test retrieving non-existent version."""
        self.doc.update_summary(
            new_content="Only version", author=self.user, corpus=self.corpus
        )

        with self.assertRaisesRegex(ValueError, "Version 5 not found"):
            get_document_summary_at_version(self.doc.id, self.corpus.id, 5)

    # ------------------------------------------------------------------
    # Tests for exact text search and SourceNode transformation
    # ------------------------------------------------------------------

    def test_search_exact_text_in_text_document(self):
        """Test exact text search in text document returns proper SourceNode format."""
        # Ensure document is marked as text/plain
        self.doc.file_type = "text/plain"
        self.doc.save()

        # Search for text that exists in our txt_content
        search_strings = ["test text"]

        results = search_exact_text_as_sources(
            document_id=self.doc.id,
            search_strings=search_strings,
            corpus_id=self.corpus.id,
        )

        # Verify we got results
        self.assertGreater(len(results), 0, "Should find at least one match")

        # Verify results are SourceNode objects
        for result in results:
            self.assertIsInstance(result, SourceNode)
            self.assertIsNotNone(result.content)
            self.assertEqual(result.similarity_score, 1.0)  # Exact match = 1.0

            # Verify metadata contains char_start and char_end (for text files)
            self.assertIn("char_start", result.metadata)
            self.assertIn("char_end", result.metadata)
            self.assertIn("document_id", result.metadata)
            self.assertEqual(result.metadata["document_id"], self.doc.id)
            self.assertEqual(result.metadata["corpus_id"], self.corpus.id)

            # Verify negative synthetic IDs
            self.assertLess(result.annotation_id, 0)

    def test_source_node_to_dict_text_format(self):
        """Test that SourceNode.to_dict() produces correct json field for text sources."""
        # Create a SourceNode as it would come from text document search
        source = SourceNode(
            annotation_id=-1,
            content="test text extract content",
            similarity_score=1.0,
            metadata={
                "document_id": self.doc.id,
                "corpus_id": self.corpus.id,
                "page": 0,
                "char_start": 10,
                "char_end": 35,
                "search_string": "test text",
                "match_type": "exact_text_text",
            },
        )

        # Convert to dict (format that will be stored in DB and sent to frontend)
        result_dict = source.to_dict()

        # Verify base fields
        self.assertEqual(result_dict["annotation_id"], -1)
        self.assertEqual(result_dict["rawText"], "test text extract content")
        self.assertEqual(result_dict["similarity_score"], 1.0)

        # Verify json field has simple {start, end} format for text files
        self.assertIn("json", result_dict)
        self.assertIsInstance(result_dict["json"], dict)
        self.assertEqual(result_dict["json"]["start"], 10)
        self.assertEqual(result_dict["json"]["end"], 35)

        # Verify metadata is flattened
        self.assertEqual(result_dict["document_id"], self.doc.id)
        self.assertEqual(result_dict["corpus_id"], self.corpus.id)
        self.assertEqual(result_dict["page"], 0)
        self.assertEqual(result_dict["char_start"], 10)
        self.assertEqual(result_dict["char_end"], 35)

    def test_source_node_to_dict_pdf_format(self):
        """Test that SourceNode.to_dict() produces correct json field for PDF sources."""
        # Create a mock MultipageAnnotationJson as it would come from PlasmaPDF
        mock_annotation_json = {
            "0": {  # Page 0
                "bounds": {
                    "top": 100.5,
                    "bottom": 120.3,
                    "left": 50.2,
                    "right": 250.8,
                },
                "tokensJsons": [
                    {"pageIndex": 0, "tokenIndex": 10},
                    {"pageIndex": 0, "tokenIndex": 11},
                    {"pageIndex": 0, "tokenIndex": 12},
                ],
                "rawText": "test text",
            }
        }

        # Create a SourceNode as it would come from PDF document search
        source = SourceNode(
            annotation_id=-1,
            content="test text",
            similarity_score=1.0,
            metadata={
                "document_id": self.doc.id,
                "corpus_id": self.corpus.id,
                "page": 1,
                "annotation_json": mock_annotation_json,  # Full MultipageAnnotationJson
                "search_string": "test text",
                "char_start": 100,
                "char_end": 109,
                "bounding_box": {
                    "top": 100.5,
                    "bottom": 120.3,
                    "left": 50.2,
                    "right": 250.8,
                },
                "match_type": "exact_text_pdf",
            },
        )

        # Convert to dict (format that will be stored in DB and sent to frontend)
        result_dict = source.to_dict()

        # Verify base fields
        self.assertEqual(result_dict["annotation_id"], -1)
        self.assertEqual(result_dict["rawText"], "test text")
        self.assertEqual(result_dict["similarity_score"], 1.0)

        # Verify json field contains full MultipageAnnotationJson for PDFs
        self.assertIn("json", result_dict)
        self.assertIsInstance(result_dict["json"], dict)
        self.assertIn("0", result_dict["json"])  # Page 0 data
        self.assertIn("bounds", result_dict["json"]["0"])
        self.assertIn("tokensJsons", result_dict["json"]["0"])
        self.assertEqual(result_dict["json"]["0"]["rawText"], "test text")

        # Verify metadata is flattened (but annotation_json should not be duplicated)
        self.assertEqual(result_dict["document_id"], self.doc.id)
        self.assertEqual(result_dict["corpus_id"], self.corpus.id)
        self.assertEqual(result_dict["page"], 1)
        self.assertNotIn("annotation_json", result_dict)  # Should be only in json field

        # Other metadata should still be present
        self.assertEqual(result_dict["char_start"], 100)
        self.assertEqual(result_dict["char_end"], 109)
        self.assertIn("bounding_box", result_dict)

    def test_search_exact_text_with_pdf_document(self):
        """Test exact text search with a text document (PDF with PAWLS would require extensive mocking)."""
        # Create a document with text extract
        text_doc = Document.objects.create(
            creator=self.user,
            title="Test Text Document",
            description="Test Text",
            file_type="text/plain",  # Use text/plain since we don't have PAWLS data
        )

        # Create mock text content
        text_content = "This is a sample document with covenants and agreements."
        text_doc.txt_extract_file.save(
            "test_text_extract.txt", ContentFile(text_content.encode())
        )

        # Note: For full PDF testing with MultipageAnnotationJson, we would need to:
        # 1. Create a mock pdf_extract_file
        # 2. Create mock PAWLS data with token positions
        # 3. Mock the PlasmaPDF build_translation_layer function
        # This is complex and would require significant mocking infrastructure.
        # For now, we verify that text-based search works correctly.

        search_strings = ["covenants and agreements"]

        results = search_exact_text_as_sources(
            document_id=text_doc.id,
            search_strings=search_strings,
            corpus_id=self.corpus.id,
        )

        # Should find text matches
        self.assertGreater(len(results), 0, "Should find matches")

        for result in results:
            self.assertIsInstance(result, SourceNode)
            self.assertIn("covenants and agreements", result.content)

            # Verify metadata
            self.assertIn("document_id", result.metadata)
            self.assertEqual(result.metadata["document_id"], text_doc.id)

            # Text documents should have char_start and char_end
            self.assertIn("char_start", result.metadata)
            self.assertIn("char_end", result.metadata)

    def test_search_exact_text_no_matches(self):
        """Test exact text search returns empty list when no matches found."""
        # Ensure document is marked as text/plain
        self.doc.file_type = "text/plain"
        self.doc.save()

        search_strings = ["ThisStringDefinitelyDoesNotExist12345"]

        results = search_exact_text_as_sources(
            document_id=self.doc.id,
            search_strings=search_strings,
            corpus_id=self.corpus.id,
        )

        self.assertEqual(len(results), 0, "Should return empty list when no matches")


class AsyncTestDuplicateTools(TransactionTestCase):
    """Separate test class for async tests to avoid database connection issues."""

    @classmethod
    def setUpClass(cls):
        """Set up test data."""
        super().setUpClass()

        cls.user = User.objects.create_user(username="testuser_async", password="12345")

        # Create a test document with txt extract file
        cls.doc = Document.objects.create(
            creator=cls.user,
            title="Async Test Document",
            description="Test Description",
        )

        # Create mock txt extract content and file
        cls.txt_content = (
            "This is test text extract content for async document analysis."
        )
        cls.doc.txt_extract_file.save(
            "test_extract_async.txt", ContentFile(cls.txt_content.encode())
        )

        cls.corpus = Corpus.objects.create(
            title="Async Corpus",
            creator=cls.user,
        )

        cls.annotation = Annotation.objects.create(
            page=1,
            raw_text="Async annotation",
            document=cls.doc,
            corpus=cls.corpus,
            creator=cls.user,
        )

    # ------------------------------------------------------------------
    # New async tests for annotation duplication helper - why separate class?
    # Why indeed... some deep dark async f*ckery going on here.
    # ------------------------------------------------------------------

    async def test_aduplicate_annotations_with_label(self):
        """Async duplication should mirror sync behaviour."""

        new_ids = await aduplicate_annotations_with_label(
            [self.annotation.id],
            new_label_text="AsyncNewLabel",
            creator_id=self.user.id,
        )

        self.assertEqual(len(new_ids), 1)

        # Pull related objects in a single DB round-trip so attribute access
        # below doesn't trigger additional (sync-only) queries.
        new_ann = await Annotation.objects.select_related("annotation_label").aget(
            pk=new_ids[0]
        )

        # corpus should now have label_set populated
        corpus_refresh = await Corpus.objects.select_related("label_set").aget(
            pk=self.corpus.id
        )
        self.assertIsNotNone(corpus_refresh.label_set)

        self.assertIsNotNone(new_ann.annotation_label)
        self.assertEqual(new_ann.annotation_label.text, "AsyncNewLabel")
        self.assertEqual(new_ann.creator_id, self.user.id)


class AsyncTestLLMTools(TestCase):
    """Separate test class for async tests to avoid database connection issues."""

    @classmethod
    def setUpClass(cls):
        """Set up test data."""
        super().setUpClass()

        cls.user = User.objects.create_user(username="testuser_async", password="12345")

        # Create a test document with txt extract file
        cls.doc = Document.objects.create(
            creator=cls.user,
            title="Async Test Document",
            description="Test Description",
        )

        # Create mock txt extract content and file
        cls.txt_content = (
            "This is test text extract content for async document analysis."
        )
        cls.doc.txt_extract_file.save(
            "test_extract_async.txt", ContentFile(cls.txt_content.encode())
        )

        cls.corpus = Corpus.objects.create(
            title="Async Corpus",
            creator=cls.user,
        )

        cls.annotation = Annotation.objects.create(
            page=1,
            raw_text="Async annotation",
            document=cls.doc,
            corpus=cls.corpus,
            creator=cls.user,
        )

    # ------------------------------------------------------------------
    # NEW: Make sure the mock extract lives inside the *current* MEDIA_ROOT
    # assigned by pytest-django for this particular test function.
    # Pytest-django rewrites settings.MEDIA_ROOT for every test; when the
    # file is only written once in setUpClass it ends up inside the first
    # tmp directory, breaking subsequent tests that run with a different
    # MEDIA_ROOT.  Re-sync the file at the start of every test to guarantee
    # it exists where Django expects it.
    # ------------------------------------------------------------------

    def setUp(self):  # noqa: D401 – simple helper, not public API
        """Ensure txt_extract_file exists in the active MEDIA_ROOT."""
        # Refresh the document to obtain a clean instance for the current DB
        # transaction.
        self.doc.refresh_from_db()

        from django.core.files.base import ContentFile

        # When pytest-django swaps MEDIA_ROOT the underlying file might no
        # longer be present at the path derived from self.doc.txt_extract_file
        # even though the field *name* itself remains unchanged. Re-create the
        # file when missing so IO in the actual test does not raise.
        storage = self.doc.txt_extract_file.storage
        if not storage.exists(self.doc.txt_extract_file.name):
            self.doc.txt_extract_file.save(
                "test_extract_async.txt",
                ContentFile(self.txt_content.encode()),
            )

    async def test_aload_document_txt_extract_success(self):
        """Async version should load full extract correctly."""
        result = await aload_document_txt_extract(self.doc.id)
        self.assertEqual(result, self.txt_content)

    async def test_aload_document_txt_extract_with_slice(self):
        """Async version should support slicing."""
        result = await aload_document_txt_extract(self.doc.id, start=5, end=15)
        self.assertEqual(result, self.txt_content[5:15])


class AsyncTestUpdateCorpusDescription(TransactionTestCase):
    """Async tests ensuring :func:`aupdate_corpus_description` behaves correctly."""

    def setUp(self):  # noqa: D401 – simple helper, not public API
        """Prepare a fresh corpus with an initial markdown description for every test."""
        self.user = User.objects.create_user(
            username="async_corpus_user", password="pw"
        )
        self.corpus = Corpus.objects.create(title="Async Corpus", creator=self.user)

        # Initialise with a first markdown description (version 1).
        self.initial_md = "# Corpus\n\nInitial description"
        update_corpus_description(
            corpus_id=self.corpus.id,
            new_content=self.initial_md,
            author_id=self.user.id,
        )

    # ------------------------------------------------------------------
    # Success paths
    # ------------------------------------------------------------------

    async def test_aupdate_with_new_content_creates_revision(self):
        """Supplying *new_content* should create a new revision and update the file."""
        new_content = "# Corpus\n\nUpdated description v2"
        revision = await aupdate_corpus_description(
            corpus_id=self.corpus.id,
            new_content=new_content,
            author_id=self.user.id,
        )

        # A revision is returned with incremented version.
        self.assertIsNotNone(revision)
        self.assertEqual(revision.version, 2)

        # The corpus markdown content now matches *new_content*.
        latest_content = await aget_corpus_description(self.corpus.id)
        self.assertEqual(latest_content, new_content)

    async def test_aupdate_with_diff_text_creates_revision(self):
        """Providing *diff_text* instead of full content should also work."""
        import difflib

        current = await aget_corpus_description(self.corpus.id)
        new_content = current + "\nAnother line appended."  # simple change

        diff_text = "".join(
            difflib.ndiff(
                current.splitlines(keepends=True), new_content.splitlines(keepends=True)
            )
        )

        revision = await aupdate_corpus_description(
            corpus_id=self.corpus.id,
            diff_text=diff_text,
            author_id=self.user.id,
        )

        self.assertIsNotNone(revision)
        self.assertEqual(revision.version, 2)
        latest_content = await aget_corpus_description(self.corpus.id)
        self.assertIn("Another line appended.", latest_content)

    async def test_aupdate_no_change_returns_none(self):
        """Supplying identical content should early-exit and return *None*."""
        result = await aupdate_corpus_description(
            corpus_id=self.corpus.id,
            new_content=self.initial_md,
            author_id=self.user.id,
        )
        self.assertIsNone(result)

    # ------------------------------------------------------------------
    # Failure / validation paths
    # ------------------------------------------------------------------

    async def test_aupdate_missing_content_raises(self):
        """Neither *new_content* nor *diff_text* provided – expect ``ValueError``."""
        with self.assertRaisesRegex(
            ValueError, "Provide either new_content or diff_text"
        ):
            await aupdate_corpus_description(
                corpus_id=self.corpus.id,
                author_id=self.user.id,
            )

    async def test_aupdate_both_content_and_diff_raise(self):
        """Supplying both *new_content* and *diff_text* is forbidden."""
        with self.assertRaisesRegex(
            ValueError, "Provide only one of new_content or diff_text"
        ):
            await aupdate_corpus_description(
                corpus_id=self.corpus.id,
                new_content="foo",
                diff_text="bar",
                author_id=self.user.id,
            )

    async def test_aupdate_missing_author_raises(self):
        """Author information is mandatory."""
        with self.assertRaisesRegex(ValueError, "Provide either author or author_id"):
            await aupdate_corpus_description(
                corpus_id=self.corpus.id,
                new_content="foo",
            )

    async def test_aupdate_invalid_corpus_raises(self):
        """Non-existent corpus id should raise a clear ``ValueError``."""
        with self.assertRaisesRegex(ValueError, "Corpus with id=999999 does not exist"):
            await aupdate_corpus_description(
                corpus_id=999999,
                new_content="foo",
                author_id=self.user.id,
            )

    # ------------------------------------------------------------------
    # Additional coverage paths
    # ------------------------------------------------------------------

    async def test_aupdate_with_author_object(self):
        """Passing author object directly should work."""
        new_content = "# Corpus\n\nUpdated with author object"
        revision = await aupdate_corpus_description(
            corpus_id=self.corpus.id,
            new_content=new_content,
            author=self.user,  # Pass user object instead of ID
        )

        self.assertIsNotNone(revision)
        self.assertEqual(revision.author, self.user)

    async def test_aupdate_snapshot_interval(self):
        """Test snapshot creation at interval boundaries."""
        # Create revisions 2-9 (version 1 already exists from setUp)
        for i in range(2, 10):
            await aupdate_corpus_description(
                corpus_id=self.corpus.id,
                new_content=f"# Corpus\n\nVersion {i}",
                author_id=self.user.id,
            )

        # Version 10 should trigger a snapshot
        final_content = "# Corpus\n\nVersion 10 with snapshot"
        revision = await aupdate_corpus_description(
            corpus_id=self.corpus.id,
            new_content=final_content,
            author_id=self.user.id,
        )

        self.assertEqual(revision.version, 10)
        self.assertIsNotNone(revision.snapshot)
        self.assertEqual(revision.snapshot, final_content)


class AsyncTestUpdateDocumentNote(TransactionTestCase):
    """Async tests ensuring :func:`aupdate_document_note` behaves correctly."""

    def setUp(self):  # noqa: D401 – simple helper, not public API
        """Prepare a fresh note with initial content for every test."""
        self.user = User.objects.create_user(username="async_note_user", password="pw")
        self.doc = Document.objects.create(
            creator=self.user,
            title="Test Document for Notes",
            description="Test Description",
        )

        # Create initial note
        self.note = Note.objects.create(
            document=self.doc,
            title="Test Note",
            content="Initial note content",
            creator=self.user,
        )

    async def _get_note_async(self, note_id):
        """Helper to fetch a note asynchronously."""
        from channels.db import database_sync_to_async

        return await database_sync_to_async(Note.objects.get)(pk=note_id)

    # ------------------------------------------------------------------
    # Success paths
    # ------------------------------------------------------------------

    async def test_aupdate_note_with_new_content_creates_revision(self):
        """Supplying *new_content* should create a new revision and update the note."""
        new_content = "Updated note content version 2"
        revision = await aupdate_document_note(
            note_id=self.note.id,
            new_content=new_content,
            author_id=self.user.id,
        )

        # A revision is returned with incremented version.
        self.assertIsNotNone(revision)
        self.assertEqual(revision.version, 2)  # First update after initial creation

        # The note content is updated - fetch asynchronously
        note = await self._get_note_async(self.note.id)
        self.assertEqual(note.content, new_content)

    async def test_aupdate_note_with_diff_text_creates_revision(self):
        """Providing *diff_text* instead of full content should also work."""
        import difflib

        original_content = self.note.content
        new_content = original_content + "\nAnother paragraph added."

        diff_text = "".join(
            difflib.ndiff(
                original_content.splitlines(keepends=True),
                new_content.splitlines(keepends=True),
            )
        )

        revision = await aupdate_document_note(
            note_id=self.note.id,
            diff_text=diff_text,
            author_id=self.user.id,
        )

        self.assertIsNotNone(revision)
        self.assertEqual(revision.version, 2)

        # Fetch note asynchronously
        note = await self._get_note_async(self.note.id)
        self.assertIn("Another paragraph added.", note.content)

    async def test_aupdate_note_no_change_returns_none(self):
        """Supplying identical content should early-exit and return *None*."""
        result = await aupdate_document_note(
            note_id=self.note.id,
            new_content=self.note.content,
            author_id=self.user.id,
        )
        self.assertIsNone(result)

    async def test_aupdate_note_tracks_author(self):
        """The revision should track the author who made the change."""
        revision = await aupdate_document_note(
            note_id=self.note.id,
            new_content="Content changed by specific author",
            author_id=self.user.id,
        )

        self.assertEqual(revision.author_id, self.user.id)

    async def test_aupdate_note_snapshot_interval(self):
        """Test snapshot creation at interval boundaries (every 10 revisions)."""
        # Note already has version 1 from creation
        # Create revisions 2-9
        for i in range(2, 10):
            await aupdate_document_note(
                note_id=self.note.id,
                new_content=f"Note version {i}",
                author_id=self.user.id,
            )

        # Version 10 should trigger a snapshot
        final_content = "Note version 10 with snapshot"
        revision = await aupdate_document_note(
            note_id=self.note.id,
            new_content=final_content,
            author_id=self.user.id,
        )

        self.assertEqual(revision.version, 10)
        self.assertIsNotNone(revision.snapshot)
        self.assertEqual(revision.snapshot, final_content)

    async def test_aupdate_note_stores_checksums(self):
        """Revisions should store SHA-256 checksums of base and full content."""
        import hashlib

        original_content = self.note.content
        new_content = "Content with verifiable checksums"

        revision = await aupdate_document_note(
            note_id=self.note.id,
            new_content=new_content,
            author_id=self.user.id,
        )

        expected_base_checksum = hashlib.sha256(original_content.encode()).hexdigest()
        expected_full_checksum = hashlib.sha256(new_content.encode()).hexdigest()

        self.assertEqual(revision.checksum_base, expected_base_checksum)
        self.assertEqual(revision.checksum_full, expected_full_checksum)

    # ------------------------------------------------------------------
    # Failure / validation paths
    # ------------------------------------------------------------------

    async def test_aupdate_note_missing_content_raises(self):
        """Neither *new_content* nor *diff_text* provided – expect ``ValueError``."""
        with self.assertRaisesRegex(
            ValueError, "Provide either new_content or diff_text"
        ):
            await aupdate_document_note(
                note_id=self.note.id,
                author_id=self.user.id,
            )

    async def test_aupdate_note_both_content_and_diff_raise(self):
        """Supplying both *new_content* and *diff_text* is forbidden."""
        with self.assertRaisesRegex(
            ValueError, "Provide only one of new_content or diff_text"
        ):
            await aupdate_document_note(
                note_id=self.note.id,
                new_content="foo",
                diff_text="bar",
                author_id=self.user.id,
            )

    async def test_aupdate_note_invalid_note_raises(self):
        """Non-existent note id should raise a clear ``ValueError``."""
        with self.assertRaisesRegex(ValueError, "Note with id=999999 does not exist"):
            await aupdate_document_note(
                note_id=999999,
                new_content="foo",
                author_id=self.user.id,
            )

    async def test_aupdate_note_preserves_diff_in_revision(self):
        """The revision should store a proper unified diff."""
        original_content = self.note.content
        new_content = "Completely different content"

        revision = await aupdate_document_note(
            note_id=self.note.id,
            new_content=new_content,
            author_id=self.user.id,
        )

        # The diff should contain both old and new content indicators
        self.assertIn("-", revision.diff)  # Removed lines
        self.assertIn("+", revision.diff)  # Added lines
        self.assertIn(original_content, revision.diff)
        self.assertIn(new_content, revision.diff)


class AsyncTestSearchDocumentNotes(TransactionTestCase):
    """Async tests ensuring :func:`asearch_document_notes` behaves correctly."""

    def setUp(self):  # noqa: D401 – simple helper, not public API
        """Prepare test data with multiple notes for searching."""
        self.user = User.objects.create_user(
            username="async_search_user", password="pw"
        )
        self.doc = Document.objects.create(
            creator=self.user,
            title="Test Document for Search",
            description="Test Description",
        )

        self.corpus = Corpus.objects.create(
            title="Search Test Corpus",
            creator=self.user,
        )
        self.corpus.add_document(document=self.doc, user=self.user)

        # Create multiple notes with different content for testing
        self.note1 = Note.objects.create(
            document=self.doc,
            corpus=self.corpus,
            title="Python Programming Guide",
            content="This note covers Python basics and advanced features",
            creator=self.user,
        )

        self.note2 = Note.objects.create(
            document=self.doc,
            corpus=self.corpus,
            title="JavaScript Tutorial",
            content="Learn JavaScript programming with practical examples",
            creator=self.user,
        )

        self.note3 = Note.objects.create(
            document=self.doc,
            corpus=self.corpus,
            title="Data Science with Python",
            content="Using Python for data analysis and machine learning",
            creator=self.user,
        )

        # Note without corpus
        self.note4 = Note.objects.create(
            document=self.doc,
            corpus=None,
            title="General Note",
            content="This is a general note about programming",
            creator=self.user,
        )

    async def _get_note_async(self, note_id):
        """Helper to fetch a note asynchronously."""
        from channels.db import database_sync_to_async

        return await database_sync_to_async(Note.objects.get)(pk=note_id)

    # ------------------------------------------------------------------
    # Success paths
    # ------------------------------------------------------------------

    async def test_asearch_notes_by_title(self):
        """Search should find notes matching title text."""
        results = await asearch_document_notes(
            document_id=self.doc.id,
            search_term="Python",
        )

        # Should find notes 1 and 3 which have "Python" in title
        self.assertEqual(len(results), 2)
        note_ids = {r["id"] for r in results}
        self.assertIn(self.note1.id, note_ids)
        self.assertIn(self.note3.id, note_ids)

    async def test_asearch_notes_by_content(self):
        """Search should find notes matching content text."""
        results = await asearch_document_notes(
            document_id=self.doc.id,
            search_term="JavaScript",
        )

        # Should find only note 2 which has "JavaScript" in title/content
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], self.note2.id)

    async def test_asearch_notes_case_insensitive(self):
        """Search should be case-insensitive."""
        results = await asearch_document_notes(
            document_id=self.doc.id,
            search_term="PYTHON",
        )

        # Should still find notes with "Python" despite case difference
        self.assertEqual(len(results), 2)

    async def test_asearch_notes_with_corpus_filter(self):
        """Search should respect corpus filter when provided."""
        # First check without corpus filter
        all_results = await asearch_document_notes(
            document_id=self.doc.id,
            search_term="note",
        )

        # Then with corpus filter
        corpus_results = await asearch_document_notes(
            document_id=self.doc.id,
            search_term="note",
            corpus_id=self.corpus.id,
        )

        # Should have fewer results with corpus filter (note4 has no corpus)
        self.assertLess(len(corpus_results), len(all_results))
        # All corpus results should belong to the corpus
        for result in corpus_results:
            note = await self._get_note_async(result["id"])
            self.assertEqual(note.corpus_id, self.corpus.id)

    async def test_asearch_notes_with_limit(self):
        """Search should respect limit parameter."""
        results = await asearch_document_notes(
            document_id=self.doc.id,
            search_term="Python",
            limit=1,
        )

        # Should only return 1 result despite 2 matches
        self.assertEqual(len(results), 1)

    async def test_asearch_notes_result_format(self):
        """Search results should have correct format."""
        results = await asearch_document_notes(
            document_id=self.doc.id,
            search_term="Python",
            limit=1,
        )

        result = results[0]
        # Check all expected fields are present
        self.assertIn("id", result)
        self.assertIn("title", result)
        self.assertIn("content", result)
        self.assertIn("creator_id", result)
        self.assertIn("created", result)
        self.assertIn("modified", result)

        # Check types
        self.assertIsInstance(result["id"], int)
        self.assertIsInstance(result["title"], str)
        self.assertIsInstance(result["content"], str)
        self.assertIsInstance(result["creator_id"], int)
        self.assertIsInstance(result["created"], str)  # ISO format string
        self.assertIsInstance(result["modified"], str)  # ISO format string

    async def test_asearch_notes_ordered_by_modified(self):
        """Results should be ordered by modified date descending."""
        # Get all notes to check ordering
        results = await asearch_document_notes(
            document_id=self.doc.id,
            search_term="note",  # All notes have "note" in title or content
        )

        # Check that results are ordered by modified date descending
        for i in range(len(results) - 1):
            # Each result's modified date should be >= the next one
            self.assertGreaterEqual(results[i]["modified"], results[i + 1]["modified"])

    async def test_asearch_notes_no_results(self):
        """Search with no matches should return empty list."""
        results = await asearch_document_notes(
            document_id=self.doc.id,
            search_term="NonexistentTerm",
        )

        self.assertEqual(results, [])

    # ------------------------------------------------------------------
    # Failure paths
    # ------------------------------------------------------------------

    async def test_asearch_notes_invalid_document(self):
        """Search for non-existent document should raise ValueError."""
        with self.assertRaisesRegex(
            ValueError, "Document with id=999999 does not exist"
        ):
            await asearch_document_notes(
                document_id=999999,
                search_term="test",
            )

    async def test_asearch_notes_empty_search_term(self):
        """Empty search term with icontains matches all records."""
        results = await asearch_document_notes(
            document_id=self.doc.id,
            search_term="",
        )

        # Empty string with icontains matches everything
        # Should return all 4 notes for this document
        self.assertEqual(len(results), 4)


# ------------------------------------------------------------------
# Tests for async document summary helpers
# ------------------------------------------------------------------


class AsyncTestDocumentSummary(TransactionTestCase):
    """Async tests for document summary functions."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username="async_summary_user", password="pw"
        )
        self.corpus = Corpus.objects.create(
            title="Async Summary Corpus",
            creator=self.user,
        )
        self.doc = Document.objects.create(
            creator=self.user,
            title="Async Summary Document",
            description="Test Description",
        )
        self.corpus.add_document(document=self.doc, user=self.user)

    async def _update_summary_async(self, document, new_content, author, corpus):
        """Helper to update document summary asynchronously."""
        from channels.db import database_sync_to_async

        return await database_sync_to_async(document.update_summary)(
            new_content=new_content, author=author, corpus=corpus
        )

    async def test_aget_document_summary(self):
        """Test async document summary retrieval."""
        from opencontractserver.llms.tools.core_tools import aget_document_summary

        # Create summary first using async helper
        await self._update_summary_async(
            self.doc,
            new_content="Async test summary content",
            author=self.user,
            corpus=self.corpus,
        )

        # Test retrieval
        result = await aget_document_summary(self.doc.id, self.corpus.id)
        self.assertEqual(result, "Async test summary content")

        # Test truncation
        result = await aget_document_summary(
            self.doc.id, self.corpus.id, truncate_length=10, from_start=True
        )
        self.assertEqual(result, "Async test")

    async def test_aget_document_summary_versions(self):
        """Test async version history retrieval."""
        from opencontractserver.llms.tools.core_tools import (
            aget_document_summary_versions,
        )

        # Create versions using async helper
        for i in range(1, 4):
            await self._update_summary_async(
                self.doc,
                new_content=f"Async version {i}",
                author=self.user,
                corpus=self.corpus,
            )

        versions = await aget_document_summary_versions(self.doc.id, self.corpus.id)
        self.assertEqual(len(versions), 3)
        self.assertEqual(versions[0]["version"], 3)

    async def test_aget_document_summary_diff(self):
        """Test async diff retrieval between versions."""
        from opencontractserver.llms.tools.core_tools import aget_document_summary_diff

        # Create two versions using async helper
        await self._update_summary_async(
            self.doc,
            new_content="Original async content",
            author=self.user,
            corpus=self.corpus,
        )
        await self._update_summary_async(
            self.doc,
            new_content="Modified async content",
            author=self.user,
            corpus=self.corpus,
        )

        diff_info = await aget_document_summary_diff(
            self.doc.id, self.corpus.id, from_version=1, to_version=2
        )

        self.assertEqual(diff_info["from_version"], 1)
        self.assertEqual(diff_info["to_version"], 2)
        self.assertIn("-Original", diff_info["diff"])
        self.assertIn("+Modified", diff_info["diff"])

    async def test_aupdate_document_summary(self):
        """Test async document summary update."""
        from opencontractserver.llms.tools.core_tools import aupdate_document_summary

        result = await aupdate_document_summary(
            document_id=self.doc.id,
            corpus_id=self.corpus.id,
            new_content="New async summary",
            author_id=self.user.id,
        )

        self.assertTrue(result["created"])
        self.assertEqual(result["version"], 1)

        # Test no change
        result = await aupdate_document_summary(
            document_id=self.doc.id,
            corpus_id=self.corpus.id,
            new_content="New async summary",  # Same content
            author_id=self.user.id,
        )

        self.assertFalse(result["created"])
        self.assertEqual(result["message"], "No change in content")

    async def test_aget_document_summary_at_version(self):
        """Test async retrieval of specific version."""
        from opencontractserver.llms.tools.core_tools import (
            aget_document_summary_at_version,
        )

        # Create specific version using async helper
        await self._update_summary_async(
            self.doc,
            new_content="Version 1 specific content",
            author=self.user,
            corpus=self.corpus,
        )

        result = await aget_document_summary_at_version(
            self.doc.id, self.corpus.id, version=1
        )
        self.assertEqual(result, "Version 1 specific content")


class AsyncTestSearchExactTextAsSources(TransactionTestCase):
    """Async tests for search_exact_text_as_sources function."""

    @classmethod
    def setUpClass(cls):
        """Disconnect document processing signals to avoid triggering ingestion."""
        from django.db.models.signals import post_save

        from opencontractserver.documents.signals import (
            DOC_CREATE_UID,
            process_doc_on_create_atomic,
        )

        # Disconnect signals BEFORE calling super().setUpClass()
        # Document is already imported at module level
        post_save.disconnect(
            process_doc_on_create_atomic, sender=Document, dispatch_uid=DOC_CREATE_UID
        )

        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        """Reconnect document processing signals."""
        try:
            super().tearDownClass()
        finally:
            from django.db.models.signals import post_save

            from opencontractserver.documents.signals import (
                DOC_CREATE_UID,
                process_doc_on_create_atomic,
            )

            # Reconnect signals in finally block to ensure it happens even if teardown fails
            # Document is already imported at module level
            post_save.connect(
                process_doc_on_create_atomic,
                sender=Document,
                dispatch_uid=DOC_CREATE_UID,
            )

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username="async_search_text_user", password="pw"
        )
        self.corpus = Corpus.objects.create(
            title="Async Search Text Corpus",
            creator=self.user,
        )

        # Create text document
        self.text_doc = Document.objects.create(
            creator=self.user,
            title="Async Text Document",
            description="Test Text",
            file_type="text/plain",
        )

        # Create mock text content with multiple search targets
        self.text_content = (
            "This is a sample document with covenants and agreements. "
            "The covenants are important legal terms. "
            "Multiple agreements exist in this document."
        )
        self.text_doc.txt_extract_file.save(
            "async_text_extract.txt", ContentFile(self.text_content.encode())
        )

        self.corpus.add_document(document=self.text_doc, user=self.user)

        # Create document with unsupported file type (for testing error handling)
        self.unsupported_doc = Document.objects.create(
            creator=self.user,
            title="Unsupported Document",
            description="Test",
            file_type="application/unsupported",
        )

        # Create document without txt_extract_file (for testing error handling)
        self.no_extract_doc = Document.objects.create(
            creator=self.user,
            title="No Extract Document",
            description="Test",
            file_type="text/plain",
        )

    async def test_asearch_exact_text_single_match(self):
        """Test async search with a single search string."""
        search_strings = ["covenants and agreements"]

        results = await asearch_exact_text_as_sources(
            document_id=self.text_doc.id,
            search_strings=search_strings,
            corpus_id=self.corpus.id,
        )

        # Should find exactly one match
        self.assertEqual(len(results), 1)

        # Verify SourceNode structure
        result = results[0]
        self.assertIsInstance(result, SourceNode)
        self.assertEqual(result.content, "covenants and agreements")
        self.assertEqual(result.similarity_score, 1.0)

        # Verify metadata
        self.assertEqual(result.metadata["document_id"], self.text_doc.id)
        self.assertEqual(result.metadata["corpus_id"], self.corpus.id)
        self.assertEqual(result.metadata["page"], 1)
        self.assertEqual(result.metadata["search_string"], "covenants and agreements")
        self.assertEqual(result.metadata["match_type"], "exact_text_plain")
        self.assertIn("char_start", result.metadata)
        self.assertIn("char_end", result.metadata)

        # Verify synthetic negative ID
        self.assertLess(result.annotation_id, 0)

    async def test_asearch_exact_text_multiple_occurrences(self):
        """Test async search finding multiple occurrences of same string."""
        # "covenants" appears twice in our text content
        search_strings = ["covenants"]

        results = await asearch_exact_text_as_sources(
            document_id=self.text_doc.id,
            search_strings=search_strings,
            corpus_id=self.corpus.id,
        )

        # Should find two matches
        self.assertEqual(len(results), 2)

        # All should be SourceNode objects with same content
        for result in results:
            self.assertIsInstance(result, SourceNode)
            self.assertEqual(result.content, "covenants")
            self.assertEqual(result.similarity_score, 1.0)

        # Each should have unique char_start position
        char_starts = [r.metadata["char_start"] for r in results]
        self.assertEqual(len(set(char_starts)), 2)  # All unique

    async def test_asearch_exact_text_multiple_strings(self):
        """Test async search with multiple different search strings."""
        search_strings = ["covenants", "agreements", "legal"]

        results = await asearch_exact_text_as_sources(
            document_id=self.text_doc.id,
            search_strings=search_strings,
            corpus_id=self.corpus.id,
        )

        # Should find: 2 covenants + 2 agreements + 1 legal = 5 total
        self.assertEqual(len(results), 5)

        # Verify we got results for each search string
        found_strings = {r.metadata["search_string"] for r in results}
        self.assertEqual(found_strings, {"covenants", "agreements", "legal"})

    async def test_asearch_exact_text_no_matches(self):
        """Test async search with no matches."""
        search_strings = ["NonexistentString12345"]

        results = await asearch_exact_text_as_sources(
            document_id=self.text_doc.id,
            search_strings=search_strings,
            corpus_id=self.corpus.id,
        )

        self.assertEqual(len(results), 0)

    async def test_asearch_exact_text_empty_search_list(self):
        """Test async search with empty search string list."""
        search_strings = []

        results = await asearch_exact_text_as_sources(
            document_id=self.text_doc.id,
            search_strings=search_strings,
            corpus_id=self.corpus.id,
        )

        self.assertEqual(len(results), 0)

    async def test_asearch_exact_text_case_sensitive(self):
        """Test that search is case-sensitive (finds exact matches only)."""
        # Our text has "covenants" (lowercase)
        search_strings = ["Covenants"]  # Capital C

        results = await asearch_exact_text_as_sources(
            document_id=self.text_doc.id,
            search_strings=search_strings,
            corpus_id=self.corpus.id,
        )

        # Should find no matches because it's case-sensitive
        self.assertEqual(len(results), 0)

    async def test_asearch_exact_text_invalid_document(self):
        """Test async search with non-existent document."""
        with self.assertRaisesRegex(ValueError, "Document id=999999 does not exist"):
            await asearch_exact_text_as_sources(
                document_id=999999,
                search_strings=["test"],
                corpus_id=self.corpus.id,
            )

    async def test_asearch_exact_text_unsupported_file_type(self):
        """Test async search with unsupported file type."""
        # Use the unsupported_doc created in setUp
        with self.assertRaisesRegex(
            ValueError, "Unsupported file_type .* for document"
        ):
            await asearch_exact_text_as_sources(
                document_id=self.unsupported_doc.id,
                search_strings=["test"],
                corpus_id=self.corpus.id,
            )

    async def test_asearch_exact_text_text_document_no_extract_file(self):
        """Test async search with text document that has no txt_extract_file."""
        # Use the no_extract_doc created in setUp (which has no txt_extract_file)
        with self.assertRaisesRegex(
            ValueError, "lacks txt_extract_file; cannot search"
        ):
            await asearch_exact_text_as_sources(
                document_id=self.no_extract_doc.id,
                search_strings=["test"],
                corpus_id=self.corpus.id,
            )

    async def test_asearch_exact_text_without_corpus_id(self):
        """Test async search without providing corpus_id."""
        search_strings = ["sample"]

        results = await asearch_exact_text_as_sources(
            document_id=self.text_doc.id,
            search_strings=search_strings,
            corpus_id=None,  # No corpus provided
        )

        # Should still work, just without corpus_id in metadata
        self.assertGreater(len(results), 0)
        self.assertIsNone(results[0].metadata["corpus_id"])

    async def test_asearch_exact_text_source_node_format(self):
        """Test that async search returns properly formatted SourceNode objects."""
        search_strings = ["document"]

        results = await asearch_exact_text_as_sources(
            document_id=self.text_doc.id,
            search_strings=search_strings,
            corpus_id=self.corpus.id,
        )

        self.assertGreater(len(results), 0)

        result = results[0]
        # Test SourceNode fields
        self.assertIsInstance(result.annotation_id, int)
        self.assertLess(result.annotation_id, 0)  # Synthetic negative ID
        self.assertIsInstance(result.content, str)
        self.assertIsInstance(result.similarity_score, float)
        self.assertEqual(result.similarity_score, 1.0)
        self.assertIsInstance(result.metadata, dict)

        # Test metadata fields for text documents
        required_keys = {
            "document_id",
            "corpus_id",
            "page",
            "search_string",
            "char_start",
            "char_end",
            "match_type",
        }
        self.assertTrue(required_keys.issubset(result.metadata.keys()))

    async def test_asearch_exact_text_unique_annotation_ids(self):
        """Test that each match gets a unique synthetic annotation_id."""
        # Search for string that appears multiple times
        search_strings = ["covenants", "agreements"]

        results = await asearch_exact_text_as_sources(
            document_id=self.text_doc.id,
            search_strings=search_strings,
            corpus_id=self.corpus.id,
        )

        # Get all annotation IDs
        annotation_ids = [r.annotation_id for r in results]

        # All should be unique
        self.assertEqual(len(annotation_ids), len(set(annotation_ids)))

        # All should be negative
        self.assertTrue(all(aid < 0 for aid in annotation_ids))
