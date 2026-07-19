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
from typing import Annotated, Any

import strawberry
from django.db.models import Q, QuerySet

from config.graphql import enums
from config.graphql._util import coerce_enum, coerce_str, strip_unset
from config.graphql.base_types import build_flat_tree
from config.graphql.core import permissions as core_permissions
from config.graphql.core.filtering import setup_filterset
from config.graphql.core.permissions import get_anonymous_user_id
from config.graphql.core.relay import (
    Node,
    make_connection_types,
    register_type,
    resolve_django_connection,
    resolve_visible_fk,
)
from config.graphql.core.scalars import GenericScalar
from config.graphql.filters import (
    AnnotationFilter,
    AuthorityFrontierFilter,
    AuthorityKeyEquivalenceFilter,
    AuthorityNamespaceFilter,
    LabelFilter,
)
from opencontractserver.annotations.models import (
    Annotation,
    AnnotationLabel,
    AuthorityFrontier,
    AuthorityKeyEquivalence,
    AuthorityNamespace,
    CorpusReference,
    LabelSet,
    Note,
    NoteRevision,
    Relationship,
)
from opencontractserver.enrichment.services.authority_mapping_service import (
    MANUAL as MANUAL_SOURCE,
)
from opencontractserver.enrichment.services.authority_permissions import (
    is_authority_admin,
)
from opencontractserver.shared.services.base import BaseService
from opencontractserver.utils.permissioning import get_users_permissions_for_obj


@strawberry.input(name="RelationInputType")
class RelationInputType:
    my_permissions: GenericScalar | None = strawberry.field(
        name="myPermissions", default=strawberry.UNSET
    )
    is_published: bool | None = strawberry.field(
        name="isPublished", default=strawberry.UNSET
    )
    object_shared_with: GenericScalar | None = strawberry.field(
        name="objectSharedWith", default=strawberry.UNSET
    )
    id: str | None = strawberry.field(name="id", default=strawberry.UNSET)
    source_ids: list[str | None] | None = strawberry.field(
        name="sourceIds", default=strawberry.UNSET
    )
    target_ids: list[str | None] | None = strawberry.field(
        name="targetIds", default=strawberry.UNSET
    )
    relationship_label_id: str | None = strawberry.field(
        name="relationshipLabelId", default=strawberry.UNSET
    )
    corpus_id: str | None = strawberry.field(name="corpusId", default=strawberry.UNSET)
    document_id: str | None = strawberry.field(
        name="documentId", default=strawberry.UNSET
    )


def _resolve_AnnotationType_annotation_type(root, info):
    """Return annotation_type as a plain string to tolerate invalid DB values."""
    return root.annotation_type or ""


def _resolve_AnnotationType_document(root, info):
    """Return the document, resolving via structural_set for structural annotations.

    Runs because ``document`` is declared as an explicit ``graphene.Field``
    above — graphene-django's auto-generated FK field would short-circuit to
    ``None`` for structural annotations (``document_id=NULL``) before this
    method ever ran.
    """
    # Deferred import avoids a module-level cycle: ``annotations.services``
    # (via ``documents.models``) pulls in ``document_types`` which imports
    # ``annotation_types``.
    from opencontractserver.annotations.services import AnnotationService

    user = info.context.user

    if root.document_id:
        # Non-structural annotation: the document is its own parent. The
        # annotation list / semantic-search resolvers always
        # ``select_related("document")``, so the FK is already in memory —
        # return it directly instead of issuing a per-row ``SELECT``.
        # ``Field.is_cached`` (``django.db.models.fields.mixins.
        # FieldCacheMixin``) checks ``instance._state.fields_cache``, i.e.
        # whether the related ``Document`` object itself was loaded via
        # ``select_related`` — NOT whether the raw ``document_id`` column
        # is present on the row (that column is always loaded). So this
        # correctly distinguishes "FK object in memory" from "FK object
        # not fetched yet", and the fallback below IS reached whenever a
        # caller queries ``Annotation`` without ``select_related("document")``.
        # Annotation READ visibility is inherited from the document, so any
        # annotation that reached this resolver already implies document
        # READ; the fallback still re-derives that via a permission-scoped
        # fetch instead of trusting an un-checked FK traversal.
        document_field = root._meta.get_field("document")
        if document_field.is_cached(root):
            return root.document
        return AnnotationService.resolve_owned_document(
            document_id=root.document_id, user=user
        )

    # Structural annotations carry document_id=NULL; resolve via structural_set.
    if not root.structural_set_id:
        return None

    structural_set = root.structural_set
    if structural_set is not None:
        # When ``AnnotationService.structural_document_prefetch`` was applied
        # (the hot list / search paths), the prefetch cache is already scoped
        # to the queried context AND to documents the user may READ —
        # evaluated once for the whole page, ordered by slug. The prefetch is
        # the permission gate (``user`` is required there), so trust it —
        # including an empty result, which is already a definitive "no
        # visible member of this set in this context" rather than a
        # missing-prefetch signal. ``_prefetched_objects_cache`` is a
        # private Django attribute (same trade-off already accepted in
        # ``config/graphql/extract_types.py::resolve_document_count``);
        # regression coverage lives in
        # ``test_corpus_cards_structural_document_resolution.py`` —
        # a broken cache-detection here silently degrades every row to
        # the per-row fallback query below, which that test's captured
        # query-count assertion catches.
        prefetched_cache = getattr(structural_set, "_prefetched_objects_cache", {})
        if "documents" in prefetched_cache:
            prefetched = list(structural_set.documents.all())
            return prefetched[0] if prefetched else None

    # Fallback when the caller did not apply
    # ``AnnotationService.structural_document_prefetch`` at all (no
    # ``_prefetched_objects_cache`` entry for ``documents``). Best-effort,
    # corpus-scoped, permission-gated degraded path — see
    # ``AnnotationService.resolve_structural_document_fallback``.
    return AnnotationService.resolve_structural_document_fallback(
        structural_set_id=root.structural_set_id,
        corpus_id=root.corpus_id,
        user=user,
    )


def _resolve_AnnotationType_content_modalities(root, info):
    """Return content modalities list from model."""
    return root.content_modalities or []


def _resolve_AnnotationType_feedback_count(root, info):
    # If ``feedback_count`` was annotated on the queryset (legacy callers),
    # honour it — but the optimizer no longer adds the annotation because
    # it forced a LEFT JOIN + GROUP BY for every annotation in the result.
    if hasattr(root, "feedback_count"):
        return root.feedback_count
    # Prefer the prefetched ``user_feedback`` list when the parent resolver
    # populated it (see ``AnnotationService.get_document_annotations``);
    # ``QuerySet.count()`` always issues a fresh ``COUNT(*)`` and would
    # produce one round-trip per annotation. ``_prefetched_objects_cache``
    # is a Django internal — if it changes shape in a future release the
    # ``self.user_feedback.count()`` fallback keeps correctness intact, only
    # losing the per-row optimisation.
    prefetched = getattr(root, "_prefetched_objects_cache", {})
    if "user_feedback" in prefetched:
        return len(prefetched["user_feedback"])
    return root.user_feedback.count()


def _resolve_AnnotationType_all_source_node_in_relationship(root, info):
    return root.source_node_in_relationships.all()


def _resolve_AnnotationType_all_target_node_in_relationship(root, info):
    return root.target_node_in_relationships.all()


