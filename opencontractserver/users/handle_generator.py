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
is rare in practice.

Determinism
-----------
The generator accepts an optional ``random.Random`` instance so tests can pin
output. Default behaviour uses ``random.SystemRandom`` for non-deterministic
selection in production.
"""

from __future__ import annotations

import logging
import random

from django.db.models import QuerySet

from opencontractserver.constants.users import (
    HANDLE_PLAIN_ATTEMPTS,
    HANDLE_SUFFIX_MAX,
    HANDLE_SUFFIX_MIN,
    HANDLE_SUFFIXED_ATTEMPTS,
)
from opencontractserver.users.handle_wordlists import ADJECTIVES, NOUNS

logger = logging.getLogger(__name__)

# Module-local aliases so callers (including tests that patch these names)
# can import directly from this module without depending on the constants
# module path. The authoritative values live in
# ``opencontractserver.constants.users``.
PLAIN_ATTEMPTS = HANDLE_PLAIN_ATTEMPTS
SUFFIXED_ATTEMPTS = HANDLE_SUFFIXED_ATTEMPTS
SUFFIX_MIN = HANDLE_SUFFIX_MIN
SUFFIX_MAX = HANDLE_SUFFIX_MAX


def _camel_case_pair(adjective: str, noun: str) -> str:
    """Combine ``adjective`` + ``noun`` into camelCase (``cleverFox``)."""
    if not adjective or not noun:
        raise ValueError("Both adjective and noun must be non-empty.")
    return adjective.lower() + noun[0].upper() + noun[1:].lower()


def generate_handle(
    *,
    scope_qs: QuerySet,
    rng: random.Random | None = None,
) -> str:
    """Generate a unique handle within ``scope_qs`` using ``ADJECTIVES × NOUNS``.

    Args:
        scope_qs: QuerySet to check uniqueness against. Callers should
            ``.exclude(pk=instance.pk)`` if regenerating for an existing row,
            otherwise the candidate's own row will be treated as a collision.
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
        if not scope_qs.filter(handle=candidate).exists():
            return candidate

    # Reaching this point means ``PLAIN_ATTEMPTS`` consecutive collisions in
    # the ~56k-pair namespace, which suggests either heavy saturation or an
    # accidentally truncated word list. Log a warning so an operator can spot
    # the regression before users start seeing numeric-suffixed handles.
    logger.warning(
        "generate_handle: plain phase exhausted after %s attempts; "
        "falling back to suffixed phase. Word list may be too small or "
        "scope_qs is unexpectedly saturated.",
        PLAIN_ATTEMPTS,
    )

    for _ in range(SUFFIXED_ATTEMPTS):
        base = _camel_case_pair(rng.choice(ADJECTIVES), rng.choice(NOUNS))
        suffix = rng.randint(SUFFIX_MIN, SUFFIX_MAX)
        candidate = f"{base}{suffix}"
        if not scope_qs.filter(handle=candidate).exists():
            return candidate

    raise RuntimeError(
        "generate_handle: exhausted all attempts. Word list may be empty or "
        "the database may be saturated beyond practical limits."
    )
