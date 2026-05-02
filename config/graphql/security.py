"""
GraphQL security utilities.

- conditional_csrf_exempt: Skips CSRF only for token-authenticated requests.
- CsrfRejectLogFilter: Demotes the predictable 'CSRF token missing' WARNING
  to INFO so genuine CSRF anomalies stand out in production logs.
- DepthLimitValidationRule: Rejects queries deeper than a configurable limit.
- DisableIntrospection: Validation rule to block introspection in production.
"""

from __future__ import annotations

import functools
import logging
from typing import Any, Callable

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.middleware.csrf import (
    REASON_CSRF_TOKEN_MISSING,
    REASON_NO_CSRF_COOKIE,
    CsrfViewMiddleware,
)
from graphql import GraphQLError, ValidationRule
from graphql.language import ast

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# C1 — Conditional CSRF exemption
# ---------------------------------------------------------------------------
# Session-authenticated requests MUST present a CSRF token.  Requests that
# carry a recognised token-auth header (Bearer / API-key) are exempt because
# the credential is not automatically attached by the browser.


def _csrf_noop_get_response(request: HttpRequest) -> HttpResponse:
    # CsrfViewMiddleware only invokes ``get_response`` when we call
    # ``__call__``; we only use ``process_view``, so this is unreachable.
    raise NotImplementedError(
        "_csrf_noop_get_response is unreachable: CsrfViewMiddleware.process_view "
        "does not call get_response."
    )


_csrf_middleware = CsrfViewMiddleware(_csrf_noop_get_response)


# Token-auth schemes that may legitimately bypass CSRF. Browsers do not
# auto-attach the ``Authorization`` header on cross-origin requests, so any
# of these schemes — when *well-formed* — are not riding on browser state
# an attacker could exploit.
#
# Defense in depth: limiting the allow-list to schemes the app actually
# parses prevents a future change in browser behaviour (or a misconfigured
# proxy) from promoting an unrelated scheme into CSRF-bypass territory.
#
# ``Bearer`` matches ``graphql_jwt``'s ``JWT_AUTH_HEADER_PREFIX``; the API
# key prefix is read from settings (defaults to ``KEY``) so deployments can
# rebrand it without losing the bypass.
_DEFAULT_TOKEN_SCHEMES: tuple[str, ...] = ("Bearer",)


def _recognised_token_schemes() -> tuple[str, ...]:
    """Return the auth schemes we accept as evidence of token-based auth.

    Resolved at call time so test settings overrides (and future runtime
    config changes) take effect without re-importing the module.
    """
    schemes = list(_DEFAULT_TOKEN_SCHEMES)
    api_key_prefix = getattr(settings, "API_TOKEN_PREFIX", None)
    if api_key_prefix:
        schemes.append(str(api_key_prefix))
    return tuple(schemes)


def _is_recognised_token_credential(auth_header: str) -> bool:
    """Return True iff the header carries a *well-formed* token credential.

    A header counts as a token credential when, and only when:

    * it splits into exactly a ``<scheme> <credential>`` pair on whitespace,
    * the scheme matches one of the recognised prefixes (case-insensitive,
      per RFC 7235), and
    * the credential portion is non-empty.

    Empty, whitespace-only, scheme-only ("Bearer", "Bearer  "), or
    unrecognised-scheme ("Basic ...") values all return False, so the
    caller treats them as 'no token presented' and falls back to whatever
    cookie-based defense applies.
    """
    if not auth_header:
        return False

    parts = auth_header.split()
    if len(parts) != 2:
        # Either nothing, scheme-only, or scheme + credential containing
        # internal whitespace (which neither Bearer nor API-key emit).
        # ``str.split()`` strips and collapses whitespace, so neither side
        # of the unpacking below can be the empty string.
        return False

    scheme, _credential = parts
    scheme_lower = scheme.lower()
    return any(scheme_lower == s.lower() for s in _recognised_token_schemes())


def conditional_csrf_exempt(view_func: Callable[..., Any]) -> Callable[..., Any]:
    """
    Decorator that exempts a view from CSRF checks **only** when the request
    carries no browser-attached credential that an attacker could ride on.

    Three cases bypass CSRF:

    * The ``Authorization`` header carries a *well-formed* token credential
      using a recognised scheme (``Bearer``, ``KEY``, …). Browsers do not
      auto-attach this header cross-origin, so CSRF is irrelevant.
    * No session cookie at all.  Without a cookie there is nothing for an
      attacker on another origin to ride; the request is fully anonymous
      and CSRF would only block legitimate Bearer-only API clients that
      momentarily have no token (startup race, refresh in flight).

    Otherwise CSRF is enforced. Empty, whitespace-only, scheme-only, or
    unrecognised-scheme ``Authorization`` values are normalised to "no
    token presented" — see :func:`_is_recognised_token_credential` for the
    full grammar — so a malformed header cannot smuggle a session-cookie
    request into the token-auth bypass.
    """

    @functools.wraps(view_func)
    def wrapped_view(request: HttpRequest, *args: Any, **kwargs: Any) -> Any:
        auth_header = request.META.get("HTTP_AUTHORIZATION", "").strip()
        session_cookie_name = getattr(settings, "SESSION_COOKIE_NAME", "sessionid")
        has_session_cookie = bool(request.COOKIES.get(session_cookie_name))
        has_token_credential = _is_recognised_token_credential(auth_header)

        if has_token_credential or not has_session_cookie:
            # Token-based auth, or fully anonymous request with no cookie an
            # attacker could ride — CSRF check would have no security value.
            # ``_dont_enforce_csrf_checks`` is a Django-private flag read by
            # CsrfViewMiddleware to bypass CSRF on a per-request basis; not in stubs.
            setattr(request, "_dont_enforce_csrf_checks", True)
        else:
            # Session cookie present without a token — enforce CSRF as normal.
            reason = _csrf_middleware.process_view(request, view_func, args, kwargs)
            if reason is not None:
                return reason

        return view_func(request, *args, **kwargs)

    # Tell Django's CsrfViewMiddleware to skip this view entirely.
    # We handle CSRF enforcement manually above for session-based requests.
    # ``setattr`` because the wrapper's type doesn't advertise the attribute.
    setattr(wrapped_view, "csrf_exempt", True)
    return wrapped_view


