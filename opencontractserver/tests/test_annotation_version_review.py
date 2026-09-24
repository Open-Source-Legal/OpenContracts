"""A version-up carries human annotations forward, flagged until a person checks them.

The contract, end to end on real uploads: unique exact matches are carried
automatically as ``AUTO``, everything else is ``STALE``; both stay pending
until a reviewer approves, corrects or drops them; relationships follow once
every endpoint has a successor; and the original version is never rewritten.
"""

import json
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.base import ContentFile
from django.test import TestCase

from config.graphql.schema import schema
from config.graphql.testing import Client
from opencontractserver.annotations.compact_json import iter_page_annotations
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

V1 = "Pay promptly. Notify the owner. Removed clause."
V2 = "Introduction. Pay promptly. Notify the new owner."


class AnnotationVersionReviewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="editor")
        self.corpus = Corpus.objects.create(title="Review", creator=self.user)
        self.label = self.label_named("Obligation")
        self.v1 = self.upload(V1)
        self.pay = self.annotate("Pay promptly.", 0)
        self.notify = self.annotate("Notify the owner.", 14)
        self.removed = self.annotate("Removed clause.", 32)
        self.edge = Relationship.objects.create(
            document=self.v1, corpus=self.corpus, creator=self.user
        )
        self.edge.source_annotations.add(self.pay)
        self.edge.target_annotations.add(self.notify)
        self.v2 = self.upload(V2)

    # -- fixtures ---------------------------------------------------------

    def label_named(self, text):
        return self.corpus.ensure_label_and_labelset(
            label_text=text, label_type=SPAN_LABEL, creator_id=self.user.pk
        )

    def upload(self, text, path="/contract.txt"):
        return import_document(
            corpus=self.corpus,
            path=path,
            content=text.encode(),
            user=self.user,
            file_type="text/plain",
            title="Contract",
        )[0]

    def annotate(self, text, start, document=None, **kwargs):
        return Annotation.objects.create(
            document=document or self.v1,
            corpus=self.corpus,
            creator=self.user,
            annotation_label=self.label,
            annotation_type=SPAN_LABEL,
            raw_text=text,
            json={"start": start, "end": start + len(text), "text": text},
            **kwargs,
        )

    def carried(self):
        """Carry v1 onto v2 and return each original's decision by raw text."""
        Review.carry_version(self.v2)
        return {
            d.annotation.raw_text: d
            for d in AnnotationVersionDecision.objects.select_related(
                "annotation", "successor"
            )
        }

    def pending(self, user=None, document=None):
        return Review.pending_count(
            user or self.user, (document or self.v2).pk, self.corpus.pk
        )

    def graphql(self, query, user=None, **variables):
        client = Client(schema, context_value=SimpleNamespace(user=user or self.user))
        result = client.execute(query, variable_values=variables)
        self.assertNotIn("errors", result, result)
        return result["data"]

    # -- automatic carry --------------------------------------------------

    def test_version_up_carries_unique_matches_and_flags_the_rest_for_review(self):
        self.annotate("Pay promptly.", 0, structural=True)
        self.annotate("Pay promptly.", 0, is_grounding_source=True)

        decisions = self.carried()

        self.assertEqual(
            set(decisions), {"Pay promptly.", "Notify the owner.", "Removed clause."}
        )
        pay = decisions["Pay promptly."]
        self.assertEqual(pay.decision, "AUTO")
        self.assertEqual(pay.successor.document_id, self.v2.pk)
        self.assertEqual(pay.successor.json["start"], V2.index("Pay promptly."))
        self.assertEqual(pay.successor.creator_id, self.pay.creator_id)
        self.assertIsNone(pay.reviewer)
        for text in ("Notify the owner.", "Removed clause."):
            self.assertEqual(decisions[text].decision, "STALE")
            self.assertIsNone(decisions[text].successor)
        self.assertEqual(self.pending(), 3, "machine-carried rows still need a person")

        self.pay.refresh_from_db()
        self.assertEqual(
            (self.pay.document_id, self.pay.json["start"]), (self.v1.pk, 0)
        )

        Review.carry_version(self.v2)
        self.assertEqual(Annotation.objects.filter(document=self.v2).count(), 1)

    def test_repeated_text_is_never_auto_placed(self):
        ambiguous = self.upload("Pay promptly. Pay promptly.", path="/ambiguous.txt")
        self.assertIsNone(Review.propose(self.pay, ambiguous))

    def test_unlocking_a_parsed_version_triggers_the_carry(self):
        from opencontractserver.tasks.doc_tasks import set_doc_lock_state

        with patch(
            "opencontractserver.tasks.corpus_tasks.process_corpus_action.delay"
        ), patch(
            "opencontractserver.tasks.doc_tasks._queue_embeddings_for_unlocked_document"
        ), self.captureOnCommitCallbacks(
            execute=True
        ):
            set_doc_lock_state(locked=False, doc_id=self.v2.pk)

        self.assertEqual(self.pending(), 3)

    # -- relationships ----------------------------------------------------

    def test_relationships_follow_once_every_endpoint_has_a_successor(self):
        decisions = self.carried()
        self.assertFalse(
            Relationship.objects.filter(document=self.v2).exists(),
            "an edge to a STALE endpoint must wait",
        )

        corrected = Review.carry_forward(
            self.user,
            self.notify.pk,
            self.v2.pk,
            placement={"json": {"start": 28, "end": 49}},
        )

        copy = Relationship.objects.get(document=self.v2)
        self.assertEqual(
            list(copy.source_annotations.values_list("pk", flat=True)),
            [decisions["Pay promptly."].successor_id],
        )
        self.assertEqual(
            list(copy.target_annotations.values_list("pk", flat=True)),
            [corrected.successor_id],
        )
        self.assertEqual(list(self.edge.source_annotations.all()), [self.pay])

        Review.drop(self.user, self.pay.pk, self.v2.pk)
        self.assertFalse(
            Relationship.objects.filter(document=self.v2).exists(),
            "dropping an endpoint removes the edge it leaves empty",
        )

    # -- human review -----------------------------------------------------

    def test_each_review_outcome_is_audited_and_final(self):
        pay_successor = self.carried()["Pay promptly."].successor_id

        approved = Review.carry_forward(self.user, self.pay.pk, self.v2.pk)
        corrected = Review.carry_forward(
            self.user,
            self.notify.pk,
            self.v2.pk,
            placement={"json": {"start": 28, "end": 49}},
        )
        dropped = Review.drop(self.user, self.removed.pk, self.v2.pk)

        self.assertEqual(
            [d.decision for d in (approved, corrected, dropped)],
            ["REAPPROVED", "CORRECTED", "DROPPED"],
        )
        self.assertEqual(
            approved.successor_id, pay_successor, "approval confirms, not copies"
        )
        self.assertEqual(corrected.successor.raw_text, "Notify the new owner.")
        self.assertIsNone(dropped.successor)
        self.assertTrue(
            all(
                d.reviewer == self.user and d.reviewed_at
                for d in (approved, corrected, dropped)
            )
        )
        self.assertEqual(self.pending(), 0)
        with self.assertRaisesMessage(ValidationError, "not awaiting review"):
            Review.carry_forward(self.user, self.pay.pk, self.v2.pk)

    def test_approving_a_stale_row_requires_a_placement(self):
        self.carried()
        with self.assertRaisesMessage(ValidationError, "No unique exact match"):
            Review.carry_forward(self.user, self.notify.pk, self.v2.pk)

    def test_changing_the_label_is_a_correction_even_when_the_text_matches(self):
        self.carried()
        deadline = self.label_named("Deadline")
        decision = Review.carry_forward(
            self.user, self.pay.pk, self.v2.pk, label_id=deadline.pk
        )
        self.assertEqual(decision.decision, "CORRECTED")
        self.assertEqual(decision.successor.annotation_label_id, deadline.pk)

    def test_state_distinguishes_machine_carried_from_human_confirmed(self):
        pay_successor = self.carried()["Pay promptly."].successor
        fresh = self.annotate("Introduction.", 0, document=self.v2)

        self.assertEqual(Review.state_for_annotation(self.user, self.pay), "AUTO")
        self.assertEqual(Review.state_for_annotation(self.user, pay_successor), "AUTO")
        self.assertIsNone(Review.state_for_annotation(self.user, fresh))

        Review.carry_forward(self.user, self.pay.pk, self.v2.pk)
        self.assertEqual(
            Review.state_for_annotation(self.user, pay_successor), "REAPPROVED"
        )

    def test_unreviewed_rows_follow_to_the_next_version_instead_of_stranding(self):
        pay_successor = self.carried()["Pay promptly."].successor
        v3 = self.upload("Pay promptly. Notify the owner. Appendix.")

        Review.carry_version(v3)

        notify = AnnotationVersionDecision.objects.get(annotation=self.notify)
        self.assertEqual(notify.target_document_id, v3.pk)
        self.assertEqual(notify.decision, "AUTO", "retried against the new text")
        chained = AnnotationVersionDecision.objects.get(annotation=pay_successor)
        self.assertEqual(
            (chained.target_document_id, chained.decision), (v3.pk, "AUTO")
        )
        self.assertEqual(
            self.pending(document=self.v2),
            0,
            "a superseded version has nothing to act on",
        )
        with self.assertRaisesMessage(ValidationError, "not awaiting review"):
            Review.carry_forward(self.user, self.pay.pk, self.v2.pk)
        # The edge's ends were carried on different hops; it still lands on v3.
        copy = Relationship.objects.get(document=v3)
        self.assertEqual(
            (
                list(copy.source_annotations.values_list("pk", flat=True)),
                list(copy.target_annotations.values_list("pk", flat=True)),
            ),
            ([chained.successor_id], [notify.successor_id]),
        )

    def test_versions_that_finish_parsing_out_of_order_still_carry_everything(self):
        v3 = self.upload("Pay promptly. Notify the owner. Appendix.")
        Review.carry_version(v3)  # v3 parses first: v2 has nothing carried yet
        self.assertEqual(self.pending(document=v3), 0)

        Review.carry_version(self.v2)  # v2 finishes late and re-runs its child

        self.assertEqual(self.pending(document=v3), 3)
        self.assertEqual(
            Annotation.objects.filter(document=v3).count(),
            2,
            "Pay and Notify reach v3; the removed clause waits as STALE",
        )
        self.assertTrue(Relationship.objects.filter(document=v3).exists())

    def test_pdf_carry_and_placement_use_the_new_versions_real_tokens(self):
        tokens = [
            {"x": 10, "y": 10, "width": 20, "height": 10, "text": "Pay"},
            {"x": 35, "y": 10, "width": 50, "height": 10, "text": "promptly."},
            {"x": 10, "y": 30, "width": 60, "height": 10, "text": "Revised."},
        ]
        self.v2.file_type = "application/pdf"
        self.v2.pawls_parse_file.save(
            "review-pawls.json",
            ContentFile(
                json.dumps(
                    [
                        {
                            "page": {"index": 0, "width": 600, "height": 800},
                            "tokens": tokens,
                        }
                    ]
                ).encode()
            ),
        )

        auto = self.carried()["Pay promptly."]
        self.assertEqual(
            list(iter_page_annotations(auto.successor.json))[0].token_indices, [0, 1]
        )

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
                    }
                }
            },
        )
        self.assertEqual(corrected.successor.raw_text, "Revised.")
        self.assertEqual(
            list(iter_page_annotations(corrected.successor.json))[0].bounds,
            {"left": 10, "top": 30, "right": 70, "bottom": 40},
        )

    # -- guards -----------------------------------------------------------

    def test_review_requires_update_on_both_document_and_corpus(self):
        self.carried()
        reviewer = get_user_model().objects.create_user(username="reader")
        for obj in (self.v1, self.v2, self.corpus):
            set_permissions_for_obj_to_user(reviewer, obj, [PermissionTypes.READ])
        self.assertEqual(self.pending(reviewer), 3, "readers can see what needs review")

        for grant in (None, self.v2):
            if grant:
                set_permissions_for_obj_to_user(
                    reviewer, grant, [PermissionTypes.READ, PermissionTypes.UPDATE]
                )
            with self.assertRaises(PermissionDenied):
                Review.drop(reviewer, self.pay.pk, self.v2.pk)

        set_permissions_for_obj_to_user(
            reviewer, self.corpus, [PermissionTypes.READ, PermissionTypes.UPDATE]
        )
        self.assertEqual(
            Review.drop(reviewer, self.pay.pk, self.v2.pk).reviewer, reviewer
        )

    def test_unrelated_targets_invalid_placements_and_foreign_labels_are_rejected(self):
        self.carried()
        unrelated = self.upload("Pay promptly.", path="/another.txt")
        foreign_label = Corpus.objects.create(
            title="Elsewhere", creator=self.user
        ).ensure_label_and_labelset(
            label_text="Private", label_type=SPAN_LABEL, creator_id=self.user.pk
        )
        attempts = {
            "unrelated document": dict(target=unrelated.pk),
            "negative offset": dict(placement={"json": {"start": -1, "end": 5}}),
            "past the end": dict(placement={"json": {"start": 0, "end": 999}}),
            "foreign label": dict(label_id=foreign_label.pk),
        }
        for name, attempt in attempts.items():
            with self.subTest(name), self.assertRaises(ValidationError):
                Review.carry_forward(
                    self.user,
                    self.pay.pk,
                    attempt.pop("target", self.v2.pk),
                    **attempt,
                )
        self.assertEqual(
            AnnotationVersionDecision.objects.get(annotation=self.pay).decision, "AUTO"
        )

    # -- GraphQL ----------------------------------------------------------

    def test_graphql_review_round_trip_keeps_historical_evidence_intact(self):
        self.carried()
        document, corpus = (
            to_global_id("DocumentType", self.v2.pk),
            to_global_id("CorpusType", self.corpus.pk),
        )
        review = self.graphql(
            """query($document: ID!, $corpus: ID!) {
              document(id: $document) { annotationsNeedingReview(corpusId: $corpus) }
              annotationVersionReview(documentId: $document, corpusId: $corpus) {
                state annotation { rawText } successor { versionState }
              }
            }""",
            document=document,
            corpus=corpus,
        )
        self.assertEqual(review["document"]["annotationsNeedingReview"], 3)
        rows = {
            r["annotation"]["rawText"]: r for r in review["annotationVersionReview"]
        }
        self.assertEqual(rows["Pay promptly."]["state"], "AUTO")
        self.assertEqual(rows["Pay promptly."]["successor"]["versionState"], "AUTO")
        self.assertIsNone(rows["Notify the owner."]["successor"])

        approved = self.graphql(
            """mutation($annotation: ID!, $target: ID!) {
              carryForwardAnnotation(annotationId: $annotation, targetDocumentId: $target) {
                state successor { versionState } reviewedBy { slug } reviewedAt
              }
            }""",
            annotation=to_global_id("AnnotationType", self.pay.pk),
            target=document,
        )["carryForwardAnnotation"]
        self.assertEqual(approved["state"], "REAPPROVED")
        self.assertEqual(approved["successor"]["versionState"], "REAPPROVED")
        self.assertEqual(approved["reviewedBy"]["slug"], self.user.slug)
        self.assertIsNotNone(approved["reviewedAt"])

        history = self.graphql(
            """query($document: ID!, $corpus: ID!) {
              document(id: $document) {
                allAnnotations(corpusId: $corpus, analysisId: "__none__") { rawText versionState }
                allRelationships(corpusId: $corpus, analysisId: "__none__") {
                  sourceAnnotations { edges { node { id } } }
                }
              }
            }""",
            document=to_global_id("DocumentType", self.v1.pk),
            corpus=corpus,
        )["document"]
        self.assertEqual(
            {a["rawText"]: a["versionState"] for a in history["allAnnotations"]},
            {
                "Pay promptly.": "REAPPROVED",
                "Notify the owner.": "STALE",
                "Removed clause.": "STALE",
            },
        )
        self.assertEqual(
            history["allRelationships"][0]["sourceAnnotations"]["edges"][0]["node"][
                "id"
            ],
            to_global_id("AnnotationType", self.pay.pk),
        )

    def test_a_corpus_the_document_does_not_belong_to_needs_no_review(self):
        """The count is non-null; a denial would null the whole document."""
        unrelated = Corpus.objects.create(title="Elsewhere", creator=self.user)
        data = self.graphql(
            """query($document: ID!, $corpus: ID!) {
              document(id: $document) { id annotationsNeedingReview(corpusId: $corpus) }
            }""",
            document=to_global_id("DocumentType", self.v2.pk),
            corpus=to_global_id("CorpusType", unrelated.pk),
        )
        self.assertEqual(data["document"]["annotationsNeedingReview"], 0)
