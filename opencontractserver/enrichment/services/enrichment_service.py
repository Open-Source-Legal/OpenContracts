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

from asgiref.sync import async_to_sync
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

    def _resolutions(
        self, corpus, documents, types, user, extra_tiers=None
    ) -> list[Resolution]:
        from opencontractserver.enrichment.authorities import authority_alias_registry
        from opencontractserver.enrichment.grammars import GenericCitationExtractor
        from opencontractserver.enrichment.reconcile import reconcile

        wanted = set(types or C.DEFAULT_REFERENCE_TYPES)
        # The trusted registry tier is ALWAYS the base; ``extra_tiers`` only
        # selects which *additional* layers (e.g. grammar) to merge on top of
        # it — it is additive, not exhaustive. So the registry extractor runs
        # unconditionally and ``extra_tiers=[DETECTION_TIER_GRAMMAR]`` means
        # "registry + grammar", never "grammar only".
        active_tiers = set(extra_tiers or ())
        resolver = ReferenceResolver(documents)
        extractor = ReferenceExtractor(authority_aliases=authority_alias_registry(user))
        generic = (
            GenericCitationExtractor()
            if C.DETECTION_TIER_GRAMMAR in active_tiers
            else None
        )
        llm_extractor = None
        if C.DETECTION_TIER_LLM in active_tiers:
            from opencontractserver.enrichment.llm_citation_extractor import (
                LLMCitationExtractor,
            )

            llm_extractor = LLMCitationExtractor()
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
            meta = doc.custom_meta if isinstance(doc.custom_meta, dict) else {}
            primary = list(
                extractor.extract(text, default_authority=meta.get("authority"))
            )
            if generic is not None:
                # Registry wins on overlap; generic adds the open-vocabulary tail.
                cands = reconcile(primary, generic.extract(text))
            else:
                cands = primary
            if llm_extractor is not None:
                llm_cands = async_to_sync(llm_extractor.aextract)(text)
                cands = reconcile(cands, llm_cands)
            for cand in cands:
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
        extra_tiers: list[str] | None = None,
    ) -> dict:
        user, corpus, documents = self._load(corpus_id, creator_id)
        resolutions = self._resolutions(
            corpus, documents, types, user, extra_tiers=extra_tiers
        )

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

    def discover(
        self,
        *,
        corpus_id: int,
        creator_id: int,
        max_documents: int | None = None,
        use_llm: bool = False,
    ) -> dict:
        """Read-only open-vocabulary inventory (registry + grammar tiers).

        Surfaces authorities the registry alone would miss, grouped by
        jurisdiction / authority_type, and flags prefixes with no
        AuthorityNamespace row (genuinely new bodies of law).

        Runs registry + grammar extraction over the *full text* of every corpus
        document, so cost scales with corpus size. ``max_documents`` caps the
        document set when set (the result reports ``documents_truncated`` so the
        cap is never silent); ``None`` (default) scans the whole corpus.
        """
        from opencontractserver.annotations.models import AuthorityNamespace

        user, corpus, documents = self._load(corpus_id, creator_id)
        documents_total = len(documents)
        documents_truncated = (
            max_documents is not None and documents_total > max_documents
        )
        if documents_truncated:
            documents = documents[:max_documents]
        extra = [C.DETECTION_TIER_GRAMMAR]
        if use_llm:
            extra.append(C.DETECTION_TIER_LLM)
        resolutions = self._resolutions(
            corpus,
            documents,
            [C.REF_LAW],
            user,
            extra_tiers=extra,
        )

        # Registry-tier candidates carry no jurisdiction/authority_type (the
        # static extractor predates the taxonomy), so resolve it by prefix from
        # the AuthorityNamespace registry, falling back to PREFIX_CLASSIFICATION.
        # Without this, dgcl/irc/etc. would be absent from the rollups below.
        # Resolver-generated canonical keys are always ``"<prefix>:<locator>"``
        # (see ReferenceResolver), so the prefix is the segment before the first
        # ``:``. A hypothetical bare key with no ``:`` would yield itself here and
        # could be misflagged as a new namespace — guard against that drift.
        prefixes = {
            r.canonical_key.split(":", 1)[0]
            for r in resolutions
            if r.canonical_key and ":" in r.canonical_key
        }
        ns_rows = list(
            AuthorityNamespace.objects.filter(prefix__in=prefixes).values_list(
                "prefix", "jurisdiction", "authority_type"
            )
        )
        known = {prefix for prefix, _j, _t in ns_rows}
        ns_class = {prefix: (jur, typ) for prefix, jur, typ in ns_rows}

        review_resolutions = [
            r
            for r in resolutions
            if (r.candidate.normalized_data or {}).get("needs_review")
        ]
        main_resolutions = [
            r
            for r in resolutions
            if not (r.candidate.normalized_data or {}).get("needs_review")
        ]

        def _classify(prefix: str, cand) -> tuple:
            ns_jur, ns_typ = ns_class.get(
                prefix, C.PREFIX_CLASSIFICATION.get(prefix, (None, None))
            )
            return (cand.jurisdiction or ns_jur, cand.authority_type or ns_typ)

        by_key: dict[str, dict] = {}
        by_jurisdiction: Counter = Counter()
        by_type: Counter = Counter()
        for r in main_resolutions:
            key = r.canonical_key
            if not key:
                continue
            cand = r.candidate
            prefix = key.split(":", 1)[0]
            jur, typ = _classify(prefix, cand)
            entry = by_key.setdefault(
                key,
                {
                    "canonical_key": key,
                    "prefix": prefix,
                    "jurisdiction": jur,
                    "authority_type": typ,
                    "detection_tier": cand.detection_tier,
                    "mention_count": 0,
                },
            )
            entry["mention_count"] += 1
            # Upgrade a first-writer None once a later mention resolves it.
            entry["jurisdiction"] = entry["jurisdiction"] or jur
            entry["authority_type"] = entry["authority_type"] or typ
            if jur:
                by_jurisdiction[jur] += 1
            if typ:
                by_type[typ] += 1

        # Prefix-level classification for new namespaces, preferring a non-None
        # source (all keys under a prefix share one body of law).
        prefix_class: dict[str, tuple] = {}
        for e in by_key.values():
            cur = prefix_class.get(e["prefix"])
            if cur is None or cur[0] is None:
                prefix_class[e["prefix"]] = (e["jurisdiction"], e["authority_type"])
        new_namespaces = [
            {
                "prefix": p,
                "jurisdiction": prefix_class.get(p, (None, None))[0],
                "authority_type": prefix_class.get(p, (None, None))[1],
            }
            for p in sorted(prefixes - known)
        ]

        return {
            "corpus_id": corpus_id,
            "documents_scanned": len(documents),
            "documents_total": documents_total,
            "documents_truncated": documents_truncated,
            "total_candidates": len(resolutions),
            "by_key": by_key,
            "by_jurisdiction": dict(by_jurisdiction),
            "by_authority_type": dict(by_type),
            "new_namespaces": new_namespaces,
            "review_candidates": [
                {
                    "canonical_key": r.canonical_key,
                    "raw_text": r.candidate.raw_text[:120],
                    "detection_tier": r.candidate.detection_tier,
                    "detection_confidence": r.candidate.detection_confidence,
                }
                for r in review_resolutions
            ],
        }

    @staticmethod
    def get_analyzer() -> Analyzer | None:
        """Lookup-only twin of :meth:`get_or_create_analyzer`.

        Returns the converged enrichment ``Analyzer`` row, or ``None`` when the
        deployment has none registered. Use this when absence means "feature
        unavailable" (e.g. intelligence setup skipping the reference half)
        rather than a row to create; both methods share this lookup so the
        converge scheme still exists exactly once.
        """
        return Analyzer.objects.filter(task_name=C.ENRICHMENT_ANALYZER_TASK).first()

    @staticmethod
    def get_or_create_analyzer(creator_id: int) -> Analyzer:
        """Converge on THE enrichment ``Analyzer`` row.

        ``task_name`` is unique, and the migration/startup auto-sync
        (``auto_create_doc_analyzers``) may already have created the row under
        ``id == task_name`` — reuse it before creating the friendly-id row.
        Every code path that needs the enrichment analyzer (service, tests)
        must go through here (or :meth:`get_analyzer` for lookup-only callers)
        so the converge logic exists exactly once.
        """
        analyzer = EnrichmentService.get_analyzer()
        if analyzer is None:
            analyzer, _ = Analyzer.objects.get_or_create(
                id=C.ENRICHMENT_ANALYZER_ID,
                defaults={
                    "task_name": C.ENRICHMENT_ANALYZER_TASK,
                    "description": C.ENRICHMENT_ANALYZER_TITLE,
                    "creator_id": creator_id,
                },
            )
        return analyzer

    def _get_analysis(self, corpus, creator_id: int) -> Analysis:
        analyzer = self.get_or_create_analyzer(creator_id)
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
        extra_tiers: list[str] | None = None,
    ) -> dict:
        """Persist the corpus's reference web.

        ``analysis`` lets the analyzer-framework adapter attach the run to the
        framework-created ``Analysis``; when omitted (agent tool / direct
        service call) a provenance ``Analysis`` is created here.
        """
        user, corpus, documents = self._load(corpus_id, creator_id)
        resolutions = self._resolutions(
            corpus, documents, types, user, extra_tiers=extra_tiers
        )
        resolutions = [
            r
            for r in resolutions
            if not (r.candidate.normalized_data or {}).get("needs_review")
        ]
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
            "annotations_upgraded": res.annotations_upgraded,
            "relationships_created": res.relationships_created,
            "references_created": res.references_created,
            "document_relationships_created": res.document_relationships_created,
            "document_relationships_pruned": res.document_relationships_pruned,
            "law_references_linked": link["law_references_linked"],
            "links_restamped": link["links_restamped"],
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

    def relink_corpora_for_keys(self, canonical_keys) -> dict:
        """Reactive re-link: converge filing corpora after an authority lands.

        Given the canonical keys a bootstrap just materialised, find every
        corpus holding EXTERNAL law references satisfiable by those keys
        (subsection citations match via their section root) and re-run the
        linking pass for each — **as that corpus's creator**, so visibility
        semantics are preserved per corpus: a private authority resolves only
        the corpora of users who can see it; nothing leaks.

        Per-corpus failures are logged and counted but do not abort the
        sweep (one broken corpus must not strand the rest).
        """
        from opencontractserver.enrichment.authorities import candidate_keys

        wanted = {k for k in canonical_keys or [] if k}
        summary = {
            "corpora_checked": 0,
            "corpora_relinked": 0,
            "corpora_failed": 0,
            "law_references_linked": 0,
            "links_restamped": 0,
        }
        if not wanted:
            return summary

        # Pre-filter SQL-side to refs whose authority prefix matches a wanted
        # key's, before the Python candidate_keys match. A ref can only satisfy
        # a wanted key if they share an authority (candidate_keys never crosses
        # authorities — it only rolls a subsection up to its section root), so
        # this bounds the scan to the relevant authorities instead of loading
        # every EXTERNAL law ref in the system into memory (the cross-product
        # concern on large deployments). The Python set-intersection below still
        # does the exact root match SQL can't express.
        from django.db.models import Q

        prefix_filter = Q()
        for prefix in {k.split(":", 1)[0] for k in wanted}:
            prefix_filter |= Q(canonical_key__startswith=f"{prefix}:")

        # Distinct (corpus, key) pairs only — bounded by the EXTERNAL-ref key
        # space, not mention volume. Root matching (regex-derived) is
        # Python-side because SQL can't express candidate_keys.
        pairs = (
            CorpusReference.objects.filter(
                prefix_filter,
                reference_type=C.REF_LAW,
                resolution_status=C.STATUS_EXTERNAL,
            )
            .exclude(canonical_key=None)
            .values_list("corpus_id", "canonical_key")
            .distinct()
        )
        affected_ids = {
            corpus_id
            for corpus_id, key in pairs
            # queryset excludes None keys; the truthiness check narrows the type
            if key and set(candidate_keys(key)) & wanted
        }
        summary["corpora_checked"] = len(affected_ids)

        for corpus in Corpus.objects.filter(id__in=affected_ids).select_related(
            "creator"
        ):
            try:
                out = self.link_external_references(
                    corpus_id=corpus.id, creator_id=corpus.creator_id
                )
            except Exception:
                logger.exception(
                    "Relink failed for corpus %s — continuing sweep", corpus.id
                )
                summary["corpora_failed"] += 1
                continue
            summary["law_references_linked"] += out["law_references_linked"]
            summary["links_restamped"] += out["links_restamped"]
            if out["law_references_linked"]:
                summary["corpora_relinked"] += 1
        return summary

    def _link_external(self, user, corpus) -> dict:
        """Resolve still-external law refs, then repair all mention links.

        Pass 1 assigns targets; pass 2 (``_restamp_mention_links``) recomputes
        ``link_url`` for *every* resolved reference from the current slugs, so
        each linking run also repairs slug drift on previously-stamped
        mentions — ``CorpusReference.target_document`` is the durable truth
        and ``link_url`` only a cached projection of it.
        """
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
        now = timezone.now()
        updated_refs: list[CorpusReference] = []
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
            ref.target_document = target
            ref.target_corpus_id = path_corpus_cache.get(target.id)
            ref.resolution_status = C.STATUS_RESOLVED
            # bulk_update bypasses auto_now — stamp ``modified`` explicitly.
            ref.modified = now
            updated_refs.append(ref)

        # One query instead of O(N) row-by-row saves (corpora carry
        # hundreds-to-thousands of law references at demo scale).
        if updated_refs:
            CorpusReference.objects.bulk_update(
                updated_refs,
                ["target_document", "target_corpus", "resolution_status", "modified"],
            )
        restamped = self._restamp_mention_links(corpus)
        return {
            "corpus_id": corpus.id,
            "law_references_linked": len(updated_refs),
            "links_restamped": restamped,
        }

    def _restamp_mention_links(self, corpus) -> int:
        """Recompute ``link_url`` for every resolved reference mention.

        The canonical slug path is the only shape the frontend router serves
        (anything else 404s). LAW refs link into the target (authority)
        corpus; DOCUMENT refs target a sibling document of the source corpus
        (``target_corpus`` is null for them). Only mentions whose stored link
        differs are written back.
        """
        refs = CorpusReference.objects.filter(
            corpus=corpus,
            resolution_status=C.STATUS_RESOLVED,
            target_document__isnull=False,
            reference_type__in=(C.REF_LAW, C.REF_DOCUMENT),
        ).select_related(
            "source_annotation", "target_document", "target_corpus__creator"
        )
        now = timezone.now()
        changed: dict[int, Annotation] = {}
        for ref in refs:
            target_document = ref.target_document
            if target_document is None:  # queryset excludes; narrows the type
                continue
            target_corpus = ref.target_corpus or corpus
            link_url = document_in_corpus_path(
                corpus_creator_slug=target_corpus.creator.slug,
                corpus_slug=target_corpus.slug,
                document_slug=target_document.slug,
            )
            mention = ref.source_annotation
            if link_url and mention.link_url != link_url:
                mention.link_url = link_url
                # bulk_update bypasses auto_now — stamp ``modified`` explicitly.
                mention.modified = now
                changed[mention.pk] = mention
        if changed:
            Annotation.objects.bulk_update(changed.values(), ["link_url", "modified"])
        return len(changed)
