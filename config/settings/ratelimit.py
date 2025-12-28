"""
Rate limiting configuration for OpenContracts.

This module contains settings for django-ratelimit integration.
"""

import os

import environ

env = environ.Env()

# Django-ratelimit settings
RATELIMIT_ENABLE = True  # Enable rate limiting globally
RATELIMIT_USE_CACHE = "default"  # Use default cache backend
RATELIMIT_VIEW = (
    "config.graphql.ratelimits.RateLimitExceeded"  # Custom rate limit exceeded view
)

# Whether to disable rate limiting
# By default, disable in test environments unless explicitly enabled
RATELIMIT_DISABLE = env.bool("RATELIMIT_DISABLE", default=False)

# Rate limit key prefix (useful for multi-tenant setups)
RATELIMIT_KEY_PREFIX = "rl"

# Whether to fail "open" (allow requests) or "closed" (deny requests) when cache is unavailable
RATELIMIT_FAIL_OPEN = False

# Custom rate limits can be overridden via environment variables
# Example: RATELIMIT_AUTH_LOGIN=10/m would set login rate to 10 per minute
# Override specific rate limits from environment if provided
RATE_LIMIT_OVERRIDES = {
    "AUTH_LOGIN": os.environ.get("RATELIMIT_AUTH_LOGIN"),
    "AUTH_REGISTER": os.environ.get("RATELIMIT_AUTH_REGISTER"),
    "AUTH_PASSWORD_RESET": os.environ.get("RATELIMIT_AUTH_PASSWORD_RESET"),
    "READ_LIGHT": os.environ.get("RATELIMIT_READ_LIGHT"),
    "READ_MEDIUM": os.environ.get("RATELIMIT_READ_MEDIUM"),
    "READ_HEAVY": os.environ.get("RATELIMIT_READ_HEAVY"),
    "WRITE_LIGHT": os.environ.get("RATELIMIT_WRITE_LIGHT"),
    "WRITE_MEDIUM": os.environ.get("RATELIMIT_WRITE_MEDIUM"),
    "WRITE_HEAVY": os.environ.get("RATELIMIT_WRITE_HEAVY"),
    "AI_ANALYSIS": os.environ.get("RATELIMIT_AI_ANALYSIS"),
    "AI_EXTRACT": os.environ.get("RATELIMIT_AI_EXTRACT"),
    "AI_QUERY": os.environ.get("RATELIMIT_AI_QUERY"),
    "EXPORT": os.environ.get("RATELIMIT_EXPORT"),
    "IMPORT": os.environ.get("RATELIMIT_IMPORT"),
    "ADMIN_OPERATION": os.environ.get("RATELIMIT_ADMIN_OPERATION"),
}

# Remove None values
RATE_LIMIT_OVERRIDES = {k: v for k, v in RATE_LIMIT_OVERRIDES.items() if v is not None}

# IP address extraction for rate limiting behind proxies
# This is important when running behind Traefik or other reverse proxies
RATELIMIT_IP_META_KEY = "HTTP_X_FORWARDED_FOR"

# Whether to group IPv6 addresses by subnet for rate limiting
# This prevents users from bypassing rate limits by using different IPv6 addresses
# in the same subnet
RATELIMIT_IPV6_MASK = 64  # Group by /64 subnet

# WebSocket rate limiting configuration
# These limits apply to WebSocket connections and messages
# NOTE: Default values are defined in config/ratelimits/config.py (single source of truth)
# Only set here if environment variables are explicitly provided
WEBSOCKET_RATE_LIMIT_OVERRIDES = {
    # Connection rate limits - how often users can establish new WebSocket connections
    "WS_CONNECT": os.environ.get("RATELIMIT_WS_CONNECT"),
    "WS_CONNECT_ANONYMOUS": os.environ.get("RATELIMIT_WS_CONNECT_ANONYMOUS"),
    # Message rate limits - how many messages can be sent per connection
    "WS_MESSAGE": os.environ.get("RATELIMIT_WS_MESSAGE"),
    "WS_MESSAGE_ANONYMOUS": os.environ.get("RATELIMIT_WS_MESSAGE_ANONYMOUS"),
    # AI query rate limits - specific limits for AI agent queries
    "WS_AI_QUERY": os.environ.get("RATELIMIT_WS_AI_QUERY"),
    "WS_AI_QUERY_ANONYMOUS": os.environ.get("RATELIMIT_WS_AI_QUERY_ANONYMOUS"),
}

# Remove None values - only overrides explicitly set via environment will be applied
WEBSOCKET_RATE_LIMIT_OVERRIDES = {
    k: v for k, v in WEBSOCKET_RATE_LIMIT_OVERRIDES.items() if v is not None
}
