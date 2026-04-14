# Commenting & Discussion System Documentation

**Last Updated:** January 9, 2026
**Status:** Fully Implemented

## Overview

The commenting and discussion system provides forum-like discussions for corpuses, document-level discussions, and a global discussions view with @ mentions support. This document serves as a reference for the implemented system architecture.

## Quick Status Summary

### Implementation Status

| Feature | Status | Key Files |
|---------|--------|-----------|
| Thread List & Detail Views | Complete | `frontend/src/components/threads/` |
| Message Composer (TipTap) | Complete | `frontend/src/components/threads/MessageComposer.tsx` |
| Voting System | Complete | `frontend/src/components/threads/VoteButtons.tsx` |
| Moderation Controls | Complete | `frontend/src/components/threads/ModerationControls.tsx` |
| Notification Center | Complete | `frontend/src/components/notifications/` |
| Corpus Discussions | Complete | `frontend/src/components/routes/CorpusThreadRoute.tsx` |
| Document Discussions | Complete | Integrated in DocumentKnowledgeBase |
| Global Discussions | Complete | `frontend/src/views/GlobalDiscussions.tsx` |
| @ Mentions | Complete | `frontend/src/components/threads/UnifiedMentionPicker.tsx` |
| Badge Notifications | Complete | `frontend/src/components/badges/BadgeCelebrationModal.tsx` |
| Badge Management UI | Complete | `frontend/src/components/badges/BadgeManagement.tsx` |
| Thread Search | Complete | `frontend/src/views/ThreadSearchRoute.tsx` |

---

## Architecture Overview

### High-Level Architecture

```
Application Layer
  - Corpus Detail (Corpuses.tsx)
  - Document Viewer (DocumentKnowledgeBase)
  - Global Forum View (/discussions)
           |
Thread Components Layer
  - ThreadList, ThreadDetail, ThreadSearch
  - MessageItem, MessageTree, VoteButtons
  - ModerationControls, NotificationBell
           |
State Management Layer
  - Jotai Atoms (threadAtoms.ts)
  - Apollo Cache
           |
Data Layer
  - GraphQL API (queries & mutations)
  - Backend Django + GraphQL (conversation models)
```

### Technology Stack

- **State Management**: Jotai (atomic state) - see `frontend/src/atoms/threadAtoms.ts`
- **GraphQL Client**: Apollo Client
- **Styling**: styled-components
- **Routing**: React Router
- **Testing**: Playwright Component Tests
- **Rich Text**: TipTap (message composer)
- **Icons**: Lucide React

---

## Source File Locations

### Backend

| Component | Location |
|-----------|----------|
| Conversation Models | `opencontractserver/conversations/models.py` |
| Conversation Signals | `opencontractserver/conversations/signals.py` |
| GraphQL Types | `config/graphql/graphene_types.py` (ConversationType, ChatMessageType) |
| GraphQL Mutations | `config/graphql/conversation_mutations.py` |
| Mention Permission Tests | `opencontractserver/tests/test_mention_permissions.py` |

### Frontend Components

| Component | Location |
|-----------|----------|
| Thread Components | `frontend/src/components/threads/` |
| Thread List | `frontend/src/components/threads/ThreadList.tsx` |
| Thread Detail | `frontend/src/components/threads/ThreadDetail.tsx` |
| Thread List Item | `frontend/src/components/threads/ThreadListItem.tsx` |
| Message Item | `frontend/src/components/threads/MessageItem.tsx` |
| Message Tree | `frontend/src/components/threads/MessageTree.tsx` |
| Message Composer | `frontend/src/components/threads/MessageComposer.tsx` |
| Vote Buttons | `frontend/src/components/threads/VoteButtons.tsx` |
| Moderation Controls | `frontend/src/components/threads/ModerationControls.tsx` |
| Reply Form | `frontend/src/components/threads/ReplyForm.tsx` |
| Create Thread Form | `frontend/src/components/threads/CreateThreadForm.tsx` |
| Thread Badge | `frontend/src/components/threads/ThreadBadge.tsx` |

### Notification Components

| Component | Location |
|-----------|----------|
| Notification Bell | `frontend/src/components/notifications/NotificationBell.tsx` |
| Notification Center | `frontend/src/components/notifications/NotificationCenter.tsx` |
| Notification Dropdown | `frontend/src/components/notifications/NotificationDropdown.tsx` |
| Notification Item | `frontend/src/components/notifications/NotificationItem.tsx` |

