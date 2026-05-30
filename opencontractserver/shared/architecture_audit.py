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

# Identifiers that consumer code MUST NOT reach into directly. They are the
# Tier-0 authorization primitives; the public entry point for any
# user-context caller is the service layer.
#
# SCOPE (read before trusting this as a blanket guarantee): this scanner —
# and therefore the ``opencontracts.E001`` system check and the pytest
# invariant that share it — enforces the ban *only* for files under
# ``config/graphql/``. CLAUDE.md rule 7 states the same rule as *policy* for
# the other user-context surfaces too (MCP tools in ``opencontractserver/mcp/``,
# LLM tools in ``opencontractserver/llms/tools/``, REST views, and
# user-context Celery tasks), but those surfaces are NOT mechanically scanned
# here and currently still contain correct-but-inline Tier-0 calls. Do not
# read a green E001 as "no inline Tier-0 anywhere" — only "none in
# config/graphql/". Expanding the scan to those packages is tracked as future
# work; if you add it, expect to migrate the existing inline usage first.
FORBIDDEN_NAMES: frozenset[str] = frozenset(
    {"visible_to_user", "user_can", "user_has_permission_for_obj"}
)

# Files in ``config/graphql/`` that are permitted to retain the forbidden
# identifiers. Each entry MUST carry a comment explaining why; the
# allowlist is NOT a place to park "I'll migrate later" debt — and it is
# NOT a place to park future real-code drift either. The allowlist is
# currently empty: ``filters.py`` no longer needs an entry because its
# only remaining references are comments, which the AST scanner already
# ignores (and leaving it allowlisted would silently permit a future
# inline reintroduction).
ALLOWED_FILES: frozenset[str] = frozenset()

# ``config/graphql`` lives at ``<repo-root>/config/graphql``. This file
# lives at ``<repo-root>/opencontractserver/shared/architecture_audit.py``,
# so ``parents[2]`` resolves to the repo root.
GRAPHQL_DIR: Path = Path(__file__).resolve().parents[2] / "config" / "graphql"


def iter_graphql_modules() -> list[Path]:
    """Return every ``.py`` file under ``config/graphql/`` (recursively).

    Uses ``rglob`` so resolver logic in subpackages (e.g.
    ``config/graphql/permissioning/permission_annotator/``) is scanned too —
    a non-recursive ``glob('*.py')`` would silently exempt those files and
    let a future inline Tier-0 reference slip through.

    Skips ``__init__.py`` (which never contains resolver logic). Returns
    an empty list if the directory does not exist — keeps the audit safe
    to call in unusual contexts (sdist installs, partial checkouts).
    """
    if not GRAPHQL_DIR.is_dir():
        return []
    return sorted(p for p in GRAPHQL_DIR.rglob("*.py") if p.name != "__init__.py")


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


# ---------------------------------------------------------------------------
# Failure-message recipes
# ---------------------------------------------------------------------------
#
# When the audit fires, the dev hitting it probably has no prior context on
# the service-layer rule. The recipes below are the answer to "OK, now what
# do I type?" — one per forbidden identifier, copy-pasteable, no doc-link
# chase required for the 95% case.
#
# Keep these recipes byte-for-byte aligned with the "Migration Recipes"
# section in ``docs/architecture/query_permission_patterns.md`` — they are
# the same content in two surfaces (failure output + browsable docs).

