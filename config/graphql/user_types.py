"""GraphQL type definitions for user-related types.

Privacy model
-------------
Personally identifying user fields (``email``, ``name``, ``first_name``,
``last_name``, ``given_name``, ``family_name``, ``username``, ``phone``,
``auth0_Id``, ``last_ip``, ``email_verified``, ``is_social_user``, login
metadata, UI preferences) are gated to *self-only* reads. Non-self viewers
— including superusers, server-side internal callers, and anonymous users
— see ``None`` for these fields. The ``slug`` is the only public identifier
and the ``display_name`` resolver returns the slug for non-self viewers.

This is enforced uniformly via :func:`_is_self_view` so any future PII
fields that need similar treatment can reuse the same gate. ``Meta.exclude``
hides fields that should never be reachable through GraphQL (passwords,
auth tokens, raw IPs); custom resolvers below override ``DjangoObjectType``
auto-exposure for fields the user themselves still needs to read.
"""

from typing import Any, Optional

import graphene
from django.contrib.auth import get_user_model
from graphene import relay
from graphene_django import DjangoObjectType

from config.graphql.base import CountableConnection
from config.graphql.permissioning.permission_annotator.mixins import (
    AnnotatePermissionsForReadMixin,
)
from opencontractserver.constants.auth import OAUTH_SUB_DISPLAY_SUFFIX_LENGTH
from opencontractserver.users.models import Assignment, UserExport, UserImport

User = get_user_model()


def _stripped(value: object) -> str:
    """Return a trimmed string when ``value`` is a string, else empty."""
    return value.strip() if isinstance(value, str) else ""


