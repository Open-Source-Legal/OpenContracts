# Versioning Query Conventions for Annotations and Search

## Overview

This document defines the architectural conventions for how annotations, vector search, and document processing interact with the dual-tree versioning system. These conventions ensure consistent behavior across all query operations while maintaining historical accuracy and corpus independence.

## Fundamental Principles

### P1: Version Immutability
Every annotation, embedding, and processing result is permanently tied to a specific Document version. These artifacts never migrate between versions, preserving complete historical accuracy.

### P2: Default to Current
All queries default to the latest version (`Document.is_current=True`) unless a specific version is explicitly requested. This represents the "working set" users interact with.

### P3: Corpus Context Primacy
Within a corpus context, only documents with active filesystem paths are considered. A document may be globally current but locally deleted in a specific corpus.

## Annotation Conventions

### A1: Annotation Version Binding
- **Rule**: Annotations are created against a specific `document_id` which IS a version
- **Implication**: When a document is updated, old annotations remain with old version
- **Rationale**: Page numbers, bounding boxes, and content may change between versions

### A2: Structural vs Corpus Annotations

#### Structural Annotations (Global Scope)
- **Created**: During document parsing, tied to specific version
- **Immutable**: Never change after creation
- **Versioning**: Each document version has its own structural annotations
- **Query Pattern**:
  ```python
  # Get structural annotations for current version
  Annotation.objects.filter(
      document__version_tree_id=version_tree_id,
      document__is_current=True,
      structural=True
  )
  ```

#### Corpus Annotations (Corpus Scope)
- **Created**: By users/analyses within corpus context
- **Version-Specific**: Tied to the document version active when created
- **Visibility**: Only shown if document has active path in corpus
- **Query Pattern**:
  ```python
  # Get corpus annotations for current version with active path
  Annotation.objects.filter(
      document__is_current=True,
      corpus_id=corpus_id,
      structural=False
  ).exclude(
      # Exclude if document deleted in this corpus
      document__documentpath__corpus_id=corpus_id,
      document__documentpath__is_current=True,
      document__documentpath__is_deleted=True
  )
  ```

### A3: Query Defaults

#### Current Version Query (Default)
```python
def get_document_annotations(document_path, corpus_id, user):
    # Find current document at this path
    current_path = DocumentPath.objects.get(
        corpus_id=corpus_id,
        path=document_path,
        is_current=True,
        is_deleted=False
    )

    # Get annotations for current version
    return Annotation.objects.filter(
        document_id=current_path.document_id,
        corpus_id=corpus_id
    )
```

#### Historical Version Query (Explicit)
```python
def get_document_annotations_at_version(document_id, corpus_id, user):
    # Direct query for specific version
    return Annotation.objects.filter(
        document_id=document_id,  # Specific version
        corpus_id=corpus_id
    )
```

### A4: Deletion Behavior
- **Soft Delete**: When document deleted from corpus, annotations remain but are hidden
- **Restore**: When document restored, previous annotations become visible again
- **True Delete**: Annotations only removed when no corpus contains the document

## Vector Search Conventions

### V1: Embedding Version Binding
- **Rule**: Each Document version has its own embeddings
- **Storage**: Embeddings stored with specific document_id
- **Immutable**: Embeddings never change after generation

### V2: Search Scope Rules

#### Default Search (Current Only)
```python
def vector_search(query, corpus_id):
    # Build base queryset
    qs = Annotation.objects.filter(
        document__is_current=True  # Only current versions
    )

    if corpus_id:
        # Further filter by corpus active paths
        qs = qs.filter(corpus_id=corpus_id).exclude(
            document__documentpath__corpus_id=corpus_id,
            document__documentpath__is_current=True,
            document__documentpath__is_deleted=True
        )

    # Apply vector similarity search
    return qs.search_by_embedding(query_vector)
```

#### Cross-Version Search (Special Case)
```python
def vector_search_all_versions(query, corpus_id):
    # Search across all versions (for finding similar historical content)
    qs = Annotation.objects.filter(
        document__version_tree_id__in=active_trees
    )
    # ... apply vector search
```

### V3: Corpus Filtering
- **Active Documents Only**: Exclude documents with `is_deleted=True` paths
- **Path State Check**: Always verify DocumentPath state before including in results
- **Performance**: Use EXISTS subquery for efficient filtering

## Processing Pipeline Conventions

### PP1: Pipeline Version Targeting
- **Input**: Pipelines receive specific document_id (version)
- **Output**: Results tied to that specific version
- **No Migration**: Results don't carry forward to new versions

### PP2: Import and Update Flow
```python
def import_document(corpus, path, content, user):
    # Create or update document (versioning handled here)
    doc, status, path_record = import_document(...)

    if status in ['created', 'updated']:
        # Process the NEW version
        parse_document.delay(doc.id)  # Specific version
        generate_embeddings.delay(doc.id)  # Specific version
        generate_thumbnail.delay(doc.id)  # Specific version

    return doc
```

