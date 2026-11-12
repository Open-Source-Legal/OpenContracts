# Architecture Invariants

OpenContracts enforces a small number of cross-cutting rules at the
codebase level — they're the "this MUST stay true" claims that hold the
permissioning, service-layer, and security model together. Each
invariant is enforced by a pytest test (CI) and, where the scan is cheap
enough to run at `manage.py` startup, **also** by a Django system check
pointing at the same scanner, so a violation cannot slip through one and
reach `main`.

This page is the index. Per-invariant detail (recipes, rationale, full
service catalogue) lives in the doc each invariant links to.

## Currently enforced

### Service-layer access in `config/graphql/` (`opencontracts.E001`)

**Rule.** GraphQL resolvers / mutations / types in `config/graphql/`
must reach models through `opencontractserver/<app>/services/` —
never inline `visible_to_user`, `user_can`, or
`user_has_permission_for_obj`.

**Scope of mechanical enforcement.** Both the system check and the pytest
invariant scan **`config/graphql/` only** (recursively, including
subpackages such as `permissioning/permission_annotator/`). The same rule
is *policy* for the other user-context surfaces — MCP tools
(`opencontractserver/mcp/`), LLM tools (`opencontractserver/llms/tools/`),
REST views, and user-context Celery tasks — but those are **not** scanned
today and still contain correct-but-inline Tier-0 calls. A green
`opencontracts.E001` means "no inline Tier-0 in `config/graphql/`," not
"none anywhere." Expanding the scan (after migrating their existing inline
usage) is tracked as future work.

**Why.** Phase 6 of the Service Layer Centralization initiative (issue
#1720). The forbidden identifiers are Tier-0 authorization primitives;
the public entry point for any user-context caller is the service
layer. Inline use bypasses the request-scoped permission cache, scatters
permission logic across hundreds of resolvers, and silently re-implements
IDOR-prevention semantics that the service layer already encodes.

**Where it fires.**
- **Django system check** —
  `opencontractserver/shared/checks.py::check_graphql_service_layer`,
  registered from `opencontractserver/users/apps.py::UsersConfig.ready`.
  Emits `Error` with id `opencontracts.E001`. Blocks every
  `manage.py` command (`runserver`, `migrate`, `shell`, `test`,
  `check --deploy`) with a non-zero exit code.
- **Pytest invariant** —
  `opencontractserver/tests/architecture/test_graphql_service_layer.py`.
  Fires in CI on every push.

**Source of truth.**
`opencontractserver/shared/architecture_audit.py` holds the AST scanner,
the `ALLOWED_FILES` allowlist, and `format_violation` which builds the
failure messages. Both enforcement surfaces call into this module so
the rule has one definition.

**How to fix a violation.** The error message itself prints a
copy-pasteable recipe for each forbidden identifier; you don't need
to leave the failure output for the 95% case. The same recipes (with
extra context and the full per-app service catalogue) live in
[`docs/architecture/query_permission_patterns.md`](../architecture/query_permission_patterns.md),
section "Migration Recipes".

**How to extend the allowlist.** The allowlist
(`opencontractserver.shared.architecture_audit.ALLOWED_FILES`) is a
last-resort escape hatch, not Phase-6-leftover debt. Each entry MUST
have a comment explaining why the file can't migrate. As of this
writing the allowlist is empty: every `config/graphql/` module is
scanned, and `filters.py` no longer needs an entry because its only
remaining references to forbidden identifiers are inside comments
(which the AST scanner already ignores). If you think you need a new
entry, write the justification in the comment and expect reviewer
pushback asking whether a per-app service method would suffice instead.

### No raw kwargs / settings mappings in log calls (tests only)

**Rule.** A log call may not render a kwargs or settings mapping — a
name, attribute or call ending in `kwargs`/`settings` — as the message, a
`%`-style argument or a keyword argument, nor through an f-string,
`str.format`, the `%` operator, `+` concatenation, a dict/tuple literal or a
transparent wrapper (`str`, `repr`, `dict(**…)`, `vars`, `asdict`,
`pformat`, `json.dumps`) — except via
`opencontractserver/utils/logging.py::redact_sensitive_kwargs`, which
accepts dicts and `Settings` dataclasses. Component kwargs are merged from
`PipelineSettings` and carry decrypted secrets; the same mappings flow into
tasks, LLM tooling and MCP code.

**Scope.** Every module under `opencontractserver/` and `config/`, tests
included. A lossless, case-insensitive text pre-filter keeps the parse to
~200 files.

**Where it fires.** `opencontractserver/tests/architecture/test_log_redaction.py`
(`SimpleTestCase`, so pytest and `manage.py test` both collect it). There is
no Django system check: the scan takes about a second, too much for every
`manage.py` start.

**Source of truth.** `opencontractserver/shared/log_redaction_audit.py` —
scanner, pre-filter, `audit_log_calls`, `format_violation`, and a docstring
listing what is caught and the deliberate limits (name-based detection;
transformed expressions such as `.get(...)`, `len(...)`, `sorted(...)`
ignored; key-name redaction). Pure Python, so a pre-commit hook or
management command can call it.

**How to fix a violation.** Wrap the mapping —
`redact_sensitive_kwargs(all_kwargs)` or `redact_sensitive_kwargs(self.settings)`
— or log the scalar you need (`all_kwargs.get("height")`) or the key list.
A helper that returns an already-safe view is accepted with a trailing
`# log-redaction: safe — <why>` on the log call; treat the marker like an
allowlist entry (greppable, needs a reason, never on a raw mapping).

**Related guarantee.** `SECRET` settings are dropped from every component and
tool `Settings` repr at class-definition time
(`opencontractserver/pipeline/base/settings_schema.py::hide_secret_settings_from_repr`,
called from `PipelineComponentBase.__init_subclass__` and
`BaseTool.__init_subclass__`), so `f"{self.settings}"` cannot write a key even
where the scanner is blind. `AgentConfig.api_key` is `repr=False` for the same
reason.

## Adding a new architecture invariant

The Phase-6 invariant is the pattern. To add another:

1. **Write the scanner** in `opencontractserver/shared/`
   (`architecture_audit.py` and `log_redaction_audit.py` are the two
   today). Pure Python — no Django imports — so it can run from
   `AppConfig.ready()`, a pre-commit hook or a management command, and the
   test module only *runs* it.
2. **Add a `format_violation`-style helper** so the failure message
   carries the copy-paste fix. Devs hitting your check for the first
   time shouldn't need to chase a doc link to know what to type.
3. **Pick the enforcement surfaces by scan cost.** A scan that is
   negligible at startup (the ~41-file `config/graphql/` scan is sub-50 ms)
   also gets a Django system check: register it in
   `opencontractserver/shared/checks.py` with `@register("architecture")`
   and a fresh `opencontracts.EXXX` id, wire it into
   `opencontractserver/users/apps.py::UsersConfig.ready`, and pin the
   registered state in the test. A tree-wide scan (the log-redaction scan
   parses ~200 files, about a second) stays test-only — say so in its
   docstring and on this page.
4. **Add the test** under `opencontractserver/tests/architecture/`,
   reusing the same scanner. Prefer `SimpleTestCase` so `manage.py test`
   collects it as well as pytest.
5. **Document the rule here.** Section name = invariant name. Link the
   detail doc with recipes and rationale.

Running a cheap check in TWO places (pytest + Django startup) gets devs the
failure on their **first** `manage.py` invocation, not when CI runs hours
later. A check too slow for startup still has one source of truth in
`shared/` that a hook can call.
