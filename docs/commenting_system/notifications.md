# Notification System Documentation

> **Epic**: #562
> **Sub-Issues**: #563 (Model), #564 (GraphQL API)
> **Status**: ✅ Completed

## Overview

The notification system provides real-time alerts to users about important events in the OpenContracts collaboration platform. Users receive notifications for replies, mentions, votes, badges, moderation actions, and thread participation.

## Architecture

### Components

1. **Notification Model** (`opencontractserver/notifications/models.py`)
   - Stores notification records
   - Tracks read/unread status
   - Links to related objects (messages, conversations, actors)

2. **Signal Handlers** (`opencontractserver/notifications/signals.py`)
   - Automatically create notifications in response to events
   - Connected via Django signals (post_save)

3. **GraphQL API** (`config/graphql/notification_mutations.py`, `config/graphql/queries.py`)
   - Queries for retrieving notifications
   - Mutations for managing notifications

4. **Admin Interface** (`opencontractserver/notifications/admin.py`)
   - Django admin for managing notifications

## Notification Types

| Type | Trigger | Recipient | Description |
|------|---------|-----------|-------------|
| `REPLY` | User replies to your message | Message creator | Direct reply notification |
| `THREAD_REPLY` | User posts in thread you're participating in | Thread participants | Participation notification |
| `VOTE` | User votes on your message | Message creator | Vote notification (upvote/downvote) |
| `BADGE` | Badge awarded to you | Badge recipient | Badge award notification |
| `MENTION` | User mentions you with @username | Mentioned user | Mention notification |
| `ACCEPTED` | Your answer is accepted | Answer creator | Accepted answer notification |
| `THREAD_LOCKED` | Thread is locked by moderator | Thread creator | Moderation action |
| `THREAD_UNLOCKED` | Thread is unlocked | Thread creator | Moderation action |
| `THREAD_PINNED` | Thread is pinned | Thread creator | Moderation action |
| `THREAD_UNPINNED` | Thread is unpinned | Thread creator | Moderation action |
| `MESSAGE_DELETED` | Message is deleted by moderator | Message creator | Moderation action |
| `THREAD_DELETED` | Thread is deleted | Thread creator | Moderation action |
| `MESSAGE_RESTORED` | Deleted message is restored | Message creator | Moderation action |
| `THREAD_RESTORED` | Deleted thread is restored | Thread creator | Moderation action |

## Database Schema

### Notification Model

```python
class Notification(models.Model):
    recipient = ForeignKey(User)           # Who receives the notification
    notification_type = CharField()         # Type from NotificationTypeChoices
    message = ForeignKey(ChatMessage)      # Related message (if applicable)
    conversation = ForeignKey(Conversation) # Related thread (if applicable)
    actor = ForeignKey(User)               # Who triggered the notification
    is_read = BooleanField(default=False)  # Read status
    created_at = DateTimeField()           # When created
    modified = DateTimeField()             # Last modified
    data = JSONField()                     # Additional context data
```

### Indexes

- `(recipient, -created_at)` - Fast retrieval of user's notifications
- `(recipient, is_read)` - Unread count queries
- `(notification_type)` - Filter by type
- `(conversation)` - Thread-related notifications
- `(message)` - Message-related notifications

## Signal Handlers

### 1. Reply Notifications

**Signal**: `post_save` on `ChatMessage`
**Handler**: `create_reply_notification()`

Creates two types of notifications:
1. **REPLY**: Direct reply to parent message creator
2. **THREAD_REPLY**: Reply in thread you're participating in

**Logic**:
- Skips if message is not from a human (`msg_type != "human"`)
- Doesn't notify self
- For direct replies: notifies parent message creator
- For thread participation: notifies all users who posted in thread (excluding self and direct parent to avoid duplicates)

### 2. Mention Notifications

**Signal**: `post_save` on `ChatMessage`
**Handler**: `create_mention_notification()`

**Logic**:
- Extracts @username mentions using regex pattern: `(?:^|(?<=\s))@([\w-]+)(?=\s|[.,!?;:]|$)`
- Supports usernames with underscores and hyphens
- Case-insensitive deduplication
- Doesn't notify self

### 3. Badge Notifications

**Signal**: `post_save` on `UserBadge`
**Handler**: `create_badge_notification()`

**Logic**:
- Triggered when badge is awarded
- Includes badge details in `data` field (name, description, icon, color)
- Distinguishes between manual awards (has `awarded_by`) and auto-awards (no `awarded_by`)

### 4. Moderation Notifications

**Signal**: `post_save` on `ModerationAction`
**Handler**: `create_moderation_notification()`

**Logic**:
- Maps `ModerationActionType` to `NotificationTypeChoices`
- Determines recipient based on action (message creator or thread creator)
- Doesn't notify if moderator acts on their own content
- Includes moderation reason in `data` field

## GraphQL API

### Queries

#### `notifications`

Get user's notifications (paginated and filterable).

```graphql
query {
  notifications(
    first: 20
    after: "cursor"
    isRead: false
    notificationType: "REPLY"
  ) {
    edges {
      node {
        id
        notificationType
        isRead
        createdAt
        actor {
          username
        }
        message {
          content
        }
        conversation {
          title
        }
        data
      }
    }
    pageInfo {
      hasNextPage
      endCursor
    }
  }
}
```

