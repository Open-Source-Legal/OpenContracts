"""Fetch individually discovered Oncor tariff documents."""

from __future__ import annotations

import re
from dataclasses import replace
from datetime import datetime
from pathlib import PurePosixPath
from typing import ClassVar
from urllib.parse import urlsplit

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
    fetch_and_extract_authority_record,
    parse_optional_bool,
)
from opencontractserver.pipeline.base.authority_html import stable_source_slug
from opencontractserver.pipeline.base.base_authority_source_provider import (
    AuthorityRequest,
    BaseAuthoritySourceProvider,
)

_ISO_DATE_RE = re.compile(r"\b(?P<date>20\d{2}[-_/]\d{2}[-_/]\d{2})\b")
_US_DATE_RE = re.compile(
    r"\b(?P<month>\d{1,2})[/-](?P<day>\d{1,2})[/-](?P<year>20\d{2})\b"
)
_MONTH_NUMBERS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}
_MONTH_NAME_PATTERN = "|".join(_MONTH_NUMBERS)
_MONTH_NAME_DATE_RE = re.compile(
    rf"\b(?P<month>{_MONTH_NAME_PATTERN})\s+"
    r"(?P<day>\d{1,2}),\s*(?P<year>20\d{2})\b",
    re.I,
)
_EFFECTIVE_DATE_EVIDENCE_RE = re.compile(
    rf"\bEffective\s+Date\s*:\s*(?:{_MONTH_NAME_PATTERN})\s+" r"\d{1,2},\s*20\d{2}\b",
    re.I,
)
_REVISION_EVIDENCE_RE = re.compile(
    r"\bRevision\s*:\s*[A-Z0-9]+(?:-[A-Z0-9]+)*\b",
    re.I,
)
_RIDER_RE = re.compile(r"\bRider\s+(?P<name>[A-Z][A-Z0-9-]{1,20})\b", re.I)


def _publisher_document_date(value: str) -> str | None:
    iso_match = _ISO_DATE_RE.search(value)
    if iso_match is not None:
        return iso_match.group("date").replace("_", "-").replace("/", "-")
    match = _US_DATE_RE.search(value)
    if match is not None:
        month = int(match.group("month"))
    else:
        match = _MONTH_NAME_DATE_RE.search(value)
        if match is None:
            return None
        month = _MONTH_NUMBERS[match.group("month").casefold()]
    try:
        return (
            datetime(
                int(match.group("year")),
                month,
                int(match.group("day")),
            )
            .date()
            .isoformat()
        )
    except ValueError:
        return None


def _historical_tariff_content_evidence(
    text: str,
    *,
    locator: str,
) -> tuple[AuthorityPublisherEvidence, ...]:
    """Return exact edition markers extracted from the publisher's tariff."""

    evidence: list[AuthorityPublisherEvidence] = []
    for pattern in (_EFFECTIVE_DATE_EVIDENCE_RE, _REVISION_EVIDENCE_RE):
        match = pattern.search(text)
        if match is not None:
            evidence.append(
                AuthorityPublisherEvidence(
                    source=PublisherEvidenceSource.PARSED_CONTENT,
                    value=match.group(0),
                    locator=locator,
                )
            )
    return tuple(evidence)


def _publisher_tariff_identity(label: str) -> tuple[str, str] | None:
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


def _tariff_relationships(
    canonical_key: str, parent_key: str | None
) -> tuple[SourceRelationship, ...]:
    relationships: list[SourceRelationship] = []
    if canonical_key == "oncor-tariff:retail-delivery":
        relationships.append(
            SourceRelationship(
                target_key="tx-admin-puct:25.214",
                relationship_type=RelationshipType.IMPLEMENTS,
                metadata={"review_status": "pending_legal_review"},
            )
        )
    if parent_key:
        relationships.extend(
            [
                SourceRelationship(
                    target_key=parent_key,
                    relationship_type=RelationshipType.EFFECTIVE_VERSION_OF,
                    metadata={"review_status": "pending_legal_review"},
                ),
                SourceRelationship(
                    target_key=parent_key,
                    relationship_type=RelationshipType.SUPERSEDED_BY,
                    metadata={"review_status": "pending_legal_review"},
                ),
            ]
        )
    return tuple(relationships)


