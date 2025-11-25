# GraphQL API Reference

## Overview

The collaboration system exposes a comprehensive GraphQL API for creating and managing discussion threads, voting on messages, and moderating content. All mutations include rate limiting and permission checks.

## GraphQL Type Definitions

### Enums

**Location**: `config/graphql/graphene_types.py`

#### ConversationTypeEnum

```graphql
enum ConversationTypeEnum {
  CHAT        # Agent-based conversation
  THREAD      # Discussion thread
}
```

#### AgentTypeEnum

```graphql
enum AgentTypeEnum {
  DOCUMENT_AGENT  # Document analysis agent
  CORPUS_AGENT    # Corpus-wide analysis agent
}
```

#### MessageStateChoices

```graphql
enum MessageStateChoices {
  IN_PROGRESS        # Message being generated
  COMPLETED          # Message complete
  CANCELLED          # Generation cancelled
  ERROR              # Error occurred
  AWAITING_APPROVAL  # Requires user approval
}
```

#### VoteType

```graphql
enum VoteType {
  UPVOTE    # Positive vote
  DOWNVOTE  # Negative vote
}
```

#### ModerationActionType

```graphql
enum ModerationActionType {
  LOCK_THREAD
  UNLOCK_THREAD
  PIN_THREAD
  UNPIN_THREAD
  DELETE_MESSAGE
  DELETE_THREAD
  RESTORE_MESSAGE
  RESTORE_THREAD
}
```

### Object Types

#### ConversationType

**Location**: `config/graphql/graphene_types.py:1415-1444`

```graphql
type ConversationType {
  id: ID!
  conversationType: ConversationTypeEnum!
  title: String
  description: String
  creator: UserType!
  chatWithCorpus: CorpusType
  chatWithDocument: DocumentType

  # Moderation
  isLocked: Boolean!
  lockedBy: UserType
  lockedAt: DateTime
  isPinned: Boolean!
  pinnedBy: UserType
  pinnedAt: DateTime

  # Messages
  allMessages: [MessageType!]!

  # Timestamps
  created: DateTime!
  modified: DateTime!
  deletedAt: DateTime
}
```

#### MessageType

**Location**: `config/graphql/graphene_types.py:1396-1412`

```graphql
type MessageType {
  id: ID!
  conversation: ConversationType!
  msgType: String!
  agentType: AgentTypeEnum
  content: String!
  data: JSONScalar
  state: MessageStateChoices!

  # Threading
  parentMessage: MessageType
  replies: [MessageType!]!

  # Voting
  upvoteCount: Int!
  downvoteCount: Int!

  # Metadata
  creator: UserType!
  created: DateTime!
  modified: DateTime!
  deletedAt: DateTime
}
```

#### MessageVoteType

```graphql
type MessageVoteType {
  id: ID!
  message: MessageType!
  voteType: VoteType!
  creator: UserType!
  created: DateTime!
}
```

#### UserReputationType

```graphql
type UserReputationType {
  id: ID!
  user: UserType!
  corpus: CorpusType
  reputationScore: Int!
  totalUpvotesReceived: Int!
  totalDownvotesReceived: Int!
  lastCalculatedAt: DateTime!
}
```

#### CorpusModeratorType

```graphql
type CorpusModeratorType {
  id: ID!
  corpus: CorpusType!
  user: UserType!
  permissions: [String!]!
  assignedBy: UserType!
  created: DateTime!
}
```

#### ModerationActionType

```graphql
type ModerationActionType {
  id: ID!
  conversation: ConversationType
  message: MessageType
  actionType: ModerationActionType!
  moderator: UserType!
  reason: String
  createdAt: DateTime!
}
```

## Queries

**Location**: `config/graphql/queries.py`

### conversations

**Query conversations by corpus or document**

```graphql
query GetConversations(
  $corpusId: ID
  $documentId: ID
  $conversationType: ConversationTypeEnum
) {
  conversations(
    corpusId: $corpusId
    documentId: $documentId
    conversationType: $conversationType
  ) {
    id
    title
    description
    conversationType
    isLocked
    isPinned
    creator {
      id
      username
    }
    allMessages {
      id
      content
      upvoteCount
      downvoteCount
    }
  }
}
```

