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
    """Pin the allowlist's shape and prevent silent rot.

    The live allowlist is currently empty: ``filters.py`` no longer needs
    an entry because its only remaining references to forbidden Tier-0
    identifiers are inside comments, which the AST scanner ignores. If a
    future contributor adds an entry, the loop below also asserts that
    the entry points at a real file — preventing the allowlist from
    rotting silently when a file is renamed or removed.

    Asserting ``ALLOWED_FILES == frozenset()`` directly (rather than only
    iterating over its entries) keeps this test non-vacuous: a stray
    addition without a matching docstring/CHANGELOG update will trip
    here and force a deliberate sign-off.
    """
    assert ALLOWED_FILES == frozenset(), (
        "Service-layer lint guard allowlist is no longer empty: "
        f"{sorted(ALLOWED_FILES)}. Each entry MUST have a comment in "
        "``architecture_audit.ALLOWED_FILES`` explaining why the file "
        "cannot migrate, and the CHANGELOG / "
        "``docs/development/architecture_invariants.md`` text MUST be "
        "refreshed to match — see issue #1720 / #1782."
    )
    # The loop below is intentionally dead while ``ALLOWED_FILES`` is empty
    # — the assertion above short-circuits the test before we reach it.
    # Keep it in place so any future allowlist entry is validated for
    # filesystem existence (renames or deletions surface immediately
    # instead of silently rotting).
    for name in ALLOWED_FILES:
        assert (
            GRAPHQL_DIR / name
        ).is_file(), f"Allowlisted file {name!r} does not exist in {GRAPHQL_DIR}"


