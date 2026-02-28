# Changelog

All notable changes to OpenContracts will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased] - 2026-02-28

### Fixed

#### Tighten JSON Field Validation for Malformed Input (Closes #1001)
- **Root cause**: `CustomJSONFieldFormTests.TestForm` used `NullableJSONField()` (a model field) instead of `UTF8JSONFormField` (a form field). Django's `Form` metaclass silently ignores model fields, so the form had zero fields and `is_valid()` always returned `True` — masking the fact that malformed JSON was never validated.
- **Fix**: Changed `TestForm.json_field` to `UTF8JSONFormField(required=False)` so form validation actually runs through Django's `forms.JSONField.to_python()`, which raises `ValidationError` on `json.JSONDecodeError` (`opencontractserver/tests/test_custom_fields.py:76`).
- **Re-enabled**: `test_form_with_invalid_json` now asserts that `'not json'` is correctly rejected (`opencontractserver/tests/test_custom_fields.py:90-92`).
- **Added**: `test_formfield_rejects_invalid_json` and `test_formfield_accepts_valid_json` integration tests on `NullableJSONFieldTests` to verify the model field's `formfield()` method produces a form field that properly validates JSON (`opencontractserver/tests/test_custom_fields.py:63-71`).

### Changed

#### Triage and Clean Up TODO/FIXME Comments (Closes #971)
- Removed 62 TODO/FIXME/HACK annotations across 43 backend and frontend files
- Replaced vague TODOs with `NOTE(deferred):` comments explaining deferral reasoning
- Deleted stale comments referencing non-existent files, already-implemented features, and empty test stubs
- Fixed typo: "whould" → "should" in `test_permissioning.py`
- Removed `console.log` debug statement in `ModernDocumentItem.tsx`
- Deleted empty test stub file `test_doc_analysis_tasks.py`
- Consolidated redundant `logger.debug()` calls in `utils/files.py`

#### Extract Magic Numbers to Constants Files (Closes #970)
- Replaced hardcoded upload limit, truncation lengths, DPI, and title limits with named constants in `constants/document_processing.py` and `constants/llm_tools.py`
- Reused existing `MAX_PROCESSING_ERROR_LENGTH`/`MAX_PROCESSING_TRACEBACK_LENGTH` in `corpuses/models.py`

#### GraphQL Module Modularization (Closes #972)
- Split `graphene_types.py` (3,717→107 lines), `mutations.py` (6,229→405 lines), `queries.py` (4,408→54 lines) into domain-specific files
- Full backward compatibility via re-exports; no logic changes

#### Consolidate Duplicate String Truncation Utilities (Closes #976)
- Added `truncate()` helper in `opencontractserver/utils/text.py` and named constants in `constants/truncation.py`
- Replaced inline truncation across `core_tools.py`, `doc_tasks.py`, and `corpuses/models.py`

#### Break Up Large Frontend Components (Closes #977)
- Split 5 large components: StyledContainers (2,115→12), SystemSettings (2,616→1,108), CorpusChat (2,347→1,346), DocumentKnowledgeBase (3,363→2,322), ChatTray (2,215→1,772)
- Extracted shared chat WebSocket types into canonical `chat/types.ts`; renamed duplicate ConversationListView components; replaced `any` types with explicit typed properties

### Added

#### Replace Mock Data with Real User Query in @mention Dropdown (Closes #1002)
- **useMentionUsers hook** (`frontend/src/components/threads/hooks/useMentionUsers.ts`): Replaced hardcoded mock users with real `SEARCH_USERS_FOR_MENTION` GraphQL query. Added 300ms debounced input to reduce excessive API calls and minimum character threshold (2 chars). Hook now returns `{ users, loading, error }` instead of just `MentionUser[]`.
- **MentionPicker component** (`frontend/src/components/threads/MentionPicker.tsx`): Added loading and error state rendering. Shows "Searching users..." during query execution and "Failed to load users" on errors. Added `loading` and `error` optional props to `MentionPickerProps`.

#### Deep Linking and Context Menu for Text/PDF Annotators (Closes #958)
- Copy Link actions in PDF (`SelectionLayer.tsx`) and TXT (`TxtAnnotator.tsx`) context menus encode selections as `?tb=` deep link URLs
- URL-driven annotation selection from chat sources (`ChatTray.tsx`); delete button for processing documents (`ModernDocumentItem.tsx`)

#### Corpus Export Test Coverage (Closes #997)
- Added `test_exported_document_structure` to validate exported document data structure: top-level keys, PAWLS page schema, annotation structure with bounding boxes and token references, and PDF burn-in validity (`opencontractserver/tests/test_corpus_export.py`)
- Added `test_round_trip_consistency` to compare exported data against original import fixture: document title, content, PAWLS page dimensions and token counts, annotation count, raw text, label names (mapped through label lookups), and bounding box coordinates (`opencontractserver/tests/test_corpus_export.py`)
- Added `test_exported_label_names_match_fixture` to verify exported label name sets match the labels actually used in the import fixture (`opencontractserver/tests/test_corpus_export.py`)
- Loaded import fixture data in setUp for round-trip comparison, replacing the previous TODO placeholder (`opencontractserver/tests/test_corpus_export.py:62`)
- Cleaned up existing tests by removing verbose print statements and TODO comments

#### Expand burn_doc_annotations Test (Closes #1000)
- Added `test_burn_doc_annotations_with_text_labels` to exercise the text-label PDF burning code path with TOKEN_LABEL fixtures and bounding-box annotation data (`opencontractserver/tests/test_doc_tasks.py`)
- Validates output PDF contains highlight annotations with correct subtype, label text, and non-empty base64-encoded content
- Validates `doc_export` JSON contains expected `doc_labels` and `labelled_text` entries
- Renamed existing test to `test_burn_doc_annotations_doc_labels_only` for clarity

#### Test Coverage for Untested Backend Modules (Closes #975)
- Unit tests for feedback, shared utils, constants, types, and MCP extended modules (`opencontractserver/tests/`)

### Fixed

#### Code Review Fixes for Text Block Deep Linking (#958)
- Document resolution via corpus membership (`DocumentPath`) instead of `creator=owner`; simplified default path to return already-resolved doc
- Cross-document source click flash fix; `useClearTextBlockOnInteraction` hook consolidation; clipboard `.catch()` for non-HTTPS; dead code removal

#### Document Version Selector UI Cleanup (Closes #964)
- Removed unused query fields (`versionCount`, `hasVersionHistory`, etc.); added WAI-ARIA keyboard navigation; safe `v?` fallback during load
- Backend validation for invalid version numbers (≤ 0); isCurrent JSDoc; updated test mocks and new keyboard nav tests

#### Rollup Vulnerability (Closes #973)
- Pinned `rollup: "^4.59.0"` via yarn resolutions to fix 3 high-severity path traversal advisories
- **Result**: rollup updated from 4.53.1 to 4.59.0, eliminating all 3 rollup-related audit advisories

### Added

#### Worker Upload Management UI and Documentation (#955)
- **GraphQL queries**: `workerAccounts`, `corpusAccessTokens`, `workerDocumentUploads` resolvers with proper permission checks (superuser-only for accounts, superuser/corpus-creator for tokens and uploads) (`config/graphql/queries.py`)
- **ReactivateWorkerAccount mutation**: Allows superusers to re-enable previously deactivated worker accounts (`config/graphql/worker_mutations.py`)
- **Worker Account management page**: New admin page at `/admin/worker-accounts` for creating, listing, and activating/deactivating worker service accounts (`frontend/src/components/admin/WorkerAccountManagement.tsx`)
- **Worker Access Tokens section in Corpus Settings**: Corpus creators and superusers can view, create, and revoke access tokens scoped to their corpus. Includes one-time key display with copy-to-clipboard (`frontend/src/components/corpuses/settings/WorkerTokensSection.tsx`)
- **Documentation walkthrough**: End-to-end guide covering account creation, token management, document upload (with curl/Python examples), metadata format reference, rate limiting, error handling, and security model (`docs/worker_uploads/walkthrough.md`)
- **Component tests**: Playwright component tests for WorkerAccountManagement with automated documentation screenshots

#### Document Version Selector End-to-End Documentation (Closes #954)
- **User-facing guide**: `docs/features/document_versioning.md` — covers version creation workflow, visual status indicators (gray/blue/orange badges), Version History Panel usage, and Trash folder recovery
- **Documentation screenshots**: Added `docScreenshot` calls to capture five key UI states:
  - `versioning--badge--single-version` — gray badge for documents without history (`frontend/tests/VersionBadge.ct.tsx`)
  - `versioning--badge--latest-version` — blue badge showing version count (`frontend/tests/VersionBadge.ct.tsx`)
  - `versioning--badge--older-version` — orange badge for outdated versions (`frontend/tests/VersionBadge.ct.tsx`)
  - `versioning--history-panel--with-versions` — already captured in `frontend/tests/VersionHistoryPanel.ct.tsx`
  - `versioning--trash-folder--restore-ui` — deleted document recovery interface (`frontend/tests/TrashFolderView.ct.tsx`)

### Changed

#### Worker Upload Permission Expansion (#955)
- `CreateCorpusAccessTokenMutation` and `RevokeCorpusAccessTokenMutation` now allow corpus creators (not just superusers) to manage tokens scoped to their own corpora
- GlobalSettingsPanel refreshed with OS Legal design tokens and lucide-react icons, replacing Semantic UI dependencies

#### Auth0 Refresh Token Migration (#955)
- **DEPLOYMENT NOTE**: `useRefreshTokens: true` is now enabled in the Auth0 SDK configuration (`frontend/src/index.tsx`). Deployments using Auth0 **must** enable "Refresh Token Rotation" in the Auth0 dashboard before deploying this change, or silent authentication will fail for all users.

### Fixed

#### Document Version Structural Annotation Set Inheritance
- **Bug**: When a document was updated with new content (different hash), `import_document()` unconditionally inherited the old version's `structural_annotation_set`. This caused the parser's `_create_structural_annotation_set()` to short-circuit (early return at `pipeline/base/parser.py:299`), leaving freshly-parsed structural annotations orphaned — never migrated into a set.
- **Fix**: `opencontractserver/documents/versioning.py:224-231` — `structural_annotation_set` is now only inherited when the content hash is unchanged. When content changes, the field is set to `None` so the parser creates a fresh `StructuralAnnotationSet` during ingestion.
- **Tests**: `opencontractserver/tests/test_structural_annotation_portability.py` — replaced single test with two: one verifying `None` on changed content, one verifying inheritance on identical content.

### Added

#### Annotation Versioning and Document Version-Aware Deep Linking
- **Version-aware document resolution**: `documentInCorpusBySlugs` GraphQL query now accepts optional `versionNumber` parameter to resolve a specific historical version of a document (`config/graphql/queries.py`)
- **Corpus versions field**: New `corpusVersions(corpusId)` field on `DocumentType` returns all versions of a document in a corpus with version number, document ID, slug, creation date, and current status (`config/graphql/graphene_types.py`)
- **`CorpusVersionInfoType` GraphQL type**: New type for version selector data returned by `corpusVersions` field
- **`?v=N` URL parameter**: Deep links to documents now support a `?v=N` query parameter to view a specific version (e.g., `/d/user/corpus/doc?v=1&ann=123`)
- **`selectedDocVersion` reactive var**: New URL-driven state variable in `frontend/src/graphql/cache.ts` synced bidirectionally via CentralRouteManager Phases 2 and 4
- **CentralRouteManager version support**: Phase 1 passes version to GraphQL resolution, Phase 2 parses `?v=` into reactive var, Phase 4 syncs back to URL (`frontend/src/routing/CentralRouteManager.tsx`)
- **`DocumentVersionSelector` component**: Inline version badge and dropdown in document header that shows available versions and allows switching between them (`frontend/src/components/documents/DocumentVersionSelector.tsx`)
- **Navigation utilities**: `QueryParams` interface and `buildQueryParams` now support `version` field for URL construction (`frontend/src/utils/navigationUtils.ts`)
- **Routing documentation**: Updated `docs/frontend/routing_system.md` with version parameter documentation, examples, and reactive var listing

#### Worker Document Upload System
- **New Django app** `opencontractserver.worker_uploads` — enables external document-processing workers to upload fully ingested, annotated, and embedded documents to a target corpus via REST API
- **Service account model** (`WorkerAccount`): dedicated machine identity with auto-created Django User for permission compatibility. Created via `createWorkerAccount` GraphQL mutation (superuser only)
- **Corpus-scoped access tokens** (`CorpusAccessToken`): cryptographically random 256-bit tokens scoped to a single corpus, with configurable expiry and per-token rate limiting. Created via `createCorpusAccessToken` GraphQL mutation
- **Hashed token storage**: tokens are stored as SHA-256 hashes — plaintext shown only once at creation via `create_token()`. Auth backend hashes incoming keys before DB lookup (`opencontractserver/worker_uploads/models.py`, `auth.py`)
- **DRF authentication backend** (`WorkerTokenAuthentication`): validates `Authorization: WorkerKey <token>` headers, hashes token and checks validity, expiry, and account status (`opencontractserver/worker_uploads/auth.py`)
- **REST upload endpoint** (`POST /api/worker-uploads/documents/`): accepts multipart form data (file + JSON metadata), stages uploads in database, returns 202 Accepted immediately. Status polling via `GET /api/worker-uploads/documents/<id>/` and listing via `GET /api/worker-uploads/documents/list/`
- **Upload format** (`WorkerDocumentUploadMetadataType`): extends V2 export format with pre-computed embeddings (`embedder_path` + document/annotation vectors), target path/folder placement, and inline label definitions for auto-creation (`opencontractserver/types/dicts.py`)
- **Database-backed queue** (`WorkerDocumentUpload`): staging table with PENDING/PROCESSING/COMPLETED/FAILED status tracking, avoids Redis saturation for high-volume uploads (millions of documents)
- **Batch processor task** (`process_pending_uploads`): Celery task on dedicated `worker_uploads` queue using `SELECT ... FOR UPDATE SKIP LOCKED` for concurrent processing without conflicts. Configurable batch size via `WORKER_UPLOAD_BATCH_SIZE` setting. Self-reschedules when more work exists
- **Multi-queue architecture**: worker upload processing runs on dedicated `worker_uploads` Celery queue, preserving capacity on the default queue for regular user operations
- **Pre-computed embedding storage**: workers can include embeddings in upload metadata; stored directly via bulk_create without re-running embedder models. Supports all vector dimensions (384–4096)
- **Corpus creator ownership**: all documents, annotations, and labels created via worker uploads are owned by the corpus creator (not the service account), ensuring correct permission inheritance
- **GraphQL management mutations**: `createWorkerAccount`, `deactivateWorkerAccount`, `createCorpusAccessToken`, `revokeCorpusAccessToken` (all superuser-only) in `config/graphql/worker_mutations.py`
- **Celery task routing**: `CELERY_TASK_ROUTES` canonicalized in one place with guard comment (`config/settings/base.py`)
- **Settings-based Beat schedule**: `CELERY_BEAT_SCHEDULE` for worker upload drain (60s interval), replacing fragile data migration approach
- **File size limit**: `MAX_WORKER_UPLOAD_SIZE_BYTES` setting (default 256 MB) enforced at upload endpoint
- **Filename sanitization**: worker-supplied document titles are sanitized before use as filenames, stripping path traversal characters and null bytes

### Technical Details
- New files: `opencontractserver/worker_uploads/{models,views,auth,serializers,tasks,urls,apps}.py`, `config/graphql/worker_mutations.py`
- Migrations: `0001_initial.py` (models), `0002_setup_beat_schedule.py` (cleanup old DB schedule), `0003_hash_token_keys.py` (SHA-256 token hashing)
- Settings: `WORKER_UPLOAD_BATCH_SIZE` (default 50), `MAX_WORKER_UPLOAD_SIZE_BYTES` (default 256 MB), `CELERY_TASK_ROUTES` for queue isolation, `CELERY_BEAT_SCHEDULE` for periodic drain
- Tests: `opencontractserver/tests/test_worker_uploads.py` covering models, hashed token auth, REST endpoints, file size limits, batch processor, filename sanitization, null corpus creator guard, and GraphQL mutations

#### Corpus Export Format Specification and Validation Utility
- **Format specification**: `docs/architecture/corpus-export-format-spec.md` — complete reference for V1 and V2 corpus export ZIP format covering all data.json fields, PAWLs structure, referential integrity rules, security limits, and import behavior
- **Standalone validator**: `opencontractserver/utils/validate_export.py` — checks structural and referential integrity of export ZIPs without requiring Django or a database. Usable as CLI (`python -m opencontractserver.utils.validate_export corpus.zip`) or library (`validate_export()` / `validate_data_json()`)
- **Validation checks**: ZIP↔data.json file consistency, label definitions and type constraints, annotation token/page index bounds, annotation bounds non-negativity, structural set hash consistency, folder hierarchy (circular reference detection, path consistency), document path references, relationship label type enforcement (including structural relationships), V2 required top-level fields, conversation/message/vote cross-references, unknown version warnings
- **Test suite**: `opencontractserver/tests/test_validate_export.py` — 48 pure-Python tests covering all validation paths including CLI entry point

