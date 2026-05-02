"""Celery tasks for synchronising user data with Auth0.

These tasks are defined only when ``settings.USE_AUTH0`` is enabled — they
fetch a Machine-to-Machine token, look up the remote profile via the Auth0
Management API, and copy the result onto the local :class:`User` row.
"""

import datetime
import json
import logging
from typing import Any, Optional

import requests
from celery import chain
from celery.result import AsyncResult
from django.conf import settings
from django.contrib.auth import get_user_model

from config import celery_app
from opencontractserver.users.models import Auth0APIToken

if settings.USE_AUTH0:
    from config.graphql_auth0_auth.settings import auth0_settings

User = get_user_model()

logger = logging.getLogger(__name__)

# These tasks are only needed for AUTH0, so we don't define them unless we're using AUTH0
if settings.USE_AUTH0:

    @celery_app.task()
    def get_new_auth0_token() -> Optional[str]:

        # print("get_new_auth0_token")
        url = f"https://{auth0_settings.AUTH0_DOMAIN}/oauth/token"
        # print(url)

        headers: dict[str, str] = {"content-type": "application/json"}
        # print(headers)

        request_data: dict[str, str] = {
            "grant_type": auth0_settings.AUTH0_M2M_MANAGEMENT_GRANT_TYPE,
            "client_id": auth0_settings.AUTH0_M2M_MANAGEMENT_API_ID,
            "client_secret": auth0_settings.AUTH0_M2M_MANAGEMENT_API_SECRET,
            "audience": f"https://{auth0_settings.AUTH0_DOMAIN}/api/v2/",
        }
        # print(f"Machine-2-Machine Request data: {request_data}")

        response = requests.post(url, headers=headers, json=request_data)

        # print("Auth0 Response:")
        # print(response.status_code)
        # print(response.text)

        if response.status_code == 200:
            payload: dict[str, Any] = json.loads(response.text)
            # print(payload)
            access_token: str = payload["access_token"]
            expires_in: int = payload["expires_in"]

            newToken = Auth0APIToken()
            newToken.token = access_token
            newToken.expiration_Date = datetime.datetime.now() + datetime.timedelta(
                0, expires_in
            )
            newToken.auth0_Response = response.text
            newToken.save()

            return newToken.token

        logger.error("Error retrieving access token to Auth0.")
        return None

    @celery_app.task()
    def apply_data_to_user(data: dict[str, Any], userPk: str) -> None:

        # print(f"apply_data_to_user() - userPk is: {userPk}\nData: {data}")

        user = User.objects.get(username=userPk)
        if user is not None and not user.synced:

            try:
                user.email = data["email"]
                # print(data["email"])
                user.email_verified = data["email_verified"]
                # print(data["email_verified"])
                if data["email_verified"]:
                    user.is_active = True
                else:
                    user.is_active = False  # disable accounts with unverified emails
                user.name = data["name"]
                # print(data["name"])
                user.given_name = data["given_name"]
                # print(data["given_name"])
                user.family_name = data["family_name"]
                # print(data["family_name"])
                user.synced = True
                user.is_social_user = True
                user.last_synced = datetime.datetime.now(datetime.timezone.utc)
                user.last_ip = data["last_ip"]
                # print(user.last_ip)
                # print(user)
                user.save()

            except Exception as inst:
                logger.error(
                    f"Exception applying data to user - exception: {type(inst)}"
                )
                logger.error(
                    f"Exception applying data to user - exception args; {inst.args}"
                )

    @celery_app.task()
    def sync_remote_user(user_pk: str) -> AsyncResult:

        refresh = False
        tokens = Auth0APIToken.objects.all()

        if not len(tokens) == 1:
            for tok in tokens:
                tok.delete()
            refresh = True
        else:
            if tokens[0].expiration_Date < datetime.datetime.now(datetime.timezone.utc):
                # print("Token has expired. Refetching from Auth0")
                tokens[0].delete()
                refresh = True

        if refresh:
            data = chain(
                get_new_auth0_token.s(),
                get_user_details_async.s(user_pk),
                apply_data_to_user.s(user_pk),
            )
        else:
            data = chain(
                get_user_details_async.s(tokens[0].token, user_pk),
                apply_data_to_user.s(user_pk),
            )

        return data.apply_async()

    @celery_app.task()
    def ensure_valid_auth0_token() -> Optional[str]:

        tokens = Auth0APIToken.objects.all()

        if len(tokens) == 0:
            # print("No Auth0 Tokens... Request one.")
            return get_new_auth0_token.delay().get()
        elif len(tokens) > 1:
            # print(
            #     "Somehow there was more than 1 token. Going to delete all and refresh"
            # )
            for tok in tokens:
                tok.delete()
                return get_new_auth0_token.delay().get()
            return None
        else:
            if tokens[0].expiration_Date < datetime.datetime.now(datetime.timezone.utc):
                # print("Token has expired. Refetching from Auth0")
                tokens[0].delete()
                return get_new_auth0_token.delay().get()
            else:
                # print("Token is good!")
                return tokens[0].token

    @celery_app.task
    def get_user_details_async(token: str, auth0_Id: str) -> dict[str, Any]:
        headers: dict[str, str] = {
            "Authorization": f"Bearer {token}",
        }
        url = f"https://{auth0_settings.AUTH0_DOMAIN}/api/v2/users/{auth0_Id}"
        response = requests.get(url, headers=headers)
        return json.loads(response.text)
