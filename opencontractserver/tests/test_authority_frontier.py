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

    def test_mark_with_candidate_record_appends_to_audit_trail(self):
        """mark() with candidate_record= sets state AND appends the record."""
        row = self._make_row(
            "usc-15:78j-audit", provider="TestProv", state="in_progress"
        )
        record = {
            "provider": "TestProv",
            "license": "proprietary",
            "source_domain": "evil.example.com",
            "verify": "skipped",
            "outcome": "blocked_license",
            "error": "license not public-domain",
            "attempted_at": "2026-06-15T00:00:00Z",
        }

        AuthorityFrontierService.mark(
            row,
            "blocked_license",
            error="license not public-domain",
            candidate_record=record,
        )

        row.refresh_from_db()
        self.assertEqual(row.discovery_state, "blocked_license")
        self.assertEqual(row.last_error, "license not public-domain")
        self.assertEqual(len(row.candidate_sources), 1)
        self.assertEqual(row.candidate_sources[0]["outcome"], "blocked_license")

    def test_mark_candidate_record_is_append_only(self):
        """A second mark() with a candidate_record appends, not overwrites."""
        row = self._make_row(
            "usc-15:78j-append", provider="TestProv", state="in_progress"
        )
        first_record = {
            "outcome": "blocked_license",
            "attempted_at": "2026-06-15T00:00:00Z",
        }
        second_record = {"outcome": "ingested", "attempted_at": "2026-06-15T01:00:00Z"}

        AuthorityFrontierService.mark(
            row, "blocked_license", candidate_record=first_record
        )
        row.refresh_from_db()
        self.assertEqual(len(row.candidate_sources), 1)

        AuthorityFrontierService.mark(row, "ingested", candidate_record=second_record)
        row.refresh_from_db()
        self.assertEqual(len(row.candidate_sources), 2)
        self.assertEqual(row.candidate_sources[0]["outcome"], "blocked_license")
        self.assertEqual(row.candidate_sources[1]["outcome"], "ingested")

    def test_mark_without_candidate_record_leaves_sources_unchanged(self):
        """mark() without candidate_record= must not alter candidate_sources."""
        row = self._make_row(
            "usc-15:78j-norecord", provider="TestProv", state="in_progress"
        )
        # Pre-populate candidate_sources
        row.candidate_sources = [{"outcome": "prior"}]
        row.save(update_fields=["candidate_sources"])

        AuthorityFrontierService.mark(row, "failed", error="network error")

        row.refresh_from_db()
        # Only the pre-existing record should remain
        self.assertEqual(len(row.candidate_sources), 1)
        self.assertEqual(row.candidate_sources[0]["outcome"], "prior")


class AuthorityFrontierGateStateTests(TestCase):
    """Tests that the Phase-4 gate discovery_state values are accepted."""

    def _make_row(self, key, state):
        return AuthorityFrontier.objects.create(
            canonical_key=key,
            authority=key.split(":")[0],
            discovery_state=state,
        )

    def test_pending_approval_state_accepted(self):
        row = self._make_row("usc-15:78j-pending", "pending_approval")
        row.refresh_from_db()
        self.assertEqual(row.discovery_state, "pending_approval")

    def test_blocked_license_state_accepted(self):
        row = self._make_row("usc-15:78j-blocked", "blocked_license")
        row.refresh_from_db()
        self.assertEqual(row.discovery_state, "blocked_license")

    def test_blocked_domain_state_accepted(self):
        row = self._make_row("usc-15:78j-blocked-domain", "blocked_domain")
        row.refresh_from_db()
        self.assertEqual(row.discovery_state, "blocked_domain")

    def test_unlocated_state_accepted(self):
        row = self._make_row("usc-15:78j-unlocated", "unlocated")
        row.refresh_from_db()
        self.assertEqual(row.discovery_state, "unlocated")

    def test_deferred_cap_state_accepted(self):
        """Phase-5: deferred_cap is a valid discovery_state value."""
        row = self._make_row("usc-15:78j-deferred", "deferred_cap")
        row.refresh_from_db()
        self.assertEqual(row.discovery_state, "deferred_cap")


