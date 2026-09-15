"""Django authentication backend for locally signed JWTs."""

from .shortcuts import get_active_user, get_user_by_token
from .utils import get_credentials


class JSONWebTokenBackend:
    def authenticate(self, request=None, **kwargs):
        if request is None or getattr(request, "_jwt_token_auth", False):
            return None
        token = get_credentials(request, **kwargs)
        return get_user_by_token(token, request) if token is not None else None

    def get_user(self, user_id):
        return get_active_user(user_id)
