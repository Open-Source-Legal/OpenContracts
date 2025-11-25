"""
Badge Query Optimizer for OpenContracts.

Provides optimized badge queries with profile privacy filtering.
Badge visibility follows the recipient's profile visibility rules.
"""

from typing import TYPE_CHECKING, Optional

from django.db.models import Q, QuerySet

if TYPE_CHECKING:
    from opencontractserver.badges.models import UserBadge


class BadgeQueryOptimizer:
    """
    Optimized badge queries with profile privacy filtering.

    Visibility model for UserBadge:
    - Badge awards are visible if the recipient's profile is visible
    - Follows UserQueryOptimizer's visibility rules
    - Corpus-specific badges: visible to users with access to that corpus
    - Own badges: always visible regardless of profile privacy

    The key insight is that badge visibility derives from user profile visibility,
    not from direct badge permissions.
    """

    @classmethod
    def get_visible_user_badges(
        cls,
        requesting_user,
        corpus_id: Optional[int] = None,
        user_id: Optional[int] = None,
    ) -> QuerySet:
        """
        Get user badge awards visible to requesting_user.

        Args:
            requesting_user: The user making the request
            corpus_id: Optional corpus to filter badges (for corpus-specific badges)
            user_id: Optional user ID to filter to a specific user's badges

        Returns:
            QuerySet of UserBadge objects visible to the requesting user
        """
        from django.contrib.auth.models import AnonymousUser

        from opencontractserver.badges.models import UserBadge
        from opencontractserver.corpuses.models import Corpus
        from opencontractserver.users.query_optimizer import UserQueryOptimizer

        # Superuser sees all badges
        if hasattr(requesting_user, "is_superuser") and requesting_user.is_superuser:
            qs = UserBadge.objects.all()
        else:
            # Get visible users based on profile privacy
            visible_users = UserQueryOptimizer.get_visible_users(
                requesting_user, corpus_id=corpus_id
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
        cls, requesting_user, user_badge_id: int
    ) -> tuple[bool, Optional["UserBadge"]]:
        """
        Check if requesting_user can see a specific user_badge.

        This method provides IDOR protection by returning the same result
        whether the badge doesn't exist or the user doesn't have permission.

        Args:
            requesting_user: The user making the request
            user_badge_id: The ID of the UserBadge to check

        Returns:
            Tuple of (has_permission, user_badge_object)
            - (True, UserBadge) if visible
            - (False, None) if not visible or doesn't exist
        """
        from opencontractserver.badges.models import UserBadge

        try:
            user_badge = cls.get_visible_user_badges(requesting_user).get(
                id=user_badge_id
            )
            return True, user_badge
        except UserBadge.DoesNotExist:
            return False, None

    @classmethod
    def get_badges_for_user(
        cls,
        requesting_user,
        target_user_id: int,
        include_corpus_badges: bool = True,
    ) -> QuerySet:
        """
        Get all visible badges for a specific user.

        This is a convenience method for displaying a user's badge collection.

        Args:
            requesting_user: The user making the request
            target_user_id: The ID of the user whose badges to retrieve
            include_corpus_badges: Whether to include corpus-specific badges

        Returns:
            QuerySet of UserBadge objects for the target user
        """
        from opencontractserver.users.query_optimizer import UserQueryOptimizer

        # First check if the target user is visible
        if not UserQueryOptimizer.check_user_visibility(
            requesting_user, target_user_id
        ):
            from opencontractserver.badges.models import UserBadge

            return UserBadge.objects.none()

        # Get badges for that user
        qs = cls.get_visible_user_badges(requesting_user, user_id=target_user_id)

        # Optionally filter out corpus-specific badges
        if not include_corpus_badges:
            qs = qs.filter(corpus__isnull=True)

        return qs.order_by("-awarded_at")
