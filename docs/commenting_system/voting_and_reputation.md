# Voting & Reputation System

## Overview

The voting and reputation system enables community-driven content curation by allowing users to vote on messages and earn reputation based on the votes their contributions receive. The system tracks reputation both globally and per-corpus.

## Core Concepts

### Voting

- **Upvote**: Positive vote indicating valuable content
- **Downvote**: Negative vote indicating low-quality content
- **One vote per user per message**: Users can only vote once on each message
- **Vote changes allowed**: Users can change their vote (upvote → downvote or vice versa)
- **No self-voting**: Users cannot vote on their own messages

### Reputation

- **Global Reputation**: User's reputation across all corpuses
- **Per-Corpus Reputation**: User's reputation within a specific corpus
- **Calculation**: `upvotes_received - downvotes_received`
- **Automatic Updates**: Recalculated when votes change

## Database Models

### MessageVote

**Purpose**: Tracks individual votes on messages.

**Location**: `opencontractserver/conversations/models.py:634-685`

**Schema**:

```python
class MessageVote(BaseOCModel):
    message = models.ForeignKey(
        ChatMessage,
        related_name="votes",
        on_delete=models.CASCADE
    )
    vote_type = models.CharField(
        max_length=10,
        choices=VoteType.choices  # "upvote" or "downvote"
    )
    creator = models.ForeignKey(
        User,
        related_name="message_votes",
        on_delete=models.CASCADE
    )

    class Meta:
        unique_together = [("message", "creator")]
        indexes = [
            models.Index(fields=["message", "vote_type"]),
            models.Index(fields=["creator"]),
        ]
```

**Key Features**:

1. **Unique Constraint**: `(message, creator)` ensures one vote per user per message
2. **Indexed for Performance**: Fast lookups for vote counts and user vote history
3. **Cascade Delete**: Votes deleted when message or user is deleted

### UserReputation

**Purpose**: Caches reputation scores for fast access.

**Location**: `opencontractserver/conversations/models.py:703-777`

**Schema**:

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
        related_name="user_reputations",
        on_delete=models.CASCADE
    )

    # Computed scores
    reputation_score = models.IntegerField(default=0)
    total_upvotes_received = models.IntegerField(default=0)
    total_downvotes_received = models.IntegerField(default=0)

    # Calculation tracking
    last_calculated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("user", "corpus")]
        indexes = [
            models.Index(fields=["user"]),
            models.Index(fields=["corpus"]),
            models.Index(fields=["reputation_score"]),
        ]
```

**Key Features**:

1. **Global vs Corpus**: `corpus=NULL` for global reputation
2. **Denormalized**: Stores computed values for performance
3. **Unique Constraint**: One reputation record per user per corpus
4. **Indexed**: Fast sorting and filtering by reputation score

## Voting Workflow

### 1. User Votes on Message

**GraphQL Mutation**:

```graphql
mutation {
  voteMessage(
    messageId: "Q2hhdE1lc3NhZ2VUeXBlOjEwMA=="
    voteType: "upvote"
  ) {
    ok
    message
    obj {
      id
      upvoteCount
      downvoteCount
    }
  }
}
```

**Implementation** (`config/graphql/voting_mutations.py:27-122`):

```python
@staticmethod
@graphql_ratelimit(rate=RateLimits.VOTE)
def mutate(root, info, message_id, vote_type):
    user = info.context.user
    message = ChatMessage.objects.get(id=message_id)

    # Prevent self-voting
    if message.creator == user:
        return VoteMessageMutation(
            ok=False,
            message="Cannot vote on your own message"
        )

    # Create or update vote
    vote, created = MessageVote.objects.update_or_create(
        message=message,
        creator=user,
        defaults={"vote_type": vote_type}
    )

    # Vote counts updated automatically via signals
    # Reputation updated automatically via signals

    return VoteMessageMutation(
        ok=True,
        message="Vote recorded",
        obj=message
    )
```

### 2. Vote Count Update (Automatic)

**Triggered by**: Django signal on MessageVote save/delete

**Signal Handler** (`opencontractserver/conversations/signals.py:18-24`):

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

**Recalculation Logic** (`signals.py:27-50`):

```python
def recalculate_message_vote_counts(message):
    """Recalculate vote counts from scratch to avoid drift"""

    vote_counts = message.votes.aggregate(
        upvotes=Count("id", filter=Q(vote_type=VoteType.UPVOTE)),
        downvotes=Count("id", filter=Q(vote_type=VoteType.DOWNVOTE)),
    )

    message.upvote_count = vote_counts["upvotes"] or 0
    message.downvote_count = vote_counts["downvotes"] or 0
    message.save(update_fields=["upvote_count", "downvote_count"])
