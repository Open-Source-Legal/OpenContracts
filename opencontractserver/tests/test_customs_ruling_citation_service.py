"""Unit tests for the deterministic HTS-code / ruling-citation regexes (no DB).

Regressed against crossfeed's own golden-tested extractor (the CROSS-rulings
acquisition project this service's regexes were ported from) — see
opencontractserver/enrichment/services/customs_ruling_citation_service.py's
module docstring for the reuse rationale.
"""

from django.test import SimpleTestCase

from opencontractserver.enrichment.services.customs_ruling_citation_service import (
    _HTS_TEXT_RE,
    _LEGACY_RULING_CITE_RE,
    _RULING_CITE_RE,
    _canonical_ruling_key,
    _normalize_hts,
    _ruling_number_from_title,
)


class NormalizeHtsTests(SimpleTestCase):
    def test_four_digit_heading(self):
        assert _normalize_hts("7113.19") == "7113.19"

    def test_ten_digit_statistical(self):
        assert _normalize_hts("3924.90.5650") == "3924.90.56.50"

    def test_eight_digit_tariff(self):
        assert _normalize_hts("8703.23.01") == "8703.23.01"

    def test_rejects_five_digit(self):
        assert _normalize_hts("12345") is None

    def test_rejects_non_digit_garbage(self):
        assert _normalize_hts("abc") is None


class HtsTextExtractionTests(SimpleTestCase):
    def test_mines_dotted_code_from_prose(self):
        text = "The gold jewelry is classified under 7113.19, HTSUS."
        matches = [m.group() for m in _HTS_TEXT_RE.finditer(text)]
        assert "7113.19" in matches

    def test_does_not_mine_bare_four_digit_year(self):
        """A bare 4-digit number (e.g. a year) must never match — the regex
        requires a heading.subheading pair (a literal dot + 2 digits)."""
        text = "This ruling was issued in 2010 and revokes HQ 962035."
        matches = [m.group() for m in _HTS_TEXT_RE.finditer(text)]
        assert not any(m == "2010" for m in matches)


class RulingCitationTests(SimpleTestCase):
    def test_mines_modern_letter_prefixed_ruling(self):
        text = "We have reviewed our decision in HQ H022844 and found it consistent."
        matches = [m.group(1) for m in _RULING_CITE_RE.finditer(text)]
        assert "H022844" in matches

    def test_mines_legacy_two_letter_ruling(self):
        text = "revokes NY R03632, dated June 2, 2005"
        matches = [m.group(1) for m in _RULING_CITE_RE.finditer(text)]
        assert "R03632" in matches

    def test_does_not_mine_bare_six_digit_number(self):
        """Documented false-positive guard (ported from crossfeed): bare
        6-digit legacy numbers are never mined from prose — dollar amounts,
        statute numbers, and "STATE + 5-digit ZIP" collide with this shape."""
        text = "Headquarters Ruling Letter 562035, dated June 22, 2001."
        matches = [m.group(1) for m in _RULING_CITE_RE.finditer(text)]
        assert "562035" not in matches

    def test_does_not_mine_state_plus_zip(self):
        """A space-separated 'STATE ZIP' (e.g. 'NY 10022') must never match:
        both alternatives require the letters immediately adjacent to the
        digits, so a space between them is never mistaken for a ruling cite."""
        text = "Port Director, U.S. Customs, NY 10022."
        matches = [m.group(1) for m in _RULING_CITE_RE.finditer(text)]
        assert matches == []


class RulingNumberFromTitleTests(SimpleTestCase):
    """Regression coverage for the title/citation lookup-key mismatch: the
    citation regex only ever extracts the bare ruling number (no file
    extension in its character class), so a title index keyed on the raw
    title silently fails to resolve any citation whenever titles carry a
    file extension — which most of this corpus's real ingested titles do
    (materialized filenames like 'A83482.doc', not the bare stem)."""

    def test_strips_doc_extension(self):
        assert _ruling_number_from_title("A83482.doc") == "A83482"

    def test_strips_pdf_extension_case_insensitively(self):
        assert _ruling_number_from_title("H022844.PDF") == "H022844"

    def test_already_extension_free_is_unchanged(self):
        assert _ruling_number_from_title("A83482") == "A83482"

    def test_none_title_is_empty_string(self):
        assert _ruling_number_from_title(None) == ""


class LegacyRulingCitationTests(SimpleTestCase):
    """Series-token legacy citations ("HQ 084665", "HRL 087392").

    The official export's legacy HQ/NY slice (the bulk of pre-2000 rulings)
    has BARE numeric ruling numbers, so the prefixed grammar alone captures
    zero citations there — measured on a 500-document official-export
    sample: 707 token+number citation instances, no false positives.
    """

    def test_mines_series_token_citation(self):
        text = "Upon further consideration, HRL 087392 is deemed correct."
        matches = [m.group(1) for m in _LEGACY_RULING_CITE_RE.finditer(text)]
        assert matches == ["087392"]

    def test_mines_across_hard_line_wrap_and_columns(self):
        text = "October 27, 1987, has been modified by HRL\n081374 dated"
        matches = [m.group(1) for m in _LEGACY_RULING_CITE_RE.finditer(text)]
        assert matches == ["081374"]

    def test_never_mines_new_york_zip_codes(self):
        """5 digits after "NY" is a ZIP (148/149 sampled instances), and
        ZIP+4 never forms a 6-digit run — the grammar requires exactly 6."""
        text = "375 Fifth Avenue, New York, NY  10176 and NY 10001-3060."
        assert list(_LEGACY_RULING_CITE_RE.finditer(text)) == []

    def test_never_mines_bare_number_without_series_token(self):
        text = "Headquarters Ruling Letter 562035, dated June 22, 2001."
        assert list(_LEGACY_RULING_CITE_RE.finditer(text)) == []

    def test_canonical_key_namespaces(self):
        # Prefixed: verbatim, uppercased.
        assert _canonical_ruling_key("H022844") == "H022844"
        assert _canonical_ruling_key("r03632") == "R03632"
        # Bare legacy: leading zeros stripped so padded identity and cite agree.
        assert _canonical_ruling_key("084665") == "84665"
        assert _canonical_ruling_key("84665") == "84665"
        # Not ruling numbers at all.
        assert _canonical_ruling_key("Plastic trays") is None
        assert _canonical_ruling_key("1466") is None
        assert _canonical_ruling_key("") is None
