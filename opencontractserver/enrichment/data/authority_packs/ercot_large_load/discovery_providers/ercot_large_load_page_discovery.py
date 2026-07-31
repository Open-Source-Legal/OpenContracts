"""Discover ERCOT large-load forms, attestations, FAQs, and guides."""

from __future__ import annotations

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

_FORM_WORDS = (
    "form",
    "attestation",
    "load information",
    "lif",
    "study request",
    "worksheet",
    "template",
)
_GUIDE_WORDS = ("guide", "guidance", "instruction", "faq", "timeline")
_PLANNING_SECTION_RE = re.compile(
    r"\bPlanning Guide\s+(?:(?:Section|Sec\.?)\s*|§\s*)" r"(?P<section>\d+(?:\.\d+)*)",
    re.I,
)
_PROTOCOL_SECTION_RE = re.compile(
    r"\bProtocol\s+(?:(?:Section|Sec\.?)\s*|§\s*)" r"(?P<section>\d+(?:\.\d+)*)",
    re.I,
)
_VERSION_RE = re.compile(r"\bv(?:ersion\s*)?(?P<version>\d+(?:\.\d+)*)\b", re.I)


def _authority_metadata(label: str, *, current_version: bool) -> dict[str, str]:
    """Describe a discovered implementation artifact without fetching it."""

    lowered = label.casefold()
    if "attestation" in lowered:
        instrument_type = "ATTESTATION"
    elif "faq" in lowered or "frequently asked" in lowered:
        instrument_type = "FAQ"
    elif any(
        term in lowered for term in ("guide", "guidance", "instruction", "timeline")
    ):
        instrument_type = "TECHNICAL_GUIDE"
    else:
        instrument_type = "FORM"
    return {
        "instrument_type": instrument_type,
        "status": "CURRENT" if current_version else "SUPERSEDED",
    }


def parse_ercot_large_load_page(
    html: str, *, index_url: str
) -> list[DiscoveryCandidate]:
    candidates: list[DiscoveryCandidate] = []
    for link in extract_authority_links(html, base_url=index_url):
        path = urlsplit(link.url).path
        filename = PurePosixPath(path).name
        label = link.text or filename
        lowered = label.casefold()
        if any(word in lowered for word in _FORM_WORDS):
            prefix = "ercot-form"
        elif any(word in lowered for word in _GUIDE_WORDS):
            # The pack's declared implementation-material namespace is
            # ``ercot-form``; the record's instrument_type below distinguishes
            # forms, FAQs, attestations, and technical guides.
            prefix = "ercot-form"
        else:
            continue
        source_slug = stable_source_slug(filename or label)
        version_match = _VERSION_RE.search(label)
        version = f"v{version_match.group('version')}" if version_match else None
        if version and not source_slug.endswith(version):
            source_slug = f"{source_slug}:{version}"
        governing_keys = [
            f"ercot-planning:{match.group('section')}"
            for match in _PLANNING_SECTION_RE.finditer(label)
        ] + [
            f"ercot-protocol:{match.group('section')}"
            for match in _PROTOCOL_SECTION_RE.finditer(label)
        ]
        current_version = "superseded" not in lowered and "archive" not in lowered
        candidates.append(
            DiscoveryCandidate(
                canonical_key=f"{prefix}:{source_slug}",
                url=link.url,
                title=label,
                extra={
                    "source_identifier": filename or source_slug,
                    "version_label": version,
                    "current_version": current_version,
                    "governing_keys": governing_keys,
                    "metadata": _authority_metadata(
                        label,
                        current_version=current_version,
                    ),
                },
            )
        )
    return candidates


class ERCOTLargeLoadPageDiscoveryProvider(BaseAuthorityDiscoveryProvider):
    title = "ERCOT Large Load Integration Page Discovery"
    description = "Discovers forms and guidance from ERCOT's large-load page."
    license = "copyright-review-required"
    link_only_discovery = True

    def _fetch_index_impl(self, index_url: str, **all_kwargs) -> tuple[str, str]:
        del all_kwargs
        return safe_fetch_text(index_url)

    def _parse_index_impl(
        self, html: str, *, index_url: str, **all_kwargs
    ) -> list[DiscoveryCandidate]:
        del all_kwargs
        return parse_ercot_large_load_page(html, index_url=index_url)
