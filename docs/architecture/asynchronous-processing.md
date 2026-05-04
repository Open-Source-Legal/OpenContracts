# Asynchronous Processing in OpenContracts

OpenContracts uses Celery for distributed task processing and Django signals for event-driven architecture. This document covers both systems and how they interact.

## Celery Task Queue

OpenContracts makes extensive use of Celery, a powerful Python framework for distributed and asynchronous processing. The docker compose stack includes dedicated celeryworkers to handle computationally-intensive and long-running tasks.

### Common Task Types

| Task Category | Examples |
|---------------|----------|
| Document Processing | Parsing PDFs, extracting text, generating thumbnails |
| Embeddings | Creating vector embeddings for semantic search |
| Analysis | Running analyzers on documents |
| Extraction | Executing fieldset-based data extraction |
| Agent Actions | Running AI agents on documents |
| Export/Import | Creating and importing corpus exports |

### Delivery semantics & task idempotency (Issue #1493)

OpenContracts configures Celery for **at-least-once** delivery via two global
settings (`config/settings/base.py`):

```python
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
```

The broker only removes a message after the task returns successfully, and
hard-kills (SIGKILL, OOM, host loss, deploy eviction) cause the broker to
requeue the message rather than silently treat it as done. Without these,
long-running ingest/parse/embed tasks could die mid-flight and leave documents
stuck with `backend_lock=True` and no parsed content.

> **All Celery tasks in this project MUST be idempotent.**
> Running the same task twice on the same input must not corrupt state,
> double-count, or produce duplicate side effects.

When you write a new task, follow these patterns:

| Concern | Pattern |
|---------|---------|
| Creating DB rows | `Model.objects.get_or_create(...)` or `update_or_create` keyed on a deterministic field |
| External webhooks / non-idempotent APIs | Pass an idempotency key derived from the task arguments, or guard with a "did we already do this?" check |
| Counters / accumulators | Use SQL `UPDATE ... SET x = <absolute value>` rather than `x = x + 1`, or use a deduplication key |
| Multi-step state transitions | Re-check the entry-state at the top of the task; bail early if already in the target state (this is how `ingest_doc` and `set_doc_lock_state` already behave) |
| Truly non-idempotent work that cannot be guarded | Opt out per-task: `@shared_task(acks_late=False, reject_on_worker_lost=False)`. Document why in a comment. |

If you cannot make a task idempotent, prefer the per-task opt-out over reverting
the global default — the global default protects the long-running document
processing pipeline that motivated the change.

#### Redis visibility timeout

OpenContracts uses Redis as the Celery broker. Redis tracks unacknowledged
messages with a *visibility timeout*: once a worker pulls a message, the broker
considers it eligible for redelivery to a different worker after the timeout
elapses, regardless of whether the original worker is still alive. With
`task_acks_late=True`, a task that runs longer than the visibility timeout will
be redelivered while still executing — a guaranteed double execution even
without any worker crash.

To prevent this, `CELERY_BROKER_TRANSPORT_OPTIONS = {"visibility_timeout": 12 * 60 * 60}`
sets the timeout to 12 hours, longer than any expected document-processing
task in this codebase. If you add a task that legitimately runs longer than
12 hours, split it into smaller chunks rather than raising the timeout
further — a long timeout directly delays redelivery after a real worker
death.

