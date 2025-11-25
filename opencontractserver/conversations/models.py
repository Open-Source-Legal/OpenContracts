from typing import Literal

import django
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import models
from guardian.models import GroupObjectPermissionBase, UserObjectPermissionBase

from opencontractserver.annotations.models import Annotation
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.shared.defaults import jsonfield_default_value
from opencontractserver.shared.fields import NullableJSONField
from opencontractserver.shared.Managers import BaseVisibilityManager
from opencontractserver.shared.mixins import HasEmbeddingMixin
from opencontractserver.shared.Models import BaseOCModel

User = get_user_model()


MessageType = Literal["ASYNC_START", "ASYNC_CONTENT", "ASYNC_FINISH", "SYNC_CONTENT"]


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
        from django.contrib.auth.models import AnonymousUser
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
    """

    from opencontractserver.shared.mixins import VectorSearchViaEmbeddingMixin

    # Use the VectorSearchViaEmbeddingMixin directly within the class
    EMBEDDING_RELATED_NAME = "embedding_set"

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

        # Map dimension to vector field
        if dimension == 384:
            vector_field = f"{self.EMBEDDING_RELATED_NAME}__vector_384"
        elif dimension == 768:
            vector_field = f"{self.EMBEDDING_RELATED_NAME}__vector_768"
        elif dimension == 1536:
            vector_field = f"{self.EMBEDDING_RELATED_NAME}__vector_1536"
        elif dimension == 3072:
            vector_field = f"{self.EMBEDDING_RELATED_NAME}__vector_3072"
        else:
            raise ValueError(f"Unsupported embedding dimension: {dimension}")

        # Filter for embeddings with matching embedder_path and non-null vector
        base_qs = self.filter(
            **{
                f"{self.EMBEDDING_RELATED_NAME}__embedder_path": embedder_path,
                f"{vector_field}__isnull": False,
            }
        )

        # Annotate with similarity score using cosine distance
        base_qs = base_qs.annotate(
            similarity_score=CosineDistance(vector_field, query_vector)
        )

        # Order by similarity and limit to top_k
        return base_qs.order_by("similarity_score")[:top_k]


class ChatMessageQuerySet(SoftDeleteQuerySet):
    """
    QuerySet for ChatMessage model with vector search capabilities.
    Combines soft-delete filtering with vector similarity search.
    """

    EMBEDDING_RELATED_NAME = "embedding_set"

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

        # Map dimension to vector field
        if dimension == 384:
            vector_field = f"{self.EMBEDDING_RELATED_NAME}__vector_384"
        elif dimension == 768:
            vector_field = f"{self.EMBEDDING_RELATED_NAME}__vector_768"
        elif dimension == 1536:
            vector_field = f"{self.EMBEDDING_RELATED_NAME}__vector_1536"
        elif dimension == 3072:
            vector_field = f"{self.EMBEDDING_RELATED_NAME}__vector_3072"
        else:
            raise ValueError(f"Unsupported embedding dimension: {dimension}")

        # Filter for embeddings with matching embedder_path and non-null vector
        base_qs = self.filter(
            **{
                f"{self.EMBEDDING_RELATED_NAME}__embedder_path": embedder_path,
                f"{vector_field}__isnull": False,
            }
        )

        # Annotate with similarity score using cosine distance
        base_qs = base_qs.annotate(
            similarity_score=CosineDistance(vector_field, query_vector)
        )

        # Order by similarity and limit to top_k
        return base_qs.order_by("similarity_score")[:top_k]


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

    def visible_to_user(self, user=None):
        """
        Override to apply soft-delete filtering on top of visibility filtering.
        """
        # Get the visibility-filtered queryset from parent
        queryset = super().visible_to_user(user)
        # Then filter out soft-deleted objects
        return queryset.filter(deleted_at__isnull=True)


# Specialized managers for Conversation and ChatMessage with vector search support
class ConversationManager(SoftDeleteManager):
    """Manager for Conversation model that uses ConversationQuerySet."""

    def get_queryset(self):
        return ConversationQuerySet(self.model, using=self._db).filter(
            deleted_at__isnull=True
        )

    def visible_to_user(self, user=None):
        """
        Delegate to the queryset's visible_to_user method.
        This ensures the custom visibility logic in SoftDeleteQuerySet is used.
        """
        return self.get_queryset().visible_to_user(user)

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

    def visible_to_user(self, user=None):
        """
        Delegate to the queryset's visible_to_user method.
        This ensures the custom visibility logic in SoftDeleteQuerySet is used.
        """
        return self.get_queryset().visible_to_user(user)

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
    Only one of chat_with_corpus or chat_with_document can be set.

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

    # Managers
    objects = ConversationManager()  # Default manager with vector search support
    all_objects = models.Manager()  # Access all objects including soft-deleted

    class Meta:
        constraints = [
            django.db.models.CheckConstraint(
                check=django.db.models.Q(chat_with_corpus__isnull=True)
                | django.db.models.Q(chat_with_document__isnull=True),
                name="one_chat_field_null_constraint",
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
        Ensure that only one of chat_with_corpus or chat_with_document is set.
        """
        if self.chat_with_corpus and self.chat_with_document:
            raise ValidationError(
                "Only one of chat_with_corpus or chat_with_document can be set."
            )

    def can_moderate(self, user) -> bool:
        """
        Check if a user can moderate this conversation.
        Corpus owners and designated moderators have moderation permissions.
        """
        # If this is a corpus conversation
        if self.chat_with_corpus:
            # Check if user is the corpus owner
            if self.chat_with_corpus.creator == user:
                return True

            # Check if user is a designated moderator
            try:
                moderator = CorpusModerator.objects.get(
                    corpus=self.chat_with_corpus, user=user
                )
                return bool(moderator.permissions)
            except CorpusModerator.DoesNotExist:
                return False

        # For non-corpus conversations, only creator can moderate
        return self.creator == user

    def lock(self, moderator, reason: str = ""):
        """
        Lock the conversation to prevent new messages.
        Creates a moderation action log.
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
        ModerationAction.objects.create(
            conversation=self,
            action_type=ModerationActionType.LOCK_THREAD,
            moderator=moderator,
            reason=reason,
            creator=moderator,
        )

    def unlock(self, moderator, reason: str = ""):
        """
        Unlock the conversation to allow new messages.
        Creates a moderation action log.
        """
        if not self.can_moderate(moderator):
            raise PermissionError(
                f"User {moderator.username} does not have permission to unlock this conversation"
            )

        self.is_locked = False
        self.locked_at = None
        self.locked_by = None
        self.save(update_fields=["is_locked", "locked_at", "locked_by"])

        # Create moderation action log
        ModerationAction.objects.create(
            conversation=self,
            action_type=ModerationActionType.UNLOCK_THREAD,
            moderator=moderator,
            reason=reason,
            creator=moderator,
        )

    def pin(self, moderator, reason: str = ""):
        """
        Pin the conversation to appear at top of list.
        Creates a moderation action log.
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
        ModerationAction.objects.create(
            conversation=self,
            action_type=ModerationActionType.PIN_THREAD,
            moderator=moderator,
            reason=reason,
            creator=moderator,
        )

    def unpin(self, moderator, reason: str = ""):
        """
        Unpin the conversation.
        Creates a moderation action log.
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
        ModerationAction.objects.create(
            conversation=self,
            action_type=ModerationActionType.UNPIN_THREAD,
            moderator=moderator,
            reason=reason,
            creator=moderator,
        )

    def soft_delete_thread(self, moderator, reason: str = ""):
        """
        Soft delete this conversation (for moderation).
        Creates a moderation action log.
        """
        from django.utils import timezone

        if not self.can_moderate(moderator):
            raise PermissionError(
                f"User {moderator.username} does not have permission to delete this conversation"
            )

        self.deleted_at = timezone.now()
        self.save(update_fields=["deleted_at"])

        # Create moderation action log
        ModerationAction.objects.create(
            conversation=self,
            action_type=ModerationActionType.DELETE_THREAD,
            moderator=moderator,
            reason=reason,
            creator=moderator,
        )

    def restore_thread(self, moderator, reason: str = ""):
        """
        Restore a soft-deleted conversation.
        Creates a moderation action log.
        """
        if not self.can_moderate(moderator):
            raise PermissionError(
                f"User {moderator.username} does not have permission to restore this conversation"
            )

        self.deleted_at = None
        self.save(update_fields=["deleted_at"])

        # Create moderation action log
        ModerationAction.objects.create(
            conversation=self,
            action_type=ModerationActionType.RESTORE_THREAD,
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

    TYPE_CHOICES = (
        ("SYSTEM", "SYSTEM"),
        ("HUMAN", "HUMAN"),
        ("LLM", "LLM"),
    )

    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name="chat_messages",
        help_text="The conversation to which this chat message belongs",
    )
    msg_type = models.CharField(
        max_length=32,
        choices=TYPE_CHOICES,
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
    objects = ChatMessageManager()  # Default manager with vector search support
    all_objects = models.Manager()  # Access all objects including soft-deleted

    def soft_delete_message(self, moderator, reason: str = ""):
        """
        Soft delete this message (for moderation).
        Creates a moderation action log.
        """
        from django.utils import timezone

        if not self.conversation.can_moderate(moderator):
            raise PermissionError(
                f"User {moderator.username} does not have permission to delete this message"
            )

        self.deleted_at = timezone.now()
        self.save(update_fields=["deleted_at"])

        # Create moderation action log
        ModerationAction.objects.create(
            message=self,
            conversation=self.conversation,
            action_type=ModerationActionType.DELETE_MESSAGE,
            moderator=moderator,
            reason=reason,
            creator=moderator,
        )

    def restore_message(self, moderator, reason: str = ""):
        """
        Restore a soft-deleted message.
        Creates a moderation action log.
        """
        if not self.conversation.can_moderate(moderator):
            raise PermissionError(
                f"User {moderator.username} does not have permission to restore this message"
            )

        self.deleted_at = None
        self.save(update_fields=["deleted_at"])

        # Create moderation action log
        ModerationAction.objects.create(
            message=self,
            conversation=self.conversation,
            action_type=ModerationActionType.RESTORE_MESSAGE,
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
        target = (
            f"conversation {self.conversation.pk}"
            if self.conversation
            else f"message {self.message.pk}"
        )
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
