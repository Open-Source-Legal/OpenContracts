"""Tier-2a: generic citation-SHAPE grammars (open-vocabulary detection).

These recognise citation *form* without knowing the body of law, so they catch
authorities outside the registry (state codes, CFR titles, obscure agencies).
Lower precedence than the Tier-1 registry extractor — see reconcile.py. No DB
access; pure functions over text returning Candidate spans (the extractor may
be handed the caller's already-loaded document list, consulted only for its
titles — see ``GenericCitationExtractor``).

Two customs/trade families ship here alongside the statutory shapes:

* HTS tariff codes ("subheading 3924.90.5650, HTSUS") — REF_LAW citations into
  the Harmonized Tariff Schedule (``htsus:<code>``), gated on a document-level
  HTSUS cue so ordinary corpora's dotted decimals are never mined.
* Title-identifier document citations (CBP CROSS ruling numbers) —
  REF_DOCUMENT citations resolved against sibling document titles, gated on
  the corpus's titles actually being identifier-shaped.
"""

from __future__ import annotations

import re
from collections.abc import Iterator

from opencontractserver.enrichment import constants as C
from opencontractserver.enrichment.abbreviations import (
    MUNICIPAL_CODE_ABBREVIATIONS,
    STATE_CODE_ABBREVIATIONS,
)
from opencontractserver.enrichment.extractor import Candidate, normalize_reference_types

# Confidence by grammar family — structured numeric cites are high precision;
# bare-Act detection (Task 11) is intentionally lower.
_CONF_STRUCTURED = 0.9
_CONF_BARE_ACT = 0.55
# Municipal (issue #1995) — calibrated BELOW structured federal cites. A
# table-keyed municipal code (known city + full jurisdiction) is more trusted
# than the open-vocabulary ``Municipal Code § N`` shape (city/jurisdiction
# uncertain), but neither outranks a numeric federal cite.
_CONF_MUNICIPAL = 0.8
_CONF_MUNICIPAL_GENERIC = 0.6
# HTS tariff codes — an ANCHORED code (a tariff cue word adjacent to the
# mention: "subheading 3924.90.5650, HTSUS") is as trusted as any structured
# federal cite; a CONTEXTUAL code (dotted-code shape alone, in a document that
# elsewhere names the HTSUS) is honest about the residual risk of matching an
# unrelated dotted decimal and sits below the trusted tier, like the
# open-vocab municipal shape.
_CONF_HTS_ANCHORED = 0.9
_CONF_HTS_CONTEXTUAL = 0.7

# A section token: digits, optional trailing letter, dotted hierarchy,
# optional hyphenated rule tail, then optional (a)(2) subsections. Known-code
# abbreviations are already the precision anchor, so retaining multiple dotted
# levels is both safe and necessary for tariff/guide sections such as 6.1.2.
_SEC = r"\d+[A-Za-z]?(?:\.\d+){0,5}(?:[-–]\d+)?(?:\([0-9a-zA-Z]+\))*"

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

# --- Texas electric / ERCOT authority shapes ------------------------------ #
# These identifiers are structurally precise and recur across multiple grid
# authority packs. They belong in the shared Tier-2 grammar rather than in one
# pack's provider parser; pack mappings still own aliases/classification.
_PUCT_TAC_RE = re.compile(
    r"\b16\s+(?:T\.?A\.?C\.?|Tex(?:as)?\.?\s+Admin(?:istrative)?\.?\s+Code)"
    r"\s+(?:§+\s*)?(?P<section>25\.\d+(?:\([0-9A-Za-z]+\))*)",
    re.IGNORECASE,
)
_ERCOT_REVISION_RE = re.compile(
    r"\b(?P<family>PGRR|NPRR)\s*(?:No\.?\s*)?(?P<number>\d{2,4})\b",
    re.IGNORECASE,
)
_ERCOT_GUIDE_RE = re.compile(
    r"\b(?:ERCOT\s+)?(?P<guide>Planning\s+Guide|Protocols?|Operating\s+Guide)"
    r"\s+(?:"
    r"(?:§+\s*|[Ss]ection\s+)"
    r"(?P<section_marked>\d+(?:\.\d+){0,5}(?:\([0-9A-Za-z]+\))*)"
    r"|(?P<section_bare>\d+(?:\.\d+){1,5}(?:\([0-9A-Za-z]+\))*)"
    r")",
    re.IGNORECASE,
)
_ERCOT_MARKET_NOTICE_RE = re.compile(
    r"(?<![A-Za-z0-9])(?P<notice>[A-Z]-[A-Z]\d{6}-\d+)(?![A-Za-z0-9])",
    re.IGNORECASE,
)

