# Service Layer Centralization — Architecture & Roadmap

**Status:** Design
**Date:** 2026-05-19
**Author:** scrudato@umich.edu

## 1. Purpose

Recent PRs introduced a service layer (`DocumentService`, `CorpusObjsService`)
and a set of per-app "query optimizers" to centralize fetching and
permission logic. The effort is partial and inconsistent. This document
defines the **target architecture** for centralizing fetch + permission
logic for *all* models, and a **phased roadmap** to get there without
creating monoliths.

The goal is one coherent, well-segmented service layer that every
user-context caller (GraphQL resolvers, MCP tools, REST views, LLM tools,
Celery tasks invoked with a user) reaches through — replacing today's mix
of services, optimizers, and hand-rolled inline permission composition.

## 2. Current State

### Tier 0 — Model managers (the foundation — keep)

`user_can(user, instance, permission)` and `visible_to_user(user)` on
managers/querysets, backed by `_default_user_can` (`utils/permissioning.py`),
`UserCanMixin` (`shared/user_can_mixin.py`), per-model manager overrides
(`shared/Managers.py`), and a two-tier request-scoped permission cache
(`shared/permission_cache.py`, `utils/permission_optimizer.py`).

Permission-centralization Phases A–F are largely complete. The invariant
`visible_to_user(u)` ⟺ `user_can(u, READ)` is pinned by
`test_authorization_invariants`. **This tier is sound and stays as-is.**

### Tier 1 — "Query Optimizers" (6 files, ~3,460 lines)

| File | Lines | Classes hosted |
|------|-------|----------------|
| `annotations/query_optimizer.py` | 1,509 | `AnnotationQueryOptimizer`, `RelationshipQueryOptimizer`, `AnalysisQueryOptimizer`, `ExtractQueryOptimizer` |
| `documents/query_optimizer.py` | 740 | `DocumentActionsQueryOptimizer`, `DocumentRelationshipQueryOptimizer`, `DocumentVersionQueryOptimizer` |
| `extracts/query_optimizer.py` | 582 | `MetadataQueryOptimizer` |
| `conversations/query_optimizer.py` | 224 | `ConversationQueryOptimizer` |
| `users/query_optimizer.py` | 250 | `UserQueryOptimizer` |
| `badges/query_optimizer.py` | 157 | `BadgeQueryOptimizer` |

Optimizers are GraphQL resolver helpers: prefetch builders, bulk
effective-permission computation, request-scoped caches.

### Tier 2 — "Services" (~3,170 lines)

| File | Lines | Responsibility |
|------|-------|----------------|
| `corpuses/corpus_objs_service.py` | 2,834 | folders R/W, doc-in-folder R/W, lifecycle/trash, path utils, doc-in-corpus membership, CAML |
| `documents/document_service.py` | 332 | document creation, quota, validation, standalone lookup, doc-level permissions |
| `document_imports/services.py` | — | import-specific |

## 3. Problems

1. **Monolith files.** `corpus_objs_service.py` (2,834 lines) holds 6+
   distinct responsibilities in one class. `annotations/query_optimizer.py`
   (1,509 lines) hosts 4 unrelated optimizer classes — two of which
   (`Analysis`, `Extract`) are not even annotation concerns and are
   misfiled in the `annotations` app.

2. **"Optimizer" vs "Service" is an unclear distinction.** Both do
   permission-filtered fetching. `AnnotationQueryOptimizer` performs
   permission *checks*; `CorpusObjsService` does *everything*. CLAUDE.md
   rule 7 is a full paragraph trying to disambiguate which to use — a
   sign the boundary is wrong, not just under-documented.

3. **Coverage gaps.** `agents`, `analyzer` (Analysis/Extract have
   optimizers but no service), `notifications`, `feedback`,
   `worker_uploads`, and **corpus-level CRUD** (the `Corpus` row itself —
   `CorpusObjsService` covers corpus *contents*, not the corpus) have no
   service. Their mutations/resolvers still hand-roll `visible_to_user` +
   permission composition inline. 31 files under `config/graphql/`
   directly reference `visible_to_user` / `user_can` /
   `user_has_permission_for_obj`.

