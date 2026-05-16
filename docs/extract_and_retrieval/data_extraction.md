# Extracting Structured Data from Documents

> **Last Updated: 2026-01-09**

## Overview

OpenContracts transforms any collection of documents into a **spreadsheet-like data grid**. You define *what* to extract via a **Fieldset**, and the system:

1. Fans out work across documents and columns using Celery
2. Uses our **structured extraction API** powered by PydanticAI agents
3. Enforces constraints through intelligent prompting
4. Parses results into Python primitives or Pydantic models with guaranteed type safety

Everything is orchestrated by two Celery tasks:
- **`run_extract`** – creates individual cells and queues work
- **`doc_extract_query_task`** – performs the actual extraction using our agent framework

> **LLM agents can also dispatch extracts.** The
> [`list_fieldsets` / `start_extract`](../architecture/llms/README.md#extract--analyzer-tools)
> agent tools wrap the same `run_extract` pipeline — letting a chat agent
> or an agent-based `CorpusAction` pick from configured Fieldsets and
> queue an extract under the standard approval gate. The tools always
> pick from existing Fieldsets; they never invent new column schemas.

## Data Models

All models are defined in [`opencontractserver/extracts/models.py`](../../opencontractserver/extracts/models.py).

### Fieldset

Groups related columns together. Each Fieldset represents a specific configuration of data fields to extract.

**Key features:**
- Defines the schema for extraction
- Can be linked to a corpus as its metadata schema
- Supports permissions for access control

### Column

Defines individual data fields to extract. Each column can be configured for either LLM-based extraction or manual entry.

**Extraction configuration:**
- **`query`** or **`match_text`**: The extraction prompt (one required for extraction columns)
- **`output_type`**: Python type as string (e.g., "str", "int", "list[str]")
- **`extract_is_list`**: Wraps the type in `List[]`
- **`must_contain_text`**: Only extract from sections containing this text
- **`limit_to_label`**: Only extract from annotations with this label
- **`instructions`**: Additional context for extraction

**Manual entry configuration:**
- **`is_manual_entry`**: When `True`, column is for manual metadata entry (no LLM extraction)
- **`data_type`**: Structured data type (STRING, INTEGER, DATE, BOOLEAN, CHOICE, etc.)
- **`validation_config`**: JSON configuration for field validation rules
- **`default_value`**: Default value for manual entry fields
- **`help_text`**: Help text displayed to users
- **`display_order`**: Order in which to display manual entry fields

### Extract

Represents an extraction job, containing metadata about the process.

**Usage:**
- Groups documents to process with the fieldset defining what to extract
- Tracks extraction progress and completion status
- Stores error information if extraction fails

### Datacell

Stores the result of extracting a specific column from a specific document.

**Features:**
- Stores extracted data in JSON format
- Links to source annotations (when available)
- Tracks processing status and errors
- Supports approval workflow for human review
- Captures LLM call history for debugging

## Extraction Pipeline

### Orchestration (`run_extract`)

The main orchestrator task that creates and manages extraction jobs:

```python
@shared_task
def run_extract(extract_id: Optional[str | int], user_id: str | int):
    # Creates Datacells for each document × column pair
    # Queues doc_extract_query_task for each cell
    # Uses chord to wait for completion
```

**Key operations:**
1. Creates one Datacell per document × column combination
2. Looks up the Celery task from `column.task_name`
3. Uses `chord(group(*tasks))` to wait for all cells
4. Calls `mark_extract_complete` when finished

### Per-Cell Extraction (`doc_extract_query_task`)

The async task that performs actual extraction using our agent framework:

```python
@celery_task_with_async_to_sync()
async def doc_extract_query_task(
    cell_id: int,
    similarity_top_k: int = 10,
    max_token_length: int = 64000
) -> None:
    """Agent-based data extraction pipeline using PydanticAI."""
```

**Extraction steps:**

1. **Setup**: Fetch Datacell, mark as started, validate corpus membership
2. **Type parsing**: Convert `column.output_type` string to Python type
3. **Prompt construction**: Build extraction prompt from query or match_text
4. **System prompt**: Add constraints from must_contain_text and limit_to_label
5. **Extract**: Call `agents.get_structured_response_from_document()`
6. **Save results**: Convert response to appropriate format and mark complete

### Async Task Decorator Pattern

The extraction task uses our custom decorator to handle async functions in Celery:

```python
@celery_task_with_async_to_sync()
async def doc_extract_query_task(...) -> None:
    # Async implementation
```

This decorator:
- Converts async functions to sync using `asgiref.sync.async_to_sync`
- Properly handles database connections
- Works seamlessly in test and production environments
- Avoids complex event loop management

**Testing async tasks:**
```python
from django.test import TransactionTestCase

class ExtractionTestCase(TransactionTestCase):
    def test_extraction(self):
        # Create datacell...
        doc_extract_query_task.si(datacell.id).apply()
        # Assert results...
```

## Sequence Diagram

```mermaid
sequenceDiagram
    participant U as User
    participant G as GraphQL/Admin
    participant R as run_extract
    participant Q as doc_extract_query_task
    participant A as Agent Framework
    participant LLM as Language Model

    U->>G: Start extraction
    G->>R: Call run_extract(extract_id)
    R->>R: Create Datacells
    R->>Q: Queue task for each cell
    Q->>A: get_structured_response()
    A->>LLM: Vector search + extraction
    LLM-->>A: Typed response
    A-->>Q: Parsed result
    Q-->>Q: Save to Datacell.data
    Q-->>R: Task complete
    R-->>G: Extract finished
    G-->>U: Results ready
```

## Supported Output Types

The system supports extraction to various Python types:

### Primitive Types
- `str` - Text strings
- `int` - Integers
- `float` - Floating point numbers
- `bool` - Boolean values

### Collection Types
- `list[str]` - List of strings
- `list[int]` - List of integers
- Use `extract_is_list=True` to wrap any type in a list

### Complex Types
- JSON objects via `dict` type
- Custom Pydantic models (planned)

## Constraints and Filtering

### Document Section Filtering

Use `must_contain_text` to limit extraction to specific sections:
```python
column.must_contain_text = "CONFIDENTIALITY"
# Only extracts from sections containing this text
```

### Annotation Label Filtering

Use `limit_to_label` to extract only from specific annotation types:
```python
column.limit_to_label = "contract-term"
# Only processes annotations with this label
```

### Additional Instructions

Provide extra context via `instructions`:
```python
column.instructions = "Extract as ISO 8601 date format"
```

## Error Handling

The extraction pipeline includes comprehensive error tracking:

1. **Cell-level errors**: Stored in `Datacell.stacktrace`
2. **Extract-level errors**: Stored in `Extract.error`
3. **Automatic retry**: Failed cells can be retried
4. **Partial completion**: Successful cells are saved even if others fail

## Manual Metadata Entry

Columns can be configured for manual entry instead of LLM-based extraction by setting `is_manual_entry=True`. This enables users to enter structured metadata directly.

### Supported Data Types

The `data_type` field supports: STRING, TEXT, BOOLEAN, INTEGER, FLOAT, DATE, DATETIME, URL, EMAIL, CHOICE, MULTI_CHOICE, and JSON. See `METADATA_DATA_TYPES` in the [models file](../../opencontractserver/extracts/models.py).

### Validation

Manual entry fields support validation via `validation_config`:

- **Numeric fields**: `min_value`, `max_value`
- **String fields**: `min_length`, `max_length`, `regex_pattern`
- **Choice fields**: `choices` (list of valid options)
- **Required fields**: `required: true`

Validation is enforced in `Datacell._validate_manual_entry()`.

### Constraints

Manual metadata has a unique constraint ensuring one datacell per document-column combination when `extract` is null.

## Datacell Approval Workflow

Datacells support a human review workflow for validating extracted or manually entered data.

### Approval Fields

- **`approved_by`**: User who approved the datacell value
- **`rejected_by`**: User who rejected the datacell value
- **`corrected_data`**: Stores user-corrected data when the original extraction was incorrect

### Workflow States

1. **Pending review**: Both `approved_by` and `rejected_by` are null
2. **Approved**: `approved_by` is set, value accepted as-is
3. **Rejected with correction**: `rejected_by` is set, `corrected_data` contains the fix

## LLM Call Logging

For debugging extraction issues, datacells capture the LLM conversation history.

- **`llm_call_log`**: Text field storing the complete message history from the extraction agent
- Useful for diagnosing unexpected extraction results
- Captured during `doc_extract_query_task` execution

## Performance Optimization

### Parallel Processing
- Extraction tasks run in parallel across Celery workers
- Each document × column combination is independent
- Scales horizontally with additional workers

### Vector Search Efficiency
- Uses pgvector for fast similarity search
- Caches embeddings for reuse
- Limits token context to `max_token_length`

### Database Optimization
- Batch creates Datacells
- Uses select_related/prefetch_related
- Minimizes database round trips

## Configuration

### Framework Selection

Set the agent framework in settings:
```python
LLMS_DEFAULT_AGENT_FRAMEWORK = "pydantic_ai"
```

### Custom Task Registration

Register custom extraction tasks:
```python
# In your app's tasks.py
@shared_task
def custom_extract_task(cell_id: int):
    # Custom extraction logic
    pass

# In Column configuration
column.task_name = "myapp.tasks.custom_extract_task"
```

## Next Steps

- **Complex types**: Expand output_type to support JSON schemas
- **Multi-step extraction**: Leverage conversation history
- **Cross-document aggregation**: Use corpus agents for analysis
- **Custom models**: Allow registration of Pydantic models
