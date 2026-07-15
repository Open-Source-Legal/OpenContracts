"""Deterministic HTS-code and CBP-ruling-citation enrichment.

**Not a general OpenContracts feature.** This is purpose-built for corpora of
CBP CROSS customs rulings (or any similarly-shaped corpus: each document HAS
an external identifier — a ruling number — and documents cite each other by
that identifier in their own text). It has no place in the general
open-vocabulary authority-discovery system (:mod:`opencontractserver.enrichment.services.enrichment_service`),
which is scoped to statutory/regulatory (``REF_LAW``) citations across any
legal corpus — HTS tariff codes and CBP ruling numbers are neither.

Detection runs against each document's OWN parsed text (via
``load_document_text_and_layer`` — the same text the parser saved), never
against text from before format conversion, so offsets are always computed
against the text OpenContracts actually stored, not the original document.

Anchoring type is an INPUT to persistence, not an eligibility gate: PDF
documents get ``TOKEN_LABEL`` annotations projected onto PAWLs bounding
boxes; ``text/plain`` documents (the official CROSS bulk exporter's output —
see ``docs/benchmarks/pr2153-cross-txt-enrichment-handoff.md``) get
``SPAN_LABEL`` annotations in the canonical text-span shape the TXT renderer
consumes. Requiring a PDF here is exactly the format gate that made a
10,000-document official-export run produce zero output.

Canonical ruling identity is derived from the document's active corpus path /
``DocumentPath.external_id`` — never from the display title alone (the
official exporter's titles are human-readable SUBJECTS: non-unique and free
to carry control characters). See :meth:`CustomsRulingCitationService._build_ruling_identity_index`.

Two different shapes, two different persistence paths:

* HTS codes are a plain classification tag — not a reference to anything —
  so they become bare ``Annotation`` rows with no ``CorpusReference``.
* Ruling-number citations are cross-document references, so they are modeled
  as :class:`~opencontractserver.enrichment.extractor.Candidate` /
  :class:`~opencontractserver.enrichment.resolver.Resolution` objects
  (``reference_type=REF_DOCUMENT``) and persisted via
  :class:`~opencontractserver.enrichment.writer.EnrichmentWriter` — the same
  hardened writer the authority-discovery system uses, so PDF token
  projection, span fallback, annotation dedup, ``CorpusReference`` creation,
  and the ``DocumentRelationship`` graph rollup are reused rather than
  reimplemented.
"""

from __future__ import annotations

import concurrent.futures
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from opencontractserver.analyzer.models import Analysis, Analyzer
from opencontractserver.annotations.models import (
    SPAN_LABEL,
    TOKEN_LABEL,
    Annotation,
    CorpusReference,
)
from opencontractserver.corpuses.models import Corpus
from opencontractserver.corpuses.services.corpus_documents import (
    CorpusDocumentService,
)
from opencontractserver.enrichment import constants as C
from opencontractserver.enrichment.extractor import Candidate
from opencontractserver.enrichment.resolver import Resolution
from opencontractserver.enrichment.writer import EnrichmentWriter
from opencontractserver.types.enums import JobStatus
from opencontractserver.utils.span_projection import (
    load_document_text_and_layer,
    project_span_to_token_annotation,
    span_annotation_payload,
)

logger = logging.getLogger(__name__)

User = get_user_model()

# Provenance Analyzer row — distinct from the general authority-discovery
# Analyzer (C.ENRICHMENT_ANALYZER_ID) so this service's runs are attributable
# and don't share a concurrency-warning namespace with unrelated corpora.
ANALYZER_ID = "customs-ruling-citation-enrichment"
ANALYZER_TASK_NAME = "opencontractserver.enrichment.customs_ruling_citations"
ANALYZER_TITLE = "Customs Ruling Citation Enrichment"

LABEL_HTS_CODE = "HTS_CODE"

# Namespace for a durable ruling identity carried on
# ``DocumentPath.external_id`` (e.g. ``cross:H022844``). The import contract
# does not populate it yet — when it does, it outranks path/title derivation.
EXTERNAL_ID_NAMESPACE = "cross:"

# --- HTS tariff codes -------------------------------------------------------
# Ported from crossfeed's crossfeed.parse.normalize (the CROSS-rulings
# acquisition project's own deterministic, golden-tested extractor). Requires
# at least heading.subheading so bare 4-digit numbers (years, quantities)
# aren't mined.
_HTS_TEXT_RE = re.compile(r"\b\d{4}\.\d{2}(?:\.\d{2,4})?(?:\.\d{2})?\b")


