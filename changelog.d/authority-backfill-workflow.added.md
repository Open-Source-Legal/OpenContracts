- **Authority-backfill workflow: production entry points, reactive re-link,
  wanted-authorities queue.** The enrichment engine's `AuthorityCorpusBootstrapper`
  previously had no production caller, nothing reacted when an authority corpus
  landed, and the only view of missing authorities was the governance graph's
  ghost nodes. Now:
  - **Wanted-authorities queue** — `CorpusReferenceService.wanted_authorities(user, corpus_id=None)`
    (`opencontractserver/enrichment/services/corpus_reference_service.py`)
    aggregates EXTERNAL law references by authority prefix (subsection keys
    rolled up to their section root via `candidate_keys`), ranked by mention
    volume with per-key corpus counts. Exposed as the `wantedAuthorities(corpusId?)`
    GraphQL query (`config/graphql/annotation_queries.py`, types in
    `annotation_types.py`) and the corpus-scoped read-only agent tool
    `list_wanted_authorities`.
  - **Reactive re-link** — `EnrichmentService.relink_corpora_for_keys(keys)`
    finds every corpus holding EXTERNAL law refs satisfiable by the
    just-bootstrapped keys and re-runs the linking pass per corpus **as that
    corpus's creator**, preserving visibility semantics (a private authority
    resolves only corpora whose creators can see it — no leak). Per-corpus
    failures are logged and counted without aborting the sweep.
  - **Bootstrap entry points** — new composite
    `bootstrap_authority_corpus(...)` (`opencontractserver/enrichment/authorities.py`)
    wraps the bootstrapper with optional `make_public` (publishes the corpus;
    `Corpus.save` propagates to documents) and reactive re-link (default on).
    Exposed two ways, both routing through the composite: the approval-gated
    agent tool `bootstrap_authority_corpus` (sections as
    `{key, heading, text, source_url?}` dicts, validated) and the
    `bootstrap_authority` management command
    (`opencontractserver/corpuses/management/commands/bootstrap_authority.py`,
    JSON spec file, `--public`, `--no-relink`, `--corpus-id`).
  - Tests: `opencontractserver/tests/test_enrichment_backfill.py` (service
    aggregation, root-key rollup, visibility, relink incl. private-authority
    no-leak and subsection→root matching, composite flags, command happy-path
    + malformed-spec rejection, GraphQL incl. malformed-ID guard) and registry/
    function coverage in `test_enrichment_tools.py`.
