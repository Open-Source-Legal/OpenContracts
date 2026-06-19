- Backend CI: fixed the recurring `AuthorityNamespace` seed-test failures
  (`test_authority_namespace.py::AuthorityNamespaceSeedTests` and
  `test_enrichment_discovery.py::DiscoveryTests::test_grammar_tier_finds_open_vocabulary_authorities`).
  The shipped namespaces are seeded by the one-shot `RunPython` migrations
  (`0082`/`0085`), so the rows live outside any test's transaction. Django's
  `flush` — run on every `TransactionTestCase` teardown — truncates
  `annotations_authoritynamespace` along with every other table
  (`serialized_rollback` is `False` by default), so under
  `pytest -n auto --dist loadscope` any `TransactionTestCase` running before
  these plain-`TestCase` tests on the same worker left them reading an empty
  registry. An idempotent `post_migrate` receiver
  (`opencontractserver/enrichment/_namespace_seed.py::ensure_seeded`, wired in
  `opencontractserver/annotations/apps.py`) re-seeds the rows after every
  `post_migrate`. `migrate` emits that signal with an `apps` kwarg but `flush`
  emits it without one, so — like Django's own `create_contenttypes` /
  `create_permissions` receivers — the receiver now falls back to the global
  app registry instead of bailing when `apps` is absent, which is the
  flush-path emission that actually has to restore the rows. The seed stays a
  no-op on freshly-seeded and production databases.
