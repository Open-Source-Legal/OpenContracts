# OpenContracts Permission System: Comprehensive Overview

The permission system uses a multi-layered architecture that integrates Django Guardian for object-level permissions with custom logic for inheritance, annotation, and enforcement.

## 🔄 Permission Flow Diagram

```
┌─────────────────┐    ┌───────────────────┐    ┌────────────────────┐
│                 │    │                   │    │                    │
│  BaseOCModel    │◄───┤ PermissionManager │◄───┤ PermissionQuerySet │
│  - is_public    │    │ - get_queryset()  │    │ - visible_to_user()│
│  - creator      │    │ - visible_to_user │    │                    │
│  - save_as()    │    └───────────────────┘    └────────────────────┘
│  - delete_as()  │            │                          │
└─────────────────┘            │                          │
        │                       │                          │
        ▼                       ▼                          ▼
┌─────────────────────────────────────────────────────────────────────┐
│                                                                     │
│              filter_queryset_by_permission()                        │
│              user_has_permission_for_obj()                          │
│              set_permissions_for_obj_to_user()                      │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
        │                       │                          │
        ▼                       ▼                          ▼
┌─────────────────┐    ┌───────────────────┐    ┌────────────────────┐
│  GraphQL        │    │ Django Guardian   │    │ Permission         │
│  Middleware     │    │ - UserObject      │    │ Types              │
│  - Annotation   │    │   Permission      │    │ - CREATE, READ     │
│                 │    │                   │    │ - CRUD, ALL etc.   │
└─────────────────┘    └───────────────────┘    └────────────────────┘
```

## 🛡️ Key Components

### 1. Core Models and Permissions

- **`BaseOCModel`**: Base abstract model providing:
  - Common fields (`is_public`, `creator`, `user_lock`, etc.)
  - Permission-aware methods (`save_as()`, `delete_as()`)
  - Default manager (`PermissionManager`)

- **`PermissionTypes` Enum**:
  - Basic permissions: CREATE, READ, UPDATE, DELETE, PERMISSION, PUBLISH
  - Composite permissions: CRUD, ALL

### 2. Permission Expansion

The system handles composite permissions by expanding them to their component permissions:

```
┌─────────────────────────────────────────────────────────┐
│                                                         │
│  Permission Expansion                                   │
│  ┌─────────┐                                            │
│  │   ALL   │──┐                                         │
│  └─────────┘  │                                         │
│               ▼                                         │
│  ┌─────────────────────────────────────────────────┐    │
│  │ CREATE, READ, UPDATE, DELETE, PERMISSION, PUBLISH│    │
│  └─────────────────────────────────────────────────┘    │
│                                                         │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│                                                         │
│  Permission Expansion                                   │
│  ┌─────────┐                                            │
│  │  CRUD   │──┐                                         │
│  └─────────┘  │                                         │
│               ▼                                         │
│  ┌───────────────────────────────┐                      │
│  │ CREATE, READ, UPDATE, DELETE  │                      │
│  └───────────────────────────────┘                      │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

This expansion happens consistently in both setting and checking permissions.

### 3. Permission Filtering (Query Level)

The system filters querysets based on user permissions through several layers:

```python
# Typical usage pattern (e.g. in GraphQL resolvers)
Document.objects.visible_to_user(info.context.user)
```

The filtering logic implements a "waterfall" approach:
- **Superusers**: See everything
- **Anonymous users**: See only public objects
- **Authenticated users**: See objects based on:
  - Creator status (own objects)
  - Public status (for READ)
  - Explicit Guardian permissions
  - Inherited permissions (via parent corpus if applicable)

### 4. Mutation Guards (Object Level)

The system protects mutations through permission checks:

```python
# Example usage in a view or GraphQL mutation
document.save_as(user)
document.delete_as(user)
```

The permission logic follows object lifecycle:
- **New objects**: Check CREATE permission
- **Existing objects**: Check UPDATE (for save) or DELETE (for delete)

### 5. GraphQL Permission Annotation

The system annotates GraphQL responses with permission data:

1. **`PermissionAnnotatingMiddleware`** intercepts GraphQL resolvers
2. Identifies underlying Django model type
3. Calls **`get_permissions_for_user_on_model_in_app()`**
4. Stores results in `info.context.permission_annotations`
5. Makes permissions available throughout the GraphQL execution

This enables frontend components to show/hide UI based on permissions without additional queries.

## 🔐 Special Permission Handling

### Inheritance

- Objects can inherit permissions from parent objects (particularly corpus)
- Models opt-in with `INHERITS_CORPUS_PERMISSIONS = True`
- Permissions cascade through relationships (corpus → documents → annotations)

### Performance Optimizations

- **Single-pass corpus inheritance**: Avoids recursive queries
- **Permission caching**: GraphQL middleware annotates permissions once per type
- **Selective expansion**: Only expands special permissions when needed

## 📊 Example Permission Flow

For a typical document query:

1. Frontend makes GraphQL query for documents
2. Query resolver uses `Document.objects.visible_to_user(user)`
3. `filter_queryset_by_permission()` filters the queryset:
   - Returns all for superusers
   - Filters by `is_public` for anonymous users
   - For regular users, includes documents they:
     - Created themselves
     - Have explicit permissions for
     - That belong to a corpus they can access (if inheritance enabled)
4. `PermissionAnnotatingMiddleware` annotates returned objects with permission data
5. Frontend receives both documents and their associated permissions

## 🔧 Best Practices

1. Use `visible_to_user()` for filtering querysets rather than manual permission checks
2. Use `save_as()` and `delete_as()` for permission-aware mutations
3. Use `set_permissions_for_obj_to_user()` for setting permissions
4. Use `get_users_permissions_for_obj()` to get all permissions at once

This multi-layered approach ensures consistent permission enforcement while providing flexibility and maintaining performance.
