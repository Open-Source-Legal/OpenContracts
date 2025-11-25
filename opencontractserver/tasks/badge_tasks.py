"""
Celery tasks for badge auto-awarding and management.
"""

import logging
from typing import Optional

from django.contrib.auth import get_user_model

from config import celery_app
from opencontractserver.badges.models import Badge, BadgeTypeChoices, UserBadge
from opencontractserver.conversations.models import ChatMessage
from opencontractserver.corpuses.models import Corpus

logger = logging.getLogger(__name__)

User = get_user_model()


class BadgeCriteriaType:
    """Constants for badge criteria types."""

    REPUTATION = "reputation_threshold"
    MESSAGE_COUNT = "message_count"
    FIRST_POST = "first_post"
    MESSAGE_UPVOTES = "message_upvotes"
    CORPUS_CONTRIBUTION = "corpus_contribution"


class BadgeCriteriaError(Exception):
    """Raised when badge criteria configuration is invalid."""

    pass


@celery_app.task()
def check_auto_badges(user_id: int, corpus_id: Optional[int] = None) -> dict:
    """
    Check and auto-award badges based on criteria.

    Args:
        user_id: User ID to check badges for
        corpus_id: Optional corpus ID for corpus-specific badge checks

    Returns:
        Dictionary with award results
    """
    logger.info(f"Checking auto badges for user_id={user_id}, corpus_id={corpus_id}")

    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        logger.error(f"User {user_id} not found")
        return {"ok": False, "error": "User not found"}

    corpus = None
    if corpus_id:
        try:
            corpus = Corpus.objects.get(id=corpus_id)
        except Corpus.DoesNotExist:
            logger.error(f"Corpus {corpus_id} not found")
            return {"ok": False, "error": "Corpus not found"}

    awarded_badges = []
    checked_badges = 0

    # Get auto-award badges that haven't been awarded to this user yet
    if corpus:
        # Check corpus-specific badges
        badges = Badge.objects.filter(
            is_auto_awarded=True,
            badge_type=BadgeTypeChoices.CORPUS,
            corpus=corpus,
        ).exclude(
            awards__user=user,
            awards__corpus=corpus,
        )
    else:
        # Check global badges
        badges = Badge.objects.filter(
            is_auto_awarded=True,
            badge_type=BadgeTypeChoices.GLOBAL,
        ).exclude(
            awards__user=user,
            awards__corpus__isnull=True,
        )

    for badge in badges:
        checked_badges += 1
        if _check_badge_criteria(user, badge, corpus):
            # Award the badge
            user_badge = UserBadge.objects.create(
                user=user,
                badge=badge,
                awarded_by=None,  # Auto-awarded
                corpus=corpus,
            )
            awarded_badges.append(
                {
                    "badge_id": badge.id,
                    "badge_name": badge.name,
                    "user_badge_id": user_badge.id,
                }
            )
            logger.info(f"Auto-awarded badge '{badge.name}' to user {user.username}")

    return {
        "ok": True,
        "checked_badges": checked_badges,
        "awarded_badges": awarded_badges,
        "awards_count": len(awarded_badges),
    }


