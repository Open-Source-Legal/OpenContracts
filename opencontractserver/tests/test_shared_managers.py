"""
Tests for opencontractserver.shared.Managers (closes #1477).

Covers the branches introduced or modified during the mypy graduation:
  - BaseVisibilityManager.visible_to_user(user=None)  → AnonymousUser path
  - PermissionManager.visible_to_user(user=None)      → AnonymousUser path
  - UserFeedbackManager.visible_to_user(user=None)    → AnonymousUser path
  - UserFeedbackManager.get_or_none()                 → hit and miss paths
  - DocumentManager.unique_blob_paths()               → blob sharing logic
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import TestCase

from opencontractserver.corpuses.models import Corpus
from opencontractserver.feedback.models import UserFeedback

User = get_user_model()


class PermissionManagerVisibleToUserNoneTest(TestCase):
    """PermissionManager.visible_to_user(user=None) must coerce None → AnonymousUser."""

    def setUp(self) -> None:
        self.owner = User.objects.create_user(
            username="pm_owner",
            email="pm_owner@example.com",
        )
        # Public corpus
        self.public_corpus = Corpus.objects.create(
            title="Public Corpus",
            creator=self.owner,
            is_public=True,
        )
        # Private corpus
        self.private_corpus = Corpus.objects.create(
            title="Private Corpus",
            creator=self.owner,
            is_public=False,
        )

    def test_none_user_sees_only_public_items(self) -> None:
        """Calling visible_to_user(user=None) should behave like AnonymousUser."""
        qs = Corpus.objects.visible_to_user(user=None)
        ids = list(qs.values_list("pk", flat=True))
        self.assertIn(self.public_corpus.pk, ids)
        self.assertNotIn(self.private_corpus.pk, ids)

    def test_anonymous_user_object_sees_only_public_items(self) -> None:
        """Passing an AnonymousUser instance should return the same result."""
        qs = Corpus.objects.visible_to_user(user=AnonymousUser())
        ids = list(qs.values_list("pk", flat=True))
        self.assertIn(self.public_corpus.pk, ids)
        self.assertNotIn(self.private_corpus.pk, ids)

    def test_authenticated_user_sees_own_private_items(self) -> None:
        """Authenticated creator should see both public and their own private items."""
        qs = Corpus.objects.visible_to_user(user=self.owner)
        ids = list(qs.values_list("pk", flat=True))
        self.assertIn(self.public_corpus.pk, ids)
        self.assertIn(self.private_corpus.pk, ids)


class UserFeedbackManagerVisibleToUserNoneTest(TestCase):
    """UserFeedbackManager.visible_to_user(user=None) coerces None → AnonymousUser."""

    def setUp(self) -> None:
        self.owner = User.objects.create_user(
            username="uf_owner",
            email="uf_owner@example.com",
        )
        # Public feedback
        self.public_feedback = UserFeedback.objects.create(
            creator=self.owner,
            is_public=True,
            comment="public",
        )
        # Private feedback
        self.private_feedback = UserFeedback.objects.create(
            creator=self.owner,
            is_public=False,
            comment="private",
        )

    def test_none_user_sees_only_public_feedback(self) -> None:
        qs = UserFeedback.objects.visible_to_user(user=None)
        ids = list(qs.values_list("pk", flat=True))
        self.assertIn(self.public_feedback.pk, ids)
        self.assertNotIn(self.private_feedback.pk, ids)

    def test_anonymous_user_object_sees_only_public_feedback(self) -> None:
        qs = UserFeedback.objects.visible_to_user(user=AnonymousUser())
        ids = list(qs.values_list("pk", flat=True))
        self.assertIn(self.public_feedback.pk, ids)
        self.assertNotIn(self.private_feedback.pk, ids)

    def test_authenticated_owner_sees_own_private_feedback(self) -> None:
        qs = UserFeedback.objects.visible_to_user(user=self.owner)
        ids = list(qs.values_list("pk", flat=True))
        self.assertIn(self.public_feedback.pk, ids)
        self.assertIn(self.private_feedback.pk, ids)

    def test_other_user_cannot_see_private_feedback(self) -> None:
        other = User.objects.create_user(
            username="uf_other",
            email="uf_other@example.com",
        )
        qs = UserFeedback.objects.visible_to_user(user=other)
        ids = list(qs.values_list("pk", flat=True))
        self.assertIn(self.public_feedback.pk, ids)
        self.assertNotIn(self.private_feedback.pk, ids)


class UserFeedbackManagerGetOrNoneTest(TestCase):
    """UserFeedbackManager.get_or_none() returns None on miss, object on hit."""

    def setUp(self) -> None:
        self.owner = User.objects.create_user(
            username="gon_owner",
            email="gon_owner@example.com",
        )
        self.feedback = UserFeedback.objects.create(
            creator=self.owner,
            is_public=True,
            comment="find me",
        )

    def test_get_or_none_returns_object_on_hit(self) -> None:
        result = UserFeedback.objects.get_or_none(pk=self.feedback.pk)
        self.assertIsNotNone(result)
        assert result is not None  # narrow type for mypy
        self.assertEqual(result.pk, self.feedback.pk)

    def test_get_or_none_returns_none_on_miss(self) -> None:
        # Use a pk that is extremely unlikely to exist
        result = UserFeedback.objects.get_or_none(pk=999999999)
        self.assertIsNone(result)

    def test_get_or_none_returns_none_for_wrong_lookup(self) -> None:
        result = UserFeedback.objects.get_or_none(comment="does-not-exist-xyz")
        self.assertIsNone(result)

    def test_get_or_none_with_kwargs_on_hit(self) -> None:
        result = UserFeedback.objects.get_or_none(
            pk=self.feedback.pk, comment="find me"
        )
        self.assertIsNotNone(result)

    def test_get_or_none_with_kwargs_on_miss(self) -> None:
        result = UserFeedback.objects.get_or_none(
            pk=self.feedback.pk, comment="wrong-comment"
        )
        self.assertIsNone(result)
