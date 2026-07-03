# Test: oc-extract microservice end-to-end smoke test

## Purpose

Verifies the standalone `oc-extract/` service end-to-end without an LLM API
key: boot the real FastAPI service, ingest documents over HTTP (JSON +
multipart), register a fieldset, run an extract through the library with a
scripted offline model, and read the persisted results (typed value +
retrieval citation) back through the running HTTP service from the same
SQLite file.

## Prerequisites

- `pip install -e './oc-extract[test,pdf]'` in a virtualenv
- No API keys needed (the extract run uses a pydantic-ai `FunctionModel`)

## Steps

1. Boot the service against a scratch DB:
   ```bash
   oc-extract --db smoke.db serve --port 8531 &
   sleep 3
   curl -s localhost:8531/health
   ```
2. Ingest a document via JSON and a file via multipart:
   ```bash
   curl -s -X POST localhost:8531/documents -H 'Content-Type: application/json' \
     -d '{"documents":[{"title":"MSA","text":"This Master Services Agreement is between ACME Corporation and Widgets Incorporated. The monthly fee is $12,500. Governed by the laws of Delaware."}]}'
   printf 'hello plain text upload' > note.txt
   curl -s -X POST localhost:8531/documents/upload -F 'files=@note.txt'
   ```
3. Register a fieldset and create (but don't run) an extract:
   ```bash
   curl -s -X POST localhost:8531/fieldsets -H 'Content-Type: application/json' \
     -d '{"name":"Key terms","fields":[{"name":"fee","query":"What is the monthly fee?","output_type":"float"}]}'
   curl -s -X POST localhost:8531/extracts -H 'Content-Type: application/json' \
     -d '{"name":"r1","fieldset_id":1,"document_ids":[1],"run":false}'
   ```
4. Run the extract offline through the library against the same DB
   (WAL mode allows the concurrent reader), with a scripted model that
   first searches and then commits `12500.0`:
   ```bash
   python - <<'EOF'
   from pydantic_ai.messages import ModelResponse, ToolCallPart
   from pydantic_ai.models.function import FunctionModel
   from oc_extract import ExtractionEngine, Store
   from oc_extract.runner import run_extract_sync

   state = {"n": 0}
   def fn(messages, info):
       state["n"] += 1
       if state["n"] == 1:
           return ModelResponse(parts=[ToolCallPart(
               tool_name="search_document", args={"query": "monthly fee"})])
       return ModelResponse(parts=[ToolCallPart(
           tool_name=info.output_tools[0].name, args={"response": 12500.0})])

   store = Store("smoke.db")
   result = run_extract_sync(store, 1, engine=ExtractionEngine(model=FunctionModel(fn)))
   print(result["finished"], result["cell_counts"])
   EOF
   ```
5. Read the persisted results back through the running service:
   ```bash
   curl -s localhost:8531/extracts/1/table
   curl -s localhost:8531/extracts/1/cells
   ```

## Expected Results

- Step 1: `{"status":"ok",...}`
- Step 2: two document ids; re-posting identical text returns the same id
- Step 4: prints a finished timestamp and `{'total': 1, 'completed': 1, 'failed': 0}`
- Step 5: the table row shows `fee = 12500.0` with `source_count >= 1`; the
  cell's `sources` contains a `retrieval` entry whose snippet includes the
  fee sentence

## Cleanup

```bash
kill %1
rm -f smoke.db smoke.db-wal smoke.db-shm note.txt
```
