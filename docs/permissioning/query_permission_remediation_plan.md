# GraphQL Query Permission Remediation Plan

> **Status**: Planning
> **Created**: 2025-01-24
> **Priority**: Critical

## Executive Summary

This document outlines a systematic plan to fix permission violations identified in `config/graphql/queries.py`. The approach creates centralized permission infrastructure following the successful patterns in `AnnotationQueryOptimizer`, ensuring developers can retrieve objects safely without understanding the permissioning system.

## Design Principles

1. **Centralized Logic**: All permission logic in dedicated optimizers/managers
2. **Developer Ergonomics**: Simple API like `.visible_to_user(user)` or `Optimizer.get_visible_X(user)`
3. **Performance First**: Use Django ORM optimizations (prefetch, select_related, subqueries)
4. **Fail Secure**: Default to most restrictive permissions when uncertain
5. **Corpus Membership Rule**: Users with > READ permission on the same corpus can see each other

---

## Phase 1: Create User Visibility Infrastructure

### 1.1 Create `UserQueryOptimizer`

**Location**: `opencontractserver/users/query_optimizer.py`

**Purpose**: Handle user visibility based on:
- Own profile is always visible
- `is_profile_public=True` profiles are visible to everyone
- Users with > READ permission on the same corpus can see each other
- Active users only (`is_active=True`)

```python
class UserQueryOptimizer:
    """
    Optimized user queries with profile privacy filtering.

    Visibility model:
    - Own profile: always visible
    - Public profiles (is_profile_public=True): visible to all
    - Private profiles: visible to users who share corpus membership with > READ permission
    - Inactive users: never visible (except to self and superusers)
    """

    @classmethod
    def get_visible_users(
        cls,
        requesting_user,
        corpus_id: Optional[int] = None,
        include_self: bool = True,
    ) -> QuerySet:
        """
        Get users visible to requesting_user.

        Args:
            requesting_user: The user making the request
            corpus_id: Optional corpus to scope visibility (users with shared access)
            include_self: Whether to include the requesting user (default True)
        """
        from django.contrib.auth import get_user_model
        from opencontractserver.corpuses.models import CorpusUserObjectPermission

        User = get_user_model()

        # Superusers see all active users
        if requesting_user.is_superuser:
            return User.objects.filter(is_active=True)

        # Anonymous users see only public profiles
        if requesting_user.is_anonymous:
            return User.objects.filter(is_active=True, is_profile_public=True)

        # Build visibility query
        # 1. Own profile (always visible)
        # 2. Public profiles
        # 3. Users who share corpus membership with > READ permission

        # Get corpuses where requesting user has > READ permission
        write_perm_codenames = ['create_corpus', 'update_corpus', 'remove_corpus']
        user_writable_corpuses = CorpusUserObjectPermission.objects.filter(
            user=requesting_user,
            permission__codename__in=write_perm_codenames
        ).values_list('content_object_id', flat=True)

        # Get users who are creators or have > READ on those corpuses
        users_in_shared_corpuses = CorpusUserObjectPermission.objects.filter(
            content_object_id__in=user_writable_corpuses,
            permission__codename__in=write_perm_codenames
        ).values_list('user_id', flat=True)

        # Also include corpus creators
        from opencontractserver.corpuses.models import Corpus
        corpus_creators = Corpus.objects.filter(
            id__in=user_writable_corpuses
        ).values_list('creator_id', flat=True)

        # Build final query
        qs = User.objects.filter(
            Q(is_active=True) & (
                Q(id=requesting_user.id) |  # Own profile
                Q(is_profile_public=True) |  # Public profiles
                Q(id__in=users_in_shared_corpuses) |  # Shared corpus membership
                Q(id__in=corpus_creators)  # Corpus creators
            )
        ).distinct()

        # Optimize query
        qs = qs.select_related().only(
            'id', 'username', 'email', 'is_profile_public', 'is_active', 'slug'
        )

        return qs

    @classmethod
    def check_user_visibility(cls, requesting_user, target_user_id: int) -> bool:
        """Check if requesting_user can see target_user."""
        return cls.get_visible_users(requesting_user).filter(id=target_user_id).exists()
```

### 1.2 Update `UserProfileManager` in `users/models.py`

**Current** (lines 34-67): Already has `visible_to_user` but doesn't handle corpus membership.

**Changes**: Integrate with `UserQueryOptimizer` or enhance directly.

```python
class UserProfileManager(DjangoUserManager):
    def visible_to_user(self, user=None, corpus_id=None):
        """
        Returns users visible to the requesting user.

        Privacy rules:
        - Own profile: always visible
        - Public profiles: visible to all
        - Private profiles: visible if share corpus with > READ permission
        - Inactive users: not visible (except self/superuser)
        """
        from opencontractserver.users.query_optimizer import UserQueryOptimizer
        return UserQueryOptimizer.get_visible_users(user, corpus_id=corpus_id)
```

---

## Phase 2: Create Badge Visibility Infrastructure

