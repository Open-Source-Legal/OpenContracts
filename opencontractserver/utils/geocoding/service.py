"""Offline place resolution against the bundled reference dataset.

Lookup order — issue #1819:

1. Exact case-insensitive match on ``name``.
2. Case-insensitive match against any ``aliases`` row.
3. Fuzzy match via ``difflib.SequenceMatcher.ratio()`` ≥
   :data:`FUZZY_MATCH_THRESHOLD`. Ties broken by population (cities) /
   stable-sort fallback (countries, states). ``difflib`` ships with the
   stdlib so no new dependency is added; if the issue's suggested
   ``rapidfuzz`` is later wired in, the threshold/comparator can be swapped
   without changing call sites.

``country_hint`` / ``state_hint`` arguments narrow the candidate pool before
matching, so the location-tagging agent (planned follow-up) can disambiguate
"Paris" inside a document about France vs Texas.

Indexes are built lazily on first call and cached on the module so the JSON
load runs at most once per process.
"""

from __future__ import annotations

import difflib
import json
import logging
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)

# ``difflib.SequenceMatcher.ratio()`` returns ``0.0..1.0``; 0.85 is the
# floor for accepting a fuzzy match. Chosen empirically to keep "Paris" /
# "Pariss" working while rejecting unrelated tokens; the issue spec
# suggests ``rapidfuzz`` ≥ 90 (0.90) — difflib's ratio is slightly more
# permissive in practice on short strings, so a hair lower keeps parity.
FUZZY_MATCH_THRESHOLD = 0.85

LabelTypeLiteral = Literal["country", "state", "city"]

_DATA_DIR = Path(__file__).parent / "data"


@dataclass(frozen=True)
class ResolvedPlace:
    """Result of a successful place resolution.

    ``admin_codes`` always contains the ISO 3166-1 alpha-2 country code
    under ``"iso_alpha2"`` (the canonical key for downstream filters).
    State and city rows additionally populate ``"admin1"`` with the
    first-level admin division code (USPS code for US rows, GeoNames
    admin1 code elsewhere). ``label_type`` mirrors the value the caller
    passed in — it's redundant on the dataclass but useful when result
    rows from different label types are flattened into the same list.
    """

    canonical_name: str
    label_type: LabelTypeLiteral
    lat: float
    lng: float
    admin_codes: dict


# --------------------------------------------------------------------------- #
# Lazy-loaded indexes — built once per process.
#
# The reference JSON is small enough (countries: ~250 rows, states: ~55,
# cities: ~150 in the bundled seed) that building the dicts on first call is
# under a millisecond. A module-level lock around the load keeps the indexes
# coherent if two threads race the first call.
# --------------------------------------------------------------------------- #
_INDEX_LOCK = threading.Lock()
_INDEXES: dict[str, object] | None = None


def _normalise(text: str) -> str:
    """Lowercase + strip surrounding whitespace, the canonical lookup key.

    Aggressive normalisation (diacritics, punctuation removal) is
    intentionally avoided here — the dataset's ``aliases`` cover the
    common variants, and stripping diacritics would silently collapse
    distinct rows (e.g. "Müller" / "Muller"). When the caller wants a
    looser comparison the fuzzy branch handles it via ``ratio()``.
    """
    return text.strip().lower()