# Bare Act: "the Clean Water Act", "the Bank Holding Company Act of 1956".
# Require >=1 capitalized word before "Act" so bare "the Act" never matches.
_BARE_ACT_RE = re.compile(
    r"\bthe\s+(?P<name>(?:[A-Z][A-Za-z'&.\-]+\s+){1,6}Act)"
    r"(?:\s+of\s+(?P<year>\d{4}))?"
)

# --- Municipal grammars (issue #1995) ------------------------------------- #
# Municipal section locator: dotted/hyphenated multi-segment numbers
# ("6.02.010", "27-2004", "12.21"), optional (a)(2) subsections. Distinct from
# _SEC because municipal codes nest deeper than a single ".N".
_MUNI_SEC = r"\d+(?:[.\-–]\d+)*(?:\([0-9a-zA-Z]+\))*"

# Section anchor REQUIRED by the open-vocab municipal grammar — the strongest
# false-positive guard: without a §/Section/Sec. + number, prose like "the city
# adopted a new Municipal Code last year" can never match.
_MUNI_CONN = r"(?:§+\s*|[Ss]ection\s+|[Ss]ec\.\s*)"

# Open-vocabulary municipal-code citation: an optional capitalised city/place
# qualifier (up to 3 words, immediately preceding the code phrase) + a municipal
# code phrase + the required section anchor. Only the UNAMBIGUOUSLY-municipal
# code phrases are accepted ("Administrative Code" is deliberately absent —
# "Texas Administrative Code" is a STATE regulation; named municipal admin codes
# such as NYC's live in MUNICIPAL_CODE_ABBREVIATIONS instead). The leading
# capital in "Municipal Code"/"Mun. Code"/"Code of Ordinances" excludes
# lowercase prose ("the city's municipal code").
_MUNI_GENERIC_RE = re.compile(
    r"(?P<city>(?:[A-Z][A-Za-z.'&-]*\s+){0,3})"
    r"(?P<code>Municipal\s+Code|Mun\.\s*Code|Code\s+of\s+Ordinances)\s+"
    + _MUNI_CONN
    + r"(?P<sec>"
    + _MUNI_SEC
    + r")"
)

# Ordinance form: "[City] Ordinance No. 2021-15", "Ord. No 126000". A "No"/"No."
# token + number is required (the trailing dot is optional, so "No 7" matches too)
# so a bare "Ordinance" never matches.
_MUNI_ORDINANCE_RE = re.compile(
    r"(?P<city>(?:[A-Z][A-Za-z.'&-]*\s+){0,3})"
    r"(?:Ordinance|Ord\.)\s+No\.?\s*(?P<num>\d+(?:[.\-–]\d+)*)"
)

# --- Customs / trade grammars (CBP CROSS-style corpora) -------------------- #
# HTS tariff-code shape, ported from crossfeed's crossfeed.parse.normalize (the
# CROSS-rulings acquisition project's deterministic, golden-tested extractor).
# Requires at least heading.subheading (XXXX.XX) so bare 4-digit numbers
# (years, quantities) are never mined.
_HTS_TEXT_RE = re.compile(r"\b\d{4}\.\d{2}(?:\.\d{2,4})?(?:\.\d{2})?\b")
# Document-level gate: the dotted-code shape alone is far too generic to run on
# every corpus ("1234.56" is also a dollar amount), so HTS candidates are only
# emitted from documents that name the schedule. Deliberately EXCLUDES the bare
# acronym "HTS" (which collides with e.g. "high-throughput screening") — real
# customs documents that abbreviate to "HTS" spell out "Harmonized Tariff
# Schedule" alongside it.
_HTS_DOC_CUE_RE = re.compile(r"\bHTSUS\b|Harmonized\s+Tariff\s+Schedule")
# Mention-level anchor: a tariff cue within _HTS_ANCHOR_WINDOW chars of the
# code upgrades it to _CONF_HTS_ANCHORED. Bare "HTS"/"heading" are safe HERE
# (the document already passed the strict cue gate above).
_HTS_ANCHOR_RE = re.compile(
    r"\bHTSUS?\b|Harmonized\s+Tariff\s+Schedule|[Ss]ub-?heading\b|[Hh]eading\b"
)
_HTS_ANCHOR_WINDOW = 48


