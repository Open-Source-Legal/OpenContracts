"""
End-to-end tests for the ``populate_content_modalities`` management command.

The command iterates ``Annotation`` rows and assigns ``content_modalities``
based on:

1. PAWLs token data via ``load_canonical_v2`` + ``iter_pages``
2. A label-text keyword fallback when no document/PAWLs data is available,
   when the annotation references no tokens, or when PAWLs loading fails.

These tests exercise both code paths plus the ``--dry-run`` and ``--force``
flags so the command is covered end-to-end through ``call_command``.
"""

import json
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.test import TestCase

from opencontractserver.annotations.models import Annotation, AnnotationLabel
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document

User = get_user_model()


# ── Fixtures ─────────────────────────────────────────────────────


def _v1_pawls_text_only() -> list:
    """v1 page list with a single text token."""
    return [
        {
            "page": {"width": 612, "height": 792, "index": 0},
            "tokens": [
                {"x": 1, "y": 1, "width": 10, "height": 10, "text": "Hello"},
            ],
        }
    ]


def _v1_pawls_image_only() -> list:
    """v1 page list with a single image token."""
    return [
        {
            "page": {"width": 612, "height": 792, "index": 0},
            "tokens": [
                {
                    "x": 1,
                    "y": 1,
                    "width": 10,
                    "height": 10,
                    "text": "",
                    "is_image": True,
                    "image_path": "p",
                    "format": "jpeg",
                    "content_hash": "h",
                    "original_width": 100,
                    "original_height": 100,
                    "image_type": "embedded",
                },
            ],
        }
    ]


def _v1_pawls_mixed() -> list:
    """v1 page list with a text token followed by an image token."""
    return [
        {
            "page": {"width": 612, "height": 792, "index": 0},
            "tokens": [
                {"x": 1, "y": 1, "width": 10, "height": 10, "text": "Hello"},
                {
                    "x": 1,
                    "y": 1,
                    "width": 10,
                    "height": 10,
                    "text": "",
                    "is_image": True,
                    "image_path": "p",
                    "format": "jpeg",
                    "content_hash": "h",
                    "original_width": 100,
                    "original_height": 100,
                    "image_type": "embedded",
                },
            ],
        }
    ]


# v2 compact annotation.json fragments — what the codebase produces today.
def _v2_anno_json_token_zero() -> dict:
    """Annotation references token index 0 on page 0."""
    return {"v": 2, "p": {"0": {"b": [0, 0, 100, 100], "t": "0"}}}


def _v2_anno_json_tokens_zero_one() -> dict:
    """Annotation references tokens 0..1 on page 0."""
    return {"v": 2, "p": {"0": {"b": [0, 0, 100, 100], "t": "0-1"}}}


# ── Tests ────────────────────────────────────────────────────────


