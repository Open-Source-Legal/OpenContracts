"""
Unit tests for the bulk-import driver's pure-Python core: file scanning,
deterministic multi-constraint batching, ZIP arcname preservation, and the
SQLite resume ledger. These run without Docker or a live server::

    python -m pytest scripts/bulk_import/tests/test_batching.py
    python scripts/bulk_import/tests/test_batching.py
"""

import hashlib
import os
import sys
import tempfile
import unittest
from io import BytesIO
from zipfile import ZipFile

# The driver lives one directory up and is not a package; add it to the path.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import oc_bulk_import as drv  # noqa: E402  # isort: skip


def _touch(path: str, size: int = 4) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(b"x" * size)


class AncestorDirsTests(unittest.TestCase):
    def test_nested_path_yields_all_ancestors(self):
        self.assertEqual(drv._ancestor_dirs("a/b/c.pdf"), {"a", "a/b"})

    def test_top_level_file_has_no_ancestors(self):
        self.assertEqual(drv._ancestor_dirs("c.pdf"), set())


class ScanTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def test_extension_filter_and_hidden_skip(self):
        _touch(os.path.join(self.tmp, "a.pdf"))
        _touch(os.path.join(self.tmp, "b.txt"))
        _touch(os.path.join(self.tmp, ".hidden.pdf"))
        _touch(os.path.join(self.tmp, ".secret", "c.pdf"))
        entries = drv.scan_files(
            self.tmp,
            {".pdf"},
            drv.DEFAULT_SINGLE_FILE_CAP,
            include_all=False,
            compute_hash=False,
        )
        rels = [e.rel_path for e in entries]
        self.assertEqual(rels, ["a.pdf"])  # txt, hidden file, hidden dir excluded

    def test_relative_posix_paths_and_sorting(self):
        _touch(os.path.join(self.tmp, "z", "2.pdf"))
        _touch(os.path.join(self.tmp, "a", "1.pdf"))
        entries = drv.scan_files(
            self.tmp,
            {".pdf"},
            drv.DEFAULT_SINGLE_FILE_CAP,
            False,
            False,
        )
        self.assertEqual([e.rel_path for e in entries], ["a/1.pdf", "z/2.pdf"])

    def test_oversize_classification(self):
        _touch(os.path.join(self.tmp, "big.pdf"), size=50)
        _touch(os.path.join(self.tmp, "small.pdf"), size=5)
        entries = drv.scan_files(
            self.tmp,
            {".pdf"},
            single_file_cap=20,
            include_all=False,
            compute_hash=False,
        )
        kinds = {e.rel_path: e.kind for e in entries}
        self.assertEqual(kinds["big.pdf"], drv.KIND_OVERSIZE)
        self.assertEqual(kinds["small.pdf"], drv.KIND_ZIP)

    def test_compute_hash_populates_sha256(self):
        path = os.path.join(self.tmp, "a.pdf")
        _touch(path, size=16)
        with_hash = drv.scan_files(
            self.tmp, {".pdf"}, drv.DEFAULT_SINGLE_FILE_CAP, False, compute_hash=True
        )
        self.assertEqual(with_hash[0].sha256, hashlib.sha256(b"x" * 16).hexdigest())
        # ...and stays empty when hashing is off.
        without = drv.scan_files(
            self.tmp, {".pdf"}, drv.DEFAULT_SINGLE_FILE_CAP, False, compute_hash=False
        )
        self.assertEqual(without[0].sha256, "")


