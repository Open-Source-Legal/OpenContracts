# Performance Tuning — Document Ingestion

This document captures what we've measured and changed about the OpenContracts
ingestion pipeline, what's left, and the operator-facing knobs available for
tuning a deployment. It exists because "ingestion is slow" is the most common
production complaint and the codebase has accumulated several layered
optimisations that interact in non-obvious ways.

## Where time goes during ingestion

Measured against the **LegalBench-RAG `cuad` subset** (29 documents,
~2,200 paragraph annotations) under two embedder configs. Baseline numbers
are paper-faithful retrieval-only benchmark runs; the harness uses the
production `corpus.import_content` → parser → `import_annotations` chain,
so timings are representative of what a production worker will see when
ingesting the same volume of work.

### Run history

| Variant | Embedder | Total wall-clock | Ingest only | Notes |
|---|---|---:|---:|---|
| Pre-batch baseline | OpenAI 3-large | 53m 5s | 50m 26s | One celery task per annotation; one HTTP round-trip per task |
| `bulk_create` + batch task w/ `embedder_path` | OpenAI 3-large | 11m 11s | 7m 59s | Single batch task per doc, sub-batches of 50 |
| `+ api_batch_size=256, parallel sub-batches=4, max_retries=8, transient re-raise` | OpenAI 3-large | 10m 47s | 7m 25s | Halves HTTP-call count for typical paragraph docs |
| `+ Session pooling, urllib3 retry, parallel sub-batches=2` | Microservice (MiniLM) | 9m 24s | 7m 59s | Matches gunicorn worker count; connection reuse |

### Phase split (microservice run, 9m 24s total)

```
parser + import_annotations + permissions + structural set + file save  ~6:30  (~80%)
embedder HTTP calls                                                       ~1:30  (~18%)
retrieval probe + report write                                            ~1:24  (~14%)
```

**The embedding endpoint is no longer the bottleneck** for either
provider once batched + concurrent. The remaining 80% is per-doc
fixed overhead in the Django ORM layer.

## What we've changed (and why)

All changes are at module scope — no PipelineSettings, no per-corpus
config, no migrations. Operators get the tuned defaults automatically.

### Embedder-level changes

#### `BaseEmbedder` gained two tunables

```python
class BaseEmbedder(...):
    api_batch_size: int = 50                # Default fallback, override per subclass
    embed_max_concurrent_sub_batches: int = 1  # Serial by default
```

Per-embedder overrides:

| Embedder | `api_batch_size` | `embed_max_concurrent_sub_batches` | Rationale |
|---|---:|---:|---|
| `OpenAIEmbedder` | 256 | 4 | OpenAI accepts 2048 inputs / ~8M tokens per call; ~96K tokens at 256×typical paragraph fits comfortably. 4 in-flight sub-batches stay inside Tier-1 RPM (3000/min). |
| `MicroserviceEmbedder` | 100 (= service cap) | 2 | Gunicorn `--workers 2` in the reference deployment; matching saturates without queueing. |

`calculate_embeddings_for_annotation_batch` now reads
`embedder.api_batch_size` (with `EMBEDDING_API_BATCH_SIZE` as a fallback
for embedders without an override) when carving sub-batches, and uses a
`ThreadPoolExecutor(max_workers=embed_max_concurrent_sub_batches)` for
the HTTP work. **DB writes (`add_embedding`) stay in the calling thread**
to dodge Django's per-thread connection bookkeeping.

#### OpenAI client hardening

```python
openai.OpenAI(
    api_key=...,
    base_url=...,
    max_retries=8,  # Was: SDK default of 2
)
```

The OpenAI SDK retries 429/5xx with exponential backoff and honours the
`Retry-After` header on 429. Raising `max_retries` from 2 → 8 covers
~minute-long rate-limit windows without the celery layer ever needing to
see the failure. After the SDK budget exhausts, our code now **re-raises**
`RateLimitError` / `APITimeoutError` / `APIConnectionError` so celery's
`autoretry_for=(Exception,)` decorator fires (with its 60s countdown).
The previous `return None` swallowed the failure silently.

