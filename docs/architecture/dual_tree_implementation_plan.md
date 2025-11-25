# Dual-Tree Architecture Implementation Plan

## First Principles (Laws of Physics)

### Foundational Principles

1. **Separation of Concerns**: Content is not Location. A document's content and its place in a filesystem are two independent concerns.
   - The Content Tree (`Document`) answers: "What is this file's content, and how has it changed?"
   - The Path Tree (`DocumentPath`) answers: "Where has this file lived, and what has happened to it?"

2. **Immutability as Goal**: Trees only grow. To "change" something, create a new node representing the new state and link it to the old state. Old nodes are never updated or deleted. This provides our audit trail and time-travel capabilities.

3. **Global Content Deduplication**: A piece of content (defined by its hash) exists only once as a Document record. All uses of that content, across all corpuses and paths, point to this single record.

4. **The Meaning of "Current"**:
   - A Document is `is_current` if it's the latest known version of that content
   - A DocumentPath is `is_current` if it represents the latest state of a file's lifecycle

### Rules for Content Tree (Document)

- **Rule C1 (Creation)**: A new Document node is created only when a content hash is seen for the first time anywhere in the system
- **Rule C2 (Versioning)**: If new content updates an existing file, the new Document node is created as a child of the Document representing the previous content
- **Rule C3 (State)**: Only one Document in a version tree (sharing a `version_tree_id`) can have `is_current=True`

### Rules for Path Tree (DocumentPath)

- **Rule P1 (Creation)**: A new DocumentPath node is created for every lifecycle event:
  - File first imported
  - File content updated to new version
  - File moved or renamed
  - File deleted (soft delete)
  - File restored
- **Rule P2 (History)**: New DocumentPath nodes are children of the previous state node
- **Rule P3 (State)**: Only nodes representing current filesystem state have `is_current=True`
- **Rule P4 (Uniqueness)**: Only one active (`is_current=True, is_deleted=False`) DocumentPath can exist per `(corpus, path)` tuple
- **Rule P5 (Versioning)**: `version_number` increments only when pointing to new Document version
- **Rule P6 (Folder Handling)**: Folder deletion creates new DocumentPath with `folder=NULL`

### Interaction Rules

- **Rule I1 (Cross-Corpus)**: Multiple corpuses sharing same Document have independent DocumentPath trees
- **Rule Q1 (True Deletion)**: Content is "truly deleted" when no active DocumentPath in corpus points to it

## Implementation Plan

### Phase 1: Data Models (Week 1, Days 1-2)

#### 1.1 Document Model Enhancement
```python
class Document(TreeNode, BaseOCModel, HasEmbeddingMixin):
    """Content Tree - tracks what content exists and how it evolved"""

    # Existing fields remain unchanged

    # New versioning fields
    version_tree_id = models.UUIDField(
        db_index=True,
        help_text="Groups all content versions of same logical document"
    )
    is_current = models.BooleanField(
        default=True,
        db_index=True,
        help_text="True for newest content in this version tree"
    )

    # TreeNode provides: parent, tree_depth, tree_path, tree_ordering

    class Meta:
        constraints = [
            # Enforce Rule C3
            models.UniqueConstraint(
                fields=['version_tree_id'],
                condition=models.Q(is_current=True),
                name='one_current_per_version_tree'
            )
        ]
```

#### 1.2 DocumentPath Model Creation
```python
class DocumentPath(TreeNode, BaseOCModel):
    """Path Tree - tracks where documents lived and what happened to them"""

    document = models.ForeignKey(
        Document,
        on_delete=models.PROTECT,  # Never delete Documents
        help_text="Specific content version this path points to"
    )

    corpus = models.ForeignKey(
        Corpus,
        on_delete=models.CASCADE,
        help_text="Corpus owning this path"
    )

    folder = models.ForeignKey(
        CorpusFolder,
        null=True,
        on_delete=models.SET_NULL,  # Rule P6
        help_text="Current folder (null if folder deleted)"
    )

    path = models.CharField(
        max_length=1024,
        db_index=True,
        help_text="Full path in corpus filesystem"
    )

    version_number = models.IntegerField(
        help_text="Content version number (Rule P5)"
    )

    is_deleted = models.BooleanField(
        default=False,
        help_text="Soft delete flag"
    )

    is_current = models.BooleanField(
        default=True,
        db_index=True,
        help_text="True for current filesystem state"
    )

    # TreeNode provides: parent (previous state)

    class Meta:
        constraints = [
            # Enforce Rule P4
            models.UniqueConstraint(
                fields=['corpus', 'path'],
                condition=models.Q(is_current=True, is_deleted=False),
                name='unique_active_path_per_corpus'
            )
        ]
        indexes = [
            models.Index(fields=['corpus', 'is_current', 'is_deleted']),
            models.Index(fields=['document', 'corpus']),
        ]
```

