"""Orchestration + query services for corpus reference enrichment.

``EnrichmentService`` is the single entry point the agent tools call:

* ``scan``  — extract + resolve across the corpus, return an inventory, NO writes.
* ``apply`` — scan, then persist under an ``Analysis`` (approval-gated at the
  tool layer).

``CorpusReferenceService`` is the read surface (visibility derives from corpus
visibility — no per-object guardian rows in v1).
"""

from __future__ import annotations

import logging
from collections import Counter

from django.contrib.auth import get_user_model

from opencontractserver.analyzer.models import Analysis, Analyzer
from opencontractserver.annotations.models import Annotation, CorpusReference
from opencontractserver.corpuses.models import Corpus
from opencontractserver.corpuses.services.corpus_documents import CorpusDocumentService
from opencontractserver.enrichment import constants as C
from opencontractserver.enrichment.extractor import ReferenceExtractor
from opencontractserver.enrichment.resolver import (
    ReferenceResolver,
    Resolution,
    _SectionAnno,
)
from opencontractserver.enrichment.writer import EnrichmentWriter
from opencontractserver.types.enums import JobStatus
from opencontractserver.utils.files import read_field_file_text

logger = logging.getLogger(__name__)
User = get_user_model()

# OC_SECTION is the built-in structural section label.
OC_SECTION_LABEL = "OC_SECTION"


class CorpusReferenceService:
    """Read surface for CorpusReference rows."""

    @staticmethod
    def visible_to_user(user):
        return CorpusReference.objects.filter(
            corpus__in=Corpus.objects.visible_to_user(user)
        )

    @classmethod
    def for_corpus(cls, user, corpus_id: int):
        return cls.visible_to_user(user).filter(corpus_id=corpus_id)


