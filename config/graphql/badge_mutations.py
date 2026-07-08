"""Generated strawberry GraphQL module (graphene migration).

Shape-generated from the graphene schema; stub functions marked PORT(...)
carry the ported business logic. See config/graphql_new/manifest.json.
"""

# mypy: disable-error-code="name-defined, valid-type, arg-type"
#   Code-generation artifacts of the strawberry schema bindings that
#   mypy's static pass cannot resolve, NOT real typing defects:
#     name-defined / valid-type — ``Annotated["XType", strawberry.lazy(...)]``
#       forward-reference strings + the runtime-generated ``*Connection``
#       types (``make_connection_types``).
#     arg-type — resolvers construct result types with ``to_global_id()``
#       (``str``) for ``strawberry.ID`` fields and return Django MODEL
#       instances where the field annotation names the strawberry type
#       (the graphene-django resolver contract). Both are correct at
#       runtime. Hand-written config/graphql/core/* stays fully checked.
# flake8: noqa: E501, F821 — generated strawberry schema module.
# E501: long GraphQL field/argument ``description=`` strings and the
# single-line generated resolver signatures (black cannot split string
# literals). F821: ``Annotated["XType", strawberry.lazy(...)]`` /
# ``cast("QuerySet", ...)`` forward-reference STRINGS that pyflakes
# resolves as names — the whole point of strawberry.lazy is to avoid the
# import (which would then be F401). Both are code-generation artifacts,
# not defects; hand-written modules (config/graphql/core/*, security.py,
# testing.py, filters.py, …) stay fully linted.

from __future__ import annotations

import logging
from typing import Annotated

import strawberry
from graphql import GraphQLError
from graphql_relay import from_global_id

from config.graphql._util import strip_unset
from config.graphql.core.auth import PermissionDenied
from config.graphql.core.relay import (
    register_type,
)
from config.graphql.core.scalars import JSONString
from config.graphql.ratelimits import RateLimits, graphql_ratelimit
from opencontractserver.badges.models import Badge, UserBadge
from opencontractserver.corpuses.models import Corpus
from opencontractserver.shared.services.base import BaseService
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import (
    get_for_user_or_none,
    set_permissions_for_obj_to_user,
)

logger = logging.getLogger(__name__)

# NOTE on decorators: the graphene mutations were decorated with
# ``@login_required`` + ``@graphql_ratelimit(...)`` on ``mutate(root, info, …)``.
# Mutate stubs here take ``payload_cls`` as their first positional argument,
# which does not match those decorators' ``(root, info, ...)`` calling
# convention — so ``login_required`` is inlined (see user_mutations.py) and
# ``graphql_ratelimit`` is applied to an inner function named ``mutate`` so
# the rate-limit cache group (defaults to the decorated function's
# ``__name__``) stays "mutate", exactly as in the graphene layer.


@strawberry.type(
    name="CreateBadgeMutation",
    description="Create a new badge (admin/corpus owner only).",
)
class CreateBadgeMutation:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    badge: None | (
        Annotated[BadgeType, strawberry.lazy("config.graphql.social_types")]
    ) = strawberry.field(name="badge", default=None)


register_type("CreateBadgeMutation", CreateBadgeMutation, model=None)


@strawberry.type(name="UpdateBadgeMutation", description="Update an existing badge.")
class UpdateBadgeMutation:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    badge: None | (
        Annotated[BadgeType, strawberry.lazy("config.graphql.social_types")]
    ) = strawberry.field(name="badge", default=None)


register_type("UpdateBadgeMutation", UpdateBadgeMutation, model=None)


@strawberry.type(name="DeleteBadgeMutation", description="Delete a badge.")
class DeleteBadgeMutation:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)


register_type("DeleteBadgeMutation", DeleteBadgeMutation, model=None)


@strawberry.type(
    name="AwardBadgeMutation", description="Manually award a badge to a user."
)
class AwardBadgeMutation:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    user_badge: None | (
        Annotated[UserBadgeType, strawberry.lazy("config.graphql.social_types")]
    ) = strawberry.field(name="userBadge", default=None)


register_type("AwardBadgeMutation", AwardBadgeMutation, model=None)


@strawberry.type(name="RevokeBadgeMutation", description="Revoke a badge from a user.")
class RevokeBadgeMutation:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)


register_type("RevokeBadgeMutation", RevokeBadgeMutation, model=None)


