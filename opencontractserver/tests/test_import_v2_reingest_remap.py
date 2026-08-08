"""Tests for the "reingest & remap" V2 corpus-import mode (opt-out at the
user-facing import entry point; explicit opt-in for direct callers).

Two layers:

``TestCorpusImportFanIn`` — pure coordination logic (the ``PendingCorpusImport``
model, ``_maybe_finalize_corpus_import`` exactly-once claim, and the
``finalize_corpus_import_relationships`` task). Rows are created directly; no
parser pipeline runs.

``TestReingestRemapEndToEnd`` — the full importer path under eager Celery with
hermetic in-test parsers, proving structural drop + reingest + remap +
relationship fan-in end to end.

See ``docs/development/2026-06-06-v2-import-reingest-remap.md``.
"""

from __future__ import annotations

import hashlib
import io
import json
import uuid
import zipfile

import pytest
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.db import transaction
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone

from opencontractserver.annotations.models import (
    RELATIONSHIP_LABEL,
    TOKEN_LABEL,
    Annotation,
    AnnotationLabel,
    LabelSet,
    Relationship,
)
from opencontractserver.corpuses.models import Corpus, TemporaryFileHandle
from opencontractserver.documents.models import (
    Document,
    DocumentPath,
    PendingCorpusImport,
    PendingDocumentAnnotations,
)
from opencontractserver.tasks.doc_tasks import (
    _maybe_finalize_corpus_import,
    finalize_corpus_import_relationships,
)
from opencontractserver.tasks.export_tasks_v2 import package_corpus_export_v2
from opencontractserver.tasks.import_tasks_v2 import (
    _import_document_with_annotations,
    _read_guarded_source_bytes,
    _read_publisher_source_payload,
    _source_is_reingestable,
)
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.annotation_anchoring import anchor_annotations
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()

pytestmark = pytest.mark.django_db

# Minimal one-page PAWLs with two tokens ("CHAPTER", "1") the anchorer can
# locate via bbox overlap + text confirmation. Mirrors the proven fixture in
# test_remap_pending_annotations / test_zip_import_integration.
_PAWLS_V1 = [
    {
        "page": {"width": 612.0, "height": 792.0, "index": 0},
        "tokens": [
            {"x": 10.0, "y": 10.0, "width": 56.0, "height": 12.0, "text": "CHAPTER"},
            {"x": 90.0, "y": 10.0, "width": 8.0, "height": 12.0, "text": "1"},
        ],
    }
]


class TestAnchorAnnotationsV2Shape(TestCase):
    """``anchor_annotations`` must accept the compact-v2 export annotation shape.

    The V2/V3 exporter writes ``annotation_json`` via ``compact_annotation_json``
    — a PDF annotation lands as ``{"v": 2, "p": {page: {"b": [...], "t": ...}}}``,
    NOT the legacy verbose ``{page: {"bounds": ...}}`` shape. Since reingest mode
    feeds these straight into the remap machinery, anchoring must understand the
    compact shape or every PDF annotation in a real export is silently dropped.
    """

    def test_compact_v2_pdf_annotation_anchors(self):
        ann = {
            "id": "a1",
            "annotationLabel": "OC_SECTION",
            "rawText": "CHAPTER 1",
            # Compact v2: b = [top, left, right, bottom]; covers both tokens.
            "annotation_json": {
                "v": 2,
                "p": {"0": {"b": [8.0, 8.0, 110.0, 24.0], "t": "0-1"}},
            },
            "structural": False,
        }
        anchored, report = anchor_annotations(
            [ann], is_pdf=True, pawls=_PAWLS_V1, content=""
        )
        self.assertEqual(len(anchored), 1, f"report={report}")
        self.assertFalse(report[0]["dropped"], f"report={report}")

    def test_compact_v2_span_annotation_anchors(self):
        """Span annotations export as ``{start, end, text}`` (unchanged)."""
        content = "This Agreement covers indemnification obligations herein."
        ann = {
            "id": "s1",
            "annotationLabel": "OC_CLAUSE",
            "rawText": "indemnification obligations",
            "annotation_json": {
                "start": content.find("indemnification"),
                "end": content.find("indemnification")
                + len("indemnification obligations"),
                "text": "indemnification obligations",
            },
            "structural": False,
        }
        anchored, report = anchor_annotations(
            [ann], is_pdf=False, pawls=[], content=content
        )
        self.assertEqual(len(anchored), 1, f"report={report}")
        self.assertFalse(report[0]["dropped"], f"report={report}")


