"""
Reddit-style auto-assigned user handle generator.

Generates memorable handles like ``cleverFox`` from a curated word list
(``ADJECTIVES × NOUNS``) and exposes them as a higher-priority branch in the
``UserType.displayName`` GraphQL chain so users without populated Auth0
``name``/``given_name`` fields render with a friendly handle instead of the
redacted ``user_xxxxxx`` fallback.

Format
------
``adjectiveNoun`` (camelCase). On collision a 2-4 digit numeric suffix is
appended (``cleverFox42``). With the default ~56k namespace, suffix promotion
is rare in practice (see ``test_user_handle.py``).

Determinism
-----------
The generator accepts an optional ``random.Random`` instance so tests can pin
output. Default behaviour uses ``random.SystemRandom`` for non-deterministic
selection in production.
"""

from __future__ import annotations

import random
from typing import Optional

from django.db.models import QuerySet

from opencontractserver.users.handle_wordlists import ADJECTIVES, NOUNS

# Tunables. Kept module-level so tests can patch them if the namespace shrinks.
DEFAULT_HANDLE_FIELD = "handle"
# Plain-pair attempts before falling back to numeric-suffixed candidates.
PLAIN_ATTEMPTS = 50
# Numeric-suffix attempts before raising. With suffix range 10..9999 and a
# fully populated namespace this is astronomically unlikely to be exhausted.
SUFFIXED_ATTEMPTS = 100
SUFFIX_MIN = 10
SUFFIX_MAX = 9999


def _camel_case_pair(adjective: str, noun: str) -> str:
    """Combine ``adjective`` + ``noun`` into camelCase (``cleverFox``)."""
    if not adjective or not noun:
        raise ValueError("Both adjective and noun must be non-empty.")
    return adjective.lower() + noun[0].upper() + noun[1:].lower()


def generate_handle(
    *,
    scope_qs: QuerySet,
    handle_field: str = DEFAULT_HANDLE_FIELD,
    rng: Optional[random.Random] = None,
) -> str:
    """Generate a unique handle within ``scope_qs`` using ``ADJECTIVES × NOUNS``.

    Args:
        scope_qs: QuerySet to check uniqueness against. Callers should
            ``.exclude(pk=instance.pk)`` if regenerating for an existing row,
            otherwise the candidate's own row will be treated as a collision.
        handle_field: Name of the field holding the handle (default ``handle``).
        rng: Optional pre-seeded RNG. Defaults to ``random.SystemRandom`` for
            non-deterministic production output.

    Returns:
        A handle string unique within the queryset scope.

    Raises:
        RuntimeError: If even the suffixed-candidate phase fails to find a
            unique handle. With the default namespace this is effectively
            unreachable; a failure indicates either a corrupted word list or
            an unrealistic level of saturation.
    """
    rng = rng or random.SystemRandom()

    for _ in range(PLAIN_ATTEMPTS):
        candidate = _camel_case_pair(rng.choice(ADJECTIVES), rng.choice(NOUNS))
        if not scope_qs.filter(**{handle_field: candidate}).exists():
            return candidate

    for _ in range(SUFFIXED_ATTEMPTS):
        base = _camel_case_pair(rng.choice(ADJECTIVES), rng.choice(NOUNS))
        suffix = rng.randint(SUFFIX_MIN, SUFFIX_MAX)
        candidate = f"{base}{suffix}"
        if not scope_qs.filter(**{handle_field: candidate}).exists():
            return candidate

    raise RuntimeError(
        "generate_handle: exhausted all attempts. Word list may be empty or "
        "the database may be saturated beyond practical limits."
    )
