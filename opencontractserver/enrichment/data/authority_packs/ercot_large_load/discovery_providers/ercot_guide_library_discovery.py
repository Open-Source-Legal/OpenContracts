"""Discover current and historical ERCOT guide/protocol documents."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import PurePosixPath
from urllib.parse import urlsplit

from opencontractserver.pipeline.base.authority_html import (
    extract_authority_links,
    stable_source_slug,
)
from opencontractserver.pipeline.base.base_authority_discovery_provider import (
    BaseAuthorityDiscoveryProvider,
    DiscoveryCandidate,
)
from opencontractserver.utils.safe_http import safe_fetch_text

_SECTION_RE = re.compile(r"\bSection\s+(?P<section>\d+(?:\.\d+)*)\b", re.I)
_ISO_DATE_RE = re.compile(r"\b(?P<date>20\d{2}-\d{2}-\d{2})\b")
_SECTION_DATE_FILENAME_RE = re.compile(
    r"^(?P<section>\d{1,2})-(?P<date>\d{6})\.(?:docx?|pdf)$",
    re.I,
)


def _guide_family(value: str) -> str | None:
    lowered = value.casefold()
    if "planning" in lowered:
        return "ercot-planning"
    if "protocol" in lowered or "nprotocol" in lowered:
        return "ercot-protocol"
    if "operating" in lowered or "noperating" in lowered:
        return "ercot-operating"
    return None


def _publisher_filename_date(filename: str) -> str | None:
    """Parse ERCOT's known ``<section>-MMDDYY.docx`` guide filename shape."""

    match = _SECTION_DATE_FILENAME_RE.fullmatch(filename)
    if match is None:
        return None
    try:
        return datetime.strptime(match.group("date"), "%m%d%y").date().isoformat()
    except ValueError:
        return None


def parse_ercot_guide_library(html: str, *, index_url: str) -> list[DiscoveryCandidate]:
    candidates: list[DiscoveryCandidate] = []
    index_family = _guide_family(index_url)
    index_is_current = "/current" in urlsplit(index_url).path.casefold()
    for link in extract_authority_links(html, base_url=index_url):
        anchor_title = link.attribute("title") or ""
        label = link.text or anchor_title
        family = _guide_family(f"{label} {anchor_title} {link.url}") or index_family
        if family is None:
            continue
        path = urlsplit(link.url).path
        filename = PurePosixPath(path).name
        section_match = _SECTION_RE.search(f"{label} {anchor_title}")
        publisher_context = " ".join(
            (index_url, label, anchor_title, link.url)
        ).casefold()
        if (
            index_is_current
            or "/current" in path.casefold()
            or "current" in f"{label} {anchor_title}".casefold()
        ):
            current: bool | None = True
        elif any(
            marker in publisher_context
            for marker in (
                "historical",
                "history",
                "archive",
                "superseded",
                "previous",
                "prior",
            )
        ):
            current = False
        else:
            current = None
        if section_match:
            key = f"{family}:{section_match.group('section')}"
        elif current and family == "ercot-planning":
            key = "ercot-planning:9"
        else:
            key = f"{family}:{stable_source_slug(filename or label)}"
        date_match = _ISO_DATE_RE.search(f"{label} {filename}")
        effective_date = (
            date_match.group("date")
            if date_match
            else _publisher_filename_date(filename)
        )
        candidates.append(
            DiscoveryCandidate(
                canonical_key=key,
                url=link.url,
                title=label or filename,
                extra={
                    "source_identifier": filename or stable_source_slug(link.text),
                    "version_label": effective_date,
                    "effective_from": effective_date,
                    "current_version": current,
                    "current_version_review_state": (
                        "KNOWN" if current is not None else "UNKNOWN_PENDING_REVIEW"
                    ),
                    "guide_family": family,
                },
            )
        )
    return candidates


class ERCOTGuideLibraryDiscoveryProvider(BaseAuthorityDiscoveryProvider):
    title = "ERCOT Guide Library Discovery"
    description = "Discovers current and historical ERCOT rule-guide documents."
    license = "copyright-review-required"
    link_only_discovery = True

    def _fetch_index_impl(self, index_url: str, **all_kwargs) -> tuple[str, str]:
        del all_kwargs
        return safe_fetch_text(index_url)

    def _parse_index_impl(
        self, html: str, *, index_url: str, **all_kwargs
    ) -> list[DiscoveryCandidate]:
        del all_kwargs
        return parse_ercot_guide_library(html, index_url=index_url)
