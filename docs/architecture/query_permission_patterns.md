# Query Permission Patterns

Reference for how OpenContracts filters querysets by user permissions.

## Architecture Overview

Permission-filtered access is organised in **three tiers**:

```
Tier 0  Model managers           user_can() / visible_to_user()
        (authorization           — single-object + queryset gates
         primitives)             — internal foundation, NOT a public entry

Tier 1  Service packages         opencontractserver/<app>/services/
        (THE public layer)       — get_* / list_* / create_* / update_* / delete_*
                                 — every user-context caller goes here
                                 — BaseService.{get_or_none, filter_visible,
                                                filter_visible_qs,
                                                require_permission, user_has}
                                   provides the generic surface

Tier 1.5  Optimizers             Private prefetch / bulk-permission helpers
        (internal detail)        — live INSIDE services; not referenced
                                   outside their owning service
```

**Rule of thumb after Phase 6 (issue #1720):** resolvers, MCP/LLM tools, REST
views, and user-context Celery tasks **never touch Tier 0 directly**. They
call Tier 1. The invariant is enforced for `config/graphql/` by
`opencontractserver/tests/architecture/test_graphql_service_layer.py` and
should be extended to other consumer directories as they migrate.

## Migration Recipes — "I just got an `opencontracts.E001` error, what do I type?"

If you landed here from a Django `manage.py` error or a pytest failure
mentioning `opencontracts.E001` / "Tier-0 permission primitive", the
recipe below is the answer. Both the test and the system check route
through the same helper (`opencontractserver.shared.architecture_audit.
format_violation`), so the failure output you saw is the same content
as what follows — copy whichever recipe matches the identifier the
scanner flagged.

In every recipe: add the import once at the top of the file:

```python
from opencontractserver.shared.services.base import BaseService
```

And always pass `request=info.context` (or the request-equivalent your
caller has) so the Tier-2 permission cache is shared across the request.
(Caveat: the cache is keyed by single object, so `request=` only does
anything on the single-object helpers — `get_or_none` /
`require_permission` / `user_has`. On the queryset helpers
`filter_visible` / `filter_visible_qs` it is accepted for API parity but is
currently a no-op; pass it anyway for consistency.)

### Recipe 1 — `visible_to_user`

```python
# ❌ Forbidden
Model.objects.visible_to_user(user)
Model.objects.visible_to_user(user).get(pk=id)

# ✅ Listing visible rows (queryset, chainable like before)
BaseService.filter_visible(Model, user, request=info.context)

# ✅ IDOR-safe single-object fetch — returns None instead of raising;
#    collapses not-found and permission-denied into one branch
obj = BaseService.get_or_none(Model, pk, user, request=info.context)
if obj is None:
    return MyMutation(ok=False, message="Not found")
```

The "raises DoesNotExist on miss" form is intentionally gone. Returning
`None` is the IDOR-safe contract — callers must surface a single
generic error string for both "missing" and "forbidden" cases so the
two branches stay indistinguishable to the client. If the surrounding
code relied on `DoesNotExist`, replace the `try/except` with a
`if obj is None:` branch returning the same error.

### Recipe 2 — `user_can`

```python
# ❌ Forbidden
if not obj.user_can(user, PermissionTypes.UPDATE):
    return MyMutation(ok=False, message="Denied")

# ✅ Fail-fast gate — returns "" on grant, error string on denial
error = BaseService.require_permission(
    obj, user, PermissionTypes.UPDATE, request=info.context
)
if error:
    return MyMutation(ok=False, message=error)
```

```python
# ❌ Forbidden (boolean UI flag)
can_edit = obj.user_can(user, PermissionTypes.UPDATE)

# ✅ Boolean for UI-state fields (can_edit_summary, can_view_history, etc.)
can_edit = BaseService.user_has(
    obj, user, PermissionTypes.UPDATE, request=info.context
)
```

`require_permission` is for resolvers that need to abort with an error
message. `user_has` is for resolvers that need a `True/False` to feed a
UI-state GraphQL field. Don't reach for `not BaseService.require_permission(...)`
when you can use `BaseService.user_has(...)` directly.

### Recipe 3 — `user_has_permission_for_obj`

Same as `user_can`. Use `BaseService.require_permission(...)` for a
gate or `BaseService.user_has(...)` for a boolean.

### When the generic helpers aren't enough

If a dedicated per-app service method exists that matches your
operation semantically (e.g. `CorpusDocumentService.get_corpus_document_by_id`,
`ConversationService.get_threads_for_corpus`, `AnnotationService.get_document_annotations`),
prefer it — it may layer prefetches, request-scoped caching, or extra
domain logic on top of the generic `BaseService.*` call. The per-app
service inventory below lists every one.

If your operation is a complex multi-object flow that doesn't fit
either bucket, that's a signal to add a new method to the relevant
per-app service rather than re-composing inline. The point of the rule
is that permission-laden orchestration stops being "the same six lines
copy-pasted everywhere" and starts being named, testable, importable
operations.

## The `BaseService` entry point

`opencontractserver.shared.services.base.BaseService` is the generic surface
every per-app service inherits. It centralises the four cross-cutting
operations that resolvers / tools used to inline against Tier 0:

| Method | Use for | Returns |
|--------|---------|---------|
| `BaseService.filter_visible(Model, user, *, request=None, **kwargs)` | Listing a model's visible rows. `**kwargs` are passed straight through to the manager's `visible_to_user(...)` so per-model perf knobs (e.g. `Document(..., lightweight=True)`) keep working. | `QuerySet` |
| `BaseService.filter_visible_qs(queryset, user, *, request=None, **kwargs)` | Same intent as `filter_visible`, but starts from an **existing queryset or related manager** — chains the queryset's own `visible_to_user` so the visibility predicate stays in the same `WHERE` expression tree as any prior `.filter(...)` clauses (no correlated `pk__in` subquery). Use this in `DjangoObjectType.get_queryset` overrides and reverse-relation field resolvers. | `QuerySet` |
| `BaseService.get_or_none(Model, pk, user, permission=None, *, request=None)` | IDOR-safe single-object fetch — returns `None` for both not-found and not-permitted so callers cannot enumerate via differential errors. | Instance \| `None` |
| `BaseService.require_permission(instance, user, permission, *, request=None, error_message=None)` | Fail-fast gate on a single object. Returns `""` on grant; a human-readable denial string otherwise — feed it straight into a `ServiceResult` / `ok=False` envelope. ⚠️ Truthy on **denial** (inverse of the legacy `if user_can(...)` idiom — see the in-method docstring). | `str` |
| `BaseService.user_has(instance, user, permission, *, request=None)` | Boolean yes/no for UI-state fields (`can_edit_summary`, `can_create_labels`, etc.). | `bool` |

Resolvers should always pass `request=info.context` so the Tier-2 permission
cache (`PermissionQueryOptimizer`) is shared across the request. The cache is
keyed by single object, so `request=` is only effective on the single-object
helpers (`get_or_none` / `require_permission` / `user_has`); on
`filter_visible` / `filter_visible_qs` it is accepted for API parity but is
currently a no-op.

## Tier-0 primitives (internal foundation)

`visible_to_user(user)` and `user_can(user, instance, permission)` live on
managers/querysets. They are the source of truth for "can this user see / do
this?", but they are **not** the recommended entry point for application code.
They power `BaseService.*` and per-app service methods.

| Model | Implementation | File |
|-------|---------------|------|
| Corpus | `PermissionedTreeQuerySet.visible_to_user` | `opencontractserver/shared/QuerySets.py` |
| Document | `DocumentQuerySet.visible_to_user` / `BaseVisibilityManager.visible_to_user` | `opencontractserver/shared/QuerySets.py`, `opencontractserver/shared/Managers.py` |
| Annotation / Note / Relationship | `*QuerySet.visible_to_user` | `opencontractserver/shared/QuerySets.py` |
| UserFeedback | `UserFeedbackQuerySet.visible_to_user` | `opencontractserver/shared/QuerySets.py` |
| Fallback | `PermissionQuerySet.visible_to_user` | `opencontractserver/shared/QuerySets.py` |

The single-object check is `Model.objects.user_can(user, obj, permission)` /
`obj.user_can(user, permission)` — paired with `visible_to_user` and pinned to
agree by `opencontractserver/tests/permissioning/test_authorization_invariants.py`.

## Per-app service inventory (Tier 1)

| App | Service module | Key methods |
|-----|----------------|-------------|
| `corpuses` | `services/corpus_service.py` (`CorpusService`) | `delete_corpus`, `set_visibility`, `update_description`, `grant_creator_permissions` |
| `corpuses` | `services/corpus_documents.py` (`CorpusDocumentService`) | `get_corpus_documents` (corpus-as-gate), `get_corpus_documents_visible_to_user` (MIN-perm), `get_corpus_document_by_id`/`by_slug`, `is_document_in_corpus`, doc add/remove |
| `corpuses` | `services/folders.py` (`FolderCRUDService`) | `get_visible_folders`, `get_folder_by_id`, `get_folder_tree`, folder CRUD |
| `corpuses` | `services/folder_documents.py` (`FolderDocumentService`) | `get_folder_documents`, `move_document_to_folder`, `get_document_folder` |
| `corpuses` | `services/lifecycle.py` (`DocumentLifecycleService`) | `get_deleted_documents`, `soft_delete_document`, `restore_document`, `permanently_delete_document`, `empty_trash` |
| `corpuses` | `services/paths.py` (`CorpusPathService`) | `DocumentPath` disambiguation internals |
| `documents` | `document_service.py` (`DocumentService`) | `get_document_by_id`, `create_document`, `set_document_permissions`, `check_user_upload_quota`, `validate_file_type` |
| `documents` | `services/actions.py` (`DocumentActionsService`) | `get_document_actions`, `get_extracts_for_document`, `get_analysis_rows_for_document` |
| `documents` | `services/relationships.py` (`DocumentRelationshipService`) | `get_visible_relationships`, `get_relationships_for_document`, `get_relationship_counts_by_document`, `user_has_permission` |
| `documents` | `services/versions.py` (`DocumentVersionService`) | `get_version_counts_by_tree` |
| `annotations` | `services/annotation_service.py` (`AnnotationService`) | `get_document_annotations`, `get_corpus_annotations`, `get_extract_annotation_summary` |
| `annotations` | `services/relationship_service.py` (`RelationshipService`) | `get_document_relationships`, `get_relationship_summary` |
| `analyzer` | `services/analysis_service.py` (`AnalysisService`) | `check_analysis_permission`, `get_visible_analyses`, `get_analysis_annotations` |
| `analyzer` | `services/analysis_lifecycle_service.py` (`AnalysisLifecycleService`) | `make_public`, `start_document_analysis`, `delete_analysis` |
| `extracts` | `services/extract_service.py` (`ExtractService`) | `check_extract_permission`, `get_visible_extracts`, `get_extract_datacells` |
| `extracts` | `services/metadata.py` (`MetadataService`) | `get_corpus_metadata_columns`, `get_document_metadata`, `get_documents_metadata_batch`, `check_metadata_mutation_permission` |
| `conversations` | `services/conversation_service.py` (`ConversationService`) | `get_threads_for_corpus`, `get_threads_for_document`, `get_chats_for_user`, `check_conversation_visibility`, `get_corpus_conversation_counts` |
| `users` | `services/user_service.py` (`UserService`) | `get_visible_users`, `check_user_visibility`, `get_users_for_mention` |
| `badges` | `services/badge_service.py` (`BadgeService`) | `get_visible_user_badges`, `check_user_badge_visibility`, `get_badges_for_user` |
| `agents` | `services/agent_configuration_service.py` (`AgentConfigurationService`) | `list_visible_agents`, `search_mentionable_agents`, `get_active_agents_by_slugs`, `get_agent_by_id`, agent CRUD |
| `agents` | `services/agent_action_result_service.py` (`AgentActionResultService`) | `list_visible_results` |
| `notifications` | `services/notification_service.py` (`NotificationService`) | `list_for_user`, `get_for_user`, `unread_count`, `mark_read` / `mark_unread` / `mark_all_read`, `delete_for_user` |
| `feedback` | `services/user_feedback_service.py` (`UserFeedbackService`) | `approve_annotation`, `reject_annotation` |
| `worker_uploads` | `services/corpus_access_token_service.py` (`CorpusAccessTokenService`) | `list_for_corpus`, `create_token`, `revoke_token` |
| `worker_uploads` | `services/worker_account_service.py` (`WorkerAccountService`) | `list_visible_accounts`, `create_worker_account`, `set_active` |
| `worker_uploads` | `services/worker_document_upload_service.py` (`WorkerDocumentUploadService`) | `list_for_corpus` |

## Permission models by object type

| Object | Own Permissions | Inherited From | Pattern |
|--------|----------------|----------------|---------|
| Corpus | Guardian (direct) | — | `read_corpus` via `corpususerobjectpermission` |
| Document | Guardian (direct) | — | `read_document` via `documentuserobjectpermission` |
| Annotation | None (inherited) | Document + Corpus | `MIN(document_permission, corpus_permission)` |
| Relationship | None (inherited) | Document + Corpus | Same as Annotation |
| Note | None (inherited) | Document + Corpus | Same as Annotation |
| Analysis | Hybrid | Own + Corpus | Own guardian permissions + corpus visibility |
| Extract | Hybrid | Own + Corpus | Own guardian permissions + corpus visibility |
| Conversation | Simple | Corpus + Document | Corpus and document visibility checks |

## Key patterns

### `MIN(document, corpus)` Permission Inheritance
Annotations, relationships, and notes have no individual guardian permissions.
Visibility is determined by the intersection of document and corpus visibility.
Implementation: `opencontractserver/shared/QuerySets.py` (AnnotationQuerySet, NoteQuerySet).

### Guardian Permission Table Lookup
For models with direct guardian permissions, query the
`{model}userobjectpermission` table directly instead of using
`get_objects_for_user` for better performance. Implementation:
`opencontractserver/shared/Managers.py`, `opencontractserver/shared/QuerySets.py`.

### Request-Level Caching
`ConversationService` and other Tier-1 services cache corpus and document
visibility subqueries per request to avoid repeated permission checks.

### Two-Tier `user_can` Caching (issue #1640)
Authorization checks via the centralized `Manager.user_can` / `obj.user_can` /
`_default_user_can` API are cached at two layers so repeated checks within a
single request collapse to one DB hit:

- **Tier 1 — Per-instance memoization.** `get_users_permissions_for_obj`
  caches its result on the instance as `_oc_granted_perms_cache: dict`,
  keyed by `(user_id, include_group_permissions_bool) → frozenset[str]`.
  Transparent to every caller of `user_can`.
- **Tier 2 — Request-scoped optimizer.** `PermissionQueryOptimizer` lives
  on the GraphQL request as `request._permission_query_optimizer`, keyed by
  `(user_id, content_type_id, instance_pk, include_group_permissions)`.
  Engaged by passing `request=` (any `BaseService` method threads it through
  for you).

Invalidation contract: `set_permissions_for_obj_to_user(..., request=...)`
clears both tiers for the affected `(user, instance)` pair when called
inside the HTTP lifecycle. Out-of-band changes (raw `assign_perm`/`remove_perm`,
migrations, Celery tasks reusing instances, group-permission changes) bypass
this hook — callers must invalidate manually via
`delattr(instance, INSTANCE_PERMS_CACHE_ATTR)` and/or
`get_request_optimizer(request).invalidate(user_id=..., instance=...)`.

Implementation: `opencontractserver/utils/permission_optimizer.py`,
`opencontractserver/utils/permissioning.py:get_users_permissions_for_obj`,
`opencontractserver/utils/permissioning.py:_default_user_can`.

Tests: `opencontractserver/tests/permissioning/test_permission_optimizer.py`.

### Analysis/Extract Privacy Filtering
Annotations created by analyses or extracts inherit visibility from those
parent objects. If a user cannot see the analysis/extract, they cannot see
its annotations. Implementation:
`opencontractserver/shared/QuerySets.py` (AnnotationQuerySet).

### IDOR Protection
Mutations use `BaseService.get_or_none` with unified error messages to prevent
object ID enumeration. The helper returns `None` for both not-found and
not-permitted, so the caller surfaces a single string that does not leak
which condition failed.

### Structural Annotation Handling
Structural annotations (headers, sections) are always visible if the parent
document is visible, regardless of creator. They are read-only for
non-superusers. Implementation: `opencontractserver/shared/QuerySets.py`
(AnnotationQuerySet visibility_filter).

## Enforcement

See [`docs/development/architecture_invariants.md`](../development/architecture_invariants.md)
for the invariant index and the pattern for adding new ones.

Two independent layers point at the same scanner
(`opencontractserver/shared/architecture_audit.py`) so a violation cannot
slip through either:

1. **Django system check** (`opencontractserver/shared/checks.py`,
   registered via `users/apps.py:ready()`). Fires on every management
   command — `manage.py runserver`, `migrate`, `shell`, `test`,
   `check --deploy`. Emits `opencontracts.E001` and blocks the command
   with a non-zero exit code on any inline Tier-0 use. This is the
   "fail on startup" guardrail — devs see violations immediately on
   the first `manage.py` invocation, not only when CI runs pytest.
2. **Pytest invariant**
   (`opencontractserver/tests/architecture/test_graphql_service_layer.py`).
   Runs in CI on every push, alongside `test_authorization_invariants`
   and `test_security_hardening`. Pins the same scanner plus a
   regression test that the Django check stays registered.

The allowlist
(`opencontractserver.shared.architecture_audit.ALLOWED_FILES`) is empty.
Every `config/graphql/` module is scanned (recursively, including
subpackages such as `permissioning/permission_annotator/`) — `filters.py`
no longer needs an entry because its only remaining references to forbidden
identifiers are inside comments (which the AST scanner already ignores).

**Enforcement scope (important):** both layers scan **`config/graphql/`
only**. The "always go through services" rule is *policy* for the other
user-context surfaces — MCP tools (`opencontractserver/mcp/`), LLM tools
(`opencontractserver/llms/tools/`), REST views, and user-context Celery
tasks — but the scanner does **not** cover them yet, and they still contain
correct-but-inline Tier-0 calls. A green `opencontracts.E001` means "no
inline Tier-0 in `config/graphql/`," not "none anywhere." Expanding the
scan to those packages (after migrating their existing inline usage) is
tracked as future work.

When you add a new resolver/mutation/MCP tool/REST view that needs
permission-filtered access, either:

1. Call an existing dedicated service method (preferred when one matches your
   operation semantically).
2. Call `BaseService.{get_or_none, filter_visible, filter_visible_qs,
   require_permission, user_has}` directly for generic "list visible X" /
   "chain visibility onto an existing queryset" / "fetch X for user" /
   "gate write on X" / "boolean has-perm-on-X" operations.

Do **not** import Tier-0 identifiers into consumer code.

## See Also

- `docs/permissioning/consolidated_permissioning_guide.md` — full permissioning architecture
- `docs/architecture/sharing.md` — object sharing patterns
- `docs/refactor_plans/2026-05-19-service-layer-centralization-design.md` — the design that produced this layering
