"""Preparation recovery with real SQLite/files and mocked services; no target DB."""

import json
import os
import sqlite3
import stat
import sys
from collections import Counter
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from unittest.mock import Mock, patch

import requests
from django.test import SimpleTestCase

from scripts.remote_ingest import checkpoints as cp
from scripts.remote_ingest import oc_remote_ingest as cli

sys.path.insert(0, str(Path(cli.__file__).parent))
from enrichers import Enrichment, label_def, metadata_field  # noqa: E402


class CountingParser:
    default_embedder_path = "test.Embedder"

    def __init__(self, counts):
        self.counts = counts
        self.settings = {"model": "parser-v1", "credential": "parser-private-key"}
        self.hook = lambda: None

    def ensure_ready(self):
        return self

    def source_mime(self, source, *, filename):
        return "text/plain"

    def identity(self, mime):
        return {
            "class_path": "test.Parser",
            "parser_name": "Fixture parser",
            "parser_version": "1.0",
            "settings": self.settings,
        }

    def parse(self, source, *, filename):
        self.counts["parse"] += 1
        self.hook()
        text = source.decode()
        # Deliberately different on every actual parse, like generated parser IDs.
        child = f"child-{self.counts['parse']}"
        return {
            "content": text,
            "file_type": "text/plain",
            "page_count": 1,
            "pawls_file_content": [],
            "labelled_text": [
                {
                    "id": aid,
                    "parent_id": None if aid == 0 else 0,
                    "annotationLabel": "Paragraph",
                    "annotation_json": {"start": 0, "end": len(text)},
                    "rawText": text,
                    "structural": True,
                }
                for aid in (0, child)
            ],
            "relationships": [
                {
                    "relationshipLabel": "contains",
                    "source_annotation_ids": [0],
                    "target_annotation_ids": [child],
                }
            ],
            "parser_extension": {"must_survive": True},
        }


