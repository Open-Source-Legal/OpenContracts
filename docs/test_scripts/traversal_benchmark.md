# Test: Agentic traversal benchmark (heavy-RAG vs RAG + traversal)

## Purpose
Measure, on real corpus questions, what the graph-navigation tools add over
plain semantic retrieval — the "measure your own best work honestly" discipline
from the Qodo *contracts-as-codebase* work. Produces a side-by-side report of
tokens, tool-call counts, latency and authority-grounding for two configs:

- **A — heavy RAG**: `similarity_search` only (today's default entry point).
- **B — RAG + traversal**: `similarity_search` + `get_document_references`,
  `read_reference_target`, `find_documents_citing`, `get_reference_neighborhood`.

## Prerequisites
- A populated corpus, ideally one that has had reference enrichment applied
  (`apply_corpus_reference_enrichment`) and an authority corpus bootstrapped
  (`bootstrap_authority_corpus`), so the reference graph has edges to walk.
- A Django user with READ on that corpus.
- A configured LLM provider (this harness makes real LLM calls; it is NOT part
  of the 30-minute suite).
- Edit `opencontractserver/benchmarks/fixtures/traversal_questions.yaml` with
  real `corpus_id`s and (optionally) gold `expected_keys` (e.g. `dgcl:145`).

## Steps
1. Confirm the corpus has resolved references to traverse:
   ```bash
   docker compose -f local.yml run --rm django python manage.py shell -c "
   from opencontractserver.annotations.models import CorpusReference
   print(CorpusReference.objects.filter(corpus_id=1).count(), 'references')
   "
   ```
2. Run the benchmark:
   ```bash
   docker compose -f local.yml run --rm django python manage.py benchmark_traversal \
     --questions opencontractserver/benchmarks/fixtures/traversal_questions.yaml \
     --user admin \
     --run-dir /tmp/traversal_run
   ```

## Expected Results
- A markdown table printed to stdout (and `report.md` / `report.json` written to
  `--run-dir`) with one aggregate row per config and one row per question.
- Config **B** should call the traversal tools (`tool calls` > config A's) and,
  on questions whose answer turns on a cited statute, show a higher
  `grounding` hit rate (the expected canonical keys appear in the answer /
  sources).
- If config B shows no traversal tool calls, the corpus likely has no resolved
  references yet — apply enrichment first.

## Cleanup
None — the harness is read-only against the corpus (it only runs agents; it
creates conversation/message rows like any chat, which can be deleted if
undesired). Delete the `--run-dir` output when finished.
