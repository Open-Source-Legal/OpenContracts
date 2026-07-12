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

import datetime
from typing import Annotated, Any

import strawberry
from django.conf import settings  # noqa: E402

from config.graphql import enums
from config.graphql._util import coerce_enum, coerce_str, strip_unset
from config.graphql.core import permissions as core_permissions
from config.graphql.core.filtering import filterset_factory, setup_filterset
from config.graphql.core.relay import (
    Node,
    make_connection_types,
    register_type,
    resolve_django_connection,
    resolve_visible_fk,
)
from config.graphql.core.scalars import GenericScalar, JSONString
from config.graphql.filters import AnnotationFilter
from opencontractserver.agents.models import AgentActionResult, AgentConfiguration
from opencontractserver.constants.auth import (  # noqa: E402
    OAUTH_SUB_DISPLAY_SUFFIX_LENGTH,
)
from opencontractserver.corpuses.models import CorpusAction, CorpusActionExecution
from opencontractserver.feedback.models import UserFeedback
from opencontractserver.notifications.models import Notification
from opencontractserver.shared.services.base import BaseService  # noqa: E402
from opencontractserver.users.models import Assignment, User, UserExport, UserImport

# ---------------------------------------------------------------------------
# Module-level helpers preserved from the graphene user_types module —
# imported by other GraphQL modules (og_metadata_queries, etc.).
# ---------------------------------------------------------------------------


def _stripped(value: object) -> str:
    """Return a trimmed string when ``value`` is a string, else empty."""
    return value.strip() if isinstance(value, str) else ""


def _is_self_view(user_obj: Any, info: Any) -> bool:
    """True iff the requester *is* the user object being resolved.

    Authentication is required: anonymous viewers, server-side ``None``
    contexts (e.g. internal callers passing ``info=None``), and deactivated
    accounts (``is_active=False``) all return ``False``. Superusers
    deliberately do not bypass this gate — PII access is reserved for
    Django admin, not the public GraphQL API.

    The ``is_active`` check is explicit because Django's
    ``AbstractBaseUser.is_authenticated`` is a ``True`` constant for any
    User instance regardless of activation status, and
    ``AuthenticationMiddleware`` does not invalidate sessions when an
    admin flips ``is_active=False``. Without this check, a deactivated
    user with a still-live session cookie would continue to read their
    own PII.
    """
    if info is None:
        return False
    context = getattr(info, "context", None)
    if context is None:
        return False
    requester = getattr(context, "user", None)
    if requester is None:
        return False
    if not getattr(requester, "is_authenticated", False):
        return False
    if not getattr(requester, "is_active", False):
        return False
    return requester.pk == user_obj.pk


def _self_only(user_obj: Any, info: Any, attr: str) -> Any | None:
    """Return ``user_obj.attr`` only when the requester is the user themselves.

    Returns ``None`` for non-self views, including superusers. The empty
    string is also normalised to ``None`` so clients can rely on ``null``
    as the universal "hidden / unset" sentinel.
    """
    if not _is_self_view(user_obj, info):
        return None
    value = getattr(user_obj, attr, None)
    if isinstance(value, str) and not value:
        return None
    return value


def redacted_handle(user_obj: Any) -> str:
    """Stable, non-PII fallback when no ``slug`` is available.

    Uses the user's primary key suffix so two distinct users never collide
    on the same fallback. Mirrors the ``user_<sub>`` shape used elsewhere
    so frontend code can format both consistently.

    Reads ``pk`` defensively: ``str(... or "")`` would silently coerce a
    falsy ``pk=0`` to the empty string and emit ``user_unknown``, which
    would alias every pk=0 user to the same handle. Autoincrement PKs
    never hit 0 in practice, but checking ``is None`` keeps the function
    correct for any backend that allows zero-valued primary keys.
    """
    pk = getattr(user_obj, "pk", None)
    pk_str = str(pk) if pk is not None else ""
    pk_suffix = pk_str[-OAUTH_SUB_DISPLAY_SUFFIX_LENGTH:]
    return f"user_{pk_suffix or 'unknown'}"


def _resolve_UserType_username(root, info, **kwargs):
    """PORT: config/graphql/user_types.py:238

    Port of UserType.resolve_username
    """
    return _self_only(root, info, "username")


def _resolve_UserType_name(root, info, **kwargs):
    """PORT: config/graphql/user_types.py:241

    Port of UserType.resolve_name
    """
    return _self_only(root, info, "name")


def _resolve_UserType_first_name(root, info, **kwargs):
    """PORT: config/graphql/user_types.py:244

    Port of UserType.resolve_first_name
    """
    return _self_only(root, info, "first_name")


def _resolve_UserType_last_name(root, info, **kwargs):
    """PORT: config/graphql/user_types.py:247

    Port of UserType.resolve_last_name
    """
    return _self_only(root, info, "last_name")


def _resolve_UserType_given_name(root, info, **kwargs):
    """PORT: config/graphql/user_types.py:250

    Port of UserType.resolve_given_name
    """
    return _self_only(root, info, "given_name")


def _resolve_UserType_family_name(root, info, **kwargs):
    """PORT: config/graphql/user_types.py:253

    Port of UserType.resolve_family_name
    """
    return _self_only(root, info, "family_name")


def _resolve_UserType_phone(root, info, **kwargs):
    """PORT: config/graphql/user_types.py:256

    Port of UserType.resolve_phone
    """
    return _self_only(root, info, "phone")


def _resolve_UserType_email(root, info, **kwargs):
    """PORT: config/graphql/user_types.py:235

    Port of UserType.resolve_email
    """
    return _self_only(root, info, "email")


def _resolve_UserType_email_verified(root, info, **kwargs):
    """PORT: config/graphql/user_types.py:259

    Port of UserType.resolve_email_verified
    """
    if not _is_self_view(root, info):
        return None
    return bool(getattr(root, "email_verified", False))


def _resolve_UserType_is_social_user(root, info, **kwargs):
    """PORT: config/graphql/user_types.py:264

    Port of UserType.resolve_is_social_user
    """
    if not _is_self_view(root, info):
        return None
    return bool(getattr(root, "is_social_user", False))


def _resolve_UserType_is_usage_capped(root, info, **kwargs):
    """PORT: config/graphql/user_types.py:280

    Port of UserType.resolve_is_usage_capped
    """
    # Account-tier signal — same self-only gate as
    # ``resolve_can_import_corpus``. Without this resolver the model
    # field ``User.is_usage_capped`` would be served raw to any
    # authenticated viewer, letting a client probe whether another
    # account is on a paid or free tier (the module docstring already
    # claims this is gated; the resolver was missing).
    if not _is_self_view(root, info):
        return None
    return bool(getattr(root, "is_usage_capped", False))


def _resolve_UserType_display_name(root, info, **kwargs):
    """PORT: config/graphql/user_types.py:291

    Port of UserType.resolve_display_name

    Pick the first non-empty branch of the display-name chain.

    Resolution order:
        1. ``name`` (Auth0 ``name`` claim).
        2. ``given_name`` + ``family_name`` (Auth0).
        3. ``first_name`` + ``last_name`` (local Django fields).
        4. ``handle`` (Reddit-style auto-assigned handle).
        5. ``username`` verbatim — ONLY when ``is_social_user=False``.
           ``UserUnicodeUsernameValidator`` (see
           ``opencontractserver/users/validators.py``) explicitly allows
           ``|`` in locally-chosen usernames, so a local username like
           ``alice|admin`` is legitimate and must NOT be redacted.
        6. ``user_<last N chars after the last "|">`` for social users.
           The raw OAuth ``sub`` (e.g. ``google-oauth2|114688...``) is
           never returned — ``rsplit("|", 1)[-1]`` strips the provider
           prefix even when the sub is short, and we keep only the last
           ``OAUTH_SUB_DISPLAY_SUFFIX_LENGTH`` chars.
        7. ``user_<pk>`` / ``user_unknown`` last-resort fallback. With a
           populated handle column (see migration 0028) this branch is
           effectively unreachable for any user touched by the backfill.

    Non-self viewers always get the user's ``slug`` (or a redacted
    ``user_<pk-suffix>`` fallback when slug is unset — should not
    happen post-migration, but is defensive against partial data).
    """
    if not _is_self_view(root, info):
        slug = _stripped(getattr(root, "slug", ""))
        return slug or redacted_handle(root)

    name = _stripped(getattr(root, "name", ""))
    if name:
        return name

    given = _stripped(getattr(root, "given_name", ""))
    family = _stripped(getattr(root, "family_name", ""))
    if given or family:
        return f"{given} {family}".strip()

    first = _stripped(getattr(root, "first_name", ""))
    last = _stripped(getattr(root, "last_name", ""))
    if first or last:
        return f"{first} {last}".strip()

    handle = _stripped(getattr(root, "handle", ""))
    if handle:
        return handle

    username = _stripped(getattr(root, "username", ""))
    is_social = bool(getattr(root, "is_social_user", False))

    # Local users get their chosen username verbatim. ``|`` is allowed
    # by ``UserUnicodeUsernameValidator``, so a ``|``-containing local
    # username like ``alice|admin`` is legitimate and not an OAuth sub.
    if username and not is_social:
        return username

    if username:
        # Social user — never surface the raw ``sub``. ``rsplit("|", 1)``
        # strips the provider prefix even when the sub is short.
        sub = username.rsplit("|", 1)[-1]
        return f"user_{sub[-OAUTH_SUB_DISPLAY_SUFFIX_LENGTH:]}"

    return redacted_handle(root)


def _resolve_UserType_reputation_global(root, info, **kwargs):
    """PORT: config/graphql/user_types.py:356

    Port of UserType.resolve_reputation_global

    Resolve global reputation for this user.

    Uses pre-attached _reputation_global from resolve_global_leaderboard
    to avoid N+1 queries. Falls back to database query for single-user
    lookups.
    """
    if hasattr(root, "_reputation_global") and root._reputation_global is not None:
        return root._reputation_global

    from opencontractserver.conversations.models import UserReputation

    try:
        rep = UserReputation.objects.get(user=root, corpus__isnull=True)
        return rep.reputation_score
    except UserReputation.DoesNotExist:
        return 0


def _resolve_UserType_reputation_for_corpus(root, info, corpus_id):
    """PORT: config/graphql/user_types.py:375

    Port of UserType.resolve_reputation_for_corpus
    """
    from graphql_relay import from_global_id

    from opencontractserver.conversations.models import UserReputation

    try:
        _, corpus_pk = from_global_id(corpus_id)
        rep = UserReputation.objects.get(user=root, corpus_id=corpus_pk)
        return rep.reputation_score
    except UserReputation.DoesNotExist:
        return 0
    except Exception:
        return 0


