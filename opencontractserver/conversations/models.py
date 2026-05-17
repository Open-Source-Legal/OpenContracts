from typing import TYPE_CHECKING, Any, Literal

import django
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import ValidationError
from django.db import models
from guardian.models import GroupObjectPermissionBase, UserObjectPermissionBase

from opencontractserver.annotations.models import Annotation
from opencontractserver.constants.search import DIM_TO_FIELD_MAP
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.shared.defaults import jsonfield_default_value
from opencontractserver.shared.fields import NullableJSONField
from opencontractserver.shared.Managers import BaseVisibilityManager
from opencontractserver.shared.mixins import HasEmbeddingMixin
from opencontractserver.shared.Models import BaseOCModel

if TYPE_CHECKING:
    from opencontractserver.users.models import User as UserModel

User = get_user_model()


# Legacy type hint for streaming message events (used in async handlers)
StreamingMessageType = Literal[
    "ASYNC_START", "ASYNC_CONTENT", "ASYNC_FINISH", "SYNC_CONTENT"
]

# For backwards compatibility - alias to the new name
MessageType = StreamingMessageType


# Message type choices for ChatMessage.msg_type field
class MessageTypeChoices(models.TextChoices):
    SYSTEM = "SYSTEM", "System"
    HUMAN = "HUMAN", "Human"
    LLM = "LLM", "LLM"


# NEW – persisted lifecycle state so the frontend does not have to
# inspect JSON blobs to determine whether a message is complete, paused…
class MessageStateChoices(models.TextChoices):
    IN_PROGRESS = "in_progress", "In Progress"
    COMPLETED = "completed", "Completed"
    CANCELLED = "cancelled", "Cancelled"
    ERROR = "error", "Error"
    AWAITING_APPROVAL = "awaiting_approval", "Awaiting Approval"


# Conversation types for distinguishing between agent chats and discussion threads
class ConversationTypeChoices(models.TextChoices):
    CHAT = "chat", "Chat"  # Default for agent-based conversations
    THREAD = "thread", "Thread"  # For discussion threads


# Agent types for multi-agent conversation support
class AgentTypeChoices(models.TextChoices):
    DOCUMENT_AGENT = "document_agent", "Document Agent"
    CORPUS_AGENT = "corpus_agent", "Corpus Agent"


# Custom QuerySet for soft delete functionality
class SoftDeleteQuerySet(models.QuerySet):
    """
    QuerySet that filters soft-deleted objects and implements user visibility.
    """

    def visible_to_user(self, user=None):
        """
        Returns queryset filtered to objects visible to the user.
        Maintains soft-delete filtering from the base queryset.
        """
        from django.apps import apps
        from django.db.models import Q

        # Handle None user as anonymous
        if user is None:
            user = AnonymousUser()

        # Start with current queryset (already has soft-delete filtering)
        queryset = self

        # Superusers see everything
        if hasattr(user, "is_superuser") and user.is_superuser:
            return queryset.order_by("created")

        # Anonymous users only see public items
        if user.is_anonymous:
            return queryset.filter(is_public=True)

        # Authenticated users: public, created by them, or explicitly shared
        model_name = self.model._meta.model_name
        app_label = self.model._meta.app_label

        try:
            permission_model_name = f"{model_name}userobjectpermission"
            permission_model_type = apps.get_model(app_label, permission_model_name)
            permitted_ids = permission_model_type.objects.filter(
                permission__codename=f"read_{model_name}", user_id=user.id
            ).values_list("content_object_id", flat=True)

            return queryset.filter(
                Q(creator_id=user.id) | Q(is_public=True) | Q(id__in=permitted_ids)
            )
        except LookupError:
            # Fallback if permission model doesn't exist
            return queryset.filter(Q(creator_id=user.id) | Q(is_public=True))


