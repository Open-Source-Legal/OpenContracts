# Frontend Requirements for Metadata Fields

This document outlines the frontend components and features needed to support the unified metadata system built on the Column/Datacell architecture.

## Architecture Overview

OpenContracts uses a **unified data model** where the same components handle both extracted data and manual metadata:

- **Fieldsets**: Each corpus automatically gets one fieldset containing all its columns
- **Columns**: Define metadata schema with `is_manual_entry=true` for manual metadata
- **Datacells**: Store values with `extract=null` for manual metadata vs `extract=<Extract>` for extracted data
- **Unified Validation**: Same validation logic for both extracted and manual data

This eliminates duplication and provides consistent data handling throughout the application.

## Core Components Needed

### 1. Metadata Column Management UI

#### Corpus Settings Panel
- **Location**: Corpus settings/configuration page
- **Features**:
  - List all metadata columns for the corpus (where `is_manual_entry=true`)
  - Add new metadata column button
  - Edit/delete existing metadata columns
  - Reorder columns using `display_order` field
  - Show column usage statistics across corpus documents

#### Metadata Column Editor Modal/Form
- **Components**:
  - Column name input (`name` field)
  - Data type selector (`data_type` field from `METADATA_DATA_TYPES`)
  - Dynamic validation configuration panel (`validation_config` JSON)
  - Default value editor (`default_value` JSON)
  - Help text input (`help_text` field)
  - Display order input (`display_order` field)
  - Preview of how the column will render
  - Save/Cancel buttons

#### Data Type Specific Configuration Components
- **String/Text**: `min_length`, `max_length`, `regex_pattern` in `validation_config`
- **Numeric**: `min_value`, `max_value` in `validation_config`
- **Choice**: `choices` array in `validation_config` (required for CHOICE/MULTI_CHOICE)
- **Date/DateTime**: `min_date`, `max_date` in `validation_config`
- **Boolean**: `default_value` toggle

### 2. Document Metadata Entry UI

#### Metadata Panel in Document View
- **Location**: Side panel in document viewer
- **Features**:
  - Collapsible metadata section
  - Form with all corpus metadata columns (ordered by `display_order`)
  - Dynamic field rendering based on `data_type`
  - Real-time validation using column `validation_config`
  - Auto-save creating/updating Datacells
  - Show help text from column `help_text` field

#### Field Input Components by Data Type
- **STRING**: Text input with length validation
- **TEXT**: Textarea with length validation  
- **BOOLEAN**: Toggle switch reflecting boolean validation
- **INTEGER**: Number input with range validation
- **FLOAT**: Number input with decimal and range validation
- **DATE**: Date picker with format and range validation
- **DATETIME**: DateTime picker with ISO 8601 format validation
- **URL**: Text input with URL format validation
- **EMAIL**: Text input with email format validation
- **CHOICE**: Dropdown using `validation_config.choices`
- **MULTI_CHOICE**: Multi-select using `validation_config.choices`
- **JSON**: JSON editor with syntax validation

### 3. Metadata Display Components

#### Document Card Metadata Display
- Show key metadata datacell values on document cards
- Configurable which columns to display
- Color coding based on datacell values (e.g., status)

#### Metadata Quick View
- Hover tooltip showing all metadata datacells
- Click to expand full metadata panel

### 4. Metadata Search and Filter

