# OpenContracts Permission Remediation Guide

**Date**: 2025-12-27
**Based on**: Audit of GraphQL mutations, Celery tasks, and comparison against `consolidated_permissioning_guide.md`

---

## ⚠️ Status Update (post-audit)

**Most of the CRITICAL findings below have been fixed in code.** This document is preserved as the historical audit record. Verification spot-checks:

| Finding (CRITICAL) | Current status in `main` | Code reference |
|---|---|---|
| `RemoveRelationships` — no permission check | ✅ Fixed: now uses `Relationship.objects.visible_to_user(user)` + `user_has_permission_for_obj()` | `config/graphql/annotation_mutations.py:725-757` |
| `UpdateRelations` — no permission check | ✅ Fixed: `visible_to_user()` gate before update | `config/graphql/annotation_mutations.py:937+` |
| `StartCorpusFork` | ✅ Fixed: `visible_to_user()` + explicit READ check | `config/graphql/corpus_mutations.py` |
| `DeleteMultipleLabelMutation` | ✅ Fixed: creator-ownership + read-only flag check | `config/graphql/label_mutations.py` |
| `StartQueryForCorpus`, `StartCorpusExport`, `StartDocumentExtract` | ✅ Fixed | corresponding mutation files |

In addition, the more recent **Auth0 permissioning audit** (recorded in `CHANGELOG.md` under "Security / Auth0 permissioning audit") shipped further defense-in-depth changes:

- `AUTH0_SUPERUSER_SUB_ALLOWLIST` allowlist for `is_superuser` JWT-claim sync (F1)
- `ADMIN_CLAIMS_CACHE_TTL` tightened from 300 s → 30 s (F2)
- `AddRelationship` IDOR oracle eliminated; document-ID is now visibility-checked (F3 + F4)
- `CreateMetadataColumn` / `UpdateMetadataColumn` existence oracles eliminated (F5, F6)
- `Datacell` mutation broad-except message leaks closed (F7)
- Bounded JWKS stale-cache fallback (F9)
- `Analysis.callback_token` now hashed at rest (F10)

The CHANGELOG entry also lists **verified false positives** (e.g., `SetCorpusVisibility`, `AnnotationImagesView`, moderation mutations) — items this guide may have over-stated.

**When reading this document, treat each finding as historical context** and verify the current code state before acting. Open issues (if any) should be tracked separately in GitHub.

---

## Executive Summary

This guide consolidates and **corrects** the findings from the GraphQL and Task audit reports. After careful code review, the original reports contained several inaccuracies and overstated claims. This guide provides:

1. **Verified vulnerabilities** with accurate severity ratings
2. **Corrections** to overstated or incorrect claims
3. **Risk-adjusted priorities** based on actual exploitability
4. **Complete inventory** of non-compliant code requiring remediation

### Corrected Risk Summary

| Severity | Count | Description |
|----------|-------|-------------|
| 🔴 **CRITICAL** | 7 | Missing permission checks in GraphQL mutations - directly exploitable |
| 🟠 **HIGH** | 5 | IDOR information leakage, missing `include_group_permissions` |
| 🟡 **MEDIUM** | 6 | Defense-in-depth violations, DRY opportunities |
| 🟢 **LOW** | 4 | Code quality, minor inconsistencies |

**Key Finding**: The Task audit report claimed 47 critical task vulnerabilities. This is **misleading**. Tasks are internal implementation details called by GraphQL mutations - they are NOT directly exposed in production. The real vulnerabilities are in the **7 GraphQL mutations** that lack permission checks before calling these tasks.

---

## Part 1: Verified Critical Vulnerabilities (Fix Immediately)

### 1.1 RemoveRelationships - NO PERMISSION CHECK

**File**: `config/graphql/mutations.py`
**Lines**: 2338-2350
**Severity**: 🔴 CRITICAL
**Impact**: Any authenticated user can delete ANY relationship by ID

