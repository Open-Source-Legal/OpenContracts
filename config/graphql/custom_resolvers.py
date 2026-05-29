"""Custom resolvers for optimized GraphQL field access."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from graphql.language import ast as gql_ast
from graphql_relay import from_global_id

from opencontractserver.constants.annotations import MANUAL_ANNOTATION_SENTINEL

# ``DjangoFilterConnectionField`` delivers filter kwargs to the resolver using
# the **Django ORM lookup names** declared in ``AnnotationFilter`` — i.e. the
# snake_case + ``__lookup`` form (``annotation_label__label_type``,
# ``raw_text__contains``, …), NOT the camelCase GraphQL argument names. If this
# set drifts from ``AnnotationFilter``'s declared filters, every request lands
# in the ``extra``-key escape hatch below and returns ``self.doc_annotations.all()``,
# defeating the ``_prefetched_doc_annotations`` prefetch and triggering an N+1
# storm (one COUNT + one SELECT + one annotation_label FK SELECT + one Corpus
# tree-CTE per document). The drift is pinned by
# ``opencontractserver/tests/test_doc_annotations_prefetch.py``.
SUPPORTED_FILTER_KEYS = {
    # AnnotationFilter Meta.fields → Django lookup names
    "annotation_label__label_type",
    "annotation_label_id",
    "annotation_label__text",
    "annotation_label__text__contains",
    "annotation_label__description__contains",
    "raw_text__contains",
    "analysis__isnull",
    "structural",
    "document_id",
    "corpus_id",
    # AnnotationFilter declared method filters
    "created_by_analysis_ids",
    "created_with_analyzer_id",
    "order_by",
    # Relay pagination args
    "first",
    "last",
    "after",
    "before",
    "offset",
}

UNSUPPORTED_FILTER_KEYS = {
    # ``uses_label_from_labelset_id`` requires a labelset M2M join we can't
    # reproduce in Python over the prefetched annotation list — fall back to
    # the queryset path so the ORM can apply it.
    "uses_label_from_labelset_id",
}


def _to_pk(global_id: str | None) -> int | None:
    if not global_id:
        return None
    try:
        _, pk = from_global_id(global_id)
        return int(pk)
    except (ValueError, TypeError):
        return None


def _apply_filter(sequence: Iterable, predicate) -> list:
    return [item for item in sequence if predicate(item)]


def _enum_value(value: Any) -> Any:
    """Unwrap graphene/Python ``Enum`` values to their underlying scalar.

    graphene-django converts Django ``Choices`` fields to GraphQL enums and
    delivers them to the resolver as Python ``Enum`` members. Plain equality
    against the underlying string (e.g. ``label_type == "DOC_TYPE_LABEL"``)
    silently returns ``False`` for enum members because ``enum.Enum`` does not
    compare equal to its value — so every Python-side filter against an enum
    kwarg would drop every row. Normalising once at the top of the filter
    section keeps the resolver's predicates as plain ``==`` comparisons.
    """
    return getattr(value, "value", value)


def resolve_doc_annotations_optimized(self, info, **kwargs) -> Any:
    """Resolve ``docAnnotations`` while favouring prefetched data and the optimizer."""

    if kwargs.get("after") or kwargs.get("before"):
        return self.doc_annotations.all()

    unsupported = {
        key
        for key, value in kwargs.items()
        if value not in (None, "", []) and key in UNSUPPORTED_FILTER_KEYS
    }
    if unsupported:
        return self.doc_annotations.all()

    extra = {
        key
        for key, value in kwargs.items()
        if value not in (None, "", [])
        and key not in SUPPORTED_FILTER_KEYS
        and key not in UNSUPPORTED_FILTER_KEYS
    }
    if extra:
        return self.doc_annotations.all()

    # Check if we have any filters that require list processing
    has_filters = any(
        [
            kwargs.get("annotation_label__label_type"),
            kwargs.get("annotation_label_id"),
            kwargs.get("annotation_label__text"),
            kwargs.get("annotation_label__text__contains"),
            kwargs.get("annotation_label__description__contains"),
            kwargs.get("raw_text__contains"),
            kwargs.get("analysis__isnull") is not None,
            kwargs.get("created_by_analysis_ids"),
            kwargs.get("created_with_analyzer_id"),
            kwargs.get("order_by"),
            kwargs.get("offset"),
            kwargs.get("first"),
            kwargs.get("last"),
        ]
    )

    # If no filters and no special arguments, just return the queryset
    if not has_filters:
        # Use optimizer for permission filtering
        from opencontractserver.annotations.services import AnnotationService

        optimizer_kwargs = {
            "document_id": self.id,
            "user": getattr(info.context, "user", None),
            "context": info.context,
        }

        structural = kwargs.get("structural")
        if structural is not None:
            optimizer_kwargs["structural"] = structural

        corpus_pk = kwargs.get("corpus_id")
        if corpus_pk is not None:
            optimizer_kwargs["corpus_id"] = int(corpus_pk)

        return AnnotationService.get_document_annotations(**optimizer_kwargs)

    prefetched = getattr(self, "_prefetched_doc_annotations", None)
    if prefetched is None:
        prefetched = getattr(self, "_prefetched_annotations", None)

    if prefetched is not None:
        annotations = list(prefetched)
    else:
        from opencontractserver.annotations.services import AnnotationService

        optimizer_kwargs = {
            "document_id": self.id,
            "user": getattr(info.context, "user", None),
            "context": info.context,
        }

        structural = kwargs.get("structural")
        if structural is not None:
            optimizer_kwargs["structural"] = structural

        corpus_pk = kwargs.get("corpus_id")
        if corpus_pk is not None:
            optimizer_kwargs["corpus_id"] = int(corpus_pk)

        annotations = list(
            AnnotationService.get_document_annotations(**optimizer_kwargs)
        )

    if not annotations:
        return self.doc_annotations.none()

    # ``DjangoFilterConnectionField`` wraps this resolver's return value
    # through ``filterset_class(queryset=<iterable>)``, and ``django-filter``
    # reads ``.model`` off the iterable on init (see
    # ``django_filters/filterset.py:196``) — returning a ``list`` here would
    # raise ``AttributeError: 'list' object has no attribute 'model'`` and
    # break the field. The ``pk__in`` re-query is small (the resolver has
    # already narrowed the candidate set in Python) and the ``select_related``
    # mirrors the prefetch in ``_apply_document_prefetches`` so FK descriptors
    # don't fire per row.
    #
    # Note: this path still fires one ``COUNT(*)`` and one ``SELECT`` per
    # parent document because graphene-django's connection wrapper insists on
    # a real ``QuerySet``. The corpus list view's badge case bypasses this
    # field entirely via ``DocumentType.doc_type_labels`` (a plain list field,
    # see ``config/graphql/document_types.py``) — that's where the prefetch is
    # actually consumed. This path is only hit by callers that legitimately
    # need cursor pagination over a document's annotations.
    # Lazy-imported: this fallback ``_as_queryset`` path is only hit when the
    # connection-shaped ``docAnnotations`` is actually requested (rare —
    # ``docTypeLabels`` is the corpus-list shape), so we avoid loading
    # ``annotations.models`` at GraphQL schema-build time.
    from opencontractserver.annotations.models import Annotation

    def _as_queryset(items):
        if not items:
            return self.doc_annotations.none()
        return Annotation.objects.filter(
            pk__in=[item.pk for item in items]
        ).select_related("annotation_label", "corpus", "analysis", "creator")

    label_type = _enum_value(kwargs.get("annotation_label__label_type"))
    if label_type:
        annotations = _apply_filter(
            annotations,
            lambda item: getattr(
                getattr(item, "annotation_label", None), "label_type", None
            )
            == label_type,
        )

    label_id = kwargs.get("annotation_label_id")
    if label_id:
        try:
            pk = int(label_id)
        except (ValueError, TypeError):
            return self.doc_annotations.all()
        annotations = _apply_filter(
            annotations, lambda item: item.annotation_label_id == pk
        )

    label_text = kwargs.get("annotation_label__text")
    if label_text:
        annotations = _apply_filter(
            annotations,
            lambda item: getattr(getattr(item, "annotation_label", None), "text", None)
            == label_text,
        )

    contains_text = kwargs.get("annotation_label__text__contains")
    if contains_text:
        annotations = _apply_filter(
            annotations,
            lambda item: contains_text
            in (getattr(getattr(item, "annotation_label", None), "text", "") or ""),
        )

    contains_description = kwargs.get("annotation_label__description__contains")
    if contains_description:
        annotations = _apply_filter(
            annotations,
            lambda item: contains_description
            in (
                getattr(getattr(item, "annotation_label", None), "description", "")
                or ""
            ),
        )

    raw_text_contains = kwargs.get("raw_text__contains")
    if raw_text_contains:
        annotations = _apply_filter(
            annotations,
            lambda item: raw_text_contains in (getattr(item, "raw_text", "") or ""),
        )

    analysis_isnull = kwargs.get("analysis__isnull")
    if analysis_isnull is not None:
        target = bool(analysis_isnull)
        annotations = _apply_filter(
            annotations,
            lambda item: (item.analysis_id is None) is target,
        )

    corpus_id_value = kwargs.get("corpus_id")
    if corpus_id_value is not None:
        try:
            corpus_pk = int(corpus_id_value)
        except (ValueError, TypeError):
            return self.doc_annotations.all()
        annotations = _apply_filter(
            annotations, lambda item: item.corpus_id == corpus_pk
        )

    created_by = kwargs.get("created_by_analysis_ids")
    if created_by:
        parts = [token.strip() for token in created_by.split(",") if token.strip()]
        include_manual = MANUAL_ANNOTATION_SENTINEL in parts
        analysis_pks: set[int] = set()
        for token in parts:
            if token == MANUAL_ANNOTATION_SENTINEL:
                continue
            analysis_pk = _to_pk(token)
            if analysis_pk is None:
                return self.doc_annotations.all()
            analysis_pks.add(analysis_pk)

        annotations = _apply_filter(
            annotations,
            lambda item: (item.analysis_id in analysis_pks)
            or (include_manual and item.analysis_id is None),
        )

    created_with_analyzer = kwargs.get("created_with_analyzer_id")
    if created_with_analyzer:
        parts = [
            token.strip() for token in created_with_analyzer.split(",") if token.strip()
        ]
        analyzer_pks: set[int] = set()
        for token in parts:
            analyzer_pk = _to_pk(token)
            if analyzer_pk is None:
                return self.doc_annotations.all()
            analyzer_pks.add(analyzer_pk)

        annotations = _apply_filter(
            annotations,
            lambda item: getattr(getattr(item, "analysis", None), "analyzer_id", None)
            in analyzer_pks,
        )

    order_value = kwargs.get("order_by")
    if order_value:
        if "__" in order_value:
            return self.doc_annotations.all()
        reverse = order_value.startswith("-")
        attribute = order_value.lstrip("-")
        try:
            annotations.sort(key=lambda item: getattr(item, attribute), reverse=reverse)
        except AttributeError:
            return self.doc_annotations.all()

    offset = kwargs.get("offset")
    if isinstance(offset, int) and offset > 0:
        annotations = annotations[offset:]

    first = kwargs.get("first")
    if isinstance(first, int) and first >= 0:
        annotations = annotations[:first]

    last = kwargs.get("last")
    if isinstance(last, int) and last >= 0:
        annotations = annotations[-last:] if last else []

    return _as_queryset(annotations)


def _argument_string_value(
    argument: gql_ast.ArgumentNode, variables: dict
) -> str | None:
    """Return the resolved string value of a GraphQL argument node, or None."""
    value_node = argument.value
    if isinstance(value_node, gql_ast.StringValueNode):
        return value_node.value
    if isinstance(value_node, gql_ast.EnumValueNode):
        return value_node.value
    if isinstance(value_node, gql_ast.VariableNode):
        return variables.get(value_node.name.value)
    return None


def _selection_set_iter(
    selection: gql_ast.SelectionNode,
    fragments: dict,
):
    """Yield Field selections directly under ``selection``, traversing fragments."""
    selection_set = getattr(selection, "selection_set", None)
    if selection_set is None:
        return
    for child in selection_set.selections:
        if isinstance(child, gql_ast.FieldNode):
            yield child
        elif isinstance(child, gql_ast.InlineFragmentNode):
            yield from _selection_set_iter(child, fragments)
        elif isinstance(child, gql_ast.FragmentSpreadNode):
            fragment = fragments.get(child.name.value)
            if fragment is not None:
                yield from _selection_set_iter(fragment, fragments)


def requests_doc_type_labels(info) -> bool:
    """
    Return ``True`` when the current GraphQL operation asks for either:

    * ``docTypeLabels`` on each document edge — the flat-list field the
      corpus document-card view actually uses for the DOC_TYPE_LABEL badge
      (see ``DocumentType.resolve_doc_type_labels``). This is the only path
      that consumes ``_prefetched_doc_annotations`` directly and avoids the
      per-row ``COUNT(*)`` + ``SELECT`` + FK descriptor storm.
    * ``docAnnotations(annotationLabel_LabelType: DOC_TYPE_LABEL)`` — the
      legacy connection-shaped field the badge view used to read. Still
      supported because external API consumers may rely on it; the prefetch
      still helps even though graphene-django's connection wrapper insists
      on a real ``QuerySet`` (one ``COUNT(*)`` + one ``SELECT`` per doc
      remain unavoidable on that path).

    Used by ``resolve_documents`` to opt the queryset into a focused prefetch
    (see ``_apply_document_prefetches``) of every doc's DOC_TYPE_LABEL
    annotations + their labels + corpus in one batch SQL.

    The check matches each field by its underlying name regardless of GraphQL
    alias — graphql-core preserves the field name on ``FieldNode.name`` even
    when the client uses ``my_alias: docTypeLabels``.
    """
    from opencontractserver.annotations.models import DOC_TYPE_LABEL

    fragments = getattr(info, "fragments", {}) or {}
    variables = getattr(info, "variable_values", {}) or {}

    for field_node in info.field_nodes or ():
        # Connection: documents → edges → node → docTypeLabels / docAnnotations
        for edges in _selection_set_iter(field_node, fragments):
            if edges.name.value != "edges":
                continue
            for node in _selection_set_iter(edges, fragments):
                if node.name.value != "node":
                    continue
                for child in _selection_set_iter(node, fragments):
                    name = child.name.value
                    if name == "docTypeLabels":
                        # Flat-list field is unconditional; no arg check.
                        return True
                    if name != "docAnnotations":
                        continue
                    for arg in child.arguments or ():
                        if arg.name.value != "annotationLabel_LabelType":
                            continue
                        if _argument_string_value(arg, variables) == DOC_TYPE_LABEL:
                            return True
    return False


# Legacy alias preserved so external callers that imported the old name keep
# working through the rename. New code should import ``requests_doc_type_labels``.
requests_doc_label_annotations = requests_doc_type_labels
