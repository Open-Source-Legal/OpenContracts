"""
Tests for config.middleware.SecurityHeadersMiddleware.

Note: Referrer-Policy is handled by Django's built-in SecurityMiddleware
(via SECURE_REFERRER_POLICY) and is NOT tested here.
"""

import re

from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings

from config.middleware import SecurityHeadersMiddleware


class SecurityHeadersIntegrationTest(TestCase):
    """Verify middleware is properly wired in the MIDDLEWARE stack.

    Uses /api/health/ — an explicitly routed endpoint that returns 200 —
    to avoid relying on unrouted URLs whose status code may change.
    """

    def test_csp_header_present_on_real_response(self):
        """Ensure CSP header appears on responses from the full middleware stack."""
        response = self.client.get("/api/health/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Content-Security-Policy", response)

    def test_permissions_policy_header_present_on_real_response(self):
        """Ensure Permissions-Policy header appears on responses."""
        response = self.client.get("/api/health/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Permissions-Policy", response)

    def test_csp_contains_nonce_on_real_response(self):
        """Ensure the CSP header includes a per-request nonce in script-src."""
        response = self.client.get("/api/health/")
        csp = response["Content-Security-Policy"]
        self.assertRegex(csp, r"'nonce-[A-Za-z0-9_-]+'")

    def test_nonce_differs_between_requests(self):
        """Each request must get a unique nonce."""
        r1 = self.client.get("/api/health/")
        r2 = self.client.get("/api/health/")
        nonce1 = re.search(r"'nonce-([A-Za-z0-9_-]+)'", r1["Content-Security-Policy"])
        nonce2 = re.search(r"'nonce-([A-Za-z0-9_-]+)'", r2["Content-Security-Policy"])
        self.assertIsNotNone(nonce1)
        self.assertIsNotNone(nonce2)
        self.assertNotEqual(nonce1.group(1), nonce2.group(1))


def _dummy_response(request):
    """Minimal WSGI-style response stub."""
    return HttpResponse("ok")


