"""Architecture invariants for ``config/graphql/`` — pytest enforcement.

This test enforces the Phase 6 service-layer rule from
``docs/refactor_plans/2026-05-19-service-layer-centralization-design.md``
on every CI run. The same scanner is also wired into a Django system
check (``opencontractserver/shared/checks.py``) so violations also fail
``manage.py`` commands at startup — pytest and Django give two
independent enforcement points pointing at the same source of truth in
``opencontractserver/shared/architecture_audit.py``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from opencontractserver.shared.architecture_audit import (
    ALLOWED_FILES,
    GRAPHQL_DIR,
    format_violation,
    iter_graphql_modules,
    scan_forbidden,
)


@pytest.mark.parametrize("module_path", iter_graphql_modules(), ids=lambda p: p.name)
def test_graphql_module_uses_service_layer(module_path: Path) -> None:
    """No forbidden Tier-0 identifier may appear in ``config/graphql/``.

    Allowed exceptions are listed in ``ALLOWED_FILES`` with a reason.
    On a hit the failure message includes the copy-pasteable recipe for
    each offending identifier (same recipe surfaced by the Django check
    ``opencontracts.E001``) so a dev who's never seen this rule before
    can fix the code without leaving the test output.
    """
    if module_path.name in ALLOWED_FILES:
        pytest.skip(f"{module_path.name} is on the documented allowlist")

    source = module_path.read_text(encoding="utf-8")
    hits = scan_forbidden(source)
    if hits:
        blocks = []
        for lineno, name in hits:
            short, hint = format_violation(module_path, lineno, name)
            blocks.append(f"{short}\n\n{hint}")
        separator = "\n\n" + ("=" * 72) + "\n\n"
        pytest.fail("\n\n" + separator.join(blocks) + "\n")


def test_allowlist_is_documented() -> None:
    """Every allowlist entry must exist in the filesystem.

    Prevents the allowlist from rotting silently when a file is renamed
    or removed.
    """
    for name in ALLOWED_FILES:
        assert (
            GRAPHQL_DIR / name
        ).is_file(), f"Allowlisted file {name!r} does not exist in {GRAPHQL_DIR}"


def test_django_system_check_is_registered() -> None:
    """The Phase-6 invariant must also be enforced at Django startup.

    Pytest runs in CI; the Django system check ALSO fires on every
    ``manage.py`` command (``runserver``, ``migrate``, ``shell``, ...) so
    a developer can't ship a violation without immediate local feedback.
    This test pins the system check to the wired-up state.
    """
    from django.core.checks import registry

    from opencontractserver.shared.checks import check_graphql_service_layer

    assert check_graphql_service_layer in registry.registry.get_checks(), (
        "opencontractserver.shared.checks.check_graphql_service_layer is not "
        "registered. Confirm ``opencontractserver.users.apps.UsersConfig.ready`` "
        "still imports ``opencontractserver.shared.checks``."
    )


def test_django_system_check_uses_same_audit() -> None:
    """The Django check must surface the same hits the pytest audit reports.

    Both enforcement layers route through
    ``opencontractserver.shared.architecture_audit.audit_graphql_modules`` —
    running the registered check and the audit function side-by-side
    pins them to agree.
    """
    from django.core.checks import run_checks

    from opencontractserver.shared.architecture_audit import audit_graphql_modules

    audit_hits = audit_graphql_modules()
    check_results = run_checks(tags=["architecture"])
    arch_errors = [r for r in check_results if r.id == "opencontracts.E001"]

    assert len(arch_errors) == len(audit_hits), (
        "Django check and pytest audit disagree on hit count: "
        f"check={len(arch_errors)} audit={len(audit_hits)}"
    )
