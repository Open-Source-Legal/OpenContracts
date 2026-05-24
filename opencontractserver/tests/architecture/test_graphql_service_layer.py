"""Architecture invariants for ``config/graphql/``.

This module enforces the Phase 6 service-layer rule from
``docs/refactor_plans/2026-05-19-service-layer-centralization-design.md``:
every GraphQL resolver/mutation MUST reach models through a service in
``opencontractserver/<app>/services/`` — NOT through inline
``visible_to_user`` / ``user_can`` / ``user_has_permission_for_obj`` calls.

The test AST-scans every ``config/graphql/*.py`` file and fails if it
finds any of the forbidden Attribute accesses, Name references, or
``ImportFrom`` aliases, except in the explicit allowlist below.

The allowlist exists ONLY for genuine framework exceptions documented at
each entry. It is NOT a place to park "I'll migrate later" debt — the
PR that adds a file here must explain why.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

# Files in config/graphql/ that are permitted to retain the forbidden
# identifiers. Each entry MUST carry a comment explaining why.
ALLOWED_FILES: frozenset[str] = frozenset(
    {
        # ``filters.py`` uses django-filters FilterSets whose base
        # queryset is already filtered by the resolver; the
        # ``visible_to_user`` references that remain are comments
        # documenting that contract. The AST scan ignores comments,
        # so this entry is here only as belt-and-braces against
        # future code edits inside this file.
        "filters.py",
    }
)

FORBIDDEN_NAMES: frozenset[str] = frozenset(
    {"visible_to_user", "user_can", "user_has_permission_for_obj"}
)

GRAPHQL_DIR = Path(__file__).resolve().parents[3] / "config" / "graphql"


def _iter_graphql_modules() -> list[Path]:
    """Return every .py file directly under ``config/graphql/``."""
    return sorted(p for p in GRAPHQL_DIR.glob("*.py") if p.name != "__init__.py")


def _scan_forbidden(source: str) -> list[tuple[int, str]]:
    """Return ``(lineno, identifier)`` for each forbidden reference.

    Detects:
        - ``Model.objects.visible_to_user(...)``  → Attribute access
        - ``obj.user_can(...)`` / ``manager.user_can(...)``  → Attribute access
        - ``user_has_permission_for_obj(...)``  → Name access
        - ``from opencontractserver... import visible_to_user``  → Import alias

    Comments and docstrings are ignored (AST does not emit them).
    """
    tree = ast.parse(source)
    hits: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in FORBIDDEN_NAMES:
            hits.append((node.lineno, node.attr))
        elif isinstance(node, ast.Name) and node.id in FORBIDDEN_NAMES:
            hits.append((node.lineno, node.id))
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name in FORBIDDEN_NAMES:
                    hits.append((node.lineno, alias.name))
    return hits


@pytest.mark.parametrize("module_path", _iter_graphql_modules(), ids=lambda p: p.name)
def test_graphql_module_uses_service_layer(module_path: Path) -> None:
    """No forbidden Tier-0 identifier may appear in ``config/graphql/``.

    Allowed exceptions are listed in ``ALLOWED_FILES`` with a reason.
    """
    if module_path.name in ALLOWED_FILES:
        pytest.skip(f"{module_path.name} is on the documented allowlist")

    source = module_path.read_text(encoding="utf-8")
    hits = _scan_forbidden(source)
    if hits:
        formatted = "\n".join(
            f"  {module_path.name}:{lineno}: {name}" for lineno, name in hits
        )
        pytest.fail(
            f"\n\n{module_path.name} uses Tier-0 permission primitives directly.\n"
            f"Migrate to ``opencontractserver.shared.services.base.BaseService`` "
            f"or the relevant per-app service (see "
            f"``docs/architecture/query_permission_patterns.md``).\n\n"
            f"Offending sites:\n{formatted}\n"
        )


def test_allowlist_is_documented() -> None:
    """Every allowlist entry must exist in the filesystem.

    Prevents the allowlist from rotting silently when a file is renamed
    or removed.
    """
    for name in ALLOWED_FILES:
        assert (
            GRAPHQL_DIR / name
        ).is_file(), f"Allowlisted file {name!r} does not exist in {GRAPHQL_DIR}"