4. **Three request-threading conventions.** `ConversationQueryOptimizer`
   is instance-based via `get_request_optimizer(request)`;
   `AnnotationQueryOptimizer` is classmethod-based with a `context=` param;
   the services are classmethod-based with a `request=` kwarg. A caller
   must know which style each helper expects.

5. **No uniform entry point.** Callers must memorize "use
   `CorpusObjsService.get_corpus_documents`" vs "`Document.objects.visible_to_user`"
   vs "`AnnotationQueryOptimizer.get_document_annotations`" per case.

## 4. Approaches Considered

**Approach A — Unified Service packages; optimizers demoted to internals
(RECOMMENDED).** One public abstraction: a per-app `services/` *package*
(a directory of cohesive modules, never one giant file). It is the single
entry point for any user-context caller. Query optimizers stop being a
public concept — they become private prefetch / bulk-permission helpers
*inside* services. A shared `BaseService` centralizes request threading,
return conventions, and IDOR-safe lookup.
*Pros:* one mental model; kills both monoliths; full model coverage;
extends the direction the codebase already chose. *Cons:* large
migration touching many files; optimizer request-cache wiring must be
preserved during the move.

**Approach B — Tidy in place: split monoliths + fill gaps, keep two named
concepts.** Split the two large files, add optimizers/services for gap
models, standardize request threading — but keep "query optimizer" and
"service" as distinct public concepts. *Pros:* lower risk, smaller
diff. *Cons:* the core optimizer-vs-service confusion (Problem 2)
survives; this tidies without truly centralizing.

**Approach C — Manager-centric: push all fetch/mutate onto managers.**
Eliminate services and optimizers; put everything on Django managers
(`Corpus.objects.create_folder(...)`). *Pros:* maximally central, one
place per model. *Cons:* managers become the new monolith and cannot be
split into packages; mixing heavy transactional business logic into
managers is an anti-pattern; aggravates circular imports; request-scoped
cache threading becomes awkward.

**Decision: Approach A.** It is the only option that centralizes *and*
avoids monoliths, which is the explicit requirement.

## 5. Target Architecture

### 5.1 Three-tier mental model

```
Tier 0  Model managers          user_can() / visible_to_user()
        (authorization          — single-object + queryset gates
         primitives)            — UNCHANGED

Tier 1  Service packages        per-app services/ directory
        (THE public layer)      — get_* / list_* / create_* / update_*
                                  / delete_*, all permission-filtered
                                — the ONLY thing resolvers/tools/REST
                                  /Celery-with-user call

Tier 1.5  Optimizers            private perf helpers INSIDE services
        (internal detail)       — prefetch builders, bulk effective-perm
                                  computation, request-scoped caches
                                — not referenced outside their service
```

Rule of thumb after migration: **resolvers and tools never touch Tier 0
or Tier 1.5 directly.** They call a Tier 1 service. Tier 0 remains
callable for low-level needs but is no longer the recommended resolver
entry point.

### 5.2 Per-app package layout

Each app exposes a `services/` package. One module per cohesive
responsibility; `__init__.py` re-exports the public service classes so
imports stay stable (`from opencontractserver.corpuses.services import
CorpusService`).

