"""
Tests for annotation sidecar import via the zip-to-corpus pipeline.

These tests verify the ability to import pre-annotated documents by
including a co-located .json sidecar (OpenContractDocExport format)
alongside the source document file in a zip upload, exercising the
``import_zip_with_folder_structure`` celery task that backs the
``POST /api/imports/zip-to-corpus/`` REST endpoint.

Uses real PDF fixtures and realistic PAWLs/annotation data — no mocks.
"""

import io
import json
import logging
import zipfile

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.db import transaction
from django.test import TestCase

from opencontractserver.corpuses.models import Corpus, TemporaryFileHandle
from opencontractserver.documents.models import (
    DocumentPath,
    PendingDocumentAnnotations,
)
from opencontractserver.tasks.import_tasks import (
    import_zip_with_folder_structure,
)
from opencontractserver.tests.fixtures import (
    SAMPLE_PDF_FILE_ONE_PATH,
    SAMPLE_PDF_FILE_TWO_PATH,
)
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.importing import validate_labels_data
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()
logger = logging.getLogger(__name__)


def _build_sidecar_json(
    annotations: list[dict] | None = None,
    doc_labels: list[str] | None = None,
    relationships: list[dict] | None = None,
) -> dict:
    """
    Build a dumb-anchor sidecar dict in the NEW importer format.

    The new sidecar is a flat ``{"annotations": [...], "doc_labels": [...]}``
    document (plus an optional ``"relationships": [...]`` list of annotation-to-
    annotation edges). Each annotation is a label/rawText anchor with either a
    page+bbox (PDF) or start+end (span) locator — there is no PAWLs content,
    no ``content``, no ``skip_pipeline``, and no ``tokensJsons``. The importer
    persists this payload verbatim into a ``PendingDocumentAnnotations`` row
    for post-ingest re-anchoring (and relationship wiring) by
    ``remap_pending_annotations``.
    """
    if annotations is None:
        annotations = []

    if doc_labels is None:
        doc_labels = []

    sidecar: dict = {
        "annotations": annotations,
        "doc_labels": doc_labels,
    }
    if relationships is not None:
        sidecar["relationships"] = relationships
    return sidecar


def _build_labels_json(
    text_labels: dict | None = None,
    doc_labels: dict | None = None,
) -> dict:
    """Build a labels.json for inclusion in a zip."""
    return {
        "text_labels": text_labels or {},
        "doc_labels": doc_labels or {},
    }


def _make_annotation(
    annot_id: int,
    raw_text: str,
    label_name: str,
    page: int = 0,
    token_start: int = 0,  # retained for call-site compatibility (unused)
    token_end: int = 1,  # retained for call-site compatibility (unused)
) -> dict:
    """Build a dumb-anchor annotation dict (page + bbox locator)."""
    return {
        "id": annot_id,
        "label": label_name,
        "rawText": raw_text,
        "page": page,
        "bbox": {"left": 50, "top": 50, "right": 200, "bottom": 70},
    }


def _make_span_annotation(
    annot_id: int,
    raw_text: str,
    label_name: str,
    start: int,
    end: int,
) -> dict:
    """Build a dumb-anchor annotation dict (start/end span locator)."""
    return {
        "id": annot_id,
        "label": label_name,
        "rawText": raw_text,
        "start": start,
        "end": end,
    }


def _make_label_data(
    text: str,
    label_type: str = "TOKEN_LABEL",
    description: str = "",
    color: str = "#FF0000",
) -> dict:
    """Build a realistic AnnotationLabelPythonType dict."""
    return {
        "text": text,
        "label_type": label_type,
        "description": description or f"Label for {text}",
        "color": color,
        "icon": "tag",
    }


class _SidecarImportTestMixin:
    """
    Shared zip/handle plumbing for sidecar import test classes.

    Centralizes the in-memory zip builder and ``TemporaryFileHandle`` factory
    so test classes that exercise the sidecar import pipeline don't redefine
    the same helpers. The ``handle_name`` class attribute lets subclasses
    distinguish their uploaded zip filename for log/debug traceability.
    """

    handle_name: str = "test_sidecar_import.zip"

    @staticmethod
    def _create_test_zip(files: dict[str, bytes]) -> io.BytesIO:
        """Create an in-memory zip file from a {path: bytes} mapping."""
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for name, content in files.items():
                zf.writestr(name, content)
        buffer.seek(0)
        return buffer

    def _create_temp_file_handle(self, zip_buffer: io.BytesIO) -> TemporaryFileHandle:
        """Create a ``TemporaryFileHandle`` from a zip buffer."""
        zip_content = ContentFile(zip_buffer.read(), name=self.handle_name)
        return TemporaryFileHandle.objects.create(file=zip_content)


