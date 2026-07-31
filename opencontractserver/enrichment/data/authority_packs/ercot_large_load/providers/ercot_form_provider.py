"""ERCOT large-load form and attestation provider."""

from __future__ import annotations

import re
from collections.abc import Iterable
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
    fetch_and_extract_authority_record,
    parse_optional_bool,
)
from opencontractserver.pipeline.base.authority_html import stable_source_slug
from opencontractserver.pipeline.base.base_authority_source_provider import (
    AuthorityRequest,
    BaseAuthoritySourceProvider,
)

_VERSION_RE = re.compile(r"\bv(?:ersion\s*)?(?P<version>\d+(?:\.\d+)*)\b", re.I)


def _governing_relationships(value: object) -> tuple[SourceRelationship, ...]:
    if isinstance(value, str) or not isinstance(value, Iterable):
        return ()
    return tuple(
        SourceRelationship(
            target_key=str(target),
            relationship_type=RelationshipType.IMPLEMENTS,
            metadata={"source": "ERCOT form listing"},
        )
        for target in value
    )


class ERCOTFormAuthoritySourceProvider(BaseAuthoritySourceProvider):
    title = "ERCOT Large-Load Implementation Materials"
    description = "Fetches individually discovered ERCOT forms and attestations."
    supported_prefixes: ClassVar[tuple[str, ...]] = ("ercot-form",)
    license: ClassVar[str] = "copyright-review-required"

    def _locate_impl(self, canonical_key: str, **all_kwargs) -> AuthorityRequest:
        candidate = all_kwargs.get("discovery_candidate")
        if candidate is None:
            raise ValueError(
                f"{canonical_key!r} requires its discovered form attachment URL"
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
        title = request.extra.get("title") or request.canonical_key
        lowered_title = str(title).casefold()
        if "attestation" in lowered_title:
            instrument = InstrumentType.ATTESTATION
        elif "faq" in lowered_title or "frequently asked" in lowered_title:
            instrument = InstrumentType.FAQ
        elif any(
            term in lowered_title
            for term in ("guide", "guidance", "instruction", "timeline")
        ):
            instrument = InstrumentType.TECHNICAL_GUIDE
        else:
            instrument = InstrumentType.FORM
        source_identifier = request.extra.get("source_identifier")
        if not isinstance(source_identifier, str) or not source_identifier.strip():
            raise ValueError("ERCOT form candidate lacked publisher source_identifier")
        current_value = parse_optional_bool(
            request.extra.get("current_version", True),
            field_name="current_version",
        )
        if current_value is None:
            raise ValueError("ERCOT form current_version cannot be null")
        record = fetch_and_extract_authority_record(
            url=request.url,
            canonical_key=request.canonical_key,
            title=str(title),
            source_identifier=source_identifier,
            publisher="Electric Reliability Council of Texas",
            jurisdiction="us-tx-ercot",
            authority_type="guidance",
            instrument_type=instrument,
            status=(SourceStatus.CURRENT if current_value else SourceStatus.SUPERSEDED),
            authority_weight=AuthorityWeight.IMPLEMENTING,
            corpus_slug="ercot-large-load-implementation",
            issued_date=request.extra.get("issued_date"),
            effective_from=request.extra.get("effective_from"),
            effective_until=request.extra.get("effective_until"),
            version_label=request.extra.get("version_label"),
            parent_key=request.extra.get("parent_key"),
            authority_family="ercot-implementation",
            current_version=current_value,
            rights_status=RightsStatus.REVIEW_REQUIRED,
            relationships=_governing_relationships(request.extra.get("governing_keys")),
            metadata={
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
                    "governing_keys",
                }
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
            ),
            params=request.params,
        )
        return [record]

    def verify_publisher_evidence(
        self, canonical_key: str, record: AuthoritySourceRecord
    ) -> bool:
        if not canonical_key.startswith("ercot-form:"):
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
        for identifier in identifiers:
            slug = stable_source_slug(identifier)
            version_match = next(
                (
                    match
                    for title in titles
                    if (match := _VERSION_RE.search(title)) is not None
                ),
                None,
            )
            if version_match is not None:
                version = f"v{version_match.group('version')}"
                if not slug.endswith(version):
                    slug = f"{slug}:{version}"
            if canonical_key == f"ercot-form:{slug}":
                return True
        return False
