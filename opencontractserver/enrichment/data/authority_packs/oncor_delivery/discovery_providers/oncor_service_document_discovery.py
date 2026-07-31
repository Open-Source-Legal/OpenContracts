"""Discover Oncor service and construction source documents."""

from __future__ import annotations

import mimetypes
import re
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
_DATE_RE = re.compile(
    r"(?:\b20\d{2}[-_/]\d{1,2}[-_/]\d{1,2}\b" r"|\b\d{1,2}[/-]\d{1,2}[/-]20\d{2}\b)"
)
_HISTORICAL_MARKERS = (
    "historical",
    "archive",
    "prior",
    "previous",
    "superseded",
)
_SERVICE_TERMS = (
    "construction",
    "electric service",
    "engineering",
    "installation",
    "metering",
    "requirement",
    "service guideline",
    "service standard",
    "specification",
)


def _authority_metadata(current: bool | None) -> dict[str, str]:
    return {
        "instrument_type": "TECHNICAL_GUIDE",
        "status": (
            "CURRENT"
            if current is True
            else "SUPERSEDED" if current is False else "PUBLISHED"
        ),
        "authority_weight": ("IMPLEMENTING" if current is True else "EVIDENTIARY"),
    }


def parse_oncor_service_documents(
    html: str, *, index_url: str
) -> list[DiscoveryCandidate]:
    """Parse every relevant Oncor service-document link on a publisher page."""

    candidates: list[DiscoveryCandidate] = []
    for link in extract_authority_links(html, base_url=index_url):
        path = urlsplit(link.url).path
        filename = PurePosixPath(path).name
        label = " ".join(part for part in (link.text, filename) if part)
        lowered = label.casefold()
        if (
            not label
            or not _DOCUMENT_PATH_RE.search(path)
            or not any(term in lowered for term in _SERVICE_TERMS)
        ):
            continue
        if "electric service guideline" in lowered:
            identifier = "electric-service-guidelines"
        else:
            identifier = stable_source_slug(link.text or PurePosixPath(filename).stem)
        if any(marker in lowered for marker in _HISTORICAL_MARKERS) or (
            _DATE_RE.search(label) is not None
        ):
            current: bool | None = False
        elif "current" in lowered:
            current = True
        else:
            current = None
        mime_type, _ = mimetypes.guess_type(filename)
        candidates.append(
            DiscoveryCandidate(
                canonical_key=f"oncor-service-guide:{identifier}",
                url=link.url,
                title=link.text or filename,
                extra={
                    "source_identifier": PurePosixPath(filename).stem,
                    "current_version": current,
                    "current_version_review_state": (
                        "KNOWN" if current is not None else "UNKNOWN_PENDING_REVIEW"
                    ),
                    "mime_type": mime_type,
                    "rights_status": "REVIEW_REQUIRED",
                    "metadata": _authority_metadata(current),
                },
            )
        )
    return candidates


class OncorServiceDocumentDiscoveryProvider(BaseAuthorityDiscoveryProvider):
    title = "Oncor Service Document Discovery"
    description = "Enumerates Oncor service documents for approved collection."
    license = "copyright-review-required"
    link_only_discovery = True

    def _fetch_index_impl(self, index_url: str, **all_kwargs) -> tuple[str, str]:
        del all_kwargs
        return safe_fetch_text(index_url)

    def _parse_index_impl(
        self, html: str, *, index_url: str, **all_kwargs
    ) -> list[DiscoveryCandidate]:
        del all_kwargs
        return parse_oncor_service_documents(html, index_url=index_url)