def _resolve_AnnotationType_descendants_tree(root, info):
    """
    Returns a flat list of descendant annotations,
    each including only the IDs of its immediate children.
    """
    from django_cte import CTE, with_cte

    def get_descendants(cte):
        base_qs = Annotation.objects.filter(parent_id=root.id).values(
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


def _resolve_AnnotationType_full_tree(root, info):
    """
    Returns a flat list of annotations from the root ancestor,
    each including only the IDs of its immediate children.
    """
    from django_cte import CTE, with_cte

    # Find the root ancestor
    tree_root = root
    while tree_root.parent_id is not None:
        tree_root = tree_root.parent

    def get_full_tree(cte):
        base_qs = Annotation.objects.filter(id=tree_root.id).values(
            "id", "parent_id", "raw_text"
        )
        recursive_qs = cte.join(Annotation, parent_id=cte.col.id).values(
            "id", "parent_id", "raw_text"
        )
        return base_qs.union(recursive_qs, all=True)

    cte = CTE.recursive(get_full_tree)
    full_tree_qs = with_cte(cte, select=cte.queryset()).order_by("id")
    nodes = list(full_tree_qs)
    full_tree = build_flat_tree(nodes, type_name="AnnotationType", text_key="raw_text")
    return full_tree


def _resolve_AnnotationType_subtree(root, info):
    """
    Returns a combined tree that includes:
    - The path from the root ancestor to this annotation (ancestors).
    - This annotation and all its descendants.
    """
    from django_cte import CTE, with_cte

    # Find all ancestors up to the root
    ancestors = []
    node = root
    while node.parent_id is not None:
        ancestors.append(node)
        node = node.parent
    ancestors.append(node)  # Include the root ancestor
    ancestor_ids = [ancestor.id for ancestor in ancestors]

    # Get all descendants of the current node
    def get_descendants(cte):
        base_qs = Annotation.objects.filter(parent_id=root.id).values(
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


@strawberry.type(name="AnnotationType")
class AnnotationType(Node):
    user_lock: None | (
        Annotated[UserType, strawberry.lazy("config.graphql.user_types")]
    ) = strawberry.field(name="userLock", default=None)
    backend_lock: bool = strawberry.field(name="backendLock", default=None)
    page: int = strawberry.field(name="page", default=None)

    @strawberry.field(name="rawText")
    def raw_text(self, info: strawberry.Info) -> str | None:
        return coerce_str(getattr(self, "raw_text", None))

    @strawberry.field(
        name="longDescription",
        description="Optional markdown description for this annotation, e.g. a section summary in a document index.",
    )
    def long_description(self, info: strawberry.Info) -> str | None:
        return coerce_str(getattr(self, "long_description", None))

    json: GenericScalar | None = strawberry.field(name="json", default=None)
    parent: AnnotationType | None = strawberry.field(name="parent", default=None)

    @strawberry.field(
        name="annotationType",
        description="Annotation type (e.g. TOKEN_LABEL, SPAN_LABEL). Returns raw DB value to avoid enum serialization errors on invalid data.",
    )
    def annotation_type(self, info: strawberry.Info) -> str | None:
        kwargs = strip_unset({})
        return _resolve_AnnotationType_annotation_type(self, info, **kwargs)

    annotation_label: AnnotationLabelType | None = strawberry.field(
        name="annotationLabel", default=None
    )

    @strawberry.field(
        name="document",
        description="The document this annotation belongs to. Structural annotations (document_id=NULL) resolve it via the shared structural set, scoped to the queried corpus by AnnotationService.structural_document_prefetch.",
    )
    def document(
        self, info: strawberry.Info
    ) -> None | (
        Annotated[DocumentType, strawberry.lazy("config.graphql.document_types")]
    ):
        kwargs = strip_unset({})
        return _resolve_AnnotationType_document(self, info, **kwargs)

    @strawberry.field(name="corpus")
    def corpus(
        self, info: strawberry.Info
    ) -> None | (Annotated[CorpusType, strawberry.lazy("config.graphql.corpus_types")]):
        # Permission-filtered FK traversal (graphene routed auto-converted FKs
        # to CorpusType through CorpusType.get_queryset). A structural
        # annotation reachable via one corpus must not leak a different,
        # private corpus via its ``corpus_id``.
        return resolve_visible_fk(self, info, "corpus_id", "CorpusType")

    analysis: None | (
        Annotated[AnalysisType, strawberry.lazy("config.graphql.extract_types")]
    ) = strawberry.field(name="analysis", default=None)
    created_by_analysis: None | (
        Annotated[AnalysisType, strawberry.lazy("config.graphql.extract_types")]
    ) = strawberry.field(
        name="createdByAnalysis",
        description="If set, this annotation is private to the analysis that created it",
        default=None,
    )
    created_by_extract: None | (
        Annotated[ExtractType, strawberry.lazy("config.graphql.extract_types")]
    ) = strawberry.field(
        name="createdByExtract",
        description="If set, this annotation is private to the extract that created it",
        default=None,
    )
    corpus_action: None | (
        Annotated[CorpusActionType, strawberry.lazy("config.graphql.agent_types")]
    ) = strawberry.field(
        name="corpusAction",
        description="If set, this annotation was created by a corpus action agent",
        default=None,
    )
    structural: bool = strawberry.field(name="structural", default=None)

    @strawberry.field(
        name="linkUrl",
        description="Target URL opened when the annotation is clicked. Only meaningful for annotations labelled OC_URL.",
    )
    def link_url(self, info: strawberry.Info) -> str | None:
        return coerce_str(getattr(self, "link_url", None))

    data: GenericScalar | None = strawberry.field(name="data", default=None)
    is_grounding_source: bool = strawberry.field(name="isGroundingSource", default=None)

    @strawberry.field(
        name="contentModalities",
        description="Content modalities present in this annotation: TEXT, IMAGE, etc.",
    )
    def content_modalities(self, info: strawberry.Info) -> list[str | None] | None:
        kwargs = strip_unset({})
        return _resolve_AnnotationType_content_modalities(self, info, **kwargs)

    @strawberry.field(
        name="imageContentFile",
        description="JSON file containing extracted image data for IMAGE modality annotations",
    )
    def image_content_file(self, info: strawberry.Info) -> str | None:
        return coerce_str(getattr(self, "image_content_file", None))

    is_public: bool = strawberry.field(name="isPublic", default=None)
    creator: Annotated[UserType, strawberry.lazy("config.graphql.user_types")] = (
        strawberry.field(name="creator", default=None)
    )
    created: datetime.datetime = strawberry.field(name="created", default=None)
    modified: datetime.datetime = strawberry.field(name="modified", default=None)

    @strawberry.field(name="assignmentSet")
    def assignment_set(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> Annotated[
        AssignmentTypeConnection, strawberry.lazy("config.graphql.user_types")
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "assignment_set", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="AssignmentType",
        )

    @strawberry.field(name="rows")
    def rows(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> Annotated[
        DocumentAnalysisRowTypeConnection,
        strawberry.lazy("config.graphql.document_types"),
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "rows", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="DocumentAnalysisRowType",
        )

    @strawberry.field(name="sourceNodeInRelationships")
    def source_node_in_relationships(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> RelationshipTypeConnection:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "source_node_in_relationships", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="RelationshipType",
        )

    @strawberry.field(name="targetNodeInRelationships")
    def target_node_in_relationships(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> RelationshipTypeConnection:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "target_node_in_relationships", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="RelationshipType",
        )

    @strawberry.field(name="children")
    def children(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
        raw_text__contains: Annotated[
            str | None, strawberry.argument(name="rawText_Contains")
        ] = strawberry.UNSET,
        annotation_label_id: Annotated[
            strawberry.ID | None, strawberry.argument(name="annotationLabelId")
        ] = strawberry.UNSET,
        annotation_label__text: Annotated[
            str | None, strawberry.argument(name="annotationLabel_Text")
        ] = strawberry.UNSET,
        annotation_label__text__contains: Annotated[
            str | None, strawberry.argument(name="annotationLabel_Text_Contains")
        ] = strawberry.UNSET,
        annotation_label__description__contains: Annotated[
            str | None,
            strawberry.argument(name="annotationLabel_Description_Contains"),
        ] = strawberry.UNSET,
        annotation_label__label_type: Annotated[
            enums.AnnotationsAnnotationLabelLabelTypeChoices | None,
            strawberry.argument(name="annotationLabel_LabelType"),
        ] = strawberry.UNSET,
        analysis__isnull: Annotated[
            bool | None, strawberry.argument(name="analysis_Isnull")
        ] = strawberry.UNSET,
        document_id: Annotated[
            strawberry.ID | None, strawberry.argument(name="documentId")
        ] = strawberry.UNSET,
        corpus_id: Annotated[
            strawberry.ID | None, strawberry.argument(name="corpusId")
        ] = strawberry.UNSET,
        structural: Annotated[
            bool | None, strawberry.argument(name="structural")
        ] = strawberry.UNSET,
        uses_label_from_labelset_id: Annotated[
            str | None, strawberry.argument(name="usesLabelFromLabelsetId")
        ] = strawberry.UNSET,
        created_by_analysis_ids: Annotated[
            str | None, strawberry.argument(name="createdByAnalysisIds")
        ] = strawberry.UNSET,
        created_with_analyzer_id: Annotated[
            str | None, strawberry.argument(name="createdWithAnalyzerId")
        ] = strawberry.UNSET,
        order_by: Annotated[
            str | None, strawberry.argument(name="orderBy", description="Ordering")
        ] = strawberry.UNSET,
    ) -> AnnotationTypeConnection:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
                "raw_text__contains": raw_text__contains,
                "annotation_label_id": annotation_label_id,
                "annotation_label__text": annotation_label__text,
                "annotation_label__text__contains": annotation_label__text__contains,
                "annotation_label__description__contains": annotation_label__description__contains,
                "annotation_label__label_type": annotation_label__label_type,
                "analysis__isnull": analysis__isnull,
                "document_id": document_id,
                "corpus_id": corpus_id,
                "structural": structural,
                "uses_label_from_labelset_id": uses_label_from_labelset_id,
                "created_by_analysis_ids": created_by_analysis_ids,
                "created_with_analyzer_id": created_with_analyzer_id,
                "order_by": order_by,
            }
        )
        resolved = getattr(self, "children", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="AnnotationType",
            filterset_class=setup_filterset(AnnotationFilter),
            filter_args={
                "raw_text__contains": "raw_text__contains",
                "annotation_label_id": "annotation_label_id",
                "annotation_label__text": "annotation_label__text",
                "annotation_label__text__contains": "annotation_label__text__contains",
                "annotation_label__description__contains": "annotation_label__description__contains",
                "annotation_label__label_type": "annotation_label__label_type",
                "analysis__isnull": "analysis__isnull",
                "document_id": "document_id",
                "corpus_id": "corpus_id",
                "structural": "structural",
                "uses_label_from_labelset_id": "uses_label_from_labelset_id",
                "created_by_analysis_ids": "created_by_analysis_ids",
                "created_with_analyzer_id": "created_with_analyzer_id",
                "order_by": "order_by",
            },
        )

    @strawberry.field(name="notes")
    def notes(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> NoteTypeConnection:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "notes", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="NoteType",
        )

    @strawberry.field(name="outboundReferences")
    def outbound_references(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> CorpusReferenceTypeConnection:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "outbound_references", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="CorpusReferenceType",
        )

    @strawberry.field(name="inboundReferences")
    def inbound_references(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> CorpusReferenceTypeConnection:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "inbound_references", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="CorpusReferenceType",
        )

    @strawberry.field(name="referencingCells")
    def referencing_cells(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> Annotated[
        DatacellTypeConnection, strawberry.lazy("config.graphql.extract_types")
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "referencing_cells", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="DatacellType",
        )

    @strawberry.field(name="userFeedback")
    def user_feedback(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> Annotated[
        UserFeedbackTypeConnection, strawberry.lazy("config.graphql.user_types")
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "user_feedback", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="UserFeedbackType",
        )

    @strawberry.field(
        name="chatMessages",
        description="Annotations that this chat message is based on",
    )
    def chat_messages(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> Annotated[
        MessageTypeConnection, strawberry.lazy("config.graphql.conversation_types")
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "chat_messages", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="MessageType",
        )

    @strawberry.field(
        name="createdByChatMessage",
        description="Annotations that this chat message created",
    )
    def created_by_chat_message(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> Annotated[
        MessageTypeConnection, strawberry.lazy("config.graphql.conversation_types")
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "created_by_chat_message", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="MessageType",
        )

    @strawberry.field(
        name="citedInResearchReports",
        description="Annotations cited in the final report",
    )
    def cited_in_research_reports(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> Annotated[
        ResearchReportTypeConnection, strawberry.lazy("config.graphql.research_types")
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "cited_in_research_reports", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="ResearchReportType",
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

    @strawberry.field(name="feedbackCount", description="Count of user feedback")
    def feedback_count(self, info: strawberry.Info) -> int | None:
        kwargs = strip_unset({})
        return _resolve_AnnotationType_feedback_count(self, info, **kwargs)

    @strawberry.field(name="allSourceNodeInRelationship")
    def all_source_node_in_relationship(
        self, info: strawberry.Info
    ) -> list[RelationshipType | None] | None:
        kwargs = strip_unset({})
        return _resolve_AnnotationType_all_source_node_in_relationship(
            self, info, **kwargs
        )

    @strawberry.field(name="allTargetNodeInRelationship")
    def all_target_node_in_relationship(
        self, info: strawberry.Info
    ) -> list[RelationshipType | None] | None:
        kwargs = strip_unset({})
        return _resolve_AnnotationType_all_target_node_in_relationship(
            self, info, **kwargs
        )

    @strawberry.field(
        name="descendantsTree",
        description="List of descendant annotations, each with immediate children's IDs.",
    )
    def descendants_tree(
        self, info: strawberry.Info
    ) -> list[GenericScalar | None] | None:
        kwargs = strip_unset({})
        return _resolve_AnnotationType_descendants_tree(self, info, **kwargs)

    @strawberry.field(
        name="fullTree",
        description="List of annotations from the root ancestor, each with immediate children's IDs.",
    )
    def full_tree(self, info: strawberry.Info) -> list[GenericScalar | None] | None:
        kwargs = strip_unset({})
        return _resolve_AnnotationType_full_tree(self, info, **kwargs)

    @strawberry.field(
        name="subtree",
        description="List representing the path from the root ancestor to this annotation and its descendants.",
    )
    def subtree(self, info: strawberry.Info) -> list[GenericScalar | None] | None:
        kwargs = strip_unset({})
        return _resolve_AnnotationType_subtree(self, info, **kwargs)


def _get_queryset_AnnotationType(queryset, info):
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


register_type(
    "AnnotationType",
    AnnotationType,
    model=Annotation,
    get_queryset=_get_queryset_AnnotationType,
)


AnnotationTypeConnection = make_connection_types(
    AnnotationType,
    type_name="AnnotationTypeConnection",
    countable=True,
    pdf_page_aware=False,
)


def _resolve_AnnotationLabelType_my_permissions(root, info):
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

    if getattr(root, "is_public", False) or getattr(root, "read_only", False):
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
        for labelset in root.included_in_labelsets.all():
            for perm in get_users_permissions_for_obj(user, labelset):
                permissions.add(perm.replace("labelset", "annotationlabel"))

    return list(permissions)


@strawberry.type(name="AnnotationLabelType")
class AnnotationLabelType(Node):
    user_lock: None | (
        Annotated[UserType, strawberry.lazy("config.graphql.user_types")]
    ) = strawberry.field(name="userLock", default=None)
    backend_lock: bool = strawberry.field(name="backendLock", default=None)
    created: datetime.datetime = strawberry.field(name="created", default=None)
    modified: datetime.datetime = strawberry.field(name="modified", default=None)

    @strawberry.field(name="labelType")
    def label_type(
        self, info: strawberry.Info
    ) -> enums.AnnotationsAnnotationLabelLabelTypeChoices:
        return coerce_enum(
            enums.AnnotationsAnnotationLabelLabelTypeChoices,
            getattr(self, "label_type", None),
        )

    analyzer: None | (
        Annotated[AnalyzerType, strawberry.lazy("config.graphql.extract_types")]
    ) = strawberry.field(name="analyzer", default=None)
    read_only: bool = strawberry.field(name="readOnly", default=None)

    @strawberry.field(name="color")
    def color(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "color", None))

    @strawberry.field(name="description")
    def description(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "description", None))

    @strawberry.field(name="icon")
    def icon(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "icon", None))

    @strawberry.field(name="text")
    def text(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "text", None))

    is_public: bool = strawberry.field(name="isPublic", default=None)
    creator: Annotated[UserType, strawberry.lazy("config.graphql.user_types")] = (
        strawberry.field(name="creator", default=None)
    )

    @strawberry.field(name="documentRelationships")
    def document_relationships(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> Annotated[
        DocumentRelationshipTypeConnection,
        strawberry.lazy("config.graphql.document_types"),
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "document_relationships", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="DocumentRelationshipType",
        )

    @strawberry.field(name="relationships")
    def relationships(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> RelationshipTypeConnection:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "relationships", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="RelationshipType",
        )

    @strawberry.field(name="annotationSet")
    def annotation_set(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
        raw_text__contains: Annotated[
            str | None, strawberry.argument(name="rawText_Contains")
        ] = strawberry.UNSET,
        annotation_label_id: Annotated[
            strawberry.ID | None, strawberry.argument(name="annotationLabelId")
        ] = strawberry.UNSET,
        annotation_label__text: Annotated[
            str | None, strawberry.argument(name="annotationLabel_Text")
        ] = strawberry.UNSET,
        annotation_label__text__contains: Annotated[
            str | None, strawberry.argument(name="annotationLabel_Text_Contains")
        ] = strawberry.UNSET,
        annotation_label__description__contains: Annotated[
            str | None,
            strawberry.argument(name="annotationLabel_Description_Contains"),
        ] = strawberry.UNSET,
        annotation_label__label_type: Annotated[
            enums.AnnotationsAnnotationLabelLabelTypeChoices | None,
            strawberry.argument(name="annotationLabel_LabelType"),
        ] = strawberry.UNSET,
        analysis__isnull: Annotated[
            bool | None, strawberry.argument(name="analysis_Isnull")
        ] = strawberry.UNSET,
        document_id: Annotated[
            strawberry.ID | None, strawberry.argument(name="documentId")
        ] = strawberry.UNSET,
        corpus_id: Annotated[
            strawberry.ID | None, strawberry.argument(name="corpusId")
        ] = strawberry.UNSET,
        structural: Annotated[
            bool | None, strawberry.argument(name="structural")
        ] = strawberry.UNSET,
        uses_label_from_labelset_id: Annotated[
            str | None, strawberry.argument(name="usesLabelFromLabelsetId")
        ] = strawberry.UNSET,
        created_by_analysis_ids: Annotated[
            str | None, strawberry.argument(name="createdByAnalysisIds")
        ] = strawberry.UNSET,
        created_with_analyzer_id: Annotated[
            str | None, strawberry.argument(name="createdWithAnalyzerId")
        ] = strawberry.UNSET,
        order_by: Annotated[
            str | None, strawberry.argument(name="orderBy", description="Ordering")
        ] = strawberry.UNSET,
    ) -> AnnotationTypeConnection:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
                "raw_text__contains": raw_text__contains,
                "annotation_label_id": annotation_label_id,
                "annotation_label__text": annotation_label__text,
                "annotation_label__text__contains": annotation_label__text__contains,
                "annotation_label__description__contains": annotation_label__description__contains,
                "annotation_label__label_type": annotation_label__label_type,
                "analysis__isnull": analysis__isnull,
                "document_id": document_id,
                "corpus_id": corpus_id,
                "structural": structural,
                "uses_label_from_labelset_id": uses_label_from_labelset_id,
                "created_by_analysis_ids": created_by_analysis_ids,
                "created_with_analyzer_id": created_with_analyzer_id,
                "order_by": order_by,
            }
        )
        resolved = getattr(self, "annotation_set", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="AnnotationType",
            filterset_class=setup_filterset(AnnotationFilter),
            filter_args={
                "raw_text__contains": "raw_text__contains",
                "annotation_label_id": "annotation_label_id",
                "annotation_label__text": "annotation_label__text",
                "annotation_label__text__contains": "annotation_label__text__contains",
                "annotation_label__description__contains": "annotation_label__description__contains",
                "annotation_label__label_type": "annotation_label__label_type",
                "analysis__isnull": "analysis__isnull",
                "document_id": "document_id",
                "corpus_id": "corpus_id",
                "structural": "structural",
                "uses_label_from_labelset_id": "uses_label_from_labelset_id",
                "created_by_analysis_ids": "created_by_analysis_ids",
                "created_with_analyzer_id": "created_with_analyzer_id",
                "order_by": "order_by",
            },
        )

    @strawberry.field(name="includedInLabelsets")
    def included_in_labelsets(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> LabelSetTypeConnection:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "included_in_labelsets", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="LabelSetType",
        )

    @strawberry.field(name="myPermissions")
    def my_permissions(self, info: strawberry.Info) -> GenericScalar | None:
        kwargs = strip_unset({})
        return _resolve_AnnotationLabelType_my_permissions(self, info, **kwargs)

    @strawberry.field(name="isPublished")
    def is_published(self, info: strawberry.Info) -> bool | None:
        return core_permissions.resolve_is_published(self, info)

    @strawberry.field(name="objectSharedWith")
    def object_shared_with(self, info: strawberry.Info) -> GenericScalar | None:
        return core_permissions.resolve_object_shared_with(self, info)


def _get_node_AnnotationLabelType(info, pk):
    """Permission-aware node resolution for the singular ``annotationLabel(id:)``
    field (IDOR guard). Returns None when absent OR not visible, matching the
    graphene ``filter_visible`` resolver; without it ``get_node_from_global_id``
    would fall back to an UNFILTERED ``.get(pk=pk)``.
    """
    if pk is None:
        return None
    return BaseService.get_or_none(
        AnnotationLabel, pk, info.context.user, request=info.context
    )


register_type(
    "AnnotationLabelType",
    AnnotationLabelType,
    model=AnnotationLabel,
    get_node=_get_node_AnnotationLabelType,
)


AnnotationLabelTypeConnection = make_connection_types(
    AnnotationLabelType,
    type_name="AnnotationLabelTypeConnection",
    countable=True,
    pdf_page_aware=False,
)


def _resolve_LabelSetType_icon(root, info):
    return "" if not root.icon else info.context.build_absolute_uri(root.icon.url)


def _resolve_LabelSetType_doc_label_count(root, info):
    """Return doc label count from annotation or query."""
    # Check if parent corpus has passed the annotated value
    if hasattr(root, "_doc_label_count") and root._doc_label_count is not None:
        return root._doc_label_count
    return root.annotation_labels.filter(label_type="DOC_TYPE_LABEL").count()


def _resolve_LabelSetType_span_label_count(root, info):
    """Return span label count from annotation or query."""
    if hasattr(root, "_span_label_count") and root._span_label_count is not None:
        return root._span_label_count
    return root.annotation_labels.filter(label_type="SPAN_LABEL").count()


def _resolve_LabelSetType_token_label_count(root, info):
    """Return token label count from annotation or query."""
    if hasattr(root, "_token_label_count") and root._token_label_count is not None:
        return root._token_label_count
    return root.annotation_labels.filter(label_type="TOKEN_LABEL").count()


def _resolve_LabelSetType_corpus_count(root, info):
    """Return count of corpuses using this label set that are visible to the user."""
    return BaseService.filter_visible_qs(
        root.used_by_corpuses, info.context.user, request=info.context
    ).count()


def _resolve_LabelSetType_all_annotation_labels(root, info):
    return root.annotation_labels.all()


@strawberry.type(name="LabelSetType")
class LabelSetType(Node):
    user_lock: None | (
        Annotated[UserType, strawberry.lazy("config.graphql.user_types")]
    ) = strawberry.field(name="userLock", default=None)
    backend_lock: bool = strawberry.field(name="backendLock", default=None)
    is_public: bool = strawberry.field(name="isPublic", default=None)
    creator: Annotated[UserType, strawberry.lazy("config.graphql.user_types")] = (
        strawberry.field(name="creator", default=None)
    )
    created: datetime.datetime = strawberry.field(name="created", default=None)
    modified: datetime.datetime = strawberry.field(name="modified", default=None)

    @strawberry.field(name="title")
    def title(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "title", None))

    @strawberry.field(name="description")
    def description(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "description", None))

    @strawberry.field(name="icon")
    def icon(self, info: strawberry.Info) -> str:
        kwargs = strip_unset({})
        return _resolve_LabelSetType_icon(self, info, **kwargs)

    @strawberry.field(name="annotationLabels")
    def annotation_labels(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
        description__contains: Annotated[
            str | None, strawberry.argument(name="description_Contains")
        ] = strawberry.UNSET,
        text: Annotated[
            str | None, strawberry.argument(name="text")
        ] = strawberry.UNSET,
        text__contains: Annotated[
            str | None, strawberry.argument(name="text_Contains")
        ] = strawberry.UNSET,
        label_type: Annotated[
            enums.AnnotationsAnnotationLabelLabelTypeChoices | None,
            strawberry.argument(name="labelType"),
        ] = strawberry.UNSET,
        used_in_labelset_id: Annotated[
            str | None, strawberry.argument(name="usedInLabelsetId")
        ] = strawberry.UNSET,
        used_in_labelset_for_corpus_id: Annotated[
            str | None, strawberry.argument(name="usedInLabelsetForCorpusId")
        ] = strawberry.UNSET,
        used_in_analysis_ids: Annotated[
            str | None, strawberry.argument(name="usedInAnalysisIds")
        ] = strawberry.UNSET,
    ) -> AnnotationLabelTypeConnection | None:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
                "description__contains": description__contains,
                "text": text,
                "text__contains": text__contains,
                "label_type": label_type,
                "used_in_labelset_id": used_in_labelset_id,
                "used_in_labelset_for_corpus_id": used_in_labelset_for_corpus_id,
                "used_in_analysis_ids": used_in_analysis_ids,
            }
        )
        resolved = getattr(self, "annotation_labels", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="AnnotationLabelType",
            filterset_class=setup_filterset(LabelFilter),
            filter_args={
                "description__contains": "description__contains",
                "text": "text",
                "text__contains": "text__contains",
                "label_type": "label_type",
                "used_in_labelset_id": "used_in_labelset_id",
                "used_in_labelset_for_corpus_id": "used_in_labelset_for_corpus_id",
                "used_in_analysis_ids": "used_in_analysis_ids",
            },
        )

    analyzer: None | (
        Annotated[AnalyzerType, strawberry.lazy("config.graphql.extract_types")]
    ) = strawberry.field(name="analyzer", default=None)
    is_default: bool = strawberry.field(name="isDefault", default=None)

    @strawberry.field(name="usedByCorpuses")
    def used_by_corpuses(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> Annotated[
        CorpusTypeConnection, strawberry.lazy("config.graphql.corpus_types")
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "used_by_corpuses", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="CorpusType",
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

    @strawberry.field(
        name="docLabelCount", description="Count of document-level type labels"
    )
    def doc_label_count(self, info: strawberry.Info) -> int | None:
        kwargs = strip_unset({})
        return _resolve_LabelSetType_doc_label_count(self, info, **kwargs)

    @strawberry.field(name="spanLabelCount", description="Count of span-based labels")
    def span_label_count(self, info: strawberry.Info) -> int | None:
        kwargs = strip_unset({})
        return _resolve_LabelSetType_span_label_count(self, info, **kwargs)

    @strawberry.field(name="tokenLabelCount", description="Count of token-level labels")
    def token_label_count(self, info: strawberry.Info) -> int | None:
        kwargs = strip_unset({})
        return _resolve_LabelSetType_token_label_count(self, info, **kwargs)

    @strawberry.field(
        name="corpusCount", description="Number of corpuses using this label set"
    )
    def corpus_count(self, info: strawberry.Info) -> int | None:
        kwargs = strip_unset({})
        return _resolve_LabelSetType_corpus_count(self, info, **kwargs)

    @strawberry.field(name="allAnnotationLabels")
    def all_annotation_labels(
        self, info: strawberry.Info
    ) -> list[AnnotationLabelType | None] | None:
        kwargs = strip_unset({})
        return _resolve_LabelSetType_all_annotation_labels(self, info, **kwargs)


def _get_node_LabelSetType(info, pk):
    """Permission-aware node resolution for the singular ``labelset(id:)``
    field (IDOR guard). Returns None when absent OR not visible, matching the
    graphene ``filter_visible`` resolver; without it ``get_node_from_global_id``
    would fall back to an UNFILTERED ``.get(pk=pk)``.
    """
    if pk is None:
        return None
    return BaseService.get_or_none(
        LabelSet, pk, info.context.user, request=info.context
    )


register_type(
    "LabelSetType",
    LabelSetType,
    model=LabelSet,
    get_node=_get_node_LabelSetType,
)


LabelSetTypeConnection = make_connection_types(
    LabelSetType,
    type_name="LabelSetTypeConnection",
    countable=True,
    pdf_page_aware=False,
)


@strawberry.type(name="RelationshipType")
class RelationshipType(Node):
    user_lock: None | (
        Annotated[UserType, strawberry.lazy("config.graphql.user_types")]
    ) = strawberry.field(name="userLock", default=None)
    backend_lock: bool = strawberry.field(name="backendLock", default=None)
    relationship_label: AnnotationLabelType | None = strawberry.field(
        name="relationshipLabel", default=None
    )

    @strawberry.field(name="corpus")
    def corpus(
        self, info: strawberry.Info
    ) -> None | (Annotated[CorpusType, strawberry.lazy("config.graphql.corpus_types")]):
        return resolve_visible_fk(self, info, "corpus_id", "CorpusType")

    @strawberry.field(name="document")
    def document(
        self, info: strawberry.Info
    ) -> None | (
        Annotated[DocumentType, strawberry.lazy("config.graphql.document_types")]
    ):
        return resolve_visible_fk(self, info, "document_id", "DocumentType")

    @strawberry.field(name="sourceAnnotations")
    def source_annotations(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
        raw_text__contains: Annotated[
            str | None, strawberry.argument(name="rawText_Contains")
        ] = strawberry.UNSET,
        annotation_label_id: Annotated[
            strawberry.ID | None, strawberry.argument(name="annotationLabelId")
        ] = strawberry.UNSET,
        annotation_label__text: Annotated[
            str | None, strawberry.argument(name="annotationLabel_Text")
        ] = strawberry.UNSET,
        annotation_label__text__contains: Annotated[
            str | None, strawberry.argument(name="annotationLabel_Text_Contains")
        ] = strawberry.UNSET,
        annotation_label__description__contains: Annotated[
            str | None,
            strawberry.argument(name="annotationLabel_Description_Contains"),
        ] = strawberry.UNSET,
        annotation_label__label_type: Annotated[
            enums.AnnotationsAnnotationLabelLabelTypeChoices | None,
            strawberry.argument(name="annotationLabel_LabelType"),
        ] = strawberry.UNSET,
        analysis__isnull: Annotated[
            bool | None, strawberry.argument(name="analysis_Isnull")
        ] = strawberry.UNSET,
        document_id: Annotated[
            strawberry.ID | None, strawberry.argument(name="documentId")
        ] = strawberry.UNSET,
        corpus_id: Annotated[
            strawberry.ID | None, strawberry.argument(name="corpusId")
        ] = strawberry.UNSET,
        structural: Annotated[
            bool | None, strawberry.argument(name="structural")
        ] = strawberry.UNSET,
        uses_label_from_labelset_id: Annotated[
            str | None, strawberry.argument(name="usesLabelFromLabelsetId")
        ] = strawberry.UNSET,
        created_by_analysis_ids: Annotated[
            str | None, strawberry.argument(name="createdByAnalysisIds")
        ] = strawberry.UNSET,
        created_with_analyzer_id: Annotated[
            str | None, strawberry.argument(name="createdWithAnalyzerId")
        ] = strawberry.UNSET,
        order_by: Annotated[
            str | None, strawberry.argument(name="orderBy", description="Ordering")
        ] = strawberry.UNSET,
    ) -> AnnotationTypeConnection:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
                "raw_text__contains": raw_text__contains,
                "annotation_label_id": annotation_label_id,
                "annotation_label__text": annotation_label__text,
                "annotation_label__text__contains": annotation_label__text__contains,
                "annotation_label__description__contains": annotation_label__description__contains,
                "annotation_label__label_type": annotation_label__label_type,
                "analysis__isnull": analysis__isnull,
                "document_id": document_id,
                "corpus_id": corpus_id,
                "structural": structural,
                "uses_label_from_labelset_id": uses_label_from_labelset_id,
                "created_by_analysis_ids": created_by_analysis_ids,
                "created_with_analyzer_id": created_with_analyzer_id,
                "order_by": order_by,
            }
        )
        resolved = getattr(self, "source_annotations", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="AnnotationType",
            filterset_class=setup_filterset(AnnotationFilter),
            filter_args={
                "raw_text__contains": "raw_text__contains",
                "annotation_label_id": "annotation_label_id",
                "annotation_label__text": "annotation_label__text",
                "annotation_label__text__contains": "annotation_label__text__contains",
                "annotation_label__description__contains": "annotation_label__description__contains",
                "annotation_label__label_type": "annotation_label__label_type",
                "analysis__isnull": "analysis__isnull",
                "document_id": "document_id",
                "corpus_id": "corpus_id",
                "structural": "structural",
                "uses_label_from_labelset_id": "uses_label_from_labelset_id",
                "created_by_analysis_ids": "created_by_analysis_ids",
                "created_with_analyzer_id": "created_with_analyzer_id",
                "order_by": "order_by",
            },
        )

    @strawberry.field(name="targetAnnotations")
    def target_annotations(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
        raw_text__contains: Annotated[
            str | None, strawberry.argument(name="rawText_Contains")
        ] = strawberry.UNSET,
        annotation_label_id: Annotated[
            strawberry.ID | None, strawberry.argument(name="annotationLabelId")
        ] = strawberry.UNSET,
        annotation_label__text: Annotated[
            str | None, strawberry.argument(name="annotationLabel_Text")
        ] = strawberry.UNSET,
        annotation_label__text__contains: Annotated[
            str | None, strawberry.argument(name="annotationLabel_Text_Contains")
        ] = strawberry.UNSET,
        annotation_label__description__contains: Annotated[
            str | None,
            strawberry.argument(name="annotationLabel_Description_Contains"),
        ] = strawberry.UNSET,
        annotation_label__label_type: Annotated[
            enums.AnnotationsAnnotationLabelLabelTypeChoices | None,
            strawberry.argument(name="annotationLabel_LabelType"),
        ] = strawberry.UNSET,
        analysis__isnull: Annotated[
            bool | None, strawberry.argument(name="analysis_Isnull")
        ] = strawberry.UNSET,
        document_id: Annotated[
            strawberry.ID | None, strawberry.argument(name="documentId")
        ] = strawberry.UNSET,
        corpus_id: Annotated[
            strawberry.ID | None, strawberry.argument(name="corpusId")
        ] = strawberry.UNSET,
        structural: Annotated[
            bool | None, strawberry.argument(name="structural")
        ] = strawberry.UNSET,
        uses_label_from_labelset_id: Annotated[
            str | None, strawberry.argument(name="usesLabelFromLabelsetId")
        ] = strawberry.UNSET,
        created_by_analysis_ids: Annotated[
            str | None, strawberry.argument(name="createdByAnalysisIds")
        ] = strawberry.UNSET,
        created_with_analyzer_id: Annotated[
            str | None, strawberry.argument(name="createdWithAnalyzerId")
        ] = strawberry.UNSET,
        order_by: Annotated[
            str | None, strawberry.argument(name="orderBy", description="Ordering")
        ] = strawberry.UNSET,
    ) -> AnnotationTypeConnection:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
                "raw_text__contains": raw_text__contains,
                "annotation_label_id": annotation_label_id,
                "annotation_label__text": annotation_label__text,
                "annotation_label__text__contains": annotation_label__text__contains,
                "annotation_label__description__contains": annotation_label__description__contains,
                "annotation_label__label_type": annotation_label__label_type,
                "analysis__isnull": analysis__isnull,
                "document_id": document_id,
                "corpus_id": corpus_id,
                "structural": structural,
                "uses_label_from_labelset_id": uses_label_from_labelset_id,
                "created_by_analysis_ids": created_by_analysis_ids,
                "created_with_analyzer_id": created_with_analyzer_id,
                "order_by": order_by,
            }
        )
        resolved = getattr(self, "target_annotations", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="AnnotationType",
            filterset_class=setup_filterset(AnnotationFilter),
            filter_args={
                "raw_text__contains": "raw_text__contains",
                "annotation_label_id": "annotation_label_id",
                "annotation_label__text": "annotation_label__text",
                "annotation_label__text__contains": "annotation_label__text__contains",
                "annotation_label__description__contains": "annotation_label__description__contains",
                "annotation_label__label_type": "annotation_label__label_type",
                "analysis__isnull": "analysis__isnull",
                "document_id": "document_id",
                "corpus_id": "corpus_id",
                "structural": "structural",
                "uses_label_from_labelset_id": "uses_label_from_labelset_id",
                "created_by_analysis_ids": "created_by_analysis_ids",
                "created_with_analyzer_id": "created_with_analyzer_id",
                "order_by": "order_by",
            },
        )

    analyzer: None | (
        Annotated[AnalyzerType, strawberry.lazy("config.graphql.extract_types")]
    ) = strawberry.field(name="analyzer", default=None)
    analysis: None | (
        Annotated[AnalysisType, strawberry.lazy("config.graphql.extract_types")]
    ) = strawberry.field(name="analysis", default=None)
    created_by_analysis: None | (
        Annotated[AnalysisType, strawberry.lazy("config.graphql.extract_types")]
    ) = strawberry.field(
        name="createdByAnalysis",
        description="If set, this relationship is private to the analysis that created it",
        default=None,
    )
    created_by_extract: None | (
        Annotated[ExtractType, strawberry.lazy("config.graphql.extract_types")]
    ) = strawberry.field(
        name="createdByExtract",
        description="If set, this relationship is private to the extract that created it",
        default=None,
    )
    structural: bool = strawberry.field(name="structural", default=None)
    is_public: bool = strawberry.field(name="isPublic", default=None)
    creator: Annotated[UserType, strawberry.lazy("config.graphql.user_types")] = (
        strawberry.field(name="creator", default=None)
    )
    created: datetime.datetime = strawberry.field(name="created", default=None)
    modified: datetime.datetime = strawberry.field(name="modified", default=None)

    @strawberry.field(name="assignmentSet")
    def assignment_set(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> Annotated[
        AssignmentTypeConnection, strawberry.lazy("config.graphql.user_types")
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "assignment_set", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="AssignmentType",
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


def _get_node_RelationshipType(info, pk):
    """Permission-aware node resolution for the singular ``relationship(id:)``
    field (IDOR guard). Mirrors the graphene resolver's
    ``BaseService.filter_visible(Relationship, ...).get(id=pk)``: returns None
    when the object is absent OR not visible to the caller, which surfaces as
    the standard not-found error and never leaks existence across the
    permission boundary. Without this hook, ``get_node_from_global_id`` falls
    back to an UNFILTERED ``.get(pk=pk)``.
    """
    if pk is None:
        return None
    return BaseService.get_or_none(
        Relationship, pk, info.context.user, request=info.context
    )


register_type(
    "RelationshipType",
    RelationshipType,
    model=Relationship,
    get_node=_get_node_RelationshipType,
)


RelationshipTypeConnection = make_connection_types(
    RelationshipType,
    type_name="RelationshipTypeConnection",
    countable=True,
    pdf_page_aware=False,
)


@strawberry.type(
    name="CorpusReferenceType",
    description="Read-only view of an enrichment cross-reference.\n\nNo ``AnnotatePermissionsForReadMixin``: ``CorpusReference`` has no guardian\npermission tables — visibility derives from the parent corpus and is\nenforced by ``CorpusReferenceService`` in the resolver.",
)
class CorpusReferenceType(Node):
    user_lock: None | (
        Annotated[UserType, strawberry.lazy("config.graphql.user_types")]
    ) = strawberry.field(name="userLock", default=None)
    backend_lock: bool = strawberry.field(name="backendLock", default=None)
    is_public: bool = strawberry.field(name="isPublic", default=None)
    creator: Annotated[UserType, strawberry.lazy("config.graphql.user_types")] = (
        strawberry.field(name="creator", default=None)
    )
    created: datetime.datetime = strawberry.field(name="created", default=None)
    modified: datetime.datetime = strawberry.field(name="modified", default=None)
    corpus: Annotated[CorpusType, strawberry.lazy("config.graphql.corpus_types")] = (
        strawberry.field(name="corpus", default=None)
    )

    @strawberry.field(name="referenceType")
    def reference_type(
        self, info: strawberry.Info
    ) -> enums.AnnotationsCorpusReferenceReferenceTypeChoices:
        return coerce_enum(
            enums.AnnotationsCorpusReferenceReferenceTypeChoices,
            getattr(self, "reference_type", None),
        )

    source_annotation: AnnotationType = strawberry.field(
        name="sourceAnnotation", default=None
    )

    @strawberry.field(name="targetAnnotation")
    def target_annotation(self, info: strawberry.Info) -> AnnotationType | None:
        return resolve_visible_fk(self, info, "target_annotation_id", "AnnotationType")

    @strawberry.field(name="targetDocument")
    def target_document(
        self, info: strawberry.Info
    ) -> None | (
        Annotated[DocumentType, strawberry.lazy("config.graphql.document_types")]
    ):
        # Cross-corpus enrichment references point at documents in corpora the
        # caller may not see (the governance graph degrades these to "ghost"
        # nodes). graphene returned null for an invisible target; preserve that.
        return resolve_visible_fk(self, info, "target_document_id", "DocumentType")

    @strawberry.field(name="targetCorpus")
    def target_corpus(
        self, info: strawberry.Info
    ) -> None | (Annotated[CorpusType, strawberry.lazy("config.graphql.corpus_types")]):
        return resolve_visible_fk(self, info, "target_corpus_id", "CorpusType")

    @strawberry.field(name="canonicalKey")
    def canonical_key(self, info: strawberry.Info) -> str | None:
        return coerce_str(getattr(self, "canonical_key", None))

    normalized_data: GenericScalar | None = strawberry.field(
        name="normalizedData", default=None
    )
    confidence: float = strawberry.field(name="confidence", default=None)

    @strawberry.field(name="jurisdiction")
    def jurisdiction(self, info: strawberry.Info) -> str | None:
        return coerce_str(getattr(self, "jurisdiction", None))

    @strawberry.field(name="authorityType")
    def authority_type(
        self, info: strawberry.Info
    ) -> enums.AnnotationsCorpusReferenceAuthorityTypeChoices | None:
        return coerce_enum(
            enums.AnnotationsCorpusReferenceAuthorityTypeChoices,
            getattr(self, "authority_type", None),
        )

    @strawberry.field(name="detectionTier")
    def detection_tier(
        self, info: strawberry.Info
    ) -> enums.AnnotationsCorpusReferenceDetectionTierChoices:
        return coerce_enum(
            enums.AnnotationsCorpusReferenceDetectionTierChoices,
            getattr(self, "detection_tier", None),
        )

    detection_confidence: float = strawberry.field(
        name="detectionConfidence", default=None
    )

    @strawberry.field(name="resolutionStatus")
    def resolution_status(
        self, info: strawberry.Info
    ) -> enums.AnnotationsCorpusReferenceResolutionStatusChoices:
        return coerce_enum(
            enums.AnnotationsCorpusReferenceResolutionStatusChoices,
            getattr(self, "resolution_status", None),
        )

    created_by_analysis: None | (
        Annotated[AnalysisType, strawberry.lazy("config.graphql.extract_types")]
    ) = strawberry.field(name="createdByAnalysis", default=None)
    is_provisional: bool = strawberry.field(name="isProvisional", default=None)


register_type("CorpusReferenceType", CorpusReferenceType, model=CorpusReference)


CorpusReferenceTypeConnection = make_connection_types(
    CorpusReferenceType,
    type_name="CorpusReferenceTypeConnection",
    countable=True,
    pdf_page_aware=False,
)


def _resolve_NoteType_revisions(root, info):
    """Returns all revisions for this note, ordered by version."""
    return root.revisions.all()


def _resolve_NoteType_descendants_tree(root, info):
    """
    Returns a flat list of descendant notes,
    each including only the IDs of its immediate children.
    """
    from django_cte import CTE, with_cte

    def get_descendants(cte):
        base_qs = Note.objects.filter(parent_id=root.id).values(
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


def _resolve_NoteType_full_tree(root, info):
    """
    Returns a flat list of notes from the root ancestor,
    each including only the IDs of its immediate children.
    """
    from django_cte import CTE, with_cte

    # Find the root ancestor
    tree_root = root
    while tree_root.parent_id is not None:
        tree_root = tree_root.parent

    def get_full_tree(cte):
        base_qs = Note.objects.filter(id=tree_root.id).values(
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


def _resolve_NoteType_subtree(root, info):
    """
    Returns a combined tree that includes:
    - The path from the root ancestor to this note (ancestors).
    - This note and all its descendants.
    """
    from django_cte import CTE, with_cte

    # Find all ancestors up to the root
    ancestors = []
    node = root
    while node.parent_id is not None:
        ancestors.append(node)
        node = node.parent
    ancestors.append(node)  # Include the root ancestor
    ancestor_ids = [ancestor.id for ancestor in ancestors]

    # Get all descendants of the current node
    def get_descendants(cte):
        base_qs = Note.objects.filter(parent_id=root.id).values(
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
    subtree = build_flat_tree(subtree_nodes, type_name="NoteType", text_key="content")
    return subtree


def _resolve_NoteType_current_version(root, info):
    """Returns the current version number."""
    latest_revision = root.revisions.order_by("-version").first()
    return latest_revision.version if latest_revision else 0


def _resolve_NoteType_content_preview(root, info):
    annotated = getattr(root, "content_preview", None)
    if annotated is not None:
        return annotated
    return (root.content or "")[:400]


@strawberry.type(
    name="NoteType",
    description="GraphQL type for the Note model with tree-based functionality.",
)
class NoteType(Node):
    user_lock: None | (
        Annotated[UserType, strawberry.lazy("config.graphql.user_types")]
    ) = strawberry.field(name="userLock", default=None)
    backend_lock: bool = strawberry.field(name="backendLock", default=None)

    @strawberry.field(name="title")
    def title(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "title", None))

    @strawberry.field(name="content")
    def content(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "content", None))

    parent: NoteType | None = strawberry.field(name="parent", default=None)
    corpus: None | (
        Annotated[CorpusType, strawberry.lazy("config.graphql.corpus_types")]
    ) = strawberry.field(name="corpus", default=None)
    document: Annotated[
        DocumentType, strawberry.lazy("config.graphql.document_types")
    ] = strawberry.field(name="document", default=None)
    annotation: AnnotationType | None = strawberry.field(
        name="annotation", default=None
    )
    is_public: bool = strawberry.field(name="isPublic", default=None)
    creator: Annotated[UserType, strawberry.lazy("config.graphql.user_types")] = (
        strawberry.field(name="creator", default=None)
    )
    created: datetime.datetime = strawberry.field(name="created", default=None)
    modified: datetime.datetime = strawberry.field(name="modified", default=None)

    @strawberry.field(name="children")
    def children(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> NoteTypeConnection:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "children", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="NoteType",
        )

    @strawberry.field(
        name="revisions",
        description="List of all revisions/versions of this note, ordered by version.",
    )
    def revisions(self, info: strawberry.Info) -> list[NoteRevisionType | None] | None:
        kwargs = strip_unset({})
        return _resolve_NoteType_revisions(self, info, **kwargs)

    @strawberry.field(name="myPermissions")
    def my_permissions(self, info: strawberry.Info) -> GenericScalar | None:
        return core_permissions.resolve_my_permissions(self, info)

    @strawberry.field(name="isPublished")
    def is_published(self, info: strawberry.Info) -> bool | None:
        return core_permissions.resolve_is_published(self, info)

    @strawberry.field(name="objectSharedWith")
    def object_shared_with(self, info: strawberry.Info) -> GenericScalar | None:
        return core_permissions.resolve_object_shared_with(self, info)

    @strawberry.field(
        name="descendantsTree",
        description="List of descendant notes, each with immediate children's IDs.",
    )
    def descendants_tree(
        self, info: strawberry.Info
    ) -> list[GenericScalar | None] | None:
        kwargs = strip_unset({})
        return _resolve_NoteType_descendants_tree(self, info, **kwargs)

    @strawberry.field(
        name="fullTree",
        description="List of notes from the root ancestor, each with immediate children's IDs.",
    )
    def full_tree(self, info: strawberry.Info) -> list[GenericScalar | None] | None:
        kwargs = strip_unset({})
        return _resolve_NoteType_full_tree(self, info, **kwargs)

    @strawberry.field(
        name="subtree",
        description="List representing the path from the root ancestor to this note and its descendants.",
    )
    def subtree(self, info: strawberry.Info) -> list[GenericScalar | None] | None:
        kwargs = strip_unset({})
        return _resolve_NoteType_subtree(self, info, **kwargs)

    @strawberry.field(
        name="currentVersion", description="Current version number of the note"
    )
    def current_version(self, info: strawberry.Info) -> int | None:
        kwargs = strip_unset({})
        return _resolve_NoteType_current_version(self, info, **kwargs)

    @strawberry.field(
        name="contentPreview",
        description="First 400 characters of the note body for list/search previews. Resolvers may annotate the queryset with `content_preview` to avoid shipping the full body over the wire.",
    )
    def content_preview(self, info: strawberry.Info) -> str | None:
        kwargs = strip_unset({})
        return _resolve_NoteType_content_preview(self, info, **kwargs)


def _get_queryset_NoteType(queryset, info):
    # Route visibility through the service layer (BaseService) so this
    # type field resolver does not touch Tier-0 directly. Uses
    # ``filter_visible_qs`` so the visibility filter chains on the
    # incoming queryset/manager in a single SQL pass.
    return BaseService.filter_visible_qs(
        queryset, info.context.user, request=info.context
    )


register_type("NoteType", NoteType, model=Note, get_queryset=_get_queryset_NoteType)


NoteTypeConnection = make_connection_types(
    NoteType, type_name="NoteTypeConnection", countable=True, pdf_page_aware=False
)


@strawberry.type(
    name="NoteRevisionType",
    description="GraphQL type for the NoteRevision model to expose note version history.",
)
class NoteRevisionType(Node):
    note: NoteType = strawberry.field(name="note", default=None)
    author: None | (
        Annotated[UserType, strawberry.lazy("config.graphql.user_types")]
    ) = strawberry.field(name="author", default=None)
    version: int = strawberry.field(name="version", default=None)

    @strawberry.field(name="diff")
    def diff(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "diff", None))

    @strawberry.field(name="snapshot")
    def snapshot(self, info: strawberry.Info) -> str | None:
        return coerce_str(getattr(self, "snapshot", None))

    @strawberry.field(name="checksumBase")
    def checksum_base(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "checksum_base", None))

    @strawberry.field(name="checksumFull")
    def checksum_full(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "checksum_full", None))

    created: datetime.datetime = strawberry.field(name="created", default=None)


