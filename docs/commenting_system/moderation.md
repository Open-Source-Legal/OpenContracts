# Moderation System

## Overview

The moderation system provides corpus owners and designated moderators with tools to manage discussions, maintain community standards, and handle inappropriate content. The system features granular permissions, complete audit trails, and reversible moderation actions.

## Core Concepts

### Permission Hierarchy

1. **Superusers**: Full access to all moderation features
2. **Corpus Owners**: Complete moderation control over their corpus
3. **Designated Moderators**: Specific permissions granted by corpus owners
4. **Content Creators**: Can delete their own messages

### Moderation Actions

- **Lock Thread**: Prevent new messages in a conversation
- **Unlock Thread**: Re-enable posting to a locked conversation
- **Pin Thread**: Highlight important discussions at the top
- **Unpin Thread**: Remove thread from pinned position
- **Delete Message**: Soft delete individual message
- **Delete Thread**: Soft delete entire conversation
- **Restore**: Restore soft-deleted content

### Granular Permissions

Moderators can be granted specific permissions:

- `lock_threads`: Lock/unlock conversations
- `pin_threads`: Pin/unpin conversations
- `delete_messages`: Delete individual messages
- `delete_threads`: Delete entire conversations

## Database Models

### CorpusModerator

**Purpose**: Designates users as moderators with specific permissions.

**Location**: `opencontractserver/conversations/models.py:794-854`

**Schema**:

```python
class CorpusModerator(BaseOCModel):
    corpus = models.ForeignKey(
        Corpus,
        related_name="moderators",
        on_delete=models.CASCADE
    )
    user = models.ForeignKey(
        User,
        related_name="moderated_corpuses",
        on_delete=models.CASCADE
    )
    permissions = models.JSONField(default=list)
    assigned_by = models.ForeignKey(
        User,
        related_name="assigned_moderators",
        on_delete=models.CASCADE
    )

    class Meta:
        unique_together = [("corpus", "user")]
        indexes = [
            models.Index(fields=["corpus"]),
            models.Index(fields=["user"]),
        ]
```

**Valid Permissions**:

```python
MODERATOR_PERMISSIONS = [
    "lock_threads",      # Can lock/unlock threads
    "pin_threads",       # Can pin/unpin threads
    "delete_messages",   # Can delete individual messages
    "delete_threads",    # Can delete entire threads
]
```

**Permission Examples**:

```python
# Full moderator (all permissions)
moderator.permissions = [
    "lock_threads",
    "pin_threads",
    "delete_messages",
    "delete_threads"
]

# Limited moderator (only thread management)
moderator.permissions = ["lock_threads", "pin_threads"]

# Content moderator (only delete permissions)
moderator.permissions = ["delete_messages", "delete_threads"]

# Minimal moderator (only lock)
moderator.permissions = ["lock_threads"]
```

**Key Methods**:

```python
def has_permission(self, permission: str) -> bool:
    """Check if moderator has specific permission"""
    return permission in self.permissions
```

### ModerationAction

**Purpose**: Immutable audit log of all moderation actions.

**Location**: `opencontractserver/conversations/models.py:885-951`

**Schema**:

```python
class ModerationAction(BaseOCModel):
    conversation = models.ForeignKey(
        Conversation,
        null=True,
        blank=True,
        related_name="moderation_actions",
        on_delete=models.CASCADE
    )
    message = models.ForeignKey(
        ChatMessage,
        null=True,
        blank=True,
        related_name="moderation_actions",
        on_delete=models.CASCADE
    )
    action_type = models.CharField(
        max_length=50,
        choices=ModerationActionType.choices
    )
    moderator = models.ForeignKey(
        User,
        related_name="moderation_actions",
        on_delete=models.CASCADE
    )
    reason = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        permissions = [("view_moderation_action", "Can view moderation actions")]
        indexes = [
            models.Index(fields=["conversation"]),
            models.Index(fields=["message"]),
            models.Index(fields=["moderator"]),
            models.Index(fields=["action_type"]),
            models.Index(fields=["created_at"]),
        ]
```

