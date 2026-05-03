"""Celery tasks for synchronising user data with Auth0.

These tasks are defined only when ``settings.USE_AUTH0`` is enabled — they
fetch a Machine-to-Machine token, look up the remote profile via the Auth0
Management API, and copy the result onto the local :class:`User` row.
"""

import datetime
import logging
import urllib.parse
from typing import Any, Optional

import requests
from celery import chain
from celery.result import AsyncResult
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction

from config import celery_app
from opencontractserver.users.models import Auth0APIToken

if settings.USE_AUTH0:
    from config.graphql_auth0_auth.settings import auth0_settings

User = get_user_model()

logger = logging.getLogger(__name__)

# Outbound calls to Auth0 must always have a timeout; without one a single
# unresponsive Auth0 request can hang a Celery worker indefinitely.
AUTH0_HTTP_TIMEOUT = 10  # seconds

# These tasks are only needed for AUTH0, so we don't define them unless we're using AUTH0
if settings.USE_AUTH0:

    @celery_app.task()
    def get_new_auth0_token() -> Optional[str]:
        url = f"https://{auth0_settings.AUTH0_DOMAIN}/oauth/token"
        headers: dict[str, str] = {"content-type": "application/json"}
        request_data: dict[str, str] = {
            "grant_type": auth0_settings.AUTH0_M2M_MANAGEMENT_GRANT_TYPE,
            "client_id": auth0_settings.AUTH0_M2M_MANAGEMENT_API_ID,
            "client_secret": auth0_settings.AUTH0_M2M_MANAGEMENT_API_SECRET,
            "audience": f"https://{auth0_settings.AUTH0_DOMAIN}/api/v2/",
        }

        try:
            response = requests.post(
                url, headers=headers, json=request_data, timeout=AUTH0_HTTP_TIMEOUT
            )
        except requests.RequestException as exc:
            logger.error("Failed to request Auth0 management token: %s", exc)
            return None

        if response.status_code != 200:
            logger.error(
                "Auth0 management token request failed (status=%s)",
                response.status_code,
            )
            return None

        try:
            payload: dict[str, Any] = response.json()
            access_token: str = payload["access_token"]
            expires_in: int = payload["expires_in"]
        except (ValueError, KeyError) as exc:
            logger.error("Auth0 management token response malformed: %s", exc)
            return None

        # Persist with a row-level lock to avoid two workers racing to insert
        # duplicate token rows when both arrive after a token expiry.
        with transaction.atomic():
            Auth0APIToken.objects.select_for_update().all().delete()
            new_token = Auth0APIToken.objects.create(
                token=access_token,
                expiration_Date=datetime.datetime.now(datetime.timezone.utc)
                + datetime.timedelta(seconds=expires_in),
            )

        return new_token.token

    @celery_app.task()
    def apply_data_to_user(data: Optional[dict[str, Any]], userPk: str) -> None:
        if not data or not isinstance(data, dict):
            logger.warning("apply_data_to_user called with empty/invalid data")
            return

        try:
            user = User.objects.get(username=userPk)
        except User.DoesNotExist:
            logger.warning("apply_data_to_user: user %s not found", userPk)
            return

        if user.synced:
            return

        try:
            user.email = data.get("email", user.email)
            email_verified = bool(data.get("email_verified", False))
            user.email_verified = email_verified
            # Disable accounts whose email is not verified by the IdP.
            user.is_active = email_verified
            user.name = data.get("name", "")
            user.given_name = data.get("given_name", "")
            user.family_name = data.get("family_name", "")
            user.synced = True
            user.is_social_user = True
            user.last_synced = datetime.datetime.now(datetime.timezone.utc)
            user.last_ip = data.get("last_ip", user.last_ip)
            user.save()
        except Exception as exc:
            logger.error("apply_data_to_user failed for %s: %s", userPk, exc)

    @celery_app.task()
    def sync_remote_user(user_pk: str) -> AsyncResult:
        # Pick a single live token if one exists; otherwise fetch a fresh one.
        # Using ``filter().first()`` instead of ``all()`` avoids the previous
        # "delete everything if there isn't exactly one row" reset that
        # produced thrash under concurrent workers.
        token_row = (
            Auth0APIToken.objects.filter(
                expiration_Date__gt=datetime.datetime.now(datetime.timezone.utc)
            )
            .order_by("-expiration_Date")
            .first()
        )

        if token_row is None:
            data = chain(
                get_new_auth0_token.s(),
                get_user_details_async.s(user_pk),
                apply_data_to_user.s(user_pk),
            )
        else:
            data = chain(
                get_user_details_async.s(token_row.token, user_pk),
                apply_data_to_user.s(user_pk),
            )

        return data.apply_async()

    @celery_app.task()
    def ensure_valid_auth0_token() -> Optional[str]:
        token_row = (
            Auth0APIToken.objects.filter(
                expiration_Date__gt=datetime.datetime.now(datetime.timezone.utc)
            )
            .order_by("-expiration_Date")
            .first()
        )
        if token_row is not None:
            return token_row.token
        return get_new_auth0_token.delay().get()

    @celery_app.task
    def get_user_details_async(token: Optional[str], auth0_Id: str) -> dict[str, Any]:
        if not token:
            logger.warning("get_user_details_async called without a token")
            return {}

        # ``sub`` claims like ``auth0|abc`` contain reserved characters; URL
        # quote the path segment so requests doesn't end up issuing a malformed
        # request to the Management API.
        quoted_id = urllib.parse.quote(auth0_Id, safe="")
        url = f"https://{auth0_settings.AUTH0_DOMAIN}/api/v2/users/{quoted_id}"
        headers: dict[str, str] = {"Authorization": f"Bearer {token}"}

        try:
            response = requests.get(url, headers=headers, timeout=AUTH0_HTTP_TIMEOUT)
        except requests.RequestException as exc:
            logger.error("Auth0 user fetch failed for %s: %s", auth0_Id, exc)
            return {}

        if response.status_code != 200:
            logger.error(
                "Auth0 user fetch returned status %s for %s",
                response.status_code,
                auth0_Id,
            )
            return {}

        try:
            return response.json()
        except ValueError as exc:
            logger.error("Auth0 user fetch returned invalid JSON: %s", exc)
            return {}