```python
# CURRENT (VULNERABLE):
@login_required
def mutate(root, info, relationship_ids):
    relation_pks = list(map(lambda graphene_id: from_global_id(graphene_id)[1], relationship_ids))
    Relationship.objects.filter(id__in=relation_pks).delete()  # ❌ NO PERMISSION CHECK
    return RemoveRelationships(ok=True)
```

**Required Fix**:
```python
@login_required
def mutate(root, info, relationship_ids):
    user = info.context.user
    for graphene_id in relationship_ids:
        pk = from_global_id(graphene_id)[1]
        try:
            relationship = Relationship.objects.get(pk=pk)
            if not user_has_permission_for_obj(
                user, relationship, PermissionTypes.DELETE, include_group_permissions=True
            ):
                return RemoveRelationships(ok=False, message="Permission denied")
            relationship.delete()
        except Relationship.DoesNotExist:
            return RemoveRelationships(ok=False, message="Relationship not found")
    return RemoveRelationships(ok=True)
```

---

### 1.2 UpdateRelations - NO PERMISSION CHECK

**File**: `config/graphql/mutations.py`
**Lines**: 2508-2545
**Severity**: 🔴 CRITICAL
**Impact**: Any authenticated user can modify ANY relationship

```python
# CURRENT (VULNERABLE):
@login_required
def mutate(root, info, relationships):
    for relationship in relationships:
        pk = from_global_id(relationship["id"])[1]
        # ...
        relationship = Relationship.objects.get(id=pk)  # ❌ NO PERMISSION CHECK
        relationship.relationship_label_id = relationship_label_pk
        relationship.save()
```

**Required Fix**: Add `user_has_permission_for_obj` check before modifying each relationship, matching the pattern in `UpdateRelationship` (lines 2402-2413).

---

### 1.3 StartCorpusFork - Missing READ Permission Check

**File**: `config/graphql/mutations.py`
**Lines**: 1067-1148
**Severity**: 🔴 CRITICAL
**Impact**: Any authenticated user can fork ANY corpus by ID, including private corpuses

```python
# CURRENT (VULNERABLE - line 1099):
corpus = Corpus.objects.get(pk=corpus_pk)  # ❌ No visibility check
```

**Required Fix**:
```python
try:
    corpus = Corpus.objects.visible_to_user(info.context.user).get(pk=corpus_pk)
except Corpus.DoesNotExist:
    return StartCorpusFork(ok=False, message="Corpus not found", new_corpus=None)

# Verify READ permission
if not user_has_permission_for_obj(
    info.context.user, corpus, PermissionTypes.READ, include_group_permissions=True
):
    return StartCorpusFork(ok=False, message="Corpus not found", new_corpus=None)
```

---

### 1.4 StartQueryForCorpus - Missing Corpus Access Check

**File**: `config/graphql/mutations.py`
**Lines**: 1151-1197
**Severity**: 🔴 CRITICAL
**Impact**: Any authenticated user can create queries for ANY corpus

```python
# CURRENT (VULNERABLE - line 1184-1188):
obj = CorpusQuery.objects.create(
    query=query,
    creator=info.context.user,
    corpus_id=from_global_id(corpus_id)[1],  # ❌ No access check on corpus
)
```

**Required Fix**: Add corpus visibility check before creating query.

---

### 1.5 StartCorpusExport - Missing Corpus Permission Check

**File**: `config/graphql/mutations.py`
**Lines**: 1200-1380
**Severity**: 🔴 CRITICAL
**Impact**: Any authenticated user can export ANY corpus

```python
# CURRENT (VULNERABLE - lines 1283-1285):
corpus_pk = from_global_id(corpus_id)[1]
export = UserExport.objects.create(...)  # ❌ No corpus permission check
```

**Required Fix**: Add visibility check and READ permission verification on corpus before creating export.

---

### 1.6 StartDocumentExtract - Missing Document/Fieldset Check

**File**: `config/graphql/mutations.py`
**Lines**: 2995-3037
**Severity**: 🔴 CRITICAL
**Impact**: Any authenticated user can create extracts for ANY document/fieldset

```python
# CURRENT (VULNERABLE - lines 3013-3014):
document = Document.objects.get(pk=doc_pk)  # ❌ No permission check
fieldset = Fieldset.objects.get(pk=fieldset_pk)  # ❌ No permission check
```

