- **Batched the per-document soft-delete loops behind `emptyCorpus` and folder
  cascade-delete into one shared bulk-trash primitive (#1951).** Added
  `DocumentLifecycleService.bulk_soft_delete_documents(corpus, document_ids,
  user)` in `opencontractserver/corpuses/services/lifecycle.py` — the batched
  counterpart of `Corpus.remove_document(document=...)`. It supersedes every
  active head path in one `UPDATE`, inserts the immutable soft-delete history
  nodes in one `bulk_create`, replays `post_save(created=True)` per new row via
  the existing `CorpusPathService._dispatch_document_path_created_signals`
  helper (so the document-text embedding + `Readme.CAML` cache-refresh
  side-effects fire exactly as before), and revokes `is_public` on now-orphaned
  documents in a single query pair. `DocumentLifecycleService.empty_corpus`
  (`lifecycle.py:~407`) and `FolderCRUDService._trash_documents_in_subtree`
  (`opencontractserver/corpuses/services/folders.py:~927`) now route through it,
  retiring both `TODO(perf, deferred)` per-document `remove_document` loops.
  The query count is now independent of the document count (a fixed handful of
  statements instead of several per document), removing the
  statement/connection-timeout risk those loops carried on multi-thousand-
  document corpora when run inside the single request transaction
  (`ATOMIC_REQUESTS=True`). Trash listing and restorability are unchanged: the
  history nodes are identical to those `remove_document` produced. The legacy
  "empty trash" path (`permanently_delete_all_in_trash`) is intentionally left
  out of scope — it is a *permanent* delete that destroys history nodes and
  keeps deliberate per-document partial-success semantics, so it cannot share a
  soft-delete primitive whose contract is "history nodes + signals preserved".
