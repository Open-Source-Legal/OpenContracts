# Backend Architecture

## Overview

The backend implementation provides a complete foundation for the collaboration system with database models, business logic, permission checking, and automatic updates via Django signals.

## Database Models

All models are defined in `opencontractserver/conversations/models.py`.

### Core Models

#### Conversation

**Purpose**: Stores discussion threads or agent-based chats.

**Location**: `opencontractserver/conversations/models.py:141-432`

**Key Fields**:

```python
class Conversation(BaseOCModel):
    conversation_type = models.CharField(
        max_length=10,
        choices=ConversationType.choices,
        default=ConversationType.CHAT
    )
    title = models.CharField(max_length=512, null=True, blank=True)
    description = models.TextField(null=True, blank=True)

    # Context linking - exactly one must be set
    chat_with_corpus = models.ForeignKey(Corpus, null=True, blank=True)
    chat_with_document = models.ForeignKey(Document, null=True, blank=True)

    # Moderation fields
    is_locked = models.BooleanField(default=False)
    locked_by = models.ForeignKey(User, null=True, blank=True)
    locked_at = models.DateTimeField(null=True, blank=True)
    is_pinned = models.BooleanField(default=False)
    pinned_by = models.ForeignKey(User, null=True, blank=True)
    pinned_at = models.DateTimeField(null=True, blank=True)

    # Soft deletion
    deleted_at = models.DateTimeField(null=True, blank=True)
```

**Conversation Types**:
- `CHAT`: Agent-based conversation (document or corpus analysis)
- `THREAD`: Discussion thread (community collaboration)

**Database Constraints**:
```python
class Meta:
    constraints = [
        models.CheckConstraint(
            check=(
                Q(chat_with_corpus__isnull=False, chat_with_document__isnull=True)
                | Q(chat_with_corpus__isnull=True, chat_with_document__isnull=False)
            ),
            name="conversation_exactly_one_chat_target",
        )
    ]
```

**Key Methods**:

```python
def lock(self, user: User, reason: str = None):
    """Lock conversation to prevent new messages"""

def unlock(self, user: User, reason: str = None):
    """Unlock conversation"""

def pin(self, user: User, reason: str = None):
    """Pin thread to top of list"""

def unpin(self, user: User, reason: str = None):
    """Unpin thread"""

def soft_delete_thread(self, user: User):
    """Soft delete the conversation"""

def restore_thread(self, user: User):
    """Restore a soft-deleted conversation"""

def can_moderate(self, user: User) -> bool:
    """Check if user can moderate this conversation"""
```

**Managers**:
- `objects`: Default manager (excludes soft-deleted)
- `all_objects`: Includes soft-deleted items

#### ChatMessage

**Purpose**: Individual messages within conversations (both chat and thread types).

**Location**: `opencontractserver/conversations/models.py:434-598`

**Key Fields**:

```python
class ChatMessage(BaseOCModel):
    conversation = models.ForeignKey(
        Conversation,
        related_name="chat_messages",
        on_delete=models.CASCADE
    )

    # Message type and agent
    msg_type = models.CharField(
        max_length=10,
        choices=MessageType.choices,
        default=MessageType.HUMAN
    )
    agent_type = models.CharField(
        max_length=50,
        choices=AgentType.choices,
        null=True,
        blank=True
    )

    # Threading support
    parent_message = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        related_name="replies",
        on_delete=models.CASCADE
    )

    # Content
    content = models.TextField(blank=True, default="")
    data = models.JSONField(default=dict, blank=True)

    # State tracking (for agent messages)
    state = models.CharField(
        max_length=20,
        choices=MessageStateChoices.choices,
        default=MessageStateChoices.IN_PROGRESS
    )

    # Voting (denormalized for performance)
    upvote_count = models.IntegerField(default=0)
    downvote_count = models.IntegerField(default=0)

    # Soft deletion
    deleted_at = models.DateTimeField(null=True, blank=True)
    deleted_by = models.ForeignKey(User, null=True, blank=True)
```

**Message Types**:
- `SYSTEM`: System-generated messages
- `HUMAN`: User-created messages
- `LLM`: Agent-generated messages

**Agent Types** (for LLM messages):
- `DOCUMENT_AGENT`: Document analysis agent
- `CORPUS_AGENT`: Corpus-wide analysis agent

