"""
Tests for issue #1640's two-tier permission caching strategy.

Tier 1 — per-instance memoization in ``get_users_permissions_for_obj``
(transparent to all callers, lives on ``instance._oc_granted_perms_cache``).

Tier 2 — request-scoped ``PermissionQueryOptimizer`` opt-in via the new
``request=`` kwarg threaded through ``Manager.user_can`` /
``obj.user_can`` / ``_default_user_can``. Attached to the request as
``request._permission_query_optimizer``.

Coverage:
- Cache hits reduce query count to zero on repeat checks.
- Cache key includes ``include_group_permissions`` (no cross-flag leakage).
- Anonymous users bypass the cache entirely.
- Fast paths (superuser, creator, public-READ) short-circuit before the
  cold path and never populate the cache.
- Request-scoped optimizer is lazily attached and reused; ``None`` request
  returns a one-shot optimizer.
- ``invalidate`` supports per-user / per-instance / total clear.
- ``set_permissions_for_obj_to_user(..., request=...)`` self-invalidates
  both tiers so subsequent ``user_can`` reflects the new state.
- Calling without ``request`` (Celery / fixture path) does not break.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory, TransactionTestCase

from opencontractserver.constants.permissioning import (
    INSTANCE_PERMS_CACHE_ATTR,
    REQUEST_OPTIMIZER_ATTR,
)
from opencontractserver.corpuses.models import Corpus
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permission_optimizer import (
    PermissionQueryOptimizer,
    get_request_optimizer,
)
from opencontractserver.utils.permissioning import (
    get_users_permissions_for_obj,
    set_permissions_for_obj_to_user,
)

User = get_user_model()


class PerInstanceMemoizationTestCase(TransactionTestCase):
    """Tier 1: per-instance memoization."""

    def setUp(self):
        self.creator = User.objects.create_user(
            username="t1_creator", email="t1c@test.test", password="x"
        )
        self.reader = User.objects.create_user(
            username="t1_reader", email="t1r@test.test", password="x"
        )
        self.corpus = Corpus.objects.create(
            title="t1 corpus", creator=self.creator, is_public=False
        )
        set_permissions_for_obj_to_user(
            self.reader, self.corpus, [PermissionTypes.READ]
        )

    def _fresh_corpus(self) -> Corpus:
        """Refetch the corpus so the per-instance cache starts empty."""
        return Corpus.objects.get(pk=self.corpus.pk)

    def test_repeat_user_can_zero_queries(self):
        """Second ``user_can`` on the same instance issues no queries."""

        corpus = self._fresh_corpus()
        # First call warms the cache.
        self.assertTrue(corpus.user_can(self.reader, PermissionTypes.READ))
        # Second call should be a pure cache hit — no DB.
        with self.assertNumQueries(0):
            self.assertTrue(corpus.user_can(self.reader, PermissionTypes.READ))
            self.assertFalse(corpus.user_can(self.reader, PermissionTypes.UPDATE))
            self.assertFalse(corpus.user_can(self.reader, PermissionTypes.DELETE))

    def test_cache_key_distinguishes_include_group_permissions(self):
        """``include_group_permissions=True/False`` produce distinct entries."""

        corpus = self._fresh_corpus()
        # Warm both sides of the cache key explicitly via the helper.
        granted_with_groups = get_users_permissions_for_obj(
            user=self.reader,
            instance=corpus,
            include_group_permissions=True,
        )
        granted_no_groups = get_users_permissions_for_obj(
            user=self.reader,
            instance=corpus,
            include_group_permissions=False,
        )
        cache = getattr(corpus, INSTANCE_PERMS_CACHE_ATTR)
        self.assertIn((self.reader.id, True), cache)
        self.assertIn((self.reader.id, False), cache)
        # Both should hold the same codenames here (no group memberships in
        # this fixture) but the cache slots must be independent.
        self.assertEqual(set(granted_with_groups), set(granted_no_groups))
        self.assertEqual(cache[(self.reader.id, True)], cache[(self.reader.id, False)])

    def test_cache_skips_anonymous_user(self):
        """``AnonymousUser`` does not populate the per-instance cache."""

        corpus = self._fresh_corpus()
        # Force the cold path by making the corpus non-public so the fast
        # path doesn't short-circuit before reaching the helper.
        anon = AnonymousUser()
        # AnonymousUser hits the fast-path "not authenticated" branch in
        # _default_user_can and never reaches get_users_permissions_for_obj,
        # but explicit calls to the helper must still avoid caching.
        get_users_permissions_for_obj(user=anon, instance=corpus)  # type: ignore[arg-type]
        self.assertFalse(hasattr(corpus, INSTANCE_PERMS_CACHE_ATTR))

    def test_fast_paths_do_not_populate_cache(self):
        """Superuser/creator/public-READ short-circuits skip the cold path."""

        # Public corpus + anonymous user — fast path.
        public = Corpus.objects.create(
            title="public", creator=self.creator, is_public=True
        )
        self.assertTrue(public.user_can(AnonymousUser(), PermissionTypes.READ))
        self.assertFalse(hasattr(public, INSTANCE_PERMS_CACHE_ATTR))

        # Creator — fast path.
        private = Corpus.objects.create(
            title="private", creator=self.creator, is_public=False
        )
        self.assertTrue(private.user_can(self.creator, PermissionTypes.READ))
        self.assertFalse(hasattr(private, INSTANCE_PERMS_CACHE_ATTR))

        # Superuser — fast path.
        admin = User.objects.create_superuser(
            username="t1_admin", email="t1a@test.test", password="x"
        )
        self.assertTrue(private.user_can(admin, PermissionTypes.READ))
        self.assertFalse(hasattr(private, INSTANCE_PERMS_CACHE_ATTR))

    def test_cache_returns_defensive_copy(self):
        """Callers can mutate the returned set without poisoning the cache.

        ``_default_user_can``'s CRUD/ALL branch unions ``read_<model>`` into
        ``granted`` locally — if the cache returned the same object, that
        would mutate the cached value.
        """

        corpus = self._fresh_corpus()
        first = get_users_permissions_for_obj(user=self.reader, instance=corpus)
        first.add("synthetic_marker")
        second = get_users_permissions_for_obj(user=self.reader, instance=corpus)
        self.assertNotIn("synthetic_marker", second)


class PermissionQueryOptimizerTestCase(TransactionTestCase):
    """Tier 2: request-scoped optimizer."""

    def setUp(self):
        self.creator = User.objects.create_user(
            username="t2_creator", email="t2c@test.test", password="x"
        )
        self.alice = User.objects.create_user(
            username="t2_alice", email="t2a@test.test", password="x"
        )
        self.bob = User.objects.create_user(
            username="t2_bob", email="t2b@test.test", password="x"
        )
        self.corpus_a = Corpus.objects.create(
            title="t2 a", creator=self.creator, is_public=False
        )
        self.corpus_b = Corpus.objects.create(
            title="t2 b", creator=self.creator, is_public=False
        )
        set_permissions_for_obj_to_user(
            self.alice, self.corpus_a, [PermissionTypes.READ]
        )
        set_permissions_for_obj_to_user(
            self.alice, self.corpus_b, [PermissionTypes.READ]
        )
        set_permissions_for_obj_to_user(self.bob, self.corpus_a, [PermissionTypes.READ])
        self.factory = RequestFactory()

    def _fresh_request(self):
        """Make a new HttpRequest with a user — the optimizer attaches here."""
        request = self.factory.get("/graphql/")
        request.user = self.alice
        return request

    def test_get_request_optimizer_lazy_creates_and_returns_same(self):
        """First call attaches; subsequent calls return the same instance."""

        request = self._fresh_request()
        optimizer = get_request_optimizer(request)
        self.assertIsInstance(optimizer, PermissionQueryOptimizer)
        self.assertIs(getattr(request, REQUEST_OPTIMIZER_ATTR), optimizer)
        self.assertIs(get_request_optimizer(request), optimizer)

    def test_get_request_optimizer_none_returns_one_shot(self):
        """``get_request_optimizer(None)`` returns a usable optimizer."""

        optimizer = get_request_optimizer(None)
        self.assertIsInstance(optimizer, PermissionQueryOptimizer)
        # Independent of any subsequent call.
        self.assertIsNot(optimizer, get_request_optimizer(None))

    def test_optimizer_caches_across_distinct_instances(self):
        """Second ``user_can`` on a different corpus instance is still cached
        within the same request (Tier 2)."""

        request = self._fresh_request()
        # Warm the cache by checking corpus_a and corpus_b under the
        # optimizer. Force a fresh fetch of each instance to defeat Tier 1
        # so we can confirm Tier 2 is doing the work.
        corpus_a = Corpus.objects.get(pk=self.corpus_a.pk)
        corpus_b = Corpus.objects.get(pk=self.corpus_b.pk)
        self.assertTrue(
            corpus_a.user_can(self.alice, PermissionTypes.READ, request=request)
        )
        self.assertTrue(
            corpus_b.user_can(self.alice, PermissionTypes.READ, request=request)
        )

        optimizer = get_request_optimizer(request)
        # Refetch corpus_a as a freshly-loaded instance — Tier 1 will be
        # empty on this object. Tier 2 should still hit on the optimizer.
        corpus_a_again = Corpus.objects.get(pk=self.corpus_a.pk)
        with self.assertNumQueries(0):
            granted = optimizer.get_granted(self.alice, corpus_a_again)
            self.assertIn(f"read_{Corpus._meta.model_name}", granted)

    def test_optimizer_distinguishes_users(self):
        """Alice and Bob on the same corpus produce distinct cache entries."""

        request = self._fresh_request()
        corpus = Corpus.objects.get(pk=self.corpus_a.pk)
        corpus.user_can(self.alice, PermissionTypes.READ, request=request)
        corpus.user_can(self.bob, PermissionTypes.READ, request=request)

        optimizer = get_request_optimizer(request)
        cache = optimizer._cache
        alice_keys = [k for k in cache if k[0] == self.alice.id]
        bob_keys = [k for k in cache if k[0] == self.bob.id]
        self.assertEqual(len(alice_keys), 1)
        self.assertEqual(len(bob_keys), 1)
        self.assertNotEqual(alice_keys[0], bob_keys[0])

    def test_invalidate_per_user(self):
        """``invalidate(user_id=...)`` drops only that user's entries."""

        optimizer = PermissionQueryOptimizer()
        optimizer.get_granted(self.alice, self.corpus_a)
        optimizer.get_granted(self.bob, self.corpus_a)
        self.assertEqual(len(optimizer._cache), 2)

        optimizer.invalidate(user_id=self.alice.id)
        remaining = list(optimizer._cache)
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0][0], self.bob.id)

    def test_invalidate_per_instance(self):
        """``invalidate(instance=...)`` drops all users' entries for that
        instance only."""

        optimizer = PermissionQueryOptimizer()
        optimizer.get_granted(self.alice, self.corpus_a)
        optimizer.get_granted(self.alice, self.corpus_b)
        optimizer.get_granted(self.bob, self.corpus_a)
        self.assertEqual(len(optimizer._cache), 3)

        optimizer.invalidate(instance=self.corpus_a)
        self.assertEqual(len(optimizer._cache), 1)
        remaining_pks = {k[2] for k in optimizer._cache}
        self.assertEqual(remaining_pks, {self.corpus_b.pk})

    def test_invalidate_caches_clears_all(self):
        """``invalidate_caches()`` empties the dict."""

        optimizer = PermissionQueryOptimizer()
        optimizer.get_granted(self.alice, self.corpus_a)
        optimizer.get_granted(self.bob, self.corpus_a)
        self.assertEqual(len(optimizer._cache), 2)
        optimizer.invalidate_caches()
        self.assertEqual(len(optimizer._cache), 0)

    def test_invalidate_rejects_mixed_coordinates(self):
        """``invalidate(instance=..., instance_pk=...)`` raises ``ValueError``.

        The two forms describe the same slot — mixing them was previously
        a silent footgun where ``instance`` won. Now it's loud.
        """

        optimizer = PermissionQueryOptimizer()
        with self.assertRaises(ValueError):
            optimizer.invalidate(instance=self.corpus_a, instance_pk=self.corpus_b.pk)
        with self.assertRaises(ValueError):
            optimizer.invalidate(instance=self.corpus_a, content_type_id=1)

    def test_optimizer_skips_anonymous_user(self):
        """Anonymous users do not populate Tier 2."""

        optimizer = PermissionQueryOptimizer()
        optimizer.get_granted(AnonymousUser(), self.corpus_a)
        self.assertEqual(len(optimizer._cache), 0)