**Action Types**:

```python
class ModerationActionType(models.TextChoices):
    LOCK_THREAD = "lock_thread", "Lock Thread"
    UNLOCK_THREAD = "unlock_thread", "Unlock Thread"
    PIN_THREAD = "pin_thread", "Pin Thread"
    UNPIN_THREAD = "unpin_thread", "Unpin Thread"
    DELETE_MESSAGE = "delete_message", "Delete Message"
    DELETE_THREAD = "delete_thread", "Delete Thread"
    RESTORE_MESSAGE = "restore_message", "Restore Message"
    RESTORE_THREAD = "restore_thread", "Restore Thread"
```

**Key Features**:

1. **Immutable**: No update or delete allowed (audit trail integrity)
2. **Complete Context**: Records who, what, when, and why
3. **Indexed**: Fast queries for reporting and analysis
4. **Nullable FK**: Can track action on deleted conversations/messages

### Conversation Moderation Fields

**Location**: `opencontractserver/conversations/models.py:141-432`

**Locking**:

```python
is_locked = models.BooleanField(default=False)
locked_by = models.ForeignKey(User, null=True, blank=True)
locked_at = models.DateTimeField(null=True, blank=True)
```

**Pinning**:

```python
is_pinned = models.BooleanField(default=False)
pinned_by = models.ForeignKey(User, null=True, blank=True)
pinned_at = models.DateTimeField(null=True, blank=True)
```

**Soft Deletion**:

```python
deleted_at = models.DateTimeField(null=True, blank=True)
deleted_by = models.ForeignKey(User, null=True, blank=True)
```

## Moderation Workflows

### 1. Designating Moderators

**GraphQL Mutation**:

```graphql
mutation {
  addModerator(
    corpusId: "Q29ycHVzVHlwZTox"
    userId: "VXNlclR5cGU6NQ=="
    permissions: ["lock_threads", "pin_threads", "delete_messages"]
  ) {
    ok
    message
    obj {
      id
      user {
        username
      }
      permissions
    }
  }
}
```

**Implementation** (`config/graphql/moderation_mutations.py:272-357`):

```python
@staticmethod
@graphql_ratelimit(rate=RateLimits.MODERATE_ACTION)
def mutate(root, info, corpus_id, user_id, permissions):
    current_user = info.context.user
    corpus = Corpus.objects.get(id=corpus_id)

    # Only corpus owners can add moderators
    if corpus.creator != current_user:
        return AddModeratorMutation(
            ok=False,
            message="Only corpus owners can add moderators"
        )

    # Validate permissions
    valid_perms = [
        "lock_threads",
        "pin_threads",
        "delete_messages",
        "delete_threads"
    ]
    for perm in permissions:
        if perm not in valid_perms:
            return AddModeratorMutation(
                ok=False,
                message=f"Invalid permission: {perm}"
            )

    # Create moderator
    moderator = CorpusModerator.objects.create(
        corpus=corpus,
        user=User.objects.get(id=user_id),
        permissions=permissions,
        assigned_by=current_user
    )

    return AddModeratorMutation(
        ok=True,
        message="Moderator added",
        obj=moderator
    )
```

**Permissions**:
- Only corpus owners can add moderators
- Cannot add yourself as moderator (already owner)
- Permissions must be from valid list

### 2. Updating Moderator Permissions

**GraphQL Mutation**:

```graphql
mutation {
  updateModeratorPermissions(
    corpusId: "Q29ycHVzVHlwZTox"
    userId: "VXNlclR5cGU6NQ=="
    permissions: ["lock_threads", "delete_threads"]  # Changed
  ) {
    ok
    message
    obj {
      permissions
    }
  }
}
```