`AuthenticationError` and `BadRequestError` still return `None` — those
are permanent (wrong key / malformed input), retrying burns budget.

#### Microservice client hardening

```python
# sent_transformer_microservice.py
session = requests.Session()
session.mount("http://", HTTPAdapter(
    max_retries=Retry(
        total=3, backoff_factor=1.0,
        status_forcelist=(429, 502, 503, 504),
        allowed_methods={"POST"},     # urllib3 default is GET-only
        raise_on_status=False,        # Let our code see the final status
    ),
    pool_connections=16, pool_maxsize=16,
))
```

A process-wide singleton session gives us:

1. **Connection pooling.** Every `requests.post` used to open a fresh TCP
   handshake. Multiplied by thousands of sub-batches, that's measurable
   overhead, and on Cloud Run it's *significant* (TLS too).
2. **urllib3-level retry on transients.** Tighter loop than celery's
   60s-countdown autoretry. A 502 blip lasting <1s gets absorbed by
   urllib3 in the same request; the embedder code never sees it.
3. **Pool size headroom.** Sized for the highest embedder concurrency
   (currently 4 for OpenAI) plus slop. No "Connection pool is full"
   warnings under concurrent ingest.

4xx (other than 429) is deliberately *not* in `status_forcelist`. Those
are permanent failures that should surface as `EmbeddingClientError`
immediately, not waste retry budget.

### Annotation-creation changes

#### `import_annotations` uses `bulk_create` + dispatched batch task

```python
# Old: per-row .create() fires post_save → per-annotation embedding task
for ann_data in annotations_data:
    Annotation.objects.create(...)  # → signal → 1 HTTP round-trip per ann

# New: collect, bulk_create (skips signals), dispatch ONE batch task
instances = [Annotation(...) for ann_data in annotations_data]
Annotation.objects.bulk_create(instances)
# Plus: explicit dispatch with embedder_path so the batch path engages
calculate_embeddings_for_annotation_batch.delay(
    annotation_ids=[a.pk for a in instances],
    corpus_id=corpus_id,
    embedder_path=get_default_embedder_path(),  # Critical
)
```

The `embedder_path=` kwarg is load-bearing.
`calculate_embeddings_for_annotation_batch` only takes the
`embed_texts_batch` fast path **when an explicit path is supplied**;
without one it falls through to per-annotation
`_apply_dual_embedding_strategy` — i.e. the slow path we were trying to
remove. We learned this the hard way after the first speedup commit
silently regressed to the per-annotation HTTP loop.

Dual embedding (default + corpus-preferred when different) is mirrored
at dispatch time: one batch task per embedder path, sub-batched by
`EMBEDDING_BATCH_SIZE` to match the production
`corpus_tasks.ensure_embeddings_for_corpus` pattern.

## Operator-facing knobs

### Constants you might tune at deployment scope

| Constant | Default | When to raise | When to lower |
|---|---:|---|---|
| `EMBEDDING_BATCH_SIZE` | 100 | Big-doc corpora (>256 annotations/doc); unlocks parallel sub-batch path | Memory-pressured workers |
| `EMBEDDING_API_BATCH_SIZE` (fallback) | 50 | Embedders without an explicit override | — |
| `MICROSERVICE_EMBEDDER_MAX_BATCH_SIZE` | 100 | Set in tandem with the service-side `MAX_TEXTS_PER_BATCH` env var; raising one without the other 400s | — |
| `OpenAIEmbedder.api_batch_size` | 256 | Tier 4+ (10M+ TPM); could go to 512 | Tight rate limits; halve to 128 |
| `OpenAIEmbedder.embed_max_concurrent_sub_batches` | 4 | Tier 4+ (10K+ RPM); 8 is safe | Tier 1 if seeing 429s in steady state |
| `OpenAIEmbedder.OPENAI_CLIENT_MAX_RETRIES` | 8 | Hostile rate-limit environments | Fail-fast deployments |
| `MicroserviceEmbedder.embed_max_concurrent_sub_batches` | 2 | Match `gunicorn --workers N` | Single-worker deployments |

