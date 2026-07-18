"""Orchestration service for corpus reference enrichment.

``EnrichmentService`` is the single entry point the agent tools call:

* ``scan``  — extract + resolve across the corpus, return an inventory, NO writes.
* ``apply`` — scan, then persist under an ``Analysis`` (approval-gated at the
  tool layer).

The read surface lives in
:mod:`opencontractserver.enrichment.services.corpus_reference_service`.
"""

from __future__ import annotations

import asyncio
import logging
from collections import Counter

from asgiref.sync import async_to_sync, sync_to_async
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
    document_identity_candidates,
)
from opencontractserver.enrichment.writer import EnrichmentWriter, WriteResult
from opencontractserver.types.enums import JobStatus
from opencontractserver.utils.files import read_field_file_text
from opencontractserver.utils.frontend_paths import document_in_corpus_path

logger = logging.getLogger(__name__)
User = get_user_model()


class EnrichmentService:
    """Scan and apply reference enrichment for a corpus."""

    # -- shared internals -------------------------------------------------- #

    def _load(self, corpus_id: int, creator_id: int):
        """Resolve the caller, the (visible) corpus, and the MIN-filtered
        document set every enrichment surface operates on.

        Document loading ALWAYS uses the MIN(corpus, document) variant
        (``get_corpus_documents_visible_to_user``): a caller with corpus READ
        but not per-document READ must never have a private document scanned
        (scan/discover return verbatim excerpts) or persisted (apply writes
        ``Annotation`` / ``CorpusReference`` / ``DocumentRelationship`` rows) —
        issue #1682. The corpus-as-gate baseline used to surface how many
        documents that filter excluded lives in
        :meth:`_document_visibility_audit`.
        """
        user = User.objects.get(pk=creator_id)
        # Visibility-scoped fetch: invisible and nonexistent corpora raise the
        # same ``Corpus.DoesNotExist`` (no existence oracle for callers that
        # pass arbitrary PKs).
        corpus = Corpus.objects.visible_to_user(user).get(pk=corpus_id)
        documents = list(
            CorpusDocumentService.get_corpus_documents_visible_to_user(
                user, corpus, include_caml=False
            )
        )
        return user, corpus, documents

    def _document_visibility_audit(
        self, user, corpus, documents, *, surface: str
    ) -> tuple[int, int]:
        """Compare the MIN-filtered document set against the corpus-as-gate
        total so callers (and operators) can detect documents excluded by
        per-document visibility.

        Returns ``(total_in_corpus, excluded)``. Emits a WARNING whenever any
        document was excluded: ``apply`` would otherwise produce a permanent,
        SILENT gap in ``Annotation`` / ``CorpusReference`` coverage for a caller
        who holds corpus READ but not per-document READ (the run still completes
        and is stamped COMPLETED). The agent tools pass the conversation user's
        ``creator_id`` — not necessarily the corpus owner — so this is a real,
        not hypothetical, exclusion path (issue #1682 follow-up).

        ``total_in_corpus`` and ``len(documents)`` come from two unsynchronized
        queries, so a document removed from the corpus between them can make the
        raw difference negative; clamp to 0 so ``excluded`` never reports a
        nonsensical negative exclusion count.
        """
        total_in_corpus = CorpusDocumentService.get_corpus_documents(
            user, corpus, include_caml=False
        ).count()
        excluded = max(0, total_in_corpus - len(documents))
        if excluded > 0:
            logger.warning(
                "Enrichment %s on corpus %s: %s of %s document(s) excluded — "
                "caller %s lacks document-level READ on them "
                "(MIN(corpus, document)); result covers only the visible "
                "subset.",
                surface,
                corpus.id,
                excluded,
                total_in_corpus,
                user.id,
            )
        return total_in_corpus, excluded

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

    def _build_detection(self, documents, types, user, extra_tiers, corpus=None):
        """Construct the extractor stack + section index shared by the sync
        (scan/discover, non-LLM apply) and concurrent (LLM apply) detection
        paths.

        Returns ``(wanted, resolver, extractor, generic, llm_extractor,
        sections_by_doc)``. The trusted registry tier is ALWAYS the base;
        ``extra_tiers`` only selects which *additional* layers (grammar, LLM)
        merge on top — so the registry extractor is unconditional and
        ``extra_tiers=[DETECTION_TIER_GRAMMAR]`` means "registry + grammar",
        never "grammar only".
        """
        from opencontractserver.enrichment.authorities import authority_alias_registry
        from opencontractserver.enrichment.grammars import GenericCitationExtractor

        wanted = set(types or C.DEFAULT_REFERENCE_TYPES)
        active_tiers = set(extra_tiers or ())
        # Canonical document identities (external_id / corpus path / title —
        # see resolver.document_identity_candidates), computed ONCE and shared
        # by the resolver's identifier index, its self-mention drop, and the
        # grammar extractor's corpus-shape gate so the three can never
        # disagree about what counts as an identifier-carrying document.
        identity_candidates = document_identity_candidates(documents, corpus=corpus)
        resolver = ReferenceResolver(documents, identity_candidates=identity_candidates)
        extractor = ReferenceExtractor(authority_aliases=authority_alias_registry(user))
        generic = (
            GenericCitationExtractor(
                documents=documents, identity_candidates=identity_candidates
            )
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
        return wanted, resolver, extractor, generic, llm_extractor, sections_by_doc

    @staticmethod
    def _doc_text(doc) -> str | None:
        """Read one document's extracted text, isolating per-doc read failures."""
        try:
            text = read_field_file_text(doc.txt_extract_file)
        except Exception as exc:
            logger.warning(
                "Enrichment: skip doc %s (text read failed: %s)", doc.id, exc
            )
            return None
        return text or None

    def _read_doc_texts(self, documents) -> dict[int, str]:
        """Read every document's text once (sync I/O) so the concurrent
        orchestrator's async detection works purely in memory."""
        out: dict[int, str] = {}
        for doc in documents:
            text = self._doc_text(doc)
            if text:
                out[doc.id] = text
        return out

    def _resolve_doc(
        self,
        doc,
        doc_text,
        *,
        wanted,
        resolver,
        extractor,
        generic,
        sections_by_doc,
        llm_cands,
    ) -> list[Resolution]:
        """Combine registry + optional grammar + already-extracted LLM
        candidates for ONE document and resolve them.

        ``llm_cands`` is the LLM candidate list (empty when the tier is off) —
        the LLM call is kept OUT of this method so the concurrent orchestrator
        can run it across documents while this sync combine stays per-document.
        Registry wins on overlap; grammar/LLM add the open-vocabulary tail.
        """
        from opencontractserver.enrichment.reconcile import reconcile

        sections = sections_by_doc.get(doc.id, [])
        meta = doc.custom_meta if isinstance(doc.custom_meta, dict) else {}
        primary = list(
            extractor.extract(
                doc_text,
                default_authority=meta.get("authority"),
                reference_types=wanted,
            )
        )
        cands = (
            reconcile(primary, generic.extract(doc_text, reference_types=wanted))
            if generic
            else primary
        )
        if llm_cands:
            cands = reconcile(cands, llm_cands)
        resolved = (
            resolver.resolve(cand, doc.id, doc_text, sections)
            for cand in cands
            if cand.reference_type in wanted
        )
        # resolve() returns None for spans that must not persist (a document's
        # self-identifying header mention — see ReferenceResolver.resolve).
        return [r for r in resolved if r is not None]

    def _iter_doc_resolutions(self, corpus, documents, types, user, extra_tiers=None):
        """Yield ``(document, [Resolution])`` one document at a time (sync).

        The read-only inventory paths (``scan``/``discover``) and the non-LLM
        ``apply`` path consume this; the LLM ``apply`` path uses the concurrent
        orchestrator :meth:`_aresolve_documents` instead (it parallelises the
        slow LLM calls across documents). Documents whose text is
        missing/unreadable yield an empty list so progress counting still sees
        every document.
        """
        wanted, resolver, extractor, generic, llm_extractor, sections_by_doc = (
            self._build_detection(documents, types, user, extra_tiers, corpus=corpus)
        )
        for doc in documents:
            doc_text = self._doc_text(doc)
            if not doc_text:
                yield doc, []
                continue
            # One async_to_sync per document — fine for the sequential
            # scan/discover surfaces; apply's LLM path uses the concurrent
            # orchestrator instead.
            llm_cands = (
                async_to_sync(llm_extractor.aextract)(doc_text)
                if llm_extractor is not None
                else []
            )
            yield doc, self._resolve_doc(
                doc,
                doc_text,
                wanted=wanted,
                resolver=resolver,
                extractor=extractor,
                generic=generic,
                sections_by_doc=sections_by_doc,
                llm_cands=llm_cands,
            )

    async def _aresolve_documents(
        self, corpus, documents, types, user, extra_tiers, writer
    ):
        """Concurrent cross-document detection + per-document provisional writes.

        Runs the LLM extraction for ALL documents concurrently under one shared
        chunk-level semaphore (so total in-flight provider load stays bounded to
        ``C.llm_max_concurrency()`` — the settings-overridable global cap — no
        matter how many documents are in flight), and writes each document's
        references the moment its detection completes.
        This keeps the per-document path's incremental visibility while filling
        the concurrency lanes ACROSS documents — the per-document path serialised
        them, so a corpus with a few large documents (an S-1's prospectus)
        bottlenecked at single-document concurrency.

        Detection (extractor/grammar/resolve) and the DB write run via
        ``sync_to_async`` (thread-sensitive → one shared thread, so ORM writes
        serialise and never race); only the LLM calls run concurrently in the
        event loop. Returns ``(aggregate WriteResult, total_candidate_count)``.
        """
        (
            wanted,
            resolver,
            extractor,
            generic,
            llm_extractor,
            sections_by_doc,
        ) = await sync_to_async(self._build_detection)(
            documents, types, user, extra_tiers, corpus=corpus
        )
        doc_texts = await sync_to_async(self._read_doc_texts)(documents)

        # Build the model once (through the extractor's own build seam, so test
        # patches apply to this path too) and share it — together with a single
        # GLOBAL chunk semaphore — across every document's extraction.
        #
        # Sharing one model object across concurrent coroutines is safe: the
        # model is a stateless pydantic-ai model wrapper (it holds only a
        # reusable async HTTP client; no per-request buffers), and every call
        # gets its OWN Agent — `_one_shot_structured` builds a fresh
        # `make_pydantic_ai_agent(model, ...)` per chunk. The same model is
        # already shared across this document's concurrent CHUNK extractions
        # (`aextract` gathers chunks under one model); the orchestrator merely
        # extends that proven sharing across documents.
        model = None
        if llm_extractor is not None:
            model = await llm_extractor._abuild_model()
        chunk_sem = asyncio.Semaphore(C.llm_max_concurrency())
        # Cap how many document coroutines are LIVE at once. The chunk semaphore
        # bounds concurrent LLM calls, but every in-flight _process holds its
        # document text + candidate list, so launching all of them at once via
        # asyncio.gather would pin the whole corpus in memory. This bounds peak
        # memory independently of the chunk-level LLM cap.
        doc_sem = asyncio.Semaphore(C.doc_max_concurrency())

        agg = WriteResult()
        # ``documents`` here is already the MIN-filtered (visible) set passed
        # in by the caller (see ``apply()``'s ``documents_visible_to_caller``);
        # name it the same way so the progress log below can't be misread as
        # the corpus-as-gate total.
        documents_visible_to_caller = len(documents)
        counters = {"total": 0, "done": 0, "attempted": 0}
        # Per-document failures captured here instead of propagating out of the
        # gather (see below) so one document's error can't discard the rest.
        failures: list[tuple[int, BaseException]] = []

        async def _process(doc) -> None:
            text = doc_texts.get(doc.id)
            if not text:
                return
            async with doc_sem:
                counters["attempted"] += 1
                try:
                    llm_cands = (
                        await llm_extractor.aextract(
                            text, model=model, semaphore=chunk_sem
                        )
                        if llm_extractor is not None
                        else []
                    )

                    def _detect_and_write():
                        doc_res = self._resolve_doc(
                            doc,
                            text,
                            wanted=wanted,
                            resolver=resolver,
                            extractor=extractor,
                            generic=generic,
                            sections_by_doc=sections_by_doc,
                            llm_cands=llm_cands,
                        )
                        doc_res = [
                            r
                            for r in doc_res
                            if not (r.candidate.normalized_data or {}).get(
                                "needs_review"
                            )
                        ]
                        return (
                            writer.write(
                                doc_res, provisional=True, reconcile_graph=False
                            ),
                            len(doc_res),
                        )

                    res, n = await sync_to_async(_detect_and_write)()
                    # Back in the single-threaded event loop: accumulation is
                    # race-free.
                    self._accumulate(agg, res)
                    counters["total"] += n
                    counters["done"] += 1
                    logger.info(
                        "Enrichment apply: doc %s/%s (corpus %s) — refs so far=%s",
                        counters["done"],
                        documents_visible_to_caller,
                        corpus.id,
                        agg.references_created,
                    )
                except Exception as exc:
                    # Isolate per-document failures. asyncio.gather() propagates
                    # the FIRST exception and cancels every other in-flight
                    # coroutine, so without this one transient provider error
                    # (LLM timeout, network blip) on a single document would
                    # discard the whole corpus's concurrent work — the opposite
                    # of the in-flight-persistence resilience this path exists
                    # for. The failed document's references simply aren't written
                    # this run; any provisional rows it left are reclaimed and
                    # finalized by a later successful run.
                    failures.append((doc.id, exc))
                    logger.exception(
                        "Enrichment apply: doc %s (corpus %s) failed — skipping",
                        doc.id,
                        corpus.id,
                    )

        await asyncio.gather(*(_process(doc) for doc in documents))
        # If EVERY attempted document failed it is almost certainly a systemic
        # error (bad API key, provider outage) rather than isolated flakiness.
        # Re-raise so apply() marks the run FAILED and leaves rows provisional,
        # instead of silently finalizing an empty result.
        if failures and len(failures) == counters["attempted"]:
            raise failures[0][1]
        return agg, counters["total"]

    def _resolutions(
        self, corpus, documents, types, user, extra_tiers=None
    ) -> list[Resolution]:
        """Flat list of resolutions across the corpus (scan/discover surface).

        Thin wrapper over :meth:`_iter_doc_resolutions` so the read-only
        inventory paths keep their whole-corpus list while ``apply`` streams the
        same per-document batches.
        """
        return [
            r
            for _doc, doc_resolutions in self._iter_doc_resolutions(
                corpus, documents, types, user, extra_tiers=extra_tiers
            )
            for r in doc_resolutions
        ]

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
        documents_total_in_corpus, documents_excluded = self._document_visibility_audit(
            user, corpus, documents, surface="scan"
        )
        resolutions = self._resolutions(
            corpus, documents, types, user, extra_tiers=extra_tiers
        )

        by_type = Counter(r.reference_type for r in resolutions)
        by_status = Counter(r.resolution_status for r in resolutions)
        samples = [
            {
                "reference_type": r.reference_type,
                "raw_text": r.candidate.raw_text[: C.REVIEW_CANDIDATE_RAW_TEXT_MAX_LEN],
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
                "raw_text": r.candidate.raw_text[: C.REVIEW_CANDIDATE_RAW_TEXT_MAX_LEN],
                "source_document_id": r.source_document_id,
            }
            for r in resolutions
            if r.resolution_status == C.STATUS_UNRESOLVED
        ][:sample_n]

        return {
            "corpus_id": corpus_id,
            "documents_scanned": len(documents),
            "documents_total_in_corpus": documents_total_in_corpus,
            "documents_excluded_by_visibility": documents_excluded,
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
        document the caller can see, so cost scales with corpus size.
        ``max_documents`` caps the document set when set (the result reports
        ``documents_truncated`` so the cap is never silent); ``None`` (default)
        scans the whole *visible* corpus.

        Two independent counts are reported so neither effect is silent:
        ``documents_total_in_corpus`` (corpus-as-gate total) vs
        ``documents_visible_to_caller`` (after the MIN(corpus, document) filter,
        before the ``max_documents`` cap) — their difference is
        ``documents_excluded_by_visibility``; ``documents_truncated`` then
        reflects only the ``max_documents`` cap applied to the visible set.
        """
        from opencontractserver.annotations.models import AuthorityNamespace

        user, corpus, documents = self._load(corpus_id, creator_id)
        documents_total_in_corpus, documents_excluded = self._document_visibility_audit(
            user, corpus, documents, surface="discover"
        )
        documents_visible_to_caller = len(documents)
        documents_truncated = (
            max_documents is not None and documents_visible_to_caller > max_documents
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

        # Read-time classification uses the SAME ladder the writer stamps at
        # persist time (candidate -> AuthorityNamespace -> classify_prefix), so
        # the inventory and the durable rows never disagree.
        from opencontractserver.enrichment.authorities import classify_canonical_key

        by_key: dict[str, dict] = {}
        by_jurisdiction: Counter = Counter()
        by_type: Counter = Counter()
        for r in main_resolutions:
            key = r.canonical_key
            if not key:
                continue
            cand = r.candidate
            prefix = key.split(":", 1)[0]
            jur, typ = classify_canonical_key(
                key,
                cand.jurisdiction,
                cand.authority_type,
                namespace_cache=ns_class,
            )
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
            "documents_visible_to_caller": documents_visible_to_caller,
            "documents_total_in_corpus": documents_total_in_corpus,
            "documents_excluded_by_visibility": documents_excluded,
            "documents_truncated": documents_truncated,
            "total_candidates": len(resolutions),
            "by_key": by_key,
            "by_jurisdiction": dict(by_jurisdiction),
            "by_authority_type": dict(by_type),
            "new_namespaces": new_namespaces,
            "review_candidates": [
                {
                    "canonical_key": r.canonical_key,
                    "raw_text": r.candidate.raw_text[
                        : C.REVIEW_CANDIDATE_RAW_TEXT_MAX_LEN
                    ],
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

        Detection tiers mirror :meth:`discover`: ``extra_tiers=None`` runs
        registry **plus** the open-vocabulary grammar so the persisted web
        matches the inventory ``discover`` surfaces (gap-5 — previously apply
        defaulted to registry-only, so grammar-discovered authorities never
        reached the frontier / governance graph). Pass ``extra_tiers=[]`` for a
        registry-only pass; the LLM tier stays opt-in (cost).

        Unlike ``discover()``'s ``use_llm`` flag, the write path takes an
        explicit ``extra_tiers`` list (e.g.
        ``[C.DETECTION_TIER_GRAMMAR, C.DETECTION_TIER_LLM]``) so what gets
        persisted is always spelled out at the call site.
        """
        user, corpus, documents = self._load(corpus_id, creator_id)
        # apply is the higher-stakes path: a document excluded by the
        # MIN(corpus, document) filter is silently absent from the persisted
        # web (no Annotation/CorpusReference rows), yet the run still completes
        # COMPLETED. Surface the exclusion (count + WARNING) so the gap is
        # auditable rather than invisible.
        documents_total_in_corpus, documents_excluded = self._document_visibility_audit(
            user, corpus, documents, surface="apply"
        )
        if extra_tiers is None:
            extra_tiers = [C.DETECTION_TIER_GRAMMAR]
        if analysis is None:
            analysis = self._get_analysis(corpus, creator_id)

        # Make the concurrent-run hazard explicit. Two enrichment runs on the
        # same corpus are *safe* — the claim rule lets a later successful run
        # reclaim + finalize the earlier run's provisional rows, and the crawl
        # seed reads finalized rows only — but the earlier run can then finalize
        # zero of its own rows and complete "empty". That's confusing in the
        # logs without this warning. (Cheap COUNT; no lock — purely advisory.)
        concurrent = (
            Analysis.objects.filter(
                analyzed_corpus_id=corpus_id,
                analyzer__task_name=C.ENRICHMENT_ANALYZER_TASK,
                status=JobStatus.RUNNING.value,
            )
            .exclude(pk=analysis.pk)
            .count()
        )
        if concurrent:
            logger.warning(
                "Enrichment apply: %s other RUNNING enrichment analysis(es) on "
                "corpus %s. Concurrent runs are safe (claim rule + finalized-only "
                "crawl seed) but the earlier run may finalize 0 rows and complete "
                "empty as this run claims them.",
                concurrent,
                corpus_id,
            )

        writer = EnrichmentWriter(corpus, creator_id, analysis=analysis)

        # Named to match discover()'s convention: this is the MIN-filtered
        # (visible) count, NOT the corpus-as-gate total — see
        # ``documents_total_in_corpus`` above. A progress log or return value
        # keyed off the corpus total here would misrepresent an
        # excluded-documents run as covering the whole corpus.
        documents_visible_to_caller = len(documents)
        agg = WriteResult()
        total_candidates = 0
        try:
            # Stream per document: each write commits in its own transaction
            # (the @corpus_analyzer_task decorator does NOT wrap the task body),
            # so references become queryable mid-run instead of only at the end
            # of a long (e.g. LLM-tier) pass. Rows are marked provisional and
            # finalized atomically once the whole run succeeds (below).
            if C.DETECTION_TIER_LLM in extra_tiers:
                # The LLM tier is the expensive one; run detection CONCURRENTLY
                # across documents (the per-document loop serialised them, so a
                # few large documents bottlenecked at single-document
                # concurrency). Still writes each document provisionally as its
                # detection completes — same incremental visibility.
                agg, total_candidates = async_to_sync(self._aresolve_documents)(
                    corpus, documents, types, user, extra_tiers, writer
                )
            else:
                for index, (doc, doc_resolutions) in enumerate(
                    self._iter_doc_resolutions(
                        corpus, documents, types, user, extra_tiers=extra_tiers
                    ),
                    start=1,
                ):
                    # needs_review candidates are inventory-only (discover
                    # surfaces them for human triage); filter them per document,
                    # as the whole-list path did before streaming.
                    doc_resolutions = [
                        r
                        for r in doc_resolutions
                        if not (r.candidate.normalized_data or {}).get("needs_review")
                    ]
                    total_candidates += len(doc_resolutions)
                    res = writer.write(
                        doc_resolutions, provisional=True, reconcile_graph=False
                    )
                    self._accumulate(agg, res)
                    logger.info(
                        "Enrichment apply: doc %s/%s (corpus %s) — refs so far=%s",
                        index,
                        documents_visible_to_caller,
                        corpus_id,
                        agg.references_created,
                    )

            # Corpus-wide DocumentRelationship rollup — once, over the full set
            # of resolved doc->doc references (a per-document reconcile would
            # prune edges whose backing references later documents had not yet
            # written).
            graph_res = writer.reconcile_document_graph()
            agg.document_relationships_created += (
                graph_res.document_relationships_created
            )
            agg.document_relationships_pruned += graph_res.document_relationships_pruned

            # Finalize: one atomic flip of THIS run's provisional rows (new and
            # claimed). This is the tie to job completion — only a run that
            # reaches here finalizes its references. A failure anywhere above
            # leaves them provisional (surfaced but excluded from the crawl
            # seed) for a later successful run to reclaim and finalize.
            CorpusReference.objects.filter(
                created_by_analysis=analysis, is_provisional=True
            ).update(is_provisional=False, modified=timezone.now())

            # Cross-corpus linking is part of a successful apply and can raise
            # (two bulk_updates over potentially thousands of rows), so it must
            # run INSIDE the try — before the COMPLETED stamp below. Stamping the
            # Analysis COMPLETED before it ran left a permanent COMPLETED
            # provenance row with law_references_linked=0 whenever _link_external
            # failed (#1996).
            link = self._link_external(user, corpus)
        except Exception:
            analysis.status = JobStatus.FAILED.value
            analysis.save(update_fields=["status"])
            raise
        analysis.status = JobStatus.COMPLETED.value
        analysis.save(update_fields=["status"])
        return {
            "corpus_id": corpus_id,
            "analysis_id": analysis.id,
            "documents_scanned": documents_visible_to_caller,
            "documents_total_in_corpus": documents_total_in_corpus,
            "documents_excluded_by_visibility": documents_excluded,
            "total_candidates": total_candidates,
            "annotations_created": agg.annotations_created,
            "annotations_upgraded": agg.annotations_upgraded,
            "relationships_created": agg.relationships_created,
            "references_created": agg.references_created,
            "references_resolved": agg.references_resolved,
            "document_relationships_created": agg.document_relationships_created,
            "document_relationships_pruned": agg.document_relationships_pruned,
            "law_references_linked": link["law_references_linked"],
            "links_demoted": link.get("links_demoted", 0),
            "links_restamped": link["links_restamped"],
        }

    @staticmethod
    def _accumulate(agg: WriteResult, res: WriteResult) -> None:
        """Fold one per-document :class:`WriteResult` into the run aggregate.

        Document-graph counts are excluded here — the rollup runs once after the
        per-document loop (see :meth:`apply`), so they are added from its own
        result, never per document.
        """
        agg.annotations_created += res.annotations_created
        agg.annotations_upgraded += res.annotations_upgraded
        agg.relationships_created += res.relationships_created
        agg.references_created += res.references_created
        agg.references_resolved += res.references_resolved
        agg.annotation_ids.extend(res.annotation_ids)
        agg.reference_ids.extend(res.reference_ids)

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
            "links_demoted": 0,
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

        # Match the exact wanted keys (covers colon-less WHOLE-ACT keys like
        # ``exchange-act``, which no ``prefix:`` startswith can reach) PLUS any
        # subsection ref that rolls up to a wanted section root. Superset of the
        # Python candidate_keys matcher below, which does the exact root match.
        prefix_filter = Q(canonical_key__in=wanted)
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
            summary["links_demoted"] += out.get("links_demoted", 0)
            summary["links_restamped"] += out["links_restamped"]
            if out["law_references_linked"] or out.get("links_demoted", 0):
                summary["corpora_relinked"] += 1
        return summary

    def _link_external(self, user, corpus) -> dict:
        """Reconcile this corpus's law-reference links against its audience.

        A link must be navigable by EVERYONE who can read the citing corpus, or
        it 404s for some viewer (e.g. a public corpus linking into a private
        authority — issue surfaced on the S-1 demo). So resolution is scoped to
        the corpus's *audience floor*: anonymous for a public corpus (only
        public authorities may link), the creator otherwise.

        The pass is bidirectional:

        * **promote** — an EXTERNAL ref whose target is audience-visible becomes
          RESOLVED;
        * **demote** — a RESOLVED ref whose target is no longer audience-visible
          (authority went private, was deleted, …) reverts to EXTERNAL,

        so a public corpus can never render a broken link. Pass 2
        (``_restamp_mention_links``) then mirrors each mention's ``link_url``
        onto its ref's resolution state — set when resolved, cleared when not —
        which also repairs slug drift on still-resolved mentions.
        """
        from opencontractserver.documents.models import Document, DocumentPath
        from opencontractserver.enrichment.authorities import find_authority_target

        # Audience floor: a public corpus's links must resolve for anonymous, so
        # only public authorities may link; a private corpus uses its creator.
        audience = None if corpus.is_public else user

        # Materialize once: this queryset is walked twice (build the target
        # cache below, then promote/demote). Left lazy, a concurrent apply() on
        # the same corpus could insert rows that pass 2 sees but that were absent
        # when the cache was built in pass 1 — those refs would be silently
        # skipped (#1996).
        refs = list(
            CorpusReference.objects.filter(corpus=corpus, reference_type=C.REF_LAW)
            .exclude(canonical_key=None)
            .select_related("source_annotation")
        )
        # Resolve each distinct key once under the audience floor.
        target_cache: dict[str, Document | None] = {}
        for ref in refs:
            key = ref.canonical_key
            if key and key not in target_cache:
                target_cache[key] = find_authority_target(key, audience)
        # Map each resolved target document to the corpus its in-app link should
        # point into. A target can have current paths in several corpora, so the
        # choice is made BOTH deterministic and navigable: prefer a corpus the
        # citing corpus's audience can actually open, then break ties on the
        # lowest corpus_id. The previous ``dict(values_list(...))`` did neither —
        # it kept whatever row Postgres returned last, so target_corpus_id (and
        # the mention link_url derived from it) was nondeterministic and could
        # 404 for the audience (#1996). Still one query for the paths plus one
        # for the visible-corpus set — no per-target N+1.
        resolved_target_ids = {t.id for t in target_cache.values() if t is not None}
        path_rows = list(
            DocumentPath.objects.filter(
                document_id__in=resolved_target_ids,
                is_current=True,
                is_deleted=False,
            )
            .order_by("corpus_id")
            .values_list("document_id", "corpus_id")
        )
        audience_visible_corpus_ids = set(
            Corpus.objects.visible_to_user(audience)
            .filter(id__in={cid for _doc_id, cid in path_rows})
            .values_list("id", flat=True)
        )
        path_corpus_cache: dict[int, int] = {}
        for doc_id, path_corpus_id in path_rows:  # ascending corpus_id
            incumbent = path_corpus_cache.get(doc_id)
            # First (lowest-id) path seeds the entry; a later audience-visible
            # corpus then supersedes a non-navigable incumbent. Net result:
            # lowest audience-visible corpus_id, else lowest corpus_id (so a
            # resolvable target never loses its corpus).
            if incumbent is None or (
                path_corpus_id in audience_visible_corpus_ids
                and incumbent not in audience_visible_corpus_ids
            ):
                path_corpus_cache[doc_id] = path_corpus_id
        now = timezone.now()
        promoted: list[CorpusReference] = []
        demoted: list[CorpusReference] = []
        for ref in refs:
            key = ref.canonical_key
            if not key:  # queryset excludes None; guard for type-narrowing
                continue
            target = target_cache.get(key)
            # A navigable link needs BOTH a resolved authority document and a
            # current corpus path to point into. The corpus is absent only in
            # the tiny TOCTOU window where the target's path is deleted between
            # find_authority_target (which requires a current path) and the path
            # query above; treat that as unresolved so a stale RESOLVED ref is
            # demoted rather than left pointing at a broken link.
            target_corpus_id = (
                path_corpus_cache.get(target.id) if target is not None else None
            )
            if target is not None and target_corpus_id is not None:
                if (
                    ref.target_document_id != target.id
                    or ref.resolution_status != C.STATUS_RESOLVED
                ):
                    ref.target_document = target
                    ref.target_corpus_id = target_corpus_id
                    ref.resolution_status = C.STATUS_RESOLVED
                    # bulk_update bypasses auto_now — stamp ``modified``.
                    ref.modified = now
                    promoted.append(ref)
            elif (
                ref.target_document_id is not None
                or ref.resolution_status == C.STATUS_RESOLVED
            ):
                # Target gone, no longer audience-visible, or (rarely) its path
                # vanished mid-pass — degrade so the corpus never renders a
                # broken link.
                ref.target_document_id = None
                ref.target_corpus_id = None
                ref.resolution_status = C.STATUS_EXTERNAL
                ref.modified = now
                demoted.append(ref)

        # One query instead of O(N) row-by-row saves (corpora carry
        # hundreds-to-thousands of law references at demo scale).
        if promoted or demoted:
            CorpusReference.objects.bulk_update(
                promoted + demoted,
                ["target_document", "target_corpus", "resolution_status", "modified"],
            )
        restamped = self._restamp_mention_links(corpus)
        return {
            "corpus_id": corpus.id,
            "law_references_linked": len(promoted),
            "links_demoted": len(demoted),
            "links_restamped": restamped,
        }

    def _restamp_mention_links(self, corpus) -> int:
        """Mirror each law/document mention's ``link_url`` onto its ref's state.

        The canonical slug path is the only shape the frontend router serves
        (anything else 404s). A RESOLVED ref's mention gets the link into the
        target (authority) corpus; an EXTERNAL ref's mention gets ``None`` — so a
        demoted reference (its authority no longer audience-visible) stops
        rendering as a clickable link instead of pointing at a 404. LAW refs
        link into ``target_corpus``; DOCUMENT refs target a sibling document of
        the source corpus (``target_corpus`` is null). Only mentions whose
        stored link differs are written back.
        """
        from django.db.models import Q

        # Bound the scan to refs that can actually change: either RESOLVED (need
        # a link computed/refreshed) or carrying a non-null mention link_url
        # (formerly resolved, now demoted → needs clearing). Every other ref is
        # unresolved with an already-null link, so the loop below would compute
        # link_url=None and skip the write — loading them only inflates memory
        # (tens of thousands of unresolved refs on a large corpus).
        refs = (
            CorpusReference.objects.filter(
                corpus=corpus,
                reference_type__in=(C.REF_LAW, C.REF_DOCUMENT),
            )
            .filter(
                Q(resolution_status=C.STATUS_RESOLVED)
                | Q(source_annotation__link_url__isnull=False)
            )
            .select_related(
                "source_annotation", "target_document", "target_corpus__creator"
            )
        )
        now = timezone.now()
        changed: dict[int, Annotation] = {}
        for ref in refs:
            mention = ref.source_annotation
            if mention is None:
                continue
            target_document = ref.target_document
            if (
                ref.resolution_status == C.STATUS_RESOLVED
                and target_document is not None
            ):
                target_corpus = ref.target_corpus or corpus
                link_url = document_in_corpus_path(
                    corpus_creator_slug=target_corpus.creator.slug,
                    corpus_slug=target_corpus.slug,
                    document_slug=target_document.slug,
                )
            else:
                # Unresolved / demoted — no clickable link.
                link_url = None
            if mention.link_url != link_url:
                mention.link_url = link_url
                # bulk_update bypasses auto_now — stamp ``modified`` explicitly.
                mention.modified = now
                changed[mention.pk] = mention
        if changed:
            Annotation.objects.bulk_update(changed.values(), ["link_url", "modified"])
        return len(changed)
