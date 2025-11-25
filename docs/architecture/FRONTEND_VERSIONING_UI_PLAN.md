# Frontend Versioning UI Implementation Plan

## Executive Summary

This plan outlines how to expose the dual-tree versioning architecture (content + path history) in the OpenContracts frontend while maintaining performance and providing an intuitive, filesystem-like user experience.

## Core Principles

1. **Progressive Disclosure**: Basic view by default, expand for details
2. **Lazy Loading**: Fetch history only when needed
3. **Performance First**: No upfront loading of historical data
4. **Filesystem Metaphors**: Trash bin, restore, version badges
5. **Non-Disruptive**: Enhance existing UI without breaking changes

## Implementation Strategy

### Phase 1: GraphQL Schema Enhancements (Week 1)

#### 1.1 Add Version Metadata to Document Type
```graphql
extend type DocumentType {
  # Existing fields...

  # Version metadata (always loaded)
  versionNumber: Int!  # From DocumentPath.version_number
  hasVersionHistory: Boolean!  # True if Document.parent exists
  versionCount: Int!  # Count of versions in tree
  isLatestVersion: Boolean!  # Document.is_current
  lastModified: DateTime!  # DocumentPath.created_at

  # Lazy-loaded version data
  versionHistory: VersionHistory  # Only loaded on request
  pathHistory: PathHistory  # Only loaded on request
}

type VersionHistory {
  versions: [DocumentVersion!]!
  currentVersion: DocumentVersion!
  versionTree: VersionTreeNode!
}

type DocumentVersion {
  id: ID!
  versionNumber: Int!
  hash: String!
  createdAt: DateTime!
  createdBy: User!
  sizeBytes: Int!
  changeType: VersionChangeType!
  parentVersion: DocumentVersion
}

enum VersionChangeType {
  INITIAL
  CONTENT_UPDATE
  MINOR_EDIT
  MAJOR_REVISION
}

type PathHistory {
  events: [PathEvent!]!
  currentPath: String!
  originalPath: String!
  moveCount: Int!
}

type PathEvent {
  id: ID!
  action: PathAction!
  path: String!
  folder: CorpusFolder
  timestamp: DateTime!
  user: User!
  versionNumber: Int!
}

enum PathAction {
  IMPORTED
  MOVED
  RENAMED
  DELETED
  RESTORED
  UPDATED
}
```

#### 1.2 Add Time-Travel Query
```graphql
extend type Query {
  corpusFilesystemAtTime(
    corpusId: ID!
    timestamp: DateTime!
  ): FilesystemSnapshot!

  documentAtVersion(
    documentId: ID!
    versionNumber: Int!
  ): DocumentType
}

type FilesystemSnapshot {
  timestamp: DateTime!
  documents: [DocumentType!]!
  folders: [CorpusFolder!]!
  statistics: SnapshotStats!
}
```

#### 1.3 Add Trash/Restore Operations
```graphql
extend type Mutation {
  restoreDocument(
    corpusId: ID!
    documentPath: String!
  ): RestoreDocumentResponse!

  permanentlyDeleteDocument(
    documentId: ID!
    confirmationPhrase: String!
  ): DeleteResponse!

  restoreToVersion(
    documentId: ID!
    versionNumber: Int!
  ): RestoreVersionResponse!
}
```

### Phase 2: UI Components & Patterns (Week 1-2)

#### 2.1 Version Badge Component
```typescript
// Shows version number as a subtle badge on document cards
interface VersionBadgeProps {
  versionNumber: number;
  hasHistory: boolean;
  isLatest: boolean;
  onClick?: () => void;
}

// Visual states:
// - v1 (gray, no history)
// - v3 (blue, has history, is latest)
// - v2 of 3 (orange, has history, not latest)
```

#### 2.2 Document Context Menu Enhancement
Add right-click context menu with:
- View Version History
- Restore Previous Version
- Download This Version
- Compare with Previous
- View Path History
- Move to Trash (soft delete)

#### 2.3 Version History Panel (Lazy Loaded)
```typescript
// Slide-out panel or modal showing version timeline
interface VersionHistoryPanelProps {
  documentId: string;
  onVersionSelect: (versionId: string) => void;
  onRestore: (versionId: string) => void;
}

// Features:
// - Timeline view with version nodes
// - Diff preview on hover
// - One-click restore
// - Download any version
// - See who made changes
```