def _load_json(filename: str) -> dict:
    with (_DATA_DIR / filename).open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _build_indexes() -> dict:
    """Read the bundled JSON files and build the lookup indexes.

    The return shape is a single dict keyed by label type so the resolver
    can pick the relevant slice in one ``__getitem__``. Each slice holds:

    * ``"rows"``: the raw list (preserves population/ordering metadata
      needed for fuzzy tie-breaks).
    * ``"exact"``: ``{normalised_name → row}`` — first row wins on
      duplicate names (rare; intentionally not deduped against population
      because the disambiguation hint logic narrows the candidate pool
      before reaching the exact-match branch).
    * ``"alias"``: ``{normalised_alias → row}`` — same first-wins rule.
    """
    countries_doc = _load_json("countries.json")
    states_doc = _load_json("us_states.json")
    cities_doc = _load_json("cities.json")

    def build_slice(rows: list[dict], name_key: str, alias_key: str) -> dict:
        exact: dict[str, dict] = {}
        alias: dict[str, dict] = {}
        for row in rows:
            primary = _normalise(row[name_key])
            exact.setdefault(primary, row)
            for raw_alias in row.get(alias_key) or []:
                alias.setdefault(_normalise(raw_alias), row)
        return {"rows": rows, "exact": exact, "alias": alias}

    country_rows = countries_doc["countries"]
    # Countries get extra alias keys for alpha2 / alpha3 codes (these are
    # routinely used as the in-text form, e.g. "FR" or "USA"), so the alias
    # map carries those alongside the explicit ``aliases`` list.
    country_alias_map: dict[str, dict] = {}
    country_exact: dict[str, dict] = {}
    for row in country_rows:
        country_exact.setdefault(_normalise(row["name"]), row)
        for code_key in ("alpha2", "alpha3"):
            if row.get(code_key):
                country_alias_map.setdefault(_normalise(row[code_key]), row)
        for raw_alias in row.get("aliases") or []:
            country_alias_map.setdefault(_normalise(raw_alias), row)

    country_slice = {
        "rows": country_rows,
        "exact": country_exact,
        "alias": country_alias_map,
    }

    state_rows = states_doc["states"]
    # State alias map gets the USPS code (``code`` field) for free.
    state_alias_map: dict[str, dict] = {}
    state_exact: dict[str, dict] = {}
    for row in state_rows:
        state_exact.setdefault(_normalise(row["name"]), row)
        if row.get("code"):
            state_alias_map.setdefault(_normalise(row["code"]), row)
        for raw_alias in row.get("aliases") or []:
            state_alias_map.setdefault(_normalise(raw_alias), row)

    state_slice = {
        "rows": state_rows,
        "exact": state_exact,
        "alias": state_alias_map,
    }

    city_slice = build_slice(cities_doc["cities"], "name", "aliases")

    logger.debug(
        "Geocoding indexes built: %d countries, %d states, %d cities",
        len(country_rows),
        len(state_rows),
        len(cities_doc["cities"]),
    )

    return {"country": country_slice, "state": state_slice, "city": city_slice}


def _get_indexes() -> dict:
    """Return cached indexes, building them once under a lock.

    The lock is acquired only when ``_INDEXES`` is unset — the hot path
    after first call is a single ``is None`` check and a dict return.
    """
    global _INDEXES
    if _INDEXES is None:
        with _INDEX_LOCK:
            if _INDEXES is None:
                _INDEXES = _build_indexes()
    return _INDEXES


def _filter_candidates(
    rows: list[dict],
    *,
    label_type: LabelTypeLiteral,
    country_hint: str | None,
    state_hint: str | None,
) -> list[dict]:
    """Narrow ``rows`` to those matching the supplied hints.

    Hints are resolved via the existing index so callers can pass any
    form they recognise ("France" / "FR" / "FRA" / "Texas" / "TX").
    A hint that doesn't resolve to a known row is treated as "no hint"
    rather than zeroing out the candidate pool — the resolver still
    tries to match, and the caller gets the best fuzzy hit. The
    alternative (silently dropping everything) would mean a typo in
    the hint hid the answer entirely.
    """
    filtered = rows

    if country_hint is not None and label_type in ("state", "city"):
        country_row = _lookup_country(country_hint)
        if country_row is not None:
            alpha2 = country_row["alpha2"]
            if label_type == "state":
                # US states only — hint must be the US for the slice to apply.
                if alpha2 == "US":
                    pass  # rows are already US-only; nothing to do
                else:
                    # Non-US country hint: state lookup is meaningless
                    # for rows in this dataset. Return empty; ``resolve_place``
                    # treats this as "hint produced no candidates" and
                    # falls back to the unfiltered row set, so the
                    # mismatch surfaces as a best-effort match rather
                    # than failing the lookup outright.
                    return []
            else:
                filtered = [r for r in filtered if r.get("country_code") == alpha2]

    if state_hint is not None and label_type == "city":
        state_row = _lookup_state(state_hint)
        if state_row is not None:
            code = state_row["code"]
            filtered = [
                r
                for r in filtered
                if (r.get("admin1_code") or "").upper() == code.upper()
            ]

    return filtered


def _lookup_country(text: str) -> dict | None:
    """Resolve a country reference (used both as a hint and as the main path)."""
    slice_ = _get_indexes()["country"]
    key = _normalise(text)
    return slice_["exact"].get(key) or slice_["alias"].get(key)


def _lookup_state(text: str) -> dict | None:
    """Resolve a US state reference (used both as a hint and as the main path)."""
    slice_ = _get_indexes()["state"]
    key = _normalise(text)
    return slice_["exact"].get(key) or slice_["alias"].get(key)


