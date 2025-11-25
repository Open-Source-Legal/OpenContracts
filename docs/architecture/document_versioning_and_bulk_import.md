# Document Versioning & Bulk Import Architecture

## Executive Summary

OpenContracts implements a **dual-tree versioning system** based on first principles of immutability and separation of concerns. The Content Tree (Document) tracks what files contain and how content evolves. The Path Tree (DocumentPath) tracks where files live and their lifecycle events. Trees only grow—they never shrink—providing complete audit trails and time-travel capabilities.

## First Principles (Laws of Physics)

### Foundational Principles

1. **Separation of Concerns**: Content is not Location
   - Content Tree answers: "What is this file's content, and how has it changed?"
   - Path Tree answers: "Where has this file lived, and what has happened to it?"

2. **Immutability**: Trees only grow, never shrink
   - Changes create new nodes linked to old ones
   - Old nodes never modified or deleted
   - Foundation for audit trails and time-travel

3. **Global Content Deduplication**: One Document per unique hash
   - Content exists once across entire system
   - All uses point to single record

4. **Precise State Definitions**:
   - Document `is_current`: Latest version of content in its tree
   - DocumentPath `is_current`: Latest state in file's lifecycle

## Rules Governing the System

### Content Tree Rules (Document)

- **Rule C1 (Creation)**: New Document created only when content hash seen for first time globally
- **Rule C2 (Versioning)**: Updates create child nodes linking to previous content version
- **Rule C3 (State)**: Only one Document per version_tree_id can have `is_current=True`

### Path Tree Rules (DocumentPath)

- **Rule P1 (Creation)**: New DocumentPath created for every lifecycle event:
  - File first imported
  - File content updated
  - File moved/renamed
  - File deleted (soft)
  - File restored
- **Rule P2 (History)**: New nodes are children of previous state
- **Rule P3 (State)**: Only current filesystem state has `is_current=True`
- **Rule P4 (Uniqueness)**: One active path per `(corpus, path)` tuple
- **Rule P5 (Versioning)**: `version_number` increments only on content changes
- **Rule P6 (Folders)**: Folder deletion sets `folder=NULL`, creates new record

### Interaction Rules

- **Rule I1 (Cross-Corpus)**: Corpuses sharing content have independent path trees
- **Rule Q1 (True Deletion)**: Content "truly deleted" when no active paths point to it

## Data Models

### Document Model (Content Tree)

```python
class Document(TreeNode, BaseOCModel, HasEmbeddingMixin):
    """
    Content Tree - tracks what content exists and how it evolved.
    Inherits from TreeNode for version history.
    """

    # ALL EXISTING FIELDS REMAIN UNCHANGED

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

    # TreeNode provides: parent (previous version), tree_depth, tree_path

    class Meta:
        constraints = [
            # Enforce Rule C3: One current per tree
            models.UniqueConstraint(
                fields=['version_tree_id'],
                condition=models.Q(is_current=True),
                name='one_current_per_version_tree'
            )
        ]
```

### DocumentPath Model (Path Tree)

```python
class DocumentPath(TreeNode, BaseOCModel):
    """
    Path Tree - tracks where documents lived and their lifecycle.
    Every operation creates a new immutable record.
    """

    document = models.ForeignKey(
        Document,
        on_delete=models.PROTECT,  # Never delete Documents
        help_text="Specific content version this path points to"
    )

    corpus = models.ForeignKey(
        Corpus,
        on_delete=models.CASCADE
    )

    folder = models.ForeignKey(
        CorpusFolder,
        null=True,
        on_delete=models.SET_NULL,  # Rule P6
        help_text="Current folder (null if deleted)"
    )

    path = models.CharField(
        max_length=1024,
        db_index=True,
        help_text="Full filesystem path"
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

    # TreeNode provides: parent (previous state in path tree)

    class Meta:
        constraints = [
            # Enforce Rule P4: Unique active paths
            models.UniqueConstraint(
                fields=['corpus', 'path'],
                condition=models.Q(is_current=True, is_deleted=False),
                name='unique_active_path_per_corpus'
            )
        ]
```

## Core Operations (Following the Rules)

### Import Document

**Action: Import File_A with content_A to /path/a in Corpus_1**

