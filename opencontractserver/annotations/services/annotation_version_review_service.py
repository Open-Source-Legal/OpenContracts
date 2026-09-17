"""Review human annotations across a document version-up.

Annotations are never versioned or migrated. After ``import_document`` creates
a new version, every human annotation on the previous version (``parent``) is
**stale** relative to the new one until a reviewer records an
``AnnotationVersionDecision``: re-approve or correct it (which creates an
ordinary successor annotation on the new version) or drop it. This service is
the single entry point for that workflow — the GraphQL query, the two
mutations, the stale count on the version badge and the per-annotation state
chip all read through it. Design: ``docs/architecture/reference-web-versioning.md``
(change 5).

Only the parent hop is reviewed: v3 reviews v2's human annotations (successors
included), never v1's.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from django.db import transaction
from django.db.models import QuerySet

from opencontractserver.annotations.models import (
    SPAN_LABEL,
    TOKEN_LABEL,
    Annotation,
    AnnotationLabel,
    AnnotationVersionDecision,
)
from opencontractserver.constants.annotations import (
    ANNOTATION_VERSION_DECISION_CORRECTED,
    ANNOTATION_VERSION_DECISION_DROPPED,
    ANNOTATION_VERSION_DECISION_REAPPROVED,
    ANNOTATION_VERSION_STATE_STALE,
)
from opencontractserver.documents.models import Document
from opencontractserver.shared.services.base import BaseService
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.span_projection import (
    load_document_text_and_layer,
    project_span_to_token_annotation,
    span_annotation_payload,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProposedPlacement:
    """Where an annotation's exact text reappears in the new version."""

    json: dict
    page: int
    annotation_type: str
    raw_text: str
    start: int
    end: int


@dataclass(frozen=True)
class ReviewEntry:
    annotation: Annotation
    state: str
    decision: AnnotationVersionDecision | None
    proposal: ProposedPlacement | None


