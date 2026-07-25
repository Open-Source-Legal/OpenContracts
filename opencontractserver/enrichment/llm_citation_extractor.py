"""Tier-2b LLM citation extractor (Phase 2).

Slides a window across document text, asks an LLM to identify citation spans
with structured output, verifies each span against the source text to reject
hallucinations, and returns :class:`~opencontractserver.enrichment.extractor.Candidate`
objects with ``detection_tier="llm"``.

PRIVACY NOTE: This module transmits raw document text chunks to the configured
external LLM provider (OpenAI, Anthropic, etc.) for analysis. Callers must
treat LLM-based extraction as opt-in and must not enable it for documents
containing sensitive or confidential content without appropriate consent.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, cast

from asgiref.sync import sync_to_async
from pydantic import BaseModel, Field

from opencontractserver.enrichment import constants as C
from opencontractserver.enrichment.extractor import Candidate
from opencontractserver.llms.model_factory import abuild_agent_model

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pydantic schemas for structured LLM output
# ---------------------------------------------------------------------------


class CitationCandidate(BaseModel):
    """One citation the LLM found within a text chunk."""

    raw_text: str = Field(
        description="Exact citation substring, verbatim from the text"
    )
    start: int = Field(
        ge=0, description="Char offset of citation start within this chunk"
    )
    end: int = Field(ge=0, description="Char offset (exclusive) within this chunk")
    jurisdiction: str = Field(description='e.g. "Delaware", "Federal", "California"')
    authority_type: str = Field(description='e.g. "statute", "regulation", "case_law"')
    normalized_citation: str = Field(
        description='Canonical form e.g. "dgcl:145"; "" if none'
    )
    confidence: float = Field(
        ge=0.0, le=1.0, description="0.0-1.0 self-rated confidence"
    )


class ChunkCitationExtraction(BaseModel):
    """Structured output for one chunk."""

    citations: list[CitationCandidate] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

_JURISDICTION_MAP: dict[str, str] = {
    "federal": "us-federal",
    "us": "us-federal",
    "united states": "us-federal",
    "delaware": "us-de",
    "california": "us-ca",
    "new york": "us-ny",
    "texas": "us-tx",
    "florida": "us-fl",
    "massachusetts": "us-ma",
    # "washington" is Washington *State* only. The LLM occasionally emits
    # "Washington" for Washington, D.C. (a distinct jurisdiction); those are
    # mapped explicitly below so they don't silently collapse into us-wa.
    "washington": "us-wa",
    "washington dc": "us-dc",
    "washington, dc": "us-dc",
    "district of columbia": "us-dc",
    "illinois": "us-il",
}

_AUTHORITY_TYPE_MAP: dict[str, str] = {
    "statute": C.AUTHORITY_TYPE_STATUTE,
    "regulation": C.AUTHORITY_TYPE_REGULATION,
    "case_law": C.AUTHORITY_TYPE_CASE,
    "case law": C.AUTHORITY_TYPE_CASE,
    "case": C.AUTHORITY_TYPE_CASE,
    "constitution": C.AUTHORITY_TYPE_CONSTITUTION,
    "ordinance": C.AUTHORITY_TYPE_MUNICIPAL,
    "municipal": C.AUTHORITY_TYPE_MUNICIPAL,
    "administrative": C.AUTHORITY_TYPE_ADMIN_RULE,
    "admin": C.AUTHORITY_TYPE_ADMIN_RULE,
    "rule": C.AUTHORITY_TYPE_ADMIN_RULE,
    "guidance": C.AUTHORITY_TYPE_GUIDANCE,
    "treaty": C.AUTHORITY_TYPE_TREATY,
}


def _normalize_jurisdiction(s: str) -> str | None:
    """Map a free-text jurisdiction string to a canonical jurisdiction code."""
    key = s.strip().lower()
    if not key:
        return None
    result = _JURISDICTION_MAP.get(key)
    if result is None:
        # The map intentionally covers only a subset of US states (Phase 2);
        # unknown jurisdictions fall through to None. Log so the miss is visible
        # when validating against real documents.
        logger.debug("Unknown jurisdiction %r — no canonical code", s)
    return result


def _normalize_authority_type(s: str) -> str | None:
    """Map a free-text authority type to a controlled-vocabulary constant."""
    key = s.strip().lower()
    if not key:
        return None
    return _AUTHORITY_TYPE_MAP.get(key)


def _slugify(text: str) -> str:
    """Convert text to a kebab-case slug, max 80 chars."""
    slug = re.sub(r"[^a-z0-9]+", "-", text.strip().lower()).strip("-")
    return slug[:80]


def _derive_canonical_key(normalized_citation: str, raw_text: str) -> str | None:
    """Derive a stable canonical key from LLM-provided citation strings.

    Priority:
    1. ``normalized_citation`` already contains a ``prefix:locator`` pair → use as-is.
    2. ``normalized_citation`` is non-empty but not keyed → ``act:<slug>``.
    3. ``raw_text`` is non-empty → ``act:<slug>``.
    4. Nothing usable → ``None``.
    """
    nc = normalized_citation.strip()
    rt = raw_text.strip()

    if nc and ":" in nc:
        # Already in canonical key form ("dgcl:145"); canonicalise the locator
        # separator so e.g. "eu:2017/1129" and "eu:2017-1129" — the same EU
        # regulation cited two ways — collapse to one key.
        return _normalize_locator_sep(nc)

    source = nc or rt
    if not source:
        return None

    slug = _slugify(source)
    if not slug:
        return None
    return f"act:{slug}"


def _normalize_locator_sep(key: str) -> str:
    """Canonicalise the locator's separators so trivially-different LLM keys for
    the SAME authority collapse.

    Only the locator (the part after the first ``:``) is touched, and only ``/``
    is rewritten to ``-`` — our canonical keys carry subsection structure with
    ``.`` / ``(`` / ``)`` (e.g. ``usc-15:78j(b)``, ``cfr-17:240.10b``), none of
    which use ``/``, so this is a no-op for them and a fold only for free-form
    LLM keys like ``eu:2017/1129``.

    POST-UPGRADE NOTE: ``CorpusReference`` upserts on (corpus, canonical_key,
    source_document_in_corpus, reference_type). Any *finalized* rows persisted by
    a prior release under the un-normalized form (``eu:2017/1129``) will NOT be
    matched by re-enrichment under the normalized form (``eu:2017-1129``), so a
    second row is created and the old one lingers (the provisional/claim
    mechanism never downgrades finalized rows). If a deployment ran the LLM tier
    before this normalization shipped, normalize existing ``/``-bearing
    ``canonical_key`` locators in a one-time data migration / cleanup pass.
    """
    prefix, sep, locator = key.partition(":")
    if not sep:
        return key
    return f"{prefix}:{locator.replace('/', '-')}"


def _is_concept_key(canonical_key: str | None) -> bool:
    """True when the key is a generic ``act:*`` *concept* rather than a precise
    citation — i.e. the catch-all ``act:`` prefix with NO section locator (no
    digit anywhere in the slug).

    A real citation carries a number (``act:asc-606``, ``irc:163``); a bare body
    of law or loose phrase does not (``act:gaap``, ``act:applicable-law``,
    ``act:dgcl``, ``act:certificate-of-incorporation``). Those are flagged
    ``needs_review`` so they surface for triage but never auto-promote into the
    persisted reference web / crawl frontier. Direction: keep, don't drop.
    """
    if not canonical_key:
        return False
    prefix, sep, locator = canonical_key.partition(":")
    if not sep or prefix != "act":
        return False
    return not any(ch.isdigit() for ch in locator)


def verify_and_place(
    full_text: str,
    chunk_start: int,
    chunk_text: str,
    cand: CitationCandidate,
) -> dict | None:
    """Verify a citation candidate and compute its absolute character offsets.

    Returns a placement dict (or ``None`` if the citation is a hallucination).

    Algorithm:
    1. Compute absolute offsets using the chunk-relative offsets the LLM gave.
    2. If the slice at those offsets exactly matches ``raw_text`` → accept.
    3. Else search for ``raw_text`` in ``chunk_text`` (drift recovery).
    4. If still not found (or ``raw_text`` is empty) → ``None`` (hallucination).
    """
    if not cand.raw_text:
        return None

    abs_start = chunk_start + cand.start
    abs_end = chunk_start + cand.end

    # Fast path: LLM offsets are exact.
    if (
        0 <= abs_start < abs_end <= len(full_text)
        and full_text[abs_start:abs_end] == cand.raw_text
    ):
        return {
            "raw_text": cand.raw_text,
            "start": abs_start,
            "end": abs_end,
            "jurisdiction": cand.jurisdiction,
            "authority_type": cand.authority_type,
            "normalized_citation": cand.normalized_citation,
            "confidence": cand.confidence,
        }

    # Recovery: the LLM's offsets drifted. Anchor on raw_text, choosing the
    # occurrence NEAREST the claimed offset (a repeated citation must not be
    # mis-anchored to an unrelated duplicate).
    if not cand.raw_text.strip():
        return None
    occurrences = []
    idx = chunk_text.find(cand.raw_text)
    while idx != -1:
        occurrences.append(idx)
        idx = chunk_text.find(cand.raw_text, idx + 1)
    if not occurrences:
        logger.debug("LLM hallucination rejected: %r not in chunk", cand.raw_text)
        return None
    local = min(occurrences, key=lambda o: abs(o - cand.start))
    placed_start = chunk_start + local
    placed_end = placed_start + len(cand.raw_text)
    return {
        "raw_text": cand.raw_text,
        "start": placed_start,
        "end": placed_end,
        "jurisdiction": cand.jurisdiction,
        "authority_type": cand.authority_type,
        "normalized_citation": cand.normalized_citation,
        "confidence": cand.confidence,
    }


# ---------------------------------------------------------------------------
# LLM instructions
# ---------------------------------------------------------------------------

_INSTRUCTIONS = """\
You are a legal citation extraction engine. Your job is to identify every
explicit citation to a law, statute, regulation, case, constitution, treaty,
administrative rule, or municipal ordinance within the supplied text.

