"""Whole-ledger verification and receipt classification, with no Django/database."""

import json
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from unittest.mock import Mock, patch

import requests

from scripts.remote_ingest import oc_remote_ingest as cli


class VerificationTests(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.cfg = cli.Config(
            target_url="https://target.invalid",
            worker_token="private-token",
            corpus_id=None,
            root_dir=tmp.name,
            ledger_path=str(Path(tmp.name) / "ledger.sqlite3"),
            extensions=(".txt",),
            max_workers=1,
            max_attempts=2,
            queue_high=0,
            queue_low=0,
            embeddings=False,
            target_folder_from_tree=False,
            verify_tls=True,
            limit=0,
            enrichers=[],
            ledger_page_size=2,
            json_output=True,
        )
        self.ledger = cli.Ledger(self.cfg.ledger_path)
        self.addCleanup(self.ledger._conn().close)
        self.client = cli.TargetClient(self.cfg)
        self.addCleanup(self.client.session.close)
        patcher = patch.object(self.client.session, "get")
        self.get = patcher.start()
        self.addCleanup(patcher.stop)

    def add(self, path, status, receipt=None):
        self.ledger._conn().execute(
            "INSERT INTO docs(rel_path, abs_path, status, upload_id, attempts, "
            "last_error, uploaded_at) VALUES(?, ?, ?, ?, 1, 'prior diagnostic', 12)",
            (path, f"/source/{path}", status, receipt),
        )

    def response(self, status="COMPLETED", **fields):
        # document_id is not a readiness signal and may be null in the API.
        return Mock(
            status_code=200,
            json=Mock(return_value=dict(upload_id="receipt", status=status, **fields)),
        )

    def verify(self):
        output = StringIO()
        with patch.object(cli, "Ledger", return_value=self.ledger), patch.object(
            cli, "TargetClient", return_value=self.client
        ), redirect_stdout(output):
            code = cli.cmd_verify(self.cfg)
        records = [json.loads(line) for line in output.getvalue().splitlines()]
        summary = records.pop()
        self.assertEqual(summary["type"], "summary")
        self.assertEqual(summary["exit_code"], code)
        self.assertEqual(summary["total"], len(records))
        self.assertEqual(sum(summary["reason_counts"].values()), len(records))
        return code, records, summary

    def test_empty_scope_is_explicit_noop_success_without_http(self):
        code, records, summary = self.verify()
        self.assertEqual((code, records, summary["outcome"]), (0, [], "empty"))
        self.assertEqual(summary["scope"], "whole_ledger")
        self.get.assert_not_called()

    def test_readiness_mode_rechecks_completed_receipts_without_rewriting_ledger(self):
        self.cfg.readiness = True
        self.add("old.txt", cli.COMPLETED, "receipt")
        before = dict(self.ledger.get_doc("old.txt"))
        for state, expected in (("outstanding", 1), ("failed", 2), ("ready", 0)):
            with self.subTest(state=state):
                self.get.return_value = Mock(
                    status_code=200,
                    json=Mock(
                        return_value={
                            "schema_version": 1,
                            "upload_id": "receipt",
                            "state": state,
                            "generation": "a" * 64,
                            "reasons": [],
                        }
                    ),
                )
                code, records, summary = self.verify()
                self.assertEqual(code, expected)
                self.assertEqual(records[0]["readiness"]["state"], state)
                self.assertEqual(summary["completion_boundary"], "search_readiness")
                self.assertEqual(dict(self.ledger.get_doc("old.txt")), before)
        self.assertEqual(self.get.call_count, 3)
        self.assertTrue(
            self.get.call_args.args[0].endswith("/api/readiness/worker/receipt/")
        )

    def test_readiness_unavailable_does_not_turn_completed_receipt_into_failure(self):
        self.cfg.readiness = True
        self.add("old.txt", cli.COMPLETED, "receipt")
        before = dict(self.ledger.get_doc("old.txt"))
        self.get.return_value = Mock(status_code=404)
        code, records, summary = self.verify()
        self.assertEqual(code, cli.VERIFY_UNAVAILABLE)
        self.assertEqual(summary["unavailable"], 1)
        self.assertIsNone(records[0]["readiness"])
        self.assertEqual(dict(self.ledger.get_doc("old.txt")), before)

    def test_readiness_response_requires_matching_receipt_and_generation(self):
        self.cfg.readiness = True
        self.add("old.txt", cli.COMPLETED, "receipt")
        for fields in (
            {"upload_id": "other"},
            {"generation": None},
            {"state": "completed"},
        ):
            with self.subTest(fields=fields):
                self.get.return_value = Mock(
                    status_code=200,
                    json=Mock(
                        return_value={
                            "schema_version": 1,
                            "upload_id": "receipt",
                            "state": "ready",
                            "generation": "a" * 64,
                            **fields,
                        }
                    ),
                )
                self.assertEqual(self.verify()[0], cli.VERIFY_UNAVAILABLE)

    def test_completed_receipt_establishes_only_worker_transaction_completion(self):
        self.add("new.txt", cli.UPLOADED, "receipt")
        self.add("old.txt", cli.COMPLETED, "old-receipt")
        self.get.return_value = self.response(document_id=None)
        code, records, summary = self.verify()
        self.assertEqual(code, 0)
        self.assertEqual(summary["outcome"], "complete")
        self.assertEqual(summary["completion_boundary"], "worker_upload_transaction")
        self.assertEqual(summary["counts"], {cli.COMPLETED: 2})
        self.assertEqual(records[0]["receipt_status"], "COMPLETED")
        self.assertGreater(self.ledger.get_doc("new.txt")["completed_at"], 12)
        self.get.assert_called_once_with(
            "https://target.invalid/api/worker-uploads/documents/receipt/",
            timeout=cli._HTTP_STATUS_TIMEOUT_SECONDS,
            verify=True,
            allow_redirects=False,
        )
        self.get.reset_mock()
        self.assertEqual(self.verify()[0], 0)
        self.get.assert_not_called()

    def test_local_states_remain_unresolved_across_verification_passes(self):
        for status, expected, reason in (
            (cli.PENDING, 1, "not_uploaded"),
            (cli.FAILED, 2, "failed"),
            (cli.PARKED, 2, "parked"),
            (cli.AMBIGUOUS, 2, "ambiguous_upload"),
            (cli.CONFLICT, 2, "source_conflict"),
            ("UNKNOWN", 3, "unknown_ledger_state"),
        ):
            with self.subTest(status=status):
                self.ledger._conn().execute("DELETE FROM docs")
                self.add("source.txt", status, "old-receipt")
                before = dict(self.ledger.get_doc("source.txt"))
                for _ in range(2):
                    code, records, _ = self.verify()
                    self.assertEqual(code, expected)
                    self.assertEqual(records[0]["reason"], reason)
                    self.assertEqual(dict(self.ledger.get_doc("source.txt")), before)
        self.get.assert_not_called()

    def test_server_failure_is_durable_and_keeps_receipt_and_error(self):
        for attempts, expected_status in ((0, cli.FAILED), (1, cli.PARKED)):
            with self.subTest(attempts=attempts):
                self.ledger._conn().execute("DELETE FROM docs")
                self.add("source.txt", cli.UPLOADED, "receipt")
                self.ledger._conn().execute("UPDATE docs SET attempts=?", (attempts,))
                self.get.return_value = self.response(
                    "FAILED", error_message="bad data"
                )
                self.get.reset_mock()
                for _ in range(2):
                    code, records, summary = self.verify()
                    self.assertEqual(code, 2)
                    self.assertEqual(summary["counts"], {expected_status: 1})
                    self.assertEqual(records[0]["upload_id"], "receipt")
                    self.assertEqual(records[0]["detail"], "server: bad data")
                self.get.assert_called_once()
                self.assertEqual(
                    self.ledger.get_doc("source.txt")["attempts"], attempts + 1
                )

    def test_pending_and_processing_receipts_are_outstanding_without_mutation(self):
        self.add("source.txt", cli.UPLOADED, "receipt")
        before = dict(self.ledger.get_doc("source.txt"))
        for status in ("PENDING", "PROCESSING"):
            self.get.return_value = self.response(status)
            code, records, _ = self.verify()
            self.assertEqual(code, 1)
            self.assertEqual(records[0]["reason"], f"receipt_{status.lower()}")
            self.assertEqual(dict(self.ledger.get_doc("source.txt")), before)

    def test_http_errors_are_distinct_safe_and_do_not_mutate_receipts(self):
        self.add("source.txt", cli.UPLOADED, "receipt")
        before = dict(self.ledger.get_doc("source.txt"))
        for http_status, reason in (
            (401, "unauthorized"),
            (403, "forbidden"),
            (404, "not_found"),
            (429, "rate_limited"),
            (500, "server_unavailable"),
            (503, "server_unavailable"),
            (302, "http_error"),
            (422, "http_error"),
        ):
            with self.subTest(http_status=http_status):
                self.get.return_value = Mock(
                    status_code=http_status,
                    headers={"Retry-After": "30"},
                    text="private-token internal server response",
                )
                code, records, summary = self.verify()
                self.assertEqual(code, 3)
                self.assertEqual(summary["unavailable"], 1)
                self.assertEqual(records[0]["reason"], reason)
                self.assertEqual(records[0]["http_status"], http_status)
                self.assertNotIn("private-token", json.dumps(records))
                self.assertEqual(dict(self.ledger.get_doc("source.txt")), before)
                if http_status == 404:
                    self.assertIn("current worker token", records[0]["detail"])

    def test_transport_and_invalid_responses_are_unavailable_without_mutation(self):
        self.add("source.txt", cli.UPLOADED, "receipt")
        before = dict(self.ledger.get_doc("source.txt"))
        for error, reason in (
            (requests.Timeout("private-token"), "network_error"),
            (requests.ConnectionError("private-token"), "network_error"),
            (requests.exceptions.InvalidURL("private-token"), "invalid_request"),
        ):
            self.get.side_effect = error
            code, records, _ = self.verify()
            self.assertEqual(code, 3)
            self.assertEqual(records[0]["reason"], reason)
            self.assertNotIn("private-token", json.dumps(records))
        self.get.side_effect = None
        body: Any
        for body in (
            None,
            [],
            {},
            {"status": "COMPLETED"},
            {"upload_id": "other", "status": "COMPLETED"},
            {"upload_id": "receipt", "status": "mystery"},
            {"upload_id": "receipt", "status": ["FAILED"]},
            {"upload_id": "receipt", "status": "FAILED", "error_message": {}},
        ):
            self.get.return_value = Mock(status_code=200, json=Mock(return_value=body))
            code, records, _ = self.verify()
            self.assertEqual(code, 3)
            self.assertEqual(records[0]["reason"], "invalid_response")
        self.get.return_value.json.side_effect = ValueError("private-token")
        self.assertEqual(self.verify()[0], 3)
        self.assertEqual(dict(self.ledger.get_doc("source.txt")), before)

    def test_mixed_scope_prioritizes_unavailability_then_failure_then_outstanding(self):
        self.add("a.txt", cli.COMPLETED)
        self.add("b.txt", cli.PENDING)
        self.add("c.txt", cli.FAILED)
        self.add("d.txt", cli.UPLOADED)  # Cannot poll a missing receipt.
        code, records, summary = self.verify()
        self.assertEqual(code, 3)
        self.assertEqual(records[-1]["reason"], "missing_receipt")
        self.assertEqual(summary["counts"], self.ledger.status_counts())
        self.ledger._conn().execute("DELETE FROM docs WHERE rel_path='d.txt'")
        self.assertEqual(self.verify()[0], 2)
        self.ledger._conn().execute("DELETE FROM docs WHERE rel_path='c.txt'")
        self.assertEqual(self.verify()[0], 1)
        self.ledger._conn().execute("DELETE FROM docs WHERE rel_path='b.txt'")
        self.assertEqual(self.verify()[0], 0)
        self.get.assert_not_called()

    def test_cli_json_flag_reaches_verify_without_booting_django(self):
        with patch.object(cli, "cmd_verify", return_value=3) as verify:
            self.assertEqual(
                cli.main(
                    [
                        "--target-url",
                        self.cfg.target_url,
                        "--worker-token",
                        "token",
                        "--ledger",
                        self.cfg.ledger_path,
                        "--json",
                        "verify",
                    ]
                ),
                3,
            )
        self.assertTrue(verify.call_args.args[0].json_output)
