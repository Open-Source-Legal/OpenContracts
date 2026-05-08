"""
Tests for ``Corpus.user_can_moderate`` (issue #1450, cluster 3).

The helper consolidates the inline
``user.is_superuser or corpus.creator == user or
corpus.moderators.filter(user=user).exists()`` pattern from
``config/graphql/conversation_queries.py``. These tests pin the existing
behavior (superuser, creator, ANY designated moderator regardless of
the ``permissions`` list) so the helper is a faithful drop-in replacement
and does not silently change moderation visibility semantics.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import TestCase

from opencontractserver.conversations.models import CorpusModerator
from opencontractserver.corpuses.models import Corpus

User = get_user_model()


class CorpusUserCanModerateTests(TestCase):
    """Pin the canonical "is_superuser OR creator OR any moderator" matrix."""

    def setUp(self) -> None:
        self.owner = User.objects.create_user(username="owner", password="pw")
        self.outsider = User.objects.create_user(username="outsider", password="pw")
        self.moderator_with_perms = User.objects.create_user(
            username="mod_perms", password="pw"
        )
        self.moderator_no_perms = User.objects.create_user(
            username="mod_no_perms", password="pw"
        )
        self.superuser = User.objects.create_superuser(
            username="root", password="pw", email="root@example.com"
        )

        self.corpus = Corpus.objects.create(title="Test Corpus", creator=self.owner)

        CorpusModerator.objects.create(
            corpus=self.corpus,
            user=self.moderator_with_perms,
            permissions=["lock_threads"],
            assigned_by=self.owner,
            creator=self.owner,
        )
        # Empty permissions list — still counts for the *view-moderation*
        # check (see helper docstring); diverges from
        # ``Conversation.can_moderate`` and is tracked separately.
        CorpusModerator.objects.create(
            corpus=self.corpus,
            user=self.moderator_no_perms,
            permissions=[],
            assigned_by=self.owner,
            creator=self.owner,
        )

    def test_superuser_can_moderate(self) -> None:
        self.assertTrue(self.corpus.user_can_moderate(self.superuser))

    def test_creator_can_moderate(self) -> None:
        self.assertTrue(self.corpus.user_can_moderate(self.owner))

    def test_designated_moderator_can_moderate(self) -> None:
        self.assertTrue(self.corpus.user_can_moderate(self.moderator_with_perms))

    def test_moderator_with_empty_permissions_still_counts(self) -> None:
        """
        Match the existing ``conversation_queries.py`` behavior: a row in
        ``CorpusModerator`` with an empty ``permissions`` list still
        grants access. The helper exists to consolidate that exact
        pattern; tightening it would be a behavior change handled in a
        follow-up PR.
        """
        self.assertTrue(self.corpus.user_can_moderate(self.moderator_no_perms))

    def test_outsider_cannot_moderate(self) -> None:
        self.assertFalse(self.corpus.user_can_moderate(self.outsider))

    def test_anonymous_user_cannot_moderate(self) -> None:
        self.assertFalse(self.corpus.user_can_moderate(AnonymousUser()))

    def test_none_user_cannot_moderate(self) -> None:
        self.assertFalse(self.corpus.user_can_moderate(None))

    def test_moderator_on_other_corpus_does_not_leak(self) -> None:
        """
        A user moderating a *different* corpus must not be granted
        moderation rights here — the relation must be scoped to ``self``.
        """
        other_corpus = Corpus.objects.create(
            title="Other Corpus", creator=self.outsider
        )
        cross_user = User.objects.create_user(username="cross", password="pw")
        CorpusModerator.objects.create(
            corpus=other_corpus,
            user=cross_user,
            permissions=["lock_threads"],
            assigned_by=self.outsider,
            creator=self.outsider,
        )
        self.assertFalse(self.corpus.user_can_moderate(cross_user))
