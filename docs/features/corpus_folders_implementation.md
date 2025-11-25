# Corpus Folders Implementation

## Status: Backend Complete ✅ | Frontend Data Layer Complete ✅ | Frontend UI Components TODO 🚧

This document tracks the implementation of hierarchical folder structures within corpuses to organize documents.

## Overview

The folder system allows users to organize documents within corpuses using a tree structure. Key design decisions:

- **ONE folder per document per corpus** (document can be in different folders in different corpuses)
- Documents not in a folder are in the "corpus root"
- Folders inherit permissions from their parent corpus (no separate folder permissions)
- TreeNode-based implementation for efficient hierarchy queries
- Performant data loading: eager load all folders (lightweight), lazy/paginated load documents per folder

## Backend Implementation ✅ COMPLETE

### 1. Database Models (`opencontractserver/corpuses/models.py`)

**CorpusFolder Model:**
- TreeNode-based hierarchy using django-tree-queries
- Fields: name, corpus FK, parent FK, description, color, icon, tags (JSONField), is_public, creator, timestamps
- Uses `PermissionedTreeQuerySet.as_manager(with_tree_fields=True)`
- Methods: `get_path()`, `get_document_count()`, `get_descendant_document_count()`
- Unique constraint: folder name must be unique per parent within corpus
- Validation: parent must be in same corpus

**CorpusDocumentFolder Model:**
- Junction table enforcing one folder per document per corpus
- Fields: document FK, corpus FK, folder FK (nullable for root)
- Unique constraint: (document, corpus)
- Validation: folder must belong to same corpus, document must be in corpus

**Migrations:**
- `0024_corpusfolder_corpusdocumentfolder_and_more.py`: Initial models and constraints
- `0025_corpusfolder_is_public.py`: Added is_public field for permission queries

### 2. GraphQL Schema

**Types (`config/graphql/graphene_types.py`):**

**CorpusFolderType:**
- Inherits from `AnnotatePermissionsForReadMixin` for permission fields
- Custom fields: `path`, `document_count`, `descendant_document_count`, `children`
- Queryset filtering via `visible_to_user()`

**DocumentType additions:**
- `folder_in_corpus(corpusId)` field returns folder assignment for document in specific corpus

**CorpusType additions:**
- `folders` field lists all folders in corpus

**Queries (`config/graphql/queries.py`):**
- `corpus_folders(corpus_id)`: Returns flat list of all folders in corpus (client builds tree)
- `corpus_folder(id)`: Get single folder by ID

**Filters (`config/graphql/filters.py`):**
- `in_folder_id` filter on DocumentFilter
- Supports special `__root__` value for documents not in any folder

**Mutations (`config/graphql/corpus_folder_mutations.py` + `mutations.py`):**

All mutations check permissions: creator OR is_public OR explicit corpus permission

1. **createCorpusFolder**: Create new folder (root or nested)
   - Args: corpusId, name, parentId?, description?, color?, icon?, tags?
   - Returns: ok, message, folder

2. **updateCorpusFolder**: Update folder properties
   - Args: folderId, name?, description?, color?, icon?, tags?
   - Returns: ok, message, folder

3. **moveCorpusFolder**: Move folder to new parent
   - Args: folderId, newParentId?
   - Prevents circular dependencies
   - Returns: ok, message, folder

4. **deleteCorpusFolder**: Delete folder
   - Args: folderId, deleteContents?
   - If deleteContents=false, moves children to parent and documents to root
   - Returns: ok, message

5. **moveDocumentToFolder**: Move single document to folder
   - Args: documentId, corpusId, folderId?
   - null folderId moves to root
   - Returns: ok, message, document

6. **moveDocumentsToFolder**: Bulk move documents
   - Args: documentIds[], corpusId, folderId?
   - Returns: ok, message, movedCount

### 3. Tests ✅ ALL PASSING

**Model Tests (`opencontractserver/tests/test_corpus_folders.py`):**
- 19 tests covering model creation, hierarchy, constraints, permissions, tree traversal

**Mutation Tests (`opencontractserver/tests/test_corpus_folder_mutations.py`):**
- 16 tests covering all CRUD operations, permission checks, edge cases

