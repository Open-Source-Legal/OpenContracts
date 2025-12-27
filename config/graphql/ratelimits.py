"""
Rate limiting decorators for GraphQL mutations and queries.

This module provides decorators for rate limiting GraphQL operations
using django-ratelimit. It supports both authenticated and anonymous users
with different rate limits based on user tier.

The heavy lifting is done by the shared config.ratelimits module.
This file only contains GraphQL-specific decorator implementations.
"""

import functools
import logging
from typing import Callable, Optional, Union

from django.conf import settings
from django_ratelimit import ALL
from django_ratelimit.core import is_ratelimited
from graphql import GraphQLError

# Re-export from shared module for backward compatibility
from config.ratelimits import (
    RateLimits,
    format_rate_limit_message,
    get_user_tier_rate,
)
from config.ratelimits.ip import get_client_ip_from_request as get_client_ip

logger = logging.getLogger(__name__)

# Re-export RateLimits and get_user_tier_rate for backward compatibility
__all__ = [
    "RateLimitExceeded",
    "get_client_ip",
    "graphql_ratelimit",
    "graphql_ratelimit_dynamic",
    "RateLimits",
    "get_user_tier_rate",
]


class RateLimitExceeded(GraphQLError):
    """Custom exception for rate limit exceeded errors in GraphQL."""

    def __init__(self, message: str = "Rate limit exceeded. Please try again later."):
        super().__init__(message)


