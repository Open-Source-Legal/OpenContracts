# Bootstrap a corpus and regenerate its home/artifacts

## Purpose
Reproduce a published, intelligence-bootstrapped corpus (editorial home, data
story, document index, shareable poster) from a folder of PDFs on the local
stack. Documents the canonical one-command path, the operational knobs a large
(100+ doc) batch needs, and an optional eager/threaded acceleration.

## Prerequisites
- Local stack up: `docker compose -f local.yml up -d` (postgres, redis,
  celeryworker, docling-parser, vector-embedder, django).
- A superuser exists (becomes the corpus owner).
- A folder of ingestible files (`.pdf/.txt/.docx/.xlsx/.pptx`).

Example used below: `City of Fort Worth Contracts`, 150 PDFs, corpus id `65`,
owner `admin`. Substitute your own.

---

## 1. Stage source files inside the django container
The django container only mounts the repo, so a host path is invisible to
`ingest_corpus`. Copy the folder in first:

```bash
docker cp /path/to/Contracts opencontracts-django-1:/tmp/fw_contracts
```

## 2. Canonical path (one command, hands-off)
```bash
docker compose -f local.yml exec -T django python manage.py ingest_corpus \
  --path /tmp/fw_contracts --title "City of Fort Worth Contracts" \
  --limit 150 --enrich --public --timeout 43200
```
Creates the corpus → imports each file (Celery parse + embed) → waits → runs
one-click intelligence setup (reference weave + per-doc summaries + Collection
Profile extract) → publishes.

**Constraint:** parsing is serial — one docling microservice worker, celery
`--concurrency=1` — at ~2–3 min/doc, and `--enrich`'s async tasks queue behind
the parses. 150 docs is several hours. For a large batch, apply §3 and
optionally §4.

---

## 3. Operational knobs for a large batch

### 3a. Disable the stuck-document watchdog
`reconcile_stuck_documents` (a `django_celery_beat` PeriodicTask, every 300 s)
marks any doc with no progress in `DOCUMENT_PROCESSING_STALE_MINUTES` (default
30) as FAILED. With a serial backlog, a parsed doc waits >30 min for its
finalize step and gets falsely failed. Disable it during the batch — use
`.save()` + `PeriodicTasks.changed()` (a `.update()` bypasses the scheduler
signal and the sweep keeps running), then reload beat:

```python
# docker compose -f local.yml exec -T django python manage.py shell
from django_celery_beat.models import PeriodicTask, PeriodicTasks
t = PeriodicTask.objects.get(name="documents-reconcile-stuck-processing")
t.enabled = False; t.save(); PeriodicTasks.changed(t)
```
```bash
docker compose -f local.yml restart celerybeat
```
One more sweep may fire before the scheduler syncs; recover its casualties with
§3d. **Re-enable when done (§8).**

### 3b. Raise the docling request timeout
Large scanned PDFs exceed the 300 s default and fail after retries. The setting
is read per task, so this propagates without a worker restart:

```python
from opencontractserver.documents.models import PipelineSettings
s = PipelineSettings.objects.first(); cs = dict(s.component_settings)
k = "opencontractserver.pipeline.parsers.docling_parser_rest.DoclingParser"
cs[k] = {**cs[k], "request_timeout": 600}; s.component_settings = cs
s.save(update_fields=["component_settings", "modified"])
```

### 3c. Restart docling when its memory climbs
`docling-parser` leaks ~per-parse and trends toward OOM. Watch
`docker stats docling-parser`; when RSS passes ~5 GB:
```bash
docker compose -f local.yml restart docling-parser   # stateless; re-queues the in-flight doc
```

### 3d. Track parsing and recover false failures
Progress signal is extracted-text presence (`backend_lock`/`processing_status`
lag behind the serial finalize step):
```python
docs = Corpus.objects.get(pk=65)._get_active_documents()
docs.exclude(txt_extract_file="").exclude(txt_extract_file=None).count()        # parsed
docs.filter(processing_status="failed").exclude(txt_extract_file="").exclude(txt_extract_file=None) \
    .update(processing_status="completed", backend_lock=False, processing_error="")   # recover parsed-but-reaped
```

---

## 4. Optional acceleration: eager + threaded enrichment
With the worker saturated by serial parsing, run the artifact-driving
enrichment in-process instead of queuing it. Set
`app.conf.task_always_eager = True` on `config.celery_app` so celery tasks run
synchronously, and fan the per-unit tasks across a thread pool (the per-cell /
per-doc tasks are async + I/O-bound, so threads give ~5–6x).

### 4a. Data story (Collection Profile extract)
`run_extract` creates one Datacell per `(doc, column)` upfront, then processes
them serially (~4 h for 288). Create the extract, let `run_extract` build the
cells, then thread the empty ones and finalize:

