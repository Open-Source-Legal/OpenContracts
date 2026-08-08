- Added a per-message **Save to My Documents** control on finished assistant
  chat messages, backed by the `saveMessageToWorkspace` GraphQL mutation. A
  chat answer previously left no durable artifact — unlike a research report it
  is not stored anywhere, so once the thread scrolled away the analysis was
  only recoverable by re-reading the conversation. The message is filed into
  the caller's private `My Documents` corpus as a markdown document, with an
  optional folder (created on demand) and an optional title that defaults to
  the message's first meaningful line. A provenance header records the source
  corpus, conversation and date. Saving the same title again versions the file
  in place rather than duplicating it.
- The mutation is **visibility-gated**, matching the discussion-permissions
  model in `docs/permissioning/consolidated_permissioning_guide.md`: anyone who
  can READ the conversation may keep a copy (strictly weaker than editing,
  which stays creator-or-moderator), the lookup goes through
  `BaseService.filter_visible` so an invisible message is indistinguishable
  from a nonexistent one, and the copy always lands in the **saver's** own
  corpus — the message author never gains access to it. Pinned by tests for
  the reader-can-save, stranger-cannot, and copy-lands-in-the-savers-workspace
  cases.
- Fixed corpus document counts reading zero for a workspace holding generated
  artifacts. `Corpus.document_count()` and the annotated subquery in
  `config/graphql/corpus_queries.py::_corpus_count_subqueries` both excluded
  **all** `text/markdown`, which was equivalent while a corpus's only markdown
  was its CAML landing article — but a personal workspace holding saved chat
  answers or research reports then reported "0 documents" while listing files.
  Both now exclude only the CAML article, via a single shared predicate
  (`CAML_ARTICLE_DOCUMENT_PATH_Q`) so the list and detail views cannot drift
  apart. The Collection Intelligence panel had the same defect from the other
  direction — `GET_CORPUS_COLLECTION_DOCS` omitted `includeCaml`, so its
  headline metric read "0 DOCUMENTS" and "No documents in this collection yet"
  — and now passes the flag like the other corpus views.