```

**Why Recalculate from Scratch?**

- Prevents drift from incremental updates
- Handles vote changes correctly (upvote → downvote)
- Self-correcting if counts get out of sync
- Small performance cost (only touches one message)

### 3. Reputation Update (Automatic)

**Triggered by**: Django signal on MessageVote save/delete

**Signal Handler** (`signals.py:53-67`):

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
        update_user_reputation(
            message_author,
            corpus=conversation.chat_with_corpus
        )
```

**Reputation Calculation** (`signals.py:86-132`):

```python
def update_user_reputation(user, corpus=None):
    """Calculate and update user reputation"""

    # Get all messages by user in scope
    messages_query = ChatMessage.objects.filter(creator=user)

    if corpus:
        # Corpus-specific: only messages in this corpus
        messages_query = messages_query.filter(
            conversation__chat_with_corpus=corpus
        )

    # Aggregate vote counts across all user's messages
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

**Dual Reputation Tracking**:

When a vote is cast on a corpus message:
1. **Global reputation** is updated (all messages across all corpuses)
2. **Corpus reputation** is updated (only messages in that corpus)

Example:
- User A posts in Corpus X → gets upvoted
  - Global reputation: +1
  - Corpus X reputation: +1
- User A posts in Corpus Y → gets upvoted
  - Global reputation: +2
  - Corpus Y reputation: +1
  - Corpus X reputation: still +1

## Voting Business Rules

### 1. Self-Voting Prevention

**Rule**: Users cannot vote on their own messages.

**Implementation** (`voting_mutations.py:72-76`):

```python
if message.creator == user:
    return VoteMessageMutation(
        ok=False,
        message="Cannot vote on your own message"
    )
```

**Rationale**: Prevents reputation manipulation.

### 2. Vote Changes Allowed

**Rule**: Users can change their vote from upvote to downvote (or vice versa).

**Implementation**:

```python
vote, created = MessageVote.objects.update_or_create(
    message=message,
    creator=user,
    defaults={"vote_type": vote_type}
)
```

**Behavior**:
- First vote on message X: Creates new MessageVote
- Second vote on message X (different type): Updates existing MessageVote
- Second vote on message X (same type): No-op, but returns success

**Example**:

```python
# User upvotes
vote_message(message_id=100, vote_type="upvote")
# Message: upvote_count=1, downvote_count=0

# User changes to downvote
vote_message(message_id=100, vote_type="downvote")
# Message: upvote_count=0, downvote_count=1
```

### 3. Vote Removal

**Rule**: Users can remove their vote entirely.

**GraphQL Mutation**:

```graphql
mutation {
  removeVote(messageId: "Q2hhdE1lc3NhZ2VUeXBlOjEwMA==") {
    ok
    message
    obj {
      upvoteCount
      downvoteCount
    }
  }
}
```

**Implementation** (`voting_mutations.py:125-187`):

```python
@staticmethod
@graphql_ratelimit(rate=RateLimits.VOTE)
def mutate(root, info, message_id):
    user = info.context.user
    message = ChatMessage.objects.get(id=message_id)

    try:
        vote = MessageVote.objects.get(message=message, creator=user)
        vote.delete()  # Triggers signal to update counts

        return RemoveVoteMutation(
            ok=True,
            message="Vote removed",
            obj=message
        )
    except MessageVote.DoesNotExist:
        return RemoveVoteMutation(
            ok=False,
            message="No vote to remove"
        )
```

### 4. Rate Limiting

**Rule**: Users limited to 60 votes per minute.

**Rationale**: Prevents vote brigading and manipulation.

**Implementation**: Applied via `@graphql_ratelimit(rate=RateLimits.VOTE)` decorator.

## Reputation Display

### Query User Reputation

**GraphQL Query**:

```graphql
query GetUserReputation($userId: ID!, $corpusId: ID) {
  userReputation(userId: $userId, corpusId: $corpusId) {
    reputationScore
    totalUpvotesReceived
    totalDownvotesReceived
    lastCalculatedAt
  }
}
```

**Global Reputation** (across all corpuses):

```graphql
query {
  userReputation(userId: "VXNlclR5cGU6NQ==") {
    reputationScore
  }
}
```

**Corpus-Specific Reputation**:

```graphql
query {
  userReputation(
    userId: "VXNlclR5cGU6NQ=="
    corpusId: "Q29ycHVzVHlwZTox"
  ) {
    reputationScore
  }
}
```

### Leaderboards

**Query Top Contributors** (planned, not yet implemented):

```graphql
query {
  topContributors(corpusId: "Q29ycHVzVHlwZTox", limit: 10) {
    user {
      id
      username
    }
    reputationScore
    totalUpvotesReceived
  }
}
```

**Implementation** (would query UserReputation):

```python
def resolve_top_contributors(self, info, corpus_id=None, limit=10):
    query = UserReputation.objects.filter(corpus_id=corpus_id)
    return query.order_by("-reputation_score")[:limit]
