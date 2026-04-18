"""Tests for Bolivian Laws ingestion service."""

from __future__ import annotations

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from opencontractserver.bolivian_laws.constants import LegalArea, LegalSource
from opencontractserver.bolivian_laws.models import (
    BolivianLegalDocument,
    LegalAreaCorpus,
)
from opencontractserver.bolivian_laws.services.ingestion import (
    ensure_area_corpus,
    infer_metadata_from_filename,
    ingest_pdf,
)
from opencontractserver.corpuses.models import Corpus

User = get_user_model()


class _FakeDocument:
    """Stand-in returned by mocked ``Corpus.import_content``."""

    def __init__(self, pk: int = 7) -> None:
        self.pk = pk
        self.id = pk


def _fake_import_content(self, *, content, user, filename=None, **kwargs):
    return _FakeDocument(), "created", None


class TestEnsureAreaCorpus(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_superuser(
            username="bl_test_admin",
            password="testpass123",
            email="bl_admin@test.com",
        )

    def test_creates_corpus_idempotently(self):
        first = ensure_area_corpus(LegalArea.CONSTITUCIONAL, user=self.user)
        second = ensure_area_corpus(LegalArea.CONSTITUCIONAL, user=self.user)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(
            LegalAreaCorpus.objects.filter(area="constitucional").count(), 1
        )

    def test_corpus_seeded_with_profile_fields(self):
        corpus = ensure_area_corpus(LegalArea.PENAL, user=self.user)
        self.assertTrue(corpus.title.startswith("Bolivia — "))
        self.assertTrue(corpus.corpus_agent_instructions)
        self.assertEqual(corpus.slug, "bolivia-penal")

    def test_unknown_area_raises(self):
        with self.assertRaises(ValueError):
            ensure_area_corpus("not-a-real-area", user=self.user)


class TestIngestPdf(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_superuser(
            username="bl_ingest_admin",
            password="testpass123",
            email="bl_ingest@test.com",
        )

    def test_ingest_creates_record_and_calls_import_content(self):
        with patch.object(
            Corpus, "import_content", autospec=True, side_effect=_fake_import_content
        ) as mock_import:
            record = ingest_pdf(
                b"%PDF-fake",
                area=LegalArea.LABORAL,
                title="Ley General del Trabajo",
                source=LegalSource.MANUAL,
                user=self.user,
            )
        mock_import.assert_called_once()
        self.assertEqual(record.status, BolivianLegalDocument.Status.INGESTED)
        self.assertEqual(record.area, "laboral")
        self.assertEqual(record.source, "manual")
        self.assertIsNotNone(record.ingested_at)
        self.assertEqual(record.pdf_sha256, _sha256_of(b"%PDF-fake"))

    def test_dedupe_returns_existing_record(self):
        with patch.object(
            Corpus, "import_content", autospec=True, side_effect=_fake_import_content
        ):
            first = ingest_pdf(
                b"%PDF-dup",
                area=LegalArea.CIVIL,
                title="Doc A",
                user=self.user,
            )
            second = ingest_pdf(
                b"%PDF-dup",
                area=LegalArea.PENAL,  # different area, same bytes
                title="Doc A again",
                user=self.user,
            )
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(BolivianLegalDocument.objects.count(), 1)

    def test_failure_marks_record_failed_and_reraises(self):
        with patch.object(
            Corpus, "import_content", autospec=True, side_effect=RuntimeError("boom")
        ):
            with self.assertRaises(RuntimeError):
                ingest_pdf(
                    b"%PDF-fail",
                    area=LegalArea.TRIBUTARIO,
                    title="Doc fail",
                    user=self.user,
                )
        record = BolivianLegalDocument.objects.get(pdf_sha256=_sha256_of(b"%PDF-fail"))
        self.assertEqual(record.status, BolivianLegalDocument.Status.FAILED)
        self.assertIn("boom", record.last_error)


class TestFilenameInference(TestCase):
    def test_full_convention(self):
        out = infer_metadata_from_filename("constitucional_2009_001_cpe.pdf")
        self.assertEqual(out["area"], "constitucional")
        self.assertEqual(out["year"], 2009)
        self.assertEqual(out["number"], "001")
        self.assertEqual(out["title_hint"], "cpe")

    def test_unknown_area_token_ignored(self):
        out = infer_metadata_from_filename("contrato_2024_05_cliente.pdf")
        # "contrato" is not a known area, so area is omitted; year/number still parse
        self.assertNotIn("area", out)
        self.assertEqual(out["year"], 2024)


def _sha256_of(content: bytes) -> str:
    import hashlib

    return hashlib.sha256(content).hexdigest()
