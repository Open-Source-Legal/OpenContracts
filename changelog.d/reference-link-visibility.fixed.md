- **References never render a link their audience cannot follow (no 404s).**
  The reference-link pass (`EnrichmentService._link_external`) now resolves
  against the citing corpus's *audience floor* — anonymous for a public corpus
  (so only public authorities may link), the creator otherwise — and is
  bidirectional: it promotes an EXTERNAL ref whose target is audience-visible to
  RESOLVED, and **demotes** a RESOLVED ref back to EXTERNAL (clearing its
  mention `link_url`) when the target authority is no longer audience-visible
  (e.g. an authority corpus goes private). Previously a public corpus could
  render clickable links into a private authority corpus, which 404'd for every
  non-owner viewer. `_restamp_mention_links` now mirrors each mention's
  `link_url` onto its ref's resolution state (set when resolved, cleared when
  not). `apply()` / `relink_corpora_for_keys` report a `links_demoted` count.
- **Document references panel surfaces resolution state clearly.**
  `DocumentReferencesPanel.tsx` replaces the faint "cited, not yet ingested"
  italic note with per-row status chips — a teal "Linked" chip on resolved rows
  and an amber "Awaiting source" chip (clock icon, with a tooltip explaining the
  authority isn't ingested yet) on unresolved law citations — plus a
  "N linked · M awaiting" breakdown in the Cites header.
