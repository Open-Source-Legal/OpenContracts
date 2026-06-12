- **Intelligence setup: large corpora no longer silently skip enrichment.**
  `CorpusActionService` gained `batch_run_action(user, action, allow_partial=)`
  (`opencontractserver/corpuses/services/corpus_actions.py`) — the trusted-caller
  variant the one-click setup now uses with `allow_partial=True`, queuing the
  first `BATCH_RUN_MAX_DOCS` documents (deterministic id order) instead of
  refusing outright when a corpus exceeds the per-call cap. The per-template
  outcome (`TemplateSetupOutcome.remaining_count`, exposed as `remainingCount`
  on `IntelligenceTemplateOutcomeType`) reports the deferred remainder and the
  banner toast surfaces it. Previously a 250-doc corpus got a success toast, a
  permanently hidden banner, and zero documents enriched.
- **Intelligence-setup status no longer demands deployment-unavailable pieces.**
  `IntelligenceSetupStatus.is_fully_set_up`
  (`opencontractserver/corpuses/services/intelligence_setup.py`) excludes the
  reference action when no enrichment analyzer is registered
  (`reference_available`, new on the status payload) and excludes bundle
  templates that are unseeded/inactive deployment-wide — either condition
  previously made the setup CTA an undismissable zombie whose every click
  toasted success.
- **Setup CTA hidden from viewers who can't run it.** The status payload gained
  `can_setup` (mirrors the mutation's permission gate);
  `IntelligenceSetupBanner.tsx` renders nothing unless `canSetup` — read-only
  and anonymous viewers of a public not-set-up corpus previously saw a
  guaranteed-to-fail "Set up" button.
- **Permission tier harmonized to CRUD.** `setupCorpusIntelligence` (service +
  mutation docstrings, `config/graphql/corpus_mutations.py`) now requires CRUD
  on the corpus — the tier `AddTemplateToCorpus` and `CreateCorpusAction`
  already gate the identical writes at; it previously required only UPDATE, a
  weaker path to the same row installs.
- **Reference action can no longer be double-installed.** The governance
  graph's "Map the reference web" bootstrap
  (`GovernanceGraphLive.tsx`) consults `corpusIntelligenceSetupStatus` and
  skips `createCorpusAction` when the add_document reference action already
  exists (a duplicate row would run the enrichment analyzer twice on every
  future upload); the server side switched to `get_or_create` to narrow the
  concurrent-race window.
- **Post-create setup opt-in surfaces soft failures.** `Corpuses.tsx` now
  inspects the resolved `setupCorpusIntelligence.ok` and shows the
  "couldn't start" toast — an `ok=false` envelope was previously discarded,
  leaving users to believe enrichment was running.
- **Setup warning toast names the actual failures.** The banner aggregates
  `templates[].error` into the warning instead of a generic guess.
- **In-flight weave reported as started.** When an enrichment analysis is
  already QUEUED/RUNNING, `CorpusIntelligenceSetupService.setup`
  (`opencontractserver/corpuses/services/intelligence_setup.py`) no longer leaves
  `reference_analysis_started=False` — the reference web *is* being built, so the
  summary (and the banner toast's "reference web weaving" note) now reflects it
  instead of silently omitting it.
- **`setup()` permission lookup collapsed to one IDOR-safe call.** The READ
  `get_or_none` + separate `require_permission(CRUD)` pair became a single
  `get_or_none(Corpus, …, PermissionTypes.CRUD)` (the canonical pattern
  `status()` already uses) — no behavior change, but no longer a divergent
  double-check.
- **Dedup/cleanup.** Template installs go through a single shared
  `CorpusActionService.install_template` (dedupe fast-path, savepoint clone,
  IntegrityError recovery, CRUD grant) used by both `AddTemplateToCorpus` and
  the bundle; the enrichment analyzer lookup goes through the new lookup-only
  `EnrichmentService.get_analyzer()` next to the converge logic; setup
  prefetches bundle templates with `name__in` and derives
  `total_active_documents` from the batch summary instead of a redundant
  corpus-document count.