class CheckpointTests(SimpleTestCase):
    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.source = self.root / "source.txt"
        self.source.write_text("Hello checkpoint")
        self.cfg = cli.Config(
            target_url="https://target.invalid",
            worker_token="worker-private-key",
            corpus_id=None,
            root_dir=tmp.name,
            ledger_path=str(self.root / "ledger.sqlite3"),
            extensions=(".txt",),
            max_workers=1,
            max_attempts=5,
            queue_high=0,
            queue_low=0,
            embeddings=True,
            target_folder_from_tree=True,
            verify_tls=True,
            limit=0,
            enrichers=["fixture:enrich"],
            enricher_identity="config-v1",
            embedding_identity="model-v1",
            ledger_page_size=2,
        )
        self.counts: Counter[str] = Counter()
        self.payloads = []
        self.ledger = cli.Ledger(self.cfg.ledger_path)
        self.plan()
        self.parser = CountingParser(self.counts)
        self.enrich_hook = lambda: None

        def enrich(ctx):
            self.counts["enrich"] += 1
            self.enrich_hook()
            return Enrichment(
                title="Enriched title",
                description="Enriched description",
                annotations=[
                    {
                        "parent_id": 0,
                        "annotationLabel": "Extra",
                        "rawText": ctx.content,
                        "annotation_type": "SPAN_LABEL",
                        "annotation_json": {"start": 0, "end": len(ctx.content)},
                    }
                ],
                annotation_labels={
                    "Extra": label_def("Extra", "SPAN_LABEL", color="blue")
                },
                custom_meta={"retained": [1, "two"]},
                metadata=[metadata_field("Category", "fixture")],
            )

        self.enrichers = [("fixture:enrich", enrich)]
        self.embedding_dimension = 384
        self.embed_hook = lambda: None
        self.upload_hook = lambda: None
        self.upload_error = None
        self.lookup_result: dict | Exception | None = cli.StatusPollError(
            "Lookup unavailable"
        )

    def plan(self):
        self.ledger.upsert_doc(
            "folder/source.txt",
            str(self.source),
            self.source.stat().st_size,
            cli._sha256(str(self.source)),
            1,
        )

    def row(self):
        return self.ledger.get_doc("folder/source.txt")

    def cache(self):
        return cp.Checkpoints(self.cfg.ledger_path, "folder/source.txt")

    def run_worker(self):
        # New HTTP clients and ledger connections on each invocation simulate restart.
        embedder = cli.EmbedderClient(
            "https://embedder.invalid",
            "embed-private-key",
            10,
            dimension=self.embedding_dimension,
            identity=self.cfg.embedding_identity,
        )
        client = cli.TargetClient(self.cfg)

        def embed_post(url, *, json, **kwargs):
            self.embed_hook()
            vector = [0.25] * self.embedding_dimension
            if url.endswith("/batch"):
                return Mock(
                    json=lambda: {"embeddings": [[vector] for _ in json["texts"]]}
                )
            self.counts["embed"] += 1
            return Mock(json=lambda: {"embeddings": [vector]})

        def upload_post(url, *, files=None, data=None, **kwargs):
            if url.endswith("/retry/"):
                self.counts["retry"] += 1
                return Mock(status_code=202, json=lambda: {"upload_id": "receipt-1"})
            self.counts["upload"] += 1
            self.payloads.append(
                (files["file"][1].read(), json.loads(data["metadata"]))
            )
            self.upload_hook()
            if self.upload_error:
                raise self.upload_error
            return Mock(status_code=202, json=lambda: {"upload_id": "receipt-1"})

        def lookup(key):
            if isinstance(self.lookup_result, Exception):
                raise self.lookup_result
            return self.lookup_result

        with (
            patch.object(cli, "_Parser", return_value=self.parser),
            patch("enrichers.load_enrichers", return_value=self.enrichers),
            patch.object(cli, "EmbedderClient", return_value=embedder),
            patch.object(cli, "TargetClient", return_value=client),
            patch.object(embedder.session, "post", side_effect=embed_post),
            patch.object(client.session, "post", side_effect=upload_post),
            patch.object(
                client,
                "lookup_upload",
                side_effect=lookup,
            ),
            patch.object(cli, "_print_status"),
        ):
            return cli.cmd_run(self.cfg)

    def start_independent_preparation_trial(self):
        # These tests inspect cache invalidation across independent preparation
        # trials. Discard the fixture receipt so server retry does not bypass it.
        self.ledger._conn().execute(
            "UPDATE docs SET status='PENDING', upload_id=NULL, client_key=NULL, upload_digest=NULL"
        )

    def assert_payload(self):
        source, payload = self.payloads[-1]
        self.assertEqual(source.decode(), payload["content"])
        self.assertEqual(payload["title"], "Enriched title")
        self.assertEqual(payload["custom_meta"], {"retained": [1, "two"]})
        self.assertEqual(payload["metadata"][0]["column_name"], "Category")
        self.assertEqual(payload["text_labels"]["Extra"]["color"], "blue")
        self.assertEqual(payload["labelled_text"][2]["id"], "enr-0")
        self.assertEqual(payload["labelled_text"][2]["parent_id"], 0)
        self.assertEqual(payload["relationships"][0]["source_annotation_ids"], [0])
        self.assertEqual(
            set(payload["embeddings"]["annotation_embeddings"]),
            {"0", "child-1", "enr-0"},
        )
        entry = self.cache().manifest["stages"]["enrich"]
        export = json.loads(
            (self.cache().path / (entry["digest"] + ".json")).read_bytes()
        )["export"]
        self.assertEqual(export["parser_extension"], {"must_survive": True})

    def test_success_persists_one_receipt_with_the_confirmation_timestamp(self):
        mark_uploaded = cli.Ledger.mark_uploaded
        confirmations = []

        def record(ledger, rel_path, upload_id, page_count, now):
            confirmations.append(now)
            mark_uploaded(ledger, rel_path, upload_id, page_count, now)

        with patch.object(cli.Ledger, "mark_uploaded", record):
            self.assertEqual(self.run_worker(), 0)
        self.assertEqual(len(confirmations), 1)
        self.assertEqual(self.row()["uploaded_at"], confirmations[0])
        self.assertEqual(self.row()["upload_id"], "receipt-1")

    def test_restart_at_each_durable_boundary_reuses_stages_and_exact_payload(self):
        self.assertEqual(self.run_worker(), 0)
        uninterrupted = deepcopy(self.payloads[-1])
        for boundary in cp.STAGES:
            with self.subTest(boundary=boundary):
                self.cfg = replace(
                    self.cfg, ledger_path=str(self.root / (boundary + ".sqlite3"))
                )
                self.ledger = cli.Ledger(self.cfg.ledger_path)
                self.plan()
                self.counts.clear()
                self.payloads.clear()
                stage = cp.Checkpoints.stage

                def interrupt(cache, name, *args):
                    result = stage(cache, name, *args)
                    if name == boundary:
                        raise RuntimeError("process interrupted after durable stage")
                    return result

                with patch.object(cp.Checkpoints, "stage", interrupt):
                    self.assertEqual(self.run_worker(), 1)
                self.assertEqual(self.row()["status"], cli.FAILED)
                self.assertEqual(self.run_worker(), 0)
                self.assertEqual([self.counts[s] for s in cp.STAGES], [1, 1, 1])
                self.assert_payload()
                self.assertEqual(self.payloads[-1], uninterrupted)
                first = deepcopy(self.payloads[-1])
                self.start_independent_preparation_trial()
                self.assertEqual(self.run_worker(), 0)
                self.assertEqual(first, self.payloads[-1])
                self.assertEqual([self.counts[s] for s in cp.STAGES], [1, 1, 1])

    def test_upload_rejection_reuses_all_preparation(self):
        self.upload_error = cli.PermanentUploadError("HTTP 400")
        self.assertEqual(self.run_worker(), 1)
        self.assertEqual(self.row()["status"], cli.FAILED)
        self.upload_error = None
        self.assertEqual(self.run_worker(), 0)
        self.assertEqual(self.payloads[0], self.payloads[1])
        self.assertEqual([self.counts[s] for s in cp.STAGES], [1, 1, 1])

    def test_configuration_changes_invalidate_only_affected_stages(self):
        self.assertEqual(self.run_worker(), 0)
        for change, expected in [
            (
                lambda: setattr(
                    self, "cfg", replace(self.cfg, embedding_identity="model-v2")
                ),
                [1, 1, 2],
            ),
            (lambda: setattr(self, "embedding_dimension", 768), [1, 1, 3]),
            (
                lambda: setattr(
                    self, "cfg", replace(self.cfg, enricher_identity="config-v2")
                ),
                [1, 2, 4],
            ),
            (lambda: self.parser.settings.update(model="parser-v2"), [2, 3, 5]),
        ]:
            self.start_independent_preparation_trial()
            change()
            self.assertEqual(self.run_worker(), 0)
            self.assertEqual([self.counts[s] for s in cp.STAGES], expected)
        for path in self.cache().path.iterdir():
            data = path.read_bytes()
            for secret in (
                b"parser-private-key",
                b"worker-private-key",
                b"embed-private-key",
            ):
                self.assertNotIn(secret, data)

    def test_enricher_order_is_part_of_identity(self):
        def other(ctx):
            return Enrichment()

        self.enrichers.append(("fixture:other", other))
        self.assertEqual(self.run_worker(), 0)
        self.start_independent_preparation_trial()
        self.enrichers.reverse()
        self.assertEqual(self.run_worker(), 0)
        self.assertEqual([self.counts[s] for s in cp.STAGES], [1, 2, 2])

    def test_missing_corrupt_and_incompatible_artifacts_are_misses(self):
        for stage in cp.STAGES:
            for damage in ("missing", "truncated", "modified", "key"):
                with self.subTest(stage=stage, damage=damage):
                    if self.row()["status"] == cli.UPLOADED:
                        self.start_independent_preparation_trial()
                    self.assertEqual(self.run_worker(), 0)
                    before = self.counts.copy()
                    cache = self.cache()
                    entry = cache.manifest["stages"][stage]
                    artifact = cache.path / (entry["digest"] + ".json")
                    if damage == "missing":
                        artifact.unlink()
                    elif damage == "truncated":
                        artifact.write_bytes(artifact.read_bytes()[:10])
                    elif damage == "modified":
                        artifact.write_bytes(artifact.read_bytes() + b" ")
                    else:
                        cache.manifest["stages"][stage]["key"] = "0" * 64
                        cache._publish()
                    self.start_independent_preparation_trial()
                    self.assertEqual(self.run_worker(), 0)
                    for name in cp.STAGES:
                        self.assertEqual(
                            self.counts[name] - before[name],
                            int(cp.STAGES.index(name) >= cp.STAGES.index(stage)),
                        )

    def test_invalid_annotation_ids_never_commit_dependent_artifacts(self):
        original = self.parser.parse
        for bad in (None, True, "", "0"):
            with self.subTest(bad=bad):

                def malformed(source, *, filename):
                    export = original(source, filename=filename)
                    export["labelled_text"][1]["id"] = bad
                    return export

                with patch.object(self.parser, "parse", side_effect=malformed):
                    self.assertEqual(self.run_worker(), 1)
                self.assertEqual(self.cache().manifest["stages"], {})
        self.assertFalse(self.payloads)
        self.assertEqual(self.counts["enrich"], 0)
        self.assertEqual(self.counts["embed"], 0)

    def test_changed_unaccepted_source_resets_preparation_retries(self):
        self.upload_error = cli.PermanentUploadError("HTTP 400")
        self.assertEqual(self.run_worker(), 1)
        self.upload_error = None
        self.ledger.mark_failed("folder/source.txt", "server failed", 1)
        self.assertEqual(self.row()["status"], cli.PARKED)
        self.source.write_text("Changed source")
        self.plan()
        row = self.row()
        self.assertEqual(row["status"], cli.PENDING)
        for field in (
            "last_error",
            "upload_id",
            "uploaded_at",
            "completed_at",
            "page_count",
        ):
            self.assertIsNone(row[field])
        self.assertEqual(row["attempts"], 0)
        self.assertEqual(self.run_worker(), 0)
        self.assertEqual([self.counts[s] for s in cp.STAGES], [2, 2, 2])
        self.assertEqual(self.payloads[-1][0], b"Changed source")

    def test_changed_accepted_source_conflicts_and_preserves_receipt(self):
        for status in (cli.UPLOADED, cli.COMPLETED, cli.AMBIGUOUS):
            with self.subTest(status=status):
                self.source.write_text("Hello checkpoint")
                self.plan()
                self.ledger.mark_uploaded("folder/source.txt", "old-receipt", 1, 12)
                self.ledger._conn().execute("UPDATE docs SET status=?", (status,))
                self.source.write_text("Changed source")
                self.plan()
                self.assertEqual(self.row()["status"], cli.CONFLICT)
                self.assertEqual(self.row()["prior_status"], status)
                self.assertEqual(self.row()["upload_id"], "old-receipt")
                self.assertNotEqual(self.row()["sha256"], cli._sha256(str(self.source)))
                self.assertEqual(self.run_worker(), 1)
                self.assertEqual(self.row()["status"], cli.CONFLICT)
        self.assertFalse(self.payloads)

    def test_current_bytes_reconciled_without_replanning(self):
        self.source.write_text("Changed after plan")
        self.assertEqual(self.run_worker(), 0)
        self.assertEqual(self.row()["sha256"], cp.digest(b"Changed after plan"))
        self.assertEqual(self.payloads[-1][0], b"Changed after plan")

    def test_snapshot_survives_source_changes_at_all_stages_and_cached_upload(self):
        for hook in ("parse", "enrich", "embed", "upload"):
            with self.subTest(hook=hook):
                self.cfg = replace(
                    self.cfg, ledger_path=str(self.root / (hook + ".sqlite3"))
                )
                self.ledger = cli.Ledger(self.cfg.ledger_path)
                self.source.write_text("Hello checkpoint")
                self.plan()

                def mutate():
                    self.source.write_text("Concurrent replacement")

                target, field = (
                    (self.parser, "hook") if hook == "parse" else (self, hook + "_hook")
                )
                with patch.object(target, field, mutate):
                    self.assertEqual(self.run_worker(), 0)
                self.assertEqual(
                    self.payloads[-1][0].decode(), self.payloads[-1][1]["content"]
                )
                self.assertEqual(self.payloads[-1][0], b"Hello checkpoint")
                self.assertEqual(self.source.read_text(), "Concurrent replacement")

        # Change the path after a cache hit, before POST. The read snapshot still wins.
        self.source.write_text("Hello checkpoint")
        self.start_independent_preparation_trial()
        before = self.counts.copy()
        stage = cp.Checkpoints.stage

        def mutate_on_hit(cache, name, *args):
            value = stage(cache, name, *args)
            self.source.write_text("Replacement after cache reuse")
            return value

        with patch.object(cp.Checkpoints, "stage", mutate_on_hit):
            self.assertEqual(self.run_worker(), 0)
        self.assertEqual(self.payloads[-1][0], b"Hello checkpoint")
        for name in cp.STAGES:
            self.assertEqual(self.counts[name], before[name])

    def test_accepted_response_lost_and_crash_before_post_are_unclaimable(self):
        self.upload_error = requests.ReadTimeout("accepted but response lost")
        self.assertEqual(self.run_worker(), 1)
        self.assertEqual(self.row()["status"], cli.AMBIGUOUS)
        self.assertIsNone(self.row()["upload_id"])
        self.assertIn("response lost", self.row()["last_error"])
        self.assertEqual(self.counts["upload"], 1)
        self.upload_error = None
        self.assertEqual(self.run_worker(), 1)
        self.assertEqual(self.counts["upload"], 1)
        self.assertEqual(set(self.cache().manifest["stages"]), set(cp.STAGES))
        with patch.object(cli, "_print_status"), patch.object(cli, "TargetClient"):
            self.assertEqual(cli.cmd_verify(self.cfg), cli.VERIFY_UNAVAILABLE)

    def test_lost_response_is_recovered_on_restart_without_repeating_successful_preparation(
        self,
    ):
        self.upload_error = requests.ReadTimeout("response lost")
        self.assertEqual(self.run_worker(), 1)
        original = dict(self.row())
        self.assertTrue(original["client_key"])
        self.assertEqual(len(original["upload_digest"]), 64)
        self.lookup_result = {
            "upload_id": "receipt-1",
            "status": "COMPLETED",
            "payload_digest": original["upload_digest"],
        }
        self.source.unlink()  # Reconciliation does not need local preparation.
        self.assertEqual(self.run_worker(), 0)
        self.assertEqual(self.row()["status"], cli.COMPLETED)
        self.assertEqual(self.row()["client_key"], original["client_key"])
        self.assertEqual([self.counts[s] for s in (*cp.STAGES, "upload")], [1, 1, 1, 1])

    def test_explicit_lookup_absence_reuses_key_and_cached_preparation_after_crash_before_post(
        self,
    ):
        mark = cli.Ledger.mark_upload_started

        def crash(ledger, rel, *args):
            mark(ledger, rel, *args)
            raise RuntimeError("crash before POST")

        with patch.object(cli.Ledger, "mark_upload_started", crash):
            self.assertEqual(self.run_worker(), 1)
        original_key = self.row()["client_key"]
        self.lookup_result = None
        self.assertEqual(self.run_worker(), 0)
        self.assertEqual(self.row()["client_key"], original_key)
        self.assertEqual([self.counts[s] for s in (*cp.STAGES, "upload")], [1, 1, 1, 1])

    def test_server_failure_retries_original_receipt_without_local_source_or_preparation(
        self,
    ):
        self.assertEqual(self.run_worker(), 0)
        self.ledger.mark_failed("folder/source.txt", "server rolled back", 5)
        self.source.unlink()
        self.assertEqual(self.run_worker(), 0)
        self.assertEqual(self.counts["retry"], 1)
        self.assertEqual(self.row()["upload_id"], "receipt-1")
        self.assertEqual([self.counts[s] for s in (*cp.STAGES, "upload")], [1, 1, 1, 1])

    def test_lookup_payload_mismatch_keeps_receipt_ambiguous_and_never_reposts(self):
        self.upload_error = requests.ReadTimeout("response lost")
        self.assertEqual(self.run_worker(), 1)
        self.lookup_result = {
            "upload_id": "other",
            "status": "COMPLETED",
            "payload_digest": "wrong",
        }
        self.assertEqual(self.run_worker(), 1)
        self.assertEqual(self.row()["status"], cli.AMBIGUOUS)
        self.assertEqual(self.counts["upload"], 1)

    def test_lost_response_followed_by_failed_processing_recovers_and_retries_the_receipt(
        self,
    ):
        self.upload_error = requests.ReadTimeout("response lost")
        self.assertEqual(self.run_worker(), 1)
        self.lookup_result = {
            "upload_id": "receipt-1",
            "status": "FAILED",
            "error_message": "temporary dependency",
            "payload_digest": self.row()["upload_digest"],
        }
        self.source.unlink()
        self.assertEqual(self.run_worker(), 0)
        self.assertEqual(self.row()["status"], cli.UPLOADED)
        self.assertEqual(self.row()["upload_id"], "receipt-1")
        self.assertEqual(self.counts["retry"], 1)
        self.assertEqual([self.counts[s] for s in (*cp.STAGES, "upload")], [1, 1, 1, 1])

    def test_lookup_404_is_unavailable_not_proof_that_submission_was_rejected(self):
        client = cli.TargetClient(self.cfg)
        with patch.object(client.session, "get", return_value=Mock(status_code=404)):
            with self.assertRaises(cli.StatusPollError):
                client.lookup_upload("durable-key")

    def test_changed_source_stays_conflicted_after_lookup_absence_while_old_post_might_be_in_flight(
        self,
    ):
        self.upload_error = requests.ReadTimeout("response lost")
        self.assertEqual(self.run_worker(), 1)
        original_key = self.row()["client_key"]
        self.lookup_result = None
        self.source.write_text("New bytes while original request could still commit")
        self.assertEqual(self.run_worker(), 1)
        self.assertEqual(self.row()["status"], cli.CONFLICT)
        self.assertEqual(self.row()["client_key"], original_key)
        self.assertEqual(self.counts["upload"], 1)

    def test_missing_source_is_retryable_and_never_uploads_cached_payload(self):
        self.assertEqual(self.run_worker(), 0)
        self.start_independent_preparation_trial()
        self.source.unlink()
        self.assertEqual(self.run_worker(), 1)
        self.assertEqual(self.row()["status"], cli.FAILED)
        self.assertEqual(self.counts["upload"], 1)

    def test_no_embeddings_explicitly_omits_payload(self):
        self.cfg = replace(self.cfg, embeddings=False)
        self.assertEqual(self.run_worker(), 0)
        self.assertNotIn("embeddings", self.payloads[-1][1])
        self.assertNotIn("embed", self.cache().manifest["stages"])

    def test_crash_after_upload_intent_before_post_is_conservatively_ambiguous(self):
        mark = cli.Ledger.mark_upload_started

        def crash(ledger, rel, *args):
            mark(ledger, rel, *args)
            raise RuntimeError("process stopped before HTTP")

        with patch.object(cli.Ledger, "mark_upload_started", crash):
            self.assertEqual(self.run_worker(), 1)
        self.assertEqual(self.row()["status"], cli.AMBIGUOUS)
        self.assertEqual(self.run_worker(), 1)
        self.assertEqual(self.counts["upload"], 0)

    def test_semantically_invalid_artifacts_with_matching_digests_recompute(self):
        self.assertEqual(self.run_worker(), 0)
        for stage in cp.STAGES:
            cache = self.cache()
            entry = cache.manifest["stages"][stage]
            artifact = json.loads(
                (cache.path / (entry["digest"] + ".json")).read_bytes()
            )
            if stage == "embed":
                artifact["annotation_embeddings"].pop("enr-0")
            else:
                export = artifact if stage == "parse" else artifact["export"]
                export["labelled_text"][1]["parent_id"] = "missing"
            data = cp.json_bytes(artifact)
            entry["digest"] = cp.digest(data)
            (cache.path / (entry["digest"] + ".json")).write_bytes(data)
            cache._publish()
            before = self.counts.copy()
            self.start_independent_preparation_trial()
            self.assertEqual(self.run_worker(), 0)
            for name in cp.STAGES:
                self.assertEqual(
                    self.counts[name] - before[name],
                    int(cp.STAGES.index(name) >= cp.STAGES.index(stage)),
                )

    def test_legacy_ledger_migrates_in_place_and_runs_uncached(self):
        legacy_path = str(self.root / "legacy.sqlite3")
        with sqlite3.connect(legacy_path) as connection:
            connection.execute(
                "CREATE TABLE docs (rel_path TEXT PRIMARY KEY, abs_path TEXT NOT NULL, "
                "size INTEGER, sha256 TEXT, status TEXT NOT NULL DEFAULT 'PENDING', "
                "upload_id TEXT, attempts INTEGER NOT NULL DEFAULT 0, page_count INTEGER, "
                "last_error TEXT, created_at REAL, uploaded_at REAL, completed_at REAL)"
            )
            connection.execute(
                "INSERT INTO docs(rel_path, abs_path, status) VALUES(?, ?, 'FAILED')",
                ("folder/source.txt", str(self.source)),
            )
        self.cfg = replace(self.cfg, ledger_path=legacy_path)
        self.ledger = cli.Ledger(legacy_path)
        self.assertEqual(self.row()["status"], cli.FAILED)
        self.assertEqual(self.run_worker(), 0)
        self.assertEqual([self.counts[s] for s in cp.STAGES], [1, 1, 1])
        self.assertEqual(self.row()["upload_id"], "receipt-1")

    def test_partial_embedding_response_is_not_cached_or_uploaded(self):
        with patch.object(cli.EmbedderClient, "embed_batch", return_value=[]):
            self.assertEqual(self.run_worker(), 1)
        self.assertEqual(set(self.cache().manifest["stages"]), {"parse", "enrich"})
        self.assertEqual(self.row()["status"], cli.FAILED)
        self.assertEqual(self.run_worker(), 0)
        self.assertEqual([self.counts[s] for s in cp.STAGES], [1, 1, 2])
        self.assertEqual(self.counts["upload"], 1)

    def test_missing_document_vector_retries_then_parks_without_fallback(self):
        self.cfg = replace(self.cfg, max_attempts=2)
        with patch.object(cli.EmbedderClient, "embed_text", return_value=None):
            for status in (cli.FAILED, cli.PARKED):
                self.assertEqual(self.run_worker(), 1)
                self.assertEqual(self.row()["status"], status)
                self.assertIn("Document embedding", self.row()["last_error"])
                self.assertEqual(
                    set(self.cache().manifest["stages"]), {"parse", "enrich"}
                )
        self.assertEqual(self.counts["upload"], 0)
        self.assertFalse(self.payloads)

    def test_unsupported_embedding_dimension_fails_before_preparation(self):
        self.cfg = replace(self.cfg, embedding_dimension=3)
        with self.assertRaisesRegex(ValueError, "not supported by server storage"):
            self.run_worker()
        self.assertEqual(self.counts["parse"], 0)
        self.assertFalse(self.payloads)


