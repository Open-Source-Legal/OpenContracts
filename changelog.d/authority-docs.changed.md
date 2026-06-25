- **Centralized authority-system documentation.** Added a single durable
  operator/author guide, `docs/guides/authoring-authority-packs.md` (pack layout,
  shipping a scraper inside a pack, `source_hosts`, add/remove/copy-to-port,
  what's still core), wired into the mkdocs nav alongside the existing
  Authority Console and Reference-Web Enrichment architecture docs. The
  `0002-authority-packs` proposal is re-framed as design-history (it points to the
  guide for the how-to and notes the now-self-contained pack layout), its dangling
  `0001-…` reference de-linked, and the proposal added to the nav so it is no
  longer orphaned. The guide and the proposal favour pointers to real files over
  pasted code to limit staleness.