def _normalize_hts(raw: str) -> str | None:
    """Canonicalize an HTS code to dotted ``XXXX.XX[.XX[.XX]]`` form, or None.

    Strips all non-digits, regroups as 4 + 2-digit groups. Accepts 4/6/8/10
    digit codes; anything else is rejected.
    """
    digits = re.sub(r"\D", "", raw)
    if len(digits) not in (4, 6, 8, 10):
        return None
    groups = [digits[:4], *[digits[i : i + 2] for i in range(4, len(digits), 2)]]
    return ".".join(groups)


# --- CBP ruling-number citations -------------------------------------------
# Ported from crossfeed's crossfeed.parse.normalize. Documented false-positive
# guard: only PREFIXED ruling numbers are mined — 1 letter + 5-6 digits
# (modern N######/H######; legacy A#####, K#####, ...) or 2 letters + 6
# digits (two-letter legacy). Bare 6-digit legacy numbers are deliberately
# NOT mined here (dollar amounts, statute numbers, and "STATE + 5-digit ZIP"
# like "NY 10022" are common false positives for that shape).
_RULING_CITE_RE = re.compile(r"\b([A-Z]\d{5,6}|[A-Z]{2}\d{6})\b")


def _ruling_number_from_title(title: str | None) -> str:
    """Canonicalize a document title to the bare ruling number it names.

    Legacy ingest paths titled documents with the materialized filename —
    some use the bare stem (``A83482``), others keep the original filename
    including its extension (``A83482.doc``). The citation regex only ever
    extracts the bare form (it has no ``.doc``/``.pdf`` in its character
    class), so ``Path(...).stem`` strips at most one trailing extension and
    is a no-op on titles that are already extension-free. Titles are the
    LAST-priority identity source — see ``_ruling_identity``.
    """
    return Path((title or "").strip()).stem.upper()


def _ruling_number_from_path(path: str) -> str:
    """Canonicalize a corpus path to the ruling number in its basename stem.

    The official CROSS bulk exporter writes ``{COLLECTION}/{ruling_number}.txt``
    (e.g. ``HQ/H022844.txt``), so the active ``DocumentPath`` basename is the
    exporter's own canonical identity for the document.
    """
    return Path(path).stem.upper()


@dataclass
class EnrichmentSummary:
    documents_scanned: int = 0
    hts_codes_created: int = 0
    citation_candidates: int = 0
    citations_resolved: int = 0
    citations_unresolved: int = 0
    annotations_created: int = 0
    references_created: int = 0
    references_resolved: int = 0
    document_relationships_created: int = 0
    document_relationships_pruned: int = 0
    # Documents whose text could not be loaded/anchored at all (loader error,
    # missing extract, unsupported type). Supported non-PDF input is NOT a
    # skip — TXT documents are processed as spans.
    documents_skipped_unanchorable: int = 0
    # Distinct canonical ruling numbers claimed by more than one document.
    # Reported (and left unresolved) rather than resolved arbitrarily.
    canonical_id_collisions: int = 0


