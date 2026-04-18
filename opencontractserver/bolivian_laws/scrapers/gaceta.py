"""Scraper for the Gaceta Oficial de Bolivia.

Site: https://gacetaoficialdebolivia.gob.bo/

The Gaceta publishes laws (Leyes), decretos supremos, resoluciones and
other official norms. Its listing page HTML structure is not formally
documented, so this scraper is deliberately defensive: it accepts any
``<a>`` tag that points to a PDF on the same host and enriches the
:class:`ScrapedEntry` with whatever metadata it can extract from the
surrounding row/text (year, issue number, publication date, rough
topic).

The exact listing URL(s) are read from ``settings.BOLIVIAN_LAWS_GACETA_*``
so that deployments can point at whichever index the Gaceta currently
exposes without touching code.
"""

from __future__ import annotations

import datetime as dt
import logging
import re
from collections.abc import Iterable, Iterator
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from opencontractserver.bolivian_laws.constants import LegalArea, LegalSource
from opencontractserver.bolivian_laws.scrapers.base import (
    BaseScraper,
    ScrapedEntry,
)

logger = logging.getLogger(__name__)

_DATE_PATTERNS = (
    re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})"),
    re.compile(r"(\d{4})-(\d{1,2})-(\d{1,2})"),
)
_ISSUE_PATTERN = re.compile(
    r"(?:gaceta|edición|edicion|nro\.?|n[º°])\s*([0-9A-Za-z\-]+)", re.I
)
_LEY_PATTERN = re.compile(r"\bley(?:\s+(?:n[º°.]?\s*)?(\d+))?", re.I)
_DECRETO_PATTERN = re.compile(r"decreto\s+supremo\s+(?:n[º°.]?\s*)?([0-9]+)", re.I)

# Lightweight keyword heuristics for the Gaceta. Not meant to be
# authoritative — the optional LLM classifier takes over when this
# returns OTROS.
_AREA_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (LegalArea.TRIBUTARIO, ("tributari", "impuesto", "sin ", "iva", "it ")),
    (LegalArea.LABORAL, ("laboral", "trabajo", "sindicato", "salario")),
    (LegalArea.PENAL, ("penal", "delito", "código penal")),
    (LegalArea.CIVIL, ("civil", "código civil", "obligaciones")),
    (LegalArea.FAMILIA, ("familia", "menor", "niñez", "adolescen")),
    (LegalArea.AGRARIO, ("agrari", "inra", "tierras", "comunitaria")),
    (LegalArea.AMBIENTAL, ("ambiental", "medio ambiente", "ley 1333")),
    (LegalArea.COMERCIAL, ("comercial", "empresa", "sociedad")),
    (LegalArea.ADMINISTRATIVO, ("administrativ", "safco", "contrataci")),
    (LegalArea.CONSTITUCIONAL, ("constitucional", "cpe", "derechos fundament")),
)


def _guess_area(text: str) -> str:
    lowered = text.lower()
    for area, keywords in _AREA_KEYWORDS:
        if any(k in lowered for k in keywords):
            return area
    return LegalArea.OTROS


def _parse_spanish_date(text: str) -> dt.date | None:
    for pattern in _DATE_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        groups = match.groups()
        try:
            if pattern is _DATE_PATTERNS[0]:
                day, month, year = (int(g) for g in groups)
            else:
                year, month, day = (int(g) for g in groups)
            return dt.date(year, month, day)
        except ValueError:
            continue
    return None


class GacetaOficialScraper(BaseScraper):
    """Scraper for https://gacetaoficialdebolivia.gob.bo/."""

    source_key = LegalSource.GACETA.value
    default_base_url = "https://gacetaoficialdebolivia.gob.bo/"
    default_listing_paths = ("/",)
    settings_base_url_key = "BOLIVIAN_LAWS_GACETA_BASE_URL"
    settings_listing_paths_key = "BOLIVIAN_LAWS_GACETA_LISTING_PATHS"

    def extract_entries(self, *, html: str, url: str) -> Iterable[ScrapedEntry]:
        soup = BeautifulSoup(html, "html.parser")
        host = urlparse(self.base_url).netloc

        for anchor in soup.find_all("a"):
            href = (anchor.get("href") or "").strip()
            if not href:
                continue
            if not href.lower().endswith(".pdf"):
                continue

            pdf_url = urljoin(url, href)
            # Stay on the same host to avoid following off-site PDFs
            if urlparse(pdf_url).netloc and urlparse(pdf_url).netloc != host:
                continue

            link_text = (anchor.get_text() or "").strip()
            context = link_text
            # Also inspect the parent row for date/issue hints
            parent = anchor.find_parent(["tr", "li", "article", "div"])
            if parent is not None:
                context = f"{link_text} | {parent.get_text(' ', strip=True)}"

            external_id = ""
            ley_match = _LEY_PATTERN.search(context)
            decreto_match = _DECRETO_PATTERN.search(context)
            issue_match = _ISSUE_PATTERN.search(context)
            if ley_match and ley_match.group(1):
                external_id = f"LEY-{ley_match.group(1)}"
            elif decreto_match:
                external_id = f"DS-{decreto_match.group(1)}"
            elif issue_match:
                external_id = f"GACETA-{issue_match.group(1)}"

            published_at = _parse_spanish_date(context)
            suggested_area = _guess_area(context)
            title = (link_text or href.rsplit("/", 1)[-1])[:1024]

            yield ScrapedEntry(
                source_key=self.source_key,
                pdf_url=pdf_url,
                title=title,
                external_id=external_id,
                published_at=published_at,
                suggested_area=suggested_area,
                metadata={
                    "listing_url": url,
                    "context": context[:500],
                },
            )

    def iter_entries(  # type: ignore[override]
        self,
        *,
        since: dt.date | None = None,
        max_entries: int | None = None,
    ) -> Iterator[ScrapedEntry]:
        seen_urls: set[str] = set()
        for entry in super().iter_entries(since=since, max_entries=None):
            if entry.pdf_url in seen_urls:
                continue
            seen_urls.add(entry.pdf_url)
            yield entry
            if max_entries is not None and len(seen_urls) >= max_entries:
                return