def _normalize_hts(raw: str) -> str | None:
    """Canonicalize an HTS code to dotted ``XXXX.XX[.XX[.XX]]`` form, or None.

    Strips all non-digits, regroups as 4 + 2-digit groups. Accepts 4/6/8/10
    digit codes; anything else is rejected. (The text shape above never emits
    fewer than 6 digits; the 4-digit acceptance serves callers normalizing
    bare headings.)
    """
    digits = re.sub(r"\D", "", raw)
    if len(digits) not in (4, 6, 8, 10):
        return None
    groups = [digits[:4], *[digits[i : i + 2] for i in range(4, len(digits), 2)]]
    return ".".join(groups)


# Leading qualifiers stripped from a captured municipal city before slugging, so
# "the Seattle Municipal Code" keys under ``muni-seattle`` not ``muni-the-seattle``.
# "city"/"county" are stopwords too: a bare "City Municipal Code § 5" (template
# placeholder, no real city) collapses to the honest ``muni:`` key instead of
# inventing a ``muni-city`` authority. Only LEADING stopwords drop, so a trailing
# qualifier in a real name survives ("Kansas City" -> ``muni-kansas-city``,
# "Marin County" -> ``muni-marin-county``). The common "City of X" form never
# reaches here as "city": the lowercase "of" breaks the capitalised run, so regex
# backtracking starts the match at the real city ("City of Portland ..." captures
# "Portland", keying ``muni-portland``).
# "see"/"under" are common capitalised citation/sentence leads that would
# otherwise be absorbed into the slug ("See Oakland Municipal Code § 5" ->
# ``muni-see-oakland``). The list is deliberately MINIMAL: only leads that are
# unambiguous non-place-names qualify. Bluebook signals that collide with real
# jurisdictions are EXCLUDED — "contra" would corrupt "Contra Costa [County]"
# into ``muni-costa``, and "accord" collides with Accord, NY. The open-vocab
# capture stays heuristic/provisional (0.6) for the residual long tail.
_CITY_STOPWORDS = frozenset(
    {"the", "this", "said", "a", "an", "city", "county", "see", "under"}
)


def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")


def _city_slug(city: str) -> str:
    """Slug a captured city qualifier, dropping leading article stopwords."""
    parts = [p for p in _slugify(city).split("-") if p]
    while parts and parts[0] in _CITY_STOPWORDS:
        parts.pop(0)
    return "-".join(parts)


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


def _puct_texas_admin_code(text: str) -> Iterator[Candidate]:
    for match in _PUCT_TAC_RE.finditer(text):
        section = match.group("section").lower()
        yield _cand(
            match.start(),
            match.end(),
            match.group(0),
            f"tx-admin-puct:{section}",
            "us-tx",
            C.AUTHORITY_TYPE_REGULATION,
        )


def _ercot_authorities(text: str) -> Iterator[Candidate]:
    for match in _ERCOT_REVISION_RE.finditer(text):
        family = match.group("family").lower()
        yield _cand(
            match.start(),
            match.end(),
            match.group(0),
            f"ercot-{family}:{match.group('number')}",
            "us-tx-ercot",
            C.AUTHORITY_TYPE_ADMIN_RULE,
        )
    guide_prefixes = {
        "planning guide": "ercot-planning",
        "protocol": "ercot-protocol",
        "protocols": "ercot-protocol",
        "operating guide": "ercot-operating",
    }
    for match in _ERCOT_GUIDE_RE.finditer(text):
        prefix = guide_prefixes[match.group("guide").lower()]
        section = match.group("section_marked") or match.group("section_bare")
        assert section is not None  # one regex alternative always captures it
        yield _cand(
            match.start(),
            match.end(),
            match.group(0),
            f"{prefix}:{section.lower()}",
            "us-tx-ercot",
            C.AUTHORITY_TYPE_ADMIN_RULE,
        )
    for match in _ERCOT_MARKET_NOTICE_RE.finditer(text):
        yield _cand(
            match.start(),
            match.end(),
            match.group(0),
            f"ercot-notice:{match.group('notice').upper()}",
            "us-tx-ercot",
            C.AUTHORITY_TYPE_GUIDANCE,
        )


