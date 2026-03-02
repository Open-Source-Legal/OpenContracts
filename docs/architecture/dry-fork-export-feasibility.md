# Feasibility Analysis: DRY Up Forking and Export Logic (Issue #816)

## Executive Summary

**Feasibility: HIGH — with significant architectural considerations.**

The forking and export codepaths share the same conceptual pipeline (select objects → collect/transform → write to destination) but diverge substantially in their **output format**, **object handling strategy**, and **data scope**. A unified pipeline is achievable and would reduce maintenance burden, but requires careful design to avoid premature abstraction. This document maps the duplication, identifies shared patterns, and proposes a concrete refactoring approach.

---

## 1. Current Architecture Overview

### Three Operations, One Conceptual Flow

| Operation | Input | Processing | Output |
|-----------|-------|------------|--------|
| **Fork** | Corpus PK + User | Clone DB objects with ID remapping | New Corpus (DB rows) |
| **Export** | Corpus PK + Format + Filters | Serialize objects to JSON/files | ZIP file (data.json + PDFs) |
| **Import** | ZIP file + User | Deserialize JSON → create DB objects | New Corpus (DB rows) |

### File Inventory

| Component | Fork Files | Export Files | Import Files |
|-----------|-----------|-------------|-------------|
| **GraphQL Mutation** | `config/graphql/corpus_mutations.py` (StartCorpusFork) | `config/graphql/document_mutations.py` (StartCorpusExport) | `config/graphql/document_mutations.py` (UploadCorpusImportZip) |
| **Celery Task** | `tasks/fork_tasks.py` | `tasks/export_tasks.py`, `tasks/export_tasks_v2.py` | `tasks/import_tasks.py`, `tasks/import_tasks_v2.py` |
| **Utilities** | `utils/corpus_forking.py` | `utils/etl.py`, `utils/export_v2.py`, `utils/packaging.py` | `utils/importing.py`, `utils/import_v2.py`, `utils/packaging.py` |

---

## 2. Detailed Duplication Analysis

### 2.1 Object Selection (HIGH duplication)

Both fork and export must identify the same set of objects to operate on. This logic is duplicated across three locations:

**Fork mutation** (`corpus_mutations.py:481-528`) and **Fork utility** (`corpus_forking.py:31-78`):
```python
# Duplicated between StartCorpusFork.mutate() and build_fork_corpus_task()
annotation_ids = list(Annotation.objects.filter(corpus_id=corpus_pk, analysis__isnull=True).values_list("id", flat=True))
doc_ids = list(corpus.get_documents().values_list("id", flat=True))
folder_ids = list(CorpusFolder.objects.filter(corpus_id=corpus_pk).with_tree_fields().values_list("id", flat=True))
relationship_ids = list(Relationship.objects.filter(corpus_id=corpus_pk, analysis__isnull=True).values_list("id", flat=True))
metadata_column_ids = list(corpus.metadata_schema.columns.filter(is_manual_entry=True).values_list("id", flat=True))
```

**Export V2 task** (`export_tasks_v2.py:90-94`):
```python
active_doc_paths = DocumentPath.objects.filter(corpus=corpus, is_current=True, is_deleted=False).select_related("document")
document_ids = [dp.document_id for dp in active_doc_paths]
```

**Key difference**: Fork collects *IDs* for all entity types upfront (passed as Celery args), while export queries objects inline during processing. Fork also explicitly filters to `analysis__isnull=True` (user-created only), while export uses the `AnnotationFilterMode` system which can include analysis-generated annotations.

### 2.2 Label/LabelSet Handling (MODERATE duplication)

**Fork** (`fork_tasks.py:71-148`): Clones LabelSet and AnnotationLabel objects one-by-one, maintaining an `old_id → new_id` map.

**Export** (`packaging.py`): Serializes labels to JSON via `package_label_set_for_export()`.

**Import** (`importing.py`): Creates labels from JSON via `load_or_create_labels()` and `prepare_import_labels()`.

The fork's label cloning is semantically identical to export-then-import but skips the JSON intermediate format. The operations are:
- Fork: `DB → clone → DB` (direct)
- Export+Import: `DB → JSON → DB` (serialized)

### 2.3 Folder Hierarchy (MODERATE duplication)

**Fork** (`fork_tasks.py:220-253`): Iterates folders in tree order, clones each with remapped `parent_id`.

**Export** (`export_v2.py:125-176`): Serializes folders with path and parent_id references.

**Import** (`import_v2.py`): Reconstructs folder hierarchy from serialized data via `import_corpus_folders()`.

Same pattern: fork does `DB → clone → DB`, export/import does `DB → JSON → DB`.

### 2.4 Document Handling (LOW direct duplication, HIGH conceptual overlap)

