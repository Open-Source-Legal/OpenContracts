# Discussion System Technical Analysis

> **Document Version:** 1.0
> **Last Updated:** 2026-01-31
> **Scope:** Backend models, GraphQL API, Frontend components
> **Related Issues:** #581 (Epic), #549, #550, #554, #557, #558, #562, #565

---

## Executive Summary

The OpenContracts Discussion System is a comprehensive, production-grade implementation providing:

| Component | Count | Status |
|-----------|-------|--------|
| Backend Models | 8 core + 16 permission models | Production |
| GraphQL Mutations | 15+ with rate limiting | Production |
| Frontend Components | 35+ React components | Production |
| Test Coverage | 12+ test suites | Comprehensive |

This document provides a detailed technical analysis categorized into three tiers:
- **Necessary**: Critical issues requiring immediate attention
- **Recommended**: Important improvements for maintainability and performance
- **Nice to Have**: Enhancements that would improve user experience

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Necessary Improvements](#necessary-improvements-critical)
3. [Recommended Improvements](#recommended-improvements-should-fix)
4. [Nice to Have](#nice-to-have-enhancements)
5. [Implementation Priority Matrix](#implementation-priority-matrix)
6. [Technical Debt Summary](#technical-debt-summary)

---

## Architecture Overview

### Backend Stack
- **Framework**: Django 4.x with Graphene-Django
- **Database**: PostgreSQL with pgvector extension
- **Task Queue**: Celery for async operations
- **Permissions**: django-guardian for object-level permissions

### Frontend Stack
- **Framework**: React 18 with TypeScript
- **State Management**: Jotai atoms + Apollo Client reactive vars
- **Styling**: styled-components
- **Real-time**: WebSocket for agent streaming

### Key Architectural Patterns

#### 1. Bifurcated Permission Model
```
CHAT type (agent conversations):
  - Restrictive: creator + explicit permissions + public flag

THREAD type (discussions):
  - Context-based: CHAT rules + inheritance from corpus/document
  - MIN(corpus_permission, document_permission) when both linked
```

#### 2. Soft Delete with Dual Managers
```python
# Default manager - excludes soft-deleted
Conversation.objects.all()

# All objects including soft-deleted
Conversation.all_objects.all()
```

#### 3. Denormalized Vote Counts
Vote counts are cached on `Conversation` and `ChatMessage` models, updated via Django signals for O(1) read performance.

---

## Necessary Improvements (Critical)

These issues represent security vulnerabilities, data integrity risks, or correctness bugs that should be addressed before the next release.

### N-1: Granular Moderator Permission Bypass

**Severity**: High
**Location**: `opencontractserver/conversations/models.py:786-801`
**Type**: Authorization Logic Flaw

#### Issue Description

The `can_moderate()` method checks if a user is a designated moderator with *any* permissions, but does not verify they have the *specific* permission for the action being performed:

```python
# Current implementation (line 786-801)
def can_moderate(self, user) -> bool:
    # ...
    if self.chat_with_corpus:
        try:
            moderator = CorpusModerator.objects.get(
                corpus=self.chat_with_corpus, user=user
            )
            # BUG: Only checks if permissions list is non-empty
            if bool(moderator.permissions):
                return True
        except CorpusModerator.DoesNotExist:
            pass
```

#### Attack Scenario

1. Corpus owner assigns User A moderator status with only `pin_threads` permission
2. User A calls `conversation.lock(user_a, "reason")` directly via model method
3. The `lock()` method calls `can_moderate()`, which returns `True` because `['pin_threads']` is truthy
4. User A successfully locks threads despite lacking `lock_threads` permission

#### Impact

Moderators can perform actions beyond their assigned permissions when calling model methods directly. GraphQL mutations have separate permission checks that mask this issue at the API layer.

#### Recommended Fix

**Option A**: Add permission parameter to `can_moderate()`

```python
def can_moderate(self, user, permission: str = None) -> bool:
    """
    Check if user can moderate. If permission specified, verify specific permission.
    """
    # Superuser/owner checks...

    if self.chat_with_corpus:
        try:
            moderator = CorpusModerator.objects.get(
                corpus=self.chat_with_corpus, user=user
            )
            if permission:
                return moderator.has_permission(permission)
            return bool(moderator.permissions)
        except CorpusModerator.DoesNotExist:
            pass
```

Then update model methods:

```python
def lock(self, moderator, reason: str = "") -> "ModerationAction":
    if not self.can_moderate(moderator, permission="lock_threads"):
        raise PermissionError(...)
```

**Option B**: Move all permission checks to a centralized `ModerationService`

```python
class ModerationService:
    @staticmethod
    def check_permission(user, conversation, action: str) -> bool:
        """Centralized permission checking for all moderation actions."""
        # Implementation
```

#### Test Cases Required

```python
def test_moderator_cannot_lock_without_lock_permission(self):
    """Moderator with only pin_threads cannot lock threads."""
    moderator = CorpusModerator.objects.create(
        corpus=self.corpus,
        user=self.user,
        permissions=["pin_threads"],
        creator=self.corpus_owner,
    )
    conversation = Conversation.objects.create(...)

    with self.assertRaises(PermissionError):
        conversation.lock(self.user, "test reason")
```

---

### N-2: IDOR Vulnerability in VoteMessageMutation

**Severity**: Medium-High
**Location**: `config/graphql/voting_mutations.py:75-91`
**Type**: Information Disclosure via Error Message Differentiation

#### Issue Description

`VoteMessageMutation` returns different error messages for "message not found" vs "permission denied", allowing attackers to enumerate valid message IDs:

```python
# Current implementation (line 75-91)
try:
    message_pk = from_global_id(message_id)[1]
    chat_message = ChatMessage.objects.get(pk=message_pk)
except ChatMessage.DoesNotExist:
    return VoteMessageMutation(
        ok=False,
        message="Message not found",  # IDOR: Different message
        obj=None
    )

# Permission check with different message
if not user_has_permission_for_obj(user, conversation, PermissionTypes.READ):
    return VoteMessageMutation(
        ok=False,
        message="You do not have permission to vote...",  # Different message
        obj=None,
    )
```

#### Comparison with Secure Implementation

`VoteConversationMutation` (line 239-249) correctly uses `visible_to_user()` pattern:

```python
# Secure pattern in VoteConversationMutation
try:
    conversation_pk = from_global_id(conversation_id)[1]
    conversation = Conversation.objects.visible_to_user(user).get(pk=conversation_pk)
except Conversation.DoesNotExist:
    return VoteConversationMutation(
        ok=False,
        message="Conversation not found or you do not have permission to access it",
        obj=None,
    )
```

#### Attack Scenario

1. Attacker iterates through message IDs: `Q2hhdE1lc3NhZ2U6MQ==`, `Q2hhdE1lc3NhZ2U6Mg==`, etc.
2. "Message not found" = ID doesn't exist
3. "You do not have permission" = ID exists but belongs to another user
4. Attacker builds a list of valid message IDs for targeted attacks

#### Recommended Fix

```python
# Use visible_to_user() pattern consistently
try:
    message_pk = from_global_id(message_id)[1]
    chat_message = ChatMessage.objects.visible_to_user(user).get(pk=message_pk)
except ChatMessage.DoesNotExist:
    return VoteMessageMutation(
        ok=False,
        message="Message not found or you do not have permission to access it",
        obj=None,
    )
```

#### Files Requiring Same Fix

| File | Mutation | Line |
|------|----------|------|
| `voting_mutations.py` | `VoteMessageMutation` | 75-91 |
| `voting_mutations.py` | `RemoveVoteMutation` | 159-176 |

---

### N-3: Missing Transaction Atomicity in Vote Mutations

**Severity**: Medium
**Location**: `config/graphql/voting_mutations.py:57`, `config/graphql/voting_mutations.py:222`
**Type**: Data Integrity Risk

#### Issue Description

Vote mutations create a vote record AND set permissions in separate operations without transaction wrapping:

```python
# Current implementation (no @transaction.atomic)
@login_required
@graphql_ratelimit(rate="60/m")
def mutate(root, info, message_id, vote_type):
    # ...
    existing_vote = MessageVote.objects.create(
        message=chat_message, vote_type=vote_type_lower, creator=user
    )
    # If this fails, we have an orphan vote without permissions
    set_permissions_for_obj_to_user(
        user, existing_vote, [PermissionTypes.CRUD]
    )
```

#### Failure Scenario

1. `MessageVote.objects.create()` succeeds
2. Database connection drops before `set_permissions_for_obj_to_user()` completes
3. Vote exists in database but user has no permissions on it
4. User cannot modify or delete their own vote

#### Comparison

`UpdateMessageMutation` (line 484) correctly uses `@transaction.atomic`:

```python
@login_required
@graphql_ratelimit(rate="30/m")
@transaction.atomic  # Correct pattern
def mutate(root, info, message_id, content):
```

#### Recommended Fix

```python
from django.db import transaction

class VoteMessageMutation(graphene.Mutation):
    @login_required
    @graphql_ratelimit(rate="60/m")
    @transaction.atomic  # Add this decorator
    def mutate(root, info, message_id, vote_type):
        # ...
```

#### Files Requiring Fix

| Mutation | Line |
|----------|------|
| `VoteMessageMutation.mutate` | 57 |
| `VoteConversationMutation.mutate` | 222 |

---

### N-4: Performance Issue in Anonymous User Visibility Queries

**Severity**: Medium
**Location**: `opencontractserver/conversations/models.py:188-217`
**Type**: N+1 Query / Performance

#### Issue Description

For anonymous users, visibility checks execute separate subqueries for public corpus/document IDs on every call:

```python
# Current implementation (line 188-217)
if user.is_anonymous:
    # These execute as subqueries on EVERY visibility check
    public_corpus_ids = Corpus.objects.filter(is_public=True).values_list(
        "id", flat=True
    )
    public_doc_ids = Document.objects.filter(is_public=True).values_list(
        "id", flat=True
    )
```

#### Impact

- High-traffic anonymous views (public landing pages) trigger redundant queries
- No caching between requests for the same public resource set
- Database load increases linearly with anonymous traffic

#### Recommended Fix

**Option A**: Use Django's cache framework

```python
from django.core.cache import cache

def _get_public_resource_ids():
    """Cached public resource IDs (5 minute TTL)."""
    cache_key = "public_resource_ids"
    cached = cache.get(cache_key)
    if cached:
        return cached

    result = {
        "corpus_ids": list(Corpus.objects.filter(is_public=True).values_list("id", flat=True)),
        "doc_ids": list(Document.objects.filter(is_public=True).values_list("id", flat=True)),
    }
    cache.set(cache_key, result, 300)  # 5 minutes
    return result
```

**Option B**: Use request-level caching via `ConversationQueryOptimizer`

The optimizer already exists but isn't used for anonymous users. Extend it to cache public IDs.

#### Cache Invalidation

Signal handlers on `Corpus` and `Document` should invalidate cache on `is_public` changes:

```python
@receiver(post_save, sender=Corpus)
def invalidate_public_cache_on_corpus_save(sender, instance, **kwargs):
    if 'is_public' in (kwargs.get('update_fields') or []):
        cache.delete("public_resource_ids")
```

---

## Recommended Improvements (Should Fix)

These improvements address maintainability, performance optimization, and code quality issues.

### R-1: Extract Duplicate Visibility Logic into Shared Mixin

**Priority**: High
**Location**: Multiple QuerySet classes
**Type**: Code Duplication / DRY Violation

#### Issue Description

Three separate QuerySet classes implement visibility logic with overlapping patterns:

| Class | Location | Lines |
|-------|----------|-------|
| `SoftDeleteQuerySet.visible_to_user()` | models.py:68-108 | 40 |
| `ConversationQuerySet.visible_to_user()` | models.py:127-288 | 161 |
| `ChatMessageQuerySet.visible_to_user()` | models.py:349-455 | 106 |

Shared patterns include:
- Anonymous user handling
- Superuser bypass
- Guardian permission lookups
- Public flag checks

#### Recommended Refactoring

Create a `BifurcatedVisibilityMixin`:

```python
class BifurcatedVisibilityMixin:
    """
    Mixin providing visibility filtering with bifurcated CHAT/THREAD logic.

    Subclasses must define:
    - VISIBILITY_TYPE: 'chat', 'thread', or 'bifurcated'
    - get_context_conditions(user): Returns Q objects for context-based visibility
    """

    def _get_base_visibility_conditions(self, user) -> Q:
        """Common visibility conditions: creator, public, explicit permission."""
        # Implementation

    def _get_anonymous_conditions(self) -> Q:
        """Visibility conditions for anonymous users."""
        # Implementation

    def visible_to_user(self, user=None):
        """Template method combining all visibility checks."""
        if user is None:
            user = AnonymousUser()

        if getattr(user, 'is_superuser', False):
            return self._superuser_queryset()

        if user.is_anonymous:
            return self.filter(self._get_anonymous_conditions())

        return self.filter(
            self._get_base_visibility_conditions(user)
            | self.get_context_conditions(user)
        )
```

---

### R-2: Add Database Indices for Common Query Patterns

**Priority**: High
**Location**: `opencontractserver/conversations/models.py`
**Type**: Performance Optimization

#### Missing Indices

| Fields | Use Case | Expected Impact |
|--------|----------|-----------------|
| `(conversation_type, chat_with_corpus_id)` | Filter threads by corpus | 10-50x faster |
| `(conversation_type, is_public)` | Anonymous user queries | 5-20x faster |
| `(creator_id, conversation_type)` | "My threads" queries | 10-30x faster |
| `(conversation_id, created_at)` | Message pagination | 5-10x faster |
| `(deleted_at, conversation_type)` | Active thread lists | 3-5x faster |

#### Migration Example

```python
# migrations/0015_add_performance_indices.py
from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [
        ('conversations', '0014_add_conversation_voting'),
    ]

    operations = [
        migrations.AddIndex(
            model_name='conversation',
            index=models.Index(
                fields=['conversation_type', 'chat_with_corpus'],
                name='conv_type_corpus_idx'
            ),
        ),
        migrations.AddIndex(
            model_name='conversation',
            index=models.Index(
                fields=['conversation_type', 'is_public'],
                name='conv_type_public_idx'
            ),
        ),
        migrations.AddIndex(
            model_name='chatmessage',
            index=models.Index(
                fields=['conversation', 'created'],
                name='msg_conv_created_idx'
            ),
        ),
    ]
```

---

### R-3: Standardize GraphQL Mutation Response Shape

**Priority**: Medium
**Location**: All mutation files in `config/graphql/`
**Type**: API Consistency

#### Current Inconsistency

| Mutation | Response Shape |
|----------|----------------|
| Most mutations | `{ok, message, obj}` |
| `DeleteThreadMutation` | `{ok, message, conversation}` |
| `RollbackModerationActionMutation` | `{ok, message, rollback_action}` |
| `AddModeratorMutation` | `{ok, message}` (no object) |

#### Recommended Standard

```python
class MutationResponse(graphene.ObjectType):
    """Standard response for all mutations."""
    ok = graphene.Boolean(required=True)
    message = graphene.String()

class ObjectMutationResponse(MutationResponse):
    """Response for mutations that return an object."""
    obj = graphene.Field(graphene.ObjectType)  # Override in subclass

# Usage
class DeleteThreadMutation(graphene.Mutation):
    class Output(MutationResponse):
        obj = graphene.Field(ConversationType)
```

---

### R-4: Add Optimistic UI Updates for Moderation Actions

**Priority**: Medium
**Location**: `frontend/src/components/threads/MessageItem.tsx`
**Type**: User Experience

#### Current Behavior

Message deletion waits for server response before updating UI:

```typescript
// Current implementation (line 818-835)
const handleConfirmDelete = useCallback(async (e: React.MouseEvent) => {
  e.stopPropagation();
  try {
    const result = await deleteMessage({
      variables: { messageId: message.id },
    });
    if (result.data?.deleteMessage.ok) {
      // UI only updates after server confirms
      onMessageDeleted?.();
    }
  } catch (err) {
    console.error("Error deleting message:", err);
  }
}, [deleteMessage, message.id, onMessageDeleted]);
```

#### Comparison

`VoteButtons.tsx` implements optimistic updates correctly:

```typescript
// Optimistic update pattern in VoteButtons (line 170-172)
setOptimisticVote(newVoteType);
// Server call happens after UI update
```

#### Recommended Implementation

```typescript
const handleConfirmDelete = useCallback(async (e: React.MouseEvent) => {
  e.stopPropagation();

  // Optimistic update
  setIsOptimisticallyDeleted(true);
  setIsDropdownOpen(false);
  setShowDeleteConfirm(false);

  try {
    const result = await deleteMessage({
      variables: { messageId: message.id },
    });
    if (!result.data?.deleteMessage.ok) {
      // Rollback on failure
      setIsOptimisticallyDeleted(false);
      // Show error toast
    } else {
      onMessageDeleted?.();
    }
  } catch (err) {
    // Rollback on error
    setIsOptimisticallyDeleted(false);
    console.error("Error deleting message:", err);
  }
}, [deleteMessage, message.id, onMessageDeleted]);
```

---

### R-5: Add Message Edit History Tracking

**Priority**: Medium
**Location**: `opencontractserver/conversations/models.py:1039-1044`
**Type**: Feature / Audit Trail

#### Current State

The `ChatMessage.data` JSONField exists but isn't used for edit history:

```python
data = NullableJSONField(
    default=jsonfield_default_value,
    null=True,
    blank=True,
    help_text="Additional data associated with the chat message (stored as JSON)",
)
```

#### Implementation Options

**Option A**: Store in `data` field

```python
# In UpdateMessageMutation
chat_message.data = chat_message.data or {}
chat_message.data.setdefault("edit_history", []).append({
    "content": chat_message.content,  # Previous content
    "edited_at": timezone.now().isoformat(),
    "edited_by": user.id,
})
chat_message.content = new_content
chat_message.save()
```

**Option B**: Dedicated model (more scalable)

```python
class ChatMessageEdit(BaseOCModel):
    """Tracks edit history for messages."""
    message = models.ForeignKey(ChatMessage, on_delete=models.CASCADE, related_name="edits")
    previous_content = models.TextField()
    edited_at = models.DateTimeField(auto_now_add=True)
    edited_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)

    class Meta:
        ordering = ["-edited_at"]
```

---

### R-6: Consolidate Rate Limit Strategy

**Priority**: Low
**Location**: `config/graphql/conversation_mutations.py:81` and related
**Type**: Security / Consistency

#### Current Inconsistency

| Operation | Rate Limit | Concern |
|-----------|------------|---------|
| `CreateThreadMutation` | 10/hour | Correct for thread creation |
| `CreateThreadMessageMutation` | 30/minute | Could be used to spam |
| `ReplyToMessageMutation` | 30/minute | Consistent with above |

#### Consideration

A user could technically create content faster by posting messages to an existing thread than by creating new threads. This may be intentional (encouraging engagement in existing discussions) but should be documented.

#### Recommended Action

Add a shared rate limit for total content creation:

```python
# In ratelimits.py
class RateLimits:
    # Existing limits...
    CONTENT_CREATION = "100/h"  # Total messages + threads per hour
```

---

### R-7: Add Caching for Badge Queries

**Priority**: Low
**Location**: `frontend/src/components/threads/ThreadDetail.tsx:341`
**Type**: Performance

#### Issue

`useMessageBadges(userIds, corpusId)` is called on every thread view, even for the same users:

```typescript
// Line 341
const { badgesByUser } = useMessageBadges(userIds, corpusId);
```

#### Recommended Fix

Use React Query or modify Apollo cache normalization:

```typescript
// Option: Use Apollo cache with longer TTL
const { data: badgesData } = useQuery(GET_USER_BADGES, {
  variables: { userIds, corpusId },
  fetchPolicy: "cache-first",
  nextFetchPolicy: "cache-first",
});
```

---

## Nice to Have (Enhancements)

These improvements would enhance user experience but are not critical for production stability.

### NH-1: Real-time Thread Updates via WebSocket

**Effort**: Large
**Impact**: High

Extend the existing `useThreadWebSocket.ts` infrastructure to broadcast:
- New messages in thread
- Vote count changes
- Moderation actions (lock/unlock/delete)

This would eliminate the need for manual refetches after actions.

---

### NH-2: Message Reactions Beyond Upvote/Downvote

**Effort**: Medium
**Impact**: Medium

Support emoji reactions (e.g., thumbsUp, heart, celebrate) similar to Slack/GitHub.

**Model Addition**:
```python
class MessageReaction(BaseOCModel):
    message = models.ForeignKey(ChatMessage, on_delete=models.CASCADE, related_name="reactions")
    reaction_type = models.CharField(max_length=50)  # e.g., "thumbs_up", "heart"

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["message", "creator", "reaction_type"],
                name="one_reaction_type_per_user_per_message",
            )
        ]
```

---

### NH-3: Thread Subscription/Watch Feature

**Effort**: Medium
**Impact**: High

Allow users to subscribe to threads for notifications on all activity, not just replies to their messages.

**Implementation**:
```python
class ThreadSubscription(BaseOCModel):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE)
    notification_level = models.CharField(
        choices=[("all", "All Activity"), ("mentions", "Mentions Only")],
        default="all",
    )

    class Meta:
        unique_together = ["conversation", "creator"]
```

---

### NH-4: Markdown Preview in Message Composer

**Effort**: Small
**Impact**: Medium

Add a real-time preview pane in `ReplyForm.tsx` and `MessageComposer.tsx` showing rendered markdown as the user types.

---

### NH-5: Thread Categories/Tags

**Effort**: Medium
**Impact**: Medium

Allow corpus owners to define categories and users to tag threads.

**Benefits**:
- Better thread discovery
- Filtering by category
- Category-specific moderation rules

---

### NH-6: User Blocking Feature

**Effort**: Medium
**Impact**: Medium

Allow users to block other users from:
- Replying to their messages
- Appearing in their thread views (client-side filter)

---

### NH-7: Draft Message Auto-save

**Effort**: Small
**Impact**: Medium

Persist in-progress message drafts to localStorage, restore on page reload.

```typescript
// In ReplyForm.tsx
useEffect(() => {
  const saved = localStorage.getItem(`draft-${conversationId}`);
  if (saved) setContent(saved);
}, [conversationId]);

useEffect(() => {
  localStorage.setItem(`draft-${conversationId}`, content);
}, [content, conversationId]);
```

---

### NH-8: Message Bookmark/Save Feature

**Effort**: Medium
**Impact**: Low

Allow users to bookmark messages for later reference.

---

### NH-9: Thread Analytics Dashboard for Moderators

**Effort**: Large
**Impact**: Medium

Dashboard showing:
- Messages per day/week
- Top contributors
- Moderation action frequency
- Flagged content metrics

---

### NH-10: Keyboard Navigation Support

**Effort**: Small
**Impact**: Medium

Add keyboard shortcuts to `MessageTree.tsx`:
- `j/k`: Navigate between messages
- `r`: Reply to current message
- `u`: Upvote current message
- `Esc`: Close modals/cancel reply

---

## Implementation Priority Matrix

| ID | Issue | Severity | Effort | Priority Score |
|----|-------|----------|--------|----------------|
| N-1 | Moderator Permission Bypass | High | Small | **P0** |
| N-2 | IDOR in VoteMessageMutation | Medium-High | Small | **P0** |
| N-3 | Missing Transaction Atomicity | Medium | Small | **P1** |
| N-4 | Anonymous Visibility Performance | Medium | Medium | **P1** |
| R-1 | Extract Visibility Mixin | N/A | Medium | **P2** |
| R-2 | Add Database Indices | N/A | Small | **P1** |
| R-3 | Standardize Response Shape | N/A | Small | **P3** |
| R-4 | Optimistic UI Updates | N/A | Small | **P2** |
| R-5 | Edit History Tracking | N/A | Medium | **P3** |
| R-6 | Rate Limit Consolidation | N/A | Small | **P3** |
| R-7 | Badge Query Caching | N/A | Small | **P3** |

**Priority Legend**:
- **P0**: Fix immediately (security/correctness)
- **P1**: Fix in next sprint
- **P2**: Plan for upcoming quarter
- **P3**: Backlog

---

## Technical Debt Summary

### Security Debt
- [ ] N-1: Granular moderator permission enforcement
- [ ] N-2: IDOR in vote mutations

### Data Integrity Debt
- [ ] N-3: Transaction atomicity in vote mutations

### Performance Debt
- [ ] N-4: Anonymous user visibility caching
- [ ] R-2: Missing database indices
- [ ] R-7: Badge query caching

### Code Quality Debt
- [ ] R-1: Duplicate visibility logic
- [ ] R-3: Inconsistent mutation response shapes

### UX Debt
- [ ] R-4: Missing optimistic updates
- [ ] R-5: No edit history visibility

---

## Appendix: File Reference

### Backend Files

| File | Purpose |
|------|---------|
| `opencontractserver/conversations/models.py` | Core models and QuerySets |
| `opencontractserver/conversations/signals.py` | Vote count and reputation signals |
| `opencontractserver/conversations/query_optimizer.py` | Request-level caching |
| `config/graphql/conversation_mutations.py` | Thread CRUD mutations |
| `config/graphql/voting_mutations.py` | Vote mutations |
| `config/graphql/moderation_mutations.py` | Moderation mutations |
| `config/graphql/graphene_types.py` | GraphQL type definitions |

### Frontend Files

| File | Purpose |
|------|---------|
| `frontend/src/components/threads/ThreadDetail.tsx` | Thread detail view |
| `frontend/src/components/threads/MessageItem.tsx` | Message component |
| `frontend/src/components/threads/VoteButtons.tsx` | Voting UI |
| `frontend/src/components/threads/MessageTree.tsx` | Threaded message display |
| `frontend/src/atoms/threadAtoms.ts` | Jotai state atoms |
| `frontend/src/hooks/useThreadWebSocket.ts` | Real-time agent responses |

---

*Document authored as part of Issue #581 (Epic: Corpus Interactivity)*
