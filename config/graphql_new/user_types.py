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
from config.graphql_new._util import coerce_enum, coerce_str, strip_unset
from config.graphql_new import enums

from config.graphql.filters import AnnotationFilter
from opencontractserver.agents.models import AgentActionResult
from opencontractserver.agents.models import AgentConfiguration
from opencontractserver.corpuses.models import CorpusAction
from opencontractserver.corpuses.models import CorpusActionExecution
from opencontractserver.feedback.models import UserFeedback
from opencontractserver.notifications.models import Notification
from opencontractserver.users.models import Assignment
from opencontractserver.users.models import User
from opencontractserver.users.models import UserExport
from opencontractserver.users.models import UserImport


def _resolve_UserType_username(root, info, **kwargs):
    """PORT: config/graphql/user_types.py:238

    Port of UserType.resolve_username
    """
    raise NotImplementedError("_resolve_UserType_username not yet ported — see manifest")


def _resolve_UserType_name(root, info, **kwargs):
    """PORT: config/graphql/user_types.py:241

    Port of UserType.resolve_name
    """
    raise NotImplementedError("_resolve_UserType_name not yet ported — see manifest")


def _resolve_UserType_first_name(root, info, **kwargs):
    """PORT: config/graphql/user_types.py:244

    Port of UserType.resolve_first_name
    """
    raise NotImplementedError("_resolve_UserType_first_name not yet ported — see manifest")


def _resolve_UserType_last_name(root, info, **kwargs):
    """PORT: config/graphql/user_types.py:247

    Port of UserType.resolve_last_name
    """
    raise NotImplementedError("_resolve_UserType_last_name not yet ported — see manifest")


def _resolve_UserType_given_name(root, info, **kwargs):
    """PORT: config/graphql/user_types.py:250

    Port of UserType.resolve_given_name
    """
    raise NotImplementedError("_resolve_UserType_given_name not yet ported — see manifest")


def _resolve_UserType_family_name(root, info, **kwargs):
    """PORT: config/graphql/user_types.py:253

    Port of UserType.resolve_family_name
    """
    raise NotImplementedError("_resolve_UserType_family_name not yet ported — see manifest")


def _resolve_UserType_phone(root, info, **kwargs):
    """PORT: config/graphql/user_types.py:256

    Port of UserType.resolve_phone
    """
    raise NotImplementedError("_resolve_UserType_phone not yet ported — see manifest")


def _resolve_UserType_email(root, info, **kwargs):
    """PORT: config/graphql/user_types.py:235

    Port of UserType.resolve_email
    """
    raise NotImplementedError("_resolve_UserType_email not yet ported — see manifest")


def _resolve_UserType_email_verified(root, info, **kwargs):
    """PORT: config/graphql/user_types.py:259

    Port of UserType.resolve_email_verified
    """
    raise NotImplementedError("_resolve_UserType_email_verified not yet ported — see manifest")


def _resolve_UserType_is_social_user(root, info, **kwargs):
    """PORT: config/graphql/user_types.py:264

    Port of UserType.resolve_is_social_user
    """
    raise NotImplementedError("_resolve_UserType_is_social_user not yet ported — see manifest")


def _resolve_UserType_is_usage_capped(root, info, **kwargs):
    """PORT: config/graphql/user_types.py:280

    Port of UserType.resolve_is_usage_capped
    """
    raise NotImplementedError("_resolve_UserType_is_usage_capped not yet ported — see manifest")


def _resolve_UserType_display_name(root, info, **kwargs):
    """PORT: config/graphql/user_types.py:291

    Port of UserType.resolve_display_name
    """
    raise NotImplementedError("_resolve_UserType_display_name not yet ported — see manifest")


def _resolve_UserType_reputation_global(root, info, **kwargs):
    """PORT: config/graphql/user_types.py:356

    Port of UserType.resolve_reputation_global
    """
    raise NotImplementedError("_resolve_UserType_reputation_global not yet ported — see manifest")


def _resolve_UserType_reputation_for_corpus(root, info, **kwargs):
    """PORT: config/graphql/user_types.py:375

    Port of UserType.resolve_reputation_for_corpus
    """
    raise NotImplementedError("_resolve_UserType_reputation_for_corpus not yet ported — see manifest")


def _resolve_UserType_total_messages(root, info, **kwargs):
    """PORT: config/graphql/user_types.py:389

    Port of UserType.resolve_total_messages
    """
    raise NotImplementedError("_resolve_UserType_total_messages not yet ported — see manifest")


def _resolve_UserType_total_threads_created(root, info, **kwargs):
    """PORT: config/graphql/user_types.py:403

    Port of UserType.resolve_total_threads_created
    """
    raise NotImplementedError("_resolve_UserType_total_threads_created not yet ported — see manifest")


def _resolve_UserType_total_annotations_created(root, info, **kwargs):
    """PORT: config/graphql/user_types.py:414

    Port of UserType.resolve_total_annotations_created
    """
    raise NotImplementedError("_resolve_UserType_total_annotations_created not yet ported — see manifest")


def _resolve_UserType_total_documents_uploaded(root, info, **kwargs):
    """PORT: config/graphql/user_types.py:426

    Port of UserType.resolve_total_documents_uploaded
    """
    raise NotImplementedError("_resolve_UserType_total_documents_uploaded not yet ported — see manifest")


def _resolve_UserType_can_import_corpus(root, info, **kwargs):
    """PORT: config/graphql/user_types.py:269

    Port of UserType.resolve_can_import_corpus
    """
    raise NotImplementedError("_resolve_UserType_can_import_corpus not yet ported — see manifest")


