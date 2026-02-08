"""
Unified rate limit configuration for GraphQL and WebSocket.

Single source of truth for all rate limit defaults. Supports overrides
via Django settings (RATE_LIMIT_OVERRIDES, WEBSOCKET_RATE_LIMIT_OVERRIDES,
and RATELIMIT_OVERRIDES).
"""

from django.conf import settings


class _RateLimits:
    """
    Unified rate limit configuration accessed as singleton attributes.

    Usage:
        from config.ratelimits import RateLimits
        rate = RateLimits.WRITE_MEDIUM   # "10/m"
        rate = RateLimits.WS_CONNECT     # "30/m"
    """

    _defaults = {
        # GraphQL — Authentication
        "AUTH_LOGIN": "5/m",
        "AUTH_REGISTER": "3/m",
        "AUTH_PASSWORD_RESET": "3/h",
        # GraphQL — Read operations
        "READ_LIGHT": "100/m",
        "READ_MEDIUM": "30/m",
        "READ_HEAVY": "10/m",
        # GraphQL — Write operations
        "WRITE_LIGHT": "30/m",
        "WRITE_MEDIUM": "10/m",
        "WRITE_HEAVY": "5/m",
        # GraphQL — AI operations
        "AI_ANALYSIS": "5/m",
        "AI_EXTRACT": "10/m",
        "AI_QUERY": "20/m",
        # GraphQL — Export/Import
        "EXPORT": "5/h",
        "IMPORT": "10/h",
        # GraphQL — Admin
        "ADMIN_OPERATION": "100/m",
        # WebSocket — Connection rate limits
        "WS_CONNECT": "30/m",
        "WS_CONNECT_ANONYMOUS": "10/m",
        # WebSocket — Message rate limits
        "WS_MESSAGE": "60/m",
        "WS_MESSAGE_ANONYMOUS": "20/m",
        # WebSocket — AI query rate limits (for agent consumers)
        "WS_AI_QUERY": "20/m",
        "WS_AI_QUERY_ANONYMOUS": "5/m",
    }

    def __init__(self):
        self._cache = {}
        self._load_overrides()

    def _load_overrides(self):
        """Load rate limit overrides from settings."""
        overrides = {}

        # Legacy GraphQL overrides
        graphql_overrides = getattr(settings, "RATE_LIMIT_OVERRIDES", {})
        overrides.update(graphql_overrides)

        # WebSocket overrides
        ws_overrides = getattr(settings, "WEBSOCKET_RATE_LIMIT_OVERRIDES", {})
        overrides.update(ws_overrides)

        # Unified overrides (highest precedence)
        unified_overrides = getattr(settings, "RATELIMIT_OVERRIDES", {})
        overrides.update(unified_overrides)

        for key, default_value in self._defaults.items():
            self._cache[key] = overrides.get(key, default_value)

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(
                f"'{self.__class__.__name__}' object has no attribute '{name}'"
            )

        if name in self._cache:
            return self._cache[name]

        if name in self._defaults:
            return self._defaults[name]

        raise AttributeError(
            f"'{self.__class__.__name__}' object has no attribute '{name}'"
        )

    def get(self, name: str, default: str = None) -> str:
        """Get a rate limit by name with optional default."""
        try:
            return getattr(self, name)
        except AttributeError:
            return default

    def get_ws_rate_for_user(self, rate_type: str, user) -> str:
        """
        Get the WebSocket rate limit for a user, accounting for authentication
        and tier multipliers.

        For authenticated users, applies tier multiplier to the base rate.
        For anonymous users, returns the _ANONYMOUS variant.
        """
        from config.ratelimits.tiers import get_tier_multiplier, is_user_authenticated

        if is_user_authenticated(user):
            base_rate = self.get(rate_type, "60/m")
            multiplier = get_tier_multiplier(user)
            if multiplier != 1.0:
                from config.ratelimits.core import apply_multiplier_to_rate

                return apply_multiplier_to_rate(base_rate, multiplier)
            return base_rate
        else:
            anon_type = f"{rate_type}_ANONYMOUS"
            return self.get(anon_type, "10/m")


# Singleton instance — the public API
RateLimits = _RateLimits()
