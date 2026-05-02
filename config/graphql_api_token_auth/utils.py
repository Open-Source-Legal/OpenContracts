"""Request helpers for extracting API tokens from incoming HTTP requests."""

import logging
from typing import Any

from django.conf import settings
from django.http import HttpRequest
from rest_framework import HTTP_HEADER_ENCODING

logger = logging.getLogger(__name__)


def get_authorization_header(request: HttpRequest) -> bytes:
    """
    Return the request's ``Authorization:`` header as a bytestring.

    The Django test client sometimes supplies the header as ``str``; we
    coerce it to ``bytes`` here so downstream callers can treat the
    header uniformly (``.split()`` on ``bytes`` returns ``list[bytes]``).
    """
    auth: str | bytes = request.META.get("HTTP_AUTHORIZATION", b"")
    if isinstance(auth, str):
        # Work around django test client oddness
        auth = auth.encode(HTTP_HEADER_ENCODING)
    return auth


def get_token_argument(request: HttpRequest, **kwargs: Any) -> str | None:
    """Return the token value from the configured API-token header, or ``None``."""
    auth = request.headers.get(settings.API_TOKEN_HEADER_NAME)
    if auth:
        parts = auth.split()
        if len(parts) == 2 and parts[0].lower() == settings.API_TOKEN_PREFIX.lower():
            return parts[1]
    return None


def get_http_authorization(request: HttpRequest) -> str | None:
    """
    Extract and validate the HTTP authorization token from the request.

    Returns the raw token string if the header has the expected
    ``<prefix> <token>`` shape, otherwise ``None``. Invalid shapes are
    not an auth failure at this layer — the caller decides whether to
    attempt token-based authentication or fall through to the next
    backend.
    """
    logger.info("Attempting to get HTTP authorization")

    auth = request.META.get("HTTP_" + settings.API_TOKEN_HEADER_NAME, "").split()
    prefix = settings.API_TOKEN_PREFIX

    logger.debug(f"Authorization header parts count: {len(auth)}")
    logger.debug(f"Expected prefix: {prefix}")

    if len(auth) != 2 or auth[0].lower() != prefix.lower():
        logger.debug(
            f"Invalid authorization format - got {len(auth)} parts with prefix '{auth[0] if auth else None}'"
        )
        return None

    token: str = auth[1]
    logger.debug("Successfully extracted token")
    return token