### PP3: Reprocessing Rules
- **New Version**: Always process from scratch
- **No Inheritance**: Don't copy results from previous versions
- **Rationale**: Content may have changed, models may have improved

## Query Patterns

### Pattern 1: Get Current Annotations for Path
```python
def get_current_annotations_for_path(corpus_id, path):
    # Step 1: Find current document at path
    current_path = DocumentPath.objects.filter(
        corpus_id=corpus_id,
        path=path,
        is_current=True,
        is_deleted=False
    ).first()

    if not current_path:
        return Annotation.objects.none()

    # Step 2: Get annotations for that version
    return Annotation.objects.filter(
        document_id=current_path.document_id,
        corpus_id=corpus_id
    )
```

### Pattern 2: Get All Versions' Annotations
```python
def get_all_versions_annotations(corpus_id, path):
    # Get all document paths (including historical)
    all_paths = DocumentPath.objects.filter(
        corpus_id=corpus_id,
        path=path
    ).values_list('document_id', flat=True)

    # Get annotations for all versions
    return Annotation.objects.filter(
        document_id__in=all_paths,
        corpus_id=corpus_id
    ).order_by('document__created')
```

### Pattern 3: Time Travel Query
```python
def get_annotations_at_time(corpus_id, path, timestamp):
    # Find document state at timestamp
    path_at_time = DocumentPath.objects.filter(
        corpus_id=corpus_id,
        path=path,
        created__lte=timestamp
    ).order_by('-created').first()

    if not path_at_time or path_at_time.is_deleted:
        return Annotation.objects.none()

    # Get annotations created before timestamp
    return Annotation.objects.filter(
        document_id=path_at_time.document_id,
        corpus_id=corpus_id,
        created__lte=timestamp
    )
```

## Implementation Checklist

### 1. AnnotationQueryOptimizer Updates
- [ ] Add version-aware query methods
- [ ] Update `get_document_annotations` to check `is_current`
- [ ] Add corpus path deletion checks
- [ ] Create `get_annotations_for_path` method

### 2. Vector Store Updates
- [ ] Filter base queryset to current documents
- [ ] Add DocumentPath deletion checks
- [ ] Update `_build_base_queryset` method
- [ ] Add version parameter to search methods

### 3. GraphQL Updates
- [ ] Add `version` parameter to annotation queries
- [ ] Default to current version when not specified
- [ ] Update resolvers to use version-aware methods
- [ ] Add time-travel query support

### 4. Frontend Updates
- [ ] Show version indicator in UI
- [ ] Add version selector for historical viewing
- [ ] Update annotation queries to handle versions
- [ ] Clear indication when viewing non-current version

## Migration Considerations

### Existing Data
1. All existing annotations are already tied to specific document versions
2. After dual-tree migration, these will be on `is_current=True` documents
3. No data migration needed for annotations themselves

### Backward Compatibility
1. Existing queries passing `document_id` continue to work
2. New version-aware methods are additive
3. GraphQL schema changes are backward compatible

## Performance Optimizations

### Indexes Required
```sql
-- For efficient current document filtering
CREATE INDEX idx_document_version_current
ON documents(version_tree_id, is_current)
WHERE is_current = TRUE;

-- For corpus path state queries
CREATE INDEX idx_docpath_corpus_current_deleted
ON document_paths(corpus_id, path, is_current, is_deleted)
WHERE is_current = TRUE AND is_deleted = FALSE;

-- For annotation version queries
CREATE INDEX idx_annotation_doc_corpus
ON annotations(document_id, corpus_id);
```

### Query Optimization Tips
1. Use EXISTS subqueries for path state checks
2. Prefetch document and path relationships
3. Cache current version lookups
4. Use select_related for document version info

## Testing Strategy

### Test Scenarios
1. **Version Update**: Annotations don't carry forward
2. **Soft Delete**: Annotations hidden but not lost
3. **Restore**: Previous annotations reappear
4. **Cross-Corpus**: Independent annotation visibility
5. **Time Travel**: Historical state reconstruction
6. **Search Scope**: Only current versions in results

### Edge Cases
1. Document current globally but deleted locally
2. Multiple versions with same content hash
3. Annotations on documents with no current version
4. Search across version boundaries

## Conclusion

These conventions ensure that:
1. Historical accuracy is preserved
2. Users work with current content by default
3. Corpus independence is maintained
4. Performance remains optimal
5. The system is predictable and consistent

The key insight is that **annotations and embeddings are version-specific artifacts** that don't migrate. This simplifies reasoning about the system and ensures data integrity across version changes.
