"""Agent tools for corpus reference enrichment.

Two-phase, CAML-style: ``scan`` (read-only inventory) then
``apply`` (approval-gated write). ``corpus_id`` and ``creator_id`` are injected
from the agent context and hidden from the LLM.
"""

from __future__ import annotations

from opencontractserver.enrichment import constants as C

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


def list_wanted_authorities(
    *,
    corpus_id: int,
    creator_id: int,
) -> dict:
    """List the authorities this corpus still cites EXTERNALLY (read-only).

    The missing-authority backlog: law citations with no resolvable target,
    aggregated by authority and ranked by mention volume — what to bootstrap
    next to light up the most references. Subsection citations roll up to
    their section root (the unit a bootstrap materialises).
    """
    from django.contrib.auth import get_user_model

    from opencontractserver.enrichment.services import CorpusReferenceService

    user = get_user_model().objects.get(pk=creator_id)
    return {
        "corpus_id": corpus_id,
        "authorities": CorpusReferenceService.wanted_authorities(
            user, corpus_id=corpus_id
        ),
    }


def discover_authorities(
    *,
    corpus_id: int,
    creator_id: int,
    max_documents: int | None = None,
    use_llm: bool = False,
) -> dict:
    """Open-vocabulary authority inventory (read-only).

    Runs registry + generic citation-shape grammars over the corpus and reports
    every detected legal authority — including ones outside the built-in
    registry (US Code, CFR, Federal Register, state/municipal codes, named
    Acts) — grouped by jurisdiction and authority type. ``new_namespaces`` lists
    prefixes with no registry entry yet: the candidates worth bootstrapping or
    locating. Writes nothing.

    Cost scales with corpus size (every document's full text is scanned). On a
    large corpus pass ``max_documents`` to cap the scan; the result then reports
    ``documents_total`` and ``documents_truncated`` so the cap is explicit.

    Set ``use_llm=True`` to run an additional LLM detection pass for
    prose/obscure citations (slower, costs tokens). Defaults to ``False``.
    When enabled, raw document text chunks are transmitted to the configured
    external LLM provider; do not use on confidential documents without
    appropriate consent.
    """
    from opencontractserver.enrichment.services import EnrichmentService

    return EnrichmentService().discover(
        corpus_id=corpus_id,
        creator_id=creator_id,
        max_documents=max_documents,
        use_llm=use_llm,
    )


def bootstrap_authority_corpus(
    *,
    creator_id: int,
    corpus_title: str,
    sections: list[dict],
    aliases: list[str] | None = None,
    make_public: bool = False,
    relink_async: bool = False,
) -> dict:
    """Create or refresh an authority corpus, then re-link citing corpora.

    Each section dict needs ``key`` (canonical key, e.g. "dgcl:145"),
    ``heading`` (document title) and ``text`` (full section text);
    ``source_url`` is optional. Idempotent: unchanged sections are skipped,
    changed text version-ups the existing document. After the bootstrap,
    EXTERNAL law references across all corpora citing these keys are
    upgraded to RESOLVED links (each corpus under its own creator's
    visibility).
    """
    from opencontractserver.enrichment.authorities import (
        AuthoritySection,
    )
    from opencontractserver.enrichment.authorities import (
        bootstrap_authority_corpus as _bootstrap,
    )

    if not sections:
        raise ValueError("sections must be a non-empty list")
    parsed: list[AuthoritySection] = []
    for i, sec in enumerate(sections):
        if not isinstance(sec, dict) or not all(
            isinstance(sec.get(f), str) and sec.get(f, "").strip()
            for f in ("key", "heading", "text")
        ):
            raise ValueError(
                f"sections[{i}] must be a dict with non-empty 'key', "
                "'heading' and 'text' (optional 'source_url')"
            )
        parsed.append(
            AuthoritySection(
                key=sec["key"].strip(),
                heading=sec["heading"].strip(),
                text=sec["text"],
                source_url=sec.get("source_url"),
            )
        )

    return _bootstrap(
        creator_id=creator_id,
        corpus_title=corpus_title,
        sections=parsed,
        aliases=aliases,
        make_public=make_public,
        relink_async=relink_async,
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


async def alist_wanted_authorities(
    *,
    corpus_id: int,
    creator_id: int,
) -> dict:
    return await _db_sync_to_async(list_wanted_authorities)(
        corpus_id=corpus_id, creator_id=creator_id
    )


async def abootstrap_authority_corpus(
    *,
    creator_id: int,
    corpus_title: str,
    sections: list[dict],
    aliases: list[str] | None = None,
    make_public: bool = False,
) -> dict:
    # relink_async=True: offload the post-bootstrap relink sweep to Celery so a
    # large authority set doesn't hold this tool's single thread-pool slot for
    # minutes. Not exposed as a tool parameter — the LLM never sets it.
    return await _db_sync_to_async(bootstrap_authority_corpus)(
        creator_id=creator_id,
        corpus_title=corpus_title,
        sections=sections,
        aliases=aliases,
        make_public=make_public,
        relink_async=True,
    )


async def adiscover_authorities(
    *,
    corpus_id: int,
    creator_id: int,
    max_documents: int | None = None,
    use_llm: bool = False,
) -> dict:
    return await _db_sync_to_async(discover_authorities)(
        corpus_id=corpus_id,
        creator_id=creator_id,
        max_documents=max_documents,
        use_llm=use_llm,
    )


def crawl_authorities(
    *,
    creator_id: int,
    corpus_id: int | None = None,
    max_depth: int = C.CRAWL_DEFAULT_MAX_DEPTH,
    min_demand: int = C.CRAWL_DEFAULT_MIN_DEMAND,
    max_authorities: int = C.CRAWL_DEFAULT_MAX_AUTHORITIES,
    per_jurisdiction_cap: int | None = None,
    token_budget: int | None = None,
) -> dict:
    """Bounded recursive crawl: discover & ingest the authorities a corpus
    cites, then the authorities THOSE cite, up to ``max_depth`` hops. Returns a
    summary with per-state counts, per-jurisdiction tallies, the stop reason,
    and the full frontier residual census. Idempotent: already-ingested
    authorities are skipped, re-crawling creates zero duplicate documents.
    """
    from opencontractserver.enrichment.services.crawl_authorities_service import (
        CrawlAuthoritiesService,
    )

    return CrawlAuthoritiesService.crawl(
        creator_id=creator_id,
        corpus_id=corpus_id,
        max_depth=max_depth,
        min_demand=min_demand,
        max_authorities=max_authorities,
        per_jurisdiction_cap=(
            per_jurisdiction_cap
            if per_jurisdiction_cap is not None
            else C.CRAWL_DEFAULT_PER_JURISDICTION_CAP
        ),
        token_budget=(
            token_budget if token_budget is not None else C.CRAWL_DEFAULT_TOKEN_BUDGET
        ),
    )


async def acrawl_authorities(
    *,
    creator_id: int,
    corpus_id: int | None = None,
    max_depth: int = C.CRAWL_DEFAULT_MAX_DEPTH,
    min_demand: int = C.CRAWL_DEFAULT_MIN_DEMAND,
    max_authorities: int = C.CRAWL_DEFAULT_MAX_AUTHORITIES,
    per_jurisdiction_cap: int | None = None,
    token_budget: int | None = None,
) -> dict:
    return await _db_sync_to_async(crawl_authorities)(
        creator_id=creator_id,
        corpus_id=corpus_id,
        max_depth=max_depth,
        min_demand=min_demand,
        max_authorities=max_authorities,
        per_jurisdiction_cap=per_jurisdiction_cap,
        token_budget=token_budget,
    )
