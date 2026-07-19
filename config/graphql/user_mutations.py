"""Generated strawberry GraphQL module (graphene migration).

Shape-generated from the graphene schema; stub functions marked PORT(...)
carry the ported business logic. See config/graphql_new/manifest.json.
"""

# mypy: disable-error-code="name-defined, valid-type, arg-type"
#   Code-generation artifacts of the strawberry schema bindings that
#   mypy's static pass cannot resolve, NOT real typing defects:
#     name-defined / valid-type — ``Annotated["XType", strawberry.lazy(...)]``
#       forward-reference strings + the runtime-generated ``*Connection``
#       types (``make_connection_types``).
#     arg-type — resolvers construct result types with ``to_global_id()``
#       (``str``) for ``strawberry.ID`` fields and return Django MODEL
#       instances where the field annotation names the strawberry type
#       (the graphene-django resolver contract). Both are correct at
#       runtime. Hand-written config/graphql/core/* stays fully checked.
# flake8: noqa: E501, F821 — generated strawberry schema module.
# E501: long GraphQL field/argument ``description=`` strings and the
# single-line generated resolver signatures (black cannot split string
# literals). F821: ``Annotated["XType", strawberry.lazy(...)]`` /
# ``cast("QuerySet", ...)`` forward-reference STRINGS that pyflakes
# resolves as names — the whole point of strawberry.lazy is to avoid the
# import (which would then be F401). Both are code-generation artifacts,
# not defects; hand-written modules (config/graphql/core/*, security.py,
# testing.py, filters.py, …) stay fully linted.

from __future__ import annotations

from calendar import timegm as _timegm
from datetime import datetime as _datetime
from typing import Annotated

import strawberry
from django.contrib.auth import authenticate as _dj_authenticate
from django.middleware.csrf import rotate_token as _rotate_token
from graphql_jwt import signals as _jwt_signals
from graphql_jwt.exceptions import JSONWebTokenError as _JWTError
from graphql_jwt.refresh_token.shortcuts import (
    create_refresh_token as _create_refresh_token,
)
from graphql_jwt.refresh_token.shortcuts import (
    refresh_token_lazy as _refresh_token_lazy,
)
from graphql_jwt.settings import jwt_settings as _jwt_settings

from config.graphql._util import strip_unset
from config.graphql.core.auth import PermissionDenied
from config.graphql.core.relay import (
    register_type,
)
from config.graphql.core.scalars import GenericScalar
from config.graphql.ratelimits import (
    RateLimits,
    get_user_tier_rate,
    graphql_ratelimit,
    graphql_ratelimit_dynamic,
)


@strawberry.type(name="ObtainJSONWebTokenWithUser")
class ObtainJSONWebTokenWithUser:
    payload: GenericScalar = strawberry.field(name="payload", default=None)
    refresh_expires_in: int = strawberry.field(name="refreshExpiresIn", default=None)
    user: None | (Annotated[UserType, strawberry.lazy("config.graphql.user_types")]) = (
        strawberry.field(name="user", default=None)
    )
    token: str = strawberry.field(name="token", default=None)
    refresh_token: str = strawberry.field(name="refreshToken", default=None)


register_type("ObtainJSONWebTokenWithUser", ObtainJSONWebTokenWithUser, model=None)


@strawberry.type(
    name="UpdateMe",
    description="Update basic profile fields for the current user, including slug.",
)
class UpdateMe:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    user: None | (Annotated[UserType, strawberry.lazy("config.graphql.user_types")]) = (
        strawberry.field(name="user", default=None)
    )


register_type("UpdateMe", UpdateMe, model=None)


@strawberry.type(name="AcceptCookieConsent")
class AcceptCookieConsent:
    ok: bool | None = strawberry.field(name="ok", default=None)


register_type("AcceptCookieConsent", AcceptCookieConsent, model=None)


@strawberry.type(
    name="DismissGettingStarted",
    description="Mutation to dismiss the getting-started guide for the current user.",
)
class DismissGettingStarted:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)


register_type("DismissGettingStarted", DismissGettingStarted, model=None)


