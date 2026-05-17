"""
Tests for fixes introduced during typing graduation of opencontractserver.tasks.*.

Covers:
- ``finalize_export``: streams the ZIP buffer to storage via
  ``django.core.files.File`` (no full-buffer re-copy via ``ContentFile``)
- ``on_demand_post_processors``: RuntimeError when export.file is missing
- ``package_funsd_exports``: int-keyed annotation_map lookup (regression test)
- ``package_corpus_export_v2``: errors field (was incorrectly ``error``)
"""

from __future__ import annotations

import io
import json
import os
import tempfile
import zipfile
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from opencontractserver.corpuses.models import Corpus
from opencontractserver.tasks.export_tasks import (
    finalize_export,
    on_demand_post_processors,
    package_funsd_exports,
)
from opencontractserver.tasks.export_tasks_v2 import package_corpus_export_v2
from opencontractserver.types.dicts import FunsdAnnotationType
from opencontractserver.users.models import UserExport

User = get_user_model()


def _make_tiny_zip(data: dict | None = None) -> io.BytesIO:
    """Build a minimal in-memory ZIP with a data.json member."""
    if data is None:
        data = {"annotated_docs": {}, "corpus": {}, "label_set": {}}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w") as zf:
        zf.writestr("data.json", json.dumps(data))
    buf.seek(0)
    return buf


class FinalizeExportTestCase(TestCase):
    """finalize_export must save the ZIP via DjangoFile and set metadata."""

    def setUp(self):
        self.user = User.objects.create_user(username="finalize_user", password="pw")
        self.corpus = Corpus.objects.create(title="FinalizeCorpus", creator=self.user)
        self.export = UserExport.objects.create(
            name="finalize-test",
            creator=self.user,
            backend_lock=True,
        )

    def test_finalize_export_saves_file_and_clears_lock(self):
        """finalize_export saves the zip, clears backend_lock, and sets finished."""
        buf = _make_tiny_zip()

        finalize_export(self.export.id, "corpus_export.zip", buf, self.corpus.title)

        self.export.refresh_from_db()
        self.assertFalse(self.export.backend_lock)
        self.assertIsNotNone(self.export.finished)
        # The file field must now point to a saved file.
        self.assertTrue(bool(self.export.file.name))

    def test_finalize_export_reads_from_seekable_buffer(self):
        """finalize_export should seek to 0 before reading the buffer."""
        buf = _make_tiny_zip()
        # Advance the buffer position to simulate the caller not rewinding.
        buf.read(5)

        # Should not raise even though the buffer position is non-zero.
        finalize_export(self.export.id, "corpus_export.zip", buf, self.corpus.title)

        self.export.refresh_from_db()
        self.assertTrue(bool(self.export.file.name))

    def test_finalize_export_accepts_spooled_temporary_file(self):
        """finalize_export must stream from a SpooledTemporaryFile, not just BytesIO.

        The V2 export path (issue #1649 OOM fix) now hands ``finalize_export``
        a ``SpooledTemporaryFile`` instead of an in-memory ``BytesIO`` so very
        large archives don't double-buffer the whole ZIP in heap. This test
        exercises the streaming-write branch by copying the tiny ZIP into a
        spool that has already rolled over to disk (max_size=1 byte). It
        guards against any future change that re-introduces a
        ``.getvalue()``- or ``.read()``-into-bytes pattern, which would
        regress the OOM fix back to its pre-PR-1676 shape.
        """
        from tempfile import SpooledTemporaryFile

        tiny = _make_tiny_zip()
        spool = SpooledTemporaryFile(max_size=1, suffix=".zip")
        spool.write(tiny.getvalue())
        # Sanity: max_size=1 forces a rollover on the first non-trivial write,
        # so we know we're exercising the disk-backed file path here.
        # ``_rolled`` is a private CPython attribute — there is no public API
        # for the on-disk-spill state today, so accept the typeshed gap.
        self.assertTrue(spool._rolled)  # type: ignore[attr-defined]
        spool.seek(0)
        try:
            finalize_export(
                self.export.id, "corpus_export.zip", spool, self.corpus.title
            )
        finally:
            spool.close()

        self.export.refresh_from_db()
        self.assertFalse(self.export.backend_lock)
        self.assertIsNotNone(self.export.finished)
        self.assertTrue(bool(self.export.file.name))


