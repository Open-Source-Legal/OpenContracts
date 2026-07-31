"""Deterministic Texas bill/version provider."""

from __future__ import annotations

import re
from typing import ClassVar
from urllib.parse import parse_qs, urlsplit

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

_KEY_RE = re.compile(
    r"^tx-(?P<chamber>sb|hb):(?P<session>\d{2}r)-(?P<number>\d+)"
    r"(?::(?P<stage>[a-z0-9-]+)(?::(?P<document_id>[a-z0-9-]+))?)?$"
)
_STAGE_SUFFIX = {
    "introduced": "I",
    "engrossed": "E",
    "enrolled": "F",
    "final": "F",
    "signed": "F",
}
_STAGE_STATUS = {
    "introduced": SourceStatus.PROPOSED,
    "engrossed": SourceStatus.PROPOSED,
    "enrolled": SourceStatus.ENACTED,
    "final": SourceStatus.ENACTED,
    "signed": SourceStatus.SIGNED,
}
_BILL_TEXT_STAGES = frozenset(_STAGE_STATUS)
_STAFF_PRODUCT_STAGE_MARKERS = {
    "analysis": ("analysis",),
    "comment": ("public comment", "comment"),
    "fiscal-note": ("fiscal note",),
    "committee-report": ("committee report",),
    "witness-list": ("witness list",),
    "impact-statement": ("impact statement",),
    "actuarial-impact": ("actuarial impact",),
    "hearing-notice": ("hearing notice",),
}
_PUBLISHER_BILL_PATH_RE = re.compile(
    r"/tlodocs/(?P<session>\d{2}R)/[^/]+/[^/]+/"
    r"(?P<document_id>(?P<chamber>SB|HB)0*(?P<number>\d+)"
    r"(?P<suffix>[A-Za-z0-9-]*))"
    r"\.(?:htm|html|pdf|docx?)$",
    re.I,
)
_PUBLISHER_SUFFIX_STAGE = {"I": "introduced", "E": "engrossed", "F": "enrolled"}


def _instrument_type_for_stage(stage: object) -> InstrumentType:
    normalized = str(stage) if stage is not None else None
    if normalized in _BILL_TEXT_STAGES:
        return InstrumentType.STATUTE
    if normalized == "comment":
        return InstrumentType.COMMENT
    if normalized is None or normalized in _STAFF_PRODUCT_STAGE_MARKERS:
        # A no-stage request is the official bill-history landing page, not a
        # bill-text version.
        return InstrumentType.STAFF_MEMO
    raise ValueError(f"unknown Texas bill document stage {normalized!r}")


