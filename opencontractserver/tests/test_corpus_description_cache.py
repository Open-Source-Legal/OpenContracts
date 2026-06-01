"""Unit tests for the canonical-CAML description cache helpers.

These helpers are pure string functions with no ORM access. They are the
single derivation point for the auto-maintained ``Corpus.description`` and
``Corpus.description_preview`` cache columns; the spec is at
``docs/superpowers/specs/2026-05-27-canonical-caml-description-refactor-design.md``.
"""

from django.db import connection
from django.test import SimpleTestCase, TestCase
from django.test.utils import CaptureQueriesContext

from opencontractserver.constants.truncation import (
    MAX_CORPUS_DESCRIPTION_PREVIEW_LENGTH,
)
from opencontractserver.corpuses.models import Corpus
from opencontractserver.corpuses.services.description_cache import (
    compute_cache_from_caml_body,
    markdown_to_plain_text,
    summarize_for_preview,
)
from opencontractserver.users.models import User


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
    user: User

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="caml-fk-user", password="x")

    def test_fk_field_exists_and_defaults_null(self):
        corpus = Corpus.objects.create(title="C", creator=self.user)
        self.assertIsNone(corpus.readme_caml_document)
        self.assertIsNone(corpus.readme_caml_document_id)


class BackfillCamlDocForCorpusTest(TestCase):
    user: User

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="backfill-user", password="x")

    def test_creates_caml_doc_with_documentpath_when_missing(self):
        from opencontractserver.corpuses.services.description_cache import (
            backfill_caml_doc_for_corpus,
        )
        from opencontractserver.documents.models import Document, DocumentPath

        corpus = Corpus.objects.create(title="C", creator=self.user)
        backfill_caml_doc_for_corpus(corpus.pk, md_description_body="Backfill body.")

        docs = Document.objects.filter(title="Readme.CAML", file_type="text/markdown")
        self.assertEqual(docs.count(), 1)
        first_doc = docs.first()
        assert first_doc is not None
        path = DocumentPath.objects.filter(
            corpus=corpus, document=first_doc, is_current=True
        ).first()
        self.assertIsNotNone(path)
        assert path is not None
        self.assertFalse(path.is_deleted)
        corpus.refresh_from_db()
        self.assertEqual(corpus.description, "Backfill body.")
        self.assertEqual(corpus.readme_caml_document_id, first_doc.pk)

    def test_idempotent_does_not_duplicate_doc_or_path(self):
        from opencontractserver.corpuses.services.description_cache import (
            backfill_caml_doc_for_corpus,
        )
        from opencontractserver.documents.models import Document, DocumentPath

        corpus = Corpus.objects.create(title="C", creator=self.user)
        backfill_caml_doc_for_corpus(corpus.pk, md_description_body="Body v1.")
        backfill_caml_doc_for_corpus(corpus.pk, md_description_body="Body v1.")

        self.assertEqual(Document.objects.filter(title="Readme.CAML").count(), 1)
        self.assertEqual(
            DocumentPath.objects.filter(
                corpus=corpus, path="Readme.CAML", is_current=True, is_deleted=False
            ).count(),
            1,
        )

    def test_existing_doc_cache_derives_from_doc_not_legacy_arg(self):
        """When a Readme.CAML doc already exists, the cache columns must be
        derived from the *document's* body, not the caller-supplied legacy
        ``md_description_body`` (which may have drifted). Regression test for
        the backfill wrong-body bug."""
        from opencontractserver.corpuses.services.description_cache import (
            backfill_caml_doc_for_corpus,
        )
        from opencontractserver.documents.models import Document

        corpus = Corpus.objects.create(title="C", creator=self.user)
        # First call creates the canonical CAML doc from this body.
        backfill_caml_doc_for_corpus(corpus.pk, md_description_body="Canonical body.")
        self.assertEqual(Document.objects.filter(title="Readme.CAML").count(), 1)

        # Second call passes a DIFFERENT (stale) legacy body. The existing doc
        # is canonical, so the cache must still reflect "Canonical body.".
        backfill_caml_doc_for_corpus(
            corpus.pk, md_description_body="Stale legacy body that must be ignored."
        )
        corpus.refresh_from_db()
        self.assertEqual(corpus.description, "Canonical body.")
        self.assertEqual(corpus.description_preview, "Canonical body.")

    def test_no_op_when_body_empty_and_no_existing_caml(self):
        from opencontractserver.corpuses.services.description_cache import (
            backfill_caml_doc_for_corpus,
        )
        from opencontractserver.documents.models import Document

        corpus = Corpus.objects.create(title="C", creator=self.user)
        backfill_caml_doc_for_corpus(corpus.pk, md_description_body="")

        self.assertEqual(Document.objects.filter(title="Readme.CAML").count(), 0)
        corpus.refresh_from_db()
        self.assertEqual(corpus.description, "")
        self.assertIsNone(corpus.readme_caml_document_id)


