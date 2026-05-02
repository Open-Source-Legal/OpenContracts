"""GraphQL type definitions for conversation, message, and moderation types."""

from typing import Any

import graphene
from django.db.models import QuerySet
from graphene import relay
from graphene.types.generic import GenericScalar
from graphene_django import DjangoObjectType
from graphql_relay import to_global_id

from config.graphql.agent_types import AgentConfigurationType
from config.graphql.base import CountableConnection
from config.graphql.base_types import AgentTypeEnum, ConversationTypeEnum
from config.graphql.permissioning.permission_annotator.mixins import (
    AnnotatePermissionsForReadMixin,
)
from opencontractserver.conversations.models import (
    ChatMessage,
    Conversation,
    ModerationAction,
)


class MentionedResourceType(graphene.ObjectType):
    """
    Represents a corpus, document, or annotation mentioned in a message.

    Mention patterns:
      @corpus:legal-contracts
      @document:contract-template
      @corpus:legal-contracts/document:contract-template
      [text](/d/.../doc?ann=id) -> Annotation mention via markdown link

    For annotations, includes full metadata for rich tooltip display.
    Permission-safe: Only returns resources visible to the requesting user.
    """

    type = graphene.String(
        required=True,
        description='Resource type: "corpus", "document", or "annotation"',
    )
    id = graphene.ID(required=True, description="Global ID of the resource")
    slug = graphene.String(description="URL-safe slug (null for annotations)")
    title = graphene.String(required=True, description="Display title of the resource")
    url = graphene.String(
        required=True, description="Frontend URL path to navigate to the resource"
    )
    corpus = graphene.Field(
        lambda: MentionedResourceType,
        description="Parent corpus context (for documents within a corpus)",
    )

    # Annotation-specific fields (Issue #689)
    raw_text = graphene.String(description="Full annotation text content")
    annotation_label = graphene.String(
        description="Annotation label name (e.g., 'Section Header', 'Definition')"
    )
    document = graphene.Field(
        lambda: MentionedResourceType,
        description="Parent document (for annotations)",
    )


