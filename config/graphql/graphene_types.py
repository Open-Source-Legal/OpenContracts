import logging

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
    Relationship,
)
from opencontractserver.conversations.models import ChatMessage, Conversation
from opencontractserver.corpuses.models import Corpus, CorpusAction, CorpusQuery
from opencontractserver.documents.models import (
    Document,
    DocumentAnalysisRow,
    DocumentRelationship,
)
from opencontractserver.extracts.models import Column, Datacell, Extract, Fieldset
from opencontractserver.feedback.models import UserFeedback
from opencontractserver.pipeline.base.file_types import (
    FileTypeEnum as FileTypeEnumModel,
)
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

    all_source_node_in_relationship = graphene.List(lambda: RelationshipType)

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
    METADATA_LABEL = "METADATA_LABEL"
    SPAN_LABEL = "SPAN_LABEL"


class AnnotationSummaryType(graphene.ObjectType):
    id: graphene.String()  # type: ignore
    label = graphene.String()
    type = LabelTypeEnum()
    raw_text = graphene.String()


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
    metadata_label_count = graphene.Int(description="Count of metadata labels")

    def resolve_doc_label_count(self, info):
        return self.annotation_labels.filter(label_type="DOC_TYPE_LABEL").count()

    def resolve_span_label_count(self, info):
        return self.annotation_labels.filter(label_type="SPAN_LABEL").count()

    def resolve_token_label_count(self, info):
        return self.annotation_labels.filter(label_type="TOKEN_LABEL").count()

    def resolve_metadata_label_count(self, info):
        return self.annotation_labels.filter(label_type="METADATA_LABEL").count()

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


class DocumentType(AnnotatePermissionsForReadMixin, DjangoObjectType):
    def resolve_pdf_file(self, info):
        return (
            ""
            if not self.pdf_file
            else info.context.build_absolute_uri(self.pdf_file.url)
        )

    def resolve_icon(self, info):
        return "" if not self.icon else info.context.build_absolute_uri(self.icon.url)

    def resolve_txt_extract_file(self, info):
        return (
            ""
            if not self.txt_extract_file
            else info.context.build_absolute_uri(self.txt_extract_file.url)
        )

    def resolve_md_summary_file(self, info):
        return (
            ""
            if not self.md_summary_file
            else info.context.build_absolute_uri(self.md_summary_file.url)
        )

    def resolve_pawls_parse_file(self, info):
        return (
            ""
            if not self.pawls_parse_file
            else info.context.build_absolute_uri(self.pawls_parse_file.url)
        )

    all_structural_annotations = graphene.List(AnnotationType)

    def resolve_all_structural_annotations(self, info):
        return self.doc_annotations.filter(structural=True).distinct()

    # Updated field and resolver for all annotations with enhanced filtering
    all_annotations = graphene.List(
        AnnotationType,
        corpus_id=graphene.ID(required=True),
        analysis_id=graphene.ID(),
        is_structural=graphene.Boolean(),
    )

    def resolve_all_annotations(
        self, info, corpus_id, analysis_id=None, is_structural=None
    ):
        try:
            corpus_pk = from_global_id(corpus_id)[1]
            annotations = self.doc_annotations.filter(corpus_id=corpus_pk)

            if analysis_id is not None:
                if analysis_id == "__none__":
                    annotations = annotations.filter(analysis__isnull=True)
                else:
                    analysis_pk = from_global_id(analysis_id)[1]
                    annotations = annotations.filter(analysis_id=analysis_pk)

            if is_structural is not None:
                annotations = annotations.filter(structural=is_structural)

            return annotations.distinct()
        except Exception as e:
            logger.warning(
                f"Failed resolving query for document {self.id} with input: corpus_id={corpus_id}, "
                f"analysis_id={analysis_id}, is_structural={is_structural}. Error: {e}"
            )
            return []

    # New field and resolver for all relationships
    all_relationships = graphene.List(
        RelationshipType,
        corpus_id=graphene.ID(required=True),
        analysis_id=graphene.ID(),
    )

    def resolve_all_relationships(self, info, corpus_id, analysis_id=None):
        try:
            # Want to limit to strucutural relationships or corpus relationships
            corpus_pk = from_global_id(corpus_id)[1]
            relationships = self.relationships.filter(
                Q(corpus_id=corpus_pk) | Q(structural=True)
            )

            if analysis_id == "__none__":
                relationships = relationships.filter(analysis__isnull=True)
            elif analysis_id is not None:
                analysis_pk = from_global_id(analysis_id)[1]
                relationships = relationships.filter(analysis_id=analysis_pk)

            return relationships.distinct()
        except Exception as e:
            logger.warning(
                f"Failed resolving relationships query for document {self.id} with input: corpus_id={corpus_id}, "
                f"analysis_id={analysis_id}. Error: {e}"
            )
            return []

    # New field for document relationships
    all_doc_relationships = graphene.List(
        DocumentRelationshipType,
        corpus_id=graphene.ID(required=True),
    )

    def resolve_all_doc_relationships(self, info, corpus_id):
        try:
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
        corpus_id=graphene.ID(required=True),
    )

    def resolve_all_notes(self, info, corpus_id: str):
        """
        Return the set of Note objects related to this Document instance that the user can see,
        filtered by corpus_id. Uses the model's built-in permission filtering for consistency.
        """
        from opencontractserver.annotations.models import Note

        user = info.context.user
        corpus_pk = from_global_id(corpus_id)[1]

        # Use the document's related manager to get notes, then filter by corpus and permissions
        document_notes = self.notes.filter(corpus_id=corpus_pk)

        # Apply permission filtering using the model's visible_to_user method
        return Note.objects.visible_to_user(user).filter(
            id__in=document_notes.values_list("id", flat=True)
        )

    class Meta:
        model = Document
        interfaces = [relay.Node]
        exclude = ("embedding", "description_embedding")
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