**Message States**:
- `IN_PROGRESS`: Message being generated
- `COMPLETED`: Message complete
- `CANCELLED`: Generation cancelled
- `ERROR`: Error occurred
- `AWAITING_APPROVAL`: Requires user approval

**Key Methods**:

```python
def soft_delete_message(self, user: User):
    """Soft delete the message"""

def restore_message(self, user: User):
    """Restore a soft-deleted message"""
```

### Voting Models

#### MessageVote

**Purpose**: Tracks individual votes on messages.

**Location**: `opencontractserver/conversations/models.py:634-685`

**Key Fields**:

```python
class MessageVote(BaseOCModel):
    message = models.ForeignKey(
        ChatMessage,
        related_name="votes",
        on_delete=models.CASCADE
    )
    vote_type = models.CharField(
        max_length=10,
        choices=VoteType.choices
    )
    creator = models.ForeignKey(
        User,
        related_name="message_votes",
        on_delete=models.CASCADE
    )
```

**Vote Types**:
- `UPVOTE`: Positive vote
- `DOWNVOTE`: Negative vote

**Database Constraints**:
```python
class Meta:
    unique_together = [("message", "creator")]
    indexes = [
        models.Index(fields=["message", "vote_type"]),
        models.Index(fields=["creator"]),
    ]
```

This ensures:
- Each user can only vote once per message
- Fast lookups for vote counts
- Fast user vote history queries

#### UserReputation

**Purpose**: Caches reputation scores for users (globally and per-corpus).

**Location**: `opencontractserver/conversations/models.py:703-777`

**Key Fields**:

```python
class UserReputation(BaseOCModel):
    user = models.ForeignKey(
        User,
        related_name="reputation_scores",
        on_delete=models.CASCADE
    )
    corpus = models.ForeignKey(
        Corpus,
        null=True,
        blank=True,
        on_delete=models.CASCADE
    )

    # Computed scores
    reputation_score = models.IntegerField(default=0)
    total_upvotes_received = models.IntegerField(default=0)
    total_downvotes_received = models.IntegerField(default=0)

    # Calculation tracking
    last_calculated_at = models.DateTimeField(auto_now=True)
```

**Reputation Calculation**:
```
reputation_score = total_upvotes_received - total_downvotes_received
```

**Database Constraints**:
```python
class Meta:
    unique_together = [("user", "corpus")]
    indexes = [
        models.Index(fields=["user"]),
        models.Index(fields=["corpus"]),
        models.Index(fields=["reputation_score"]),
    ]
```

**Design Notes**:
- `corpus=NULL` represents global reputation
- Denormalized for performance (avoids aggregate queries)
- Updated automatically via Django signals
- Can be recalculated from scratch if needed

### Moderation Models

#### CorpusModerator

**Purpose**: Designates users as moderators with specific permissions.

**Location**: `opencontractserver/conversations/models.py:794-854`

**Key Fields**:

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

**Database Constraints**:
```python
class Meta:
    unique_together = [("corpus", "user")]
    indexes = [
        models.Index(fields=["corpus"]),
        models.Index(fields=["user"]),
    ]
```

**Key Methods**:

```python
def has_permission(self, permission: str) -> bool:
    """Check if moderator has specific permission"""
    return permission in self.permissions
```

**Permission Examples**:

```python
# Full moderator
moderator.permissions = [
    "lock_threads",
    "pin_threads",
    "delete_messages",
    "delete_threads"
]

# Limited moderator (can only lock threads)
moderator.permissions = ["lock_threads"]
```

#### ModerationAction

**Purpose**: Immutable audit log of all moderation actions.

**Location**: `opencontractserver/conversations/models.py:885-951`

**Key Fields**:

```python
class ModerationAction(BaseOCModel):
    conversation = models.ForeignKey(
        Conversation,
        null=True,
        blank=True,
        on_delete=models.CASCADE
    )
    message = models.ForeignKey(
        ChatMessage,
        null=True,
        blank=True,
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
```

**Action Types**:
- `LOCK_THREAD`
- `UNLOCK_THREAD`
- `PIN_THREAD`
- `UNPIN_THREAD`
- `DELETE_MESSAGE`
- `DELETE_THREAD`
- `RESTORE_MESSAGE`
- `RESTORE_THREAD`

