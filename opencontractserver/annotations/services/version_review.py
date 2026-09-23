"""Carry human annotations onto each new document version, then have people check them.

A version-up carries every human annotation on the parent automatically when
its text still matches uniquely (``AUTO``) and flags the rest (``STALE``).
Neither is trusted: both count as pending until a reviewer approves, corrects
or drops them. Relationships follow once all their endpoints have successors.
"""

import json
from typing import Any

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from opencontractserver.annotations.compact_json import (
    compact_annotation_json,
    iter_page_annotations,
)
from opencontractserver.annotations.models import (
    DOC_TYPE_LABEL,
    Annotation,
    AnnotationLabel,
    AnnotationVersionDecision,
    Relationship,
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

Decision = AnnotationVersionDecision.Decision
PENDING = (Decision.AUTO, Decision.STALE)


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
    def _decisions(cls, user, document_id, corpus_id):
        """Carry outcomes onto this version whose original the user can read."""
        document, corpus = cls._scope(user, document_id, corpus_id)
        return AnnotationVersionDecision.objects.filter(
            target_document=document,
            annotation__in=cls._human_visible(user).filter(corpus=corpus),
        )

    @classmethod
    def review(cls, user, document_id, corpus_id):
        return (
            cls._decisions(user, document_id, corpus_id)
            .select_related(
                "annotation__annotation_label",
                "successor__annotation_label",
                "reviewer",
            )
            .order_by("annotation__page", "annotation_id")
        )

    @classmethod
    def pending_count(cls, user, document_id, corpus_id):
        """Carried annotations on the current version that no person has checked."""
        decisions = cls._decisions(user, document_id, corpus_id)
        return decisions.filter(
            decision__in=PENDING, target_document__is_current=True
        ).count()

    @classmethod
    def state_for_annotation(cls, user, annotation, *, request=None):
        """Review state as seen from the annotation's own version.

        An annotation's forward decision (what happened to it on the next
        version) wins; otherwise it reports how it was carried here, so a
        current version shows which annotations are machine-carried and which
        a person confirmed. Fresh annotations report nothing.
        """
        if not annotation.document_id or not annotation.corpus_id:
            return None
        key = (annotation.document_id, annotation.corpus_id)
        cache = getattr(request, "_annotation_version_states", {})
        if key not in cache:
            human = cls._human_visible(user).filter(
                document_id=annotation.document_id, corpus_id=annotation.corpus_id
            )
            decisions = AnnotationVersionDecision.objects
            cache[key] = {
                **dict(
                    decisions.filter(successor__in=human).values_list(
                        "successor_id", "decision"
                    )
                ),
                **dict(
                    decisions.filter(annotation__in=human).values_list(
                        "annotation_id", "decision"
                    )
                ),
            }
            if request is not None:
                request._annotation_version_states = cache
        return cache[key].get(annotation.pk)

    @staticmethod
    def _create_successor(annotation, document, placement, label):
        return Annotation.objects.create(
            document=document,
            corpus_id=annotation.corpus_id,
            creator_id=annotation.creator_id,
            annotation_label=label,
            long_description=annotation.long_description,
            data=annotation.data,
            link_url=annotation.link_url,
            **placement,
        )

    @staticmethod
    def _carry_relationships(document, corpus_id):
        """Copy human relationships whose every endpoint now has a successor here.

        Endpoints are followed through the whole successor chain, so an edge
        whose ends were carried on different hops still lands once both do.
        """
        chain = dict(
            AnnotationVersionDecision.objects.filter(
                target_document__version_tree_id=document.version_tree_id,
                annotation__corpus_id=corpus_id,
                successor__isnull=False,
            ).values_list("annotation_id", "successor_id")
        )
        here = set(
            Annotation.objects.filter(
                document=document, pk__in=chain.values()
            ).values_list("pk", flat=True)
        )
        if not here:
            return

        def resolve(pk):
            seen = set()
            while pk not in here and pk in chain and pk not in seen:
                seen.add(pk)
                pk = chain[pk]
            return pk if pk in here else None

        def endpoints(relationship, carried=False):
            ends = [
                frozenset(resolve(a.pk) if carried else a.pk for a in annotations.all())
                for annotations in (
                    relationship.source_annotations,
                    relationship.target_annotations,
                )
            ]
            return relationship.relationship_label_id, *ends

        related = Relationship.objects.prefetch_related(
            "source_annotations", "target_annotations"
        )
        existing = {
            endpoints(relationship)
            for relationship in related.filter(document=document, corpus_id=corpus_id)
        }
        originals = (
            related.filter(
                Q(source_annotations__in=chain) | Q(target_annotations__in=chain),
                corpus_id=corpus_id,
                structural=False,
                analysis__isnull=True,
                created_by_analysis__isnull=True,
                created_by_extract__isnull=True,
            )
            .exclude(document=document)
            .distinct()
        )
        for relationship in originals:
            key = label, sources, targets = endpoints(relationship, carried=True)
            if not sources or not targets or None in sources | targets:
                continue
            if key in existing:
                continue
            copy = Relationship.objects.create(
                document=document,
                corpus_id=corpus_id,
                relationship_label_id=label,
                creator_id=relationship.creator_id,
            )
            copy.source_annotations.set(sources)
            copy.target_annotations.set(targets)
            existing.add(key)

    @classmethod
    @transaction.atomic
    def carry_version(cls, document):
        """Carry the parent version's human annotations onto ``document``.

        Runs once parsing has finished, as the system: this is a proposal, so
        it records outcomes but never a reviewer. Rows still ``STALE`` on the
        parent move to this version and get a fresh match attempt, so nothing
        is stranded when versions arrive faster than reviews. Versions may
        finish parsing in any order, so a pass into an already superseded
        version still runs and then re-runs its parsed child. Idempotent.
        """
        document = Document.objects.select_for_update().get(pk=document.pk)
        if not document.parent_id or document.backend_lock:
            return
        loaded = cls._load_placement_source(document)
        corpus_ids = (
            DocumentPath.objects.filter(document=document, is_deleted=False)
            .values_list("corpus_id", flat=True)
            .distinct()
        )
        for corpus_id in corpus_ids:
            waiting = AnnotationVersionDecision.objects.filter(
                target_document_id=document.parent_id,
                decision=Decision.STALE,
                annotation__corpus_id=corpus_id,
            ).select_related("annotation__annotation_label")
            fresh = cls.human_annotations(
                Annotation.objects.filter(
                    document_id=document.parent_id,
                    corpus_id=corpus_id,
                    version_decision__isnull=True,
                )
            ).select_related("annotation_label")
            for decision in [
                *waiting,
                *(AnnotationVersionDecision(annotation=a) for a in fresh),
            ]:
                annotation = decision.annotation
                proposal = cls.propose(annotation, document, loaded=loaded)
                decision.target_document = document
                decision.decision = Decision.AUTO if proposal else Decision.STALE
                if proposal:
                    decision.successor = cls._create_successor(
                        annotation, document, proposal, annotation.annotation_label
                    )
                decision.save()
            cls._carry_relationships(document, corpus_id)
        child = Document.objects.filter(
            parent_id=document.pk, backend_lock=False
        ).first()
        if child is not None:
            cls.carry_version(child)

    @classmethod
    def _lock_review(cls, user, annotation_id, target_document_id):
        annotation = cls._human_visible(user).filter(pk=annotation_id).first()
        if annotation is None:
            raise PermissionDenied("Annotation is unavailable.")
        document, corpus = cls._scope(user, target_document_id, annotation.corpus_id)
        for obj in (document, corpus):
            if not cls.user_has(obj, user, PermissionTypes.UPDATE):
                raise PermissionDenied(
                    "Review requires update permission on the document and corpus."
                )
        # Same lock order as ``carry_version``: the version, then the row.
        document = Document.objects.select_for_update().get(pk=document.pk)
        decision = (
            AnnotationVersionDecision.objects.select_for_update(of=("self",))
            .select_related("annotation__annotation_label", "successor")
            .filter(
                annotation_id=annotation.pk,
                target_document=document,
                decision__in=PENDING,
            )
            .first()
        )
        if decision is None or not document.is_current:
            raise ValidationError(
                "This annotation is not awaiting review on the current version."
            )
        return decision, corpus

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

    @staticmethod
    def _close(decision, user, outcome):
        decision.decision = outcome
        decision.reviewer = user
        decision.reviewed_at = timezone.now()
        decision.save()
        return decision

    @classmethod
    @transaction.atomic
    def carry_forward(
        cls, user, annotation_id, target_document_id, *, placement=None, label_id=None
    ):
        """Approve a carried annotation, optionally re-placing it or changing its label."""
        decision, corpus = cls._lock_review(user, annotation_id, target_document_id)
        annotation, document = decision.annotation, decision.target_document
        label = annotation.annotation_label
        if label_id is not None and label_id != annotation.annotation_label_id:
            label = AnnotationLabel.objects.filter(
                pk=label_id, included_in_labelset=corpus.label_set
            ).first()
            if label is None or label.label_type != annotation.annotation_type:
                raise ValidationError("Choose a compatible label from this corpus.")
        if placement is None and decision.successor is None:
            raise ValidationError(
                "No unique exact match. Place this annotation on the new document."
            )
        selected = (
            {}
            if placement is None
            else cls._manual_placement(
                annotation,
                document,
                placement,
                loaded=cls._load_placement_source(document),
            )
        )
        successor = decision.successor
        if successor is None:
            decision.successor = cls._create_successor(
                annotation, document, selected, label
            )
        else:
            for field, value in {**selected, "annotation_label": label}.items():
                setattr(successor, field, value)
            successor.save()
        cls._close(
            decision,
            user,
            (
                Decision.REAPPROVED
                if placement is None and label == annotation.annotation_label
                else Decision.CORRECTED
            ),
        )
        cls._carry_relationships(document, corpus.pk)
        return decision

    @classmethod
    @transaction.atomic
    def drop(cls, user, annotation_id, target_document_id):
        """Reject a carried annotation, removing any successor and edges it leaves empty."""
        decision, _ = cls._lock_review(user, annotation_id, target_document_id)
        if successor := decision.successor:
            touching = list(
                Relationship.objects.filter(
                    Q(source_annotations=successor) | Q(target_annotations=successor)
                ).values_list("pk", flat=True)
            )
            successor.delete()
            decision.successor = None
            Relationship.objects.filter(pk__in=touching).filter(
                Q(source_annotations__isnull=True) | Q(target_annotations__isnull=True)
            ).delete()
        return cls._close(decision, user, Decision.DROPPED)