### Phase 2: Core Operations (Week 1, Days 3-5)

#### 2.1 Import Operation
```python
def calculate_content_version(document):
    """
    Calculate the version number of a document by counting
    ancestors in the content tree.
    """
    count = 1
    current = document
    while current.parent_id:
        count += 1
        current = current.parent
    return count

def import_document(corpus, path, content, user, folder=None):
    """
    Implements interaction rules for import.
    Returns: (document, status, path_record)
    """
    content_hash = compute_sha256(content)

    with transaction.atomic():
        # Step 1: Check Content Tree (Rules C1, C2)
        existing_doc = Document.objects.filter(
            pdf_file_hash=content_hash
        ).first()

        # Step 2: Check Path Tree (Rules P1, P4)
        current_path = DocumentPath.objects.filter(
            corpus=corpus,
            path=path,
            is_current=True,
            is_deleted=False
        ).select_for_update().first()

        if current_path:
            # Path exists - check if content changed
            if current_path.document.pdf_file_hash == content_hash:
                return current_path.document, 'unchanged', current_path

            # Content changed - apply Rule C2
            old_doc = current_path.document

            if existing_doc:
                # Content exists elsewhere
                new_doc = existing_doc
            else:
                # Create new version (Rule C2)
                Document.objects.filter(
                    version_tree_id=old_doc.version_tree_id
                ).update(is_current=False)  # Rule C3

                new_doc = Document.objects.create(
                    # Copy fields from old_doc
                    version_tree_id=old_doc.version_tree_id,
                    parent=old_doc,  # Rule C2
                    is_current=True,
                    pdf_file_hash=content_hash,
                    # ... other fields
                )

            # Apply Rules P1, P2
            current_path.is_current = False
            current_path.save()

            new_path = DocumentPath.objects.create(
                document=new_doc,
                corpus=corpus,
                folder=folder or current_path.folder,
                path=path,
                version_number=current_path.version_number + 1,  # Rule P5
                parent=current_path,  # Rule P2
                is_current=True
            )

            return new_doc, 'updated', new_path

        else:
            # New path
            if existing_doc:
                # Content exists elsewhere (Rule I1)
                doc = existing_doc
                # Calculate actual content version from tree depth
                version = doc.get_ancestors(include_self=True).count()
                # Alternative if TreeNode doesn't provide get_ancestors:
                # version = calculate_content_version(doc)
            else:
                # Brand new content (Rule C1)
                tree_id = uuid.uuid4()
                doc = Document.objects.create(
                    pdf_file_hash=content_hash,
                    version_tree_id=tree_id,
                    is_current=True,
                    parent=None,  # Root of content tree
                    # ... other fields
                )
                version = 1  # First version of new content

            # Create root of path tree (Rule P1)
            new_path = DocumentPath.objects.create(
                document=doc,
                corpus=corpus,
                folder=folder,
                path=path,
                version_number=version,
                parent=None,  # Root of path tree
                is_current=True
            )

            return doc, 'created', new_path
```

#### 2.2 Move Operation
```python
def move_document(corpus, old_path, new_path, new_folder=None):
    """Move document - creates new DocumentPath, Document unchanged"""

    current = DocumentPath.objects.get(
        corpus=corpus,
        path=old_path,
        is_current=True,
        is_deleted=False
    )

    with transaction.atomic():
        # Apply Rule P3
        current.is_current = False
        current.save()

        # Apply Rules P1, P2
        return DocumentPath.objects.create(
            document=current.document,  # Same content
            corpus=corpus,
            folder=new_folder or current.folder,
            path=new_path,
            version_number=current.version_number,  # Rule P5 - no increment
            parent=current,  # Rule P2
            is_current=True
        )
```

