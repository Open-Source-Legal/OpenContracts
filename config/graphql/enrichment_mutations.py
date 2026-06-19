"""GraphQL mutations for corpus enrichment and authority-crawl dispatch.

Allows callers to trigger the reference-enrichment analyzer and/or the
bounded-authority-crawl analyzer on a corpus they can UPDATE. Lifecycle
and permission logic lives in
:class:`opencontractserver.analyzer.services.AnalysisLifecycleService`;
the mutation decodes global IDs, translates the ``RunEnrichmentOptionsInput``
into service-layer dicts, and forwards to the service.
"""

import logging
from typing import Any

import graphene
from graphql_jwt.decorators import login_required
from graphql_relay import from_global_id

from config.graphql.graphene_types import AnalysisType
from opencontractserver.analyzer.services.analysis_lifecycle_service import (
    AnalysisLifecycleService,
)
from opencontractserver.enrichment import constants as C
from opencontractserver.enrichment.services import EnrichmentService
from opencontractserver.enrichment.services.crawl_authorities_service import (
    CrawlAuthoritiesService,
)

logger = logging.getLogger(__name__)


class RunEnrichmentOptionsInput(graphene.InputObjectType):
    """Optional tuning knobs forwarded to the enrichment / crawl analyzers."""

    reference_types = graphene.List(
        graphene.String,
        description="Restrict enrichment to these reference-type codes (e.g. 'LAW').",
    )
    use_llm_tier = graphene.Boolean(
        default_value=False,
        description="Enable the LLM detection tier for the enrichment analyzer.",
    )
    # Crawl bounds — forwarded verbatim to the crawl analyzer input schema.
    max_depth = graphene.Int(description="Maximum authority-to-authority BFS depth.")
    min_demand = graphene.Int(
        description="Skip frontier rows with mention_count below this floor."
    )
    max_authorities = graphene.Int(
        description="Hard cap on authority-bootstrap calls per run."
    )
    per_jurisdiction_cap = graphene.Int(
        description="Maximum ingests per jurisdiction code per run."
    )
    token_budget = graphene.Int(
        description="Approximate token budget for the crawl run."
    )


class RunCorpusEnrichmentMutation(graphene.Mutation):
    """Dispatch the enrichment and/or crawl analyzer on a corpus.

    The caller must hold UPDATE on the corpus — both analyzers write
    references and/or publish authority documents into it.  At least one of
    ``run_enrichment`` / ``run_crawl`` must be True.  On success every
    dispatched :class:`~opencontractserver.analyzer.models.Analysis` row is
    returned; the rows are created synchronously even though the underlying
    Celery tasks are queued on transaction commit.
    """

    class Arguments:
        corpus_id = graphene.ID(
            required=True, description="Global ID of the corpus to run on."
        )
        run_enrichment = graphene.Boolean(
            default_value=True,
            description="Dispatch the reference-enrichment analyzer.",
        )
        run_crawl = graphene.Boolean(
            default_value=False,
            description="Dispatch the bounded authority-crawl analyzer.",
        )
        options = RunEnrichmentOptionsInput(
            required=False,
            description="Optional tuning knobs for the dispatched analyzers.",
        )

    ok = graphene.Boolean()
    message = graphene.String()
    analyses = graphene.List(AnalysisType)

    @login_required
    def mutate(
        root,
        info,
        corpus_id,
        run_enrichment=True,
        run_crawl=False,
        options=None,
    ):
        user = info.context.user

        try:
            corpus_pk = from_global_id(corpus_id)[1]
            if not corpus_pk:
                raise ValueError("empty pk")
        except Exception:
            return RunCorpusEnrichmentMutation(
                ok=False,
                message="Resource not found or you do not have permission.",
                analyses=[],
            )

        if not run_enrichment and not run_crawl:
            return RunCorpusEnrichmentMutation(
                ok=False,
                message="Select at least one job (runEnrichment or runCrawl).",
                analyses=[],
            )

        created = []

        if run_enrichment:
            analyzer = EnrichmentService.get_or_create_analyzer(user.id)
            input_data: dict[str, Any] = {
                "use_llm": bool(getattr(options, "use_llm_tier", False) or False),
            }
            ref_types = getattr(options, "reference_types", None)
            if ref_types:
                valid_types = [t for t in ref_types if t in C.ALL_REFERENCE_TYPES]
                if valid_types:
                    input_data["types"] = valid_types

            logger.info(
                "RunCorpusEnrichmentMutation: dispatching enrichment analyzer "
                "analyzer_pk=%s corpus_pk=%s user=%s",
                analyzer.pk,
                corpus_pk,
                user.id,
            )
            res = AnalysisLifecycleService.start_document_analysis(
                user,
                analyzer_pk=analyzer.pk,
                corpus_pk=corpus_pk,
                analysis_input_data=input_data,
                request=info.context,
                require_corpus_update=True,
            )
            if not res.ok:
                return RunCorpusEnrichmentMutation(
                    ok=False,
                    message=res.error,
                    analyses=[],
                )
            created.append(res.value)

        if run_crawl:
            analyzer = CrawlAuthoritiesService.get_or_create_analyzer(user.id)
            bounds = {}
            for field in (
                "max_depth",
                "min_demand",
                "max_authorities",
                "per_jurisdiction_cap",
                "token_budget",
            ):
                val = getattr(options, field, None) if options is not None else None
                if val is not None:
                    bounds[field] = val

            logger.info(
                "RunCorpusEnrichmentMutation: dispatching crawl analyzer "
                "analyzer_pk=%s corpus_pk=%s user=%s bounds=%s",
                analyzer.pk,
                corpus_pk,
                user.id,
                bounds,
            )
            res = AnalysisLifecycleService.start_document_analysis(
                user,
                analyzer_pk=analyzer.pk,
                corpus_pk=corpus_pk,
                analysis_input_data=bounds or None,
                request=info.context,
                require_corpus_update=True,
            )
            if not res.ok:
                return RunCorpusEnrichmentMutation(
                    ok=False,
                    message=res.error,
                    analyses=created,
                )
            created.append(res.value)

        return RunCorpusEnrichmentMutation(
            ok=True,
            message="SUCCESS",
            analyses=created,
        )


