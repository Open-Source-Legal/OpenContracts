- **Removed the `ensure_aiohttp_vcr_compat()` shim and its stale pin rationale.**
  vcrpy 8.2.0+ restored aiohttp 3.14 compatibility (the broken
  `AsyncStreamReaderMixin` reference was dropped in
  [`kevin1024/vcrpy#996`](https://github.com/kevin1024/vcrpy/pull/996)), and
  `requirements/local.txt` already pins `vcrpy==8.3.0`. The compat shim in
  `opencontractserver/utils/vcr_replay.py`, its call site in `conftest.py`,
  the `EnsureAiohttpVcrCompatTests` test class, and the eight-line comment
  block above the vcrpy pin were dead code. Resolves #2140.