### 2.1 Create `BadgeQueryOptimizer`

**Location**: `opencontractserver/badges/query_optimizer.py`

**Purpose**: Handle badge/user_badge visibility based on recipient's profile visibility.

```python
class BadgeQueryOptimizer:
    """
    Optimized badge queries with profile privacy filtering.

    Visibility model for UserBadge:
    - Badge awards are visible if the recipient's profile is visible
    - Follows UserQueryOptimizer's visibility rules
    - Corpus-specific badges: visible to users with access to that corpus
    """

    @classmethod
    def get_visible_user_badges(
        cls,
        requesting_user,
        corpus_id: Optional[int] = None,
        user_id: Optional[int] = None,  # Filter to specific user's badges
    ) -> QuerySet:
        """Get user badge awards visible to requesting_user."""
        from opencontractserver.badges.models import UserBadge
        from opencontractserver.users.query_optimizer import UserQueryOptimizer

        # Superuser sees all
        if requesting_user.is_superuser:
            qs = UserBadge.objects.all()
        else:
            # Get visible users
            visible_users = UserQueryOptimizer.get_visible_users(
                requesting_user, corpus_id=corpus_id
            )

            # Filter to badges of visible users
            qs = UserBadge.objects.filter(user__in=visible_users)

            # For corpus-specific badges, also check corpus permission
            if not requesting_user.is_anonymous:
                # Include badges from corpuses user can access
                from opencontractserver.corpuses.models import Corpus
                visible_corpuses = Corpus.objects.visible_to_user(requesting_user)

                qs = qs.filter(
                    Q(corpus__isnull=True) |  # Global badges
                    Q(corpus__in=visible_corpuses)  # Corpus badges user can see
                )

        if user_id:
            qs = qs.filter(user_id=user_id)

        # Optimize
        return qs.select_related('user', 'badge', 'awarded_by', 'corpus')

    @classmethod
    def check_user_badge_visibility(
        cls, requesting_user, user_badge_id: int
    ) -> tuple[bool, Optional['UserBadge']]:
        """Check if requesting_user can see a specific user_badge."""
        from opencontractserver.badges.models import UserBadge

        try:
            user_badge = cls.get_visible_user_badges(requesting_user).get(id=user_badge_id)
            return True, user_badge
        except UserBadge.DoesNotExist:
            return False, None
```

---

## Phase 3: Create Document/Corpus Actions Optimizer

### 3.1 Create `DocumentActionsQueryOptimizer`

**Location**: `opencontractserver/documents/query_optimizer.py`

**Purpose**: Replace the broken `resolve_document_corpus_actions` logic.

```python
class DocumentActionsQueryOptimizer:
    """
    Optimized queries for document-related actions (extracts, analysis rows, corpus actions).

    Follows the least-privilege model from AnnotationQueryOptimizer:
    - Document permissions are primary
    - Corpus permissions are secondary
    - Effective permission = MIN(document_permission, corpus_permission)
    """

    @classmethod
    def get_document_actions(
        cls,
        user,
        document_id: int,
        corpus_id: Optional[int] = None,
    ) -> dict:
        """
        Get all actions/extracts/analyses for a document with proper permission filtering.

        Returns dict with:
        - corpus_actions: CorpusAction objects
        - extracts: Extract objects
        - analysis_rows: DocumentAnalysisRow objects
        """
        from opencontractserver.annotations.query_optimizer import (
            AnalysisQueryOptimizer,
            ExtractQueryOptimizer,
        )
        from opencontractserver.corpuses.models import Corpus, CorpusAction
        from opencontractserver.documents.models import Document
        from opencontractserver.types.enums import PermissionTypes
        from opencontractserver.utils.permissioning import user_has_permission_for_obj

        result = {
            'corpus_actions': [],
            'extracts': [],
            'analysis_rows': [],
        }

        # Check document permission first
        try:
            document = Document.objects.get(id=document_id)
        except Document.DoesNotExist:
            return result

        # Check document READ permission
        if not user.is_superuser:
            if user.is_anonymous:
                if not document.is_public:
                    return result
            elif not user_has_permission_for_obj(
                user, document, PermissionTypes.READ, include_group_permissions=True
            ):
                return result

        # Get corpus if provided
        corpus = None
        if corpus_id:
            try:
                corpus = Corpus.objects.get(id=corpus_id)
                # Check corpus READ permission
                if not user.is_superuser:
                    if user.is_anonymous:
                        if not corpus.is_public:
                            return result
                    elif not user_has_permission_for_obj(
                        user, corpus, PermissionTypes.READ, include_group_permissions=True
                    ):
                        return result
            except Corpus.DoesNotExist:
                pass

        # Get corpus actions (using proper visible_to_user)
        if corpus:
            result['corpus_actions'] = list(
                CorpusAction.objects.visible_to_user(user).filter(corpus=corpus)
            )

        # Get extracts using ExtractQueryOptimizer
        visible_extracts = ExtractQueryOptimizer.get_visible_extracts(
            user, corpus_id=corpus_id
        )
        result['extracts'] = list(
            visible_extracts.filter(documents=document)
        )

        # Get analysis rows
        # Filter to analyses user can see, then get their rows for this document
        visible_analyses = AnalysisQueryOptimizer.get_visible_analyses(
            user, corpus_id=corpus_id
        )
        result['analysis_rows'] = list(
            document.rows.filter(analysis__in=visible_analyses)
            .select_related('analysis', 'analysis__analyzer')
        )

        return result
```

