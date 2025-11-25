"""
User Query Optimizer for OpenContracts.

Provides optimized user queries with profile privacy filtering and corpus membership visibility.
"""

from typing import TYPE_CHECKING, Optional

from django.db.models import Q, QuerySet

if TYPE_CHECKING:
    pass


class UserQueryOptimizer:
    """
    Optimized user queries with profile privacy filtering.

    Visibility model:
    - Own profile: always visible
    - Public profiles (is_profile_public=True): visible to all
    - Private profiles: visible to users who share corpus membership with > READ permission
    - Inactive users: never visible (except to superusers)

    Permission model for corpus membership visibility:
    - Users with any of these permission codenames on the same corpus can see each other:
      - create_corpus (CREATE permission)
      - update_corpus (UPDATE permission)
      - remove_corpus (DELETE permission)
    - READ-only permission does NOT enable seeing private profiles
    """

    # Permission codenames that indicate > READ access
    WRITE_PERMISSION_CODENAMES = ["create_corpus", "update_corpus", "remove_corpus"]

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

        Returns:
            QuerySet of User objects visible to the requesting user
        """
        from django.contrib.auth import get_user_model
        from django.contrib.auth.models import AnonymousUser

        from opencontractserver.corpuses.models import (
            Corpus,
            CorpusUserObjectPermission,
        )

        User = get_user_model()

        # Superusers see all active users
        if hasattr(requesting_user, "is_superuser") and requesting_user.is_superuser:
            return User.objects.filter(is_active=True)

        # Anonymous users see only public profiles
        if requesting_user is None or isinstance(requesting_user, AnonymousUser):
            return User.objects.filter(is_active=True, is_profile_public=True)

        # Build visibility query for authenticated users
        # Start with base query for active users
        base_q = Q(is_active=True)

        # 1. Own profile (always visible if include_self is True)
        own_profile_q = Q(id=requesting_user.id) if include_self else Q()

        # 2. Public profiles
        public_profiles_q = Q(is_profile_public=True)

        # 3. Users who share corpus membership with > READ permission
        # Get corpuses where requesting user has > READ permission
        user_writable_corpus_ids = (
            CorpusUserObjectPermission.objects.filter(
                user=requesting_user,
                permission__codename__in=cls.WRITE_PERMISSION_CODENAMES,
            )
            .values_list("content_object_id", flat=True)
            .distinct()
        )

        # Also include corpuses where requesting user is the creator
        # (creators have implicit full permissions)
        user_owned_corpus_ids = Corpus.objects.filter(
            creator=requesting_user
        ).values_list("id", flat=True)

        # Combine both sources of writable corpuses
        all_writable_corpus_ids = list(user_writable_corpus_ids) + list(
            user_owned_corpus_ids
        )

        if all_writable_corpus_ids:
            # Find users who also have > READ on these corpuses
            users_with_write_access = (
                CorpusUserObjectPermission.objects.filter(
                    content_object_id__in=all_writable_corpus_ids,
                    permission__codename__in=cls.WRITE_PERMISSION_CODENAMES,
                )
                .values_list("user_id", flat=True)
                .distinct()
            )

            # Also include corpus creators
            corpus_creator_ids = Corpus.objects.filter(
                id__in=all_writable_corpus_ids
            ).values_list("creator_id", flat=True)

            # Build the shared membership query
            shared_membership_q = Q(id__in=users_with_write_access) | Q(
                id__in=corpus_creator_ids
            )
        else:
            shared_membership_q = Q()

        # Combine all visibility conditions
        visibility_q = own_profile_q | public_profiles_q | shared_membership_q

        # Build final query
        qs = User.objects.filter(base_q & visibility_q).distinct()

        # If corpus_id is specified, further filter to users with access to that corpus
        if corpus_id:
            corpus_user_ids = (
                CorpusUserObjectPermission.objects.filter(
                    content_object_id=corpus_id,
                    permission__codename__in=cls.WRITE_PERMISSION_CODENAMES,
                )
                .values_list("user_id", flat=True)
                .distinct()
            )

            # Include corpus creator
            try:
                corpus = Corpus.objects.get(id=corpus_id)
                corpus_creator_id = corpus.creator_id
            except Corpus.DoesNotExist:
                corpus_creator_id = None

            corpus_scope_q = Q(id__in=corpus_user_ids)
            if corpus_creator_id:
                corpus_scope_q |= Q(id=corpus_creator_id)

            # Also include self if in scope
            if include_self:
                corpus_scope_q |= Q(id=requesting_user.id)

            qs = qs.filter(corpus_scope_q)

        # Optimize query - only select needed fields for typical use cases
        qs = qs.only(
            "id",
            "username",
            "email",
            "is_profile_public",
            "is_active",
            "slug",
            "name",
            "first_name",
            "last_name",
        )

        return qs

    @classmethod
    def check_user_visibility(cls, requesting_user, target_user_id: int) -> bool:
        """
        Check if requesting_user can see target_user.

        Args:
            requesting_user: The user making the request
            target_user_id: The ID of the user to check visibility for

        Returns:
            True if target_user is visible to requesting_user, False otherwise
        """
        return cls.get_visible_users(requesting_user).filter(id=target_user_id).exists()

    @classmethod
    def get_users_for_mention(
        cls,
        requesting_user,
        text_search: Optional[str] = None,
        corpus_id: Optional[int] = None,
        limit: int = 20,
    ) -> QuerySet:
        """
        Get users for @ mention autocomplete.

        This is a convenience method that combines visibility filtering with search.

        Args:
            requesting_user: The user making the request
            text_search: Optional text to filter by username or email
            corpus_id: Optional corpus to scope visibility
            limit: Maximum number of results to return

        Returns:
            QuerySet of User objects matching the search criteria
        """
        from django.contrib.auth.models import AnonymousUser

        # Anonymous users cannot mention
        if requesting_user is None or isinstance(requesting_user, AnonymousUser):
            from django.contrib.auth import get_user_model

            User = get_user_model()
            return User.objects.none()

        # Get visible users
        qs = cls.get_visible_users(requesting_user, corpus_id=corpus_id)

        # Apply text search if provided
        if text_search:
            qs = qs.filter(
                Q(username__icontains=text_search) | Q(email__icontains=text_search)
            )

        # Order by username and limit results
        return qs.order_by("username")[:limit]