**Total: 35 passing tests**

## Frontend Data Layer ✅ COMPLETE

### 1. GraphQL Operations (`frontend/src/graphql/queries/folders.ts`)

**Queries:**
- `GET_CORPUS_FOLDERS` - Fetch all folders in corpus (flat list)
- `GET_CORPUS_FOLDER` - Fetch single folder with children

**Mutations:**
- `CREATE_CORPUS_FOLDER` - Create new folder (root or nested)
- `UPDATE_CORPUS_FOLDER` - Update folder properties
- `MOVE_CORPUS_FOLDER` - Move folder to new parent
- `DELETE_CORPUS_FOLDER` - Delete folder (with cascade options)
- `MOVE_DOCUMENT_TO_FOLDER` - Move single document to folder
- `MOVE_DOCUMENTS_TO_FOLDER` - Bulk move documents

**TypeScript Interfaces:**
- `CorpusFolderType` - Main folder type
- `ParsedCorpusFolderType` - With tags parsed to array
- `FolderTreeNode` - Tree node with children
- All input/output interfaces for queries and mutations

**Helper Functions:**
- `parseCorpusFolderTags(folder)` - Parse JSON tags to array
- `buildFolderTree(folders)` - Build tree from flat list
- `buildFolderBreadcrumb(folderId, folders)` - Build path to folder
- `getAllDescendantFolderIds(folderId, folders)` - Get all descendant IDs

**Document Query Updates:**
- Updated `GET_DOCUMENTS` to support `inFolderId` parameter
- Special value `"__root__"` for documents not in any folder
- Updated `RequestDocumentsInputs` interface

### 2. State Management (`frontend/src/atoms/folderAtoms.ts`)

**Base State Atoms:**
- `selectedFolderIdAtom` - Currently selected folder (null = root)
- `folderListAtom` - Flat list from server
- `folderCorpusIdAtom` - Current corpus context

**Derived Atoms (Computed):**
- `folderTreeAtom` - Tree structure built from flat list
- `folderBreadcrumbAtom` - Path from root to current folder
- `currentFolderAtom` - Currently selected folder object
- `folderMapAtom` - Map for quick lookups

**UI State Atoms:**
- `expandedFolderIdsAtom` - Expanded folders (persisted to localStorage)
- `showCreateFolderModalAtom` - Create modal visibility
- `showEditFolderModalAtom` - Edit modal visibility
- `showMoveFolderModalAtom` - Move modal visibility
- `showDeleteFolderModalAtom` - Delete modal visibility
- `activeFolderModalIdAtom` - Folder being edited/moved/deleted
- `createFolderParentIdAtom` - Parent for create operation
- `folderSearchQueryAtom` - Tree search/filter query

**Drag & Drop State:**
- `draggingFolderIdAtom` - Currently dragging folder
- `draggingDocumentIdAtom` - Currently dragging document
- `dropTargetFolderIdAtom` - Drop target folder
- `enableDragDropAtom` - Enable/disable drag-drop

**Permission Atoms:**
- `canCreateFoldersAtom` - Can user create folders in current corpus
- `canUpdateCurrentFolderAtom` - Can user update current folder
- `canDeleteCurrentFolderAtom` - Can user delete current folder

**Helper Actions (Write-only Atoms):**
- `toggleFolderExpansionAtom` - Toggle folder expansion
- `expandFolderPathAtom` - Expand folder and all ancestors
- `collapseAllFoldersAtom` - Collapse all folders
- `expandAllFoldersAtom` - Expand all folders
- `selectAndExpandFolderAtom` - Select folder and expand path to it
- `openCreateFolderModalAtom` - Open create modal with parent
- `openEditFolderModalAtom` - Open edit modal
- `openMoveFolderModalAtom` - Open move modal
- `openDeleteFolderModalAtom` - Open delete modal
- `closeAllFolderModalsAtom` - Close all modals

## Frontend UI Components ✅ COMPLETE

### Architecture Plan

**State Management (Jotai):** ✅ COMPLETE
- All atoms implemented in `frontend/src/atoms/folderAtoms.ts`
- Base, derived, UI, drag-drop, and permission atoms
- Helper actions for common operations