# ---------------------------------------------------------------------------
# C2 — CSRF reject log volume control
# ---------------------------------------------------------------------------
# Django's ``CsrfViewMiddleware`` emits a WARNING for every reject via the
# ``django.security.csrf`` logger. The most common reject in our deployment
# is the benign "CSRF token missing." case — Bearer-only SPAs trip it on
# every cold start, drowning out genuine anomalies like origin-mismatch or
# bad-referer rejects that warrant attention.

# Standard CsrfViewMiddleware reasons. We only demote the predictable
# "missing" cases; everything else stays at WARNING so it remains visible
# in production log shipping. Sourced from Django (see imports above) so a
# future patch that tweaks the phrasing flows through automatically.
_BENIGN_CSRF_REASONS: frozenset[str] = frozenset(
    {
        REASON_CSRF_TOKEN_MISSING,
        REASON_NO_CSRF_COOKIE,
    }
)


class CsrfRejectLogFilter(logging.Filter):
    """Demote the routine 'CSRF token missing' WARNING to INFO.

    Genuine CSRF anomalies (origin mismatch, bad referer, mismatched
    token) keep their WARNING level so they can still page on. The filter
    is wired into the ``django.security.csrf`` logger via ``LOGGING`` in
    ``config/settings/base.py``.
    """

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: D401
        # Django's reject log uses ``logger.warning("Forbidden (%s): %s",
        # reason, request.path)`` — the reason is the first positional arg.
        args = record.args
        if not args or not isinstance(args, tuple):
            return True
        reason = args[0]
        if not isinstance(reason, str):
            return True
        if reason in _BENIGN_CSRF_REASONS:
            record.levelno = logging.INFO
            record.levelname = logging.getLevelName(logging.INFO)
        return True


# ---------------------------------------------------------------------------
# M1 — GraphQL query depth limiting
# ---------------------------------------------------------------------------

GRAPHQL_MAX_QUERY_DEPTH = getattr(settings, "GRAPHQL_MAX_QUERY_DEPTH", 15)


def _measure_depth(
    node: ast.Node,
    current_depth: int = 0,
    context: Any = None,
    visited_fragments: set[str] | None = None,
) -> int:
    """Recursively measure the maximum depth of selection sets.

    Follows fragment spreads through the fragment registry to prevent
    attackers from hiding depth behind named fragments.
    """
    if visited_fragments is None:
        visited_fragments = set()
    if not hasattr(node, "selection_set") or node.selection_set is None:
        return current_depth

    max_child = current_depth
    for selection in node.selection_set.selections:
        if isinstance(selection, ast.FieldNode):
            child_depth = _measure_depth(
                selection, current_depth + 1, context, visited_fragments
            )
        elif isinstance(selection, ast.InlineFragmentNode):
            child_depth = _measure_depth(
                selection, current_depth, context, visited_fragments
            )
        elif isinstance(selection, ast.FragmentSpreadNode) and context is not None:
            frag_name = selection.name.value
            if frag_name not in visited_fragments:
                visited_fragments.add(frag_name)
                fragment = context.get_fragment(frag_name)
                if fragment:
                    child_depth = _measure_depth(
                        fragment, current_depth, context, visited_fragments
                    )
                else:
                    child_depth = current_depth
            else:
                child_depth = current_depth  # cycle guard
        else:
            child_depth = current_depth
        if child_depth > max_child:
            max_child = child_depth
    return max_child


class DepthLimitValidationRule(ValidationRule):
    """
    Reject GraphQL queries that exceed ``GRAPHQL_MAX_QUERY_DEPTH`` levels of
    nesting.  Prevents resource-exhaustion attacks via deeply-nested relay
    queries.
    """

    def enter_operation_definition(self, node: ast.Node, *_args: Any) -> None:
        depth = _measure_depth(node, context=self.context)
        if depth > GRAPHQL_MAX_QUERY_DEPTH:
            self.report_error(
                GraphQLError(
                    f"Query depth {depth} exceeds maximum allowed depth "
                    f"of {GRAPHQL_MAX_QUERY_DEPTH}.",
                    [node],
                )
            )


# ---------------------------------------------------------------------------
# M2 — Disable introspection in production
# ---------------------------------------------------------------------------


class DisableIntrospection(ValidationRule):
    """
    Unconditionally block __schema and __type introspection queries.

    This rule is added to the schema's validation_rules list conditionally
    in schema.py (only when settings.DEBUG is False).
    """

    def enter_field(self, node: ast.FieldNode, *_args: Any) -> None:
        field_name = node.name.value
        if field_name in ("__schema", "__type"):
            self.report_error(
                GraphQLError(
                    "Introspection is disabled.",
                    [node],
                )
            )