#### Advanced Search Panel
- Filter documents by metadata datacell values
- Support for:
  - Exact match (string, choice)
  - Range queries (numeric, date) 
  - Boolean filters
  - Multi-value filters (multi-choice)
  - Null/not-null filters (where datacell exists/doesn't exist)

#### Filter Builder UI
- Visual query builder for complex metadata filters
- Save/load filter presets
- Export filtered results

### 5. Bulk Metadata Operations

#### Bulk Edit Modal
- Select multiple documents
- Update metadata datacells in bulk
- Options:
  - Set same value for all (creates/updates datacells)
  - Clear values (deletes datacells)
  - Find and replace in existing datacells

#### Import/Export
- CSV import/export for metadata datacells
- Column mapping UI for imports
- Validation preview using column validation rules

## GraphQL API Integration

**Important**: OpenContracts uses Graphene Django which automatically converts Python `snake_case` field names to GraphQL `camelCase`. For example:
- Model field `data_type` becomes GraphQL field `dataType`
- Model field `validation_config` becomes GraphQL field `validationConfig`
- Model field `is_manual_entry` becomes GraphQL field `isManualEntry`

### Core Mutations
```graphql
# Schema Management
createMetadataColumn(
  corpusId: ID!
  name: String!
  dataType: String!
  validationConfig: GenericScalar
  defaultValue: GenericScalar
  helpText: String
  displayOrder: Int
)

updateMetadataColumn(
  columnId: ID!
  name: String
  validationConfig: GenericScalar
  defaultValue: GenericScalar
  helpText: String
  displayOrder: Int
)

# Value Management  
setMetadataValue(
  documentId: ID!
  corpusId: ID!
  columnId: ID!
  value: GenericScalar!
)

deleteMetadataValue(
  documentId: ID!
  corpusId: ID!
  columnId: ID!
)
```

### Core Queries
```graphql
# Get corpus metadata schema
corpusMetadataColumns(corpusId: ID!): [ColumnType]

# Get document metadata values
documentMetadataDatacells(documentId: ID!): [DatacellType]

# Check completion status
metadataCompletionStatusV2(documentId: ID!, corpusId: ID!): MetadataCompletionStatusType
```

### Type Definitions
```graphql
type ColumnType {
  id: ID!
  name: String!
  fieldset: FieldsetType!
  dataType: String          # null for extraction columns
  validationConfig: GenericScalar
  defaultValue: GenericScalar
  helpText: String
  displayOrder: Int
  isManualEntry: Boolean!
  
  # Extraction-specific fields (null for metadata columns)
  query: String
  matchText: String
  outputType: String!
  taskName: String!
  extractIsList: Boolean!
}

type DatacellType {
  id: ID!
  data: GenericScalar!      # Structured as {"value": actual_value}
  dataDefinition: String!
  column: ColumnType!
  document: DocumentType!
  extract: ExtractType      # null for metadata, set for extracted data
  creator: UserType!
  started: DateTime
  completed: DateTime
  failed: DateTime
  approvedBy: UserType
  rejectedBy: UserType
  correctedData: JSONString
}
```

## Technical Implementation Notes

### State Management
```typescript
interface MetadataState {
  // Schema state
  columns: Column[];
  
  // Values state  
  datacells: Record<string, Datacell>; // keyed by columnId
  
  // UI state
  validation: Record<string, ValidationError>;
  isDirty: boolean;
  isSaving: boolean;
}

interface Column {
  id: string;
  name: string;
  dataType: MetadataDataType;
  validationConfig: Record<string, any>;
  defaultValue: any;
  helpText: string;
  displayOrder: number;
  isManualEntry: boolean;
}

interface Datacell {
  id?: string;
  data: { value: any };
  columnId: string;
  documentId: string;
  creator: string;
}

type MetadataDataType = 
  | 'STRING' | 'TEXT' | 'BOOLEAN' | 'INTEGER' | 'FLOAT'
  | 'DATE' | 'DATETIME' | 'URL' | 'EMAIL' 
  | 'CHOICE' | 'MULTI_CHOICE' | 'JSON';
```

### Apollo Client Integration
```typescript
// Efficient caching strategy
const typePolicies = {
  CorpusType: {
    fields: {
      metadataColumns: {
        merge(existing = [], incoming) {
          return incoming;
        }
      }
    }
  },
  DocumentType: {
    fields: {
      metadataDatacells: {
        merge(existing = [], incoming) {
          return incoming;
        }
      }
    }
  }
};

// Optimistic updates for better UX
const setMetadataValue = useMutation(SET_METADATA_VALUE, {
  optimisticResponse: {
    setMetadataValue: {
      ok: true,
      obj: {
        id: 'temp-id',
        data: { value: newValue },
        column: { id: columnId },
        // ... other fields
      }
    }
  }
});
```

### Client-Side Validation
```typescript
const validateDatacellValue = (value: any, column: Column): ValidationError | null => {
  const { dataType, validationConfig } = column;
  
  // Required field check
  if (validationConfig.required && (value === null || value === undefined || value === '')) {
    return { message: `${column.name} is required` };
  }
  
  // Type-specific validation (mirrors backend validation)
  switch (dataType) {
    case 'STRING':
    case 'TEXT':
      return validateStringConstraints(value, validationConfig);
    case 'INTEGER':
    case 'FLOAT':
      return validateNumericRange(value, validationConfig);
    case 'CHOICE':
      return validateChoice(value, validationConfig);
    case 'MULTI_CHOICE':
      return validateMultiChoice(value, validationConfig);
    case 'EMAIL':
      return validateEmail(value);
    case 'URL':
      return validateUrl(value);
    case 'DATE':
      return validateDate(value, validationConfig);
    case 'DATETIME':
      return validateDateTime(value, validationConfig);
    case 'BOOLEAN':
      return validateBoolean(value);
    case 'JSON':
      return validateJson(value);
    default:
      return null;
  }
};
```

## User Experience Considerations

### 1. Progressive Disclosure
- Show required columns first (where `validationConfig.required=true`)
- Group columns by category if needed
- Collapsible sections for large schemas

### 2. Inline Validation
- Real-time validation matching backend `Datacell.clean()` logic
- Clear error messages using column `help_text`
- Visual indicators for validation state

### 3. Smart Defaults
- Pre-fill with column `default_value` when creating new datacells
- Remember user preferences per column type

### 4. Auto-save Strategy
```typescript
// Debounced auto-save for better UX
const debouncedSave = useDebouncedCallback(
  (datacells: Record<string, Datacell>) => {
    // Batch multiple datacell updates
    batchUpdateMetadata(datacells);
  },
  2000 // 2 second delay
);
```

### 5. Responsive Design
- Mobile-friendly column management
- Touch-optimized datacell entry
- Adaptive layouts for different screen sizes

## Performance Considerations

### Query Optimization
```graphql
# Efficient corpus metadata loading
query GetCorpusMetadata($corpusId: ID!) {
  corpus(id: $corpusId) {
    metadataColumns {
      id
      name  
      dataType
      validationConfig
      defaultValue
      helpText
      displayOrder
    }
  }
}

# Efficient document metadata loading
query GetDocumentMetadata($documentId: ID!) {
  document(id: $documentId) {
    metadataDatacells {
      id
      data
      column {
        id
        name
        dataType
      }
    }
  }
}
```

### Caching Strategy
- Cache column schemas at corpus level
- Cache datacells at document level  
- Invalidate cache on schema changes
- Use Apollo Client field policies for efficient merging

### Batch Operations
```typescript
// Batch multiple datacell updates
const batchUpdateMetadata = async (updates: DatacellUpdate[]) => {
  const mutations = updates.map(update => ({
    mutation: SET_METADATA_VALUE,
    variables: update
  }));
  
  await Promise.all(mutations.map(m => apolloClient.mutate(m)));
};
```

## Testing Requirements

### Unit Tests
- Column configuration components
- Datacell input components for each data type
- Validation logic matching backend
- State management reducers

### Integration Tests
- Full metadata workflow (create column → enter datacell → save)
- GraphQL mutation/query integration
- Apollo Client cache behavior
- Bulk operations

### E2E Tests
- Complete corpus setup with metadata columns
- Document metadata entry flow
- Search and filter by metadata datacells
- Bulk edit operations across multiple documents

## Accessibility Requirements

- ARIA labels for all form inputs
- Keyboard navigation through metadata forms
- Screen reader support for validation errors
- High contrast mode compatibility
- Focus management in modals and panels

## Migration Considerations

### From Legacy Annotation System
1. **Data Migration**: Transform existing metadata annotations to datacells
2. **Schema Migration**: Convert annotation labels to columns
3. **UI Updates**: Replace annotation-based forms with column-based forms
4. **API Updates**: Update all GraphQL queries/mutations to new endpoints

### Component Migration Path
1. **Phase 1**: Read-only metadata display using new API
2. **Phase 2**: Individual datacell editing
3. **Phase 3**: Column schema management
4. **Phase 4**: Advanced search and filtering
5. **Phase 5**: Bulk operations and import/export

## Error Handling

### Validation Errors
```typescript
interface ValidationError {
  field: string;
  message: string;
  code: 'REQUIRED' | 'TYPE_MISMATCH' | 'CONSTRAINT_VIOLATION' | 'FORMAT_ERROR';
}

// Handle backend validation errors
const handleValidationError = (error: ApolloError) => {
  if (error.graphQLErrors.some(e => e.extensions?.code === 'VALIDATION_ERROR')) {
    // Show field-specific validation errors
    const validationErrors = extractValidationErrors(error);
    setFieldErrors(validationErrors);
  }
};
```

### Network Errors
- Retry failed mutations automatically
- Show offline indicators
- Queue changes for when connectivity returns
- Optimistic updates with rollback on failure

## Security Considerations

### Input Sanitization
- Sanitize all user inputs before sending to backend
- Use parameterized GraphQL queries
- Validate JSON inputs for JSON data type columns

### Permission Handling
- Check corpus permissions before showing metadata UI
- Disable editing for read-only users
- Handle permission errors gracefully

This updated document now accurately reflects the unified Column/Datacell architecture and provides comprehensive guidance for frontend implementation.