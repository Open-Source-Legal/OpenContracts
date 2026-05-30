"""Tests for the offline geocoding utility — issue #1819.

Covers the four lookup branches (exact / alias / fuzzy / no-match) for
each label type and the disambiguation contract for hinted lookups
(``Paris`` + ``state_hint="TX"`` vs unhinted ``Paris``).

The dataset bundled at ``opencontractserver/utils/geocoding/data/`` is the
fixture — tests assert against rows that exist in that bundle. When the
dataset is refreshed (see ``docs/credits/geonames.md``) these tests serve
as smoke tests for the regeneration recipe.
"""

from __future__ import annotations

from django.test import SimpleTestCase

from opencontractserver.utils.geocoding import ResolvedPlace, resolve_place
from opencontractserver.utils.geocoding.service import LabelTypeLiteral


def _must_resolve(
    text: str,
    label_type: LabelTypeLiteral,
    **kwargs: str | None,
) -> ResolvedPlace:
    """Assert a hit and return it.

    ``resolve_place`` returns ``Optional[ResolvedPlace]``. Tests below
    that expect a hit need a narrowed value for mypy to see attribute
    access — ``self.assertIsNotNone`` doesn't propagate the narrowing.
    The bare ``assert`` here is the conventional pattern; the message
    points at the bundled dataset so a future row removal that breaks
    a test is self-explanatory.
    """
    result = resolve_place(text, label_type, **kwargs)
    assert result is not None, (
        f"resolve_place({text!r}, {label_type!r}, **{kwargs!r}) returned None — "
        "the bundled reference dataset may have lost the expected row."
    )
    return result


class ResolvePlaceCountryTests(SimpleTestCase):
    """Country lookups — exact, alias, fuzzy, miss."""

    def test_exact_name(self):
        # Sanity: hit returns the canonical name, never the user's casing.
        result = _must_resolve("France", "country")
        self.assertEqual(result.canonical_name, "France")
        self.assertEqual(result.label_type, "country")
        self.assertEqual(result.admin_codes["iso_alpha2"], "FR")
        # The dataclass is frozen — guard against accidental mutation.
        self.assertIsInstance(result, ResolvedPlace)

    def test_alpha2_alias(self):
        # Alpha-2 codes routinely appear in text; they must hit the alias path.
        result = _must_resolve("FR", "country")
        self.assertEqual(result.canonical_name, "France")

    def test_alpha3_alias(self):
        result = _must_resolve("USA", "country")
        self.assertEqual(result.canonical_name, "United States")
        self.assertEqual(result.admin_codes["iso_alpha2"], "US")

    def test_dotted_alias(self):
        # ``U.S.`` is an explicit alias entry; without it the dotted form
        # wouldn't normalise to ``US`` (we don't strip punctuation).
        result = _must_resolve("U.S.", "country")
        self.assertEqual(result.canonical_name, "United States")

    def test_case_insensitive(self):
        # Lookups must be case-insensitive — the index lowercases keys.
        for variant in ("france", "FRANCE", "FrAnCe"):
            with self.subTest(variant=variant):
                self.assertEqual(
                    _must_resolve(variant, "country").canonical_name, "France"
                )

    def test_fuzzy_match_typo(self):
        # ``Frace`` — one missing letter, the simple typo class the fuzzy
        # branch is meant to forgive. ``difflib.SequenceMatcher.ratio()``
        # handles substitutions/insertions/deletions well; transpositions
        # (e.g. ``Frnace``) sit below the threshold and are deliberately
        # NOT matched — keeping false-positive rate manageable matters more
        # than catching every typo. If the spec's ``rapidfuzz`` is later
        # wired in, transpositions would clear the bar.
        result = _must_resolve("Frace", "country")
        self.assertEqual(result.canonical_name, "France")

    def test_no_match_returns_none(self):
        # Pure garbage should NOT cross the fuzzy threshold.
        self.assertIsNone(resolve_place("Zzqqxxnnopq", "country"))

    def test_empty_string_returns_none(self):
        # Defensive: empty / None inputs must not crash the resolver.
        self.assertIsNone(resolve_place("", "country"))


