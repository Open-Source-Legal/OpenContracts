"""Corpus-scoped analyzer tasks (@corpus_analyzer_task).

These run ONCE per Analysis with the whole corpus in scope, own their writes,
and are surfaced through the analyzer framework (auto-synced Analyzer rows,
run_task_name_analyzer dispatch, CorpusAction triggers).
"""

import logging

from opencontractserver.enrichment import constants as C
from opencontractserver.shared.decorators import corpus_analyzer_task

logger = logging.getLogger(__name__)


@corpus_analyzer_task(
    input_schema={
        "type": "object",
        "properties": {
            "types": {
                "type": "array",
                "items": {
                    "type": "string",
                    "enum": ["LAW", "DOCUMENT", "SECTION", "DEFINED_TERM"],
                },
                "description": (
                    "Reference types to enrich. Defaults to LAW, DOCUMENT and "
                    "SECTION; DEFINED_TERM is opt-in (precision/volume)."
                ),
            },
            "use_llm": {
                "type": "boolean",
                "default": False,
                "description": (
                    "Enable Tier-2b LLM citation extraction (opt-in; cost implications)."
                ),
            },
        },
    }
)
def corpus_reference_enrichment(
    *args,
    corpus_id: int,
    analysis_id: int,
    types: list[str] | None = None,
    use_llm: bool = False,
    **kwargs,
) -> dict:
    """Crawl the corpus and persist its reference web.

    Detects explicit references (law citations, document/exhibit references,
    internal section references; defined terms opt-in), annotates every
    mention, links section references via relationships, rolls resolved
    document references up to document-graph edges, records law citations as
    canonical-key cross-references, and resolves them against visible
    authority corpora. Idempotent: re-running enriches only newly-found
    references.

    ``use_llm`` opts into the cost-gated Tier-2b LLM extraction pass in
    addition to the default grammar tier.
    """
    from opencontractserver.analyzer.models import Analysis
    from opencontractserver.enrichment.services import EnrichmentService

    analysis = Analysis.objects.get(id=analysis_id)
    if analysis.creator_id is None:
        raise ValueError(
            f"Analysis {analysis_id} has no creator; cannot run enrichment"
        )
    extra_tiers = [C.DETECTION_TIER_GRAMMAR] + (
        [C.DETECTION_TIER_LLM] if use_llm else []
    )
    return EnrichmentService().apply(
        corpus_id=corpus_id,
        creator_id=analysis.creator_id,
        types=types,
        analysis=analysis,
        extra_tiers=extra_tiers,
    )


@corpus_analyzer_task(
    input_schema={
        "type": "object",
        "properties": {
            "max_depth": {
                "type": "integer",
                "minimum": 0,
                "maximum": 5,
                "default": C.CRAWL_DEFAULT_MAX_DEPTH,
            },
            "min_demand": {
                "type": "integer",
                "minimum": 0,
                "default": C.CRAWL_DEFAULT_MIN_DEMAND,
            },
            "max_authorities": {
                "type": "integer",
                "minimum": 1,
                "default": C.CRAWL_DEFAULT_MAX_AUTHORITIES,
            },
            "per_jurisdiction_cap": {
                "type": "integer",
                "minimum": 1,
                "default": C.CRAWL_DEFAULT_PER_JURISDICTION_CAP,
            },
            "token_budget": {
                "type": "integer",
                "minimum": 0,
                "default": C.CRAWL_DEFAULT_TOKEN_BUDGET,
            },
            "make_public": {"type": "boolean", "default": True},
        },
        "additionalProperties": False,
    }
)
def crawl_authorities(
    *args,
    corpus_id: int,
    analysis_id: int,
    max_depth: int | None = None,
    min_demand: int | None = None,
    max_authorities: int | None = None,
    per_jurisdiction_cap: int | None = None,
    token_budget: int | None = None,
    make_public: bool = True,
    **kwargs,
) -> dict:
    """Bounded recursive authority crawl.

    The ``@corpus_analyzer_task`` decorator owns the Analysis lifecycle
    (RUNNING → COMPLETED/FAILED, result_message/error_message).  This body
    returns the summary dict from ``CrawlAuthoritiesService.crawl``.

    Bound parameters fall back to the module constants when not supplied so
    every call site can override selectively.
    """
    from opencontractserver.analyzer.models import Analysis
    from opencontractserver.enrichment.services.crawl_authorities_service import (
        CrawlAuthoritiesService,
    )

    # Module-level `logging` is already imported at the top of the file; no need
    # to re-import. `logger` is a Logger instance, not the module, so there is
    # no name conflict here.
    task_log = logging.getLogger(
        "opencontractserver.tasks.corpus_analysis_tasks.crawl_authorities"
    ).info

    analysis = Analysis.objects.get(id=analysis_id)
    if analysis.creator_id is None:
        raise ValueError(
            f"Analysis {analysis_id} has no creator; cannot run authority crawl"
        )

    return CrawlAuthoritiesService.crawl(
        creator_id=analysis.creator_id,
        corpus_id=corpus_id,
        max_depth=max_depth if max_depth is not None else C.CRAWL_DEFAULT_MAX_DEPTH,
        min_demand=(
            min_demand if min_demand is not None else C.CRAWL_DEFAULT_MIN_DEMAND
        ),
        max_authorities=(
            max_authorities
            if max_authorities is not None
            else C.CRAWL_DEFAULT_MAX_AUTHORITIES
        ),
        per_jurisdiction_cap=(
            per_jurisdiction_cap
            if per_jurisdiction_cap is not None
            else C.CRAWL_DEFAULT_PER_JURISDICTION_CAP
        ),
        token_budget=(
            token_budget if token_budget is not None else C.CRAWL_DEFAULT_TOKEN_BUDGET
        ),
        make_public=make_public,
        log=task_log,
    )