class ReadmeCamlSignalTest(TestCase):
    """Tests for Task 3's Document/DocumentPath signal handlers that keep
    ``Corpus.description``, ``Corpus.description_preview``, and
    ``Corpus.readme_caml_document_id`` in sync with the canonical
    Readme.CAML body.

    All trigger code is wrapped in ``captureOnCommitCallbacks`` because
    the signal defers its cache writes to ``transaction.on_commit``;
    inside a Django ``TestCase`` no real commit ever fires, so without
    capturing the callbacks the cache refresh would never run.
    """

    user: User

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="caml-signal-user", password="x")

    def _create_caml(self, corpus, body):
        """Create the corpus's Readme.CAML doc via the canonical
        ``import_document`` path.

        Wrapped in ``captureOnCommitCallbacks(execute=True)`` so the
        post-commit cache-refresh callback actually fires inside the
        test's outer atomic block.
        """
        from opencontractserver.constants.document_processing import (
            CAML_ARTICLE_TITLE,
            MARKDOWN_MIME_TYPE,
        )
        from opencontractserver.documents.versioning import import_document

        with self.captureOnCommitCallbacks(execute=True):
            doc, _status, _path = import_document(
                corpus=corpus,
                path=CAML_ARTICLE_TITLE,
                content=body.encode("utf-8"),
                user=self.user,
                file_type=MARKDOWN_MIME_TYPE,
                title=CAML_ARTICLE_TITLE,
            )
        return doc

    def test_creating_caml_doc_populates_corpus_cache(self):
        corpus = Corpus.objects.create(title="C", creator=self.user)
        doc = self._create_caml(corpus, "# Hello\n\nWorld.")

        corpus.refresh_from_db()
        self.assertEqual(corpus.description, "Hello\n\nWorld.")
        self.assertEqual(corpus.description_preview, "Hello")
        self.assertEqual(corpus.readme_caml_document_id, doc.pk)

    def test_editing_caml_body_refreshes_cache(self):
        corpus = Corpus.objects.create(title="C", creator=self.user)
        old_doc = self._create_caml(corpus, "Old body.")
        new_doc = self._create_caml(corpus, "New body.")

        corpus.refresh_from_db()
        self.assertEqual(corpus.description, "New body.")
        self.assertEqual(corpus.description_preview, "New body.")
        self.assertEqual(corpus.readme_caml_document_id, new_doc.pk)
        self.assertNotEqual(corpus.readme_caml_document_id, old_doc.pk)

    def test_hard_deleting_caml_doc_clears_cache(self):
        from opencontractserver.documents.models import Document, DocumentPath

        corpus = Corpus.objects.create(title="C", creator=self.user)
        doc = self._create_caml(corpus, "Some body.")

        corpus.refresh_from_db()
        self.assertEqual(corpus.description, "Some body.")
        self.assertEqual(corpus.readme_caml_document_id, doc.pk)

        # Hard delete: must remove DocumentPath rows first because
        # ``DocumentPath.document`` is ``on_delete=PROTECT``. This mirrors
        # ``permanently_delete_document`` semantics.
        with self.captureOnCommitCallbacks(execute=True):
            DocumentPath.objects.filter(document=doc).delete()
            Document.objects.filter(pk=doc.pk).delete()

        corpus.refresh_from_db()
        self.assertEqual(corpus.description, "")
        self.assertEqual(corpus.description_preview, "")
        self.assertIsNone(corpus.readme_caml_document_id)

    def test_soft_deleting_caml_doc_via_path_clears_cache(self):
        """Soft delete = flip the current DocumentPath to is_deleted=True.

        The signal must clear the cache because there's no longer an
        active path pointing at the Readme.CAML doc.
        """
        from opencontractserver.documents.models import DocumentPath

        corpus = Corpus.objects.create(title="C", creator=self.user)
        doc = self._create_caml(corpus, "Some body.")

        corpus.refresh_from_db()
        self.assertEqual(corpus.readme_caml_document_id, doc.pk)

        path = DocumentPath.objects.filter(
            corpus=corpus, document=doc, is_current=True
        ).first()
        self.assertIsNotNone(path)
        assert path is not None
        with self.captureOnCommitCallbacks(execute=True):
            path.is_deleted = True
            path.save(update_fields=["is_deleted"])

        corpus.refresh_from_db()
        self.assertEqual(corpus.description, "")
        self.assertEqual(corpus.description_preview, "")
        self.assertIsNone(corpus.readme_caml_document_id)

    def test_non_caml_doc_save_does_not_touch_cache(self):
        from opencontractserver.documents.versioning import import_document

        corpus = Corpus.objects.create(title="C", creator=self.user)
        self._create_caml(corpus, "Original.")

        corpus.refresh_from_db()
        self.assertEqual(corpus.description, "Original.")
        original_caml_fk = corpus.readme_caml_document_id

        # Create a non-CAML doc in the same corpus. It must not disturb
        # the cache columns.
        with self.captureOnCommitCallbacks(execute=True):
            import_document(
                corpus=corpus,
                path="Other.pdf",
                content=b"unrelated",
                user=self.user,
                file_type="application/pdf",
                title="Other",
            )

        corpus.refresh_from_db()
        self.assertEqual(corpus.description, "Original.")
        self.assertEqual(corpus.description_preview, "Original.")
        self.assertEqual(corpus.readme_caml_document_id, original_caml_fk)

    def test_direct_cache_write_is_overwritten_on_next_caml_save(self):
        """Codifies the read-only-cache invariant (spec §4.2):
        manual writes to ``description`` are silently overwritten on the
        next Readme.CAML save.
        """
        corpus = Corpus.objects.create(title="C", creator=self.user)
        self._create_caml(corpus, "Body one.")

        # Drift the cache by hand-writing via QuerySet.update so
        # Corpus.save() doesn't immediately recompute description_preview.
        Corpus.objects.filter(pk=corpus.pk).update(description="hand-written drift")
        corpus.refresh_from_db()
        self.assertEqual(corpus.description, "hand-written drift")

        # Version-up the CAML doc; the signal must overwrite the drift.
        self._create_caml(corpus, "Body two.")

        corpus.refresh_from_db()
        self.assertEqual(corpus.description, "Body two.")
        self.assertEqual(corpus.description_preview, "Body two.")


