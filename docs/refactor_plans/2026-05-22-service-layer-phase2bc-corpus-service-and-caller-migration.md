# Service Layer Centralization — Phase 2B & 2C Implementation Plan

> **Status:** Implemented (issue #1716). This document is retained as the
> design record for Phases 2B and 2C.
>
> **For agentic workers:** Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `CorpusService` owning Corpus-row CRUD (Phase 2B), then migrate
every caller off the deprecated `CorpusObjsService` facade and delete the
`corpus_objs_service.py` shim (Phase 2C).

**Architecture:** Phase 2A (PR #1737) split the `corpus_objs_service.py`
monolith into the segmented `corpuses/services/` package (`CorpusPathService`,
`CorpusDocumentService`, `DocumentLifecycleService`, `FolderCRUDService`,
`FolderDocumentService`), keeping `corpus_objs_service.py` as a thin
re-export shim with a deprecated `CorpusObjsService` facade. Phase 2B adds the
sixth service — `CorpusService` for the `Corpus` row itself — closing the
design-doc §3 Problem 3 gap. Phase 2C migrates the ~37 caller files / tests
onto the segmented services and deletes the shim (CLAUDE.md no-dead-code rule).

**Tech Stack:** Django 4.x, Graphene GraphQL, DRF serializers, `BaseService`
(`shared/services/base.py`), `ServiceResult` (`shared/services/conventions.py`).

---

## Context the engineer needs

- Read first: `docs/refactor_plans/2026-05-19-service-layer-centralization-design.md`
  (§3 Problem 3, §5.2/§5.3) and `docs/refactor_plans/2026-05-21-service-layer-phase2-corpus-services-plan.md`
  (the Phase 2A plan; §4 outlines 2B, §5 outlines 2C).
- `BaseService` provides `get_or_none`, `filter_visible`, `require_permission`,
  `log_action`. `ServiceResult` is a frozen dataclass: build with
  `ServiceResult.success(value)` / `ServiceResult.failure("error")`; it
  tuple-unpacks as `(value, error)`.
- The five existing segmented services are classmethod-based (`cls.method(...)`),
  inherit `BaseService`, and take an optional `request=` kwarg threaded into
  `user_can`. `CorpusService` follows the same shape.
- IDOR rule (CLAUDE.md): query by id, return the *same* message for
  not-found / not-permitted. `get_for_user_or_none` (in
  `opencontractserver/utils/permissioning.py`) already does this.
- Run targeted tests, never the full 30-min suite:
  `docker compose -f test.yml run --rm django pytest <paths> -n 4 --dist loadscope`

## Method → owning-service map (used throughout Phase 2C)

| Owning service | Methods |
|---|---|
| `CorpusPathService` | `_compute_moved_path`, `_target_directory_string_from_path`, `_dispatch_document_path_created_signals`, `_fetch_occupied_paths_in_directory`, `_disambiguate_path`, `_create_successor_path_with_retry` |
| `CorpusDocumentService` | `_check_document_in_corpus`, `_build_corpus_documents_queryset`, `get_corpus_documents`, `get_corpus_documents_visible_to_user`, `get_corpus_document_by_slug`, `get_corpus_document_by_id`, `is_document_in_corpus`, `get_corpus_caml_articles`, `upload_document_to_corpus`, `add_document_to_corpus`, `add_documents_to_corpus`, `remove_document_from_corpus`, `remove_documents_from_corpus` |
| `DocumentLifecycleService` | `get_deleted_documents`, `soft_delete_document`, `restore_document`, `permanently_delete_document`, `empty_trash` |
| `FolderCRUDService` | `get_visible_folders`, `get_folder_by_id`, `get_folder_tree`, `create_folder`, `update_folder`, `move_folder`, `delete_folder`, `get_folder_path`, `search_folders`, `create_folder_structure_from_paths` |
| `FolderDocumentService` | `get_folder_documents`, `get_folder_document_ids`, `get_folder_document_count`, `move_document_to_folder`, `move_documents_to_folder`, `get_document_folder` |

---

# Phase 2B — `CorpusService` for Corpus-row CRUD

### Scope decision

`CreateCorpusMutation` / `UpdateCorpusMutation` are `DRFMutation` subclasses —
the row create/update flows through the *shared* `DRFMutation` infrastructure
+ `CorpusSerializer`. That generic CRUD machinery is deliberately **kept** (it
is shared across many mutations; gutting it for one model would be a net loss
and a real frontend-contract risk). Phase 2B instead extracts every
*Corpus-specific* piece of inline logic into `CorpusService` and has the two
DRF mutations delegate to it — so all corpus-row business logic lives in the
service while the GraphQL output contract stays byte-identical. The three
plain `graphene.Mutation` corpus mutations (`SetCorpusVisibility`,
`UpdateCorpusDescription`, `DeleteCorpusMutation`) become thin wrappers that
decode global IDs and delegate fully.

This closes design-doc §3 Problem 3: corpus-row delete / visibility /
description versioning / the create-time creator-permission grant / the
update-time embedder guard all become `CorpusService`-owned.

### Task B1: Create `CorpusService`

**Files:**
- Create: `opencontractserver/corpuses/services/corpus_service.py`
- Modify: `opencontractserver/corpuses/services/__init__.py`

- [ ] **Step 1:** Write `corpus_service.py` — `CorpusService(BaseService)`,
  classmethod-based:
  - `update_description(user, corpus, new_content) -> ServiceResult` —
    creator-only; call `corpus.update_description(new_content=, author=user)`;
    `ServiceResult.success(revision)` (revision may be `None` when unchanged).
  - `delete_corpus(user, corpus, *, request=None) -> ServiceResult` — reject
    `corpus.is_personal`; reject when `user_lock` held by another user; require
    DELETE via `require_permission`; `corpus.delete()`.
  - `set_visibility(user, corpus, is_public, *, request=None) -> ServiceResult` —
    require PERMISSION; no-op when already at target; on `True` dispatch
    `make_corpus_public_task`; on `False` set `is_public=False` and save. The
    success value is the user-facing status message.
  - `assert_embedder_change_allowed(corpus, new_embedder) -> str` — `""` when
    allowed, else the existing embedder-change error string.
  - `grant_creator_permissions(user, corpus, *, request=None) -> None` — grant
    `[CRUD, PUBLISH, PERMISSION]` via `set_permissions_for_obj_to_user`.
  Each mutating method `log_action`s. Model / task imports stay deferred
  inside methods (circular-import rule).
- [ ] **Step 2:** Register in `services/__init__.py`: import `CorpusService`,
  add to `__all__`, add a docstring bullet.
- [ ] **Step 3:** `py_compile` both files.

### Task B2: Delegate the GraphQL mutations to `CorpusService`

**Files:**
- Modify: `config/graphql/corpus_mutations.py`

- [ ] **Step 1:** `SetCorpusVisibility.mutate` — decode `corpus_id`, fetch via
  `get_for_user_or_none`, call `CorpusService.set_visibility`, map the
  `ServiceResult` to `ok`/`message`. Keep the unified IDOR message.
- [ ] **Step 2:** `UpdateCorpusDescription.mutate` — decode, fetch, call
  `CorpusService.update_description`, map result (`version` from the revision).
- [ ] **Step 3:** `DeleteCorpusMutation.mutate` — decode, fetch, call
  `CorpusService.delete_corpus`, map result.
- [ ] **Step 4:** `CreateCorpusMutation` keeps `DRFMutation`; its override
  calls `CorpusService.grant_creator_permissions` after a successful create.
  `UpdateCorpusMutation` keeps `DRFMutation`; its override calls
  `CorpusService.assert_embedder_change_allowed` for the guard.
- [ ] **Step 5:** Remove now-unused imports; `black`/`isort`/`flake8`.

### Task B3: Tests for `CorpusService`

**Files:**
- Create: `opencontractserver/tests/test_corpus_service.py`

- [ ] **Step 1:** Cover each method: success, permission-denied, IDOR-safe
  None handling, the embedder guard, personal-corpus delete rejection,
  user-lock delete rejection, visibility no-op, description unchanged.
- [ ] **Step 2:** Run `pytest opencontractserver/tests/test_corpus_service.py
  -n 4 --dist loadscope --create-db`; expect PASS.
- [ ] **Step 3:** Run the existing corpus mutation tests to confirm the
  GraphQL contract is unchanged (`test_corpus_mutations*`, schema tests).
- [ ] **Step 4:** Update `CHANGELOG.md`; commit.

---

# Phase 2C — Caller migration + shim deletion

### Task C1: Migrate non-test callers (23 files)

For each file: replace `from opencontractserver.corpuses.corpus_objs_service
import CorpusObjsService` with imports of the specific owning service(s) from
`opencontractserver.corpuses.services`, and rewrite each `CorpusObjsService.X`
call to `<OwningService>.X` using the method→service map above. Files & methods:

- `config/graphql/corpus_folder_mutations.py` → `FolderCRUDService` (create/update/move/delete_folder), `FolderDocumentService` (move_document(s)_to_folder)
- `config/graphql/corpus_queries.py` → `FolderCRUDService` (get_visible_folders, get_folder_by_id), `DocumentLifecycleService` (get_deleted_documents)
- `config/graphql/corpus_types.py` → `CorpusDocumentService`
- `config/graphql/corpus_mutations.py` → `CorpusDocumentService` (add/remove_documents_to/from_corpus)
- `config/graphql/document_mutations.py` → `DocumentLifecycleService`
- `config/graphql/document_relationship_mutations.py` → `CorpusDocumentService`
- `config/graphql/document_types.py` → `FolderDocumentService`
- `config/graphql/extract_mutations.py` → `CorpusDocumentService`
- `config/graphql/og_metadata_queries.py` → `CorpusDocumentService`
- `opencontractserver/discovery/views.py` → `CorpusDocumentService`
- `opencontractserver/documents/document_service.py` → `CorpusDocumentService`
- `opencontractserver/llms/agents/core_agents.py` → `CorpusDocumentService`
- `opencontractserver/llms/tools/core_tools/annotations.py` → `CorpusDocumentService`
- `opencontractserver/llms/tools/core_tools/caml_article.py` → `CorpusDocumentService`
- `opencontractserver/llms/tools/core_tools/document_indexing.py` → `CorpusDocumentService`
- `opencontractserver/llms/tools/core_tools/documents.py` → `FolderCRUDService` (get_folder_by_id), `FolderDocumentService` (move_document_to_folder)
- `opencontractserver/llms/tools/core_tools/pii.py` → `CorpusDocumentService`
- `opencontractserver/mcp/resources.py` → `CorpusDocumentService`
- `opencontractserver/mcp/server.py` → `CorpusDocumentService`
- `opencontractserver/mcp/tools.py` → `CorpusDocumentService`
- `opencontractserver/tasks/badge_tasks.py` → `CorpusDocumentService`
- `opencontractserver/tasks/import_tasks.py` → `FolderCRUDService`
- `opencontractserver/utils/import_v2.py` → `FolderCRUDService`

- [ ] Per file: rewrite import + calls, `py_compile`.
- [ ] Commit checkpoint after the GraphQL files, then the rest.

### Task C2: Migrate test callers

- [ ] `test_corpus_objs_service.py` (295 refs across 28 methods) — rewrite each
  `CorpusObjsService.X` to its owning service; replace the facade import with
  the five segmented imports; keep all scenarios/assertions unchanged. Keep the
  filename (CLAUDE.md rule 5 — minimal change to old tests).
- [ ] `test_corpus_get_documents_deprecation.py`, `test_permission_optimizer.py`,
  `test_document_service.py`, `test_document_stats.py`, `test_import_utils.py`,
  `test_llms_typing_coverage.py`, `test_move_document_tool.py`,
  `test_permanent_deletion.py`, `test_zip_import_integration.py` — same rewrite.
- [ ] `test_corpus_services_package.py` — delete `test_shim_import_emits_
  deprecation_warning` and the facade-MRO tests (the shim/facade no longer
  exist); keep the package-structure tests.

### Task C3: Delete the shim, update docs

- [ ] Delete `opencontractserver/corpuses/corpus_objs_service.py`.
- [ ] Update docstring/comment references to `CorpusObjsService` /
  `corpus_objs_service` in `corpuses/models.py`, `documents/apps.py`,
  `utils/permissioning.py`, `CLAUDE.md` (rule 7), and the consolidated
  permissioning guide / `query_permission_patterns.md` — point at the
  segmented services.
- [ ] `CHANGELOG.md`; mark the Phase 2 plan doc 2B/2C complete.

### Task C4: Verify

- [ ] `grep -rn "CorpusObjsService\|corpus_objs_service" --include=*.py .`
  returns nothing.
- [ ] `pytest opencontractserver/tests/test_corpus_objs_service.py
  opencontractserver/tests/test_corpus_services_package.py
  opencontractserver/tests/test_corpus_service.py
  opencontractserver/tests/test_base_service.py -n 4 --dist loadscope --create-db`
  — all PASS.
- [ ] Smoke the migrated MCP / discovery / tasks / GraphQL test modules.
- [ ] `black` / `isort` / `flake8` clean.
