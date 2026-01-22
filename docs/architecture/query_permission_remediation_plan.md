# Query Permission System Remediation Plan

This document outlines improvements identified during the January 2026 audit of the query optimizer and `visible_to_user()` implementations.

## Status Legend

- 🔴 **High Priority** - Security or correctness issues requiring immediate attention
- 🟡 **Medium Priority** - Code quality and maintainability improvements
- 🟢 **Low Priority** - Nice-to-have optimizations and cleanup

---

## 🔴 High Priority

### H1: Audit DocumentManager Permission Inheritance

**Issue**: There are two implementations of `visible_to_user()` with different behavior:

- `BaseVisibilityManager.visible_to_user()` (lines 40-197) - Checks guardian permissions
- `PermissionQuerySet.visible_to_user()` (lines 137-184) - Only checks `is_public` and `creator`

`DocumentManager` inherits from `BaseVisibilityManager` but uses `DocumentQuerySet` which inherits from `PermissionQuerySet`. Need to verify the correct implementation is being used.

**Risk**: Documents shared via guardian permissions (not public, not creator-owned) may not appear in `Document.objects.visible_to_user()` results.

**Location**:
- `opencontractserver/shared/Managers.py:269-286` (DocumentManager)
- `opencontractserver/shared/QuerySets.py:136-184` (PermissionQuerySet)

**Action Items**:
1. [ ] Write a test case that creates a document, shares it with another user via `set_permissions_for_obj_to_user()`, and verifies it appears in `visible_to_user()` results
2. [ ] Trace the inheritance chain to confirm which `visible_to_user()` implementation is invoked
3. [ ] If guardian permissions are not being checked, fix the inheritance or override appropriately
4. [ ] Add inline documentation clarifying the inheritance chain

**Test Script Location**: `docs/test_scripts/test_document_guardian_permissions.md`

---

### H2: Document Metadata Permission Model Divergence

**Issue**: Metadata (Datacells) uses a **different** permission model than annotations:

| Object | Permission Model |
|--------|------------------|
| Annotations | `MIN(document_perm, corpus_perm)` |
| Metadata | `corpus_perm + document_visibility` |

This is intentional but undocumented, creating potential confusion and security review gaps.

**Location**: `opencontractserver/extracts/query_optimizer.py:452-529` (`check_metadata_mutation_permission`)

**Action Items**:
1. [ ] Add a "Special Permission Models" section to `docs/permissioning/consolidated_permissioning_guide.md`
2. [ ] Document the rationale: metadata schemas are corpus-level features
3. [ ] Add inline comments in `MetadataQueryOptimizer` explaining the divergence
4. [ ] Review all metadata mutation endpoints to ensure they use `check_metadata_mutation_permission()`

---

## 🟡 Medium Priority

### M1: Extract Shared Permission Computation Utility

**Issue**: The same permission computation logic is duplicated across multiple optimizers:

- `AnnotationQueryOptimizer._compute_effective_permissions()` (lines 29-140)
- `MetadataQueryOptimizer._compute_effective_permissions()` (lines 34-109)
- `DocumentActionsQueryOptimizer._check_document_permission()` (lines 116-156)
- `DocumentActionsQueryOptimizer._check_corpus_permission()` (lines 158-198)

**Risk**: Bug fixes or changes must be applied to multiple locations; easy to miss one.

**Action Items**:
1. [ ] Create `compute_doc_corpus_permissions(user, document_id, corpus_id)` in `opencontractserver/utils/permissioning.py`
2. [ ] Return a named tuple or dataclass: `EffectivePermissions(can_read, can_create, can_update, can_delete, can_comment)`
3. [ ] Refactor all optimizers to use the shared utility
4. [ ] Add comprehensive unit tests for the shared utility
5. [ ] Ensure backward compatibility by keeping old method signatures as thin wrappers

**Estimated Scope**: 4-6 files modified, ~200 lines of code

---

### M2: Standardize visible_to_user() Implementations

**Issue**: There are 7+ different implementations with varying logic, making the codebase harder to understand and maintain.

**Current Implementations**:
| Implementation | Checks Guardian | Checks Creator | Checks Public | Special Logic |
|----------------|-----------------|----------------|---------------|---------------|
| `BaseVisibilityManager` | ✅ | ✅ | ✅ | Model-specific prefetches |
| `PermissionQuerySet` | ❌ | ✅ | ✅ | None |
| `AnnotationQuerySet` | ❌ | ✅ | ✅ | Privacy filtering |
| `UserProfileManager` | N/A | ✅ | ✅ | Profile privacy |
| `PermissionedTreeQuerySet` | ✅ | ✅ | ✅ | Tree fields |