**Required Fix**:
```python
try:
    document = Document.objects.visible_to_user(info.context.user).get(pk=doc_pk)
    fieldset = Fieldset.objects.visible_to_user(info.context.user).get(pk=fieldset_pk)
except (Document.DoesNotExist, Fieldset.DoesNotExist):
    return StartDocumentExtract(ok=False, message="Resource not found", obj=None)
```

---

### 1.7 DeleteMultipleLabelMutation - No Permission Check

**File**: `config/graphql/mutations.py`
**Lines**: 2557-2586
**Severity**: 🔴 CRITICAL
**Impact**: Any authenticated user can delete ANY annotation labels

```python
# CURRENT (VULNERABLE - lines 2577-2578):
labels = AnnotationLabel.objects.filter(pk__in=label_pks)
labels.delete()  # ❌ NO PERMISSION CHECK
```

**Required Fix**: Add permission check for each label before deletion.

---

## Part 2: High Severity Issues

### 2.1 Badge Mutation IDOR Enumeration

**File**: `config/graphql/badge_mutations.py`
**Lines**: 399-403, 500-501
**Severity**: 🟠 HIGH
**Impact**: Badge/User ID enumeration via different error messages

**Note**: The original report claimed these were CRITICAL. However, review shows:
- Permission checks ARE performed before awarding/revoking (lines 419-431, 505-516)
- The issue is information disclosure (enumeration), NOT unauthorized action
- Different error messages reveal existence of badges/users

**Required Fix**: Use `visible_to_user()` pattern and consistent error messages.

---

### 2.2 Moderation Mutation IDOR Leakage

**File**: `config/graphql/moderation_mutations.py`
**Lines**: 60-71, 120-132, 181-193, 242-254
**Severity**: 🟠 HIGH
**Impact**: Conversation ID enumeration via different error messages

```python
# CURRENT (lines 61-71):
except Conversation.DoesNotExist:
    return LockThreadMutation(ok=False, message="Conversation not found", obj=None)
# Later:
if not conversation.can_moderate(user):
    return LockThreadMutation(ok=False, message="You do not have permission...", obj=None)
```

**Required Fix**: Use same message for both cases:
```python
# Either not found or no permission - same message
return LockThreadMutation(ok=False, message="Conversation not found", obj=None)
```

---

### 2.3 Missing include_group_permissions in Some Mutations

**File**: `config/graphql/mutations.py`
**Lines**: Various
**Severity**: 🟠 HIGH
**Impact**: Group-based permissions (including public access) may not work correctly

**Affected locations** (need verification):
- Line 447: `CreateMetadataColumn`
- Line 545: `UpdateMetadataColumn`
- Line 619: `SetMetadataValue`
- Line 695: `DeleteMetadataValue`

---

## Part 3: Report Corrections

### 3.1 INCORRECT: Corpus Folder Mutations

**Original Claim**: 6 CRITICAL IDOR vulnerabilities in corpus_folder_mutations.py

**Reality**: These mutations correctly delegate to `CorpusObjsService` which has proper permission checks:
- `check_corpus_write_permission()` (lines 154-196)
- `check_corpus_delete_permission()` (lines 199-237)
- Uses `user_has_permission_for_obj` with `include_group_permissions=True`

**Verdict**: ✅ No remediation needed for corpus folder mutations themselves. Minor IDOR improvement possible (consistent error messages).

---

### 3.2 INCORRECT: SetCorpusVisibility

**Original Claim**: Missing permission check

**Reality**: Proper permission checks exist at lines 253-265:
```python
can_change_visibility = (
    user.is_superuser
    or corpus.creator_id == user.id
    or user_has_permission_for_obj(user, corpus, PermissionTypes.PERMISSION, include_group_permissions=True)
)
```

**Verdict**: ✅ No remediation needed.

---

### 3.3 OVERSTATED: Task-Level Vulnerabilities

**Original Claim**: 47 CRITICAL vulnerabilities in Celery tasks