### Service-side env vars (microservice deployment)

| Env var | Default | Notes |
|---|---:|---|
| `MAX_TEXTS_PER_BATCH` | 100 | Server-side cap; set together with `MICROSERVICE_EMBEDDER_MAX_BATCH_SIZE` |
| Gunicorn `--workers` | 2 | Each worker is single-threaded; bump for higher concurrency throughput |
| `MAX_BATCH_SIZE` (internal `encode()` chunk) | 8 | Internal sentence-transformer batching; affects per-call latency |

### Celery worker concurrency (deployment)

The `--concurrency` flag on celery workers is a major lever for
multi-document throughput. Default deployments often sit at 4, but a
sentence-transformer microservice with 2 workers can comfortably feed
8+ celery worker concurrency for ingestion (each celery worker fires
one batched embedding HTTP call per doc; workers fan out across the
gunicorn fleet).

```bash
# Example: bump celery-worker concurrency for ingest-heavy deployments
celery -A config.celery_app worker --concurrency=8 -Q ingest
```

## What's still slow (open work)

The 80% per-doc overhead breaks down roughly as:

| Suspected cost | Per-doc estimate | Status |
|---|---:|---|
| Per-annotation `set_permissions_for_obj_to_user` | ~5-15s | **Likely dead work** — `AnnotationQuerySet.visible_to_user` doesn't consult `AnnotationUserObjectPermission` |
| Label create/lookup (`load_or_create_labels`) | ~50-100ms | Cached after first doc; small |
| Doc-level embedding (single HTTP call) | ~100-500ms | Could piggyback on annotation batch task |
| Thumbnail generation | ~150ms | Separate celery task; non-blocking on batch |
| Badge auto-check | ~50ms × N tasks | Could move to corpus-level |
| File saves (`txt_extract_file`) | ~50ms | Disk-bound; minimal upside |

**Top suspect: per-annotation permission writes are dead work.**
`AnnotationQuerySet.visible_to_user` doesn't query `AnnotationUserObjectPermission`
— annotation visibility derives from document + corpus + structural +
creator + analysis/extract privacy. The per-annotation `assign_perm` /
`remove_perm` calls in `import_annotations` populate guardian rows that
are never read. Removing them is potentially the single biggest
production-side win remaining (~5-15s/doc on annotation-heavy ingests),
behaviour-preserving, and orthogonal to the embedder work above.

Dual-tracking via `docs/permissioning/consolidated_permissioning_guide.md`
which explicitly states "Annotations & Relationships: NO individual
permissions - inherited from document + corpus."

## Lessons learned

These are non-obvious things that bit us during the speedup work.
Capturing them so future maintainers don't re-discover.

### `bulk_create` skips post_save signals

Django's `Manager.bulk_create()` does NOT fire `pre_save` / `post_save`
signals by default. This was the *load-bearing* property that let us
collapse N per-annotation embedding tasks into one batch dispatch. Any
new signal handler attached to `Annotation.post_save` for ingest-time
work needs to be reflected explicitly in `import_annotations` (e.g.
the badges-tick handler, if it ever needs to apply per-annotation).

### `calculate_embeddings_for_annotation_batch` requires `embedder_path`

The task body has two branches: an `embedder_path`-supplied fast path
that uses `embed_texts_batch`, and a fallback path that loops
per-annotation through `_apply_dual_embedding_strategy`. Dispatching
without `embedder_path=` looks correct from the call site but silently
takes the slow branch. Always pass it.

### Default `urllib3.Retry` is GET-only

