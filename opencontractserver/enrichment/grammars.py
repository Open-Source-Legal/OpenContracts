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
_CONF_BARE_ACT = 0.55

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
# The periods are optional (``Fed\.?``/``Reg\.?``) to tolerate OCR that drops
# punctuation, so "40 Fed Reg 1234" matches alongside "40 Fed. Reg. 1234". The
# leading volume number + trailing page number keep false positives low; "Fed"
# never matches "Federal", so prose like "Federal Regulation 40" is excluded.
_FEDREG_RE = re.compile(r"\b(?P<vol>\d+)\s+Fed\.?\s?Reg\.?\s+(?P<page>\d[\d,]*)")
# "No." is optional: the Bluebook short form "Pub. L. 117-58" (no "No.") is the
# dominant form in filings and opinions alongside "Pub. L. No. 117-58".
_PUBL_RE = re.compile(
    r"\bPub(?:lic)?\.?\s?L(?:aw)?\.?\s?(?:No\.?\s?)?(?P<cong>\d+)[-–](?P<num>\d+)",
    re.IGNORECASE,
)
_STAT_RE = re.compile(r"\b(?P<vol>\d+)\s+Stat\.?\s+(?P<page>\d[\d,]*)")

# Bare Act: "the Clean Water Act", "the Bank Holding Company Act of 1956".
# Require >=1 capitalized word before "Act" so bare "the Act" never matches.
_BARE_ACT_RE = re.compile(
    r"\bthe\s+(?P<name>(?:[A-Z][A-Za-z'&.\-]+\s+){1,6}Act)"
    r"(?:\s+of\s+(?P<year>\d{4}))?"
)


