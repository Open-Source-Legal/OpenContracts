- **Discover search is now hybrid (text + semantic) across every category, plus a new Documents category.**
  The Discover view (`frontend/src/views/DiscoverSearchResults.tsx`) previously
  reused the `*ForMention` autocomplete resolvers and `conversations`/`corpuses`
  list fields, which were substring/FTS-only and searched a narrow field set.
  New dedicated, relevance-ranked resolvers in
  `config/graphql/discover_queries.py` (`DiscoverSearchQueryMixin`, registered
  in `config/graphql/queries.py`) back each category with a **hybrid** search
  that fuses a text arm (substring + PostgreSQL full-text) with a semantic arm
  (pgvector cosine similarity over existing embeddings) via Reciprocal Rank
  Fusion:
  - `discoverAnnotations` — substring + FTS + vector.
  - `discoverDocuments` — **new Discover category** (title/description + doc
    embedding); surfaced as a new "Documents" tab in the UI.
  - `discoverNotes` — now uses FTS (see `Note.search_vector` below) + vector,
    not just `LIKE`.
  - `discoverCorpuses` — matches collection title/description **and**
    collections whose contained documents/annotations match the query.
  - `discoverDiscussions` — now searches thread **message bodies**, not just the
    thread title, plus vector; scoped to THREADs (CHATs excluded).
  Each resolver permission-filters through `BaseService.filter_visible` before
  either arm runs; the semantic arm degrades gracefully to text-only when no
  embedder is configured or content is not yet embedded. Backend tests:
  `opencontractserver/tests/test_discover_search_graphql.py`. Frontend queries:
  `DISCOVER_ANNOTATIONS` / `DISCOVER_DOCUMENTS` / `DISCOVER_NOTES` /
  `DISCOVER_CORPUSES` / `DISCOVER_DISCUSSIONS` in `frontend/src/graphql/queries.ts`;
  component test updated in `frontend/tests/DiscoverSearchResults.ct.tsx`.
- **`Note.search_vector` full-text column (migration `annotations/0076`).**
  Adds a trigger-maintained `tsvector` (built from `title` + `content`) and a
  GIN index to `Note`, mirroring `Annotation.search_vector` (migration 0063).
  This gives note search stemming + ranking and an index instead of the prior
  unindexed `LIKE '%…%'` sequential scan. Model change in
  `opencontractserver/annotations/models.py`. `NoteType`
  (`config/graphql/annotation_types.py`) excludes the new `search_vector` field —
  graphene-django cannot convert a `SearchVectorField` and would otherwise raise
  at schema-import time.
