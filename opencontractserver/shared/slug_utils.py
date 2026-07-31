from __future__ import annotations

import re
from collections.abc import Iterable

from django.conf import settings
from django.db.models import QuerySet

ALLOWED_SLUG_PATTERN = re.compile(r"[^A-Za-z0-9-]+")


def get_reserved_user_slugs() -> set[str]:
    """Return the set of reserved top-level user slugs from settings.

    Defaults are provided if the project setting is absent.
    """
    default_reserved = {
        "corpuses",
        "corpus",
        "documents",
        "document",
        "settings",
        "login",
        "logout",
        "admin",
        "api",
        "graphql",
    }
    configured: Iterable[str] = getattr(
        settings, "RESERVED_USER_SLUGS", default_reserved
    )
    return set(configured)


def sanitize_slug(value: str, *, max_length: int) -> str:
    """Convert arbitrary text to a case-preserving slug limited to allowed characters.

    Rules:
    - Preserve case (case-sensitive URLs)
    - Replace spaces/underscores with hyphens
    - Remove characters outside [A-Za-z0-9-]
    - Collapse duplicate hyphens
    - Trim leading/trailing hyphens
    - Truncate to max_length
    """
    if value is None:
        value = ""

    # Replace spaces/underscores with hyphens while preserving case
    value = value.replace(" ", "-").replace("_", "-")
    # Strip disallowed characters
    value = ALLOWED_SLUG_PATTERN.sub("", value)
    # Collapse multiple hyphens
    value = re.sub(r"-+", "-", value)
    # Trim hyphens
    value = value.strip("-")
    # Enforce max length.  Truncation can expose a separator that was not at
    # either edge of the original value (``"a…a tail"`` can become
    # ``"a…a-"``).  Trim once more so callers that later validate/sanitise a
    # generated slug do not silently turn it into a colliding shorter value.
    if max_length and len(value) > max_length:
        value = value[:max_length]
    return value.strip("-")


def generate_unique_slug(
    *,
    base_value: str,
    scope_qs: QuerySet,
    slug_field: str = "slug",
    max_length: int,
    fallback_prefix: str,
) -> str:
    """Generate a unique, case-sensitive slug within a queryset scope.

    Args:
        base_value: Preferred seed value (e.g., title or username)
        scope_qs: QuerySet to check for uniqueness within (use filters for scoping)
        slug_field: Name of the slug field to check within scope
        max_length: Maximum length of the slug
        fallback_prefix: Used if sanitization results in an empty string

    Returns:
        A unique slug string within the given scope.
    """
    base_slug = sanitize_slug(base_value or "", max_length=max_length)
    if not base_slug:
        base_slug = fallback_prefix
        base_slug = sanitize_slug(base_slug, max_length=max_length)

    candidate = base_slug
    suffix = 2
    while scope_qs.filter(**{slug_field: candidate}).exists():
        # Leave room for hyphen and suffix digits
        trimmed = base_slug[: max(1, max_length - (len(str(suffix)) + 1))]
        candidate = f"{trimmed}-{suffix}"
        suffix += 1

    return candidate


def validate_user_slug_or_raise(slug: str) -> None:
    """Validate a user slug against reserved names and allowed charset.

    Raises ValueError on invalid.
    """
    if not slug:
        raise ValueError("Slug cannot be empty.")
    if ALLOWED_SLUG_PATTERN.search(slug.replace("-", "")):
        # Characters beyond [A-Za-z0-9-] were present
        raise ValueError("Slug contains invalid characters.")
    if slug in get_reserved_user_slugs():
        raise ValueError("Slug is reserved and cannot be used.")