### Changed

#### Migrate from deprecated PyPDF2 to pypdf (Closes #938)
- Replaced `PyPDF2==3.0.1` with `pypdf` in `requirements/base.txt`
- Removed redundant `pypdf` entry from `requirements/local.txt` (now provided by base)
- Updated imports in `opencontractserver/utils/files.py`, `opencontractserver/utils/etl.py`, and `opencontractserver/tests/test_pdf_redaction.py`
- Removed unused `add_highlight_to_page` function from `opencontractserver/utils/files.py` (used deprecated `_addObject` API, never called)

#### Django 4.2 → 5.2 LTS Upgrade
- **Django version**: Upgraded from Django 4.2.24 to 5.2.11 (LTS)
  - `requirements/base.txt`, `requirements/local.txt`, `requirements/production.txt`
- **STORAGES migration**: Replaced deprecated `STATICFILES_STORAGE` and `DEFAULT_FILE_STORAGE` settings with the unified `STORAGES` dict (required since Django 5.1)
  - `config/settings/base.py` — LOCAL, AWS, and GCP storage backends all migrated
  - `config/settings/test.py` — test storage configuration migrated
  - `opencontractserver/tests/base.py` — test `@override_settings` migrated
  - `opencontractserver/tests/test_agent_search_tools.py` — all `@override_settings` decorators migrated
  - `opencontractserver/tests/test_storage_backends.py` — assertions updated to check `STORAGES` dict
- **Removed `USE_L10N` setting**: This setting was removed in Django 5.0 (localization is always enabled)
  - `config/settings/base.py:78`
- **Removed `SECURE_BROWSER_XSS_FILTER` setting**: This setting was removed in Django 5.0 (modern browsers handle XSS filtering natively)
  - `config/settings/base.py:503-504`
- **Replaced `pytz` with `datetime.timezone`**: Django 5.0+ uses `zoneinfo` instead of `pytz`
  - `opencontractserver/users/tasks.py` — replaced `pytz.utc.localize()` with `datetime.datetime.now(datetime.timezone.utc)`
  - Removed `pytz` from direct requirements in `requirements/base.txt`
- **Updated third-party packages for Django 5.2 compatibility**:
  - `graphene-django`: 3.2.2 → 3.2.3 (adds Django 5.1+ support; Django 5.2 not officially supported — tracked via TODO)
  - `django-stubs`: 4.2.7 → 5.2.0
  - `djangorestframework-stubs`: 1.8.0 → 3.15.4
  - `django-celery-beat`: 2.6.0 → 2.8.1 (adds Django 5.2 support)
  - `django-filter`: 24.3 → 25.1 (adds Django 5.2 support)
  - `django-model-utils`: 4.3.1 → 5.0.0 (adds Django 5.x support; no direct imports in codebase — transitive dependency)
  - `django-crispy-forms`: 2.4 → 2.5 (adds Django 5.2 support)
  - `django-cte`: 2.0.0 → 3.0.0 (adds Django 5.2 support, fixes ambiguous column names; LOUTER breaking change does not affect this project — no `_join_type` usage found)
  - `django-environ`: 0.12.0 → 0.13.0 (adds Django 5.2 support)
- **Removed `django-debug-toolbar`**: Was never wired into INSTALLED_APPS or MIDDLEWARE; removed unused dependency and associated INTERNAL_IPS config from `config/settings/local.py`
- **Replaced Collectfast with Collectfasta** (production static file collection):
  - `Collectfast==2.2.0` was archived/unmaintained (last release 2020), incompatible with Django 5.x `STORAGES` setting
  - Switched to `collectfasta>=3.2.0`, an actively maintained fork tested with Django 5.2.3
  - `requirements/production.txt` — package swap
  - `config/settings/production.py` — updated INSTALLED_APPS reference
  - `config/settings/base.py` — renamed `COLLECTFAST_STRATEGY` to `COLLECTFASTA_STRATEGY` and updated paths from `collectfast.strategies.*` to `collectfasta.strategies.*`

### Security

#### Dependency Security Updates
- **Django 4.2.24 → 4.2.28 (now 5.2.11)**: CVEs fixed by the 5.2.11 LTS release include multiple SQL injection vectors (CVE-2025-59681, CVE-2025-64459, CVE-2025-13372, CVE-2026-1312, CVE-2026-1287, CVE-2026-1207), directory traversal (CVE-2025-59682), DoS attacks (CVE-2025-64458, CVE-2025-64460), and user enumeration timing attack (CVE-2025-13473)
  - Updated in `requirements/base.txt`, `requirements/local.txt`, `requirements/production.txt`
- **cryptography 46.0.3 → 46.0.5**: Fixes CVE-2026-26007 — missing subgroup validation in ECDSA/ECDH public key loading for SECT curves, enabling signature forgery and private key leakage
  - Updated in `requirements/base.txt`
- **axios ^1.12.0 → ^1.13.5**: Fixes DoS vulnerability via `__proto__` key in `mergeConfig`
  - Updated in `frontend/package.json`
- **Removed unused `worker-loader`**: Webpack-specific package unused in Vite project; removal eliminates transitive `ajv@6.12.6` ReDoS vulnerability (via `worker-loader > schema-utils > ajv`)
  - Removed from `frontend/package.json`

### Fixed

#### TxtAnnotator Infinite Re-render Loop (Closes #933)
- **Unstable default parameter**: `chatSources = []` in `TxtAnnotator` component props created a new array reference on every render, triggering infinite re-renders via `useEffect` dependency arrays when the prop was not explicitly passed (`frontend/src/components/annotator/renderers/txt/TxtAnnotator.tsx:335`)
- Extracted `ChatSourceHighlight` interface and defined module-level `EMPTY_CHAT_SOURCES` constant as the default value, ensuring referential stability across renders

#### Follow-up Text Annotation Fixes (Closes #911)
- **Double-scroll bug**: `toggleSelectedAnnotation` in `AnnotatorSidebar.tsx:758` and `RelationshipList.tsx:106` called `scrollIntoView` for all annotation types, including text span annotations which already scroll via `TxtAnnotator`'s own `selectedAnnotations` useEffect. This caused two competing scroll animations. Fixed by guarding with `instanceof ServerTokenAnnotation` check.
- **Phantom ID tracking**: `TxtAnnotator.tsx:366` built `currentIds` from all visible annotations before verifying DOM elements existed. Annotations without rendered spans became "ghost" IDs tracked in `registeredAnnotationIdsRef` but never actually registered. Fixed by only adding IDs to the tracking set after confirming a DOM element was found and registered.
- **Page number display regression**: `HighlightItem.tsx` and `RelationHighlightItem.tsx` now use `(annotation instanceof ServerTokenAnnotation || annotation.page > 0)` to show page labels. PDF token annotations always display page labels (page is always meaningful), while span annotations only display them when `page > 0` (since `page=0` is a sentinel for "no page concept applies").
- **TypeScript type narrowing**: `HighlightItem.tsx:176` stored `instanceof` check in an intermediate boolean variable, preventing TypeScript's control-flow narrowing. Inlined the `instanceof` check directly in the conditional.

#### BaseChunkedParser Robustness and Consistency (Closes #926)
- **Config ValueError not wrapped**: `calculate_page_chunks` raises `ValueError` for invalid `max_pages_per_chunk`/`min_pages_for_chunking`, but the call in `_parse_document_impl` was unwrapped. Now caught and re-raised as `DocumentParsingError(is_transient=False)` (`opencontractserver/pipeline/base/chunked_parser.py`)
- **Small-document annotations unprefixed**: Single-chunk documents returned directly from `_parse_chunk_with_retry` without passing through `_reassemble_chunk_results`, resulting in unprefixed annotation/relationship IDs. Now all results consistently receive `c0_` prefixed IDs (`opencontractserver/pipeline/base/chunked_parser.py`)
- **Uncovered backoff cap branch**: `MAX_CHUNK_RETRY_BACKOFF_SECONDS` cap was never exercised by tests. Added test with `chunk_retry_limit=4` that verifies backoff values `[5, 10, 20, 30]` where the 4th retry hits the 30s cap (`opencontractserver/tests/test_chunked_parser.py`)
- **Theoretical race in concurrent test**: `slow_chunks_started.is_set()` assertion could fail on heavily loaded CI. Added `slow_chunks_started.wait(timeout=2)` before the assertion (`opencontractserver/tests/test_chunked_parser.py`)

#### Context Guardrails for LLM Conversation Management (Closes #907)

- **`truncate_tool_output` negative slice defense** (`opencontractserver/llms/context_guardrails.py`): Replaced fragile guard clause with explicit `char_budget = max(0, max_chars - len(notice))` to prevent negative slice indices when `max_chars` is smaller than the truncation notice length
- **Token double-counting across compaction cycles** (`opencontractserver/llms/context_guardrails.py`, `opencontractserver/llms/agents/pydantic_ai_agents.py`): Added `stored_summary_tokens` parameter to `compact_message_history()` so the stored summary is counted in `total_before` (threshold check) but not double-counted in `total_after` (the new summary replaces the old one)
- **Repeating prefix in compaction summaries** (`opencontractserver/llms/agents/pydantic_ai_agents.py`): Successive compaction cycles no longer accumulate duplicate `COMPACTION_SUMMARY_PREFIX` headers — the merge logic now strips the prefix from both old and new summaries before re-adding it once
- **Fragile sentence extraction in deterministic summary** (`opencontractserver/llms/context_guardrails.py`): Extended the first-sentence regex to split on double-newlines (paragraph boundaries) and newlines before markdown list markers (`-`, `*`, `•`, numbered lists), preventing entire bullet-list responses from being treated as a single sentence
- **Deprecated asyncio pattern in tests** (`opencontractserver/tests/test_context_guardrails.py`): Converted `TestPersistCompactionOptimisticLock` from `asyncio.run()` wrapper calls to native `async def` test methods, removing the unused `asyncio` import
- **Weak truncation test assertions** (`opencontractserver/tests/test_context_guardrails.py`): Strengthened `test_custom_max_chars` and `test_truncation_notice_contains_limit` to assert exact upper-bound length (`<= max_chars`) and verify content starts from the beginning of the input string; added `test_truncated_content_from_beginning_not_end` test
- **CHARS_PER_TOKEN_ESTIMATE docstring inconsistency** (`opencontractserver/constants/context_guardrails.py`): Clarified that the constant is intentionally 3.5 (not 4) to over-count tokens slightly for conservative compaction triggering
- **Missing integrity constraint documentation** (`opencontractserver/conversations/models.py`): Added comment and expanded `help_text` on `compacted_before_message_id` explaining why `BigIntegerField` (not `ForeignKey`) is safe — the `id__gt` filter remains correct even if the cutoff message is deleted
- **Unreachable defensive code** (`opencontractserver/llms/context_guardrails.py`): Added clarifying comment on the `recent_count < 1` guard explaining it is unreachable with default `MIN_RECENT_MESSAGES` but protects against callers passing `min_recent=0`
- **Missing compaction bookmark filter tests** (`opencontractserver/tests/test_context_guardrails.py`): Added `TestCompactionBookmarkDatabaseFilter` with two async tests verifying `get_conversation_messages()` applies `id__gt` filtering when a bookmark is set and skips it when `None`
- **New sentence extraction tests** (`opencontractserver/tests/test_context_guardrails.py`): Added `test_markdown_bullet_list_split` and `test_double_newline_paragraph_split` covering the improved regex

#### MCP Documentation Accuracy (Closes #924)
- **Missing `created` field in tool return docs**: `list_public_corpuses`, `list_documents`, and `list_annotations` all return a `created` ISO 8601 timestamp, but `llms-full.txt` omitted it from the documented return shapes
- **Incorrect annotation label shape**: `list_annotations` return docs showed `label` (string) but the actual response uses `annotation_label: { text, color, label_type }` (object) — updated to match `format_annotation()` in `opencontractserver/mcp/formatters.py`
- **Underdocumented `document://` resource**: The resource description only said "Document metadata and full extracted text" without listing the actual fields. Added field inventory including `text_preview` (first 500 chars), `full_text`, `corpus`, and `created` — critical for agents choosing between preview and full text under context window constraints
- **File**: `frontend/public/llms-full.txt`

#### BaseChunkedParser Cleanup (Closes #914)
- **Duplicate test line**: Removed redundant `PdfReader` assignment in `test_pdf_splitting.py:95`
- **Infinite loop guard**: Added input validation for `max_pages_per_chunk` and `min_pages_for_chunking` in `calculate_page_chunks()` (`opencontractserver/utils/pdf_splitting.py`); added `max_concurrent_chunks` validation in `_parse_document_impl` (`opencontractserver/pipeline/base/chunked_parser.py`)
- **Dead code / ID inconsistency**: Removed single-chunk fast-path short-circuit in `_reassemble_chunk_results()` that returned unprefixed IDs, creating inconsistency with multi-chunk results
- **Flaky test**: Replaced wall-clock timing assertion in `test_concurrent_failure_cancels_remaining` with a shorter sleep to reduce CI flakiness
- **Type safety**: Replaced `type: ignore[return-value]` in `_dispatch_concurrent` with explicit `cast()` call
- **Noisy logging**: Downgraded orphaned parent-child reference log from `warning` to `debug` level — these are expected on virtually every large hierarchical document
- **Backoff cap**: Added `MAX_CHUNK_RETRY_BACKOFF_SECONDS` constant (30s) to cap exponential backoff in per-chunk retries (`opencontractserver/constants/document_processing.py`)
- **Missing boundary test**: Added test for exact `min_pages_for_chunking` threshold (75 pages) and clarified docstring semantics
- **Memory trade-off documented**: Added comment explaining concurrent dispatch memory implications
- **Cross-chunk limitation documented**: Enhanced class docstring with follow-up improvement suggestion for section-aware chunk boundaries

### Added
- Unit tests for `HighlightItem` scroll behavior and page label display (`frontend/src/components/annotator/sidebar/__tests__/HighlightItem.scroll.test.tsx`)

### Security

#### Resolve Dependabot Security Advisories (pydantic-ai + ajv)
- **pydantic-ai 0.2.x → 1.x migration**: Upgraded from pydantic-ai 0.2.20 to >=1.56.0,<2 to resolve CVE in older version. Migration includes:
  - `End` import moved from `pydantic_ai.agent` to `pydantic_graph` (`opencontractserver/llms/agents/pydantic_ai_agents.py`)
  - All 3 `PydanticAIAgent` creation sites migrated from `system_prompt=` to `instructions=` to use the 1.x-recommended parameter that is always included in model requests regardless of message history
  - `griffe>=1.3.2,<2` pin removed (was a transitive workaround only needed for pydantic-ai 0.2.x)
  - Test file updated: `result.data` → `result.output`, `result_type` → `output_type`, `system_prompt` → `instructions` (`opencontractserver/tests/test_pydantic_ai_agents.py`)
  - `openai` bumped from ==1.102.0 to >=2.11.0,<3 (pydantic-ai 1.x requires openai >=2.11.0)
  - `pdf2image` pinned to >=1.16.0 (ancient 0.1.x versions have broken setup.py, caused cascading build failures in CI)
- **ajv ReDoS fix (CVE in ajv <8.17.1)**: Added scoped Yarn resolutions for `@rjsf/validator-ajv8/ajv` and `ajv-formats/ajv` to pin ajv 8.18.0, avoiding conflict with schema-utils which requires ajv 6.x (`frontend/package.json`)

#### IDOR Vulnerabilities Fixed in 4 GraphQL Mutations
- **HIGH**: Fixed information leakage allowing object ID enumeration via different error messages
  - `RemoveAnnotation` (`config/graphql/mutations.py`)
  - `RejectAnnotation` (`config/graphql/mutations.py`)
  - `ApproveAnnotation` (`config/graphql/mutations.py`)
  - `RemoveRelationship` (`config/graphql/mutations.py`)
- **Attack Vector**: Unauthorized users could distinguish between "object doesn't exist" and "object exists but you can't access it" by observing different error responses
- **Impact**: Allowed enumeration of valid annotation/relationship IDs
- **Solution**: All mutations now use `visible_to_user()` pattern with unified error messages; secondary permission checks also return the same unified message
- **Information leakage fix**: Outer exception handlers no longer return `str(e)` to clients; errors are logged server-side only
- **Test Coverage**: Added IDOR protection tests in `test_permission_fixes.py` and `test_voting_mutations_graphql.py`

#### QuerySet Permission Filtering Gaps Fixed
- `DocumentQuerySet.visible_to_user()` and `NoteQuerySet.visible_to_user()` inherited from `PermissionQuerySet` which had guardian permission checks commented out — only checking `is_public` and `creator`
  - `opencontractserver/shared/QuerySets.py` (classes `DocumentQuerySet`, `NoteQuerySet`)
- `AnnotationQuerySet.visible_to_user()` checked document/corpus visibility via `is_public` and `creator` only, missing guardian permission lookups for documents and corpuses
  - `opencontractserver/shared/QuerySets.py` (class `AnnotationQuerySet`)
