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

import logging
import re
from typing import Any

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
    "washington": "us-wa",
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
    return _JURISDICTION_MAP.get(key)


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
        # Already in canonical key form ("dgcl:145")
        return nc

    source = nc or rt
    if not source:
        return None

    slug = _slugify(source)
    if not slug:
        return None
    return f"act:{slug}"


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
    from pydantic_ai import Agent

    # Deterministic output is required: the same citation must yield the same
    # key even when it falls in the overlap region of two adjacent chunks.
    model_settings = {"temperature": 0}

    agent: Agent[None, ChunkCitationExtraction] = Agent(
        model=model,
        output_type=ChunkCitationExtraction,
        instructions=_INSTRUCTIONS,
        retries=C.LLM_STRUCTURED_RETRIES,
        model_settings=model_settings,
    )
    result = await agent.run(chunk_text)
    return result.output


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
    ) -> None:
        self._model_spec = model
        self._window = window
        self._overlap = overlap

    async def aextract(self, text: str) -> list[Candidate]:
        """Extract law citation candidates from ``text`` using the LLM.

        Returns an empty list immediately for blank/whitespace-only input
        without building an LLM model.
        """
        if not text or not text.strip():
            return []

        # Resolve the model spec once.
        from opencontractserver.llms.llm_registry import resolve_model_spec

        spec = resolve_model_spec(
            explicit=self._model_spec,
            agent_preferred=None,
            corpus_preferred=None,
            settings_default=None,
        )
        model = await abuild_agent_model(spec)

        step = self._window - self._overlap
        if step <= 0:
            step = self._window

        # Dedup on (start, end) only. An identical span IS the same citation;
        # LLM nondeterminism must not let two different derived keys for the
        # same span both survive into the output. First chunk wins.
        seen: set[tuple[int, int]] = set()
        candidates: list[Candidate] = []

        pos = 0
        while pos < len(text):
            chunk_start = pos
            chunk_text = text[pos : pos + self._window]

            try:
                extraction = await _one_shot_structured(
                    chunk_text=chunk_text,
                    model=model,
                )
            except Exception:
                logger.exception(
                    "LLM citation extraction failed for chunk at offset %d", pos
                )
                pos += step
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
                needs_review = conf < C.LLM_CONFIDENCE_FLOOR

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

            pos += step

        return candidates
