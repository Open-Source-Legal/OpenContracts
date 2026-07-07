# Test: One-step desktop setup (`python3 oc-desktop.py`)

## Purpose
Verify the single-user desktop packaging end-to-end from the perspective of a
minimally technical user: one command + one password choice must yield a
working, login-able app in a browser, with a clean Ctrl+C shutdown and a fast
second launch. This is the manual procedure behind the clean-room usability
tests referenced on PR #2137; rerun it after any change to
`opencontractserver/desktop/` or the desktop settings profile.

## Prerequisites
- A source checkout (or release ZIP) of the repository.
- Python 3.10–3.12 on PATH (`python3 --version`).
- Internet access for the first run (PyPI + GitHub releases).
- No leftover state: delete the per-user app-data dir if present
  (Linux `~/.local/share/OpenContracts`, macOS
  `~/Library/Application Support/OpenContracts`, Windows
  `%LOCALAPPDATA%\OpenContracts`) — or export `OC_DESKTOP_DATA_DIR` to a
  scratch path to isolate the test.

## Steps
1. First launch, from the checkout root:
   ```bash
   python3 oc-desktop.py        # Windows: py oc-desktop.py
   ```
2. Within seconds, the password prompt must appear (min 8 chars, asked twice)
   **before** any long install starts; after answering, setup runs unattended
   (private venv + deps, embedded Postgres, full migrate — watch for
   `annotations.0074` printing its pg_trgm skip note on the embedded server —
   first-run bootstrap, SPA acquisition, Daphne).
3. Wait for the banner (`OpenContracts is running: http://127.0.0.1:8406/`),
   then verify:
   ```bash
   curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8406/          # 200
   curl -s http://127.0.0.1:8406/api/health/                                # {"status": "ok"}
   ```
4. Verify login with the prompted password:
   ```bash
   curl -s -X POST http://127.0.0.1:8406/graphql/ -H "Content-Type: application/json" \
     -d '{"query":"mutation { tokenAuth(username: \"desktop\", password: \"<your password>\") { token } }"}'
   ```
   Then an authenticated `me { username }` query with
   `Authorization: Bearer <token>` must return `"desktop"`.
5. Press Ctrl+C in the launch terminal. Teardown must complete within ~10 s,
   print the farewell (data location + how to restart), and leave no
   daphne/celery/postgres processes and no listener on 8406.
6. Second launch: rerun the same command. It must NOT re-prompt for a
   password or reinstall anything, and must reach a healthy app in well under
   a minute. Ctrl+C again and confirm the same clean teardown.

## Expected Results
- Exactly one command and one password decision across the whole flow.
- Migration `0074` skips its trigram index gracefully on the embedded
  Postgres (no `pg_trgm` crash); no `ERROR`-level noise from `corpuses/0028`
  on a fresh database.
- Banner states the URL, the `desktop` username, and the Ctrl+C stop
  instruction; shutdown farewell states where data lives.
- Warm relaunch ≈ tens of seconds; venv/dist/password all reused.

## Cleanup
Delete the app-data directory (or the `OC_DESKTOP_DATA_DIR` scratch path) to
reset completely; build artifacts under `frontend/dist` / `frontend/node_modules`
(only present if the yarn fallback ran) can be removed with `git clean -fdx frontend`.
