# Corpus Export/Import V2.0

## Overview

This document describes the V2 corpus export/import format, which captures the full state of an OpenContracts corpus — including features that were added after the original V1 export was designed.

**Issue**: #502
**Format version marker**: `"version": "2.0"` in `data.json`

## Background

V1 (the original export) only handled basic corpus metadata, documents with PAWLs tokens, user annotations (text and doc labels), and labelsets. Since then the platform grew several first-class features that V1 couldn't represent:

- **Structural annotations** — corpus-isolated copies of parser-emitted structure
- **Conversations / messages** — chat threads against a corpus or document
- **Corpus folders** — hierarchical organization
- **Document versioning** — `DocumentPath` lineage
- **Ingestion sources** — provenance for documents brought in by integrations
- **Post-processors** — export-pipeline customization
- **Agent configuration** — corpus and document agent instructions
- **Markdown descriptions** — CAML-style narrative with revision history
- **Corpus actions & action trail** — recurring/triggered actions and their execution history

V2 captures all of these in a single ZIP that round-trips through import (with a couple of intentional exceptions noted below).

## Design Goals

1. **Backward compatibility** — V1 exports remain importable.
2. **Completeness** — capture everything needed to faithfully reproduce a corpus.
3. **Shareability** — enable publishing annotated datasets.
4. **Efficiency** — deduplicate the heaviest payload (structural annotation sets) across documents.
5. **Flexibility** — opt in to heavier optional content (conversations, action trail).

## Format

### Version Detection

The `version` field in `data.json` tells importers which schema to expect:

- `"version": "1.0"` (or missing) → V1
- `"version": "2.0"` → V2

The same import task handles both — the detection happens internally.

### Top-Level `data.json` Shape

The authoritative TypedDict is `OpenContractsExportDataJsonV2Type` in `opencontractserver/types/dicts.py`. At a high level it carries three groups of fields:

**V1-compatible fields (always present):**

- `version` — format marker (`"2.0"`)
- `annotated_docs` — keyed by document filename → per-document export payload
- `doc_labels`, `text_labels` — label definitions used by the corpus
- `corpus` — corpus metadata (V2-enhanced via `OpenContractCorpusV2Type`)
- `label_set` — the corpus's label set

**V2 mandatory fields:**

- `structural_annotation_sets` — keyed by content hash → per-set payload
- `folders` — corpus folder hierarchy
- `document_paths` — document path / version tree entries
- `relationships` — cross-document and corpus-level annotation relationships
- `agent_config` — corpus/document agent instructions
- `md_description` — current markdown description text
- `md_description_revisions` — full revision history of the markdown description
- `post_processors` — configured post-processor identifiers
- `ingestion_sources` — named integration sources referenced by document paths

**V2 optional fields (gated by export flags):**

- `conversations`, `messages`, `message_votes` — included when `include_conversations=True`
- `action_trail` — included when `include_action_trail=True` (corpus actions, executions, summary stats)

### Per-Document Payload Additions

`OpenContractDocExport` (also in `dicts.py`) gains two V2-only fields:

- `file_type` — MIME type of the source file
- `structural_set_hash` — points at an entry in `structural_annotation_sets`, allowing many documents to share one heavy payload

### Structural Annotation Set Payload

`StructuralAnnotationSetExport` is the heaviest entry. Each set carries the **full payload**, not a reference:

- `content_hash` — the dedup key
- Parser identity (`parser_name`, `parser_version`) and size counters (`page_count`, `token_count`)
- `pawls_file_content` — full PAWLS tokens with bounding boxes
- `txt_content` — full extracted text
- `structural_annotations` — every structural annotation in the set (with label text, raw text, page, annotation JSON, parent reference, annotation type, optional long description)
- `structural_relationships` — relationships between those structural annotations

Documents reference a set by its content hash; the set itself is emitted once per corpus regardless of how many documents use it.

## Implementation

### File Layout

```
opencontractserver/
├── types/
│   └── dicts.py                          # V2 TypedDict definitions
├── utils/
│   ├── packaging.py                      # V1/V2 corpus + labelset (un)packing
│   ├── export_v2.py                      # V2 export helpers
│   ├── import_v2.py                      # V2 import helpers
│   ├── importing.py                      # Shared document/label/annotation import
│   └── etl.py                            # Shared label lookup + per-doc export builder
└── tasks/
    ├── export_tasks.py                   # V1-era export plumbing (finalize, FUNSD, etc.)
    ├── export_tasks_v2.py                # V2 export Celery task
    ├── import_tasks.py                   # V1 import task — now a thin shim
    └── import_tasks_v2.py                # Unified V1/V2 import Celery task
```

### Export Pipeline

The entry point is `package_corpus_export_v2` in `tasks/export_tasks_v2.py`. Parameters:

- `export_id` — `UserExport` row to write into
- `corpus_pk` — corpus to export
- `include_conversations` — opt-in heavy conversation/message/vote payload
- `include_action_trail` — opt-in action history payload
- `action_trail_limit` — cap on action executions exported
- `analysis_pk_list` — optional filter to scope annotations to specific analyses
- `annotation_filter_mode` — how to filter annotations (`CORPUS_LABELSET_ONLY` by default)

