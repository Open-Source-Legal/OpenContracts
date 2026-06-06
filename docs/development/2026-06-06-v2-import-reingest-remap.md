# Design: Opt-in "reingest & remap" for V2 corpus-export import

- **Status:** Implemented (see `changelog.d/v2-import-reingest-remap.added.md`)
- **Date:** 2026-06-06
- **Implementation note:** one gap surfaced during implementation that the
  design glossed over — the V2/V3 exporter writes PDF `annotation_json` in the
  **compact-v2** shape (`{"v": 2, "p": {page: {"b": [...], "t": ...}}}`), not the
  legacy verbose `{page: {"bounds": ...}}` shape `legacy_annotation_to_dumb_anchor`
  originally understood. Without handling it, every PDF annotation in a real
  export was silently dropped on remap. `legacy_annotation_to_dumb_anchor`
  (`utils/annotation_anchoring.py`) now accepts both shapes. Additionally, the
  deferred payload rewrites each annotation's `annotationLabel` from the export
  label **id** to the label **text**, because `remap_pending_annotations`
  resolves labels by text (the dumb-anchor contract) while the V2 export keys
  them by id. A live smoke test (`docs/test_scripts/smoke_reingest_remap.py`)
  surfaced a third: the V2 export only preserves the original **source file** for
  PDFs/binaries — text/markdown docs ship a single-NUL placeholder — so reingest
  must detect placeholder sources (`_source_is_reingestable`) and fall back to
  the baked import for them (recording a DONE pending row so their annotation
  ids still join the relationship fan-in), rather than feeding `\x00` to the
  parser. Reingest is thus a re-parse for PDF/binary docs and a no-op-baked
  import for source-less docs.
- **Scope:** Backend capability only (no REST field, no frontend). Relationships
  wired via the asynchronous `PendingDocumentAnnotations.id_map`.
- **Builds on:** PR #1910 "Defer annotation import and remap onto final PAWLs
  layer" (deferred-remap foundation).

## 1. Summary

Add a **reingest & remap** mode to the V2/V3 corpus-export importer that, per
document:

1. **Drops all structural annotations** carried by the export (the
   `StructuralAnnotationSet` and any `structural=True` entries in
   `labelled_text`).
2. **Re-ingests** the document through the *current* parser pipeline, producing
   a fresh PAWLs/text layer and fresh structural annotations.
3. **Re-anchors ("remaps") the remaining** non-structural annotations onto that
   fresh layer using the deferred-remap machinery, then wires corpus-level
   relationships once every document's remap has completed.

Reingest is **opt-out at the user-facing import boundary**: the service
`import_corpus_export_for_user` (the REST `CorpusExportImportView` and the
chunked-upload completion path both call it) defaults
`reingest_and_remap=True`, so a user uploading a corpus export gets the
re-parsed/re-anchored layer by default. To trust the export's baked PAWLs +
structural set instead, the caller passes `reingest_and_remap=False`.

The lower-level tasks (`import_corpus`, `import_corpus_v2`,
`import_corpus_v2_from_bytes`, `_import_corpus`,
`_import_document_with_annotations`) keep `reingest_and_remap=False` as their
default — an explicit opt-in for direct/programmatic callers. This keeps
`fork_corpus` (which calls `import_corpus_v2_from_bytes` and must not re-parse
an in-system duplicate) and the existing baked-import test suite unchanged
without forcing the heavyweight reingest path on them. The service threads the
flag down to the tasks explicitly, so the user-facing default still wins.

## 2. Motivation

A V2/V3 export freezes the PAWLs token layer and structural annotations produced
by *whatever parser version made the export*. When the parser improves (better
sectioning, table extraction, OCR, tokenization), an old export's structural
layer is stale, and its human/producer annotations are pinned to stale token
indices.

"Reingest & remap" lets an operator re-import an old export and **upgrade it to
the current parser's understanding** while preserving the human annotations:
throw away the exported structural layer, re-parse, and re-anchor the human
annotations onto the new tokens. This is the natural sibling of the bulk-ZIP /
sidecar import path, which already does exactly this for "dumb-anchor" producer
annotations (`import_zip_with_folder_structure`).

PR #1910 built the machinery (`PendingDocumentAnnotations`,
`remap_pending_annotations`, `anchor_annotations` + its
`legacy_annotation_to_dumb_anchor` adapter) and deliberately left the V2
corpus-import path unchanged:

> "The full-V2 / single-document corpus-export import path (which ships
> self-consistent PAWLs + indices) is deliberately unchanged."
> — `changelog.d/1910-deferred-remap.added.md`

This design wires that machinery into the V2 importer.

## 3. Goals / Non-goals

**Goals**
- Opt-in, default-off mode for `import_corpus` / `import_corpus_v2` / `_import_corpus`.
- Drop exported structural annotations; reingest via the standard pipeline;
  remap surviving non-structural token/span annotations + doc-labels.
- Wire corpus-level (non-structural) relationships **correctly** despite
  annotations now being created asynchronously, by consuming
  `PendingDocumentAnnotations.id_map` after all remaps complete.
- Reuse existing helpers (`import_content`, `PendingDocumentAnnotations`,
  `remap_pending_annotations`, `anchor_annotations`, `_import_v2_relationships`).
  No bespoke importer-owned Celery chain (consistent with the #1910 refactor).

**Non-goals (this iteration)**
- No REST serializer field and no frontend toggle (explicitly out of scope).
- `fork_corpus` is unchanged (it stays synchronous; forking a corpus should not
  silently re-parse it under a new parser version).
- No structural-set *reuse/dedup* in this mode (we discard them by design).
- The bulk-ZIP importer's existing "relationships dropped + warned" gap is **not**
  closed here, but the fan-in mechanism below is designed to be reused for it
  later (see §9).

## 4. Background: how the two import paths differ today

### 4.1 Synchronous V2 import (default; `tasks/import_tasks_v2.py`)

`_import_corpus` → per doc `_import_document_with_annotations`:

1. `create_document_from_export_data` (`utils/importing.py:477`) — creates a
   standalone `Document` with the export's PAWLs/text baked in and
   `processing_started=now()` set, which **suppresses** the parser pipeline (the
   `Document` post_save signal only fires the ingest chain when
   `not instance.processing_started`).
2. Optionally attaches the imported `StructuralAnnotationSet`
   (`import_structural_annotation_set`, `utils/import_v2.py:57`).
3. `corpus.add_document()` — corpus-isolated copy + `DocumentPath`.
4. `import_doc_annotations` → `import_annotations` — **synchronously** creates
   token/span annotations against the export's PAWLs indices and returns
   `annot_id_map` (export-local id → new pk).

Back in `_import_corpus`, the per-doc maps are aggregated into
`all_annot_id_maps`, then `_import_v2_relationships` (`:552`) wires corpus-level
relationships using that map. (Intra-doc relationships are *not* imported in the
V2 path — `import_doc_annotations` does not call `import_relationships`; the
export emits everything as corpus-level `relationships`.)

### 4.2 Deferred-remap path (bulk-ZIP; `tasks/import_tasks.py`)

`import_zip_with_folder_structure`: creates the doc via
`corpus.import_content(..., backend_lock=True)` (no `processing_started`, so the
pipeline runs), and persists producer annotations in a
`PendingDocumentAnnotations` row inside the **same** `transaction.atomic()` as
the doc. The standard post_save chain then runs:

```
extract_thumbnail → ingest_doc → remap_pending_annotations → set_doc_lock_state
```

`remap_pending_annotations` (`tasks/doc_tasks.py:979`) anchors the pending
annotations onto the freshly-parsed PAWLs and records
`PendingDocumentAnnotations.id_map = {str(old_export_id): new_pk}`. Relationships
are *not* wired (TODO in `import_tasks.py`; the `id_map` field was the forward
investment for closing it).

### 4.3 Why relationships are the hard part here

In reingest mode the annotations land **asynchronously** (one Celery chain per
document, dispatched by the post_save signal via `transaction.on_commit`), so at
the moment `_import_corpus` returns, `all_annot_id_maps` is empty. The importer
does **not** own those chains, so it cannot simply `chord` them. We need a
fan-in: wait until every document's remap for this import run is done, aggregate
their `id_map`s, then wire relationships.

## 5. Design overview

```
import_corpus(reingest_and_remap=True)
        │
        ▼
_import_corpus
  ├─ setup corpus + labels (unchanged; creates TOKEN/SPAN/RELATIONSHIP/DOC labels)
  ├─ SKIP import_structural_annotation_set        ← (1) drop structural
  ├─ create PendingCorpusImport(run_id, relationships, status=ENUMERATING)  [if rels exist]
  ├─ for each doc: _import_document_with_annotations(reingest_and_remap=True)
  │       ├─ import_content(raw bytes, backend_lock=True)   ← (2) reingest
  │       └─ PendingDocumentAnnotations(run_id, payload=non-structural anns)  ← (3) remap later
  ├─ set PendingCorpusImport.expected_doc_count, status=READY
  └─ _maybe_finalize_corpus_import(run_id)         (covers "all remaps already done")

per-doc post_save chain (async, one per doc):
  extract_thumbnail → ingest_doc → remap_pending_annotations → set_doc_lock_state
                                          │
                                          └─ _maybe_finalize_corpus_import(run_id)  (guarded no-op for non-import remaps)

_maybe_finalize_corpus_import(run_id):  (atomic, exactly-once claim)
   if PendingCorpusImport is READY and all run rows left PENDING:
       flip → FINALIZING, dispatch finalize_corpus_import_relationships(run_id)

finalize_corpus_import_relationships(run_id):
   aggregate id_map from all DONE PendingDocumentAnnotations(run_id)
   rebuild label_lookup_by_text from corpus.label_set
   _import_v2_relationships(payload, corpus, aggregated_id_map, labels, creator)
   mark DONE
```

## 6. Detailed design

### 6.1 Flag plumbing (backend only)

Add `reingest_and_remap` to, in call order (the **service** defaults it `True`
— the opt-out boundary — while every lower-level task defaults it `False`):

- `document_imports/services.py::import_corpus_export_for_user(..., reingest_and_remap=True)`
  — appended to the `import_corpus.s(...)` signature. The REST view
  (`CorpusExportImportView`) and the chunked-upload completion path both call
  this without overriding it, so the user-facing import reingest by default;
  **no serializer field** is added, so there is no per-request opt-out from the
  public API yet.
- `tasks/import_tasks.py::import_corpus(..., reingest_and_remap=False)` (`:63`) —
  pass-through to `import_corpus_v2`; defaults off (the service passes the value
  through explicitly).
- `tasks/import_tasks_v2.py::import_corpus_v2(...)`,
  `import_corpus_v2_from_bytes(...)`, `_import_corpus(...)`,
  `_import_document_with_annotations(...)`.
- `fork_corpus` (`tasks/fork_tasks.py`) calls `import_corpus_v2_from_bytes`
  with the default `False` — **unchanged**.

> Celery signature compatibility: `import_corpus` is dispatched as
> `import_corpus.s(temp_file.id, user.id, corpus.id)`. Adding a trailing
> keyword-with-default keeps existing `.s(...)` call sites valid.

### 6.2 Per-document reingest path

In `_import_document_with_annotations`, when `reingest_and_remap=True`:

```python
# 1. Raw source bytes from the zip (NOT the baked PAWLs/text).
with import_zip.open(doc_filename) as fh:
    file_bytes = fh.read()

with transaction.atomic():
    # 2. Reingest: no processing_started → standard pipeline runs on commit.
    corpus_doc, _status, _path = corpus_obj.import_content(
        content=file_bytes,
        user=user_obj,
        filename=doc_filename,                       # path auto-generated
        title=doc_data["title"],
        description=doc_data.get("description", ""),
        file_type=doc_data.get("file_type"),
        pdf_file_hash=doc_data.get("pdf_file_hash") or None,  # roundtrip key
        backend_lock=True,
    )
    set_permissions_for_obj_to_user(user_obj, corpus_doc, [PermissionTypes.ALL], is_new=True)

    # 3. Defer the surviving non-structural annotations for remap.
    non_structural = [a for a in doc_data.get("labelled_text", []) if not a.get("structural")]
    if non_structural or doc_data.get("doc_labels"):
        PendingDocumentAnnotations.objects.create(
            document=corpus_doc,
            corpus=corpus_obj,
            creator=user_obj,
            ingestion_run_id=import_run_id,
            payload={"annotations": non_structural, "doc_labels": doc_data.get("doc_labels", [])},
            status=PendingDocumentAnnotations.Status.PENDING,
        )

return corpus_doc, {}   # synchronous id_map is empty in this mode
```

Notes:
- **No `structural_sets` argument** is passed in this mode, so no
  `StructuralAnnotationSet` is imported or attached → exported structural
  annotations are dropped. The fresh parser regenerates structural annotations
  during ingest.
- `labelled_text` entries are the **legacy baked-`annotation_json`** shape.
  `anchor_annotations` already accepts them via `legacy_annotation_to_dumb_anchor`
  (it discards stale token indices and re-derives from bbox + `rawText`), and it
  **drops + reports** any `structural=True` entry — so filtering structurals out
  above is belt-and-suspenders, keeping the payload lean and the report clean.
- The doc + pending row share one `transaction.atomic()` so the post_save chain
  (dispatched at the outermost commit) sees the committed pending row — the same
  invariant the bulk-ZIP importer relies on.
- `import_content` auto-generates a `DocumentPath`; `_reconstruct_document_paths`
  later rewrites path/folder/version/lineage keyed on `pdf_file_hash`
  (preserved), so folder structure is restored as in the default path.
- `doc_hash_to_corpus_doc` / `doc_filename_to_corpus_doc` are still populated, so
  DocumentPath reconstruction, metadata schema, conversations, and CAML README
  rewriting are unaffected.

**Markdown / CAML docs:** these short-circuit the pipeline in the post_save
signal (status COMPLETED immediately, no PAWLs). They normally carry no
`labelled_text`, so no pending row is created and remap never runs for them. If
one *did* carry annotations, remap would report them as un-anchorable (no PAWLs)
— acceptable and visible on the row's `report`. The corpus description /
Readme.CAML flow (`md_description` shim, `refresh_description_cache_for_corpus`)
is unchanged.

### 6.3 Coordination model for relationship fan-in

New model `PendingCorpusImport` (in `documents/models.py`, beside
`PendingDocumentAnnotations`; migration `documents/0042`):

| field | type | purpose |
|-------|------|---------|
| `import_run_id` | `UUIDField(unique, db_index)` | same value stamped on the run's `PendingDocumentAnnotations.ingestion_run_id` |
| `corpus` | `FK(Corpus, on_delete=CASCADE)` | target corpus |
| `creator` | `FK(User, on_delete=CASCADE)` | importing user (relationship creator) |
| `relationships_payload` | `JSONField(default=list)` | corpus-level non-structural relationships to wire |
| `expected_doc_count` | `IntegerField(null=True)` | number of pending-annotation docs created; `NULL` while enumerating |
| `status` | `CharField(choices)` | `ENUMERATING / READY / FINALIZING / DONE / FAILED` |
| `report` | `JSONField(default=dict)` | created/skipped counts + errors |
| `created_at` / `updated_at` | timestamps | stuck-row debugging |

A coordination row is created **only when the run has corpus-level relationships
to wire** — otherwise there is nothing to finalize and reingest mode skips it
entirely (the run is pure fan-out).

**Pre-existing dependency (no new field migration).**
`PendingDocumentAnnotations.ingestion_run_id` (`UUIDField(null=True, db_index=True)`)
and `PendingDocumentAnnotations.id_map` (`JSONField(default=dict)`) **already
exist** — they were added by #1910 in migration `documents/0041`. This design
adds **only one** migration, `documents/0042`, for the new `PendingCorpusImport`
model; it does not touch `PendingDocumentAnnotations`'s schema. The `null=True` on
`ingestion_run_id` is what lets ordinary single-doc uploads carry no run id and be
skipped by the finalize trigger (see §6.4 step 2).

**`expected_doc_count` is observability, not the completeness gate.** The
finalization check in `_maybe_finalize_corpus_import` (§6.4 step 3) is "are there
still `PENDING` rows for this run?" (`.exists()`), **not** a comparison against
`expected_doc_count`. The count is deliberately *not* part of the gate: a row may
end `DONE` or `FAILED`, both of which clear `PENDING`, and using the count would
race against rows that error during `import_content` and are never created. The
field exists for (a) the orphaned-row sweeper in §9 (a sanity bound on how many
rows a healthy run should have produced) and (b) stuck-run debugging. If it earns
no consumer once the sweeper lands, it should be dropped rather than left dangling.

**`relationships_payload` size.** The payload is the run's corpus-level
non-structural relationships, stored as one JSON blob on one row. For
export-sized corpora this is bounded and fine. For a hypothetical very large /
densely cross-linked corpus the blob could grow large; this is noted as a known
ceiling, not addressed here. If it becomes a problem, the relationships can be
chunked across rows keyed by `import_run_id` without changing the fan-in contract.

### 6.4 Lifecycle & exactly-once finalization

1. **Enumerate (in `_import_corpus`, reingest mode):**
   - Mint `import_run_id = uuid4()` once for the import.
   - If `relationships_data` is non-empty, create
     `PendingCorpusImport(import_run_id, corpus, creator, relationships_payload=relationships_data, expected_doc_count=None, status=ENUMERATING)`.
   - Run the doc loop, counting successfully-created pending rows.
   - After the loop: `expected_doc_count = <count>`, `status = READY`, save; then
     call `_maybe_finalize_corpus_import(import_run_id)` (handles the case where
     every doc's remap already finished before `READY` was set, including
     `count == 0` → finalize immediately, relationships all-skipped).

2. **Trigger (in `remap_pending_annotations`, `tasks/doc_tasks.py`):** after
   processing a doc's rows, collect the distinct non-null `ingestion_run_id`s of
   the rows it handled and call `_maybe_finalize_corpus_import(run_id)` for each.
   The guard is explicit and two-staged — the `null` check short-circuits before
   any extra query, then `_maybe_finalize_corpus_import` itself is a no-op when no
   coordination row exists for the run (a relationship-free run mints a run id but
   no `PendingCorpusImport` row):
   ```python
   run_ids = {
       r.ingestion_run_id
       for r in handled_rows
       if r.ingestion_run_id is not None     # (a) single-doc uploads skip here
   }
   for run_id in run_ids:
       _maybe_finalize_corpus_import(run_id)  # (b) no PendingCorpusImport row → returns immediately
   ```
   - Cost on the generic path: ordinary single-doc uploads have **no** pending
     rows at all, so `remap_pending_annotations` bails at its first query and
     never reaches this check; even if a non-import remap produced a row, its
     `ingestion_run_id` is `NULL` and is filtered out by (a) before any query.
     Only genuine *import* remaps pay the one indexed lookup inside
     `_maybe_finalize_corpus_import`.

3. **`_maybe_finalize_corpus_import(run_id)` (atomic, exactly-once):**
   ```python
   with transaction.atomic():
       row = (PendingCorpusImport.objects
              .select_for_update(skip_locked=True)
              .filter(import_run_id=run_id, status=READY).first())
       if row is None:
           return  # absent, not enumerated yet, or already claimed
       remaining = PendingDocumentAnnotations.objects.filter(
           ingestion_run_id=run_id, status=PendingDocumentAnnotations.Status.PENDING
       ).exists()
       if remaining:
           return  # not all docs done; lock releases on block exit
       row.status = PendingCorpusImport.Status.FINALIZING
       row.save(update_fields=["status"])
   transaction.on_commit(lambda: finalize_corpus_import_relationships.delay(str(run_id)))
   ```
   Only the worker that both observes completeness **and** wins the row lock
   flips to `FINALIZING` and dispatches — exactly-once across the post-loop
   check, the last doc's remap, and any Celery at-least-once retries.

4. **`finalize_corpus_import_relationships(run_id)` (new Celery task):**
   - Load the row and accept it only in a re-runnable state — `FINALIZING` (normal
     dispatch) **or** `FAILED` (a prior attempt that errored mid-wiring; see retry
     note below). Any other state (`DONE`, missing) is a no-op return, so a stray
     redelivery after success never double-wires.
   - Aggregate `id_map`: merge `.id_map` from every
     `PendingDocumentAnnotations.objects.filter(ingestion_run_id=run_id, status=DONE)`.
     Keys are `str(old_export_id)`; values are new pks.
   - Rebuild `label_lookup_by_text = {(lbl.text, lbl.label_type): lbl for lbl in corpus.label_set.annotation_labels.all()}`
     (relationship labels are present — export writes `RELATIONSHIP_LABEL` into
     `text_labels`, `etl.py:204`).
   - Call `_import_v2_relationships(relationships_payload, corpus, aggregated_id_map, label_lookup_by_text, creator)`.
     It already skips structural relationships and drops endpoints missing from
     the map (annotations that failed to anchor), so partial remaps degrade
     gracefully.
   - Mark `DONE` with a report; on exception mark `FAILED` with the error.

   **Retry / idempotency.** Relationship wiring must be safe to run more than once
   because Celery delivery is at-least-once. Two layers cover this: (a) the task
   accepts `FAILED` as a re-entry state (above), so a retried/redelivered task can
   resume rather than dead-end on `status != FINALIZING`; (b) the wiring itself is
   made idempotent — wrap the `_import_v2_relationships` call so a re-run does not
   create duplicate `Relationship` rows (skip relationships already present for the
   corpus, or run inside a transaction that `DONE` gates). The simplest concrete
   rule: the finalize body runs in `transaction.atomic()` and flips `FAILED →
   FINALIZING → DONE`; only a `DONE` flip commits the wired relationships, so a
   crash before `DONE` rolls back the partial relationship writes and the retry
   starts clean. This is verified by test case 9 (§8).

   **State machine:**
   `ENUMERATING → READY → FINALIZING → DONE` on success;
   `FINALIZING → FAILED → (retry) → FINALIZING → DONE` on a recoverable error.
   `ENUMERATING`/`READY` can also be terminal-orphaned by an importer crash (§6.5),
   which the §9 sweeper is responsible for resolving.

### 6.5 Race & failure analysis

- **Last remap vs. post-loop READY:** if the final remap runs while status is
  still `ENUMERATING`, its `_maybe_finalize` filter (`status=READY`) no-ops; the
  post-loop `_maybe_finalize` then finalizes. If `READY` is set first, the final
  remap finalizes. Exactly one finalize either way.
- **Duplicate/retried remap:** the atomic `select_for_update(skip_locked)` +
  flip to `FINALIZING` makes the second observer find `status != READY`.
- **A doc fails to anchor anything:** its row ends `FAILED` (not `PENDING`), so
  completion still triggers; its (absent) annotations are simply missing from the
  aggregated map and dependent relationship endpoints are skipped.
- **A doc errors during `import_content`:** `_import_document_with_annotations`
  returns `(None, {})` (existing contract); no pending row, not counted; the run
  still finalizes for the docs that succeeded.
- **`_import_corpus` crashes before setting `READY`:** the coordination row is
  orphaned in `ENUMERATING` and relationships are never wired — consistent with
  the existing "standalone Celery import accepts partial state on failure"
  contract (`_import_corpus` docstring). Mitigation/future work in §9 (sweeper or
  TTL-based finalize).

## 7. Components touched

**New**
- `documents/models.py`: `PendingCorpusImport` model.
- `documents/migrations/0042_pendingcorpusimport.py`.
- `tasks/doc_tasks.py`: `finalize_corpus_import_relationships` task +
  `_maybe_finalize_corpus_import` helper.

**Changed**
- `document_imports/services.py`: `import_corpus_export_for_user(reingest_and_remap=True)` (opt-out boundary) → thread into `import_corpus.s(...)`. (Chunked
  `corpus_export` completion path inherits the `True` default.)
- `tasks/import_tasks.py`: `import_corpus(reingest_and_remap=False)` pass-through (low-level default off; the service overrides it).
- `tasks/import_tasks_v2.py`: flag on `import_corpus_v2`,
  `import_corpus_v2_from_bytes`, `_import_corpus`,
  `_import_document_with_annotations`; reingest branch; coordination-row
  create/READY; post-loop finalize call; skip structural-set import in this mode.
- `tasks/doc_tasks.py::remap_pending_annotations`: post-processing finalize
  trigger (guarded).

**Unchanged (verified):** default V2/V3 import, `fork_corpus`, REST serializers,
frontend, `_reconstruct_document_paths`, metadata/conversation/CAML import.

## 8. Testing plan

Backend tests (new `tests/test_import_v2_reingest_remap.py`, plus targeted
additions to `tests/test_remap_pending_annotations.py`):

1. **Drop structural:** build a tiny V2 export (PDF + structural set + a couple
   of human token annotations + a corpus relationship), import with
   `reingest_and_remap=True` under `CELERY_TASK_ALWAYS_EAGER`; assert no
   `StructuralAnnotationSet` from the export is attached and structural
   annotations present after import are the *parser's*, not the export's
   (e.g. differ in `creator`/`structural_set` lineage / count).
2. **Reingest:** assert the doc went through the pipeline (PAWLs/text regenerated;
   `processing_status == COMPLETED`, `backend_lock == False`).
3. **Remap:** assert surviving non-structural annotations are re-anchored onto
   the fresh PAWLs and the `PendingDocumentAnnotations` row is `DONE`; an
   un-anchorable annotation is reported `dropped` and does not fail the run.
4. **Relationship fan-in (the key case):** a corpus relationship referencing two
   remapped annotations across two docs is created **after** both remaps, with
   correct endpoints resolved from the aggregated `id_map`; the
   `PendingCorpusImport` row ends `DONE`.
5. **Exactly-once / ordering:** force finalize from both the post-loop call and a
   remap; assert relationships are created once (no duplicates).
6. **Default path untouched:** `reingest_and_remap=False` (default) still imports
   structural sets synchronously and creates no `PendingDocumentAnnotations` /
   `PendingCorpusImport` rows (regression guard).
7. **No-relationships run:** reingest mode with no corpus relationships creates
   no `PendingCorpusImport` row and still remaps annotations.
8. **Doc fails during `import_content`:** one doc in a multi-doc run raises during
   reingest; assert it produces no pending row, the run still finalizes, and only
   the surviving docs' relationships are wired (endpoints into the failed doc are
   dropped, not errored).
