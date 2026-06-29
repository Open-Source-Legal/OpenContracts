- **Extraction: stop reading oversized documents just to discard them.**
  `doc_extract_query_task` (`opencontractserver/tasks/data_extract_tasks.py`) read the entire
  `txt_extract_file` into memory and only then checked `len(text) <= EXTRACT_FULL_TEXT_CHAR_LIMIT`.
  A pre-read byte-size guard now skips the read when `txt_extract_file.size >
  EXTRACT_FULL_TEXT_CHAR_LIMIT * MAX_UTF8_BYTES_PER_CHAR` (new constant in
  `opencontractserver/constants/extraction.py`) — the byte size above which the text cannot
  possibly fit the char budget — falling back to retrieval. In-range documents are still read and
  filtered exactly as before; a failing/absent `.size` falls through to the read defensively.
- **Extraction: remove spurious prompt-injection size warnings.** Dropped the
  `warn_if_content_large(full_text, ...)` call on the (already fenced + notice-prefixed) document
  body. Its 1000-char threshold (`UNTRUSTED_CONTENT_SIZE_WARNING_THRESHOLD`) fired on nearly every
  real document against the 24 000-char inject budget, logging a `[PromptInjection] WARNING` per
  cell; the warning is meant for short field values, not 24k-char bodies.
- **Extraction: report the request budget actually in force.** `_classify_none_result` /
  `_failure_message_for_classification` (`opencontractserver/tasks/data_extract_tasks.py`) no
  longer hardcode `EXTRACT_AGENT_REQUEST_LIMIT` when fingerprinting a `usage_limit_exceeded`
  None-result — they take the effective `request_limit` as an argument so classification and the
  operator-facing message stay correct if a caller overrides the budget via `UsageLimits`. The
  matching `UsageLimitExceeded` warning in
  `opencontractserver/llms/agents/pydantic_ai_agents.py::_structured_response_raw` now logs the
  resolved `UsageLimits.request_limit` rather than the hardcoded default. Tests:
  `opencontractserver/tests/test_data_extract_failure_classification.py`,
  `opencontractserver/tests/test_pydantic_ai_agents.py`.