For each citation found:
- raw_text: copy the citation VERBATIM from the text — do not paraphrase.
- start/end: character offsets within this chunk (0-indexed, end is exclusive).
- jurisdiction: the governing jurisdiction (e.g. "Delaware", "Federal",
  "California"). Use "Federal" for US federal law.
- authority_type: one of "statute", "regulation", "case_law", "constitution",
  "ordinance", "administrative", "guidance", "treaty".
- normalized_citation: canonical form if recognisable (e.g. "dgcl:145" for
  DGCL Section 145, "securities-act:5" for Securities Act Section 5); leave ""
  if unsure.
- confidence: 0.0-1.0 self-rated confidence that this is a real citation.

Return ONLY citations you are confident about. Do NOT invent text that is not
in the provided excerpt.
"""


# ---------------------------------------------------------------------------
# Async primitive
# ---------------------------------------------------------------------------


async def _one_shot_structured(
    *,
    chunk_text: str,
    model: Any,
) -> ChunkCitationExtraction:
    """Run one structured extraction call against a single chunk.

    Temperature is forced to 0 for all providers so that an identical citation
    in the same chunk position yields a stable canonical key across overlapping
    chunks. TestModel ignores model_settings, so this has no effect on tests.
    """
    from opencontractserver.llms.agents.pydantic_ai_factory import (
        make_pydantic_ai_agent,
    )

    # Route through the project's sanctioned construction chokepoint (forbids the
    # system_prompt foot-gun, installs history compaction). Deterministic output
    # is required so an identical citation yields a stable canonical key even
    # when it falls in the overlap region of two adjacent chunks.
    agent = make_pydantic_ai_agent(
        model,
        instructions=_INSTRUCTIONS,
        output_type=ChunkCitationExtraction,
        output_retries=C.LLM_STRUCTURED_RETRIES,
        model_settings={"temperature": 0},
    )
    result = await agent.run(chunk_text)
    # output_type is passed through **kwargs, so the static type is Any/str;
    # the runtime value is a validated ChunkCitationExtraction.
    return cast(ChunkCitationExtraction, result.output)


# ---------------------------------------------------------------------------
# Main extractor class
# ---------------------------------------------------------------------------


class LLMCitationExtractor:
    """Slide a window over document text, extract citations via LLM.

    Args:
        model: pydantic-ai model spec string (e.g. ``"openai:gpt-4o"``).
               Defaults to the project-configured default via
               :func:`~opencontractserver.llms.llm_registry.resolve_model_spec`.
        window: sliding window size in characters.
        overlap: overlap between adjacent windows in characters.
    """

    def __init__(
        self,
        *,
        model: str | None = None,
        window: int = C.LLM_CHUNK_WINDOW,
        overlap: int = C.LLM_CHUNK_OVERLAP,
        max_concurrency: int | None = None,
    ) -> None:
        # Guard the chunking parameters up front: a non-positive window makes
        # ``step`` zero (window - overlap <= 0 falls back to window) and the
        # ``while pos < len(text)`` loop in aextract() would never advance.
        if window <= 0:
            raise ValueError(f"window must be positive, got {window!r}")
        if overlap < 0:
            raise ValueError(f"overlap must be non-negative, got {overlap!r}")
        self._model_spec = model
        self._window = window
        self._overlap = overlap
        # None => the settings-overridable global cap (C.llm_max_concurrency()).
        self._max_concurrency = max(
            1,
            max_concurrency if max_concurrency is not None else C.llm_max_concurrency(),
        )

    async def _abuild_model(self) -> Any:
        """Resolve the configured model spec and build the agent model.

        The single model-build seam: ``aextract`` uses it when no model is
        passed, and the multi-document orchestrator
        (``EnrichmentService._aresolve_documents``) calls it once to build a
        shared model. Centralising it here means tests that patch
        ``abuild_agent_model`` in this module cover BOTH call paths (the
        orchestrator no longer builds via a separate import, which silently
        bypassed the patch and issued real provider calls).

        ``settings_default`` is threaded in from
        :func:`~opencontractserver.pipeline.utils.get_default_llm_spec` so a
        live retarget of the install-wide ``PipelineSettings.default_llm``
        (System Settings UI) takes effect here without a worker restart.
        Leaving it ``None`` silently skipped that tier and pinned enrichment
        to the deploy-time ``DEFAULT_LLM`` / ``OPENAI_MODEL`` env values
        (issue #2078).
        """
        from opencontractserver.llms.llm_registry import resolve_model_spec
        from opencontractserver.pipeline.utils import get_default_llm_spec

        spec = resolve_model_spec(
            explicit=self._model_spec,
            agent_preferred=None,
            corpus_preferred=None,
            # ORM access (reads the PipelineSettings singleton), so it is
            # threaded through sync_to_async; resolve_model_spec stays ORM-free.
            settings_default=await sync_to_async(get_default_llm_spec)(),
        )
        return await abuild_agent_model(spec)

    async def aextract(
        self,
        text: str,
        *,
        model: Any = None,
        semaphore: asyncio.Semaphore | None = None,
    ) -> list[Candidate]:
        """Extract law citation candidates from ``text`` using the LLM.

        Returns an empty list immediately for blank/whitespace-only input
        without building an LLM model.

        ``model`` and ``semaphore`` let a multi-document orchestrator share one
        built model and one GLOBAL chunk-concurrency semaphore across every
        document, so the total in-flight provider load stays bounded even while
        many documents extract at once (cross-document concurrency). When
        omitted (the single-document callers), each call builds its own model
        and a private semaphore — identical to the prior behaviour.
        """
        if not text or not text.strip():
            return []

        if model is None:
            model = await self._abuild_model()

        step = self._window - self._overlap
        if step <= 0:
            step = self._window

        # Enumerate the sliding-window chunks up front so they can run
        # concurrently — each (chunk_start, chunk_text) extraction is fully
        # independent.
        chunks: list[tuple[int, str]] = []
        pos = 0
        while pos < len(text):
            chunks.append((pos, text[pos : pos + self._window]))
            pos += step

        # Run the per-chunk structured calls CONCURRENTLY, bounded by a semaphore
        # so we never exceed the provider's rate limits or cost-spike. This
        # replaces the old strictly-sequential ``await`` loop — the single
        # biggest cost of the LLM tier (e.g. ~2,900 serial calls on a large
        # corpus). A failed chunk yields ``None`` and is skipped, exactly as the
        # old per-chunk try/except did. A shared ``semaphore`` (passed by the
        # multi-document orchestrator) caps load ACROSS documents; otherwise a
        # private one caps this document alone.
        sem = (
            semaphore
            if semaphore is not None
            else asyncio.Semaphore(self._max_concurrency)
        )

        async def _run(
            chunk_start: int, chunk_text: str
        ) -> tuple[int, str, ChunkCitationExtraction | None]:
            async with sem:
                try:
                    extraction = await _one_shot_structured(
                        chunk_text=chunk_text,
                        model=model,
                    )
                except Exception:
                    logger.exception(
                        "LLM citation extraction failed for chunk at offset %d",
                        chunk_start,
                    )
                    return chunk_start, chunk_text, None
                return chunk_start, chunk_text, extraction

        # ``gather`` preserves input order, so processing below stays in
        # ascending-offset order — the dedup ("first chunk wins") is therefore
        # deterministic, identical to the old sequential loop.
        results = await asyncio.gather(*(_run(cs, ct) for cs, ct in chunks))

        # Dedup on (start, end) only. An identical span IS the same citation;
        # LLM nondeterminism must not let two different derived keys for the
        # same span both survive into the output. First chunk wins.
        seen: set[tuple[int, int]] = set()
        candidates: list[Candidate] = []

        for chunk_start, chunk_text, extraction in results:
            if extraction is None:
                continue
            for llm_cand in extraction.citations:
                placement = verify_and_place(text, chunk_start, chunk_text, llm_cand)
                if placement is None:
                    continue

                jur = _normalize_jurisdiction(placement["jurisdiction"])
                atype = _normalize_authority_type(placement["authority_type"])
                canonical_key = _derive_canonical_key(
                    placement["normalized_citation"],
                    placement["raw_text"],
                )
                dedup_key = (placement["start"], placement["end"])
                if dedup_key in seen:
                    continue
                seen.add(dedup_key)

                conf = placement["confidence"]
                # Low confidence OR a generic act:* concept (no section locator)
                # → review bucket: surfaced for triage, not auto-promoted into the
                # persisted reference web / crawl frontier.
                needs_review = conf < C.LLM_CONFIDENCE_FLOOR or _is_concept_key(
                    canonical_key
                )

                # Extract the authority prefix (part before ':') when available.
                authority: str | None = None
                nc = placement["normalized_citation"].strip()
                if nc and ":" in nc:
                    authority = nc.split(":", 1)[0]

                candidates.append(
                    Candidate(
                        reference_type=C.REF_LAW,
                        start=placement["start"],
                        end=placement["end"],
                        raw_text=placement["raw_text"],
                        canonical_key=canonical_key,
                        jurisdiction=jur,
                        authority_type=atype,
                        detection_tier=C.DETECTION_TIER_LLM,
                        detection_confidence=conf,
                        normalized_data={
                            "authority": authority,
                            "tier": C.DETECTION_TIER_LLM,
                            "llm_jurisdiction": placement["jurisdiction"],
                            "llm_authority_type": placement["authority_type"],
                            "normalized_citation": placement["normalized_citation"],
                            "needs_review": needs_review,
                        },
                    )
                )

        return candidates
