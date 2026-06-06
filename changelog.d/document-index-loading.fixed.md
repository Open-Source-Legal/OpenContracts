- **Document index showed a previously-viewed document's sections until the
  network caught up.** The top-level `annotations` Relay field policy
  (`frontend/src/graphql/cache.ts`) keyed its cache list with
  `ContextAwareRelayStylePaginationKeyArgsFunction`, which returned only the
  field name/alias and ignored every filter argument. As a result the corpus
  annotation list, the card grid, and the document index
  (`GET_DOCUMENT_ANNOTATION_INDEX`) all collapsed into a single Relay list, so
  with `fetchPolicy: "cache-first"` the index served whichever document was
  opened last (e.g. "only 3 OC_SECTION refs from the old doc") until the
  network response replaced it. The key function now folds the filter
  arguments into the cache key — excluding the Relay pagination cursors
  (`first`/`last`/`before`/`after`) so genuine infinite-scroll pages of one
  filter set still merge — isolating each document/corpus/label into its own
  list. Also fixed the latent alias bug in the same function: `field.alias` is
  a GraphQL `NameNode`, so it now reads `.value` instead of stringifying the
  node to `"[object Object]"`. Regression tests added in
  `frontend/src/graphql/__tests__/cache.test.ts`.
- **Mobile "Sections" sheet loaded nothing for indexed documents.**
  `MobileSectionsSheet` (`frontend/src/components/knowledge_base/document/layouts/mobile/MobileSectionsSheet.tsx`)
  read the *structural* annotation set (`structural=true`), but the document
  index is built from `OC_SECTION` annotations, which the enricher marks
  `structural=false` (`opencontractserver/pipeline/enrichers/pdf_outline_enricher.py`).
  Those sets are disjoint, so an OC_SECTION-indexed document rendered an empty
  mobile sheet while the desktop "Index" tab was full. The sheet now loads the
  same `GET_DOCUMENT_ANNOTATION_INDEX` query the desktop tab uses (a flat,
  page-ordered jump list with the mobile-native styling preserved), gated on
  the sheet being open so the fetch stays lazy. `MobileDocumentLayout` now
  threads `documentId`/`corpusId` to the sheet. Tests updated:
  `frontend/tests/MobileSectionsSheet.{ct,harness}.tsx`,
  `frontend/tests/MobileDocumentLayout.harness.tsx`, and
  `frontend/tests/MobileDocumentKnowledgeBase.ct.tsx`.