```
opencontractserver/
  shared/
    services/
      __init__.py
      base.py            # BaseService — shared machinery (§5.3)
      conventions.py     # ServiceResult / return-type helpers, IDOR lookup
  corpuses/
    services/
      __init__.py
      corpus_service.py      # Corpus row CRUD + corpus-level permissions
      folders.py             # folder R/W  (from corpus_objs_service)
      corpus_documents.py    # doc-in-corpus R/W + membership
      lifecycle.py           # soft-delete / restore / trash
      paths.py               # DocumentPath disambiguation utilities
  documents/
    services/
      __init__.py
      document_service.py    # creation, quota, validation, lookup, perms
      relationships.py       # (from documents/query_optimizer.py)
      versions.py            # (from documents/query_optimizer.py)
      actions.py             # (from documents/query_optimizer.py)
  annotations/
    services/
      __init__.py
      annotation_service.py  # (from AnnotationQueryOptimizer)
      relationship_service.py# (from RelationshipQueryOptimizer)
  analyzer/
    services/
      __init__.py
      analysis_service.py    # (from misfiled AnalysisQueryOptimizer)
  extracts/
    services/
      __init__.py
      extract_service.py     # (from misfiled ExtractQueryOptimizer)
      metadata.py            # (from MetadataQueryOptimizer)
  conversations/services/    # (from ConversationQueryOptimizer)
  users/services/            # (from UserQueryOptimizer)
  badges/services/           # (from BadgeQueryOptimizer)
  agents/services/           # NEW — gap model
  notifications/services/    # NEW — gap model (simple ownership model)
  feedback/services/         # NEW — gap model
  worker_uploads/services/   # NEW — gap model
```

No single module should exceed roughly 600–800 lines. When a
responsibility outgrows that, it splits into a sibling module within the
same package. The package directory is the unit of an "app's service
layer"; the file is the unit of a "responsibility".

### 5.3 `BaseService` — the centralized machinery

`shared/services/base.py` provides one base class all services inherit.
This is the "as central as possible" piece — common behavior lives once;
concrete per-app services stay small.

`BaseService` standardizes:

- **Request threading.** One convention: every public method takes an
  optional `request` (or `context`) kwarg, threaded into Tier 0
  `user_can` calls so the request-scoped permission cache is shared.
  The three legacy styles (`context=`, `get_request_optimizer`,
  `request=`) collapse to this one.
- **Return conventions.** Reads return permission-filtered querysets or
  `None` (IDOR-safe). Writes return a `ServiceResult` (or the existing
  `(obj, error)` / `(ok, error)` tuple, standardized) — defined in
  `conventions.py`.
- **IDOR-safe single-object lookup.** A `get_for_user_or_none(model,
  pk, user, permission=READ, request=...)` helper: queries by pk,
  returns `None` for both not-found and permission-denied. Replaces the
  per-mutation hand-rolled pattern.
- **Permission delegation.** Services never re-implement permission
  logic — they call `Model.objects.user_can(...)` /
  `.visible_to_user(...)` (Tier 0). `BaseService` provides thin helpers
  (`require_permission`, `filter_visible`) that wrap those calls with
  consistent error semantics.
- **Transaction + logging conventions.** All mutations wrapped in
  `transaction.atomic()`; consistent structured logging of
  who-did-what-to-which-object.

Concrete services contain only model-specific fetch/mutate logic. They
must not duplicate permission rules, request-cache wiring, or return-shape
boilerplate — all of that is inherited.

### 5.4 What happens to "query optimizers"

The term is retired as a public concept. Each optimizer's logic moves
into its owning app's service package as a **private module or private
methods** (`_prefetch_*`, `_bulk_effective_permissions`,
`_RequestCache`). The misfiled ones move to the correct app
(`AnalysisQueryOptimizer` → `analyzer/services/`, `ExtractQueryOptimizer`
+ `MetadataQueryOptimizer` → `extracts/services/`). Performance behavior
(prefetches, bulk permission computation, request caching) is preserved
exactly — this is a relocation + encapsulation, not a rewrite.

## 6. Phased Roadmap

Mirrors the existing Phase A–F naming style. Each phase is independently
shippable, independently tested, and leaves the tree green. Tracking
issues: Phase 1 #1715, Phase 2 #1716, Phase 3 #1717, Phase 4 #1718,
Phase 5 #1719, Phase 6 #1720.

