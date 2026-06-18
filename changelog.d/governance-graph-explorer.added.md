- **Reference-web graph explorer** — the "Explore the full graph" link on the
  corpus governance/reference-web glimpse now opens a dedicated, deep-linkable
  full-screen explorer (`?view=graph`) instead of dumping the user on the corpus
  documents list. New view `GovernanceGraphExplorer.tsx` renders the same
  deterministic bipartite layout as the glimpse (filings above, the law on a
  pinned shelf below) at full scale, adding d3-zoom pan/zoom, a control rail
  (text search + filing/statute/cited-not-ingested layer toggles + per–body-of-law
  filters that dim rather than reflow, for spatial stability), and a node-detail
  drawer that surfaces jurisdiction, authority type, frontier crawl status, and
  the node's citations with click-through into the document.
  - Extracted the glimpse's intricate force-layout geometry into a shared,
    behaviour-preserving `frontend/src/utils/governanceGraphLayout.ts`
    (`computeGovernanceLayout` + label helpers) consumed by both the glimpse and
    the explorer — single source of truth, pixel-identical glimpse output.
  - `GET_GOVERNANCE_GRAPH` now also selects the already-available
    `jurisdiction`, `authorityType`, and `discoveryState` node fields.
  - Added `view=graph` to the corpus-home view whitelist (`cache.ts`,
    `CentralRouteManager`, `navigationUtils.updateDetailViewParam`) and repointed
    every "Explore the full graph" callback (`CorpusHome`, `CorpusLandingView`,
    article/CAML embeds) at it.