class ResolvePlaceStateTests(SimpleTestCase):
    """US state lookups."""

    def test_exact_name(self):
        result = _must_resolve("Texas", "state")
        self.assertEqual(result.canonical_name, "Texas")
        self.assertEqual(result.admin_codes["admin1"], "TX")
        self.assertEqual(result.admin_codes["iso_alpha2"], "US")

    def test_usps_code_alias(self):
        # Two-letter USPS codes are the most common abbreviation in text.
        result = _must_resolve("TX", "state")
        self.assertEqual(result.canonical_name, "Texas")

    def test_dotted_alias(self):
        # ``N.Y.`` / ``N.Y`` is the historical AP-style abbreviation.
        result = _must_resolve("N.Y.", "state")
        self.assertEqual(result.canonical_name, "New York")

    def test_dc(self):
        # DC has multiple alias forms — confirm at least one resolves.
        for variant in ("DC", "D.C.", "District of Columbia", "Washington DC"):
            with self.subTest(variant=variant):
                self.assertEqual(
                    _must_resolve(variant, "state").canonical_name,
                    "District of Columbia",
                )

    def test_no_match_returns_none(self):
        self.assertIsNone(resolve_place("Zzzqqq", "state"))

    def test_non_us_country_hint_falls_back_to_unfiltered(self):
        # Bundled state data is US-only. A non-US ``country_hint``
        # narrows the candidate pool to zero — per the documented hint
        # fallback semantics, the resolver should fall back to the
        # unfiltered pool rather than returning None, so the user's
        # text isn't lost to a best-effort hint that didn't apply.
        result = _must_resolve("Texas", "state", country_hint="France")
        self.assertEqual(result.canonical_name, "Texas")
        self.assertEqual(result.admin_codes["admin1"], "TX")


class ResolvePlaceCityTests(SimpleTestCase):
    """City lookups — covers disambiguation via hints."""

    def test_exact_name_unique(self):
        result = _must_resolve("Tokyo", "city")
        self.assertEqual(result.canonical_name, "Tokyo")
        self.assertEqual(result.admin_codes["iso_alpha2"], "JP")

    def test_alias_match(self):
        # GeoNames historical alias — should fall through to alias map.
        result = _must_resolve("Bombay", "city")
        self.assertEqual(result.canonical_name, "Mumbai")

    def test_ambiguous_picks_largest_by_population(self):
        # Multiple "Paris" rows exist (FR + US-TX/TN/KY). Without hints the
        # population tie-break must return Paris, FR (~2.1M > all US Paris
        # rows under 100k).
        result = _must_resolve("Paris", "city")
        self.assertEqual(result.canonical_name, "Paris")
        self.assertEqual(result.admin_codes["iso_alpha2"], "FR")

    def test_state_hint_narrows_ambiguous(self):
        # The hint must override population — ``Paris, TX`` wins despite
        # being two orders of magnitude smaller.
        result = _must_resolve("Paris", "city", country_hint="US", state_hint="TX")
        self.assertEqual(result.canonical_name, "Paris")
        self.assertEqual(result.admin_codes["iso_alpha2"], "US")
        self.assertEqual(result.admin_codes["admin1"], "TX")

    def test_country_hint_narrows_ambiguous(self):
        # Country hint alone (no state) — must prefer the matching country.
        # Multiple "London" rows exist (GB + CA).
        result = _must_resolve("London", "city", country_hint="Canada")
        self.assertEqual(result.canonical_name, "London")
        self.assertEqual(result.admin_codes["iso_alpha2"], "CA")

    def test_state_hint_picks_correct_springfield(self):
        # Springfield exists in multiple US states; the state hint must
        # disambiguate to the right one. Springfield, MA is the largest
        # of the three bundled rows so it wins ties without the hint.
        result_il = _must_resolve(
            "Springfield", "city", country_hint="US", state_hint="IL"
        )
        result_mo = _must_resolve(
            "Springfield", "city", country_hint="US", state_hint="MO"
        )
        self.assertEqual(result_il.admin_codes["admin1"], "IL")
        self.assertEqual(result_mo.admin_codes["admin1"], "MO")

    def test_hint_via_country_name_form(self):
        # ``country_hint="France"`` must resolve through the country index
        # before filtering — same as passing ``"FR"`` directly.
        result = _must_resolve("Paris", "city", country_hint="France")
        self.assertEqual(result.admin_codes["iso_alpha2"], "FR")

    def test_fuzzy_city(self):
        # ``Pariss`` → Paris via difflib ratio.
        result = _must_resolve("Pariss", "city")
        self.assertEqual(result.canonical_name, "Paris")

    def test_no_match_returns_none(self):
        self.assertIsNone(resolve_place("Qqqzzzxxxnnnoppp", "city"))

    def test_unknown_hint_falls_back_gracefully(self):
        # An unrecognised country_hint must not zero the candidate pool —
        # the resolver should still try unfiltered lookup so a typo doesn't
        # hide the answer entirely.
        result = _must_resolve("Tokyo", "city", country_hint="Zzzzqqq")
        self.assertEqual(result.canonical_name, "Tokyo")
