# OpenContracts Permission System - Complete Guide

> **🔴 CRITICAL CHANGE**: Annotations and Relationships no longer have individual permissions. Both inherit permissions from document + corpus. This eliminates N+1 queries and simplifies the security model.

> **🔴 CRITICAL SECURITY**: Structural annotations and relationships are ALWAYS read-only except for superusers. Even owners with full CRUD permissions cannot modify structural items. This is enforced in `AnnotationManager.user_can` and `RelationshipManager.user_can` (`opencontractserver/shared/Managers.py`) — the structural-write branch runs before any other permission branch. This superuser write to structural items is the **single retained admin data privilege** (a deliberate break-glass for repairing system-generated structural data); see the Admin (Superuser) Access Model banner below.

> **🛡️ ADMIN (SUPERUSER) ACCESS MODEL (scoped admin access, 2026-05)**: A superuser is authorized over **user data** (corpuses, documents, annotations, relationships, notes, conversations, analyses, extracts, datacells, folders, feedback, profiles, badge awards, agents, …) **exactly like a normal user** — there is **no blanket bypass**. With no grants, an admin sees only public + own + explicitly-shared rows and is denied writes on private data it does not own. The blanket `if user.is_superuser: return all()/True` short-circuits were removed from every visibility manager / queryset / `user_can` / permission-enumeration / query-optimizer path. **Three things are retained for superusers:** (1) the **structural-write break-glass** above; (2) **moderation** of conversations/threads (`Conversation.can_moderate` / `Corpus.user_can_moderate` — the two deliberately differ: the corpus surface accepts any `CorpusModerator` row while the conversation surface requires a non-empty `permissions` list; reconciliation tracked under #1450); and (3) **admin-only configuration/restriction gates** enforced in mutations/services — e.g. `PipelineSettings`, `Badge` and `CorpusCategory` management, "create global agents", "make analyses public", worker-upload provisioning, and **triggering reference-enrichment / authority-crawl analyses on any *readable* corpus** (the superuser-gated admin enrichment runner: `AnalysisLifecycleService.start_document_analysis(..., require_corpus_update=True)` exempts superusers from the corpus-`UPDATE` requirement so an admin can run/seed enrichment + the authority-crawl frontier on corpora they can see without owning them — but the exemption is scoped to write-trigger only; superusers are **not** exempt from the READ visibility check, so a private corpus they cannot see stays unreachable). The legitimate **break-glass for inspecting/repairing arbitrary user data is the Django admin site** (`is_staff`), which uses unfiltered ORM and is unaffected by these manager changes. (Follow-up: an explicit, audited support/impersonation mechanism may be added later.)
>
> **Permanent document deletion (escape hatch):** `DocumentLifecycleService.permanently_delete_document` and empty-trash now gate on `corpus.user_can(user, DELETE)` computed like a normal user — there is **no superuser override**. An admin who must purge orphaned/malicious documents they do not own has two paths: (1) grant themselves `DELETE` on the owning corpus (the ordinary permission flow), after which the app-level operation succeeds; or (2) use the Django admin site's unfiltered ORM for direct deletion. Both no-grant-denied and granted-success cases are pinned by `opencontractserver/tests/test_permanent_deletion.py::TestPermanentDeletionPermissions::test_permanent_delete_requires_delete_permission_computed_like_normal_user`.

> **🟠 AUTHORIZATION API**: The canonical single-object authorization check is `Model.objects.user_can(user, obj, permission)` (manager surface) / `obj.user_can(user, permission)` (instance surface). It is the read/check counterpart of the `Model.objects.visible_to_user(user)` queryset filter — the two are pinned to agree by the invariant suite in `opencontractserver/tests/permissioning/test_authorization_invariants.py`. New code MUST call `user_can`.

> **🔵 SOURCE PRIVACY**: Annotations **and Relationships** can be marked as "created by" an analysis or extract using `created_by_analysis` and `created_by_extract` fields. These rows are private to the source object and only visible to users with permission to that analysis/extract. Relationships gained full enforcement in the 2026-06 permissioning audit (closing the Phase-C deferral from issue #1655): `RelationshipManager.user_can` and `RelationshipManager.visible_to_user` now recurse into the source exactly like annotations. The list-side privacy gates honour **user- and group-level** guardian grants via the shared builders in `opencontractserver/utils/source_visibility.py`. **Deleted-source semantics**: both FKs are `on_delete=SET_NULL` — deleting the source Analysis/Extract NULLs the field and the rows become ORDINARY rows governed only by doc+corpus permissions. Deleting a private analysis does NOT keep its annotations private; an operator who wants the rows gone must delete (or re-scope) them before deleting the source. (Full mechanics, including the read-vs-SET_NULL race window's fail-closed guard, live in `_source_privacy_recursion_passes`, `opencontractserver/shared/Managers.py`.)

> **🟢 NEW FEATURE**: COMMENT permission added with special "open commenting" mode. When `corpus.allow_comments = True`, any user who can READ an annotation can COMMENT on it. Enables community feedback without explicit permission grants.

> **⚠️ DEPRECATION WARNING**: The `resolve_oc_model_queryset` function in `opencontractserver.shared.resolvers` was DEPRECATED and replaced with `Model.objects.visible_to_user(user)` calls.

> **🟡 ANONYMOUS USER SUPPORT**: Anonymous users can access public resources with read-only permissions. Document AND corpus must both be `is_public=True` for access. Documents in public corpora **automatically inherit `is_public=True`** at creation time (see [Public Corpus Document Propagation](#public-corpus-document-propagation)). Applies to documents, corpuses, conversations, analyses (public only), and annotations.

> **🟣 USER PROFILE PRIVACY**: User profiles have privacy controls via `is_profile_public`. Private profiles are visible only to users who share corpus membership with > READ permission. See `UserService` in `opencontractserver/users/services/user_service.py`.

> **🟣 BADGE VISIBILITY**: Badge awards follow the recipient's profile privacy rules. Badges are visible if the recipient's profile is visible, or for corpus-specific badges, if the user has access to that corpus. See `BadgeService` in `opencontractserver/badges/services/badge_service.py`.

> **🟢 SERVICE-LAYER ENTRY (Phase 6 — issue #1720)**: Every consumer of permission-filtered data (GraphQL resolvers, MCP tools, REST views, user-context Celery tasks) reaches models through `opencontractserver/<app>/services/`. The shared base `opencontractserver.shared.services.base.BaseService` exposes `get_or_none`, `filter_visible`, `filter_visible_qs` (chains `visible_to_user` onto an existing queryset/related manager in one SQL pass and **fails closed** — raises `TypeError` rather than passing unfiltered rows through), `require_permission`, and `user_has` for cases where a dedicated per-app method is overkill. Direct inline use of the Tier-0 tokens `visible_to_user` / `user_can` / `user_has_permission_for_obj` is forbidden in `config/graphql/` and enforced **twice**: by `opencontractserver/tests/architecture/test_graphql_service_layer.py` AND by a Django system check (`opencontractserver/shared/checks.py`, `opencontracts.E001`) that fails `manage.py` startup on any violation. (The legacy `user_has_permission_for_obj` helper itself has been deleted; the token remains scanned so it cannot be reintroduced.) **Scope nuance:** both enforcers scan `config/graphql/` only, and only for those three tokens — e.g. the mention-autocomplete resolvers in `config/graphql/search_queries.py` still inline guardian `get_objects_for_user` legally. Treat a green E001 as "no inline Tier-0 in `config/graphql/`", not "everything is service-routed". See `docs/architecture/query_permission_patterns.md` for the full per-app service catalogue.

## Key Changes in Current Implementation

| Component | Old Model | New Model | Impact |
|-----------|-----------|-----------|---------|
| **Annotation Permissions** | Individual per-annotation | Inherited from document+corpus | No N+1 queries |
| **Relationship Permissions** | Individual per-relationship | Inherited from document+corpus | Same as annotations |
| **Structural Items** | Could be modified by owners | **READ-ONLY except for superusers** | Critical security |
| **Permission Priority** | Corpus > Document | Document > Corpus (most restrictive) | Better security |
| **Database Queries** | 1 per annotation/relationship | 2 total (doc + corpus) | Massive performance gain |
| **Permission Storage** | `annotationuserobjectpermission` table | Not consulted — computed at runtime (the guardian tables still exist in the schema but play no part in annotation visibility) | Simpler permission model |
| **Permission Uniformity** | Each annotation/relationship different | All same in document | Predictable behavior |
| **Analysis Privacy** | All annotations visible with doc+corpus perms | Annotations created by analysis are private | Enhanced privacy control |
| **Extract Privacy** | All annotations visible with doc+corpus perms | Annotations created by extract are private | Enhanced privacy control |
| **Anonymous Access** | Not supported | Read-only access to public resources | Public corpus support |
| **User Profile Privacy** | All users visible | Privacy via `is_profile_public` + corpus membership | Profile privacy control |
| **Badge Visibility** | All badges visible | Follows recipient's profile privacy | Badge privacy control |
| **Document Actions** | Inline permission checks | `DocumentActionsService` | Centralized least-privilege |
| **Relationship Privacy** | `created_by_*` fields present but unenforced | Full privacy recursion in `RelationshipManager` (2026-06, closes #1655 Phase-C) | Relationships match annotations |
| **Single-object check** | inline permission helper | `Manager.user_can()` / `obj.user_can()` | Check surface paired with `visible_to_user()` filter |

## Table of Contents
1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Permission Types](#permission-types)
4. [COMMENT Permission System](#comment-permission-system)
5. [Backend Implementation](#backend-implementation)
6. [Frontend Implementation](#frontend-implementation)
7. [Annotation Permission Inheritance](#annotation-permission-inheritance)
8. [User Profile and Badge Visibility](#user-profile-and-badge-visibility)
9. [Document Actions Permissions](#document-actions-permissions)
10. [Performance Optimizations](#performance-optimizations)
11. [Component Integration](#component-integration)
12. [Testing](#testing)
13. [Troubleshooting](#troubleshooting)
14. [Agent/LLM Permission Model](#agentllm-permission-model)
15. [The user_can Authorization API](#the-user_can-authorization-api)
16. [resolve_oc_model_queryset Deprecation](#resolve_oc_model_queryset-deprecation)

## Overview

OpenContracts implements a sophisticated hierarchical permission system with different rules for different object types:

### Permission Models

1. **Standard Objects (Corpus, Document, etc.)**
   - Direct permission model - permissions are checked on the object itself
   - Corpus-level permissions can provide additional context when viewing documents
   - **Anonymous users**: Read-only access if `is_public=True`

2. **CorpusFolder - INHERITS CORPUS PERMISSIONS**
   - **NO individual permissions** - CorpusFolder objects do NOT have their own permission records
   - Inherits ALL permissions from parent Corpus
   - **Write operations** (create, update, move, delete folders) require:
     - User is Corpus creator, OR
     - User has `PermissionTypes.UPDATE` permission on parent Corpus (with `include_group_permissions=True`)
   - **CRITICAL SECURITY**: `corpus.is_public=True` grants READ-ONLY access, NOT write access
   - Never check `corpus.is_public` for write permission authorization
   - Implementation: permission gates live in `FolderCRUDService` (`opencontractserver/corpuses/services/folders.py` — every write method checks `corpus.user_can(user, PermissionTypes.UPDATE)`, which honours creator status and group grants); `config/graphql/corpus_folder_mutations.py` is a thin GraphQL wrapper that delegates to the service

3. **Annotations and Relationships - NO INDIVIDUAL PERMISSIONS**
   - **IMPORTANT: Annotations and Relationships do NOT have individual permissions**
   - Both annotations and relationships inherit permissions from their parent document and corpus
   - **Document permissions are PRIMARY** (most restrictive)
   - **Corpus permissions are SECONDARY** (additional restrictions)
   - Formula: `Effective Permission = MIN(document_permission, corpus_permission)`
   - This ensures annotations/relationships are never more permissive than their parent document
   - **Performance benefit**: Eliminates N+1 permission queries
   - **CRITICAL**: Structural annotations and relationships are ALWAYS read-only except for superusers
   - Relationships use the same permission inheritance model as annotations (implemented in `RelationshipManager.user_can` / `RelationshipQuerySet.visible_to_user`, `opencontractserver/shared/Managers.py`)
   - **Privacy fields**: Both Annotation and Relationship models have `created_by_analysis`, `created_by_extract`, `structural`, and `is_public` fields (see `opencontractserver/annotations/models.py`)

4. **Analyses and Extracts - HYBRID MODEL**
   - Have their own individual permissions (can be shared independently)
   - **Visibility requires THREE conditions**:
     1. Permission on the analysis/extract object itself
     2. READ permission on the corpus containing the analysis/extract
     3. READ permission on relevant documents for seeing content
   - **Access Formula**:
     - `Can See Analysis/Extract = HAS_OBJECT_PERMISSION AND CAN_READ_CORPUS`
     - `Can See Annotations Within = CAN_SEE_ANALYSIS AND CAN_READ_DOCUMENT`
   - **Key behaviors**:
     - Users WITHOUT analysis/extract permission see nothing (even if they have corpus+doc access)
     - Users WITH analysis/extract permission but missing corpus permission see nothing
     - Users WITH analysis/extract+corpus permission see the analysis/extract
     - Annotations/datacells within are filtered to only show those on documents user can read
   - This allows controlled sharing of analyses while maintaining document security boundaries

5. **CorpusCategory - GLOBALLY VISIBLE, ADMIN-PROVISIONED**
   - **NO individual permissions** - Categories are visible to ALL users (including anonymous)
   - Categories are admin-provisioned structural data: superusers manage them via the superuser-gated GraphQL mutations (`CreateCorpusCategory` / `UpdateCorpusCategory` / `DeleteCorpusCategory` in `config/graphql/corpus_category_mutations.py`) or the Django Admin
   - Users cannot create, modify, or delete categories - only superusers can
   - **GraphQL Type**: Does NOT use `AnnotatePermissionsForReadMixin` (categories have no permissions)
   - **corpusCount field**: Dynamically computed based on user's visible corpuses
     - Anonymous users see count of public corpuses in each category
     - Authenticated users see count of corpuses they have access to
   - Categories are seeded via migration with a `system` user (inactive, unusable password)
   - Implementation: `CorpusCategoryType` in `config/graphql/corpus_types.py`
   - Query resolver: `resolve_corpus_categories` in `config/graphql/corpus_queries.py` (uses `BaseService.filter_visible(Corpus, user)` for the per-user `corpusCount` annotation)

### Key Principles

1. **Document Security First**: For annotations, document permissions are the primary security boundary
2. **Most Restrictive Wins**: When multiple permission sources exist, the most restrictive applies
3. **Progressive Enhancement**: Features are enabled based on available permissions
4. **Fail Secure**: Default to most restrictive permissions when uncertain
5. **Server-Side Enforcement**: Client-side checks are for UX only; all security is enforced server-side
6. **Performance Optimized**: Query optimizer eliminates N+1 permission queries

## Architecture

```
Standard Permission Flow:
Route → Slug Resolution → Permission Loading → Component Evaluation → UI Rendering

Annotation Permission Flow (Optimized):
Document Request → Query Optimizer → Permission Computation (Once) → Apply to All Annotations → UI Rendering

Analysis/Extract Permission Flow:
Request → Check Object Permission → Check Corpus Permission → Filter Document Content → UI Rendering

Permission Sources:
1. Document Permissions (myPermissions on Document type)
2. Corpus Permissions (myPermissions on Corpus type)
3. Analysis/Extract Permissions (individual object permissions)

Evaluation Priority for Annotations:
1. Document permissions (MUST have at least READ)
2. Corpus permissions (further restricts if present)
3. Structural annotation override (always READ-ONLY if doc is readable)
4. Analysis visibility filter (additional restriction)

Evaluation Priority for Analyses/Extracts:
1. Analysis/Extract object permission (MUST have at least READ)
2. Corpus permission (MUST have at least READ)
3. Document permissions (filters visible content within)
```

## Example Scenario: Multi-User Permission Hierarchy

### Setup:
- **Corpus X**: Contains Doc Alpha, Doc Beta
- **Corpus Y**: Contains Doc Beta
- **User A**: Permissions on Doc Alpha, Doc Beta, Corpus X
- **User B**: Permissions on Doc Beta, Corpus X, Corpus Y
- **User C**: Permissions on Doc Alpha, Corpus Y

### Results:

| User | Corpus View | Documents Visible | Analyses/Extracts |
|------|------------|-------------------|-------------------|
| **User A** | Sees Corpus X | Alpha & Beta in X | Sees analyses/extracts on X if given permission |
| **User B** | Sees X & Y | Beta in X, Beta in Y | Sees analyses/extracts on X or Y if given permission |
| **User C** | Sees Corpus Y | Empty (Alpha not in Y) | Cannot see any analyses in Y (no docs visible) |

### Analysis Permission Example:

If an Analysis is created on Corpus X analyzing both Alpha and Beta:
- **User A with analysis permission**: Sees analysis, sees annotations on both Alpha & Beta
- **User B with analysis permission**: Sees analysis, sees annotations on Beta only
- **User C with analysis permission**: Cannot see analysis (no corpus X permission)
- **User A WITHOUT analysis permission**: Cannot see analysis (even with corpus+doc permissions)

### Annotation Privacy Example (NEW):

If the Analysis creates annotations with `created_by_analysis` field set:
- **User A with doc+corpus but NO analysis permission**: Cannot see these private annotations
- **User A with analysis permission**: Sees all analysis-created annotations on Alpha & Beta
- **User B with analysis permission**: Sees analysis-created annotations on Beta only (no Alpha access)
- **Structural annotations**: Always visible regardless of `created_by_analysis` field

## Key Behaviors Summary

### GraphQL Query Modes (CRITICAL)
The `allAnnotations` field operates in **two distinct modes**:

1. **Manual/User Mode** (NO `analysis_id` provided):
   - Returns ONLY annotations where `analysis` field is NULL
   - Even if you have permission to analyses, their annotations are excluded
   - Extract-based annotations are included (if `analysis` field is NULL and user has extract permission)

2. **Analysis-Specific Mode** (`analysis_id` provided):
   - Returns ONLY annotations from the specified analysis
   - User must have READ permission on the analysis object
   - Filters by the `analysis` foreign key field

**Why**: Prevents mixing manual work with analysis-generated results. Users explicitly choose which "view" they want.

### Standard Annotations (no `created_by_*` fields)
1. Visibility determined by document + corpus permissions
2. All annotations in a document share the same permissions
3. Most restrictive permission wins (document vs corpus)
4. **Query mode matters**: Manual mode excludes analysis-linked annotations even with permission

### Private Annotations (`created_by_analysis` or `created_by_extract` set)
1. **Invisible by default**: Not shown even with document+corpus permissions
2. **Require source permission**: Must have permission to the analysis/extract that created them
3. **Still respect document boundaries**: Even with analysis permission, only see annotations on documents you can access
4. **Structural exception**: Structural annotations are ALWAYS visible if document is readable
5. **Independent from query mode**: Privacy filtering applies in BOTH manual and analysis-specific query modes

### Permission Hierarchy
```
Query Mode Filtering (FIRST STEP - happens BEFORE permission checks):
IF analysis_id is NOT provided:
    Filter to: analysis__isnull=True (manual annotations only)
ELSE:
    Filter to: analysis_id=<specified> (specific analysis only)

Then apply permission checks:

For Standard Annotations:
Document Permission (PRIMARY) ∩ Corpus Permission (SECONDARY) = Effective Permission

For Private Annotations AND Relationships (created_by_analysis or created_by_extract):
Source Permission (REQUIRED) ∩ Document Permission ∩ Corpus Permission = Effective Permission
(The row's own creator is exempt from the source check — matching the
queryset gates' Q(creator=user) disjunct and the relationship creator
short-circuit.)

For Structural Annotations:
Document READ Permission = Always Visible (READ-ONLY)
(Privacy filtering skipped for structural items)

For COMMENT Permission (Special Case):
IF corpus.allow_comments == True:
    can_comment = can_read  # Readable = Commentable
ELSE:
    can_comment = doc_comment AND corpus_comment  # Standard MIN logic
```

## Permission Types

### Backend Enum (opencontractserver/types/enums.py)

```python
class PermissionTypes(str, enum.Enum):
    CREATE = "CREATE"
    READ = "READ"
    EDIT = "EDIT"         # Alias for UPDATE
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    COMMENT = "COMMENT"   # NEW: Comment on annotations/relationships
    PERMISSION = "PERMISSION"
    PUBLISH = "PUBLISH"
    CRUD = "CRUD"         # Shorthand for CREATE+READ+UPDATE+DELETE
    ALL = "ALL"           # All permissions including COMMENT+PUBLISH+PERMISSION
```

### Frontend Enum (frontend/src/components/types.ts)

```typescript
export enum PermissionTypes {
  CAN_PERMISSION = "CAN_PERMISSION",
  CAN_PUBLISH = "CAN_PUBLISH",
  CAN_COMMENT = "CAN_COMMENT",
  CAN_CREATE = "CAN_CREATE",
  CAN_READ = "CAN_READ",
  CAN_UPDATE = "CAN_UPDATE",
  CAN_REMOVE = "CAN_REMOVE",
}
```

### Permission Translation

The GraphQL layer translates between backend Django Guardian format and frontend enum format:

```python
# Backend Django Guardian format (what's stored in database):
["create_document", "read_document", "update_document", "remove_document"]

# GraphQL myPermissions field returns (backend format):
["create_annotation", "read_annotation", "update_annotation", "remove_annotation"]

# Frontend transforms to (for UI logic):
["CAN_CREATE", "CAN_READ", "CAN_UPDATE", "CAN_REMOVE"]
```

**Note**: The GraphQL `myPermissions` field returns backend format (e.g., `read_annotation`) not frontend format (`CAN_READ`). Frontend components handle the transformation.

### Permission Capabilities

| Permission | Corpus Context | Document Context | Capabilities |
|------------|----------------|------------------|--------------|
| **CAN_READ** | View corpus, documents | View document | Basic viewing access |
| **CAN_CREATE** | Add documents, annotations | Create annotations | Content creation |
| **CAN_UPDATE** | Edit corpus, annotations | Edit document/annotations | Content modification |
| **CAN_REMOVE** | Delete corpus content | Delete document | Content deletion |
| **CAN_PUBLISH** | Make corpus public | Make document public | Public visibility |
| **CAN_PERMISSION** | Manage corpus access | Manage document access | Permission management |
| **CAN_COMMENT** | Add comments | Add comments | Comment functionality |

### Voting Permissions

Voting on messages, conversations/threads, and corpuses uses a **visibility-based permission model**:

**Rule: If you can see it, you can vote on it.**

This simple convention means:
- Users can upvote/downvote any message, thread, or corpus they have READ access to
- Users CANNOT vote on their own messages, threads, or corpuses (enforced server-side)
- No explicit "VOTE" permission type exists - voting is implicitly allowed with READ access
- Vote counts are denormalized on ChatMessage / Conversation / Corpus models for performance

**Implementation Details:**
- `MessageVote` model: Tracks votes on ChatMessage objects
- `ConversationVote` model: Tracks votes on Conversation/Thread objects
- `CorpusVote` model: Tracks votes on Corpus objects (see below for anonymous-voter handling)
- One vote per user per object (enforced via database UNIQUE constraint)
- Users can change their vote type (upvote ↔ downvote)
- Vote mutations check visibility via the matching `Model.objects.visible_to_user(user)` filter (routed through `BaseService.get_or_none` in the service layer)

**Mutations:**
- `voteMessage(messageId, voteType)` - Vote on a message (`@login_required`)
- `removeVote(messageId)` - Remove vote from a message (`@login_required`)
- `voteConversation(conversationId, voteType)` - Vote on a thread (`@login_required`)
- `removeConversationVote(conversationId)` - Remove vote from a thread (`@login_required`)
- `voteCorpus(corpusId, voteType)` - Vote on a corpus (**no `@login_required`** — see Corpus-specific notes below)
- `removeCorpusVote(corpusId)` - Remove vote from a corpus (**no `@login_required`**)

**GraphQL Fields:**
- `MessageType.userVote` - Current user's vote ("UPVOTE", "DOWNVOTE", or null)
- `ConversationType.userVote` - Current user's vote on the thread
- `CorpusType.myVote` - Current viewer's vote on the corpus (named `myVote` rather than `userVote` because it generalises to anonymous viewers — see below)
- `upvoteCount` / `downvoteCount` - Denormalized vote counts on all three types
- `CorpusType.score` - `upvoteCount - downvoteCount`, indexed for `orderBy: "top"` sorts on the corpus list view

#### Corpus Voting — Anonymous Voter Support

Unlike message and conversation voting, **corpus voting accepts anonymous callers**. The discovery surface (`/corpuses`) is reachable without login, and public corpora are visible to anonymous users; allowing them to upvote/downvote turns score into a meaningful community signal rather than a leaderboard for authenticated users only.

**Two voter shapes share one table (`CorpusVote`):**

| Voter shape | `creator` | `session_key` | UNIQUE constraint |
|-------------|-----------|---------------|-------------------|
| Authenticated | NOT NULL (user FK) | NULL | `one_vote_per_user_per_corpus` (partial, `creator IS NOT NULL`) |
| Anonymous | NULL | NOT NULL (Django session id) | `one_anon_vote_per_session_per_corpus` (partial, `creator IS NULL AND session_key IS NOT NULL`) |

The **two partial UNIQUE indexes** (rather than a single composite UNIQUE) are required because Postgres treats every NULL as distinct — an unconditional `UNIQUE(corpus, creator)` would let unbounded anonymous rows accumulate, and an unconditional `UNIQUE(corpus, session_key)` would block every authenticated row.

A salted SHA-256 `ip_hash` is recorded for audit/abuse review but is intentionally **NOT** part of the unique constraint — shared NATs would otherwise prevent legitimate co-located voters from voting.

**Permission gating (both branches):**
- READ visibility on the corpus is the only check (`BaseService.get_or_none(Corpus, pk, user)`).
- For anonymous viewers, `Corpus.objects.visible_to_user(AnonymousUser())` already filters down to public corpuses only, so the READ gate naturally blocks anonymous voting on private corpora.
- Self-vote (creator voting on their own corpus) is blocked on the authenticated branch; anonymous voters by definition are not the creator.

**Session bootstrap:**
The `voteCorpus` mutation calls `session.save()` on first cast to materialise a `session_key` so subsequent votes from the same browser dedupe correctly. The `removeCorpusVote` mutation reads `session_key` passively — it never creates a session for callers who haven't voted.

**Sort surface:**
`CorpusFilter.order_by` (GraphQL arg `orderBy`) is tuple-mapped to expose `top` / `-top` for score sorting, `created` / `-modified` / `title` for traditional sorts. When `orderBy` is `top` or `-top`, `is_personal=True` corpora are excluded — personal "My Documents" corpora are private singletons that should not rank against shared content.

**Implementation:**
- Model + signal-driven count maintenance: `opencontractserver/corpuses/models.py` (`CorpusVote`, `CorpusVoteType`) + `opencontractserver/corpuses/signals.py` (`update_corpus_vote_counts_on_save` / `_on_delete`)
- Service: `opencontractserver/corpuses/services/votes.py` (`CorpusVoteService`)
- GraphQL: `config/graphql/voting_mutations.py` (`VoteCorpusMutation`, `RemoveCorpusVoteMutation`)
- Tests: `opencontractserver/tests/test_corpus_voting.py`

## Permission Model Summary by Object Type

This section provides a comprehensive reference for how permissions work across different object types in the system.

For every object type below, permissions are reachable through two paired surfaces, both defined per model in `opencontractserver/shared/Managers.py`:

- **`Model.objects.visible_to_user(user)`** — the queryset *filter*: which rows the user may READ.
- **`Model.objects.user_can(user, obj, permission)`** / **`obj.user_can(user, permission)`** — the single-object *check*: may the user perform `permission` on `obj`.

The two are pinned to agree for READ by the invariant suite (`test_authorization_invariants.py`). Use the filter for list queries and the check for mutation/field-resolver gating.

### Permission Model Reference Table

| Object Type | Permission Model | Primary Permission Source | Secondary Checks | Special Rules |
|-------------|------------------|---------------------------|------------------|---------------|
| **Corpus** | Direct | Object permissions | `is_public` flag | Creator has full access |
| **Document** | Direct | Object permissions | `is_public` flag | Creator has full access |
| **DocumentRelationship** | Inherited (Doc+Corpus) | Source + Target doc permissions | Corpus permissions | `Effective = MIN(source_doc, target_doc, corpus)` |
| **CorpusFolder** | Inherited (Corpus) | Parent corpus permissions | None | No individual permissions; write requires UPDATE on corpus |
| **Annotation** | Inherited (Doc+Corpus) | Document permissions | Corpus permissions | `Effective = MIN(doc, corpus)`; Structural always READ-ONLY |
| **Relationship** | Inherited (Doc+Corpus) | Document permissions | Corpus permissions | `Effective = MIN(doc, corpus)`; Structural always READ-ONLY; `created_by_*` privacy recursion (2026-06) |
| **Metadata (Datacell)** | Corpus-primary | Corpus permissions | Document READ required | Corpus UPDATE + Doc READ = can edit; corpus-level feature |
| **Analysis** | Hybrid | Object permissions | Corpus READ required | Content filtered by doc permissions |
| **Extract** | Hybrid | Object permissions | Corpus READ required | Content filtered by doc permissions |
| **Conversation (CHAT)** | Restrictive | Creator + explicit permissions + public | `is_public` flag | Personal agent chats; NO context inheritance |
| **Conversation (THREAD)** | Context-based | Base rules + context inheritance | `is_public` flag | Collaborative discussions; inherits from corpus/document |
| **ChatMessage** | Inherited (Conversation) + Moderator | Parent conversation visibility | Moderator access | See [ChatMessage Visibility](#chatmessage-visibility-moderator-access) |
| **UserBadge** | Privacy-filtered | Recipient's profile privacy | Corpus membership | Follows recipient's `is_profile_public` |
| **User** | Privacy-controlled | `is_profile_public` | Corpus membership | Private users visible via shared corpus with > READ |
| **Note** | Inherited (Doc+Corpus) | Document + corpus visibility | Creator / explicit grants | `NoteManager.user_can` / `NoteQuerySet.visible_to_user` (MIN of doc+corpus) |
| **UserFeedback** | Inherited (Annotation) for READ | Commented annotation visibility | Creator / `is_public` / guardian on the row | READ inherits from the annotation; writes are creator/explicit-grant only (`UserFeedbackManager`) |
| **Embedding** | Inherited (parent object) | Parent document/annotation/note visibility | — | `EmbeddingManager` (`opencontractserver/shared/Managers.py`) |
| **CorpusAction** | Direct (generic) | Creator / `is_public` / guardian | — | Generic `visible_to_user`; listed per-corpus by `DocumentActionsService` |
| **CorpusGroup** | Direct (`BaseOCModel`) | Creator / `is_public` / guardian | Member corpora + bound agent re-gated per viewer | Membership resolved at **call time**, never snapshotted; `Effective member set = MIN(group READ, corpus READ)` |
| **Notification** | Recipient-only | `recipient == user` | — | Simple ownership — no guardian tables, does NOT use `AnnotatePermissionsForReadMixin` |

### Detailed Permission Formulas

#### Standard Objects (Corpus, Document)
```
Can Access = is_creator OR has_object_permission OR (is_public AND READ)
# Superusers are NOT a disjunct here — they are computed exactly like a normal
# user for data (scoped admin access, 2026-05). See the Admin Access Model banner.
```

#### Public Corpus Document Propagation

Documents in public corpora automatically inherit `is_public=True`, ensuring the two-flag rule is naturally satisfied without queryset-level overrides.

**Propagation triggers:**
1. **`Corpus.add_document()` / `import_document()`**: New documents created in a public corpus get `is_public=True` at creation time.
2. **`Corpus.save()` (is_public change)**: When a corpus becomes public, all its documents are updated to `is_public=True`. When a corpus becomes private, documents are set to `is_public=False` **only if** they are not in any other public corpus.

**Invariant**: `document.is_public = True` if the document is in at least one public corpus (or was explicitly marked public).

**Implementation**:
- `Corpus._propagate_public_status_to_documents()` in `opencontractserver/corpuses/models.py`
- `import_document()` in `opencontractserver/documents/versioning.py` sets `is_public=corpus.is_public`
- `Corpus.add_document()` sets `is_public=self.is_public or source_doc.is_public`

#### DocumentRelationship (Inherited Permissions)

DocumentRelationship objects inherit permissions from their source_document, target_document, and corpus (same model as annotation Relationships). User must have permission on BOTH documents AND corpus (if set).

```
Permission Formula:
  Effective Permission = MIN(source_doc_permission, target_doc_permission, corpus_permission)

READ Check:
  # Superusers are computed like a normal user (no is_superuser disjunct).
  can_read = (can_read_source_document AND can_read_target_document
              AND (no_corpus OR can_read_corpus))

CREATE Check:
  can_create = has_CREATE_permission_on_source_document
               AND has_CREATE_permission_on_target_document
               AND (no corpus OR has_CREATE_permission_on_corpus)

UPDATE Check:
  can_update = has_UPDATE_permission_on_source_document
               AND has_UPDATE_permission_on_target_document
               AND (no corpus OR has_UPDATE_permission_on_corpus)

DELETE Check:
  can_delete = has_DELETE_permission_on_source_document
               AND has_DELETE_permission_on_target_document
               AND (no corpus OR has_DELETE_permission_on_corpus)
```

**Key characteristics:**
- DocumentRelationship connects two Document objects (not annotations)
- NO individual guardian permissions - inherits from source_doc + target_doc + corpus
- Types: `RELATIONSHIP` (labeled semantic link) or `NOTES` (free-form notes between docs)
- Permission model matches annotation Relationship for consistency
- **Anonymous users**: Read-only access if source doc, target doc, AND corpus are all `is_public=True`
- **No `@login_required`**: Query resolvers do NOT require authentication; permission filtering via `visible_to_user()` handles anonymous access to public resources

**Service**: Use `DocumentRelationshipService` (`opencontractserver/documents/services/relationships.py`) for:
- IDOR-safe fetches with `get_relationship_by_id(user, id)`
- Filtered queries with `get_visible_relationships(user, ...)`
- Document-specific queries with `get_relationships_for_document(user, doc_id, ...)`
- Permission checks with `user_has_permission(user, doc_relationship, permission_type)` — MIN(source_doc, target_doc, corpus) via three `user_can` calls

#### Annotations & Relationships (including DocumentRelationship)
```
Effective Permission = MIN(document_permission, corpus_permission)
Structural Override = IF structural THEN READ-ONLY (except superuser)
Privacy Filter = IF created_by_analysis/extract THEN require source permission
```

**Note**: The Relationship model (for annotation-to-annotation relationships) has the same privacy fields as Annotation — `created_by_analysis`, `created_by_extract`, `structural`, and `is_public` — and, since the 2026-06 permissioning audit, the same **enforcement**: `RelationshipManager.user_can` recurses into the source object and `RelationshipManager.visible_to_user` carries the matching privacy gate (see `opencontractserver/shared/Managers.py`; parity pinned by `RelationshipAuthorizationInvariantsTestCase`). The row's own **creator** passes the source privacy gate even without source access, mirrored by `Q(creator=user)` in the queryset gate. For annotations, document/corpus permission checks still apply after that source-privacy exemption.

##### Annotation Images (`/api/annotations/<id>/images/`)

Annotation **thumbnails / cropped image data** (extracted from PAWLs image tokens or `image_content_file`) follow **the same visibility rule as the annotation itself** — *if you can read the annotation, you can read its images*. The REST view is `AnnotationImagesView` at `opencontractserver/annotations/views.py`; the permission gate in `get_annotation_images_with_permission` (`opencontractserver/llms/tools/image_tools.py`) delegates directly to `AnnotationQuerySet.visible_to_user` so the rules cannot drift.

The endpoint always returns `200 OK` with `{"images": [], "count": 0}` for missing/unauthorized requests (IDOR protection); the response shape is identical whether the annotation does not exist, the user lacks permission, or the annotation simply has no image content.

#### Analyses & Extracts (Hybrid Model)
```
Can See Object = has_object_permission AND can_read_corpus
Can See Content = can_see_object AND can_read_document
```

#### Metadata (Datacell) - Corpus-Primary Model

Metadata values (Datacells) follow a **corpus-primary** permission model, which differs from annotations:

```
READ Check:
  can_read = can_read_document AND can_read_corpus

UPDATE Check:
  can_update = can_read_document AND has_UPDATE_permission_on_corpus

DELETE Check:
  can_delete = can_read_document AND has_DELETE_permission_on_corpus
```

**Why this differs from annotations:**
- Metadata schemas (columns) are defined at the **corpus level**, not document level
- Corpus owners/editors should be able to fill in metadata for any document they can see
- Explicit document UPDATE permissions aren't always assigned for corpus-scoped documents (performance optimization)
- This aligns with CorpusFolder's permission model (inherits from corpus)

**Key characteristics:**
- Requires only Document READ (not UPDATE) - user just needs to see the document
- Corpus permission determines write access - UPDATE to edit, DELETE to remove
- Anonymous users: READ-only access if both document and corpus are public (documents in public corpora inherit `is_public=True` automatically)
- Superusers: computed like a normal user — NO blanket access to metadata (scoped admin access, 2026-05); an admin reads/writes datacells only on documents+corpora it can access normally

**Implementation**: `MetadataService.check_metadata_mutation_permission()` in `opencontractserver/extracts/services/metadata.py`

#### Conversations - Bifurcated Permission Model

Conversations use a **bifurcated permission model** based on `conversation_type`:

##### CHAT Type (Restrictive - Personal Agent Chats)
```
Visibility Check:
  # Superusers are computed like a normal user (no is_superuser disjunct) —
  # scoped admin access, 2026-05.
  can_see = is_creator
            OR has_explicit_guardian_permission (read_conversation)
            OR is_public

Note: CHAT type does NOT inherit visibility from corpus/document context.
      Even if a user can read the corpus, they cannot see another user's CHAT.
```

##### THREAD Type (Context-Based - Collaborative Discussions)
```
Visibility Check:
  can_see = CHAT_rules (creator OR explicit_permission OR is_public)
            OR context_inheritance (see below)

Context Inheritance (AND logic when both set):
  IF only chat_with_corpus set:
    can_see = user can READ corpus
  ELIF only chat_with_document set:
    can_see = user can READ document
  ELIF both chat_with_corpus AND chat_with_document set:
    can_see = user can READ corpus AND user can READ document
```

##### Moderation (Applies to Both Types)
```
Moderation Check:
  # Moderation is a RETAINED admin capability — superusers keep can_moderate
  # (scoped admin access, 2026-05). This is an ops capability, distinct from
  # data *visibility*, which is computed normally for superusers above.
  can_moderate = is_superuser
                 OR is_conversation_creator
                 OR corpus.creator == user
                 OR document.creator == user
                 OR user is CorpusModerator with permissions
```

##### Key Differences Summary

| Aspect | CHAT | THREAD |
|--------|------|--------|
| Purpose | Personal agent conversations | Collaborative discussions |
| Context Inheritance | NO | YES |
| Context Fields | Only ONE (corpus OR document) | BOTH allowed (doc-in-corpus) |
| Corpus Reader Visibility | Cannot see others' CHATs | CAN see corpus THREADs |

**Implementation**: `ConversationQuerySet.visible_to_user()` in `opencontractserver/conversations/models.py`

#### ChatMessage Visibility (Moderator Access)

ChatMessages inherit visibility from their parent conversation via `Conversation.objects.visible_to_user()`. This means messages automatically inherit the bifurcated CHAT/THREAD permission logic. Additionally, moderator access is provided for corpus/document owners.

```
Visibility Check (ChatMessage.visible_to_user):
  # Superusers are computed like a normal user (no is_superuser disjunct) —
  # message visibility is scoped (scoped admin access, 2026-05). NOTE the
  # moderator conditions below are the owner-based ones (creator/owns-corpus/
  # owns-document), NOT the broader can_moderate (which includes superuser),
  # so a superuser does NOT see all messages via this path.
  can_see_message = message is in VISIBLE conversation (inherits bifurcated logic)
                    OR user created the message
                    OR user has explicit permission on the message
                    OR user can moderate the conversation (owner-based, below)

Moderator Conditions (for visibility):
  can_moderate = conversation.creator == user
                 OR user owns corpus (chat_with_corpus.creator == user)
                 OR user owns document (chat_with_document.creator == user)
```

**Key Implementation Details:**
- Located in `ChatMessageQuerySet.visible_to_user()` (`opencontractserver/conversations/models.py`)
- **Primary visibility check**: Uses `Conversation.objects.visible_to_user()` to inherit bifurcated permissions
- Moderators can see ALL messages in conversations they moderate, even without explicit message permissions
- Mutations like UpdateMessage and DeleteMessage use this visibility check and additionally verify the user has edit/delete permissions (or is a moderator)

**Example - Bifurcated Behavior:**
```python
# Setup: Alice owns corpus, Bob has corpus READ permission
corpus = Corpus.objects.create(title="Legal Docs", creator=alice)
assign_perm("read_corpus", bob, corpus)

# Alice creates a CHAT (agent conversation) on the corpus
chat = Conversation.objects.create(
    chat_with_corpus=corpus, creator=alice, conversation_type="chat"
)
chat_msg = ChatMessage.objects.create(conversation=chat, creator=alice)

# Alice creates a THREAD (discussion) on the corpus
thread = Conversation.objects.create(
    chat_with_corpus=corpus, creator=alice, conversation_type="thread"
)
thread_msg = ChatMessage.objects.create(conversation=thread, creator=alice)

# Bob (corpus reader) can see THREAD messages but NOT CHAT messages
visible_to_bob = ChatMessage.objects.visible_to_user(bob)
assert thread_msg in visible_to_bob  # THREAD inherits corpus visibility
assert chat_msg not in visible_to_bob  # CHAT is private to creator

# Alice (corpus owner) can see ALL messages as moderator
visible_to_alice = ChatMessage.objects.visible_to_user(alice)
assert chat_msg in visible_to_alice  # Moderator access
assert thread_msg in visible_to_alice  # Moderator access
```

#### CorpusGroup (multi-corpus retrieval bundles)

A `CorpusGroup` bundles several corpora so an agent can retrieve across all of
them at once (`search_across_corpora`, issue #2056). The group is an ordinary
`BaseOCModel` — creator / `is_public` / guardian — but its **membership is not a
permission grant**:

```
Can see group      = is_creator OR has_object_permission OR (is_public AND READ)
Can edit group     = user_can(user, group, CRUD)          # creator or explicit grant
Member corpora     = Corpus.objects.visible_to_user(user).filter(corpus_groups=group)
                     # i.e. MIN(group READ, corpus READ), recomputed on EVERY call
```

**The load-bearing rule**: membership is resolved at call time and intersected
with per-user corpus visibility by
`opencontractserver/corpuses/services/corpus_groups.py::CorpusGroupService.get_group_corpora_visible_to_user`.
A private corpus inside a shared or public group is therefore **never** searched
for, or disclosed to, a user who lacks corpus-level READ — and a membership
change takes effect on the very next query rather than at some config snapshot.
Adding a corpus to a group can never widen access to it.

The bound `default_agent` is gated the same way (`resolve_visible_fk` on
`CorpusGroupType`), so a private agent's `system_instructions` cannot leak
through a public group.

Writes go through `CorpusGroupService.create_group` / `update_group` /
`delete_group`, which verify `PermissionTypes.CRUD` and return the uniform
`GROUP_NOT_FOUND_MESSAGE` for both "does not exist" and "exists but forbidden"
(IDOR-uniform). `create_group` / `update_group` additionally require every
submitted member corpus to be READ-visible to the caller, so a user cannot
smuggle an unreadable corpus into a group they own.

**Membership edits are asymmetric — visibility filtering never deletes.**
`update_group`'s `corpus_pks` replaces only the *caller-visible* slice of the
membership:

```
New membership = (members the caller CANNOT read)  ∪  (submitted, caller-readable set)
```

The two halves are disjoint by construction, so the net rule is **you may add
or remove only what you can see**. This is required because the edit form is
seeded from the per-viewer-filtered `CorpusGroupType.corpora` — if a member
became invisible to the editor after being added (its owner flipped it
private), a wholesale replace would silently destroy that membership on an
unrelated save, with no field exposing the true membership count to detect it.
Adding is still gated by `_resolve_member_corpora`, so the fix cannot be used
to smuggle an unreadable corpus in; removing a visible member works normally.
See `CorpusGroupService.update_group` and the regression tests
`opencontractserver/tests/test_corpus_groups.py::CorpusGroupServiceTests::test_update_group_preserves_invisible_member_on_unrelated_edit`
/ `::test_update_group_can_still_remove_a_visible_member`.

**User-facing surface**: the per-user management GUI at `/corpus-groups`
(`frontend/src/components/corpus_groups/CorpusGroupManagement.tsx`) lists only
groups the viewer created, via the `mine: true` filter on the `corpusGroups`
connection (`config/graphql/filters.py::CorpusGroupFilter`, built on the shared
`OwnershipScopeFilterMixin`). That filter only ever **narrows** the
already-visibility-scoped queryset returned by
`CorpusGroupService.list_visible_groups` — the node type's `get_queryset` and the
service both run before the filterset in
`config/graphql/core/relay.py::resolve_django_connection`. There is no superuser
gate and no instance-wide listing, consistent with the Admin Access Model banner.

### Anonymous User Access Summary

| Object Type | Can Read? | Conditions |
|-------------|-----------|------------|
| Corpus | ✅ | `is_public=True` |
| Document | ✅ | `is_public=True` |
| Annotation | ✅ | Document AND Corpus both public |
| Relationship | ✅ | Document AND Corpus both public |
| DocumentRelationship | ✅ | Source doc, target doc, AND corpus all public |
| Analysis | ✅ | Analysis public AND Corpus public |
| Extract | ❌ | Never — enforced at the manager (`ExtractManager` denies anonymous on both `visible_to_user` and `user_can`) AND service (`ExtractService`) layers (2026-06 audit) |
| Conversation | ✅ | `is_public=True`; **THREADs additionally** via context inheritance when the attached corpus/document is public (CHATs never) |
| CorpusGroup | ✅ | `is_public=True` — but member corpora are still filtered to public ones, so an anonymous viewer sees the group with only its public members |
| User Profile | ✅ | `is_profile_public=True` |

### Structural Item Protection Summary

| Item Type | Non-Superuser | Superuser |
|-----------|---------------|-----------|
| Structural Annotation | READ-ONLY | Full CRUD |
| Structural Relationship | READ-ONLY | Full CRUD |
| Non-Structural Annotation | Per doc+corpus permissions | Full CRUD |
| Non-Structural Relationship | Per doc+corpus permissions | Full CRUD |

**Enforcement Locations:**
- Annotations: `AnnotationManager.user_can` (`opencontractserver/shared/Managers.py`) — structural-write branch runs before any other permission branch
- Relationships: `RelationshipManager.user_can` (`opencontractserver/shared/Managers.py`) — same ordering
- Pre-computed `myPermissions`: the list services (`AnnotationService` / `RelationshipService`) mask `_can_update`/`_can_delete` per-row on structural rows to `user.is_superuser`, so the UI mirrors the break-glass

### Discussion Thread Permissions

Discussions follow a **visibility-based participation model**: if you can READ a resource, you can participate in discussions about it.

All checks route through the service layer (`BaseService` /
`get_for_user_or_none`) inside `config/graphql/conversation_mutations.py` —
there are no inline permission checks:

| Action | Permission Required | Enforcement |
|--------|---------------------|-------------|
| Create thread on corpus | READ on corpus | `CreateThreadMutation` → `get_for_user_or_none(Corpus, …)` |
| Create thread on document | READ on document | `CreateThreadMutation` → `get_for_user_or_none(Document, …)` |
| Create thread on both | READ on corpus AND document | Both lookups above |
| Post message in thread | READ on conversation | `CreateThreadMessageMutation` → `get_for_user_or_none(Conversation, …)` |
| Reply to message | READ on conversation | `ReplyToMessageMutation` → `BaseService.require_permission` |
| Vote on message/thread | READ on conversation | Visibility-based (`BaseService.get_or_none` in `voting_mutations.py`) |
| Save message to My Documents | READ on conversation | Visibility-based (`SaveMessageToWorkspaceMutation` → `BaseService.filter_visible`). Copies a message you can already read into **your own** personal corpus, so it is strictly weaker than editing; the author never gains access to the saver's private copy. |
| Edit own message | Creator OR moderator | `UpdateMessage` → `BaseService.filter_visible` + `BaseService.user_has` |
| Delete own message | Creator OR moderator | `DeleteMessage` → `get_for_user_or_none(ChatMessage, …)` + `BaseService.user_has` |
| Moderate thread (lock/pin/delete) | See below | `moderation_mutations.py` → `conversation.can_moderate(user)` |

**Moderator Access:**
A user can moderate a thread if any of the following are true (`Conversation.can_moderate`, `opencontractserver/conversations/models.py`):
- User is a superuser (retained admin capability — see the Admin Access Model banner)
- User is the thread creator
- User owns the corpus (`chat_with_corpus.creator == user`)
- User owns the document (`chat_with_document.creator == user`)
- User is a `CorpusModerator` for the corpus **with a non-empty `permissions` list**

EDIT/UPDATE permission on the corpus or document does **NOT** grant thread
moderation — delegated moderation goes through `CorpusModerator` rows.
(`Corpus.user_can_moderate`, the corpus-level moderation surface, is
deliberately looser — it accepts any `CorpusModerator` row regardless of the
`permissions` list; reconciliation tracked under #1450.)

**Rationale**: Discussions are meant to be collaborative. Anyone who can view a resource should be able to ask questions and participate in conversations about it. This encourages engagement and knowledge sharing while still maintaining moderation controls for resource owners.

**Anonymous Users**: Can only view threads on public resources (`is_public=True`). Cannot create threads or post messages (requires authentication).

## COMMENT Permission System

### Overview

The COMMENT permission allows users to add comments/feedback on annotations and relationships. It follows the same inheritance model as other permissions (READ, CREATE, UPDATE, DELETE) but includes a special "open commenting" mode via the `corpus.allow_comments` field.

### Permission Models

**Standard Mode** (`corpus.allow_comments = False`):
```
can_comment = MIN(doc_comment, corpus_comment)
```
- Requires explicit COMMENT permission on both document AND corpus
- Most restrictive permission wins
- Same behavior as READ, CREATE, UPDATE, DELETE

**Open Commenting Mode** (`corpus.allow_comments = True`):
```
can_comment = can_read
```
- Any user who can READ an annotation can COMMENT on it
- Enables community feedback and collaboration without permission overhead
- Still respects all READ boundaries (document, corpus, privacy)

### Key Rules

1. **READ is Required**: Cannot comment on what you cannot see
   - No document READ = no comment
   - No corpus READ = no comment
   - Private annotation (analysis/extract) not accessible = no comment

2. **Corpus Override**: `corpus.allow_comments` only applies when corpus context exists
   - Document-only views use document COMMENT permission
   - No corpus = standard permission check on document

3. **Privacy Respected**: Open commenting mode still respects all visibility boundaries
   - `created_by_analysis` annotations: need analysis permission
   - `created_by_extract` annotations: need extract permission
   - Different users may see different subsets of annotations

### Implementation

**In `AnnotationService._compute_effective_permissions()` (`opencontractserver/annotations/services/annotation_service.py`):**

```python
# Compute final read permission
final_read = doc_read and corpus_read

# BACON MODE: If corpus allows comments, readable = commentable
if corpus.allow_comments:
    final_comment = final_read  # Can see it? Can comment on it.
else:
    # Standard restrictive model
    final_comment = doc_comment and corpus_comment

return (final_read, can_create, can_update, can_delete, final_comment)
```

### Model Permissions

COMMENT permission must be defined in model Meta for:
- `Document` - `comment_document`
- `Corpus` - `comment_corpus`
- `Annotation` - `comment_annotation`
- `Relationship` - `comment_relationship`

### Use Cases

**Open Commenting Mode (`allow_comments=True`):**
- Public annotation projects with community feedback
- Collaborative document review where everyone can comment
- Educational corpuses where students can discuss annotations
- Beta testing environments with open feedback

**Standard Mode (`allow_comments=False`):**
- Confidential/sensitive documents with controlled access
- Professional environments requiring explicit permission grants
- Multi-tier access where some users can only view

### Examples

**Example 1: Open Commenting**
```python
# Setup
corpus.allow_comments = True
set_permissions(user, document, [READ])  # No COMMENT
set_permissions(user, corpus, [READ])    # No COMMENT

# Result
can_comment = True  # READ granted = COMMENT granted
```

**Example 2: Controlled Commenting**
```python
# Setup
corpus.allow_comments = False
set_permissions(user, document, [READ])         # No COMMENT
set_permissions(user, corpus, [READ, COMMENT])  # Has COMMENT

# Result
can_comment = False  # Document lacks COMMENT (most restrictive wins)
```

**Example 3: Respecting Boundaries**
```python
# Setup
corpus.allow_comments = True
set_permissions(user, corpus, [READ])     # Has corpus access
# NO document permissions

# Result
can_comment = False  # Cannot read document = cannot comment
```

## Backend Implementation

### Core Utilities (opencontractserver/utils/permissioning.py)

```python
def set_permissions_for_obj_to_user(
    user_val: int | str | type[User],
    instance: type[django.db.models.Model],
    permissions: list[PermissionTypes],
) -> None:
    """
    REPLACE current permissions with specified permissions.

    IMPORTANT: This function now correctly removes ALL existing
    permissions before adding new ones (fixed in recent update).
    """
    # 1. Remove all existing permissions for the user on this object
    # 2. Add requested permissions
    # This ensures true permission replacement, not accumulation

def get_users_permissions_for_obj(
    user: type[User],
    instance: type[django.db.models.Model],
    include_group_permissions: bool = True,
) -> set[str]:
    """Get all permissions a user has for a specific object.

    Group permissions are included BY DEFAULT. Results are memoized on the
    instance (Tier-1 cache, INSTANCE_PERMS_CACHE_ATTR) — see the
    Two-Tier Permission Cache section.
    """
```

### GraphQL Integration

#### Permission Annotation Mixin

```python
class AnnotatePermissionsForReadMixin:
    my_permissions = GenericScalar()

    def resolve_my_permissions(self, info) -> list[PermissionTypes]:
        # Check for pre-computed permissions (annotations/relationships only)
        model_name = self._meta.model_name
        if model_name in ['annotation', 'relationship', 'documentrelationship'] and hasattr(self, '_can_read'):
            # Use optimized pre-computed permissions from AnnotationService
            # These are annotated as _can_read, _can_create, _can_update, _can_delete
            permissions = set()
            if getattr(self, '_can_read', False):
                permissions.add(f"read_{model_name}")
            if getattr(self, '_can_update', False):
                permissions.add(f"update_{model_name}")
            # ... etc
            return list(permissions)

        # Standard permission resolution for other models
        # Uses cached permission metadata from middleware or direct DB query
```

#### Middleware

```python
class PermissionAnnotatingMiddleware:
    def resolve(self, next, root, info, **kwargs):
        # Detects Django model type from GraphQL resolver
        # Caches permission metadata in info.context.permission_annotations
        # Avoids repeated database queries for same model types
```

## Annotation Permission Inheritance

### Critical Change: No More Annotation-Level Permissions

**⚠️ ARCHITECTURAL CHANGE**: Individual annotation-level permissions have been completely eliminated. This means:

1. **No per-annotation permission storage** - Annotations don't have their own permission records in the database
2. **No per-annotation permission checks** - We never check permissions on individual annotation objects
3. **Uniform permissions for all annotations** - All annotations in a document have the same permissions
4. **Computed once, applied to all** - Permissions are computed at query time based on document+corpus

### Why This Change?

1. **Performance**: Eliminated N+1 query problem (checking permissions for each annotation)
2. **Security**: Simpler, more predictable permission model
3. **Consistency**: All annotations in a document have uniform access control
4. **Maintainability**: Less complex permission logic to maintain

### The New Model (Implemented)

Annotations and relationships use a special permission inheritance model that prioritizes document security:

```python
# From opencontractserver/annotations/services/annotation_service.py
# NOTE: deliberately ABBREVIATED — the ``...`` and prose comments sketch the
# shape; this is not copy-paste code. The implementation is the single
# source of truth.

class AnnotationService(BaseService):
    @classmethod
    def _compute_effective_permissions(
        cls,
        user,
        document_id: int,
        corpus_id: Optional[int] = None,
        context=None,
    ) -> tuple[bool, bool, bool, bool, bool]:
        """
        Compute effective permissions based on document and corpus.
        Document permissions are PRIMARY (most restrictive).

        Returns: (can_read, can_create, can_update, can_delete, can_comment)
        """
        # NOTE (scoped admin access, 2026-05): there is NO superuser
        # short-circuit here — admins are computed via the same
        # document+corpus logic below. (The structural-write break-glass lives
        # in AnnotationManager.user_can; the list services additionally mask
        # per-row structural _can_update/_can_delete to user.is_superuser.)

        # ``context`` (the GraphQL request) memoizes the answer per
        # (user, document, corpus) AND threads request= into the underlying
        # Document/Corpus ``user_can`` calls (Tier-2 cache, PR #1665).

        # Anonymous users only have read access to public documents/corpuses
        if user.is_anonymous:
            # document public? corpus (if given) public? → (True, False,
            # False, False, False); otherwise all False.
            ...

        # Authenticated: document permissions FIRST, each via the canonical
        # ``Document.objects.user_can(user, document, <perm>, request=context)``
        # — so creator status and group grants are honoured. No document READ
        # = no access at all. If no corpus, document permissions stand alone.

        # With a corpus: same five ``Corpus.objects.user_can`` checks, then
        # the most restrictive wins:
        #     final_<perm> = doc_<perm> AND corpus_<perm>
        # COMMENT has the one exception (BACON MODE): when
        # ``corpus.allow_comments`` is True, final_comment = final_read.
```

See the COMMENT Permission System section above for the full comment-mode
logic; the real implementation is the single source of truth.

### Special Cases

1. **Structural Annotations** ⚠️ **CRITICAL SECURITY RULE**
   - **ALWAYS READ-ONLY except for superusers**
   - **Cannot be edited, updated, or deleted by ANY user (including owners with full CRUD permissions)**
   - Only superusers can modify or delete structural annotations
   - This protection is enforced in `AnnotationManager.user_can` (`opencontractserver/shared/Managers.py`), before any other permission branch
   - Structural annotations are ALWAYS visible regardless of `created_by_*` fields
   - Filtered automatically when no corpus context

2. **Structural Relationships** ⚠️ **CRITICAL SECURITY RULE**
   - **ALWAYS READ-ONLY except for superusers**
   - **Cannot be edited, updated, or deleted by ANY user (including owners with full CRUD permissions)**
   - Only superusers can modify or delete structural relationships
   - This protection is enforced in `RelationshipManager.user_can` (`opencontractserver/shared/Managers.py`), before any other permission branch
   - Relationships inherit permissions from document+corpus (just like annotations)
   - Structural protection is checked BEFORE any other permission logic

3. **Analysis-Created Annotations** (NEW)
   - Annotations with `created_by_analysis` field set are private to that analysis
   - Only visible to users who have permission to the analysis object
   - Even if user has document+corpus permissions, they cannot see these annotations without analysis permission
   - Structural annotations are exempt from this privacy rule

4. **Extract-Created Annotations** (NEW)
   - Annotations with `created_by_extract` field set are private to that extract
   - Only visible to users who have permission to the extract object
   - Even if user has document+corpus permissions, they cannot see these annotations without extract permission
   - Structural annotations are exempt from this privacy rule

5. **Superuser Access (scoped admin access, 2026-05)**
   - Superusers are computed like a normal user for data — NO blanket bypass
   - They get only the permissions a normal user would (is_public READ / creator / explicit grant); they do NOT automatically see private analysis/extract annotations
   - **The one retained data privilege: superusers may write (modify/delete) structural annotations/relationships** — non-superusers are denied (structural-write break-glass)
   - Inspecting/repairing arbitrary data is done via the Django admin site

6. **Anonymous Users** (NEW)
   - Can access resources where `is_public=True`
   - Get READ-ONLY permissions (no CREATE, UPDATE, DELETE, COMMENT)
   - For annotations: BOTH document AND corpus must be public
   - For analyses: Only see public analyses in public corpuses
   - For extracts: No access (always filtered out)
   - For conversations: Only see `is_public=True` conversations

## Annotation Privacy Model (NEW)

### Overview

The annotation privacy model allows annotations to be marked as "created by" a specific analysis or extract, making them private to that source object. This provides fine-grained privacy control for programmatically generated annotations.

### Centralized Permission Checking - THE Single Source of Truth

**CRITICAL**: The canonical single-object authorization check is `Model.objects.user_can(user, obj, permission)` (manager surface) / `obj.user_can(user, permission)` (instance surface), defined per model in `opencontractserver/shared/Managers.py`. Never bypass this API or implement custom permission logic.

All permission checks for annotations and relationships go through the per-model `user_can` implementation, which automatically handles:

1. **Superuser handling (scoped admin access, 2026-05)** - Superusers are computed like a normal user; the ONLY exception is the structural-write break-glass (they may write structural items). No blanket full-permission bypass.
2. **Structural protection** - Structural annotations/relationships are ALWAYS read-only for non-superusers (superusers retain structural-write via the break-glass)
3. **Privacy enforcement** - Checks source object permissions for private annotations
4. **Permission inheritance** - Requires SAME permission level on source object as requested
5. **Document+corpus computation** - Uses `AnnotationService._compute_effective_permissions` for final permissions

**Implementation Details:**
- Structural annotation protection: `AnnotationManager.user_can` (`opencontractserver/shared/Managers.py`)
- Structural relationship protection: `RelationshipManager.user_can` (`opencontractserver/shared/Managers.py`)
- Both checks happen BEFORE any other permission logic
- `user_can` is the read/check counterpart of the `Model.objects.visible_to_user(user)` queryset filter; the two are pinned to agree by `opencontractserver/tests/permissioning/test_authorization_invariants.py`
- All mutations automatically respect this (RemoveAnnotation, UpdateAnnotation, RemoveRelationship, UpdateRelationship, etc.)

This means mutations don't need to understand the privacy model - they just call `obj.user_can(...)` and it handles everything.

**Important for Private Annotations**: Operations like DELETE require the matching permission on BOTH:
- The analysis/extract that created the annotation (DELETE permission)
- The document AND corpus (DELETE permission on both)
All requirements must be met or the operation is denied.

### Database Schema

```python
class Annotation(BaseOCModel):
    # Standard fields...

    # Privacy fields (NEW)
    created_by_analysis = ForeignKey(
        'analyzer.Analysis',
        null=True, blank=True,
        on_delete=SET_NULL,
        related_name='created_annotations',
        help_text='If set, this annotation is private to the analysis that created it'
    )

    created_by_extract = ForeignKey(
        'extracts.Extract',
        null=True, blank=True,
        on_delete=SET_NULL,
        related_name='created_annotations',
        help_text='If set, this annotation is private to the extract that created it'
    )

    class Meta:
        constraints = [
            CheckConstraint(
                check=Q(created_by_analysis__isnull=True) | Q(created_by_extract__isnull=True),
                name='annotation_created_by_only_one_source',
                violation_error_message='An annotation cannot be created by both an analysis and an extract'
            )
        ]
```

### Privacy Filtering in List Queries

The "which sources can this user see" subqueries are built ONCE, in
`opencontractserver/utils/source_visibility.py`, and shared by every list
path that applies the privacy gate (`AnnotationQuerySet.visible_to_user`,
`AnnotationService.get_document_annotations` / `get_corpus_annotations`,
`RelationshipManager.visible_to_user`, and
`RelationshipService.get_document_relationships`). The builders honour
**user- and group-level** guardian grants — matching `user_can`'s privacy
recursion, which resolves group grants by default — and encode the
anonymous rules (public analyses only; extracts never).

**Performance note:** each privacy gate embeds the visible-analysis and
visible-extract subqueries, including user- and group-level guardian grant
lookups. The concrete Guardian tables already carry unique B-tree indexes on
`(user, permission, content_object)` / `(group, permission, content_object)`;
the 2026-06 audit also adds hot-path companion indexes on
`(permission, user, content_object)` and `(permission, group, content_object)`
for the source privacy tables
(`anl_uop_perm_user_obj_idx`, `anl_gop_perm_grp_obj_idx`,
`ext_uop_perm_user_obj_idx`, `ext_gop_perm_grp_obj_idx`). Keep that shape
before adding new source-privacy list surfaces; otherwise annotation +
relationship requests can stack several nested subqueries in one page load.

```python
# In any privacy-gated list path:
from opencontractserver.utils.source_visibility import (
    visible_analyses_for,
    visible_extracts_for,
)

visible_analyses = visible_analyses_for(user)   # public | own | user-grant | group-grant
visible_extracts = visible_extracts_for(user)   # own | user-grant | group-grant (none for anonymous)

# Filter annotations: exclude private ones unless user has access
# BUT always include structural annotations (they're always visible)
qs = qs.exclude(
    # Exclude non-structural analysis-created annotations user can't see
    Q(created_by_analysis__isnull=False) &
    Q(structural=False) &  # Only apply privacy to non-structural
    ~Q(created_by_analysis__in=visible_analyses)
).exclude(
    # Exclude non-structural extract-created annotations user can't see
    Q(created_by_extract__isnull=False) &
    Q(structural=False) &  # Only apply privacy to non-structural
    ~Q(created_by_extract__in=visible_extracts)
)
```

### Import Process Updates

When importing annotations from an analysis, the system now automatically sets the `created_by_analysis` field:

```python
# In import_annotations_from_analysis()
annotation = Annotation.objects.create(
    annotation_label_id=label_id,
    document_id=doc_id,
    analysis_id=analysis_id,
    created_by_analysis_id=analysis_id,  # Mark as created by this analysis
    creator_id=creator_id,
    corpus=analysis.analyzed_corpus
)
```

### Mutation Integration

All annotation mutations now properly respect the privacy model through the centralized permission system:

```python
# Example from RemoveAnnotation mutation (config/graphql/annotation_mutations.py).
# Inline ``user_can`` is FORBIDDEN in config/graphql/ (E001) — mutations go
# through BaseService, which delegates to the same per-model user_can:
def mutate(root, info, annotation_id):
    annotation_pk = from_global_id(annotation_id)[1]  # Relay global id → pk
    annotation_obj = BaseService.get_or_none(
        Annotation, annotation_pk, info.context.user, request=info.context
    )  # IDOR-safe: None whether missing or unreadable

    # TRUTHINESS INVERSION (see BaseService.require_permission docstring):
    # require_permission returns "" (falsy) when GRANTED and a human-readable
    # denial string (truthy) when DENIED — it does NOT raise. The idiom below
    # reads as "if denied, bail". Do NOT transcribe the legacy
    # ``if user_can(...)`` direction onto this call — that flips the gate;
    # use BaseService.user_has when you want a boolean grant.
    if annotation_obj is None or BaseService.require_permission(
        annotation_obj, info.context.user, PermissionTypes.DELETE,
        request=info.context,
    ):
        return RemoveAnnotation(ok=False, message="Permission denied")

    annotation_obj.delete()
    return RemoveAnnotation(ok=True)
```

The mutations that have been updated to use this pattern include:
- **RemoveAnnotation** - Checks DELETE permission with privacy model
- **UpdateAnnotation** - Uses user_can_edit which internally calls user_can
- **RejectAnnotation** - Checks visibility before rejection
- **ApproveAnnotation** - Checks visibility before approval
- **AddRelationship** - Checks both annotations are visible
- **RemoveRelationship** - Checks DELETE permission on relationship

### Migration Strategy

For existing systems, a data migration is provided that:
1. Identifies existing annotations linked to analyses
2. Sets `created_by_analysis` for non-structural analysis annotations
3. Preserves backward compatibility with the `analysis` field

```python
def migrate_existing_analysis_annotations(apps, schema_editor):
    Annotation = apps.get_model('annotations', 'Annotation')

    # Update annotations that are linked to an analysis and are not structural
    updated = Annotation.objects.filter(
        analysis__isnull=False,
        structural=False
    ).update(
        created_by_analysis_id=models.F('analysis_id')
    )
```

## User Profile and Badge Visibility

### Overview

User profiles and badge awards have privacy controls that follow a consistent visibility model. This ensures that private user information is only visible to appropriate audiences.

### User Profile Privacy

User profiles have a `is_profile_public` boolean field that controls visibility:

**Visibility Rules:**
1. **Own Profile**: Always visible regardless of privacy setting
2. **Public Profiles** (`is_profile_public=True`): Visible to all authenticated users
3. **Private Profiles** (`is_profile_public=False`): Only visible via corpus membership with > READ permission
4. **Inactive Users** (`is_active=False`): Never visible through the app (incl. to superusers, scoped admin access 2026-05) — reachable only via the Django admin site
5. **Anonymous Users**: Can only see public profiles
6. **Superusers (scoped admin access, 2026-05)**: computed like a normal user — they see private profiles ONLY via the same shared-corpus-membership rule as anyone else; there is **no** `UserProfileManager` superuser bypass. Admin/moderation surfaces that legitimately need to reach a private-profile user (e.g. badge awarding) **authorize the action first and then resolve the target with a direct, unfiltered lookup** (`User.objects.filter(pk=..., is_active=True)`) rather than relying on profile visibility. Auditing arbitrary profiles is done via the Django admin site.

**Corpus Membership Visibility:**
Private profiles become visible to users who share a corpus where the private user has more than READ permission (i.e., CREATE, UPDATE, or DELETE). This ensures collaborators who are actively contributing to a corpus can see each other.

### Implementation: UserService

The `UserService` class in `opencontractserver/users/services/user_service.py` provides centralized user visibility logic:

```python
from opencontractserver.users.services import UserService

# Get all users visible to the requesting user
visible_users = UserService.get_visible_users(requesting_user)

# Check if a specific user is visible
is_visible = UserService.check_user_visibility(requesting_user, target_user_id)

# Search for users (for @mention autocomplete)
results = UserService.get_users_for_mention(requesting_user, text_search="alice")
```

**Key Methods:**

| Method | Description | Returns |
|--------|-------------|---------|
| `get_visible_users(user)` | All users visible to the requesting user | QuerySet |
| `check_user_visibility(user, target_id)` | Check if specific user is visible | bool |
| `get_users_for_mention(user, text_search)` | Search users for @mention (authenticated only) | QuerySet |

### Badge Visibility

Badge awards (`UserBadge` model) follow the recipient's profile privacy rules:

**Visibility Rules:**
1. **Own Badges**: Always visible regardless of recipient's profile privacy
2. **Badges of Public Users**: Visible to all authenticated users
3. **Badges of Private Users**: Visible only if recipient's profile is visible (via corpus membership)
4. **Corpus-Specific Badges**: Visible only to users with access to that corpus
5. **Anonymous Users**: Can only see badges of public users

### Implementation: BadgeService

The `BadgeService` class in `opencontractserver/badges/services/badge_service.py` provides centralized badge visibility logic:

```python
from opencontractserver.badges.services import BadgeService

# Get all badge awards visible to the requesting user
visible_badges = BadgeService.get_visible_user_badges(requesting_user)

# Check visibility of a specific badge award (IDOR-safe)
has_permission, badge_obj = BadgeService.check_user_badge_visibility(
    requesting_user, user_badge_id
)

# Get badges for a specific user (respects privacy)
user_badges = BadgeService.get_badges_for_user(requesting_user, target_user_id)
```

**Key Methods:**

| Method | Description | Returns |
|--------|-------------|---------|
| `get_visible_user_badges(user)` | All badge awards visible to user | QuerySet |
| `check_user_badge_visibility(user, badge_id)` | Check specific badge visibility (IDOR-safe) | tuple(bool, UserBadge or None) |
| `get_badges_for_user(user, target_user_id)` | Get visible badges for a specific user | QuerySet |

### IDOR Protection

Both services implement IDOR protection by returning the same response whether an object doesn't exist or the user lacks permission:

```python
# IDOR-safe check - same response for non-existent or inaccessible
has_permission, badge = BadgeService.check_user_badge_visibility(user, badge_id)
if not has_permission:
    return None  # Same response whether badge doesn't exist or user can't see it
```

### GraphQL Resolver Integration

The following GraphQL resolvers use these optimizers:

| Resolver | Service | Location |
|----------|---------|----------|
| `resolve_user_by_slug` | `UserService.get_visible_users` | `config/graphql/user_queries.py` |
| `resolve_search_users_for_mention` | `UserService.get_visible_users` | `config/graphql/search_queries.py` |
| `resolve_user_badges` | `BadgeService.get_visible_user_badges` | `config/graphql/social_queries.py` |
| `resolve_user_badge` | `BadgeService.check_user_badge_visibility` | `config/graphql/social_queries.py` |

### Testing

Comprehensive tests are available in:
- `opencontractserver/tests/permissioning/test_user_visibility.py` - 16 tests for user visibility
- `opencontractserver/tests/permissioning/test_badge_visibility.py` - 13 tests for badge visibility

---

## Document Actions Permissions

### Overview

Document actions (corpus actions, extracts, and analysis rows) follow the least-privilege model where effective permissions are the minimum of document and corpus permissions.

### Permission Model

**Formula:** `Effective Permission = MIN(document_permission, corpus_permission)`

This ensures:
- Users cannot access document-related data beyond their document permissions
- Corpus permissions provide additional restrictions, not expansions
- Consistent permission behavior across all document-related objects

### Implementation: DocumentActionsService

The `DocumentActionsService` class in `opencontractserver/documents/services/actions.py` provides centralized permission logic for document-related queries:

```python
from opencontractserver.documents.services import DocumentActionsService

# Get all actions/extracts/analyses for a document
result = DocumentActionsService.get_document_actions(
    user=requesting_user,
    document_id=document_id,
    corpus_id=corpus_id,  # Optional
    request=info.context,  # Optional — engages the Tier-2 permission cache
)
# Returns: {"corpus_actions": [...], "extracts": [...], "analysis_rows": [...]}

# Get corpus actions for a corpus
corpus_actions = DocumentActionsService.get_corpus_actions_for_corpus(
    user=requesting_user,
    corpus_id=corpus_id
)

# Get extracts that include a document
extracts = DocumentActionsService.get_extracts_for_document(
    user=requesting_user,
    document_id=document_id,
    corpus_id=corpus_id  # Optional
)

# Get analysis rows for a document
analysis_rows = DocumentActionsService.get_analysis_rows_for_document(
    user=requesting_user,
    document_id=document_id,
    corpus_id=corpus_id  # Optional
)
```

**Key Methods:**

| Method | Description | Returns |
|--------|-------------|---------|
| `get_document_actions(user, doc_id, corpus_id)` | All actions/extracts/analyses for document | dict |
| `get_corpus_actions_for_corpus(user, corpus_id)` | Corpus actions for a corpus | QuerySet |
| `get_extracts_for_document(user, doc_id, corpus_id)` | Extracts including a document | QuerySet |
| `get_analysis_rows_for_document(user, doc_id, corpus_id)` | Analysis rows for a document | QuerySet |

### Permission Checking

The service gates on the canonical `user_can` API — no private helper
methods, no superuser branch (scoped admin access, 2026-05):

```python
# Inside get_document_actions:
if not document.user_can(user, PermissionTypes.READ, request=request):
    return empty_result
if corpus_id and not corpus.user_can(user, PermissionTypes.READ, request=request):
    return empty_result
```

`user_can` grants READ if the object is public, the user is the creator, or
the user holds an explicit guardian grant (user- or group-level). Superusers
are computed exactly like a normal user.

### Integration with Other Optimizers

The `DocumentActionsService` leverages the per-app services for consistent permission filtering:

- **`ExtractService`** (`opencontractserver/extracts/services/extract_service.py`): filters visible extracts (hybrid model — extract permission AND corpus READ)
- **`AnalysisService`** (`opencontractserver/analyzer/services/analysis_service.py`): filters visible analyses (same hybrid model)

```python
# Example: How get_document_actions composes the services
def get_document_actions(cls, user, document_id, corpus_id=None, *, request=None):
    # 1. Check document permission (canonical user_can)
    if not document.user_can(user, PermissionTypes.READ, request=request):
        return empty_result

    # 2. Check corpus permission (if provided)
    if corpus_id and not corpus.user_can(user, PermissionTypes.READ, request=request):
        return empty_result

    # 3. Use ExtractService for extracts
    visible_extracts = ExtractService.get_visible_extracts(user, corpus_id=corpus_id, context=request)
    result["extracts"] = visible_extracts.filter(documents=document)

    # 4. Use AnalysisService for analysis rows
    visible_analyses = AnalysisService.get_visible_analyses(user, corpus_id=corpus_id, context=request)
    result["analysis_rows"] = document.rows.filter(analysis__in=visible_analyses)

    return result
```

### GraphQL Resolver Integration

The `resolve_document_corpus_actions` resolver (`config/graphql/action_queries.py`) uses this service:

```python
def resolve_document_corpus_actions(self, info, document_id, corpus_id=None):
    result = DocumentActionsService.get_document_actions(
        user=info.context.user,
        document_id=decode_id(document_id),
        corpus_id=decode_id(corpus_id) if corpus_id else None,
        request=info.context,
    )
    return result
```

### Testing

Comprehensive tests are available in:
- `opencontractserver/tests/permissioning/test_document_actions_permissions.py` - 11 tests

Key test scenarios:
- Document owner can see their document's actions
- Users without document permission get empty results
- Corpus permission filtering works correctly
- Anonymous user handling
- Superuser handling: computed like a normal user — sees document actions only for documents/corpora it can access (no blanket access; scoped admin access 2026-05)

---

## Performance Optimizations

### Query Optimizer

The system uses a query optimizer to eliminate N+1 permission queries that plagued the old individual annotation permission model:

```python
# OLD MODEL (ELIMINATED):
# Each annotation had its own permission records in the database
for annotation in annotations:
    # This would query annotationuserobjectpermission table for EACH annotation!
    check_permission(user, annotation)  # N database queries!

# NEW MODEL:
# No annotation permissions in database - compute from document+corpus
permissions = compute_permissions(user, document, corpus)  # Just 2 queries total
# Apply same permissions to ALL annotations
queryset.annotate(
    _can_read=Value(permissions.can_read),
    _can_update=Value(permissions.can_update),
    # ...
)
```

### Database Impact

The elimination of annotation-level permissions means:
- No `annotationuserobjectpermission` table queries
- No `annotationgroupobjectpermission` table queries
- Just 2 permission checks total (document + corpus) regardless of annotation count

### Benefits

1. **Eliminated N+1 Queries**: From O(n) to O(1) permission checks
2. **Reduced Database Load**: 2 permission queries total instead of 1 per annotation
3. **Consistent Performance**: Scales with any number of annotations
4. **Backwards Compatible**: GraphQL API unchanged

### Implementation Details

The optimization is transparent to the GraphQL layer:

```python
# In resolve_all_annotations (config/graphql/document_types.py)
queryset = AnnotationService.get_document_annotations(
    document_id=self.id,
    user=info.context.user,
    corpus_id=corpus_pk,
    analysis_id=analysis_pk,
    context=info.context,  # request-scoped permission + instance caches
)
# Queryset already has permissions annotated (_can_read, _can_update, …)
```

## GraphQL Query Patterns

### Querying Annotations - CRITICAL Requirements

**IMPORTANT**: When querying annotations through GraphQL, you MUST:
1. Use the `allAnnotations` field (NOT `annotations`)
2. Include the `corpusId` parameter for proper permission filtering
3. Understand the `analysis_id` parameter behavior (optional but important)

#### The `analysis` Field vs `created_by_analysis` Field

There are TWO separate fields that control annotation visibility:

1. **`analysis` field** (ForeignKey): Links an annotation to an analysis for organizational purposes
2. **`created_by_analysis` field** (ForeignKey): Marks an annotation as PRIVATE to an analysis

These serve different purposes and are filtered differently!

#### Query Modes: Manual vs Analysis-Specific

The `allAnnotations` field has **two distinct query modes** based on the `analysis_id` parameter:

**Mode 1: Manual/User Annotations Only** (NO `analysis_id` provided):
```graphql
query {
    document(id: "DocumentID") {
        allAnnotations(corpusId: "CorpusID") {
            # Returns ONLY annotations where analysis field is NULL
            # Even if you have permission to see analysis-linked annotations,
            # they will be excluded unless you specify analysis_id
            id
            rawText
        }
    }
}
```

**Mode 2: Specific Analysis Annotations** (`analysis_id` provided):
```graphql
query {
    document(id: "DocumentID") {
        allAnnotations(corpusId: "CorpusID", analysisId: "AnalysisID") {
            # Returns ONLY annotations from this specific analysis
            # User must have permission to the analysis object
            id
            rawText
        }
    }
}
```

#### Why This Design?

This separation allows users to:
- View their "manual" work without mixing in analysis-generated annotations
- View specific analysis results by querying with that `analysis_id`
- Avoid confusion when multiple analyses create annotations on the same document

#### Privacy Filtering (Separate from Query Mode)

The `created_by_analysis` and `created_by_extract` fields add an ADDITIONAL privacy layer:
- Annotations marked as `created_by_analysis` are ONLY visible if you have permission to that analysis
- Annotations marked as `created_by_extract` are ONLY visible if you have permission to that extract
- This applies REGARDLESS of which query mode you're using

#### Complete Examples

**Example 1: User's Manual Annotations**
```graphql
# Query without analysis_id - sees manual annotations only
query {
    document(id: "DocumentID") {
        allAnnotations(corpusId: "CorpusID") {
            id
            rawText
            # Will NOT include analysis-linked annotations
            # even if you created them or have permission
        }
    }
}
```

**Example 2: Specific Analysis Results**
```graphql
# Query with analysis_id - sees that analysis's annotations
query {
    document(id: "DocumentID") {
        allAnnotations(corpusId: "CorpusID", analysisId: "AnalysisID123") {
            id
            rawText
            # Will ONLY include annotations from AnalysisID123
            # Requires READ permission on the analysis object
        }
    }
}
```

**Example 3: Extract-Based Annotations**
```graphql
# Extract annotations appear in manual mode if:
# 1. They have NO analysis field set
# 2. User has permission to the extract
query {
    document(id: "DocumentID") {
        allAnnotations(corpusId: "CorpusID") {
            id
            rawText
            # Includes extract annotations (if analysis field is null)
        }
    }
}
```

#### Common Query Mistakes

```graphql
# WRONG - Will return empty or incorrect results
query {
    document(id: "DocumentID") {
        annotations {  # Wrong field name!
            ...
        }
    }
}

# WRONG - Missing corpusId parameter
query {
    document(id: "DocumentID") {
        allAnnotations {  # Missing corpusId!
            ...
        }
    }
}

# POTENTIAL CONFUSION - This won't show analysis annotations
query {
    document(id: "DocumentID") {
        allAnnotations(corpusId: "CorpusID") {
            # Missing analysis_id means MANUAL ONLY
            # Analysis-linked annotations will be excluded
        }
    }
}
```

**Why corpusId is Required**: The permission system needs the corpus context to properly compute annotation visibility, including filtering private annotations based on analysis/extract permissions.

## Frontend Implementation

### State Management (Jotai Atoms)

```typescript
// Document permissions
const documentPermissionsAtom = atom<string[]>([]);

// Corpus state (includes permissions)
const corpusStateAtom = atom({
  canUpdateCorpus: false,
  myPermissions: []
});
```

### Permission Hooks

```typescript
// Document permissions
export const useDocumentPermissions = () => {
  const [permissions, setPermissions] = useAtom(documentPermissionsAtom);
  return { permissions, setPermissions };
};

// Corpus state
export const useCorpusState = () => {
  const corpusState = useAtomValue(corpusStateAtom);
  return {
    canUpdateCorpus: corpusState.canUpdateCorpus,
    myPermissions: corpusState.myPermissions
  };
};
```

### Permission Evaluation Logic

For standard document viewing (corpus context optional):
```typescript
// From DocumentKnowledgeBase.tsx
const canEdit = React.useMemo(() => {
  // Explicit readOnly prop overrides all
  if (readOnly) return false;

  // No corpus = limited editing capabilities
  if (!corpusId) return false;

  // Corpus permissions can enable editing
  if (canUpdateCorpus) return true;

  // Fallback to document permissions
  return permissions.includes(PermissionTypes.CAN_UPDATE);
}, [readOnly, corpusId, permissions, canUpdateCorpus]);
```

Note: For annotations specifically, the backend handles the document+corpus permission logic.

## Component Integration

### Core Components

#### DocumentKnowledgeBase
- Evaluates permissions from both document and corpus sources
- Passes `read_only` prop to child components
- Annotations receive permissions from backend query optimizer

#### PDF Component
```typescript
<PDF
  read_only={!canEdit}
  createAnnotationHandler={canEdit ? handleCreate : undefined}
/>
```

#### TxtAnnotator
```typescript
<TxtAnnotatorWrapper
  readOnly={!canEdit}
  allowInput={canEdit}
/>
```

### Component Patterns

#### Pattern 1: Conditional Rendering
```typescript
{canEdit && (
  <Button onClick={handleEdit}>Edit</Button>
)}
```

#### Pattern 2: Prop Passing
```typescript
<ChildComponent
  readOnly={!canEdit}
  onEdit={canEdit ? handleEdit : undefined}
/>
```

#### Pattern 3: Feature Gating
```typescript
const { isFeatureAvailable } = useFeatureAvailability(corpusId);

if (!isFeatureAvailable('ANNOTATIONS')) {
  return <EmptyState>Add to corpus to enable annotations</EmptyState>;
}
```

### Read-Only Mode Support

Components that properly support read-only mode:

- ✅ **PDF Component**: Prevents annotation creation
- ✅ **TxtAnnotatorWrapper**: Disables input
- ✅ **SelectionLayer**: Shows read-only messages
- ✅ **AnnotationMenu**: Shows only copy option
- ✅ **FloatingControls**: Hides edit actions
- ✅ **Content Feed**: Passes readOnly to children

## Testing

### Comprehensive Test Coverage

The permission system is thoroughly tested in:
- `opencontractserver/tests/permissioning/test_authorization_invariants.py` - **The filter/check parity suite** (`visible_to_user ⟺ user_can(READ)` per model, incl. relationship privacy recursion and group-granted sources)
- `opencontractserver/tests/permissioning/test_annotation_privacy_scoping.py` - Proves annotation privacy scoping works
- `opencontractserver/tests/permissioning/test_relationship_privacy_scoping.py` - Relationship privacy scoping through the document-view listing (2026-06)
- `opencontractserver/tests/permissioning/test_source_visibility_group_grants.py` - Group-granted analysis/extract permissions unlock private rows in list queries (2026-06)
- `opencontractserver/tests/permissioning/test_extract_anonymous_lockdown.py` - Extracts are never anonymous-visible, at manager AND service layers (2026-06)
- `opencontractserver/tests/permissioning/test_structural_mypermissions_breakglass.py` - Pre-computed myPermissions mirror the structural-write break-glass (2026-06)
- `opencontractserver/tests/permissioning/test_annotation_permission_inheritance.py` - Validates inheritance model
- `opencontractserver/tests/permissioning/test_analysis_extract_hybrid_permissions.py` - Tests hybrid permission model
- `opencontractserver/tests/test_structural_protection.py` - **Tests structural annotation/relationship protection**
- `opencontractserver/tests/test_relationship_mutation_permissions.py` - Tests relationship permission inheritance

These tests definitively prove that:
1. Private annotations are properly scoped to analyses/extracts
2. Multiple teams can work on shared corpuses without seeing each other's private annotations
3. Permission changes take effect immediately
4. Mutations properly respect the privacy model
5. **Structural annotations/relationships CANNOT be modified by non-superusers (even owners with full CRUD)**
6. Relationships inherit permissions from document+corpus exactly like annotations

### Backend Tests

#### Permission Setting Tests
```python
def test_permission_replacement():
    # Give user all permissions
    set_permissions_for_obj_to_user(
        user_val=user,
        instance=document,
        permissions=[PermissionTypes.ALL]
    )

    # Replace with just READ
    set_permissions_for_obj_to_user(
        user_val=user,
        instance=document,
        permissions=[PermissionTypes.READ]
    )

    # Should ONLY have READ (not ALL permissions)
    perms = get_users_permissions_for_obj(user, document, include_group_permissions=True)
    assert perms == {'read_document'}
```

**Important Testing Note**: The test suite uses GraphQL clients with mock contexts to test permission inheritance through the full stack, ensuring that the optimization layer and GraphQL resolvers work correctly together.

#### Annotation Permission Inheritance Tests
```python
def test_document_primary_permissions():
    # Document: READ only
    # Corpus: UPDATE allowed
    # Result: Annotation should be READ-ONLY (most restrictive)

    set_permissions_for_obj_to_user(user, document, [PermissionTypes.READ])
    set_permissions_for_obj_to_user(user, corpus, [PermissionTypes.UPDATE])

    annotations = AnnotationService.get_document_annotations(
        document_id=document.id,
        user=user,
        corpus_id=corpus.id
    )

    # Annotations should be read-only despite corpus having update
    for ann in annotations:
        assert ann._can_read == True
        assert ann._can_update == False  # Document restriction applies
```

#### Annotation Privacy Tests (NEW)
```python
def test_analysis_created_annotation_privacy():
    # Create annotation marked as created by analysis
    private_annotation = Annotation.objects.create(
        annotation_label=label,
        document=doc,
        corpus=corpus,
        analysis=analysis,
        created_by_analysis=analysis,  # Mark as private to analysis
        creator=owner
    )

    # User with doc+corpus but NO analysis permission
    set_permissions_for_obj_to_user(viewer, doc, [PermissionTypes.READ])
    set_permissions_for_obj_to_user(viewer, corpus, [PermissionTypes.READ])

    # Should NOT see the private annotation
    visible = AnnotationService.get_document_annotations(
        document_id=doc.id,
        user=viewer,
        corpus_id=corpus.id
    )
    assert private_annotation not in visible

    # Grant analysis permission
    set_permissions_for_obj_to_user(viewer, analysis, [PermissionTypes.READ])

    # Now should see the annotation
    visible = AnnotationService.get_document_annotations(
        document_id=doc.id,
        user=viewer,
        corpus_id=corpus.id
    )
    assert private_annotation in visible

def test_structural_annotations_always_visible():
    # Structural annotations bypass privacy rules
    structural = Annotation.objects.create(
        annotation_label=label,
        document=doc,
        corpus=corpus,
        analysis=analysis,
        created_by_analysis=analysis,  # Private to analysis
        structural=True,  # BUT structural overrides privacy
        creator=owner
    )

    # User WITHOUT analysis permission
    visible = AnnotationService.get_document_annotations(
        document_id=doc.id,
        user=viewer,
        corpus_id=corpus.id,
        structural=True
    )
    assert structural in visible  # Still visible because structural
```

#### Structural Protection Tests (CRITICAL)
```python
def test_owner_cannot_update_structural_annotation():
    """Owner CANNOT UPDATE structural annotations even with full permissions."""
    # Create structural annotation
    structural_annotation = Annotation.objects.create(
        annotation_label=token_label,
        document=doc,
        corpus=corpus,
        creator=owner,
        structural=True,
    )

    # Grant owner FULL permissions on document and corpus
    set_permissions_for_obj_to_user(owner, doc, [PermissionTypes.CRUD])
    set_permissions_for_obj_to_user(owner, corpus, [PermissionTypes.CRUD])

    # Owner STILL cannot update structural annotation
    assert not structural_annotation.user_can(owner, PermissionTypes.UPDATE)

def test_superuser_can_update_structural_annotation():
    """Superuser CAN UPDATE structural annotations."""
    superuser = User.objects.create_superuser(username="super", password="test")

    # Superuser can modify structural items
    assert structural_annotation.user_can(superuser, PermissionTypes.UPDATE)

def test_owner_cannot_delete_structural_relationship():
    """Owner CANNOT DELETE structural relationships even with full permissions."""
    structural_rel = Relationship.objects.create(
        relationship_label=relationship_label,
        document=doc,
        corpus=corpus,
        creator=owner,
        structural=True,
    )

    # Owner has full permissions
    set_permissions_for_obj_to_user(owner, doc, [PermissionTypes.CRUD])
    set_permissions_for_obj_to_user(owner, corpus, [PermissionTypes.CRUD])

    # But STILL cannot delete structural relationship
    assert not structural_rel.user_can(owner, PermissionTypes.DELETE)
```

**Key Validation Points:**
- File: `opencontractserver/tests/test_structural_protection.py`
- 12 comprehensive tests covering annotations and relationships
- Tests verify non-superusers CANNOT modify structural items even with CRUD
- Tests verify superusers CAN modify structural items
- Tests verify non-structural items work normally

### Frontend Tests

```typescript
describe('Permission Flow', () => {
  it('should handle annotation permissions from backend', async () => {
    const mocks = [
      createAnnotationQueryMock({
        annotations: [{
          id: '1',
          myPermissions: ['read_annotation']  // Backend computed
        }]
      })
    ];

    render(
      <MockedProvider mocks={mocks}>
        <DocumentKnowledgeBase documentId="123" corpusId="456" />
      </MockedProvider>
    );

    // Annotations should be read-only as determined by backend
    await waitFor(() => {
      expect(screen.getByTestId('annotation-1')).toHaveAttribute('data-readonly', 'true');
    });
  });
});
```

## Troubleshooting

### Common Issues

#### Annotations appear editable when document is read-only
- **Check**: Backend query optimizer is being used for annotation queries
- **Check**: Document permissions are being checked first in `_compute_effective_permissions`
- **Check**: Frontend is respecting the `myPermissions` from annotations

#### Private annotations appearing when they shouldn't (NEW)
- **Check**: `created_by_analysis` or `created_by_extract` fields are properly set
- **Check**: User does NOT have permission to the analysis/extract object
- **Check**: Query optimizer is filtering based on visible_analyses/visible_extracts
- **Note**: Structural annotations bypass privacy and are always visible

#### Permission changes not taking effect
- **Issue**: Old permissions weren't being removed
- **Fix**: `set_permissions_for_obj_to_user` now removes all permissions before adding new ones
- **Verify**: Check database directly to ensure old permissions are removed

#### N+1 Query Performance Issues
- **Check**: Annotation queries use `AnnotationService`
- **Check**: `_can_*` attributes are present on annotation querysets
- **Check**: `AnnotationType.get_queryset()` detects and preserves pre-computed permissions

#### Mutual exclusivity constraint violations (NEW)
- **Error**: "An annotation cannot be created by both an analysis and an extract"
- **Check**: Never set both `created_by_analysis` AND `created_by_extract`
- **Fix**: Choose one source of creation per annotation
- **Database**: Enforced by CheckConstraint at database level

### Debug Steps

1. **Check Query Optimizer**: Verify annotation queries go through optimizer
2. **Inspect Permissions**: Check `_can_*` attributes on annotation objects
3. **Review Database**: Directly query permission tables to verify state
4. **GraphQL Responses**: Check `myPermissions` in network tab
5. **Add Logging**: Use logger in `_compute_effective_permissions` for debugging

### Performance Monitoring

- **Query Count**: Monitor Django Debug Toolbar for permission query count
- **Optimizer Usage**: Log when query optimizer is used vs. fallback
- **Cache Hit Rate**: Track permission metadata cache effectiveness
- **Response Time**: Measure annotation query response times

## Security Considerations

1. **Document-First Security**: Annotations never exceed document permissions
2. **Server-Side Enforcement**: All mutations validate permissions on backend
3. **No Client Trust**: Frontend permissions are UX hints only
4. **Fail-Safe Defaults**: Default to most restrictive permissions on errors
5. **Audit Trail**: Permission changes are logged for security auditing

## Migration Guide

### For Existing Systems

#### From Individual Annotation Permissions

If migrating from a system with individual annotation permissions:

1. **Database Cleanup**: Remove any `annotationuserobjectpermission` and `annotationgroupobjectpermission` records
2. **Code Updates**: Remove any code that sets permissions on individual annotations
3. **Permission Strategy**: Ensure document and corpus permissions are properly set
4. **User Education**: Inform users that all annotations in a document now share the same permissions

#### From Corpus-Override Model

If migrating from the old permission model where corpus overrode documents:

1. **Review Permission Logic**: Document permissions are now primary for annotations
2. **Update Tests**: Tests assuming corpus override need updating
3. **User Communication**: Inform users that annotation permissions now follow document security
4. **Data Audit**: Review existing permission sets for consistency

### Breaking Changes

- ❌ **Cannot set permissions on individual annotations** - Use document/corpus permissions instead
- ❌ **Cannot have different permissions for different annotations in same document** - All share same permissions
- ❌ **Corpus permissions no longer override document permissions** - Most restrictive wins

## Implementation Notes for Analyses/Extracts

### Query Pattern for Analyses/Extracts

```python
def get_visible_analyses(user, corpus_id=None):
    """
    Get analyses visible to user based on:
    1. User has READ permission on analysis
    2. User has READ permission on corpus
    3. Filter annotations to only those on readable documents
    """
    # Step 1: Get analyses user has permission to read
    analyses = Analysis.objects.filter(
        # User has explicit permission OR analysis is public
        Q(analysisuserobjectpermission__user=user) | Q(is_public=True)
    )

    # Step 2: Filter by corpus permission
    if corpus_id:
        analyses = analyses.filter(
            analyzed_corpus_id=corpus_id,
            analyzed_corpus__in=Corpus.objects.visible_to_user(user)
        )

    # Step 3: When fetching annotations, filter by document permissions
    # This happens in the annotation resolver using existing optimizer

    return analyses
```

### GraphQL Resolver Pattern

```python
def resolve_analysis_annotations(analysis, info):
    """
    Resolve annotations within an analysis, filtered by document permissions.
    """
    # Use existing AnnotationService
    user = info.context.user

    # Get all annotation IDs from this analysis
    annotation_ids = analysis.annotations.values_list('id', flat=True)

    # Filter to only those on documents user can read
    visible_annotations = []
    for doc_id in analysis.analyzed_documents.values_list('id', flat=True):
        if doc.user_can(user, PermissionTypes.READ):
            visible_annotations.extend(
                annotation_ids.filter(document_id=doc_id)
            )

    return Annotation.objects.filter(id__in=visible_annotations)
```

## Common Pitfalls and Solutions

### Pitfall 1: Forgetting corpusId in GraphQL queries
**Problem**: Querying `allAnnotations` without `corpusId` returns **structural annotations only** (corpus-scoped user annotations are omitted; requesting `isStructural: false` without a corpus returns empty)
**Solution**: ALWAYS include `corpusId` parameter when you want user/manual annotations

### Pitfall 2: Not understanding analysis_id parameter behavior
**Problem**: Expecting to see all annotations (manual + analysis) when querying without `analysis_id`
**Reality**: Querying without `analysis_id` returns ONLY manual annotations (where `analysis` field is NULL)
**Solution**:
- Use NO `analysis_id` parameter to get manual/user annotations
- Use specific `analysis_id` to get annotations from that analysis only
- If you need to see annotations from multiple sources, make separate queries
**Example**:
```graphql
# This will NOT show analysis annotations even if you have permission
query {
    document(id: "Doc123") {
        allAnnotations(corpusId: "Corpus456") {
            id  # Only manual annotations
        }
    }
}

# To see analysis annotations, provide analysis_id
query {
    document(id: "Doc123") {
        allAnnotations(corpusId: "Corpus456", analysisId: "Analysis789") {
            id  # Only annotations from Analysis789
        }
    }
}
```

### Pitfall 3: Assuming analysis permission alone is enough for mutations
**Problem**: Trying to delete private annotations with only analysis permission fails
**Solution**: Ensure user has matching permission level on document AND corpus too

### Pitfall 4: Trying to modify structural annotations
**Problem**: Structural annotations are ALWAYS read-only, updates will fail
**Solution**: Check `annotation.structural` before attempting modifications

### Pitfall 5: Using wrong field names in GraphQL
**Problem**: Using `annotations` instead of `allAnnotations` in queries
**Solution**: Always use `allAnnotations` field name for querying document annotations

### Pitfall 6: Using a raw permission check for corpus-scoped visibility
**Problem**: A raw single-object check doesn't account for corpus context
**Solution**: For corpus-scoped objects (documents in corpus, metadata), use the `visible_to_user()` pattern:
```python
# WRONG - misses corpus context
has_read = document.user_can(user, PermissionTypes.READ)

# CORRECT - handles full visibility model
is_visible = Document.objects.visible_to_user(user).filter(id=doc_id).exists()
```

**When to use each:**
- `user_can`: single-object authorization checks (write permissions, top-level objects)
- `Model.objects.visible_to_user()`: READ/visibility checks for corpus-scoped objects

## @ Mention Permissions (NEW)

### Overview

The @ mention system allows users to reference corpuses and documents in discussions using patterns like `@corpus:slug`, `@document:slug`, or `@corpus:slug/document:slug`. Mention permissions follow a **write-permission-required** model to prevent information leakage and ensure users only mention resources in collaborative contexts.

**See detailed specification:** `docs/permissioning/mention_permissioning_spec.md`

### Core Principles

1. **Write Permission Required (Private Resources)**: Users must have CREATE, UPDATE, or DELETE permission to mention private corpuses/documents
2. **Read Permission Sufficient (Public Resources)**: Public resources can be mentioned by anyone with READ access
3. **IDOR Protection**: Autocomplete searches never reveal existence of inaccessible resources
4. **Viewer-Filtered Rendering**: Mention chips only render for viewers with appropriate permissions

### Permission Rules

#### Corpus Mentions (`@corpus:slug`)

Users can autocomplete/mention a corpus if they have **at least one of**:
- **Creator**: User created the corpus
- **Write Permission**: User has `create_corpus`, `update_corpus`, or `delete_corpus` permission
- **Public Corpus**: Corpus is marked `is_public=True`

**Rationale**: Mentioning implies collaborative context; read-only viewers shouldn't draw attention to resources they can't contribute to.

#### Document Mentions (`@document:slug` or `@corpus:slug/document:slug`)

Users can autocomplete/mention a document if they have **at least one of**:
- **Creator**: User created the document
- **Write Permission on Document**: User has `create_document`, `update_document`, or `delete_document` on document
- **Write Permission on Parent Corpus**: Document is in a corpus where user has write permission
- **Public Document in Accessible Context**: Document is `is_public=True` AND (no corpus OR public corpus OR user has READ access to corpus)

**Rationale**: Similar to corpuses, but public documents are included for open forum discussions.

### Backend Implementation

#### Autocomplete Filtering

```python
# In config/graphql/search_queries.py
# NOTE: these mention resolvers inline guardian ``get_objects_for_user`` —
# legal under E001 (which scans only visible_to_user / user_can /
# user_has_permission_for_obj) but an acknowledged exception to the
# service-layer policy; migration into a service is a known follow-up.

def resolve_search_corpuses_for_mention(self, info, text_search=None, **kwargs):
    """Only returns corpuses where user can meaningfully contribute."""
    from guardian.shortcuts import get_objects_for_user

    user = info.context.user

    if user.is_anonymous:
        return Corpus.objects.none()

    # Scoped admin access (2026-05): NO superuser branch — admins are computed
    # like a normal user (creator / writable / public), same as anyone else.

    # Get corpuses user has write permission to
    writable_corpuses = get_objects_for_user(
        user,
        ["corpuses.create_corpus", "corpuses.update_corpus", "corpuses.delete_corpus"],
        klass=Corpus,
        any_perm=True
    )

    # Combine: creator OR writable OR public
    qs = Corpus.objects.filter(
        Q(creator=user) | Q(id__in=writable_corpuses) | Q(is_public=True)
    ).distinct()

    return qs
```

#### Mention Rendering with Viewer Filtering

The `mentionedResources` field on `MessageType` resolves mentioned resources **per viewer**:

```python
def resolve_mentioned_resources(self, info):
    """
    Parse message content and resolve mentioned resources.
    SECURITY: Only returns resources visible to requesting user.
    """
    user = info.context.user
    content = self.content or ""

    # Parse mention patterns (regex)
    resources = []

    for corpus_slug in parse_corpus_mentions(content):
        try:
            corpus = Corpus.objects.get(slug=corpus_slug)
            if corpus.user_can(user, PermissionTypes.READ):
                resources.append({
                    'type': 'CORPUS',
                    'slug': corpus_slug,
                    'title': corpus.title,
                    # ...
                })
        except Corpus.DoesNotExist:
            # Resource doesn't exist or user can't see it - skip silently (IDOR protection)
            pass

    return resources
```

### Frontend Implementation

The frontend **trusts backend filtering** and has no client-side permission logic:

#### Autocomplete
```typescript
// useResourceMentionSearch hook
export function useResourceMentionSearch(query: string) {
  // Query backend with search text
  const [searchCorpuses] = useLazyQuery(SEARCH_CORPUSES_FOR_MENTION);
  const [searchDocuments] = useLazyQuery(SEARCH_DOCUMENTS_FOR_MENTION);

  // Backend has already filtered - frontend displays results as-is
  // No client-side permission checks
}
```

#### Rendering
```typescript
// parseMentionsInContent function
export function parseMentionsInContent(
  content: string,
  mentionedResources: MentionedResource[]  // Already viewer-filtered by backend
): React.ReactNode {
  const mentionMap = new Map();
  mentionedResources.forEach(resource => {
    mentionMap.set(getMentionPattern(resource), resource);
  });

  // Parse content for mention patterns
  // If resource in mentionMap: render chip
  // If not in mentionMap: render plain text (IDOR protection)
}
```

### IDOR Protection Strategy

1. **Autocomplete**: Only shows resources user has write permission to (or public resources)
2. **Mention Parsing**: Backend filters `mentionedResources` per viewer
3. **Chip Rendering**: Inaccessible mentions render as plain text, not chips
4. **Error Messages**: Same message whether resource doesn't exist or user lacks permission
5. **No Timing Attacks**: All resource lookups use same execution path

### Example Scenarios

#### Scenario 1: Private Corpus Mention
```python
# Setup
owner = create_user("owner")
viewer = create_user("viewer")

private_corpus = Corpus.objects.create(
    title="Private Legal Corpus",
    creator=owner,
    is_public=False
)

# Give viewer READ permission (not write)
set_permissions_for_obj_to_user(viewer, private_corpus, [PermissionTypes.READ])

# Autocomplete test
owner_results = search_corpuses_for_mention(owner, "Legal")
assert private_corpus in owner_results  # Owner can mention

viewer_results = search_corpuses_for_mention(viewer, "Legal")
assert private_corpus not in viewer_results  # Viewer cannot mention (read-only)
```

#### Scenario 2: Public Document Mention
```python
# Setup
public_doc = Document.objects.create(
    title="Public Contract Template",
    is_public=True,
    creator=owner
)

# Public documents are mentionable by anyone (even read-only users)
viewer_results = search_documents_for_mention(viewer, "Contract")
assert public_doc in viewer_results  # Viewer can mention public document
```

#### Scenario 3: Mention Rendering with Different Viewers
```python
# Message content
content = "Check @corpus:private-legal for details"

# Owner viewing message
owner_resources = message.mentioned_resources(owner)
assert len(owner_resources) == 1  # Owner sees mention

# Viewer viewing same message
viewer_resources = message.mentioned_resources(viewer)
assert len(viewer_resources) == 0  # Viewer doesn't see mention

# Frontend renders:
# - For owner: Clickable chip "Private Legal Corpus"
# - For viewer: Plain text "@corpus:private-legal" (no chip)
```

### Testing Requirements

**Backend Tests** (`opencontractserver/tests/test_mention_permissions.py`):
- [ ] Corpus autocomplete respects write permissions
- [ ] Document autocomplete respects write + corpus permissions
- [ ] Public resources are mentionable with read-only access
- [ ] Anonymous users cannot mention anything
- [ ] `mentionedResources` filters by viewer permissions
- [ ] IDOR protection: same error for non-existent vs. inaccessible

**Frontend Tests** (planned — no dedicated mention-permission spec exists yet):
- [ ] Autocomplete displays backend-filtered results
- [ ] Inaccessible mentions render as plain text
- [ ] Accessible mentions render as clickable chips
- [ ] No client-side permission filtering

### Migration Notes

When deploying this feature:
1. **No data migration needed** - permission checks are query-time only
2. **Existing mentions gracefully degrade** - inaccessible mentions become plain text
3. **Permission changes take effect immediately** - no caching of mention visibility

### Security Audit Checklist

- [x] Autocomplete uses write permission filtering (not just read)
- [x] Backend filters `mentionedResources` per viewer
- [x] Frontend trusts backend, no client-side permission logic
- [x] Inaccessible mentions render as plain text (IDOR protection)
- [ ] Backend tests cover permission edge cases
- [ ] Frontend tests verify rendering behavior
- [ ] Anonymous user handling tested
- [ ] Public vs. private resource scenarios tested

---

## Agent/LLM Permission Model

### Overview

The Agent/LLM system implements a defense-in-depth permission model where agents inherit the calling user's permissions and can never escalate beyond them. This ensures that agents operate as proxies for users, not as privileged entities.

**Core Principle**: Agents execute with the **minimum** of the user's permissions, never exceeding what the user themselves could do directly.

### Architecture Layers

The permission system operates at three layers:

1. **WebSocket Consumer Layer** - Initial connection authorization
2. **Tool Filtering Layer** - Removes unauthorized tools before agent initialization
3. **Runtime Validation Layer** - Defense-in-depth checks before each tool execution

### 1. WebSocket Consumer Layer

**Location**: `config/websocket/consumers/unified_agent_conversation.py`

The `UnifiedAgentConsumer` validates user permissions **before** accepting the WebSocket connection:

```python
# In UnifiedAgentConsumer._validate_resource_permissions()
# (called from connect(); config/websocket/consumers/unified_agent_conversation.py)

# For corpus context
if self.corpus_id:
    self.corpus = await Corpus.objects.aget(id=self.corpus_id)
    if is_authenticated:
        has_perm = await database_sync_to_async(
            self.corpus.user_can
        )(user, PermissionTypes.READ)
        if not has_perm:
            await self.close(code=4003)
            return
    elif not self.corpus.is_public:
        await self.close(code=4003)
        return

# For document context
if self.document_id:
    self.document = await Document.objects.aget(id=self.document_id)
    if is_authenticated:
        has_perm = await database_sync_to_async(
            self.document.user_can
        )(user, PermissionTypes.READ)
        if not has_perm:
            await self.close(code=4003)
            return
    elif not self.document.is_public:
        await self.close(code=4003)
        return
```

**Key Rules:**
- **Authenticated users**: Must have READ permission on corpus/document
- **Anonymous users**: Only allowed if resource is `is_public=True`
- **Connection rejection**: Closes with code 4003 (Forbidden) if unauthorized
- **Early validation**: Prevents agent initialization for unauthorized users

### 2. Tool Filtering Layer

**Location**: `opencontractserver/llms/agents/agent_factory.py`

Before agent initialization, tools are filtered based on user permissions. This happens in `UnifiedAgentFactory.create_document_agent()` and `UnifiedAgentFactory.create_corpus_agent()`.

#### Tool Filtering Logic

```python
# In UnifiedAgentFactory.create_document_agent() (agent_factory.py) —
# create_corpus_agent() applies the same filters against the corpus.
# The flags themselves are declared on CoreTool in
# opencontractserver/llms/tools/tool_factory.py.

# Check user's write permission on document
has_write_permission = await _user_has_write_permission(user_id, doc_obj)

filtered_tools = []
for t in tools:
    # Filter approval-required tools in public contexts
    if public_context and isinstance(t, CoreTool) and t.requires_approval:
        logger.warning("Skipping approval-required tool '%s' for public context", t.name)
        continue

    # Filter corpus-dependent tools when no corpus provided
    if corpus is None and isinstance(t, CoreTool) and t.requires_corpus:
        logger.info("Skipping corpus-required tool '%s' - no corpus provided", t.name)
        continue

    # Filter write tools if user lacks write permission
    if (
        not has_write_permission
        and isinstance(t, CoreTool)
        and t.requires_write_permission
    ):
        logger.info(
            "Skipping write tool '%s' - user %s lacks WRITE permission on document %s",
            t.name, user_id, doc_obj.id
        )
        continue

    filtered_tools.append(t)
```

#### Tool Flags

Each `CoreTool` has three permission-related flags:

| Flag | Purpose | Filter Condition |
|------|---------|------------------|
| `requires_approval` | Tool needs user confirmation | Filtered if `public_context=True` |
| `requires_corpus` | Tool needs corpus context | Filtered if `corpus=None` |
| `requires_write_permission` | Tool performs write operations | Filtered if user lacks CRUD permission |

**Examples:**
- **Create Annotation Tool**: `requires_write_permission=True` - Only available to users with CREATE/UPDATE/DELETE on document
- **Vector Search Tool**: `requires_write_permission=False` - Available to all users with READ access
- **Corpus Summary Tool**: `requires_corpus=True` - Filtered out for standalone document agents

### 3. Runtime Validation Layer

**Location**: `opencontractserver/llms/tools/pydantic_ai_tools.py`

The async `_check_user_permissions()` function runs (awaited) **before every tool execution** as a defense-in-depth measure:

```python
# In pydantic_ai_tools.py

async def _check_user_permissions(ctx: RunContext[PydanticAIDependencies]) -> None:
    """
    Validate that the user in context has permission to access the resources.

    This is a defense-in-depth check that runs BEFORE any tool execution to
    ensure an agent cannot escalate beyond the calling user's permissions.
    Even if the consumer layer has a bug, tools won't leak data.
    """
    deps = ctx.deps
    user_id = deps.user_id
    document_id = deps.document_id
    corpus_id = deps.corpus_id

    if user_id is None:
        # Anonymous user - only allow if resources are public
        if document_id:
            doc = await Document.objects.aget(pk=document_id)
            if not doc.is_public:
                raise PermissionError("Anonymous access denied to private document")
        if corpus_id:
            corpus = await Corpus.objects.aget(pk=corpus_id)
            if not corpus.is_public:
                raise PermissionError("Anonymous access denied to private corpus")
        return

    # Authenticated user - uses visible_to_user() which properly handles
    # creator access, public status, and guardian permissions
    user = await User.objects.aget(pk=user_id)

    if document_id:
        has_perm = await database_sync_to_async(
            lambda: Document.objects.visible_to_user(user)
            .filter(pk=document_id).exists()
        )()
        if not has_perm:
            raise PermissionError(f"User {user_id} lacks READ permission on document")

    if corpus_id:
        has_perm = await database_sync_to_async(
            lambda: Corpus.objects.visible_to_user(user)
            .filter(pk=corpus_id).exists()
        )()
        if not has_perm:
            raise PermissionError(f"User {user_id} lacks READ permission on corpus")
```

**Injection Point**: The check is awaited inside the single `async_wrapper` that wraps every tool in `pydantic_ai_tools.py`:

```python
async def async_wrapper(ctx: RunContext[PydanticAIDependencies], *args, **kwargs):
    # Defense-in-depth: validate user permissions BEFORE any tool execution
    await _check_user_permissions(ctx)

    # Then execute tool...
    return await original_func(*args, **kwargs)
```

**Tool fault tolerance (issue #820)**: the same wrapper splits exception
handling by class — **security exceptions propagate, operational errors do
not**:

```python
except (PermissionError, ToolConfirmationRequired):
    raise  # security exceptions propagate to the framework
except Exception as e:
    # operational failures are returned to the LLM as an error string
    return f"[Tool error] {func_name} failed: {e}. ..."
```

#### Writing permission checks inside a tool

Tool authors who need a check *beyond* the wrapper's READ gate (e.g. a write tool confirming the caller may UPDATE a specific object) MUST use the `user_can` API:

```python
# Inside an agent tool — confirm the caller may edit this object.
if not obj.user_can(user, PermissionTypes.UPDATE):
    raise PermissionError("User lacks UPDATE permission")
```

Notes:
- `obj.user_can(user, perm)` honours creator status uniformly (Phase A): a creator who never received an explicit guardian grant still passes, matching the read-side `visible_to_user` filter. Migrated tool sites (`image_tools.py`, `extracts_and_analyzers.py`, `memory.py`, `caml_article.py`) rely on this — do not re-add bare `creator_id == user.pk` OR-branches.
- `user_can` defaults to `include_group_permissions=True`; users holding a permission via a group pass the gate.
- Agent tools run without a GraphQL request in scope, so omit the `request=` kwarg — they degrade gracefully to Tier-1 instance caching (see [the two-tier cache](#two-tier-permission-cache)).
- All production agent tools are async; call `database_sync_to_async(obj.user_can)(user, perm)` from async tool bodies.

### 4. Vector Search Permission Layer

**Locations**:
- GraphQL: `resolve_semantic_search` in `config/graphql/search_queries.py`
- Vector Store: `opencontractserver/llms/vector_stores/core_vector_stores.py`

The vector search system implements its own permission layer to ensure users can only search annotations they have access to.

#### GraphQL `semantic_search` Query

The `semantic_search` query validates document/corpus access before creating the vector store:

```python
# Defense-in-depth check at GraphQL layer (config/graphql/search_queries.py).
# Inline visible_to_user is forbidden in config/graphql/ (E001) — the
# resolver goes through BaseService:
if document_pk:
    if not BaseService.filter_visible(Document, user, request=info.context).filter(id=document_pk).exists():
        return []  # IDOR-safe: same response for not found vs. no permission

if corpus_pk:
    if not BaseService.filter_visible(Corpus, user, request=info.context).filter(id=corpus_pk).exists():
        return []  # IDOR-safe: same response for not found vs. no permission
```

#### CoreAnnotationVectorStore Permission Check

The `CoreAnnotationVectorStore` class performs its own permission verification in `_build_base_queryset()`:

```python
# From core_vector_stores.py:_build_base_queryset()

# Verify user has access to document
if self.document_id is not None:
    has_access = Document.objects.visible_to_user(user).filter(id=self.document_id).exists()
    if not has_access:
        return Annotation.objects.none()  # IDOR-safe

# Verify user has access to corpus
if self.corpus_id is not None:
    has_access = Corpus.objects.visible_to_user(user).filter(id=self.corpus_id).exists()
    if not has_access:
        return Annotation.objects.none()  # IDOR-safe
```

#### Global Search Method

The `global_search` class method uses the canonical `visible_to_user()` pattern:

```python
# Get all documents visible to user
accessible_doc_ids = Document.objects.visible_to_user(user).filter(is_current=True).values_list("id", flat=True)

# Filter annotations to accessible documents
queryset = Annotation.objects.filter(
    Q(document_id__in=accessible_doc_ids) |
    Q(structural=True, structural_set__documents__in=accessible_doc_ids)
)
```

#### Key Security Properties

| Property | Implementation |
|----------|----------------|
| **IDOR Protection** | Returns empty results for both non-existent and inaccessible resources |
| **Defense-in-depth** | Checks at GraphQL layer AND vector store layer |
| **Visibility Pattern** | Uses `visible_to_user()` for all permission checks |
| **Anonymous Support** | Anonymous users can search public documents/corpuses only |
| **Structural Annotations** | Visible if user can access the document (always READ-only) |

### Permission Inheritance Model

Agents inherit permissions from the **calling user**, not from the agent creator or any other privileged entity.

**Formula**: `Effective Tool Permission = MIN(caller_permission, tool_requirement)`

#### Example Scenarios

**Scenario 1: Read-Only User with Document Agent**

```python
# Setup
user = create_user("viewer")
document = create_document("Contract.pdf", is_public=False)
set_permissions_for_obj_to_user(user, document, [PermissionTypes.READ])

# Agent initialization
agent = await create_document_agent(document=document, user_id=user.id)

# Available tools:
# - vector_search (read-only) ✅
# - extract_entities (read-only) ✅
# - create_annotation (write) ❌ FILTERED OUT

# If somehow a write tool wasn't filtered, runtime check would block:
# _check_user_permissions() → PermissionError
```

**Scenario 2: Anonymous User with Public Corpus**

```python
# Setup
corpus = create_corpus("Public Legal Docs", is_public=True)

# Agent initialization
agent = await create_corpus_agent(corpus=corpus, user_id=None)  # Anonymous

# Available tools:
# - vector_search ✅
# - document_search ✅
# - create_annotation ❌ FILTERED OUT (anonymous = no write)
# - export_data ❌ FILTERED OUT (anonymous = no write)

# Runtime validation:
# _check_user_permissions() checks corpus.is_public → allows read tools
```

**Scenario 3: Owner with Full Permissions**

```python
# Setup
owner = create_user("owner")
document = create_document("Contract.pdf", creator=owner)
corpus = create_corpus("Legal Docs", creator=owner)

# Agent initialization (owner has CRUD by default)
agent = await create_document_agent(
    document=document,
    corpus=corpus,
    user_id=owner.id
)

# Available tools:
# - vector_search ✅
# - create_annotation ✅
# - update_annotation ✅
# - delete_annotation ✅
# - All tools available (owner has full permissions)
```

### Legacy Consumers (Deprecated)

The following WebSocket consumers have been **removed/deprecated** in favor of `UnifiedAgentConsumer`:

- ❌ `DocumentQueryConsumer` - Use `UnifiedAgentConsumer` with `document_id` param
- ❌ `CorpusQueryConsumer` - Use `UnifiedAgentConsumer` with `corpus_id` param
- ❌ `StandaloneDocumentQueryConsumer` - Use `UnifiedAgentConsumer` with `document_id` only

**Migration Example:**

```javascript
// OLD (deprecated)
const ws = new WebSocket(`/ws/corpus_query/${corpusId}/`);

// NEW (unified — route defined in config/asgi.py)
const ws = new WebSocket(`/ws/agent-chat/?corpus_id=${corpusId}`);
```

### Key Security Properties

1. **No Privilege Escalation**: Agents cannot access resources the user cannot access
2. **Defense in Depth**: Three layers of permission checks (consumer, factory, runtime)
3. **Fail-Safe**: Permission checks default to denial on errors
4. **Audit Trail**: All permission failures are logged with user/resource context
5. **Anonymous Safety**: Anonymous users limited to public resources, read-only tools

### Cross-Reference: Full LLM Architecture

For complete details on the LLM/Agent system architecture, see:
- **`docs/architecture/llms/README.md`** - Full LLM framework documentation
- **`docs/architecture/llms/agent_lifecycle.md`** - Agent lifecycle and conversation management
- **`docs/architecture/llms/tool_system.md`** - Tool registration and execution

### Testing

Comprehensive tests for the agent permission model are located in:
- `opencontractserver/tests/test_agent_factory.py` - Agent factory permission filtering
- `opencontractserver/tests/websocket/test_unified_agent_consumer.py` - WebSocket layer validation
- `opencontractserver/tests/websocket/test_agent_permission_escalation.py` - Escalation scenarios across the layers
- `opencontractserver/tests/test_pydantic_ai_tools_module.py` - Runtime permission checks + fault tolerance

Key test scenarios:
- Anonymous users can only access public resources
- Read-only users cannot execute write tools
- Write tools are filtered for users without CRUD permissions
- Runtime checks block tool execution even if filtering fails
- Permission changes take effect immediately (no caching)

---

## The `user_can` Authorization API

`Model.objects.user_can(user, obj, permission)` (manager surface) and `obj.user_can(user, permission)` (instance surface) are the canonical single-object authorization check. They are the read/check counterpart of the `Model.objects.visible_to_user(user)` queryset filter. Both live per model in `opencontractserver/shared/Managers.py`; the instance surface is provided by `InstanceUserCanMixin` (`opencontractserver/shared/user_can_mixin.py`), which delegates to `type(obj)._default_manager.user_can`.

**Filter/check parity is an invariant.** For READ, `user_can(u, obj, READ)` must equal `visible_to_user(u).filter(pk=obj.pk).exists()` for every user. This is pinned by the suite in `opencontractserver/tests/permissioning/test_authorization_invariants.py` — if a manager's `user_can` and its queryset's `visible_to_user` ever drift, that suite fails by design.

### Extending `user_can` when introducing a new visibility-managed model

When you add a new model whose rows must be permission-filtered, work through this checklist:

1. **Manager + queryset.** Give the model a manager inheriting `BaseVisibilityManager` (and a queryset inheriting `PermissionQuerySet`) so it gets `user_can` and `visible_to_user` for free with the default creator / `is_public` / guardian rules.
2. **Instance surface.** Make the model inherit `InstanceUserCanMixin` so callers can use `obj.user_can(...)`. The mixin raises a clear `TypeError` if the default manager has no `user_can` — so step 1 must be done first.
3. **Override in lockstep.** If the model has non-standard visibility (permission inheritance, privacy recursion, structural locking, type bifurcation), override **both** `Manager.user_can` and `QuerySet.visible_to_user`. Never change one without the other — the parity invariant will fail.
4. **Resolve the user uniformly.** Use `resolve_user_for_user_can(user)` at the top of a custom `user_can` so `int` / `str` ids, `None`, `AnonymousUser`, and invalid strings all resolve consistently (it returns `None` for anything unresolvable; deny on `None`).
5. **Honour creator status uniformly.** Per Phase A, a creator passes `user_can` without an explicit guardian grant, matching `visible_to_user`'s `Q(creator=user)` predicate. Do not gate creators behind guardian rows.
6. **Add an invariant test class.** In `test_authorization_invariants.py`, subclass `_UserCanInvariantsMixin` + `TransactionTestCase`, and in `setUp` populate `model_cls`, `_superuser`, `_matrix_users`, and `_matrix_instances`. The mixin's equivalence / surface-agreement / admin-data-parity tests then come for free (the `_superuser` is asserted to have NO blanket access — `test_superuser_has_no_blanket_data_access` — matching the scoped-admin contract).
7. **Cover the fixture matrix.** `_matrix_users` must include: superuser, creator, a non-creator with an explicit guardian grant, an unshared stranger, a public-only viewer (stranger × a public instance), and `AnonymousUser()`.
8. **Pin model-specific invariants.** Add a focused test for any special rule: structural locking, recursive privacy, `is_public` write asymmetry, or CHAT/THREAD-style bifurcation.

### Two-Tier Permission Cache

`user_can` permission resolution is memoized at two tiers (introduced in PR #1665). Both are transparent — they never change the answer, only avoid recomputation.

- **Tier 1 — per-instance memoization.** Always on. Results are cached on the in-memory model instance under `INSTANCE_PERMS_CACHE_ATTR`. The cache lives as long as the instance object does; two separate `Document` instances for the same row do not share it. This is what Celery tasks, agent tools, websocket consumers, and fixtures rely on.
- **Tier 2 — request-scoped optimizer.** Opt-in. Activated by threading a GraphQL request through the `request=` kwarg: `obj.user_can(user, perm, request=info.context)`. All `user_can` calls in that request then share one `PermissionQueryOptimizer` (`get_request_optimizer(request)`), so repeated checks across many rows / resolvers in a single GraphQL request collapse to far fewer queries.

**When to pass `request=`:**

- **GraphQL resolvers and mutations** — pass `request=info.context`. This is where Tier-2 pays off (list resolvers check permissions per row).
- **Celery tasks, agent tools, websocket consumers, import services, fixtures, tests** — omit `request=`. They have no GraphQL request in scope; they degrade gracefully to Tier-1 instance caching. Passing a non-request object is unsafe.

**Cache invalidation.** `set_permissions_for_obj_to_user(user, obj, perms, request=info.context)` invalidates both tiers for that `(user, obj)` pair after the grant lands, so later `user_can` checks in the same request see the new state. Group-permission changes (`user.groups.add(...)`, `assign_perm(perm, group, obj)`) do **not** flow through that helper — a caller mutating group membership mid-request must invalidate manually (`delattr(instance, INSTANCE_PERMS_CACHE_ATTR)` and/or `get_request_optimizer(request).invalidate(user_id=user.id)`).

### Service Layer: corpus services and `DocumentService`

Authorization checks answer "may this user do X to this object." *Fetching* the right objects for a user is the job of the service layer, and request-context code should go through it rather than composing `visible_to_user` filters by hand:

- **`DocumentService`** (`opencontractserver/documents/document_service.py`) — the single source of truth for document-level operations: creation, quota, lifecycle, document-level permissions, and standalone single-document lookup. Use it when the document is the noun and corpus context is incidental.
- **The `opencontractserver/corpuses/services/` package** — the single source of truth for corpus-scoped operations: "give me X inside corpus Y for user Z" (issue #1716 split the former `CorpusObjsService` monolith into segmented services). Import the specific service from `opencontractserver.corpuses.services`: `CorpusDocumentService` (document-in-corpus reads/writes + membership: `get_corpus_documents`, `get_corpus_documents_visible_to_user`, `get_corpus_document_by_slug`, `get_corpus_document_by_id`, `is_document_in_corpus`, CAML articles), `FolderCRUDService` (folder CRUD, tree, search), `FolderDocumentService` (document-in-folder placement), `DocumentLifecycleService` (soft-delete/restore/trash), `CorpusPathService` (`DocumentPath` disambiguation internals), and `CorpusService` (Corpus-row CRUD: delete, visibility, description versioning).

#### Corpus document access — two deliberate semantics (issue #1682)

`CorpusDocumentService` exposes **two list methods with intentionally
different security semantics**. Choose by caller intent; never silently swap
one for the other:

- **`get_corpus_documents(user, corpus)` — corpus-as-gate.** Corpus READ
  unlocks *every* document with an active path in that corpus, including
  private documents the user holds no document-level grant on. This is the
  documented default for **pipeline-facing** callers that legitimately
  operate over a whole readable corpus: MCP tools, discovery, badge/analysis
  tasks, and the single-document helpers built on it
  (`get_corpus_document_by_slug` / `get_corpus_document_by_id` /
  `is_document_in_corpus`).
- **`get_corpus_documents_visible_to_user(user, corpus)` — MIN(document,
  corpus).** Enforces `MIN(document_permission, corpus_permission)`: a
  private document inside a public (or merely shared) corpus stays hidden
  from users who lack document-level READ. **User-facing surfaces that must
  not leak private documents — e.g. the GraphQL `CorpusType.documents`
  resolver — MUST use this variant.**

**IDOR safety:** never fuse `corpus.get_documents().values_list("id", flat=True)` with `Document.objects.visible_to_user(user)` by hand — that copy-paste pattern is IDOR-prone. `CorpusDocumentService` is the canonical entry point and returns an empty queryset (not a leak, not an error) on permission denial. `corpus.get_documents()` itself now emits a `DeprecationWarning`; internal/task code without a user must call `corpus._get_active_documents()` explicitly.

---

## resolve_oc_model_queryset Deprecation

> The old `resolve_oc_model_queryset` function was duplicative and not uniformly implemented. Applicable logic was moved to custom base manager with a visible_to_user(user) function.
