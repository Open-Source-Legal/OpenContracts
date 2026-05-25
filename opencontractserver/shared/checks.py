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

    Same scanner as the pytest invariant — both call
    ``opencontractserver.shared.architecture_audit.audit_graphql_modules``
    so there is one source of truth for what counts as a violation, and
    ``architecture_audit.format_violation`` builds the per-identifier
    recipe so both surfaces show byte-identical fix instructions.

    Severity is ``Error`` (``opencontracts.E001``): Django blocks any
    management command (``runserver``, ``migrate``, ``shell``, ``test``,
    ``check --deploy``) when an Error-level check fires, which is the
    "fail on startup" semantic we want.

    Cost note: the AST scan runs once per ``manage.py`` invocation
    (Django's system-check framework fires every registered check on
    every command — ``migrate``, ``shell``, ``runserver``, ``test``…).
    With ~41 files in ``config/graphql/`` this is sub-50 ms and
    negligible relative to Django startup, so the check intentionally
    runs synchronously rather than being fast-pathed or gated behind
    ``DEBUG`` — the "fail on first management command" semantic is the
    whole point of dual-enforcement, and skipping the scan in some
    contexts would create silent gaps. Revisit only if the scan ever
    becomes a measurable slice of cold-start time.
    """
    # Deferred import — keeps ``shared.checks`` cheap to import; the AST
    # scan only runs when the registered check actually fires.
    from opencontractserver.shared.architecture_audit import (
        audit_graphql_modules,
        format_violation,
    )

    issues: list[Error] = []
    for module_path, lineno, name in audit_graphql_modules():
        short, hint = format_violation(module_path, lineno, name)
        issues.append(Error(short, hint=hint, id="opencontracts.E001"))
    return issues