def _hts(text: str) -> Iterator[Candidate]:
    """HTS tariff-code citations -> ``htsus:<code>`` law candidates.

    References into the Harmonized Tariff Schedule of the United States — a
    REF_LAW citation like any other statute mention, so it inherits the whole
    downstream (CorpusReference rows, discover() inventory, governance-graph
    ghost nodes, and cross-corpus linking if an HTSUS authority corpus is ever
    bootstrapped). Document-gated on _HTS_DOC_CUE_RE; per-mention confidence
    reflects whether a tariff cue anchors the specific code.
    """
    if not _HTS_DOC_CUE_RE.search(text):
        return
    for m in _HTS_TEXT_RE.finditer(text):
        code = _normalize_hts(m.group())
        if code is None:
            continue
        window = text[
            max(0, m.start() - _HTS_ANCHOR_WINDOW) : m.end() + _HTS_ANCHOR_WINDOW
        ]
        conf = (
            _CONF_HTS_ANCHORED
            if _HTS_ANCHOR_RE.search(window)
            else _CONF_HTS_CONTEXTUAL
        )
        yield _cand(
            m.start(),
            m.end(),
            m.group(0),
            f"{C.HTSUS_PREFIX}:{code}",
            C.JURISDICTION_US_FEDERAL,
            C.AUTHORITY_TYPE_STATUTE,
            conf=conf,
            extra={"section": code},
        )


