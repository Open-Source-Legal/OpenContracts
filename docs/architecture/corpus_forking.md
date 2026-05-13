# Corpus Forking: Technical Documentation

This document describes the corpus forking implementation — what is actually
copied, what is shared with the source, what is intentionally left out, and
how the two entry points (GraphQL mutation, programmatic utility) differ.

## Overview

Corpus forking produces a new `Corpus` row owned by the forking user, attached
to the original via `parent_id`. The new corpus inherits the source corpus's
scalar fields, gets a fresh `LabelSet` + `Label` copies, gets corpus-isolated
documents (with file blobs **shared** by reference), copies user-created
annotations and relationships, copies folder hierarchy, and — when invoked via
the GraphQL path or `build_fork_corpus_task` — also copies the manual metadata
schema (Fieldset + manual-entry Columns + manual Datacells).

## Architecture

### Components

| Component | File | Responsibility |
|-----------|------|----------------|
| GraphQL mutation | `config/graphql/corpus_mutations.py` (`StartCorpusFork`) | Permission check, corpus shell creation, optional `preferred_embedder` override, dispatch async task |
| Programmatic utility | `opencontractserver/utils/corpus_forking.py` (`build_fork_corpus_task`) | Same shell-creation flow without GraphQL/permission plumbing; returns a Celery signature for callers (tests) to apply |
| Object collector | `opencontractserver/utils/corpus_collector.py` (`collect_corpus_objects`) | Single source of truth for which IDs the fork task receives (see #816) |
| Fork task | `opencontractserver/tasks/fork_tasks.py` (`fork_corpus`) | Async Celery task that performs the clone inside one `transaction.atomic()` |

The mutation and utility paths must stay in sync on what they collect — see
"Two entry points, one task" below for current drift.

### Data flow

```
1. Caller (mutation or utility) loads source Corpus
2. collect_corpus_objects(corpus, include_metadata=True) gathers:
   - active document IDs via DocumentPath (is_current=True, is_deleted=False)
   - user-created annotation IDs (analysis__isnull=True)
   - user-created relationship IDs (analysis__isnull=True)
   - label_set_id
   - folder IDs in tree order (with_tree_fields())
   - manual metadata: Fieldset/Columns (is_manual_entry=True) and
     non-extract Datacells (extract__isnull=True)
3. Caller deep-copies the source Corpus in-memory (pk=None, slug=""),
   prefixes title with "[FORK] ", sets backend_lock=True, creator=user,
   parent_id=source.pk, then saves to insert a new row.
4. Caller clears corpus_clone.label_set (the cloned row still points at the
   source's labelset; the fork task creates a new one).
5. Caller dispatches fork_corpus.si(...) via transaction.on_commit so the
   new shell is visible when the task starts.
6. fork_corpus runs inside transaction.atomic() and clones in order:
   a. LabelSet + Labels (builds label_map)
   b. Metadata schema: Fieldset + manual-entry Columns (builds column_map)
   c. Folders (builds folder_map, tree-ordered)
   d. Documents via corpus.add_document() (builds doc_map; preserves
      original DocumentPath path + folder assignment; deduplicates
      structural set sharing across docs)
   e. Annotations (builds annotation_map; remaps document_id +
      annotation_label_id; corpus_id → new corpus)
   f. Manual Datacells (remaps document_id + column_id; approval status
      reset)
   g. Relationships (remaps source/target annotation IDs via
      annotation_map; only created when BOTH sides have surviving
      mappings)
7. On success: unlock corpus (backend_lock=False), return corpus.id.
8. On any exception inside the transaction: roll back, set error=True,
   unlock, return None.
```

### ID maps maintained by `fork_corpus`

```python
label_map: dict[int, int]                     # old label id -> new label id
column_map: dict[int, int]                    # old Column id -> new Column id
folder_map: dict[int, int]                    # old folder id -> new folder id
doc_map: dict[int, int]                       # old doc id -> new corpus-isolated doc id
annotation_map: dict[int, int]                # old annotation id -> new annotation id
structural_set_map: dict[int, StructuralAnnotationSet]
                                              # old set id -> set reused for all docs
                                              # that pointed at it. NOTE: this holds the
                                              # SAME set instance that was on the source
                                              # corpus's docs; nothing is duplicated.
```

### Tree ordering for folder hierarchy

Folders are stored as a `tree_queries.TreeNode`. When cloning, parents must
exist before children so `parent_id=folder_map.get(old_folder.parent_id)`
resolves. The default `tree_ordering` produced by `.with_tree_fields()` is
parent-first; use that rather than `.order_by("tree_depth", "pk")` because
`tree_depth` is a CTE-only column and Django will reject it at validation.

```python
CorpusFolder.objects.filter(corpus_id=pk).with_tree_fields()  # correct
```

## What gets copied — and how

### Cloned (new rows in the target corpus)

| Data | Filter | Notes |
|------|--------|-------|
| `Corpus` row itself | n/a | Copied by `pk=None; save()`. All scalar fields (`description`, `preferred_embedder`, `post_processors`, `corpus_agent_instructions`, `document_agent_instructions`, `allow_comments`, `is_public`, `error`, etc.) carry over. `title` is prefixed `"[FORK] "`. `parent_id` is set to the source's pk. `slug` is cleared so `save()` mints a new one. |
| `LabelSet` | source's `label_set` if any | New row, title prefixed `"[FORK] "`. Icon is **deep-copied** (file contents are read and rewritten under a new storage path). |
| `AnnotationLabel` | every label in source labelset | New rows; mapped via `label_map`. |
| `Fieldset` + `Column` (manual metadata) | `Column.is_manual_entry=True` | New rows. Columns preserve `display_order`, `output_type`, `data_type`, `validation_config`, `default_value`, `help_text`. `query`/`match_text` are explicitly set to `None` (extraction-only fields are not relevant for manual metadata). |
| `CorpusFolder` | all folders on source | Tree hierarchy reconstructed via `folder_map`. `tags` are deep-copied. |
| `Document` | active via `DocumentPath` | Created via `corpus.add_document()`, which inserts a **corpus-isolated copy** sharing the source document's file blobs (see "Shared, not duplicated" below). Title prefixed `"[FORK] "`. |
| `DocumentPath` | implicit | Created by `add_document()`. Original path + folder are preserved when an `original_path` exists on the source corpus (lookup uses `corpus.parent_id` to find the source). |
| `Annotation` | user-created on source corpus (`analysis__isnull=True`) | New rows; mapped via `annotation_map`. `document_id` and `annotation_label_id` are remapped. `corpus_id` is set to the new corpus. **CRUD permissions are granted per annotation** — note that the V2 import path documents this as dead work (see "Known oddities" below). |
| `Datacell` (manual) | `extract__isnull=True` for documents in `doc_map` AND columns in `column_map` | New rows. `data` is deep-copied via `.copy()`. `approved_by`/`rejected_by`/`corrected_data` are reset (fresh approval state). |
| `Relationship` | user-created on source corpus (`analysis__isnull=True`) | New rows. Source/target M2M annotation IDs are remapped via `annotation_map`. **A relationship is skipped if neither source nor target has any surviving annotation mapping** — partial mappings still create a relationship with the surviving subset. |

### Shared, not duplicated (reference-copied)

These are "copied" in the sense that the new row references them, but the
underlying storage / row is the same as the source's. Modifying the file
content out-of-band on the source affects the fork (and vice versa).

| Data | What is shared | Why |
|------|----------------|-----|
| `Corpus.icon` (file field) | Storage path | `pk=None; save()` reuses the file reference. **Not deep-copied** — unlike `LabelSet.icon`. |
| `Corpus.md_description` (file field) | Storage path | Same as `icon`. |
| `Document.pdf_file`, `Document.pawls_parse_file`, `Document.txt_extract_file`, `Document.icon`, `Document.md_summary_file` | Storage paths | `corpus.add_document()` explicitly shares blobs (Rule I3). |
| `StructuralAnnotationSet` | Same row reused for all forked docs that pointed at it | `add_document()` defaults `structural_annotation_set` to `document.structural_annotation_set` unless overridden. `fork_corpus` keeps a `structural_set_map` so multi-doc references stay consistent within the fork, but the set it stores is the **original** set — the fork's docs reference the same structural annotations as the source's docs. New embeddings under the fork's `preferred_embedder` are added lazily by `ensure_embeddings_for_corpus`. |

### Not copied (by design)

| Data | Reason |
|------|--------|
| Analysis-generated annotations and relationships | They belong to an Analysis, not to the source corpus's curated dataset. Filter: `analysis__isnull=True` excludes them. |
| Extraction-only `Column` rows (`is_manual_entry=False`) | Extraction columns belong to extracts, not to the corpus's manual metadata. |
| `Datacell` rows with `extract` set | Same reasoning — those belong to the extract. |
| Datacell approval status (`approved_by`, `rejected_by`, `corrected_data`) | Manual approval state is intentionally reset on fork. |
| `Note` rows | Not yet implemented. Tracked under "Future enhancements" below. |
| `Category` M2M associations | `pk=None; save()` doesn't carry M2Ms; not currently re-attached. |
| Vector embeddings on annotations / docs | Regenerated on demand by `ensure_embeddings_for_corpus` when the fork's `preferred_embedder` differs from the source's. |
| `UserExport`, `Conversation`, `ChatMessage`, `MessageVote`, action trail | Out of scope — none of the fork code touches these. |

## Permissions granted on fork

After a successful fork, `set_permissions_for_obj_to_user(user, obj, [PermissionTypes.CRUD])` is called for these new objects:

- `Corpus` (set by the caller, not the task)
- `Fieldset`, `Column` (set by the task when metadata is included)
- `CorpusFolder`
- `Document` (the corpus-isolated copy)
- `Annotation`
- `Datacell` (manual metadata)
- `Relationship`

**Notable omissions:** `LabelSet` and individual `AnnotationLabel` rows do **not** receive guardian permissions. Whether this matters in practice depends on the labelset/label visibility model the rest of the app relies on — but it is a real divergence from "the user owns everything they just forked".

## Two entry points, one task

Both paths land at `fork_corpus.si(...)` with the same positional args, but
they differ:

| Concern | `StartCorpusFork` (GraphQL) | `build_fork_corpus_task` (utility) |
|---------|-----------------------------|------------------------------------|
| Auth + visibility check | Yes (`visible_to_user`, then `READ` perm) | None — caller is responsible |
| `preferred_embedder` override | Yes (`preferred_embedder` arg overwrites before save) | **No support** — fork always inherits the source's embedder |
| Telemetry | Records `corpus_forked` event | None |
| Apply pattern | `apply_async()` on `transaction.on_commit` | Returns a `Signature`; caller does `.apply().get()` (tests use this for synchronous execution) |

Keep these two paths feature-parity-aware: any change to one (e.g. new
collected fields, new corpus-level overrides) should be mirrored to the other.

## Error handling

`fork_corpus` runs inside `transaction.atomic()`. Any unhandled exception
inside the `try` rolls the transaction back, sets `corpus.error = True`,
releases `corpus.backend_lock`, and returns `None`. The corpus shell remains
in the database with `error=True` so the UI can surface the failure; cleanup
of the orphaned shell row is a future enhancement.

The task tolerates legacy queued tasks (predating the metadata feature) by
defaulting `metadata_column_ids` and `metadata_datacell_ids` to `None` and
treating `None` as "no metadata to copy".

## Testing

### Round-trip tests

- `opencontractserver/tests/test_corpus_fork_round_trip.py` — multi-generation
  forks, exception handling, metadata preservation, regression cases. Uses a
  `CorpusSnapshot` dataclass plus per-feature assertions.
- `opencontractserver/tests/test_corpus_forking.py` — original feature-level
  test that round-trips a real V1 export through `build_fork_corpus_task`.

### Running

```bash
docker compose -f test.yml run django pytest opencontractserver/tests/test_corpus_fork_round_trip.py
docker compose -f test.yml run django pytest opencontractserver/tests/test_corpus_forking.py
```

## Known oddities and watchpoints

These are the spots most likely to surprise a reader of the code:

- **Annotation labels that aren't in the source labelset get silently dropped.**
  `fork_tasks.py` builds `label_map` from `old_label_set.annotation_labels.all()`.
  An annotation whose `annotation_label_id` is *not* in the labelset (e.g. a
  label that was once in the set and was later removed, or a structural label
  on a non-structural annotation) gets its `annotation_label_id` rewritten to
  `None` rather than kept or having the annotation skipped. Compare with the
  V2 import path, which logs a warning and **skips** the annotation. This is a
  drift between the two ID-remap pipelines.
- **Per-annotation guardian permissions on the fork path.** `fork_corpus` runs
  `set_permissions_for_obj_to_user(user_id, annotation, [CRUD])` for every new
  annotation. The V2 import path's `import_annotations` deliberately skips
  this — annotation visibility is computed from doc + corpus, not from
  guardian rows. The fork path's per-row writes are dead work; locked-in
  visibility tests live in `test_import_utils.py`. Consider unifying.
- **`structural_set_map` comment is misleading.** Its comment says
  "duplicated structural_annotation_sets" but the values are the *originals*
  from the source corpus — `add_document` shares them by default. No
  duplication happens unless a caller explicitly overrides the kwarg.
- **`corpus.icon` and `corpus.md_description` are reference-copied, not deep-copied.**
  `LabelSet.icon` is deep-copied (file content rewritten). The asymmetry isn't
  intentional — it's just what falls out of `pk=None; save()` vs explicit
  file-handling. If the source corpus is deleted, the fork's icon /
  md_description files are at risk depending on storage GC rules.
- **DocumentPath lookup uses `corpus.parent_id`, not the original ancestor.**
  For multi-generation forks, the path/folder is inherited from the *immediate*
  parent corpus, not the ur-source. That's fine when paths are stable across
  generations but worth noting if path data drifts.
- **`preferred_embedder` override only exists on the GraphQL path.**
  `build_fork_corpus_task` always inherits the source corpus's embedder.

### Known design tradeoffs

These are deliberate consequences of "fork = V2 export+import" rather than
oddities; they're called out so reviewers don't mistake them for bugs.

- **All source-corpus conversations are inherited regardless of creator.**
  `fork_corpus` calls `build_corpus_v2_zip` with `user_for_visibility=None`,
  meaning every conversation row attached to the source (corpus-level and
  document-level) flows through the export and is reattached to the forked
  corpus. The forking user therefore inherits other users' chat history. This
  is the historical fork contract ("fork = full copy of the source state")
  and the parity test depends on it. If a future requirement demands
  conversation privacy, the right knob is to plumb the forking user through
  `user_for_visibility=`, not to special-case the conversation packager.
- **Storage blobs written by the export/import roundtrip are GC'd on commit.**
  The post-import blob-sharing step rewires `pdf_file`, `pawls_parse_file`,
  `txt_extract_file`, `icon`, and `md_summary_file` on each forked document
  to point at the source corpus's storage paths (so fork doesn't bloat
  storage with duplicate copies). The fresh blobs that the V2 import just
  wrote are collected during the doc loop and deleted via
  `transaction.on_commit(default_storage.delete)`, so the GC only fires once
  the fork transaction is durable — a rollback leaves the V2-import blobs
  intact (they are still the live references on whatever survives). The
  callback is best-effort: per-path `try / except` logs WARNING and
  continues on individual storage failures so one bad path doesn't leak the
  rest. Tracked previously as #1638; see
  `CorpusForkOrphanedBlobGCTest` for behavioural coverage.
