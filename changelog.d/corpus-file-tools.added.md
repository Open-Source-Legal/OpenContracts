- **Agent tools for managing documents as files in a corpus: search, rename, delete (move already existed).**
  Rounds out the corpus file-management toolset in
  `opencontractserver/llms/tools/core_tools/documents.py` so an LLM agent can
  treat a corpus like a filesystem. All three route through the canonical
  corpus service layer and mirror the human surfaces' permissioning:
  - `search_corpus_documents` — **read-only** discovery. Case-insensitive match
    against each document's title AND its corpus path; returns
    `document_id`/`title`/`path`/`folder`/`file_type`/`is_deleted`. Filters by
    `MIN(document_permission, corpus_permission)` via
    `CorpusDocumentService.get_corpus_documents_visible_to_user`, so a private
    document never leaks through a merely-readable corpus. Supports `folder_id`,
    `include_deleted`, and a capped `limit` (default 25, max 200 —
    `CORPUS_FILE_SEARCH_DEFAULT_LIMIT`/`_MAX_LIMIT` in
    `opencontractserver/constants/tools.py`).
  - `rename_document` — **write + approval gated**. Changes only the filename
    (last path segment); the document stays in its folder (use `move_document`
    to change folders). Names are sanitised — characters other than
    letters/digits/`-_.` (including slashes) collapse to `_`, so a rename can
    never traverse directories — and the current extension is preserved when the
    new name omits one (`report.pdf` → `Q3_Summary.pdf`). Backed by a new
    `FolderDocumentService.rename_document` (requires corpus UPDATE) that reuses
    the same TOCTOU-safe successor-path machinery as moves
    (`CorpusPathService._create_successor_path_with_retry`).
  - `delete_document` — **write + approval gated**. Soft-deletes to the
    restorable corpus trash via `DocumentLifecycleService.soft_delete_document`
    (requires corpus DELETE); nothing is permanently erased.
  Registered in `opencontractserver/llms/tools/tool_registry.py` (CORPUS
  category, `requires_corpus=True`; write tools additionally
  `requires_write_permission`/`requires_approval`) and re-exported from
  `opencontractserver/llms/tools/core_tools/__init__.py`. On a corpus agent the
  LLM picks the `document_id`; on a document agent it is pinned to the current
  document (standard `build_inject_params_for_context` injection).
- **`sanitize_corpus_filename` helper (`opencontractserver/shared/utils.py`).**
  Extracts the corpus-filename sanitisation that was duplicated inline in
  `Corpus.add_document` and the text-document import tool into one canonical
  function; `_derive_path_from_title`
  (`opencontractserver/llms/tools/core_tools/text_document_import.py`) and the
  new `rename_document` service now share it. Also hoisted the listing-tool
  `limit` clamp into a shared `clamp_limit`
  (`opencontractserver/llms/tools/core_tools/_helpers.py`), reused by the
  extract/analyzer discovery tools.
- **Tests:** `opencontractserver/tests/test_corpus_file_tools.py` covers search
  (title/path match, folder filter, trash inclusion, limit cap, IDOR, and the
  MIN document-visibility rule), rename (extension preservation, sanitisation,
  no-op, conflict disambiguation, permission/IDOR failures), delete
  (soft-delete to trash, permission/IDOR failures), and async-wrapper smoke
  coverage.
