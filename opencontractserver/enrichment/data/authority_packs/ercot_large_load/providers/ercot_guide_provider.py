"""ERCOT current/historical guide and protocol document provider."""

from __future__ import annotations

import re
from typing import ClassVar
from urllib.parse import urlsplit

from opencontractserver.enrichment.authority_sources import (
    AuthorityPublisherEvidence,
    AuthoritySourceRecord,
    AuthorityWeight,
    InstrumentType,
    PublisherEvidenceSource,
    RightsStatus,
    SourceStatus,
    fetch_and_extract_authority_record,
    parse_optional_bool,
)
from opencontractserver.pipeline.base.authority_html import stable_source_slug
from opencontractserver.pipeline.base.base_authority_source_provider import (
    AuthorityRequest,
    BaseAuthoritySourceProvider,
)

_SECTION_RE = re.compile(r"\bSection\s+(?P<section>\d+(?:\.\d+)*)\b", re.I)


def _guide_family_from_publisher(value: str) -> str | None:
    lowered = value.casefold()
    if "planning" in lowered:
        return "ercot-planning"
    if "protocol" in lowered or "nprotocol" in lowered:
        return "ercot-protocol"
    if "operating" in lowered or "noperating" in lowered:
        return "ercot-operating"
    return None


class ERCOTGuideAuthoritySourceProvider(BaseAuthoritySourceProvider):
    title = "ERCOT Current Large-Load Rules"
    description = "Fetches discovered ERCOT guides and current rule libraries."
    supported_prefixes: ClassVar[tuple[str, ...]] = (
        "ercot-planning",
        "ercot-protocol",
        "ercot-operating",
    )
    license: ClassVar[str] = "copyright-review-required"

    def _locate_impl(self, canonical_key: str, **all_kwargs) -> AuthorityRequest:
        prefix, _, identifier = canonical_key.partition(":")
        if not identifier or prefix not in self.supported_prefixes:
            raise ValueError(f"unsupported ERCOT guide key {canonical_key!r}")
        candidate = all_kwargs.get("discovery_candidate")
        if candidate is None:
            raise ValueError(
                f"{canonical_key!r} requires its discovered guide attachment URL; "
                "the current-guide index page is not authority content"
            )
        url = candidate.url
        extra = {"title": candidate.title, **dict(candidate.extra)}
        return AuthorityRequest(
            canonical_key=canonical_key,
            url=url,
            extra={"identifier": identifier, "family": prefix, **extra},
        )

    def _fetch_impl(
        self, request: AuthorityRequest, **all_kwargs
    ) -> list[AuthoritySourceRecord]:
        del all_kwargs
        family = str(request.extra["family"])
        instrument = (
            InstrumentType.PLANNING_GUIDE
            if family == "ercot-planning"
            else (
                InstrumentType.PROTOCOL
                if family == "ercot-protocol"
                else InstrumentType.OPERATING_GUIDE
            )
        )
        if "current_version" in request.extra:
            current = parse_optional_bool(
                request.extra.get("current_version"),
                field_name="current_version",
            )
        else:
            # A publisher URL explicitly rooted in /current is positive current
            # evidence; absence of that marker is unknown, not superseded.
            current = (
                True if "/current" in urlsplit(request.url).path.casefold() else None
            )
        corpus_slug = (
            "ercot-current-large-load-rules"
            if current
            and family in {"ercot-planning", "ercot-protocol", "ercot-operating"}
            else "ercot-large-load-revision-history"
        )
        source_identifier = request.extra.get("source_identifier")
        if not isinstance(source_identifier, str) or not source_identifier.strip():
            raise ValueError("ERCOT guide candidate lacked publisher source_identifier")
        publisher_family = request.extra.get("guide_family")
        if publisher_family != family:
            raise ValueError(
                "ERCOT guide candidate family did not match requested canonical key"
            )
        title = request.extra.get("title") or request.canonical_key
        record = fetch_and_extract_authority_record(
            url=request.url,
            canonical_key=request.canonical_key,
            title=title,
            source_identifier=source_identifier,
            publisher="Electric Reliability Council of Texas",
            jurisdiction="us-tx-ercot",
            authority_type=(
                "admin-rule"
                if family in {"ercot-planning", "ercot-protocol", "ercot-operating"}
                else "guidance"
            ),
            instrument_type=instrument,
            status=(
                SourceStatus.CURRENT
                if current is True
                else (
                    SourceStatus.SUPERSEDED
                    if current is False
                    else SourceStatus.PUBLISHED
                )
            ),
            authority_weight=(
                AuthorityWeight.CONTROLLING
                if current is True
                and family in {"ercot-planning", "ercot-protocol", "ercot-operating"}
                else AuthorityWeight.EVIDENTIARY
            ),
            corpus_slug=corpus_slug,
            issued_date=request.extra.get("issued_date"),
            effective_from=request.extra.get("effective_from"),
            effective_until=request.extra.get("effective_until"),
            version_label=request.extra.get("version_label"),
            parent_key=request.extra.get("parent_key"),
            authority_family="ercot-market-rule",
            current_version=current,
            rights_status=RightsStatus.REVIEW_REQUIRED,
            metadata={
                "current_version_review_state": (
                    "KNOWN" if current is not None else "UNKNOWN_PENDING_REVIEW"
                ),
                **{
                    key: value
                    for key, value in request.extra.items()
                    if key
                    not in {
                        "title",
                        "source_identifier",
                        "issued_date",
                        "effective_from",
                        "effective_until",
                        "version_label",
                        "parent_key",
                        "current_version",
                    }
                },
            },
            publisher_evidence=(
                AuthorityPublisherEvidence(
                    source=PublisherEvidenceSource.SOURCE_IDENTIFIER,
                    value=source_identifier,
                    locator=request.url,
                ),
                AuthorityPublisherEvidence(
                    source=PublisherEvidenceSource.TITLE,
                    value=str(title),
                    locator=request.url,
                ),
                AuthorityPublisherEvidence(
                    source=PublisherEvidenceSource.URL,
                    value=request.url,
                    locator=request.url,
                ),
                AuthorityPublisherEvidence(
                    source=PublisherEvidenceSource.LISTING_METADATA,
                    value=str(publisher_family),
                    locator=request.url,
                ),
            ),
            params=request.params,
        )
        return [record]

    def verify_publisher_evidence(
        self, canonical_key: str, record: AuthoritySourceRecord
    ) -> bool:
        if canonical_key.partition(":")[0] not in self.supported_prefixes:
            return False
        identifiers = [
            evidence.value
            for evidence in record.publisher_evidence
            if evidence.source == PublisherEvidenceSource.SOURCE_IDENTIFIER
        ]
        titles = [
            evidence.value
            for evidence in record.publisher_evidence
            if evidence.source == PublisherEvidenceSource.TITLE
        ]
        urls = [
            evidence.value
            for evidence in record.publisher_evidence
            if evidence.source == PublisherEvidenceSource.URL
        ]
        listing_families = [
            evidence.value
            for evidence in record.publisher_evidence
            if evidence.source == PublisherEvidenceSource.LISTING_METADATA
            and evidence.value in self.supported_prefixes
        ]
        family = (
            listing_families[0]
            if listing_families
            else _guide_family_from_publisher(" ".join([*titles, *urls]))
        )
        if family is None:
            return False
        section_match = next(
            (
                match
                for title in titles
                if (match := _SECTION_RE.search(title)) is not None
            ),
            None,
        )
        if section_match is not None:
            derived = f"{family}:{section_match.group('section')}"
            return derived == canonical_key
        current = any(
            "/current" in urlsplit(url).path.casefold() for url in urls
        ) or any("current" in title.casefold() for title in titles)
        if current and family == "ercot-planning":
            return canonical_key == "ercot-planning:9"
        return any(
            canonical_key == f"{family}:{stable_source_slug(identifier)}"
            for identifier in identifiers
        )
