import logging

import graphql_jwt
from django.contrib.auth import get_user_model
from graphql_jwt.exceptions import JSONWebTokenError, JSONWebTokenExpired

from config.graphql_auth0_auth.utils import get_user_by_token

UserModel = get_user_model()
logger = logging.getLogger(__name__)


class Auth0RemoteUserJSONWebTokenBackend:
    """
    Django authentication backend for Auth0 JWT tokens.

    Designed to work with graphql_jwt and the GraphQL layer. JWT exceptions
    are re-raised so the GraphQL layer can return a structured error to the
    client (the frontend distinguishes "token expired -> refresh" from
    "invalid token -> re-authenticate").

    Only called for JWT-bearing requests; standard session auth still flows
    through Django's ``ModelBackend``.
    """

    def authenticate(self, request=None, **kwargs):
        if request is None or getattr(request, "_jwt_token_auth", False):
            return None

        token = graphql_jwt.utils.get_credentials(request, **kwargs)
        if token is None:
            return None

        try:
            return get_user_by_token(token)
        except (JSONWebTokenExpired, JSONWebTokenError):
            # Surface JWT exceptions so the GraphQL layer translates them
            # into proper error responses instead of silently returning an
            # anonymous user (which masks tampering attempts).
            raise
        except Exception as e:
            logger.error("Unexpected error authenticating Auth0 token: %s", e)
            return None

    def get_user(self, user_id):
        try:
            return UserModel._default_manager.get(pk=user_id)
        except UserModel.DoesNotExist:
            return None
