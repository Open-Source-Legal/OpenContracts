"""Deterministic ERCOT market-notice provider."""

from __future__ import annotations

import re
from datetime import datetime
from typing import ClassVar

from opencontractserver.enrichment.authority_sources import (
    AuthorityPublisherEvidence,
    AuthoritySourceRecord,
    AuthorityWeight,
    InstrumentType,
    PublisherEvidenceSource,
    RelationshipType,
    RightsStatus,
    SourceRelationship,
    SourceStatus,
)
from opencontractserver.pipeline.base.authority_html import visible_html_text
from opencontractserver.pipeline.base.base_authority_source_provider import (
    AuthorityRequest,
    BaseAuthoritySourceProvider,
)
from opencontractserver.utils.safe_http import safe_fetch_bytes

_KEY_RE = re.compile(r"^ercot-notice:(?P<notice>[A-Z]-[A-Z]\d{6}-\d+)$", re.I)
_NOTICE_RE = re.compile(r"\b(?P<id>[A-Z]-[A-Z]\d{6}-\d+)\b", re.I)
_PLANNING_RE = re.compile(
    r"\bPlanning Guide\s+(?:Section|Sec\.?|§)\s*" r"(?P<section>\d+(?:\.\d+)*)",
    re.I,
)
_PROTOCOL_RE = re.compile(
    r"\b(?:Nodal\s+)?Protocol(?:s)?\s+(?:Section|Sec\.?|§)\s*"
    r"(?P<section>\d+(?:\.\d+)*)",
    re.I,
)


def parse_ercot_market_notice(
    html: str, *, notice_id: str
) -> tuple[str, str | None, tuple[SourceRelationship, ...], str]:
    text = visible_html_text(html)
    if notice_id.casefold() not in text.casefold():
        raise ValueError(f"ERCOT market notice page did not contain {notice_id}")
    title_match = re.search(rf"(?im)^.*{re.escape(notice_id)}.*$", text)
    title = (
        title_match.group(0).strip()
        if title_match
        else f"ERCOT Market Notice {notice_id}"
    )
    issued_date = None
    encoded_date = re.search(r"[A-Z]-[A-Z](\d{6})-\d+", notice_id, re.I)
    if encoded_date:
        try:
            issued_date = (
                datetime.strptime(encoded_date.group(1), "%m%d%y").date().isoformat()
            )
        except ValueError:
            issued_date = None
    relationships: list[SourceRelationship] = []
    for match in _PLANNING_RE.finditer(text):
        relationships.append(
            SourceRelationship(
                target_key=f"ercot-planning:{match.group('section')}",
                relationship_type=RelationshipType.IMPLEMENTS,
            )
        )
    for match in _PROTOCOL_RE.finditer(text):
        relationships.append(
            SourceRelationship(
                target_key=f"ercot-protocol:{match.group('section')}",
                relationship_type=RelationshipType.IMPLEMENTS,
            )
        )
    for match in _NOTICE_RE.finditer(text):
        other = match.group("id").upper()
        if other != notice_id.upper():
            relationships.append(
                SourceRelationship(
                    target_key=f"ercot-notice:{other}",
                    relationship_type=RelationshipType.CITES,
                )
            )
    deduped = tuple(
        {
            (relationship.target_key, relationship.relationship_type): relationship
            for relationship in relationships
        }.values()
    )
    return title, issued_date, deduped, text


class ERCOTMarketNoticeAuthoritySourceProvider(BaseAuthoritySourceProvider):
    title = "ERCOT Large-Load Implementation Materials"
    description = "Fetches key-addressable ERCOT market notices."
    supported_prefixes: ClassVar[tuple[str, ...]] = ("ercot-notice",)
    license: ClassVar[str] = "copyright-review-required"

    def can_handle(self, canonical_key: str) -> bool:
        return _KEY_RE.fullmatch(canonical_key) is not None

    def _locate_impl(self, canonical_key: str, **all_kwargs) -> AuthorityRequest:
        match = _KEY_RE.fullmatch(canonical_key)
        if match is None:
            raise ValueError(f"unsupported ERCOT market-notice key {canonical_key!r}")
        notice = match.group("notice").upper()
        candidate = all_kwargs.get("discovery_candidate")
        return AuthorityRequest(
            canonical_key=canonical_key,
            url=(
                candidate.url
                if candidate is not None
                else f"https://www.ercot.com/services/comm/mkt_notices/{notice}"
            ),
            extra={"notice": notice},
        )

    def _fetch_impl(
        self, request: AuthorityRequest, **all_kwargs
    ) -> list[AuthoritySourceRecord]:
        del all_kwargs
        content, final_host = safe_fetch_bytes(request.url, params=request.params)
        try:
            html = content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("ERCOT market notice was not UTF-8 HTML") from exc
        notice = str(request.extra["notice"])
        title, issued_date, relationships, text = parse_ercot_market_notice(
            html, notice_id=notice
        )
        return [
            AuthoritySourceRecord(
                canonical_key=request.canonical_key,
                title=title,
                source_url=request.url,
                source_identifier=notice,
                publisher="Electric Reliability Council of Texas",
                jurisdiction="us-tx-ercot",
                authority_type="guidance",
                instrument_type=InstrumentType.MARKET_NOTICE,
                issued_date=issued_date,
                effective_from=None,
                effective_until=None,
                status=SourceStatus.PUBLISHED,
                authority_weight=AuthorityWeight.IMPLEMENTING,
                parent_key=None,
                version_label=None,
                content=content,
                mime_type="text/html",
                corpus_slug="ercot-large-load-implementation",
                metadata={"final_source_host": final_host},
                relationships=relationships,
                authority_family="ercot-implementation",
                published_date=issued_date,
                current_version=True,
                rights_status=RightsStatus.REVIEW_REQUIRED,
                extracted_text=text,
                publisher_evidence=(
                    AuthorityPublisherEvidence(
                        source=PublisherEvidenceSource.PARSED_CONTENT,
                        value=notice,
                        locator=request.url,
                    ),
                ),
            )
        ]

    def verify_publisher_evidence(
        self, canonical_key: str, record: AuthoritySourceRecord
    ) -> bool:
        match = _KEY_RE.fullmatch(canonical_key)
        if match is None:
            return False
        expected = match.group("notice").upper()
        return any(
            evidence.source == PublisherEvidenceSource.PARSED_CONTENT
            and evidence.value.upper() == expected
            for evidence in record.publisher_evidence
        )
