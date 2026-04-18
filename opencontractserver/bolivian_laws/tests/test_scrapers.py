"""Tests for the Bolivian legal source scrapers.

The scrapers are driven by ``httpx.MockTransport`` so no real HTTP
requests are made. Each source's HTML is a tiny, self-contained fixture
that mimics the structural features the parser relies on (anchors
ending in ``.pdf``, surrounding rows with dates and resolution IDs).
"""

from __future__ import annotations

import datetime as dt

import httpx
from django.test import SimpleTestCase

from opencontractserver.bolivian_laws.constants import LegalArea, LegalSource
from opencontractserver.bolivian_laws.scrapers import (
    SCRAPERS,
    ScrapedEntry,
    get_scraper_class,
)
from opencontractserver.bolivian_laws.scrapers.gaceta import GacetaOficialScraper
from opencontractserver.bolivian_laws.scrapers.tcp import (
    TribunalConstitucionalScraper,
)
from opencontractserver.bolivian_laws.scrapers.tsj import (
    TribunalSupremoJusticiaScraper,
)

GACETA_HTML = """
<html><body>
<table>
  <tr>
    <td>Ley N° 1178 SAFCO — 20/07/1990</td>
    <td><a href="/pdfs/ley-1178.pdf">Descargar PDF</a></td>
  </tr>
  <tr>
    <td>Decreto Supremo 29894 — 07/02/2009</td>
    <td><a href="/pdfs/ds-29894.pdf">Descargar PDF</a></td>
  </tr>
  <tr>
    <td>Noticia sin PDF</td>
    <td><a href="https://otra.bo/externo.pdf">Externo</a></td>
  </tr>
</table>
</body></html>
"""

TSJ_HTML = """
<html><body>
<ul>
  <li>Sala Penal — Auto Supremo 123/2023, 15/03/2023 —
    <a href="/docs/as-123-2023.pdf">PDF</a>
  </li>
  <li>Sala Civil — Auto Supremo 456/2022, 10/11/2022 —
    <a href="/docs/as-456-2022.pdf">PDF</a>
  </li>
  <li>Sala Social y Administrativa — Sentencia 77/2024 —
    <a href="/docs/ss-77-2024.pdf">PDF</a>
  </li>
</ul>
</body></html>
"""

TCP_HTML = """
<html><body>
<div>
  <article>
    <h3>SCP 0250/2012 — Acción de Amparo Constitucional</h3>
    <p>Publicada el 12/05/2012</p>
    <a href="/r/scp-0250-2012.pdf">Ver resolución</a>
  </article>
  <article>
    <h3>DCP 0001/2020</h3>
    <p>Acción de Inconstitucionalidad — 03/02/2020</p>
    <a href="/r/dcp-0001-2020.pdf">Ver resolución</a>
  </article>
</body></html>
"""


def _mock_transport(html: str) -> httpx.MockTransport:
    pdf_bytes = b"%PDF-1.4 fake content"

    def _handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith(".pdf"):
            return httpx.Response(200, content=pdf_bytes)
        return httpx.Response(200, text=html)

    return httpx.MockTransport(_handler)


def _make_client(html: str) -> httpx.Client:
    return httpx.Client(
        transport=_mock_transport(html),
        base_url="http://test.local",
        follow_redirects=True,
    )


class TestGacetaScraper(SimpleTestCase):
    def test_extracts_pdf_entries_with_metadata(self):
        client = _make_client(GACETA_HTML)
        scraper = GacetaOficialScraper(
            client=client,
            request_delay_seconds=0,
            base_url="http://test.local/",
            listing_paths=("/",),
        )
        entries = list(scraper.iter_entries())
        self.assertEqual(len(entries), 2)

        by_id = {e.external_id: e for e in entries}
        self.assertIn("LEY-1178", by_id)
        self.assertIn("DS-29894", by_id)

        ley = by_id["LEY-1178"]
        self.assertEqual(ley.source_key, LegalSource.GACETA.value)
        self.assertEqual(ley.published_at, dt.date(1990, 7, 20))
        # SAFCO is administrative-flavoured
        self.assertEqual(ley.suggested_area, LegalArea.ADMINISTRATIVO)

        decreto = by_id["DS-29894"]
        self.assertEqual(decreto.published_at, dt.date(2009, 2, 7))

    def test_skips_entries_older_than_since(self):
        client = _make_client(GACETA_HTML)
        scraper = GacetaOficialScraper(
            client=client,
            request_delay_seconds=0,
            base_url="http://test.local/",
            listing_paths=("/",),
        )
        entries = list(scraper.iter_entries(since=dt.date(2000, 1, 1)))
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].external_id, "DS-29894")

    def test_download_pdf_returns_bytes(self):
        client = _make_client(GACETA_HTML)
        scraper = GacetaOficialScraper(
            client=client,
            request_delay_seconds=0,
            base_url="http://test.local/",
            listing_paths=("/",),
        )
        entry = next(iter(scraper.iter_entries()))
        pdf = scraper.download_pdf(entry)
        self.assertTrue(pdf.startswith(b"%PDF"))

    def test_dedupes_pdf_urls_within_run(self):
        dup_html = GACETA_HTML + ('<a href="/pdfs/ley-1178.pdf">Enlace duplicado</a>')
        client = _make_client(dup_html)
        scraper = GacetaOficialScraper(
            client=client,
            request_delay_seconds=0,
            base_url="http://test.local/",
            listing_paths=("/",),
        )
        entries = list(scraper.iter_entries())
        urls = [e.pdf_url for e in entries]
        self.assertEqual(len(urls), len(set(urls)))


