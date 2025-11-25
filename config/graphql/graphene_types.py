import logging
from typing import Optional

import graphene
import graphene.types.json
from django.contrib.auth import get_user_model
from django.db.models import Q, QuerySet
from graphene import relay
from graphene.types.generic import GenericScalar
from graphene_django import DjangoObjectType
from graphene_django.filter import DjangoFilterConnectionField
from graphql_relay import from_global_id, to_global_id

from config.graphql.base import CountableConnection
from config.graphql.custom_resolvers import resolve_doc_annotations_optimized
from config.graphql.filters import AnnotationFilter, LabelFilter
from config.graphql.permissioning.permission_annotator.mixins import (
    AnnotatePermissionsForReadMixin,
)
from opencontractserver.analyzer.models import Analysis, Analyzer, GremlinEngine
from opencontractserver.annotations.models import (
    Annotation,
    AnnotationLabel,
    LabelSet,
    Note,
    NoteRevision,
    Relationship,
)
from opencontractserver.conversations.models import ChatMessage, Conversation
from opencontractserver.corpuses.models import (
    Corpus,
    CorpusAction,
    CorpusDescriptionRevision,
    CorpusEngagementMetrics,
    CorpusFolder,
    CorpusQuery,
)
from opencontractserver.documents.models import (
    Document,
    DocumentAnalysisRow,
    DocumentPath,
    DocumentRelationship,
    DocumentSummaryRevision,
)
from opencontractserver.extracts.models import Column, Datacell, Extract, Fieldset
from opencontractserver.feedback.models import UserFeedback
from opencontractserver.pipeline.base.file_types import (
    FileTypeEnum as BackendFileTypeEnum,
)
from opencontractserver.pipeline.utils import get_components_by_mimetype
from opencontractserver.users.models import Assignment, UserExport, UserImport

User = get_user_model()
logger = logging.getLogger(__name__)


def build_flat_tree(
    nodes: list, type_name: str = "AnnotationType", text_key: str = "raw_text"
) -> list:
    """
    Builds a flat list of node representations from a list of dictionaries where each
    has at least 'id' and 'parent_id', plus an additional text field (default "raw_text")
    that may differ depending on the model (Annotation or Note).

    Args:
        nodes (list): A list of dicts with fields "id", "parent_id", and a text field.
        type_name (str): GraphQL type name used by to_global_id (e.g. "AnnotationType" or "NoteType").
        text_key (str): The dictionary key to use for the text field (e.g. "raw_text" or "content").

    Returns:
        list: A list of node dicts in which each node has:
            - "id" (global ID),
            - text field under "raw_text",
            - "children": list of child node global IDs.
    """
    # Map node IDs to their immediate children IDs
    id_to_children = {}
    for node in nodes:
        node_id = node["id"]
        parent_id = node["parent_id"]
        if parent_id:
            id_to_children.setdefault(parent_id, []).append(node_id)

    # Build the flat list of nodes
    node_list = []
    for node in nodes:
        node_id = node["id"]
        node_id_global = to_global_id(type_name, node_id)
        # Convert child IDs to global IDs
        children_ids = id_to_children.get(node_id, [])
        children_global_ids = [to_global_id(type_name, cid) for cid in children_ids]
        # Use the appropriate text field key, defaulting to empty if missing
        node_dict = {
            "id": node_id_global,
            text_key: node.get(text_key, ""),
            "children": children_global_ids,
        }
        node_list.append(node_dict)

    return node_list


