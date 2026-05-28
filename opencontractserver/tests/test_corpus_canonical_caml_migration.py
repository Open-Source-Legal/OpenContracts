"""Post-migration invariants for the Canonical-CAML description refactor.

Originally this module exercised migration 0052's ``backfill_all`` by
staging legacy ``Corpus.md_description`` files and
``CorpusDescriptionRevision`` rows through the live ORM and then
invoking the backfill against the live model registry. Migration 0053
removes both the FileField and the revision model, so the staging path
is no longer expressible against the post-0053 schema — the
``CanonicalCamlBackfillMigrationTest`` class has been retired.

What survives here is the structural verification that the legacy
storage is gone and that the new canonical write path (Document signal
handler refreshing ``Corpus.description_preview``) is the only thing
populating the cache columns. End-to-end backfill behavior is covered
by ``test_corpus_export_import_v2`` and ``test_v2_import_back_compat``
which round-trip V2 archives through the synthesized Readme.CAML
Document path (Task 14 + signal handler from Task 3).

Spec: docs/superpowers/specs/2026-05-27-canonical-caml-description-refactor-design.md §4.9
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase

from opencontractserver.corpuses.models import Corpus


class LegacyStorageDroppedTest(TestCase):
    """After migration 0053, the legacy field / model class are gone."""

    def test_corpus_has_no_md_description_attr(self):
        self.assertFalse(
            hasattr(Corpus, "md_description"),
            "Corpus.md_description still exists — migration 0053 didn't run?",
        )

    def test_no_corpus_description_revision_model(self):
        from django.apps import apps

        with self.assertRaises(LookupError):
            apps.get_model("corpuses", "CorpusDescriptionRevision")

    def test_description_preview_save_override_no_longer_present(self):
        """Confirms the Corpus.save() override branch is gone — cache writes
        only flow through the Document signal handler now."""
        from opencontractserver.corpuses.services.corpus_service import (
            CorpusService,
        )

        User = get_user_model()
        u = User.objects.create_user(username="legacy-drop", password="x")
        corpus = Corpus.objects.create(title="C", creator=u)
        with self.captureOnCommitCallbacks(execute=True):
            CorpusService.update_description(u, corpus, "Body via CAML.")
        corpus.refresh_from_db()
        self.assertEqual(corpus.description_preview, "Body via CAML.")
