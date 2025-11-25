# Corpus Folders API Reference for Frontend

## Quick Start

The corpus folders API provides hierarchical organization for documents within corpuses. This document focuses on the GraphQL API surface and integration points for frontend developers.

---

## GraphQL Types

### CorpusFolderType

```graphql
type CorpusFolderType {
  # Standard fields from AnnotatePermissionsForReadMixin
  id: ID!
  myPermissions: [String!]!       # ["create_corpus", "read_corpus", "update_corpus", etc.]
  isPublished: Boolean!
  objectSharedWith: [UserType!]!

  # Folder-specific fields
  name: String!                    # Folder name (not full path)
  description: String!             # Optional description
  color: String!                   # Hex color code (default: "#05313d")
  icon: String!                    # Icon identifier (default: "folder")
  tags: GenericScalar!             # JSON array of tag strings
  isPublic: Boolean!
  created: DateTime!
  modified: DateTime!

  # Relationships
  corpus: CorpusType!
  parent: CorpusFolderType         # null if root-level folder
  creator: UserType!

  # Computed fields
  path: String!                    # Full path from root (e.g., "Legal/Contracts/2024")
  documentCount: Int!              # Documents directly in this folder
  descendantDocumentCount: Int!   # Documents in this folder + all subfolders
  children: [CorpusFolderType!]!  # Immediate child folders
}
```

