import json
import logging
import threading
import time
import uuid

import jwt
import requests
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.utils.translation import gettext as _
from graphql_jwt import exceptions

from config.graphql_auth0_auth.settings import auth0_settings
from opencontractserver.constants import TOKEN_LOG_PREFIX_LENGTH

logger = logging.getLogger(__name__)

# JWKS cache to avoid fetching on every token validation
# Cache expires after 10 minutes (600 seconds)
# Thread-safe implementation using a lock for concurrent environments
_jwks_cache: dict = {"data": None, "expires_at": 0}
_jwks_cache_lock = threading.Lock()
_JWKS_CACHE_TTL = 600  # seconds
# Bounded grace window for serving stale JWKS when Auth0 is unreachable.
# Without this bound, a key compromise + rotation in Auth0 followed by an
# Auth0 outage would let the old (compromised) key keep verifying tokens
# indefinitely. After ``_JWKS_CACHE_TTL + _JWKS_STALE_GRACE`` seconds the
# cache fails closed and tokens stop verifying until Auth0 is reachable.
_JWKS_STALE_GRACE = 3600  # seconds


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
            logger.debug("_get_cached_jwks() - Using cached JWKS")
            return _jwks_cache["data"]

        logger.debug("_get_cached_jwks() - Fetching fresh JWKS from Auth0")
        try:
            response = requests.get(
                f"https://{domain}/.well-known/jwks.json", timeout=10
            )
            response.raise_for_status()
            jwks = response.json()
        except requests.RequestException as e:
            logger.error("_get_cached_jwks() - Failed to fetch JWKS from Auth0: %s", e)
            if _can_serve_stale(current_time):
                logger.warning(
                    "_get_cached_jwks() - Serving stale JWKS (fetch failure)"
                )
                return _jwks_cache["data"]
            logger.error(
                "_get_cached_jwks() - Stale-grace window exceeded; failing closed"
            )
            raise
        except ValueError as e:
            logger.error("_get_cached_jwks() - Invalid JSON response from Auth0: %s", e)
            if _can_serve_stale(current_time):
                logger.warning(
                    "_get_cached_jwks() - Serving stale JWKS (JSON parse failure)"
                )
                return _jwks_cache["data"]
            logger.error(
                "_get_cached_jwks() - Stale-grace window exceeded; failing closed"
            )
            raise

        _jwks_cache["data"] = jwks
        _jwks_cache["expires_at"] = current_time + _JWKS_CACHE_TTL
        return jwks


def _can_serve_stale(current_time: float) -> bool:
    """Return True when the cache holds data still inside the stale-grace window.

    .. warning::
       This helper reads ``_jwks_cache`` without acquiring ``_jwks_cache_lock``.
       Callers **must** already hold ``_jwks_cache_lock`` for the read to be
       safe. All call sites today live inside ``_get_cached_jwks`` under
       ``with _jwks_cache_lock:``. Do not invoke this from a different
       context without re-acquiring the lock.

       Note: ``threading.Lock.locked()`` returns True if **any** thread holds
       the lock, not necessarily the calling thread, so no runtime assert can
       guarantee correctness here without switching to ``threading.RLock``
       and tracking the owner. The single call site below makes this safe
       today; future refactors that move callers out of ``_get_cached_jwks``
       must re-acquire the lock or switch to an RLock.
    """
    if _jwks_cache["data"] is None:
        return False
    return current_time < _jwks_cache["expires_at"] + _JWKS_STALE_GRACE


