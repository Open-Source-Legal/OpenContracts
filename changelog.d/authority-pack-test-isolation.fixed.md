- **Test suite: a developer's authority-pack fetch cache no longer leaks into tests.**
  `config/settings/test.py` inherited the default
  `AUTHORITY_PACK_INSTALL_DIR = ROOT_DIR/.authority_packs`, which is a real fetch
  cache on any machine where `install_authority_pack` has been run — and which
  `pipeline/registry.py::authority_pack_dirs` scans as an implicit discovery
  root. Every test touching pack discovery was therefore environment-dependent:
  `test_authority_pack_sideload.py::AuthorityPackDiscoveryTests` (3 tests) failed
  locally while passing in CI, and the SSRF allowlist union, pack catalog, and
  in-pack provider imports were silently exposed the same way. Test settings now
  pin the install dir to a path that does not exist, so the third discovery
  source contributes nothing unless a test opts in via `override_settings`; the
  tests that assert an exact pack set also state that precondition themselves.