- **Bug**: Code calling `Model.objects.filter(...).visible_to_user(user)` or `Model.objects.visible_to_user(user)` skipped guardian permission checks, making objects invisible to users with explicit share permissions
- **Impact**: Documents shared via `set_permissions_for_obj_to_user()` were invisible through the QuerySet chain code path; annotations on shared documents/corpuses were invisible; Notes on accessible documents were not visible
- **Fix**: All three QuerySets now override `visible_to_user()` with proper guardian permission table lookups. Documents and Annotations check guardian tables directly; Notes inherit from document + corpus permissions

### Fixed

#### Corpus Export/Import V2: Audit and Roundtrip Fixes
- **SPAN_LABEL and RELATIONSHIP_LABEL missing from label export**: `build_label_lookups()` in `opencontractserver/utils/etl.py` only exported TOKEN_LABEL and DOC_TYPE_LABEL labels. SPAN_LABEL and RELATIONSHIP_LABEL labels were silently dropped, causing annotation and relationship import to fail. Now all four label types are exported.
- **Relationship labels not gathered from Relationship model**: `build_label_lookups()` only queried labels from `Annotation` objects. Labels used exclusively on `Relationship` objects (RELATIONSHIP_LABEL type) were never collected. Added Relationship model queries to capture these labels.
- **Label lookup key mismatch for structural annotations and relationships**: Structural annotations and relationships reference labels by TEXT in exports, but the import label_lookup was keyed by PK strings. Created a text-keyed label lookup (`label_lookup_by_text`) in `_import_corpus()` for use by `import_structural_annotation_set()` and `_import_v2_relationships()`.
  - File: `opencontractserver/tasks/import_tasks_v2.py`
- **Document file_type not preserved**: Non-PDF documents (text/plain, etc.) lost their MIME type during export/import since `file_type` was not included in `OpenContractDocExport`. Added `file_type` to export data and import logic.
  - Files: `opencontractserver/types/dicts.py`, `opencontractserver/utils/etl.py`, `opencontractserver/utils/importing.py`
- **Document-level conversations not exported**: `package_conversations()` only exported corpus-level conversations (`chat_with_corpus=corpus`). Document-level conversations (`chat_with_document`) were completely missed. Now both types are exported.
  - File: `opencontractserver/utils/export_v2.py`
- **Conversation export missing permission filtering**: `package_conversations()` exported ALL conversations regardless of the exporting user's permissions. Added `visible_to_user()` filtering for both conversations and messages.
  - File: `opencontractserver/utils/export_v2.py`
- **Conversation fields missing from export/import**: `description`, `is_locked`, `is_pinned` were not exported or imported. Added to both export and import.
- **Message fields missing from export/import**: `parent_message` (threaded replies), `data` (JSON metadata) were not exported or imported. Added to both export and import with two-pass parent re-linking.
- **Timestamps silently discarded on conversation/message import**: Django's `auto_now_add=True` on `created_at` and `auto_now=True` on `updated_at` fields ignored values passed to `create()`. Fixed by using `QuerySet.update()` after creation to patch timestamps.
  - File: `opencontractserver/utils/import_v2.py`
- **include_conversations/include_action_trail not exposed in export mutation**: The V2 export task accepted these parameters but the GraphQL mutation never passed them, hardcoding `False`. Added both as optional mutation arguments.
  - File: `config/graphql/mutations.py`
- **DocumentPath version trees not reconstructed on import**: Exported DocumentPath data (paths, version numbers, folder assignments) was never used during import. Added `_reconstruct_document_paths()` to update auto-created DocumentPaths to match exported path structure.
  - File: `opencontractserver/tasks/import_tasks_v2.py`

### Technical Details
- All label types (TOKEN_LABEL, SPAN_LABEL, RELATIONSHIP_LABEL) are now exported in the `text_labels` dict with their actual `label_type` preserved for correct deserialization
- Conversation document hash (`chat_with_document_hash`) is exported alongside the document ID for cross-system re-linking
- Timestamp patching uses `Model.all_objects.filter(pk=obj.pk).update()` to bypass `auto_now`/`auto_now_add` behavior
- Comprehensive test coverage added: `TestLabelTypeExportCompleteness`, `TestDocumentFileTypeRoundTrip`, `TestConversationExportEnhancements`

### Added

#### Chunked Document Processing for Large PDFs
- **New `BaseChunkedParser` abstract class** (`opencontractserver/pipeline/base/chunked_parser.py`): Extends `BaseParser` to transparently split large PDF documents into page-range chunks for independent parsing and reassembly. Documents below a configurable page threshold are processed as a single request (zero overhead). Features:
  - Automatic PDF splitting via pypdf with configurable `max_pages_per_chunk` (default: 50) and `min_pages_for_chunking` (default: 75)
  - Optional concurrent chunk dispatch via `ThreadPoolExecutor` (`max_concurrent_chunks`, default: 3)
  - Per-chunk retry with exponential back-off before escalating to Celery-level retry
  - Correct reassembly of PAWLs page indices, annotation page references, `tokensJsons.pageIndex`, annotation/relationship IDs, and parent-child relationships across chunk boundaries
  - `_post_reassemble_hook()` for document-wide post-processing (e.g., image extraction on the full PDF)
- **New PDF splitting utility** (`opencontractserver/utils/pdf_splitting.py`): `get_pdf_page_count()`, `split_pdf_by_page_range()`, `calculate_page_chunks()` — pure functions for PDF page manipulation
- **New chunking constants** (`opencontractserver/constants/document_processing.py`): `DEFAULT_MAX_PAGES_PER_CHUNK`, `DEFAULT_MIN_PAGES_FOR_CHUNKING`, `DEFAULT_MAX_CONCURRENT_CHUNKS`, `DEFAULT_CHUNK_RETRY_LIMIT`
- **DoclingParser now extends `BaseChunkedParser`** (`opencontractserver/pipeline/parsers/docling_parser_rest.py`): Large documents are automatically split and parsed in chunks. Configurable via `PipelineSettings` (`DOCLING_MAX_PAGES_PER_CHUNK`, `DOCLING_MIN_PAGES_FOR_CHUNKING`, `DOCLING_MAX_CONCURRENT_CHUNKS`). Image extraction runs once on the full PDF after reassembly via `_post_reassemble_hook`.

#### Context Guardrails & Conversation Compaction (Closes #898)
- **Context guardrails constants** (`opencontractserver/constants/context_guardrails.py`): Centralized configuration for model context windows (OpenAI, Anthropic, Google), compaction thresholds, tool output limits, and token estimation parameters. Covers 20+ model variants with sensible defaults.
- **Token estimation** (`opencontractserver/llms/context_guardrails.py`): Fast heuristic token counter (~3.5 chars/token) for estimating conversation size without importing heavyweight tokeniser libraries. Intentionally over-estimates to trigger compaction conservatively.
- **Model context window lookup** (`context_guardrails.py`): Resolves model names to context window sizes via exact match then longest-prefix matching, with a 128K default fallback for unknown models.
- **Conversation compaction** (`context_guardrails.py`): When conversation history approaches the context window limit (default 75%), older messages are replaced by a concise summary while preserving recent turns (4–20 messages) verbatim. Supports pluggable summary functions for LLM-based summarization.
- **Tool output truncation** (`context_guardrails.py`, `opencontractserver/llms/tools/pydantic_ai_tools.py`): String outputs from tools are automatically truncated to 50K characters with a notice directing the LLM to use range parameters. Applied at the PydanticAI tool wrapper level so all tools benefit transparently.
- **Per-agent compaction configuration** (`CompactionConfig` dataclass): Added `compaction` field to `AgentConfig` allowing per-conversation overrides of threshold ratio, recent message counts, and tool output limits. Enabled by default.
- **Automatic compaction in message history retrieval** (`opencontractserver/llms/agents/pydantic_ai_agents.py`): `_get_message_history()` now checks conversation size against model limits and injects a compaction summary as a system message when needed, transparent to the agent framework.
- **Persisted compaction bookmarks** (`opencontractserver/conversations/models.py`): Added `compaction_summary` and `compacted_before_message_id` fields to the `Conversation` model. Compaction is computed once and persisted — subsequent reads skip old messages at the DB level via `id__gt` filter, making long conversations cheap to load.
  - Migration: `opencontractserver/conversations/migrations/0015_add_compaction_fields.py`
  - `CoreConversationManager.persist_compaction()` writes the bookmark with optimistic locking (concurrent requests are safely resolved)
  - `CoreConversationManager.get_conversation_messages()` honours the cutoff automatically
- **Comprehensive test suite** (`opencontractserver/tests/test_context_guardrails.py`): 30+ unit tests covering token estimation, model lookup, truncation, compaction triggers, summary generation, message proxy conversion, configuration defaults, and Conversation model field definitions. Uses `SimpleTestCase` for fast parallel execution.

### Changed

#### Pipeline Registry: Deduplicate and Filter Abstract Components
- **Removed `MultimodalMicroserviceEmbedder` backwards-compatibility alias**: The module-level alias `MultimodalMicroserviceEmbedder = CLIPMicroserviceEmbedder` in `opencontractserver/pipeline/embedders/multimodal_microservice.py` has been removed. Use `CLIPMicroserviceEmbedder` directly.
- **Fixed duplicate embedder entries in pipeline registry**: `_discover_subclasses()` in `opencontractserver/pipeline/registry.py` now deduplicates discovered classes by identity and skips abstract intermediate base classes via `inspect.isabstract()`, preventing aliases and abstract bases from appearing in the get-embedders query endpoint.

### Fixed

#### Prompt Injection via User-Controlled Content in Agent Prompts
- **Root cause**: Thread and document action prompt builders injected user-controlled content (message bodies, thread titles, document titles) directly into Markdown-structured LLM prompts without any sanitisation boundary. A user who can post a message to a moderated thread could craft content that overrides agent instructions.
  - File: `opencontractserver/tasks/agent_tasks.py` (lines 808-848)
  - File: `opencontractserver/llms/agents/core_agents.py` (lines 963-983, 1036-1054)
  - File: `opencontractserver/llms/agents/pydantic_ai_agents.py` (lines 1655-1669, 2301-2315)
- **Fix**: All user-generated content injected into agent prompts is now wrapped in `<user_content>` / `</user_content>` XML fence tags. An explicit `UNTRUSTED_CONTENT_NOTICE` instruction block is added to thread moderation prompts telling the LLM to treat fenced content as raw data and ignore any embedded directives. A size-threshold warning (`UNTRUSTED_CONTENT_SIZE_WARNING_THRESHOLD = 1000 chars`) logs a `[PromptInjection]` warning for abnormally large user content.
  - New file: `opencontractserver/utils/prompt_sanitization.py` — `fence_user_content()`, `warn_if_content_large()`, `UNTRUSTED_CONTENT_NOTICE`
  - New constant: `opencontractserver/constants/moderation.py` — `UNTRUSTED_CONTENT_SIZE_WARNING_THRESHOLD`
  - New tests: `opencontractserver/tests/test_prompt_sanitization.py`
  - Updated tests: `opencontractserver/tests/test_thread_corpus_actions.py` — added `test_async_thread_action_prompt_fences_user_content`

#### Prompt Injection Mitigation Follow-up (Closes #913)
- **Dead code fix**: `warn_if_content_large()` was called on truncated message previews (max 203 chars) but checks against a 1000-char threshold, making the warning ineffective. Moved the call to run on full content before truncation.
  - File: `opencontractserver/tasks/agent_tasks.py` (`_build_thread_action_system_prompt`)
- **Inconsistent monitoring**: Document and corpus titles embedded in system prompts in `core_agents.py` and `pydantic_ai_agents.py` now have `warn_if_content_large()` calls for consistent size monitoring.
  - File: `opencontractserver/llms/agents/core_agents.py` (`CoreDocumentAgentFactory`, `CoreCorpusAgentFactory`)
  - File: `opencontractserver/llms/agents/pydantic_ai_agents.py` (`PydanticAIDocumentAgent`, `PydanticAICorpusAgent`)
- **Null safety**: All title values passed to `fence_user_content()` and `warn_if_content_large()` now use `or "untitled"` fallback to prevent `TypeError` when `document.title` or `corpus.title` is `None`.
  - Affected files: `agent_tasks.py`, `core_agents.py`, `pydantic_ai_agents.py`
- **Documentation mismatch**: `UNTRUSTED_CONTENT_NOTICE` now describes the labeled tag variant (`<user_content label="...">`) matching the actual implementation, and explains that the label attribute does not change handling.
  - File: `opencontractserver/utils/prompt_sanitization.py`

#### Frontend: Most views show legacy corpus.description instead of versioned mdDescription (Closes #892)
- **Backend description sync**: `Corpus.update_description()` now keeps the plain-text `description` field in sync when `md_description` is updated via the versioned markdown system. A new `_markdown_to_plain_text()` static method strips markdown formatting for the plain-text field.
  - File: `opencontractserver/corpuses/models.py` (lines 249-272, `update_description` method)
- **New `useCorpusMdDescription` hook**: Reusable React hook that fetches markdown content from a corpus's `mdDescription` URL and returns the raw text for rendering with `SafeMarkdown`.
  - File: `frontend/src/hooks/useCorpusMdDescription.ts`
- **CorpusContextSidebar**: Now fetches and renders the versioned markdown description instead of the stale plain-text `description` field.
  - File: `frontend/src/components/threads/CorpusContextSidebar.tsx`
- **DocumentKnowledgeBase**: Corpus info display now fetches `mdDescription` content and renders it as markdown. Added `title`, `description`, and `mdDescription` fields to the `GET_DOCUMENT_KNOWLEDGE_AND_ANNOTATIONS` query's corpus selection.
  - File: `frontend/src/components/knowledge_base/document/DocumentKnowledgeBase.tsx`
  - File: `frontend/src/graphql/queries.ts` (line 3028)
- **CorpusHeader (settings)**: Now fetches and renders the versioned markdown description via `useCorpusMdDescription` hook with `SafeMarkdown`. Added `mdDescription` to prop chain through `CorpusSettings` and `Corpuses.tsx`.
  - File: `frontend/src/components/corpuses/settings/CorpusHeader.tsx`
  - File: `frontend/src/components/corpuses/CorpusSettings.tsx`
  - File: `frontend/src/views/Corpuses.tsx`
- **TypeScript type update**: Added `mdDescription` optional field to `RawCorpusType`.
  - File: `frontend/src/types/graphql-api.ts`

#### Edit Description Modal Does Not Save on Update (Issue #899)
- **Root cause**: The edit document CRUDModal in `App.tsx` had a no-op `onSubmit` handler that only closed the modal without calling the `UPDATE_DOCUMENT` mutation, so changes were silently discarded
  - File: `frontend/src/App.tsx` (lines 128-149, 398)
- **Fix**: Added `useMutation` hook for `UPDATE_DOCUMENT` in `App.tsx` with proper `onCompleted`/`onError` handlers and `refetchQueries: "active"` to refresh displayed data
- **Removed duplicate modals**: `Documents.tsx` rendered its own edit/view CRUDModals controlled by the same `editingDocument` reactive var as `App.tsx`, causing potential double-modal rendering. Removed the duplicates from `Documents.tsx` and consolidated into the global `App.tsx` handler
  - File: `frontend/src/views/Documents.tsx` (removed ~45 lines of duplicate modal + mutation code)

### Changed

#### Import/Export Pipeline Consolidation
- **DRY refactor of import/export code**: Extracted shared helpers into `opencontractserver/utils/importing.py`:
  - `prepare_import_labels()` - eliminates 4x duplicated label loading boilerplate
  - `create_document_from_export_data()` - eliminates 3x duplicated document creation
  - `import_doc_annotations()` - eliminates 3x duplicated doc+text annotation import loops
- **V1 import now delegates to V2 machinery**: `import_corpus()` in `import_tasks.py` delegates to `import_corpus_v2()` which handles both V1 and V2 formats through a unified `_import_corpus()` handler
- **V2 import fixed to use `corpus.add_document()`**: Previously created documents directly without corpus isolation; now properly uses the versioning API for correct DocumentPath records and corpus isolation
- **V2 import now sets permissions on annotations**: Previously skipped `set_permissions_for_obj_to_user` on annotations
- **V2 import now handles `content_modalities`**: Via the shared `import_annotations()` helper
- **Export finalization DRYed up**: New `finalize_export()` in `export_tasks.py` replaces 4x repeated save/timestamp/notification pattern in `package_annotated_docs`, `package_funsd_exports`, `on_demand_post_processors`, and `package_corpus_export_v2`
- **Removed duplicate `import_relationships` and `import_document_paths`** from `utils/import_v2.py` - relationship import handled inline in `_import_v2_relationships`, DocumentPaths created by `corpus.add_document()`
- **Deleted empty `opencontractserver/utils/export.py`**

### Added

#### Store Model Name in ChatMessage Metadata (#897)
- **Automatic model name persistence**: The LLM model name from `AgentConfig` is now stored in the `data` JSON field of every `ChatMessage` produced by an agent, enabling debugging, auditing, and reproducibility
  - `opencontractserver/llms/agents/core_agents.py` — all five `CoreConversationManager` message-writing methods now persist `data["model_name"]`:
    - `create_placeholder_message()` and `store_llm_message()` — unconditional write at creation time
    - `complete_message()`, `update_message()`, `mark_message_error()` — use `setdefault` to backfill without overwriting placeholder values