```python
import django, os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local"); django.setup()
from config.celery_app import app
app.conf.task_always_eager = True; app.conf.task_eager_propagates = True
from concurrent.futures import ThreadPoolExecutor
from django.db import connection
from django.db.models import Q
from django.utils import timezone
from django.contrib.auth import get_user_model
from opencontractserver.corpuses.models import Corpus, CorpusAction, CorpusActionTrigger
from opencontractserver.corpuses.services.corpus_documents import CorpusDocumentService
from opencontractserver.corpuses.services.data_story import (
    PROFILE_ACTION_NAME, get_or_create_default_profile_fieldset)
from opencontractserver.extracts.models import Datacell, Extract
from opencontractserver.tasks.extract_orchestrator_tasks import run_extract, mark_extract_complete
from opencontractserver.utils.celery_tasks import get_task_by_name

u = get_user_model().objects.filter(is_superuser=True).order_by("id").first()
c = Corpus.objects.get(pk=65)
fieldset, _ = get_or_create_default_profile_fieldset(u)
Extract.objects.filter(corpus=c, fieldset=fieldset).delete()   # clean re-run; run_extract is not re-runnable on a populated Extract
action, _ = CorpusAction.objects.get_or_create(
    corpus=c, fieldset=fieldset, trigger=CorpusActionTrigger.ADD_DOCUMENT.value,
    defaults={"name": PROFILE_ACTION_NAME, "creator": u})
extract = Extract.objects.create(
    corpus=c, name=f"Action {action.name} for {c.title}", fieldset=fieldset,
    creator=u, corpus_action=action)
docs = [d for d in CorpusDocumentService.get_corpus_documents(u, c) if d.txt_extract_file]
extract.documents.add(*docs); extract.started = timezone.now(); extract.finished = None; extract.save()

run_extract(extract.id, u.id)   # creates the cells (and starts serial processing — interrupt once cells exist)

cells = list(Datacell.objects.filter(extract=extract).filter(Q(data__isnull=True) | Q(data={})).select_related("column"))
def proc(cell):
    try: get_task_by_name(cell.column.task_name).apply(args=(cell.pk,))
    finally: connection.close()
list(ThreadPoolExecutor(max_workers=6).map(proc, cells))
mark_extract_complete(extract.id)
```
Gotchas: don't background the eager run with a trailing `&` (the wrapper exits
and kills it); a "filled" cell is `data` not null **and** not `{}`; LLM value
extraction varies run-to-run.

### 4b. Document index one-liners (per-doc descriptions)
Same pattern with `run_agent_corpus_action`:
```python
from opencontractserver.corpuses.models import CorpusActionTemplate, CorpusActionExecution
from opencontractserver.corpuses.services.corpus_actions import CorpusActionService
from opencontractserver.tasks.agent_tasks import run_agent_corpus_action

action, _ = CorpusActionService.install_template(
    u, c, CorpusActionTemplate.objects.get(name="Document Description Updater"))
doc_ids = [d.id for d in CorpusDocumentService.get_corpus_documents(u, c) if d.txt_extract_file]
execs = CorpusActionExecution.bulk_queue(
    corpus_action=action, document_ids=doc_ids,
    trigger=CorpusActionTrigger.MANUAL_BATCH.value, user_id=u.id)
def proc(e):
    try:
        run_agent_corpus_action.apply(kwargs=dict(
            corpus_action_id=action.id, document_id=e.document_id,
            user_id=u.id, execution_id=e.id, force=True))
    finally: connection.close()
list(ThreadPoolExecutor(max_workers=5).map(proc, execs))
```
The per-doc description prompt is the `Document Description Updater` template's
`task_instructions` in `opencontractserver/corpuses/template_seeds.py`.

---

## 5. Data-first CAML home (optional)
The post-create branding agent writes a prose-heavy article with the live
embeds at the bottom. To lead with the embeds, overwrite the `Readme.CAML` body
(written verbatim to a new version, no agent re-generation):
```python
from opencontractserver.corpuses.services.corpus_service import CorpusService
CorpusService.update_description(u, c, NEW_CAML_BODY)
```
`NEW_CAML_BODY`: hero frontmatter, then the embeds in order —
`[component:collection-datastory]`, `[component:insight-panel]`, the graph
embeds (self-hide when empty), `[component:ask-across-docs]` — plus one short
chapter. Keep counts live (the `insight-panel` metric band); never hardcode
them. See the `writing-caml-articles` guidance for syntax.

## 6. Publish
```python
c.is_public = True; c.save()   # or pass --public to ingest_corpus
```

## 7. Capture screenshots
```bash
cd frontend && node scripts/env.js && node_modules/.bin/vite --port 3000 --strictPort
```
`:3000` is in `CORS_ALLOWED_ORIGINS`. Drive with Playwright, **a fresh browser
context per run** (a reused context caches a stale `/graphql` CORS preflight):
```js
const ctx = await browser.newContext({ viewport: { width: 1440, height: 7400 }, deviceScaleFactor: 1.5 });
const page = await ctx.newPage();
await page.goto("http://localhost:3000/c/admin/<corpus-slug>");
await page.click("text=Accept and continue");   // anonymous cookie/terms modal
// Tall viewport: the article scrolls inside an inner viewport-height container,
// so fullPage alone clips it. Element-screenshot the data-story / index sections
// by their text markers ("BY DOCUMENT TYPE", " pages", etc.).
```
Run from a path where `require("playwright")` resolves, or set
`NODE_PATH=<repo>/frontend/node_modules`.

## 8. Restore
```python
t = PeriodicTask.objects.get(name="documents-reconcile-stuck-processing")
t.enabled = True; t.save(); PeriodicTasks.changed(t)
```
```bash
docker compose -f local.yml restart celerybeat   # re-enable the watchdog
# stop the Vite :3000 process
```

---

## Notes
- §3–§4 are manual because the serial single-worker docling pipeline + 30-min
  watchdog don't suit a large batch. Folding eager/threaded enrichment and
  watchdog-awareness into `ingest_corpus` as a `--fast` flag would make this one
  command; not yet implemented.
- Steps that mutate the DB run on the live local DB. Never run the suite against
  it (`test.yml` recreates the shared postgres).