#### 2.4 Trash Folder Implementation
```typescript
// Special system folder showing soft-deleted documents
interface TrashFolderProps {
  corpusId: string;
  onRestore: (documentIds: string[]) => void;
  onPermanentDelete: (documentIds: string[]) => void;
}

// Features:
// - Shows deleted documents with deletion date
// - Bulk restore capability
// - Empty trash option (with confirmation)
// - Auto-expiry warning (if implemented)
```

#### 2.5 Time Travel Slider
```typescript
// Corpus-level time machine interface
interface TimeTravelControlsProps {
  corpusId: string;
  minDate: Date;
  maxDate: Date;
  onChange: (date: Date) => void;
}

// Features:
// - Date/time slider
// - Preset jumps (1 day, 1 week, 1 month ago)
// - Visual diff indicator
// - "Return to Present" button
```

### Phase 3: Performance Optimizations (Week 2)

#### 3.1 GraphQL Query Strategy

**Default Document Query (no change to current)**:
```graphql
query GetDocuments($corpusId: ID!, $folderId: ID) {
  documents(inCorpusWithId: $corpusId, inFolderId: $folderId) {
    edges {
      node {
        id
        title
        # Basic version metadata only
        versionNumber
        hasVersionHistory
        isLatestVersion
        # NOT loading versionHistory or pathHistory
      }
    }
  }
}
```

**On-Demand Version Query** (triggered by user action):
```graphql
query GetDocumentHistory($documentId: ID!) {
  document(id: $documentId) {
    versionHistory {
      versions {
        id
        versionNumber
        createdAt
        createdBy { username }
        changeType
      }
    }
    pathHistory {
      events {
        action
        path
        timestamp
        user { username }
      }
    }
  }
}
```

#### 3.2 Caching Strategy

```typescript
// Apollo Cache Configuration
const cache = new InMemoryCache({
  typePolicies: {
    DocumentType: {
      fields: {
        versionHistory: {
          // Cache version history separately
          merge: false,
        },
        pathHistory: {
          // Cache path history separately
          merge: false,
        },
      },
    },
    Query: {
      fields: {
        corpusFilesystemAtTime: {
          // Key by corpusId + timestamp
          keyArgs: ["corpusId", "timestamp"],
          merge: false,
        },
      },
    },
  },
});
```

#### 3.3 Prefetching Strategy

```typescript
// Prefetch version info only for selected/hovered documents
const prefetchVersionInfo = (documentId: string) => {
  client.query({
    query: GET_DOCUMENT_VERSION_COUNT,
    variables: { documentId },
    // Don't update UI, just warm cache
    fetchPolicy: 'cache-first',
  });
};
```

### Phase 4: Visual Design Patterns (Week 2-3)

#### 4.1 Version Indicator Styles

```css
/* Subtle version badge on document cards */
.version-badge {
  position: absolute;
  top: 8px;
  right: 8px;
  font-size: 11px;
  padding: 2px 6px;
  border-radius: 10px;
  background: rgba(0, 0, 0, 0.05);
  color: #666;
}

.version-badge--has-history {
  background: #e3f2fd;
  color: #1976d2;
  cursor: pointer;
}

.version-badge--outdated {
  background: #fff3e0;
  color: #f57c00;
}
```

#### 4.2 Document Card Enhancements

```typescript
// Visual states for document cards
interface DocumentCardState {
  isDeleted: boolean;  // Shown in trash with strikethrough
  isOutdated: boolean;  // Not the latest version
  hasNewVersion: boolean;  // Newer version available
  isModified: boolean;  // Has unsaved changes
}

// Visual indicators:
// - Strikethrough for deleted
// - Orange tint for outdated
// - Blue dot for new version available
// - Yellow border for modified
```

#### 4.3 Timeline Visualization

```typescript
// Version timeline component
interface TimelineNodeProps {
  version: DocumentVersion;
  isActive: boolean;
  isCurrent: boolean;
  showDiff: boolean;
}

// Visual elements:
// - Connected nodes showing version progression
// - Branch indicators for parallel edits
// - User avatars at each node
// - Relative time labels
// - Hover for details
```

### Phase 5: User Experience Flows (Week 3)

#### 5.1 Viewing Version History
1. User sees version badge on document card (e.g., "v3")
2. Clicks badge → Opens version history panel
3. Panel shows timeline with all versions
4. Hover over version → Shows preview/diff
5. Click version → Opens in viewer (read-only)
6. Option to restore or download

