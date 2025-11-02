# Corpus Collaboration System Documentation

## Overview

The OpenContracts Corpus Collaboration System enables rich, community-driven interactions within corpus contexts. This system transforms OpenContracts from a document annotation platform into a collaborative knowledge hub by adding discussion capabilities, voting/reputation systems, and moderation tools.

## Epic Issue

This system was implemented as part of Epic [#581 - Corpus Interactivity: Discussion Collaboration System](https://github.com/Open-Source-Legal/OpenContracts/issues/581).

## Implemented Sub-Epics

The following sub-epics have been completed:

1. **[#549](https://github.com/Open-Source-Legal/OpenContracts/issues/549)** - Update GraphQL schema and mutations for thread support
2. **[#550](https://github.com/Open-Source-Legal/OpenContracts/issues/550)** - Epic: Voting System & Reputation
3. **[#554](https://github.com/Open-Source-Legal/OpenContracts/issues/554)** - Create GraphQL mutations for voting with rate limiting
4. **[#557](https://github.com/Open-Source-Legal/OpenContracts/issues/557)** - Create GraphQL mutations for moderation actions
5. **[#558](https://github.com/Open-Source-Legal/OpenContracts/issues/558)** - Epic: Badge System
6. **[#562](https://github.com/Open-Source-Legal/OpenContracts/issues/562)** - Epic: Notification System

## Current Implementation Status

### Backend: ✅ Complete

The backend implementation is fully functional with:
- Complete database models for threads, voting, reputation, moderation, badges, and notifications
- Comprehensive GraphQL API with mutations and queries
- Robust permission system with corpus owners and designated moderators
- Rate limiting to prevent abuse
- Automatic reputation calculation and notification creation via Django signals
- Soft delete functionality for reversible moderation
- Badge system with auto-awarding capabilities
- Real-time notification system for all user interactions
- Extensive test coverage (8 test files, 100,000+ characters of tests)

### Frontend: ⚠️ Not Yet Implemented

The frontend UI components have not been built yet. The backend API is ready to support the UI implementation.

## Core Features

### 1. Discussion Threads

- Create threaded discussions at the corpus or document level
- Support for nested message replies (unlimited depth)
- Thread metadata: title, description, creation timestamp
- Conversation types: CHAT (agent-based) or THREAD (discussion)

### 2. Voting & Reputation System

- Upvote/downvote functionality on messages
- User reputation tracking (both global and per-corpus)
- Denormalized vote counts for performance
- Asynchronous reputation calculation via signals
- Protection against self-voting

### 3. Moderation System

- Corpus-level moderator designation with granular permissions
- Thread locking to prevent new messages
- Thread pinning to highlight important discussions
- Soft deletion of threads and messages (reversible)
- Complete audit trail of all moderation actions
- Permission hierarchy: superusers > corpus owners > designated moderators > creators

### 4. Badge System

- Global and corpus-specific badges
- Manual and automatic badge awarding
- Configurable criteria for auto-awards (reputation thresholds, contribution metrics)
- Badge icons and customizable colors
- Complete audit trail of badge awards and revocations
- Integration with notification system

### 5. Notification System

- Real-time notifications for all user interactions
- 14 notification types: replies, mentions, votes, badges, moderation actions, thread participation
- @username mention detection with smart parsing
- Configurable read/unread status
- GraphQL API for managing notifications
- Automatic cleanup via signal handlers
- Rich notification context data

### 6. Rate Limiting

- Multi-level rate limiting to prevent abuse
- Different limits for different operation types
- User-tier based limits (superuser > authenticated > anonymous)
- IP and user-based tracking

## Documentation Structure

This documentation is organized into the following sections:

1. **[Overview](./README.md)** - This document
2. **[Backend Architecture](./backend_architecture.md)** - Database models, signals, and core logic
3. **[GraphQL API](./graphql_api.md)** - Mutations, queries, and type definitions
4. **[Voting & Reputation](./voting_and_reputation.md)** - How voting and reputation scoring works
5. **[Moderation System](./moderation.md)** - Moderator roles, permissions, and actions
6. **[Notifications](./notifications.md)** - Notification system and user alerts
7. **[Testing](./testing.md)** - Test coverage and testing strategies
8. **[Implementation Timeline](./implementation_timeline.md)** - What was built and when

## Quick Links

### Key Backend Files

- **Models**: `opencontractserver/conversations/models.py`, `opencontractserver/badges/models.py`, `opencontractserver/notifications/models.py`
- **Signals**: `opencontractserver/conversations/signals.py`, `opencontractserver/notifications/signals.py`
- **Thread Mutations**: `config/graphql/conversation_mutations.py`
- **Voting Mutations**: `config/graphql/voting_mutations.py`
- **Moderation Mutations**: `config/graphql/moderation_mutations.py`
- **Badge Mutations**: `config/graphql/badge_mutations.py`
- **Notification Mutations**: `config/graphql/notification_mutations.py`
- **Queries**: `config/graphql/queries.py`
- **Rate Limits**: `config/graphql/ratelimits.py`

### Test Files

- `opencontractserver/tests/test_threading.py`
- `opencontractserver/tests/test_voting.py`
- `opencontractserver/tests/test_voting_mutations_graphql.py`
- `opencontractserver/tests/test_moderation.py`
- `opencontractserver/tests/test_conversation_mutations_graphql.py`
- `opencontractserver/tests/test_conversation_query.py`
- `opencontractserver/tests/test_badges.py`
- `opencontractserver/tests/test_notifications.py`
- `opencontractserver/tests/test_notification_graphql.py`

## Development Guidelines

All contributions to this feature set followed these requirements:

### Test Coverage

- **Backend**: All changes include comprehensive tests
  - Run with: `docker compose -f test.yml run django python manage.py test`
  - Target: >90% coverage for new code
  - All tests must pass before PR approval

- **Frontend**: UI components must include Playwright component tests
  - Run with: `yarn run test:ct`
  - Mock backend data appropriately
  - Test user interactions, loading states, and error handling

### Code Quality

- **Pre-commit hooks**: Run `pre-commit run --all-files` before pushing
  - Ensures code formatting (Black, isort, prettier)
  - Linting (flake8, ESLint)
  - Type checking where applicable

### Pull Request Process

- **Target Branch**: PRs opened against the `v3.0.0.b3` branch
- **PR Description**: Includes link to issue, description of changes, test coverage summary, screenshots/videos for UI changes
- **Reviews**: At least one approval required
- **CI/CD**: All GitHub Actions checks must pass

## Next Steps

The following epics remain to be implemented:

- **#565**: Epic: Corpus Engagement Metrics & Analytics
- **#569**: Epic: Thread Search & Discovery
- **#572**: Epic: Frontend UI Implementation (All backend features complete, ready for UI development)
