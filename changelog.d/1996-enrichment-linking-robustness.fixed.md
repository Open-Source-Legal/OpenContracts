- **Enrichment linking/provenance robustness — three pre-existing bugs in
  `opencontractserver/enrichment/services/enrichment_service.py` (issue #1996).**
  - **Analysis stranded `COMPLETED` when linking failed.** `apply()` stamped the
    provenance `Analysis` `COMPLETED` and saved it *before* calling
    `_link_external()` (which issues two `bulk_update`s over potentially
    thousands of rows). A failure there propagated to the caller while the
    `Analysis` row stayed permanently `COMPLETED` with `law_references_linked=0`.
    Fix: `_link_external()` now runs inside `apply()`'s `try` (after
    `writer.write`, before the `COMPLETED` stamp), so a linking failure marks the
    `Analysis` `FAILED` and re-raises (`enrichment_service.py:444-458`).
  - **Nondeterministic / non-navigable `target_corpus_id` for multi-corpus
    authority documents.** `_link_external()` built `path_corpus_cache` with
    `dict(DocumentPath…values_list("document_id","corpus_id"))`, which silently
    kept whatever row Postgres returned last when an authority document had
    current paths in more than one corpus — yielding a nondeterministic
    `target_corpus_id` and a mention `link_url` that 404s for the other corpus.
    Fix: the target corpus is now chosen deterministically *and* navigably —
    prefer a corpus the citing corpus's audience can actually open, breaking ties
    on the lowest `corpus_id` (one query for paths + one for the visible-corpus
    set; no per-target N+1) (`enrichment_service.py:620-655`).
  - **`refs` queryset iterated twice while lazy.** The `CorpusReference`
    queryset was walked once to build the target cache and again to
    promote/demote; rows inserted between the two evaluations by a concurrent
    `apply()` on the same corpus appeared in pass 2 but not the cache and were
    silently skipped. Fix: materialize it once with `list(...)` before the first
    loop (`enrichment_service.py:604-613`).
  - Regression coverage added in
    `opencontractserver/tests/test_enrichment_linking.py`
    (`test_apply_marks_analysis_failed_when_linking_raises`,
    `test_link_target_corpus_is_deterministic_for_multi_corpus_authority`,
    `test_link_target_corpus_prefers_audience_visible_corpus`).