def jwt_auth0_decode(token):
    logger.debug(
        "jwt_auth0_decode() - Attempting to decode token, first %d chars: %s...",
        TOKEN_LOG_PREFIX_LENGTH,
        token[:TOKEN_LOG_PREFIX_LENGTH],
    )
    try:
        header = jwt.get_unverified_header(token)
        logger.debug("jwt_auth0_decode() - Header: %s", header)
        jwks = _get_cached_jwks(auth0_settings.AUTH0_DOMAIN)
        logger.debug(
            "jwt_auth0_decode() - Retrieved JWKS with %s keys",
            len(jwks.get("keys", [])),
        )
        public_key = None
        for jwk in jwks["keys"]:
            logger.debug(
                "jwt_auth0_decode() - Checking JWK kid: %s against header kid: %s",
                jwk["kid"],
                header["kid"],
            )
            if jwk["kid"] == header["kid"]:
                logger.debug("jwt_auth0_decode() - Found matching kid: %s", jwk["kid"])
                public_key = jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(jwk))
                break

        if public_key is None:
            logger.error(
                "jwt_auth0_decode() - Public key not found - no matching kid in JWKS"
            )
            raise Exception("Public key not found.")

        issuer = f"https://{auth0_settings.AUTH0_DOMAIN}/"
        logger.debug("jwt_auth0_decode() - Issuer: %s", issuer)
        logger.debug(
            "jwt_auth0_decode() - API Audience: %s", auth0_settings.AUTH0_API_AUDIENCE
        )
        logger.debug(
            "jwt_auth0_decode() - Algorithm: %s", auth0_settings.AUTH0_TOKEN_ALGORITHM
        )

        # JWKS endpoints publish public keys only; the cryptography stubs widen
        # ``RSAAlgorithm.from_jwk`` to ``RSAPrivateKey | RSAPublicKey`` so cast
        # back to the public-key arm for ``jwt.decode``.
        from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey

        assert isinstance(public_key, RSAPublicKey)
        decoded = jwt.decode(
            token,
            public_key,
            audience=auth0_settings.AUTH0_API_AUDIENCE,
            issuer=issuer,
            algorithms=[auth0_settings.AUTH0_TOKEN_ALGORITHM],
        )
        logger.debug(
            "jwt_auth0_decode() - Successfully decoded token with keys: %s",
            list(decoded.keys()),
        )
        return decoded
    except Exception as e:
        logger.error("jwt_auth0_decode() - Error decoding token: %s", e)
        raise


def get_payload(token):
    logger.debug(
        "get_payload() - Processing token, first %d chars: %s...",
        TOKEN_LOG_PREFIX_LENGTH,
        token[:TOKEN_LOG_PREFIX_LENGTH] if token else "None",
    )
    try:
        payload = auth0_settings.AUTH0_DECODE_HANDLER(token)
        logger.debug(
            "get_payload() - Successfully got payload with keys: %s",
            list(payload.keys()),
        )
        return payload
    except jwt.ExpiredSignatureError as e:
        logger.error("get_payload() - Token expired: %s", e)
        raise exceptions.JSONWebTokenExpired()
    except jwt.DecodeError as e:
        logger.error("get_payload() - Decode error: %s", e)
        raise exceptions.JSONWebTokenError(_("Error decoding signature"))
    except jwt.InvalidTokenError as e:
        logger.error("get_payload() - Invalid token error: %s", e)
        raise exceptions.JSONWebTokenError(_("Invalid token"))
    except Exception as e:
        logger.error("get_payload() - Unexpected error: %s", e)
        raise


def user_can_authenticate(user):
    """
    Reject users with is_active=False. Custom user models that don't have
    that attribute are allowed.
    """
    is_active = getattr(user, "is_active", None)
    logger.debug("user_can_authenticate() - User: %s, is_active: %s", user, is_active)
    return is_active or is_active is None


def configure_user(user):
    """
    Configure a user after creation and return the updated user.
    Also triggers async task to sync user data with auth0 profile.
    """
    logger.debug("configure_user() - Configuring new user: %s", user)
    user.is_active = True
    user.is_social_user = True
    user.set_password(
        uuid.uuid4().__str__()
    )  # Random django password to prevent malicious use of user with no pass
    user.first_signed_in = timezone.now()
    user.save()
    logger.debug(
        "configure_user() - User configured and saved: %s, is_active: %s",
        user,
        user.is_active,
    )

    # For new users from outside
    logger.debug("configure_user() - Triggering async sync for user: %s", user.username)
    # Lazy import to avoid circular dependency when USE_AUTH0 is False
    from opencontractserver.users.tasks import sync_remote_user

    sync_remote_user.delay(
        user.username
    )  # This is run async, but I'm not sure we want this actually...

    return user


