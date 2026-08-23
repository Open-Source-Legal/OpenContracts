"""Deterministic reference extraction from document text (no DB access).

The extractor recognises *explicit* references with high-precision grammars and
emits :class:`Candidate` spans. Target resolution (which document/section/corpus
a candidate points at) is the resolver's job — the extractor only normalises
what the text itself states (e.g. a law citation's canonical key).
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass, field

from opencontractserver.enrichment import constants as C


@dataclass
class Candidate:
    """A single detected reference span within one document's text."""

    reference_type: str
    start: int
    end: int
    raw_text: str
    canonical_key: str | None = None
    normalized_data: dict = field(default_factory=dict)
    # Phase 1 classification + detection provenance. Registry-tier candidates
    # leave jurisdiction/authority_type None (filled later from the namespace
    # table); generic-grammar candidates set them at detection time.
    jurisdiction: str | None = None
    authority_type: str | None = None
    detection_tier: str = C.DETECTION_TIER_REGISTRY
    detection_confidence: float = 1.0


# Section number as it appears in a citation: "145", "4(a)(2)", "144A", and —
# critically for REGULATIONS — dotted forms like "120.41" or "1301.051".
#
# The dotted alternative is not cosmetic. Without it, statute-style numbering
# works and regulation-style numbering fails in two different ways, both silent:
# "Section 120.10 of the ITAR" matched nothing at all (the pattern consumed
# "120" and then required " of", finding "."), while "ITAR Section 120.41"
# matched the PREFIX "120" and produced `itar:120` — a citation to the
# definition of "specially designed" resolving to the Part 120 overview. Every
# CFR-, state-admin-code- and municipal-code-style corpus has this shape.
#
# `(?:\.\d+)*` requires digits after each dot, so a sentence-final period is
# never swallowed: "…Section 120.10 of the ITAR." keeps its full stop.
_SECTION_NUMBER = r"\d+(?:\.\d+)*[A-Za-z]?(?:\([0-9a-zA-Z]+\))*"

# The token introducing a section. "§" (and "§§" for ranges) is the dominant
# form in regulatory text and was previously unmatched, so "ITAR § 120.41" and
# "22 C.F.R. § 126.1" produced nothing. "Part" is included because part-level
# citation is a real form for regulations ("Part 122 of the ITAR") and the
# authority alternation gates it — "Part 3 of the Agreement" cannot match,
# because "Agreement" is not a registered authority alias.
_SECTION_TOKEN = r"(?:Sections?\s+|Parts?\s+|§§?\s*)"

# Roman-numeral divisions ("Category XI of the United States Munitions List").
# Kept separate from _SECTION_NUMBER so that Roman numerals can only ever match
# behind an explicit divider word AND an authority alias — "Section I of the
# Agreement" must not become a citation. Emitted lowercase by the shared
# candidate builder, which is required: authority-key matching is
# case-sensitive on the section part and the extractor lowercases, so an
# uppercase key would be unreachable.
#
# Deliberately narrow: "Category" only. Roman-numeral divisions are rare, and
# every registered alias on the install shares this pattern — widening it to
# Title/Article/Chapter would fire against every other authority corpus
# (dgcl, tx-occ, the fw-* family) for no demonstrated gain. Add a divider word
# here when a corpus actually needs it, with a test that shows the citation
# form it is meant to catch.
_DIVISION_TOKEN = r"(?:Category|Categories)\s+"
_DIVISION_NUMBER = r"[IVXLCivxlc]+"

# NOTE: Export Control Classification Numbers ("ECCN 3A611") are deliberately
# NOT here. They are a citation SHAPE — the literal "ECCN" anchors the form, so
# it is recognisable without knowing which body of law is installed — and shapes
# belong in the Tier-2a grammars, emitting a shape-level prefix (``eccn:3a611``)
# that a pack maps to its own key with one ``equivalences`` row. See
# ``grammars._eccns`` and the ``ECCN_PREFIX`` note in ``constants``.