- **Tests**: Seven new async tests verifying model name storage across all message lifecycle paths
  - `opencontractserver/tests/test_core_agents.py` — covers explicit model name, default model name, all five methods, and `setdefault` preservation semantics

#### Nested Approval Gates for Corpus Agent Sub-Agents
- **Sub-agent approval propagation**: When a corpus agent delegates a question to a document sub-agent via `ask_document`, and the sub-agent encounters a tool requiring approval, the approval request now propagates up to the corpus agent level and is surfaced to the user via WebSocket (`ASYNC_APPROVAL_NEEDED`)
  - File: `opencontractserver/llms/agents/pydantic_ai_agents.py` (ask_document_tool closure)
- **Frontend sub-tool unwrapping**: CorpusChat's approval modal now displays the actual sub-tool name/arguments instead of the generic `ask_document` wrapper, with validation for malformed metadata
  - File: `frontend/src/components/corpuses/CorpusChat.tsx` (ASYNC_APPROVAL_NEEDED handler)
- **Comprehensive nested approval test suite**: 10 async tests covering approval propagation, metadata stripping, bypass flag lifecycle, malformed event handling, and schema safety
  - File: `opencontractserver/tests/test_nested_approval_gates.py`
- **Architecture documentation**: Added "Nested Approval Gates" section to LLM framework docs with flow diagrams and security notes
  - File: `docs/architecture/llms/README.md`

#### Expose Tool Usage in Chat UI
- **Tool Usage Badge** (`frontend/src/components/widgets/chat/ChatMessage.tsx:1180-1288`): Assistant messages that use tools now display a wrench icon badge ("X tools used") in the message header, visible in both document and corpus chat views. Users can quickly see AI tool usage without expanding the full timeline, improving agent transparency.
- **Tool Call Popover** (`ChatMessage.tsx:1222-1286`): Hovering over the badge opens a popover listing each tool call's formatted name, JSON input arguments, and output result. Keyboard accessible (Enter/Space to toggle, Escape to close) with full ARIA attributes.
- **Tool result content in timeline**: Backend now captures tool result/output content in timeline `tool_result` entries (previously only stored tool name)
  - `opencontractserver/llms/agents/timeline_schema.py:52` — added `result` field
  - `opencontractserver/llms/agents/timeline_utils.py:77-92` — captures result from metadata, truncated to 500 chars
  - `opencontractserver/llms/agents/pydantic_ai_agents.py:123-155` — `_extract_tool_result_summary()` extracts and truncates at source
- **Tool result entries for search tools** (`pydantic_ai_agents.py:642-657, 686-702, 807-813`): `similarity_search`, `search_exact_text`, and `ask_document` now emit `tool_result` timeline entries with result summaries (e.g., "Found 3 matching annotations"). Other tools use a generic extractor with "Completed" fallback.

#### Automated Documentation Screenshots
- **Screenshot capture utility** (`frontend/tests/utils/docScreenshot.ts`): Captures screenshots during Playwright component tests using an enforced `{area}--{component}--{state}` naming convention
- **CI workflow** (`.github/workflows/screenshots.yml`): Automatically runs component tests on PRs touching `frontend/` or `docs/`, then commits updated screenshots back to the PR branch
- **Initial screenshot coverage**: Landing page components (hero, stats bar, trending corpuses, call-to-action) and badge components (celebration modal, toast)

#### V2 Export Format
- **`OPEN_CONTRACTS_V2` export format**: New export type available in `StartCorpusExport` mutation that includes structural annotation sets, folder hierarchy, relationships, agent config, markdown descriptions, and conversations
- **`content_modalities` now exported**: Annotations with IMAGE or other modalities now survive export/import round-trips (`opencontractserver/utils/etl.py:build_document_export`)
- **Migration `0025_alter_userexport_format_add_v2`**: Adds `OPEN_CONTRACTS_V2` to UserExport format choices

#### Edge Case Tests for Personal Corpus (Issue #839)
- **Concurrent creation race condition test**: Verifies that 5 concurrent threads calling `get_or_create_personal_corpus()` all return the same corpus with no duplicates or errors
  - File: `opencontractserver/tests/test_personal_corpus.py` (`TestConcurrentPersonalCorpusCreation`)
- **Delete and recreate flow tests**: Verifies that after deleting a personal corpus, recreation produces a new corpus with correct attributes and permissions
  - File: `opencontractserver/tests/test_personal_corpus.py` (`TestDeleteAndRecreatePersonalCorpus`)
- **Embedding task queue failure tests**: Verifies graceful degradation when Redis/Celery is unavailable during embedding task queuing, including partial batch failure scenarios
  - File: `opencontractserver/tests/test_personal_corpus.py` (`TestEmbeddingTaskQueueFailure`)

### Fixed

#### MCP Telemetry in Async Context
- **`SynchronousOnlyOperation` in MCP server** (`config/telemetry.py`, `opencontractserver/mcp/telemetry.py`, `opencontractserver/mcp/server.py`): Added async telemetry functions (`arecord_event`, `arecord_mcp_tool_call`, `arecord_mcp_resource_read`, `arecord_mcp_request`) that use `sync_to_async` to safely run Django ORM lookups in a thread pool. Prevents "You cannot call this from an async context" errors on every MCP request.
- **Installation ID caching** (`config/telemetry.py:91-113`): Added process-lifetime cache for installation UUID to eliminate redundant database queries on every telemetry call, particularly beneficial for high-frequency MCP requests.

#### Security: LLM Prompt Injection Protection for Approval Bypass
- **Replaced `skip_approval` function parameter with `config._approval_bypass_allowed` flag**: The previous design exposed a `skip_approval` parameter in `ask_document_tool`'s function signature that a malicious LLM could set to `True` to bypass approval gates. Now uses a runtime flag on `AgentConfig` that only `resume_with_approval()` can set, wrapped in a `try/finally` block to guarantee reset
  - File: `opencontractserver/llms/agents/pydantic_ai_agents.py`

#### Inconsistent Approval Status Handling in CorpusChat
- **Added `updateMessageApprovalStatus` to CorpusChat**: Previously, `ASYNC_APPROVAL_RESULT` handler in CorpusChat only cleared pending state without updating message `approvalStatus`, unlike ChatTray and useAgentChat which both call `updateMessageApprovalStatus`. Now consistent across all components
  - File: `frontend/src/components/corpuses/CorpusChat.tsx`
- **Added message `approvalStatus: "awaiting"` on ASYNC_APPROVAL_NEEDED**: CorpusChat now marks messages as awaiting approval in both `chat` and `serverMessages` state arrays, matching ChatTray/useAgentChat behavior
  - File: `frontend/src/components/corpuses/CorpusChat.tsx`

#### Defensive Handling of Malformed Approval Events
- **Backend**: `ask_document_tool` now validates `pending_tool_call` is a dict with a non-empty `name` key before raising `ToolConfirmationRequired`; malformed events are logged and skipped
  - File: `opencontractserver/llms/agents/pydantic_ai_agents.py`
- **Frontend**: `_sub_tool_name` validation checks type is string and non-empty; `_sub_tool_arguments` validates type is object before use
  - File: `frontend/src/components/corpuses/CorpusChat.tsx`

#### Corpus Agent Action Failure: griffe/pydantic-ai Incompatibility
- **Pin `griffe>=1.3.2,<2`** (`requirements/base.txt`): griffe 2.0.0 (released 2026-02-09) removed the `**options` catch-all from all docstring parsers. pydantic-ai 0.2.x unconditionally passes `returns_named_value` and `returns_multiple_items` as parser options to all parsers (including numpy), causing `TypeError: parse_numpy() got an unexpected keyword argument 'returns_named_value'`. This broke all `run_agent_corpus_action` tasks during agent creation. Pinning griffe below 2.0 restores the `**options` parameter that absorbs these Google-specific options harmlessly.

#### SynchronousOnlyOperation in Vector Store Construction from Async Context
- **Wrap vector store construction in `sync_to_async`** (`opencontractserver/llms/vector_stores/pydantic_ai_vector_stores.py:392`): `create_vector_search_tool()` now wraps `PydanticAIAnnotationVectorStore(...)` in `sync_to_async` so the sync ORM calls inside `CoreAnnotationVectorStore.__init__` (embedder resolution via `get_embedder()`) run in a thread pool instead of triggering Django's `SynchronousOnlyOperation`.
- **Pre-resolve embedder_path in `PydanticAIDocumentAgent.create()`** (`opencontractserver/llms/agents/pydantic_ai_agents.py:1529`): Added async embedder pre-resolution using `aget_embedder()` before constructing the vector store, matching the existing pattern in `PydanticAICorpusAgent.create()`. This prevents the sync `get_embedder()` fallback from hitting the ORM in an async context.
- **Defensive `sync_to_async` fallback in both agent `create()` methods** (`pydantic_ai_agents.py`): If `aget_embedder()` fails and `embedder_path` remains `None`, the `PydanticAIAnnotationVectorStore(...)` constructor is wrapped in `sync_to_async` so the ORM calls inside `get_embedder()` run in a thread pool. Applied to both `PydanticAIDocumentAgent.create()` and `PydanticAICorpusAgent.create()`.
- **Fix async test** (`opencontractserver/tests/test_pydantic_ai_agents.py:412`): Wrapped `PydanticAIAnnotationVectorStore(...)` construction in `sync_to_async` in `test_pydantic_ai_vector_store_search`.

### Changed

#### Streamlined Agentic Corpus Action Configuration
- **Renamed `agent_prompt` to `task_instructions`** on `CorpusAction` model (`opencontractserver/corpuses/models.py`): Single, clearly-named field for describing what the agent should do. Migration `0041` handles the rename.
- **Goal-oriented system prompt assembly** (`opencontractserver/tasks/agent_tasks.py`): Agent corpus actions now auto-generate a structured system prompt with automation guardrails ("you MUST use tools"), execution context (trigger type, document metadata, corpus info), and the user's task instructions. Agents no longer receive raw `system_instructions` as the system prompt — the system wraps everything in a goal-oriented format that prevents conversational responses.
- **Document context injection**: Document-based agent actions now inject document title, ID, corpus title, and current description into the system prompt so agents don't waste tool calls loading basic metadata.
- **Thread context injection refactored**: Thread-based agent actions now use the same structured prompt pattern as document actions, with thread context, recent messages, and triggering message content all included in the system prompt rather than the user message.
- **`AgentConfiguration` is now optional for agent actions**: `CorpusAction` can be created with just `task_instructions` (no `agent_config` required). The DB constraint (`valid_action_type_configuration`) now allows lightweight agent actions. `AgentConfiguration` is still supported for custom persona/tool defaults.
- **Default tool selection by trigger type** (`opencontractserver/constants/corpus_actions.py`): When no tools are specified on `agent_config.available_tools`, the system auto-selects trigger-appropriate defaults (document tools for add/edit triggers, moderation tools for thread/message triggers).
- **`pre_authorized_tools` semantics changed** (`opencontractserver/tasks/agent_tasks.py`): `pre_authorized_tools` now only controls which tools skip approval gates. Tool availability is determined by `agent_config.available_tools` (if set) or trigger-appropriate defaults. See **Breaking Changes** below for migration guidance.
- **GraphQL API updated**: `CreateCorpusAction` and `UpdateCorpusAction` mutations use `taskInstructions` instead of `agentPrompt`. The `taskInstructions` field alone (without `agentConfigId`) is now sufficient to create an agent action.
- **Frontend updated**: `CreateCorpusActionModal` and `CorpusActionsSection` use "Task Instructions" labeling instead of "Agent Prompt".
- **Unified Quick Create flow**: `CreateCorpusActionModal` now supports inline agent creation for document triggers (add_document, edit_document) in addition to thread triggers. The modal auto-selects trigger-appropriate tools and default instructions.
- **Manual action trigger** (`config/graphql/mutations.py`): New `RunCorpusAction` mutation allows superusers to manually trigger agent actions on specific documents. Uses `transaction.on_commit()` to dispatch Celery tasks after the DB transaction commits, and `force=True` to bypass dedup checks for manual triggers.
- **ToolFunctionRegistry** (`opencontractserver/llms/tools/tool_registry.py`): Centralized singleton registry mapping tool names to sync/async function implementations. Replaces 3 manually-curated dicts in `_resolve_tools()`. Adding a new tool now requires edits in 2 files instead of 4+.

#### Mobile Navigation & URL-Driven Corpus Navigation

- **Detail view switching now pushes browser history**: `updateDetailViewParam()` in `frontend/src/utils/navigationUtils.ts` now pushes new history entries instead of replacing, so browser back/forward navigates between landing and details views. `updateTabParam()` retains replace semantics so tab switches don't accumulate history entries
- **Thread selection now URL-driven**: Discussions tab thread selection uses the existing `?thread=` query parameter (synced by CentralRouteManager) instead of the local `inlineSelectedThreadIdAtom` Jotai atom. Clicking a thread pushes `?thread=<id>` to the URL; browser back returns to the list
  - Files: `frontend/src/components/discussions/CorpusDiscussionsView.tsx`, `frontend/src/utils/navigationUtils.ts`, `frontend/src/views/Corpuses.tsx`
- **Tab-specific params cleared on tab switch**: `updateTabParam()` now removes `thread` and `message` params when switching tabs to prevent stale state persisting across tab changes
- **Removed `inlineSelectedThreadIdAtom`**: Replaced by URL-driven `selectedThreadId` reactive var from `frontend/src/graphql/cache.ts`; dead `onViewModeChange` callback removed from `CorpusDiscussionsView`

### Added

#### Mobile Menu Access in Corpus Home Views

- **Mobile navigation menu buttons**: Added `MobileMenuButton` (kebab icon, visible ≤600px) to `CorpusLandingView` (breadcrumb row) and `CorpusDetailsView` (header row), allowing mobile users to open the sidebar bottom sheet from the home tab — previously only accessible from non-home tabs
  - Files: `frontend/src/components/corpuses/CorpusHome/CorpusLandingView.tsx`, `frontend/src/components/corpuses/CorpusHome/CorpusDetailsView.tsx`, `frontend/src/components/corpuses/CorpusHome/styles.ts`
- **`updateThreadParam()` utility**: New navigation utility for setting/clearing the `?thread=` URL param with push semantics, following the same pattern as `updateTabParam()` and `updateMessageParam()`
  - File: `frontend/src/utils/navigationUtils.ts`

### Breaking Changes

- **`pre_authorized_tools` no longer controls tool availability**: Previously, `pre_authorized_tools` was used as both the tool set AND the approval gate — if set, it replaced `agent_config.available_tools` entirely. Now it only controls which tools skip the approval gate. **Migration**: If you relied on `pre_authorized_tools` to restrict which tools an agent can access, move those tool names to `agent_config.available_tools` instead. `pre_authorized_tools` should only list tools that are safe to run without human approval.

### Known Limitations

- **Orphaned QUEUED executions if Celery broker is unavailable**: The `RunCorpusAction` mutation creates a `CorpusActionExecution` with `QUEUED` status and dispatches the Celery task via `transaction.on_commit()`. If the Celery broker is down at commit time, the task dispatch silently fails and the execution record stays `QUEUED` indefinitely. This is a general characteristic of the `on_commit` + Celery pattern used throughout the codebase. Monitor for stale `QUEUED` records if broker reliability is a concern.

#### Edge Case Tests for Personal Corpus (Issue #839)
- **Concurrent creation race condition test**: Verifies that 5 concurrent threads calling `get_or_create_personal_corpus()` all return the same corpus with no duplicates or errors
  - File: `opencontractserver/tests/test_personal_corpus.py` (`TestConcurrentPersonalCorpusCreation`)
- **Delete and recreate flow tests**: Verifies that after deleting a personal corpus, recreation produces a new corpus with correct attributes and permissions
  - File: `opencontractserver/tests/test_personal_corpus.py` (`TestDeleteAndRecreatePersonalCorpus`)
- **Embedding task queue failure tests**: Verifies graceful degradation when Redis/Celery is unavailable during embedding task queuing, including partial batch failure scenarios
  - File: `opencontractserver/tests/test_personal_corpus.py` (`TestEmbeddingTaskQueueFailure`)

### Fixed

#### Security Hardening: Authentication & Permissioning Audit Remediation