# QuerySets with vector search support
class ConversationQuerySet(SoftDeleteQuerySet):
    """
    QuerySet for Conversation model with vector search capabilities.
    Combines soft-delete filtering with vector similarity search.

    Implements bifurcated visibility based on conversation_type:
    - CHAT: Restrictive (creator + explicit permissions + public)
    - THREAD: Context-based (inherits visibility from corpus/document)
    """

    from opencontractserver.shared.mixins import VectorSearchViaEmbeddingMixin

    # Use the VectorSearchViaEmbeddingMixin directly within the class
    EMBEDDING_RELATED_NAME = "embedding_set"

    def visible_to_user(
        self, user: "UserModel | AnonymousUser | None" = None
    ) -> "ConversationQuerySet":
        """
        Returns queryset filtered to conversations visible to the user.

        Bifurcated logic based on conversation_type:

        CHAT type (restrictive - personal agent chats):
        - Creator can see their own chats
        - Users with explicit guardian permission can see
        - Public chats are visible to all

        THREAD type (context-based - collaborative discussions):
        - All CHAT rules apply, PLUS:
        - If only chat_with_corpus is set: user must have READ on corpus
        - If only chat_with_document is set: user must have READ on document
        - If BOTH are set: user must have READ on corpus AND document (AND logic)

        Note on performance: This method executes subqueries for visible corpus/document
        IDs on each call. For list queries in GraphQL resolvers, consider using
        ConversationQueryOptimizer which provides request-level caching.

        Args:
            user: The user to filter visibility for. None is treated as anonymous.

        Returns:
            QuerySet of visible conversations, ordered by -created (newest first).
        """
        from django.apps import apps
        from django.db.models import Q

        from opencontractserver.corpuses.models import Corpus
        from opencontractserver.documents.models import Document

        # Handle None user as anonymous
        if user is None:
            user = AnonymousUser()

        # Start with current queryset (already has soft-delete filtering)
        queryset = self

        # Superusers see everything
        if hasattr(user, "is_superuser") and user.is_superuser:
            return queryset.distinct().order_by("-created")

        # Anonymous users: can ONLY view THREADs (never CHATs)
        # Per consolidated_permissioning_guide.md line 604: "Anonymous Users: Can only view threads on public resources"
        if user.is_anonymous:
            # Base: directly public THREADs only (anonymous cannot see CHATs at all)
            anon_base = Q(
                is_public=True, conversation_type=ConversationTypeChoices.THREAD
            )

            # Context inheritance for THREADs on public corpuses/documents
            # Anonymous users can see threads linked to public corpuses/documents.
            # The thread's own is_public flag provides DIRECT visibility (via anon_base),
            # while context inheritance provides visibility through the resource.
            # Per permissioning guide: "threads on public resources" means the
            # corpus/document is public, not the thread itself.
            public_corpus_ids = Corpus.objects.filter(is_public=True).values_list(
                "id", flat=True
            )
            public_doc_ids = Document.objects.filter(is_public=True).values_list(
                "id", flat=True
            )

            # Thread on public corpus only - inherits visibility from corpus
            anon_corpus_context = Q(
                conversation_type=ConversationTypeChoices.THREAD,
                chat_with_corpus_id__in=public_corpus_ids,
                chat_with_document__isnull=True,
            )
            # Thread on public document only - inherits visibility from document
            anon_doc_context = Q(
                conversation_type=ConversationTypeChoices.THREAD,
                chat_with_document_id__in=public_doc_ids,
                chat_with_corpus__isnull=True,
            )
            # Thread on both corpus and document - MIN permission rule:
            # need BOTH corpus AND document to be public
            anon_both_context = Q(
                conversation_type=ConversationTypeChoices.THREAD,
                chat_with_corpus_id__in=public_corpus_ids,
                chat_with_document_id__in=public_doc_ids,
            )

            anon_filter = (
                anon_base | anon_corpus_context | anon_doc_context | anon_both_context
            )
            return queryset.filter(anon_filter).distinct().order_by("-created")

        # Get explicitly permitted conversation IDs via guardian
        model_name = self.model._meta.model_name
        app_label = self.model._meta.app_label

        try:
            permission_model_name = f"{model_name}userobjectpermission"
            permission_model_type = apps.get_model(app_label, permission_model_name)
            permitted_ids = permission_model_type.objects.filter(
                permission__codename=f"read_{model_name}", user_id=user.id
            ).values_list("content_object_id", flat=True)
        except LookupError:
            permitted_ids = []

        # Base conditions: apply to BOTH CHAT and THREAD types
        base_conditions = (
            Q(creator_id=user.id) | Q(is_public=True) | Q(id__in=permitted_ids)
        )

        # CHAT type: base conditions only (restrictive)
        chat_filter = (
            Q(conversation_type=ConversationTypeChoices.CHAT) & base_conditions
        )

        # THREAD type: base conditions + context inheritance
        # Get visible corpus and document IDs for this user.
        # Note: These are lazy QuerySets - they become subqueries in the final SQL,
        # not separate database queries. The database optimizer handles them efficiently.
        # For CHAT-only filters, the OR logic short-circuits these in the query plan.
        visible_corpus_ids = Corpus.objects.visible_to_user(user).values_list(
            "id", flat=True
        )
        visible_doc_ids = Document.objects.visible_to_user(user).values_list(
            "id", flat=True
        )

        # Context inheritance conditions:
        # - Each case uses AND logic internally (must have ALL required permissions)
        # - Cases are combined with OR (ANY matching case grants access)
        #
        # Case 1: Only corpus set - user must have READ on corpus
        corpus_only_context = Q(chat_with_corpus_id__in=visible_corpus_ids) & Q(
            chat_with_document__isnull=True
        )

        # Case 2: Only document set - user must have READ on document
        doc_only_context = Q(chat_with_document_id__in=visible_doc_ids) & Q(
            chat_with_corpus__isnull=True
        )

        # Case 3: Both set - user must have READ on BOTH corpus AND document
        both_context = Q(chat_with_corpus_id__in=visible_corpus_ids) & Q(
            chat_with_document_id__in=visible_doc_ids
        )

        # Note: Threads with neither corpus nor document set (orphan threads)
        # rely on base conditions only and are NOT covered by context_conditions

        # Combine context conditions with OR (any matching context grants access)
        context_conditions = corpus_only_context | doc_only_context | both_context

        # THREAD type: base conditions OR context inheritance
        thread_filter = Q(conversation_type=ConversationTypeChoices.THREAD) & (
            base_conditions | context_conditions
        )

        # Combine CHAT and THREAD filters
        return (
            queryset.filter(chat_filter | thread_filter).distinct().order_by("-created")
        )

    def search_by_embedding(
        self,
        query_vector: list[float],
        embedder_path: str,
        top_k: int = 10,
    ) -> models.QuerySet:
        """
        Vector search for conversations by embeddings.
        Inherits from VectorSearchViaEmbeddingMixin pattern.
        """
        from pgvector.django import CosineDistance

        dimension = len(query_vector)
        field_name = DIM_TO_FIELD_MAP.get(dimension)
        if not field_name:
            raise ValueError(f"Unsupported embedding dimension: {dimension}")
        vector_field = f"{self.EMBEDDING_RELATED_NAME}__{field_name}"

        # Separate local avoids django-stubs generic mismatch on annotate() rebind.
        base_qs = self.filter(
            **{
                f"{self.EMBEDDING_RELATED_NAME}__embedder_path": embedder_path,
                f"{vector_field}__isnull": False,
            }
        )
        annotated_qs = base_qs.annotate(
            similarity_score=CosineDistance(vector_field, query_vector)
        )
        return annotated_qs.order_by("similarity_score")[:top_k]