register_type("NoteRevisionType", NoteRevisionType, model=NoteRevision)


NoteRevisionTypeConnection = make_connection_types(
    NoteRevisionType,
    type_name="NoteRevisionTypeConnection",
    countable=True,
    pdf_page_aware=False,
)


def _resolve_AuthorityNamespaceNode_aliases(root, info):
    return root.aliases or []


def _resolve_AuthorityNamespaceNode_scope(root, info):
    return "global" if root.is_global else "corpus"


def _resolve_AuthorityNamespaceNode_equivalence_count(root, info) -> int:
    kp = f"{root.prefix}:"
    return AuthorityKeyEquivalence.objects.filter(
        Q(from_key__startswith=kp) | Q(to_key__startswith=kp)
    ).count()


def _resolve_AuthorityNamespaceNode_frontier_count(root, info) -> int:
    return AuthorityFrontier.objects.filter(authority=root.prefix).count()


def _resolve_AuthorityNamespaceNode_reference_count(root, info) -> int:
    return CorpusReference.objects.filter(
        canonical_key__startswith=f"{root.prefix}:"
    ).count()


def _resolve_AuthorityNamespaceNode_effective_provider(root, info):
    from opencontractserver.enrichment.services import AuthorityNamespaceService

    return AuthorityNamespaceService._effective_provider(root.prefix)


