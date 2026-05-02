"""
DRF authentication backend for CorpusAccessToken-based worker auth.

Workers authenticate via:
    Authorization: WorkerKey <token>

The backend hashes the incoming plaintext token with SHA-256 and looks up
the hash in the database. Only hashes are stored — plaintext tokens are
shown once at creation and never persisted.
"""

import logging
from typing import Any, Optional

from django.utils import timezone
from rest_framework import authentication, exceptions

from opencontractserver.worker_uploads.models import CorpusAccessToken, hash_token

logger = logging.getLogger(__name__)

WORKER_AUTH_PREFIX = "WorkerKey"


class WorkerTokenAuthentication(authentication.BaseAuthentication):
    """
    Authenticates requests from external document-processing workers.

    Returns (user, token) where:
    - user: the auto-created Django User linked to the WorkerAccount
    - token: the CorpusAccessToken instance (available as request.auth)
    """

    def authenticate(self, request: Any) -> Optional[tuple[Any, CorpusAccessToken]]:
        auth_header = authentication.get_authorization_header(request).decode("utf-8")
        if not auth_header:
            return None

        parts = auth_header.split()
        # Empty after split — only reachable for whitespace-only headers like "  "
        if len(parts) == 0 or parts[0] != WORKER_AUTH_PREFIX:
            return None

        if len(parts) == 1:
            raise exceptions.AuthenticationFailed(
                "Invalid WorkerKey header. No token provided."
            )
        if len(parts) > 2:
            raise exceptions.AuthenticationFailed(
                "Invalid WorkerKey header. Token must not contain spaces."
            )

        return self._authenticate_token(parts[1])

    def _authenticate_token(self, plaintext_key: str) -> tuple[Any, CorpusAccessToken]:
        key_hash = hash_token(plaintext_key)
        key_prefix = plaintext_key[:8]
        try:
            token = CorpusAccessToken.objects.select_related(
                "worker_account", "worker_account__user"
            ).get(key=key_hash)
        except CorpusAccessToken.DoesNotExist:
            logger.warning(
                "WorkerToken auth failed: invalid token (prefix=%s)", key_prefix
            )
            raise exceptions.AuthenticationFailed("Invalid worker token.")

        if not token.is_active:
            logger.warning(
                "WorkerToken auth failed: revoked token (prefix=%s)", key_prefix
            )
            raise exceptions.AuthenticationFailed("Token has been revoked.")

        if not token.worker_account.is_active:
            logger.warning(
                "WorkerToken auth failed: inactive account %s (prefix=%s)",
                token.worker_account.name,
                key_prefix,
            )
            raise exceptions.AuthenticationFailed("Worker account is inactive.")

        if token.expires_at and timezone.now() >= token.expires_at:
            logger.warning(
                "WorkerToken auth failed: expired token (prefix=%s)", key_prefix
            )
            raise exceptions.AuthenticationFailed("Token has expired.")

        return (token.worker_account.user, token)

    def authenticate_header(self, request: Any) -> str:
        return f'{WORKER_AUTH_PREFIX} realm="api"'