@graphql_ratelimit(rate=RateLimits.AUTH_LOGIN, key="ip", group="mutate")
def _auth_login_rate_gate(root, info, **kwargs):
    """Rate-limit gate with the ``(root, info)`` shape core decorators expect.

    IP-keyed rather than user-tier-based: ``tokenAuth`` is called by an
    unauthenticated client, so there is no user to key on until *after* this
    succeeds. Shares ``RateLimits.AUTH_LOGIN`` with the Django-admin login
    view (``config/admin_auth/views.py``) — GraphQL login is just as much a
    credential-stuffing target as the admin one. See ``_write_light_rate_gate``
    in ``annotation_mutations.py`` for why this is a standalone gate function
    invoked from within the mutate body rather than a decorator on the
    strawberry resolver itself (whose first positional argument is
    ``payload_cls``, not ``root``).
    """
    return None


@graphql_ratelimit_dynamic(get_rate=get_user_tier_rate("WRITE_LIGHT"), group="mutate")
def _write_light_rate_gate(root, info, **kwargs):
    """Rate-limit gate with the ``(root, info)`` shape core decorators expect.

    See ``_write_light_rate_gate`` in ``annotation_mutations.py`` for the full
    rationale.
    """
    return None


def _mutate_ObtainJSONWebTokenWithUser(
    payload_cls, root, info, username=None, password=None
):
    """PORT: /home/user/oc-graphene-ref/config/graphql/user_mutations.py:75

    Port of ObtainJSONWebTokenWithUser.mutate

    Flattened port of ``graphql_jwt.mutations.JSONWebTokenMutation.mutate``
    (the ``@token_auth`` decorator chain: ``setup_jwt_cookie`` →
    ``csrf_rotation`` → ``refresh_expiration`` → the auth body →
    ``on_token_auth_resolve``) plus the project's
    ``ObtainJSONWebTokenWithUser.resolve`` override, which attaches the
    authenticated user to the payload.

    Rate-limited (``RateLimits.AUTH_LOGIN``, IP-keyed) — closes a gap where
    GraphQL login had no throttling despite the identical Django-admin login
    view being protected by the same category (issue surfaced by PR #2139
    review).
    """
    # Rate limit BEFORE attempting authentication — this must throttle
    # credential-stuffing attempts regardless of whether they succeed.
    _auth_login_rate_gate(root, info)

    context = info.context
    context._jwt_token_auth = True

    user = _dj_authenticate(
        request=context,
        username=username,
        password=password,
    )
    if user is None:
        raise _JWTError("Please enter valid credentials")

    if hasattr(context, "user"):
        context.user = user

    # ObtainJSONWebTokenWithUser.resolve — return the authenticated user.
    result = payload_cls(user=context.user)
    _jwt_signals.token_issued.send(sender=payload_cls, request=context, user=user)

    # graphql_jwt.decorators.on_token_auth_resolve
    result.payload = _jwt_settings.JWT_PAYLOAD_HANDLER(user, context)
    result.token = _jwt_settings.JWT_ENCODE_HANDLER(result.payload, context)

    if _jwt_settings.JWT_LONG_RUNNING_REFRESH_TOKEN:
        if getattr(context, "jwt_cookie", False):
            context.jwt_refresh_token = _create_refresh_token(user)
            result.refresh_token = context.jwt_refresh_token.get_token()
        else:
            result.refresh_token = _refresh_token_lazy(user)

    # graphql_jwt.decorators.refresh_expiration
    result.refresh_expires_in = (
        _timegm(_datetime.utcnow().utctimetuple())
        + _jwt_settings.JWT_REFRESH_EXPIRATION_DELTA.total_seconds()
    )

    # graphql_jwt.decorators.csrf_rotation
    if _jwt_settings.JWT_CSRF_ROTATION:
        _rotate_token(context)

    # graphql_jwt.decorators.setup_jwt_cookie
    if getattr(context, "jwt_cookie", False):
        context.jwt_token = result.token

    return result


def m_token_auth(
    info: strawberry.Info,
    username: Annotated[str, strawberry.argument(name="username")] = strawberry.UNSET,
    password: Annotated[str, strawberry.argument(name="password")] = strawberry.UNSET,
) -> ObtainJSONWebTokenWithUser | None:
    kwargs = strip_unset({"username": username, "password": password})
    return _mutate_ObtainJSONWebTokenWithUser(
        ObtainJSONWebTokenWithUser, None, info, **kwargs
    )