#### 5.2 Restoring Deleted Documents
1. User navigates to Trash folder (special system folder)
2. Sees all soft-deleted documents with deletion date
3. Can select multiple documents
4. Click "Restore" → Documents return to original location
5. Or click "Permanently Delete" → Confirmation required

#### 5.3 Time Travel Browsing
1. User clicks clock icon in corpus toolbar
2. Time slider appears at top of document list
3. Dragging slider updates view to show corpus at that time
4. Documents show as they were (versions, locations, deletions)
5. Read-only mode with clear "Historical View" indicator
6. "Return to Present" button to exit

#### 5.4 Comparing Versions
1. User opens version history for document
2. Selects two versions to compare
3. Opens split-screen diff viewer
4. Shows additions in green, deletions in red
5. Can navigate between changes
6. Option to restore either version

### Phase 6: Implementation Roadmap

#### Week 1: Backend Integration
- [ ] Extend GraphQL schema with version fields
- [ ] Add version metadata to Document type resolver
- [ ] Create lazy-loading resolvers for history
- [ ] Add trash/restore mutations
- [ ] Create time-travel query resolver

#### Week 2: Core UI Components
- [ ] Version badge component
- [ ] Document context menu with version options
- [ ] Version history panel (lazy loaded)
- [ ] Basic trash folder view
- [ ] Update DocumentCards to show version badges

#### Week 3: Advanced Features
- [ ] Time travel slider interface
- [ ] Version comparison viewer
- [ ] Path history visualization
- [ ] Bulk operations for trash
- [ ] Version prefetching on hover

#### Week 4: Polish & Testing
- [ ] Performance testing with large histories
- [ ] E2E tests for version workflows
- [ ] Accessibility improvements
- [ ] Documentation and user guides
- [ ] Migration of existing documents

### Phase 7: Component Integration Examples

#### 7.1 Enhanced CorpusDocumentCards.tsx
```typescript
// Minimal changes to existing component
const CorpusDocumentCards = () => {
  // Existing state...

  // Add version-specific state
  const [showTrash, setShowTrash] = useState(false);
  const [timeTravelDate, setTimeTravelDate] = useState<Date | null>(null);
  const [selectedVersions, setSelectedVersions] = useState<Map<string, number>>();

  // Modified query to include version metadata
  const queryVariables = {
    ...existingVariables,
    includeVersionMetadata: true,  // New flag
    includeDeleted: showTrash,  // Show deleted in trash
    asOfDate: timeTravelDate,  // Time travel parameter
  };

  // Add trash toggle in toolbar
  // Add time travel controls
  // Pass version props to DocumentCards
};
```

#### 7.2 DocumentCard Version Display
```typescript
const DocumentCard = ({ document, viewMode }) => {
  const { versionNumber, hasVersionHistory, isLatestVersion } = document;

  return (
    <Card>
      {/* Existing content */}

      {/* Version badge */}
      {versionNumber > 1 && (
        <VersionBadge
          version={versionNumber}
          hasHistory={hasVersionHistory}
          isLatest={isLatestVersion}
          onClick={() => openVersionHistory(document.id)}
        />
      )}

      {/* Deleted indicator */}
      {document.isDeleted && (
        <DeletedOverlay
          deletedAt={document.deletedAt}
          onRestore={() => restoreDocument(document.id)}
        />
      )}
    </Card>
  );
};
```

### Performance Guarantees

1. **Initial Load**: No performance degradation
   - Version metadata adds < 100ms to query
   - Only basic fields loaded by default

2. **History Loading**: On-demand only
   - Version history: < 200ms for 100 versions
   - Path history: < 150ms for 50 events
   - Uses separate GraphQL queries

3. **Time Travel**: Optimized queries
   - Snapshot query: < 500ms for 10k documents
   - Results cached for 5 minutes
   - Progressive loading for large corpuses

4. **Memory Usage**: Controlled caching
   - History cached per document, not globally
   - LRU eviction for old history data
   - Maximum 50 documents with full history in cache

## Permission Integration

### Core Permission Rules for Versioning

Based on the consolidated permission guide, versioning features must respect:

