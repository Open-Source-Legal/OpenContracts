"""
Authentication backend for Django admin with Auth0 support.

This backend allows Auth0-authenticated users to access Django admin
when USE_AUTH0 is enabled, falling back to standard authentication
when disabled.
"""

import logging
from typing import TYPE_CHECKING, Any, Optional

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.http import HttpRequest

if TYPE_CHECKING:
    from opencontractserver.users.models import User

logger = logging.getLogger(__name__)
UserModel = get_user_model()


class Auth0AdminBackend(ModelBackend):
    """
    Admin authentication backend that works with Auth0.

    This backend is used by the custom admin login view to authenticate
    users who have already authenticated via Auth0 on the frontend.

    For users who navigate directly to /admin/, it redirects them to
    the frontend Auth0 login flow, then back to admin.
    """

    def authenticate(
        self,
        request: Optional[HttpRequest],
        username: Optional[str] = None,
        password: Optional[str] = None,
        **kwargs: Any,
    ) -> Optional["User"]:
        """
        Authenticate a user by their Auth0 user ID (sub claim).

        This is called after the user has authenticated via Auth0 on the
        frontend and the token has been validated. ``username`` and
        ``password`` are declared to match :class:`ModelBackend`'s
        signature (Django calls every backend with those kwargs) but are
        ignored here — credential-based login falls through to the
        default backend. The Auth0-specific ``auth0_user_id`` is passed
        via ``**kwargs``.

        Args:
            request: The HTTP request object.
            username: Accepted for :class:`ModelBackend` compatibility; ignored.
            password: Accepted for :class:`ModelBackend` compatibility; ignored.
            **kwargs: Additional credentials. The ``auth0_user_id`` key
                (Auth0 JWT ``sub`` claim) drives the lookup; other keys
                are ignored.

        Returns:
            The authenticated user if valid and ``is_staff``, otherwise ``None``.
        """
        if not getattr(settings, "USE_AUTH0", False):
            return None

        auth0_user_id: Optional[str] = kwargs.get("auth0_user_id")
        if not auth0_user_id:
            return None

        try:
            user = UserModel.objects.get(username=auth0_user_id)
            if user.is_active and user.is_staff:
                logger.info(
                    "Auth0 admin authentication successful for user ID %s", user.pk
                )
                return user
            else:
                logger.warning(
                    "Auth0 user %s denied admin access: is_active=%s, is_staff=%s",
                    auth0_user_id,
                    user.is_active,
                    user.is_staff,
                )
                return None
        except UserModel.DoesNotExist:
            logger.warning("Auth0 admin auth failed: user %s not found", auth0_user_id)
            return None

    def get_user(self, user_id: int) -> Optional["User"]:
        """Retrieve user by primary key."""
        try:
            return UserModel.objects.get(pk=user_id)
        except UserModel.DoesNotExist:
            return None