class MessageType(AnnotatePermissionsForReadMixin, DjangoObjectType):

    data = GenericScalar()
    agent_type = graphene.Field(
        AgentTypeEnum, description="Type of agent that generated this message"
    )
    agent_configuration = graphene.Field(
        AgentConfigurationType,
        description="Agent configuration that generated this message",
    )
    mentioned_resources = graphene.List(
        MentionedResourceType,
        description="Corpuses and documents mentioned in this message using @ syntax. "
        "Only includes resources visible to the requesting user.",
    )
    user_vote = graphene.String(
        description="Current user's vote on this message: 'UPVOTE', 'DOWNVOTE', or null"
    )

    def resolve_msg_type(self, info) -> Any:
        """Convert msg_type to string for GraphQL enum compatibility."""
        if self.msg_type:
            # Handle both string values and enum members
            if hasattr(self.msg_type, "value"):
                return self.msg_type.value
            return self.msg_type
        return None

    def resolve_agent_type(self, info) -> Any:
        """Convert string agent_type from model to enum."""
        if self.agent_type:
            return AgentTypeEnum.get(self.agent_type)
        return None

    def resolve_agent_configuration(self, info) -> Any:
        """Resolve agent_configuration field."""
        return self.agent_configuration

    def resolve_user_vote(self, info) -> Any:
        """
        Returns the current user's vote on this message.

        Returns:
            'UPVOTE' if the user has upvoted the message
            'DOWNVOTE' if the user has downvoted the message
            None if the user has not voted or is not authenticated
        """
        user = info.context.user
        if not user or not user.is_authenticated:
            return None

        from opencontractserver.conversations.models import MessageVote

        vote = MessageVote.objects.filter(message=self, creator=user).first()
        if vote:
            return vote.vote_type.upper()  # Return 'UPVOTE' or 'DOWNVOTE'
        return None

    def resolve_mentioned_resources(self, info) -> Any:
        """
        Parse message content for @mentions and return structured resource references.

        Patterns:
          @corpus:slug -> Corpus
          @document:slug -> Document
          @corpus:corpus-slug/document:doc-slug -> Document in Corpus
          [text](/d/.../doc?ann=id) -> Annotation (via markdown link)

        SECURITY: Uses .visible_to_user() to enforce permissions.
        Mentions to inaccessible resources are silently ignored.
        """
        import base64
        import binascii
        import re
        from urllib.parse import parse_qs, urlparse

        from opencontractserver.annotations.models import Annotation
        from opencontractserver.corpuses.models import Corpus
        from opencontractserver.documents.models import Document, DocumentPath

        def _extract_annotation_id(url: str) -> Any:
            """
            Extract annotation ID from URL query params.

            Handles both plain IDs and Base64-encoded Relay global IDs.

            Examples:
                /d/user/doc?ann=123 -> 123
                /d/user/corpus/doc?ann=QW5ub3RhdGlvblR5cGU6Mw== -> 3
            """
            parsed = urlparse(url)
            query = parse_qs(parsed.query)
            ann_ids = query.get("ann", [])

            if not ann_ids:
                return None

            ann_id = ann_ids[0]

            # Handle Relay-style Base64 global IDs (e.g., "QW5ub3RhdGlvblR5cGU6Mw==")
            try:
                decoded = base64.b64decode(ann_id).decode("utf-8")
                # Format: "AnnotationType:123" -> extract "123"
                parts = decoded.split(":")
                if len(parts) == 2:
                    return int(parts[1])
            except (ValueError, binascii.Error, UnicodeDecodeError):
                pass

            # Already a plain ID
            try:
                return int(ann_id)
            except ValueError:
                return None

        content = self.content or ""
        mentions = []
        user = info.context.user

        # Pattern 1: @corpus:slug/document:slug (must check first to avoid double-matching)
        corpus_doc_pattern = r"@corpus:([a-z0-9-]+)/document:([a-z0-9-]+)"
        for corpus_slug, doc_slug in re.findall(corpus_doc_pattern, content):
            try:
                corpus = Corpus.objects.visible_to_user(user).get(slug=corpus_slug)
                # Use filter().first() instead of get() to handle case where doc not in corpus
                document = (
                    Document.objects.visible_to_user(user).filter(slug=doc_slug).first()
                )

                if document and corpus:
                    # Check if document is actually in this corpus via DocumentPath
                    if DocumentPath.objects.filter(
                        document=document, corpus=corpus
                    ).exists():
                        mentions.append(
                            MentionedResourceType(
                                type="document",
                                id=document.id,
                                slug=document.slug,
                                title=document.title,
                                url=f"/d/{corpus.creator.slug}/{corpus.slug}/{document.slug}",
                                corpus=MentionedResourceType(
                                    type="corpus",
                                    id=corpus.id,
                                    slug=corpus.slug,
                                    title=corpus.title,
                                    url=f"/c/{corpus.creator.slug}/{corpus.slug}",
                                ),
                            )
                        )
            except (Corpus.DoesNotExist, Document.DoesNotExist):
                # Permission denied or doesn't exist - silently ignore
                continue

        # Pattern 2: @corpus:slug (but not if followed by /document:)
        corpus_pattern = r"@corpus:([a-z0-9-]+)(?!/document:)"
        for corpus_slug in re.findall(corpus_pattern, content):
            try:
                corpus = Corpus.objects.visible_to_user(user).get(slug=corpus_slug)
                mentions.append(
                    MentionedResourceType(
                        type="corpus",
                        id=corpus.id,
                        slug=corpus.slug,
                        title=corpus.title,
                        url=f"/c/{corpus.creator.slug}/{corpus.slug}",
                    )
                )
            except Corpus.DoesNotExist:
                # Permission denied or doesn't exist - silently ignore
                continue

        # Pattern 3: @document:slug (standalone)
        # The regex @document: will NOT match /document: in corpus/document patterns,
        # so we can safely process all matches without checking for duplicates
        doc_pattern = r"@document:([a-z0-9-]+)"
        for doc_slug in re.findall(doc_pattern, content):
            try:
                document = Document.objects.visible_to_user(user).get(slug=doc_slug)
                url = f"/d/{document.creator.slug}/{document.slug}"

                # Try to get corpus context via DocumentPath
                doc_path = DocumentPath.objects.filter(document=document).first()
                corpus = doc_path.corpus if doc_path else None

                mentions.append(
                    MentionedResourceType(
                        type="document",
                        id=document.id,
                        slug=document.slug,
                        title=document.title,
                        url=url,
                        corpus=(
                            MentionedResourceType(
                                type="corpus",
                                id=corpus.id,
                                slug=corpus.slug,
                                title=corpus.title,
                                url=f"/c/{corpus.creator.slug}/{corpus.slug}",
                            )
                            if corpus
                            else None
                        ),
                    )
                )
            except Document.DoesNotExist:
                # Permission denied or doesn't exist - silently ignore
                continue

        # Pattern 4: Annotation mentions via markdown links (Issue #689)
        # Matches: [any text](/d/path?...ann=id...)
        # Handles both corpus-scoped and non-corpus-scoped document URLs
        link_pattern = r"\[([^\]]+)\]\((/d/[^)]+\?[^)]*ann=[^)]+)\)"

        for _link_text, url in re.findall(link_pattern, content):
            ann_id = _extract_annotation_id(url)
            if not ann_id:
                continue

            try:
                annotation = Annotation.objects.visible_to_user(user).get(id=ann_id)
                doc = annotation.document
                label = annotation.annotation_label

                mentions.append(
                    MentionedResourceType(
                        type="annotation",
                        id=annotation.id,
                        slug=None,  # Annotations don't have slugs
                        title=label.text if label else "Annotation",
                        url=url,  # Preserve original URL for navigation
                        raw_text=annotation.raw_text,
                        annotation_label=label.text if label else None,
                        document=MentionedResourceType(
                            type="document",
                            id=doc.id,
                            slug=doc.slug,
                            title=doc.title,
                            url=f"/d/{doc.creator.slug}/{doc.slug}",
                        ),
                    )
                )
            except Annotation.DoesNotExist:
                # Permission denied or doesn't exist - silently ignore
                continue

        return mentions

    class Meta:
        model = ChatMessage
        interfaces = [relay.Node]
        connection_class = CountableConnection


