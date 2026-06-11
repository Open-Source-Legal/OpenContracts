- **Enrichment mention links no longer 404** — the writer and
  `link_external_references` wrote `link_url` as `/corpus/{id}/document/{id}`,
  a shape no frontend route serves (it falls into the `*` catch-all → 404).
  They now emit the canonical slug path
  `/d/{corpus.creator.slug}/{corpus.slug}/{document.slug}` via the new
  `opencontractserver/utils/frontend_paths.py::document_in_corpus_path`
  helper (mirrors the frontend's `buildCanonicalPath`); cross-corpus law
  links point into the authority corpus. Links with missing slugs are
  skipped rather than written broken.
- **`@corpus_analyzer_task` no longer marks a retrying Analysis FAILED**
  (`opencontractserver/shared/decorators.py`) — `celery.exceptions.Retry`
  extends `Exception`, so the wrapper's failure branch stamped
  `Analysis.status=FAILED` before the retry ran. `Retry` is now re-raised
  untouched, mirroring `doc_analyzer_task`; regression test pins the
  RUNNING status surviving a retry.
- **Enrichment perf**: OC_SECTION lookups batched to one query per corpus
  (was one per document), and `link_external_references` collapses O(N)
  row-by-row saves into two `bulk_update` calls (refs + mentions).
