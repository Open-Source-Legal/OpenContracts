"""Custom resolvers for optimized GraphQL field access."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from graphql.language import ast as gql_ast
from graphql_relay import from_global_id

from opencontractserver.constants.annotations import MANUAL_ANNOTATION_SENTINEL

SUPPORTED_FILTER_KEYS = {
    "annotationLabel_LabelType",
    "annotationLabelId",
    "annotationLabel_Text",
    "annotationLabel_Text_Contains",
    "annotationLabel_Description_Contains",
    "rawText_Contains",
    "analysis_Isnull",
    "structural",
    "corpusId",
    "createdByAnalysisIds",
    "createdWithAnalyzerId",
    "orderBy",
    "order_by",
    "offset",
    "first",
    "last",
}

UNSUPPORTED_FILTER_KEYS = {
    "usesLabelFromLabelsetId",
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
            kwargs.get("annotationLabel_LabelType"),
            kwargs.get("annotationLabelId"),
            kwargs.get("annotationLabel_Text"),
            kwargs.get("annotationLabel_Text_Contains"),
            kwargs.get("annotationLabel_Description_Contains"),
            kwargs.get("rawText_Contains"),
            kwargs.get("analysis_Isnull") is not None,
            kwargs.get("order"),
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

        corpus_pk = _to_pk(kwargs.get("corpusId"))
        if corpus_pk is not None:
            optimizer_kwargs["corpus_id"] = corpus_pk

        return AnnotationService.get_document_annotations(**optimizer_kwargs)

    prefetched = getattr(self, "_prefetched_doc_annotations", None)
    if prefetched is None:
        prefetched = getattr(self, "_prefetched_annotations", None)

    if prefetched is not None:
        annotations = list(prefetched)
    else:
        optimizer_kwargs = {
            "document_id": self.id,
            "user": getattr(info.context, "user", None),
            "context": info.context,
        }

        structural = kwargs.get("structural")
        if structural is not None:
            optimizer_kwargs["structural"] = structural

        corpus_pk = _to_pk(kwargs.get("corpusId"))
        if kwargs.get("corpusId") and corpus_pk is None:
            return self.doc_annotations.all()
        if corpus_pk is not None:
            optimizer_kwargs["corpus_id"] = corpus_pk

        annotations = list(
            AnnotationService.get_document_annotations(**optimizer_kwargs)
        )

    if not annotations:
        return self.doc_annotations.none()

    label_type = kwargs.get("annotationLabel_LabelType")
    if label_type:
        annotations = _apply_filter(
            annotations,
            lambda item: getattr(
                getattr(item, "annotation_label", None), "label_type", None
            )
            == label_type,
        )

    label_id = kwargs.get("annotationLabelId")
    if label_id:
        pk = _to_pk(label_id)
        if pk is None:
            return self.doc_annotations.all()
        annotations = _apply_filter(
            annotations, lambda item: item.annotation_label_id == pk
        )

    label_text = kwargs.get("annotationLabel_Text")
    if label_text:
        annotations = _apply_filter(
            annotations,
            lambda item: getattr(getattr(item, "annotation_label", None), "text", None)
            == label_text,
        )

    contains_text = kwargs.get("annotationLabel_Text_Contains")
    if contains_text:
        annotations = _apply_filter(
            annotations,
            lambda item: contains_text
            in (getattr(getattr(item, "annotation_label", None), "text", "") or ""),
        )

    contains_description = kwargs.get("annotationLabel_Description_Contains")
    if contains_description:
        annotations = _apply_filter(
            annotations,
            lambda item: contains_description
            in (
                getattr(getattr(item, "annotation_label", None), "description", "")
                or ""
            ),
        )

    raw_text_contains = kwargs.get("rawText_Contains")
    if raw_text_contains:
        annotations = _apply_filter(
            annotations,
            lambda item: raw_text_contains in (getattr(item, "raw_text", "") or ""),
        )

    analysis_isnull = kwargs.get("analysis_Isnull")
    if analysis_isnull is not None:
        target = bool(analysis_isnull)
        annotations = _apply_filter(
            annotations,
            lambda item: (item.analysis_id is None) is target,
        )

    corpus_id_value = kwargs.get("corpusId")
    if corpus_id_value:
        corpus_pk = _to_pk(corpus_id_value)
        if corpus_pk is None:
            return self.doc_annotations.all()
        annotations = _apply_filter(
            annotations, lambda item: item.corpus_id == corpus_pk
        )

    created_by = kwargs.get("createdByAnalysisIds")
    if created_by:
        parts = [token.strip() for token in created_by.split(",") if token.strip()]
        include_manual = MANUAL_ANNOTATION_SENTINEL in parts
        analysis_pks = set()
        for token in parts:
            if token == MANUAL_ANNOTATION_SENTINEL:
                continue
            pk = _to_pk(token)
            if pk is None:
                return self.doc_annotations.all()
            analysis_pks.add(pk)

        annotations = _apply_filter(
            annotations,
            lambda item: (item.analysis_id in analysis_pks)
            or (include_manual and item.analysis_id is None),
        )

    created_with_analyzer = kwargs.get("createdWithAnalyzerId")
    if created_with_analyzer:
        parts = [
            token.strip() for token in created_with_analyzer.split(",") if token.strip()
        ]
        analyzer_pks = set()
        for token in parts:
            pk = _to_pk(token)
            if pk is None:
                return self.doc_annotations.all()
            analyzer_pks.add(pk)

        annotations = _apply_filter(
            annotations,
            lambda item: getattr(getattr(item, "analysis", None), "analyzer_id", None)
            in analyzer_pks,
        )

    order_value = kwargs.get("orderBy") or kwargs.get("order_by")
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

    return annotations


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


def requests_doc_label_annotations(info) -> bool:
    """
    Return True when the current GraphQL operation asks for the
    ``docAnnotations`` field on each document edge with
    ``annotationLabel_LabelType: "DOC_TYPE_LABEL"``.

    Used by ``resolve_documents`` to opt the queryset into a focused
    prefetch (see ``_apply_document_prefetches``) so the per-document
    fall-through in ``resolve_doc_annotations_optimized`` does not fire
    for the corpus list view's DOC_TYPE_LABEL badge.

    The check matches the field name (``docAnnotations``) regardless of
    GraphQL alias — the frontend uses ``doc_label_annotations: docAnnotations(...)``
    and graphql-core preserves the underlying field name on FieldNode.name.
    """
    from opencontractserver.annotations.models import DOC_TYPE_LABEL

    fragments = getattr(info, "fragments", {}) or {}
    variables = getattr(info, "variable_values", {}) or {}

    for field_node in info.field_nodes or ():
        # Connection: documents → edges → node → docAnnotations
        for edges in _selection_set_iter(field_node, fragments):
            if edges.name.value != "edges":
                continue
            for node in _selection_set_iter(edges, fragments):
                if node.name.value != "node":
                    continue
                for child in _selection_set_iter(node, fragments):
                    if child.name.value != "docAnnotations":
                        continue
                    for arg in child.arguments or ():
                        if arg.name.value != "annotationLabel_LabelType":
                            continue
                        if _argument_string_value(arg, variables) == DOC_TYPE_LABEL:
                            return True
    return False