class SecurityHeadersMiddlewareTests(SimpleTestCase):
    """Verify CSP and Permissions-Policy headers."""

    def setUp(self):
        self.factory = RequestFactory()

    # ------------------------------------------------------------------
    # Content-Security-Policy
    # ------------------------------------------------------------------
    @override_settings(
        SECURE_CSP_DIRECTIVES={
            "default-src": ["'self'"],
            "script-src": ["'self'"],
        },
        SECURE_PERMISSIONS_POLICY=None,
    )
    def test_csp_header_built_from_directives(self):
        mw = SecurityHeadersMiddleware(_dummy_response)
        response = mw(self.factory.get("/"))
        csp = response["Content-Security-Policy"]
        self.assertIn("default-src 'self'", csp)
        self.assertIn("script-src 'self'", csp)

    @override_settings(
        SECURE_CSP_DIRECTIVES={
            "script-src": ["'self'"],
        },
        SECURE_PERMISSIONS_POLICY=None,
    )
    def test_csp_nonce_injected_into_script_src(self):
        """The per-request nonce must appear in script-src."""
        mw = SecurityHeadersMiddleware(_dummy_response)
        request = self.factory.get("/")
        response = mw(request)
        csp = response["Content-Security-Policy"]
        # Nonce should be in script-src
        self.assertRegex(csp, r"script-src 'self' 'nonce-[A-Za-z0-9_-]+'")
        # And it should match what was set on the request
        self.assertIn(f"'nonce-{request.csp_nonce}'", csp)

    @override_settings(
        SECURE_CSP_DIRECTIVES={
            "default-src": ["'self'"],
        },
        SECURE_PERMISSIONS_POLICY=None,
    )
    def test_csp_nonce_not_in_non_script_directives(self):
        """Nonce should only appear in script-src, not other directives."""
        mw = SecurityHeadersMiddleware(_dummy_response)
        request = self.factory.get("/")
        response = mw(request)
        csp = response["Content-Security-Policy"]
        self.assertNotIn("nonce", csp)

    @override_settings(
        SECURE_CSP_DIRECTIVES=None,
        SECURE_PERMISSIONS_POLICY=None,
    )
    def test_csp_omitted_when_none(self):
        mw = SecurityHeadersMiddleware(_dummy_response)
        response = mw(self.factory.get("/"))
        self.assertNotIn("Content-Security-Policy", response)

    @override_settings(
        SECURE_CSP_DIRECTIVES={},
        SECURE_PERMISSIONS_POLICY=None,
    )
    def test_csp_omitted_when_empty_dict(self):
        """Empty dict should be treated as falsy — no CSP header emitted."""
        mw = SecurityHeadersMiddleware(_dummy_response)
        response = mw(self.factory.get("/"))
        self.assertNotIn("Content-Security-Policy", response)

    @override_settings(
        SECURE_CSP_DIRECTIVES={
            "connect-src": ["'self'", "wss:", "ws:"],
        },
        SECURE_PERMISSIONS_POLICY=None,
    )
    def test_csp_multiple_values_per_directive(self):
        mw = SecurityHeadersMiddleware(_dummy_response)
        response = mw(self.factory.get("/"))
        csp = response["Content-Security-Policy"]
        self.assertIn("connect-src 'self' wss: ws:", csp)

    @override_settings(
        SECURE_CSP_DIRECTIVES={
            "script-src": ["'self'"],
        },
        SECURE_PERMISSIONS_POLICY=None,
    )
    def test_csp_nonce_set_on_request(self):
        """Middleware must attach csp_nonce to the request object."""
        mw = SecurityHeadersMiddleware(_dummy_response)
        request = self.factory.get("/")
        mw(request)
        self.assertTrue(hasattr(request, "csp_nonce"))
        self.assertTrue(len(request.csp_nonce) > 0)

    @override_settings(
        SECURE_CSP_DIRECTIVES=None,
        SECURE_PERMISSIONS_POLICY=None,
    )
    def test_nonce_not_generated_when_csp_disabled(self):
        """No nonce should be generated when CSP is not configured."""
        mw = SecurityHeadersMiddleware(_dummy_response)
        request = self.factory.get("/")
        mw(request)
        self.assertFalse(hasattr(request, "csp_nonce"))

    @override_settings(
        SECURE_CSP_DIRECTIVES={
            "script-src": ["'self'"],
            "script-src-elem": ["'self'"],
        },
        SECURE_PERMISSIONS_POLICY=None,
    )
    def test_csp_nonce_injected_into_script_src_elem(self):
        """Nonce must also appear in script-src-elem when that directive exists."""
        mw = SecurityHeadersMiddleware(_dummy_response)
        request = self.factory.get("/")
        response = mw(request)
        csp = response["Content-Security-Policy"]
        nonce_token = f"'nonce-{request.csp_nonce}'"
        self.assertIn(f"script-src 'self' {nonce_token}", csp)
        self.assertIn(f"script-src-elem 'self' {nonce_token}", csp)

    # ------------------------------------------------------------------
    # Permissions-Policy
    # ------------------------------------------------------------------
    @override_settings(
        SECURE_PERMISSIONS_POLICY={
            "camera": [],
            "microphone": [],
            "geolocation": ["self"],
        },
        SECURE_CSP_DIRECTIVES=None,
    )
    def test_permissions_policy_header(self):
        mw = SecurityHeadersMiddleware(_dummy_response)
        response = mw(self.factory.get("/"))
        pp = response["Permissions-Policy"]
        self.assertIn("camera=()", pp)
        self.assertIn("microphone=()", pp)
        self.assertIn("geolocation=(self)", pp)

    @override_settings(
        SECURE_PERMISSIONS_POLICY=None,
        SECURE_CSP_DIRECTIVES=None,
    )
    def test_permissions_policy_omitted_when_none(self):
        mw = SecurityHeadersMiddleware(_dummy_response)
        response = mw(self.factory.get("/"))
        self.assertNotIn("Permissions-Policy", response)

    @override_settings(
        SECURE_PERMISSIONS_POLICY={},
        SECURE_CSP_DIRECTIVES=None,
    )
    def test_permissions_policy_omitted_when_empty_dict(self):
        """Empty dict should be treated as falsy — no header emitted."""
        mw = SecurityHeadersMiddleware(_dummy_response)
        response = mw(self.factory.get("/"))
        self.assertNotIn("Permissions-Policy", response)

    # ------------------------------------------------------------------
    # All headers together (default settings)
    # ------------------------------------------------------------------
    @override_settings(
        SECURE_CSP_DIRECTIVES={
            "default-src": ["'self'"],
            "object-src": ["'none'"],
        },
        SECURE_PERMISSIONS_POLICY={
            "camera": [],
        },
    )
    def test_all_headers_present(self):
        mw = SecurityHeadersMiddleware(_dummy_response)
        response = mw(self.factory.get("/"))
        self.assertIn("Content-Security-Policy", response)
        self.assertIn("Permissions-Policy", response)


class ValidateCSPDomainTests(SimpleTestCase):
    """Test config.middleware.validate_csp_domain (production code)."""

    def test_rejects_spaces(self):
        """A domain containing spaces would split CSP directive values."""
        from django.core.exceptions import ImproperlyConfigured

        from config.middleware import validate_csp_domain

        with self.assertRaises(ImproperlyConfigured):
            validate_csp_domain("evil.com script-src *")

    def test_rejects_semicolons(self):
        """A domain containing semicolons would inject new CSP directives."""
        from django.core.exceptions import ImproperlyConfigured

        from config.middleware import validate_csp_domain

        with self.assertRaises(ImproperlyConfigured):
            validate_csp_domain("evil.com; script-src *")

    def test_accepts_valid_domain(self):
        """A well-formed Auth0 domain should not raise."""
        from config.middleware import validate_csp_domain

        # Should not raise
        validate_csp_domain("myapp.us.auth0.com")
