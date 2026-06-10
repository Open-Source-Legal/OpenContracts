"""Corpus-scoped analyzer tasks (@corpus_analyzer_task).

These run ONCE per Analysis with the whole corpus in scope, own their writes,
and are surfaced through the analyzer framework (auto-synced Analyzer rows,
run_task_name_analyzer dispatch, CorpusAction triggers).
"""

import logging

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
            }
        },
    }
)
def corpus_reference_enrichment(
    *args,
    corpus_id: int,
    analysis_id: int,
    types: list[str] | None = None,
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
    """
    from opencontractserver.analyzer.models import Analysis
    from opencontractserver.enrichment.services import EnrichmentService

    analysis = Analysis.objects.get(id=analysis_id)
    if analysis.creator_id is None:
        raise ValueError(
            f"Analysis {analysis_id} has no creator; cannot run enrichment"
        )
    return EnrichmentService().apply(
        corpus_id=corpus_id,
        creator_id=analysis.creator_id,
        types=types,
        analysis=analysis,
    )
