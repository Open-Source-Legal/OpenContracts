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

from opencontractserver.badges.models import Badge
from opencontractserver.badges.models import UserBadge
from opencontractserver.notifications.models import Notification


def _resolve_NotificationType_message(root, info, **kwargs):
    """PORT: config/graphql/social_types.py:149

    Port of NotificationType.resolve_message
    """
    raise NotImplementedError("_resolve_NotificationType_message not yet ported — see manifest")


def _resolve_NotificationType_conversation(root, info, **kwargs):
    """PORT: config/graphql/social_types.py:170

    Port of NotificationType.resolve_conversation
    """
    raise NotImplementedError("_resolve_NotificationType_conversation not yet ported — see manifest")


def _resolve_NotificationType_data(root, info, **kwargs):
    """PORT: config/graphql/social_types.py:191

    Port of NotificationType.resolve_data
    """
    raise NotImplementedError("_resolve_NotificationType_data not yet ported — see manifest")


@strawberry.type(name="NotificationType", description='GraphQL type for notifications.')
class NotificationType(Node):
    recipient: Annotated["UserType", strawberry.lazy("config.graphql_new.user_types")] = strawberry.field(name="recipient", description='User receiving this notification')
    @strawberry.field(name="notificationType", description='Type of notification')
    def notification_type(self, info: strawberry.Info) -> enums.NotificationsNotificationNotificationTypeChoices:
        return coerce_enum(enums.NotificationsNotificationNotificationTypeChoices, getattr(self, "notification_type", None))
    @strawberry.field(name="message", description='Related message if applicable')
    def message(self, info: strawberry.Info) -> Optional[Annotated["MessageType", strawberry.lazy("config.graphql_new.conversation_types")]]:
        kwargs = strip_unset({})
        return _resolve_NotificationType_message(self, info, **kwargs)
    @strawberry.field(name="conversation", description='Related conversation/thread if applicable')
    def conversation(self, info: strawberry.Info) -> Optional[Annotated["ConversationType", strawberry.lazy("config.graphql_new.conversation_types")]]:
        kwargs = strip_unset({})
        return _resolve_NotificationType_conversation(self, info, **kwargs)
    actor: Optional[Annotated["UserType", strawberry.lazy("config.graphql_new.user_types")]] = strawberry.field(name="actor", description='User who triggered this notification (if applicable)')
    is_read: bool = strawberry.field(name="isRead", description='Whether the notification has been read')
    created_at: datetime.datetime = strawberry.field(name="createdAt", description='When the notification was created')
    modified: datetime.datetime = strawberry.field(name="modified", description='When the notification was last modified')
    @strawberry.field(name="data", description='Additional context data for the notification (e.g., vote type, badge info)')
    def data(self, info: strawberry.Info) -> Optional[JSONString]:
        kwargs = strip_unset({})
        return _resolve_NotificationType_data(self, info, **kwargs)


register_type("NotificationType", NotificationType, model=Notification)


NotificationTypeConnection = make_connection_types(NotificationType, type_name="NotificationTypeConnection", countable=True, pdf_page_aware=False)


@strawberry.type(name="BadgeType", description='GraphQL type for badges.')
class BadgeType(Node):
    is_public: bool = strawberry.field(name="isPublic")
    creator: Annotated["UserType", strawberry.lazy("config.graphql_new.user_types")] = strawberry.field(name="creator")
    created: datetime.datetime = strawberry.field(name="created")
    modified: datetime.datetime = strawberry.field(name="modified")
    @strawberry.field(name="name", description='Unique name for the badge')
    def name(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "name", None))
    @strawberry.field(name="description", description='Description of what this badge represents or how to earn it')
    def description(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "description", None))
    @strawberry.field(name="icon", description="Icon identifier from lucide-react (e.g., 'Trophy', 'Star', 'Award')")
    def icon(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "icon", None))
    @strawberry.field(name="badgeType", description='Whether this badge is global or corpus-specific')
    def badge_type(self, info: strawberry.Info) -> enums.BadgesBadgeBadgeTypeChoices:
        return coerce_enum(enums.BadgesBadgeBadgeTypeChoices, getattr(self, "badge_type", None))
    @strawberry.field(name="color", description='Hex color code for badge display')
    def color(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "color", None))
    corpus: Optional[Annotated["CorpusType", strawberry.lazy("config.graphql_new.corpus_types")]] = strawberry.field(name="corpus", description='If badge_type is CORPUS, the corpus this badge belongs to')
    is_auto_awarded: bool = strawberry.field(name="isAutoAwarded", description='Whether this badge is automatically awarded based on criteria')
    criteria_config: Optional[JSONString] = strawberry.field(name="criteriaConfig", description="JSON configuration for auto-award criteria. Example: {'type': 'reputation_threshold', 'value': 100, 'scope': 'global'}")
    @strawberry.field(name="myPermissions")
    def my_permissions(self, info: strawberry.Info) -> Optional[GenericScalar]:
        return core_permissions.resolve_my_permissions(self, info)
    @strawberry.field(name="isPublished")
    def is_published(self, info: strawberry.Info) -> Optional[bool]:
        return core_permissions.resolve_is_published(self, info)
    @strawberry.field(name="objectSharedWith")
    def object_shared_with(self, info: strawberry.Info) -> Optional[GenericScalar]:
        return core_permissions.resolve_object_shared_with(self, info)


