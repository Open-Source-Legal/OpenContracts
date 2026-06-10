- **Governance Graph panel** — the reference web, rendered on the Corpus
  Intelligence home. A bipartite d3-force composition (deterministic, seeded,
  no animation loop): filing documents cluster in an upper band (connected
  components over DOCUMENT edges drive per-cluster hues; swarm clusters spread
  into wide constellations), statute sections pin to an authority-grouped "law
  shelf" below with staggered citation-head labels and authority captions, and
  mention-weighted amber citation arcs sweep between the layers (dashed slate
  for citations without an in-system target). Scale-aware rendering (degree-
  gated shelf labels, thinned edges, abbreviated captions) keeps 200-node
  corpora legible. Hover focuses a node's incident edges; clicking any
  document/statute node navigates to its canonical page — across corpora.
  - `GovernanceGraphGlimpse` / `GovernanceGraphLive` / `GovernanceGraphEmbed`
    (`frontend/src/components/corpuses/CorpusHome/intelligence/`), registered
    as the `governance-graph` CAML embed and composed into
    `CorpusIntelligenceOverview`; layout + palette vocabulary in
    `frontend/src/assets/configurations/constants.ts`.
- **One-click reference-web bootstrap** — the panel's empty state offers
  "Map the reference web": discovers the corpus-reference-enrichment analyzer
  by task name, starts an immediate corpus analysis (`startAnalysisOnDoc`),
  installs an `add_document` CorpusAction so the web grows with the corpus,
  and polls until the first weave lands ("Weaving the reference web…").
- **References side panel** in the document viewer — a new "References" tab
  (`frontend/src/components/knowledge_base/document/DocumentReferencesPanel.tsx`)
  shows one document's slice of the web: **Cites** (outbound, grouped by
  canonical key with mention counts — "SEC Rule § 144 ×26" — ghost rows noted
  "cited, not yet ingested") and **Cited by** (inbound, grouped by source
  document). Resolved rows navigate to the cited statute/exhibit via the
  mention's canonical link; inbound rows resolve the source document by id
  (`frontend/src/hooks/useNavigateToDocumentById.ts`, shared with the graph).
- **`corpusReferences(documentId:)` filter** — restricts the reference listing
  to rows touching one document on either side (the single-fetch shape the
  References panel needs); `config/graphql/annotation_queries.py`.
