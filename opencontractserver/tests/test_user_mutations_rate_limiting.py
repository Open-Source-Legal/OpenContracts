"""Regression tests for the tokenAuth / updateMe rate-limiting gap.

Every other ported mutation module in the graphene->strawberry migration
decorates its writes with ``graphql_ratelimit``/``graphql_ratelimit_dynamic``,
but ``config/graphql/user_mutations.py`` had none at all — flagged by PR #2139
review. ``tokenAuth`` is a natural credential-stuffing target (the Django-admin
login view already guards the identical operation with
``RateLimits.AUTH_LOGIN``); ``updateMe`` is a plain authenticated write like
any other mutation in this codebase, all of which are rate-limited.

These tests call the mutation resolvers directly with a context object that
has both ``.user`` and ``.META`` (required for the rate-limit key extraction —
see ``config/ratelimit/decorators.py::_graphql_rate_limit_check``, which
silently skips rate limiting when ``.META`` is absent, as most lightweight
test contexts elsewhere in this suite are). ``config.ratelimit.engine.time``
is mocked to make the fixed-window limit deterministic instead of depending on
wall-clock timing.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from graphql_jwt.exceptions import JSONWebTokenError

from config.graphql.user_mutations import m_token_auth, m_update_me
from config.ratelimit.decorators import RateLimitExceeded
from config.ratelimit.rates import parse_rate

User = get_user_model()


class _RateLimitContext:
    """Minimal context exposing ``.user`` and ``.META`` (IP source)."""

    def __init__(self, user, ip: str = "203.0.113.5"):
        self.user = user
        self.META = {"REMOTE_ADDR": ip}
        self.jwt_cookie = False


class _Info:
    def __init__(self, context):
        self.context = context


@override_settings(RATELIMIT_DISABLE=False)
class TokenAuthRateLimitTestCase(TestCase):
    """``tokenAuth`` is IP-rate-limited under ``RateLimits.AUTH_LOGIN``."""

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(username="rl_bob", password="12345678")

    def tearDown(self):
        cache.clear()

    @patch("config.ratelimit.engine.time")
    def test_blocks_after_auth_login_limit(self, mock_time):
        mock_time.time.return_value = 1_000_000.0
        limit, _ = parse_rate("5/m")  # RateLimits.AUTH_LOGIN

        info = _Info(_RateLimitContext(user=None))
        for _ in range(limit):
            result = m_token_auth(
                info, username="rl_bob", password="12345678"  # type: ignore[arg-type]
            )
            assert result is not None
            self.assertTrue(result.token)

        with self.assertRaises(RateLimitExceeded):
            m_token_auth(info, username="rl_bob", password="12345678")  # type: ignore[arg-type]

    @patch("config.ratelimit.engine.time")
    def test_rate_limit_is_keyed_by_ip_not_by_success(self, mock_time):
        # A run of failed logins from the same IP must still count against
        # the limit — the gate runs before authentication is attempted, so
        # brute-forcing wrong passwords cannot dodge the throttle.
        mock_time.time.return_value = 1_000_000.0
        limit, _ = parse_rate("5/m")

        info = _Info(_RateLimitContext(user=None))
        for _ in range(limit):
            with self.assertRaises(JSONWebTokenError):
                m_token_auth(
                    info,  # type: ignore[arg-type]
                    username="rl_bob",
                    password="wrong-password",
                )

        with self.assertRaises(RateLimitExceeded):
            m_token_auth(info, username="rl_bob", password="12345678")  # type: ignore[arg-type]

    @patch("config.ratelimit.engine.time")
    def test_distinct_ips_get_independent_limits(self, mock_time):
        mock_time.time.return_value = 1_000_000.0
        limit, _ = parse_rate("5/m")

        info_a = _Info(_RateLimitContext(user=None, ip="203.0.113.1"))
        info_b = _Info(_RateLimitContext(user=None, ip="203.0.113.2"))

        for _ in range(limit):
            m_token_auth(info_a, username="rl_bob", password="12345678")  # type: ignore[arg-type]
        with self.assertRaises(RateLimitExceeded):
            m_token_auth(info_a, username="rl_bob", password="12345678")  # type: ignore[arg-type]

        # A different IP is unaffected by info_a's exhausted bucket.
        result = m_token_auth(
            info_b, username="rl_bob", password="12345678"  # type: ignore[arg-type]
        )
        assert result is not None
        self.assertTrue(result.token)


@override_settings(RATELIMIT_DISABLE=False)
class UpdateMeRateLimitTestCase(TestCase):
    """``updateMe`` is rate-limited under the ``WRITE_LIGHT`` tier."""

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(username="rl_alice", password="pw")
        # New users default to usage-capped (opencontractserver/users/models.py),
        # which halves the tier-adjusted rate on top of the 2x authenticated
        # multiplier — uncap so this test pins the plain authenticated tier.
        self.user.is_usage_capped = False
        self.user.save(update_fields=["is_usage_capped"])

    def tearDown(self):
        cache.clear()

    @patch("config.ratelimit.engine.time")
    def test_blocks_after_write_light_authenticated_limit(self, mock_time):
        mock_time.time.return_value = 1_000_000.0
        # WRITE_LIGHT is "30/m"; an uncapped authenticated user gets the 2x
        # tier multiplier (get_tier_adjusted_rate), so the real ceiling is 60.
        base_limit, _ = parse_rate("30/m")
        limit = base_limit * 2

        info = _Info(_RateLimitContext(user=self.user))
        for _ in range(limit):
            result = m_update_me(info, name="Alice")  # type: ignore[arg-type]
            assert result is not None
            self.assertTrue(result.ok)

        with self.assertRaises(RateLimitExceeded):
            m_update_me(info, name="Alice")  # type: ignore[arg-type]

    def test_unauthenticated_call_is_rejected_before_rate_limiting(self):
        # PermissionDenied, not RateLimitExceeded — the login_required check
        # still runs first, matching every other ported mutation.
        from config.graphql.core.auth import PermissionDenied

        info = _Info(MagicMock(user=MagicMock(is_authenticated=False)))
        with self.assertRaises(PermissionDenied):
            m_update_me(info, name="Alice")  # type: ignore[arg-type]