class ConversationType(AnnotatePermissionsForReadMixin, DjangoObjectType):

    all_messages = graphene.List(MessageType)
    conversation_type = graphene.Field(
        ConversationTypeEnum, description="Type of conversation (chat or thread)"
    )
    user_vote = graphene.String(
        description="Current user's vote on this conversation: 'UPVOTE', 'DOWNVOTE', or null"
    )

    def resolve_all_messages(self, info) -> Any:
        return self.chat_messages.all()

    def resolve_conversation_type(self, info) -> Any:
        """Convert string conversation_type from model to enum."""
        if self.conversation_type:
            return ConversationTypeEnum.get(self.conversation_type)
        return None

    def resolve_user_vote(self, info) -> Any:
        """
        Returns the current user's vote on this conversation/thread.

        Returns:
            'UPVOTE' if the user has upvoted the conversation
            'DOWNVOTE' if the user has downvoted the conversation
            None if the user has not voted or is not authenticated
        """
        user = info.context.user
        if not user or not user.is_authenticated:
            return None

        from opencontractserver.conversations.models import ConversationVote

        vote = ConversationVote.objects.filter(conversation=self, creator=user).first()
        if vote:
            return vote.vote_type.upper()  # Return 'UPVOTE' or 'DOWNVOTE'
        return None

    @classmethod
    def get_node(cls, info, id) -> Any:
        """
        Override the default node resolution to apply permission checks.
        Anonymous users can only see public conversations.
        Authenticated users can see public, their own, or explicitly shared.
        """
        if id is None:
            return None

        try:
            queryset = Conversation.objects.visible_to_user(info.context.user)
            return queryset.get(pk=id)
        except Conversation.DoesNotExist:
            return None

    class Meta:
        model = Conversation
        interfaces = [relay.Node]
        connection_class = CountableConnection

    @classmethod
    def get_queryset(cls, queryset, info) -> Any:
        if issubclass(type(queryset), QuerySet):
            return queryset.visible_to_user(info.context.user)
        elif "RelatedManager" in str(type(queryset)):
            # https://stackoverflow.com/questions/11320702/import-relatedmanager-from-django-db-models-fields-related
            return queryset.all().visible_to_user(info.context.user)
        else:
            return queryset


# Explicit Connection class for ConversationType to use in relay.ConnectionField
class ConversationConnection(CountableConnection):
    """Connection class for ConversationType used in searchConversations query."""

    class Meta:
        node = ConversationType


# ==============================================================================
# MODERATION TYPES
# ==============================================================================


class ModerationActionType(DjangoObjectType):
    """GraphQL type for ModerationAction audit records."""

    class Meta:
        model = ModerationAction
        interfaces = (relay.Node,)
        fields = [
            "id",
            "conversation",
            "message",
            "action_type",
            "moderator",
            "reason",
            "created",
            "modified",
        ]

    # Additional computed fields
    corpus_id = graphene.ID(description="Corpus ID if action is on a corpus thread")
    is_automated = graphene.Boolean(description="Whether this was an automated action")
    can_rollback = graphene.Boolean(
        description="Whether this action can be rolled back"
    )

    def resolve_corpus_id(self, info) -> Any:
        """Get corpus ID from conversation if linked."""
        if self.conversation and self.conversation.chat_with_corpus:
            return to_global_id("CorpusType", self.conversation.chat_with_corpus.pk)
        return None

    def resolve_is_automated(self, info) -> Any:
        """Check if this was an automated (agent) action - no human moderator."""
        return self.moderator is None

    def resolve_can_rollback(self, info) -> Any:
        """Check if this action can be rolled back."""
        rollback_types = {
            "delete_message",
            "delete_thread",
            "lock_thread",
            "pin_thread",
        }
        return self.action_type in rollback_types


class ModerationMetricsType(graphene.ObjectType):
    """Aggregated moderation metrics for monitoring."""

    total_actions = graphene.Int()
    automated_actions = graphene.Int()
    manual_actions = graphene.Int()
    actions_by_type = GenericScalar()  # Dict[action_type, count]
    hourly_action_rate = graphene.Float()
    is_above_threshold = graphene.Boolean()
    threshold_exceeded_types = graphene.List(graphene.String)
    time_range_hours = graphene.Int()
    start_time = graphene.DateTime()
    end_time = graphene.DateTime()
