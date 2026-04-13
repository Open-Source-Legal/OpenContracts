# Benchmarking OpenContracts against LegalBench-RAG

OpenContracts ships a benchmark harness under
[`opencontractserver/benchmarks/`](../../opencontractserver/benchmarks/) that
turns an external RAG dataset into a live corpus, runs the production extract
pipeline against it with a configurable model, and reports standard retrieval
and answer metrics.  The first supported benchmark is **LegalBench-RAG**
(Pipitone & Alami, 2024 — [arXiv:2408.10343](https://arxiv.org/abs/2408.10343),
[zeroentropy-ai/legalbenchrag](https://github.com/zeroentropy-ai/legalbenchrag)).

## What you get

For every benchmark query the harness captures two independent signals:

| Axis | What it measures | Where it comes from |
| --- | --- | --- |
| Answer quality | SQuAD-style normalized exact match and token F1 | `Datacell.data` from the existing `doc_extract_query_task` |
| Retrieval quality | Character-span recall@k, precision@k, and IoU over gold spans | A direct probe of `CoreAnnotationVectorStore` (independent of the extract path) |

Answer and retrieval are reported separately so you can diagnose which half
of the pipeline is underperforming on a given task.

## Directory layout

LegalBench-RAG ships as::

    <root>/
      corpus/<subset>/<file>.txt         # raw text documents
      benchmarks/<subset>.json           # test cases (query + gold snippets)

Each `benchmarks/<subset>.json` deserializes to::

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
from opencontractserver.benchmarks import (
    LegalBenchRAGAdapter,
    run_benchmark,
)

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

Every object in the harness is importable from the package root, so the
same flow works from notebooks and ad-hoc scripts.

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