---

## Phase 4: Fix Individual Resolvers

### 4.1 Fix `resolve_user_by_slug` (CRITICAL)

**File**: `config/graphql/queries.py:163-170`

**Current**:
```python
def resolve_user_by_slug(self, info, slug):
    User = get_user_model()
    return User.objects.get(slug=slug)
```

**Fixed**:
```python
def resolve_user_by_slug(self, info, slug):
    from opencontractserver.users.query_optimizer import UserQueryOptimizer

    User = get_user_model()
    try:
        # Use visibility filtering
        return UserQueryOptimizer.get_visible_users(
            info.context.user
        ).get(slug=slug)
    except User.DoesNotExist:
        return None
```

### 4.2 Fix `resolve_search_users_for_mention` (HIGH)

**File**: `config/graphql/queries.py:1134-1176`

**Current**: Ignores `is_profile_public`.

**Fixed**:
```python
@graphql_ratelimit_dynamic(get_rate=get_user_tier_rate("READ_LIGHT"))
def resolve_search_users_for_mention(self, info, text_search=None, **kwargs):
    """
    Search users for @ mention autocomplete.

    SECURITY: Respects user profile privacy settings.
    Users are visible if:
    - Profile is public
    - Requesting user shares corpus membership with > READ permission
    """
    from opencontractserver.users.query_optimizer import UserQueryOptimizer

    user = info.context.user

    # Anonymous users cannot mention
    if user.is_anonymous:
        return User.objects.none()

    # Get visible users using optimizer
    qs = UserQueryOptimizer.get_visible_users(user)

    if text_search:
        qs = qs.filter(
            Q(username__icontains=text_search) | Q(email__icontains=text_search)
        )

    return qs.order_by("username")
```

### 4.3 Fix `resolve_user_badges` / `resolve_user_badge` (HIGH)

**File**: `config/graphql/queries.py:2447-2456`

**Current**: No permission filtering.

**Fixed**:
```python
def resolve_user_badges(self, info, **kwargs):
    """Resolve user badge awards with profile privacy filtering."""
    from opencontractserver.badges.query_optimizer import BadgeQueryOptimizer

    return BadgeQueryOptimizer.get_visible_user_badges(info.context.user)

def resolve_user_badge(self, info, **kwargs):
    """Resolve a single user badge with visibility check and IDOR protection."""
    from opencontractserver.badges.query_optimizer import BadgeQueryOptimizer

    django_pk = from_global_id(kwargs.get("id", None))[1]

    has_permission, user_badge = BadgeQueryOptimizer.check_user_badge_visibility(
        info.context.user, django_pk
    )

    if not has_permission:
        # Same error whether doesn't exist or no permission (IDOR protection)
        raise GraphQLError("User badge not found")

    return user_badge
```

### 4.4 Fix `resolve_document_corpus_actions` (CRITICAL)

**File**: `config/graphql/queries.py:1488-1527`

**Current**: Bypasses permission system entirely.

**Fixed**:
```python
def resolve_document_corpus_actions(self, info, document_id, corpus_id=None):
    from opencontractserver.documents.query_optimizer import DocumentActionsQueryOptimizer

    doc_django_pk = from_global_id(document_id)[1]
    corpus_django_pk = from_global_id(corpus_id)[1] if corpus_id else None

    actions = DocumentActionsQueryOptimizer.get_document_actions(
        user=info.context.user,
        document_id=doc_django_pk,
        corpus_id=corpus_django_pk,
    )

    return DocumentCorpusActionsType(
        corpus_actions=actions['corpus_actions'],
        extracts=actions['extracts'],
        analysis_rows=actions['analysis_rows'],
    )
```

### 4.5 Fix `resolve_assignments` / `resolve_assignment` (LOW - Not Used)

**Option A: Mark as Deprecated**
```python
def resolve_assignments(self, info, **kwargs):
    """
    DEPRECATED: Assignment feature is not currently used.
    See opencontractserver/users/models.py:203-206
    """
    import warnings
    warnings.warn("Assignment feature is deprecated and not in use", DeprecationWarning)

    # Keep existing behavior for backwards compatibility
    if info.context.user.is_superuser:
        return Assignment.objects.all()
    return Assignment.objects.filter(assignor=info.context.user)

def resolve_assignment(self, info, **kwargs):
    """DEPRECATED: Assignment feature is not currently used."""
    import warnings
    warnings.warn("Assignment feature is deprecated and not in use", DeprecationWarning)

    django_pk = from_global_id(kwargs.get("id", None))[1]
    # Fix the AttributeError by using direct query instead of broken visible_to_user
    if info.context.user.is_superuser:
        return Assignment.objects.get(id=django_pk)
    return Assignment.objects.get(
        Q(id=django_pk) & (Q(assignor=info.context.user) | Q(assignee=info.context.user))
    )
```

