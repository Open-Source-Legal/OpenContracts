- Added `WorkspaceService`
  (`opencontractserver/corpuses/services/workspace.py`) for filing generated
  artifacts into a user's personal `My Documents` corpus. It binds the three
  primitives that already existed — `Corpus.get_or_create_personal_corpus`,
  `CorpusFolder`, and `documents/versioning.py::import_document` — and is
  deliberately narrow: save only, since the workspace is an ordinary corpus and
  the corpus/folder/lifecycle services already own move, delete and list. Saves
  are idempotent by path, so re-saving versions the file in place rather than
  duplicating it. Generated titles are treated as untrusted input: separators
  are stripped so a title cannot invent a folder level, and dot runs are
  collapsed so a traversal segment cannot reach a corpus V2 export ZIP. See
  `docs/architecture/user-workspace-storage.md`.
- Completed deep-research reports are now filed in their creator's workspace as
  `Research Reports/<slug>.md`, with a provenance header (source corpus,
  generated date, report link) so the file explains itself outside the app. The
  saved document is linked from `ResearchReport.workspace_document` and exposed
  on the GraphQL type as `workspaceDocument`. The save runs outside
  `finalize`'s atomic block and swallows its errors — the report is already
  COMPLETED and cost minutes of model time, so a failed file write must not
  turn a successful run into a failed one. Markdown documents skip the ingest
  chain (no parsing, thumbnailing or annotations), but the `DocumentPath`
  signal still queues a document-level text embedding, so a saved report has no
  annotation-level chunks for passage retrieval yet can surface in
  document-level similarity search — and each save costs one embedding call.
- Fixed the corpus document list hiding markdown documents. `documents(
  inCorpusWithId:)` excludes `text/markdown` unless a caller passes
  `includeCaml: true` (a default aimed at extractors and analyzers), and
  `GET_CORPUS_DOCUMENTS_FOR_TOC` / `DocumentTableOfContents.tsx` did not — so a
  report filed in `My Documents` existed in the database while the list a user
  opens to find it rendered "No Documents". `RunCorpusActionModal` deliberately
  still omits the flag, since a corpus action should not offer to run over a
  CAML article.
