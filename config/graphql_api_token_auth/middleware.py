"""GraphQL middleware that authenticates requests via API-token headers."""

from typing import Any, Callable

from django.contrib.auth import authenticate, get_user_model
from django.http import HttpRequest

from config.graphql_api_token_auth.utils import (
    get_http_authorization,
    get_token_argument,
)

User = get_user_model()


def _context_has_user(request: HttpRequest) -> bool:
    return hasattr(request, "user") and request.user.is_authenticated


def _authenticate(request: HttpRequest) -> bool:
    """
    Return True if we should attempt API-token authentication.

    Returns False if the request carries a Bearer token (handled by JWT
    middleware) or is already authenticated via another backend.
    """
    auth = request.META.get("HTTP_AUTHORIZATION", "")
    if auth.startswith("Bearer "):
        return False

    is_anonymous = not _context_has_user(request)
    return is_anonymous and get_http_authorization(request) is not None


class ApiKeyTokenMiddleware:
    """Graphene middleware that authenticates via an API-token header."""

    def __init__(self) -> None:
        self.cached_allow_any: set[str] = set()

    def authenticate_context(self, info: Any, **kwargs: Any) -> bool:
        root_path = info.path[0]

        if root_path not in self.cached_allow_any:
            return True
        return False

    def resolve(
        self,
        next: Callable[..., Any],
        root: Any,
        info: Any,
        **kwargs: Any,
    ) -> Any:

        # Check to see if user already on context

        if "user" in info.context.POST:
            existing_user = info.context.POST["user"]
            if (
                existing_user is not None
                and isinstance(existing_user, User)
                and existing_user.is_authenticated
            ):
                return next(root, info, **kwargs)

        context = info.context
        token_argument = get_token_argument(context, **kwargs)

        if (
            _authenticate(context) or token_argument is not None
        ) and self.authenticate_context(info, **kwargs):

            # If we already have an authenticated user for our request, don't bother re-authenticating
            # same request. This was causing a massive performance hit.
            if not _context_has_user(context):
                user = authenticate(request=context, **kwargs)

                if user is not None:
                    context.user = user

        return next(root, info, **kwargs)
