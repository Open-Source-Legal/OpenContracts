- **Extraction: inject full text for short documents.** For documents whose extracted text
  is ≤ `EXTRACT_FULL_TEXT_CHAR_LIMIT` (24 K chars ≈ ~6 K tokens,
  `opencontractserver/constants/extraction.py`), `doc_extract_query_task` now appends the full
  document text to the prompt — read via the canonical `read_field_file_text`, prefixed with
  `UNTRUSTED_CONTENT_NOTICE`, and wrapped in `fence_user_content` — so the agent can answer,
  and confirm the **absence** of a clause, in a single read instead of issuing many low-signal
  `similarity_search` calls (retrieval cannot prove absence). When the full text is in context
  the prompt also relaxes the system prompt's mandatory multi-search negative-case rule. In
  the diligence eval this cut per-cell tool calls from **~16 to ~1** and eliminated the
  `tool_loop_no_output` / `no_final_response` failures that short contracts otherwise
  triggered. Larger documents fall back to retrieval (where the request budget backstops any
  looping).
