"""System checks for the users app — Auth0 admin-claim hardening."""

from typing import Any

from django.conf import settings
from django.core.checks import Critical, Tags, Warning, register


@register(Tags.security)
def check_auth0_superuser_allowlist(
    app_configs: Any, **kwargs: Any
) -> list[Warning | Critical]:
    """Warn when Auth0 is enabled but the superuser allowlist is empty.

    With an empty allowlist the JWT claim sync silently refuses every
    ``is_superuser=True`` claim, which is the desired safe default — but
    deployments that genuinely need a Django superuser via Auth0 must
    populate ``AUTH0_SUPERUSER_SUB_ALLOWLIST`` with the relevant subs. This
    check surfaces that decision at startup so it isn't discovered only
    when an admin login mysteriously fails to elevate.

    Severity escalates from Warning (``users.W001``) to Critical
    (``users.E001``) when at least one ``is_superuser=True`` row already
    exists in the DB, because that row will be silently demoted on the
    user's next claim sync. ``E001`` blocks ``manage.py check --deploy``
    and stops a deploy that would lock out the only admin account.
    """
    issues: list[Warning | Critical] = []

    if not getattr(settings, "USE_AUTH0", False):
        return issues

    allowlist = getattr(settings, "AUTH0_SUPERUSER_SUB_ALLOWLIST", [])
    if allowlist:
        return issues

    hint = (
        "Set AUTH0_SUPERUSER_SUB_ALLOWLIST to a comma-separated "
        "list of Auth0 sub values (e.g. 'auth0|abc123,google-oauth2|456') "
        "for users who should retain Django superuser. Tenants must "
        "still source the {namespace}is_superuser claim from "
        "app_metadata, never user_metadata."
    )

    # Defer ORM use until after Django is ready — system checks run during
    # AppConfig setup, but the DB may not be reachable in every context
    # (e.g. ``makemigrations``). Any failure falls back to the warning.
    has_existing_superuser = False
    try:
        from django.contrib.auth import get_user_model

        has_existing_superuser = (
            get_user_model().objects.filter(is_superuser=True).exists()
        )
    except Exception:
        # DB not reachable — emit the warning, but skip the critical
        # severity escalation so makemigrations etc. keep working.
        has_existing_superuser = False

    if has_existing_superuser:
        issues.append(
            Critical(
                "AUTH0_SUPERUSER_SUB_ALLOWLIST is empty while USE_AUTH0=True "
                "AND at least one existing Django superuser will be demoted "
                "on the next claim sync. Populate the allowlist BEFORE deploy "
                "to retain superuser access.",
                hint=hint,
                id="users.E001",
            )
        )
    else:
        issues.append(
            Warning(
                "AUTH0_SUPERUSER_SUB_ALLOWLIST is empty while USE_AUTH0=True. "
                "JWT-driven is_superuser elevation is blocked for every user. "
                "Existing superusers will be demoted on their next claim sync.",
                hint=hint,
                id="users.W001",
            )
        )

    return issues
