"""Discover official Texas bill-text and history attachments."""

from __future__ import annotations

import re
from pathlib import PurePosixPath
from urllib.parse import urlsplit

from opencontractserver.pipeline.base.authority_html import (
    extract_authority_links,
    normalize_html_text,
    stable_source_slug,
)
from opencontractserver.pipeline.base.base_authority_discovery_provider import (
    BaseAuthorityDiscoveryProvider,
    DiscoveryCandidate,
)
from opencontractserver.utils.safe_http import safe_fetch_text

_BILL_DOC_RE = re.compile(
    r"/tlodocs/(?P<session>\d{2}R)/(?P<family>[^/]+)/[^/]+/"
    r"(?P<chamber>SB|HB)0*(?P<number>\d+)"
    r"(?P<suffix>[A-Za-z0-9-]*)\.(?:htm|html|pdf|docx?)$",
    re.I,
)
_SUFFIX_STAGE = {
    "I": "introduced",
    "E": "engrossed",
    "F": "enrolled",
}
_STAFF_FAMILY_STAGES = {
    "analysis": "analysis",
    "fiscalnotes": "fiscal-note",
    "publiccomments": "comment",
    "summcomm": "committee-report",
    "witlistbill": "witness-list",
}
_STAFF_PRODUCT_MARKERS = (
    ("fiscal note", "fiscal-note"),
    ("bill analysis", "analysis"),
    ("analysis", "analysis"),
    ("public comment", "comment"),
    ("witness list", "witness-list"),
    ("impact statement", "impact-statement"),
    ("actuarial impact", "actuarial-impact"),
    ("hearing notice", "hearing-notice"),
    ("committee report", "committee-report"),
)


def _representation_rank(url: str) -> tuple[int, str]:
    """Prefer the publisher's HTML view for one document identity."""

    suffix = PurePosixPath(urlsplit(url).path).suffix.casefold()
    priority = {
        ".htm": 0,
        ".html": 0,
        ".pdf": 1,
        ".docx": 2,
        ".doc": 2,
    }.get(suffix, 3)
    return priority, url


def _bill_stage(*, suffix: str, family: str, title: str, url: str) -> str:
    upper_suffix = suffix.upper()
    normalized_family = family.casefold()
    # I/E/F identify a bill-text version only within the publisher's billtext
    # family. The same filename suffix is reused for distinct fiscal notes and
    # analyses, which must retain their own legislative-history identities.
    if normalized_family == "billtext" and upper_suffix in _SUFFIX_STAGE:
        return _SUFFIX_STAGE[upper_suffix]
    lowered = f"{family} {title}".casefold()
    family_stage = _STAFF_FAMILY_STAGES.get(normalized_family)
    if family_stage is not None:
        return family_stage
    for marker, stage in _STAFF_PRODUCT_MARKERS:
        if marker in lowered:
            return stage
    if upper_suffix in _SUFFIX_STAGE:
        return _SUFFIX_STAGE[upper_suffix]
    for name in ("introduced", "engrossed", "enrolled"):
        if name in lowered:
            return name
    return stable_source_slug(PurePosixPath(urlsplit(url).path).stem)


def _identity_metadata(*, stage: str, family: str) -> dict[str, str]:
    is_billtext = family.casefold() == "billtext"
    if is_billtext and stage in {"introduced", "engrossed"}:
        return {
            "instrument_type": "STATUTE",
            "status": "PROPOSED",
        }
    if is_billtext and stage == "enrolled":
        return {
            "instrument_type": "STATUTE",
            "status": "ENACTED",
        }
    if stage == "comment":
        return {
            "instrument_type": "COMMENT",
            "status": "PUBLISHED",
            "authority_weight": "ADVOCACY",
        }
    return {
        "instrument_type": "STAFF_MEMO",
        "status": "PUBLISHED",
    }


def parse_texas_bill_history(html: str, *, index_url: str) -> list[DiscoveryCandidate]:
    candidates_by_key: dict[str, DiscoveryCandidate] = {}
    for link in extract_authority_links(html, base_url=index_url):
        match = _BILL_DOC_RE.search(urlsplit(link.url).path)
        if match is None:
            continue
        session = match.group("session").lower()
        chamber = match.group("chamber").lower()
        number = int(match.group("number"))
        family = match.group("family")
        publisher_title = normalize_html_text(link.attribute("aria-label") or link.text)
        stage = _bill_stage(
            suffix=match.group("suffix"),
            family=family,
            title=publisher_title,
            url=link.url,
        )
        source_identifier = PurePosixPath(urlsplit(link.url).path).stem
        key = f"tx-{chamber}:{session}-{number}:{stage}"
        # Publisher bill-text versions have one stable identity per stage
        # (introduced/engrossed/enrolled). Legislative-history stages do not:
        # the listing can contain several distinct analyses, fiscal notes, or
        # committee products. Bind those keys to the publisher filename so two
        # official attachments can never collapse onto one canonical identity.
        if stage not in _SUFFIX_STAGE.values():
            key = f"{key}:{source_identifier.casefold()}"
        candidate = DiscoveryCandidate(
            canonical_key=key,
            url=link.url,
            title=publisher_title or f"Texas {chamber[0].upper()}.B. {number} {stage}",
            extra={
                "chamber": chamber.upper(),
                "session": session.upper(),
                "number": number,
                "stage": stage,
                "source_identifier": source_identifier,
                "metadata": _identity_metadata(stage=stage, family=family),
            },
        )
        prior = candidates_by_key.get(key)
        if prior is None or _representation_rank(candidate.url) < _representation_rank(
            prior.url
        ):
            # Texas publishes PDF/HTML/DOCX representations of the same
            # legislative-history document. They share one publisher document
            # identifier and therefore one canonical key; retain the portable
            # HTML representation instead of fabricating content variants.
            candidates_by_key[key] = candidate
    return list(candidates_by_key.values())


class TexasBillHistoryDiscoveryProvider(BaseAuthorityDiscoveryProvider):
    title = "Texas Bill History Discovery"
    description = "Discovers official bill text and legislative-history documents."
    license = "mixed-review-required"
    link_only_discovery = True

    def _fetch_index_impl(self, index_url: str, **all_kwargs) -> tuple[str, str]:
        del all_kwargs
        return safe_fetch_text(index_url)

    def _parse_index_impl(
        self, html: str, *, index_url: str, **all_kwargs
    ) -> list[DiscoveryCandidate]:
        del all_kwargs
        return parse_texas_bill_history(html, index_url=index_url)
