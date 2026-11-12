"""Log-redaction invariant: no log call may format a raw kwargs/settings mapping.

Pipeline component kwargs are merged from ``PipelineSettings``, which carries
decrypted component secrets (API keys for parser and embedder services), and
the same mappings flow on into tasks, LLM tooling and MCP code. Interpolating
such a mapping into a log message writes the secret to the log stream, so a
log call may only format it through
``opencontractserver.utils.logging.redact_sensitive_kwargs``.

Single source of truth for the scanner. Enforced by
``opencontractserver/tests/architecture/test_log_redaction.py`` (pytest and
``manage.py test``). There is deliberately no Django system check: the scan
parses ~200 files (about a second), too much for every ``manage.py`` start —
see ``docs/development/architecture_invariants.md``. The module is pure
Python so a pre-commit hook or management command can reuse it.

What the scanner catches — an expression that *names* a kwargs/settings
mapping (a bare name ``all_kwargs``, an attribute ``self._settings`` or a
call ``self.get_component_settings()``) whose value is rendered by a
``logging``-style method call (``logger.info`` …):

* as the message itself (``logger.debug(all_kwargs)``) or a ``%``-style
  positional argument;
* through an f-string, ``str.format`` (positional or keyword), the ``%``
  operator (scalar, tuple or dict right-hand side) or ``+`` concatenation;
* as a keyword argument (``msg=``, ``extra={...}``) or inside a dict / tuple /
  list literal, including ``{**all_kwargs}``;
* wrapped in a transparent renderer: ``str``, ``repr``, ``format``,
  ``dict(...)`` / ``dict(**...)``, ``vars``, ``dataclasses.asdict``,
  ``pprint.pformat``, ``json.dumps``.

Not flagged: a call to ``redact_sensitive_kwargs`` (resolved through
``import … as`` aliases), and transformed expressions —
``all_kwargs.get("height")``, ``all_kwargs["x"]``, ``len(all_kwargs)``,
``sorted(all_kwargs)``, ``self.settings.api_url`` — so a scalar or a key
listing can be logged as is.

Known limits, by design — widen when a real case shows up:

* Detection is name-based. A secret-bearing dict under an unrelated name
  (``opts``, ``headers``, ``payload``) is not flagged.
* A helper whose name ends in ``kwargs``/``settings`` is treated as the
  mapping it returns (``self.get_component_settings()``), whatever its
  arguments. A helper that returns an already-safe view is accepted only with
  the trailing marker ``# log-redaction: safe`` on the log call, which is
  greppable and reviewed like an allowlist entry.
* ``redact_sensitive_kwargs`` itself matches *key names*
  (``SENSITIVE_KEY_PATTERNS``); a secret stored under an unusual key such as
  ``{"auth": ("user", "pass")}`` passes through un-redacted.
* Only ``logging``-style method calls are inspected; ``print``,
  ``warnings.warn`` and a bare ``info(...)`` imported from ``logging`` are not.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Iterator
from pathlib import Path

LOG_METHODS: frozenset[str] = frozenset(
    {"debug", "info", "warning", "error", "exception", "critical", "log"}
)
REDACTOR = "redact_sensitive_kwargs"
REDACTOR_PATH = "opencontractserver.utils.logging.redact_sensitive_kwargs"
SENSITIVE_NAME_SUFFIXES: tuple[str, ...] = ("kwargs", "settings")
# Callables that render their single argument as-is, so the secret still
# reaches the log. ``format`` covers both the builtin and ``"{}".format(x)``.
TRANSPARENT_WRAPPERS: frozenset[str] = frozenset(
    {"str", "repr", "format", "dict", "vars", "asdict", "pformat", "dumps"}
)
# Trailing comment that accepts one log call. Reserve it for helpers that
# return an already-redacted view; a raw mapping never qualifies.
SAFE_MARKER = "log-redaction: safe"

# This file lives at ``<repo-root>/opencontractserver/shared/``.
REPO_ROOT: Path = Path(__file__).resolve().parents[2]
SCAN_ROOTS: tuple[Path, ...] = (
    REPO_ROOT / "opencontractserver",
    REPO_ROOT / "config",
)

# Mirrors the AST condition in ``scan_log_calls`` (``node.func.attr in
# LOG_METHODS``); Python allows whitespace before the call parenthesis.
_LOG_CALL_RE = re.compile(r"\.(" + "|".join(sorted(LOG_METHODS)) + r")\s*\(")


def _expr_name(node: ast.AST) -> str | None:
    """The identifier an expression is named by: ``x``, ``a.x`` or ``x(...)``."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Call):
        return _expr_name(node.func)
    return None


def _peel_transparent(node: ast.expr) -> ast.expr | None:
    """One layer of as-is rendering around ``node``, or ``None`` if there is none."""
    if isinstance(node, ast.Call) and _expr_name(node.func) in TRANSPARENT_WRAPPERS:
        if len(node.args) == 1 and not node.keywords:
            return node.args[0]  # str(x), dict(x), json.dumps(x)
        if not node.args and len(node.keywords) == 1 and node.keywords[0].arg is None:
            return node.keywords[0].value  # dict(**x)
    if isinstance(node, ast.Dict) and len(node.keys) == 1 and node.keys[0] is None:
        return node.values[0]  # {**x}
    return None