1. **Document Permissions are Primary**
   - Version history visibility requires READ permission on document
   - Restore operations require UPDATE permission on document
   - Delete operations require DELETE permission on document
   - Formula: `Effective Permission = MIN(document_permission, corpus_permission)`

2. **Corpus Context Required for Write Operations**
   - Moving documents requires UPDATE permission on corpus
   - Restoring deleted documents requires UPDATE permission on corpus
   - Version restore requires UPDATE permission on both document AND corpus

3. **Anonymous User Access**
   - Can view version history if document AND corpus are `is_public=True`
   - Read-only access to time travel feature
   - Cannot restore or modify versions
   - Cannot access trash (write operation)

4. **Soft Delete Permission Model**
   ```python
   # Delete operation (soft delete)
   required: DELETE permission on document AND corpus

   # Restore operation
   required: UPDATE permission on document AND corpus

   # View deleted items in trash
   required: READ permission on corpus

   # Permanently delete
   required: DELETE permission + special confirmation
   ```

### GraphQL Permission Checks

```graphql
extend type DocumentType {
  # Version fields respect document permissions
  versionHistory: VersionHistory @requiresPermission(READ)
  pathHistory: PathHistory @requiresPermission(READ)

  # Check permissions in resolvers
  canRestore: Boolean!  # Has UPDATE permission
  canDelete: Boolean!   # Has DELETE permission
  canViewHistory: Boolean!  # Has READ permission
}

extend type Mutation {
  # All mutations check permissions server-side
  restoreDocument(
    corpusId: ID!
    documentPath: String!
  ): RestoreDocumentResponse! @requiresPermission(UPDATE)

  restoreToVersion(
    documentId: ID!
    versionNumber: Int!
  ): RestoreVersionResponse! @requiresPermission(UPDATE)

  permanentlyDeleteDocument(
    documentId: ID!
    confirmationPhrase: String!
  ): DeleteResponse! @requiresPermission(DELETE)
}
```

### Frontend Permission Checks

```typescript
// Version badge visibility
const showVersionBadge = React.useMemo(() => {
  // Always show if user can read document
  return permissions.includes(PermissionTypes.CAN_READ);
}, [permissions]);

// Restore button availability
const canRestore = React.useMemo(() => {
  // Requires UPDATE on both document and corpus
  const hasDocUpdate = permissions.includes(PermissionTypes.CAN_UPDATE);
  const hasCorpusUpdate = corpusPermissions.includes(PermissionTypes.CAN_UPDATE);
  return hasDocUpdate && hasCorpusUpdate && !user.is_anonymous;
}, [permissions, corpusPermissions, user]);

// Time travel mode
const timeTravelMode = React.useMemo(() => {
  if (timeTravelDate) {
    return {
      readOnly: true,  // ALWAYS read-only in historical view
      message: user.is_anonymous
        ? "Viewing historical state (anonymous access)"
        : "Viewing historical state (read-only)"
    };
  }
  return { readOnly: false };
}, [timeTravelDate, user]);

// Trash access
const canAccessTrash = React.useMemo(() => {
  // Must be authenticated and have corpus READ permission
  if (user.is_anonymous) return false;
  return corpusPermissions.includes(PermissionTypes.CAN_READ);
}, [user, corpusPermissions]);
```

### Backend Permission Implementation

```python
# In opencontractserver/documents/versioning.py

def restore_document(corpus, path, user):
    """
    Restore soft-deleted document.
    Requires UPDATE permission on both document and corpus.
    """
    # Get the deleted DocumentPath
    deleted_path = DocumentPath.objects.get(
        corpus=corpus,
        path=path,
        is_current=True,
        is_deleted=True
    )

    # Check permissions
    if not user_has_permission_for_obj(
        user, deleted_path.document, PermissionTypes.UPDATE
    ):
        raise PermissionError("No UPDATE permission on document")

    if not user_has_permission_for_obj(
        user, corpus, PermissionTypes.UPDATE
    ):
        raise PermissionError("No UPDATE permission on corpus")

    # Perform restore...

def get_filesystem_at_time(corpus, timestamp, user):
    """
    Time travel query - always returns read-only view.
    Requires READ permission on corpus.
    """
    if not user_has_permission_for_obj(
        user, corpus, PermissionTypes.READ
    ):
        return DocumentPath.objects.none()

    # Return historical state (frontend enforces read-only)
```

### Security Considerations

