"""
Core rate limiting utilities shared between GraphQL and WebSocket.

Provides common functions for parsing rate strings, formatting
error messages, and applying tier multipliers.
"""

# WebSocket close reason max length (per spec, close reasons must be ≤123 bytes)
WS_CLOSE_REASON_MAX_BYTES = 123

# Period mapping: character -> seconds
PERIOD_SECONDS = {
    "s": 1,
    "m": 60,
    "h": 3600,
    "d": 86400,
}

# Period mapping: seconds -> human-readable name
PERIOD_NAMES = {
    1: "second",
    60: "minute",
    3600: "hour",
    86400: "day",
}

# Period mapping: character -> human-readable name
PERIOD_CHAR_NAMES = {
    "s": "second",
    "m": "minute",
    "h": "hour",
    "d": "day",
}


def parse_rate(rate: str) -> tuple[int, int]:
    """
    Parse a rate string like "10/m" into (count, seconds).

    Supported periods: s (seconds), m (minutes), h (hours), d (days).

    Returns:
        Tuple of (max_count, period_in_seconds)

    Raises:
        ValueError: If rate format is invalid
    """
    parts = rate.split("/")
    if len(parts) != 2:
        raise ValueError(f"Invalid rate format: {rate}")

    try:
        count = int(parts[0])
    except ValueError:
        raise ValueError(f"Invalid count in rate: {rate}")

    period_char = parts[1].lower()
    period_seconds = PERIOD_SECONDS.get(period_char)

    if period_seconds is None:
        raise ValueError(f"Invalid period in rate: {rate}")

    return count, period_seconds


def period_to_name(period_seconds: int) -> str:
    """Convert period in seconds to human-readable name."""
    return PERIOD_NAMES.get(period_seconds, "period")


def format_rate_limit_message(rate: str) -> str:
    """Format a human-readable rate limit exceeded message."""
    try:
        count, period_seconds = parse_rate(rate)
        period_name = period_to_name(period_seconds)
        return f"Limit exceeded: Max {count} requests per {period_name}. Please try again later."
    except ValueError:
        return "Rate limit exceeded. Please try again later."


def apply_multiplier_to_rate(rate: str, multiplier: float) -> str:
    """Apply a multiplier to a rate string (e.g. "10/m" * 2.0 -> "20/m")."""
    parts = rate.split("/")
    if len(parts) != 2:
        return rate

    try:
        count = int(parts[0])
        new_count = max(1, int(count * multiplier))
        return f"{new_count}/{parts[1]}"
    except ValueError:
        return rate