class LedgerPermissionsTests(SimpleTestCase):
    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = str(Path(tmp.name) / "ledger.sqlite3")

    def assert_private(self):
        for suffix in ("", "-wal", "-shm"):
            self.assertEqual(stat.S_IMODE(os.stat(self.path + suffix).st_mode), 0o600)

    def test_new_ledger_is_private_before_sqlite_opens_under_permissive_umask(self):
        connect = sqlite3.connect

        def check_before_connect(*args, **kwargs):
            self.assertEqual(stat.S_IMODE(os.stat(self.path).st_mode), 0o600)
            return connect(*args, **kwargs)

        previous_umask = os.umask(0)
        try:
            with patch.object(cli.sqlite3, "connect", side_effect=check_before_connect):
                ledger = cli.Ledger(self.path)
            self.addCleanup(ledger._conn().close)
            ledger.set_meta("example", "private data")
            self.assert_private()
        finally:
            os.umask(previous_umask)

    def test_existing_ledger_and_recovery_files_are_hardened_without_data_loss(self):
        legacy = sqlite3.connect(self.path)
        self.addCleanup(legacy.close)
        legacy.execute("PRAGMA journal_mode=WAL")
        legacy.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")
        legacy.execute("INSERT INTO meta VALUES('example', 'preserved')")
        legacy.commit()
        for suffix in ("", "-wal", "-shm"):
            os.chmod(self.path + suffix, 0o666)
        ledger = cli.Ledger(self.path)
        self.addCleanup(ledger._conn().close)
        self.assertEqual(ledger.get_meta("example"), "preserved")
        self.assert_private()


