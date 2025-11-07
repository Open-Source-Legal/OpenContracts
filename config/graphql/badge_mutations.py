"""
GraphQL mutations for the badge system.
"""

import logging

import graphene
from django.contrib.auth import get_user_model
from graphql import GraphQLError
from graphql_jwt.decorators import login_required
from graphql_relay import from_global_id

from config.graphql.graphene_types import BadgeType, UserBadgeType
from config.graphql.ratelimits import RateLimits, graphql_ratelimit
from opencontractserver.badges.models import Badge, UserBadge
from opencontractserver.corpuses.models import Corpus
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import (
    set_permissions_for_obj_to_user,
    user_has_permission_for_obj,
)

User = get_user_model()
logger = logging.getLogger(__name__)


class CreateBadgeMutation(graphene.Mutation):
    """Create a new badge (admin/corpus owner only)."""

    class Arguments:
        name = graphene.String(required=True, description="Unique badge name")
        description = graphene.String(required=True, description="Badge description")
        icon = graphene.String(
            required=True,
            description="Icon identifier from lucide-react (e.g., 'Trophy')",
        )
        badge_type = graphene.String(
            required=True, description="Badge type: GLOBAL or CORPUS"
        )
        color = graphene.String(required=False, description="Hex color code")
        corpus_id = graphene.ID(
            required=False, description="Corpus ID for corpus-specific badges"
        )
        is_auto_awarded = graphene.Boolean(
            required=False,
            description="Whether badge is automatically awarded",
            default_value=False,
        )
        criteria_config = graphene.JSONString(
            required=False,
            description="JSON configuration for auto-award criteria",
        )

    ok = graphene.Boolean()
    message = graphene.String()
    badge = graphene.Field(BadgeType)

    @login_required
    @graphql_ratelimit(rate=RateLimits.WRITE_MEDIUM)
    def mutate(
        root,
        info,
        name,
        description,
        icon,
        badge_type,
        color=None,
        corpus_id=None,
        is_auto_awarded=False,
        criteria_config=None,
    ):
        user = info.context.user

        try:
            # Permission check: must be superuser or corpus owner
            corpus = None
            if corpus_id:
                corpus_pk = from_global_id(corpus_id)[1]
                corpus = Corpus.objects.get(pk=corpus_pk)

                # Check if user has permission for this corpus
                if not user.is_superuser and not user_has_permission_for_obj(
                    user, corpus, PermissionTypes.CRUD, include_group_permissions=True
                ):
                    raise GraphQLError(
                        "You must be a corpus owner to create corpus-specific badges."
                    )
            elif not user.is_superuser:
                raise GraphQLError("You must be a superuser to create global badges.")

            # Create the badge
            badge = Badge.objects.create(
                name=name,
                description=description,
                icon=icon,
                badge_type=badge_type,
                color=color or "#05313d",
                corpus=corpus,
                is_auto_awarded=is_auto_awarded,
                criteria_config=criteria_config,
                creator=user,
                is_public=True,  # Badges are generally public
            )

            # Set permissions
            set_permissions_for_obj_to_user(user, badge, [PermissionTypes.CRUD])

            return CreateBadgeMutation(
                ok=True,
                message="Badge created successfully",
                badge=badge,
            )

        except Corpus.DoesNotExist:
            return CreateBadgeMutation(
                ok=False,
                message="Corpus not found",
                badge=None,
            )
        except Exception as e:
            logger.exception("Error creating badge")
            return CreateBadgeMutation(
                ok=False,
                message=f"Failed to create badge: {str(e)}",
                badge=None,
            )


class UpdateBadgeMutation(graphene.Mutation):
    """Update an existing badge."""

    class Arguments:
        badge_id = graphene.ID(required=True, description="Badge ID to update")
        name = graphene.String(required=False)
        description = graphene.String(required=False)
        icon = graphene.String(required=False)
        color = graphene.String(required=False)
        is_auto_awarded = graphene.Boolean(required=False)
        criteria_config = graphene.JSONString(required=False)

    ok = graphene.Boolean()
    message = graphene.String()
    badge = graphene.Field(BadgeType)

    @login_required
    @graphql_ratelimit(rate=RateLimits.WRITE_LIGHT)
    def mutate(
        root,
        info,
        badge_id,
        name=None,
        description=None,
        icon=None,
        color=None,
        is_auto_awarded=None,
        criteria_config=None,
    ):
        user = info.context.user

        try:
            badge_pk = from_global_id(badge_id)[1]
            badge = Badge.objects.get(pk=badge_pk)

            # Permission check
            if not user.is_superuser and not user_has_permission_for_obj(
                user, badge, PermissionTypes.CRUD, include_group_permissions=True
            ):
                raise GraphQLError("You do not have permission to update this badge.")

            # Update fields
            if name is not None:
                badge.name = name
            if description is not None:
                badge.description = description
            if icon is not None:
                badge.icon = icon
            if color is not None:
                badge.color = color
            if is_auto_awarded is not None:
                badge.is_auto_awarded = is_auto_awarded
            if criteria_config is not None:
                badge.criteria_config = criteria_config

            badge.save()

            return UpdateBadgeMutation(
                ok=True,
                message="Badge updated successfully",
                badge=badge,
            )

        except Badge.DoesNotExist:
            return UpdateBadgeMutation(
                ok=False,
                message="Badge not found",
                badge=None,
            )
        except Exception as e:
            logger.exception("Error updating badge")
            return UpdateBadgeMutation(
                ok=False,
                message=f"Failed to update badge: {str(e)}",
                badge=None,
            )


