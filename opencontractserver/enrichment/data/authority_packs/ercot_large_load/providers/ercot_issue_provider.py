"""Deterministic ERCOT NPRR/PGRR issue-page provider."""

from __future__ import annotations

import re
from dataclasses import dataclass
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
)
from opencontractserver.enrichment.data.authority_packs.ercot_large_load.issue_identity import (
    classify_ercot_issue_attachment,
)
from opencontractserver.pipeline.base.authority_html import (
    extract_labeled_value,
    visible_html_text,
)
from opencontractserver.pipeline.base.base_authority_source_provider import (
    AuthorityRequest,
    BaseAuthoritySourceProvider,
)
from opencontractserver.utils.safe_http import safe_fetch_bytes

_KEY_RE = re.compile(
    r"^ercot-(?P<family>pgrr|nprr):(?P<number>\d+)" r"(?::item:(?P<item>\d+))?$"
)
_DATE_RE = re.compile(r"\b(?P<date>\d{2}/\d{2}/\d{4})\b")
_RELATED_ISSUE_RE = re.compile(r"\b(?P<family>NPRR|PGRR)(?P<number>\d+)\b")
_SECTION_RE = re.compile(r"\b\d+(?:\.\d+)*(?:\([A-Za-z0-9]+\))*\b")
_ATTACHMENT_ID_RE = re.compile(
    r"(?P<number>\d+)(?P<family>NPRR|PGRR)-(?P<item>\d+)-.+"
    r"\.(?:docx?|pdf|xlsx?|xls)$",
    re.I,
)


@dataclass(frozen=True)
class ERCOTIssuePage:
    title: str
    source_status: SourceStatus
    status_text: str
    issued_date: str | None
    effective_from: str | None
    filed_date: str | None
    sponsor: str | None
    sections: tuple[str, ...]
    related_keys: tuple[str, ...]
    text: str


def parse_ercot_issue_page(html: str, *, family: str, number: str) -> ERCOTIssuePage:
    """Parse ERCOT's labeled issue summary without inferring legal effect."""

    text = visible_html_text(html)
    own_id = f"{family.upper()}{number}"
    own_match = re.search(
        rf"(?<![A-Za-z0-9]){re.escape(own_id)}(?![A-Za-z0-9])",
        text,
        re.I,
    )
    if own_match is None:
        raise ValueError(f"ERCOT issue page did not identify {own_id}")
    title_value = extract_labeled_value(text, "Title")
    status_text = extract_labeled_value(text, "Status") or ""
    effective_text = extract_labeled_value(text, "Effective Dates") or ""
    posted_text = extract_labeled_value(text, "Date Posted") or ""
    sponsor = extract_labeled_value(text, "Sponsor")
    sections_text = extract_labeled_value(text, "Sections") or ""

    normalized_status = status_text.casefold()
    if "approved" in normalized_status:
        source_status = SourceStatus.APPROVED
    elif "withdrawn" in normalized_status:
        source_status = SourceStatus.WITHDRAWN
    elif "rejected" in normalized_status:
        source_status = SourceStatus.REJECTED
    elif "pending" in normalized_status:
        source_status = SourceStatus.PENDING
    elif "posted" in normalized_status or "published" in normalized_status:
        source_status = SourceStatus.PUBLISHED
    else:
        raise ValueError(f"unknown ERCOT issue publisher status {status_text!r}")

    issued_match = _DATE_RE.search(status_text)
    effective_match = _DATE_RE.search(effective_text)
    filed_match = _DATE_RE.search(posted_text)
    sections = tuple(dict.fromkeys(_SECTION_RE.findall(sections_text)))
    related = tuple(
        dict.fromkeys(
            f"ercot-{match.group('family').lower()}:{match.group('number')}"
            for match in _RELATED_ISSUE_RE.finditer(f"{title_value or ''}\n{text}")
            if match.group(0).upper() != own_id
        )
    )
    family_title = (
        "Planning Guide Revision Request"
        if family.lower() == "pgrr"
        else "Nodal Protocol Revision Request"
    )
    title = f"{family_title} {number}"
    if title_value:
        title = f"{title} — {title_value}"
    return ERCOTIssuePage(
        title=title,
        source_status=source_status,
        status_text=status_text or "status not exposed",
        issued_date=issued_match.group("date") if issued_match else None,
        effective_from=effective_match.group("date") if effective_match else None,
        filed_date=filed_match.group("date") if filed_match else None,
        sponsor=sponsor,
        sections=sections,
        related_keys=related,
        text=text,
    )


