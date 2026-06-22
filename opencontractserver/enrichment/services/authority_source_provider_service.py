"""Read-only view of the authority source-provider registry (the "scrapers").

The authority source providers (US Code / eCFR / Federal Register / agentic web
locator) are auto-discovered code classes with no DB row — until now they were
entirely invisible to the API. This service surfaces the registered providers
(name, supported prefixes, license, priority, enabled, requires-approval) plus a
``has_credentials`` flag derived from the existing encrypted-secrets vault, so
the Authority Console's Scrapers tab can show what can be ingested from where.

Read-only by design: enabling/disabling a provider and editing its secrets stay
with the provider class + the existing ``UpdateComponentSecretsMutation`` (the
one credential vault — this service never invents a parallel store).
"""

from __future__ import annotations

import logging
from typing import Any

from opencontractserver.enrichment.services.authority_permissions import (
    is_authority_admin,
)

logger = logging.getLogger(__name__)


class AuthoritySourceProviderService:
    """Superuser-only read of the registered authority source providers."""

    @staticmethod
    def list_providers(user) -> list[dict[str, Any]]:
        """Return the registered authority providers (empty for non-admins).

        Each entry: ``{name, class_name, title, supported_prefixes, license,
        priority, requires_approval, enabled, has_credentials}`` — the registry
        ClassVars plus whether the encrypted-secrets vault holds anything for the
        provider's class path. Ordered by ascending ``priority`` (the same order
        provider selection uses), then name.
        """
        if not is_authority_admin(user):
            return []

        from opencontractserver.documents.models import PipelineSettings
        from opencontractserver.pipeline.registry import (
            get_all_authority_source_providers_cached,
        )

        try:
            secrets = PipelineSettings.get_instance().get_secrets()
        except Exception:  # noqa: BLE001 — a vault read must not break the listing
            logger.warning("Could not read PipelineSettings secrets", exc_info=True)
            secrets = {}

        rows: list[dict[str, Any]] = []
        for defn in get_all_authority_source_providers_cached():
            cls = defn.component_class
            rows.append(
                {
                    "name": defn.name,
                    "class_name": defn.class_name,
                    "title": defn.title,
                    "supported_prefixes": list(
                        getattr(cls, "supported_prefixes", ()) or ()
                    ),
                    "license": getattr(cls, "license", None),
                    "priority": getattr(cls, "priority", None),
                    "requires_approval": bool(getattr(cls, "requires_approval", False)),
                    "enabled": bool(getattr(cls, "enabled", True)),
                    "has_credentials": bool(secrets.get(defn.class_name)),
                }
            )
        rows.sort(
            key=lambda r: (r["priority"] if r["priority"] is not None else 0, r["name"])
        )
        return rows