**Routing Integration:** 🚧 TODO
- Update routing system per `docs/frontend/routing_system.md`
- URL pattern: `/corpus/:corpusId/folder/:folderId?`
- Folder state should drive URL and vice versa

### Components Implemented

#### 1. Core Folder Components ✅ COMPLETE

**`FolderTreeNode.tsx`** ✅
- Recursive component rendering single folder with children
- Expand/collapse chevron with smooth animation
- Folder icon changes (open/closed) based on expanded state
- Color-coded folders (supports custom colors)
- Document count badge showing documents in folder
- Selection highlighting with blue border
- Drop target highlighting for drag-and-drop
- Right-click context menu (Open, Create Subfolder, Edit, Delete)
- Draggable for folder-to-folder moves
- Title tooltip showing full folder path
- Indentation based on depth (20px per level)

**`FolderTreeSidebar.tsx`** ✅
- Fetches folders via GET_CORPUS_FOLDERS query
- Builds tree structure using `folderTreeAtom` (computed from flat list)
- Search/filter with recursive tree filtering
- Shows "Corpus Root" as special clickable item at top
- "New Folder" button (permission-aware via `canCreateFoldersAtom`)
- Expand All / Collapse All buttons
- Loading state with Semantic UI Loader
- Error state with user-friendly message
- Empty state for no folders
- Search empty state when no matches
- Custom scrollbar styling
- Updates `folderListAtom` on query completion

**`FolderBreadcrumb.tsx`** ✅
- Shows navigation path: Corpus Root > Folder1 > Folder2
- Computed from `folderBreadcrumbAtom` (walks up tree)
- Clickable segments to navigate up hierarchy
- Ellipsis for deep nesting (configurable `maxDepth`, default 5)
- Always shows first folder + last N-1 folders when using ellipsis
- Highlights current folder (bold, different color, non-clickable)
- Home icon for Corpus Root
- Chevron separators between segments
- Horizontal scroll for very wide paths
- Tooltips showing full path on hover

#### 2. Integration Updates 🚧 TODO

**`FolderDocumentBrowser.tsx`** (Container) 🚧 TODO
- Combines FolderTreeSidebar + FolderBreadcrumb + CorpusDocumentCards
- Layout: sidebar on left, main content on right
- Responsive: collapse sidebar on mobile

**`CorpusDocumentCards.tsx`** Updates 🚧 TODO:
- Accept `folderId` prop (or read from route/atom)
- Update GraphQL query to filter by `inFolderId`
- Show FolderBreadcrumb at top
- Support drag-and-drop document assignment

**Routing Updates 🚧 TODO:**
- Extend corpus routes to handle `/folder/:folderId`
- Update `useCorpusRouter` hook
- Sync folderId between URL ↔ Jotai atoms

#### 3. Folder Action Components ✅ COMPLETE

**`CreateFolderModal.tsx`** ✅
- Form fields: name (required), description, color picker, icon, tags
- Visual color preview with click-to-pick
- Hex color input with validation
- Parent folder context shown with info message
- Comma-separated tag input
- Form validation (required name, max length, no duplicates at same level)
- Uses `CREATE_CORPUS_FOLDER` mutation
- Optimistic update + refetch
- Auto-selects and expands newly created folder
- Error handling with user-friendly messages

**`EditFolderModal.tsx`** ✅
- Similar to create modal but pre-populated with current values
- Loads folder from `folderMapAtom` using `activeFolderModalIdAtom`
- Tags parsed to comma-separated string using `parseCorpusFolderTags`
- Form validation (no duplicate names at same level, excluding self)
- Uses `UPDATE_CORPUS_FOLDER` mutation
- Updates local cache optimistically
- Refetches to ensure consistency

**`MoveFolderModal.tsx`** ✅
- Dropdown with all valid destination folders
- "Corpus Root" as special option
- Prevents circular moves (excludes self and all descendants)
- Shows current location with folder path
- Shows folder being moved with icon and name
- Validates no duplicate names at destination
- Uses `MOVE_CORPUS_FOLDER` mutation
- Semantic UI Dropdown with search
- User-friendly error messages for edge cases

