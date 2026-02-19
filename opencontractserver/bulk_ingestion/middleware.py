"""
Graphene middleware for workstation API key authentication.

Detects ``Authorization: WSK wsk_...`` headers and authenticates the
request as the key's creator. Runs before JWT middleware so that
workstation requests are authenticated before JSONWebTokenMiddleware
attempts (and fails) to decode the token as a JWT.

After successful authentication the Authorization header is cleared so
downstream middleware (JWT, API-key) does not re-process it.
"""

import logging

from django.utils import timezone

logger = logging.getLogger(__name__)

WORKSTATION_AUTH_PREFIX = "WSK"


class WorkstationKeyMiddleware:
    """Graphene middleware that authenticates workstation API keys."""

    def resolve(self, next, root, info, **kwargs):
        request = info.context

        # Only run once per request — skip if already authenticated
        if hasattr(request, "_workstation_auth_checked"):
            return next(root, info, **kwargs)
        request._workstation_auth_checked = True

        # Check for WSK prefix in Authorization header
        auth_header = request.META.get("HTTP_AUTHORIZATION", "")
        if not auth_header.startswith(f"{WORKSTATION_AUTH_PREFIX} "):
            return next(root, info, **kwargs)

        raw_key = auth_header[len(WORKSTATION_AUTH_PREFIX) + 1 :].strip()
        if not raw_key.startswith("wsk_"):
            return next(root, info, **kwargs)

        # Lazy import to avoid circular imports at module load time
        from opencontractserver.bulk_ingestion.models import WorkstationApiKey

        key_hash = WorkstationApiKey.hash_key(raw_key)

        try:
            api_key = WorkstationApiKey.objects.select_related("creator").get(
                key_hash=key_hash
            )
        except WorkstationApiKey.DoesNotExist:
            logger.warning("Workstation auth failed: unknown key")
            return next(root, info, **kwargs)

        if not api_key.is_active:
            logger.warning(
                f"Workstation auth failed: revoked key {api_key.key_prefix}..."
            )
            return next(root, info, **kwargs)

        if api_key.expires_at and api_key.expires_at < timezone.now():
            logger.warning(
                f"Workstation auth failed: expired key {api_key.key_prefix}..."
            )
            return next(root, info, **kwargs)

        # Authenticate
        request.user = api_key.creator

        # Update last_used_at (fire-and-forget, don't fail the request)
        try:
            WorkstationApiKey.objects.filter(pk=api_key.pk).update(
                last_used_at=timezone.now()
            )
        except Exception:
            pass

        # Clear Authorization header so JWT middleware doesn't try to
        # decode the workstation key as a JWT and override with AnonymousUser
        request.META["HTTP_AUTHORIZATION"] = ""

        logger.debug(
            f"Workstation key {api_key.key_prefix}... "
            f"authenticated as user {api_key.creator_id}"
        )

        return next(root, info, **kwargs)