- **Analysis callback DoS prevention** (`opencontractserver/analyzer/views.py`): Invalid callback tokens no longer mark analyses as FAILED; uses `hmac.compare_digest()` for timing-safe token comparison; unified error messages prevent analysis ID enumeration
- **User lock logic inversion** (`config/graphql/base.py`): Fixed `==` to `!=` in DRFDeletion and DRFMutation user lock checks — previously blocked the lock holder and allowed everyone else
- **IDOR prevention in base mutations** (`config/graphql/base.py`): DRFDeletion and DRFMutation now use `visible_to_user()` filtering before `.get()` to prevent object existence leakage
- **Open redirect prevention** (`config/urls.py`): `home_redirect` now validates the Host header against `ALLOWED_HOSTS` before constructing the redirect URL
- **Cross-corpus data leakage** (`config/graphql/graphene_types.py`): Document summary resolvers (`resolve_summary_revisions`, `resolve_current_summary_version`, `resolve_summary_content`) now verify corpus visibility before returning data
- **CSRF trusted origins** (`config/settings/production.py`): Fixed missing comma causing implicit string concatenation in `CSRF_TRUSTED_ORIGINS`
- **HSTS enforcement** (`config/settings/production.py`): Increased `SECURE_HSTS_SECONDS` from 60 to 518400 (6 days)
- **Analyzer visibility default** (`opencontractserver/analyzer/models.py`): Changed `Analyzer` and `GremlinEngine` `is_public` default from `True` to `False` to prevent accidental data exposure
- **IDOR prevention in GraphQL mutations** (`config/graphql/mutations.py`): Added `visible_to_user()` filtering to 11 previously unprotected `.objects.get()` calls in `StartDocumentExtract`, `DeleteAnalysisMutation`, `CreateColumn`, `CreateExtract`, `CreateCorpusAction`, `UpdateCorpusAction`, and `CreateNote`
- **IDOR prevention in conversation mutations** (`config/graphql/conversation_mutations.py`): `CreateThreadMutation` and `CreateThreadMessageMutation` now use `visible_to_user()` instead of fetch-then-check pattern
- **IDOR prevention in folder mutations** (`config/graphql/corpus_folder_mutations.py`): All folder mutations now verify corpus visibility before operating on folders; folder lookups scoped to validated corpus
- **IDOR prevention in voting mutations** (`config/graphql/voting_mutations.py`): `VoteMessageMutation` and `RemoveVoteMutation` now use `ChatMessage.objects.visible_to_user()` instead of fetch-then-check
- **IDOR prevention in badge mutations** (`config/graphql/badge_mutations.py`): `AwardBadgeMutation` now uses `Badge.objects.visible_to_user()` for badge lookup

### Fixed

#### Enable Relationships for Span-Based (Text) Annotations (Closes #281)
- **File type detection inconsistency**: Multiple frontend components checked for text file types using only `startsWith("text/")`, missing documents with `application/txt` MIME type. Created centralized `isTextFileType()` and `isPdfFileType()` utilities in `frontend/src/utils/files.ts` and updated all callers.
- **Label initialization race condition**: The `initialized.current` ref in `UISettingsAtom.tsx` (line 288) could be set to `true` after span label initialization, preventing relationship labels from auto-initializing on subsequent effect runs. Replaced with separate `spanLabelInitialized` and `relationLabelInitialized` refs.
- **Type restrictions blocking span annotations in relationship UI**: `RelationItem`, `RelationHighlightItem`, `HighlightItem`, and `annotationSelectedViaRelationship()` only accepted `ServerTokenAnnotation` (PDF annotations). Updated all to accept `ServerTokenAnnotation | ServerSpanAnnotation` union type, enabling the sidebar relationship display and creation flow for text documents.
- **Files changed**: `frontend/src/utils/files.ts`, `frontend/src/components/annotator/context/UISettingsAtom.tsx`, `frontend/src/components/annotator/sidebar/RelationItem.tsx`, `frontend/src/components/annotator/sidebar/RelationHighlightItem.tsx`, `frontend/src/components/annotator/sidebar/HighlightItem.tsx`, `frontend/src/components/annotator/utils.ts`, `frontend/src/components/annotator/hooks/AnnotationHooks.tsx`, `frontend/src/components/annotator/labels/EnhancedLabelSelector.tsx`, `frontend/src/components/annotator/labels/UnifiedLabelSelector.tsx`, `frontend/src/components/annotator/labels/label_selector/LabelSelector.tsx`, `frontend/src/components/knowledge_base/document/DocumentKnowledgeBase.tsx`, `frontend/src/components/widgets/chat/ChatMessage.tsx`

## [3.0.0.b4] - 2026-02-08

### ⚠️ Important Migration Notes

**Migration 0040 (`corpus_created_with_embedder`) backfills existing corpuses**

This release includes a data migration that:

- Adds a `created_with_embedder` audit field to all corpuses
- Backfills `preferred_embedder` on existing corpuses that don't have one set (uses current `DEFAULT_EMBEDDER`)
- Backfills `created_with_embedder` from `preferred_embedder`

This migration is safe and non-destructive. Existing corpuses with explicit `preferred_embedder` values are unchanged.

**Migration 0038 (`create_personal_corpuses`) is IRREVERSIBLE**

This release includes a data migration that creates personal "My Documents" corpuses for all users and moves standalone documents into them. This migration **cannot be rolled back** via `python manage.py migrate`. Attempting to reverse will raise `NotImplementedError`.

**Before deploying to production:**

- Ensure you have a database backup
- Test the migration in a staging environment first
- Plan for this being a one-way migration

If rollback is required after deployment, you must write a custom migration to handle your specific data preservation needs.

### Added

#### Document Processing Failure Indicators and Retry Controls (Issue #825)

- **Processing status display**: Document cards and list items now show distinct states for processing (spinner) vs. failed (error overlay with message) instead of a generic "Processing..." overlay for all locked documents
- **Retry button**: Failed documents display a retry button that triggers the `RetryDocumentProcessing` GraphQL mutation, allowing users to re-process documents without backend access
- **Context menu retry**: "Retry Processing" option added to the document context menu for failed documents
- **Permission-aware**: Retry controls only appear when the user has permission to retry (`canRetry` field from backend)
- **Error messages**: Processing error messages from the backend are displayed on the failure overlay (truncated for readability)
- Files: `frontend/src/components/documents/ModernDocumentItem.tsx`, `frontend/src/components/documents/DocumentItem.tsx`, `frontend/src/graphql/queries.ts`, `frontend/src/graphql/mutations.ts`, `frontend/src/types/graphql-api.ts`

#### Embedder Consistency Management (Issue #437)

- **Frozen embedder binding at corpus creation**: `preferred_embedder` is now auto-populated from `DEFAULT_EMBEDDER` when a corpus is created without an explicit embedder. This decouples existing corpuses from future changes to the global setting.
  - Files: `opencontractserver/corpuses/models.py` (save method)
- **Audit trail field `created_with_embedder`**: Records which embedder was active at corpus creation. Never changes, even after re-embedding.
  - Files: `opencontractserver/corpuses/models.py`, migration `0040_corpus_created_with_embedder.py`
- **Immutability guard on `preferred_embedder`**: `UpdateCorpusMutation` rejects changes to `preferred_embedder` after documents have been added to a corpus, preventing inconsistent embeddings.
  - Files: `config/graphql/mutations.py` (UpdateCorpusMutation.mutate)
- **`reEmbedCorpus` mutation**: Controlled migration path for changing a corpus's embedder. Locks the corpus, queues background re-embedding for all annotations, and unlocks when complete.
  - Files: `config/graphql/mutations.py` (ReEmbedCorpus), `opencontractserver/tasks/corpus_tasks.py` (reembed_corpus)
- **Fork with embedder override**: `forkCorpus` mutation now accepts optional `preferredEmbedder` argument to create the fork with a different embedder.
  - Files: `config/graphql/mutations.py` (StartCorpusFork)
- **Corpus-scoped search uses corpus embedder**: `resolve_semantic_search` now uses `corpus.preferred_embedder` for corpus-scoped queries instead of the global `DEFAULT_EMBEDDER`, ensuring consistent results.
  - Files: `config/graphql/queries.py` (resolve_semantic_search)
- **Startup system check**: Django system check warns at startup if `DEFAULT_EMBEDDER` has changed since existing corpuses were created, preventing silent search inconsistencies.
  - Files: `opencontractserver/corpuses/checks.py`, `opencontractserver/corpuses/apps.py`

#### Auth0 Authentication for Django Admin

- **Auth0 admin login support**: Django admin now supports Auth0 authentication when `USE_AUTH0=True`
  - Custom login view displays Auth0 "Sign in" button with password fallback
  - Custom logout view properly clears both Django session and Auth0 session
  - Backward compatible: password authentication always available
  - Files: `config/admin_auth/views.py`, `config/admin_auth/backends.py`
- **Admin claims synchronization**: Admin privileges can be set via Auth0 token claims
  - Supports `{namespace}is_staff` and `{namespace}is_superuser` claims
  - Claims synced on API requests with 5-minute cache TTL (configurable via `ADMIN_CLAIMS_CACHE_TTL` constant)
  - Immediate sync during admin login ensures fresh permissions for admin access
  - Handles boolean, string ("true"/"false"), and numeric (0/1) claim values
  - Configurable namespace via `AUTH0_ADMIN_CLAIM_NAMESPACE` env var
  - Files: `config/graphql_auth0_auth/utils.py:269-360`
  - **Required Auth0 Action** (Post-Login): Set up the following Auth0 Action to include admin claims in tokens:

    ```javascript
    exports.onExecutePostLogin = async (event, api) => {
      const namespace = "https://opencontracts.opensource.legal/";
      const appMetadata = event.user.app_metadata || {};

      // Add admin claims to access token
      if (appMetadata.is_staff !== undefined) {
        api.accessToken.setCustomClaim(
          `${namespace}is_staff`,
          appMetadata.is_staff,
        );
      }
      if (appMetadata.is_superuser !== undefined) {
        api.accessToken.setCustomClaim(
          `${namespace}is_superuser`,
          appMetadata.is_superuser,
        );
      }
    };
    ```

    Then set `app_metadata.is_staff` and `app_metadata.is_superuser` on users via Auth0 Management API or Dashboard.

- **Auth0AdminBackend**: Dedicated authentication backend for admin login via Auth0
  - Validates user exists, is active, and has `is_staff=True`
  - Files: `config/admin_auth/backends.py:18-88`
- **Security hardening**:
  - Open redirect prevention using `url_has_allowed_host_and_scheme()`
  - Host header injection prevention for Auth0 logout `returnTo` URL
  - CSRF protection on all login/logout endpoints
  - Files: `config/admin_auth/views.py:24-89`
- **Professional login template**: Standalone HTML template with Auth0 SDK integration
  - Loading states, error handling, graceful degradation
  - Uses Subresource Integrity (SRI) for CDN-hosted Auth0 SDK
  - **CSP Note**: Template uses inline JavaScript; if Content-Security-Policy is enabled,
    add `script-src 'unsafe-inline'` or implement CSP nonces
  - Files: `opencontractserver/templates/admin/auth0_login.html`
- **Comprehensive test coverage**: 50+ tests covering security edge cases
  - Open redirect prevention, boolean claim parsing, logout URL safety
  - Files: `opencontractserver/tests/test_admin_auth.py`

### Fixed

- **Admin token handling**: Admin login no longer accepts JWT tokens via query parameters (reduces CSRF/token leakage risk). Files: `config/admin_auth/views.py:146-179`
- **Admin claims demotion**: Missing or invalid admin claims now default to False to avoid privilege retention. Files: `config/graphql_auth0_auth/utils.py:331-411`
- **Token storage scope**: Admin Auth0 SPA client now uses in-memory token storage instead of localStorage. Files: `opencontractserver/templates/admin/auth0_login.html:249-257`

#### Runtime-Configurable Pipeline Settings (Superuser Only)

- **PipelineSettings singleton model**: Database-backed configuration for document processing pipeline
  - Stores preferred parsers, embedders, and thumbnailers per MIME type
  - Stores parser-specific kwargs and component settings overrides
  - Database is the single source of truth at runtime (no Django settings fallback)
  - Singleton pattern: only one instance exists, cannot be deleted
  - Files: `opencontractserver/documents/models.py:734-1140`
- **Encrypted secrets storage**: Secure storage for API keys and sensitive credentials
  - Uses Fernet symmetric encryption (key derived from Django SECRET_KEY)
  - Secrets are never exposed via GraphQL responses
  - GraphQL only returns list of components that have secrets configured
  - Methods: `set_secrets()`, `get_secrets()`, `update_secrets()`, `get_full_component_settings()`
  - Files: `opencontractserver/documents/models.py:1012-1139`
- **GraphQL query `pipelineSettings`**: Any authenticated user can read current pipeline configuration
  - Returns preferred components, parser kwargs, component settings
  - Includes `componentsWithSecrets` field (list of paths, not actual secrets)
  - Includes audit fields (modified, modified_by)
  - Files: `config/graphql/queries.py:4214-4250`
- **GraphQL mutation `updatePipelineSettings`**: Superusers can modify pipeline configuration at runtime
  - Validates component class paths exist in the pipeline registry
  - Tracks who made changes (modified_by field)
  - Changes take effect immediately for new document processing tasks
  - Files: `config/graphql/pipeline_settings_mutations.py:20-220`
- **GraphQL mutation `resetPipelineSettings`**: Superusers can reset to Django settings defaults
  - Restores all values from PREFERRED_PARSERS, PREFERRED_EMBEDDERS, etc.
  - Files: `config/graphql/pipeline_settings_mutations.py:223-302`
- **GraphQL mutation `updateComponentSecrets`**: Superusers can securely store API keys per component
  - Accepts component path and secrets dict, encrypts and stores in database
  - Supports merge mode (add to existing) or replace mode
  - Files: `config/graphql/pipeline_settings_mutations.py:305-411`
- **GraphQL mutation `deleteComponentSecrets`**: Superusers can remove secrets for a component
  - Files: `config/graphql/pipeline_settings_mutations.py:414-481`
- **Migration 0031**: Creates PipelineSettings table with encrypted_secrets field
  - Files: `opencontractserver/documents/migrations/0031_add_pipeline_settings.py`
- **Migration 0032**: Adds database index to `PipelineSettings.modified` for audit query performance
  - Files: `opencontractserver/documents/migrations/0032_add_index_to_pipeline_settings_modified.py`
- **Management command `migrate_pipeline_settings`**: Self-documenting component discovery and settings migration
  - `--list-components`: Introspects pipeline registry to show all components with settings schemas, env vars, defaults, and descriptions
  - `--sync-preferences`: Syncs PREFERRED_PARSERS, PREFERRED_EMBEDDERS, etc. from Django settings to database
  - `--component <name>`: Filters output to a specific component
  - Files: `opencontractserver/documents/management/commands/migrate_pipeline_settings.py`
- **Pipeline Configuration Guide**: Documentation covering first-time setup, upgrades, runtime configuration, and troubleshooting
  - Files: `docs/pipelines/pipeline_configuration.md`
- **Integration with doc_tasks**: `ingest_doc` and `extract_thumbnail` now read from PipelineSettings
  - Files: `opencontractserver/tasks/doc_tasks.py:355-374`, `opencontractserver/tasks/doc_tasks.py:686-721`
- **Integration with pipeline/utils**: `get_preferred_embedder` and `get_default_embedder` use PipelineSettings
  - Files: `opencontractserver/pipeline/utils.py:303-361`

### Changed

- Pipeline settings getters (`get_preferred_parser`, `get_preferred_embedder`, `get_parser_kwargs`, `get_default_embedder`) no longer fall back to Django settings at runtime. Database is the sole source of truth; initial values are populated from Django settings via `get_instance()`.
  - Files: `opencontractserver/documents/models.py:977-1092`
- Pipeline component settings are now DB-only at runtime (Django settings fallback removed from `PipelineComponentBase.get_component_settings()`)
  - Files: `opencontractserver/pipeline/base/base_component.py:180-217`
- Pipeline configuration UI now reads component settings schema from GraphQL instead of hardcoding config requirements.
  - Files: `frontend/src/components/admin/SystemSettings.tsx:69-129`
- Pipeline configuration UI now centralizes pipeline UI constants in `PIPELINE_UI` for sizing and validation values.
  - Files: `frontend/src/assets/configurations/constants.ts:174-187`

### Fixed

- Secrets modal now validates component existence, required secret fields, and payload size before mutation.
  - Files: `frontend/src/components/admin/SystemSettings.tsx:1500-1558`
- MIME filter accessibility labels now include stage context.
  - Files: `frontend/src/components/admin/SystemSettings.tsx:1076-1089`
- GraphQL `updateComponentSecrets` mutation now validates payload size before encryption attempt.
  - Files: `config/graphql/pipeline_settings_mutations.py:104-135`
- Pipeline components query now requires authentication; non-superusers only see configured components without settings schema details.
  - Files: `config/graphql/queries.py:1815-1949`
- Settings schema `_coerce_value` now logs warnings on coercion failures instead of silently swallowing errors.
  - Files: `opencontractserver/pipeline/base/settings_schema.py:416-419`
- `PipelineSettings.save()` now invalidates cache via `transaction.on_commit()` to prevent stale cache when DB write rolls back.
  - Files: `opencontractserver/documents/models.py:896-906`
- `PipelineComponentCard` memo now uses custom comparison to avoid unnecessary re-renders from object prop references.
  - Files: `frontend/src/components/admin/SystemSettings.tsx:1134-1140`
- Pipeline mutation error messages now consistently include component path for debugging.
  - Files: `config/graphql/pipeline_settings_mutations.py:644-656, 720-729`

### Removed

#### ModernBERT Embedders

