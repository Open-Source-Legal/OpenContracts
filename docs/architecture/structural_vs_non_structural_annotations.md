# Structural vs Non-Structural Annotations Architecture

## Overview

OpenContracts distinguishes between two fundamentally different types of annotations:

1. **Structural Annotations**: Immutable document structure elements extracted during parsing (headers, sections, paragraphs, tables, figures)
2. **Non-Structural Annotations**: User-created or analysis-generated annotations that add semantic meaning to documents

This distinction enables efficient storage and sharing of structural data across corpus-isolated document copies.

## The Problem

With corpus isolation (each corpus gets its own Document copy), duplicating thousands of structural annotations per copy is wasteful and conceptually incorrect. Structural annotations represent the document's inherent structure and should be identical across all copies.

## The Solution: StructuralAnnotationSet

Structural annotations are separated from Document instances and stored in shared `StructuralAnnotationSet` objects that multiple Documents can reference.

### Core Architecture

```python
class StructuralAnnotationSet(models.Model):
    """Immutable set of structural annotations shared across document copies"""
    content_hash = models.CharField(max_length=64, unique=True, db_index=True)
    parser_name = models.CharField(max_length=255, null=True)
    parser_version = models.CharField(max_length=50, null=True)
    page_count = models.IntegerField(null=True)
    token_count = models.IntegerField(null=True)

    # Shared parsing artifacts
    pawls_parse_file = models.FileField(upload_to="pawls/", ...)
    txt_extract_file = models.FileField(upload_to="txt_extracts/", ...)
```

### Model Relationships

```python
class Document(BaseOCModel):
    # Points to shared structural annotations
    structural_annotation_set = models.ForeignKey(
        StructuralAnnotationSet,
        on_delete=models.PROTECT,  # Cannot delete while documents reference it
        null=True,
        blank=True
    )

class Annotation(models.Model):
    # XOR constraint: belongs to EITHER document OR structural_set
    document = models.ForeignKey(Document, null=True, blank=True)
    structural_set = models.ForeignKey(StructuralAnnotationSet, null=True, blank=True)

    # Flag indicating if this is a structural annotation
    structural = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.CheckConstraint(
                name='annotation_has_single_parent',
                check=(
                    Q(document__isnull=False, structural_set__isnull=True) |
                    Q(document__isnull=True, structural_set__isnull=False)
                )
            )
        ]

class Relationship(models.Model):
    # Same XOR pattern as Annotation
    document = models.ForeignKey(Document, null=True, blank=True)
    structural_set = models.ForeignKey(StructuralAnnotationSet, null=True, blank=True)
    structural = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.CheckConstraint(
                name='relationship_has_single_parent',
                check=(
                    Q(document__isnull=False, structural_set__isnull=True) |
                    Q(document__isnull=True, structural_set__isnull=False)
                )
            )
        ]
```

## How It Works

### Document Parsing Flow

```python
# 1. Document parsed (e.g., via Docling)
document = Document.objects.create(pdf_file_hash="abc123", ...)

# 2. Create or retrieve StructuralAnnotationSet by content hash
struct_set, created = StructuralAnnotationSet.objects.get_or_create(
    content_hash="abc123",
    defaults={
        'parser_name': 'docling',
        'parser_version': '1.0.0',
        'pawls_parse_file': pawls_file,
        'txt_extract_file': text_file,
    }
)

# 3. Link document to structural set
document.structural_annotation_set = struct_set
document.save()

# 4. Create structural annotations linked to set
for annotation_data in parsed_annotations:
    Annotation.objects.create(
        structural_set=struct_set,  # NOT document!
        structural=True,
        annotation_type='header',
        ...
    )
```

### Cross-Corpus Sharing

```python
# Original document with 5000 structural annotations
doc1 = Document.objects.create(pdf_file_hash="abc123")
struct_set = StructuralAnnotationSet.objects.create(content_hash="abc123")
doc1.structural_annotation_set = struct_set
# 5000 annotations created with structural_set=struct_set

# Add to Corpus X - creates corpus-isolated copy
corpus_x.add_document(doc1, user_x)
# Creates doc_copy_x with structural_annotation_set=struct_set (SHARED!)

# Add to Corpus Y - creates another corpus-isolated copy
corpus_y.add_document(doc1, user_y)
# Creates doc_copy_y with structural_annotation_set=struct_set (SHARED!)

# Result: 3 Document objects, 1 StructuralAnnotationSet, 5000 annotations
# NOT 15000 annotations!
```

