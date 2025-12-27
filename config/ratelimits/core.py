"""
Core rate limiting utilities shared between GraphQL and WebSocket.

This module provides common functions for parsing rate strings, formatting
error messages, and other shared rate limiting logic.
"""

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

    Supported periods:
    - s: seconds
    - m: minutes
    - h: hours
    - d: days

    Args:
        rate: Rate string (e.g., "10/m" for 10 per minute)

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
    """
    Convert period in seconds to human-readable name.

    Args:
        period_seconds: Period in seconds

    Returns:
        Human-readable period name (e.g., "minute")
    """
    return PERIOD_NAMES.get(period_seconds, "period")


def period_char_to_name(period_char: str) -> str:
    """
    Convert period character to human-readable name.

    Args:
        period_char: Period character (s, m, h, d)

    Returns:
        Human-readable period name (e.g., "minute")
    """
    return PERIOD_CHAR_NAMES.get(period_char.lower(), "period")


def format_rate_limit_message(rate: str) -> str:
    """
    Format a rate limit exceeded message.

    Args:
        rate: Rate string (e.g., "10/m")

    Returns:
        Human-readable error message
    """
    try:
        count, period_seconds = parse_rate(rate)
        period_name = period_to_name(period_seconds)
        return f"Limit exceeded: Max {count} requests per {period_name}. Please try again later."
    except ValueError:
        return "Rate limit exceeded. Please try again later."


def apply_multiplier_to_rate(rate: str, multiplier: float) -> str:
    """
    Apply a multiplier to a rate string.

    Args:
        rate: Rate string (e.g., "10/m")
        multiplier: Multiplier to apply (e.g., 2.0 for double)

    Returns:
        New rate string with multiplied count
    """
    parts = rate.split("/")
    if len(parts) != 2:
        return rate

    try:
        count = int(parts[0])
        new_count = max(1, int(count * multiplier))
        return f"{new_count}/{parts[1]}"
    except ValueError:
        return rate