class BatchingTests(unittest.TestCase):
    def _entries(self, specs):
        # specs: list of (rel_path, size)
        return [
            drv.FileEntry(rel, f"/abs/{rel}", size, drv.KIND_ZIP) for rel, size in specs
        ]

    def test_respects_file_count_cap(self):
        entries = self._entries([(f"f{i}.pdf", 1) for i in range(10)])
        batches = drv.plan_batches(
            entries, target_files=3, target_bytes=10**9, target_folders=999
        )
        self.assertTrue(all(b.file_count <= 3 for b in batches))
        self.assertEqual(sum(b.file_count for b in batches), 10)

    def test_respects_byte_cap(self):
        entries = self._entries([(f"f{i}.pdf", 100) for i in range(10)])
        batches = drv.plan_batches(
            entries, target_files=999, target_bytes=250, target_folders=999
        )
        self.assertTrue(all(b.byte_size <= 250 for b in batches))

    def test_respects_folder_cap(self):
        # Each file in its own folder -> folder count is the binding constraint.
        entries = self._entries([(f"dir{i}/f.pdf", 1) for i in range(10)])
        batches = drv.plan_batches(
            entries, target_files=999, target_bytes=10**9, target_folders=3
        )
        for b in batches:
            folders = set()
            for m in b.members:
                folders |= drv._ancestor_dirs(m.rel_path)
            self.assertLessEqual(len(folders), 3)

    def test_oversize_is_its_own_batch(self):
        entries = [
            drv.FileEntry("a.pdf", "/abs/a.pdf", 1, drv.KIND_ZIP),
            drv.FileEntry("big.pdf", "/abs/big.pdf", 999, drv.KIND_OVERSIZE),
        ]
        batches = drv.plan_batches(entries, 500, 10**9, 999)
        oversize = [b for b in batches if b.kind == drv.KIND_OVERSIZE]
        self.assertEqual(len(oversize), 1)
        self.assertEqual(oversize[0].file_count, 1)

    def test_deterministic_batch_ids_across_runs(self):
        # scan_files always feeds plan_batches a path-sorted list, so the same
        # tree must reproduce identical batch ids on every run — this is what
        # makes the SQLite ledger resume correctly.
        entries = self._entries([(f"d/{i:02d}.pdf", 1) for i in range(20)])
        first = drv.plan_batches(entries, 5, 10**9, 999)
        again = drv.plan_batches(entries, 5, 10**9, 999)
        self.assertEqual([x.batch_id for x in first], [x.batch_id for x in again])
        # Each id is a stable content hash of its members, not a positional guess.
        self.assertEqual(len({x.batch_id for x in first}), len(first))


class ZipTests(unittest.TestCase):
    def test_arcnames_preserve_relative_tree(self):
        tmp = tempfile.mkdtemp()
        _touch(os.path.join(tmp, "x", "y", "doc.pdf"))
        _touch(os.path.join(tmp, "top.pdf"))
        members = [
            drv.FileEntry(
                "x/y/doc.pdf", os.path.join(tmp, "x", "y", "doc.pdf"), 4, drv.KIND_ZIP
            ),
            drv.FileEntry("top.pdf", os.path.join(tmp, "top.pdf"), 4, drv.KIND_ZIP),
        ]
        stream = drv.build_zip_stream(members)
        self.assertEqual(stream.tell(), 0)  # positioned at 0, ready to stream
        with ZipFile(stream) as zf:
            self.assertEqual(sorted(zf.namelist()), ["top.pdf", "x/y/doc.pdf"])


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.path = os.path.join(tempfile.mkdtemp(), "ledger.db")
        self.ledger = drv.Ledger(self.path)
        self.batch = drv.Batch(
            "abc123",
            drv.KIND_ZIP,
            [
                drv.FileEntry("a/1.pdf", "/abs/a/1.pdf", 10, drv.KIND_ZIP),
                drv.FileEntry("a/2.pdf", "/abs/a/2.pdf", 20, drv.KIND_ZIP),
            ],
        )

    def test_upsert_is_idempotent(self):
        self.assertEqual(self.ledger.upsert_batches([self.batch]), 1)
        # Second upsert inserts nothing and preserves the row.
        self.assertEqual(self.ledger.upsert_batches([self.batch]), 0)
        self.assertEqual(self.ledger.total_member_count(), 2)

    def test_submit_and_verify_transitions(self):
        self.ledger.upsert_batches([self.batch])
        self.assertEqual(self.ledger.batch_ids_to_submit(), ["abc123"])
        self.ledger.mark_submitted("abc123", "job-1")
        # SUBMITTED is no longer offered for re-submission.
        self.assertEqual(self.ledger.batch_ids_to_submit(), [])
        # ...and counts as expected-to-have-landed.
        self.assertEqual(self.ledger.submitted_member_count(), 2)
        self.assertEqual(self.ledger.mark_verified_all_submitted(), 1)
        self.assertEqual(self.ledger.status_counts(), {"VERIFIED": 1})

    def test_failed_batches_are_resubmitted(self):
        self.ledger.upsert_batches([self.batch])
        parked = self.ledger.mark_failed("abc123", "boom", max_attempts=5)
        self.assertFalse(parked)  # below the ceiling -> still retryable
        self.assertEqual(self.ledger.batch_ids_to_submit(), ["abc123"])
        self.assertEqual(self.ledger.attempts("abc123"), 1)

    def test_exhausted_batches_are_parked_and_not_resubmitted(self):
        # Once retries are exhausted the batch must leave the submit list, or it
        # would fail every subsequent run forever.
        self.ledger.upsert_batches([self.batch])
        self.assertFalse(self.ledger.mark_failed("abc123", "boom", max_attempts=2))
        self.assertTrue(self.ledger.mark_failed("abc123", "boom", max_attempts=2))
        self.assertEqual(self.ledger.batch_ids_to_submit(), [])  # PARKED, excluded
        self.assertEqual(self.ledger.status_counts(), {"PARKED": 1})

    def test_baseline_default_is_write_once(self):
        self.assertEqual(self.ledger.set_meta_default("baseline_total_docs", "0"), "0")
        # A later call never overwrites the first value.
        self.assertEqual(self.ledger.set_meta_default("baseline_total_docs", "99"), "0")


