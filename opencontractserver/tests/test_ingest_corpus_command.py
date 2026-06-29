"""Integration tests for the ``ingest_corpus`` management command.

The command is the programmatic twin of the create-corpus + intelligence-setup
UI flow: create corpus -> import each file (parse + embed) -> [wait] -> [enrich]
-> [publish]. The heavy / async pieces are mocked here so the command's
orchestration runs fast and deterministically:

* ``import_document_for_user`` is mocked to return a ready document (no real
  parse/embed, no Celery), and
* ``CorpusIntelligenceSetupService.setup`` is mocked for the ``--enrich`` path.

A freshly created document's ``backend_lock`` defaults to ``False``, so the
``--wait`` poll loop clears on its first iteration without sleeping.
"""

from __future__ import annotations

import tempfile
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from opencontractserver.corpuses.models import Corpus
from opencontractserver.document_imports.services import ImportResult
from opencontractserver.documents.models import Document
from opencontractserver.shared.services.conventions import ServiceResult

User = get_user_model()

_IMPORT_TARGET = "opencontractserver.document_imports.services.import_document_for_user"
_SETUP_TARGET = (
    "opencontractserver.corpuses.services.intelligence_setup."
    "CorpusIntelligenceSetupService.setup"
)


class IngestCorpusCommandTests(TestCase):
    owner: Any
    superuser: Any

    @classmethod
    def setUpTestData(cls):
        # A non-superuser owner: ``visible_to_user`` only includes the corpus
        # if the command actually grants creator permissions (only superusers
        # bypass guardian), so the grant assertion below is meaningful.
        cls.owner = User.objects.create_user(username="ingest-owner", password="x")
        cls.superuser = User.objects.create_user(username="ingest-super", password="x")
        cls.superuser.is_superuser = True
        cls.superuser.save()

    @staticmethod
    def _ready_document(owner: Any) -> Document:
        doc = Document.objects.create(title="ingested", creator=owner, description="")
        doc._skip_signals = True
        return doc

    def test_ingest_creates_corpus_and_grants_owner_permissions(self):
        doc = self._ready_document(self.owner)
        out = StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "a.txt").write_text("hello world")
            with patch(
                _IMPORT_TARGET,
                return_value=ImportResult(document=doc, error=None),
            ) as mock_import:
                call_command(
                    "ingest_corpus",
                    "--path",
                    tmp,
                    "--title",
                    "Ingested Corpus",
                    "--owner",
                    self.owner.username,
                    stdout=out,
                )

        mock_import.assert_called_once()
        corpus = Corpus.objects.get(title="Ingested Corpus")
        self.assertEqual(corpus.creator_id, self.owner.id)
        # Finding 3: a bare ORM ``create()`` does not grant guardian object-level
        # permissions, so the command must mirror the GraphQL CreateCorpus path —
        # otherwise the corpus is invisible to its own (non-superuser) owner.
        self.assertTrue(
            Corpus.objects.visible_to_user(self.owner).filter(pk=corpus.pk).exists()
        )
        output = out.getvalue()
        self.assertIn("Created corpus", output)
        self.assertIn("1 docs", output)
        self.assertIn("Done.", output)

    def test_ingest_defaults_to_first_superuser_when_owner_omitted(self):
        doc = self._ready_document(self.superuser)
        out = StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "a.txt").write_text("hello")
            with patch(
                _IMPORT_TARGET,
                return_value=ImportResult(document=doc, error=None),
            ):
                call_command(
                    "ingest_corpus",
                    "--path",
                    tmp,
                    "--title",
                    "Default Owner Corpus",
                    stdout=out,
                )

        corpus = Corpus.objects.get(title="Default Owner Corpus")
        self.assertEqual(corpus.creator_id, self.superuser.id)
        self.assertIn(f"as {self.superuser.username}", out.getvalue())

    def test_ingest_with_wait_enrich_and_public(self):
        doc = self._ready_document(self.owner)
        out = StringIO()
        summary = SimpleNamespace(
            reference_analysis_started=True, total_active_documents=1
        )
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "a.txt").write_text("hello")
            with patch(
                _IMPORT_TARGET,
                return_value=ImportResult(document=doc, error=None),
            ), patch(
                _SETUP_TARGET, return_value=ServiceResult.success(summary)
            ) as mock_setup:
                call_command(
                    "ingest_corpus",
                    "--path",
                    tmp,
                    "--title",
                    "Full Corpus",
                    "--owner",
                    self.owner.username,
                    "--enrich",  # implies --wait
                    "--public",
                    # ``backend_lock`` defaults to False so the wait loop clears
                    # on the first poll; timeout=0 is a no-hang backstop.
                    "--timeout",
                    "0",
                    stdout=out,
                )

        mock_setup.assert_called_once()
        corpus = Corpus.objects.get(title="Full Corpus")
        self.assertTrue(corpus.is_public)
        output = out.getvalue()
        self.assertIn("all documents processed", output)
        self.assertIn("setup started", output)
        self.assertIn("Marked corpus public", output)

    def test_ingest_errors_when_no_ingestible_files(self):
        from django.core.management.base import CommandError

        out = StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            # An unsupported extension is filtered out -> nothing to ingest.
            (Path(tmp) / "skip.bin").write_text("nope")
            with self.assertRaises(CommandError):
                call_command(
                    "ingest_corpus",
                    "--path",
                    tmp,
                    "--title",
                    "Empty Corpus",
                    "--owner",
                    self.owner.username,
                    stdout=out,
                )
