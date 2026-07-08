- `find_documents_citing` (`opencontractserver/llms/tools/core_tools/graph_navigation.py`)
  now derives each citing document's `corpus_id` from the bounded ranked
  aggregate (`Min("corpus")`) instead of the separate, capped citing-clause
  sample scan. Previously a top-`mention_count`-ranked document whose numeric
  `document_id` sorted past the `NAV_CITING_SAMPLE_SCAN` budget got a null
  `corpus_id` next to real `mention_count`/`document_title` data — a
  data-integrity gap. `mention_count` and `corpus_id` are now both exact DB
  aggregates unaffected by the snippet-scan budget.
- `get_document_references` error envelopes now report the normalized
  `direction` ("both" for an unrecognized value) rather than the raw
  LLM-supplied string, so error and happy-path envelopes stay shaped alike.