class UserImportType(AnnotatePermissionsForReadMixin, DjangoObjectType):
    def resolve_zip(self, info):
        return "" if not self.file else info.context.build_absolute_uri(self.zip.url)

    class Meta:
        model = UserImport
        interfaces = [relay.Node]
        connection_class = CountableConnection


class UserExportType(AnnotatePermissionsForReadMixin, DjangoObjectType):
    def resolve_file(self, info):
        return "" if not self.file else info.context.build_absolute_uri(self.file.url)

    class Meta:
        model = UserExport
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

        results = self.annotations.all()
        if document_id is not None:
            document_pk = from_global_id(document_id)[1]
            logger.info(
                f"Resolve full annotations for analysis {self.id} with doc {document_pk}"
            )
            results = results.filter(document_id=document_pk)

        return results

    class Meta:
        model = Analysis
        interfaces = [relay.Node]
        connection_class = CountableConnection


class ColumnType(AnnotatePermissionsForReadMixin, DjangoObjectType):
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

    class Meta:
        model = Extract
        interfaces = [relay.Node]
        connection_class = CountableConnection

    def resolve_full_datacell_list(self, info):
        return self.extracted_datacells.all()

    def resolve_full_document_list(self, info):
        return self.documents.all()


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

    class Meta:
        model = ChatMessage
        interfaces = [relay.Node]
        connection_class = CountableConnection


class ConversationType(AnnotatePermissionsForReadMixin, DjangoObjectType):

    all_messages = graphene.List(MessageType)

    def resolve_all_messages(self, info):
        return self.chat_messages.all()

    class Meta:
        model = Conversation
        interfaces = [relay.Node]
        connection_class = CountableConnection


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

    PDF = FileTypeEnumModel.PDF.value
    TXT = FileTypeEnumModel.TXT.value
    DOCX = FileTypeEnumModel.DOCX.value
    # Add more file types as needed


class PipelineComponentType(graphene.ObjectType):
    """Graphene type for pipeline components."""

    name = graphene.String(description="Name of the component class.")
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

    post_processors = graphene.List(
        PipelineComponentType, description="List of available post-processors."
    )