def _resolve_UserType_total_messages(root, info, **kwargs):
    """PORT: config/graphql/user_types.py:389

    Port of UserType.resolve_total_messages
    """
    from opencontractserver.conversations.models import (
        ChatMessage,
        MessageTypeChoices,
    )

    return (
        BaseService.filter_visible(ChatMessage, info.context.user, request=info.context)
        .filter(creator=root, msg_type=MessageTypeChoices.HUMAN)
        .count()
    )


def _resolve_UserType_total_threads_created(root, info, **kwargs):
    """PORT: config/graphql/user_types.py:403

    Port of UserType.resolve_total_threads_created
    """
    from opencontractserver.conversations.models import Conversation

    return (
        BaseService.filter_visible(
            Conversation, info.context.user, request=info.context
        )
        .filter(creator=root, conversation_type="thread")
        .count()
    )


def _resolve_UserType_total_annotations_created(root, info, **kwargs):
    """PORT: config/graphql/user_types.py:414

    Port of UserType.resolve_total_annotations_created
    """
    from opencontractserver.annotations.models import Annotation

    # Filter by visibility via service layer, then narrow to this creator.
    return (
        BaseService.filter_visible(Annotation, info.context.user, request=info.context)
        .filter(creator=root)
        .count()
    )


def _resolve_UserType_total_documents_uploaded(root, info, **kwargs):
    """PORT: config/graphql/user_types.py:426

    Port of UserType.resolve_total_documents_uploaded
    """
    from opencontractserver.documents.models import Document

    return (
        BaseService.filter_visible(Document, info.context.user, request=info.context)
        .filter(creator=root)
        .count()
    )


def _resolve_UserType_can_import_corpus(root, info, **kwargs):
    """PORT: config/graphql/user_types.py:269

    Port of UserType.resolve_can_import_corpus
    """
    # Self-only gate: ``is_usage_capped`` reflects account-tier status,
    # so exposing this cross-user would let any client probe whether
    # another account is paid/free. Returns ``None`` for non-self
    # viewers (parallel to the other PII resolvers above).
    if not _is_self_view(root, info):
        return None
    if root.is_usage_capped and not settings.USAGE_CAPPED_USER_CAN_IMPORT_CORPUS:
        return False
    return True


