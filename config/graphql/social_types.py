"""GraphQL type definitions for badge, leaderboard, community, notification, and search types."""

from typing import Any

import graphene
from graphene import relay
from graphene_django import DjangoObjectType

from config.graphql.annotation_types import AnnotationType
from config.graphql.base import CountableConnection
from config.graphql.permissioning.permission_annotator.mixins import (
    AnnotatePermissionsForReadMixin,
)
from config.graphql.user_types import UserType
from opencontractserver.badges.models import Badge, UserBadge
from opencontractserver.conversations.models import ChatMessage, Conversation
from opencontractserver.notifications.models import Notification


# ---------------- Badge System Types ----------------
class BadgeType(AnnotatePermissionsForReadMixin, DjangoObjectType):
    """GraphQL type for badges."""

    class Meta:
        model = Badge
        interfaces = [relay.Node]
        connection_class = CountableConnection
        fields = (
            "id",
            "name",
            "description",
            "icon",
            "badge_type",
            "color",
            "corpus",
            "is_auto_awarded",
            "criteria_config",
            "creator",
            "is_public",
            "created",
            "modified",
        )


class UserBadgeType(AnnotatePermissionsForReadMixin, DjangoObjectType):
    """GraphQL type for user badge awards."""

    class Meta:
        model = UserBadge
        interfaces = [relay.Node]
        connection_class = CountableConnection
        fields = (
            "id",
            "user",
            "badge",
            "awarded_at",
            "awarded_by",
            "corpus",
        )


class CriteriaFieldType(graphene.ObjectType):
    """GraphQL type for criteria field definition from the registry."""

    name = graphene.String(
        required=True, description="Field identifier used in criteria_config JSON"
    )
    label = graphene.String(
        required=True, description="Human-readable label for UI display"
    )
    field_type = graphene.String(
        required=True,
        description="Field data type: 'number', 'text', or 'boolean'",
    )
    required = graphene.Boolean(
        required=True, description="Whether this field must be present in configuration"
    )
    description = graphene.String(
        description="Help text explaining the field's purpose"
    )
    min_value = graphene.Int(
        description="Minimum allowed value (for number fields only)"
    )
    max_value = graphene.Int(
        description="Maximum allowed value (for number fields only)"
    )
    allowed_values = graphene.List(
        graphene.String,
        description="List of allowed values (for enum-like text fields)",
    )


class CriteriaTypeDefinitionType(graphene.ObjectType):
    """GraphQL type for criteria type definition from the registry."""

    type_id = graphene.String(
        required=True, description="Unique identifier for this criteria type"
    )
    name = graphene.String(required=True, description="Display name for UI")
    description = graphene.String(
        required=True, description="Explanation of what this criteria checks"
    )
    scope = graphene.String(
        required=True,
        description="Where this criteria can be used: 'global', 'corpus', or 'both'",
    )
    fields = graphene.List(
        graphene.NonNull(CriteriaFieldType),
        required=True,
        description="Configuration fields required for this criteria type",
    )
    implemented = graphene.Boolean(
        required=True, description="Whether the evaluation logic is implemented"
    )


class NotificationType(DjangoObjectType):
    """GraphQL type for notifications."""

    class Meta:
        model = Notification
        interfaces = [relay.Node]
        connection_class = CountableConnection
        fields = (
            "id",
            "recipient",
            "notification_type",
            "message",
            "conversation",
            "actor",
            "is_read",
            "created_at",
            "modified",
            "data",
        )
        filter_fields = {
            "is_read": ["exact"],
            "notification_type": ["exact"],
            "created_at": ["lte", "gte"],
        }

    def resolve_message(self, info) -> Any:
        """
        Resolve message field with permission check.
        Returns None if user doesn't have permission to view the message.
        """
        if not self.message:
            return None

        user = info.context.user if hasattr(info.context, "user") else None
        if not user or not user.is_authenticated:
            return None

        # Check if user can access this message via visible_to_user
        accessible_messages = ChatMessage.objects.visible_to_user(user).filter(
            id=self.message.id
        )

        if accessible_messages.exists():
            return self.message
        return None

    def resolve_conversation(self, info) -> Any:
        """
        Resolve conversation field with permission check.
        Returns None if user doesn't have permission to view the conversation.
        """
        if not self.conversation:
            return None

        user = info.context.user if hasattr(info.context, "user") else None
        if not user or not user.is_authenticated:
            return None

        # Check if user can access this conversation via visible_to_user
        accessible_conversations = Conversation.objects.visible_to_user(user).filter(
            id=self.conversation.id
        )

        if accessible_conversations.exists():
            return self.conversation
        return None

    def resolve_data(self, info) -> Any:
        """
        Resolve data field. The data is stored as JSON and returned as-is.
        Frontend must handle HTML escaping to prevent XSS.

        Note: Content previews in data field come from message.content which is
        user-generated. Frontend MUST escape this content before rendering.
        """
        # Data field is already JSON - no server-side sanitization needed
        # as GraphQL's GenericScalar handles JSON serialization safely.
        # XSS protection must be handled on frontend via proper escaping.
        return self.data