class ChatMessageQuerySet(SoftDeleteQuerySet):
    """
    QuerySet for ChatMessage model with vector search capabilities.
    Combines soft-delete filtering with vector similarity search.

    IMPORTANT: This queryset extends visibility to include moderator access.
    Users who are moderators of a conversation (via can_moderate()) can see
    all messages in that conversation, even without explicit message permissions.
    """

    EMBEDDING_RELATED_NAME = "embedding_set"

    def visible_to_user(
        self, user: "UserModel | AnonymousUser | None" = None
    ) -> "ChatMessageQuerySet":
        """
        Returns queryset filtered to messages visible to the user.

        A user can see a message if ANY of:
        1. User is superuser
        2. Message is in a visible conversation (inherits bifurcated CHAT/THREAD logic)
        3. User created the message
        4. User has explicit permission on the message
        5. User can moderate the conversation (corpus/document/thread owner)

        The primary visibility check (case 2) leverages Conversation.objects.visible_to_user()
        which implements bifurcated permissions:
        - CHAT: creator + explicit permissions + public
        - THREAD: CHAT rules + context inheritance from corpus/document

        The moderator access (case 5) is retained for additional access to allow
        corpus/document owners to see all messages for moderation purposes, even
        if they wouldn't normally see the conversation.
        """
        from django.db.models import Q

        from opencontractserver.corpuses.models import Corpus
        from opencontractserver.documents.models import Document

        # Handle None user as anonymous
        if user is None:
            user = AnonymousUser()

        # Start with current queryset (already has soft-delete filtering)
        queryset = self.filter(deleted_at__isnull=True)

        # Superusers see everything
        if hasattr(user, "is_superuser") and user.is_superuser:
            return queryset.order_by("created")

        # Anonymous users only see messages in public conversations
        if user.is_anonymous:
            return queryset.filter(conversation__is_public=True).order_by("created")

        # Primary visibility: messages in visible conversations
        # This inherits the bifurcated CHAT/THREAD permission logic
        # Note: Conversation is defined in this same module, no import needed
        visible_conversation_ids = Conversation.objects.visible_to_user(
            user
        ).values_list("id", flat=True)
        conversation_visible = Q(conversation_id__in=visible_conversation_ids)

        # Additional conditions for explicit message-level access
        from django.apps import apps

        try:
            permission_model = apps.get_model(
                "conversations", "chatmessageuserobjectpermission"
            )
            has_permission = Q(
                id__in=permission_model.objects.filter(user=user).values_list(
                    "content_object_id", flat=True
                )
            )
        except LookupError:
            has_permission = Q(pk__in=[])

        base_conditions = (
            Q(creator=user)  # User created the message
            | has_permission  # User has explicit permission on message
        )

        # Moderator conditions: user can moderate the conversation
        # This provides additional access beyond conversation visibility
        # for corpus/document owners who need to moderate discussions
        #
        # Includes:
        # - Conversation creator
        # - Corpus owner (for corpus-linked threads)
        # - Document owner (for document-linked threads)

        owned_corpus_ids = Corpus.objects.filter(creator=user).values_list(
            "id", flat=True
        )
        owned_document_ids = Document.objects.filter(creator=user).values_list(
            "id", flat=True
        )

        moderator_conditions = (
            Q(conversation__creator=user)  # Thread creator
            | Q(conversation__chat_with_corpus_id__in=owned_corpus_ids)  # Corpus owner
            | Q(
                conversation__chat_with_document_id__in=owned_document_ids
            )  # Document owner
        )

        # Combine all conditions with OR:
        # - Message in visible conversation, OR
        # - User created the message or has explicit permission, OR
        # - User is a moderator
        # Order by created timestamp for chronological message display
        return (
            queryset.filter(
                conversation_visible | base_conditions | moderator_conditions
            )
            .distinct()
            .order_by("created")
        )

    def search_by_embedding(
        self,
        query_vector: list[float],
        embedder_path: str,
        top_k: int = 10,
    ) -> models.QuerySet:
        """
        Vector search for chat messages by embeddings.
        Inherits from VectorSearchViaEmbeddingMixin pattern.
        """
        from pgvector.django import CosineDistance

        dimension = len(query_vector)
        field_name = DIM_TO_FIELD_MAP.get(dimension)
        if not field_name:
            raise ValueError(f"Unsupported embedding dimension: {dimension}")
        vector_field = f"{self.EMBEDDING_RELATED_NAME}__{field_name}"

        # Separate local avoids django-stubs generic mismatch on annotate() rebind.
        base_qs = self.filter(
            **{
                f"{self.EMBEDDING_RELATED_NAME}__embedder_path": embedder_path,
                f"{vector_field}__isnull": False,
            }
        )
        annotated_qs = base_qs.annotate(
            similarity_score=CosineDistance(vector_field, query_vector)
        )
        return annotated_qs.order_by("similarity_score")[:top_k]


# Custom manager for soft delete functionality
class SoftDeleteManager(BaseVisibilityManager):
    """
    Manager that combines visibility filtering with soft-delete filtering.
    Filters out soft-deleted objects by default while respecting user permissions.
    Use Model.all_objects to access soft-deleted objects.

    Inherits from BaseVisibilityManager to provide the visible_to_user() method
    required by GraphQL queries.
    """

    def get_queryset(self):
        # Return our custom queryset, filtered for non-deleted objects
        return SoftDeleteQuerySet(self.model, using=self._db).filter(
            deleted_at__isnull=True
        )

    def visible_to_user(
        self,
        user=None,
        lightweight: bool = False,
        with_doc_label_annotations: bool = False,
    ):
        """
        Override to apply soft-delete filtering on top of visibility filtering.

        ``lightweight`` and ``with_doc_label_annotations`` are forwarded to
        ``BaseVisibilityManager`` for signature parity but have no effect on
        soft-deleted models (no heavy prefetches involved).
        """
        # Get the visibility-filtered queryset from parent
        queryset = super().visible_to_user(
            user,
            lightweight=lightweight,
            with_doc_label_annotations=with_doc_label_annotations,
        )
        # Then filter out soft-deleted objects
        return queryset.filter(deleted_at__isnull=True)


# Specialized managers for Conversation and ChatMessage with vector search support
class ConversationManager(SoftDeleteManager):
    """Manager for Conversation model that uses ConversationQuerySet."""

    def get_queryset(self):
        return ConversationQuerySet(self.model, using=self._db).filter(
            deleted_at__isnull=True
        )

    def visible_to_user(
        self,
        user=None,
        lightweight: bool = False,
        with_doc_label_annotations: bool = False,
    ):
        """
        Delegate to the queryset's visible_to_user method.
        This ensures the custom visibility logic in ConversationQuerySet is used.

        ``lightweight`` and ``with_doc_label_annotations`` are accepted for
        signature parity with ``BaseVisibilityManager`` but unused — the
        underlying queryset has no heavy prefetches.
        """
        return self.get_queryset().visible_to_user(user)

    def user_can(
        self,
        user,
        instance,
        permission,
        *,
        include_group_permissions: bool = True,
        request: Any = None,
    ) -> bool:
        """Single-object authorization check for ``Conversation``.

        For **READ**, route through ``visible_to_user(user).filter(pk=...).
        exists()`` so the CHAT/THREAD bifurcation
        (``ConversationQuerySet.visible_to_user`` at lines 128-288) is the
        single source of truth — anonymous-can-only-see-public-THREADs,
        THREAD-context-inheritance, etc. all stay encoded in one place.

        For **non-READ**, delegate to ``_default_user_can`` so the
        is_public-grants-only-READ asymmetry holds: writing to a
        conversation still requires creator status or explicit guardian
        permission, and ``is_public=True`` does NOT grant writes.
        """
        from opencontractserver.types.enums import PermissionTypes
        from opencontractserver.utils.permissioning import _default_user_can

        if permission == PermissionTypes.READ:
            return self.visible_to_user(user).filter(pk=instance.pk).exists()
        return _default_user_can(
            user,
            instance,
            permission,
            include_group_permissions=include_group_permissions,
            request=request,
        )

    def search_by_embedding(self, query_vector, embedder_path, top_k=10):
        """
        Convenience method to perform vector search:
            Conversation.objects.search_by_embedding([...], "embedder/path", top_k=10)
        """
        return self.get_queryset().search_by_embedding(
            query_vector, embedder_path, top_k
        )


