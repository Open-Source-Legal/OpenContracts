# Celery Configuration for Worker Uploads

Worker uploads (the [Worker Uploads REST API](worker_uploads.md) and the
[Remote Ingest Worker](remote_ingest_worker.md)) are ingested **asynchronously**:
the upload endpoint only *stages* each upload (returns HTTP 202), and a Celery
task turns it into a `Document`. This page is the operations reference for the
Celery workers + queues a target instance must run.

!!! danger "The #1 silent failure"
    If no Celery worker consumes the **`worker_uploads`** queue, uploads are
    accepted (HTTP 202) but stay `PENDING` **forever** and **no documents are
    ever created** — the uploading client still sees success, so the failure is
    invisible until someone notices the corpus is empty.

## TL;DR — minimum viable config

Against the Redis broker, the target instance must run:

1. **≥1 Celery worker** consuming **all three** queues
   `celery,worker_uploads,doc_parse`
2. **Exactly one Celery Beat** scheduler

```bash
# worker — exactly what compose/production/django/celery/worker/start runs:
celery -A config.celery_app worker -l INFO -Q celery,worker_uploads,doc_parse

# beat — run ONE instance only (see High Availability below):
celery -A config.celery_app beat -l INFO
```

The stock `production.yml` / `local.yml` `celeryworker` + `celerybeat` services
already do this. This page matters when you run a **custom or self-hosted**
deployment, scale workers, or split queues.

## The three queues (there are only three)

`CELERY_TASK_ROUTES` (in `config/settings/base.py`) routes
`worker_uploads.tasks.*` to a dedicated queue and the later stages of the
per-document ingest chain (`extract_thumbnail`, `ingest_doc`,
`set_doc_lock_state`) to `doc_parse`; everything else uses the default
`celery` queue.

| Queue | Carries | Consumed by |
|---|---|---|
| `worker_uploads` | `process_pending_uploads` (creates the `Document`) + `recover_stalled_uploads` | the upload worker |
| `doc_parse` | the value-producing ingest-chain stages — **`extract_thumbnail`**, **`ingest_doc`** (parse), **`set_doc_lock_state`** (unlock + corpus actions) | the same or another worker |
| `celery` (default) | **everything else** — `convert_document_to_pdf` (the chain's cheap first stage, kept on the default queue so a conversion flood can't starve parsing), maintenance tasks, embeddings, analyses | the same or another worker |

!!! warning "Cover all three queues"
    A worker on `-Q worker_uploads` **alone** stages documents but never
    parses them. A worker missing `doc_parse` leaves every document stuck
    mid-chain — converted but never thumbnailed/parsed/unlocked — **silently**
    (the upload client already got its 202). Use
    `-Q celery,worker_uploads,doc_parse`, or run one worker per queue so all
    three are always covered.

## Beat schedule (mandatory)

Defined in `CELERY_BEAT_SCHEDULE`:

| Task | Interval | Purpose |
|---|---|---|
| `process_pending_uploads` | **60 s** | drains `PENDING` → `Document` (also nudged on each upload POST) |
| `recover_stalled_uploads` | **300 s** | resets uploads stuck in `PROCESSING` longer than `WORKER_UPLOAD_STALE_MINUTES` (15) back to `PENDING` |

Without Beat, an upload still processes (the POST nudges the drain), but **crash
recovery and the periodic safety-net drain stop** — uploads orphaned in
`PROCESSING` by a worker restart never recover.

## Scaling & High Availability

- **Horizontal scale is safe.** `process_pending_uploads` claims a batch with
  `SELECT … FOR UPDATE SKIP LOCKED`, so any number of worker processes/replicas
  drain `worker_uploads` concurrently with no double-processing.
- **For bulk ingestion** (the remote-ingest-worker case), run a **dedicated**
  worker on `-Q worker_uploads` so an upload flood doesn't starve interactive
  work on `celery`; keep your existing worker on `-Q celery,doc_parse` (or
  all three). The `doc_parse` split exists for the same starvation reason at
  the next stage: on a bulk ingest, every document's cheap
  `convert_document_to_pdf` is enqueued up front on `celery`, and giving the
  later parse/unlock stages their own consumer capacity keeps the conversion
  backlog from starving them.
