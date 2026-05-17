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
    _InstancePermsCache,
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
        # First call warms the cache. Assert a finite query budget so a
        # regression that makes the cold path explode in queries is still
        # caught here — without this bound, only the second call's
        # zero-query assertion below would notice anything had changed.
        # 6 = current guardian lookup cost (object + group perms, content-
        # type warm-up, user/anon resolution); update if the path changes.
        # NOTE: This pin is intentionally exact, not a `<=` bound — a
        # regression that adds even one extra query should be visible
        # here. Expect to revisit this number on django-guardian or
        # Django upgrades (guardian occasionally restructures its
        # object-permission lookup) and on any refactor of
        # ``get_users_permissions_for_obj``. If the count grows after an
        # upgrade and you've verified the new shape is correct, bump the
        # constant and update this comment with the new query breakdown.
        with self.assertNumQueries(6):
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

    def test_direct_call_with_superuser_warms_instance_cache(self):
        """Superusers go through the guardian-superuser branch.

        ``_default_user_can`` short-circuits for superusers before reaching
        ``get_users_permissions_for_obj``, so the warming side-effect at
        the superuser return path is only exercised when callers invoke
        the helper directly (e.g. mutation resolvers checking compound
        permissions). The cache must still populate so a subsequent
        direct call short-circuits to the Tier 1 hit path.
        """

        admin = User.objects.create_superuser(
            username="t1_warm_admin", email="t1_wa@test.test", password="x"
        )
        corpus = self._fresh_corpus()
        granted = get_users_permissions_for_obj(user=admin, instance=corpus)
        # Superuser on a guardian-enabled model gets the rich 7-perm set.
        self.assertIn("create_corpus", granted)
        self.assertIn("permission_corpus", granted)
        # Cache attribute is now present under the keyed slot.
        cache = getattr(corpus, INSTANCE_PERMS_CACHE_ATTR, None)
        assert cache is not None
        # Default ``include_group_permissions=True`` (aligned with every
        # other ``user_can`` surface) — see ``get_users_permissions_for_obj``.
        self.assertIn((admin.id, True), cache)
        # Second call returns a defensive copy of the same content.
        again = get_users_permissions_for_obj(user=admin, instance=corpus)
        self.assertEqual(again, granted)

    def test_refresh_from_db_does_not_clear_tier1_cache(self):
        """Negative regression guard: ``refresh_from_db()`` does NOT clear
        Tier 1.

        The cache is keyed by ``(user_id, include_group_permissions)`` and
        attached to the instance under
        ``_oc_granted_perms_cache``. Django's
        ``refresh_from_db`` reloads field values from the row but does
        not clear arbitrary instance attributes, so the cached frozenset
        survives. This is by design (the contract pinned in
        ``constants/permissioning.py``) — long-lived Celery instances or
        any code that mutates guardian permissions out-of-band must
        ``del instance._oc_granted_perms_cache`` to force a re-read.

        We pin both sides of the contract:
          1. ``refresh_from_db`` leaves the cache attribute attached.
          2. ``delattr(instance, INSTANCE_PERMS_CACHE_ATTR)`` is the
             documented workaround and causes the next call to re-hit
             the DB.
        """

        corpus = self._fresh_corpus()
        # Warm the cache.
        self.assertTrue(corpus.user_can(self.reader, PermissionTypes.READ))
        self.assertTrue(hasattr(corpus, INSTANCE_PERMS_CACHE_ATTR))

        # refresh_from_db reloads model fields but leaves the cache
        # attribute attached — this is the known footgun.
        corpus.refresh_from_db()
        self.assertTrue(
            hasattr(corpus, INSTANCE_PERMS_CACHE_ATTR),
            "refresh_from_db must NOT clear the perm cache — that contract "
            "is documented in constants/permissioning.py and any change to "
            "this behaviour needs a coordinated invalidation strategy.",
        )

        # The documented workaround: explicit delattr.
        delattr(corpus, INSTANCE_PERMS_CACHE_ATTR)
        self.assertFalse(hasattr(corpus, INSTANCE_PERMS_CACHE_ATTR))
        # Next call re-warms from scratch (i.e. it ran the cold path).
        self.assertTrue(corpus.user_can(self.reader, PermissionTypes.READ))
        self.assertTrue(hasattr(corpus, INSTANCE_PERMS_CACHE_ATTR))

    def test_direct_call_with_prefetched_guardian_perms_warms_cache(self):
        """The fast-path return at the prefetched-perms branch also caches.

        When a queryset has been hydrated with the per-user guardian
        prefetches (``user_perm_attr``), ``get_users_permissions_for_obj``
        builds the codename set from the prefetch and short-circuits
        without a guardian query. That return must still warm Tier 1 so
        a follow-up call on the same instance avoids re-walking the
        prefetched perms.
        """

        from opencontractserver.shared.prefetch_attrs import user_perm_attr

        corpus = self._fresh_corpus()
        # Simulate a prefetch attach: collect the reader's CorpusUserObjectPermissions
        # and stash them on the instance under the per-user prefetch attr.
        user_perms = list(
            corpus.corpususerobjectpermission_set.filter(
                user=self.reader
            ).select_related("permission")
        )
        setattr(corpus, user_perm_attr(self.reader.id), user_perms)

        granted = get_users_permissions_for_obj(user=self.reader, instance=corpus)
        # The grant from setUp is READ → only ``read_corpus``.
        self.assertEqual(granted, {"read_corpus"})

        # Cache populated under the keyed slot.
        cache = getattr(corpus, INSTANCE_PERMS_CACHE_ATTR, None)
        assert cache is not None
        self.assertIn((self.reader.id, True), cache)


