# Recording and replaying LLM cassettes for the extract E2E spec

The E2E Playwright spec at `frontend/tests/e2e/extract-pdf-workflow.spec.ts` drives the full extract pipeline including a real LLM call. To keep CI fast, deterministic, and free of LLM-API spend, the call can be wrapped in a [VCR.py](https://vcrpy.readthedocs.io/) cassette so the recorded HTTP interaction is replayed instead of hitting the provider.

## How it works

`opencontractserver/utils/vcr_replay.py` exposes a `maybe_vcr_cassette()` context manager that is wrapped around the agent invocation in `opencontractserver/tasks/data_extract_tasks.py::doc_extract_query_task`. When the relevant env vars are unset, the manager is a no-op — production behavior is unchanged.

When the env vars are set:
- `OC_LLM_VCR_MODE=record` — every LLM HTTP call is captured to the cassette file (overwriting any existing one).
- `OC_LLM_VCR_MODE=once` — record if missing, replay if present.
- `OC_LLM_VCR_MODE=replay` — replay only; an unmatched request raises `CannotOverwriteExistingCassetteException` and bubbles up as an extraction failure.

The cassette path is supplied via `OC_LLM_VCR_CASSETTE` (filesystem path, must be visible inside the celery worker container).

A custom matcher strips volatile fields from request bodies so a cassette recorded against one DB (with timestamp `1777504812606` and document PK `56`, etc.) replays cleanly against another (with different IDs and timestamps). The patterns are in `_VOLATILE_PATTERNS` at the top of `vcr_replay.py` — extend them as new volatile values surface.

## Recording a fresh cassette

1. Bring up the local stack with the VCR env vars set so the worker container picks them up:

   ```bash
   OC_LLM_VCR_MODE=record \
   OC_LLM_VCR_CASSETTE=/app/opencontractserver/tests/fixtures/cassettes/e2e_extract_pdf_workflow/extract.yaml \
   docker compose -f local.yml up -d --no-deps --force-recreate celeryworker
   ```

2. Run the E2E spec end-to-end against a real OpenAI key:

   ```bash
   cd frontend
   E2E_RUN_LLM_TESTS=true E2E_TEST_PASSWORD="<your superuser password>" \
     yarn test:e2e --grep "Extract PDF workflow" --reporter=list
   ```

3. Verify the cassette landed under `opencontractserver/tests/fixtures/cassettes/e2e_extract_pdf_workflow/extract.yaml`. Commit it.

## Replaying

1. Bring up the worker in replay mode (no real key required — VCR intercepts every request to the LLM provider):

   ```bash
   OC_LLM_VCR_MODE=replay \
   OC_LLM_VCR_CASSETTE=/app/opencontractserver/tests/fixtures/cassettes/e2e_extract_pdf_workflow/extract.yaml \
   docker compose -f local.yml up -d --no-deps --force-recreate celeryworker
   ```

2. Run the spec normally. Total time drops from ~1.6 min to roughly the same — the bulk of the runtime is parser ingest + Playwright wall-clock, not the LLM call.

To prove no real LLM call happens, replace `OPENAI_API_KEY` in `.envs/.local/.django` with a deliberately-fake string before re-running. The spec still passes.

## Debugging matcher failures

Set `OC_LLM_VCR_DEBUG=1` (also forwarded through `local.yml` to the worker). On every body-mismatch the matcher writes a JSON line with the first byte of difference + 200 chars of context to `/tmp/vcr-mismatch-<pid>.log` inside the container. Tail it to see exactly what's volatile and isn't being normalized:

```bash
docker exec celeryworker bash -c 'tail -1 /tmp/vcr-mismatch-*.log | python3 -m json.tool'
```

Add new patterns to `_VOLATILE_PATTERNS` until the matcher succeeds.

## Limitations / follow-ups

- **LlamaParse is not yet covered.** PDF ingest still calls `https://api.cloud.llamaindex.ai`. To run the spec in CI without any external network, `_LLM_HOSTS` in `vcr_replay.py` needs to grow to include the LlamaParse host AND the wrapper needs to be applied around `ingest_doc` too. That's a separate PR.
- **Cassette goes stale on prompt changes.** Any change to the structured-extraction system prompt, the column query, or the tool schemas will produce a new request body and require re-recording.
- **One cassette per spec.** The current cassette is named `e2e_extract_pdf_workflow/extract.yaml`. If you add a second LLM-using spec, give it its own cassette directory.

## Why VCR rather than `pydantic_ai.models.test.TestModel`

A `TestModel` would be cheaper (no HTTP at all) but it would not exercise the openai-SDK + httpx + pydantic-ai integration path. PR #1399's `failure_mode=no_final_response` classifier specifically targets that integration path — bypassing it with a pure-Python test double would mask the very class of bugs the spec exists to catch.
