- The global **Authority Sources** monitor (`/admin/authorities`) can now
  **run discovery on a selected subset** of the queue, not just observe it.
  Select queued `AuthorityFrontier` rows (per-row checkboxes + a header
  "select all in current filter") and trigger authority discovery on exactly
  those rows — closing the gap where the only trigger was the corpus-bound
  enrichment runner.
  - Backend: new superuser-only `runAuthorityDiscovery(frontierIds: [ID!]!)`
    mutation (`config/graphql/enrichment_mutations.py`) → fire-and-forget
    `discover_selected_authorities` Celery task
    (`opencontractserver/tasks/corpus_tasks.py`) →
    `CrawlAuthoritiesService.discover_selected`
    (`opencontractserver/enrichment/services/crawl_authorities_service.py`),
    which loops `discover_and_bootstrap` over the chosen rows **depth-0** (no
    seed-from-wanted, no child seeding). Corpus-agnostic — no `Analysis` row.
  - `AuthorityFrontierNode` gains `ingestable` / `predictedProvider`
    (`config/graphql/annotation_types.py`) so the monitor shows which rows a
    provider can actually handle and warns when a selection includes
    no-provider rows (they record `unsupported`).
  - Frontend (`AuthoritySourcesMonitor.tsx`): selection + sticky action bar
    ("N selected", no-provider warning, Run discovery), a Provider/ingestable
    indicator column, and live polling that reflects each row's
    `discovery_state` as the run settles.