**`DeleteFolderModal.tsx`** ✅
- Warning modal with AlertTriangle icon
- Red color scheme to indicate danger
- Shows folder info: path, document count, subfolder count
- Explains what will happen: subfolders and documents move to parent
- "This action cannot be undone" warning
- Lists affected items (subfolders and documents)
- Uses `DELETE_CORPUS_FOLDER` mutation
- Clears selection if deleted folder was selected
- Negative button styling (red)

**Component Index (`index.ts`)** ✅
- Exports all folder components for easy importing

### GraphQL Fragments and Queries ✅ COMPLETE

All queries and mutations are in `frontend/src/graphql/queries/folders.ts`

**~~Create `frontend/src/graphql/fragments/folders.graphql`:~~** (Not needed - using inline gql)

```graphql
fragment CorpusFolderFields on CorpusFolderType {
  id
  name
  description
  color
  icon
  tags
  path
  documentCount
  descendantDocumentCount
  created
  modified
  parent {
    id
    name
  }
  myPermissions
  isPublished
}

fragment CorpusFolderTree on CorpusFolderType {
  ...CorpusFolderFields
  children {
    ...CorpusFolderFields
  }
}
```

**Create `frontend/src/graphql/queries/folders.graphql`:**

```graphql
query GetCorpusFolders($corpusId: ID!) {
  corpusFolders(corpusId: $corpusId) {
    ...CorpusFolderFields
  }
}

query GetCorpusFolder($id: ID!) {
  corpusFolder(id: $id) {
    ...CorpusFolderTree
  }
}
```

**Create `frontend/src/graphql/mutations/folders.graphql`:**

```graphql
mutation CreateCorpusFolder(
  $corpusId: ID!
  $name: String!
  $parentId: ID
  $description: String
  $color: String
  $icon: String
  $tags: [String]
) {
  createCorpusFolder(
    corpusId: $corpusId
    name: $name
    parentId: $parentId
    description: $description
    color: $color
    icon: $icon
    tags: $tags
  ) {
    ok
    message
    folder {
      ...CorpusFolderFields
    }
  }
}

# ... similar for update, move, delete mutations
```

### Jotai Atoms ✅ COMPLETE

**`frontend/src/atoms/folderAtoms.ts`:** Fully implemented with all atoms listed above

```typescript
import { atom } from 'jotai';
import { atomWithStorage } from 'jotai/utils';

// Currently selected folder ID (null = root)
export const selectedFolderIdAtom = atom<string | null>(null);

// Flat list of folders from server
export const folderListAtom = atom<CorpusFolder[]>([]);

// Derived: folder tree (built from flat list)
export const folderTreeAtom = atom((get) => {
  const folders = get(folderListAtom);
  return buildFolderTree(folders);
});

// Derived: breadcrumb path to current folder
export const folderBreadcrumbAtom = atom((get) => {
  const folderId = get(selectedFolderIdAtom);
  const folders = get(folderListAtom);
  return buildBreadcrumbPath(folderId, folders);
});

// Expanded folder IDs (for tree UI state)
export const expandedFolderIdsAtom = atomWithStorage<Set<string>>(
  'expandedFolderIds',
  new Set()
);
```

### Implementation Order (Recommended)

1. **GraphQL Layer** (1-2 hours)
   - Create fragments, queries, mutations
   - Run codegen to generate TypeScript types

2. **State Management** (1 hour)
   - Create Jotai atoms
   - Add folder tree building utilities

3. **Routing Updates** (1-2 hours)
   - Extend corpus routes for folders
   - Sync URL ↔ state

4. **Basic Tree Component** (3-4 hours)
   - FolderTreeNode (recursive)
   - FolderTreeSidebar (with virtualization)
   - Basic expand/collapse, selection

5. **Document Integration** (2-3 hours)
   - Update CorpusDocumentCards to filter by folder
   - Add FolderBreadcrumb navigation
   - Test document viewing in folders

6. **Folder CRUD Modals** (4-5 hours)
   - Create/Edit/Move/Delete folder modals
   - Form validation, error handling
   - Mutation integration with optimistic updates

