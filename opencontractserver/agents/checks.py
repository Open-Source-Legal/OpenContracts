"""Django system checks for the agents / agent-tool subsystem."""

from typing import Any

from django.conf import settings
from django.core.checks import Tags, Warning, register


@register(Tags.security)
def check_privacy_filter_api_key(app_configs: Any, **kwargs: Any) -> list[Warning]:
    """Warn if the privacy-filter service is reachable but unauthenticated.

    Compose's ``${PRIVACY_FILTER_API_KEY:-}`` default keeps the service
    opt-in by parsing fine when the operator hasn't exported the env var
    — but the consequence is the privacy-filter container starts with an
    empty ``API_KEYS`` allowlist, and any caller on the Docker bridge can
    POST to it unauthenticated. The runtime client also logs a one-shot
    warning on first request, but operators typically notice startup
    output more reliably than per-request log lines, so we surface the
    same misconfiguration here as a system check.
    """
    warnings: list[Warning] = []

    privacy_filter_url = (getattr(settings, "PRIVACY_FILTER_URL", "") or "").strip()
    privacy_filter_api_key = (
        getattr(settings, "PRIVACY_FILTER_API_KEY", "") or ""
    ).strip()

    if privacy_filter_url and not privacy_filter_api_key:
        warnings.append(
            Warning(
                "PRIVACY_FILTER_URL is set but PRIVACY_FILTER_API_KEY is empty.",
                hint=(
                    "The privacy-filter PII detection service is running "
                    "without an API key, so any caller on the Docker bridge "
                    "can POST to it unauthenticated. Export "
                    "PRIVACY_FILTER_API_KEY in the production environment "
                    "or leave PRIVACY_FILTER_URL unset to disable the "
                    "PII-scan agent tool."
                ),
                id="agents.W001",
            )
        )

    return warnings
