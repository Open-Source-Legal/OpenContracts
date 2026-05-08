"""GraphQL type definitions for user-related types."""

from typing import Any

import graphene
from django.conf import settings
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


class UserType(AnnotatePermissionsForReadMixin, DjangoObjectType):
    display_name = graphene.String(
        description=(
            "A safe, friendly display name for this user. Resolved in order from "
            "``name`` → ``given_name`` + ``family_name`` → ``first_name`` + "
            "``last_name`` → ``username`` (only when it is not an OAuth "
            "``provider|sub`` identifier) → redacted ``user_<suffix>`` fallback. "
            "Never returns the raw OAuth ``sub`` used as the Django ``username`` "
            "for social-login users."
        )
    )

    # Overrides DjangoObjectType's auto-exposed model field so the
    # ``resolve_email`` gate below runs — without this declaration the
    # resolver is bypassed for cross-user reads.
    email = graphene.String(
        description=(
            "Email address. Returned only when the requesting user is viewing "
            "themselves or is a superuser; ``null`` otherwise. This prevents "
            "the leaderboard / public-profile surfaces from leaking other "
            "users' email addresses to clients that select the field."
        )
    )

    # Reputation fields (Epic #565)
    reputation_global = graphene.Int(
        description="Global reputation score across all corpuses"
    )
    reputation_for_corpus = graphene.Int(
        corpus_id=graphene.ID(required=True),
        description="Reputation score for a specific corpus",
    )

    # Activity statistics (Issue #611 - User Profile Page)
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

    def resolve_email(self, info) -> str | None:
        """Gate ``email`` to self-views and superusers.

        ``DjangoObjectType`` would otherwise auto-expose the model field to
        any client that selected it (e.g. on a leaderboard ``user`` subtree),
        which is more PII than the leaderboard needs. Self / superuser views
        — ``me``, profile settings, admin tooling — still get the real value.
        """
        requester = getattr(info.context, "user", None)
        if requester is None or not requester.is_authenticated:
            return None
        if requester.is_superuser or requester.pk == self.pk:
            return self.email or None
        return None

    def resolve_can_import_corpus(self, info) -> bool:
        if not self.is_authenticated:
            return False
        if self.is_usage_capped and not settings.USAGE_CAPPED_USER_CAN_IMPORT_CORPUS:
            return False
        return True

    def resolve_display_name(self, info) -> str:
        """
        Resolve a privacy-preserving display name for this user.

        Priority (first non-empty wins):
        1. ``name`` — full name claim from Auth0 profile.
        2. ``given_name`` + ``family_name`` — Auth0 split-name claims.
        3. ``first_name`` + ``last_name`` — legacy Django profile fields.
        4. ``username`` — only when it does not look like a raw OAuth
           ``provider|sub`` identifier (no ``|`` separator).
        5. ``user_<last N chars of OAuth sub>`` — redacted fallback. The
           bare ``"user"`` final fallback only triggers if ``username`` is
           empty (Django enforces non-empty so this is unreachable in
           practice) and is intentionally not a unique identifier.

        ``username`` is set to the Auth0 ``sub`` for social users (see
        ``jwt_get_username_from_payload_handler``), so the raw value must
        never be surfaced in any UI. The expected profile fields (``name``,
        ``given_name``, ``family_name``, ``first_name``, ``last_name``)
        are all model columns on ``opencontractserver.users.models.User``.

        The ``|`` character alone is NOT a sufficient OAuth-sub signal —
        the project's ``UserUnicodeUsernameValidator`` allows ``|`` in
        locally-chosen usernames. The redaction branch is gated on
        ``is_social_user`` so a local user named e.g. ``alice|admin`` is
        not mistakenly redacted.
        """
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

        # Local users get their chosen username verbatim. ``|`` is allowed
        # by ``UserUnicodeUsernameValidator``, so a ``|``-containing local
        # username is legitimate and not an OAuth sub.
        if username and not is_social:
            return username

        if username:
            # Social user — never surface the raw ``sub``. ``rsplit("|", 1)``
            # strips the provider prefix even when the sub is short
            # (``auth0|abc`` → ``abc``); when the username has no ``|`` (a
            # data-corruption edge case) it falls through to the whole
            # username, which is then suffix-truncated.
            sub = username.rsplit("|", 1)[-1]
            return f"user_{sub[-OAUTH_SUB_DISPLAY_SUFFIX_LENGTH:]}"

        # Django enforces non-empty username, so this branch is effectively
        # unreachable; the bare "user" sentinel is intentionally not unique.
        return "user"

    def resolve_reputation_global(self, info) -> Any:
        """
        Resolve global reputation for this user.

        Uses pre-attached _reputation_global from resolve_global_leaderboard
        to avoid N+1 queries. Falls back to database query for single-user
        lookups.

        Epic: #565 - Corpus Engagement Metrics & Analytics
        Issue: #568 - Create GraphQL queries for engagement metrics and leaderboards
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
        """
        Resolve reputation for this user in a specific corpus.

        Epic: #565 - Corpus Engagement Metrics & Analytics
        Issue: #568 - Create GraphQL queries for engagement metrics and leaderboards
        """
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
        """
        Resolve total messages posted by this user.
        Only counts messages visible to the requesting user.

        Issue: #611 - User Profile Page
        """
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
        """
        Resolve total threads created by this user.
        Only counts threads visible to the requesting user.

        Issue: #611 - User Profile Page
        """
        from opencontractserver.conversations.models import Conversation

        return (
            Conversation.objects.visible_to_user(info.context.user)
            .filter(creator=self, conversation_type="thread")
            .count()
        )

    def resolve_total_annotations_created(self, info) -> Any:
        """
        Resolve total annotations created by this user.
        Only counts annotations visible to the requesting user.

        Issue: #611 - User Profile Page
        """
        from opencontractserver.annotations.models import Annotation

        return (
            Annotation.objects.filter(creator=self)
            .visible_to_user(info.context.user)
            .count()
        )

    def resolve_total_documents_uploaded(self, info) -> Any:
        """
        Resolve total documents uploaded by this user.
        Only counts documents visible to the requesting user.

        Issue: #611 - User Profile Page
        """
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
