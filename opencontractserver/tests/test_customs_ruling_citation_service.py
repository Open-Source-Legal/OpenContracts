"""Unit tests for the deterministic HTS-code / ruling-citation regexes (no DB).

Regressed against crossfeed's own golden-tested extractor (the CROSS-rulings
acquisition project this service's regexes were ported from) — see
opencontractserver/enrichment/services/customs_ruling_citation_service.py's
module docstring for the reuse rationale.
"""

from django.test import SimpleTestCase

from opencontractserver.enrichment.services.customs_ruling_citation_service import (
    _HTS_TEXT_RE,
    _RULING_CITE_RE,
    _normalize_hts,
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