class TestSidecarDetectionInManifest(TestCase):
    """Tests for sidecar/labels detection in zip validation."""

    def test_json_sidecar_detected_for_pdf(self):
        """A .json file with same stem as a .pdf is detected as sidecar."""
        from opencontractserver.utils.zip_security import validate_zip_for_import

        pdf_bytes = SAMPLE_PDF_FILE_ONE_PATH.read_bytes()
        sidecar = json.dumps(_build_sidecar_json()).encode("utf-8")

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("doc.pdf", pdf_bytes)
            zf.writestr("doc.json", sidecar)
        buffer.seek(0)

        with zipfile.ZipFile(buffer, "r") as zf:
            manifest = validate_zip_for_import(zf)

        self.assertTrue(manifest.is_valid)
        self.assertIn("doc.pdf", manifest.annotation_sidecars)
        self.assertEqual(manifest.annotation_sidecars["doc.pdf"], "doc.json")
        # The sidecar should NOT appear in valid_files
        valid_paths = [e.sanitized_path for e in manifest.valid_files]
        self.assertNotIn("doc.json", valid_paths)
        self.assertIn("doc.pdf", valid_paths)

    def test_json_sidecar_detected_in_subfolder(self):
        """Sidecars in subfolders are matched correctly."""
        from opencontractserver.utils.zip_security import validate_zip_for_import

        pdf_bytes = SAMPLE_PDF_FILE_ONE_PATH.read_bytes()
        sidecar = json.dumps(_build_sidecar_json()).encode("utf-8")

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("contracts/master.pdf", pdf_bytes)
            zf.writestr("contracts/master.json", sidecar)
        buffer.seek(0)

        with zipfile.ZipFile(buffer, "r") as zf:
            manifest = validate_zip_for_import(zf)

        self.assertTrue(manifest.is_valid)
        self.assertIn("contracts/master.pdf", manifest.annotation_sidecars)

    def test_standalone_json_not_treated_as_sidecar(self):
        """A .json file without a matching document stays in valid_files."""
        from opencontractserver.utils.zip_security import validate_zip_for_import

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("data.json", b'{"key": "value"}')
        buffer.seek(0)

        with zipfile.ZipFile(buffer, "r") as zf:
            manifest = validate_zip_for_import(zf)

        self.assertTrue(manifest.is_valid)
        self.assertEqual(len(manifest.annotation_sidecars), 0)
        valid_paths = [e.sanitized_path for e in manifest.valid_files]
        self.assertIn("data.json", valid_paths)

    def test_labels_file_detected(self):
        """labels.json at root is detected as the labels file."""
        from opencontractserver.utils.zip_security import validate_zip_for_import

        pdf_bytes = SAMPLE_PDF_FILE_ONE_PATH.read_bytes()
        labels = json.dumps(_build_labels_json()).encode("utf-8")

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("doc.pdf", pdf_bytes)
            zf.writestr("labels.json", labels)
        buffer.seek(0)

        with zipfile.ZipFile(buffer, "r") as zf:
            manifest = validate_zip_for_import(zf)

        self.assertTrue(manifest.is_valid)
        self.assertEqual(manifest.labels_file, "labels.json")
        # labels.json should not be in valid_files or sidecars
        valid_paths = [e.sanitized_path for e in manifest.valid_files]
        self.assertNotIn("labels.json", valid_paths)
        self.assertNotIn("labels.json", manifest.annotation_sidecars)

    def test_labels_json_in_subfolder_not_detected_as_labels_file(self):
        """labels.json in a subfolder should NOT be detected as the labels file."""
        from opencontractserver.utils.zip_security import validate_zip_for_import

        pdf_bytes = SAMPLE_PDF_FILE_ONE_PATH.read_bytes()

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("docs/labels.pdf", pdf_bytes)
            zf.writestr("docs/labels.json", b'{"text_labels": {}}')
        buffer.seek(0)

        with zipfile.ZipFile(buffer, "r") as zf:
            manifest = validate_zip_for_import(zf)

        self.assertTrue(manifest.is_valid)
        # Should NOT be the root labels file
        self.assertIsNone(manifest.labels_file)
        # Should be detected as a sidecar for docs/labels.pdf
        self.assertIn("docs/labels.pdf", manifest.annotation_sidecars)

    def test_multiple_labels_files_uses_first(self):
        """When both labels.json and LABELS.json exist, only the first is used."""
        from opencontractserver.utils.zip_security import validate_zip_for_import

        pdf_bytes = SAMPLE_PDF_FILE_ONE_PATH.read_bytes()
        sidecar = json.dumps(_build_sidecar_json()).encode("utf-8")

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("doc.pdf", pdf_bytes)
            zf.writestr("doc.json", sidecar)
            zf.writestr("labels.json", b'{"text_labels": {}, "doc_labels": {}}')
            zf.writestr("LABELS.json", b'{"text_labels": {}, "doc_labels": {}}')
        buffer.seek(0)

        with zipfile.ZipFile(buffer, "r") as zf:
            manifest = validate_zip_for_import(zf)

        self.assertTrue(manifest.is_valid)
        # First labels file should be used
        self.assertIsNotNone(manifest.labels_file)

    def test_mixed_sidecar_and_plain_documents(self):
        """Zip with some docs having sidecars and others without."""
        from opencontractserver.utils.zip_security import validate_zip_for_import

        pdf_bytes = SAMPLE_PDF_FILE_ONE_PATH.read_bytes()
        sidecar = json.dumps(_build_sidecar_json()).encode("utf-8")

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("annotated.pdf", pdf_bytes)
            zf.writestr("annotated.json", sidecar)
            zf.writestr("plain.pdf", pdf_bytes)
            zf.writestr("labels.json", b'{"text_labels": {}, "doc_labels": {}}')
        buffer.seek(0)

        with zipfile.ZipFile(buffer, "r") as zf:
            manifest = validate_zip_for_import(zf)

        self.assertTrue(manifest.is_valid)
        self.assertEqual(len(manifest.annotation_sidecars), 1)
        self.assertIn("annotated.pdf", manifest.annotation_sidecars)
        valid_paths = [e.sanitized_path for e in manifest.valid_files]
        self.assertIn("annotated.pdf", valid_paths)
        self.assertIn("plain.pdf", valid_paths)
        # Sidecar JSON and labels.json excluded from valid_files
        self.assertNotIn("annotated.json", valid_paths)
        self.assertNotIn("labels.json", valid_paths)


