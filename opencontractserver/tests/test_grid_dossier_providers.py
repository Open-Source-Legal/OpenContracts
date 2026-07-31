"""Focused, network-free tests for the four grid-dossier provider packs."""

from __future__ import annotations

import io
import sys
import zipfile
from dataclasses import replace
from typing import Any, ClassVar
from unittest.mock import patch

from django.test import SimpleTestCase

from opencontractserver.enrichment.authority_sources import (
    AuthorityWeight,
    InstrumentType,
    RelationshipType,
    RightsStatus,
    SourceStatus,
)
from opencontractserver.pipeline.base.base_authority_discovery_provider import (
    DiscoveryCandidate,
)
from opencontractserver.pipeline.registry import (
    get_all_authority_discovery_providers_cached,
    get_all_authority_source_providers_cached,
    reset_registry,
)


class GridDossierProviderTests(SimpleTestCase):
    """Pack registry, pure listing parsers, and rich-record classification."""

    source_definitions: ClassVar[dict[str, Any]] = {}
    discovery_definitions: ClassVar[dict[str, Any]] = {}

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        reset_registry()
        cls.source_definitions = {
            definition.name: definition
            for definition in get_all_authority_source_providers_cached()
        }
        cls.discovery_definitions = {
            definition.name: definition
            for definition in get_all_authority_discovery_providers_cached()
        }

    @classmethod
    def tearDownClass(cls):
        reset_registry()
        super().tearDownClass()

    @classmethod
    def _source_class(cls, name: str):
        component_class = cls.source_definitions[name].component_class
        assert component_class is not None
        return component_class

    @classmethod
    def _source_module(cls, name: str):
        return sys.modules[cls._source_class(name).__module__]

    @classmethod
    def _discovery_class(cls, name: str):
        component_class = cls.discovery_definitions[name].component_class
        assert component_class is not None
        return component_class

    @classmethod
    def _discovery_module(cls, name: str):
        return sys.modules[cls._discovery_class(name).__module__]

    def test_all_grid_dossier_source_and_discovery_providers_register(self):
        self.assertTrue(
            {
                "TexasStatuteAuthoritySourceProvider",
                "TexasBillAuthoritySourceProvider",
                "PUCTRuleAuthoritySourceProvider",
                "PUCTInterchangeDocumentAuthoritySourceProvider",
                "ERCOTIssueAuthoritySourceProvider",
                "ERCOTMarketNoticeAuthoritySourceProvider",
                "ERCOTGuideAuthoritySourceProvider",
                "ERCOTFormAuthoritySourceProvider",
                "OncorTariffAuthoritySourceProvider",
                "OncorServiceDocumentAuthoritySourceProvider",
            }.issubset(self.source_definitions)
        )
        self.assertTrue(
            {
                "TexasCodeDiscoveryProvider",
                "TexasBillHistoryDiscoveryProvider",
                "PUCTRuleDiscoveryProvider",
                "PUCTProjectDiscoveryProvider",
                "ERCOTIssueIndexDiscoveryProvider",
                "ERCOTMarketNoticeDiscoveryProvider",
                "ERCOTGuideLibraryDiscoveryProvider",
                "ERCOTLargeLoadPageDiscoveryProvider",
                "OncorTariffIndexDiscoveryProvider",
                "OncorServiceDocumentDiscoveryProvider",
            }.issubset(self.discovery_definitions)
        )

    def test_texas_code_parser_uses_current_tcss_resource_urls(self):
        module = self._discovery_module("TexasCodeDiscoveryProvider")
        candidates = module.parse_texas_code_index(
            """
            <a href="/resources/UT/htm/UT.37.htm#37.056">
              Sec. 37.056 — Transmission service for large loads
            </a>
            """,
            index_url="https://tcss.legis.texas.gov/statutes",
        )
        self.assertEqual(
            [candidate.canonical_key for candidate in candidates], ["tx-util:37.056"]
        )
        self.assertEqual(
            candidates[0].url,
            "https://tcss.legis.texas.gov/resources/UT/htm/UT.37.htm",
        )

    def test_texas_bill_history_parser_supports_senate_and_house_bills(self):
        module = self._discovery_module("TexasBillHistoryDiscoveryProvider")
        candidates = module.parse_texas_bill_history(
            """
            <a href="/tlodocs/89R/billtext/html/SB00006E.htm">Engrossed S.B. 6</a>
            <a href="/tlodocs/89R/billtext/html/HB00005F.htm">Enrolled H.B. 5</a>
            """,
            index_url="https://capitol.texas.gov/BillLookup/History.aspx",
        )
        self.assertEqual(
            {candidate.canonical_key for candidate in candidates},
            {"tx-sb:89r-6:engrossed", "tx-hb:89r-5:enrolled"},
        )

    def test_texas_bill_history_keys_repeatable_staff_stages_by_publisher_id(self):
        module = self._discovery_module("TexasBillHistoryDiscoveryProvider")
        candidates = module.parse_texas_bill_history(
            """
            <a href="/tlodocs/89R/analysis/html/SB00006A.htm">
              Senate Research Center Bill Analysis
            </a>
            <a href="/tlodocs/89R/analysis/html/SB00006H.htm">
              House Research Organization Bill Analysis
            </a>
            """,
            index_url="https://capitol.texas.gov/BillLookup/Text.aspx",
        )

        self.assertEqual(
            {candidate.canonical_key for candidate in candidates},
            {
                "tx-sb:89r-6:analysis:sb00006a",
                "tx-sb:89r-6:analysis:sb00006h",
            },
        )
        self.assertEqual(
            {candidate.extra["source_identifier"] for candidate in candidates},
            {"SB00006A", "SB00006H"},
        )

    def test_texas_bill_history_collapses_publisher_representations_to_html(self):
        module = self._discovery_module("TexasBillHistoryDiscoveryProvider")
        candidates = module.parse_texas_bill_history(
            """
            <a href="/tlodocs/89R/analysis/pdf/SB00006H.pdf">
              House Committee Report Bill Analysis (PDF)
            </a>
            <a href="/tlodocs/89R/analysis/html/SB00006H.htm">
              House Committee Report Bill Analysis
            </a>
            <a href="/tlodocs/89R/analysis/doc/SB00006H.docx">
              House Committee Report Bill Analysis (Word)
            </a>
            """,
            index_url="https://capitol.texas.gov/BillLookup/Text.aspx",
        )

        self.assertEqual(len(candidates), 1)
        self.assertEqual(
            candidates[0].canonical_key,
            "tx-sb:89r-6:analysis:sb00006h",
        )
        self.assertTrue(candidates[0].url.endswith("/analysis/html/SB00006H.htm"))

    def test_texas_sb6_history_preserves_all_official_document_identities(self):
        module = self._discovery_module("TexasBillHistoryDiscoveryProvider")
        identities = (
            ("billtext/html/SB00006I.htm", "Introduced Bill Text"),
            ("fiscalnotes/html/SB00006I.htm", "Introduced Fiscal Note"),
            ("analysis/html/SB00006I.htm", "Introduced Bill Analysis"),
            ("billtext/html/SB00006S.htm", "Senate Committee Report Bill Text"),
            (
                "fiscalnotes/html/SB00006S.htm",
                "Senate Committee Report Fiscal Note",
            ),
            ("analysis/html/SB00006S.htm", "Senate Committee Report Bill Analysis"),
            (
                "witlistbill/html/SB00006S.htm",
                "Senate Committee Report Witness List",
            ),
            ("billtext/html/SB00006E.htm", "Engrossed Bill Text"),
            ("fiscalnotes/html/SB00006E.htm", "Engrossed Fiscal Note"),
            ("billtext/html/SB00006H.htm", "House Committee Report Bill Text"),
            (
                "fiscalnotes/html/SB00006H.htm",
                "House Committee Report Fiscal Note",
            ),
            ("analysis/html/SB00006H.htm", "House Committee Report Bill Analysis"),
            (
                "summcomm/html/SB00006.htm",
                "House Committee Report Summary of Committee Action",
            ),
            (
                "fiscalnotes/html/SB00006A.htm",
                "Senate Amendments Printing Fiscal Note",
            ),
            ("billtext/html/SB00006F.htm", "Enrolled Bill Text"),
            ("fiscalnotes/html/SB00006F.htm", "Enrolled Fiscal Note"),
            ("analysis/html/SB00006F.htm", "Enrolled Bill Analysis"),
            (
                "publiccomments/billhistory/SB00006H.pdf",
                "House Public Comments (PDF)",
            ),
        )
        candidates = module.parse_texas_bill_history(
            "".join(
                f'<a href="/tlodocs/89R/{path}" aria-label="{title}">{title}</a>'
                for path, title in identities
            ),
            index_url="https://capitol.texas.gov/BillLookup/Text.aspx",
        )
        by_key = {candidate.canonical_key: candidate for candidate in candidates}
        expected_keys = {
            "tx-sb:89r-6:introduced",
            "tx-sb:89r-6:fiscal-note:sb00006i",
            "tx-sb:89r-6:analysis:sb00006i",
            "tx-sb:89r-6:committee-report:sb00006s",
            "tx-sb:89r-6:fiscal-note:sb00006s",
            "tx-sb:89r-6:analysis:sb00006s",
            "tx-sb:89r-6:witness-list:sb00006s",
            "tx-sb:89r-6:engrossed",
            "tx-sb:89r-6:fiscal-note:sb00006e",
            "tx-sb:89r-6:committee-report:sb00006h",
            "tx-sb:89r-6:fiscal-note:sb00006h",
            "tx-sb:89r-6:analysis:sb00006h",
            "tx-sb:89r-6:committee-report:sb00006",
            "tx-sb:89r-6:fiscal-note:sb00006a",
            "tx-sb:89r-6:enrolled",
            "tx-sb:89r-6:fiscal-note:sb00006f",
            "tx-sb:89r-6:analysis:sb00006f",
            "tx-sb:89r-6:comment:sb00006h",
        }

        self.assertEqual(len(candidates), 18)
        self.assertEqual(set(by_key), expected_keys)
        self.assertEqual(
            by_key["tx-sb:89r-6:introduced"].url,
            "https://capitol.texas.gov/tlodocs/89R/billtext/html/SB00006I.htm",
        )
        self.assertEqual(
            by_key["tx-sb:89r-6:witness-list:sb00006s"].extra["stage"],
            "witness-list",
        )
        expected_billtext_metadata = {
            "tx-sb:89r-6:introduced": {
                "instrument_type": "STATUTE",
                "status": "PROPOSED",
            },
            "tx-sb:89r-6:comment:sb00006h": {
                "instrument_type": "COMMENT",
                "status": "PUBLISHED",
                "authority_weight": "ADVOCACY",
            },
            "tx-sb:89r-6:engrossed": {
                "instrument_type": "STATUTE",
                "status": "PROPOSED",
            },
            "tx-sb:89r-6:enrolled": {
                "instrument_type": "STATUTE",
                "status": "ENACTED",
            },
        }
        for key, expected_metadata in expected_billtext_metadata.items():
            self.assertEqual(by_key[key].extra["metadata"], expected_metadata)
        for key in expected_keys - expected_billtext_metadata.keys():
            self.assertEqual(
                by_key[key].extra["metadata"],
                {
                    "instrument_type": "STAFF_MEMO",
                    "status": "PUBLISHED",
                },
            )

    def test_puct_rule_and_attachment_parsers_preserve_document_identity(self):
        rule_module = self._discovery_module("PUCTRuleDiscoveryProvider")
        rules = rule_module.parse_puct_rule_index(
            '<a href="/agency/rulesnlaws/subrules/electric/25.109/">Rule 25.109</a>',
            index_url="https://www.puc.texas.gov/rules",
        )
        self.assertEqual(rules[0].canonical_key, "tx-admin-puct:25.109")

        project_module = self._discovery_module("PUCTProjectDiscoveryProvider")
        candidates = project_module.parse_puct_project_index(
            """
            <a href="/files/order.pdf?ControlNumber=58211&ItemNumber=4">
              Final Order
            </a>
            <a href="/files/typed-order.pdf?ControlNumber=58211&ItemNumber=6"
               data-document-type="Final Order"
               data-author-role="Commission">
              Final Order
            </a>
            <a href="/files/comments.pdf?ControlNumber=58211&ItemNumber=7">
              Comments on Final Order
            </a>
            <a href="/files/testimony-a.pdf?ControlNumber=58211&ItemNumber=5">
              Direct Testimony A
            </a>
            <a href="/files/testimony-b.pdf?ControlNumber=58211&ItemNumber=5">
              Direct Testimony B
            </a>
            <a href="/files/mislabeled-order.pdf?ControlNumber=58211&ItemNumber=8"
               data-document-type="Final Order"
               data-author-role="Applicant">
              Final Order
            </a>
            """,
            index_url=(
                "https://interchange.puc.texas.gov/search/filings/?ControlNumber=58211"
            ),
        )
        keys = [candidate.canonical_key for candidate in candidates]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertEqual(keys[0], "puct-project:58211:item:4:document:order")
        self.assertTrue(keys[1].startswith("puct-order:58211:"))
        self.assertEqual(keys[2], "puct-project:58211:item:7:document:comments")
        self.assertIn("puct-project:58211:item:5:document:testimony-a", keys)
        self.assertIn("puct-project:58211:item:5:document:testimony-b", keys)
        self.assertIn(
            "puct-project:58211:item:8:document:mislabeled-order",
            keys,
        )

    def test_puct_project_parser_enumerates_every_item_and_attachment(self):
        project_module = self._discovery_module("PUCTProjectDiscoveryProvider")
        listing_url = (
            "https://interchange.puc.texas.gov/search/filings/?ControlNumber=59142"
        )
        item_pages = project_module.parse_puct_project_item_pages(
            """
            <table>
              <tr>
                <td><a href="/search/documents/?controlNumber=59142&amp;itemNumber=2">2</a></td>
                <td>12/18/2025</td>
                <td>GOOGLE LLC, LANCIUM LLC</td>
                <td>COM</td>
                <td>Joint Comments on ERCOT Large Load Process Reforms</td>
              </tr>
              <tr>
                <td><a href="/search/documents/?controlNumber=59142&amp;itemNumber=1">1</a></td>
                <td>12/17/2025</td>
                <td>PUC EXECUTIVE DIRECTOR</td>
                <td>LTRS</td>
                <td>CONTROL NUMBER REQUEST</td>
              </tr>
            </table>
            """,
            index_url=listing_url,
        )
        self.assertEqual(
            [page["item_number"] for page in item_pages],
            ["1", "2"],
        )
        self.assertEqual(item_pages[0]["filing_party"], "PUC EXECUTIVE DIRECTOR")
        self.assertEqual(
            item_pages[1]["detail_url"],
            "https://interchange.puc.texas.gov/search/documents/"
            "?controlNumber=59142&itemNumber=2",
        )

        attachments = project_module.parse_puct_project_attachment_page(
            """
            <p><strong>File Stamp</strong> &nbsp; 12/17/2025</p>
            <p><strong>Filing Party</strong> &nbsp; PUC EXECUTIVE DIRECTOR</p>
            <p><strong>Filing Description</strong> &nbsp; CONTROL NUMBER REQUEST</p>
            <table>
              <tr>
                <td><a href="/Documents/59142_1_1567370.ZIP">59142_1_1567370</a></td>
                <td>ZIP</td>
              </tr>
              <tr>
                <td><a href="/Documents/59142_1_1567371.PDF">59142_1_1567371</a></td>
                <td>PDF</td>
              </tr>
            </table>
            """,
            detail_url=item_pages[0]["detail_url"],
            listing_metadata=item_pages[0],
        )
        self.assertEqual(len(attachments), 2)
        self.assertEqual(
            {candidate.canonical_key for candidate in attachments},
            {
                "puct-project:59142:item:1:document:1567370",
                "puct-project:59142:item:1:document:1567371",
            },
        )
        by_hint = {
            candidate.extra["attachment_mime_hint"]: candidate
            for candidate in attachments
        }
        self.assertEqual(set(by_hint), {"zip", "pdf"})
        self.assertEqual(
            by_hint["zip"].url,
            "https://interchange.puc.texas.gov/Documents/59142_1_1567370.ZIP",
        )
        self.assertEqual(
            by_hint["zip"].extra["pdf_rendition_url"],
            by_hint["pdf"].url,
        )
        self.assertEqual(
            by_hint["pdf"].extra["native_package_url"],
            by_hint["zip"].url,
        )
        for attachment in attachments:
            self.assertEqual(attachment.extra["parent_key"], "puct-project:59142")
            self.assertEqual(attachment.extra["filed_date"], "2025-12-17")
            self.assertTrue(attachment.extra["government_authored"])
            self.assertEqual(attachment.extra["publisher_author_role"], "agency")

    def test_puct_project_discovery_fetches_every_detail_with_pack_ca(self):
        module = self._discovery_module("PUCTProjectDiscoveryProvider")
        provider = self._discovery_class("PUCTProjectDiscoveryProvider")()
        listing_url = (
            "https://interchange.puc.texas.gov/search/filings/?ControlNumber=59142"
        )
        listing_html = """
            <table>
              <tr>
                <td><a href="/search/documents/?controlNumber=59142&amp;itemNumber=1">1</a></td>
                <td>12/17/2025</td><td>PUC EXECUTIVE DIRECTOR</td>
                <td>LTRS</td><td>CONTROL NUMBER REQUEST</td>
              </tr>
              <tr>
                <td><a href="/search/documents/?controlNumber=59142&amp;itemNumber=2">2</a></td>
                <td>12/18/2025</td><td>GOOGLE LLC</td>
                <td>COM</td><td>COMMENTS</td>
              </tr>
            </table>
        """

        def detail_html(item: int, first_id: int) -> str:
            return f"""
                <p><strong>File Stamp</strong> &nbsp; 12/{16 + item}/2025</p>
                <p><strong>Filing Party</strong> &nbsp; PUC EXECUTIVE DIRECTOR</p>
                <p><strong>Filing Description</strong> &nbsp; ITEM {item}</p>
                <a href="/Documents/59142_{item}_{first_id}.ZIP">native</a>
                <a href="/Documents/59142_{item}_{first_id + 1}.PDF">rendition</a>
            """

        ca_bundle = ("-----BEGIN CERTIFICATE-----\nfixture\n-----END CERTIFICATE-----",)
        with patch.object(
            module,
            "safe_fetch_text",
            side_effect=[
                (listing_html, "interchange.puc.texas.gov"),
                (detail_html(1, 1567370), "interchange.puc.texas.gov"),
                (detail_html(2, 1567372), "interchange.puc.texas.gov"),
            ],
        ) as safe_fetch:
            envelope, final_host = provider._fetch_index_impl(
                listing_url,
                max_detail_pages=10,
                extra_ca_certificates=ca_bundle,
            )

        self.assertEqual(final_host, "interchange.puc.texas.gov")
        candidates = provider._parse_index_impl(envelope, index_url=listing_url)
        self.assertEqual(len(candidates), 4)
        self.assertEqual(
            {candidate.extra["item_number"] for candidate in candidates},
            {"1", "2"},
        )
        self.assertEqual(
            len({candidate.canonical_key for candidate in candidates}),
            len(candidates),
        )
        self.assertEqual(
            len(safe_fetch.call_args_list),
            3,
            "listing plus every filing-detail page must be fetched",
        )
        for call in safe_fetch.call_args_list:
            self.assertEqual(
                call.kwargs["extra_ca_certificates"],
                ca_bundle,
            )

    def test_ercot_listing_parsers_emit_only_declared_prefixes(self):
        issue_module = self._discovery_module("ERCOTIssueIndexDiscoveryProvider")
        issues = issue_module.parse_ercot_issue_index(
            '<a href="/mktrules/issues/PGRR115">PGRR115</a>',
            index_url="https://www.ercot.com/mktrules/issues",
        )
        self.assertEqual(issues[0].canonical_key, "ercot-pgrr:115")

        notice_module = self._discovery_module("ERCOTMarketNoticeDiscoveryProvider")
        notices = notice_module.parse_ercot_market_notice_index(
            '<a href="/services/comm/mkt_notices/M-A010126-01">Notice</a>',
            index_url="https://www.ercot.com/services/comm/mkt_notices",
        )
        self.assertEqual(notices[0].canonical_key, "ercot-notice:M-A010126-01")

        guide_module = self._discovery_module("ERCOTGuideLibraryDiscoveryProvider")
        guides = guide_module.parse_ercot_guide_library(
            """
            <a href="/content/current-planning.pdf">
              Current Planning Guide Section 9
            </a>
            <a href="/content/current-operating.pdf">
              Current Nodal Operating Guide Section 2
            </a>
            """,
            index_url="https://www.ercot.com/mktrules/guides",
        )
        self.assertEqual(
            {candidate.canonical_key for candidate in guides},
            {"ercot-planning:9", "ercot-operating:2"},
        )

        load_module = self._discovery_module("ERCOTLargeLoadPageDiscoveryProvider")
        load_documents = load_module.parse_ercot_large_load_page(
            """
            <a href="/files/Large-Load-Information-Form-v2.pdf">
              Large Load Information Form v2
            </a>
            <a href="/files/Large-Load-FAQ.pdf">Large Load FAQ</a>
            """,
            index_url="https://www.ercot.com/services/rq/largeload",
        )
        self.assertTrue(load_documents)
        self.assertTrue(
            all(
                candidate.canonical_key.startswith("ercot-form:")
                for candidate in load_documents
            )
        )
        self.assertEqual(
            [
                candidate.extra["metadata"]["instrument_type"]
                for candidate in load_documents
            ],
            ["FORM", "FAQ"],
        )
        self.assertTrue(
            all(
                candidate.extra["metadata"]["status"] == "CURRENT"
                for candidate in load_documents
            )
        )

    def test_ercot_large_load_page_requires_labeled_governing_sections(self):
        module = self._discovery_module("ERCOTLargeLoadPageDiscoveryProvider")
        candidates = module.parse_ercot_large_load_page(
            """
            <a href="/files/planning-faq-2026.pdf">
              Large Load FAQ for Planning Guide 2026
            </a>
            <a href="/files/planning-section-9-faq.pdf">
              Large Load FAQ for Planning Guide Section 9
            </a>
            <a href="/files/protocol-section-25.pdf">
              Large Load Instructions for Protocol Sec. 25.5
            </a>
            """,
            index_url="https://www.ercot.com/services/rq/largeload",
        )
        self.assertEqual(candidates[0].extra["governing_keys"], [])
        self.assertEqual(
            candidates[1].extra["governing_keys"],
            ["ercot-planning:9"],
        )
        self.assertEqual(
            candidates[2].extra["governing_keys"],
            ["ercot-protocol:25.5"],
        )

    def test_ercot_issue_detail_discovers_complete_numbered_attachment_chain(self):
        module = self._discovery_module("ERCOTIssueIndexDiscoveryProvider")
        candidates = module.parse_ercot_issue_index(
            """
            <a href="/files/145PGRR-116-Board-Report-060226.docx">
              Board Report
            </a>
            <a href="/files/145PGRR-130-PUCT-Report-061826.docx">
              PUCT Report
            </a>
            <a href="/files/145PGRR-87-Comments-052026.pdf">
              Stakeholder Comments
            </a>
            <a href="/files/145PGRR-41-Legacy-Ballot-041526.xls">
              Legacy Ballot
            </a>
            """,
            index_url="https://www.ercot.com/mktrules/issues/PGRR145",
        )
        by_key = {candidate.canonical_key: candidate for candidate in candidates}
        self.assertEqual(
            set(by_key),
            {
                "ercot-pgrr:145",
                "ercot-pgrr:145:item:116",
                "ercot-pgrr:145:item:130",
                "ercot-pgrr:145:item:87",
                "ercot-pgrr:145:item:41",
            },
        )
        puct_report = by_key["ercot-pgrr:145:item:130"]
        self.assertEqual(
            puct_report.extra["filename"],
            "145PGRR-130-PUCT-Report-061826.docx",
        )
        self.assertEqual(puct_report.extra["descriptor"], "PUCT Report")
        self.assertEqual(puct_report.extra["filed_date"], "2026-06-18")
        self.assertEqual(puct_report.extra["family"], "pgrr")
        self.assertEqual(puct_report.extra["parent_key"], "ercot-pgrr:145")
        self.assertEqual(
            by_key["ercot-pgrr:145:item:41"].extra["source_extension"],
            "xls",
        )

    def test_ercot_issue_discovery_uses_shared_conservative_metadata(self):
        discovery_module = self._discovery_module("ERCOTIssueIndexDiscoveryProvider")
        source_module = self._source_module("ERCOTIssueAuthoritySourceProvider")
        candidates = discovery_module.parse_ercot_issue_index(
            """
            <a href="/files/145PGRR-1-060226.docx">Original PGRR</a>
            <a href="/files/145PGRR-87-Comments-052026.pdf">
              Stakeholder Comments
            </a>
            <a href="/files/145PGRR-116-Board-Report-060226.docx">
              Board Report
            </a>
            """,
            index_url="https://www.ercot.com/mktrules/issues/PGRR145",
        )
        metadata_by_key = {
            candidate.canonical_key: candidate.extra["metadata"]
            for candidate in candidates
        }
        self.assertEqual(
            metadata_by_key["ercot-pgrr:145"],
            {
                "instrument_type": "REVISION_REQUEST",
                "status": "PUBLISHED",
                "authority_weight": "EVIDENTIARY",
            },
        )
        self.assertEqual(
            metadata_by_key["ercot-pgrr:145:item:1"],
            {
                "instrument_type": "REVISION_REQUEST",
                "status": "FILED",
                "authority_weight": "EVIDENTIARY",
            },
        )
        self.assertEqual(
            metadata_by_key["ercot-pgrr:145:item:87"],
            {
                "instrument_type": "COMMENT",
                "status": "FILED",
                "authority_weight": "ADVOCACY",
            },
        )
        self.assertEqual(
            metadata_by_key["ercot-pgrr:145:item:116"],
            {
                "instrument_type": "STAFF_MEMO",
                "status": "FILED",
                "authority_weight": "EVIDENTIARY",
            },
        )
        self.assertIs(
            discovery_module.classify_ercot_issue_attachment,
            source_module.classify_ercot_issue_attachment,
        )

    def test_ercot_current_guide_infers_family_and_date_from_live_markup(self):
        guide_module = self._discovery_module("ERCOTGuideLibraryDiscoveryProvider")
        guides = guide_module.parse_ercot_guide_library(
            """
            <a download href="/files/09-071126.docx"
               title="Section 9: Large Load Interconnection">
              Section 9
            </a>
            """,
            index_url=("https://www.ercot.com/mktrules/guides/planning/current"),
        )
        self.assertEqual(len(guides), 1)
        self.assertEqual(guides[0].canonical_key, "ercot-planning:9")
        self.assertEqual(guides[0].url, "https://www.ercot.com/files/09-071126.docx")
        self.assertEqual(guides[0].extra["effective_from"], "2026-07-11")
        self.assertEqual(guides[0].extra["version_label"], "2026-07-11")
        self.assertTrue(guides[0].extra["current_version"])

    def test_ercot_undated_guide_currency_is_unknown_without_status_marker(self):
        guide_module = self._discovery_module("ERCOTGuideLibraryDiscoveryProvider")
        guides = guide_module.parse_ercot_guide_library(
            """
            <a href="/files/planning-guide-section-9.pdf">
              Planning Guide Section 9
            </a>
            """,
            index_url="https://www.ercot.com/mktrules/guides/planning",
        )
        self.assertEqual(len(guides), 1)
        self.assertIsNone(guides[0].extra["current_version"])
        self.assertEqual(
            guides[0].extra["current_version_review_state"],
            "UNKNOWN_PENDING_REVIEW",
        )

    def test_oncor_parsers_separate_current_history_rider_and_review_required(self):
        tariff_module = self._discovery_module("OncorTariffIndexDiscoveryProvider")
        tariffs = tariff_module.parse_oncor_tariff_index(
            """
            <a href="/docs/retail-delivery-tariff.pdf">
              Current Tariff for Retail Delivery Service
            </a>
            <a href="/docs/retail-delivery-tariff-03-01-2025.pdf">
              Previous Retail Delivery Tariff 03/01/2025
            </a>
            <a href="/docs/rider-lls.pdf">Rider LLS</a>
            """,
            index_url="https://www.oncor.com/tariffs",
        )
        by_key = {candidate.canonical_key: candidate for candidate in tariffs}
        self.assertIn("oncor-tariff:retail-delivery", by_key)
        historical = by_key["oncor-tariff:retail-delivery-2025-03-01"]
        self.assertFalse(historical.extra["current_version"])
        self.assertEqual(
            historical.extra["parent_key"],
            "oncor-tariff:retail-delivery",
        )
        self.assertIn("oncor-rider:lls", by_key)
        self.assertIsNone(by_key["oncor-rider:lls"].extra["current_version"])
        self.assertEqual(
            by_key["oncor-rider:lls"].extra["current_version_review_state"],
            "UNKNOWN_PENDING_REVIEW",
        )
        self.assertEqual(
            by_key["oncor-rider:lls"].extra["metadata"],
            {
                "instrument_type": "TARIFF",
                "status": "PUBLISHED",
                "authority_weight": "EVIDENTIARY",
            },
        )
        self.assertEqual(
            by_key["oncor-tariff:retail-delivery"].extra["metadata"],
            {
                "instrument_type": "TARIFF",
                "status": "CURRENT",
                "authority_weight": "CONTROLLING",
            },
        )

        service_module = self._discovery_module("OncorServiceDocumentDiscoveryProvider")
        service = service_module.parse_oncor_service_documents(
            '<a href="/docs/electric-service-guidelines.pdf">'
            "Electric Service Guidelines</a>",
            index_url="https://www.oncor.com/construction",
        )
        self.assertEqual(
            service[0].canonical_key,
            "oncor-service-guide:electric-service-guidelines",
        )
        self.assertEqual(service[0].extra["rights_status"], "REVIEW_REQUIRED")
        self.assertNotIn("link_only", service[0].extra)
        self.assertIsNone(service[0].extra["current_version"])
        self.assertEqual(
            service[0].extra["current_version_review_state"],
            "UNKNOWN_PENDING_REVIEW",
        )
        self.assertEqual(
            service[0].extra["metadata"],
            {
                "instrument_type": "TECHNICAL_GUIDE",
                "status": "PUBLISHED",
                "authority_weight": "EVIDENTIARY",
            },
        )

    def test_non_public_pack_discovery_is_explicitly_link_only(self):
        provider_class = self._discovery_class("OncorTariffIndexDiscoveryProvider")
        provider = provider_class()
        fixture = (
            '<a href="/docs/tariff.pdf">Current Tariff for Retail Delivery Service</a>'
        )
        with patch.object(
            provider,
            "_fetch_index_impl",
            return_value=(fixture, "www.oncor.com"),
        ):
            result = provider.discover_candidates(["https://www.oncor.com/tariffs"])
        self.assertEqual(len(result.candidates), 1)
        self.assertEqual(result.candidates[0].extra["discovery_mode"], "link-only")
        self.assertEqual(
            result.candidates[0].extra["publisher_license"],
            "copyright-review-required",
        )

    def test_pack_provider_rejects_another_installed_packs_host(self):
        provider = self._source_class("OncorTariffAuthoritySourceProvider")()
        cross_pack_candidate = DiscoveryCandidate(
            canonical_key="oncor-tariff:retail-delivery",
            url="https://www.ercot.com/files/not-oncor.pdf",
            title="Current Tariff for Retail Delivery Service",
            extra={
                "source_identifier": "not-oncor",
                "current_version": True,
            },
        )
        with self.assertRaisesRegex(ValueError, "outside declared source_hosts"):
            provider.locate(
                cross_pack_candidate.canonical_key,
                discovery_candidate=cross_pack_candidate,
            )

    def test_pack_discovery_rejects_cross_pack_redirect_final_host(self):
        provider = self._discovery_class("OncorTariffIndexDiscoveryProvider")()
        fixture = (
            '<a href="/docs/tariff.pdf">Current Tariff for Retail Delivery Service</a>'
        )
        with patch.object(
            provider,
            "_fetch_index_impl",
            return_value=(fixture, "www.ercot.com"),
        ):
            result = provider.discover_candidates(["https://www.oncor.com/tariffs"])
        self.assertEqual(result.candidates, [])
        self.assertIn(
            "redirect-final host", next(iter(result.skipped_index_urls.values()))
        )

    def test_pack_provider_rejects_cross_pack_redirect_final_host(self):
        provider = self._source_class("PUCTRuleAuthoritySourceProvider")()
        request = provider.locate("tx-admin-puct:25.109")
        with (
            patch(
                "opencontractserver.enrichment.authority_sources.safe_fetch_bytes",
                return_value=(
                    b"<h1>Rule 25.109</h1><p>Official rule text.</p>",
                    "www.ercot.com",
                ),
            ),
            self.assertRaisesRegex(ValueError, "redirect-final host"),
        ):
            provider.fetch(request)

    def test_statute_parser_stops_at_next_section_and_locates_current_host(self):
        provider_class = self._source_class("TexasStatuteAuthoritySourceProvider")
        provider = provider_class()
        request = provider.locate("tx-util:37.056")
        self.assertEqual(
            request.url,
            "https://tcss.legis.texas.gov/resources/UT/htm/UT.37.htm",
        )
        module = self._source_module("TexasStatuteAuthoritySourceProvider")
        parsed = module.parse_texas_statute_section(
            """
            <p>Sec. 37.056. Large load interconnection requirements.</p>
            <p>(a) The commission shall adopt rules.</p>
            <p>Sec. 37.057. Other requirements.</p>
            """,
            "37.056",
        )
        self.assertIn("commission shall adopt rules", parsed)
        self.assertNotIn("Other requirements", parsed)

    def test_statute_record_preserves_exact_publisher_chapter_bytes(self):
        module = self._source_module("TexasStatuteAuthoritySourceProvider")
        provider = self._source_class("TexasStatuteAuthoritySourceProvider")()
        request = provider.locate("tx-util:37.056")
        first_chapter = b"""
            <p>Sec. 37.056. Large load rule.</p>
            <p>(a) The commission shall adopt rules.</p>
            <p>Sec. 37.057. Original unrelated section.</p>
        """
        second_chapter = b"""
            <p>Sec. 37.056. Large load rule.</p>
            <p>(a) The commission shall adopt rules.</p>
            <p>Sec. 37.057. Amended unrelated section.</p>
        """
        with patch.object(
            module,
            "safe_fetch_bytes",
            side_effect=[
                (first_chapter, "tcss.legis.texas.gov"),
                (second_chapter, "tcss.legis.texas.gov"),
            ],
        ):
            first = provider.fetch(request)[0]
            second = provider.fetch(request)[0]
        self.assertEqual(first.content, first_chapter)
        self.assertEqual(second.content, second_chapter)
        self.assertNotEqual(first.content_hash, second.content_hash)
        self.assertEqual(first.mime_type, "text/html")
        self.assertEqual(first.extracted_text, second.extracted_text)
        self.assertEqual(first.metadata["raw_source_mime_type"], "text/html")
        self.assertTrue(provider.verify_publisher_evidence(first.canonical_key, first))
        self.assertFalse(provider.verify_publisher_evidence("tx-util:37.057", first))

    def test_puct_rule_requires_parsed_publisher_section_evidence(self):
        provider = self._source_class("PUCTRuleAuthoritySourceProvider")()
        request = provider.locate("tx-admin-puct:25.109")
        with patch(
            "opencontractserver.enrichment.authority_sources.safe_fetch_bytes",
            return_value=(
                b"<h1>Rule 25.109</h1><p>Official rule text.</p>",
                "www.puc.texas.gov",
            ),
        ):
            record = provider.fetch(request)[0]
        self.assertTrue(
            provider.verify_publisher_evidence(record.canonical_key, record)
        )
        self.assertFalse(
            provider.verify_publisher_evidence("tx-admin-puct:25.110", record)
        )

    def test_bill_provider_locates_house_bill_versions(self):
        provider = self._source_class("TexasBillAuthoritySourceProvider")()
        request = provider.locate("tx-hb:89r-5:enrolled")
        self.assertEqual(
            request.url,
            "https://capitol.texas.gov/tlodocs/89R/billtext/html/HB00005F.htm",
        )
        self.assertIn("H.B. 5", request.citation)

    def test_texas_legislative_history_defaults_to_rights_review(self):
        module = self._source_module("TexasBillAuthoritySourceProvider")
        provider = self._source_class("TexasBillAuthoritySourceProvider")()
        request = provider.locate("tx-hb:89r-5:enrolled")
        sentinel = object()
        with patch.object(
            module, "fetch_and_extract_authority_record", return_value=sentinel
        ) as fetch_record:
            self.assertEqual(provider._fetch_impl(request), [sentinel])
        kwargs = fetch_record.call_args.kwargs
        self.assertEqual(kwargs["rights_status"], RightsStatus.REVIEW_REQUIRED)
        self.assertIn("legal-edict status", kwargs["metadata"]["rights_basis"])
        self.assertEqual(provider.license, "mixed-review-required")

    def test_texas_bill_provider_classifies_only_known_document_stages(self):
        module = self._source_module("TexasBillAuthoritySourceProvider")
        provider = self._source_class("TexasBillAuthoritySourceProvider")()

        fiscal_note = DiscoveryCandidate(
            canonical_key="tx-hb:89r-5:fiscal-note",
            url="https://capitol.texas.gov/tlodocs/89R/fiscalnotes/html/HB00005A.htm",
            title="Fiscal Note for H.B. 5",
            extra={
                "source_identifier": "HB00005A",
                "stage": "fiscal-note",
            },
        )
        request = provider.locate(
            fiscal_note.canonical_key,
            discovery_candidate=fiscal_note,
        )
        sentinel = object()
        with patch.object(
            module, "fetch_and_extract_authority_record", return_value=sentinel
        ) as fetch_record:
            self.assertEqual(provider._fetch_impl(request), [sentinel])
        self.assertEqual(
            fetch_record.call_args.kwargs["instrument_type"],
            InstrumentType.STAFF_MEMO,
        )

        public_comment = DiscoveryCandidate(
            canonical_key="tx-hb:89r-5:comment:hb00005h",
            url=(
                "https://capitol.texas.gov/tlodocs/89R/publiccomments/"
                "billhistory/HB00005H.pdf"
            ),
            title="House Public Comments",
            extra={
                "source_identifier": "HB00005H",
                "stage": "comment",
            },
        )
        comment_request = provider.locate(
            public_comment.canonical_key,
            discovery_candidate=public_comment,
        )
        with patch.object(
            module, "fetch_and_extract_authority_record", return_value=sentinel
        ) as fetch_record:
            self.assertEqual(provider._fetch_impl(comment_request), [sentinel])
        self.assertEqual(
            fetch_record.call_args.kwargs["instrument_type"],
            InstrumentType.COMMENT,
        )
        self.assertEqual(
            fetch_record.call_args.kwargs["authority_weight"],
            AuthorityWeight.ADVOCACY,
        )

        unknown = DiscoveryCandidate(
            canonical_key="tx-hb:89r-5:mystery-attachment",
            url="https://capitol.texas.gov/tlodocs/89R/misc/html/HB00005X.htm",
            title="Attachment X",
            extra={
                "source_identifier": "HB00005X",
                "stage": "mystery-attachment",
            },
        )
        unknown_request = provider.locate(
            unknown.canonical_key,
            discovery_candidate=unknown,
        )
        with self.assertRaisesRegex(
            ValueError,
            "unknown Texas bill document stage",
        ):
            provider._fetch_impl(unknown_request)

    def test_puct_interchange_rights_are_classified_per_record(self):
        module = self._source_module("PUCTInterchangeDocumentAuthoritySourceProvider")
        final_order = module.classify_puct_interchange_document(
            "puct-order:58211:4",
            "Final Order",
            publisher_document_type="Final Order",
            publisher_author_role="Commission",
        )
        testimony = module.classify_puct_interchange_document(
            "puct-project:58211:item:8", "Direct Testimony of Example LLC"
        )
        self.assertEqual(final_order[0], InstrumentType.FINAL_ORDER)
        self.assertEqual(final_order[3], "puct-electric-rules-and-orders")
        self.assertEqual(final_order[4], RightsStatus.PUBLIC_DOMAIN)
        self.assertEqual(testimony[0], InstrumentType.TESTIMONY)
        self.assertEqual(testimony[3], "puct-large-load-proceedings")
        self.assertEqual(testimony[4], RightsStatus.REVIEW_REQUIRED)
        with self.assertRaisesRegex(ValueError, "structured publisher evidence"):
            module.classify_puct_interchange_document(
                "puct-order:58211:4",
                "Final Order",
            )
        procedural_filing = module.classify_puct_interchange_document(
            "puct-project:58211:item:9:document:123",
            "Attachment A",
            publisher_document_type="Application",
            publisher_author_role="filing-party",
        )
        self.assertEqual(procedural_filing[0], InstrumentType.FILING)
        self.assertEqual(procedural_filing[1], AuthorityWeight.ADVOCACY)
        self.assertEqual(procedural_filing[2], SourceStatus.FILED)
        self.assertEqual(procedural_filing[4], RightsStatus.REVIEW_REQUIRED)

        agency_filing = module.classify_puct_interchange_document(
            "puct-project:58211:item:10:document:124",
            "Control Number Request",
            publisher_document_type="LTRS",
            publisher_author_role="agency",
        )
        self.assertEqual(agency_filing[0], InstrumentType.FILING)
        self.assertEqual(agency_filing[1], AuthorityWeight.INTERPRETIVE)

    def test_puct_attachment_fetch_emits_filed_in_and_forwards_pack_ca(self):
        module = self._source_module("PUCTInterchangeDocumentAuthoritySourceProvider")
        provider = self._source_class(
            "PUCTInterchangeDocumentAuthoritySourceProvider"
        )()
        candidate = DiscoveryCandidate(
            canonical_key="puct-project:59142:item:2:document:1567373",
            url="https://interchange.puc.texas.gov/Documents/59142_2_1567373.PDF",
            title="Joint Comments on ERCOT Large Load Process Reforms (PDF rendition)",
            extra={
                "control_number": "59142",
                "item_number": "2",
                "document_id": "1567373",
                "document_name": "59142_2_1567373.PDF",
                "source_identifier": "59142_2_1567373",
                "parent_key": "puct-project:59142",
                "publisher_document_type": (
                    "Joint Comments on ERCOT Large Load Process Reforms"
                ),
                "publisher_author_role": "filing-party",
                "filed_date": "2025-12-18",
            },
        )
        request = provider.locate(
            candidate.canonical_key,
            discovery_candidate=candidate,
        )
        sentinel = object()
        ca_bundle = ("-----BEGIN CERTIFICATE-----\nfixture\n-----END CERTIFICATE-----",)
        with patch.object(
            module,
            "fetch_and_extract_authority_record",
            return_value=sentinel,
        ) as fetch_record:
            self.assertEqual(
                provider._fetch_impl(
                    request,
                    extra_ca_certificates=ca_bundle,
                ),
                [sentinel],
            )

        kwargs = fetch_record.call_args.kwargs
        self.assertEqual(kwargs["instrument_type"], InstrumentType.COMMENT)
        self.assertEqual(kwargs["authority_weight"], AuthorityWeight.ADVOCACY)
        self.assertEqual(kwargs["rights_status"], RightsStatus.REVIEW_REQUIRED)
        self.assertEqual(kwargs["extra_ca_certificates"], ca_bundle)
        self.assertEqual(
            [
                (relationship.relationship_type, relationship.target_key)
                for relationship in kwargs["relationships"]
            ],
            [(RelationshipType.FILED_IN, "puct-project:59142")],
        )

    def test_puct_native_zip_returns_package_and_every_safe_member(self):
        module = self._source_module("PUCTInterchangeDocumentAuthoritySourceProvider")
        provider = self._source_class(
            "PUCTInterchangeDocumentAuthoritySourceProvider"
        )()
        package_url = "https://interchange.puc.texas.gov/Documents/59142_2_1567372.ZIP"
        rendition_url = (
            "https://interchange.puc.texas.gov/Documents/59142_2_1567373.PDF"
        )
        candidate = DiscoveryCandidate(
            canonical_key="puct-project:59142:item:2:document:1567372",
            url=package_url,
            title=(
                "Joint Comments on ERCOT Large Load Process Reforms "
                "(native filing package)"
            ),
            extra={
                "control_number": "59142",
                "item_number": "2",
                "document_id": "1567372",
                "document_name": "59142_2_1567372.ZIP",
                "source_identifier": "59142_2_1567372",
                "parent_key": "puct-project:59142",
                "publisher_document_type": (
                    "Joint Comments on ERCOT Large Load Process Reforms"
                ),
                "publisher_author_role": "filing-party",
                "filed_date": "2025-12-18",
                "pdf_rendition_url": rendition_url,
            },
        )
        request = provider.locate(
            candidate.canonical_key,
            discovery_candidate=candidate,
        )

        package_buffer = io.BytesIO()
        native_members = {
            "letter.txt": b"Native publisher letter body.",
            "support/appendix.html": (
                b"<html><body>Native publisher appendix.</body></html>"
            ),
        }
        with zipfile.ZipFile(
            package_buffer,
            "w",
            compression=zipfile.ZIP_DEFLATED,
        ) as archive:
            for name, content in native_members.items():
                archive.writestr(name, content)
        package_bytes = package_buffer.getvalue()
        rendition_bytes = b"%PDF-1.7\nmock official consolidated rendition"
        ca_bundle = ("-----BEGIN CERTIFICATE-----\nfixture\n-----END CERTIFICATE-----",)

        with (
            patch.object(
                module,
                "safe_fetch_bytes",
                side_effect=[
                    (package_bytes, "interchange.puc.texas.gov"),
                    (rendition_bytes, "interchange.puc.texas.gov"),
                ],
            ) as safe_fetch,
            patch.object(
                module,
                "extract_authority_text",
                return_value="Official extracted publisher text.",
            ),
        ):
            records = list(
                provider.fetch(
                    request,
                    extra_ca_certificates=ca_bundle,
                    max_bytes=134_217_728,
                )
            )

        self.assertEqual(len(records), 1 + len(native_members))
        package = records[0]
        self.assertEqual(package.canonical_key, candidate.canonical_key)
        self.assertEqual(package.content, package_bytes)
        self.assertEqual(package.mime_type, "application/zip")
        self.assertEqual(package.portable_rendition_content, rendition_bytes)
        self.assertEqual(
            package.portable_rendition_mime_type,
            "application/pdf",
        )
        self.assertEqual(
            package.portable_rendition_filename,
            "59142_2_1567373.PDF",
        )
        self.assertTrue(
            provider.verify_publisher_evidence(package.canonical_key, package)
        )
        for record in records:
            self.assertEqual(record.rights_status, RightsStatus.REVIEW_REQUIRED)
            self.assertEqual(
                [
                    (relationship.relationship_type, relationship.target_key)
                    for relationship in record.relationships
                ],
                [(RelationshipType.FILED_IN, "puct-project:59142")],
            )

        member_records = {
            record.metadata["archive_member_name"]: record for record in records[1:]
        }
        self.assertEqual(set(member_records), set(native_members))
        expected_member_mime_types = {
            "letter.txt": "text/plain",
            "support/appendix.html": "text/html",
        }
        for member_name, member_content in native_members.items():
            record = member_records[member_name]
            expected_key = module.puct_interchange_key_from_evidence(
                control_number="59142",
                item_number="2",
                document_id="1567372",
                document_name="59142_2_1567372.ZIP",
                archive_member_name=member_name,
                title="Joint Comments on ERCOT Large Load Process Reforms",
                publisher_document_type=(
                    "Joint Comments on ERCOT Large Load Process Reforms"
                ),
                publisher_author_role="filing-party",
            )
            self.assertEqual(record.canonical_key, expected_key)
            self.assertEqual(record.content, member_content)
            self.assertEqual(
                record.mime_type,
                expected_member_mime_types[member_name],
            )
            self.assertEqual(
                record.metadata["archive_member_mime_type"],
                expected_member_mime_types[member_name],
            )
            self.assertEqual(record.metadata["archive_parent_key"], package.key)
            self.assertTrue(
                provider.verify_publisher_evidence(record.canonical_key, record)
            )
            self.assertFalse(
                provider.verify_publisher_evidence(
                    f"{record.canonical_key}-tampered",
                    record,
                )
            )
        self.assertEqual(
            len({record.canonical_key for record in records}), len(records)
        )
        self.assertEqual(
            [call.args[0] for call in safe_fetch.call_args_list],
            [package_url, rendition_url],
        )
        for call in safe_fetch.call_args_list:
            self.assertEqual(
                call.kwargs["extra_ca_certificates"],
                ca_bundle,
            )
            self.assertEqual(call.kwargs["max_bytes"], 134_217_728)

    def test_ercot_issue_and_notice_parsers_preserve_status_and_relationships(self):
        issue_module = self._source_module("ERCOTIssueAuthoritySourceProvider")
        issue = issue_module.parse_ercot_issue_page(
            """
            <h1>PGRR115</h1>
            <p>Title: Large Load Interconnection Requirements</p>
            <p>Status: Approved 01/15/2026</p>
            <p>Effective Dates: 02/01/2026</p>
            <p>Date Posted: 12/01/2025</p>
            <p>Sponsor: ERCOT</p>
            <p>Sections: 9.1.1 and 9.2</p>
            <p>Related NPRR1234</p>
            """,
            family="pgrr",
            number="115",
        )
        self.assertEqual(issue.source_status, SourceStatus.APPROVED)
        self.assertEqual(issue.effective_from, "02/01/2026")
        self.assertEqual(issue.sections, ("9.1.1", "9.2"))
        self.assertIn("ercot-nprr:1234", issue.related_keys)

        notice_module = self._source_module("ERCOTMarketNoticeAuthoritySourceProvider")
        _, issued_date, relationships, _ = notice_module.parse_ercot_market_notice(
            """
                <h1>Market Notice M-A010126-01</h1>
                <p>Implements Planning Guide Section 9.1.</p>
                <p>See Market Notice M-A123125-02.</p>
                """,
            notice_id="M-A010126-01",
        )
        self.assertEqual(issued_date, "2026-01-01")
        targets = {relationship.target_key for relationship in relationships}
        self.assertIn("ercot-planning:9.1", targets)
        self.assertIn("ercot-notice:M-A123125-02", targets)

        _, _, edition_relationships, _ = notice_module.parse_ercot_market_notice(
            """
                <h1>Market Notice M-A010126-01</h1>
                <p>Planning Guide 2025 and Nodal Protocols 2026 editions.</p>
                <p>Planning Guide Sec. 9 and Protocol § 3.2 apply.</p>
            """,
            notice_id="M-A010126-01",
        )
        self.assertEqual(
            {relationship.target_key for relationship in edition_relationships},
            {"ercot-planning:9", "ercot-protocol:3.2"},
        )

    def test_ercot_issue_plain_section_and_unknown_status_rules(self):
        module = self._source_module("ERCOTIssueAuthoritySourceProvider")
        issue = module.parse_ercot_issue_page(
            """
            <h1>PGRR145</h1>
            <p>Title: Large Load Process</p>
            <p>Status: Posted</p>
            <p>Sections: 9</p>
            """,
            family="pgrr",
            number="145",
        )
        self.assertEqual(issue.sections, ("9",))
        self.assertEqual(issue.source_status, SourceStatus.PUBLISHED)
        with self.assertRaisesRegex(ValueError, "unknown ERCOT issue publisher status"):
            module.parse_ercot_issue_page(
                """
                <h1>PGRR145</h1>
                <p>Title: Large Load Process</p>
                <p>Status: Under Discussion</p>
                <p>Sections: 9</p>
                """,
                family="pgrr",
                number="145",
            )

    def test_pending_ercot_revision_request_is_evidentiary_not_controlling(self):
        module = self._source_module("ERCOTIssueAuthoritySourceProvider")
        provider = self._source_class("ERCOTIssueAuthoritySourceProvider")()
        request = provider.locate("ercot-pgrr:115")
        pending_html = b"""
            <h1>PGRR115</h1>
            <p>Title: Large Load Study Process</p>
            <p>Status: Pending</p>
            <p>Date Posted: 12/01/2025</p>
            <p>Sections: 9.1.1</p>
        """
        with patch.object(
            module,
            "safe_fetch_bytes",
            return_value=(pending_html, "www.ercot.com"),
        ):
            record = provider.fetch(request)[0]
        self.assertEqual(record.status, SourceStatus.PENDING)
        self.assertEqual(record.authority_weight, "EVIDENTIARY")
        self.assertTrue(
            provider.verify_publisher_evidence(record.canonical_key, record)
        )

    def test_ercot_issue_attachments_are_noncontrolling_and_filed_in_root(self):
        discovery_module = self._discovery_module("ERCOTIssueIndexDiscoveryProvider")
        source_module = self._source_module("ERCOTIssueAuthoritySourceProvider")
        provider = self._source_class("ERCOTIssueAuthoritySourceProvider")()
        candidates = discovery_module.parse_ercot_issue_index(
            """
            <a href="/files/145PGRR-116-Board-Report-060226.docx">
              Board Report
            </a>
            <a href="/files/145PGRR-87-Comments-052026.pdf">
              Stakeholder Comments
            </a>
            """,
            index_url="https://www.ercot.com/mktrules/issues/PGRR145",
        )
        attachments = [
            candidate for candidate in candidates if ":item:" in candidate.canonical_key
        ]
        sentinel = object()
        observed: dict[str, dict[str, Any]] = {}
        for candidate in attachments:
            request = provider.locate(
                candidate.canonical_key, discovery_candidate=candidate
            )
            with patch.object(
                source_module,
                "fetch_and_extract_authority_record",
                return_value=sentinel,
            ) as fetch_record:
                self.assertEqual(provider._fetch_impl(request), [sentinel])
            observed[candidate.canonical_key] = dict(fetch_record.call_args.kwargs)

        board = observed["ercot-pgrr:145:item:116"]
        self.assertEqual(board["instrument_type"], InstrumentType.STAFF_MEMO)
        self.assertEqual(board["authority_weight"], "EVIDENTIARY")
        self.assertEqual(board["parent_key"], "ercot-pgrr:145")
        self.assertEqual(board["relationships"][0].relationship_type, "FILED_IN")
        comments = observed["ercot-pgrr:145:item:87"]
        self.assertEqual(comments["instrument_type"], InstrumentType.COMMENT)
        self.assertEqual(comments["authority_weight"], "ADVOCACY")
        with self.assertRaisesRegex(ValueError, "unknown ERCOT issue attachment"):
            source_module.classify_ercot_issue_attachment("Supporting File")
        self.assertEqual(
            source_module.classify_ercot_issue_attachment(
                "145PGRR-1-060226.docx",
                item_sequence="1",
            ),
            (InstrumentType.REVISION_REQUEST, AuthorityWeight.EVIDENTIARY),
        )
        with self.assertRaisesRegex(ValueError, "unknown ERCOT issue attachment"):
            source_module.classify_ercot_issue_attachment(
                "145PGRR-2-060226.docx",
                item_sequence="2",
            )

    def test_ercot_legacy_xls_attachment_is_not_silently_skipped(self):
        discovery_module = self._discovery_module("ERCOTIssueIndexDiscoveryProvider")
        provider = self._source_class("ERCOTIssueAuthoritySourceProvider")()
        candidates = discovery_module.parse_ercot_issue_index(
            '<a href="/files/145PGRR-41-Legacy-Ballot-041526.xls">Legacy Ballot</a>',
            index_url="https://www.ercot.com/mktrules/issues/PGRR145",
        )
        candidate = next(
            item for item in candidates if item.canonical_key.endswith(":item:41")
        )
        request = provider.locate(
            candidate.canonical_key, discovery_candidate=candidate
        )
        with (
            patch(
                "opencontractserver.enrichment.authority_sources.safe_fetch_bytes",
                return_value=(b"legacy xls bytes", "www.ercot.com"),
            ),
            self.assertRaisesRegex(ValueError, "unsupported authority .* MIME"),
        ):
            provider.fetch(request)

    def test_ercot_operating_guide_routes_to_current_rules(self):
        module = self._source_module("ERCOTGuideAuthoritySourceProvider")
        provider = self._source_class("ERCOTGuideAuthoritySourceProvider")()
        candidate = DiscoveryCandidate(
            canonical_key="ercot-operating:2",
            url="https://www.ercot.com/files/current-operating-guide.pdf",
            title="Current Nodal Operating Guide Section 2",
            extra={
                "current_version": True,
                "source_identifier": "nog-2",
                "guide_family": "ercot-operating",
            },
        )
        request = provider.locate(
            candidate.canonical_key, discovery_candidate=candidate
        )
        sentinel = object()
        with patch.object(
            module, "fetch_and_extract_authority_record", return_value=sentinel
        ) as fetch_record:
            self.assertEqual(provider._fetch_impl(request), [sentinel])
        kwargs = fetch_record.call_args.kwargs
        self.assertEqual(kwargs["instrument_type"], InstrumentType.OPERATING_GUIDE)
        self.assertEqual(kwargs["corpus_slug"], "ercot-current-large-load-rules")
        self.assertEqual(kwargs["rights_status"], RightsStatus.REVIEW_REQUIRED)

    def test_ercot_guide_provider_never_fetches_an_index_as_section_content(self):
        provider = self._source_class("ERCOTGuideAuthoritySourceProvider")()
        with self.assertRaisesRegex(ValueError, "attachment URL"):
            provider.locate("ercot-planning:9")

    def test_historical_ercot_guide_routes_to_revision_history(self):
        module = self._source_module("ERCOTGuideAuthoritySourceProvider")
        provider = self._source_class("ERCOTGuideAuthoritySourceProvider")()
        candidate = DiscoveryCandidate(
            canonical_key="ercot-planning:planning-guide-2024-01-01",
            url="https://www.ercot.com/files/planning-guide-2024-01-01.pdf",
            title="Planning Guide 2024-01-01",
            extra={
                "current_version": False,
                "source_identifier": "planning-guide-2024-01-01",
                "version_label": "2024-01-01",
                "guide_family": "ercot-planning",
            },
        )
        request = provider.locate(
            candidate.canonical_key, discovery_candidate=candidate
        )
        sentinel = object()
        with patch.object(
            module, "fetch_and_extract_authority_record", return_value=sentinel
        ) as fetch_record:
            self.assertEqual(provider._fetch_impl(request), [sentinel])
        self.assertEqual(
            fetch_record.call_args.kwargs["corpus_slug"],
            "ercot-large-load-revision-history",
        )
        self.assertEqual(
            fetch_record.call_args.kwargs["status"],
            SourceStatus.SUPERSEDED,
        )
        self.assertEqual(
            fetch_record.call_args.kwargs["authority_weight"],
            "EVIDENTIARY",
        )

    def test_listing_current_version_rejects_truthy_strings(self):
        provider = self._source_class("OncorTariffAuthoritySourceProvider")()
        candidate = DiscoveryCandidate(
            canonical_key="oncor-tariff:retail-delivery",
            url="https://www.oncor.com/docs/current-tariff.pdf",
            title="Current Tariff for Retail Delivery Service",
            extra={
                "source_identifier": "current-tariff",
                "current_version": "false",
            },
        )
        request = provider.locate(
            candidate.canonical_key,
            discovery_candidate=candidate,
        )
        with self.assertRaisesRegex(
            ValueError, "current_version must be true, false, or null"
        ):
            provider._fetch_impl(request)

    def test_oncor_service_provider_fetches_real_review_required_content(self):
        module = self._source_module("OncorServiceDocumentAuthoritySourceProvider")
        provider = self._source_class("OncorServiceDocumentAuthoritySourceProvider")()
        candidate = DiscoveryCandidate(
            canonical_key="oncor-service-guide:electric-service-guidelines",
            url="https://www.oncor.com/docs/electric-service-guidelines.pdf",
            title="Oncor Electric Service Guidelines",
            extra={
                "source_identifier": "electric-service-guidelines",
                "current_version": True,
                "effective_from": "2025-02-01",
                "version_label": "2025-02",
            },
        )
        request = provider.locate(
            candidate.canonical_key, discovery_candidate=candidate
        )
        sentinel = object()
        with patch.object(
            module,
            "fetch_and_extract_authority_record",
            return_value=sentinel,
        ) as fetch_record:
            self.assertEqual(provider._fetch_impl(request), [sentinel])

        kwargs = fetch_record.call_args.kwargs
        self.assertEqual(kwargs["rights_status"], RightsStatus.REVIEW_REQUIRED)
        self.assertEqual(kwargs["corpus_slug"], "oncor-service-requirements")
        self.assertTrue(kwargs["current_version"])
        self.assertEqual(kwargs["status"], SourceStatus.CURRENT)
        self.assertEqual(
            kwargs["authority_weight"],
            AuthorityWeight.IMPLEMENTING,
        )
        self.assertEqual(kwargs["effective_from"], "2025-02-01")
        self.assertEqual(kwargs["version_label"], "2025-02")
        self.assertEqual(
            [
                (relationship.relationship_type, relationship.target_key)
                for relationship in kwargs["relationships"]
            ],
            [
                (
                    RelationshipType.IMPLEMENTS,
                    "oncor-tariff:retail-delivery",
                )
            ],
        )

    def test_oncor_historical_tariff_routes_to_history_slug(self):
        provider = self._source_class("OncorTariffAuthoritySourceProvider")()
        candidate = DiscoveryCandidate(
            canonical_key="oncor-tariff:retail-delivery-2017-11-27",
            url=(
                "https://www.oncor.com/docs/"
                "Tariff%20for%20Retail%20Delivery%20Service.pdf"
            ),
            title="Oncor Retail Delivery Tariff, Revision Twenty",
            extra={
                "source_identifier": "tariff-revision-20",
                "current_version": False,
                "parent_key": "oncor-tariff:retail-delivery",
                "effective_from": "2017-11-27",
            },
        )
        request = provider.locate(
            candidate.canonical_key, discovery_candidate=candidate
        )
        extracted_text = (
            "Tariff for Retail Delivery Service\n"
            "Oncor Electric Delivery Company LLC\n"
            "Effective Date: November 27, 2017 Revision: Twenty\n"
        )
        with (
            patch(
                "opencontractserver.enrichment.authority_sources.safe_fetch_bytes",
                return_value=(
                    b"%PDF-1.7\nmock Oncor historical tariff",
                    "www.oncor.com",
                ),
            ),
            patch(
                "opencontractserver.enrichment.authority_sources.extract_authority_text",
                return_value=extracted_text,
            ),
        ):
            record = provider._fetch_impl(request)[0]

        self.assertEqual(record.corpus_slug, "oncor-tariff-history")
        self.assertEqual(record.rights_status, RightsStatus.REVIEW_REQUIRED)
        relationship_types = {
            relationship.relationship_type for relationship in record.relationships
        }
        self.assertEqual(
            relationship_types,
            {"EFFECTIVE_VERSION_OF", "SUPERSEDED_BY"},
        )
        parsed_evidence = {
            evidence.value
            for evidence in record.publisher_evidence
            if evidence.source == "PARSED_CONTENT"
        }
        self.assertEqual(
            parsed_evidence,
            {
                "Effective Date: November 27, 2017",
                "Revision: Twenty",
            },
        )
        self.assertTrue(
            provider.verify_publisher_evidence(record.canonical_key, record)
        )
        self.assertFalse(
            provider.verify_publisher_evidence(
                "oncor-tariff:retail-delivery-2017-11-28",
                record,
            )
        )
        for missing_marker in (
            "Effective Date: November 27, 2017",
            "Revision: Twenty",
        ):
            record_missing_marker = replace(
                record,
                publisher_evidence=tuple(
                    evidence
                    for evidence in record.publisher_evidence
                    if evidence.value != missing_marker
                ),
            )
            self.assertFalse(
                provider.verify_publisher_evidence(
                    record_missing_marker.canonical_key,
                    record_missing_marker,
                )
            )
        record_without_parsed_content = replace(
            record,
            publisher_evidence=tuple(
                evidence
                for evidence in record.publisher_evidence
                if evidence.source != "PARSED_CONTENT"
            ),
        )
        self.assertFalse(
            provider.verify_publisher_evidence(
                record_without_parsed_content.canonical_key,
                record_without_parsed_content,
            )
        )

    def test_oncor_undated_tariff_is_unknown_not_controlling(self):
        module = self._source_module("OncorTariffAuthoritySourceProvider")
        provider = self._source_class("OncorTariffAuthoritySourceProvider")()
        candidate = DiscoveryCandidate(
            canonical_key="oncor-rider:lls",
            url="https://www.oncor.com/docs/rider-lls.pdf",
            title="Rider LLS",
            extra={
                "source_identifier": "rider-lls",
                "current_version": None,
            },
        )
        request = provider.locate(
            candidate.canonical_key,
            discovery_candidate=candidate,
        )
        sentinel = object()
        with patch.object(
            module, "fetch_and_extract_authority_record", return_value=sentinel
        ) as fetch_record:
            self.assertEqual(provider._fetch_impl(request), [sentinel])
        kwargs = fetch_record.call_args.kwargs
        self.assertIsNone(kwargs["current_version"])
        self.assertEqual(kwargs["status"], SourceStatus.PUBLISHED)
        self.assertEqual(
            kwargs["authority_weight"],
            AuthorityWeight.EVIDENTIARY,
        )
        self.assertEqual(
            kwargs["metadata"]["current_version_review_state"],
            "UNKNOWN_PENDING_REVIEW",
        )