**Action Items**:
1. [ ] Create a checklist of what each implementation should check
2. [ ] Document why each model needs custom logic (or doesn't)
3. [ ] Consider creating a base mixin with configurable flags:
   ```python
   class VisibilityMixin:
       check_guardian_permissions = True
       check_creator = True
       check_public = True
   ```
4. [ ] Add tests for each implementation verifying correct behavior

---

### M3: Add Request-Level Caching to Other Optimizers

**Issue**: `DocumentRelationshipQueryOptimizer` implements excellent request-level caching, but other frequently-used optimizers don't.

**Candidates for Caching**:
- `AnnotationQueryOptimizer` - Called multiple times per document view
- `RelationshipQueryOptimizer` - Same
- `BadgeQueryOptimizer` - Called for each user profile view

**Action Items**:
1. [ ] Add optional `context` parameter to optimizer methods
2. [ ] Implement caching pattern from `DocumentRelationshipQueryOptimizer` (lines 340-406)
3. [ ] Update GraphQL resolvers to pass `info.context` to optimizers
4. [ ] Add cache invalidation documentation

**Template**:
```python
_CACHE_KEY = "_annotation_optimizer_cache"

@classmethod
def get_document_annotations(cls, document_id, user, context=None, **kwargs):
    if context is not None:
        cache_key = f"{cls._CACHE_KEY}_{document_id}_{user.id}"
        if hasattr(context, cache_key):
            return getattr(context, cache_key)

    result = cls._compute_annotations(document_id, user, **kwargs)

    if context is not None:
        setattr(context, cache_key, result)

    return result
```

---

### M4: Consistent Creator Permission Handling

**Issue**: Creator status grants different permissions depending on whether the model has guardian tables:

- **Without guardian tables**: Creator gets full CRUD (lines 234-240 in `permissioning.py`)
- **With guardian tables**: Creator must have permissions explicitly set (usually via signal handlers)

**Risk**: If signal handlers fail or are bypassed, creators may lose access to their own objects.

**Action Items**:
1. [ ] Audit all models to verify signal handlers correctly set creator permissions
2. [ ] Consider adding a fallback in `get_users_permissions_for_obj()` to always grant CRUD to creators
3. [ ] Document the expected behavior in the permissioning guide
4. [ ] Add tests verifying creators always have CRUD on their objects

---

## 🟢 Low Priority

### L1: Change Warning to Debug in BaseVisibilityManager

**Issue**: `BaseVisibilityManager.visible_to_user()` logs a warning on every call (lines 77-79):

```python
logger.warning(
    f"Consider implementing tuned visible_to_user method on {model_name} manager"
)
```

This generates unnecessary log noise in production.

**Action Items**:
1. [ ] Change `logger.warning` to `logger.debug`
2. [ ] Or remove the log entirely and add a code comment instead

**Location**: `opencontractserver/shared/Managers.py:77-79`

---

### L2: Add Index Recommendations for Guardian Tables

**Issue**: Permission subqueries in `BaseVisibilityManager` could benefit from indexes on guardian tables.

**Action Items**:
1. [ ] Analyze slow query logs for permission-related queries
2. [ ] Consider adding indexes:
   ```sql
   CREATE INDEX idx_userobjectperm_user_content
   ON {model}_userobjectpermission (user_id, content_object_id);
   ```
3. [ ] Benchmark before and after
4. [ ] Document index requirements for large deployments

---

### L3: Deprecate Legacy Method Signatures

**Issue**: Several optimizers have deprecated methods that should be removed:

- `AnnotationQueryOptimizer._check_document_permission()` (lines 476-484)
- `AnnotationQueryOptimizer._apply_permission_filter()` (lines 487-493)
- `RelationshipQueryOptimizer._apply_permission_filter()` (lines 764-770)

**Action Items**:
1. [ ] Search codebase for any remaining usages of deprecated methods
2. [ ] Remove deprecated methods if no usages found
3. [ ] If usages exist, add deprecation warnings and plan removal timeline

---

### L4: Add Permission Computation Metrics

**Issue**: No visibility into how often permissions are computed or how long they take.

**Action Items**:
1. [ ] Add metrics/logging for permission computation:
   - Count of `_compute_effective_permissions()` calls per request
   - Time spent in permission computation
2. [ ] Use Django's `connection.queries` in debug mode to count queries
3. [ ] Consider adding OpenTelemetry spans for permission checks
4. [ ] Create dashboard for monitoring permission system performance

---

### L5: Unify Annotation and Relationship visible_to_user()

**Issue**: Annotations use `AnnotationQuerySet.visible_to_user()` while Relationships inherit from `BaseVisibilityManager`. Both should use the same permission model but are implemented differently.

**Action Items**:
1. [ ] Review `Relationship.objects.visible_to_user()` implementation
2. [ ] Verify it correctly handles:
   - Privacy filtering for analysis/extract-created relationships
   - Structural relationship special rules
3. [ ] Consider creating `RelationshipQuerySet` with parallel logic to `AnnotationQuerySet`
4. [ ] Or refactor both to use query optimizers exclusively for visibility

---

## Implementation Order Recommendation

```
Phase 1 (Immediate):
├── H1: Audit DocumentManager (security verification)
└── H2: Document metadata permissions (documentation)

Phase 2 (Next Sprint):
├── M1: Extract shared permission utility (foundation)
├── M4: Creator permission handling (security hardening)
└── L1: Fix warning log level (quick win)

Phase 3 (Following Sprint):
├── M2: Standardize visible_to_user() (maintainability)
├── M3: Add request-level caching (performance)
└── L3: Remove deprecated methods (cleanup)

Phase 4 (Backlog):
├── L2: Index recommendations (performance)
├── L4: Permission metrics (observability)
└── L5: Unify annotation/relationship (consistency)
```

---

## Testing Requirements

For each remediation item, tests should verify:

1. **Positive cases**: Users with correct permissions can access objects
2. **Negative cases**: Users without permissions cannot access objects
3. **Edge cases**: Superusers, anonymous users, public objects, creator access
4. **Performance**: No N+1 queries introduced
5. **Regression**: Existing functionality preserved

Test locations:
- Unit tests: `opencontractserver/tests/test_permissions.py`
- Integration tests: `opencontractserver/tests/test_graphql_permissions.py`

---

## Success Metrics

After completing all remediations:

- [ ] Zero security issues identified in permission system audit
- [ ] All permission implementations documented
- [ ] < 5 permission-related queries per GraphQL request (measured)
- [ ] Single source of truth for permission computation
- [ ] 100% test coverage for permission utilities