def _row_to_resolved(row: dict, label_type: LabelTypeLiteral) -> ResolvedPlace:
    """Project a raw dataset row into the public ``ResolvedPlace`` shape.

    Keeps the public dataclass clean of dataset internals (population,
    raw aliases, etc.) — callers only ever see the canonical name +
    coordinates + admin codes.
    """
    if label_type == "country":
        admin_codes = {"iso_alpha2": row["alpha2"]}
        if row.get("alpha3"):
            admin_codes["iso_alpha3"] = row["alpha3"]
        return ResolvedPlace(
            canonical_name=row["name"],
            label_type=label_type,
            lat=float(row["lat"]),
            lng=float(row["lng"]),
            admin_codes=admin_codes,
        )
    if label_type == "state":
        # US states only — alpha2 of the parent country is always ``US`` for
        # the bundled dataset, but key the dict explicitly so a future
        # multi-country state dataset slots in cleanly.
        return ResolvedPlace(
            canonical_name=row["name"],
            label_type=label_type,
            lat=float(row["lat"]),
            lng=float(row["lng"]),
            admin_codes={"iso_alpha2": "US", "admin1": row["code"]},
        )
    # city
    admin_codes = {"iso_alpha2": row["country_code"]}
    if row.get("admin1_code"):
        admin_codes["admin1"] = row["admin1_code"]
    return ResolvedPlace(
        canonical_name=row["name"],
        label_type=label_type,
        lat=float(row["lat"]),
        lng=float(row["lng"]),
        admin_codes=admin_codes,
    )


def _population_score(row: dict) -> int:
    """Return ``row['population']`` as an int for tie-breaking.

    Missing / falsey population is treated as 0 so a row without
    population data loses every tie-break — the right behaviour for the
    "ambiguous tie → pick the well-known one" rule. Coerce to int because
    the dataset writes population as a number but a future CC-BY refresh
    could surface it as a string; defending here keeps the comparator
    total-ordered without crashing on type drift.
    """
    raw = row.get("population")
    if not raw:
        return 0
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 0


def _best_fuzzy(
    text: str, rows: list[dict], *, name_key: str, alias_key: str
) -> dict | None:
    """Return the highest-ratio row among ``rows`` for ``text``, or ``None``.

    Compares against both ``name`` and every entry in ``aliases``. Ties on
    ratio break by population (so "Paris" → Paris, FR over Paris, TX with
    no hint). Rows below :data:`FUZZY_MATCH_THRESHOLD` are skipped entirely.
    """
    target = _normalise(text)
    best_row: dict | None = None
    best_score: tuple[float, int] = (FUZZY_MATCH_THRESHOLD - 1e-9, -1)

    for row in rows:
        # Score against the row's canonical name and every alias; the row's
        # score is the max across all of them. Building one matcher per
        # comparison (rather than caching) is fine — these are short strings
        # and the dataset is small.
        candidates = [row[name_key]] + list(row.get(alias_key) or [])
        # Some rows (countries) carry alpha codes that should also match
        # fuzzily. Those are stored at top level rather than in ``aliases``,
        # so add them explicitly when present.
        for code_key in ("alpha2", "alpha3", "code"):
            if row.get(code_key):
                candidates.append(row[code_key])
        score = max(
            difflib.SequenceMatcher(None, target, _normalise(cand)).ratio()
            for cand in candidates
        )
        if score < FUZZY_MATCH_THRESHOLD:
            continue
        # Tie-break tuple: (ratio, population). Larger wins on both axes.
        candidate_key = (score, _population_score(row))
        if candidate_key > best_score:
            best_row = row
            best_score = candidate_key

    return best_row


