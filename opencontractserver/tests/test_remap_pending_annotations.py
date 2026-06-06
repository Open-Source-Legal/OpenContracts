"""Unit tests for the remap_pending_annotations Celery task.

Verifies that PendingDocumentAnnotations are correctly consumed after
pipeline output (PAWLs / text layer) is present on the document.
"""

from __future__ import annotations

import json

import pytest
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TestCase
from django.utils import timezone

from opencontractserver.annotations.models import (
    TOKEN_LABEL,
    Annotation,
    AnnotationLabel,
    LabelSet,
    Relationship,
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

    def test_concurrent_claim_guard_skips_already_processed_row(self):
        """A row flipped to DONE after the batch read is skipped, not re-imported.

        Simulates the Celery at-least-once race (review finding #2): a sibling
        worker has already processed the row by the time this one acquires the
        FOR UPDATE lock. The guard must bail before ``import_annotations`` so no
        duplicate annotations are created.
        """
        from opencontractserver.tasks.doc_tasks import _remap_one_pending_row

        # In-memory object still reads PENDING (as it would right after the batch
        # ``filter(status=PENDING)`` materialised it)...
        stale_pending = PendingDocumentAnnotations.objects.get(pk=self.pending.pk)
        # ...but a sibling worker has already finished and flipped the DB row.
        PendingDocumentAnnotations.objects.filter(pk=self.pending.pk).update(
            status=PendingDocumentAnnotations.Status.DONE
        )

        result = _remap_one_pending_row(stale_pending, self.doc, {})

        self.assertIn("skipped", result, msg=f"Expected a skip, got {result}")
        # No annotations were created by this redundant pass.
        self.assertEqual(
            Annotation.objects.filter(
                document=self.doc, annotation_label=self.label
            ).count(),
            0,
            msg="Concurrent-claim guard must not create duplicate annotations",
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

        # annotation_json is persisted in the canonical compact v2 form
        # ``{"v": 2, "p": {page: {"b": [...], "t": "<ranges>"}}}`` — matching the
        # parser's structural annotations.
        from opencontractserver.annotations.compact_json import decode_token_ranges

        self.assertEqual(ann.json.get("v"), 2, msg=f"expected compact v2: {ann.json}")
        self.assertIn("0", ann.json["p"], msg=f"missing page '0': {ann.json}")
        token_indices = decode_token_ranges(ann.json["p"]["0"]["t"])
        self.assertTrue(len(token_indices) > 0, "token indices should be non-empty")

        # Joined token text should contain "CHAPTER"
        page_tokens = _PAWLS_V1[0]["tokens"]
        joined = " ".join(
            page_tokens[i]["text"] for i in token_indices if i < len(page_tokens)
        )
        self.assertIn(
            "CHAPTER", joined, msg=f"Expected 'CHAPTER' in joined tokens: {joined!r}"
        )

    def test_run_id_filter_applies_only_matching_run(self):
        """run_id scopes which PENDING rows are processed."""
        import uuid

        run = uuid.uuid4()
        self.pending.ingestion_run_id = run
        self.pending.save(update_fields=["ingestion_run_id"])

        # Non-matching run id → nothing processed, row stays PENDING.
        other = uuid.uuid4()
        result = remap_pending_annotations(doc_id=self.doc.id, run_id=str(other))
        self.assertIn("skipped", result, msg=f"Unexpected result: {result}")
        self.pending.refresh_from_db()
        self.assertEqual(self.pending.status, PendingDocumentAnnotations.Status.PENDING)

        # Matching run id → processed (row leaves PENDING).
        result = remap_pending_annotations(doc_id=self.doc.id, run_id=str(run))
        self.assertNotIn("skipped", result, msg=f"Unexpected result: {result}")
        self.pending.refresh_from_db()
        self.assertEqual(self.pending.status, PendingDocumentAnnotations.Status.DONE)

    def test_run_id_none_applies_all_pending(self):
        """run_id=None (the standard-chain call) processes every PENDING row
        regardless of which run stamped it."""
        import uuid

        self.pending.ingestion_run_id = uuid.uuid4()
        self.pending.save(update_fields=["ingestion_run_id"])

        result = remap_pending_annotations(doc_id=self.doc.id, run_id=None)
        self.assertNotIn("skipped", result, msg=f"Unexpected result: {result}")
        self.pending.refresh_from_db()
        self.assertEqual(self.pending.status, PendingDocumentAnnotations.Status.DONE)

    @pytest.mark.usefixtures("enable_doc_processing_signals")
    def test_standard_chain_includes_remap_step(self):
        """The standard post_save ingest chain must schedule remap_pending_annotations.

        Regression lock for the wiring: the bulk-ZIP importer no longer owns a
        bespoke chain, so deferred annotations only get applied if the standard
        chain carries the remap step. We mock ``chain`` in the signal module and
        capture the on_commit dispatch, so the real pipeline never runs — we
        only assert the remap task signature is present, between ingest and the
        unlock step. End-to-end proof lives in the zip-import integration test.
        """
        from unittest.mock import patch

        with patch("opencontractserver.documents.signals.chain") as mock_chain:
            with self.captureOnCommitCallbacks(execute=True):
                Document.objects.create(
                    title="chain probe",
                    creator=self.user,
                    file_type="application/pdf",
                )

        self.assertTrue(mock_chain.called, "standard ingest chain was not dispatched")
        signatures = mock_chain.call_args.args
        task_names = [sig["task"] for sig in signatures]
        self.assertIn(
            "opencontractserver.tasks.doc_tasks.remap_pending_annotations",
            task_names,
            msg=f"remap step missing from chain: {task_names}",
        )
        # Must sit AFTER ingest (PAWLs/text exist) and BEFORE unlock.
        self.assertLess(
            task_names.index("opencontractserver.tasks.doc_tasks.ingest_doc"),
            task_names.index(
                "opencontractserver.tasks.doc_tasks.remap_pending_annotations"
            ),
        )
        self.assertLess(
            task_names.index(
                "opencontractserver.tasks.doc_tasks.remap_pending_annotations"
            ),
            task_names.index("opencontractserver.tasks.doc_tasks.set_doc_lock_state"),
        )

    def test_id_map_persisted_after_remap(self):
        """remap stores the old_id -> new_annotation_pk map on the row; the
        relationship-wiring step (and any later consumer) reads it without a
        backfill."""
        result = remap_pending_annotations(doc_id=self.doc.id)
        self.assertNotIn("skipped", result)
        self.pending.refresh_from_db()
        ann = Annotation.objects.get(document=self.doc, annotation_label=self.label)
        # _DUMB_ANN carries id "a1"; JSON object keys are strings.
        self.assertEqual(self.pending.id_map, {"a1": ann.id})

    # -- annotation-to-annotation relationship wiring ------------------------

    def test_relationship_between_annotations_is_created(self):
        """A sidecar ``relationships`` edge is wired between the two anchored
        annotations using the import id_map, auto-creating its RELATIONSHIP_LABEL.
        """
        ann1 = {**_DUMB_ANN, "id": "a1"}
        ann2 = {**_DUMB_ANN, "id": "a2"}
        self.pending.payload = {
            "annotations": [ann1, ann2],
            "doc_labels": [],
            "relationships": [
                {
                    "id": "r1",
                    "relationshipLabel": "REFERENCES",
                    "source_annotation_ids": ["a1"],
                    "target_annotation_ids": ["a2"],
                }
            ],
        }
        self.pending.save(update_fields=["payload"])

        result = remap_pending_annotations(doc_id=self.doc.id)

        self.assertEqual(result["status"], PendingDocumentAnnotations.Status.DONE)
        self.assertEqual(result["relationships"], 1, msg=f"{result}")
        self.assertEqual(result["relationships_dropped"], 0, msg=f"{result}")

        rels = Relationship.objects.filter(document=self.doc, corpus=self.corpus)
        self.assertEqual(rels.count(), 1)
        rel = rels.first()
        self.assertEqual(rel.relationship_label.text, "REFERENCES")
        self.assertEqual(rel.relationship_label.label_type, "RELATIONSHIP_LABEL")
        # Producer relationships are never structural.
        self.assertFalse(rel.structural)

        src = list(rel.source_annotations.all())
        tgt = list(rel.target_annotations.all())
        self.assertEqual(len(src), 1)
        self.assertEqual(len(tgt), 1)
        self.assertNotEqual(src[0].id, tgt[0].id)

        # The id_map carries both annotation endpoints (keys stringified).
        self.pending.refresh_from_db()
        self.assertEqual(set(self.pending.id_map.keys()), {"a1", "a2"})

    def test_relationship_endpoint_ids_match_across_int_and_str(self):
        """An int sidecar annotation id and a str relationship endpoint id (or
        vice versa) still resolve — the wiring accepts both forms."""
        ann1 = {**_DUMB_ANN, "id": 1}
        ann2 = {**_DUMB_ANN, "id": 2}
        self.pending.payload = {
            "annotations": [ann1, ann2],
            "doc_labels": [],
            "relationships": [
                {
                    "relationshipLabel": "REFERENCES",
                    "source_annotation_ids": ["1"],  # str vs int id above
                    "target_annotation_ids": [2],
                }
            ],
        }
        self.pending.save(update_fields=["payload"])

        result = remap_pending_annotations(doc_id=self.doc.id)
        self.assertEqual(result["relationships"], 1, msg=f"{result}")
        self.assertEqual(Relationship.objects.filter(document=self.doc).count(), 1)

    def test_link_url_and_data_persisted_on_annotations(self):
        """``link_url`` (OC_URL) and ``data`` (geocoded payload) survive the
        deferred remap onto the created Annotation."""
        geo = {"canonical_name": "France", "lat": 46.0, "lng": 2.0, "geocoded": True}
        ann = {
            **_DUMB_ANN,
            "id": "u1",
            "link_url": "https://example.com/ref",
            "data": geo,
        }
        self.pending.payload = {"annotations": [ann], "doc_labels": []}
        self.pending.save(update_fields=["payload"])

        result = remap_pending_annotations(doc_id=self.doc.id)
        self.assertEqual(result["status"], PendingDocumentAnnotations.Status.DONE)

        ann_obj = Annotation.objects.get(document=self.doc, annotation_label=self.label)
        self.assertEqual(ann_obj.link_url, "https://example.com/ref")
        self.assertEqual(ann_obj.data, geo)

    def test_relationship_with_dangling_endpoint_dropped_and_reported(self):
        """A relationship whose target never anchored is dropped (not silently)
        and counted, while the resolvable annotation still lands (row DONE)."""
        ann1 = {**_DUMB_ANN, "id": "a1"}
        self.pending.payload = {
            "annotations": [ann1],
            "doc_labels": [],
            "relationships": [
                {
                    "id": "r1",
                    "relationshipLabel": "REFERENCES",
                    "source_annotation_ids": ["a1"],
                    "target_annotation_ids": ["ghost"],  # never declared/anchored
                }
            ],
        }
        self.pending.save(update_fields=["payload"])

        result = remap_pending_annotations(doc_id=self.doc.id)

        # The annotation landed, so the row is DONE despite the dropped edge.
        self.assertEqual(result["status"], PendingDocumentAnnotations.Status.DONE)
        self.assertEqual(result["relationships"], 0, msg=f"{result}")
        self.assertEqual(result["relationships_dropped"], 1, msg=f"{result}")
        self.assertEqual(Relationship.objects.filter(document=self.doc).count(), 0)

        self.pending.refresh_from_db()
        self.assertTrue(
            any(
                r.get("dropped") and "target" in (r.get("reason") or "")
                for r in self.pending.report
            ),
            msg=f"Expected a dropped-target report entry: {self.pending.report}",
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

    def test_total_anchor_failure_is_reported_failed_not_done(self):
        """When NO annotation anchors (geometry miss + rawText not found), the
        row must be FAILED, not a silent DONE.

        Regression for the ``anchored and created == 0`` guard: with every
        annotation failing to anchor, ``anchored == []`` made the guard
        ``[] and ...`` → False → DONE, mis-reporting a total anchor failure as
        success even though the producer asked for an annotation and it was
        dropped. The label resolves fine here (OC_SECTION) — the failure is
        purely anchoring, distinguishing it from the unresolved-label path.
        """
        doc = Document.objects.create(
            title="Unanchorable Doc",
            creator=self.user,
            file_type="application/pdf",
            processing_started=timezone.now(),
        )
        pawls_bytes = json.dumps(_PAWLS_V1).encode("utf-8")
        doc.pawls_parse_file.save(
            "unanchor_pawls.json", ContentFile(pawls_bytes), save=True
        )
        doc.txt_extract_file.save(
            "unanchor_text.txt", ContentFile(_TEXT_CONTENT), save=True
        )

        # bbox far from any token AND rawText that won't fuzzy-match "CHAPTER 1".
        unanchorable = dict(_DUMB_ANN)
        unanchorable["bbox"] = {
            "left": 500.0,
            "top": 500.0,
            "right": 560.0,
            "bottom": 520.0,
        }
        unanchorable["rawText"] = "ZZZ NONEXISTENT PHRASE QQQ"
        pending = PendingDocumentAnnotations.objects.create(
            document=doc,
            corpus=self.corpus,
            creator=self.user,
            payload={"annotations": [unanchorable], "doc_labels": []},
            status=PendingDocumentAnnotations.Status.PENDING,
        )

        result = remap_pending_annotations(doc_id=doc.id)

        # Nothing landed, and the failure to anchor is surfaced — not DONE.
        self.assertEqual(
            Annotation.objects.filter(document=doc).count(),
            0,
            msg="Unanchorable annotation must not be created",
        )
        self.assertEqual(result["anchored"], 0, msg=f"Unexpected result: {result}")
        self.assertEqual(
            result["label_unresolved"],
            0,
            msg=f"Label resolves; failure is anchoring, not label: {result}",
        )
        self.assertEqual(
            result["status"],
            PendingDocumentAnnotations.Status.FAILED,
            msg=f"Total anchor failure must be FAILED, not DONE: {result}",
        )

        pending.refresh_from_db()
        self.assertEqual(pending.status, PendingDocumentAnnotations.Status.FAILED)
        dropped = [r for r in pending.report if r.get("dropped")]
        self.assertTrue(
            dropped, msg=f"Expected a dropped report entry: {pending.report}"
        )
