import json
import logging
import threading
import time
import uuid

import jwt
import requests
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.utils.translation import gettext as _
from graphql_jwt import exceptions

from config.graphql_auth0_auth.settings import auth0_settings

logger = logging.getLogger(__name__)

# JWKS cache to avoid fetching on every token validation
# Cache expires after 10 minutes (600 seconds)
# Thread-safe implementation using a lock for concurrent environments
_jwks_cache: dict = {"data": None, "expires_at": 0}
_jwks_cache_lock = threading.Lock()
_JWKS_CACHE_TTL = 600  # seconds


def _get_cached_jwks(domain: str) -> dict:
    """
    Fetch JWKS from Auth0 with caching.
    Returns cached JWKS if still valid, otherwise fetches fresh data.

    Thread-safe implementation using a lock to prevent race conditions
    in concurrent environments (Gunicorn workers, async requests).
    """
    with _jwks_cache_lock:
        current_time = time.time()
        if _jwks_cache["data"] is not None and current_time < _jwks_cache["expires_at"]:
            return _jwks_cache["data"]

        try:
            response = requests.get(
                f"https://{domain}/.well-known/jwks.json", timeout=10
            )
            response.raise_for_status()
            jwks = response.json()
        except requests.RequestException as e:
            logger.error("Failed to fetch JWKS from Auth0: %s", e)
            if _jwks_cache["data"] is not None:
                logger.warning("Using stale JWKS cache due to fetch failure")
                return _jwks_cache["data"]
            raise
        except ValueError as e:
            logger.error("Invalid JSON response from Auth0 JWKS endpoint: %s", e)
            if _jwks_cache["data"] is not None:
                logger.warning("Using stale JWKS cache due to JSON parse failure")
                return _jwks_cache["data"]
            raise

        _jwks_cache["data"] = jwks
        _jwks_cache["expires_at"] = current_time + _JWKS_CACHE_TTL
        return jwks


def jwt_auth0_decode(token):
    header = jwt.get_unverified_header(token)
    jwks = _get_cached_jwks(auth0_settings.AUTH0_DOMAIN)
    public_key = None
    for jwk in jwks.get("keys", []):
        if jwk["kid"] == header.get("kid"):
            public_key = jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(jwk))
            break

    if public_key is None:
        # Surfaced as InvalidTokenError so get_payload() converts it into a
        # JSONWebTokenError rather than letting a bare Exception propagate.
        raise jwt.InvalidTokenError("Public key not found for token kid")

    issuer = f"https://{auth0_settings.AUTH0_DOMAIN}/"

    # JWKS endpoints publish public keys only, but the cryptography stubs widen
    # ``RSAAlgorithm.from_jwk`` to ``RSAPrivateKey | RSAPublicKey``. Use an
    # explicit runtime check instead of ``assert`` so the guard is preserved
    # under ``python -O`` (which strips assertions).
    if not isinstance(public_key, RSAPublicKey):
        raise jwt.InvalidTokenError("JWKS returned unexpected key type")

    return jwt.decode(
        token,
        public_key,
        audience=auth0_settings.AUTH0_API_AUDIENCE,
        issuer=issuer,
        algorithms=[auth0_settings.AUTH0_TOKEN_ALGORITHM],
    )


def get_payload(token):
    try:
        return auth0_settings.AUTH0_DECODE_HANDLER(token)
    except jwt.ExpiredSignatureError:
        raise exceptions.JSONWebTokenExpired()
    except jwt.InvalidTokenError as e:
        # Covers DecodeError, InvalidSignatureError, MissingRequiredClaimError,
        # InvalidAudienceError, InvalidIssuerError and the "public key not
        # found" case raised above.
        logger.warning("JWT validation failed: %s", e)
        raise exceptions.JSONWebTokenError(_("Invalid token"))


def user_can_authenticate(user):
    """
    Reject users with is_active=False. Custom user models that don't have
    that attribute are allowed.
    """
    is_active = getattr(user, "is_active", None)
    return is_active or is_active is None


def configure_user(user):
    """
    Configure a user after creation and return the updated user.
    Also triggers async task to sync user data with auth0 profile.
    """
    user.is_active = True
    # Random django password to prevent malicious use of user with no pass.
    user.set_password(str(uuid.uuid4()))
    user.first_signed_in = timezone.now()
    user.save()

    # Lazy import to avoid circular dependency when USE_AUTH0 is False
    from opencontractserver.users.tasks import sync_remote_user

    sync_remote_user.delay(user.username)
    return user


def get_auth0_user_from_token(remote_username):
    if not remote_username:
        return None

    UserModel = get_user_model()
    user = None

    if auth0_settings.AUTH0_CREATE_NEW_USERS:
        try:
            user, created = UserModel._default_manager.get_or_create(
                **{UserModel.USERNAME_FIELD: remote_username}
            )
            if created:
                user = configure_user(user)
        except Exception as e:
            logger.error("get_auth0_user_from_token() get_or_create failed: %s", e)
            return None
    else:
        try:
            user = UserModel._default_manager.get_by_natural_key(remote_username)
        except UserModel.DoesNotExist:
            return None
        except Exception as e:
            logger.error("get_auth0_user_from_token() lookup failed: %s", e)
            return None

    if user is None:
        return None

    if not (user.is_active and user_can_authenticate(user)):
        logger.info("get_auth0_user_from_token() user %s is not active", user.username)
        return None

    return user