register_type("BadgeType", BadgeType, model=Badge)


BadgeTypeConnection = make_connection_types(BadgeType, type_name="BadgeTypeConnection", countable=True, pdf_page_aware=False)


@strawberry.type(name="UserBadgeType", description='GraphQL type for user badge awards.')
class UserBadgeType(Node):
    user: Annotated["UserType", strawberry.lazy("config.graphql_new.user_types")] = strawberry.field(name="user", description='User who received the badge')
    badge: "BadgeType" = strawberry.field(name="badge", description='Badge that was awarded')
    awarded_at: datetime.datetime = strawberry.field(name="awardedAt", description='When the badge was awarded')
    awarded_by: Optional[Annotated["UserType", strawberry.lazy("config.graphql_new.user_types")]] = strawberry.field(name="awardedBy", description='User who awarded the badge (null for auto-awards)')
    corpus: Optional[Annotated["CorpusType", strawberry.lazy("config.graphql_new.corpus_types")]] = strawberry.field(name="corpus", description='For corpus-specific badges, the context in which it was awarded')
    @strawberry.field(name="myPermissions")
    def my_permissions(self, info: strawberry.Info) -> Optional[GenericScalar]:
        return core_permissions.resolve_my_permissions(self, info)
    @strawberry.field(name="isPublished")
    def is_published(self, info: strawberry.Info) -> Optional[bool]:
        return core_permissions.resolve_is_published(self, info)
    @strawberry.field(name="objectSharedWith")
    def object_shared_with(self, info: strawberry.Info) -> Optional[GenericScalar]:
        return core_permissions.resolve_object_shared_with(self, info)


register_type("UserBadgeType", UserBadgeType, model=UserBadge)


UserBadgeTypeConnection = make_connection_types(UserBadgeType, type_name="UserBadgeTypeConnection", countable=True, pdf_page_aware=False)


@strawberry.type(name="CriteriaTypeDefinitionType", description='GraphQL type for criteria type definition from the registry.')
class CriteriaTypeDefinitionType:
    @strawberry.field(name="typeId", description='Unique identifier for this criteria type')
    def type_id(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "type_id", None))
    @strawberry.field(name="name", description='Display name for UI')
    def name(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "name", None))
    @strawberry.field(name="description", description='Explanation of what this criteria checks')
    def description(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "description", None))
    @strawberry.field(name="scope", description="Where this criteria can be used: 'global', 'corpus', or 'both'")
    def scope(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "scope", None))
    @strawberry.field(name="fields", description='Configuration fields required for this criteria type')
    def fields(self, info: strawberry.Info) -> list["CriteriaFieldType"]:
        return resolve_django_list(self, info, getattr(self, "fields"), "CriteriaFieldType")
    implemented: bool = strawberry.field(name="implemented", description='Whether the evaluation logic is implemented')


register_type("CriteriaTypeDefinitionType", CriteriaTypeDefinitionType, model=None)


@strawberry.type(name="CriteriaFieldType", description='GraphQL type for criteria field definition from the registry.')
class CriteriaFieldType:
    @strawberry.field(name="name", description='Field identifier used in criteria_config JSON')
    def name(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "name", None))
    @strawberry.field(name="label", description='Human-readable label for UI display')
    def label(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "label", None))
    @strawberry.field(name="fieldType", description="Field data type: 'number', 'text', or 'boolean'")
    def field_type(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "field_type", None))
    required: bool = strawberry.field(name="required", description='Whether this field must be present in configuration')
    @strawberry.field(name="description", description="Help text explaining the field's purpose")
    def description(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "description", None))
    min_value: Optional[int] = strawberry.field(name="minValue", description='Minimum allowed value (for number fields only)')
    max_value: Optional[int] = strawberry.field(name="maxValue", description='Maximum allowed value (for number fields only)')
    @strawberry.field(name="allowedValues", description='List of allowed values (for enum-like text fields)')
    def allowed_values(self, info: strawberry.Info) -> Optional[list[Optional[str]]]:
        return coerce_str(getattr(self, "allowed_values", None))


