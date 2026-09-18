"""
Tests for the California foreclosure compliance integration.

Organised into scenario groups:

1. INSTRUMENT CLASSIFICATION - reading what a document *is* off its text
2. DATE EXTRACTION           - reading the dates the statute measures from
3. MATTER ASSEMBLY           - turning a corpus of instruments into a matter
4. SERVICE CLIENT            - transport, error surfacing, result shaping

The ruleset itself is tested in the Rust crate (`legalis-ca-foreclosure`, 94
tests). These tests cover the Python side of the boundary: what gets sent, and
what is done with what comes back.

Deliberately covered: the cases that must NOT read as compliance. A document
whose type cannot be established, a matter with no recognisable instruments,
and a service that is down all have to fail loudly — a compliance analyzer that
reports a clean bill of health because it could not reach its ruleset is worse
than one that crashes.
"""

import datetime
from unittest.mock import MagicMock, patch

import requests
from django.test import SimpleTestCase

from opencontractserver.foreclosure.client import (
    ComplianceResult,
    ForeclosureComplianceClient,
    ForeclosureServiceError,
)
from opencontractserver.foreclosure.matter import (
    NOTICE_OF_DEFAULT,
    NOTICE_OF_SALE,
    RECONVEYANCE,
    build_matter,
    classify_instrument,
    find_instrument_number,
    find_labelled_date,
    instrument_from_text,
    parse_date,
)

# ---------------------------------------------------------------------------
# 1. INSTRUMENT CLASSIFICATION
# ---------------------------------------------------------------------------


class InstrumentClassificationTests(SimpleTestCase):
    def test_classifies_a_notice_of_default(self):
        self.assertEqual(
            classify_instrument("NOTICE OF DEFAULT AND ELECTION TO SELL"),
            NOTICE_OF_DEFAULT,
        )

    def test_notice_of_default_outranks_the_deed_of_trust_it_recites(self):
        # The full heading contains "deed of trust"; the earliest match wins so
        # the specific instrument is not shadowed by the general one.
        self.assertEqual(
            classify_instrument(
                "NOTICE OF DEFAULT AND ELECTION TO SELL UNDER DEED OF TRUST"
            ),
            NOTICE_OF_DEFAULT,
        )

    def test_classifies_a_notice_of_trustees_sale_with_and_without_apostrophe(self):
        self.assertEqual(classify_instrument("NOTICE OF TRUSTEE'S SALE"), NOTICE_OF_SALE)
        self.assertEqual(classify_instrument("NOTICE OF TRUSTEES SALE"), NOTICE_OF_SALE)

    def test_classifies_a_reconveyance(self):
        self.assertEqual(
            classify_instrument("FULL RECONVEYANCE"),
            RECONVEYANCE,
        )

    def test_unrecognised_text_returns_none_rather_than_guessing(self):
        self.assertIsNone(classify_instrument("Quarterly earnings statement"))
        self.assertIsNone(classify_instrument(""))


# ---------------------------------------------------------------------------
# 2. DATE EXTRACTION
# ---------------------------------------------------------------------------


class DateExtractionTests(SimpleTestCase):
    def test_parses_the_formats_recorded_instruments_use(self):
        expected = datetime.date(2024, 1, 15)
        for value in ("January 15, 2024", "01/15/2024", "2024-01-15", "Jan 15, 2024"):
            with self.subTest(value=value):
                self.assertEqual(parse_date(value), expected)

    def test_rejects_text_that_is_not_a_date(self):
        self.assertIsNone(parse_date("sometime last spring"))

    def test_finds_a_labelled_recording_date(self):
        text = "A.P.N.: 123-456\nRecording Date: January 15, 2024\nTrustor: Someone"
        self.assertEqual(
            find_labelled_date(text, ("Recording Date",)),
            datetime.date(2024, 1, 15),
        )

    def test_label_matching_is_case_insensitive(self):
        self.assertEqual(
            find_labelled_date("recording date: 01/15/2024", ("Recording Date",)),
            datetime.date(2024, 1, 15),
        )

    def test_absent_label_yields_none(self):
        self.assertIsNone(find_labelled_date("no dates here", ("Recording Date",)))

    def test_finds_the_instrument_number(self):
        self.assertEqual(
            find_instrument_number("Instrument No. 2024-0114872 recorded"),
            "2024-0114872",
        )
        self.assertIsNone(find_instrument_number("no number present"))