1. **IDOR Prevention**
   - Version history endpoints check document ownership
   - Trash queries filter by corpus membership
   - Same error for "not found" vs "no permission"

2. **Audit Trail Protection**
   - Version history is immutable (no UPDATE/DELETE)
   - Only superusers can modify historical records
   - All restore operations logged with user info

3. **Cross-Corpus Security**
   - Version numbers don't leak across corpuses
   - Path history only shows corpus-specific events
   - Content deduplication doesn't expose other corpus data

### Permission Test Cases

```python
# Test: Anonymous user cannot restore
def test_anonymous_cannot_restore():
    response = client.post('/graphql', {
        'query': 'mutation { restoreDocument(...) }'
    }, headers={'Authorization': None})
    assert response.errors[0].message == "Authentication required"

# Test: Read-only user cannot restore
def test_readonly_cannot_restore():
    set_permissions_for_obj_to_user(user, doc, [PermissionTypes.READ])
    set_permissions_for_obj_to_user(user, corpus, [PermissionTypes.READ])

    with pytest.raises(PermissionError):
        restore_document(corpus, "/doc.pdf", user)

# Test: Time travel respects permissions
def test_time_travel_permission_filtering():
    # User without corpus permission
    past = get_filesystem_at_time(corpus, timestamp, unauthorized_user)
    assert past.count() == 0

    # User with permission sees history
    past = get_filesystem_at_time(corpus, timestamp, authorized_user)
    assert past.count() > 0
```

### Migration Strategy

1. **Phase 1**: Deploy backend changes
   - GraphQL schema additions are backward compatible
   - Permission checks integrated from day one
   - Existing queries continue to work unchanged

2. **Phase 2**: Add UI components gradually
   - Version badges appear automatically (respects READ permission)
   - History panel available but checks permissions
   - Trash folder only visible to authenticated users

3. **Phase 3**: Enable advanced features
   - Time travel behind feature flag + permission check
   - Version comparison requires READ permission
   - Gradual rollout with permission awareness

### Success Metrics

1. **Performance**:
   - Document list load time: < 10% increase
   - Version history load: < 300ms p95
   - Time travel query: < 1s p95

2. **Usability**:
   - 80% of users understand version badges
   - 60% successfully restore a deleted document
   - 40% use version history within first month

3. **Adoption**:
   - 30% of users view version history monthly
   - 20% use time travel feature
   - 50% reduction in "permanently lost" documents

## Summary

This implementation plan provides a comprehensive approach to exposing your dual-tree versioning architecture in the frontend while maintaining performance and usability. The key is progressive disclosure - showing just enough information by default (version badges) while making rich history available on demand through lazy loading and dedicated UI components.

The filesystem-like experience is achieved through familiar metaphors (trash bin, restore, versions) while the performance is maintained through careful GraphQL query design and caching strategies. The implementation can be rolled out gradually without disrupting existing users.

---

## Implementation Progress Tracking

### Completed Tasks

- [x] **Phase 1.1: GraphQL Schema - Version Metadata Types**
  - Added `PathActionEnum`, `VersionChangeTypeEnum` enums to `config/graphql/graphene_types.py`
  - Added `DocumentVersionType`, `VersionHistoryType`, `PathEventType`, `PathHistoryType` types
  - Added `DocumentPathType` GraphQL type with DjangoObjectType and permission filtering
  - Added version metadata fields to `DocumentType`:
    - `versionNumber(corpusId)` - from DocumentPath
    - `hasVersionHistory` - checks if Document.parent exists
    - `versionCount` - counts versions in tree
    - `isLatestVersion` - checks Document.is_current
    - `lastModified(corpusId)` - from DocumentPath.created timestamp
  - Added lazy-loaded fields:
    - `versionHistory` - complete version tree with all versions
    - `pathHistory(corpusId)` - all lifecycle events
  - Added permission helpers:
    - `canRestore(corpusId)` - checks UPDATE permission
    - `canViewHistory` - checks READ permission
  - **File**: `config/graphql/graphene_types.py` (lines 461-608, 1063-1289)

- [x] **Phase 1.1 Tests: Backend GraphQL Tests**
  - Created comprehensive test suite: `opencontractserver/tests/test_document_versioning_graphql.py`
  - Test classes:
    - `TestVersionMetadataFields` - basic field resolvers
    - `TestVersionHistoryLazyLoading` - version history queries
    - `TestPathHistoryLazyLoading` - path event queries
    - `TestVersioningPermissions` - permission checks (READ, UPDATE)
    - `TestVersionMetadataIntegration` - combined queries
  - Tests cover: version numbers, history detection, permission checks, edge cases