class ChatMessageManager(SoftDeleteManager):
    """Manager for ChatMessage model that uses ChatMessageQuerySet."""

    def get_queryset(self):
        return ChatMessageQuerySet(self.model, using=self._db).filter(
            deleted_at__isnull=True
        )

    def visible_to_user(
        self,
        user=None,
        lightweight: bool = False,
        with_doc_label_annotations: bool = False,
    ):
        """
        Delegate to the queryset's visible_to_user method.
        This ensures the custom visibility logic in ChatMessageQuerySet is used.

        ``lightweight`` and ``with_doc_label_annotations`` are accepted for
        signature parity with ``BaseVisibilityManager`` but unused — the
        underlying queryset has no heavy prefetches.
        """
        return self.get_queryset().visible_to_user(user)

    def user_can(
        self,
        user,
        instance,
        permission,
        *,
        include_group_permissions: bool = True,
        request: Any = None,
    ) -> bool:
        """Single-object authorization check for ``ChatMessage``.

        For **READ**, defer to ``visible_to_user(user).filter(pk=...).
        exists()`` so the moderator branch
        (``ChatMessageQuerySet.visible_to_user`` lines 403-425 — corpus
        owner / document owner / conversation creator) and the
        conversation-inheritance branch are the single source of truth.

        For **non-READ**, delegate to ``_default_user_can`` (creator OR
        guardian; ChatMessage has no ``is_public`` field, so the default
        branch correctly denies anonymous and non-grantee writes).
        """
        from opencontractserver.types.enums import PermissionTypes
        from opencontractserver.utils.permissioning import _default_user_can

        if permission == PermissionTypes.READ:
            return self.visible_to_user(user).filter(pk=instance.pk).exists()
        return _default_user_can(
            user,
            instance,
            permission,
            include_group_permissions=include_group_permissions,
            request=request,
        )

    def search_by_embedding(self, query_vector, embedder_path, top_k=10):
        """
        Convenience method to perform vector search:
            ChatMessage.objects.search_by_embedding([...], "embedder/path", top_k=10)
        """
        return self.get_queryset().search_by_embedding(
            query_vector, embedder_path, top_k
        )


class ConversationUserObjectPermission(UserObjectPermissionBase):
    """
    Permissions for Conversation objects at the user level.
    """

    content_object = django.db.models.ForeignKey(
        "Conversation", on_delete=django.db.models.CASCADE
    )


class ConversationGroupObjectPermission(GroupObjectPermissionBase):
    """
    Permissions for Conversation objects at the group level.
    """

    content_object = django.db.models.ForeignKey(
        "Conversation", on_delete=django.db.models.CASCADE
    )