**Option B: Full Fix** (if feature will be used later)
Create `AssignmentQueryOptimizer` following same pattern.

### 4.6 Fix `resolve_bulk_document_upload_status` (MEDIUM)

**File**: `config/graphql/queries.py:2197-2288`

**Issue**: Any authenticated user can check any job's status.

**Fix Strategy**: Store job ownership in Redis alongside the job.

```python
# When creating the job (in mutation):
redis_client.set(f"bulk_upload_job:{job_id}:owner", user.id, ex=86400)  # 24h TTL

# In resolver:
@login_required
def resolve_bulk_document_upload_status(self, info, job_id):
    # Verify job ownership
    expected_owner = redis_client.get(f"bulk_upload_job:{job_id}:owner")
    if expected_owner and int(expected_owner) != info.context.user.id:
        if not info.context.user.is_superuser:
            return BulkDocumentUploadStatusType(
                job_id=job_id,
                success=False,
                completed=False,
                errors=["Job not found"],  # Same error for IDOR protection
            )

    # ... rest of existing logic
```

---

## Phase 5: Testing Strategy

### 5.1 Test Files to Create

1. `opencontractserver/tests/test_user_visibility.py`
   - Test profile privacy respected
   - Test corpus membership visibility
   - Test anonymous user restrictions

2. `opencontractserver/tests/test_badge_visibility.py`
   - Test badge visibility follows profile privacy
   - Test corpus-specific badge visibility

3. `opencontractserver/tests/test_document_actions_permissions.py`
   - Test proper permission inheritance
   - Test hybrid model for extracts/analyses

### 5.2 Test Cases

```python
class TestUserVisibility(TestCase):
    def test_private_profile_not_visible_to_strangers(self):
        """User with is_profile_public=False should not be visible to unrelated users."""

    def test_private_profile_visible_to_corpus_members(self):
        """User with is_profile_public=False visible to users with > READ on shared corpus."""

    def test_public_profile_visible_to_all(self):
        """User with is_profile_public=True visible to all authenticated users."""

    def test_inactive_user_not_visible(self):
        """Inactive users (is_active=False) should not be visible except to self/superuser."""

    def test_own_profile_always_visible(self):
        """User can always see their own profile regardless of settings."""

class TestBadgeVisibility(TestCase):
    def test_badge_visibility_follows_profile_privacy(self):
        """Badge awards only visible if recipient's profile is visible."""

    def test_corpus_badge_requires_corpus_access(self):
        """Corpus-specific badges require access to that corpus."""
```

---

## Implementation Order

| Priority | Task | Effort | Files |
|----------|------|--------|-------|
| 1 | Create `UserQueryOptimizer` | Medium | `users/query_optimizer.py` |
| 2 | Create `BadgeQueryOptimizer` | Low | `badges/query_optimizer.py` |
| 3 | Create `DocumentActionsQueryOptimizer` | Medium | `documents/query_optimizer.py` |
| 4 | Fix `resolve_user_by_slug` | Low | `config/graphql/queries.py` |
| 5 | Fix `resolve_search_users_for_mention` | Low | `config/graphql/queries.py` |
| 6 | Fix `resolve_user_badges` / `resolve_user_badge` | Low | `config/graphql/queries.py` |
| 7 | Fix `resolve_document_corpus_actions` | Low | `config/graphql/queries.py` |
| 8 | Fix `resolve_assignments` | Low | `config/graphql/queries.py` |
| 9 | Add job ownership to bulk upload | Medium | Multiple files |
| 10 | Write tests | High | `tests/` |

---

## Performance Considerations

### Query Optimization Patterns Used

1. **Subqueries over JOINs**: Use `values_list(..., flat=True)` + `__in` instead of JOINs for permission checks
2. **Prefetch Related**: Use `select_related` and `prefetch_related` to avoid N+1
3. **Only/Defer**: Use `.only()` to limit fields when full model not needed
4. **Exists Subqueries**: Use `Exists(OuterRef(...))` for permission checks instead of JOINs

### Example Optimized Query

```python
# BAD - Multiple queries per user
for user in users:
    if UserQueryOptimizer.check_user_visibility(requesting_user, user.id):
        visible_users.append(user)

# GOOD - Single optimized query
visible_users = UserQueryOptimizer.get_visible_users(requesting_user)
```

---

## Backwards Compatibility

1. **Deprecation Warnings**: Add warnings for deprecated resolvers
2. **Graceful Fallbacks**: New optimizers return empty querysets on permission denial
3. **Consistent Error Messages**: Same error for "not found" and "no permission" (IDOR protection)

