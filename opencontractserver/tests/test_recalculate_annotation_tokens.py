"""
Tests for ``recalculate_annotation_tokens_from_bboxes``.

Verifies that the recalculation pass correctly rebuilds ``tokensJsons``
from each annotation's bounding box against a document's freshly-parsed
PAWLs, and that it gracefully no-ops when there is nothing to do.
"""

from __future__ import annotations

import json

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TestCase

from opencontractserver.annotations.compact_json import iter_page_annotations
from opencontractserver.annotations.models import (
    TOKEN_LABEL,
    Annotation,
    AnnotationLabel,
)
from opencontractserver.documents.models import Document
from opencontractserver.tasks.import_tasks import (
    recalculate_annotation_tokens_from_bboxes,
)

User = get_user_model()


def _pawls_with_two_tokens_per_page() -> list[dict]:
    return [
        {
            "page": {"width": 612, "height": 792, "index": 0},
            "tokens": [
                {"x": 100, "y": 100, "width": 50, "height": 20, "text": "Hello"},
                {"x": 160, "y": 100, "width": 60, "height": 20, "text": "World"},
                {"x": 400, "y": 400, "width": 30, "height": 20, "text": "Far"},
            ],
        },
        {
            "page": {"width": 612, "height": 792, "index": 1},
            "tokens": [
                {"x": 50, "y": 50, "width": 40, "height": 15, "text": "Page2"},
            ],
        },
    ]


class TestRecalculateAnnotationTokensFromBboxes(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(
            username="recalc_user", password="testpass"
        )
        self.label = AnnotationLabel.objects.create(
            text="Heading",
            label_type=TOKEN_LABEL,
            creator=self.user,
            color="#FF0000",
        )

    def _make_doc(
        self,
        pawls: list[dict] | None = None,
    ) -> Document:
        doc = Document.objects.create(
            title="Recalc Doc",
            creator=self.user,
            file_type="application/pdf",
            page_count=2,
        )
        if pawls is not None:
            doc.pawls_parse_file.save(
                "pawls.json", ContentFile(json.dumps(pawls).encode("utf-8"))
            )
            doc.save()
        return doc

    def _make_annotation(
        self,
        doc: Document,
        bounds: dict[str, float],
        page_idx: int = 0,
        bogus_tokens: list[int] | None = None,
    ) -> Annotation:
        # Provide deliberately wrong tokensJsons so we can verify they get
        # replaced.  The bbox is what should drive the recalculation.
        tokens = bogus_tokens if bogus_tokens is not None else [99, 100]
        annot = Annotation.objects.create(
            raw_text="some text",
            page=page_idx,
            json={
                str(page_idx): {
                    "bounds": bounds,
                    "tokensJsons": [
                        {"pageIndex": page_idx, "tokenIndex": t} for t in tokens
                    ],
                    "rawText": "some text",
                }
            },
            annotation_label=self.label,
            document=doc,
            creator=self.user,
            annotation_type=TOKEN_LABEL,
        )
        return annot

    def _token_indices(self, annotation: Annotation, page_idx: int = 0) -> list[int]:
        annotation.refresh_from_db()
        for page in iter_page_annotations(
            annotation.json, raw_text=annotation.raw_text or ""
        ):
            if page.page_index == page_idx:
                return sorted(page.token_indices)
        return []

    def test_replaces_token_refs_with_bbox_intersection(self):
        doc = self._make_doc(pawls=_pawls_with_two_tokens_per_page())
        # Bounds covering the first two tokens on page 0.
        annot = self._make_annotation(
            doc, {"top": 95, "left": 90, "right": 230, "bottom": 130}
        )

        result = recalculate_annotation_tokens_from_bboxes.apply(
            kwargs={"document_id": doc.pk}
        ).get()

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["updated"], 1)
        self.assertEqual(self._token_indices(annot), [0, 1])

    def test_empty_bbox_yields_empty_tokens_without_error(self):
        doc = self._make_doc(pawls=_pawls_with_two_tokens_per_page())
        # Bounds far away from any token — should produce empty tokensJsons
        # rather than the bogus indices we seeded.
        annot = self._make_annotation(
            doc, {"top": 5, "left": 5, "right": 10, "bottom": 10}
        )

        result = recalculate_annotation_tokens_from_bboxes.apply(
            kwargs={"document_id": doc.pk}
        ).get()

        self.assertEqual(result["status"], "success")
        self.assertEqual(self._token_indices(annot), [])

    def test_explicit_subset_of_annotation_ids(self):
        doc = self._make_doc(pawls=_pawls_with_two_tokens_per_page())
        a1 = self._make_annotation(
            doc, {"top": 95, "left": 90, "right": 230, "bottom": 130}
        )
        a2 = self._make_annotation(
            doc, {"top": 95, "left": 90, "right": 230, "bottom": 130}
        )

        result = recalculate_annotation_tokens_from_bboxes.apply(
            kwargs={"document_id": doc.pk, "annotation_ids": [a1.pk]}
        ).get()
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["updated"], 1)
        # a1 was updated; a2's bogus tokens still in place.
        self.assertEqual(self._token_indices(a1), [0, 1])
        self.assertEqual(self._token_indices(a2), [99, 100])

    def test_multipage_annotation_recalculated_per_page(self):
        doc = self._make_doc(pawls=_pawls_with_two_tokens_per_page())
        # Annotation spans both page 0 (covers token 0) and page 1 (covers token 0).
        annot = Annotation.objects.create(
            raw_text="multi page",
            page=0,
            json={
                "0": {
                    "bounds": {
                        "top": 95,
                        "left": 95,
                        "right": 155,
                        "bottom": 125,
                    },
                    "tokensJsons": [{"pageIndex": 0, "tokenIndex": 99}],
                    "rawText": "Hello",
                },
                "1": {
                    "bounds": {
                        "top": 45,
                        "left": 45,
                        "right": 95,
                        "bottom": 70,
                    },
                    "tokensJsons": [{"pageIndex": 1, "tokenIndex": 99}],
                    "rawText": "Page2",
                },
            },
            annotation_label=self.label,
            document=doc,
            creator=self.user,
            annotation_type=TOKEN_LABEL,
        )

        recalculate_annotation_tokens_from_bboxes.apply(
            kwargs={"document_id": doc.pk}
        ).get()

        self.assertEqual(self._token_indices(annot, 0), [0])
        self.assertEqual(self._token_indices(annot, 1), [0])

    def test_skips_when_no_pawls_data(self):
        doc = self._make_doc(pawls=None)
        annot = self._make_annotation(
            doc, {"top": 95, "left": 90, "right": 230, "bottom": 130}
        )

        result = recalculate_annotation_tokens_from_bboxes.apply(
            kwargs={"document_id": doc.pk}
        ).get()

        self.assertEqual(result["status"], "skipped")
        self.assertEqual(self._token_indices(annot), [99, 100])

    def test_skips_when_document_missing(self):
        result = recalculate_annotation_tokens_from_bboxes.apply(
            kwargs={"document_id": 9999}
        ).get()
        self.assertEqual(result["status"], "skipped")

    def test_skips_when_doc_has_no_token_annotations(self):
        doc = self._make_doc(pawls=_pawls_with_two_tokens_per_page())
        result = recalculate_annotation_tokens_from_bboxes.apply(
            kwargs={"document_id": doc.pk}
        ).get()
        self.assertEqual(result["status"], "skipped")


