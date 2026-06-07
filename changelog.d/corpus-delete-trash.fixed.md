- **Corpus "Select All" now selects every matching document, not just the
  loaded page.** The folder/corpus document grid is virtualized, so "Select All"
  used to read `currentViewDocumentIds` — only the documents the paginated query
  had loaded — meaning a follow-up "Remove from corpus" silently left the
  unloaded documents behind. `handleSelectAll`
  (`frontend/src/components/corpuses/folders/FolderDocumentBrowser.tsx`) now
  fetches the complete id set for the current filters via a new lightweight
  `corpusDocumentIds` query (`config/graphql/document_queries.py`,
  descendant-aware folder scoping reusing `DocumentFilter`) and the toolbar's
  "X of N" count uses the connection's real `totalCount` instead of the loaded
  page length.
- **Sidebar folder document counts now refresh after every delete.** Several
  corpus delete/move/import paths evicted the `documents` connection but forgot
  `corpusFolders`, leaving the folder-tree badges (`documentCount` /
  `descendantDocumentCount` in `FolderTreeSidebar`) stale until reload. A shared
  `evictCorpusDocumentCaches` helper (`frontend/src/graphql/cacheEvictions.ts`)
  now evicts `documents`, `corpusFolders`, `corpusDocumentIds`, and
  `deletedDocumentsInCorpus` together, and is wired into the per-card remove
  (`CorpusDocumentCards`), bulk remove (`RemoveDocumentsModal`), folder delete
  (`DeleteFolderModal`), move-to-folder (`FolderDocumentBrowser`), and bulk
  import (`BulkImportModal`) paths.