class PopulateContentModalitiesCommandTests(TestCase):
    """End-to-end coverage of the ``populate_content_modalities`` command."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.user = User.objects.create_user(
            username="populate_modalities_user", password="testpass123"
        )
        cls.corpus = Corpus.objects.create(title="Test Corpus", creator=cls.user)
        cls.text_label = AnnotationLabel.objects.create(
            text="definition", creator=cls.user
        )
        cls.image_label = AnnotationLabel.objects.create(
            text="figure", creator=cls.user
        )
        cls.chart_label = AnnotationLabel.objects.create(text="chart", creator=cls.user)

    # ── Helpers ──────────────────────────────────────────────────

    def _make_document(self, pawls_data) -> Document:
        """Create a document with a ``pawls_parse_file`` containing *pawls_data*.

        ``pawls_data`` may be a v1 list, a v2 dict, or raw bytes (for the
        corrupt-PAWLs test).
        """
        if isinstance(pawls_data, (bytes, bytearray)):
            payload = bytes(pawls_data)
        else:
            payload = json.dumps(pawls_data).encode()
        document = Document.objects.create(
            title="Test Doc",
            creator=self.user,
            pdf_file=ContentFile(b"fake pdf", name="test.pdf"),
            pawls_parse_file=ContentFile(payload, name="test.pawls"),
        )
        self.corpus.add_document(document=document, user=self.user)
        return document

    def _make_document_without_pawls(self) -> Document:
        """Create a document that has no ``pawls_parse_file`` set.

        ``Annotation`` requires either a document or a structural set, so the
        ``not annotation.document.pawls_parse_file`` branch of the command's
        ``_determine_modalities`` fallback is exercised by attaching a
        document that simply has no PAWLs file rather than a NULL document.
        """
        document = Document.objects.create(
            title="Test Doc No PAWLs",
            creator=self.user,
            pdf_file=ContentFile(b"fake pdf", name="test.pdf"),
        )
        self.corpus.add_document(document=document, user=self.user)
        return document

    def _run_command(self, *args: str) -> str:
        """Invoke the command with stdout capture and return the captured text."""
        out = StringIO()
        err = StringIO()
        call_command("populate_content_modalities", *args, stdout=out, stderr=err)
        return out.getvalue()

    # ── --dry-run preserves rows ─────────────────────────────────

    def test_dry_run_does_not_modify_rows(self) -> None:
        """``--dry-run`` should report changes but never persist them."""
        document = self._make_document(_v1_pawls_text_only())
        annotation = Annotation.objects.create(
            document=document,
            corpus=self.corpus,
            annotation_label=self.text_label,
            creator=self.user,
            json=_v2_anno_json_token_zero(),
            content_modalities=[],
        )

        output = self._run_command("--dry-run")

        annotation.refresh_from_db()
        self.assertEqual(annotation.content_modalities, [])
        self.assertIn("DRY RUN", output)
        self.assertIn("Would update", output)

    # ── --force reprocesses already-set rows ─────────────────────

    def test_force_reprocesses_pre_set_annotations(self) -> None:
        """``--force`` should recompute even when ``content_modalities`` is set."""
        document = self._make_document(_v1_pawls_image_only())
        annotation = Annotation.objects.create(
            document=document,
            corpus=self.corpus,
            annotation_label=self.image_label,
            creator=self.user,
            json=_v2_anno_json_token_zero(),
            content_modalities=["TEXT"],  # incorrect placeholder value
        )

        self._run_command("--force")

        annotation.refresh_from_db()
        # The pawls token is an image, so the recomputed value must include IMAGE.
        self.assertIn("IMAGE", annotation.content_modalities)
        self.assertNotIn("TEXT", annotation.content_modalities)

    # ── Default mode skips already-populated rows ────────────────

    def test_default_mode_skips_already_populated(self) -> None:
        """Without ``--force``, only rows with empty modalities are processed."""
        document = self._make_document(_v1_pawls_image_only())
        # An already-populated annotation that should be left alone.
        preset = Annotation.objects.create(
            document=document,
            corpus=self.corpus,
            annotation_label=self.image_label,
            creator=self.user,
            json=_v2_anno_json_token_zero(),
            content_modalities=["TEXT"],  # deliberately incorrect
        )
        # An empty annotation that should be updated.
        empty = Annotation.objects.create(
            document=document,
            corpus=self.corpus,
            annotation_label=self.image_label,
            creator=self.user,
            json=_v2_anno_json_token_zero(),
            content_modalities=[],
        )

        self._run_command()

        preset.refresh_from_db()
        empty.refresh_from_db()
        # Pre-set value is left untouched, even though it is wrong.
        self.assertEqual(preset.content_modalities, ["TEXT"])
        # Empty annotation gets recomputed against the image token.
        self.assertEqual(empty.content_modalities, ["IMAGE"])

    # ── PAWLs path: image-only ───────────────────────────────────

    def test_pawls_image_only_annotation(self) -> None:
        document = self._make_document(_v1_pawls_image_only())
        annotation = Annotation.objects.create(
            document=document,
            corpus=self.corpus,
            annotation_label=self.image_label,
            creator=self.user,
            json=_v2_anno_json_token_zero(),
            content_modalities=[],
        )

        self._run_command()

        annotation.refresh_from_db()
        self.assertEqual(annotation.content_modalities, ["IMAGE"])

    # ── PAWLs path: text-only ────────────────────────────────────

    def test_pawls_text_only_annotation(self) -> None:
        document = self._make_document(_v1_pawls_text_only())
        annotation = Annotation.objects.create(
            document=document,
            corpus=self.corpus,
            annotation_label=self.text_label,
            creator=self.user,
            json=_v2_anno_json_token_zero(),
            content_modalities=[],
        )

        self._run_command()

        annotation.refresh_from_db()
        self.assertEqual(annotation.content_modalities, ["TEXT"])

    # ── PAWLs path: mixed ────────────────────────────────────────

    def test_pawls_mixed_annotation(self) -> None:
        document = self._make_document(_v1_pawls_mixed())
        annotation = Annotation.objects.create(
            document=document,
            corpus=self.corpus,
            annotation_label=self.text_label,
            creator=self.user,
            json=_v2_anno_json_tokens_zero_one(),  # references both tokens
            content_modalities=[],
        )

        self._run_command()

        annotation.refresh_from_db()
        self.assertEqual(annotation.content_modalities, ["IMAGE", "TEXT"])

    # ── No-document fallback (label says image) ──────────────────

    def test_no_document_fallback_label_hint_image(self) -> None:
        """Annotation whose document has no PAWLs file falls back to label hint."""
        document = self._make_document_without_pawls()
        annotation = Annotation.objects.create(
            document=document,
            corpus=self.corpus,
            annotation_label=self.image_label,  # "figure"
            creator=self.user,
            json={},
            content_modalities=[],
        )

        self._run_command()

        annotation.refresh_from_db()
        self.assertEqual(annotation.content_modalities, ["IMAGE"])

    # ── No-document fallback (label says text) ───────────────────

    def test_no_document_fallback_label_hint_text(self) -> None:
        """Neutral label text falls back to the TEXT default."""
        document = self._make_document_without_pawls()
        annotation = Annotation.objects.create(
            document=document,
            corpus=self.corpus,
            annotation_label=self.text_label,  # "definition"
            creator=self.user,
            json={},
            content_modalities=[],
        )

        self._run_command()

        annotation.refresh_from_db()
        self.assertEqual(annotation.content_modalities, ["TEXT"])

    # ── PAWLs load failure falls back to label hint ──────────────

    def test_pawls_load_failure_falls_back_to_label_hint(self) -> None:
        """Corrupt PAWLs file should not crash the command — label hint wins."""
        document = self._make_document(b"not json")
        annotation = Annotation.objects.create(
            document=document,
            corpus=self.corpus,
            annotation_label=self.image_label,  # "figure"
            creator=self.user,
            json=_v2_anno_json_token_zero(),
            content_modalities=[],
        )

        self._run_command()

        annotation.refresh_from_db()
        self.assertEqual(annotation.content_modalities, ["IMAGE"])

    # ── Empty token refs fall back to label hint ─────────────────

    def test_empty_token_refs_fall_back_to_label_hint(self) -> None:
        """Valid PAWLs but no token references should fall back to label text."""
        document = self._make_document(_v1_pawls_text_only())
        annotation = Annotation.objects.create(
            document=document,
            corpus=self.corpus,
            annotation_label=self.chart_label,  # "chart"
            creator=self.user,
            json={},  # no token references
            content_modalities=[],
        )

        self._run_command()

        annotation.refresh_from_db()
        self.assertEqual(annotation.content_modalities, ["IMAGE"])

    # ── Per-annotation errors increment error_count ──────────────

    def test_processing_error_increments_error_count(self) -> None:
        """If ``_determine_modalities`` raises, the command logs and continues."""
        document = self._make_document(_v1_pawls_text_only())
        Annotation.objects.create(
            document=document,
            corpus=self.corpus,
            annotation_label=self.text_label,
            creator=self.user,
            json=_v2_anno_json_token_zero(),
            content_modalities=[],
        )

        target = (
            "opencontractserver.annotations.management.commands."
            "populate_content_modalities.Command._determine_modalities"
        )
        with patch(target, side_effect=RuntimeError("boom")):
            output = self._run_command()

        # The error path writes "Errors: N" with N >= 1 in the final summary.
        self.assertIn("Errors: 1", output)
        self.assertIn("Error processing annotation", output)
