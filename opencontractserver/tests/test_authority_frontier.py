"""Tests for AuthorityFrontier, AuthorityKeyEquivalence, and AuthorityFrontierService."""

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase

from opencontractserver.annotations.models import (
    SPAN_LABEL,
    Annotation,
    AuthorityFrontier,
    AuthorityKeyEquivalence,
    CorpusReference,
)
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document, DocumentPath
from opencontractserver.enrichment import constants as C
from opencontractserver.enrichment.services import AuthorityFrontierService

User = get_user_model()


class ClassifyPrefixTests(TestCase):
    """Unit tests for the classify_prefix helper in enrichment.constants."""

    def test_usc_title_prefix(self):
        juris, atype = C.classify_prefix("usc-15")
        self.assertEqual(juris, C.JURISDICTION_US_FEDERAL)
        self.assertEqual(atype, C.AUTHORITY_TYPE_STATUTE)

    def test_usc_different_title(self):
        juris, atype = C.classify_prefix("usc-17")
        self.assertEqual(juris, C.JURISDICTION_US_FEDERAL)
        self.assertEqual(atype, C.AUTHORITY_TYPE_STATUTE)

    def test_cfr_title_prefix(self):
        juris, atype = C.classify_prefix("cfr-40")
        self.assertEqual(juris, C.JURISDICTION_US_FEDERAL)
        self.assertEqual(atype, C.AUTHORITY_TYPE_REGULATION)

    def test_fedreg_prefix(self):
        juris, atype = C.classify_prefix("fedreg")
        self.assertEqual(juris, C.JURISDICTION_US_FEDERAL)
        self.assertEqual(atype, C.AUTHORITY_TYPE_ADMIN_RULE)

    def test_static_map_dgcl(self):
        juris, atype = C.classify_prefix("dgcl")
        self.assertEqual(juris, "us-de")
        self.assertEqual(atype, C.AUTHORITY_TYPE_STATUTE)

    def test_unknown_prefix_returns_none(self):
        juris, atype = C.classify_prefix("unknown-xyz")
        self.assertIsNone(juris)
        self.assertIsNone(atype)

    def test_usc_partial_match_rejected(self):
        # "usc" without a dash-number should NOT match the USC regex
        juris, atype = C.classify_prefix("usc")
        self.assertIsNone(juris)
        self.assertIsNone(atype)