- **The target's upload worker is light.** It imports pre-processed data and
  stores the embeddings the client shipped — it does **not** parse, OCR, or
  re-embed (that ran on the remote worker). Thumbnail rendering on the
  `doc_parse` queue is the heavier part of the post-upload work.
- **Beat: exactly one instance.** Two Beats schedule every periodic task twice.
  In an HA setup pin Beat to a single replica (`replicas: 1` / a leader).

## Key settings (env-overridable)

| Setting | Default | Notes |
|---|---|---|
| `WORKER_UPLOAD_BATCH_SIZE` | `50` | uploads claimed per `process_pending_uploads` run |
| `WORKER_UPLOAD_STALE_MINUTES` | `15` | `PROCESSING` → `PENDING` reset threshold |
| `MAX_WORKER_UPLOAD_SIZE_BYTES` | `256 MiB` | per-file cap (`256 * 1024 * 1024` bytes ≈ 268 MB decimal) |
| `MAX_WORKER_METADATA_SIZE_BYTES` | `500 MiB` | per-upload metadata JSON cap (binary MiB, not decimal MB) |
| `CELERY_BROKER_URL` / `REDIS_URL` | `redis://…/0` | broker = Redis |
| `CELERY_WORKER_MAX_MEMORY_PER_CHILD` | `~14 GB` | worker child recycled after this |

The four `WORKER_UPLOAD_*` / `MAX_WORKER_*` rows above are the canonical
worker-upload knobs documented in
[Worker Uploads – Configuration](worker_uploads.md#configuration); they are
repeated here only for the at-a-glance Celery setup. If a default changes, update
`config/settings/base.py` and that page — this table follows.

Reliability is set globally and needs no per-deployment change:
`CELERY_TASK_ACKS_LATE=True` + `CELERY_TASK_REJECT_ON_WORKER_LOST=True` (uploads
redeliver if a worker dies mid-task), and the Redis broker
`visibility_timeout` is 12 h — keep it longer than your slowest task or Redis
will re-deliver an in-flight task to a second worker.

## Verification (run after deploy)

```bash
# 1) A worker is consuming ALL THREE queues
#    (expect "celery", "worker_uploads", AND "doc_parse"):
celery -A config.celery_app inspect active_queues

# 2) Beat is scheduling the drains (expect process_pending_uploads / recover_stalled_uploads),
#    or just confirm the celerybeat process/container is up and logging ticks.
celery -A config.celery_app inspect scheduled

# 3) End-to-end: uploads must not pile up as PENDING.
python manage.py shell -c "from opencontractserver.worker_uploads.models import WorkerDocumentUpload as W; from collections import Counter; print(dict(Counter(W.objects.values_list('status', flat=True))))"
#    Healthy: COMPLETED grows; PENDING/PROCESSING stay near 0.
```

## Symptom → cause

| Symptom | Cause | Fix |
|---|---|---|
| `PENDING` climbs and never drains; no documents appear | No worker on the `worker_uploads` queue | Add `worker_uploads` to a worker's `-Q` |
| Documents created but stuck locked/processing forever — **no thumbnails, no parsed text** | Worker missing the `doc_parse` queue (`extract_thumbnail`/`ingest_doc`/`set_doc_lock_state` route there) | Add `doc_parse` to the worker's `-Q` (or run a `doc_parse` worker) |
| Non-PDF documents never even convert | Worker missing the default `celery` queue (`convert_document_to_pdf` routes there) | Add `celery` to the worker's `-Q` (or run a `celery` worker) |
| Rows stuck in `PROCESSING` > 15 min | Beat is down (no `recover_stalled_uploads`) | Start exactly one Celery Beat |
| Every periodic task runs twice | More than one Beat instance | Run a single Beat |
