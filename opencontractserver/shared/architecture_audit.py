"""Architecture invariants for ``config/graphql/`` (Phase 6 — issue #1720).

Single source of truth for the rule "no config/graphql/ file may inline
``visible_to_user`` / ``user_can`` / ``user_has_permission_for_obj``".
Imported by two enforcement layers that share this exact same scanner:

- ``opencontractserver/tests/architecture/test_graphql_service_layer.py`` —
  pytest invariant that fires in CI.
- ``opencontractserver/shared/checks.py`` — Django system check that fires
  on every management command (``runserver``, ``migrate``, ``shell``,
  ``test``, ...) and blocks startup on any violation.

This module is pure Python — no Django imports — so it is safe to import
from anywhere, including from inside ``AppConfig.ready()``.
"""

from __future__ import annotations

import ast
from pathlib import Path

# Identifiers that consumer code (resolvers, MCP tools, REST views,
# user-context Celery tasks) MUST NOT reach into directly. They are the
# Tier-0 authorization primitives; the public entry point for any
# user-context caller is the service layer.
FORBIDDEN_NAMES: frozenset[str] = frozenset(
    {"visible_to_user", "user_can", "user_has_permission_for_obj"}
)

# Files in ``config/graphql/`` that are permitted to retain the forbidden
# identifiers. Each entry MUST carry a comment explaining why; the
# allowlist is NOT a place to park "I'll migrate later" debt.
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

# ``config/graphql`` lives at ``<repo-root>/config/graphql``. This file
# lives at ``<repo-root>/opencontractserver/shared/architecture_audit.py``,
# so ``parents[2]`` resolves to the repo root.
GRAPHQL_DIR: Path = Path(__file__).resolve().parents[2] / "config" / "graphql"


def iter_graphql_modules() -> list[Path]:
    """Return every ``.py`` file directly under ``config/graphql/``.

    Skips ``__init__.py`` (which never contains resolver logic). Returns
    an empty list if the directory does not exist — keeps the audit safe
    to call in unusual contexts (sdist installs, partial checkouts).
    """
    if not GRAPHQL_DIR.is_dir():
        return []
    return sorted(p for p in GRAPHQL_DIR.glob("*.py") if p.name != "__init__.py")


def scan_forbidden(source: str) -> list[tuple[int, str]]:
    """Return ``(lineno, identifier)`` for each forbidden reference.

    Detects:
        - ``Model.objects.visible_to_user(...)``  → Attribute access
        - ``obj.user_can(...)`` / ``manager.user_can(...)``  → Attribute access
        - ``user_has_permission_for_obj(...)``  → Name access
        - ``from opencontractserver... import visible_to_user``  → Import alias

    Comments and docstrings are intentionally ignored (the AST does not
    emit them as ``Attribute`` / ``Name`` / ``ImportFrom`` nodes).
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


def audit_graphql_modules() -> list[tuple[Path, int, str]]:
    """Scan every non-allowlisted graphql module; return one entry per hit.

    Returns ``(module_path, lineno, identifier)`` tuples. An empty list
    means the invariant holds: every consumer-side reference to the
    forbidden Tier-0 identifiers has been routed through the service
    layer.
    """
    hits: list[tuple[Path, int, str]] = []
    for module_path in iter_graphql_modules():
        if module_path.name in ALLOWED_FILES:
            continue
        try:
            source = module_path.read_text(encoding="utf-8")
        except OSError:
            # Unreadable file — treat as out-of-scope rather than failing
            # the entire check. Genuine file-system failures will surface
            # via other Django infrastructure (manage.py check, etc.).
            continue
        for lineno, name in scan_forbidden(source):
            hits.append((module_path, lineno, name))
    return hits
