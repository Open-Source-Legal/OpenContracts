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
    based on the USE_AUTH0 setting. This is the single entry point
    for JWT validation across all API surfaces.

    Args:
        token: The JWT token string to validate.

    Returns:
        The authenticated Django user object.

    Raises:
        JSONWebTokenExpired: Token has expired. Client should refresh
            their token and retry.
        JSONWebTokenError: Token is invalid. Client should re-authenticate.
    """
    if getattr(settings, "USE_AUTH0", False):
        return _validate_auth0_token(token)
    return _validate_graphql_jwt_token(token)


def _validate_graphql_jwt_token(token: str) -> "User":
    """
    Validate a standard graphql_jwt token (HS256, local secret).

    Args:
        token: The JWT token string.

    Returns:
        The authenticated user.

    Raises:
        JSONWebTokenExpired: Token has expired.
        JSONWebTokenError: Token is invalid or user not found.
    """
    from graphql_jwt.exceptions import JSONWebTokenError
    from graphql_jwt.utils import get_payload, get_user_by_payload

    logger.debug(f"Validating graphql_jwt token: {token[:10]}...")

    # get_payload raises JSONWebTokenExpired or JSONWebTokenError
    payload = get_payload(token)

    user = get_user_by_payload(payload)
    if user is None:
        logger.warning("No user found for graphql_jwt token payload")
        raise JSONWebTokenError("User not found")

    if not user.is_active:
        logger.warning(f"User {user.username} is inactive")
        raise JSONWebTokenError("User is disabled")

    logger.debug(f"Successfully validated graphql_jwt token for user: {user.username}")
    return user


def _validate_auth0_token(token: str) -> "User":
    """
    Validate an Auth0 JWT token (RS256, JWKS verification).

    Args:
        token: The Auth0 JWT token string.

    Returns:
        The authenticated user (created if AUTH0_CREATE_NEW_USERS is True).

    Raises:
        JSONWebTokenExpired: Token has expired.
        JSONWebTokenError: Token is invalid or user not found.
    """
    from graphql_jwt.exceptions import JSONWebTokenError

    from config.graphql_auth0_auth.utils import get_user_by_token

    logger.debug(f"Validating Auth0 token: {token[:10]}...")

    # get_user_by_token handles payload extraction, user lookup/creation,
    # and raises JSONWebTokenExpired or JSONWebTokenError as appropriate
    user = get_user_by_token(token)

    if user is None:
        logger.warning("No user found/created for Auth0 token")
        raise JSONWebTokenError("User not found")

    if not user.is_active:
        logger.warning(f"User {user.username} is inactive")
        raise JSONWebTokenError("User is disabled")

    logger.debug(f"Successfully validated Auth0 token for user: {user.username}")
    return user
