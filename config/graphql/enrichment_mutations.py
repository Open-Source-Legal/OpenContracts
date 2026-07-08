"""Generated strawberry GraphQL module (graphene migration).

Shape-generated from the graphene schema; stub functions marked PORT(...)
carry the ported business logic. See config/graphql_new/manifest.json.
"""
from __future__ import annotations

import datetime
import decimal
import uuid
from typing import Annotated, Any, Optional

import strawberry

from config.graphql.core import permissions as core_permissions
from config.graphql.core.filtering import filterset_factory, setup_filterset
from config.graphql.core.mutations import drf_deletion, drf_mutation
from config.graphql.core.relay import (
    Node,
    get_node_from_global_id,
    make_connection_types,
    register_type,
    resolve_django_connection,
    resolve_django_list,
)
from config.graphql.core.scalars import BigInt, GenericScalar, JSONString
from config.graphql._util import coerce_enum, coerce_str, strip_unset
from config.graphql import enums




@strawberry.input(name="RunEnrichmentOptionsInput", description='Optional tuning knobs forwarded to the enrichment / crawl analyzers.')
class RunEnrichmentOptionsInput:
    reference_types: Optional[list[Optional[str]]] = strawberry.field(name="referenceTypes", description="Restrict enrichment to these reference-type codes (e.g. 'LAW').", default=strawberry.UNSET)
    use_llm_tier: Optional[bool] = strawberry.field(name="useLlmTier", description='Enable the LLM detection tier for the enrichment analyzer.', default=False)
    max_depth: Optional[int] = strawberry.field(name="maxDepth", description='Maximum authority-to-authority BFS depth.', default=strawberry.UNSET)
    min_demand: Optional[int] = strawberry.field(name="minDemand", description='Skip frontier rows with mention_count below this floor.', default=strawberry.UNSET)
    max_authorities: Optional[int] = strawberry.field(name="maxAuthorities", description='Hard cap on authority-bootstrap calls per run.', default=strawberry.UNSET)
    per_jurisdiction_cap: Optional[int] = strawberry.field(name="perJurisdictionCap", description='Maximum ingests per jurisdiction code per run.', default=strawberry.UNSET)
    token_budget: Optional[int] = strawberry.field(name="tokenBudget", description='Approximate token budget for the crawl run.', default=strawberry.UNSET)


@strawberry.type(name="RunCorpusEnrichmentMutation", description='Dispatch the enrichment and/or crawl analyzer on a corpus.\n\nThe caller must hold UPDATE on the corpus — both analyzers write\nreferences and/or publish authority documents into it.  At least one of\n``run_enrichment`` / ``run_crawl`` must be True.  On success every\ndispatched :class:`~opencontractserver.analyzer.models.Analysis` row is\nreturned; the rows are created synchronously even though the underlying\nCelery tasks are queued on transaction commit.')
class RunCorpusEnrichmentMutation:
    ok: Optional[bool] = strawberry.field(name="ok", default=None)
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))
    @strawberry.field(name="analyses")
    def analyses(self, info: strawberry.Info) -> Optional[list[Optional[Annotated["AnalysisType", strawberry.lazy("config.graphql.extract_types")]]]]:
        return resolve_django_list(self, info, getattr(self, "analyses"), "AnalysisType")
    partial: Optional[bool] = strawberry.field(name="partial", description='True when some requested jobs dispatched but others failed (e.g. enrichment started but the crawl could not be dispatched). Only meaningful when ``ok`` is True; lets callers surface the non-fatal ``message`` without coupling to its text.', default=None)


register_type("RunCorpusEnrichmentMutation", RunCorpusEnrichmentMutation, model=None)


@strawberry.type(name="RunAuthorityDiscoveryMutation", description="Run authority discovery on a hand-picked set of ``AuthorityFrontier`` rows.\n\nThe corpus-agnostic counterpart to :class:`RunCorpusEnrichmentMutation`'s\ncrawl: instead of seeding + dequeuing the whole frontier under a corpus\n``Analysis``, this ingests *exactly* the selected rows (depth 0, no\nrecursion), so the global Authority Sources monitor can drain a chosen\nsubset of the queue.\n\n**Superuser-only.** The ``AuthorityFrontier`` is a global, system-managed\nqueue with no per-object permissions — mirroring the ``authorityFrontier``\nquery gate, there is no corpus to check ``UPDATE`` against. The work is\nenqueued fire-and-forget; the monitor reflects each row's ``discovery_state``\nas it transitions.")
class RunAuthorityDiscoveryMutation:
    ok: Optional[bool] = strawberry.field(name="ok", default=None)
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))
    count: Optional[int] = strawberry.field(name="count", default=None)


