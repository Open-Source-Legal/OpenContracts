"""Generated strawberry GraphQL module (graphene migration).

Shape-generated from the graphene schema; stub functions marked PORT(...)
carry the ported business logic. See config/graphql_new/manifest.json.
"""
from __future__ import annotations

import datetime
import decimal
import uuid
from typing import Annotated, Any, Optional

import strawberry

from config.graphql.core import permissions as core_permissions
from config.graphql.core.filtering import filterset_factory, setup_filterset
from config.graphql.core.mutations import drf_deletion, drf_mutation
from config.graphql.core.relay import (
    Node,
    get_node_from_global_id,
    make_connection_types,
    register_type,
    resolve_django_connection,
    resolve_django_list,
)
from config.graphql.core.scalars import BigInt, GenericScalar, JSONString
from config.graphql._util import coerce_enum, coerce_str, strip_unset
from config.graphql import enums




@strawberry.type(name="CreateBadgeMutation", description='Create a new badge (admin/corpus owner only).')
class CreateBadgeMutation:
    ok: Optional[bool] = strawberry.field(name="ok", default=None)
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))
    badge: Optional[Annotated["BadgeType", strawberry.lazy("config.graphql.social_types")]] = strawberry.field(name="badge", default=None)


register_type("CreateBadgeMutation", CreateBadgeMutation, model=None)


@strawberry.type(name="UpdateBadgeMutation", description='Update an existing badge.')
class UpdateBadgeMutation:
    ok: Optional[bool] = strawberry.field(name="ok", default=None)
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))
    badge: Optional[Annotated["BadgeType", strawberry.lazy("config.graphql.social_types")]] = strawberry.field(name="badge", default=None)


register_type("UpdateBadgeMutation", UpdateBadgeMutation, model=None)


@strawberry.type(name="DeleteBadgeMutation", description='Delete a badge.')
class DeleteBadgeMutation:
    ok: Optional[bool] = strawberry.field(name="ok", default=None)
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))


register_type("DeleteBadgeMutation", DeleteBadgeMutation, model=None)


@strawberry.type(name="AwardBadgeMutation", description='Manually award a badge to a user.')
class AwardBadgeMutation:
    ok: Optional[bool] = strawberry.field(name="ok", default=None)
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))
    user_badge: Optional[Annotated["UserBadgeType", strawberry.lazy("config.graphql.social_types")]] = strawberry.field(name="userBadge", default=None)


register_type("AwardBadgeMutation", AwardBadgeMutation, model=None)


@strawberry.type(name="RevokeBadgeMutation", description='Revoke a badge from a user.')
class RevokeBadgeMutation:
    ok: Optional[bool] = strawberry.field(name="ok", default=None)
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))


register_type("RevokeBadgeMutation", RevokeBadgeMutation, model=None)