_RECIPES: dict[str, str] = {
    "visible_to_user": (
        "Forbidden:\n"
        "  Model.objects.visible_to_user(user)\n"
        "  Model.objects.visible_to_user(user).get(pk=id)\n"
        "\n"
        "Use instead:\n"
        "  # listing visible rows (queryset, chainable)\n"
        "  BaseService.filter_visible(Model, user, request=info.context)\n"
        "\n"
        "  # IDOR-safe single-object fetch (returns None instead of raising;\n"
        "  # collapses not-found and permission-denied into one branch)\n"
        "  obj = BaseService.get_or_none(Model, pk, user, request=info.context)\n"
        "  if obj is None:\n"
        "      return MyMutation(ok=False, message='Not found')\n"
    ),
    "user_can": (
        "Forbidden:\n"
        "  obj.user_can(user, PermissionTypes.X)\n"
        "  Model.objects.user_can(user, obj, PermissionTypes.X)\n"
        "\n"
        "Use instead:\n"
        "  # fail-fast gate — returns '' on grant, error string on denial\n"
        "  error = BaseService.require_permission(\n"
        "      obj, user, PermissionTypes.UPDATE, request=info.context\n"
        "  )\n"
        "  if error:\n"
        "      return MyMutation(ok=False, message=error)\n"
        "\n"
        "  # boolean for UI-state fields (can_edit_summary, can_view_history,\n"
        "  # etc.) — returns True/False\n"
        "  has_perm = BaseService.user_has(\n"
        "      obj, user, PermissionTypes.UPDATE, request=info.context\n"
        "  )\n"
    ),
    "user_has_permission_for_obj": (
        "Forbidden:\n"
        "  user_has_permission_for_obj(user, obj, permission)\n"
        "\n"
        "Use instead: the same BaseService helpers as ``user_can`` above —\n"
        "  - BaseService.require_permission(...) for a fail-fast gate\n"
        "  - BaseService.user_has(...) for a True/False UI flag\n"
    ),
}

_REQUIRED_IMPORT = "from opencontractserver.shared.services.base import BaseService"

_DOCS_POINTER = (
    "Why this rule exists: CLAUDE.md rule 7 + Phase 6 of the service-layer "
    "centralization (issue #1720). The forbidden identifiers are Tier-0 "
    "authorization primitives; the public entry point for any user-context "
    "caller is the service layer.\n"
    "Full reference: docs/architecture/query_permission_patterns.md "
    "(section 'Migration Recipes' has the same per-identifier playbook in "
    "Markdown form, plus the per-app service catalogue)."
)


def format_violation(module_path: Path, lineno: int, name: str) -> tuple[str, str]:
    """Return ``(short_message, hint_with_recipe)`` for one audit hit.

    Both enforcement surfaces (pytest fail message, Django ``Error``
    hint) call this so they stay byte-identical.

    ``short_message`` is one line — suitable for the headline ``msg=``
    of a Django ``Error`` or the leading line of a ``pytest.fail`` blob.
    ``hint_with_recipe`` is a multi-line block containing the
    copy-pasteable fix for ``name`` plus the required import plus a
    pointer to the docs.
    """
    short = (
        f"{module_path.name}:{lineno} uses Tier-0 permission primitive "
        f"`{name}` directly — config/graphql/ must reach models through "
        f"the service layer."
    )
    recipe = _RECIPES.get(
        name,
        # Should never happen — the AST scanner only emits identifiers
        # from FORBIDDEN_NAMES, every entry of which has a recipe. If a
        # future contributor adds a new forbidden name without a recipe
        # this fallback still gives the reader something usable.
        f"Forbidden identifier ``{name}``. Replace with the corresponding "
        f"BaseService helper (get_or_none / filter_visible / "
        f"require_permission / user_has) or a dedicated per-app service "
        f"method.\n",
    )
    hint = (
        "How to fix:\n"
        f"{recipe}\n"
        f"Required import: {_REQUIRED_IMPORT}\n"
        "On the single-object helpers (``get_or_none`` / ``require_permission`` "
        "/ ``user_has``) pass ``request=info.context`` so the Tier-2 "
        "permission cache is engaged. On the queryset helpers "
        "(``filter_visible`` / ``filter_visible_qs``) ``request=`` is accepted "
        "for API parity but is currently a no-op (the cache is keyed by "
        "single object, not by queryset).\n"
        "\n"
        f"{_DOCS_POINTER}"
    )
    return short, hint