## Query Integration

The architecture is transparent to application code. Queries automatically fetch annotations from both sources.

### AnnotationQueryOptimizer Integration

```python
# In opencontractserver/annotations/query_optimizer.py
def get_document_annotations(self, document_id):
    document = Document.objects.select_related('structural_annotation_set').get(pk=document_id)

    # Build OR filter to query BOTH sources
    annotation_filter = (
        Q(document_id=document_id) |  # Non-structural annotations
        Q(structural_set_id=document.structural_annotation_set_id, structural=True)  # Structural
    )

    annotations = Annotation.objects.filter(annotation_filter)
    # Application sees all annotations seamlessly
```

### Vector Store Integration

```python
# In opencontractserver/llms/vector_stores/core_vector_stores.py
def search_by_embedding(self, ...):
    # Version filter preserves structural annotations
    if only_current_versions:
        active_filters &= (
            Q(document__is_current=True) |  # Non-structural from current versions
            Q(document_id__isnull=True, structural=True)  # Structural (no document FK)
        )

    # Scoping by document includes structural annotations
    if document:
        annotation_filter |= Q(
            structural_set_id=document.structural_annotation_set_id,
            structural=True
        )
```

## Key Design Decisions

### 1. Content-Based Deduplication

Structural annotations are tied to content hash, not document ID. Same content = same structural annotations.

### 2. XOR Constraints

Database-level enforcement ensures annotations belong to either a document OR a structural set, never both or neither.

### 3. Storage Efficiency

- **Before**: O(n) storage where n = number of corpus copies
- **After**: O(1) storage - structural annotations stored once

### 4. Immutability Guarantee

`PROTECT` on delete prevents deletion of StructuralAnnotationSet while documents reference it. Structural annotations cannot be modified.

### 5. Seamless Query Integration

Application code doesn't need to know about the distinction. Query optimizers handle dual-source fetching transparently.

## Non-Structural Annotations

Non-structural annotations remain attached to specific Document instances:

```python
# User highlights a section and adds a comment
Annotation.objects.create(
    document=doc_copy_x,  # Tied to specific corpus copy
    corpus=corpus_x,
    annotation_type='highlight',
    annotation_label='important_clause',
    creator=user,
    ...
)
```

These are NOT shared across corpus copies because they represent user-specific or analysis-specific interpretations.

## Benefits

### Storage Efficiency
- Structural annotations stored once regardless of corpus copies
- Parsing artifacts (PAWLS, text extracts) shared across documents
- Significant reduction in database size for multi-corpus deployments

### Conceptual Correctness
- Structural annotations represent inherent document structure (immutable)
- Non-structural annotations represent interpretations (corpus-specific)
- Clear separation of concerns

### Performance
- Faster corpus copy operations (no annotation duplication)
- Efficient queries with dual-source fetching
- Reduced memory footprint in application

### Maintainability
- Parser updates affect only StructuralAnnotationSet
- Clear ownership model (structural vs non-structural)
- Database constraints prevent invalid states

## Migrations

Two migrations implement this architecture:

1. **annotations/0048_add_structural_annotation_set.py**
   - Creates StructuralAnnotationSet model
   - Adds XOR constraints on Annotation and Relationship

2. **documents/0026_add_structural_annotation_set.py**
   - Adds structural_annotation_set FK to Document

Both migrations are backward compatible (new fields nullable).

## Test Coverage

Three test suites validate the architecture:

- **test_structural_annotation_sets.py** (22 tests): Model behavior, constraints, CRUD operations
- **test_structural_annotation_portability.py** (10 tests): Cross-corpus sharing, corpus isolation
- **test_query_optimizer_structural_sets.py** (10 tests): Query optimizer integration

**All 42 tests passing**

## Future Enhancements

1. **Parser Versioning**: Track structural annotation set versions when parser algorithms improve
2. **Lazy Migration**: Migrate existing documents to structural sets on first parse after upgrade
3. **Analytics**: Track structural set reuse rates across corpuses
4. **Export**: Include structural annotation sets in corpus export/import operations

---

**Implementation**: Phase 2.5 of dual-tree versioning architecture
**Status**: Complete and production-ready
**Related**: Issue #654, DUAL_TREE_IMPLEMENTATION_SUMMARY.md
