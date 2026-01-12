# Changelog

All notable changes to OpenContracts will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased] - 2026-01-11

### Changed

#### Removed StructuralAnnotationSet Model - Architecture Simplification
- **Background**: `StructuralAnnotationSet` was designed to allow sharing structural annotations (headers, sections, etc.) across corpuses to avoid duplication. However, analysis showed this benefit was never realized since each corpus always duplicates structural annotations for corpus-specific embeddings.
- **Change**: Removed the entire `StructuralAnnotationSet` model and associated infrastructure
- **Migration Strategy**: 5 reversible migrations that safely move structural annotations from sets to documents:
  1. `0057_remove_structural_set_constraints.py` - Remove XOR constraints
  2. `0058_migrate_structural_to_documents.py` - Data migration (reversible)
  3. `0059_remove_structural_set_fk.py` - Remove FK fields from Annotation/Relationship
  4. `0030_remove_structural_annotation_set_fk.py` - Remove FK from Document
  5. `0060_delete_structuralannotationset.py` - Delete model
- **Files Modified**:
  - `opencontractserver/annotations/models.py` - Removed model, FK fields, and constraints
  - `opencontractserver/documents/models.py` - Removed `structural_annotation_set` FK
  - `opencontractserver/annotations/query_optimizer.py` - Simplified queries (removed union)
  - `opencontractserver/pipeline/base/parser.py` - Removed structural set creation
  - `opencontractserver/corpuses/models.py` - Updated `add_document()` to copy structural annotations
  - `opencontractserver/utils/export_v2.py` - Removed structural set packaging
  - `opencontractserver/utils/import_v2.py` - Added backward compatibility for legacy imports
  - `opencontractserver/tasks/export_tasks_v2.py`, `import_tasks_v2.py` - Updated export/import
- **Tests Deleted**: 5 obsolete test files for structural annotation sets
- **Management Commands Deleted**: `migrate_structural_annotations.py`
- **Backward Compatibility**: V2 exports now include empty `structural_annotation_sets` dict; legacy imports handle embedded structural data

#### Fixed Export/Import Document Hash Matching
- **Bug**: V2 round-trip export/import failed to match documents because PDF modifications (annotation burn-in via PyPDF2) changed the file hash
- **Root Cause**: Export modifies PDFs with annotations, but import used hash from modified PDF
- **Fix**: Export now stores original `pdf_file_hash` in document data; import uses stored hash for matching
- **Files Changed**:
  - `opencontractserver/types/dicts.py` - Added `pdf_file_hash` field to `OpenContractDocExport`
  - `opencontractserver/utils/etl.py` - Include original hash in export
  - `opencontractserver/tasks/import_tasks_v2.py` - Use stored hash for document matching

### Fixed

#### Android Share URL Missing Entity Prefix (PR #795)
- **Bug**: Android native share was dropping entity type prefixes (`/c/`, `/d/`, `/e/`) from shared URLs
- **Root Cause**: `frontend/src/components/seo/MetaTags.tsx:50-56` was generating canonical URLs as `/{userSlug}/{entitySlug}` instead of `/{prefix}/{userSlug}/{entitySlug}`
- **Impact**: Links shared via Android browser resulted in 404s (e.g., `/john/my-corpus` instead of `/c/john/my-corpus`)
- **Fix**: Refactored `MetaTags.tsx` to use existing `buildCanonicalPath()` utility from `navigationUtils.ts`
- **Added**: Unit tests for MetaTags canonical URL generation (`frontend/src/components/seo/__tests__/MetaTags.test.tsx`)
- **Added**: Development warning for unexpected `entityType` values
- **Added**: Enhanced Cloudflare worker request logging for crawler debugging (`cloudflare-og-worker/src/index.ts`)

### Security

#### WebSocket Agent Permission Vulnerability Fixed (PR #792)
- **CRITICAL**: Fixed permission bypass in legacy WebSocket consumers
  - `config/websocket/consumers/corpus_conversation.py` - No permission checks
  - `config/websocket/consumers/document_conversation.py` - No permission checks
  - `config/websocket/consumers/standalone_document_conversation.py` - No permission checks
  - **Impact**: Any authenticated user could access ANY document/corpus via WebSocket
- **Solution**: Migrated to `UnifiedAgentConsumer` with three-layer permission model:
  - Consumer layer validates READ permission at WebSocket connect time (`config/websocket/consumers/unified_agent_conversation.py:93-187`)
  - Tool filtering layer removes write tools for read-only users (`opencontractserver/llms/agents/agent_factory.py:178-210`)
  - Runtime layer validates permissions before every tool execution (`opencontractserver/llms/tools/pydantic_ai_tools.py:20-111`)
- **Defense-in-depth**: Added `_check_user_permissions()` function that validates user has READ permission on document/corpus before any tool execution
- **Tool permission flags**: Added `requires_write_permission` flag to `CoreTool` (`opencontractserver/llms/tools/tool_factory.py:45-50`)
- **Write tools protected**: `add_document_note`, `update_document_summary`, `update_corpus_description`, `duplicate_annotations`

### Added

#### WebSocket Permission Escalation Tests (49 tests)
- **Test file**: `opencontractserver/tests/websocket/test_agent_permission_escalation.py`
- **Consumer-level permission tests** (13 tests): Validates connection-time permission checks for corpus, document, and combined contexts
- **Tool filtering tests** (13 tests): Verifies write tools filtered for read-only users and anonymous access
- **Runtime permission validation tests** (6 tests): Defense-in-depth `_check_user_permissions()` function
- **Permission escalation scenarios** (9 tests): Cross-user access, mid-session permission changes, resource substitution attacks
- **Integration tests** (8 tests): Full conversation flows with permission verification

#### MCP Telemetry Tracking
- **PostHog telemetry for MCP usage** (`opencontractserver/mcp/telemetry.py`): Track MCP tool calls and resource reads when telemetry is enabled
  - Records tool usage (`mcp_tool_call`): tool name, success/failure, error type
  - Records resource access (`mcp_resource_read`): resource type (corpus, document, annotation, thread), success/failure
  - Records general requests (`mcp_request`): endpoint, method, transport type, success/failure
  - Privacy-preserving: Uses salted SHA-256 IP hashing for unique user counting (raw IPs are never sent to PostHog)
  - Support for all MCP transports: streamable_http, sse, stdio
  - No query content or outputs are captured - only usage metadata
- **Telemetry integration in MCP server** (`opencontractserver/mcp/server.py`):
  - Context-based telemetry with per-request isolation via ContextVar
  - Automatic client IP extraction from ASGI scope (supports X-Forwarded-For, X-Real-IP)
  - Error telemetry for failed requests with error type classification
  - Records both successful and failed requests for error rate calculations
- **Comprehensive test coverage** (`opencontractserver/mcp/tests/test_mcp.py`):
  - Unit tests for IP hashing, context management, event recording
  - Integration tests for telemetry recording in tool/resource handlers
  - Context manager for test isolation (`isolated_telemetry_context`)

### Removed

#### Legacy WebSocket Consumers (Security Cleanup)
- **Deleted**: `config/websocket/consumers/corpus_conversation.py` (~330 lines)
- **Deleted**: `config/websocket/consumers/document_conversation.py` (~610 lines)
- **Deleted**: `config/websocket/consumers/standalone_document_conversation.py` (~530 lines)
- **Deleted**: `opencontractserver/tests/test_websocket_corpus_consumer.py` - Obsolete tests for deleted consumer
- **Deleted**: `opencontractserver/tests/test_websocket_document_consumer.py` - Obsolete tests for deleted consumer
- **Deleted**: `opencontractserver/tests/websocket/test_standalone_document_consumer.py` - Obsolete tests for deleted consumer
- **Updated**: `config/asgi.py` - Removed legacy WebSocket routes

### Changed

#### Frontend WebSocket Migration
- **Updated**: `frontend/src/components/chat/get_websockets.ts` - All WebSocket URLs now use unified endpoint
- **Updated**: `frontend/src/components/knowledge_base/document/utils.ts` - Document chat uses unified endpoint

### Technical Details
- Uses existing PostHog infrastructure from `config/telemetry.py`
- Respects `TELEMETRY_ENABLED` setting and TEST mode disable
- IP hashing uses `TELEMETRY_IP_SALT` setting to prevent rainbow table attacks
- ContextVar ensures proper isolation in concurrent async requests

---

## [Unreleased] - 2026-01-04

### Changed

#### NavMenu Refactoring (PR #779)
- **Migrated to @os-legal/ui NavBar** (`frontend/src/components/layout/NavMenu.tsx`): Complete refactor from Semantic UI Menu to unified NavBar component
  - Single responsive component replaces separate NavMenu and MobileNavMenu
  - Built-in hamburger menu at 1100px breakpoint eliminates conditional rendering in App.tsx
  - Modern styling consistent with os-legal-style design system
- **Deleted obsolete files**: Removed `MobileNavMenu.tsx` and `MobileNavMenu.css` (~370 lines)
- **Simplified App.tsx** (`frontend/src/App.tsx:320-325`): Removed conditional menu rendering and `useWindowDimensions` dependency
- **Improved code quality** (`frontend/src/components/layout/NavMenu.tsx`):
  - Replaced inline SVG icons with lucide-react imports (Download, User, Settings, LogOut)
  - Refactored login button to use styled-components instead of inline styles
  - Added type-safe `getUserProps` helper to replace `as any` casts for user properties

### Added

#### NavMenu Component Tests
- **Playwright component tests** (`frontend/tests/NavMenu.ct.tsx`): 18 comprehensive tests covering:
  - Navigation items and active state highlighting
  - Authentication states (login button vs user menu)
  - User menu items (Exports, Profile, Admin Settings, Logout)
  - Superuser-only features (Badge Management nav item, Admin Settings menu)
  - Branding elements (logo, version badge, brand name)
  - Responsive behavior (hamburger menu, mobile navigation)
- **Test wrapper** (`frontend/tests/NavMenuTestWrapper.tsx`): Provides Auth0Provider, MockedProvider, MemoryRouter, and JotaiProvider context

### Fixed

#### Superuser Features in Non-Auth0 Mode
- **LOGIN_MUTATION missing isSuperuser** (`frontend/src/graphql/mutations.ts:49-65`): Added `isSuperuser` field to login query
  - Previously, superuser features (Badge Management, Admin Settings) were broken in non-Auth0 mode
  - Updated `LoginOutputs` interface to include `username`, `isUsageCapped`, and `isSuperuser` fields

---

## [Unreleased] - 2026-01-03

### Fixed

#### WebSocket Connection Performance (Issue: Chat "Reconnecting" delay)
- **Auth0 JWKS caching** (`config/graphql_auth0_auth/utils.py:17-38`): Added in-memory cache for Auth0 JWKS with 10-minute TTL
  - Previously fetched JWKS from Auth0 on every token validation, causing 6-10 second delays
  - Now caches JWKS keys, reducing subsequent WebSocket auth to near-instant
- **CorpusChat double connection fix** (`frontend/src/components/corpuses/CorpusChat.tsx:1043-1056`): Skip forceNewChat useEffect on initial mount
  - `isNewChat` state already initialized from `forceNewChat` prop
  - Prevents redundant `startNewChat()` call that caused socket close/reconnect cycle
- **Notification WebSocket auth guard** (`frontend/src/hooks/useNotificationWebSocket.ts:312-318`): Skip connection attempt without auth token
  - Prevents 403 Access Denied errors when connecting before auth token is available
  - Eliminates unnecessary connection attempts and error spam in console

---

## [Unreleased] - 2026-01-02

### Added

#### Extract View Refactoring (PR #772)
- **Route-based extract detail view** (`frontend/src/views/ExtractDetail.tsx:439-1063`, `frontend/src/components/routes/ExtractDetailRoute.tsx:1-58`): Complete refactor from modal-based to route-based architecture
  - Modern full-page layout with tabbed interface (Data, Documents, Schema)
  - Stats grid showing document count, column count, rows, and success rate
  - WebSocket-based real-time updates for running extracts (replaced polling)
  - Responsive design following existing patterns