### Badge Components

| Component | Location |
|-----------|----------|
| Badge Celebration Modal | `frontend/src/components/badges/BadgeCelebrationModal.tsx` |
| Badge Toast | `frontend/src/components/badges/BadgeToast.tsx` |
| Badge Management | `frontend/src/components/badges/BadgeManagement.tsx` |
| User Badges | `frontend/src/components/badges/UserBadges.tsx` |
| Message Badges | `frontend/src/components/badges/MessageBadges.tsx` |

### Mention Components

| Component | Location |
|-----------|----------|
| Unified Mention Picker | `frontend/src/components/threads/UnifiedMentionPicker.tsx` |
| Resource Mention Picker | `frontend/src/components/threads/ResourceMentionPicker.tsx` |
| Mention Picker | `frontend/src/components/threads/MentionPicker.tsx` |
| Markdown Message Renderer | `frontend/src/components/threads/MarkdownMessageRenderer.tsx` |

### Routes and Views

| Component | Location |
|-----------|----------|
| Global Discussions View | `frontend/src/views/GlobalDiscussions.tsx` |
| Global Discussions Route | `frontend/src/components/routes/GlobalDiscussionsRoute.tsx` |
| Corpus Thread Route | `frontend/src/components/routes/CorpusThreadRoute.tsx` |
| Thread Search Route | `frontend/src/views/ThreadSearchRoute.tsx` |
| Thread Search Component | `frontend/src/components/search/ThreadSearch.tsx` |

### State Management

| Component | Location |
|-----------|----------|
| Thread Atoms | `frontend/src/atoms/threadAtoms.ts` |
| Thread Preferences Hook | `frontend/src/components/threads/hooks/useThreadPreferences.ts` |
| Badge Notifications Hook | `frontend/src/hooks/useBadgeNotifications.ts` |
| Mention Search Hooks | `frontend/src/components/threads/hooks/useUnifiedMentionSearch.ts` |

### Tests

| Test | Location |
|------|----------|
| Thread Component Tests | `frontend/src/components/threads/__tests__/` |
| Mention Permission Tests | `opencontractserver/tests/test_mention_permissions.py` |

---

## State Management

### Jotai Atoms

The discussion system uses Jotai atoms defined in `frontend/src/atoms/threadAtoms.ts`:

- `threadSortAtom` - Current sort order (newest, active, upvoted, pinned)
- `threadFiltersAtom` - Filter options (showLocked, showDeleted)
- `currentThreadIdAtom` - Currently selected thread
- `selectedMessageIdAtom` - Message for deep linking
- `expandedMessageIdsAtom` - Collapsible thread state
- `showCreateThreadModalAtom` - Thread creation modal visibility
- `replyingToMessageIdAtom` - Reply form target

### Apollo Cache Configuration

Cache policies for conversation types are configured in the Apollo cache setup. Key considerations:

- `ConversationType.allMessages` - Messages are in-memory only, not paginated
- `ChatMessageType.upvoteCount/downvoteCount` - Use optimistic updates
- `Query.conversations` - Paginated with cursor-based merging

---

## Routing

### Routes

| Path | Component | Description |
|------|-----------|-------------|
| `/discussions` | GlobalDiscussionsRoute | Global discussions view |
| `/c/:userIdent/:corpusIdent/discussions/:threadId` | CorpusThreadRoute | Full-page corpus thread |
| `/d/:userIdent/:docIdent?thread=:threadId` | DocumentKnowledgeBase | Document thread (query param) |

### Navigation Utilities

Thread navigation utilities are available in `frontend/src/utils/navigationUtils.ts` for:
- Updating thread selection in URL
- Generating corpus thread URLs
- Navigating between thread views

---

## Key Features

### @ Mentions System

The @ mention system allows users to reference corpuses, documents, and other users in messages.

**Backend Implementation:**
- Permission-based filtering (write access OR public resources)
- GraphQL search queries: `searchCorpusesForMention`, `searchDocumentsForMention`
- IDOR protection via silent filtering