class AnnotationVersionReviewService(BaseService):
    """Stale / re-approved / corrected / dropped for annotations across versions."""

    # ------------------------------------------------------------------ #
    # Reads                                                                #
    # ------------------------------------------------------------------ #

    @staticmethod
    def human_annotations(document_id: int, corpus_id: int | None = None) -> QuerySet:
        """Non-structural annotations a person made on ``document_id``.

        Machine-made rows (analysis, extract, corpus-action, enrichment
        mentions) are re-derived on the new version by their producers and
        are never review items.
        """
        qs = Annotation.objects.filter(
            document_id=document_id,
            structural=False,
            analysis__isnull=True,
            created_by_analysis__isnull=True,
            created_by_extract__isnull=True,
            corpus_action__isnull=True,
        )
        if corpus_id is not None:
            qs = qs.filter(corpus_id=corpus_id)
        return qs.select_related("annotation_label").order_by("page", "id")

    @classmethod
    def decisions_for(
        cls, target_document_id: int
    ) -> dict[int, AnnotationVersionDecision]:
        """``{annotation_id: decision}`` for every decision recorded against
        ``target_document_id`` (one query)."""
        return {
            d.annotation_id: d
            for d in AnnotationVersionDecision.objects.filter(
                target_document_id=target_document_id
            ).select_related("successor")
        }

    @classmethod
    def entries(
        cls,
        user,
        document: Document,
        corpus_id: int | None = None,
        *,
        with_proposals: bool = True,
    ) -> list[ReviewEntry]:
        """Every human annotation on ``document.parent`` with its state relative
        to ``document``; STALE entries carry a proposed placement.

        ``document`` must be visible to ``user`` (callers resolve it through
        :meth:`BaseService.get_or_none`). Returns ``[]`` when there is no
        previous version.
        """
        if document.parent_id is None:
            return []
        annotations = list(
            cls._reviewable(user, cls.human_annotations(document.parent_id, corpus_id))
        )
        if not annotations:
            return []
        decisions = cls.decisions_for(document.id)
        locator = cls._Locator(document) if with_proposals else None
        out: list[ReviewEntry] = []
        for ann in annotations:
            decision = decisions.get(ann.id)
            if decision is not None:
                out.append(ReviewEntry(ann, decision.decision, decision, None))
                continue
            proposal = locator.propose(ann) if locator is not None else None
            out.append(ReviewEntry(ann, ANNOTATION_VERSION_STATE_STALE, None, proposal))
        return out

    @classmethod
    def _reviewable(cls, user, qs: QuerySet) -> QuerySet:
        """Visibility gate for annotations on a SUPERSEDED version.

        ``Annotation.objects.visible_to_user`` intentionally hides rows whose
        document has no active path in their corpus (the superseded-version
        set is exactly what current views must not show). Review is the one
        surface that reads them, so it applies the same MIN(document, corpus)
        rule directly: the annotation's document and corpus must be readable
        by the reviewer. Rows are already restricted to human annotations, so
        the analysis/extract privacy gate does not apply.
        """
        from opencontractserver.corpuses.models import Corpus

        visible_docs = cls.filter_visible(Document, user).values("id")
        visible_corpora = cls.filter_visible(Corpus, user).values("id")
        from django.db.models import Q

        return qs.filter(document_id__in=visible_docs).filter(
            Q(corpus__isnull=True) | Q(corpus_id__in=visible_corpora)
        )

    @classmethod
    def get_reviewable_annotation(
        cls, user, annotation_pk, *, request=None
    ) -> Annotation | None:
        """IDOR-safe lookup of a human annotation eligible for review: the same
        ``None`` for a missing pk, a machine-made row, or one whose document
        or corpus the caller cannot read."""
        try:
            pk = int(annotation_pk)
        except (TypeError, ValueError):
            return None
        return (
            cls._reviewable(
                user,
                Annotation.objects.filter(
                    pk=pk,
                    structural=False,
                    analysis__isnull=True,
                    created_by_analysis__isnull=True,
                    created_by_extract__isnull=True,
                    corpus_action__isnull=True,
                ),
            )
            .select_related("annotation_label")
            .first()
        )

    @classmethod
    def stale_count(cls, document: Document, corpus_id: int | None = None) -> int:
        """Human annotations on the previous version with no decision for
        ``document`` — two cheap queries, no text loading."""
        if document.parent_id is None:
            return 0
        return (
            cls.human_annotations(document.parent_id, corpus_id)
            .exclude(version_decisions__target_document_id=document.id)
            .count()
        )

    @classmethod
    def state_for_annotation(
        cls, annotation: Annotation, *, request=None
    ) -> str | None:
        """State of ``annotation`` relative to its document's successor version,
        or ``None`` when it is not a human annotation or no successor exists.

        Memoised per request per document: one lookup of the successor version
        and one of its decisions, whatever the number of annotations rendered.
        """
        if annotation.document_id is None or annotation.structural:
            return None
        if (
            annotation.analysis_id
            or annotation.created_by_analysis_id
            or annotation.created_by_extract_id
            or annotation.corpus_action_id
        ):
            return None
        cache: dict[int, tuple[int | None, dict[int, AnnotationVersionDecision]]]
        cache_attr = "_annotation_version_state_cache"
        cache = getattr(request, cache_attr, None) if request is not None else None
        if cache is None:
            cache = {}
            if request is not None:
                try:
                    setattr(request, cache_attr, cache)
                except AttributeError:
                    pass
        if annotation.document_id not in cache:
            successor = (
                Document.objects.filter(parent_id=annotation.document_id)
                .order_by("-created", "-id")
                .values_list("id", flat=True)
                .first()
            )
            cache[annotation.document_id] = (
                successor,
                cls.decisions_for(successor) if successor is not None else {},
            )
        successor_id, decisions = cache[annotation.document_id]
        if successor_id is None:
            return None
        decision = decisions.get(annotation.id)
        return decision.decision if decision else ANNOTATION_VERSION_STATE_STALE

    # ------------------------------------------------------------------ #
    # Writes                                                               #
    # ------------------------------------------------------------------ #

    @classmethod
    def _check_hop(cls, annotation: Annotation, target_document: Document) -> str:
        if target_document.parent_id != annotation.document_id:
            return (
                "Annotations are reviewed against the next version only: the "
                "target document is not the direct successor of the "
                "annotation's document."
            )
        if AnnotationVersionDecision.objects.filter(
            annotation=annotation, target_document=target_document
        ).exists():
            return "This annotation already has a decision for that version."
        return ""

    @classmethod
    @transaction.atomic
    def carry_forward(
        cls,
        user,
        annotation: Annotation,
        target_document: Document,
        *,
        json: dict,
        page: int,
        annotation_type: str,
        raw_text: str,
        annotation_label: AnnotationLabel | None = None,
        request=None,
    ) -> tuple[AnnotationVersionDecision | None, str]:
        """Create the successor annotation on ``target_document`` and record
        the decision: ``REAPPROVED`` when text and label are unchanged from
        the original, else ``CORRECTED``. Returns ``(decision, error)``.

        Requires UPDATE on ``target_document`` (annotating it).
        """
        error = cls.require_permission(
            target_document, user, PermissionTypes.UPDATE, request=request
        ) or cls._check_hop(annotation, target_document)
        if error:
            return None, error
        if annotation_type not in (SPAN_LABEL, TOKEN_LABEL):
            return None, f"Unsupported annotation type {annotation_type!r}."
        label = annotation_label or annotation.annotation_label
        data = dict(annotation.data or {})
        data.pop("char_span", None)  # offsets belonged to the previous version
        successor = Annotation.objects.create(
            raw_text=raw_text,
            page=page,
            json=json,
            annotation_label=label,
            document=target_document,
            corpus_id=annotation.corpus_id,
            creator=user,
            annotation_type=annotation_type,
            structural=False,
            data=data or None,
            link_url=annotation.link_url,
            is_public=annotation.is_public,
        )
        unchanged = (raw_text or "").strip() == (
            annotation.raw_text or ""
        ).strip() and (label.id if label else None) == annotation.annotation_label_id
        decision = AnnotationVersionDecision.objects.create(
            annotation=annotation,
            target_document=target_document,
            decision=(
                ANNOTATION_VERSION_DECISION_REAPPROVED
                if unchanged
                else ANNOTATION_VERSION_DECISION_CORRECTED
            ),
            successor=successor,
            creator=user,
        )
        return decision, ""

    @classmethod
    def drop(
        cls, user, annotation: Annotation, target_document: Document, *, request=None
    ) -> tuple[AnnotationVersionDecision | None, str]:
        """Record that ``annotation`` no longer applies on ``target_document``."""
        error = cls.require_permission(
            target_document, user, PermissionTypes.UPDATE, request=request
        ) or cls._check_hop(annotation, target_document)
        if error:
            return None, error
        decision = AnnotationVersionDecision.objects.create(
            annotation=annotation,
            target_document=target_document,
            decision=ANNOTATION_VERSION_DECISION_DROPPED,
            creator=user,
        )
        return decision, ""

    # ------------------------------------------------------------------ #
    # Proposed placement                                                   #
    # ------------------------------------------------------------------ #

    class _Locator:
        """Exact-text search over the new version, loaded once per call.

        Plain-text authority sections nearly always match; PDFs project the
        match onto PAWLs tokens with the same helper the enrichment writer
        uses, and fall back to "no proposal" (manual placement) when the text
        layer is missing or the span cannot be projected.
        """

        def __init__(self, document: Document) -> None:
            self.text: str | None = None
            self.layer: Any = None
            try:
                self.text, self.layer, _ = load_document_text_and_layer(document)
            except ValueError as exc:
                logger.info(
                    "Annotation review: no text layer for doc %s (%s); proposals off",
                    document.id,
                    exc,
                )

        @staticmethod
        def _old_start(annotation: Annotation) -> int | None:
            payload = annotation.json if isinstance(annotation.json, dict) else {}
            start = payload.get("start")
            if not isinstance(start, int):
                data = annotation.data if isinstance(annotation.data, dict) else {}
                span = data.get("char_span") or {}
                start = span.get("start") if isinstance(span, dict) else None
            return start if isinstance(start, int) else None

        def propose(self, annotation: Annotation) -> ProposedPlacement | None:
            needle = (annotation.raw_text or "").strip()
            if not needle or not self.text:
                return None
            hits: list[int] = []
            idx = self.text.find(needle)
            while idx != -1:
                hits.append(idx)
                idx = self.text.find(needle, idx + 1)
            if not hits:
                return None
            anchor = self._old_start(annotation)
            start = (
                min(hits, key=lambda h: abs(h - anchor))
                if anchor is not None
                else hits[0]
            )
            end = start + len(needle)
            if self.layer is None:
                payload, page = span_annotation_payload(start, end, needle)
                return ProposedPlacement(payload, page, SPAN_LABEL, needle, start, end)
            try:
                payload, page, raw = project_span_to_token_annotation(
                    self.layer,
                    start=start,
                    end=end,
                    text=needle,
                    label_text=(
                        annotation.annotation_label.text
                        if annotation.annotation_label
                        else ""
                    ),
                )
            except ValueError:
                return None
            return ProposedPlacement(
                payload, page, TOKEN_LABEL, raw or needle, start, end
            )