class DequeueQueuedTests(TestCase):
    """Tests for AuthorityFrontierService.dequeue_queued (Phase-5 provider-agnostic dequeue)."""

    def _make_row(self, key, state="queued", mention_count=5, depth=0):
        return AuthorityFrontier.objects.create(
            canonical_key=key,
            authority=key.split(":")[0],
            discovery_state=state,
            mention_count=mention_count,
            depth=depth,
        )

    def test_returns_only_queued_rows(self):
        """Non-queued rows must never be returned."""
        self._make_row("usc-15:1a", state="queued", mention_count=10)
        self._make_row("usc-15:1b", state="ingested", mention_count=20)
        self._make_row("usc-15:1c", state="failed", mention_count=30)
        rows = AuthorityFrontierService.dequeue_queued(limit=10)
        keys = [r.canonical_key for r in rows]
        self.assertIn("usc-15:1a", keys)
        self.assertNotIn("usc-15:1b", keys)
        self.assertNotIn("usc-15:1c", keys)

    def test_ordered_by_mention_count_desc(self):
        """Highest-demand row must come first."""
        self._make_row("usc-15:2a", mention_count=3)
        self._make_row("usc-15:2b", mention_count=20)
        self._make_row("usc-15:2c", mention_count=10)
        rows = AuthorityFrontierService.dequeue_queued(limit=10)
        counts = [r.mention_count for r in rows]
        self.assertEqual(counts, sorted(counts, reverse=True))

    def test_max_depth_filter(self):
        """Rows with depth > max_depth must be excluded."""
        self._make_row("usc-15:3a", depth=0, mention_count=10)
        self._make_row("usc-15:3b", depth=2, mention_count=8)
        self._make_row("usc-15:3c", depth=3, mention_count=6)  # excluded by max_depth=2
        rows = AuthorityFrontierService.dequeue_queued(limit=10, max_depth=2)
        keys = [r.canonical_key for r in rows]
        self.assertIn("usc-15:3a", keys)
        self.assertIn("usc-15:3b", keys)
        self.assertNotIn("usc-15:3c", keys)

    def test_min_demand_filter(self):
        """Rows with mention_count below min_demand must be excluded."""
        self._make_row("usc-15:4a", mention_count=5)
        self._make_row("usc-15:4b", mention_count=1)  # excluded by min_demand=2
        rows = AuthorityFrontierService.dequeue_queued(limit=10, min_demand=2)
        keys = [r.canonical_key for r in rows]
        self.assertIn("usc-15:4a", keys)
        self.assertNotIn("usc-15:4b", keys)

    def test_limit_respected(self):
        """No more than ``limit`` rows should be returned."""
        for i in range(5):
            self._make_row(f"usc-15:5{i}", mention_count=10 - i)
        rows = AuthorityFrontierService.dequeue_queued(limit=3)
        self.assertEqual(len(rows), 3)

    def test_no_provider_filter(self):
        """dequeue_queued must return rows even when provider is None (seed rows)."""
        row = self._make_row("usc-15:6a", mention_count=5)
        self.assertIsNone(row.provider)
        rows = AuthorityFrontierService.dequeue_queued(limit=10)
        keys = [r.canonical_key for r in rows]
        self.assertIn("usc-15:6a", keys)

    def test_combined_max_depth_and_min_demand(self):
        """Both filters apply simultaneously."""
        self._make_row("usc-15:7a", depth=0, mention_count=5)  # passes both
        self._make_row("usc-15:7b", depth=3, mention_count=5)  # fails max_depth=2
        self._make_row("usc-15:7c", depth=0, mention_count=1)  # fails min_demand=2
        rows = AuthorityFrontierService.dequeue_queued(
            limit=10, max_depth=2, min_demand=2
        )
        keys = [r.canonical_key for r in rows]
        self.assertIn("usc-15:7a", keys)
        self.assertNotIn("usc-15:7b", keys)
        self.assertNotIn("usc-15:7c", keys)

    def test_dequeue_atomically_claims_rows_in_progress(self):
        """dequeue_queued is an atomic CLAIM, not a plain read (issue #2027).

        Each returned row must be flipped to ``in_progress`` — both in the
        returned object and in the DB — so a second concurrent dequeue cannot
        re-return it and re-run ``discover_and_bootstrap`` on the same key.
        """
        self._make_row("usc-15:claim-a", mention_count=10)
        self._make_row("usc-15:claim-b", mention_count=5)

        first = AuthorityFrontierService.dequeue_queued(limit=1)
        self.assertEqual(len(first), 1)
        self.assertEqual(first[0].canonical_key, "usc-15:claim-a")
        # Claimed in the returned object AND persisted to the DB.
        self.assertEqual(first[0].discovery_state, "in_progress")
        self.assertEqual(
            AuthorityFrontier.objects.get(
                canonical_key="usc-15:claim-a"
            ).discovery_state,
            "in_progress",
        )
        self.assertIsNotNone(first[0].last_attempt)

        # A second dequeue must skip the already-claimed row and pick the next.
        second = AuthorityFrontierService.dequeue_queued(limit=10)
        keys = {r.canonical_key for r in second}
        self.assertNotIn("usc-15:claim-a", keys)
        self.assertIn("usc-15:claim-b", keys)

    def test_filtered_out_rows_are_not_claimed(self):
        """Rows excluded by min_demand/max_depth must stay ``queued`` (unclaimed).

        The crawl's frontier_drained residual census counts ``queued`` rows, so
        the claim must touch only rows it actually returns.
        """
        self._make_row("usc-15:keep", mention_count=5, depth=0)
        self._make_row("usc-15:low", mention_count=1, depth=0)  # below min_demand
        self._make_row("usc-15:deep", mention_count=5, depth=9)  # beyond max_depth

        claimed = AuthorityFrontierService.dequeue_queued(
            limit=10, max_depth=2, min_demand=2
        )
        self.assertEqual({r.canonical_key for r in claimed}, {"usc-15:keep"})
        # The excluded rows are untouched — still queued for a later, looser pass.
        self.assertEqual(
            AuthorityFrontier.objects.get(canonical_key="usc-15:low").discovery_state,
            "queued",
        )
        self.assertEqual(
            AuthorityFrontier.objects.get(canonical_key="usc-15:deep").discovery_state,
            "queued",
        )