class Conversation(BaseOCModel, HasEmbeddingMixin):
    """
    Stores high-level information about an agent-based conversation.
    Each conversation can have multiple messages (now renamed to ChatMessage) associated with it.

    Context Field Rules:
    - For CHAT type: Only ONE of chat_with_corpus OR chat_with_document can be set
      (agents need single context for streaming)
    - For THREAD type: BOTH can be set simultaneously (doc-in-corpus discussions)

    Includes HasEmbeddingMixin for vector search support on conversation titles and descriptions.
    """

    title = models.CharField(
        max_length=255,
        blank=True,
        help_text="Optional title for the conversation",
    )
    description = models.TextField(
        blank=True,
        help_text="Optional description for the conversation",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="Timestamp when the conversation was created",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="Timestamp when the conversation was last updated",
    )
    conversation_type = models.CharField(
        max_length=32,
        choices=ConversationTypeChoices.choices,
        default=ConversationTypeChoices.CHAT,
        help_text="Type of conversation: chat (agent-based) or thread (discussion)",
    )
    deleted_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp when the conversation was soft-deleted",
    )

    # Moderation fields
    is_locked = models.BooleanField(
        default=False,
        help_text="Whether the thread is locked (prevents new messages)",
    )
    locked_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp when the thread was locked",
    )
    locked_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="locked_conversations",
        null=True,
        blank=True,
        help_text="Moderator who locked the thread",
    )
    is_pinned = models.BooleanField(
        default=False,
        help_text="Whether the thread is pinned (appears at top of list)",
    )
    pinned_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp when the thread was pinned",
    )
    pinned_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="pinned_conversations",
        null=True,
        blank=True,
        help_text="Moderator who pinned the thread",
    )

    # Voting denormalized counts for performance
    upvote_count = models.IntegerField(
        default=0,
        help_text="Cached count of upvotes for this conversation/thread",
    )
    downvote_count = models.IntegerField(
        default=0,
        help_text="Cached count of downvotes for this conversation/thread",
    )

    chat_with_corpus = models.ForeignKey(
        Corpus,
        on_delete=models.SET_NULL,
        related_name="conversations",
        help_text="The corpus to which this conversation belongs",
        blank=True,
        null=True,
    )
    chat_with_document = models.ForeignKey(
        Document,
        on_delete=models.SET_NULL,
        related_name="conversations",
        help_text="The document to which this conversation belongs",
        blank=True,
        null=True,
    )

    # Context compaction bookmark — when a conversation grows large enough
    # to approach the LLM context window, older messages are summarised and
    # the summary is stored here.  On subsequent loads only messages with
    # ``id > compacted_before_message_id`` are fetched from the DB; the
    # summary is prepended as a synthetic system message.
    compaction_summary = models.TextField(
        blank=True,
        default="",
        help_text=(
            "Summary of compacted (older) messages.  Empty when no "
            "compaction has occurred."
        ),
    )
    # NOTE: This is intentionally a BigIntegerField rather than a ForeignKey
    # to avoid CASCADE deletion issues — if the referenced ChatMessage is
    # deleted, the ``id__gt`` filter in ``get_conversation_messages()``
    # remains correct because it only needs a numeric threshold, not a live
    # row.  Any message with ``id > compacted_before_message_id`` is
    # returned regardless of whether the cutoff message itself still exists.
    compacted_before_message_id = models.BigIntegerField(
        null=True,
        blank=True,
        help_text=(
            "ID of the last message that was folded into "
            "compaction_summary.  Messages with id <= this value "
            "are excluded from LLM context (but kept in the DB).  "
            "Stored as a plain integer (not a ForeignKey) so the "
            "id__gt filter remains valid even if the cutoff message "
            "is deleted."
        ),
    )

    # Agent memory curation
    memory_curated = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Whether this conversation has been curated for corpus memory.",
    )

    # Managers
    objects = ConversationManager()  # type: ignore[misc]  # Default manager with vector search support
    all_objects = models.Manager()  # Access all objects including soft-deleted

    class Meta:
        constraints = [
            # For CHAT type: enforce mutual exclusivity (at least one must be NULL)
            # For THREAD type: allow both to be set (doc-in-corpus discussions)
            django.db.models.CheckConstraint(
                condition=(
                    # THREAD type allows both fields to be set
                    django.db.models.Q(conversation_type="thread")
                    | (
                        # CHAT type requires at least one to be NULL
                        django.db.models.Q(chat_with_corpus__isnull=True)
                        | django.db.models.Q(chat_with_document__isnull=True)
                    )
                ),
                name="chat_type_mutual_exclusivity_constraint",
            ),
        ]
        indexes = [
            models.Index(fields=["deleted_at"]),  # Optimize soft-delete queries
        ]
        permissions = (
            ("permission_conversation", "permission conversation"),
            ("publish_conversation", "publish conversation"),
            ("create_conversation", "create conversation"),
            ("read_conversation", "read conversation"),
            ("update_conversation", "update conversation"),
            ("remove_conversation", "delete conversation"),
            ("comment_conversation", "comment conversation"),
        )

    def clean(self):
        """
        Validate context field rules based on conversation type.

        - CHAT type: Only ONE of chat_with_corpus OR chat_with_document can be set
        - THREAD type: Both can be set simultaneously (doc-in-corpus discussions)
        """
        if self.chat_with_corpus and self.chat_with_document:
            # Only CHAT type has mutual exclusivity requirement
            if self.conversation_type == ConversationTypeChoices.CHAT:
                raise ValidationError(
                    "For CHAT conversations, only one of chat_with_corpus or "
                    "chat_with_document can be set. Use THREAD type for "
                    "document-in-corpus discussions."
                )

    def can_moderate(self, user) -> bool:
        """
        Check if a user can moderate this conversation.

        Moderation is granted if user is ANY of:
        - Superuser
        - Conversation creator
        - Corpus owner (if chat_with_corpus is set)
        - Document owner (if chat_with_document is set)
        - Designated corpus moderator with permissions

        For THREAD type with both corpus AND document set, having moderation
        rights on EITHER grants moderation access (OR logic, not AND).
        """
        # Superusers can always moderate
        if user.is_superuser:
            return True

        # Conversation creator can always moderate
        if self.creator == user:
            return True

        # Check corpus-based moderation rights
        if self.chat_with_corpus:
            # Corpus owner can moderate
            if self.chat_with_corpus.creator == user:
                return True

            # Check if user is a designated corpus moderator
            try:
                moderator = CorpusModerator.objects.get(
                    corpus=self.chat_with_corpus, user=user
                )
                if bool(moderator.permissions):
                    return True
            except CorpusModerator.DoesNotExist:
                pass

        # Check document-based moderation rights
        if self.chat_with_document:
            # Document owner can moderate
            if self.chat_with_document.creator == user:
                return True

        # No moderation rights found
        return False

    def lock(self, moderator, reason: str = "") -> "ModerationAction":
        """
        Lock the conversation to prevent new messages.
        Creates a moderation action log.

        Returns:
            ModerationAction: The created moderation action record.
        """
        from django.utils import timezone

        if not self.can_moderate(moderator):
            raise PermissionError(
                f"User {moderator.username} does not have permission to lock this conversation"
            )

        self.is_locked = True
        self.locked_at = timezone.now()
        self.locked_by = moderator
        self.save(update_fields=["is_locked", "locked_at", "locked_by"])

        # Create moderation action log
        return ModerationAction.objects.create(
            conversation=self,
            action_type=ModerationActionType.LOCK_THREAD.value,
            moderator=moderator,
            reason=reason,
            creator=moderator,
        )

    def unlock(self, moderator, reason: str = "") -> "ModerationAction":
        """
        Unlock the conversation to allow new messages.
        Creates a moderation action log.

        Returns:
            ModerationAction: The created moderation action record.
        """
        if not self.can_moderate(moderator):
            raise PermissionError(
                f"User {moderator.username} does not have permission to unlock this conversation"
            )

        self.is_locked = False
        self.locked_at = None
        self.locked_by = None
        self.save(update_fields=["is_locked", "locked_at", "locked_by"])

        # Create moderation action log - use .value for GraphQL enum compatibility
        return ModerationAction.objects.create(
            conversation=self,
            action_type=ModerationActionType.UNLOCK_THREAD.value,
            moderator=moderator,
            reason=reason,
            creator=moderator,
        )

    def pin(self, moderator, reason: str = "") -> "ModerationAction":
        """
        Pin the conversation to appear at top of list.
        Creates a moderation action log.

        Returns:
            ModerationAction: The created moderation action record.
        """
        from django.utils import timezone

        if not self.can_moderate(moderator):
            raise PermissionError(
                f"User {moderator.username} does not have permission to pin this conversation"
            )

        self.is_pinned = True
        self.pinned_at = timezone.now()
        self.pinned_by = moderator
        self.save(update_fields=["is_pinned", "pinned_at", "pinned_by"])

        # Create moderation action log
        return ModerationAction.objects.create(
            conversation=self,
            action_type=ModerationActionType.PIN_THREAD.value,
            moderator=moderator,
            reason=reason,
            creator=moderator,
        )

    def unpin(self, moderator, reason: str = "") -> "ModerationAction":
        """
        Unpin the conversation.
        Creates a moderation action log.

        Returns:
            ModerationAction: The created moderation action record.
        """
        if not self.can_moderate(moderator):
            raise PermissionError(
                f"User {moderator.username} does not have permission to unpin this conversation"
            )

        self.is_pinned = False
        self.pinned_at = None
        self.pinned_by = None
        self.save(update_fields=["is_pinned", "pinned_at", "pinned_by"])

        # Create moderation action log
        return ModerationAction.objects.create(
            conversation=self,
            action_type=ModerationActionType.UNPIN_THREAD.value,
            moderator=moderator,
            reason=reason,
            creator=moderator,
        )

    def soft_delete_thread(self, moderator, reason: str = "") -> "ModerationAction":
        """
        Soft delete this conversation (for moderation).
        Creates a moderation action log.

        Returns:
            ModerationAction: The created moderation action record.
        """
        from django.utils import timezone

        if not self.can_moderate(moderator):
            raise PermissionError(
                f"User {moderator.username} does not have permission to delete this conversation"
            )

        self.deleted_at = timezone.now()
        self.save(update_fields=["deleted_at"])

        # Create moderation action log
        return ModerationAction.objects.create(
            conversation=self,
            action_type=ModerationActionType.DELETE_THREAD.value,
            moderator=moderator,
            reason=reason,
            creator=moderator,
        )

    def restore_thread(self, moderator, reason: str = "") -> "ModerationAction":
        """
        Restore a soft-deleted conversation.
        Creates a moderation action log.

        Returns:
            ModerationAction: The created moderation action record.
        """
        if not self.can_moderate(moderator):
            raise PermissionError(
                f"User {moderator.username} does not have permission to restore this conversation"
            )

        self.deleted_at = None
        self.save(update_fields=["deleted_at"])

        # Create moderation action log
        return ModerationAction.objects.create(
            conversation=self,
            action_type=ModerationActionType.RESTORE_THREAD.value,
            moderator=moderator,
            reason=reason,
            creator=moderator,
        )

    def __str__(self) -> str:
        return f"Conversation {self.pk} - {self.title if self.title else 'Untitled'}"

    def get_embedding_reference_kwargs(self) -> dict:
        """
        Required by HasEmbeddingMixin to specify which field references this conversation.
        """
        return {"conversation_id": self.pk}


