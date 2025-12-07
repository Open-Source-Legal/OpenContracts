# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

OpenContracts is an Apache 2.0 licensed enterprise document analytics platform for PDFs and text-based formats. It features a Django/GraphQL backend with PostgreSQL + pgvector, a React/TypeScript frontend, and pluggable document processing pipelines powered by machine learning models.

## Essential Commands

### Backend (Django)

```bash
# Run backend tests (use --keepdb to speed up subsequent runs)
docker compose -f test.yml run django python manage.py test --keepdb

# Run specific test file
docker compose -f test.yml run django python manage.py test opencontractserver.tests.test_notifications --keepdb

# Run specific test class/method
docker compose -f test.yml run django python manage.py test opencontractserver.tests.test_notifications.TestNotificationModel.test_create_notification --keepdb

# Apply database migrations
docker compose -f local.yml run django python manage.py migrate

# Create new migration
docker compose -f local.yml run django python manage.py makemigrations

# Django shell
docker compose -f local.yml run django python manage.py shell

# Code quality (runs automatically via pre-commit hooks)
pre-commit run --all-files
```

### Frontend (React/TypeScript)

```bash
cd frontend

# Start development server
yarn start

# Run unit tests (Vitest)
yarn run test:unit

# Run component tests (Playwright) - IMPORTANT: Use --reporter=list to prevent hanging
yarn run test:ct --reporter=list

# Run component tests with grep filter
yarn run test:ct --reporter=list -g "test name pattern"

# Linting and formatting
yarn lint
yarn fix-styles

# Build for production
yarn build
```

### Production Deployment

```bash
# CRITICAL: Always run migrations FIRST in production
docker compose -f production.yml --profile migrate up migrate

# Then start main services
docker compose -f production.yml up
```

## High-Level Architecture

### Backend Architecture

**Stack**: Django 4.x + GraphQL (Graphene) + PostgreSQL + pgvector + Celery

**Key Patterns**:

1. **GraphQL Schema Organization**:
   - `config/graphql/graphene_types.py` - All GraphQL type definitions
   - `config/graphql/queries.py` - Query resolvers
   - `config/graphql/*_mutations.py` - Mutation files (organized by feature)
   - `config/graphql/schema.py` - Schema composition

2. **Permission System** (CRITICAL - see `docs/permissioning/consolidated_permissioning_guide.md`):
   - **Annotations & Relationships**: NO individual permissions - inherited from document + corpus
   - **Documents & Corpuses**: Direct object-level permissions via django-guardian
   - **Analyses & Extracts**: Hybrid model (own permissions + corpus permissions + document filtering)
   - Formula: `Effective Permission = MIN(document_permission, corpus_permission)`
   - **Structural items are ALWAYS read-only** except for superusers
   - Use `Model.objects.visible_to_user(user)` pattern (NOT `resolve_oc_model_queryset` - DEPRECATED)

3. **AnnotatePermissionsForReadMixin**:
   - Most GraphQL types inherit this mixin (see `config/graphql/permissioning/permission_annotator/mixins.py`)
   - Adds `my_permissions`, `is_published`, `object_shared_with` fields
   - Requires model to have guardian permission tables (`{model}userobjectpermission_set`)
   - Notifications use simple ownership model and DON'T use this mixin

4. **Django Signal Handlers**:
   - Automatic notification creation on model changes (see `opencontractserver/notifications/signals.py`)
   - Must be imported in app's `apps.py` `ready()` method
   - Use `_skip_signals` attribute to prevent duplicate notifications in tests

5. **Pluggable Parser Pipeline**:
   - Base classes in `opencontractserver/pipeline/base/`
   - Parsers, embedders, thumbnailers auto-discovered and registered
   - Multiple backends: Docling (ML-based), NLM-Ingest, Text
   - All convert to unified PAWLs format for frontend

### Frontend Architecture

**Stack**: React 18 + TypeScript + Apollo Client + Jotai + PDF.js + Vite

**Key Patterns**:

1. **State Management**:
   - **Jotai atoms** for global state (NOT Redux/Context)
   - Located in `frontend/src/atoms/` directory
   - Key atoms: `pdfAnnotationsAtom`, `activeLayerAtom`, `showStructuralAtom`
   - Computed/derived atoms automatically update when dependencies change

2. **Route Driven State**
   - We use routes to drive core object selections - e.g. selected user, selected document, selected corpus. 
   - If you're working on code that touches the routes or requires selection of object, ensure it follows the core routing mantra set forth in docs/frontend/routing_system.md .
   - Ensure any changes to the routing scheme or related code are proeprly reflected in routing system documentation MD file. 

2. **PDF Annotation System** (see `.cursor/rules/pdf-viewer-and-annotator-architecture.mdc`):
   - **Virtualized rendering**: Only visible pages (+overscan) rendered for performance
   - Binary search to find visible page range (O(log n))
   - Height caching per zoom level
   - Two-phase scroll-to-annotation system
   - Dual-layer architecture: Document layer (annotations) + Knowledge layer (summaries)

