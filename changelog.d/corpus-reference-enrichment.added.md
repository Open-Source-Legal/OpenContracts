- **Corpus reference enrichment agent.** A corpus-scoped agent tool pair that
  crawls a corpus, inventories explicit references, and persists them — proven
  on a real 55-document S-1 corpus (348 references created).
  - New deterministic engine in `opencontractserver/enrichment/`
    (`extractor.py`, `resolver.py`, `writer.py`, `services/`): regex/grammar
    extraction of law citations (`Section 145 of the Delaware General
    Corporation Law` → canonical key `dgcl:145`), document/exhibit references,
    internal section references, and defined-term definition sites
    (`(the "Company")` / `"Change of Control" means …` → `term:company` /
    `term:change-of-control`, opt-in and capped); resolution to in-corpus target
    documents and OC_SECTION annotations.
  - New `CorpusReference` model (`opencontractserver/annotations/models.py`,
    migration `annotations/0078_corpusreference`): a first-class
    cross-document / cross-corpus / external-law connection with an indexed
    `canonical_key` join key (`target_corpus` anticipates future cross-corpus
    linking). Within-document section links continue to use `Relationship`;
    every reference also gets a mention `Annotation` (law payloads stored in
    `Annotation.data`, resolved document links in `Annotation.link_url` as
    in-app site-relative paths).
  - Two agent tools (`opencontractserver/llms/tools/core_tools/corpus_references.py`,
    registered in `tool_registry.py`): `scan_corpus_references` (read-only
    inventory) and `apply_corpus_reference_enrichment`
    (`requires_approval=True`, `requires_write_permission=True`) — the
    CAML-style scan → approval-gated apply pattern. Enrichment is idempotent.
  - Read-only GraphQL `corpusReferences(corpusId)` query
    (`config/graphql/annotation_types.py`, `annotation_queries.py`), visibility
    scoped to corpus READ via `CorpusReferenceService`.
  - Resolved document/exhibit references additionally roll up to
    `DocumentRelationship` rows (`enrichment/writer.py`), feeding the corpus
    document graph. Mention dedup is by (document, label, span start) so a
    growing alias registry cannot duplicate mentions.
- **Authority corpora + cross-corpus law linking.**
  - `opencontractserver/enrichment/authorities.py`: `AuthorityCorpusBootstrapper`
    materialises statute sections as keyed text documents
    (`Document.custom_meta.canonical_key`, e.g. `dgcl:145`), idempotently
    (skip / version-up on amendment / self-healing restamp after concurrent
    pipeline saves). `find_authority_target` resolves citations with
    subsection→section fallback (`dgcl:122(17)` → `dgcl:122`), visibility- and
    current-version-aware.
  - `EnrichmentService.link_external_references` upgrades EXTERNAL law
    citations to RESOLVED cross-corpus links (`target_corpus`/`target_document`
    + in-app `link_url` on the mention); runs automatically inside `apply()`
    and is re-runnable as new authority corpora appear.
  - Data-driven authority alias registry: `authority_alias_registry(user)`
    merges static defaults with `custom_meta.authority_aliases` declared by
    authority corpora — adding a body of law is a bootstrap call, zero code.
- **Citation grammar coverage** (`enrichment/extractor.py`): suffix form
  ("Section 145 of the DGCL"), prefix form ("Securities Act Section 4(a)(5)"),
  statute-internal relative form ("§ 251 of this title", keyed via the
  document's own authority context), and bare SEC rules ("Rule 506(b)",
  "Rule 144A", "Rule 10b-5" → `sec-rule:*`).
- **Analyzer framework: corpus-scoped analyzers.**
  - New `@corpus_analyzer_task` decorator (`shared/decorators.py`) — the
    corpus-scoped sibling of `@doc_analyzer_task`: runs once per Analysis,
    owns its own writes, wrapper manages the Analysis lifecycle
    (RUNNING/COMPLETED/FAILED, timestamps, result/error messages).
  - `get_corpus_analyzer_task_by_name` / `get_analyzer_task_by_name`
    (`utils/celery_tasks.py`); `run_task_name_analyzer` dispatches
    corpus-scoped analyzers as a single task (no per-doc fan-out); analyzer
    auto-sync and the `analyzer.W001` check cover both flavours.
  - Enrichment adapter task
    (`opencontractserver/tasks/corpus_analysis_tasks.py`) registers the engine
    as a real task-based Analyzer (dispatchable via `CorpusAction`), attaching
    to the framework-created Analysis instead of creating its own.
- **Demo pipeline** (`demo/`, untracked zips excluded): authority seed JSONs
  with real statutory text (DGCL, Securities Act, Exchange Act, IRC, ICA,
  SEC Rules — 17 C.F.R.), bootstrap/import/export scripts, and a standalone
  D3 governance-graph visualization (`governance_graph.html`).