---

## Detailed Test Specifications

All tests should be realistic, human-readable, and prove the changes work.

### Test File: `opencontractserver/tests/permissioning/test_user_visibility.py`

```python
"""
Tests for User Profile Visibility System

These tests verify that user profiles respect privacy settings and corpus membership rules.
"""
from django.test import TestCase
from django.contrib.auth import get_user_model
from opencontractserver.corpuses.models import Corpus
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user
from opencontractserver.users.query_optimizer import UserQueryOptimizer

User = get_user_model()


class TestUserProfilePrivacy(TestCase):
    """Tests that verify user profile privacy settings are respected."""

    def setUp(self):
        """Create test users with different privacy settings."""
        self.public_user = User.objects.create_user(
            username="public_alice",
            email="alice@example.com",
            password="testpass123",
            is_profile_public=True,
        )
        self.private_user = User.objects.create_user(
            username="private_bob",
            email="bob@example.com",
            password="testpass123",
            is_profile_public=False,
        )
        self.viewer = User.objects.create_user(
            username="viewer_carol",
            email="carol@example.com",
            password="testpass123",
        )

    def test_public_profile_visible_to_any_authenticated_user(self):
        """
        GIVEN: A user (Alice) with is_profile_public=True
        WHEN: Another user (Carol) queries for visible users
        THEN: Alice's profile should be in the results
        """
        visible_users = UserQueryOptimizer.get_visible_users(self.viewer)

        self.assertIn(
            self.public_user,
            visible_users,
            "Public profiles should be visible to any authenticated user"
        )

    def test_private_profile_not_visible_to_unrelated_user(self):
        """
        GIVEN: A user (Bob) with is_profile_public=False
        AND: A viewer (Carol) who does NOT share any corpus membership with Bob
        WHEN: Carol queries for visible users
        THEN: Bob's profile should NOT be in the results
        """
        visible_users = UserQueryOptimizer.get_visible_users(self.viewer)

        self.assertNotIn(
            self.private_user,
            visible_users,
            "Private profiles should NOT be visible to unrelated users"
        )

    def test_own_profile_always_visible_regardless_of_privacy_setting(self):
        """
        GIVEN: A user (Bob) with is_profile_public=False
        WHEN: Bob queries for visible users
        THEN: Bob should see his own profile in the results
        """
        visible_users = UserQueryOptimizer.get_visible_users(self.private_user)

        self.assertIn(
            self.private_user,
            visible_users,
            "Users should always see their own profile regardless of privacy setting"
        )


class TestUserVisibilityViaCorpusMembership(TestCase):
    """Tests that verify corpus membership enables user visibility."""

    def setUp(self):
        """Create test users and a shared corpus."""
        self.corpus_owner = User.objects.create_user(
            username="owner",
            email="owner@example.com",
            password="testpass123",
        )
        self.private_collaborator = User.objects.create_user(
            username="collaborator",
            email="collab@example.com",
            password="testpass123",
            is_profile_public=False,  # Private profile
        )
        self.outsider = User.objects.create_user(
            username="outsider",
            email="outsider@example.com",
            password="testpass123",
        )

        # Create a corpus
        self.shared_corpus = Corpus.objects.create(
            title="Shared Legal Corpus",
            creator=self.corpus_owner,
        )

        # Give collaborator UPDATE permission (> READ) on the corpus
        set_permissions_for_obj_to_user(
            self.private_collaborator,
            self.shared_corpus,
            [PermissionTypes.READ, PermissionTypes.UPDATE],
        )

    def test_private_user_visible_to_corpus_member_with_write_permission(self):
        """
        GIVEN: A user (collaborator) with is_profile_public=False
        AND: Another user (owner) who shares a corpus with collaborator
        AND: Collaborator has > READ permission on that corpus
        WHEN: Owner queries for visible users
        THEN: Collaborator's profile should be visible
        """
        visible_users = UserQueryOptimizer.get_visible_users(self.corpus_owner)

        self.assertIn(
            self.private_collaborator,
            visible_users,
            "Private profiles should be visible to users who share corpus with > READ"
        )

    def test_private_user_not_visible_to_outsider(self):
        """
        GIVEN: A user (collaborator) with is_profile_public=False
        AND: A user (outsider) who does NOT have access to any shared corpus
        WHEN: Outsider queries for visible users
        THEN: Collaborator's profile should NOT be visible
        """
        visible_users = UserQueryOptimizer.get_visible_users(self.outsider)

        self.assertNotIn(
            self.private_collaborator,
            visible_users,
            "Private profiles should NOT be visible to users outside shared corpuses"
        )

    def test_read_only_corpus_member_cannot_see_private_profiles(self):
        """
        GIVEN: A corpus with two members
        AND: One member (viewer) has only READ permission
        AND: Another member (collaborator) has is_profile_public=False
        WHEN: Viewer queries for visible users
        THEN: Collaborator's profile should NOT be visible (READ is not enough)
        """
        read_only_user = User.objects.create_user(
            username="readonly",
            email="readonly@example.com",
            password="testpass123",
        )
        # Give only READ permission (not > READ)
        set_permissions_for_obj_to_user(
            read_only_user,
            self.shared_corpus,
            [PermissionTypes.READ],
        )

        visible_users = UserQueryOptimizer.get_visible_users(read_only_user)

        self.assertNotIn(
            self.private_collaborator,
            visible_users,
            "READ-only permission should NOT enable seeing private profiles"
        )


class TestUserVisibilityAnonymousUser(TestCase):
    """Tests for anonymous user visibility rules."""

    def setUp(self):
        """Create test users."""
        self.public_user = User.objects.create_user(
            username="public",
            email="public@example.com",
            password="testpass123",
            is_profile_public=True,
        )
        self.private_user = User.objects.create_user(
            username="private",
            email="private@example.com",
            password="testpass123",
            is_profile_public=False,
        )

    def test_anonymous_user_can_see_public_profiles(self):
        """
        GIVEN: A public user profile
        WHEN: An anonymous user queries for visible users
        THEN: Public profiles should be visible
        """
        from django.contrib.auth.models import AnonymousUser

        anonymous = AnonymousUser()
        visible_users = UserQueryOptimizer.get_visible_users(anonymous)

        self.assertIn(
            self.public_user,
            visible_users,
            "Anonymous users should see public profiles"
        )

    def test_anonymous_user_cannot_see_private_profiles(self):
        """
        GIVEN: A private user profile
        WHEN: An anonymous user queries for visible users
        THEN: Private profiles should NOT be visible
        """
        from django.contrib.auth.models import AnonymousUser

        anonymous = AnonymousUser()
        visible_users = UserQueryOptimizer.get_visible_users(anonymous)

        self.assertNotIn(
            self.private_user,
            visible_users,
            "Anonymous users should NOT see private profiles"
        )


class TestInactiveUserVisibility(TestCase):
    """Tests that inactive users are properly hidden."""

    def setUp(self):
        """Create active and inactive users."""
        self.active_user = User.objects.create_user(
            username="active",
            email="active@example.com",
            password="testpass123",
            is_active=True,
        )
        self.inactive_user = User.objects.create_user(
            username="inactive",
            email="inactive@example.com",
            password="testpass123",
            is_active=False,  # Deactivated account
            is_profile_public=True,  # Even public profiles should be hidden
        )
        self.viewer = User.objects.create_user(
            username="viewer",
            email="viewer@example.com",
            password="testpass123",
        )

    def test_inactive_user_not_visible_even_with_public_profile(self):
        """
        GIVEN: A user account that has been deactivated (is_active=False)
        AND: That user had is_profile_public=True
        WHEN: Another user queries for visible users
        THEN: The inactive user should NOT be visible
        """
        visible_users = UserQueryOptimizer.get_visible_users(self.viewer)

        self.assertNotIn(
            self.inactive_user,
            visible_users,
            "Inactive users should NOT be visible even with public profile"
        )

    def test_superuser_can_see_inactive_users(self):
        """
        GIVEN: An inactive user
        AND: A superuser
        WHEN: Superuser queries for visible users
        THEN: The inactive user should be visible (for admin purposes)
        """
        superuser = User.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="adminpass123",
        )
        # Note: Superuser sees all ACTIVE users - inactive may or may not be included
        # depending on design decision. This test documents expected behavior.
        visible_users = UserQueryOptimizer.get_visible_users(superuser)

        # Active users should definitely be visible
        self.assertIn(self.active_user, visible_users)
```