# "Section 145", "Section 4(a)(2)", "Section 7(a)(2)(B)" followed by authority.
# The authority alternation is compiled per extractor instance from an alias
# registry (static defaults + DB-declared aliases on authority corpora), so
# adding a body of law never requires a code change. Aliases are matched
# longest-first so "Securities Exchange Act" wins over "Exchange Act".
def _compile_law_re(aliases) -> re.Pattern:
    alt = "|".join(re.escape(a) for a in sorted(aliases, key=len, reverse=True))
    return re.compile(
        _SECTION_TOKEN + r"(?P<sec>" + _SECTION_NUMBER + r")\s+of\s+(?:the\s+)?"
        r"(?P<auth>" + alt + r")",
        re.IGNORECASE,
    )


def _compile_prefix_law_re(aliases) -> re.Pattern:
    """Form-style citations with the authority BEFORE the section:
    "Securities Act Section 4(a)(5)", "Investment Company Act Section 3(c)",
    "ITAR § 120.41", "22 C.F.R. § 126.1"."""
    alt = "|".join(re.escape(a) for a in sorted(aliases, key=len, reverse=True))
    return re.compile(
        r"(?P<auth>"
        + alt
        + r")\s*"
        + _SECTION_TOKEN
        + r"(?P<sec>"
        + _SECTION_NUMBER
        + r")",
        re.IGNORECASE,
    )


def _compile_division_re(aliases) -> re.Pattern:
    """Roman-numeral divisions of a named authority, in either order:
    "Category XI of the United States Munitions List", "USML Category VIII"."""
    alt = "|".join(re.escape(a) for a in sorted(aliases, key=len, reverse=True))
    return re.compile(
        _DIVISION_TOKEN + r"(?P<sec>" + _DIVISION_NUMBER + r")\s+of\s+(?:the\s+)?"
        r"(?P<auth>" + alt + r")"
        r"|"
        r"(?P<auth2>"
        + alt
        + r")\s+"
        + _DIVISION_TOKEN
        + r"(?P<sec2>"
        + _DIVISION_NUMBER
        + r")",
        re.IGNORECASE,
    )


# Statute-internal relative idiom: "§ 251 of this title", "Section 141(b) of
# this chapter". Only keyable when the caller supplies the document's own
# authority (from the authority corpus's custom_meta) as default_authority.
_LAW_RELATIVE_RE = re.compile(
    r"(?:§|Section)\s+(?P<sec>\d+[A-Za-z]?(?:\([0-9a-zA-Z]+\))*)\s+of\s+this\s+"
    r"(?:title|chapter)",
    re.IGNORECASE,
)
# Bare SEC rule citations: "Rule 506(b)", "Rule 504(b)(1)", "Rule 144A",
# "Rule 10b-5". No authority name in text — keyed under SEC_RULE_PREFIX.
_RULE_RE = re.compile(
    r"Rule\s+(?P<rule>\d+[A-Za-z]?(?:-\d+)?(?:\([0-9a-zA-Z]+\))*)",
)
_EXHIBIT_RE = re.compile(r"Exhibit\s+(?P<num>\d+\.\d+[A-Za-z()]*)", re.IGNORECASE)
# see / under  ...  "Heading"  (curly or straight quotes)
_SECTION_RE = re.compile(
    r"(?:see|under)\b[^\"“]{0,40}?[\"“]" r"(?P<head>[A-Z][^\"”]{2,60})[\"”]",
    re.IGNORECASE,
)
# Defined-term DEFINITION sites — high precision only, both forms combined into
# one alternation so they are scanned in a single document-order pass:
#   1. parenthetical:  (the "Company")  ("Notes")  (collectively, the "Shares")
#   2. copular:        "Change of Control" means | shall mean | refers to
_TERM_RE = re.compile(
    r"\((?:the\s+|collectively,?\s+the\s+|each\s+an?\s+|together(?:,)?\s+the\s+)?"
    r"[\"“](?P<paren_term>[A-Z][^\"”]{1,60}?)[\"”]"
    r"|"
    r"[\"“](?P<means_term>[A-Z][^\"”]{1,60}?)[\"”]\s+"
    r"(?:means\b|shall\s+mean\b|refers\s+to\b|has\s+the\s+meaning\b)",
)


