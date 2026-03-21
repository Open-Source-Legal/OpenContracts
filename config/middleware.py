"""
Custom security middleware for OpenContracts.

Adds Content-Security-Policy and Permissions-Policy headers to all responses.
Configuration is driven by Django settings (see base.py).

Each request gets a unique CSP nonce (attached as ``request.csp_nonce``) that
is injected into ``script-src``.  Templates can use ``{{ request.csp_nonce }}``
(or a view can pass it explicitly) to allow inline ``<script>`` blocks.

Note: Referrer-Policy is handled by Django's built-in SecurityMiddleware via
the SECURE_REFERRER_POLICY setting and is NOT duplicated here.
"""

import secrets

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


def validate_csp_domain(domain):
    """
    Validate that *domain* is safe to embed in a CSP header value.

    Raises ``ImproperlyConfigured`` if the domain contains characters
    that would break or inject into the CSP header (spaces split
    directive values; semicolons delimit directives).
    """
    if " " in domain or ";" in domain:
        raise ImproperlyConfigured(
            f"AUTH0_DOMAIN contains invalid characters for CSP: {domain!r}"
        )


class SecurityHeadersMiddleware:
    """
    Middleware that adds security headers to HTTP responses.

    Configured via Django settings:
        SECURE_CSP_DIRECTIVES      – dict of CSP directive name → list of values
        SECURE_PERMISSIONS_POLICY  – dict of feature name → list of allowlist tokens

    A per-request cryptographic nonce is generated and:
      1. Stored on ``request.csp_nonce`` for use in templates.
      2. Appended to ``script-src`` in the CSP header as ``'nonce-<value>'``.

    Note: Referrer-Policy is handled by Django's built-in SecurityMiddleware
    (django.middleware.security.SecurityMiddleware) via SECURE_REFERRER_POLICY.
    """

    def __init__(self, get_response):
        self.get_response = get_response

        self._csp_directives = getattr(settings, "SECURE_CSP_DIRECTIVES", None)
        self._permissions = self._build_permissions_policy(
            getattr(settings, "SECURE_PERMISSIONS_POLICY", None)
        )

    def __call__(self, request):
        # Only generate a nonce when CSP is active — avoids unnecessary work
        # when the middleware is present but CSP is not configured.
        if self._csp_directives:
            nonce = secrets.token_urlsafe(32)
            request.csp_nonce = nonce
        else:
            nonce = None

        response = self.get_response(request)

        if self._csp_directives:
            response["Content-Security-Policy"] = self._build_csp(
                self._csp_directives, nonce
            )

        if self._permissions:
            response["Permissions-Policy"] = self._permissions

        return response

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_csp(directives, nonce=None):
        """
        Build a CSP header string from a directive dict.

        If *nonce* is provided it is appended to ``script-src`` as
        ``'nonce-<value>'``.

        Example input::

            {
                "default-src": ["'self'"],
                "script-src":  ["'self'"],
                "connect-src": ["'self'"],
            }

        Returns ``"default-src 'self'; script-src 'self' 'nonce-abc'; ..."``
        or ``None`` if *directives* is falsy.
        """
        if not directives:
            return None
        nonce_directives = {"script-src", "script-src-elem"}
        parts = []
        for directive, values in directives.items():
            if nonce and directive in nonce_directives:
                values = list(values) + [f"'nonce-{nonce}'"]
            parts.append(f"{directive} {' '.join(values)}")
        return "; ".join(parts)

    @staticmethod
    def _build_permissions_policy(features):
        """
        Build a Permissions-Policy header string from a feature dict.

        Example input::

            {
                "camera":     [],
                "microphone": [],
                "geolocation": ["self"],
            }

        Returns ``"camera=(), microphone=(), geolocation=(self)"``
        or ``None`` if *features* is falsy.
        """
        if not features:
            return None
        parts = []
        for feature, allowlist in features.items():
            if allowlist:
                inner = " ".join(allowlist)
                parts.append(f"{feature}=({inner})")
            else:
                parts.append(f"{feature}=()")
        return ", ".join(parts)