class TestSidecarImportTask(_SidecarImportTestMixin, TestCase):
    """
    Integration tests for dumb-anchor sidecar import via the
    import_zip_with_folder_structure Celery task.

    The importer does NOT apply annotations inline and no longer dispatches its
    own Celery chain. It creates the document through the normal parser pipeline
    and persists the producer (dumb-anchor) annotations in a
    ``PendingDocumentAnnotations`` row stamped with the import's run id. The
    standard Document post_save chain (``extract_thumbnail -> ingest_doc ->
    remap_pending_annotations -> set_doc_lock_state``) then runs the remap after
    PAWLs / text exist. These tests assert the persisted pending row + its
    payload; end-to-end re-anchoring through the chain is covered by the
    post-ingest integration tests (``TestDumbAnchorRemapThroughChain``).
    """

    def setUp(self):
        """Set up test user, corpus, and load real fixture data."""
        with transaction.atomic():
            self.user = User.objects.create_user(
                username="sidecar_user", password="testpass"
            )

        with transaction.atomic():
            self.corpus = Corpus.objects.create(
                title="Sidecar Test Corpus",
                description="Corpus for testing sidecar import",
                creator=self.user,
            )
            set_permissions_for_obj_to_user(
                self.user, self.corpus, [PermissionTypes.ALL]
            )

        self.pdf_bytes = SAMPLE_PDF_FILE_ONE_PATH.read_bytes()
        self.pdf_bytes_2 = SAMPLE_PDF_FILE_TWO_PATH.read_bytes()

    def _run_import(self, files: dict[str, bytes], job_id: str) -> dict:
        """Run the importer and capture (but do NOT execute) any on_commit callbacks.

        The importer no longer dispatches its own ingest chain — the standard
        Document post_save chain (signal-owned) does, and that signal is
        disconnected in these unit tests. We capture with ``execute=False`` so
        any on_commit callbacks are not run inline (running the real chain would
        invoke the parser pipeline, out of scope here). These tests assert the
        importer persists the ``PendingDocumentAnnotations`` row; full
        re-anchoring through the chain is covered by the post-ingest integration
        suite (``TestDumbAnchorRemapThroughChain``). ``self.captured`` holds the
        captured callbacks for the most recent import.
        """
        zip_buffer = self._create_test_zip(files)
        handle = self._create_temp_file_handle(zip_buffer)
        with self.captureOnCommitCallbacks(execute=False) as callbacks:
            result = import_zip_with_folder_structure.apply(
                kwargs={
                    "temporary_file_handle_id": handle.id,
                    "user_id": self.user.id,
                    "job_id": job_id,
                    "corpus_id": self.corpus.id,
                }
            ).get()
        self.captured = callbacks
        return result

    def test_single_annotated_document_persists_pending_row(self):
        """A dumb-anchor sidecar persists a PendingDocumentAnnotations row."""
        annotations = [
            _make_annotation(1, "Exhibit", "Heading", page=0),
            _make_span_annotation(2, "Certain information", "Clause", start=10, end=29),
        ]
        sidecar = _build_sidecar_json(
            annotations=annotations,
            doc_labels=["Contract"],
        )
        files = {
            "agreement.pdf": self.pdf_bytes,
            "agreement.json": json.dumps(sidecar).encode("utf-8"),
        }

        result = self._run_import(files, "test-sidecar-1")

        self.assertTrue(result["completed"], f"Errors: {result.get('errors')}")
        self.assertTrue(result["success"], f"Errors: {result.get('errors')}")
        self.assertEqual(result["files_processed"], 1)
        self.assertEqual(result["annotation_sidecars_found"], 1)
        self.assertEqual(result["pending_annotation_docs"], 1)
        # New importer applies NO annotations inline.
        self.assertEqual(result["annotations_imported"], 0)
        # The deferred path tracks work via ``pending_annotation_docs``; the old
        # ``annotation_sidecars_processed`` counter was removed as dead (always 0).
        self.assertNotIn("annotation_sidecars_processed", result)

        # Document was created in the corpus.
        doc_paths = DocumentPath.objects.filter(corpus=self.corpus)
        self.assertEqual(doc_paths.count(), 1)
        corpus_doc = doc_paths.first().document

        # Exactly one pending row, carrying the verbatim dumb-anchor payload.
        pending = PendingDocumentAnnotations.objects.filter(document=corpus_doc)
        self.assertEqual(pending.count(), 1)
        row = pending.first()
        self.assertEqual(row.corpus_id, self.corpus.id)
        self.assertEqual(row.creator_id, self.user.id)
        self.assertEqual(row.status, PendingDocumentAnnotations.Status.PENDING)
        self.assertEqual(row.payload["annotations"], annotations)
        self.assertEqual(row.payload["doc_labels"], ["Contract"])
        # The deferred set is stamped with this import's ingestion run id so the
        # standard chain's remap step (and later relationship wiring) can group
        # and gate it.
        self.assertIsNotNone(row.ingestion_run_id)

    def test_sidecar_relationships_captured_into_pending_payload(self):
        """A sidecar's ``relationships`` list is persisted verbatim on the
        pending row (not dropped/errored) for deferred wiring at remap time."""
        annotations = [
            _make_annotation(1, "Master Agreement", "Heading", page=0),
            _make_annotation(2, "Schedule A", "Heading", page=0),
        ]
        relationships = [
            {
                "id": "r1",
                "relationshipLabel": "REFERENCES",
                "source_annotation_ids": [1],
                "target_annotation_ids": [2],
            }
        ]
        sidecar = _build_sidecar_json(
            annotations=annotations, relationships=relationships
        )
        files = {
            "agreement.pdf": self.pdf_bytes,
            "agreement.json": json.dumps(sidecar).encode("utf-8"),
        }

        result = self._run_import(files, "test-sidecar-rels")

        self.assertTrue(result["success"], f"Errors: {result.get('errors')}")
        self.assertEqual(result["pending_annotation_docs"], 1)
        # Relationships are captured, not dropped — the old drop-and-warn that
        # appended to results["errors"] is gone.
        self.assertEqual(result["sidecar_relationships_found"], 1)
        self.assertEqual(
            result["errors"], [], msg=f"Unexpected errors: {result['errors']}"
        )

        row = PendingDocumentAnnotations.objects.get()
        self.assertEqual(row.payload["relationships"], relationships)
        self.assertEqual(row.status, PendingDocumentAnnotations.Status.PENDING)

    def test_sidecar_without_relationships_persists_empty_list(self):
        """A sidecar with no ``relationships`` key still persists an empty list
        so the remap's ``payload.get('relationships')`` is always well-formed."""
        annotations = [_make_annotation(1, "Heading", "Heading", page=0)]
        sidecar = _build_sidecar_json(annotations=annotations)
        files = {
            "doc.pdf": self.pdf_bytes,
            "doc.json": json.dumps(sidecar).encode("utf-8"),
        }

        result = self._run_import(files, "test-sidecar-no-rels")

        self.assertTrue(result["success"], f"Errors: {result.get('errors')}")
        self.assertEqual(result["sidecar_relationships_found"], 0)
        row = PendingDocumentAnnotations.objects.get()
        self.assertEqual(row.payload["relationships"], [])

    def test_sidecar_without_doc_labels_persists_empty_list(self):
        """A sidecar with only span annotations persists doc_labels=[]."""
        annotations = [
            _make_span_annotation(1, "Hello world", "Phrase", start=0, end=11),
        ]
        sidecar = _build_sidecar_json(annotations=annotations)
        files = {
            "doc.pdf": self.pdf_bytes,
            "doc.json": json.dumps(sidecar).encode("utf-8"),
        }

        result = self._run_import(files, "test-sidecar-span")

        self.assertTrue(result["success"], f"Errors: {result.get('errors')}")
        self.assertEqual(result["pending_annotation_docs"], 1)
        row = PendingDocumentAnnotations.objects.get()
        self.assertEqual(row.payload["annotations"], annotations)
        self.assertEqual(row.payload["doc_labels"], [])

    def test_malformed_dumb_anchor_with_labels_json_persists_failed_row(self):
        """When a labels.json ships alongside a dumb-anchor sidecar, the sidecar
        is pre-flight validated and a malformed payload is persisted FAILED.

        The validator's label-resolution check is defined against labels.json,
        so it only runs when one is present. Here a label is missing entirely
        (an empty string) and the row's anchor is fine — the import must NOT
        silently queue a doomed remap; it persists the pending row as FAILED
        with the validation errors in its ``report`` and surfaces an error,
        co-locating the failure with the import.
        """
        annotations = [
            # Valid, label resolves in labels.json below.
            _make_annotation(1, "Heading", "OC_SECTION", page=0),
            # Malformed: empty label → fails dumb-anchor schema.
            _make_annotation(2, "Body", "", page=0),
        ]
        sidecar = _build_sidecar_json(annotations=annotations)
        labels = _build_labels_json(
            text_labels={"OC_SECTION": _make_label_data("OC_SECTION")}
        )
        files = {
            "agreement.pdf": self.pdf_bytes,
            "agreement.json": json.dumps(sidecar).encode("utf-8"),
            "labels.json": json.dumps(labels).encode("utf-8"),
        }

        result = self._run_import(files, "test-sidecar-malformed")

        # Document still ingests; only the annotation set is rejected.
        self.assertTrue(result["completed"], f"Errors: {result.get('errors')}")
        self.assertEqual(result["pending_annotation_docs"], 1)
        self.assertEqual(result["annotation_sidecars_errored"], 1)
        self.assertTrue(
            any("failed validation" in e for e in result["errors"]),
            msg=f"Expected a validation error surfaced: {result['errors']}",
        )

        # Pending row is persisted FAILED (never silently dropped) with the
        # validation errors recorded on its report so remap skips it.
        row = PendingDocumentAnnotations.objects.get()
        self.assertEqual(row.status, PendingDocumentAnnotations.Status.FAILED)
        self.assertTrue(
            row.report and any("error" in entry for entry in row.report),
            msg=f"Expected validation errors on report: {row.report}",
        )

    def test_empty_annotations_list_still_persists_pending_row(self):
        """A sidecar with an empty ``annotations`` list is still NEW-format.

        The list being present (even if empty) identifies the dumb-anchor
        format, so a pending row is created (the remap is a downstream no-op).
        """
        sidecar = _build_sidecar_json(annotations=[], doc_labels=["Contract"])
        files = {
            "doc.pdf": self.pdf_bytes,
            "doc.json": json.dumps(sidecar).encode("utf-8"),
        }

        result = self._run_import(files, "test-sidecar-empty")

        self.assertTrue(result["success"], f"Errors: {result.get('errors')}")
        self.assertEqual(result["pending_annotation_docs"], 1)
        row = PendingDocumentAnnotations.objects.get()
        self.assertEqual(row.payload["annotations"], [])
        self.assertEqual(row.payload["doc_labels"], ["Contract"])

    def test_sidecar_in_subfolder_persists_pending_row(self):
        """A sidecar co-located in a subfolder is detected and persisted."""
        annotations = [_make_annotation(1, "Heading", "Heading", page=0)]
        sidecar = _build_sidecar_json(annotations=annotations)
        files = {
            "contracts/master.pdf": self.pdf_bytes,
            "contracts/master.json": json.dumps(sidecar).encode("utf-8"),
        }

        result = self._run_import(files, "test-sidecar-subfolder")

        self.assertTrue(result["success"], f"Errors: {result.get('errors')}")
        self.assertEqual(result["pending_annotation_docs"], 1)
        self.assertEqual(PendingDocumentAnnotations.objects.count(), 1)

    def test_multiple_annotated_documents_each_get_pending_row(self):
        """Each annotated document gets its own pending row."""
        sidecar_a = _build_sidecar_json(
            annotations=[
                _make_annotation(1, "A1", "Heading", page=0),
                _make_annotation(2, "A2", "Heading", page=0),
            ],
            doc_labels=["Contract"],
        )
        sidecar_b = _build_sidecar_json(
            annotations=[_make_annotation(3, "B1", "Heading", page=0)],
        )
        files = {
            "doc_a.pdf": self.pdf_bytes,
            "doc_a.json": json.dumps(sidecar_a).encode("utf-8"),
            "doc_b.pdf": self.pdf_bytes_2,
            "doc_b.json": json.dumps(sidecar_b).encode("utf-8"),
        }

        result = self._run_import(files, "test-sidecar-multi")

        self.assertTrue(result["success"], f"Errors: {result.get('errors')}")
        self.assertEqual(result["files_processed"], 2)
        self.assertEqual(result["pending_annotation_docs"], 2)
        self.assertEqual(PendingDocumentAnnotations.objects.count(), 2)

    def test_mixed_sidecar_and_plain_documents(self):
        """A plain (no-sidecar) document gets NO pending row."""
        sidecar = _build_sidecar_json(
            annotations=[_make_annotation(1, "Heading", "Heading", page=0)],
        )
        files = {
            "annotated.pdf": self.pdf_bytes,
            "annotated.json": json.dumps(sidecar).encode("utf-8"),
            "plain.pdf": self.pdf_bytes_2,
        }

        result = self._run_import(files, "test-sidecar-mixed")

        self.assertTrue(result["success"], f"Errors: {result.get('errors')}")
        self.assertEqual(result["files_processed"], 2)
        # Only the annotated document yields a pending row.
        self.assertEqual(result["pending_annotation_docs"], 1)
        self.assertEqual(PendingDocumentAnnotations.objects.count(), 1)

    def test_zip_without_any_sidecars_unchanged_behavior(self):
        """A zip with no sidecars creates docs but no pending rows."""
        files = {
            "a.pdf": self.pdf_bytes,
            "b.pdf": self.pdf_bytes_2,
        }

        result = self._run_import(files, "test-no-sidecar")

        self.assertTrue(result["success"], f"Errors: {result.get('errors')}")
        self.assertEqual(result["files_processed"], 2)
        self.assertEqual(result["annotation_sidecars_found"], 0)
        self.assertEqual(result["pending_annotation_docs"], 0)
        self.assertEqual(PendingDocumentAnnotations.objects.count(), 0)

    def test_malformed_sidecar_json_records_error_and_no_pending_row(self):
        """A sidecar that is not valid JSON is reported; the doc still imports."""
        files = {
            "doc.pdf": self.pdf_bytes,
            "doc.json": b"{ this is not valid json ]",
        }

        result = self._run_import(files, "test-malformed-sidecar")

        # The document is still created via the pipeline (sidecar is best-effort).
        self.assertEqual(result["files_processed"], 1)
        self.assertEqual(result["annotation_sidecars_errored"], 1)
        self.assertEqual(result["pending_annotation_docs"], 0)
        self.assertEqual(PendingDocumentAnnotations.objects.count(), 0)
        self.assertTrue(
            any("Sidecar read error" in e for e in result["errors"]),
            f"Expected a sidecar read error in {result['errors']}",
        )


