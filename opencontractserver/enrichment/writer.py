"""Persist resolved references as annotations / relationships / CorpusReferences.

All writes for one run happen inside a single transaction under one ``Analysis``
(provenance). Creation is idempotent: re-running enriches only newly-found
references (mentions are deduped by (document, span, label); ``CorpusReference``
rows by their unique (source_annotation, reference_type, canonical_key) guard).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from django.db import transaction

from opencontractserver.annotations.models import (
    RELATIONSHIP_LABEL,
    SPAN_LABEL,
    Annotation,
    CorpusReference,
    Relationship,
)
from opencontractserver.documents.models import DocumentRelationship
from opencontractserver.enrichment import constants as C
from opencontractserver.enrichment.resolver import Resolution

logger = logging.getLogger(__name__)


@dataclass
class WriteResult:
    annotations_created: int = 0
    relationships_created: int = 0
    references_created: int = 0
    document_relationships_created: int = 0
    annotation_ids: list[int] = None  # type: ignore[assignment]
    reference_ids: list[int] = None  # type: ignore[assignment]

    def __post_init__(self):
        if self.annotation_ids is None:
            self.annotation_ids = []
        if self.reference_ids is None:
            self.reference_ids = []


class EnrichmentWriter:
    """Turn :class:`Resolution` objects into durable rows."""

    def __init__(self, corpus, creator_id: int, analysis=None) -> None:
        self.corpus = corpus
        self.creator_id = creator_id
        self.analysis = analysis
        self._label_cache: dict[tuple[str, str], object] = {}

    def _label(self, text: str, label_type: str):
        key = (text, label_type)
        if key not in self._label_cache:
            self._label_cache[key] = self.corpus.ensure_label_and_labelset(
                label_text=text, creator_id=self.creator_id, label_type=label_type
            )
        return self._label_cache[key]

    def _get_or_create_mention(self, res: Resolution) -> tuple[Annotation, bool]:
        cand = res.candidate
        label = self._label(C.LABEL_FOR_TYPE[res.reference_type], SPAN_LABEL)
        json_pos = {"start": cand.start, "end": cand.end}
        # Dedup by (document, label, span START): the span END can legitimately
        # move when the alias registry grows (a longer authority alias wins
        # longest-first matching), and that must not duplicate the mention.
        existing = Annotation.objects.filter(
            document_id=res.source_document_id,
            corpus=self.corpus,
            annotation_label=label,
            json__start=cand.start,
        ).first()
        if existing is not None:
            return existing, False

        data = dict(cand.normalized_data)
        if res.canonical_key:
            data["canonical_key"] = res.canonical_key
        link_url = None
        if res.target_document_id:
            link_url = f"/corpus/{self.corpus.id}/document/{res.target_document_id}"

        ann = Annotation(
            raw_text=cand.raw_text,
            page=1,
            json=json_pos,
            annotation_label=label,
            document_id=res.source_document_id,
            corpus=self.corpus,
            creator_id=self.creator_id,
            annotation_type=SPAN_LABEL,
            structural=False,
            data=data or None,
            link_url=link_url,
            analysis=self.analysis,
        )
        ann.save()
        return ann, True

    def write(self, resolutions: list[Resolution]) -> WriteResult:
        result = WriteResult()
        rel_label = self._label(C.LABEL_RELATIONSHIP, RELATIONSHIP_LABEL)

        with transaction.atomic():
            for res in resolutions:
                mention, created = self._get_or_create_mention(res)
                if created:
                    result.annotations_created += 1
                    result.annotation_ids.append(mention.pk)

                # Within-document section link -> Relationship.
                if (
                    res.reference_type == C.REF_SECTION
                    and res.target_annotation_id is not None
                ):
                    self._ensure_section_relationship(mention, res, rel_label, result)
                    continue

                # Everything else with a cross-boundary/external nature ->
                # CorpusReference. (Offset-only section refs also land here so
                # the resolved target offset is recorded.)
                self._ensure_corpus_reference(mention, res, result)

                # Resolved doc->doc refs additionally roll up to a document-
                # level edge: DocumentRelationship is what the corpus document
                # graph renders (documents = nodes, relationships = edges).
                if (
                    res.reference_type == C.REF_DOCUMENT
                    and res.target_document_id is not None
                ):
                    self._ensure_document_relationship(res, rel_label, result)

        return result

    def _ensure_document_relationship(self, res, rel_label, result):
        _, created = DocumentRelationship.objects.get_or_create(
            source_document_id=res.source_document_id,
            target_document_id=res.target_document_id,
            annotation_label=rel_label,
            relationship_type=C.DOC_REL_RELATIONSHIP,
            defaults={
                "corpus": self.corpus,
                "creator_id": self.creator_id,
                "data": {"analysis_id": self.analysis.id if self.analysis else None},
            },
        )
        if created:
            result.document_relationships_created += 1

    def _ensure_section_relationship(self, mention, res, rel_label, result):
        already = Relationship.objects.filter(
            relationship_label=rel_label,
            document_id=res.source_document_id,
            corpus=self.corpus,
            source_annotations=mention,
            target_annotations__id=res.target_annotation_id,
        ).exists()
        if already:
            return
        rel = Relationship.objects.create(
            relationship_label=rel_label,
            document_id=res.source_document_id,
            corpus=self.corpus,
            creator_id=self.creator_id,
            analysis=self.analysis,
        )
        rel.source_annotations.set([mention])
        rel.target_annotations.set([res.target_annotation_id])
        result.relationships_created += 1

    def _ensure_corpus_reference(self, mention, res, result):
        normalized = dict(res.normalized_data)
        if res.target_offset is not None:
            normalized["target_offset"] = res.target_offset
        ref, created = CorpusReference.objects.get_or_create(
            source_annotation=mention,
            reference_type=res.reference_type,
            canonical_key=res.canonical_key,
            defaults={
                "corpus": self.corpus,
                "target_annotation_id": res.target_annotation_id,
                "target_document_id": res.target_document_id,
                "resolution_status": res.resolution_status,
                "confidence": res.confidence,
                "normalized_data": normalized or None,
                "created_by_analysis": self.analysis,
                "creator_id": self.creator_id,
            },
        )
        if created:
            result.references_created += 1
            result.reference_ids.append(ref.pk)
