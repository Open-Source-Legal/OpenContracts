import { ApolloCache } from "@apollo/client";

/**
 * Root Query fields whose cached results become stale whenever documents are
 * added to, removed from, moved within, or deleted from a corpus.
 *
 * - `documents` — the paginated document grid connection.
 * - `corpusFolders` — the folder tree, including the per-folder `documentCount`
 *   / `descendantDocumentCount` badges shown in the sidebar.
 * - `corpusDocumentIds` — the flat id list backing the grid's "Select All".
 * - `deletedDocumentsInCorpus` — the Trash view listing.
 */
const CORPUS_DOCUMENT_CACHE_FIELDS = [
  "documents",
  "corpusFolders",
  "corpusDocumentIds",
  "deletedDocumentsInCorpus",
] as const;

/**
 * Evict every corpus-scoped document/folder cache field so active queries
 * refetch with fresh data after a mutation that changes corpus membership.
 *
 * Centralises the previously copy-pasted
 * `cache.evict({ fieldName: "documents" })` + `corpusFolders` + `gc()` blocks
 * (RemoveDocumentsModal, FolderDocumentBrowser, BulkImportModal, …) into one
 * place. Crucially it also evicts `corpusFolders`, which several delete paths
 * forgot — that omission left the sidebar's folder document counts stale after
 * a delete (the bug fixed alongside this helper).
 *
 * Evicting a root Query field invalidates the active watchers observing it;
 * with the corpus views' `cache-and-network` fetch policy they immediately
 * refetch from the network, so counts and lists stay in sync.
 */
export function evictCorpusDocumentCaches(cache: ApolloCache<unknown>): void {
  for (const fieldName of CORPUS_DOCUMENT_CACHE_FIELDS) {
    // Evict by field NAME only (no args filter), which drops every cached
    // corpus/filter variant of the field rather than just the current one.
    // This is intentional: switching corpus without a remount must not serve
    // another corpus's stale list/counts, so we invalidate them all and let
    // the active watcher for the current corpus refetch.
    cache.evict({ fieldName });
  }
  cache.gc();
}
