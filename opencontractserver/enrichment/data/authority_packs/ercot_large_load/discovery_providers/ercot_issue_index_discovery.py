"""Discover ERCOT NPRR and PGRR issue pages."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import PurePosixPath
from urllib.parse import unquote, urlsplit

from opencontractserver.enrichment.authority_sources import (
    AuthorityWeight,
    InstrumentType,
    SourceStatus,
)
from opencontractserver.enrichment.data.authority_packs.ercot_large_load.issue_identity import (
    classify_ercot_issue_attachment,
)
from opencontractserver.pipeline.base.authority_html import extract_authority_links
from opencontractserver.pipeline.base.base_authority_discovery_provider import (
    BaseAuthorityDiscoveryProvider,
    DiscoveryCandidate,
)
from opencontractserver.utils.safe_http import safe_fetch_text

_ISSUE_PATH_RE = re.compile(
    r"/mktrules/issues/(?P<family>NPRR|PGRR)(?P<number>\d+)/?$", re.I
)
_ATTACHMENT_FILENAME_RE = re.compile(
    r"(?P<filename>"
    r"(?P<number>\d+)(?P<family>NPRR|PGRR)-(?P<item>\d+)-"
    r"(?:(?P<dated_descriptor>.+)-(?P<date>\d{6})|(?P<descriptor>.+))"
    r"\.(?P<extension>docx?|pdf|xlsx?|xls)"
    r")",
    re.I,
)
_ISSUE_SUMMARY_METADATA = {
    "instrument_type": InstrumentType.REVISION_REQUEST.value,
    "status": SourceStatus.PUBLISHED.value,
    "authority_weight": AuthorityWeight.EVIDENTIARY.value,
}


def _attachment_date(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        return datetime.strptime(value, "%m%d%y").date().isoformat()
    except ValueError:
        return None


def _detail_identity(index_url: str) -> tuple[str, str] | None:
    match = _ISSUE_PATH_RE.search(urlsplit(index_url).path)
    if match is None:
        return None
    return match.group("family").lower(), match.group("number")


def parse_ercot_issue_index(html: str, *, index_url: str) -> list[DiscoveryCandidate]:
    candidates: list[DiscoveryCandidate] = []
    detail_identity = _detail_identity(index_url)
    if detail_identity is not None:
        detail_family, detail_number = detail_identity
        candidates.append(
            DiscoveryCandidate(
                canonical_key=f"ercot-{detail_family}:{detail_number}",
                url=index_url,
                title=f"{detail_family.upper()}{detail_number}",
                extra={
                    "family": detail_family,
                    "number": detail_number,
                    "source_identifier": f"{detail_family.upper()}{detail_number}",
                    "record_scope": "issue-summary",
                    "metadata": dict(_ISSUE_SUMMARY_METADATA),
                },
            )
        )

    for link in extract_authority_links(html, base_url=index_url):
        match = _ISSUE_PATH_RE.search(urlsplit(link.url).path)
        if match is not None:
            family = match.group("family").lower()
            number = match.group("number")
            source_identifier = f"{family.upper()}{number}"
            candidates.append(
                DiscoveryCandidate(
                    canonical_key=f"ercot-{family}:{number}",
                    url=link.url,
                    title=link.text or source_identifier,
                    extra={
                        "family": family,
                        "number": number,
                        "source_identifier": source_identifier,
                        "record_scope": "issue-summary",
                        "metadata": dict(_ISSUE_SUMMARY_METADATA),
                    },
                )
            )
            continue

        # An issue detail page exposes a numbered official attachment chain.
        # The item sequence is the stable publisher identity; descriptor/date
        # remain metadata and may be corrected without changing the key.
        if detail_identity is None:
            continue
        path_filename = unquote(PurePosixPath(urlsplit(link.url).path).name)
        attachment_match = _ATTACHMENT_FILENAME_RE.search(
            f"{path_filename} {link.text} {link.attribute('title') or ''}"
        )
        if attachment_match is None:
            continue
        family = attachment_match.group("family").lower()
        number = attachment_match.group("number")
        if (family, number) != detail_identity:
            continue
        item = str(int(attachment_match.group("item")))
        filename = attachment_match.group("filename")
        raw_descriptor = attachment_match.group(
            "dated_descriptor"
        ) or attachment_match.group("descriptor")
        descriptor = re.sub(r"[-_]+", " ", raw_descriptor).strip()
        filed_date = _attachment_date(attachment_match.group("date"))
        instrument_type, authority_weight = classify_ercot_issue_attachment(
            descriptor,
            item_sequence=item,
        )
        candidates.append(
            DiscoveryCandidate(
                canonical_key=f"ercot-{family}:{number}:item:{item}",
                url=link.url,
                title=link.text or descriptor or filename,
                extra={
                    "family": family,
                    "number": number,
                    "item_sequence": item,
                    "descriptor": descriptor,
                    "filename": filename,
                    "source_identifier": PurePosixPath(filename).stem,
                    "filed_date": filed_date,
                    "version_label": (
                        f"item-{item}-{filed_date}" if filed_date else f"item-{item}"
                    ),
                    "parent_key": f"ercot-{family}:{number}",
                    "record_scope": "issue-attachment",
                    "source_extension": attachment_match.group("extension").lower(),
                    "metadata": {
                        "instrument_type": instrument_type.value,
                        "status": SourceStatus.FILED.value,
                        "authority_weight": authority_weight.value,
                    },
                },
            )
        )
    return candidates


class ERCOTIssueIndexDiscoveryProvider(BaseAuthorityDiscoveryProvider):
    title = "ERCOT Revision Request Discovery"
    description = "Discovers ERCOT NPRR and PGRR issue pages."
    license = "copyright-review-required"
    link_only_discovery = True

    def _fetch_index_impl(self, index_url: str, **all_kwargs) -> tuple[str, str]:
        del all_kwargs
        return safe_fetch_text(index_url)

    def _parse_index_impl(
        self, html: str, *, index_url: str, **all_kwargs
    ) -> list[DiscoveryCandidate]:
        del all_kwargs
        return parse_ercot_issue_index(html, index_url=index_url)