def _check_badge_criteria(
    user: User, badge: Badge, corpus: Optional[Corpus] = None
) -> bool:
    """
    Check if user meets the criteria for a badge.

    Args:
        user: User to check
        badge: Badge to check criteria for
        corpus: Optional corpus context

    Returns:
        True if user meets criteria, False otherwise
    """
    if not badge.criteria_config:
        logger.warning(f"Badge {badge.name} has no criteria config")
        return False

    criteria_type = badge.criteria_config.get("type")

    if not criteria_type:
        logger.warning(f"Badge {badge.name} has incomplete criteria config")
        return False

    # Validate criteria config against registry
    from opencontractserver.badges.criteria_registry import BadgeCriteriaRegistry

    is_valid, error_message = BadgeCriteriaRegistry.validate_config(
        badge.criteria_config
    )
    if not is_valid:
        logger.warning(
            f"Badge {badge.name} has invalid criteria config: {error_message}"
        )
        return False

    # Get value field if criteria type uses it
    value = badge.criteria_config.get("value")

    try:
        if criteria_type == BadgeCriteriaType.REPUTATION:
            # Check user's reputation score
            from opencontractserver.conversations.models import UserReputation

            if corpus:
                # Corpus-specific reputation
                try:
                    reputation = UserReputation.objects.get(user=user, corpus=corpus)
                    return reputation.reputation_score >= int(value)
                except UserReputation.DoesNotExist:
                    # No reputation record means score is 0
                    return int(value) <= 0
            else:
                # Global reputation (corpus=null)
                try:
                    reputation = UserReputation.objects.get(
                        user=user, corpus__isnull=True
                    )
                    return reputation.reputation_score >= int(value)
                except UserReputation.DoesNotExist:
                    # No reputation record means score is 0
                    return int(value) <= 0

        elif criteria_type == BadgeCriteriaType.MESSAGE_COUNT:
            # Check number of messages created
            if corpus:
                # Corpus-specific message count
                count = ChatMessage.objects.filter(
                    creator=user, conversation__chat_with_corpus=corpus
                ).count()
            else:
                # Global message count
                count = ChatMessage.objects.filter(creator=user).count()

            return count >= int(value)

        elif criteria_type == BadgeCriteriaType.FIRST_POST:
            # Award on first message created
            if corpus:
                count = ChatMessage.objects.filter(
                    creator=user, conversation__chat_with_corpus=corpus
                ).count()
            else:
                count = ChatMessage.objects.filter(creator=user).count()

            return count >= 1

        elif criteria_type == BadgeCriteriaType.MESSAGE_UPVOTES:
            # Check if user has a message with N upvotes
            from opencontractserver.conversations.models import MessageVote, VoteType

            # Get user's messages in the appropriate scope
            if corpus:
                # Corpus-specific messages
                user_messages = ChatMessage.objects.filter(
                    creator=user, conversation__chat_with_corpus=corpus
                )
            else:
                # All messages
                user_messages = ChatMessage.objects.filter(creator=user)

            # For each message, count upvotes and check if any meets threshold
            for message in user_messages:
                upvote_count = MessageVote.objects.filter(
                    message=message, vote_type=VoteType.UPVOTE
                ).count()

                if upvote_count >= int(value):
                    return True

            return False

        elif criteria_type == BadgeCriteriaType.CORPUS_CONTRIBUTION:
            # Check contribution to corpus (documents, annotations, etc.)
            if not corpus:
                logger.warning(
                    f"Badge {badge.name} requires corpus context but none provided"
                )
                return False

            # Count documents uploaded to corpus
            # Note: Uses DocumentPath-based source of truth via get_documents()
            doc_count = corpus.get_documents().filter(creator=user).count()

            # Count annotations in corpus
            from opencontractserver.annotations.models import Annotation

            annotation_count = Annotation.objects.filter(
                creator=user, corpus=corpus
            ).count()

            total_contributions = doc_count + annotation_count
            return total_contributions >= int(value)

        else:
            valid_types = [
                BadgeCriteriaType.REPUTATION,
                BadgeCriteriaType.MESSAGE_COUNT,
                BadgeCriteriaType.FIRST_POST,
                BadgeCriteriaType.MESSAGE_UPVOTES,
                BadgeCriteriaType.CORPUS_CONTRIBUTION,
            ]
            logger.error(
                f"Unknown criteria type '{criteria_type}' for badge {badge.name}. "
                f"Valid types: {', '.join(valid_types)}"
            )
            return False

    except (ValueError, TypeError) as e:
        # Configuration errors - invalid value format
        logger.error(
            f"Badge configuration error for '{badge.name}': {e}. "
            f"Check criteria_config: {badge.criteria_config}"
        )
        return False
    except Exception as e:
        # Unexpected errors - database issues, etc.
        logger.exception(
            f"Unexpected error checking badge criteria for '{badge.name}': {e}"
        )
        return False


@celery_app.task()
def check_badges_for_all_users(corpus_id: Optional[int] = None) -> dict:
    """
    Check and award badges for all users (admin utility task).

    Args:
        corpus_id: Optional corpus ID to check corpus-specific badges

    Returns:
        Dictionary with results
    """
    logger.info(f"Checking badges for all users (corpus_id={corpus_id})")

    results = []
    for user in User.objects.filter(is_active=True):
        result = check_auto_badges(user.id, corpus_id)
        if result.get("awards_count", 0) > 0:
            results.append(
                {
                    "user_id": user.id,
                    "username": user.username,
                    "awards_count": result["awards_count"],
                }
            )

    return {
        "ok": True,
        "users_checked": User.objects.filter(is_active=True).count(),
        "users_with_awards": len(results),
        "results": results,
    }


@celery_app.task()
def revoke_badges_by_criteria(badge_id: int) -> dict:
    """
    Revoke badges that no longer meet criteria (for badges where criteria changed).

    Args:
        badge_id: Badge ID to check

    Returns:
        Dictionary with results
    """
    logger.info(f"Checking badge {badge_id} for revocations")

    try:
        badge = Badge.objects.get(id=badge_id, is_auto_awarded=True)
    except Badge.DoesNotExist:
        return {"ok": False, "error": "Badge not found or not auto-awarded"}

    revoked_count = 0
    checked_count = 0

    # Get all user badges for this badge
    user_badges = UserBadge.objects.filter(badge=badge).select_related("user")

    for user_badge in user_badges:
        checked_count += 1
        # Check if user still meets criteria
        if not _check_badge_criteria(user_badge.user, badge, user_badge.corpus):
            user_badge.delete()
            revoked_count += 1
            logger.info(
                f"Revoked badge '{badge.name}' from user {user_badge.user.username}"
            )

    return {
        "ok": True,
        "badge_name": badge.name,
        "checked_count": checked_count,
        "revoked_count": revoked_count,
    }
