- **Second-round desktop usability + review fixes** (from a clean-room re-test
  of the one-step flow and adversarial PR reviews):
  - **Password prompt moved to the very start of the first run**
    (`opencontractserver/desktop/bootstrap.py::maybe_prompt_first_run_password`):
    the single interactive question used to land 15+ minutes in, mid-install,
    after users had walked away. The prompt helper is shared with
    `desktop_bootstrap` (which keeps it as a fallback and now also enforces
    the `LOGIN_MIN_LENGTH` floor on the `OC_DESKTOP_PASSWORD` env var —
    previously the env path bypassed the only validation this superuser
    account gets). The launcher drops the env var before spawning the
    long-lived children.
  - **Failed SPA refresh can no longer destroy a working cached copy**
    (`opencontractserver/desktop/spa_dist.py::download_spa`): downloads now
    extract into a staging sibling and swap in only after checksum,
    extraction, and index.html checks all pass. `safe_extract_zip` also
    rejects symlink zip members (defense-in-depth).
  - **App-data directories are actually user-private now**: the launcher's
    `_ensure_dirs` and the pgdata `mkdir` bypassed `paths.subdir`'s `0o700`,
    leaving the full local database and uploaded documents umask-readable on
    shared machines.
  - **`corpuses/0028` no longer prints a scary fake `ERROR` on every fresh
    install**: `permission_corpus` is created by `post_migrate`, i.e. always
    after this data migration on a first `migrate`, and a fresh DB has no
    corpuses to backfill — it now warns only when real data was skipped.
  - Friendlier messaging: nltk corpora download progress line, plain-language
    keyring-fallback warning, shutdown farewell (where data lives, how to
    restart), pre-release-vs-offline distinction in the no-UI warning, and a
    force-stop escape hatch (third Ctrl+C) plus a KeyboardInterrupt-tolerant
    teardown drain. README states the app URL (http://127.0.0.1:8406/) and
    honest first-run timing.