class OncorTariffAuthoritySourceProvider(BaseAuthoritySourceProvider):
    title = "Oncor Current Delivery Tariff"
    description = "Fetches discovered Oncor tariffs, schedules, riders, and rate codes."
    supported_prefixes: ClassVar[tuple[str, ...]] = ("oncor-tariff", "oncor-rider")
    license: ClassVar[str] = "copyright-review-required"

    def _locate_impl(self, canonical_key: str, **all_kwargs) -> AuthorityRequest:
        candidate = all_kwargs.get("discovery_candidate")
        if candidate is None:
            raise ValueError(
                f"{canonical_key!r} requires its discovered Oncor document URL"
            )
        return AuthorityRequest(
            canonical_key=canonical_key,
            url=candidate.url,
            extra={"title": candidate.title, **dict(candidate.extra)},
        )

    def _fetch_impl(
        self, request: AuthorityRequest, **all_kwargs
    ) -> list[AuthoritySourceRecord]:
        del all_kwargs
        current_value = parse_optional_bool(
            request.extra.get("current_version"),
            field_name="current_version",
        )
        parent_key = request.extra.get("parent_key")
        title = request.extra.get("title") or request.canonical_key
        source_identifier = request.extra.get("source_identifier")
        if not isinstance(source_identifier, str) or not source_identifier.strip():
            raise ValueError(
                "Oncor tariff candidate lacked publisher source_identifier"
            )
        record = fetch_and_extract_authority_record(
            url=request.url,
            canonical_key=request.canonical_key,
            title=str(title),
            source_identifier=source_identifier,
            publisher="Oncor Electric Delivery Company LLC",
            jurisdiction="us-tx-oncor",
            authority_type="regulation",
            instrument_type=InstrumentType.TARIFF,
            status=(
                SourceStatus.CURRENT
                if current_value is True
                else (
                    SourceStatus.SUPERSEDED
                    if current_value is False
                    else SourceStatus.PUBLISHED
                )
            ),
            authority_weight=(
                AuthorityWeight.CONTROLLING
                if current_value is True
                else AuthorityWeight.EVIDENTIARY
            ),
            corpus_slug=(
                "oncor-current-delivery-tariff"
                if current_value is True
                else "oncor-tariff-history"
            ),
            parent_key=str(parent_key) if parent_key else None,
            issued_date=request.extra.get("issued_date"),
            effective_from=request.extra.get("effective_from"),
            effective_until=request.extra.get("effective_until"),
            version_label=request.extra.get("version_label"),
            authority_family=(
                "oncor-tariff" if current_value is not False else "oncor-tariff-history"
            ),
            current_version=current_value,
            rights_status=RightsStatus.REVIEW_REQUIRED,
            relationships=_tariff_relationships(
                request.canonical_key,
                str(parent_key) if parent_key else None,
            ),
            metadata={
                "current_version_review_state": (
                    "KNOWN" if current_value is not None else "UNKNOWN_PENDING_REVIEW"
                ),
                **{
                    key: value
                    for key, value in request.extra.items()
                    if key
                    not in {
                        "title",
                        "source_identifier",
                        "parent_key",
                        "issued_date",
                        "effective_from",
                        "effective_until",
                        "version_label",
                        "current_version",
                        "current_version_review_state",
                    }
                },
            },
            publisher_evidence=(
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
            ),
            params=request.params,
        )
        if current_value is False:
            record = replace(
                record,
                publisher_evidence=(
                    *record.publisher_evidence,
                    *_historical_tariff_content_evidence(
                        record.extracted_text or "",
                        locator=request.url,
                    ),
                ),
            )
        return [record]

    def verify_publisher_evidence(
        self, canonical_key: str, record: AuthoritySourceRecord
    ) -> bool:
        if canonical_key.partition(":")[0] not in self.supported_prefixes:
            return False
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
        parsed_content = [
            evidence.value
            for evidence in record.publisher_evidence
            if evidence.source == PublisherEvidenceSource.PARSED_CONTENT
        ]
        parsed_version_date = next(
            (
                _publisher_document_date(value)
                for value in parsed_content
                if _EFFECTIVE_DATE_EVIDENCE_RE.fullmatch(value)
            ),
            None,
        )
        has_parsed_revision = any(
            _REVISION_EVIDENCE_RE.fullmatch(value) is not None
            for value in parsed_content
        )
        for title in titles:
            for url in urls:
                filename = PurePosixPath(urlsplit(url).path).name
                label = " ".join(part for part in (title, filename) if part)
                identity = _publisher_tariff_identity(label)
                if identity is None:
                    continue
                prefix, base_identifier = identity
                lowered = label.casefold()
                version_date = _publisher_document_date(label) or (
                    parsed_version_date if has_parsed_revision else None
                )
                historical = any(
                    marker in lowered
                    for marker in (
                        "historical",
                        "archive",
                        "prior",
                        "previous",
                        "superseded",
                    )
                )
                if historical or version_date is not None:
                    current: bool | None = False
                elif "current" in lowered:
                    current = True
                else:
                    current = None
                identifier = base_identifier
                if current is False:
                    version_token = version_date or stable_source_slug(
                        PurePosixPath(filename).stem
                    )
                    identifier = f"{base_identifier}-{version_token}"
                if canonical_key == f"{prefix}:{identifier}":
                    return True
        return False
