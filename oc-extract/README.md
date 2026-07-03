# oc-extract

A standalone, lightweight port of OpenContracts' structured data extraction
workflow: define a **field set** (a prompt + output schema per field), point
it at one or more **locally processed documents**, and get **typed answers
with citations** back — stored in **SQLite** for later retrieval. Runs as a
Python library or a FastAPI microservice. No accounts, no permissions, no
Postgres/Celery/Redis.

The only network call in the pipeline is the LLM request itself (any model
pydantic-ai supports, including OpenAI-compatible local servers).

## How it maps to OpenContracts

The design is a faithful distillation of the production pipeline
(`opencontractserver/tasks/data_extract_tasks.py::doc_extract_query_task`,
`extract_orchestrator_tasks.py::run_extract`,
`llms/agents/pydantic_ai_agents.py::_structured_response_raw`):

| OpenContracts | oc-extract | Notes |
|---|---|---|
| `Fieldset` / `Column` | `FieldSet` / `FieldSpec` (`schema.py`) | Same knobs: `query`, `match_text` (`\|\|\|` few-shot), `must_contain_text`, `instructions`, `output_type`, `extract_is_list` |
| `parse_model_or_primitive` | `parse_output_type` | `"str"/"int"/"float"/"bool"` or `name: type` lines → dynamic Pydantic model |
| `Extract` + Celery chord over cells | `extracts` table + `runner.run_extract` (asyncio semaphore) | One cell per document × field, concurrent, extract marked finished when all settle |
| `Datacell` (`data={"data": ...}`, `sources`, `started/completed/failed`, `stacktrace`, `llm_call_log`) | `cells` table (same shape, JSON columns) | Identical `{"data": value}` storage convention |
| pydantic-ai structured agent with `final_result` output tool, `output_retries=3`, `UsageLimits(request_limit=20)` | `engine.ExtractionEngine` | `ToolOutput(Optional[T], name="final_result")` forces a typed commit; same budgets |
| Extraction-protocol system prompt (commit-early, 2-3 searches before concluding absence, raw-value-only) | `engine._system_prompt` | Ported nearly verbatim |
| Full-text injection ≤ 24k chars (`EXTRACT_FULL_TEXT_CHAR_LIMIT`) | `build_prompt` + `FULL_TEXT_CHAR_LIMIT` | Short docs answered in one read; absence confirmed without search loops |
| Hybrid pgvector + Postgres-FTS retrieval over annotations (`similarity_search` tool) | Pure-Python BM25 over paragraph chunks (`search_document` tool) | No embedding model or vector DB needed; chunk hits are captured as citations exactly like `retrieved_annotation_ids` |
| Retrieval citations → `Datacell.sources` + post-hoc grounding (`extraction_grounding.py`) | `sources` JSON: `retrieval` entries (what the agent saw) + `grounding` entries (exact/case/normalized/fuzzy char-offset alignment) | Same two-pass citation strategy, same bounds (min length 5, max 50 strings, fuzzy caps) |
| `None`-result classification (`agent_committed_none` / `usage_limit_exceeded` / `no_final_response`) | Same constants in `constants.py` | `agent_committed_none` is stored as a *completed* cell with a null value (legitimate absence), integration failures as *failed* |
| Prompt-injection fencing (`fence_user_content`, `UNTRUSTED_CONTENT_NOTICE`) | `fencing.py` | Field guidance and document text are fenced as untrusted data |

Deliberate simplifications: no auth/permissions, no annotation labels
(`limit_to_label` has no standalone analogue), lexical BM25 instead of
embeddings, SQLite instead of Postgres, asyncio instead of Celery. One
improvement over the production path: `must_contain_text` is a **hard**
retrieval filter here (OpenContracts applies it as advisory prompt guidance
in the doc-agent path).

## Install

```bash
cd oc-extract
pip install .            # library + service
pip install '.[pdf]'     # + PDF ingestion (pypdf)
pip install '.[anthropic]'  # + Anthropic models
export OPENAI_API_KEY=sk-...          # or ANTHROPIC_API_KEY
export OC_EXTRACT_MODEL=openai:gpt-4o-mini   # optional; this is the default
```