def _mutate_UpdateMe(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:59

    Port of UpdateMe.mutate

    Rate-limited (``WRITE_LIGHT``, user-tier) — closes a gap flagged in PR
    #2139 review where this mutation had no throttling despite every other
    ported mutation module decorating its writes.
    """
    # @login_required (graphql_jwt) — inlined because mutate stubs take
    # ``payload_cls`` as their first positional argument, which does not
    # match core.auth's ``(root, info, ...)`` calling convention.
    if not info.context.user.is_authenticated:
        raise PermissionDenied()
    # @graphql_ratelimit_dynamic(get_rate=get_user_tier_rate("WRITE_LIGHT")) —
    # inlined for the same reason; raises RateLimitExceeded when over.
    _write_light_rate_gate(root, info)

    from config.graphql.serializers import UserUpdateSerializer

    user = info.context.user
    try:
        serializer = UserUpdateSerializer(user, data=kwargs, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return payload_cls(ok=True, message="Success", user=user)
    except Exception as e:
        return payload_cls(
            ok=False, message=f"Failed to update profile: {e}", user=None
        )


def m_update_me(
    info: strawberry.Info,
    first_name: Annotated[
        str | None, strawberry.argument(name="firstName")
    ] = strawberry.UNSET,
    is_profile_public: Annotated[
        bool | None, strawberry.argument(name="isProfilePublic")
    ] = strawberry.UNSET,
    last_name: Annotated[
        str | None, strawberry.argument(name="lastName")
    ] = strawberry.UNSET,
    name: Annotated[str | None, strawberry.argument(name="name")] = strawberry.UNSET,
    phone: Annotated[str | None, strawberry.argument(name="phone")] = strawberry.UNSET,
    profile_about_markdown: Annotated[
        str | None, strawberry.argument(name="profileAboutMarkdown")
    ] = strawberry.UNSET,
    profile_headline: Annotated[
        str | None, strawberry.argument(name="profileHeadline")
    ] = strawberry.UNSET,
    profile_links_markdown: Annotated[
        str | None, strawberry.argument(name="profileLinksMarkdown")
    ] = strawberry.UNSET,
    slug: Annotated[str | None, strawberry.argument(name="slug")] = strawberry.UNSET,
) -> UpdateMe | None:
    kwargs = strip_unset(
        {
            "first_name": first_name,
            "is_profile_public": is_profile_public,
            "last_name": last_name,
            "name": name,
            "phone": phone,
            "profile_about_markdown": profile_about_markdown,
            "profile_headline": profile_headline,
            "profile_links_markdown": profile_links_markdown,
            "slug": slug,
        }
    )
    return _mutate_UpdateMe(UpdateMe, None, info, **kwargs)


def _mutate_AcceptCookieConsent(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:19

    Port of AcceptCookieConsent.mutate
    """
    # @login_required (graphql_jwt) — inlined; see _mutate_UpdateMe.
    if not info.context.user.is_authenticated:
        raise PermissionDenied()

    user = info.context.user
    user.has_accepted_cookies = True
    user.save()
    return payload_cls(ok=True)


def m_accept_cookie_consent(info: strawberry.Info) -> AcceptCookieConsent | None:
    kwargs = strip_unset({})
    return _mutate_AcceptCookieConsent(AcceptCookieConsent, None, info, **kwargs)


def _mutate_DismissGettingStarted(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:33

    Port of DismissGettingStarted.mutate
    """
    # @login_required (graphql_jwt) — inlined; see _mutate_UpdateMe.
    if not info.context.user.is_authenticated:
        raise PermissionDenied()

    user = info.context.user
    user.has_dismissed_getting_started = True
    user.save()
    return payload_cls(ok=True, message="Getting started dismissed")


def m_dismiss_getting_started(
    info: strawberry.Info,
) -> DismissGettingStarted | None:
    kwargs = strip_unset({})
    return _mutate_DismissGettingStarted(DismissGettingStarted, None, info, **kwargs)


MUTATION_FIELDS = {
    "token_auth": strawberry.field(resolver=m_token_auth, name="tokenAuth"),
    "update_me": strawberry.field(
        resolver=m_update_me,
        name="updateMe",
        description="Update basic profile fields for the current user, including slug.",
    ),
    "accept_cookie_consent": strawberry.field(
        resolver=m_accept_cookie_consent, name="acceptCookieConsent"
    ),
    "dismiss_getting_started": strawberry.field(
        resolver=m_dismiss_getting_started,
        name="dismissGettingStarted",
        description="Mutation to dismiss the getting-started guide for the current user.",
    ),
}