class DeleteBadgeMutation(graphene.Mutation):
    """Delete a badge."""

    class Arguments:
        badge_id = graphene.ID(required=True, description="Badge ID to delete")

    ok = graphene.Boolean()
    message = graphene.String()

    @login_required
    @graphql_ratelimit(rate=RateLimits.WRITE_LIGHT)
    def mutate(root, info, badge_id):
        user = info.context.user

        try:
            badge_pk = from_global_id(badge_id)[1]
            badge = Badge.objects.get(pk=badge_pk)

            # Permission check
            if not user.is_superuser and not user_has_permission_for_obj(
                user, badge, PermissionTypes.CRUD, include_group_permissions=True
            ):
                raise GraphQLError("You do not have permission to delete this badge.")

            badge.delete()

            return DeleteBadgeMutation(
                ok=True,
                message="Badge deleted successfully",
            )

        except Badge.DoesNotExist:
            return DeleteBadgeMutation(
                ok=False,
                message="Badge not found",
            )
        except Exception as e:
            logger.exception("Error deleting badge")
            return DeleteBadgeMutation(
                ok=False,
                message=f"Failed to delete badge: {str(e)}",
            )


class AwardBadgeMutation(graphene.Mutation):
    """Manually award a badge to a user."""

    class Arguments:
        badge_id = graphene.ID(required=True, description="Badge ID to award")
        user_id = graphene.ID(required=True, description="User ID to award badge to")
        corpus_id = graphene.ID(
            required=False, description="Corpus context for corpus-specific badges"
        )

    ok = graphene.Boolean()
    message = graphene.String()
    user_badge = graphene.Field(UserBadgeType)

    @login_required
    @graphql_ratelimit(rate="5/m")  # More restrictive rate limit for awarding
    def mutate(root, info, badge_id, user_id, corpus_id=None):
        awarder = info.context.user

        try:
            badge_pk = from_global_id(badge_id)[1]
            badge = Badge.objects.get(pk=badge_pk)

            recipient_pk = from_global_id(user_id)[1]
            recipient = User.objects.get(pk=recipient_pk)

            corpus = None
            if corpus_id:
                corpus_pk = from_global_id(corpus_id)[1]
                corpus = Corpus.objects.get(pk=corpus_pk)

            # Permission check: must be moderator/owner of the corpus or superuser
            if badge.badge_type == "CORPUS" and badge.corpus:
                # For corpus badges, check corpus permissions
                if not awarder.is_superuser and not user_has_permission_for_obj(
                    awarder,
                    badge.corpus,
                    PermissionTypes.CRUD,
                    include_group_permissions=True,
                ):
                    raise GraphQLError(
                        "You must be a corpus owner/moderator to award this badge."
                    )
            elif not awarder.is_superuser:
                raise GraphQLError("You must be a superuser to award global badges.")

            # Check if badge was already awarded
            existing = UserBadge.objects.filter(
                user=recipient, badge=badge, corpus=corpus
            ).first()
            if existing:
                return AwardBadgeMutation(
                    ok=False,
                    message="Badge already awarded to this user",
                    user_badge=existing,
                )

            # Award the badge
            user_badge = UserBadge.objects.create(
                user=recipient,
                badge=badge,
                awarded_by=awarder,
                corpus=corpus,
            )

            return AwardBadgeMutation(
                ok=True,
                message="Badge awarded successfully",
                user_badge=user_badge,
            )

        except Badge.DoesNotExist:
            return AwardBadgeMutation(
                ok=False,
                message="Badge not found",
                user_badge=None,
            )
        except User.DoesNotExist:
            return AwardBadgeMutation(
                ok=False,
                message="User not found",
                user_badge=None,
            )
        except Corpus.DoesNotExist:
            return AwardBadgeMutation(
                ok=False,
                message="Corpus not found",
                user_badge=None,
            )
        except Exception as e:
            logger.exception("Error awarding badge")
            return AwardBadgeMutation(
                ok=False,
                message=f"Failed to award badge: {str(e)}",
                user_badge=None,
            )


class RevokeBadgeMutation(graphene.Mutation):
    """Revoke a badge from a user."""

    class Arguments:
        user_badge_id = graphene.ID(required=True, description="UserBadge ID to revoke")

    ok = graphene.Boolean()
    message = graphene.String()

    @login_required
    @graphql_ratelimit(rate=RateLimits.WRITE_LIGHT)
    def mutate(root, info, user_badge_id):
        user = info.context.user

        try:
            user_badge_pk = from_global_id(user_badge_id)[1]
            user_badge = UserBadge.objects.select_related("badge").get(pk=user_badge_pk)

            # Permission check
            badge = user_badge.badge
            if badge.badge_type == "CORPUS" and badge.corpus:
                if not user.is_superuser and not user_has_permission_for_obj(
                    user,
                    badge.corpus,
                    PermissionTypes.CRUD,
                    include_group_permissions=True,
                ):
                    raise GraphQLError(
                        "You must be a corpus owner/moderator to revoke this badge."
                    )
            elif not user.is_superuser:
                raise GraphQLError("You must be a superuser to revoke global badges.")

            user_badge.delete()

            return RevokeBadgeMutation(
                ok=True,
                message="Badge revoked successfully",
            )

        except UserBadge.DoesNotExist:
            return RevokeBadgeMutation(
                ok=False,
                message="User badge not found",
            )
        except Exception as e:
            logger.exception("Error revoking badge")
            return RevokeBadgeMutation(
                ok=False,
                message=f"Failed to revoke badge: {str(e)}",
            )
