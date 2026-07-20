- Removed the now-dead `ensure_aiohttp_vcr_compat()` aiohttp/vcrpy compat shim
  (`opencontractserver/utils/vcr_replay.py`) and its call sites in `conftest.py`
  and `maybe_vcr_cassette()`. The shim restored
  `aiohttp.streams.AsyncStreamReaderMixin`, a symbol aiohttp 3.14 removed and
  vcrpy 8.1.1's aiohttp stub subclassed at import time (issue #1920). vcrpy
  8.2.0 fixed the stub upstream (kevin1024/vcrpy#996) — `MockStream` no longer
  inherits the mixin — so the shim has been a no-op since the pin moved to
  8.2.1. Verified empirically against `vcrpy==8.3.0` + `aiohttp==3.14.1`:
  entering a cassette with no shim applied succeeds. The `aiohttp>=3.13,<3.14`
  cap this was paired with had already been lifted. The
  `EnsureAiohttpVcrCompatTests` shim unit tests are replaced by
  `VcrCassetteEntryTests` in `opencontractserver/tests/test_vcr_replay.py`,
  which keeps the meaningful regression guard: entering a cassette (and thus
  lazily importing `vcr/stubs/aiohttp_stubs.py`) must not raise. Closes #2140.
