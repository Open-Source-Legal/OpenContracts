"""
Authentication backend for Django admin with Auth0 support.

The admin login view validates the Auth0 JWT itself and then calls
``django.contrib.auth.login(request, user, backend=...)``, which writes the
user/backend pair into the session without re-running ``authenticate()``. We
therefore only need this backend to implement ``get_user()`` so subsequent
requests can rehydrate the session.

``authenticate()`` is intentionally a no-op: there is no credential we could
verify here that we don't already verify in the view, and accepting a bare
``auth0_user_id`` kwarg would let any caller of
``django.contrib.auth.authenticate(request, auth0_user_id=...)`` log in as
that user without proving they own the account.
"""

import logging
from typing import TYPE_CHECKING, Any, Optional

from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.http import HttpRequest

if TYPE_CHECKING:
    from opencontractserver.users.models import User

logger = logging.getLogger(__name__)
UserModel = get_user_model()


class Auth0AdminBackend(ModelBackend):
    """Session rehydration backend for Auth0-authenticated admin users."""

    def authenticate(
        self,
        request: Optional[HttpRequest],
        username: Optional[str] = None,
        password: Optional[str] = None,
        **kwargs: Any,
    ) -> Optional["User"]:
        """No-op: credential verification happens in the admin login view."""
        return None

    def get_user(self, user_id: int) -> Optional["User"]:
        """Retrieve user by primary key."""
        try:
            return UserModel.objects.get(pk=user_id)
        except UserModel.DoesNotExist:
            return None
