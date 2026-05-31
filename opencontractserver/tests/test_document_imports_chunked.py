"""
Tests for the chunked (resumable) multipart import endpoints.

These back the ``/api/imports/chunked/*`` flow that works around the 100 MB
per-request body ceiling on upstream proxies (Cloudflare): the client slices a
file into sub-ceiling parts, PUTs each part, then POSTs ``complete`` to
reassemble + import. Reassembly funnels into the same ``import_*_for_user``
services the direct endpoints use, so these tests focus on the chunking
machinery: arithmetic validation, per-part limits, IDOR isolation, integrity
checks, byte-exact reassembly, and cleanup.
"""

from __future__ import annotations

import hashlib
import io
import math
import zipfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from opencontractserver.corpuses.models import Corpus, TemporaryFileHandle
from opencontractserver.document_imports.models import (
    ChunkedUploadPart,
    ChunkedUploadSession,
    ChunkedUploadStatus,
)
from opencontractserver.documents.models import Document
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()


# Minimal but valid PDF; ``filetype`` recognises the magic bytes. Padded so we
# can split it into several parts with a small chunk size.
_PDF_CORE = (
    b"%PDF-1.7\n"
    b"1 0 obj\n<</Type/Catalog/Pages 2 0 R>>\nendobj\n"
    b"2 0 obj\n<</Type/Pages/Kids[3 0 R]/Count 1>>\nendobj\n"
    b"3 0 obj\n<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R/Resources<<>>>>\nendobj\n"
    b"xref\n0 4\n0000000000 65535 f\n0000000010 00000 n\n"
    b"0000000053 00000 n\n0000000102 00000 n\n"
    b"trailer\n<</Size 4/Root 1 0 R>>\nstartxref\n178\n%%EOF\n"
)
# Trailing comment bytes keep it a valid PDF while making it big enough to chunk.
PDF_BYTES = _PDF_CORE + b"%" + (b"A" * 4096) + b"\n"


