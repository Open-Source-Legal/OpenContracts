- **Default corpus article now composes the governance graph** — the canonical
  CAML intelligence block (`opencontractserver/corpuses/caml_intelligence.py`,
  `CAML_INTELLIGENCE_BLOCK` + `CAML_INTELLIGENCE_MARKERS`) predated the
  reference web and only embedded `insight-panel` / `document-graph` /
  `ask-across-docs`. A corpus created with LLM auto-branding disabled (the
  `CORPUS_AUTO_BRANDING_ENABLED=False` kill-switch path) therefore got a
  structural default article with **no governance graph and no "Map the
  reference web" bootstrap CTA** — the reference web was unreachable from the
  corpus home. The block now includes `[component:governance-graph]` ("How
  this collection is wired to the law") between the insight panel and the
  document graph, mirroring `CorpusIntelligenceOverview`'s composition; the
  marker tuple addition also makes `ensure_intelligence_block` /
  `backfill_intelligence_block` aware of it. Discovered while recording the
  corpus-creation→enrichment demo. Test updated:
  `opencontractserver/tests/test_caml_intelligence_block.py`.
