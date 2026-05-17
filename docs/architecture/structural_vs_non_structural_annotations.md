# Structural vs Non-Structural Annotations Architecture

## Overview

OpenContracts distinguishes between two fundamentally different types of annotations:

1. **Structural Annotations**: Immutable document structure elements extracted during parsing (headers, sections, paragraphs, tables, figures)
2. **Non-Structural Annotations**: User-created or analysis-generated annotations that add semantic meaning to documents

Both annotation types are **corpus-isolated** - each corpus maintains its own complete copy of all annotations for documents within it.

## The Design: Corpus Isolation

With corpus isolation, each corpus gets its own Document copy AND its own StructuralAnnotationSet. This ensures:

- Complete data isolation between corpuses
- Independent lifecycle management per corpus
- No cross-corpus data leakage
- Simplified permission model (corpus boundaries are hard boundaries)

## The Solution: StructuralAnnotationSet

Structural annotations are separated from Document instances and stored in `StructuralAnnotationSet` objects. When a document is added to a corpus, its structural annotation set is **duplicated** for that corpus.

### Core Architecture

```python
class StructuralAnnotationSet(models.Model):
    """Immutable set of structural annotations for a corpus-specific document copy"""
    # Format: {sha256_hash}_{corpus_id} for corpus-specific sets
    content_hash = models.CharField(max_length=128, unique=True, db_index=True)
    parser_name = models.CharField(max_length=255, null=True)
    parser_version = models.CharField(max_length=50, null=True)
    page_count = models.IntegerField(null=True)
    token_count = models.IntegerField(null=True)

    # Corpus-specific parsing artifacts
    pawls_parse_file = models.FileField(upload_to="pawls/", ...)
    txt_extract_file = models.FileField(upload_to="txt_extracts/", ...)
```

### Model Relationships

```python
class Document(BaseOCModel):
    # Points to corpus-specific structural annotations
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

### Document Upload Flow

When a document is uploaded directly to a corpus:

```python
# 1. Document uploaded to corpus
document = Document.objects.create(pdf_file_hash="abc123", ...)