#### 2.3 Delete Operation
```python
def delete_document(corpus, path):
    """Soft delete - creates deleted DocumentPath"""

    current = DocumentPath.objects.get(
        corpus=corpus,
        path=path,
        is_current=True,
        is_deleted=False
    )

    with transaction.atomic():
        current.is_current = False
        current.save()

        return DocumentPath.objects.create(
            document=current.document,
            corpus=corpus,
            folder=current.folder,
            path=current.path,
            version_number=current.version_number,  # Rule P5
            parent=current,  # Rule P2
            is_deleted=True,  # Soft delete
            is_current=True
        )
```

#### 2.4 Restore Operation
```python
def restore_document(corpus, path):
    """Restore deleted document"""

    deleted = DocumentPath.objects.get(
        corpus=corpus,
        path=path,
        is_current=True,
        is_deleted=True
    )

    with transaction.atomic():
        deleted.is_current = False
        deleted.save()

        return DocumentPath.objects.create(
            document=deleted.document,
            corpus=corpus,
            folder=deleted.folder,
            path=deleted.path,
            version_number=deleted.version_number,
            parent=deleted,
            is_deleted=False,  # Not deleted
            is_current=True
        )
```

### Phase 3: Query Infrastructure (Week 2, Days 1-3)

#### 3.1 Current Filesystem View
```python
def get_current_filesystem(corpus):
    """Get current filesystem state"""
    return DocumentPath.objects.filter(
        corpus=corpus,
        is_current=True,
        is_deleted=False
    ).select_related('document', 'folder')
```

#### 3.2 Content History
```python
def get_content_history(document):
    """Traverse content tree upward"""
    history = []
    current = document
    while current:
        history.append(current)
        current = current.parent
    return reversed(history)  # Oldest to newest
```

#### 3.3 Path History
```python
def get_path_history(document_path):
    """Traverse path tree upward"""
    history = []
    current = document_path
    while current:
        history.append({
            'timestamp': current.created_at,
            'path': current.path,
            'version': current.version_number,
            'deleted': current.is_deleted,
            'action': determine_action(current, current.parent)
        })
        current = current.parent
    return reversed(history)
```

#### 3.4 Time Travel
```python
def get_filesystem_at_time(corpus, timestamp):
    """Reconstruct filesystem at specific time"""

    # For each unique path, find the most recent DocumentPath before timestamp
    from django.db.models import OuterRef, Subquery

    newest_before_time = DocumentPath.objects.filter(
        corpus=corpus,
        created_at__lte=timestamp,
        path=OuterRef('path')
    ).order_by('-created_at').values('id')[:1]

    return DocumentPath.objects.filter(
        id__in=Subquery(newest_before_time)
    ).exclude(is_deleted=True)
```

### Phase 4: Migrations (Week 2, Days 4-5)

#### 4.1 Migration Strategy

**Note**: Since CorpusDocumentFolder was never deployed to production, we can implement a clean migration without legacy concerns.

```python
def migrate_existing_data(apps, schema_editor):
    """
    Initialize dual-tree structure for existing documents.
    Note: CorpusDocumentFolder doesn't exist in production,
    so we create DocumentPath records from corpus.documents relationships.
    """
    Document = apps.get_model('documents', 'Document')
    DocumentPath = apps.get_model('documents', 'DocumentPath')
    Corpus = apps.get_model('corpuses', 'Corpus')

    # Step 1: Initialize Document trees
    for doc in Document.objects.all():
        doc.version_tree_id = uuid.uuid4()
        doc.is_current = True
        doc.parent = None  # All existing docs are roots
        doc.save()

    # Step 2: Create DocumentPath records from existing relationships
    for corpus in Corpus.objects.prefetch_related('documents'):
        for doc in corpus.documents.all():
            # Generate path from document title
            path = f"/{doc.title}"

            DocumentPath.objects.create(
                document=doc,
                corpus=corpus,
                folder=None,  # Root level by default
                path=path,
                version_number=1,  # All existing docs are v1
                parent=None,  # All are roots initially
                is_current=True,
                is_deleted=False
            )

    print(f"Migrated {Document.objects.count()} documents")
```

**Benefits of Clean Migration**:
- No legacy CorpusDocumentFolder to remove
- Simpler migration with less risk
- No need for verification phase
- Direct implementation of new architecture

### Phase 5: Testing (Week 3)

#### 5.1 Test Matrix
- **Content Tree Tests**:
  - Global deduplication (Rule C1)
  - Version creation (Rule C2)
  - Current flag management (Rule C3)

