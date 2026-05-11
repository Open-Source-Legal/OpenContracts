"""
GraphQL mutations for user preference and authentication operations.
"""

import logging

import graphene
import graphql_jwt
from graphql_jwt.decorators import login_required

from config.graphql.graphene_types import UserType

logger = logging.getLogger(__name__)


class AcceptCookieConsent(graphene.Mutation):
    ok = graphene.Boolean()

    @login_required
    def mutate(root, info) -> "AcceptCookieConsent":
        user = info.context.user
        user.has_accepted_cookies = True
        user.save()
        return AcceptCookieConsent(ok=True)


class DismissGettingStarted(graphene.Mutation):
    """Mutation to dismiss the getting-started guide for the current user."""

    ok = graphene.Boolean()
    message = graphene.String()

    @login_required
    def mutate(root, info) -> "DismissGettingStarted":
        user = info.context.user
        user.has_dismissed_getting_started = True
        user.save()
        return DismissGettingStarted(ok=True, message="Getting started dismissed")


class UpdateMe(graphene.Mutation):
    """Update basic profile fields for the current user, including slug."""

    class Arguments:
        name = graphene.String(required=False)
        first_name = graphene.String(required=False)
        last_name = graphene.String(required=False)
        phone = graphene.String(required=False)
        slug = graphene.String(required=False)
        is_profile_public = graphene.Boolean(required=False)  # Issue #611
        profile_headline = graphene.String(required=False)
        profile_about_markdown = graphene.String(required=False)
        profile_links_markdown = graphene.String(required=False)

    ok = graphene.Boolean()
    message = graphene.String()
    user = graphene.Field(UserType)

    @login_required
    def mutate(self, info, **kwargs) -> "UpdateMe":
        from config.graphql.serializers import UserUpdateSerializer

        user = info.context.user
        try:
            serializer = UserUpdateSerializer(user, data=kwargs, partial=True)
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return UpdateMe(ok=True, message="Success", user=user)
        except Exception as e:
            return UpdateMe(
                ok=False, message=f"Failed to update profile: {e}", user=None
            )


class ObtainJSONWebTokenWithUser(graphql_jwt.ObtainJSONWebToken):
    user = graphene.Field(UserType)

    @classmethod
    def resolve(cls, root, info, **kwargs) -> "ObtainJSONWebTokenWithUser":
        return cls(user=info.context.user)
