"""
Tests for the ``populate_content_modalities`` management command.

Covers the command exit paths plus its private ``_determine_modalities``
helper across the major code branches: no document, label-fallback, mixed
text/image PAWLs lookup, dry-run, force, error-during-load.
"""

import json
from io import StringIO
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.test import TestCase

from opencontractserver.annotations.management.commands.populate_content_modalities import (
    Command,
)
from opencontractserver.annotations.models import Annotation, AnnotationLabel
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document

User = get_user_model()

pytestmark = pytest.mark.django_db


def _v1_pawls_text_only() -> list:
    return [
        {
            "page": {"width": 612.0, "height": 792.0, "index": 0},
            "tokens": [
                {"x": 10, "y": 10, "width": 30, "height": 12, "text": "Hello"},
            ],
        }
    ]


def _v1_pawls_with_image() -> list:
    return [
        {
            "page": {"width": 612.0, "height": 792.0, "index": 0},
            "tokens": [
                {"x": 10, "y": 10, "width": 30, "height": 12, "text": "Hi"},
                {
                    "x": 100,
                    "y": 100,
                    "width": 200,
                    "height": 150,
                    "text": "",
                    "is_image": True,
                },
            ],
        }
    ]


class PopulateContentModalitiesTests(TestCase):
    """Covers the command's public surface end-to-end."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="populate_modalities_user", password="testpass123"
        )
        cls.corpus = Corpus.objects.create(
            title="Modalities Corpus",
            creator=cls.user,
        )
        cls.text_label = AnnotationLabel.objects.create(
            text="Heading",
            creator=cls.user,
        )
        cls.image_label = AnnotationLabel.objects.create(
            text="Figure 1",
            creator=cls.user,
        )

    def _create_document(self, pawls_data) -> Document:
        document = Document.objects.create(
            title="Modalities Doc",
            creator=self.user,
            pdf_file=ContentFile(b"fake pdf", name="m.pdf"),
            pawls_parse_file=ContentFile(
                json.dumps(pawls_data).encode(), name="m.pawls"
            ),
        )
        self.corpus.add_document(document=document, user=self.user)
        return document

    def _create_annotation(
        self, document, label, page_idx=0, token_idx=0, modalities=None
    ) -> Annotation:
        return Annotation.objects.create(
            document=document,
            corpus=self.corpus,
            annotation_label=label,
            creator=self.user,
            content_modalities=modalities or [],
            json={
                "0": {
                    "bounds": {"left": 0, "top": 0, "right": 10, "bottom": 10},
                    "tokensJsons": [{"pageIndex": page_idx, "tokenIndex": token_idx}],
                }
            },
        )

    # ---- _determine_modalities branch coverage --------------------

    def _create_document_without_pawls(self) -> Document:
        document = Document.objects.create(
            title="No Pawls Doc",
            creator=self.user,
            pdf_file=ContentFile(b"fake pdf", name="np.pdf"),
        )
        self.corpus.add_document(document=document, user=self.user)
        return document

    def test_determine_modalities_no_pawls_file_falls_back_to_label(self):
        # Document exists but has no pawls_parse_file → uses label as hint.
        # ``Figure 1`` matches the IMAGE keyword set so the helper returns
        # ``["IMAGE"]``.
        document = self._create_document_without_pawls()
        annotation = Annotation.objects.create(
            document=document,
            corpus=self.corpus,
            annotation_label=self.image_label,
            creator=self.user,
            content_modalities=[],
            json={},
        )
        cmd = Command()
        self.assertEqual(cmd._determine_modalities(annotation), ["IMAGE"])

    def test_determine_modalities_no_pawls_file_text_label(self):
        document = self._create_document_without_pawls()
        annotation = Annotation.objects.create(
            document=document,
            corpus=self.corpus,
            annotation_label=self.text_label,
            creator=self.user,
            content_modalities=[],
            json={},
        )
        cmd = Command()
        self.assertEqual(cmd._determine_modalities(annotation), ["TEXT"])

    def test_determine_modalities_pawls_load_error_falls_back_to_label(self):
        # Document has a pawls file, but loading raises — command must catch
        # the exception and use the label hint instead of crashing.
        document = self._create_document(_v1_pawls_with_image())
        annotation = self._create_annotation(document, self.image_label, token_idx=1)
        cmd = Command()
        with patch(
            "opencontractserver.annotations.management.commands."
            "populate_content_modalities.load_canonical_v2",
            side_effect=ValueError("boom"),
        ):
            self.assertEqual(cmd._determine_modalities(annotation), ["IMAGE"])

    def test_determine_modalities_pawls_load_error_text_label(self):
        document = self._create_document(_v1_pawls_text_only())
        annotation = self._create_annotation(document, self.text_label, token_idx=0)
        cmd = Command()
        with patch(
            "opencontractserver.annotations.management.commands."
            "populate_content_modalities.load_canonical_v2",
            side_effect=ValueError("boom"),
        ):
            self.assertEqual(cmd._determine_modalities(annotation), ["TEXT"])

    def test_determine_modalities_no_token_refs_uses_label(self):
        # Annotation pawls loads fine but JSON has no token refs — falls back
        # to label hints.
        document = self._create_document(_v1_pawls_with_image())
        annotation = Annotation.objects.create(
            document=document,
            corpus=self.corpus,
            annotation_label=self.image_label,
            creator=self.user,
            content_modalities=[],
            json={},
        )
        cmd = Command()
        self.assertEqual(cmd._determine_modalities(annotation), ["IMAGE"])

    def test_determine_modalities_text_token(self):
        document = self._create_document(_v1_pawls_text_only())
        annotation = self._create_annotation(document, self.text_label, token_idx=0)
        cmd = Command()
        self.assertEqual(cmd._determine_modalities(annotation), ["TEXT"])

    def test_determine_modalities_image_only(self):
        document = self._create_document(_v1_pawls_with_image())
        # Token index 1 is the image token in ``_v1_pawls_with_image``.
        annotation = self._create_annotation(document, self.image_label, token_idx=1)
        cmd = Command()
        self.assertEqual(cmd._determine_modalities(annotation), ["IMAGE"])

    def test_determine_modalities_mixed_image_and_text(self):
        document = self._create_document(_v1_pawls_with_image())
        annotation = Annotation.objects.create(
            document=document,
            corpus=self.corpus,
            annotation_label=self.image_label,
            creator=self.user,
            content_modalities=[],
            json={
                "0": {
                    "bounds": {"left": 0, "top": 0, "right": 10, "bottom": 10},
                    "tokensJsons": [
                        {"pageIndex": 0, "tokenIndex": 0},  # Hi (text)
                        {"pageIndex": 0, "tokenIndex": 1},  # image
                    ],
                }
            },
        )
        cmd = Command()
        self.assertEqual(
            sorted(cmd._determine_modalities(annotation)),
            sorted(["IMAGE", "TEXT"]),
        )

    def test_determine_modalities_skips_out_of_bounds(self):
        # Token references that would IndexError are silently skipped, so
        # nothing is detected and the helper returns the empty-default TEXT.
        document = self._create_document(_v1_pawls_text_only())
        annotation = Annotation.objects.create(
            document=document,
            corpus=self.corpus,
            annotation_label=self.text_label,
            creator=self.user,
            content_modalities=[],
            json={
                "0": {
                    "bounds": {"left": 0, "top": 0, "right": 10, "bottom": 10},
                    "tokensJsons": [
                        {"pageIndex": 5, "tokenIndex": 0},  # bad page
                        {"pageIndex": 0, "tokenIndex": 99},  # bad token
                    ],
                }
            },
        )
        cmd = Command()
        self.assertEqual(cmd._determine_modalities(annotation), ["TEXT"])

    # ---- Command handle() branch coverage -------------------------

    def test_handle_dry_run_does_not_persist(self):
        document = self._create_document(_v1_pawls_with_image())
        annotation = self._create_annotation(document, self.image_label, token_idx=1)
        out = StringIO()
        call_command("populate_content_modalities", "--dry-run", stdout=out)

        annotation.refresh_from_db()
        self.assertEqual(annotation.content_modalities, [])
        self.assertIn("DRY RUN", out.getvalue())

    def test_handle_persists_modalities_for_default_run(self):
        document = self._create_document(_v1_pawls_with_image())
        annotation = self._create_annotation(document, self.image_label, token_idx=1)
        out = StringIO()
        call_command("populate_content_modalities", stdout=out)

        annotation.refresh_from_db()
        self.assertEqual(annotation.content_modalities, ["IMAGE"])

    def test_handle_force_reprocesses_already_set_annotations(self):
        document = self._create_document(_v1_pawls_with_image())
        annotation = self._create_annotation(
            document,
            self.image_label,
            token_idx=1,
            modalities=["TEXT"],  # already set, would be skipped without --force
        )
        out = StringIO()
        call_command("populate_content_modalities", "--force", stdout=out)

        annotation.refresh_from_db()
        # --force re-runs detection and overwrites with the correct value.
        self.assertEqual(annotation.content_modalities, ["IMAGE"])

    def test_handle_records_errors_for_broken_annotation(self):
        # Patch ``_determine_modalities`` so it raises for one annotation.
        # The command should catch the error, increment ``error_count``, and
        # keep going — verifying the per-annotation try/except branch.
        document = self._create_document(_v1_pawls_with_image())
        self._create_annotation(document, self.image_label, token_idx=1)

        out = StringIO()
        with patch.object(
            Command, "_determine_modalities", side_effect=RuntimeError("nope")
        ):
            call_command("populate_content_modalities", stdout=out)

        self.assertIn("Errors: 1", out.getvalue())
