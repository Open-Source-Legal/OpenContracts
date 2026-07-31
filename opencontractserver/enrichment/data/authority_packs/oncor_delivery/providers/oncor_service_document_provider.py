"""Fetch individually discovered Oncor service and construction documents."""

from __future__ import annotations

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


class OncorServiceDocumentAuthoritySourceProvider(BaseAuthoritySourceProvider):
    title = "Oncor Service and Construction Requirements"
    description = "Fetches Oncor service and construction source documents."
    supported_prefixes: ClassVar[tuple[str, ...]] = ("oncor-service-guide",)
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
        title = request.extra.get("title") or request.canonical_key
        source_identifier = request.extra.get("source_identifier")
        if not isinstance(source_identifier, str) or not source_identifier.strip():
            raise ValueError(
                "Oncor service candidate lacked publisher source_identifier"
            )
        current_value = parse_optional_bool(
            request.extra.get("current_version"),
            field_name="current_version",
        )
        relationships = (
            SourceRelationship(
                target_key="oncor-tariff:retail-delivery",
                relationship_type=RelationshipType.IMPLEMENTS,
                metadata={"review_status": "pending_legal_review"},
            ),
        )
        max_bytes = all_kwargs.get("max_bytes")
        record = fetch_and_extract_authority_record(
            url=request.url,
            canonical_key=request.canonical_key,
            title=str(title),
            source_identifier=source_identifier,
            publisher="Oncor Electric Delivery Company LLC",
            jurisdiction="us-tx-oncor",
            authority_type="guidance",
            instrument_type=InstrumentType.TECHNICAL_GUIDE,
            issued_date=request.extra.get("issued_date"),
            effective_from=request.extra.get("effective_from"),
            effective_until=request.extra.get("effective_until"),
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
                AuthorityWeight.IMPLEMENTING
                if current_value is True
                else AuthorityWeight.EVIDENTIARY
            ),
            parent_key=request.extra.get("parent_key"),
            version_label=request.extra.get("version_label"),
            corpus_slug="oncor-service-requirements",
            metadata={
                "rights_basis": "Oncor-authored work; explicit review required",
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
                        "version_label",
                        "issued_date",
                        "effective_from",
                        "effective_until",
                        "current_version",
                    }
                },
            },
            relationships=relationships,
            authority_family="oncor-service-requirement",
            current_version=current_value,
            rights_status=RightsStatus.REVIEW_REQUIRED,
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
            max_bytes=(int(max_bytes) if max_bytes is not None else None),
            extra_ca_certificates=all_kwargs.get("extra_ca_certificates"),
        )
        return [record]

    def verify_publisher_evidence(
        self, canonical_key: str, record: AuthoritySourceRecord
    ) -> bool:
        if not canonical_key.startswith("oncor-service-guide:"):
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
        for title in titles:
            for url in urls:
                filename = PurePosixPath(urlsplit(url).path).name
                label = " ".join(part for part in (title, filename) if part)
                if "electric service guideline" in label.casefold():
                    identifier = "electric-service-guidelines"
                else:
                    identifier = stable_source_slug(title or filename)
                if canonical_key == f"oncor-service-guide:{identifier}":
                    return True
        return False
