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


# "Section 145", "Section 4(a)(2)", "Section 7(a)(2)(B)" followed by authority.
# The authority alternation is compiled per extractor instance from an alias
# registry (static defaults + DB-declared aliases on authority corpora), so
# adding a body of law never requires a code change. Aliases are matched
# longest-first so "Securities Exchange Act" wins over "Exchange Act".
def _compile_law_re(aliases) -> re.Pattern:
    alt = "|".join(re.escape(a) for a in sorted(aliases, key=len, reverse=True))
    return re.compile(
        r"Section\s+(?P<sec>\d+[A-Za-z]?(?:\([0-9a-zA-Z]+\))*)\s+of\s+the\s+"
        r"(?P<auth>" + alt + r")",
        re.IGNORECASE,
    )


def _compile_prefix_law_re(aliases) -> re.Pattern:
    """Form-style citations with the authority BEFORE the section:
    "Securities Act Section 4(a)(5)", "Investment Company Act Section 3(c)"."""
    alt = "|".join(re.escape(a) for a in sorted(aliases, key=len, reverse=True))
    return re.compile(
        r"(?P<auth>" + alt + r")\s+Section\s+"
        r"(?P<sec>\d+[A-Za-z]?(?:\([0-9a-zA-Z]+\))*)",
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
# Defined-term DEFINITION sites — high precision only:
#   1. parenthetical:  (the "Company")  ("Notes")  (collectively, the "Shares")
#   2. copular:        "Change of Control" means | shall mean | refers to
_TERM_PAREN_RE = re.compile(
    r"\((?:the\s+|collectively,?\s+the\s+|each\s+an?\s+|together(?:,)?\s+the\s+)?"
    r"[\"“](?P<term>[A-Z][^\"”]{1,60}?)[\"”]",
)
_TERM_MEANS_RE = re.compile(
    r"[\"“](?P<term>[A-Z][^\"”]{1,60}?)[\"”]\s+"
    r"(?:means\b|shall\s+mean\b|refers\s+to\b|has\s+the\s+meaning\b)",
)
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

    def extract(
        self,
        text: str,
        default_authority: str | None = None,
        reference_types: set[str] | tuple[str, ...] | list[str] | None = None,
    ) -> list[Candidate]:
        wanted = set(reference_types) if reference_types is not None else None
        out: list[Candidate] = []
        if wanted is None or C.REF_LAW in wanted:
            out.extend(self._laws(text))
            out.extend(self._prefix_laws(text))
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

        Opt-in (not in the default reference-type set) and capped at
        ``MAX_DEFINED_TERMS`` to keep precision/volume in check. The cap is a
        TOTAL per document across both grammar forms: matches are merged in
        document order before capping, so a document heavy in parenthetical
        definitions cannot starve the "means" form — the first N definition
        sites win regardless of form. Each definition becomes a
        cross-corpus-trackable stub keyed ``term:<slug>`` — the same
        philosophy as law citations.
        """
        seen: set[str] = set()
        emitted = 0
        for examined, m in enumerate(_TERM_RE.finditer(text), start=1):
            if examined > C.MAX_DEFINED_TERMS or emitted >= C.MAX_DEFINED_TERMS:
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
