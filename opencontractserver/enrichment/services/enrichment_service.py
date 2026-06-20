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

        # Read each document's text once (isolating per-doc read failures).
        doc_texts: dict[int, str] = {}
        for doc in documents:
            try:
                text = read_field_file_text(doc.txt_extract_file)
            except Exception as exc:
                logger.warning(
                    "Enrichment: skip doc %s (text read failed: %s)", doc.id, exc
                )
                continue
            if text:
                doc_texts[doc.id] = text

        # Run every document's LLM tier inside a SINGLE async_to_sync bridge
        # rather than one bridge per document. The documents are still processed
        # sequentially inside _extract_all (intentional: avoids LLM-provider
        # rate-limit bursts and keeps per-document error isolation simple) — the
        # win is consolidating the sync/async boundary crossing, not concurrency.
        # Safe under both sync and _db_sync_to_async-wrapped async callers.
        llm_by_doc: dict[int, list] = {}
        if llm_extractor is not None and doc_texts:

            async def _extract_all() -> dict[int, list]:
                out: dict[int, list] = {}
                for did, txt in doc_texts.items():
                    out[did] = await llm_extractor.aextract(txt)
                return out

            llm_by_doc = async_to_sync(_extract_all)()

        resolutions: list[Resolution] = []
        for doc in documents:
            doc_text = doc_texts.get(doc.id)
            if doc_text is None:
                continue
            sections = sections_by_doc.get(doc.id, [])
            meta = doc.custom_meta if isinstance(doc.custom_meta, dict) else {}
            primary = list(
                extractor.extract(doc_text, default_authority=meta.get("authority"))
            )
            if generic is not None:
                # Registry wins on overlap; generic adds the open-vocabulary tail.
                cands = reconcile(primary, generic.extract(doc_text))
            else:
                cands = primary
            if llm_extractor is not None:
                cands = reconcile(cands, llm_by_doc.get(doc.id, []))
            for cand in cands:
                if cand.reference_type not in wanted:
                    continue
                resolutions.append(resolver.resolve(cand, doc.id, doc_text, sections))
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
        if extra_tiers is None:
            extra_tiers = [C.DETECTION_TIER_GRAMMAR]
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
            # Cross-corpus linking is part of a successful apply and can raise
            # (two bulk_updates over potentially thousands of rows), so it must
            # run INSIDE the try. Stamping the Analysis COMPLETED before it ran
            # left a permanent COMPLETED provenance row with
            # law_references_linked=0 whenever _link_external failed (#1996).
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
            "documents_scanned": len(documents),
            "total_candidates": len(resolutions),
            "annotations_created": res.annotations_created,
            "annotations_upgraded": res.annotations_upgraded,
            "relationships_created": res.relationships_created,
            "references_created": res.references_created,
            "document_relationships_created": res.document_relationships_created,
            "document_relationships_pruned": res.document_relationships_pruned,
            "law_references_linked": link["law_references_linked"],
            "links_demoted": link.get("links_demoted", 0),
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
            if target is not None:
                if (
                    ref.target_document_id != target.id
                    or ref.resolution_status != C.STATUS_RESOLVED
                ):
                    ref.target_document = target
                    ref.target_corpus_id = path_corpus_cache.get(target.id)
                    ref.resolution_status = C.STATUS_RESOLVED
                    # bulk_update bypasses auto_now — stamp ``modified``.
                    ref.modified = now
                    promoted.append(ref)
            elif (
                ref.target_document_id is not None
                or ref.resolution_status == C.STATUS_RESOLVED
            ):
                # Target no longer visible to the corpus's audience — degrade so
                # the corpus never renders a broken link.
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
