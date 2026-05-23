# Service Layer Centralization — Phase 2 (Split the `CorpusObjsService` monolith) Implementation Plan

**Status:** Phase A shipped by the linked PR. Phases B and C are implemented —
see `docs/refactor_plans/2026-05-22-service-layer-phase2bc-corpus-service-and-caller-migration.md`
for their detailed plan.
**Date:** 2026-05-21
**Tracking issue:** #1716
**Depends on:** Phase 1 (#1715 — `BaseService` foundation, merged)

## 1. Goal

Convert the ~2,900-line `opencontractserver/corpuses/corpus_objs_service.py`
monolith — which holds six distinct responsibilities in a single
`CorpusObjsService` class — into a segmented `opencontractserver/corpuses/services/`
package, one cohesive module per responsibility, each service inheriting the
Phase 1 `BaseService`.

This is Phase 2 of the roadmap in
`docs/refactor_plans/2026-05-19-service-layer-centralization-design.md` (§6).
Read that design doc first — §3 (Problem 1, "Monolith files") and §5.2
(per-app package layout) define what this phase builds.

## 2. The change sequence

Issue #1716's full scope (segment the monolith, add a new `corpus_service.py`
for Corpus-row CRUD, ship a re-export shim, then delete the shim) is too large
for one safe, reviewable change. It is delivered as a three-phase sequence,
each independently shippable and each leaving the tree green:

| Phase | Deliverable | Risk | Touches |
|-------|-------------|------|---------|
| **A** | Split the monolith into the `corpuses/services/` package (`folders`, `folder_documents`, `corpus_documents`, `lifecycle`, `paths`); keep `corpus_objs_service.py` as a thin re-export shim with a backward-compatible `CorpusObjsService` facade. | Low — pure relocation, no behaviour change, no call site touched. | `corpuses/` only |
| **B** | Add `corpus_service.py` for **Corpus-row CRUD** (`create` / `update` / `delete` / visibility), migrating the logic currently inline in `config/graphql/corpus_mutations.py` (`CreateCorpusMutation`, `UpdateCorpusMutation`, `UpdateCorpusDescription`, `DeleteCorpusMutation`, `SetCorpusVisibility`). | Medium — moves logic out of GraphQL mutations. | `corpuses/`, `config/graphql/corpus_mutations.py` |
| **C** | Migrate the ~37 caller files off the `CorpusObjsService` facade onto the segmented services; delete the `corpus_objs_service.py` shim (no-dead-code rule). | Medium — wide but mechanical. | `config/graphql/`, `mcp/`, `llms/`, `tasks/`, `discovery/`, tests |

**This PR implements Phase A only.** Phases B and C are scoped here for
continuity and will be delivered as follow-up PRs against #1716.

## 3. Phase A — detailed design (this PR)

### 3.1 Target package layout

```
opencontractserver/corpuses/
  corpus_objs_service.py       # was 2,920 lines — now a ~75-line shim
  services/
    __init__.py                # re-exports the five services
    paths.py                   # CorpusPathService(BaseService)
    corpus_documents.py        # CorpusDocumentService(BaseService)
    lifecycle.py               # DocumentLifecycleService(BaseService)
    folders.py                 # FolderCRUDService(BaseService)
    folder_documents.py        # FolderDocumentService(BaseService)
```

### 3.2 Method → module mapping

All 40 methods of the former `CorpusObjsService` are relocated, byte-for-byte,
into exactly one of the five services. Method order within each module
preserves the monolith's logical grouping.

**`paths.py` — `CorpusPathService`** (6 methods — `DocumentPath`
disambiguation internals; all private; no permission checks):
`_compute_moved_path`, `_target_directory_string_from_path`,
`_dispatch_document_path_created_signals`, `_fetch_occupied_paths_in_directory`,
`_disambiguate_path`, `_create_successor_path_with_retry`.

**`corpus_documents.py` — `CorpusDocumentService`** (13 methods —
document-in-corpus reads / writes + membership):
`_check_document_in_corpus`, `_build_corpus_documents_queryset`,
`get_corpus_documents`, `get_corpus_documents_visible_to_user`,
`get_corpus_document_by_slug`, `get_corpus_document_by_id`,
`is_document_in_corpus`, `get_corpus_caml_articles`,
`upload_document_to_corpus`, `add_document_to_corpus`,
`add_documents_to_corpus`, `remove_document_from_corpus`,
`remove_documents_from_corpus`.