@strawberry.type(name="UserType")
class UserType(Node):
    is_superuser: bool = strawberry.field(
        name="isSuperuser",
        description="Designates that this user has all permissions without explicitly assigning them.",
        default=None,
    )
    is_staff: bool = strawberry.field(
        name="isStaff",
        description="Designates whether the user can log into this admin site.",
        default=None,
    )
    date_joined: datetime.datetime = strawberry.field(name="dateJoined", default=None)

    @strawberry.field(
        name="username",
        description="Login username. Self-only. For OAuth/social users this is the raw provider ``sub`` and must never be exposed cross-user — use ``slug`` or ``displayName`` for any UI that identifies a user.",
    )
    def username(self, info: strawberry.Info) -> str | None:
        kwargs = strip_unset({})
        return _resolve_UserType_username(self, info, **kwargs)

    @strawberry.field(name="name", description="Full name claim. Self-only.")
    def name(self, info: strawberry.Info) -> str | None:
        kwargs = strip_unset({})
        return _resolve_UserType_name(self, info, **kwargs)

    @strawberry.field(name="firstName", description="First name. Self-only.")
    def first_name(self, info: strawberry.Info) -> str | None:
        kwargs = strip_unset({})
        return _resolve_UserType_first_name(self, info, **kwargs)

    @strawberry.field(name="lastName", description="Last name. Self-only.")
    def last_name(self, info: strawberry.Info) -> str | None:
        kwargs = strip_unset({})
        return _resolve_UserType_last_name(self, info, **kwargs)

    @strawberry.field(
        name="givenName", description="OIDC ``given_name`` claim. Self-only."
    )
    def given_name(self, info: strawberry.Info) -> str | None:
        kwargs = strip_unset({})
        return _resolve_UserType_given_name(self, info, **kwargs)

    @strawberry.field(
        name="familyName", description="OIDC ``family_name`` claim. Self-only."
    )
    def family_name(self, info: strawberry.Info) -> str | None:
        kwargs = strip_unset({})
        return _resolve_UserType_family_name(self, info, **kwargs)

    @strawberry.field(name="phone", description="Phone number. Self-only.")
    def phone(self, info: strawberry.Info) -> str | None:
        kwargs = strip_unset({})
        return _resolve_UserType_phone(self, info, **kwargs)

    @strawberry.field(
        name="email",
        description="Email address. Returned **only** when the requesting user is viewing their own profile; ``null`` for everyone else, including superusers. Real PII reaches the GraphQL surface only via the ``me`` query / profile-settings flow.",
    )
    def email(self, info: strawberry.Info) -> str | None:
        kwargs = strip_unset({})
        return _resolve_UserType_email(self, info, **kwargs)

    is_active: bool = strawberry.field(name="isActive", default=None)

    @strawberry.field(
        name="emailVerified",
        description="Whether the user has verified their email. Self-only.",
    )
    def email_verified(self, info: strawberry.Info) -> bool | None:
        kwargs = strip_unset({})
        return _resolve_UserType_email_verified(self, info, **kwargs)

    @strawberry.field(
        name="isSocialUser",
        description="Whether the user signed in through a social/OAuth provider. Self-only — exposes account-shape information that could be used to fingerprint identity providers.",
    )
    def is_social_user(self, info: strawberry.Info) -> bool | None:
        kwargs = strip_unset({})
        return _resolve_UserType_is_social_user(self, info, **kwargs)

    @strawberry.field(
        name="isUsageCapped",
        description="Whether this user has exceeded their usage cap. Self-only — exposes paid/free account-tier status. Returns ``None`` for non-self viewers.",
    )
    def is_usage_capped(self, info: strawberry.Info) -> bool | None:
        kwargs = strip_unset({})
        return _resolve_UserType_is_usage_capped(self, info, **kwargs)

    @strawberry.field(
        name="slug",
        description="Case-sensitive URL slug. Allowed characters: A-Z, a-z, 0-9, and hyphen (-).",
    )
    def slug(self, info: strawberry.Info) -> str | None:
        return coerce_str(getattr(self, "slug", None))

    @strawberry.field(
        name="handle",
        description="Auto-assigned Reddit-style handle (e.g. 'cleverFox', 'cleverFox42'). Used by the displayName resolver when Auth0 name claims are absent. User-facing editing is out of scope for the initial rollout.",
    )
    def handle(self, info: strawberry.Info) -> str | None:
        return coerce_str(getattr(self, "handle", None))

    cookie_consent_accepted: bool = strawberry.field(
        name="cookieConsentAccepted",
        description="Whether the user has accepted cookie consent",
        default=None,
    )
    cookie_consent_date: datetime.datetime | None = strawberry.field(
        name="cookieConsentDate",
        description="When the user accepted cookie consent",
        default=None,
    )
    is_profile_public: bool = strawberry.field(
        name="isProfilePublic",
        description="Whether this user's profile is visible to other users",
        default=None,
    )

    @strawberry.field(
        name="profileHeadline",
        description="Short one-line tagline shown at the top of the profile page.",
    )
    def profile_headline(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "profile_headline", None))

    @strawberry.field(
        name="profileAboutMarkdown",
        description="Free-form Markdown bio rendered on the public profile.",
    )
    def profile_about_markdown(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "profile_about_markdown", None))

    @strawberry.field(
        name="profileLinksMarkdown",
        description="Markdown list of links rendered on the public profile.",
    )
    def profile_links_markdown(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "profile_links_markdown", None))

    dismissed_getting_started: bool = strawberry.field(
        name="dismissedGettingStarted",
        description="Whether the user has dismissed the Getting Started guide on the Discover page",
        default=None,
    )

    @strawberry.field(name="createdAssignments")
    def created_assignments(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> AssignmentTypeConnection:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "created_assignments", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="AssignmentType",
        )

    @strawberry.field(name="myAssignments")
    def my_assignments(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> AssignmentTypeConnection:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "my_assignments", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="AssignmentType",
        )

    @strawberry.field(name="userexportSet")
    def userexport_set(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> UserExportTypeConnection:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "userexport_set", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="UserExportType",
        )

    @strawberry.field(name="lockedUserexportObjects")
    def locked_userexport_objects(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> UserExportTypeConnection:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "locked_userexport_objects", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="UserExportType",
        )

    @strawberry.field(name="userimportSet")
    def userimport_set(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> UserImportTypeConnection:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "userimport_set", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="UserImportType",
        )

    @strawberry.field(name="lockedUserimportObjects")
    def locked_userimport_objects(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> UserImportTypeConnection:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "locked_userimport_objects", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="UserImportType",
        )

    @strawberry.field(name="lockedDocumentObjects")
    def locked_document_objects(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> Annotated[
        DocumentTypeConnection, strawberry.lazy("config.graphql.document_types")
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "locked_document_objects", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="DocumentType",
        )

    @strawberry.field(name="documentSet")
    def document_set(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> Annotated[
        DocumentTypeConnection, strawberry.lazy("config.graphql.document_types")
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "document_set", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="DocumentType",
        )

    @strawberry.field(name="lockedDocumentanalysisrowObjects")
    def locked_documentanalysisrow_objects(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> Annotated[
        DocumentAnalysisRowTypeConnection,
        strawberry.lazy("config.graphql.document_types"),
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "locked_documentanalysisrow_objects", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="DocumentAnalysisRowType",
        )

    @strawberry.field(name="documentanalysisrowSet")
    def documentanalysisrow_set(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> Annotated[
        DocumentAnalysisRowTypeConnection,
        strawberry.lazy("config.graphql.document_types"),
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "documentanalysisrow_set", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="DocumentAnalysisRowType",
        )

    @strawberry.field(name="lockedDocumentrelationshipObjects")
    def locked_documentrelationship_objects(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> Annotated[
        DocumentRelationshipTypeConnection,
        strawberry.lazy("config.graphql.document_types"),
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "locked_documentrelationship_objects", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="DocumentRelationshipType",
        )

    @strawberry.field(name="documentrelationshipSet")
    def documentrelationship_set(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> Annotated[
        DocumentRelationshipTypeConnection,
        strawberry.lazy("config.graphql.document_types"),
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "documentrelationship_set", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="DocumentRelationshipType",
        )

    @strawberry.field(name="lockedIngestionsourceObjects")
    def locked_ingestionsource_objects(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> Annotated[
        IngestionSourceTypeConnection,
        strawberry.lazy("config.graphql.document_types"),
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "locked_ingestionsource_objects", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="IngestionSourceType",
        )

    @strawberry.field(name="ingestionsourceSet")
    def ingestionsource_set(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> Annotated[
        IngestionSourceTypeConnection,
        strawberry.lazy("config.graphql.document_types"),
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "ingestionsource_set", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="IngestionSourceType",
        )

    @strawberry.field(name="lockedDocumentpathObjects")
    def locked_documentpath_objects(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> Annotated[
        DocumentPathTypeConnection, strawberry.lazy("config.graphql.document_types")
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "locked_documentpath_objects", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="DocumentPathType",
        )

    @strawberry.field(name="documentpathSet")
    def documentpath_set(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> Annotated[
        DocumentPathTypeConnection, strawberry.lazy("config.graphql.document_types")
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "documentpath_set", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="DocumentPathType",
        )

    @strawberry.field(name="documentSummaryRevisions")
    def document_summary_revisions(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> Annotated[
        DocumentSummaryRevisionTypeConnection,
        strawberry.lazy("config.graphql.document_types"),
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "document_summary_revisions", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="DocumentSummaryRevisionType",
        )

    @strawberry.field(name="lockedCorpuscategoryObjects")
    def locked_corpuscategory_objects(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> Annotated[
        CorpusCategoryTypeConnection, strawberry.lazy("config.graphql.corpus_types")
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "locked_corpuscategory_objects", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="CorpusCategoryType",
        )

    @strawberry.field(name="corpuscategorySet")
    def corpuscategory_set(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> Annotated[
        CorpusCategoryTypeConnection, strawberry.lazy("config.graphql.corpus_types")
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "corpuscategory_set", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="CorpusCategoryType",
        )

    @strawberry.field(name="corpusSet")
    def corpus_set(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> Annotated[
        CorpusTypeConnection, strawberry.lazy("config.graphql.corpus_types")
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "corpus_set", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="CorpusType",
        )

    @strawberry.field(name="editingCorpuses")
    def editing_corpuses(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> Annotated[
        CorpusTypeConnection, strawberry.lazy("config.graphql.corpus_types")
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "editing_corpuses", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="CorpusType",
        )

    @strawberry.field(name="lockedCorpusactionObjects")
    def locked_corpusaction_objects(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
        id: Annotated[
            strawberry.ID | None, strawberry.argument(name="id")
        ] = strawberry.UNSET,
        name: Annotated[
            str | None, strawberry.argument(name="name")
        ] = strawberry.UNSET,
        name__icontains: Annotated[
            str | None, strawberry.argument(name="name_Icontains")
        ] = strawberry.UNSET,
        name__istartswith: Annotated[
            str | None, strawberry.argument(name="name_Istartswith")
        ] = strawberry.UNSET,
        corpus__id: Annotated[
            strawberry.ID | None, strawberry.argument(name="corpus_Id")
        ] = strawberry.UNSET,
        fieldset__id: Annotated[
            strawberry.ID | None, strawberry.argument(name="fieldset_Id")
        ] = strawberry.UNSET,
        analyzer__id: Annotated[
            strawberry.ID | None, strawberry.argument(name="analyzer_Id")
        ] = strawberry.UNSET,
        agent_config__id: Annotated[
            strawberry.ID | None, strawberry.argument(name="agentConfig_Id")
        ] = strawberry.UNSET,
        trigger: Annotated[
            enums.CorpusesCorpusActionTriggerChoices | None,
            strawberry.argument(name="trigger"),
        ] = strawberry.UNSET,
        creator__id: Annotated[
            strawberry.ID | None, strawberry.argument(name="creator_Id")
        ] = strawberry.UNSET,
        source_template__id: Annotated[
            strawberry.ID | None, strawberry.argument(name="sourceTemplate_Id")
        ] = strawberry.UNSET,
    ) -> Annotated[
        CorpusActionTypeConnection, strawberry.lazy("config.graphql.agent_types")
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
                "id": id,
                "name": name,
                "name__icontains": name__icontains,
                "name__istartswith": name__istartswith,
                "corpus__id": corpus__id,
                "fieldset__id": fieldset__id,
                "analyzer__id": analyzer__id,
                "agent_config__id": agent_config__id,
                "trigger": trigger,
                "creator__id": creator__id,
                "source_template__id": source_template__id,
            }
        )
        resolved = getattr(self, "locked_corpusaction_objects", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="CorpusActionType",
            filterset_class=filterset_factory(
                CorpusAction,
                fields={
                    "id": ["exact"],
                    "name": ["exact", "icontains", "istartswith"],
                    "corpus__id": ["exact"],
                    "fieldset__id": ["exact"],
                    "analyzer__id": ["exact"],
                    "agent_config__id": ["exact"],
                    "trigger": ["exact"],
                    "creator__id": ["exact"],
                    "source_template__id": ["exact"],
                },
            ),
            filter_args={
                "id": "id",
                "name": "name",
                "name__icontains": "name__icontains",
                "name__istartswith": "name__istartswith",
                "corpus__id": "corpus__id",
                "fieldset__id": "fieldset__id",
                "analyzer__id": "analyzer__id",
                "agent_config__id": "agent_config__id",
                "trigger": "trigger",
                "creator__id": "creator__id",
                "source_template__id": "source_template__id",
            },
        )

    @strawberry.field(name="corpusactionSet")
    def corpusaction_set(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
        id: Annotated[
            strawberry.ID | None, strawberry.argument(name="id")
        ] = strawberry.UNSET,
        name: Annotated[
            str | None, strawberry.argument(name="name")
        ] = strawberry.UNSET,
        name__icontains: Annotated[
            str | None, strawberry.argument(name="name_Icontains")
        ] = strawberry.UNSET,
        name__istartswith: Annotated[
            str | None, strawberry.argument(name="name_Istartswith")
        ] = strawberry.UNSET,
        corpus__id: Annotated[
            strawberry.ID | None, strawberry.argument(name="corpus_Id")
        ] = strawberry.UNSET,
        fieldset__id: Annotated[
            strawberry.ID | None, strawberry.argument(name="fieldset_Id")
        ] = strawberry.UNSET,
        analyzer__id: Annotated[
            strawberry.ID | None, strawberry.argument(name="analyzer_Id")
        ] = strawberry.UNSET,
        agent_config__id: Annotated[
            strawberry.ID | None, strawberry.argument(name="agentConfig_Id")
        ] = strawberry.UNSET,
        trigger: Annotated[
            enums.CorpusesCorpusActionTriggerChoices | None,
            strawberry.argument(name="trigger"),
        ] = strawberry.UNSET,
        creator__id: Annotated[
            strawberry.ID | None, strawberry.argument(name="creator_Id")
        ] = strawberry.UNSET,
        source_template__id: Annotated[
            strawberry.ID | None, strawberry.argument(name="sourceTemplate_Id")
        ] = strawberry.UNSET,
    ) -> Annotated[
        CorpusActionTypeConnection, strawberry.lazy("config.graphql.agent_types")
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
                "id": id,
                "name": name,
                "name__icontains": name__icontains,
                "name__istartswith": name__istartswith,
                "corpus__id": corpus__id,
                "fieldset__id": fieldset__id,
                "analyzer__id": analyzer__id,
                "agent_config__id": agent_config__id,
                "trigger": trigger,
                "creator__id": creator__id,
                "source_template__id": source_template__id,
            }
        )
        resolved = getattr(self, "corpusaction_set", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="CorpusActionType",
            filterset_class=filterset_factory(
                CorpusAction,
                fields={
                    "id": ["exact"],
                    "name": ["exact", "icontains", "istartswith"],
                    "corpus__id": ["exact"],
                    "fieldset__id": ["exact"],
                    "analyzer__id": ["exact"],
                    "agent_config__id": ["exact"],
                    "trigger": ["exact"],
                    "creator__id": ["exact"],
                    "source_template__id": ["exact"],
                },
            ),
            filter_args={
                "id": "id",
                "name": "name",
                "name__icontains": "name__icontains",
                "name__istartswith": "name__istartswith",
                "corpus__id": "corpus__id",
                "fieldset__id": "fieldset__id",
                "analyzer__id": "analyzer__id",
                "agent_config__id": "agent_config__id",
                "trigger": "trigger",
                "creator__id": "creator__id",
                "source_template__id": "source_template__id",
            },
        )

    @strawberry.field(name="corpusactiontemplateSet")
    def corpusactiontemplate_set(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> Annotated[
        CorpusActionTemplateTypeConnection,
        strawberry.lazy("config.graphql.agent_types"),
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "corpusactiontemplate_set", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="CorpusActionTemplateType",
        )

    @strawberry.field(name="lockedCorpusactiontemplateObjects")
    def locked_corpusactiontemplate_objects(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> Annotated[
        CorpusActionTemplateTypeConnection,
        strawberry.lazy("config.graphql.agent_types"),
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "locked_corpusactiontemplate_objects", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="CorpusActionTemplateType",
        )

    @strawberry.field(name="corpusfolderSet")
    def corpusfolder_set(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> Annotated[
        CorpusFolderTypeConnection, strawberry.lazy("config.graphql.corpus_types")
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "corpusfolder_set", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="CorpusFolderType",
        )

    @strawberry.field(name="lockedCorpusactionexecutionObjects")
    def locked_corpusactionexecution_objects(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
        id: Annotated[
            strawberry.ID | None, strawberry.argument(name="id")
        ] = strawberry.UNSET,
        corpus__id: Annotated[
            strawberry.ID | None, strawberry.argument(name="corpus_Id")
        ] = strawberry.UNSET,
        corpus_action__id: Annotated[
            strawberry.ID | None, strawberry.argument(name="corpusAction_Id")
        ] = strawberry.UNSET,
        document__id: Annotated[
            strawberry.ID | None, strawberry.argument(name="document_Id")
        ] = strawberry.UNSET,
        status: Annotated[
            enums.CorpusesCorpusActionExecutionStatusChoices | None,
            strawberry.argument(name="status"),
        ] = strawberry.UNSET,
        action_type: Annotated[
            enums.CorpusesCorpusActionExecutionActionTypeChoices | None,
            strawberry.argument(name="actionType"),
        ] = strawberry.UNSET,
        trigger: Annotated[
            enums.CorpusesCorpusActionExecutionTriggerChoices | None,
            strawberry.argument(name="trigger"),
        ] = strawberry.UNSET,
        creator__id: Annotated[
            strawberry.ID | None, strawberry.argument(name="creator_Id")
        ] = strawberry.UNSET,
    ) -> Annotated[
        CorpusActionExecutionTypeConnection,
        strawberry.lazy("config.graphql.agent_types"),
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
                "id": id,
                "corpus__id": corpus__id,
                "corpus_action__id": corpus_action__id,
                "document__id": document__id,
                "status": status,
                "action_type": action_type,
                "trigger": trigger,
                "creator__id": creator__id,
            }
        )
        resolved = getattr(self, "locked_corpusactionexecution_objects", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="CorpusActionExecutionType",
            filterset_class=filterset_factory(
                CorpusActionExecution,
                fields={
                    "id": ["exact"],
                    "corpus__id": ["exact"],
                    "corpus_action__id": ["exact"],
                    "document__id": ["exact"],
                    "status": ["exact"],
                    "action_type": ["exact"],
                    "trigger": ["exact"],
                    "creator__id": ["exact"],
                },
            ),
            filter_args={
                "id": "id",
                "corpus__id": "corpus__id",
                "corpus_action__id": "corpus_action__id",
                "document__id": "document__id",
                "status": "status",
                "action_type": "action_type",
                "trigger": "trigger",
                "creator__id": "creator__id",
            },
        )

    @strawberry.field(name="corpusactionexecutionSet")
    def corpusactionexecution_set(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
        id: Annotated[
            strawberry.ID | None, strawberry.argument(name="id")
        ] = strawberry.UNSET,
        corpus__id: Annotated[
            strawberry.ID | None, strawberry.argument(name="corpus_Id")
        ] = strawberry.UNSET,
        corpus_action__id: Annotated[
            strawberry.ID | None, strawberry.argument(name="corpusAction_Id")
        ] = strawberry.UNSET,
        document__id: Annotated[
            strawberry.ID | None, strawberry.argument(name="document_Id")
        ] = strawberry.UNSET,
        status: Annotated[
            enums.CorpusesCorpusActionExecutionStatusChoices | None,
            strawberry.argument(name="status"),
        ] = strawberry.UNSET,
        action_type: Annotated[
            enums.CorpusesCorpusActionExecutionActionTypeChoices | None,
            strawberry.argument(name="actionType"),
        ] = strawberry.UNSET,
        trigger: Annotated[
            enums.CorpusesCorpusActionExecutionTriggerChoices | None,
            strawberry.argument(name="trigger"),
        ] = strawberry.UNSET,
        creator__id: Annotated[
            strawberry.ID | None, strawberry.argument(name="creator_Id")
        ] = strawberry.UNSET,
    ) -> Annotated[
        CorpusActionExecutionTypeConnection,
        strawberry.lazy("config.graphql.agent_types"),
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
                "id": id,
                "corpus__id": corpus__id,
                "corpus_action__id": corpus_action__id,
                "document__id": document__id,
                "status": status,
                "action_type": action_type,
                "trigger": trigger,
                "creator__id": creator__id,
            }
        )
        resolved = getattr(self, "corpusactionexecution_set", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="CorpusActionExecutionType",
            filterset_class=filterset_factory(
                CorpusActionExecution,
                fields={
                    "id": ["exact"],
                    "corpus__id": ["exact"],
                    "corpus_action__id": ["exact"],
                    "document__id": ["exact"],
                    "status": ["exact"],
                    "action_type": ["exact"],
                    "trigger": ["exact"],
                    "creator__id": ["exact"],
                },
            ),
            filter_args={
                "id": "id",
                "corpus__id": "corpus__id",
                "corpus_action__id": "corpus_action__id",
                "document__id": "document__id",
                "status": "status",
                "action_type": "action_type",
                "trigger": "trigger",
                "creator__id": "creator__id",
            },
        )

    @strawberry.field(name="annotationlabelSet")
    def annotationlabel_set(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> Annotated[
        AnnotationLabelTypeConnection,
        strawberry.lazy("config.graphql.annotation_types"),
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "annotationlabel_set", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="AnnotationLabelType",
        )

    @strawberry.field(name="lockedAnnotationlabelObjects")
    def locked_annotationlabel_objects(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> Annotated[
        AnnotationLabelTypeConnection,
        strawberry.lazy("config.graphql.annotation_types"),
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "locked_annotationlabel_objects", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="AnnotationLabelType",
        )

    @strawberry.field(name="relationshipSet")
    def relationship_set(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> Annotated[
        RelationshipTypeConnection, strawberry.lazy("config.graphql.annotation_types")
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "relationship_set", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="RelationshipType",
        )

    @strawberry.field(name="lockedRelationshipObjects")
    def locked_relationship_objects(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> Annotated[
        RelationshipTypeConnection, strawberry.lazy("config.graphql.annotation_types")
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "locked_relationship_objects", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="RelationshipType",
        )

    @strawberry.field(name="annotationSet")
    def annotation_set(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
        raw_text__contains: Annotated[
            str | None, strawberry.argument(name="rawText_Contains")
        ] = strawberry.UNSET,
        annotation_label_id: Annotated[
            strawberry.ID | None, strawberry.argument(name="annotationLabelId")
        ] = strawberry.UNSET,
        annotation_label__text: Annotated[
            str | None, strawberry.argument(name="annotationLabel_Text")
        ] = strawberry.UNSET,
        annotation_label__text__contains: Annotated[
            str | None, strawberry.argument(name="annotationLabel_Text_Contains")
        ] = strawberry.UNSET,
        annotation_label__description__contains: Annotated[
            str | None,
            strawberry.argument(name="annotationLabel_Description_Contains"),
        ] = strawberry.UNSET,
        annotation_label__label_type: Annotated[
            enums.AnnotationsAnnotationLabelLabelTypeChoices | None,
            strawberry.argument(name="annotationLabel_LabelType"),
        ] = strawberry.UNSET,
        analysis__isnull: Annotated[
            bool | None, strawberry.argument(name="analysis_Isnull")
        ] = strawberry.UNSET,
        document_id: Annotated[
            strawberry.ID | None, strawberry.argument(name="documentId")
        ] = strawberry.UNSET,
        corpus_id: Annotated[
            strawberry.ID | None, strawberry.argument(name="corpusId")
        ] = strawberry.UNSET,
        structural: Annotated[
            bool | None, strawberry.argument(name="structural")
        ] = strawberry.UNSET,
        uses_label_from_labelset_id: Annotated[
            str | None, strawberry.argument(name="usesLabelFromLabelsetId")
        ] = strawberry.UNSET,
        created_by_analysis_ids: Annotated[
            str | None, strawberry.argument(name="createdByAnalysisIds")
        ] = strawberry.UNSET,
        created_with_analyzer_id: Annotated[
            str | None, strawberry.argument(name="createdWithAnalyzerId")
        ] = strawberry.UNSET,
        order_by: Annotated[
            str | None, strawberry.argument(name="orderBy", description="Ordering")
        ] = strawberry.UNSET,
    ) -> Annotated[
        AnnotationTypeConnection, strawberry.lazy("config.graphql.annotation_types")
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
                "raw_text__contains": raw_text__contains,
                "annotation_label_id": annotation_label_id,
                "annotation_label__text": annotation_label__text,
                "annotation_label__text__contains": annotation_label__text__contains,
                "annotation_label__description__contains": annotation_label__description__contains,
                "annotation_label__label_type": annotation_label__label_type,
                "analysis__isnull": analysis__isnull,
                "document_id": document_id,
                "corpus_id": corpus_id,
                "structural": structural,
                "uses_label_from_labelset_id": uses_label_from_labelset_id,
                "created_by_analysis_ids": created_by_analysis_ids,
                "created_with_analyzer_id": created_with_analyzer_id,
                "order_by": order_by,
            }
        )
        resolved = getattr(self, "annotation_set", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="AnnotationType",
            filterset_class=setup_filterset(AnnotationFilter),
            filter_args={
                "raw_text__contains": "raw_text__contains",
                "annotation_label_id": "annotation_label_id",
                "annotation_label__text": "annotation_label__text",
                "annotation_label__text__contains": "annotation_label__text__contains",
                "annotation_label__description__contains": "annotation_label__description__contains",
                "annotation_label__label_type": "annotation_label__label_type",
                "analysis__isnull": "analysis__isnull",
                "document_id": "document_id",
                "corpus_id": "corpus_id",
                "structural": "structural",
                "uses_label_from_labelset_id": "uses_label_from_labelset_id",
                "created_by_analysis_ids": "created_by_analysis_ids",
                "created_with_analyzer_id": "created_with_analyzer_id",
                "order_by": "order_by",
            },
        )

    @strawberry.field(name="lockedAnnotationObjects")
    def locked_annotation_objects(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
        raw_text__contains: Annotated[
            str | None, strawberry.argument(name="rawText_Contains")
        ] = strawberry.UNSET,
        annotation_label_id: Annotated[
            strawberry.ID | None, strawberry.argument(name="annotationLabelId")
        ] = strawberry.UNSET,
        annotation_label__text: Annotated[
            str | None, strawberry.argument(name="annotationLabel_Text")
        ] = strawberry.UNSET,
        annotation_label__text__contains: Annotated[
            str | None, strawberry.argument(name="annotationLabel_Text_Contains")
        ] = strawberry.UNSET,
        annotation_label__description__contains: Annotated[
            str | None,
            strawberry.argument(name="annotationLabel_Description_Contains"),
        ] = strawberry.UNSET,
        annotation_label__label_type: Annotated[
            enums.AnnotationsAnnotationLabelLabelTypeChoices | None,
            strawberry.argument(name="annotationLabel_LabelType"),
        ] = strawberry.UNSET,
        analysis__isnull: Annotated[
            bool | None, strawberry.argument(name="analysis_Isnull")
        ] = strawberry.UNSET,
        document_id: Annotated[
            strawberry.ID | None, strawberry.argument(name="documentId")
        ] = strawberry.UNSET,
        corpus_id: Annotated[
            strawberry.ID | None, strawberry.argument(name="corpusId")
        ] = strawberry.UNSET,
        structural: Annotated[
            bool | None, strawberry.argument(name="structural")
        ] = strawberry.UNSET,
        uses_label_from_labelset_id: Annotated[
            str | None, strawberry.argument(name="usesLabelFromLabelsetId")
        ] = strawberry.UNSET,
        created_by_analysis_ids: Annotated[
            str | None, strawberry.argument(name="createdByAnalysisIds")
        ] = strawberry.UNSET,
        created_with_analyzer_id: Annotated[
            str | None, strawberry.argument(name="createdWithAnalyzerId")
        ] = strawberry.UNSET,
        order_by: Annotated[
            str | None, strawberry.argument(name="orderBy", description="Ordering")
        ] = strawberry.UNSET,
    ) -> Annotated[
        AnnotationTypeConnection, strawberry.lazy("config.graphql.annotation_types")
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
                "raw_text__contains": raw_text__contains,
                "annotation_label_id": annotation_label_id,
                "annotation_label__text": annotation_label__text,
                "annotation_label__text__contains": annotation_label__text__contains,
                "annotation_label__description__contains": annotation_label__description__contains,
                "annotation_label__label_type": annotation_label__label_type,
                "analysis__isnull": analysis__isnull,
                "document_id": document_id,
                "corpus_id": corpus_id,
                "structural": structural,
                "uses_label_from_labelset_id": uses_label_from_labelset_id,
                "created_by_analysis_ids": created_by_analysis_ids,
                "created_with_analyzer_id": created_with_analyzer_id,
                "order_by": order_by,
            }
        )
        resolved = getattr(self, "locked_annotation_objects", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="AnnotationType",
            filterset_class=setup_filterset(AnnotationFilter),
            filter_args={
                "raw_text__contains": "raw_text__contains",
                "annotation_label_id": "annotation_label_id",
                "annotation_label__text": "annotation_label__text",
                "annotation_label__text__contains": "annotation_label__text__contains",
                "annotation_label__description__contains": "annotation_label__description__contains",
                "annotation_label__label_type": "annotation_label__label_type",
                "analysis__isnull": "analysis__isnull",
                "document_id": "document_id",
                "corpus_id": "corpus_id",
                "structural": "structural",
                "uses_label_from_labelset_id": "uses_label_from_labelset_id",
                "created_by_analysis_ids": "created_by_analysis_ids",
                "created_with_analyzer_id": "created_with_analyzer_id",
                "order_by": "order_by",
            },
        )

    @strawberry.field(name="lockedLabelsetObjects")
    def locked_labelset_objects(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> Annotated[
        LabelSetTypeConnection, strawberry.lazy("config.graphql.annotation_types")
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "locked_labelset_objects", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="LabelSetType",
        )

    @strawberry.field(name="labelsetSet")
    def labelset_set(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> Annotated[
        LabelSetTypeConnection, strawberry.lazy("config.graphql.annotation_types")
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "labelset_set", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="LabelSetType",
        )

    @strawberry.field(name="noteSet")
    def note_set(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> Annotated[
        NoteTypeConnection, strawberry.lazy("config.graphql.annotation_types")
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "note_set", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="NoteType",
        )

    @strawberry.field(name="lockedNoteObjects")
    def locked_note_objects(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> Annotated[
        NoteTypeConnection, strawberry.lazy("config.graphql.annotation_types")
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "locked_note_objects", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="NoteType",
        )

    @strawberry.field(name="noteRevisions")
    def note_revisions(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> Annotated[
        NoteRevisionTypeConnection, strawberry.lazy("config.graphql.annotation_types")
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "note_revisions", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="NoteRevisionType",
        )

    @strawberry.field(name="lockedCorpusreferenceObjects")
    def locked_corpusreference_objects(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> Annotated[
        CorpusReferenceTypeConnection,
        strawberry.lazy("config.graphql.annotation_types"),
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "locked_corpusreference_objects", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="CorpusReferenceType",
        )

    @strawberry.field(name="corpusreferenceSet")
    def corpusreference_set(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> Annotated[
        CorpusReferenceTypeConnection,
        strawberry.lazy("config.graphql.annotation_types"),
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "corpusreference_set", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="CorpusReferenceType",
        )

    @strawberry.field(name="authoredAuthorityNamespaces")
    def authored_authority_namespaces(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> Annotated[
        AuthorityNamespaceNodeConnection,
        strawberry.lazy("config.graphql.annotation_types"),
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "authored_authority_namespaces", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="AuthorityNamespaceNode",
        )

    @strawberry.field(name="authoredAuthorityEquivalences")
    def authored_authority_equivalences(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> Annotated[
        AuthorityKeyEquivalenceNodeConnection,
        strawberry.lazy("config.graphql.annotation_types"),
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "authored_authority_equivalences", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="AuthorityKeyEquivalenceNode",
        )

    @strawberry.field(name="lockedGremlinengineObjects")
    def locked_gremlinengine_objects(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> Annotated[
        GremlinEngineType_WRITEConnection,
        strawberry.lazy("config.graphql.extract_types"),
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "locked_gremlinengine_objects", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="GremlinEngineType_WRITE",
        )

    @strawberry.field(name="gremlinengineSet")
    def gremlinengine_set(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> Annotated[
        GremlinEngineType_WRITEConnection,
        strawberry.lazy("config.graphql.extract_types"),
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "gremlinengine_set", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="GremlinEngineType_WRITE",
        )

    @strawberry.field(name="lockedAnalyzerObjects")
    def locked_analyzer_objects(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> Annotated[
        AnalyzerTypeConnection, strawberry.lazy("config.graphql.extract_types")
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "locked_analyzer_objects", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="AnalyzerType",
        )

    @strawberry.field(name="analyzerSet")
    def analyzer_set(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> Annotated[
        AnalyzerTypeConnection, strawberry.lazy("config.graphql.extract_types")
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "analyzer_set", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="AnalyzerType",
        )

    @strawberry.field(name="analysisSet")
    def analysis_set(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> Annotated[
        AnalysisTypeConnection, strawberry.lazy("config.graphql.extract_types")
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "analysis_set", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="AnalysisType",
        )

    @strawberry.field(name="lockedAnalysisObjects")
    def locked_analysis_objects(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> Annotated[
        AnalysisTypeConnection, strawberry.lazy("config.graphql.extract_types")
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "locked_analysis_objects", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="AnalysisType",
        )

    @strawberry.field(name="lockedFieldsetObjects")
    def locked_fieldset_objects(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> Annotated[
        FieldsetTypeConnection, strawberry.lazy("config.graphql.extract_types")
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "locked_fieldset_objects", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="FieldsetType",
        )

    @strawberry.field(name="fieldsetSet")
    def fieldset_set(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> Annotated[
        FieldsetTypeConnection, strawberry.lazy("config.graphql.extract_types")
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "fieldset_set", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="FieldsetType",
        )

    @strawberry.field(name="lockedColumnObjects")
    def locked_column_objects(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> Annotated[
        ColumnTypeConnection, strawberry.lazy("config.graphql.extract_types")
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "locked_column_objects", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="ColumnType",
        )

    @strawberry.field(name="columnSet")
    def column_set(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> Annotated[
        ColumnTypeConnection, strawberry.lazy("config.graphql.extract_types")
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "column_set", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="ColumnType",
        )

    @strawberry.field(name="lockedExtractObjects")
    def locked_extract_objects(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> Annotated[
        ExtractTypeConnection, strawberry.lazy("config.graphql.extract_types")
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "locked_extract_objects", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="ExtractType",
        )

    @strawberry.field(name="extractSet")
    def extract_set(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> Annotated[
        ExtractTypeConnection, strawberry.lazy("config.graphql.extract_types")
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "extract_set", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="ExtractType",
        )

    @strawberry.field(name="approvedCells")
    def approved_cells(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> Annotated[
        DatacellTypeConnection, strawberry.lazy("config.graphql.extract_types")
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "approved_cells", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="DatacellType",
        )

    @strawberry.field(name="rejectedCells")
    def rejected_cells(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> Annotated[
        DatacellTypeConnection, strawberry.lazy("config.graphql.extract_types")
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "rejected_cells", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="DatacellType",
        )

    @strawberry.field(name="lockedDatacellObjects")
    def locked_datacell_objects(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> Annotated[
        DatacellTypeConnection, strawberry.lazy("config.graphql.extract_types")
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "locked_datacell_objects", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="DatacellType",
        )

    @strawberry.field(name="datacellSet")
    def datacell_set(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> Annotated[
        DatacellTypeConnection, strawberry.lazy("config.graphql.extract_types")
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "datacell_set", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="DatacellType",
        )

    @strawberry.field(name="lockedUserfeedbackObjects")
    def locked_userfeedback_objects(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> UserFeedbackTypeConnection:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "locked_userfeedback_objects", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="UserFeedbackType",
        )

    @strawberry.field(name="userfeedbackSet")
    def userfeedback_set(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> UserFeedbackTypeConnection:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "userfeedback_set", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="UserFeedbackType",
        )

    @strawberry.field(
        name="lockedConversations", description="Moderator who locked the thread"
    )
    def locked_conversations(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> Annotated[
        ConversationTypeConnection,
        strawberry.lazy("config.graphql.conversation_types"),
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "locked_conversations", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="ConversationType",
        )

    @strawberry.field(
        name="pinnedConversations", description="Moderator who pinned the thread"
    )
    def pinned_conversations(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> Annotated[
        ConversationTypeConnection,
        strawberry.lazy("config.graphql.conversation_types"),
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "pinned_conversations", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="ConversationType",
        )

    @strawberry.field(name="lockedConversationObjects")
    def locked_conversation_objects(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> Annotated[
        ConversationTypeConnection,
        strawberry.lazy("config.graphql.conversation_types"),
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "locked_conversation_objects", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="ConversationType",
        )

    @strawberry.field(name="conversationSet")
    def conversation_set(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> Annotated[
        ConversationTypeConnection,
        strawberry.lazy("config.graphql.conversation_types"),
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "conversation_set", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="ConversationType",
        )

    @strawberry.field(name="lockedChatmessageObjects")
    def locked_chatmessage_objects(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> Annotated[
        MessageTypeConnection, strawberry.lazy("config.graphql.conversation_types")
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "locked_chatmessage_objects", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="MessageType",
        )

    @strawberry.field(name="chatmessageSet")
    def chatmessage_set(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> Annotated[
        MessageTypeConnection, strawberry.lazy("config.graphql.conversation_types")
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "chatmessage_set", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="MessageType",
        )

    @strawberry.field(
        name="moderationActionsTaken", description="Moderator who took this action"
    )
    def moderation_actions_taken(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> Annotated[
        ModerationActionTypeConnection,
        strawberry.lazy("config.graphql.conversation_types"),
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "moderation_actions_taken", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="ModerationActionType",
        )

    @strawberry.field(name="lockedModerationactionObjects")
    def locked_moderationaction_objects(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> Annotated[
        ModerationActionTypeConnection,
        strawberry.lazy("config.graphql.conversation_types"),
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "locked_moderationaction_objects", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="ModerationActionType",
        )

    @strawberry.field(name="moderationactionSet")
    def moderationaction_set(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> Annotated[
        ModerationActionTypeConnection,
        strawberry.lazy("config.graphql.conversation_types"),
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "moderationaction_set", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="ModerationActionType",
        )

    @strawberry.field(name="lockedBadgeObjects")
    def locked_badge_objects(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> Annotated[BadgeTypeConnection, strawberry.lazy("config.graphql.social_types")]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "locked_badge_objects", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="BadgeType",
        )

    @strawberry.field(name="badgeSet")
    def badge_set(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> Annotated[BadgeTypeConnection, strawberry.lazy("config.graphql.social_types")]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "badge_set", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="BadgeType",
        )

    @strawberry.field(name="badges", description="User who received the badge")
    def badges(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> Annotated[
        UserBadgeTypeConnection, strawberry.lazy("config.graphql.social_types")
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "badges", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="UserBadgeType",
        )

    @strawberry.field(
        name="badgesAwarded",
        description="User who awarded the badge (null for auto-awards)",
    )
    def badges_awarded(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> Annotated[
        UserBadgeTypeConnection, strawberry.lazy("config.graphql.social_types")
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "badges_awarded", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="UserBadgeType",
        )

    @strawberry.field(
        name="notifications", description="User receiving this notification"
    )
    def notifications(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
        is_read: Annotated[
            bool | None, strawberry.argument(name="isRead")
        ] = strawberry.UNSET,
        notification_type: Annotated[
            enums.NotificationsNotificationNotificationTypeChoices | None,
            strawberry.argument(name="notificationType"),
        ] = strawberry.UNSET,
        created_at__lte: Annotated[
            datetime.datetime | None, strawberry.argument(name="createdAt_Lte")
        ] = strawberry.UNSET,
        created_at__gte: Annotated[
            datetime.datetime | None, strawberry.argument(name="createdAt_Gte")
        ] = strawberry.UNSET,
    ) -> Annotated[
        NotificationTypeConnection, strawberry.lazy("config.graphql.social_types")
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
                "is_read": is_read,
                "notification_type": notification_type,
                "created_at__lte": created_at__lte,
                "created_at__gte": created_at__gte,
            }
        )
        resolved = getattr(self, "notifications", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="NotificationType",
            filterset_class=filterset_factory(
                Notification,
                fields={
                    "is_read": ["exact"],
                    "notification_type": ["exact"],
                    "created_at": ["lte", "gte"],
                },
            ),
            filter_args={
                "is_read": "is_read",
                "notification_type": "notification_type",
                "created_at__lte": "created_at__lte",
                "created_at__gte": "created_at__gte",
            },
        )

    @strawberry.field(
        name="notificationsTriggered",
        description="User who triggered this notification (if applicable)",
    )
    def notifications_triggered(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
        is_read: Annotated[
            bool | None, strawberry.argument(name="isRead")
        ] = strawberry.UNSET,
        notification_type: Annotated[
            enums.NotificationsNotificationNotificationTypeChoices | None,
            strawberry.argument(name="notificationType"),
        ] = strawberry.UNSET,
        created_at__lte: Annotated[
            datetime.datetime | None, strawberry.argument(name="createdAt_Lte")
        ] = strawberry.UNSET,
        created_at__gte: Annotated[
            datetime.datetime | None, strawberry.argument(name="createdAt_Gte")
        ] = strawberry.UNSET,
    ) -> Annotated[
        NotificationTypeConnection, strawberry.lazy("config.graphql.social_types")
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
                "is_read": is_read,
                "notification_type": notification_type,
                "created_at__lte": created_at__lte,
                "created_at__gte": created_at__gte,
            }
        )
        resolved = getattr(self, "notifications_triggered", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="NotificationType",
            filterset_class=filterset_factory(
                Notification,
                fields={
                    "is_read": ["exact"],
                    "notification_type": ["exact"],
                    "created_at": ["lte", "gte"],
                },
            ),
            filter_args={
                "is_read": "is_read",
                "notification_type": "notification_type",
                "created_at__lte": "created_at__lte",
                "created_at__gte": "created_at__gte",
            },
        )

    @strawberry.field(name="lockedAgentconfigurationObjects")
    def locked_agentconfiguration_objects(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
        scope: Annotated[
            enums.AgentsAgentConfigurationScopeChoices | None,
            strawberry.argument(name="scope"),
        ] = strawberry.UNSET,
        is_active: Annotated[
            bool | None, strawberry.argument(name="isActive")
        ] = strawberry.UNSET,
        corpus: Annotated[
            strawberry.ID | None, strawberry.argument(name="corpus")
        ] = strawberry.UNSET,
    ) -> Annotated[
        AgentConfigurationTypeConnection,
        strawberry.lazy("config.graphql.agent_types"),
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
                "scope": scope,
                "is_active": is_active,
                "corpus": corpus,
            }
        )
        resolved = getattr(self, "locked_agentconfiguration_objects", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="AgentConfigurationType",
            filterset_class=filterset_factory(
                AgentConfiguration,
                fields={
                    "scope": ["exact"],
                    "is_active": ["exact"],
                    "corpus": ["exact"],
                },
            ),
            filter_args={
                "scope": "scope",
                "is_active": "is_active",
                "corpus": "corpus",
            },
        )

    @strawberry.field(name="agentconfigurationSet")
    def agentconfiguration_set(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
        scope: Annotated[
            enums.AgentsAgentConfigurationScopeChoices | None,
            strawberry.argument(name="scope"),
        ] = strawberry.UNSET,
        is_active: Annotated[
            bool | None, strawberry.argument(name="isActive")
        ] = strawberry.UNSET,
        corpus: Annotated[
            strawberry.ID | None, strawberry.argument(name="corpus")
        ] = strawberry.UNSET,
    ) -> Annotated[
        AgentConfigurationTypeConnection,
        strawberry.lazy("config.graphql.agent_types"),
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
                "scope": scope,
                "is_active": is_active,
                "corpus": corpus,
            }
        )
        resolved = getattr(self, "agentconfiguration_set", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="AgentConfigurationType",
            filterset_class=filterset_factory(
                AgentConfiguration,
                fields={
                    "scope": ["exact"],
                    "is_active": ["exact"],
                    "corpus": ["exact"],
                },
            ),
            filter_args={
                "scope": "scope",
                "is_active": "is_active",
                "corpus": "corpus",
            },
        )

    @strawberry.field(name="lockedAgentactionresultObjects")
    def locked_agentactionresult_objects(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
        id: Annotated[
            strawberry.ID | None, strawberry.argument(name="id")
        ] = strawberry.UNSET,
        corpus_action__id: Annotated[
            strawberry.ID | None, strawberry.argument(name="corpusAction_Id")
        ] = strawberry.UNSET,
        document__id: Annotated[
            strawberry.ID | None, strawberry.argument(name="document_Id")
        ] = strawberry.UNSET,
        status: Annotated[
            enums.AgentsAgentActionResultStatusChoices | None,
            strawberry.argument(name="status"),
        ] = strawberry.UNSET,
        creator__id: Annotated[
            strawberry.ID | None, strawberry.argument(name="creator_Id")
        ] = strawberry.UNSET,
    ) -> Annotated[
        AgentActionResultTypeConnection, strawberry.lazy("config.graphql.agent_types")
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
                "id": id,
                "corpus_action__id": corpus_action__id,
                "document__id": document__id,
                "status": status,
                "creator__id": creator__id,
            }
        )
        resolved = getattr(self, "locked_agentactionresult_objects", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="AgentActionResultType",
            filterset_class=filterset_factory(
                AgentActionResult,
                fields={
                    "id": ["exact"],
                    "corpus_action__id": ["exact"],
                    "document__id": ["exact"],
                    "status": ["exact"],
                    "creator__id": ["exact"],
                },
            ),
            filter_args={
                "id": "id",
                "corpus_action__id": "corpus_action__id",
                "document__id": "document__id",
                "status": "status",
                "creator__id": "creator__id",
            },
        )

    @strawberry.field(name="agentactionresultSet")
    def agentactionresult_set(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
        id: Annotated[
            strawberry.ID | None, strawberry.argument(name="id")
        ] = strawberry.UNSET,
        corpus_action__id: Annotated[
            strawberry.ID | None, strawberry.argument(name="corpusAction_Id")
        ] = strawberry.UNSET,
        document__id: Annotated[
            strawberry.ID | None, strawberry.argument(name="document_Id")
        ] = strawberry.UNSET,
        status: Annotated[
            enums.AgentsAgentActionResultStatusChoices | None,
            strawberry.argument(name="status"),
        ] = strawberry.UNSET,
        creator__id: Annotated[
            strawberry.ID | None, strawberry.argument(name="creator_Id")
        ] = strawberry.UNSET,
    ) -> Annotated[
        AgentActionResultTypeConnection, strawberry.lazy("config.graphql.agent_types")
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
                "id": id,
                "corpus_action__id": corpus_action__id,
                "document__id": document__id,
                "status": status,
                "creator__id": creator__id,
            }
        )
        resolved = getattr(self, "agentactionresult_set", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="AgentActionResultType",
            filterset_class=filterset_factory(
                AgentActionResult,
                fields={
                    "id": ["exact"],
                    "corpus_action__id": ["exact"],
                    "document__id": ["exact"],
                    "status": ["exact"],
                    "creator__id": ["exact"],
                },
            ),
            filter_args={
                "id": "id",
                "corpus_action__id": "corpus_action__id",
                "document__id": "document__id",
                "status": "status",
                "creator__id": "creator__id",
            },
        )

    @strawberry.field(name="lockedResearchreportObjects")
    def locked_researchreport_objects(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> Annotated[
        ResearchReportTypeConnection, strawberry.lazy("config.graphql.research_types")
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "locked_researchreport_objects", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="ResearchReportType",
        )

    @strawberry.field(name="researchreportSet")
    def researchreport_set(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> Annotated[
        ResearchReportTypeConnection, strawberry.lazy("config.graphql.research_types")
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "researchreport_set", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="ResearchReportType",
        )

    @strawberry.field(name="myPermissions")
    def my_permissions(self, info: strawberry.Info) -> GenericScalar | None:
        return core_permissions.resolve_my_permissions(self, info)

    @strawberry.field(name="isPublished")
    def is_published(self, info: strawberry.Info) -> bool | None:
        return core_permissions.resolve_is_published(self, info)

    @strawberry.field(name="objectSharedWith")
    def object_shared_with(self, info: strawberry.Info) -> GenericScalar | None:
        return core_permissions.resolve_object_shared_with(self, info)

    @strawberry.field(
        name="displayName",
        description="Privacy-preserving display name. Non-self viewers always receive the user's ``slug`` (or a redacted ``user_<pk-suffix>`` fallback when no slug exists). Self-views walk the rich PII-safe fallback chain so personal-settings UIs greet the user with their chosen name. Self-view chain: name → given_name + family_name → first_name + last_name → auto-assigned handle → username (local users only) → redacted 'user_<sub_suffix>' for social users → redacted 'user_<pk-suffix>'. The raw OAuth ``provider|sub`` value used as the Django ``username`` for social-login users is never returned.",
    )
    def display_name(self, info: strawberry.Info) -> str | None:
        kwargs = strip_unset({})
        return _resolve_UserType_display_name(self, info, **kwargs)

    @strawberry.field(
        name="reputationGlobal",
        description="Global reputation score across all corpuses",
    )
    def reputation_global(self, info: strawberry.Info) -> int | None:
        kwargs = strip_unset({})
        return _resolve_UserType_reputation_global(self, info, **kwargs)

    @strawberry.field(
        name="reputationForCorpus", description="Reputation score for a specific corpus"
    )
    def reputation_for_corpus(
        self,
        info: strawberry.Info,
        corpus_id: Annotated[
            strawberry.ID, strawberry.argument(name="corpusId")
        ] = strawberry.UNSET,
    ) -> int | None:
        kwargs = strip_unset({"corpus_id": corpus_id})
        return _resolve_UserType_reputation_for_corpus(self, info, **kwargs)

    @strawberry.field(
        name="totalMessages", description="Total number of messages posted by this user"
    )
    def total_messages(self, info: strawberry.Info) -> int | None:
        kwargs = strip_unset({})
        return _resolve_UserType_total_messages(self, info, **kwargs)

    @strawberry.field(
        name="totalThreadsCreated",
        description="Total number of threads created by this user",
    )
    def total_threads_created(self, info: strawberry.Info) -> int | None:
        kwargs = strip_unset({})
        return _resolve_UserType_total_threads_created(self, info, **kwargs)

    @strawberry.field(
        name="totalAnnotationsCreated",
        description="Total number of annotations created by this user (visible to requester)",
    )
    def total_annotations_created(self, info: strawberry.Info) -> int | None:
        kwargs = strip_unset({})
        return _resolve_UserType_total_annotations_created(self, info, **kwargs)

    @strawberry.field(
        name="totalDocumentsUploaded",
        description="Total number of documents uploaded by this user (visible to requester)",
    )
    def total_documents_uploaded(self, info: strawberry.Info) -> int | None:
        kwargs = strip_unset({})
        return _resolve_UserType_total_documents_uploaded(self, info, **kwargs)

    @strawberry.field(
        name="canImportCorpus",
        description="Whether this user is permitted to import a corpus. Self-only — this exposes account-tier (usage-capped) status, which is PII. Returns ``None`` for non-self viewers. Self-views see the same gate the server enforces in the corpus-export and zip-to-corpus REST import endpoints (/api/imports/corpus/, /api/imports/zip-to-corpus/): false for usage-capped users when USAGE_CAPPED_USER_CAN_IMPORT_CORPUS is disabled.",
    )
    def can_import_corpus(self, info: strawberry.Info) -> bool | None:
        kwargs = strip_unset({})
        return _resolve_UserType_can_import_corpus(self, info, **kwargs)


register_type("UserType", UserType, model=User)


UserTypeConnection = make_connection_types(
    UserType, type_name="UserTypeConnection", countable=True, pdf_page_aware=False
)


@strawberry.type(name="AssignmentType")
class AssignmentType(Node):
    @strawberry.field(name="name")
    def name(self, info: strawberry.Info) -> str | None:
        return coerce_str(getattr(self, "name", None))

    document: Annotated[
        DocumentType, strawberry.lazy("config.graphql.document_types")
    ] = strawberry.field(name="document", default=None)

    @strawberry.field(name="corpus")
    def corpus(
        self, info: strawberry.Info
    ) -> None | (Annotated[CorpusType, strawberry.lazy("config.graphql.corpus_types")]):
        return resolve_visible_fk(self, info, "corpus_id", "CorpusType")

    @strawberry.field(name="resultingAnnotations")
    def resulting_annotations(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
        raw_text__contains: Annotated[
            str | None, strawberry.argument(name="rawText_Contains")
        ] = strawberry.UNSET,
        annotation_label_id: Annotated[
            strawberry.ID | None, strawberry.argument(name="annotationLabelId")
        ] = strawberry.UNSET,
        annotation_label__text: Annotated[
            str | None, strawberry.argument(name="annotationLabel_Text")
        ] = strawberry.UNSET,
        annotation_label__text__contains: Annotated[
            str | None, strawberry.argument(name="annotationLabel_Text_Contains")
        ] = strawberry.UNSET,
        annotation_label__description__contains: Annotated[
            str | None,
            strawberry.argument(name="annotationLabel_Description_Contains"),
        ] = strawberry.UNSET,
        annotation_label__label_type: Annotated[
            enums.AnnotationsAnnotationLabelLabelTypeChoices | None,
            strawberry.argument(name="annotationLabel_LabelType"),
        ] = strawberry.UNSET,
        analysis__isnull: Annotated[
            bool | None, strawberry.argument(name="analysis_Isnull")
        ] = strawberry.UNSET,
        document_id: Annotated[
            strawberry.ID | None, strawberry.argument(name="documentId")
        ] = strawberry.UNSET,
        corpus_id: Annotated[
            strawberry.ID | None, strawberry.argument(name="corpusId")
        ] = strawberry.UNSET,
        structural: Annotated[
            bool | None, strawberry.argument(name="structural")
        ] = strawberry.UNSET,
        uses_label_from_labelset_id: Annotated[
            str | None, strawberry.argument(name="usesLabelFromLabelsetId")
        ] = strawberry.UNSET,
        created_by_analysis_ids: Annotated[
            str | None, strawberry.argument(name="createdByAnalysisIds")
        ] = strawberry.UNSET,
        created_with_analyzer_id: Annotated[
            str | None, strawberry.argument(name="createdWithAnalyzerId")
        ] = strawberry.UNSET,
        order_by: Annotated[
            str | None, strawberry.argument(name="orderBy", description="Ordering")
        ] = strawberry.UNSET,
    ) -> Annotated[
        AnnotationTypeConnection, strawberry.lazy("config.graphql.annotation_types")
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
                "raw_text__contains": raw_text__contains,
                "annotation_label_id": annotation_label_id,
                "annotation_label__text": annotation_label__text,
                "annotation_label__text__contains": annotation_label__text__contains,
                "annotation_label__description__contains": annotation_label__description__contains,
                "annotation_label__label_type": annotation_label__label_type,
                "analysis__isnull": analysis__isnull,
                "document_id": document_id,
                "corpus_id": corpus_id,
                "structural": structural,
                "uses_label_from_labelset_id": uses_label_from_labelset_id,
                "created_by_analysis_ids": created_by_analysis_ids,
                "created_with_analyzer_id": created_with_analyzer_id,
                "order_by": order_by,
            }
        )
        resolved = getattr(self, "resulting_annotations", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="AnnotationType",
            filterset_class=setup_filterset(AnnotationFilter),
            filter_args={
                "raw_text__contains": "raw_text__contains",
                "annotation_label_id": "annotation_label_id",
                "annotation_label__text": "annotation_label__text",
                "annotation_label__text__contains": "annotation_label__text__contains",
                "annotation_label__description__contains": "annotation_label__description__contains",
                "annotation_label__label_type": "annotation_label__label_type",
                "analysis__isnull": "analysis__isnull",
                "document_id": "document_id",
                "corpus_id": "corpus_id",
                "structural": "structural",
                "uses_label_from_labelset_id": "uses_label_from_labelset_id",
                "created_by_analysis_ids": "created_by_analysis_ids",
                "created_with_analyzer_id": "created_with_analyzer_id",
                "order_by": "order_by",
            },
        )

    @strawberry.field(name="resultingRelationships")
    def resulting_relationships(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> Annotated[
        RelationshipTypeConnection, strawberry.lazy("config.graphql.annotation_types")
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "resulting_relationships", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="RelationshipType",
        )

    @strawberry.field(name="comments")
    def comments(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "comments", None))

    assignor: UserType = strawberry.field(name="assignor", default=None)
    assignee: UserType | None = strawberry.field(name="assignee", default=None)
    completed_at: datetime.datetime | None = strawberry.field(
        name="completedAt", default=None
    )
    created: datetime.datetime = strawberry.field(name="created", default=None)
    modified: datetime.datetime = strawberry.field(name="modified", default=None)

    @strawberry.field(name="myPermissions")
    def my_permissions(self, info: strawberry.Info) -> GenericScalar | None:
        return core_permissions.resolve_my_permissions(self, info)

    @strawberry.field(name="isPublished")
    def is_published(self, info: strawberry.Info) -> bool | None:
        return core_permissions.resolve_is_published(self, info)

    @strawberry.field(name="objectSharedWith")
    def object_shared_with(self, info: strawberry.Info) -> GenericScalar | None:
        return core_permissions.resolve_object_shared_with(self, info)


def _get_node_AssignmentType(info, pk):
    """Permission-aware node resolution for the singular ``assignment(id:)``
    field (IDOR guard). The Assignment feature is DEPRECATED and the model has
    no ``visible_to_user`` manager, so this mirrors the graphene resolver's
    explicit gate: superusers may fetch any assignment; other authenticated
    users may fetch only assignments where they are the assignor or assignee;
    everyone else gets None (same not-found error whether the row is absent or
    forbidden). Without this hook, ``get_node_from_global_id`` falls back to an
    UNFILTERED ``.get(pk=pk)``.
    """
    from django.db.models import Q

    user = getattr(info.context, "user", None)
    if user is None or not getattr(user, "is_authenticated", False):
        return None
    try:
        pk_int = int(pk)
    except (TypeError, ValueError):
        return None
    if user.is_superuser:
        return Assignment.objects.filter(pk=pk_int).first()
    return Assignment.objects.filter(
        Q(pk=pk_int) & (Q(assignor=user) | Q(assignee=user))
    ).first()


register_type(
    "AssignmentType",
    AssignmentType,
    model=Assignment,
    get_node=_get_node_AssignmentType,
)


AssignmentTypeConnection = make_connection_types(
    AssignmentType,
    type_name="AssignmentTypeConnection",
    countable=True,
    pdf_page_aware=False,
)


@strawberry.type(name="UserFeedbackType")
class UserFeedbackType(Node):
    user_lock: UserType | None = strawberry.field(name="userLock", default=None)
    backend_lock: bool = strawberry.field(name="backendLock", default=None)
    is_public: bool = strawberry.field(name="isPublic", default=None)
    creator: UserType = strawberry.field(name="creator", default=None)
    created: datetime.datetime = strawberry.field(name="created", default=None)
    modified: datetime.datetime = strawberry.field(name="modified", default=None)
    approved: bool = strawberry.field(name="approved", default=None)
    rejected: bool = strawberry.field(name="rejected", default=None)

    @strawberry.field(name="comment")
    def comment(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "comment", None))

    @strawberry.field(name="markdown")
    def markdown(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "markdown", None))

    metadata: JSONString | None = strawberry.field(name="metadata", default=None)

    @strawberry.field(name="commentedAnnotation")
    def commented_annotation(
        self, info: strawberry.Info
    ) -> None | (
        Annotated[AnnotationType, strawberry.lazy("config.graphql.annotation_types")]
    ):
        return resolve_visible_fk(
            self, info, "commented_annotation_id", "AnnotationType"
        )

    @strawberry.field(name="myPermissions")
    def my_permissions(self, info: strawberry.Info) -> GenericScalar | None:
        return core_permissions.resolve_my_permissions(self, info)

    @strawberry.field(name="isPublished")
    def is_published(self, info: strawberry.Info) -> bool | None:
        return core_permissions.resolve_is_published(self, info)

    @strawberry.field(name="objectSharedWith")
    def object_shared_with(self, info: strawberry.Info) -> GenericScalar | None:
        return core_permissions.resolve_object_shared_with(self, info)


def _get_queryset_UserFeedbackType(queryset, info):
    """PORT: config.graphql.user_types.UserFeedbackType.get_queryset

    Port of UserFeedbackType.get_queryset
    """
    # https://docs.graphene-python.org/projects/django/en/latest/queries/#default-queryset
    # When the parent resolver prefetched the reverse relation
    # (see ``AnnotationService.get_document_annotations`` which
    # registers a ``Prefetch("user_feedback", ...)``), the manager passed
    # in here has its parent's ``_prefetched_objects_cache`` populated.
    # Re-applying the visibility filter invalidates that cache and forces
    # a fresh SELECT per parent row — the original N+1 storm we were
    # trying to eliminate. Detect the prefetch and pass through.
    # ``instance``, ``prefetch_cache_name``, and ``_prefetched_objects_cache``
    # are Django RelatedManager internals — if their shape changes in a
    # future release the service-layer fallback keeps correctness intact,
    # only losing the per-row optimisation.
    instance = getattr(queryset, "instance", None)
    cache_name = getattr(queryset, "prefetch_cache_name", None)
    prefetched = getattr(instance, "_prefetched_objects_cache", None) or {}
    if instance is not None and cache_name is not None and cache_name in prefetched:
        return queryset

    # Chain ``visible_to_user`` on the incoming queryset/manager so the
    # filter is a single ``WHERE`` expression tree (no ``pk__in``
    # subquery over the full table).
    return BaseService.filter_visible_qs(
        queryset, info.context.user, request=info.context
    )


register_type(
    "UserFeedbackType",
    UserFeedbackType,
    model=UserFeedback,
    get_queryset=_get_queryset_UserFeedbackType,
)


UserFeedbackTypeConnection = make_connection_types(
    UserFeedbackType,
    type_name="UserFeedbackTypeConnection",
    countable=True,
    pdf_page_aware=False,
)


def _resolve_UserExportType_file(root, info, **kwargs):
    """PORT: config/graphql/user_types.py:465

    Port of UserExportType.resolve_file
    """
    return "" if not root.file else info.context.build_absolute_uri(root.file.url)


@strawberry.type(name="UserExportType")
class UserExportType(Node):
    user_lock: UserType | None = strawberry.field(name="userLock", default=None)
    modified: datetime.datetime = strawberry.field(name="modified", default=None)

    @strawberry.field(name="file")
    def file(self, info: strawberry.Info) -> str:
        kwargs = strip_unset({})
        return _resolve_UserExportType_file(self, info, **kwargs)

    @strawberry.field(name="name")
    def name(self, info: strawberry.Info) -> str | None:
        return coerce_str(getattr(self, "name", None))

    created: datetime.datetime = strawberry.field(name="created", default=None)
    started: datetime.datetime | None = strawberry.field(name="started", default=None)
    finished: datetime.datetime | None = strawberry.field(name="finished", default=None)

    @strawberry.field(name="errors")
    def errors(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "errors", None))

    post_processors: JSONString = strawberry.field(
        name="postProcessors",
        description="List of fully qualified Python paths to post-processor functions",
        default=None,
    )
    input_kwargs: JSONString | None = strawberry.field(
        name="inputKwargs",
        description="Additional keyword arguments to pass to post-processors",
        default=None,
    )

    @strawberry.field(name="format")
    def format(self, info: strawberry.Info) -> enums.UsersUserExportFormatChoices:
        return coerce_enum(
            enums.UsersUserExportFormatChoices, getattr(self, "format", None)
        )

    backend_lock: bool = strawberry.field(name="backendLock", default=None)
    is_public: bool = strawberry.field(name="isPublic", default=None)
    creator: UserType = strawberry.field(name="creator", default=None)

    @strawberry.field(name="myPermissions")
    def my_permissions(self, info: strawberry.Info) -> GenericScalar | None:
        return core_permissions.resolve_my_permissions(self, info)

    @strawberry.field(name="isPublished")
    def is_published(self, info: strawberry.Info) -> bool | None:
        return core_permissions.resolve_is_published(self, info)

    @strawberry.field(name="objectSharedWith")
    def object_shared_with(self, info: strawberry.Info) -> GenericScalar | None:
        return core_permissions.resolve_object_shared_with(self, info)


def _get_node_UserExportType(info, pk):
    """Permission-aware node resolution for the singular ``userexport(id:)``
    field (IDOR guard). Mirrors the graphene ``BaseService.get_or_none(
    UserExport, ...)`` resolver; without it ``get_node_from_global_id`` would
    fall back to an UNFILTERED ``.get(pk=pk)``.
    """
    if pk is None:
        return None
    return BaseService.get_or_none(
        UserExport, pk, info.context.user, request=info.context
    )


register_type(
    "UserExportType",
    UserExportType,
    model=UserExport,
    get_node=_get_node_UserExportType,
)


UserExportTypeConnection = make_connection_types(
    UserExportType,
    type_name="UserExportTypeConnection",
    countable=True,
    pdf_page_aware=False,
)


def _resolve_UserImportType_zip(root, info, **kwargs):
    """PORT: config/graphql/user_types.py:475

    Port of UserImportType.resolve_zip
    """
    # NOTE: kept verbatim from the graphene resolver, including the
    # ``self.file`` guard (UserImport has no ``file`` field — only ``zip``).
    return "" if not root.file else info.context.build_absolute_uri(root.zip.url)


@strawberry.type(name="UserImportType")
class UserImportType(Node):
    user_lock: UserType | None = strawberry.field(name="userLock", default=None)
    backend_lock: bool = strawberry.field(name="backendLock", default=None)
    modified: datetime.datetime = strawberry.field(name="modified", default=None)

    @strawberry.field(name="zip")
    def zip(self, info: strawberry.Info) -> str:
        kwargs = strip_unset({})
        return _resolve_UserImportType_zip(self, info, **kwargs)

    @strawberry.field(name="name")
    def name(self, info: strawberry.Info) -> str | None:
        return coerce_str(getattr(self, "name", None))

    created: datetime.datetime = strawberry.field(name="created", default=None)
    started: datetime.datetime | None = strawberry.field(name="started", default=None)
    finished: datetime.datetime | None = strawberry.field(name="finished", default=None)

    @strawberry.field(name="errors")
    def errors(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "errors", None))

    is_public: bool = strawberry.field(name="isPublic", default=None)
    creator: UserType = strawberry.field(name="creator", default=None)

    @strawberry.field(name="myPermissions")
    def my_permissions(self, info: strawberry.Info) -> GenericScalar | None:
        return core_permissions.resolve_my_permissions(self, info)

    @strawberry.field(name="isPublished")
    def is_published(self, info: strawberry.Info) -> bool | None:
        return core_permissions.resolve_is_published(self, info)

    @strawberry.field(name="objectSharedWith")
    def object_shared_with(self, info: strawberry.Info) -> GenericScalar | None:
        return core_permissions.resolve_object_shared_with(self, info)


def _get_node_UserImportType(info, pk):
    """Permission-aware node resolution for the singular ``userimport(id:)``
    field (IDOR guard). Mirrors the graphene ``BaseService.get_or_none(
    UserImport, ...)`` resolver; without it ``get_node_from_global_id`` would
    fall back to an UNFILTERED ``.get(pk=pk)``.
    """
    if pk is None:
        return None
    return BaseService.get_or_none(
        UserImport, pk, info.context.user, request=info.context
    )


register_type(
    "UserImportType",
    UserImportType,
    model=UserImport,
    get_node=_get_node_UserImportType,
)


UserImportTypeConnection = make_connection_types(
    UserImportType,
    type_name="UserImportTypeConnection",
    countable=True,
    pdf_page_aware=False,
)


@strawberry.type(
    name="BulkDocumentUploadStatusType",
    description="Type for checking the status of a bulk document upload job",
)
class BulkDocumentUploadStatusType:
    @strawberry.field(name="jobId")
    def job_id(self, info: strawberry.Info) -> str | None:
        return coerce_str(getattr(self, "job_id", None))

    success: bool | None = strawberry.field(name="success", default=None)
    total_files: int | None = strawberry.field(name="totalFiles", default=None)
    processed_files: int | None = strawberry.field(name="processedFiles", default=None)
    skipped_files: int | None = strawberry.field(name="skippedFiles", default=None)
    error_files: int | None = strawberry.field(name="errorFiles", default=None)

    @strawberry.field(name="documentIds")
    def document_ids(self, info: strawberry.Info) -> list[str | None] | None:
        return getattr(self, "document_ids", None)

    @strawberry.field(name="errors")
    def errors(self, info: strawberry.Info) -> list[str | None] | None:
        return getattr(self, "errors", None)

    completed: bool | None = strawberry.field(name="completed", default=None)


register_type("BulkDocumentUploadStatusType", BulkDocumentUploadStatusType, model=None)
