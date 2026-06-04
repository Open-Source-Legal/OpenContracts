"""Tests for the cached annotation-count queryset (issue #1908).

The un-scoped "Browse annotations" view shows an exact ``totalCount`` backed by
a ``COUNT(*)`` over the full permission-filtered set. graphene-django runs that
COUNT eagerly on every page, so ``AnnotationQuerySet.with_cached_count()`` caches
the value keyed by the compiled SQL. These tests pin that the cache:

  - returns the correct value on a miss and persists it,
  - serves a stale value within the TTL (proving the COUNT is not re-run),
  - keys per filter/user so different querysets never collide,
  - survives the ``_clone()`` graphene performs during pagination.
"""

from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase

from opencontractserver.annotations.models import Annotation, AnnotationLabel
from opencontractserver.documents.models import Document
from opencontractserver.shared.QuerySets import CachedCountAnnotationQuerySet
from opencontractserver.types.enums import LabelType
from opencontractserver.users.models import User


class TestCachedAnnotationCount(TestCase):
    owner: User
    other: User
    doc: Document
    label: AnnotationLabel

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(
            username="count-owner", email="co@test.com", password="x"
        )
        cls.other = User.objects.create_user(
            username="count-other", email="ct@test.com", password="x"
        )
        cls.doc = Document.objects.create(
            title="Doc", creator=cls.owner, is_public=False
        )
        cls.label = AnnotationLabel.objects.create(
            text="L", creator=cls.owner, label_type=LabelType.TOKEN_LABEL
        )
        for i in range(3):
            Annotation.objects.create(
                raw_text=f"a{i}",
                document=cls.doc,
                annotation_label=cls.label,
                creator=cls.owner,
            )

    def setUp(self):
        # LocMemCache persists across tests in a class; isolate each method.
        cache.clear()

    def _visible_qs(self, user):
        return Annotation.objects.visible_to_user(user)

    def test_with_cached_count_returns_cached_subclass(self):
        qs = self._visible_qs(self.owner).with_cached_count()
        self.assertIsInstance(qs, CachedCountAnnotationQuerySet)

    def test_count_correct_on_miss(self):
        qs = self._visible_qs(self.owner).with_cached_count()
        self.assertEqual(qs.count(), 3)

    def test_count_served_stale_within_ttl(self):
        # Warm the cache.
        self.assertEqual(self._visible_qs(self.owner).with_cached_count().count(), 3)

        # Add a row; a fresh cached queryset with the SAME filters keys to the
        # same SQL and must serve the stale (cached) value, proving no re-COUNT.
        Annotation.objects.create(
            raw_text="a3",
            document=self.doc,
            annotation_label=self.label,
            creator=self.owner,
        )
        self.assertEqual(self._visible_qs(self.owner).with_cached_count().count(), 3)

        # After invalidation the live count is reflected.
        cache.clear()
        self.assertEqual(self._visible_qs(self.owner).with_cached_count().count(), 4)

    def test_uncached_queryset_is_always_live(self):
        # The plain (non-cached) queryset must NOT be affected by the cache.
        self.assertEqual(self._visible_qs(self.owner).count(), 3)
        Annotation.objects.create(
            raw_text="a4",
            document=self.doc,
            annotation_label=self.label,
            creator=self.owner,
        )
        self.assertEqual(self._visible_qs(self.owner).count(), 4)

    def test_count_keys_per_user(self):
        # The owner sees 3; another user (no access to a private doc) sees 0.
        # Distinct SQL → distinct cache keys → no collision.
        self.assertEqual(self._visible_qs(self.owner).with_cached_count().count(), 3)
        self.assertEqual(self._visible_qs(self.other).with_cached_count().count(), 0)

    def test_cached_count_survives_clone(self):
        # graphene slices the queryset (a clone) before reading totalCount;
        # the cached-count behaviour must survive select_related/filter chains.
        qs = (
            self._visible_qs(self.owner)
            .with_cached_count()
            .select_related("annotation_label")
            .filter(structural=False)
        )
        self.assertIsInstance(qs, CachedCountAnnotationQuerySet)
        self.assertEqual(qs.count(), 3)

    def test_cache_backend_failure_degrades_to_live_count(self):
        # A cache-backend outage must NOT break the browse page: count() falls
        # back to a live COUNT rather than propagating the cache error.
        qs = self._visible_qs(self.owner).with_cached_count()
        with patch(
            "django.core.cache.cache.get", side_effect=Exception("redis down")
        ), patch("django.core.cache.cache.set", side_effect=Exception("redis down")):
            self.assertEqual(qs.count(), 3)

    def test_zero_ttl_bypasses_cache(self):
        # An unconfigured TTL (<= 0) must behave like a plain queryset: always
        # live, never written to the cache (guards against caching forever
        # under LocMemCache).
        qs = self._visible_qs(self.owner).with_cached_count()
        qs._count_cache_ttl = 0
        with patch("django.core.cache.cache.set") as mock_set:
            self.assertEqual(qs.count(), 3)
            mock_set.assert_not_called()
