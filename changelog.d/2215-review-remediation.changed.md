- `installAuthorityPack` now carries `@graphql_ratelimit(RateLimits.ADMIN_OPERATION)`
  like comparable admin writes (`config/graphql/authority_pack_api.py`). It was
  already gated to authority admins; the limit is defence in depth on an
  operation that installs corpora and rewrites the governance graph. No schema
  change — the decorated resolver sits behind the strawberry-facing one, the
  same split `config/graphql/annotation_queries.py` uses.
- The publisher-source duplicate-member check rescanned `ZipFile.infolist()`
  once per tagged document (`opencontractserver/tasks/import_tasks_v2.py`),
  i.e. O(entries × tagged documents) over attacker-supplied input. The member
  census is now computed once per open ZIP and memoised on it. (`NameToInfo`
  cannot serve this — it keeps only the last entry for a repeated name, and
  spotting a repeat is the point of the check.)
- The 1 MB blob-hashing chunk size is now `BLOB_HASH_CHUNK_BYTES` in
  `opencontractserver/constants/document_processing.py` rather than a literal
  at each of its two call sites (`import_tasks_v2.py`, `validate_export.py`).
- New tests, no behaviour change: a DB-credentialed `build_agent_model` now has
  an end-to-end assertion that a Responses-only model really is constructed as
  `OpenAIResponsesModel` (and an ordinary model is not) — the existing coverage
  mocked `_construct_model` or asserted only the env-credential string
  redirect, so nothing reached the branch that picks the class, and the class
  IS the endpoint. Anchoring of `requires_responses_api` is pinned directly.
  The publisher-source duplicate-member rejection (`occurrences > 1`) is now
  tested alongside the existing missing-member case, so both sides of the guard
  the memoised census serves are covered.
