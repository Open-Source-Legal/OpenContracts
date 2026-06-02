"""Unit tests for the remap_pending_annotations Celery task.

Verifies that PendingDocumentAnnotations are correctly consumed after
pipeline output (PAWLs / text layer) is present on the document.
"""

from __future__ import annotations

import json

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TestCase
from django.utils import timezone

from opencontractserver.annotations.models import (
    TOKEN_LABEL,
    Annotation,
    AnnotationLabel,
    LabelSet,
)
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document, PendingDocumentAnnotations
from opencontractserver.tasks.doc_tasks import remap_pending_annotations

User = get_user_model()

# ---------------------------------------------------------------------------
# Minimal v1 PAWLs fixture — one page, two tokens ("CHAPTER", "1") that the
# anchoring logic can locate via bbox overlap or fuzzy-text match.
# ---------------------------------------------------------------------------
_PAWLS_V1 = [
    {
        "page": {"width": 612.0, "height": 792.0, "index": 0},
        "tokens": [
            {"x": 10.0, "y": 10.0, "width": 56.0, "height": 12.0, "text": "CHAPTER"},
            {"x": 90.0, "y": 10.0, "width": 8.0, "height": 12.0, "text": "1"},
        ],
    }
]

_TEXT_CONTENT = b"CHAPTER 1"

# Dumb-anchor annotation covering both tokens.  bbox left=8, right=110 wraps
# both tokens (x=10..66 and x=90..98) with slight padding, ensuring
# select_tokens_in_region finds them and the text confirmation passes.
_DUMB_ANN = {
    "id": "a1",
    "label": "OC_SECTION",
    "rawText": "CHAPTER 1",
    "page": 0,
    "bbox": {"left": 8.0, "top": 8.0, "right": 110.0, "bottom": 24.0},
    "parent_id": None,
}


