"""Backfill correctness for migration 0052.

We invoke the migration's ``backfill_all`` function manually via the
live model registry, after staging legacy ``md_description`` content on
a fresh corpus. The test verifies that the backfill creates a
Readme.CAML Document + DocumentPath, replays revisions as version-tree
siblings, and populates the Corpus cache columns.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TransactionTestCase

from opencontractserver.corpuses.models import Corpus, CorpusDescriptionRevision
from opencontractserver.documents.models import Document, DocumentPath


class CanonicalCamlBackfillMigrationTest(TransactionTestCase):
    def setUp(self):
        super().setUp()
        User = get_user_model()
        # TransactionTestCase truncates tables between tests, so the user
        # must be recreated per-test rather than in setUpClass.
        self.user, _ = User.objects.get_or_create(
            username="canonical-caml-mig",
            defaults={"password": "x"},
        )

    def _stage_corpus_with_md_description(self, body: str) -> Corpus:
        corpus = Corpus.objects.create(title="Mig", creator=self.user)
        corpus.md_description.save(
            "md_description.md",
            ContentFile(body.encode("utf-8")),
            save=True,
        )
        return corpus

    def _run_backfill_with_live_models(self, corpus: Corpus) -> None:
        # Import the migration module dynamically (file starts with a digit)
        import importlib

        mod = importlib.import_module(
            "opencontractserver.corpuses.migrations." "0052_canonical_caml_backfill"
        )
        # The migration callable expects an `apps` object exposing
        # get_model. We use the live registry via django.apps.apps so
        # the test runs against live schema.
        from django.apps import apps as live_apps

        mod.backfill_all(live_apps, None)

    def test_corpus_with_md_description_gets_caml_doc(self):
        corpus = self._stage_corpus_with_md_description("Backfill body.")
        self._run_backfill_with_live_models(corpus)
        corpus.refresh_from_db()
        # Cache populated
        self.assertEqual(corpus.description, "Backfill body.")
        self.assertEqual(corpus.description_preview, "Backfill body.")
        self.assertIsNotNone(corpus.readme_caml_document_id)
        # Document + DocumentPath created
        doc = Document.objects.get(pk=corpus.readme_caml_document_id)
        self.assertEqual(doc.title, "Readme.CAML")
        self.assertEqual(doc.file_type, "text/markdown")
        self.assertTrue(doc.is_current)
        path = DocumentPath.objects.get(
            corpus=corpus, path="Readme.CAML", is_current=True
        )
        self.assertEqual(path.document_id, doc.pk)
        self.assertFalse(path.is_deleted)

    def test_revisions_replayed_as_version_tree_siblings(self):
        corpus = self._stage_corpus_with_md_description("v3 body")
        CorpusDescriptionRevision.objects.create(
            corpus=corpus,
            author=self.user,
            version=1,
            snapshot="v1 body",
            diff="",
        )
        CorpusDescriptionRevision.objects.create(
            corpus=corpus,
            author=self.user,
            version=2,
            snapshot="v2 body",
            diff="",
        )
        self._run_backfill_with_live_models(corpus)
        corpus.refresh_from_db()
        # Head + 2 siblings = 3 Documents sharing one version_tree_id
        head_doc = corpus.readme_caml_document
        assert head_doc is not None  # narrow Optional for mypy + sanity gate
        tree_id = head_doc.version_tree_id
        self.assertEqual(Document.objects.filter(version_tree_id=tree_id).count(), 3)
        # Exactly one is the current head
        head_count = Document.objects.filter(
            version_tree_id=tree_id, is_current=True
        ).count()
        self.assertEqual(head_count, 1)
        # Exactly one DocumentPath is current for the corpus
        current_paths = DocumentPath.objects.filter(
            corpus=corpus, path="Readme.CAML", is_current=True, is_deleted=False
        )
        self.assertEqual(current_paths.count(), 1)

    def test_idempotent_second_run_is_no_op(self):
        corpus = self._stage_corpus_with_md_description("Once.")
        self._run_backfill_with_live_models(corpus)
        self._run_backfill_with_live_models(corpus)
        # Still exactly one CAML doc + one current path
        self.assertEqual(
            DocumentPath.objects.filter(
                corpus=corpus, path="Readme.CAML", is_current=True
            ).count(),
            1,
        )
        corpus.refresh_from_db()
        head_id = (
            corpus.readme_caml_document_id
            or DocumentPath.objects.filter(
                corpus=corpus, path="Readme.CAML", is_current=True
            )
            .values_list("document_id", flat=True)
            .first()
        )
        self.assertIsNotNone(head_id)
        assert head_id is not None  # narrow Optional for mypy
        # Total Documents in the tree unchanged
        head = Document.objects.get(pk=head_id)
        self.assertEqual(
            Document.objects.filter(version_tree_id=head.version_tree_id).count(),
            1,
        )

    def test_corpus_without_md_description_gets_no_caml_doc(self):
        corpus = Corpus.objects.create(title="Empty", creator=self.user)
        self._run_backfill_with_live_models(corpus)
        corpus.refresh_from_db()
        self.assertIsNone(corpus.readme_caml_document_id)
        self.assertEqual(corpus.description, "")
        self.assertEqual(corpus.description_preview, "")
        self.assertEqual(
            DocumentPath.objects.filter(corpus=corpus, path="Readme.CAML").count(),
            0,
        )