`urllib3.util.retry.Retry()` defaults to retrying only safe HTTP methods.
Embedding endpoints are POST. You must set
`allowed_methods=frozenset(["POST"])` (or a superset) or no retries fire.
The default behaviour was masked in our case because the celery
autoretry layer compensates — we just ate the 60s countdown unnecessarily.

### Django connections are per-thread

When fanning HTTP work across a `ThreadPoolExecutor`, each thread gets
its own Django DB connection lazily. Doing ORM writes from worker
threads is correct but requires explicit `connections.close_all()` at
thread exit, otherwise idle connections accumulate against
`max_connections`. We sidestepped this by keeping DB writes in the
calling thread and giving worker threads only the HTTP work.

### `max_retries` on `openai.OpenAI()` honours `Retry-After`

The Anthropic and OpenAI SDKs both honour the server's `Retry-After`
header on 429 responses out of the box. Raising the SDK-level
`max_retries` is the correct lever for handling rate-limit blips, *not*
adding a custom retry loop in the embedder. Re-raising RateLimitError
*after* the SDK budget exhausts lets celery take over with its own
backoff for the genuinely-long rate-limit windows.

### `force_celery_eager()` serializes docs in the benchmark

The benchmark loader uses `force_celery_eager()` so every doc's celery
chain runs synchronously in the calling thread before the next doc
starts. **Production doesn't have this property** — each doc upload is
its own celery task and they fan out across worker concurrency. Don't
optimise the benchmark loader's serial loop and quote the resulting
speedup as a production-side gain; the production gain is whatever
celery worker concurrency already gave you.

### Module-level `requests.Session` pays for itself

For any client that fires many small POSTs to the same host (embedding,
reranking, parsing microservices), a process-wide `requests.Session`
with a sized `HTTPAdapter` cuts handshake overhead measurably. The
pattern in `sent_transformer_microservice._get_session()` is a
ready-to-copy template — pair it with a `urllib3.Retry` config and
you've got connection reuse + transient-failure absorption for free.

## How to validate a tuning change locally

1. Wipe the DB:
   ```bash
   docker compose -f local.yml run --rm django python manage.py shell -c "
     from opencontractserver.documents.models import Document, DocumentPath
     from opencontractserver.annotations.models import Annotation, StructuralAnnotationSet
     from opencontractserver.corpuses.models import Corpus
     from opencontractserver.extracts.models import Extract, Fieldset, Datacell, Column
     for m in [Datacell, Extract, Column, Fieldset, Annotation, DocumentPath,
               Document, StructuralAnnotationSet, Corpus]:
         m.objects.all().delete()
   "
   ```

2. Stage a pipeline config (see `docs/benchmarks/legalbench_rag_results.md`
   for Config A/B/C templates).

3. Run the cuad subset of LegalBench-RAG retrieval-only:
   ```bash
   docker compose -f local.yml run --rm \
     -v /path/to/legalbenchrag_data:/data/legalbenchrag:ro \
     -v /tmp/runs:/data/runs \
     django python manage.py run_benchmark \
       --benchmark legalbench-rag --path /data/legalbenchrag \
       --user admin --top-k 32 --retrieval-only --corpus-wide \
       --subsets cuad --run-dir /data/runs/cuad_$(date +%s)
   ```

4. Read `Ingesting N documents` and `Creating N columns` log timestamps to
   isolate the ingest phase from retrieval/eval. The wall-clock
   between those two log lines is the ingestion bottleneck under test.

5. Compare against the run-history table above. Speedups should
   reproduce within ~10% on the same hardware.

## Cross-references

- LegalBench-RAG benchmark methodology and results:
  [`docs/benchmarks/legalbench_rag_results.md`](../benchmarks/legalbench_rag_results.md)
- Permission system (why annotation-level permissions are dead work):
  [`docs/permissioning/consolidated_permissioning_guide.md`](../permissioning/consolidated_permissioning_guide.md)
- Pipeline component architecture:
  [`docs/pipelines/pipeline_overview.md`](../pipelines/pipeline_overview.md)