3. **Unified Filtering Architecture**:
   - `useVisibleAnnotations` and `useVisibleRelationships` hooks provide parallel filtering
   - Both read from same Jotai atoms (`showStructuralAtom`, `showSelectedOnlyAtom`)
   - Ensures consistency across all components
   - Forced visibility for selected items and their connections

4. **Component Testing** (see `.cursor/rules/test-document-knowledge-base.mdc`):
   - ALWAYS mount components through test wrappers (e.g., `DocumentKnowledgeBaseTestWrapper`)
   - Wrapper provides: MockedProvider + InMemoryCache + Jotai Provider + asset mocking
   - Use `--reporter=list` flag to prevent hanging
   - Increase timeouts (20s+) for PDF rendering in Chromium
   - GraphQL mocks must match variables EXACTLY
   - Mock same query multiple times for refetches

### Data Flow Architecture

**Document Processing**:
1. Upload → Parser Selection (Docling/NLM-Ingest/Text)
2. Parser generates PAWLs JSON (tokens with bounding boxes)
3. Text layer extracted from PAWLs
4. Annotations created for structure (headers, sections, etc.)
5. Relationships detected between elements
6. Vector embeddings generated for search

**GraphQL Permission Flow**:
1. Query resolver filters objects with `.visible_to_user(user)`
2. GraphQL types resolve `my_permissions` via `AnnotatePermissionsForReadMixin`
3. Frontend uses permissions to enable/disable UI features
4. Mutations check permissions and return consistent errors to prevent IDOR

## Critical Security Patterns

1. **IDOR Prevention**:
   - Query by both ID AND user-owned field: `Model.objects.get(pk=pk, recipient=user)`
   - Return same error message whether object doesn't exist or belongs to another user
   - Prevents enumeration via timing or different error messages

2. **Permission Checks**:
   - NEVER trust frontend - always check server-side
   - Use `visible_to_user()` manager method for querysets
   - Check `user_has_permission_for_obj()` for individual objects (in `opencontractserver.utils.permissioning`)

3. **XSS Prevention**:
   - User-generated content in JSON fields must be escaped on frontend
   - GraphQL's GenericScalar handles JSON serialization safely
   - Document this requirement in resolver comments

## Testing Patterns

### Backend Tests

**Location**: `opencontractserver/tests/`

**Patterns**:
- Use `TransactionTestCase` for tests with signals/asynchronous behavior
- Use `TestCase` for faster tests without transaction isolation
- Clear auto-created notifications when testing moderation: `Notification.objects.filter(recipient=user).delete()`
- Use `_skip_signals` attribute on instances to prevent signal handlers during fixtures

### Frontend Component Tests

**Location**: `frontend/tests/`

**Critical Requirements**:
- Mount through test wrappers that provide all required context
- GraphQL mocks must match query variables exactly
- Include mocks for empty-string variants (unexpected boot calls)
- Wait for visible evidence, not just network-idle
- Use `page.mouse` for PDF canvas interactions (NOT `locator.dragTo`)
- Add settle time after drag operations (500ms UI, 1000ms Apollo cache)

## Documentation Locations

- **Permissioning**: `docs/permissioning/consolidated_permissioning_guide.md`
- **PDF Data Layer**: `docs/architecture/PDF-data-layer.md`
- **Parser Pipeline**: `docs/pipelines/pipeline_overview.md`
- **LLM Framework**: `docs/architecture/llms/README.md`
- **Collaboration System**: `docs/commenting_system/README.md`

## Branch Strategy

- **Development**: PRs target `v3.0.0.b3` branch (NOT main)
- **Production**: `main` branch
- Use feature branches: `feature/description-issue-number`
- Commit message format: Descriptive with issue references (e.g., "Closes #562")

## Pre-commit Hooks

Automatically run on commit:
- black (Python formatting)
- isort (import sorting)
- flake8 (linting)
- prettier (frontend formatting)
- pyupgrade (Python syntax modernization)

Run manually: `pre-commit run --all-files`

## Common Pitfalls

1. **Frontend tests hanging**: Always use `--reporter=list` flag
2. **Permission N+1 queries**: Use `.visible_to_user()` NOT individual permission checks
3. **Missing GraphQL mocks**: Check variables match exactly, add duplicates for refetches
4. **Notification duplication in tests**: Moderation methods auto-create ModerationAction records
5. **Structural annotation editing**: Always read-only except for superusers
6. **Missing signal imports**: Import signal handlers in `apps.py` `ready()` method
7. **PDF rendering slow in tests**: Increase timeouts to 20s+ for Chromium
8. **Cache serialization crashes**: Keep InMemoryCache definition inside wrapper, not test file
9. **Backend Tests Waiting > 10 seconds on Postgres to be Ready**: Usually indicates somehow docker network has gotten fubared. Destroy and recreate network.