**Features**:
- Automatic filtering to current user's notifications
- Pagination support (Relay-style)
- Filter by `is_read` and `notification_type`
- Ordered by `-created_at` (newest first)

#### `unreadNotificationCount`

Get count of unread notifications.

```graphql
query {
  unreadNotificationCount
}
```

### Mutations

#### `markNotificationRead`

Mark a single notification as read.

```graphql
mutation {
  markNotificationRead(notificationId: "Tm90aWZpY2F0aW9uVHlwZTox") {
    ok
    message
    notification {
      id
      isRead
    }
  }
}
```

#### `markNotificationUnread`

Mark a single notification as unread.

```graphql
mutation {
  markNotificationUnread(notificationId: "Tm90aWZpY2F0aW9uVHlwZTox") {
    ok
    message
    notification {
      id
      isRead
    }
  }
}
```

#### `markAllNotificationsRead`

Mark all user's notifications as read.

```graphql
mutation {
  markAllNotificationsRead {
    ok
    message
    count  # Number of notifications marked
  }
}
```

#### `deleteNotification`

Delete a notification.

```graphql
mutation {
  deleteNotification(notificationId: "Tm90aWZpY2F0aW9uVHlwZTox") {
    ok
    message
  }
}
```

## Permission Model

The notification system follows a **simple ownership model**:

- **Users can only access their own notifications**
- No inheritance from document/corpus permissions
- No sharing or delegation
- Enforced in GraphQL resolvers and mutations

### Query Permissions

- `notifications` query automatically filters to `recipient=current_user`
- `notification(id)` query raises `GraphQLError` if accessing another user's notification
- `unreadNotificationCount` only counts current user's notifications

### Mutation Permissions

All mutations check: `notification.recipient == current_user`

If check fails, returns: `{ok: false, message: "You can only X your own notifications"}`

## Testing

### Test Coverage

**Location**: `opencontractserver/tests/test_notifications.py`, `opencontractserver/tests/test_notification_graphql.py`

**Coverage**: 34 tests covering:

1. **Model Tests**:
   - Notification creation
   - Mark as read/unread
   - Mention extraction (various formats)
   - String representation
   - Ordering

2. **Signal Tests**:
   - Reply notifications (direct and thread participation)
   - Mention notifications (single and multiple)
   - Badge award notifications
   - Moderation notifications (lock, delete, restore)
   - Self-action exclusion

3. **GraphQL Tests**:
   - Query notifications (filtering, pagination)
   - Unread count
   - Mark as read/unread
   - Mark all as read
   - Delete notifications
   - Permission checks

### Running Tests

```bash
# Run all notification tests
docker compose -f test.yml run django python manage.py test \
    opencontractserver.tests.test_notifications \
    opencontractserver.tests.test_notification_graphql

# Run specific test
docker compose -f test.yml run django python manage.py test \
    opencontractserver.tests.test_notifications.TestNotificationModel.test_extract_mentions_basic
```

## Implementation Notes

### Mention Detection

The `extract_mentions()` method uses a carefully crafted regex:

```python
pattern = r"(?:^|(?<=\s))@([\w-]+)(?=\s|[.,!?;:]|$)"
```

**Features**:
- Matches @username at start of string or after whitespace
- Supports alphanumerics, underscores, hyphens
- Must be followed by whitespace, punctuation, or end of string
- Case-insensitive deduplication

**Examples**:
- ✅ `@user1` - Valid
- ✅ `Hey @user_name!` - Valid
- ✅ `cc @user-2` - Valid
- ❌ `email@example.com` - Not matched (no preceding space)
- ❌ `#user1` - Not matched (no @ symbol)

### Thread Participation Logic

When a user posts in a thread:

1. **Direct Reply Notification**: If replying to specific message, parent creator gets `REPLY` notification
2. **Thread Participation Notification**: All users who have posted in thread get `THREAD_REPLY` notification
3. **Deduplication**: If user already got `REPLY` notification, they don't get duplicate `THREAD_REPLY`

### Moderation Integration

Moderation methods (`lock()`, `soft_delete_message()`, etc.) automatically create `ModerationAction` records, which trigger notifications via signals. Tests should NOT manually create duplicate `ModerationAction` records.

## Future Enhancements

Potential improvements (not currently implemented):

1. **Real-time Delivery**: WebSocket/GraphQL subscriptions for instant notifications
2. **Email Notifications**: Configurable email digests
3. **Push Notifications**: Mobile/browser push notifications
4. **Notification Preferences**: User-configurable notification settings
5. **Notification Grouping**: Batch similar notifications (e.g., "5 new votes")
6. **Notification History**: Archive/search old notifications
7. **Notification Templates**: Customizable notification messages

## Related Documentation

- [Backend Architecture](./backend_architecture.md) - Overall system design
- [GraphQL API](./graphql_api.md) - Complete GraphQL documentation
- [Moderation System](./moderation.md) - Moderation features
- [Voting & Reputation](./voting_and_reputation.md) - Voting system

## API Reference

For complete API documentation including all fields and filters, see:
- [GraphQL API Documentation](./graphql_api.md#notification-system)
