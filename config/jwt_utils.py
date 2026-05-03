"""
Unified JWT authentication utilities for all API surfaces.

This module provides a single, DRY entry point for JWT token validation
that automatically handles both Auth0 and standard graphql_jwt tokens
based on the USE_AUTH0 setting.

Used by:
- REST API authentication (rest_jwt_auth.py)
- WebSocket authentication middleware
- Any future authentication contexts

Raises:
- JSONWebTokenExpired: Token has expired (client should refresh)
- JSONWebTokenError: Token is invalid (client should re-authenticate)
"""

import logging
from typing import TYPE_CHECKING

from django.conf import settings

if TYPE_CHECKING:
    from opencontractserver.users.models import User

logger = logging.getLogger(__name__)


def get_user_from_jwt_token(token: str) -> "User":
    """
    Validate a JWT token and return the associated user.

    Automatically handles both Auth0 and standard graphql_jwt tokens
    based on the USE_AUTH0 setting.

    Raises:
        JSONWebTokenExpired: Token has expired. Client should refresh
            their token and retry.
        JSONWebTokenError: Token is invalid. Client should re-authenticate.
    """
    if getattr(settings, "USE_AUTH0", False):
        return _validate_auth0_token(token)
    return _validate_graphql_jwt_token(token)


def _validate_graphql_jwt_token(token: str) -> "User":
    """Validate a standard graphql_jwt token (HS256, local secret)."""
    from graphql_jwt.exceptions import JSONWebTokenError
    from graphql_jwt.utils import get_payload, get_user_by_payload

    payload = get_payload(token)

    user = get_user_by_payload(payload)
    if user is None:
        raise JSONWebTokenError("User not found")

    if not user.is_active:
        raise JSONWebTokenError("User is disabled")

    return user


def _validate_auth0_token(token: str) -> "User":
    """Validate an Auth0 JWT token (RS256, JWKS verification)."""
    from graphql_jwt.exceptions import JSONWebTokenError

    from config.graphql_auth0_auth.utils import get_user_by_token

    user = get_user_by_token(token)

    if user is None:
        raise JSONWebTokenError("User not found")

    if not user.is_active:
        raise JSONWebTokenError("User is disabled")

    return user
