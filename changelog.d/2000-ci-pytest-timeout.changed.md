- CI backend test suite (`.github/workflows/backend.yml`) now runs pytest with
  `--timeout=600 --timeout-method=thread` (adds `pytest-timeout` to
  `requirements/local.txt`). A single test that blocks on a starved service —
  the 2-core runner runs `-n auto` workers alongside the docling/embedder ML
  containers — previously hung its worker until the 100-minute step ceiling with
  no traceback. It now fails fast (~10 min, ~10x the slowest legitimate test)
  and dumps the offending test's stack so the culprit is immediately
  identifiable. The `thread` method is required because it interrupts blocking C
  calls (sockets) the default `signal` method cannot, and works inside xdist
  workers.