**Implementation** (`moderation_mutations.py:425-511`):

```python
@staticmethod
@graphql_ratelimit(rate=RateLimits.MODERATE_ACTION)
def mutate(root, info, corpus_id, user_id, permissions):
    current_user = info.context.user
    corpus = Corpus.objects.get(id=corpus_id)

    # Only corpus owners can update permissions
    if corpus.creator != current_user:
        return UpdateModeratorPermissionsMutation(
            ok=False,
            message="Only corpus owners can update permissions"
        )

    # Get existing moderator
    moderator = CorpusModerator.objects.get(
        corpus=corpus,
        user_id=user_id
    )

    # Validate and update permissions
    # ... validation code ...

    moderator.permissions = permissions
    moderator.save()

    return UpdateModeratorPermissionsMutation(
        ok=True,
        message="Permissions updated",
        obj=moderator
    )
```

### 3. Removing Moderators

**GraphQL Mutation**:

```graphql
mutation {
  removeModerator(
    corpusId: "Q29ycHVzVHlwZTox"
    userId: "VXNlclR5cGU6NQ=="
  ) {
    ok
    message
  }
}
```

**Implementation** (`moderation_mutations.py:360-422`):

```python
@staticmethod
@graphql_ratelimit(rate=RateLimits.MODERATE_ACTION)
def mutate(root, info, corpus_id, user_id):
    current_user = info.context.user
    corpus = Corpus.objects.get(id=corpus_id)

    # Only corpus owners can remove moderators
    if corpus.creator != current_user:
        return RemoveModeratorMutation(
            ok=False,
            message="Only corpus owners can remove moderators"
        )

    # Delete moderator record
    CorpusModerator.objects.filter(
        corpus=corpus,
        user_id=user_id
    ).delete()

    return RemoveModeratorMutation(
        ok=True,
        message="Moderator removed"
    )
```

### 4. Locking Threads

**Use Case**: Prevent further discussion on resolved or inappropriate threads.

**GraphQL Mutation**:

```graphql
mutation {
  lockThread(
    conversationId: "Q29udmVyc2F0aW9uVHlwZTo1MA=="
    reason: "Discussion has become unproductive"
  ) {
    ok
    message
    obj {
      isLocked
      lockedBy {
        username
      }
      lockedAt
    }
  }
}
```

**Implementation** (`moderation_mutations.py:28-86`):

```python
@staticmethod
@graphql_ratelimit(rate=RateLimits.MODERATE_ACTION)
def mutate(root, info, conversation_id, reason=None):
    user = info.context.user
    conversation = Conversation.objects.get(id=conversation_id)

    # Check general moderation permission
    if not conversation.can_moderate(user):
        return LockThreadMutation(
            ok=False,
            message="You don't have permission to moderate this thread"
        )

    # Check specific "lock_threads" permission for moderators
    if conversation.chat_with_corpus:
        corpus = conversation.chat_with_corpus
        if corpus.creator != user:  # Not owner, check moderator perms
            try:
                moderator = CorpusModerator.objects.get(
                    corpus=corpus,
                    user=user
                )
                if not moderator.has_permission("lock_threads"):
                    return LockThreadMutation(
                        ok=False,
                        message="You don't have lock permission"
                    )
            except CorpusModerator.DoesNotExist:
                return LockThreadMutation(
                    ok=False,
                    message="You are not a moderator"
                )

    # Lock the thread
    conversation.lock(user, reason)

    # Create audit record
    ModerationAction.objects.create(
        conversation=conversation,
        action_type=ModerationActionType.LOCK_THREAD,
        moderator=user,
        reason=reason
    )

    return LockThreadMutation(
        ok=True,
        message="Thread locked",
        obj=conversation
    )
```

**Model Method** (`models.py:284-298`):