It walks active `DocumentPath` rows for the corpus and, for each active document:

1. Builds the V1-compatible per-document export via shared helpers in `utils/etl.py`.
2. If the document has a `StructuralAnnotationSet`, stamps `structural_set_hash` on the doc export and tracks the set for later emission.
3. Writes the source file into the ZIP.

It then emits the rest of the corpus payload using helpers in `utils/export_v2.py`:

- Structural annotation sets (deduplicated by content hash)
- Corpus metadata in V2 form, plus the label set
- Folder hierarchy
- Document paths and ingestion sources
- Cross-document relationships
- Agent configuration
- Markdown description and revision history
- Conversations / messages / votes (when requested)
- Action trail (when requested)

Finally it writes `data.json` to the ZIP and calls `finalize_export` to persist it onto the `UserExport`.

### Import Pipeline

The entry point is `import_corpus_v2` in `tasks/import_tasks_v2.py`. The legacy `import_corpus` task (in `tasks/import_tasks.py`) is now a thin shim that delegates here — so GraphQL mutations that pre-date V2 transparently handle V2 ZIPs.

`import_corpus_v2` opens the ZIP, reads `data.json`, detects the version, and hands off to a single unified `_import_corpus` function that branches on `is_v2`. The order of operations:

1. **Corpus + label setup** (shared with V1) — creates or reuses the seed corpus and its label set; loads/creates labels referenced by the export.
2. **Build a `(text, label_type)` label lookup** — used by structural annotations and relationships, which reference labels by text rather than primary key.
3. **Structural annotation sets** (V2 only) — for each set in the export, look up by `content_hash`; reuse the existing set if found, otherwise create a new one with its PAWLS file, text extract, structural annotations, and structural relationships.
4. **Documents + annotations** (shared) — for each document, create or attach to the corpus via `corpus.add_document()` for proper corpus isolation, then import its annotations. Each call returns an `old_id → new_id` annotation map, aggregated across all documents.
5. **Folders** (V2 only) — sorted by path depth so parents land before children.
6. **Ingestion sources** (V2 only) — `get_or_create` by name. Note that ingestion source `config` is exported as an empty dict (credentials are not shipped); importers must reconfigure.
7. **DocumentPath reconstruction** (V2 only) — uses the document hash (or filename fallback) to bind to the correct corpus document, then updates path, version number, folder assignment, and ingestion lineage on the `DocumentPath` rows already created by `add_document()`. **Only current, non-deleted paths are reconstructed** — historical versions are not recreated because the file content is not part of the export.
8. **Relationships** (V2 only) — uses the aggregated annotation ID map to remap source/target references; relationships whose source or target didn't survive import are silently dropped.
9. **Agent configuration** (V2 only) — corpus / document agent instructions are restored.
10. **Markdown description and revisions** (V2 only) — `oc-import://` placeholder links inside the markdown are rewritten to live IDs using the aggregated annotation map and a strict filename → document map.
11. **Conversations / messages / votes** (V2 only, when present) — restored against the new corpus with a document-hash mapping so message attachments resolve to the right document.

### Structural Annotation Deduplication

`content_hash` is computed during document processing and stored on the `StructuralAnnotationSet` model. On export the same Python object is added to a set, so each unique structural payload appears exactly once in `structural_annotation_sets`. On import, a `filter(content_hash=...).first()` lookup reuses the existing set rather than duplicating it. This is the main reason V2 exports remain manageable even for large corpora where many documents share parsed structure.

### Folder Hierarchy Reconstruction

Each folder is exported with its full path string. On import folders are sorted by path depth so parents are created before children, and a parent-ID map links children to their newly-created parents.

### DocumentPath Version Trees

Only **current, non-deleted** paths are reconstructed. The exporter emits enough metadata to rebuild path, version number, folder assignment, and ingestion lineage, but historical file content is intentionally not shipped — so prior versions in the lineage cannot be materialized from the export alone.

### Relationship ID Remapping

Annotations get new primary keys on import. The unified import keeps an `old_id → new_id` map per document and aggregates it across all documents. Relationships are reconstructed by remapping each source/target ID through this aggregate. Any reference that doesn't map (e.g. its annotation was filtered out at export time) is silently dropped — orphaned relationships do not block the import.

### Optional Conversation Export

Conversations can be large and aren't always wanted in a shared export. They're emitted only when `include_conversations=True`, alongside their messages and message votes. The import side checks for the `conversations` key before doing any work, so older or smaller exports without this section import cleanly.

### Optional Action Trail Export

When `include_action_trail=True`, the export carries a snapshot of corpus actions, their executions, and summary statistics. **Note: the action trail is currently export-only.** It's a write-side diagnostic / audit artifact; the import pipeline does not yet ingest it.

## What's NOT Exported

**Vector embeddings.** Intentionally excluded because:

- They can be regenerated from content.
- They make exports very large.
- Different deployments may use different embedders / dimensions.
- Regenerating on import keeps embeddings consistent with the target system's embedder.

