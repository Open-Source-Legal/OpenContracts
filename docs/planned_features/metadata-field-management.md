# OpenContracts Metadata Field Management - Implementation Plan & Specification

## Executive Summary

This document outlines the plan to implement metadata field management features in OpenContracts, allowing users to:
1. Define and manage metadata schemas at the corpus level
2. Edit metadata values inline in the document list view (Excel-like functionality)
3. View and manage metadata columns in the corpus settings page

## Architecture Overview

### Backend Foundation (Already Implemented)
- **Unified Column/Datacell Model**: Metadata uses the same infrastructure as data extraction
- **Metadata Columns**: Identified by `is_manual_entry=true` and have `data_type` field
- **Metadata Fieldsets**: One-to-one relationship with corpus via `corpus.metadata_schema`
- **Validation**: Built-in validation based on `data_type` and `validation_config`
- **GraphQL API**: Full CRUD operations for metadata columns and values

### Frontend Requirements
The frontend needs to implement:
1. Metadata schema management UI in corpus settings (CorpusSettings.tsx)
2. Inline editing in document list view
3. GraphQL integration for metadata operations

## Detailed Implementation Plan

### Phase 1: GraphQL Integration & Core Infrastructure

#### 1.1 Create GraphQL Queries and Mutations
Create new file: `frontend/src/graphql/metadataOperations.ts`

```typescript
// Queries
export const GET_CORPUS_METADATA_COLUMNS = gql`
  query GetCorpusMetadataColumns($corpusId: ID!) {
    corpusMetadataColumns(corpusId: $corpusId) {
      id
      name
      dataType
      helpText
      validationConfig
      defaultValue
      displayOrder
      isManualEntry
    }
  }
`;

export const GET_DOCUMENT_METADATA_DATACELLS = gql`
  query GetDocumentMetadataDatacells($documentId: ID!, $corpusId: ID!) {
    documentMetadataDatacells(documentId: $documentId, corpusId: $corpusId) {
      id
      data
      column {
        id
        name
        dataType
        validationConfig
      }
    }
  }
`;

// Mutations
export const CREATE_METADATA_COLUMN = gql`
  mutation CreateMetadataColumn(
    $corpusId: ID!
    $name: String!
    $dataType: String!
    $validationConfig: GenericScalar
    $defaultValue: GenericScalar
    $helpText: String
    $displayOrder: Int
  ) {
    createMetadataColumn(
      corpusId: $corpusId
      name: $name
      dataType: $dataType
      validationConfig: $validationConfig
      defaultValue: $defaultValue
      helpText: $helpText
      displayOrder: $displayOrder
    ) {
      ok
      message
      obj {
        id
        name
        dataType
      }
    }
  }
`;

export const UPDATE_METADATA_COLUMN = gql`...`;
export const DELETE_METADATA_COLUMN = gql`...`;
export const SET_METADATA_VALUE = gql`...`;
export const DELETE_METADATA_VALUE = gql`...`;
```

#### 1.2 Type Definitions
Create new file: `frontend/src/types/metadata.ts`

```typescript
export enum MetadataDataType {
  STRING = "STRING",
  TEXT = "TEXT",
  BOOLEAN = "BOOLEAN",
  INTEGER = "INTEGER",
  FLOAT = "FLOAT",
  DATE = "DATE",
  DATETIME = "DATETIME",
  URL = "URL",
  EMAIL = "EMAIL",
  CHOICE = "CHOICE",
  MULTI_CHOICE = "MULTI_CHOICE",
  JSON = "JSON"
}

export interface MetadataColumn {
  id: string;
  name: string;
  dataType: MetadataDataType;
  validationConfig?: ValidationConfig;
  defaultValue?: any;
  helpText?: string;
  displayOrder: number;
  isManualEntry: boolean;
}

export interface ValidationConfig {
  required?: boolean;
  min_length?: number;
  max_length?: number;
  min_value?: number;
  max_value?: number;
  choices?: string[];
  regex_pattern?: string;
  min_date?: string;
  max_date?: string;
}
```

