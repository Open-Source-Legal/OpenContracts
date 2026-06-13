- **One-click collection-intelligence setup** — the orchestration layer the
  enrichment pieces were missing: nothing previously composed the
  deterministic reference web with the LLM document enrichment at corpus
  setup, so new corpora landed with unreadable document indexes (raw import
  metadata as descriptions, 0% summary coverage) until each action was
  manually added from the Action Library and batch-run.
  - `CorpusIntelligenceSetupService`
    (`opencontractserver/corpuses/services/intelligence_setup.py`):
    idempotent composite that installs the reference-enrichment
    `add_document` action + starts the first weave, clones the
    *Document Description Updater* and *Document Summary Generator*
    templates (bundle pinned in
    `opencontractserver/constants/corpus_actions.py`
    `INTELLIGENCE_SETUP_TEMPLATE_NAMES`), and batch-runs each over every
    document already in the corpus. Re-running converges: existing action
    rows are reused, already-run documents are skipped, an in-flight
    reference analysis is not duplicated.
  - GraphQL: `setupCorpusIntelligence` mutation +
    `corpusIntelligenceSetupStatus` query
    (`config/graphql/corpus_mutations.py`, `corpus_queries.py`,
    `corpus_types.py`); `createCorpus` now returns `objId` so follow-up
    mutations can chain off creation.
  - Frontend: `IntelligenceSetupBanner`
    (`frontend/src/components/corpuses/CorpusHome/intelligence/`) renders a
    setup CTA inside `IntelligencePanel` (so both the intelligence overview
    and the `insight-panel` CAML embed surface it) and hides once the bundle
    is installed; the New Corpus modal gains a default-on "Set up collection
    intelligence" opt-in that chains the mutation after creation
    (`CorpusModal.tsx`, `views/Corpuses.tsx`).
  - Tests: `opencontractserver/tests/test_intelligence_setup.py` (service +
    GraphQL), `frontend/tests/IntelligenceSetupBanner.ct.tsx`.