class UserType(AnnotatePermissionsForReadMixin, DjangoObjectType):
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

    def resolve_reputation_global(self, info):
        """
        Resolve global reputation for this user.

        Epic: #565 - Corpus Engagement Metrics & Analytics
        Issue: #568 - Create GraphQL queries for engagement metrics and leaderboards
        """
        from opencontractserver.conversations.models import UserReputation

        try:
            rep = UserReputation.objects.get(user=self, corpus__isnull=True)
            return rep.reputation_score
        except UserReputation.DoesNotExist:
            return 0

    def resolve_reputation_for_corpus(self, info, corpus_id):
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

    def resolve_total_messages(self, info):
        """
        Resolve total messages posted by this user.
        Only counts messages visible to the requesting user.

        Issue: #611 - User Profile Page
        """
        from opencontractserver.conversations.models import ChatMessage

        return (
            ChatMessage.objects.filter(creator=self, msg_type="HUMAN")
            .visible_to_user(info.context.user)
            .count()
        )

    def resolve_total_threads_created(self, info):
        """
        Resolve total threads created by this user.
        Only counts threads visible to the requesting user.

        Issue: #611 - User Profile Page
        """
        from opencontractserver.conversations.models import Conversation

        return (
            Conversation.objects.filter(creator=self, conversation_type="thread")
            .visible_to_user(info.context.user)
            .count()
        )

    def resolve_total_annotations_created(self, info):
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

    def resolve_total_documents_uploaded(self, info):
        """
        Resolve total documents uploaded by this user.
        Only counts documents visible to the requesting user.

        Issue: #611 - User Profile Page
        """
        from opencontractserver.documents.models import Document

        return (
            Document.objects.filter(creator=self)
            .visible_to_user(info.context.user)
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


class RelationshipType(AnnotatePermissionsForReadMixin, DjangoObjectType):
    class Meta:
        model = Relationship
        interfaces = [relay.Node]
        connection_class = CountableConnection


class RelationInputType(AnnotatePermissionsForReadMixin, graphene.InputObjectType):
    id = graphene.String()
    source_ids = graphene.List(graphene.String)
    target_ids = graphene.List(graphene.String)
    relationship_label_id = graphene.String()
    corpus_id = graphene.String()
    document_id = graphene.String()


class AnnotationInputType(AnnotatePermissionsForReadMixin, graphene.InputObjectType):
    id = graphene.String(required=True)
    page = graphene.Int()
    raw_text = graphene.String()
    json = GenericScalar()  # noqa
    annotation_label = graphene.String()
    is_public = graphene.Boolean()


class AnnotationType(AnnotatePermissionsForReadMixin, DjangoObjectType):
    json = GenericScalar()  # noqa
    feedback_count = graphene.Int(description="Count of user feedback")

    all_source_node_in_relationship = graphene.List(lambda: RelationshipType)

    def resolve_feedback_count(self, info):
        # If feedback_count was annotated on the queryset, use it
        if hasattr(self, "feedback_count"):
            return self.feedback_count
        # Otherwise, count it (but this triggers N+1)
        return self.user_feedback.count()

    def resolve_all_source_node_in_relationship(self, info):
        return self.source_node_in_relationships.all()

    all_target_node_in_relationship = graphene.List(lambda: RelationshipType)

    def resolve_all_target_node_in_relationship(self, info):
        return self.target_node_in_relationships.all()

    # Updated fields for tree representations
    descendants_tree = graphene.List(
        GenericScalar,
        description="List of descendant annotations, each with immediate children's IDs.",
    )
    full_tree = graphene.List(
        GenericScalar,
        description="List of annotations from the root ancestor, each with immediate children's IDs.",
    )

    subtree = graphene.List(
        GenericScalar,
        description="List representing the path from the root ancestor to this annotation and its descendants.",
    )

    # Resolver for descendants_tree
    def resolve_descendants_tree(self, info):
        """
        Returns a flat list of descendant annotations,
        each including only the IDs of its immediate children.
        """
        from django_cte import With

        def get_descendants(cte):
            base_qs = Annotation.objects.filter(parent_id=self.id).values(
                "id", "parent_id", "raw_text"
            )
            recursive_qs = cte.join(Annotation, parent_id=cte.col.id).values(
                "id", "parent_id", "raw_text"
            )
            return base_qs.union(recursive_qs, all=True)

        cte = With.recursive(get_descendants)
        descendants_qs = cte.queryset().with_cte(cte).order_by("id")
        descendants_list = list(descendants_qs)

        return build_flat_tree(
            descendants_list, type_name="AnnotationType", text_key="raw_text"
        )

    # Resolver for full_tree
    def resolve_full_tree(self, info):
        """
        Returns a flat list of annotations from the root ancestor,
        each including only the IDs of its immediate children.
        """
        from django_cte import With

        # Find the root ancestor
        root = self
        while root.parent_id is not None:
            root = root.parent

        def get_full_tree(cte):
            base_qs = Annotation.objects.filter(id=root.id).values(
                "id", "parent_id", "raw_text"
            )
            recursive_qs = cte.join(Annotation, parent_id=cte.col.id).values(
                "id", "parent_id", "raw_text"
            )
            return base_qs.union(recursive_qs, all=True)

        cte = With.recursive(get_full_tree)
        full_tree_qs = cte.queryset().with_cte(cte).order_by("id")
        nodes = list(full_tree_qs)
        full_tree = build_flat_tree(
            nodes, type_name="AnnotationType", text_key="raw_text"
        )
        return full_tree

    # Resolver for subtree
    def resolve_subtree(self, info):
        """
        Returns a combined tree that includes:
        - The path from the root ancestor to this annotation (ancestors).
        - This annotation and all its descendants.
        """
        from django_cte import With

        # Find all ancestors up to the root
        ancestors = []
        node = self
        while node.parent_id is not None:
            ancestors.append(node)
            node = node.parent
        ancestors.append(node)  # Include the root ancestor
        ancestor_ids = [ancestor.id for ancestor in ancestors]

        # Get all descendants of the current node
        def get_descendants(cte):
            base_qs = Annotation.objects.filter(parent_id=self.id).values(
                "id", "parent_id", "raw_text"
            )
            recursive_qs = cte.join(Annotation, parent_id=cte.col.id).values(
                "id", "parent_id", "raw_text"
            )
            return base_qs.union(recursive_qs, all=True)

        descendants_cte = With.recursive(get_descendants)
        descendants_qs = (
            descendants_cte.queryset()
            .with_cte(descendants_cte)
            .values("id", "parent_id", "raw_text")
        )

        # Combine ancestors and descendants
        combined_qs = (
            Annotation.objects.filter(id__in=ancestor_ids)
            .values("id", "parent_id", "raw_text")
            .union(descendants_qs, all=True)
        )

        subtree_nodes = list(combined_qs)
        subtree = build_flat_tree(
            subtree_nodes, type_name="AnnotationType", text_key="raw_text"
        )
        return subtree

    class Meta:
        model = Annotation
        interfaces = [relay.Node]
        exclude = ("embedding",)
        connection_class = CountableConnection

        # In order for filter options to show up in nested resolvers, you need to specify them
        # in the Graphene type
        filterset_class = AnnotationFilter

    @classmethod
    def get_queryset(cls, queryset, info):
        # Check if permissions were already handled by the query optimizer
        # The optimizer adds _can_read, _can_create, etc. annotations
        if hasattr(queryset, "query") and queryset.query.annotations:
            # Check if the queryset has permission annotations from the optimizer
            if any(key.startswith("_can_") for key in queryset.query.annotations):
                # Permissions already handled by query optimizer, don't filter again
                return queryset

        # Fall back to original permission filtering
        if issubclass(type(queryset), QuerySet):
            return queryset.visible_to_user(info.context.user)
        elif "RelatedManager" in str(type(queryset)):
            # https://stackoverflow.com/questions/11320702/import-relatedmanager-from-django-db-models-fields-related
            return queryset.all().visible_to_user(info.context.user)
        else:
            return queryset


class PdfPageInfoType(graphene.ObjectType):
    page_count = graphene.Int()
    current_page = graphene.Int()
    has_next_page = graphene.Boolean()
    has_previous_page = graphene.Boolean()
    corpus_id = graphene.ID()
    document_id = graphene.ID()
    for_analysis_ids = graphene.String()
    label_type = graphene.String()


class LabelTypeEnum(graphene.Enum):
    RELATIONSHIP_LABEL = "RELATIONSHIP_LABEL"
    DOC_TYPE_LABEL = "DOC_TYPE_LABEL"
    TOKEN_LABEL = "TOKEN_LABEL"
    SPAN_LABEL = "SPAN_LABEL"


class ConversationTypeEnum(graphene.Enum):
    """Enum for conversation types."""

    CHAT = "chat"
    THREAD = "thread"


class AgentTypeEnum(graphene.Enum):
    """Enum for agent types in messages."""

    DOCUMENT_AGENT = "document_agent"
    CORPUS_AGENT = "corpus_agent"


# -------------------- Versioning Types (Phase 1) -------------------- #


class PathActionEnum(graphene.Enum):
    """Enum for document path lifecycle actions."""

    IMPORTED = "IMPORTED"
    MOVED = "MOVED"
    RENAMED = "RENAMED"
    DELETED = "DELETED"
    RESTORED = "RESTORED"
    UPDATED = "UPDATED"


class VersionChangeTypeEnum(graphene.Enum):
    """Enum for types of version changes."""

    INITIAL = "INITIAL"
    CONTENT_UPDATE = "CONTENT_UPDATE"
    MINOR_EDIT = "MINOR_EDIT"
    MAJOR_REVISION = "MAJOR_REVISION"


class DocumentVersionType(graphene.ObjectType):
    """Represents a single version in the document's content history."""

    id = graphene.ID(required=True, description="Global ID of the document version")
    version_number = graphene.Int(
        required=True, description="Sequential version number"
    )
    hash = graphene.String(required=True, description="SHA-256 hash of PDF content")
    created_at = graphene.DateTime(
        required=True, description="When version was created"
    )
    created_by = graphene.Field(
        lambda: UserType, required=True, description="User who created this version"
    )
    size_bytes = graphene.Int(description="File size in bytes")
    change_type = graphene.Field(
        VersionChangeTypeEnum,
        required=True,
        description="Type of change from previous version",
    )
    parent_version = graphene.Field(
        lambda: DocumentVersionType, description="Previous version in content tree"
    )


class VersionHistoryType(graphene.ObjectType):
    """Complete version history for a document."""

    versions = graphene.List(
        graphene.NonNull(DocumentVersionType),
        required=True,
        description="All versions of this document",
    )
    current_version = graphene.Field(
        DocumentVersionType, required=True, description="The current active version"
    )
    version_tree = GenericScalar(description="Tree structure of version relationships")


class PathEventType(graphene.ObjectType):
    """A single event in the document's path history."""

    id = graphene.ID(required=True, description="Global ID of the path event")
    action = graphene.Field(
        PathActionEnum, required=True, description="Type of path action"
    )
    path = graphene.String(required=True, description="Path at time of event")
    folder = graphene.Field(
        lambda: CorpusFolderType,
        description="Folder at time of event (null if at root)",
    )
    timestamp = graphene.DateTime(required=True, description="When this event occurred")
    user = graphene.Field(
        lambda: UserType, required=True, description="User who performed the action"
    )
    version_number = graphene.Int(
        required=True, description="Content version at time of event"
    )


class PathHistoryType(graphene.ObjectType):
    """Complete path history for a document in a corpus."""

    events = graphene.List(
        graphene.NonNull(PathEventType),
        required=True,
        description="All path events in chronological order",
    )
    current_path = graphene.String(
        required=True, description="Current path of document"
    )
    original_path = graphene.String(required=True, description="Original import path")
    move_count = graphene.Int(
        required=True, description="Number of move/rename operations"
    )


class DocumentPathType(AnnotatePermissionsForReadMixin, DjangoObjectType):
    """GraphQL type for DocumentPath model - represents filesystem lifecycle events."""

    action = graphene.Field(PathActionEnum, description="Inferred action type")

    def resolve_action(self, info):
        """Infer action type from path state."""
        if self.is_deleted:
            return "DELETED"
        elif self.parent is None:
            return "IMPORTED"
        else:
            # Check if this is an update vs move
            if hasattr(self, "parent") and self.parent:
                if self.parent.path != self.path:
                    return "MOVED"
                elif self.parent.version_number != self.version_number:
                    return "UPDATED"
            return "UPDATED"

    class Meta:
        model = DocumentPath
        interfaces = [relay.Node]
        connection_class = CountableConnection

    @classmethod
    def get_queryset(cls, queryset, info):
        """Filter paths to only those in corpuses the user can see."""
        if issubclass(type(queryset), QuerySet):
            # Filter by corpus visibility
            from opencontractserver.corpuses.models import Corpus

            visible_corpus_ids = Corpus.objects.visible_to_user(
                info.context.user
            ).values_list("id", flat=True)
            return queryset.filter(corpus_id__in=visible_corpus_ids)
        elif "RelatedManager" in str(type(queryset)):
            from opencontractserver.corpuses.models import Corpus

            visible_corpus_ids = Corpus.objects.visible_to_user(
                info.context.user
            ).values_list("id", flat=True)
            return queryset.all().filter(corpus_id__in=visible_corpus_ids)
        else:
            return queryset


class DocumentRelationshipType(AnnotatePermissionsForReadMixin, DjangoObjectType):
    """GraphQL type for DocumentRelationship model."""

    data = GenericScalar()

    class Meta:
        model = DocumentRelationship
        interfaces = [relay.Node]
        connection_class = CountableConnection

    @classmethod
    def get_queryset(cls, queryset, info):
        if issubclass(type(queryset), QuerySet):
            return queryset.visible_to_user(info.context.user)
        elif "RelatedManager" in str(type(queryset)):
            return queryset.all().visible_to_user(info.context.user)
        else:
            return queryset


class PageAwareAnnotationType(graphene.ObjectType):
    pdf_page_info = graphene.Field(PdfPageInfoType)
    page_annotations = graphene.List(AnnotationType)


class AnnotationLabelType(AnnotatePermissionsForReadMixin, DjangoObjectType):
    class Meta:
        model = AnnotationLabel
        interfaces = [relay.Node]
        connection_class = CountableConnection


class LabelSetType(AnnotatePermissionsForReadMixin, DjangoObjectType):
    annotation_labels = DjangoFilterConnectionField(
        AnnotationLabelType, filterset_class=LabelFilter
    )

    # Count fields for different label types
    doc_label_count = graphene.Int(description="Count of document-level type labels")
    span_label_count = graphene.Int(description="Count of span-based labels")
    token_label_count = graphene.Int(description="Count of token-level labels")

    def resolve_doc_label_count(self, info):
        return self.annotation_labels.filter(label_type="DOC_TYPE_LABEL").count()

    def resolve_span_label_count(self, info):
        return self.annotation_labels.filter(label_type="SPAN_LABEL").count()

    def resolve_token_label_count(self, info):
        return self.annotation_labels.filter(label_type="TOKEN_LABEL").count()

    # To get ALL labels for a given labelset
    all_annotation_labels = graphene.Field(graphene.List(AnnotationLabelType))

    def resolve_all_annotation_labels(self, info):
        return self.annotation_labels.all()

    # Custom resolver for icon field
    def resolve_icon(self, info):
        return "" if not self.icon else info.context.build_absolute_uri(self.icon.url)

    class Meta:
        model = LabelSet
        interfaces = [relay.Node]
        connection_class = CountableConnection


class NoteType(AnnotatePermissionsForReadMixin, DjangoObjectType):
    """
    GraphQL type for the Note model with tree-based functionality.
    """

    # Updated fields for tree representations
    descendants_tree = graphene.List(
        GenericScalar,
        description="List of descendant notes, each with immediate children's IDs.",
    )
    full_tree = graphene.List(
        GenericScalar,
        description="List of notes from the root ancestor, each with immediate children's IDs.",
    )
    subtree = graphene.List(
        GenericScalar,
        description="List representing the path from the root ancestor to this note and its descendants.",
    )

    # Version history
    revisions = graphene.List(
        lambda: NoteRevisionType,
        description="List of all revisions/versions of this note, ordered by version.",
    )
    current_version = graphene.Int(description="Current version number of the note")

    def resolve_revisions(self, info):
        """Returns all revisions for this note, ordered by version."""
        return self.revisions.all()

    def resolve_current_version(self, info):
        """Returns the current version number."""
        latest_revision = self.revisions.order_by("-version").first()
        return latest_revision.version if latest_revision else 0

    # Resolver for descendants_tree
    def resolve_descendants_tree(self, info):
        """
        Returns a flat list of descendant notes,
        each including only the IDs of its immediate children.
        """
        from django_cte import With

        def get_descendants(cte):
            base_qs = Note.objects.filter(parent_id=self.id).values(
                "id", "parent_id", "content"
            )
            recursive_qs = cte.join(Note, parent_id=cte.col.id).values(
                "id", "parent_id", "content"
            )
            return base_qs.union(recursive_qs, all=True)

        cte = With.recursive(get_descendants)
        descendants_qs = cte.queryset().with_cte(cte).order_by("id")
        descendants_list = list(descendants_qs)
        descendants_tree = build_flat_tree(
            descendants_list, type_name="NoteType", text_key="content"
        )
        return descendants_tree

    # Resolver for full_tree
    def resolve_full_tree(self, info):
        """
        Returns a flat list of notes from the root ancestor,
        each including only the IDs of its immediate children.
        """
        from django_cte import With

        # Find the root ancestor
        root = self
        while root.parent_id is not None:
            root = root.parent

        def get_full_tree(cte):
            base_qs = Note.objects.filter(id=root.id).values(
                "id", "parent_id", "content"
            )
            recursive_qs = cte.join(Note, parent_id=cte.col.id).values(
                "id", "parent_id", "content"
            )
            return base_qs.union(recursive_qs, all=True)

        cte = With.recursive(get_full_tree)
        full_tree_qs = cte.queryset().with_cte(cte).order_by("id")
        nodes = list(full_tree_qs)
        full_tree = build_flat_tree(nodes, type_name="NoteType", text_key="content")
        return full_tree

    # Resolver for subtree
    def resolve_subtree(self, info):
        """
        Returns a combined tree that includes:
        - The path from the root ancestor to this note (ancestors).
        - This note and all its descendants.
        """
        from django_cte import With

        # Find all ancestors up to the root
        ancestors = []
        node = self
        while node.parent_id is not None:
            ancestors.append(node)
            node = node.parent
        ancestors.append(node)  # Include the root ancestor
        ancestor_ids = [ancestor.id for ancestor in ancestors]

        # Get all descendants of the current node
        def get_descendants(cte):
            base_qs = Note.objects.filter(parent_id=self.id).values(
                "id", "parent_id", "content"
            )
            recursive_qs = cte.join(Note, parent_id=cte.col.id).values(
                "id", "parent_id", "content"
            )
            return base_qs.union(recursive_qs, all=True)

        descendants_cte = With.recursive(get_descendants)
        descendants_qs = (
            descendants_cte.queryset()
            .with_cte(descendants_cte)
            .values("id", "parent_id", "content")
        )

        # Combine ancestors and descendants
        combined_qs = (
            Note.objects.filter(id__in=ancestor_ids)
            .values("id", "parent_id", "content")
            .union(descendants_qs, all=True)
        )

        subtree_nodes = list(combined_qs)
        subtree = build_flat_tree(
            subtree_nodes, type_name="NoteType", text_key="content"
        )
        return subtree

    class Meta:
        model = Note
        exclude = ("embedding",)
        interfaces = [relay.Node]
        connection_class = CountableConnection

    @classmethod
    def get_queryset(cls, queryset, info):
        if issubclass(type(queryset), QuerySet):
            return queryset.visible_to_user(info.context.user)
        elif "RelatedManager" in str(type(queryset)):
            return queryset.all().visible_to_user(info.context.user)
        else:
            return queryset


class NoteRevisionType(DjangoObjectType):
    """
    GraphQL type for the NoteRevision model to expose note version history.
    """

    class Meta:
        model = NoteRevision
        interfaces = [relay.Node]
        connection_class = CountableConnection
        fields = [
            "id",
            "note",
            "author",
            "version",
            "diff",
            "snapshot",
            "checksum_base",
            "checksum_full",
            "created",
        ]


class DocumentType(AnnotatePermissionsForReadMixin, DjangoObjectType):
    # Import optimized resolvers for file fields
    from config.graphql.optimized_file_resolvers import (
        resolve_icon_optimized,
        resolve_md_summary_file_optimized,
        resolve_pawls_parse_file_optimized,
        resolve_pdf_file_optimized,
        resolve_txt_extract_file_optimized,
    )

    # Use optimized resolvers that minimize storage backend overhead
    resolve_pdf_file = resolve_pdf_file_optimized
    resolve_icon = resolve_icon_optimized
    resolve_txt_extract_file = resolve_txt_extract_file_optimized
    resolve_md_summary_file = resolve_md_summary_file_optimized
    resolve_pawls_parse_file = resolve_pawls_parse_file_optimized
    resolve_doc_annotations = resolve_doc_annotations_optimized

    all_structural_annotations = graphene.List(AnnotationType)

    def resolve_all_structural_annotations(self, info):
        from opencontractserver.annotations.query_optimizer import (
            AnnotationQueryOptimizer,
        )

        return AnnotationQueryOptimizer.get_document_annotations(
            document_id=self.id,
            user=getattr(info.context, "user", None),
            structural=True,
            use_cache=True,
        )

    # Updated field and resolver for all annotations with enhanced filtering
    all_annotations = graphene.List(
        AnnotationType,
        corpus_id=graphene.ID(),
        analysis_id=graphene.ID(),
        is_structural=graphene.Boolean(),
    )

    def resolve_all_annotations(
        self, info, corpus_id=None, analysis_id=None, is_structural=None
    ):
        from opencontractserver.annotations.query_optimizer import (
            AnnotationQueryOptimizer,
        )

        user = getattr(info.context, "user", None)
        corpus_pk = from_global_id(corpus_id)[1] if corpus_id else None
        analysis_pk = None
        if analysis_id:
            analysis_pk = (
                0 if analysis_id == "__none__" else from_global_id(analysis_id)[1]
            )
        return AnnotationQueryOptimizer.get_document_annotations(
            document_id=self.id,
            user=user,
            corpus_id=corpus_pk,
            analysis_id=analysis_pk,
            structural=is_structural,
            use_cache=True,
        )

    # New field and resolver for all relationships
    all_relationships = graphene.List(
        RelationshipType,
        corpus_id=graphene.ID(),
        analysis_id=graphene.ID(),
    )

    def resolve_all_relationships(self, info, corpus_id=None, analysis_id=None):
        """Resolve all relationships using the optimizer."""
        from opencontractserver.annotations.query_optimizer import (
            RelationshipQueryOptimizer,
        )

        try:
            corpus_pk = None
            analysis_pk = None

            if corpus_id:
                _, corpus_pk = from_global_id(corpus_id)
            if analysis_id and analysis_id != "__none__":
                _, analysis_pk = from_global_id(analysis_id)
            elif analysis_id == "__none__":
                analysis_pk = 0  # Special case for user relationships

            # Get user from context
            user = info.context.user if hasattr(info.context, "user") else None

            return RelationshipQueryOptimizer.get_document_relationships(
                document_id=self.id,
                user=user,
                corpus_id=corpus_pk,
                analysis_id=analysis_pk,
                use_cache=True,
            )
        except Exception as e:
            logger.warning(
                f"Failed resolving relationships query for document {self.id} with input: corpus_id={corpus_id}, "
                f"analysis_id={analysis_id}. Error: {e}"
            )
            return []

    # New field for document relationships
    all_doc_relationships = graphene.List(
        DocumentRelationshipType,
        corpus_id=graphene.ID(),
    )

    def resolve_all_doc_relationships(self, info, corpus_id=None):
        try:
            if corpus_id is None:
                relationships = DocumentRelationship.objects.filter(
                    (Q(source_document=self) | Q(target_document=self))
                    & Q(structural=True)
                ).distinct()
            else:
                corpus_pk = from_global_id(corpus_id)[1]
                # Get relationships where this document is either source or target
                relationships = DocumentRelationship.objects.filter(
                    (Q(source_document=self) | Q(target_document=self))
                    & Q(corpus_id=corpus_pk)
                ).distinct()

            return relationships
        except Exception as e:
            logger.warning(
                "Failed resolving document relationships query for "
                f"document {self.id} with input: corpus_id={corpus_id}. "
                f"Error: {e}"
            )
            return []

    all_notes = graphene.List(
        NoteType,
        corpus_id=graphene.ID(),
    )

    def resolve_all_notes(self, info, corpus_id: Optional[str] = None):
        """
        Return the set of Note objects related to this Document instance that the user can see,
        filtered by corpus_id.
        """
        from opencontractserver.annotations.models import Note

        user = info.context.user

        # Start with a base queryset of all Notes the user can see
        base_qs = Note.objects.visible_to_user(user=user)

        if corpus_id is None:
            corpus_pk = None
            return base_qs.filter(document=self)

        else:
            corpus_pk = from_global_id(corpus_id)[1]
            # Then intersect with this Document's related notes, filtering by the given corpus_id
            # This ensures we only query notes that are both visible to the user and belong to
            # this specific Document (through the related manager self.notes).
            return base_qs.filter(document=self, corpus_id=corpus_pk)

    # Summary version history (corpus-specific)
    summary_revisions = graphene.List(
        lambda: DocumentSummaryRevisionType,
        corpus_id=graphene.ID(required=True),
        description="List of all summary revisions/versions for a specific corpus, ordered by version.",
    )
    current_summary_version = graphene.Int(
        corpus_id=graphene.ID(required=True),
        description="Current version number of the summary for a specific corpus",
    )
    summary_content = graphene.String(
        corpus_id=graphene.ID(required=True),
        description="Current summary content for a specific corpus",
    )

    def resolve_summary_revisions(self, info, corpus_id):
        """Returns all revisions for this document's summary in a specific corpus, ordered by version."""
        from opencontractserver.documents.models import DocumentSummaryRevision

        _, corpus_pk = from_global_id(corpus_id)
        return DocumentSummaryRevision.objects.filter(
            document_id=self.pk, corpus_id=corpus_pk
        ).order_by("version")

    def resolve_current_summary_version(self, info, corpus_id):
        """Returns the current summary version number for a specific corpus."""
        from opencontractserver.documents.models import DocumentSummaryRevision

        _, corpus_pk = from_global_id(corpus_id)
        latest_revision = (
            DocumentSummaryRevision.objects.filter(
                document_id=self.pk, corpus_id=corpus_pk
            )
            .order_by("-version")
            .first()
        )

        return latest_revision.version if latest_revision else 0

    def resolve_summary_content(self, info, corpus_id):
        """Returns the current summary content for a specific corpus."""
        from opencontractserver.corpuses.models import Corpus

        _, corpus_pk = from_global_id(corpus_id)
        try:
            corpus = Corpus.objects.get(pk=corpus_pk)
            return self.get_summary_for_corpus(corpus)
        except Corpus.DoesNotExist:
            return ""

    # -------------------- Version Metadata Fields (Phase 1.1) -------------------- #
    # These are lightweight fields that are always loaded with documents

    version_number = graphene.Int(
        corpus_id=graphene.ID(required=True),
        description="Content version number in this corpus (from DocumentPath)",
    )
    has_version_history = graphene.Boolean(
        description="True if this document has multiple versions (parent exists)"
    )
    version_count = graphene.Int(
        description="Total number of versions in this document's version tree"
    )
    is_latest_version = graphene.Boolean(
        description="True if this is the current version (Document.is_current)"
    )
    last_modified = graphene.DateTime(
        corpus_id=graphene.ID(required=True),
        description="When the document was last modified in this corpus",
    )

    # Lazy-loaded version history fields
    version_history = graphene.Field(
        VersionHistoryType,
        description="Complete version history (lazy-loaded on request)",
    )
    path_history = graphene.Field(
        PathHistoryType,
        corpus_id=graphene.ID(required=True),
        description="Path/location history in corpus (lazy-loaded on request)",
    )

    # Permission helpers for versioning features
    can_restore = graphene.Boolean(
        corpus_id=graphene.ID(required=True),
        description="Whether user can restore this document (requires UPDATE permission)",
    )
    can_view_history = graphene.Boolean(
        description="Whether user can view version history (requires READ permission)"
    )

    def resolve_version_number(self, info, corpus_id):
        """Get version number from DocumentPath for this corpus."""
        _, corpus_pk = from_global_id(corpus_id)
        try:
            path_record = DocumentPath.objects.filter(
                document_id=self.id, corpus_id=corpus_pk, is_current=True
            ).first()
            return path_record.version_number if path_record else 1
        except Exception:
            return 1

    def resolve_has_version_history(self, info):
        """Check if document has parent (i.e., multiple versions exist)."""
        return self.parent is not None

    def resolve_version_count(self, info):
        """Count total versions in this document's version tree."""
        # Count all documents with same version_tree_id
        return Document.objects.filter(version_tree_id=self.version_tree_id).count()

    def resolve_is_latest_version(self, info):
        """Check if this is the current version."""
        return self.is_current

    def resolve_last_modified(self, info, corpus_id):
        """Get last modification time from DocumentPath."""
        _, corpus_pk = from_global_id(corpus_id)
        try:
            path_record = DocumentPath.objects.filter(
                document_id=self.id, corpus_id=corpus_pk, is_current=True
            ).first()
            return path_record.created if path_record else self.modified
        except Exception:
            return self.modified

    def resolve_version_history(self, info):
        """
        Lazy-load complete version history.
        Returns all versions in the document's version tree.
        """
        from graphql_relay import to_global_id

        # Get all documents in the version tree, ordered by creation
        versions = Document.objects.filter(
            version_tree_id=self.version_tree_id
        ).order_by("created")

        version_list = []
        for idx, doc in enumerate(versions, start=1):
            # Determine change type
            if doc.parent is None:
                change_type = "INITIAL"
            else:
                # Could be enhanced to detect minor vs major changes
                change_type = "CONTENT_UPDATE"

            version_data = {
                "id": to_global_id("DocumentType", doc.id),
                "version_number": idx,
                "hash": doc.pdf_file_hash or "",
                "created_at": doc.created,
                "created_by": doc.creator,
                "size_bytes": doc.pdf_file.size if doc.pdf_file else None,
                "change_type": change_type,
                "parent_version": None,  # Could be resolved if needed
            }
            version_list.append(version_data)

        # Find current version
        current = next(
            (
                v
                for v in version_list
                if v["id"] == to_global_id("DocumentType", self.id)
            ),
            version_list[-1] if version_list else None,
        )

        return {
            "versions": version_list,
            "current_version": current,
            "version_tree": None,  # Could build tree structure if needed
        }

    def resolve_path_history(self, info, corpus_id):
        """
        Lazy-load path history for this document in a corpus.
        Returns all lifecycle events (import, move, delete, restore).
        """
        from graphql_relay import to_global_id

        _, corpus_pk = from_global_id(corpus_id)

        # Get all path records for this document in this corpus
        path_records = DocumentPath.objects.filter(
            document__version_tree_id=self.version_tree_id, corpus_id=corpus_pk
        ).order_by("created")

        events = []
        original_path = None
        current_path = None
        move_count = 0

        for path_record in path_records:
            # Infer action type
            if path_record.is_deleted:
                action = "DELETED"
            elif path_record.parent is None:
                action = "IMPORTED"
                original_path = path_record.path
            else:
                # Check if path changed vs version changed
                if hasattr(path_record, "parent") and path_record.parent:
                    if path_record.parent.path != path_record.path:
                        action = "MOVED"
                        move_count += 1
                    elif (
                        path_record.parent.version_number != path_record.version_number
                    ):
                        action = "UPDATED"
                    else:
                        action = "RESTORED"
                else:
                    action = "UPDATED"

            if path_record.is_current and not path_record.is_deleted:
                current_path = path_record.path

            event = {
                "id": to_global_id("DocumentPathType", path_record.id),
                "action": action,
                "path": path_record.path,
                "folder": path_record.folder,
                "timestamp": path_record.created,
                "user": path_record.creator,
                "version_number": path_record.version_number,
            }
            events.append(event)

        return {
            "events": events,
            "current_path": current_path or original_path or "",
            "original_path": original_path or "",
            "move_count": move_count,
        }

    def resolve_can_restore(self, info, corpus_id):
        """Check if user has UPDATE permission for restore operations."""
        from django.contrib.auth.models import AnonymousUser

        from opencontractserver.corpuses.models import Corpus
        from opencontractserver.types.enums import PermissionTypes
        from opencontractserver.utils.permissioning import user_has_permission_for_obj

        user = info.context.user
        if isinstance(user, AnonymousUser) or not user or not user.is_authenticated:
            return False

        # Check document permission
        has_doc_update = user_has_permission_for_obj(
            user, self, PermissionTypes.UPDATE, include_group_permissions=True
        )
        if not has_doc_update:
            return False

        # Check corpus permission
        _, corpus_pk = from_global_id(corpus_id)
        try:
            corpus = Corpus.objects.get(pk=corpus_pk)
            has_corpus_update = user_has_permission_for_obj(
                user, corpus, PermissionTypes.UPDATE, include_group_permissions=True
            )
            return has_corpus_update
        except Corpus.DoesNotExist:
            return False

    def resolve_can_view_history(self, info):
        """Check if user has READ permission for viewing history."""
        from django.contrib.auth.models import AnonymousUser

        from opencontractserver.types.enums import PermissionTypes
        from opencontractserver.utils.permissioning import user_has_permission_for_obj

        user = info.context.user

        # Public documents can be viewed by anyone
        if self.is_public:
            return True

        if isinstance(user, AnonymousUser) or not user or not user.is_authenticated:
            return False

        return user_has_permission_for_obj(
            user, self, PermissionTypes.READ, include_group_permissions=True
        )

    page_annotations = graphene.List(
        AnnotationType,
        corpus_id=graphene.ID(required=True),
        page=graphene.Int(),  # Now optional for backwards compatibility
        pages=graphene.List(graphene.Int),  # NEW: Accept multiple pages
        structural=graphene.Boolean(),
        analysis_id=graphene.ID(),
        description="Get annots for spec. page(s) using opt. queries. Either 'page' (single) or 'pages' (multiple).",
    )

    page_relationships = graphene.List(
        RelationshipType,
        corpus_id=graphene.ID(required=True),
        pages=graphene.List(graphene.Int, required=True),
        structural=graphene.Boolean(),
        analysis_id=graphene.ID(),
        description="Get relationships where source or target annotations are on the specified page(s).",
    )

    def resolve_page_annotations(
        self,
        info,
        corpus_id,
        page=None,
        pages=None,
        structural=None,
        analysis_id=None,
        extract_id=None,
    ):
        """Resolve annotations for specific page(s) using optimized queries."""
        from django.contrib.auth.models import AnonymousUser
        from graphql import GraphQLError

        from opencontractserver.annotations.query_optimizer import (
            AnnotationQueryOptimizer,
        )

        _, corpus_pk = from_global_id(corpus_id)
        analysis_pk = None
        if analysis_id:
            _, analysis_pk = from_global_id(analysis_id)
        extract_pk = None
        if extract_id:
            _, extract_pk = from_global_id(extract_id)

        # Get user from the GraphQL context
        user = info.context.user if hasattr(info.context, "user") else None

        # Check if user has permission to access this document
        if not self.is_public:
            if isinstance(user, AnonymousUser) or not user or not user.is_authenticated:
                raise GraphQLError(
                    "Permission denied: Authentication required to access private documents"
                )
            elif user != self.creator and not user.is_superuser:
                # Check if user has explicit permission
                from opencontractserver.types.enums import PermissionTypes
                from opencontractserver.utils.permissioning import (
                    user_has_permission_for_obj,
                )

                if not user_has_permission_for_obj(user, self, PermissionTypes.READ):
                    raise GraphQLError(
                        "Permission denied: You do not have access to this document"
                    )

        # Handle both single page and multiple pages
        # Priority: if 'pages' is provided, use it; otherwise fall back to 'page'
        page_list = None
        if pages is not None and len(pages) > 0:
            page_list = pages
        elif page is not None:
            page_list = [page]

        # If neither is provided, return empty list (maintain backwards compatibility)
        if page_list is None:
            return []

        return AnnotationQueryOptimizer.get_document_annotations(
            document_id=self.id,
            user=user,
            corpus_id=corpus_pk,
            pages=page_list,  # Pass list of pages
            structural=structural,
            analysis_id=analysis_pk,
            extract_id=extract_pk,
            use_cache=True,
        )

    def resolve_page_relationships(
        self,
        info,
        corpus_id,
        pages,
        structural=None,
        analysis_id=None,
        extract_id=None,
        strict_extract_mode=False,
    ):
        """Resolve relationships for specific page(s) using the optimizer."""
        from django.contrib.auth.models import AnonymousUser
        from graphql import GraphQLError

        from opencontractserver.annotations.query_optimizer import (
            RelationshipQueryOptimizer,
        )

        _, corpus_pk = from_global_id(corpus_id)
        analysis_pk = None
        if analysis_id:
            if analysis_id == "__none__":
                analysis_pk = 0  # Special case for user annotations
            else:
                _, analysis_pk = from_global_id(analysis_id)
        extract_pk = None
        if extract_id:
            _, extract_pk = from_global_id(extract_id)

        # Get user from the GraphQL context
        user = info.context.user if hasattr(info.context, "user") else None

        # Permission checks mirroring annotation resolvers
        if not self.is_public:
            if isinstance(user, AnonymousUser) or not user or not user.is_authenticated:
                raise GraphQLError(
                    "Permission denied: Authentication required to access private documents"
                )
            elif user != self.creator and not user.is_superuser:
                from opencontractserver.types.enums import PermissionTypes
                from opencontractserver.utils.permissioning import (
                    user_has_permission_for_obj,
                )

                if not user_has_permission_for_obj(user, self, PermissionTypes.READ):
                    raise GraphQLError(
                        "Permission denied: You do not have access to this document"
                    )

        return RelationshipQueryOptimizer.get_document_relationships(
            document_id=self.id,
            user=user,
            corpus_id=corpus_pk,
            pages=pages if pages else None,
            structural=structural,
            analysis_id=analysis_pk,
            extract_id=extract_pk,
            strict_extract_mode=strict_extract_mode,
            use_cache=True,
        )

    relationship_summary = graphene.Field(
        GenericScalar,
        corpus_id=graphene.ID(required=True),
        description="Get relationship summary statistics for this document and corpus (MV-backed).",
    )

    # Extract-specific summary
    extract_annotation_summary = graphene.Field(
        GenericScalar,
        extract_id=graphene.ID(required=True),
        description="Get summary of annotations used in specific extract.",
    )

    def resolve_relationship_summary(self, info, corpus_id):
        from django.contrib.auth.models import AnonymousUser
        from graphql import GraphQLError

        from opencontractserver.annotations.query_optimizer import (
            RelationshipQueryOptimizer,
        )

        # Permissions mirroring annotation summary style
        user = info.context.user if hasattr(info.context, "user") else None

        if not self.is_public:
            if isinstance(user, AnonymousUser) or not user or not user.is_authenticated:
                raise GraphQLError(
                    "Permission denied: Authentication required to access private documents"
                )
            elif user != self.creator and not user.is_superuser:
                from opencontractserver.types.enums import PermissionTypes
                from opencontractserver.utils.permissioning import (
                    user_has_permission_for_obj,
                )

                if not user_has_permission_for_obj(user, self, PermissionTypes.READ):
                    raise GraphQLError(
                        "Permission denied: You do not have access to this document"
                    )

        _, corpus_pk = from_global_id(corpus_id)
        summary = RelationshipQueryOptimizer.get_relationship_summary(
            document_id=self.id, corpus_id=corpus_pk, user=user
        )
        return summary

    def resolve_extract_annotation_summary(self, info, extract_id):
        """Get summary of annotations in extract."""
        from django.contrib.auth.models import AnonymousUser
        from graphql import GraphQLError

        from opencontractserver.annotations.query_optimizer import (
            AnnotationQueryOptimizer,
        )

        user = info.context.user if hasattr(info.context, "user") else None
        _, extract_pk = from_global_id(extract_id)

        # Check if user has permission to access this document
        if not self.is_public:
            if isinstance(user, AnonymousUser) or not user or not user.is_authenticated:
                raise GraphQLError(
                    "Permission denied: Authentication required to access private documents"
                )
            elif user != self.creator and not user.is_superuser:
                from opencontractserver.types.enums import PermissionTypes
                from opencontractserver.utils.permissioning import (
                    user_has_permission_for_obj,
                )

                if not user_has_permission_for_obj(user, self, PermissionTypes.READ):
                    raise GraphQLError(
                        "Permission denied: You do not have access to this document"
                    )

        return AnnotationQueryOptimizer.get_extract_annotation_summary(
            document_id=self.id, extract_id=extract_pk, user=user, use_cache=True
        )

    # Folder assignment within a corpus
    folder_in_corpus = graphene.Field(
        lambda: CorpusFolderType,
        corpus_id=graphene.ID(required=True),
        description="Get the folder this document is in within a specific corpus (null = root)",
    )

    def resolve_folder_in_corpus(self, info, corpus_id):
        """Get folder assignment for this document in a specific corpus."""
        from opencontractserver.corpuses.models import CorpusDocumentFolder

        _, corpus_pk = from_global_id(corpus_id)
        try:
            assignment = CorpusDocumentFolder.objects.get(
                document_id=self.id, corpus_id=corpus_pk
            )
            return assignment.folder
        except CorpusDocumentFolder.DoesNotExist:
            return None

    class Meta:
        model = Document
        interfaces = [relay.Node]
        exclude = ("embedding",)
        connection_class = CountableConnection

    @classmethod
    def get_queryset(cls, queryset, info):
        if issubclass(type(queryset), QuerySet):
            return queryset.visible_to_user(info.context.user)
        elif "RelatedManager" in str(type(queryset)):
            # https://stackoverflow.com/questions/11320702/import-relatedmanager-from-django-db-models-fields-related
            return queryset.all().visible_to_user(info.context.user)
        else:
            return queryset


# Explicit Connection class for DocumentType to use in relay.ConnectionField
class DocumentTypeConnection(CountableConnection):
    """Connection class for DocumentType used in Corpus.documents field."""

    class Meta:
        node = DocumentType


# ---------------- Engagement Metrics Types (Epic #565) ----------------
class CorpusEngagementMetricsType(graphene.ObjectType):
    """
    GraphQL type for corpus engagement metrics.

    This type does NOT use AnnotatePermissionsForReadMixin because
    engagement metrics are read-only and permissions are checked on
    the parent Corpus object.

    Epic: #565 - Corpus Engagement Metrics & Analytics
    Issue: #568 - Create GraphQL queries for engagement metrics and leaderboards
    """

    # Thread counts
    total_threads = graphene.Int(
        description="Total number of discussion threads in this corpus"
    )
    active_threads = graphene.Int(
        description="Number of active (not locked/deleted) threads"
    )

    # Message counts
    total_messages = graphene.Int(
        description="Total number of messages across all threads"
    )
    messages_last_7_days = graphene.Int(
        description="Number of messages posted in the last 7 days"
    )
    messages_last_30_days = graphene.Int(
        description="Number of messages posted in the last 30 days"
    )

    # Contributor counts
    unique_contributors = graphene.Int(
        description="Total number of unique users who have posted messages"
    )
    active_contributors_30_days = graphene.Int(
        description="Number of users who posted in the last 30 days"
    )

    # Engagement metrics
    total_upvotes = graphene.Int(
        description="Total upvotes across all messages in this corpus"
    )
    avg_messages_per_thread = graphene.Float(
        description="Average number of messages per thread"
    )

    # Metadata
    last_updated = graphene.DateTime(
        description="Timestamp when metrics were last calculated"
    )


class CorpusFolderType(AnnotatePermissionsForReadMixin, DjangoObjectType):
    """
    GraphQL type for corpus folders.
    Folders inherit permissions from their parent corpus.
    """

    path = graphene.String(description="Full path from root to this folder")
    document_count = graphene.Int(
        description="Number of documents directly in this folder"
    )
    descendant_document_count = graphene.Int(
        description="Number of documents in this folder and all subfolders"
    )
    children = graphene.List(
        lambda: CorpusFolderType, description="Immediate child folders"
    )

    def resolve_path(self, info):
        """Get full path from root to this folder."""
        return self.get_path()

    def resolve_document_count(self, info):
        """Get count of documents directly in this folder."""
        return self.get_document_count()

    def resolve_descendant_document_count(self, info):
        """Get count of documents in this folder and all subfolders."""
        return self.get_descendant_document_count()

    def resolve_children(self, info):
        """Get immediate child folders."""
        return self.children.all().visible_to_user(info.context.user)

    class Meta:
        model = CorpusFolder
        interfaces = [relay.Node]
        connection_class = CountableConnection

    @classmethod
    def get_queryset(cls, queryset, info):
        """Filter folders to only those the user can see (via corpus permissions)."""
        if issubclass(type(queryset), QuerySet):
            return queryset.visible_to_user(info.context.user)
        elif "RelatedManager" in str(type(queryset)):
            return queryset.all().visible_to_user(info.context.user)
        else:
            return queryset


class CorpusType(AnnotatePermissionsForReadMixin, DjangoObjectType):
    all_annotation_summaries = graphene.List(
        AnnotationType,
        analysis_id=graphene.ID(),
        label_types=graphene.List(LabelTypeEnum),
    )

    # Explicit documents field to use custom resolver via DocumentPath
    # This is necessary because Corpus model no longer has M2M documents field
    # (corpus isolation moved to DocumentPath-based relationships)
    documents = relay.ConnectionField(
        DocumentTypeConnection, description="Documents in this corpus via DocumentPath"
    )

    def resolve_documents(self, info):
        """
        Custom resolver for documents field that uses DocumentPath.
        Returns documents with active paths in this corpus.
        """
        user = getattr(info.context, "user", None)
        # Use the Corpus method that queries via DocumentPath
        documents = self.get_documents()
        # Apply visibility filtering
        from opencontractserver.documents.models import Document

        if hasattr(Document.objects, "visible_to_user"):
            return Document.objects.filter(
                id__in=documents.values_list("id", flat=True)
            ).visible_to_user(user)
        return documents

    def resolve_annotations(self, info):
        """
        Custom resolver for annotations field that properly computes permissions.
        Uses AnnotationQueryOptimizer to ensure permission flags are set.
        """
        from opencontractserver.annotations.models import Annotation
        from opencontractserver.annotations.query_optimizer import (
            AnnotationQueryOptimizer,
        )

        user = getattr(info.context, "user", None)

        # Get all document IDs in this corpus via DocumentPath
        document_ids = self.get_documents().values_list("id", flat=True)

        # Collect annotations for all documents with proper permission computation
        all_annotations = Annotation.objects.none()
        for doc_id in document_ids:
            annotations = AnnotationQueryOptimizer.get_document_annotations(
                document_id=doc_id, user=user, corpus_id=self.id, use_cache=True
            )
            all_annotations = all_annotations | annotations

        return all_annotations.distinct()

    def resolve_all_annotation_summaries(self, info, **kwargs):

        analysis_id = kwargs.get("analysis_id", None)
        label_types = kwargs.get("label_types", None)

        annotation_set = self.annotations.all()

        if label_types and isinstance(label_types, list):
            logger.info(f"Filter to label_types: {label_types}")
            annotation_set = annotation_set.filter(
                annotation_label__label_type__in=[
                    label_type.value for label_type in label_types
                ]
            )

        if analysis_id:
            try:
                analysis_pk = from_global_id(analysis_id)[1]
                annotation_set = annotation_set.filter(analysis_id=analysis_pk)
            except Exception as e:
                logger.warning(
                    f"Failed resolving analysis pk for corpus {self.id} with input graphene id"
                    f" {analysis_id}: {e}"
                )

        return annotation_set

    applied_analyzer_ids = graphene.List(graphene.String)

    def resolve_applied_analyzer_ids(self, info):
        return list(
            self.analyses.all().values_list("analyzer_id", flat=True).distinct()
        )

    def resolve_icon(self, info):
        return "" if not self.icon else info.context.build_absolute_uri(self.icon.url)

    # File link resolver for markdown description
    def resolve_md_description(self, info):
        return (
            ""
            if not self.md_description
            else info.context.build_absolute_uri(self.md_description.url)
        )

    # Optional list of description revisions
    description_revisions = graphene.List(lambda: CorpusDescriptionRevisionType)

    def resolve_description_revisions(self, info):
        # Returns all revisions, ordered by version asc by default from model ordering
        return self.revisions.all() if hasattr(self, "revisions") else []

    # Folder structure
    folders = graphene.List(
        CorpusFolderType, description="All folders in this corpus (flat list)"
    )

    def resolve_folders(self, info):
        """Get all folders in this corpus with permission filtering."""
        return self.folders.all().visible_to_user(info.context.user)

    # Engagement metrics (Epic #565)
    engagement_metrics = graphene.Field(CorpusEngagementMetricsType)

    def resolve_engagement_metrics(self, info):
        """
        Resolve engagement metrics for this corpus.

        Returns None if metrics haven't been calculated yet.

        Epic: #565 - Corpus Engagement Metrics & Analytics
        Issue: #568 - Create GraphQL queries for engagement metrics and leaderboards
        """
        try:
            return self.engagement_metrics
        except CorpusEngagementMetrics.DoesNotExist:
            return None

    class Meta:
        model = Corpus
        interfaces = [relay.Node]
        connection_class = CountableConnection

    @classmethod
    def get_queryset(cls, queryset, info):
        if issubclass(type(queryset), QuerySet):
            return queryset.visible_to_user(info.context.user)
        elif "RelatedManager" in str(type(queryset)):
            # https://stackoverflow.com/questions/11320702/import-relatedmanager-from-django-db-models-fields-related
            return queryset.all().visible_to_user(info.context.user)
        else:
            return queryset


class CorpusActionType(AnnotatePermissionsForReadMixin, DjangoObjectType):
    class Meta:
        model = CorpusAction
        interfaces = [relay.Node]
        connection_class = CountableConnection
        filter_fields = {
            "id": ["exact"],
            "name": ["exact", "icontains", "istartswith"],
            "corpus__id": ["exact"],
            "fieldset__id": ["exact"],
            "analyzer__id": ["exact"],
            "trigger": ["exact"],
            "creator__id": ["exact"],
        }


class UserExportType(AnnotatePermissionsForReadMixin, DjangoObjectType):
    def resolve_file(self, info):
        return "" if not self.file else info.context.build_absolute_uri(self.file.url)

    class Meta:
        model = UserExport
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


class UserImportType(AnnotatePermissionsForReadMixin, DjangoObjectType):
    def resolve_zip(self, info):
        return "" if not self.file else info.context.build_absolute_uri(self.zip.url)

    class Meta:
        model = UserImport
        interfaces = [relay.Node]
        connection_class = CountableConnection


class AnalyzerType(AnnotatePermissionsForReadMixin, DjangoObjectType):
    analyzer_id = graphene.String()

    def resolve_analyzer_id(self, info):
        return self.id.__str__()

    input_schema = GenericScalar(
        description="JSONSchema describing the analyzer's expected input if provided."
    )

    manifest = GenericScalar()

    full_label_list = graphene.List(AnnotationLabelType)

    def resolve_full_label_list(self, info):
        return self.annotation_labels.all()

    def resolve_icon(self, info):
        return "" if not self.icon else info.context.build_absolute_uri(self.icon.url)

    class Meta:
        model = Analyzer
        interfaces = [relay.Node]
        connection_class = CountableConnection


class GremlinEngineType_READ(AnnotatePermissionsForReadMixin, DjangoObjectType):
    class Meta:
        model = GremlinEngine
        exclude = ("api_key",)
        interfaces = [relay.Node]
        connection_class = CountableConnection


class GremlinEngineType_WRITE(AnnotatePermissionsForReadMixin, DjangoObjectType):
    class Meta:
        model = GremlinEngine
        interfaces = [relay.Node]
        connection_class = CountableConnection


class AnalysisType(AnnotatePermissionsForReadMixin, DjangoObjectType):
    full_annotation_list = graphene.List(
        AnnotationType,
        document_id=graphene.ID(),
    )

    def resolve_full_annotation_list(self, info, document_id=None):
        from opencontractserver.annotations.query_optimizer import (
            AnalysisQueryOptimizer,
        )

        if document_id is not None:
            document_pk = int(from_global_id(document_id)[1])
        else:
            document_pk = None

        return AnalysisQueryOptimizer.get_analysis_annotations(
            self, info.context.user, document_id=document_pk
        )

    @classmethod
    def get_node(cls, info, id):
        """
        Override the default node resolution to apply permission checks.
        """
        from opencontractserver.annotations.query_optimizer import (
            AnalysisQueryOptimizer,
        )

        has_perm, analysis = AnalysisQueryOptimizer.check_analysis_permission(
            info.context.user, int(id)
        )
        return analysis if has_perm else None

    class Meta:
        model = Analysis
        interfaces = [relay.Node]
        connection_class = CountableConnection


class ColumnType(AnnotatePermissionsForReadMixin, DjangoObjectType):
    validation_config = GenericScalar()
    default_value = GenericScalar()

    class Meta:
        model = Column
        interfaces = [relay.Node]
        connection_class = CountableConnection


class FieldsetType(AnnotatePermissionsForReadMixin, DjangoObjectType):
    in_use = graphene.Boolean(
        description="True if the fieldset is used in any extract that has started."
    )
    full_column_list = graphene.List(ColumnType)

    class Meta:
        model = Fieldset
        interfaces = [relay.Node]
        connection_class = CountableConnection

    def resolve_in_use(self, info) -> bool:
        """
        Returns True if the fieldset is used in any extract that has started.
        """
        return self.extracts.filter(started__isnull=False).exists()

    def resolve_full_column_list(self, info):
        return self.columns.all()


class DatacellType(AnnotatePermissionsForReadMixin, DjangoObjectType):
    data = GenericScalar()
    corrected_data = GenericScalar()
    full_source_list = graphene.List(AnnotationType)

    def resolve_full_source_list(self, info):
        return self.sources.all()

    class Meta:
        model = Datacell
        interfaces = [relay.Node]
        connection_class = CountableConnection


class ExtractType(AnnotatePermissionsForReadMixin, DjangoObjectType):
    full_datacell_list = graphene.List(DatacellType)
    full_document_list = graphene.List(DocumentType)

    @classmethod
    def get_node(cls, info, id):
        """
        Override the default node resolution to apply permission checks.
        """
        from opencontractserver.annotations.query_optimizer import ExtractQueryOptimizer

        has_perm, extract = ExtractQueryOptimizer.check_extract_permission(
            info.context.user, int(id)
        )
        return extract if has_perm else None

    class Meta:
        model = Extract
        interfaces = [relay.Node]
        connection_class = CountableConnection

    def resolve_full_datacell_list(self, info):
        from opencontractserver.annotations.query_optimizer import ExtractQueryOptimizer

        return ExtractQueryOptimizer.get_extract_datacells(
            self, info.context.user, document_id=None
        )

    def resolve_full_document_list(self, info):
        from opencontractserver.types.enums import PermissionTypes
        from opencontractserver.utils.permissioning import user_has_permission_for_obj

        # Filter to only documents user can read
        if info.context.user.is_superuser:
            return self.documents.all()

        readable_docs = []
        for doc in self.documents.all():
            if user_has_permission_for_obj(
                info.context.user,
                doc,
                PermissionTypes.READ,
                include_group_permissions=True,
            ):
                readable_docs.append(doc)
        return readable_docs


class CorpusQueryType(AnnotatePermissionsForReadMixin, DjangoObjectType):
    full_source_list = graphene.List(AnnotationType)

    def resolve_full_source_list(self, info):
        return self.sources.all()

    class Meta:
        model = CorpusQuery
        interfaces = [relay.Node]
        connection_class = CountableConnection


class DocumentAnalysisRowType(AnnotatePermissionsForReadMixin, DjangoObjectType):
    class Meta:
        model = DocumentAnalysisRow
        interfaces = [relay.Node]
        connection_class = CountableConnection


class DocumentCorpusActionsType(graphene.ObjectType):
    corpus_actions = graphene.List(CorpusActionType)
    extracts = graphene.List(ExtractType)
    analysis_rows = graphene.List(DocumentAnalysisRowType)


class CorpusStatsType(graphene.ObjectType):
    total_docs = graphene.Int()
    total_annotations = graphene.Int()
    total_comments = graphene.Int()
    total_analyses = graphene.Int()
    total_extracts = graphene.Int()
    total_threads = graphene.Int()


class MentionedResourceType(graphene.ObjectType):
    """
    Represents a corpus or document mentioned in a message using @ syntax.

    Examples:
      @corpus:legal-contracts
      @document:contract-template
      @corpus:legal-contracts/document:contract-template

    Permission-safe: Only returns resources visible to the requesting user.
    """

    type = graphene.String(
        required=True, description='Resource type: "corpus" or "document"'
    )
    id = graphene.ID(required=True, description="Global ID of the resource")
    slug = graphene.String(required=True, description="URL-safe slug of the resource")
    title = graphene.String(required=True, description="Display title of the resource")
    url = graphene.String(
        required=True, description="Frontend URL path to navigate to the resource"
    )
    corpus = graphene.Field(
        lambda: MentionedResourceType,
        description="Parent corpus context (for documents within a corpus)",
    )


class MessageType(AnnotatePermissionsForReadMixin, DjangoObjectType):

    data = GenericScalar()
    agent_type = graphene.Field(
        AgentTypeEnum, description="Type of agent that generated this message"
    )
    agent_configuration = graphene.Field(
        lambda: AgentConfigurationType,
        description="Agent configuration that generated this message",
    )
    mentioned_resources = graphene.List(
        MentionedResourceType,
        description="Corpuses and documents mentioned in this message using @ syntax. "
        "Only includes resources visible to the requesting user.",
    )

    def resolve_agent_type(self, info):
        """Convert string agent_type from model to enum."""
        if self.agent_type:
            return AgentTypeEnum.get(self.agent_type)
        return None

    def resolve_agent_configuration(self, info):
        """Resolve agent_configuration field."""
        return self.agent_configuration

    def resolve_mentioned_resources(self, info):
        """
        Parse message content for @mentions and return structured resource references.

        Patterns:
          @corpus:slug → Corpus
          @document:slug → Document
          @corpus:corpus-slug/document:doc-slug → Document in Corpus

        SECURITY: Uses .visible_to_user() to enforce permissions.
        Mentions to inaccessible resources are silently ignored.
        """
        import re

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
                    # Check if document is actually in this corpus
                    if corpus in document.corpus_set.all():
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

                # Try to get corpus context (documents can be in multiple corpuses)
                corpus = (
                    document.corpus_set.first()
                    if document.corpus_set.exists()
                    else None
                )

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

    def resolve_all_messages(self, info):
        return self.chat_messages.all()

    def resolve_conversation_type(self, info):
        """Convert string conversation_type from model to enum."""
        if self.conversation_type:
            return ConversationTypeEnum.get(self.conversation_type)
        return None

    @classmethod
    def get_node(cls, info, id):
        """
        Override the default node resolution to apply permission checks.
        Anonymous users can only see public conversations.
        Authenticated users can see public, their own, or explicitly shared.
        """
        import logging

        logger = logging.getLogger(__name__)

        logger.info(f"🔍 ConversationType.get_node called with id: {id}")
        logger.info(f"   User: {info.context.user}")
        logger.info(f"   User type: {type(info.context.user)}")
        is_auth = (
            info.context.user.is_authenticated
            if hasattr(info.context.user, "is_authenticated")
            else "N/A"
        )
        logger.info(f"   Is authenticated: {is_auth}")

        try:
            queryset = Conversation.objects.visible_to_user(info.context.user)
            logger.info(f"   Queryset count: {queryset.count()}")

            conversation = queryset.get(pk=id)
            logger.info(
                f"   ✅ Found conversation: {conversation.id} - {conversation.title}"
            )
            return conversation
        except Conversation.DoesNotExist:
            logger.warning(f"   ❌ Conversation {id} not found or not visible to user")
            return None
        except Exception as e:
            logger.error(f"   ❌ Error in get_node: {e}", exc_info=True)
            return None

    class Meta:
        model = Conversation
        interfaces = [relay.Node]
        connection_class = CountableConnection

    @classmethod
    def get_queryset(cls, queryset, info):
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


class UserFeedbackType(AnnotatePermissionsForReadMixin, DjangoObjectType):
    class Meta:
        model = UserFeedback
        interfaces = [relay.Node]
        connection_class = CountableConnection

    # https://docs.graphene-python.org/projects/django/en/latest/queries/#default-queryset
    @classmethod
    def get_queryset(cls, queryset, info):
        if issubclass(type(queryset), QuerySet):
            return queryset.visible_to_user(info.context.user)
        elif "RelatedManager" in str(type(queryset)):
            # https://stackoverflow.com/questions/11320702/import-relatedmanager-from-django-db-models-fields-related
            return queryset.all().visible_to_user(info.context.user)
        else:
            return queryset


class FileTypeEnum(graphene.Enum):
    """Graphene enum for FileTypeEnum."""

    PDF = BackendFileTypeEnum.PDF.value
    TXT = BackendFileTypeEnum.TXT.value
    DOCX = BackendFileTypeEnum.DOCX.value
    # HTML has been removed as we don't support it


class PipelineComponentType(graphene.ObjectType):
    """Graphene type for pipeline components."""

    name = graphene.String(description="Name of the component class.")
    class_name = graphene.String(description="Full Python path to the component class.")
    module_name = graphene.String(description="Name of the module the component is in.")
    title = graphene.String(description="Title of the component.")
    description = graphene.String(description="Description of the component.")
    author = graphene.String(description="Author of the component.")
    dependencies = graphene.List(
        graphene.String, description="List of dependencies required by the component."
    )
    vector_size = graphene.Int(description="Vector size for embedders.", required=False)
    supported_file_types = graphene.List(
        FileTypeEnum, description="List of supported file types."
    )
    component_type = graphene.String(
        description="Type of the component (parser, embedder, or thumbnailer)."
    )
    input_schema = GenericScalar(
        description="JSONSchema schema for inputs supported from user (experimental - not fully implemented)."
    )


class PipelineComponentsType(graphene.ObjectType):
    """Graphene type for grouping pipeline components."""

    parsers = graphene.List(
        PipelineComponentType, description="List of available parsers."
    )
    embedders = graphene.List(
        PipelineComponentType, description="List of available embedders."
    )
    thumbnailers = graphene.List(
        PipelineComponentType, description="List of available thumbnail generators."
    )
    post_processors = graphene.List(
        PipelineComponentType, description="List of available post-processors."
    )


def resolve_pipeline_components(self, info, mimetype=None):
    from opencontractserver.pipeline.base.file_types import FileTypeEnum

    # Convert GraphQL string to backend enum
    backend_enum = None
    if mimetype:
        try:
            backend_enum = FileTypeEnum[
                mimetype
            ]  # This should work if the enum values match
        except KeyError:
            pass

    components = get_components_by_mimetype(backend_enum)
    return components


# ---------------- CorpusDescriptionRevisionType ----------------
class CorpusDescriptionRevisionType(AnnotatePermissionsForReadMixin, DjangoObjectType):
    """GraphQL type for corpus description revisions."""

    class Meta:
        model = CorpusDescriptionRevision
        interfaces = [relay.Node]
        connection_class = CountableConnection


class DocumentSummaryRevisionType(AnnotatePermissionsForReadMixin, DjangoObjectType):
    """GraphQL type for document summary revisions."""

    class Meta:
        model = DocumentSummaryRevision
        interfaces = [relay.Node]
        connection_class = CountableConnection


# ---------------- Badge System Types ----------------
class BadgeType(AnnotatePermissionsForReadMixin, DjangoObjectType):
    """GraphQL type for badges."""

    class Meta:
        from opencontractserver.badges.models import Badge

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
        from opencontractserver.badges.models import UserBadge

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


# ---------------- Agent Configuration Types ----------------
class AgentConfigurationType(AnnotatePermissionsForReadMixin, DjangoObjectType):
    """GraphQL type for agent configurations."""

    class Meta:
        from opencontractserver.agents.models import AgentConfiguration

        model = AgentConfiguration
        interfaces = [relay.Node]
        connection_class = CountableConnection
        fields = (
            "id",
            "name",
            "description",
            "system_instructions",
            "available_tools",
            "permission_required_tools",
            "badge_config",
            "avatar_url",
            "scope",
            "corpus",
            "is_active",
            "creator",
            "is_public",
            "created",
            "modified",
        )
        filter_fields = {
            "scope": ["exact"],
            "is_active": ["exact"],
            "corpus": ["exact"],
        }


class NotificationType(DjangoObjectType):
    """GraphQL type for notifications."""

    class Meta:
        from opencontractserver.notifications.models import Notification

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

    def resolve_message(self, info):
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
        accessible_messages = ChatMessage.objects.filter(
            id=self.message.id
        ).visible_to_user(user)

        if accessible_messages.exists():
            return self.message
        return None

    def resolve_conversation(self, info):
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
        accessible_conversations = Conversation.objects.filter(
            id=self.conversation.id
        ).visible_to_user(user)

        if accessible_conversations.exists():
            return self.conversation
        return None

    def resolve_data(self, info):
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