class InstrumentFromTextTests(SimpleTestCase):
    NOD_TEXT = (
        "NOTICE OF DEFAULT AND ELECTION TO SELL UNDER DEED OF TRUST\n"
        "Instrument No. 2024-0114872\n"
        "Recording Date: January 15, 2024\n"
        "Date Mailed to Trustor: January 22, 2024\n"
    )

    def test_builds_an_instrument_payload(self):
        payload = instrument_from_text(self.NOD_TEXT, document_id=7)
        self.assertIsNotNone(payload)
        self.assertEqual(payload["kind"], NOTICE_OF_DEFAULT)
        self.assertEqual(payload["recorded_date"], "2024-01-15")
        self.assertEqual(payload["mailed_date"], "2024-01-22")
        self.assertEqual(payload["instrument_number"], "2024-0114872")

    def test_provenance_names_the_source_document(self):
        payload = instrument_from_text(self.NOD_TEXT, document_id=7)
        self.assertEqual(payload["provenance"]["document_id"], "7")

    def test_title_is_consulted_before_body_text(self):
        # The body mentions a reconveyance; the title says what this document is.
        payload = instrument_from_text(
            "This instrument follows a Full Reconveyance of an earlier lien.\n"
            "Recording Date: March 1, 2024\n",
            title="NOTICE OF TRUSTEE'S SALE",
        )
        self.assertEqual(payload["kind"], NOTICE_OF_SALE)

    def test_document_without_a_recording_date_is_dropped_not_guessed(self):
        payload = instrument_from_text("NOTICE OF DEFAULT with no dates", document_id=1)
        self.assertIsNone(payload)

    def test_unrecognisable_document_is_dropped(self):
        self.assertIsNone(
            instrument_from_text("Recording Date: January 15, 2024", document_id=1)
        )


# ---------------------------------------------------------------------------
# 3. MATTER ASSEMBLY
# ---------------------------------------------------------------------------


class FakeFile:
    def __init__(self, text: str):
        self._text = text

    def read(self):
        return self._text.encode("utf-8")


class FakeDocument:
    def __init__(self, doc_id, title, text):
        self.id = doc_id
        self.title = title
        self.txt_extract_file = FakeFile(text) if text is not None else None


class MatterAssemblyTests(SimpleTestCase):
    def _documents(self):
        return [
            FakeDocument(
                1,
                "Notice of Default",
                "NOTICE OF DEFAULT\nRecording Date: January 15, 2024\n"
                "Date Mailed to Trustor: January 22, 2024\n",
            ),
            FakeDocument(
                2,
                "Notice of Trustee's Sale",
                "NOTICE OF TRUSTEE'S SALE\nRecording Date: April 22, 2024\n"
                "First Publication Date: April 22, 2024\n"
                "Date Posted: April 22, 2024\n",
            ),
        ]

    def test_builds_a_matter_from_a_corpus_of_instruments(self):
        matter, unrecognised = build_matter(
            matter_id="corpus-1", documents=self._documents()
        )
        self.assertEqual(len(matter["instruments"]), 2)
        self.assertEqual(unrecognised, [])
        self.assertEqual(matter["matter_id"], "corpus-1")

    def test_facts_that_no_instrument_carries_come_from_input(self):
        matter, _ = build_matter(
            matter_id="corpus-1",
            documents=self._documents(),
            facts={
                "sale_date": "2024-06-14",
                "loan_purpose": "consumer",
                "occupancy": "owner_occupied",
                "dwelling_units": 1,
            },
        )
        self.assertEqual(matter["sale_date"], "2024-06-14")
        self.assertEqual(matter["loan_purpose"], "consumer")

    def test_absent_facts_stay_null_rather_than_being_invented(self):
        matter, _ = build_matter(matter_id="c", documents=self._documents())
        # These gate whole bodies of law; guessing them would be worse than
        # reporting the gap.
        self.assertIsNone(matter["sale_date"])
        self.assertIsNone(matter["loan_purpose"])
        self.assertIsNone(matter["occupancy"])

    def test_unreadable_documents_are_reported_not_silently_dropped(self):
        documents = self._documents() + [
            FakeDocument(3, "Cover letter", "Dear Sir, please find enclosed.")
        ]
        matter, unrecognised = build_matter(matter_id="c", documents=documents)
        self.assertEqual(len(matter["instruments"]), 2)
        self.assertEqual([d.id for d in unrecognised], [3])

    def test_document_with_no_extract_is_unrecognised(self):
        matter, unrecognised = build_matter(
            matter_id="c", documents=[FakeDocument(9, "Untitled", None)]
        )
        self.assertEqual(matter["instruments"], [])
        self.assertEqual(len(unrecognised), 1)

    def test_list_facts_pass_through(self):
        matter, _ = build_matter(
            matter_id="c",
            documents=self._documents(),
            facts={
                "reinstatement_tenders": [
                    {
                        "tendered_date": "2024-06-05",
                        "amount_sufficient": True,
                        "accepted": False,
                    }
                ]
            },
        )
        self.assertEqual(len(matter["reinstatement_tenders"]), 1)


