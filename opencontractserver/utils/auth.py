"""Authentication helpers shared by anonymous-friendly resolvers/mutations.

Most of the platform's permission checks operate on a real ``User`` —
``user.is_authenticated`` is enough. The anonymous-voting surface introduced
in PR #1789 added a triple-guard that callers need to repeat verbatim in
three modules so an ``AnonymousUser`` instance (or a bare ``None``) is
treated as anonymous even if its ``is_authenticated`` attribute reports
``True``:

* ``user is not None``
* ``getattr(user, "is_authenticated", False)``
* ``not getattr(user, "is_anonymous", True)``

This module centralises that contract so the auth/anon branch logic stays
consistent across ``corpus_types.py``, ``voting_mutations.py``, and
``corpuses/services/votes.py``.
"""

from __future__ import annotations

from typing import Any


def is_authenticated_user(user: Any) -> bool:
    """Return ``True`` when ``user`` is a real authenticated account.

    Expected callers pass ``AbstractBaseUser | AnonymousUser | None`` — the
    parameter is typed as ``Any`` to accept the test doubles and third-party
    wrappers that anonymous-friendly surfaces also see.

    Treats ``None`` and Django's ``AnonymousUser`` as not-authenticated
    even though ``AnonymousUser.is_authenticated`` may be set on
    test doubles or third-party wrappers — ``is_anonymous`` is the
    authoritative signal for the anonymous shape and must agree before
    we trust ``is_authenticated``.
    """
    return bool(
        user is not None
        and getattr(user, "is_authenticated", False)
        and not getattr(user, "is_anonymous", True)
    )
