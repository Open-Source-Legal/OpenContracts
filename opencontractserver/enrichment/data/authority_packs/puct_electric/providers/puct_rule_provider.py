"""Deterministic PUCT substantive-rule provider."""

from __future__ import annotations

import re
from dataclasses import replace
from typing import ClassVar

from opencontractserver.enrichment.authority_sources import (
    AuthorityPublisherEvidence,
    AuthoritySourceRecord,
    AuthorityWeight,
    InstrumentType,
    PublisherEvidenceSource,
    RightsStatus,
    SourceStatus,
    fetch_and_extract_authority_record,
)
from opencontractserver.pipeline.base.base_authority_source_provider import (
    AuthorityRequest,
    BaseAuthoritySourceProvider,
)

_KEY_RE = re.compile(r"^tx-admin-puct:(?P<section>25\.\d+[A-Za-z]?)$")
_PUBLISHER_RULE_RE = re.compile(
    r"(?:§|Section|Rule)\s*(?P<section>25\.\d+[A-Za-z]?)\b",
    re.I,
)


class PUCTRuleAuthoritySourceProvider(BaseAuthoritySourceProvider):
    title = "PUCT Electric Rules and Controlling Orders"
    description = "Fetches official PUCT Chapter 25 substantive-rule pages."
    supported_prefixes: ClassVar[tuple[str, ...]] = ("tx-admin-puct",)
    license: ClassVar[str] = "public-domain"

    def can_handle(self, canonical_key: str) -> bool:
        return _KEY_RE.fullmatch(canonical_key) is not None

    def _locate_impl(self, canonical_key: str, **all_kwargs) -> AuthorityRequest:
        match = _KEY_RE.fullmatch(canonical_key)
        if match is None:
            raise ValueError(f"unsupported PUCT rule key {canonical_key!r}")
        section = match.group("section")
        candidate = all_kwargs.get("discovery_candidate")
        url = (
            candidate.url
            if candidate is not None
            else (
                "https://www.puc.texas.gov/agency/rulesnlaws/subrules/electric/"
                f"{section}/"
            )
        )
        return AuthorityRequest(
            canonical_key=canonical_key,
            url=url,
            citation=f"16 Tex. Admin. Code § {section}",
            extra={
                "section": section,
                "title": candidate.title if candidate is not None else None,
                **(dict(candidate.extra) if candidate is not None else {}),
            },
        )

    def _fetch_impl(
        self, request: AuthorityRequest, **all_kwargs
    ) -> list[AuthoritySourceRecord]:
        del all_kwargs
        section = str(request.extra["section"])
        record = fetch_and_extract_authority_record(
            url=request.url,
            canonical_key=request.canonical_key,
            title=request.extra.get("title")
            or f"16 Texas Administrative Code § {section}",
            source_identifier=f"16-TAC-{section}",
            publisher="Public Utility Commission of Texas",
            jurisdiction="us-tx",
            authority_type="regulation",
            instrument_type=InstrumentType.REGULATION,
            status=SourceStatus.CURRENT,
            authority_weight=AuthorityWeight.CONTROLLING,
            corpus_slug="puct-electric-rules-and-orders",
            issued_date=request.extra.get("issued_date"),
            effective_from=request.extra.get("effective_from"),
            version_label=request.extra.get("version_label"),
            authority_family="puct-electric-rule",
            current_version=True,
            rights_status=RightsStatus.PUBLIC_DOMAIN,
            metadata={
                "rule_section": section,
                "effective_date_review_state": (
                    "KNOWN"
                    if request.extra.get("effective_from")
                    else "UNKNOWN_PENDING_REVIEW"
                ),
                "rights_basis": (
                    "official codified agency rule; government legal edict"
                ),
            },
            params=request.params,
        )
        publisher_match = next(
            (
                match
                for match in _PUBLISHER_RULE_RE.finditer(record.text)
                if match.group("section").casefold() == section.casefold()
            ),
            None,
        )
        if publisher_match is None:
            raise ValueError(
                f"PUCT rule response did not identify publisher section {section}"
            )
        return [
            replace(
                record,
                publisher_evidence=(
                    AuthorityPublisherEvidence(
                        source=PublisherEvidenceSource.PARSED_CONTENT,
                        value=publisher_match.group(0),
                        locator=request.url,
                    ),
                ),
            )
        ]

    def verify_publisher_evidence(
        self, canonical_key: str, record: AuthoritySourceRecord
    ) -> bool:
        key_match = _KEY_RE.fullmatch(canonical_key)
        if key_match is None:
            return False
        expected = key_match.group("section").casefold()
        return any(
            evidence.source == PublisherEvidenceSource.PARSED_CONTENT
            and (match := _PUBLISHER_RULE_RE.fullmatch(evidence.value)) is not None
            and match.group("section").casefold() == expected
            for evidence in record.publisher_evidence
        )
