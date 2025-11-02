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
    CorpusQuery,
)
from opencontractserver.documents.models import (
    Document,
    DocumentAnalysisRow,
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


class CorpusType(AnnotatePermissionsForReadMixin, DjangoObjectType):
    all_annotation_summaries = graphene.List(
        AnnotationType,
        analysis_id=graphene.ID(),
        label_types=graphene.List(LabelTypeEnum),
    )

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

        # Get all document IDs in this corpus
        document_ids = self.documents.values_list("id", flat=True)

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


class MessageType(AnnotatePermissionsForReadMixin, DjangoObjectType):

    data = GenericScalar()
    agent_type = graphene.Field(
        AgentTypeEnum, description="Type of agent that generated this message"
    )

    def resolve_agent_type(self, info):
        """Convert string agent_type from model to enum."""
        if self.agent_type:
            return AgentTypeEnum.get(self.agent_type)
        return None

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
