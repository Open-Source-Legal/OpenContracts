# Service Layer Centralization — Phase 5 (Fill Coverage Gaps) Implementation Plan

**Status:** Implemented
**Date:** 2026-05-23
**Tracking issue:** #1719
**Depends on:** Phase 1 (#1715), Phase 3 (#1717), Phase 4 (#1718) — all merged

## 1. Goal

Create per-app `services/` packages for the five models that still hand-roll
permission composition inline:

- `agents` (`AgentConfiguration`, `AgentActionResult`) — full guardian
  permission model
- `analyzer` (analysis *lifecycle* — start/delete/make-public — beyond the
  Phase-3 read-only `AnalysisService`)
- `notifications` (`Notification` — simple ownership model, NO
  `AnnotatePermissionsForReadMixin`)
- `feedback` (`UserFeedback` — guardian permissions + annotation-derived
  comment permission)
- `worker_uploads` (`WorkerAccount`, `CorpusAccessToken`,
  `WorkerDocumentUpload` — superuser- and corpus-creator-gated admin)

This is Phase 5 of the roadmap in
`docs/refactor_plans/2026-05-19-service-layer-centralization-design.md` (§6).
Phase 5 closes the design-doc §3 Problem 3 coverage gap.

## 2. Approach

The migrated logic is **byte-for-byte equivalent** to the inline resolver /
mutation code being replaced. This is a relocation + encapsulation, not a
rewrite — no behaviour, permission semantics, transaction boundary, or query
shape changes. Each service inherits `shared.services.BaseService` and
follows the established conventions:

- Public methods are classmethod-based, taking an optional `request=` kwarg
  threaded into `user_can` so the Tier-2 request-scoped permission cache is
  shared (the Phase-4 convention).
- Reads return permission-filtered querysets or `None` (IDOR-safe).
- Writes return `ServiceResult` envelopes — tuple-unpackable so GraphQL
  mutations remain `(value, error)`-shaped.
- Model imports stay deferred inside methods (circular-import rule).

The `NotificationService` is the lone exception to `BaseService`'s `user_can`
machinery: `Notification` uses a simple ownership model (recipient-based) and
its manager does not implement `user_can`. The service still inherits
`BaseService` for `log_action` and architectural conformance, but provides its
own IDOR-safe lookup keyed on `recipient=user`.

## 3. Per-app deliverables

### 3.1 `agents/services/`

| Service | Module | Responsibility |
|---|---|---|
| `AgentConfigurationService(BaseService)` | `agent_configuration_service.py` | Agent CRUD + visibility queries (resolve_agents, resolve_agent, Create/Update/Delete mutations) |
| `AgentActionResultService(BaseService)` | `agent_action_result_service.py` | Agent action result visibility queries (resolve_agent_action_results) |

Migrates: `config/graphql/agent_mutations.py` (Create/Update/Delete),
`config/graphql/social_queries.py` (`resolve_agents`,
`resolve_agent_configurations`, `resolve_agent`),
`config/graphql/action_queries.py` (`resolve_agent_action_results`).

### 3.2 `analyzer/services/` (extend)

The Phase-3 `AnalysisService` (read-only — `check_analysis_permission`,
`get_visible_analyses`, `get_analysis_annotations`) is unchanged. Phase 5
adds:

| Service | Module | Responsibility |
|---|---|---|
| `AnalysisLifecycleService(BaseService)` | `analysis_lifecycle_service.py` | `make_public`, `start_document_analysis`, `delete_analysis` |

Migrates: `config/graphql/analysis_mutations.py` (`MakeAnalysisPublic`,
`StartDocumentAnalysisMutation`, `DeleteAnalysisMutation`).

### 3.3 `notifications/services/`

| Service | Module | Responsibility |
|---|---|---|
| `NotificationService(BaseService)` | `notification_service.py` | Notification queries (list / unread-count / IDOR-safe single lookup) + mutations (mark read/unread/all-read/delete) |

Note: `Notification` uses **simple ownership** — no `AnnotatePermissionsForReadMixin`,
no `user_can` manager. `NotificationService` provides its own ownership-filtered
lookup so callers cannot distinguish "not found" from "belongs to another user"
(IDOR rule).

Migrates: `config/graphql/notification_mutations.py` (all four mutations),
`config/graphql/social_queries.py` (`resolve_notifications`,
`resolve_notification`, `resolve_unread_notification_count`).

### 3.4 `feedback/services/`

| Service | Module | Responsibility |
|---|---|---|
| `UserFeedbackService(BaseService)` | `user_feedback_service.py` | `approve_annotation`, `reject_annotation` — the two annotation-derived feedback flows |

Migrates: `config/graphql/annotation_mutations.py`
(`ApproveAnnotation`, `RejectAnnotation`).

### 3.5 `worker_uploads/services/`

| Service | Module | Responsibility |
|---|---|---|
| `WorkerAccountService(BaseService)` | `worker_account_service.py` | Worker account lifecycle (create / deactivate / reactivate / list) — superuser-gated |
| `CorpusAccessTokenService(BaseService)` | `corpus_access_token_service.py` | Token CRUD (create / revoke / list-for-corpus) — superuser or corpus creator |
| `WorkerDocumentUploadService(BaseService)` | `worker_document_upload_service.py` | Upload listing per corpus — superuser or corpus creator |

Migrates: `config/graphql/worker_mutations.py` (all four mutations),
`config/graphql/worker_queries.py` (all three resolvers).

## 4. Tests

New test module: `opencontractserver/tests/test_service_layer_phase5.py`
covering the Phase-5 contract:

- Each new service is importable from its app's `services/` package root.
- Each service inherits `BaseService`.
- Public methods accept `request=` as keyword-only (the Phase-4 convention).
- The `NotificationService` exposes its simple-ownership lookup that does
  NOT depend on `user_can`.

Behavioural regressions are caught by the existing GraphQL mutation / query
test suites (`test_notification_graphql.py`, `test_feedback.py`,
`test_worker_uploads.py`, `test_agent_action_result.py`, the agent / analysis
mutation suites). Those tests are NOT modified — they exercise the same
GraphQL surface, now wired through the services.

## 5. CHANGELOG

Add an `[Unreleased]` entry under `### Changed` summarising the relocation,
listing each new service package and the migrated GraphQL files.

## 6. Out of scope (deferred to Phase 6, #1720)

- Sweeping the remaining 26 GraphQL files that do not touch the five gap
  models.
- Updating CLAUDE.md rule 7 to the simpler "always go through the app's
  `services/` package" phrasing.
- Refreshing `docs/architecture/query_permission_patterns.md` and the
  consolidated permissioning guide.
- Adding a lint/test guard against direct `visible_to_user` imports in
  `config/graphql/`.

## 7. Success criteria

- All five new service packages exist, each module ≤ 600 lines.
- Every migrated GraphQL resolver/mutation for the gap models calls a service
  rather than composing `visible_to_user` + `user_can` inline (or, in the
  notification case, hand-rolling `recipient=user` IDOR-safe lookups inline).
- All existing GraphQL / model tests pass unchanged.
- Phase-5 structural tests pass.
- `BaseService` request-threading convention applied uniformly.
