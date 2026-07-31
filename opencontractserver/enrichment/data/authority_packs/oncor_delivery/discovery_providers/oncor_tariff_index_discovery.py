"""Discover current and historical Oncor tariff documents."""

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

_DOCUMENT_PATH_RE = re.compile(r"\.(?:pdf|docx?|xlsx?|html?)$", re.I)
_ISO_DATE_RE = re.compile(r"\b(?P<date>20\d{2}[-_/]\d{2}[-_/]\d{2})\b")
_US_DATE_RE = re.compile(
    r"\b(?P<month>\d{1,2})[/-](?P<day>\d{1,2})[/-](?P<year>20\d{2})\b"
)
_RIDER_RE = re.compile(r"\bRider\s+(?P<name>[A-Z][A-Z0-9-]{1,20})\b", re.I)
_HISTORICAL_MARKERS = (
    "historical",
    "archive",
    "prior",
    "previous",
    "superseded",
)


def _authority_metadata(current: bool | None) -> dict[str, str]:
    return {
        "instrument_type": "TARIFF",
        "status": (
            "CURRENT"
            if current is True
            else "SUPERSEDED" if current is False else "PUBLISHED"
        ),
        "authority_weight": ("CONTROLLING" if current is True else "EVIDENTIARY"),
    }


def _document_date(value: str) -> str | None:
    iso_match = _ISO_DATE_RE.search(value)
    if iso_match is not None:
        return iso_match.group("date").replace("_", "-").replace("/", "-")
    us_match = _US_DATE_RE.search(value)
    if us_match is None:
        return None
    try:
        return (
            datetime(
                int(us_match.group("year")),
                int(us_match.group("month")),
                int(us_match.group("day")),
            )
            .date()
            .isoformat()
        )
    except ValueError:
        return None


def _tariff_identity(label: str) -> tuple[str, str] | None:
    """Return ``(prefix, identifier)`` for one tariff link label."""

    lowered = label.casefold()
    rider_match = _RIDER_RE.search(label)
    if rider_match is not None:
        return "oncor-rider", stable_source_slug(rider_match.group("name"))
    if "rate code" in lowered:
        return "oncor-tariff", "rate-codes"
    if "retail delivery" in lowered or "tariff for delivery service" in lowered:
        return "oncor-tariff", "retail-delivery"
    if "wholesale" in lowered and ("tariff" in lowered or "transmission" in lowered):
        return "oncor-tariff", "wholesale-transmission"
    if "transmission" in lowered and ("tariff" in lowered or "rate" in lowered):
        return "oncor-tariff", "transmission"
    if "rate schedule" in lowered:
        return "oncor-tariff", "rate-schedules"
    if "tariff" in lowered:
        return "oncor-tariff", stable_source_slug(label)
    return None


def parse_oncor_tariff_index(html: str, *, index_url: str) -> list[DiscoveryCandidate]:
    """Parse an already-fetched Oncor tariff listing without network access."""

    candidates: list[DiscoveryCandidate] = []
    for link in extract_authority_links(html, base_url=index_url):
        path = urlsplit(link.url).path
        filename = PurePosixPath(path).name
        label = " ".join(part for part in (link.text, filename) if part)
        if not label or not _DOCUMENT_PATH_RE.search(path):
            continue
        identity = _tariff_identity(label)
        if identity is None:
            continue
        prefix, base_identifier = identity
        lowered = label.casefold()
        version_date = _document_date(label)
        historical = any(marker in lowered for marker in _HISTORICAL_MARKERS)
        has_current_marker = "current" in lowered
        if historical or version_date is not None:
            current: bool | None = False
        elif has_current_marker:
            current = True
        else:
            # An undated generic publisher link is not evidence that the work is
            # the controlling tariff.  Preserve an explicit unknown state.
            current = None
        identifier = base_identifier
        parent_key: str | None = None
        if current is False:
            version_token = version_date or stable_source_slug(
                PurePosixPath(filename).stem
            )
            identifier = f"{base_identifier}-{version_token}"
            parent_key = f"{prefix}:{base_identifier}"
        candidates.append(
            DiscoveryCandidate(
                canonical_key=f"{prefix}:{identifier}",
                url=link.url,
                title=link.text or filename,
                extra={
                    "source_identifier": PurePosixPath(filename).stem,
                    "current_version": current,
                    "parent_key": parent_key,
                    "version_label": version_date
                    or (PurePosixPath(filename).stem if current is False else None),
                    "effective_from": version_date,
                    "current_version_review_state": (
                        "KNOWN" if current is not None else "UNKNOWN_PENDING_REVIEW"
                    ),
                    "rights_status": "REVIEW_REQUIRED",
                    "metadata": _authority_metadata(current),
                },
            )
        )
    return candidates


class OncorTariffIndexDiscoveryProvider(BaseAuthorityDiscoveryProvider):
    title = "Oncor Tariff Index Discovery"
    description = "Enumerates Oncor tariff links without ingesting linked works."
    license = "copyright-review-required"
    link_only_discovery = True

    def _fetch_index_impl(self, index_url: str, **all_kwargs) -> tuple[str, str]:
        del all_kwargs
        return safe_fetch_text(index_url)

    def _parse_index_impl(
        self, html: str, *, index_url: str, **all_kwargs
    ) -> list[DiscoveryCandidate]:
        del all_kwargs
        return parse_oncor_tariff_index(html, index_url=index_url)