**Implementation** (`queries.py:1217-1243`):
- Filters by document_id or corpus_id
- Uses ConversationFilter for flexible filtering
- Prefetches chat_messages for performance
- Respects user permissions via `visible_to_user()`

### userReputation

**Query user reputation (global or per-corpus)**

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

### corpusModerators

**Query moderators for a corpus**

```graphql
query GetCorpusModerators($corpusId: ID!) {
  corpusModerators(corpusId: $corpusId) {
    id
    user {
      id
      username
    }
    permissions
    assignedBy {
      id
      username
    }
  }
}
```

### moderationActions

**Query moderation action audit log**

```graphql
query GetModerationActions(
  $conversationId: ID
  $moderatorId: ID
  $actionType: ModerationActionType
) {
  moderationActions(
    conversationId: $conversationId
    moderatorId: $moderatorId
    actionType: $actionType
  ) {
    id
    actionType
    moderator {
      username
    }
    reason
    createdAt
  }
}
```

## Mutations

### Thread Management Mutations

**Location**: `config/graphql/conversation_mutations.py`

#### createThread

**Create a new discussion thread**

**Rate Limit**: 10 per hour

```graphql
mutation CreateThread(
  $corpusId: ID!
  $title: String!
  $description: String
  $initialMessage: String!
) {
  createThread(
    corpusId: $corpusId
    title: $title
    description: $description
    initialMessage: $initialMessage
  ) {
    ok
    message
    obj {
      id
      title
      description
      allMessages {
        id
        content
      }
    }
  }
}
```

**Implementation** (`conversation_mutations.py:32-101`):
1. Validates corpus exists and user has access
2. Creates Conversation with type="thread"
3. Creates initial ChatMessage
4. Assigns permissions to creator
5. Returns created thread

**Example**:

```python
# GraphQL variables
{
  "corpusId": "Q29ycHVzVHlwZTox",
  "title": "Best practices for contract review",
  "description": "Let's discuss best practices for reviewing employment contracts",
  "initialMessage": "What are the key clauses to look for in employment contracts?"
}
```

#### createThreadMessage

**Post a new message to a thread**

**Rate Limit**: 30 per minute

```graphql
mutation CreateThreadMessage(
  $conversationId: ID!
  $content: String!
) {
  createThreadMessage(
    conversationId: $conversationId
    content: $content
  ) {
    ok
    message
    obj {
      id
      content
      creator {
        username
      }
      created
    }
  }
}
```

**Implementation** (`conversation_mutations.py:104-168`):
1. Validates conversation exists
2. Checks if thread is locked
3. Creates ChatMessage
4. Returns created message

**Errors**:
- Thread is locked
- User doesn't have access to corpus
- Conversation not found

#### replyToMessage

**Create a nested reply to a message**

**Rate Limit**: 30 per minute

```graphql
mutation ReplyToMessage(
  $parentMessageId: ID!
  $content: String!
) {
  replyToMessage(
    parentMessageId: $parentMessageId
    content: $content
  ) {
    ok
    message
    obj {
      id
      content
      parentMessage {
        id
        content
      }
    }
  }
}
```

**Implementation** (`conversation_mutations.py:171-237`):
1. Validates parent message exists
2. Checks if thread is locked
3. Creates ChatMessage with parent_message reference
4. Returns created reply

#### deleteConversation

**Soft delete a conversation**

**Rate Limit**: 20 per minute (via moderation rate limit)

```graphql
mutation DeleteConversation($conversationId: ID!) {
  deleteConversation(conversationId: $conversationId) {
    ok
    message
  }
}
```

**Implementation** (`conversation_mutations.py:240-287`):
1. Validates conversation exists
2. Checks user is creator OR has moderation permission
3. Calls `conversation.soft_delete_thread(user)`
4. Creates ModerationAction record

**Permissions**:
- Conversation creator can always delete
- Moderators with "delete_threads" permission can delete
- Corpus owners can delete

#### deleteMessage

**Soft delete a message**

**Rate Limit**: 20 per minute (via moderation rate limit)

```graphql
mutation DeleteMessage($messageId: ID!) {
  deleteMessage(messageId: $messageId) {
    ok
    message
  }
}
```

**Implementation** (`conversation_mutations.py:290-338`):
1. Validates message exists
2. Checks user is creator OR has moderation permission
3. Calls `message.soft_delete_message(user)`
4. Creates ModerationAction record

