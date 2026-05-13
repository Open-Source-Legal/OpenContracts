"""System checks for the users app — Auth0 admin-claim hardening."""

from typing import Any

from django.conf import settings
from django.core.checks import Warning, register


@register()
def check_auth0_superuser_allowlist(app_configs: Any, **kwargs: Any) -> list[Warning]:
    """Warn when Auth0 is enabled but the superuser allowlist is empty.

    With an empty allowlist the JWT claim sync silently refuses every
    ``is_superuser=True`` claim, which is the desired safe default — but
    deployments that genuinely need a Django superuser via Auth0 must
    populate ``AUTH0_SUPERUSER_SUB_ALLOWLIST`` with the relevant subs. This
    check surfaces that decision at startup so it isn't discovered only
    when an admin login mysteriously fails to elevate.
    """
    warnings: list[Warning] = []

    if not getattr(settings, "USE_AUTH0", False):
        return warnings

    allowlist = getattr(settings, "AUTH0_SUPERUSER_SUB_ALLOWLIST", [])
    if not allowlist:
        warnings.append(
            Warning(
                "AUTH0_SUPERUSER_SUB_ALLOWLIST is empty while USE_AUTH0=True. "
                "JWT-driven is_superuser elevation is blocked for every user. "
                "Existing superusers will be demoted on their next claim sync.",
                hint=(
                    "Set AUTH0_SUPERUSER_SUB_ALLOWLIST to a comma-separated "
                    "list of Auth0 sub values (e.g. 'auth0|abc123,google-oauth2|456') "
                    "for users who should retain Django superuser. Tenants must "
                    "still source the {namespace}is_superuser claim from "
                    "app_metadata, never user_metadata."
                ),
                id="users.W001",
            )
        )

    return warnings