# ==============================================================================
# LEADERBOARD TYPES (Issue #613 - Leaderboard and Community Stats Dashboard)
# ==============================================================================


class LeaderboardMetricEnum(graphene.Enum):
    """
    Enum for different leaderboard metrics.

    Issue: #613 - Create leaderboard and community stats dashboard
    Epic: #572 - Social Features Epic
    """

    BADGES = "badges"
    MESSAGES = "messages"
    THREADS = "threads"
    ANNOTATIONS = "annotations"
    REPUTATION = "reputation"


class LeaderboardScopeEnum(graphene.Enum):
    """
    Enum for leaderboard scope (time period or corpus).

    Issue: #613 - Create leaderboard and community stats dashboard
    """

    ALL_TIME = "all_time"
    MONTHLY = "monthly"
    WEEKLY = "weekly"


class LeaderboardEntryType(graphene.ObjectType):
    """
    Represents a single entry in the leaderboard.

    Issue: #613 - Create leaderboard and community stats dashboard
    Epic: #572 - Social Features Epic
    """

    user = graphene.Field(UserType, description="The user in this leaderboard entry")
    rank = graphene.Int(description="User's rank in the leaderboard (1-indexed)")
    score = graphene.Int(description="User's score for this metric")

    # Optional detailed breakdown
    badge_count = graphene.Int(description="Total badges earned by user")
    message_count = graphene.Int(description="Total messages posted by user")
    thread_count = graphene.Int(description="Total threads created by user")
    annotation_count = graphene.Int(description="Total annotations created by user")
    reputation = graphene.Int(description="User's reputation score")

    # Rising star indicator (for users with recent high activity)
    is_rising_star = graphene.Boolean(
        description="True if user has shown significant recent activity"
    )


class LeaderboardType(graphene.ObjectType):
    """
    Complete leaderboard with entries and metadata.

    Issue: #613 - Create leaderboard and community stats dashboard
    Epic: #572 - Social Features Epic
    """

    metric = graphene.Field(
        LeaderboardMetricEnum, description="The metric this leaderboard is sorted by"
    )
    scope = graphene.Field(
        LeaderboardScopeEnum, description="The time period for this leaderboard"
    )
    corpus_id = graphene.ID(description="If corpus-specific leaderboard, the corpus ID")
    total_users = graphene.Int(description="Total number of users in leaderboard")
    entries = graphene.List(
        LeaderboardEntryType, description="Leaderboard entries in rank order"
    )
    current_user_rank = graphene.Int(
        description="Current user's rank in this leaderboard (null if not ranked)"
    )


class BadgeDistributionType(graphene.ObjectType):
    """
    Statistics about badge distribution across users.

    Issue: #613 - Create leaderboard and community stats dashboard
    Epic: #572 - Social Features Epic
    """

    badge = graphene.Field(BadgeType, description="The badge")
    award_count = graphene.Int(
        description="Number of times this badge has been awarded"
    )
    unique_recipients = graphene.Int(
        description="Number of unique users who have earned this badge"
    )


class CommunityStatsType(graphene.ObjectType):
    """
    Overall community engagement statistics.

    Issue: #613 - Create leaderboard and community stats dashboard
    Epic: #572 - Social Features Epic
    """

    total_users = graphene.Int(description="Total number of active users")
    total_messages = graphene.Int(description="Total messages posted")
    total_threads = graphene.Int(description="Total threads created")
    total_annotations = graphene.Int(description="Total annotations created")
    total_badges_awarded = graphene.Int(description="Total badge awards")
    badge_distribution = graphene.List(
        BadgeDistributionType, description="Badge distribution across users"
    )

    # Time-based metrics
    messages_this_week = graphene.Int(description="Messages posted in last 7 days")
    messages_this_month = graphene.Int(description="Messages posted in last 30 days")
    active_users_this_week = graphene.Int(description="Users who posted in last 7 days")
    active_users_this_month = graphene.Int(
        description="Users who posted in last 30 days"
    )


# ---------------- Semantic Search Types ----------------
class BlockContextType(graphene.ObjectType):
    """The smallest enclosing ``OC_SUBTREE_GROUP`` block for a vector hit.

    Lets clients deep-link directly to the materialised subtree relationship
    (``Relationship.id``) instead of recursively walking ``parent_id`` —
    used by the document viewer's "jump to surfaced block" affordance.
    """

    relationship_id = graphene.ID(
        required=True,
        description=(
            "Database PK of the OC_SUBTREE_GROUP relationship. NOTE: this "
            "is the raw Django PK (matching ``Relationship.id``), NOT a "
            "global Relay ID — frontend deep-links pass it through directly."
        ),
    )
    source_annotation_id = graphene.ID(
        required=True,
        description=(
            "PK of the ancestor annotation that anchors this block. Useful "
            "for highlighting the block root in the document viewer."
        ),
    )
    source_text = graphene.String(
        required=True,
        description=(
            "Raw text of the ancestor annotation. May be empty for "
            "image-only structural rows; clients should treat empty as "
            "valid rather than missing."
        ),
    )
    target_annotation_ids = graphene.List(
        graphene.NonNull(graphene.ID),
        required=True,
        description=(
            "PKs of every annotation transitively under the block source — "
            "i.e. the descendants the document viewer should also "
            "highlight when jumping to this block."
        ),
    )
    block_text = graphene.String(
        required=True,
        description=(
            "Source + targets concatenated newline-separated, capped at "
            "``SUBTREE_GROUP_BLOCK_TEXT_MAX_CHARS`` characters. Safe to "
            "render directly; no further truncation needed."
        ),
    )