class TestSidecarUpversioning(_SidecarImportTestMixin, TestCase):
    """
    Intersection of dumb-anchor sidecar import + path-collision upversioning.

    Verifies that when a zip containing a document AND its dumb-anchor sidecar
    is imported at a path that already has a Document, the NEW Document version
    receives its own ``PendingDocumentAnnotations`` row, while the prior
    version's pending row remains attached to the prior (now non-current)
    Document. Pending rows are NOT migrated between versions: each Document row
    owns its own pending payload, tied by FK to that specific version.
    """

    handle_name = "test_sidecar_upversion.zip"

    def setUp(self):
        with transaction.atomic():
            self.user = User.objects.create_user(
                username="upversion_sidecar_user", password="testpass"
            )

        with transaction.atomic():
            self.corpus = Corpus.objects.create(
                title="Sidecar Upversion Corpus",
                description="Corpus for sidecar+upversion intersection tests",
                creator=self.user,
            )
            set_permissions_for_obj_to_user(
                self.user, self.corpus, [PermissionTypes.ALL]
            )

        self.pdf_bytes_v1 = SAMPLE_PDF_FILE_ONE_PATH.read_bytes()
        self.pdf_bytes_v2 = SAMPLE_PDF_FILE_TWO_PATH.read_bytes()

    def _run_import(self, files: dict[str, bytes], job_id: str) -> dict:
        # execute=False: queue the ingest chain without running the real
        # parser pipeline (see TestSidecarImportTask._run_import).
        handle = self._create_temp_file_handle(self._create_test_zip(files))
        with self.captureOnCommitCallbacks(execute=False):
            return import_zip_with_folder_structure.apply(
                kwargs={
                    "temporary_file_handle_id": handle.id,
                    "user_id": self.user.id,
                    "job_id": job_id,
                    "corpus_id": self.corpus.id,
                }
            ).get()

    def test_pending_rows_attach_to_their_own_version(self):
        """
        Importing a sidecar+document at an existing path:
        - creates a new Document version (same version_tree_id, parent=v1)
        - attaches v2's pending row to the NEW Document
        - leaves v1's pending row attached to the now-non-current v1 Document
        - increments DocumentPath.version_number and re-links the path chain
        """
        # --- v1 import ---
        annotations_v1 = [_make_annotation(1, "Original Heading", "Heading", page=0)]
        sidecar_v1 = _build_sidecar_json(
            annotations=annotations_v1, doc_labels=["Contract"]
        )
        files_v1 = {
            "filings/master.pdf": self.pdf_bytes_v1,
            "filings/master.json": json.dumps(sidecar_v1).encode("utf-8"),
        }
        result_v1 = self._run_import(files_v1, "test-sidecar-upversion-v1")

        self.assertTrue(result_v1["success"], f"Errors: {result_v1.get('errors')}")
        self.assertEqual(result_v1["files_processed"], 1)
        self.assertEqual(result_v1["files_upversioned"], 0)
        self.assertEqual(result_v1["pending_annotation_docs"], 1)

        v1_path = DocumentPath.objects.get(
            corpus=self.corpus,
            path="/filings/master.pdf",
            is_current=True,
            is_deleted=False,
        )
        self.assertEqual(v1_path.version_number, 1)
        v1_doc = v1_path.document

        v1_pending = PendingDocumentAnnotations.objects.get(document=v1_doc)
        self.assertEqual(v1_pending.payload["annotations"], annotations_v1)
        self.assertEqual(v1_pending.payload["doc_labels"], ["Contract"])

        # --- v2 import: same path, different content + sidecar ---
        annotations_v2 = [
            _make_annotation(10, "Revised Heading", "Heading", page=0),
            _make_annotation(11, "New Section", "Section", page=0),
        ]
        sidecar_v2 = _build_sidecar_json(
            annotations=annotations_v2, doc_labels=["Amendment"]
        )
        files_v2 = {
            "filings/master.pdf": self.pdf_bytes_v2,
            "filings/master.json": json.dumps(sidecar_v2).encode("utf-8"),
        }
        result_v2 = self._run_import(files_v2, "test-sidecar-upversion-v2")

        self.assertTrue(result_v2["success"], f"Errors: {result_v2.get('errors')}")
        self.assertEqual(result_v2["files_processed"], 1)
        self.assertEqual(result_v2["files_upversioned"], 1)
        self.assertIn("/filings/master.pdf", result_v2["upversioned_paths"])
        self.assertEqual(result_v2["pending_annotation_docs"], 1)

        # --- Path tree assertions ---
        v1_path.refresh_from_db()
        self.assertFalse(v1_path.is_current)

        v2_path = DocumentPath.objects.get(
            corpus=self.corpus,
            path="/filings/master.pdf",
            is_current=True,
            is_deleted=False,
        )
        self.assertEqual(v2_path.version_number, 2)
        self.assertEqual(v2_path.parent, v1_path)

        # --- Content tree assertions ---
        v2_doc = v2_path.document
        self.assertNotEqual(v2_doc.id, v1_doc.id)
        self.assertEqual(v2_doc.version_tree_id, v1_doc.version_tree_id)
        self.assertEqual(v2_doc.parent, v1_doc)

        # --- Pending rows are scoped to their own version ---
        v2_pending = PendingDocumentAnnotations.objects.get(document=v2_doc)
        self.assertEqual(v2_pending.payload["annotations"], annotations_v2)
        self.assertEqual(v2_pending.payload["doc_labels"], ["Amendment"])

        # v1's pending row is unchanged and still attached to v1.
        v1_pending.refresh_from_db()
        self.assertEqual(v1_pending.payload["annotations"], annotations_v1)
        self.assertEqual(v1_pending.document_id, v1_doc.id)

        # Exactly two pending rows total (one per version), no migration.
        self.assertEqual(
            PendingDocumentAnnotations.objects.filter(
                document__version_tree_id=v1_doc.version_tree_id
            ).count(),
            2,
        )


