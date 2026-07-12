"""Deterministic HTS-code and CBP-ruling-citation enrichment.

**Not a general OpenContracts feature.** This is purpose-built for corpora of
CBP CROSS customs rulings (or any similarly-shaped corpus: each document's
title IS an external identifier — a ruling number — and documents cite each
other by that identifier in their own text). It has no place in the general
open-vocabulary authority-discovery system (:mod:`opencontractserver.enrichment.services.enrichment_service`),
which is scoped to statutory/regulatory (``REF_LAW``) citations across any
legal corpus — HTS tariff codes and CBP ruling numbers are neither.

Detection runs against each document's OWN parsed text (via
``load_document_text_and_layer`` — the same PAWLs-token-anchored text the
parser saved), never against text from before PDF conversion: a ``.doc``
source is converted to PDF and re-parsed by Warp-Ingest before this service
ever sees it, so offsets are always computed against the text OpenContracts
actually stored, not the original document.

Two different shapes, two different persistence paths:

* HTS codes are a plain classification tag — not a reference to anything —
  so they become bare ``Annotation`` rows with no ``CorpusReference``.
* Ruling-number citations are cross-document references, so they are modeled
  as :class:`~opencontractserver.enrichment.extractor.Candidate` /
  :class:`~opencontractserver.enrichment.resolver.Resolution` objects
  (``reference_type=REF_DOCUMENT``) and persisted via
  :class:`~opencontractserver.enrichment.writer.EnrichmentWriter` — the same
  hardened writer the authority-discovery system uses, so PDF token
  projection, annotation dedup, ``CorpusReference`` creation, and the
  ``DocumentRelationship`` graph rollup are reused rather than reimplemented.
"""

from __future__ import annotations

import concurrent.futures
import logging
import re
from dataclasses import dataclass
from pathlib import Path

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from opencontractserver.analyzer.models import Analysis, Analyzer
from opencontractserver.annotations.models import (
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

# Per-document cost is dominated by load_document_text_and_layer's S3 fetch +
# PAWLS JSON parse (~230ms measured on a 220K-doc corpus), not by the regex
# matching or DB writes that follow. That fetch touches no ORM state, so it
# is safe to prefetch across threads (releases the GIL during socket I/O)
# while the actual writes stay single-threaded on the caller. Sized well
# above CPU count since this is I/O-bound, not compute-bound; not so high
# that it floods the storage backend with concurrent connections.
PREFETCH_WORKERS = 12

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

    Titles are set at ingest time from the materialized filename — some
    ingest paths use the bare stem (``A83482``), others keep the original
    filename including its extension (``A83482.doc``). The citation regex
    only ever extracts the bare form (it has no ``.doc``/``.pdf`` in its
    character class), so a title carrying an extension would never match
    ``title_index`` and every citation into that document would silently
    read as unresolved. ``Path(...).stem`` strips at most one trailing
    extension and is a no-op on titles that are already extension-free.
    """
    return Path((title or "").strip()).stem.upper()


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
    documents_skipped_not_pdf: int = 0


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
        *resolution* still considers every document's title in the corpus,
        not just the scanned subset, so a limited run can still resolve a
        citation to a sibling ruling outside the scanned slice.
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

        # Ruling number (as it appears in a sibling document's title, upper-
        # cased and extension-stripped — see _ruling_number_from_title) ->
        # document. Built from the FULL document list regardless of `limit`
        # so resolution isn't artificially degraded by which slice happened
        # to get scanned.
        title_index = {
            _ruling_number_from_title(doc.title): doc for doc in documents if doc.title
        }

        scanned_documents = documents if limit is None else documents[:limit]
        summary = EnrichmentSummary(documents_scanned=len(scanned_documents))

        writer = EnrichmentWriter(corpus, creator_id, analysis=analysis)

        try:
            with concurrent.futures.ThreadPoolExecutor(
                max_workers=PREFETCH_WORKERS
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
                        summary.documents_skipped_not_pdf += 1
                        continue
                    if ann_type != TOKEN_LABEL or layer is None:
                        # Only PDF/PAWLs-token-anchored documents are
                        # supported — HTS/ruling mentions need a page +
                        # bounding box to be useful annotations.
                        summary.documents_skipped_not_pdf += 1
                        continue

                    own_number = _ruling_number_from_title(doc.title)

                    hts_created = cls._write_hts_annotations(
                        doc, layer, doc_text, corpus, creator_id
                    )
                    summary.hts_codes_created += hts_created
                    summary.annotations_created += hts_created

                    resolutions = cls._build_citation_resolutions(
                        doc, layer, doc_text, own_number, title_index
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
        doc, layer, doc_text: str, corpus, creator_id: int
    ) -> int:
        """Create bare (non-reference) HTS_CODE annotations for one document.

        Deduped by (document, start) against pre-existing HTS_CODE annotations
        so re-running only adds newly-found codes.
        """
        matches = []
        seen_codes: set[str] = set()
        for m in _HTS_TEXT_RE.finditer(doc_text):
            code = _normalize_hts(m.group())
            if code is None:
                continue
            matches.append((m.start(), m.end(), m.group(), code))
            seen_codes.add(code)
        if not matches:
            return 0

        label = corpus.ensure_label_and_labelset(
            label_text=LABEL_HTS_CODE, creator_id=creator_id, label_type=TOKEN_LABEL
        )
        existing_starts = set(
            Annotation.objects.filter(
                document_id=doc.id, corpus=corpus, annotation_label=label
            ).values_list("data__char_span__start", flat=True)
        )

        created = 0
        with transaction.atomic():
            for start, end, raw_text, code in matches:
                if start in existing_starts:
                    continue
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
                Annotation.objects.create(
                    raw_text=projected_raw,
                    page=page,
                    json=annotation_json,
                    annotation_label=label,
                    document_id=doc.id,
                    corpus=corpus,
                    creator_id=creator_id,
                    annotation_type=TOKEN_LABEL,
                    structural=False,
                    data={"code": code, "char_span": {"start": start, "end": end}},
                )
                existing_starts.add(start)
                created += 1
        return created

    @staticmethod
    def _build_citation_resolutions(
        doc, layer, doc_text: str, own_number: str, title_index: dict
    ) -> list[Resolution]:
        """Ruling-citation Candidates + Resolutions for one document.

        Resolved against sibling document titles in the SAME corpus; a
        citation to a ruling not present in this corpus is UNRESOLVED (still
        recorded as a mention, no target).
        """
        resolutions: list[Resolution] = []
        seen: set[str] = {own_number}
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
            target = title_index.get(number)
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