class SemanticSearchResultType(graphene.ObjectType):
    """
    Result type for semantic (vector) search across annotations.

    Returns annotation matches with their similarity scores, enabling
    relevance-ranked search results from the global embeddings.

    PERMISSION MODEL:
    - Uses Document.objects.visible_to_user() for document access control
    - Structural annotations visible if document is accessible
    - Non-structural annotations visible if public OR owned by user
    """

    annotation = graphene.Field(
        AnnotationType,
        required=True,
        description="The matched annotation",
    )
    similarity_score = graphene.Float(
        required=True,
        description="Similarity score (0.0-1.0, higher is more similar)",
    )
    document = graphene.Field(
        lambda: _get_document_type(),
        description="The document containing this annotation (for convenience)",
    )
    corpus = graphene.Field(
        lambda: _get_corpus_type(),
        description="The corpus containing this annotation, if any",
    )
    block_context = graphene.Field(
        BlockContextType,
        description=(
            "Smallest enclosing OC_SUBTREE_GROUP subtree for this hit, "
            "or null when the annotation has no materialised containing "
            "block (root structural rows, legacy documents)."
        ),
    )

    def resolve_document(self, info) -> Any:
        """Resolve the document from the annotation."""
        if self.annotation and self.annotation.document:
            return self.annotation.document
        return None

    def resolve_corpus(self, info) -> Any:
        """Resolve the corpus from the annotation."""
        if self.annotation:
            return self.annotation.corpus
        return None


class SemanticSearchRelationshipResultType(graphene.ObjectType):
    """Semantic search hit where the matched object is a *Relationship*.

    Surfaces ``OC_SUBTREE_GROUP`` rows (or, in the future, any embedded
    relationship type) ranked by vector similarity. The doc viewer uses
    ``source_annotation_id`` + ``target_annotation_ids`` to scroll-and-select
    the whole block in a single navigation, mirroring the existing
    ``RelationGroup`` selection flow.

    ID convention
    -------------
    ``relationship_id``, ``source_annotation_id``, ``target_annotation_ids``,
    ``document_id``, and ``corpus_id`` are ALL raw Django PKs (not Relay
    global IDs). The frontend deep-link path consumes them directly without
    ``from_global_id``. Do NOT feed these values into resolvers that expect
    a Relay global ID (e.g. ``node(id: $documentId)``) — they will silently
    fail. Use the corresponding Relay-encoded type if you need that contract.
    """

    relationship_id = graphene.ID(
        required=True,
        description=(
            "Database PK of the Relationship. NOTE: this is the raw Django "
            "PK (matching ``Relationship.id``), NOT a global Relay ID — "
            "frontend deep-links and selection setters pass it through "
            "directly without ``from_global_id``."
        ),
    )
    similarity_score = graphene.Float(
        required=True,
        description="Cosine similarity (0.0-1.0, higher is more similar).",
    )
    label = graphene.String(
        description=(
            "Relationship label text (e.g. ``OC_SUBTREE_GROUP``). Provided "
            "so callers can filter or branch on the relationship kind "
            "without a follow-up fetch."
        ),
    )
    source_annotation_id = graphene.ID(
        description=(
            "PK of the (typically single) source annotation — the block's "
            "root. Null only when the relationship has no source row, "
            "which the materialiser does not produce but defensive "
            "frontends should still handle."
        ),
    )
    target_annotation_ids = graphene.List(
        graphene.NonNull(graphene.ID),
        required=True,
        description="PKs of the relationship's target annotations.",
    )
    block_text = graphene.String(
        required=True,
        description=(
            "Source + targets concatenated newline-separated, capped at "
            "``SUBTREE_GROUP_BLOCK_TEXT_MAX_CHARS`` — the same string the "
            "embedder saw, suitable for snippet display."
        ),
    )
    document_id = graphene.ID(
        description=(
            "PK of the document this relationship is anchored to (or that "
            "shares the ``StructuralAnnotationSet`` for structural rows). "
            "Null when the relationship is global and not tied to any "
            "single document."
        ),
    )
    corpus_id = graphene.ID(
        description=(
            "PK of the corpus this relationship belongs to. Null for "
            "non-corpus relationships."
        ),
    )


def _get_document_type() -> Any:
    from config.graphql.document_types import DocumentType

    return DocumentType


def _get_corpus_type() -> Any:
    from config.graphql.corpus_types import CorpusType

    return CorpusType