**Database Constraints**:
```python
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

**Design Notes**:
- Immutable (no update/delete allowed)
- Complete audit trail for compliance
- Can track who did what, when, and why
- Indexed for fast reporting and analysis

## Soft Delete Pattern

### Implementation

The soft delete pattern allows "deleting" records without actually removing them from the database, enabling:
- Data preservation for audit trails
- Reversible moderation actions
- Maintaining referential integrity

### Custom QuerySet

**Location**: `opencontractserver/conversations/models.py:46-91`

```python
class SoftDeleteQuerySet(models.QuerySet):
    def delete(self):
        """Soft delete by setting deleted_at timestamp"""
        return super().update(deleted_at=timezone.now())

    def hard_delete(self):
        """Actually delete from database"""
        return super().delete()

    def alive(self):
        """Only non-deleted records"""
        return self.filter(deleted_at=None)

    def dead(self):
        """Only deleted records"""
        return self.exclude(deleted_at=None)
```

### Custom Manager

**Location**: `opencontractserver/conversations/models.py:95-118`

```python
class SoftDeleteManager(models.Manager):
    def __init__(self, *args, **kwargs):
        self.alive_only = kwargs.pop("alive_only", True)
        super().__init__(*args, **kwargs)

    def get_queryset(self):
        if self.alive_only:
            return SoftDeleteQuerySet(self.model).alive()
        return SoftDeleteQuerySet(self.model)
```

### Usage in Models

```python
class Conversation(BaseOCModel):
    deleted_at = models.DateTimeField(null=True, blank=True)

    # Default manager excludes deleted
    objects = SoftDeleteManager()

    # Includes deleted
    all_objects = SoftDeleteManager(alive_only=False)
```

### Querying Examples

```python
# Only active conversations
conversations = Conversation.objects.all()

# Include deleted conversations
all_conversations = Conversation.all_objects.all()

# Only deleted conversations
deleted = Conversation.all_objects.dead()

# Restore a deleted conversation
conversation.deleted_at = None
conversation.save()
```

## Django Signals

Signals provide automatic updates when data changes, ensuring consistency without requiring manual coordination.

**Location**: `opencontractserver/conversations/signals.py`

### Vote Count Updates

**Signal**: `post_save` and `post_delete` on `MessageVote`

```python
@receiver(post_save, sender=MessageVote)
def update_vote_counts_on_save(sender, instance, created, **kwargs):
    """Recalculate message vote counts when vote is created/updated"""
    recalculate_message_vote_counts(instance.message)

@receiver(post_delete, sender=MessageVote)
def update_vote_counts_on_delete(sender, instance, **kwargs):
    """Recalculate message vote counts when vote is deleted"""
    recalculate_message_vote_counts(instance.message)
```

**Implementation** (`signals.py:27-50`):

```python
def recalculate_message_vote_counts(message):
    """Recalculate vote counts from scratch"""
    vote_counts = message.votes.aggregate(
        upvotes=Count("id", filter=Q(vote_type=VoteType.UPVOTE)),
        downvotes=Count("id", filter=Q(vote_type=VoteType.DOWNVOTE)),
    )

    message.upvote_count = vote_counts["upvotes"] or 0
    message.downvote_count = vote_counts["downvotes"] or 0
    message.save(update_fields=["upvote_count", "downvote_count"])
```

**Benefits**:
- Vote counts always accurate
- Automatic updates on any vote change
- Performance: denormalized counts avoid COUNT queries on message display

### Reputation Calculation

**Signal**: `post_save` and `post_delete` on `MessageVote`

```python
@receiver(post_save, sender=MessageVote)
@receiver(post_delete, sender=MessageVote)
def update_reputation_on_vote_change(sender, instance, **kwargs):
    """Update reputation when votes change"""
    message_author = instance.message.creator

    # Update global reputation
    update_user_reputation(message_author, corpus=None)

    # Update corpus-specific reputation if applicable
    conversation = instance.message.conversation
    if conversation.chat_with_corpus:
        update_user_reputation(message_author, corpus=conversation.chat_with_corpus)