def _is_self_view(user_obj: Any, info: Any) -> bool:
    """True iff the requester *is* the user object being resolved.

    Authentication is required: anonymous viewers, server-side ``None``
    contexts (e.g. internal callers passing ``info=None``), and inactive
    sessions all return ``False``. Superusers deliberately do not bypass
    this gate — PII access is reserved for Django admin, not the public
    GraphQL API.
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
    return requester.pk == user_obj.pk


def _self_only(user_obj: Any, info: Any, attr: str) -> Optional[Any]:
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


def _redacted_handle(user_obj: Any) -> str:
    """Stable, non-PII fallback when no ``slug`` is available.

    Uses the user's primary key suffix so two distinct users never collide
    on the same fallback. Mirrors the ``user_<sub>`` shape used elsewhere
    so frontend code can format both consistently.
    """
    pk_suffix = str(getattr(user_obj, "pk", "") or "")[
        -OAUTH_SUB_DISPLAY_SUFFIX_LENGTH:
    ]
    return f"user_{pk_suffix or 'unknown'}"


class UserType(AnnotatePermissionsForReadMixin, DjangoObjectType):
    # ------------------------------------------------------------------
    # Public identity
    # ------------------------------------------------------------------
    display_name = graphene.String(
        description=(
            "Privacy-preserving display name. Non-self viewers always receive "
            "the user's ``slug`` (or a redacted ``user_<id>`` fallback when "
            "no slug exists). Self-views still get the rich profile-name "
            "fallback for personal-settings UI. The raw OAuth ``provider|sub`` "
            "value used as the Django ``username`` for social-login users is "
            "never returned."
        )
    )

    # ------------------------------------------------------------------
    # PII fields — declared explicitly so the self-only resolvers below
    # run instead of ``DjangoObjectType``'s default auto-resolver.
    # Returning ``None`` for non-self viewers is the security boundary.
    # ------------------------------------------------------------------
    email = graphene.String(
        description=(
            "Email address. Returned **only** when the requesting user is "
            "viewing their own profile; ``null`` for everyone else, including "
            "superusers. Real PII reaches the GraphQL surface only via the "
            "``me`` query / profile-settings flow."
        )
    )
    username = graphene.String(
        description=(
            "Login username. Self-only. For OAuth/social users this is the "
            "raw provider ``sub`` and must never be exposed cross-user — use "
            "``slug`` or ``displayName`` for any UI that identifies a user."
        )
    )
    name = graphene.String(description="Full name claim. Self-only.")
    first_name = graphene.String(description="First name. Self-only.")
    last_name = graphene.String(description="Last name. Self-only.")
    given_name = graphene.String(description="OIDC ``given_name`` claim. Self-only.")
    family_name = graphene.String(description="OIDC ``family_name`` claim. Self-only.")
    phone = graphene.String(description="Phone number. Self-only.")
    email_verified = graphene.Boolean(
        description="Whether the user has verified their email. Self-only."
    )
    is_social_user = graphene.Boolean(
        description=(
            "Whether the user signed in through a social/OAuth provider. "
            "Self-only — exposes account-shape information that could be "
            "used to fingerprint identity providers."
        )
    )

    # ------------------------------------------------------------------
    # Reputation / activity (already public; resolvers below)
    # ------------------------------------------------------------------
    reputation_global = graphene.Int(
        description="Global reputation score across all corpuses"
    )
    reputation_for_corpus = graphene.Int(
        corpus_id=graphene.ID(required=True),
        description="Reputation score for a specific corpus",
    )

    total_messages = graphene.Int(
        description="Total number of messages posted by this user"
    )
    total_threads_created = graphene.Int(
        description="Total number of threads created by this user"
    )
    total_annotations_created = graphene.Int(
        description="Total number of annotations created by this user (visible to requester)"
    )
    total_documents_uploaded = graphene.Int(
        description="Total number of documents uploaded by this user (visible to requester)"
    )

    can_import_corpus = graphene.Boolean(
        description=(
            "Whether this user is permitted to import a corpus. Mirrors the "
            "server-side check in UploadCorpusImportZip / ImportZipToCorpus: "
            "false for usage-capped users when "
            "USAGE_CAPPED_USER_CAN_IMPORT_CORPUS is disabled."
        )
    )

    # ------------------------------------------------------------------
    # Self-only resolvers
    # ------------------------------------------------------------------
    def resolve_email(self, info) -> Optional[str]:
        return _self_only(self, info, "email")

    def resolve_username(self, info) -> Optional[str]:
        return _self_only(self, info, "username")

    def resolve_name(self, info) -> Optional[str]:
        return _self_only(self, info, "name")

    def resolve_first_name(self, info) -> Optional[str]:
        return _self_only(self, info, "first_name")

    def resolve_last_name(self, info) -> Optional[str]:
        return _self_only(self, info, "last_name")

    def resolve_given_name(self, info) -> Optional[str]:
        return _self_only(self, info, "given_name")

    def resolve_family_name(self, info) -> Optional[str]:
        return _self_only(self, info, "family_name")

    def resolve_phone(self, info) -> Optional[str]:
        return _self_only(self, info, "phone")

    def resolve_email_verified(self, info) -> Optional[bool]:
        if not _is_self_view(self, info):
            return None
        return bool(getattr(self, "email_verified", False))

    def resolve_is_social_user(self, info) -> Optional[bool]:
        if not _is_self_view(self, info):
            return None
        return bool(getattr(self, "is_social_user", False))

    def resolve_can_import_corpus(self, info) -> bool:
        # ``self`` here is the User model instance being resolved on, not
        # necessarily the requester. ``can_import_corpus`` is a property of
        # *that* user; the cap-based gating is the same regardless of viewer
        # because the leaderboard etc. don't surface this field cross-user.
        if not getattr(self, "is_authenticated", False):
            return False
        from django.conf import settings

        if self.is_usage_capped and not settings.USAGE_CAPPED_USER_CAN_IMPORT_CORPUS:
            return False
        return True

    def resolve_display_name(self, info) -> str:
        """
        Resolve a privacy-preserving display name for this user.

        Non-self viewers always get the user's ``slug`` (or a redacted
        ``user_<pk-suffix>`` fallback when slug is unset — should not
        happen post-migration, but is defensive against partial data).

        Self-views walk the rich profile-name fallback so settings UIs
        can show "Welcome, Alice". The raw OAuth ``provider|sub`` used as
        the Django ``username`` for social-login users is never returned;
        we redact it to ``user_<sub-suffix>``.

        Priority for self-views (first non-empty wins):
        1. ``name`` — full-name claim from Auth0 profile.
        2. ``given_name`` + ``family_name`` — Auth0 split-name claims.
        3. ``first_name`` + ``last_name`` — legacy Django profile fields.
        4. ``username`` — only for non-social local users (no OAuth sub).
        5. Redacted ``user_<sub-suffix>`` fallback.

        ``slug`` is intentionally not in the self-view chain: the user's
        choice of personal name should win for "what does my settings
        page greet me with?", and slug is what other people see anyway.
        """
        if not _is_self_view(self, info):
            slug = _stripped(getattr(self, "slug", ""))
            return slug or _redacted_handle(self)

        name = _stripped(getattr(self, "name", ""))
        if name:
            return name

        given_family = " ".join(
            part
            for part in (
                _stripped(getattr(self, "given_name", "")),
                _stripped(getattr(self, "family_name", "")),
            )
            if part
        )
        if given_family:
            return given_family

        first_last = " ".join(
            part
            for part in (
                _stripped(getattr(self, "first_name", "")),
                _stripped(getattr(self, "last_name", "")),
            )
            if part
        )
        if first_last:
            return first_last

        username = _stripped(getattr(self, "username", ""))
        is_social = bool(getattr(self, "is_social_user", False))
        if username and not is_social:
            return username

        if username:
            sub = username.rsplit("|", 1)[-1]
            return f"user_{sub[-OAUTH_SUB_DISPLAY_SUFFIX_LENGTH:]}"

        return _redacted_handle(self)

    def resolve_reputation_global(self, info) -> Any:
        """
        Resolve global reputation for this user.

        Uses pre-attached _reputation_global from resolve_global_leaderboard
        to avoid N+1 queries. Falls back to database query for single-user
        lookups.
        """
        if hasattr(self, "_reputation_global") and self._reputation_global is not None:
            return self._reputation_global

        from opencontractserver.conversations.models import UserReputation

        try:
            rep = UserReputation.objects.get(user=self, corpus__isnull=True)
            return rep.reputation_score
        except UserReputation.DoesNotExist:
            return 0

    def resolve_reputation_for_corpus(self, info, corpus_id) -> Any:
        from graphql_relay import from_global_id

        from opencontractserver.conversations.models import UserReputation

        try:
            _, corpus_pk = from_global_id(corpus_id)
            rep = UserReputation.objects.get(user=self, corpus_id=corpus_pk)
            return rep.reputation_score
        except UserReputation.DoesNotExist:
            return 0
        except Exception:
            return 0

    def resolve_total_messages(self, info) -> int:
        from opencontractserver.conversations.models import (
            ChatMessage,
            MessageTypeChoices,
        )

        return (
            ChatMessage.objects.visible_to_user(info.context.user)
            .filter(creator=self, msg_type=MessageTypeChoices.HUMAN)
            .count()
        )

    def resolve_total_threads_created(self, info) -> Any:
        from opencontractserver.conversations.models import Conversation

        return (
            Conversation.objects.visible_to_user(info.context.user)
            .filter(creator=self, conversation_type="thread")
            .count()
        )

    def resolve_total_annotations_created(self, info) -> Any:
        from opencontractserver.annotations.models import Annotation

        return (
            Annotation.objects.filter(creator=self)
            .visible_to_user(info.context.user)
            .count()
        )

    def resolve_total_documents_uploaded(self, info) -> Any:
        from opencontractserver.documents.models import Document

        return (
            Document.objects.visible_to_user(info.context.user)
            .filter(creator=self)
            .count()
        )

    class Meta:
        model = User
        interfaces = [relay.Node]
        connection_class = CountableConnection
        # Block model fields that should never reach the GraphQL surface,
        # even for self-views. ``password`` is the obvious one; the rest
        # are tracking metadata that has no client use case and would
        # leak operational details about a user (when they last logged
        # in, what IP, whether their profile is being synced from Auth0).
        exclude = (
            "password",
            "last_ip",
            "last_login",
            "last_synced",
            "synced",
            "auth0_Id",
            "first_signed_in",
        )


class AssignmentType(AnnotatePermissionsForReadMixin, DjangoObjectType):
    class Meta:
        model = Assignment
        interfaces = [relay.Node]
        connection_class = CountableConnection


class UserExportType(AnnotatePermissionsForReadMixin, DjangoObjectType):
    def resolve_file(self, info) -> Any:
        return "" if not self.file else info.context.build_absolute_uri(self.file.url)

    class Meta:
        model = UserExport
        interfaces = [relay.Node]
        connection_class = CountableConnection


class UserImportType(AnnotatePermissionsForReadMixin, DjangoObjectType):
    def resolve_zip(self, info) -> Any:
        return "" if not self.file else info.context.build_absolute_uri(self.zip.url)

    class Meta:
        model = UserImport
        interfaces = [relay.Node]
        connection_class = CountableConnection


class BulkDocumentUploadStatusType(graphene.ObjectType):
    """Type for checking the status of a bulk document upload job"""

    job_id = graphene.String()
    success = graphene.Boolean()
    total_files = graphene.Int()
    processed_files = graphene.Int()
    skipped_files = graphene.Int()
    error_files = graphene.Int()
    document_ids = graphene.List(graphene.String)
    errors = graphene.List(graphene.String)
    completed = graphene.Boolean()


class UserFeedbackType(AnnotatePermissionsForReadMixin, DjangoObjectType):
    class Meta:
        from opencontractserver.feedback.models import UserFeedback

        model = UserFeedback
        interfaces = [relay.Node]
        connection_class = CountableConnection

    # https://docs.graphene-python.org/projects/django/en/latest/queries/#default-queryset
    @classmethod
    def get_queryset(cls, queryset, info) -> Any:
        from django.db.models import QuerySet

        # When the parent resolver prefetched the reverse relation
        # (see ``AnnotationQueryOptimizer.get_document_annotations`` which
        # registers a ``Prefetch("user_feedback", ...)``), the manager passed
        # in here has its parent's ``_prefetched_objects_cache`` populated.
        # Re-applying ``.visible_to_user(...)`` invalidates that cache and
        # forces a fresh SELECT per parent row — the original N+1 storm we
        # were trying to eliminate. Detect the prefetch and pass through.
        # ``instance``, ``prefetch_cache_name``, and ``_prefetched_objects_cache``
        # are Django RelatedManager internals — if their shape changes in a
        # future release the fallback (re-applying ``visible_to_user``) keeps
        # correctness intact, only losing the per-row optimisation.
        instance = getattr(queryset, "instance", None)
        cache_name = getattr(queryset, "prefetch_cache_name", None)
        prefetched = getattr(instance, "_prefetched_objects_cache", None) or {}
        if instance is not None and cache_name is not None and cache_name in prefetched:
            return queryset

        if issubclass(type(queryset), QuerySet):
            return queryset.visible_to_user(info.context.user)
        elif "RelatedManager" in str(type(queryset)):
            # https://stackoverflow.com/questions/11320702/import-relatedmanager-from-django-db-models-fields-related
            return queryset.all().visible_to_user(info.context.user)
        else:
            return queryset