class ChatMessage(BaseOCModel, HasEmbeddingMixin):
    """
    Represents a single chat message within an agent conversation.
    ChatMessages follow a standardized format to indicate their type,
    content, and any additional data.

    Includes HasEmbeddingMixin for vector search support on message content.
    """

    class Meta:
        indexes = [
            models.Index(fields=["deleted_at"]),  # Optimize soft-delete queries
        ]
        permissions = (
            ("permission_chatmessage", "permission chatmessage"),
            ("publish_chatmessage", "publish chatmessage"),
            ("create_chatmessage", "create chatmessage"),
            ("read_chatmessage", "read chatmessage"),
            ("update_chatmessage", "update chatmessage"),
            ("remove_chatmessage", "delete chatmessage"),
            ("comment_chatmessage", "comment chatmessage"),
        )

    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name="chat_messages",
        help_text="The conversation to which this chat message belongs",
    )
    msg_type = models.CharField(
        max_length=32,
        choices=MessageTypeChoices.choices,
        help_text="The type of message (SYSTEM, HUMAN, or LLM)",
    )
    agent_type = models.CharField(
        max_length=32,
        choices=AgentTypeChoices.choices,
        blank=True,
        null=True,
        help_text="The specific agent type that generated this message (for LLM messages)",
    )
    agent_configuration = models.ForeignKey(
        "agents.AgentConfiguration",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="messages",
        help_text="Which agent generated this message (if msgType != HUMAN)",
    )
    parent_message = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        related_name="replies",
        blank=True,
        null=True,
        db_index=True,
        help_text="Parent message for threaded replies",
    )
    content = models.TextField(
        help_text="The textual content of the chat message",
    )
    data = NullableJSONField(
        default=jsonfield_default_value,
        null=True,
        blank=True,
        help_text="Additional data associated with the chat message (stored as JSON)",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="Timestamp when the chat message was created",
    )
    deleted_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp when the message was soft-deleted",
    )

    source_document = models.ForeignKey(
        Document,
        on_delete=models.SET_NULL,
        related_name="chat_messages",
        help_text="A document that this chat message is based on",
        blank=True,
        null=True,
    )
    source_annotations = models.ManyToManyField(
        Annotation,
        related_name="chat_messages",
        help_text="Annotations that this chat message is based on",
        blank=True,
    )
    created_annotations = models.ManyToManyField(
        Annotation,
        related_name="created_by_chat_message",
        help_text="Annotations that this chat message created",
        blank=True,
    )
    mentioned_agents = models.ManyToManyField(
        "agents.AgentConfiguration",
        related_name="mentioned_in_messages",
        help_text="Agents mentioned in this message that should respond",
        blank=True,
    )

    state = models.CharField(
        max_length=32,
        choices=MessageStateChoices.choices,
        default=MessageStateChoices.COMPLETED,
        help_text="Lifecycle state of the message for quick filtering",
    )

    # Voting denormalized counts for performance
    upvote_count = models.IntegerField(
        default=0,
        help_text="Cached count of upvotes for this message",
    )
    downvote_count = models.IntegerField(
        default=0,
        help_text="Cached count of downvotes for this message",
    )

    # Managers
    objects = ChatMessageManager()  # type: ignore[misc]  # Default manager with vector search support
    all_objects = models.Manager()  # Access all objects including soft-deleted

    def soft_delete_message(self, moderator, reason: str = "") -> "ModerationAction":
        """
        Soft delete this message (for moderation).
        Creates a moderation action log.

        Returns:
            ModerationAction: The created moderation action record.
        """
        from django.utils import timezone

        if not self.conversation.can_moderate(moderator):
            raise PermissionError(
                f"User {moderator.username} does not have permission to delete this message"
            )

        self.deleted_at = timezone.now()
        self.save(update_fields=["deleted_at"])

        # Create moderation action log
        return ModerationAction.objects.create(
            message=self,
            conversation=self.conversation,
            action_type=ModerationActionType.DELETE_MESSAGE.value,
            moderator=moderator,
            reason=reason,
            creator=moderator,
        )

    def restore_message(self, moderator, reason: str = "") -> "ModerationAction":
        """
        Restore a soft-deleted message.
        Creates a moderation action log.

        Returns:
            ModerationAction: The created moderation action record.
        """
        if not self.conversation.can_moderate(moderator):
            raise PermissionError(
                f"User {moderator.username} does not have permission to restore this message"
            )

        self.deleted_at = None
        self.save(update_fields=["deleted_at"])

        # Create moderation action log
        return ModerationAction.objects.create(
            message=self,
            conversation=self.conversation,
            action_type=ModerationActionType.RESTORE_MESSAGE.value,
            moderator=moderator,
            reason=reason,
            creator=moderator,
        )

    def __str__(self) -> str:
        return (
            f"ChatMessage {self.pk} - {self.msg_type} "
            f"in conversation {self.conversation.pk}"
        )

    def get_embedding_reference_kwargs(self) -> dict:
        """
        Required by HasEmbeddingMixin to specify which field references this message.
        """
        return {"message_id": self.pk}

    # (compatibility alias added below, outside the class body)


