### Fixed

- **Corpus/folder document-list query no longer signs the same media URLs on
  every request.** Each document edge selects four file-URL fields
  (`pdfFile`, `txtExtractFile`, `pawlsParseFile`, `icon`); on GCS with IAM
  signBlob (Workload Identity, no local signing key) every `FieldFile.url` is a
  network round trip, so an N-document page fanned out to ~N×4 serialized
  signing calls (a ~7.8s corpus-folder query in production). The existing
  per-request memo in `config/graphql/optimized_file_resolvers.py` couldn't
  help — a list query never resolves the same `(document, field)` twice. Added
  a cross-request shared cache (Redis in prod) keyed by storage blob name (a
  signed URL is not user-specific), so each blob is signed at most once per
  `FILE_URL_SHARED_CACHE_TTL` window and served from cache for every subsequent
  request and user. New setting `FILE_URL_SHARED_CACHE_TTL` in
  `config/settings/base.py` (default: half the signed-URL lifetime, capped at
  6h; `0` for LOCAL storage, which keeps the prior per-request-only behavior).
  Cache failures degrade gracefully to a fresh sign.
- **Trimmed the corpus/folder document-list query overfetch.** `GET_DOCUMENTS`
  (`frontend/src/graphql/queries.ts`) selected `txtExtractFile` and
  `pawlsParseFile` signed URLs that no list consumer reads (the document-detail
  loader fetches them on open via its own query), so the corpus folder view was
  signing two extra URLs per document for nothing. Removed both fields, halving
  the cold-path signing fan-out (now `pdfFile` + `icon` only). Verified no
  `GET_DOCUMENTS` consumer reads the dropped fields.
- **Concurrent signing for document-list pages.** New
  `FileUrlPrewarmMiddleware` (`config/graphql/file_url_prewarm.py`) intercepts a
  resolved `documents` connection and signs the page's *requested* file URLs in
  a thread pool (`FILE_URL_SIGN_CONCURRENCY`, default 16), warming the request
  cache so the per-node resolvers return without serial `signBlob` round trips.
  Collapses an N-deep serial signing chain into ~N/concurrency; no-op unless
  `FILE_URL_SHARED_CACHE_TTL > 0`.
- **Bounded the corpus-folder first page.** `CorpusDocumentCards` now passes an
  explicit `limit` (`DEFAULT_LIST_PAGE_SIZE`, 20) to `GET_DOCUMENTS`; previously
  the initial query was unbounded and graphene returned up to
  `RELAY_CONNECTION_MAX_LIMIT` (100) documents, signing pdf+icon URLs for all of
  them on the first paint. Subsequent pages already loaded at the same size via
  `fetchMore`.
- **Lazy `pdfFile` on the document cards.** `pdfFile` is no longer fetched (and
  signed) for every card; `GET_DOCUMENTS` drops it and the download action
  resolves the signed URL on click via `useLazyPdfUrl` + the new
  `GET_DOCUMENT_PDF_URL` query. Backward-compatible — callers whose query still
  supplies `pdfFile` skip the lazy fetch; the download button now gates on
  `PDF_MIME_TYPE` (`frontend/src/components/documents/{ModernDocumentItem,DocumentItem}.tsx`).