- **Single `transaction.atomic()` wraps both export and import.** The export
  step does DB reads + ZIP construction (no writes), the import step does
  DB writes + blob writes. For large corpora the combined critical section
  can hold a write lock for minutes. Splitting export out of the transaction
  would reduce lock contention; the tradeoff is partial-state visibility if
  the import then fails. This is acceptable today because forks of large
  corpora are rare and explicit.

## Future enhancements

### Phase 5 — `Note` cloning

```python
for old_doc_id, new_doc_id in doc_map.items():
    for note in Note.objects.filter(document_id=old_doc_id):
        Note.objects.create(
            document_id=new_doc_id,
            corpus_id=new_corpus_id,
            title=note.title,
            content=note.content,
            page=note.page,
            json=note.json.copy() if note.json else None,
            creator_id=user_id,
        )
```

### Phase 6 — Orphaned-shell cleanup on failure

When `fork_corpus` returns `None` due to an exception, the corpus shell row
remains with `error=True`. A cleanup task should remove the shell and any
partial children produced before the transaction rolled back (though
`transaction.atomic()` should mean there are none).

### Deep-copy `Corpus.icon` and `Corpus.md_description`

Mirror the `LabelSet.icon` pattern — read the file content and rewrite it
under a new storage path so the fork is fully independent of the source's
storage.

### Carry `Category` M2M associations

A small extra step in the fork task after the corpus shell is saved.

### Preferred-embedder override on `build_fork_corpus_task`

Add a `preferred_embedder: str | None = None` parameter to the utility so the
two entry points have feature parity.

## Performance considerations

1. `prefetch_related("source_annotations", "target_annotations")` on relationships avoids N+1 M2M loads.
2. Per-annotation guardian writes are an avoidable ~14 DB ops/annotation (see "Known oddities").
3. Fork runs as a single Celery task to avoid request timeouts; `transaction.atomic()` keeps partial state invisible.
4. Folder cloning relies on `with_tree_fields()` instead of recursive Python — single CTE query.

## Changelog

- **2025-11**: Added manual metadata copying (Fieldset, Columns, Datacells).
- **2025-01**: Added folder + relationship preservation; standardized fork permissions to CRUD; added `prefetch_related` for relationships; corrected tree-ordering to use `with_tree_fields()`.
