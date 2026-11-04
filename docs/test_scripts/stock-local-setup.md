# Test: Stock local setup (embedder auth, worker reloads, Windows checkouts)

## Purpose
Verifies the issue #2514 fixes that the automated suite can't reach: a stock
`local.yml` resolves matching embedder keys, the Celery worker survives its own
parse output, the frontend image builds within its heap limit, and a
`core.autocrlf=true` clone keeps container scripts on LF.

`opencontractserver/tests/test_local_compose_wiring.py` pins the first two.

## Prerequisites
- Docker with Compose v2
- `pip install watchfiles==1.3.0` in a virtualenv on your `PATH`
- Run from the repository root, with these set:
  ```bash
  REPO=$(git rev-parse --show-toplevel)
  TMP=$(mktemp -d)
  ```

## Steps
1. Resolve the stock compose environment from the sample env files. This uses a
   scratch copy because `.envs/.local` is gitignored and may hold your real
   credentials:
   ```bash
   mkdir "$TMP/stock"
   git -C "$REPO" archive HEAD | tar -x -C "$TMP/stock"
   mkdir -p "$TMP/stock/.envs/.local"
   cp "$REPO"/docs/sample_env_files/backend/local/.django \
      "$REPO"/docs/sample_env_files/backend/local/.postgres "$TMP/stock/.envs/.local/"
   touch "$TMP/stock/.envs/.local/.frontend"
   (cd "$TMP/stock" && env -u VECTOR_EMBEDDER_API_KEY -u MULTIMODAL_EMBEDDER_API_KEY \
     docker compose -f local.yml config --format json) | python3 -c "
   import json, sys
   services = json.load(sys.stdin)['services']
   for name in ('django', 'celeryworker', 'vector-embedder', 'multimodal-embedder'):
       env = services[name]['environment']
       print(name, {k: v for k, v in env.items() if k.endswith('EMBEDDER_API_KEY')})
   "
   ```
2. Run the real worker start script against a fake tree, with a `celery` shim on
   `PATH` that logs one line on start and ignores SIGINT (a task that won't finish):
   ```bash
   mkdir -p "$TMP/app/opencontractserver/media/pawls" "$TMP/app/config"
   echo 'x = 1' > "$TMP/app/opencontractserver/models.py"
   (cd "$TMP/app" && bash "$REPO/compose/local/django/celery/worker/start") &
   echo '{}' > "$TMP/app/opencontractserver/media/pawls/doc.json"   # expect no restart
   echo 'x = 2' >> "$TMP/app/opencontractserver/models.py"          # expect a restart
   ```
   Stop `watchfiles` and the shim afterwards; killing the `bash` job alone leaves
   them running.
3. Build the frontend stage at both heap limits:
   ```bash
   docker build --target builder --build-arg NODE_MAX_OLD_SPACE_SIZE=2048 "$REPO/frontend"
   docker build --target builder "$REPO/frontend"
   ```
4. Clone with Windows line-ending defaults and inspect the checkout:
   ```bash
   git -c core.autocrlf=true clone --branch <branch> "file://$REPO/.git" "$TMP/crlf"
   git -C "$TMP/crlf" ls-files --eol compose | awk '{print $1, $2}' | sort | uniq -c
   git -C "$TMP/crlf" -c core.autocrlf=true add --renormalize .
   git -C "$TMP/crlf" status --short -- compose '*.sh'
   ```

## Expected Results
1. All four services resolve `abc123`; `django` and `celeryworker` list both keys.
2. The media write leaves the worker alone. The `.py` edit restarts it: one SIGINT,
   then a second start line about 5 seconds later.
3. The 2048 build fails with `JavaScript heap out of memory`; the default passes.
4. Every `compose/` file reports `i/lf w/lf`, and the status output is empty.

## Cleanup
```bash
rm -rf "$TMP"
```