```

**Implementation** (`signals.py:86-132`):

```python
def update_user_reputation(user, corpus=None):
    """Calculate and update user reputation"""

    # Get all messages by user in scope
    messages_query = ChatMessage.objects.filter(creator=user)
    if corpus:
        messages_query = messages_query.filter(
            conversation__chat_with_corpus=corpus
        )

    # Aggregate vote counts
    vote_stats = messages_query.aggregate(
        total_upvotes=Count(
            "votes",
            filter=Q(votes__vote_type=VoteType.UPVOTE)
        ),
        total_downvotes=Count(
            "votes",
            filter=Q(votes__vote_type=VoteType.DOWNVOTE)
        ),
    )

    total_upvotes = vote_stats["total_upvotes"] or 0
    total_downvotes = vote_stats["total_downvotes"] or 0
    reputation_score = total_upvotes - total_downvotes

    # Create or update reputation record
    UserReputation.objects.update_or_create(
        user=user,
        corpus=corpus,
        defaults={
            "reputation_score": reputation_score,
            "total_upvotes_received": total_upvotes,
            "total_downvotes_received": total_downvotes,
        },
    )
```

**Benefits**:
- Reputation always up-to-date
- Supports both global and per-corpus reputation
- Calculated from source of truth (vote records)
- Can be moved to async task (Celery) for scale

## Permission System

### Permission Hierarchy

1. **Superusers**: Full access to everything
2. **Corpus Owners**: All moderation permissions for their corpus
3. **Designated Moderators**: Specific permissions from `CorpusModerator.permissions`
4. **Object Creators**: Can manage their own content (delete own messages, etc.)

### Moderation Permission Check

**Location**: `Conversation.can_moderate()` method (`models.py:261-282`)

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

### Permission Checking for Specific Actions

GraphQL mutations check specific permissions:

```python
def resolve_lock_thread(self, info, conversation_id, reason=None):
    conversation = Conversation.objects.get(id=conversation_id)
    user = info.context.user

    # Check if user can moderate
    if not conversation.can_moderate(user):
        return Error(message="You don't have permission to moderate this thread")

    # Check specific permission for moderators (not owners)
    if conversation.chat_with_corpus:
        if conversation.chat_with_corpus.creator != user:
            moderator = CorpusModerator.objects.get(
                corpus=conversation.chat_with_corpus,
                user=user
            )
            if not moderator.has_permission("lock_threads"):
                return Error(message="You don't have lock permission")

    conversation.lock(user, reason)
    return Success(obj=conversation)
```

### Integration with Django Guardian

OpenContracts uses Django Guardian for object-level permissions. The collaboration system integrates with this:

```python
from guardian.shortcuts import assign_perm

# When thread is created, grant permissions to creator
assign_perm("view_conversation", user, conversation)
assign_perm("change_conversation", user, conversation)
assign_perm("delete_conversation", user, conversation)
```

## Performance Optimizations

### 1. Denormalized Vote Counts

**Problem**: Counting votes on every message display is expensive.

**Solution**: Store `upvote_count` and `downvote_count` on `ChatMessage`.

**Implementation**:
- Counts updated via signals on every vote change
- Recalculated from scratch to avoid drift
- Fast reads (no JOIN or COUNT needed)

### 2. Denormalized Reputation Scores

**Problem**: Calculating reputation from all votes is expensive.

**Solution**: Store reputation in `UserReputation` table.

**Implementation**:
- Updated via signals on vote changes
- Separate global and per-corpus scores
- Can be recalculated from source of truth if needed

### 3. Database Indexes

Strategic indexes for common queries:

```python
# Fast message vote lookups
indexes = [
    models.Index(fields=["message", "vote_type"]),
    models.Index(fields=["creator"]),
]

# Fast moderation action queries
indexes = [
    models.Index(fields=["conversation"]),
    models.Index(fields=["moderator"]),
    models.Index(fields=["action_type"]),
    models.Index(fields=["created_at"]),
]
```

### 4. Prefetching in Queries

GraphQL resolvers use `select_related` and `prefetch_related`:

```python
def resolve_conversations(self, info, **kwargs):
    return (
        Conversation.objects
        .filter(chat_with_corpus=kwargs.get("corpus_id"))
        .select_related("creator", "chat_with_corpus")
        .prefetch_related("chat_messages")
        .visible_to_user(info.context.user)
    )