class ArtifactStorageTests(SimpleTestCase):
    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.ledger_path = str(Path(tmp.name) / "ledger.sqlite3")

    def test_interrupted_artifact_or_manifest_write_never_publishes_partial_stage(self):
        for boundary in ("artifact", "manifest"):
            with self.subTest(boundary=boundary):
                cache = cp.Checkpoints(self.ledger_path, boundary)
                write = cp._atomic_write
                prepare = Mock(return_value={"complete": True})

                def validate(value):
                    self.assertEqual(value, {"complete": True})

                def interrupt(path, data):
                    if (
                        boundary == "artifact"
                        and path.name != "manifest.json"
                        or boundary == "manifest"
                        and b'"parse"' in data
                    ):
                        raise OSError("interrupted write")
                    write(path, data)

                with patch.object(cp, "_atomic_write", interrupt):
                    with self.assertRaises(OSError):
                        cache.stage("parse", "source", prepare, validate)
                restarted = cp.Checkpoints(self.ledger_path, boundary)
                self.assertEqual(restarted.manifest["stages"], {})
                self.assertEqual(
                    restarted.stage("parse", "source", prepare, validate)[0],
                    {"complete": True},
                )
                self.assertEqual(prepare.call_count, 2)

    def test_atomic_write_leaves_old_artifact_intact_on_replace_failure(self):
        path = Path(self.ledger_path)
        path.write_bytes(b"old complete artifact")
        with patch.object(cp.os, "replace", side_effect=OSError("interrupted")):
            with self.assertRaises(OSError):
                cp._atomic_write(path, b"new artifact")
        self.assertEqual(path.read_bytes(), b"old complete artifact")
        self.assertEqual(list(path.parent.glob(".tmp-*")), [])

    def test_corrupt_manifests_miss_and_cleanup_preserves_unknown_references(self):
        cache = cp.Checkpoints(self.ledger_path, "source")
        cache.stage("parse", "source", lambda: {"value": 1}, lambda v: None)
        referenced = cache.path / (
            cache.manifest["stages"]["parse"]["digest"] + ".json"
        )
        os.utime(referenced, (0, 0))
        for bad in (
            b'{"truncated":',
            b"null",
            b'{"version":0,"stages":{}}',
            b'{"version":1,"stages":{"parse":{"key":"x","digest":"../../file"}}}',
        ):
            with self.subTest(bad=bad):
                cache.manifest_path.write_bytes(bad)
                restarted = cp.Checkpoints(self.ledger_path, "source")
                self.assertEqual(restarted.manifest["stages"], {})
                self.assertEqual(restarted.prune(), 0)
                self.assertTrue(referenced.exists())
                prepare = Mock(return_value={"value": 1})
                restarted.stage("parse", "source", prepare, lambda v: None)
                prepare.assert_called_once()

    def test_cleanup_keeps_active_artifacts_and_recent_orphans(self):
        cache = cp.Checkpoints(self.ledger_path, "source")
        cache.stage("parse", "source", lambda: {"value": 1}, lambda v: None)
        referenced = cache.path / (
            cache.manifest["stages"]["parse"]["digest"] + ".json"
        )
        orphan = cache.path / ("0" * 64 + ".json")
        temporary = cache.path / ".tmp-interrupted"
        recent = cache.path / ("1" * 64 + ".json")
        for path in (orphan, temporary, recent):
            path.write_text("partial or unreferenced")
        for path in (referenced, orphan, temporary):
            os.utime(path, (0, 0))
        self.assertEqual(cache.prune(), 2)
        self.assertTrue(referenced.exists())
        self.assertTrue(recent.exists())
        self.assertEqual(cache.prune(), 0)