def _resolve_AuthorityNamespaceNode_created_by_username(root, info):
    return root.created_by.username if root.created_by_id else None


@strawberry.type(
    name="AuthorityNamespaceNode",
    description="One ``AuthorityNamespace`` row: a body of law (canonical-key prefix) whose\n``aliases`` drive Tier-1 citation extraction.\n\nGlobal reference data with no per-object permissions, so the connection is\n**superuser-only**: ``get_queryset`` returns nothing for everyone else and\norders by ``prefix``. The ``*_count`` and ``effective_provider`` fields are\nstring-joined to the other authority models on demand (graphene resolves\nthem only when selected, so the master list pays only for what it shows).",
)
class AuthorityNamespaceNode(Node):
    @strawberry.field(name="prefix")
    def prefix(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "prefix", None))

    @strawberry.field(name="displayName")
    def display_name(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "display_name", None))

    @strawberry.field(name="jurisdiction")
    def jurisdiction(self, info: strawberry.Info) -> str | None:
        return coerce_str(getattr(self, "jurisdiction", None))

    @strawberry.field(name="provider")
    def provider(self, info: strawberry.Info) -> str | None:
        return coerce_str(getattr(self, "provider", None))

    @strawberry.field(name="sourceRootUrl")
    def source_root_url(self, info: strawberry.Info) -> str | None:
        return coerce_str(getattr(self, "source_root_url", None))

    @strawberry.field(name="license")
    def license(self, info: strawberry.Info) -> str | None:
        return coerce_str(getattr(self, "license", None))

    @strawberry.field(name="baselineOrigin")
    def baseline_origin(self, info: strawberry.Info) -> str | None:
        return coerce_str(getattr(self, "baseline_origin", None))

    is_global: bool = strawberry.field(name="isGlobal", default=None)

    @strawberry.field(name="authorityCorpus")
    def authority_corpus(
        self, info: strawberry.Info
    ) -> None | (Annotated[CorpusType, strawberry.lazy("config.graphql.corpus_types")]):
        return resolve_visible_fk(self, info, "authority_corpus_id", "CorpusType")

    created: datetime.datetime = strawberry.field(name="created", default=None)
    modified: datetime.datetime = strawberry.field(name="modified", default=None)

    @strawberry.field(
        name="aliases", description="Lowercased surface forms feeding extraction."
    )
    def aliases(self, info: strawberry.Info) -> list[str | None] | None:
        kwargs = strip_unset({})
        return _resolve_AuthorityNamespaceNode_aliases(self, info, **kwargs)

    @strawberry.field(name="source", description="'baseline' or 'manual' (ownership).")
    def source(self, info: strawberry.Info) -> str | None:
        return coerce_str(getattr(self, "source", None))

    @strawberry.field(name="authorityType", description="Raw authority_type value.")
    def authority_type(self, info: strawberry.Info) -> str | None:
        return coerce_str(getattr(self, "authority_type", None))

    @strawberry.field(name="scope", description="'global' or 'corpus' (derived).")
    def scope(self, info: strawberry.Info) -> str | None:
        kwargs = strip_unset({})
        return _resolve_AuthorityNamespaceNode_scope(self, info, **kwargs)

    @strawberry.field(
        name="equivalenceCount",
        description="Key-equivalences whose from/to key is under this prefix.",
    )
    def equivalence_count(self, info: strawberry.Info) -> int | None:
        kwargs = strip_unset({})
        return _resolve_AuthorityNamespaceNode_equivalence_count(self, info, **kwargs)

    @strawberry.field(
        name="frontierCount", description="Discovery-queue rows for this authority."
    )
    def frontier_count(self, info: strawberry.Info) -> int | None:
        kwargs = strip_unset({})
        return _resolve_AuthorityNamespaceNode_frontier_count(self, info, **kwargs)

    @strawberry.field(
        name="referenceCount",
        description="CorpusReferences whose canonical_key is under this prefix.",
    )
    def reference_count(self, info: strawberry.Info) -> int | None:
        kwargs = strip_unset({})
        return _resolve_AuthorityNamespaceNode_reference_count(self, info, **kwargs)

    @strawberry.field(
        name="effectiveProvider",
        description="Registry class-name that would actually handle this prefix (by can_handle/priority) — contrast with the advisory 'provider' column. Null when no provider can handle it.",
    )
    def effective_provider(self, info: strawberry.Info) -> str | None:
        kwargs = strip_unset({})
        return _resolve_AuthorityNamespaceNode_effective_provider(self, info, **kwargs)

    @strawberry.field(
        name="createdByUsername",
        description="Curator who created/edited this manual row (else null).",
    )
    def created_by_username(self, info: strawberry.Info) -> str | None:
        kwargs = strip_unset({})
        return _resolve_AuthorityNamespaceNode_created_by_username(self, info, **kwargs)