7. **Drag and Drop** (2-3 hours)
   - Document → folder assignment
   - Folder → folder moving
   - Use react-dnd or native drag API

8. **Polish** (2-3 hours)
   - Keyboard navigation
   - Accessibility (ARIA labels)
   - Loading states, empty states
   - Error handling

**Total Estimated Time: 18-26 hours**

## Testing Strategy (Frontend)

### Unit Tests
- Folder tree building utilities
- Atom derivations
- Route parameter parsing

### Component Tests (Playwright)
- Mount FolderTreeSidebar with mock data
- Test expand/collapse
- Test folder selection
- Test context menu

### Integration Tests
- Full folder CRUD workflow
- Document filtering by folder
- Drag and drop operations

## Performance Considerations

### Backend (Already Optimized)
- TreeNode uses PostgreSQL CTEs for efficient hierarchy queries
- Indexes on corpus+name, corpus+parent for fast lookups
- `visible_to_user()` filters at database level

### Frontend (To Implement)
- **Virtualization**: Only render visible folders in tree (react-window)
- **Lazy Loading**: Load document lists per folder on demand
- **Optimistic Updates**: Update UI immediately, rollback on error
- **Cache Strategy**: Apollo cache for folder list, invalidate on mutations
- **Debounce**: Folder search/filter input

## Security & Permissions

- Folders inherit corpus permissions (no separate folder ACLs)
- All mutations check: `corpus.creator == user OR corpus.is_public OR user_has_permission(UPDATE/DELETE)`
- Frontend should hide/disable actions based on `myPermissions` field
- Structural rule: Only superusers can modify structural annotations (doesn't apply to folders)

## Edge Cases Handled

### Backend ✅
- Duplicate folder names under same parent → Error
- Moving folder into itself or descendant → Error
- Parent in different corpus → Error
- Document already in folder → Replaces assignment
- Deleting folder with contents → Optional cascade or preserve
- Root-level folders (parentId=null) → Supported

### Frontend (To Handle)
- Deep nesting UI (breadcrumb ellipsis, tree indent limits)
- Long folder names (truncate with tooltip)
- Empty folders (show "No documents" state)
- Corpus root (show as special "Root" folder in tree)
- Permission changes (refetch folders on corpus permission update)

## Migration Path for Existing Data

- All existing corpus documents are implicitly in "root" (no CorpusDocumentFolder record)
- Users can create folders and move documents as needed
- No data migration required

## Future Enhancements (Not in Scope)

- Folder templates (predefined folder structures)
- Folder-level metadata/tags
- Bulk folder operations (move multiple folders)
- Folder sharing (separate from corpus permissions)
- Folder search across corpuses
- Folder color themes
- Document tagging within folders
- Folder view modes (list, grid, kanban)

## Related Documentation

- **Permissioning Guide**: `docs/permissioning/consolidated_permissioning_guide.md`
- **Routing System**: `docs/frontend/routing_system.md`
- **Backend Models**: `opencontractserver/corpuses/models.py`
- **GraphQL Types**: `config/graphql/graphene_types.py`
- **Mutations**: `config/graphql/corpus_folder_mutations.py`

## Questions & Decisions Log

**Q: Should folders have separate permissions from corpus?**
A: No. Folders inherit corpus permissions to keep the model simple. Users who can edit a corpus can manage its folders.

**Q: Can a document be in multiple folders within a corpus?**
A: No. ONE folder per document per corpus. This simplifies UI and prevents ambiguity. Document can be in different folders in different corpuses.

**Q: How to handle documents not in any folder?**
A: They're in the "corpus root". No CorpusDocumentFolder record = root. UI shows "Root" as top-level tree item.

**Q: Should we paginate folder list?**
A: No. Folders are lightweight metadata. Load all folders eagerly (flat list), build tree on client. Paginate documents per folder.

**Q: What about very deep hierarchies?**
A: No artificial depth limit. UI handles with breadcrumb ellipsis and tree virtualization. In practice, most corpuses won't exceed 5-6 levels.

---

**Last Updated**: 2025-11-10
**Status**: Backend complete (35/35 tests passing), Frontend pending
**Next Step**: Create GraphQL fragments and queries for frontend