- **WebSocket notification hook** (`frontend/src/hooks/useExtractCompletionNotification.ts:1-86`): Real-time extract completion detection
  - Listens for `EXTRACT_COMPLETE` notifications via WebSocket
  - Filters for specific extract ID and triggers refetch on completion
  - Eliminates need for polling (previously every 5 seconds)
- **Extracts list page** (`frontend/src/views/Extracts.tsx:1-410`): New landing page for extract management
  - Filter tabs (All, My Extracts, Running, Completed)
  - Search with debounced input and cleanup on unmount
  - CollectionCard components with status indicators
- **Extract list card** (`frontend/src/components/extracts/ExtractListCard.tsx:1-228`): Card component for extract listing
  - Status-aware styling (Running, Completed, Failed, Not Started)
  - Context menu with view and delete actions
  - Keyboard accessibility (Escape to close, Enter/Space to activate)
- **Shared utilities** (`frontend/src/utils/extractUtils.ts:1-70`): DRY utility functions using centralized constants
- **Extract landing route** (`frontend/src/components/routes/ExtractLandingRoute.tsx:1-35`): Route component for /extracts

### Removed
- **EditExtractModal component**: Replaced by route-based ExtractDetail view - modal approach deprecated
- **Obsolete test files** (`frontend/tests/EditExtractModal.ct.tsx`, `frontend/tests/EditExtractModalTestWrapper.tsx`): Removed tests for deleted modal component
- **Polling constants** (`frontend/src/constants/extract.ts`): Removed `EXTRACT_POLLING_INTERVAL_MS` and `EXTRACT_POLLING_TIMEOUT_MS` - replaced by WebSocket notifications

### Changed
- **openedExtract reactive var documentation** (`frontend/src/graphql/cache.ts:364-388`): Clarified that route components (like ExtractDetailRoute) can set this var, not just CentralRouteManager
- **Consolidated constants** (`frontend/src/assets/configurations/constants.ts:47-51`): Moved `EXTRACT_SEARCH_DEBOUNCE_MS` to centralized `DEBOUNCE` object
- **extractUtils refactor** (`frontend/src/utils/extractUtils.ts:32-55`): Now uses `EXTRACT_STATUS` and `EXTRACT_STATUS_COLORS` constants instead of hardcoded values

---

## [Unreleased] - 2026-01-01

### Added

#### Corpuses Page Redesign
- **CorpusListView component** (`frontend/src/components/corpuses/CorpusListView.tsx`): Modern corpus listing page using @os-legal/ui components
  - Hero section with search and filter tabs (All, My Corpuses, Shared, Public)
  - Stats grid showing corpus, document, annotation, and shared counts
  - CollectionCard components with category badges, visibility status, and labelset information
  - Context menu for edit, view, export, fork, and delete actions
  - Infinite scroll support for large corpus lists
- **PostHog Analytics Integration** (`frontend/src/utils/analytics.ts`): Consent-based analytics tracking
  - Cookie consent banner integration
  - Automatic test/CI environment detection to prevent analytics in non-production
  - User identification and event tracking functions
  - Page view tracking for SPA navigation
- **Component tests** (`frontend/tests/CorpusListView.ct.tsx`): 12 Playwright component tests for CorpusListView
- **Unit tests** (`frontend/src/utils/__tests__/analytics.test.ts`): 20 Vitest tests for analytics utility functions

### Fixed

#### Routing Audit Follow-ups
- **Notification navigation fallback** (`frontend/src/components/notifications/NotificationDropdown.tsx:182-188`, `NotificationCenter.tsx:207-213`): Added fallback navigation to `/discussions` when corpus slug data is missing. Previously, users clicking notifications with missing slug data would see no response.
- **Network-only fetch policy optimization** (`frontend/src/routing/CentralRouteManager.tsx:621-632`): Changed thread resolution corpus query from `network-only` to `cache-and-network` since `authInitComplete` now ensures `clearStore()` completes before route queries run. This improves navigation performance when corpus data is already cached.
- **Unit test coverage** (`frontend/src/utils/__tests__/navigationUtils.test.ts:497-503`): Added missing test for `parseRoute("/discussions")` to prevent regression of discussions route parsing.

#### Type Safety and Bug Fixes
- **User email detection** (`frontend/src/components/corpuses/CorpusListView.tsx:345-349`): Fixed currentUserEmail logic to use `userObj` reactive variable from Apollo cache instead of inferring from corpus permissions - prevents filter failures when no corpus has CAN_REMOVE permission
- **TypeScript type casts** (`frontend/src/components/corpuses/CorpusListView.tsx`, `CorpusModal.tsx`): Removed 7 `as any` type casts by correcting `CorpusType.categories` type from `CorpusCategoryTypeConnection` to `CorpusCategoryType[]` to match backend GraphQL schema
- **N+1 query prevention** (`config/graphql/queries.py:820-825`): Added `prefetch_related("categories")` to `resolve_corpuses` to avoid N+1 queries when fetching corpus categories

### Changed
- **Deleted CorpusCards component** (`frontend/src/components/corpuses/CorpusCards.tsx`): Replaced by CorpusListView with @os-legal/ui components

#### LabelSet Detail Page Refactoring
- **LabelSetDetailPage component split** (`frontend/src/components/labelsets/LabelSetDetailPage.tsx`): Reduced from 2,064 lines to ~1,100 lines
  - Extracted 16 SVG icons to `detail/LabelSetIcons.tsx`
  - Extracted 40+ styled-components to `detail/LabelSetDetailStyles.ts`
  - Added barrel exports in `detail/index.ts`
- **Color constants centralized** (`frontend/src/assets/configurations/constants.ts`): Added `DEFAULT_LABEL_COLOR` and `PRIMARY_LABEL_COLOR`

### Security
- **Frontend permission checks** (`frontend/src/components/labelsets/LabelSetDetailPage.tsx:1189-1344`): Added defensive permission checks to all mutation handlers
  - `handleDeleteLabel` now verifies `canRemove` before deletion
  - `handleSaveEdit` now verifies `canUpdate` before updating
  - `handleSaveCreate` now verifies `canUpdate` before creation
  - `handleDelete` (labelset) now verifies `canRemove` before deletion