register_type("CriteriaFieldType", CriteriaFieldType, model=None)


@strawberry.type(name="LeaderboardType", description='Complete leaderboard with entries and metadata.\n\nIssue: #613 - Create leaderboard and community stats dashboard\nEpic: #572 - Social Features Epic')
class LeaderboardType:
    @strawberry.field(name="metric", description='The metric this leaderboard is sorted by')
    def metric(self, info: strawberry.Info) -> Optional[enums.LeaderboardMetricEnum]:
        return coerce_enum(enums.LeaderboardMetricEnum, getattr(self, "metric", None))
    @strawberry.field(name="scope", description='The time period for this leaderboard')
    def scope(self, info: strawberry.Info) -> Optional[enums.LeaderboardScopeEnum]:
        return coerce_enum(enums.LeaderboardScopeEnum, getattr(self, "scope", None))
    @strawberry.field(name="corpusId", description='If corpus-specific leaderboard, the corpus ID')
    def corpus_id(self, info: strawberry.Info) -> Optional[strawberry.ID]:
        return coerce_str(getattr(self, "corpus_id", None))
    total_users: Optional[int] = strawberry.field(name="totalUsers", description='Total number of users in leaderboard')
    @strawberry.field(name="entries", description='Leaderboard entries in rank order')
    def entries(self, info: strawberry.Info) -> Optional[list[Optional["LeaderboardEntryType"]]]:
        return resolve_django_list(self, info, getattr(self, "entries"), "LeaderboardEntryType")
    current_user_rank: Optional[int] = strawberry.field(name="currentUserRank", description="Current user's rank in this leaderboard (null if not ranked)")


register_type("LeaderboardType", LeaderboardType, model=None)


@strawberry.type(name="LeaderboardEntryType", description='Represents a single entry in the leaderboard.\n\nIssue: #613 - Create leaderboard and community stats dashboard\nEpic: #572 - Social Features Epic')
class LeaderboardEntryType:
    user: Optional[Annotated["UserType", strawberry.lazy("config.graphql_new.user_types")]] = strawberry.field(name="user", description='The user in this leaderboard entry')
    rank: Optional[int] = strawberry.field(name="rank", description="User's rank in the leaderboard (1-indexed)")
    score: Optional[int] = strawberry.field(name="score", description="User's score for this metric")
    badge_count: Optional[int] = strawberry.field(name="badgeCount", description='Total badges earned by user')
    message_count: Optional[int] = strawberry.field(name="messageCount", description='Total messages posted by user')
    thread_count: Optional[int] = strawberry.field(name="threadCount", description='Total threads created by user')
    annotation_count: Optional[int] = strawberry.field(name="annotationCount", description='Total annotations created by user')
    reputation: Optional[int] = strawberry.field(name="reputation", description="User's reputation score")
    is_rising_star: Optional[bool] = strawberry.field(name="isRisingStar", description='True if user has shown significant recent activity')


register_type("LeaderboardEntryType", LeaderboardEntryType, model=None)


@strawberry.type(name="CommunityStatsType", description='Overall community engagement statistics.\n\nIssue: #613 - Create leaderboard and community stats dashboard\nEpic: #572 - Social Features Epic')
class CommunityStatsType:
    total_users: Optional[int] = strawberry.field(name="totalUsers", description='Total number of active users')
    total_messages: Optional[int] = strawberry.field(name="totalMessages", description='Total messages posted')
    total_threads: Optional[int] = strawberry.field(name="totalThreads", description='Total threads created')
    total_annotations: Optional[int] = strawberry.field(name="totalAnnotations", description='Total annotations created')
    total_badges_awarded: Optional[int] = strawberry.field(name="totalBadgesAwarded", description='Total badge awards')
    @strawberry.field(name="badgeDistribution", description='Badge distribution across users')
    def badge_distribution(self, info: strawberry.Info) -> Optional[list[Optional["BadgeDistributionType"]]]:
        return resolve_django_list(self, info, getattr(self, "badge_distribution"), "BadgeDistributionType")
    messages_this_week: Optional[int] = strawberry.field(name="messagesThisWeek", description='Messages posted in last 7 days')
    messages_this_month: Optional[int] = strawberry.field(name="messagesThisMonth", description='Messages posted in last 30 days')
    active_users_this_week: Optional[int] = strawberry.field(name="activeUsersThisWeek", description='Users who posted in last 7 days')
    active_users_this_month: Optional[int] = strawberry.field(name="activeUsersThisMonth", description='Users who posted in last 30 days')


