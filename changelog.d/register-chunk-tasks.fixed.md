- Register the chunked-parse Celery tasks at worker startup
  (`opencontractserver/tasks/__init__.py`). `chunk_tasks` was imported only
  inside `ingest_doc`, so worker main processes discarded
  `parse_document_chunk` messages as unregistered tasks and every PDF large
  enough to be parsed in chunks stayed `processing` until the stuck-document
  sweep failed it. `opencontractserver/tests/test_celery_task_registration.py`
  checks every task module registers in a fresh interpreter.
