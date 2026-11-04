# Test: Stock local setup (embedder auth, worker reloads, Windows checkouts)

## Purpose
Verifies the issue #2514 fixes that the automated suite can't reach: a stock
`local.yml` resolves matching embedder keys, the Celery worker survives its own
parse output, the frontend image builds within its heap limit, and a
`core.autocrlf=true` clone keeps container scripts on LF.

`opencontractserver/tests/test_local_compose_wiring.py` pins the first two.

## Prerequisites
- Docker with Compose v2
- A throwaway directory, referred to as `$TMP`
- `pip install watchfiles==1.3.0` in a virtualenv on your `PATH`

## Steps
1. Resolve the stock compose environment from the sample env files:
   ```bash
   mkdir -p .envs/.local
   cp docs/sample_env_files/backend/local/.django docs/sample_env_files/backend/local/.postgres .envs/.local/
   touch .envs/.local/.frontend
   env -u VECTOR_EMBEDDER_API_KEY -u MULTIMODAL_EMBEDDER_API_KEY \
     docker compose -f local.yml config --format json | python3 -c "
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
   mkdir -p $TMP/app/opencontractserver/media/pawls $TMP/app/config
   echo 'x = 1' > $TMP/app/opencontractserver/models.py
   (cd $TMP/app && bash /path/to/repo/compose/local/django/celery/worker/start) &
   echo '{}' > $TMP/app/opencontractserver/media/pawls/doc.json   # expect no restart
   echo 'x = 2' >> $TMP/app/opencontractserver/models.py          # expect a restart
   ```
3. Build the frontend stage at both heap limits:
   ```bash
   cd frontend
   docker build --target builder --build-arg NODE_MAX_OLD_SPACE_SIZE=2048 .
   docker build --target builder .
   ```
4. Clone with Windows line-ending defaults and inspect the checkout:
   ```bash
   git -c core.autocrlf=true clone --branch <branch> file://$PWD/.git $TMP/crlf
   git -C $TMP/crlf ls-files --eol compose | awk '{print $1, $2}' | sort | uniq -c
   git add --renormalize . && git status --short
   ```

## Expected Results
1. All four services resolve `abc123`; `django` and `celeryworker` list both keys.
2. The media write leaves the worker alone. The `.py` edit restarts it: one SIGINT,
   then a second start line about 5 seconds later.
3. The 2048 build fails with `JavaScript heap out of memory`; the default passes.
4. Every `compose/` file reports `i/lf w/lf`, and renormalizing changes nothing.

## Cleanup
```bash
rm -rf $TMP .envs/.local
```
Keep `.envs/.local` if it held your own configuration before step 1.
