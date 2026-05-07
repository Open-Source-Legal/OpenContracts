"""Regression tests for ``package_annotated_docs`` skipping failed placeholders."""

from __future__ import annotations

import base64
import io
import json
import zipfile
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from opencontractserver.annotations.models import LabelSet
from opencontractserver.corpuses.models import Corpus
from opencontractserver.tasks.export_tasks import package_annotated_docs
from opencontractserver.users.models import UserExport

User = get_user_model()


def _make_label(pk: str, text: str) -> dict:
    return {
        "id": pk,
        "color": "#FF0000",
        "description": "",
        "icon": "tag",
        "text": text,
        "label_type": "TOKEN_LABEL",
    }


def _make_doc_export(title: str) -> dict:
    return {
        "doc_labels": [],
        "labelled_text": [],
        "title": title,
        "description": "",
        "content": "",
        "pawls_file_content": [],
        "page_count": 1,
        "file_type": "application/pdf",
    }


class PackageAnnotatedDocsSkipTestCase(TestCase):
    """Verifies package_annotated_docs skips failed burn_doc_annotations tuples."""

    def setUp(self) -> None:
        self.user = User.objects.create_user(username="bob", password="12345678")
        # ``package_annotated_docs`` now raises if either
        # ``package_corpus_for_export`` or ``package_label_set_for_export``
        # returns ``None`` (PR #1482 typing graduation made the None case a
        # hard error instead of silently writing a None into
        # ``OpenContractsExportDataJsonPythonType``). LabelSet is required
        # for ``package_label_set_for_export`` to succeed, so we attach one
        # in the test fixture.
        self.label_set = LabelSet.objects.create(
            title="Test LabelSet",
            description="For package_annotated_docs tests",
            creator=self.user,
        )
        self.corpus = Corpus.objects.create(
            title="Test Corpus",
            description="For package_annotated_docs tests",
            creator=self.user,
            label_set=self.label_set,
        )
        self.export = UserExport.objects.create(
            name="test-export",
            creator=self.user,
        )

        # A tiny payload that survives base64 + zip round-trip.
        self.fake_pdf_bytes = b"%PDF-1.4\n% fake body\n"
        self.fake_pdf_b64 = base64.b64encode(self.fake_pdf_bytes).decode("utf-8")

        self.text_labels = {"1": _make_label("1", "Important")}
        self.doc_labels = {"2": _make_label("2", "Contract")}

    def _collect_finalize(self):
        """Return a side_effect that captures finalize_export's output_bytes."""
        captured: dict = {}

        def _capture(export_id, filename, output_bytes, corpus_title):
            # finalize_export does output_bytes.seek(0) before saving; mirror
            # that so the captured buffer is ready to read in-test.
            output_bytes.seek(0)
            captured["bytes"] = output_bytes.getvalue()
            captured["filename"] = filename

        return captured, _capture

    def test_skips_failed_placeholder_and_packages_successful_docs(self) -> None:
        """Mixed input: one good doc + one failed placeholder -> only good doc lands in zip."""
        good_doc = (
            "good.pdf",
            self.fake_pdf_b64,
            _make_doc_export("Good Doc"),
            self.text_labels,
            self.doc_labels,
        )
        # This is exactly what build_document_export returns on failure.
        failed_doc = ("", "", None, {}, {})

        captured, capture_fn = self._collect_finalize()
        with patch(
            "opencontractserver.tasks.export_tasks.finalize_export",
            side_effect=capture_fn,
        ), self.assertLogs(
            "opencontractserver.tasks.export_tasks", level="WARNING"
        ) as log_cm:
            package_annotated_docs(
                burned_docs=(good_doc, failed_doc),
                export_id=self.export.id,
                corpus_pk=self.corpus.id,
            )

        self.assertTrue(
            any("Skipping failed burned doc" in line for line in log_cm.output),
            f"Expected skip-warning log, got: {log_cm.output}",
        )
        self.assertIn("bytes", captured, "finalize_export was not called")
        zf = zipfile.ZipFile(io.BytesIO(captured["bytes"]))
        names = set(zf.namelist())

        # The failed placeholder's empty-string filename must NOT be in the zip.
        self.assertNotIn("", names)
        self.assertIn("good.pdf", names)
        self.assertIn("data.json", names)

        data = json.loads(zf.read("data.json").decode("utf-8"))
        self.assertIn("good.pdf", data["annotated_docs"])
        self.assertNotIn("", data["annotated_docs"])
        # No None values should leak into annotated_docs.
        self.assertTrue(
            all(v is not None for v in data["annotated_docs"].values()),
            "annotated_docs must not contain None values for failed exports",
        )
        # Labels from the successful doc still propagate.
        self.assertEqual(data["text_labels"], self.text_labels)
        self.assertEqual(data["doc_labels"], self.doc_labels)

    def test_all_failed_produces_empty_annotated_docs_without_crashing(self) -> None:
        """Every doc failed -> no crash, empty annotated_docs, no bogus keys."""
        failed_doc_a = ("", "", None, {}, {})
        failed_doc_b = ("", "", None, {}, {})

        captured, capture_fn = self._collect_finalize()
        with patch(
            "opencontractserver.tasks.export_tasks.finalize_export",
            side_effect=capture_fn,
        ):
            package_annotated_docs(
                burned_docs=(failed_doc_a, failed_doc_b),
                export_id=self.export.id,
                corpus_pk=self.corpus.id,
            )

        self.assertIn("bytes", captured, "finalize_export was not called")
        zf = zipfile.ZipFile(io.BytesIO(captured["bytes"]))
        # Only data.json, no empty-filename entry.
        self.assertEqual(set(zf.namelist()), {"data.json"})

        data = json.loads(zf.read("data.json").decode("utf-8"))
        self.assertEqual(data["annotated_docs"], {})

    def test_raises_when_corpus_export_packager_returns_none(self) -> None:
        """
        PR #1482 added an explicit ``RuntimeError`` when
        ``package_corpus_for_export`` returns ``None`` (previously the result
        was silently written into ``OpenContractsExportDataJsonPythonType``).
        """
        good_doc = (
            "good.pdf",
            self.fake_pdf_b64,
            _make_doc_export("Good"),
            self.text_labels,
            self.doc_labels,
        )

        with patch(
            "opencontractserver.tasks.export_tasks.package_corpus_for_export",
            return_value=None,
        ), self.assertRaises(RuntimeError) as cm:
            package_annotated_docs(
                burned_docs=(good_doc,),
                export_id=self.export.id,
                corpus_pk=self.corpus.id,
            )
        self.assertIn("corpus", str(cm.exception).lower())

    def test_raises_when_label_set_packager_returns_none(self) -> None:
        """
        PR #1482 added an explicit ``RuntimeError`` when
        ``package_label_set_for_export`` returns ``None``.
        """
        good_doc = (
            "good.pdf",
            self.fake_pdf_b64,
            _make_doc_export("Good"),
            self.text_labels,
            self.doc_labels,
        )

        with patch(
            "opencontractserver.tasks.export_tasks.package_label_set_for_export",
            return_value=None,
        ), self.assertRaises(RuntimeError) as cm:
            package_annotated_docs(
                burned_docs=(good_doc,),
                export_id=self.export.id,
                corpus_pk=self.corpus.id,
            )
        self.assertIn("label set", str(cm.exception).lower())
