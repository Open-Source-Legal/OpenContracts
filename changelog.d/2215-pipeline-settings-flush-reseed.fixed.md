- **The `PipelineSettings` singleton now survives a `TransactionTestCase`
  flush, fixing a 600s test-suite deadlock.** Migration
  `0031_add_pipeline_settings` seeds the singleton with a one-shot `RunPython`,
  so its row lives outside any test transaction. Django's `flush` — run on
  every `TransactionTestCase` teardown — truncates
  `documents_pipelinesettings` along with every other table, and with
  `serialized_rollback` disabled (the default) nothing restored it. Under
  `pytest -n 4 --dist loadscope`, any `TransactionTestCase` running before an
  embedder-touching test on the same worker left the install with **no**
  singleton for the rest of that worker's session.

  Because `PipelineSettings.get_instance()` re-creates the row lazily, the
  absence did not fail loudly — it deadlocked. An `async` test under Django's
  `TestCase` reaches `get_embedder` → `get_default_embedder_path` →
  `get_instance` on the asgiref executor thread, which holds its own DB
  connection; that connection cannot see the main thread's uncommitted row, so
  it issued a competing `INSERT` and blocked on the test transaction's lock
  while the main thread was parked in `AsyncToSync.__call__` waiting for the
  executor. Neither side could advance until `pytest-timeout` fired at 600s,
  and the hang left `unittest.mock.patch` decorators un-exited, cascading into
  every later test in the class sharing the patched target. Observed as 5
  failures in `test_core_agents.py::TestCoreAgentFactoriesDefaults` (two
  600.01s timeouts plus three `'Mocked default prompt'` assertion errors).

  Fixed with an idempotent `post_migrate` receiver
  (`opencontractserver/documents/_pipeline_settings_seed.py`, connected in
  `documents/apps.py`) that re-seeds the singleton after each flush and repairs
  reused/poisoned CI volumes at DB setup — mirroring the existing
  `enrichment/_namespace_seed.py` convergence for `AuthorityNamespace`. Like
  that sibling, it falls back to the global app registry when `post_migrate` is
  emitted without an `apps` kwarg, which is exactly how `flush` emits it.
  Regression test: `opencontractserver/tests/test_pipeline_settings_flush_reseed.py`.
