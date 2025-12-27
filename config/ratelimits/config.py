"""
Unified rate limit configuration for GraphQL and WebSocket.

This module provides a single RateLimits configuration class that serves
both GraphQL mutations/queries and WebSocket connections/messages.
"""

from django.conf import settings


class _RateLimits:
    """
    Unified rate limit configurations for all operation types.

    Provides default rate limits that can be overridden via Django settings.
    Access limits as attributes: RateLimits.WRITE_MEDIUM, RateLimits.WS_CONNECT, etc.
    """

    _defaults = {
        # ============================================================
        # GraphQL Rate Limits
        # ============================================================
        # Authentication operations
        "AUTH_LOGIN": "5/m",  # 5 login attempts per minute
        "AUTH_REGISTER": "3/m",  # 3 registration attempts per minute
        "AUTH_PASSWORD_RESET": "3/h",  # 3 password reset requests per hour
        # Read operations
        "READ_LIGHT": "100/m",  # Light queries (single object fetches)
        "READ_MEDIUM": "30/m",  # Medium queries (filtered lists)
        "READ_HEAVY": "10/m",  # Heavy queries (complex aggregations)
        # Write operations
        "WRITE_LIGHT": "30/m",  # Light mutations (updates, deletes)
        "WRITE_MEDIUM": "10/m",  # Medium mutations (create with validation)
        "WRITE_HEAVY": "5/m",  # Heavy mutations (bulk operations, file uploads)
        # AI/Analysis operations
        "AI_ANALYSIS": "5/m",  # AI analysis requests
        "AI_EXTRACT": "10/m",  # AI extraction requests
        "AI_QUERY": "20/m",  # AI query requests
        # Export/Import operations
        "EXPORT": "5/h",  # Export operations
        "IMPORT": "10/h",  # Import operations
        # Admin operations
        "ADMIN_OPERATION": "100/m",  # Admin operations (higher limit)
        # ============================================================
        # WebSocket Rate Limits
        # ============================================================
        # Connection rate limits
        "WS_CONNECT": "30/m",  # 30 connection attempts per minute
        "WS_CONNECT_ANONYMOUS": "10/m",  # 10 for anonymous users
        # Message rate limits
        "WS_MESSAGE": "60/m",  # 60 messages per minute
        "WS_MESSAGE_ANONYMOUS": "20/m",  # 20 for anonymous users
        # AI query rate limits (for agent consumers)
        "WS_AI_QUERY": "20/m",  # 20 AI queries per minute
        "WS_AI_QUERY_ANONYMOUS": "5/m",  # 5 for anonymous users
    }

    def __init__(self):
        self._cache = {}
        self._load_overrides()

    def _load_overrides(self):
        """Load rate limit overrides from settings."""
        # Support both unified and legacy override settings
        overrides = {}

        # Legacy GraphQL overrides
        graphql_overrides = getattr(settings, "RATE_LIMIT_OVERRIDES", {})
        overrides.update(graphql_overrides)

        # Legacy WebSocket overrides
        ws_overrides = getattr(settings, "WEBSOCKET_RATE_LIMIT_OVERRIDES", {})
        overrides.update(ws_overrides)

        # Unified overrides (takes precedence)
        unified_overrides = getattr(settings, "RATELIMIT_OVERRIDES", {})
        overrides.update(unified_overrides)

        # Cache the final values
        for key, default_value in self._defaults.items():
            self._cache[key] = overrides.get(key, default_value)

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(
                f"'{self.__class__.__name__}' object has no attribute '{name}'"
            )

        # Check cache first
        if name in self._cache:
            return self._cache[name]

        # Fall back to defaults
        if name in self._defaults:
            return self._defaults[name]

        raise AttributeError(
            f"'{self.__class__.__name__}' object has no attribute '{name}'"
        )

    def get(self, name: str, default: str = None) -> str:
        """
        Get a rate limit by name with optional default.

        Args:
            name: Rate limit name (e.g., "WRITE_MEDIUM")
            default: Default value if not found

        Returns:
            Rate limit string
        """
        try:
            return getattr(self, name)
        except AttributeError:
            return default

    def get_ws_rate_for_user(self, rate_type: str, user) -> str:
        """
        Get the appropriate WebSocket rate limit based on user authentication status.

        Args:
            rate_type: Base rate type (e.g., "WS_CONNECT", "WS_MESSAGE")
            user: The user object from scope

        Returns:
            The rate limit string to apply
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
            # Use anonymous rate limit
            anon_type = f"{rate_type}_ANONYMOUS"
            return self.get(anon_type, "10/m")


# Singleton instance - this is the public API
RateLimits = _RateLimits()
