# Service Layer Centralization — Phase 3 Implementation Plan

**Goal:** Split the 1,507-line `opencontractserver/annotations/query_optimizer.py`
monolith and relocate the misfiled optimizer classes into per-app `services/`
packages, completing issue #1717.

**Architecture:** Phase 3 of the roadmap in
`docs/refactor_plans/2026-05-19-service-layer-centralization-design.md` (§6),
building on the Phase 1 `BaseService` foundation (#1715). The
`annotations/query_optimizer.py` file hosts four classes — two of which
(`Analysis`, `Extract`) are not annotation concerns and are misfiled. Each
class moves into its correct app's `services/` package, is renamed from
`*QueryOptimizer` to `*Service`, and inherits `BaseService`. `query_optimizer`
stops being a public concept for these five classes (design doc §9).

**Tech stack:** Python 3.12, Django 4.x, the `shared/services/` foundation
(`BaseService`, `ServiceResult`) from Phase 1.

---

## Background

`annotations/query_optimizer.py` (1,507 lines) hosts:

| Class | Lines | Correct app |
|-------|-------|-------------|
| `AnnotationQueryOptimizer` | 27–817 | `annotations` |
| `RelationshipQueryOptimizer` | 820–1093 | `annotations` |
| `AnalysisQueryOptimizer` | 1096–1302 | `analyzer` (misfiled) |
| `ExtractQueryOptimizer` | 1305–1507 | `extracts` (misfiled) |

`extracts/query_optimizer.py` (582 lines) hosts `MetadataQueryOptimizer`
(lines 19–582).

Key facts verified during planning:

- **No shim.** Phase 2 kept a re-export shim because of its huge blast radius
  (~37 callers). Phase 3 is smaller (~13 production callers) and the design
  doc §9 success criterion — *"the term 'query optimizer' no longer appears as
  a public API concept"* — forbids a `query_optimizer.py` shim. Both
  `query_optimizer.py` files are deleted; every caller is migrated.
- **`mypy_baseline.txt` is advisory** (`docs/typing/README.md`): mypy does not
  consume it. The real gate is `mypy.ini`'s per-module `[mypy-…]` sections.
  Neither `annotations.query_optimizer` nor `extracts.query_optimizer` has a
  section — they are actively type-checked and clean, so the relocated code
  must also be mypy-clean. The new service modules are not in `mypy.ini`, so
  mypy checks them from scratch.
- **Relocate, do not rewrite.** Method bodies move byte-for-byte. The only
  per-method change: `RelationshipService` references `AnnotationService`
  (was `AnnotationQueryOptimizer`) for the shared `_compute_effective_permissions`
  / `_get_document_for_request` helpers. The `context=` request-threading
  kwarg is preserved (renaming it to `request=` is a Phase-4 concern).
- **Classmethod style preserved.** The optimizers are `@classmethod`-based;
  `BaseService` adds `@staticmethod` helpers with disjoint names — inheriting
  it is behaviour-neutral.
- **Pre-existing latent bug, untouched.** `performance_optimizations/test_base.py`
  calls `AnnotationQueryOptimizer.clear_permission_caches()` — a method that
  has never existed — inside `new_context()`, which is itself never called.
  This is relocated faithfully (rename only); fixing it is out of scope.

---

## File structure

**Create (new service packages):**

- `opencontractserver/annotations/services/__init__.py` — re-exports
  `AnnotationService`, `RelationshipService`.
- `opencontractserver/annotations/services/annotation_service.py` —
  `AnnotationService` (from `AnnotationQueryOptimizer`).
- `opencontractserver/annotations/services/relationship_service.py` —
  `RelationshipService` (from `RelationshipQueryOptimizer`).
- `opencontractserver/analyzer/services/__init__.py` — re-exports
  `AnalysisService`.
- `opencontractserver/analyzer/services/analysis_service.py` —
  `AnalysisService` (from `AnalysisQueryOptimizer`).
- `opencontractserver/extracts/services/__init__.py` — re-exports
  `ExtractService`, `MetadataService`.
- `opencontractserver/extracts/services/extract_service.py` —
  `ExtractService` (from `ExtractQueryOptimizer`).
- `opencontractserver/extracts/services/metadata.py` — `MetadataService`
  (from `MetadataQueryOptimizer`).
- `opencontractserver/tests/test_service_packages_phase3.py` — new
  structural-contract test.

**Delete:**

- `opencontractserver/annotations/query_optimizer.py`
- `opencontractserver/extracts/query_optimizer.py`

**Modify — production call sites (12 files):** `config/graphql/`
{`extract_queries`, `extract_mutations`, `corpus_queries`, `extract_types`,
`annotation_queries`, `corpus_types`, `custom_resolvers`, `document_types`}`.py`;
`opencontractserver/mcp/`{`resources`, `tools`}`.py`;
`opencontractserver/shared/Managers.py`;
`opencontractserver/documents/query_optimizer.py` (import paths only — this
file's own split is Phase 4).

**Modify — comment/docstring-only references:**
`config/graphql/`{`annotation_types`, `user_types`, `document_queries`}`.py`;
`opencontractserver/shared/QuerySets.py`; `opencontractserver/utils/importing.py`;
`opencontractserver/extracts/diff.py`.

**Modify — tests (imports + class names only, zero scenario changes):**
`opencontractserver/tests/` {`test_query_optimizer_structural_sets`,
`test_corpus_annotations_query`, `test_annotation_privacy`,
`test_get_document_knowledge_optimizations`, `test_analysis_annotation_import`,
`test_visibility_managers`, `test_structural_annotations_graphql_backwards_compat`}`.py`;
`opencontractserver/tests/permissioning/` {`test_query_optimizer_methods`,
`test_metadata_query_optimizer`, `test_version_aware_query_optimizer`,
`test_comment_permission`}`.py`;
`opencontractserver/tests/performance_optimizations/test_base.py`;
comment-only: `test_import_utils.py`, `test_extract_iterations.py`.

**Modify — docs/meta:** `docs/typing/mypy_baseline.txt` (rename the two
`test_base.py` advisory entries' class name), `docs/architecture/query_permission_patterns.md`
(Layer-2 table rows for the five moved classes), `CHANGELOG.md`.

The class→module mapping:

| Was | Now |
|-----|-----|
| `AnnotationQueryOptimizer` (`annotations.query_optimizer`) | `AnnotationService` (`annotations.services`) |
| `RelationshipQueryOptimizer` (`annotations.query_optimizer`) | `RelationshipService` (`annotations.services`) |
| `AnalysisQueryOptimizer` (`annotations.query_optimizer`) | `AnalysisService` (`analyzer.services`) |
| `ExtractQueryOptimizer` (`annotations.query_optimizer`) | `ExtractService` (`extracts.services`) |
| `MetadataQueryOptimizer` (`extracts.query_optimizer`) | `MetadataService` (`extracts.services`) |

---

## Tasks

### Task 1 — Create the three `services/` packages

- [ ] Create the five service modules by relocating each class body
      byte-for-byte; replace the module header (docstring + imports), rename
      the class to `*Service`, and make it inherit `BaseService`.
- [ ] `relationship_service.py` imports `AnnotationService` and repoints its
      three `AnnotationQueryOptimizer.*` references.
- [ ] Create the three `__init__.py` files re-exporting the public services.
- [ ] `py_compile` every new module.

### Task 2 — Migrate production call sites

- [ ] Repoint all 12 functional call-site files at the new import paths /
      class names. Imports that pulled multiple now-differently-housed classes
      from one statement are split per owning package.
- [ ] Update comment/docstring-only references for accuracy.

### Task 3 — Migrate tests

- [ ] Repoint every optimizer test's imports + class references. **Zero**
      scenario/assertion changes — these tests are the behavioural regression
      gate (issue #1717).
- [ ] Add `test_service_packages_phase3.py` — structural contract:
  - the five services import from their package `__init__`;
  - each inherits `BaseService`;
  - `annotations.query_optimizer` / `extracts.query_optimizer` no longer
    import (proves the no-shim deletion);
  - the public `get_*` / `check_*` / `validate_*` methods are present.

### Task 4 — Delete the monoliths + housekeeping

- [ ] Delete both `query_optimizer.py` files.
- [ ] Update `docs/architecture/query_permission_patterns.md` Layer-2 table.
- [ ] Update the two advisory `mypy_baseline.txt` lines (class rename only).
- [ ] Add the `CHANGELOG.md` entry.

### Task 5 — Verify

- [ ] `grep` confirms zero residual references to the five old class names
      and the two old module paths.
- [ ] `pre-commit` (black, isort, flake8, pyupgrade, mypy) clean — mypy is the
      safety net for deferred-import path correctness across all call sites.
- [ ] Run the optimizer regression suite + the new structural test in Docker.

---

## Testing strategy

The existing optimizer test modules (`test_query_optimizer_methods.py`,
`test_metadata_query_optimizer.py`, `test_version_aware_query_optimizer.py`,
`test_query_optimizer_structural_sets.py`, `test_annotation_privacy.py`,
`test_comment_permission.py`, `test_get_document_knowledge_optimizations.py`,
`test_corpus_annotations_query.py`, `test_analysis_annotation_import.py`,
`test_visibility_managers.py`, `test_structural_annotations_graphql_backwards_compat.py`)
are the behavioural regression gate — they run unchanged except for the
mechanical import/class-name repoint. `test_service_packages_phase3.py` covers
the new structural contract. mypy (which type-checks function-local imports)
verifies every migrated call site resolves.

## Risks

- **Missed reference → `ImportError` at resolver runtime.** Mitigated by an
  exhaustive post-edit `grep` and by mypy checking deferred imports.
- **Relocation drift.** Mitigated by byte-for-byte body moves (`sed` range
  extraction) and the unchanged regression suite.
- **Circular imports.** `annotation_service.py` imports only `shared.services`
  + stdlib + Django; `relationship_service.py` imports `annotation_service`
  (one-directional). All call-site imports stay function-local.
