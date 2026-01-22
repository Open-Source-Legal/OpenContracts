# Query Permission and Performance Optimization Patterns

This document describes the architectural patterns used in OpenContracts for permission filtering and query optimization.

## Overview

OpenContracts uses a **two-layer permission filtering architecture**:

| Layer | Purpose | When to Use |
|-------|---------|-------------|
| `visible_to_user()` | Standard visibility filtering on QuerySets | Simple models with direct permissions (Corpus, Document, LabelSet) |
| Query Optimizers | Complex permission computation with N+1 prevention | Nested models requiring composite permissions (Annotations, Relationships, Metadata) |

## Core Permission Model

### MIN (Most Restrictive) Pattern

For objects nested within documents and corpuses, effective permissions are computed as:

```
Effective_Permission = MIN(Document_Permission, Corpus_Permission)
```

This means a user must have permission on BOTH the document AND the corpus to access nested objects like annotations, relationships, and metadata.

**Implementation**: `AnnotationQueryOptimizer._compute_effective_permissions()` in `opencontractserver/annotations/query_optimizer.py:29-140`

```python
# Pseudocode for MIN pattern
def compute_effective_permissions(user, document_id, corpus_id):
    doc_read = check_document_permission(user, document_id, READ)
    corpus_read = check_corpus_permission(user, corpus_id, READ)

    # Both must grant permission
    effective_read = doc_read and corpus_read
    return effective_read
```

### Permission Hierarchy

```
┌─────────────────────────────────────────────────────────────┐
│                        Superuser                             │
│                    (all permissions)                         │
├─────────────────────────────────────────────────────────────┤
│                     Object Creator                           │
│              (full CRUD on created objects)                  │
├─────────────────────────────────────────────────────────────┤
│                   Public Objects                             │
│                  (READ for everyone)                         │
├─────────────────────────────────────────────────────────────┤
│              Explicit Guardian Permissions                   │
│         (granted via set_permissions_for_obj_to_user)        │
├─────────────────────────────────────────────────────────────┤
│                  Group Permissions                           │
│              (inherited from user groups)                    │
└─────────────────────────────────────────────────────────────┘
```

## Pattern 1: visible_to_user() Manager Method

### When to Use

- Top-level models with direct permissions (Corpus, Document, Analysis, Extract)
- Models where permission is self-contained (not inherited from parent objects)
- Simple filtering without complex joins

### Implementation Location

Primary implementation: `opencontractserver/shared/Managers.py:40-197` (`BaseVisibilityManager`)

### Standard Pattern

```python
# In GraphQL resolver
def resolve_corpuses(self, info):
    return Corpus.objects.visible_to_user(info.context.user)

# In query resolver
def resolve_document(self, info, id):
    return Document.objects.visible_to_user(info.context.user).get(id=id)
```

### What visible_to_user() Checks

1. **Superuser**: Returns all objects
2. **Anonymous**: Returns only `is_public=True` objects
3. **Authenticated**: Returns objects where:
   - User is creator, OR
   - Object is public, OR
   - User has explicit guardian permissions

### Model-Specific Implementations

| Model | Implementation | Special Logic |
|-------|----------------|---------------|
| Corpus, Document | `BaseVisibilityManager` | Standard + prefetches |
| Annotation | `AnnotationQuerySet` | Privacy filtering for analysis/extract-created |
| User | `UserProfileManager` | Profile privacy + corpus membership |
| Conversation | `SoftDeleteQuerySet` | Soft delete + visibility |
| ChatMessage | `ChatMessageQuerySet` | Moderator access extension |
| AgentConfiguration | `AgentConfigurationQuerySet` | Scope-based (GLOBAL vs CORPUS) |

## Pattern 2: Query Optimizers

### When to Use

- Objects with inherited/composite permissions (Annotations, Relationships)
- When computing permissions requires multiple related objects
- When N+1 query prevention is critical
- When permission flags need to be annotated onto results

### Available Optimizers

| Optimizer | Location | Purpose |
|-----------|----------|---------|
| `AnnotationQueryOptimizer` | `annotations/query_optimizer.py:16-494` | Annotation queries with doc+corpus permissions |
| `RelationshipQueryOptimizer` | `annotations/query_optimizer.py:496-762` | Relationship queries |
| `AnalysisQueryOptimizer` | `annotations/query_optimizer.py:773-975` | Analysis visibility with corpus context |
| `ExtractQueryOptimizer` | `annotations/query_optimizer.py:977-1173` | Extract visibility with corpus context |
| `DocumentActionsQueryOptimizer` | `documents/query_optimizer.py:16-311` | Corpus actions, extracts, analysis rows |
| `DocumentRelationshipQueryOptimizer` | `documents/query_optimizer.py:314-632` | Document-to-document relationships |
| `MetadataQueryOptimizer` | `extracts/query_optimizer.py:19-572` | Datacell/metadata queries |
| `BadgeQueryOptimizer` | `badges/query_optimizer.py:16-158` | Badge visibility via user profile |
| `UserQueryOptimizer` | `users/query_optimizer.py:15-231` | User profile visibility |