```python
def lock(self, user: User, reason: str = None):
    """Lock conversation to prevent new messages"""
    self.is_locked = True
    self.locked_by = user
    self.locked_at = timezone.now()
    self.save(update_fields=["is_locked", "locked_by", "locked_at"])
```

**Effect**:
- `is_locked` set to `True`
- New messages blocked (checked in `createThreadMessage` mutation)
- Existing messages remain visible
- Can be unlocked later

### 5. Unlocking Threads

**GraphQL Mutation**:

```graphql
mutation {
  unlockThread(
    conversationId: "Q29udmVyc2F0aW9uVHlwZTo1MA=="
    reason: "Issue resolved, reopening discussion"
  ) {
    ok
    obj {
      isLocked
    }
  }
}
```

**Model Method** (`models.py:300-314`):

```python
def unlock(self, user: User, reason: str = None):
    """Unlock conversation"""
    self.is_locked = False
    self.locked_by = None
    self.locked_at = None
    self.save(update_fields=["is_locked", "locked_by", "locked_at"])
```

### 6. Pinning Threads

**Use Case**: Highlight important announcements or FAQs.

**GraphQL Mutation**:

```graphql
mutation {
  pinThread(
    conversationId: "Q29udmVyc2F0aW9uVHlwZTo1MA=="
    reason: "Important community guidelines"
  ) {
    ok
    obj {
      isPinned
      pinnedBy {
        username
      }
      pinnedAt
    }
  }
}
```

**Model Method** (`models.py:316-330`):

```python
def pin(self, user: User, reason: str = None):
    """Pin thread to top of list"""
    self.is_pinned = True
    self.pinned_by = user
    self.pinned_at = timezone.now()
    self.save(update_fields=["is_pinned", "pinned_by", "pinned_at"])
```

**Effect**:
- Thread appears at top of list (frontend sorting)
- Highlighted visually (frontend styling)
- Multiple threads can be pinned

### 7. Unpinning Threads

**GraphQL Mutation**:

```graphql
mutation {
  unpinThread(
    conversationId: "Q29udmVyc2F0aW9uVHlwZTo1MA=="
  ) {
    ok
    obj {
      isPinned
    }
  }
}
```

**Model Method** (`models.py:332-346`):

```python
def unpin(self, user: User, reason: str = None):
    """Unpin thread"""
    self.is_pinned = False
    self.pinned_by = None
    self.pinned_at = None
    self.save(update_fields=["is_pinned", "pinned_by", "pinned_at"])
```

### 8. Deleting Messages

**Use Case**: Remove spam, harassment, or off-topic content.

**GraphQL Mutation**:

```graphql
mutation {
  deleteMessage(
    messageId: "Q2hhdE1lc3NhZ2VUeXBlOjEwMA=="
  ) {
    ok
    message
  }
}
```

**Implementation** (`conversation_mutations.py:290-338`):

```python
@staticmethod
@graphql_ratelimit(rate=RateLimits.MODERATE_ACTION)
def mutate(root, info, message_id):
    user = info.context.user
    message = ChatMessage.objects.get(id=message_id)

    # Check if user is creator OR has moderation permission
    is_creator = message.creator == user

    can_moderate = False
    if message.conversation.can_moderate(user):
        # Check specific permission for moderators
        if message.conversation.chat_with_corpus:
            corpus = message.conversation.chat_with_corpus
            if corpus.creator != user:  # Not owner
                moderator = CorpusModerator.objects.get(
                    corpus=corpus,
                    user=user
                )
                can_moderate = moderator.has_permission("delete_messages")
            else:
                can_moderate = True  # Owner can always delete

    if not is_creator and not can_moderate:
        return DeleteMessageMutation(
            ok=False,
            message="You don't have permission to delete this message"
        )

    # Soft delete the message
    message.soft_delete_message(user)

    # Create audit record (if moderation action, not self-delete)
    if not is_creator:
        ModerationAction.objects.create(
            message=message,
            action_type=ModerationActionType.DELETE_MESSAGE,
            moderator=user
        )

    return DeleteMessageMutation(
        ok=True,
        message="Message deleted"
    )
```