def jwt_get_username_from_payload_handler(payload):
    return payload.get("sub")


def _parse_boolean_claim(value: object) -> tuple[bool, bool]:
    """
    Parse a claim value to a boolean.

    Auth0 claims are usually JSON booleans, but some Action templates emit
    strings.  We accept the JSON forms and the canonical string forms only
    ("true"/"false") so a misconfigured Action fails loudly rather than
    silently coercing values like "yes" or "1".

    Returns:
        tuple: (parsed_value, is_valid)
    """
    if isinstance(value, bool):
        return value, True

    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized == "true":
            return True, True
        if normalized == "false":
            return False, True
        logger.warning("Unrecognised boolean claim string: %r", value)
        return False, False

    if value is None:
        return False, False

    logger.warning("Unexpected claim type: %s", type(value))
    return False, False


def _normalize_admin_claim(value: object, claim_name: str) -> tuple[bool, bool]:
    """
    Normalize an admin claim with fail-closed semantics.

    Missing or invalid claims are treated as False to avoid privilege retention.

    Returns:
        tuple: (parsed_value, is_valid)
    """
    if value is None:
        return False, True

    parsed_value, is_valid = _parse_boolean_claim(value)
    if not is_valid:
        logger.warning(
            "Admin claim %s invalid (%r); defaulting to False", claim_name, value
        )
        return False, True

    return parsed_value, True


def sync_admin_claims_from_payload(user, payload):
    """
    Sync is_staff and is_superuser from Auth0 token claims.

    Claims are expected at namespace + 'is_staff' and namespace + 'is_superuser'.
    Missing or invalid claims are treated as False to avoid privilege retention.

    Returns:
        bool: True on success (whether changes were made or not),
              False only if save failed (non-fatal error).
    """
    from django.conf import settings

    namespace = getattr(
        settings,
        "AUTH0_ADMIN_CLAIM_NAMESPACE",
        "https://contracts.opensource.legal/",
    )

    raw_is_staff = payload.get(f"{namespace}is_staff")
    raw_is_superuser = payload.get(f"{namespace}is_superuser")

    is_staff_claim, is_staff_valid = _normalize_admin_claim(raw_is_staff, "is_staff")
    is_superuser_claim, is_superuser_valid = _normalize_admin_claim(
        raw_is_superuser, "is_superuser"
    )

    needs_save = False
    if is_staff_valid and user.is_staff != is_staff_claim:
        # Privilege transitions are low-volume (rate-limited via
        # ADMIN_CLAIMS_CACHE_TTL) and security-sensitive, so log them at INFO
        # to preserve an audit trail.
        logger.info(
            "Auth0 claim sync changed is_staff for user %s: %s -> %s",
            user.username,
            user.is_staff,
            is_staff_claim,
        )
        user.is_staff = is_staff_claim
        needs_save = True

    if is_superuser_valid and user.is_superuser != is_superuser_claim:
        logger.info(
            "Auth0 claim sync changed is_superuser for user %s: %s -> %s",
            user.username,
            user.is_superuser,
            is_superuser_claim,
        )
        user.is_superuser = is_superuser_claim
        needs_save = True

    if needs_save:
        try:
            user.save(update_fields=["is_staff", "is_superuser"])
        except Exception as e:
            logger.error(
                "Failed to save admin claims for user %s: %s", user.username, e
            )
            return False

    return True


def _sync_admin_claims_cached(user, payload):
    """
    Sync admin claims from payload with caching to limit performance impact.

    Claims are synced at most once per ADMIN_CLAIMS_CACHE_TTL seconds per user.
    If cache is unavailable, claims are synced on every request as fallback.
    """
    from django.conf import settings

    if not getattr(settings, "USE_AUTH0", False):
        return

    from django.core.cache import cache

    from opencontractserver.constants import ADMIN_CLAIMS_CACHE_TTL

    cache_key = f"admin_claims_sync:{user.id}"

    try:
        if cache.get(cache_key):
            return
    except Exception as e:
        logger.warning("Cache unavailable for admin claims check: %s", e)

    try:
        sync_admin_claims_from_payload(user, payload)
        try:
            cache.set(cache_key, True, timeout=ADMIN_CLAIMS_CACHE_TTL)
        except Exception as e:
            logger.warning("Failed to cache admin claims sync status: %s", e)
    except Exception as e:
        logger.warning("Failed to sync admin claims for user %s: %s", user.username, e)


def get_user_by_payload(payload):
    username = jwt_get_username_from_payload_handler(payload)
    if not username:
        raise exceptions.JSONWebTokenError(_("Invalid payload"))

    user = auth0_settings.AUTH0_GET_USER_FROM_TOKEN_HANDLER(username)
    if user is not None:
        if not getattr(user, "is_active", True):
            raise exceptions.JSONWebTokenError(_("User is disabled"))
        # Sync admin claims with caching to balance security and performance.
        _sync_admin_claims_cached(user, payload)

    return user


def get_user_by_token(token, **kwargs):
    """
    Given a JWT token from auth0, verify the token. If valid,
    1) check if matching user exists and return obj or, 2), if no
    user exists and settings is set to create user obj for unknown user,
    create a user, configure it, and return user obj.
    """
    payload = get_payload(token)
    return get_user_by_payload(payload)
