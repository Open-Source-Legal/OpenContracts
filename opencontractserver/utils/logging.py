"""
Logging utilities for OpenContracts.

Provides helper functions for safe logging that avoid exposing sensitive data.
"""

import dataclasses
from collections.abc import Iterable
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


def _is_dataclass_instance(value: Any) -> bool:
    """A dataclass *instance* (a component's ``Settings``), not the class."""
    return dataclasses.is_dataclass(value) and not isinstance(value, type)


def _is_redactable(value: Any) -> bool:
    """A nested value that is itself redacted rather than copied through."""
    return isinstance(value, dict) or _is_dataclass_instance(value)


def _items(mapping: Any) -> Iterable[tuple[str, Any]]:
    """``(name, value)`` pairs of a dataclass instance or any ``.items()`` mapping."""
    if _is_dataclass_instance(mapping):
        return ((f.name, getattr(mapping, f.name)) for f in dataclasses.fields(mapping))
    return mapping.items()


def redact_sensitive_kwargs(kwargs: Any) -> dict[str, Any]:
    """
    Recursively redact sensitive values from a mapping before logging.

    Accepts a dict or a dataclass instance (e.g. a pipeline component's
    ``Settings``), and returns a plain dict either way. Matches keys containing
    common sensitive patterns like 'api_key', 'secret', 'password', 'token',
    etc. (case-insensitive). Handles nested dicts / dataclasses and lists of
    them.

    Args:
        kwargs: Dict or dataclass instance that may contain sensitive values.

    Returns:
        A new dictionary with sensitive values replaced with '***'.

    Example:
        >>> redact_sensitive_kwargs({"api_key": "sk-123", "verbose": True})
        {"api_key": "***", "verbose": True}

        >>> redact_sensitive_kwargs({"config": {"api_key": "sk-123"}})
        {"config": {"api_key": "***"}}
    """
    result: dict[str, Any] = {}
    for k, v in _items(kwargs):
        if any(pattern in k.lower() for pattern in SENSITIVE_KEY_PATTERNS):
            result[k] = "***"
        elif _is_redactable(v):
            result[k] = redact_sensitive_kwargs(v)
        elif isinstance(v, list):
            result[k] = [
                redact_sensitive_kwargs(item) if _is_redactable(item) else item
                for item in v
            ]
        else:
            result[k] = v
    return result
