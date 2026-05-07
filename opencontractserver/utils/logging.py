"""
Logging utilities for OpenContracts.

Provides helper functions for safe logging that avoid exposing sensitive data.
"""

from typing import Any

# Keys that should be redacted in logs (case-insensitive partial match)
# Using specific patterns to avoid false positives (e.g., "keyboard", "hockey")
SENSITIVE_KEY_PATTERNS = (
    "_key",  # Matches api_key, secret_key, but not keyboard
    "apikey",  # Matches apikey, ApiKey (no underscore variant)
    "_secret",  # Matches client_secret, app_secret
    "secret_",  # Matches secret_key, secret_id
    "password",
    "_token",  # Matches access_token, auth_token
    "token_",  # Matches token_secret, token_id
    "credential",
    "authorization",
    "bearer",  # Common auth header value prefix
)


def redact_sensitive_kwargs(kwargs: dict[str, Any]) -> dict[str, Any]:
    """
    Recursively redact sensitive values from a kwargs dict before logging.

    Matches keys containing common sensitive patterns like 'api_key', 'secret',
    'password', 'token', etc. (case-insensitive). Handles nested dictionaries
    and lists of dictionaries.

    Args:
        kwargs: Dictionary of keyword arguments that may contain sensitive values.

    Returns:
        A new dictionary with sensitive values replaced with '***'.

    Example:
        >>> redact_sensitive_kwargs({"api_key": "sk-123", "verbose": True})
        {"api_key": "***", "verbose": True}

        >>> redact_sensitive_kwargs({"config": {"api_key": "sk-123"}})
        {"config": {"api_key": "***"}}
    """
    result: dict[str, Any] = {}
    for k, v in kwargs.items():
        if any(pattern in k.lower() for pattern in SENSITIVE_KEY_PATTERNS):
            result[k] = "***"
        elif isinstance(v, dict):
            result[k] = redact_sensitive_kwargs(v)
        elif isinstance(v, list):
            result[k] = [
                redact_sensitive_kwargs(item) if isinstance(item, dict) else item
                for item in v
            ]
        else:
            result[k] = v
    return result