```

## Performance Optimizations

### 1. Denormalized Vote Counts

**Problem**: Counting votes on every message display is expensive.

```python
# Expensive query (avoid this)
message.votes.filter(vote_type="upvote").count()
```

**Solution**: Store counts on ChatMessage.

```python
# Fast query
message.upvote_count  # Already computed
```

**Benefits**:
- No JOIN needed
- No COUNT aggregation
- Simple integer field access
- Scales to millions of messages

**Trade-off**:
- Extra storage (8 bytes per message)
- Must keep in sync (handled by signals)

### 2. Denormalized Reputation Scores

**Problem**: Calculating reputation from all votes is expensive.

```python
# Expensive query (avoid this)
user_votes = MessageVote.objects.filter(
    message__creator=user
).aggregate(
    upvotes=Count("id", filter=Q(vote_type="upvote")),
    downvotes=Count("id", filter=Q(vote_type="downvote")),
)
reputation = upvotes - downvotes
```

**Solution**: Store in UserReputation table.

```python
# Fast query
UserReputation.objects.get(user=user, corpus=None).reputation_score
```

**Benefits**:
- Fast lookups for user profiles
- Fast sorting for leaderboards
- Efficient filtering (e.g., "users with reputation > 100")

### 3. Strategic Indexing

**MessageVote Indexes**:

```python
indexes = [
    models.Index(fields=["message", "vote_type"]),  # Count votes by type
    models.Index(fields=["creator"]),               # User vote history
]
```

**UserReputation Indexes**:

```python
indexes = [
    models.Index(fields=["user"]),              # User lookup
    models.Index(fields=["corpus"]),            # Corpus leaderboard
    models.Index(fields=["reputation_score"]),  # Sorting by score
]
```

### 4. Signal-Based Updates

**Benefits**:
- Automatic consistency (no manual updates needed)
- Decoupled from mutation logic
- Centralized update logic

**Potential Optimization**: Move to Celery tasks for high-traffic sites.

```python
# Current: Synchronous
@receiver(post_save, sender=MessageVote)
def update_reputation_on_vote_change(sender, instance, **kwargs):
    update_user_reputation(instance.message.creator)

# Future: Asynchronous
@receiver(post_save, sender=MessageVote)
def update_reputation_on_vote_change(sender, instance, **kwargs):
    update_user_reputation_async.delay(instance.message.creator.id)
```

## Reputation Use Cases

### 1. User Profiles

Display user's contribution metrics:

```python
# Global stats
global_rep = UserReputation.objects.get(user=user, corpus=None)
print(f"Global reputation: {global_rep.reputation_score}")
print(f"Total upvotes: {global_rep.total_upvotes_received}")
print(f"Total downvotes: {global_rep.total_downvotes_received}")

# Per-corpus stats
corpus_reps = UserReputation.objects.filter(
    user=user
).exclude(corpus=None).order_by("-reputation_score")

for rep in corpus_reps:
    print(f"{rep.corpus.title}: {rep.reputation_score}")
```

### 2. Leaderboards

Rank users by contribution quality:

```python
# Global leaderboard
top_users = UserReputation.objects.filter(
    corpus=None
).order_by("-reputation_score")[:10]

# Corpus leaderboard
top_contributors = UserReputation.objects.filter(
    corpus=my_corpus
).order_by("-reputation_score")[:10]
```

### 3. Badge Awards (Integration Point)

Automatically award badges for reputation milestones:

```python
# Pseudo-code for badge system integration
if global_rep.reputation_score >= 100:
    award_badge(user, badge="Helpful Contributor")

if global_rep.reputation_score >= 1000:
    award_badge(user, badge="Expert Contributor")