register_type("CommunityStatsType", CommunityStatsType, model=None)


@strawberry.type(name="BadgeDistributionType", description='Statistics about badge distribution across users.\n\nIssue: #613 - Create leaderboard and community stats dashboard\nEpic: #572 - Social Features Epic')
class BadgeDistributionType:
    badge: Optional["BadgeType"] = strawberry.field(name="badge", description='The badge')
    award_count: Optional[int] = strawberry.field(name="awardCount", description='Number of times this badge has been awarded')
    unique_recipients: Optional[int] = strawberry.field(name="uniqueRecipients", description='Number of unique users who have earned this badge')


register_type("BadgeDistributionType", BadgeDistributionType, model=None)


def _resolve_SemanticSearchResultType_document(root, info, **kwargs):
    """PORT: config/graphql/social_types.py:419

    Port of SemanticSearchResultType.resolve_document
    """
    raise NotImplementedError("_resolve_SemanticSearchResultType_document not yet ported — see manifest")


def _resolve_SemanticSearchResultType_corpus(root, info, **kwargs):
    """PORT: config/graphql/social_types.py:432

    Port of SemanticSearchResultType.resolve_corpus
    """
    raise NotImplementedError("_resolve_SemanticSearchResultType_corpus not yet ported — see manifest")


@strawberry.type(name="SemanticSearchResultType", description='Result type for semantic (vector) search across annotations.\n\nReturns annotation matches with their similarity scores, enabling\nrelevance-ranked search results from the global embeddings.\n\nPERMISSION MODEL:\n- Filters documents through the service layer (BaseService.filter_visible)\n- Structural annotations visible if document is accessible\n- Non-structural annotations visible if public OR owned by user')
class SemanticSearchResultType:
    annotation: Annotated["AnnotationType", strawberry.lazy("config.graphql_new.annotation_types")] = strawberry.field(name="annotation", description='The matched annotation')
    similarity_score: float = strawberry.field(name="similarityScore", description='Similarity score (0.0-1.0, higher is more similar)')
    @strawberry.field(name="document", description='The document containing this annotation (for convenience)')
    def document(self, info: strawberry.Info) -> Optional[Annotated["DocumentType", strawberry.lazy("config.graphql_new.document_types")]]:
        kwargs = strip_unset({})
        return _resolve_SemanticSearchResultType_document(self, info, **kwargs)
    @strawberry.field(name="corpus", description='The corpus containing this annotation, if any')
    def corpus(self, info: strawberry.Info) -> Optional[Annotated["CorpusType", strawberry.lazy("config.graphql_new.corpus_types")]]:
        kwargs = strip_unset({})
        return _resolve_SemanticSearchResultType_corpus(self, info, **kwargs)
    block_context: Optional["BlockContextType"] = strawberry.field(name="blockContext", description='Smallest enclosing OC_SUBTREE_GROUP subtree for this hit, or null when the annotation has no materialised containing block (root structural rows, legacy documents).')


register_type("SemanticSearchResultType", SemanticSearchResultType, model=None)


