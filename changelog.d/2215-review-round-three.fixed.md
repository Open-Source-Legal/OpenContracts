- **Authority pack install no longer reports a committed install as failed.**
  `_install_plan` (`opencontractserver/enrichment/services/authority_pack_service.py`)
  commits taxonomy/corpora/relationships in one `transaction.atomic()` block and
  then runs the reactive relink; `install()` re-runs `preflight_path` afterwards
  to report fresh state. Both steps are post-commit, and an exception in either
  surfaced as `ok=False` (relink: uncaught, propagating out of the resolver;
  refresh: caught by the `(CommandError, OSError, UnicodeError)` tuple) for a
  pack that was already in the database. The idempotent retry then silently
  no-ops, so the operator's view and the database never reconcile. Both now
  degrade to `post_commit_warnings` carried on `AuthorityPackInstallResult` —
  surfaced in the GraphQL mutation `message` + `result.warnings`, and printed by
  `load_authority_pack`. The refresh failure falls back to the approved
  pre-install plan rather than returning nothing.
- **Concurrent first install of the same authority pack returns a clean
  refusal.** `_preflight_corpus_identities` reads without a lock, so two
  installs can both see "no such corpus" and then collide inside
  `bootstrap_authority_corpus`'s `get_or_create(slug=…, creator=…)`. The
  resulting `IntegrityError` was outside `install()`'s caught-exception tuple
  and escaped raw. It is now caught on its own and returned as
  `CONCURRENT_INSTALL_MESSAGE`; the loser's atomic block rolls back, so nothing
  of its attempt survives and a retry converges.
- **A gate fault no longer wedges an `AuthorityFrontier` row in `in_progress`.**
  `AuthorityDiscoveryService.discover_and_bootstrap` marks the row in-flight
  before fetching; the fetch and bootstrap stretches each had a fault handler
  but the gate stretch (approval fingerprint → `AuthorityGateService.evaluate` →
  audit record) did not. Since `dequeue_queued` only returns `queued` rows, a
  stranded row was invisible to every later crawl until an admin reset it by
  hand, and the exception also aborted the whole `crawl_authorities_service`
  batch. That stretch now has its own handler that marks the row `failed` with
  an audit record — deliberately separate from the bootstrap handler, which
  builds its record from a `decision` that is not yet bound there.
- **`AuthorityGateService._verify_rich_publisher_evidence` catches broadly and
  fails closed.** Its `except (KeyError, TypeError, ValueError)` let an
  unlisted exception type from a provider's `verify_publisher_evidence`
  override (an in-pack provider is free to raise `AttributeError`/`IndexError`
  off a malformed evidence payload) escape the gate entirely. The catch is now
  `Exception` + `logger.exception`; the return is still `False`, so a broken
  verifier can only ever refuse a record, never admit an unverified one.
- **`PipelineComponentRegistry` construction is thread-safe.**
  `__new__`/`__init__`'s check-then-act was unsynchronised and `get_registry()`'s
  `lru_cache` does not serialise the wrapped call on a miss, so two threads
  racing on first access could both enter discovery — which walks the
  filesystem, `exec_module`s every in-pack authority provider, and mutates the
  process-global `sys.modules` — while the second thread sailed past the
  `_initialized` flag (set *before* discovery) and read component tuples that
  were still empty. Construction and `reset_registry()` now hold a class-level
  `threading.RLock`; re-entrant same-thread access from a pack module's import
  behaves exactly as before.