class TestSourceReingestability(TestCase):
    """The placeholder guard that routes source-less docs to the baked path."""

    def test_placeholder_and_empty_are_not_reingestable(self):
        # The V2 exporter writes a single NUL byte for docs with no real
        # source file (text/markdown); those must NOT be re-parsed.
        self.assertFalse(_source_is_reingestable(b"\x00"))
        self.assertFalse(_source_is_reingestable(b""))

    def test_real_bytes_are_reingestable(self):
        self.assertTrue(_source_is_reingestable(b"%PDF-1.4 ..."))
        self.assertTrue(_source_is_reingestable(b"plain text body"))

    def test_publisher_source_sidecar_is_hash_verified_and_legacy_is_unchanged(self):
        source_bytes = b"<html><body>publisher source</body></html>"
        source_hash = hashlib.sha256(source_bytes).hexdigest()
        doc_data = {
            "custom_meta": {
                "publisher_source_member": "publisher-source-rule.html",
                "publisher_source_content_hash": source_hash,
                "publisher_source_mime_type": "text/html",
                "publisher_source_packaging": "sidecar",
            }
        }
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("rule.txt", b"portable text")
            zf.writestr("publisher-source-rule.html", source_bytes)
        buf.seek(0)

        with zipfile.ZipFile(buf) as zf:
            payload = _read_publisher_source_payload(zf, "rule.txt", doc_data)
            self.assertIsNotNone(payload)
            self.assertEqual(payload.content, source_bytes)
            self.assertEqual(payload.mime_type, "text/html")
            self.assertIsNone(
                _read_publisher_source_payload(
                    zf,
                    "rule.txt",
                    {"custom_meta": {"unrelated": True}},
                )
            )

    def test_publisher_source_sidecar_rejects_missing_mismatch_and_unsafe_path(self):
        source_bytes = b"<html>publisher source</html>"
        base_meta = {
            "publisher_source_member": "publisher-source-rule.html",
            "publisher_source_content_hash": hashlib.sha256(source_bytes).hexdigest(),
            "publisher_source_mime_type": "text/html",
            "publisher_source_packaging": "sidecar",
        }
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("rule.txt", b"portable text")
            zf.writestr("publisher-source-rule.html", source_bytes)
        buf.seek(0)

        with zipfile.ZipFile(buf) as zf:
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                _read_publisher_source_payload(
                    zf,
                    "rule.txt",
                    {
                        "custom_meta": {
                            **base_meta,
                            "publisher_source_content_hash": "0" * 64,
                        }
                    },
                )
            with self.assertRaisesRegex(ValueError, "safe ZIP member"):
                _read_publisher_source_payload(
                    zf,
                    "rule.txt",
                    {
                        "custom_meta": {
                            **base_meta,
                            "publisher_source_member": "../publisher.html",
                        }
                    },
                )
            with self.assertRaisesRegex(ValueError, "occurs 0 times"):
                _read_publisher_source_payload(
                    zf,
                    "rule.txt",
                    {
                        "custom_meta": {
                            **base_meta,
                            "publisher_source_member": "missing.html",
                        }
                    },
                )

    def test_publisher_source_sidecar_rejects_a_repeated_member_name(self):
        """A name appearing twice in the central directory is refused.

        This is the branch that forces the member census to exist.
        ``ZipFile.NameToInfo`` keeps only the LAST entry for a repeated name,
        so it can neither detect nor disambiguate this: a ZIP carrying two
        ``publisher-source-rule.html`` entries would silently hash one and let
        an extractor take the other. The sibling case above covers count 0
        (missing); this covers count > 1, and together they pin both sides of
        ``occurrences != 1`` across the memoised-``Counter`` refactor.
        """
        source_bytes = b"<html>publisher source</html>"
        meta = {
            "publisher_source_member": "publisher-source-rule.html",
            "publisher_source_content_hash": hashlib.sha256(source_bytes).hexdigest(),
            "publisher_source_mime_type": "text/html",
            "publisher_source_packaging": "sidecar",
        }
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("rule.txt", b"portable text")
            zf.writestr("publisher-source-rule.html", source_bytes)
            # Same name, different bytes — the shadowing case.
            zf.writestr("publisher-source-rule.html", b"<html>decoy</html>")
        buf.seek(0)

        with zipfile.ZipFile(buf) as zf:
            with self.assertRaisesRegex(ValueError, "occurs 2 times"):
                _read_publisher_source_payload(zf, "rule.txt", {"custom_meta": meta})

    def test_baked_import_persists_publisher_sidecar_as_original_file(self):
        user = User.objects.create_user(username="source_sidecar_user", password="pw")
        labelset = LabelSet.objects.create(title="LS", creator=user)
        corpus = Corpus.objects.create(title="C", creator=user, label_set=labelset)
        source_bytes = b"<html><body>publisher source</body></html>"
        source_hash = hashlib.sha256(source_bytes).hexdigest()
        custom_meta = {
            "publisher_source_member": "publisher-source-rule.html",
            "publisher_source_content_hash": source_hash,
            "publisher_source_mime_type": "text/html",
            "publisher_source_packaging": "sidecar",
        }
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("rule.txt", b"portable text")
            zf.writestr("publisher-source-rule.html", source_bytes)
        buf.seek(0)

        with zipfile.ZipFile(buf) as zf:
            corpus_doc, _ = _import_document_with_annotations(
                doc_filename="rule.txt",
                doc_data={
                    "title": "Rule",
                    "description": "",
                    "content": "portable text",
                    "file_type": "text/plain",
                    "pawls_file_content": [],
                    "custom_meta": custom_meta,
                },
                import_zip=zf,
                user_obj=user,
                corpus_obj=corpus,
                label_lookup={},
                doc_label_lookup={},
                reingest_and_remap=False,
            )

        self.assertIsNotNone(corpus_doc)
        corpus_doc.refresh_from_db()
        self.assertEqual(corpus_doc.original_file_type, "text/html")
        with corpus_doc.original_file.open("rb") as source_file:
            self.assertEqual(source_file.read(), source_bytes)
        self.assertEqual(corpus_doc.custom_meta, custom_meta)

    @override_settings(MAX_CORPUS_REINGEST_SOURCE_BYTES=4)
    def test_read_guarded_source_bytes_rejects_oversized_zip_member(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("documents/large.pdf", b"%PDF-1.4 large")
        buf.seek(0)

        with zipfile.ZipFile(buf) as zf:
            self.assertIsNone(_read_guarded_source_bytes(zf, "documents/large.pdf"))

    @override_settings(MAX_CORPUS_REINGEST_SOURCE_BYTES=32)
    def test_read_guarded_source_bytes_allows_member_under_limit(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("documents/small.pdf", b"%PDF-1.4 small")
        buf.seek(0)

        with zipfile.ZipFile(buf) as zf:
            self.assertEqual(
                _read_guarded_source_bytes(zf, "documents/small.pdf"),
                b"%PDF-1.4 small",
            )

    @override_settings(MAX_CORPUS_REINGEST_SOURCE_BYTES=None)
    def test_read_guarded_source_bytes_none_disables_guard(self):
        """``None`` is the disable sentinel base.py parses a negative env value
        into: the member is read unbounded regardless of size (0 must NOT do
        this — see the zero-rejects test below)."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("documents/any.pdf", b"%PDF-1.4 unbounded body")
        buf.seek(0)

        with zipfile.ZipFile(buf) as zf:
            self.assertEqual(
                _read_guarded_source_bytes(zf, "documents/any.pdf"),
                b"%PDF-1.4 unbounded body",
            )

    @override_settings(MAX_CORPUS_REINGEST_SOURCE_BYTES=0)
    def test_read_guarded_source_bytes_zero_rejects_nonempty_member(self):
        """0 is a literal zero-byte limit, not a disable: every non-empty member
        is rejected (so zeroing the setting hardens rather than opens a hole)."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("documents/any.pdf", b"%PDF-1.4 x")
        buf.seek(0)

        with zipfile.ZipFile(buf) as zf:
            self.assertIsNone(_read_guarded_source_bytes(zf, "documents/any.pdf"))

    @override_settings(MAX_CORPUS_REINGEST_SOURCE_BYTES=4)
    def test_read_guarded_source_bytes_missing_member_returns_none(self):
        """A member absent from the ZIP is skipped gracefully (KeyError caught)
        rather than aborting the whole corpus import."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("documents/present.pdf", b"x")
        buf.seek(0)

        with zipfile.ZipFile(buf) as zf:
            self.assertIsNone(_read_guarded_source_bytes(zf, "documents/missing.pdf"))

    @override_settings(MAX_CORPUS_REINGEST_SOURCE_BYTES=4)
    def test_read_guarded_source_bytes_rejects_metadata_lie_on_read(self):
        """A crafted ZIP whose central-directory file_size under-reports the
        real member is rejected (returns None → document skipped).

        Shrinking the reported ``file_size`` to 3 (<= 4) bypasses the metadata
        guard. For a ``ZIP_STORED`` member ``ZipExtFile`` caps the decompressed
        output at ``file_size``, so the bounded ``read(5)`` stops at 3 bytes,
        hits end-of-member, and validates the stored CRC-32 (computed over the
        real 10 bytes) against the 3 it returned — the mismatch raises
        ``BadZipFile``. The rejection therefore comes from the EXCEPTION HANDLER,
        not the post-read length guard (which a real STORED member can never
        reach, since the output is already capped at ``file_size``). This test
        asserts on the emitted log so the actual guard stays pinned.
        """
        # 10-byte stored entry: compress_size == 10.
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_STORED) as zf:
            zf.writestr("documents/liar.pdf", b"%PDF-1.4 x")
        buf.seek(0)

        with zipfile.ZipFile(buf) as real_zf:
            # ZipFile.getinfo() returns the live ZipInfo from NameToInfo, so
            # modifying it in-place is seen by the subsequent getinfo() call
            # inside _read_guarded_source_bytes.
            real_info = real_zf.getinfo("documents/liar.pdf")
            # Lie: shrink reported file_size to 3 so the first guard (3 > 4) is
            # skipped. The actual stored data is 10 bytes, so the bounded read
            # trips CRC validation and raises BadZipFile → caught → None.
            real_info.file_size = 3
            # _read_guarded_source_bytes is a thin wrapper around the shared
            # read_zip_member_bounded() choke point (see zip_security.py), so
            # the warning is emitted from that module's logger, not this one.
            with self.assertLogs(
                "opencontractserver.utils.zip_security", level="WARNING"
            ) as captured:
                result = _read_guarded_source_bytes(real_zf, "documents/liar.pdf")

        self.assertIsNone(result)
        # Assert the EXCEPTION handler fired (CRC trip), not the post-read guard.
        self.assertTrue(
            any("could not be read safely" in line for line in captured.output),
            f"expected read-error (CRC) warning, got {captured.output}",
        )

    @override_settings(MAX_CORPUS_REINGEST_SOURCE_BYTES=4)
    def test_read_guarded_source_bytes_rejects_overlong_read(self):
        """Defense-in-depth: a member that slips past the metadata guard but
        whose bounded read still yields more than the limit is rejected by the
        post-read length check (returns None → document skipped).

        Real crafted ZIPs trip CRC validation instead, but this guards against
        any reader path that returns extra bytes without raising.
        """
        from types import SimpleNamespace
        from unittest.mock import MagicMock

        # 11 readable bytes behind a member that reports file_size=2 (<= 4, so
        # the metadata guard is skipped). The bounded read pulls 5 bytes (4 + 1),
        # and 5 > 4 trips the length guard.
        fh = io.BytesIO(b"%PDF-1.4 xx")
        member_cm = MagicMock()
        member_cm.__enter__.return_value = fh
        member_cm.__exit__.return_value = False
        fake_zip = MagicMock()
        fake_zip.getinfo.return_value = SimpleNamespace(file_size=2)
        fake_zip.open.return_value = member_cm

        self.assertIsNone(_read_guarded_source_bytes(fake_zip, "documents/x.pdf"))

    @override_settings(MAX_CORPUS_REINGEST_SOURCE_BYTES=4)
    def test_oversized_member_rejected_on_both_reingest_and_baked_paths(self):
        """An over-size source member is skipped on BOTH paths — proving the
        guard cannot be bypassed by falling through to the baked import.

        Regression for the critical finding: when the reingest peek rejected an
        over-size member, the caller previously re-opened the SAME member with
        ``import_zip.open(doc_filename)`` (no size limit) for the baked import,
        streaming the whole entry to storage. The baked block now routes through
        the same size guard, so the document is skipped on either path.
        """
        user = User.objects.create_user(username="baked_guard_user", password="pw")
        labelset = LabelSet.objects.create(title="LS", creator=user)
        corpus = Corpus.objects.create(title="C", creator=user, label_set=labelset)

        # Real (non-placeholder) PDF bytes so the reingest path would otherwise
        # treat the member as reingestable; the size guard must reject it first.
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("documents/huge.pdf", b"%PDF-1.4 oversized body")
        zip_bytes = buf.getvalue()

        for reingest in (True, False):
            with self.subTest(reingest_and_remap=reingest):
                doc_count_before = Document.objects.count()
                with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
                    corpus_doc, annot_id_map = _import_document_with_annotations(
                        doc_filename="documents/huge.pdf",
                        doc_data={
                            "title": "Huge",
                            "content": "x",
                            "pawls_file_content": [],
                        },
                        import_zip=zf,
                        user_obj=user,
                        corpus_obj=corpus,
                        label_lookup={},
                        doc_label_lookup={},
                        reingest_and_remap=reingest,
                    )

                self.assertIsNone(corpus_doc)
                self.assertEqual(annot_id_map, {})
                # The over-size member was never streamed into storage.
                self.assertEqual(Document.objects.count(), doc_count_before)

    @override_settings(MAX_CORPUS_REINGEST_SOURCE_BYTES=4)
    def test_oversized_member_read_guard_not_called_twice_on_reingest_reject(self):
        """Regression: an oversize member rejected by the reingest peek must
        not be re-read (and re-rejected) a second time by the baked fallback
        block.

        Before the fix, ``baked_source_bytes`` used ``None`` as both "not yet
        read" (direct baked path) and "read but rejected by the guard"
        (reingest fallback), so the baked block could not tell the two states
        apart and re-opened + re-rejected the SAME ZIP member — doubling the
        warning logs the guard emits for a single oversize event.
        """
        from unittest import mock

        user = User.objects.create_user(username="single_read_user", password="pw")
        labelset = LabelSet.objects.create(title="LS", creator=user)
        corpus = Corpus.objects.create(title="C", creator=user, label_set=labelset)

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("documents/huge.pdf", b"%PDF-1.4 oversized body")
        buf.seek(0)

        with zipfile.ZipFile(buf) as zf:
            with mock.patch(
                "opencontractserver.tasks.import_tasks_v2._read_guarded_source_bytes",
                wraps=_read_guarded_source_bytes,
            ) as mocked_read:
                corpus_doc, annot_id_map = _import_document_with_annotations(
                    doc_filename="documents/huge.pdf",
                    doc_data={
                        "title": "Huge",
                        "content": "x",
                        "pawls_file_content": [],
                    },
                    import_zip=zf,
                    user_obj=user,
                    corpus_obj=corpus,
                    label_lookup={},
                    doc_label_lookup={},
                    reingest_and_remap=True,
                )

            # The peek read the member exactly once: the baked fallback block
            # must reuse that rejection rather than re-opening the member.
            mocked_read.assert_called_once_with(zf, "documents/huge.pdf")

        self.assertIsNone(corpus_doc)
        self.assertEqual(annot_id_map, {})


class TestCorpusImportFanIn(TestCase):
    """Coordination-layer unit tests for the relationship fan-in."""

    def setUp(self):
        self.user = User.objects.create_user(username="fanin_user", password="testpass")
        self.labelset = LabelSet.objects.create(title="LS", creator=self.user)
        self.token_label = AnnotationLabel.objects.create(
            text="OC_SECTION", label_type=TOKEN_LABEL, creator=self.user
        )
        self.rel_label = AnnotationLabel.objects.create(
            text="references", label_type=RELATIONSHIP_LABEL, creator=self.user
        )
        self.labelset.annotation_labels.add(self.token_label, self.rel_label)
        self.corpus = Corpus.objects.create(
            title="C", creator=self.user, label_set=self.labelset
        )

    def _doc(self) -> Document:
        return Document.objects.create(
            title="D", creator=self.user, file_type="application/pdf"
        )

    def _annotation(self, doc: Document) -> Annotation:
        return Annotation.objects.create(
            document=doc,
            corpus=self.corpus,
            annotation_label=self.token_label,
            raw_text="x",
            creator=self.user,
        )

    def test_maybe_finalize_noop_when_no_coordination_row(self):
        """An unknown run id is a clean no-op (relationship-free runs)."""
        # Should not raise even though no PendingCorpusImport row exists.
        _maybe_finalize_corpus_import(uuid.uuid4())

    def test_maybe_finalize_noop_while_pending_rows_remain(self):
        """A READY run with a still-PENDING doc row is not finalized yet."""
        run_id = uuid.uuid4()
        coord = PendingCorpusImport.objects.create(
            import_run_id=run_id,
            corpus=self.corpus,
            creator=self.user,
            relationships_payload=[],
            expected_doc_count=1,
            status=PendingCorpusImport.Status.READY,
        )
        PendingDocumentAnnotations.objects.create(
            document=self._doc(),
            corpus=self.corpus,
            creator=self.user,
            ingestion_run_id=run_id,
            payload={},
            status=PendingDocumentAnnotations.Status.PENDING,
        )

        with self.captureOnCommitCallbacks(execute=True):
            _maybe_finalize_corpus_import(run_id)

        coord.refresh_from_db()
        self.assertEqual(coord.status, PendingCorpusImport.Status.READY)

    def test_maybe_finalize_wires_relationships_when_all_done(self):
        """Once every doc row is DONE, finalize wires the relationship.

        Two documents, each with a remapped annotation recorded in its
        ``id_map``; a corpus relationship references one endpoint per doc. The
        fan-in must resolve both via the aggregated map and create exactly one
        Relationship.
        """
        run_id = uuid.uuid4()
        doc_a, doc_b = self._doc(), self._doc()
        ann_a, ann_b = self._annotation(doc_a), self._annotation(doc_b)

        PendingDocumentAnnotations.objects.create(
            document=doc_a,
            corpus=self.corpus,
            creator=self.user,
            ingestion_run_id=run_id,
            payload={},
            id_map={"100": ann_a.id},
            status=PendingDocumentAnnotations.Status.DONE,
        )
        PendingDocumentAnnotations.objects.create(
            document=doc_b,
            corpus=self.corpus,
            creator=self.user,
            ingestion_run_id=run_id,
            payload={},
            id_map={"200": ann_b.id},
            status=PendingDocumentAnnotations.Status.DONE,
        )

        coord = PendingCorpusImport.objects.create(
            import_run_id=run_id,
            corpus=self.corpus,
            creator=self.user,
            relationships_payload=[
                {
                    "relationshipLabel": "references",
                    "source_annotation_ids": [100],
                    "target_annotation_ids": [200],
                    "structural": False,
                }
            ],
            expected_doc_count=2,
            status=PendingCorpusImport.Status.READY,
        )

        with self.captureOnCommitCallbacks(execute=True):
            _maybe_finalize_corpus_import(run_id)

        coord.refresh_from_db()
        self.assertEqual(coord.status, PendingCorpusImport.Status.DONE)
        rels = Relationship.objects.filter(corpus=self.corpus, structural=False)
        self.assertEqual(rels.count(), 1)
        rel = rels.get()
        self.assertEqual(list(rel.source_annotations.all()), [ann_a])
        self.assertEqual(list(rel.target_annotations.all()), [ann_b])

    def test_finalize_exactly_once_under_double_dispatch(self):
        """A second finalize after DONE never double-wires (idempotency)."""
        run_id = uuid.uuid4()
        doc_a, doc_b = self._doc(), self._doc()
        ann_a, ann_b = self._annotation(doc_a), self._annotation(doc_b)
        for doc, key, ann in ((doc_a, "100", ann_a), (doc_b, "200", ann_b)):
            PendingDocumentAnnotations.objects.create(
                document=doc,
                corpus=self.corpus,
                creator=self.user,
                ingestion_run_id=run_id,
                payload={},
                id_map={key: ann.id},
                status=PendingDocumentAnnotations.Status.DONE,
            )
        PendingCorpusImport.objects.create(
            import_run_id=run_id,
            corpus=self.corpus,
            creator=self.user,
            relationships_payload=[
                {
                    "relationshipLabel": "references",
                    "source_annotation_ids": [100],
                    "target_annotation_ids": [200],
                    "structural": False,
                }
            ],
            expected_doc_count=2,
            status=PendingCorpusImport.Status.FINALIZING,
        )

        # First finalize wires the relationship.
        finalize_corpus_import_relationships(str(run_id))
        # A redelivered task after DONE must be a no-op.
        finalize_corpus_import_relationships(str(run_id))

        self.assertEqual(
            Relationship.objects.filter(corpus=self.corpus, structural=False).count(),
            1,
        )

    def test_finalize_reentry_from_failed_state(self):
        """A FAILED row can be retried and reach DONE (retry contract)."""
        run_id = uuid.uuid4()
        doc_a, doc_b = self._doc(), self._doc()
        ann_a, ann_b = self._annotation(doc_a), self._annotation(doc_b)
        for doc, key, ann in ((doc_a, "100", ann_a), (doc_b, "200", ann_b)):
            PendingDocumentAnnotations.objects.create(
                document=doc,
                corpus=self.corpus,
                creator=self.user,
                ingestion_run_id=run_id,
                payload={},
                id_map={key: ann.id},
                status=PendingDocumentAnnotations.Status.DONE,
            )
        coord = PendingCorpusImport.objects.create(
            import_run_id=run_id,
            corpus=self.corpus,
            creator=self.user,
            relationships_payload=[
                {
                    "relationshipLabel": "references",
                    "source_annotation_ids": [100],
                    "target_annotation_ids": [200],
                    "structural": False,
                }
            ],
            expected_doc_count=2,
            status=PendingCorpusImport.Status.FAILED,
        )

        finalize_corpus_import_relationships(str(run_id))

        coord.refresh_from_db()
        self.assertEqual(coord.status, PendingCorpusImport.Status.DONE)
        self.assertEqual(
            Relationship.objects.filter(corpus=self.corpus, structural=False).count(),
            1,
        )

    def test_finalize_skips_relationship_with_missing_endpoint(self):
        """An endpoint absent from every id_map drops the relationship.

        Only one doc anchored; a relationship references an annotation from a
        doc whose remap failed (no id_map entry), so it cannot be wired.
        """
        run_id = uuid.uuid4()
        doc_a = self._doc()
        ann_a = self._annotation(doc_a)
        PendingDocumentAnnotations.objects.create(
            document=doc_a,
            corpus=self.corpus,
            creator=self.user,
            ingestion_run_id=run_id,
            payload={},
            id_map={"100": ann_a.id},
            status=PendingDocumentAnnotations.Status.DONE,
        )
        PendingCorpusImport.objects.create(
            import_run_id=run_id,
            corpus=self.corpus,
            creator=self.user,
            relationships_payload=[
                {
                    "relationshipLabel": "references",
                    "source_annotation_ids": [100],
                    "target_annotation_ids": [999],  # never anchored
                    "structural": False,
                }
            ],
            expected_doc_count=1,
            status=PendingCorpusImport.Status.FINALIZING,
        )

        finalize_corpus_import_relationships(str(run_id))

        self.assertEqual(
            Relationship.objects.filter(corpus=self.corpus, structural=False).count(),
            0,
        )


class TestRemapFinalizeTrigger(TestCase):
    """``remap_pending_annotations`` triggers the fan-in for import runs only."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="trigger_user", password="testpass"
        )
        self.labelset = LabelSet.objects.create(title="LS", creator=self.user)
        self.corpus = Corpus.objects.create(
            title="C", creator=self.user, label_set=self.labelset
        )

    def _doc(self) -> Document:
        from django.utils import timezone

        # ``processing_started`` suppresses the post_save ingest signal so the
        # test drives ``remap_pending_annotations`` directly.
        return Document.objects.create(
            title="D",
            creator=self.user,
            file_type="application/pdf",
            processing_started=timezone.now(),
        )

    def test_remap_triggers_finalize_when_run_completes(self):
        """Completing the last doc's remap finalizes the coordination row."""
        from opencontractserver.tasks.doc_tasks import remap_pending_annotations

        run_id = uuid.uuid4()
        doc = self._doc()
        PendingDocumentAnnotations.objects.create(
            document=doc,
            corpus=self.corpus,
            creator=self.user,
            ingestion_run_id=run_id,
            payload={"annotations": [], "doc_labels": []},
            status=PendingDocumentAnnotations.Status.PENDING,
        )
        coord = PendingCorpusImport.objects.create(
            import_run_id=run_id,
            corpus=self.corpus,
            creator=self.user,
            relationships_payload=[],
            expected_doc_count=1,
            status=PendingCorpusImport.Status.READY,
        )

        with self.captureOnCommitCallbacks(execute=True):
            remap_pending_annotations(doc_id=doc.id)

        coord.refresh_from_db()
        self.assertEqual(coord.status, PendingCorpusImport.Status.DONE)

    def test_remap_without_run_id_does_not_finalize_or_error(self):
        """An ordinary upload (run_id=None, no coordination row) is unaffected."""
        from opencontractserver.tasks.doc_tasks import remap_pending_annotations

        doc = self._doc()
        pending = PendingDocumentAnnotations.objects.create(
            document=doc,
            corpus=self.corpus,
            creator=self.user,
            ingestion_run_id=None,
            payload={"annotations": [], "doc_labels": []},
            status=PendingDocumentAnnotations.Status.PENDING,
        )

        with self.captureOnCommitCallbacks(execute=True):
            remap_pending_annotations(doc_id=doc.id)

        pending.refresh_from_db()
        self.assertEqual(pending.status, PendingDocumentAnnotations.Status.DONE)
        self.assertFalse(PendingCorpusImport.objects.exists())


# These imports are intentionally module-level-but-late (E402): the
# coordination-only test classes above need nothing from the heavy zip-import
# integration module, and importing it eagerly at the top would pull its
# hermetic-parser machinery into every test in this file. Keeping them here
# scopes that cost to the end-to-end class below. (Not function-local because
# the parser-path constants are referenced in class-level decorators/fixtures.)
from opencontractserver.tests.fixtures import SAMPLE_PDF_FILE_ONE_PATH  # noqa: E402

# Hermetic in-test PDF parser (shared with test_zip_import_integration) returns
# deterministic PAWLs with a known "CHAPTER 1" heading, so the reingested docs
# get a real parser-produced layer without any external parser service.
from opencontractserver.tests.test_zip_import_integration import (  # noqa: E402
    _DUMB_ANCHOR_PDF_PARSER_PATH,
    DUMB_ANCHOR_HEADING_BBOX,
    DUMB_ANCHOR_HEADING_TEXT,
)
from opencontractserver.users.models import UserExport  # noqa: E402


@pytest.mark.usefixtures("enable_doc_processing_signals")
class TestReingestRemapEndToEnd(TransactionTestCase):
    """Full export -> reingest-import round-trip under the real ingest chain.

    Builds a source corpus with two PDF documents (each with one token
    annotation over the heading) and a corpus-level relationship linking them,
    exports it, then re-imports with ``reingest_and_remap=True``. The hermetic
    PDF parser regenerates a deterministic PAWLs layer; the surviving
    annotations re-anchor onto it; and once both remaps finish, the fan-in wires
    the relationship. ``TransactionTestCase`` so ``transaction.on_commit`` ingest
    chains actually fire under eager Celery.
    """

    def _set_pdf_parser(self) -> None:
        from opencontractserver.documents.models import PipelineSettings

        ps = PipelineSettings.get_instance(use_cache=False)
        ps.preferred_parsers = {
            **(ps.preferred_parsers or {}),
            "application/pdf": _DUMB_ANCHOR_PDF_PARSER_PATH,
        }
        ps.save()
        PipelineSettings.clear_cache()
        self.addCleanup(PipelineSettings.clear_cache)

    def setUp(self):
        self.pdf_bytes = SAMPLE_PDF_FILE_ONE_PATH.read_bytes()
        # Minimal source PAWLs (export needs *some* layer; the reingest discards
        # it and re-parses, so its exact tokens do not matter).
        self.src_pawls = json.dumps(
            [
                {
                    "page": {"width": 612.0, "height": 792.0, "index": 0},
                    "tokens": [
                        {
                            "x": 50.0,
                            "y": 50.0,
                            "width": 70.0,
                            "height": 14.0,
                            "text": "CHAPTER",
                        },
                        {
                            "x": 125.0,
                            "y": 50.0,
                            "width": 10.0,
                            "height": 14.0,
                            "text": "1",
                        },
                    ],
                }
            ]
        ).encode("utf-8")

        with transaction.atomic():
            self.user = User.objects.create_user(
                username="reingest_user", password="testpass"
            )

        with transaction.atomic():
            self.labelset = LabelSet.objects.create(title="LS", creator=self.user)
            self.token_label = AnnotationLabel.objects.create(
                text="OC_SECTION", label_type=TOKEN_LABEL, creator=self.user
            )
            self.rel_label = AnnotationLabel.objects.create(
                text="relates_to",
                label_type=RELATIONSHIP_LABEL,
                creator=self.user,
            )
            self.labelset.annotation_labels.add(self.token_label, self.rel_label)
            self.corpus = Corpus.objects.create(
                title="Reingest Source Corpus",
                creator=self.user,
                label_set=self.labelset,
            )
            set_permissions_for_obj_to_user(
                self.user, self.corpus, [PermissionTypes.ALL]
            )

        created_anns: list[Annotation] = []
        for idx in (1, 2):
            with transaction.atomic():
                doc = Document.objects.create(
                    title=f"Doc {idx}",
                    creator=self.user,
                    file_type="application/pdf",
                    pdf_file=ContentFile(self.pdf_bytes, name=f"doc{idx}.pdf"),
                    pdf_file_hash=f"src_hash_{idx}",
                    pawls_parse_file=ContentFile(self.src_pawls, name="pawls.json"),
                    page_count=1,
                    # Suppress the source-side ingest signal; this corpus is the
                    # fixture to export, not under test.
                    processing_started=timezone.now(),
                )
                DocumentPath.objects.create(
                    document=doc,
                    corpus=self.corpus,
                    path=f"/doc{idx}.pdf",
                    version_number=1,
                    is_current=True,
                    is_deleted=False,
                    creator=self.user,
                )
                ann = Annotation.objects.create(
                    document=doc,
                    corpus=self.corpus,
                    annotation_label=self.token_label,
                    raw_text=DUMB_ANCHOR_HEADING_TEXT,
                    page=0,
                    annotation_type=TOKEN_LABEL,
                    json={
                        "0": {
                            "bounds": DUMB_ANCHOR_HEADING_BBOX,
                            "tokensJsons": [],
                            "rawText": DUMB_ANCHOR_HEADING_TEXT,
                        }
                    },
                    creator=self.user,
                )
                set_permissions_for_obj_to_user(self.user, ann, [PermissionTypes.ALL])
            created_anns.append(ann)

        self.ann_a, self.ann_b = created_anns

        with transaction.atomic():
            rel = Relationship.objects.create(
                corpus=self.corpus,
                document=self.ann_a.document,
                relationship_label=self.rel_label,
                structural=False,
                creator=self.user,
            )
            rel.source_annotations.set([self.ann_a])
            rel.target_annotations.set([self.ann_b])
            set_permissions_for_obj_to_user(self.user, rel, [PermissionTypes.ALL])

    def _export_and_stage(self) -> TemporaryFileHandle:
        export = UserExport.objects.create(backend_lock=True, creator=self.user)
        package_corpus_export_v2(
            export_id=export.id,
            corpus_pk=self.corpus.id,
            include_conversations=False,
        )
        export.refresh_from_db()
        temp_file = TemporaryFileHandle.objects.create()
        export.file.open("rb")
        temp_file.file.save("reingest_import.zip", export.file)
        export.file.close()
        return temp_file

    def test_reingest_remap_round_trip_wires_relationship(self):
        from opencontractserver.tasks.import_tasks_v2 import import_corpus_v2

        self._set_pdf_parser()
        temp_file = self._export_and_stage()

        imported_id = import_corpus_v2(
            temporary_file_handle_id=temp_file.id,
            user_id=self.user.id,
            seed_corpus_id=None,
            reingest_and_remap=True,
        )
        self.assertIsNotNone(imported_id)
        imported = Corpus.objects.get(id=imported_id)

        # Documents reingested: backend unlocked, parser-produced text present.
        imported_docs = list(
            Document.objects.filter(
                pk__in=DocumentPath.objects.filter(
                    corpus=imported, is_current=True, is_deleted=False
                ).values_list("document_id", flat=True)
            )
        )
        self.assertEqual(len(imported_docs), 2)
        for doc in imported_docs:
            doc.refresh_from_db()
            self.assertFalse(doc.backend_lock, f"doc {doc.id} still locked")
            self.assertTrue(
                doc.txt_extract_file
                and doc.txt_extract_file.read().decode("utf-8").strip()
            )

        # Both deferred annotation rows consumed and DONE.
        rows = PendingDocumentAnnotations.objects.filter(document__in=imported_docs)
        self.assertEqual(rows.count(), 2)
        for r in rows:
            self.assertEqual(r.status, PendingDocumentAnnotations.Status.DONE)

        # Surviving non-structural annotations re-anchored onto fresh PAWLs.
        imported_annots = Annotation.objects.filter(
            corpus=imported,
            annotation_label__text="OC_SECTION",
            structural=False,
        )
        self.assertEqual(imported_annots.count(), 2)

        # Coordination row finalized.
        coord = PendingCorpusImport.objects.get(corpus=imported)
        self.assertEqual(coord.status, PendingCorpusImport.Status.DONE)

        # Relationship wired across the two reingested docs via the fan-in.
        rels = Relationship.objects.filter(corpus=imported, structural=False)
        self.assertEqual(rels.count(), 1)
        rel = rels.get()
        self.assertEqual(rel.source_annotations.count(), 1)
        self.assertEqual(rel.target_annotations.count(), 1)
        src = rel.source_annotations.get()
        tgt = rel.target_annotations.get()
        self.assertNotEqual(src.document_id, tgt.document_id)

    def _build_sourceless_corpus_and_stage(self) -> TemporaryFileHandle:
        """Stage an export of a corpus whose docs have **no preserved source**.

        Two ``text/plain`` documents with no ``pdf_file`` (so the V2 exporter
        writes the single-NUL placeholder for each) plus a cross-doc
        relationship between one annotation on each. On reingest import both docs
        must take the baked fallback (``_source_is_reingestable`` is False), and
        the fan-in must still wire the relationship from their recorded id_maps.
        """
        labelset = LabelSet.objects.create(title="SL-LS", creator=self.user)
        labelset.annotation_labels.add(self.token_label, self.rel_label)
        with transaction.atomic():
            corpus = Corpus.objects.create(
                title="Source-less Corpus", creator=self.user, label_set=labelset
            )
            set_permissions_for_obj_to_user(self.user, corpus, [PermissionTypes.ALL])

        anns: list[Annotation] = []
        for idx in (1, 2):
            with transaction.atomic():
                doc = Document.objects.create(
                    title=f"Text Doc {idx}",
                    creator=self.user,
                    file_type="text/plain",
                    # No pdf_file -> exporter emits the NUL placeholder, so the
                    # importer cannot re-parse and must fall back to baked import.
                    txt_extract_file=ContentFile(
                        f"body of source-less doc {idx}".encode(), name=f"d{idx}.txt"
                    ),
                    page_count=1,
                    processing_started=timezone.now(),  # suppress source ingest
                )
                DocumentPath.objects.create(
                    document=doc,
                    corpus=corpus,
                    path=f"/text{idx}.txt",
                    version_number=1,
                    is_current=True,
                    is_deleted=False,
                    creator=self.user,
                )
                ann = Annotation.objects.create(
                    document=doc,
                    corpus=corpus,
                    annotation_label=self.token_label,
                    raw_text=f"span {idx}",
                    page=0,
                    annotation_type=TOKEN_LABEL,
                    json={"0": {"bounds": {}, "tokensJsons": [], "rawText": f"s{idx}"}},
                    creator=self.user,
                )
                set_permissions_for_obj_to_user(self.user, ann, [PermissionTypes.ALL])
            anns.append(ann)

        with transaction.atomic():
            rel = Relationship.objects.create(
                corpus=corpus,
                document=anns[0].document,
                relationship_label=self.rel_label,
                structural=False,
                creator=self.user,
            )
            rel.source_annotations.set([anns[0]])
            rel.target_annotations.set([anns[1]])
            set_permissions_for_obj_to_user(self.user, rel, [PermissionTypes.ALL])

        export = UserExport.objects.create(backend_lock=True, creator=self.user)
        package_corpus_export_v2(
            export_id=export.id, corpus_pk=corpus.id, include_conversations=False
        )
        export.refresh_from_db()
        temp_file = TemporaryFileHandle.objects.create()
        export.file.open("rb")
        temp_file.file.save("sourceless_import.zip", export.file)
        export.file.close()
        return temp_file

    def test_sourceless_docs_fall_back_to_baked_and_relationship_wires(self):
        """Reingest of source-less docs: baked fallback + cross-doc fan-in.

        Covers §8 test-case 10 — the path that now fires by default for every
        text-corpus reimport (reingest is opt-out at the user-facing boundary).
        """
        from opencontractserver.tasks.import_tasks_v2 import import_corpus_v2

        temp_file = self._build_sourceless_corpus_and_stage()
        imported_id = import_corpus_v2(
            temporary_file_handle_id=temp_file.id,
            user_id=self.user.id,
            seed_corpus_id=None,
            reingest_and_remap=True,
        )
        self.assertIsNotNone(imported_id)
        imported = Corpus.objects.get(id=imported_id)

        imported_docs = list(
            Document.objects.filter(
                pk__in=DocumentPath.objects.filter(
                    corpus=imported, is_current=True, is_deleted=False
                ).values_list("document_id", flat=True)
            )
        )
        self.assertEqual(len(imported_docs), 2)

        # Both docs imported baked (their text content survives) and unlocked.
        for doc in imported_docs:
            doc.refresh_from_db()
            self.assertFalse(doc.backend_lock, f"doc {doc.id} still locked")
            self.assertTrue(
                doc.txt_extract_file
                and doc.txt_extract_file.read().decode("utf-8").strip()
            )

        # Each source-less doc recorded a DONE fallback row: empty payload (no
        # deferred remap) but a populated id_map for the fan-in to aggregate.
        rows = PendingDocumentAnnotations.objects.filter(document__in=imported_docs)
        self.assertEqual(rows.count(), 2)
        for r in rows:
            self.assertEqual(r.status, PendingDocumentAnnotations.Status.DONE)
            self.assertEqual(r.payload, {})
            self.assertTrue(r.id_map, f"fallback row {r.pk} has empty id_map")

        # The annotations imported baked (synchronously), not deferred.
        self.assertEqual(
            Annotation.objects.filter(
                corpus=imported, annotation_label__text="OC_SECTION", structural=False
            ).count(),
            2,
        )

        # Coordination row finalized and the cross-doc relationship wired from
        # the aggregated fallback id_maps.
        coord = PendingCorpusImport.objects.get(corpus=imported)
        self.assertEqual(coord.status, PendingCorpusImport.Status.DONE)
        rels = Relationship.objects.filter(corpus=imported, structural=False)
        self.assertEqual(rels.count(), 1)
        rel = rels.get()
        self.assertNotEqual(
            rel.source_annotations.get().document_id,
            rel.target_annotations.get().document_id,
        )

    def test_default_path_unchanged_no_pending_rows(self):
        """``reingest_and_remap=False`` (import_corpus_v2 default) creates no rows."""
        from opencontractserver.tasks.import_tasks_v2 import import_corpus_v2

        temp_file = self._export_and_stage()
        imported_id = import_corpus_v2(
            temporary_file_handle_id=temp_file.id,
            user_id=self.user.id,
            seed_corpus_id=None,
        )
        self.assertIsNotNone(imported_id)
        imported = Corpus.objects.get(id=imported_id)

        self.assertFalse(PendingCorpusImport.objects.filter(corpus=imported).exists())
        self.assertFalse(
            PendingDocumentAnnotations.objects.filter(
                document__in=DocumentPath.objects.filter(corpus=imported).values_list(
                    "document_id", flat=True
                )
            ).exists()
        )
        # Default path wires the relationship synchronously.
        self.assertEqual(
            Relationship.objects.filter(corpus=imported, structural=False).count(),
            1,
        )


class TestServiceLevelOptOutDefault(TestCase):
    """The user-facing import service defaults reingest **on** (opt-out).

    ``import_corpus_export_for_user`` is the boundary where reingest becomes the
    default for a user uploading an export. The lower-level ``import_corpus``
    task keeps it off; the service must therefore queue the task with
    ``reingest_and_remap=True`` unless the caller overrides it.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username="opt_out_default_user", password="pw", is_usage_capped=False
        )
        # Smallest archive that passes the synchronous ZIP-magic peek. The
        # queued celery task is mocked, so its contents are never parsed.
        import io
        import zipfile

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("data.json", "{}")
        self.zip_bytes = buf.getvalue()

    def _queued_reingest_flag(self, **service_kwargs):
        """Call the service with the task patched; return the queued flag."""
        from unittest.mock import patch

        from opencontractserver.document_imports import services

        with patch.object(services, "import_corpus") as mock_task:
            services.import_corpus_export_for_user(
                user=self.user,
                zip_source=self.zip_bytes,
                **service_kwargs,
            )
        mock_task.s.assert_called_once()
        return mock_task.s.call_args.kwargs.get("reingest_and_remap")

    def test_default_queues_reingest_on(self):
        self.assertIs(self._queued_reingest_flag(), True)

    def test_explicit_false_opts_out(self):
        self.assertIs(self._queued_reingest_flag(reingest_and_remap=False), False)