class Tier1CacheThreadSafetyTestCase(TransactionTestCase):
    """Tier 1: per-instance cache must survive concurrent invalidation.

    Pre-fix, the cache was a plain ``dict`` and
    ``set_permissions_for_obj_to_user`` deleted entries inside a
    ``for key in [...]`` snapshot. Under ASGI / async views / any path
    that lets multiple threads touch the same Python instance, a
    concurrent writer mutating the dict mid-sweep would raise
    ``RuntimeError: dictionary changed size during iteration``. The
    ``_InstancePermsCache`` wrapper plus ``drop_for_user`` close that
    gap by holding a lock for the compound op.
    """

    def setUp(self):
        self.creator = User.objects.create_user(
            username="t1_thread_creator", email="t1_tc@test.test", password="x"
        )
        self.corpus = Corpus.objects.create(
            title="t1 thread corpus", creator=self.creator, is_public=False
        )
        # A modest fleet of readers so the invalidate sweep has more than
        # one key to iterate. The race is observable with N≥2 keys; the
        # extra entries shorten the mean iteration before a race would
        # surface without bloating fixture cost (each ``create_user`` +
        # ``set_permissions_for_obj_to_user`` is a guardian write).
        self.readers = [
            User.objects.create_user(
                username=f"t1_thread_reader_{i}",
                email=f"t1_tr_{i}@test.test",
                password="x",
            )
            for i in range(8)
        ]
        for reader in self.readers:
            set_permissions_for_obj_to_user(reader, self.corpus, [PermissionTypes.READ])

    def test_instance_cache_is_thread_safe_wrapper(self):
        """Warming the cache attaches the thread-safe wrapper, not a plain dict."""

        corpus = Corpus.objects.get(pk=self.corpus.pk)
        get_users_permissions_for_obj(user=self.readers[0], instance=corpus)
        cache = getattr(corpus, INSTANCE_PERMS_CACHE_ATTR)
        self.assertIsInstance(cache, _InstancePermsCache)

    def test_concurrent_reads_and_invalidations_do_not_race(self):
        """Reader threads must not see ``RuntimeError`` during a concurrent
        invalidate sweep.

        The pre-fix ``for key in [k for k in dict if ...]`` pattern was
        safe in isolation but the comprehension's snapshot could still
        race with a concurrent reader iterating the same dict (e.g.
        the cache key isolation tests above iterate the cache for
        membership). This test pins the contract: under heavy
        contention from N=4 reader threads doing membership tests and
        the main thread sweeping keys, no thread raises.
        """

        import threading

        corpus = Corpus.objects.get(pk=self.corpus.pk)
        # Warm Tier 1 with one frozenset per reader so the sweep
        # actually has work to do.
        for reader in self.readers:
            get_users_permissions_for_obj(user=reader, instance=corpus)
        cache = getattr(corpus, INSTANCE_PERMS_CACHE_ATTR)
        self.assertIsInstance(cache, _InstancePermsCache)
        # Population check before the storm.
        self.assertEqual(len(cache), len(self.readers))

        errors: list[BaseException] = []
        stop = threading.Event()

        def hammer_reads():
            try:
                while not stop.is_set():
                    # Membership checks and indexed reads — same operations
                    # that production cache hits perform on the hot path.
                    for k in list(cache):
                        _ = cache.get(k)
            except BaseException as exc:  # noqa: BLE001 — surface to the test.
                errors.append(exc)

        readers = [threading.Thread(target=hammer_reads) for _ in range(4)]
        for t in readers:
            t.start()
        try:
            # Repeatedly invalidate every reader's entries. Each sweep
            # mutates the dict while the reader threads are walking it.
            # 5 iterations × 8 readers is enough contention to surface
            # the pre-fix race ~deterministically (verified locally by
            # reverting drop_for_user to the raw ``del`` loop) while
            # keeping the test under a couple of seconds.
            for _ in range(5):
                for reader in self.readers:
                    cache.drop_for_user(reader.id)
                # Re-warm so the next sweep has keys to remove.
                for reader in self.readers:
                    get_users_permissions_for_obj(user=reader, instance=corpus)
        finally:
            stop.set()
            for t in readers:
                t.join(timeout=5.0)

        self.assertEqual(
            errors,
            [],
            "Reader threads must not raise during concurrent invalidate sweeps; "
            f"saw {errors!r}",
        )

    def test_set_permissions_invalidation_uses_thread_safe_drop(self):
        """``set_permissions_for_obj_to_user`` routes Tier 1 invalidation
        through the thread-safe ``drop_for_user`` method.

        The legacy code did an inline ``for key in [...]: del cache[key]``.
        The new path delegates to ``_InstancePermsCache.drop_for_user`` so
        the lock-guarded contract is centralized. Asserting on the call
        ensures a future refactor that re-inlines the sweep would trip
        a test rather than silently re-introduce the race.
        """

        from unittest.mock import patch

        corpus = Corpus.objects.get(pk=self.corpus.pk)
        # Warm Tier 1 for two readers so the sweep has work.
        reader_a, reader_b = self.readers[0], self.readers[1]
        get_users_permissions_for_obj(user=reader_a, instance=corpus)
        get_users_permissions_for_obj(user=reader_b, instance=corpus)
        cache = getattr(corpus, INSTANCE_PERMS_CACHE_ATTR)
        self.assertIsInstance(cache, _InstancePermsCache)

        with patch.object(_InstancePermsCache, "drop_for_user", autospec=True) as drop:
            set_permissions_for_obj_to_user(
                reader_a, corpus, [PermissionTypes.READ, PermissionTypes.UPDATE]
            )

        # The mutation invalidates exactly reader_a's entries.
        drop.assert_called_once_with(cache, reader_a.id)


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

    def test_invalidate_rejects_pk_without_content_type(self):
        """``invalidate(instance_pk=...)`` alone is ambiguous across model
        types — without a ``content_type_id`` the wildcard match would
        evict entries for every model whose PK collides. The guard
        forces callers to either pair the pk with its content type or
        use ``instance=``.
        """

        optimizer = PermissionQueryOptimizer()
        with self.assertRaises(ValueError):
            optimizer.invalidate(instance_pk=self.corpus_a.pk)
        with self.assertRaises(ValueError):
            optimizer.invalidate(user_id=self.alice.id, instance_pk=self.corpus_a.pk)

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


