"""
Tests for the ``UserType.displayName`` GraphQL resolver.

Issue: #1557 — Raw OAuth ``provider|sub`` identifiers were leaking into the
leaderboard USER column because resolvers rendered ``user.username`` directly,
and ``username`` is set to the Auth0 ``sub`` claim for social-login users.

These tests pin down the resolution priority and the redaction fallback so
that a future regression cannot quietly re-expose the raw ``sub``.
"""

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
        user = User.objects.create_user(username=username)
        display = _resolve(user)
        # Suffix only — must not contain the provider prefix or the pipe.
        self.assertEqual(display, "user_010643")
        self.assertNotIn("|", display)
        self.assertNotIn("google", display)
        self.assertNotIn(username, display)

    def test_redacts_short_oauth_sub(self):
        """Even short ``sub`` strings should not leak in full."""
        username = "auth0|abcde"
        user = User.objects.create_user(username=username)
        display = _resolve(user)
        self.assertTrue(display.startswith("user_"))
        self.assertNotIn("|", display)

    def test_whitespace_only_name_is_skipped(self):
        """A whitespace-only ``name`` field must not satisfy the priority chain."""
        user = User.objects.create_user(
            username="auth0|abcdef0123456789",
            name="   ",
            given_name="Ada",
            family_name="Lovelace",
        )
        self.assertEqual(_resolve(user), "Ada Lovelace")

    def test_partial_split_name_does_not_leave_stray_whitespace(self):
        """Only ``family_name`` set — rendered output should be trimmed."""
        user = User.objects.create_user(
            username="auth0|abc",
            family_name="Lovelace",
        )
        self.assertEqual(_resolve(user), "Lovelace")