class TestSetDocLockStateDispatchesRecalc(TestCase):
    """
    Verifies that the post-pipeline hook (``set_doc_lock_state``) dispatches
    the recalculation task whenever the document has at least one
    TOKEN_LABEL annotation. This is the canonical convention for
    post-pipeline fan-out (alongside ``process_corpus_action``); see
    ``opencontractserver/corpuses/signals.py`` for the documented pattern.
    """

    def setUp(self) -> None:
        self.user = User.objects.create_user(
            username="lock_recalc_user", password="testpass"
        )
        self.label = AnnotationLabel.objects.create(
            text="Heading",
            label_type=TOKEN_LABEL,
            creator=self.user,
            color="#FF0000",
        )

    def _make_doc(self) -> Document:
        return Document.objects.create(
            title="Hook Doc",
            creator=self.user,
            file_type="application/pdf",
            page_count=1,
        )

    def test_recalc_dispatched_when_unlocking_succeeds(self):
        from unittest.mock import patch

        from opencontractserver.documents.models import DocumentProcessingStatus
        from opencontractserver.tasks.doc_tasks import set_doc_lock_state

        doc = self._make_doc()
        doc.processing_status = DocumentProcessingStatus.PROCESSING
        doc.backend_lock = True
        doc.save(update_fields=["processing_status", "backend_lock"])

        # Need at least one TOKEN_LABEL annotation for the dispatch to fire.
        Annotation.objects.create(
            raw_text="hi",
            page=0,
            json={
                "0": {
                    "bounds": {"top": 0, "left": 0, "right": 1, "bottom": 1},
                    "tokensJsons": [],
                    "rawText": "hi",
                }
            },
            annotation_label=self.label,
            document=doc,
            creator=self.user,
            annotation_type=TOKEN_LABEL,
        )

        with patch(
            "opencontractserver.tasks.import_tasks."
            "recalculate_annotation_tokens_from_bboxes.delay"
        ) as mock_delay:
            set_doc_lock_state.apply(
                kwargs={"locked": False, "doc_id": doc.pk}
            ).get()

        mock_delay.assert_called_once_with(document_id=doc.pk)

    def test_recalc_not_dispatched_when_no_token_annotations(self):
        from unittest.mock import patch

        from opencontractserver.documents.models import DocumentProcessingStatus
        from opencontractserver.tasks.doc_tasks import set_doc_lock_state

        doc = self._make_doc()
        doc.processing_status = DocumentProcessingStatus.PROCESSING
        doc.backend_lock = True
        doc.save(update_fields=["processing_status", "backend_lock"])

        with patch(
            "opencontractserver.tasks.import_tasks."
            "recalculate_annotation_tokens_from_bboxes.delay"
        ) as mock_delay:
            set_doc_lock_state.apply(
                kwargs={"locked": False, "doc_id": doc.pk}
            ).get()

        mock_delay.assert_not_called()

    def test_recalc_not_dispatched_when_doc_failed(self):
        from unittest.mock import patch

        from opencontractserver.documents.models import DocumentProcessingStatus
        from opencontractserver.tasks.doc_tasks import set_doc_lock_state

        doc = self._make_doc()
        doc.processing_status = DocumentProcessingStatus.FAILED
        doc.backend_lock = True
        doc.save(update_fields=["processing_status", "backend_lock"])

        # Even with annotations present, FAILED means set_doc_lock_state
        # short-circuits before the recalc dispatch.
        Annotation.objects.create(
            raw_text="hi",
            page=0,
            json={
                "0": {
                    "bounds": {"top": 0, "left": 0, "right": 1, "bottom": 1},
                    "tokensJsons": [],
                    "rawText": "hi",
                }
            },
            annotation_label=self.label,
            document=doc,
            creator=self.user,
            annotation_type=TOKEN_LABEL,
        )

        with patch(
            "opencontractserver.tasks.import_tasks."
            "recalculate_annotation_tokens_from_bboxes.delay"
        ) as mock_delay:
            set_doc_lock_state.apply(
                kwargs={"locked": False, "doc_id": doc.pk}
            ).get()

        mock_delay.assert_not_called()