@strawberry.type(name="UserType")
class UserType(Node):
    is_superuser: bool = strawberry.field(name="isSuperuser", description='Designates that this user has all permissions without explicitly assigning them.')
    is_staff: bool = strawberry.field(name="isStaff", description='Designates whether the user can log into this admin site.')
    date_joined: datetime.datetime = strawberry.field(name="dateJoined")
    @strawberry.field(name="username", description='Login username. Self-only. For OAuth/social users this is the raw provider ``sub`` and must never be exposed cross-user — use ``slug`` or ``displayName`` for any UI that identifies a user.')
    def username(self, info: strawberry.Info) -> Optional[str]:
        kwargs = strip_unset({})
        return _resolve_UserType_username(self, info, **kwargs)
    @strawberry.field(name="name", description='Full name claim. Self-only.')
    def name(self, info: strawberry.Info) -> Optional[str]:
        kwargs = strip_unset({})
        return _resolve_UserType_name(self, info, **kwargs)
    @strawberry.field(name="firstName", description='First name. Self-only.')
    def first_name(self, info: strawberry.Info) -> Optional[str]:
        kwargs = strip_unset({})
        return _resolve_UserType_first_name(self, info, **kwargs)
    @strawberry.field(name="lastName", description='Last name. Self-only.')
    def last_name(self, info: strawberry.Info) -> Optional[str]:
        kwargs = strip_unset({})
        return _resolve_UserType_last_name(self, info, **kwargs)
    @strawberry.field(name="givenName", description='OIDC ``given_name`` claim. Self-only.')
    def given_name(self, info: strawberry.Info) -> Optional[str]:
        kwargs = strip_unset({})
        return _resolve_UserType_given_name(self, info, **kwargs)
    @strawberry.field(name="familyName", description='OIDC ``family_name`` claim. Self-only.')
    def family_name(self, info: strawberry.Info) -> Optional[str]:
        kwargs = strip_unset({})
        return _resolve_UserType_family_name(self, info, **kwargs)
    @strawberry.field(name="phone", description='Phone number. Self-only.')
    def phone(self, info: strawberry.Info) -> Optional[str]:
        kwargs = strip_unset({})
        return _resolve_UserType_phone(self, info, **kwargs)
    @strawberry.field(name="email", description='Email address. Returned **only** when the requesting user is viewing their own profile; ``null`` for everyone else, including superusers. Real PII reaches the GraphQL surface only via the ``me`` query / profile-settings flow.')
    def email(self, info: strawberry.Info) -> Optional[str]:
        kwargs = strip_unset({})
        return _resolve_UserType_email(self, info, **kwargs)
    is_active: bool = strawberry.field(name="isActive")
    @strawberry.field(name="emailVerified", description='Whether the user has verified their email. Self-only.')
    def email_verified(self, info: strawberry.Info) -> Optional[bool]:
        kwargs = strip_unset({})
        return _resolve_UserType_email_verified(self, info, **kwargs)
    @strawberry.field(name="isSocialUser", description='Whether the user signed in through a social/OAuth provider. Self-only — exposes account-shape information that could be used to fingerprint identity providers.')
    def is_social_user(self, info: strawberry.Info) -> Optional[bool]:
        kwargs = strip_unset({})
        return _resolve_UserType_is_social_user(self, info, **kwargs)
    @strawberry.field(name="isUsageCapped", description='Whether this user has exceeded their usage cap. Self-only — exposes paid/free account-tier status. Returns ``None`` for non-self viewers.')
    def is_usage_capped(self, info: strawberry.Info) -> Optional[bool]:
        kwargs = strip_unset({})
        return _resolve_UserType_is_usage_capped(self, info, **kwargs)
    @strawberry.field(name="slug", description='Case-sensitive URL slug. Allowed characters: A-Z, a-z, 0-9, and hyphen (-).')
    def slug(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "slug", None))
    @strawberry.field(name="handle", description="Auto-assigned Reddit-style handle (e.g. 'cleverFox', 'cleverFox42'). Used by the displayName resolver when Auth0 name claims are absent. User-facing editing is out of scope for the initial rollout.")
    def handle(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "handle", None))
    cookie_consent_accepted: bool = strawberry.field(name="cookieConsentAccepted", description='Whether the user has accepted cookie consent')
    cookie_consent_date: Optional[datetime.datetime] = strawberry.field(name="cookieConsentDate", description='When the user accepted cookie consent')
    is_profile_public: bool = strawberry.field(name="isProfilePublic", description="Whether this user's profile is visible to other users")
    @strawberry.field(name="profileHeadline", description='Short one-line tagline shown at the top of the profile page.')
    def profile_headline(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "profile_headline", None))
    @strawberry.field(name="profileAboutMarkdown", description='Free-form Markdown bio rendered on the public profile.')
    def profile_about_markdown(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "profile_about_markdown", None))
    @strawberry.field(name="profileLinksMarkdown", description='Markdown list of links rendered on the public profile.')
    def profile_links_markdown(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "profile_links_markdown", None))
    dismissed_getting_started: bool = strawberry.field(name="dismissedGettingStarted", description='Whether the user has dismissed the Getting Started guide on the Discover page')
    @strawberry.field(name="createdAssignments")
    def created_assignments(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> "AssignmentTypeConnection":
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "created_assignments", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="AssignmentType", )
    @strawberry.field(name="myAssignments")
    def my_assignments(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> "AssignmentTypeConnection":
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "my_assignments", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="AssignmentType", )
    @strawberry.field(name="userexportSet")
    def userexport_set(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> "UserExportTypeConnection":
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "userexport_set", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="UserExportType", )
    @strawberry.field(name="lockedUserexportObjects")
    def locked_userexport_objects(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> "UserExportTypeConnection":
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "locked_userexport_objects", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="UserExportType", )
    @strawberry.field(name="userimportSet")
    def userimport_set(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> "UserImportTypeConnection":
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "userimport_set", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="UserImportType", )
    @strawberry.field(name="lockedUserimportObjects")
    def locked_userimport_objects(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> "UserImportTypeConnection":
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "locked_userimport_objects", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="UserImportType", )
    @strawberry.field(name="lockedDocumentObjects")
    def locked_document_objects(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["DocumentTypeConnection", strawberry.lazy("config.graphql_new.document_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "locked_document_objects", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="DocumentType", )
    @strawberry.field(name="documentSet")
    def document_set(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["DocumentTypeConnection", strawberry.lazy("config.graphql_new.document_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "document_set", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="DocumentType", )
    @strawberry.field(name="lockedDocumentanalysisrowObjects")
    def locked_documentanalysisrow_objects(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["DocumentAnalysisRowTypeConnection", strawberry.lazy("config.graphql_new.document_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "locked_documentanalysisrow_objects", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="DocumentAnalysisRowType", )
    @strawberry.field(name="documentanalysisrowSet")
    def documentanalysisrow_set(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["DocumentAnalysisRowTypeConnection", strawberry.lazy("config.graphql_new.document_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "documentanalysisrow_set", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="DocumentAnalysisRowType", )
    @strawberry.field(name="lockedDocumentrelationshipObjects")
    def locked_documentrelationship_objects(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["DocumentRelationshipTypeConnection", strawberry.lazy("config.graphql_new.document_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "locked_documentrelationship_objects", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="DocumentRelationshipType", )
    @strawberry.field(name="documentrelationshipSet")
    def documentrelationship_set(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["DocumentRelationshipTypeConnection", strawberry.lazy("config.graphql_new.document_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "documentrelationship_set", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="DocumentRelationshipType", )
    @strawberry.field(name="lockedIngestionsourceObjects")
    def locked_ingestionsource_objects(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["IngestionSourceTypeConnection", strawberry.lazy("config.graphql_new.document_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "locked_ingestionsource_objects", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="IngestionSourceType", )
    @strawberry.field(name="ingestionsourceSet")
    def ingestionsource_set(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["IngestionSourceTypeConnection", strawberry.lazy("config.graphql_new.document_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "ingestionsource_set", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="IngestionSourceType", )
    @strawberry.field(name="lockedDocumentpathObjects")
    def locked_documentpath_objects(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["DocumentPathTypeConnection", strawberry.lazy("config.graphql_new.document_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "locked_documentpath_objects", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="DocumentPathType", )
    @strawberry.field(name="documentpathSet")
    def documentpath_set(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["DocumentPathTypeConnection", strawberry.lazy("config.graphql_new.document_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "documentpath_set", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="DocumentPathType", )
    @strawberry.field(name="documentSummaryRevisions")
    def document_summary_revisions(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["DocumentSummaryRevisionTypeConnection", strawberry.lazy("config.graphql_new.document_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "document_summary_revisions", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="DocumentSummaryRevisionType", )
    @strawberry.field(name="lockedCorpuscategoryObjects")
    def locked_corpuscategory_objects(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["CorpusCategoryTypeConnection", strawberry.lazy("config.graphql_new.corpus_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "locked_corpuscategory_objects", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="CorpusCategoryType", )
    @strawberry.field(name="corpuscategorySet")
    def corpuscategory_set(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["CorpusCategoryTypeConnection", strawberry.lazy("config.graphql_new.corpus_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "corpuscategory_set", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="CorpusCategoryType", )
    @strawberry.field(name="corpusSet")
    def corpus_set(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["CorpusTypeConnection", strawberry.lazy("config.graphql_new.corpus_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "corpus_set", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="CorpusType", )
    @strawberry.field(name="editingCorpuses")
    def editing_corpuses(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["CorpusTypeConnection", strawberry.lazy("config.graphql_new.corpus_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "editing_corpuses", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="CorpusType", )
    @strawberry.field(name="lockedCorpusactionObjects")
    def locked_corpusaction_objects(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET, id: Annotated[Optional[strawberry.ID], strawberry.argument(name="id")] = strawberry.UNSET, name: Annotated[Optional[str], strawberry.argument(name="name")] = strawberry.UNSET, name__icontains: Annotated[Optional[str], strawberry.argument(name="name_Icontains")] = strawberry.UNSET, name__istartswith: Annotated[Optional[str], strawberry.argument(name="name_Istartswith")] = strawberry.UNSET, corpus__id: Annotated[Optional[strawberry.ID], strawberry.argument(name="corpus_Id")] = strawberry.UNSET, fieldset__id: Annotated[Optional[strawberry.ID], strawberry.argument(name="fieldset_Id")] = strawberry.UNSET, analyzer__id: Annotated[Optional[strawberry.ID], strawberry.argument(name="analyzer_Id")] = strawberry.UNSET, agent_config__id: Annotated[Optional[strawberry.ID], strawberry.argument(name="agentConfig_Id")] = strawberry.UNSET, trigger: Annotated[Optional[enums.CorpusesCorpusActionTriggerChoices], strawberry.argument(name="trigger")] = strawberry.UNSET, creator__id: Annotated[Optional[strawberry.ID], strawberry.argument(name="creator_Id")] = strawberry.UNSET, source_template__id: Annotated[Optional[strawberry.ID], strawberry.argument(name="sourceTemplate_Id")] = strawberry.UNSET) -> Annotated["CorpusActionTypeConnection", strawberry.lazy("config.graphql_new.agent_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last, "id": id, "name": name, "name__icontains": name__icontains, "name__istartswith": name__istartswith, "corpus__id": corpus__id, "fieldset__id": fieldset__id, "analyzer__id": analyzer__id, "agent_config__id": agent_config__id, "trigger": trigger, "creator__id": creator__id, "source_template__id": source_template__id})
        resolved = getattr(self, "locked_corpusaction_objects", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="CorpusActionType", filterset_class=filterset_factory(CorpusAction, fields={'id': ['exact'], 'name': ['exact', 'icontains', 'istartswith'], 'corpus__id': ['exact'], 'fieldset__id': ['exact'], 'analyzer__id': ['exact'], 'agent_config__id': ['exact'], 'trigger': ['exact'], 'creator__id': ['exact'], 'source_template__id': ['exact']}), filter_args={"id": "id", "name": "name", "name__icontains": "name__icontains", "name__istartswith": "name__istartswith", "corpus__id": "corpus__id", "fieldset__id": "fieldset__id", "analyzer__id": "analyzer__id", "agent_config__id": "agent_config__id", "trigger": "trigger", "creator__id": "creator__id", "source_template__id": "source_template__id"}, )
    @strawberry.field(name="corpusactionSet")
    def corpusaction_set(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET, id: Annotated[Optional[strawberry.ID], strawberry.argument(name="id")] = strawberry.UNSET, name: Annotated[Optional[str], strawberry.argument(name="name")] = strawberry.UNSET, name__icontains: Annotated[Optional[str], strawberry.argument(name="name_Icontains")] = strawberry.UNSET, name__istartswith: Annotated[Optional[str], strawberry.argument(name="name_Istartswith")] = strawberry.UNSET, corpus__id: Annotated[Optional[strawberry.ID], strawberry.argument(name="corpus_Id")] = strawberry.UNSET, fieldset__id: Annotated[Optional[strawberry.ID], strawberry.argument(name="fieldset_Id")] = strawberry.UNSET, analyzer__id: Annotated[Optional[strawberry.ID], strawberry.argument(name="analyzer_Id")] = strawberry.UNSET, agent_config__id: Annotated[Optional[strawberry.ID], strawberry.argument(name="agentConfig_Id")] = strawberry.UNSET, trigger: Annotated[Optional[enums.CorpusesCorpusActionTriggerChoices], strawberry.argument(name="trigger")] = strawberry.UNSET, creator__id: Annotated[Optional[strawberry.ID], strawberry.argument(name="creator_Id")] = strawberry.UNSET, source_template__id: Annotated[Optional[strawberry.ID], strawberry.argument(name="sourceTemplate_Id")] = strawberry.UNSET) -> Annotated["CorpusActionTypeConnection", strawberry.lazy("config.graphql_new.agent_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last, "id": id, "name": name, "name__icontains": name__icontains, "name__istartswith": name__istartswith, "corpus__id": corpus__id, "fieldset__id": fieldset__id, "analyzer__id": analyzer__id, "agent_config__id": agent_config__id, "trigger": trigger, "creator__id": creator__id, "source_template__id": source_template__id})
        resolved = getattr(self, "corpusaction_set", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="CorpusActionType", filterset_class=filterset_factory(CorpusAction, fields={'id': ['exact'], 'name': ['exact', 'icontains', 'istartswith'], 'corpus__id': ['exact'], 'fieldset__id': ['exact'], 'analyzer__id': ['exact'], 'agent_config__id': ['exact'], 'trigger': ['exact'], 'creator__id': ['exact'], 'source_template__id': ['exact']}), filter_args={"id": "id", "name": "name", "name__icontains": "name__icontains", "name__istartswith": "name__istartswith", "corpus__id": "corpus__id", "fieldset__id": "fieldset__id", "analyzer__id": "analyzer__id", "agent_config__id": "agent_config__id", "trigger": "trigger", "creator__id": "creator__id", "source_template__id": "source_template__id"}, )
    @strawberry.field(name="corpusactiontemplateSet")
    def corpusactiontemplate_set(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["CorpusActionTemplateTypeConnection", strawberry.lazy("config.graphql_new.agent_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "corpusactiontemplate_set", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="CorpusActionTemplateType", )
    @strawberry.field(name="lockedCorpusactiontemplateObjects")
    def locked_corpusactiontemplate_objects(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["CorpusActionTemplateTypeConnection", strawberry.lazy("config.graphql_new.agent_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "locked_corpusactiontemplate_objects", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="CorpusActionTemplateType", )
    @strawberry.field(name="corpusfolderSet")
    def corpusfolder_set(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["CorpusFolderTypeConnection", strawberry.lazy("config.graphql_new.corpus_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "corpusfolder_set", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="CorpusFolderType", )
    @strawberry.field(name="lockedCorpusactionexecutionObjects")
    def locked_corpusactionexecution_objects(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET, id: Annotated[Optional[strawberry.ID], strawberry.argument(name="id")] = strawberry.UNSET, corpus__id: Annotated[Optional[strawberry.ID], strawberry.argument(name="corpus_Id")] = strawberry.UNSET, corpus_action__id: Annotated[Optional[strawberry.ID], strawberry.argument(name="corpusAction_Id")] = strawberry.UNSET, document__id: Annotated[Optional[strawberry.ID], strawberry.argument(name="document_Id")] = strawberry.UNSET, status: Annotated[Optional[enums.CorpusesCorpusActionExecutionStatusChoices], strawberry.argument(name="status")] = strawberry.UNSET, action_type: Annotated[Optional[enums.CorpusesCorpusActionExecutionActionTypeChoices], strawberry.argument(name="actionType")] = strawberry.UNSET, trigger: Annotated[Optional[enums.CorpusesCorpusActionExecutionTriggerChoices], strawberry.argument(name="trigger")] = strawberry.UNSET, creator__id: Annotated[Optional[strawberry.ID], strawberry.argument(name="creator_Id")] = strawberry.UNSET) -> Annotated["CorpusActionExecutionTypeConnection", strawberry.lazy("config.graphql_new.agent_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last, "id": id, "corpus__id": corpus__id, "corpus_action__id": corpus_action__id, "document__id": document__id, "status": status, "action_type": action_type, "trigger": trigger, "creator__id": creator__id})
        resolved = getattr(self, "locked_corpusactionexecution_objects", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="CorpusActionExecutionType", filterset_class=filterset_factory(CorpusActionExecution, fields={'id': ['exact'], 'corpus__id': ['exact'], 'corpus_action__id': ['exact'], 'document__id': ['exact'], 'status': ['exact'], 'action_type': ['exact'], 'trigger': ['exact'], 'creator__id': ['exact']}), filter_args={"id": "id", "corpus__id": "corpus__id", "corpus_action__id": "corpus_action__id", "document__id": "document__id", "status": "status", "action_type": "action_type", "trigger": "trigger", "creator__id": "creator__id"}, )
    @strawberry.field(name="corpusactionexecutionSet")
    def corpusactionexecution_set(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET, id: Annotated[Optional[strawberry.ID], strawberry.argument(name="id")] = strawberry.UNSET, corpus__id: Annotated[Optional[strawberry.ID], strawberry.argument(name="corpus_Id")] = strawberry.UNSET, corpus_action__id: Annotated[Optional[strawberry.ID], strawberry.argument(name="corpusAction_Id")] = strawberry.UNSET, document__id: Annotated[Optional[strawberry.ID], strawberry.argument(name="document_Id")] = strawberry.UNSET, status: Annotated[Optional[enums.CorpusesCorpusActionExecutionStatusChoices], strawberry.argument(name="status")] = strawberry.UNSET, action_type: Annotated[Optional[enums.CorpusesCorpusActionExecutionActionTypeChoices], strawberry.argument(name="actionType")] = strawberry.UNSET, trigger: Annotated[Optional[enums.CorpusesCorpusActionExecutionTriggerChoices], strawberry.argument(name="trigger")] = strawberry.UNSET, creator__id: Annotated[Optional[strawberry.ID], strawberry.argument(name="creator_Id")] = strawberry.UNSET) -> Annotated["CorpusActionExecutionTypeConnection", strawberry.lazy("config.graphql_new.agent_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last, "id": id, "corpus__id": corpus__id, "corpus_action__id": corpus_action__id, "document__id": document__id, "status": status, "action_type": action_type, "trigger": trigger, "creator__id": creator__id})
        resolved = getattr(self, "corpusactionexecution_set", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="CorpusActionExecutionType", filterset_class=filterset_factory(CorpusActionExecution, fields={'id': ['exact'], 'corpus__id': ['exact'], 'corpus_action__id': ['exact'], 'document__id': ['exact'], 'status': ['exact'], 'action_type': ['exact'], 'trigger': ['exact'], 'creator__id': ['exact']}), filter_args={"id": "id", "corpus__id": "corpus__id", "corpus_action__id": "corpus_action__id", "document__id": "document__id", "status": "status", "action_type": "action_type", "trigger": "trigger", "creator__id": "creator__id"}, )
    @strawberry.field(name="annotationlabelSet")
    def annotationlabel_set(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["AnnotationLabelTypeConnection", strawberry.lazy("config.graphql_new.annotation_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "annotationlabel_set", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="AnnotationLabelType", )
    @strawberry.field(name="lockedAnnotationlabelObjects")
    def locked_annotationlabel_objects(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["AnnotationLabelTypeConnection", strawberry.lazy("config.graphql_new.annotation_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "locked_annotationlabel_objects", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="AnnotationLabelType", )
    @strawberry.field(name="relationshipSet")
    def relationship_set(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["RelationshipTypeConnection", strawberry.lazy("config.graphql_new.annotation_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "relationship_set", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="RelationshipType", )
    @strawberry.field(name="lockedRelationshipObjects")
    def locked_relationship_objects(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["RelationshipTypeConnection", strawberry.lazy("config.graphql_new.annotation_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "locked_relationship_objects", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="RelationshipType", )
    @strawberry.field(name="annotationSet")
    def annotation_set(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET, raw_text__contains: Annotated[Optional[str], strawberry.argument(name="rawText_Contains")] = strawberry.UNSET, annotation_label_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="annotationLabelId")] = strawberry.UNSET, annotation_label__text: Annotated[Optional[str], strawberry.argument(name="annotationLabel_Text")] = strawberry.UNSET, annotation_label__text__contains: Annotated[Optional[str], strawberry.argument(name="annotationLabel_Text_Contains")] = strawberry.UNSET, annotation_label__description__contains: Annotated[Optional[str], strawberry.argument(name="annotationLabel_Description_Contains")] = strawberry.UNSET, annotation_label__label_type: Annotated[Optional[enums.AnnotationsAnnotationLabelLabelTypeChoices], strawberry.argument(name="annotationLabel_LabelType")] = strawberry.UNSET, analysis__isnull: Annotated[Optional[bool], strawberry.argument(name="analysis_Isnull")] = strawberry.UNSET, document_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="documentId")] = strawberry.UNSET, corpus_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="corpusId")] = strawberry.UNSET, structural: Annotated[Optional[bool], strawberry.argument(name="structural")] = strawberry.UNSET, uses_label_from_labelset_id: Annotated[Optional[str], strawberry.argument(name="usesLabelFromLabelsetId")] = strawberry.UNSET, created_by_analysis_ids: Annotated[Optional[str], strawberry.argument(name="createdByAnalysisIds")] = strawberry.UNSET, created_with_analyzer_id: Annotated[Optional[str], strawberry.argument(name="createdWithAnalyzerId")] = strawberry.UNSET, order_by: Annotated[Optional[str], strawberry.argument(name="orderBy", description='Ordering')] = strawberry.UNSET) -> Annotated["AnnotationTypeConnection", strawberry.lazy("config.graphql_new.annotation_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last, "raw_text__contains": raw_text__contains, "annotation_label_id": annotation_label_id, "annotation_label__text": annotation_label__text, "annotation_label__text__contains": annotation_label__text__contains, "annotation_label__description__contains": annotation_label__description__contains, "annotation_label__label_type": annotation_label__label_type, "analysis__isnull": analysis__isnull, "document_id": document_id, "corpus_id": corpus_id, "structural": structural, "uses_label_from_labelset_id": uses_label_from_labelset_id, "created_by_analysis_ids": created_by_analysis_ids, "created_with_analyzer_id": created_with_analyzer_id, "order_by": order_by})
        resolved = getattr(self, "annotation_set", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="AnnotationType", filterset_class=setup_filterset(AnnotationFilter), filter_args={"raw_text__contains": "raw_text__contains", "annotation_label_id": "annotation_label_id", "annotation_label__text": "annotation_label__text", "annotation_label__text__contains": "annotation_label__text__contains", "annotation_label__description__contains": "annotation_label__description__contains", "annotation_label__label_type": "annotation_label__label_type", "analysis__isnull": "analysis__isnull", "document_id": "document_id", "corpus_id": "corpus_id", "structural": "structural", "uses_label_from_labelset_id": "uses_label_from_labelset_id", "created_by_analysis_ids": "created_by_analysis_ids", "created_with_analyzer_id": "created_with_analyzer_id", "order_by": "order_by"}, )
    @strawberry.field(name="lockedAnnotationObjects")
    def locked_annotation_objects(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET, raw_text__contains: Annotated[Optional[str], strawberry.argument(name="rawText_Contains")] = strawberry.UNSET, annotation_label_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="annotationLabelId")] = strawberry.UNSET, annotation_label__text: Annotated[Optional[str], strawberry.argument(name="annotationLabel_Text")] = strawberry.UNSET, annotation_label__text__contains: Annotated[Optional[str], strawberry.argument(name="annotationLabel_Text_Contains")] = strawberry.UNSET, annotation_label__description__contains: Annotated[Optional[str], strawberry.argument(name="annotationLabel_Description_Contains")] = strawberry.UNSET, annotation_label__label_type: Annotated[Optional[enums.AnnotationsAnnotationLabelLabelTypeChoices], strawberry.argument(name="annotationLabel_LabelType")] = strawberry.UNSET, analysis__isnull: Annotated[Optional[bool], strawberry.argument(name="analysis_Isnull")] = strawberry.UNSET, document_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="documentId")] = strawberry.UNSET, corpus_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="corpusId")] = strawberry.UNSET, structural: Annotated[Optional[bool], strawberry.argument(name="structural")] = strawberry.UNSET, uses_label_from_labelset_id: Annotated[Optional[str], strawberry.argument(name="usesLabelFromLabelsetId")] = strawberry.UNSET, created_by_analysis_ids: Annotated[Optional[str], strawberry.argument(name="createdByAnalysisIds")] = strawberry.UNSET, created_with_analyzer_id: Annotated[Optional[str], strawberry.argument(name="createdWithAnalyzerId")] = strawberry.UNSET, order_by: Annotated[Optional[str], strawberry.argument(name="orderBy", description='Ordering')] = strawberry.UNSET) -> Annotated["AnnotationTypeConnection", strawberry.lazy("config.graphql_new.annotation_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last, "raw_text__contains": raw_text__contains, "annotation_label_id": annotation_label_id, "annotation_label__text": annotation_label__text, "annotation_label__text__contains": annotation_label__text__contains, "annotation_label__description__contains": annotation_label__description__contains, "annotation_label__label_type": annotation_label__label_type, "analysis__isnull": analysis__isnull, "document_id": document_id, "corpus_id": corpus_id, "structural": structural, "uses_label_from_labelset_id": uses_label_from_labelset_id, "created_by_analysis_ids": created_by_analysis_ids, "created_with_analyzer_id": created_with_analyzer_id, "order_by": order_by})
        resolved = getattr(self, "locked_annotation_objects", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="AnnotationType", filterset_class=setup_filterset(AnnotationFilter), filter_args={"raw_text__contains": "raw_text__contains", "annotation_label_id": "annotation_label_id", "annotation_label__text": "annotation_label__text", "annotation_label__text__contains": "annotation_label__text__contains", "annotation_label__description__contains": "annotation_label__description__contains", "annotation_label__label_type": "annotation_label__label_type", "analysis__isnull": "analysis__isnull", "document_id": "document_id", "corpus_id": "corpus_id", "structural": "structural", "uses_label_from_labelset_id": "uses_label_from_labelset_id", "created_by_analysis_ids": "created_by_analysis_ids", "created_with_analyzer_id": "created_with_analyzer_id", "order_by": "order_by"}, )
    @strawberry.field(name="lockedLabelsetObjects")
    def locked_labelset_objects(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["LabelSetTypeConnection", strawberry.lazy("config.graphql_new.annotation_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "locked_labelset_objects", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="LabelSetType", )
    @strawberry.field(name="labelsetSet")
    def labelset_set(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["LabelSetTypeConnection", strawberry.lazy("config.graphql_new.annotation_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "labelset_set", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="LabelSetType", )
    @strawberry.field(name="noteSet")
    def note_set(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["NoteTypeConnection", strawberry.lazy("config.graphql_new.annotation_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "note_set", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="NoteType", )
    @strawberry.field(name="lockedNoteObjects")
    def locked_note_objects(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["NoteTypeConnection", strawberry.lazy("config.graphql_new.annotation_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "locked_note_objects", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="NoteType", )
    @strawberry.field(name="noteRevisions")
    def note_revisions(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["NoteRevisionTypeConnection", strawberry.lazy("config.graphql_new.annotation_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "note_revisions", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="NoteRevisionType", )
    @strawberry.field(name="lockedCorpusreferenceObjects")
    def locked_corpusreference_objects(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["CorpusReferenceTypeConnection", strawberry.lazy("config.graphql_new.annotation_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "locked_corpusreference_objects", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="CorpusReferenceType", )
    @strawberry.field(name="corpusreferenceSet")
    def corpusreference_set(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["CorpusReferenceTypeConnection", strawberry.lazy("config.graphql_new.annotation_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "corpusreference_set", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="CorpusReferenceType", )
    @strawberry.field(name="authoredAuthorityNamespaces")
    def authored_authority_namespaces(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["AuthorityNamespaceNodeConnection", strawberry.lazy("config.graphql_new.annotation_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "authored_authority_namespaces", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="AuthorityNamespaceNode", )
    @strawberry.field(name="authoredAuthorityEquivalences")
    def authored_authority_equivalences(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["AuthorityKeyEquivalenceNodeConnection", strawberry.lazy("config.graphql_new.annotation_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "authored_authority_equivalences", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="AuthorityKeyEquivalenceNode", )
    @strawberry.field(name="lockedGremlinengineObjects")
    def locked_gremlinengine_objects(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["GremlinEngineType_WRITEConnection", strawberry.lazy("config.graphql_new.extract_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "locked_gremlinengine_objects", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="GremlinEngineType_WRITE", )
    @strawberry.field(name="gremlinengineSet")
    def gremlinengine_set(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["GremlinEngineType_WRITEConnection", strawberry.lazy("config.graphql_new.extract_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "gremlinengine_set", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="GremlinEngineType_WRITE", )
    @strawberry.field(name="lockedAnalyzerObjects")
    def locked_analyzer_objects(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["AnalyzerTypeConnection", strawberry.lazy("config.graphql_new.extract_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "locked_analyzer_objects", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="AnalyzerType", )
    @strawberry.field(name="analyzerSet")
    def analyzer_set(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["AnalyzerTypeConnection", strawberry.lazy("config.graphql_new.extract_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "analyzer_set", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="AnalyzerType", )
    @strawberry.field(name="analysisSet")
    def analysis_set(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["AnalysisTypeConnection", strawberry.lazy("config.graphql_new.extract_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "analysis_set", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="AnalysisType", )
    @strawberry.field(name="lockedAnalysisObjects")
    def locked_analysis_objects(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["AnalysisTypeConnection", strawberry.lazy("config.graphql_new.extract_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "locked_analysis_objects", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="AnalysisType", )
    @strawberry.field(name="lockedFieldsetObjects")
    def locked_fieldset_objects(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["FieldsetTypeConnection", strawberry.lazy("config.graphql_new.extract_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "locked_fieldset_objects", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="FieldsetType", )
    @strawberry.field(name="fieldsetSet")
    def fieldset_set(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["FieldsetTypeConnection", strawberry.lazy("config.graphql_new.extract_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "fieldset_set", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="FieldsetType", )
    @strawberry.field(name="lockedColumnObjects")
    def locked_column_objects(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["ColumnTypeConnection", strawberry.lazy("config.graphql_new.extract_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "locked_column_objects", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="ColumnType", )
    @strawberry.field(name="columnSet")
    def column_set(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["ColumnTypeConnection", strawberry.lazy("config.graphql_new.extract_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "column_set", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="ColumnType", )
    @strawberry.field(name="lockedExtractObjects")
    def locked_extract_objects(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["ExtractTypeConnection", strawberry.lazy("config.graphql_new.extract_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "locked_extract_objects", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="ExtractType", )
    @strawberry.field(name="extractSet")
    def extract_set(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["ExtractTypeConnection", strawberry.lazy("config.graphql_new.extract_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "extract_set", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="ExtractType", )
    @strawberry.field(name="approvedCells")
    def approved_cells(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["DatacellTypeConnection", strawberry.lazy("config.graphql_new.extract_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "approved_cells", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="DatacellType", )
    @strawberry.field(name="rejectedCells")
    def rejected_cells(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["DatacellTypeConnection", strawberry.lazy("config.graphql_new.extract_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "rejected_cells", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="DatacellType", )
    @strawberry.field(name="lockedDatacellObjects")
    def locked_datacell_objects(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["DatacellTypeConnection", strawberry.lazy("config.graphql_new.extract_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "locked_datacell_objects", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="DatacellType", )
    @strawberry.field(name="datacellSet")
    def datacell_set(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["DatacellTypeConnection", strawberry.lazy("config.graphql_new.extract_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "datacell_set", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="DatacellType", )
    @strawberry.field(name="lockedUserfeedbackObjects")
    def locked_userfeedback_objects(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> "UserFeedbackTypeConnection":
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "locked_userfeedback_objects", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="UserFeedbackType", )
    @strawberry.field(name="userfeedbackSet")
    def userfeedback_set(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> "UserFeedbackTypeConnection":
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "userfeedback_set", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="UserFeedbackType", )
    @strawberry.field(name="lockedConversations", description='Moderator who locked the thread')
    def locked_conversations(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["ConversationTypeConnection", strawberry.lazy("config.graphql_new.conversation_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "locked_conversations", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="ConversationType", )
    @strawberry.field(name="pinnedConversations", description='Moderator who pinned the thread')
    def pinned_conversations(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["ConversationTypeConnection", strawberry.lazy("config.graphql_new.conversation_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "pinned_conversations", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="ConversationType", )
    @strawberry.field(name="lockedConversationObjects")
    def locked_conversation_objects(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["ConversationTypeConnection", strawberry.lazy("config.graphql_new.conversation_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "locked_conversation_objects", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="ConversationType", )
    @strawberry.field(name="conversationSet")
    def conversation_set(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["ConversationTypeConnection", strawberry.lazy("config.graphql_new.conversation_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "conversation_set", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="ConversationType", )
    @strawberry.field(name="lockedChatmessageObjects")
    def locked_chatmessage_objects(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["MessageTypeConnection", strawberry.lazy("config.graphql_new.conversation_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "locked_chatmessage_objects", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="MessageType", )
    @strawberry.field(name="chatmessageSet")
    def chatmessage_set(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["MessageTypeConnection", strawberry.lazy("config.graphql_new.conversation_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "chatmessage_set", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="MessageType", )
    @strawberry.field(name="moderationActionsTaken", description='Moderator who took this action')
    def moderation_actions_taken(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["ModerationActionTypeConnection", strawberry.lazy("config.graphql_new.conversation_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "moderation_actions_taken", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="ModerationActionType", )
    @strawberry.field(name="lockedModerationactionObjects")
    def locked_moderationaction_objects(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["ModerationActionTypeConnection", strawberry.lazy("config.graphql_new.conversation_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "locked_moderationaction_objects", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="ModerationActionType", )
    @strawberry.field(name="moderationactionSet")
    def moderationaction_set(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["ModerationActionTypeConnection", strawberry.lazy("config.graphql_new.conversation_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "moderationaction_set", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="ModerationActionType", )
    @strawberry.field(name="lockedBadgeObjects")
    def locked_badge_objects(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["BadgeTypeConnection", strawberry.lazy("config.graphql_new.social_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "locked_badge_objects", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="BadgeType", )
    @strawberry.field(name="badgeSet")
    def badge_set(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["BadgeTypeConnection", strawberry.lazy("config.graphql_new.social_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "badge_set", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="BadgeType", )
    @strawberry.field(name="badges", description='User who received the badge')
    def badges(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["UserBadgeTypeConnection", strawberry.lazy("config.graphql_new.social_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "badges", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="UserBadgeType", )
    @strawberry.field(name="badgesAwarded", description='User who awarded the badge (null for auto-awards)')
    def badges_awarded(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["UserBadgeTypeConnection", strawberry.lazy("config.graphql_new.social_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "badges_awarded", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="UserBadgeType", )
    @strawberry.field(name="notifications", description='User receiving this notification')
    def notifications(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET, is_read: Annotated[Optional[bool], strawberry.argument(name="isRead")] = strawberry.UNSET, notification_type: Annotated[Optional[enums.NotificationsNotificationNotificationTypeChoices], strawberry.argument(name="notificationType")] = strawberry.UNSET, created_at__lte: Annotated[Optional[datetime.datetime], strawberry.argument(name="createdAt_Lte")] = strawberry.UNSET, created_at__gte: Annotated[Optional[datetime.datetime], strawberry.argument(name="createdAt_Gte")] = strawberry.UNSET) -> Annotated["NotificationTypeConnection", strawberry.lazy("config.graphql_new.social_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last, "is_read": is_read, "notification_type": notification_type, "created_at__lte": created_at__lte, "created_at__gte": created_at__gte})
        resolved = getattr(self, "notifications", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="NotificationType", filterset_class=filterset_factory(Notification, fields={'is_read': ['exact'], 'notification_type': ['exact'], 'created_at': ['lte', 'gte']}), filter_args={"is_read": "is_read", "notification_type": "notification_type", "created_at__lte": "created_at__lte", "created_at__gte": "created_at__gte"}, )
    @strawberry.field(name="notificationsTriggered", description='User who triggered this notification (if applicable)')
    def notifications_triggered(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET, is_read: Annotated[Optional[bool], strawberry.argument(name="isRead")] = strawberry.UNSET, notification_type: Annotated[Optional[enums.NotificationsNotificationNotificationTypeChoices], strawberry.argument(name="notificationType")] = strawberry.UNSET, created_at__lte: Annotated[Optional[datetime.datetime], strawberry.argument(name="createdAt_Lte")] = strawberry.UNSET, created_at__gte: Annotated[Optional[datetime.datetime], strawberry.argument(name="createdAt_Gte")] = strawberry.UNSET) -> Annotated["NotificationTypeConnection", strawberry.lazy("config.graphql_new.social_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last, "is_read": is_read, "notification_type": notification_type, "created_at__lte": created_at__lte, "created_at__gte": created_at__gte})
        resolved = getattr(self, "notifications_triggered", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="NotificationType", filterset_class=filterset_factory(Notification, fields={'is_read': ['exact'], 'notification_type': ['exact'], 'created_at': ['lte', 'gte']}), filter_args={"is_read": "is_read", "notification_type": "notification_type", "created_at__lte": "created_at__lte", "created_at__gte": "created_at__gte"}, )
    @strawberry.field(name="lockedAgentconfigurationObjects")
    def locked_agentconfiguration_objects(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET, scope: Annotated[Optional[enums.AgentsAgentConfigurationScopeChoices], strawberry.argument(name="scope")] = strawberry.UNSET, is_active: Annotated[Optional[bool], strawberry.argument(name="isActive")] = strawberry.UNSET, corpus: Annotated[Optional[strawberry.ID], strawberry.argument(name="corpus")] = strawberry.UNSET) -> Annotated["AgentConfigurationTypeConnection", strawberry.lazy("config.graphql_new.agent_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last, "scope": scope, "is_active": is_active, "corpus": corpus})
        resolved = getattr(self, "locked_agentconfiguration_objects", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="AgentConfigurationType", filterset_class=filterset_factory(AgentConfiguration, fields={'scope': ['exact'], 'is_active': ['exact'], 'corpus': ['exact']}), filter_args={"scope": "scope", "is_active": "is_active", "corpus": "corpus"}, )
    @strawberry.field(name="agentconfigurationSet")
    def agentconfiguration_set(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET, scope: Annotated[Optional[enums.AgentsAgentConfigurationScopeChoices], strawberry.argument(name="scope")] = strawberry.UNSET, is_active: Annotated[Optional[bool], strawberry.argument(name="isActive")] = strawberry.UNSET, corpus: Annotated[Optional[strawberry.ID], strawberry.argument(name="corpus")] = strawberry.UNSET) -> Annotated["AgentConfigurationTypeConnection", strawberry.lazy("config.graphql_new.agent_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last, "scope": scope, "is_active": is_active, "corpus": corpus})
        resolved = getattr(self, "agentconfiguration_set", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="AgentConfigurationType", filterset_class=filterset_factory(AgentConfiguration, fields={'scope': ['exact'], 'is_active': ['exact'], 'corpus': ['exact']}), filter_args={"scope": "scope", "is_active": "is_active", "corpus": "corpus"}, )
    @strawberry.field(name="lockedAgentactionresultObjects")
    def locked_agentactionresult_objects(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET, id: Annotated[Optional[strawberry.ID], strawberry.argument(name="id")] = strawberry.UNSET, corpus_action__id: Annotated[Optional[strawberry.ID], strawberry.argument(name="corpusAction_Id")] = strawberry.UNSET, document__id: Annotated[Optional[strawberry.ID], strawberry.argument(name="document_Id")] = strawberry.UNSET, status: Annotated[Optional[enums.AgentsAgentActionResultStatusChoices], strawberry.argument(name="status")] = strawberry.UNSET, creator__id: Annotated[Optional[strawberry.ID], strawberry.argument(name="creator_Id")] = strawberry.UNSET) -> Annotated["AgentActionResultTypeConnection", strawberry.lazy("config.graphql_new.agent_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last, "id": id, "corpus_action__id": corpus_action__id, "document__id": document__id, "status": status, "creator__id": creator__id})
        resolved = getattr(self, "locked_agentactionresult_objects", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="AgentActionResultType", filterset_class=filterset_factory(AgentActionResult, fields={'id': ['exact'], 'corpus_action__id': ['exact'], 'document__id': ['exact'], 'status': ['exact'], 'creator__id': ['exact']}), filter_args={"id": "id", "corpus_action__id": "corpus_action__id", "document__id": "document__id", "status": "status", "creator__id": "creator__id"}, )
    @strawberry.field(name="agentactionresultSet")
    def agentactionresult_set(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET, id: Annotated[Optional[strawberry.ID], strawberry.argument(name="id")] = strawberry.UNSET, corpus_action__id: Annotated[Optional[strawberry.ID], strawberry.argument(name="corpusAction_Id")] = strawberry.UNSET, document__id: Annotated[Optional[strawberry.ID], strawberry.argument(name="document_Id")] = strawberry.UNSET, status: Annotated[Optional[enums.AgentsAgentActionResultStatusChoices], strawberry.argument(name="status")] = strawberry.UNSET, creator__id: Annotated[Optional[strawberry.ID], strawberry.argument(name="creator_Id")] = strawberry.UNSET) -> Annotated["AgentActionResultTypeConnection", strawberry.lazy("config.graphql_new.agent_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last, "id": id, "corpus_action__id": corpus_action__id, "document__id": document__id, "status": status, "creator__id": creator__id})
        resolved = getattr(self, "agentactionresult_set", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="AgentActionResultType", filterset_class=filterset_factory(AgentActionResult, fields={'id': ['exact'], 'corpus_action__id': ['exact'], 'document__id': ['exact'], 'status': ['exact'], 'creator__id': ['exact']}), filter_args={"id": "id", "corpus_action__id": "corpus_action__id", "document__id": "document__id", "status": "status", "creator__id": "creator__id"}, )
    @strawberry.field(name="lockedResearchreportObjects")
    def locked_researchreport_objects(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["ResearchReportTypeConnection", strawberry.lazy("config.graphql_new.research_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "locked_researchreport_objects", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="ResearchReportType", )
    @strawberry.field(name="researchreportSet")
    def researchreport_set(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["ResearchReportTypeConnection", strawberry.lazy("config.graphql_new.research_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "researchreport_set", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="ResearchReportType", )
    @strawberry.field(name="myPermissions")
    def my_permissions(self, info: strawberry.Info) -> Optional[GenericScalar]:
        return core_permissions.resolve_my_permissions(self, info)
    @strawberry.field(name="isPublished")
    def is_published(self, info: strawberry.Info) -> Optional[bool]:
        return core_permissions.resolve_is_published(self, info)
    @strawberry.field(name="objectSharedWith")
    def object_shared_with(self, info: strawberry.Info) -> Optional[GenericScalar]:
        return core_permissions.resolve_object_shared_with(self, info)
    @strawberry.field(name="displayName", description="Privacy-preserving display name. Non-self viewers always receive the user's ``slug`` (or a redacted ``user_<pk-suffix>`` fallback when no slug exists). Self-views walk the rich PII-safe fallback chain so personal-settings UIs greet the user with their chosen name. Self-view chain: name → given_name + family_name → first_name + last_name → auto-assigned handle → username (local users only) → redacted 'user_<sub_suffix>' for social users → redacted 'user_<pk-suffix>'. The raw OAuth ``provider|sub`` value used as the Django ``username`` for social-login users is never returned.")
    def display_name(self, info: strawberry.Info) -> Optional[str]:
        kwargs = strip_unset({})
        return _resolve_UserType_display_name(self, info, **kwargs)
    @strawberry.field(name="reputationGlobal", description='Global reputation score across all corpuses')
    def reputation_global(self, info: strawberry.Info) -> Optional[int]:
        kwargs = strip_unset({})
        return _resolve_UserType_reputation_global(self, info, **kwargs)
    @strawberry.field(name="reputationForCorpus", description='Reputation score for a specific corpus')
    def reputation_for_corpus(self, info: strawberry.Info, corpus_id: Annotated[strawberry.ID, strawberry.argument(name="corpusId")] = strawberry.UNSET) -> Optional[int]:
        kwargs = strip_unset({"corpus_id": corpus_id})
        return _resolve_UserType_reputation_for_corpus(self, info, **kwargs)
    @strawberry.field(name="totalMessages", description='Total number of messages posted by this user')
    def total_messages(self, info: strawberry.Info) -> Optional[int]:
        kwargs = strip_unset({})
        return _resolve_UserType_total_messages(self, info, **kwargs)
    @strawberry.field(name="totalThreadsCreated", description='Total number of threads created by this user')
    def total_threads_created(self, info: strawberry.Info) -> Optional[int]:
        kwargs = strip_unset({})
        return _resolve_UserType_total_threads_created(self, info, **kwargs)
    @strawberry.field(name="totalAnnotationsCreated", description='Total number of annotations created by this user (visible to requester)')
    def total_annotations_created(self, info: strawberry.Info) -> Optional[int]:
        kwargs = strip_unset({})
        return _resolve_UserType_total_annotations_created(self, info, **kwargs)
    @strawberry.field(name="totalDocumentsUploaded", description='Total number of documents uploaded by this user (visible to requester)')
    def total_documents_uploaded(self, info: strawberry.Info) -> Optional[int]:
        kwargs = strip_unset({})
        return _resolve_UserType_total_documents_uploaded(self, info, **kwargs)
    @strawberry.field(name="canImportCorpus", description='Whether this user is permitted to import a corpus. Self-only — this exposes account-tier (usage-capped) status, which is PII. Returns ``None`` for non-self viewers. Self-views see the same gate the server enforces in the corpus-export and zip-to-corpus REST import endpoints (/api/imports/corpus/, /api/imports/zip-to-corpus/): false for usage-capped users when USAGE_CAPPED_USER_CAN_IMPORT_CORPUS is disabled.')
    def can_import_corpus(self, info: strawberry.Info) -> Optional[bool]:
        kwargs = strip_unset({})
        return _resolve_UserType_can_import_corpus(self, info, **kwargs)


register_type("UserType", UserType, model=User)


UserTypeConnection = make_connection_types(UserType, type_name="UserTypeConnection", countable=True, pdf_page_aware=False)


@strawberry.type(name="AssignmentType")
class AssignmentType(Node):
    @strawberry.field(name="name")
    def name(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "name", None))
    document: Annotated["DocumentType", strawberry.lazy("config.graphql_new.document_types")] = strawberry.field(name="document")
    corpus: Optional[Annotated["CorpusType", strawberry.lazy("config.graphql_new.corpus_types")]] = strawberry.field(name="corpus")
    @strawberry.field(name="resultingAnnotations")
    def resulting_annotations(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET, raw_text__contains: Annotated[Optional[str], strawberry.argument(name="rawText_Contains")] = strawberry.UNSET, annotation_label_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="annotationLabelId")] = strawberry.UNSET, annotation_label__text: Annotated[Optional[str], strawberry.argument(name="annotationLabel_Text")] = strawberry.UNSET, annotation_label__text__contains: Annotated[Optional[str], strawberry.argument(name="annotationLabel_Text_Contains")] = strawberry.UNSET, annotation_label__description__contains: Annotated[Optional[str], strawberry.argument(name="annotationLabel_Description_Contains")] = strawberry.UNSET, annotation_label__label_type: Annotated[Optional[enums.AnnotationsAnnotationLabelLabelTypeChoices], strawberry.argument(name="annotationLabel_LabelType")] = strawberry.UNSET, analysis__isnull: Annotated[Optional[bool], strawberry.argument(name="analysis_Isnull")] = strawberry.UNSET, document_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="documentId")] = strawberry.UNSET, corpus_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="corpusId")] = strawberry.UNSET, structural: Annotated[Optional[bool], strawberry.argument(name="structural")] = strawberry.UNSET, uses_label_from_labelset_id: Annotated[Optional[str], strawberry.argument(name="usesLabelFromLabelsetId")] = strawberry.UNSET, created_by_analysis_ids: Annotated[Optional[str], strawberry.argument(name="createdByAnalysisIds")] = strawberry.UNSET, created_with_analyzer_id: Annotated[Optional[str], strawberry.argument(name="createdWithAnalyzerId")] = strawberry.UNSET, order_by: Annotated[Optional[str], strawberry.argument(name="orderBy", description='Ordering')] = strawberry.UNSET) -> Annotated["AnnotationTypeConnection", strawberry.lazy("config.graphql_new.annotation_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last, "raw_text__contains": raw_text__contains, "annotation_label_id": annotation_label_id, "annotation_label__text": annotation_label__text, "annotation_label__text__contains": annotation_label__text__contains, "annotation_label__description__contains": annotation_label__description__contains, "annotation_label__label_type": annotation_label__label_type, "analysis__isnull": analysis__isnull, "document_id": document_id, "corpus_id": corpus_id, "structural": structural, "uses_label_from_labelset_id": uses_label_from_labelset_id, "created_by_analysis_ids": created_by_analysis_ids, "created_with_analyzer_id": created_with_analyzer_id, "order_by": order_by})
        resolved = getattr(self, "resulting_annotations", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="AnnotationType", filterset_class=setup_filterset(AnnotationFilter), filter_args={"raw_text__contains": "raw_text__contains", "annotation_label_id": "annotation_label_id", "annotation_label__text": "annotation_label__text", "annotation_label__text__contains": "annotation_label__text__contains", "annotation_label__description__contains": "annotation_label__description__contains", "annotation_label__label_type": "annotation_label__label_type", "analysis__isnull": "analysis__isnull", "document_id": "document_id", "corpus_id": "corpus_id", "structural": "structural", "uses_label_from_labelset_id": "uses_label_from_labelset_id", "created_by_analysis_ids": "created_by_analysis_ids", "created_with_analyzer_id": "created_with_analyzer_id", "order_by": "order_by"}, )
    @strawberry.field(name="resultingRelationships")
    def resulting_relationships(self, info: strawberry.Info, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Annotated["RelationshipTypeConnection", strawberry.lazy("config.graphql_new.annotation_types")]:
        kwargs = strip_unset({"offset": offset, "before": before, "after": after, "first": first, "last": last})
        resolved = getattr(self, "resulting_relationships", None)
        return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="RelationshipType", )
    @strawberry.field(name="comments")
    def comments(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "comments", None))
    assignor: "UserType" = strawberry.field(name="assignor")
    assignee: Optional["UserType"] = strawberry.field(name="assignee")
    completed_at: Optional[datetime.datetime] = strawberry.field(name="completedAt")
    created: datetime.datetime = strawberry.field(name="created")
    modified: datetime.datetime = strawberry.field(name="modified")
    @strawberry.field(name="myPermissions")
    def my_permissions(self, info: strawberry.Info) -> Optional[GenericScalar]:
        return core_permissions.resolve_my_permissions(self, info)
    @strawberry.field(name="isPublished")
    def is_published(self, info: strawberry.Info) -> Optional[bool]:
        return core_permissions.resolve_is_published(self, info)
    @strawberry.field(name="objectSharedWith")
    def object_shared_with(self, info: strawberry.Info) -> Optional[GenericScalar]:
        return core_permissions.resolve_object_shared_with(self, info)


register_type("AssignmentType", AssignmentType, model=Assignment)


AssignmentTypeConnection = make_connection_types(AssignmentType, type_name="AssignmentTypeConnection", countable=True, pdf_page_aware=False)


@strawberry.type(name="UserFeedbackType")
class UserFeedbackType(Node):
    user_lock: Optional["UserType"] = strawberry.field(name="userLock")
    backend_lock: bool = strawberry.field(name="backendLock")
    is_public: bool = strawberry.field(name="isPublic")
    creator: "UserType" = strawberry.field(name="creator")
    created: datetime.datetime = strawberry.field(name="created")
    modified: datetime.datetime = strawberry.field(name="modified")
    approved: bool = strawberry.field(name="approved")
    rejected: bool = strawberry.field(name="rejected")
    @strawberry.field(name="comment")
    def comment(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "comment", None))
    @strawberry.field(name="markdown")
    def markdown(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "markdown", None))
    metadata: Optional[JSONString] = strawberry.field(name="metadata")
    commented_annotation: Optional[Annotated["AnnotationType", strawberry.lazy("config.graphql_new.annotation_types")]] = strawberry.field(name="commentedAnnotation")
    @strawberry.field(name="myPermissions")
    def my_permissions(self, info: strawberry.Info) -> Optional[GenericScalar]:
        return core_permissions.resolve_my_permissions(self, info)
    @strawberry.field(name="isPublished")
    def is_published(self, info: strawberry.Info) -> Optional[bool]:
        return core_permissions.resolve_is_published(self, info)
    @strawberry.field(name="objectSharedWith")
    def object_shared_with(self, info: strawberry.Info) -> Optional[GenericScalar]:
        return core_permissions.resolve_object_shared_with(self, info)


def _get_queryset_UserFeedbackType(queryset, info):
    """PORT: config.graphql.user_types.UserFeedbackType.get_queryset

    Port of UserFeedbackType.get_queryset
    """
    raise NotImplementedError("_get_queryset_UserFeedbackType not yet ported — see manifest")


register_type("UserFeedbackType", UserFeedbackType, model=UserFeedback, get_queryset=_get_queryset_UserFeedbackType)


UserFeedbackTypeConnection = make_connection_types(UserFeedbackType, type_name="UserFeedbackTypeConnection", countable=True, pdf_page_aware=False)


def _resolve_UserExportType_file(root, info, **kwargs):
    """PORT: config/graphql/user_types.py:465

    Port of UserExportType.resolve_file
    """
    raise NotImplementedError("_resolve_UserExportType_file not yet ported — see manifest")


@strawberry.type(name="UserExportType")
class UserExportType(Node):
    user_lock: Optional["UserType"] = strawberry.field(name="userLock")
    modified: datetime.datetime = strawberry.field(name="modified")
    @strawberry.field(name="file")
    def file(self, info: strawberry.Info) -> str:
        kwargs = strip_unset({})
        return _resolve_UserExportType_file(self, info, **kwargs)
    @strawberry.field(name="name")
    def name(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "name", None))
    created: datetime.datetime = strawberry.field(name="created")
    started: Optional[datetime.datetime] = strawberry.field(name="started")
    finished: Optional[datetime.datetime] = strawberry.field(name="finished")
    @strawberry.field(name="errors")
    def errors(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "errors", None))
    post_processors: JSONString = strawberry.field(name="postProcessors", description='List of fully qualified Python paths to post-processor functions')
    input_kwargs: Optional[JSONString] = strawberry.field(name="inputKwargs", description='Additional keyword arguments to pass to post-processors')
    @strawberry.field(name="format")
    def format(self, info: strawberry.Info) -> enums.UsersUserExportFormatChoices:
        return coerce_enum(enums.UsersUserExportFormatChoices, getattr(self, "format", None))
    backend_lock: bool = strawberry.field(name="backendLock")
    is_public: bool = strawberry.field(name="isPublic")
    creator: "UserType" = strawberry.field(name="creator")
    @strawberry.field(name="myPermissions")
    def my_permissions(self, info: strawberry.Info) -> Optional[GenericScalar]:
        return core_permissions.resolve_my_permissions(self, info)
    @strawberry.field(name="isPublished")
    def is_published(self, info: strawberry.Info) -> Optional[bool]:
        return core_permissions.resolve_is_published(self, info)
    @strawberry.field(name="objectSharedWith")
    def object_shared_with(self, info: strawberry.Info) -> Optional[GenericScalar]:
        return core_permissions.resolve_object_shared_with(self, info)


register_type("UserExportType", UserExportType, model=UserExport)


UserExportTypeConnection = make_connection_types(UserExportType, type_name="UserExportTypeConnection", countable=True, pdf_page_aware=False)


def _resolve_UserImportType_zip(root, info, **kwargs):
    """PORT: config/graphql/user_types.py:475

    Port of UserImportType.resolve_zip
    """
    raise NotImplementedError("_resolve_UserImportType_zip not yet ported — see manifest")


@strawberry.type(name="UserImportType")
class UserImportType(Node):
    user_lock: Optional["UserType"] = strawberry.field(name="userLock")
    backend_lock: bool = strawberry.field(name="backendLock")
    modified: datetime.datetime = strawberry.field(name="modified")
    @strawberry.field(name="zip")
    def zip(self, info: strawberry.Info) -> str:
        kwargs = strip_unset({})
        return _resolve_UserImportType_zip(self, info, **kwargs)
    @strawberry.field(name="name")
    def name(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "name", None))
    created: datetime.datetime = strawberry.field(name="created")
    started: Optional[datetime.datetime] = strawberry.field(name="started")
    finished: Optional[datetime.datetime] = strawberry.field(name="finished")
    @strawberry.field(name="errors")
    def errors(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "errors", None))
    is_public: bool = strawberry.field(name="isPublic")
    creator: "UserType" = strawberry.field(name="creator")
    @strawberry.field(name="myPermissions")
    def my_permissions(self, info: strawberry.Info) -> Optional[GenericScalar]:
        return core_permissions.resolve_my_permissions(self, info)
    @strawberry.field(name="isPublished")
    def is_published(self, info: strawberry.Info) -> Optional[bool]:
        return core_permissions.resolve_is_published(self, info)
    @strawberry.field(name="objectSharedWith")
    def object_shared_with(self, info: strawberry.Info) -> Optional[GenericScalar]:
        return core_permissions.resolve_object_shared_with(self, info)


register_type("UserImportType", UserImportType, model=UserImport)


UserImportTypeConnection = make_connection_types(UserImportType, type_name="UserImportTypeConnection", countable=True, pdf_page_aware=False)


@strawberry.type(name="BulkDocumentUploadStatusType", description='Type for checking the status of a bulk document upload job')
class BulkDocumentUploadStatusType:
    @strawberry.field(name="jobId")
    def job_id(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "job_id", None))
    success: Optional[bool] = strawberry.field(name="success")
    total_files: Optional[int] = strawberry.field(name="totalFiles")
    processed_files: Optional[int] = strawberry.field(name="processedFiles")
    skipped_files: Optional[int] = strawberry.field(name="skippedFiles")
    error_files: Optional[int] = strawberry.field(name="errorFiles")
    @strawberry.field(name="documentIds")
    def document_ids(self, info: strawberry.Info) -> Optional[list[Optional[str]]]:
        return coerce_str(getattr(self, "document_ids", None))
    @strawberry.field(name="errors")
    def errors(self, info: strawberry.Info) -> Optional[list[Optional[str]]]:
        return coerce_str(getattr(self, "errors", None))
    completed: Optional[bool] = strawberry.field(name="completed")


register_type("BulkDocumentUploadStatusType", BulkDocumentUploadStatusType, model=None)

