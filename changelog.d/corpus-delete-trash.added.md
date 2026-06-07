- **"Empty Corpus" action — move every document to Trash and remove all folders
  in one step.** Addresses "no easy way to empty everything". New
  `emptyCorpus(corpusId)` mutation (`config/graphql/document_mutations.py`)
  delegates to `DocumentLifecycleService.empty_corpus`
  (`opencontractserver/corpuses/services/lifecycle.py`), which soft-deletes all
  active documents (recoverable from the trash until it is emptied) and deletes
  the folder tree; it requires corpus DELETE permission. Surfaced as a guarded,
  confirmation-modal "Empty Corpus" toolbar action (`EmptyCorpusModal`,
  `FolderToolbar`), shown only to users with delete permission
  (`canDeleteCorpusAtom`).
- **New `corpusDocumentIds` GraphQL query** returns the global IDs of every
  document matching a corpus/folder/search filter, ignoring pagination. It backs
  the document grid's "Select All" so bulk actions cover the full result set, and
  reuses `DocumentFilter` so its scoping matches the paginated `documents`
  connection exactly (including descendant-aware folder filtering).
