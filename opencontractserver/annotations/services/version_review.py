"""Explicit, permission-checked review of human annotations across one version hop."""

import json
from dataclasses import dataclass
from typing import Any

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Exists, OuterRef

from opencontractserver.annotations.compact_json import (
    compact_annotation_json,
    iter_page_annotations,
)
from opencontractserver.annotations.models import (
    DOC_TYPE_LABEL,
    Annotation,
    AnnotationLabel,
    AnnotationVersionDecision,
)
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document, DocumentPath
from opencontractserver.shared.services.base import BaseService
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.compact_pawls import expand_pawls_pages
from opencontractserver.utils.pdf_token_matching import union_bounds
from opencontractserver.utils.span_projection import (
    load_document_text_and_layer,
    project_span_to_token_annotation,
    span_annotation_payload,
)


@dataclass
class ReviewRow:
    annotation: Annotation
    state: str
    proposed_placement: dict | None = None
    successor: Annotation | None = None
    reviewed_by: object = None
    reviewed_at: object = None


class AnnotationVersionReviewService(BaseService):
    @staticmethod
    def human_annotations(queryset):
        return queryset.filter(
            structural=False,
            structural_set__isnull=True,
            analysis__isnull=True,
            created_by_analysis__isnull=True,
            created_by_extract__isnull=True,
            corpus_action__isnull=True,
            is_grounding_source=False,
        )

    @classmethod
    def _human_visible(cls, user):
        # The general annotation queryset hides superseded paths. This read is
        # explicitly historical; human rows have no analysis/extract privacy.
        if not getattr(user, "is_authenticated", False):
            return Annotation.objects.none()
        return cls.human_annotations(
            Annotation.objects.filter(
                document__in=Document.objects.visible_to_user(user, lightweight=True),
                corpus__in=Corpus.objects.visible_to_user(user),
            )
        )

    @classmethod
    def _scope(cls, user, document_id, corpus_id):
        document = cls.get_or_none(Document, document_id, user)
        corpus = cls.get_or_none(Corpus, corpus_id, user)
        if (
            document is None
            or corpus is None
            or not DocumentPath.objects.filter(
                document=document,
                corpus=corpus,
                is_deleted=False,
            ).exists()
        ):
            raise PermissionDenied("Document or corpus is unavailable.")
        return document, corpus

    @classmethod
    def _successor(cls, user, document_id, corpus_id):
        """The one reviewable target: the current version immediately after this one.

        Every surface asks this question — the annotation badge, the stale
        count, and the mutations that record a decision. They share this
        definition so a row can never be reported reviewable by one and
        rejected by another (an annotation stranded two versions back reports
        no state rather than a ``STALE`` nothing will accept).
        """
        if not document_id:
            return None
        return (
            Document.objects.visible_to_user(user, lightweight=True)
            .filter(
                parent_id=document_id,
                is_current=True,
                path_records__corpus_id=corpus_id,
                path_records__is_current=True,
                path_records__is_deleted=False,
            )
            .order_by("id")
            .first()
        )

    @classmethod
    def _previous(cls, user, document, corpus):
        return (
            cls._human_visible(user)
            .filter(
                document_id=document.parent_id,
                corpus=corpus,
            )
            .select_related("annotation_label")
            if document.parent_id
            else Annotation.objects.none()
        )

    @staticmethod
    def _load_placement_source(document):
        try:
            return load_document_text_and_layer(document)
        except (ValueError, OSError):
            return "", None, None

    @classmethod
    def propose(cls, annotation, document, *, loaded=None):
        """An exact, unique text match is a suggestion; repeated text needs placement."""
        if annotation.annotation_type == DOC_TYPE_LABEL:
            return dict(
                json={},
                page=1,
                raw_text=annotation.raw_text or "",
                annotation_type=DOC_TYPE_LABEL,
            )
        text, layer, annotation_type = loaded or cls._load_placement_source(document)
        raw = annotation.raw_text
        if not raw or not annotation_type:
            return None
        start = text.find(raw)
        if start < 0 or text.find(raw, start + 1) >= 0:
            return None
        end = start + len(raw)
        if layer is None:
            payload, page = span_annotation_payload(start, end, raw)
        else:
            try:
                payload, page, raw = project_span_to_token_annotation(
                    layer,
                    start=start,
                    end=end,
                    text=raw,
                    label_text=(
                        annotation.annotation_label.text
                        if annotation.annotation_label
                        else ""
                    ),
                )
            except ValueError:
                return None
        return dict(
            json=compact_annotation_json(payload),
            page=page,
            raw_text=raw,
            annotation_type=annotation_type,
        )

    @classmethod
    def review(cls, user, document_id, corpus_id):
        document, corpus = cls._scope(user, document_id, corpus_id)
        annotations = cls._previous(user, document, corpus)
        decisions = {
            decision.annotation_id: decision
            for decision in AnnotationVersionDecision.objects.filter(
                target_document=document,
                annotation__in=annotations,
            ).select_related("successor__annotation_label", "creator")
        }
        loaded = cls._load_placement_source(document)
        rows = []
        for annotation in annotations.order_by("page", "id"):
            decision = decisions.get(annotation.pk)
            rows.append(
                ReviewRow(
                    annotation=annotation,
                    state=decision.decision if decision else "STALE",
                    proposed_placement=(
                        None
                        if decision
                        else cls.propose(annotation, document, loaded=loaded)
                    ),
                    successor=decision.successor if decision else None,
                    reviewed_by=decision.creator if decision else None,
                    reviewed_at=decision.created if decision else None,
                )
            )
        return rows

    @classmethod
    def stale_count(cls, user, document_id, corpus_id):
        document, corpus = cls._scope(user, document_id, corpus_id)
        # A badge on a version nothing can be reviewed against is noise.
        if cls._successor(user, document.parent_id, corpus.pk) != document:
            return 0
        decided = AnnotationVersionDecision.objects.filter(
            annotation_id=OuterRef("pk"),
            target_document=document,
        )
        return cls._previous(user, document, corpus).filter(~Exists(decided)).count()

    @classmethod
    def state_for_annotation(cls, user, annotation, *, request=None):
        if not annotation.document_id or not annotation.corpus_id:
            return None
        key = (annotation.document_id, annotation.corpus_id)
        cache = getattr(request, "_annotation_version_states", {})
        if key not in cache:
            states = {}
            if cls.get_or_none(Corpus, annotation.corpus_id, user):
                human = cls._human_visible(user).filter(
                    document_id=annotation.document_id,
                    corpus_id=annotation.corpus_id,
                )
                # A recorded decision is history and always reported. STALE is
                # a call to action, so it is only reported while a successor
                # exists that the review mutations would actually accept.
                if cls._successor(user, annotation.document_id, annotation.corpus_id):
                    states = dict.fromkeys(human.values_list("pk", flat=True), "STALE")
                states.update(
                    AnnotationVersionDecision.objects.filter(annotation__in=human)
                    .order_by("target_document_id")
                    .values_list("annotation_id", "decision")
                )
            cache[key] = states
            if request is not None:
                request._annotation_version_states = cache
        return cache[key].get(annotation.pk)

    @classmethod
    def _lock_review(cls, user, annotation_id, target_document_id):
        annotation = (
            cls._human_visible(user)
            .filter(
                pk=annotation_id,
            )
            .select_related("annotation_label")
            .select_for_update(of=("self",))
            .first()
        )
        if annotation is None:
            raise PermissionDenied("Annotation is unavailable.")
        document, corpus = cls._scope(user, target_document_id, annotation.corpus_id)
        for obj in (document, corpus):
            if not cls.user_has(obj, user, PermissionTypes.UPDATE):
                raise PermissionDenied(
                    "Review requires update permission on the document and corpus."
                )
        document = Document.objects.select_for_update().get(pk=document.pk)
        if cls._successor(user, annotation.document_id, corpus.pk) != document:
            raise ValidationError(
                "Review must target the current, immediately following version."
            )
        if AnnotationVersionDecision.objects.filter(
            annotation=annotation, target_document=document
        ).exists():
            raise ValidationError(
                "This annotation was already reviewed for this version."
            )
        return annotation, document, corpus

    @classmethod
    def _manual_placement(cls, annotation, document, placement, *, loaded):
        """Derive content and bounds from the selected positions on the target."""
        payload = placement.get("json") if isinstance(placement, dict) else None
        if not isinstance(payload, dict):
            raise ValidationError("Select a placement on the new document.")
        if annotation.annotation_type == DOC_TYPE_LABEL:
            return cls.propose(annotation, document, loaded=loaded)
        text, layer, annotation_type = loaded
        if annotation_type is None:
            raise ValidationError(
                "The new document is not ready for annotation placement."
            )
        if layer is None:
            start, end = payload.get("start"), payload.get("end")
            if (
                type(start) is not int
                or type(end) is not int
                or not (0 <= start < end <= len(text))
            ):
                raise ValidationError(
                    "The selected text range is outside the new document."
                )
            raw = text[start:end]
            payload, page = span_annotation_payload(start, end, raw)
        else:
            with document.pawls_parse_file.open("r") as stream:
                pages = expand_pawls_pages(json.load(stream))
            rebuilt: dict[str, dict[str, Any]] = {}
            try:
                for selection in iter_page_annotations(payload):
                    index, indices = selection.page_index, selection.token_indices
                    if index < 0 or index >= len(pages) or not indices:
                        raise ValueError("Invalid page or empty selection")
                    tokens = pages[index]["tokens"]
                    if any(i < 0 or i >= len(tokens) for i in indices):
                        raise ValueError("Invalid token")
                    rebuilt[str(index)] = dict(
                        bounds=union_bounds(tokens, indices),
                        tokensJsons=[
                            dict(pageIndex=index, tokenIndex=i)
                            for i in sorted(set(indices))
                        ],
                        rawText=" ".join(
                            tokens[i].get("text", "") for i in sorted(set(indices))
                        ),
                    )
            except (ValueError, TypeError, KeyError, IndexError) as exc:
                raise ValidationError(
                    "The selected tokens are outside the new document."
                ) from exc
            if not rebuilt:
                raise ValidationError("Select text on the new document.")
            page = min(int(index) for index in rebuilt)
            raw = " ".join(
                rebuilt[index]["rawText"] for index in sorted(rebuilt, key=int)
            )
            payload = compact_annotation_json(rebuilt)
        return dict(
            json=payload, page=page, raw_text=raw, annotation_type=annotation_type
        )

    @classmethod
    @transaction.atomic
    def carry_forward(
        cls, user, annotation_id, target_document_id, *, placement=None, label_id=None
    ):
        annotation, document, corpus = cls._lock_review(
            user, annotation_id, target_document_id
        )
        label = annotation.annotation_label
        if label_id is not None and label_id != annotation.annotation_label_id:
            label = AnnotationLabel.objects.filter(
                pk=label_id, included_in_labelset=corpus.label_set
            ).first()
            if label is None or label.label_type != annotation.annotation_type:
                raise ValidationError("Choose a compatible label from this corpus.")
        # One parse of the target's text/token layer serves both the
        # suggestion and the manual placement — this runs under the review
        # locks, so every extra read holds them longer.
        loaded = cls._load_placement_source(document)
        proposal = cls.propose(annotation, document, loaded=loaded)
        selected = (
            proposal
            if placement is None
            else cls._manual_placement(annotation, document, placement, loaded=loaded)
        )
        if selected is None:
            raise ValidationError(
                "No unique exact match. Place this annotation on the new document."
            )
        successor = Annotation.objects.create(
            document=document,
            corpus=corpus,
            creator=user,
            annotation_label=label,
            long_description=annotation.long_description,
            data=annotation.data,
            link_url=annotation.link_url,
            **selected,
        )
        return AnnotationVersionDecision.objects.create(
            annotation=annotation,
            target_document=document,
            successor=successor,
            creator=user,
            decision=(
                "REAPPROVED"
                if selected == proposal and label == annotation.annotation_label
                else "CORRECTED"
            ),
        )

    @classmethod
    @transaction.atomic
    def drop(cls, user, annotation_id, target_document_id):
        annotation, document, _ = cls._lock_review(
            user, annotation_id, target_document_id
        )
        return AnnotationVersionDecision.objects.create(
            annotation=annotation,
            target_document=document,
            decision="DROPPED",
            creator=user,
        )
