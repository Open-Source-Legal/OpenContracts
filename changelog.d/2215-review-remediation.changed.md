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