class SeedChildKeysTests(TestCase):
    """Tests for AuthorityFrontierService.seed_child_keys (Phase-5 idempotent seeding)."""

    def _make_parent(self, key="usc-15:78j", depth=0):
        return AuthorityFrontier.objects.create(
            canonical_key=key,
            authority=key.split(":")[0],
            discovery_state="ingested",
            depth=depth,
        )

    def test_creates_child_rows_at_depth_plus_one(self):
        """New rows should be created at parent.depth + 1.

        Parent is exchange-act:10 (no conflict with seeded keys).
        Seeds:
          "usc-15:78j(b)" → root "usc-15:78j"   (new row; (b) subsection stripped)
          "cfr-40:261.4"  → root "cfr-40:261.4"  (new row; ".4" is a WHOLE section,
                                                  NOT a subsection — preserved intact)
        Both are new → child_created=2.
        """
        parent = self._make_parent("exchange-act:10", depth=0)
        result = AuthorityFrontierService.seed_child_keys(
            parent, ["usc-15:78j(b)", "cfr-40:261.4"]
        )
        self.assertEqual(result["child_created"], 2)
        self.assertEqual(result["child_skipped"], 0)

        usc_row = AuthorityFrontier.objects.get(canonical_key="usc-15:78j")
        # cfr-40:261.4 is a whole section (part 261, section .4) — the dotted
        # section number is preserved; only parenthetical subsections roll up.
        cfr_row = AuthorityFrontier.objects.get(canonical_key="cfr-40:261.4")

        # Both should be at depth 1 and in queued state
        self.assertEqual(usc_row.depth, 1)
        self.assertEqual(usc_row.discovery_state, "queued")
        self.assertEqual(usc_row.jurisdiction, C.JURISDICTION_US_FEDERAL)
        self.assertEqual(usc_row.authority_type, C.AUTHORITY_TYPE_STATUTE)

        self.assertEqual(cfr_row.depth, 1)
        self.assertEqual(cfr_row.discovery_state, "queued")
        self.assertEqual(cfr_row.authority, "cfr-40")
        self.assertEqual(cfr_row.jurisdiction, C.JURISDICTION_US_FEDERAL)
        self.assertEqual(cfr_row.authority_type, C.AUTHORITY_TYPE_REGULATION)

    def test_section_root_rollup(self):
        """Subsection keys like usc-15:78j(b) must roll up to usc-15:78j."""
        parent = self._make_parent("dgcl:102", depth=0)
        result = AuthorityFrontierService.seed_child_keys(
            parent, ["usc-15:78j(b)", "usc-15:78j(c)"]
        )
        # Both roll to same root usc-15:78j — only one row created
        self.assertEqual(result["child_created"], 1)
        self.assertEqual(result["child_skipped"], 1)
        self.assertEqual(
            AuthorityFrontier.objects.filter(canonical_key="usc-15:78j").count(), 1
        )

    def test_idempotent_second_call(self):
        """Calling seed_child_keys again with the same keys must skip all.

        "cfr-17:240.10b-5" is a whole section (preserved); "usc-15:77b" stays
        as-is. First call creates 2 rows; second call skips both (idempotent).
        """
        parent = self._make_parent("exchange-act:10", depth=0)
        raw_keys = ["cfr-17:240.10b-5", "usc-15:77b"]
        # Both are whole sections (no parenthetical subsection to strip).
        rolled_roots = ["cfr-17:240.10b-5", "usc-15:77b"]

        first = AuthorityFrontierService.seed_child_keys(parent, raw_keys)
        self.assertEqual(first["child_created"], 2)

        second = AuthorityFrontierService.seed_child_keys(parent, raw_keys)
        self.assertEqual(second["child_created"], 0)
        self.assertEqual(second["child_skipped"], 2)

        # No duplicates in DB — rows keyed by rolled roots
        self.assertEqual(
            AuthorityFrontier.objects.filter(canonical_key__in=rolled_roots).count(),
            2,
        )

    def test_partial_overlap_creates_only_new(self):
        """Overlapping keys are skipped; new keys are created."""
        parent = self._make_parent("irc:1", depth=0)
        first = AuthorityFrontierService.seed_child_keys(parent, ["usc-26:61"])
        self.assertEqual(first["child_created"], 1)

        # Add the same key plus a new one
        second = AuthorityFrontierService.seed_child_keys(
            parent, ["usc-26:61", "usc-26:162"]
        )
        self.assertEqual(second["child_created"], 1)
        self.assertEqual(second["child_skipped"], 1)

    def test_depth_is_parent_depth_plus_one(self):
        """Depth of child rows must always be parent.depth + 1."""
        parent = self._make_parent("dgcl:141", depth=1)
        AuthorityFrontierService.seed_child_keys(parent, ["dgcl:242"])
        child = AuthorityFrontier.objects.get(canonical_key="dgcl:242")
        self.assertEqual(child.depth, 2)

    def test_no_duplicate_canonical_key_rows(self):
        """Multiple calls must never produce duplicate canonical_key rows."""
        parent = self._make_parent("usc-15:78j", depth=0)
        # The parent key itself is "usc-15:78j"; seeding a child that rolls to
        # the same root must detect the pre-existing row.
        AuthorityFrontierService.seed_child_keys(parent, ["cfr-40:261"])
        AuthorityFrontierService.seed_child_keys(parent, ["cfr-40:261"])
        AuthorityFrontierService.seed_child_keys(parent, ["cfr-40:261"])
        self.assertEqual(
            AuthorityFrontier.objects.filter(canonical_key="cfr-40:261").count(), 1
        )

    def test_empty_keys_list_returns_zero_counts(self):
        """Passing an empty list must return created=0, skipped=0."""
        parent = self._make_parent()
        result = AuthorityFrontierService.seed_child_keys(parent, [])
        self.assertEqual(result["child_created"], 0)
        self.assertEqual(result["child_skipped"], 0)

    def test_jurisdiction_and_authority_type_populated(self):
        """Newly created child rows must have correct jurisdiction + authority_type."""
        parent = self._make_parent("exchange-act:10", depth=0)
        AuthorityFrontierService.seed_child_keys(parent, ["usc-15:78b"])
        child = AuthorityFrontier.objects.get(canonical_key="usc-15:78b")
        self.assertEqual(child.jurisdiction, C.JURISDICTION_US_FEDERAL)
        self.assertEqual(child.authority_type, C.AUTHORITY_TYPE_STATUTE)

    def test_discovery_state_is_queued(self):
        """Newly seeded child rows must always start as queued."""
        parent = self._make_parent("exchange-act:10", depth=0)
        AuthorityFrontierService.seed_child_keys(parent, ["dgcl:141"])
        child = AuthorityFrontier.objects.get(canonical_key="dgcl:141")
        self.assertEqual(child.discovery_state, "queued")

    def test_existing_row_at_any_state_is_skipped(self):
        """A row already at 'ingested' must be skipped (never reset to queued)."""
        # Pre-create at ingested state
        AuthorityFrontier.objects.create(
            canonical_key="usc-15:78l",
            authority="usc-15",
            discovery_state="ingested",
            depth=0,
        )
        parent = self._make_parent("exchange-act:12", depth=0)
        result = AuthorityFrontierService.seed_child_keys(parent, ["usc-15:78l"])
        self.assertEqual(result["child_created"], 0)
        self.assertEqual(result["child_skipped"], 1)
        # State must still be ingested, not reset to queued
        row = AuthorityFrontier.objects.get(canonical_key="usc-15:78l")
        self.assertEqual(row.discovery_state, "ingested")
