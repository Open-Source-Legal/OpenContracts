# Type Checking (mypy)

This directory documents how OpenContracts' Python type-checking pipeline is
wired up and how to graduate modules out of the initial baseline.

## How it is wired

- **Configuration**: `mypy.ini` at the repo root. (Pulled out of `setup.cfg`
  because the per-module baseline list below is large.)
  - `python_version = 3.11` (matches `requirements/base.txt` runtime).
  - `plugins = mypy_django_plugin.main, mypy_drf_plugin.main` — Django- and
    DRF-aware type inference (models, querysets, serializers, etc.).
  - `django_settings_module = config.settings.mypy` — a thin wrapper around
    `config.settings.test` that supplies a dummy `DATABASE_URL` so mypy runs
    without needing an env var. The plugin introspects `INSTALLED_APPS`,
    model fields, reverse relations, etc. but never actually connects.
  - `check_untyped_defs`, `warn_unused_ignores`, `warn_redundant_casts`, and
    `warn_unused_configs` are on so the bar rises as modules graduate.
  - `ignore_missing_imports = True` — most ML/pipeline deps
    (`pdfplumber`, `docling`, `sentence-transformers`, …) ship no stubs.
- **Pre-commit hook**: `.pre-commit-config.yaml` runs
  `pre-commit/mirrors-mypy` with stubs + the minimum Django runtime pinned in
  `additional_dependencies` so contributors don't need the full dev env
  installed locally. All deps are version-pinned — pre-commit autoupdate
  only bumps `rev`, so leaving stubs unpinned would let them drift
  independently on every weekly refresh.
- **CI**: `.github/workflows/backend.yml` runs
  `python -m mypy --config-file mypy.ini opencontractserver config` as part
  of the `linter` job. The preceding `Install dependencies` step pip-installs
  `requirements/local.txt`, which pins `mypy`, `django-stubs`, and
  `djangorestframework-stubs` alongside the Django runtime — so the plugin
  has everything it needs in the runner env.

## How to run mypy locally

### Inside the Django Docker container (recommended)

The test container already has every runtime dep installed, which keeps the
Django plugin happy.

```bash
docker compose -f test.yml run --rm django \
  python -m mypy --config-file mypy.ini opencontractserver config
```

### Via pre-commit (isolated env)

```bash
pre-commit run mypy --all-files
```

Pre-commit builds its own virtualenv from the hook's `additional_dependencies`
on first run (a few minutes) and caches it afterwards.

### Via your own dev virtualenv

```bash
pip install -r requirements/local.txt
python -m mypy --config-file mypy.ini opencontractserver config
```

No `DATABASE_URL` env var is required — `config.settings.mypy` bakes in a
dummy one for type-checking only.

## Why there is a baseline

As of issue #1331 the codebase has ~7.2k pre-existing mypy errors across 357
files (see `mypy_baseline.txt`). Forcing all of those to be fixed in one go
would block the rest of the remediation work.

### What the baseline does (and does not) gate

`mypy.ini` lists **every file** that had an error at the time of the initial
wire-up under its own `[mypy-<module.path>]` section with
`ignore_errors = True`. There is **no wildcard pattern** covering
`opencontractserver.*` or `config.*`.

That matters because:

- **New files ARE type-checked.** A brand-new module at
  `opencontractserver/new_feature/views.py` is not in the baseline, so mypy
  will check it and the hook / CI will fail on any errors.
- **Refactoring an existing baselined file does not silently re-silence
  it.** If a module is renamed or moved, its old `[mypy-…]` section
  becomes dead (`warn_unused_configs` flags this) and the new path is
  checked from scratch.
- **Existing baselined files are silenced.** Any error inside
  `opencontractserver/utils/storages.py` (for example) is suppressed until
  that module is graduated.

### Baseline shape (issue #1331)

| Metric                | Value |
|-----------------------|-------|
| Files with errors     | 357   |
| Total error messages  | 7208  |
| Top error code        | `attr-defined` (2403) |
| Next most common      | `union-attr` (355), `arg-type` (159), `assignment` (83), `valid-type` (82), `misc` (81) |
| Worst offender (file) | `opencontractserver/mcp/tests/test_mcp.py` (319 errors) |

The full breakdown lives in `mypy_baseline.txt` (sorted by file + line for
stable diffs).

## How to graduate a module out of the baseline

1. **Delete the module's section** in `mypy.ini`. Example — to graduate
   `opencontractserver/constants/annotations.py`:

    ```ini
    # Before
    [mypy-opencontractserver.constants.annotations]
    ignore_errors = True

    # After
    (section removed)
    ```

2. Run mypy and fix what surfaces:

    ```bash
    python -m mypy --config-file mypy.ini opencontractserver config
    ```

3. **Prune the corresponding lines** from `docs/typing/mypy_baseline.txt`.
   This file is an advisory reference — it is not consumed by mypy itself,
   so it must be pruned manually. **Reviewers**: before approving a
   graduation PR, verify that:
   - Every pruned entry references the module being graduated (no
     unrelated drive-by deletions).
   - Every entry for the graduated module has been pruned (no leftover
     lines that would silently rot in the reference file).

4. Commit with a message referencing the tracker issue, e.g.
   `typing: graduate opencontractserver.constants.annotations (refs #1331)`.

### Order we'd suggest graduating in

Pick small, leaf-ish modules first so the Django plugin has less surface to
cover:

1. `opencontractserver/constants/*` — pure Python constants, no imports.
2. `opencontractserver/utils/*` helpers that don't touch models.
3. `config/settings/*` — narrow and rarely changed.
4. Apps with small `models.py` footprints (e.g. `feedback`, `discovery`).
5. Work outwards into GraphQL types and views.

## How to suppress a single error

Prefer fixing the error. When that isn't realistic in the current PR:

```python
foo = something_mypy_doesnt_like()  # type: ignore[assignment]
```

Always pass the error code in brackets — `warn_unused_ignores` is on, so
bare `# type: ignore` comments will themselves produce errors once the
surrounding module graduates.

If a *whole* module can't be fixed yet but you want to leave a trail:

```ini
[mypy-opencontractserver.legacy_thing]
ignore_errors = True
```

…with a comment pointing at the tracker issue that will remove it.

## Troubleshooting

- **`Error constructing plugin instance of NewSemanalDjangoPlugin`** — the
  Django plugin imports `config.settings.mypy`, which transitively imports
  most of `INSTALLED_APPS`. Missing one of those apps (e.g. `celery`,
  `channels`, `django-storages`) is almost always the cause. Install the
  missing dep or run mypy from inside the test container.
- **`Set the DATABASE_URL environment variable`** — you're pointing mypy at
  `config.settings.test` or `.base` instead of `config.settings.mypy`.
  Double-check `django_settings_module` in `mypy.ini`.
- **`Library stubs not installed for "requests"`** — add `types-requests`
  to the hook's `additional_dependencies` (and to the dev env if you want
  the error to go away locally outside pre-commit).
