"""Badge service — permission-aware badge queries with profile privacy filtering.

Badge visibility follows the recipient's profile visibility rules.

Visibility model for UserBadge:
- Badge awards are visible if the recipient's profile is visible
- Follows ``UserService``'s visibility rules
- Corpus-specific badges: visible to users with access to that corpus
- Own badges: always visible regardless of profile privacy

The key insight is that badge visibility derives from user profile
visibility, not from direct badge permissions.

Migrated from ``badges/query_optimizer.py`` as Phase 4 of the service-layer
centralization roadmap — see
docs/refactor_plans/2026-05-19-service-layer-centralization-design.md.
"""

from typing import TYPE_CHECKING, Any, Optional

from django.db.models import Q, QuerySet

from opencontractserver.shared.services import BaseService

if TYPE_CHECKING:
    from opencontractserver.badges.models import UserBadge


class BadgeService(BaseService):
    """Permission-aware badge queries with profile privacy filtering.

    All public methods accept an optional ``request`` kwarg for service-layer
    API consistency (the standard ``BaseService`` convention).
    """

    @classmethod
    def get_visible_user_badges(
        cls,
        requesting_user,
        corpus_id: Optional[int] = None,
        user_id: Optional[int] = None,
        *,
        request: Optional[Any] = None,
    ) -> QuerySet:
        """
        Get user badge awards visible to requesting_user.

        Args:
            requesting_user: The user making the request
            corpus_id: Optional corpus to filter badges (for corpus-specific badges)
            user_id: Optional user ID to filter to a specific user's badges
            request: Accepted for service-layer API consistency.

        Returns:
            QuerySet of UserBadge objects visible to the requesting user
        """
        from django.contrib.auth.models import AnonymousUser

        from opencontractserver.badges.models import UserBadge
        from opencontractserver.corpuses.models import Corpus
        from opencontractserver.users.services import UserService

        # Superusers are computed like any other user (scoped admin access,
        # 2026-05): badge awards (UserBadge) are user data and follow normal
        # profile-privacy + corpus visibility for admins too.
        # Get visible users based on profile privacy
        visible_users = UserService.get_visible_users(
            requesting_user, corpus_id=corpus_id, request=request
        )

        # Filter to badges of visible users
        qs = UserBadge.objects.filter(user__in=visible_users)

        # For corpus-specific badges, also check corpus permission
        if requesting_user is not None and not isinstance(
            requesting_user, AnonymousUser
        ):
            # Include badges from corpuses user can access
            visible_corpuses = Corpus.objects.visible_to_user(requesting_user)

            qs = qs.filter(
                Q(corpus__isnull=True)  # Global badges
                | Q(corpus__in=visible_corpuses)  # Corpus badges user can see
            )
        else:
            # Anonymous users can only see global badges or public corpus badges
            qs = qs.filter(
                Q(corpus__isnull=True)  # Global badges
                | Q(corpus__is_public=True)  # Public corpus badges
            )

        # Filter to specific user if requested
        if user_id:
            qs = qs.filter(user_id=user_id)

        # Optimize query with select_related
        return qs.select_related("user", "badge", "awarded_by", "corpus")

    @classmethod
    def check_user_badge_visibility(
        cls, requesting_user, user_badge_id: int, *, request: Optional[Any] = None
    ) -> tuple[bool, Optional["UserBadge"]]:
        """
        Check if requesting_user can see a specific user_badge.

        This method provides IDOR protection by returning the same result
        whether the badge doesn't exist or the user doesn't have permission.

        Args:
            requesting_user: The user making the request
            user_badge_id: The ID of the UserBadge to check
            request: Accepted for service-layer API consistency.

        Returns:
            Tuple of (has_permission, user_badge_object)
            - (True, UserBadge) if visible
            - (False, None) if not visible or doesn't exist
        """
        from opencontractserver.badges.models import UserBadge

        try:
            user_badge = cls.get_visible_user_badges(
                requesting_user, request=request
            ).get(id=user_badge_id)
            return True, user_badge
        except UserBadge.DoesNotExist:
            return False, None

    @classmethod
    def get_badges_for_user(
        cls,
        requesting_user,
        target_user_id: int,
        include_corpus_badges: bool = True,
        *,
        request: Optional[Any] = None,
    ) -> QuerySet:
        """
        Get all visible badges for a specific user.

        This is a convenience method for displaying a user's badge collection.

        Args:
            requesting_user: The user making the request
            target_user_id: The ID of the user whose badges to retrieve
            include_corpus_badges: Whether to include corpus-specific badges
            request: Accepted for service-layer API consistency.

        Returns:
            QuerySet of UserBadge objects for the target user
        """
        from opencontractserver.users.services import UserService

        # First check if the target user is visible
        if not UserService.check_user_visibility(
            requesting_user, target_user_id, request=request
        ):
            from opencontractserver.badges.models import UserBadge

            return UserBadge.objects.none()

        # Get badges for that user
        qs = cls.get_visible_user_badges(
            requesting_user, user_id=target_user_id, request=request
        )

        # Optionally filter out corpus-specific badges
        if not include_corpus_badges:
            qs = qs.filter(corpus__isnull=True)

        return qs.order_by("-awarded_at")
