"""
Tests for the ``UserType.displayName`` GraphQL resolver.

Issue: #1557 — Raw OAuth ``provider|sub`` identifiers were leaking into the
leaderboard USER column because resolvers rendered ``user.username`` directly,
and ``username`` is set to the Auth0 ``sub`` claim for social-login users.

These tests pin down the resolution priority and the redaction fallback so
that a future regression cannot quietly re-expose the raw ``sub``.
"""

from typing import Any, Optional

from django.contrib.auth import get_user_model
from django.test import TestCase

from config.graphql.user_types import UserType

User = get_user_model()


def _resolve(user) -> str:
    """Invoke ``UserType.resolve_display_name`` against a real ``User`` row.

    The resolver is a plain method so we don't need a request/info object —
    passing ``None`` keeps the test focused on the resolution priority.
    """
    return UserType.resolve_display_name(user, None)


def _resolve_email(user, info) -> Optional[str]:
    """Invoke ``UserType.resolve_email`` against a real ``User`` row.

    ``UserType`` is a ``DjangoObjectType`` so its ``self`` is the user model
    at runtime — the cast keeps mypy happy without a per-call ignore.
    """
    return UserType.resolve_email(user, info)


class DisplayNameResolverTestCase(TestCase):
    """Pin down the resolution priority and redaction guarantees."""

    def test_uses_name_when_present(self):
        user = User.objects.create_user(
            username="google-oauth2|114688257717759010643",
            name="Jane Doe",
            given_name="Jane",
            family_name="Doe",
            first_name="Jane",
            last_name="Doe",
        )
        self.assertEqual(_resolve(user), "Jane Doe")

    def test_falls_back_to_given_and_family_when_name_blank(self):
        user = User.objects.create_user(
            username="auth0|69a95a1f877f485f61aed0c4",
            name="",
            given_name="Ada",
            family_name="Lovelace",
            first_name="ignored",
            last_name="ignored",
        )
        self.assertEqual(_resolve(user), "Ada Lovelace")

    def test_falls_back_to_given_only(self):
        user = User.objects.create_user(
            username="auth0|abcdef0123456789",
            given_name="Ada",
        )
        self.assertEqual(_resolve(user), "Ada")

    def test_falls_back_to_first_and_last(self):
        user = User.objects.create_user(
            username="github|987654321",
            first_name="Grace",
            last_name="Hopper",
        )
        self.assertEqual(_resolve(user), "Grace Hopper")

    def test_uses_username_when_not_oauth_sub(self):
        """Local-auth usernames (no ``|`` separator) pass through unchanged."""
        user = User.objects.create_user(username="alice")
        self.assertEqual(_resolve(user), "alice")

    def test_redacts_oauth_sub_when_no_profile_fields(self):
        """Raw OAuth ``sub`` MUST never be returned — only a redacted suffix."""
        username = "google-oauth2|114688257717759010643"
        user = User.objects.create_user(username=username, is_social_user=True)
        display = _resolve(user)
        # Suffix only — must not contain the provider prefix or the pipe.
        self.assertEqual(display, "user_010643")
        self.assertNotIn("|", display)
        self.assertNotIn("google", display)
        self.assertNotIn(username, display)

    def test_redacts_short_oauth_sub(self):
        """Even short ``sub`` strings should not leak the provider/separator.

        Invariant: when the ``sub`` is shorter than
        ``OAUTH_SUB_DISPLAY_SUFFIX_LENGTH``, the entire ``sub`` is used —
        intentionally, because Python's ``str[-N:]`` returns the whole
        string when ``N`` exceeds its length. The separator and provider
        prefix are still stripped via ``rsplit("|", 1)``.
        """
        from opencontractserver.constants.auth import OAUTH_SUB_DISPLAY_SUFFIX_LENGTH

        sub = "abcde"
        self.assertLess(
            len(sub),
            OAUTH_SUB_DISPLAY_SUFFIX_LENGTH,
            "Test premise: sub must be shorter than the suffix length to "
            "exercise the whole-sub fallback.",
        )
        username = f"auth0|{sub}"
        user = User.objects.create_user(username=username, is_social_user=True)
        display = _resolve(user)
        self.assertEqual(display, f"user_{sub}")
        self.assertNotIn("|", display)

    def test_does_not_redact_local_username_with_pipe(self):
        """Local users (``is_social_user=False``) keep their ``|``-containing
        username verbatim — ``UserUnicodeUsernameValidator`` allows ``|``,
        so a local user named ``alice|admin`` is legitimate and the
        OAuth-sub redaction must not fire."""
        user = User.objects.create_user(username="alice|admin", is_social_user=False)
        self.assertEqual(_resolve(user), "alice|admin")

    def test_whitespace_only_name_is_skipped(self):
        """A whitespace-only ``name`` field must not satisfy the priority chain."""
        user = User.objects.create_user(
            username="auth0|abcdef0123456789",
            name="   ",
            given_name="Ada",
            family_name="Lovelace",
        )
        self.assertEqual(_resolve(user), "Ada Lovelace")

    def test_whitespace_only_given_and_family_are_skipped(self):
        """Whitespace-only ``given_name``/``family_name`` must not satisfy the chain."""
        user = User.objects.create_user(
            username="auth0|abcdef0123456789",
            given_name="   ",
            family_name="\t\n",
            first_name="Grace",
            last_name="Hopper",
        )
        self.assertEqual(_resolve(user), "Grace Hopper")

    def test_partial_split_name_does_not_leave_stray_whitespace(self):
        """Only ``family_name`` set — rendered output should be trimmed."""
        user = User.objects.create_user(
            username="auth0|abc",
            family_name="Lovelace",
        )
        self.assertEqual(_resolve(user), "Lovelace")


