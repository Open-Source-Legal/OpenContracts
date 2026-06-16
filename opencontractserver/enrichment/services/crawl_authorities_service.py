"""Bounded recursive authority crawl (BFS over the AuthorityFrontier).

Seeds the frontier from wanted_authorities (depth 0), then repeatedly dequeues
the highest-demand queued row, discovers and bootstraps it, and on 'ingested'
re-extracts the new authority document's outbound citations to seed the frontier
at depth+1.  Stops on bounds (max_depth, authority cap, per-jurisdiction cap,
min-demand floor, token budget) — every stop reason is in the summary dict.
"""

from __future__ import annotations

import logging
from collections import Counter

from opencontractserver.annotations.models import AuthorityFrontier
from opencontractserver.enrichment import constants as C
from opencontractserver.enrichment.services.authority_discovery_service import (
    AuthorityDiscoveryService,
)
from opencontractserver.enrichment.services.authority_frontier_service import (
    AuthorityFrontierService,
)
from opencontractserver.enrichment.services.corpus_reference_service import (
    CorpusReferenceService,
)
from opencontractserver.enrichment.services.enrichment_service import EnrichmentService
from opencontractserver.shared.services.base import BaseService
from opencontractserver.users.models import User

logger = logging.getLogger(__name__)


class CrawlAuthoritiesService(BaseService):
    """Drive a bounded BFS over the authority frontier."""

    @classmethod
    def crawl(
        cls,
        *,
        creator_id: int,
        corpus_id: int | None = None,
        max_depth: int = C.CRAWL_DEFAULT_MAX_DEPTH,
        min_demand: int = C.CRAWL_DEFAULT_MIN_DEMAND,
        max_authorities: int = C.CRAWL_DEFAULT_MAX_AUTHORITIES,
        per_jurisdiction_cap: int = C.CRAWL_DEFAULT_PER_JURISDICTION_CAP,
        token_budget: int = C.CRAWL_DEFAULT_TOKEN_BUDGET,
        make_public: bool = True,
        log=logger.info,
    ) -> dict:
        """Run a bounded BFS crawl over the authority frontier.

        Seeds depth-0 rows from the Wanted Authorities aggregation, then
        iterates the BFS loop until one of four hard caps is hit or the
        frontier is drained.  Returns a full summary dict — no silent
        truncation of outcomes, blocked tallies, or the residual census.

        Args:
            creator_id: PK of the user who will own discovered authority corpora.
            corpus_id: If given, restrict the Wanted Authorities seed to one
                corpus.  None = all visible corpora.
            max_depth: Authority-to-authority hops past depth-0 seeds.
            min_demand: Skip frontier rows with mention_count below this floor.
            max_authorities: Hard cap on ``discover_and_bootstrap`` calls per run.
            per_jurisdiction_cap: Max ingests per jurisdiction code per run.
                Cap-blocked rows are parked at ``deferred_cap`` so they are not
                re-dequeued in the same run (termination guarantee).
            token_budget: Cumulative estimated tokens (text length / 4) before
                stopping.  0 or negative = unbounded.
            make_public: Publish discovered authority corpora (default True).
            log: Callable used for progress messages (default ``logger.info``).

        Returns:
            Summary dict with keys:
                corpus_id, stop_reason, max_depth, min_demand, max_authorities,
                per_jurisdiction_cap, token_budget, tokens_spent_estimate,
                seed_created, seed_updated, authorities_ingested, children_seeded,
                outcomes, blocked_by_bound, per_jurisdiction, frontier_residual.
        """
        user = User.objects.get(pk=creator_id)

        # --- depth-0 seed from the Wanted Authorities aggregation ---------------
        seed = AuthorityFrontierService.seed_from_wanted_authorities(
            user, corpus_id=corpus_id
        )
        log(
            "crawl seed: created=%s updated=%s",
            seed["frontier_created"],
            seed["frontier_updated"],
        )

        ingested = 0
        tokens_spent = 0
        per_juris: Counter = Counter()
        outcomes: Counter = Counter()
        child_seeded = 0
        blocked_by_bound: Counter = Counter()
        stop_reason = "frontier_drained"

        while True:
            # Hard cap checks before dequeue so the summary is honest.
            if ingested >= max_authorities:
                stop_reason = "max_authorities"
                break
            # token_budget <= 0 means "unbounded" (the check is skipped entirely).
            if token_budget > 0 and tokens_spent >= token_budget:
                stop_reason = "token_budget"
                break

            rows = AuthorityFrontierService.dequeue_queued(
                limit=1, max_depth=max_depth, min_demand=min_demand
            )
            if not rows:
                # Count how many queued rows remain so the summary is non-silent
                # about what was left. This is the UNION of rows excluded by the
                # min_demand floor and/or the max_depth bound — the single key
                # does not attribute each row to one cause or the other.
                blocked_by_bound["min_demand_or_depth"] = (
                    AuthorityFrontier.objects.filter(discovery_state="queued").count()
                )
                stop_reason = "frontier_drained"
                break

            row = rows[0]

            # Per-jurisdiction cap: checked per-row (not a dequeue filter) so
            # high-demand rows in a capped jurisdiction don't starve the loop —
            # they get parked and the loop continues.
            jkey = row.jurisdiction or "unknown"
            if per_juris[jkey] >= per_jurisdiction_cap:
                blocked_by_bound[f"jurisdiction_cap:{jkey}"] += 1
                # Park at "deferred_cap" so dequeue_queued (which filters on
                # discovery_state="queued") cannot re-return this row this run —
                # the structural guarantee that the cap branch terminates.
                AuthorityFrontierService.mark(row, "deferred_cap")
                continue

            result = AuthorityDiscoveryService.discover_and_bootstrap(
                creator_id=creator_id,
                frontier_row=row,
                make_public=make_public,
                relink_async=True,
            )
            status = result["status"]
            outcomes[status] += 1
            log(
                "crawl %s -> %s (depth=%s)",
                row.canonical_key,
                status,
                row.depth,
            )

            if status != "ingested":
                # discover_and_bootstrap already marked the row terminal.
                continue

            ingested += 1
            per_juris[jkey] += 1
            authority_corpus_id = result["corpus_id"]

            # Re-extract the authority's OWN outbound citations and seed the
            # frontier at depth+1 — only when we haven't reached max_depth.
            if row.depth < max_depth:
                # Authority corpora hold one small document per statute section,
                # so this apply scan is bounded (not a large-corpus scan).
                apply_res = EnrichmentService().apply(
                    corpus_id=authority_corpus_id,
                    creator_id=creator_id,
                    types=[C.REF_LAW],
                    extra_tiers=[C.DETECTION_TIER_GRAMMAR],
                )
                tokens_spent += cls._estimate_tokens(authority_corpus_id, user)

                outbound = list(
                    CorpusReferenceService.for_corpus(user, authority_corpus_id)
                    .filter(
                        reference_type=C.REF_LAW,
                        resolution_status=C.STATUS_EXTERNAL,
                    )
                    .exclude(canonical_key=None)
                    .values_list("canonical_key", flat=True)
                    .distinct()
                )
                seeded = AuthorityFrontierService.seed_child_keys(row, outbound)
                child_seeded += seeded["child_created"]
                log(
                    "  re-extract %s: %s outbound, %s new frontier rows "
                    "(refs_created=%s)",
                    authority_corpus_id,
                    len(outbound),
                    seeded["child_created"],
                    apply_res.get("references_created", 0),
                )

        residual = cls._state_census()

        summary = {
            "corpus_id": corpus_id,
            "stop_reason": stop_reason,
            "max_depth": max_depth,
            "min_demand": min_demand,
            "max_authorities": max_authorities,
            "per_jurisdiction_cap": per_jurisdiction_cap,
            "token_budget": token_budget,
            "tokens_spent_estimate": tokens_spent,
            "seed_created": seed["frontier_created"],
            "seed_updated": seed["frontier_updated"],
            "authorities_ingested": ingested,
            "children_seeded": child_seeded,
            "outcomes": dict(outcomes),
            "blocked_by_bound": dict(blocked_by_bound),
            "per_jurisdiction": dict(per_juris),
            "frontier_residual": residual,
        }
        log("crawl complete: %s", summary)
        return summary

    @staticmethod
    def _estimate_tokens(corpus_id: int, user: User) -> int:
        """Rough token spend estimate: total authority-corpus text length / 4.

        Used only to check against ``token_budget`` — a conservative lower
        bound.  Returns 0 if the corpus has no text extracts yet (newly
        bootstrapped corpora may not have text files persisted in the same
        transaction).
        """
        from opencontractserver.corpuses.models import Corpus
        from opencontractserver.corpuses.services import CorpusDocumentService
        from opencontractserver.utils.files import read_field_file_text

        try:
            corpus = Corpus.objects.get(pk=corpus_id)
        except Corpus.DoesNotExist:
            return 0

        total = 0
        for doc in CorpusDocumentService.get_corpus_documents(user, corpus):
            try:
                total += len(read_field_file_text(doc.txt_extract_file) or "")
            except (OSError, ValueError, AttributeError):
                continue
        return total // 4

    @staticmethod
    def _state_census() -> dict:
        """Return a {discovery_state: count} census of ALL frontier rows.

        Used in the summary to satisfy the no-silent-truncation invariant:
        ``sum(frontier_residual.values()) == AuthorityFrontier.objects.count()``.
        """
        from django.db.models import Count

        return {
            row["discovery_state"]: row["n"]
            for row in AuthorityFrontier.objects.values("discovery_state").annotate(
                n=Count("id")
            )
        }