class OnDemandPostProcessorsTestCase(TestCase):
    """on_demand_post_processors: guard against missing export file."""

    def setUp(self):
        self.user = User.objects.create_user(username="postproc_user", password="pw")
        self.corpus = Corpus.objects.create(title="PPCorpus", creator=self.user)
        self.export = UserExport.objects.create(
            name="postproc-test",
            creator=self.user,
            post_processors=["some.processor"],
        )

    def test_raises_when_export_file_is_missing(self):
        """
        When post_processors is non-empty but export.file.name is falsy,
        on_demand_post_processors must raise RuntimeError (not AttributeError
        or another exception from deeper in the stack).
        """
        # Ensure there is no file saved (the factory default).
        self.assertFalse(bool(self.export.file.name))

        with self.assertRaises(
            RuntimeError, msg="Expected RuntimeError for missing file"
        ):
            on_demand_post_processors(self.export.id, self.corpus.id)

    def test_no_post_processors_is_a_noop(self):
        """When post_processors is empty the task completes silently."""
        self.export.post_processors = []
        self.export.save()

        # Should not raise.
        on_demand_post_processors(self.export.id, self.corpus.id)


class PackageFunsdExportsIntKeyTestCase(TestCase):
    """
    Regression tests for the FUNSD key-type fix.

    Prior to the fix, doc_tasks.py used int keys in annotation_map but
    export_tasks.py looked up via str(index), silently omitting all annotations.
    After the fix both sides use int keys consistently.
    """

    def setUp(self):
        self.user = User.objects.create_user(username="funsd_user", password="pw")
        self.corpus = Corpus.objects.create(title="FunsdCorpus", creator=self.user)
        self.export = UserExport.objects.create(
            name="funsd-test",
            creator=self.user,
        )

    def _run_package_funsd(
        self,
        funsd_annotations: dict,
        page_image_paths: list,
        doc_id: int = 1,
    ) -> dict:
        """
        Run package_funsd_exports with a local-storage image file and
        collect the resulting zip content.
        """
        captured: dict = {}

        def _capture(export_id, filename, output_bytes, corpus_title):
            output_bytes.seek(0)
            captured["bytes"] = output_bytes.getvalue()

        with patch(
            "opencontractserver.tasks.export_tasks.finalize_export",
            side_effect=_capture,
        ):
            package_funsd_exports(
                funsd_data=((doc_id, funsd_annotations, page_image_paths),),
                export_id=self.export.id,
                corpus_pk=self.corpus.id,
            )

        return captured

    def test_annotation_on_page_zero_appears_in_zip_with_int_key(self):
        """
        When annotation_map has key 0 (int), the annotation must appear in
        annotations/doc_<id>-pg_0.json; it must NOT be silently absent.
        """
        annotation: FunsdAnnotationType = {
            "box": (0.0, 0.0, 10.0, 10.0),
            "text": "hello",
            "label": "TestLabel",
            "words": [],
            "linking": [],
            "id": "ann-0",
            "parent_id": None,
        }
        funsd_annotations = {0: [annotation]}

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp.write(b"\x89PNG\r\n\x1a\n")  # PNG magic bytes
            tmp_path = tmp.name

        try:
            page_image_paths = [(1, tmp_path, "png")]
            captured = self._run_package_funsd(
                funsd_annotations, page_image_paths, doc_id=1
            )
        finally:
            os.unlink(tmp_path)

        self.assertIn("bytes", captured, "finalize_export was not called")

        zf = zipfile.ZipFile(io.BytesIO(captured["bytes"]))
        names = zf.namelist()

        annot_file = "annotations/doc_1-pg_0.json"
        self.assertIn(annot_file, names)

        page_data = json.loads(zf.read(annot_file).decode("utf-8"))
        self.assertIn("form", page_data)
        # The annotation must appear – this is the regression guard.
        self.assertEqual(len(page_data["form"]), 1)
        self.assertEqual(page_data["form"][0]["text"], "hello")

    def test_pages_without_annotations_write_empty_form(self):
        """
        Pages with no annotation entry produce {"form": []} in the zip.
        """
        funsd_annotations: dict[int, list] = {}  # no annotations at all

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp.write(b"\x89PNG\r\n\x1a\n")
            tmp_path = tmp.name

        try:
            page_image_paths = [(1, tmp_path, "png")]
            captured = self._run_package_funsd(
                funsd_annotations, page_image_paths, doc_id=1
            )
        finally:
            os.unlink(tmp_path)

        zf = zipfile.ZipFile(io.BytesIO(captured["bytes"]))
        annot_file = "annotations/doc_1-pg_0.json"
        self.assertIn(annot_file, zf.namelist())

        page_data = json.loads(zf.read(annot_file).decode("utf-8"))
        self.assertEqual(page_data, {"form": []})

    def test_aws_storage_reads_page_via_s3_get_object(self):
        """
        AWS storage branch: ``s3.get_object`` returns the page bytes which are
        then written into the zip. Patches ``boto3.client`` so no real AWS
        call is made.
        """
        annotation: FunsdAnnotationType = {
            "box": (0.0, 0.0, 5.0, 5.0),
            "text": "aws-page",
            "label": "L",
            "words": [],
            "linking": [],
            "id": "ann-aws",
            "parent_id": None,
        }
        funsd_annotations = {0: [annotation]}
        page_image_paths = [(7, "s3/key/path.png", "png")]

        # Build a mock s3 client whose get_object returns a Body with .read().
        body = io.BytesIO(b"\x89PNG\r\n\x1a\n")
        fake_s3 = MagicMock()
        fake_s3.get_object.return_value = {"Body": body}

        captured: dict = {}

        def _capture(export_id, filename, output_bytes, corpus_title):
            output_bytes.seek(0)
            captured["bytes"] = output_bytes.getvalue()

        with self.settings(
            STORAGE_BACKEND="AWS",
            AWS_STORAGE_BUCKET_NAME="bucket-x",
        ), patch("boto3.client", return_value=fake_s3), patch(
            "opencontractserver.tasks.export_tasks.finalize_export",
            side_effect=_capture,
        ):
            package_funsd_exports(
                funsd_data=((7, funsd_annotations, page_image_paths),),
                export_id=self.export.id,
                corpus_pk=self.corpus.id,
            )

        fake_s3.get_object.assert_called_once_with(
            Bucket="bucket-x", Key="s3/key/path.png"
        )
        self.assertIn("bytes", captured)
        zf = zipfile.ZipFile(io.BytesIO(captured["bytes"]))
        self.assertIn("images/doc_7-pg_0.png", zf.namelist())

    def test_gcp_storage_reads_page_via_blob_download(self):
        """
        GCP storage branch: ``gcs_bucket.blob().download_as_bytes()`` returns
        the page bytes which are then written into the zip. The package_funsd
        helper resolves ``gcs_bucket`` lazily from the AWS/GCP gating block at
        the top of the function, so we patch the storage-client construction.
        """
        annotation: FunsdAnnotationType = {
            "box": (0.0, 0.0, 5.0, 5.0),
            "text": "gcp-page",
            "label": "L",
            "words": [],
            "linking": [],
            "id": "ann-gcp",
            "parent_id": None,
        }
        funsd_annotations = {0: [annotation]}
        page_image_paths = [(9, "gcs/key/path.png", "png")]

        fake_blob = MagicMock()
        fake_blob.download_as_bytes.return_value = b"\x89PNG\r\n\x1a\n"
        fake_bucket = MagicMock()
        fake_bucket.blob.return_value = fake_blob
        fake_storage_client = MagicMock()
        fake_storage_client.bucket.return_value = fake_bucket

        captured: dict = {}

        def _capture(export_id, filename, output_bytes, corpus_title):
            output_bytes.seek(0)
            captured["bytes"] = output_bytes.getvalue()

        with self.settings(
            STORAGE_BACKEND="GCP",
            GS_BUCKET_NAME="gcs-bucket",
            GS_PROJECT_ID="gcp-test-project",
        ), patch(
            "google.cloud.storage.Client",
            return_value=fake_storage_client,
            create=True,
        ), patch(
            "opencontractserver.tasks.export_tasks.finalize_export",
            side_effect=_capture,
        ):
            package_funsd_exports(
                funsd_data=((9, funsd_annotations, page_image_paths),),
                export_id=self.export.id,
                corpus_pk=self.corpus.id,
            )

        fake_blob.download_as_bytes.assert_called_once()
        self.assertIn("bytes", captured)
        zf = zipfile.ZipFile(io.BytesIO(captured["bytes"]))
        self.assertIn("images/doc_9-pg_0.png", zf.namelist())

    def test_multiple_pages_multiple_annotations(self):
        """Annotations on multiple pages are stored in separate files."""
        annotation_p0: FunsdAnnotationType = {
            "box": (0.0, 0.0, 5.0, 5.0),
            "text": "page0",
            "label": "LabelA",
            "words": [],
            "linking": [],
            "id": "ann-p0",
            "parent_id": None,
        }
        annotation_p1: FunsdAnnotationType = {
            "box": (1.0, 1.0, 6.0, 6.0),
            "text": "page1",
            "label": "LabelB",
            "words": [],
            "linking": [],
            "id": "ann-p1",
            "parent_id": None,
        }
        funsd_annotations = {0: [annotation_p0], 1: [annotation_p1]}

        tmp_files = []
        page_image_paths = []
        try:
            for _ in range(2):
                tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
                tmp.write(b"\x89PNG\r\n\x1a\n")
                tmp.close()
                tmp_files.append(tmp.name)
                page_image_paths.append((1, tmp.name, "png"))

            captured = self._run_package_funsd(
                funsd_annotations, page_image_paths, doc_id=1
            )
        finally:
            for f in tmp_files:
                os.unlink(f)

        zf = zipfile.ZipFile(io.BytesIO(captured["bytes"]))
        names = zf.namelist()

        self.assertIn("annotations/doc_1-pg_0.json", names)
        self.assertIn("annotations/doc_1-pg_1.json", names)

        p0 = json.loads(zf.read("annotations/doc_1-pg_0.json").decode())
        p1 = json.loads(zf.read("annotations/doc_1-pg_1.json").decode())

        self.assertEqual(p0["form"][0]["text"], "page0")
        self.assertEqual(p1["form"][0]["text"], "page1")