class DefaultUserCanCoverageTestCase(TransactionTestCase):
    """Direct coverage for the centralized ``_default_user_can`` body.

    Pins each permission-type branch (CREATE/UPDATE/EDIT/DELETE/COMMENT/
    PUBLISH/PERMISSION/CRUD/ALL) and each user-resolution path
    (None / AnonymousUser / int id / str id / unknown id / unauthenticated
    test-double) so refactors of the dispatch table don't silently regress
    a branch.
    """

    def setUp(self):
        self.creator = User.objects.create_user(
            username="duc_creator", email="duc_c@test.test", password="x"
        )
        self.grantee = User.objects.create_user(
            username="duc_grantee", email="duc_g@test.test", password="x"
        )
        # Non-public so the public-READ short-circuit doesn't mask the
        # branches we want to exercise.
        self.corpus = Corpus.objects.create(
            title="duc", creator=self.creator, is_public=False
        )

    def _call(self, user, permission, **kwargs):
        from opencontractserver.utils.permissioning import _default_user_can

        return _default_user_can(user, self.corpus, permission, **kwargs)

    def test_none_user_returns_false(self):
        self.assertFalse(self._call(None, PermissionTypes.READ))

    def test_anonymous_user_public_read(self):
        public = Corpus.objects.create(
            title="public_duc", creator=self.creator, is_public=True
        )
        from opencontractserver.utils.permissioning import _default_user_can

        self.assertTrue(
            _default_user_can(AnonymousUser(), public, PermissionTypes.READ)
        )
        # Anonymous + non-READ on public → still False
        self.assertFalse(
            _default_user_can(AnonymousUser(), public, PermissionTypes.UPDATE)
        )
        # Anonymous + READ on private → False
        self.assertFalse(self._call(AnonymousUser(), PermissionTypes.READ))

    def test_user_resolved_from_int_id(self):
        """Passing the user's integer id resolves to the User instance."""
        self.assertTrue(self._call(self.creator.id, PermissionTypes.READ))

    def test_user_resolved_from_str_id(self):
        """Passing the user's id as a string still resolves correctly."""
        self.assertTrue(self._call(str(self.creator.id), PermissionTypes.READ))

    def test_unknown_user_id_returns_false(self):
        # Pick an id we know doesn't exist
        last = User.objects.order_by("-id").first()
        assert last is not None
        bogus_id = last.id + 9999
        self.assertFalse(self._call(bogus_id, PermissionTypes.READ))

    def test_unauthenticated_double_treats_public_read_only(self):
        """Custom user-like with ``is_authenticated=False`` still routes the
        public-READ short-circuit (long-tail defensive branch).
        """

        class _FakeUnauthUser:
            id = 999_999
            is_authenticated = False
            is_superuser = False
            is_anonymous = False

        public = Corpus.objects.create(
            title="public_for_double", creator=self.creator, is_public=True
        )
        from opencontractserver.utils.permissioning import _default_user_can

        self.assertTrue(
            _default_user_can(
                _FakeUnauthUser(),  # type: ignore[arg-type]
                public,
                PermissionTypes.READ,
            )
        )
        self.assertFalse(
            _default_user_can(
                _FakeUnauthUser(),  # type: ignore[arg-type]
                public,
                PermissionTypes.UPDATE,
            )
        )
        # Non-public + double → False
        self.assertFalse(self._call(_FakeUnauthUser(), PermissionTypes.READ))

    def test_superuser_short_circuits_all_permissions(self):
        admin = User.objects.create_superuser(
            username="duc_admin", email="duc_a@test.test", password="x"
        )
        for perm in (
            PermissionTypes.READ,
            PermissionTypes.CREATE,
            PermissionTypes.UPDATE,
            PermissionTypes.EDIT,
            PermissionTypes.DELETE,
            PermissionTypes.COMMENT,
            PermissionTypes.PUBLISH,
            PermissionTypes.PERMISSION,
            PermissionTypes.CRUD,
            PermissionTypes.ALL,
        ):
            self.assertTrue(self._call(admin, perm), f"superuser denied {perm}")

    def test_each_individual_permission_branch(self):
        """Each non-compound permission codename is dispatched correctly."""
        # Grant the full surface so every individual branch returns True.
        set_permissions_for_obj_to_user(
            self.grantee,
            self.corpus,
            [
                PermissionTypes.CREATE,
                PermissionTypes.READ,
                PermissionTypes.UPDATE,
                PermissionTypes.DELETE,
                PermissionTypes.COMMENT,
                PermissionTypes.PUBLISH,
                PermissionTypes.PERMISSION,
            ],
        )
        # Re-fetch to drop the per-instance cache populated by setUp,
        # ensuring the cold path is exercised at least once.
        corpus = Corpus.objects.get(pk=self.corpus.pk)
        from opencontractserver.utils.permissioning import _default_user_can

        for perm in (
            PermissionTypes.CREATE,
            PermissionTypes.READ,
            PermissionTypes.UPDATE,
            PermissionTypes.EDIT,  # alias for UPDATE
            PermissionTypes.DELETE,
            PermissionTypes.COMMENT,
            PermissionTypes.PUBLISH,
            PermissionTypes.PERMISSION,
        ):
            self.assertTrue(
                _default_user_can(self.grantee, corpus, perm),
                f"{perm} unexpectedly False",
            )

    def test_crud_requires_all_four_base_perms(self):
        # Only READ granted → CRUD must be False.
        set_permissions_for_obj_to_user(
            self.grantee, self.corpus, [PermissionTypes.READ]
        )
        corpus = Corpus.objects.get(pk=self.corpus.pk)
        from opencontractserver.utils.permissioning import _default_user_can

        self.assertFalse(_default_user_can(self.grantee, corpus, PermissionTypes.CRUD))

        # Grant the missing three → CRUD now passes.
        set_permissions_for_obj_to_user(
            self.grantee,
            self.corpus,
            [
                PermissionTypes.CREATE,
                PermissionTypes.READ,
                PermissionTypes.UPDATE,
                PermissionTypes.DELETE,
            ],
        )
        corpus = Corpus.objects.get(pk=self.corpus.pk)
        self.assertTrue(_default_user_can(self.grantee, corpus, PermissionTypes.CRUD))

    def test_all_requires_seven_perms(self):
        # CRUD-only grant is insufficient for ALL.
        set_permissions_for_obj_to_user(
            self.grantee,
            self.corpus,
            [
                PermissionTypes.CREATE,
                PermissionTypes.READ,
                PermissionTypes.UPDATE,
                PermissionTypes.DELETE,
            ],
        )
        corpus = Corpus.objects.get(pk=self.corpus.pk)
        from opencontractserver.utils.permissioning import _default_user_can

        self.assertFalse(_default_user_can(self.grantee, corpus, PermissionTypes.ALL))

        # Add the remaining COMMENT/PUBLISH/PERMISSION grants.
        set_permissions_for_obj_to_user(
            self.grantee,
            self.corpus,
            [
                PermissionTypes.CREATE,
                PermissionTypes.READ,
                PermissionTypes.UPDATE,
                PermissionTypes.DELETE,
                PermissionTypes.COMMENT,
                PermissionTypes.PUBLISH,
                PermissionTypes.PERMISSION,
            ],
        )
        corpus = Corpus.objects.get(pk=self.corpus.pk)
        self.assertTrue(_default_user_can(self.grantee, corpus, PermissionTypes.ALL))

    def test_crud_satisfied_by_public_read_plus_explicit_writes(self):
        """The is_public READ fold-in keeps CRUD passable when a user has
        only the C/U/D explicit grants on a public corpus (no explicit READ
        is needed because is_public synthesises it).
        """
        public = Corpus.objects.create(
            title="public_crud", creator=self.creator, is_public=True
        )
        set_permissions_for_obj_to_user(
            self.grantee,
            public,
            [
                PermissionTypes.CREATE,
                PermissionTypes.UPDATE,
                PermissionTypes.DELETE,
            ],
        )
        public = Corpus.objects.get(pk=public.pk)
        from opencontractserver.utils.permissioning import _default_user_can

        self.assertTrue(_default_user_can(self.grantee, public, PermissionTypes.CRUD))

    def test_creator_passes_compound_perms_without_explicit_grants(self):
        """Creator short-circuit applies BEFORE the compound CRUD/ALL check."""
        from opencontractserver.utils.permissioning import _default_user_can

        self.assertTrue(
            _default_user_can(self.creator, self.corpus, PermissionTypes.CRUD)
        )
        self.assertTrue(
            _default_user_can(self.creator, self.corpus, PermissionTypes.ALL)
        )

    def test_unknown_permission_returns_false(self):
        """An unhandled PermissionTypes value falls through to the final
        ``return False`` — protects against a future enum value silently
        granting access.
        """

        # Inject a sentinel that isn't in the dispatch table.
        class _Sentinel:
            value = "made_up_permission"

        from opencontractserver.utils.permissioning import _default_user_can

        set_permissions_for_obj_to_user(
            self.grantee, self.corpus, [PermissionTypes.READ]
        )
        corpus = Corpus.objects.get(pk=self.corpus.pk)
        self.assertFalse(
            _default_user_can(
                self.grantee,
                corpus,
                _Sentinel(),  # type: ignore[arg-type]
            )
        )