def _slug_act(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")


def _canonical_act_prefix(name: str) -> str | None:
    """Map a matched bare-Act name to its registry canonical prefix, if known.

    Reuses the Tier-1 registry alias table (``constants.AUTHORITY_PREFIX``) so a
    popular-name Act collapses to the SAME prefix the registry uses — e.g.
    "Securities Exchange Act" / "Exchange Act" -> ``exchange-act``, "Securities
    Act" -> ``securities-act`` — instead of fragmenting into distinct
    ``act:<slug>`` keys per spelling/year. The matched ``name`` group never
    includes the trailing " of <year>" (that is captured separately), so a year
    suffix can never defeat the lookup. A leading U.S. jurisdiction qualifier
    ("U.S.", "U. S.", "United States") is stripped before the lookup so "the
    U.S. Securities Exchange Act of 1934" canonicalises like its bare form.
    Returns ``None`` for an unrecognised Act (the open-vocabulary ``act:<slug>``
    fallback — keyed off the ORIGINAL name — then applies).
    """
    normalized = re.sub(r"\s+", " ", name.strip().lower())
    normalized = re.sub(
        r"^(?:u\.?\s*s\.?(?:a\.?)?|united states(?: of america)?)\s+",
        "",
        normalized,
    )
    return C.AUTHORITY_PREFIX.get(normalized)


def _cand(
    start, end, raw, key, jur, typ, conf=_CONF_STRUCTURED, extra=None
) -> Candidate:
    normalized_data = {
        "authority": key.split(":", 1)[0],
        "tier": C.DETECTION_TIER_GRAMMAR,
    }
    # Grammar-specific fields (e.g. bare-Act ``section``/``display_name``) are
    # merged here rather than mutated onto the returned object by the caller, so
    # the dict is fully formed in one place and never aliased.
    if extra:
        normalized_data.update(extra)
    return Candidate(
        reference_type=C.REF_LAW,
        start=start,
        end=end,
        raw_text=raw,
        canonical_key=key,
        normalized_data=normalized_data,
        jurisdiction=jur,
        authority_type=typ,
        detection_tier=C.DETECTION_TIER_GRAMMAR,
        detection_confidence=conf,
    )


def _usc(text: str) -> Iterator[Candidate]:
    for m in _USC_RE.finditer(text):
        key = f"usc-{m.group('title')}:{m.group('sec').lower()}"
        yield _cand(
            m.start(),
            m.end(),
            m.group(0),
            key,
            C.JURISDICTION_US_FEDERAL,
            C.AUTHORITY_TYPE_STATUTE,
        )


def _cfr(text: str) -> Iterator[Candidate]:
    for m in _CFR_RE.finditer(text):
        key = f"cfr-{m.group('title')}:{m.group('sec').lower()}"
        yield _cand(
            m.start(),
            m.end(),
            m.group(0),
            key,
            C.JURISDICTION_US_FEDERAL,
            C.AUTHORITY_TYPE_REGULATION,
        )


def _fedreg(text: str) -> Iterator[Candidate]:
    for m in _FEDREG_RE.finditer(text):
        page = m.group("page").replace(",", "")
        key = f"fedreg:{m.group('vol')}.{page}"
        yield _cand(
            m.start(),
            m.end(),
            m.group(0),
            key,
            C.JURISDICTION_US_FEDERAL,
            C.AUTHORITY_TYPE_ADMIN_RULE,
        )


def _publ(text: str) -> Iterator[Candidate]:
    for m in _PUBL_RE.finditer(text):
        key = f"publ:{m.group('cong')}-{m.group('num')}"
        yield _cand(
            m.start(),
            m.end(),
            m.group(0),
            key,
            C.JURISDICTION_US_FEDERAL,
            C.AUTHORITY_TYPE_STATUTE,
        )


def _stat(text: str) -> Iterator[Candidate]:
    for m in _STAT_RE.finditer(text):
        page = m.group("page").replace(",", "")
        key = f"stat:{m.group('vol')}.{page}"
        yield _cand(
            m.start(),
            m.end(),
            m.group(0),
            key,
            C.JURISDICTION_US_FEDERAL,
            C.AUTHORITY_TYPE_STATUTE,
        )


def _bare_acts(text: str) -> Iterator[Candidate]:
    for m in _BARE_ACT_RE.finditer(text):
        # The regex guarantees >=1 capitalized word before "Act", so ``name``
        # always has >=2 whitespace tokens and bare "the Act" never reaches here.
        name = m.group("name")
        year = m.group("year")
        canonical = _canonical_act_prefix(name)
        if canonical is not None:
            # Recognised body of law: emit the registry prefix as a section-less
            # whole-act key (the year is identity, not a locator, so it is
            # dropped). Every spelling collapses to one key that dedups with
            # Tier-1 mentions and resolves to the existing authority corpus.
            jur, typ = C.classify_prefix(canonical)
            yield _cand(
                m.start(),
                m.end(),
                m.group(0),
                canonical,
                jur,
                typ,
                conf=_CONF_STRUCTURED,
                extra={"section": None, "display_name": name},
            )
            continue
        # Unknown Act — open-vocabulary fallback. Jurisdiction is assumed
        # ``us-federal``: the shape alone can't tell "the Clean Air Act"
        # (federal) from "the Texas Business Organizations Act" (state). The low
        # _CONF_BARE_ACT signal flags the uncertainty; state-act disambiguation
        # is a Phase-1 follow-up.
        slug = _slug_act(name)
        key = f"act:{slug}-{year}" if year else f"act:{slug}"
        yield _cand(
            m.start(),
            m.end(),
            m.group(0),
            key,
            C.JURISDICTION_US_FEDERAL,
            C.AUTHORITY_TYPE_STATUTE,
            conf=_CONF_BARE_ACT,
            extra={"section": None, "display_name": name},
        )


class GenericCitationExtractor:
    """Run all Tier-2a shape grammars over text → list[Candidate]."""

    def __init__(self) -> None:
        # State-code alternation, longest-first so "Del. Code Ann. tit. 8" wins
        # over a hypothetical "Del. Code". Escaped spaces become ``\s+`` so OCR
        # double-spaces / line-break wraps still match; the captured text is
        # whitespace-normalized before lookup (``_state_canon``).
        ordered = sorted(STATE_CODE_ABBREVIATIONS, key=len, reverse=True)
        self._state_alt = "|".join(re.escape(a).replace(r"\ ", r"\s+") for a in ordered)
        self._state_canon = {
            re.sub(r"\s+", " ", a): v for a, v in STATE_CODE_ABBREVIATIONS.items()
        }
        self._state_re = (
            re.compile(
                r"(?P<abbr>" + self._state_alt + r")\s+(?:§+\s*)?(?P<sec>" + _SEC + r")"
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
        out.extend(_bare_acts(text))
        out.extend(self._states(text))
        return out

    def _states(self, text: str) -> Iterator[Candidate]:
        if self._state_re is None:
            return
        for m in self._state_re.finditer(text):
            abbr = re.sub(r"\s+", " ", m.group("abbr"))
            prefix, jur, typ = self._state_canon[abbr]
            key = f"{prefix}:{m.group('sec').lower()}"
            yield _cand(m.start(), m.end(), m.group(0), key, jur, typ)