class TestValidateLabelsData(TestCase):
    """Unit tests for validate_labels_data schema validation."""

    def _validate(self, data):
        return validate_labels_data(data)

    # --- Top-level structure ---

    def test_valid_labels_data(self):
        """Well-formed labels.json produces no errors."""
        data = _build_labels_json(
            text_labels={"Heading": _make_label_data("Heading")},
            doc_labels={"Contract": _make_label_data("Contract", "DOC_TYPE_LABEL")},
        )
        self.assertEqual(self._validate(data), [])

    def test_empty_sections_valid(self):
        """Empty text_labels and doc_labels dicts are valid."""
        self.assertEqual(self._validate({"text_labels": {}, "doc_labels": {}}), [])

    def test_missing_sections_valid(self):
        """Omitting both sections entirely is valid (no labels to import)."""
        self.assertEqual(self._validate({}), [])

    def test_top_level_not_dict(self):
        """Non-dict top-level value is rejected."""
        errors = self._validate(["not", "a", "dict"])
        self.assertEqual(len(errors), 1)
        self.assertIn("must be a JSON object", errors[0])

    def test_top_level_string(self):
        """String top-level value is rejected."""
        errors = self._validate("just a string")
        self.assertEqual(len(errors), 1)
        self.assertIn("must be a JSON object", errors[0])

    # --- Section-level structure ---

    def test_text_labels_as_list(self):
        """text_labels as a list instead of dict is rejected."""
        errors = self._validate({"text_labels": [{"text": "Heading"}]})
        self.assertEqual(len(errors), 1)
        self.assertIn("text_labels", errors[0])
        self.assertIn("must be a JSON object", errors[0])

    def test_doc_labels_as_list(self):
        """doc_labels as a list instead of dict is rejected."""
        errors = self._validate({"doc_labels": ["Contract"]})
        self.assertEqual(len(errors), 1)
        self.assertIn("doc_labels", errors[0])

    def test_both_sections_as_lists(self):
        """Both sections as lists produce two errors."""
        errors = self._validate({"text_labels": [], "doc_labels": []})
        self.assertEqual(len(errors), 2)

    # --- Label entry structure ---

    def test_label_entry_not_dict(self):
        """A label entry that is a string instead of dict is rejected."""
        errors = self._validate({"text_labels": {"Heading": "not a dict"}})
        self.assertEqual(len(errors), 1)
        self.assertIn("must be a JSON object", errors[0])

    def test_missing_text_field(self):
        """A label entry missing the 'text' field is rejected."""
        errors = self._validate(
            {"text_labels": {"Heading": {"label_type": "TOKEN_LABEL", "color": "#FFF"}}}
        )
        self.assertEqual(len(errors), 1)
        self.assertIn("missing required field 'text'", errors[0])

    def test_empty_text_field(self):
        """A label entry with empty string 'text' is rejected."""
        errors = self._validate(
            {"text_labels": {"Heading": {"text": "  ", "label_type": "TOKEN_LABEL"}}}
        )
        self.assertEqual(len(errors), 1)
        self.assertIn("non-empty string", errors[0])

    def test_text_field_wrong_type(self):
        """A label entry with non-string 'text' is rejected."""
        errors = self._validate({"text_labels": {"Heading": {"text": 123}}})
        self.assertEqual(len(errors), 1)
        self.assertIn("non-empty string", errors[0])

    # --- Optional field type checks ---

    def test_color_as_integer(self):
        """color as integer instead of string is rejected."""
        label = _make_label_data("Heading")
        label["color"] = 0xFF0000
        errors = self._validate({"text_labels": {"Heading": label}})
        self.assertEqual(len(errors), 1)
        self.assertIn("'color' must be a string", errors[0])

    def test_icon_as_integer(self):
        """icon as integer instead of string is rejected."""
        label = _make_label_data("Heading")
        label["icon"] = 42
        errors = self._validate({"text_labels": {"Heading": label}})
        self.assertEqual(len(errors), 1)
        self.assertIn("'icon' must be a string", errors[0])

    def test_description_as_integer(self):
        """description as integer instead of string is rejected."""
        label = _make_label_data("Heading")
        label["description"] = 99
        errors = self._validate({"text_labels": {"Heading": label}})
        self.assertEqual(len(errors), 1)
        self.assertIn("'description' must be a string", errors[0])

    def test_invalid_label_type(self):
        """Unrecognised label_type string is rejected."""
        label = _make_label_data("Heading")
        label["label_type"] = "INVALID_TYPE"
        errors = self._validate({"text_labels": {"Heading": label}})
        self.assertEqual(len(errors), 1)
        self.assertIn("invalid label_type", errors[0])

    def test_label_type_wrong_type(self):
        """label_type as integer is rejected."""
        label = _make_label_data("Heading")
        label["label_type"] = 1
        errors = self._validate({"text_labels": {"Heading": label}})
        self.assertEqual(len(errors), 1)
        self.assertIn("'label_type' must be a string", errors[0])

    # --- Multiple errors ---

    def test_multiple_bad_labels(self):
        """Multiple malformed labels in the same section produce multiple errors."""
        errors = self._validate(
            {
                "text_labels": {
                    "A": {"label_type": "TOKEN_LABEL"},  # missing text
                    "B": "just a string",  # not a dict
                    "C": {"text": "", "color": 123},  # empty text + bad color
                }
            }
        )
        self.assertGreaterEqual(len(errors), 3)