def graphql_ratelimit(
    key: Optional[str] = None,
    rate: str = "10/m",
    method: Union[str, list] = ALL,
    block: bool = True,
    group: Optional[str] = None,
):
    """
    Rate limit decorator for GraphQL resolvers.

    Args:
        key: The key to use for rate limiting. Can be:
            - None: Uses user ID for authenticated users, IP for anonymous
            - "ip": Always uses IP address
            - "user": Always uses user ID (fails for anonymous users)
            - "user_or_ip": Uses user ID if authenticated, IP otherwise
            - Custom callable that takes (root, info, **kwargs) and returns a string
        rate: Rate limit string (e.g., "10/m" for 10 per minute, "100/h" for 100 per hour)
        method: HTTP method(s) to apply rate limiting to
        block: Whether to block requests that exceed the limit
        group: Optional group name for shared rate limits

    Examples:
        @graphql_ratelimit(rate="5/m")  # 5 requests per minute per user/IP
        def resolve_expensive_query(root, info, **kwargs):
            ...

        @graphql_ratelimit(key="ip", rate="100/h")  # 100 requests per hour per IP
        def mutate_create_document(root, info, **kwargs):
            ...
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(root, info, *args, **kwargs):
            # Handle cases where info might be None or not have context
            if not info or not hasattr(info, "context"):
                if not getattr(settings, "TESTING", False):
                    logger.warning(
                        f"Rate limiting skipped for {func.__name__}: info object is None or missing context. "
                        "This may indicate a security issue if happening in production."
                    )
                return func(root, info, *args, **kwargs)

            request = info.context

            # Handle test contexts where context might not be a request
            if not request or not hasattr(request, "META"):
                if not getattr(settings, "TESTING", False):
                    logger.warning(
                        f"Rate limiting skipped for {func.__name__}: context is not a Django request object. "
                        f"Context type: {type(request).__name__}. "
                        "This may indicate a security issue if happening in production."
                    )
                return func(root, info, *args, **kwargs)

            # Skip rate limiting if explicitly disabled
            if getattr(settings, "RATELIMIT_DISABLE", False):
                return func(root, info, *args, **kwargs)

            # Determine the key generation function for django-ratelimit
            key_func = _get_key_function(key, root, info, kwargs, block)

            # Check if rate limited
            is_limited = is_ratelimited(
                request=request,
                group=group or func.__name__,
                fn=func,
                key=key_func,
                rate=rate,
                method=method,
                increment=True,
            )

            if is_limited and block:
                limit_key = (
                    key_func(group or func.__name__, request) if key_func else "unknown"
                )
                logger.warning(
                    f"Rate limit exceeded for {func.__name__} - Key: {limit_key}, Rate: {rate}"
                )
                raise RateLimitExceeded(format_rate_limit_message(rate))

            # Set rate limit headers on response if available
            if hasattr(request, "META"):
                request.META["X-RateLimit-Limit"] = rate
                request.META["X-RateLimit-Remaining"] = "N/A"

            return func(root, info, *args, **kwargs)

        return wrapper

    return decorator


def graphql_ratelimit_dynamic(
    get_rate: Callable[[any, any], str],
    key: Optional[str] = None,
    method: Union[str, list] = ALL,
    block: bool = True,
    group: Optional[str] = None,
):
    """
    Dynamic rate limit decorator that determines the rate based on user type.

    Args:
        get_rate: Callable that takes (root, info) and returns a rate string
        Other args same as graphql_ratelimit

    Example:
        @graphql_ratelimit_dynamic(get_rate=get_user_tier_rate("READ_MEDIUM"))
        def resolve_documents(root, info, **kwargs):
            ...
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(root, info, *args, **kwargs):
            # Same safety checks as graphql_ratelimit
            if not info or not hasattr(info, "context"):
                if not getattr(settings, "TESTING", False):
                    logger.warning(
                        f"Dynamic rate limiting skipped for {func.__name__}: info object is None or missing context. "
                        "This may indicate a security issue if happening in production."
                    )
                return func(root, info, *args, **kwargs)

            request = info.context
            if not request or not hasattr(request, "META"):
                if not getattr(settings, "TESTING", False):
                    logger.warning(
                        f"Dynamic rate limiting skipped for {func.__name__}: context is not a Django request object. "
                        f"Context type: {type(request).__name__}. "
                        "This may indicate a security issue if happening in production."
                    )
                return func(root, info, *args, **kwargs)

            # Skip rate limiting if explicitly disabled
            if getattr(settings, "RATELIMIT_DISABLE", False):
                return func(root, info, *args, **kwargs)

            # Get the dynamic rate
            rate = get_rate(root, info)

            # Determine the key generation function for django-ratelimit
            key_func = _get_key_function(key, root, info, kwargs, block)

            # Check if rate limited
            is_limited = is_ratelimited(
                request=request,
                group=group or func.__name__,
                fn=func,
                key=key_func,
                rate=rate,
                method=method,
                increment=True,
            )

            if is_limited and block:
                limit_key = (
                    key_func(group or func.__name__, request) if key_func else "unknown"
                )
                logger.warning(
                    f"Rate limit exceeded for {func.__name__} - Key: {limit_key}, Rate: {rate}"
                )
                raise RateLimitExceeded(format_rate_limit_message(rate))

            # Set rate limit headers on response if available
            if hasattr(request, "META"):
                request.META["X-RateLimit-Limit"] = rate
                request.META["X-RateLimit-Remaining"] = "N/A"

            return func(root, info, *args, **kwargs)

        return wrapper

    return decorator


def _get_key_function(key, root, info, kwargs, block):
    """
    Create a key function for django-ratelimit based on the key parameter.

    Args:
        key: Key specification (None, "ip", "user", "user_or_ip", or callable)
        root: GraphQL root object
        info: GraphQL info object
        kwargs: Resolver kwargs
        block: Whether to block on auth failure

    Returns:
        A key function compatible with django-ratelimit
    """
    if key is None or key == "user_or_ip":
        # Default: use user ID for authenticated, IP for anonymous
        def get_key(group, request):
            if request.user and request.user.is_authenticated:
                return f"user:{request.user.id}"
            else:
                return f"ip:{get_client_ip(request)}"

        return get_key
    elif key == "ip":
        return lambda g, r: f"ip:{get_client_ip(r)}"
    elif key == "user":

        def user_key(group, request):
            if not request.user or not request.user.is_authenticated:
                if block:
                    raise GraphQLError("Authentication required for this operation")
                return None
            return f"user:{request.user.id}"

        return user_key
    elif callable(key):
        # Custom key function - wrap it to match django-ratelimit signature
        return lambda g, r: key(root, info, **kwargs)
    else:
        # Static key
        return lambda g, r: str(key)
