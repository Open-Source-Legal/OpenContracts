import json
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings

from opencontractserver.annotations.models import Annotation, AnnotationLabel, Note
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.llms.tools.core_tools import (
    aget_md_summary_token_length,
    aget_note_content_token_length,
    aget_notes_for_document_corpus,
    aget_partial_note_content,
    aload_document_md_summary,
    get_note_content_token_length,
    get_partial_note_content,
)
from opencontractserver.tasks.data_extract_tasks import annotation_window, text_search
from opencontractserver.types.dicts import PawlsTokenPythonType

User = get_user_model()


def create_mock_pawls_content(text: str) -> str:
    """Create a mock PAWLS parse file content with the given text."""
    # Split text into words to create tokens
    words = text.split()
    tokens: list[PawlsTokenPythonType] = []
    x_pos = 0
    for word in words:
        token: PawlsTokenPythonType = {
            "x": x_pos,
            "y": 0,
            "width": len(word) * 10,  # Rough approximation
            "height": 10,
            "text": word,
        }
        tokens.append(token)
        x_pos += len(word) * 10 + 5  # Add space between words

    pawls_content = [
        {"page": {"width": 800, "height": 1000, "index": 1}, "tokens": tokens}
    ]
    return json.dumps(pawls_content)


@pytest.mark.django_db
@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        },
    },
    MEDIA_ROOT="test_media/",
)
class TestDataExtractTasks(TestCase):
    """Test cases for data extraction task functions."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(username="testuser", password="testpass")

        # This is the text we use for the PDF doc
        self.pdf_content = "This is a test document with some sample text ..."

        # Create the actual pawls JSON for the PDF
        pawls_content = create_mock_pawls_content(self.pdf_content)

        self.pdf_doc = Document.objects.create(
            title="Test PDF Document",
            creator=self.user,
            file_type="application/pdf",
            pawls_parse_file=ContentFile(pawls_content, name="test_pawls.json"),
        )

        # Make sure the text doc's content matches the annotation's raw_text:
        text_doc_content = "Test text annotation"
        self.txt_doc = Document.objects.create(
            title="Test Text Document",
            creator=self.user,
            file_type="text/plain",
            txt_extract_file=ContentFile(text_doc_content, name="test.txt"),
        )

        self.label = AnnotationLabel.objects.create(
            text="Test Label",
            creator=self.user,
        )

        # Create test structural annotations
        self.structural_annotation = Annotation.objects.create(
            document=self.pdf_doc,
            annotation_label=self.label,
            raw_text="This is a test structural annotation",
            page=1,
            structural=True,
            creator=self.user,
        )

        self.structural_annotation_2 = Annotation.objects.create(
            document=self.pdf_doc,
            annotation_label=self.label,
            raw_text="Another test structural annotation",
            page=2,
            structural=True,
            creator=self.user,
        )

        # Create test regular annotations with proper PAWLS format
        self.pdf_annotation = Annotation.objects.create(
            document=self.pdf_doc,
            annotation_label=self.label,
            raw_text="test document with some",  # part of self.pdf_content
            page=1,
            json={
                "1": {
                    "bounds": {"top": 0, "bottom": 10, "left": 20, "right": 100},
                    "tokensJsons": [
                        {"pageIndex": 1, "tokenIndex": i} for i in range(3, 6)
                    ],
                    "rawText": "test document with some",
                }
            },
            creator=self.user,
        )

        self.txt_annotation = Annotation.objects.create(
            document=self.txt_doc,
            annotation_label=self.label,
            raw_text="Test text annotation",
            page=1,
            json={"start": 0, "end": 19},
            creator=self.user,
        )

    @patch("opencontractserver.tasks.data_extract_tasks.os.path.exists")
    def test_text_search_finds_structural_annotations(self, mock_exists):
        """Test that text_search finds structural annotations containing the query."""
        mock_exists.return_value = True
        result = text_search(self.pdf_doc.id, "test structural")
        self.assertIn("This is a test structural annotation", result)
        self.assertIn("Another test structural annotation", result)

    @patch("opencontractserver.tasks.data_extract_tasks.os.path.exists")
    def test_text_search_case_insensitive(self, mock_exists):
        """Test that text_search is case insensitive."""
        mock_exists.return_value = True
        result = text_search(self.pdf_doc.id, "TEST STRUCTURAL")
        self.assertIn("This is a test structural annotation", result)

    @patch("opencontractserver.tasks.data_extract_tasks.os.path.exists")
    def test_text_search_no_matches(self, mock_exists):
        """Test text_search when no matches are found."""
        mock_exists.return_value = True
        result = text_search(self.pdf_doc.id, "nonexistent text")
        self.assertEqual(result, "No structural annotations matched your text_search.")

    @patch("opencontractserver.tasks.data_extract_tasks.os.path.exists")
    def test_text_search_limit_three_results(self, mock_exists):
        """Test that text_search returns at most 3 results."""
        mock_exists.return_value = True
        # Create more than 3 matching annotations
        for i in range(4):
            Annotation.objects.create(
                document=self.pdf_doc,
                annotation_label=self.label,
                raw_text=f"Test structural annotation {i}",
                page=1,
                structural=True,
                creator=self.user,
            )

        result = text_search(self.pdf_doc.id, "Test structural")
        matches = result.count("\n") + 1  # Count newlines + 1 for the last line
        self.assertEqual(matches, 3)

    @patch("opencontractserver.tasks.data_extract_tasks.os.path.exists")
    def test_annotation_window_pdf(self, mock_exists):
        """
        Patch open() so that reading doc.pawls_parse_file.path gives us valid JSON
        from create_mock_pawls_content, enabling JSON parsing and text snippet retrieval.
        """
        mock_exists.return_value = True
        pawls_json = create_mock_pawls_content(self.pdf_content)

        with patch("builtins.open", create=True) as mock_open:
            mock_open.return_value.__enter__.return_value.read.return_value = pawls_json
            result = annotation_window(
                self.pdf_doc.id, str(self.pdf_annotation.id), "5"
            )

            self.assertIsNotNone(result)
            # We expect 'test document with some' in snippet
            self.assertIn("test document with some", result)
            # Possibly also expect words before/after if the window is big enough
            self.assertIn("This is a test document", result)

    @patch("opencontractserver.tasks.data_extract_tasks.os.path.exists")
    def test_annotation_window_text(self, mock_exists):
        """
        The doc's text is now 'Test text annotation' (which is 19 chars long).
        So annotation_window should slice [0:19].
        """
        mock_exists.return_value = True

        with patch("builtins.open", create=True) as mock_open:
            # Return the same text that we stored in setUp
            mock_open.return_value.__enter__.return_value.read.return_value = (
                "Test text annotation"
            )
            result = annotation_window(
                self.txt_doc.id, str(self.txt_annotation.id), "5"
            )

            self.assertIsNotNone(result)
            # Now it should indeed contain the raw_text
            self.assertIn("Test text annotation", result)

    @patch("opencontractserver.tasks.data_extract_tasks.os.path.exists")
    def test_annotation_window_invalid_window_size(self, mock_exists):
        """Test annotation_window with invalid window size."""
        mock_exists.return_value = True
        result = annotation_window(
            self.pdf_doc.id, str(self.pdf_annotation.id), "invalid"
        )
        self.assertEqual(result, "Error: Could not parse window_size as an integer.")

    @patch("opencontractserver.tasks.data_extract_tasks.os.path.exists")
    def test_annotation_window_nonexistent_annotation(self, mock_exists):
        """Test annotation_window with nonexistent annotation ID."""
        mock_exists.return_value = True
        result = annotation_window(self.pdf_doc.id, "99999", "5")
        self.assertEqual(result, "Error: Annotation [99999] not found.")

    @patch("opencontractserver.tasks.data_extract_tasks.os.path.exists")
    def test_annotation_window_size_limit(self, mock_exists):
        """Test that annotation_window respects the maximum window size."""
        mock_exists.return_value = True
        # Create a long text with 2000 words
        long_text = " ".join(["word"] * 2000)
        with patch("builtins.open", create=True) as mock_open:
            mock_open.return_value.__enter__.return_value.read.return_value = long_text
            result = annotation_window(
                self.pdf_doc.id, str(self.pdf_annotation.id), "1000"
            )
            # Should be clamped to 500 words on each side
            self.assertIsNotNone(result)
            # Count words in result
            word_count = len(result.split())
            self.assertLessEqual(word_count, 1000)

    def tearDown(self):
        """Clean up test data."""
        Annotation.objects.all().delete()
        Document.objects.all().delete()
        AnnotationLabel.objects.all().delete()
        User.objects.all().delete()

    # Additional tests for core_tools functions will be inserted below


# ---------------------------------------------------------------------------
# Additional tests for opencontractserver.llms.tools.core_tools
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        },
    },
    MEDIA_ROOT="test_media/",
)
class TestCoreTools(TestCase):
    """Tests for synchronous helper functions in core_tools.py."""

    def setUp(self):
        """Create user, document with markdown summary, corpus, and notes"""
        self.user = User.objects.create_user(username="coretools", password="pass")

        # Markdown summary content for the document
        self.md_summary_content = "Markdown summary for testing purposes."

        # Document with an attached md_summary_file (sync functions expect this)
        self.doc = Document.objects.create(
            title="Markdown Doc",
            creator=self.user,
            file_type="text/markdown",
            md_summary_file=ContentFile(self.md_summary_content, name="summary.md"),
        )

        # Optional corpus used for corpus-filtered note retrieval
        self.corpus = Corpus.objects.create(title="Test Corpus", creator=self.user)

        # Notes – one without corpus and one with corpus
        self.note1_content = "This is a note on the document."
        self.note1 = Note.objects.create(
            title="Note 1",
            content=self.note1_content,
            document=self.doc,
            creator=self.user,
        )

        self.note2_content = "Another note belonging to corpus."
        self.note2 = Note.objects.create(
            title="Note 2",
            content=self.note2_content,
            document=self.doc,
            corpus=self.corpus,
            creator=self.user,
        )

    # ---------------------------------------------------------------------
    # get_note_content_token_length
    # ---------------------------------------------------------------------
    def test_get_note_content_token_length(self):
        """Should return correct whitespace token count for a note."""
        expected = len(self.note1_content.split())
        result = get_note_content_token_length(self.note1.id)
        self.assertEqual(result, expected)

        # Invalid ID should raise ValueError
        with self.assertRaises(ValueError):
            get_note_content_token_length(999_999)

    # ---------------------------------------------------------------------
    # get_partial_note_content
    # ---------------------------------------------------------------------
    def test_get_partial_note_content(self):
        """Should return the specified substring and validate indices."""
        start, end = 5, 15
        expected_substring = self.note1_content[start:end]
        result = get_partial_note_content(self.note1.id, start, end)
        self.assertEqual(result, expected_substring)

        # Non-existent note should raise
        with self.assertRaises(ValueError):
            get_partial_note_content(999_999, 0, 10)

        # end < start should raise
        with self.assertRaises(ValueError):
            get_partial_note_content(self.note1.id, 10, 5)

    def tearDown(self):
        """Clean up created objects."""
        Note.objects.all().delete()
        Corpus.objects.all().delete()
        Document.objects.all().delete()
        User.objects.all().delete()

    # ---------------------------------------------------------------------
    # Asynchronous tests for core_tools async helpers
    # ---------------------------------------------------------------------

    @override_settings(
        STORAGES={
            "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
            "staticfiles": {
                "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
            },
        },
        MEDIA_ROOT="test_media/",
    )
    async def test_async_md_summary_helpers(self):
        """Test aget_md_summary_token_length and aload_document_md_summary."""
        user = await User.objects.acreate(username="asyncuser", password="pass")

        md_summary_text = "Async markdown summary file content for testing."
        doc = await Document.objects.acreate(
            title="Async Doc",
            creator=user,
            file_type="text/markdown",
            md_summary_file=ContentFile(md_summary_text, name="async_summary.md"),
        )

        # ---------------------------------------------------------------------
        # aget_md_summary_token_length returns correct token count
        # ---------------------------------------------------------------------
        expected_tokens = len(md_summary_text.split())
        token_length = await aget_md_summary_token_length(doc.id)
        self.assertEqual(token_length, expected_tokens)

        # ---------------------------------------------------------------------
        # aload_document_md_summary with truncation (start)
        # ---------------------------------------------------------------------
        first_ten_chars = md_summary_text[:10]
        loaded_start = await aload_document_md_summary(
            doc.id, truncate_length=10, from_start=True
        )
        self.assertEqual(loaded_start, first_ten_chars)

        # ---------------------------------------------------------------------
        # aload_document_md_summary with truncation (end)
        # ---------------------------------------------------------------------
        last_ten_chars = md_summary_text[-10:]
        loaded_end = await aload_document_md_summary(
            doc.id, truncate_length=10, from_start=False
        )
        self.assertEqual(loaded_end, last_ten_chars)

        # ---------------------------------------------------------------------
        # Invalid document ID should raise
        # ---------------------------------------------------------------------
        with self.assertRaises(ValueError):
            await aget_md_summary_token_length(999_999)

    @override_settings(
        STORAGES={
            "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
            "staticfiles": {
                "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
            },
        },
        MEDIA_ROOT="test_media/",
    )
    async def test_aget_notes_for_document_corpus(self):
        """Test asynchronous retrieval of notes with and without corpus filter."""
        user = await User.objects.acreate(username="notecorpus", password="pass")

        # Create document and corpus
        doc = await Document.objects.acreate(
            title="Doc for Notes",
            creator=user,
            file_type="text/plain",
            txt_extract_file=ContentFile("", name="placeholder.txt"),
        )
        corpus = await Corpus.objects.acreate(title="Corpus A", creator=user)

        # Create notes – one with corpus, one without
        note_no_corpus = await Note.objects.acreate(
            title="Loose Note",
            content="Unlinked to corpus",
            document=doc,
            creator=user,
        )

        note_with_corpus = await Note.objects.acreate(
            title="Linked Note",
            content="Linked to corpus",
            document=doc,
            corpus=corpus,
            creator=user,
        )

        # ---------------------------------------------------------------------
        # Without corpus filter – expect both notes
        # ---------------------------------------------------------------------
        all_notes = await aget_notes_for_document_corpus(doc.id)
        self.assertEqual(
            {n["id"] for n in all_notes}, {note_no_corpus.id, note_with_corpus.id}
        )

        # ---------------------------------------------------------------------
        # With corpus filter – expect only the linked note
        # ---------------------------------------------------------------------
        filtered_notes = await aget_notes_for_document_corpus(
            doc.id, corpus_id=corpus.id
        )
        self.assertEqual(len(filtered_notes), 1)
        self.assertEqual(filtered_notes[0]["id"], note_with_corpus.id)

        # Non-existent document raises ValueError
        with self.assertRaises(ValueError):
            await aget_notes_for_document_corpus(999_999)

    async def test_aget_note_content_token_length(self):
        """Test async note content token length calculation."""
        user = await User.objects.acreate(username="tokenuser", password="pass")
        doc = await Document.objects.acreate(
            title="Doc for token len",
            creator=user,
            file_type="text/plain",
        )
        note = await Note.objects.acreate(
            title="Token Note",
            content="one two three four five",
            document=doc,
            creator=user,
        )

        result = await aget_note_content_token_length(note.id)
        self.assertEqual(result, 5)

        # Empty content returns 0
        empty_note = await Note.objects.acreate(
            title="Empty Note",
            content="",
            document=doc,
            creator=user,
        )
        self.assertEqual(await aget_note_content_token_length(empty_note.id), 0)

        # Non-existent note raises ValueError
        with self.assertRaises(ValueError):
            await aget_note_content_token_length(999_999)

    async def test_aget_partial_note_content(self):
        """Test async partial note content retrieval."""
        user = await User.objects.acreate(username="partialuser", password="pass")
        doc = await Document.objects.acreate(
            title="Doc for partial",
            creator=user,
            file_type="text/plain",
        )
        note = await Note.objects.acreate(
            title="Partial Note",
            content="Hello, this is a test note with some content.",
            document=doc,
            creator=user,
        )

        # Default slice (0:500)
        result = await aget_partial_note_content(note.id)
        self.assertEqual(result, "Hello, this is a test note with some content.")

        # Custom slice
        result = await aget_partial_note_content(note.id, start=0, end=5)
        self.assertEqual(result, "Hello")

        # Negative start clamped to 0
        result = await aget_partial_note_content(note.id, start=-10, end=5)
        self.assertEqual(result, "Hello")

        # end < start raises ValueError
        with self.assertRaises(ValueError):
            await aget_partial_note_content(note.id, start=10, end=5)

        # Non-existent note raises ValueError
        with self.assertRaises(ValueError):
            await aget_partial_note_content(999_999)