def _slugify_term(term: str) -> str:
    """Normalize a defined term to a stable cross-corpus key fragment."""
    return re.sub(r"[^a-z0-9]+", "-", term.strip().lower()).strip("-")


def normalize_reference_types(
    reference_types: set[str] | tuple[str, ...] | list[str] | None,
) -> set[str] | None:
    """Normalize a caller-supplied reference-type filter to a set, or ``None``.

    ``None`` is the "no filter, extract everything" sentinel. Shared by
    :meth:`ReferenceExtractor.extract` and
    :meth:`opencontractserver.enrichment.grammars.GenericCitationExtractor.extract`
    so the sentinel/type contract has a single edit point.
    """
    return set(reference_types) if reference_types is not None else None


class ReferenceExtractor:
    """Stateless-per-text extractor: ``extract(text) -> list[Candidate]``.

    ``authority_aliases`` maps authority alias (as it appears in text) ->
    canonical key prefix; defaults to the static ``AUTHORITY_PREFIX`` set.
    Callers with corpus context should pass the merged registry from
    :func:`opencontractserver.enrichment.authorities.authority_alias_registry`.

    ``default_authority`` keys relative citations ("§ 251 of this title")
    when extracting from a statute document that knows its own authority;
    without it, relative citations are skipped (they cannot be keyed).
    """

    def __init__(self, authority_aliases: dict[str, str] | None = None) -> None:
        aliases = authority_aliases or C.AUTHORITY_PREFIX
        self._alias_to_prefix = {k.lower(): v for k, v in aliases.items()}
        self._law_re = _compile_law_re(self._alias_to_prefix)
        self._prefix_law_re = _compile_prefix_law_re(self._alias_to_prefix)
        self._division_re = _compile_division_re(self._alias_to_prefix)

    def extract(
        self,
        text: str,
        default_authority: str | None = None,
        reference_types: set[str] | tuple[str, ...] | list[str] | None = None,
    ) -> list[Candidate]:
        wanted = normalize_reference_types(reference_types)
        out: list[Candidate] = []
        if wanted is None or C.REF_LAW in wanted:
            out.extend(self._laws(text))
            out.extend(self._prefix_laws(text))
            out.extend(self._divisions(text))
            out.extend(self._rules(text))
            if default_authority:
                out.extend(self._relative_laws(text, default_authority))
        if wanted is None or C.REF_DOCUMENT in wanted:
            out.extend(self._exhibits(text))
        if wanted is None or C.REF_SECTION in wanted:
            out.extend(self._sections(text))
        if wanted is None or C.REF_DEFINED_TERM in wanted:
            out.extend(self._terms(text))
        return out

    def _law_candidate(self, m: re.Match) -> Candidate:
        sec = m.group("sec")
        auth_text = m.group("auth")
        prefix = self._alias_to_prefix[auth_text.lower()]
        return Candidate(
            reference_type=C.REF_LAW,
            start=m.start(),
            end=m.end(),
            raw_text=m.group(0),
            canonical_key=f"{prefix}:{sec.lower()}",
            normalized_data={
                "authority": prefix,
                "section": sec,
                "authority_text": auth_text,
            },
        )

    def _laws(self, text: str) -> Iterator[Candidate]:
        for m in self._law_re.finditer(text):
            yield self._law_candidate(m)

    def _prefix_laws(self, text: str) -> Iterator[Candidate]:
        for m in self._prefix_law_re.finditer(text):
            yield self._law_candidate(m)

    def _divisions(self, text: str) -> Iterator[Candidate]:
        """Roman-numeral divisions ("Category XI of the U.S. Munitions List").

        The compiled pattern carries both orders in one alternation, so exactly
        one of the two group pairs is populated per match.
        """
        for m in self._division_re.finditer(text):
            sec = m.group("sec") or m.group("sec2")
            auth_text = m.group("auth") or m.group("auth2")
            if not sec or not auth_text:
                continue
            prefix = self._alias_to_prefix[auth_text.lower()]
            yield Candidate(
                reference_type=C.REF_LAW,
                start=m.start(),
                end=m.end(),
                raw_text=m.group(0),
                canonical_key=f"{prefix}:{sec.lower()}",
                normalized_data={
                    "authority": prefix,
                    "section": sec,
                    "authority_text": auth_text,
                },
            )

    def _rules(self, text: str) -> Iterator[Candidate]:
        for m in _RULE_RE.finditer(text):
            rule = m.group("rule")
            yield Candidate(
                reference_type=C.REF_LAW,
                start=m.start(),
                end=m.end(),
                raw_text=m.group(0),
                canonical_key=f"{C.SEC_RULE_PREFIX}:{rule.lower()}",
                normalized_data={
                    "authority": C.SEC_RULE_PREFIX,
                    "section": rule,
                    "rule": True,
                },
            )

    def _relative_laws(self, text: str, authority: str) -> Iterator[Candidate]:
        for m in _LAW_RELATIVE_RE.finditer(text):
            sec = m.group("sec")
            yield Candidate(
                reference_type=C.REF_LAW,
                start=m.start(),
                end=m.end(),
                raw_text=m.group(0),
                canonical_key=f"{authority}:{sec.lower()}",
                normalized_data={
                    "authority": authority,
                    "section": sec,
                    "relative": True,
                },
            )

    def _exhibits(self, text: str) -> Iterator[Candidate]:
        for m in _EXHIBIT_RE.finditer(text):
            yield Candidate(
                reference_type=C.REF_DOCUMENT,
                start=m.start(),
                end=m.end(),
                raw_text=m.group(0),
                normalized_data={"exhibit_number": m.group("num")},
            )

    def _sections(self, text: str) -> Iterator[Candidate]:
        for m in _SECTION_RE.finditer(text):
            head = m.group("head").strip()
            # Span covers the quoted heading (including the surrounding quotes).
            yield Candidate(
                reference_type=C.REF_SECTION,
                start=m.start("head") - 1,
                end=m.end("head") + 1,
                raw_text=m.group(0),
                normalized_data={"heading": head},
            )

    def _terms(self, text: str) -> Iterator[Candidate]:
        """Defined-term DEFINITION sites, deduped by slug, capped per document.

        Opt-in (not in the default reference-type set). The first
        ``MAX_DEFINED_TERMS`` *unique* definition sites win — the cap is on
        emitted (distinct) terms, not raw regex hits, so a wall of repeated
        early definitions (e.g. 50x ``(the "Company")``) cannot exhaust the
        quota before a later distinct term is reached. Both grammar forms are
        merged in document order, so a document heavy in parenthetical
        definitions cannot starve the "means" form. A separate, larger
        ``MAX_DEFINED_TERM_SCAN`` ceiling bounds total hits inspected so a
        pathologically duplicate-heavy document still terminates. Each
        definition becomes a cross-corpus-trackable stub keyed ``term:<slug>``
        — the same philosophy as law citations.
        """
        seen: set[str] = set()
        emitted = 0
        for examined, m in enumerate(_TERM_RE.finditer(text), start=1):
            # Unique-term quota: the first N DISTINCT definition sites win.
            if emitted >= C.MAX_DEFINED_TERMS:
                return
            # Raw-scan DoS ceiling: a duplicate-heavy document must still
            # terminate even before N unique terms accrue (duplicates do not
            # consume the quota above, so this budget is intentionally larger).
            if examined > C.MAX_DEFINED_TERM_SCAN:
                return
            term_group = (
                "paren_term" if m.group("paren_term") is not None else "means_term"
            )
            kind = "parenthetical" if term_group == "paren_term" else "means"
            # Trim trailing punctuation captured inside the quotes
            # (e.g. (the "Notes," ...) -> "Notes").
            term = m.group(term_group).strip().rstrip(C.TRAILING_PUNCT)
            slug = _slugify_term(term)
            if not slug or slug in seen:
                continue
            seen.add(slug)
            emitted += 1
            yield Candidate(
                reference_type=C.REF_DEFINED_TERM,
                start=m.start(term_group) - 1,
                end=m.end(term_group) + 1,
                raw_text=term,
                canonical_key=f"term:{slug}",
                normalized_data={"term": term, "slug": slug, "kind": kind},
            )