class MutationInvalidationTestCase(TransactionTestCase):
    """``set_permissions_for_obj_to_user`` clears both tiers when given a
    request, so subsequent ``user_can`` checks reflect the new state."""

    def setUp(self):
        self.creator = User.objects.create_user(
            username="inv_creator", email="invc@test.test", password="x"
        )
        self.target = User.objects.create_user(
            username="inv_target", email="invt@test.test", password="x"
        )
        self.corpus = Corpus.objects.create(
            title="inv", creator=self.creator, is_public=False
        )
        self.factory = RequestFactory()

    def test_set_permissions_with_request_invalidates_both_tiers(self):
        """Grant after a denied check is visible mid-request when ``request``
        is supplied."""

        request = self.factory.get("/graphql/")
        request.user = self.target

        # Step 1: target has no grant — both tiers cache False.
        self.assertFalse(
            self.corpus.user_can(self.target, PermissionTypes.UPDATE, request=request)
        )
        optimizer = get_request_optimizer(request)
        self.assertGreater(len(optimizer._cache), 0)
        self.assertTrue(hasattr(self.corpus, INSTANCE_PERMS_CACHE_ATTR))

        # Step 2: grant UPDATE with the request — both tiers invalidated.
        set_permissions_for_obj_to_user(
            self.target,
            self.corpus,
            [PermissionTypes.UPDATE],
            request=request,
        )

        # Step 3: re-check — must reflect the new grant.
        self.assertTrue(
            self.corpus.user_can(self.target, PermissionTypes.UPDATE, request=request)
        )

    def test_set_permissions_without_request_skips_tier_two(self):
        """Celery/fixture path: ``request=None`` is safe and does not raise.
        Tier 1 is still scrubbed for the target user so reused instances see
        the new grant."""

        # Warm Tier 1 with a denial.
        self.assertFalse(self.corpus.user_can(self.target, PermissionTypes.UPDATE))
        self.assertTrue(hasattr(self.corpus, INSTANCE_PERMS_CACHE_ATTR))

        # Grant without a request — Tier 2 not touched, Tier 1 scrubbed.
        set_permissions_for_obj_to_user(
            self.target, self.corpus, [PermissionTypes.UPDATE]
        )

        # Re-check reflects the new state for the target user even on the
        # reused instance (Tier 1 was scrubbed for ``target.id``).
        self.assertTrue(self.corpus.user_can(self.target, PermissionTypes.UPDATE))