class TexasBillAuthoritySourceProvider(BaseAuthoritySourceProvider):
    title = "Texas Large-Load Legislative History"
    description = "Fetches official Texas bill histories and bill-text versions."
    supported_prefixes: ClassVar[tuple[str, ...]] = ("tx-sb", "tx-hb")
    # Official availability does not establish that every analysis, fiscal
    # note, report, or hearing artifact is a legal edict.
    license: ClassVar[str] = "mixed-review-required"

    def can_handle(self, canonical_key: str) -> bool:
        return _KEY_RE.fullmatch(canonical_key) is not None

    def _locate_impl(self, canonical_key: str, **all_kwargs) -> AuthorityRequest:
        match = _KEY_RE.fullmatch(canonical_key)
        if match is None:
            raise ValueError(f"unsupported Texas bill key {canonical_key!r}")
        candidate = all_kwargs.get("discovery_candidate")
        chamber = match.group("chamber").upper()
        session = match.group("session").upper()
        number = int(match.group("number"))
        stage = match.group("stage")
        if candidate is not None:
            url = candidate.url
            title = candidate.title
            candidate_extra = dict(candidate.extra)
        elif stage:
            suffix = _STAGE_SUFFIX.get(stage)
            if suffix is None:
                raise ValueError(
                    f"Texas bill stage {stage!r} requires a discovery candidate URL"
                )
            url = (
                f"https://capitol.texas.gov/tlodocs/{session}/billtext/html/"
                f"{chamber}{number:05d}{suffix}.htm"
            )
            title = None
            candidate_extra = {}
        else:
            url = (
                "https://capitol.texas.gov/BillLookup/History.aspx"
                f"?LegSess={session}&Bill={chamber}{number}"
            )
            title = None
            candidate_extra = {}
        return AuthorityRequest(
            canonical_key=canonical_key,
            url=url,
            citation=f"{session} {chamber[0]}.B. {number}",
            extra={
                "chamber": chamber,
                "session": session,
                "number": number,
                "stage": stage,
                "title": title,
                **candidate_extra,
            },
        )

    def _fetch_impl(
        self, request: AuthorityRequest, **all_kwargs
    ) -> list[AuthoritySourceRecord]:
        del all_kwargs
        stage = request.extra.get("stage")
        chamber = str(request.extra["chamber"])
        session = str(request.extra["session"])
        number = int(request.extra["number"])
        prefix = f"tx-{chamber.lower()}"
        root_key = f"{prefix}:{session.lower()}-{number}"
        title = request.extra.get("title") or (
            f"Texas {'Senate' if chamber == 'SB' else 'House'} Bill {number}"
            + (f", {str(stage).replace('-', ' ')} version" if stage else " history")
        )
        source_identifier = request.extra.get("source_identifier") or (
            f"{session}-{chamber}{number}" + (f"-{stage}" if stage else "")
        )
        instrument_type = _instrument_type_for_stage(stage)
        publisher_evidence = [
            AuthorityPublisherEvidence(
                source=PublisherEvidenceSource.URL,
                value=request.url,
                locator=request.url,
            )
        ]
        if request.extra.get("title"):
            publisher_evidence.append(
                AuthorityPublisherEvidence(
                    source=PublisherEvidenceSource.TITLE,
                    value=str(request.extra["title"]),
                    locator=request.url,
                )
            )
        record = fetch_and_extract_authority_record(
            url=request.url,
            canonical_key=request.canonical_key,
            title=str(title),
            source_identifier=str(source_identifier),
            publisher="Texas Legislature",
            jurisdiction="us-tx",
            authority_type="statute",
            instrument_type=instrument_type,
            status=_STAGE_STATUS.get(str(stage), SourceStatus.PUBLISHED),
            authority_weight=(
                AuthorityWeight.ADVOCACY
                if stage == "comment"
                else AuthorityWeight.EVIDENTIARY
            ),
            corpus_slug="texas-large-load-legislative-history",
            parent_key=root_key if request.canonical_key != root_key else None,
            version_label=str(stage) if stage else None,
            issued_date=request.extra.get("issued_date"),
            effective_from=request.extra.get("effective_from"),
            authority_family="texas-legislative-history",
            current_version=bool(stage in {"enrolled", "final", "signed"}),
            rights_status=RightsStatus.REVIEW_REQUIRED,
            metadata={
                "session": session,
                "chamber": chamber,
                "bill_number": number,
                "stage": stage,
                "rights_basis": (
                    "legislative-history attachment; legal-edict status has "
                    "not been established"
                ),
            },
            publisher_evidence=tuple(publisher_evidence),
            params=request.params,
        )
        return [record]

    def verify_publisher_evidence(
        self, canonical_key: str, record: AuthoritySourceRecord
    ) -> bool:
        key_match = _KEY_RE.fullmatch(canonical_key)
        if key_match is None:
            return False
        expected_session = key_match.group("session").upper()
        expected_chamber = key_match.group("chamber").upper()
        expected_number = int(key_match.group("number"))
        expected_stage = key_match.group("stage")
        expected_document_id = key_match.group("document_id")
        titles = [
            evidence.value
            for evidence in record.publisher_evidence
            if evidence.source == PublisherEvidenceSource.TITLE
        ]
        for evidence in record.publisher_evidence:
            if evidence.source != PublisherEvidenceSource.URL:
                continue
            parsed = urlsplit(evidence.value)
            path_match = _PUBLISHER_BILL_PATH_RE.search(parsed.path)
            if path_match is not None:
                if (
                    path_match.group("session").upper() != expected_session
                    or path_match.group("chamber").upper() != expected_chamber
                    or int(path_match.group("number")) != expected_number
                ):
                    continue
                if (
                    expected_document_id is not None
                    and path_match.group("document_id").casefold()
                    != expected_document_id.casefold()
                ):
                    continue
                observed_stage = _PUBLISHER_SUFFIX_STAGE.get(
                    path_match.group("suffix").upper()
                )
                staff_markers = _STAFF_PRODUCT_STAGE_MARKERS.get(str(expected_stage))
                if staff_markers and any(
                    any(marker in title.casefold() for marker in staff_markers)
                    for title in titles
                ):
                    return True
                if expected_stage == observed_stage:
                    return True
                # The publisher's F suffix proves the enrolled/final family but
                # not the finer "final"/"signed" label.  Require that label in
                # the independently observed listing title.
                if (
                    observed_stage == "enrolled"
                    and expected_stage in {"final", "signed"}
                    and any(
                        re.search(
                            rf"(?<![A-Za-z0-9]){re.escape(expected_stage)}"
                            r"(?![A-Za-z0-9])",
                            title,
                            re.I,
                        )
                        for title in titles
                    )
                ):
                    return True
                continue
            if expected_stage is not None:
                continue
            query = {
                key.casefold(): values[-1]
                for key, values in parse_qs(parsed.query).items()
                if values
            }
            bill = query.get("bill", "")
            if (
                query.get("legsess", "").upper() == expected_session
                and bill[:2].upper() == expected_chamber
                and bill[2:].isdigit()
                and int(bill[2:]) == expected_number
            ):
                return True
        return False
