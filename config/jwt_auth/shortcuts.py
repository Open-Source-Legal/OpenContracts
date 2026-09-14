"""Token issuance and user lookup for all API transports."""

from django.contrib.auth import get_user_model

from .settings import jwt_settings
from .utils import get_payload, get_user_by_payload


def get_token(user, context=None, **extra):
    payload = jwt_settings.JWT_PAYLOAD_HANDLER(user, context)
    payload.update(extra)
    return jwt_settings.JWT_ENCODE_HANDLER(payload, context)


def get_user_by_token(token, context=None):
    return get_user_by_payload(get_payload(token, context))


def get_active_user(user_id):
    """Load an active account by primary key in a single query.

    Backends without a ``ModelBackend`` parent share this for ``get_user`` so a
    restored session cannot outlive account deactivation. Returns ``None`` for
    missing and inactive accounts alike.
    """
    model = get_user_model()
    try:
        return model._default_manager.get(pk=user_id, is_active=True)
    except model.DoesNotExist:
        return None
