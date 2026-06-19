"""Phase 3 auto-derivation: USLM <sourceCredit> harvest + popular-name import.

Both importers write source-scoped ``AuthorityKeyEquivalence`` rows (``uslm`` /
``popular_name``) and must never clobber a row owned by a different source
(baseline / manual / the other importer). Network is never touched — the USLM
test patches ``_load_title_xml`` with fixture bytes and the popular-name test
passes fixture HTML directly.
"""

import xml.etree.ElementTree as ET
from unittest.mock import patch

from django.test import TestCase

from opencontractserver.annotations.models import AuthorityKeyEquivalence
from opencontractserver.enrichment.services.popular_name_importer import (
    PopularNameTableImporter,
    parse_popular_name_table,
)
from opencontractserver.pipeline.authority_source_providers.us_code_provider import (
    USCodeAuthoritySourceProvider,
    parse_sourcecredit_keys,
)

# A minimal OLRC USLM title XML carrying one section whose <sourceCredit> cites a
# Public Law, a Statutes-at-Large page, and an Act (the Act ref is ignored).
_USLM_TITLE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<uscDoc xmlns="http://xml.house.gov/schemas/uslm/1.0">
  <main>
    <section identifier="/us/usc/t15/s78j">
      <num value="78j">§ 78j.</num>
      <heading>Manipulative and deceptive devices</heading>
      <sourceCredit>(<ref href="/us/act/1934-06-06/ch404/s10">June 6, 1934,
        ch. 404</ref>, <ref href="/us/stat/48/891">48 Stat. 891</ref>;
        <ref href="/us/pl/111/203/s929X">Pub. L. 111-203</ref>.)</sourceCredit>
      <subsection>
        <content>It shall be unlawful for any person ...</content>
      </subsection>
    </section>
  </main>
</uscDoc>
""".encode()


class ParseSourceCreditKeysTests(TestCase):
    def test_extracts_pl_and_stat_skips_act(self):
        root = ET.fromstring(_USLM_TITLE_XML)
        section = next(
            el for el in root.iter("{http://xml.house.gov/schemas/uslm/1.0}section")
        )
        assert parse_sourcecredit_keys(section) == ["publ:111-203", "stat:48.891"]

    def test_no_sourcecredit_returns_empty(self):
        section = ET.fromstring(
            '<section xmlns="http://xml.house.gov/schemas/uslm/1.0">'
            "<num>1</num></section>"
        )
        assert parse_sourcecredit_keys(section) == []


_LOAD_TITLE_XML = (
    "opencontractserver.pipeline.authority_source_providers"
    ".us_code_provider.USCodeAuthoritySourceProvider._load_title_xml"
)


class USLMHarvestTests(TestCase):
    def _fetch(self):
        provider = USCodeAuthoritySourceProvider()
        request = provider.locate("usc-15:78j")
        with patch(_LOAD_TITLE_XML, return_value=_USLM_TITLE_XML):
            return provider.fetch(request)

    def test_fetch_harvests_uslm_equivalences(self):
        sections = self._fetch()
        # The section text is still returned (harvest is a side-effect).
        assert sections and sections[0].key == "usc-15:78j"
        publ = AuthorityKeyEquivalence.objects.get(
            from_key="publ:111-203", to_key="usc-15:78j"
        )
        assert publ.source == "uslm"
        assert publ.confidence == 0.9
        assert AuthorityKeyEquivalence.objects.filter(
            from_key="stat:48.891", to_key="usc-15:78j", source="uslm"
        ).exists()

    def test_harvest_is_idempotent(self):
        self._fetch()
        self._fetch()
        assert (
            AuthorityKeyEquivalence.objects.filter(
                from_key="publ:111-203", to_key="usc-15:78j"
            ).count()
            == 1
        )

    def test_harvest_never_clobbers_manual(self):
        AuthorityKeyEquivalence.objects.create(
            from_key="stat:48.891",
            to_key="usc-15:78j",
            source="manual",
            note="curator",
        )
        self._fetch()
        row = AuthorityKeyEquivalence.objects.get(
            from_key="stat:48.891", to_key="usc-15:78j"
        )
        assert row.source == "manual"
        assert row.note == "curator"

    def test_malformed_sourcecredit_does_not_break_fetch(self):
        provider = USCodeAuthoritySourceProvider()
        request = provider.locate("usc-15:78j")
        with patch(_LOAD_TITLE_XML, return_value=_USLM_TITLE_XML), patch.object(
            provider,
            "_harvest_sourcecredit_equivalences",
            side_effect=RuntimeError("harvest exploded"),
        ):
            sections = provider.fetch(request)  # must still return the section
        assert sections and sections[0].key == "usc-15:78j"


# A faithful slice of the OLRC popular-names HTML (real attribute structure):
# one entry with a stat-bearing cite row, plus a row without a statviewer link
# (must be skipped) and an entry with no cite row at all.
_POPULAR_NAMES_HTML = """
<div id='SecuritiesExchangeActof1934' class='popular-name-table-entry' item='1'>
  <p class='popular-name'>Securities Exchange Act of 1934</p>
  <p class='popular-name-information' content-type='cite' datekey='1934-06-06'
     usckey='15:78a'>June 6,
     <a href="/statviewer.htm?volume=48&amp;page=881">48 Stat. 881</a>
     (<a href="/view.xhtml?req=granuleid:USC-prelim-title15-section78a">15 U.S.C. 78a</a>
     et seq.)</p>
  <p class='popular-name-information' content-type='short-title-ref' usckey='15:78a'>
     Short title, see
     <a href="/view.xhtml?req=granuleid:USC-prelim-title15-section78a">15 U.S.C. 78a</a></p>
