"""
Custom admin login views supporting Auth0 authentication.

These views provide a seamless login experience that supports both
Auth0 authentication (when USE_AUTH0=True) and traditional password
authentication (always available as fallback).
"""

import logging
from typing import TYPE_CHECKING, Optional
from urllib.parse import urlencode

from django.conf import settings
from django.contrib import admin, messages
from django.contrib.auth import authenticate, login, logout
from django.http import (
    HttpRequest,
    HttpResponse,
    HttpResponseBase,
    HttpResponseNotAllowed,
    JsonResponse,
)

if TYPE_CHECKING:
    from opencontractserver.users.models import User
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View
from django.views.decorators.csrf import csrf_protect

from config.ratelimit.decorators import view_ratelimit
from config.ratelimit.rates import RateLimits

logger = logging.getLogger(__name__)

# Rate limits for admin login endpoints — read from shared RateLimits singleton.
# NOTE: These are captured at import time since @view_ratelimit evaluates the
# rate parameter at decoration time.  Calling RateLimits.reload() will NOT
# affect admin login rates; a server restart is required.
# Direct attribute access (no getattr fallback) so missing attributes surface
# as AttributeError at startup rather than silently falling back to a default.
ADMIN_LOGIN_RATE = RateLimits.AUTH_LOGIN
ADMIN_LOGIN_PAGE_RATE = RateLimits.ADMIN_LOGIN_PAGE


def _get_login_url() -> str:
    """Get the admin login URL using reverse() for proper URL resolution."""
    return reverse("admin_auth0_login")


def _get_admin_index_url() -> str:
    """Get the admin index URL using reverse() for proper URL resolution."""
    return reverse("admin:index")


def _get_next_url_from_request(request: HttpRequest) -> Optional[str]:
    """
    Extract the 'next' parameter from request, checking POST first then GET.

    This ensures consistent handling across all authentication methods.

    Args:
        request: The HTTP request object.

    Returns:
        The next URL from POST or GET params, or None if not present.
    """
    return request.POST.get("next") or request.GET.get("next")


