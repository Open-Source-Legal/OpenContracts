"""Human review creates a successor on the new document without rewriting history."""

from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from opencontractserver.annotations.models import (
    SPAN_LABEL,
    Annotation,
    AnnotationVersionDecision,
    Relationship,
)
from opencontractserver.annotations.services.version_review import (
    AnnotationVersionReviewService as Review,
)
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.versioning import import_document
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.ids import to_global_id
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user


class AnnotationVersionReviewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="editor")
        self.corpus = Corpus.objects.create(title="Review", creator=self.user)
        self.label = self.corpus.ensure_label_and_labelset(
            label_text="Obligation",
            label_type=SPAN_LABEL,
            creator_id=self.user.pk,
        )
        self.v1 = self.upload("Pay promptly. Notify the owner. Removed clause.")
        self.pay = self.annotate("Pay promptly.", 0)
        self.notify = self.annotate("Notify the owner.", 14)
        self.removed = self.annotate("Removed clause.", 32)
        self.v2 = self.upload("Introduction. Pay promptly. Notify the new owner.")

    def upload(self, text, path="/contract.txt"):
        return import_document(
            corpus=self.corpus,
            path=path,
            content=text.encode(),
            user=self.user,
            file_type="text/plain",
            title="Contract",
        )[0]

    def annotate(self, text, start, **kwargs):
        return Annotation.objects.create(
            document=self.v1,
            corpus=self.corpus,
            creator=self.user,
            annotation_label=self.label,
            annotation_type=SPAN_LABEL,
            raw_text=text,
            json={"start": start, "end": start + len(text), "text": text},
            **kwargs,
        )

    def test_review_proposes_only_unique_exact_matches_and_excludes_derived_annotations(
        self,
    ):
        self.annotate("Layout", 0, structural=True)
        self.annotate("Grounding", 0, is_grounding_source=True)
        rows = Review.review(self.user, self.v2.pk, self.corpus.pk)
        self.assertEqual(
            {row.annotation.pk for row in rows},
            {self.pay.pk, self.notify.pk, self.removed.pk},
        )
        self.assertTrue(
            all(row.state == "STALE" and row.successor is None for row in rows)
        )
        proposed = next(
            row.proposed_placement for row in rows if row.annotation.pk == self.pay.pk
        )
        self.assertEqual(
            proposed["json"], {"start": 14, "end": 27, "text": "Pay promptly."}
        )
        self.assertIsNone(
            next(
                row.proposed_placement
                for row in rows
                if row.annotation.pk == self.removed.pk
            )
        )
        self.assertEqual(Review.stale_count(self.user, self.v2.pk, self.corpus.pk), 3)

        duplicate_text = self.upload(
            "Pay promptly. Pay promptly.", path="/ambiguous.txt"
        )
        self.assertIsNone(Review.propose(self.pay, duplicate_text))

    def test_approve_correct_and_drop_are_audited_and_the_next_hop_reviews_successors(
        self,
    ):
        approved = Review.carry_forward(self.user, self.pay.pk, self.v2.pk)
        corrected = Review.carry_forward(
            self.user,
            self.notify.pk,
            self.v2.pk,
            placement={"json": {"start": 28, "end": 49}},
        )
        dropped = Review.drop(self.user, self.removed.pk, self.v2.pk)
        self.assertEqual(
            (approved.decision, corrected.decision, dropped.decision),
            ("REAPPROVED", "CORRECTED", "DROPPED"),
        )
        self.assertEqual(approved.successor.document_id, self.v2.pk)
        self.assertEqual(approved.successor.raw_text, self.pay.raw_text)
        self.assertEqual(corrected.successor.raw_text, "Notify the new owner.")
        self.assertIsNone(dropped.successor_id)
        self.pay.refresh_from_db()
        self.assertEqual(self.pay.document_id, self.v1.pk)
        self.assertEqual(self.pay.json["start"], 0)
        self.assertEqual(Review.stale_count(self.user, self.v2.pk, self.corpus.pk), 0)
        self.assertEqual(Review.state_for_annotation(self.user, self.pay), "REAPPROVED")

        v3 = self.upload("Introduction. Pay promptly. Notify the new owner. Again.")
        self.assertEqual(
            {
                row.annotation.pk
                for row in Review.review(self.user, v3.pk, self.corpus.pk)
            },
            {approved.successor_id, corrected.successor_id},
        )
        self.assertEqual(Review.state_for_annotation(self.user, self.pay), "REAPPROVED")

    def test_decisions_are_unique_and_repeated_actions_do_not_leave_orphan_successors(
        self,
    ):
        decision = Review.carry_forward(self.user, self.pay.pk, self.v2.pk)
        with self.assertRaisesMessage(ValidationError, "already reviewed"):
            Review.carry_forward(self.user, self.pay.pk, self.v2.pk)
        self.assertEqual(Annotation.objects.filter(document=self.v2).count(), 1)
        with self.assertRaises(IntegrityError), transaction.atomic():
            AnnotationVersionDecision.objects.create(
                annotation=self.pay,
                target_document=self.v2,
                creator=self.user,
                decision="DROPPED",
            )
        self.assertEqual(
            AnnotationVersionDecision.objects.get(pk=decision.pk).decision, "REAPPROVED"
        )

    def test_label_change_is_a_correction_even_when_the_text_matches(self):
        other_label = self.corpus.ensure_label_and_labelset(
            label_text="Deadline",
            label_type=SPAN_LABEL,
            creator_id=self.user.pk,
        )
        decision = Review.carry_forward(
            self.user, self.pay.pk, self.v2.pk, label_id=other_label.pk
        )
        self.assertEqual(decision.decision, "CORRECTED")
        self.assertEqual(decision.successor.annotation_label_id, other_label.pk)

    def test_pdf_proposals_and_manual_placements_use_the_new_versions_real_tokens(self):
        import json

        from django.core.files.base import ContentFile

        from opencontractserver.annotations.compact_json import iter_page_annotations

        self.v2.file_type = "application/pdf"
        self.v2.pawls_parse_file.save(
            "review-pawls.json",
            ContentFile(
                json.dumps(
                    [
                        {
                            "page": {"index": 0, "width": 600, "height": 800},
                            "tokens": [
                                {
                                    "x": 10,
                                    "y": 10,
                                    "width": 20,
                                    "height": 10,
                                    "text": "Pay",
                                },
                                {
                                    "x": 35,
                                    "y": 10,
                                    "width": 50,
                                    "height": 10,
                                    "text": "promptly.",
                                },
                                {
                                    "x": 10,
                                    "y": 30,
                                    "width": 60,
                                    "height": 10,
                                    "text": "Revised.",
                                },
                            ],
                        }
                    ]
                ).encode()
            ),
        )
        decision = Review.carry_forward(self.user, self.pay.pk, self.v2.pk)
        page = list(iter_page_annotations(decision.successor.json))[0]
        self.assertEqual(page.token_indices, [0, 1])
        self.assertEqual(decision.decision, "REAPPROVED")
        corrected = Review.carry_forward(
            self.user,
            self.notify.pk,
            self.v2.pk,
            placement={
                "json": {
                    "0": {
                        "tokensJsons": [{"pageIndex": 0, "tokenIndex": 2}],
                        "bounds": {},
                        "rawText": "Untrusted client text",
                    },
                }
            },
        )
        self.assertEqual(corrected.decision, "CORRECTED")
        self.assertEqual(corrected.successor.raw_text, "Revised.")
        self.assertEqual(
            list(iter_page_annotations(corrected.successor.json))[0].bounds,
            {"left": 10, "top": 30, "right": 70, "bottom": 40},
        )

    def test_graphql_exposes_review_state_and_refreshes_the_stale_count(self):
        from config.graphql.schema import schema
        from config.graphql.testing import Client

        client = Client(schema, context_value=SimpleNamespace(user=self.user))
        relationship = Relationship.objects.create(
            document=self.v1, corpus=self.corpus, creator=self.user
        )
        relationship.source_annotations.add(self.pay)
        relationship.target_annotations.add(self.notify)
        document_id = to_global_id("DocumentType", self.v2.pk)
        corpus_id = to_global_id("CorpusType", self.corpus.pk)
        result = client.execute(
            """query($document: ID!, $corpus: ID!) {
          document(id: $document) { staleAnnotationCount(corpusId: $corpus) }
          annotationVersionReview(documentId: $document, corpusId: $corpus) {
            annotation { id rawText versionState } state proposedPlacement
          }
        }""",
            variable_values={"document": document_id, "corpus": corpus_id},
        )
        self.assertNotIn("errors", result, result)
        self.assertEqual(result["data"]["document"]["staleAnnotationCount"], 3)
        self.assertEqual(len(result["data"]["annotationVersionReview"]), 3)
        self.assertTrue(
            all(
                row["annotation"]["versionState"] == "STALE"
                for row in result["data"]["annotationVersionReview"]
            )
        )
        result = client.execute(
            """mutation($annotation: ID!, $target: ID!) {
          carryForwardAnnotation(annotationId: $annotation, targetDocumentId: $target) {
            state successor { rawText document { id } } reviewedBy { slug } reviewedAt
          }
        }""",
            variable_values={
                "annotation": to_global_id("AnnotationType", self.pay.pk),
                "target": document_id,
            },
        )
        self.assertNotIn("errors", result, result)
        row = result["data"]["carryForwardAnnotation"]
        self.assertEqual(row["state"], "REAPPROVED")
        self.assertEqual(row["successor"]["document"]["id"], document_id)
        self.assertEqual(row["reviewedBy"]["slug"], self.user.slug)
        self.assertIsNotNone(row["reviewedAt"])
        # The historical viewer must still load its evidence and relationship
        # endpoints; approving a successor must never transplant the old edge.
        history = client.execute(
            """query($document: ID!, $corpus: ID!) {
          document(id: $document) {
            allAnnotations(corpusId: $corpus, analysisId: "__none__") { id rawText versionState }
            allRelationships(corpusId: $corpus, analysisId: "__none__") {
              id sourceAnnotations { edges { node { id } } }
              targetAnnotations { edges { node { id } } }
            }
          }
        }""",
            variable_values={
                "document": to_global_id("DocumentType", self.v1.pk),
                "corpus": corpus_id,
            },
        )
        self.assertNotIn("errors", history, history)
        self.assertEqual(len(history["data"]["document"]["allAnnotations"]), 3)
        states = {
            annotation["rawText"]: annotation["versionState"]
            for annotation in history["data"]["document"]["allAnnotations"]
        }
        self.assertEqual(states["Pay promptly."], "REAPPROVED")
        self.assertEqual(states["Notify the owner."], "STALE")
        old_edge = history["data"]["document"]["allRelationships"][0]
        self.assertEqual(
            old_edge["sourceAnnotations"]["edges"][0]["node"]["id"],
            to_global_id("AnnotationType", self.pay.pk),
        )
        self.assertEqual(
            old_edge["targetAnnotations"]["edges"][0]["node"]["id"],
            to_global_id("AnnotationType", self.notify.pk),
        )
        self.assertFalse(Relationship.objects.filter(document=self.v2).exists())

    def test_a_further_version_retires_state_no_target_would_accept(self):
        """A badge that no mutation honours is worse than no badge."""
        self.assertEqual(Review.state_for_annotation(self.user, self.pay), "STALE")
        self.assertEqual(Review.stale_count(self.user, self.v2.pk, self.corpus.pk), 3)

        v3 = self.upload("Introduction. Pay promptly. Notify the new owner. Again.")

        self.assertIsNone(Review.state_for_annotation(self.user, self.pay))
        self.assertEqual(Review.stale_count(self.user, self.v2.pk, self.corpus.pk), 0)
        for target in (self.v2, v3):
            with self.subTest(target=target.pk), self.assertRaisesMessage(
                ValidationError, "immediately following version"
            ):
                Review.carry_forward(self.user, self.pay.pk, target.pk)

    def test_a_corpus_the_document_does_not_belong_to_counts_zero_stale(self):
        """``staleAnnotationCount`` is non-null; denying it would null the document."""
        from config.graphql.schema import schema
        from config.graphql.testing import Client

        unrelated = Corpus.objects.create(title="Elsewhere", creator=self.user)
        client = Client(schema, context_value=SimpleNamespace(user=self.user))
        result = client.execute(
            """query($document: ID!, $corpus: ID!) {
          document(id: $document) { id staleAnnotationCount(corpusId: $corpus) }
        }""",
            variable_values={
                "document": to_global_id("DocumentType", self.v2.pk),
                "corpus": to_global_id("CorpusType", unrelated.pk),
            },
        )
        self.assertNotIn("errors", result, result)
        self.assertEqual(result["data"]["document"]["staleAnnotationCount"], 0)

    def test_review_requires_update_on_both_document_and_corpus(self):
        reviewer = get_user_model().objects.create_user(username="reader")
        for obj in (self.v1, self.v2, self.corpus):
            set_permissions_for_obj_to_user(reviewer, obj, [PermissionTypes.READ])
        self.assertEqual(Review.stale_count(reviewer, self.v2.pk, self.corpus.pk), 3)
        with self.assertRaises(PermissionDenied):
            Review.drop(reviewer, self.pay.pk, self.v2.pk)
        set_permissions_for_obj_to_user(
            reviewer, self.v2, [PermissionTypes.READ, PermissionTypes.UPDATE]
        )
        with self.assertRaises(PermissionDenied):
            Review.carry_forward(reviewer, self.pay.pk, self.v2.pk)
        set_permissions_for_obj_to_user(
            reviewer, self.corpus, [PermissionTypes.READ, PermissionTypes.UPDATE]
        )
        self.assertEqual(
            Review.drop(reviewer, self.pay.pk, self.v2.pk).creator, reviewer
        )

    def test_unrelated_targets_invalid_placements_and_foreign_labels_are_rejected(self):
        unrelated = self.upload("Pay promptly.", path="/another.txt")
        with self.assertRaises(ValidationError):
            Review.carry_forward(self.user, self.pay.pk, unrelated.pk)
        for placement in (
            {"json": {"start": -1, "end": 5}},
            {"json": {"start": 0, "end": 999}},
        ):
            with self.subTest(placement=placement), self.assertRaises(ValidationError):
                Review.carry_forward(
                    self.user, self.pay.pk, self.v2.pk, placement=placement
                )
        other_corpus = Corpus.objects.create(title="Elsewhere", creator=self.user)
        foreign_label = other_corpus.ensure_label_and_labelset(
            label_text="Private label",
            label_type=SPAN_LABEL,
            creator_id=self.user.pk,
        )
        with self.assertRaises(ValidationError):
            Review.carry_forward(
                self.user, self.pay.pk, self.v2.pk, label_id=foreign_label.pk
            )
        self.upload("Third version.")
        with self.assertRaises(ValidationError):
            Review.drop(self.user, self.pay.pk, self.v2.pk)
        self.assertFalse(AnnotationVersionDecision.objects.exists())