class SetPermissionsInvalidationCoverageTestCase(TransactionTestCase):
    """Cover the cache-invalidation branches in
    ``set_permissions_for_obj_to_user`` that the existing test suite
    leaves implicit.
    """

    def setUp(self):
        self.creator = User.objects.create_user(
            username="spi_creator", email="spi_c@test.test", password="x"
        )
        self.grantee = User.objects.create_user(
            username="spi_grantee", email="spi_g@test.test", password="x"
        )
        self.corpus = Corpus.objects.create(
            title="spi", creator=self.creator, is_public=False
        )

    def test_invalidation_preserves_other_users_cache_entries(self):
        """The instance-cache scrub on grant only deletes the affected
        user's entries — entries for OTHER users in the same cache must
        survive.
        """
        from opencontractserver.utils.permissioning import (
            get_users_permissions_for_obj,
        )

        other = User.objects.create_user(
            username="spi_other", email="spi_o@test.test", password="x"
        )
        set_permissions_for_obj_to_user(other, self.corpus, [PermissionTypes.READ])
        set_permissions_for_obj_to_user(
            self.grantee, self.corpus, [PermissionTypes.READ]
        )

        # Warm Tier 1 for both users via the helper.
        get_users_permissions_for_obj(user=other, instance=self.corpus)
        get_users_permissions_for_obj(user=self.grantee, instance=self.corpus)

        cache_before = dict(getattr(self.corpus, INSTANCE_PERMS_CACHE_ATTR, {}))
        # Should hold both users' entries. Default ``include_group_permissions=True``
        # is aligned across every ``user_can`` surface (see
        # ``get_users_permissions_for_obj`` docstring).
        self.assertIn((other.id, True), cache_before)
        self.assertIn((self.grantee.id, True), cache_before)

        # Re-grant for grantee only — must scrub grantee's entries but
        # leave ``other``'s untouched.
        set_permissions_for_obj_to_user(
            self.grantee, self.corpus, [PermissionTypes.UPDATE]
        )
        cache_after = getattr(self.corpus, INSTANCE_PERMS_CACHE_ATTR, {})
        self.assertIn((other.id, True), cache_after)
        self.assertNotIn((self.grantee.id, True), cache_after)

    def test_set_permissions_without_request_still_drops_instance_cache(self):
        """Tier 1 must always be scrubbed, even when no request is supplied
        (Celery / fixture / signal path).
        """
        from opencontractserver.utils.permissioning import (
            get_users_permissions_for_obj,
        )

        set_permissions_for_obj_to_user(
            self.grantee, self.corpus, [PermissionTypes.READ]
        )
        get_users_permissions_for_obj(user=self.grantee, instance=self.corpus)
        self.assertIn(
            (self.grantee.id, True),
            getattr(self.corpus, INSTANCE_PERMS_CACHE_ATTR, {}),
        )

        # Re-grant WITHOUT request — should still drop the cache slot.
        set_permissions_for_obj_to_user(
            self.grantee, self.corpus, [PermissionTypes.UPDATE]
        )
        self.assertNotIn(
            (self.grantee.id, True),
            getattr(self.corpus, INSTANCE_PERMS_CACHE_ATTR, {}),
        )