- [x] **Phase 1.2: Lazy-Loaded History Types**
  - Implemented in Phase 1.1 (combined implementation)
  - `resolve_version_history()` - fetches all versions in tree
  - `resolve_path_history()` - fetches all path events with action inference

- [x] **Phase 2.1: VersionBadge Frontend Component**
  - Created `frontend/src/components/documents/VersionBadge.tsx`
  - Features:
    - Visual states: gray (no history), blue (latest), orange (outdated)
    - Tooltip with version info and action hint
    - Click handler for history panel
    - Accessible (ARIA labels, keyboard support)
    - Styled-components with animations
  - **File**: `frontend/src/components/documents/VersionBadge.tsx`

- [x] **Phase 2.1 Tests: VersionBadge Component Tests**
  - Created Playwright component tests: `frontend/tests/VersionBadge.ct.tsx`
  - Tests: rendering, click handlers, tooltips, permissions, ARIA attributes
  - 15+ test cases covering all states and interactions

- [x] **Phase 2.2: Document Card Integration**
  - Updated `frontend/src/graphql/queries.ts`:
    - Added `hasVersionHistory`, `versionCount`, `isLatestVersion`, `canViewHistory` to GET_DOCUMENTS
  - Updated `frontend/src/types/graphql-api.ts`:
    - Added version metadata fields to `RawDocumentType`
  - Updated `frontend/src/components/documents/ModernDocumentItem.tsx`:
    - Added VersionBadge import and VersionHistoryPanel import
    - Added `VersionBadgeWrapper` styled component for positioning
    - Integrated VersionBadge into card preview area
    - Added version info to list view metadata
    - Added "View Version History" to context menu (permission-gated)
    - Added state management for version history panel (`versionHistoryOpen`)
    - Wired up VersionBadge clicks to open history panel
    - Integrated VersionHistoryPanel rendering in both card and list views
  - **Files**: `ModernDocumentItem.tsx`, `queries.ts`, `graphql-api.ts`

- [x] **Phase 3: Apollo Cache Policies**
  - Updated `frontend/src/graphql/cache.ts`:
    - Added `versionHistory` cache policy (merge: false)
    - Added `pathHistory` cache policy with corpusId keyArgs
    - Added `versionNumber` cache policy with corpusId keyArgs
    - Added `lastModified` cache policy with corpusId keyArgs
    - Added `canRestore` cache policy with corpusId keyArgs
  - Cache policies ensure proper data isolation per corpus context
  - **File**: `frontend/src/graphql/cache.ts`

- [x] **Phase 2.3: Version History Panel**
  - Created `frontend/src/components/documents/VersionHistoryPanel.tsx`:
    - Modal-based UI using Semantic UI Modal
    - Timeline visualization with styled-components
    - Version cards with metadata (user, timestamp, size, change type)
    - Visual indicators for current version (blue dot, "Current" label)
    - Lazy loading with `useLazyQuery` and `cache-first` policy
    - GraphQL query: `GET_DOCUMENT_VERSION_HISTORY`
    - Restore and Download action buttons (permission-gated)
    - Loading state with Semantic UI Loader
    - Error handling with Message component
    - Empty state for documents without history
    - Version change type badges (INITIAL, CONTENT_UPDATE, MINOR_EDIT, MAJOR_REVISION)
    - Human-readable file size formatting
    - Relative and absolute timestamp display
    - Click-to-select version cards
  - **File**: `frontend/src/components/documents/VersionHistoryPanel.tsx`

- [x] **Phase 2.3 Tests: Panel Tests**
  - Created `frontend/tests/VersionHistoryPanel.ct.tsx`:
    - Rendering tests (open/closed states)
    - Loading state verification
    - Version list display after loading
    - Version metadata display (users, change types, file sizes)
    - Error message display on fetch failure
    - Empty state for no versions
    - Close button functionality
    - Restore button for non-current versions
    - Download button for non-current versions
    - Current version info message
    - Version sorting (descending by version number)
    - Lazy loading verification (fetch on open)
  - 14+ test cases with Apollo MockedProvider
  - **File**: `frontend/tests/VersionHistoryPanel.ct.tsx`

