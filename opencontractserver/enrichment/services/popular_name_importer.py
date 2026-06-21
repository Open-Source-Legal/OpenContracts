"""Importer for the OLRC USC popular-name table (Phase 3 "popular_name" source).

The Office of Law Revision Counsel publishes a public-domain *popular names*
table (``https://uscode.house.gov/popularnames/popularnames.htm``) listing every
named Act and its codification. Each entry is machine-readable:

    <div class='popular-name-table-entry' id='...'>
      <p class='popular-name'>Securities Exchange Act of 1934</p>
      <p class='popular-name-information' content-type='cite' ... usckey='15:78a'>
        June 6, <a ...>1934, ch. 404</a>,
        <a href="/statviewer.htm?volume=48&amp;page=881">48 Stat. 881</a>
        (<a ...>15 U.S.C. 78a</a> et seq.)
      </p>
    </div>

The reliably-derivable, grammar-aligned bridge is **Statutes-at-Large ↔ USC**:
the ``usckey='{title}:{section}'`` attribute gives the USC codification and the
``statviewer`` link gives the Stat. ``volume``/``page`` — so a filing citing
"48 Stat. 881" (grammar key ``stat:48.881``) resolves to the ingested USC
section ``usc-15:78a``. This scales across the whole table (one+ cite row per
Act). The *section-level* act↔USC correspondence (``exchange-act:10`` →
``usc-15:78j``) is act-*start* granular in this table and is supplied instead by
the curated baseline + the USLM ``<sourceCredit>`` harvest.

The importer is idempotent and source-scoped (never clobbers
baseline/manual/uslm rows — see ``authority_equivalence_ingest``).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from opencontractserver.enrichment.services.authority_equivalence_ingest import (
    CREATED,
    SKIPPED_INVALID,
    SKIPPED_OWNED,
    UPDATED,
    upsert_equivalence,
)
from opencontractserver.utils.safe_http import safe_fetch_text

logger = logging.getLogger(__name__)

OLRC_POPULAR_NAMES_URL = "https://uscode.house.gov/popularnames/popularnames.htm"

# Table-derived bridges are high- but not perfect-confidence (the Stat. page is
# the Act's start; whole-act citations are coarser than a section cite).
_POPULAR_NAME_CONFIDENCE = 0.85

# One Act block. Splitting on the entry div keeps each Act's name + cite rows
# together so a bridge can be tagged with its Act name (provenance note).
_ENTRY_SPLIT_RE = re.compile(
    r"<div[^>]*class=['\"]popular-name-table-entry['\"]", re.IGNORECASE
)
_NAME_RE = re.compile(
    r"<p[^>]*class=['\"]popular-name['\"][^>]*>(?P<name>.*?)</p>",
    re.IGNORECASE | re.DOTALL,
)
# A cite row carries the USC codification in its ``usckey`` attribute.
_INFO_RE = re.compile(
    r"<p[^>]*class=['\"]popular-name-information['\"][^>]*?"
    r"usckey=['\"](?P<title>\d+):(?P<section>[0-9A-Za-z.\-]+)['\"]"
    r"[^>]*>(?P<body>.*?)</p>",
    re.IGNORECASE | re.DOTALL,
)
# The statviewer link inside a cite row: volume + page (HTML-escaped ``&amp;``).
_STAT_RE = re.compile(
    r"statviewer\.htm\?volume=(?P<vol>\d+)&(?:amp;)?page=(?P<page>\d+)",
    re.IGNORECASE,
)
_TAG_RE = re.compile(r"<[^>]+>")


@dataclass
class PopularNameBridge:
    """One derivable ``stat ↔ usc`` bridge from a popular-name cite row."""

    stat_key: str  # e.g. "stat:48.881"
    usc_key: str  # e.g. "usc-15:78a"
    act_name: str  # e.g. "Securities Exchange Act of 1934"


def _strip_tags(html: str) -> str:
    return re.sub(r"\s+", " ", _TAG_RE.sub("", html or "")).strip()


def parse_popular_name_table(html: str) -> list[PopularNameBridge]:
    """Parse the OLRC popular-names HTML into ``stat ↔ usc`` bridges (pure).

    Skips entries / rows lacking a ``usckey`` or a ``statviewer`` link. Returns
    bridges in document order (one Act may yield several — original + amendments).
    """
    bridges: list[PopularNameBridge] = []
    for piece in _ENTRY_SPLIT_RE.split(html or "")[1:]:
        name_match = _NAME_RE.search(piece)
        act_name = _strip_tags(name_match.group("name")) if name_match else ""
        for info in _INFO_RE.finditer(piece):
            stat = _STAT_RE.search(info.group("body"))
            if stat is None:
                continue
            bridges.append(
                PopularNameBridge(
                    stat_key=f"stat:{stat.group('vol')}.{stat.group('page')}",
                    usc_key=f"usc-{info.group('title')}:{info.group('section')}",
                    act_name=act_name,
                )
            )
    return bridges


class PopularNameTableImporter:
    """Fetch + parse the OLRC popular-name table and upsert ``stat ↔ usc`` rows."""

    SOURCE = "popular_name"

    @classmethod
    def import_table(
        cls,
        *,
        html: str | None = None,
        url: str | None = None,
    ) -> dict:
        """Import bridges, returning ``{created, updated, skipped_owned,
        skipped_invalid, parsed}``.

        ``html`` short-circuits the fetch (used by tests / offline re-runs);
        otherwise the table is fetched from ``url`` (default
        :data:`OLRC_POPULAR_NAMES_URL`) via the SSRF-safe allowlisted client.
        """
        if html is None:
            html, _ = safe_fetch_text(url or OLRC_POPULAR_NAMES_URL)

        bridges = parse_popular_name_table(html)
        counts = {CREATED: 0, UPDATED: 0, SKIPPED_OWNED: 0, SKIPPED_INVALID: 0}
        for bridge in bridges:
            outcome = upsert_equivalence(
                from_key=bridge.stat_key,
                to_key=bridge.usc_key,
                source=cls.SOURCE,
                confidence=_POPULAR_NAME_CONFIDENCE,
                note=(
                    f"OLRC popular-name table: {bridge.act_name}"
                    if bridge.act_name
                    else "OLRC popular-name table"
                ),
            )
            counts[outcome] = counts.get(outcome, 0) + 1

        summary = {
            "created": counts[CREATED],
            "updated": counts[UPDATED],
            "skipped_owned": counts[SKIPPED_OWNED],
            "skipped_invalid": counts[SKIPPED_INVALID],
            "parsed": len(bridges),
        }
        logger.info("PopularNameTableImporter: %s", summary)
        return summary
