- **Extraction: restore dropped `Column` constraint fields.** `Column.instructions`,
  `must_contain_text`, and `limit_to_label` are GraphQL-settable, persisted, cloned, and
  diffed, but the marvin→doc-agent rewrite (commit `184903f62`) stopped feeding them to the
  extraction LLM — so per-column guidance/scoping had zero effect. `doc_extract_query_task`
  (`opencontractserver/tasks/data_extract_tasks.py`) now folds all three back into the prompt
  the agent runs, and the dead `get_column_extraction_params` helper (zero callers) was
  removed. Regression test: `opencontractserver/tests/test_extract_prompt_wiring.py`.
