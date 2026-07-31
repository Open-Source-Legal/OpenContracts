"""Deterministic Texas Utilities Code section provider."""

from __future__ import annotations

import re
from typing import ClassVar

from opencontractserver.enrichment.authority_sources import (
    AuthorityPublisherEvidence,
    AuthoritySourceRecord,
    AuthorityWeight,
    InstrumentType,
    PublisherEvidenceSource,
    RightsStatus,
    SourceStatus,
)
from opencontractserver.pipeline.base.authority_html import visible_html_text
from opencontractserver.pipeline.base.base_authority_source_provider import (
    AuthorityRequest,
    BaseAuthoritySourceProvider,
)
from opencontractserver.utils.safe_http import safe_fetch_bytes

_KEY_RE = re.compile(r"^tx-util:(?P<section>\d+[A-Za-z]?(?:\.\d+[A-Za-z]?)+)$")
_NEXT_SECTION_RE = re.compile(
    r"(?im)(?=^\s*(?:Sec\.|Section)\s+\d+[A-Za-z]?(?:\.\d+[A-Za-z]?)+\b)"
)


def parse_texas_statute_section(html: str, section: str) -> str:
    """Extract exactly one numbered section from an official chapter page."""

    text = visible_html_text(html)
    marker = re.compile(rf"(?im)^\s*(?:Sec\.|Section)\s+{re.escape(section)}\b[.:\s-]*")
    match = marker.search(text)
    if match is None:
        raise ValueError(f"Texas Utilities Code section {section} was not found")
    following = text[match.end() :]
    next_match = _NEXT_SECTION_RE.search(following)
    body = following[: next_match.start()] if next_match else following
    body = body.strip()
    if not body:
        raise ValueError(f"Texas Utilities Code section {section} had no text")
    return f"Sec. {section}. {body}"


class TexasStatuteAuthoritySourceProvider(BaseAuthoritySourceProvider):
    title = "Texas Electric Statutes"
    description = "Fetches official Texas Utilities Code section text."
    supported_prefixes: ClassVar[tuple[str, ...]] = ("tx-util",)
    license: ClassVar[str] = "public-domain"

    def can_handle(self, canonical_key: str) -> bool:
        return _KEY_RE.fullmatch(canonical_key) is not None

    def _locate_impl(self, canonical_key: str, **all_kwargs) -> AuthorityRequest:
        del all_kwargs
        match = _KEY_RE.fullmatch(canonical_key)
        if match is None:
            raise ValueError(f"unsupported Texas Utilities Code key {canonical_key!r}")
        section = match.group("section")
        chapter = section.split(".", 1)[0]
        return AuthorityRequest(
            canonical_key=canonical_key,
            url=(f"https://tcss.legis.texas.gov/resources/UT/htm/UT.{chapter}.htm"),
            citation=f"Tex. Util. Code § {section}",
            extra={"section": section, "chapter": chapter},
        )

    def _fetch_impl(
        self, request: AuthorityRequest, **all_kwargs
    ) -> list[AuthoritySourceRecord]:
        del all_kwargs
        content, final_host = safe_fetch_bytes(request.url, params=request.params)
        try:
            html = content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("Texas statute source was not UTF-8 HTML") from exc
        section = str(request.extra["section"])
        section_text = parse_texas_statute_section(html, section)
        return [
            AuthoritySourceRecord(
                canonical_key=request.canonical_key,
                title=f"Texas Utilities Code § {section}",
                source_url=request.url,
                source_identifier=f"UT-{section}",
                publisher="Texas Legislature",
                jurisdiction="us-tx",
                authority_type="statute",
                instrument_type=InstrumentType.STATUTE,
                issued_date=None,
                effective_from=None,
                effective_until=None,
                status=SourceStatus.CURRENT,
                authority_weight=AuthorityWeight.CONTROLLING,
                parent_key=None,
                version_label=None,
                # Preserve the exact publisher response as the sideloaded source
                # file. The canonical key and extracted text remain scoped to
                # this section even though the Legislature publishes it only as
                # part of a chapter page.
                content=content,
                mime_type="text/html",
                corpus_slug="texas-electric-statutes",
                metadata={
                    "chapter": request.extra["chapter"],
                    "final_source_host": final_host,
                    "raw_source_mime_type": "text/html",
                    "raw_source_scope": "chapter",
                    "rights_basis": (
                        "official codified Texas statute; government legal edict"
                    ),
                    "effective_date_review_state": "UNKNOWN_PENDING_REVIEW",
                },
                authority_family="texas-electric-law",
                current_version=True,
                rights_status=RightsStatus.PUBLIC_DOMAIN,
                extracted_text=section_text,
                publisher_evidence=(
                    AuthorityPublisherEvidence(
                        source=PublisherEvidenceSource.PARSED_CONTENT,
                        value=f"Sec. {section}",
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
        section = match.group("section")
        marker = re.compile(
            rf"^(?:Sec\.|Section)\s+{re.escape(section)}$",
            re.I,
        )
        return any(
            evidence.source == PublisherEvidenceSource.PARSED_CONTENT
            and bool(marker.fullmatch(evidence.value))
            for evidence in record.publisher_evidence
        )