def _document_identifier_citations(text: str) -> Iterator[Candidate]:
    """Identifier document citations (e.g. CBP ruling numbers).

    Two grammars feed one resolver index, both normalized through
    ``constants.canonical_document_identifier``:

    * prefixed identifiers (``constants.DOC_IDENTIFIER_RE``, "H022844");
    * series-token legacy citations
      (``constants.LEGACY_DOC_IDENTIFIER_CITE_RE``, "HRL 087392") — the
      bulk of pre-2000 rulings have bare numeric identities the prefixed
      shape cannot see (on the real 10K official-export benchmark this
      grammar carries 9,377 of the corpus's 9,677 citation candidates).

    Callers must apply the corpus-shape gate (``GenericCitationExtractor``
    only invokes this when the corpus's document identities are
    predominantly identifier-shaped).
    """
    matched = [(m, m.group(1)) for m in C.DOC_IDENTIFIER_RE.finditer(text)] + [
        (m, m.group(1)) for m in C.LEGACY_DOC_IDENTIFIER_CITE_RE.finditer(text)
    ]
    matched.sort(key=lambda pair: pair[0].start())
    for m, raw_ident in matched:
        key = C.canonical_document_identifier(raw_ident)
        if key is None:
            continue
        yield Candidate(
            reference_type=C.REF_DOCUMENT,
            start=m.start(),
            end=m.end(),
            raw_text=m.group(0),
            normalized_data={
                C.KEY_DOCUMENT_IDENTIFIER: key,
                "tier": C.DETECTION_TIER_GRAMMAR,
            },
            detection_tier=C.DETECTION_TIER_GRAMMAR,
            detection_confidence=_CONF_STRUCTURED,
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
        slug = _slugify(name)
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
    """Run all Tier-2a shape grammars over text → list[Candidate].

    ``documents`` (optional) is the corpus's already-loaded document set — the
    same permission-scoped list the caller hands the resolver. A corpus whose
    document identities are predominantly identifier-shaped (CBP CROSS-style)
    activates the identifier document-citation grammar; every other corpus
    leaves it inert, so serial/order/patent numbers in unrelated corpora are
    never mined as document citations. ``identity_candidates`` (the resolver's
    ``document_identity_candidates`` output, keyed by document id) carries
    path/external_id-derived identities; without it the gate falls back to
    title-only derivation (never the DB).
    """

    def __init__(self, documents=None, *, identity_candidates=None) -> None:
        documents = list(documents or [])
        if identity_candidates is not None:
            considered = len(documents)
            matching = sum(1 for doc in documents if identity_candidates.get(doc.id))
        else:
            idents = [
                C.document_identifier_from_title(doc.title)
                for doc in documents
                if (doc.title or "").strip()
            ]
            considered = len(idents)
            matching = sum(
                1 for i in idents if C.canonical_document_identifier(i) is not None
            )
        # Condition ORDER is load-bearing: the MIN_DOCS check short-circuits
        # the fraction check, and ``matching >= MIN_DOCS`` (with MIN_DOCS > 0)
        # guarantees ``considered`` is non-zero — reordering these would
        # reintroduce a ZeroDivisionError on an empty document set.
        self._doc_identifier_gate = (
            matching >= C.DOC_IDENTIFIER_TITLE_GATE_MIN_DOCS
            and matching / considered >= C.DOC_IDENTIFIER_TITLE_GATE_FRACTION
        )
        # Merge pack-declared abbreviations onto the Python baseline so a pack can
        # carry its jurisdiction's citation vocabulary in its own directory
        # (portable with the pack). The shipped baseline WINS a key collision — a
        # pack extends, it never overrides the engine's vocab. Lazy import: this
        # reaches the pipeline registry to enumerate packs, which would cycle
        # through the very-early enrichment.constants import if done at module top.
        from opencontractserver.enrichment.services.authority_pack_config import (
            pack_declared_abbreviations,
        )

        pack_state, pack_muni = pack_declared_abbreviations()
        # Baseline entries predate the pack precision flag, so normalize them
        # to the four-field runtime shape. The baseline still wins collisions.
        state_table = {
            **pack_state,
            **{
                abbreviation: (*entry, False)
                for abbreviation, entry in STATE_CODE_ABBREVIATIONS.items()
            },
        }
        muni_table = {
            **pack_muni,
            **{
                abbreviation: (*entry, False)
                for abbreviation, entry in MUNICIPAL_CODE_ABBREVIATIONS.items()
            },
        }

        # State-code alternation, longest-first so "Del. Code Ann. tit. 8" wins
        # over a hypothetical "Del. Code". Escaped spaces become ``\s+`` so OCR
        # double-spaces / line-break wraps still match; the captured text is
        # whitespace-normalized before lookup (``_state_canon``).
        self._state_canon = {
            re.sub(r"\s+", " ", abbreviation): entry[:3]
            for abbreviation, entry in state_table.items()
        }
        self._state_res = self._compile_abbreviation_patterns(
            state_table, section_pattern=_SEC
        )
        # Municipal-code table alternation — same construction as the state
        # table (longest-first, OCR-tolerant whitespace, normalized lookup).
        self._muni_canon = {
            re.sub(r"\s+", " ", abbreviation): entry[:3]
            for abbreviation, entry in muni_table.items()
        }
        self._muni_res = self._compile_abbreviation_patterns(
            muni_table, section_pattern=_MUNI_SEC
        )

    @staticmethod
    def _compile_abbreviation_patterns(
        table: dict[str, tuple],
        *,
        section_pattern: str,
    ) -> tuple[re.Pattern, ...]:
        """Compile optional- and required-marker abbreviation groups.

        Known baseline abbreviations retain their historical optional-``§``
        behavior. Pack entries can opt into the stricter connector without
        creating a separate grammar path.
        """

        patterns: list[re.Pattern] = []
        for marker_required in (False, True):
            ordered = sorted(
                (
                    abbreviation
                    for abbreviation, entry in table.items()
                    if bool(entry[3]) is marker_required
                ),
                key=len,
                reverse=True,
            )
            if not ordered:
                continue
            alternation = "|".join(
                re.escape(abbreviation).replace(r"\ ", r"\s+")
                for abbreviation in ordered
            )
            connector = (
                r"\s+(?:§+\s*|(?i:section|sec\.?)\s+)"
                if marker_required
                else r"\s+(?:§+\s*)?"
            )
            patterns.append(
                re.compile(
                    r"(?P<abbr>"
                    + alternation
                    + r")"
                    + connector
                    + r"(?P<sec>"
                    + section_pattern
                    + r")"
                )
            )
        return tuple(patterns)

    def extract(
        self,
        text: str,
        reference_types: set[str] | tuple[str, ...] | list[str] | None = None,
    ) -> list[Candidate]:
        # Each grammar pass emits a single reference_type, so passes whose type
        # the caller does not want are skipped outright — the output would be
        # filtered out downstream anyway.
        wanted = normalize_reference_types(reference_types)
        out: list[Candidate] = []
        if wanted is None or C.REF_LAW in wanted:
            out.extend(_usc(text))
            out.extend(_cfr(text))
            out.extend(_fedreg(text))
            out.extend(_publ(text))
            out.extend(_stat(text))
            out.extend(_puct_texas_admin_code(text))
            out.extend(_ercot_authorities(text))
            out.extend(_hts(text))
            out.extend(_bare_acts(text))
            out.extend(self._states(text))
            # Municipal: table pass first (high-precision, full jurisdiction),
            # then the open-vocab shape pass — which skips any span the table
            # already claimed so a known code never double-emits its shadow.
            muni = list(self._municipal(text))
            out.extend(muni)
            out.extend(self._municipal_generic(text, [(c.start, c.end) for c in muni]))
        if (wanted is None or C.REF_DOCUMENT in wanted) and self._doc_identifier_gate:
            out.extend(_document_identifier_citations(text))
        return out

    def _states(self, text: str) -> Iterator[Candidate]:
        matches = [
            match for pattern in self._state_res for match in pattern.finditer(text)
        ]
        for m in sorted(matches, key=lambda match: (match.start(), -match.end())):
            abbr = re.sub(r"\s+", " ", m.group("abbr"))
            prefix, jur, typ = self._state_canon[abbr]
            key = f"{prefix}:{m.group('sec').lower()}"
            yield _cand(m.start(), m.end(), m.group(0), key, jur, typ)

    def _municipal(self, text: str) -> Iterator[Candidate]:
        """Known municipal codes (table) → full jurisdiction, high confidence."""
        matches = [
            match for pattern in self._muni_res for match in pattern.finditer(text)
        ]
        for m in sorted(matches, key=lambda match: (match.start(), -match.end())):
            abbr = re.sub(r"\s+", " ", m.group("abbr"))
            prefix, jur, typ = self._muni_canon[abbr]
            key = f"{prefix}:{m.group('sec').lower()}"
            yield _cand(
                m.start(), m.end(), m.group(0), key, jur, typ, conf=_CONF_MUNICIPAL
            )

    def _municipal_generic(
        self, text: str, claimed: list[tuple[int, int]]
    ) -> Iterator[Candidate]:
        """Open-vocabulary municipal citations (shape + ordinance forms).

        Jurisdiction is left ``None``: a captured city ("Oakland") does not
        reveal its state ("us-ca"), so the engine refuses to guess one (unlike a
        table-keyed code, which carries the full ``us-ca-san-francisco``). The
        city slug is preserved in the ``muni-<city>`` prefix — the SAME prefix a
        table entry uses — so adding that city to MUNICIPAL_CODE_ABBREVIATIONS
        later seamlessly upgrades these mentions instead of orphaning them.
        ``authority_type`` is always ``municipal-ordinance``.

        The ordinance form keys ``<prefix>:ord-<num>`` (a locator, not a code
        section), so unlike the code-section form it is NOT table-upgradeable —
        the table maps code names, not ordinance numbers. It exists to surface
        the citation at low confidence, not to resolve to a known authority.

        Downstream note: every candidate from this open-vocab pass carries a
        ``detection_confidence`` below the table tier and (for non-table cities)
        ``jurisdiction=None``. Those two signals are the filter — consumers
        should treat such mentions as PROVISIONAL (surfaced for discovery/review,
        never promoted to the trusted tier) until corroborated, e.g. the city is
        tabled. This matters most for the anchorless ordinance form, where any
        capitalised lead word becomes a pseudo-city ("Employee Ordinance No. 7").
        """

        def _is_claimed(start: int, end: int) -> bool:
            # Overlap test (De Morgan of ``not (end <= cs or start >= ce)``):
            # the spans intersect iff this one starts before another ends AND
            # ends after it begins.
            return any(start < ce and end > cs for cs, ce in claimed)

        for m in _MUNI_GENERIC_RE.finditer(text):
            if _is_claimed(m.start(), m.end()):
                continue
            slug = _city_slug(m.group("city") or "")
            prefix = f"muni-{slug}" if slug else "muni"
            yield _cand(
                m.start(),
                m.end(),
                m.group(0),
                f"{prefix}:{m.group('sec').lower()}",
                None,
                C.AUTHORITY_TYPE_MUNICIPAL,
                conf=_CONF_MUNICIPAL_GENERIC,
            )
        for m in _MUNI_ORDINANCE_RE.finditer(text):
            if _is_claimed(m.start(), m.end()):
                continue
            slug = _city_slug(m.group("city") or "")
            prefix = f"muni-{slug}" if slug else "muni"
            yield _cand(
                m.start(),
                m.end(),
                m.group(0),
                f"{prefix}:ord-{m.group('num').lower()}",
                None,
                C.AUTHORITY_TYPE_MUNICIPAL,
                conf=_CONF_MUNICIPAL_GENERIC,
            )
