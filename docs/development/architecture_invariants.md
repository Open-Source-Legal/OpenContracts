# Architecture Invariants

OpenContracts enforces a small number of cross-cutting rules at the
codebase level — they're the "this MUST stay true" claims that hold the
permissioning, service-layer, and security model together. Each
invariant is enforced by **both** a pytest test (CI) **and** a Django
system check (`manage.py` startup), pointing at the same scanner, so a
violation cannot slip through one and reach `main`.

This page is the index. Per-invariant detail (recipes, rationale, full
service catalogue) lives in the doc each invariant links to.

## Currently enforced

### Service-layer access in `config/graphql/` (`opencontracts.E001`)

**Rule.** GraphQL resolvers / mutations / types in `config/graphql/`
must reach models through `opencontractserver/<app>/services/` —
never inline `visible_to_user`, `user_can`, or
`user_has_permission_for_obj`.

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

## Adding a new architecture invariant

The Phase-6 invariant is the pattern. To add another:

1. **Write the scanner** in `opencontractserver/shared/`. Pure
   Python — no Django imports — so it can run from inside
   `AppConfig.ready()`.
2. **Add a `format_violation`-style helper** so the failure message
   carries the copy-paste fix. Devs hitting your check for the first
   time shouldn't need to chase a doc link to know what to type.
3. **Register a Django system check** in
   `opencontractserver/shared/checks.py` (or a sibling module). Use
   `@register("architecture")` and a fresh `opencontracts.EXXX` id.
4. **Wire it into an existing `AppConfig.ready`** (the `users` app is
   the canonical home — see how the Phase-6 check is wired in
   `opencontractserver/users/apps.py`).
5. **Add the pytest invariant** under
   `opencontractserver/tests/architecture/`. Reuse the same scanner;
   add regression tests pinning the Django check's registered state
   and the agreement between both enforcement surfaces.
6. **Document the rule here.** Section name = invariant name. Link the
   detail doc with recipes and rationale.

The whole point of running the check in TWO places (pytest + Django
startup) is so devs get the failure on their **first** `manage.py`
invocation, not when CI runs hours later.
