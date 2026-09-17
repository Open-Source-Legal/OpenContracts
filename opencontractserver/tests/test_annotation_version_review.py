"""Human-annotation review across a document version-up (change 5 of
``docs/architecture/reference-web-versioning.md``).

Annotations are never moved. After a version-up every human annotation on the
previous version is STALE relative to the new one until a reviewer re-approves
it, corrects it or drops it. The service proposes a placement by exact text
match; the reviewer decides.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase

from config.graphql.core.relay import to_global_id
from config.graphql.schema import schema
from config.graphql.testing import Client
from opencontractserver.annotations.models import (
    SPAN_LABEL,
    Annotation,
    AnnotationLabel,
    AnnotationVersionDecision,
)
from opencontractserver.annotations.services import AnnotationVersionReviewService
from opencontractserver.constants.annotations import (
    ANNOTATION_VERSION_DECISION_CORRECTED,
    ANNOTATION_VERSION_DECISION_DROPPED,
    ANNOTATION_VERSION_DECISION_REAPPROVED,
    ANNOTATION_VERSION_STATE_STALE,
)
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.documents.versioning import import_document
from opencontractserver.utils.span_projection import span_annotation_payload

User = get_user_model()

V1_TEXT = "Alpha clause. Beta clause. Gamma clause."
V2_TEXT = "Alfa clause. Preamble. Beta clause (amended). Gamma clause."
PATH = "/statute.txt"


class _ReviewFixture(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="reviewer", password="p")
        self.corpus = Corpus.objects.create(title="Statutes", creator=self.user)
        self.label = AnnotationLabel.objects.create(
            text="Clause", creator=self.user, label_type=SPAN_LABEL
        )
        self.v1, _, _ = import_document(
            corpus=self.corpus,
            path=PATH,
            content=V1_TEXT.encode("utf-8"),
            user=self.user,
            file_type="text/plain",
            title="Statute",
        )
        self.alpha = self._span("Alpha clause")
        self.beta = self._span("Beta clause")
        self.gamma = self._span("Gamma clause")
        # Machine-made rows are never review items.
        Annotation.objects.create(
            raw_text="Alpha",
            page=0,
            json={"start": 0, "end": 5, "text": "Alpha"},
            annotation_label=self.label,
            document=self.v1,
            corpus=self.corpus,
            creator=self.user,
            annotation_type=SPAN_LABEL,
            structural=True,
        )

    def _span(self, text: str, document: Document | None = None) -> Annotation:
        document = document or self.v1
        source = V1_TEXT if document == self.v1 else V2_TEXT
        start = source.index(text)
        payload, page = span_annotation_payload(start, start + len(text), text)
        return Annotation.objects.create(
            raw_text=text,
            page=page,
            json=payload,
            annotation_label=self.label,
            document=document,
            corpus=self.corpus,
            creator=self.user,
            annotation_type=SPAN_LABEL,
            structural=False,
        )

    def _version_up(self, text: str = V2_TEXT) -> Document:
        doc, status, _ = import_document(
            corpus=self.corpus,
            path=PATH,
            content=text.encode("utf-8"),
            user=self.user,
            file_type="text/plain",
        )
        self.assertEqual(status, "updated")
        return doc

    def _ctx(self, user=None):
        return type("Request", (), {"user": user or self.user})()


class ReviewServiceTests(_ReviewFixture):
    def test_no_previous_version_means_nothing_to_review(self):
        self.assertEqual(AnnotationVersionReviewService.entries(self.user, self.v1), [])
        self.assertEqual(AnnotationVersionReviewService.stale_count(self.v1), 0)

    def test_every_human_annotation_starts_stale_with_exact_text_proposals(self):
        v2 = self._version_up()
        entries = AnnotationVersionReviewService.entries(self.user, v2, self.corpus.id)
        by_text = {e.annotation.raw_text: e for e in entries}
        self.assertEqual(set(by_text), {"Alpha clause", "Beta clause", "Gamma clause"})
        self.assertTrue(all(e.state == ANNOTATION_VERSION_STATE_STALE for e in entries))
        # Structural row excluded.
        self.assertFalse(any(e.annotation.structural for e in entries))

        beta = by_text["Beta clause"].proposal
        self.assertIsNotNone(beta)
        self.assertEqual(beta.start, V2_TEXT.index("Beta clause"))
        self.assertEqual(beta.annotation_type, SPAN_LABEL)
        self.assertEqual(
            beta.json,
            {"start": beta.start, "end": beta.end, "text": "Beta clause"},
        )
        self.assertIsNotNone(by_text["Gamma clause"].proposal)
        # Text that no longer exists gets no proposal: manual placement.
        self.assertIsNone(by_text["Alpha clause"].proposal)
        self.assertEqual(
            AnnotationVersionReviewService.stale_count(v2, self.corpus.id), 3
        )

    def test_proposal_prefers_occurrence_nearest_the_old_position(self):
        text = "Beta clause. Filler. Beta clause. Tail."
        self.beta.json = {"start": 21, "end": 32, "text": "Beta clause"}
        self.beta.save(update_fields=["json"])
        v2 = self._version_up(text)
        entry = next(
            e
            for e in AnnotationVersionReviewService.entries(self.user, v2)
            if e.annotation.id == self.beta.id
        )
        self.assertEqual(entry.proposal.start, 21)

    def test_carry_forward_with_unchanged_text_is_reapproved(self):
        v2 = self._version_up()
        entry = next(
            e
            for e in AnnotationVersionReviewService.entries(self.user, v2)
            if e.annotation.id == self.beta.id
        )
        decision, error = AnnotationVersionReviewService.carry_forward(
            self.user,
            self.beta,
            v2,
            json=entry.proposal.json,
            page=entry.proposal.page,
            annotation_type=entry.proposal.annotation_type,
            raw_text=entry.proposal.raw_text,
        )
        self.assertEqual(error, "")
        self.assertEqual(decision.decision, ANNOTATION_VERSION_DECISION_REAPPROVED)
        successor = decision.successor
        self.assertEqual(successor.document_id, v2.id)
        self.assertEqual(successor.raw_text, "Beta clause")
        self.assertEqual(successor.annotation_label_id, self.label.id)
        self.assertEqual(successor.corpus_id, self.corpus.id)
        self.assertFalse(successor.structural)
        # The original is untouched (history).
        self.beta.refresh_from_db()
        self.assertEqual(self.beta.document_id, self.v1.id)
        self.assertEqual(
            AnnotationVersionReviewService.state_for_annotation(self.beta),
            ANNOTATION_VERSION_DECISION_REAPPROVED,
        )
        self.assertEqual(AnnotationVersionReviewService.stale_count(v2), 2)

    def test_carry_forward_with_edited_text_is_corrected(self):
        v2 = self._version_up()
        new_text = "Beta clause (amended)"
        start = V2_TEXT.index(new_text)
        payload, page = span_annotation_payload(start, start + len(new_text), new_text)
        decision, error = AnnotationVersionReviewService.carry_forward(
            self.user,
            self.beta,
            v2,
            json=payload,
            page=page,
            annotation_type=SPAN_LABEL,
            raw_text=new_text,
        )
        self.assertEqual(error, "")
        self.assertEqual(decision.decision, ANNOTATION_VERSION_DECISION_CORRECTED)
        self.assertEqual(decision.successor.raw_text, new_text)

    def test_carry_forward_with_different_label_is_corrected(self):
        v2 = self._version_up()
        other = AnnotationLabel.objects.create(
            text="Definition", creator=self.user, label_type=SPAN_LABEL
        )
        start = V2_TEXT.index("Gamma clause")
        payload, page = span_annotation_payload(start, start + 12, "Gamma clause")
        decision, error = AnnotationVersionReviewService.carry_forward(
            self.user,
            self.gamma,
            v2,
            json=payload,
            page=page,
            annotation_type=SPAN_LABEL,
            raw_text="Gamma clause",
            annotation_label=other,
        )
        self.assertEqual(error, "")
        self.assertEqual(decision.decision, ANNOTATION_VERSION_DECISION_CORRECTED)
        self.assertEqual(decision.successor.annotation_label_id, other.id)

    def test_drop_records_decision_without_successor(self):
        v2 = self._version_up()
        decision, error = AnnotationVersionReviewService.drop(self.user, self.alpha, v2)
        self.assertEqual(error, "")
        self.assertEqual(decision.decision, ANNOTATION_VERSION_DECISION_DROPPED)
        self.assertIsNone(decision.successor)
        self.assertEqual(
            AnnotationVersionReviewService.state_for_annotation(self.alpha),
            ANNOTATION_VERSION_DECISION_DROPPED,
        )
        self.assertFalse(Annotation.objects.filter(document=v2).exists())

    def test_second_decision_for_same_pair_is_rejected(self):
        v2 = self._version_up()
        _, error = AnnotationVersionReviewService.drop(self.user, self.alpha, v2)
        self.assertEqual(error, "")
        _, error = AnnotationVersionReviewService.drop(self.user, self.alpha, v2)
        self.assertIn("already has a decision", error)
        self.assertEqual(
            AnnotationVersionDecision.objects.filter(annotation=self.alpha).count(), 1
        )

    def test_only_the_direct_successor_hop_is_reviewable(self):
        v2 = self._version_up()
        v3 = self._version_up(V2_TEXT + " More.")
        # v1's annotation reviewed against v3 (skipping v2) is refused.
        _, error = AnnotationVersionReviewService.drop(self.user, self.alpha, v3)
        self.assertIn("direct successor", error)
        # And against itself.
        _, error = AnnotationVersionReviewService.drop(self.user, self.alpha, self.v1)
        self.assertIn("direct successor", error)
        # v3 reviews v2's human annotations (successors included), not v1's.
        AnnotationVersionReviewService.carry_forward(
            self.user,
            self.beta,
            v2,
            json={"start": 0, "end": 11, "text": "Beta clause"},
            page=0,
            annotation_type=SPAN_LABEL,
            raw_text="Beta clause",
        )
        v3_entries = AnnotationVersionReviewService.entries(self.user, v3)
        self.assertEqual({e.annotation.document_id for e in v3_entries}, {v2.id})
        self.assertEqual(len(v3_entries), 1)

    def test_reviewer_needs_update_on_the_target_document(self):
        v2 = self._version_up()
        reader = User.objects.create_user(username="reader", password="p")
        for d in (self.v1, v2):
            d.is_public = True
            d.save(update_fields=["is_public"])
        self.corpus.is_public = True
        self.corpus.save(update_fields=["is_public"])
        _, error = AnnotationVersionReviewService.drop(reader, self.alpha, v2)
        self.assertTrue(error)
        self.assertFalse(AnnotationVersionDecision.objects.exists())

    def test_machine_annotation_has_no_version_state(self):
        self._version_up()
        structural = Annotation.objects.get(document=self.v1, structural=True)
        self.assertIsNone(
            AnnotationVersionReviewService.state_for_annotation(structural)
        )

    def test_annotation_on_latest_version_has_no_version_state(self):
        self.assertIsNone(
            AnnotationVersionReviewService.state_for_annotation(self.beta)
        )


class ReviewGraphQLTests(_ReviewFixture):
    def test_query_mutations_and_badges(self):
        v2 = self._version_up()
        client = Client(schema)
        gid = lambda t, pk: to_global_id(t, pk)  # noqa: E731

        review_q = """
            query($docId: ID!, $corpusId: ID) {
              annotationVersionReview(documentId: $docId, corpusId: $corpusId) {
                state
                annotation { id rawText versionState }
                successor { id }
                proposedJson proposedPage proposedAnnotationType proposedRawText
              }
              document(id: $docId) { staleAnnotationCount(corpusId: $corpusId) }
            }
        """
        variables = {
            "docId": gid("DocumentType", v2.id),
            "corpusId": gid("CorpusType", self.corpus.id),
        }
        out = client.execute(review_q, variables=variables, context_value=self._ctx())
        self.assertNotIn("errors", out, out)
        entries = out["data"]["annotationVersionReview"]
        self.assertEqual(len(entries), 3)
        self.assertTrue(all(e["state"] == "STALE" for e in entries))
        self.assertTrue(
            all(e["annotation"]["versionState"] == "STALE" for e in entries)
        )
        self.assertEqual(out["data"]["document"]["staleAnnotationCount"], 3)
        beta = next(e for e in entries if e["annotation"]["rawText"] == "Beta clause")
        self.assertEqual(beta["proposedAnnotationType"], "SPAN_LABEL")
        self.assertEqual(beta["proposedRawText"], "Beta clause")

        carry = client.execute(
            """
            mutation($a: ID!, $d: ID!, $json: GenericScalar!, $page: Int!, $t: String!, $txt: String!) {
              carryForwardAnnotation(
                annotationId: $a, targetDocumentId: $d, json: $json, page: $page,
                annotationType: $t, rawText: $txt
              ) { ok message decision successor { id rawText } }
            }
            """,
            variables={
                "a": beta["annotation"]["id"],
                "d": variables["docId"],
                "json": beta["proposedJson"],
                "page": beta["proposedPage"],
                "t": beta["proposedAnnotationType"],
                "txt": beta["proposedRawText"],
            },
            context_value=self._ctx(),
        )
        self.assertNotIn("errors", carry, carry)
        payload = carry["data"]["carryForwardAnnotation"]
        self.assertTrue(payload["ok"], payload)
        self.assertEqual(payload["decision"], "REAPPROVED")
        self.assertEqual(payload["successor"]["rawText"], "Beta clause")

        alpha = next(e for e in entries if e["annotation"]["rawText"] == "Alpha clause")
        drop = client.execute(
            """
            mutation($a: ID!, $d: ID!) {
              dropStaleAnnotation(annotationId: $a, targetDocumentId: $d) { ok message }
            }
            """,
            variables={"a": alpha["annotation"]["id"], "d": variables["docId"]},
            context_value=self._ctx(),
        )
        self.assertNotIn("errors", drop, drop)
        self.assertTrue(drop["data"]["dropStaleAnnotation"]["ok"])

        out = client.execute(review_q, variables=variables, context_value=self._ctx())
        states = {
            e["annotation"]["rawText"]: (e["state"], e["annotation"]["versionState"])
            for e in out["data"]["annotationVersionReview"]
        }
        self.assertEqual(states["Beta clause"], ("REAPPROVED", "REAPPROVED"))
        self.assertEqual(states["Alpha clause"], ("DROPPED", "DROPPED"))
        self.assertEqual(states["Gamma clause"], ("STALE", "STALE"))
        self.assertEqual(out["data"]["document"]["staleAnnotationCount"], 1)

    def test_invisible_document_yields_empty_review(self):
        v2 = self._version_up()
        stranger = User.objects.create_user(username="stranger", password="p")
        out = Client(schema).execute(
            """
            query($docId: ID!) { annotationVersionReview(documentId: $docId) { state } }
            """,
            variables={"docId": to_global_id("DocumentType", v2.id)},
            context_value=self._ctx(stranger),
        )
        self.assertNotIn("errors", out, out)
        self.assertEqual(out["data"]["annotationVersionReview"], [])

    def test_mutation_requires_update_on_target(self):
        v2 = self._version_up()
        reader = User.objects.create_user(username="reader2", password="p")
        for d in (self.v1, v2):
            d.is_public = True
            d.save(update_fields=["is_public"])
        self.corpus.is_public = True
        self.corpus.save(update_fields=["is_public"])
        self.alpha.is_public = True
        self.alpha.save(update_fields=["is_public"])
        out = Client(schema).execute(
            """
            mutation($a: ID!, $d: ID!) {
              dropStaleAnnotation(annotationId: $a, targetDocumentId: $d) { ok message }
            }
            """,
            variables={
                "a": to_global_id("AnnotationType", self.alpha.id),
                "d": to_global_id("DocumentType", v2.id),
            },
            context_value=self._ctx(reader),
        )
        self.assertNotIn("errors", out, out)
        self.assertFalse(out["data"]["dropStaleAnnotation"]["ok"])
        self.assertFalse(AnnotationVersionDecision.objects.exists())
