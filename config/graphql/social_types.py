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
from typing import Annotated

import strawberry

from config.graphql import enums
from config.graphql._util import coerce_enum, coerce_str, strip_unset
from config.graphql.core import permissions as core_permissions
from config.graphql.core.relay import (
    Node,
    make_connection_types,
    register_type,
    resolve_visible_fk,
)
from config.graphql.core.scalars import GenericScalar, JSONString
from opencontractserver.badges.models import Badge, UserBadge
from opencontractserver.conversations.models import ChatMessage, Conversation
from opencontractserver.notifications.models import Notification
from opencontractserver.shared.services.base import BaseService


def _resolve_NotificationType_message(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/social_types.py:149

    Port of NotificationType.resolve_message

    Resolve message field with permission check.
    Returns None if user doesn't have permission to view the message.
    """
    if not root.message:
        return None

    user = info.context.user if hasattr(info.context, "user") else None
    if not user or not user.is_authenticated:
        return None

    # Check via the service layer whether this user can see the message.
    accessible_messages = BaseService.filter_visible(
        ChatMessage, user, request=info.context
    ).filter(id=root.message.id)

    if accessible_messages.exists():
        return root.message
    return None


def _resolve_NotificationType_conversation(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/social_types.py:170

    Port of NotificationType.resolve_conversation

    Resolve conversation field with permission check.
    Returns None if user doesn't have permission to view the conversation.
    """
    if not root.conversation:
        return None

    user = info.context.user if hasattr(info.context, "user") else None
    if not user or not user.is_authenticated:
        return None

    # Check via the service layer whether this user can see the conversation.
    accessible_conversations = BaseService.filter_visible(
        Conversation, user, request=info.context
    ).filter(id=root.conversation.id)

    if accessible_conversations.exists():
        return root.conversation
    return None


def _resolve_NotificationType_data(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/social_types.py:191

    Port of NotificationType.resolve_data

    Resolve data field. The data is stored as JSON and returned as-is.
    Frontend must handle HTML escaping to prevent XSS.

    Note: Content previews in data field come from message.content which is
    user-generated. Frontend MUST escape this content before rendering.
    """
    # Data field is already JSON - no server-side sanitization needed
    # as GraphQL's GenericScalar handles JSON serialization safely.
    # XSS protection must be handled on frontend via proper escaping.
    return root.data


@strawberry.type(name="NotificationType", description="GraphQL type for notifications.")
class NotificationType(Node):
    recipient: Annotated[UserType, strawberry.lazy("config.graphql.user_types")] = (
        strawberry.field(
            name="recipient",
            description="User receiving this notification",
            default=None,
        )
    )

    @strawberry.field(name="notificationType", description="Type of notification")
    def notification_type(
        self, info: strawberry.Info
    ) -> enums.NotificationsNotificationNotificationTypeChoices:
        return coerce_enum(
            enums.NotificationsNotificationNotificationTypeChoices,
            getattr(self, "notification_type", None),
        )

    @strawberry.field(name="message", description="Related message if applicable")
    def message(
        self, info: strawberry.Info
    ) -> None | (
        Annotated[MessageType, strawberry.lazy("config.graphql.conversation_types")]
    ):
        kwargs = strip_unset({})
        return _resolve_NotificationType_message(self, info, **kwargs)

    @strawberry.field(
        name="conversation", description="Related conversation/thread if applicable"
    )
    def conversation(
        self, info: strawberry.Info
    ) -> None | (
        Annotated[
            ConversationType, strawberry.lazy("config.graphql.conversation_types")
        ]
    ):
        kwargs = strip_unset({})
        return _resolve_NotificationType_conversation(self, info, **kwargs)

    actor: None | (
        Annotated[UserType, strawberry.lazy("config.graphql.user_types")]
    ) = strawberry.field(
        name="actor",
        description="User who triggered this notification (if applicable)",
        default=None,
    )
    is_read: bool = strawberry.field(
        name="isRead",
        description="Whether the notification has been read",
        default=None,
    )
    created_at: datetime.datetime = strawberry.field(
        name="createdAt", description="When the notification was created", default=None
    )
    modified: datetime.datetime = strawberry.field(
        name="modified",
        description="When the notification was last modified",
        default=None,
    )

    @strawberry.field(
        name="data",
        description="Additional context data for the notification (e.g., vote type, badge info)",
    )
    def data(self, info: strawberry.Info) -> JSONString | None:
        kwargs = strip_unset({})
        return _resolve_NotificationType_data(self, info, **kwargs)


def _get_node_NotificationType(info, pk):
    """PORT: config.graphql.social_queries.SocialQueryMixin.resolve_notification

    Port of the graphene ``resolve_notification`` override on the Query
    mixin (graphene's ``relay.Node.Field(NotificationType)`` was shadowed
    by a ``resolve_notification`` method): notifications use a simple
    ownership model (``recipient=user``), NOT the guardian permission
    manager, so the default ``BaseService.get_or_none`` node path cannot
    be used. Returns consistent error to prevent IDOR enumeration.
    """
    from graphql import GraphQLError

    from opencontractserver.notifications.services import NotificationService

    notification = NotificationService.get_for_user(
        info.context.user, int(pk), request=info.context
    )
    if notification is None:
        # Same error whether notification doesn't exist or belongs to
        # another user (IDOR protection).
        raise GraphQLError("Notification not found")
    return notification


register_type(
    "NotificationType",
    NotificationType,
    model=Notification,
    get_node=_get_node_NotificationType,
)


NotificationTypeConnection = make_connection_types(
    NotificationType,
    type_name="NotificationTypeConnection",
    countable=True,
    pdf_page_aware=False,
)


@strawberry.type(name="BadgeType", description="GraphQL type for badges.")
class BadgeType(Node):
    is_public: bool = strawberry.field(name="isPublic", default=None)
    creator: Annotated[UserType, strawberry.lazy("config.graphql.user_types")] = (
        strawberry.field(name="creator", default=None)
    )
    created: datetime.datetime = strawberry.field(name="created", default=None)
    modified: datetime.datetime = strawberry.field(name="modified", default=None)

    @strawberry.field(name="name", description="Unique name for the badge")
    def name(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "name", None))

    @strawberry.field(
        name="description",
        description="Description of what this badge represents or how to earn it",
    )
    def description(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "description", None))

    @strawberry.field(
        name="icon",
        description="Icon identifier from lucide-react (e.g., 'Trophy', 'Star', 'Award')",
    )
    def icon(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "icon", None))

    @strawberry.field(
        name="badgeType", description="Whether this badge is global or corpus-specific"
    )
    def badge_type(self, info: strawberry.Info) -> enums.BadgesBadgeBadgeTypeChoices:
        return coerce_enum(
            enums.BadgesBadgeBadgeTypeChoices, getattr(self, "badge_type", None)
        )

    @strawberry.field(name="color", description="Hex color code for badge display")
    def color(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "color", None))

    @strawberry.field(
        name="corpus",
        description="If badge_type is CORPUS, the corpus this badge belongs to",
    )
    def corpus(
        self, info: strawberry.Info
    ) -> None | (Annotated[CorpusType, strawberry.lazy("config.graphql.corpus_types")]):
        return resolve_visible_fk(self, info, "corpus_id", "CorpusType")

    is_auto_awarded: bool = strawberry.field(
        name="isAutoAwarded",
        description="Whether this badge is automatically awarded based on criteria",
        default=None,
    )
    criteria_config: JSONString | None = strawberry.field(
        name="criteriaConfig",
        description="JSON configuration for auto-award criteria. Example: {'type': 'reputation_threshold', 'value': 100, 'scope': 'global'}",
        default=None,
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


def _get_node_BadgeType(info, pk):
    """Permission-aware node resolution for the singular ``badge(id:)`` field
    (IDOR guard). Mirrors the graphene ``BaseService.filter_visible(Badge,
    ...).get(id=pk)`` resolver (``get_or_none`` = filter_visible + get-or-None);
    without it ``get_node_from_global_id`` would fall back to an UNFILTERED
    ``.get(pk=pk)``.
    """
    if pk is None:
        return None
    return BaseService.get_or_none(Badge, pk, info.context.user, request=info.context)


register_type("BadgeType", BadgeType, model=Badge, get_node=_get_node_BadgeType)


BadgeTypeConnection = make_connection_types(
    BadgeType, type_name="BadgeTypeConnection", countable=True, pdf_page_aware=False
)


@strawberry.type(
    name="UserBadgeType", description="GraphQL type for user badge awards."
)
class UserBadgeType(Node):
    user: Annotated[UserType, strawberry.lazy("config.graphql.user_types")] = (
        strawberry.field(
            name="user", description="User who received the badge", default=None
        )
    )
    badge: BadgeType = strawberry.field(
        name="badge", description="Badge that was awarded", default=None
    )
    awarded_at: datetime.datetime = strawberry.field(
        name="awardedAt", description="When the badge was awarded", default=None
    )
    awarded_by: None | (
        Annotated[UserType, strawberry.lazy("config.graphql.user_types")]
    ) = strawberry.field(
        name="awardedBy",
        description="User who awarded the badge (null for auto-awards)",
        default=None,
    )

    @strawberry.field(
        name="corpus",
        description="For corpus-specific badges, the context in which it was awarded",
    )
    def corpus(
        self, info: strawberry.Info
    ) -> None | (Annotated[CorpusType, strawberry.lazy("config.graphql.corpus_types")]):
        return resolve_visible_fk(self, info, "corpus_id", "CorpusType")

    @strawberry.field(name="myPermissions")
    def my_permissions(self, info: strawberry.Info) -> GenericScalar | None:
        return core_permissions.resolve_my_permissions(self, info)

    @strawberry.field(name="isPublished")
    def is_published(self, info: strawberry.Info) -> bool | None:
        return core_permissions.resolve_is_published(self, info)

    @strawberry.field(name="objectSharedWith")
    def object_shared_with(self, info: strawberry.Info) -> GenericScalar | None:
        return core_permissions.resolve_object_shared_with(self, info)


def _get_node_UserBadgeType(info, pk):
    """PORT: config.graphql.social_queries.SocialQueryMixin.resolve_user_badge

    Port of the graphene ``resolve_user_badge`` override on the Query mixin
    (graphene's ``relay.Node.Field(UserBadgeType)`` was shadowed by a
    ``resolve_user_badge`` method).

    Resolve a single user badge by ID with visibility check and IDOR
    protection.

    SECURITY: Returns same error whether badge doesn't exist or user lacks
    permission. This prevents enumeration attacks.
    """
    from graphql import GraphQLError

    from opencontractserver.badges.services import BadgeService

    has_permission, user_badge = BadgeService.check_user_badge_visibility(
        info.context.user, int(pk), request=info.context
    )

    if not has_permission:
        # Same error whether doesn't exist or no permission (IDOR protection)
        raise GraphQLError("User badge not found")

    return user_badge


register_type(
    "UserBadgeType",
    UserBadgeType,
    model=UserBadge,
    get_node=_get_node_UserBadgeType,
)


UserBadgeTypeConnection = make_connection_types(
    UserBadgeType,
    type_name="UserBadgeTypeConnection",
    countable=True,
    pdf_page_aware=False,
)


@strawberry.type(
    name="CriteriaTypeDefinitionType",
    description="GraphQL type for criteria type definition from the registry.",
)
class CriteriaTypeDefinitionType:
    type_id: str = strawberry.field(
        name="typeId",
        description="Unique identifier for this criteria type",
        default=None,
    )
    name: str = strawberry.field(
        name="name", description="Display name for UI", default=None
    )
    description: str = strawberry.field(
        name="description",
        description="Explanation of what this criteria checks",
        default=None,
    )
    scope: str = strawberry.field(
        name="scope",
        description="Where this criteria can be used: 'global', 'corpus', or 'both'",
        default=None,
    )
    fields: list[CriteriaFieldType] = strawberry.field(
        name="fields",
        description="Configuration fields required for this criteria type",
        default=None,
    )
    implemented: bool = strawberry.field(
        name="implemented",
        description="Whether the evaluation logic is implemented",
        default=None,
    )


register_type("CriteriaTypeDefinitionType", CriteriaTypeDefinitionType, model=None)


@strawberry.type(
    name="CriteriaFieldType",
    description="GraphQL type for criteria field definition from the registry.",
)
class CriteriaFieldType:
    name: str = strawberry.field(
        name="name",
        description="Field identifier used in criteria_config JSON",
        default=None,
    )
    label: str = strawberry.field(
        name="label", description="Human-readable label for UI display", default=None
    )
    field_type: str = strawberry.field(
        name="fieldType",
        description="Field data type: 'number', 'text', or 'boolean'",
        default=None,
    )
    required: bool = strawberry.field(
        name="required",
        description="Whether this field must be present in configuration",
        default=None,
    )
    description: str | None = strawberry.field(
        name="description",
        description="Help text explaining the field's purpose",
        default=None,
    )
    min_value: int | None = strawberry.field(
        name="minValue",
        description="Minimum allowed value (for number fields only)",
        default=None,
    )
    max_value: int | None = strawberry.field(
        name="maxValue",
        description="Maximum allowed value (for number fields only)",
        default=None,
    )
    allowed_values: list[str | None] | None = strawberry.field(
        name="allowedValues",
        description="List of allowed values (for enum-like text fields)",
        default=None,
    )


register_type("CriteriaFieldType", CriteriaFieldType, model=None)


@strawberry.type(
    name="LeaderboardType",
    description="Complete leaderboard with entries and metadata.\n\nIssue: #613 - Create leaderboard and community stats dashboard\nEpic: #572 - Social Features Epic",
)
class LeaderboardType:
    metric: enums.LeaderboardMetricEnum | None = strawberry.field(
        name="metric",
        description="The metric this leaderboard is sorted by",
        default=None,
    )
    scope: enums.LeaderboardScopeEnum | None = strawberry.field(
        name="scope", description="The time period for this leaderboard", default=None
    )
    corpus_id: strawberry.ID | None = strawberry.field(
        name="corpusId",
        description="If corpus-specific leaderboard, the corpus ID",
        default=None,
    )
    total_users: int | None = strawberry.field(
        name="totalUsers",
        description="Total number of users in leaderboard",
        default=None,
    )
    entries: list[LeaderboardEntryType | None] | None = strawberry.field(
        name="entries", description="Leaderboard entries in rank order", default=None
    )
    current_user_rank: int | None = strawberry.field(
        name="currentUserRank",
        description="Current user's rank in this leaderboard (null if not ranked)",
        default=None,
    )


register_type("LeaderboardType", LeaderboardType, model=None)


@strawberry.type(
    name="LeaderboardEntryType",
    description="Represents a single entry in the leaderboard.\n\nIssue: #613 - Create leaderboard and community stats dashboard\nEpic: #572 - Social Features Epic",
)
class LeaderboardEntryType:
    user: None | (Annotated[UserType, strawberry.lazy("config.graphql.user_types")]) = (
        strawberry.field(
            name="user", description="The user in this leaderboard entry", default=None
        )
    )
    rank: int | None = strawberry.field(
        name="rank",
        description="User's rank in the leaderboard (1-indexed)",
        default=None,
    )
    score: int | None = strawberry.field(
        name="score", description="User's score for this metric", default=None
    )
    badge_count: int | None = strawberry.field(
        name="badgeCount", description="Total badges earned by user", default=None
    )
    message_count: int | None = strawberry.field(
        name="messageCount", description="Total messages posted by user", default=None
    )
    thread_count: int | None = strawberry.field(
        name="threadCount", description="Total threads created by user", default=None
    )
    annotation_count: int | None = strawberry.field(
        name="annotationCount",
        description="Total annotations created by user",
        default=None,
    )
    reputation: int | None = strawberry.field(
        name="reputation", description="User's reputation score", default=None
    )
    is_rising_star: bool | None = strawberry.field(
        name="isRisingStar",
        description="True if user has shown significant recent activity",
        default=None,
    )


register_type("LeaderboardEntryType", LeaderboardEntryType, model=None)


@strawberry.type(
    name="CommunityStatsType",
    description="Overall community engagement statistics.\n\nIssue: #613 - Create leaderboard and community stats dashboard\nEpic: #572 - Social Features Epic",
)
class CommunityStatsType:
    total_users: int | None = strawberry.field(
        name="totalUsers", description="Total number of active users", default=None
    )
    total_messages: int | None = strawberry.field(
        name="totalMessages", description="Total messages posted", default=None
    )
    total_threads: int | None = strawberry.field(
        name="totalThreads", description="Total threads created", default=None
    )
    total_annotations: int | None = strawberry.field(
        name="totalAnnotations", description="Total annotations created", default=None
    )
    total_badges_awarded: int | None = strawberry.field(
        name="totalBadgesAwarded", description="Total badge awards", default=None
    )
    badge_distribution: list[BadgeDistributionType | None] | None = strawberry.field(
        name="badgeDistribution",
        description="Badge distribution across users",
        default=None,
    )
    messages_this_week: int | None = strawberry.field(
        name="messagesThisWeek",
        description="Messages posted in last 7 days",
        default=None,
    )
    messages_this_month: int | None = strawberry.field(
        name="messagesThisMonth",
        description="Messages posted in last 30 days",
        default=None,
    )
    active_users_this_week: int | None = strawberry.field(
        name="activeUsersThisWeek",
        description="Users who posted in last 7 days",
        default=None,
    )
    active_users_this_month: int | None = strawberry.field(
        name="activeUsersThisMonth",
        description="Users who posted in last 30 days",
        default=None,
    )


register_type("CommunityStatsType", CommunityStatsType, model=None)


@strawberry.type(
    name="BadgeDistributionType",
    description="Statistics about badge distribution across users.\n\nIssue: #613 - Create leaderboard and community stats dashboard\nEpic: #572 - Social Features Epic",
)
class BadgeDistributionType:
    badge: BadgeType | None = strawberry.field(
        name="badge", description="The badge", default=None
    )
    award_count: int | None = strawberry.field(
        name="awardCount",
        description="Number of times this badge has been awarded",
        default=None,
    )
    unique_recipients: int | None = strawberry.field(
        name="uniqueRecipients",
        description="Number of unique users who have earned this badge",
        default=None,
    )


register_type("BadgeDistributionType", BadgeDistributionType, model=None)


def _resolve_SemanticSearchResultType_document(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/social_types.py:419

    Port of SemanticSearchResultType.resolve_document

    Resolve the document from the annotation.

    Delegates to ``AnnotationType.resolve_document`` (the ported
    ``_resolve_AnnotationType_document``) so this convenience field shares
    the annotation resolver's visibility gate (it must not leak a private
    document via a raw FK) AND resolves structural annotations
    (``document_id=NULL``) through their shared structural set, exactly
    like the nested ``annotation { document }`` field.
    """
    # Deferred import mirrors the reference's late binding through the
    # AnnotationType class and avoids a module-level import cycle.
    from config.graphql.annotation_types import _resolve_AnnotationType_document

    if root.annotation is None:
        return None
    return _resolve_AnnotationType_document(root.annotation, info)


def _resolve_SemanticSearchResultType_corpus(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/social_types.py:432

    Port of SemanticSearchResultType.resolve_corpus

    Resolve the corpus from the annotation.
    """
    if root.annotation:
        return root.annotation.corpus
    return None


@strawberry.type(
    name="SemanticSearchResultType",
    description="Result type for semantic (vector) search across annotations.\n\nReturns annotation matches with their similarity scores, enabling\nrelevance-ranked search results from the global embeddings.\n\nPERMISSION MODEL:\n- Filters documents through the service layer (BaseService.filter_visible)\n- Structural annotations visible if document is accessible\n- Non-structural annotations visible if public OR owned by user",
)
class SemanticSearchResultType:
    annotation: Annotated[
        AnnotationType, strawberry.lazy("config.graphql.annotation_types")
    ] = strawberry.field(
        name="annotation", description="The matched annotation", default=None
    )
    similarity_score: float = strawberry.field(
        name="similarityScore",
        description="Similarity score (0.0-1.0, higher is more similar)",
        default=None,
    )

    @strawberry.field(
        name="document",
        description="The document containing this annotation (for convenience)",
    )
    def document(
        self, info: strawberry.Info
    ) -> None | (
        Annotated[DocumentType, strawberry.lazy("config.graphql.document_types")]
    ):
        kwargs = strip_unset({})
        return _resolve_SemanticSearchResultType_document(self, info, **kwargs)

    @strawberry.field(
        name="corpus", description="The corpus containing this annotation, if any"
    )
    def corpus(
        self, info: strawberry.Info
    ) -> None | (Annotated[CorpusType, strawberry.lazy("config.graphql.corpus_types")]):
        kwargs = strip_unset({})
        return _resolve_SemanticSearchResultType_corpus(self, info, **kwargs)

    block_context: BlockContextType | None = strawberry.field(
        name="blockContext",
        description="Smallest enclosing OC_SUBTREE_GROUP subtree for this hit, or null when the annotation has no materialised containing block (root structural rows, legacy documents).",
        default=None,
    )


register_type("SemanticSearchResultType", SemanticSearchResultType, model=None)


@strawberry.type(
    name="BlockContextType",
    description='The smallest enclosing ``OC_SUBTREE_GROUP`` block for a vector hit.\n\nLets clients deep-link directly to the materialised subtree relationship\n(``Relationship.id``) instead of recursively walking ``parent_id`` —\nused by the document viewer\'s "jump to surfaced block" affordance.',
)
class BlockContextType:
    relationship_id: strawberry.ID = strawberry.field(
        name="relationshipId",
        description="Database PK of the OC_SUBTREE_GROUP relationship. NOTE: this is the raw Django PK (matching ``Relationship.id``), NOT a global Relay ID — frontend deep-links pass it through directly.",
        default=None,
    )
    source_annotation_id: strawberry.ID = strawberry.field(
        name="sourceAnnotationId",
        description="PK of the ancestor annotation that anchors this block. Useful for highlighting the block root in the document viewer.",
        default=None,
    )
    source_text: str = strawberry.field(
        name="sourceText",
        description="Raw text of the ancestor annotation. May be empty for image-only structural rows; clients should treat empty as valid rather than missing.",
        default=None,
    )
    target_annotation_ids: list[strawberry.ID] = strawberry.field(
        name="targetAnnotationIds",
        description="PKs of every annotation transitively under the block source — i.e. the descendants the document viewer should also highlight when jumping to this block.",
        default=None,
    )
    block_text: str = strawberry.field(
        name="blockText",
        description="Source + targets concatenated newline-separated, capped at ``SUBTREE_GROUP_BLOCK_TEXT_MAX_CHARS`` characters. Safe to render directly; no further truncation needed.",
        default=None,
    )


register_type("BlockContextType", BlockContextType, model=None)


@strawberry.type(
    name="SemanticSearchRelationshipResultType",
    description="Semantic search hit where the matched object is a *Relationship*.\n\nSurfaces ``OC_SUBTREE_GROUP`` rows (or, in the future, any embedded\nrelationship type) ranked by vector similarity. The doc viewer uses\n``source_annotation_id`` + ``target_annotation_ids`` to scroll-and-select\nthe whole block in a single navigation, mirroring the existing\n``RelationGroup`` selection flow.\n\nID convention\n-------------\n``relationship_id``, ``source_annotation_id``, ``target_annotation_ids``,\n``document_id``, and ``corpus_id`` are ALL raw Django PKs (not Relay\nglobal IDs). The frontend deep-link path consumes them directly without\n``from_global_id``. Do NOT feed these values into resolvers that expect\na Relay global ID (e.g. ``node(id: $documentId)``) — they will silently\nfail. Use the corresponding Relay-encoded type if you need that contract.",
)
class SemanticSearchRelationshipResultType:
    relationship_id: strawberry.ID = strawberry.field(
        name="relationshipId",
        description="Database PK of the Relationship. NOTE: this is the raw Django PK (matching ``Relationship.id``), NOT a global Relay ID — frontend deep-links and selection setters pass it through directly without ``from_global_id``.",
        default=None,
    )
    similarity_score: float = strawberry.field(
        name="similarityScore",
        description="Cosine similarity (0.0-1.0, higher is more similar).",
        default=None,
    )
    label: str | None = strawberry.field(
        name="label",
        description="Relationship label text (e.g. ``OC_SUBTREE_GROUP``). Provided so callers can filter or branch on the relationship kind without a follow-up fetch.",
        default=None,
    )
    source_annotation_id: strawberry.ID | None = strawberry.field(
        name="sourceAnnotationId",
        description="PK of the (typically single) source annotation — the block's root. Null only when the relationship has no source row, which the materialiser does not produce but defensive frontends should still handle.",
        default=None,
    )
    target_annotation_ids: list[strawberry.ID] = strawberry.field(
        name="targetAnnotationIds",
        description="PKs of the relationship's target annotations.",
        default=None,
    )
    block_text: str = strawberry.field(
        name="blockText",
        description="Source + targets concatenated newline-separated, capped at ``SUBTREE_GROUP_BLOCK_TEXT_MAX_CHARS`` — the same string the embedder saw, suitable for snippet display.",
        default=None,
    )
    document_id: strawberry.ID | None = strawberry.field(
        name="documentId",
        description="PK of the document this relationship is anchored to (or that shares the ``StructuralAnnotationSet`` for structural rows). Null when the relationship is global and not tied to any single document.",
        default=None,
    )
    corpus_id: strawberry.ID | None = strawberry.field(
        name="corpusId",
        description="PK of the corpus this relationship belongs to. Null for non-corpus relationships.",
        default=None,
    )


register_type(
    "SemanticSearchRelationshipResultType",
    SemanticSearchRelationshipResultType,
    model=None,
)
