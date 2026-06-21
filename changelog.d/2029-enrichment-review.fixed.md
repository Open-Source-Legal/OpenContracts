- **Closed a duplicate-notification race in the analysis-status signal
  (`opencontractserver/notifications/signals.py`, issue #2029 — PR #2008
  review).** The handler guarded duplicate `ANALYSIS_RUNNING/COMPLETE/FAILED`
  notifications with a `Notification.objects.filter(...).exists()` check
  followed by a separate `.create()`. Two concurrent `Analysis.post_save`
  signals (e.g. a Celery worker plus an in-process save) could both pass the
  `exists()` check before either committed, leaking duplicate rows. The
  check-then-create pair is now a single atomic `get_or_create`, backed by a new
  partial unique constraint `uniq_notification_per_analysis_type` on
  `(analysis, notification_type)` (`condition=analysis NOT NULL`) added in
  `opencontractserver/notifications/migrations/0007_notification_analysis_idempotency_constraint.py`.
  The migration de-dupes any pre-existing rows (keeping the earliest) before
  adding the constraint; the partial condition leaves the many analysis-less
  notification types unconstrained.
- **`runCorpusEnrichment` now rejects unknown `reference_types` instead of
  silently dropping them (`config/graphql/enrichment_mutations.py`).** A request
  whose `reference_types` contained only unrecognised codes previously filtered
  to an empty list, left `types` unset, and ran enrichment against ALL reference
  types — the opposite of the caller's intent. The mutation now returns
  `ok=False` naming the unknown code(s) and dispatches nothing.
- **`runCorpusEnrichment` surfaces partial success
  (`config/graphql/enrichment_mutations.py`).** When the enrichment analyzer
  dispatches but the authority crawl fails, the mutation now returns `ok=True`
  with the already-running enrichment row and a non-fatal message — previously
  it returned `ok=False` with the enrichment row mixed in, leading callers to
  treat the whole request as failed and retry (double-dispatching enrichment).
  The Runner (`frontend/src/components/admin/enrichment/EnrichmentRunner.tsx`)
  surfaces the message as a warning toast.
- **Forwarded `request` to the corpus UPDATE check in
  `AnalysisLifecycleService.start_document_analysis`
  (`opencontractserver/analyzer/services/analysis_lifecycle_service.py`).** The
  `user_can(user, UPDATE)` gate now shares the Tier-2 permission cache when
  called from a GraphQL mutation, removing a redundant permission DB hit.