class WithReadmeCamlDocQuerysetTest(TestCase):
    user: User

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="qcount-user", password="x")
        from opencontractserver.documents.versioning import import_document

        for i in range(10):
            corpus = Corpus.objects.create(title=f"C{i}", creator=cls.user)
            import_document(
                corpus=corpus,
                path="Readme.CAML",
                content=f"Body {i}".encode(),
                user=cls.user,
                file_type="text/markdown",
                title="Readme.CAML",
            )

    def test_select_related_avoids_n_plus_1_on_readme_caml_doc(self):
        from opencontractserver.corpuses.services.corpus_documents import (
            CorpusDocumentService,
        )

        qs = CorpusDocumentService.with_readme_caml_doc(Corpus.objects.all())

        with CaptureQueriesContext(connection) as ctx:
            corpuses = list(qs)
            # Access the FK on every row — must NOT trigger an extra
            # query per row (that's the point of select_related).
            for corpus in corpuses:
                _ = corpus.readme_caml_document
        # Without select_related this would be 1 + 10 = 11 queries.
        # With select_related it is 1 query (one JOIN).
        # Permit a small slack for any meta queries Django emits.
        self.assertLess(
            len(ctx.captured_queries),
            4,
            f"Expected ≤3 queries, got {len(ctx.captured_queries)}: "
            + "\n".join(q["sql"][:120] for q in ctx.captured_queries),
        )