- **Path Tree Tests**:
  - Lifecycle events create nodes (Rule P1)
  - Parent-child relationships (Rule P2)
  - Current state management (Rule P3)
  - Unique active paths (Rule P4)
  - Version numbering (Rule P5)

- **Interaction Tests**:
  - Cross-corpus independence (Rule I1)
  - True deletion detection (Rule Q1)
  - Time travel queries
  - Complex workflows (import → move → update → delete → restore)

#### 5.2 Performance Testing (Critical)

##### Time-Travel Query Performance
```python
def test_time_travel_performance():
    """
    Test filesystem reconstruction performance at scale.
    Target: < 500ms for realistic datasets
    """
    # Create test dataset
    # - 10,000 documents
    # - 100,000 path records (avg 10 events per doc)
    # - 5 years of history

    corpus = create_test_corpus()
    generate_realistic_history(corpus, num_docs=10000)

    # Benchmark queries
    timestamps = [
        timezone.now() - timedelta(days=i*30)
        for i in range(60)  # 60 monthly snapshots
    ]

    for timestamp in timestamps:
        start = time.time()
        snapshot = get_filesystem_at_time(corpus, timestamp)
        duration = time.time() - start

        assert duration < 0.5, f"Query took {duration}s, target < 0.5s"
        assert snapshot.count() > 0
```

##### Performance Optimization Strategy
If time-travel queries exceed 500ms threshold:

1. **Option A: Add Strategic Indexes**
```python
class DocumentPath(TreeNode, BaseOCModel):
    class Meta:
        indexes = [
            # Composite index for time-travel
            models.Index(
                fields=['corpus', 'path', 'created_at', 'is_deleted'],
                name='idx_time_travel'
            ),
        ]
```

2. **Option B: Materialized View (PostgreSQL)**
```sql
CREATE MATERIALIZED VIEW corpus_filesystem_snapshots AS
WITH RECURSIVE snapshots AS (
    -- Complex CTE to pre-compute monthly snapshots
)
REFRESH MATERIALIZED VIEW CONCURRENTLY corpus_filesystem_snapshots;
```

3. **Option C: Summary Cache Table**
```python
class FilesystemSnapshot(models.Model):
    """Pre-computed filesystem states at regular intervals."""
    corpus = models.ForeignKey(Corpus)
    timestamp = models.DateTimeField()
    snapshot_data = models.JSONField()  # Cached state

    class Meta:
        unique_together = ['corpus', 'timestamp']
        indexes = [
            models.Index(fields=['corpus', 'timestamp'])
        ]
```

**Testing Requirements**:
- Benchmark with 1K, 10K, 100K, 1M path records
- Test with varying tree depths (1-20 levels)
- Measure query time distribution (p50, p95, p99)
- Profile memory usage during queries
- Test concurrent time-travel queries

### Phase 6: GraphQL Integration (Week 3-4)

#### 6.1 Schema Updates
```graphql
type Document {
    # Existing fields

    # Version info
    versionNumber: Int!
    versionHistory: [Document!]!
    isCurrentVersion: Boolean!

    # Path info for this corpus
    currentPath: String
    pathHistory: [DocumentPath!]!
}

type DocumentPath {
    id: ID!
    path: String!
    versionNumber: Int!
    isDeleted: Boolean!
    isCurrent: Boolean!
    document: Document!
    createdAt: DateTime!
    action: PathAction!
}

enum PathAction {
    CREATED
    UPDATED
    MOVED
    DELETED
    RESTORED
}
```

### Phase 7: Frontend Integration (Week 4)

#### 7.1 UI Components
- **Version Selector**: Browse content versions
- **Path History**: View file's journey
- **Filesystem Timeline**: Scrub through time
- **Restore UI**: Undelete files
- **Audit Trail**: Complete history view

## Success Metrics

1. **Correctness**: All rules enforced, no violations
2. **Performance**: Time-travel queries < 500ms
3. **Storage**: Path tree overhead < 10% of content size
4. **Usability**: Users can easily understand and navigate history

## Risk Mitigation

1. **Race Conditions**: Use SELECT FOR UPDATE on path queries
2. **Migration Failures**: Comprehensive rollback plan
3. **Performance**: Add strategic indexes, consider materialized views for time-travel
4. **Complexity**: Clear documentation, visual diagrams

This implementation directly translates the first principles into working code, maintaining the conceptual clarity throughout.
