- **Extraction: inject full text for short documents.** For documents whose extracted text
  is ≤ `EXTRACT_FULL_TEXT_CHAR_LIMIT` (50 K chars, `opencontractserver/constants/extraction.py`),
  `doc_extract_query_task` now appends the full (fenced via `fence_user_content`) document
  text to the prompt so the agent can answer — and, critically, confirm the **absence** of a
  clause — in a single read instead of issuing many low-signal `similarity_search` calls
  (retrieval can't prove absence). In the diligence eval this cut per-cell tool calls from
  **~16 to ~1** and eliminated the `tool_loop_no_output` / `no_final_response` failures that
  short contracts otherwise triggered. Retrieval tools remain the primary path for longer
  documents above the budget.