9. **Finalize retry idempotency:** force `finalize_corpus_import_relationships` to
   error after the row flips to `FINALIZING` (simulate a mid-wiring failure), then
   re-dispatch; assert relationships end up created **exactly once** (no
   duplicates) and the row ends `DONE` — exercising the at-least-once + idempotency
   contract in §6.4 step 4.
10. **Markdown/CAML carrying annotations (edge case from §6.2):** import a
    CAML/markdown doc that (unusually) carries `labelled_text` in reingest mode;
    assert remap reports them un-anchorable on the row's `report` (no PAWLs) and
    the run does not fail.

In addition to the end-to-end cases above, add a **targeted unit test on
`anchor_annotations`** feeding it a realistic V2-shaped legacy annotation (baked
`annotation_json` + `bbox` + `rawText`, no live token indices) and asserting
`legacy_annotation_to_dumb_anchor` produces a valid anchor. This catches V2-shape
divergence (e.g. a missing `bbox` key) faster and more precisely than the
end-to-end remap case 3, since the V2 export annotation shape feeds the remap
machinery here for the first time.

Run targeted: `docker compose -f test.yml run django pytest opencontractserver/tests/test_import_v2_reingest_remap.py opencontractserver/tests/test_remap_pending_annotations.py -n 4 --dist loadscope --create-db`.

