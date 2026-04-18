"""Tests for the scraping Celery tasks.

The scraper itself is mocked at the class level (``iter_entries`` +
``download_pdf``) so these tests focus on orchestration: SHA-256
dedupe, status counting, and fan-out wiring.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable
from contextlib import contextmanager
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from opencontractserver.bolivian_laws.constants import LegalArea, LegalSource
from opencontractserver.bolivian_laws.models import BolivianLegalDocument
from opencontractserver.bolivian_laws.scrapers.base import ScrapedEntry
from opencontractserver.bolivian_laws.tasks import (
    scrape_and_ingest_all,
    scrape_and_ingest_source,
)
from opencontractserver.corpuses.models import Corpus

User = get_user_model()


class _FakeDocument:
    def __init__(self, pk: int = 1) -> None:
        self.pk = pk
        self.id = pk


def _fake_import_content(self, *, content, user, filename=None, **kwargs):
    return _FakeDocument(), "created", None


class _FakeScraper:
    """Stand-in that bypasses HTTP entirely."""

    entries: list[ScrapedEntry] = []
    pdf_map: dict[str, bytes] = {}

    def __init__(self, *args, **kwargs) -> None:  # swallow everything
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> None:
        return None

    def iter_entries(self, *, since=None, max_entries=None) -> Iterable[ScrapedEntry]:
        yield from self.entries

    def download_pdf(self, entry: ScrapedEntry) -> bytes:
        return self.pdf_map[entry.pdf_url]


@contextmanager
def _patch_scraper_class(source_key: str, fake: type[_FakeScraper]):
    with patch(
        "opencontractserver.bolivian_laws.scrapers.registry.SCRAPERS",
        {source_key: fake},
    ):
        yield


class TestScrapeAndIngestSource(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_superuser(
            username="bl_scrape_admin",
            password="testpass123",
            email="bl_scrape@test.com",
        )

    def test_ingests_new_entries_and_dedupes_second_run(self):
        entries = [
            ScrapedEntry(
                source_key=LegalSource.GACETA.value,
                pdf_url="http://test.local/ley-1178.pdf",
                title="Ley 1178",
                external_id="LEY-1178",
                published_at=dt.date(1990, 7, 20),
                suggested_area=LegalArea.ADMINISTRATIVO,
            ),
            ScrapedEntry(
                source_key=LegalSource.GACETA.value,
                pdf_url="http://test.local/ds-29894.pdf",
                title="DS 29894",
                external_id="DS-29894",
                suggested_area=LegalArea.OTROS,
            ),
        ]
        pdf_map = {
            "http://test.local/ley-1178.pdf": b"%PDF-ley-1178",
            "http://test.local/ds-29894.pdf": b"%PDF-ds-29894",
        }

        FakeScraper = type(
            "FakeGacetaScraper",
            (_FakeScraper,),
            {"entries": entries, "pdf_map": pdf_map},
        )

        with (
            _patch_scraper_class(LegalSource.GACETA.value, FakeScraper),
            patch.object(
                Corpus,
                "import_content",
                autospec=True,
                side_effect=_fake_import_content,
            ),
        ):
            first = scrape_and_ingest_source.run(
                LegalSource.GACETA.value, user_id=self.user.pk
            )
            second = scrape_and_ingest_source.run(
                LegalSource.GACETA.value, user_id=self.user.pk
            )

        self.assertEqual(first["discovered"], 2)
        self.assertEqual(first["ingested"], 2)
        self.assertEqual(first["dedupe_hits"], 0)
        self.assertEqual(first["failed"], 0)

        self.assertEqual(second["discovered"], 2)
        self.assertEqual(second["ingested"], 0)
        self.assertEqual(second["dedupe_hits"], 2)
        self.assertEqual(BolivianLegalDocument.objects.count(), 2)

    def test_failed_download_counted_and_does_not_abort_batch(self):
        bad = ScrapedEntry(
            source_key=LegalSource.GACETA.value,
            pdf_url="http://test.local/missing.pdf",
            title="Missing",
        )
        good = ScrapedEntry(
            source_key=LegalSource.GACETA.value,
            pdf_url="http://test.local/ok.pdf",
            title="OK",
            suggested_area=LegalArea.OTROS,
        )

        class _PartialScraper(_FakeScraper):
            entries = [bad, good]
            pdf_map = {"http://test.local/ok.pdf": b"%PDF-ok"}

            def download_pdf(self, entry):  # type: ignore[override]
                if entry.pdf_url.endswith("missing.pdf"):
                    raise RuntimeError("404 not found")
                return self.pdf_map[entry.pdf_url]

        with (
            _patch_scraper_class(LegalSource.GACETA.value, _PartialScraper),
            patch.object(
                Corpus,
                "import_content",
                autospec=True,
                side_effect=_fake_import_content,
            ),
        ):
            summary = scrape_and_ingest_source.run(
                LegalSource.GACETA.value, user_id=self.user.pk
            )

        self.assertEqual(summary["discovered"], 2)
        self.assertEqual(summary["ingested"], 1)
        self.assertEqual(summary["failed"], 1)
        self.assertEqual(BolivianLegalDocument.objects.count(), 1)

    def test_unknown_source_key_raises(self):
        with self.assertRaises(KeyError):
            scrape_and_ingest_source.run("definitely-not-a-source")


class TestScrapeAndIngestAllFanOut(TestCase):
    def test_fan_out_enqueues_one_task_per_source(self):
        enqueued: list[str] = []

        class _FakeAsyncResult:
            def __init__(self, source: str) -> None:
                self.id = f"task-{source}"

        def _fake_delay(source_key, **kwargs):
            enqueued.append(source_key)
            return _FakeAsyncResult(source_key)

        with patch(
            "opencontractserver.bolivian_laws.tasks.scrape_and_ingest_source.delay",
            side_effect=_fake_delay,
        ):
            ids = scrape_and_ingest_all.run()

        self.assertEqual(
            sorted(enqueued),
            [LegalSource.GACETA.value, LegalSource.TCP.value, LegalSource.TSJ.value],
        )
        self.assertEqual(len(ids), 3)
