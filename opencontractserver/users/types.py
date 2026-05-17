"""Shared user-related typing aliases and resolution helpers.

Centralises ``UserOrAnonymous`` so service / view / tool surfaces don't
re-declare the union, and provides the canonical id → user-or-anonymous
resolver consumed by everything that bridges
``AgentConfig.user_id`` / ``request.user.id`` / a stored ``creator_id``
into a service call expecting an actual model instance.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Union

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser

if TYPE_CHECKING:
    from opencontractserver.users.models import User

    UserOrAnonymous = Union[User, AnonymousUser]


def resolve_user_or_anon(user_id: int | None) -> UserOrAnonymous:
    """Resolve an integer ``user_id`` to a ``User`` or :class:`AnonymousUser`.

    Centralised here (not on a service class) because the pattern is needed
    anywhere ``AgentConfig.user_id`` / persisted creator IDs cross into a
    service that requires an actual model instance — every such bridge
    would otherwise re-implement the same two-line lookup with subtly
    different error handling.

    The lookup hits the database. Callers running inside async code MUST
    invoke this from inside the same ``sync_to_async`` block as the ORM
    query that consumes the result; calling it bare from an async
    function will raise ``SynchronousOnlyOperation``.
    """

    if user_id is None:
        return AnonymousUser()
    return get_user_model().objects.get(pk=user_id)
