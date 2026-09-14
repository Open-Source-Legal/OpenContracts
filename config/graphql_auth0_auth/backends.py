import logging

from django.contrib.auth import get_user_model

from config.graphql_auth0_auth.utils import get_user_by_token
from config.jwt_auth import utils as jwt_utils
from config.jwt_auth.exceptions import JSONWebTokenExpired

UserModel = get_user_model()
logger = logging.getLogger(__name__)


class Auth0RemoteUserJSONWebTokenBackend:
    """
    Django authentication backend for Auth0 JWT tokens.

    This backend is designed to work with graphql_jwt and the GraphQL layer.
    It differs from standard Django authentication backends in that it
    RE-RAISES JSONWebTokenExpired exceptions instead of returning None.

    Why this design:
    - graphql_jwt expects backends to raise JWT exceptions for proper error handling
    - The GraphQL layer catches these and translates them to proper error responses
    - This allows the frontend to distinguish between "token expired" (refresh needed)
      vs "token invalid" (re-authentication needed)

    ``authenticate`` validates header credentials. Django also calls ``get_user``
    for sessions created with this backend; it reloads active accounts while
    Django validates the session hash.
    """

    def authenticate(self, request=None, **kwargs):
        logger.debug(
            f"Auth0RemoteUserJSONWebTokenBackend.authenticate() - Starting with request: {request}"
        )

        if request is None or getattr(request, "_jwt_token_auth", False):
            logger.debug(
                "Auth0RemoteUserJSONWebTokenBackend.authenticate() - request is None or _jwt_token_auth is True, returning None"  # noqa: E501
            )
            return None

        token = jwt_utils.get_credentials(request, **kwargs)
        logger.debug(
            f"Auth0RemoteUserJSONWebTokenBackend.authenticate() - token retrieved: {'Present' if token else 'None'}"
        )

        if token is not None:
            try:
                user = get_user_by_token(token)
                logger.debug(
                    f"Auth0RemoteUserJSONWebTokenBackend.authenticate() - User from token: {user}, id: {user.id if user else 'None'}"  # noqa: E501
                )
                return user
            except JSONWebTokenExpired:
                # Re-raise expired token exceptions so GraphQL layer can signal
                # the frontend to refresh the token. This ensures the frontend
                # receives "Signature has expired" instead of generic auth error.
                logger.warning(
                    "Auth0RemoteUserJSONWebTokenBackend.authenticate() - Token has expired, "
                    "propagating to GraphQL layer for proper client signaling"
                )
                raise
            except Exception as e:
                logger.error(
                    f"Auth0RemoteUserJSONWebTokenBackend.authenticate() - Error getting user by token: {str(e)}"
                )
                return None

        logger.debug(
            "Auth0RemoteUserJSONWebTokenBackend.authenticate() - No token found, returning None"
        )
        return None

    def get_user(self, user_id):
        logger.debug(
            f"Auth0RemoteUserJSONWebTokenBackend.get_user() - Looking up user_id: {user_id}"
        )
        try:
            user = UserModel._default_manager.get(pk=user_id, is_active=True)
            logger.debug(
                f"Auth0RemoteUserJSONWebTokenBackend.get_user() - Found user: {user}, is_active: {user.is_active}"
            )
            return user
        except UserModel.DoesNotExist:
            logger.warning(
                f"Auth0RemoteUserJSONWebTokenBackend.get_user() - User with id {user_id} does not exist"
            )
            return None
        except Exception as e:
            logger.error(
                f"Auth0RemoteUserJSONWebTokenBackend.get_user() - Error getting user: {str(e)}"
            )
            return None