class _FakeResp:
    def __init__(self, code):
        self.status_code = code
        self.headers = {}
        self.text = ""

    def json(self):
        return {"ok": True, "job_id": "j"}


class RequestRetryTests(unittest.TestCase):
    def test_file_stream_is_rewound_between_retries(self):
        # A retried multipart upload must re-send the FULL body — the bug was
        # that the BytesIO sat at EOF after the first attempt and uploaded
        # nothing on retry.
        client = drv.OCClient("http://example")
        client._sleep_backoff = lambda attempt: None  # no real sleeping
        bodies = []
        calls = {"n": 0}

        def fake_request(method, url, headers=None, timeout=None, **kwargs):
            bodies.append(kwargs["files"]["file"][1].read())
            calls["n"] += 1
            return _FakeResp(503 if calls["n"] == 1 else 200)

        client._session.request = fake_request
        resp = client._request(
            "POST",
            "http://example/up",
            files={"file": ("a.zip", BytesIO(b"PAYLOAD"), "application/zip")},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(bodies, [b"PAYLOAD", b"PAYLOAD"])


class _FakeStatsClient:
    """Stand-in OCClient that returns scripted processingCount values."""

    def __init__(self, processing_values):
        self._values = list(processing_values)
        self.calls = 0

    def document_stats(self, corpus_id):
        self.calls += 1
        # Pop while more remain; otherwise keep returning the final value.
        value = self._values.pop(0) if len(self._values) > 1 else self._values[0]
        return {"processingCount": value, "totalDocs": 0}


class GovernorTests(unittest.TestCase):
    def test_disabled_when_high_is_zero(self):
        client = _FakeStatsClient([999])
        gov = drv.QueueGovernor(client, "c", high=0, low=0, poll_interval=0)
        gov.wait()
        self.assertEqual(client.calls, 0)  # never polls when backpressure off

    def test_blocks_until_backlog_drains(self):
        # First poll is over the high-water mark, second is under the low-water
        # mark -> wait() must loop once and then return. poll_interval=0 makes
        # the in-loop sleep a no-op, so no real waiting.
        client = _FakeStatsClient([50, 1])
        gov = drv.QueueGovernor(client, "c", high=10, low=2, poll_interval=0)
        gov.wait()
        self.assertGreaterEqual(client.calls, 2)

    def test_reading_is_cached_within_interval(self):
        client = _FakeStatsClient([5])
        gov = drv.QueueGovernor(client, "c", high=100, low=10, poll_interval=1000)
        self.assertEqual(gov._maybe_poll(), 5)
        self.assertEqual(gov._maybe_poll(), 5)  # served from cache
        self.assertEqual(client.calls, 1)


if __name__ == "__main__":
    unittest.main()