class _FakeRequest:
    """Minimal stand-in for ``info.context`` carrying just ``user``."""

    def __init__(self, user) -> None:
        self.user = user


class _FakeInfo:
    """Minimal stand-in for ``graphene.ResolveInfo`` carrying just ``context``."""

    def __init__(self, user) -> None:
        self.context = _FakeRequest(user)


class EmailResolverTestCase(TestCase):
    """Pin down the email-gating contract: self / superuser only.

    Issue: #1557 follow-up — even with the leaderboard query no longer
    selecting ``email``, ``DjangoObjectType`` would auto-expose the field
    to any client that selected it on a public ``user`` subtree. The
    resolver must redact ``email`` for cross-user reads.
    """

    alice: Any
    bob: Any
    admin: Any

    @classmethod
    def setUpTestData(cls) -> None:
        cls.alice = User.objects.create_user(
            username="email-test-alice", email="alice@example.com"
        )
        cls.bob = User.objects.create_user(
            username="email-test-bob", email="bob@example.com"
        )
        cls.admin = User.objects.create_user(
            username="email-test-admin",
            email="admin@example.com",
            is_superuser=True,
            is_staff=True,
        )

    def test_returns_email_for_self_view(self):
        info = _FakeInfo(self.alice)
        self.assertEqual(_resolve_email(self.alice, info), "alice@example.com")

    def test_returns_email_for_superuser_view_of_other(self):
        info = _FakeInfo(self.admin)
        self.assertEqual(_resolve_email(self.bob, info), "bob@example.com")

    def test_redacts_email_when_other_user_views(self):
        info = _FakeInfo(self.alice)
        self.assertIsNone(_resolve_email(self.bob, info))

    def test_redacts_email_for_anonymous_requester(self):
        from django.contrib.auth.models import AnonymousUser

        info = _FakeInfo(AnonymousUser())
        self.assertIsNone(_resolve_email(self.alice, info))

    def test_redacts_email_when_context_user_missing(self):
        """``info.context.user`` may be unset on internal/synthetic resolves."""

        class _ContextNoUser:
            pass

        class _InfoNoUser:
            context = _ContextNoUser()

        self.assertIsNone(_resolve_email(self.alice, _InfoNoUser()))

    def test_returns_none_when_self_email_blank(self):
        """A self-view with no email stored should still redact (return ``None``)."""
        no_email_user = User.objects.create_user(username="noemail", email="")
        info = _FakeInfo(no_email_user)
        self.assertIsNone(_resolve_email(no_email_user, info))