### Phase 2: Corpus Settings - Metadata Schema Management

#### 2.1 Create Metadata Management Component
Create new file: `frontend/src/components/corpuses/CorpusMetadataSettings.tsx`

**Key Features:**
- List all metadata columns for the corpus
- Add/Edit/Delete metadata columns
- Reorder columns (drag & drop)
- Configure validation rules per data type
- Preview of field rendering

**UI Structure:**
```typescript
export const CorpusMetadataSettings: React.FC<{ corpusId: string }> = ({ corpusId }) => {
  // Component will include:
  // 1. Header with "Add Metadata Field" button
  // 2. Table/List of existing metadata columns
  // 3. Drag handles for reordering
  // 4. Edit/Delete actions per column
  // 5. Modal for creating/editing columns
};
```

#### 2.2 Integrate into CorpusSettings.tsx
Add a new section to the existing CorpusSettings component:

```typescript
// In CorpusSettings.tsx
<InfoSection>
  <SectionHeader>
    <SectionTitle>Metadata Fields</SectionTitle>
    <AddMetadataButton onClick={() => setShowMetadataModal(true)}>
      <Icon name="plus" />
      Add Field
    </AddMetadataButton>
  </SectionHeader>
  <MetadataContent>
    <CorpusMetadataSettings corpusId={corpus.id} />
  </MetadataContent>
</InfoSection>
```

### Phase 3: Document List View - Inline Metadata Editing

#### 3.1 Create Enhanced Document Grid Component
Create new file: `frontend/src/components/documents/DocumentMetadataGrid.tsx`

**Key Features:**
- Excel-like grid interface
- Inline cell editing
- Keyboard navigation (Tab, Enter, Arrow keys)
- Real-time validation
- Bulk operations support
- Column resizing
- Sort by metadata values
- Filter by metadata values

**Component Structure:**
```typescript
interface DocumentMetadataGridProps {
  corpusId: string;
  documents: DocumentType[];
  metadataColumns: MetadataColumn[];
  onUpdateValue: (documentId: string, columnId: string, value: any) => void;
  loading?: boolean;
}

export const DocumentMetadataGrid: React.FC<DocumentMetadataGridProps> = ({...}) => {
  // Implement virtualized grid for performance
  // Use react-window or similar for large datasets
  // Include cell editors for each data type
};
```

#### 3.2 Create Cell Editors for Each Data Type
Create new directory: `frontend/src/components/metadata/editors/`

- `StringEditor.tsx` - Text input with length validation
- `BooleanEditor.tsx` - Toggle/checkbox
- `DateEditor.tsx` - Date picker
- `ChoiceEditor.tsx` - Dropdown selector
- `MultiChoiceEditor.tsx` - Multi-select component
- `NumberEditor.tsx` - Numeric input with range validation
- etc.

#### 3.3 Modify Document List View
Update `CorpusDocumentCards.tsx` to support grid view toggle:

```typescript
// Add view mode toggle
const [viewMode, setViewMode] = useState<'cards' | 'grid'>('cards');

// Conditionally render based on view mode
{viewMode === 'cards' ? (
  <DocumentCards {...existing props} />
) : (
  <DocumentMetadataGrid
    corpusId={opened_corpus_id}
    documents={documents}
    metadataColumns={metadataColumns}
    onUpdateValue={handleMetadataUpdate}
  />
)}
```

### Phase 4: Metadata Display in Card View

#### 4.1 Enhance DocumentItem Component
Modify `DocumentItem.tsx` to display key metadata values:

```typescript
// Add metadata display section
<div className="metadata-preview">
  {document.metadataDatacells?.slice(0, 3).map(datacell => (
    <MetadataTag
      key={datacell.id}
      label={datacell.column.name}
      value={datacell.data.value}
      dataType={datacell.column.dataType}
    />
  ))}
</div>
```

