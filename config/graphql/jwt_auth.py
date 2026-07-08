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

from calendar import timegm
from datetime import datetime
from typing import Annotated

import strawberry
from django.middleware.csrf import rotate_token
from graphql_jwt.exceptions import JSONWebTokenError
from graphql_jwt.refresh_token import signals as refresh_token_signals
from graphql_jwt.refresh_token.shortcuts import (
    create_refresh_token,
    get_refresh_token,
    refresh_token_lazy,
)
from graphql_jwt.settings import jwt_settings
from graphql_jwt.utils import get_payload

from config.graphql._util import strip_unset
from config.graphql.core.relay import (
    register_type,
)
from config.graphql.core.scalars import GenericScalar


@strawberry.type(name="Verify")
class Verify:
    payload: GenericScalar = strawberry.field(name="payload", default=None)


register_type("Verify", Verify, model=None)


@strawberry.type(name="Refresh")
class Refresh:
    payload: GenericScalar = strawberry.field(name="payload", default=None)
    refresh_expires_in: int = strawberry.field(name="refreshExpiresIn", default=None)
    token: str = strawberry.field(name="token", default=None)
    refresh_token: str = strawberry.field(name="refreshToken", default=None)


register_type("Refresh", Refresh, model=None)


def _ensure_token(info, token):
    """Port of ``graphql_jwt.decorators.ensure_token``."""
    if token is None:
        token = info.context.COOKIES.get(jwt_settings.JWT_COOKIE_NAME)
        if token is None:
            raise JSONWebTokenError("Token is required")
    return token


def _refresh_expires_in(orig_iat=None):
    """Port of ``graphql_jwt.decorators.refresh_expiration`` timestamping."""
    base = (
        orig_iat if orig_iat is not None else timegm(datetime.utcnow().utctimetuple())
    )
    return base + jwt_settings.JWT_REFRESH_EXPIRATION_DELTA.total_seconds()


def _maybe_rotate_csrf(info):
    """Port of ``graphql_jwt.decorators.csrf_rotation``."""
    if jwt_settings.JWT_CSRF_ROTATION:
        rotate_token(info.context)


def _mutate_Verify(payload_cls, root, info, token=None):
    """Port of ``graphql_jwt.mutations.Verify`` (VerifyMixin.verify)."""
    token = _ensure_token(info, token)
    return payload_cls(payload=get_payload(token, info.context))


def m_verify_token(
    info: strawberry.Info,
    token: Annotated[str | None, strawberry.argument(name="token")] = strawberry.UNSET,
) -> Verify | None:
    kwargs = strip_unset({"token": token})
    return _mutate_Verify(Verify, None, info, **kwargs)


def _mutate_Refresh(payload_cls, root, info, refresh_token=None):
    """Port of ``graphql_jwt.refresh_token.mixins.RefreshTokenMixin.refresh``
    (the long-running-refresh-token variant selected by
    ``JWT_LONG_RUNNING_REFRESH_TOKEN=True``), including the
    ``refresh_expiration`` / ``csrf_rotation`` decorator behaviour."""
    context = info.context

    # ensure_refresh_token
    if refresh_token is None:
        refresh_token = context.COOKIES.get(jwt_settings.JWT_REFRESH_TOKEN_COOKIE_NAME)
        if refresh_token is None:
            raise JSONWebTokenError("Refresh token is required")

    old_refresh_token = get_refresh_token(refresh_token, context)

    if old_refresh_token.is_expired(context):
        raise JSONWebTokenError("Refresh token is expired")

    payload = jwt_settings.JWT_PAYLOAD_HANDLER(old_refresh_token.user, context)
    token = jwt_settings.JWT_ENCODE_HANDLER(payload, context)

    if getattr(context, "jwt_cookie", False):
        context.jwt_refresh_token = create_refresh_token(
            old_refresh_token.user, old_refresh_token
        )
        new_refresh_token = context.jwt_refresh_token.get_token()
    else:
        new_refresh_token = refresh_token_lazy(
            old_refresh_token.user, old_refresh_token
        )

    refresh_token_signals.refresh_token_rotated.send(
        sender=payload_cls,
        request=context,
        refresh_token=old_refresh_token,
        refresh_token_issued=new_refresh_token,
    )

    result = payload_cls(payload=payload)
    result.token = token
    result.refresh_token = new_refresh_token
    result.refresh_expires_in = _refresh_expires_in()
    _maybe_rotate_csrf(info)
    return result


def m_refresh_token(
    info: strawberry.Info,
    refresh_token: Annotated[
        str | None, strawberry.argument(name="refreshToken")
    ] = strawberry.UNSET,
) -> Refresh | None:
    kwargs = strip_unset({"refresh_token": refresh_token})
    return _mutate_Refresh(Refresh, None, info, **kwargs)


MUTATION_FIELDS = {
    "verify_token": strawberry.field(resolver=m_verify_token, name="verifyToken"),
    "refresh_token": strawberry.field(resolver=m_refresh_token, name="refreshToken"),
}