def _get_safe_redirect_url(
    request: HttpRequest,
    url: Optional[str] = None,
    default: Optional[str] = None,
) -> str:
    """
    Validate and return a safe redirect URL.

    Prevents open redirect attacks by validating the URL against
    allowed hosts.

    Args:
        request: The HTTP request object.
        url: The URL to validate. If None, extracts from request params.
        default: Default URL if validation fails.

    Returns:
        The validated URL or default if validation fails.
    """
    if default is None:
        default = _get_admin_index_url()

    # If no URL provided, extract from request
    if url is None:
        url = _get_next_url_from_request(request)

    if not url:
        return default

    # Block backslash-prefixed URLs: browsers normalize "\evil.com" to
    # "//evil.com", which can bypass protocol-relative URL checks.
    if url.startswith("\\"):
        logger.warning("Blocked backslash-prefixed redirect URL: %s", url)
        return default

    # Validate the URL is safe (same host or in ALLOWED_HOSTS)
    if url_has_allowed_host_and_scheme(
        url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return url

    logger.warning("Blocked unsafe redirect URL: %s", url)
    return default


def _get_safe_logout_return_url(request: HttpRequest) -> str:
    """
    Get a safe return URL for Auth0 logout.

    Uses the configured ALLOWED_HOSTS to build a safe return URL,
    preventing Host header injection attacks.

    Args:
        request: The HTTP request object.

    Returns:
        A safe absolute URL for the Auth0 logout returnTo parameter.

    Raises:
        ImproperlyConfigured: If no safe host can be determined from ALLOWED_HOSTS.
    """
    from django.core.exceptions import ImproperlyConfigured

    allowed_hosts = getattr(settings, "ALLOWED_HOSTS", [])
    safe_host = None

    request_host = request.get_host().split(":")[0]
    if request_host in allowed_hosts or "*" in allowed_hosts:
        safe_host = request.get_host()
    else:
        # Use the first allowed host that isn't a wildcard
        for host in allowed_hosts:
            if host and host != "*" and not host.startswith("."):
                safe_host = host
                break

    if safe_host is None:
        raise ImproperlyConfigured(
            "Cannot determine safe logout return URL. "
            "ALLOWED_HOSTS must contain at least one non-wildcard host. "
            "Example: ALLOWED_HOSTS=['myapp.example.com', 'localhost']"
        )

    scheme = "https" if request.is_secure() else "http"
    login_path = reverse("admin_auth0_login")
    return f"{scheme}://{safe_host}{login_path}"


class Auth0AdminLoginView(View):
    """
    Custom admin login view that supports both Auth0 and password authentication.

    When USE_AUTH0 is enabled:
    - Displays Auth0 login button
    - Accepts JWT token for authentication
    - Falls back to password form if Auth0 fails

    When USE_AUTH0 is disabled:
    - Uses standard password authentication only
    """

    template_name = "admin/auth0_login.html"

    @method_decorator(csrf_protect)
    @method_decorator(view_ratelimit(rate=ADMIN_LOGIN_PAGE_RATE, block=False))
    def get(self, request: HttpRequest) -> HttpResponseBase:
        """Display the appropriate login form."""
        if getattr(request, "limited", False):
            logger.warning("Rate limit exceeded for admin login page GET")
            return HttpResponse(
                "Too many requests. Please try again later.",
                status=429,
                content_type="text/plain",
            )

        # Check if user is already authenticated
        if request.user.is_authenticated and request.user.is_staff:
            return redirect(_get_admin_index_url())

        # Validate the next URL to prevent open redirect attacks
        next_url = _get_safe_redirect_url(request)

        context = {
            "title": "Log in",
            "site_header": admin.site.site_header or "Django administration",
            "site_title": admin.site.site_title or "Django site admin",
            "use_auth0": getattr(settings, "USE_AUTH0", False),
            "next": next_url,
            "csp_nonce": self._get_csp_nonce(request),
        }

        # Add Auth0 settings if enabled
        if getattr(settings, "USE_AUTH0", False):
            context.update(
                {
                    "auth0_domain": getattr(settings, "AUTH0_DOMAIN", ""),
                    "auth0_client_id": getattr(settings, "AUTH0_CLIENT_ID", ""),
                    "auth0_audience": getattr(settings, "AUTH0_API_AUDIENCE", ""),
                }
            )

        return render(request, self.template_name, context)

    @method_decorator(csrf_protect)
    @method_decorator(view_ratelimit(rate=ADMIN_LOGIN_RATE, block=False))
    def post(self, request: HttpRequest) -> HttpResponseBase:
        """Handle token-based login via POST or password authentication."""
        if getattr(request, "limited", False):
            logger.warning("Rate limit exceeded for admin login POST")
            return JsonResponse(
                {
                    "error": (
                        "Too many login attempts. "
                        "Please wait a minute and try again."
                    )
                },
                status=429,
            )

        token = request.POST.get("token")
        if token:
            return self._authenticate_with_token(request, token)

        # Fall back to standard password authentication
        username = request.POST.get("username")
        password = request.POST.get("password")
        user = authenticate(request, username=username, password=password)

        if user is not None and user.is_staff:
            login(request, user)
            # Validate redirect URL to prevent open redirect attacks
            next_url = _get_safe_redirect_url(request)
            return redirect(next_url)

        messages.error(request, "Invalid credentials or insufficient permissions.")
        return redirect(_get_login_url())

    @staticmethod
    def _get_csp_nonce(request: HttpRequest) -> str:
        """Return the CSP nonce from the request, warning if it is missing.

        An empty nonce would produce an invalid CSP directive that silently
        blocks all JavaScript on the login page, so this must be loud.
        """
        nonce = getattr(request, "csp_nonce", None)
        if not nonce:
            logger.warning(
                "CSP nonce missing from request — SecurityHeadersMiddleware may "
                "be absent or misconfigured in MIDDLEWARE. Inline scripts on "
                "the admin login page will be blocked by CSP."
            )
            return ""
        return nonce

    def _authenticate_with_token(
        self, request: HttpRequest, token: str
    ) -> HttpResponseBase:
        """Authenticate user with Auth0 JWT token."""
        from config.jwt_utils import get_user_from_jwt_token

        try:
            user: Optional["User"] = get_user_from_jwt_token(token)

            if user and user.is_active:
                # Sync admin claims from token (only during admin login, not API requests)
                sync_success = self._sync_admin_claims(user, token)
                if not sync_success:
                    # Fail login if claim sync fails to prevent using stale permissions
                    logger.error(
                        "Admin claim sync failed for user %s, denying login",
                        user.username,
                    )
                    messages.error(request, "Authentication failed. Please try again.")
                    return redirect(_get_login_url())
                # Refresh user to get updated is_staff status
                user.refresh_from_db()

            if user and user.is_active and user.is_staff:
                # Use the Auth0AdminBackend for session login
                login(
                    request,
                    user,
                    backend="config.admin_auth.backends.Auth0AdminBackend",
                )
                # Validate redirect URL to prevent open redirect attacks
                next_url = _get_safe_redirect_url(request)
                logger.info("Admin login successful for user ID %s", user.pk)
                return redirect(next_url)
            else:
                logger.warning(
                    "User ID %s denied admin access",
                    user.pk if user else "unknown",
                )
                messages.error(
                    request, "You do not have permission to access the admin."
                )
                return redirect(_get_login_url())

        except Exception as e:
            logger.error("Admin token authentication failed: %s", e)
            messages.error(request, "Authentication failed. Please try again.")
            return redirect(_get_login_url())

    def _sync_admin_claims(self, user: "User", token: str) -> bool:
        """
        Sync admin claims from Auth0 token to user model.

        This is only called during admin login to avoid performance
        overhead on every API request.

        Returns:
            bool: True if sync succeeded (or was skipped), False if it failed.
        """
        if not getattr(settings, "USE_AUTH0", False):
            # Defensive check - should not be reached in practice since
            # _authenticate_with_token() is only called when Auth0 is active
            return True

        try:
            from config.graphql_auth0_auth.utils import (
                get_payload,
                sync_admin_claims_from_payload,
            )

            payload = get_payload(token)
            return sync_admin_claims_from_payload(user, payload)
        except Exception as e:
            # Log but don't fail authentication - claim sync is secondary
            logger.warning("Failed to sync admin claims for user ID %s: %s", user.pk, e)
            return False


class Auth0AdminLogoutView(View):
    """
    Handle admin logout with Auth0 session cleanup.

    Logout requires POST for CSRF protection (following Django's LogoutView pattern).
    GET requests are rejected with 405 Method Not Allowed.
    """

    @method_decorator(csrf_protect)
    def post(self, request: HttpRequest) -> HttpResponseBase:
        """Log out the user and redirect appropriately."""
        logout(request)

        if getattr(settings, "USE_AUTH0", False):
            # Redirect to Auth0 logout to clear Auth0 session
            # Use safe return URL to prevent Host header injection
            return_to = _get_safe_logout_return_url(request)
            auth0_domain = getattr(settings, "AUTH0_DOMAIN", "")
            auth0_client_id = getattr(settings, "AUTH0_CLIENT_ID", "")

            # Use urlencode to safely encode the returnTo parameter
            params = urlencode({"client_id": auth0_client_id, "returnTo": return_to})
            logout_url = f"https://{auth0_domain}/v2/logout?{params}"
            return redirect(logout_url)

        return redirect(_get_admin_index_url())

    def get(self, request: HttpRequest) -> HttpResponse:
        """
        Reject GET requests for logout.

        Logout via GET is insecure (CSRF vulnerability). Use POST instead.
        However, for backwards compatibility with browser bookmark/history,
        we redirect to admin index if user is not authenticated.
        """
        if not request.user.is_authenticated:
            return redirect(_get_admin_index_url())

        # Return 405 Method Not Allowed for authenticated users
        return HttpResponseNotAllowed(
            ["POST"],
            content="Logout requires POST request for CSRF protection. "
            "Please use the logout button in the admin interface.",
        )
