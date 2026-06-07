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
    get_anonymous_user_id,
)
from opencontractserver.annotations.models import (
    Annotation,
    AnnotationLabel,
    LabelSet,
    Note,
    NoteRevision,
    Relationship,
)
from opencontractserver.shared.services.base import BaseService
from opencontractserver.utils.permissioning import get_users_permissions_for_obj


def _get_document_type() -> Any:
    """Lazy ``DocumentType`` accessor.

    ``document_types`` imports ``annotation_types`` at module load, so a
    top-level import here would be circular. Resolved at schema-build time.
    """
    from config.graphql.document_types import DocumentType

    return DocumentType


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
    # ``data`` carries label-specific structured metadata (e.g. the
    # ``{canonical_name, lat, lng, admin_codes, geocoded}`` payload that
    # the OC_COUNTRY/OC_STATE/OC_CITY mutations write — see #1819).
    # Declared explicitly as ``GenericScalar`` so graphene-django doesn't
    # try to coerce the JSONField into a typed graphene field; the
    # existing ``json`` declaration above uses the same pattern.
    data = GenericScalar()  # noqa
    annotation_type = graphene.String(
        description="Annotation type (e.g. TOKEN_LABEL, SPAN_LABEL). "
        "Returns raw DB value to avoid enum serialization errors on invalid data.",
    )
    feedback_count = graphene.Int(description="Count of user feedback")
    content_modalities = graphene.List(
        graphene.String,
        description="Content modalities present in this annotation: TEXT, IMAGE, etc.",
    )
    # ``document`` is declared explicitly (rather than relying on graphene-django's
    # auto-generated FK field) so ``resolve_document`` below is ALWAYS invoked.
    # graphene-django's FK resolver short-circuits to ``None`` whenever the raw
    # ``document_id`` column is NULL (``converter.py`` reads ``root.document_id``
    # then ``get_node(None)`` → ``None``) — which is EVERY structural annotation,
    # since those carry ``document_id=NULL`` and reach their document only via the
    # shared ``structural_set``. Without this explicit field the resolver never
    # runs for structural annotations and the corpus cards render "Unknown
    # Document". Lazy type ref avoids the annotation_types ↔ document_types
    # import cycle (document_types imports annotation_types).
    document = graphene.Field(
        _get_document_type,
        description=(
            "The document this annotation belongs to. Structural annotations "
            "(document_id=NULL) resolve it via the shared structural set, scoped "
            "to the queried corpus by AnnotationService.structural_document_prefetch."
        ),
    )

    def resolve_document(self, info) -> Any:
        """Return the document, resolving via structural_set for structural annotations.

        Runs because ``document`` is declared as an explicit ``graphene.Field``
        above — graphene-django's auto-generated FK field would short-circuit to
        ``None`` for structural annotations (``document_id=NULL``) before this
        method ever ran.
        """
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
            # Fallback when the caller did not apply
            # ``AnnotationService.structural_document_prefetch`` (deferred import
            # avoids a module-level cycle with documents.models). Scope to this
            # annotation's own corpus and order deterministically so we never
            # reintroduce the original arbitrary ``.documents.first()`` bug;
            # query-context scoping (which corpus is being viewed) only happens
            # via the prefetch above, so this is a best-effort degraded path.
            from opencontractserver.documents.models import Document

            documents = Document.objects.filter(
                structural_annotation_set_id=self.structural_set_id
            )
            if self.corpus_id:
                documents = documents.filter(
                    path_records__corpus_id=self.corpus_id,
                    path_records__is_current=True,
                    path_records__is_deleted=False,
                )
            return documents.order_by("slug").first()
        return None

    def resolve_annotation_type(self, info) -> Any:
        """Return annotation_type as a plain string to tolerate invalid DB values."""
        return self.annotation_type or ""

    def resolve_content_modalities(self, info) -> Any:
        """Return content modalities list from model."""
        return self.content_modalities or []

    all_source_node_in_relationship = graphene.List(lambda: RelationshipType)

    def resolve_feedback_count(self, info) -> int:
        # If ``feedback_count`` was annotated on the queryset (legacy callers),
        # honour it — but the optimizer no longer adds the annotation because
        # it forced a LEFT JOIN + GROUP BY for every annotation in the result.
        if hasattr(self, "feedback_count"):
            return self.feedback_count
        # Prefer the prefetched ``user_feedback`` list when the parent resolver
        # populated it (see ``AnnotationService.get_document_annotations``);
        # ``QuerySet.count()`` always issues a fresh ``COUNT(*)`` and would
        # produce one round-trip per annotation. ``_prefetched_objects_cache``
        # is a Django internal — if it changes shape in a future release the
        # ``self.user_feedback.count()`` fallback keeps correctness intact, only
        # losing the per-row optimisation.
        prefetched = getattr(self, "_prefetched_objects_cache", {})
        if "user_feedback" in prefetched:
            return len(prefetched["user_feedback"])
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
        # Always pre-join the FKs the GraphQL type exposes
        # (``annotation_label`` and ``corpus``). Without this, graphene-django's
        # auto-generated FK resolver falls through to ``cls.get_node(info, pk)``
        # → ``Corpus.objects.get(pk)`` per row — and because ``Corpus`` is a
        # ``TreeNode`` registered with ``with_tree_fields=True``, every such
        # ``get`` triggers a recursive ``WITH __rank_table`` CTE.
        # ``AnnotationService.get_document_annotations`` already adds
        # ``annotation_label`` / ``creator`` / ``analysis`` but not ``corpus``,
        # so the join is added here regardless of which path produced the qs.
        fk_joins = ("annotation_label", "corpus")

        # The query optimizer adds ``_can_*`` annotations and has already
        # filtered for visibility — don't re-filter.
        if (
            hasattr(queryset, "query")
            and queryset.query.annotations
            and any(key.startswith("_can_") for key in queryset.query.annotations)
        ):
            return queryset.select_related(*fk_joins)

        # Otherwise apply ``visible_to_user`` via the service layer
        # (the ``opencontracts.E001`` system check forbids inline use here),
        # then layer the FK joins on top.
        return BaseService.filter_visible_qs(
            queryset, info.context.user, request=info.context
        ).select_related(*fk_joins)