class TestMalformedLabelsImport(_SidecarImportTestMixin, TestCase):
    """
    Integration tests verifying that malformed labels.json is rejected
    gracefully during import_zip_with_folder_structure.
    """

    handle_name = "test_labels_validation.zip"

    def setUp(self):
        with transaction.atomic():
            self.user = User.objects.create_user(
                username="labels_validation_user", password="testpass"
            )

        with transaction.atomic():
            self.corpus = Corpus.objects.create(
                title="Labels Validation Corpus",
                description="Corpus for testing labels validation",
                creator=self.user,
            )
            set_permissions_for_obj_to_user(
                self.user, self.corpus, [PermissionTypes.ALL]
            )

        self.pdf_bytes = SAMPLE_PDF_FILE_ONE_PATH.read_bytes()

    def _run_import(self, labels_data) -> dict:
        sidecar = _build_sidecar_json(
            annotations=[
                _make_annotation(1, "Exhibit", "Heading", page=0),
            ],
        )
        files = {
            "doc.pdf": self.pdf_bytes,
            "doc.json": json.dumps(sidecar).encode("utf-8"),
            "labels.json": json.dumps(labels_data).encode("utf-8"),
        }
        zip_buffer = self._create_test_zip(files)
        handle = self._create_temp_file_handle(zip_buffer)

        return import_zip_with_folder_structure.apply(
            kwargs={
                "temporary_file_handle_id": handle.id,
                "user_id": self.user.id,
                "job_id": "test-labels-validation",
                "corpus_id": self.corpus.id,
            }
        ).get()

    def test_text_labels_as_list_rejected(self):
        """Import fails gracefully when text_labels is a list."""
        result = self._run_import({"text_labels": [{"text": "Heading"}]})
        self.assertFalse(result["labels_loaded"])
        error_text = " ".join(result["errors"])
        self.assertIn("text_labels", error_text)

    def test_label_missing_text_field_rejected(self):
        """Import fails gracefully when a label entry lacks 'text'."""
        result = self._run_import(
            {"text_labels": {"Heading": {"label_type": "TOKEN_LABEL", "color": "#F00"}}}
        )
        self.assertFalse(result["labels_loaded"])
        error_text = " ".join(result["errors"])
        self.assertIn("missing required field 'text'", error_text)

    def test_color_as_integer_rejected(self):
        """Import fails gracefully when color is an integer."""
        label = _make_label_data("Heading")
        label["color"] = 0xFF0000
        result = self._run_import({"text_labels": {"Heading": label}})
        self.assertFalse(result["labels_loaded"])
        error_text = " ".join(result["errors"])
        self.assertIn("'color' must be a string", error_text)

    def test_top_level_not_dict_rejected(self):
        """Import fails gracefully when labels.json is not a dict."""
        result = self._run_import(["not", "a", "dict"])
        self.assertFalse(result["labels_loaded"])
        error_text = " ".join(result["errors"])
        self.assertIn("must be a JSON object", error_text)