register_type("RunAuthorityDiscoveryMutation", RunAuthorityDiscoveryMutation, model=None)


def _mutate_RunCorpusEnrichmentMutation(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:141

    Port of RunCorpusEnrichmentMutation.mutate
    """
    raise NotImplementedError("_mutate_RunCorpusEnrichmentMutation not yet ported — see manifest")


def m_run_corpus_enrichment(info: strawberry.Info, corpus_id: Annotated[strawberry.ID, strawberry.argument(name="corpusId", description='Global ID of the corpus to run on.')] = strawberry.UNSET, options: Annotated[Optional["RunEnrichmentOptionsInput"], strawberry.argument(name="options", description='Optional tuning knobs for the dispatched analyzers.')] = strawberry.UNSET, run_crawl: Annotated[Optional[bool], strawberry.argument(name="runCrawl", description='Dispatch the bounded authority-crawl analyzer.')] = False, run_enrichment: Annotated[Optional[bool], strawberry.argument(name="runEnrichment", description='Dispatch the reference-enrichment analyzer.')] = True) -> Optional["RunCorpusEnrichmentMutation"]:
    kwargs = strip_unset({"corpus_id": corpus_id, "options": options, "run_crawl": run_crawl, "run_enrichment": run_enrichment})
    return _mutate_RunCorpusEnrichmentMutation(RunCorpusEnrichmentMutation, None, info, **kwargs)


def _mutate_RunAuthorityDiscoveryMutation(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:389

    Port of RunAuthorityDiscoveryMutation.mutate
    """
    raise NotImplementedError("_mutate_RunAuthorityDiscoveryMutation not yet ported — see manifest")


def m_run_authority_discovery(info: strawberry.Info, frontier_ids: Annotated[list[strawberry.ID], strawberry.argument(name="frontierIds", description='Global IDs of the AuthorityFrontier rows to run discovery on.')] = strawberry.UNSET) -> Optional["RunAuthorityDiscoveryMutation"]:
    kwargs = strip_unset({"frontier_ids": frontier_ids})
    return _mutate_RunAuthorityDiscoveryMutation(RunAuthorityDiscoveryMutation, None, info, **kwargs)



MUTATION_FIELDS = {
    "run_corpus_enrichment": strawberry.field(resolver=m_run_corpus_enrichment, name="runCorpusEnrichment", description='Dispatch the enrichment and/or crawl analyzer on a corpus.\n\nThe caller must hold UPDATE on the corpus — both analyzers write\nreferences and/or publish authority documents into it.  At least one of\n``run_enrichment`` / ``run_crawl`` must be True.  On success every\ndispatched :class:`~opencontractserver.analyzer.models.Analysis` row is\nreturned; the rows are created synchronously even though the underlying\nCelery tasks are queued on transaction commit.'),
    "run_authority_discovery": strawberry.field(resolver=m_run_authority_discovery, name="runAuthorityDiscovery", description="Run authority discovery on a hand-picked set of ``AuthorityFrontier`` rows.\n\nThe corpus-agnostic counterpart to :class:`RunCorpusEnrichmentMutation`'s\ncrawl: instead of seeding + dequeuing the whole frontier under a corpus\n``Analysis``, this ingests *exactly* the selected rows (depth 0, no\nrecursion), so the global Authority Sources monitor can drain a chosen\nsubset of the queue.\n\n**Superuser-only.** The ``AuthorityFrontier`` is a global, system-managed\nqueue with no per-object permissions — mirroring the ``authorityFrontier``\nquery gate, there is no corpus to check ``UPDATE`` against. The work is\nenqueued fire-and-forget; the monitor reflects each row's ``discovery_state``\nas it transitions."),
}