class AnnotationLabelType(AnnotatePermissionsForReadMixin, DjangoObjectType):
    class Meta:
        model = AnnotationLabel
        interfaces = [relay.Node]
        connection_class = CountableConnection

    def resolve_my_permissions(self, info) -> list[str]:
        """Inherit permissions from the LabelSet(s) that include this label.

        AnnotationLabels deliberately carry no django-guardian object-permission
        tables of their own — the LabelSet is the permissioned entity that
        governs its labels. A label can belong to multiple labelsets; the
        caller's effective permissions are the union of their permissions
        across those labelsets, with ``*_labelset`` codenames mapped onto
        ``*_annotationlabel``. Public / built-in (``read_only``) labels are
        always readable.

        This override replaces the generic mixin resolver, which assumes the
        model exposes a ``{model}userobjectpermission_set`` reverse accessor
        and otherwise raises ``AttributeError`` (caught + error-logged) for
        every annotation-label node.
        """
        permissions: set[str] = set()

        if getattr(self, "is_public", False) or getattr(self, "read_only", False):
            permissions.add("read_annotationlabel")

        context = getattr(info, "context", None)
        user = getattr(context, "user", None)
        anon_id = get_anonymous_user_id(info)
        if (
            user is not None
            and getattr(user, "is_authenticated", False)
            and user.id != anon_id
        ):
            # ``get_users_permissions_for_obj`` returns only the perms the
            # caller actually holds on each labelset (creator / guardian /
            # group / is_public), so labelsets they cannot see contribute
            # nothing.
            #
            # Known limitation (accepted): this is a per-label N+1 — each label
            # node runs ``included_in_labelsets.all()`` plus a permission lookup
            # per labelset, with no resolver-level ``prefetch_related`` to
            # collapse it. Acceptable only because label↔labelset membership is
            # small (typically 1) in practice. If ``AnnotationLabelType`` is ever
            # rendered inside a large connection that also selects
            # ``myPermissions``, add ``prefetch_related("included_in_labelsets")``
            # to the source queryset before this fans out.
            for labelset in self.included_in_labelsets.all():
                for perm in get_users_permissions_for_obj(user, labelset):
                    permissions.add(perm.replace("labelset", "annotationlabel"))

        return list(permissions)


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
        return BaseService.filter_visible_qs(
            self.used_by_corpuses, info.context.user, request=info.context
        ).count()

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

    content_preview = graphene.String(
        description=(
            "First 400 characters of the note body for list/search previews. "
            "Resolvers may annotate the queryset with `content_preview` to "
            "avoid shipping the full body over the wire."
        )
    )

    def resolve_content_preview(self, info) -> str:
        annotated = getattr(self, "content_preview", None)
        if annotated is not None:
            return annotated
        return (self.content or "")[:400]

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
        exclude = ("embedding", "search_vector")
        interfaces = [relay.Node]
        connection_class = CountableConnection

    @classmethod
    def get_queryset(cls, queryset, info) -> Any:
        # Route visibility through the service layer (BaseService) so this
        # type field resolver does not touch Tier-0 directly. Uses
        # ``filter_visible_qs`` so the visibility filter chains on the
        # incoming queryset/manager in a single SQL pass.
        return BaseService.filter_visible_qs(
            queryset, info.context.user, request=info.context
        )


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