class Tier1PicklingScrubTestCase(TransactionTestCase):
    """``InstanceUserCanMixin.__getstate__`` strips the Tier 1 cache.

    The Tier 1 per-instance cache is stashed on ``instance.__dict__`` under
    ``INSTANCE_PERMS_CACHE_ATTR``. Default pickling would carry it to
    Celery workers (or any other ``pickle``-based round-trip), leaving the
    receiver acting on a snapshot that may have drifted between
    ``apply_async`` and the worker picking the task up. ``__getstate__``
    on the shared mixin strips the entry so the worker can never see a
    stale frozenset.
    """

    def setUp(self):
        self.creator = User.objects.create_user(
            username="pickle_creator", email="pc@test.test", password="x"
        )
        self.reader = User.objects.create_user(
            username="pickle_reader", email="pr@test.test", password="x"
        )
        self.corpus = Corpus.objects.create(
            title="pickle corpus", creator=self.creator, is_public=False
        )
        set_permissions_for_obj_to_user(
            self.reader, self.corpus, [PermissionTypes.READ]
        )

    def test_pickle_drops_cache_attribute(self):
        """Round-tripping through pickle removes the Tier 1 cache."""
        import pickle

        # Warm Tier 1.
        get_users_permissions_for_obj(user=self.reader, instance=self.corpus)
        self.assertTrue(hasattr(self.corpus, INSTANCE_PERMS_CACHE_ATTR))

        restored = pickle.loads(pickle.dumps(self.corpus))
        self.assertFalse(
            hasattr(restored, INSTANCE_PERMS_CACHE_ATTR),
            "Pickled instance must NOT carry the Tier 1 cache to the receiver "
            "(see InstanceUserCanMixin.__getstate__).",
        )
        # Producer-side instance keeps its cache — only the serialised
        # state is scrubbed.
        self.assertTrue(hasattr(self.corpus, INSTANCE_PERMS_CACHE_ATTR))

    def test_getstate_returns_dict_without_cache_key(self):
        """Direct ``__getstate__`` call returns a dict missing the cache key."""

        get_users_permissions_for_obj(user=self.reader, instance=self.corpus)
        state = self.corpus.__getstate__()
        self.assertIsInstance(state, dict)
        self.assertNotIn(INSTANCE_PERMS_CACHE_ATTR, state)


