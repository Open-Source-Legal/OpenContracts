# OpenContracts Sharing Architecture

> **Status**: This document describes the current state and planned improvements for corpus/document sharing.

## Table of Contents

1. [Current State](#current-state)
2. [Architecture Overview](#architecture-overview)
3. [Phase 1: Owner-Controlled Public Visibility](#phase-1-owner-controlled-public-visibility)
4. [Phase 2: User-Level Sharing](#phase-2-user-level-sharing)

---

## Current State

### What Works

| Feature | Status | Notes |
|---------|--------|-------|
| Permission types defined | ✅ | `PERMISSION`, `READ`, `UPDATE`, `DELETE`, `CREATE`, `PUBLISH`, `COMMENT` |
| Permission storage | ✅ | Django Guardian with `{Model}UserObjectPermission` tables |
| `myPermissions` GraphQL field | ✅ | Users can see their own permissions on objects |
| `objectSharedWith` GraphQL field | ✅ | Shows all users with access (read-only) |
| `set_permissions_for_obj_to_user()` | ✅ | Core utility function for granting permissions |
| Make corpus public (superuser) | ✅ | `MakeCorpusPublic` mutation, superuser-only |

### What's Missing

| Feature | Status | Impact |
|---------|--------|--------|
| Owner can make corpus public | ❌ | Creators must ask superusers to make corpuses public |
| Share with specific users | ❌ | No mutation exists to grant another user access |
| PERMISSION type enforcement | ❌ | Backend doesn't check PERMISSION for `is_public` changes |
| Creators get PERMISSION | ❌ | Creators only get CRUD+PUBLISH, not PERMISSION |

### Security Gap

The frontend checks `CAN_PERMISSION` before allowing visibility changes, but the backend `UpdateCorpusMutation` only checks `UPDATE` permission:

```python
# Backend: base.py DRFMutation
if not obj.user_can(user, PermissionTypes.UPDATE):  # Only UPDATE!
    raise PermissionError(...)
```

```typescript
// Frontend: CorpusSettings.tsx
const canPermission = permissions.includes(PermissionTypes.CAN_PERMISSION);
// UI disabled if !canPermission, but backend doesn't enforce this
```

---

## Architecture Overview

### Permission Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Permission System                             │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌──────────────┐    ┌──────────────────┐    ┌──────────────────┐  │
│  │   Frontend   │    │     GraphQL      │    │     Backend      │  │
│  │              │    │                  │    │                  │  │
│  │ CAN_PERMISSION│───▶│ myPermissions   │◀───│ permission_corpus│  │
│  │ CAN_UPDATE   │    │ objectSharedWith │    │ update_corpus    │  │
│  │ CAN_READ     │    │                  │    │ read_corpus      │  │
│  └──────────────┘    └──────────────────┘    └──────────────────┘  │
│         │                    │                       │              │
│         ▼                    ▼                       ▼              │
│  ┌──────────────┐    ┌──────────────────┐    ┌──────────────────┐  │
│  │  UI Gating   │    │    Mutations     │    │ Django Guardian  │  │
│  │  (cosmetic)  │    │  (enforcement)   │    │   (storage)      │  │
│  └──────────────┘    └──────────────────┘    └──────────────────┘  │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### Key Files

| File | Purpose |
|------|---------|
| `opencontractserver/utils/permissioning.py` | Core permission utilities |
| `opencontractserver/types/enums.py` | `PermissionTypes` enum |
| `config/graphql/base.py` | `DRFMutation` base class with permission checks |
| `config/graphql/mutations.py` | `UpdateCorpusMutation`, `MakeCorpusPublic` |
| `config/graphql/permissioning/permission_annotator/mixins.py` | `myPermissions`, `objectSharedWith` resolvers |
| `opencontractserver/utils/sharing.py` | `make_corpus_public()` logic |
| `frontend/src/components/corpuses/CorpusSettings.tsx` | UI for visibility settings |

### Permission Types Reference

| Type | Backend Codename | Frontend Enum | Purpose |
|------|------------------|---------------|---------|
| READ | `read_corpus` | `CAN_READ` | View corpus and contents |
| CREATE | `create_corpus` | `CAN_CREATE` | Add documents/annotations |
| UPDATE | `update_corpus` | `CAN_UPDATE` | Edit corpus metadata |
| DELETE | `remove_corpus` | `CAN_REMOVE` | Delete corpus |
| PUBLISH | `publish_corpus` | `CAN_PUBLISH` | Make corpus public |
| PERMISSION | `permission_corpus` | `CAN_PERMISSION` | Manage access/sharing |
| COMMENT | `comment_corpus` | `CAN_COMMENT` | Add comments |

---

## Phase 1: Owner-Controlled Public Visibility

### Goal

Allow corpus creators (owners) to toggle their corpus's public visibility without requiring superuser intervention.

### Requirements

1. **Owners can set `is_public`**: Creator of a corpus should be able to make it public/private
2. **Backend enforcement**: Server-side check, not just UI gating
3. **Cascading visibility**: When making public, related objects should also become public
4. **Backward compatible**: Existing permissions and workflows unchanged

### Implementation Plan

#### 1.1 Update Permission Grant on Corpus Creation

**File**: `config/graphql/mutations.py`

**Change**: Grant `PERMISSION` and `PUBLISH` to creators

```python
# In CreateCorpusMutation.mutate() around line 2562-2566
# BEFORE:
set_permissions_for_obj_to_user(
    info.context.user,
    corpus,
    [PermissionTypes.CRUD, PermissionTypes.PUBLISH],
)

# AFTER:
set_permissions_for_obj_to_user(
    info.context.user,
    corpus,
    [PermissionTypes.CRUD, PermissionTypes.PUBLISH, PermissionTypes.PERMISSION],
)
```

#### 1.2 Create SetCorpusVisibility Mutation

**File**: `config/graphql/mutations.py`

**New mutation** that properly checks permissions and handles cascading:

```python
class SetCorpusVisibility(graphene.Mutation):
    """
    Set corpus visibility (public/private).

    Requires either:
    - User is corpus creator (owner), OR
    - User has PERMISSION permission on corpus, OR
    - User is superuser
    """

    class Arguments:
        corpus_id = graphene.ID(required=True)
        is_public = graphene.Boolean(required=True)

    ok = graphene.Boolean()
    message = graphene.String()

    @login_required
    @graphql_ratelimit(rate=RateLimits.WRITE_MEDIUM)
    def mutate(root, info, corpus_id, is_public):
        user = info.context.user
        corpus_pk = from_global_id(corpus_id)[1]

        try:
            corpus = Corpus.objects.get(pk=corpus_pk)
        except Corpus.DoesNotExist:
            return SetCorpusVisibility(ok=False, message="Corpus not found")

        # Permission check: owner OR has PERMISSION OR superuser
        can_change_visibility = (
            user.is_superuser or
            corpus.creator_id == user.id or
            corpus.user_can(user, PermissionTypes.PERMISSION)
        )

        if not can_change_visibility:
            return SetCorpusVisibility(
                ok=False,
                message="You don't have permission to change this corpus's visibility"
            )

        if is_public:
            # Use existing make_corpus_public logic (async task)
            make_corpus_public_task.si(corpus_id=corpus_pk).apply_async()
            return SetCorpusVisibility(
                ok=True,
                message="Making corpus public. This may take a moment for large corpuses."
            )
        else:
            # Make private (simpler - just update the flag)
            corpus.is_public = False
            corpus.save(update_fields=['is_public'])
            return SetCorpusVisibility(ok=True, message="Corpus is now private")
```

#### 1.3 Remove is_public from UpdateCorpusMutation

**File**: `config/graphql/mutations.py`

**Change**: Remove `is_public` from `UpdateCorpusMutation.Arguments` to prevent bypassing the proper visibility mutation:

```python
class UpdateCorpusMutation(DRFMutation):
    class Arguments:
        id = graphene.String(required=True)
        title = graphene.String(required=False)
        description = graphene.String(required=False)
        icon = graphene.String(required=False)
        label_set = graphene.String(required=False)
        preferred_embedder = graphene.String(required=False)
        slug = graphene.String(required=False)
        # REMOVED: is_public = graphene.Boolean(required=False)
        corpus_agent_instructions = graphene.String(required=False)
        document_agent_instructions = graphene.String(required=False)
```

Also remove `is_public` from the serializer or make it read-only:

**File**: `config/graphql/serializers.py`

```python
class CorpusSerializer(serializers.ModelSerializer):
    class Meta:
        model = Corpus
        fields = [...]
        read_only_fields = ["id", "is_public"]  # Add is_public to read_only
```

#### 1.4 Update Frontend to Use New Mutation

**File**: `frontend/src/graphql/mutations.ts`

```typescript
export const SET_CORPUS_VISIBILITY = gql`
  mutation SetCorpusVisibility($corpusId: ID!, $isPublic: Boolean!) {
    setCorpusVisibility(corpusId: $corpusId, isPublic: $isPublic) {
      ok
      message
    }
  }
`;
```

**File**: `frontend/src/components/corpuses/CorpusSettings.tsx`

Update to use the new mutation instead of `UPDATE_CORPUS` for visibility changes.

#### 1.5 Add Migration for Existing Creators

**File**: New migration in `opencontractserver/corpuses/migrations/`

Grant `PERMISSION` to all existing corpus creators:

```python
def grant_permission_to_creators(apps, schema_editor):
    from guardian.shortcuts import assign_perm
    Corpus = apps.get_model('corpuses', 'Corpus')

    for corpus in Corpus.objects.select_related('creator').iterator():
        if corpus.creator:
            assign_perm('permission_corpus', corpus.creator, corpus)

class Migration(migrations.Migration):
    operations = [
        migrations.RunPython(grant_permission_to_creators, migrations.RunPython.noop),
    ]
```

### Testing Requirements

1. **Unit tests** for `SetCorpusVisibility` mutation:
   - Owner can make public/private
   - User with PERMISSION can make public/private
   - User with only UPDATE cannot change visibility
   - Superuser can change any corpus
   - Non-owner without PERMISSION is denied

2. **Integration tests**:
   - Visibility change cascades to documents, annotations, etc.
   - Frontend correctly gates based on permissions

---

## Phase 2: User-Level Sharing

### Goal

Allow corpus owners to share their corpuses with specific users, granting them various permission levels.

### Requirements

1. **Share mutation**: Grant another user access to a corpus
2. **Revoke mutation**: Remove a user's access
3. **Permission levels**: Support granting specific permissions (READ, UPDATE, etc.)
4. **UI for sharing**: Modal or panel to manage who has access
5. **Notifications**: Optionally notify users when shared with them

### Implementation Plan (High-Level)

#### 2.1 Backend Mutations

```python
class ShareCorpus(graphene.Mutation):
    """Share a corpus with another user."""
    class Arguments:
        corpus_id = graphene.ID(required=True)
        user_id = graphene.ID(required=True)
        permissions = graphene.List(graphene.String, required=True)

    # Requires PERMISSION on corpus
    # Calls set_permissions_for_obj_to_user()

class RevokeCorpusAccess(graphene.Mutation):
    """Remove a user's access to a corpus."""
    class Arguments:
        corpus_id = graphene.ID(required=True)
        user_id = graphene.ID(required=True)

    # Requires PERMISSION on corpus
    # Calls set_permissions_for_obj_to_user(user, corpus, [])
```

#### 2.2 Frontend Components

- `ShareCorpusModal`: UI for searching users and granting access
- `CorpusAccessList`: Display current users with access
- `PermissionSelector`: Dropdown for selecting permission levels

#### 2.3 User Search Query

```graphql
query SearchUsersForSharing($query: String!) {
  searchUsers(query: $query) {
    edges {
      node {
        id
        username
        email
      }
    }
  }
}
```

#### 2.4 Notifications Integration

When sharing, optionally create a notification:

```python
Notification.objects.create(
    recipient=target_user,
    notification_type=NotificationTypes.CORPUS_SHARED,
    actor=sharing_user,
    target_corpus=corpus,
    message=f"{sharing_user.username} shared '{corpus.title}' with you"
)
```

### Security Considerations

1. **IDOR Prevention**: Use `visible_to_user()` for user search to prevent enumeration
2. **Permission Escalation**: Cannot grant permissions you don't have yourself
3. **Rate Limiting**: Apply rate limits to prevent abuse
4. **Audit Trail**: Log permission changes for security auditing

---

## Migration Path

### Phase 1 Rollout

1. Deploy backend changes (new mutation, migration)
2. Update frontend to use new mutation
3. Remove deprecated `is_public` from `UpdateCorpusMutation`
4. Monitor for issues

### Phase 2 Rollout

1. Deploy sharing mutations
2. Deploy user search functionality
3. Deploy frontend sharing UI
4. Add notifications
5. Documentation and user communication

---

## Appendix: Current Permission Assignment

### When Corpus is Created

```python
# mutations.py:2562-2566
set_permissions_for_obj_to_user(
    user, corpus,
    [PermissionTypes.CRUD, PermissionTypes.PUBLISH]  # Missing PERMISSION!
)
```

### Permission Types Breakdown

| Permission | Includes |
|------------|----------|
| `CRUD` | CREATE, READ, UPDATE, DELETE |
| `ALL` | CRUD + COMMENT + PUBLISH + PERMISSION |

### Relevant Database Tables

- `corpuses_corpususerobjectpermission` - User-level permissions
- `corpuses_corpusgroupobjectpermission` - Group-level permissions
- `auth_permission` - Permission definitions