```python
def calculate_content_version(document):
    """
    Calculate the actual version number of a document
    by counting its position in the content tree.
    """
    count = 1
    current = document
    while current.parent_id:
        count += 1
        current = current.parent
    return count

def import_document(corpus, path, content, user, folder=None):
    content_hash = compute_sha256(content)

    with transaction.atomic():
        # 1. Check Content Tree (Rules C1, C2)
        existing_doc = Document.objects.filter(
            pdf_file_hash=content_hash
        ).first()

        # 2. Check Path Tree (Rule P4)
        current_path = DocumentPath.objects.filter(
            corpus=corpus,
            path=path,
            is_current=True,
            is_deleted=False
        ).select_for_update().first()

        if current_path:
            # Path exists - is content different?
            if current_path.document.pdf_file_hash == content_hash:
                return current_path.document, 'unchanged', current_path

            # Content changed - create new version
            old_doc = current_path.document

            if not existing_doc:
                # Apply Rule C2: Create child in content tree
                Document.objects.filter(
                    version_tree_id=old_doc.version_tree_id
                ).update(is_current=False)  # Rule C3

                new_doc = Document.objects.create(
                    version_tree_id=old_doc.version_tree_id,
                    parent=old_doc,  # Rule C2
                    is_current=True,
                    pdf_file_hash=content_hash,
                    # ... copy other fields
                )
            else:
                new_doc = existing_doc

            # Apply Rules P1, P2, P3
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
            if not existing_doc:
                # Apply Rule C1: Brand new content
                tree_id = uuid.uuid4()
                doc = Document.objects.create(
                    pdf_file_hash=content_hash,
                    version_tree_id=tree_id,
                    is_current=True,
                    parent=None,  # Root of content tree
                    # ... other fields
                )
                version = 1
            else:
                # Content exists elsewhere (Rule I1)
                doc = existing_doc
                # Get actual content version number
                version = calculate_content_version(doc)

            # Apply Rule P1: Create root of path tree
            new_path = DocumentPath.objects.create(
                document=doc,
                corpus=corpus,
                folder=folder,
                path=path,
                version_number=version,  # Actual content version
                parent=None,  # Root of path tree
                is_current=True
            )

            return doc, 'created', new_path
```

### Move Document

**Action: Move /path/a to /path/b**

```python
def move_document(corpus, old_path, new_path, new_folder=None):
    """
    Content unchanged, only path changes.
    Document tree untouched, new DocumentPath created.
    """
    current = DocumentPath.objects.get(
        corpus=corpus,
        path=old_path,
        is_current=True,
        is_deleted=False
    )

    with transaction.atomic():
        # Apply Rule P3: Update state
        current.is_current = False
        current.save()

        # Apply Rules P1, P2: Create child
        return DocumentPath.objects.create(
            document=current.document,  # Same content
            corpus=corpus,
            folder=new_folder or current.folder,
            path=new_path,
            version_number=current.version_number,  # Rule P5: no increment
            parent=current,  # Rule P2
            is_current=True
        )
```

### Delete Document

**Action: Delete /path/b**

```python
def delete_document(corpus, path):
    """
    Soft delete - content preserved, path marked deleted.
    """
    current = DocumentPath.objects.get(
        corpus=corpus,
        path=path,
        is_current=True,
        is_deleted=False
    )

    with transaction.atomic():
        current.is_current = False
        current.save()

        # Apply Rules P1, P2: Create deleted child
        return DocumentPath.objects.create(
            document=current.document,
            corpus=corpus,
            folder=current.folder,
            path=current.path,
            version_number=current.version_number,
            parent=current,
            is_deleted=True,  # Marked deleted
            is_current=True
        )
```

### Restore Document

**Action: Restore /path/b**

```python
def restore_document(corpus, path):
    """
    Undelete - create non-deleted child of deleted node.
    """
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
            is_deleted=False,  # Restored
            is_current=True
        )
```

## Querying the Trees

### Current Filesystem View

```python
def get_current_filesystem(corpus):
    """Get current filesystem state for a corpus."""
    return DocumentPath.objects.filter(
        corpus=corpus,
        is_current=True,
        is_deleted=False
    )
```

### Content History

```python
def get_content_history(document):
    """Traverse content tree upward to get version history."""
    history = []
    current = document
    while current:
        history.append(current)
        current = current.parent
    return reversed(history)  # Oldest to newest
```

### Path History

```python
def get_path_history(path_node):
    """Traverse path tree upward to get lifecycle history."""
    history = []
    current = path_node
    while current:
        history.append(current)
        current = current.parent
    return reversed(history)  # Oldest to newest
```

### Time Travel

```python
def get_filesystem_at_time(corpus, timestamp):
    """
    Reconstruct filesystem at specific point in time.
    For each unique path, find most recent node before timestamp.
    """
    from django.db.models import OuterRef, Subquery

    # Most recent path record before timestamp
    newest_before = DocumentPath.objects.filter(
        corpus=corpus,
        created_at__lte=timestamp,
        path=OuterRef('path')
    ).order_by('-created_at').values('id')[:1]

    return DocumentPath.objects.filter(
        id__in=Subquery(newest_before)
    ).exclude(is_deleted=True)
```

### True Deletion Check

```python
def is_truly_deleted(corpus, path, content_hash):
    """
    Apply Rule Q1: Content truly deleted when no active paths point to it.
    """
    # Is this path deleted?
    path_deleted = DocumentPath.objects.filter(
        corpus=corpus,
        path=path,
        is_current=True,
        is_deleted=True
    ).exists()

    if not path_deleted:
        return False

    # Does content exist elsewhere?
    content_exists = DocumentPath.objects.filter(
        corpus=corpus,
        document__pdf_file_hash=content_hash,
        is_current=True,
        is_deleted=False
    ).exists()

    return not content_exists
```

## Complete Example Workflow

Let's trace through a complete lifecycle:

