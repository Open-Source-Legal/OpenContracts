- `config/graphql/core/relay.py` / `config/graphql/corpus_types.py`: fixed a
  CI-caught regression where `annotation.corpus` (and every other FK/relay-FK
  field pointing at `CorpusType` — `corpus.parent`, `corpus.memoryDocument`,
  `Analysis.analyzedCorpus`, etc.) lost its per-request cache, so each access
  re-fired the recursive `WITH __rank_table` CTE that `Corpus`'s
  `with_tree_fields=True` `TreeNode` registration emits
  (`opencontractserver/tests/test_doc_annotations_prefetch_n_plus_one.py::test_corpus_tree_cte_does_not_scale_with_document_count`
  failed 8 CTEs for 4 docs vs. the ≤4 ceiling for 1 doc).
  - Root cause: `resolve_visible_fk` (FK traversal) and `get_node_from_global_id`
    (the singular `corpus(id:)` / relay `node(id:)` lookup) both read the same
    `TypeRegistryEntry.get_node` slot. `CorpusType` deliberately registers no
    `get_node` there, because caching it would leak a stale `Corpus` object
    across `corpus(id:)` calls that reuse one request context while
    permissions change mid-test (`opencontractserver/tests/permissioning/test_permissioning.py`
    drives several `corpus(id:)` queries through one shared `graphene_client`
    while provisioning/deprovisioning perms between them). That correctly
    fixed the top-level query, but silently starved the unrelated FK-traversal
    call site of caching too.
  - Fix: added a second, independent hook — `TypeRegistryEntry.get_node_for_fk`
    / `register_type(..., get_node_for_fk=...)` — consulted only by
    `resolve_visible_fk`, never by `get_node_from_global_id`. `CorpusType` now
    registers its existing cached `_get_node_CorpusType` there, restoring the
    per-request `_corpus_node_cache` for FK access while leaving the top-level
    `corpus(id:)` query exactly as uncached as before. No schema/SDL change
    (resolver-internal); verified against the full guard suite
    (`test_doc_annotations_prefetch_n_plus_one`, `test_mentions`,
    `test_singular_node_idor`, `test_fk_visibility_traversal`,
    `test_schema_parity`, `permissioning/test_permissioning`) — 51 passed.