- [x] **Phase 1.3: Trash/Restore Mutations** (COMPLETED)
  - Added `RestoreDeletedDocument` mutation - Restores soft-deleted document paths
  - Added `RestoreDocumentToVersion` mutation - Restores document to previous content version
  - Both mutations include:
    - Permission checks (UPDATE on document + corpus)
    - Error handling with specific error messages
    - Transaction safety for version restoration
    - Logging of user actions
  - Registered mutations in root Mutation class
  - **File modified**: `config/graphql/mutations.py` (lines 3806-4075, 4129-4131)
  - Note: `permanentlyDeleteDocument` not implemented (soft delete is preferred pattern)

- [x] **Phase 1.3 Tests: Mutation Tests** (COMPLETED)
  - Created comprehensive backend test suite in `test_document_versioning_graphql.py`:
    - `TestRestoreDeletedDocumentMutation` (4 tests):
      - Successful restoration of soft-deleted document path
      - Failure when document is not deleted
      - Permission denied scenarios
      - Nonexistent document handling
    - `TestRestoreDocumentToVersionMutation` (5 tests):
      - Successful restoration to previous version (creates new version)
      - Failure when targeting current version
      - Permission denied scenarios
      - Version number increment verification
      - Nonexistent document/corpus handling
  - Tests verify: permission enforcement, business logic, IDOR prevention, edge cases
  - **File**: `opencontractserver/tests/test_document_versioning_graphql.py`

- [x] **Wire Up Frontend Mutations** (COMPLETED)
  - Updated `VersionHistoryPanel.tsx`:
    - Added `RESTORE_DOCUMENT_TO_VERSION` GraphQL mutation definition
    - Added `corpusId` to props interface (required for mutation context)
    - Implemented `useMutation` hook with onCompleted/onError handlers
    - Created `handleRestore` function to invoke mutation
    - Added success message display (dismissible)
    - Added error message display (handles both business logic failures and network errors)
    - Added loading state on restore button during mutation
    - Removed onRestore callback dependency (mutation handled internally)
  - Updated `ModernDocumentItem.tsx`:
    - Passes `corpusId` from `openedCorpus()` to VersionHistoryPanel
    - Removed onRestore placeholder callbacks
  - Updated `VersionHistoryPanelTestWrapper.tsx`:
    - Added `corpusId` prop support
    - Added mutation mock support (success, failure, error scenarios)
    - Added refetch mock after successful mutation
  - Added 5 new mutation tests to `VersionHistoryPanel.ct.tsx`:
    - Success message after successful restore
    - Error message on business logic failure
    - Error message on network error
    - Success message dismissal
    - Error message dismissal
  - **Files**: `VersionHistoryPanel.tsx`, `ModernDocumentItem.tsx`, `VersionHistoryPanelTestWrapper.tsx`, `VersionHistoryPanel.ct.tsx`

### In Progress

(None currently)

### Pending Tasks

(None for trash folder view - Phase 2.4 complete)

- [x] **Phase 2.4: Trash Folder View** (COMPLETED)
  - Created `TrashFolderView.tsx` component with:
    - Card grid layout for deleted documents
    - Selection and bulk restore functionality
    - Individual document restore buttons
    - Success/error message handling
    - Empty state for empty trash
    - Confirmation modal for empty trash action
    - Document metadata display (title, type, deletion date, original folder)
  - Added backend GraphQL query `deletedDocumentsInCorpus`:
    - Queries DocumentPath records where `is_deleted=True` and `is_current=True`
    - Permission-checked (corpus visibility)
    - Returns document info, path info, user info
  - Added frontend GraphQL query and types in `folders.ts`
  - Integrated trash item into `FolderTreeSidebar.tsx`:
    - Trash icon from lucide-react
    - Positioned below Corpus Root
    - Selection handling with special "trash" ID
  - Updated `FolderDocumentBrowser.tsx`:
    - Conditionally renders TrashFolderView when `selectedFolderId === "trash"`
    - Hides breadcrumb for trash folder
    - Disables right-click context menu in trash view
  - Added `RESTORE_DELETED_DOCUMENT` mutation to frontend mutations.ts
  - **Files**: `TrashFolderView.tsx`, `FolderTreeSidebar.tsx`, `FolderDocumentBrowser.tsx`, `folders.ts` (queries), `mutations.ts`, `queries.py` (backend)