**Reality**:
1. Celery Flower is NOT exposed in production (only in `local.yml`)
2. Tasks are internal implementation called by GraphQL mutations
3. The actual vulnerabilities are in the 7 GraphQL mutations listed above
4. Task-level checks would be defense-in-depth, not primary security

**Verdict**: Task remediation is MEDIUM priority (defense-in-depth), not CRITICAL.

---

### 3.4 CLARIFICATION: Conversation Permission Formula

**Original Claim**: CreateThreadMessageMutation and ReplyToMessageMutation violate permission formula

**Reality**: These mutations DO check `user_has_permission_for_obj` on the conversation. The "formula violation" refers to edge cases with THREAD type conversations that have both corpus AND document set. This is a nuanced issue, not a complete bypass.

**Verdict**: 🟡 MEDIUM - Worth reviewing but not a critical vulnerability.

---

## Part 4: DRY Consolidation Opportunities

### 4.1 Creator-Only Pattern (7 instances)

**Files**: `config/graphql/mutations.py`
**Pattern**: `obj = Model.objects.get(pk=pk, creator=info.context.user)`

**Issue**: Bypasses permission system, prevents sharing/delegation

**Recommendation**: Create helper:
```python
def get_object_with_permission(model, pk, user, permission_type):
    """Get object and verify user has permission, with IDOR protection."""
    try:
        obj = model.objects.visible_to_user(user).get(pk=pk)
    except model.DoesNotExist:
        raise PermissionError(f"{model.__name__} not found")

    if not user_has_permission_for_obj(user, obj, permission_type, include_group_permissions=True):
        raise PermissionError(f"{model.__name__} not found")

    return obj
```

---

### 4.2 Notification Retrieval Pattern (3 instances)

**File**: `config/graphql/notification_mutations.py`
**Lines**: 37-69, 86-118, 167-196

**Recommendation**: Extract to helper:
```python
def get_user_notification_or_error(notification_id, user):
    """Retrieve notification by ID and recipient (IDOR-safe)."""
    try:
        notification_pk = from_global_id(notification_id)[1]
        return Notification.objects.get(pk=notification_pk, recipient=user), None
    except Notification.DoesNotExist:
        return None, "Notification not found"
```

---

### 4.3 Moderation Check Pattern (4 instances)

**File**: `config/graphql/moderation_mutations.py`
**Lines**: 57-63, 118-124, 179-185, 240-246

**Recommendation**: Extract to helper:
```python
def get_conversation_with_moderation_check(conversation_id, user):
    """Get conversation with moderation verification (IDOR-safe)."""
    try:
        pk = from_global_id(conversation_id)[1]
        conversation = Conversation.objects.get(pk=pk)
        if not conversation.can_moderate(user):
            return None, "Conversation not found"
        return conversation, None
    except Conversation.DoesNotExist:
        return None, "Conversation not found"
```

---

## Part 5: Implementation Priority

### Week 1: Critical Mutations (MUST FIX)

| Priority | Mutation | File:Line | Effort |
|----------|----------|-----------|--------|
| P0 | `RemoveRelationships` | mutations.py:2338 | 1 hour |
| P0 | `UpdateRelations` | mutations.py:2508 | 1 hour |
| P0 | `StartCorpusFork` | mutations.py:1067 | 1 hour |
| P0 | `StartQueryForCorpus` | mutations.py:1151 | 30 min |
| P0 | `StartCorpusExport` | mutations.py:1200 | 1 hour |
| P0 | `StartDocumentExtract` | mutations.py:2995 | 1 hour |
| P0 | `DeleteMultipleLabelMutation` | mutations.py:2557 | 30 min |

**Total**: ~6 hours

---

### Week 2: High Severity Issues

| Priority | Issue | File | Effort |
|----------|-------|------|--------|
| P1 | Badge IDOR enumeration | badge_mutations.py | 2 hours |
| P1 | Moderation IDOR enumeration | moderation_mutations.py | 2 hours |
| P1 | Missing include_group_permissions | mutations.py | 1 hour |

**Total**: ~5 hours

---

### Week 3: Defense-in-Depth & DRY