**Model Method** (`models.py:584-592`):

```python
def soft_delete_message(self, user: User):
    """Soft delete the message"""
    self.deleted_at = timezone.now()
    self.deleted_by = user
    self.save(update_fields=["deleted_at", "deleted_by"])
```

**Effect**:
- Message marked as deleted (`deleted_at` timestamp set)
- Hidden from default queries (via `SoftDeleteManager`)
- Can be restored later
- Preserves data for audit trail

### 9. Deleting Threads

**Use Case**: Remove entire inappropriate discussions.

**GraphQL Mutation**:

```graphql
mutation {
  deleteConversation(
    conversationId: "Q29udmVyc2F0aW9uVHlwZTo1MA=="
  ) {
    ok
    message
  }
}
```

**Model Method** (`models.py:348-361`):

```python
def soft_delete_thread(self, user: User):
    """Soft delete the conversation"""
    self.deleted_at = timezone.now()
    self.deleted_by = user
    self.save(update_fields=["deleted_at", "deleted_by"])
```

**Permissions**:
- Conversation creator can always delete
- Moderators must have "delete_threads" permission
- Corpus owners can delete any thread in their corpus

**Effect**:
- Conversation and all messages hidden
- Data preserved for audit trail
- Can be restored

### 10. Restoring Deleted Content

**Model Methods** (`models.py:363-377`, `594-607`):

```python
def restore_thread(self, user: User):
    """Restore a soft-deleted conversation"""
    self.deleted_at = None
    self.deleted_by = None
    self.save(update_fields=["deleted_at", "deleted_by"])

def restore_message(self, user: User):
    """Restore a soft-deleted message"""
    self.deleted_at = None
    self.deleted_by = None
    self.save(update_fields=["deleted_at", "deleted_by"])
```

**Note**: GraphQL mutations for restore not yet implemented, but model methods exist.

## Permission Checking

### can_moderate() Method

**Location**: `Conversation.can_moderate()` (`models.py:261-282`)

```python
def can_moderate(self, user) -> bool:
    """Check if user has moderation permissions"""

    if self.chat_with_corpus:
        # Corpus owner has full permissions
        if self.chat_with_corpus.creator == user:
            return True

        # Check designated moderator status
        try:
            moderator = CorpusModerator.objects.get(
                corpus=self.chat_with_corpus,
                user=user
            )
            # Has permissions if any permissions are granted
            return bool(moderator.permissions)
        except CorpusModerator.DoesNotExist:
            return False

    # For non-corpus conversations, only creator can moderate
    return self.creator == user
```

**Decision Flow**:

1. Is this a corpus conversation?
   - Yes: Check if user is corpus owner → Full access
   - Yes: Check if user is designated moderator → Check specific permissions
   - No: Check if user is conversation creator → Full access

2. For specific actions, check granular permissions:
   - Lock/Unlock: Check `has_permission("lock_threads")`
   - Pin/Unpin: Check `has_permission("pin_threads")`
   - Delete Message: Check `has_permission("delete_messages")`
   - Delete Thread: Check `has_permission("delete_threads")`

### has_permission() Method

**Location**: `CorpusModerator.has_permission()` (`models.py:844-850`)

```python
def has_permission(self, permission: str) -> bool:
    """Check if moderator has specific permission"""
    return permission in self.permissions
```

**Usage in Mutations**:

```python
# In lockThread mutation
if corpus.creator != user:  # Not owner
    moderator = CorpusModerator.objects.get(corpus=corpus, user=user)
    if not moderator.has_permission("lock_threads"):
        return Error(message="You don't have lock permission")
```

## Audit Trail

### ModerationAction Records

Every moderation action creates an immutable audit record:

