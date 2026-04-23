# Benchmarking OpenContracts against LegalBench-RAG

OpenContracts ships a benchmark harness under
[`opencontractserver/benchmarks/`](../../opencontractserver/benchmarks/) that
turns an external RAG dataset into a live corpus, runs the production extract
pipeline against it with a configurable model, and reports standard retrieval
and answer metrics.  The first supported benchmark is **LegalBench-RAG**
(Pipitone & Alami, 2024 — [arXiv:2408.10343](https://arxiv.org/abs/2408.10343),
[zeroentropy-ai/legalbenchrag](https://github.com/zeroentropy-ai/legalbenchrag)).

## What you get

LegalBench-RAG is a **retrieval** benchmark — the paper scores character-
span recall/precision, not LLM answer text.  The harness follows that
convention: the headline number is `citation_span_overlaps_gold`, which
measures whether the annotations the extraction agent actually linked to
`Datacell.sources` overlap the gold passages.

| Axis | Metric | Where it comes from |
| --- | --- | --- |
| Retrieval (headline) | `citation_span_overlaps_gold`, `citation_text_contains_gold_span`, `citation_coverage_rate` | Annotations the agent linked into `Datacell.sources` via the `similarity_search` tool |
| Retrieval (probe) | `probe_recall_at_k`, `probe_precision_at_k`, `probe_char_iou` | A standalone single-shot top-k `CoreAnnotationVectorStore.search` — useful as an isolated retrieval-algorithm A/B, but NOT what the agent actually used |
| Answer quality (auxiliary) | `answer_token_f1` (SQuAD), `answer_token_recall`, `answer_contains_verbatim_span` | `Datacell.data` from `doc_extract_query_task` |

Answer F1 is reported for completeness but is not the primary signal.
SQuAD-style token F1 is hostile to the LLM's natural paraphrased output
style even when the agent has cited the correct passage — measure it to
track regressions, but read `citation_span_overlaps_gold` first.

### Recommended smoke-test size

Full privacy_qa is 194 tasks; CUAD is ~4,000; MAUD ~1,700; ContractNLI
~1,000.  A 30-task slice (`--limit 30`) over a subset gives a mean
within ~0.03 of the full-run number on the citation metrics and is
roughly 1 / 6 the API cost.  Use the full run only when a measured
change on the smoke is close to the noise floor.

## Directory layout

LegalBench-RAG ships as:

    <root>/
      corpus/<subset>/<file>.txt         # raw text documents
      benchmarks/<subset>.json           # test cases (query + gold snippets)

Each `benchmarks/<subset>.json` deserializes to:

    {
      "tests": [
        {
          "query": "...",
          "snippets": [
            {"file_path": "cuad/NDA_001.txt", "span": [1234, 1456]}
          ],
          "tags": []
        }
      ]
    }

The four official subsets are `contractnli`, `cuad`, `maud`, and
`privacy_qa`.  The harness autodetects whichever subsets are present on
disk so you can run against the full set or a slice.

## Running the benchmark

Download the LegalBench-RAG data from the upstream repository (it is not
vendored into this repo).  Then:

```bash
docker compose -f local.yml run --rm django python manage.py run_benchmark \
    --benchmark legalbench-rag \
    --path /data/legalbench-rag \
    --user admin \
    --model openai:gpt-4o-mini \
    --top-k 10 \
    --run-dir /tmp/lbrag_run
```

Useful flags:

- `--subsets cuad privacy_qa` — restrict to one or more subsets
- `--limit 50` — cap total tasks for a smoke-test run
- `--model anthropic:claude-opus-4-6` — sweep a different LLM
- `--run-label experiment-1` — stitched into the default run directory name
- `--corpus-title "LBR CUAD v1"` — override the auto-generated corpus title

Everything the command writes lives under the run directory:

```
<run_dir>/
  config.json         # adapter configuration + timestamps
  gold.json           # per-datacell gold answers and spans
  report.json         # per-task metrics + aggregate scores
  report.csv          # flat tabular version for diffing
```

## Programmatic API

```python
from opencontractserver.benchmarks.adapters.legalbench_rag import LegalBenchRAGAdapter
from opencontractserver.benchmarks.runner import run_benchmark

adapter = LegalBenchRAGAdapter(
    root="/data/legalbench-rag",
    subsets=["cuad"],
    limit=100,
)
report = run_benchmark(
    adapter=adapter,
    user=my_django_user,
    model="openai:gpt-4o-mini",
    top_k=10,
)

print(report.aggregates)
for result in report.task_results[:5]:
    print(result.task_id, result.answer_token_f1, result.retrieval_recall_at_k)
```

Import from the submodules directly (the package ``__init__`` does not
re-export symbols to avoid ``AppRegistryNotReady`` at startup).

## Adding a new benchmark

Implement a subclass of `BaseBenchmarkAdapter`
(`opencontractserver/benchmarks/adapters/base.py`) and register it in
`opencontractserver/benchmarks/management/commands/run_benchmark.py`'s
`BENCHMARK_REGISTRY`.  The adapter only has to yield `BenchmarkDocument` and
`BenchmarkTask` objects — everything downstream (corpus creation, extraction,
retrieval, metrics, reporting) is shared.

## Model override

The runner passes `model_override=<your-model>` into
`doc_extract_query_task`, which is a small, backward-compatible addition to
the production task.  When no override is supplied the task still uses the
existing `openai:gpt-4o-mini` default — nothing about ordinary extract runs
changes.

## Caveats

- Benchmark documents are ingested through the standard `TxtParser`
  pipeline, which creates sentence-level structural annotations as our
  retrieval units.  Character offsets are preserved verbatim because we
  upload the raw benchmark text unchanged.
- Retrieval metrics depend on the corpus embedder.  A new corpus is
  created per run so you can A/B embedders by running the benchmark twice
  with different embedder configurations.
- The harness forces celery eager mode for ingestion and extraction so
  results are available synchronously.  The runner restores the previous
  celery config when it returns.