### Standard Optimizer Pattern

```python
class MyQueryOptimizer:
    @classmethod
    def _compute_effective_permissions(cls, user, document_id, corpus_id):
        """Compute MIN(doc_perm, corpus_perm) for all permission types."""
        # Returns: (can_read, can_create, can_update, can_delete, can_comment)
        pass

    @classmethod
    def get_objects(cls, document_id, user, corpus_id=None, **filters):
        """Main query method with permission filtering."""
        # 1. Compute permissions once
        can_read, can_create, can_update, can_delete, can_comment = \
            cls._compute_effective_permissions(user, document_id, corpus_id)

        if not can_read:
            return Model.objects.none()

        # 2. Build optimized query
        qs = Model.objects.filter(document_id=document_id)

        # 3. Apply additional filters
        if corpus_id:
            qs = qs.filter(corpus_id=corpus_id)

        # 4. Optimize with prefetches
        qs = qs.select_related('label', 'creator')

        # 5. Annotate with computed permissions for GraphQL
        qs = qs.annotate(
            _can_read=Value(can_read),
            _can_update=Value(can_update),
            # ...
        )

        return qs
```

### Using Optimizers in GraphQL

```python
# In graphene_types.py
def resolve_allAnnotations(self, info, document_id, corpus_id=None):
    from opencontractserver.annotations.query_optimizer import AnnotationQueryOptimizer

    return AnnotationQueryOptimizer.get_document_annotations(
        document_id=document_id,
        user=info.context.user,
        corpus_id=corpus_id,
    )
```

## Pattern 3: N+1 Query Prevention

### Bulk Permission Checks

Instead of checking permissions for each object individually (O(n)), query guardian tables directly (O(1)).

**Implementation**: `MetadataQueryOptimizer._get_readable_document_ids_bulk()` in `extracts/query_optimizer.py:111-172`

```python
@classmethod
def _get_readable_document_ids_bulk(cls, user, document_ids, documents=None):
    """
    Check READ permission for multiple documents in a single query.
    Returns set of document IDs the user can read.
    """
    if user.is_superuser:
        return set(document_ids)

    # Query guardian tables directly
    from opencontractserver.documents.models import DocumentUserObjectPermission

    permitted_ids = set(
        DocumentUserObjectPermission.objects.filter(
            user=user,
            content_object_id__in=document_ids,
            permission__codename='read_document'
        ).values_list('content_object_id', flat=True)
    )

    # Add public documents
    public_ids = set(
        Document.objects.filter(
            id__in=document_ids,
            is_public=True
        ).values_list('id', flat=True)
    )

    return permitted_ids | public_ids
```

### Request-Level Caching

Cache permission computations on the request context to avoid repeated queries within the same GraphQL request.

**Implementation**: `DocumentRelationshipQueryOptimizer` in `documents/query_optimizer.py:340-406`

```python
_VISIBLE_DOC_IDS_CACHE_KEY = "_doc_rel_visible_doc_ids"

@classmethod
def _get_visible_document_ids(cls, user, context=None):
    """Get visible document IDs with request-level caching."""

    # Check cache first
    if context is not None:
        cache_key = f"{cls._VISIBLE_DOC_IDS_CACHE_KEY}_{user.id}"
        if hasattr(context, cache_key):
            return getattr(context, cache_key)

    # Compute visible IDs
    visible_ids = set(
        Document.objects.visible_to_user(user)
        .values_list('id', flat=True)
    )

    # Store in cache
    if context is not None:
        setattr(context, cache_key, visible_ids)

    return visible_ids
```

### Batch Methods

Return data for multiple objects in a single query instead of querying each individually.

**Implementation**: `MetadataQueryOptimizer.get_documents_metadata_batch()` in `extracts/query_optimizer.py:267-370`

```python
@classmethod
def get_documents_metadata_batch(cls, user, corpus, document_ids):
    """
    Fetch metadata for multiple documents in one query.
    Returns: dict[document_id -> list[Datacell]]
    """
    # 1. Bulk permission check
    readable_ids = cls._get_readable_document_ids_bulk(user, document_ids)

    # 2. Single query for all datacells
    qs = Datacell.objects.filter(
        document_id__in=readable_ids,
        column__fieldset=corpus.metadata_schema,
    ).select_related("column", "document")

    # 3. Group by document
    result = {doc_id: [] for doc_id in readable_ids}
    for datacell in qs:
        result[datacell.document_id].append(datacell)

    return result
```

## Pattern 4: Privacy Filtering for Derived Objects