class TestTsjScraper(SimpleTestCase):
    def test_maps_sala_to_area(self):
        client = _make_client(TSJ_HTML)
        scraper = TribunalSupremoJusticiaScraper(
            client=client,
            request_delay_seconds=0,
            base_url="http://test.local/",
            listing_paths=("/jurisprudencia/",),
        )
        entries = list(scraper.iter_entries())
        self.assertEqual(len(entries), 3)
        areas = {e.pdf_url.rsplit("/", 1)[-1]: e.suggested_area for e in entries}
        self.assertEqual(areas["as-123-2023.pdf"], LegalArea.PENAL)
        self.assertEqual(areas["as-456-2022.pdf"], LegalArea.CIVIL)
        self.assertEqual(areas["ss-77-2024.pdf"], LegalArea.LABORAL)

    def test_extracts_resolution_number(self):
        client = _make_client(TSJ_HTML)
        scraper = TribunalSupremoJusticiaScraper(
            client=client,
            request_delay_seconds=0,
            base_url="http://test.local/",
            listing_paths=("/jurisprudencia/",),
        )
        entries = list(scraper.iter_entries())
        ids = {e.external_id for e in entries}
        self.assertIn("AS-123/2023", ids)


class TestTcpScraper(SimpleTestCase):
    def test_all_entries_routed_to_constitucional(self):
        client = _make_client(TCP_HTML)
        scraper = TribunalConstitucionalScraper(
            client=client,
            request_delay_seconds=0,
            base_url="http://test.local/",
            listing_paths=("/jurisprudencia/",),
        )
        entries = list(scraper.iter_entries())
        self.assertEqual(len(entries), 2)
        self.assertTrue(
            all(e.suggested_area == LegalArea.CONSTITUCIONAL for e in entries)
        )

    def test_extracts_resolution_id_and_accion(self):
        client = _make_client(TCP_HTML)
        scraper = TribunalConstitucionalScraper(
            client=client,
            request_delay_seconds=0,
            base_url="http://test.local/",
            listing_paths=("/jurisprudencia/",),
        )
        entries = {e.external_id: e for e in scraper.iter_entries()}
        self.assertIn("SCP-0250/2012", entries)
        self.assertEqual(
            entries["SCP-0250/2012"].metadata.get("accion"),
            "amparo_constitucional",
        )
        self.assertIn("DCP-0001/2020", entries)
        self.assertEqual(
            entries["DCP-0001/2020"].metadata.get("accion"),
            "accion_de_inconstitucionalidad",
        )


class TestScraperRegistry(SimpleTestCase):
    def test_registry_covers_all_scraped_sources(self):
        self.assertEqual(
            set(SCRAPERS.keys()),
            {LegalSource.GACETA.value, LegalSource.TSJ.value, LegalSource.TCP.value},
        )

    def test_get_scraper_class_unknown_key_raises(self):
        with self.assertRaises(KeyError):
            get_scraper_class("no-such-source")


class TestBaseScraperDefensiveness(SimpleTestCase):
    def test_broken_listing_page_does_not_abort_run(self):
        """A 500 response on one page must not break the iterator."""

        def _handler(request: httpx.Request) -> httpx.Response:
            if "broken" in request.url.path:
                return httpx.Response(500, text="server error")
            if request.url.path.endswith(".pdf"):
                return httpx.Response(200, content=b"%PDF-x")
            return httpx.Response(200, text=GACETA_HTML)

        client = httpx.Client(
            transport=httpx.MockTransport(_handler),
            base_url="http://test.local",
            follow_redirects=True,
        )
        scraper = GacetaOficialScraper(
            client=client,
            request_delay_seconds=0,
            base_url="http://test.local/",
            listing_paths=("/broken/", "/ok/"),
        )
        entries = list(scraper.iter_entries())
        # The /ok/ listing still yields the two entries from GACETA_HTML
        self.assertEqual(len(entries), 2)


class TestScrapedEntryShape(SimpleTestCase):
    def test_as_dict_serialises_date(self):
        entry = ScrapedEntry(
            source_key="gaceta",
            pdf_url="http://x/y.pdf",
            title="t",
            published_at=dt.date(2024, 1, 2),
        )
        payload = entry.as_dict()
        self.assertEqual(payload["published_at"], "2024-01-02")