class ChatMessageUserObjectPermission(UserObjectPermissionBase):
    """
    Permissions for ChatMessage objects at the user level.
    """

    content_object = django.db.models.ForeignKey(
        "ChatMessage", on_delete=django.db.models.CASCADE
    )


class ChatMessageGroupObjectPermission(GroupObjectPermissionBase):
    """
    Permissions for ChatMessage objects at the group level.
    """

    content_object = django.db.models.ForeignKey(
        "ChatMessage", on_delete=django.db.models.CASCADE
    )


# --------------------------------------------------------------------------- #
# Voting System Models
# --------------------------------------------------------------------------- #


class VoteType(models.TextChoices):
    """Vote type choices for upvote/downvote functionality."""

    UPVOTE = "upvote", "Upvote"
    DOWNVOTE = "downvote", "Downvote"


class MessageVote(BaseOCModel):
    """
    Tracks individual votes on chat messages.
    Users can upvote or downvote messages in discussion threads.
    One vote per user per message (can be changed from upvote to downvote).
    """

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["message", "creator"],
                name="one_vote_per_user_per_message",
            )
        ]
        permissions = (
            ("permission_messagevote", "permission messagevote"),
            ("create_messagevote", "create messagevote"),
            ("read_messagevote", "read messagevote"),
            ("update_messagevote", "update messagevote"),
            ("remove_messagevote", "delete messagevote"),
        )
        indexes = [
            models.Index(fields=["message", "vote_type"]),
            models.Index(fields=["creator"]),
        ]

    message = models.ForeignKey(
        ChatMessage,
        on_delete=models.CASCADE,
        related_name="votes",
        help_text="The message being voted on",
    )
    vote_type = models.CharField(
        max_length=16,
        choices=VoteType.choices,
        help_text="Type of vote (upvote or downvote)",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="Timestamp when the vote was cast",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="Timestamp when the vote was last changed",
    )

    def __str__(self) -> str:
        return (
            f"{self.vote_type} by {self.creator.username} "
            f"on message {self.message.pk}"
        )


class MessageVoteUserObjectPermission(UserObjectPermissionBase):
    """Permissions for MessageVote objects at the user level."""

    content_object = django.db.models.ForeignKey(
        "MessageVote", on_delete=django.db.models.CASCADE
    )


class MessageVoteGroupObjectPermission(GroupObjectPermissionBase):
    """Permissions for MessageVote objects at the group level."""

    content_object = django.db.models.ForeignKey(
        "MessageVote", on_delete=django.db.models.CASCADE
    )


class ConversationVote(BaseOCModel):
    """
    Tracks individual votes on conversations/threads.
    Users can upvote or downvote threads in discussion forums.
    One vote per user per conversation (can be changed from upvote to downvote).

    Permission: Users can vote on any conversation they can see (visibility-based).
    """

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["conversation", "creator"],
                name="one_vote_per_user_per_conversation",
            )
        ]
        permissions = (
            ("permission_conversationvote", "permission conversationvote"),
            ("create_conversationvote", "create conversationvote"),
            ("read_conversationvote", "read conversationvote"),
            ("update_conversationvote", "update conversationvote"),
            ("remove_conversationvote", "delete conversationvote"),
        )
        indexes = [
            models.Index(fields=["conversation", "vote_type"]),
            models.Index(fields=["creator"]),
        ]

    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name="votes",
        help_text="The conversation/thread being voted on",
    )
    vote_type = models.CharField(
        max_length=16,
        choices=VoteType.choices,
        help_text="Type of vote (upvote or downvote)",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="Timestamp when the vote was cast",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="Timestamp when the vote was last changed",
    )

    def __str__(self) -> str:
        return (
            f"{self.vote_type} by {self.creator.username} "
            f"on conversation {self.conversation.pk}"
        )


class ConversationVoteUserObjectPermission(UserObjectPermissionBase):
    """Permissions for ConversationVote objects at the user level."""

    content_object = django.db.models.ForeignKey(
        "ConversationVote", on_delete=django.db.models.CASCADE
    )


class ConversationVoteGroupObjectPermission(GroupObjectPermissionBase):
    """Permissions for ConversationVote objects at the group level."""

    content_object = django.db.models.ForeignKey(
        "ConversationVote", on_delete=django.db.models.CASCADE
    )


class UserReputation(BaseOCModel):
    """
    Tracks user reputation scores globally and per-corpus.
    Reputation is calculated based on upvotes/downvotes received on messages.
    """

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "corpus"],
                name="one_reputation_per_user_per_corpus",
            )
        ]
        permissions = (
            ("permission_userreputation", "permission userreputation"),
            ("create_userreputation", "create userreputation"),
            ("read_userreputation", "read userreputation"),
            ("update_userreputation", "update userreputation"),
            ("remove_userreputation", "delete userreputation"),
        )
        indexes = [
            models.Index(fields=["user", "corpus"]),
            models.Index(fields=["reputation_score"]),
        ]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="reputation_scores",
        help_text="The user whose reputation is being tracked",
    )
    corpus = models.ForeignKey(
        Corpus,
        on_delete=models.CASCADE,
        related_name="user_reputations",
        blank=True,
        null=True,
        help_text="The corpus for which reputation is tracked (null = global)",
    )
    reputation_score = models.IntegerField(
        default=0,
        help_text="Current reputation score (upvotes - downvotes)",
    )
    total_upvotes_received = models.IntegerField(
        default=0,
        help_text="Total upvotes received across all messages",
    )
    total_downvotes_received = models.IntegerField(
        default=0,
        help_text="Total downvotes received across all messages",
    )
    last_calculated_at = models.DateTimeField(
        auto_now=True,
        help_text="Timestamp when reputation was last calculated",
    )

    def __str__(self) -> str:
        corpus_name = self.corpus.title if self.corpus else "Global"
        return f"{self.user.username} - {corpus_name}: {self.reputation_score}"