**`lifecycle.py` — `DocumentLifecycleService`** (5 methods — soft-delete /
restore / trash): `get_deleted_documents`, `soft_delete_document`,
`restore_document`, `permanently_delete_document`, `empty_trash`.

**`folders.py` — `FolderCRUDService`** (10 methods — folder CRUD + the folder
tree + search + bulk structure creation): `get_visible_folders`,
`get_folder_by_id`, `get_folder_tree`, `create_folder`, `update_folder`,
`move_folder`, `delete_folder`, `get_folder_path`, `search_folders`,
`create_folder_structure_from_paths`.

**`folder_documents.py` — `FolderDocumentService`** (6 methods —
document-in-folder placement, listing, and counts): `get_folder_documents`,
`get_folder_document_ids`, `get_folder_document_count`,
`move_document_to_folder`, `move_documents_to_folder`, `get_document_folder`.

### 3.3 Cross-module reference strategy

The monolith used `cls.<helper>` for every internal call because every method
lived on one class. After the split, calls fall into two categories:

- **Within-module** calls keep `cls.<method>` — they still resolve through the
  service's own MRO (e.g. `get_folder_tree` → `cls.get_visible_folders`,
  `get_corpus_document_by_id` → `cls.get_corpus_documents`).
- **Cross-module** calls are rewritten to an **explicit service-class
  reference** — `FolderCRUDService` / `FolderDocumentService` /
  `DocumentLifecycleService` call `CorpusPathService._disambiguate_path(...)`
  and `CorpusDocumentService._check_document_in_corpus(...)` directly.

Exactly **14 call sites** are rewritten, spread across `folders.py`,
`folder_documents.py`, and `lifecycle.py`; every other line of every method
body is identical to the monolith. Explicit references were chosen over
`cls.`-via-inheritance so each service is a flat `BaseService` subclass
(matching design doc §5.2), method behaviour is independent of the entry
point (facade vs standalone), and a reader can see exactly which service owns
each helper.

### 3.4 The `CorpusObjsService` facade

`corpus_objs_service.py` becomes a thin shim that re-exports the five services
and defines a deprecated facade:

```python
class CorpusObjsService(
    FolderCRUDService, FolderDocumentService, CorpusDocumentService,
    DocumentLifecycleService, CorpusPathService,
):
    pass
```

Because the five services are flat `BaseService` subclasses with **disjoint
method names**, the C3 linearisation is unambiguous and every one of the 40
methods remains callable as `CorpusObjsService.<method>`. This keeps all ~37
existing caller files and all 290+ tests in `test_corpus_objs_service.py`
working with no call-site change. The facade adds no methods and overrides
nothing — it is a pure aggregation point, and it is deleted with the shim in
Phase C.

### 3.5 Test handling

`test_corpus_objs_service.py` (5,324 lines, ~290 tests) is the behavioural
regression net for the relocation and continues to exercise every method
through the `CorpusObjsService` facade. Its test scenarios, fixtures, and
assertions are **unchanged**. The only edits are **9 `@patch` / `patch.object`
target relocations** that follow moved symbols (the "new imports" the issue
anticipates) plus one new import:

- `@patch("…corpus_objs_service.post_save")` → `@patch("…services.paths.post_save")`
  (×2) — `post_save` is referenced by `_dispatch_document_path_created_signals`,
  now in `paths.py`.
- `patch.object(CorpusObjsService, "_disambiguate_path", …)` →
  `patch.object(CorpusPathService, "_disambiguate_path", …)` (×7) — the folder
  write operations now call `CorpusPathService._disambiguate_path` explicitly,
  so the mock must target the owning service.

A new structural test module — `test_corpus_services_package.py` — covers the
Phase A contract that the regression suite does not: package layout,
`BaseService` inheritance, the facade's MRO / method aggregation, standalone
operation of each segmented service, and cross-service delegation.

### 3.6 Deliberately NOT done in Phase A

- **No behaviour change.** Method bodies are relocated verbatim; permission
  checks, transaction boundaries, query shapes, and logging are untouched. An
  automated faithfulness check confirms every relocated method body is
  byte-identical to the monolith (modulo the 14 documented rewrites).
- **No `BaseService` helper adoption.** Services inherit `BaseService` (so the
  `get_or_none` / `filter_visible` / `require_permission` / `log_action`
  helpers are available) but the relocated methods keep their existing inline
  `corpus.user_can(...)` checks and `(obj, error)` tuple returns. Re-expressing
  them in terms of `BaseService` / `ServiceResult` is a behaviour-adjacent
  change deferred to a later phase.
