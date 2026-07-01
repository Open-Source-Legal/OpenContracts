"""Numeric helpers shared across services.

Domain-agnostic numeric utilities live here so any service can reuse them
without importing from another app's package (CLAUDE.md item 6: utilities
belong in utility files).
"""

from __future__ import annotations


def clamp_int(value: int, *, lower: int, upper: int) -> int:
    """Clamp a caller-supplied value into the inclusive ``[lower, upper]`` range.

    A value that cannot be coerced to ``int`` (``None``, a string, etc.) falls
    back to ``lower`` — the safe floor — rather than raising, so a single
    hostile/sloppy caller can neither crash the call nor escape the bounds.

    This is deliberately distinct from
    :func:`opencontractserver.llms.tools.core_tools._helpers.clamp_limit`, which
    has a *separate* ``default`` argument and treats any non-positive request as
    "use the default" (its floor is implicitly ``1``). ``clamp_int`` has no
    default channel: it simply pins the value between an explicit ``lower`` and
    ``upper``, folding the non-int fallback into ``lower``. The two are NOT
    interchangeable — pick by whether you need a separate default (``clamp_limit``)
    or a pure two-sided clamp (``clamp_int``).
    """
    # ``value`` is annotated ``int`` for the production callers (whose bounds are
    # already int-typed), but the try/except defensively tolerates a runtime
    # non-int (e.g. an LLM passing a string) and floors it to ``lower``.
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = lower
    return max(lower, min(number, upper))