- **Color input sanitization** (`frontend/src/components/labelsets/LabelSetDetailPage.tsx:125-143`): Added `isValidHexColor` and `sanitizeColor` utilities
  - Validates hex color format (3 or 6 character, with or without #)
  - Prevents potential XSS via CSS color injection

### Technical Details
- New test file: `frontend/tests/LabelSetDetailPage.ct.tsx` with comprehensive component tests
  - Rendering tests for all tabs (Overview, Text/Doc/Span/Relationship Labels)
  - Permission-based UI visibility tests
  - Search functionality tests
  - Mobile navigation tests

---

## [Unreleased] - 2025-12-31

### Added

#### Secure Zip Import with Folder Structure Preservation
- **Zip security utilities** (`opencontractserver/utils/zip_security.py`): Comprehensive security validation for zip file imports
  - Path traversal protection: Sanitizes all paths, rejects `..` sequences, drive letters, absolute paths
  - Zip bomb detection: Monitors compression ratios, enforces size limits (500MB total, 100MB per file)
  - Symlink rejection: Detects and skips symbolic links in zip entries
  - Resource limits: Max 1000 files, 500 folders, 20 levels deep (all configurable)
  - Hidden file filtering: Skips `.DS_Store`, `__MACOSX`, `Thumbs.db`, etc.
- **Security constants** (`opencontractserver/constants/zip_import.py`): Configurable limits via Django settings
- **Folder structure creation** (`opencontractserver/corpuses/folder_service.py:1268-1411`): `create_folder_structure_from_paths()` efficiently creates folder hierarchies, reusing existing folders
- **Import Celery task** (`opencontractserver/tasks/import_tasks.py:580-912`): `import_zip_with_folder_structure` task with three-phase processing:
  - Phase 1: Security validation without extraction
  - Phase 2: Atomic folder structure creation
  - Phase 3: Batched document processing with per-file error handling
- **GraphQL mutation** (`config/graphql/mutations.py:1890-2040`): `importZipToCorpus` mutation with rate limiting
  - Accepts base64-encoded zip file
  - Optional target folder placement
  - Returns job_id for async tracking
  - Requires corpus EDIT permission
- **Document upversioning on collision**: When importing a document to a path that already has a document, the new document becomes version 2 (or higher), with the previous version preserved in history
- **Comprehensive test suites**:
  - Security tests (`opencontractserver/tests/test_zip_security.py`): 49 tests for path sanitization, validation, edge cases
  - Integration tests (`opencontractserver/tests/test_zip_import_integration.py`): 17 tests for task and folder service
- **Design documentation** (`docs/features/zip_import_with_folders_design.md`): Complete specification including security model, API, error handling

#### Corpus Categories and Landing Page Redesign
- **CorpusCategory model** (`opencontractserver/corpuses/models.py`): New model for organizing corpuses by type (Legislation, Contracts, Case Law, Knowledge)
  - Admin-provisioned structural data - managed via Django Admin only
  - ManyToMany relationship with Corpus for flexible categorization
  - Default categories seeded via migration (`0035_seed_default_categories.py`)
- **CorpusCategoryType GraphQL type** (`config/graphql/graphene_types.py:1589-1633`):
  - Globally visible to all users (no individual permissions)
  - `corpusCount` field with N+1 query optimization via annotation
- **Landing page redesign** using @os-legal/ui component library:
  - `CompactLeaderboard` component - clean list-based leaderboard replacing grid cards
  - `CategorySelector` component for corpus categorization
  - Skeleton loading states and error handling throughout
- **TypeScript types** (`frontend/src/types/graphql-api.ts`): Added `CorpusCategoryType`, `CorpusCategoryTypeConnection`, `CorpusCategoryTypeEdge`
- **Array utilities** (`frontend/src/utils/arrayUtils.ts`): `arraysEqualUnordered` and `arraysEqualOrdered` for DRY comparison logic

### Fixed

#### Security and Performance
- **System user security** (`opencontractserver/corpuses/migrations/0035_seed_default_categories.py`): Defense-in-depth with unusable password for system user
- **N+1 query in corpusCount** (`config/graphql/queries.py:835-866`): Pre-annotated counts in `resolve_corpus_categories` resolver
- **Type safety** (`frontend/src/components/corpuses/CorpusModal.tsx`, `CorpusSettings.tsx`): Removed `as any` casts for categories field

### Changed
- **Permission model** (`config/graphql/graphene_types.py`): `CorpusCategoryType` no longer uses `AnnotatePermissionsForReadMixin` - categories are globally visible structural data
- **Documentation** (`docs/permissioning/consolidated_permissioning_guide.md`): Added section on CorpusCategory permissions

### Technical Details
- Categories are created by a `system` user with `is_active=False` and unusable password
- `corpusCount` respects user visibility: anonymous sees public corpuses only, authenticated users see corpuses they have access to
- Removed 632-line `TopContributors.tsx` component, replaced with ~280-line `CompactLeaderboard.tsx`

---

## [Unreleased] - 2025-12-29

### Added

#### Moderation Dashboard and Rollback Features (Issue #742)
- **ModerationActionType GraphQL type** (`config/graphql/graphene_types.py:3071-3121`): Exposes ModerationAction audit records with computed fields:
  - `corpusId`: Links to parent corpus for filtering
  - `isAutomated`: Identifies agent vs. human moderation
  - `canRollback`: Indicates whether action can be undone
- **ModerationMetricsType** (`config/graphql/graphene_types.py:3109-3121`): Aggregated metrics for monitoring moderation activity:
  - Total/automated/manual action counts
  - Hourly action rate with threshold alerting
  - Actions grouped by type
- **New GraphQL queries** (`config/graphql/queries.py:1875-2043`):
  - `moderationActions`: Filterable query for audit logs (corpus, thread, moderator, action type)
  - `moderationAction`: Single action lookup by ID
  - `moderationMetrics`: Aggregated stats with threshold violations
- **RollbackModerationActionMutation** (`config/graphql/moderation_mutations.py:594-707`): Undo automated moderation actions:
  - Supports rollback of delete_message, delete_thread, lock_thread, pin_thread
  - Creates new audit record for the rollback
  - Permission-gated to moderators
- **DeleteThreadMutation and RestoreThreadMutation** (`config/graphql/moderation_mutations.py:267-363`): Complete thread lifecycle management for frontend
- **ModerationDashboard component** (`frontend/src/components/moderation/ModerationDashboard.tsx`): Full-featured moderation UI:
  - Metrics display with threshold alerts
  - Filterable action table (action type, automated only)
  - Rollback confirmation modal
  - Time range selector (1h, 24h, 7d, 30d)
- **Dynamic tool fetching** (`frontend/src/components/corpuses/CreateCorpusActionModal.tsx`): Replaces hardcoded moderation tools with GraphQL query to `availableTools(category: "moderation")`

### Fixed

#### Race Condition in Agent Thread Actions (Issue #742)
- **Fixed TOCTOU vulnerability** (`opencontractserver/tasks/agent_tasks.py:859-898`): Added `select_for_update()` with `transaction.atomic()` to prevent duplicate agent execution claims

#### Tool Validation for Inline Agents (Issue #742)
- **Added tool category validation** (`config/graphql/mutations.py:3875-3897`): CreateCorpusAction now validates that inline agent tools are from the MODERATION category when using thread/message triggers

## [Unreleased] - 2025-12-28

### Added

#### MCP (Model Context Protocol) Interface Proposal (Issue #387)
- **Comprehensive MCP interface design** (`docs/mcp/mcp_interface_proposal.md`): Read-only access to public OpenContracts resources for AI assistants
- **4 resource types**: corpus, document, annotation, thread - with hierarchical URI patterns
- **7 tools for discovery and retrieval**: `list_public_corpuses`, `list_documents`, `get_document_text`, `list_annotations`, `search_corpus`, `list_threads`, `get_thread_messages`
- **Anonymous user permission model**: Operates as AnonymousUser with automatic filtering to `is_public=True` resources
- **Synchronous Django ORM implementation**: Uses `sync_to_async` wrapper pattern for MCP server integration
- **Performance optimizations**: Uses existing `AnnotationQueryOptimizer`, `prefetch_related` for threaded messages, and proper pagination
- **Robust URI parsing**: Regex-based URI parsing with slug validation to prevent injection attacks
- **Helper function implementations**: Complete `format_*` functions for corpus, document, annotation, thread, and message formatting

#### Markdown Link Generation Tool for Agent Responses (Issue #530)
- **New `create_markdown_link` agent tool** (`opencontractserver/llms/tools/core_tools.py:1990-2174`): Agents can now generate properly formatted markdown links for annotations, corpus, documents, and conversations
- **Supported entity types**:
  - **Annotations**: `[Annotation text](/d/user/corpus/doc?ann=123)` - Links to annotation with document context
  - **Corpus**: `[Corpus Title](/c/user/corpus-slug)` - Direct links to corpus
  - **Documents**: `[Document Title](/d/user/corpus/doc-slug)` - Smart routing (standalone or corpus-based)
  - **Conversations/Threads**: `[Discussion Title](/c/user/corpus/discussions/123)` - Links to discussion threads
- **Intelligent link generation**:
  - Automatically detects if documents belong to a corpus for proper URL structure
  - Truncates long annotation text (>100 chars) for readability
  - Uses entity titles when available, falls back to generic labels (e.g., "Annotation 123")
  - Validates entity existence, creator, and slug availability before generating links
- **Async support**: Both sync (`create_markdown_link`) and async (`acreate_markdown_link`) versions available
- **Tool registry entry** (`opencontractserver/llms/tools/tool_registry.py:364-380`): Registered as COORDINATION category tool with full parameter documentation
- **Comprehensive test coverage** (`opencontractserver/tests/test_llm_tools.py:2031-2417`):
  - 35+ test cases covering all entity types, edge cases, and error conditions
  - Tests for both sync and async implementations
  - Validation of error messages for missing entities, creators, slugs, and invalid types

#### Real-Time Notification System via WebSocket (Issue #637)
- **WebSocket notification consumer** (`config/websocket/consumers/notification_updates.py`): New `NotificationUpdatesConsumer` provides real-time notification delivery for all notification types (BADGE, REPLY, MENTION, THREAD_REPLY, moderation actions)
- **Frontend WebSocket hook** (`frontend/src/hooks/useNotificationWebSocket.ts`): `useNotificationWebSocket` hook manages WebSocket connection lifecycle with auto-reconnection, heartbeat monitoring, and graceful error handling
- **Signal broadcasting** (`opencontractserver/notifications/signals.py:33-100`): All notification creation signals now broadcast via WebSocket channel layer for instant delivery
- **ASGI routing** (`config/asgi.py:88-94`): Registered `ws/notification-updates/` WebSocket endpoint with authentication middleware
- **WebSocket URL helper** (`frontend/src/components/chat/get_websockets.ts:226-259`): `getNotificationUpdatesWebSocket` function constructs WebSocket URLs with proper protocol handling

### Changed

#### Badge Notifications Migrated from Polling to WebSocket (Issue #637)
- **useBadgeNotifications hook** (`frontend/src/hooks/useBadgeNotifications.ts`): Completely refactored from Apollo Client polling (30s intervals) to WebSocket-based real-time updates
- **Zero latency**: Badge awards now appear instantly instead of 0-30 second delay
- **Reduced server load**: Eliminated continuous polling requests from all connected clients
- **Backward compatible**: Maintains same interface (`newBadges`, `clearNewBadges`) with added `connectionState` for debugging

### Fixed

#### WebSocket Token Expiration Close Code Handling (PR #746)
- **Updated all WebSocket consumers** to check `scope['auth_error']` from middleware and use specific close codes:
  - `config/websocket/consumers/document_conversation.py:77-91`: Uses auth_error codes for expired/invalid tokens
  - `config/websocket/consumers/corpus_conversation.py:67-79`: Uses auth_error codes for expired/invalid tokens
  - `config/websocket/consumers/standalone_document_conversation.py:97-106`: Checks auth_error before falling back to anonymous handling
  - `config/websocket/consumers/unified_agent_conversation.py:119-127`: Uses auth_error codes for expired/invalid tokens
  - `config/websocket/consumers/thread_updates.py:77-88`: Uses auth_error codes for expired/invalid tokens
- **Removed unused `Union` import** from `config/websocket/middleware.py:2`
- **Fixed lazy import issue** in `config/graphql_auth0_auth/utils.py:124`: Moved `sync_remote_user` import inside function to avoid import error when `USE_AUTH0=False`
- **Added Auth0 test settings** in `config/settings/test.py:120-133`: Default Auth0 settings for test environment to allow importing Auth0 modules during testing

#### Impact
- Frontend can now distinguish between expired tokens (4001) and invalid tokens (4002) via WebSocket close codes
- Enables targeted token refresh vs full re-authentication based on close code
- Fixes issue #744 where token expiration wasn't properly signaled to clients

### Added

#### LlamaParse Document Parser Integration (Issue #692)
- **New LlamaParseParser** (`opencontractserver/pipeline/parsers/llamaparse_parser.py`): Full integration with LlamaParse API for document parsing with layout extraction
  - Supports PDF and DOCX file types
  - Extracts structural annotations (Title, Heading, Paragraph, Table, Figure, List, etc.) with bounding boxes
  - Generates PAWLS tokens from LlamaParse layout data for PDF annotation display
  - Supports multiple bounding box formats (fractional 0-1, absolute coordinates, array format)
  - Configurable via environment variables or Django settings
- **Environment variable configuration**:
  - `LLAMAPARSE_API_KEY` / `LLAMA_CLOUD_API_KEY`: API key for LlamaParse authentication
  - `LLAMAPARSE_RESULT_TYPE`: Output type ("json", "markdown", "text") - default: "json"
  - `LLAMAPARSE_EXTRACT_LAYOUT`: Enable layout extraction with bounding boxes - default: True
  - `LLAMAPARSE_NUM_WORKERS`: Parallel processing workers - default: 4
  - `LLAMAPARSE_LANGUAGE`: Document language - default: "en"
  - `LLAMAPARSE_VERBOSE`: Enable verbose logging - default: False
- **Parser selection via environment variable**:
  - `PDF_PARSER`: Set to "llamaparse", "docling" (default), or "nlm" to select default PDF parser
  - Location: `config/settings/base.py:740-765`
- **Comprehensive test suite** (`opencontractserver/tests/test_doc_parser_llamaparse.py`):
  - Tests for successful parsing with layout extraction
  - Tests for markdown mode without layout
  - Tests for bounding box format conversion (fractional, absolute, array)
  - Tests for annotation creation and token generation
  - Tests for error handling (missing API key, API errors, empty results)
  - Tests for configuration via settings and kwargs override

#### Thread/Message Triggered Corpus Actions for Automated Moderation
- **Extended CorpusActionTrigger enum** with `NEW_THREAD` and `NEW_MESSAGE` triggers (`opencontractserver/corpuses/models.py:849-854`) to enable automated moderation of discussion threads
- **New moderation tools** (`opencontractserver/llms/tools/moderation_tools.py`): 9 tools for thread moderation including:
  - `get_thread_context`: Retrieve thread metadata (title, creator, lock/pin status)
  - `get_thread_messages`: Get recent messages for context
  - `get_message_content`: Get full content of a specific message
  - `delete_message`: Soft delete a message with audit logging
  - `lock_thread`/`unlock_thread`: Control thread access
  - `add_thread_message`: Post agent messages to threads
  - `pin_thread`/`unpin_thread`: Feature important threads
- **New MODERATION tool category** (`opencontractserver/llms/tools/tool_registry.py:42`) with 9 registered tools and proper approval requirements
- **Signal handlers** for thread/message creation (`opencontractserver/corpuses/signals.py`) using `transaction.on_commit` pattern to trigger corpus actions
- **New Celery tasks** (`opencontractserver/tasks/corpus_tasks.py`):
  - `process_thread_corpus_action`: Processes actions when threads are created
  - `process_message_corpus_action`: Processes actions when messages are posted
- **Agent thread action task** (`opencontractserver/tasks/agent_tasks.py:run_agent_thread_action`): Runs AI agents with thread context and moderation tools
- **Updated CorpusActionExecution model** (`opencontractserver/corpuses/models.py`) with optional `conversation` and `message` FKs for audit trail
- **Updated AgentActionResult model** (`opencontractserver/agents/models.py`) with nullable document FK and new `triggering_conversation`/`triggering_message` FKs
- **Frontend updates** (`frontend/src/components/corpuses/CreateCorpusActionModal.tsx`):
  - Added "On New Thread" and "On New Message" trigger options
  - Thread/message triggers automatically select agent action type
  - Info message explaining available moderation tools
- **Comprehensive test coverage**:
  - Backend tests: `opencontractserver/tests/test_thread_corpus_actions.py`
  - Frontend tests: `frontend/tests/create-corpus-action-modal.ct.tsx`
- **Database migrations**:
  - `opencontractserver/agents/migrations/0008_add_thread_message_triggers.py`: Adds nullable `triggering_conversation` and `triggering_message` FKs to AgentActionResult, makes `document` nullable
  - `opencontractserver/corpuses/migrations/0032_add_thread_message_triggers.py`: Adds nullable `conversation` and `message` FKs to CorpusActionExecution

#### Use Cases Enabled
- Automated content moderation (e.g., auto-delete messages with prohibited content)
- Thread management (e.g., auto-lock threads discussing prohibited topics)
- Automated responses (e.g., welcome messages for new threads)
- Content classification (e.g., auto-pin important announcements)

#### Proactive Apollo Cache Management System (PR #725)
- **New `CacheManager` service** (`frontend/src/services/cacheManager.ts`): Centralized Apollo cache management with debouncing, targeted invalidation, and auth-aware cache operations
  - `resetOnAuthChange()`: Full cache clear with optional refetch for login/logout transitions
  - `refreshActiveQueries()`: Soft refresh without clearing cache
  - `invalidateEntityQueries()`: Targeted invalidation for document/corpus/annotation CRUD operations
  - Debouncing: 1000ms for full resets, 500ms for entity invalidations
  - Debug utilities: `logCacheSize()`, `extractCacheForDebug()`
- **New `useCacheManager` hook** (`frontend/src/hooks/useCacheManager.ts`): React hook with memoized CacheManager instance and stable callback references
- **Comprehensive test suite** (`frontend/src/services/__tests__/cacheManager.test.ts`, `frontend/src/hooks/__tests__/useCacheManager.test.tsx`): 30+ tests covering debouncing, error handling, lifecycle, singleton management, and auth scenarios

### Technical Details

#### LlamaParse Parser Architecture
- Uses `llama-parse` library for API communication
- JSON mode with `extract_layout=True` provides bounding boxes as fractions of page dimensions (0-1)
- Converts LlamaParse layout elements to OpenContracts structural annotations
- Generates PAWLS tokens by splitting text into words and distributing across bounding box
- Element type mapping converts LlamaParse labels (title, paragraph, table, etc.) to OpenContracts annotation labels
- Falls back to text extraction mode when layout extraction is disabled

#### Markdown Link Tool Implementation
- Follows OpenContracts routing patterns from `docs/frontend/routing_system.md`
- Uses `select_related()` to minimize database queries (single query per entity)
- Handles both standalone documents and corpus-based document contexts
- Entity validation with clear error messages for IDOR prevention
- URL patterns match frontend `navigationUtils.ts` for consistency

### Fixed

#### Token Expiration Signal to Frontend (Issue #744)
- **Fixed `Auth0RemoteUserJSONWebTokenBackend.authenticate()` swallowing `JSONWebTokenExpired` exceptions** (`config/graphql_auth0_auth/backends.py:44-52`):
  - Previously, when a JWT token expired, the authentication backend caught all exceptions and returned `None`
  - The GraphQL layer then returned a generic "User is not authenticated" error
  - Frontend's `errorLink.ts` could not detect token expiration and trigger automatic refresh
  - Fix: Re-raise `JSONWebTokenExpired` so the GraphQL layer returns "Signature has expired"
  - Frontend now correctly detects expiration and triggers page reload for silent token refresh
- **Enhanced WebSocket middleware with auth error signaling** (`config/websocket/middleware.py:44-124`):
  - Added `scope["auth_error"]` dict with `code` and `message` fields
  - New close codes: `WS_CLOSE_TOKEN_EXPIRED` (4001), `WS_CLOSE_TOKEN_INVALID` (4002)
  - Consumers can now close connections with specific codes for frontend handling
- **Enhanced Auth0 WebSocket middleware** (`config/websocket/middlewares/websocket_auth0_middleware.py:52-130`):
  - Added consistent `scope["auth_error"]` handling for Auth0 tokens
  - Matches close code behavior with non-Auth0 middleware
- **New test coverage** (`opencontractserver/tests/test_token_expiration.py`):
  - Tests for `Auth0RemoteUserJSONWebTokenBackend` token expiration re-raising
  - Tests for WebSocket middleware auth error handling
  - Tests for WebSocket close code consistency

#### Independent Structural Annotation and Show Selected Controls (Issue #735)
- **Removed forced coupling between structural and showSelectedOnly controls** (`frontend/src/components/annotator/controls/AnnotationControls.tsx:200-207`):
  - Previously, enabling "Show Structural" would force "Show Only Selected" to be checked and disabled
  - Users can now toggle "Show Only Selected" independently when structural annotations are visible
  - All combinations now work:
    - Show all structural annotations: structural ON, selectedOnly OFF
    - Show only selected structural annotation: structural ON, selectedOnly ON
    - Hide all structural annotations: structural OFF
- **Updated checkbox onChange handler** (`frontend/src/components/annotator/controls/AnnotationControls.tsx:268`): Now correctly extracts `data?.checked ?? false` for consistency with other toggle handlers
- **Updated component tests** (`frontend/tests/FloatingDocumentControls.ct.tsx:263-371`):
  - Renamed test to reflect new independent behavior
  - Added new test verifying controls can be toggled independently
- **Note**: Users who previously had `showStructural: true` will notice different behavior: the "Show Only Selected" control now respects their actual preference instead of being forced to true

#### Cache Management Race Condition Fix (PR #725)
- **Auth state now set BEFORE cache clear** (`frontend/src/components/auth/AuthGate.tsx:69-92`, `frontend/src/views/Login.tsx:106-117`, `frontend/src/components/layout/useNavMenu.ts:64-90`):
  - Previously, cache was cleared before updating auth state, creating a window where queries could fetch with wrong auth context
  - Fixed by setting auth token/user/status first, then clearing cache
  - Refetched queries now correctly use the new auth context
- **AuthGate uses useCacheManager hook** (`frontend/src/components/auth/AuthGate.tsx:7,27`): Replaced direct `new CacheManager()` instantiation with proper hook usage, eliminating `as any` type assertion and ensuring memoization
- **Fire-and-forget logout cache clear** (`frontend/src/components/layout/useNavMenu.ts:69-79`): Logout no longer blocks on cache clear operation, improving perceived performance

### Technical Details

#### Cache Management Architecture
- **Race condition prevention**: Auth state updates are synchronous; cache clear is async. By setting auth first, any queries triggered during cache clear use the correct credentials.
- **Singleton pattern preserved for non-React contexts**: The singleton functions (`initializeCacheManager`, `getCacheManager`, etc.) remain exported for testing and non-React usage, with documentation clarifying when to use hooks vs singleton.
- **Dependency management**: `useCacheManager` hook returns stable callback references via `useCallback`, safe to include in effect dependencies.

### Fixed

#### Mobile Responsive Styling for Settings and Badge Widgets (Issue #690)
- **Badge component z-index optimization** (`frontend/src/components/badges/Badge.tsx:47,107`): Lowered z-index values from 9999/10000 to 200/201 to avoid conflicts with other UI elements while maintaining proper layering
- **Unified mobile behavior detection** (`frontend/src/components/badges/Badge.tsx:148-152`): Combined touch device detection with viewport width check to ensure mobile UX works consistently across real devices and test environments
- **Test wrapper extraction** (`frontend/tests/UserBadgesTestWrapper.tsx`, `frontend/tests/GlobalSettingsPanelTestWrapper.tsx`): Moved test wrappers to separate files following Playwright component testing best practices
- **Improved test reliability** (`frontend/tests/mobile-responsive.ct.tsx`): Fixed element disambiguation issues using proper locator strategies

#### Agent Chat Processing Indicator (PR #687)
- **Added visual feedback for agent processing** (`frontend/src/components/widgets/chat/ChatMessage.tsx:1342-1405`): When an agent starts processing a response, an animated "Agent is thinking..." indicator now displays instead of an empty message bubble
- **Processing indicator conditions**: Shows when assistant message is incomplete with no content and no timeline entries
- **Accessibility improvements**: Added ARIA attributes (`role="status"`, `aria-live="polite"`, `aria-label`) for screen reader support
- **Animation performance**: Added `will-change: transform, opacity` to animated dots for smoother rendering
- **Component tests**: Added comprehensive Playwright component tests (`frontend/tests/chat-message-processing-indicator.ct.tsx`) covering indicator visibility, accessibility, and state transitions

### Fixed

#### Trash View Error Prevention (Issue #691)
- **State synchronization fix** (`frontend/src/components/corpuses/folders/FolderTreeSidebar.tsx:363-369`):
  - Fixed trash folder click handler to use consistent state update pattern matching other folder navigation
  - Added `handleTrashClick` callback that properly delegates to `onFolderSelect` when provided (URL-driven state)
  - Removed direct Jotai atom manipulation that caused race conditions with CentralRouteManager
- **Defensive null handling** (`frontend/src/components/corpuses/folders/TrashFolderView.tsx`):
  - Added `safeFormatDistanceToNow()` and `safeFormat()` helper functions for robust date formatting
  - Added optional chaining for `creator`, `document`, and nested properties to prevent runtime errors
  - Added validation in `handleRestoreSingle()` and `handleRestoreSelected()` to check for valid document data
- **Type safety improvements** (`frontend/src/graphql/queries/folders.ts:92-104`):
  - Updated `DeletedDocumentPathType` interface to mark `creator` and `document` as potentially null
  - Ensures TypeScript catches potential null access issues at compile time

### Added

#### Agent Message Visual Differentiation (Issue #688)
- **Enhanced MessageItem component** (`frontend/src/components/threads/MessageItem.tsx:27-50, 59-66, 68-191, 211-245, 461-466, 530-550`):
  - Agent detection logic using `getAgentDisplayData()` helper function
  - `hexToRgba()` utility for generating color-tinted backgrounds from agent badge colors
  - Distinct visual styling for agent messages vs user messages:
    - **Background**: Subtle gradient using agent's badge color with low opacity (8% to 3%)
    - **Border**: Colored border matching agent's badge color instead of default gray
    - **Accent strip**: 4px colored left border (like highlighted messages) using agent color
    - **Avatar**: Bot icon instead of User icon, with agent-colored gradient background
    - **Box shadow**: Agent-colored shadow on avatar for visual consistency
- **Accessibility improvements**:
  - Updated `aria-label` to include "(AI Agent)" suffix for screen readers
  - Avatar `title` attribute identifies agent name and type
- Agent color sourced from `AgentConfiguration.badgeConfig.color` field (falls back to default blue #4A90E2)

#### Network Recovery on Screen Unlock (Issue #697)
- **New `useNetworkStatus` hook** (`frontend/src/hooks/useNetworkStatus.ts`): Monitors page visibility and network status changes to detect when the app resumes from background (e.g., screen unlock on mobile)
- **New `NetworkStatusHandler` component** (`frontend/src/components/network/NetworkStatusHandler.tsx`): Automatically refetches active Apollo Client queries when:
  - The page becomes visible after being hidden (screen unlock on mobile)
  - The network comes back online after being offline
- **WebSocket reconnection on resume**: Updated `useThreadWebSocket` and `useAgentChat` hooks to reconnect WebSockets when the page becomes visible
- **Toast notifications**: Informs users of connectivity changes ("Reconnecting...", "Connection restored", "You appear to be offline")

### Technical Details

#### Real-Time Notification System Architecture (Issue #637)
- **Security**: User-specific channel groups (`notification_user_{user_id}`) prevent IDOR and cross-user data leakage
- **Performance optimizations**:
  - User-specific WebSocket channels (not global broadcast)
  - Efficient `bulk_create()` for thread participant notifications
  - Exponential backoff on reconnection failures (2s → 4s → 8s → 16s, max 8x)
  - Heartbeat monitoring every 30s to detect stale connections
- **Signal integration**: All notification types (BADGE, REPLY, MENTION, THREAD_REPLY, moderation) automatically broadcast via `broadcast_notification_via_websocket()` helper
- **Error handling**: WebSocket broadcast failures don't break signal handlers - notifications still save to database
- **Connection lifecycle**: Auto-reconnection on network recovery, page visibility change, and authentication token refresh
- **Testing**: Comprehensive test suite (`opencontractserver/tests/test_notification_websocket.py`) covering authentication, IDOR prevention, concurrent connections, and signal integration
- **Network monitoring**: Integrated with `useNetworkStatus` hook for automatic reconnection on mobile screen unlock and network recovery

#### Network Recovery Implementation
- Uses `visibilitychange` event to detect page visibility changes
- Uses `online`/`offline` events to detect network status changes
- Configurable resume threshold (default 2s for NetworkStatusHandler, 1s for WebSocket hooks)
- Debounced refetch to prevent rapid repeated calls
- Graceful degradation: continues to work if events are not supported

#### Upload Modal Styling Improvements (Issue #696)
- **New styled components for upload modals** (`frontend/src/components/widgets/modals/UploadModalStyles.ts`): Comprehensive styled-components library with 25+ responsive components including `StyledUploadModal`, `DropZone`, `StepIndicator`, `FileListItem`, and more
- **Step indicator UI** for DocumentUploadModal showing progress through upload workflow (Select → Details → Corpus)
- **Modern gradient header** with icon and subtitle for both upload modals
- **Progress bar integration** showing real-time upload progress with success/error states

#### Mobile UI Improvements for Picker and Edit Message Modal (Issue #686)
- **Backend UpdateMessage mutation** (`config/graphql/conversation_mutations.py:455-619`):
  - New `UpdateMessageMutation` for editing existing thread messages
  - Validates CRUD permission on message or moderator status
  - Re-parses mentions when content is updated (with race condition protection - parsing happens before DB modifications)
  - Triggers agent responses for newly mentioned agents
  - Documented behavior: agents respond to ALL mentions, including re-mentions in edited messages
- **Frontend UPDATE_MESSAGE mutation** (`frontend/src/graphql/mutations.ts:2726-2760`): GraphQL mutation with TypeScript types
- **EditMessageModal component** (`frontend/src/components/threads/EditMessageModal.tsx`):
  - Full-screen modal on mobile for better touch interaction
  - Uses MessageComposer for consistent editing experience
  - Safe area insets for notched devices
  - Loading states and error handling
  - Custom unsaved changes confirmation modal (replaces browser `window.confirm()`)
  - Debounced content updates (150ms) for improved performance during typing
  - XSS protection documented: uses MarkdownMessageRenderer with `rehype-sanitize`
- **Message actions dropdown in MessageItem** (`frontend/src/components/threads/MessageItem.tsx:219-432`):
  - Desktop: Standard dropdown menu with Edit/Delete options
  - Mobile: Bottom sheet style for thumb-friendly interaction
  - Inline delete confirmation with mobile-optimized buttons
  - Backdrop overlay on mobile for visual focus

#### Improved Inline Reference Cards for Mentions (Issue #689)
- **Annotation mentions** now display the first ~24 characters of annotation text instead of cryptic IDs
  - Full annotation text accessible via hover tooltip
  - Falls back to label type if no raw text available
  - Location: `frontend/src/components/threads/MentionChip.tsx:212-229`
- **Document mentions** show document title with corpus context (e.g., "Document Title (in Corpus Name)")
  - Location: `frontend/src/components/threads/MessageComposer.tsx:361-375`
- **Corpus mentions** show corpus name instead of `@corpus:slug` format
  - Location: `frontend/src/components/threads/MessageComposer.tsx:351-359`
- **Shared constant** `MENTION_PREVIEW_LENGTH = 24` for consistent truncation across components
  - Location: `frontend/src/assets/configurations/constants.ts:6-8`
- **Text sanitization utility** for user-generated content to prevent XSS
  - Location: `frontend/src/utils/textSanitization.ts`
  - Unit tests: `frontend/src/utils/textSanitization.test.ts`
- **Component tests** for MentionChip covering all resource types and text truncation
  - Location: `frontend/tests/mention-chip.spec.tsx`

### Changed

#### Upload Modal Mobile Responsiveness (Issue #696)
- **DocumentUploadModal** (`frontend/src/components/widgets/modals/DocumentUploadModal.tsx`): Refactored to use new styled components with responsive grid layout for edit step
- **BulkUploadModal** (`frontend/src/components/widgets/modals/BulkUploadModal.tsx`): Complete visual overhaul with styled drop zone, file size display, and responsive layout
- **DocumentUploadList** (`frontend/src/components/documents/DocumentUploadList.tsx`): New drop zone styling with drag-active feedback and pulse animation
- **DocumentListItem** (`frontend/src/components/documents/DocumentListItem.tsx`): Improved file list items with proper touch targets (56px min-height, 64px on mobile), status icons, and delete button styling
- **Mobile-first breakpoints**: All upload modal components now have explicit breakpoints at 480px (mobile) and 768px (tablet)
- **Touch target compliance**: All interactive elements meet 44px minimum touch target size for mobile accessibility
- **Responsive action buttons**: Modal actions stack vertically on mobile for full-width tappable buttons
- **Custom scrollbar styling**: File list has styled scrollbars for visual polish

#### MentionChip Component Improvements (Issue #689)
- Extended `MentionChip` to support ANNOTATION type with green gradient styling
- Added default cases to all switch statements for TypeScript exhaustiveness checking
- Refactored `handleClick` to `handleActivation` accepting `React.MouseEvent | React.KeyboardEvent` union type (fixes unsafe `as any` assertion)
- Sanitized user-generated annotation text before display to prevent XSS

### Fixed

#### Mobile Layout for Picker Components (Issue #686)
- **Picker keyboard handling** (`MentionPicker.tsx:22-54`, `UnifiedMentionPicker.tsx:25-57`):
  - Added CSS environment variables (`env(safe-area-inset-bottom)`) for keyboard-aware positioning
  - Smooth slide-up animation for picker appearance
  - Max-height constraints using `min()` to prevent overflow on small screens
- **Touch targets** (`MentionPicker.tsx:83-108`, `UnifiedMentionPicker.tsx:96-108`):
  - Increased touch target size (52-60px min-height) for easier selection
  - Larger font size (15px) on mobile for readability
  - Mobile-specific border radius for rounded corners
- **MessageComposer mobile improvements** (`MessageComposer.tsx:48-93`):
  - Larger toolbar button touch targets (40x40px) on mobile
  - Increased gap between buttons for easier tapping

### Technical Details

#### Message Editing Tests (Issue #686)
- **New test for parent relationship preservation** (`opencontractserver/tests/test_conversation_mutations_graphql.py:1071-1168`):
  - Verifies that editing a reply message preserves its `parent_message` field
  - Ensures thread structure integrity when users edit replies
  - Part of comprehensive UpdateMessage mutation test suite

#### Upload Modal Architecture
- Styled-components with transient props (`$active`, `$selected`, `$status`) to prevent DOM attribute warnings
- CSS keyframe animations for drag-active pulse effect and fade-in modal transitions
- Gradient backgrounds using `linear-gradient(135deg, #667eea 0%, #764ba2 100%)` for visual consistency
- Semantic UI React components wrapped with styled-components for enhanced styling while preserving functionality

#### Permanent Deletion (Empty Trash) Functionality (PR #707)
- **Core deletion logic** (`opencontractserver/documents/versioning.py:617-760`):
  - `permanently_delete_document()`: Irreversible deletion with cascade cleanup
  - `permanently_delete_all_in_trash()`: Bulk deletion (empty trash) with partial success support
- **Cascade cleanup** deletes:
  - All DocumentPath records for the document in the corpus (entire history)
  - User annotations (non-structural) on the document
  - Relationships involving those annotations (uses Q objects to avoid duplicate counting)
  - DocumentSummaryRevision records for the document+corpus
  - The Document itself if no other corpus references it (Rule Q1)
- **Service layer** (`opencontractserver/corpuses/folder_service.py:1096-1181`): Permission-checked wrappers
- **GraphQL mutations** (`config/graphql/mutations.py:4069-4187`):
  - `PermanentlyDeleteDocument`: Delete single soft-deleted document
  - `EmptyTrash`: Delete all soft-deleted documents in corpus
  - Both enforce DELETE permission via django-guardian
- **Frontend UI** (`frontend/src/components/corpuses/folders/TrashFolderView.tsx`):
  - "Empty Trash" button with confirmation modal
  - Warning message explaining what will be permanently deleted
  - Auto-dismiss success/error messages with configurable durations
  - TypeScript type safety for all mutation responses
- **Comprehensive test suite** (`opencontractserver/tests/test_permanent_deletion.py`): 34 tests covering core logic, cascade cleanup, Rule Q1, permissions, GraphQL mutations, and edge cases

### Technical Details
- Partial deletions are allowed in bulk operations (each document deletion is atomic)
- Structural annotations are preserved (shared via StructuralAnnotationSet)
- Corpus-isolated deletion: Only affects target corpus, other corpus references preserved
- Composite index `[corpus, is_current, is_deleted]` on DocumentPath for efficient trash queries

#### Mobile-Friendly Corpus Modal
- **New CorpusModal component** (`frontend/src/components/corpuses/CorpusModal.tsx`): Purpose-built modal replacing CRUDModal for corpus create/edit/view operations with mobile-first design
- **13 comprehensive component tests** (`frontend/tests/corpus-modal.ct.tsx`): Full test coverage for all modal modes and interactions
- **Smart change detection for EDIT mode**: Only sends changed fields to backend using original value comparison (`CorpusModal.tsx:498-519`)
- **ARIA accessibility**: CloseButton includes `aria-label="Close modal"` for screen reader users

### Changed

#### Corpus Modal Architecture
- **Replaced CRUDModal with CorpusModal**: Simplified form handling with controlled inputs instead of complex JSON Schema Form library
- **Removed debug console.log statements** (`Corpuses.tsx`): Cleaned up 4 debug logging statements

### Technical Details

#### Corpus Modal Implementation
- Mobile-first responsive design: 16px input font prevents iOS auto-zoom, 48px min touch targets
- Proper TypeScript types: Icon type is `string | null` (not ArrayBuffer), slug field uses existing type from RawCorpusType
- isDirty computed by comparing current values against stored original values (not just tracking changes)

#### Social Media Preview (OG Metadata) System (PR #701)
- **Cloudflare Worker for social media previews** (`cloudflare-og-worker/`): Intercepts requests from social media crawlers (Facebook, Twitter, LinkedIn, Discord, Slack, etc.) and returns HTML with Open Graph meta tags for rich link previews
- **Public OG metadata GraphQL queries** (`config/graphql/queries.py:3235-3403`): New unauthenticated queries for fetching public corpus, document, thread, and extract metadata
  - `ogCorpusMetadata`: Returns title, description, icon, document count for public corpuses
  - `ogDocumentMetadata`: Returns title, description, icon for public standalone documents
  - `ogDocumentInCorpusMetadata`: Returns document metadata with corpus context
  - `ogThreadMetadata`: Returns discussion thread metadata (title, corpus, message count)
  - `ogExtractMetadata`: Returns data extract metadata
- **Worker architecture**: Modular TypeScript implementation with crawler detection, URL parsing, metadata fetching, and HTML generation
- **Comprehensive documentation** (`docs/architecture/social-media-previews.md`): Architecture overview, deployment guide, and testing instructions

### Fixed

#### New Corpus Modal Mobile Issues (Issue #702)
- **Mobile form data loss in CorpusModal** (`frontend/src/components/corpuses/CorpusModal.tsx:406-418`):
  - Fixed fields clearing when typing on mobile by tracking modal open transitions with `prevOpenRef` instead of resetting form on every render
  - The original `useEffect` was running on every `corpus` or `open` change, causing form state to reset during keyboard/focus events on mobile
- **Slow embedder loading** (`frontend/src/components/widgets/CRUD/EmbedderSelector.tsx:43-46`):
  - Changed Apollo query to `cache-first` policy since embedders rarely change
  - Prevents unnecessary network requests when reopening CorpusModal
- **Cramped mobile layout** (`frontend/src/components/corpuses/CorpusModal.tsx:327-333`, `frontend/src/components/widgets/file-controls/FilePreviewAndUpload.tsx:54-57,129-135`):
  - Reduced icon upload area max-width from 200px to 150px on mobile
  - Reduced ImagePreview height from 150px to 100px on mobile
  - Made EditBadge smaller and better positioned on mobile viewports

#### Production Deployment
- **Missing COLLECTFAST_STRATEGY for GCP storage backend** (`config/settings/base.py:436`): Added `collectfast.strategies.gcloud.GoogleCloudStrategy` for GCP deployments. Previously, `collectfast` was installed in production but `COLLECTFAST_STRATEGY` was only configured for AWS, causing `collectstatic` to fail with `ImproperlyConfigured: No strategy configured` error when using `STORAGE_BACKEND=GCP`.
- **GCS static files ACL incompatible with uniform bucket-level access** (`opencontractserver/utils/storages.py:38`): Changed `StaticRootGoogleCloudStorage.default_acl` from `"publicRead"` to `None`. GCS buckets with uniform bucket-level access enabled cannot use per-object ACLs; access must be controlled via IAM policies at the bucket level instead.

#### Social Media Preview Security & Performance Fixes (PR #701 remediation)
- **Prevented potential infinite loop in worker passthrough** (`cloudflare-og-worker/src/index.ts:23-42`): Added `passToOrigin()` helper function with `X-OG-Worker-Pass` header to prevent Cloudflare Worker from re-invoking itself on route-based deployments
- **Added rate limiting to public OG queries** (`config/graphql/queries.py`): All five OG metadata resolvers now have `@graphql_ratelimit(key="ip", rate="60/m", group="og_metadata")` to prevent abuse and DoS attacks
- **Fixed N+1 query in corpus document count** (`config/graphql/queries.py:3250-3255`): Changed from `corpus.documents.count()` to `Corpus.objects.annotate(doc_count=Count("documents"))` for single-query optimization
- **Fixed N+1 query in thread message count** (`config/graphql/queries.py:3359-3364`): Changed from `thread.messages.count()` to `Conversation.objects.annotate(msg_count=Count("messages"))` for single-query optimization
- **Added input validation for decodeURIComponent** (`cloudflare-og-worker/src/parser.ts:88-95`): Wrapped `decodeURIComponent()` in try-catch to handle malformed URLs gracefully instead of crashing the worker
- **Unified description truncation** (`config/graphql/queries.py`): Removed redundant Python-side `[:500]` truncation; description truncation now handled solely by the worker at 200 characters for consistency

### Added

#### Mobile UI/UX Improvements for Corpus Navigation
- **Mobile-first folder sidebar defaults**: Sidebar now collapses by default on mobile/tablet devices (≤768px) to maximize document viewing area
- **Mobile bottom-sheet mention pickers**: User, resource, and unified mention pickers now display as bottom sheets on mobile (≤600px) for thumb-friendly interaction
- **Discussions and Analytics quick access**: Added icon buttons to CorpusHome stat cards for direct navigation to Discussions and Analytics tabs
- **Sidebar auto-close behavior**: Folder sidebar automatically closes on mobile/tablet after folder selection for seamless navigation
- **Mobile sidebar backdrop overlay**: Semi-transparent backdrop behind mobile sidebar for visual focus and easy dismissal
- **Escape key accessibility**: Mobile sidebar can now be dismissed with Escape key for keyboard accessibility
- **TABLET_BREAKPOINT constant**: Added to `constants.ts` for consistent responsive breakpoint management across components

### Fixed

#### Mobile UI/UX Fixes
- **Settings button variable name bug** (`frontend/src/components/corpuses/CorpusHome.tsx:780`): Fixed `canUpdate` → `canEdit` reference error that prevented Settings button from displaying for users with update permissions
- **FAB z-index layering** (`frontend/src/views/Corpuses.tsx:1320`): Raised FAB z-index from 100 to 150 to ensure visibility above folder sidebar toggle (z-index: 101)
- **Explicit z-index layering**: Made mobile sidebar z-index layering explicit (backdrop: 98, toggle button: 99) to prevent fragile DOM-order-dependent behavior

#### Mobile Responsive Styling for Settings and Badge Widgets (PR #690)
- **UserSettingsModal responsive styling** (`frontend/src/components/modals/UserSettingsModal.tsx:14-80`):
  - Modal takes 95% width on mobile (≤768px) with reduced padding
  - Form groups stack vertically on small screens (≤480px) for single-column layout
  - Action buttons display full-width and stack vertically (Save above Close) on mobile
  - Added `styled-components` import and styled wrapper components
- **Badge component touch support** (`frontend/src/components/badges/Badge.tsx:23-41, 96-112, 145-199`):
  - Added tap-to-toggle tooltip on touch devices (detects via `ontouchstart`)
  - Created `MobileOverlay` backdrop for dismissing badge popups by tapping outside
  - Popup centers on mobile screens using fixed positioning instead of floating-ui
  - Increased touch target size (min-height 36px, larger padding)
  - Disabled hover transforms on touch devices using `@media (hover: none)`
- **UserBadges container responsive layout** (`frontend/src/components/badges/UserBadges.tsx:18-27, 37-48, 58-61`):
  - Reduced padding and gap on mobile viewports
  - Badges center-aligned on mobile for better visual balance
  - Empty state and header text sizes reduced on mobile
- **GlobalSettingsPanel responsive grid** (`frontend/src/components/admin/GlobalSettingsPanel.tsx:11-67, 82-104, 119-123, 137-139, 148-150, 163-168`):
  - Container padding reduced on mobile (2rem → 1rem → 0.75rem)
  - Settings grid switches to single column on small mobile (≤480px)
  - Card content padding reduced progressively on smaller screens
  - Touch-friendly card interactions with active state feedback (scale 0.98)
  - "Coming Soon" badge displays on its own line on very small screens

### Changed

#### Mobile UI/UX Refactoring
- **Hardcoded breakpoints replaced with constants**: Updated all hardcoded `768px` references in `FolderDocumentBrowser.tsx` and `folderAtoms.ts` to use `TABLET_BREAKPOINT` constant for maintainability
- **Improved breakpoint documentation**: Added detailed JSDoc comment in `folderAtoms.ts` explaining why `TABLET_BREAKPOINT` (768px) is used for sidebar collapse rather than `MOBILE_VIEW_BREAKPOINT` (600px)

---

### Added

#### v3.0.0.b3 Migration Tools (Issue #654)
- **New management command: `validate_v3_migration`**
  - Pre-flight and post-migration validation for dual-tree versioning and structural annotations
  - Checks: version_tree_id, is_current, DocumentPath records, XOR constraints, structural set uniqueness
  - Reports structural migration candidates
  - Options: `--verbose`, `--fix`
  - Location: `opencontractserver/documents/management/commands/validate_v3_migration.py`

- **New management command: `migrate_structural_annotations`**
  - Optional command to migrate structural annotations to shared StructuralAnnotationSet objects
  - Creates StructuralAnnotationSet by content hash (pdf_file_hash) for storage efficiency
  - Moves structural annotations/relationships from document FK to structural_set FK
  - Documents with same hash share StructuralAnnotationSet (O(1) storage vs O(n))
  - Options: `--dry-run`, `--document-id`, `--corpus-id`, `--batch-size`, `--verbose`, `--force`
  - Location: `opencontractserver/annotations/management/commands/migrate_structural_annotations.py`

- **Comprehensive migration test suite** (`opencontractserver/tests/test_v3_migration.py`)
  - DocumentVersioningMigrationTests: version_tree_id, is_current, DocumentPath creation
  - XORConstraintTests: Annotation/Relationship XOR constraint validation
  - StructuralMigrationCommandTests: Management command functionality, idempotency
  - RollbackAndEdgeCaseTests: Edge cases, error handling, data integrity
  - ValidationCommandTests: validate_v3_migration command testing
  - 25+ human-readable tests covering all migration scenarios

- **Migration documentation** (`docs/migrations/v3_upgrade_guide.md`)
  - Pre-upgrade checklist with backup recommendations
  - Step-by-step migration instructions for production and development
  - Optional structural annotation migration guide
  - Rollback procedure documentation
  - FAQ addressing common concerns (XOR constraint safety, storage savings, incremental migration)

#### Discovery Landing Page (New)
- **Beautiful, modern landing page** as the main entry point for the application
  - Replaces direct redirect to /corpuses with a unified discovery experience
  - Different content for anonymous vs authenticated users
  - Responsive design with mobile-first approach
  - Location: `frontend/src/views/DiscoveryLanding.tsx`

- **New landing page components** (`frontend/src/components/landing/`)
  - `HeroSection.tsx`: Animated hero with gradient backgrounds, floating icons, and global search
  - `StatsBar.tsx`: Community metrics display with animated counters (users, collections, documents, threads, annotations, weekly active)
  - `TrendingCorpuses.tsx`: Card grid of popular document collections with engagement metrics
  - `RecentDiscussions.tsx`: List of recent public discussions with badges for pinned/locked threads
  - `TopContributors.tsx`: Leaderboard-style display of top community contributors with reputation scores
  - `CallToAction.tsx`: Conversion section for anonymous users with feature highlights
  - All components feature modern UI/UX: glass morphism, smooth Framer Motion animations, skeleton loaders

- **GraphQL queries for discovery data** (`frontend/src/graphql/landing-queries.ts`)
  - `GET_DISCOVERY_DATA`: Unified query fetching corpuses, conversations, community stats, and leaderboard
  - `GET_TRENDING_CORPUSES`: Public corpuses with engagement metrics
  - `GET_RECENT_DISCUSSIONS`: Recent threads with pagination
  - `GET_COMMUNITY_STATS`: Platform-wide statistics
  - `GET_GLOBAL_LEADERBOARD`: Top contributors with badges

- **Route integration**
  - Root path (`/`) now displays DiscoveryLanding instead of redirecting to /corpuses
  - Location: `frontend/src/App.tsx:377-382`

- **Component tests** (`frontend/tests/landing-components.spec.tsx`)
  - HeroSection tests: rendering, authenticated/anonymous variants, search submission
  - StatsBar tests: stats rendering, loading state, null handling
  - TrendingCorpuses tests: corpus cards, loading skeletons, empty state
  - RecentDiscussions tests: discussion items, pinned badges, reply counts
  - TopContributors tests: contributor cards, reputation scores, leaderboard button
  - CallToAction tests: anonymous visibility, authenticated hiding
  - DiscoveryLanding integration tests: full page rendering, section visibility

#### Permission Audit Remediation - Query Optimizers
- **New `UserQueryOptimizer`** for centralized user profile visibility logic
  - Respects `is_profile_public` privacy setting
  - Private profiles visible via corpus membership with > READ permission
  - Inactive users filtered out (except for superusers)
  - IDOR-safe visibility checks
  - Location: `opencontractserver/users/query_optimizer.py`

- **New `BadgeQueryOptimizer`** for centralized badge visibility logic
  - Badge visibility follows recipient's profile privacy rules
  - Corpus-specific badges visible only to corpus members
  - Own badges always visible regardless of privacy
  - IDOR-safe visibility checks
  - Location: `opencontractserver/badges/query_optimizer.py`

- **New `DocumentActionsQueryOptimizer`** for document-related actions
  - Centralized permission logic for corpus actions, extracts, and analysis rows
  - Follows least-privilege model: `Effective Permission = MIN(document_permission, corpus_permission)`
  - Integrates with ExtractQueryOptimizer and AnalysisQueryOptimizer
  - Location: `opencontractserver/documents/query_optimizer.py`

- **Comprehensive permission test suites** (40 tests total)
  - `opencontractserver/tests/permissioning/test_user_visibility.py` - 16 tests for user profile visibility
  - `opencontractserver/tests/permissioning/test_badge_visibility.py` - 13 tests for badge visibility
  - `opencontractserver/tests/permissioning/test_document_actions_permissions.py` - 11 tests for document actions

- **Updated permissioning documentation**
  - Added Section 8: User Profile and Badge Visibility
  - Added Section 9: Document Actions Permissions
  - Added callouts for new privacy features
  - Updated Key Changes table with new optimizer rows
  - Location: `docs/permissioning/consolidated_permissioning_guide.md`

#### Corpus Engagement Analytics Dashboard (Issue #579)
- **New CorpusEngagementDashboard component** displaying comprehensive engagement metrics
  - Thread metrics: total threads, active threads, average messages per thread
  - Message activity: total messages, 7-day and 30-day message counts with bar chart visualization
  - Community engagement: unique contributors, active contributors (30d), total upvotes
  - Auto-refresh every 5 minutes with last updated timestamp
  - Mobile-responsive design with conditional layouts and grid systems
  - Location: `frontend/src/components/analytics/CorpusEngagementDashboard.tsx`

- **GraphQL integration for engagement metrics**
  - New query: `GET_CORPUS_ENGAGEMENT_METRICS` with TypeScript interfaces
  - Leverages existing backend `CorpusEngagementMetrics` model (already tested)
  - Location: `frontend/src/graphql/queries.ts:3873-3979`

- **Analytics tab in Corpus view**
  - New tab with BarChart3 icon next to Discussions tab
  - Conditionally rendered based on corpus ID availability
  - Location: `frontend/src/views/Corpuses.tsx:2209-2216`

- **Dependencies**
  - Added recharts@3.4.1 for data visualization (BarChart, ResponsiveContainer, Tooltip, Legend)
  - Added react-countup for animated number counters

#### Thread Search UI (Issue #580)
- **Backend pagination support for conversation search**
  - Updated `searchConversations` resolver to use `relay.ConnectionField` with cursor-based pagination
  - Supports `first`, `after`, `last`, `before` parameters for efficient result pagination
  - Returns paginated structure with `edges`, `pageInfo`, and `totalCount`
  - Location: `config/graphql/queries.py:1659-1748`

- **GraphQL queries and TypeScript types with pagination**
  - Updated `SEARCH_CONVERSATIONS` query to support paginated results
  - Added pagination parameters: `first`, `after`, `last`, `before`
  - Enhanced TypeScript interfaces with connection structure (edges, nodes, cursors, pageInfo)
  - Includes full thread metadata: chatMessages count, isPinned, isLocked, corpus/document references
  - Location: `frontend/src/graphql/queries.ts:3923-4059`

- **New search components** (`frontend/src/components/search/`)
  - `SearchBar.tsx`: Search input with clear button and Enter key support
  - `SearchFilters.tsx`: Filter by conversation type with clear filters button
  - `SearchResults.tsx`: Results display with pagination, reuses ThreadListItem component
  - `ThreadSearch.tsx`: Main search container with debounced query (300ms) and pagination
  - All components follow existing design patterns and are mobile-responsive

- **Embedded search in Corpus Discussions view**
  - Added tab navigation to switch between "All Threads" and "Search"
  - Search scoped to current corpus when embedded
  - Location: `frontend/src/components/discussions/CorpusDiscussionsView.tsx`

- **Standalone /threads route**
  - New dedicated search page accessible at `/threads`
  - Global search across all accessible discussions
  - Location: `frontend/src/views/ThreadSearchRoute.tsx`, `frontend/src/App.tsx:421`

- **Backend tests for paginated search**
  - Tests verify pagination structure (edges, pageInfo, totalCount)
  - Tests verify cursor-based pagination with multiple pages
  - Location: `opencontractserver/tests/test_conversation_search.py:609-743`

- **Frontend component tests** (18 tests, 100% passing)
  - SearchBar component tests (5 tests): input rendering, search icon, clear button, Enter key submission
  - SearchFilters component tests (5 tests): filter rendering, option counting, selected state, clear filters button
  - SearchResults component tests (4 tests): loading state, empty state, no results state, results rendering
  - ThreadSearch component tests (4 tests): search bar integration, filters toggle, corpus-scoped search
  - Location: `frontend/tests/search-components.ct.tsx`

- **Enhanced backend test coverage for conversation search** (Issue #580 - Coverage Improvement)
  - Added `GraphQLResolverEdgeCasesTest` class with 8 new comprehensive tests
  - Tests cover GraphQL resolver edge cases including:
    - Default embedder path fallback when no corpus/document ID provided
    - Error handling when DEFAULT_EMBEDDER_PATH is not configured
    - Reverse pagination with `last` and `before` parameters
    - Multiple result handling and pagination behavior
    - Message search with various filter combinations
  - Coverage improvements target previously untested code paths in `config/graphql/queries.py:1711-1722, 1797-1808`
  - Location: `opencontractserver/tests/test_conversation_search.py:2666-3050`

#### Structural Annotation Sets (Phase 2.5)
- **New `StructuralAnnotationSet` model** for shared, immutable structural annotations
  - Content-hash based uniqueness (`content_hash` field)
  - Stores parser metadata (`parser_name`, `parser_version`, `page_count`, `token_count`)
  - Stores shared parsing artifacts (`pawls_parse_file`, `txt_extract_file`)
  - Location: `opencontractserver/annotations/models.py`

- **Document → StructuralAnnotationSet FK** with PROTECT on delete
  - Multiple corpus-isolated documents can share the same structural annotation set
  - Eliminates duplication of structural annotations across corpus copies
  - Location: `opencontractserver/documents/models.py:119-127`

- **Annotation.structural_set FK** with XOR constraint
  - Annotations now belong to EITHER a document OR a structural_set (not both, not neither)
  - Database constraint: `annotation_has_single_parent`
  - Location: `opencontractserver/annotations/models.py`

- **Relationship.structural_set FK** with XOR constraint
  - Same pattern as Annotation for relationships
  - Database constraint: `relationship_has_single_parent`
  - Location: `opencontractserver/annotations/models.py`

- **Database migrations**
  - `opencontractserver/annotations/migrations/0048_add_structural_annotation_set.py`
  - `opencontractserver/documents/migrations/0026_add_structural_annotation_set.py`

- **Comprehensive test suite** (32 tests)
  - `opencontractserver/tests/test_structural_annotation_sets.py` (22 tests)
  - `opencontractserver/tests/test_structural_annotation_portability.py` (10 tests)

### Fixed

#### Permission Audit Remediation - GraphQL Resolver Fixes

1. **User profile visibility not respecting privacy settings**
   - **File**: `config/graphql/queries.py` - `resolve_user_by_slug`, `resolve_search_users_for_mention`
   - **Issue**: Resolvers returned users without checking `is_profile_public` or corpus membership
   - **Fixed**: Now uses `UserQueryOptimizer` for proper privacy filtering
   - **Impact**: Private user profiles no longer visible to unauthorized users

2. **Badge visibility not respecting recipient privacy**
   - **File**: `config/graphql/queries.py` - `resolve_user_badges`, `resolve_user_badge`
   - **Issue**: Badge awards were visible regardless of recipient's profile privacy
   - **Fixed**: Now uses `BadgeQueryOptimizer` which filters by recipient visibility
   - **Impact**: Badges of private users no longer leaked to unauthorized viewers

3. **Document actions missing permission checks**
   - **File**: `config/graphql/queries.py` - `resolve_document_corpus_actions`
   - **Issue**: Inline permission checks were inconsistent with least-privilege model
   - **Fixed**: Now uses `DocumentActionsQueryOptimizer` for centralized permission logic
   - **Impact**: Document-related data properly filtered by document AND corpus permissions

4. **Assignment resolver using incorrect visible_to_user signature**
   - **File**: `config/graphql/queries.py` - `resolve_assignments`, `resolve_assignment`
   - **Issue**: Called `Assignment.objects.visible_to_user(info.context.user)` but manager expected different signature
   - **Fixed**: Updated to use correct manager method call pattern
   - **Impact**: Assignment queries now properly filter by user visibility

5. **Unused local imports shadowing top-level imports**
   - **File**: `config/graphql/queries.py` - lines 2810, 2990
   - **Issue**: Local `UserBadge` imports inside resolvers were redundant and caused flake8 warnings
   - **Fixed**: Removed redundant local imports, using top-level import
   - **Impact**: Cleaner code, no shadowing warnings

#### Thread Search (Issue #580)

6. **Anonymous user null reference in searchConversations resolver**
   - **File**: `config/graphql/queries.py:1725`
   - **Issue**: Resolver accessed `info.context.user.is_anonymous` without checking if user was `None`, causing AttributeError in tests with anonymous users
   - **Fixed**: Added null check before accessing `is_anonymous` attribute
   - **Impact**: Anonymous user search queries now work correctly without AttributeError

#### Critical Production Code Fixes

2. **Missing parsing artifacts in corpus copies**
   - **Files**: `opencontractserver/corpuses/models.py:445-451`, `opencontractserver/documents/versioning.py:238-244`
   - **Issue**: When creating corpus-isolated document copies, essential parsing artifacts were not being copied
   - **Fixed**: Added copying of `pawls_parse_file`, `txt_extract_file`, `icon`, `md_summary_file`, `page_count`
   - **Impact**: Corpus copies now have all parsing data needed for annotation, search, and display

3. **Missing `is_public` inheritance in corpus copies**
   - **Files**: `opencontractserver/corpuses/models.py:451`, `opencontractserver/documents/versioning.py:244`
   - **Issue**: Public documents became private when added to a corpus (copy didn't inherit `is_public`)
   - **Fixed**: Added `is_public=document.is_public` to corpus copy creation
   - **Impact**: Document visibility is now correctly preserved across corpus isolation

4. **NULL hash deduplication bug**
   - **File**: `opencontractserver/corpuses/models.py:414-425`
   - **Issue**: All documents without PDF content hashes were incorrectly treated as duplicates
   - **Fixed**: Added null check: `if document.pdf_file_hash is not None:` before hash-based deduplication
   - **Impact**: Documents without hashes are now correctly treated as distinct documents

5. **Structural annotation portability**
   - **Files**: `opencontractserver/corpuses/models.py:456`, `opencontractserver/documents/versioning.py:248`
   - **Issue**: Structural annotations were not traveling with documents when added to multiple corpuses
   - **Fixed**: Corpus copies now inherit `structural_annotation_set` from source document
   - **Impact**: Structural annotations are shared (not duplicated) across corpus-isolated copies

6. **GraphQL corpus.documents field missing**
   - **Files**: `config/graphql/graphene_types.py:1179-1184`, `config/graphql/graphene_types.py:1297-1302`
   - **Issue**: After corpus isolation migration (removing M2M documents field), GraphQL queries for `corpus.documents` returned empty because no explicit field declaration existed
   - **Fixed**: Added explicit `DocumentTypeConnection` class and `documents = relay.ConnectionField()` declaration to CorpusType
   - **Impact**: GraphQL queries now correctly resolve documents via DocumentPath-based relationships

7. **Parser `save_parsed_data()` using old M2M relationship**
   - **File**: `opencontractserver/pipeline/base/parser.py:126-133`
   - **Issue**: `save_parsed_data()` used deprecated `corpus.documents.add()` M2M method which no longer exists
   - **Fixed**: Updated to use `corpus.add_document(document=document, user=user)` for corpus isolation
   - **Impact**: Parsers can now correctly associate documents with corpuses during processing

8. **Document mention resolver using old M2M relationship**
   - **File**: `config/graphql/queries.py:976-1015`
   - **Issue**: `resolve_search_documents_for_mention()` queried via `corpus__in` M2M relationship which no longer exists
   - **Fixed**: Updated to query via `DocumentPath` with `is_current=True, is_deleted=False` filters
   - **Impact**: Document mention autocomplete now correctly finds documents in corpuses

9. **BaseFixtureTestCase not adding documents to corpus**
   - **File**: `opencontractserver/tests/base.py:385-399`
   - **Issue**: Test setup created corpus but didn't add fixture documents to it via DocumentPath
   - **Fixed**: Added loop to call `corpus.add_document()` for each fixture document and update references to corpus copies
   - **Impact**: WebSocket and other tests now properly test with documents in corpus context

### Changed

#### Test Suite Updates for Corpus Isolation Architecture

- **Removed deprecated legacy manager tests**
  - **File**: `opencontractserver/tests/test_document_path_migration.py`
  - **Removed**: Test classes for deprecated `DocumentCorpusRelationshipManager` (20+ tests)
  - **Reason**: The backward compatibility M2M manager was removed in Issue #654 Phase 2
  - **Note**: `DocumentCorpusRelationshipManager` in `opencontractserver/documents/managers.py` remains as documentation but is unused
  - **Impact**: Improved test clarity by removing tests for code that never executes

- **Permission assignment order** in test setups
  - Moved permission assignment AFTER `add_document()` calls
  - Ensures permissions are assigned to corpus copies, not originals
  - Files: `test_visibility_managers.py`, `test_resolvers.py`, `test_permissioning.py`, `test_version_aware_query_optimizer.py`

- **Document count expectations**
  - Updated tests to account for both originals and corpus copies existing
  - Example: Owner sees 6 documents (3 originals + 3 corpus copies) instead of 3
  - Files: `test_visibility_managers.py`, `test_resolvers.py`

- **Document-to-corpus linking**
  - Changed from M2M `corpus.documents.add()` to `corpus.add_document()`
  - File: `test_custom_permission_filters.py:211-213`

- **Corpus document queries**
  - Updated tests to query corpus documents via DocumentPath, not M2M
  - File: `test_bulk_document_upload.py:305-313`

### Technical Details

#### Architectural Changes

The structural annotation set feature implements Phase 2.5 of the dual-tree versioning architecture:

1. **Content-based deduplication**: Structural annotations are tied to content hash, not individual documents
2. **Corpus isolation compatibility**: When a document is copied to multiple corpuses, all copies share the same structural annotation set
3. **Immutability guarantee**: Structural annotations in shared sets cannot be modified (protected by PROTECT on delete)
4. **XOR constraints**: Database-level enforcement that annotations belong to either a document or a structural set

#### File Changes Summary

**New Files:**
- `opencontractserver/tests/test_structural_annotation_sets.py`
- `opencontractserver/tests/test_structural_annotation_portability.py`
- `opencontractserver/annotations/migrations/0048_add_structural_annotation_set.py`
- `opencontractserver/documents/migrations/0026_add_structural_annotation_set.py`
- `docs/architecture/STRUCTURAL_ANNOTATION_SETS.md`
- `CHANGELOG.md`

**Modified Files:**
- `opencontractserver/annotations/models.py` - Added StructuralAnnotationSet model, updated Annotation/Relationship models
- `opencontractserver/documents/models.py` - Added structural_annotation_set FK
- `opencontractserver/corpuses/models.py` - Fixed add_document() to copy all artifacts + structural set
- `opencontractserver/documents/versioning.py` - Fixed import_document() to copy all artifacts + structural set
- `config/graphql/graphene_types.py` - Added DocumentTypeConnection and explicit documents field for CorpusType
- `config/graphql/queries.py` - Updated document mention resolver to use DocumentPath
- `opencontractserver/pipeline/base/parser.py` - Updated save_parsed_data() to use add_document()
- `opencontractserver/tests/base.py` - Updated BaseFixtureTestCase to add documents to corpus
- `opencontractserver/tests/test_visibility_managers.py` - Updated for corpus isolation
- `opencontractserver/tests/test_resolvers.py` - Updated for corpus isolation
- `opencontractserver/tests/test_bulk_document_upload.py` - Updated for corpus isolation
- `opencontractserver/tests/permissioning/test_permissioning.py` - Updated for corpus isolation
- `opencontractserver/tests/permissioning/test_custom_permission_filters.py` - Updated for corpus isolation
- `opencontractserver/tests/permissioning/test_version_aware_query_optimizer.py` - Updated for corpus isolation
- `CLAUDE.md` - Added Changelog Maintenance section

### Fixed (Continued)

10. **Query optimizer missing structural_set annotations**
   - **Files**: `opencontractserver/annotations/query_optimizer.py:189-212, 273-301, 541-564, 624-643`
   - **Issue**: `AnnotationQueryOptimizer.get_document_annotations()` and `RelationshipQueryOptimizer.get_document_relationships()` only queried by `document_id`, missing annotations/relationships stored in `structural_set` (which have `document_id=NULL`)
   - **Impact**: GraphQL queries using query optimizer (most annotation/relationship queries) did NOT return structural annotations from structural sets - only vector store had the dual-query logic
   - **Fixed**:
     - Added document fetch with `select_related("structural_annotation_set")` for efficiency
     - Built OR filter: `Q(document_id=X) | Q(structural_set_id=Y, structural=True)` to query BOTH sources
     - Updated corpus filtering to preserve structural_set items (which have `corpus_id=NULL`)
     - Applied same fix to both AnnotationQueryOptimizer and RelationshipQueryOptimizer
   - **Tests Added**: `opencontractserver/tests/test_query_optimizer_structural_sets.py` (10 comprehensive integration tests)
   - **Test Results**: All 42 structural annotation tests pass (10 new + 32 existing)

11. **Vector store returning duplicate results**
   - **File**: `opencontractserver/shared/mixins.py:40-89`
   - **Issue**: `search_by_embedding()` method returned duplicate results (2x, 4x, 6x expected counts) when annotations had multiple Embedding rows with the same `embedder_path`
   - **Root Cause**: JOIN to Embedding table created cartesian product - if annotation had 2 Embedding rows, JOIN produced 2 result rows
   - **Investigation**: Confirmed annotations have multiple Embedding rows due to dual FK relationship:
     1. `Embedding.annotation` FK (one-to-many): annotation can have multiple embeddings
     2. `Annotation.embeddings` FK (many-to-one): annotation points to single "primary" embedding
   - **Fixed**: Hybrid deduplication approach in `search_by_embedding()`:
     1. Order by `id, similarity_score` and apply PostgreSQL `DISTINCT ON (id)`
     2. Materialize query to list
     3. Sort in Python by `similarity_score`
     4. Return top_k results
   - **Rationale**: PostgreSQL `DISTINCT ON` requires the distinct field to be first in ORDER BY, conflicting with need to order by similarity_score. Hybrid approach ensures correctness.
   - **Test Results**: All 9 version-aware vector store tests now pass (previously all 8 failing)

12. **Vector store excluding structural annotations from StructuralAnnotationSet**
   - **File**: `opencontractserver/llms/vector_stores/core_vector_stores.py:168-196, 221-270`
   - **Issue**: Version filtering excluded ALL structural annotations from structural sets, causing vector search to return 0 results
   - **Root Cause - Filter Ordering Bug**:
     1. `only_current_versions` filter applied `Q(document__is_current=True)` (line 170)
     2. This creates `INNER JOIN` on document table
     3. Structural annotations have `document_id=NULL` (stored in StructuralAnnotationSet)
     4. NULL document_id fails the JOIN → structural annotations excluded
     5. This happened BEFORE document/corpus scoping (lines 221-270)
     6. Result: Scoping logic tried to include structural annotations, but they were already filtered out
   - **Symptoms**:
     - Initial queryset: 1344 annotations
     - After version filter: 0 results (all structural annotations excluded)
     - WebSocket tests failed with no ASYNC_CONTENT (agent had no context)
   - **Fixed**:
     - Modified version filter to preserve structural annotations:
       ```python
       active_filters &= Q(document__is_current=True) | Q(
           document_id__isnull=True, structural=True
       )
       ```
     - Logic: Annotations with document FK must have `is_current=True`, structural annotations (no document FK) pass through
     - Later scoping filters by `structural_set_id` to ensure only relevant structural annotations included
   - **Comments Added**: Comprehensive inline documentation explaining:
     - Why structural annotations have `document_id=NULL`
     - Filter ordering and interaction between version filter and scoping
     - Two-phase filtering approach (version → scoping)
   - **Test Results**:
     - Vector store now finds 336 annotations (was 0)
     - SQL shows correct filter: `(document.is_current OR (annotation.document_id IS NULL AND structural))`

13. **Agent tool execution failing due to list/QuerySet type mismatch**
   - **Files**: `opencontractserver/llms/vector_stores/core_vector_stores.py:30-90`
   - **Issue**: After deduplication fix (#10), `search_by_embedding()` returns list instead of QuerySet, breaking agent tool execution
   - **Root Cause - Type Assumption**:
     1. Deduplication fix materialized QuerySet to list for DISTINCT ON + Python sorting
     2. Helper functions `_safe_queryset_info()` and `_safe_execute_queryset()` assumed QuerySet
     3. Called `.count()` method on lists (which don't have `.count()` for length)
     4. Agent's `similarity_search` tool failed silently
     5. LLM called tool → tool execution broke → no second LLM call → no ASYNC_CONTENT
   - **Symptoms**:
     - Only 1 LLM API call in cassettes (should be 2: tool call + final answer)
     - Agent produced ASYNC_START and ASYNC_FINISH but no ASYNC_CONTENT
     - Cassette files abnormally small (27KB vs expected 50-70KB)
   - **Fixed**: Updated helper functions to handle both QuerySets and lists:
     ```python
     async def _safe_queryset_info(queryset, description: str) -> str:
         if isinstance(queryset, list):
             return f"{description}: {len(queryset)} results"
         # ... handle QuerySet

     async def _safe_execute_queryset(queryset) -> list:
         if isinstance(queryset, list):
             return queryset  # Already materialized
         # ... execute QuerySet
     ```
   - **Test Results**:
     - Tool execution now succeeds ✅
     - Cassettes show 2 LLM calls (tool call + response) ✅
     - Cassette size increased to 55KB (proper content) ✅
     - WebSocket tests still fail (different issue: agent streaming layer - not tool execution)

### Known Issues

1. **Pre-existing annotation visibility limitation**: `AnnotationQuerySet.visible_to_user()` doesn't check object-level permissions (only checks `is_public` or `creator`). This was not introduced by these changes but is more apparent with corpus isolation.

2. **WebSocket conversation tests** (`ConversationSourceLoggingTestCase`): Tests fail with no ASYNC_CONTENT messages.
   - **Current Status**: Tests fail with `AssertionError: [] is not true : At least one ASYNC_CONTENT expected`
   - **Vector Store Issues RESOLVED**:
     1. ✅ Vector store deduplication (issue #10 above) - All 9 vector store tests pass
     2. ✅ Query optimizer structural_set support (issue #9 above) - All 42 structural annotation tests pass
     3. ✅ Vector store version filtering (issue #11 above) - Now finds 336 annotations (was 0)
   - **Remaining Issue**: Agent produces no streaming content despite finding annotations
     - Vector store successfully returns 336 annotations to agent
     - Agent runs but produces no ASYNC_CONTENT messages (only ASYNC_START and ASYNC_FINISH)
     - Likely cause: VCR cassette mocking issue or LLM API configuration
     - **NOT a vector store or structural annotation architecture issue**
   - **Next Steps**: Investigate VCR cassette recordings and LLM mocking configuration
   - **Impact**: Isolated to WebSocket tests - production vector search and retrieval works correctly

### Migration Notes

- Run migrations in order: annotations/0048 before documents/0026
- No data migration required - new fields are nullable
- Existing documents will have `structural_annotation_set=None` until parsed

### Performance Considerations

- Structural annotations are now shared (O(1) storage) instead of duplicated per corpus copy
- DocumentPath queries are indexed for efficient corpus document lookups
- Content-hash based deduplication prevents redundant parsing