Note that pre-computed embeddings *are* supported for the worker-upload path (`WorkerEmbeddingsType` / `WorkerDocumentUploadMetadataType` in `dicts.py`). That's a different ingestion surface than corpus export/import.

**Ingestion source credentials.** Ingestion source `config` is always exported as an empty dict because it may contain secrets. Importers must reconfigure sources after import.

**Per-object permissions.** Imported objects are granted permissions to the importing user; per-user grants from the source system are not preserved.

**Action trail on import.** The action trail can be emitted at export time but is not currently imported.

## Backward Compatibility

### V1 Imports Still Work

The legacy `import_corpus` Celery task is now a one-line shim that calls `import_corpus_v2`. Version detection happens inside the unified `_import_corpus` function, which conditionally enables V2 steps based on the detected format. V1 ZIPs flow through the same code path; the V2-only steps are skipped.

### V1 Exports Remain Valid

V1 fields are preserved unchanged in V2:

- The V1 sub-shape is a subset of `OpenContractsExportDataJsonV2Type`.
- New V2 fields are added without renaming or repurposing V1 fields.
- The unified importer handles missing V2 fields gracefully via `.get(..., default)`.

## GraphQL Integration

### Export

The existing `StartCorpusExport` mutation accepts an `export_format` argument. When the value is `OPEN_CONTRACTS_V2`, the mutation dispatches `package_corpus_export_v2` with the appropriate flags (`include_conversations`, `include_action_trail`, `analysis_pk_list`, `annotation_filter_mode`). No separate V2 export mutation exists — and none is needed.

### Import

The existing `UploadCorpusImportZip` mutation calls the V1 `import_corpus` task, which now delegates to `import_corpus_v2`. V2 ZIPs therefore import correctly through the unchanged mutation — version detection happens transparently inside the task. There is no separate V2 import mutation.

## Usage

### Export V2 Corpus (programmatic)

```python
from opencontractserver.tasks.export_tasks_v2 import package_corpus_export_v2
from opencontractserver.users.models import UserExport

export = UserExport.objects.create(creator=user, backend_lock=True)

package_corpus_export_v2.delay(
    export_id=export.id,
    corpus_pk=corpus.id,
    include_conversations=True,
    include_action_trail=False,
)
```

### Import V2 Corpus (programmatic)

```python
from opencontractserver.corpuses.models import TemporaryFileHandle
from opencontractserver.tasks.import_tasks_v2 import import_corpus_v2

temp_file = TemporaryFileHandle.objects.create()
temp_file.file.save("corpus_export.zip", uploaded_file)

import_corpus_v2.delay(
    temporary_file_handle_id=temp_file.id,
    user_id=user.id,
    seed_corpus_id=None,  # or an existing corpus ID to merge into
)
```

## Testing

V2 export/import has a dedicated test suite in `opencontractserver/tests/test_corpus_export_import_v2.py`. Additional typing-focused tests live alongside it (e.g. `test_export_tasks_typing_fixes.py`, `test_import_tasks_v2_typing_coverage.py`). When extending the format, prefer adding round-trip integration tests that verify both write-side correctness (TypedDict shape, dedup) and read-side correctness (ID remapping, hierarchy reconstruction).

## Performance Notes

- **Structural annotation sets** dominate export size; dedup by `content_hash` is the main lever.
- **Conversations** can be large; keep them opt-in.
- **ZIP writes** stream into an in-memory `BytesIO`; for very large corpora this could become a memory pressure point and is a candidate for future incremental writing.
- **Import** uses `corpus.add_document()` for each document, which handles corpus isolation but is per-document; bulk-creates are used where shape allows (annotations, label maps).

## Known Caveats / Drift Watchpoints

These are the spots most likely to surprise someone reading code against this document:

- **Unified import handler.** Both V1 and V2 flow through one `_import_corpus(version, ...)` function rather than separate handlers.
- **`import_corpus` is a shim.** The V1 task forwards to `import_corpus_v2`. Don't add logic to `import_corpus.py` — extend `import_tasks_v2.py` and `utils/import_v2.py`.
- **Action trail is export-only.** Exporting it works; importing it is not implemented.
- **DocumentPath history is partial.** Only current, non-deleted paths round-trip.
- **Ingestion source configs are empty.** Credentials are intentionally stripped on export.

## Future Enhancements

1. **Selective export** — export a subset of documents or folders.
2. **Incremental export** — emit only deltas since a previous export.
3. **Action trail import** — round-trip the optional action history.
4. **Streaming ZIP writes** — avoid holding the whole archive in memory.
5. **Optional encryption** — for sensitive corpora.
6. **Direct cloud delivery** — push the archive straight to S3/GCS without a local materialization.

## Summary

V2 export/import provides:

- **Complete** — captures all first-class corpus state (with the documented exceptions).
- **Backward compatible** — V1 ZIPs still import via the unified handler.
- **Efficient** — heavy structural payloads dedup by content hash.
- **Flexible** — heavy optional content (conversations, action trail) is opt-in.
- **GraphQL-ready** — both the export mutation and the import mutation already speak V2 with no client changes.

This enables reliable backup/restore and dataset sharing across OpenContracts deployments.