def get_auth0_user_from_token(remote_username):
    logger.debug(
        "get_auth0_user_from_token() - Starting with remote_username: %s",
        remote_username,
    )

    if not remote_username:
        logger.warning("get_auth0_user_from_token() - No remote username provided")
        return
    user = None

    UserModel = get_user_model()
    logger.debug("get_auth0_user_from_token() - UserModel: %s", UserModel)
    logger.debug("get_auth0_user_from_token() - remote_username: %s", remote_username)
    logger.debug(
        "get_auth0_user_from_token() - AUTH0_CREATE_NEW_USERS: %s",
        auth0_settings.AUTH0_CREATE_NEW_USERS,
    )

    if auth0_settings.AUTH0_CREATE_NEW_USERS:
        logger.debug(
            "get_auth0_user_from_token() - Attempting to get_or_create user with username: %s",
            remote_username,
        )
        try:
            user, created = UserModel._default_manager.get_or_create(
                **{UserModel.USERNAME_FIELD: remote_username}
            )
            logger.debug("get_auth0_user_from_token() - user created: %s", created)
            logger.debug(
                "get_auth0_user_from_token() - user: %s, id: %s",
                user,
                user.id if user else "None",
            )
            if created:
                logger.debug(
                    "get_auth0_user_from_token() - configuring new user: %s", user
                )
                user = configure_user(user)
                logger.debug(
                    "get_auth0_user_from_token() - user configured: %s, is_active: %s",
                    user,
                    user.is_active if user else "None",
                )
        except Exception as e:
            logger.error("get_auth0_user_from_token() - Error in get_or_create: %s", e)
    else:
        try:
            logger.debug(
                "get_auth0_user_from_token() - Attempting to get user by natural key: %s",
                remote_username,
            )
            user = UserModel._default_manager.get_by_natural_key(remote_username)
            logger.debug(
                "get_auth0_user_from_token() - found existing user: %s, id: %s",
                user,
                user.id if user else "None",
            )
        except UserModel.DoesNotExist:
            logger.warning(
                "get_auth0_user_from_token() - User with username %s does not exist",
                remote_username,
            )
            pass
        except Exception as e:
            logger.error(
                "get_auth0_user_from_token() - Error getting user by natural key: %s", e
            )

    if user is None:
        logger.warning(
            "get_auth0_user_from_token() - returning None as no user found/created"
        )
        return user
    else:
        is_active = user.is_active and user_can_authenticate(user)
        logger.debug(
            "get_auth0_user_from_token() - user %s active status: %s",
            user.username,
            is_active,
        )
        if not is_active:
            logger.warning(
                "get_auth0_user_from_token() - User %s is not active, returning None",
                user.username,
            )
        return user if is_active else None


def jwt_get_username_from_payload_handler(payload):
    username = payload.get("sub")
    logger.debug(
        "jwt_get_username_from_payload_handler() - Extracted username from payload: %s",
        username,
    )
    return username


def _parse_boolean_claim(value: object) -> tuple[bool, bool]:
    """
    Parse a claim value to a boolean, handling string representations.

    Auth0 claims may be sent as booleans or strings depending on configuration.
    This function handles both cases safely.

    Args:
        value: The claim value (bool, str, or None).

    Returns:
        tuple: (parsed_value, is_valid) where is_valid is False if value
               cannot be parsed.
    """
    if isinstance(value, bool):
        return value, True

    if isinstance(value, str):
        lower_value = value.lower().strip()
        if lower_value in ("true", "1", "yes"):
            return True, True
        if lower_value in ("false", "0", "no"):
            return False, True
        logger.warning("Invalid boolean claim value: %s", value)
        return False, False

    # Handle numeric values (0/1)
    if isinstance(value, (int, float)):
        return bool(value), True

    if value is None:
        return False, False

    logger.warning("Unexpected claim type: %s", type(value))
    return False, False


