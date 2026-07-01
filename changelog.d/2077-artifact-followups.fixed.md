- **Avoid an N+1 SELECT on artifact creation.** `ArtifactService.create` now refetches the new
  artifact with `select_related("corpus", "creator")` before returning, so the `CreateArtifact`
  mutation's `_artifact_to_type` serializer (which reads `a.corpus.slug`) no longer issues an extra
  query per create.
- **`ingest_corpus --wait` no longer stalls to timeout on a failed or deleted document.**
  `_wait_for_processing` (`opencontractserver/corpuses/management/commands/ingest_corpus.py`)
  waited for `free == len(doc_ids)`; a failed doc never clears its backend lock and a deleted doc
  leaves the queryset, so either burned the full `--timeout`. It now treats a document as settled
  once it is lock-free, failed, or missing, and reports the failed/missing counts when it continues.
  Test: `test_wait_for_processing_settles_on_failed_and_missing_docs`.
- **`ArtifactService.update_captions` no longer triggers an N+1 (or `SynchronousOnlyOperation`).**
  It now refetches with `select_related("corpus", "creator")` before returning, mirroring `create`,
  so the `UpdateArtifact` serializer's `a.corpus.slug` / `a.creator.slug` reads don't issue extra
  queries.
- **`SetArtifactImage` rejects non-PNG uploads.** The mutation now verifies the decoded bytes begin
  with the PNG magic number before persisting them as `<slug>.png` at a public media URL, closing a
  hole that accepted arbitrary binary (SVG-with-script, polyglots, executables).
- **`reference-web` artifact template is no longer offered until its renderer exists.** It was listed
  in the backend registry but had no frontend poster, so users could mint an artifact `/a/<slug>`
  could never render. Removed from `ARTIFACT_TEMPLATES` (and its unused `_reference_count` /
  `_MIN_REFERENCES` eligibility plumbing) until the poster ships.
- **`CorpusDataStoryService.build` is request-memoized.** The corpus home fetches `corpusDataStory`
  and `corpusArtifactTemplates` in one request and both resolve through the (expensive) datacell
  aggregation; it now runs once per `(corpus, user)` per request instead of twice.
- **Artifact poster PNG export handles non-ASCII captions.** `ArtifactPosterRoute` replaced the
  legacy `unescape(encodeURIComponent(...))` idiom (removed from the WHATWG spec; breaks on accented
  names / currency symbols) with explicit `TextEncoder` UTF-8 encoding.