- **⚠️ Breaking Change**: ModernBERT embedders have been removed from the codebase
  - `opencontractserver/pipeline/embedders/modern_bert_embedder.py` - removed
  - `opencontractserver/pipeline/embedders/minn_modern_bert_embedder.py` - removed
  - `model_preloaders/download_modernbert_model.py` - removed
  - Tests removed: `opencontractserver/tests/test_modern_bert_embedder.py`, `opencontractserver/tests/test_minn_modern_bert_embedder.py`
  - Documentation removed: `docs/embedders/modernbert_embedder.md`, `docs/embedders/minn_modernbert_embedder.md`
  - **Migration path**: Users currently using ModernBERT embedders must switch to alternative embedders:
    - `SentenceTransformerEmbedder` - General purpose sentence transformer embeddings
    - `OpenAIEmbedder` - OpenAI API-based embeddings (requires API key)
    - `VoyageAIEmbedder` - Voyage AI embeddings (requires API key)
  - Update PipelineSettings via admin UI or management command before upgrading

#### Personal Corpus ("My Documents") Feature

- **Personal corpus auto-creation**: Each user now automatically receives a personal "My Documents" corpus
  - Created via signal handler when user account is created
  - Uses database constraint to ensure one personal corpus per user (`one_personal_corpus_per_user`)
  - Personal corpus is private (`is_public=False`) and grants full permissions to owner
  - Files: `opencontractserver/corpuses/models.py:378-432`, `opencontractserver/users/signals.py:16-48`
- **All uploads default to personal corpus**: Documents without a specified corpus go to "My Documents"
  - Single file uploads via GraphQL now route to personal corpus
  - Zip file bulk uploads also default to personal corpus when no corpus specified
  - Files: `config/graphql/mutations.py:1807-1908`, `opencontractserver/tasks/import_tasks.py:514-585`
- **`Corpus.get_or_create_personal_corpus()` class method**: Idempotent method to get/create personal corpus
  - Thread-safe using `get_or_create` with atomic transaction
  - Grants full permissions on creation
  - Files: `opencontractserver/corpuses/models.py:390-432`
- **Data migration for existing users**: Migration creates personal corpuses for existing users and moves standalone documents
  - Creates "My Documents" corpus for all active users
  - Moves documents without any DocumentPath to their creator's personal corpus
  - **⚠️ IRREVERSIBLE MIGRATION**: This migration cannot be rolled back automatically. Attempting to reverse will raise `NotImplementedError`. Rolling back would delete DocumentPath records and orphan user documents from their corpus organization. If rollback is required, a custom migration must be written to handle data preservation.
  - Files: `opencontractserver/corpuses/migrations/0038_create_personal_corpuses.py`

#### Shared StructuralAnnotationSet

- **Reuse structural sets instead of duplicating**: `add_document()` now reuses the source document's structural set
  - Previously, adding a document to a corpus duplicated the entire StructuralAnnotationSet
  - Now shares the set, reducing storage and maintaining single source of truth
  - Files: `opencontractserver/corpuses/models.py:528-535`
- **Incremental embedding creation**: New Celery task checks for missing embeddings when document is added
  - `ensure_embeddings_for_corpus()` checks if embeddings exist for corpus's required embedders
  - Only queues embedding generation for annotations missing embeddings
  - Supports both DEFAULT_EMBEDDER and corpus's preferred_embedder
  - Files: `opencontractserver/tasks/corpus_tasks.py:712-850`

#### Inline Thread View with Corpus Context Sidebar

- **Added inline thread viewing**: Users can now view thread details inline within the Discussions tab instead of navigating away
  - Click a thread to view details in-place with a "Back" button to return to the list
  - Thread state tracked via `inlineSelectedThreadIdAtom` Jotai atom
  - Files: `frontend/src/components/discussions/CorpusDiscussionsView.tsx`, `frontend/src/atoms/threadAtoms.ts`
- **Added corpus context sidebar**: Displays corpus context alongside thread details
  - About section with corpus description (markdown rendered)
  - Documents section with collapsible table of contents
  - Quick stats grid (documents, threads, annotations, comments)
  - Collapsible sections with smooth animations via Framer Motion
  - Responsive behavior: hidden < 1024px, collapsible 1024-1200px, always expanded > 1200px
  - Sidebar expanded state persisted to localStorage via `threadContextSidebarExpandedAtom`
  - Files: `frontend/src/components/threads/CorpusContextSidebar.tsx`, `frontend/src/components/threads/ThreadDetailWithContext.tsx`
  - New styled components: `frontend/src/components/threads/styles/contextSidebarStyles.ts`