### Test File: `opencontractserver/tests/permissioning/test_badge_visibility.py`

```python
"""
Tests for Badge/UserBadge Visibility System

These tests verify that badge awards respect the recipient's profile privacy.
"""
from django.test import TestCase
from django.contrib.auth import get_user_model
from opencontractserver.badges.models import Badge, UserBadge
from opencontractserver.badges.query_optimizer import BadgeQueryOptimizer
from opencontractserver.corpuses.models import Corpus
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()


class TestUserBadgeVisibility(TestCase):
    """Tests that user badge visibility follows profile privacy rules."""

    def setUp(self):
        """Create test users, badges, and awards."""
        self.badge_owner = User.objects.create_user(
            username="badgeholder",
            email="badge@example.com",
            password="testpass123",
            is_profile_public=False,  # Private profile
        )
        self.viewer = User.objects.create_user(
            username="viewer",
            email="viewer@example.com",
            password="testpass123",
        )

        # Create a badge
        self.achievement_badge = Badge.objects.create(
            name="First Annotation",
            description="Awarded for creating your first annotation",
            icon="Star",
            creator=self.viewer,  # Badge definition creator
        )

        # Award the badge
        self.badge_award = UserBadge.objects.create(
            user=self.badge_owner,  # Private user receives badge
            badge=self.achievement_badge,
        )

    def test_badge_of_private_user_not_visible_to_unrelated_viewer(self):
        """
        GIVEN: A badge awarded to a user (badgeholder) with is_profile_public=False
        AND: A viewer who does NOT share corpus membership with badgeholder
        WHEN: Viewer queries for visible user badges
        THEN: The badge award should NOT be visible
        """
        visible_badges = BadgeQueryOptimizer.get_visible_user_badges(self.viewer)

        self.assertNotIn(
            self.badge_award,
            visible_badges,
            "Badges of private users should NOT be visible to unrelated viewers"
        )

    def test_own_badges_always_visible(self):
        """
        GIVEN: A user (badgeholder) with badge awards
        WHEN: badgeholder queries for their own badges
        THEN: Their badges should be visible regardless of profile privacy
        """
        visible_badges = BadgeQueryOptimizer.get_visible_user_badges(self.badge_owner)

        self.assertIn(
            self.badge_award,
            visible_badges,
            "Users should always see their own badges"
        )


class TestCorpusSpecificBadgeVisibility(TestCase):
    """Tests for corpus-specific badge visibility."""

    def setUp(self):
        """Create corpus-specific badge scenario."""
        self.corpus_owner = User.objects.create_user(
            username="corpusowner",
            email="owner@example.com",
            password="testpass123",
        )
        self.badge_recipient = User.objects.create_user(
            username="recipient",
            email="recipient@example.com",
            password="testpass123",
            is_profile_public=True,  # Public profile
        )
        self.outsider = User.objects.create_user(
            username="outsider",
            email="outsider@example.com",
            password="testpass123",
        )

        # Create private corpus
        self.private_corpus = Corpus.objects.create(
            title="Private Legal Corpus",
            creator=self.corpus_owner,
            is_public=False,
        )

        # Give recipient access to corpus
        set_permissions_for_obj_to_user(
            self.badge_recipient,
            self.private_corpus,
            [PermissionTypes.READ, PermissionTypes.UPDATE],
        )

        # Create corpus-specific badge
        self.corpus_badge = Badge.objects.create(
            name="Top Contributor",
            description="Top contributor in this corpus",
            icon="Trophy",
            badge_type="CORPUS",
            corpus=self.private_corpus,
            creator=self.corpus_owner,
        )

        # Award corpus badge
        self.corpus_badge_award = UserBadge.objects.create(
            user=self.badge_recipient,
            badge=self.corpus_badge,
            corpus=self.private_corpus,
        )

    def test_corpus_badge_visible_to_corpus_member(self):
        """
        GIVEN: A corpus-specific badge awarded in a private corpus
        AND: A user who has access to that corpus
        WHEN: User queries for visible badges
        THEN: The corpus badge should be visible
        """
        visible_badges = BadgeQueryOptimizer.get_visible_user_badges(self.corpus_owner)

        self.assertIn(
            self.corpus_badge_award,
            visible_badges,
            "Corpus-specific badges should be visible to corpus members"
        )

    def test_corpus_badge_not_visible_to_outsider(self):
        """
        GIVEN: A corpus-specific badge awarded in a private corpus
        AND: A user who does NOT have access to that corpus
        WHEN: User queries for visible badges
        THEN: The corpus badge should NOT be visible
        """
        visible_badges = BadgeQueryOptimizer.get_visible_user_badges(self.outsider)

        self.assertNotIn(
            self.corpus_badge_award,
            visible_badges,
            "Corpus-specific badges should NOT be visible to non-members"
        )
```