Objects created by analyses or extracts have additional privacy filtering beyond document+corpus permissions.

### Rule

A user can only see annotations/relationships created by an analysis/extract if:
1. They have document+corpus permissions, AND
2. They have access to the creating analysis/extract (public, creator, or explicit permission)

**Exception**: Structural annotations are always visible if the document is readable.

### Implementation

```python
# From AnnotationQueryOptimizer.get_document_annotations() lines 258-270
if not user.is_superuser:
    visible_analyses = Analysis.objects.filter(
        Q(is_public=True) | Q(creator=user)
    )

    # Exclude private annotations user can't see
    # BUT always include structural annotations
    qs = qs.exclude(
        Q(created_by_analysis__isnull=False)
        & Q(structural=False)  # Only apply privacy to non-structural
        & ~Q(created_by_analysis__in=visible_analyses)
    )
```

## Pattern 5: IDOR Protection

Prevent information disclosure through error message differences.

### Rule

Return the same response whether an object doesn't exist OR the user lacks permission.

### Implementation

```python
# From BadgeQueryOptimizer.check_user_badge_visibility()
@classmethod
def check_user_badge_visibility(cls, requesting_user, user_badge_id):
    """
    Returns (is_visible, user_badge_or_none).
    Same result whether not found or no permission.
    """
    try:
        user_badge = cls.get_visible_user_badges(requesting_user).get(id=user_badge_id)
        return True, user_badge
    except UserBadge.DoesNotExist:
        return False, None  # Same result for both cases
```

## Pattern 6: Structural Annotation Handling

Structural annotations (document structure like headers, sections) follow special rules.

### Rules

1. **Always readable** if the document is readable (no additional permissions needed)
2. **Always read-only** for non-superusers (cannot be modified/deleted)
3. **Shared across corpuses** via `structural_annotation_set` (not tied to specific corpus)

### Implementation

```python
# Write protection in permissioning.py lines 353-357
if instance.structural and permission != PermissionTypes.READ:
    logger.info(f"User denied write access to structural annotation")
    return False

# Query inclusion in AnnotationQueryOptimizer lines 203-209
if document.structural_annotation_set_id:
    doc_filters |= Q(
        structural_set_id=document.structural_annotation_set_id,
        structural=True,
    )
```

## Special Permission Models

### Metadata (Datacells)

Metadata uses a **different** permission model than annotations:

- **Annotations**: `MIN(document_perm, corpus_perm)` for all operations
- **Metadata Mutations**: `corpus_perm + document_visibility` (corpus editors can edit metadata on any visible document)

**Rationale**: Metadata schemas are corpus-level features. Corpus editors should be able to manage metadata across all documents they can see.

### User Profile Visibility

Profile visibility follows social networking patterns:

1. Own profile: Always visible
2. Public profiles (`is_profile_public=True`): Visible to all
3. Private profiles: Visible only to users sharing corpus membership with `>READ` permissions (CREATE, UPDATE, DELETE)

**Rationale**: Users who collaborate (with write access) can see each other, but read-only viewers cannot see private profiles.

## Best Practices Summary

1. **Use `visible_to_user()` for top-level models** - Don't reinvent permission filtering
2. **Use Query Optimizers for nested objects** - Ensures MIN pattern is correctly applied
3. **Compute permissions once, apply to many** - Don't check permissions per-object in loops
4. **Annotate permission flags for GraphQL** - Frontend needs to know what actions are allowed
5. **Use bulk permission checks** - Query guardian tables directly for large sets
6. **Implement request-level caching** - Prevent repeated permission queries in same request
7. **Always handle structural annotations** - They have special visibility and read-only rules
8. **Return consistent errors** - Same response for "not found" and "no permission"

## File Reference

| File | Key Classes/Functions |
|------|----------------------|
| `opencontractserver/shared/Managers.py` | `BaseVisibilityManager`, `PermissionManager` |
| `opencontractserver/shared/QuerySets.py` | `PermissionQuerySet`, `AnnotationQuerySet`, `PermissionedTreeQuerySet` |
| `opencontractserver/utils/permissioning.py` | `user_has_permission_for_obj()`, `set_permissions_for_obj_to_user()` |
| `opencontractserver/annotations/query_optimizer.py` | `AnnotationQueryOptimizer`, `RelationshipQueryOptimizer`, `AnalysisQueryOptimizer`, `ExtractQueryOptimizer` |
| `opencontractserver/documents/query_optimizer.py` | `DocumentActionsQueryOptimizer`, `DocumentRelationshipQueryOptimizer` |
| `opencontractserver/extracts/query_optimizer.py` | `MetadataQueryOptimizer` |
| `opencontractserver/badges/query_optimizer.py` | `BadgeQueryOptimizer` |
| `opencontractserver/users/query_optimizer.py` | `UserQueryOptimizer` |