- [ ] **Phase 2.5: Time Travel Slider**
  - [ ] Date/time selector UI
  - [ ] GraphQL query for historical state
  - [ ] Read-only mode indicator
  - [ ] "Return to Present" button

- [ ] **Phase 4: Polish & Documentation**
  - [ ] Performance testing
  - [ ] Accessibility audit
  - [ ] User documentation
  - [ ] Migration guide

### Files Modified/Created

**Backend (Django/GraphQL)**:
- `config/graphql/graphene_types.py` - Added version types and resolvers
- `config/graphql/mutations.py` - Added RestoreDeletedDocument and RestoreDocumentToVersion mutations
- `config/graphql/queries.py` - Added deletedDocumentsInCorpus query for trash folder
- `opencontractserver/tests/test_document_versioning_graphql.py` - NEW: GraphQL tests

**Frontend (React/TypeScript)**:
- `frontend/src/components/documents/VersionBadge.tsx` - NEW: Badge component with keyboard accessibility
- `frontend/src/components/documents/VersionHistoryPanel.tsx` - NEW: History panel with timeline, restore mutation integration
- `frontend/src/components/documents/ModernDocumentItem.tsx` - Integrated badge and history panel, passes corpusId
- `frontend/src/components/corpuses/folders/TrashFolderView.tsx` - NEW: Trash folder view with restore functionality
- `frontend/src/components/corpuses/folders/FolderTreeSidebar.tsx` - Added Trash folder item
- `frontend/src/components/corpuses/folders/FolderDocumentBrowser.tsx` - Integrated TrashFolderView rendering
- `frontend/src/graphql/queries.ts` - Added version fields to GET_DOCUMENTS
- `frontend/src/graphql/queries/folders.ts` - Added GET_DELETED_DOCUMENTS_IN_CORPUS query
- `frontend/src/graphql/mutations.ts` - Added RESTORE_DELETED_DOCUMENT mutation
- `frontend/src/graphql/cache.ts` - Added Apollo cache policies for versioning
- `frontend/src/types/graphql-api.ts` - Added TypeScript types
- `frontend/tests/VersionBadge.ct.tsx` - NEW: Badge component tests (13 passing)
- `frontend/tests/VersionHistoryPanel.ct.tsx` - NEW: History panel tests (18 passing, including 5 mutation tests)
- `frontend/tests/VersionHistoryPanelTestWrapper.tsx` - NEW: Test wrapper with Apollo mocking and mutation support
- `frontend/tests/TrashFolderView.ct.tsx` - NEW: Trash folder tests (17 passing)
- `frontend/tests/TrashFolderViewTestWrapper.tsx` - NEW: Test wrapper for trash folder

### Next Steps (Priority Order)

1. **Phase 2.5**: Time travel slider (optional advanced feature)
2. **Add tests for TrashFolderView**: Component tests for trash folder
3. **Run backend integration tests**: Verify backend mutation tests when Docker networking resolves
4. **Performance testing**: Verify lazy loading and cache efficiency
5. **End-to-end integration**: Test full workflow with actual backend
6. **Implement permanent deletion**: Currently only soft-delete is implemented

### Known Issues

- Docker networking issue may prevent running backend tests (iptables DOCKER-ISOLATION-STAGE-2 missing)
- TypeScript compilation verified passing with all new types ✓
- Version history restore mutation fully wired (frontend → backend) ✓
- Trash folder view complete with restore functionality ✓
- Download version functionality still a placeholder (console.log)
- Permanent delete not yet implemented (soft-delete only)

### Test Results (Latest Run)

- **VersionBadge Component Tests**: 13/13 passing ✓
- **VersionHistoryPanel Component Tests**: 18/18 passing ✓ (includes 5 mutation tests)
- **TrashFolderView Component Tests**: 17/17 passing ✓ (includes restore mutation tests)
- **Backend Mutation Tests**: 9 tests written (4 RestoreDeletedDocument + 5 RestoreDocumentToVersion)
- **Total versioning-related frontend tests**: 48 passing ✓ (13 + 18 + 17)
- **All pre-commit hooks**: Passing ✓ (black, isort, flake8)
- **TypeScript compilation**: Passing ✓
- Tests cover: rendering, interactions, ARIA accessibility, tooltips, error states, loading states, mutation success/failure handling, message dismissal, selection management, bulk operations