def _make_zip(entries: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in entries.items():
            zf.writestr(name, content)
    return buf.getvalue()


START_URL = "/api/imports/chunked/start/"


def _part_url(upload_id, index: int) -> str:
    return f"/api/imports/chunked/{upload_id}/parts/{index}/"


def _complete_url(upload_id) -> str:
    return f"/api/imports/chunked/{upload_id}/complete/"


def _status_url(upload_id) -> str:
    return f"/api/imports/chunked/{upload_id}/"


@override_settings(CELERY_TASK_ALWAYS_EAGER=False)
class ChunkedUploadTests(TestCase):
    client: APIClient

    def setUp(self):
        self.user = User.objects.create_user(
            username="alice", password="pw", is_usage_capped=False
        )
        self.other_user = User.objects.create_user(
            username="bob", password="pw", is_usage_capped=False
        )
        self.corpus = Corpus.objects.create(
            title="Alice Corpus", creator=self.user, backend_lock=False
        )
        set_permissions_for_obj_to_user(self.user, self.corpus, [PermissionTypes.CRUD])
        self.client = APIClient()

    # ---- helpers ----

    def _login(self, user=None):
        self.client.force_authenticate(user=user or self.user)

    def _start(self, *, kind, filename, total_size, chunk_size, metadata=None):
        total_chunks = max(1, math.ceil(total_size / chunk_size))
        return self.client.post(
            START_URL,
            {
                "kind": kind,
                "filename": filename,
                "total_size": total_size,
                "chunk_size": chunk_size,
                "total_chunks": total_chunks,
                "metadata": metadata or {},
            },
            format="json",
        )

    def _put_part(self, upload_id, index, blob: bytes):
        return self.client.put(
            _part_url(upload_id, index),
            {"file": SimpleUploadedFile(f"part{index}", blob)},
            format="multipart",
        )

    def _upload_all_parts(self, upload_id, data: bytes, chunk_size: int):
        total_chunks = max(1, math.ceil(len(data) / chunk_size))
        for i in range(total_chunks):
            blob = data[i * chunk_size : (i + 1) * chunk_size]
            resp = self._put_part(upload_id, i, blob)
            self.assertEqual(resp.status_code, 200, resp.content)
        return total_chunks

    def _run_document(
        self, data: bytes, *, filename="big.pdf", chunk_size=1024, metadata=None
    ):
        meta = {"title": "Big Doc"}
        meta.update(metadata or {})
        start = self._start(
            kind="document",
            filename=filename,
            total_size=len(data),
            chunk_size=chunk_size,
            metadata=meta,
        )
        self.assertEqual(start.status_code, 201, start.content)
        upload_id = start.json()["upload_id"]
        self._upload_all_parts(upload_id, data, chunk_size)
        complete = self.client.post(_complete_url(upload_id))
        return upload_id, complete

    # ---- auth ----

    def test_start_unauthenticated_is_rejected(self):
        resp = self._start(
            kind="document", filename="x.pdf", total_size=10, chunk_size=10
        )
        self.assertIn(resp.status_code, (401, 403))

    # ---- happy path (single document) ----

    def test_document_chunked_round_trip_reassembles_bytes(self):
        self._login()
        # chunk_size 1024 over a >4KB file -> several parts.
        upload_id, complete = self._run_document(PDF_BYTES, chunk_size=1024)
        self.assertEqual(complete.status_code, 201, complete.content)
        body = complete.json()
        self.assertTrue(body["ok"])
        document = Document.objects.get(pk=body["document_id"])
        self.assertEqual(document.creator, self.user)

        # Byte-exact reassembly: the stored PDF must equal what we uploaded.
        with document.pdf_file.open("rb") as fh:
            stored = fh.read()
        self.assertEqual(
            hashlib.sha256(stored).hexdigest(),
            hashlib.sha256(PDF_BYTES).hexdigest(),
        )

        # Session is COMPLETED and its parts were reclaimed.
        session = ChunkedUploadSession.objects.get(id=upload_id)
        self.assertEqual(session.status, ChunkedUploadStatus.COMPLETED)
        self.assertEqual(ChunkedUploadPart.objects.filter(session=session).count(), 0)

    def test_document_chunked_into_corpus(self):
        self._login()
        _, complete = self._run_document(
            PDF_BYTES,
            chunk_size=2048,
            metadata={"add_to_corpus_id": str(self.corpus.id)},
        )
        self.assertEqual(complete.status_code, 201, complete.content)
        document = Document.objects.get(pk=complete.json()["document_id"])
        self.assertIn(document, self.corpus.get_documents())

    def test_single_part_upload(self):
        """A file smaller than the chunk size is a 1-part session."""
        self._login()
        _, complete = self._run_document(PDF_BYTES, chunk_size=10 * 1024 * 1024)
        self.assertEqual(complete.status_code, 201, complete.content)

    def test_document_complete_streams_file_not_bytes(self):
        """``complete`` must hand the import service a streaming ``file_obj``,
        never the whole assembled file as a ``bytes`` blob (issue #1843)."""
        from unittest.mock import patch

        from opencontractserver.document_imports import services

        self._login()
        start = self._start(
            kind="document",
            filename="big.pdf",
            total_size=len(PDF_BYTES),
            chunk_size=1024,
            metadata={"title": "Big Doc"},
        )
        upload_id = start.json()["upload_id"]
        self._upload_all_parts(upload_id, PDF_BYTES, 1024)

        captured: dict = {}

        real_import = services.import_document_for_user

        def _spy(**kwargs):
            captured.update(kwargs)
            return real_import(**kwargs)

        with patch.object(services, "import_document_for_user", side_effect=_spy):
            complete = self.client.post(_complete_url(upload_id))

        self.assertEqual(complete.status_code, 201, complete.content)
        # Streaming contract: a file-like is threaded through, not raw bytes.
        self.assertIsNone(captured.get("file_bytes"))
        self.assertIsNotNone(captured.get("file_obj"))

    def test_document_chunked_hash_is_computed_by_streaming(self):
        """The stored document's content hash matches a direct SHA-256 of the
        uploaded bytes even though the import never buffered them whole."""
        self._login()
        _, complete = self._run_document(PDF_BYTES, chunk_size=1024)
        self.assertEqual(complete.status_code, 201, complete.content)
        document = Document.objects.get(pk=complete.json()["document_id"])
        self.assertEqual(document.pdf_file_hash, hashlib.sha256(PDF_BYTES).hexdigest())

    def test_text_document_chunked_round_trip(self):
        """A plain-text single-document upload streams into txt_extract_file."""
        self._login()
        txt_bytes = b"Streamed plain text\n" + (b"line of body text\n" * 400)
        start = self._start(
            kind="document",
            filename="notes.txt",
            total_size=len(txt_bytes),
            chunk_size=1024,
            metadata={"title": "Notes", "add_to_corpus_id": str(self.corpus.id)},
        )
        self.assertEqual(start.status_code, 201, start.content)
        upload_id = start.json()["upload_id"]
        self._upload_all_parts(upload_id, txt_bytes, 1024)
        complete = self.client.post(_complete_url(upload_id))
        self.assertEqual(complete.status_code, 201, complete.content)

        document = Document.objects.get(pk=complete.json()["document_id"])
        # Text content is routed to txt_extract_file (not pdf_file) and the
        # streamed hash matches the raw bytes.
        self.assertTrue(document.txt_extract_file)
        self.assertFalse(document.pdf_file)
        with document.txt_extract_file.open("rb") as fh:
            self.assertEqual(fh.read(), txt_bytes)
        self.assertEqual(document.pdf_file_hash, hashlib.sha256(txt_bytes).hexdigest())

    # ---- validation ----

    def test_inconsistent_total_chunks_rejected(self):
        self._login()
        resp = self.client.post(
            START_URL,
            {
                "kind": "document",
                "filename": "x.pdf",
                "total_size": 100,
                "chunk_size": 60,
                "total_chunks": 5,  # ceil(100/60) == 2, not 5
                "metadata": {"title": "T"},
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 400, resp.content)

    @override_settings(MAX_DOCUMENT_IMPORT_SIZE_BYTES=10)
    def test_oversize_start_rejected_413(self):
        self._login()
        resp = self._start(
            kind="document",
            filename="x.pdf",
            total_size=100,
            chunk_size=100,
            metadata={"title": "T"},
        )
        self.assertEqual(resp.status_code, 413, resp.content)
        self.assertEqual(resp.json()["max_bytes"], 10)

    def test_document_start_requires_title(self):
        self._login()
        resp = self._start(
            kind="document", filename="x.pdf", total_size=10, chunk_size=10
        )
        self.assertEqual(resp.status_code, 400, resp.content)

    def test_part_exceeding_declared_chunk_size_rejected(self):
        self._login()
        start = self._start(
            kind="document",
            filename="x.pdf",
            total_size=10,
            chunk_size=10,
            metadata={"title": "T"},
        )
        upload_id = start.json()["upload_id"]
        resp = self._put_part(upload_id, 0, b"X" * 20)  # 20 > chunk_size 10
        self.assertEqual(resp.status_code, 400, resp.content)

    def test_part_index_out_of_range_rejected(self):
        self._login()
        start = self._start(
            kind="document",
            filename="x.pdf",
            total_size=10,
            chunk_size=10,
            metadata={"title": "T"},
        )
        upload_id = start.json()["upload_id"]
        resp = self._put_part(upload_id, 5, b"X")  # total_chunks == 1
        self.assertEqual(resp.status_code, 400, resp.content)

    def test_complete_with_missing_part_is_incomplete(self):
        self._login()
        start = self._start(
            kind="document",
            filename="x.pdf",
            total_size=120,
            chunk_size=60,
            metadata={"title": "T"},
        )
        upload_id = start.json()["upload_id"]
        self._put_part(upload_id, 0, b"A" * 60)  # only 1 of 2 parts
        resp = self.client.post(_complete_url(upload_id))
        self.assertEqual(resp.status_code, 400, resp.content)

    def test_complete_with_size_mismatch_rejected(self):
        self._login()
        start = self._start(
            kind="document",
            filename="x.pdf",
            total_size=100,
            chunk_size=60,  # ceil(100/60) == 2
            metadata={"title": "T"},
        )
        upload_id = start.json()["upload_id"]
        self._put_part(upload_id, 0, b"A" * 60)
        self._put_part(upload_id, 1, b"B" * 30)  # 90 != declared 100
        resp = self.client.post(_complete_url(upload_id))
        self.assertEqual(resp.status_code, 400, resp.content)

    # ---- idempotency / status ----

    def test_resending_a_part_is_idempotent(self):
        self._login()
        start = self._start(
            kind="document",
            filename="x.pdf",
            total_size=120,
            chunk_size=60,
            metadata={"title": "T"},
        )
        upload_id = start.json()["upload_id"]
        self._put_part(upload_id, 0, b"A" * 60)
        resp = self._put_part(upload_id, 0, b"C" * 60)  # overwrite index 0
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()["received_chunks"], 1)
        self.assertEqual(
            ChunkedUploadPart.objects.filter(session_id=upload_id).count(), 1
        )

    def test_status_endpoint_reports_progress(self):
        self._login()
        start = self._start(
            kind="document",
            filename="x.pdf",
            total_size=180,
            chunk_size=60,
            metadata={"title": "T"},
        )
        upload_id = start.json()["upload_id"]
        self._put_part(upload_id, 0, b"A" * 60)
        resp = self.client.get(_status_url(upload_id))
        self.assertEqual(resp.status_code, 200, resp.content)
        body = resp.json()
        self.assertEqual(body["received_chunks"], 1)
        self.assertEqual(body["total_chunks"], 3)
        self.assertEqual(body["status"], ChunkedUploadStatus.PENDING)

    # ---- IDOR isolation ----

    def test_other_user_cannot_touch_session(self):
        self._login()  # alice
        start = self._start(
            kind="document",
            filename="x.pdf",
            total_size=60,
            chunk_size=60,
            metadata={"title": "T"},
        )
        upload_id = start.json()["upload_id"]

        # Bob cannot PUT a part, complete, or read status of Alice's session.
        self.client.force_authenticate(user=self.other_user)
        self.assertEqual(self._put_part(upload_id, 0, b"A" * 60).status_code, 404)
        self.assertEqual(self.client.post(_complete_url(upload_id)).status_code, 404)
        self.assertEqual(self.client.get(_status_url(upload_id)).status_code, 404)

    # ---- zip kind ----

    def test_documents_zip_chunked_round_trip(self):
        self._login()
        zip_bytes = _make_zip({"a.pdf": PDF_BYTES, "b.pdf": PDF_BYTES})
        start = self._start(
            kind="documents_zip",
            filename="bundle.zip",
            total_size=len(zip_bytes),
            chunk_size=1024,
            metadata={"add_to_corpus_id": str(self.corpus.id)},
        )
        self.assertEqual(start.status_code, 201, start.content)
        upload_id = start.json()["upload_id"]
        self._upload_all_parts(upload_id, zip_bytes, 1024)
        complete = self.client.post(_complete_url(upload_id))
        self.assertEqual(complete.status_code, 202, complete.content)
        self.assertIn("job_id", complete.json())
        # The archive was staged for the async importer.
        self.assertTrue(TemporaryFileHandle.objects.exists())

    def test_non_zip_bytes_rejected_for_zip_kind(self):
        self._login()
        # A PDF is not a zip; complete must surface the not-a-zip error (400).
        # No metadata is passed at start: documents_zip has no required
        # start-time metadata (unlike `document`, which needs `title`, or
        # `zip_to_corpus`, which needs `corpus_id`), so the zip-magic check at
        # complete time is the first thing that can reject this upload.
        start = self._start(
            kind="documents_zip",
            filename="bundle.zip",
            total_size=len(PDF_BYTES),
            chunk_size=1024,
        )
        upload_id = start.json()["upload_id"]
        self._upload_all_parts(upload_id, PDF_BYTES, 1024)
        complete = self.client.post(_complete_url(upload_id))
        self.assertEqual(complete.status_code, 400, complete.content)
        session = ChunkedUploadSession.objects.get(id=upload_id)
        self.assertEqual(session.status, ChunkedUploadStatus.FAILED)


class ChunkedUploadServiceUnitTests(TestCase):
    """Direct service-layer tests that don't need the HTTP transport."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="carol", password="pw", is_usage_capped=False
        )

    def test_purge_stale_sessions_removes_parts(self):
        from datetime import timedelta

        from django.utils import timezone

        from opencontractserver.document_imports.services import (
            purge_stale_chunked_uploads,
        )

        session = ChunkedUploadSession.objects.create(
            creator=self.user,
            kind="document",
            filename="x.pdf",
            total_size=10,
            chunk_size=10,
            total_chunks=1,
            status=ChunkedUploadStatus.PENDING,
        )
        ChunkedUploadPart.objects.create(
            session=session,
            index=0,
            file=SimpleUploadedFile("p0", b"0123456789"),
            size=10,
        )
        # Backdate beyond the staleness window.
        ChunkedUploadSession.objects.filter(id=session.id).update(
            modified=timezone.now() - timedelta(hours=48)
        )

        purged = purge_stale_chunked_uploads(stale_hours=24)
        self.assertEqual(purged, 1)
        self.assertFalse(ChunkedUploadSession.objects.filter(id=session.id).exists())
        self.assertEqual(ChunkedUploadPart.objects.count(), 0)

    def test_purge_spares_assembling_within_grace_but_reclaims_crashed(self):
        """ASSEMBLING sessions are protected from the normal stale window.

        A live ``complete`` request streams parts without holding the session
        row lock, so the GC must not delete an ASSEMBLING session's parts
        inside the (generous) grace window — only once it has clearly outlived
        any real reassembly (a crashed worker).
        """
        from datetime import timedelta

        from django.utils import timezone

        from opencontractserver.document_imports.services import (
            CHUNKED_UPLOAD_ASSEMBLING_GRACE_HOURS,
            purge_stale_chunked_uploads,
        )

        def _make_assembling(filename: str) -> ChunkedUploadSession:
            return ChunkedUploadSession.objects.create(
                creator=self.user,
                kind="document",
                filename=filename,
                total_size=10,
                chunk_size=10,
                total_chunks=1,
                status=ChunkedUploadStatus.ASSEMBLING,
            )

        live = _make_assembling("live.pdf")
        crashed = _make_assembling("crashed.pdf")

        # ``live`` is past the 1h stale window but well within the grace window;
        # ``crashed`` is past the grace window.
        ChunkedUploadSession.objects.filter(id=live.id).update(
            modified=timezone.now() - timedelta(hours=2)
        )
        ChunkedUploadSession.objects.filter(id=crashed.id).update(
            modified=timezone.now()
            - timedelta(hours=CHUNKED_UPLOAD_ASSEMBLING_GRACE_HOURS + 1)
        )

        purged = purge_stale_chunked_uploads(stale_hours=1)
        self.assertEqual(purged, 1)
        self.assertTrue(ChunkedUploadSession.objects.filter(id=live.id).exists())
        self.assertFalse(ChunkedUploadSession.objects.filter(id=crashed.id).exists())

    def test_purge_removes_old_completed_but_keeps_recent(self):
        from datetime import timedelta

        from django.utils import timezone

        from opencontractserver.document_imports.services import (
            purge_stale_chunked_uploads,
        )

        def _make_completed(filename: str) -> ChunkedUploadSession:
            return ChunkedUploadSession.objects.create(
                creator=self.user,
                kind="document",
                filename=filename,
                total_size=10,
                chunk_size=10,
                total_chunks=1,
                status=ChunkedUploadStatus.COMPLETED,
            )

        old = _make_completed("old.pdf")
        recent = _make_completed("recent.pdf")
        # Backdate the "old" COMPLETED session beyond the retention window; the
        # recent one stays inside it.
        ChunkedUploadSession.objects.filter(id=old.id).update(
            modified=timezone.now() - timedelta(days=45)
        )

        purged = purge_stale_chunked_uploads(
            stale_hours=24, completed_retention_days=30
        )
        self.assertEqual(purged, 1)
        self.assertFalse(ChunkedUploadSession.objects.filter(id=old.id).exists())
        self.assertTrue(ChunkedUploadSession.objects.filter(id=recent.id).exists())

        # retention_days=0 disables COMPLETED purging entirely.
        ChunkedUploadSession.objects.filter(id=recent.id).update(
            modified=timezone.now() - timedelta(days=400)
        )
        kept = purge_stale_chunked_uploads(stale_hours=24, completed_retention_days=0)
        self.assertEqual(kept, 0)
        self.assertTrue(ChunkedUploadSession.objects.filter(id=recent.id).exists())
