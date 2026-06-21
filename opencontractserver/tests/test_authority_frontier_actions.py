"""Tests for the AuthorityFrontier admin row-action verbs (Authority Console
Phase 3): requeue / reset / reroute / approve / delete, plus the ``mark()``
clear-field kwargs they rely on.

The load-bearing correctness checks: a requeue of an already-ingested row must
move it back to ``queued`` while clearing ``ingested_document`` (otherwise the
``frontier_queued_no_ingested_doc`` CheckConstraint rejects the save), and a
``deferred_cap`` row must become ``dequeue_queued``-able again after a requeue
(the silent-backlog fix). All verbs are superuser-gated.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase

from opencontractserver.annotations.models import AuthorityFrontier
from opencontractserver.documents.models import Document
from opencontractserver.enrichment.services import AuthorityFrontierService

User = get_user_model()


class AuthorityFrontierActionTests(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_user(
            username="root", password="p", is_superuser=True, is_staff=True
        )
        self.regular = User.objects.create_user(username="joe", password="p")
        self.doc = Document.objects.create(creator=self.superuser, title="Doc")

    def _ingested_row(self, key="usc-15:78j"):
        return AuthorityFrontier.objects.create(
            canonical_key=key,
            authority="usc-15",
            discovery_state="ingested",
            ingested_document=self.doc,
            last_error="stale error",
            provider="USCodeAuthoritySourceProvider",
        )

    # ---- requeue (the constraint-safe re-queue) ------------------------------
    def test_requeue_clears_document_without_constraint_violation(self):
        row = self._ingested_row()
        res = AuthorityFrontierService.requeue(self.superuser, pk=row.pk)
        assert res.ok, res.error
        row.refresh_from_db()
        assert row.discovery_state == "queued"
        assert row.ingested_document_id is None  # cleared → no constraint breach
        assert row.last_error is None

    def test_requeue_unsticks_deferred_cap_for_dequeue(self):
        row = AuthorityFrontier.objects.create(
            canonical_key="usc-15:1",
            authority="usc-15",
            discovery_state="deferred_cap",
            mention_count=5,
        )
        # A deferred_cap row is invisible to the crawl driver's dequeue.
        assert row not in AuthorityFrontierService.dequeue_queued()
        AuthorityFrontierService.requeue(self.superuser, pk=row.pk)
        row.refresh_from_db()
        assert row.discovery_state == "queued"
        assert row.pk in {r.pk for r in AuthorityFrontierService.dequeue_queued()}

    def test_requeue_rejects_non_admin(self):
        row = self._ingested_row()
        res = AuthorityFrontierService.requeue(self.regular, pk=row.pk)
        assert not res.ok
        row.refresh_from_db()
        assert row.discovery_state == "ingested"

    # ---- reset ---------------------------------------------------------------
    def test_reset_clears_provider_too(self):
        row = self._ingested_row()
        res = AuthorityFrontierService.reset(self.superuser, pk=row.pk)
        assert res.ok, res.error
        row.refresh_from_db()
        assert row.discovery_state == "queued"
        assert row.ingested_document_id is None
        assert row.provider is None
        assert row.last_error is None

    # ---- reroute -------------------------------------------------------------
    def test_reroute_rejects_unknown_provider(self):
        row = self._ingested_row()
        res = AuthorityFrontierService.reroute(
            self.superuser, pk=row.pk, provider="NoSuchProvider"
        )
        assert not res.ok
        assert "Unknown provider" in res.error

    def test_reroute_sets_valid_provider_and_requeues(self):
        names = AuthorityFrontierService.registered_provider_names()
        assert names, "expected at least one registered authority provider"
        target = sorted(names)[0]
        row = self._ingested_row()
        res = AuthorityFrontierService.reroute(
            self.superuser, pk=row.pk, provider=target
        )
        assert res.ok, res.error
        row.refresh_from_db()
        assert row.provider == target
        assert row.discovery_state == "queued"
        assert row.ingested_document_id is None

    # ---- approve -------------------------------------------------------------
    def test_approve_only_pending_approval(self):
        pending = AuthorityFrontier.objects.create(
            canonical_key="dgcl:145",
            authority="dgcl",
            discovery_state="pending_approval",
        )
        res = AuthorityFrontierService.approve(self.superuser, pk=pending.pk)
        assert res.ok, res.error
        pending.refresh_from_db()
        assert pending.discovery_state == "queued"

        other = AuthorityFrontier.objects.create(
            canonical_key="dgcl:146", authority="dgcl", discovery_state="failed"
        )
        res2 = AuthorityFrontierService.approve(self.superuser, pk=other.pk)
        assert not res2.ok
        assert "pending-approval" in res2.error

    # ---- delete --------------------------------------------------------------
    def test_delete_rows(self):
        a = AuthorityFrontier.objects.create(canonical_key="x:1", authority="x")
        b = AuthorityFrontier.objects.create(canonical_key="x:2", authority="x")
        res = AuthorityFrontierService.delete_rows(self.superuser, pks=[a.pk, b.pk])
        assert res.ok
        assert res.count >= 2
        assert not AuthorityFrontier.objects.filter(pk__in=[a.pk, b.pk]).exists()

    def test_delete_rows_rejects_non_admin(self):
        a = AuthorityFrontier.objects.create(canonical_key="x:1", authority="x")
        res = AuthorityFrontierService.delete_rows(self.regular, pks=[a.pk])
        assert not res.ok
        assert AuthorityFrontier.objects.filter(pk=a.pk).exists()

    # ---- mark() guards -------------------------------------------------------
    def test_mark_rejects_conflicting_set_and_clear(self):
        row = self._ingested_row()
        with self.assertRaises(ValueError):
            AuthorityFrontierService.mark(
                row, "queued", document_id=self.doc.pk, clear_document=True
            )