class EmbeddingContractTests(SimpleTestCase):
    def test_single_shapes_and_exact_finite_dimension(self):
        client = cli.EmbedderClient("https://embedder", None, 2, dimension=384)
        vector = [0.5] * 384
        response: Any
        for response in (vector, [vector]):
            self.assertEqual(client._coerce_vector(response), vector)
        for response in (
            None,
            [],
            [vector, vector],
            [None],
            vector[:-1],
            vector + [0.1],
            [True] * 384,
            ["0.5"] * 384,
            [float("nan")] * 384,
            [float("inf")] * 384,
            [float("-inf")] * 384,
            [10**400] * 384,
        ):
            with self.subTest(response=str(response)[:40]), self.assertRaises(
                ValueError
            ):
                client._coerce_vector(response)

    def test_batch_shapes_cardinality_and_per_item_failure(self):
        client = cli.EmbedderClient("https://embedder", None, 2, dimension=384)
        vector = [0.5] * 384
        response: Any
        for response in ([vector, vector], [[vector], [vector]]):
            with patch.object(
                client.session,
                "post",
                return_value=Mock(json=lambda: {"embeddings": response}),
            ):
                self.assertEqual(
                    client.embed_batch(["one", " ", "two"]), [vector, None, vector]
                )
        for response in (
            None,
            [],
            [vector],
            [vector, vector, vector],
            [vector, None],
            [vector, vector[:-1]],
        ):
            with self.subTest(response=str(response)[:40]), patch.object(
                client.session,
                "post",
                return_value=Mock(json=lambda: {"embeddings": response}),
            ), self.assertRaises(ValueError):
                client.embed_batch(["one", "two"])

    def test_required_coverage_and_json_stable_ids(self):
        embedder = Mock(dimension=384)
        embedder.embed_text.return_value = [0.5] * 384
        embedder.embed_batch.return_value = [[0.5] * 384]
        annotations = [{"id": 0, "rawText": "one"}, {"id": "blank", "rawText": " "}]
        payload = cli._compute_embeddings(
            embedder=embedder,
            embedder_path="test",
            content="one",
            labelled_text=annotations,
        )
        self.assertEqual(set(payload["annotation_embeddings"]), {"0"})
        for bad_id in (None, "", True, "0", 0):
            with self.subTest(bad_id=bad_id), self.assertRaises(ValueError):
                cli._embedding_ids(annotations + [{"id": bad_id, "rawText": "two"}])
        embedder.embed_text.return_value = None
        with self.assertRaisesRegex(ValueError, "finite numeric"):
            cli._compute_embeddings(
                embedder=embedder,
                embedder_path="test",
                content="one",
                labelled_text=annotations,
            )

    def test_http_response_envelopes_and_mixed_dimensions_fail(self):
        client = cli.EmbedderClient("https://embedder", None, 2, dimension=384)
        body: Any
        for body in (
            None,
            [],
            {},
            {"vectors": [0.1] * 384},
            {"embeddings": [[0.1] * 384, [0.1] * 768]},
        ):
            with self.subTest(body=str(body)[:40]), patch.object(
                client.session, "post", return_value=Mock(json=lambda: body)
            ):
                for call in (
                    lambda: client.embed_text("document"),
                    lambda: client.embed_batch(["one", "two"]),
                ):
                    with self.assertRaises(ValueError):
                        call()

    def test_partial_missing_and_unmapped_annotation_vectors_fail(self):
        embedder = Mock(dimension=384)
        vector = [0.5] * 384
        embedder.embed_text.return_value = vector
        annotations = [{"id": "a", "rawText": "one"}, {"id": "b", "rawText": "two"}]
        for rows in ([vector], [vector, None], [vector, vector, vector]):
            embedder.embed_batch.return_value = rows
            with self.assertRaises(ValueError):
                cli._compute_embeddings(
                    embedder=embedder,
                    embedder_path="test",
                    content="document",
                    labelled_text=annotations,
                )
        with self.assertRaisesRegex(ValueError, "coverage"):
            cli._validate_embeddings(
                {
                    "embedder_path": "test",
                    "document_embedding": vector,
                    "annotation_embeddings": {"a": vector, "unmapped": vector},
                },
                annotations,
                384,
                "test",
            )