class FolderServiceRequestKwargCoverageTestCase(TransactionTestCase):
    """Smoke coverage for the ``request=`` kwarg flowing through the
    ``DocumentFolderService`` permission gates.

    The folder service methods accept ``request=request`` so the Tier 2
    optimizer can be shared across folder-related GraphQL resolvers in
    the same request. Verify the parameter is accepted and the denial
    branch fires when the user has no access.
    """

    def setUp(self):
        self.creator = User.objects.create_user(
            username="fs_creator", email="fs_c@test.test", password="x"
        )
        self.outsider = User.objects.create_user(
            username="fs_outsider", email="fs_o@test.test", password="x"
        )
        self.corpus = Corpus.objects.create(
            title="fs", creator=self.creator, is_public=False
        )
        self.factory = RequestFactory()

    def test_get_visible_folders_denies_outsider(self):
        from opencontractserver.corpuses.folder_service import DocumentFolderService

        request = self.factory.get("/graphql/")
        request.user = self.outsider
        # Permission-denied path returns an empty QuerySet (NOT raise) so
        # GraphQL resolvers can serialize cleanly. Exercise the branch.
        result = DocumentFolderService.get_visible_folders(
            self.outsider, self.corpus.id, request=request
        )
        self.assertEqual(list(result), [])

    def test_get_visible_folders_allows_creator(self):
        from opencontractserver.corpuses.folder_service import DocumentFolderService

        request = self.factory.get("/graphql/")
        request.user = self.creator
        # Creator can list folders — returned queryset is permitted but
        # may be empty when no folder rows exist; .list() materialises
        # without raising.
        result = DocumentFolderService.get_visible_folders(
            self.creator, self.corpus.id, request=request
        )
        # Either a list or a queryset; both are acceptable — just exercise
        # the success-path return.
        self.assertIsNotNone(result)