```python
ModerationAction.objects.create(
    conversation=conversation,  # or None if message-level
    message=message,            # or None if thread-level
    action_type=ModerationActionType.LOCK_THREAD,
    moderator=user,
    reason=reason               # Optional explanation
)
```

### Querying Audit Log

**By Conversation**:

```python
actions = ModerationAction.objects.filter(
    conversation=conversation
).order_by("-created_at")

for action in actions:
    print(f"{action.moderator.username} {action.action_type} at {action.created_at}")
    if action.reason:
        print(f"  Reason: {action.reason}")
```

**By Moderator**:

```python
actions = ModerationAction.objects.filter(
    moderator=user
).order_by("-created_at")
```

**By Action Type**:

```python
deletions = ModerationAction.objects.filter(
    action_type=ModerationActionType.DELETE_MESSAGE
)
```

**GraphQL Query** (example, not yet implemented):

```graphql
query {
  moderationActions(
    conversationId: "Q29udmVyc2F0aW9uVHlwZTo1MA=="
  ) {
    actionType
    moderator {
      username
    }
    reason
    createdAt
  }
}
```

### Use Cases for Audit Trail

1. **Transparency**: Users can see moderation history
2. **Accountability**: Track moderator actions
3. **Appeals**: Review moderation decisions
4. **Analytics**: Identify patterns (e.g., which threads require most moderation)
5. **Compliance**: Legal/regulatory requirements

## Rate Limiting

All moderation mutations use the same rate limit:

**Rate**: 20 actions per minute

**Rationale**: Prevents moderation abuse while allowing legitimate batch actions.

**Applied To**:
- lockThread
- unlockThread
- pinThread
- unpinThread
- deleteConversation
- deleteMessage
- addModerator
- removeModerator
- updateModeratorPermissions

## Frontend Integration (Planned)

### Moderator UI Components

**Moderator Badge**:

```typescript
function ModeratorBadge({ user, corpus }) {
  const { data } = useQuery(GET_MODERATOR_STATUS, {
    variables: { userId: user.id, corpusId: corpus.id }
  });

  if (!data?.isModerator) return null;

  return <Badge>Moderator</Badge>;
}
```

**Moderation Controls**:

```typescript
function ThreadModerationControls({ conversation }) {
  const [lockThread] = useMutation(LOCK_THREAD);
  const [pinThread] = useMutation(PIN_THREAD);
  const [deleteThread] = useMutation(DELETE_THREAD);

  // Check user permissions
  const canModerate = conversation.canModerate;
  const permissions = conversation.moderatorPermissions;

  if (!canModerate) return null;

  return (
    <div>
      {permissions.includes("lock_threads") && (
        <Button onClick={() => lockThread({ variables: { conversationId: conversation.id } })}>
          {conversation.isLocked ? "Unlock" : "Lock"}
        </Button>
      )}
      {permissions.includes("pin_threads") && (
        <Button onClick={() => pinThread({ variables: { conversationId: conversation.id } })}>
          {conversation.isPinned ? "Unpin" : "Pin"}
        </Button>
      )}
      {permissions.includes("delete_threads") && (
        <Button onClick={() => deleteThread({ variables: { conversationId: conversation.id } })}>
          Delete
        </Button>
      )}
    </div>
  );
}
```

**Moderator Management**:

```typescript
function ModeratorManagement({ corpus }) {
  const [addModerator] = useMutation(ADD_MODERATOR);
  const [removeModerator] = useMutation(REMOVE_MODERATOR);

  // Only corpus owners see this
  if (!corpus.isOwner) return null;

  return (
    <div>
      <h3>Moderators</h3>
      {corpus.moderators.map(mod => (
        <div key={mod.id}>
          {mod.user.username}
          <PermissionList permissions={mod.permissions} />
          <Button onClick={() => removeModerator({ variables: { userId: mod.user.id } })}>
            Remove
          </Button>
        </div>
      ))}
      <AddModeratorForm onAdd={addModerator} />
    </div>
  );
}
```

