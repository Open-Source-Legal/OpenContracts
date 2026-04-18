"""Scraper for the Tribunal Supremo de Justicia (TSJ) of Bolivia.

Site: https://tsj.bo/

The TSJ publishes *autos supremos* and *sentencias* grouped by sala
(Civil, Penal, Social / Laboral, Contencioso-Administrativa, etc.).
Each resolution is typically a PDF accessible from the jurisprudence
index.

This scraper maps sala names (found in the listing context) to
:class:`LegalArea` values so the ingestion pipeline lands each PDF in
its specialist corpus automatically.
"""

from __future__ import annotations

import datetime as dt
import logging
import re
from collections.abc import Iterable
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from opencontractserver.bolivian_laws.constants import LegalArea, LegalSource
from opencontractserver.bolivian_laws.scrapers.base import (
    BaseScraper,
    ScrapedEntry,
)

logger = logging.getLogger(__name__)

_AUTO_PATTERN = re.compile(
    r"(?:auto\s+supremo|a\.s\.|sentencia)\s*(?:n[º°.]?\s*)?([0-9\-/]+)",
    re.I,
)
_DATE_PATTERN = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})")

_SALA_TO_AREA: tuple[tuple[tuple[str, ...], str], ...] = (
    (("civil",), LegalArea.CIVIL),
    (("penal",), LegalArea.PENAL),
    (("social", "laboral"), LegalArea.LABORAL),
    (("administrativ", "contencios"), LegalArea.ADMINISTRATIVO),
    (("familia",), LegalArea.FAMILIA),
    (("agrari",), LegalArea.AGRARIO),
    (("tributari", "agroambien"), LegalArea.AGRARIO),
)


def _guess_area_from_context(context: str) -> str:
    lowered = context.lower()
    for keywords, area in _SALA_TO_AREA:
        if any(k in lowered for k in keywords):
            return area
    return LegalArea.OTROS


def _parse_date(context: str) -> dt.date | None:
    match = _DATE_PATTERN.search(context)
    if not match:
        return None
    try:
        day, month, year = (int(g) for g in match.groups())
        return dt.date(year, month, day)
    except ValueError:
        return None


class TribunalSupremoJusticiaScraper(BaseScraper):
    """Scraper for https://tsj.bo/ jurisprudence listings."""

    source_key = LegalSource.TSJ.value
    default_base_url = "https://tsj.bo/"
    default_listing_paths = ("/jurisprudencia/",)
    settings_base_url_key = "BOLIVIAN_LAWS_TSJ_BASE_URL"
    settings_listing_paths_key = "BOLIVIAN_LAWS_TSJ_LISTING_PATHS"

    def extract_entries(self, *, html: str, url: str) -> Iterable[ScrapedEntry]:
        soup = BeautifulSoup(html, "html.parser")
        host = urlparse(self.base_url).netloc

        for anchor in soup.find_all("a"):
            href = (anchor.get("href") or "").strip()
            if not href or not href.lower().endswith(".pdf"):
                continue

            pdf_url = urljoin(url, href)
            if urlparse(pdf_url).netloc and urlparse(pdf_url).netloc != host:
                continue

            link_text = (anchor.get_text() or "").strip()
            parent = anchor.find_parent(["tr", "li", "article", "div"])
            context = (
                f"{link_text} | {parent.get_text(' ', strip=True)}"
                if parent is not None
                else link_text
            )

            external_id = ""
            match = _AUTO_PATTERN.search(context)
            if match:
                external_id = f"AS-{match.group(1)}"

            published_at = _parse_date(context)
            suggested_area = _guess_area_from_context(context)
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
                    "sala_hint": suggested_area,
                },
            )
