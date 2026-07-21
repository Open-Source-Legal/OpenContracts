- **Corpus groups: silent membership data loss on edit.**
  `opencontractserver/corpuses/services/corpus_groups.py::CorpusGroupService.update_group`
  replaced membership wholesale via `group.corpora.set(submitted)`. Because
  `CorpusGroupType.corpora` is per-viewer filtered by
  `get_group_corpora_visible_to_user`, the edit form can only ever seed the
  members the caller can currently READ — so if a member became invisible to
  the editor after being added (its owner made it private), any unrelated save
  (e.g. a title-only edit) silently destroyed that membership. The editor could
  not see the member, no field exposed the true membership count (`totalCount`
  is filtered too), and the M2M row was unrecoverable. `update_group` now
  replaces only the caller-visible slice: final membership is
  `(members the caller cannot READ) ∪ (submitted, caller-readable set)`.
  Adding remains gated by `_resolve_member_corpora`, so an unreadable corpus
  still cannot be smuggled in, and removing a visible member is unchanged.
  Regression tests in `opencontractserver/tests/test_corpus_groups.py`; rule
  documented in `docs/permissioning/consolidated_permissioning_guide.md`.
