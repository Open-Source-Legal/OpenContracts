# Document Versioning Philosophy

## First Principles (Laws of Physics)

### Foundational Principles

1. **Separation of Concerns**: Content is not Location
   - Content Tree (Document): "What is this file's content?"
   - Path Tree (DocumentPath): "Where has this file lived?"

2. **Immutability**: Trees only grow, never shrink
   - Changes create new nodes linked to old ones
   - Old nodes never modified or deleted
   - Foundation for complete audit trails

3. **Global Content Deduplication**: One Document per unique hash
   - Content exists once across entire system
   - All uses point to single record

4. **Precise State Definitions**:
   - Document `is_current`: Latest content version in tree
   - DocumentPath `is_current`: Latest lifecycle state

## Rules Governing the System

### Content Tree Rules
- **C1**: New Document only when hash first seen globally
- **C2**: Updates create child nodes of previous version
- **C3**: Only one current Document per version tree

### Path Tree Rules
- **P1**: Every lifecycle event creates new node
- **P2**: New nodes are children of previous state
- **P3**: Only current filesystem state is `is_current=True`
- **P4**: One active path per `(corpus, path)` tuple
- **P5**: Version number increments only on content changes
- **P6**: Folder deletion sets `folder=NULL`

### Interaction Rules
- **I1**: Corpuses share Documents but have independent paths
- **Q1**: Content "truly deleted" when no active paths point to it

## Architecture Summary

```python
# Content Tree - What is this file?
class Document(TreeNode):
    version_tree_id = UUID  # Groups versions
    is_current = Boolean    # Latest in tree
    parent → previous_version

# Path Tree - Where has this file lived?
class DocumentPath(TreeNode):
    document → specific_version
    corpus = ForeignKey
    path = CharField
    version_number = Integer
    is_deleted = Boolean
    is_current = Boolean
    parent → previous_state

# CorpusDocumentFolder unchanged
# Simple linking, DocumentPath handles versioning
```

## Operations Create Trees

```
Import v1.pdf:
  Document(1, parent=None) + DocumentPath(1, parent=None)
    ↓
Move to /new/:
  Document(1) unchanged + DocumentPath(2, parent=1)
    ↓
Update content:
  Document(2, parent=1) + DocumentPath(3, parent=2)
    ↓
Delete:
  Document(2) unchanged + DocumentPath(4, parent=3, deleted=True)
    ↓
Restore:
  Document(2) unchanged + DocumentPath(5, parent=4, deleted=False)
```

## Key Benefits

✅ **Complete Audit Trail** - Every action preserved forever
✅ **Time Travel** - Reconstruct any historical state
✅ **Undelete** - Soft deletes enable recovery
✅ **Global Deduplication** - Process content only once
✅ **Clean Separation** - Content independent from location
✅ **Immutability** - Historical data never lost
✅ **Corpus Independence** - Documents remain shareable

## Implementation Checklist

### Phase 1: Models
- [ ] Add TreeNode to Document model
- [ ] Create DocumentPath model
- [ ] Add unique constraints

### Phase 2: Operations
- [ ] Import logic with dual trees
- [ ] Move operation (path only)
- [ ] Delete operation (soft delete)
- [ ] Restore operation

### Phase 3: Queries
- [ ] Current filesystem view
- [ ] Content history traversal
- [ ] Path history traversal
- [ ] Time-travel reconstruction

### Phase 4: Migration
- [ ] Initialize Document trees
- [ ] Create DocumentPath from existing data
- [ ] Preserve all relationships

### Phase 5: Integration
- [ ] GraphQL schema updates
- [ ] Frontend version selector
- [ ] Path history viewer
- [ ] Time-travel UI

## Testing Priorities

1. **Rule Enforcement** - All rules validated
2. **Tree Integrity** - Parent-child relationships correct
3. **State Management** - `is_current` flags accurate
4. **Cross-Corpus** - Independence maintained
5. **Performance** - Tree queries < 500ms

## Related Documentation

- [Full Technical Specification](./document_versioning_and_bulk_import.md)
- [Implementation Plan](./dual_tree_implementation_plan.md)
- [Document Model](../../opencontractserver/documents/models.py)
- [Corpus Models](../../opencontractserver/corpuses/models.py)
