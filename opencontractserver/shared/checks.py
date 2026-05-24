"""Django system checks enforcing the OpenContracts architecture invariants.

The single check registered here mirrors the pytest invariant in
``opencontractserver/tests/architecture/test_graphql_service_layer.py``.
Phase 6 (issue #1720) made every GraphQL resolver/mutation route through
the service layer; this check fires on every management command (so
``runserver``, ``migrate``, ``shell``, ``test``, ``check --deploy``, ...)
and blocks startup if any ``config/graphql/`` file inlines a Tier-0
permission primitive.

Wired in by ``opencontractserver.users.apps.UsersConfig.ready`` (the same
``ready()`` that already registers the Auth0 superuser allowlist check).
"""

from typing import Any

from django.core.checks import Error, register


@register("architecture")
def check_graphql_service_layer(app_configs: Any, **kwargs: Any) -> list[Error]:
    """Fail Django startup on any inline Tier-0 use in ``config/graphql/``.

    Same scanner as the pytest invariant — they import the audit function
    from ``opencontractserver.shared.architecture_audit`` so there is one
    source of truth for what counts as a violation.

    Severity is ``Error`` (``opencontracts.E001``): Django blocks any
    management command when an Error-level check fires, which is exactly
    the "fail on startup" semantic we want. Use the migration recipe in
    ``docs/architecture/query_permission_patterns.md`` to fix any hit —
    ``BaseService.get_or_none`` / ``filter_visible`` / ``require_permission``
    / ``user_has`` cover every pattern the rule replaces.
    """
    # Deferred import — keeps ``shared.checks`` cheap to import; the AST
    # scan only runs when the registered check actually fires.
    from opencontractserver.shared.architecture_audit import audit_graphql_modules

    issues: list[Error] = []
    for module_path, lineno, name in audit_graphql_modules():
        issues.append(
            Error(
                (
                    f"{module_path.name}:{lineno} uses Tier-0 permission "
                    f"primitive `{name}` directly. config/graphql/ must "
                    "reach models through the service layer."
                ),
                hint=(
                    "Replace with BaseService.get_or_none / filter_visible "
                    "/ require_permission / user_has, or the relevant "
                    "per-app service. See "
                    "docs/architecture/query_permission_patterns.md."
                ),
                id="opencontracts.E001",
            )
        )
    return issues
