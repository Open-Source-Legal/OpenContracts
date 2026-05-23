# Query Permission Patterns

Reference for how OpenContracts filters querysets by user permissions.

## Architecture Overview

Permission filtering uses two layers:

1. **Managers & QuerySets** — `visible_to_user()` methods that filter querysets to objects a user can see
2. **Query Optimizers** — GraphQL resolver helpers that add prefetches, select_related, and bulk permission checks to avoid N+1 queries

Both layers work together: the manager/queryset produces the base filtered set, and the optimizer adds performance tuning for the GraphQL context.

## Layer 1: visible_to_user() Implementations

| Model | Implementation | File | Pattern |
|-------|---------------|------|---------|
| Corpus | `PermissionedTreeQuerySet.visible_to_user` | `opencontractserver/shared/QuerySets.py:30-86` | Guardian via `get_objects_for_user` |
| Document | `DocumentQuerySet.visible_to_user` | `opencontractserver/shared/QuerySets.py:193-229` | Guardian permission table lookup |
| Document (manager) | `BaseVisibilityManager.visible_to_user` | `opencontractserver/shared/Managers.py:40-203` | Guardian + model-specific prefetches |
| Annotation | `AnnotationQuerySet.visible_to_user` | `opencontractserver/shared/QuerySets.py:245-379` | Guardian on doc/corpus + analysis/extract privacy |
| Note | `NoteQuerySet.visible_to_user` | `opencontractserver/shared/QuerySets.py:368-399` | Document + corpus inheritance |
| UserFeedback | `UserFeedbackQuerySet.visible_to_user` | `opencontractserver/shared/QuerySets.py:112-133` | Creator + public + annotation visibility |
| Fallback | `PermissionQuerySet.visible_to_user` | `opencontractserver/shared/QuerySets.py:137-184` | Creator + public only (no guardian) |

**Important:** When code calls `Model.objects.filter(...).visible_to_user(user)`, the `.filter()` returns a QuerySet (not a Manager), so the QuerySet's `visible_to_user` is invoked. Models that need guardian checks must override `visible_to_user` on their QuerySet class, not just the Manager.

## Layer 2: Query Optimizers

| Optimizer | File | Scope |
|-----------|------|-------|
| `AnnotationService` | `opencontractserver/annotations/services/annotation_service.py` | Annotation bulk permissions |
| `RelationshipService` | `opencontractserver/annotations/services/relationship_service.py` | Relationship bulk permissions |
| `AnalysisService` | `opencontractserver/analyzer/services/analysis_service.py` | Analysis visibility with corpus checks |
| `ExtractService` | `opencontractserver/extracts/services/extract_service.py` | Extract visibility with corpus checks |
| `ConversationService` | `opencontractserver/conversations/services/conversation_service.py` | Request-level caching for corpus/doc visibility |
| `PermissionQueryOptimizer` | `opencontractserver/utils/permission_optimizer.py` | Per-request `user_can` cache for any visibility-managed model |
| `DocumentActionsService` | `opencontractserver/documents/services/actions.py` | Document action permissions |
| `DocumentRelationshipService` | `opencontractserver/documents/services/relationships.py` | Document relationship permissions |
| `DocumentVersionService` | `opencontractserver/documents/services/versions.py` | Document version-tree counts |
| `MetadataService` | `opencontractserver/extracts/services/metadata.py` | Extract metadata permissions |
| `BadgeService` | `opencontractserver/badges/services/badge_service.py` | Badge visibility |
| `UserService` | `opencontractserver/users/services/user_service.py` | User profile permissions |

## Permission Models by Object Type

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

## Key Patterns

### MIN(document, corpus) Permission Inheritance
Annotations, relationships, and notes have no individual guardian permissions. Visibility is determined by the intersection of document and corpus visibility.
- Implementation: `opencontractserver/shared/QuerySets.py` (AnnotationQuerySet, NoteQuerySet)

### Guardian Permission Table Lookup
For models with direct guardian permissions, query the `{model}userobjectpermission` table directly instead of using `get_objects_for_user` for better performance.
- Implementation: `opencontractserver/shared/Managers.py:103-118`
- Also: `opencontractserver/shared/QuerySets.py:210-225` (DocumentQuerySet)

### Request-Level Caching
`ConversationService` caches corpus and document visibility subqueries per request to avoid repeated permission checks.
- Implementation: `opencontractserver/conversations/services/conversation_service.py`

### Two-Tier `user_can` Caching (issue #1640)
Authorization checks via the centralized `Manager.user_can` / `obj.user_can` /
`_default_user_can` API are cached at two layers so repeated checks within a
single request collapse to one DB hit:

- **Tier 1 — Per-instance memoization.** `get_users_permissions_for_obj`
  caches its result on the instance as `_oc_granted_perms_cache: dict`,
  keyed by `(user_id, include_group_permissions_bool) → frozenset[str]`.
  Transparent to every caller of `user_can`. No plumbing needed.
- **Tier 2 — Request-scoped optimizer.** `PermissionQueryOptimizer` lives
  on the GraphQL request as `request._permission_query_optimizer` (key in
  `opencontractserver/constants/permissioning.py`), keyed by
  `(user_id, content_type_id, instance_pk, include_group_permissions)`.
  Opt-in via the new `request=` kwarg threaded through `Manager.user_can`
  / `obj.user_can` / `_default_user_can`. Lets multiple instances of the
  same model in one request share a cache (e.g. paginated `my_permissions`
  resolvers).

Invalidation contract: `set_permissions_for_obj_to_user(..., request=...)`
clears both tiers for the affected `(user, instance)` pair when called
inside the HTTP lifecycle. The following changes flow around this hook
and leave cached entries computed with `include_group_permissions=True`
stale — callers must invalidate manually:

- Out-of-band guardian perm changes (raw `assign_perm`/`remove_perm`,
  migrations, Celery tasks reusing instances) → `delattr(instance,
  INSTANCE_PERMS_CACHE_ATTR)` and/or
  `get_request_optimizer(request).invalidate(user_id=..., instance=...)`.
- Group-permission changes — `user.groups.add(group)`, `user.groups.remove(group)`,
  or `assign_perm(perm, group, obj)` — same remedy.
- `refresh_from_db()` reloads model fields but does not touch the
  Tier 1 attribute; same remedy applies if the instance is reused.

#### Operator note — group-level guardian usage in this codebase

The Tier 1 / Tier 2 caches treat `include_group_permissions=True` as the
default (the alignment that made the two layers a "one default, one answer"
contract). Group-permission staleness is therefore valid for the entire
request lifetime once a granted-set is cached. Two facts limit the actual
exposure today, but neither is a guarantee for future installations:

- **No production call site assigns guardian permissions to a `Group`.**
  As of this writing, the only `assign_perm(...)` callers in
  `opencontractserver/utils/permissioning.py:182-248` route through the
  user-targeted form `assign_perm(perm, user, obj)`. The
  `*GroupObjectPermission` tables (`DocumentGroupObjectPermission`,
  `ConversationGroupObjectPermission`, etc.) are *defined* on every
  visibility-managed model and *queried* on the read path
  (`DocumentManager._prefetch_user_group_perm_attr` and the guardian
  lookup inside `get_users_permissions_for_obj`), but no shipped code
  writes to them.
- **Tenants that wire guardian group permissions on their own — via the
  Django admin, a custom mutation, or a data migration — own
  invalidation.** After any `assign_perm(perm, group, obj)` /
  `remove_perm(...)` or `user.groups.add(...)` /
  `user.groups.remove(...)` performed mid-request, the caller must
  `delattr(instance, INSTANCE_PERMS_CACHE_ATTR)` and/or
  `get_request_optimizer(request).invalidate(user_id=..., instance=...)`
  before the next `user_can` check on the affected `(user, instance)`
  pair. The mutation-side hook in `set_permissions_for_obj_to_user`
  only handles the user-targeted path it owns.

If your deployment starts using group-targeted guardian permissions for
the first time, audit every mutation that touches group membership or
group perms and add the matching invalidate call. The caches will not
flag the staleness for you.

- Implementation: `opencontractserver/utils/permission_optimizer.py`,
  `opencontractserver/utils/permissioning.py:get_users_permissions_for_obj`,
  `opencontractserver/utils/permissioning.py:_default_user_can`
- Tests: `opencontractserver/tests/permissioning/test_permission_optimizer.py`

### Analysis/Extract Privacy Filtering
Annotations created by analyses or extracts inherit visibility from those parent objects. If a user cannot see the analysis/extract, they cannot see its annotations.
- Implementation: `opencontractserver/shared/QuerySets.py:251-291` (AnnotationQuerySet)

### IDOR Protection
Mutations use `visible_to_user()` filtering with unified error messages to prevent object ID enumeration.
- Single-object check: `Manager.user_can()` / `obj.user_can()` (`opencontractserver/utils/permissioning.py` — `_default_user_can`)
- Permission assignment: `opencontractserver/utils/permissioning.py:20-163` (`set_permissions_for_obj_to_user`)

### Structural Annotation Handling
Structural annotations (headers, sections) are always visible if the parent document is visible, regardless of creator. They are read-only for non-superusers.
- Implementation: `opencontractserver/shared/QuerySets.py:276-278` (AnnotationQuerySet visibility_filter)

## See Also

- `docs/permissioning/consolidated_permissioning_guide.md` — full permissioning architecture
- `docs/architecture/sharing.md` — object sharing patterns