### Test File: `opencontractserver/tests/permissioning/test_document_actions_permissions.py`

```python
"""
Tests for Document Actions Permission System

These tests verify that document_corpus_actions follows the least-privilege model.
"""
from django.test import TestCase
from django.contrib.auth import get_user_model
from opencontractserver.corpuses.models import Corpus, CorpusAction
from opencontractserver.documents.models import Document
from opencontractserver.documents.query_optimizer import DocumentActionsQueryOptimizer
from opencontractserver.extracts.models import Extract, Fieldset
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()


class TestDocumentActionsPermissions(TestCase):
    """Tests for document actions with proper permission inheritance."""

    def setUp(self):
        """Create test scenario with document, corpus, and extracts."""
        self.owner = User.objects.create_user(
            username="owner",
            email="owner@example.com",
            password="testpass123",
        )
        self.reader = User.objects.create_user(
            username="reader",
            email="reader@example.com",
            password="testpass123",
        )
        self.outsider = User.objects.create_user(
            username="outsider",
            email="outsider@example.com",
            password="testpass123",
        )

        # Create corpus and document
        self.corpus = Corpus.objects.create(
            title="Test Corpus",
            creator=self.owner,
            is_public=False,
        )
        self.document = Document.objects.create(
            title="Test Document",
            creator=self.owner,
        )

        # Give reader READ permission on both
        set_permissions_for_obj_to_user(
            self.reader,
            self.corpus,
            [PermissionTypes.READ],
        )
        set_permissions_for_obj_to_user(
            self.reader,
            self.document,
            [PermissionTypes.READ],
        )

        # Create a fieldset and extract
        self.fieldset = Fieldset.objects.create(
            name="Test Fieldset",
            creator=self.owner,
        )
        self.extract = Extract.objects.create(
            name="Test Extract",
            corpus=self.corpus,
            fieldset=self.fieldset,
            creator=self.owner,
        )
        self.extract.documents.add(self.document)

    def test_owner_can_see_all_document_actions(self):
        """
        GIVEN: A document owner with full permissions
        WHEN: Owner queries for document actions
        THEN: All extracts and actions should be visible
        """
        actions = DocumentActionsQueryOptimizer.get_document_actions(
            user=self.owner,
            document_id=self.document.id,
            corpus_id=self.corpus.id,
        )

        self.assertIn(
            self.extract,
            actions['extracts'],
            "Owner should see all extracts on their document"
        )

    def test_reader_with_explicit_permission_can_see_document(self):
        """
        GIVEN: A user (reader) with explicit READ permission on document AND corpus
        WHEN: Reader queries for document actions
        THEN: Reader should see extracts they have permission to
        """
        # Give reader explicit permission on extract too
        set_permissions_for_obj_to_user(
            self.reader,
            self.extract,
            [PermissionTypes.READ],
        )

        actions = DocumentActionsQueryOptimizer.get_document_actions(
            user=self.reader,
            document_id=self.document.id,
            corpus_id=self.corpus.id,
        )

        self.assertIn(
            self.extract,
            actions['extracts'],
            "Reader with explicit permission should see the extract"
        )

    def test_outsider_cannot_see_any_document_actions(self):
        """
        GIVEN: A user (outsider) with NO permissions on document or corpus
        WHEN: Outsider queries for document actions
        THEN: All actions should be empty (permission denied)
        """
        actions = DocumentActionsQueryOptimizer.get_document_actions(
            user=self.outsider,
            document_id=self.document.id,
            corpus_id=self.corpus.id,
        )

        self.assertEqual(
            actions['extracts'],
            [],
            "Outsider should NOT see any extracts"
        )
        self.assertEqual(
            actions['corpus_actions'],
            [],
            "Outsider should NOT see any corpus actions"
        )

    def test_user_with_only_document_permission_cannot_see_corpus_actions(self):
        """
        GIVEN: A user with READ permission on document but NOT corpus
        WHEN: User queries for document actions
        THEN: Corpus actions should be empty (corpus permission required)
        """
        doc_only_user = User.objects.create_user(
            username="doconly",
            email="doconly@example.com",
            password="testpass123",
        )
        set_permissions_for_obj_to_user(
            doc_only_user,
            self.document,
            [PermissionTypes.READ],
        )
        # No corpus permission!

        actions = DocumentActionsQueryOptimizer.get_document_actions(
            user=doc_only_user,
            document_id=self.document.id,
            corpus_id=self.corpus.id,
        )

        self.assertEqual(
            actions['corpus_actions'],
            [],
            "User without corpus permission should NOT see corpus actions"
        )


class TestDocumentActionsIDORProtection(TestCase):
    """Tests for IDOR protection in document actions."""

    def setUp(self):
        """Create scenario for IDOR testing."""
        self.user_a = User.objects.create_user(
            username="user_a",
            email="a@example.com",
            password="testpass123",
        )
        self.user_b = User.objects.create_user(
            username="user_b",
            email="b@example.com",
            password="testpass123",
        )

        # User A's private document
        self.private_document = Document.objects.create(
            title="Private Document",
            creator=self.user_a,
            is_public=False,
        )

    def test_cannot_enumerate_private_documents(self):
        """
        GIVEN: User B who does NOT have permission to User A's document
        WHEN: User B queries for document actions on User A's document
        THEN: Empty results should be returned (same as if document didn't exist)
        """
        actions = DocumentActionsQueryOptimizer.get_document_actions(
            user=self.user_b,
            document_id=self.private_document.id,
            corpus_id=None,
        )

        # Should return empty dict, not error with "permission denied"
        self.assertEqual(actions['extracts'], [])
        self.assertEqual(actions['corpus_actions'], [])
        self.assertEqual(actions['analysis_rows'], [])
```

---

## Security Audit Checklist

After implementation, verify:

- [ ] `resolve_user_by_slug` respects `is_profile_public`
- [ ] `resolve_search_users_for_mention` respects profile privacy
- [ ] `resolve_user_badges` respects recipient's profile privacy
- [ ] `resolve_user_badge` has IDOR protection
- [ ] `resolve_document_corpus_actions` uses proper permission model
- [ ] `resolve_assignments` doesn't cause AttributeError
- [ ] Bulk upload job ownership is verified
- [ ] All new optimizers handle anonymous users correctly
- [ ] All new optimizers handle superusers correctly
- [ ] No N+1 query issues introduced
- [ ] All tests pass and prove the security requirements
