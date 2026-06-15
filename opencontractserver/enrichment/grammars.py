"""Tier-2a: generic citation-SHAPE grammars (open-vocabulary detection).

These recognise citation *form* without knowing the body of law, so they catch
authorities outside the registry (state codes, CFR titles, obscure agencies).
Lower precedence than the Tier-1 registry extractor — see reconcile.py. No DB
access; pure functions over text returning Candidate spans.
"""

from __future__ import annotations

import re
from collections.abc import Iterator

from opencontractserver.enrichment import constants as C
from opencontractserver.enrichment.abbreviations import STATE_CODE_ABBREVIATIONS
from opencontractserver.enrichment.extractor import Candidate

# Confidence by grammar family — structured numeric cites are high precision;
# bare-Act detection (Task 11) is intentionally lower.
_CONF_STRUCTURED = 0.9

# A section token: digits, optional trailing letter, optional (a)(2) subsections,
# optional hyphenated rule tail (10b-5, 261.4).
_SEC = r"\d+[A-Za-z]?(?:\.\d+)?(?:[-–]\d+)?(?:\([0-9a-zA-Z]+\))*"

_USC_RE = re.compile(
    r"\b(?P<title>\d+)\s+U\.?\s?S\.?\s?C\.?\s+(?:§+\s*)?(?P<sec>" + _SEC + r")"
)
_CFR_RE = re.compile(
    r"\b(?P<title>\d+)\s+C\.?\s?F\.?\s?R\.?\s+(?:§+\s*)?(?P<sec>\d+\.\d+"
    r"(?:[-–]\d+)?(?:\([0-9a-zA-Z]+\))*)"
)
_FEDREG_RE = re.compile(r"\b(?P<vol>\d+)\s+Fed\.?\s?Reg\.?\s+(?P<page>\d[\d,]*)")
_PUBL_RE = re.compile(
    r"\bPub(?:lic)?\.?\s?L(?:aw)?\.?\s?No\.?\s?(?P<cong>\d+)[-–](?P<num>\d+)",
    re.IGNORECASE,
)
_STAT_RE = re.compile(r"\b(?P<vol>\d+)\s+Stat\.?\s+(?P<page>\d[\d,]*)")


def _cand(start, end, raw, key, jur, typ, conf=_CONF_STRUCTURED) -> Candidate:
    return Candidate(
        reference_type=C.REF_LAW,
        start=start,
        end=end,
        raw_text=raw,
        canonical_key=key,
        normalized_data={"authority": key.split(":", 1)[0], "tier": "grammar"},
        jurisdiction=jur,
        authority_type=typ,
        detection_tier=C.DETECTION_TIER_GRAMMAR,
        detection_confidence=conf,
    )


def _usc(text: str) -> Iterator[Candidate]:
    for m in _USC_RE.finditer(text):
        key = f"usc-{m.group('title')}:{m.group('sec').lower()}"
        yield _cand(
            m.start(), m.end(), m.group(0), key,
            C.JURISDICTION_US_FEDERAL, C.AUTHORITY_TYPE_STATUTE,
        )


def _cfr(text: str) -> Iterator[Candidate]:
    for m in _CFR_RE.finditer(text):
        key = f"cfr-{m.group('title')}:{m.group('sec').lower()}"
        yield _cand(
            m.start(), m.end(), m.group(0), key,
            C.JURISDICTION_US_FEDERAL, C.AUTHORITY_TYPE_REGULATION,
        )


def _fedreg(text: str) -> Iterator[Candidate]:
    for m in _FEDREG_RE.finditer(text):
        page = m.group("page").replace(",", "")
        key = f"fedreg:{m.group('vol')}.{page}"
        yield _cand(
            m.start(), m.end(), m.group(0), key,
            C.JURISDICTION_US_FEDERAL, C.AUTHORITY_TYPE_ADMIN_RULE,
        )


def _publ(text: str) -> Iterator[Candidate]:
    for m in _PUBL_RE.finditer(text):
        key = f"publ:{m.group('cong')}-{m.group('num')}"
        yield _cand(
            m.start(), m.end(), m.group(0), key,
            C.JURISDICTION_US_FEDERAL, C.AUTHORITY_TYPE_STATUTE,
        )


def _stat(text: str) -> Iterator[Candidate]:
    for m in _STAT_RE.finditer(text):
        page = m.group("page").replace(",", "")
        key = f"stat:{m.group('vol')}.{page}"
        yield _cand(
            m.start(), m.end(), m.group(0), key,
            C.JURISDICTION_US_FEDERAL, C.AUTHORITY_TYPE_STATUTE,
        )


class GenericCitationExtractor:
    """Run all Tier-2a shape grammars over text → list[Candidate]."""

    def __init__(self) -> None:
        # State-code alternation, longest-first so "Del. Code Ann. tit. 8" wins
        # over a hypothetical "Del. Code". Compiled once per instance.
        ordered = sorted(STATE_CODE_ABBREVIATIONS, key=len, reverse=True)
        self._state_alt = "|".join(re.escape(a) for a in ordered)
        self._state_re = (
            re.compile(
                r"(?P<abbr>" + self._state_alt + r")\s+(?:§+\s*)?(?P<sec>"
                + _SEC + r")"
            )
            if ordered
            else None
        )

    def extract(self, text: str) -> list[Candidate]:
        out: list[Candidate] = []
        out.extend(_usc(text))
        out.extend(_cfr(text))
        out.extend(_fedreg(text))
        out.extend(_publ(text))
        out.extend(_stat(text))
        out.extend(self._states(text))
        return out

    def _states(self, text: str) -> Iterator[Candidate]:
        if self._state_re is None:
            return
        for m in self._state_re.finditer(text):
            prefix, jur, typ = STATE_CODE_ABBREVIATIONS[m.group("abbr")]
            key = f"{prefix}:{m.group('sec').lower()}"
            yield _cand(m.start(), m.end(), m.group(0), key, jur, typ)
