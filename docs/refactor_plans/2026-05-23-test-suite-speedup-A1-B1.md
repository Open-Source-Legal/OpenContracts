# Backend Test Suite Speedup — Phase A + B Design

**Date:** 2026-05-23
**Author:** scrudato@umich.edu (drafted with Claude Code)
**Status:** Phase A1 landed (PR #1767, CI 41 min → ~32 min, ~22% reduction). Phase B1 trialled and reverted — see §6 post-mortem and §10. Phase B2/B3 (fixture-load redesign) is the next lever.
**Target:** Pull backend CI from ~47 min → **under 15 min** while preserving full Codecov reporting on both PR and `main` events. After A1, the binding constraint is per-test 17 MB fixture reload in `TransactionTestCase` subclasses — see §10.
**Scope:** `.github/workflows/backend.yml`, `compose/local/django/Dockerfile`, `opencontractserver/tests/base.py`, `opencontractserver/conftest.py`, `pytest.ini`, `opencontractserver/tests/fixtures/test_data.json`. No changes to product code.

---

## 1. Problem statement

Backend CI on the `main` branch is consistently **47–52 min** wall-clock, dominated by the `pytest` step at **~41 min** (per `gh run view 26334920376`). Phase 1 (`#1713`, skip coverage on PRs), Phase 2 (`#1710`, `TransactionTestCase` → `TestCase` audit), and Phase 3 (`#1711`, slim `BaseFixtureTestCase`) shaved roughly **20 minutes** off the prior 72-min wall time but progress has plateaued. Iteration speed is now the bottleneck.

Phase 1 was effectively **reverted** by commit `328a9a290` (`enable PR coverage`). Phase 2 left ~177 tests still on `TransactionTestCase` semantics in the `WebsocketFixtureBaseTestCase` and `TransactionFixtureTestCase` subclasses. Phase 3 only helped the `TestCase` variant of `BaseFixtureTestCase`; the transaction-based variants still reload the 17 MB `test_data.json` once per test.

**Hard constraint:** Codecov reporting must remain intact. We can change *how* coverage is collected and *how fast*, but Codecov on every `main` push and every PR must keep working.

## 2. Evidence

From the most recent successful `main` run (`#26334920376`, full `--durations=0`):

**Job-level (47 min total):**

| Step | Wall |
|---|---:|
| Build the Stack | 2:18 |
| Run DB Migrations (separate step) | 3:03 |
| Run Backend Test Suite | **41:00** (7,400 tests, 16 workers `-n auto`) |
| Everything else | ~0:33 |

**Test phase histogram (9,773 phase entries, sum 9,495 s):**

| Bucket | n | Σ | % |
|---|---:|---:|---:|
| < 0.1 s | 6,233 | 139 s | 1.5% |
| 0.1 – 1 s | 2,725 | 650 s | 6.8% |
| 1 – 5 s | 509 | 719 s | 7.6% |
| 5 – 15 s | 63 | 653 s | 6.9% |
| 15 – 30 s | 61 | 1,308 s | 13.8% |
| **30 – 60 s** | **177** | **5,523 s** | **58.2%** |
| > 60 s | 5 | 503 s | 5.3% |

**58% of test wall time is concentrated in 177 tests at 30–60 s each, all in the same handful of files.**

**Top files by Σ time (call + setup + teardown):**

| File | Σ | n | Base class |
|---|---:|---:|---|
| `websocket/test_agent_permission_escalation.py` | 1520 s | 98 | `WebsocketFixtureBaseTestCase` |
| `test_extract_analyzer_tools.py` | 1375 s | 93 | `TransactionFixtureTestCase` |
| `test_structured_response_api.py` | 937 s | 35 | `TransactionFixtureTestCase` |
| `websocket/test_unified_agent_consumer.py` | 872 s | 56 | `WebsocketFixtureBaseTestCase` |
| `test_websocket_auth.py` | 838 s | 54 | `WebsocketFixtureBaseTestCase` |
| `test_notification_websocket.py` | 560 s | 22 | `WebsocketFixtureBaseTestCase` |
| `test_unified_agent_consumer_delegation.py` | 400 s | 25 | `WebsocketFixtureBaseTestCase` |

**Top serial-floor classes** (single-class total times — these set the wall-time floor because `--dist loadscope` pins a whole class to one worker):

| Class | Σ | n |
|---|---:|---:|
| `TestStructuredResponseAPI` | **843 s (14.1 min)** | 27 |
| `NotificationWebSocketTestCase` | 560 s | 18 |
| `TestStartExtract` | 468 s | 15 |
| `UnifiedAgentConsumerDelegationTestCase` | 400 s | 13 |
| `AuthHandshakeMixinTests` | 311 s | 10 |

The 14-min serial floor of `TestStructuredResponseAPI` alone makes anything below ~17 min impossible without breaking class-scope binding.

**Setup-phase concentration:** 1,502 s total setup across 4,689 setups. The top 53 setups (all ≥5 s) sum to **1,425 s** (95% of all setup time). The four 100+ s outliers (108.8, 107.4, 105.8, 105.7) are per-worker initial DB creation from migrations (unavoidable). The remaining ~49 ≥5 s setups average ~26 s each — these are 17 MB `test_data.json` reloads inside `TransactionTestCase._fixture_setup` for the websocket / extract / structured-response classes.

**Other facts:**

- **Python 3.11.15** in the test container. Coverage.py on 3.11 uses the C trace function; `sys.monitoring` (`COVERAGE_CORE=sysmon`) needs 3.12+ and is **5-10× cheaper**.
- **`test_data.json`** is 17 MB, 255 K JSON lines, 7,584 objects (3,584 `guardian.userobjectpermission`, 1,344 `annotations.annotation`, 1,344 `annotations.embedding`, 472 relationships). Loaded per-test under `TransactionTestCase` semantics.
- **`Run DB Migrations`** step (3 min) precedes pytest but `pytest.ini` already specifies `--reuse-db`, and the test DB volume (`test_postgres_data`) persists across CI runs on `yuge`. The step is redundant whenever the DB is warm; `pytest --create-db` would handle cold starts.
- **`Build the Stack`** (2:18) rebuilds the Django image from scratch. No registry pull-through cache.
- **`--cov`** runs unconditionally (`#1713` was reverted). **Measured overhead on Python 3.11 (see §6): +156% over no-cov baseline** — coverage instrumentation more than doubles wall time on the hot files. Extrapolating to the full suite, removing coverage would cut the test step from ~41 min to ~16 min on the same Python version.

## 3. Goals & non-goals

**Goals:**

- Phase A: ship CI/config-only changes, **target ≤25 min** wall-clock for the backend job.
- Phase B: ship the structural changes for fixture/dist that drop the serial floor, **target ≤15 min** wall-clock.
- Preserve full Codecov reporting on PR *and* push events — no change to what data Codecov receives.
- No flakiness regressions; no skipped tests.
- Each phase is independently mergeable and independently rollbackable.

**Non-goals:**

- Sharding the backend job across multiple CI runners (Phase C; tracked separately).
- Test-code rewrites beyond the base-class layer and fixture content.
- Frontend CI optimization (separate concern).
- Replacing pytest-xdist with a different parallel runner.

## 4. Phase A — CI / config changes (no test-code touched)

**A1. Upgrade Python to 3.12 + enable `sys.monitoring`-backed coverage.**
- Bump `ARG PYTHON_VERSION=3.11.15-slim-bookworm` → `3.12-slim-bookworm` in `compose/local/django/Dockerfile` and `compose/production/django/Dockerfile`.
- Set `COVERAGE_CORE=sysmon` in `.envs/.test/.django`.
- Validate all pinned wheels in `requirements/base.txt`, `local.txt`, `production.txt` have 3.12 wheels. Notable risk: `psycopg2-binary`, `numpy`, `pandas`, `lxml` — all have 3.12 wheels in current versions, but a real-image rebuild needs to confirm.
- Codecov impact: **none.** Same `coverage.xml` content, just collected faster.
- Estimated wall-time saving: **~10-12 min.** Local A/B (§6) shows coverage on Py 3.11 costs 156% over no-cov baseline. `sys.monitoring` typically reduces that overhead to 5-15%, so we recover roughly 9-11 min of the current ~12 min coverage tax while preserving Codecov reporting in full.

**A2. Delete the redundant `Run DB Migrations` CI step.**
- `pytest.ini` already sets `--reuse-db`. `pytest-django` runs `migrate` automatically when the DB schema is stale or absent. The explicit `manage.py migrate` step is redundant on warm volumes and duplicated work on cold ones.
- Replace with a one-line `pytest --create-db --collect-only` warm-up that triggers DB creation without running tests — only on the first run after a schema change. Or, simpler: remove the step entirely and let pytest's first call do it.
- Estimated wall-time saving: **~3 min** on warm runs, neutral on cold.

**A3. Push the built Django image to `ghcr.io` and pull instead of build.**
- Add a `docker buildx bake --push` step keyed on the SHA of `requirements/*.txt` + `Dockerfile`. CI pulls if the tag exists; builds + pushes if not.
- Estimated wall-time saving: **~1.5–2 min** on cache hits (nearly every run).

**A4. Make `-n auto` explicit.**
- `-n auto` resolves to `os.cpu_count()` inside the container. On Linux this respects cgroup CPU limits, but if `yuge`'s cgroup misreports cores, pytest may over- or under-subscribe.
- Replace with `-n ${PYTEST_WORKERS:-16}` (or whatever `yuge`'s actual core count is) and document the choice. Backstop with `--maxfail=10` so a CI break doesn't tie up all workers.
- Estimated wall-time saving: **0–1 min**, primarily insurance.

**A5. Drop the redundant `disable_document_processing_signals` autouse waste** *(only if safe)*.
- The session-scoped `disable_document_processing_signals` fixture in `opencontractserver/conftest.py` connects/disconnects post_save signals at session boundaries. It's autouse, runs once per worker — already fine. **No change.** Listed here only because a prior audit flagged it; leave alone.

**Phase A acceptance:** Same coverage in Codecov for both PR and `main`, backend job wall-clock ≤ 25 min on the typical PR. No new test failures or flakes across 3 consecutive PR runs.

## 5. Phase B — structural changes (fixture + dist + base classes)

**B1. Replace `--dist loadscope` with `--dist worksteal`; mark class-scope-required tests explicitly.**

- `loadscope` pins every test in a class to a single worker. This *only* matters for tests that share class-scoped state (`setUpClass`, `setUpTestData`, class-level fixtures). The current default of `loadscope` for the entire suite over-constrains parallelism for every class that doesn't share state.
- New default: `--dist worksteal`. This dynamically rebalances work across idle workers, giving better fan-out for the big classes (`TestStructuredResponseAPI`'s 27 tests can run on 27 workers instead of 1).
- Mark only the classes that genuinely require class binding with `@pytest.mark.xdist_group(name="<class>")` — this is a small, well-defined set: `BaseFixtureTestCase` subclasses (because `setUpTestData` builds shared state) and any class explicitly relying on `setUpClass` side effects. The `_FixtureSetupMixin` design in `base.py` already makes the distinction clean — `BaseFixtureTestCase` (TestCase, class-scope state) gets a default `xdist_group` matching the class; `TransactionFixtureTestCase` (per-test fixture rebuild) does not.
- Implement via `pytest_collection_modifyitems` in `opencontractserver/conftest.py` — auto-tag any `unittest.TestCase` subclass that defines `setUpTestData` (or that subclasses `BaseFixtureTestCase`) with `xdist_group=cls.__qualname__`. No per-class manual annotation needed.
- Estimated wall-time saving: **~6-10 min**. Local A/B (§6) shows a **37% reduction** swapping loadscope → worksteal on the no-cov runs (B 7:38 → C 4:50) for the hot files; extrapolating to the full suite (where many non-hot classes don't benefit) gives the lower bound.

**B2. Slim `test_data.json` from 17 MB → < 1 MB; recreate sparse rows in `setUp` of tests that need them.**

- Current fixture: 7,584 objects. Audit usage:
  - 3,584 `guardian.userobjectpermission` rows — most tests grant their own perms in `_build_corpus_fixture_state`; the fixture rows are duplicative for `WebsocketFixtureBaseTestCase` and friends.
  - 1,344 `annotations.embedding` rows — needed only by similarity/vector-store tests. Most tests don't touch them.
  - 472 relationship rows — same story.
- Strategy: keep only the canonical 4 documents + 1 corpus + 1 user + ~20 representative annotations in the JSON. Move the bulk rows to **factory-built per-test or per-class data** under `opencontractserver/tests/factories.py` using `factory_boy` (already a dependency).
- `_build_corpus_fixture_state` would still grant the explicit per-test permissions it needs; tests that depend on the bulk embeddings call a new `cls.materialize_embedding_fixtures()` helper in their `setUpTestData` / `setUp`.
- Risk: a small number of tests may implicitly depend on fixture rows we cut. Mitigation: run the full suite locally before/after the slim, diff failures, fix usages.
- Estimated wall-time saving: **~3-5 min** (cuts per-`loaddata` cost from ~1-2 s to ~50 ms; per-test x 177 tests = a lot of cumulative IO).

**B3. Redesign `WebsocketFixtureBaseTestCase` to load the fixture once per class.** *(Possibly optional — defer until after A1+B1 land and we re-measure.)*

- `TransactionTestCase` re-runs `_fixture_setup` (which calls `loaddata`) **per test** because each test runs in a flushed-and-reseeded DB. We cannot get true `TestCase` semantics for channels consumers (they open separate DB connections that need to see committed data).
- However, we *can* manually load the fixture once in `setUpClass`, commit it, and use a **manual TRUNCATE-and-restore of only the mutated tables** in `_post_teardown` to give per-test isolation without paying for full `flush()` + `loaddata()`.
- Implementation sketch in `opencontractserver/tests/base.py`:
  - In `WebsocketFixtureBaseTestCase.setUpClass`: load fixture, build corpus/document state, **snapshot the affected table contents** via `pg_dump --data-only --table=...` into in-memory SQL.
  - Override `_fixture_setup` / `_fixture_teardown` to no-op (fixture is class-scoped now).
  - In `_post_teardown`: for each table the test class is expected to mutate (annotation, relationship, conversation, message, etc.), `TRUNCATE` + restore from the snapshot. Tables the class never mutates (documents, corpus, users) stay untouched.
  - List of mutable tables maintained per subclass via a `_mutable_tables = (...)` class attr, defaulting to a sensible superset for the websocket/extract/structured cluster.
- Estimated wall-time saving: **~6-10 min** (cuts the per-test setup from ~25 s → ~1-2 s for the 177 heavy tests).

**B4. Re-audit residual `TransactionTestCase` users per Phase 2 criteria.**

- Reapply the Phase 2 (#1710) audit grep — `async def`, `await `, `communicator`, `database_sync_to_async`, `threading`, `on_commit`, `select_for_update` — against the *current* tree. Classes with none of these convert to `TestCase`. Phase 2 caught the bulk; this is mop-up.
- Estimated saving: **~1-2 min**, plus less per-test variance.

**Phase B acceptance:** Backend job wall-clock ≤ 15 min. No new flakiness over 5 consecutive PR + 2 main runs. Coverage delta to current run ≤ 0.5% absolute (same code paths execute, only DB-isolation strategy changed).

## 6. Local A/B verification

Three pytest invocations against the same warmed test DB, restricted to the 3 representative hot files (`test_extract_analyzer_tools.py`, `test_structured_response_api.py`, `test_notification_websocket.py` — together ~2,872 s in CI, the dominant hot-path):

| Run | Flags | Measures |
|---|---|---|
| A | `--cov --cov-report= -n auto --dist loadscope` | Baseline (CI-like) |
| B | `-n auto --dist loadscope` | A − cov = **coverage overhead** |
| C | `-n auto --dist worksteal` | B with dist swap = **worksteal lift** |

This gives us:

- **Coverage overhead (A − B)** → upper bound on what A1 (Python 3.12 + sysmon) can save. If A − B is huge, A1 is high-ROI; if small, A1 is mostly insurance.
- **Worksteal lift (B − C)** → measures B1's ceiling on a representative subset.

**Local results (measured 2026-05-23, 8-core local box, warm DB):**

| Run | Wall | Δ vs A | Notes |
|---|---:|---:|---|
| A | **19:34** (1173.79 s) | — | CI-like: `--cov --dist loadscope` |
| B | **7:38** (458.41 s) | **−61%** | A minus cov |
| C | **4:50** (290.32 s) | **−75%** | B with `--dist worksteal` |

**Coverage overhead (A − B): 11:55 (+156% over no-cov baseline).** Much larger than my initial 25-35% estimate. Python 3.11's C-trace instrumentation more than doubles wall time on hot files; this validates A1 as the single highest-ROI Phase A change.

**Worksteal lift (B − C): 2:48 (−37%).** Validates B1 — loadscope's class-pinning is the binding constraint on the heavy classes once coverage is out of the way. Worksteal alone, with no code change, gives a 1.58× speedup on the hot subset.

**Combined (A − C): 14:44 (−75%, 4.0× speedup).** A1 + B1 together — both are pure flag/config changes — could plausibly bring the full CI step from ~41 min to ~10-13 min. Phases B2 (slim fixture) and B3 (class-once fixture) become refinements rather than load-bearing changes.

*Caveats:* Local is 8 cores vs `yuge` ~16; this is 3 of 340 test files (~30% of CI test time); pytest-xdist startup/coverage-combine overhead amortizes differently at full-suite scale. Treat ratios, not absolute extrapolations, as the binding signal.

## 7. Risk register

| Risk | Phase | Mitigation |
|---|---|---|
| Python 3.12 wheel missing for a pinned dep | A1 | Build image locally first; fall back to 3.11 if any dep is stuck. |
| `worksteal` reorders tests, exposes order-dependency bugs | B1 | Run the full suite 3× post-change on `main`-merged commits; flake-quarantine + fix any that surface. |
| Slimming `test_data.json` breaks tests that implicitly use cut rows | B2 | Diff suite pass/fail before vs after; fix usages by adding explicit `setUp` data construction. |
| Manual snapshot/restore in B3 misses a mutated table → test pollution | B3 | Build snapshot/restore on a per-class `_mutable_tables` allow-list; add an assertion that compares the table count before/after, fails loudly if drift. |
| Removing migrate step + cold DB on fresh `yuge` runner | A2 | `pytest --create-db` covers cold start; document the fallback in the workflow comment. |
| Docker image push to ghcr requires extra secret | A3 | Existing `GITHUB_TOKEN` has packages: write — verify, add scope if missing. |
| Codecov patch coverage degrades visibility on PRs | A1 | A1 *preserves* full coverage; this risk is zero unless we revert to skip-on-PR. |

## 8. Rollout

Land in this order, each as its own PR with its own measured CI delta in the PR body:

1. **PR-A1** Python 3.12 + sysmon. Smoke-test on a draft PR; confirm Codecov receives identical xml.
2. **PR-A2** Drop redundant migrate step. Verify cold-start path with a forced `pytest --create-db`.
3. **PR-A3** GHCR image cache.
4. **PR-A4** Explicit worker count.
5. **PR-B1** worksteal + `xdist_group` auto-tagging. Run 3 consecutive PR runs to flush out order-dependencies.
6. **Re-measure after PR-B1 lands.** If the suite is already ≤ 15 min, treat B2/B3 as optional refinements and only do B4. If we're still > 15 min, proceed.
7. **PR-B2** Slim `test_data.json`.
8. **PR-B3** Class-once fixture load for `WebsocketFixtureBaseTestCase`.
9. **PR-B4** Residual `TransactionTestCase` audit.

Each PR records the actual CI wall-time delta in the description, so we can revisit the projections honestly. Estimated cumulative landing time: 1-1.5 weeks at 1-2 PRs per day. Steps 1, 5, and 6 are the load-bearing ones; the rest are increments.

## 9. Open questions

1. **Worksteal + ordering pollution** — RESOLVED. The first PR #1767 run answered this with a hard yes: ~39 tests have latent ordering dependencies. See §10 for details.
2. **Phase C readiness** — sub-15 min is the stated target. If after B2/B3 we are at ~13 min and the user wants ≤ 10 min, sharding via job matrix is the next lever (Phase C). Open question: budget appetite for the added matrix-job complexity.

## 10. Post-mortem: Phase B1 trial in PR #1767

**What we shipped:** Phase A1 (Python 3.12.7 + `COVERAGE_CORE=sysmon` + dropped `django_coverage_plugin`) and Phase B1 (`--dist worksteal` + conftest auto-tag for class-bound `TestCase` subclasses) together.

**What CI did:** Backend pytest step 41 min → **31:53** wall (−22%). **39 tests failed**, mostly with `psycopg2.errors.UniqueViolation: duplicate key value violates unique constraint "users_user_username_key"  DETAIL: Key (username)=(admin) already exists.` Coverage uploaded successfully — Codecov was unaffected.

**Failure mode:** The failures concentrated in **plain `django.test.TestCase` subclasses** (no `setUpTestData`, no `fixtures`) that my auto-tag deliberately skipped: `UserTypePrivacyTestCase`, `TestSearchAgentsForMention`, `TestOpenContractsAnalyzers`, `CreateDefaultLabelsetTestCase`, `TestHybridSearch`, `PermissionFilteringTestCase`, plus `TestNestedApprovalGates` (a `TransactionTestCase`). Worksteal interleaved tests from these classes with tests from other classes on the same worker, exposing state leaks that loadscope's class-pinning was hiding — likely a mix of migration-seeded `admin`/`system`/`Anonymous` users colliding with `UserFactory()` calls, `Celery eager` tasks committing data via `on_commit`, and `User.save()`'s handle/slug auto-generation logic that queries the global user set.

**Where my projection went wrong:**

1. **Over-extrapolated the local A/B.** The 4× speedup (19:34 → 4:50) was measured on the 3 hottest files — together ~30% of CI test time. Those files were uniquely amplified by both factors I optimized (heavy `--cov` instrumentation + class-pinned to one worker). For the other 70% of the suite, individual test phases are too short for either factor to dominate, so the savings don't scale linearly. The honest projection for A1 + B1 was always closer to 25-30%, not 75%.

2. **Conflated coverage cost with fixture-load cost.** The local A/B's coverage tax (+156%) was specific to the 18 MB fixture-reloading test classes — coverage instrumentation was the *multiplier* on top of the fixture-load base cost. Sysmon removes the multiplier but not the base cost. After A1, the binding constraint is the per-test fixture reload itself, which is what Phase B3 attacks.

3. **The auto-tag was both too narrow and not enough.** Too narrow because it only pinned `TestCase` subclasses with `setUpTestData`/`fixtures`, leaving plain `TestCase` classes vulnerable to interleave-on-worker pollution from other classes' uncommitted state. But broadening the pin to all `TestCase` subclasses would reintroduce most of loadscope's class-pinning floor, undoing worksteal's benefit. The fundamental issue is that the tests have hidden ordering dependencies, not that the scheduler is wrong.

**What we kept (Phase A1, landed):**

- Python 3.12.7 in the image (`compose/{local,production}/django/Dockerfile`).
- `COVERAGE_CORE=sysmon` (`.envs/.test/.django`).
- Dropped `django_coverage_plugin` (`setup.cfg`).

**What we reverted (Phase B1, removed):**

- `.github/workflows/backend.yml` returned to `--dist loadscope`.
- `conftest.py::pytest_collection_modifyitems` returned to handling only the `serial` marker.

**Implication for B2/B3:** Phase B3 (class-once fixture load for `WebsocketFixtureBaseTestCase` + per-test TRUNCATE-restore) is now the highest-ROI remaining lever. It directly attacks the 177-test × ~25 s = ~74 min single-threaded fixture-reload cost without requiring any change to the dist scheduler or risking the test-isolation bugs worksteal exposes. Phase B1 should only be re-attempted *after* a dedicated test-isolation sweep that finds and fixes the `admin`-user collision pattern (probably in factories + Celery-eager + migration seeds) so that worksteal can run cleanly.