class UploadReplayTests(SimpleTestCase):
    def setUp(self):
        self.target_client = cli.TargetClient(
            Mock(
                target_url="https://target",
                worker_token="private",
                verify_tls=True,
            )
        )
        self.metadata = {"file_type": "text/plain"}

    def upload(self):
        return self.target_client.upload(
            b"snapshot", self.metadata, filename="source.txt"
        )

    def test_only_explicit_rate_limit_rejection_is_retried(self):
        captured = []
        responses = iter(
            [
                Mock(status_code=429, headers={"Retry-After": "0"}),
                Mock(status_code=202, json=lambda: {"upload_id": "receipt"}),
            ]
        )

        def post(*args, files, **kwargs):
            captured.append(files["file"][1].read())
            self.assertFalse(kwargs["allow_redirects"])
            return next(responses)

        with patch.object(self.target_client.session, "post", side_effect=post):
            self.assertEqual(self.upload(), "receipt")
        self.assertEqual(captured, [b"snapshot", b"snapshot"])

    def test_uncertain_responses_never_replay_post(self):
        for status in (200, 301, 307, 500, 502, 503):
            with self.subTest(status=status), patch.object(
                self.target_client.session,
                "post",
                return_value=Mock(status_code=status),
            ) as post, self.assertRaises(cli.AmbiguousUploadError):
                self.upload()
            self.assertEqual(post.call_count, 1)
        body: Any
        for body in ({}, {"upload_id": None}, {"upload_id": ""}, [], None):
            with self.subTest(body=body), patch.object(
                self.target_client.session,
                "post",
                return_value=Mock(status_code=202, json=lambda: body),
            ) as post, self.assertRaises(cli.AmbiguousUploadError):
                self.upload()
            self.assertEqual(post.call_count, 1)

    def test_transport_failures_are_ambiguous_and_rejections_remain_retryable(self):
        for error in (
            requests.ReadTimeout("secret"),
            requests.ConnectionError("secret"),
        ):
            with patch.object(
                self.target_client.session, "post", side_effect=error
            ) as post:
                with self.assertRaises(cli.AmbiguousUploadError) as caught:
                    self.upload()
                self.assertNotIn("secret", str(caught.exception))
                self.assertEqual(post.call_count, 1)
        for status in (400, 401, 403, 413):
            with patch.object(
                self.target_client.session,
                "post",
                return_value=Mock(status_code=status),
            ) as post:
                with self.assertRaises(cli.PermanentUploadError):
                    self.upload()
                self.assertEqual(post.call_count, 1)