**Important Notes:**
- `tags` returns a JSON string like `"[\"tag1\", \"tag2\"]"` - parse with `JSON.parse()` if needed
- `myPermissions` inherits from parent corpus (folders don't have separate permissions)
- `path` is a computed field showing the full folder path with "/" separators

### DocumentType (New Field)

```graphql
type DocumentType {
  # ... existing fields ...

  # NEW: Get folder assignment for this document in a specific corpus
  folderInCorpus(corpusId: ID!): CorpusFolderType  # null = document is in root
}
```

### CorpusType (New Field)

```graphql
type CorpusType {
  # ... existing fields ...

  # NEW: All folders in this corpus
  folders: [CorpusFolderType!]!
}
```

---

## Queries

### 1. Get All Folders in a Corpus

**Query:**
```graphql
query GetCorpusFolders($corpusId: ID!) {
  corpusFolders(corpusId: $corpusId) {
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
}
```

**Response:**
```json
{
  "data": {
    "corpusFolders": [
      {
        "id": "Q29ycHVzRm9sZGVyVHlwZTox",
        "name": "Legal",
        "description": "Legal documents",
        "color": "#ff0000",
        "icon": "folder",
        "tags": "[\"important\"]",
        "path": "Legal",
        "documentCount": 5,
        "descendantDocumentCount": 23,
        "parent": null,
        "myPermissions": ["read_corpus", "update_corpus"],
        "isPublished": false
      },
      {
        "id": "Q29ycHVzRm9sZGVyVHlwZToy",
        "name": "Contracts",
        "path": "Legal/Contracts",
        "parent": {
          "id": "Q29ycHVzRm9sZGVyVHlwZTox",
          "name": "Legal"
        },
        // ... other fields
      }
    ]
  }
}
```

**Usage:**
- Returns a **flat list** of all folders
- Frontend builds tree structure from `parent` relationships
- Use this query to populate the folder tree sidebar
- Returns only folders user has permission to view

**TypeScript Example:**
```typescript
const { data, loading } = useQuery(GET_CORPUS_FOLDERS, {
  variables: { corpusId: selectedCorpusId }
});

// Build tree from flat list
const folderTree = buildTreeFromFlatList(data?.corpusFolders || []);
```

### 2. Get Single Folder

**Query:**
```graphql
query GetCorpusFolder($id: ID!) {
  corpusFolder(id: $id) {
    id
    name
    path
    parent {
      id
      name
    }
    children {
      id
      name
      documentCount
    }
    # ... other fields
  }
}
```

**Usage:**
- Get detailed info about a specific folder
- Includes immediate children
- Use for folder detail views or breadcrumb construction

### 3. Get Documents in a Folder

**Query:**
```graphql
query GetDocumentsInFolder(
  $corpusId: ID!
  $folderId: String  # Use "__root__" for root documents, or folder global ID
  $limit: Int
  $offset: Int
) {
  documents(
    corpusId: $corpusId
    inFolderId: $folderId
    limit: $limit
    offset: $offset
  ) {
    edges {
      node {
        id
        title
        description
        # ... other document fields
      }
    }
    pageInfo {
      hasNextPage
      hasPreviousPage
    }
    totalCount
  }
}
```

**Special Values for `inFolderId`:**
- `null` or omitted: All documents in corpus (no filtering)
- `"__root__"`: Documents not assigned to any folder (in corpus root)
- Folder global ID: Documents in that specific folder

**Usage:**
```typescript
// Get root documents
const { data } = useQuery(GET_DOCUMENTS, {
  variables: {
    corpusId: selectedCorpusId,
    inFolderId: "__root__"
  }
});

// Get documents in specific folder
const { data } = useQuery(GET_DOCUMENTS, {
  variables: {
    corpusId: selectedCorpusId,
    inFolderId: selectedFolderId
  }
});
```

---

## Mutations

### 1. Create Folder

**Mutation:**
```graphql
mutation CreateCorpusFolder(
  $corpusId: ID!
  $name: String!
  $parentId: ID           # Omit for root-level folder
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
      id
      name
      path
      parent {
        id
      }
    }
  }
}
```

**Example Variables:**
```json
{
  "corpusId": "Q29ycHVzVHlwZTox",
  "name": "2024 Contracts",
  "parentId": "Q29ycHVzRm9sZGVyVHlwZToy",
  "description": "All contracts from 2024",
  "color": "#3498db",
  "icon": "folder",
  "tags": ["2024", "active"]
}
```

**Success Response:**
```json
{
  "data": {
    "createCorpusFolder": {
      "ok": true,
      "message": "Folder created successfully",
      "folder": {
        "id": "Q29ycHVzRm9sZGVyVHlwZTo1",
        "name": "2024 Contracts",
        "path": "Legal/Contracts/2024 Contracts",
        "parent": {
          "id": "Q29ycHVzRm9sZGVyVHlwZToy"
        }
      }
    }
  }
}
```

**Error Response:**
```json
{
  "data": {
    "createCorpusFolder": {
      "ok": false,
      "message": "A folder named '2024 Contracts' already exists in this location",
      "folder": null
    }
  }
}
```

**Permission Required:** User must be corpus creator, corpus is public, or user has UPDATE permission on corpus

### 2. Update Folder

**Mutation:**
```graphql
mutation UpdateCorpusFolder(
  $folderId: ID!
  $name: String
  $description: String
  $color: String
  $icon: String
  $tags: [String]
) {
  updateCorpusFolder(
    folderId: $folderId
    name: $name
    description: $description
    color: $color
    icon: $icon
    tags: $tags
  ) {
    ok
    message
    folder {
      id
      name
      description
      color
      icon
      tags
    }
  }
}
```

**Notes:**
- All fields except `folderId` are optional
- Only provided fields will be updated
- Cannot change parent (use `moveCorpusFolder` instead)

**Permission Required:** UPDATE on corpus

### 3. Move Folder

**Mutation:**
```graphql
mutation MoveCorpusFolder(
  $folderId: ID!
  $newParentId: ID  # null to move to root
) {
  moveCorpusFolder(
    folderId: $folderId
    newParentId: $newParentId
  ) {
    ok
    message
    folder {
      id
      name
      path
      parent {
        id
        name
      }
    }
  }
}
```

**Usage:**
```typescript
// Move folder to root
await moveFolder({
  variables: {
    folderId: draggedFolderId,
    newParentId: null
  }
});

// Move folder under another folder
await moveFolder({
  variables: {
    folderId: draggedFolderId,
    newParentId: targetFolderId
  }
});
```

**Validation:**
- Cannot move folder into itself
- Cannot move folder into its own descendants (circular reference)
- Cannot move folder to different corpus
- Duplicate names under new parent will fail

**Permission Required:** UPDATE on corpus

### 4. Delete Folder

**Mutation:**
```graphql
mutation DeleteCorpusFolder(
  $folderId: ID!
  $deleteContents: Boolean  # Default: false
) {
  deleteCorpusFolder(
    folderId: $folderId
    deleteContents: $deleteContents
  ) {
    ok
    message
  }
}
```

**Behavior:**
- `deleteContents: false` (default):
  - Moves child folders to this folder's parent
  - Moves documents to corpus root (deletes CorpusDocumentFolder records)

- `deleteContents: true`:
  - Deletes folder and all subfolders (CASCADE)
  - Documents remain in corpus but move to root

**Permission Required:** DELETE on corpus

### 5. Move Document to Folder

**Mutation:**
```graphql
mutation MoveDocumentToFolder(
  $documentId: ID!
  $corpusId: ID!
  $folderId: ID  # null to move to root
) {
  moveDocumentToFolder(
    documentId: $documentId
    corpusId: $corpusId
    folderId: $folderId
  ) {
    ok
    message
    document {
      id
      title
    }
  }
}
```

**Usage:**
```typescript
// Move document to folder
await moveDocument({
  variables: {
    documentId: doc.id,
    corpusId: currentCorpusId,
    folderId: targetFolderId
  }
});

// Move document to corpus root
await moveDocument({
  variables: {
    documentId: doc.id,
    corpusId: currentCorpusId,
    folderId: null
  }
});
```

**Notes:**
- Replaces any existing folder assignment for this document in this corpus
- Document must already be in the corpus
- Folder must be in the same corpus

**Permission Required:** UPDATE on corpus

### 6. Bulk Move Documents to Folder

**Mutation:**
```graphql
mutation MoveDocumentsToFolder(
  $documentIds: [ID]!
  $corpusId: ID!
  $folderId: ID  # null to move to root
) {
  moveDocumentsToFolder(
    documentIds: $documentIds
    corpusId: $corpusId
    folderId: $folderId
  ) {
    ok
    message
    movedCount
  }
}
```

**Usage:**
```typescript
// Bulk move selected documents
await bulkMoveDocuments({
  variables: {
    documentIds: selectedDocumentIds,
    corpusId: currentCorpusId,
    folderId: targetFolderId
  }
});
```

**Response:**
```json
{
  "data": {
    "moveDocumentsToFolder": {
      "ok": true,
      "message": "Successfully moved 15 document(s)",
      "movedCount": 15
    }
  }
}
```

**Permission Required:** UPDATE on corpus

---

## Integration Patterns

### 1. Building Folder Tree from Flat List

```typescript
interface CorpusFolder {
  id: string;
  name: string;
  parent: { id: string } | null;
  children?: CorpusFolder[];
}

function buildFolderTree(folders: CorpusFolder[]): CorpusFolder[] {
  const folderMap = new Map<string, CorpusFolder>();
  const rootFolders: CorpusFolder[] = [];

  // First pass: create map and initialize children arrays
  folders.forEach(folder => {
    folderMap.set(folder.id, { ...folder, children: [] });
  });

  // Second pass: build tree structure
  folders.forEach(folder => {
    const node = folderMap.get(folder.id)!;

    if (folder.parent) {
      const parentNode = folderMap.get(folder.parent.id);
      if (parentNode) {
        parentNode.children!.push(node);
      }
    } else {
      rootFolders.push(node);
    }
  });

  return rootFolders;
}
```

### 2. Building Breadcrumb Path

```typescript
function buildBreadcrumbPath(
  folderId: string | null,
  folders: CorpusFolder[]
): CorpusFolder[] {
  if (!folderId) return [];

  const folderMap = new Map(folders.map(f => [f.id, f]));
  const path: CorpusFolder[] = [];

  let current = folderMap.get(folderId);
  while (current) {
    path.unshift(current);
    current = current.parent ? folderMap.get(current.parent.id) : null;
  }

  return path;
}
```

### 3. Optimistic UI Updates

```typescript
// When creating a folder
const [createFolder] = useMutation(CREATE_CORPUS_FOLDER, {
  update(cache, { data: { createCorpusFolder } }) {
    if (createCorpusFolder.ok) {
      // Add to cache
      cache.modify({
        fields: {
          corpusFolders(existingFolders = []) {
            const newFolderRef = cache.writeFragment({
              data: createCorpusFolder.folder,
              fragment: gql`
                fragment NewFolder on CorpusFolderType {
                  id
                  name
                  parent { id }
                }
              `
            });
            return [...existingFolders, newFolderRef];
          }
        }
      });
    }
  },
  optimisticResponse: {
    createCorpusFolder: {
      __typename: 'CreateCorpusFolderMutation',
      ok: true,
      message: 'Creating...',
      folder: {
        __typename: 'CorpusFolderType',
        id: `temp-${Date.now()}`,
        name: variables.name,
        path: `.../${variables.name}`,
        parent: variables.parentId ? { id: variables.parentId } : null,
        // ... other fields with sensible defaults
      }
    }
  }
});
```

### 4. Permission Checking

```typescript
function canUserManageFolders(folder: CorpusFolder): boolean {
  const permissions = folder.myPermissions;
  return permissions.includes('update_corpus') ||
         permissions.includes('create_corpus');
}

function canUserDeleteFolder(folder: CorpusFolder): boolean {
  return folder.myPermissions.includes('delete_corpus');
}

// In component
{canUserManageFolders(folder) && (
  <button onClick={() => openEditModal(folder)}>
    Edit Folder
  </button>
)}
```

### 5. Drag and Drop Document Assignment

```typescript
const [moveDocument] = useMutation(MOVE_DOCUMENT_TO_FOLDER);

const handleDocumentDrop = async (
  documentId: string,
  targetFolderId: string | null
) => {
  try {
    const result = await moveDocument({
      variables: {
        documentId,
        corpusId: currentCorpusId,
        folderId: targetFolderId
      },
      // Refetch documents in both source and target folders
      refetchQueries: ['GetDocumentsInFolder']
    });

    if (result.data.moveDocumentToFolder.ok) {
      toast.success('Document moved successfully');
    }
  } catch (error) {
    toast.error('Failed to move document');
  }
};
```

---

## Error Handling

All mutations return a consistent structure:

```typescript
interface MutationResponse {
  ok: boolean;
  message: string;
  // ... other fields
}
```

**Common Error Messages:**

| Message | Meaning | Solution |
|---------|---------|----------|
| "You do not have permission to..." | User lacks required permission | Check corpus permissions |
| "A folder named 'X' already exists in this location" | Duplicate name under same parent | Choose different name or parent |
| "Folder not found" | Folder doesn't exist or user can't access | Check folder ID and permissions |
| "Corpus not found" | Corpus doesn't exist or user can't access | Check corpus ID and permissions |
| "Cannot move folder into itself or its descendants" | Circular reference attempt | Choose different target parent |
| "Parent folder must be in the same corpus" | Cross-corpus move attempt | Keep folders within same corpus |
| "Document is not in this corpus" | Document not added to corpus | Add document to corpus first |

---

## Rate Limiting

All mutations use rate limiting:
- CREATE, UPDATE, MOVE operations: `RateLimits.WRITE_LIGHT`
- DELETE operations: `RateLimits.WRITE_LIGHT`
- BULK operations: `RateLimits.WRITE_HEAVY`

In production, rate limits are enforced. In tests, rate limiting is skipped for TestContext.

---

## Apollo Cache Considerations

### Automatic Cache Updates
These happen automatically:
- Fetching a single folder updates the cache entry
- Fetching folder list updates all folder entries

### Manual Cache Updates Needed
Handle these in mutation `update` functions:
- Creating a folder → add to `corpusFolders` list
- Deleting a folder → remove from list
- Moving a folder → update parent relationships
- Moving documents → refetch affected folder document counts

### Example Cache Update

```typescript
const [deleteFolder] = useMutation(DELETE_CORPUS_FOLDER, {
  update(cache, { data }) {
    if (data.deleteCorpusFolder.ok) {
      cache.modify({
        fields: {
          corpusFolders(existingFolders, { readField }) {
            return existingFolders.filter(
              folderRef => readField('id', folderRef) !== deletedFolderId
            );
          }
        }
      });

      // Also evict the folder itself
      cache.evict({ id: cache.identify({
        __typename: 'CorpusFolderType',
        id: deletedFolderId
      })});
      cache.gc();
    }
  }
});
```

---

## Testing Utilities

### Mock Data Factory

```typescript
function createMockFolder(overrides?: Partial<CorpusFolder>): CorpusFolder {
  return {
    id: `mock-folder-${Math.random()}`,
    name: 'Test Folder',
    description: 'Test description',
    color: '#05313d',
    icon: 'folder',
    tags: '[]',
    path: 'Test Folder',
    documentCount: 0,
    descendantDocumentCount: 0,
    created: new Date().toISOString(),
    modified: new Date().toISOString(),
    parent: null,
    children: [],
    myPermissions: ['read_corpus', 'update_corpus'],
    isPublished: false,
    ...overrides
  };
}
```

### Mock Apollo Provider

```typescript
const mocks = [
  {
    request: {
      query: GET_CORPUS_FOLDERS,
      variables: { corpusId: 'test-corpus-id' }
    },
    result: {
      data: {
        corpusFolders: [
          createMockFolder({ name: 'Folder 1' }),
          createMockFolder({ name: 'Folder 2', parent: { id: 'folder-1-id' } })
        ]
      }
    }
  }
];

<MockedProvider mocks={mocks} addTypename={false}>
  <YourComponent />
</MockedProvider>
```

---

## Quick Reference: Mutation Permissions

| Mutation | Permission Required |
|----------|-------------------|
| `createCorpusFolder` | corpus.creator OR corpus.is_public OR UPDATE permission |
| `updateCorpusFolder` | corpus.creator OR corpus.is_public OR UPDATE permission |
| `moveCorpusFolder` | corpus.creator OR corpus.is_public OR UPDATE permission |
| `deleteCorpusFolder` | corpus.creator OR DELETE permission |
| `moveDocumentToFolder` | corpus.creator OR corpus.is_public OR UPDATE permission |
| `moveDocumentsToFolder` | corpus.creator OR corpus.is_public OR UPDATE permission |

**Key Points:**
- Folders have NO separate permissions - they inherit from corpus
- `myPermissions` field shows effective permissions (from corpus)
- Public corpuses allow any authenticated user to manage folders
- DELETE permission is stricter (no is_public bypass)

---

## Common Workflows

### 1. Initial Load: Populate Folder Tree
```
1. User selects corpus
2. Query: corpusFolders(corpusId)
3. Build tree from flat list
4. Render FolderTreeSidebar
5. Load documents for root folder
```

### 2. Navigate to Folder
```
1. User clicks folder in tree
2. Update selectedFolderIdAtom
3. Update URL: /corpus/:corpusId/folder/:folderId
4. Query: documents(corpusId, inFolderId)
5. Render FolderBreadcrumb + CorpusDocumentCards
```

### 3. Create Subfolder
```
1. User right-clicks folder → "Create Subfolder"
2. Show CreateFolderModal with parentId pre-filled
3. User fills form
4. Mutation: createCorpusFolder(parentId: selectedFolderId)
5. Update cache, refetch if needed
6. Expand parent in tree to show new child
```

### 4. Drag Document to Folder
```
1. User drags document from list
2. User drops on folder in tree
3. Mutation: moveDocumentToFolder(documentId, folderId)
4. Refetch document list for both folders
5. Update folder document counts
```

### 5. Reorganize Folders
```
1. User drags folder in tree
2. User drops on target parent folder
3. Validate: not dropping into self/descendant
4. Mutation: moveCorpusFolder(newParentId)
5. Update tree structure
6. Update breadcrumb if currently viewing moved folder
```

---

**Last Updated**: 2025-11-10
**Backend Version**: v3.0.0.b3
**Status**: Production Ready ✅
