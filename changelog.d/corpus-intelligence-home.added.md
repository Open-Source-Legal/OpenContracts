- **Corpus Intelligence home (Phase 1).** The corpus landing now opens with a
  composed "God's-eye view" so an everyday user immediately experiences
  large-scale document intelligence on collections they already have access to.
  It fuses three existing capabilities into one surface
  (`frontend/src/components/corpuses/CorpusHome/intelligence/`):
  an insight-framed metrics panel (`IntelligencePanel` — documents, citation
  density, summary coverage, dominant labels), a visual document-relationship
  graph (`DocumentGraphGlimpse` — documents as nodes, relationships as edges,
  rendered with a deterministic d3-force layout — no new dependency), and
  one-click cross-document questions wired to the existing corpus agent
  (`CorpusIntelligenceOverview`). Composed into the default landing via
  `CorpusHome/CorpusLandingView.tsx`, reusing the existing `onChatSubmit` /
  `onViewDetails` callbacks (no routing changes).
- Two new permission-aware GraphQL resolvers back the home, both routed through
  the service layer (`DocumentRelationshipService`, `BaseService.filter_visible`)
  in `config/graphql/corpus_queries.py`: `corpusDocumentGraph(corpusId, limit)`
  returns degree-ranked document nodes + labeled edges (capped via
  `CORPUS_DOCUMENT_GRAPH_MAX_NODES`), and `corpusIntelligenceAggregates(corpusId)`
  returns label distribution + summary coverage. A private document inside a
  shared corpus stays hidden from users without document-level READ. New types
  live in `config/graphql/corpus_types.py`; new constants in
  `opencontractserver/constants/stats.py`. Tests:
  `opencontractserver/tests/test_corpus_intelligence.py` (resolvers, limit
  truncation, permission filtering) and
  `frontend/tests/DocumentGraphGlimpse.ct.tsx` (graph rendering, truncation,
  empty state).
