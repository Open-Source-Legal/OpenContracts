"""
GraphQL query mixin for user, assignment, import, and export queries.
"""

from __future__ import annotations

import warnings
from typing import TYPE_CHECKING, Any

import graphene
from django.db.models import Q, QuerySet
from graphene import relay
from graphene_django.fields import DjangoConnectionField
from graphene_django.filter import DjangoFilterConnectionField
from graphql import GraphQLError
from graphql_jwt.decorators import login_required
from graphql_relay import from_global_id

from config.graphql.filters import AssignmentFilter, ExportFilter
from config.graphql.graphene_types import (
    AssignmentType,
    UserExportType,
    UserImportType,
    UserType,
)
from opencontractserver.users.models import Assignment, UserExport, UserImport

if TYPE_CHECKING:
    from opencontractserver.users.models import User


class UserQueryMixin:
    """Query fields and resolvers for user, assignment, import, and export queries."""

    # USER RESOLVERS #####################################
    me = graphene.Field(UserType)
    user_by_slug = graphene.Field(UserType, slug=graphene.String(required=True))

    def resolve_me(self, info: graphene.ResolveInfo) -> User | None:
        user = info.context.user
        if not user.is_authenticated:
            return None
        return user

    def resolve_user_by_slug(
        self, info: graphene.ResolveInfo, slug: str
    ) -> User | None:
        """
        Resolve a user by their slug with profile privacy filtering.

        SECURITY: Respects is_profile_public and corpus membership visibility rules.
        Users are visible if:
        - Profile is public (is_profile_public=True)
        - Requesting user shares corpus membership with > READ permission
        - It's the requesting user's own profile
        """
        from django.contrib.auth import get_user_model

        from opencontractserver.users.query_optimizer import UserQueryOptimizer

        User = get_user_model()
        try:
            # Use visibility filtering instead of direct query
            return UserQueryOptimizer.get_visible_users(info.context.user).get(
                slug=slug
            )
        except User.DoesNotExist:
            return None

    # IMPORT RESOLVERS #####################################
    userimports = DjangoConnectionField(UserImportType)

    @login_required
    def resolve_userimports(
        self, info: graphene.ResolveInfo, **kwargs: Any
    ) -> QuerySet[UserImport]:
        return UserImport.objects.visible_to_user(info.context.user)

    userimport = relay.Node.Field(UserImportType)

    @login_required
    def resolve_userimport(
        self, info: graphene.ResolveInfo, **kwargs: Any
    ) -> UserImport:
        relay_id = kwargs.get("id")
        if relay_id is None:
            raise GraphQLError("UserImport id is required")
        django_pk = from_global_id(relay_id)[1]
        return UserImport.objects.visible_to_user(info.context.user).get(id=django_pk)

    # EXPORT RESOLVERS #####################################
    userexports = DjangoFilterConnectionField(
        UserExportType, filterset_class=ExportFilter
    )

    @login_required
    def resolve_userexports(
        self, info: graphene.ResolveInfo, **kwargs: Any
    ) -> QuerySet[UserExport]:
        return UserExport.objects.visible_to_user(info.context.user)

    userexport = relay.Node.Field(UserExportType)

    @login_required
    def resolve_userexport(
        self, info: graphene.ResolveInfo, **kwargs: Any
    ) -> UserExport:
        relay_id = kwargs.get("id")
        if relay_id is None:
            raise GraphQLError("UserExport id is required")
        django_pk = from_global_id(relay_id)[1]
        return UserExport.objects.visible_to_user(info.context.user).get(id=django_pk)

    # ASSIGNMENT RESOLVERS #####################################
    assignments = DjangoFilterConnectionField(
        AssignmentType, filterset_class=AssignmentFilter
    )

    @login_required
    def resolve_assignments(
        self, info: graphene.ResolveInfo, **kwargs: Any
    ) -> QuerySet[Assignment]:
        """
        Resolve assignments.

        DEPRECATED: Assignment feature is not currently used.
        See opencontractserver/users/models.py:202-206

        SECURITY: Users can only see assignments where they are the assignor or assignee.
        Superusers can see all assignments.
        """
        warnings.warn(
            "Assignment feature is deprecated and not in use", DeprecationWarning
        )

        user = info.context.user
        if user.is_superuser:
            return Assignment.objects.all()
        else:
            # User can see assignments they created or were assigned to
            return Assignment.objects.filter(Q(assignor=user) | Q(assignee=user))

    assignment = relay.Node.Field(AssignmentType)

    @login_required
    def resolve_assignment(
        self, info: graphene.ResolveInfo, **kwargs: Any
    ) -> Assignment:
        """
        Resolve a single assignment by ID.

        DEPRECATED: Assignment feature is not currently used.

        SECURITY: Uses direct query instead of broken visible_to_user
        (Assignment model doesn't have this method - it inherits from
        django.db.models.Model, not BaseOCModel).
        """
        warnings.warn(
            "Assignment feature is deprecated and not in use", DeprecationWarning
        )

        user = info.context.user
        relay_id = kwargs.get("id")
        if relay_id is None:
            raise GraphQLError("Assignment not found")
        django_pk = from_global_id(relay_id)[1]

        # Use direct query - Assignment model doesn't have visible_to_user manager
        if user.is_superuser:
            try:
                return Assignment.objects.get(id=django_pk)
            except Assignment.DoesNotExist:
                raise GraphQLError("Assignment not found")

        # Regular users can only see their own assignments
        try:
            return Assignment.objects.get(
                Q(id=django_pk) & (Q(assignor=user) | Q(assignee=user))
            )
        except Assignment.DoesNotExist:
            # Same error whether doesn't exist or no permission (IDOR protection)
            raise GraphQLError("Assignment not found")
