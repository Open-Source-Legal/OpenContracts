"""Tests for Django system checks registered by the ``agents`` app.

Pins the behaviour of :func:`opencontractserver.agents.checks.check_privacy_filter_api_key`
(``agents.W001``), which surfaces the "PRIVACY_FILTER_URL set but
PRIVACY_FILTER_API_KEY empty" misconfiguration at startup.
"""

from __future__ import annotations

from django.core.checks import Tags
from django.test import SimpleTestCase, override_settings

from opencontractserver.agents.checks import check_privacy_filter_api_key


class CheckPrivacyFilterApiKeyTests(SimpleTestCase):
    """Verify all four (URL set | URL unset) × (key set | key unset) cases."""

    @override_settings(
        PRIVACY_FILTER_URL="http://privacy_filter:8000",
        PRIVACY_FILTER_API_KEY="",
    )
    def test_warns_when_url_set_without_key(self) -> None:
        warnings = check_privacy_filter_api_key(app_configs=None)
        self.assertEqual(len(warnings), 1)
        warning = warnings[0]
        self.assertEqual(warning.id, "agents.W001")
        # The hint must be load-bearing operator guidance.
        self.assertIsNotNone(warning.hint)
        assert warning.hint is not None  # narrow for mypy
        self.assertIn("PRIVACY_FILTER_API_KEY", warning.hint)
        # Message names both env vars so grep'ing the startup output is useful.
        self.assertIn("PRIVACY_FILTER_URL", warning.msg)
        self.assertIn("PRIVACY_FILTER_API_KEY", warning.msg)

    @override_settings(
        PRIVACY_FILTER_URL="http://privacy_filter:8000",
        PRIVACY_FILTER_API_KEY="dev-only-not-secret",
    )
    def test_silent_when_both_set(self) -> None:
        self.assertEqual(check_privacy_filter_api_key(app_configs=None), [])

    @override_settings(
        PRIVACY_FILTER_URL="",
        PRIVACY_FILTER_API_KEY="",
    )
    def test_silent_when_both_unset(self) -> None:
        # Default-disabled state: opt-in service not wired in this deploy.
        self.assertEqual(check_privacy_filter_api_key(app_configs=None), [])

    @override_settings(
        PRIVACY_FILTER_URL="",
        PRIVACY_FILTER_API_KEY="dev-only-not-secret",
    )
    def test_silent_when_only_key_set(self) -> None:
        # Key set without URL is harmless — the runtime client never fires.
        self.assertEqual(check_privacy_filter_api_key(app_configs=None), [])

    @override_settings(
        PRIVACY_FILTER_URL="   http://privacy_filter:8000   ",
        PRIVACY_FILTER_API_KEY="   ",
    )
    def test_whitespace_treated_as_unset(self) -> None:
        # A whitespace-only ``PRIVACY_FILTER_API_KEY`` is the same operational
        # failure mode as an empty string — the privacy-filter container
        # would still start with an empty allowlist. Surface the same warning.
        warnings = check_privacy_filter_api_key(app_configs=None)
        self.assertEqual(len(warnings), 1)
        self.assertEqual(warnings[0].id, "agents.W001")

    def test_registered_with_security_tag(self) -> None:
        """The check must be tagged ``security`` so ``manage.py check
        --tag security`` surfaces it alongside the rest of the security
        family.
        """
        # The decorator stashes its tags on the function as ``tags``.
        self.assertIn(Tags.security, check_privacy_filter_api_key.tags)
