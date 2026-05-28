"""Unit tests for the canonical-CAML description cache helpers.

These helpers are pure string functions with no ORM access. They are the
single derivation point for the auto-maintained ``Corpus.description`` and
``Corpus.description_preview`` cache columns; the spec is at
``docs/superpowers/specs/2026-05-27-canonical-caml-description-refactor-design.md``.
"""

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from opencontractserver.constants.truncation import (
    MAX_CORPUS_DESCRIPTION_PREVIEW_LENGTH,
)
from opencontractserver.corpuses.models import Corpus
from opencontractserver.corpuses.services.description_cache import (
    compute_cache_from_caml_body,
    markdown_to_plain_text,
    summarize_for_preview,
)


class MarkdownToPlainTextTest(SimpleTestCase):
    def test_strips_headings_bold_italic_links(self):
        md = (
            "# Title\n\n"
            "Some **bold** and *italic* and [a link](https://example.com)."
        )
        self.assertEqual(
            markdown_to_plain_text(md),
            "Title\n\nSome bold and italic and a link.",
        )

    def test_preserves_inline_code_content(self):
        self.assertEqual(
            markdown_to_plain_text("Use `git status` to check."),
            "Use git status to check.",
        )

    def test_strips_fenced_code_blocks_keeps_content(self):
        md = "```python\nprint('hi')\n```\n"
        self.assertIn("print('hi')", markdown_to_plain_text(md))

    def test_empty_returns_empty(self):
        self.assertEqual(markdown_to_plain_text(""), "")


class SummarizeForPreviewTest(SimpleTestCase):
    def test_short_text_passes_through(self):
        self.assertEqual(summarize_for_preview("Hello"), "Hello")

    def test_takes_first_paragraph_only(self):
        text = "First paragraph.\n\nSecond paragraph."
        self.assertEqual(summarize_for_preview(text), "First paragraph.")

    def test_collapses_internal_whitespace(self):
        self.assertEqual(summarize_for_preview("hello\n  world"), "hello world")

    def test_truncates_at_word_boundary_with_ellipsis(self):
        text = "word " * 100
        result = summarize_for_preview(text)
        self.assertTrue(result.endswith("…"))
        self.assertLessEqual(len(result), MAX_CORPUS_DESCRIPTION_PREVIEW_LENGTH + 1)
        self.assertFalse(result.endswith(" …"))

    def test_empty_returns_empty(self):
        self.assertEqual(summarize_for_preview(""), "")


class ComputeCacheFromCamlBodyTest(SimpleTestCase):
    def test_returns_pair_of_plain_text_and_preview(self):
        body = "# Hello\n\nWorld."
        plain, preview = compute_cache_from_caml_body(body)
        self.assertEqual(plain, "Hello\n\nWorld.")
        self.assertEqual(preview, "Hello")

    def test_empty_body_returns_empty_pair(self):
        self.assertEqual(compute_cache_from_caml_body(""), ("", ""))

    def test_none_body_returns_empty_pair(self):
        self.assertEqual(compute_cache_from_caml_body(None), ("", ""))


class CorpusReadmeCamlFKTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user(
            username="caml-fk-user", password="x"
        )

    def test_fk_field_exists_and_defaults_null(self):
        corpus = Corpus.objects.create(
            title="C", creator=self.user
        )
        self.assertIsNone(corpus.readme_caml_document)
        self.assertIsNone(corpus.readme_caml_document_id)


class BackfillCamlDocForCorpusTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user(
            username="backfill-user", password="x"
        )

    def test_creates_caml_doc_with_documentpath_when_missing(self):
        from opencontractserver.corpuses.services.description_cache import (
            backfill_caml_doc_for_corpus,
        )
        from opencontractserver.documents.models import Document, DocumentPath

        corpus = Corpus.objects.create(title="C", creator=self.user)
        backfill_caml_doc_for_corpus(
            corpus.pk, md_description_body="Backfill body."
        )

        docs = Document.objects.filter(
            title="Readme.CAML", file_type="text/markdown"
        )
        self.assertEqual(docs.count(), 1)
        path = DocumentPath.objects.filter(
            corpus=corpus, document=docs.first(), is_current=True
        ).first()
        self.assertIsNotNone(path)
        self.assertFalse(path.is_deleted)
        corpus.refresh_from_db()
        self.assertEqual(corpus.description, "Backfill body.")
        self.assertEqual(corpus.readme_caml_document_id, docs.first().pk)

    def test_idempotent_does_not_duplicate_doc_or_path(self):
        from opencontractserver.corpuses.services.description_cache import (
            backfill_caml_doc_for_corpus,
        )
        from opencontractserver.documents.models import Document, DocumentPath

        corpus = Corpus.objects.create(title="C", creator=self.user)
        backfill_caml_doc_for_corpus(
            corpus.pk, md_description_body="Body v1."
        )
        backfill_caml_doc_for_corpus(
            corpus.pk, md_description_body="Body v1."
        )

        self.assertEqual(
            Document.objects.filter(title="Readme.CAML").count(), 1
        )
        self.assertEqual(
            DocumentPath.objects.filter(
                corpus=corpus, path="Readme.CAML", is_current=True, is_deleted=False
            ).count(),
            1,
        )

    def test_no_op_when_body_empty_and_no_existing_caml(self):
        from opencontractserver.corpuses.services.description_cache import (
            backfill_caml_doc_for_corpus,
        )
        from opencontractserver.documents.models import Document

        corpus = Corpus.objects.create(title="C", creator=self.user)
        backfill_caml_doc_for_corpus(corpus.pk, md_description_body="")

        self.assertEqual(
            Document.objects.filter(title="Readme.CAML").count(), 0
        )
        corpus.refresh_from_db()
        self.assertEqual(corpus.description, "")
        self.assertIsNone(corpus.readme_caml_document_id)