class MdDescriptionResolverTest(TestCase):
    user: User
    corpus: Corpus

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="resolver-user", password="x")
        cls.corpus = Corpus.objects.create(title="C", creator=cls.user)
        from opencontractserver.documents.versioning import import_document

        import_document(
            corpus=cls.corpus,
            path="Readme.CAML",
            content=b"# Hello",
            user=cls.user,
            file_type="text/markdown",
            title="Readme.CAML",
        )
        # The signal handler that populates the FK runs via
        # transaction.on_commit. setUpTestData runs inside a single
        # outer transaction in TestCase, so we have to flush manually
        # or pre-populate the FK by re-resolving.
        from opencontractserver.documents.models import DocumentPath

        cls.corpus.refresh_from_db()
        if cls.corpus.readme_caml_document_id is None:
            # Fallback: resolve the head ourselves (signal couldn't fire
            # mid-setUpTestData). This keeps the test deterministic.
            head = (
                DocumentPath.objects.filter(
                    corpus=cls.corpus, path="Readme.CAML", is_current=True
                )
                .select_related("document")
                .first()
            )
            assert head is not None
            cls.corpus.readme_caml_document_id = head.document_id
            cls.corpus.save(update_fields=["readme_caml_document"])
            cls.corpus.refresh_from_db()

    def test_md_description_resolves_to_caml_doc_url(self):
        from config.graphql.corpus_types import CorpusType

        class FakeRequest:
            def build_absolute_uri(self, url):
                return f"https://example.com{url}"

        class FakeInfo:
            context = FakeRequest()

        url = CorpusType.resolve_md_description(self.corpus, FakeInfo())
        self.assertIsNotNone(url)
        # The CAML doc body lives in txt_extract_file → URL should reference
        # the configured storage path for txt-extract files.
        self.assertTrue(url.startswith("https://example.com/"))

    def test_md_description_is_none_without_caml_doc(self):
        from config.graphql.corpus_types import CorpusType

        bare = Corpus.objects.create(title="Bare", creator=self.user)
        result = CorpusType.resolve_md_description(bare, None)
        self.assertIsNone(result)


class ReadmeCamlDocumentFieldTest(TestCase):
    user: User
    corpus: Corpus

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="rcdf-user", password="x")
        cls.corpus = Corpus.objects.create(title="C", creator=cls.user)
        from opencontractserver.documents.versioning import import_document

        import_document(
            corpus=cls.corpus,
            path="Readme.CAML",
            content=b"# Field test body",
            user=cls.user,
            file_type="text/markdown",
            title="Readme.CAML",
        )
        # Make sure the FK is populated (signal may not have fired
        # inside the wrapping setUpTestData transaction).
        cls.corpus.refresh_from_db()
        if cls.corpus.readme_caml_document_id is None:
            from opencontractserver.documents.models import DocumentPath

            head = (
                DocumentPath.objects.filter(
                    corpus=cls.corpus, path="Readme.CAML", is_current=True
                )
                .select_related("document")
                .first()
            )
            assert head is not None
            cls.corpus.readme_caml_document_id = head.document_id
            cls.corpus.save(update_fields=["readme_caml_document"])
            cls.corpus.refresh_from_db()

    def test_field_resolves_to_caml_document(self):
        from config.graphql.corpus_types import CorpusType

        doc = CorpusType.resolve_readme_caml_document(self.corpus, None)
        self.assertIsNotNone(doc)
        self.assertEqual(doc.title, "Readme.CAML")
        self.assertEqual(doc.file_type, "text/markdown")

    def test_field_is_none_when_corpus_lacks_caml_doc(self):
        from config.graphql.corpus_types import CorpusType

        bare = Corpus.objects.create(title="Bare", creator=self.user)
        result = CorpusType.resolve_readme_caml_document(bare, None)
        self.assertIsNone(result)