**Phase 1 — Foundation (#1715).** Create `shared/services/` with `BaseService`,
`conventions.py`, and `get_for_user_or_none`. No behavior change; no
callers migrated yet. Unit-test the base machinery directly. *Smallest
phase; unblocks everything else.*

**Phase 2 — Split the `CorpusObjsService` monolith (#1716).** Convert
`corpuses/corpus_objs_service.py` into the `corpuses/services/` package
(`folders`, `corpus_documents`, `lifecycle`, `paths`), each module
inheriting `BaseService`. Add `corpus_service.py` for Corpus-row CRUD
currently inline in `corpus_mutations.py`. Keep
`corpus_objs_service.py` as a thin re-export shim for one release, then
delete it (No-dead-code rule). Existing tests in
`test_corpus_objs_service.py` must pass unchanged against the new
imports.

**Phase 3 (#1717) — Split the `annotations/query_optimizer.py` monolith and
relocate misfiled optimizers.** Move `AnnotationQueryOptimizer` /
`RelationshipQueryOptimizer` into `annotations/services/`; move
`AnalysisQueryOptimizer` → `analyzer/services/`; move
`ExtractQueryOptimizer` + `MetadataQueryOptimizer` →
`extracts/services/`. Wrap optimizer logic as private service internals;
expose `get_*`/`list_*` public methods. Update all GraphQL call sites
(`extract_queries.py`, `extract_mutations.py`, `corpus_queries.py`,
`extract_types.py`).

**Phase 4 — Migrate remaining optimizers into service packages (#1718).**
`documents/query_optimizer.py`, `conversations`, `users`, `badges`.
Standardize their request threading onto the `BaseService` convention
(retires `get_request_optimizer`).

**Phase 5 — Fill coverage gaps (#1719).** New service packages for `agents`,
`analyzer` (analysis lifecycle beyond the optimizer),
`notifications` (note: simple ownership model — no
`AnnotatePermissionsForReadMixin`), `feedback`, `worker_uploads`.
Migrate their inline resolver/mutation permission logic onto the
services.

**Phase 6 — Resolver cleanup + enforcement (#1720).** Sweep the 31
`config/graphql/` files: every resolver/mutation fetches through a
service, not inline `visible_to_user`/`user_can`. Update CLAUDE.md
(replace rule 7's paragraph with the simple "always go through the
app's `services/` package" rule). Refresh
`docs/architecture/query_permission_patterns.md` and the consolidated
permissioning guide. Optionally add a lint/test guard that fails if
`config/graphql/` imports `visible_to_user` directly.

## 7. Non-Goals

- Changing Tier 0 (`user_can` / `visible_to_user` / the permission
  cache). The authorization primitives and their pinned invariant are
  out of scope.
- Changing permission *semantics* for any model. This is a structural
  relocation; every existing permission rule must produce identical
  decisions before and after.
- Rewriting the GraphQL schema or mutation response shapes beyond
  standardizing the service return envelope.
- Touching `document_imports/services.py` internals beyond having it
  inherit `BaseService` for consistency.

## 8. Risks & Mitigations

- **Circular imports.** Services importing models importing managers is
  the existing hot spot (see the many deferred imports in
  `corpus_objs_service.py`). *Mitigation:* keep model imports deferred
  inside methods; `BaseService` itself imports no concrete models.
- **Lost performance behavior during optimizer relocation.**
  *Mitigation:* relocate, do not rewrite; keep prefetch/bulk-permission
  logic byte-for-byte where possible; rely on existing optimizer tests
  (`test_query_optimizer_methods.py`, `test_metadata_query_optimizer.py`,
  `test_version_aware_query_optimizer.py`) as regression gates.
- **Large blast radius.** *Mitigation:* phased rollout; re-export shims
  for one release per renamed module; each phase leaves the tree green.
- **Backend test-suite runtime (30+ min).** *Mitigation:* per phase, run
  only the affected app's test modules in parallel; reserve the full
  suite for pre-merge of each phase.

## 9. Success Criteria

- No service or optimizer module exceeds ~800 lines.
- Every model with user-facing access has a service package; no GraphQL
  resolver composes `visible_to_user` + permission checks inline.
- One request-threading convention across the entire service layer.
- The term "query optimizer" no longer appears as a public API concept.
- All existing permission and optimizer tests pass unchanged (semantics
  preserved); the `visible_to_user ⟺ user_can(READ)` invariant still
  holds.
- CLAUDE.md rule 7 reduces to a single sentence.