class CustomsRulingCitationService:
    """Runs HTS-code + ruling-citation detection over a corpus of rulings."""

    @staticmethod
    def get_or_create_analyzer(creator_id: int) -> Analyzer:
        analyzer = Analyzer.objects.filter(task_name=ANALYZER_TASK_NAME).first()
        if analyzer is None:
            analyzer, _ = Analyzer.objects.get_or_create(
                id=ANALYZER_ID,
                defaults={
                    "task_name": ANALYZER_TASK_NAME,
                    "description": ANALYZER_TITLE,
                    "creator_id": creator_id,
                },
            )
        return analyzer

    @classmethod
    def enrich_corpus(
        cls, *, corpus_id: int, creator_id: int, limit: int | None = None
    ) -> dict:
        """Detect + persist HTS codes and ruling citations for one corpus.

        Document loading uses the MIN(corpus, document) visibility variant
        (matching :mod:`enrichment_service`'s own Tier-0 discipline): a caller
        with corpus READ but not per-document READ never has a private
        document scanned or written to.

        ``limit``, when set, restricts the documents actually *scanned* to a
        deterministic (lowest-id-first) subset of size ``limit`` — for a
        quick, fully-complete pass over a manageable slice (evaluating
        output quality/UX on a corpus too large to enrich end-to-end in one
        sitting) rather than a partial pass over the whole corpus. Citation
        *resolution* still considers every document's canonical identity in
        the corpus, not just the scanned subset, so a limited run can still
        resolve a citation to a sibling ruling outside the scanned slice.
        """
        user = User.objects.get(pk=creator_id)
        corpus = Corpus.objects.visible_to_user(user).get(pk=corpus_id)
        documents = list(
            CorpusDocumentService.get_corpus_documents_visible_to_user(
                user, corpus, include_caml=False
            )
        )
        documents.sort(key=lambda doc: doc.id)

        analyzer = cls.get_or_create_analyzer(creator_id)
        analysis = Analysis.objects.create(
            analyzer=analyzer,
            analyzed_corpus=corpus,
            creator_id=creator_id,
            status=JobStatus.RUNNING.value,
        )

        # Canonical ruling number -> document, derived from active corpus
        # paths / external_id (title only as legacy fallback). Built from the
        # FULL document list regardless of `limit` so resolution isn't
        # artificially degraded by which slice happened to get scanned.
        doc_by_number, own_numbers_by_doc_id, collision_count = (
            cls._build_ruling_identity_index(corpus, documents)
        )

        scanned_documents = documents if limit is None else documents[:limit]
        summary = EnrichmentSummary(
            documents_scanned=len(scanned_documents),
            canonical_id_collisions=collision_count,
        )

        writer = EnrichmentWriter(corpus, creator_id, analysis=analysis)

        try:
            with concurrent.futures.ThreadPoolExecutor(
                max_workers=cls._prefetch_workers()
            ) as pool:
                loaded = pool.map(cls._safe_load_text_and_layer, scanned_documents)
                for doc, doc_text, layer, ann_type, exc in loaded:
                    if exc is not None:
                        logger.warning(
                            "CustomsRulingCitationService: could not load text "
                            "for doc %s (%s); skipping.",
                            doc.id,
                            exc,
                        )
                        summary.documents_skipped_unanchorable += 1
                        continue
                    if ann_type not in (TOKEN_LABEL, SPAN_LABEL) or (
                        ann_type == TOKEN_LABEL and layer is None
                    ):
                        # Defensive only: the loader contract is TOKEN (with a
                        # layer) or SPAN. Anchoring type is an input to
                        # persistence below, never an eligibility gate — TXT
                        # documents are fully supported as spans.
                        summary.documents_skipped_unanchorable += 1
                        continue

                    hts_created = cls._write_hts_annotations(
                        doc,
                        layer,
                        doc_text,
                        corpus,
                        creator_id,
                        ann_type=ann_type,
                        analysis=analysis,
                    )
                    summary.hts_codes_created += hts_created
                    summary.annotations_created += hts_created

                    resolutions = cls._build_citation_resolutions(
                        doc,
                        doc_text,
                        own_numbers_by_doc_id.get(doc.id, set()),
                        doc_by_number,
                    )
                    summary.citation_candidates += len(resolutions)
                    summary.citations_resolved += sum(
                        1
                        for r in resolutions
                        if r.resolution_status == C.STATUS_RESOLVED
                    )
                    summary.citations_unresolved += sum(
                        1
                        for r in resolutions
                        if r.resolution_status == C.STATUS_UNRESOLVED
                    )
                    if resolutions:
                        res = writer.write(
                            resolutions, provisional=True, reconcile_graph=False
                        )
                        summary.annotations_created += res.annotations_created
                        summary.references_created += res.references_created
                        summary.references_resolved += res.references_resolved

            graph_res = writer.reconcile_document_graph()
            summary.document_relationships_created = (
                graph_res.document_relationships_created
            )
            summary.document_relationships_pruned = (
                graph_res.document_relationships_pruned
            )

            CorpusReference.objects.filter(
                created_by_analysis=analysis, is_provisional=True
            ).update(is_provisional=False, modified=timezone.now())
        except Exception:
            analysis.status = JobStatus.FAILED.value
            analysis.save(update_fields=["status"])
            raise

        analysis.status = JobStatus.COMPLETED.value
        analysis.save(update_fields=["status"])

        return {
            "corpus_id": corpus_id,
            "analysis_id": analysis.id,
            **summary.__dict__,
        }

    @staticmethod
    def _prefetch_workers() -> int:
        """Bounded text-prefetch concurrency (see the setting's comment in
        ``config/settings/base.py``): explicit setting wins; otherwise storage
        pool size minus the caller thread's slot."""
        configured = settings.CUSTOMS_ENRICHMENT_PREFETCH_WORKERS
        if configured is not None:
            return max(1, configured)
        pool_size = getattr(settings, "AWS_S3_CONNECTION_POOL_SIZE", 10)
        return max(1, pool_size - 1)

    @classmethod
    def _build_ruling_identity_index(
        cls, corpus, documents
    ) -> tuple[dict[str, Any], dict[int, set[str]], int]:
        """Canonical ruling number -> document, plus per-document identities.

        Identity is derived per document from the first shape-valid candidate
        in priority order (handoff §D,
        ``docs/benchmarks/pr2153-cross-txt-enrichment-handoff.md``):

        1. an active ``DocumentPath.external_id`` in the ``cross:`` namespace
           (the durable contract, once the import path populates it);
        2. the active corpus path's basename stem — the official CROSS bulk
           exporter writes ``{COLLECTION}/{ruling_number}.txt``;
        3. the display title's stem (legacy ingests titled documents with the
           materialized filename, e.g. ``A83482.doc``).

        Official-export titles are human-readable SUBJECTS — non-unique,
        control-character-laden display metadata — so a candidate only counts
        when it matches the prefixed ruling-number shape the citation regex
        can actually emit (``_RULING_CITE_RE``); anything else can never be
        looked up and must not occupy an identity slot.

        Two documents normalizing to the same identity is AMBIGUITY: the
        number is reported (summary count + warning) and REMOVED from the
        index — citations to it stay unresolved — rather than silently
        resolved to whichever document iteration happened to visit last.

        Returns ``(doc_by_number, own_numbers_by_doc_id, collision_count)``.
        ``own_numbers_by_doc_id`` carries ALL of a document's shape-valid
        identity candidates (not just the winning one) so citation detection
        can suppress a document quoting its own number under any of its
        identities.
        """
        from opencontractserver.documents.models import DocumentPath

        paths_by_doc: dict[int, list[tuple[str, str]]] = {}
        for doc_id, path, external_id in (
            DocumentPath.objects.filter(
                corpus=corpus,
                document_id__in=[doc.id for doc in documents],
                is_current=True,
                is_deleted=False,
            )
            .order_by("document_id", "path")
            .values_list("document_id", "path", "external_id")
        ):
            paths_by_doc.setdefault(doc_id, []).append((path or "", external_id or ""))

        doc_by_number: dict[str, Any] = {}
        own_numbers_by_doc_id: dict[int, set[str]] = {}
        ambiguous: set[str] = set()
        for doc in documents:  # sorted lowest-id-first upstream — deterministic
            candidates = cls._ruling_identity_candidates(
                doc, paths_by_doc.get(doc.id, [])
            )
            own_numbers_by_doc_id[doc.id] = set(candidates)
            if not candidates:
                continue
            number = candidates[0]  # highest-priority shape-valid identity
            if number in ambiguous:
                continue
            claimant = doc_by_number.get(number)
            if claimant is not None and claimant.id != doc.id:
                ambiguous.add(number)
                continue
            doc_by_number[number] = doc

        for number in sorted(ambiguous):
            # Unresolvable, not last-write-wins: drop the first claimant too.
            doc_by_number.pop(number, None)
            logger.warning(
                "CustomsRulingCitationService: ruling number %s is claimed by "
                "multiple documents in corpus %s — citations to it stay "
                "unresolved until the duplicate identity is corrected.",
                number,
                corpus.id,
            )
        return doc_by_number, own_numbers_by_doc_id, len(ambiguous)

    @staticmethod
    def _ruling_identity_candidates(doc, paths: list[tuple[str, str]]) -> list[str]:
        """A document's shape-valid ruling numbers, highest-priority first.

        ``paths`` are the document's active ``(path, external_id)`` pairs —
        see ``_build_ruling_identity_index`` for the priority rationale.
        """
        candidates = [
            external_id[len(EXTERNAL_ID_NAMESPACE) :].strip().upper()
            for _path, external_id in paths
            if external_id.startswith(EXTERNAL_ID_NAMESPACE)
        ]
        candidates += [_ruling_number_from_path(path) for path, _ in paths if path]
        candidates.append(_ruling_number_from_title(doc.title))
        return [c for c in candidates if c and _RULING_CITE_RE.fullmatch(c)]

    @staticmethod
    def _safe_load_text_and_layer(doc):
        """Thread-pool-mapped wrapper around ``load_document_text_and_layer``.

        Returns a fixed-shape tuple instead of raising so ``executor.map()``
        never surfaces a per-document failure as an exception when iterating
        results — the caller checks ``exc`` and logs/skips exactly as the
        pre-parallelization code did with its inline try/except.
        """
        try:
            doc_text, layer, ann_type = load_document_text_and_layer(doc)
            return doc, doc_text, layer, ann_type, None
        except Exception as exc:  # noqa: BLE001 - reported to caller, not swallowed
            return doc, None, None, None, exc

    @staticmethod
    def _write_hts_annotations(
        doc, layer, doc_text: str, corpus, creator_id: int, *, ann_type, analysis
    ) -> int:
        """Create bare (non-reference) HTS_CODE annotations for one document.

        ``ann_type`` selects the persistence shape: ``TOKEN_LABEL`` projects
        each char span onto PAWLs bounding boxes (``layer`` required);
        ``SPAN_LABEL`` stores the canonical text-span shape
        (``annotation_anchoring._anchor_text``) — ``page=0`` is the no-page
        sentinel the frontend suppresses, and a text annotation never
        advertises fake PDF geometry.

        Dedupe is by (document, char start) against ALL pre-existing
        ``HTS_CODE``-labelled annotations, across both representations:
        enrichment rows carry the span in ``data.char_span`` while
        importer-style sidecar spans carry it in ``json`` (attached to a
        TOKEN-typed label — the documented import-contract mismatch, see
        ``test_zip_import_integration``). Legacy producer rows are retained
        as source evidence and never duplicated or relabelled here;
        correcting their label type is a deliberate future migration.
        """
        matches = []
        for m in _HTS_TEXT_RE.finditer(doc_text):
            code = _normalize_hts(m.group())
            if code is None:
                continue
            matches.append((m.start(), m.end(), m.group(), code))
        if not matches:
            return 0

        label = corpus.ensure_label_and_labelset(
            label_text=LABEL_HTS_CODE, creator_id=creator_id, label_type=ann_type
        )
        # Union of both stored span representations (see docstring).
        existing_starts = {
            value
            for row in Annotation.objects.filter(
                document_id=doc.id,
                corpus=corpus,
                annotation_label__text=LABEL_HTS_CODE,
            ).values_list("json__start", "data__char_span__start")
            for value in row
            if value is not None
        }

        created = 0
        with transaction.atomic():
            for start, end, raw_text, code in matches:
                if start in existing_starts:
                    continue
                if ann_type == TOKEN_LABEL:
                    try:
                        annotation_json, page, projected_raw = (
                            project_span_to_token_annotation(
                                layer,
                                start=start,
                                end=end,
                                text=raw_text,
                                label_text=LABEL_HTS_CODE,
                            )
                        )
                    except ValueError as exc:
                        logger.debug(
                            "CustomsRulingCitationService: HTS span->token "
                            "projection failed for doc %s: %s",
                            doc.id,
                            exc,
                        )
                        continue
                else:
                    annotation_json, page = span_annotation_payload(
                        start, end, raw_text
                    )
                    projected_raw = raw_text
                Annotation.objects.create(
                    raw_text=projected_raw,
                    page=page,
                    json=annotation_json,
                    annotation_label=label,
                    document_id=doc.id,
                    corpus=corpus,
                    creator_id=creator_id,
                    annotation_type=ann_type,
                    structural=False,
                    data={"code": code, "char_span": {"start": start, "end": end}},
                    analysis=analysis,
                )
                existing_starts.add(start)
                created += 1
        return created

    @staticmethod
    def _build_citation_resolutions(
        doc,
        doc_text: str,
        own_numbers: set[str],
        doc_by_number: dict,
    ) -> list[Resolution]:
        """Ruling-citation Candidates + Resolutions for one document.

        Resolved against sibling documents' canonical identities in the SAME
        corpus (see ``_build_ruling_identity_index``); a citation to a ruling
        not present — or whose identity is claimed by multiple documents — is
        UNRESOLVED (still recorded as a mention, no target). ``own_numbers``
        (all of the document's own identities) suppresses the header line
        where a ruling quotes its own number.
        """
        resolutions: list[Resolution] = []
        seen: set[str] = set(own_numbers)
        for m in _RULING_CITE_RE.finditer(doc_text):
            number = m.group(1)
            if number in seen:
                continue
            seen.add(number)
            cand = Candidate(
                reference_type=C.REF_DOCUMENT,
                start=m.start(),
                end=m.end(),
                raw_text=m.group(0),
                normalized_data={"ruling_number": number},
            )
            target = doc_by_number.get(number)
            if target is not None and target.id != doc.id:
                resolutions.append(
                    Resolution(
                        candidate=cand,
                        source_document_id=doc.id,
                        resolution_status=C.STATUS_RESOLVED,
                        target_document_id=target.id,
                    )
                )
            else:
                resolutions.append(
                    Resolution(
                        candidate=cand,
                        source_document_id=doc.id,
                        resolution_status=C.STATUS_UNRESOLVED,
                    )
                )
        return resolutions
