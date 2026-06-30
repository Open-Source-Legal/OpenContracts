- **Extraction: fence the per-column constraint fields against prompt injection.**
  `Column.instructions`, `must_contain_text`, and `limit_to_label` are user-settable via the
  `CreateColumn` / `UpdateColumn` GraphQL mutations (only `@login_required`) and were
  concatenated raw into the extraction prompt — a prompt-injection vector. `doc_extract_query_task`
  (`opencontractserver/tasks/data_extract_tasks.py`) now wraps each value with
  `fence_user_content` (which also escapes any attempt to break out of the `<user_content>`
  fence) under `UNTRUSTED_CONTENT_NOTICE`, so the values stay readable to the model as guidance
  while injected directives/role-reassignments are neutralized. The notice is emitted exactly
  once even when both column constraints and the full document text are fenced. Regression tests:
  `opencontractserver/tests/test_extract_prompt_wiring.py` (fencing, fence-breakout escaping,
  single-notice).