### Phase 5: Search and Filter Integration

#### 5.1 Add Metadata Filters
Create new component: `frontend/src/components/widgets/filters/MetadataFilter.tsx`

**Features:**
- Dynamic filter UI based on data type
- Range filters for numeric/date fields
- Multi-select for choice fields
- Text search for string fields

#### 5.2 Integrate with Search Bar
Update the document search bar in `Corpuses.tsx` to include metadata filters:

```typescript
<CreateAndSearchBar
  onChange={handleDocumentSearchChange}
  actions={contract_actions}
  placeholder="Search for document in corpus..."
  value={documentSearchCache}
  filters={
    <>
      <MetadataFilter
        corpusId={opened_corpus.id}
        onFilterChange={handleMetadataFilterChange}
      />
      {/* Existing filters */}
    </>
  }
/>
```

## UI/UX Design Principles

### Grid View Design
- **Clean, Excel-like interface**: Familiar spreadsheet paradigm
- **Sticky headers**: Column headers remain visible while scrolling
- **Frozen columns**: Document title column stays fixed
- **Visual feedback**: Highlight edited cells, show validation errors inline
- **Keyboard shortcuts**: Standard spreadsheet navigation

### Performance Considerations
- **Virtualization**: Only render visible rows for large datasets
- **Debounced saves**: Batch updates to reduce API calls
- **Optimistic updates**: Immediate UI feedback with rollback on error
- **Lazy loading**: Load metadata values as needed

### Accessibility
- **ARIA labels**: Proper labeling for screen readers
- **Keyboard navigation**: Full keyboard support
- **High contrast mode**: Support for accessibility themes
- **Focus management**: Clear focus indicators

## Technical Considerations

### State Management
- Use Apollo Client cache for metadata schema
- Local state for edit mode and unsaved changes
- Optimistic updates for better UX

### Validation
- Client-side validation matching backend rules
- Real-time validation feedback
- Batch validation for bulk operations

### Performance Optimization
- Virtual scrolling for large document lists
- Memoization of expensive computations
- Efficient re-rendering strategies

## Migration Path

### Phase 1: Read-only Display (Week 1)
- Implement GraphQL queries
- Display metadata in document cards
- Show metadata schema in settings

### Phase 2: Schema Management (Week 2)
- Add/edit/delete metadata columns
- Validation configuration UI
- Column reordering

### Phase 3: Inline Editing (Week 3-4)
- Grid view implementation
- Cell editors for all data types
- Real-time validation

### Phase 4: Advanced Features (Week 5)
- Bulk operations
- Import/export
- Advanced filtering

## Testing Strategy

### Unit Tests
- Cell editor components
- Validation logic
- State management

### Integration Tests
- GraphQL operations
- End-to-end workflows
- Error handling

### E2E Tests
- Complete metadata workflow
- Performance with large datasets
- Keyboard navigation

## Questions to Address

1. **Column Visibility**: Should users be able to hide/show columns in grid view?
2. **Export Format**: What formats should be supported for bulk export (CSV, Excel, JSON)?
3. **Permissions**: Should there be column-level permissions or only corpus-level?
4. **History**: Should we track metadata value changes over time?
5. **Templates**: Should we support metadata schema templates for common use cases?

## Dependencies

No additional npm packages required initially. The implementation will use:
- Existing Apollo Client for GraphQL
- Semantic UI React for base components
- Styled-components for custom styling
- React hooks for state management

## Success Metrics

1. **Performance**: Grid view loads < 2s for 1000 documents
2. **Usability**: Users can edit metadata values with < 3 clicks
3. **Reliability**: 99% success rate for metadata updates
4. **Adoption**: 80% of corpus creators define metadata schemas

This plan provides a comprehensive approach to implementing metadata field management in OpenContracts while maintaining consistency with the existing codebase and providing an excellent user experience.