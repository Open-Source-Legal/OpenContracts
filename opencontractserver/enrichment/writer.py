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
from django.db.models import Q

from opencontractserver.annotations.models import (
    RELATIONSHIP_LABEL,
    SPAN_LABEL,
    TOKEN_LABEL,
    Annotation,
    CorpusReference,
    Relationship,
)
from opencontractserver.documents.models import Document, DocumentRelationship
from opencontractserver.enrichment import constants as C
from opencontractserver.enrichment.authorities import (
    classify_canonical_key,
    namespace_classification_cache,
)
from opencontractserver.enrichment.resolver import Resolution
from opencontractserver.utils.frontend_paths import document_in_corpus_path
from opencontractserver.utils.span_projection import (
    load_document_text_and_layer,
    project_span_to_token_annotation,
)

logger = logging.getLogger(__name__)


@dataclass
class WriteResult:
    annotations_created: int = 0
    # Legacy span mentions on PDF documents converged to token mentions.
    annotations_upgraded: int = 0
    relationships_created: int = 0
    references_created: int = 0
    # Existing UNRESOLVED rows upgraded to RESOLVED on re-apply (e.g. a
    # sibling document ingested later, or a resolution-logic fix applied
    # after the row was first written). See _ensure_corpus_reference.
    references_resolved: int = 0
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
        # Per-source-document PlasmaPDF layers (None = not a PDF / unavailable
        # → span fallback). Built lazily and kept for the run: resolutions
        # arrive grouped per document, and a layer is reused by every mention
        # on its document.
        self._pdf_layers: dict[int, object | None] = {}
        # Source text (txt_extract_file) per document — only read when a
        # drifted offset needs the ordinal-occurrence remap below.
        self._src_texts: dict[int, str | None] = {}
        # prefix -> (jurisdiction, authority_type) for the batch being written,
        # so persist-time classification resolves the AuthorityNamespace tier
        # once instead of per CorpusReference row. Populated in write().
        self._ns_class: dict[str, tuple] = {}

    def _label(self, text: str, label_type: str):
        key = (text, label_type)
        if key not in self._label_cache:
            self._label_cache[key] = self.corpus.ensure_label_and_labelset(
                label_text=text, creator_id=self.creator_id, label_type=label_type
            )
        return self._label_cache[key]

    def _layer_for(self, document_id: int):
        """PlasmaPDF translation layer for a PDF source document, or ``None``.

        ``None`` (text/DOCX docs, missing PAWLs, load failure) means the
        mention keeps the char-span representation the TXT renderer consumes.
        """
        if document_id not in self._pdf_layers:
            layer = None
            try:
                doc = Document.objects.get(pk=document_id)
                if (doc.file_type or "").lower() == "application/pdf":
                    _text, layer, _ann_type = load_document_text_and_layer(doc)
            except Exception as exc:
                logger.warning(
                    "Enrichment: PAWLs layer unavailable for doc %s (%s) — "
                    "falling back to span mentions.",
                    document_id,
                    exc,
                )
            self._pdf_layers[document_id] = layer
        return self._pdf_layers[document_id]

    def _project_mention(self, res: Resolution) -> tuple[dict, int] | None:
        """Token payload ``(annotation_json, page)`` for a PDF mention, or
        ``None`` when the mention must stay a char span.

        Guard: the extractor's offsets index ``txt_extract_file``, which the
        parser saves from the translation layer's ``doc_text`` — so the layer
        text at the span MUST equal the candidate's raw text. A mismatch means
        the txt extract drifted from the PAWLs layer (e.g. regenerated by a
        different parser); projecting would paint tokens in the wrong place,
        so keep the trustworthy span representation instead.
        """
        cand = res.candidate
        layer = self._layer_for(res.source_document_id)
        if layer is None:
            return None
        start, end = cand.start, cand.end
        if layer.doc_text[start:end] != cand.raw_text:
            # Whitespace-level drift between txt_extract_file and the PAWLs
            # text is routine on real ingests (page separators, join rules,
            # hard line-wraps) — remap by ordinal occurrence of the mention's
            # raw text, whitespace-insensitively.
            remapped = self._remap_span(res.source_document_id, layer.doc_text, cand)
            if remapped is None:
                logger.warning(
                    "Enrichment: could not locate %r (occurrence-remapped) in "
                    "PAWLs text for doc %s — keeping span mention.",
                    (cand.raw_text or "")[:60],
                    res.source_document_id,
                )
                return None
            start, end = remapped
        try:
            annotation_json, page, _raw = project_span_to_token_annotation(
                layer,
                start=start,
                end=end,
                text=cand.raw_text,
                label_text=C.LABEL_FOR_TYPE[res.reference_type],
            )
        except ValueError as exc:
            logger.warning(
                "Enrichment: span->token projection failed for doc %s: %s",
                res.source_document_id,
                exc,
            )
            return None
        return annotation_json, page

    def _src_text_for(self, document_id: int) -> str | None:
        """The extractor's source text (``txt_extract_file``) for a document."""
        if document_id not in self._src_texts:
            from opencontractserver.utils.files import read_field_file_text

            text = None
            try:
                doc = Document.objects.get(pk=document_id)
                text = read_field_file_text(doc.txt_extract_file)
            except Exception as exc:
                logger.warning(
                    "Enrichment: could not read source text for doc %s (%s).",
                    document_id,
                    exc,
                )
            self._src_texts[document_id] = text
        return self._src_texts[document_id]

    def _remap_span(
        self, document_id: int, doc_text: str, cand
    ) -> tuple[int, int] | None:
        """Map ``cand``'s span from extractor (txt) coords to PAWLs coords.

        Both texts contain the same mention occurrences in the same order
        when the drift is whitespace/formatting-level, so the N-th occurrence
        of the raw text in one is the N-th in the other. Matching is
        whitespace-insensitive (``\\s+`` between words) because hard
        line-wraps put ``\\n`` inside citations where the PAWLs text has
        spaces. Returns ``(start, end)`` in ``doc_text`` coords, or ``None``
        when the occurrence doesn't exist there (material divergence —
        caller falls back to a span mention).
        """
        import re

        raw = cand.raw_text or ""
        src = self._src_text_for(document_id)
        if not raw.split() or not src:
            return None
        pattern = re.compile(r"\s+".join(re.escape(part) for part in raw.split()))
        # The mention's own occurrence is the src match whose span contains
        # cand.start. Containment (not "starts before") matters because some
        # extractors anchor the span inside the raw text — see-quoted SECTION
        # refs put "See " in raw_text but start the span at the quoted
        # heading, so the own occurrence begins before cand.start.
        ordinal = None
        preceding = 0
        for i, m in enumerate(pattern.finditer(src)):
            if m.start() <= cand.start < m.end():
                ordinal = i
                break
            if m.end() <= cand.start:
                preceding += 1
        if ordinal is None:
            ordinal = preceding
        for i, m in enumerate(pattern.finditer(doc_text)):
            if i == ordinal:
                return m.start(), m.end()
        return None

    def _get_or_create_mention(
        self, res: Resolution, result: WriteResult
    ) -> tuple[Annotation, bool]:
        cand = res.candidate
        label_text = C.LABEL_FOR_TYPE[res.reference_type]
        # PDF documents get token mentions (PAWLs bounding boxes — the PDF
        # viewer can only paint those); everything else keeps char spans.
        projected = self._project_mention(res)

        # Dedup by (document, label text, span START): the span END can
        # legitimately move when the alias registry grows (a longer authority
        # alias wins longest-first matching), and that must not duplicate the
        # mention. Token mentions carry the span in data.char_span; legacy
        # span mentions carry it in json — match either representation, by
        # label TEXT (the span- and token-typed label rows share it).
        # select_related keeps CorpusReference's save-time type<->label
        # agreement check query-free for deduped mentions.
        existing = (
            Annotation.objects.filter(
                document_id=res.source_document_id,
                corpus=self.corpus,
                annotation_label__text=label_text,
            )
            .filter(Q(json__start=cand.start) | Q(data__char_span__start=cand.start))
            .select_related("annotation_label")
            .first()
        )
        if existing is not None:
            if projected is not None and existing.annotation_type == SPAN_LABEL:
                # Converge: upgrade a legacy span mention in place (same row,
                # so CorpusReference/Relationship FKs survive). Re-running
                # enrichment is thereby also the backfill for pre-fix corpora.
                annotation_json, page = projected
                data = dict(existing.data or {})
                data["char_span"] = {"start": cand.start, "end": cand.end}
                existing.json = annotation_json
                existing.page = page
                existing.annotation_type = TOKEN_LABEL
                existing.annotation_label = self._label(label_text, TOKEN_LABEL)
                existing.data = data
                existing.save(
                    update_fields=[
                        "json",
                        "page",
                        "annotation_type",
                        "annotation_label",
                        "data",
                        "modified",
                    ]
                )
                result.annotations_upgraded += 1
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

        if projected is not None:
            annotation_json, page = projected
            json_payload: dict = annotation_json
            ann_type = TOKEN_LABEL
            # The char span survives in data so dedupe/converge stay keyed on
            # the extractor's native coordinates.
            data["char_span"] = {"start": cand.start, "end": cand.end}
        else:
            json_payload = {"start": cand.start, "end": cand.end}
            ann_type = SPAN_LABEL
            page = 1

        ann = Annotation(
            raw_text=cand.raw_text,
            page=page,
            json=json_payload,
            annotation_label=self._label(label_text, ann_type),
            document_id=res.source_document_id,
            corpus=self.corpus,
            creator_id=self.creator_id,
            annotation_type=ann_type,
            structural=False,
            data=data or None,
            link_url=link_url,
            analysis=self.analysis,
        )
        ann.save()
        return ann, True

    def write(
        self,
        resolutions: list[Resolution],
        *,
        provisional: bool = False,
        reconcile_graph: bool = True,
    ) -> WriteResult:
        """Persist one batch of resolutions in a single transaction.

        ``provisional`` stamps newly-created ``CorpusReference`` rows as
        in-flight (see :attr:`CorpusReference.is_provisional`) — set by the
        per-document streaming path in :meth:`EnrichmentService.apply` so
        references become visible mid-run, then finalized atomically on
        completion.

        ``reconcile_graph`` controls the corpus-wide ``DocumentRelationship``
        rollup. It is a projection of ALL the corpus's resolved doc->doc
        references, so it must run once over the full set — NOT per document
        (a per-doc reconcile would prune edges whose backing references the
        later documents have not yet written). The streaming path passes
        ``reconcile_graph=False`` here and calls :meth:`reconcile_document_graph`
        once after the last document. The default ``True`` preserves the
        single-shot behaviour for any non-streaming caller.
        """
        result = WriteResult()
        rel_label = self._label(C.LABEL_RELATIONSHIP, RELATIONSHIP_LABEL)

        target_ids = {r.target_document_id for r in resolutions if r.target_document_id}
        self._doc_slugs = dict(
            Document.objects.filter(id__in=target_ids).values_list("id", "slug")
        )
        # Prefetch the AuthorityNamespace classification for every law-ref prefix
        # in one query so persist-time backfill (_ensure_corpus_reference) never
        # hits the DB per row.
        self._ns_class = namespace_classification_cache(
            r.canonical_key.split(":", 1)[0]
            for r in resolutions
            if r.reference_type == C.REF_LAW and r.canonical_key
        )

        with transaction.atomic():
            for res in resolutions:
                mention, created = self._get_or_create_mention(res, result)
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
                self._ensure_corpus_reference(mention, res, result, provisional)

            # Resolved doc->doc refs roll up to document-level edges:
            # DocumentRelationship is what the corpus document graph renders
            # (documents = nodes, relationships = edges).
            if reconcile_graph:
                self._reconcile_document_graph(rel_label, result)

        return result

    def reconcile_document_graph(self) -> WriteResult:
        """Run the corpus-wide doc-graph projection once, in its own transaction.

        The streaming path in :meth:`EnrichmentService.apply` writes each
        document's references with ``reconcile_graph=False`` and then calls this
        after the last document, so the ``DocumentRelationship`` rollup sees the
        complete set of resolved doc->doc references exactly once.
        """
        result = WriteResult()
        rel_label = self._label(C.LABEL_RELATIONSHIP, RELATIONSHIP_LABEL)
        with transaction.atomic():
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

        # Materialise the current projection once — we both prune stale rows
        # and read coverage from it, with a delete in between; evaluating the
        # lazy queryset twice around the delete is a wasted round-trip.
        projection_rows = list(
            DocumentRelationship.objects.filter(
                corpus=self.corpus,
                relationship_type=C.DOC_REL_RELATIONSHIP,
                annotation_label=rel_label,
            ).values_list("id", "source_document_id", "target_document_id", "data")
        )
        stale_ids = [
            pk
            for pk, src, tgt, data in projection_rows
            if isinstance(data, dict)
            and "analysis_id" in data  # enrichment-owned only
            and (src, tgt) not in expected
        ]
        if stale_ids:
            DocumentRelationship.objects.filter(id__in=stale_ids).delete()
            result.document_relationships_pruned += len(stale_ids)

        # Coverage = every projection row still standing after the prune
        # (user-authored rows count too: don't shadow them).
        stale_set = set(stale_ids)
        covered = {
            (src, tgt) for pk, src, tgt, data in projection_rows if pk not in stale_set
        }
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

    def _ensure_corpus_reference(self, mention, res, result, provisional=False):
        normalized = dict(res.normalized_data)
        if res.target_offset is not None:
            normalized["target_offset"] = res.target_offset
        # Classify at PERSIST time so the durable row carries the same taxonomy
        # discover() reports: the candidate's values win, else the
        # AuthorityNamespace registry, else the static shape rules. Registry-tier
        # candidates carry no jurisdiction/authority_type, so without this they
        # would be stored as (None, None) — see gap-4.
        jurisdiction, authority_type = classify_canonical_key(
            res.canonical_key,
            res.candidate.jurisdiction,
            res.candidate.authority_type,
            namespace_cache=self._ns_class,
        )
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
                # Phase 1: carry the classification + detection provenance onto
                # the durable row (candidate values, backfilled above).
                "jurisdiction": jurisdiction,
                "authority_type": authority_type,
                "detection_tier": res.candidate.detection_tier,
                "detection_confidence": res.candidate.detection_confidence,
                # In-flight runs mark new rows provisional; finalized on the
                # producing run's success (EnrichmentService.apply).
                "is_provisional": provisional,
            },
        )
        if created:
            result.references_created += 1
            result.reference_ids.append(ref.pk)
            return

        # --- existing row ---------------------------------------------------
        update_fields: list[str] = []
        if (ref.jurisdiction is None or ref.authority_type is None) and (
            jurisdiction is not None or authority_type is not None
        ):
            # Heal a row persisted before classification existed (or by an
            # earlier registry-only pass): converge on re-apply so the
            # governance graph + frontier never read a stale (None, None).
            ref.jurisdiction = ref.jurisdiction or jurisdiction
            ref.authority_type = ref.authority_type or authority_type
            update_fields += ["jurisdiction", "authority_type"]

        # Heal a row persisted as UNRESOLVED before its target could be found
        # (a sibling document ingested later, or a resolution-logic bug fixed
        # after the row was first written — e.g. issue where a title-index
        # lookup key mismatch made every citation into some documents
        # unresolvable). get_or_create's lookup key (source_annotation,
        # reference_type, canonical_key) doesn't include the resolution
        # target, so without this heal a re-apply that now finds the target
        # silently re-fetches the stale UNRESOLVED row and never upgrades it
        # — the run's in-memory resolved-count would over-report what
        # actually persisted. Converge forward only: an already-RESOLVED row
        # is never downgraded back to UNRESOLVED by a later run that fails to
        # find the same target (mirrors the jurisdiction/authority_type
        # heal-only-forward rule above).
        if (
            ref.resolution_status != C.STATUS_RESOLVED
            and res.resolution_status == C.STATUS_RESOLVED
        ):
            ref.target_annotation_id = res.target_annotation_id
            ref.target_document_id = res.target_document_id
            ref.resolution_status = res.resolution_status
            ref.confidence = res.confidence
            if normalized:
                ref.normalized_data = normalized
            update_fields += [
                "target_annotation_id",
                "target_document_id",
                "resolution_status",
                "confidence",
                "normalized_data",
            ]
            result.references_resolved += 1

        # Claim rule: a still-provisional row owned by a DIFFERENT analysis is
        # re-attributed to the current analysis so the completion flip — which
        # keys on ``created_by_analysis=self.analysis`` — finalizes it. We claim
        # regardless of the prior owner's state (FAILED or still RUNNING) ON
        # PURPOSE: the lifecycle is then resilient to a run that died without
        # marking itself FAILED (e.g. a Celery worker warm-shutdown orphaning an
        # Analysis at RUNNING) — the NEXT successful run reclaims and finalizes
        # its provisional rows with no reaper required.
        #
        # A FINALIZED row (is_provisional=False) is NEVER touched here: re-running
        # enrichment must never downgrade an already-finalized reference back to
        # provisional, even mid-run. That guard is what keeps the semantics safe
        # under (currently un-prevented) concurrent same-corpus runs: two runs
        # may claim each other's *provisional* rows, but the outcome is
        # well-defined — no finalized row is ever corrupted, whichever run
        # finalizes a given row last owns it, and if both succeed it ends
        # finalized. The only quirk (eventual owner later fails → row lingers
        # provisional until the next successful run) is identical to the accepted
        # failed-run behavior, and the crawl's finalized-only guard is downstream
        # so no half-correct ingest can result.
        if (
            ref.is_provisional
            and self.analysis is not None
            and ref.created_by_analysis_id != self.analysis.id
        ):
            ref.created_by_analysis = self.analysis
            update_fields.append("created_by_analysis")

        if update_fields:
            ref.save(update_fields=[*update_fields, "modified"])
