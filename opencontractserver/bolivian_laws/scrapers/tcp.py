"""Scraper for the Tribunal Constitucional Plurinacional (TCP) of Bolivia.

Site: https://tcpbolivia.bo/

The TCP publishes *Sentencias Constitucionales Plurinacionales* (SCP),
*Declaraciones Constitucionales Plurinacionales* (DCP) and *Autos
Constitucionales* (AC). Every resolution is routed to the
``LegalArea.CONSTITUCIONAL`` corpus: the TCP deals exclusively with
constitutional matters, so area classification is trivial.

Metadata-wise, we try to extract the resolution number (e.g.
``SCP-0250/2012``) and the publication date from the surrounding row.
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

_RESOLUTION_PATTERN = re.compile(
    r"\b(SCP|DCP|AC)\s*[-–]?\s*(\d{1,6}/\d{4})",
    re.I,
)
_DATE_PATTERN = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})")
_ACCION_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("amparo", "amparo_constitucional"),
    ("libertad", "accion_de_libertad"),
    ("popular", "accion_popular"),
    ("cumplimiento", "accion_de_cumplimiento"),
    ("inconstitucional", "accion_de_inconstitucionalidad"),
    ("proteccion de privacidad", "proteccion_de_privacidad"),
)


def _parse_date(context: str) -> dt.date | None:
    match = _DATE_PATTERN.search(context)
    if not match:
        return None
    try:
        day, month, year = (int(g) for g in match.groups())
        return dt.date(year, month, day)
    except ValueError:
        return None


def _detect_accion(context: str) -> str | None:
    lowered = context.lower()
    for keyword, label in _ACCION_KEYWORDS:
        if keyword in lowered:
            return label
    return None


class TribunalConstitucionalScraper(BaseScraper):
    """Scraper for https://tcpbolivia.bo/ constitutional jurisprudence."""

    source_key = LegalSource.TCP.value
    default_base_url = "https://tcpbolivia.bo/"
    default_listing_paths = ("/jurisprudencia/",)
    settings_base_url_key = "BOLIVIAN_LAWS_TCP_BASE_URL"
    settings_listing_paths_key = "BOLIVIAN_LAWS_TCP_LISTING_PATHS"

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
            resolution_type = ""
            match = _RESOLUTION_PATTERN.search(context)
            if match:
                resolution_type = match.group(1).upper()
                external_id = f"{resolution_type}-{match.group(2)}"

            published_at = _parse_date(context)
            accion = _detect_accion(context)
            title = (link_text or href.rsplit("/", 1)[-1])[:1024]

            metadata = {
                "listing_url": url,
                "context": context[:500],
            }
            if resolution_type:
                metadata["resolution_type"] = resolution_type
            if accion:
                metadata["accion"] = accion

            yield ScrapedEntry(
                source_key=self.source_key,
                pdf_url=pdf_url,
                title=title,
                external_id=external_id,
                published_at=published_at,
                suggested_area=LegalArea.CONSTITUCIONAL,
                metadata=metadata,
            )