Reference:
[Redis broker visibility timeout](https://docs.celeryq.dev/en/stable/getting-started/backends-and-brokers/redis.html#visibility-timeout).

#### Known non-idempotent tasks

The shift to at-least-once delivery exposes pre-existing tasks that create
rows unconditionally. Until they are made idempotent, a worker death mid-task
on these paths can produce duplicate database rows on retry:

| Task | File / line | Risk |
|------|-------------|------|
| `process_corpus_action` (extract path) | `corpus_tasks.py` ~L251 | Duplicate `Datacell` rows |
| `process_thread_corpus_action` | `corpus_tasks.py` ~L589 | Duplicate `CorpusActionExecution` |
| `process_message_corpus_action` | `corpus_tasks.py` ~L681 | Duplicate `CorpusActionExecution` |
| `generate_agent_response` | `agent_tasks.py` ~L148 | Duplicate `ChatMessage` |
| Bulk import paths | `import_tasks.py` (raw `.create()` calls) | Duplicate imported objects |

In practice, real worker deaths during these tasks are rare and the duplicate
rows are recoverable. Hardening these paths (typically by switching to
`get_or_create` keyed on a deterministic field, or by claiming a
pre-allocated row at task start) is tracked separately. Treat any new task
as idempotent-by-construction; do not extend this list.

### Queue Management

If your Celery queue gets clogged due to unexpected issues or high volume, you can purge it:

```bash
docker compose -f local.yml run django celery -A config.celery_app purge
```

**Warning**: Purging the queue can cause issues:
- Documents may lack PAWLs token layers (not annotatable)
- Corpus actions may not trigger
- In such cases, delete and re-upload affected documents

## Django Signals

OpenContracts uses Django signals for event-driven processing. Key signals include:

### Document Processing Signals

**Location**: `opencontractserver/documents/signals.py`

#### `post_save` on Document (Creation)

When a document is created, triggers the processing pipeline:

```python
@receiver(post_save, sender=Document)
def process_doc_on_create_atomic(sender, instance, created, **kwargs):
    if created:
        # Chain: thumbnail → parse → unlock
        transaction.on_commit(lambda: chain(
            extract_thumbnail.si(doc_id=instance.id),
            ingest_doc.si(user_id=instance.creator_id, doc_id=instance.id),
            set_doc_lock_state.si(locked=False, doc_id=instance.id),
        ).apply_async())
```

#### `document_processing_complete` (Custom Signal)

Fired when document processing finishes (from `set_doc_lock_state`):

```python
# Definition
document_processing_complete = Signal()  # provides: document, user_id

# Fired in set_doc_lock_state task
if not locked:
    document_processing_complete.send(
        sender=Document,
        document=document,
        user_id=document.creator_id,
    )
```

### Corpus Action Signals

**Location**: `opencontractserver/corpuses/signals.py`

#### Direct Invocation (No M2M Signals)

> **Note**: The `Corpus.documents` M2M field has been removed (Issue #835). Corpus action
> triggering is now handled directly in `Corpus.add_document()`, `import_document()`, and
> `set_doc_lock_state()` — not via signals.

When a document is added to a corpus via `Corpus.add_document()`, actions are triggered
directly if the document is ready (`backend_lock=False`). Locked documents are handled
by `set_doc_lock_state()` when processing completes.

#### `set_doc_lock_state()` — Deferred Action Handler

Triggers deferred corpus actions when document processing completes:

```python
@receiver(document_processing_complete)
def handle_document_processing_complete(sender, document, user_id, **kwargs):
    corpuses = Corpus.objects.filter(documents=document)
    for corpus in corpuses:
        process_corpus_action.si(...).apply_async()
```

## Document Processing Pipeline

When a document is uploaded, it goes through a processing pipeline:

```
┌─────────────────────────────────────────────────────────────────┐
│                    DOCUMENT PROCESSING PIPELINE                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. Document Created                                             │
│     └─► backend_lock = True                                      │
│                                                                  │
│  2. post_save Signal Fires                                       │
│     └─► Chains processing tasks                                  │
│                                                                  │
│  3. extract_thumbnail Task                                       │
│     └─► Generates preview image                                  │
│                                                                  │
│  4. ingest_doc Task                                              │
│     └─► Parses document (Docling/LlamaParse)                    │
│     └─► Extracts text layers                                     │
│     └─► Creates PAWLs tokens                                     │
│                                                                  │
│  5. set_doc_lock_state Task                                      │
│     └─► backend_lock = False                                     │
│     └─► processing_finished = now()                              │
│     └─► Fires document_processing_complete signal                │
│                                                                  │
│  6. Corpus Actions Triggered (if doc in corpus)                  │
│     └─► Fieldset extractions                                     │
│     └─► Analyzer analyses                                        │
│     └─► Agent actions                                            │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Deferred Action Architecture

Corpus actions wait for document processing to complete before executing. This is critical for agent-based actions that need access to parsed document content.

### Why Deferred?

- Agent tools like `load_document_text` require parsed content
- Embedding-based search requires vector embeddings
- Thumbnail previews should be available

### How It Works

| Document State | M2M Signal Behavior | Processing Complete Behavior |
|----------------|---------------------|------------------------------|
| `backend_lock=True` | Skipped | Triggers actions |
| `backend_lock=False` | Triggers immediately | N/A |

### Timing

1. **New upload to corpus**:
   - M2M signal fires → document locked → skipped
   - Processing completes → signal fires → actions trigger

2. **Existing doc added to corpus**:
   - M2M signal fires → document unlocked → triggers immediately

## Signal Registration

Signals must be imported in the app's `ready()` method:

```python
# opencontractserver/corpuses/apps.py
class CorpusesConfig(AppConfig):
    def ready(self):
        from opencontractserver.corpuses import signals  # noqa: F401

# opencontractserver/documents/apps.py
class DocumentsConfig(AppConfig):
    def ready(self):
        from opencontractserver.documents import signals  # noqa: F401
```

## Monitoring

### Flower Dashboard

Access Celery monitoring at `http://localhost:5555` (when running locally).

### Logging

Key log patterns for debugging:

| Pattern | Component |
|---------|-----------|
| `[set_doc_lock_state]` | Document processing completion |
| `[CorpusSignal]` | Corpus action triggering |
| `[AgentCorpusAction]` | Agent action execution |
| `process_corpus_action()` | Action task processing |

## Related Documentation

- [Pipeline Overview](../pipelines/pipeline_overview.md)
- [CorpusAction System](./opencontract-corpus-actions.md)
- [Agent-Based Corpus Actions](./agent_corpus_actions_design.md)