def test_django_system_check_is_registered() -> None:
    """The Phase-6 invariant must also be enforced at Django startup.

    Pytest runs in CI; the Django system check ALSO fires on every
    ``manage.py`` command (``runserver``, ``migrate``, ``shell``, ...) so
    a developer can't ship a violation without immediate local feedback.

    Two assertions pin the wiring:

    1. The ``architecture`` tag is registered at all (cheap public-API
       check via ``tag_exists`` — no internal-registry attribute access).
    2. ``check_graphql_service_layer`` specifically is registered under
       that tag. The earlier ``tag_exists("architecture")`` guard alone
       would silently pass if our check were deleted but some other
       ``"architecture"``-tagged check were added — pinning the function
       identity closes that gap.
    """
    from django.core.checks import tag_exists
    from django.core.checks.registry import registry

    from opencontractserver.shared.checks import check_graphql_service_layer

    assert tag_exists("architecture"), (
        "The ``architecture`` system-check tag is not registered. Confirm "
        "``opencontractserver.users.apps.UsersConfig.ready`` still imports "
        "``opencontractserver.shared.checks``."
    )

    # ``CheckRegistry.get_checks`` in Django 5.x takes no ``tags`` kwarg, so we
    # filter ``registered_checks`` by the per-check ``tags`` attribute the
    # ``@register("architecture")`` decorator sets — this pins the exact
    # function identity, not just tag presence.
    architecture_checks = [
        c
        for c in registry.registered_checks
        if "architecture" in getattr(c, "tags", ())
    ]
    assert check_graphql_service_layer in architecture_checks, (
        "``check_graphql_service_layer`` is not registered under the "
        "``architecture`` tag. Confirm the ``@register('architecture')`` "
        "decorator on ``opencontractserver.shared.checks.check_graphql_service_layer`` "
        "is still in place."
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


# ---------------------------------------------------------------------------
# Unit tests for the scanner / formatter / audit helpers
# ---------------------------------------------------------------------------
#
# The repository itself is (intentionally) clean, so the integration tests
# above never exercise the violation-reporting branches of
# ``architecture_audit`` / ``checks``. These unit tests inject synthetic
# violations so the audit and formatter branches are exercised — without
# any of them, the patch coverage on the new files drops below the
# codecov gate.


def test_scan_forbidden_detects_attribute_access() -> None:
    """``Model.objects.visible_to_user`` / ``obj.user_can`` — Attribute path."""
    source = (
        "def resolve(self, info):\n"
        "    return Model.objects.visible_to_user(info.context.user)\n"
        "\n"
        "def can_edit(self, info):\n"
        "    return self.obj.user_can(info.context.user, 'UPDATE')\n"
    )

    hits = scan_forbidden(source)

    names = sorted(name for _, name in hits)
    assert names == ["user_can", "visible_to_user"], hits


def test_scan_forbidden_detects_bare_name_access() -> None:
    """``user_has_permission_for_obj(...)`` called as a bare Name."""
    source = (
        "def resolve(self, info):\n"
        "    if user_has_permission_for_obj(info.context.user, self.obj, 'READ'):\n"
        "        return self.obj\n"
        "    return None\n"
    )

    hits = scan_forbidden(source)

    assert "user_has_permission_for_obj" in {name for _, name in hits}, hits


def test_scan_forbidden_detects_import_from_alias() -> None:
    """``from ... import visible_to_user`` — ImportFrom alias path."""
    source = (
        "from opencontractserver.permissions import visible_to_user\n"
        "\n"
        "x = visible_to_user\n"  # second hit (Name) but we only assert the import
    )

    hits = scan_forbidden(source)

    # At least one hit at the import line (line 1).
    import_hits = [h for h in hits if h[0] == 1]
    assert import_hits, f"Expected ImportFrom hit at line 1, got {hits}"
    assert import_hits[0][1] == "visible_to_user"


def test_scan_forbidden_ignores_unrelated_identifiers() -> None:
    """Identifiers outside ``FORBIDDEN_NAMES`` must not fire."""
    source = "x = foo.bar()\ny = baz()\nfrom collections import OrderedDict\n"
    assert scan_forbidden(source) == []


def test_format_violation_for_each_known_identifier(tmp_path: Path) -> None:
    """Every entry in ``FORBIDDEN_NAMES`` must produce a tailored recipe."""
    from opencontractserver.shared.architecture_audit import FORBIDDEN_NAMES

    sample = tmp_path / "fake_resolver.py"
    sample.write_text("# placeholder")

    for name in FORBIDDEN_NAMES:
        short, hint = format_violation(sample, 42, name)
        assert "fake_resolver.py:42" in short
        assert f"`{name}`" in short
        assert "How to fix:" in hint
        assert "BaseService" in hint
        assert "request=info.context" in hint
        assert "docs/architecture/query_permission_patterns.md" in hint


def test_format_violation_fallback_for_unknown_identifier(tmp_path: Path) -> None:
    """Unknown identifiers fall back to a generic-but-useful hint."""
    sample = tmp_path / "fake.py"
    sample.write_text("# placeholder")

    short, hint = format_violation(sample, 7, "some_future_primitive")

    assert "fake.py:7" in short
    assert "some_future_primitive" in short
    # Fallback hint still points at the BaseService helpers.
    assert "BaseService" in hint
    assert "get_or_none" in hint or "require_permission" in hint


def test_iter_graphql_modules_returns_empty_when_dir_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """If ``GRAPHQL_DIR`` is absent the audit must not crash — just no-op."""
    from opencontractserver.shared import architecture_audit

    nonexistent = tmp_path / "does-not-exist"
    monkeypatch.setattr(architecture_audit, "GRAPHQL_DIR", nonexistent)

    assert architecture_audit.iter_graphql_modules() == []


def test_audit_graphql_modules_reports_synthetic_violation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """``audit_graphql_modules`` must surface a real violation in a scanned file."""
    from opencontractserver.shared import architecture_audit

    fake_dir = tmp_path / "graphql"
    fake_dir.mkdir()
    # __init__.py is always skipped — make sure it is not counted.
    (fake_dir / "__init__.py").write_text("from . import bad_resolver\n")
    bad = fake_dir / "bad_resolver.py"
    bad.write_text(
        "def resolve(self, info):\n"
        "    return Thing.objects.visible_to_user(info.context.user)\n"
    )

    monkeypatch.setattr(architecture_audit, "GRAPHQL_DIR", fake_dir)

    hits = architecture_audit.audit_graphql_modules()

    assert len(hits) == 1, hits
    module_path, lineno, name = hits[0]
    assert module_path == bad
    assert name == "visible_to_user"
    assert lineno == 2


def test_audit_graphql_modules_skips_allowlisted(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Files named in ``ALLOWED_FILES`` must be skipped even if they contain hits.

    The live ``ALLOWED_FILES`` is currently empty (the per-file decision
    is enforced from the AST, not from a name list), so this test patches
    the constant alongside ``GRAPHQL_DIR`` to exercise the skip branch.
    """
    from opencontractserver.shared import architecture_audit

    fake_dir = tmp_path / "graphql"
    fake_dir.mkdir()
    allowed = fake_dir / "exempt.py"
    allowed.write_text(
        "def resolve(self, info):\n"
        "    return Thing.objects.visible_to_user(info.context.user)\n"
    )

    monkeypatch.setattr(architecture_audit, "GRAPHQL_DIR", fake_dir)
    monkeypatch.setattr(architecture_audit, "ALLOWED_FILES", frozenset({"exempt.py"}))

    assert architecture_audit.audit_graphql_modules() == []


def test_audit_graphql_modules_skips_unreadable_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """An ``OSError`` while reading a module must be tolerated, not raised."""
    from opencontractserver.shared import architecture_audit

    fake_dir = tmp_path / "graphql"
    fake_dir.mkdir()
    unreadable = fake_dir / "broken.py"
    unreadable.write_text("# placeholder")

    monkeypatch.setattr(architecture_audit, "GRAPHQL_DIR", fake_dir)

    original_read_text = Path.read_text

    def fake_read_text(self: Path, encoding: str | None = None) -> str:
        if self == unreadable:
            raise OSError("simulated unreadable file")
        return original_read_text(self, encoding=encoding)

    monkeypatch.setattr(Path, "read_text", fake_read_text)

    # No raise; unreadable file is simply skipped.
    assert architecture_audit.audit_graphql_modules() == []


def test_django_check_emits_error_when_audit_reports_violations(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The Django system check must convert audit hits into ``Error`` records."""
    from opencontractserver.shared import checks as arch_checks

    fake_dir = tmp_path / "graphql"
    fake_dir.mkdir()
    bad = fake_dir / "bad_resolver.py"
    bad.write_text(
        "def resolve(self, info):\n"
        "    return Thing.objects.visible_to_user(info.context.user)\n"
    )

    # Patching ``GRAPHQL_DIR`` in the shared audit module is enough — the
    # check imports the audit function lazily inside its body and re-reads
    # the constant on each call.
    from opencontractserver.shared import architecture_audit

    monkeypatch.setattr(architecture_audit, "GRAPHQL_DIR", fake_dir)

    errors = arch_checks.check_graphql_service_layer(app_configs=None)

    assert len(errors) == 1, errors
    error = errors[0]
    assert error.id == "opencontracts.E001"
    assert "bad_resolver.py" in error.msg
    assert "visible_to_user" in error.msg
    assert error.hint is not None
    assert "How to fix:" in error.hint


def test_django_check_returns_empty_when_repo_is_clean() -> None:
    """The clean repo (current state) must produce zero check errors."""
    from opencontractserver.shared.checks import check_graphql_service_layer

    assert check_graphql_service_layer(app_configs=None) == []