## Best Practices

### 1. Provide Reasons

Always include a reason when moderating:

```graphql
mutation {
  deleteMessage(
    messageId: "..."
    reason: "Spam/commercial content violates community guidelines"
  )
}
```

**Benefits**:
- Transparency for users
- Context for appeals
- Learning for community

### 2. Graduated Response

Use moderation actions proportionally:

1. **First offense**: Warning (comment or private message)
2. **Repeated issues**: Lock thread or delete specific messages
3. **Severe violations**: Delete thread or ban user

### 3. Clear Guidelines

Establish and publish community guidelines:

```markdown
# Community Guidelines

## Acceptable Use
- Respectful discussion
- Constructive feedback
- On-topic contributions

## Prohibited
- Harassment or personal attacks
- Spam or commercial content
- Off-topic discussions

## Moderation
Moderators may lock, delete, or pin threads at their discretion.
```

### 4. Moderator Coordination

For multiple moderators:

- Agree on moderation standards
- Communicate about actions (via private channel)
- Review moderation log regularly
- Handle appeals collectively

### 5. Reversible Actions

Use soft delete instead of hard delete:

- Allows appeals and restoration
- Preserves audit trail
- Reduces risk of mistakes

## Testing

**Test File**: `opencontractserver/tests/test_moderation.py`

**Key Test Cases**:

1. **Moderator Creation**:
   - Corpus owner can add moderator
   - Non-owner cannot add moderator
   - Permissions validated

2. **Thread Locking**:
   - Owner can lock
   - Moderator with permission can lock
   - Moderator without permission cannot lock
   - Locked thread prevents new messages

3. **Thread Pinning**:
   - Pinned threads have correct metadata
   - Permission checks work

4. **Message Deletion**:
   - Creator can delete own message
   - Moderator with permission can delete any message
   - Soft delete preserves data

5. **Audit Trail**:
   - ModerationAction created for each action
   - Correct action type, moderator, and reason recorded

Run tests:

```bash
docker compose -f test.yml run django python manage.py test \
    opencontractserver.tests.test_moderation
```

## Future Enhancements

### 1. User Suspension

Temporarily ban users from posting:

```python
class UserSuspension(BaseOCModel):
    user = models.ForeignKey(User)
    corpus = models.ForeignKey(Corpus)
    suspended_by = models.ForeignKey(User)
    reason = models.TextField()
    suspended_until = models.DateTimeField()
```

### 2. Auto-Moderation Rules

Automatic actions based on criteria:

```python
# Auto-lock threads after 90 days of inactivity
# Auto-pin threads with high vote scores
# Auto-flag messages with banned words
```

### 3. Moderation Queue

Review flagged content before taking action:

```python
class ModerationQueue(BaseOCModel):
    message = models.ForeignKey(ChatMessage)
    flagged_by = models.ForeignKey(User)
    reason = models.TextField()
    status = models.CharField(choices=["pending", "approved", "removed"])
```

### 4. Bulk Actions

Moderate multiple items at once:

```graphql
mutation {
  bulkDeleteMessages(
    messageIds: ["...", "...", "..."]
    reason: "Spam wave"
  )
}
```

### 5. Moderation Statistics

Track moderation metrics:

```python
# Actions per moderator
# Most common action types
# Response time to flags
# Appeal success rate
```

### 6. Role-Based Permissions

Predefined moderator roles:

```python
MODERATOR_ROLES = {
    "junior": ["lock_threads"],
    "standard": ["lock_threads", "pin_threads", "delete_messages"],
    "senior": ["lock_threads", "pin_threads", "delete_messages", "delete_threads"],
}
```

### 7. Community Flagging

Allow users to report content:

```graphql
mutation {
  flagMessage(
    messageId: "..."
    reason: "Spam"
  )
}
```

Moderators review flagged content in queue.