def _get_queryset_AuthorityNamespaceNode(queryset: QuerySet, info: Any) -> QuerySet:
    user = getattr(info.context, "user", None)
    if not is_authority_admin(user):
        return queryset.none()
    return queryset.select_related("authority_corpus", "created_by").order_by("prefix")


register_type(
    "AuthorityNamespaceNode",
    AuthorityNamespaceNode,
    model=AuthorityNamespace,
    get_queryset=_get_queryset_AuthorityNamespaceNode,
)


AuthorityNamespaceNodeConnection = make_connection_types(
    AuthorityNamespaceNode,
    type_name="AuthorityNamespaceNodeConnection",
    countable=True,
    pdf_page_aware=False,
)


def _frontier_predicted_provider(row):
    """Provider class-name that would handle ``row.canonical_key`` (or ``None``).

    Memoized on the row instance so the ``ingestable`` and ``predicted_provider``
    resolvers share a single registry+equivalence lookup per node. ``row`` is the
    ``AuthorityFrontier`` MODEL instance graphene passes as the resolver root
    (NOT an ``AuthorityFrontierNode``), so this MUST be a free function — a method
    defined on the type is invisible on the model-instance root.
    """
    if not hasattr(row, "_predicted_provider_cache"):
        from opencontractserver.enrichment.services.authority_discovery_service import (  # noqa: E501
            AuthorityDiscoveryService,
        )

        row._predicted_provider_cache = AuthorityDiscoveryService._provider_for(
            row.canonical_key
        )[0]
    return row._predicted_provider_cache