| Priority | Issue | Effort |
|----------|-------|--------|
| P2 | Extract permission helper functions | 4 hours |
| P2 | Add task-level permission checks (defense-in-depth) | 8 hours |
| P2 | Consolidate duplicative patterns | 4 hours |

**Total**: ~16 hours

---

## Part 6: Testing Requirements

### Required Security Tests

1. **Permission Bypass Tests**:
   ```python
   def test_cannot_delete_others_relationships():
       """Non-owner cannot delete relationships they don't have permission for."""

   def test_cannot_fork_private_corpus():
       """Cannot fork corpus without READ permission."""

   def test_cannot_export_private_corpus():
       """Cannot export corpus without READ permission."""
   ```

2. **IDOR Protection Tests**:
   ```python
   def test_same_error_for_nonexistent_and_forbidden():
       """Same message whether object doesn't exist or user lacks permission."""
   ```

3. **include_group_permissions Tests**:
   ```python
   def test_public_corpus_accessible_via_group():
       """Public resources accessible when include_group_permissions=True."""
   ```

---

## Part 7: Complete Non-Compliant Code Inventory

### GraphQL Mutations Requiring Changes

| File | Mutation | Issue | Severity |
|------|----------|-------|----------|
| mutations.py:2338 | RemoveRelationships | No permission check | CRITICAL |
| mutations.py:2508 | UpdateRelations | No permission check | CRITICAL |
| mutations.py:1067 | StartCorpusFork | No visibility check | CRITICAL |
| mutations.py:1151 | StartQueryForCorpus | No corpus check | CRITICAL |
| mutations.py:1200 | StartCorpusExport | No permission check | CRITICAL |
| mutations.py:2995 | StartDocumentExtract | No permission check | CRITICAL |
| mutations.py:2557 | DeleteMultipleLabelMutation | No permission check | CRITICAL |
| badge_mutations.py:400 | AwardBadgeMutation | IDOR enumeration | HIGH |
| badge_mutations.py:501 | RevokeBadgeMutation | IDOR enumeration | HIGH |
| moderation_mutations.py:60 | LockThreadMutation | IDOR enumeration | HIGH |
| moderation_mutations.py:120 | UnlockThreadMutation | IDOR enumeration | HIGH |
| moderation_mutations.py:180 | PinThreadMutation | IDOR enumeration | HIGH |
| moderation_mutations.py:240 | UnpinThreadMutation | IDOR enumeration | HIGH |

### Tasks Requiring Defense-in-Depth Updates (Lower Priority)

| File | Task | Issue |
|------|------|-------|
| fork_tasks.py:25 | fork_corpus | No user validation |
| permissioning_tasks.py:12 | make_corpus_public_task | No permission check |
| permissioning_tasks.py:22 | make_analysis_public_task | No permission check |
| cleanup_tasks.py:17 | delete_analysis_and_annotations_task | No user context |
| export_tasks.py | Various | No permission checks |

**Note**: These tasks are called by GraphQL mutations which should check permissions. Task-level checks are defense-in-depth.

### Files Demonstrating Good Compliance (Use as Examples)

| File | Pattern |
|------|---------|
| agent_mutations.py | Uses `visible_to_user()` + `include_group_permissions=True` |
| notification_mutations.py | Correct ownership model (recipient=user) |
| corpus_folder_mutations.py | Delegates to CorpusObjsService with proper checks |
| corpus_objs_service.py | Centralized permission checking with IDOR protection |

---

## Conclusion

The original audit reports identified real issues but significantly overstated the severity:

- **True Critical Issues**: 7 GraphQL mutations lack permission checks
- **Overstated Claims**: 47 "critical" task vulnerabilities reduced to defense-in-depth concerns
- **Incorrect Claims**: Corpus folder mutations are properly secured via service layer

**Recommended Timeline**:
- Week 1: Fix 7 critical mutations (~6 hours)
- Week 2: Fix 6 high-severity IDOR issues (~5 hours)
- Week 3: Defense-in-depth and DRY consolidation (~16 hours)

**Total Effort**: ~27 hours of focused work
