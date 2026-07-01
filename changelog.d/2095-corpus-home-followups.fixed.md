- **Fixed a null-title crash in the corpus-home Collection Overview panel.**
  `IntelligencePanel.tsx`'s documents-index sort comparator
  (`frontend/src/components/corpuses/CorpusHome/intelligence/IntelligencePanel.tsx`)
  called `a.title.localeCompare(b.title)` directly. `Document.title` is
  `CharField(null=True, blank=True)` (`opencontractserver/documents/models.py`),
  so a document with a `null` title (mid-ingest, or a parser that never set
  one) threw a `TypeError` and crashed the entire panel for that corpus. The
  render path already guarded with `doc.title || "Untitled document"`; the
  comparator now applies the same `(a.title || "").localeCompare(b.title || "")`
  guard. Added a regression test to `frontend/tests/IntelligencePanel.ct.tsx`
  that mounts the panel with a null-titled document and asserts it renders
  (rather than throwing) with the "Untitled document" fallback. (#2095)
