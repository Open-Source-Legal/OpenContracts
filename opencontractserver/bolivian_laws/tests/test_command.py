"""Test the ingest_bolivian_laws management command."""

from __future__ import annotations

import tempfile
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from opencontractserver.bolivian_laws.constants import LegalArea
from opencontractserver.bolivian_laws.models import BolivianLegalDocument
from opencontractserver.corpuses.models import Corpus

User = get_user_model()


def _fake_import_content(self, *, content, user, filename=None, **kwargs):
    class _Doc:
        pk = 1
        id = 1

    return _Doc(), "created", None


class TestIngestCommand(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_superuser(
            username="bl_cmd_admin",
            password="testpass123",
            email="bl_cmd@test.com",
        )

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.tmp_path = Path(self.tmp.name)
        # Create three small "PDF" placeholders
        for name in ("law_a.pdf", "law_b.pdf", "law_c.pdf"):
            (self.tmp_path / name).write_bytes(f"%PDF-{name}".encode())

    def test_requires_area_or_auto_classify(self):
        with self.assertRaises(CommandError):
            call_command("ingest_bolivian_laws", path=str(self.tmp_path))

    def test_path_must_be_directory(self):
        with self.assertRaises(CommandError):
            call_command(
                "ingest_bolivian_laws",
                path="/this/path/does/not/exist",
                area=LegalArea.PENAL,
            )

    def test_dry_run_does_not_ingest(self):
        out = StringIO()
        call_command(
            "ingest_bolivian_laws",
            path=str(self.tmp_path),
            area=LegalArea.PENAL,
            dry_run=True,
            stdout=out,
        )
        self.assertEqual(BolivianLegalDocument.objects.count(), 0)
        self.assertIn("DRY", out.getvalue())

    def test_inline_ingest_creates_records(self):
        with patch.object(
            Corpus, "import_content", autospec=True, side_effect=_fake_import_content
        ):
            call_command(
                "ingest_bolivian_laws",
                path=str(self.tmp_path),
                area=LegalArea.PENAL,
            )
        self.assertEqual(BolivianLegalDocument.objects.count(), 3)
        statuses = set(BolivianLegalDocument.objects.values_list("status", flat=True))
        self.assertEqual(statuses, {BolivianLegalDocument.Status.INGESTED})