# 2. Create corpus-specific StructuralAnnotationSet
struct_set = StructuralAnnotationSet.objects.create(
    content_hash=f"abc123_{corpus.id}",  # Corpus-specific hash
    parser_name='docling',
    parser_version='1.0.0',
    pawls_parse_file=pawls_file,
    txt_extract_file=text_file,
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

### Adding Document to Corpus (Duplication)

When an existing document is added to a new corpus, both the document and its structural annotation set are duplicated:

```python
# Original document with 5000 structural annotations in Corpus A
doc1 = Document.objects.get(pk=original_id)
struct_set_a = doc1.structural_annotation_set
# struct_set_a has content_hash="abc123_corpus_a_id"

# Add to Corpus B - creates corpus-isolated copies
corpus_b.add_document(doc1, user)

# Result:
# - New Document copy (doc_copy_b) created for Corpus B
# - New StructuralAnnotationSet (struct_set_b) created with content_hash="abc123_corpus_b_id"
# - All 5000 structural annotations DUPLICATED to struct_set_b
# - doc_copy_b.structural_annotation_set = struct_set_b

# Add to Corpus C - creates another set of corpus-isolated copies
corpus_c.add_document(doc1, user)

# Final result: 3 Document objects, 3 StructuralAnnotationSets, 15000 annotations
# Each corpus has complete isolation
```

### No Source Document Provenance

When documents are copied between corpuses, **no provenance tracking** is maintained:

```python
# After adding doc1 to corpus_b:
doc_copy_b = corpus_b.documents.get(pdf_file_hash="abc123")
doc_copy_b.source_document_id  # None - no provenance link

# This is intentional: corpus copies are independent entities
# with no cross-corpus references
```

## Query Integration

Queries fetch annotations from the document's corpus-specific structural annotation set.

### Accessing Structural Annotations

```python
# Recommended: Query through the document's structural_annotation_set
document = Document.objects.select_related('structural_annotation_set').get(pk=document_id)
structural_annotations = document.structural_annotation_set.structural_annotations.all()

# Alternative: Direct query with structural_set FK
annotations = Annotation.objects.filter(
    structural_set=document.structural_annotation_set,
    structural=True
)
```

### Combined Query (All Annotations)

```python
# In opencontractserver/annotations/query_optimizer.py
def get_document_annotations(self, document_id):
    document = Document.objects.select_related('structural_annotation_set').get(pk=document_id)

    # Query both non-structural (document FK) and structural (structural_set FK)
    annotation_filter = (
        Q(document_id=document_id) |  # Non-structural annotations
        Q(structural_set_id=document.structural_annotation_set_id, structural=True)
    )

    annotations = Annotation.objects.filter(annotation_filter)
    # Returns all annotations for this document within its corpus context
```

### Vector Store Integration

```python
# In opencontractserver/llms/vector_stores/core_vector_stores.py
def search_by_embedding(self, ...):
    # Version filter for current documents
    if only_current_versions:
        active_filters &= (
            Q(document__is_current=True) |  # Non-structural from current versions
            Q(document_id__isnull=True, structural=True)  # Structural (no document FK)
        )

    # Scoping by document includes its structural annotations
    if document:
        annotation_filter |= Q(
            structural_set_id=document.structural_annotation_set_id,
            structural=True
        )
```

## Key Design Decisions

### 1. Corpus Isolation Over Deduplication

Each corpus gets its own complete copy of structural annotations. This prioritizes:
- Data isolation and security
- Independent corpus lifecycle management
- Simplified permission boundaries
- Predictable query behavior
- **Multi-embedder support**: Each corpus can use different embedding models, requiring consistent per-corpus vector spaces. Shared annotations would require managing multiple embedding sets per annotation, significantly complicating vector search operations.

Trade-off: O(n) storage where n = number of corpus copies containing the document.

### 2. XOR Constraints

Database-level enforcement ensures annotations belong to either a document OR a structural set, never both or neither.

### 3. Extended Content Hash

The `content_hash` field uses format `{sha256_hash}_{corpus_id}` (up to 128 chars) to ensure uniqueness per corpus while maintaining content identification.

### 4. Immutability Guarantee

`PROTECT` on delete prevents deletion of StructuralAnnotationSet while documents reference it. Structural annotations cannot be modified after creation.

### 5. No Cross-Corpus References

Document copies do not maintain `source_document` provenance links. Each corpus copy is an independent entity.

## Non-Structural Annotations

Non-structural annotations are attached to specific Document instances within a corpus:

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

These represent user-specific or analysis-specific interpretations and are naturally corpus-isolated.

## Benefits

### Complete Corpus Isolation
- Each corpus is a self-contained unit
- No data leakage between corpuses
- Deletion of one corpus doesn't affect others
- Clear permission boundaries

### Conceptual Clarity
- Structural annotations represent inherent document structure (immutable)
- Non-structural annotations represent interpretations (corpus-specific)
- Clear separation of concerns
- Predictable behavior

### Simplified Operations
- Corpus deletion is straightforward (cascade all related data)
- No complex reference counting for shared data
- Export/import operations are self-contained per corpus

### Maintainability
- Clear ownership model (everything belongs to exactly one corpus)
- Database constraints prevent invalid states
- Straightforward debugging (no cross-corpus dependencies)

## Trade-offs

### Storage
- O(n) storage for structural annotations where n = corpus copies
- Parsing artifacts (PAWLS, text extracts) duplicated per corpus
- Acceptable trade-off for isolation benefits

### Processing
- Document parsing may occur multiple times for same content
- Mitigated by caching at upload layer when appropriate

## Materialised Subtree Groups (`OC_SUBTREE_GROUP`)

Structural parsing produces a hierarchy of annotations connected by
`Annotation.parent` self-FKs and explicit `OC_PARENT_CHILD_LABEL_NAME`
relationships. To make "give me the surrounding block of an annotation hit"
queries cheap, every non-leaf node also gets a pre-materialised
`OC_SUBTREE_GROUP` `Relationship` row whose **source** is that ancestor and
whose **targets** are the ancestor's full transitive descendant set.

Retrieval can then surface the larger block of an annotation hit with a single
join instead of running a recursive CTE per result.

### Where this happens

`BaseParser.save_parsed_data` calls `build_subtree_groups_for_document` (in
`opencontractserver/utils/subtree_groups.py`) between the relationship-import
step and the structural-set migration. The system label `OC_SUBTREE_GROUP` is
resolved by filter-first / create-as-fallback (ignoring `creator`), so the
label never silently forks per-user.

### Guardrails

- Groups whose descendant set exceeds `SUBTREE_GROUP_MAX_DESCENDANTS` (default
  500) are skipped with a warning.
- The walker prunes branches deeper than `SUBTREE_GROUP_MAX_DEPTH` (default
  32) and detects cycles defensively via on-stack tracking.

### Re-parse safety

Prior `OC_SUBTREE_GROUP` rows are deleted from both `document`-scoped and
`structural_set`-scoped tables before re-materialisation, and newly created
rows are attached directly to the existing `StructuralAnnotationSet` when one
is already linked to the document — so re-parsing never leaves orphan rows.

## Migrations

Key migrations implementing this architecture:

1. **annotations/0048_add_structural_annotation_set.py**
   - Creates StructuralAnnotationSet model
   - Adds XOR constraints on Annotation and Relationship

2. **documents/0026_add_structural_annotation_set.py**
   - Adds structural_annotation_set FK to Document

3. **annotations/0056_alter_structuralannotationset_content_hash.py**
   - Extends content_hash to 128 chars for corpus-specific format

## Test Coverage

Three test suites validate the architecture:

- **test_structural_annotation_sets.py**: Model behavior, constraints, CRUD operations
- **test_structural_annotation_portability.py**: Corpus isolation, duplication behavior
- **test_query_optimizer_structural_sets.py**: Query optimizer integration with isolated sets

---

**Implementation**: Phase 2.5 of dual-tree versioning architecture
**Status**: Complete and production-ready