## Microservice

```bash
oc-extract --db contracts.db serve --port 8500
```

```bash
# 1. Ingest documents (raw text, or upload pdf/txt/md files)
curl -s -X POST localhost:8500/documents -H 'Content-Type: application/json' \
  -d '{"documents": [{"title": "MSA", "text": "...contract text..."}]}'
curl -s -X POST localhost:8500/documents/upload -F 'files=@msa.pdf'

# 2. Register a field set
curl -s -X POST localhost:8500/fieldsets -H 'Content-Type: application/json' -d '{
  "name": "Key terms",
  "fields": [
    {"name": "parties", "query": "Who are the contracting parties?",
     "output_type": "str", "extract_is_list": true},
    {"name": "monthly_fee", "query": "What is the monthly fee in USD?",
     "output_type": "float"},
    {"name": "governing_law", "query": "Which law governs this agreement?",
     "instructions": "Answer with the jurisdiction name only."}
  ]}'

# 3. Run an extract (fieldset x documents), processed in the background
curl -s -X POST localhost:8500/extracts -H 'Content-Type: application/json' \
  -d '{"name": "MSA review", "fieldset_id": 1, "document_ids": [1]}'

# 4. Poll status, then read results
curl -s localhost:8500/extracts/1              # status + cell counts
curl -s localhost:8500/extracts/1/table        # rows=documents, cols=fields
curl -s localhost:8500/extracts/1/cells        # full cells with citations
curl -s 'localhost:8500/cells/1?include_llm_log=true'  # per-cell LLM audit log
```

Every completed cell carries `sources`: `retrieval` entries (the chunks the
agent's search surfaced, with char offsets and page numbers for PDFs) and
`grounding` entries (where each extracted string was located in the document,
with the alignment method and score).

## Library

```python
from oc_extract import ExtractionEngine, FieldSet, FieldSpec, Store
from oc_extract.documents import load_path
from oc_extract.runner import run_extract_sync

store = Store("contracts.db")
doc = load_path("msa.pdf")
doc_id = store.add_document(doc.title, doc.text, page_offsets=doc.page_offsets)

fs_id = store.create_fieldset(FieldSet(
    name="Key terms",
    fields=[
        FieldSpec(name="parties", query="Who are the contracting parties?",
                  extract_is_list=True),
        FieldSpec(name="term", query="Extract the contract term.",
                  output_type="length: str\nstart_date: str"),  # dynamic model
    ],
))

extract_id = store.create_extract("MSA review", fs_id, [doc_id])
result = run_extract_sync(store, extract_id)
for row in store.extract_table(extract_id):
    print(row["document_title"], row["values"])
```

Or from the CLI, fully scripted:

```bash
oc-extract --db contracts.db add-docs msa.pdf nda.txt
oc-extract --db contracts.db add-fieldset examples/key_terms.json
oc-extract --db contracts.db run --fieldset 1 --documents all --name "review"
oc-extract --db contracts.db show 1 --cells
```

## Field spec reference

| Key | Meaning |
|---|---|
| `name` | Field/column name (key in the results table) |
| `query` | Natural-language question to answer from the document |
| `match_text` | Alternate prompt seed; `\|\|\|`-separated values become few-shot examples |
| `must_contain_text` | Hard retrieval filter + advisory guidance: only sections containing this text |
| `instructions` | Extra guidance folded into the prompt (fenced, treated as data) |
| `output_type` | `str`, `int`, `float`, `bool`, or newline-separated `field: type` lines (compiled to a Pydantic model; `list[str]`-style element types allowed) |
| `extract_is_list` | Wrap the output type in a list |

Every field is implicitly nullable: the agent may commit to "not present"
(`failure_mode="agent_committed_none"`, stored as a completed cell with a
null value) rather than inventing an answer.

## Testing

The suite runs fully offline — the engine is exercised with pydantic-ai's
`FunctionModel` and the service with a stub engine:

```bash
pip install '.[test]'
pytest
```