class AuthorityFrontierModelTests(TestCase):
    """Model round-trip and constraint tests for AuthorityFrontier."""

    def test_round_trip(self):
        row = AuthorityFrontier.objects.create(
            canonical_key="usc-15:78j",
            authority="usc-15",
            jurisdiction=C.JURISDICTION_US_FEDERAL,
            authority_type=C.AUTHORITY_TYPE_STATUTE,
            mention_count=5,
            distinct_corpus_count=2,
            discovery_state="queued",
        )
        row.refresh_from_db()
        self.assertEqual(row.canonical_key, "usc-15:78j")
        self.assertEqual(row.authority, "usc-15")
        self.assertEqual(row.jurisdiction, C.JURISDICTION_US_FEDERAL)
        self.assertEqual(row.authority_type, C.AUTHORITY_TYPE_STATUTE)
        self.assertEqual(row.mention_count, 5)
        self.assertEqual(row.distinct_corpus_count, 2)
        self.assertEqual(row.discovery_state, "queued")
        self.assertIsNone(row.ingested_document)

    def test_canonical_key_unique(self):
        AuthorityFrontier.objects.create(
            canonical_key="usc-15:78j",
            authority="usc-15",
            discovery_state="queued",
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                AuthorityFrontier.objects.create(
                    canonical_key="usc-15:78j",
                    authority="usc-15",
                    discovery_state="queued",
                )

    def test_check_constraint_queued_with_ingested_document(self):
        """The CheckConstraint frontier_queued_no_ingested_doc must fire."""
        user = User.objects.create_user(username="frontier-check", password="p")
        doc = Document.objects.create(title="Doc", creator=user)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                AuthorityFrontier.objects.create(
                    canonical_key="cfr-40:261.4",
                    authority="cfr-40",
                    discovery_state="queued",
                    ingested_document=doc,
                )

    def test_ingested_state_with_document_allowed(self):
        """discovery_state='ingested' + ingested_document is valid."""
        user = User.objects.create_user(username="frontier-ingested", password="p")
        doc = Document.objects.create(title="Doc", creator=user)
        row = AuthorityFrontier.objects.create(
            canonical_key="cfr-40:261.5",
            authority="cfr-40",
            discovery_state="ingested",
            ingested_document=doc,
        )
        self.assertEqual(row.discovery_state, "ingested")
        self.assertEqual(row.ingested_document_id, doc.pk)


class AuthorityKeyEquivalenceModelTests(TestCase):
    """Model round-trip and constraint tests for AuthorityKeyEquivalence.

    Uses synthetic ``zz-*`` keys that are NOT in the curated equivalence seed
    (migration 0087), so these model-level assertions stay isolated from seeded
    rows.
    """

    def test_round_trip(self):
        equiv = AuthorityKeyEquivalence.objects.create(
            from_key="zz-act:10",
            to_key="zz-usc:78j",
            source="uslm",
            confidence=0.98,
        )
        equiv.refresh_from_db()
        self.assertEqual(equiv.from_key, "zz-act:10")
        self.assertEqual(equiv.to_key, "zz-usc:78j")
        self.assertEqual(equiv.source, "uslm")
        self.assertAlmostEqual(equiv.confidence, 0.98)

    def test_unique_pair_constraint(self):
        AuthorityKeyEquivalence.objects.create(
            from_key="zz-act:10",
            to_key="zz-usc:78j",
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                AuthorityKeyEquivalence.objects.create(
                    from_key="zz-act:10",
                    to_key="zz-usc:78j",
                )

    def test_reverse_pair_allowed(self):
        """The inverse direction is a separate, valid row."""
        AuthorityKeyEquivalence.objects.create(
            from_key="zz-act:10",
            to_key="zz-usc:78j",
        )
        # Reverse pair should not raise
        rev = AuthorityKeyEquivalence.objects.create(
            from_key="zz-usc:78j",
            to_key="zz-act:10",
        )
        self.assertIsNotNone(rev.pk)


def _build_corpus_with_external_ref(username, canonical_key):
    """Helper: corpus + document + annotation + external CorpusReference."""
    user = User.objects.create_user(username=username, password="p")
    corpus = Corpus.objects.create(title="Filing Corpus", creator=user)
    doc = Document.objects.create(title="Filing Doc", creator=user)
    # Link doc to corpus via DocumentPath (is_current=True so visible)
    DocumentPath.objects.create(
        document=doc,
        corpus=corpus,
        path="/filing/doc.pdf",
        version_number=1,
        is_current=True,
        is_deleted=False,
        creator=user,
    )
    label = corpus.ensure_label_and_labelset(
        label_text=C.LABEL_REF_LAW, creator_id=user.id, label_type=SPAN_LABEL
    )
    ann = Annotation.objects.create(
        raw_text=canonical_key,
        page=1,
        json={"start": 0, "end": len(canonical_key)},
        annotation_label=label,
        document=doc,
        corpus=corpus,
        creator=user,
        annotation_type=SPAN_LABEL,
    )
    CorpusReference.objects.create(
        corpus=corpus,
        reference_type=C.REF_LAW,
        source_annotation=ann,
        canonical_key=canonical_key,
        resolution_status=C.STATUS_EXTERNAL,
        jurisdiction=C.JURISDICTION_US_FEDERAL,
        authority_type=C.AUTHORITY_TYPE_STATUTE,
        creator=user,
    )
    return user, corpus, doc


class AuthorityFrontierServiceSeedTests(TestCase):
    """Tests for AuthorityFrontierService.seed_from_wanted_authorities."""

    def test_seed_creates_frontier_row(self):
        user, corpus, _ = _build_corpus_with_external_ref("seed-user-1", "usc-15:78j")
        result = AuthorityFrontierService.seed_from_wanted_authorities(
            user, corpus_id=corpus.id
        )
        self.assertGreaterEqual(result["frontier_created"], 1)

        row = AuthorityFrontier.objects.get(canonical_key="usc-15:78j")
        self.assertEqual(row.authority, "usc-15")
        self.assertEqual(row.jurisdiction, C.JURISDICTION_US_FEDERAL)
        self.assertEqual(row.authority_type, C.AUTHORITY_TYPE_STATUTE)
        self.assertGreaterEqual(row.mention_count, 1)
        self.assertEqual(row.discovery_state, "queued")

    def test_seed_is_idempotent(self):
        user, corpus, _ = _build_corpus_with_external_ref("seed-user-2", "usc-15:78j")
        # First seed
        AuthorityFrontierService.seed_from_wanted_authorities(user, corpus_id=corpus.id)
        # Second seed — should not duplicate, discovery_state should stay queued
        result2 = AuthorityFrontierService.seed_from_wanted_authorities(
            user, corpus_id=corpus.id
        )
        # Only one row should exist
        count = AuthorityFrontier.objects.filter(canonical_key="usc-15:78j").count()
        self.assertEqual(count, 1)
        # Second run marks the row as updated (not created)
        self.assertEqual(result2["frontier_created"], 0)
        self.assertGreaterEqual(result2["frontier_updated"], 1)
        row = AuthorityFrontier.objects.get(canonical_key="usc-15:78j")
        self.assertEqual(row.discovery_state, "queued")

    def test_seed_does_not_overwrite_in_progress_state(self):
        user, corpus, _ = _build_corpus_with_external_ref("seed-user-3", "usc-15:78j")
        AuthorityFrontierService.seed_from_wanted_authorities(user, corpus_id=corpus.id)
        # Simulate in-flight discovery
        row = AuthorityFrontier.objects.get(canonical_key="usc-15:78j")
        row.discovery_state = "in_progress"
        row.save(update_fields=["discovery_state"])

        # Re-seed should NOT overwrite the state (only refreshes counts)
        AuthorityFrontierService.seed_from_wanted_authorities(user, corpus_id=corpus.id)
        row.refresh_from_db()
        self.assertEqual(row.discovery_state, "in_progress")


class AuthorityFrontierServiceDequeueMarkTests(TestCase):
    """Tests for dequeue_for_provider and mark."""

    def _make_row(self, key, provider, state="queued", mention_count=5):
        return AuthorityFrontier.objects.create(
            canonical_key=key,
            authority=key.split(":")[0],
            discovery_state=state,
            provider=provider,
            mention_count=mention_count,
        )

    def test_dequeue_returns_queued_rows_for_provider(self):
        p = "USCodeAuthoritySourceProvider"
        self._make_row("usc-15:78j", provider=p, mention_count=10)
        self._make_row("usc-15:78m", provider=p, mention_count=5)
        self._make_row("usc-17:77j", provider="OtherProvider")
        rows = AuthorityFrontierService.dequeue_for_provider(p, limit=10)
        keys = [r.canonical_key for r in rows]
        self.assertIn("usc-15:78j", keys)
        self.assertIn("usc-15:78m", keys)
        self.assertNotIn("usc-17:77j", keys)

    def test_dequeue_ordered_by_mention_count_desc(self):
        p = "TestProvider"
        self._make_row("usc-15:1", provider=p, mention_count=3)
        self._make_row("usc-15:2", provider=p, mention_count=20)
        self._make_row("usc-15:3", provider=p, mention_count=10)
        rows = AuthorityFrontierService.dequeue_for_provider(p, limit=10)
        counts = [r.mention_count for r in rows]
        self.assertEqual(counts, sorted(counts, reverse=True))

    def test_dequeue_respects_limit(self):
        p = "LimitProvider"
        for i in range(5):
            self._make_row(f"usc-15:{i+100}", provider=p)
        rows = AuthorityFrontierService.dequeue_for_provider(p, limit=3)
        self.assertEqual(len(rows), 3)

    def test_mark_ingested_with_document(self):
        user = User.objects.create_user(username="mark-test-user", password="p")
        doc = Document.objects.create(title="Authority Doc", creator=user)
        row = self._make_row(
            "usc-15:78j-mark", provider="TestProv", state="in_progress"
        )

        AuthorityFrontierService.mark(row, "ingested", document_id=doc.pk)

        row.refresh_from_db()
        self.assertEqual(row.discovery_state, "ingested")
        self.assertIsNotNone(row.last_attempt)
        self.assertEqual(row.ingested_document_id, doc.pk)
        self.assertIsNone(row.last_error)

    def test_mark_failed_with_error(self):
        row = self._make_row(
            "usc-15:78j-fail", provider="TestProv", state="in_progress"
        )
        AuthorityFrontierService.mark(row, "failed", error="Timeout fetching USLM")

        row.refresh_from_db()
        self.assertEqual(row.discovery_state, "failed")
        self.assertEqual(row.last_error, "Timeout fetching USLM")
        self.assertIsNotNone(row.last_attempt)