class ERCOTIssueAuthoritySourceProvider(BaseAuthoritySourceProvider):
    title = "ERCOT Large-Load Revision History"
    description = "Fetches deterministic ERCOT NPRR and PGRR issue histories."
    supported_prefixes: ClassVar[tuple[str, ...]] = ("ercot-pgrr", "ercot-nprr")
    license: ClassVar[str] = "copyright-review-required"

    def can_handle(self, canonical_key: str) -> bool:
        return _KEY_RE.fullmatch(canonical_key) is not None

    def _locate_impl(self, canonical_key: str, **all_kwargs) -> AuthorityRequest:
        match = _KEY_RE.fullmatch(canonical_key)
        if match is None:
            raise ValueError(f"unsupported ERCOT issue key {canonical_key!r}")
        candidate = all_kwargs.get("discovery_candidate")
        family = match.group("family")
        number = match.group("number")
        item = match.group("item")
        if item is not None and candidate is None:
            raise ValueError(
                f"{canonical_key!r} requires its discovered issue attachment URL"
            )
        return AuthorityRequest(
            canonical_key=canonical_key,
            url=(
                candidate.url
                if candidate is not None
                else f"https://www.ercot.com/mktrules/issues/{family.upper()}{number}"
            ),
            extra={
                **(dict(candidate.extra) if candidate is not None else {}),
                "title": candidate.title if candidate is not None else None,
                "family": family,
                "number": number,
                "item_sequence": item,
            },
        )

    def _fetch_impl(
        self, request: AuthorityRequest, **all_kwargs
    ) -> list[AuthoritySourceRecord]:
        del all_kwargs
        item = request.extra.get("item_sequence")
        if item is not None:
            title = request.extra.get("title") or request.canonical_key
            descriptor = str(request.extra.get("descriptor") or title)
            instrument, weight = classify_ercot_issue_attachment(
                descriptor,
                item_sequence=item,
            )
            family = str(request.extra["family"])
            number = str(request.extra["number"])
            root_key = f"ercot-{family}:{number}"
            filename = request.extra.get("filename")
            if not isinstance(filename, str) or not filename.strip():
                raise ValueError(
                    "ERCOT issue attachment lacked publisher filename evidence"
                )
            return [
                fetch_and_extract_authority_record(
                    url=request.url,
                    canonical_key=request.canonical_key,
                    title=str(title),
                    source_identifier=(
                        request.extra.get("source_identifier")
                        or f"{family}-{number}-{item}"
                    ),
                    publisher="Electric Reliability Council of Texas",
                    jurisdiction="us-tx-ercot",
                    authority_type="admin-rule",
                    instrument_type=instrument,
                    status=SourceStatus.FILED,
                    authority_weight=weight,
                    corpus_slug="ercot-large-load-revision-history",
                    parent_key=root_key,
                    version_label=request.extra.get("version_label"),
                    filed_date=request.extra.get("filed_date"),
                    issued_date=request.extra.get("filed_date"),
                    authority_family="ercot-revision-request",
                    current_version=False,
                    rights_status=RightsStatus.REVIEW_REQUIRED,
                    relationships=(
                        SourceRelationship(
                            target_key=root_key,
                            relationship_type=RelationshipType.FILED_IN,
                            metadata={"source": "ERCOT issue attachment listing"},
                        ),
                    ),
                    metadata={
                        "issue_family": family,
                        "issue_number": number,
                        "item_sequence": str(item),
                        "descriptor": descriptor,
                        "filename": filename,
                        "source_extension": request.extra.get("source_extension"),
                    },
                    publisher_evidence=(
                        AuthorityPublisherEvidence(
                            source=PublisherEvidenceSource.SOURCE_IDENTIFIER,
                            value=filename,
                            locator=request.url,
                        ),
                    ),
                    params=request.params,
                )
            ]

        content, final_host = safe_fetch_bytes(request.url, params=request.params)
        try:
            html = content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("ERCOT issue page was not UTF-8 HTML") from exc
        family = str(request.extra["family"])
        number = str(request.extra["number"])
        parsed = parse_ercot_issue_page(html, family=family, number=number)
        affected_prefix = "ercot-planning" if family == "pgrr" else "ercot-protocol"
        relationships = tuple(
            [
                SourceRelationship(
                    target_key=f"{affected_prefix}:{section}",
                    relationship_type=RelationshipType.REVISES,
                    metadata={"source": "ERCOT issue page Sections field"},
                )
                for section in parsed.sections
            ]
            + [
                SourceRelationship(
                    target_key=target,
                    relationship_type=RelationshipType.CITES,
                    metadata={"source": "ERCOT issue page"},
                )
                for target in parsed.related_keys
            ]
        )
        return [
            AuthoritySourceRecord(
                canonical_key=request.canonical_key,
                title=parsed.title,
                source_url=request.url,
                source_identifier=f"{family.upper()}{number}",
                publisher="Electric Reliability Council of Texas",
                jurisdiction="us-tx-ercot",
                authority_type="admin-rule",
                instrument_type=InstrumentType.REVISION_REQUEST,
                issued_date=parsed.issued_date,
                effective_from=parsed.effective_from,
                effective_until=None,
                status=parsed.source_status,
                # Revision requests are history/proceeding evidence.  Until
                # their legal-effect matrix is reviewed, even an approved issue
                # must not outrank the current effective guide/protocol text.
                authority_weight=AuthorityWeight.EVIDENTIARY,
                parent_key=None,
                version_label=parsed.source_status.value.casefold(),
                content=content,
                mime_type="text/html",
                corpus_slug="ercot-large-load-revision-history",
                metadata={
                    "publisher_status": parsed.status_text,
                    "sponsor": parsed.sponsor,
                    "affected_sections": list(parsed.sections),
                    "final_source_host": final_host,
                },
                relationships=relationships,
                authority_family="ercot-revision-request",
                filed_date=parsed.filed_date,
                current_version=parsed.source_status
                not in {SourceStatus.WITHDRAWN, SourceStatus.REJECTED},
                rights_status=RightsStatus.REVIEW_REQUIRED,
                extracted_text=parsed.text,
                publisher_evidence=(
                    AuthorityPublisherEvidence(
                        source=PublisherEvidenceSource.PARSED_CONTENT,
                        value=f"{family.upper()}{number}",
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
        family = key_match.group("family")
        number = key_match.group("number")
        item = key_match.group("item")
        if item is None:
            expected = f"{family.upper()}{number}"
            return any(
                evidence.source == PublisherEvidenceSource.PARSED_CONTENT
                and evidence.value.upper() == expected
                for evidence in record.publisher_evidence
            )
        for evidence in record.publisher_evidence:
            if evidence.source != PublisherEvidenceSource.SOURCE_IDENTIFIER:
                continue
            match = _ATTACHMENT_ID_RE.search(evidence.value)
            if (
                match is not None
                and match.group("family").casefold() == family.casefold()
                and match.group("number") == number
                and str(int(match.group("item"))) == str(int(item))
            ):
                return True
        return False