**Frontend Implementation:**
- TipTap extension with @ trigger
- Autocomplete dropdown with keyboard navigation
- Clickable mention chips for navigation

**Documentation:** See `docs/permissioning/mention_permissioning_spec.md` for detailed permissioning rules.

### Voting System

- Upvote/downvote with optimistic updates
- Vote counts displayed on messages
- User's current vote state tracked

### Moderation

- Pin/unpin threads
- Lock/unlock threads
- Soft delete/restore threads and messages
- Moderator badge display

### Notifications

- Real-time notification polling (30-second interval)
- Unread count badge
- Notification types: replies, mentions, badge awards, moderation actions
- Mark as read/unread functionality

### Badge Celebrations

- Toast notifications for badge awards
- Full-screen celebration modal for significant badges
- Queue management for multiple simultaneous badges
- Framer Motion animations

---

## Conversation Types

The backend supports flexible conversation types:

| Type | Description | Use Case |
|------|-------------|----------|
| THREAD | Forum-style with title | Corpus discussions |
| COMMENT | Simple comment, no title | Document annotations |
| CHAT | Real-time conversation | Agent chat (WebSocket) |

The `conversation_type` field is a UI hint - the backend doesn't enforce strict behavior differences. Frontend adapts UI based on context.

---

## Security Patterns

### IDOR Prevention

All mutations use `visible_to_user()` filtering or creator-scoped queries BEFORE object retrieval. Uniform error messages prevent resource enumeration.

Example pattern:
```python
try:
    obj = Model.objects.visible_to_user(user).get(pk=pk)
except Model.DoesNotExist:
    return Mutation(ok=False, message="Not found")  # Same for non-existent AND unauthorized
```

### Permission Model

- Conversations inherit permissions from parent corpus/document
- Mentions require write permission on private resources OR resource must be public
- Moderation requires corpus/document ownership or explicit moderator role

---

## Testing

### Running Tests

```bash
# Backend conversation tests
docker compose -f test.yml run django pytest opencontractserver/tests/test_mention_permissions.py -v

# Frontend component tests
cd frontend
yarn test:ct --reporter=list -g "Thread"
yarn test:ct --reporter=list frontend/src/components/threads/__tests__/
```

### Test Patterns

- Use test wrappers that provide MockedProvider + JotaiProvider
- GraphQL mocks must match variables exactly (null vs undefined matters)
- Include mocks for refetch calls
- Use `--reporter=list` to prevent Playwright hanging

---

## Performance Considerations

1. **Message Tree Memoization** - Use `useMemo` for tree building
2. **Virtual Scrolling** - For lists with >100 items
3. **Debounced Search** - 300ms debounce on search inputs
4. **Lazy Loading** - Images and avatars use `loading="lazy"`
5. **Polling Intervals** - 30-second polling for notifications and thread updates

---

## Accessibility

- Keyboard navigation through thread lists (Tab, Enter, Arrow keys)
- ARIA labels on interactive elements
- Focus management for modals
- Screen reader announcements for loading/error states
- WCAG 2.1 AA compliance

---

## Related Documentation

- **Permissioning Guide**: `docs/permissioning/consolidated_permissioning_guide.md`
- **Mention Permissions**: `docs/permissioning/mention_permissioning_spec.md`
- **Frontend Routing**: `docs/frontend/routing_system.md`
- **PDF Data Layer**: `docs/architecture/PDF-data-layer.md`

---

## Historical Implementation Notes

The discussion system was implemented across multiple issues:

| Issue | Feature | Status |
|-------|---------|--------|
| #573 | Thread List and Detail Views | Closed |
| #574 | Message Composer and Reply UI | Closed |
| #575 | Voting UI and Reputation Display | Closed |
| #576 | Moderation UI and Controls | Closed |
| #577 | Notification Center UI | Closed |
| #578 | Badge Display and Management UI | Closed |
| #579 | Analytics Dashboard | Closed |
| #580 | Thread Search UI | Closed |
| #610 | User Badge Display in Conversations | Closed |
| #611 | User Profile Page | Closed |
| #612 | Badge Notification System | Closed |
| #621 | Corpus Discussion Integration | Closed |
| #622 | Document Discussion Integration | Closed |
| #623 | Global Discussions + @ Mentions | Closed |
| #634 | Backend Agent/Bot Configuration | Closed |
