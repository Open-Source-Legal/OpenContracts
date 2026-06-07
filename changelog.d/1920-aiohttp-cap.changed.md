- Lifted the temporary `aiohttp<3.14` cap in `requirements/base.txt` (added in
  #1914), returning `aiohttp` to its natural unpinned-transitive state so CI
  resolves the current 3.14+ line again. vcrpy 8.1.1 (the latest release, still
  pinned in `requirements/local.txt`) is not yet compatible with aiohttp 3.14:
  `vcr/stubs/aiohttp_stubs.py` subclasses `aiohttp.streams.AsyncStreamReaderMixin`
  at import time, a symbol aiohttp 3.14 removed (kevin1024/vcrpy#995; fix proposed
  in the unreleased PR #996). A small, idempotent import-time shim,
  `ensure_aiohttp_vcr_compat()` in `opencontractserver/utils/vcr_replay.py`,
  restores that symbol as an empty mixin so VCR cassette entry works under
  aiohttp >=3.14 (this codebase only records/replays httpx LLM cassettes, so the
  aiohttp `MockStream` is never instantiated). The shim is applied from the root
  `conftest.py` before any test module's top-level `import vcr`, and from
  `maybe_vcr_cassette()` for the non-pytest E2E record/replay harness. Delete the
  shim and bump `vcrpy` once a release ships the vcrpy#996 fix. Regression test:
  `opencontractserver/tests/test_vcr_replay.py::EnsureAiohttpVcrCompatTests`.
  Closes #1920.
