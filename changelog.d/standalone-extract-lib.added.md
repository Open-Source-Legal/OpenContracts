- **`oc-extract/` — standalone structured data extraction library + microservice.**
  A lightweight, SQLite-backed port of the extract pipeline
  (`opencontractserver/tasks/data_extract_tasks.py::doc_extract_query_task` +
  `extract_orchestrator_tasks.py::run_extract`) with no accounts, permissions,
  Postgres, Celery, or embedding dependencies. Ingest documents locally
  (PDF via pypdf, plain text/markdown), register a fieldset
  (`FieldSpec` mirrors `Column`: `query`, `match_text` few-shot via `|||`,
  `must_contain_text`, `instructions`, `output_type` primitives or
  `name: type` dynamic models, `extract_is_list`), run an extract over
  document × field cells (asyncio replaces the Celery chord), and read typed
  results with citations back over HTTP (FastAPI) or the Python API.
  Citations combine retrieval hits (BM25 `search_document` tool captures
  chunk ids, the standalone analogue of `retrieved_annotation_ids`) with
  post-hoc grounding (exact → case-insensitive → whitespace-normalized →
  bounded fuzzy alignment ported from `utils/extraction_grounding.py`).
  Mirrors production semantics: `final_result` ToolOutput commit,
  `UsageLimits(request_limit=20)`, `output_retries=3`, 24k-char full-text
  injection, prompt fencing (`fence_user_content`), and `NONE_RESULT_*`
  failure-mode classification. 39 offline tests (FunctionModel/stub engine).