```python
# 1. Import v1.pdf with content_A
doc1, status1, path1 = import_document(corpus, "/v1.pdf", content_A, user)
# Creates: Document(id=1, parent=None), DocumentPath(id=1, parent=None)

# 2. Move to /contracts/v1.pdf
path2 = move_document(corpus, "/v1.pdf", "/contracts/v1.pdf", contracts_folder)
# Creates: DocumentPath(id=2, parent=1, document=1)
# Document unchanged

# 3. Update with content_B
doc2, status2, path3 = import_document(corpus, "/contracts/v1.pdf", content_B, user)
# Creates: Document(id=2, parent=1), DocumentPath(id=3, parent=2, document=2)

# 4. Delete the file
path4 = delete_document(corpus, "/contracts/v1.pdf")
# Creates: DocumentPath(id=4, parent=3, is_deleted=True, document=2)

# 5. Restore the file
path5 = restore_document(corpus, "/contracts/v1.pdf")
# Creates: DocumentPath(id=5, parent=4, is_deleted=False, document=2)

# Now we can query:
# - Content history: [Document(1), Document(2)]
# - Path history: [Path(1), Path(2), Path(3), Path(4), Path(5)]
# - Current state: Path(5) → Document(2)
```

## Migration Strategy

### Phase 1: Add TreeNode to Document

```python
def migrate_documents(apps, schema_editor):
    """Initialize content trees for existing documents."""
    Document = apps.get_model('documents', 'Document')

    for doc in Document.objects.all():
        doc.version_tree_id = uuid.uuid4()
        doc.is_current = True
        doc.parent = None  # All existing are roots
        doc.save()
```

### Phase 2: Create DocumentPath Records

```python
def create_path_records(apps, schema_editor):
    """
    Create initial path tree from existing corpus-document relationships.
    Note: CorpusDocumentFolder was never deployed to production,
    so we create clean DocumentPath records.
    """
    DocumentPath = apps.get_model('documents', 'DocumentPath')
    Corpus = apps.get_model('corpuses', 'Corpus')

    for corpus in Corpus.objects.prefetch_related('documents'):
        for doc in corpus.documents.all():
            # Generate initial path from document title
            path = f"/{doc.title}"

            DocumentPath.objects.create(
                document=doc,
                corpus=corpus,
                folder=None,  # Start at root
                path=path,
                version_number=1,  # All existing docs start as v1
                parent=None,  # All are roots initially
                is_current=True,
                is_deleted=False
            )
```

## Benefits of This Architecture

1. **Complete Audit Trail**: Every action creates permanent record
2. **Time Travel**: Reconstruct any historical state
3. **Undelete**: Soft deletes enable recovery
4. **Global Deduplication**: Process content only once
5. **Clean Separation**: Content logic independent from location logic
6. **Immutability**: Historical data never lost or modified
7. **Scalability**: Tree queries efficient with CTEs
8. **Clarity**: Rules directly map to code

## Testing Strategy

### Test Categories

1. **Content Tree Tests**
   - Rule C1: Global deduplication works
   - Rule C2: Versions link correctly
   - Rule C3: Only one current per tree

2. **Path Tree Tests**
   - Rule P1: All events create nodes
   - Rule P2: Parent-child relationships
   - Rule P3: Current state management
   - Rule P4: Unique active paths
   - Rule P5: Version numbering

3. **Interaction Tests**
   - Rule I1: Cross-corpus independence
   - Rule Q1: True deletion detection
   - Time travel queries
   - Complex workflows

### Example Test

```python
def test_complete_lifecycle(self):
    """Test import → move → update → delete → restore cycle."""

    # Import
    doc1, _, path1 = import_document(corpus, "/test.pdf", content1, user)
    self.assertIsNone(doc1.parent)
    self.assertIsNone(path1.parent)

    # Move
    path2 = move_document(corpus, "/test.pdf", "/new.pdf", folder)
    self.assertEqual(path2.document, doc1)  # Same content
    self.assertEqual(path2.parent, path1)

    # Update
    doc2, _, path3 = import_document(corpus, "/new.pdf", content2, user)
    self.assertEqual(doc2.parent, doc1)  # Content tree
    self.assertEqual(path3.parent, path2)  # Path tree
    self.assertEqual(path3.version_number, 2)

    # Delete
    path4 = delete_document(corpus, "/new.pdf")
    self.assertTrue(path4.is_deleted)
    self.assertEqual(path4.parent, path3)

    # Restore
    path5 = restore_document(corpus, "/new.pdf")
    self.assertFalse(path5.is_deleted)
    self.assertEqual(path5.parent, path4)

    # Verify trees
    content_history = get_content_history(doc2)
    self.assertEqual(len(content_history), 2)

    path_history = get_path_history(path5)
    self.assertEqual(len(path_history), 5)
```

## Conclusion

This dual-tree architecture, built on first principles of immutability and separation of concerns, provides a robust foundation for document versioning. By clearly defining the rules that govern the system and ensuring all code follows these rules, we achieve a system that is both powerful and comprehensible. The trees tell the complete story of every document's journey through the system.