```

## Database Migrations

The collaboration system was built incrementally through migrations:

1. **0001_initial.py**: Base Conversation and ChatMessage models
2. **0006_messagevote_userreputation_and_more.py**: Added voting system
3. **0007_corpusmoderator_conversation_is_locked_and_more.py**: Added moderation system

All migrations are reversible and maintain data integrity.

## Design Patterns

### 1. Soft Delete Pattern

Allows reversible deletion with audit trail preservation.

### 2. Signal-Based Updates

Automatic consistency without tight coupling between components.

### 3. Denormalization for Performance

Trade storage for read performance on frequently accessed data.

### 4. Granular Permissions

Flexible permission system supporting different moderator roles.

### 5. Audit Trail

Immutable ModerationAction records for compliance and transparency.

## Future Considerations

### Async Task Processing

Current signal handlers are synchronous. For scale, consider:

```python
from celery import shared_task

@shared_task
def update_reputation_async(user_id, corpus_id=None):
    user = User.objects.get(id=user_id)
    corpus = Corpus.objects.get(id=corpus_id) if corpus_id else None
    update_user_reputation(user, corpus)

# In signal handler
@receiver(post_save, sender=MessageVote)
def update_reputation_on_vote_change(sender, instance, **kwargs):
    update_reputation_async.delay(
        instance.message.creator.id,
        instance.message.conversation.chat_with_corpus_id
    )
```

### Caching

High-traffic discussions could benefit from caching:

```python
from django.core.cache import cache

def get_conversation_with_cache(conversation_id):
    cache_key = f"conversation:{conversation_id}"
    conversation = cache.get(cache_key)
    if not conversation:
        conversation = Conversation.objects.get(id=conversation_id)
        cache.set(cache_key, conversation, timeout=300)  # 5 minutes
    return conversation
```

### Real-time Updates

WebSocket consumers exist for agent chats and could be extended for thread notifications:

```python
# In consumer
async def thread_message_created(self, event):
    await self.send_json({
        "type": "thread_message_created",
        "message": event["message"],
    })
```

## Engagement Metrics System (Epic #565)

### Overview

The engagement metrics system provides aggregated statistics about corpus participation, enabling dashboards, leaderboards, and analytics. Metrics are calculated asynchronously via Celery tasks to avoid performance impact on user operations.

### Database Model

#### CorpusEngagementMetrics

**Purpose**: Stores denormalized engagement metrics per corpus for fast dashboard queries.

**Location**: `opencontractserver/corpuses/models.py:600-676`

**Key Fields**:

```python
class CorpusEngagementMetrics(models.Model):
    corpus = models.OneToOneField(Corpus, related_name="engagement_metrics")

    # Thread counts
    total_threads = models.IntegerField(default=0)
    active_threads = models.IntegerField(default=0)

    # Message counts
    total_messages = models.IntegerField(default=0)
    messages_last_7_days = models.IntegerField(default=0)
    messages_last_30_days = models.IntegerField(default=0)

    # Contributor counts
    unique_contributors = models.IntegerField(default=0)
    active_contributors_30_days = models.IntegerField(default=0)

    # Engagement metrics
    total_upvotes = models.IntegerField(default=0)
    avg_messages_per_thread = models.FloatField(default=0.0)

    # Metadata
    last_updated = models.DateTimeField(auto_now=True)
```

**Design Rationale**:
- **Denormalized**: Metrics are pre-calculated and stored to avoid expensive real-time aggregations
- **OneToOne Relationship**: Each corpus has exactly one metrics record
- **No Permissions Mixin**: Metrics are read-only and permissions are checked on the parent Corpus
- **Auto-Updated Timestamp**: Tracks when metrics were last calculated

### Celery Tasks

#### update_corpus_engagement_metrics

**Purpose**: Calculate and update metrics for a specific corpus.

**Location**: `opencontractserver/tasks/corpus_tasks.py:240-362`

**Signature**:
```python
@shared_task
def update_corpus_engagement_metrics(corpus_id: int | str) -> dict
```

**What It Does**:
1. Counts total and active (non-locked, non-deleted) threads
2. Counts total messages and messages in last 7/30 days
3. Counts unique contributors (all-time and 30-day active)
4. Counts total upvotes across all corpus messages
5. Calculates average messages per thread
6. Updates or creates CorpusEngagementMetrics record

**Performance**:
- Filters exclude soft-deleted conversations and messages
- Single-pass aggregations using Django ORM
- Target execution time: <200ms per corpus

**Error Handling**:
- Returns detailed error logs if corpus not found
- Transactions ensure atomic updates
- Safe to run multiple times (idempotent)

#### update_all_corpus_engagement_metrics

**Purpose**: Batch update metrics for all corpuses.

**Location**: `opencontractserver/tasks/corpus_tasks.py:365-397`

**Signature**:
```python
@shared_task
def update_all_corpus_engagement_metrics() -> dict
```

**What It Does**:
1. Gets all corpus IDs
2. Queues individual `update_corpus_engagement_metrics` task for each
3. Returns summary of queued updates

**Usage**:
```python
# Manual trigger (Django shell or admin)
from opencontractserver.tasks.corpus_tasks import update_all_corpus_engagement_metrics
update_all_corpus_engagement_metrics.delay()

