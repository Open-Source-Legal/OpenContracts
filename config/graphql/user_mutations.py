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




@strawberry.type(name="ObtainJSONWebTokenWithUser")
class ObtainJSONWebTokenWithUser:
    payload: GenericScalar = strawberry.field(name="payload", default=None)
    refresh_expires_in: int = strawberry.field(name="refreshExpiresIn", default=None)
    user: Optional[Annotated["UserType", strawberry.lazy("config.graphql.user_types")]] = strawberry.field(name="user", default=None)
    token: str = strawberry.field(name="token", default=None)
    refresh_token: str = strawberry.field(name="refreshToken", default=None)


register_type("ObtainJSONWebTokenWithUser", ObtainJSONWebTokenWithUser, model=None)


@strawberry.type(name="UpdateMe", description='Update basic profile fields for the current user, including slug.')
class UpdateMe:
    ok: Optional[bool] = strawberry.field(name="ok", default=None)
    message: Optional[str] = strawberry.field(name="message", default=None)
    user: Optional[Annotated["UserType", strawberry.lazy("config.graphql.user_types")]] = strawberry.field(name="user", default=None)


register_type("UpdateMe", UpdateMe, model=None)


@strawberry.type(name="AcceptCookieConsent")
class AcceptCookieConsent:
    ok: Optional[bool] = strawberry.field(name="ok", default=None)


register_type("AcceptCookieConsent", AcceptCookieConsent, model=None)


@strawberry.type(name="DismissGettingStarted", description='Mutation to dismiss the getting-started guide for the current user.')
class DismissGettingStarted:
    ok: Optional[bool] = strawberry.field(name="ok", default=None)
    message: Optional[str] = strawberry.field(name="message", default=None)


register_type("DismissGettingStarted", DismissGettingStarted, model=None)


def _mutate_ObtainJSONWebTokenWithUser(payload_cls, root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/user_mutations.py:75

    Port of ObtainJSONWebTokenWithUser.mutate
    """
    raise NotImplementedError("_mutate_ObtainJSONWebTokenWithUser not yet ported — see manifest")


def m_token_auth(info: strawberry.Info, username: Annotated[str, strawberry.argument(name="username")] = strawberry.UNSET, password: Annotated[str, strawberry.argument(name="password")] = strawberry.UNSET) -> Optional["ObtainJSONWebTokenWithUser"]:
    kwargs = strip_unset({"username": username, "password": password})
    return _mutate_ObtainJSONWebTokenWithUser(ObtainJSONWebTokenWithUser, None, info, **kwargs)


def _mutate_UpdateMe(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:59

    Port of UpdateMe.mutate
    """
    raise NotImplementedError("_mutate_UpdateMe not yet ported — see manifest")


def m_update_me(info: strawberry.Info, first_name: Annotated[Optional[str], strawberry.argument(name="firstName")] = strawberry.UNSET, is_profile_public: Annotated[Optional[bool], strawberry.argument(name="isProfilePublic")] = strawberry.UNSET, last_name: Annotated[Optional[str], strawberry.argument(name="lastName")] = strawberry.UNSET, name: Annotated[Optional[str], strawberry.argument(name="name")] = strawberry.UNSET, phone: Annotated[Optional[str], strawberry.argument(name="phone")] = strawberry.UNSET, profile_about_markdown: Annotated[Optional[str], strawberry.argument(name="profileAboutMarkdown")] = strawberry.UNSET, profile_headline: Annotated[Optional[str], strawberry.argument(name="profileHeadline")] = strawberry.UNSET, profile_links_markdown: Annotated[Optional[str], strawberry.argument(name="profileLinksMarkdown")] = strawberry.UNSET, slug: Annotated[Optional[str], strawberry.argument(name="slug")] = strawberry.UNSET) -> Optional["UpdateMe"]:
    kwargs = strip_unset({"first_name": first_name, "is_profile_public": is_profile_public, "last_name": last_name, "name": name, "phone": phone, "profile_about_markdown": profile_about_markdown, "profile_headline": profile_headline, "profile_links_markdown": profile_links_markdown, "slug": slug})
    return _mutate_UpdateMe(UpdateMe, None, info, **kwargs)


def _mutate_AcceptCookieConsent(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:19

    Port of AcceptCookieConsent.mutate
    """
    raise NotImplementedError("_mutate_AcceptCookieConsent not yet ported — see manifest")


def m_accept_cookie_consent(info: strawberry.Info) -> Optional["AcceptCookieConsent"]:
    kwargs = strip_unset({})
    return _mutate_AcceptCookieConsent(AcceptCookieConsent, None, info, **kwargs)


def _mutate_DismissGettingStarted(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:33

    Port of DismissGettingStarted.mutate
    """
    raise NotImplementedError("_mutate_DismissGettingStarted not yet ported — see manifest")


def m_dismiss_getting_started(info: strawberry.Info) -> Optional["DismissGettingStarted"]:
    kwargs = strip_unset({})
    return _mutate_DismissGettingStarted(DismissGettingStarted, None, info, **kwargs)



MUTATION_FIELDS = {
    "token_auth": strawberry.field(resolver=m_token_auth, name="tokenAuth"),
    "update_me": strawberry.field(resolver=m_update_me, name="updateMe", description='Update basic profile fields for the current user, including slug.'),
    "accept_cookie_consent": strawberry.field(resolver=m_accept_cookie_consent, name="acceptCookieConsent"),
    "dismiss_getting_started": strawberry.field(resolver=m_dismiss_getting_started, name="dismissGettingStarted", description='Mutation to dismiss the getting-started guide for the current user.'),
}