def _normalize_admin_claim(value: object, claim_name: str) -> tuple[bool, bool]:
    """
    Normalize an admin claim with fail-closed semantics.

    Missing or invalid claims are treated as False to avoid privilege retention.

    Args:
        value: The raw claim value.
        claim_name: The claim name for logging.

    Returns:
        tuple: (parsed_value, is_valid)
    """
    if value is None:
        logger.info("Admin claim %s missing; defaulting to False", claim_name)
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

    Handles both boolean and string claim values (e.g., true, "true", "True").

    Defense-in-depth: ``is_superuser`` elevation additionally requires the
    user's Auth0 sub (Django ``username``) to appear in
    ``settings.AUTH0_SUPERUSER_SUB_ALLOWLIST``. A user not in the allowlist
    is forced to ``is_superuser=False`` regardless of the JWT claim. This
    blocks tenant misconfigurations where ``is_superuser`` is sourced from
    user-writable ``user_metadata``.

    Args:
        user: The Django user object to update.
        payload: The decoded JWT payload containing claims.

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

    logger.debug(
        "sync_admin_claims - namespace: %s, payload keys: %s",
        namespace,
        list(payload.keys()),
    )
    raw_is_staff = payload.get(f"{namespace}is_staff")
    raw_is_superuser = payload.get(f"{namespace}is_superuser")
    logger.debug(
        "sync_admin_claims - raw_is_staff: %r, raw_is_superuser: %r",
        raw_is_staff,
        raw_is_superuser,
    )

    # Parse claims with type safety (fail closed on missing/invalid)
    is_staff_claim, is_staff_valid = _normalize_admin_claim(raw_is_staff, "is_staff")
    is_superuser_claim, is_superuser_valid = _normalize_admin_claim(
        raw_is_superuser, "is_superuser"
    )

    # Defense-in-depth allowlist for is_superuser. If the user is not in the
    # allowlist, force the effective claim to False regardless of what the
    # token says. We log loudly when we override a True claim so operators
    # see attempted elevations that were blocked.
    #
    # NB: ``is_staff`` is intentionally NOT allowlist-gated here. Operators
    # who source ``is_staff`` from user-writable ``user_metadata`` already
    # accept that any Auth0 user can grant themselves Django admin (read)
    # access; the allowlist is targeted at the much larger blast radius of
    # ``is_superuser`` (full admin write). If you need to gate ``is_staff``
    # too, layer a parallel ``AUTH0_STAFF_SUB_ALLOWLIST`` check below.
    superuser_allowlist = getattr(settings, "AUTH0_SUPERUSER_SUB_ALLOWLIST", [])
    if (
        is_superuser_valid
        and is_superuser_claim
        and user.username not in superuser_allowlist
    ):
        logger.warning(
            "Blocked is_superuser=True claim for user %s (sub not in "
            "AUTH0_SUPERUSER_SUB_ALLOWLIST). Add the sub to the allowlist "
            "to permit elevation.",
            user.username,
        )
        is_superuser_claim = False

    needs_save = False

    # Only update if claim is valid and different from current value
    if is_staff_valid and user.is_staff != is_staff_claim:
        user.is_staff = is_staff_claim
        needs_save = True
        logger.info("Synced is_staff=%s for user %s", is_staff_claim, user.username)

    if is_superuser_valid and user.is_superuser != is_superuser_claim:
        user.is_superuser = is_superuser_claim
        needs_save = True
        logger.info(
            "Synced is_superuser=%s for user %s", is_superuser_claim, user.username
        )

    if needs_save:
        try:
            user.save(update_fields=["is_staff", "is_superuser"])
        except Exception as e:
            # Log but don't crash - admin login should still work
            logger.error(
                "Failed to save admin claims for user %s: %s", user.username, e
            )
            return False

    return True