class ManagerAndInstanceRequestPassthroughTestCase(TransactionTestCase):
    """The new ``request=`` kwarg on ``Manager.user_can`` and
    ``obj.user_can`` is plumbed through to ``_default_user_can`` and the
    optimizer.
    """

    def setUp(self):
        self.creator = User.objects.create_user(
            username="pt_creator", email="ptc@test.test", password="x"
        )
        self.reader = User.objects.create_user(
            username="pt_reader", email="ptr@test.test", password="x"
        )
        self.corpus = Corpus.objects.create(
            title="pt", creator=self.creator, is_public=False
        )
        set_permissions_for_obj_to_user(
            self.reader, self.corpus, [PermissionTypes.READ]
        )
        self.factory = RequestFactory()

    def test_manager_user_can_routes_through_optimizer(self):
        request = self.factory.get("/graphql/")
        request.user = self.reader

        result = Corpus.objects.user_can(
            self.reader, self.corpus, PermissionTypes.READ, request=request
        )
        self.assertTrue(result)
        optimizer = get_request_optimizer(request)
        self.assertEqual(len(optimizer._cache), 1)

    def test_instance_user_can_routes_through_optimizer(self):
        request = self.factory.get("/graphql/")
        request.user = self.reader

        result = self.corpus.user_can(
            self.reader, PermissionTypes.READ, request=request
        )
        self.assertTrue(result)
        optimizer = get_request_optimizer(request)
        self.assertEqual(len(optimizer._cache), 1)
