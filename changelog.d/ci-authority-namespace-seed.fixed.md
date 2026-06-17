- Backend CI: fixed the recurring `AuthorityNamespace` seed-test failures
  (`test_authority_namespace.py::AuthorityNamespaceSeedTests` and
  `test_enrichment_discovery.py::DiscoveryTests::test_grammar_tier_finds_open_vocabulary_authorities`)
  on the self-hosted runner. The one-shot `RunPython` seed (migration `0082`)
  and its reseed (`0085`) only ever run once per migration ledger, so a
  persistent `pytest --reuse-db` test-database volume that already records the
  seed migration as applied keeps an empty `AuthorityNamespace` table forever —
  a later reseed migration cannot help because it too is recorded applied after
  its first run. Added an idempotent `post_migrate` receiver
  (`opencontractserver/enrichment/_namespace_seed.py::ensure_seeded`, wired in
  `opencontractserver/annotations/apps.py`) that re-runs the `update_or_create`
  seed on every `migrate`, converging any reused/poisoned database while staying
  a no-op on freshly-seeded and production databases.
