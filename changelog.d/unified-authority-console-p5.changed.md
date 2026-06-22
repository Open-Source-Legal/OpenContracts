- **Authority Console — Phase 5 (runs tab + final cleanup; initiative complete).**
  The standalone `/admin/enrichment` page (`AdminEnrichment.tsx`) is **absorbed**
  into the console's **Runs** tab and **deleted** (page + CT + wrapper + route +
  export). The Runs tab re-mounts the existing `EnrichmentRunner` /
  `EnrichmentJobList` (driven by `useOptimisticRows`) unchanged — those stay in
  `components/admin/enrichment/` because the per-corpus `CorpusEnrichmentCard`
  also consumes them; only the page wrapper moved. The transitional
  `PlaceholderTab` is removed (all five tabs are now real). This completes the
  unified Authority Console: **all three former standalone admin panels
  (`/admin/authorities`, `/admin/authority-mappings`, `/admin/enrichment`) are
  deleted**, collapsed into one front door at `/admin/authority` with tabs for
  Authorities · Aliases & Relationships · Discovery Queue · Scrapers · Runs —
  zero duplicate components, zero dead code.
