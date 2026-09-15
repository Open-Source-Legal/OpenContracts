"""Run controls preserve local identity, checkpoints, and monetary precision."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import cast
from unittest.mock import Mock, patch
from uuid import uuid4

from django.test import SimpleTestCase

from opencontractserver.tests.test_remote_ingest_checkpoints import CountingParser
from scripts.remote_ingest import oc_remote_ingest as cli
from scripts.remote_ingest.checkpoints import Checkpoints


class RunParser(CountingParser):
    identities: dict


class RemoteIngestionRunTests(SimpleTestCase):
    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.cfg = cli.Config(
            target_url="https://target.invalid",
            worker_token="private-worker-token",
            corpus_id=None,
            root_dir=tmp.name,
            ledger_path=str(self.root / "ledger.sqlite3"),
            extensions=(".txt",),
            max_workers=1,
            max_attempts=3,
            queue_high=0,
            queue_low=0,
            embeddings=False,
            target_folder_from_tree=True,
            verify_tls=True,
            limit=0,
            enrichers=[],
            ingestion_run_id=str(uuid4()),
            run_ceiling_usd="0.000004",
        )
        self.ledger = cli.Ledger(self.cfg.ledger_path)
        self.addCleanup(self.ledger._conn().close)
        self.source = self.root / "source.txt"
        self.source.write_text("Prepared source")
        self.ledger.upsert_doc(
            "source.txt",
            str(self.source),
            self.source.stat().st_size,
            cli._sha256(str(self.source)),
            1,
        )
        self.counts = {"parse": 0}
        self.parser = RunParser(self.counts)
        self.parser.identities = {"text/plain": self.parser.identity("text/plain")}

    def test_budget_pause_preserves_receipt_checkpoint_and_attempt_count(self):
        self.ledger.upsert_doc("accepted.txt", "gone.txt", 1, "hash", 1)
        self.ledger.mark_uploaded("accepted.txt", "durable-receipt", 1, 1)
        cache = Checkpoints(self.cfg.ledger_path, "source.txt")
        cache.stage(
            "parse", ["identity"], lambda: {"prepared": True}, lambda value: None
        )
        before = {p: p.read_bytes() for p in cache.path.iterdir() if p.is_file()}
        self.assertEqual(len(before), 2)  # The manifest and its prepared artifact.
        client = Mock()
        client.ingestion_run_status.return_value = {
            "status": "BUDGET_EXHAUSTED",
            "reserved_usd": "0.000004",
            "accounted_usd": "0",
            "remaining_usd": "0",
        }
        with patch.object(cli, "TargetClient", return_value=client), patch.object(
            cli, "_Parser"
        ) as parser:
            self.assertEqual(cli.cmd_run(self.cfg), 2)
        parser.assert_not_called()
        pending = self.ledger.get_doc("source.txt")
        self.assertEqual((pending["status"], pending["attempts"]), ("PENDING", 0))
        self.assertEqual(
            self.ledger.get_doc("accepted.txt")["upload_id"], "durable-receipt"
        )
        for path, content in before.items():
            self.assertEqual(path.read_bytes(), content)

    def test_creation_and_upload_use_the_same_secret_free_preparation_identity(self):
        preparations = cli._run_preparations(self.cfg, self.parser)
        client = Mock()
        client.upload.return_value = "receipt"
        result = cli._process_one(
            self.cfg,
            cast(cli._Parser, self.parser),
            None,
            client,
            self.ledger.get_doc("source.txt"),
            ledger=self.ledger,
        )
        self.assertTrue(result[1], result)
        metadata = client.upload.call_args.args[1]
        self.assertEqual(
            metadata["preparation_identity"], preparations[0]["fingerprint"]
        )
        self.assertEqual(metadata["ingestion_run_id"], self.cfg.ingestion_run_id)
        self.assertNotIn("parser-private-key", json.dumps(preparations))
        self.assertNotIn("private-worker-token", json.dumps(preparations))

    def test_changed_local_settings_fail_policy_check_before_preparation(self):
        policy = {"preparations": cli._run_preparations(self.cfg, self.parser)}
        self.parser.identities["text/plain"]["settings"] = {"model": "different"}
        with self.assertRaisesRegex(ValueError, "immutable run policy"):
            cli._validate_run_preparations(self.cfg, self.parser, policy)
        self.assertEqual(self.counts["parse"], 0)

    def test_lost_create_response_reuses_persisted_run_identity(self):
        self.cfg.ingestion_run_id = None
        client = Mock()
        client.ingestion_run_request.side_effect = [
            cli.StatusPollError("lost"),
            {"status": "ACTIVE"},
        ]
        with patch.object(cli, "_Parser", return_value=self.parser), patch.object(
            cli, "TargetClient", return_value=client
        ):
            with self.assertRaises(cli.StatusPollError):
                cli.cmd_ingestion_run(self.cfg, "create")
            saved = self.ledger.get_meta("ingestion_run_id")
            self.assertIsNotNone(saved)
            self.cfg.ingestion_run_id = None
            self.assertEqual(cli.cmd_ingestion_run(self.cfg, "create"), 0)
        first, second = client.ingestion_run_request.call_args_list
        self.assertEqual(first.args[0], second.args[0])
        self.assertEqual(second.args[0]["id"], saved)
        self.assertEqual(second.args[0]["ceiling_usd"], "0.000004")

    def test_resume_sends_exact_ceiling_and_keeps_existing_run(self):
        client = Mock()
        client.ingestion_run_request.return_value = {"status": "ACTIVE"}
        with patch.object(cli, "TargetClient", return_value=client):
            cli.cmd_ingestion_run(self.cfg, "resume")
        client.ingestion_run_request.assert_called_once_with(
            {"action": "resume", "ceiling_usd": "0.000004"}
        )

    def test_create_cannot_rebind_a_ledger_to_a_different_run(self):
        original = str(uuid4())
        self.ledger.set_meta("ingestion_run_id", original)
        with patch.object(cli, "TargetClient") as client:
            with self.assertRaisesRegex(ValueError, "different ingestion run"):
                cli.cmd_ingestion_run(self.cfg, "create")
        client.assert_not_called()
        self.assertEqual(self.ledger.get_meta("ingestion_run_id"), original)
