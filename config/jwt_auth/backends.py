"""Django authentication backend for locally signed JWTs."""

from django.contrib.auth import get_user_model

from .shortcuts import get_user_by_token
from .utils import get_credentials


class JSONWebTokenBackend:
    def authenticate(self, request=None, **kwargs):
        if request is None or getattr(request, "_jwt_token_auth", False):
            return None
        token = get_credentials(request, **kwargs)
        return get_user_by_token(token, request) if token is not None else None

    def get_user(self, user_id):
        model = get_user_model()
        try:
            return model._default_manager.get(pk=user_id, is_active=True)
        except model.DoesNotExist:
            return None