class EnrichmentService:
    """Scan and apply reference enrichment for a corpus."""

    # -- shared internals -------------------------------------------------- #

    def _load(self, corpus_id: int, creator_id: int):
        user = User.objects.get(pk=creator_id)
        corpus = Corpus.objects.get(pk=corpus_id)
        documents = list(
            CorpusDocumentService.get_corpus_documents(user, corpus, include_caml=False)
        )
        return user, corpus, documents

    def _sections_for(self, doc_id: int) -> list[_SectionAnno]:
        rows = Annotation.objects.filter(
            document_id=doc_id, annotation_label__text=OC_SECTION_LABEL
        ).values_list("id", "raw_text")
        return [_SectionAnno(id=pk, raw_text=txt or "") for pk, txt in rows]

    def _resolutions(self, corpus, documents, types, user) -> list[Resolution]:
        from opencontractserver.enrichment.authorities import authority_alias_registry

        wanted = set(types or C.DEFAULT_REFERENCE_TYPES)
        resolver = ReferenceResolver(documents)
        # The alias registry is corpus-data-driven (authority corpora declare
        # their own aliases) and visibility-scoped to the run user.
        extractor = ReferenceExtractor(authority_aliases=authority_alias_registry(user))
        resolutions: list[Resolution] = []
        for doc in documents:
            try:
                text = read_field_file_text(doc.txt_extract_file)
            except Exception as exc:  # isolate per-document failures
                logger.warning(
                    "Enrichment: skip doc %s (text read failed: %s)", doc.id, exc
                )
                continue
            if not text:
                continue
            sections = self._sections_for(doc.id)
            # Authority documents know their own body of law — that context
            # keys relative citations ("§ 251 of this title") in statute text.
            meta = doc.custom_meta if isinstance(doc.custom_meta, dict) else {}
            for cand in extractor.extract(
                text, default_authority=meta.get("authority")
            ):
                if cand.reference_type not in wanted:
                    continue
                resolutions.append(resolver.resolve(cand, doc.id, text, sections))
        return resolutions

    # -- public API -------------------------------------------------------- #

    def scan(
        self,
        *,
        corpus_id: int,
        creator_id: int,
        types: list[str] | None = None,
        sample_n: int = C.DEFAULT_SAMPLE_N,
    ) -> dict:
        user, corpus, documents = self._load(corpus_id, creator_id)
        resolutions = self._resolutions(corpus, documents, types, user)

        by_type = Counter(r.reference_type for r in resolutions)
        by_status = Counter(r.resolution_status for r in resolutions)
        samples = [
            {
                "reference_type": r.reference_type,
                "raw_text": r.candidate.raw_text[:120],
                "canonical_key": r.canonical_key,
                "resolution_status": r.resolution_status,
                "target_document_id": r.target_document_id,
                "source_document_id": r.source_document_id,
            }
            for r in resolutions[:sample_n]
        ]
        unresolved = [
            {
                "reference_type": r.reference_type,
                "raw_text": r.candidate.raw_text[:120],
                "source_document_id": r.source_document_id,
            }
            for r in resolutions
            if r.resolution_status == C.STATUS_UNRESOLVED
        ][:sample_n]

        return {
            "corpus_id": corpus_id,
            "documents_scanned": len(documents),
            "total_candidates": len(resolutions),
            "counts_by_type": dict(by_type),
            "counts_by_status": dict(by_status),
            "samples": samples,
            "unresolved_samples": unresolved,
        }

    def _get_analysis(self, corpus, creator_id: int) -> Analysis:
        # task_name is unique and the startup sync may have created the row
        # under id == task_name already — converge on it before creating.
        analyzer = Analyzer.objects.filter(task_name=C.ENRICHMENT_ANALYZER_TASK).first()
        if analyzer is None:
            analyzer, _ = Analyzer.objects.get_or_create(
                id=C.ENRICHMENT_ANALYZER_ID,
                defaults={
                    "task_name": C.ENRICHMENT_ANALYZER_TASK,
                    "description": C.ENRICHMENT_ANALYZER_TITLE,
                    "creator_id": creator_id,
                },
            )
        return Analysis.objects.create(
            analyzer=analyzer,
            analyzed_corpus=corpus,
            creator_id=creator_id,
            status=JobStatus.COMPLETED.value,
        )

    def apply(
        self,
        *,
        corpus_id: int,
        creator_id: int,
        types: list[str] | None = None,
        analysis: Analysis | None = None,
    ) -> dict:
        """Persist the corpus's reference web.

        ``analysis`` lets the analyzer-framework adapter attach the run to the
        framework-created ``Analysis``; when omitted (agent tool / direct
        service call) a provenance ``Analysis`` is created here.
        """
        user, corpus, documents = self._load(corpus_id, creator_id)
        resolutions = self._resolutions(corpus, documents, types, user)
        if analysis is None:
            analysis = self._get_analysis(corpus, creator_id)
        writer = EnrichmentWriter(corpus, creator_id, analysis=analysis)
        res = writer.write(resolutions)
        link = self._link_external(user, corpus)
        return {
            "corpus_id": corpus_id,
            "analysis_id": analysis.id,
            "documents_scanned": len(documents),
            "total_candidates": len(resolutions),
            "annotations_created": res.annotations_created,
            "relationships_created": res.relationships_created,
            "references_created": res.references_created,
            "document_relationships_created": res.document_relationships_created,
            "law_references_linked": link["law_references_linked"],
        }

    # -- cross-corpus linking ----------------------------------------------- #

    def link_external_references(self, *, corpus_id: int, creator_id: int) -> dict:
        """Upgrade EXTERNAL law references to RESOLVED cross-corpus links.

        Re-runnable: as new authority corpora are bootstrapped, another pass
        links any still-external citations whose canonical keys now have a
        visible authority document.
        """
        user = User.objects.get(pk=creator_id)
        corpus = Corpus.objects.get(pk=corpus_id)
        return self._link_external(user, corpus)

    def _link_external(self, user, corpus) -> dict:
        from opencontractserver.documents.models import Document
        from opencontractserver.enrichment.authorities import find_authority_target

        refs = (
            CorpusReference.objects.filter(
                corpus=corpus,
                reference_type=C.REF_LAW,
                target_document__isnull=True,
            )
            .exclude(canonical_key=None)
            .select_related("source_annotation")
        )
        target_cache: dict[str, Document | None] = {}
        linked = 0
        for ref in refs:
            key = ref.canonical_key
            if not key:  # queryset excludes None; guard for type-narrowing
                continue
            if key not in target_cache:
                target_cache[key] = find_authority_target(key, user)
            target = target_cache[key]
            if target is None:
                continue
            target_corpus_id = (
                target.path_records.filter(is_current=True, is_deleted=False)
                .values_list("corpus_id", flat=True)
                .first()
            )
            ref.target_document = target
            ref.target_corpus_id = target_corpus_id
            ref.resolution_status = C.STATUS_RESOLVED
            ref.save(
                update_fields=[
                    "target_document",
                    "target_corpus",
                    "resolution_status",
                    "modified",
                ]
            )
            if target_corpus_id is not None:
                mention = ref.source_annotation
                mention.link_url = f"/corpus/{target_corpus_id}/document/{target.id}"
                mention.save(update_fields=["link_url", "modified"])
            linked += 1
        return {"corpus_id": corpus.id, "law_references_linked": linked}