# ---------------------------------------------------------------------------
# 4. SERVICE CLIENT
# ---------------------------------------------------------------------------


class ComplianceResultTests(SimpleTestCase):
    def _result(self):
        return ComplianceResult(
            summary={"violations": 2, "needs_attention": True},
            report={
                "findings": [
                    {"rule_id": "a", "status": "violation"},
                    {"rule_id": "b", "status": "violation"},
                    {"rule_id": "c", "status": "requires_judgment"},
                    {"rule_id": "d", "status": "insufficient_record"},
                    {"rule_id": "e", "status": "compliant"},
                ]
            },
            text="report",
        )

    def test_partitions_findings_by_status(self):
        result = self._result()
        self.assertEqual(len(result.violations), 2)
        self.assertEqual(len(result.requires_judgment), 1)
        self.assertEqual(len(result.insufficient_record), 1)

    def test_insufficient_record_is_not_counted_as_a_violation(self):
        result = self._result()
        ids = {f["rule_id"] for f in result.violations}
        self.assertNotIn("d", ids)

    def test_needs_attention_reads_the_summary(self):
        self.assertTrue(self._result().needs_attention)


class ForeclosureClientTests(SimpleTestCase):
    def _response(self, status_code=200, json_body=None, text=""):
        response = MagicMock(spec=requests.Response)
        response.status_code = status_code
        response.ok = 200 <= status_code < 300
        response.text = text
        if json_body is None:
            response.json.side_effect = ValueError("no json")
        else:
            response.json.return_value = json_body
        return response

    @patch("opencontractserver.foreclosure.client.requests.get")
    def test_health_returns_ruleset_identity(self, mock_get):
        mock_get.return_value = self._response(
            json_body={
                "status": "ok",
                "jurisdiction": "US-CA",
                "rule_count": 11,
                "attorney_verified_count": 0,
            }
        )
        health = ForeclosureComplianceClient("http://svc").health()
        self.assertEqual(health["jurisdiction"], "US-CA")
        self.assertEqual(health["attorney_verified_count"], 0)

    @patch("opencontractserver.foreclosure.client.requests.post")
    def test_evaluate_shapes_the_result(self, mock_post):
        mock_post.return_value = self._response(
            json_body={
                "summary": {"violations": 1, "needs_attention": True},
                "report": {"findings": [{"rule_id": "x", "status": "violation"}]},
                "text": "REPORT",
            }
        )
        result = ForeclosureComplianceClient("http://svc").evaluate({"matter_id": "m"})
        self.assertEqual(len(result.violations), 1)
        self.assertEqual(result.text, "REPORT")

    @patch("opencontractserver.foreclosure.client.requests.post")
    def test_service_rejection_carries_the_reason(self, mock_post):
        mock_post.return_value = self._response(
            status_code=400,
            json_body={"error": "invalid_matter", "detail": "matter_id must not be empty"},
        )
        with self.assertRaises(ForeclosureServiceError) as ctx:
            ForeclosureComplianceClient("http://svc").evaluate({"matter_id": ""})
        self.assertIn("matter_id", str(ctx.exception))

    @patch("opencontractserver.foreclosure.client.requests.post")
    def test_unreachable_service_raises_rather_than_returning_empty(self, mock_post):
        # The failure mode that matters: a compliance analyzer must never report
        # "no violations" because it could not reach its ruleset.
        mock_post.side_effect = requests.ConnectionError("connection refused")
        with self.assertRaises(ForeclosureServiceError) as ctx:
            ForeclosureComplianceClient("http://svc").evaluate({"matter_id": "m"})
        self.assertIn("could not reach", str(ctx.exception))

    @patch("opencontractserver.foreclosure.client.requests.post")
    def test_server_error_is_surfaced(self, mock_post):
        mock_post.return_value = self._response(status_code=503, text="unavailable")
        with self.assertRaises(ForeclosureServiceError):
            ForeclosureComplianceClient("http://svc").evaluate({"matter_id": "m"})

    @patch("opencontractserver.foreclosure.client.requests.post")
    def test_malformed_success_response_is_an_error(self, mock_post):
        mock_post.return_value = self._response(json_body={"unexpected": True})
        with self.assertRaises(ForeclosureServiceError):
            ForeclosureComplianceClient("http://svc").evaluate({"matter_id": "m"})

    @patch("opencontractserver.foreclosure.client.requests.get")
    def test_base_url_trailing_slash_is_normalised(self, mock_get):
        mock_get.return_value = self._response(json_body={"status": "ok"})
        ForeclosureComplianceClient("http://svc/").health()
        self.assertEqual(mock_get.call_args[0][0], "http://svc/health")
