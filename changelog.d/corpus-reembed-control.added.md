- Surfaced corpus re-embedding in the UI. `updateCorpus` refuses to change
  `preferredEmbedder` once a corpus holds documents (issue #437) and directs the
  caller to the `reEmbedCorpus` mutation — which had no frontend control, so the
  error named an API the UI never exposed and the only way out of the dialog was
  to restore the original embedder. `CorpusModal` now shows an inline migration
  prompt when the embedder selection changes on an existing corpus, with a
  **Re-embed corpus** action that calls `reEmbedCorpus` and reports its result
  (`frontend/src/components/corpuses/CorpusModal.tsx`,
  `frontend/src/graphql/mutations.ts::RE_EMBED_CORPUS`). Covered by
  `frontend/tests/CorpusModalReEmbed.ct.tsx`.