### Voting Mutations

**Location**: `config/graphql/voting_mutations.py`

#### voteMessage

**Upvote or downvote a message**

**Rate Limit**: 60 per minute

```graphql
mutation VoteMessage(
  $messageId: ID!
  $voteType: String!  # "upvote" or "downvote"
) {
  voteMessage(
    messageId: $messageId
    voteType: $voteType
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

**Implementation** (`voting_mutations.py:27-122`):
1. Validates message exists
2. Prevents self-voting
3. Creates or updates MessageVote
4. Signal automatically updates vote counts
5. Signal automatically updates reputation
6. Returns updated message

**Business Logic**:
- User can change their vote (upvote → downvote or vice versa)
- Voting on same type is idempotent (no error)
- Cannot vote on own messages

**Example**:

```python
# Upvote a message
{
  "messageId": "Q2hhdE1lc3NhZ2VUeXBlOjEwMA==",
  "voteType": "upvote"
}

# Change to downvote
{
  "messageId": "Q2hhdE1lc3NhZ2VUeXBlOjEwMA==",
  "voteType": "downvote"
}
```

#### removeVote

**Remove your vote from a message**

**Rate Limit**: 60 per minute

```graphql
mutation RemoveVote($messageId: ID!) {
  removeVote(messageId: $messageId) {
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

**Implementation** (`voting_mutations.py:125-187`):
1. Validates message exists
2. Finds user's vote
3. Deletes MessageVote
4. Signal automatically updates vote counts
5. Signal automatically updates reputation
6. Returns updated message

### Moderation Mutations

**Location**: `config/graphql/moderation_mutations.py`

All moderation mutations check permissions and create ModerationAction audit records.

#### lockThread

**Lock a thread to prevent new messages**

**Rate Limit**: 20 per minute

```graphql
mutation LockThread(
  $conversationId: ID!
  $reason: String
) {
  lockThread(
    conversationId: $conversationId
    reason: $reason
  ) {
    ok
    message
    obj {
      id
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
1. Validates conversation exists
2. Checks user can moderate
3. Checks specific "lock_threads" permission for moderators
4. Calls `conversation.lock(user, reason)`
5. Creates ModerationAction record
6. Returns updated conversation

**Permissions**:
- Corpus owners can always lock
- Moderators must have "lock_threads" permission

#### unlockThread

**Unlock a locked thread**

**Rate Limit**: 20 per minute

```graphql
mutation UnlockThread(
  $conversationId: ID!
  $reason: String
) {
  unlockThread(
    conversationId: $conversationId
    reason: $reason
  ) {
    ok
    message
    obj {
      id
      isLocked
    }
  }
}
```

**Implementation**: Similar to lockThread, calls `conversation.unlock(user, reason)`

#### pinThread

**Pin a thread to top of list**

**Rate Limit**: 20 per minute

```graphql
mutation PinThread(
  $conversationId: ID!
  $reason: String
) {
  pinThread(
    conversationId: $conversationId
    reason: $reason
  ) {
    ok
    message
    obj {
      id
      isPinned
      pinnedBy {
        username
      }
      pinnedAt
    }
  }
}
```

**Implementation** (`moderation_mutations.py:150-208`):
1. Validates conversation exists
2. Checks user can moderate
3. Checks specific "pin_threads" permission for moderators
4. Calls `conversation.pin(user, reason)`
5. Creates ModerationAction record
6. Returns updated conversation

**Permissions**:
- Corpus owners can always pin
- Moderators must have "pin_threads" permission

#### unpinThread

**Unpin a thread**

**Rate Limit**: 20 per minute

```graphql
mutation UnpinThread(
  $conversationId: ID!
  $reason: String
) {
  unpinThread(
    conversationId: $conversationId
    reason: $reason
  ) {
    ok
    message
    obj {
      id
      isPinned
    }
  }
}
```

**Implementation**: Similar to pinThread, calls `conversation.unpin(user, reason)`

#### addModerator

**Designate a user as a moderator with specific permissions**

**Rate Limit**: 20 per minute

```graphql
mutation AddModerator(
  $corpusId: ID!
  $userId: ID!
  $permissions: [String!]!
) {
  addModerator(
    corpusId: $corpusId
    userId: $userId
    permissions: $permissions
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

**Implementation** (`moderation_mutations.py:272-357`):
1. Validates corpus exists
2. Checks user is corpus owner (only owners can add moderators)
3. Validates permissions against allowed list
4. Creates CorpusModerator record
5. Returns created moderator

**Valid Permissions**:
- `lock_threads`
- `pin_threads`
- `delete_messages`
- `delete_threads`

**Example**:

```python
{
  "corpusId": "Q29ycHVzVHlwZTox",
  "userId": "VXNlclR5cGU6NQ==",
  "permissions": ["lock_threads", "pin_threads"]
}
```

**Permissions**:
- Only corpus owners can add moderators

#### removeModerator

**Remove moderator designation**

**Rate Limit**: 20 per minute

```graphql
mutation RemoveModerator(
  $corpusId: ID!
  $userId: ID!
) {
  removeModerator(
    corpusId: $corpusId
    userId: $userId
  ) {
    ok
    message
  }
}
```

**Implementation** (`moderation_mutations.py:360-422`):
1. Validates corpus exists
2. Checks user is corpus owner
3. Deletes CorpusModerator record
4. Returns success

**Permissions**:
- Only corpus owners can remove moderators

#### updateModeratorPermissions

**Update an existing moderator's permissions**

**Rate Limit**: 20 per minute

```graphql
mutation UpdateModeratorPermissions(
  $corpusId: ID!
  $userId: ID!
  $permissions: [String!]!
) {
  updateModeratorPermissions(
    corpusId: $corpusId
    userId: $userId
    permissions: $permissions
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

**Implementation** (`moderation_mutations.py:425-511`):
1. Validates corpus exists
2. Checks user is corpus owner
3. Validates new permissions
4. Updates CorpusModerator.permissions
5. Returns updated moderator

**Permissions**:
- Only corpus owners can update moderator permissions

## Rate Limiting

**Location**: `config/graphql/ratelimits.py`

### Rate Limit Configuration

The system uses the `@graphql_ratelimit` decorator with predefined rate limits:

```python
class RateLimits:
    READ_LIGHT = "100/m"       # Light read operations
    WRITE_LIGHT = "30/m"       # Light write operations
    WRITE_MEDIUM = "10/m"      # Medium write operations
    MODERATE_ACTION = "20/m"   # Moderation actions
    VOTE = "60/m"              # Voting actions
    THREAD_CREATE = "10/h"     # Thread creation
    MESSAGE_CREATE = "30/m"    # Message creation
```

### Applied Rate Limits

| Mutation | Rate Limit | Reason |
|----------|------------|--------|
| createThread | 10/hour | Prevent thread spam |
| createThreadMessage | 30/minute | Prevent message spam |
| replyToMessage | 30/minute | Prevent reply spam |
| voteMessage | 60/minute | Prevent vote manipulation |
| removeVote | 60/minute | Prevent vote manipulation |
| lockThread | 20/minute | Prevent moderation abuse |
| unlockThread | 20/minute | Prevent moderation abuse |
| pinThread | 20/minute | Prevent moderation abuse |
| unpinThread | 20/minute | Prevent moderation abuse |
| deleteConversation | 20/minute | Prevent moderation abuse |
| deleteMessage | 20/minute | Prevent moderation abuse |
| addModerator | 20/minute | Prevent permission abuse |
| removeModerator | 20/minute | Prevent permission abuse |
| updateModeratorPermissions | 20/minute | Prevent permission abuse |

### Rate Limit Implementation

```python
from config.graphql.ratelimits import graphql_ratelimit, RateLimits

class CreateThreadMutation(graphene.Mutation):
    @staticmethod
    @graphql_ratelimit(rate=RateLimits.THREAD_CREATE)
    def mutate(root, info, **kwargs):
        # Mutation logic
        pass
```

### Rate Limit Errors

When rate limit is exceeded:

```json
{
  "errors": [
    {
      "message": "Rate limit exceeded. Please try again later.",
      "extensions": {
        "code": "RATE_LIMIT_EXCEEDED"
      }
    }
  ]
}
```

## Error Handling

### Common Error Responses

```python
# Success response
{
  "ok": true,
  "message": "Thread created successfully",
  "obj": { /* created object */ }
}

# Error response
{
  "ok": false,
  "message": "You don't have permission to moderate this thread",
  "obj": null
}
```

### Error Types

1. **Permission Errors**:
   - "You don't have permission to moderate this thread"
   - "You don't have lock permission"
   - "Only corpus owners can add moderators"

2. **Validation Errors**:
   - "Thread is locked"
   - "Cannot vote on your own message"
   - "Invalid permissions specified"

3. **Not Found Errors**:
   - "Conversation not found"
   - "Message not found"
   - "User not found"

4. **Rate Limit Errors**:
   - "Rate limit exceeded. Please try again later."

## Schema Integration

**Location**: `config/graphql/mutations.py:3860-3877`

All collaboration mutations are registered in the main schema:

```python
class Mutation(graphene.ObjectType):
    # Thread mutations
    create_thread = CreateThreadMutation.Field()
    create_thread_message = CreateThreadMessageMutation.Field()
    reply_to_message = ReplyToMessageMutation.Field()
    delete_conversation = DeleteConversationMutation.Field()
    delete_message = DeleteMessageMutation.Field()

    # Voting mutations
    vote_message = VoteMessageMutation.Field()
    remove_vote = RemoveVoteMutation.Field()

    # Moderation mutations
    lock_thread = LockThreadMutation.Field()
    unlock_thread = UnlockThreadMutation.Field()
    pin_thread = PinThreadMutation.Field()
    unpin_thread = UnpinThreadMutation.Field()
    add_moderator = AddModeratorMutation.Field()
    remove_moderator = RemoveModeratorMutation.Field()
    update_moderator_permissions = UpdateModeratorPermissionsMutation.Field()
```

## Complete Example Workflow

### 1. Create a Thread

```graphql
mutation {
  createThread(
    corpusId: "Q29ycHVzVHlwZTox"
    title: "Contract Review Best Practices"
    description: "Discussion about reviewing employment contracts"
    initialMessage: "What clauses should we prioritize?"
  ) {
    ok
    message
    obj {
      id
      title
      allMessages {
        id
        content
      }
    }
  }
}
```

### 2. Reply to Initial Message

```graphql
mutation {
  replyToMessage(
    parentMessageId: "Q2hhdE1lc3NhZ2VUeXBlOjEwMA=="
    content: "I always check the non-compete clause first"
  ) {
    ok
    obj {
      id
      content
      parentMessage {
        content
      }
    }
  }
}
```

### 3. Vote on Reply

```graphql
mutation {
  voteMessage(
    messageId: "Q2hhdE1lc3NhZ2VUeXBlOjEwMQ=="
    voteType: "upvote"
  ) {
    ok
    obj {
      id
      upvoteCount
      downvoteCount
    }
  }
}
```

### 4. Pin Important Thread

```graphql
mutation {
  pinThread(
    conversationId: "Q29udmVyc2F0aW9uVHlwZTo1MA=="
    reason: "Important discussion for new users"
  ) {
    ok
    obj {
      id
      isPinned
      pinnedBy {
        username
      }
    }
  }
}
```

### 5. Check User Reputation

```graphql
query {
  userReputation(
    userId: "VXNlclR5cGU6NQ=="
    corpusId: "Q29ycHVzVHlwZTox"
  ) {
    reputationScore
    totalUpvotesReceived
    totalDownvotesReceived
  }
}
```

## Frontend Integration (Planned)

The frontend would typically use Apollo Client or similar:

```typescript
// Example React component (not yet implemented)
import { gql, useMutation } from '@apollo/client';

const CREATE_THREAD = gql`
  mutation CreateThread($corpusId: ID!, $title: String!, $initialMessage: String!) {
    createThread(corpusId: $corpusId, title: $title, initialMessage: $initialMessage) {
      ok
      message
      obj {
        id
        title
      }
    }
  }
`;

function CreateThreadForm({ corpusId }) {
  const [createThread, { loading, error }] = useMutation(CREATE_THREAD);

  const handleSubmit = async (e) => {
    e.preventDefault();
    await createThread({
      variables: {
        corpusId,
        title: e.target.title.value,
        initialMessage: e.target.message.value,
      },
    });
  };

  return <form onSubmit={handleSubmit}>...</form>;
}
```