def _mutate_CreateBadgeMutation(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:59

    Port of CreateBadgeMutation.mutate
    """
    raise NotImplementedError("_mutate_CreateBadgeMutation not yet ported — see manifest")


def m_create_badge(info: strawberry.Info, badge_type: Annotated[str, strawberry.argument(name="badgeType", description='Badge type: GLOBAL or CORPUS')] = strawberry.UNSET, color: Annotated[Optional[str], strawberry.argument(name="color", description='Hex color code')] = strawberry.UNSET, corpus_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="corpusId", description='Corpus ID for corpus-specific badges')] = strawberry.UNSET, criteria_config: Annotated[Optional[JSONString], strawberry.argument(name="criteriaConfig", description='JSON configuration for auto-award criteria')] = strawberry.UNSET, description: Annotated[str, strawberry.argument(name="description", description='Badge description')] = strawberry.UNSET, icon: Annotated[str, strawberry.argument(name="icon", description="Icon identifier from lucide-react (e.g., 'Trophy')")] = strawberry.UNSET, is_auto_awarded: Annotated[Optional[bool], strawberry.argument(name="isAutoAwarded", description='Whether badge is automatically awarded')] = False, name: Annotated[str, strawberry.argument(name="name", description='Unique badge name')] = strawberry.UNSET) -> Optional["CreateBadgeMutation"]:
    kwargs = strip_unset({"badge_type": badge_type, "color": color, "corpus_id": corpus_id, "criteria_config": criteria_config, "description": description, "icon": icon, "is_auto_awarded": is_auto_awarded, "name": name})
    return _mutate_CreateBadgeMutation(CreateBadgeMutation, None, info, **kwargs)


def _mutate_UpdateBadgeMutation(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:177

    Port of UpdateBadgeMutation.mutate
    """
    raise NotImplementedError("_mutate_UpdateBadgeMutation not yet ported — see manifest")


def m_update_badge(info: strawberry.Info, badge_id: Annotated[strawberry.ID, strawberry.argument(name="badgeId", description='Badge ID to update')] = strawberry.UNSET, color: Annotated[Optional[str], strawberry.argument(name="color")] = strawberry.UNSET, criteria_config: Annotated[Optional[JSONString], strawberry.argument(name="criteriaConfig")] = strawberry.UNSET, description: Annotated[Optional[str], strawberry.argument(name="description")] = strawberry.UNSET, icon: Annotated[Optional[str], strawberry.argument(name="icon")] = strawberry.UNSET, is_auto_awarded: Annotated[Optional[bool], strawberry.argument(name="isAutoAwarded")] = strawberry.UNSET, name: Annotated[Optional[str], strawberry.argument(name="name")] = strawberry.UNSET) -> Optional["UpdateBadgeMutation"]:
    kwargs = strip_unset({"badge_id": badge_id, "color": color, "criteria_config": criteria_config, "description": description, "icon": icon, "is_auto_awarded": is_auto_awarded, "name": name})
    return _mutate_UpdateBadgeMutation(UpdateBadgeMutation, None, info, **kwargs)


def _mutate_DeleteBadgeMutation(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:306

    Port of DeleteBadgeMutation.mutate
    """
    raise NotImplementedError("_mutate_DeleteBadgeMutation not yet ported — see manifest")


def m_delete_badge(info: strawberry.Info, badge_id: Annotated[strawberry.ID, strawberry.argument(name="badgeId", description='Badge ID to delete')] = strawberry.UNSET) -> Optional["DeleteBadgeMutation"]:
    kwargs = strip_unset({"badge_id": badge_id})
    return _mutate_DeleteBadgeMutation(DeleteBadgeMutation, None, info, **kwargs)


def _mutate_AwardBadgeMutation(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:368

    Port of AwardBadgeMutation.mutate
    """
    raise NotImplementedError("_mutate_AwardBadgeMutation not yet ported — see manifest")


def m_award_badge(info: strawberry.Info, badge_id: Annotated[strawberry.ID, strawberry.argument(name="badgeId", description='Badge ID to award')] = strawberry.UNSET, corpus_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="corpusId", description='Corpus context for corpus-specific badges')] = strawberry.UNSET, user_id: Annotated[strawberry.ID, strawberry.argument(name="userId", description='User ID to award badge to')] = strawberry.UNSET) -> Optional["AwardBadgeMutation"]:
    kwargs = strip_unset({"badge_id": badge_id, "corpus_id": corpus_id, "user_id": user_id})
    return _mutate_AwardBadgeMutation(AwardBadgeMutation, None, info, **kwargs)


def _mutate_RevokeBadgeMutation(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:488

    Port of RevokeBadgeMutation.mutate
    """
    raise NotImplementedError("_mutate_RevokeBadgeMutation not yet ported — see manifest")


def m_revoke_badge(info: strawberry.Info, user_badge_id: Annotated[strawberry.ID, strawberry.argument(name="userBadgeId", description='UserBadge ID to revoke')] = strawberry.UNSET) -> Optional["RevokeBadgeMutation"]:
    kwargs = strip_unset({"user_badge_id": user_badge_id})
    return _mutate_RevokeBadgeMutation(RevokeBadgeMutation, None, info, **kwargs)



MUTATION_FIELDS = {
    "create_badge": strawberry.field(resolver=m_create_badge, name="createBadge", description='Create a new badge (admin/corpus owner only).'),
    "update_badge": strawberry.field(resolver=m_update_badge, name="updateBadge", description='Update an existing badge.'),
    "delete_badge": strawberry.field(resolver=m_delete_badge, name="deleteBadge", description='Delete a badge.'),
    "award_badge": strawberry.field(resolver=m_award_badge, name="awardBadge", description='Manually award a badge to a user.'),
    "revoke_badge": strawberry.field(resolver=m_revoke_badge, name="revokeBadge", description='Revoke a badge from a user.'),
}