class PackageCorpusExportV2ErrorsFieldTestCase(TestCase):
    """
    Regression test: package_corpus_export_v2 sets export.errors (not the
    non-existent export.error) when an exception occurs.

    Prior to the fix, the except block referenced ``export.error = True``
    which would have raised ``AttributeError`` instead of recording the
    failure, masking the original exception.
    """

    def setUp(self):
        self.user = User.objects.create_user(username="v2_err_user", password="pw")
        self.export = UserExport.objects.create(
            name="v2-err-test",
            creator=self.user,
            backend_lock=True,
        )

    def test_runtime_error_when_corpus_packager_returns_none(self):
        """
        PR #1482 added a hard ``RuntimeError`` when
        ``package_corpus_for_export`` returns ``None`` for V2 exports.  Verify
        the failure flows through the except-handler that records the error
        on the export and re-raises so Celery sees the failure.
        """
        # Create a corpus that the task can fetch.
        corpus = Corpus.objects.create(title="Empty V2 Corpus", creator=self.user)

        # Stub out the V2 corpus packager so it returns None mid-way through
        # the task. Patch path matches the import at the top of
        # ``export_tasks_v2``.
        with patch(
            "opencontractserver.tasks.export_tasks_v2.package_corpus_for_export",
            return_value=None,
        ), self.assertRaises(RuntimeError):
            package_corpus_export_v2(
                export_id=self.export.id,
                corpus_pk=corpus.id,
            )

        self.export.refresh_from_db()
        self.assertFalse(self.export.backend_lock)
        self.assertTrue(bool(self.export.errors))

    def test_errors_field_populated_on_failure(self):
        """
        When the export pipeline raises an unexpected error, the task records
        the failure on the export (``errors`` set to a non-empty string,
        ``backend_lock`` cleared) and *re-raises* so Celery marks the task
        FAILURE. The PR-1482 typing fix was about the recording side
        (``export.errors``, not the non-existent ``export.error``); the
        propagation is unchanged.
        """
        # Use a corpus_pk that doesn't exist to trigger an exception inside
        # package_corpus_export_v2 before it saves anything.
        nonexistent_corpus_pk = 999_999_999

        with self.assertRaises(Corpus.DoesNotExist):
            package_corpus_export_v2(
                export_id=self.export.id,
                corpus_pk=nonexistent_corpus_pk,
            )

        self.export.refresh_from_db()
        self.assertFalse(
            self.export.backend_lock,
            "backend_lock must be cleared even on failure",
        )
        self.assertTrue(
            bool(self.export.errors),
            "export.errors must be set to the error string on failure",
        )
