"""GraphQL type definitions for annotation, relationship, label, and note types."""

from typing import Any

import graphene
from django.db.models import QuerySet
from graphene import relay
from graphene.types.generic import GenericScalar
from graphene_django import DjangoObjectType
from graphene_django.filter import DjangoFilterConnectionField

from config.graphql.base import CountableConnection
from config.graphql.base_types import build_flat_tree
from config.graphql.filters import AnnotationFilter, LabelFilter
from config.graphql.permissioning.permission_annotator.mixins import (
    AnnotatePermissionsForReadMixin,
)
from opencontractserver.annotations.models import (
    Annotation,
    AnnotationLabel,
    LabelSet,
    Note,
    NoteRevision,
    Relationship,
)


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
    annotation_type = graphene.String(
        description="Annotation type (e.g. TOKEN_LABEL, SPAN_LABEL). "
        "Returns raw DB value to avoid enum serialization errors on invalid data.",
    )
    feedback_count = graphene.Int(description="Count of user feedback")
    content_modalities = graphene.List(
        graphene.String,
        description="Content modalities present in this annotation: TEXT, IMAGE, etc.",
    )

    def resolve_document(self, info) -> Any:
        """Return the document, resolving via structural_set for structural annotations."""
        if self.document_id:
            return self.document
        # Structural annotations have document=NULL; resolve via structural_set
        if self.structural_set_id:
            structural_set = self.structural_set
            if structural_set is not None:
                # Use prefetched documents if available (evaluates prefetch cache)
                prefetched = list(structural_set.documents.all())
                if prefetched:
                    return prefetched[0]
            # Fallback to DB query if not prefetched (avoids circular import
            # with documents.models at module level)
            from opencontractserver.documents.models import Document

            return Document.objects.filter(
                structural_annotation_set_id=self.structural_set_id
            ).first()
        return None

    def resolve_annotation_type(self, info) -> Any:
        """Return annotation_type as a plain string to tolerate invalid DB values."""
        return self.annotation_type or ""

    def resolve_content_modalities(self, info) -> Any:
        """Return content modalities list from model."""
        return self.content_modalities or []

    all_source_node_in_relationship = graphene.List(lambda: RelationshipType)

    def resolve_feedback_count(self, info) -> int:
        # If feedback_count was annotated on the queryset, use it
        if hasattr(self, "feedback_count"):
            return self.feedback_count
        # Otherwise, count it (but this triggers N+1)
        return self.user_feedback.count()

    def resolve_all_source_node_in_relationship(self, info) -> QuerySet[Relationship]:
        return self.source_node_in_relationships.all()

    all_target_node_in_relationship = graphene.List(lambda: RelationshipType)

    def resolve_all_target_node_in_relationship(self, info) -> Any:
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
    def resolve_descendants_tree(self, info) -> Any:
        """
        Returns a flat list of descendant annotations,
        each including only the IDs of its immediate children.
        """
        from django_cte import CTE, with_cte

        def get_descendants(cte):
            base_qs = Annotation.objects.filter(parent_id=self.id).values(
                "id", "parent_id", "raw_text"
            )
            recursive_qs = cte.join(Annotation, parent_id=cte.col.id).values(
                "id", "parent_id", "raw_text"
            )
            return base_qs.union(recursive_qs, all=True)

        cte = CTE.recursive(get_descendants)
        descendants_qs = with_cte(cte, select=cte.queryset()).order_by("id")
        descendants_list = list(descendants_qs)

        return build_flat_tree(
            descendants_list, type_name="AnnotationType", text_key="raw_text"
        )

    # Resolver for full_tree
    def resolve_full_tree(self, info) -> Any:
        """
        Returns a flat list of annotations from the root ancestor,
        each including only the IDs of its immediate children.
        """
        from django_cte import CTE, with_cte

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

        cte = CTE.recursive(get_full_tree)
        full_tree_qs = with_cte(cte, select=cte.queryset()).order_by("id")
        nodes = list(full_tree_qs)
        full_tree = build_flat_tree(
            nodes, type_name="AnnotationType", text_key="raw_text"
        )
        return full_tree

    # Resolver for subtree
    def resolve_subtree(self, info) -> Any:
        """
        Returns a combined tree that includes:
        - The path from the root ancestor to this annotation (ancestors).
        - This annotation and all its descendants.
        """
        from django_cte import CTE, with_cte

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

        descendants_cte = CTE.recursive(get_descendants)
        descendants_qs = with_cte(
            descendants_cte, select=descendants_cte.queryset()
        ).values("id", "parent_id", "raw_text")

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
        exclude = ("embedding", "search_vector")
        connection_class = CountableConnection

        # In order for filter options to show up in nested resolvers, you need to specify them
        # in the Graphene type
        filterset_class = AnnotationFilter

    @classmethod
    def get_queryset(cls, queryset, info) -> Any:
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

    def resolve_doc_label_count(self, info) -> Any:
        """Return doc label count from annotation or query."""
        # Check if parent corpus has passed the annotated value
        if hasattr(self, "_doc_label_count") and self._doc_label_count is not None:
            return self._doc_label_count
        return self.annotation_labels.filter(label_type="DOC_TYPE_LABEL").count()

    def resolve_span_label_count(self, info) -> Any:
        """Return span label count from annotation or query."""
        if hasattr(self, "_span_label_count") and self._span_label_count is not None:
            return self._span_label_count
        return self.annotation_labels.filter(label_type="SPAN_LABEL").count()

    def resolve_token_label_count(self, info) -> Any:
        """Return token label count from annotation or query."""
        if hasattr(self, "_token_label_count") and self._token_label_count is not None:
            return self._token_label_count
        return self.annotation_labels.filter(label_type="TOKEN_LABEL").count()

    # Count of corpuses using this label set
    corpus_count = graphene.Int(description="Number of corpuses using this label set")

    def resolve_corpus_count(self, info) -> Any:
        """Return count of corpuses using this label set that are visible to the user."""
        user = info.context.user
        return self.used_by_corpuses.visible_to_user(user).count()

    # To get ALL labels for a given labelset
    all_annotation_labels = graphene.Field(graphene.List(AnnotationLabelType))

    def resolve_all_annotation_labels(self, info) -> Any:
        return self.annotation_labels.all()

    # Custom resolver for icon field
    def resolve_icon(self, info) -> Any:
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

    def resolve_revisions(self, info) -> Any:
        """Returns all revisions for this note, ordered by version."""
        return self.revisions.all()

    def resolve_current_version(self, info) -> Any:
        """Returns the current version number."""
        latest_revision = self.revisions.order_by("-version").first()
        return latest_revision.version if latest_revision else 0

    # Resolver for descendants_tree
    def resolve_descendants_tree(self, info) -> Any:
        """
        Returns a flat list of descendant notes,
        each including only the IDs of its immediate children.
        """
        from django_cte import CTE, with_cte

        def get_descendants(cte):
            base_qs = Note.objects.filter(parent_id=self.id).values(
                "id", "parent_id", "content"
            )
            recursive_qs = cte.join(Note, parent_id=cte.col.id).values(
                "id", "parent_id", "content"
            )
            return base_qs.union(recursive_qs, all=True)

        cte = CTE.recursive(get_descendants)
        descendants_qs = with_cte(cte, select=cte.queryset()).order_by("id")
        descendants_list = list(descendants_qs)
        descendants_tree = build_flat_tree(
            descendants_list, type_name="NoteType", text_key="content"
        )
        return descendants_tree

    # Resolver for full_tree
    def resolve_full_tree(self, info) -> Any:
        """
        Returns a flat list of notes from the root ancestor,
        each including only the IDs of its immediate children.
        """
        from django_cte import CTE, with_cte

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

        cte = CTE.recursive(get_full_tree)
        full_tree_qs = with_cte(cte, select=cte.queryset()).order_by("id")
        nodes = list(full_tree_qs)
        full_tree = build_flat_tree(nodes, type_name="NoteType", text_key="content")
        return full_tree

    # Resolver for subtree
    def resolve_subtree(self, info) -> Any:
        """
        Returns a combined tree that includes:
        - The path from the root ancestor to this note (ancestors).
        - This note and all its descendants.
        """
        from django_cte import CTE, with_cte

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

        descendants_cte = CTE.recursive(get_descendants)
        descendants_qs = with_cte(
            descendants_cte, select=descendants_cte.queryset()
        ).values("id", "parent_id", "content")

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
    def get_queryset(cls, queryset, info) -> Any:
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
