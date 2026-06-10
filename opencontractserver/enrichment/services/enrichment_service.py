"""Orchestration service for corpus reference enrichment.

``EnrichmentService`` is the single entry point the agent tools call:

* ``scan``  — extract + resolve across the corpus, return an inventory, NO writes.
* ``apply`` — scan, then persist under an ``Analysis`` (approval-gated at the
  tool layer).

The read surface lives in
:mod:`opencontractserver.enrichment.services.corpus_reference_service`.
"""

from __future__ import annotations

import logging
from collections import Counter

from django.contrib.auth import get_user_model
from django.utils import timezone

from opencontractserver.analyzer.models import Analysis, Analyzer
from opencontractserver.annotations.models import Annotation, CorpusReference
from opencontractserver.constants.annotations import OC_SECTION_LABEL
from opencontractserver.corpuses.models import Corpus
from opencontractserver.corpuses.services.corpus_documents import CorpusDocumentService
from opencontractserver.enrichment import constants as C
from opencontractserver.enrichment.extractor import ReferenceExtractor
from opencontractserver.enrichment.resolver import (
    ReferenceResolver,
    Resolution,
    SectionAnno,
)
from opencontractserver.enrichment.writer import EnrichmentWriter
from opencontractserver.types.enums import JobStatus
from opencontractserver.utils.files import read_field_file_text
from opencontractserver.utils.frontend_paths import document_in_corpus_path

logger = logging.getLogger(__name__)
User = get_user_model()


class EnrichmentService:
    """Scan and apply reference enrichment for a corpus."""

    # -- shared internals -------------------------------------------------- #

    def _load(self, corpus_id: int, creator_id: int):
        user = User.objects.get(pk=creator_id)
        # Visibility-scoped fetch: invisible and nonexistent corpora raise the
        # same ``Corpus.DoesNotExist`` (no existence oracle for callers that
        # pass arbitrary PKs).
        corpus = Corpus.objects.visible_to_user(user).get(pk=corpus_id)
        documents = list(
            CorpusDocumentService.get_corpus_documents(user, corpus, include_caml=False)
        )
        return user, corpus, documents

    def _sections_by_doc(self, documents) -> dict[int, list[SectionAnno]]:
        """OC_SECTION annotations grouped by document — one query per corpus."""
        sections: dict[int, list[SectionAnno]] = {}
        rows = Annotation.objects.filter(
            document_id__in=[d.id for d in documents],
            annotation_label__text=OC_SECTION_LABEL,
        ).values_list("id", "raw_text", "document_id")
        for pk, txt, doc_id in rows:
            sections.setdefault(doc_id, []).append(
                SectionAnno(id=pk, raw_text=txt or "")
            )
        return sections

    def _resolutions(self, corpus, documents, types, user) -> list[Resolution]:
        from opencontractserver.enrichment.authorities import authority_alias_registry

        wanted = set(types or C.DEFAULT_REFERENCE_TYPES)
        resolver = ReferenceResolver(documents)
        # The alias registry is corpus-data-driven (authority corpora declare
        # their own aliases) and visibility-scoped to the run user.
        extractor = ReferenceExtractor(authority_aliases=authority_alias_registry(user))
        sections_by_doc = self._sections_by_doc(documents)
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
            sections = sections_by_doc.get(doc.id, [])
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
        # Two provenance paths: when ``apply`` runs via the analyzer framework
        # (Celery), the @corpus_analyzer_task wrapper owns the Analysis and
        # drives RUNNING -> COMPLETED/FAILED. This branch serves the direct
        # agent-tool / service call, which runs synchronously inside ``apply``
        # — the Analysis starts RUNNING and is set to COMPLETED on success or
        # FAILED on exception by ``apply()``.
        return Analysis.objects.create(
            analyzer=analyzer,
            analyzed_corpus=corpus,
            creator_id=creator_id,
            status=JobStatus.RUNNING.value,
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
        try:
            res = writer.write(resolutions)
        except Exception:
            analysis.status = JobStatus.FAILED.value
            analysis.save(update_fields=["status"])
            raise
        analysis.status = JobStatus.COMPLETED.value
        analysis.save(update_fields=["status"])
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
        # Same visibility-scoped semantics as ``_load`` (uniform DoesNotExist
        # for invisible vs nonexistent).
        corpus = Corpus.objects.visible_to_user(user).get(pk=corpus_id)
        return self._link_external(user, corpus)

    def _link_external(self, user, corpus) -> dict:
        from opencontractserver.documents.models import Document, DocumentPath
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
        corpus_cache: dict[int, Corpus] = {}
        now = timezone.now()
        updated_refs: list[CorpusReference] = []
        updated_mentions: list[Annotation] = []
        # First pass: build target_cache (deduped by canonical key).
        for ref in refs:
            key = ref.canonical_key
            if not key:
                continue
            if key not in target_cache:
                target_cache[key] = find_authority_target(key, user)
        # Batch-fetch corpus membership for all resolved targets in one query
        # instead of one per target (avoids N+1 on large corpora).
        resolved_target_ids = {t.id for t in target_cache.values() if t is not None}
        path_corpus_cache: dict[int, int | None] = dict(
            DocumentPath.objects.filter(
                document_id__in=resolved_target_ids,
                is_current=True,
                is_deleted=False,
            ).values_list("document_id", "corpus_id")
        )
        for ref in refs:
            key = ref.canonical_key
            if not key:  # queryset excludes None; guard for type-narrowing
                continue
            target = target_cache.get(key)
            if target is None:
                continue
            target_corpus_id = path_corpus_cache.get(target.id)
            ref.target_document = target
            ref.target_corpus_id = target_corpus_id
            ref.resolution_status = C.STATUS_RESOLVED
            # bulk_update bypasses auto_now — stamp ``modified`` explicitly.
            ref.modified = now
            updated_refs.append(ref)
            if target_corpus_id is not None:
                if target_corpus_id not in corpus_cache:
                    corpus_cache[target_corpus_id] = Corpus.objects.select_related(
                        "creator"
                    ).get(pk=target_corpus_id)
                target_corpus = corpus_cache[target_corpus_id]
                # Canonical slug path into the authority corpus — the only
                # shape the frontend router serves (anything else 404s).
                link_url = document_in_corpus_path(
                    corpus_creator_slug=target_corpus.creator.slug,
                    corpus_slug=target_corpus.slug,
                    document_slug=target.slug,
                )
                if link_url:
                    mention = ref.source_annotation
                    mention.link_url = link_url
                    mention.modified = now
                    updated_mentions.append(mention)

        # Two queries instead of O(N) row-by-row saves (corpora carry
        # hundreds-to-thousands of law references at demo scale).
        if updated_refs:
            CorpusReference.objects.bulk_update(
                updated_refs,
                ["target_document", "target_corpus", "resolution_status", "modified"],
            )
        if updated_mentions:
            Annotation.objects.bulk_update(updated_mentions, ["link_url", "modified"])
        return {"corpus_id": corpus.id, "law_references_linked": len(updated_refs)}
