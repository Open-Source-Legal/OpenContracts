"""Custom resolvers for optimized GraphQL field access."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

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
        from opencontractserver.annotations.query_optimizer import (
            AnnotationQueryOptimizer,
        )

        optimizer_kwargs = {
            "document_id": self.id,
            "user": getattr(info.context, "user", None),
            "use_cache": True,
        }

        structural = kwargs.get("structural")
        if structural is not None:
            optimizer_kwargs["structural"] = structural

        corpus_pk = _to_pk(kwargs.get("corpusId"))
        if corpus_pk is not None:
            optimizer_kwargs["corpus_id"] = corpus_pk

        return AnnotationQueryOptimizer.get_document_annotations(**optimizer_kwargs)

    prefetched = getattr(self, "_prefetched_doc_annotations", None)
    if prefetched is None:
        prefetched = getattr(self, "_prefetched_annotations", None)

    if prefetched is not None:
        annotations = list(prefetched)
    else:
        optimizer_kwargs = {
            "document_id": self.id,
            "user": getattr(info.context, "user", None),
            "use_cache": True,
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
            AnnotationQueryOptimizer.get_document_annotations(**optimizer_kwargs)
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
