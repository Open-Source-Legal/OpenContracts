- **`governanceGraph` GraphQL query** — the corpus-scoped reference web in
  node-link form, the in-app successor to `demo/export_governance_graph.py`
  (first integration step from #1976's callout). Nodes are documents (filing
  primaries, exhibits, statute sections) plus "ghost" nodes for law citations
  with no visible target document; edges are mention-weighted `LAW` (resolved,
  possibly cross-corpus), `LAW_EXTERNAL` (rolled up to the citation's section
  root), and `DOCUMENT` (`DocumentRelationship` rollups).
  - Graph assembly lives in
    `opencontractserver/enrichment/services/governance_graph_service.py`;
    the resolver (`config/graphql/annotation_queries.py`) only encodes relay
    ids — no inline Tier-0 (E001 green).
  - Visibility: corpus READ gates the query (invisible corpus → empty graph);
    every surfaced document is independently READ-checked — invisible source
    documents drop their edges, invisible target documents degrade to external
    ghost nodes so titles never leak, and only READ-visible target corpora are
    listed (pinned by `opencontractserver/tests/test_governance_graph.py`).
  - Node lists are degree-capped at `GOVERNANCE_GRAPH_MAX_NODES` (200,
    `opencontractserver/constants/stats.py`) with full-graph counts +
    `truncated` flag, mirroring `corpusDocumentGraph`'s contract.