def resolve_place(
    text: str,
    label_type: LabelTypeLiteral,
    *,
    country_hint: str | None = None,
    state_hint: str | None = None,
) -> ResolvedPlace | None:
    """Pure-Python, offline place resolution. Returns ``None`` on no-match.

    Args:
        text: The raw text from the annotation span (caller has already
            extracted the substring it wants to geocode).
        label_type: Which dataset to consult. Drives the candidate pool and
            the structure of ``ResolvedPlace.admin_codes``.
        country_hint: Optional disambiguation hint for ``label_type``
            ``"state"`` or ``"city"`` — only candidates whose country
            matches this hint are considered. Resolved through the same
            country index so any recognised form ("France" / "FR" / "FRA")
            works.
        state_hint: Optional disambiguation hint for ``label_type``
            ``"city"`` — only candidates whose first-level admin
            division matches this hint are considered. Resolved through
            the US state index (the only state slice bundled today).

    Returns:
        ``ResolvedPlace`` on hit, ``None`` when no row passes the exact
        / alias / fuzzy lookup chain.

    Notes:
        The resolver is deterministic: the same ``(text, label_type,
        hints)`` always produces the same answer, by design. Refreshing
        the bundled dataset is the only way to change a result; see
        ``docs/credits/geonames.md`` for the regeneration recipe.

        **Hint fallback semantics.** When ``country_hint`` / ``state_hint``
        narrow the candidate pool to zero rows (e.g. a typo'd hint, or a
        hint that points at a country slice this dataset doesn't carry —
        only US states are bundled today), the resolver falls back to
        the unfiltered candidate pool rather than returning ``None``.
        This keeps user experience graceful when a hint is best-effort.
        Callers that need hint-strict matching can verify the returned
        ``ResolvedPlace.admin_codes`` against the hint after the call.
    """
    if not text or not isinstance(text, str):
        return None
    if label_type not in ("country", "state", "city"):  # pragma: no cover
        raise ValueError(
            f"label_type must be 'country' / 'state' / 'city' (got {label_type!r})"
        )

    indexes = _get_indexes()
    slice_ = indexes[label_type]
    rows: list[dict] = list(slice_["rows"])  # copy so hint-filter mutates safe

    # Hint narrowing happens BEFORE exact / alias lookup so a hinted
    # ambiguous string (e.g. "Paris" + state_hint="TX") prefers the right
    # row even when both spellings are exact matches.
    filtered_rows = _filter_candidates(
        rows,
        label_type=label_type,
        country_hint=country_hint,
        state_hint=state_hint,
    )
    if not filtered_rows:
        # Hint reduced the candidate set to nothing — fall back to the
        # unfiltered rows so we don't fail just because the hint was
        # exotic. Callers who insist on hint-strict matching can verify
        # via ``ResolvedPlace.admin_codes`` after the call.
        filtered_rows = rows

    # ---- Exact name match ----------------------------------------------
    # The pre-built index covers ALL rows; when hints narrow the candidate
    # pool we must verify the indexed hit still passes the filter.
    #
    # The ``exact_row in filtered_rows`` membership check below (and the
    # ``alias_row in filtered_rows`` check in the alias branch) is O(n)
    # — Python's ``list.__contains__`` walks the list and calls
    # ``dict.__eq__`` per element. That's fine for the current dataset
    # sizes (< 200 cities, ~190 countries, ~55 states). If the bundled
    # dataset is ever expanded to GeoNames' full ``cities1000`` (~130k
    # rows), build an ``id(row)`` → ``True`` set from ``filtered_rows``
    # once and use that for membership instead.
    target_key = _normalise(text)
    exact_row = slice_["exact"].get(target_key)
    if exact_row is not None and exact_row in filtered_rows:
        return _row_to_resolved(exact_row, label_type)

    # Find best exact within the filtered subset (multiple "Paris" rows
    # etc.). Tie-break by population so the largest match wins — without
    # this the loop returns whichever row appears first in the source
    # dataset, which is a latent bug once cities.json is regenerated
    # from the full GeoNames ``cities1000`` dump.
    if filtered_rows is not rows:
        exact_matches = [
            row for row in filtered_rows if _normalise(row["name"]) == target_key
        ]
        if exact_matches:
            best_exact = max(exact_matches, key=_population_score)
            return _row_to_resolved(best_exact, label_type)

    # ---- Alias match ---------------------------------------------------
    alias_row = slice_["alias"].get(target_key)
    if alias_row is not None and alias_row in filtered_rows:
        return _row_to_resolved(alias_row, label_type)

    if filtered_rows is not rows:
        for row in filtered_rows:
            for code_key in ("alpha2", "alpha3", "code"):
                if row.get(code_key) and _normalise(row[code_key]) == target_key:
                    return _row_to_resolved(row, label_type)
            for raw_alias in row.get("aliases") or []:
                if _normalise(raw_alias) == target_key:
                    return _row_to_resolved(row, label_type)

    # ---- Fuzzy match ---------------------------------------------------
    name_key = "name"
    alias_key = "aliases"
    best = _best_fuzzy(text, filtered_rows, name_key=name_key, alias_key=alias_key)
    if best is not None:
        return _row_to_resolved(best, label_type)

    return None
