# Metadata Fields

## Overview

OpenContracts provides a unified data model for both extracted data and manual metadata entry at the corpus level. This feature allows you to define structured metadata schemas for documents within a corpus, ensuring consistent data collection and validation across your document sets.

## Architecture

The metadata system is built on the same foundation as the data extraction system, providing a DRY (Don't Repeat Yourself) approach to structured data:

### Core Components

- **Fieldset**: Container for columns, with different uses for metadata vs extraction
  - **Metadata Fieldsets**: Linked to corpus via `OneToOneField(corpus)`, automatically created per corpus
  - **Extraction Fieldsets**: Independent fieldsets for data extraction tasks, used in Extract operations
- **Columns**: Define individual fields with data types, validation rules, and display configuration
  - **Metadata Columns**: Have `is_manual_entry=True` and `data_type` set
  - **Extraction Columns**: Have `is_manual_entry=False` and use `query`, `match_text`, `output_type`
- **Datacells**: Store the actual values for both metadata and extracted data
  - **Metadata Datacells**: Have `extract=NULL` and are manually created/edited
  - **Extraction Datacells**: Have `extract` set and are created by extraction tasks
- **Unified Validation**: Consistent validation logic shared between extracted data and manual metadata

### Key Benefits

1. **Unified Architecture**: Same models handle both extracted data and manual metadata
2. **Type Safety**: Strong typing with comprehensive validation
3. **Corpus-Level Schema**: Consistent metadata structure across all documents in a corpus
4. **Automatic Management**: Metadata fieldsets are automatically created when first metadata column is added to a corpus

## Fieldset Relationships: Metadata vs Extraction

OpenContracts uses the same `Fieldset` model for both metadata schemas and extraction schemas, but they serve different purposes:

### Metadata Fieldsets
- **Relationship**: `OneToOneField` between Corpus and Fieldset via `corpus.metadata_schema`
- **Creation**: Automatically created when first metadata column is added to a corpus
- **Naming**: Typically named "{Corpus Title} Metadata"
- **Purpose**: Define manual metadata entry schema for all documents in the corpus
- **Columns**: All columns have `is_manual_entry=True` and `data_type` values
- **Lifecycle**: Tied to the corpus lifecycle, deleted when corpus is deleted

### Extraction Fieldsets  
- **Relationship**: No direct corpus relationship, used via Extract objects
- **Creation**: Created manually or via extraction workflows
- **Naming**: User-defined or auto-generated based on extraction name
- **Purpose**: Define what data to extract from documents using AI/NLP
- **Columns**: All columns have `is_manual_entry=False` and extraction configuration (`query`, `match_text`, etc.)
- **Lifecycle**: Independent, can be reused across multiple extractions

### Key Differences

| Aspect | Metadata Fieldsets | Extraction Fieldsets |
|--------|-------------------|---------------------|
| **Corpus Link** | `corpus.metadata_schema` | None (via Extract) |
| **Column Type** | `is_manual_entry=True` | `is_manual_entry=False` |
| **Data Source** | Manual user input | AI/NLP extraction |
| **Schema Fields** | `data_type`, `validation_config` | `query`, `match_text`, `output_type` |
| **Datacell Link** | `extract=NULL` | `extract` references Extract |
| **Use Case** | Document metadata | Document data extraction |

## Supported Data Types

The system supports 12 different data types for metadata fields:

| Data Type | Description | Example Values | Validation |
|-----------|-------------|----------------|------------|
| `STRING` | Single-line text | "John Doe", "Contract-123" | Length, regex patterns |
| `TEXT` | Multi-line text | Long descriptions, notes | Length constraints |
| `BOOLEAN` | True/False values | true, false | Type validation |
| `INTEGER` | Whole numbers | 42, -10, 0 | Range validation |
| `FLOAT` | Decimal numbers | 3.14, -0.5, 100.0 | Range validation |
| `DATE` | Date values (YYYY-MM-DD) | "2024-01-15" | Date format, range |
| `DATETIME` | Date and time values (ISO 8601) | "2024-01-15T10:30:00Z" | DateTime format, range |
| `URL` | Web addresses | "https://example.com" | URL format validation |
| `EMAIL` | Email addresses | "user@example.com" | Email format validation |
| `CHOICE` | Single selection from predefined options | "Draft", "Final" | Choice validation |
| `MULTI_CHOICE` | Multiple selections from predefined options | ["Legal", "Financial"] | Multi-choice validation |
| `JSON` | Arbitrary JSON data | {"key": "value"} | JSON format validation |

## Column Configuration

Each metadata column can be configured with various constraints and options through the `validation_config` field:

### Common Configuration Options

```json
{
  "required": true,              // Whether the field is mandatory
  "help_text": "Enter the author's full name",  // Help text for users
  "default_value": "Unknown"    // Default value if not provided
}
```

### Type-Specific Configuration

#### String/Text Fields
```json
{
  "min_length": 3,              // Minimum character length
  "max_length": 100,            // Maximum character length
  "regex_pattern": "^[A-Z]{2}-\\d{4}$"  // Regex validation pattern
}
```

#### Numeric Fields (Integer/Float)
```json
{
  "min_value": 0,               // Minimum allowed value
  "max_value": 100              // Maximum allowed value
}
```

#### Choice Fields
```json
{
  "choices": ["Draft", "Review", "Final"]  // Available options (required)
}
```

#### Date/DateTime Fields
```json
{
  "min_date": "2024-01-01",     // Earliest allowed date
  "max_date": "2024-12-31"      // Latest allowed date
}
```

## Database Schema

### Column Model Fields

```python
class Column(models.Model):
    name = models.CharField(max_length=256)          # Field name
    data_type = models.CharField(choices=METADATA_DATA_TYPES, max_length=32, null=True, blank=True)  # Data type for metadata
    validation_config = NullableJSONField()         # Validation rules
    is_manual_entry = models.BooleanField(default=False)  # True for metadata, False for extraction
    default_value = NullableJSONField()             # Default value
    help_text = models.TextField(null=True, blank=True)  # User guidance
    display_order = models.IntegerField()           # Display ordering
    fieldset = models.ForeignKey(Fieldset)          # Parent fieldset
    
    # Legacy extraction fields (null for metadata columns)
    query = models.TextField(null=True, blank=True)
    match_text = models.TextField(null=True, blank=True)
    output_type = models.TextField()                # Required for all columns
    task_name = models.CharField(max_length=1024)   # Task for extraction
```

### Datacell Model Fields

```python
class Datacell(models.Model):
    data = NullableJSONField()                      # The actual value (structured as {"value": actual_value})
    document = models.ForeignKey(Document)          # Associated document
    column = models.ForeignKey(Column)              # Field definition
    extract = models.ForeignKey(Extract, null=True, blank=True) # Null for metadata, set for extracted data
    creator = models.ForeignKey(User)               # Who created it
    
    # Additional fields
    data_definition = models.TextField()            # Description of the data
    started = models.DateTimeField(null=True, blank=True)     # Processing timestamps
    completed = models.DateTimeField(null=True, blank=True)
    failed = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(User, null=True, blank=True, related_name="approved_cells")
    rejected_by = models.ForeignKey(User, null=True, blank=True, related_name="rejected_cells")
    corrected_data = NullableJSONField(null=True, blank=True)
```

### Constraints

- **Unique Metadata**: One metadata value per document/column combination (enforced by `unique_manual_metadata_per_doc_column` constraint)
- **Validation on Save**: Automatic validation based on column configuration through `Datacell.clean()` method
- **Corpus Isolation**: Metadata schemas are corpus-specific through fieldset-corpus relationship
- **Extract Nullability**: Metadata datacells have `extract=NULL`, extracted datacells have `extract` set
- **Manual Entry Flag**: Only columns with `is_manual_entry=True` can be used for manual metadata entry

## Validation System

The system performs comprehensive validation at multiple levels:

### Model-Level Validation

Validation occurs in the `Datacell.clean()` method and includes:

- **Type Checking**: Ensures values match the column's data type
- **Constraint Validation**: Applies min/max values, string lengths, regex patterns
- **Required Field Validation**: Enforces required fields
- **Choice Validation**: Ensures selected values are from allowed options
- **Format Validation**: Validates URLs, emails, dates, and JSON structure

### Validation Methods

```python
def _validate_manual_entry(self):
    """Comprehensive validation for manual metadata entries."""
    # Type-specific validation
    if self.column.data_type == 'BOOLEAN':
        self._validate_boolean_value()
    elif self.column.data_type in ['INTEGER', 'FLOAT']:
        self._validate_numeric_range()
    elif self.column.data_type in ['STRING', 'TEXT']:
        self._validate_string_constraints()
    # ... and so on
```

### Example Validation Errors

```python
# String too short
ValidationError: "Product Code must be at least 3 characters"

# Invalid choice
ValidationError: "Document Type values must be from: ['Contract', 'Invoice', 'Report']"

# Invalid date format
ValidationError: "Due Date must be in YYYY-MM-DD format"

# Required field missing
ValidationError: "Author is required"

# Type mismatch
ValidationError: "Status must be a boolean value"
```

## GraphQL API Integration

The metadata system exposes a complete GraphQL API for managing schemas and values. See [Metadata API Examples](metadata-api-examples.md) for detailed usage examples.

### Key Mutations
- `createMetadataColumn`: Define new metadata fields
- `updateMetadataColumn`: Modify existing metadata fields
- `setMetadataValue`: Set metadata values for documents
- `deleteMetadataValue`: Remove metadata values

### Key Queries
- `corpusMetadataColumns`: Get metadata schema for a corpus
- `documentMetadataDatacells`: Get metadata values for a document
- `metadataCompletionStatusV2`: Check completion status

## Best Practices

### Schema Design
1. **Plan Your Schema**: Design your metadata schema before adding documents
2. **Use Specific Types**: Choose the most appropriate data type (e.g., EMAIL instead of STRING)
3. **Provide Guidance**: Add clear help_text and default values
4. **Order Fields**: Use display_order for logical field arrangement

### Data Entry
1. **Validate Early**: Set appropriate constraints to catch errors at entry time
2. **Use Defaults**: Provide sensible default values for optional fields
3. **Required vs Optional**: Carefully consider which fields should be required

### Performance
1. **Bulk Operations**: Use bulk operations for setting metadata on multiple documents
2. **Indexing**: Metadata fields are automatically indexed for efficient querying
3. **Lazy Loading**: Validation occurs on save, not on read

## Migration from Legacy Systems

When migrating from annotation-based metadata systems:

1. **Extract Existing Data**: Export current metadata values
2. **Define New Schema**: Create columns matching existing metadata fields
3. **Migrate Values**: Transform annotation data to datacell format
4. **Cleanup**: Remove old annotation-based metadata

## Integration Points

### Document Import/Export
- Metadata schemas are included in corpus export/import
- Values are preserved during document transfer
- Validation ensures data integrity during import

### Permissions
- Metadata access inherits from corpus permissions
- Fine-grained control over who can modify schemas vs values
- Audit trail for all metadata changes

### Search and Filtering
- Metadata values are searchable and filterable
- Type-aware search (e.g., date range queries)
- Integration with corpus-wide search functionality

## Technical Notes

### Database Constraints
- `UniqueConstraint` ensures one metadata value per document/column
- `Q(extract__isnull=True)` identifies metadata vs extracted data
- Foreign key relationships maintain data integrity

### Performance Considerations
- Metadata queries are optimized with proper indexing
- Bulk operations supported for large-scale metadata entry
- Lazy validation reduces read-time overhead

### Extensibility
- New data types can be added by extending `METADATA_DATA_TYPES`
- Custom validation can be added to the validation chain
- GraphQL schema automatically reflects model changes