def _resolve_AuthorityFrontierNode_ingestable(root, info) -> bool:
    return _frontier_predicted_provider(root) is not None


def _resolve_AuthorityFrontierNode_predicted_provider(root, info):
    return _frontier_predicted_provider(root)


@strawberry.type(
    name="AuthorityFrontierNode",
    description="One ``AuthorityFrontier`` row: the discovery/ingestion state of a wanted\nsection-root canonical key (e.g. ``usc-15:78j``), aggregated instance-wide\nacross all corpora.\n\n``AuthorityFrontier`` is a system-managed global queue with no per-object\npermissions, so the connection is **superuser-only**: ``get_queryset``\nreturns nothing for everyone else and sets the backlog-first default order\n(``-mention_count``, matching the model's index).",
)
class AuthorityFrontierNode(Node):
    @strawberry.field(name="canonicalKey")
    def canonical_key(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "canonical_key", None))

    @strawberry.field(name="authority")
    def authority(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "authority", None))

    @strawberry.field(name="jurisdiction")
    def jurisdiction(self, info: strawberry.Info) -> str | None:
        return coerce_str(getattr(self, "jurisdiction", None))

    @strawberry.field(name="authorityType")
    def authority_type(
        self, info: strawberry.Info
    ) -> enums.AnnotationsAuthorityFrontierAuthorityTypeChoices | None:
        return coerce_enum(
            enums.AnnotationsAuthorityFrontierAuthorityTypeChoices,
            getattr(self, "authority_type", None),
        )

    mention_count: int = strawberry.field(name="mentionCount", default=None)
    distinct_corpus_count: int = strawberry.field(
        name="distinctCorpusCount", default=None
    )

    @strawberry.field(name="discoveryState")
    def discovery_state(
        self, info: strawberry.Info
    ) -> enums.AnnotationsAuthorityFrontierDiscoveryStateChoices:
        return coerce_enum(
            enums.AnnotationsAuthorityFrontierDiscoveryStateChoices,
            getattr(self, "discovery_state", None),
        )

    depth: int = strawberry.field(name="depth", default=None)

    @strawberry.field(name="provider")
    def provider(self, info: strawberry.Info) -> str | None:
        return coerce_str(getattr(self, "provider", None))

    @strawberry.field(name="lastError")
    def last_error(self, info: strawberry.Info) -> str | None:
        return coerce_str(getattr(self, "last_error", None))

    last_attempt: datetime.datetime | None = strawberry.field(
        name="lastAttempt", default=None
    )
    created: datetime.datetime = strawberry.field(name="created", default=None)
    modified: datetime.datetime = strawberry.field(name="modified", default=None)
    candidate_sources: GenericScalar | None = strawberry.field(
        name="candidateSources",
        description="Per-corpus demand breakdown: [{corpus_id, mention_count, top_detection_tier}].",
        default=None,
    )
    ingested_document: None | (
        Annotated[DocumentType, strawberry.lazy("config.graphql.document_types")]
    ) = strawberry.field(
        name="ingestedDocument",
        description="The Document imported for this key once ingested (else null).",
        default=None,
    )

    @strawberry.field(
        name="ingestable",
        description="True if a source provider can_handle this key directly or via an AuthorityKeyEquivalence bridge (i.e. discovery could ingest it). False keys would record 'unsupported' if run.",
    )
    def ingestable(self, info: strawberry.Info) -> bool | None:
        kwargs = strip_unset({})
        return _resolve_AuthorityFrontierNode_ingestable(self, info, **kwargs)

    @strawberry.field(
        name="predictedProvider",
        description="Registry class name of the provider that would handle this key, or null when none can.",
    )
    def predicted_provider(self, info: strawberry.Info) -> str | None:
        kwargs = strip_unset({})
        return _resolve_AuthorityFrontierNode_predicted_provider(self, info, **kwargs)


