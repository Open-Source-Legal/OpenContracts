# Auto-assigned User Handles

OpenContracts auto-assigns every user a Reddit-style display handle (e.g.
`cleverFox`, `cleverFox42`) so the UI never falls through to a redacted
`user_<id>` placeholder for accounts whose Auth0 `name` / `given_name` /
`first_name` claims are absent.

Handles are read-only for end users in the initial rollout. The codebase is
structured to make a future "edit your handle" mutation a small follow-on
change without touching the storage model.

## At a glance

| Concern | Where |
|---|---|
| Field declaration | `opencontractserver/users/models.py` (`User.handle`) |
| Word lists | `opencontractserver/users/handle_wordlists.py` |
| Pure generator | `opencontractserver/users/handle_generator.py::generate_handle` |
| GraphQL exposure | `config/graphql/user_types.py::UserType.resolve_display_name` |
| Schema migration | `opencontractserver/users/migrations/0027_user_handle.py` |
| Backfill migration | `opencontractserver/users/migrations/0028_backfill_user_handles.py` |
| Re-run command | `opencontractserver/users/management/commands/regenerate_user_handles.py` |
| Tunables (constants) | `opencontractserver/constants/users.py` |

## Resolution chain

`UserType.displayName` is the single rendering choke point. The first
non-empty branch wins:

1. `name` (Auth0 `name` claim).
2. `given_name` + `family_name` (Auth0).
3. `first_name` + `last_name` (local Django fields).
4. **`handle`** — the auto-assigned Reddit-style handle.
5. `username` verbatim — only when `is_social_user=False`.
   `UserUnicodeUsernameValidator` allows `|` in locally-chosen usernames, so a
   local username like `alice|admin` is legitimate and is **not** redacted.
6. `user_<last N chars after the last "|">` — for social users only, where
   the raw OAuth `sub` (e.g. `google-oauth2|114688…`) must never be returned.
   `rsplit("|", 1)[-1]` strips the provider prefix even when the sub is short,
   keeping only the last `OAUTH_SUB_DISPLAY_SUFFIX_LENGTH` characters.
7. `user_<pk>` / `user_unknown` — last-resort safety net. With a populated
   `handle` column this branch is effectively unreachable.

## Generator

`generate_handle(scope_qs, *, handle_field="handle", rng=None)`:

- Two-phase loop:
  1. **Plain phase** — sample an `(adjective, noun)` pair, camelCase it
     (`cleverFox`), and check `scope_qs.filter(handle=…).exists()`. With
     ~56k base combinations and `HANDLE_PLAIN_ATTEMPTS = 50`, this almost
     always succeeds.
  2. **Suffixed phase** — if the plain phase exhausts, append a random 2–4
     digit suffix (`cleverFox42`). Bounded by `HANDLE_SUFFIXED_ATTEMPTS = 100`.
- Pure function — takes its scope queryset and an optional `random.Random`,
  returns a string. No side effects, no model knowledge.
- Logs a warning when the plain phase exhausts so an operator can spot
  namespace saturation before users start seeing numeric suffixes.
- Raises `RuntimeError` if even the suffixed phase exhausts. With the default
  word lists this is unreachable; a real failure indicates a corrupted list
  or a misconfigured environment.

The optional `rng` parameter lets tests pin output deterministically. In
production the default is `random.SystemRandom`.

## Auto-assignment on `User.save()`

`User.save()` assigns a handle when **all** of the following hold:

- The `handle` column exists (guarded with `table_has_column` so initial
  migrations that pre-date the column don't explode).
- `handle` is in the saved field set (or `update_fields=None`).
- The current value is empty.
- The username is not `Anonymous` (the django-guardian system account never
  surfaces to other users and never gets a handle — the migration and the
  management command apply the same exclusion to stay symmetric).

A bounded retry loop wraps the insert: `generate_handle`'s `.exists()` check
does not lock the row, so two concurrent inserts can sample the same
candidate before either commits. On `IntegrityError` we re-query to confirm
it was the `handle` column that collided (no string-parsing of DB error
messages — formats vary by driver), then re-roll up to
`HANDLE_INSERT_RETRY_ATTEMPTS = 5` times.

## Migrations

Two migrations, deliberately split:

1. `0027_user_handle` — schema change only (adds the `handle` column with a
   unique constraint).
2. `0028_backfill_user_handles` — data migration assigning a handle to every
   existing user lacking one. Re-runnable through the management command if
   the word list grows.

The data migration imports the live `generate_handle` rather than a frozen
historical snapshot. The function's signature is stable and pure, but if it
is ever moved or renamed update the import in this migration to match.
Within a single transaction PostgreSQL's `READ COMMITTED` isolation lets
each row's `save()` be visible to subsequent `generate_handle()` queries on
the same connection, so no per-row commit is needed.

## Management command

```bash
python manage.py regenerate_user_handles --dry-run
python manage.py regenerate_user_handles                 # missing only
python manage.py regenerate_user_handles --reroll-suffixed
python manage.py regenerate_user_handles --reroll-all    # destructive
```

| Mode | What it touches |
|---|---|
| (default) | Users with `handle IS NULL` or empty. |
| `--reroll-suffixed` | Above + users whose handle ends in digits. Use after enlarging the word list to upgrade collision-suffixed users to clean pairs. |
| `--reroll-all` | Every user (except Anonymous). Destructive — every previously surfaced handle changes. |
| `--dry-run` | Read-only preview. Implemented via `transaction.set_rollback(True)` inside a single atomic block. |

When rerolling, the user's own row stays in `scope_qs` (rather than being
excluded by pk) so its current DB handle blocks `generate_handle` from
re-selecting the same value. Setting `user.handle = None` in Python alone
would not reach the DB and a candidate equal to the existing handle would
otherwise round-trip.

## Tunables

`opencontractserver/constants/users.py`:

| Constant | Purpose | Default |
|---|---|---|
| `USER_HANDLE_MAX_LENGTH` | Field width on `User.handle`. | 64 |
| `HANDLE_PLAIN_ATTEMPTS` | Plain-phase generator attempts. | 50 |
| `HANDLE_SUFFIXED_ATTEMPTS` | Suffixed-phase generator attempts. | 100 |
| `HANDLE_SUFFIX_MIN` / `HANDLE_SUFFIX_MAX` | Numeric suffix range. | 10 / 9999 |
| `HANDLE_INSERT_RETRY_ATTEMPTS` | `User.save()` collision retries. | 5 |

## Word list rules

`handle_wordlists.py` is hand-curated. Editing rules (enforced by the test
suite):

- ASCII, lowercase, alphabetic only — no spaces, hyphens, or punctuation.
- Length 3–12 characters.
- Each word is unique to its list. Cross-list overlaps would let the
  generator emit degenerate same-word pairs like `cometComet`; the test
  `test_wordlists_have_no_cross_list_overlap` pins this invariant.
- `Anonymous` and other reserved usernames are not handles; they are
  excluded by `User.save()` / migration / management command guards.

To grow the namespace, append to the relevant list and re-run
`regenerate_user_handles --reroll-suffixed` to upgrade users who previously
got a numeric-suffixed handle.

## Tests

`opencontractserver/tests/test_user_handle.py` covers:

- Word-list invariants (uniqueness, alphabet, namespace size, no cross-list overlap).
- Generator: camelCase format, deterministic under fixed seed, skips existing
  values, falls back to suffixed phase under saturation, no PII leakage.
- `User.save()` auto-assignment, including the Anonymous-user exclusion.
- Management command modes (default, `--dry-run`, `--reroll-suffixed`,
  Anonymous-user exclusion under `--reroll-all`).
- `displayName` resolver chain priority across all six branches and schema
  exposure via the `me` query.
