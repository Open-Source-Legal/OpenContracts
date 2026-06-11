"""Agent tools for corpus reference enrichment.

Two-phase, CAML-style: ``scan`` (read-only inventory) then
``apply`` (approval-gated write). ``corpus_id`` and ``creator_id`` are injected
from the agent context and hidden from the LLM.
"""

from __future__ import annotations

from ._helpers import _db_sync_to_async


def scan_corpus_references(
    *,
    corpus_id: int,
    creator_id: int,
    types: list[str] | None = None,
    sample_n: int = 10,
) -> dict:
    """Inventory explicit references in a corpus WITHOUT writing anything.

    Detects law citations (e.g. "Section 145 of the Delaware General Corporation
    Law"), document/exhibit references, and internal section references, then
    reports counts by type and sample resolved/unresolved candidates so the user
    can review before applying enrichment.
    """
    from opencontractserver.enrichment.services import EnrichmentService

    return EnrichmentService().scan(
        corpus_id=corpus_id, creator_id=creator_id, types=types, sample_n=sample_n
    )


def apply_corpus_reference_enrichment(
    *,
    corpus_id: int,
    creator_id: int,
    types: list[str] | None = None,
) -> dict:
    """Create reference annotations, relationships, and cross-references.

    Annotates every detected reference, links internal section references via
    relationships, resolves document/exhibit references to in-app links, and
    records law citations as cross-corpus-trackable stubs. Idempotent:
    re-running enriches only newly-found references.
    """
    from opencontractserver.enrichment.services import EnrichmentService

    return EnrichmentService().apply(
        corpus_id=corpus_id, creator_id=creator_id, types=types
    )


async def ascan_corpus_references(
    *,
    corpus_id: int,
    creator_id: int,
    types: list[str] | None = None,
    sample_n: int = 10,
) -> dict:
    return await _db_sync_to_async(scan_corpus_references)(
        corpus_id=corpus_id, creator_id=creator_id, types=types, sample_n=sample_n
    )


async def aapply_corpus_reference_enrichment(
    *,
    corpus_id: int,
    creator_id: int,
    types: list[str] | None = None,
) -> dict:
    return await _db_sync_to_async(apply_corpus_reference_enrichment)(
        corpus_id=corpus_id, creator_id=creator_id, types=types
    )