# Scheduled execution (celerybeat)
# Add to CELERY_BEAT_SCHEDULE in settings
app.conf.beat_schedule = {
    'update-engagement-metrics-hourly': {
        'task': 'opencontractserver.tasks.corpus_tasks.update_all_corpus_engagement_metrics',
        'schedule': crontab(minute=0),  # Every hour
    },
}
```

### GraphQL Integration

#### Type Definitions

**CorpusEngagementMetricsType**: GraphQL type for engagement metrics

**Location**: `config/graphql/graphene_types.py:1083-1134`

```graphql
type CorpusEngagementMetricsType {
    totalThreads: Int
    activeThreads: Int
    totalMessages: Int
    messagesLast7Days: Int
    messagesLast30Days: Int
    uniqueContributors: Int
    activeContributors30Days: Int
    totalUpvotes: Int
    avgMessagesPerThread: Float
    lastUpdated: DateTime
}
```

#### Corpus Field

Added to `CorpusType`:

```graphql
type Corpus {
    # ... existing fields ...
    engagementMetrics: CorpusEngagementMetricsType
}
```

**Resolver**: Returns `None` if metrics haven't been calculated yet (graceful degradation).

#### User Reputation Fields

Added to `UserType`:

```graphql
type User {
    # ... existing fields ...
    reputationGlobal: Int
    reputationForCorpus(corpusId: ID!): Int
}
```

**Resolvers**:
- `reputationGlobal`: Returns user's global reputation (corpus=null)
- `reputationForCorpus`: Returns user's reputation for a specific corpus
- Both return 0 if no reputation record exists

#### Leaderboard Queries

**Location**: `config/graphql/queries.py:1834-1907`

```graphql
type Query {
    corpusLeaderboard(corpusId: ID!, limit: Int = 10): [UserType!]!
    globalLeaderboard(limit: Int = 10): [UserType!]!
}
```

**corpusLeaderboard**:
- Returns top contributors for a corpus by reputation score
- Requires read access to the corpus
- Ordered by reputation descending
- Default limit: 10 users

**globalLeaderboard**:
- Returns top contributors globally by reputation score
- Ordered by reputation descending
- Default limit: 10 users

**Example Queries**:

```graphql
# Get corpus engagement metrics
query GetCorpusMetrics($corpusId: ID!) {
    corpus(id: $corpusId) {
        title
        engagementMetrics {
            totalThreads
            totalMessages
            uniqueContributors
            avgMessagesPerThread
            lastUpdated
        }
    }
}

# Get corpus leaderboard
query GetLeaderboard($corpusId: ID!) {
    corpusLeaderboard(corpusId: $corpusId, limit: 5) {
        username
        reputationForCorpus(corpusId: $corpusId)
    }
}

# Get global leaderboard
query GetGlobalLeaders {
    globalLeaderboard(limit: 10) {
        username
        reputationGlobal
    }
}
```

### Testing

**Test Coverage**:
- **Model tests**: `opencontractserver/tests/test_corpus_engagement_metrics.py` (9 tests)
- **Task tests**: `opencontractserver/tests/test_engagement_metrics_tasks.py` (13 tests)
- **GraphQL tests**: `opencontractserver/tests/test_engagement_metrics_graphql.py` (9 tests)

**Total**: 31 tests covering model creation, metrics calculation, task execution, GraphQL queries, and permission checks.