class UserReputationUserObjectPermission(UserObjectPermissionBase):
    """Permissions for UserReputation objects at the user level."""

    content_object = django.db.models.ForeignKey(
        "UserReputation", on_delete=django.db.models.CASCADE
    )


class UserReputationGroupObjectPermission(GroupObjectPermissionBase):
    """Permissions for UserReputation objects at the group level."""

    content_object = django.db.models.ForeignKey(
        "UserReputation", on_delete=django.db.models.CASCADE
    )


# --------------------------------------------------------------------------- #
# Moderation System Models
# --------------------------------------------------------------------------- #


class ModeratorPermissionChoices(models.TextChoices):
    """Permission levels for corpus moderators."""

    LOCK_THREADS = "lock_threads", "Can Lock Threads"
    PIN_THREADS = "pin_threads", "Can Pin Threads"
    DELETE_MESSAGES = "delete_messages", "Can Delete Messages"
    DELETE_THREADS = "delete_threads", "Can Delete Threads"


class CorpusModerator(BaseOCModel):
    """
    Tracks designated moderators for a corpus with specific permissions.
    Corpus owners have all permissions by default.
    """

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["corpus", "user"],
                name="one_moderator_per_user_per_corpus",
            )
        ]
        permissions = (
            ("permission_corpusmoderator", "permission corpusmoderator"),
            ("create_corpusmoderator", "create corpusmoderator"),
            ("read_corpusmoderator", "read corpusmoderator"),
            ("update_corpusmoderator", "update corpusmoderator"),
            ("remove_corpusmoderator", "delete corpusmoderator"),
        )
        indexes = [
            models.Index(fields=["corpus", "user"]),
            models.Index(fields=["user"]),
        ]

    corpus = models.ForeignKey(
        Corpus,
        on_delete=models.CASCADE,
        related_name="moderators",
        help_text="The corpus being moderated",
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="moderated_corpuses",
        help_text="The user who is a moderator",
    )
    permissions = models.JSONField(
        default=list,
        help_text="List of permission strings (e.g., ['lock_threads', 'pin_threads'])",
    )
    assigned_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When moderator permissions were assigned",
    )
    assigned_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="assigned_moderators",
        null=True,
        blank=True,
        help_text="Who assigned these moderator permissions",
    )

    def has_permission(self, permission: str) -> bool:
        """Check if moderator has a specific permission."""
        return permission in self.permissions

    def __str__(self) -> str:
        return f"{self.user.username} - Moderator of {self.corpus.title}"


class CorpusModeratorUserObjectPermission(UserObjectPermissionBase):
    """Permissions for CorpusModerator objects at the user level."""

    content_object = django.db.models.ForeignKey(
        "CorpusModerator", on_delete=django.db.models.CASCADE
    )


class CorpusModeratorGroupObjectPermission(GroupObjectPermissionBase):
    """Permissions for CorpusModerator objects at the group level."""

    content_object = django.db.models.ForeignKey(
        "CorpusModerator", on_delete=django.db.models.CASCADE
    )


class ModerationActionType(models.TextChoices):
    """Types of moderation actions."""

    LOCK_THREAD = "lock_thread", "Lock Thread"
    UNLOCK_THREAD = "unlock_thread", "Unlock Thread"
    PIN_THREAD = "pin_thread", "Pin Thread"
    UNPIN_THREAD = "unpin_thread", "Unpin Thread"
    DELETE_THREAD = "delete_thread", "Delete Thread"
    RESTORE_THREAD = "restore_thread", "Restore Thread"
    DELETE_MESSAGE = "delete_message", "Delete Message"
    RESTORE_MESSAGE = "restore_message", "Restore Message"


class ModerationAction(BaseOCModel):
    """
    Tracks all moderation actions for auditing purposes.
    Creates an immutable log of what was done, when, and by whom.
    """

    class Meta:
        permissions = (
            ("permission_moderationaction", "permission moderationaction"),
            ("create_moderationaction", "create moderationaction"),
            ("read_moderationaction", "read moderationaction"),
        )
        indexes = [
            models.Index(fields=["conversation"]),
            models.Index(fields=["message"]),
            models.Index(fields=["moderator"]),
            models.Index(fields=["action_type"]),
            models.Index(fields=["created_at"]),
        ]
        ordering = ["-created_at"]

    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name="moderation_actions",
        null=True,
        blank=True,
        help_text="The conversation that was moderated",
    )
    message = models.ForeignKey(
        ChatMessage,
        on_delete=models.CASCADE,
        related_name="moderation_actions",
        null=True,
        blank=True,
        help_text="The message that was moderated",
    )
    action_type = models.CharField(
        max_length=32,
        choices=ModerationActionType.choices,
        help_text="Type of moderation action taken",
    )
    moderator = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="moderation_actions_taken",
        null=True,
        help_text="Moderator who took this action",
    )
    reason = models.TextField(
        blank=True,
        help_text="Optional reason for the moderation action",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When the action was taken",
    )

    def __str__(self) -> str:
        if self.conversation:
            target = f"conversation {self.conversation.pk}"
        elif self.message is not None:
            # Every ModerationAction is created with either conversation or message set;
            # this branch is the normal path when only a message is moderated.
            target = f"message {self.message.pk}"
        else:
            # Should never happen given construction invariants, but guard defensively.
            target = "unknown target"
        moderator_name = self.moderator.username if self.moderator else "Unknown"
        return f"{self.action_type} on {target} by {moderator_name}"


class ModerationActionUserObjectPermission(UserObjectPermissionBase):
    """Permissions for ModerationAction objects at the user level."""

    content_object = django.db.models.ForeignKey(
        "ModerationAction", on_delete=django.db.models.CASCADE
    )


class ModerationActionGroupObjectPermission(GroupObjectPermissionBase):
    """Permissions for ModerationAction objects at the group level."""

    content_object = django.db.models.ForeignKey(
        "ModerationAction", on_delete=django.db.models.CASCADE
    )


# --------------------------------------------------------------------------- #
# Backwards-compatibility: older code expects ``ChatMessage.MessageStateChoices``
# as an attribute on the model *after* import.  We expose the alias after the
# class is fully defined to avoid NameError during class construction.
# --------------------------------------------------------------------------- #

ChatMessage.MessageStateChoices = MessageStateChoices  # type: ignore[attr-defined]
