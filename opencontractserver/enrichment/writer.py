"""Persist resolved references as annotations / relationships / CorpusReferences.

All writes for one run happen inside a single transaction under one ``Analysis``
(provenance). Creation is idempotent: re-running enriches only newly-found
references (mentions are deduped by (document, span, label); ``CorpusReference``
rows by their unique (source_annotation, reference_type, canonical_key) guard
plus a partial constraint covering keyless rows). ``DocumentRelationship``
rollups are a derived projection of the resolved doc->doc references and are
reconciled — created AND pruned — on every run.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from django.db import transaction

from opencontractserver.annotations.models import (
    RELATIONSHIP_LABEL,
    SPAN_LABEL,
    Annotation,
    CorpusReference,
    Relationship,
)
from opencontractserver.documents.models import Document, DocumentRelationship
from opencontractserver.enrichment import constants as C
from opencontractserver.enrichment.resolver import Resolution
from opencontractserver.utils.frontend_paths import document_in_corpus_path

logger = logging.getLogger(__name__)


@dataclass
class WriteResult:
    annotations_created: int = 0
    relationships_created: int = 0
    references_created: int = 0
    document_relationships_created: int = 0
    document_relationships_pruned: int = 0
    annotation_ids: list[int] = field(default_factory=list)
    reference_ids: list[int] = field(default_factory=list)


class EnrichmentWriter:
    """Turn :class:`Resolution` objects into durable rows."""

    def __init__(self, corpus, creator_id: int, analysis=None) -> None:
        self.corpus = corpus
        self.creator_id = creator_id
        self.analysis = analysis
        self._label_cache: dict[tuple[str, str], object] = {}
        # Target-document slugs, prefetched once per write() so mention links
        # can carry the canonical /d/ path without a per-mention query.
        self._doc_slugs: dict[int, str | None] = {}

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
        # select_related keeps CorpusReference's save-time type<->label
        # agreement check query-free for deduped mentions.
        existing = (
            Annotation.objects.filter(
                document_id=res.source_document_id,
                corpus=self.corpus,
                annotation_label=label,
                json__start=cand.start,
            )
            .select_related("annotation_label")
            .first()
        )
        if existing is not None:
            return existing, False

        data = dict(cand.normalized_data)
        if res.canonical_key:
            data["canonical_key"] = res.canonical_key
        link_url = None
        if res.target_document_id:
            # Canonical slug path — the only shape the frontend router serves
            # (any other form falls into the catch-all 404).
            link_url = document_in_corpus_path(
                corpus_creator_slug=self.corpus.creator.slug,
                corpus_slug=self.corpus.slug,
                document_slug=self._doc_slugs.get(res.target_document_id),
            )

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

        target_ids = {r.target_document_id for r in resolutions if r.target_document_id}
        self._doc_slugs = dict(
            Document.objects.filter(id__in=target_ids).values_list("id", "slug")
        )

        with transaction.atomic():
            for res in resolutions:
                mention, created = self._get_or_create_mention(res)
                if created:
                    result.annotations_created += 1
                    result.annotation_ids.append(mention.pk)

                # Defined-term definition sites are mention-only: the
                # OC_REF_TERM annotation carries ``term:<slug>`` in its data
                # and the site has no target (it IS the target). A
                # CorpusReference row adds nothing until usage->definition
                # linking exists.
                if res.reference_type == C.REF_DEFINED_TERM:
                    continue

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

            # Resolved doc->doc refs roll up to document-level edges:
            # DocumentRelationship is what the corpus document graph renders
            # (documents = nodes, relationships = edges).
            self._reconcile_document_graph(rel_label, result)

        return result

    def _reconcile_document_graph(self, rel_label, result):
        """Sync the doc-graph projection with the durable reference truth.

        ``DocumentRelationship`` rollups are a *derived projection* of the
        resolved doc->doc ``CorpusReference`` rows — never a second source of
        truth. Each run rebuilds the projection for this corpus: edges whose
        backing reference disappeared are pruned, missing edges are created.
        Enrichment-owned rows are recognized by the ``analysis_id`` key in
        ``data``; user-authored rows are never deleted, and a user-authored
        row for the same (source, target, label) pair already satisfies the
        projection (no duplicate is added).
        """
        expected = set(
            CorpusReference.objects.filter(
                corpus=self.corpus,
                reference_type=C.REF_DOCUMENT,
                target_document__isnull=False,
            ).values_list("source_annotation__document_id", "target_document_id")
        )

        projection_rows = DocumentRelationship.objects.filter(
            corpus=self.corpus,
            relationship_type=C.DOC_REL_RELATIONSHIP,
            annotation_label=rel_label,
        )
        stale_ids = [
            pk
            for pk, src, tgt, data in projection_rows.values_list(
                "id", "source_document_id", "target_document_id", "data"
            )
            if isinstance(data, dict)
            and "analysis_id" in data  # enrichment-owned only
            and (src, tgt) not in expected
        ]
        if stale_ids:
            DocumentRelationship.objects.filter(id__in=stale_ids).delete()
            result.document_relationships_pruned += len(stale_ids)

        # User-authored rows count toward coverage: don't shadow them.
        covered = set(
            projection_rows.values_list("source_document_id", "target_document_id")
        )
        for src, tgt in sorted(expected - covered):
            # get_or_create (not create): two enrichment runs racing on the
            # same corpus can both compute the same (src, tgt) as missing and
            # would otherwise each INSERT a duplicate edge. Key on the edge's
            # natural identity; creator/data are write-once defaults.
            _, created = DocumentRelationship.objects.get_or_create(
                source_document_id=src,
                target_document_id=tgt,
                annotation_label=rel_label,
                relationship_type=C.DOC_REL_RELATIONSHIP,
                corpus=self.corpus,
                defaults={
                    "creator_id": self.creator_id,
                    "data": {
                        "analysis_id": self.analysis.id if self.analysis else None
                    },
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