def _sync_admin_claims_cached(user, payload):
    """
    Sync admin claims from payload with caching to limit performance impact.

    This function uses Django's cache to avoid syncing admin claims on every
    API request. Claims are synced at most once per ADMIN_CLAIMS_CACHE_TTL
    seconds per user.

    If cache is unavailable, claims are synced on every request as fallback.

    Args:
        user: The Django user object to potentially update.
        payload: The decoded JWT payload containing claims.
    """
    from django.conf import settings

    if not getattr(settings, "USE_AUTH0", False):
        return

    from django.core.cache import cache

    from opencontractserver.constants import ADMIN_CLAIMS_CACHE_TTL

    # Operators can tune the TTL via AUTH0_ADMIN_CLAIMS_CACHE_TTL env var; the
    # module-level constant remains the default and is mirrored in
    # ``config/settings/base.py``.
    cache_ttl = getattr(
        settings, "AUTH0_ADMIN_CLAIMS_CACHE_TTL", ADMIN_CLAIMS_CACHE_TTL
    )
    cache_key = f"admin_claims_sync:{user.id}"

    # Check if we've synced recently (with cache failure fallback)
    try:
        if cache.get(cache_key):
            return
    except Exception as e:
        # Cache unavailable, proceed with sync
        logger.warning("Cache unavailable for admin claims check: %s", e)

    # Sync claims and set cache
    try:
        sync_admin_claims_from_payload(user, payload)
        try:
            cache.set(cache_key, True, timeout=cache_ttl)
        except Exception as e:
            # Cache set failed, but sync succeeded - that's fine
            logger.warning("Failed to cache admin claims sync status: %s", e)
    except Exception as e:
        # Log but don't fail the request - claim sync is secondary
        logger.warning("Failed to sync admin claims for user %s: %s", user.username, e)


def get_user_by_payload(payload):
    logger.debug("get_user_by_payload() - Payload keys: %s", list(payload.keys()))

    username = jwt_get_username_from_payload_handler(payload)
    logger.debug("get_user_by_payload() - Extracted username: %s", username)

    if not username:
        logger.error("get_user_by_payload() - No username in payload")
        raise exceptions.JSONWebTokenError(_("Invalid payload"))

    logger.debug(
        "get_user_by_payload() - Getting user from token handler with username: %s",
        username,
    )
    user = auth0_settings.AUTH0_GET_USER_FROM_TOKEN_HANDLER(username)
    logger.debug(
        "get_user_by_payload() - User returned from handler: %s, id: %s",
        user,
        user.id if user else "None",
    )

    if user is not None:
        is_active = getattr(user, "is_active", True)
        logger.debug(
            "get_user_by_payload() - User %s is_active: %s", user.username, is_active
        )
        if not is_active:
            logger.error("get_user_by_payload() - User %s is disabled", user.username)
            raise exceptions.JSONWebTokenError(_("User is disabled"))
        # Sync admin claims with caching to balance security and performance.
        # Claims are synced periodically (every ADMIN_CLAIMS_CACHE_TTL seconds)
        # rather than on every request to avoid database overhead.
        _sync_admin_claims_cached(user, payload)
    else:
        logger.warning("get_user_by_payload() - No user found for username")

    logger.debug(
        "get_user_by_payload() - returning user: %s, id: %s",
        user,
        user.id if user else "None",
    )
    return user


def get_user_by_token(token, **kwargs):
    """
    Given a JWT token from auth0, verify the token. If valid,
    1) check if matching user exists and return obj or, 2), if no
    user exists and settings is set to create user obj for unknown user,
    create a user, configure it, and return user obj
    """
    logger.debug(
        "get_user_by_token() - Starting with token first %d chars: %s...",
        TOKEN_LOG_PREFIX_LENGTH,
        token[:TOKEN_LOG_PREFIX_LENGTH] if token else "None",
    )
    try:
        payload = get_payload(token)
        logger.debug(
            "get_user_by_token() - Got payload with keys: %s", list(payload.keys())
        )
        user = get_user_by_payload(payload)
        logger.debug(
            "get_user_by_token() - User from payload: %s, id: %s",
            user,
            user.id if user else "None",
        )
        return user
    except Exception as e:
        logger.error("get_user_by_token() - Error processing token: %s", e)
        raise
