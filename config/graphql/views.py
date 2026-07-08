"""Strawberry GraphQL HTTP view.

Replaces ``graphene_django.views.GraphQLView`` and the graphene-level auth
middlewares (``graphql_jwt.middleware.JSONWebTokenMiddleware`` +
``config.graphql_api_token_auth.middleware.ApiKeyTokenMiddleware``): the
per-request authentication those middlewares performed on first resolver
entry now happens once in ``get_context`` — same backend chain
(``django.contrib.auth.authenticate(request=...)`` walks
``AUTHENTICATION_BACKENDS``: JWT / Auth0 / API-key backends), same
precedence (an already-authenticated session user is left untouched).

The GraphQL context object IS the Django ``HttpRequest`` — every resolver
ported from graphene keeps reading ``info.context.user`` /
``info.context.build_absolute_uri`` etc. unchanged.
"""

from __future__ import annotations

import logging
from typing import Any

from django.contrib.auth import authenticate
from django.contrib.auth.models import AnonymousUser
from django.http import HttpRequest, HttpResponse, JsonResponse
from strawberry.django.views import GraphQLView as _StrawberryGraphQLView

logger = logging.getLogger(__name__)


def authenticate_request(request: HttpRequest) -> None:
    """Authenticate a GraphQL request via the configured backend chain.

    Mirrors ``graphql_jwt.middleware.JSONWebTokenMiddleware``'s behaviour
    (plus the API-key middleware): only attempt authentication when the
    request is anonymous and carries an ``Authorization`` header; leave
    session-authenticated users untouched. Token errors (expired/invalid
    signature) propagate to the caller for GraphQL-error formatting.
    """
    has_user = hasattr(request, "user")
    if has_user and request.user.is_authenticated:
        return
    if not request.META.get("HTTP_AUTHORIZATION"):
        if not has_user:
            request.user = AnonymousUser()
        return
    user = authenticate(request=request)
    if user is not None:
        request.user = user
    elif not has_user:
        request.user = AnonymousUser()


class GraphQLView(_StrawberryGraphQLView):
    """Strawberry Django view using the raw ``HttpRequest`` as context."""

    def get_context(self, request: HttpRequest, response: HttpResponse) -> Any:
        authenticate_request(request)
        return request

    def dispatch(self, request: HttpRequest, *args: Any, **kwargs: Any):
        try:
            return super().dispatch(request, *args, **kwargs)
        except Exception as exc:  # noqa: BLE001
            # Auth-level failures raised during get_context surface as a
            # GraphQL-style error payload, like the graphene middlewares
            # produced, instead of a 500. Under graphene these were raised
            # inside per-field resolution (``JSONWebTokenMiddleware`` /
            # ``ApiKeyTokenMiddleware``), so graphql-core caught them and
            # returned a normal ``{"errors": [...]}`` 200. Auth now runs in
            # ``get_context`` — before execution begins — so we reproduce that
            # contract here: expired/invalid JWT (``JSONWebTokenError``) and
            # malformed/unknown/inactive API keys (DRF ``AuthenticationFailed``
            # raised by ``ApiKeyBackend`` when ``USE_API_KEY_AUTH=True``) both
            # become a 200 error payload rather than an unhandled 500.
            from graphql_jwt.exceptions import JSONWebTokenError
            from rest_framework.exceptions import AuthenticationFailed

            if isinstance(exc, (JSONWebTokenError, AuthenticationFailed)):
                return JsonResponse(
                    {"errors": [{"message": str(exc)}], "data": None}, status=200
                )
            raise