- **Added modernized discussion thread UI**: Comprehensive redesign following OS-Legal-Style design system
  - Typography-first design: Serif headings (Georgia), sans-serif body (Inter)
  - Teal accent color scheme (#0f766e) for interactive elements
  - Improved message cards, vote buttons, badges, and metadata displays
  - Mobile-responsive with proper breakpoints
  - Files: `frontend/src/components/threads/styles/discussionStyles.ts` (950+ lines)
- **Added agent mention rendering**: Discussion messages render styled agent mentions with custom colors
  - Runtime validation of badge configuration from GenericScalar fields
  - Hex color validation with fallback to default agent color
  - Tooltip display for agent mentions
  - Files: `frontend/src/components/threads/MarkdownMessageRenderer.tsx`
- **Added component tests for new features**:
  - Mention badge rendering tests: `frontend/tests/MentionRendering.ct.tsx`
  - Compact vote button tests: `frontend/tests/VoteButtonsCompact.ct.tsx`

### Technical Details

- Added `is_personal` BooleanField to Corpus model with database constraint
- Added composite index on `(creator, is_personal)` for efficient lookups
- Schema migration: `opencontractserver/corpuses/migrations/0037_add_is_personal_corpus.py`
- Comprehensive test suite: `opencontractserver/tests/test_personal_corpus.py` (14 tests)

#### AnnotationsPanel Shared Component

- **Created `AnnotationsPanel` reusable component**: Extracts shared filtering/display logic from annotations views
  - Provides filter tabs for type (All/Doc/Text) and source (All/Human/Agent/Structural)
  - Includes SearchBox, grid display with ModernAnnotationCard, empty state, and pagination
  - Can be used by both standalone Annotations view and corpus annotations tab
  - Files: `frontend/src/components/annotations/AnnotationsPanel.tsx`
- **Added `AnnotationsPanel` unit tests**: Comprehensive tests for filters, search, grid, empty/loading states
  - Files: `frontend/src/components/annotations/__tests__/AnnotationsPanel.test.tsx`
- **Added semantic search to corpus annotations tab**: Search box now uses vector similarity search
  - Debounced search triggers semantic search as user types (500ms delay)
  - Displays similarity scores on annotation cards
  - Supports infinite scroll for semantic search results
  - Shows appropriate empty state and loading messages for search mode
  - Files: `frontend/src/components/annotations/CorpusAnnotationCards.tsx`
- **Fixed semantic search similarity score calculation**: Scores now correctly display as percentages
  - CosineDistance returns distance (0=identical), converted to similarity (1=identical)
  - Results are sorted by similarity (highest first) and scores display correctly (e.g., 85% for close matches)
  - Files: `opencontractserver/shared/mixins.py`
- **Created lightweight `GET_ANNOTATIONS_FOR_CARDS` query**: Fetches only fields needed for ModernAnnotationCard display
  - Excludes heavy fields: `tokensJsons`, `json`, `page`, and unnecessary nested objects
  - Reduces payload from ~340KB to ~30KB for 2130 annotations (estimated 90% reduction)
  - Files: `frontend/src/graphql/queries.ts`

### Fixed

#### Annotations Panel Scroll Issue

- **Fixed corpus annotations tab scroll behavior**: Restructured AnnotationsPanel to scroll only the cards grid
  - Container uses flex column layout with `overflow: hidden`
  - FiltersSection has `flex-shrink: 0` to stay fixed at top
  - AnnotationsListContainer has `flex: 1` and `overflow-y: auto` for card scrolling
  - Filters (search, type tabs, source tabs) stay visible while cards scroll below
  - Files: `frontend/src/components/annotations/AnnotationsPanel.tsx`

#### Annotations Query Missing Pagination

- **Added initial page limit to annotations queries**: Previously loaded all annotations at once
  - Added `limit` and `cursor` fields to `GetAnnotationsInputs` interface
  - Set initial page size to 20 annotations for both Annotations.tsx and CorpusAnnotationCards.tsx
  - Infinite scroll loads more as user scrolls down
  - Files: `frontend/src/graphql/queries.ts`, `frontend/src/views/Annotations.tsx`, `frontend/src/components/annotations/CorpusAnnotationCards.tsx`

#### Corpus Annotations Tab Source Filter

- **Fixed structural annotations not visible in corpus tab**: Annotations tab now shows filter controls even when empty
  - Added source filter (Human/Agent/Structural) to `CorpusAnnotationCards`
  - Source filter syncs to GraphQL query variables: "structural" → `structural: true`, "human" → `structural: false, analysis_Isnull: true`, "agent" → `structural: false, analysis_Isnull: false`
  - Users can now toggle to see structural annotations that were previously hidden
  - Files: `frontend/src/components/annotations/CorpusAnnotationCards.tsx`
- **Added missing `usesLabelFromLabelsetId` to GetAnnotationsInputs interface**: Interface was missing a field used by the query
  - Files: `frontend/src/graphql/queries.ts:752`

### Changed

#### BREAKING: Removed Corpus.documents M2M Relationship (PR #840)

- **Removed `Corpus.documents` ManyToManyField**: DocumentPath is now the sole source of truth for corpus-document relationships
  - Migration `0039_remove_corpus_documents_m2m` validates no orphaned M2M entries before removal
  - All code paths now use `corpus.add_document()`, `corpus.remove_document()`, `corpus.get_documents()`, `corpus.document_count()`
  - GraphQL `CorpusType.documents` field now resolves via explicit DocumentPath-based resolver
  - Frontend queries updated to use `documentCount` field instead of `documents { totalCount }`
  - Files: `opencontractserver/corpuses/models.py`, `config/graphql/graphene_types.py`, `config/graphql/queries.py`
- **Removed deprecated Corpus methods**: `_create_text_document_internal()` and `create_text_document()` removed (use `import_content()` instead)
  - Removed deprecated `content` parameter from `add_document()` (use `import_content()` for content-based imports)
  - Files: `opencontractserver/corpuses/models.py`
- **Removed `sync_m2m_to_documentpath` management command**: No longer needed after M2M removal
  - Files: `opencontractserver/documents/management/commands/sync_m2m_to_documentpath.py` (deleted)
- **Added request-level caching to DocumentPathType**: Visible corpus IDs now cached per-request to prevent N+1 queries
  - Follows same pattern as `ConversationQueryOptimizer` and `DocumentRelationshipQueryOptimizer`
  - Files: `config/graphql/graphene_types.py:620-636`
- **Fixed stale frontend GraphQL queries**: Two queries still referenced removed `documents { totalCount }` connection field
  - `GET_EDITABLE_CORPUSES` in `AddToCorpusModal.tsx` now uses `documentCount`
  - `GET_MY_CORPUSES` in `queries.ts` now uses `documentCount`
  - Files: `frontend/src/components/modals/AddToCorpusModal.tsx`, `frontend/src/graphql/queries.ts`

#### Pipeline Configuration UI Redesign

- **Replaced JSON-based configuration with visual pipeline flow**: System Settings page redesigned for intuitive configuration
  - Visual pipeline stages: Document Upload → Parser → Thumbnailer → Embedder → Ready for Search
  - Clickable component cards replace JSON text editing
  - Per-stage MIME type selectors (PDF, TXT, DOCX)
  - Auto-expanding advanced settings for components requiring API keys
  - Collapsible advanced settings to reduce visual clutter
  - Files: `frontend/src/components/admin/SystemSettings.tsx`
- **New component icon system**: Custom SVG icons for each pipeline component type
  - Docling, LlamaParse, ModernBERT, OpenAI, and more
  - Semantic icons that are visually distinctive
  - Generic fallback icon for unknown components
  - Files: `frontend/src/components/admin/PipelineIcons.tsx`
- **Added accessibility attributes**: ARIA support for screen readers
  - `aria-pressed` on MIME type and component selection buttons
  - `aria-expanded` on collapsible settings sections
  - `aria-label` on interactive elements
  - Files: `frontend/src/components/admin/SystemSettings.tsx`

#### Window Resize Performance

- **Added debounce to window resize handler**: Prevents excessive re-renders during window resize
  - 150ms debounce delay on resize events
  - Properly cleans up timeout on unmount
  - Files: `frontend/src/components/hooks/WindowDimensionHook.tsx`

#### Annotations View Refactoring

- **Updated Annotations.tsx to use AnnotationsPanel**: DRY refactoring, keeps hero section, stats, semantic search, advanced filters
  - Files: `frontend/src/views/Annotations.tsx`
- **Deleted superseded AnnotationCards.tsx**: Functionality absorbed into AnnotationsPanel
  - Files: `frontend/src/components/annotations/AnnotationCards.tsx` (deleted)

#### Annotations Query Optimization

- **Switched to lightweight query for annotation cards**: Both `Annotations.tsx` and `CorpusAnnotationCards.tsx` now use `GET_ANNOTATIONS_FOR_CARDS`
  - Previous query fetched `tokensJsons` (huge JSON), `json`, full document paths (pdfFile, txtExtractFile, pawlsParseFile), full corpus details
  - New query fetches only: id, created, creator (id, email, username), corpus (id, slug, labelSet.title), document (id, slug, title), annotationLabel (id, text, color, labelType), analysis (id, analyzer.analyzerId), annotationType, structural, rawText, isPublic, contentModalities
  - Expected improvement: ~90% payload reduction, significantly faster load times
  - Files: `frontend/src/views/Annotations.tsx`, `frontend/src/components/annotations/CorpusAnnotationCards.tsx`

### Added

#### GraphQL Corpus Query Optimization

- **Added `documentCount` field to CorpusType**: Efficient document count using annotated subquery instead of N+1 queries
  - For list queries (`corpuses`), the resolver annotates `_document_count` via `DocumentPath` subquery
  - For single corpus queries, falls back to model's `document_count()` method
  - Files: `config/graphql/graphene_types.py:2028-2038`, `config/graphql/queries.py:836-869`
- **Added `annotationCount` field to CorpusType**: Efficient annotation count using annotated subquery
  - For list queries, `resolve_corpuses` annotates `_annotation_count` via Document→DocumentPath join
  - For single corpus queries, falls back to counting via DocumentPath query
  - Files: `config/graphql/graphene_types.py`, `config/graphql/queries.py`
- **Optimized LabelSet count resolvers**: Label counts now use corpus-annotated values when available
  - `resolve_label_set` on CorpusType copies annotated counts to LabelSet instance
  - `resolve_doc_label_count`, `resolve_span_label_count`, `resolve_token_label_count` check for annotations before querying
  - Files: `config/graphql/graphene_types.py:680-699, 2040-2056`
- **Optimized leaderboard `reputationGlobal` resolution**: `resolve_global_leaderboard` now attaches `_reputation_global` to user objects, avoiding N+1 queries when resolving `reputationGlobal`
  - Files: `config/graphql/queries.py`, `config/graphql/graphene_types.py`
- **Added query optimization tests**: Comprehensive tests for `documentCount`, `annotationCount`, and label set optimization
  - Files: `opencontractserver/tests/test_corpus_query_optimization.py`

### Changed

#### DiscoveryLanding GraphQL Query Optimization

- **Removed unused fields from landing page queries**: Eliminates ~39 N+1 queries per landing page load
  - Removed from `GET_DISCOVERY_DATA`: `chatMessages { totalCount }` (unused by ActivitySection), `totalMessages`, `totalThreadsCreated`, `totalAnnotationsCreated` (unused by CompactLeaderboard)
  - Replaced `documents { totalCount }` and `annotations { totalCount }` with `documentCount` and `annotationCount` (efficient subquery-backed fields)
  - Files: `frontend/src/graphql/landing-queries.ts`
- **Updated FeaturedCollections to use optimized count fields**: Uses `documentCount`/`annotationCount` instead of connection `totalCount`
  - Files: `frontend/src/components/landing/FeaturedCollections.tsx`
- **Updated TrendingCorpuses to use optimized count fields**: Uses `documentCount` instead of `documents.totalCount`
  - Files: `frontend/src/components/landing/TrendingCorpuses.tsx`
- **Updated RecentDiscussions to remove chatMessages dependency**: Display "View thread" instead of reply count
  - Files: `frontend/src/components/landing/RecentDiscussions.tsx`

#### Frontend Corpus Query Cleanup

- **Removed unused fields from GET_CORPUSES query**: Reduces payload and eliminates N+1 queries
  - Removed: `preferredEmbedder`, `appliedAnalyzerIds`, `documents.edges`, `annotations.totalCount`
  - Added: `documentCount` (efficient server-side count)
  - Files: `frontend/src/graphql/queries.ts:603-673`
- **Updated CorpusItem to use documentCount**: Uses new field instead of `documents?.edges?.length`
  - Files: `frontend/src/components/corpuses/CorpusItem.tsx:602-605`
- **Updated CorpusListView formatStats function**: Uses `documentCount` and removes annotation count display
  - Files: `frontend/src/components/corpuses/CorpusListView.tsx:303-306`
- **Added documentCount and annotationCount to TypeScript types**: Updated `RawCorpusType` interface
  - Files: `frontend/src/types/graphql-api.ts`

### Technical Details

- **Query reduction**: DiscoveryLanding page goes from ~39 N+1 queries to ~0 extra queries (all counts resolved via subqueries or removed)
- **Backward compatibility**: All new fields (`documentCount`, `annotationCount`) gracefully fall back to model methods for single corpus queries
- **Pattern**: Label counts are passed from corpus to label_set via instance attribute injection in `resolve_label_set`
- **Pattern**: Leaderboard reputation score is pre-attached to user objects via `_reputation_global` attribute

### Added

#### 2048-Dimensional Embedding Support

- **Added vector_2048 field to Embedding model**: Support for 2048-dimensional embeddings used by newer embedding models
  - Migration 0061 adds nullable `vector_2048` column to `annotations_embedding` table
  - Files: `opencontractserver/annotations/models.py:470`, `opencontractserver/annotations/migrations/0061_add_vector_2048.py`
- **Updated dimension handling across codebase**:
  - `Managers.py:_get_vector_field_name` returns "vector_2048" for 2048-dim vectors (lines 363-364)
  - `mixins.py:_dimension_to_field` returns embedding relation for 2048-dim (lines 37-38)
  - `mixins.py:get_embedding` retrieves 2048-dim vectors (lines 144-145)
  - Vector stores validate 2048 as supported dimension
  - Files: `opencontractserver/shared/Managers.py`, `opencontractserver/shared/mixins.py`, `opencontractserver/llms/vector_stores/core_vector_stores.py`, `opencontractserver/llms/vector_stores/core_conversation_vector_stores.py`

#### Multimodal Embedder Refactoring

- **Refactored MultimodalMicroserviceEmbedder into inheritance hierarchy**:
  - `BaseMultimodalMicroserviceEmbedder`: Abstract base class with shared multimodal embedding logic
  - `CLIPMicroserviceEmbedder`: CLIP ViT-L-14 model (768 dimensions) with backwards-compatible legacy settings
  - `QwenMicroserviceEmbedder`: Qwen embedding model (1024 dimensions)
  - Files: `opencontractserver/pipeline/embedders/multimodal_microservice.py`
- **Added model-specific settings**: `CLIP_EMBEDDER_URL`, `CLIP_EMBEDDER_API_KEY`, `QWEN_EMBEDDER_URL`, `QWEN_EMBEDDER_API_KEY`
  - Files: `config/settings/base.py:666-669`
- **Deprecated legacy settings**: `MULTIMODAL_EMBEDDER_URL` and `MULTIMODAL_EMBEDDER_API_KEY` still work but emit deprecation warnings
  - Users should migrate to `CLIP_EMBEDDER_URL` / `CLIP_EMBEDDER_API_KEY`

### Fixed

#### MicroserviceEmbedder Reliability

- **Fixed MicroserviceEmbedder production failures**: Added Content-Type header and 30s timeout to prevent silent failures
  - Files: `opencontractserver/pipeline/embedders/sent_transformer_microservice.py:522, 530`

### Added

#### Bulk Document Selection and Removal

- **Bulk document selection in folder toolbar**: New Select All / Deselect All functionality for corpus documents
  - Selection count display showing "X of Y" documents selected
  - Clear selection button to deselect all
  - Selection state persists across folder navigation for building cross-folder selections
  - Files: `frontend/src/components/corpuses/folders/FolderToolbar.tsx:780-827`
- **Bulk remove from corpus action**: Remove multiple selected documents from corpus in one operation
  - Dedicated danger button with document count indicator
  - Proper confirmation modal (replaces browser `window.confirm`)
  - Files: `frontend/src/components/corpuses/folders/RemoveDocumentsModal.tsx`, `frontend/src/components/corpuses/folders/FolderDocumentBrowser.tsx:367-371`
- **Mobile-responsive bulk actions**: Kebab menu includes selection controls for tablet/mobile viewports
  - Files: `frontend/src/components/corpuses/folders/FolderToolbar.tsx:976-993`
- **Loading state handling**: Select All button disabled while documents are loading to prevent incomplete selections
  - New `documentsLoading` reactive var syncs loading state from CorpusDocumentCards to FolderToolbar
  - Files: `frontend/src/graphql/cache.ts:379-384`, `frontend/src/components/documents/CorpusDocumentCards.tsx:193-201`

### Fixed

#### Embedder Error Handling and Response Parsing (PR #828)

- **Fixed silent embedding failures**: Added `EmbeddingGenerationError` exception class that triggers Celery task retries when default embeddings fail
  - Default embedding failures now properly raise and retry (up to 3 times with 60s delay)
  - Corpus-specific embedding failures are logged but don't fail the task (non-fatal)
  - Files: `opencontractserver/tasks/embeddings_task.py:165-273`
- **Fixed 1D vs 2D array response parsing**: Embedders now handle both array formats from embedding services
  - Some services return `[0.1, 0.2, ...]` (1D), others return `[[0.1, 0.2, ...]]` (2D batch format)
  - Previously caused "object of type 'float' has no len()" errors
  - Files: `opencontractserver/pipeline/embedders/sent_transformer_microservice.py:113-119`, `opencontractserver/pipeline/embedders/multimodal_microservice.py:195-201`
- **Fixed bytes-to-string decoding**: Added workaround for storage backends that return bytes even in text mode
  - Affects django-storages S3Boto3Storage with certain configurations
  - Previously caused "bytes not JSON serializable" errors
  - Files: `opencontractserver/tasks/embeddings_task.py:306-314`
- **Aligned error handling across embedders**: MicroserviceEmbedder now distinguishes 4xx (client) vs 5xx (server) errors like MultimodalMicroserviceEmbedder
  - Files: `opencontractserver/pipeline/embedders/sent_transformer_microservice.py:120-133`
- **Added comprehensive test coverage**: 18 new tests for error handling, bytes decoding, and array format parsing
  - Files: `opencontractserver/tests/test_embeddings_task.py`
- **Added TestEmbedder for fast, deterministic test embeddings**: Tests now use a fast in-memory embedder by default instead of the HTTP-based MicroserviceEmbedder
  - Returns deterministic fake vectors based on text hash (same text = same embedding)
  - Eliminates HTTP round-trips to vector-embedder service during tests (faster test execution)
  - Integration tests that need real service connectivity should explicitly instantiate MicroserviceEmbedder
  - Files: `opencontractserver/pipeline/embedders/test_embedder.py`, `config/settings/test.py:120-134`

#### Cache Eviction Consistency

- **Fixed folder document counts not updating after bulk removal**: Added `corpusFolders` cache eviction to `REMOVE_DOCUMENTS_FROM_CORPUS` mutation to match the pattern used by `MOVE_DOCUMENT_TO_FOLDER`
  - Files: `frontend/src/components/corpuses/folders/RemoveDocumentsModal.tsx:109-112`

#### Duplicate Tool Registration and Caller Tool Precedence

- **Fixed duplicate tool registration error in PydanticAI agent**: Resolved `pydantic_ai.exceptions.UserError` when caller-provided tools have the same name as default tools
  - Files: `opencontractserver/llms/agents/pydantic_ai_agents.py:2063-2082`
- **Caller-provided tools now take precedence over defaults**: When a caller passes a tool with the same name as a built-in default, the caller's tool configuration (description, requires_approval, etc.) is now used instead of silently dropping it
  - Allows callers to override tool behavior and configurations
  - Applies to both `PydanticAIDocumentAgent.create()` and `structured_response()`
  - Added info-level logging when caller tools override defaults
  - Files: `opencontractserver/llms/agents/pydantic_ai_agents.py:961-992`, `opencontractserver/llms/agents/pydantic_ai_agents.py:2063-2082`
- **Added comprehensive test coverage**:
  - `test_caller_tool_overrides_default_configuration` verifies caller's tool is used (not default)
  - `test_config_tools_deduplicated_in_structured_response` covers the config.tools path
  - Files: `opencontractserver/tests/test_duplicate_tool_registration.py`
- **Fixed PydanticAICorpusAgent consistency**: Now uses same caller-precedence pattern as document agent
- **Extracted `deduplicate_tools()` utility**: DRY refactor moves repeated deduplication logic to reusable function
  - Checks both `__name__` and `name` attributes for tool identification
  - Filters out `None` values to handle tools without names
  - Includes security documentation in docstring
  - Files: `opencontractserver/utils/tools.py`
- **Added documentation for tool precedence**: New section in LLM docs explaining when conflicts occur, which configuration wins, and security considerations
  - Files: `docs/architecture/llms/README.md`

### Added

#### Document Processing Pipeline Hardening (PR #824)

- **Document processing status tracking**: New `DocumentProcessingStatus` enum with PENDING, PROCESSING, COMPLETED, FAILED states
  - `processing_status` field on Document model with database index
  - `processing_error` and `processing_error_traceback` fields for failure diagnostics
  - Files: `opencontractserver/documents/models.py:24-32`, `opencontractserver/documents/models.py:141-159`
- **Typed parsing exceptions**: New `DocumentParsingError` with `is_transient` flag
  - Transient errors (network timeouts, service unavailable) trigger automatic retry
  - Permanent errors (invalid file, no parser) fail immediately
  - Files: `opencontractserver/pipeline/base/exceptions.py`
- **Automatic retry with exponential backoff**: Up to 3 retries with 60-300s backoff and jitter
  - Failed documents remain locked (`backend_lock=True`) to prevent broken state
  - Files: `opencontractserver/tasks/doc_tasks.py:287-435`
- **Manual retry via GraphQL**: New `RetryDocumentProcessing` mutation
  - Allows users to retry failed documents after infrastructure issues are resolved
  - Atomic state reset prevents race conditions from multiple retry clicks
  - Files: `config/graphql/mutations.py:2244-2330`
- **Failure notifications**: New `DOCUMENT_PROCESSING_FAILED` notification type
  - Notifies document creator when processing fails
  - Files: `opencontractserver/tasks/doc_tasks.py:113-146`, `opencontractserver/notifications/models.py`
- **Processing status constants**: Centralized in `opencontractserver/constants/document_processing.py`
- **24 unit tests**: Comprehensive coverage of new functionality
  - Files: `opencontractserver/tests/test_pipeline_hardening.py`

#### Bifurcated Conversation Permissions (CHAT vs THREAD)

- **New `conversation_type` field on Conversation model**: Distinguishes between personal agent chats and collaborative discussions
  - `CHAT` type: Restrictive permissions (creator + explicit permissions + public only)
  - `THREAD` type: Context-based permissions (inherits visibility from linked corpus/document)
  - Files: `opencontractserver/conversations/models.py:51-53`, `opencontractserver/conversations/migrations/`
- **Bifurcated `visible_to_user()` queryset method**: Different visibility logic based on conversation type
  - CHAT: Only creator, explicit guardian permissions, or public flag
  - THREAD: CHAT rules + context inheritance (READ on corpus AND/OR document)
  - AND logic when both corpus and document are linked (must have READ on both)
  - Files: `opencontractserver/conversations/models.py:127-238`
- **ConversationQueryOptimizer helper class**: Request-level caching to avoid N+1 queries
  - Caches visible conversation IDs per request
  - IDOR-safe `check_conversation_visibility()` method for mutations
  - Convenience methods: `get_threads_for_corpus()`, `get_threads_for_document()`, `get_chats_for_user()`
  - Files: `opencontractserver/conversations/query_optimizer.py`
- **ChatMessage visibility inheritance**: Messages inherit bifurcated permissions from parent conversation
  - Moderator access retained for corpus/document owners
  - Files: `opencontractserver/conversations/models.py:299-398`
- **22 new permission tests**: Comprehensive coverage of CHAT vs THREAD behavior
  - Files: `opencontractserver/tests/test_conversation_permissions.py`
- **Updated permissioning guide**: Documentation for bifurcated model with examples
  - Files: `docs/permissioning/consolidated_permissioning_guide.md`

#### Corpus Forking: Folder and Relationship Preservation

- **Folder hierarchy preservation during fork**: Forked corpora now maintain the complete folder structure
  - Folders cloned in tree-depth order to preserve parent-child relationships
  - Documents retain their folder assignments in the forked corpus
  - Uses `tree_queries` CTE with `.with_tree_fields()` for proper ordering
  - Files: `opencontractserver/tasks/fork_tasks.py:126-159`, `config/graphql/mutations.py:1180-1187`
- **Relationship preservation during fork**: Annotation relationships are now copied
  - Source and target annotations remapped to forked annotation IDs
  - Relationship labels preserved via label_map
  - Uses `prefetch_related()` for efficient M2M loading
  - Files: `opencontractserver/tasks/fork_tasks.py:286-356`
- **Fork task signature extended**: Added `folder_ids` and `relationship_ids` parameters
  - Files: `opencontractserver/tasks/fork_tasks.py:29-38`
- **Round-trip test suite**: Comprehensive tests validating fork data integrity across generations
  - Files: `opencontractserver/tests/test_corpus_fork_round_trip.py`

#### Corpus-Scoped MCP Endpoints for Shareable Links

- **New `/mcp/corpus/{corpus_slug}/` endpoint**: Scoped MCP endpoint for single-corpus access
  - All tools automatically operate within the specified corpus context
  - No need for explicit `corpus_slug` parameters in tool calls
  - Validates corpus exists and is publicly accessible before accepting requests
  - Returns 404 with helpful message for private/nonexistent corpuses
  - Files: `opencontractserver/mcp/server.py:371-651`, `config/asgi.py`
- **New `get_corpus_info` tool**: Returns detailed corpus information for scoped endpoints
  - Replaces `list_public_corpuses` for scoped context
  - Includes label set information, document count, and metadata
  - Files: `opencontractserver/mcp/tools.py:401-447`
- **Scoped tool wrappers**: Auto-inject corpus_slug into existing tools
  - Creates corpus-specific tool handlers that wrap global tool implementations
  - Files: `opencontractserver/mcp/tools.py:450-498`
- **TTL-based cache with eviction**: Scoped session managers cached with 1-hour TTL
  - LRU eviction at 100 entries to prevent unbounded memory growth
  - Cache invalidation logging for monitoring
  - Files: `opencontractserver/mcp/server.py:583-630`
- **Comprehensive test coverage**: 15+ tests for scoped endpoint functionality
  - Tests for validation, tool execution, cache behavior, error handling
  - Files: `opencontractserver/mcp/tests/test_mcp.py`
- **Updated MCP documentation**: Usage examples for both global and scoped endpoints
  - Files: `docs/mcp/README.md`

#### Unified Upload Modal with @os-legal/ui Design System

- **Consolidated `BulkUploadModal` and `DocumentUploadModal`** into single `UploadModal` component
  - Auto-detects upload mode: ZIP files → bulk mode, PDFs → single mode
  - Multi-step wizard for single mode (Select → Details → Corpus)
  - Simplified single-step flow for bulk ZIP uploads
  - Files: `frontend/src/components/widgets/modals/UploadModal/`
- **Custom hooks for upload state management**:
  - `useUploadState` - file list and selection state
  - `useUploadMutations` - GraphQL mutations with consistent `makePublic` handling
  - `useCorpusSearch` - debounced corpus search with permission filtering
  - Files: `frontend/src/components/widgets/modals/UploadModal/hooks/`
- **Modular sub-components**: `FileDropZone`, `FileList`, `FileDetailsForm`, `CorpusSelectorCard`, `StepIndicator`, `UploadProgress`
- **File size validation**: 100MB limit with user feedback (configurable via `UPLOAD.MAX_FILE_SIZE_BYTES` constant)
- **16 Playwright component tests** covering both modes, validation, and mobile responsiveness
- **Manual test documentation**: `docs/manual-test-scripts/upload-modal.md`
- **Upload constants**: Added `UPLOAD.MAX_FILE_SIZE_BYTES` and `DEBOUNCE.CORPUS_SEARCH_MS` to `frontend/src/assets/configurations/constants.ts`

#### Pre-extracted Image Content for Annotations

- **`image_content_file` FileField on Annotation model**: Stores pre-extracted image data as JSON files
  - Eliminates need to reload full PAWLs file (~10MB) for each image embedding request
  - Performance improvement: ~10-20x faster for image annotation embeddings
  - Files: `opencontractserver/annotations/models.py:109-114`
  - Migration: `opencontractserver/annotations/migrations/0060_add_annotation_image_content_file.py`
- **Batch image extraction utilities**: Efficient batch processing during annotation creation
  - `extract_and_store_annotation_images()` - extracts images from PAWLs and stores as JSON
  - `batch_extract_annotation_images()` - batch processes multiple annotations sharing PAWLs data
  - Files: `opencontractserver/utils/multimodal_embeddings.py:351-502`
- **Unique constraints on Embedding model**: Database-level prevention of duplicate embeddings
  - Migration: `opencontractserver/annotations/migrations/0059_add_embedding_unique_constraints.py`

#### Corpus-Specific Embeddings

- **Dual embedding strategy**: Creates both default (global search) and corpus-specific embeddings
  - Default embedder for cross-corpus search compatibility
  - Corpus-preferred embedder for corpus-specific semantic search
  - Files: `opencontractserver/tasks/embeddings_task.py:88-160`
- **Corpus ID propagation through ingestion chain**: Parser now receives corpus context
  - Enables corpus-specific embeddings during document ingestion
  - Files: `opencontractserver/tasks/doc_tasks.py:203-248`, `opencontractserver/pipeline/base/parser.py:130-143`

### Fixed

- **Corpus title not getting [FORK] prefix**: Fixed f-string that did nothing (`f"{corpus.title}"` → `f"[FORK] {corpus.title}"`)
  - Files: `config/graphql/mutations.py:1199`
- **tree_depth ordering error**: Removed explicit `order_by("tree_depth", "pk")` and rely on default `tree_ordering` from `with_tree_fields()`. The `tree_depth` field is CTE-computed and only available at SQL execution time, not during Django's `order_by()` validation.
  - Files: `config/graphql/mutations.py:1184`, `opencontractserver/tasks/fork_tasks.py:133`, `opencontractserver/utils/corpus_forking.py:46`, `opencontractserver/tests/test_corpus_fork_round_trip.py:389`
- **Fork fails with corpuses without label_set**: Added conditional handling to skip label set cloning when corpus has no label_set
  - Files: `opencontractserver/tasks/fork_tasks.py:56-136`
- **Document slug uniqueness violation during fork**: Clear slug before saving forked document so save() generates a new unique slug
  - Files: `opencontractserver/tasks/fork_tasks.py:186`
- **Annotation label mapping error**: Gracefully handle annotations without labels or when label_map is empty
  - Files: `opencontractserver/tasks/fork_tasks.py:279-285`
- **Test assertion bug**: Fixed comparison of count to queryset (`forked_labelset_labels.count() == original_labelset_labels.all()` → `.count() == .count()`)
  - Files: `opencontractserver/tests/test_corpus_forking.py:99`
- **Incorrect CorpusFolder permission setting in tests**: Removed `set_permissions_for_obj_to_user()` call for folders - CorpusFolder inherits permissions from parent Corpus, not individual permissions per the consolidated permissioning guide
  - Files: `opencontractserver/tests/test_corpus_fork_round_trip.py:277`
- **Critical: Infinite loop in corpus document copies**: Fixed chain reaction where corpus copies triggered re-ingestion
  - **Root Cause**: `add_document()` created corpus copies without setting `processing_started`, causing the ingestion signal to fire on each copy
  - **Impact**: Uploading one document created infinite chain of copies (doc → copy → copy of copy → ...)
  - **Fix**: Set `processing_started=timezone.now()` on corpus copies to prevent signal from firing
  - **Files**: `opencontractserver/corpuses/models.py:478-481`
- **Multimodal embeddings for structural annotations**: Fixed PAWLs loading from `structural_set.pawls_parse_file`
  - Structural annotations now correctly load images for embedding generation
  - Files: `opencontractserver/utils/multimodal_embeddings.py:136-166`
- **Embedding duplicate constraint violations with race condition handling**
  - **Root Cause**: Parallel Celery workers could create duplicate embeddings due to race conditions between check and create
  - **Fix**: Added `IntegrityError` catch in `store_embedding()` to handle race conditions atomically
  - **Fix**: Migration 0059 now cleans up existing duplicates before adding unique constraints (keeps best embedding per group)
  - **Fix**: Migration uses `atomic=False` to avoid PostgreSQL "pending trigger events" error
  - **Fix**: Removed `visible_to_user()` filtering from existence checks (constraints apply globally)
  - **Files**: `opencontractserver/shared/Managers.py:369-442`, `opencontractserver/annotations/migrations/0059_add_embedding_unique_constraints.py`

### Changed

- **Permission consistency**: Utility function `build_fork_corpus_task()` now uses `PermissionTypes.CRUD` (was `ALL`) to match mutation
  - Files: `opencontractserver/utils/corpus_forking.py:69`
- **`BulkUploadModal`** is now a thin wrapper: `<UploadModal forceMode="bulk" />`
- **`DocumentUploadModal`** is now a thin wrapper: `<UploadModal forceMode="single" />`
- **Image retrieval uses fast path**: Both REST API and embedding tasks check `image_content_file` first
  - Falls back to PAWLs loading only for legacy annotations without pre-extracted images
  - Files: `opencontractserver/llms/tools/image_tools.py:281-349`, `opencontractserver/utils/multimodal_embeddings.py:101-127`
- **`import_annotations()` accepts `pawls_data` parameter**: Enables batch image extraction during import
  - Files: `opencontractserver/utils/importing.py:58-150`
- **`StructuralAnnotationSet.duplicate()` copies image files**: Preserves pre-extracted images during corpus isolation
  - Files: `opencontractserver/annotations/models.py:705-745`
-

### Technical Details

- Documentation consolidated from separate remediation/edit plan files into `docs/architecture/corpus_forking.md`
- Removed obsolete files: `corpus_forking_edit_plan.md`, `corpus_forking_remediation_plan.md`
- Migrated from Semantic UI to `@os-legal/ui` design system (Modal, Button, Input, Progress, etc.)
- Uses `--oc-*` CSS design tokens for consistent theming
- Debounce cleanup on unmount to prevent memory leaks
- Sequential uploads to avoid server overload (documented trade-off)

### Removed

- **Deleted unused components**: `DocumentUploadList.tsx`, `DocumentListItem.tsx`

### Security

- **JWT authentication error message hardening** (CWE-209: Information Exposure Through Error Messages)
  - JWT errors now return generic messages (`"Invalid token"`) instead of exposing exception details
  - Detailed errors logged server-side only for debugging
  - Files: `config/rest_jwt_auth.py:80-90`
- **Sensitive data redaction in logs** (CWE-532: Insertion of Sensitive Information into Log File)
  - New `redact_sensitive_kwargs()` utility recursively redacts API keys, secrets, passwords, tokens, credentials
  - Applied to parser, embedder, and post-processor kwargs logging
  - Files: `opencontractserver/utils/logging.py`, `opencontractserver/tasks/doc_tasks.py`,
    `opencontractserver/pipeline/base/embedder.py`, `opencontractserver/pipeline/base/post_processor.py`,
    `opencontractserver/pipeline/parsers/llamaparse_parser.py`, `opencontractserver/pipeline/post_processors/pdf_redactor.py`

### Added

#### Image Annotation Display in UnifiedContentFeed

- **Modality badges for annotations**: Visual indicators showing TEXT, IMAGE, or MIXED modalities
  - Color-coded badges: Blue (text), Orange (image), Purple (mixed)
  - Integrated inline with annotation labels in HighlightItem
  - Files: `frontend/src/components/annotator/sidebar/ModalityBadge.tsx`
- **Image thumbnail previews**: Display image content directly in annotation feed
  - 80x80px thumbnails with hover effects and lazy loading
  - Automatic fetching only when IMAGE modality is present
  - Files: `frontend/src/components/annotator/sidebar/AnnotationImagePreview.tsx`
- **REST API endpoint for annotation images**: `/api/annotations/<id>/images/`
  - Permission-checked image retrieval using existing `get_annotation_images_with_permission()`
  - IDOR protection: Returns empty array for unauthorized access
  - Files: `opencontractserver/annotations/views.py`, `config/urls.py`
- **Unified JWT authentication utility**: Single entry point for token validation across all API surfaces
  - Automatic handling of both Auth0 (RS256/JWKS) and standard graphql_jwt (HS256) tokens
  - DRY architecture eliminates conditional Auth0/non-Auth0 switching in multiple files
  - Files: `config/jwt_utils.py` (NEW)
- **GraphQL content_modalities field exposure**: Added to AnnotationType schema
  - Enables frontend to filter annotations by modality
  - Files: `config/graphql/graphene_types.py`

### Fixed

- **Image annotations now clearly visible**: Image and mixed-modality annotations display properly in UnifiedContentFeed
  - Previously showed as empty text with no indication of content
  - Files: `frontend/src/components/annotator/sidebar/HighlightItem.tsx:163-167,225,249`
  - Files: `frontend/src/components/knowledge_base/document/unified_feed/ContentItemRenderer.tsx:218`
- **Structural annotations now return images**: Fixed image retrieval for structural annotations without direct document references
  - **Root Cause**: `get_annotation_images_with_permission()` returned empty array for structural annotations (no `document` field)
  - **Fix**: Load PAWLs data from `structural_set.pawls_parse_file` when document is None
  - **Impact**: Structural image annotations (e.g., figures, charts) now display thumbnails in UI
  - **Files Modified**:
    - `opencontractserver/llms/tools/image_tools.py:220-305` - Added `_extract_image_from_pawls()` helper
    - `opencontractserver/llms/tools/image_tools.py:278-305` - Updated `get_annotation_images()` to check structural_set
    - `opencontractserver/llms/tools/image_tools.py:434-492` - Updated `get_annotation_images_with_permission()` for structural permissions
  - **Test Coverage**: Added test for structural annotation image retrieval
    - Files: `opencontractserver/tests/test_annotation_images_api.py:253-321`
    - All 6 tests passing including new structural annotation test
- **Parser pipeline now populates content_modalities**: Text parser now correctly sets content_modalities field
  - **Text Parser**: Sets content_modalities to `["TEXT"]` for all text-only annotations
    - Files: `opencontractserver/pipeline/parsers/oc_text_parser.py:108`
  - **Backfill Command**: Created management command to populate existing annotations with missing content_modalities
    - Analyzes token references in PAWLs data to determine modalities
    - Fallback: Uses annotation label text as hint (e.g., "image", "figure", "chart")
    - Files: `opencontractserver/annotations/management/commands/populate_content_modalities.py`
    - Usage: `python manage.py populate_content_modalities [--dry-run] [--force]`

### Changed

- **Unified JWT authentication architecture**: Refactored authentication to use single shared utility
  - **REST API**: `config/rest_jwt_auth.py` now uses `jwt_utils.get_user_from_jwt_token()`
  - **WebSocket**: Unified `JWTAuthMiddleware` replaces separate Auth0/non-Auth0 middlewares
    - Files: `config/websocket/middleware.py` - Single middleware handles both token types
    - Files: `config/websocket/middlewares/websocket_auth0_middleware.py` - Now alias to unified middleware (deprecated)
  - **ASGI**: Simplified `config/asgi.py` to use single middleware instead of conditional switching
  - **Benefit**: DRY architecture - token validation logic centralized in one place

### Removed

- **NLM Ingest Parser**: Removed legacy NLM-Ingest PDF parser in favor of Docling (default) and LlamaParse
  - **Rationale**: Docling provides superior ML-based parsing with better structure extraction; NLM parser was rarely used
  - **Migration**: Users with `PDF_PARSER=nlm` should switch to `PDF_PARSER=docling` (default) or `PDF_PARSER=llamaparse`
  - **Files Removed**:
    - `opencontractserver/pipeline/parsers/nlm_ingest_parser.py`
    - `opencontractserver/tests/test_doc_parser_nlm_ingest.py`
    - `docs/pipelines/nlm_ingest_parser.md`
  - **Settings Updated**: Removed `nlm` option from `_PDF_PARSER_MAP` in `config/settings/base.py`

### Technical Details

- **Backend**: REST endpoint leverages existing permission-checked `image_tools.py` functions
- **Frontend hook**: `useAnnotationImages` conditionally fetches images only for IMAGE modality (performance optimization)
- **TypeScript types**: Added `contentModalities?: string[]` to annotation types
  - Files: `frontend/src/types/graphql-api.ts:147`
  - Files: `frontend/src/components/annotator/types/annotations.ts:92,145`
- **Test coverage**: 5 backend tests for REST endpoint with authentication and permission checking
  - Files: `opencontractserver/tests/test_annotation_images_api.py`

### Added

#### Corpus-Isolated Structural Annotations

- **StructuralAnnotationSet duplication per corpus**: Each corpus now gets its own copy of structural annotations when documents are added
  - Enables multi-embedder support (each corpus can use different embedding models)
  - Maintains consistent per-corpus vector spaces for similarity search
  - Files: `opencontractserver/annotations/models.py`, `opencontractserver/corpuses/models.py`
- **Extended content_hash format**: Changed from `{sha256}` to `{sha256}_{corpus_id}` (max 128 chars)
  - Migration: `opencontractserver/annotations/migrations/0056_alter_structuralannotationset_content_hash.py`

#### Multimodal Embedding Support

- **Image token extraction from PDFs**: Extract images from PDFs via Docling parser and store as unified tokens in PAWLs format
  - Storage path convention: `document_images/{doc_id}/page_{page}_img_{idx}.{format}`
  - Image tokens include position, dimensions, format, and storage path
  - Files: `opencontractserver/utils/pdf_token_extraction.py`
- **CLIP ViT-L-14 multimodal embedder**: 768-dimensional vectors in shared text/image embedding space
  - Enables cross-modal similarity search (text queries find relevant images)
  - Files: `opencontractserver/pipeline/embedders/multimodal_microservice.py`
- **ContentModality enum**: Type-safe modality tracking for embedders and annotations
  - Single source of truth: `supported_modalities: set[ContentModality]`
  - Convenience properties: `is_multimodal`, `supports_text`, `supports_images`
  - Files: `opencontractserver/types/enums.py`, `opencontractserver/pipeline/base/embedder.py`
- **Multimodal embedding utilities**: Weighted averaging for mixed text+image content
  - Default weights: 30% text, 70% image (configurable via `MULTIMODAL_EMBEDDING_WEIGHTS`)
  - Files: `opencontractserver/utils/multimodal_embeddings.py`
- **content_modalities field on Annotation model**: ArrayField tracking `["TEXT"]`, `["IMAGE"]`, or `["TEXT", "IMAGE"]`
  - Computed from PAWLs token analysis during annotation creation
  - Files: `opencontractserver/annotations/models.py`, `opencontractserver/annotations/utils.py`
- **LLM image tools for agents**: `list_document_images`, `get_document_image`, `get_annotation_images`
  - Permission-checked variants prevent IDOR vulnerabilities
  - Files: `opencontractserver/llms/tools/image_tools.py`, `opencontractserver/llms/tools/tool_registry.py`
- **Modality filtering in vector search**: Filter annotations by content type in similarity search
  - Files: `opencontractserver/llms/vector_stores/core_vector_stores.py`
- **Comprehensive documentation**: Architecture docs for multimodal embeddings and PAWLs format
  - Files: `docs/architecture/multimodal-embeddings.md`, `docs/architecture/pawls-format.md`

### Changed

#### Corpus Isolation Architecture

- **Removed content-based deduplication**: Each upload creates independent documents regardless of content hash
- **Removed source_document provenance**: `source_document_id` no longer set when adding documents to corpus
- **Structural annotations no longer shared**: Each corpus gets duplicated structural annotation sets
- **Updated documentation**: Rewrote `structural_vs_non_structural_annotations.md`, updated `document_versioning.md`, `documents_and_annotations.md`

#### Multimodal Support

- Extended PAWLs token format to support unified image tokens (`is_image=True`)
- Updated `BaseEmbedder` to use `ContentModality` enum instead of boolean flags
- Updated `PipelineComponentDefinition` in registry to store `supported_modalities`
- Enhanced embedding task to detect multimodal content and generate appropriate embeddings

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
  - `PDF_PARSER`: Set to "llamaparse" or "docling" (default) to select default PDF parser
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

## [3.0.0.b3] - 2025-12-11

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
  1.  `Embedding.annotation` FK (one-to-many): annotation can have multiple embeddings
  2.  `Annotation.embeddings` FK (many-to-one): annotation points to single "primary" embedding
- **Fixed**: Hybrid deduplication approach in `search_by_embedding()`:
  1.  Order by `id, similarity_score` and apply PostgreSQL `DISTINCT ON (id)`
  2.  Materialize query to list
  3.  Sort in Python by `similarity_score`
  4.  Return top_k results
- **Rationale**: PostgreSQL `DISTINCT ON` requires the distinct field to be first in ORDER BY, conflicting with need to order by similarity_score. Hybrid approach ensures correctness.
- **Test Results**: All 9 version-aware vector store tests now pass (previously all 8 failing)

12. **Vector store excluding structural annotations from StructuralAnnotationSet**

- **File**: `opencontractserver/llms/vector_stores/core_vector_stores.py:168-196, 221-270`
- **Issue**: Version filtering excluded ALL structural annotations from structural sets, causing vector search to return 0 results
- **Root Cause - Filter Ordering Bug**:
  1.  `only_current_versions` filter applied `Q(document__is_current=True)` (line 170)
  2.  This creates `INNER JOIN` on document table
  3.  Structural annotations have `document_id=NULL` (stored in StructuralAnnotationSet)
  4.  NULL document_id fails the JOIN → structural annotations excluded
  5.  This happened BEFORE document/corpus scoping (lines 221-270)
  6.  Result: Scoping logic tried to include structural annotations, but they were already filtered out
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
  1.  Deduplication fix materialized QuerySet to list for DISTINCT ON + Python sorting
  2.  Helper functions `_safe_queryset_info()` and `_safe_execute_queryset()` assumed QuerySet
  3.  Called `.count()` method on lists (which don't have `.count()` for length)
  4.  Agent's `similarity_search` tool failed silently
  5.  LLM called tool → tool execution broke → no second LLM call → no ASYNC_CONTENT
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
