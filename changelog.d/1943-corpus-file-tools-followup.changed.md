- **Corpus file-tool review polish (PR #1940 follow-up, issue #1943 items 3–5).**
  - **`require_user` helper (`opencontractserver/llms/tools/core_tools/_helpers.py`).**
    The 5-line "no user injected / id not found → `PermissionError`" guard that
    `rename_document` and `delete_document` each repeated is now a single
    `require_user(user_id, caller)` helper (companion to the existing
    `get_user_or_none`), preserving the same per-caller error messages.
    Read-only tools keep using `get_user_or_none` (which tolerates anonymous
    access) (item 4).
  - **`delete_document` tool description (`opencontractserver/llms/tools/tool_registry.py`).**
    The description now spells out that deletion needs the corpus DELETE tier —
    *higher* than the write permission `rename_document`/`move_document` use —
    and instructs the LLM to report a `permission denied` failure rather than
    retry-loop on it. A WRITE-but-not-DELETE user still passes the coarse
    framework `requires_write_permission` gate and is correctly rejected by
    `DocumentLifecycleService.soft_delete_document`; tightening this to a
    dedicated `requires_delete_permission` flag (so the tool is filtered out
    before such a user ever sees it) remains a tracked follow-up (item 3).
  - **Direct unit test for `sanitize_corpus_filename`**
    (`opencontractserver/tests/test_shared_utils.py`). The canonical
    corpus-filename sanitiser was only exercised indirectly through the rename
    integration paths; it now has a focused test covering empty/None →
    fallback, all-special-chars → underscores, path-separator collapse (no
    directory traversal), no run-collapsing, leading-dot preservation, and
    truncation at `MAX_FILENAME_LENGTH` (item 5).
  - **Not changed (item 2):** `CorpusDocumentService._check_document_in_corpus`
    was kept private. It was deliberately renamed from public to underscore-
    prefixed in PR #1685 to signal its "NO PERMISSION CHECK" contract; its
    cross-service callers all live inside `corpuses.services` and gate corpus
    READ upstream, so the leading underscore (service-internal use) is correct.
