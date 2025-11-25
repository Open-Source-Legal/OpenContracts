# Testing Documentation

## Overview

The collaboration system has comprehensive test coverage across all components: models, signals, GraphQL mutations, queries, and business logic. All tests follow the project's testing standards with >90% coverage requirement.

## Test Organization

### Backend Tests Location

All tests are in `opencontractserver/tests/`:

1. **test_threading.py** - Core conversation and message functionality
2. **test_voting.py** - Voting models and reputation calculation
3. **test_voting_mutations_graphql.py** - GraphQL voting API
4. **test_moderation.py** - Moderation system
5. **test_conversation_mutations_graphql.py** - Thread creation GraphQL API
6. **test_conversation_query.py** - Thread query GraphQL API

### Frontend Tests Location

**Status**: Not yet implemented

**Planned Location**: Frontend component tests using Playwright

**Expected Coverage**: Thread UI, voting buttons, moderation controls

## Running Tests

### Backend Tests

**Run All Collaboration Tests**:

```bash
docker compose -f test.yml run django python manage.py test \
    opencontractserver.tests.test_threading \
    opencontractserver.tests.test_voting \
    opencontractserver.tests.test_voting_mutations_graphql \
    opencontractserver.tests.test_moderation \
    opencontractserver.tests.test_conversation_mutations_graphql \
    opencontractserver.tests.test_conversation_query
```

**Run Specific Test File**:

```bash
docker compose -f test.yml run django python manage.py test \
    opencontractserver.tests.test_voting
```

**Run Specific Test Case**:

```bash
docker compose -f test.yml run django python manage.py test \
    opencontractserver.tests.test_voting.VotingTestCase.test_upvote_increases_count
```

**Run with Coverage Report**:

```bash
docker compose -f test.yml run django coverage run --source='.' manage.py test
docker compose -f test.yml run django coverage report
docker compose -f test.yml run django coverage html
```

### Frontend Tests (Planned)

```bash
# Run all component tests
yarn run test:ct

# Run specific component test
yarn run test:ct ThreadList

# Run in headed mode (see browser)
yarn run test:ct --headed

# Run with coverage
yarn run test:ct --coverage
```