</div>
<div id='CleanWaterAct' class='popular-name-table-entry' item='2'>
  <p class='popular-name'>Clean Water Act</p>
  <p class='popular-name-information' content-type='cite' usckey='33:1251'>Oct. 18,
     <a href="/statviewer.htm?volume=86&amp;page=816">86 Stat. 816</a>
     (<a href="/view.xhtml?req=granuleid:USC-prelim-title33-section1251">33 U.S.C. 1251</a>
     et seq.)</p>
</div>
<div id='NoCiteAct' class='popular-name-table-entry' item='3'>
  <p class='popular-name'>Act With No Cite Row</p>
</div>
"""


class ParsePopularNameTableTests(TestCase):
    def test_parses_stat_to_usc_bridges(self):
        bridges = parse_popular_name_table(_POPULAR_NAMES_HTML)
        pairs = {(b.stat_key, b.usc_key) for b in bridges}
        assert ("stat:48.881", "usc-15:78a") in pairs
        assert ("stat:86.816", "usc-33:1251") in pairs
        # The short-title-ref row has no statviewer link → not a bridge.
        assert len(bridges) == 2
        sec = next(b for b in bridges if b.usc_key == "usc-15:78a")
        assert sec.act_name == "Securities Exchange Act of 1934"

    def test_empty_html_is_noop(self):
        assert parse_popular_name_table("") == []


class PopularNameImporterTests(TestCase):
    def test_import_creates_popular_name_rows(self):
        summary = PopularNameTableImporter.import_table(html=_POPULAR_NAMES_HTML)
        assert summary["created"] == 2
        assert summary["parsed"] == 2
        row = AuthorityKeyEquivalence.objects.get(
            from_key="stat:48.881", to_key="usc-15:78a"
        )
        assert row.source == "popular_name"
        assert row.confidence == 0.85
        assert "Securities Exchange Act of 1934" in (row.note or "")

    def test_import_is_idempotent(self):
        PopularNameTableImporter.import_table(html=_POPULAR_NAMES_HTML)
        summary = PopularNameTableImporter.import_table(html=_POPULAR_NAMES_HTML)
        assert summary["created"] == 0
        assert summary["updated"] == 2

    def test_import_never_clobbers_baseline(self):
        AuthorityKeyEquivalence.objects.create(
            from_key="stat:48.881",
            to_key="usc-15:78a",
            source="baseline",
        )
        summary = PopularNameTableImporter.import_table(html=_POPULAR_NAMES_HTML)
        assert summary["skipped_owned"] == 1
        row = AuthorityKeyEquivalence.objects.get(
            from_key="stat:48.881", to_key="usc-15:78a"
        )
        assert row.source == "baseline"

    def test_command_imports_from_file(self):
        import tempfile
        from io import StringIO

        from django.core.management import call_command

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".htm", delete=False, encoding="utf-8"
        ) as fh:
            fh.write(_POPULAR_NAMES_HTML)
            path = fh.name

        out = StringIO()
        call_command("import_popular_name_table", "--file", path, stdout=out)
        assert "created=2" in out.getvalue()
        assert AuthorityKeyEquivalence.objects.filter(
            from_key="stat:86.816", to_key="usc-33:1251", source="popular_name"
        ).exists()
