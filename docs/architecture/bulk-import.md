# Bulk Import Architecture

This document describes the internal architecture for bulk importing documents
into OpenContracts via ZIP files. For user-facing documentation (ZIP structure,
CSV schemas, security limits), see
[Bulk ZIP Import](../upload_methods/bulk_zip_import.md).

## Import Process Architecture

### Phase 1: Validation

The ZIP file is validated for security constraints before any processing:

```python
from opencontractserver.utils.zip_security import validate_zip_for_import

manifest = validate_zip_for_import(zip_file_path)
if manifest.validation_errors:
    raise ValidationError(manifest.validation_errors)
```

The validation produces a `ZipManifest` containing:
- List of valid files to process
- List of skipped files (with reasons)
- Folder paths to create
- Relationship file path (if present)
- Validation errors

### Phase 2: Folder Creation

Folder structure is created in a single transaction:

```python
from opencontractserver.corpuses.corpus_objs_service import CorpusObjsService

folder_map, created, reused, error = CorpusObjsService.create_folder_structure_from_paths(
    user=user,
    corpus=corpus,
    folder_paths=manifest.folder_paths,
    target_folder=target_folder,  # optional
)
```

Existing folders are reused, not duplicated.

### Phase 3: Document Import

Documents are imported with the following logic:
1. Check if path already exists in corpus
2. If exists: create new version (upversion)
3. If new: create document and DocumentPath

A `document_path_map` is built during this phase for relationship processing:

```python
document_path_map: dict[str, Document] = {}
# Key: normalized zip path (e.g., "contracts/agreement.pdf")
# Value: Document object
```

### Phase 4: Relationship Creation

If a `relationships.csv` file is present:

```python
from opencontractserver.utils.relationship_file_parser import parse_relationship_file

with zipfile.ZipFile(zip_path) as zf:
    csv_content = zf.read(manifest.relationship_file)

parsed = parse_relationship_file(csv_content, manifest.relationship_file)
if parsed.is_valid:
    stats = create_relationships_from_parsed(
        corpus=corpus,
        user=user,
        document_path_map=document_path_map,
        parsed_relationships=parsed.relationships,
    )
```

Relationships are created using `corpus.ensure_label_and_labelset()` for atomic label/labelset creation with `LabelType.RELATIONSHIP_LABEL`.

## Task Result Schema

The Celery task returns a detailed result dict:

```python
{
    "job_id": "task-uuid",
    "completed": True,
    "success": True,
    "validation_passed": True,
    "validation_errors": [],
    "total_files_in_zip": 17,
    "files_processed": 15,
    "files_skipped_hidden": 2,
    "files_skipped_type": 1,
    "files_skipped_size": 0,
    "files_skipped_path": 0,
    "files_errored": 0,
    "files_upversioned": 3,
    "folders_created": 5,
    "folders_reused": 2,
    "metadata_file_found": True,
    "metadata_applied": 12,
    "relationships_file_found": True,
    "relationships_created": 8,
    "relationships_skipped": 1,
    "relationship_errors": ["Source document not found: missing.pdf"],
    "document_ids": ["uuid1", "uuid2", ...],
    "errors": [],
    "skipped_oversized": [],
    "upversioned_paths": ["/docs/existing.pdf"],
}
```

## Frontend Components

### BulkImportModal

Located at `frontend/src/components/widgets/modals/BulkImportModal.tsx`

The modal provides:
1. **Confirmation step**: Warning about bulk import being irreversible
2. **Upload step**: Drag-and-drop file selection
3. **Progress step**: Upload progress indicator

### FolderToolbar Integration

The Upload button has a dropdown with two options:
- **Upload Documents**: Standard multi-file upload
- **Bulk Import (ZIP)**: Opens BulkImportModal

## File Locations

| Component | Path |
|-----------|------|
| ZIP Security | `opencontractserver/utils/zip_security.py` |
| Relationship Parser | `opencontractserver/utils/relationship_file_parser.py` |
| Metadata Parser | `opencontractserver/utils/metadata_file_parser.py` |
| Import Task | `opencontractserver/tasks/import_tasks.py` |
| GraphQL Mutation | `config/graphql/mutations.py` (ImportZipToCorpus) |
| Frontend Modal | `frontend/src/components/widgets/modals/BulkImportModal.tsx` |
| Frontend Mutation | `frontend/src/graphql/mutations.ts` |

## Error Handling

### Validation Errors (Import Blocked)

- Too many files in ZIP
- ZIP exceeds total size limit
- Suspected zip bomb (high compression ratio)
- Path traversal detected
- Invalid ZIP format

### Processing Errors (Partial Success)

- Individual file too large (skipped)
- Unsupported file type (skipped)
- File extraction error (skipped)
- Relationship source/target not found (skipped)

### Graceful Degradation

- Malformed `relationships.csv` does not fail the import
- Missing documents in relationships are logged and skipped
- The import succeeds with available documents

## Testing

### Unit Tests

```bash
# Relationship parser tests
docker compose -f test.yml run django pytest opencontractserver/tests/test_relationship_file_parser.py -v

# Metadata parser tests
docker compose -f test.yml run django pytest opencontractserver/tests/test_metadata_file_parser.py -v

# ZIP security tests
docker compose -f test.yml run django pytest opencontractserver/tests/test_zip_security.py -v
```

### Integration Tests

```bash
# Full import integration tests (includes relationship and metadata tests)
docker compose -f test.yml run django pytest opencontractserver/tests/test_zip_import_integration.py -v

# Run only relationship tests
docker compose -f test.yml run django pytest opencontractserver/tests/test_zip_import_integration.py::TestRelationshipFileImport -v

# Run only metadata tests
docker compose -f test.yml run django pytest opencontractserver/tests/test_zip_import_integration.py::TestMetadataFileImport -v
```