class RunAuthorityDiscoveryMutation(graphene.Mutation):
    """Run authority discovery on a hand-picked set of ``AuthorityFrontier`` rows.

    The corpus-agnostic counterpart to :class:`RunCorpusEnrichmentMutation`'s
    crawl: instead of seeding + dequeuing the whole frontier under a corpus
    ``Analysis``, this ingests *exactly* the selected rows (depth 0, no
    recursion), so the global Authority Sources monitor can drain a chosen
    subset of the queue.

    **Superuser-only.** The ``AuthorityFrontier`` is a global, system-managed
    queue with no per-object permissions — mirroring the ``authorityFrontier``
    query gate, there is no corpus to check ``UPDATE`` against. The work is
    enqueued fire-and-forget; the monitor reflects each row's ``discovery_state``
    as it transitions.
    """

    class Arguments:
        frontier_ids = graphene.List(
            graphene.NonNull(graphene.ID),
            required=True,
            description="Global IDs of the AuthorityFrontier rows to run discovery on.",
        )

    ok = graphene.Boolean()
    message = graphene.String()
    count = graphene.Int()

    @login_required
    def mutate(root, info, frontier_ids):
        user = info.context.user
        if not getattr(user, "is_superuser", False):
            # Same opaque message whether the rows exist or the user lacks
            # access — the frontier is superuser-only, no existence oracle.
            return RunAuthorityDiscoveryMutation(
                ok=False,
                message="Resource not found or you do not have permission.",
                count=0,
            )

        pks: list[int] = []
        for gid in frontier_ids:
            try:
                pks.append(int(from_global_id(gid)[1]))
            except (ValueError, TypeError, IndexError):
                continue
        pks = list(dict.fromkeys(pks))  # de-dupe, preserve order

        if not pks:
            return RunAuthorityDiscoveryMutation(
                ok=False,
                message="No valid authority rows selected.",
                count=0,
            )

        from opencontractserver.tasks.corpus_tasks import (
            discover_selected_authorities,
        )

        logger.info(
            "RunAuthorityDiscoveryMutation: dispatching discovery for %s rows user=%s",
            len(pks),
            user.id,
        )
        discover_selected_authorities.delay(frontier_ids=pks, creator_id=user.id)

        plural = "y" if len(pks) == 1 else "ies"
        return RunAuthorityDiscoveryMutation(
            ok=True,
            message=f"Discovery started for {len(pks)} authorit{plural}.",
            count=len(pks),
        )