def _mutate_CreateBadgeMutation(
    payload_cls,
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
    """PORT: /home/user/oc-graphene-ref/config/graphql/badge_mutations.py:59

    Port of CreateBadgeMutation.mutate
    """
    # @login_required — inlined (see module NOTE above).
    if not info.context.user.is_authenticated:
        raise PermissionDenied()

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
                # Service-layer IDOR-safe fetch + permission gate; both produce
                # the same unified "Corpus not found" message.
                corpus = BaseService.get_or_none(
                    Corpus, corpus_pk, user, request=info.context
                )
                if corpus is None or BaseService.require_permission(
                    corpus, user, PermissionTypes.UPDATE, request=info.context
                ):
                    return CreateBadgeMutation(
                        ok=False,
                        message="Corpus not found",
                        badge=None,
                    )
            elif not user.is_superuser:
                raise GraphQLError("You must be a superuser to create global badges.")

            # Validate criteria_config before attempting to create
            if is_auto_awarded:
                if not criteria_config:
                    return CreateBadgeMutation(
                        ok=False,
                        message="Auto-awarded badges must have criteria configuration",
                        badge=None,
                    )

                # Validate against registry
                from opencontractserver.badges.criteria_registry import (
                    BadgeCriteriaRegistry,
                )

                is_valid, error_message = BadgeCriteriaRegistry.validate_config(
                    criteria_config
                )
                if not is_valid:
                    return CreateBadgeMutation(
                        ok=False,
                        message=f"Invalid criteria configuration: {error_message}",
                        badge=None,
                    )

            elif criteria_config:
                return CreateBadgeMutation(
                    ok=False,
                    message="Only auto-awarded badges can have criteria configuration",
                    badge=None,
                )

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
            set_permissions_for_obj_to_user(
                user, badge, [PermissionTypes.CRUD], is_new=True, request=info.context
            )

            return CreateBadgeMutation(
                ok=True,
                message="Badge created successfully",
                badge=badge,
            )

        except Exception as e:
            logger.exception("Error creating badge")
            return CreateBadgeMutation(
                ok=False,
                message=f"Failed to create badge: {str(e)}",
                badge=None,
            )

    return mutate(
        root,
        info,
        name,
        description,
        icon,
        badge_type,
        color=color,
        corpus_id=corpus_id,
        is_auto_awarded=is_auto_awarded,
        criteria_config=criteria_config,
    )


def m_create_badge(
    info: strawberry.Info,
    badge_type: Annotated[
        str,
        strawberry.argument(
            name="badgeType", description="Badge type: GLOBAL or CORPUS"
        ),
    ] = strawberry.UNSET,
    color: Annotated[
        str | None, strawberry.argument(name="color", description="Hex color code")
    ] = strawberry.UNSET,
    corpus_id: Annotated[
        strawberry.ID | None,
        strawberry.argument(
            name="corpusId", description="Corpus ID for corpus-specific badges"
        ),
    ] = strawberry.UNSET,
    criteria_config: Annotated[
        JSONString | None,
        strawberry.argument(
            name="criteriaConfig",
            description="JSON configuration for auto-award criteria",
        ),
    ] = strawberry.UNSET,
    description: Annotated[
        str, strawberry.argument(name="description", description="Badge description")
    ] = strawberry.UNSET,
    icon: Annotated[
        str,
        strawberry.argument(
            name="icon",
            description="Icon identifier from lucide-react (e.g., 'Trophy')",
        ),
    ] = strawberry.UNSET,
    is_auto_awarded: Annotated[
        bool | None,
        strawberry.argument(
            name="isAutoAwarded", description="Whether badge is automatically awarded"
        ),
    ] = False,
    name: Annotated[
        str, strawberry.argument(name="name", description="Unique badge name")
    ] = strawberry.UNSET,
) -> CreateBadgeMutation | None:
    kwargs = strip_unset(
        {
            "badge_type": badge_type,
            "color": color,
            "corpus_id": corpus_id,
            "criteria_config": criteria_config,
            "description": description,
            "icon": icon,
            "is_auto_awarded": is_auto_awarded,
            "name": name,
        }
    )
    return _mutate_CreateBadgeMutation(CreateBadgeMutation, None, info, **kwargs)


def _mutate_UpdateBadgeMutation(
    payload_cls,
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
    """PORT: /home/user/oc-graphene-ref/config/graphql/badge_mutations.py:177

    Port of UpdateBadgeMutation.mutate
    """
    # @login_required — inlined (see module NOTE above).
    if not info.context.user.is_authenticated:
        raise PermissionDenied()

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
            # Service-layer IDOR-safe fetch.
            badge = BaseService.get_or_none(Badge, badge_pk, user, request=info.context)
            if badge is None:
                return UpdateBadgeMutation(
                    ok=False,
                    message="Badge not found",
                    badge=None,
                )

            # Permission check: For corpus badges, check corpus permissions
            # For global badges, must be superuser
            if badge.corpus:
                # Corpus badge - check if creator or has UPDATE permission
                if BaseService.require_permission(
                    badge.corpus, user, PermissionTypes.UPDATE, request=info.context
                ):
                    return UpdateBadgeMutation(
                        ok=False,
                        message="Badge not found",
                        badge=None,
                    )
            elif not user.is_superuser:
                # Global badge - must be superuser
                return UpdateBadgeMutation(
                    ok=False,
                    message="Badge not found",
                    badge=None,
                )

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

            # Validate criteria_config if badge will be auto-awarded
            # Check the final state after all updates
            final_is_auto_awarded = (
                is_auto_awarded
                if is_auto_awarded is not None
                else badge.is_auto_awarded
            )
            final_criteria_config = (
                criteria_config
                if criteria_config is not None
                else badge.criteria_config
            )

            if final_is_auto_awarded:
                if not final_criteria_config:
                    return UpdateBadgeMutation(
                        ok=False,
                        message="Auto-awarded badges must have criteria configuration",
                        badge=None,
                    )

                # Validate against registry
                from opencontractserver.badges.criteria_registry import (
                    BadgeCriteriaRegistry,
                )

                is_valid, error_message = BadgeCriteriaRegistry.validate_config(
                    final_criteria_config
                )
                if not is_valid:
                    return UpdateBadgeMutation(
                        ok=False,
                        message=f"Invalid criteria configuration: {error_message}",
                        badge=None,
                    )

            elif final_criteria_config:
                return UpdateBadgeMutation(
                    ok=False,
                    message="Only auto-awarded badges can have criteria configuration",
                    badge=None,
                )

            badge.save()

            return UpdateBadgeMutation(
                ok=True,
                message="Badge updated successfully",
                badge=badge,
            )

        except Exception as e:
            logger.exception("Error updating badge")
            return UpdateBadgeMutation(
                ok=False,
                message=f"Failed to update badge: {str(e)}",
                badge=None,
            )

    return mutate(
        root,
        info,
        badge_id,
        name=name,
        description=description,
        icon=icon,
        color=color,
        is_auto_awarded=is_auto_awarded,
        criteria_config=criteria_config,
    )


def m_update_badge(
    info: strawberry.Info,
    badge_id: Annotated[
        strawberry.ID,
        strawberry.argument(name="badgeId", description="Badge ID to update"),
    ] = strawberry.UNSET,
    color: Annotated[str | None, strawberry.argument(name="color")] = strawberry.UNSET,
    criteria_config: Annotated[
        JSONString | None, strawberry.argument(name="criteriaConfig")
    ] = strawberry.UNSET,
    description: Annotated[
        str | None, strawberry.argument(name="description")
    ] = strawberry.UNSET,
    icon: Annotated[str | None, strawberry.argument(name="icon")] = strawberry.UNSET,
    is_auto_awarded: Annotated[
        bool | None, strawberry.argument(name="isAutoAwarded")
    ] = strawberry.UNSET,
    name: Annotated[str | None, strawberry.argument(name="name")] = strawberry.UNSET,
) -> UpdateBadgeMutation | None:
    kwargs = strip_unset(
        {
            "badge_id": badge_id,
            "color": color,
            "criteria_config": criteria_config,
            "description": description,
            "icon": icon,
            "is_auto_awarded": is_auto_awarded,
            "name": name,
        }
    )
    return _mutate_UpdateBadgeMutation(UpdateBadgeMutation, None, info, **kwargs)


def _mutate_DeleteBadgeMutation(payload_cls, root, info, badge_id):
    """PORT: /home/user/oc-graphene-ref/config/graphql/badge_mutations.py:306

    Port of DeleteBadgeMutation.mutate
    """
    # @login_required — inlined (see module NOTE above).
    if not info.context.user.is_authenticated:
        raise PermissionDenied()

    @graphql_ratelimit(rate=RateLimits.WRITE_LIGHT)
    def mutate(root, info, badge_id):
        user = info.context.user

        try:
            badge_pk = from_global_id(badge_id)[1]
            # Service-layer IDOR-safe fetch.
            badge = BaseService.get_or_none(Badge, badge_pk, user, request=info.context)
            if badge is None:
                return DeleteBadgeMutation(
                    ok=False,
                    message="Badge not found",
                )

            # Permission check: For corpus badges, check corpus permissions
            # For global badges, must be superuser
            if badge.corpus:
                # Corpus badge - check if creator or has UPDATE permission
                if BaseService.require_permission(
                    badge.corpus, user, PermissionTypes.UPDATE, request=info.context
                ):
                    return DeleteBadgeMutation(
                        ok=False,
                        message="Badge not found",
                    )
            elif not user.is_superuser:
                # Global badge - must be superuser
                return DeleteBadgeMutation(
                    ok=False,
                    message="Badge not found",
                )

            badge.delete()

            return DeleteBadgeMutation(
                ok=True,
                message="Badge deleted successfully",
            )

        except Exception as e:
            logger.exception("Error deleting badge")
            return DeleteBadgeMutation(
                ok=False,
                message=f"Failed to delete badge: {str(e)}",
            )

    return mutate(root, info, badge_id)


def m_delete_badge(
    info: strawberry.Info,
    badge_id: Annotated[
        strawberry.ID,
        strawberry.argument(name="badgeId", description="Badge ID to delete"),
    ] = strawberry.UNSET,
) -> DeleteBadgeMutation | None:
    kwargs = strip_unset({"badge_id": badge_id})
    return _mutate_DeleteBadgeMutation(DeleteBadgeMutation, None, info, **kwargs)


def _mutate_AwardBadgeMutation(
    payload_cls, root, info, badge_id, user_id, corpus_id=None
):
    """PORT: /home/user/oc-graphene-ref/config/graphql/badge_mutations.py:368

    Port of AwardBadgeMutation.mutate
    """
    # @login_required — inlined (see module NOTE above).
    if not info.context.user.is_authenticated:
        raise PermissionDenied()

    @graphql_ratelimit(rate="5/m")  # More restrictive rate limit for awarding
    def mutate(root, info, badge_id, user_id, corpus_id=None):
        from django.contrib.auth import get_user_model

        User = get_user_model()
        awarder = info.context.user

        try:
            # Pre-guard ``from_global_id``: a malformed base64 id raises
            # before the helper is reached — return the same unified message
            # as a missing / hidden badge.
            try:
                badge_pk = from_global_id(badge_id)[1]
            except Exception:
                return AwardBadgeMutation(
                    ok=False, message="Badge not found", user_badge=None
                )
            badge = get_for_user_or_none(Badge, badge_pk, awarder)
            if badge is None:
                return AwardBadgeMutation(
                    ok=False, message="Badge not found", user_badge=None
                )

            corpus = None
            if corpus_id:
                try:
                    corpus_pk = from_global_id(corpus_id)[1]
                except Exception:
                    return AwardBadgeMutation(
                        ok=False, message="Corpus not found", user_badge=None
                    )
                corpus = get_for_user_or_none(Corpus, corpus_pk, awarder)
                if corpus is None:
                    return AwardBadgeMutation(
                        ok=False, message="Corpus not found", user_badge=None
                    )

            # Permission check: must be moderator/owner of the corpus or superuser
            # IDOR FIX: Return same "Badge not found" message as above to prevent enumeration
            if badge.badge_type == "CORPUS" and badge.corpus:
                # For corpus badges, check corpus permissions.
                if BaseService.require_permission(
                    badge.corpus,
                    awarder,
                    PermissionTypes.CRUD,
                    request=info.context,
                ):
                    return AwardBadgeMutation(
                        ok=False,
                        message="Badge not found",
                        user_badge=None,
                    )
            elif not awarder.is_superuser:
                return AwardBadgeMutation(
                    ok=False,
                    message="Badge not found",
                    user_badge=None,
                )

            # Awarding is authorized above (corpus CRUD for corpus badges, or
            # superuser for global badges). Resolve the recipient with a direct,
            # unfiltered lookup: awarding to a private-profile recipient is
            # legitimate once the awarder is authorized, so this no longer
            # depends on the awarder being able to *see* the recipient's profile
            # (scoped admin access, 2026-05). Running it after the authorization
            # gate also keeps the IDOR contract — an unauthorized caller gets
            # "Badge not found" before any recipient existence is revealed.
            try:
                recipient_pk = from_global_id(user_id)[1]
            except Exception:
                return AwardBadgeMutation(
                    ok=False, message="User not found", user_badge=None
                )
            recipient = User.objects.filter(pk=recipient_pk, is_active=True).first()
            if recipient is None:
                return AwardBadgeMutation(
                    ok=False, message="User not found", user_badge=None
                )

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

        except Exception as e:
            logger.exception("Error awarding badge")
            return AwardBadgeMutation(
                ok=False,
                message=f"Failed to award badge: {str(e)}",
                user_badge=None,
            )

    return mutate(root, info, badge_id, user_id, corpus_id=corpus_id)


def m_award_badge(
    info: strawberry.Info,
    badge_id: Annotated[
        strawberry.ID,
        strawberry.argument(name="badgeId", description="Badge ID to award"),
    ] = strawberry.UNSET,
    corpus_id: Annotated[
        strawberry.ID | None,
        strawberry.argument(
            name="corpusId", description="Corpus context for corpus-specific badges"
        ),
    ] = strawberry.UNSET,
    user_id: Annotated[
        strawberry.ID,
        strawberry.argument(name="userId", description="User ID to award badge to"),
    ] = strawberry.UNSET,
) -> AwardBadgeMutation | None:
    kwargs = strip_unset(
        {"badge_id": badge_id, "corpus_id": corpus_id, "user_id": user_id}
    )
    return _mutate_AwardBadgeMutation(AwardBadgeMutation, None, info, **kwargs)


def _mutate_RevokeBadgeMutation(payload_cls, root, info, user_badge_id):
    """PORT: /home/user/oc-graphene-ref/config/graphql/badge_mutations.py:488

    Port of RevokeBadgeMutation.mutate
    """
    # @login_required — inlined (see module NOTE above).
    if not info.context.user.is_authenticated:
        raise PermissionDenied()

    @graphql_ratelimit(rate=RateLimits.WRITE_LIGHT)
    def mutate(root, info, user_badge_id):
        user = info.context.user

        try:
            user_badge_pk = from_global_id(user_badge_id)[1]
            # IDOR FIX: Get user badge, but don't reveal existence vs. permission difference
            try:
                user_badge = UserBadge.objects.select_related("badge").get(
                    pk=user_badge_pk
                )
            except UserBadge.DoesNotExist:
                return RevokeBadgeMutation(
                    ok=False,
                    message="User badge not found",
                )

            # Permission check
            # IDOR FIX: Return same "User badge not found" message as above to prevent enumeration
            badge = user_badge.badge
            if badge.badge_type == "CORPUS" and badge.corpus:
                if BaseService.require_permission(
                    badge.corpus, user, PermissionTypes.CRUD, request=info.context
                ):
                    return RevokeBadgeMutation(
                        ok=False,
                        message="User badge not found",
                    )
            elif not user.is_superuser:
                return RevokeBadgeMutation(
                    ok=False,
                    message="User badge not found",
                )

            user_badge.delete()

            return RevokeBadgeMutation(
                ok=True,
                message="Badge revoked successfully",
            )

        except Exception as e:
            logger.exception("Error revoking badge")
            return RevokeBadgeMutation(
                ok=False,
                message=f"Failed to revoke badge: {str(e)}",
            )

    return mutate(root, info, user_badge_id)


def m_revoke_badge(
    info: strawberry.Info,
    user_badge_id: Annotated[
        strawberry.ID,
        strawberry.argument(name="userBadgeId", description="UserBadge ID to revoke"),
    ] = strawberry.UNSET,
) -> RevokeBadgeMutation | None:
    kwargs = strip_unset({"user_badge_id": user_badge_id})
    return _mutate_RevokeBadgeMutation(RevokeBadgeMutation, None, info, **kwargs)


MUTATION_FIELDS = {
    "create_badge": strawberry.field(
        resolver=m_create_badge,
        name="createBadge",
        description="Create a new badge (admin/corpus owner only).",
    ),
    "update_badge": strawberry.field(
        resolver=m_update_badge,
        name="updateBadge",
        description="Update an existing badge.",
    ),
    "delete_badge": strawberry.field(
        resolver=m_delete_badge, name="deleteBadge", description="Delete a badge."
    ),
    "award_badge": strawberry.field(
        resolver=m_award_badge,
        name="awardBadge",
        description="Manually award a badge to a user.",
    ),
    "revoke_badge": strawberry.field(
        resolver=m_revoke_badge,
        name="revokeBadge",
        description="Revoke a badge from a user.",
    ),
}