def _get_queryset_AuthorityFrontierNode(queryset: QuerySet, info: Any) -> QuerySet:
    user = getattr(info.context, "user", None)
    if not is_authority_admin(user):
        return queryset.none()
    # Backlog-first by default (most-cited wanted authorities lead); the
    # ``-mention_count, discovery_state`` index backs this ordering.
    return queryset.select_related("ingested_document").order_by(
        "-mention_count", "discovery_state"
    )


register_type(
    "AuthorityFrontierNode",
    AuthorityFrontierNode,
    model=AuthorityFrontier,
    get_queryset=_get_queryset_AuthorityFrontierNode,
)


AuthorityFrontierNodeConnection = make_connection_types(
    AuthorityFrontierNode,
    type_name="AuthorityFrontierNodeConnection",
    countable=True,
    pdf_page_aware=False,
)


def _resolve_AuthorityKeyEquivalenceNode_editable(root, info) -> bool:
    return root.source == MANUAL_SOURCE


def _resolve_AuthorityKeyEquivalenceNode_created_by_username(root, info):
    return root.created_by.username if root.created_by_id else None


@strawberry.type(
    name="AuthorityKeyEquivalenceNode",
    description='One ``AuthorityKeyEquivalence`` row (canonical-key synonym) for the\nruntime authority-mappings admin panel.\n\nGlobal system data with no per-object permissions, so the connection is\n**superuser-only**: ``get_queryset`` returns nothing for everyone else and\nsets the default order (most-recently-modified first). ``editable`` is True\nonly for ``source="manual"`` rows — loader/importer-owned rows\n(``baseline`` / ``popular_name`` / ``uslm``) are read-only.',
)
class AuthorityKeyEquivalenceNode(Node):
    @strawberry.field(name="fromKey")
    def from_key(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "from_key", None))

    @strawberry.field(name="toKey")
    def to_key(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "to_key", None))

    @strawberry.field(name="source")
    def source(
        self, info: strawberry.Info
    ) -> enums.AnnotationsAuthorityKeyEquivalenceSourceChoices:
        return coerce_enum(
            enums.AnnotationsAuthorityKeyEquivalenceSourceChoices,
            getattr(self, "source", None),
        )

    confidence: float = strawberry.field(name="confidence", default=None)

    @strawberry.field(name="note")
    def note(self, info: strawberry.Info) -> str | None:
        return coerce_str(getattr(self, "note", None))

    created: datetime.datetime = strawberry.field(name="created", default=None)
    modified: datetime.datetime = strawberry.field(name="modified", default=None)

    @strawberry.field(
        name="editable",
        description="True iff this is a manual row the curator may edit/delete.",
    )
    def editable(self, info: strawberry.Info) -> bool | None:
        kwargs = strip_unset({})
        return _resolve_AuthorityKeyEquivalenceNode_editable(self, info, **kwargs)

    @strawberry.field(
        name="createdByUsername",
        description="Username of the curator who created this manual row (else null).",
    )
    def created_by_username(self, info: strawberry.Info) -> str | None:
        kwargs = strip_unset({})
        return _resolve_AuthorityKeyEquivalenceNode_created_by_username(
            self, info, **kwargs
        )


def _get_queryset_AuthorityKeyEquivalenceNode(
    queryset: QuerySet, info: Any
) -> QuerySet:
    user = getattr(info.context, "user", None)
    if not is_authority_admin(user):
        return queryset.none()
    return queryset.select_related("created_by").order_by("-modified")


register_type(
    "AuthorityKeyEquivalenceNode",
    AuthorityKeyEquivalenceNode,
    model=AuthorityKeyEquivalence,
    get_queryset=_get_queryset_AuthorityKeyEquivalenceNode,
)


AuthorityKeyEquivalenceNodeConnection = make_connection_types(
    AuthorityKeyEquivalenceNode,
    type_name="AuthorityKeyEquivalenceNodeConnection",
    countable=True,
    pdf_page_aware=False,
)


@strawberry.type(
    name="GovernanceGraphType",
    description="The corpus-scoped reference web in node-link form.\n\nBuilt by ``GovernanceGraphService`` from corpus-as-gate ``CorpusReference``\nrows + permission-filtered ``DocumentRelationship`` rows, with every\nsurfaced document independently READ-checked (invisible targets degrade to\nexternal ghost nodes). Counts describe the full visible graph; the\nnode/edge lists may be degree-capped (``truncated``).",
)
class GovernanceGraphType:
    corpora: list[GovernanceGraphCorpusType] = strawberry.field(
        name="corpora", default=None
    )
    nodes: list[GovernanceGraphNodeType] = strawberry.field(name="nodes", default=None)
    edges: list[GovernanceGraphEdgeType] = strawberry.field(name="edges", default=None)
    document_count: int = strawberry.field(
        name="documentCount",
        description="Distinct visible document nodes (pre-cap).",
        default=None,
    )
    external_key_count: int = strawberry.field(
        name="externalKeyCount",
        description="Distinct external ghost nodes (pre-cap).",
        default=None,
    )
    edge_count: int = strawberry.field(
        name="edgeCount",
        description="Distinct edges in the full graph (pre-cap).",
        default=None,
    )
    mention_count: int = strawberry.field(
        name="mentionCount",
        description="Total reference mentions across all edges.",
        default=None,
    )
    truncated: bool = strawberry.field(
        name="truncated",
        description="True when nodes/edges were dropped to honor the node cap.",
        default=None,
    )


register_type("GovernanceGraphType", GovernanceGraphType, model=None)


@strawberry.type(
    name="GovernanceGraphCorpusType",
    description="A corpus participating in the governance graph (filing or authority).",
)
class GovernanceGraphCorpusType:
    id: strawberry.ID = strawberry.field(
        name="id", description="Global CorpusType id.", default=None
    )
    title: str | None = strawberry.field(name="title", default=None)
    kind: str = strawberry.field(
        name="kind",
        description='"filing" or "authority" (cited body of law).',
        default=None,
    )


register_type("GovernanceGraphCorpusType", GovernanceGraphCorpusType, model=None)


@strawberry.type(
    name="GovernanceGraphNodeType",
    description="One governance-graph node: a document or an external-citation ghost.",
)
class GovernanceGraphNodeType:
    id: str = strawberry.field(
        name="id",
        description='Node id: the global DocumentType id for document nodes, or "key:<canonical_key>" for external ghost nodes.',
        default=None,
    )
    document_id: strawberry.ID | None = strawberry.field(
        name="documentId",
        description="Global DocumentType id (null for external ghost nodes).",
        default=None,
    )
    title: str | None = strawberry.field(
        name="title",
        description="Document title, or the canonical key for ghost nodes.",
        default=None,
    )
    kind: str = strawberry.field(
        name="kind",
        description='"primary", "exhibit", "statute" or "external".',
        default=None,
    )
    corpus_id: strawberry.ID | None = strawberry.field(
        name="corpusId",
        description="Global CorpusType id of the node's corpus (null for ghosts).",
        default=None,
    )
    authority: str | None = strawberry.field(
        name="authority",
        description='Body-of-law key prefix (e.g. "dgcl") for statute/ghost nodes.',
        default=None,
    )
    jurisdiction: str | None = strawberry.field(
        name="jurisdiction",
        description='Jurisdiction code, e.g. "us-de", "us-federal" (null if unknown).',
        default=None,
    )
    authority_type: str | None = strawberry.field(
        name="authorityType",
        description='Authority type: "statute", "regulation", etc. (null if unknown).',
        default=None,
    )
    discovery_state: str | None = strawberry.field(
        name="discoveryState",
        description='Authority-frontier crawl status for ghost nodes: "queued", "in_progress", "ingested", "failed", "unsupported", "blocked_license", "blocked_domain", "unlocated", "pending_approval", "deferred_cap" — or null when not tracked.',
        default=None,
    )
    degree: int = strawberry.field(
        name="degree",
        description="Summed mention weight of edges touching the node.",
        default=None,
    )


register_type("GovernanceGraphNodeType", GovernanceGraphNodeType, model=None)


@strawberry.type(
    name="GovernanceGraphEdgeType",
    description="One weighted reference edge between two governance-graph nodes.",
)
class GovernanceGraphEdgeType:
    source: str = strawberry.field(
        name="source", description="Source node id.", default=None
    )
    target: str = strawberry.field(
        name="target", description="Target node id.", default=None
    )
    edge_type: str = strawberry.field(
        name="edgeType",
        description='"LAW", "LAW_EXTERNAL" or "DOCUMENT".',
        default=None,
    )
    weight: int = strawberry.field(
        name="weight", description="Mention count.", default=None
    )


register_type("GovernanceGraphEdgeType", GovernanceGraphEdgeType, model=None)


@strawberry.type(
    name="WantedAuthorityType",
    description="One authority worth bootstrapping, ranked by citation demand.\n\nAggregated by ``CorpusReferenceService.wanted_authorities`` from EXTERNAL\nlaw references visible to the requesting user — the actionable backlog\nbehind the governance graph's ghost nodes.",
)
class WantedAuthorityType:
    authority: str = strawberry.field(
        name="authority", description='Authority prefix, e.g. "dgcl".', default=None
    )
    mention_count: int = strawberry.field(
        name="mentionCount",
        description="Total EXTERNAL mentions for this authority.",
        default=None,
    )
    key_count: int = strawberry.field(
        name="keyCount", description="Distinct section-root keys cited.", default=None
    )
    corpus_count: int = strawberry.field(
        name="corpusCount",
        description="Distinct corpora with unresolved citations.",
        default=None,
    )
    top_keys: list[WantedAuthorityKeyType] = strawberry.field(
        name="topKeys",
        description="Most-cited missing keys (capped server-side).",
        default=None,
    )


register_type("WantedAuthorityType", WantedAuthorityType, model=None)


@strawberry.type(
    name="WantedAuthorityKeyType",
    description="One missing canonical key (rolled up to its section root).",
)
class WantedAuthorityKeyType:
    canonical_key: str = strawberry.field(
        name="canonicalKey",
        description='Section-root canonical key, e.g. "dgcl:145".',
        default=None,
    )
    mention_count: int = strawberry.field(
        name="mentionCount",
        description="EXTERNAL mentions citing this key.",
        default=None,
    )
    corpus_count: int = strawberry.field(
        name="corpusCount",
        description="Distinct corpora citing this key.",
        default=None,
    )


register_type("WantedAuthorityKeyType", WantedAuthorityKeyType, model=None)


@strawberry.type(
    name="AuthorityFrontierStatsType",
    description="Facet-aware summary counts for the authority-sources monitor's chips.\n\nCounts honour the non-state facets (jurisdiction / authority_type /\nprovider / search) but NOT the state filter, so the chips always show the\nfull state breakdown for the current facet selection.",
)
class AuthorityFrontierStatsType:
    total_count: int = strawberry.field(
        name="totalCount",
        description="Total frontier rows matching the non-state facets.",
        default=None,
    )
    by_state: list[AuthorityFrontierStateCountType] = strawberry.field(
        name="byState",
        description="Row count per discovery_state (only non-empty states).",
        default=None,
    )


register_type("AuthorityFrontierStatsType", AuthorityFrontierStatsType, model=None)


@strawberry.type(
    name="AuthorityFrontierStateCountType",
    description="One ``discovery_state`` and how many frontier rows are in it.",
)
class AuthorityFrontierStateCountType:
    state: str = strawberry.field(
        name="state", description="discovery_state value.", default=None
    )
    count: int = strawberry.field(name="count", default=None)


register_type(
    "AuthorityFrontierStateCountType", AuthorityFrontierStateCountType, model=None
)


@strawberry.type(
    name="AuthorityMappingStatsType",
    description="Per-``source`` summary counts for the authority-mappings panel chips.\n\nHonours the ``search`` facet but NOT a source filter, so the chips always\nshow the full source breakdown for the current search.",
)
class AuthorityMappingStatsType:
    total_count: int = strawberry.field(
        name="totalCount",
        description="Total equivalence rows matching the search.",
        default=None,
    )
    by_source: list[AuthorityMappingSourceCountType] = strawberry.field(
        name="bySource",
        description="Row count per source (only non-empty sources).",
        default=None,
    )