def _unwrap_transparent(node: ast.expr) -> ast.expr:
    while (inner := _peel_transparent(node)) is not None:
        node = inner
    return node


def _raw_sensitive_mapping(
    node: ast.expr, redactor_names: frozenset[str]
) -> tuple[ast.expr, str] | None:
    """The unwrapped mapping and its name if ``node`` renders one unredacted."""
    node = _unwrap_transparent(node)
    if isinstance(node, ast.Call) and _expr_name(node.func) in redactor_names:
        return None
    name = _expr_name(node)
    if name and name.lower().endswith(SENSITIVE_NAME_SUFFIXES):
        return node, name
    return None


def _rendered_exprs(call: ast.Call) -> Iterator[ast.expr]:
    """Every expression whose value ends up in the logged output of ``call``.

    Each positional and keyword argument is rendered as a whole (the message,
    a ``%``-style argument, ``msg=``/``extra=``); inside them, only the
    constructs that render a sub-expression as-is are followed, so a value
    consumed by an opaque call (``len(x)``, ``sorted(x)``) is not yielded.
    """
    for root in (*call.args, *(kw.value for kw in call.keywords)):
        for part in ast.walk(root):
            if part is root:
                yield part
            if isinstance(part, ast.FormattedValue):  # f"{x}"
                yield part.value
            elif (
                isinstance(part, ast.Call)
                and isinstance(part.func, ast.Attribute)
                and part.func.attr == "format"
            ):  # "{} {}".format(a, x) / "{k}".format(k=x)
                yield from part.args
                yield from (kw.value for kw in part.keywords)
            elif isinstance(part, ast.BinOp) and isinstance(part.op, ast.Mod):
                yield part.right  # "%s" % x — tuple / dict RHS handled below
            elif isinstance(part, ast.BinOp) and isinstance(part.op, ast.Add):
                yield part.left  # "kwargs: " + str(x)
                yield part.right
            elif isinstance(part, ast.Dict):  # {"k": x} / {**x}
                yield from part.values
            elif isinstance(part, (ast.Tuple, ast.List, ast.Set)):  # (a, x)
                yield from part.elts


def _redactor_names(tree: ast.AST) -> frozenset[str]:
    """``redact_sensitive_kwargs`` plus every ``import … as`` alias bound to it."""
    names = {REDACTOR}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            names.update(
                alias.asname
                for alias in node.names
                if alias.name == REDACTOR and alias.asname
            )
    return frozenset(names)


def scan_log_calls(source: str) -> list[tuple[int, str]]:
    """Return ``(line, name)`` for each raw kwargs/settings mapping in a log call.

    A log call whose source lines carry ``SAFE_MARKER`` is skipped. A mapping
    reached by two paths (``"{}".format(x)`` is both a transparent wrapper and
    a ``.format`` call) is one hit; hits are ordered by position.
    """
    tree = ast.parse(source)
    redactor_names = _redactor_names(tree)
    lines = source.splitlines()
    hits: set[tuple[int, int, str]] = set()
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in LOG_METHODS
        ):
            continue
        end = node.end_lineno or node.lineno
        if any(SAFE_MARKER in line for line in lines[node.lineno - 1 : end]):
            continue
        for expr in _rendered_exprs(node):
            found = _raw_sensitive_mapping(expr, redactor_names)
            if found:
                mapping, name = found
                hits.add((mapping.lineno, mapping.col_offset, name))
    return [(line, name) for line, _, name in sorted(hits)]


def may_contain_hit(source: str) -> bool:
    """Lossless text pre-filter: a hit needs a sensitive name and a log call.

    Case-insensitive on the name, like ``_raw_sensitive_mapping``; the method
    names are matched exactly, like the AST condition.
    """
    lowered = source.lower()
    return any(s in lowered for s in SENSITIVE_NAME_SUFFIXES) and bool(
        _LOG_CALL_RE.search(source)
    )


def iter_candidate_modules() -> Iterator[tuple[Path, str]]:
    """Yield ``(path, source)`` for every scan-root module the pre-filter keeps."""
    for root in SCAN_ROOTS:
        for path in sorted(root.rglob("*.py")):
            try:
                source = path.read_text(encoding="utf-8")
            except OSError:
                # Unreadable file — out of scope rather than a failed audit;
                # genuine file-system failures surface elsewhere.
                continue
            if may_contain_hit(source):
                yield path, source


def audit_log_calls() -> list[tuple[Path, int, str]]:
    """Scan every candidate module; return ``(path, line, name)`` per hit."""
    return [
        (path, line, name)
        for path, source in iter_candidate_modules()
        for line, name in scan_log_calls(source)
    ]


def format_violation(path: Path, lineno: int, name: str) -> str:
    """One copy-pasteable line per hit, with the fix inline."""
    try:
        shown = path.relative_to(REPO_ROOT)
    except ValueError:
        shown = path
    return (
        f"{shown}:{lineno} formats `{name}` raw — wrap it in "
        f"{REDACTOR}(...) (accepts dicts and Settings dataclasses) or log the "
        f"scalar / key list you need instead."
    )
