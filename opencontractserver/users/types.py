"""Shared user-related typing aliases.

Centralised here to avoid duplicate ``UserOrAnonymous = User | AnonymousUser``
declarations every time a service / view / tool needs to accept either an
authenticated user or an anonymous one. Both names are imported under
``if TYPE_CHECKING:`` at call-sites, so this module incurs no runtime cost.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Union

if TYPE_CHECKING:
    from django.contrib.auth.models import AnonymousUser

    from opencontractserver.users.models import User

    UserOrAnonymous = Union[User, AnonymousUser]