class TestRemapPendingAnnotations(TestCase):
    """remap_pending_annotations happy-path and skip-path tests."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="remap_test_user", password="testpass"
        )

        # -- LabelSet + label ------------------------------------------------
        self.labelset = LabelSet.objects.create(
            title="Test LabelSet",
            creator=self.user,
        )
        self.label = AnnotationLabel.objects.create(
            text="OC_SECTION",
            label_type=TOKEN_LABEL,
            creator=self.user,
        )
        self.labelset.annotation_labels.add(self.label)

        # -- Corpus with labelset --------------------------------------------
        self.corpus = Corpus.objects.create(
            title="Test Corpus",
            creator=self.user,
            label_set=self.labelset,
        )

        # -- Document: set processing_started so the post_save signal is
        #    suppressed (signal only fires when not instance.processing_started).
        self.doc = Document.objects.create(
            title="Test Doc",
            creator=self.user,
            file_type="application/pdf",
            processing_started=timezone.now(),
        )

        # Save PAWLs and text layer after creation (outside any class-level
        # transaction wrapping so the files are on disk when the task runs).
        pawls_bytes = json.dumps(_PAWLS_V1).encode("utf-8")
        self.doc.pawls_parse_file.save(
            "test_pawls.json", ContentFile(pawls_bytes), save=True
        )
        self.doc.txt_extract_file.save(
            "test_text.txt", ContentFile(_TEXT_CONTENT), save=True
        )

        # -- PendingDocumentAnnotations row ----------------------------------
        self.pending = PendingDocumentAnnotations.objects.create(
            document=self.doc,
            corpus=self.corpus,
            creator=self.user,
            payload={
                "annotations": [_DUMB_ANN],
                "doc_labels": [],
            },
            status=PendingDocumentAnnotations.Status.PENDING,
        )

    # -----------------------------------------------------------------------

    def test_id_less_annotation_imports_and_is_not_failed(self):
        """An anchored annotation without an export-local ``id`` still imports;
        the row must be DONE (not FAILED) and ``anchored`` must count it.

        Regression: the status decision previously keyed off ``annot_id_map``,
        which only contains id-bearing annotations, so an id-less-but-created
        annotation wrongly flipped the row to FAILED with anchored=0.
        """
        ann_no_id = {k: v for k, v in _DUMB_ANN.items() if k != "id"}
        self.pending.payload = {"annotations": [ann_no_id], "doc_labels": []}
        self.pending.save(update_fields=["payload"])

        result = remap_pending_annotations(doc_id=self.doc.id)

        self.assertEqual(result["anchored"], 1, msg=f"Unexpected result: {result}")
        self.assertEqual(result["status"], PendingDocumentAnnotations.Status.DONE)
        self.pending.refresh_from_db()
        self.assertEqual(self.pending.status, PendingDocumentAnnotations.Status.DONE)
        self.assertEqual(
            Annotation.objects.filter(
                document=self.doc, annotation_label=self.label
            ).count(),
            1,
        )

    def test_annotation_created_and_pending_marked_done(self):
        """Task creates an Annotation for OC_SECTION and marks pending as DONE."""
        result = remap_pending_annotations(doc_id=self.doc.id)

        # Return value
        self.assertEqual(result["doc_id"], self.doc.id)
        self.assertIn("anchored", result, msg=f"Unexpected result: {result}")
        self.assertGreaterEqual(result["anchored"], 1)

        # PendingDocumentAnnotations row updated
        self.pending.refresh_from_db()
        self.assertEqual(self.pending.status, PendingDocumentAnnotations.Status.DONE)

        # Annotation exists
        anns = Annotation.objects.filter(
            document=self.doc,
            corpus=self.corpus,
            annotation_label=self.label,
        )
        self.assertEqual(
            anns.count(), 1, msg="Expected exactly one OC_SECTION annotation"
        )
        ann = anns.first()

        # annotation_json should contain the page key with tokensJsons
        self.assertIn(
            "0", ann.json, msg=f"annotation_json missing page '0': {ann.json}"
        )
        page_data = ann.json["0"]
        tokens_json = page_data.get("tokensJsons") or []
        self.assertTrue(len(tokens_json) > 0, "tokensJsons should be non-empty")

        # Joined token text should contain "CHAPTER"
        token_indices = [
            t["tokenIndex"] if isinstance(t, dict) else t for t in tokens_json
        ]
        page_tokens = _PAWLS_V1[0]["tokens"]
        joined = " ".join(
            page_tokens[i]["text"] for i in token_indices if i < len(page_tokens)
        )
        self.assertIn(
            "CHAPTER", joined, msg=f"Expected 'CHAPTER' in joined tokens: {joined!r}"
        )

    def test_skipped_when_no_pending_row(self):
        """Task returns a 'skipped' dict when the document has no pending row."""
        other_doc = Document.objects.create(
            title="Other Doc",
            creator=self.user,
            file_type="application/pdf",
            processing_started=timezone.now(),
        )
        result = remap_pending_annotations(doc_id=other_doc.id)
        self.assertIn("skipped", result, msg=f"Expected 'skipped' key, got: {result}")
        self.assertEqual(result["doc_id"], other_doc.id)

    def test_unresolved_label_is_reported_not_silently_dropped(self):
        """An anchored annotation whose label is absent from the corpus labelset
        must NOT be created, and the loss must be visible.

        The annotation anchors fine onto the PAWLs (geometry/text match), but
        import_annotations silently skips it because its label is not in the
        corpus labelset. The remap task must record a dropped report entry that
        cites the missing label, surface ``label_unresolved`` in the return
        dict, and — since nothing landed — mark the pending row FAILED rather
        than a silent DONE.
        """
        # A second pending doc referencing a label NOT in the corpus labelset.
        doc = Document.objects.create(
            title="Bad Label Doc",
            creator=self.user,
            file_type="application/pdf",
            processing_started=timezone.now(),
        )
        pawls_bytes = json.dumps(_PAWLS_V1).encode("utf-8")
        doc.pawls_parse_file.save("bad_pawls.json", ContentFile(pawls_bytes), save=True)
        doc.txt_extract_file.save("bad_text.txt", ContentFile(_TEXT_CONTENT), save=True)

        bad_ann = dict(_DUMB_ANN)
        bad_ann["label"] = "NOT_IN_LABELSET"
        pending = PendingDocumentAnnotations.objects.create(
            document=doc,
            corpus=self.corpus,
            creator=self.user,
            payload={"annotations": [bad_ann], "doc_labels": []},
            status=PendingDocumentAnnotations.Status.PENDING,
        )

        result = remap_pending_annotations(doc_id=doc.id)

        # No annotation should have been created for this document.
        self.assertEqual(
            Annotation.objects.filter(document=doc).count(),
            0,
            msg="Annotation with an unresolved label must not be created",
        )

        # Return dict reflects the unresolved label and the empty anchoring.
        self.assertEqual(result["anchored"], 0, msg=f"Unexpected result: {result}")
        self.assertEqual(
            result["label_unresolved"], 1, msg=f"Unexpected result: {result}"
        )
        self.assertEqual(
            result["status"],
            PendingDocumentAnnotations.Status.FAILED,
            msg=f"Unexpected result: {result}",
        )

        # Pending row marked FAILED (everything anchored was dropped on label).
        pending.refresh_from_db()
        self.assertEqual(pending.status, PendingDocumentAnnotations.Status.FAILED)

        # Report has a dropped entry citing the missing label.
        dropped = [r for r in pending.report if r.get("dropped")]
        self.assertTrue(
            dropped, msg=f"Expected a dropped report entry: {pending.report}"
        )
        self.assertTrue(
            any(
                "NOT_IN_LABELSET" in (r.get("reason") or "")
                and "labelset" in (r.get("reason") or "")
                for r in dropped
            ),
            msg=f"Expected a report entry citing the missing label: {dropped}",
        )