```

### 4. Moderation Privileges

Grant moderation powers based on reputation:

```python
# Example: Auto-moderator for high reputation
if corpus_rep.reputation_score >= 500:
    CorpusModerator.objects.get_or_create(
        corpus=corpus,
        user=user,
        defaults={
            "permissions": ["delete_messages"],
            "assigned_by": corpus.creator
        }
    )
```

### 5. Content Sorting

Display best content first:

```python
# Sort messages by vote score
messages = (
    ChatMessage.objects
    .filter(conversation=thread)
    .annotate(vote_score=F("upvote_count") - F("downvote_count"))
    .order_by("-vote_score")
)
```

## Edge Cases & Considerations

### 1. Deleted Messages

**Question**: What happens to reputation when a message is deleted?

**Current Behavior**:
- Soft-deleted messages still exist in database
- Votes on deleted messages still count toward reputation
- This is intentional (prevents gaming by delete/recreate)

**Alternative** (not implemented):
```python
# Could exclude deleted messages from reputation
messages_query = ChatMessage.objects.filter(
    creator=user,
    deleted_at__isnull=True  # Only count non-deleted
)
```

### 2. Deleted Users

**Question**: What happens to votes when a user is deleted?

**Current Behavior**:
- CASCADE delete removes MessageVote records
- Signals trigger reputation recalculation
- Message vote counts updated automatically

### 3. Negative Reputation

**Question**: Can reputation go negative?

**Answer**: Yes, if downvotes exceed upvotes.

**Handling**:
```python
# Reputation can be negative
if reputation_score < 0:
    # Could restrict permissions
    # Could hide posts
    # Could require moderation
    pass
```

### 4. Vote Spam Detection

**Current Protection**:
- Rate limiting (60 votes/minute)
- No self-voting

**Future Enhancements**:
- Detect vote brigading (multiple users voting same way quickly)
- Throttle voting on very old content
- Require minimum reputation to vote

### 5. Reputation Decay

**Current**: Reputation is cumulative (never decreases except via downvotes)

**Future Enhancement**: Time-based decay

```python
# Pseudo-code for reputation decay
recent_messages = messages_query.filter(
    created__gte=timezone.now() - timedelta(days=90)
)
# Weight recent contributions higher
```

## Testing

The voting system has comprehensive test coverage.

**Test Files**:
- `opencontractserver/tests/test_voting.py` - Model and signal tests
- `opencontractserver/tests/test_voting_mutations_graphql.py` - GraphQL mutation tests

**Key Test Cases**:

1. **Vote Creation**:
   - User can upvote message
   - User can downvote message
   - Vote counts update correctly

2. **Vote Changes**:
   - User can change upvote to downvote
   - Vote counts recalculate correctly

3. **Vote Removal**:
   - User can remove their vote
   - Counts update correctly

4. **Self-Voting**:
   - User cannot vote on own message
   - Returns appropriate error

5. **Reputation Calculation**:
   - Global reputation calculates correctly
   - Per-corpus reputation calculates correctly
   - Updates on vote changes

6. **Rate Limiting**:
   - Enforced at 60 votes/minute
   - Returns rate limit error

7. **Permissions**:
   - User must have corpus access to vote
   - Respects object-level permissions

Run tests:

```bash
# Backend tests
docker compose -f test.yml run django python manage.py test \
    opencontractserver.tests.test_voting \
    opencontractserver.tests.test_voting_mutations_graphql
```

## Future Enhancements

### 1. Weighted Voting

Give more weight to votes from high-reputation users:

```python
vote_value = 1 + (voter_reputation / 1000)
```

### 2. Vote Reasons

Allow users to explain their vote:

```python
class MessageVote(BaseOCModel):
    # ...existing fields...
    reason = models.TextField(null=True, blank=True)
```

### 3. Vote Analytics

Track voting patterns for insights:

```python
# Most controversial messages (high upvotes AND downvotes)
controversial = ChatMessage.objects.filter(
    upvote_count__gte=10,
    downvote_count__gte=10
)
```

### 4. Reputation History

Track reputation changes over time:

```python
class ReputationHistory(BaseOCModel):
    user = models.ForeignKey(User)
    corpus = models.ForeignKey(Corpus, null=True)
    reputation_score = models.IntegerField()
    recorded_at = models.DateTimeField(auto_now_add=True)
```

### 5. Badges Integration

Automatically award badges for:
- First upvote received
- 100 reputation milestone
- 1000 reputation milestone
- Most upvoted message in corpus
- Consistent positive contributions