## 9. Future work / explicitly deferred

- **Reuse for bulk-ZIP relationships:** the same `PendingCorpusImport` fan-in can
  close the bulk-ZIP importer's "relationships dropped + warned" gap
  (`import_tasks.py`); out of scope here.
- **Orphaned-coordination sweeper:** a management command or TTL that finalizes
  (or fails) `ENUMERATING`/`READY` rows stuck past a threshold, for the
  importer-crash case in §6.5. This is the intended consumer of
  `expected_doc_count` (§6.3): a `READY` row whose `PENDING` count plus `DONE`/
  `FAILED` count never reaches `expected_doc_count` within the threshold is a
  stuck run the sweeper can fail explicitly.
- **REST + frontend surface:** the service now defaults reingest **on**
  (opt-out), but there is still no per-request override — add `reingest_and_remap`
  to `CorpusExportImportSerializer` + a UI toggle so a user can opt a specific
  upload *out* of reingest (intentionally excluded now; the default-on behaviour
  ships first).
- **Alternative considered — polling finalizer:** instead of triggering from
  `remap_pending_annotations`, dispatch a self-re-enqueuing finalizer (countdown
  while PENDING rows remain, bounded attempts). Simpler (no change to the generic
  remap path) but uses polling latency + a worker slot and needs an attempt cap.
  Rejected as primary in favor of the event-driven, exactly-once trigger; kept as
  a fallback if the remap-path coupling proves undesirable.

## 10. Changelog

On implementation, add `changelog.d/<pr>.added.md` documenting the
reingest-&-remap V2 import mode (opt-out at the user-facing import service), the
`PendingCorpusImport` model + migration, and the asynchronous
relationship-wiring fan-in.