**Fork** (`fork_tasks.py:262-333`): Uses `corpus.add_document()` which creates a corpus-isolated copy sharing file blobs. Maintains `doc_map` for annotation remapping. Handles structural_annotation_set reuse.

**Export** (`etl.py`, `export_tasks_v2.py`): Calls `build_document_export()` per document which reads files, base64-encodes PDFs, extracts annotation data. Writes to ZIP.

**Import** (`importing.py:275-328`): Creates Document from file handle, calls `corpus.add_document()`, then imports annotations.

The fork and import both use `corpus.add_document()` — this is already a shared primitive. Export is fundamentally different (serialization vs. cloning).

### 2.5 Annotation Handling (MODERATE duplication)

**Fork** (`fork_tasks.py:338-396`): Clones annotations with `pk=None` trick, remaps `document_id`, `corpus_id`, `annotation_label_id`.

**Export** (`etl.py`): Serializes annotations to JSON dicts with bounding boxes and label references.

**Import** (`importing.py:68-160`): Creates annotations from JSON with two-pass approach (create, then set parents).

Fork's annotation cloning is simpler than import because it doesn't need to handle parent relationships or image extraction — the cloned annotations already have correct structure.

### 2.6 Relationship Handling (MODERATE duplication)

**Fork** (`fork_tasks.py:450-529`): Clones relationships with M2M annotation remapping using `annotation_map`.

**Export** (`export_v2.py:240-284`): Serializes relationships with annotation ID references.

**Import** (`import_tasks_v2.py:354-404`): Creates relationships from JSON, remaps annotation IDs.

Both fork and import maintain an `annotation_id_map` and perform the same M2M remapping logic.

### 2.7 Metadata Schema/Datacells (Fork-only, no export equivalent)

Fork clones Fieldset, Columns, and Datacells (`fork_tasks.py:152-448`). Export V2 does **not** export metadata schema. This is fork-specific functionality with no duplication.

### 2.8 ID Mapping Pattern (HIGH conceptual duplication)

All three operations maintain parallel ID mapping dictionaries:

```python
# Fork
label_map = {}        # old_label_id → new_label_id
doc_map = {}          # old_doc_id → new_doc_id
folder_map = {}       # old_folder_id → new_folder_id
annotation_map = {}   # old_annotation_id → new_annotation_id
column_map = {}       # old_column_id → new_column_id

# Import
label_lookup = {}           # label_name → AnnotationLabel
doc_hash_to_corpus_doc = {} # hash → Document
all_annot_id_maps = {}      # old_id → new_pk
```

---

## 3. Duplication Between Fork Mutation and Fork Utility

There is a **near-complete duplication** of the object selection logic between:

1. `config/graphql/corpus_mutations.py` lines 481-528 (`StartCorpusFork.mutate()`)
2. `opencontractserver/utils/corpus_forking.py` lines 31-78 (`build_fork_corpus_task()`)

Both collect the exact same IDs (annotations, documents, folders, relationships, metadata columns, metadata datacells) with identical queries. The mutation also duplicates the corpus shell creation logic (lines 530-555) that exists in the utility (lines 80-96).

**This is the lowest-hanging fruit for DRY improvement** — the mutation should simply call `build_fork_corpus_task()` instead of duplicating its logic.

---

## 4. Feasibility Assessment

### What CAN be unified (High ROI)

| Component | Approach | Effort | Impact |
|-----------|----------|--------|--------|
| **Object Selection** | Extract a `CorpusObjectCollector` that returns all entity IDs/querysets for a corpus | Small | Eliminates 3-way duplication of selection queries |
| **Fork Mutation ↔ Fork Utility** | Mutation calls utility directly instead of duplicating | Trivial | Removes ~50 lines of exact duplication |
| **ID Mapping Infrastructure** | Shared `IDRemapper` class used by both fork and import | Small | Standardizes the mapping pattern |
| **Folder Hierarchy Cloning** | Shared `clone_folder_hierarchy(source_corpus, target_corpus, user)` | Small | Used by fork; importable by import with adapter |

### What SHOULD NOT be unified (Low ROI / High Risk)

| Component | Reason |
|-----------|--------|
| **Document handling** | Fork uses `corpus.add_document()` (blob sharing), export serializes to base64/ZIP. Fundamentally different operations. |
| **Export serialization** | The `build_document_export()` + ZIP packaging is export-specific. Forcing fork through JSON serialization would add overhead and complexity with no benefit. |
| **Annotation filtering** | Export supports `AnnotationFilterMode` (corpus-only, plus-analyses, analyses-only). Fork always uses user-created-only. Merging these would add unnecessary complexity to fork. |
| **Post-processor pipeline** | Export-only feature. No fork equivalent needed. |
| **V2-specific exports** | Conversations, action trail, md_description — these are export-only features with no fork equivalent. |

