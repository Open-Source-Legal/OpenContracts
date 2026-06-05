- **Discover search: dedupe the per-query embedding across the five category resolvers (PR #1908 follow-up, issue #1919).**
  The Discover "All" tab fires all five category resolvers
  (`config/graphql/discover_queries.py`) as five independent HTTP requests
  (Apollo uses a non-batching link), each of which previously embedded the
  *same* query string with the same default embedder — up to 5× the embedding
  latency/cost for one user search. A new per-process LRU
  (`_cached_query_vector`, sized by
  `DISCOVER_QUERY_VECTOR_CACHE_SIZE` in `opencontractserver/constants/search.py`)
  memoises the deterministic `(query_text, embedder_path)` embedding so those
  requests share one embedding call. The semantic arm stays best-effort: a
  transient embedder failure is never cached as a wrong result and the text arm
  always returns on its own.
- **Clarity/DRY cleanups in `discover_queries.py`.** `_order_by_ids` now *owns*
  the `id__in=ids` predicate; the five resolvers no longer pre-filter the
  visible queryset (removing a redundant double `id__in` clause that only
  PostgreSQL's optimiser was collapsing). The five identical deferred
  `get_default_embedder_path` imports inside the resolver bodies are
  consolidated into a single module-level `_default_embedder_path()` helper.
  Added inline docs for the `discoverCorpuses` content-match `IN (...)` size
  bound and for the `5 × READ_LIGHT` per-search rate cost of the "All" tab
  (`DISCOVER_DEFAULT_LIMIT` comment).
- **New backend test coverage** in
  `opencontractserver/tests/test_discover_search_graphql.py`: the `limit`
  parameter is now exercised end-to-end (`limit=1` clamps the fused result set),
  and `discoverCorpuses` is asserted not to surface a collection whose content
  matches the query but which the user cannot read.