@strawberry.type(name="BlockContextType", description='The smallest enclosing ``OC_SUBTREE_GROUP`` block for a vector hit.\n\nLets clients deep-link directly to the materialised subtree relationship\n(``Relationship.id``) instead of recursively walking ``parent_id`` —\nused by the document viewer\'s "jump to surfaced block" affordance.')
class BlockContextType:
    @strawberry.field(name="relationshipId", description='Database PK of the OC_SUBTREE_GROUP relationship. NOTE: this is the raw Django PK (matching ``Relationship.id``), NOT a global Relay ID — frontend deep-links pass it through directly.')
    def relationship_id(self, info: strawberry.Info) -> strawberry.ID:
        return coerce_str(getattr(self, "relationship_id", None))
    @strawberry.field(name="sourceAnnotationId", description='PK of the ancestor annotation that anchors this block. Useful for highlighting the block root in the document viewer.')
    def source_annotation_id(self, info: strawberry.Info) -> strawberry.ID:
        return coerce_str(getattr(self, "source_annotation_id", None))
    @strawberry.field(name="sourceText", description='Raw text of the ancestor annotation. May be empty for image-only structural rows; clients should treat empty as valid rather than missing.')
    def source_text(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "source_text", None))
    @strawberry.field(name="targetAnnotationIds", description='PKs of every annotation transitively under the block source — i.e. the descendants the document viewer should also highlight when jumping to this block.')
    def target_annotation_ids(self, info: strawberry.Info) -> list[strawberry.ID]:
        return resolve_django_list(self, info, getattr(self, "target_annotation_ids"), "ID")
    @strawberry.field(name="blockText", description='Source + targets concatenated newline-separated, capped at ``SUBTREE_GROUP_BLOCK_TEXT_MAX_CHARS`` characters. Safe to render directly; no further truncation needed.')
    def block_text(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "block_text", None))


register_type("BlockContextType", BlockContextType, model=None)


@strawberry.type(name="SemanticSearchRelationshipResultType", description='Semantic search hit where the matched object is a *Relationship*.\n\nSurfaces ``OC_SUBTREE_GROUP`` rows (or, in the future, any embedded\nrelationship type) ranked by vector similarity. The doc viewer uses\n``source_annotation_id`` + ``target_annotation_ids`` to scroll-and-select\nthe whole block in a single navigation, mirroring the existing\n``RelationGroup`` selection flow.\n\nID convention\n-------------\n``relationship_id``, ``source_annotation_id``, ``target_annotation_ids``,\n``document_id``, and ``corpus_id`` are ALL raw Django PKs (not Relay\nglobal IDs). The frontend deep-link path consumes them directly without\n``from_global_id``. Do NOT feed these values into resolvers that expect\na Relay global ID (e.g. ``node(id: $documentId)``) — they will silently\nfail. Use the corresponding Relay-encoded type if you need that contract.')
class SemanticSearchRelationshipResultType:
    @strawberry.field(name="relationshipId", description='Database PK of the Relationship. NOTE: this is the raw Django PK (matching ``Relationship.id``), NOT a global Relay ID — frontend deep-links and selection setters pass it through directly without ``from_global_id``.')
    def relationship_id(self, info: strawberry.Info) -> strawberry.ID:
        return coerce_str(getattr(self, "relationship_id", None))
    similarity_score: float = strawberry.field(name="similarityScore", description='Cosine similarity (0.0-1.0, higher is more similar).')
    @strawberry.field(name="label", description='Relationship label text (e.g. ``OC_SUBTREE_GROUP``). Provided so callers can filter or branch on the relationship kind without a follow-up fetch.')
    def label(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "label", None))
    @strawberry.field(name="sourceAnnotationId", description="PK of the (typically single) source annotation — the block's root. Null only when the relationship has no source row, which the materialiser does not produce but defensive frontends should still handle.")
    def source_annotation_id(self, info: strawberry.Info) -> Optional[strawberry.ID]:
        return coerce_str(getattr(self, "source_annotation_id", None))
    @strawberry.field(name="targetAnnotationIds", description="PKs of the relationship's target annotations.")
    def target_annotation_ids(self, info: strawberry.Info) -> list[strawberry.ID]:
        return resolve_django_list(self, info, getattr(self, "target_annotation_ids"), "ID")
    @strawberry.field(name="blockText", description='Source + targets concatenated newline-separated, capped at ``SUBTREE_GROUP_BLOCK_TEXT_MAX_CHARS`` — the same string the embedder saw, suitable for snippet display.')
    def block_text(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "block_text", None))
    @strawberry.field(name="documentId", description='PK of the document this relationship is anchored to (or that shares the ``StructuralAnnotationSet`` for structural rows). Null when the relationship is global and not tied to any single document.')
    def document_id(self, info: strawberry.Info) -> Optional[strawberry.ID]:
        return coerce_str(getattr(self, "document_id", None))
    @strawberry.field(name="corpusId", description='PK of the corpus this relationship belongs to. Null for non-corpus relationships.')
    def corpus_id(self, info: strawberry.Info) -> Optional[strawberry.ID]:
        return coerce_str(getattr(self, "corpus_id", None))


register_type("SemanticSearchRelationshipResultType", SemanticSearchRelationshipResultType, model=None)