- **No caller migration.** All callers keep using `CorpusObjsService` via the
  shim (Phase C migrates them).

## 4. Phase B — outline (follow-up)

Add `corpuses/services/corpus_service.py` — `CorpusService(BaseService)` —
owning **Corpus-row** CRUD: create, update, delete, and visibility changes
currently implemented inline in `config/graphql/corpus_mutations.py`. The
GraphQL mutations (`CreateCorpusMutation`, `UpdateCorpusMutation`,
`UpdateCorpusDescription`, `DeleteCorpusMutation`, `SetCorpusVisibility`)
become thin wrappers that delegate to `CorpusService`. This closes the
design doc §3 Problem 3 gap ("corpus-level CRUD … has no service").

## 5. Phase C — outline (follow-up)

Migrate the ~37 files that import `CorpusObjsService` onto the segmented
services (`from opencontractserver.corpuses.services import FolderCRUDService`,
etc.), then delete `corpus_objs_service.py` and the `CorpusObjsService` facade
(CLAUDE.md no-dead-code rule). Update CLAUDE.md rule 7, the consolidated
permissioning guide, and `docs/architecture/query_permission_patterns.md` to
reference the segmented package.

## 6. Architecture decisions

- **Flat services, explicit cross-references (not mixin inheritance).** Each
  service extends `BaseService` directly; cross-module helpers are reached by
  explicit class reference. The alternative — having `FolderCRUDService`
  inherit `CorpusPathService` so `cls.`-dispatch keeps working — would minimise
  the test diff but produce a mixin web where a service's behaviour depends on
  the entry point and `paths.py` leaks into `FolderCRUDService`'s surface. The
  flat layout matches design doc §5.2 and keeps the facade's MRO trivially valid.
- **Facade in the shim, not in the package.** `CorpusObjsService` is defined
  in `corpus_objs_service.py`, not in `services/`. The `services/` package is
  born clean — it never contains the deprecated facade — and Phase C deletes
  the facade simply by deleting the shim file.
- **Runtime `DeprecationWarning` from the shim.** The shim issues a
  module-level `DeprecationWarning` on import. It fires once per process (the
  module body runs only on the first import — subsequent imports hit the module
  cache), so the cost is a single warning, not one per importer. This makes the
  deprecation observable in CI logs and the test runner's warning capture and
  gives Phase 2C a runtime signal for call-site discovery in addition to static
  grep. Deprecation is also documented in the module/class docstrings and the
  changelog.

## 7. Testing strategy

- `test_corpus_objs_service.py` — unchanged scenarios; the behavioural
  regression net for all 40 relocated methods (run via the facade).
- `test_corpus_services_package.py` — new; the Phase A structural contract.
- `test_base_service.py` — Phase 1 foundation; unaffected, run as a sanity
  check.
- Automated extraction-faithfulness verification (every relocated method body
  is byte-identical to the monolith modulo the 14 documented rewrites).
- The backend suite runs in CI (the 30-minute full suite is not run locally).

## 8. Risks & mitigations

- **Circular imports.** `paths.py` and `corpus_documents.py` are import leaves;
  `folders.py` / `lifecycle.py` import them at module top level; the shim
  imports the package. Model imports stay deferred inside method bodies exactly
  as in the monolith. The new top-level imports are a strict subset of what the
  monolith already imported, so import-time behaviour is unchanged.
- **Facade method collisions.** The five services have disjoint method names
  (pinned by `test_segmented_services_share_no_method_names`), so the facade's
  MRO cannot silently shadow a method.
- **Module size.** The original `corpus_objs_service.py` folder logic would
  have produced a ~1,300-line `folders.py`, above the design doc's ~800-line
  guideline. It is therefore split along its natural seam into `folders.py`
  (`FolderCRUDService`, ~800 lines — folder CRUD, tree, search) and
  `folder_documents.py` (`FolderDocumentService`, ~560 lines —
  document-in-folder placement and queries); the two classes have no
  interdependency, so the split adds no cross-service coupling.

## 9. Success criteria

- The `corpus_objs_service.py` monolith is split into five cohesive,
  `BaseService`-inheriting modules; the file is a thin shim.
- Every `CorpusObjsService.<method>` call site and every
  `test_corpus_objs_service.py` scenario keeps working unchanged.
- Each segmented service is independently usable without the facade.
- No permission semantics, transaction boundary, or query shape changes —
  verified by the unchanged regression suite and the faithfulness check.
