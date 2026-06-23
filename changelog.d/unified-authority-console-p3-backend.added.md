- **Authority Console — Phase 3 backend (frontier action verbs).** Added
  superuser-gated admin row-actions for the `AuthorityFrontier` discovery queue:
  `requeue` / `reset` / `reroute` / `approve` / `delete_rows` on
  `AuthorityFrontierService`, each a thin wrapper over the single `mark()`
  transition primitive, exposed as GraphQL mutations
  (`config/graphql/authority_frontier_mutations.py`:
  `requeue/reset/reroute/approve/deleteAuthorityFrontier`).

### Fixed
- **`mark()` can now clear fields, fixing the requeue constraint trap.** The
  `AuthorityFrontierService.mark()` primitive gained `clear_document` /
  `clear_error` / `clear_provider` / `set_provider` kwargs (previously it could
  only *set* `ingested_document`/`last_error`). An admin **requeue** of an
  already-ingested row now moves it back to `queued` while clearing
  `ingested_document` — without this, the `frontier_queued_no_ingested_doc`
  CheckConstraint would reject the save. This also un-sticks `deferred_cap` rows
  (the silent backlog): a requeued row becomes `dequeue_queued`-able again.
  `reroute` validates the target provider against the registered provider class
  names before re-queuing. Set/clear kwargs are guarded as mutually exclusive.