register_type("AuthorityMappingStatsType", AuthorityMappingStatsType, model=None)


@strawberry.type(
    name="AuthorityMappingSourceCountType",
    description="One ``source`` value and how many equivalence rows carry it.",
)
class AuthorityMappingSourceCountType:
    source: str = strawberry.field(
        name="source", description="source value.", default=None
    )
    count: int = strawberry.field(name="count", default=None)


register_type(
    "AuthorityMappingSourceCountType", AuthorityMappingSourceCountType, model=None
)


@strawberry.type(
    name="AuthorityNamespaceStatsType",
    description="Faceted summary counts for the registry panel's chips.\n\nHonours ``search`` but not the facet selects, so chips show the full\nbreakdown for the current search (mirrors ``AuthorityMappingStatsType``).",
)
class AuthorityNamespaceStatsType:
    total_count: int = strawberry.field(name="totalCount", default=None)
    by_jurisdiction: list[AuthorityNamespaceFacetCountType] = strawberry.field(
        name="byJurisdiction", default=None
    )
    by_authority_type: list[AuthorityNamespaceFacetCountType] = strawberry.field(
        name="byAuthorityType", default=None
    )
    by_scope: list[AuthorityNamespaceFacetCountType] = strawberry.field(
        name="byScope", default=None
    )


register_type("AuthorityNamespaceStatsType", AuthorityNamespaceStatsType, model=None)


@strawberry.type(
    name="AuthorityNamespaceFacetCountType",
    description="One facet value (jurisdiction / authority_type / scope) and its row count.",
)
class AuthorityNamespaceFacetCountType:
    value: str | None = strawberry.field(
        name="value",
        description="The facet value (null collapses to '').",
        default=None,
    )
    count: int = strawberry.field(name="count", default=None)


register_type(
    "AuthorityNamespaceFacetCountType", AuthorityNamespaceFacetCountType, model=None
)


@strawberry.type(
    name="AuthorityDetailType",
    description="Everything about one body of law, string-joined across the authority models.\n\nThe console's single-authority view. Superuser-gated at the service layer\n(``AuthorityNamespaceService.detail``); the nested node types are returned as\npre-fetched instances, so their own connection gates are not re-applied (the\nservice already enforced access).",
)
class AuthorityDetailType:
    namespace: AuthorityNamespaceNode = strawberry.field(name="namespace", default=None)
    equivalences_out: list[AuthorityKeyEquivalenceNode] = strawberry.field(
        name="equivalencesOut",
        description="Equivalences FROM a key under this prefix.",
        default=None,
    )
    equivalences_in: list[AuthorityKeyEquivalenceNode] = strawberry.field(
        name="equivalencesIn",
        description="Equivalences TO a key under this prefix.",
        default=None,
    )
    frontier_rows: list[AuthorityFrontierNode] = strawberry.field(
        name="frontierRows", default=None
    )
    frontier_state_counts: list[AuthorityFrontierStateCountType] = strawberry.field(
        name="frontierStateCounts", default=None
    )
    reference_total: int = strawberry.field(name="referenceTotal", default=None)
    reference_status_counts: list[AuthorityReferenceStatusCountType] = strawberry.field(
        name="referenceStatusCounts", default=None
    )
    reference_sample: list[CorpusReferenceType] = strawberry.field(
        name="referenceSample",
        description="Most-recent references under this prefix (capped).",
        default=None,
    )
    effective_provider: str | None = strawberry.field(
        name="effectiveProvider", default=None
    )


register_type("AuthorityDetailType", AuthorityDetailType, model=None)


@strawberry.type(
    name="AuthorityReferenceStatusCountType",
    description="One ``resolution_status`` and how many references under a prefix carry it.",
)
class AuthorityReferenceStatusCountType:
    status: str = strawberry.field(name="status", default=None)
    count: int = strawberry.field(name="count", default=None)


register_type(
    "AuthorityReferenceStatusCountType", AuthorityReferenceStatusCountType, model=None
)


@strawberry.type(
    name="AuthoritySourceProviderType",
    description="One registered authority source provider (a \"scraper\").\n\nThe auto-discovered provider classes (US Code / eCFR / Federal Register /\nagentic web locator) surfaced read-only for the console's Scrapers tab —\nthey have no DB row, so this is a registry projection. ``has_credentials``\nreflects whether the encrypted-secrets vault holds anything for this\nprovider's class path (credentials are edited via the existing\n``updateComponentSecrets`` mutation, not here).",
)
class AuthoritySourceProviderType:
    name: str = strawberry.field(
        name="name", description="Registry class name.", default=None
    )
    class_name: str | None = strawberry.field(
        name="className", description="Full module.ClassName path.", default=None
    )
    title: str | None = strawberry.field(name="title", default=None)
    supported_prefixes: list[str | None] = strawberry.field(
        name="supportedPrefixes", default=None
    )
    license: str | None = strawberry.field(name="license", default=None)
    priority: int | None = strawberry.field(name="priority", default=None)
    requires_approval: bool = strawberry.field(name="requiresApproval", default=None)
    enabled: bool = strawberry.field(name="enabled", default=None)
    has_credentials: bool = strawberry.field(name="hasCredentials", default=None)


register_type("AuthoritySourceProviderType", AuthoritySourceProviderType, model=None)


def q_authority_frontier(
    info: strawberry.Info,
    offset: Annotated[
        int | None, strawberry.argument(name="offset")
    ] = strawberry.UNSET,
    before: Annotated[
        str | None, strawberry.argument(name="before")
    ] = strawberry.UNSET,
    after: Annotated[str | None, strawberry.argument(name="after")] = strawberry.UNSET,
    first: Annotated[int | None, strawberry.argument(name="first")] = strawberry.UNSET,
    last: Annotated[int | None, strawberry.argument(name="last")] = strawberry.UNSET,
    jurisdiction: Annotated[
        str | None, strawberry.argument(name="jurisdiction")
    ] = strawberry.UNSET,
    provider: Annotated[
        str | None, strawberry.argument(name="provider")
    ] = strawberry.UNSET,
    authority: Annotated[
        str | None, strawberry.argument(name="authority")
    ] = strawberry.UNSET,
    discovery_state: Annotated[
        str | None, strawberry.argument(name="discoveryState")
    ] = strawberry.UNSET,
    authority_type: Annotated[
        str | None, strawberry.argument(name="authorityType")
    ] = strawberry.UNSET,
    search: Annotated[
        str | None, strawberry.argument(name="search")
    ] = strawberry.UNSET,
) -> AuthorityFrontierNodeConnection | None:
    kwargs = strip_unset(
        {
            "offset": offset,
            "before": before,
            "after": after,
            "first": first,
            "last": last,
            "jurisdiction": jurisdiction,
            "provider": provider,
            "authority": authority,
            "discovery_state": discovery_state,
            "authority_type": authority_type,
            "search": search,
        }
    )
    resolved = None
    return resolve_django_connection(
        resolved=resolved,
        info=info,
        args=kwargs,
        node_type_name="AuthorityFrontierNode",
        default_manager=AuthorityFrontier._default_manager,
        filterset_class=setup_filterset(AuthorityFrontierFilter),
        filter_args={
            "jurisdiction": "jurisdiction",
            "provider": "provider",
            "authority": "authority",
            "discovery_state": "discovery_state",
            "authority_type": "authority_type",
            "search": "search",
        },
    )


def q_authority_key_equivalences(
    info: strawberry.Info,
    offset: Annotated[
        int | None, strawberry.argument(name="offset")
    ] = strawberry.UNSET,
    before: Annotated[
        str | None, strawberry.argument(name="before")
    ] = strawberry.UNSET,
    after: Annotated[str | None, strawberry.argument(name="after")] = strawberry.UNSET,
    first: Annotated[int | None, strawberry.argument(name="first")] = strawberry.UNSET,
    last: Annotated[int | None, strawberry.argument(name="last")] = strawberry.UNSET,
    source: Annotated[
        str | None, strawberry.argument(name="source")
    ] = strawberry.UNSET,
    search: Annotated[
        str | None, strawberry.argument(name="search")
    ] = strawberry.UNSET,
) -> AuthorityKeyEquivalenceNodeConnection | None:
    kwargs = strip_unset(
        {
            "offset": offset,
            "before": before,
            "after": after,
            "first": first,
            "last": last,
            "source": source,
            "search": search,
        }
    )
    resolved = None
    return resolve_django_connection(
        resolved=resolved,
        info=info,
        args=kwargs,
        node_type_name="AuthorityKeyEquivalenceNode",
        default_manager=AuthorityKeyEquivalence._default_manager,
        filterset_class=setup_filterset(AuthorityKeyEquivalenceFilter),
        filter_args={"source": "source", "search": "search"},
    )


def q_authority_namespaces(
    info: strawberry.Info,
    offset: Annotated[
        int | None, strawberry.argument(name="offset")
    ] = strawberry.UNSET,
    before: Annotated[
        str | None, strawberry.argument(name="before")
    ] = strawberry.UNSET,
    after: Annotated[str | None, strawberry.argument(name="after")] = strawberry.UNSET,
    first: Annotated[int | None, strawberry.argument(name="first")] = strawberry.UNSET,
    last: Annotated[int | None, strawberry.argument(name="last")] = strawberry.UNSET,
    jurisdiction: Annotated[
        str | None, strawberry.argument(name="jurisdiction")
    ] = strawberry.UNSET,
    authority_type: Annotated[
        str | None, strawberry.argument(name="authorityType")
    ] = strawberry.UNSET,
    scope: Annotated[str | None, strawberry.argument(name="scope")] = strawberry.UNSET,
    search: Annotated[
        str | None, strawberry.argument(name="search")
    ] = strawberry.UNSET,
) -> AuthorityNamespaceNodeConnection | None:
    kwargs = strip_unset(
        {
            "offset": offset,
            "before": before,
            "after": after,
            "first": first,
            "last": last,
            "jurisdiction": jurisdiction,
            "authority_type": authority_type,
            "scope": scope,
            "search": search,
        }
    )
    resolved = None
    return resolve_django_connection(
        resolved=resolved,
        info=info,
        args=kwargs,
        node_type_name="AuthorityNamespaceNode",
        default_manager=AuthorityNamespace._default_manager,
        filterset_class=setup_filterset(AuthorityNamespaceFilter),
        filter_args={
            "jurisdiction": "jurisdiction",
            "authority_type": "authority_type",
            "scope": "scope",
            "search": "search",
        },
    )


QUERY_FIELDS = {
    "authority_frontier": strawberry.field(
        resolver=q_authority_frontier,
        name="authorityFrontier",
        description="Global authority-source discovery queue (AuthorityFrontier): the crawl/ingestion state of every wanted section-root key across all corpora, ranked by citation demand. SUPERUSER-ONLY (empty otherwise) — gating + default order live on the node's get_queryset.",
    ),
    "authority_key_equivalences": strawberry.field(
        resolver=q_authority_key_equivalences,
        name="authorityKeyEquivalences",
        description="Runtime authority key-equivalence registry (AuthorityKeyEquivalence): act-section ↔ USC/CFR codification synonyms used to bridge citations across namespaces. SUPERUSER-ONLY (empty otherwise) — gating + default order live on the node's get_queryset.",
    ),
    "authority_namespaces": strawberry.field(
        resolver=q_authority_namespaces,
        name="authorityNamespaces",
        description="The registry of bodies of law (AuthorityNamespace): one row per canonical-key prefix (e.g. 'usc-15', 'dgcl') whose aliases drive Tier-1 citation extraction. SUPERUSER-ONLY (empty otherwise) — gating + default order live on the node's get_queryset.",
    ),
}