### What COULD be unified (Medium ROI, worth evaluating)

| Component | Approach | Consideration |
|-----------|----------|---------------|
| **Label cloning** | `clone_labels(source_labelset, user) → (new_labelset, label_map)` | Used by fork. Import creates from JSON, so different input format. Could share output shape. |
| **Relationship cloning** | `clone_relationships(relationship_ids, annotation_map, doc_map, user, corpus)` | Fork and import both do annotation M2M remapping. Import has slightly different input (JSON vs queryset). |
| **Import as "fork from JSON"** | Restructure import to: deserialize JSON → temporary objects → run fork-like cloning | Technically possible but adds complexity. The current import code is already well-factored with shared helpers. |

---

## 5. Proposed Refactoring Strategy

### Phase 1: Quick Wins (Estimated: 1-2 days)

1. **Deduplicate fork mutation ↔ fork utility**: Make `StartCorpusFork.mutate()` call `build_fork_corpus_task()` instead of duplicating the ID collection and corpus shell creation logic. This removes ~50 lines of exact duplication.

2. **Extract `collect_corpus_object_ids(corpus, user_annotations_only=True)`**: A utility function that returns a typed dict of all entity IDs for a corpus. Used by both fork and export.

### Phase 2: Shared Primitives (Estimated: 2-3 days)

3. **Extract `clone_label_set(source_labelset, user) → (new_labelset, label_map)`**: Shared function for label set cloning with ID mapping. Fork uses directly; import could use after creating labels from JSON.

4. **Extract `clone_folder_hierarchy(folders_qs, target_corpus, user) → folder_map`**: Shared folder cloning with parent remapping.

5. **Extract `clone_relationships(relationships_qs, annotation_map, doc_map, user, corpus) → list[Relationship]`**: Shared M2M relationship remapping.

### Phase 3: Pipeline Architecture (Estimated: 3-5 days, optional)

6. **Define a `CorpusTransferPipeline` protocol**: A three-stage pipeline as the issue suggests:
   - **Stage 1: Select** — `collect_corpus_object_ids()` (shared)
   - **Stage 2: Retrieve** — Permission-filtered querysets (shared)
   - **Stage 3: Write** — Pluggable backends:
     - `DatabaseWriter` (fork): clones objects directly
     - `ZipWriter` (export): serializes to ZIP
     - `DatabaseReader` (import): reads from ZIP, creates objects

   This is the most ambitious option. It would provide the cleanest architecture but requires careful design of the protocol to avoid leaky abstractions. The key challenge is that fork operates on querysets/IDs while export operates on serialized representations.

---

## 6. Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Breaking fork data integrity | Medium | High | Extensive existing test suites (`test_corpus_fork_round_trip.py`) provide safety net |
| Breaking export format compatibility | Low | High | Export validation (`validate_export.py`) catches format regressions |
| Performance regression in fork | Low | Medium | Fork is already DB-bound; shared utilities won't add meaningful overhead |
| Over-abstraction making code harder to understand | Medium | Medium | Limit Phase 3 to only what's clearly beneficial. Prefer explicit duplication over wrong abstraction |
| Test suite disruption | Medium | Medium | CLAUDE.md rule: don't touch old tests without permission. New shared utilities need their own tests |

---

## 7. Recommendation

**Start with Phase 1 and Phase 2.** These deliver the most value with the least risk:

- Phase 1 eliminates the most egregious duplication (fork mutation vs. utility) and is trivially safe.
- Phase 2 creates reusable primitives that reduce the fork task from ~510 lines to ~200 lines while making each operation independently testable.

**Defer Phase 3** until after Phases 1-2 are stable. The pipeline architecture is elegant but the current code isn't duplicated enough to justify the abstraction cost. Fork, export, and import have genuinely different requirements (filtering modes, serialization formats, permission models) that a unified pipeline would need to accommodate, risking a leaky abstraction.

**Do NOT attempt to make import a "fork from JSON."** The import code is already well-factored with shared helpers (`create_document_from_export_data`, `import_doc_annotations`, `import_annotations`). Forcing it through a fork-like pipeline would add indirection without reducing complexity.

---

## 8. Lines of Code Impact (Estimated)

| Phase | Lines Removed | Lines Added | Net Change |
|-------|--------------|-------------|------------|
| Phase 1 | ~80 | ~20 | -60 |
| Phase 2 | ~200 | ~150 | -50 |
| Phase 3 | ~300 | ~250 | -50 |
| **Total** | **~580** | **~420** | **-160** |

The primary benefit isn't LOC reduction — it's consolidating the ID-collection and cloning logic into single, well-tested functions instead of maintaining parallel implementations.
