"""Generated strawberry GraphQL module (graphene migration).

Shape-generated from the graphene schema; stub functions marked PORT(...)
carry the ported business logic. See config/graphql_new/manifest.json.
"""

# mypy: disable-error-code="name-defined, valid-type, arg-type"
#   Code-generation artifacts of the strawberry schema bindings that
#   mypy's static pass cannot resolve, NOT real typing defects:
#     name-defined / valid-type — ``Annotated["XType", strawberry.lazy(...)]``
#       forward-reference strings + the runtime-generated ``*Connection``
#       types (``make_connection_types``).
#     arg-type — resolvers construct result types with ``to_global_id()``
#       (``str``) for ``strawberry.ID`` fields and return Django MODEL
#       instances where the field annotation names the strawberry type
#       (the graphene-django resolver contract). Both are correct at
#       runtime. Hand-written config/graphql/core/* stays fully checked.
# flake8: noqa: E501, F821 — generated strawberry schema module.
# E501: long GraphQL field/argument ``description=`` strings and the
# single-line generated resolver signatures (black cannot split string
# literals). F821: ``Annotated["XType", strawberry.lazy(...)]`` /
# ``cast("QuerySet", ...)`` forward-reference STRINGS that pyflakes
# resolves as names — the whole point of strawberry.lazy is to avoid the
# import (which would then be F401). Both are code-generation artifacts,
# not defects; hand-written modules (config/graphql/core/*, security.py,
# testing.py, filters.py, …) stay fully linted.

from __future__ import annotations

import logging
from typing import Annotated, Any

import strawberry
from django.db import transaction
from graphql_relay import from_global_id

from config.graphql._util import strip_unset
from config.graphql.core.auth import PermissionDenied
from config.graphql.core.relay import (
    register_type,
)
from config.graphql.ratelimits import RateLimits, graphql_ratelimit
from opencontractserver.analyzer.services.analysis_lifecycle_service import (
    AnalysisLifecycleService,
)
from opencontractserver.corpuses.models import Corpus
from opencontractserver.corpuses.services import CorpusService
from opencontractserver.enrichment import constants as C
from opencontractserver.enrichment.services import EnrichmentService
from opencontractserver.enrichment.services.authority_permissions import (
    DENIED,
    is_authority_admin,
)
from opencontractserver.enrichment.services.crawl_authorities_service import (
    CrawlAuthoritiesService,
)

logger = logging.getLogger(__name__)

# field -> (minimum, maximum) for caller-supplied crawl bounds. ``maximum=None``
# means "no upper bound": for ``min_demand`` a HIGHER value is MORE selective
# (it skips more frontier rows), so it is cheaper, never a resource risk — only
# a floor is enforced (mirrors the crawl analyzer input schema, which sets only
# ``minimum: 0`` on min_demand). The remaining bounds gate the EXPENSIVE
# direction, so they are capped at the safe default.
CRAWL_BOUND_LIMITS: dict[str, tuple[int, int | None]] = {
    "max_depth": (0, C.CRAWL_MAX_ALLOWED_DEPTH),
    "min_demand": (0, None),
    "max_authorities": (1, C.CRAWL_DEFAULT_MAX_AUTHORITIES),
    "per_jurisdiction_cap": (1, C.CRAWL_DEFAULT_PER_JURISDICTION_CAP),
    # A zero token budget disables the crawl loop's budget stop check; require
    # a positive budget when callers override the safe default.
    "token_budget": (1, C.CRAWL_DEFAULT_TOKEN_BUDGET),
}


def _validate_crawl_bounds(options: Any | None) -> tuple[dict[str, int], str | None]:
    """Validate crawl options before queueing a worker-consuming job."""

    bounds: dict[str, int] = {}
    for field, (minimum, maximum) in CRAWL_BOUND_LIMITS.items():
        val = getattr(options, field, None) if options is not None else None
        # strawberry input fields default to ``strawberry.UNSET`` when omitted
        # (graphene surfaced these as ``None``); treat both as "not supplied".
        if val is None or val is strawberry.UNSET:
            continue
        if val < minimum or (maximum is not None and val > maximum):
            msg = (
                f"{field} must be at least {minimum}."
                if maximum is None
                else f"{field} must be between {minimum} and {maximum}."
            )
            return {}, msg
        bounds[field] = val
    return bounds, None


@strawberry.input(
    name="RunEnrichmentOptionsInput",
    description="Optional tuning knobs forwarded to the enrichment / crawl analyzers.",
)
class RunEnrichmentOptionsInput:
    reference_types: list[str | None] | None = strawberry.field(
        name="referenceTypes",
        description="Restrict enrichment to these reference-type codes (e.g. 'LAW').",
        default=strawberry.UNSET,
    )
    use_llm_tier: bool | None = strawberry.field(
        name="useLlmTier",
        description="Enable the LLM detection tier for the enrichment analyzer.",
        default=False,
    )
    max_depth: int | None = strawberry.field(
        name="maxDepth",
        description="Maximum authority-to-authority BFS depth.",
        default=strawberry.UNSET,
    )
    min_demand: int | None = strawberry.field(
        name="minDemand",
        description="Skip frontier rows with mention_count below this floor.",
        default=strawberry.UNSET,
    )
    max_authorities: int | None = strawberry.field(
        name="maxAuthorities",
        description="Hard cap on authority-bootstrap calls per run.",
        default=strawberry.UNSET,
    )
    per_jurisdiction_cap: int | None = strawberry.field(
        name="perJurisdictionCap",
        description="Maximum ingests per jurisdiction code per run.",
        default=strawberry.UNSET,
    )
    token_budget: int | None = strawberry.field(
        name="tokenBudget",
        description="Approximate token budget for the crawl run.",
        default=strawberry.UNSET,
    )


@strawberry.type(
    name="RunCorpusEnrichmentMutation",
    description="Dispatch the enrichment and/or crawl analyzer on a corpus.\n\nThe caller must hold UPDATE on the corpus — both analyzers write\nreferences and/or publish authority documents into it.  At least one of\n``run_enrichment`` / ``run_crawl`` must be True.  On success every\ndispatched :class:`~opencontractserver.analyzer.models.Analysis` row is\nreturned; the rows are created synchronously even though the underlying\nCelery tasks are queued on transaction commit.",
)
class RunCorpusEnrichmentMutation:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    analyses: None | (
        list[
            None
            | (Annotated[AnalysisType, strawberry.lazy("config.graphql.extract_types")])
        ]
    ) = strawberry.field(name="analyses", default=None)
    partial: bool | None = strawberry.field(
        name="partial",
        description="True when some requested jobs dispatched but others failed (e.g. enrichment started but the crawl could not be dispatched). Only meaningful when ``ok`` is True; lets callers surface the non-fatal ``message`` without coupling to its text.",
        default=None,
    )


register_type("RunCorpusEnrichmentMutation", RunCorpusEnrichmentMutation, model=None)


@strawberry.type(
    name="RunAuthorityDiscoveryMutation",
    description="Run authority discovery on a hand-picked set of ``AuthorityFrontier`` rows.\n\nThe corpus-agnostic counterpart to :class:`RunCorpusEnrichmentMutation`'s\ncrawl: instead of seeding + dequeuing the whole frontier under a corpus\n``Analysis``, this ingests *exactly* the selected rows (depth 0, no\nrecursion), so the global Authority Sources monitor can drain a chosen\nsubset of the queue.\n\n**Superuser-only.** The ``AuthorityFrontier`` is a global, system-managed\nqueue with no per-object permissions — mirroring the ``authorityFrontier``\nquery gate, there is no corpus to check ``UPDATE`` against. The work is\nenqueued fire-and-forget; the monitor reflects each row's ``discovery_state``\nas it transitions.",
)
class RunAuthorityDiscoveryMutation:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    count: int | None = strawberry.field(name="count", default=None)


register_type(
    "RunAuthorityDiscoveryMutation", RunAuthorityDiscoveryMutation, model=None
)


def _mutate_RunCorpusEnrichmentMutation(
    payload_cls,
    root,
    info,
    corpus_id,
    run_enrichment=True,
    run_crawl=False,
    options=None,
):
    """PORT: config/graphql/enrichment_mutations.py:141

    Port of RunCorpusEnrichmentMutation.mutate
    """
    # @login_required — inlined because mutate stubs take ``payload_cls`` as
    # their first positional argument, which does not match core.auth's
    # ``(root, info, ...)`` calling convention. ``graphql_ratelimit`` is applied
    # to an inner function named ``mutate`` so the rate-limit cache group
    # (defaults to the decorated function's ``__name__``) stays "mutate",
    # exactly as in the graphene layer.
    if not info.context.user.is_authenticated:
        raise PermissionDenied()

    @graphql_ratelimit(rate=RateLimits.AI_ANALYSIS)
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
            type_name, corpus_pk = from_global_id(corpus_id)
            # Validate the relay type prefix: ``from_global_id`` happily decodes
            # ``DocumentType:42`` and we must not let a non-Corpus pk flow into
            # ``start_document_analysis(corpus_pk=...)`` and rely solely on the
            # downstream visibility filter as a safety net.
            if type_name != "CorpusType" or not corpus_pk:
                raise ValueError("invalid corpus ID")
        except Exception:
            # Intentionally broad: ``from_global_id`` raises on non-base64 /
            # malformed relay ids (binascii/UnicodeDecodeError, ValueError), and
            # the explicit ``raise`` above covers a wrong type prefix. All map to
            # the same generic not-found/no-permission response so a caller cannot
            # distinguish "malformed id" from "exists but not visible" (IDOR).
            return payload_cls(
                ok=False,
                partial=False,
                message="Resource not found or you do not have permission.",
                analyses=[],
            )

        # ---- Corpus visibility gate: must run before ANY branch that could
        # leak corpus-specific state (e.g. "a job is already running") to a
        # caller who cannot even see the corpus. Without this, a user with no
        # access to ``corpus_pk`` could use the duplicate-job guard below as an
        # oracle: the error message differs depending on whether an active
        # analysis exists on a corpus they have never been granted READ on.
        # ``start_document_analysis`` re-checks visibility (and UPDATE) later;
        # that is intentional defence-in-depth, not redundant guarding — this
        # gate only proves the caller may observe the corpus's state at all.
        if (
            CorpusService.get_or_none(Corpus, corpus_pk, user, request=info.context)
            is None
        ):
            return payload_cls(
                ok=False,
                partial=False,
                message="Resource not found or you do not have permission.",
                analyses=[],
            )

        if not run_enrichment and not run_crawl:
            return payload_cls(
                ok=False,
                partial=False,
                message="Select at least one job (runEnrichment or runCrawl).",
                analyses=[],
            )

        # ---- Lock-free validation: fail fast before opening a transaction ----
        if run_enrichment:
            use_llm = bool(getattr(options, "use_llm_tier", False) or False)
            if use_llm and not is_authority_admin(user):
                return payload_cls(
                    ok=False,
                    partial=False,
                    message="Only authority administrators can enable the LLM tier.",
                    analyses=[],
                )
        else:
            use_llm = False

        if run_crawl:
            bounds, bounds_error = _validate_crawl_bounds(options)
            if bounds_error:
                return payload_cls(
                    ok=False,
                    partial=False,
                    message=bounds_error,
                    analyses=[],
                )
        else:
            bounds = {}

        if run_enrichment:
            enrichment_input: dict[str, Any] = {"use_llm": use_llm}
            ref_types = getattr(options, "reference_types", None)
            # An omitted field (None) or an explicitly empty list are both
            # treated as "no type restriction" — ``types`` stays unset and the
            # analyzer uses its default set. Only a non-empty list is validated;
            # the deliberate-empty-list case isn't an error (it's equivalent to
            # omitting the field).
            if ref_types:
                # Reject unknown codes rather than silently dropping them. If we
                # filtered to an empty ``valid_types`` and left ``types`` unset,
                # the analyzer would fall through to scanning ALL reference types
                # — the opposite of the caller's intent. Surface the bad codes so
                # the caller knows their request was rejected, not modified.
                unknown = [t for t in ref_types if t not in C.ALL_REFERENCE_TYPES]
                if unknown:
                    return payload_cls(
                        ok=False,
                        partial=False,
                        message=(
                            "Unknown reference type(s): "
                            + ", ".join(unknown)
                            + ". Valid types: "
                            + ", ".join(C.ALL_REFERENCE_TYPES)
                            + "."
                        ),
                        analyses=[],
                    )
                enrichment_input["types"] = list(ref_types)

        # ---- Atomic check-and-create under a per-corpus dispatch lock --------
        # The duplicate-job guard and the analysis creation run as one atomic
        # unit while holding a row lock on the corpus, so two concurrent requests
        # for the same corpus cannot both read "no active job" and both dispatch
        # (TOCTOU). The on_commit-queued Celery tasks fire only after this commits.
        created = []
        with transaction.atomic():
            AnalysisLifecycleService.lock_corpus_for_dispatch(corpus_pk)

            if run_enrichment and AnalysisLifecycleService.active_analysis_exists(
                corpus_pk, C.ENRICHMENT_ANALYZER_TASK
            ):
                return payload_cls(
                    ok=False,
                    partial=False,
                    message="An enrichment analysis is already queued or running.",
                    analyses=[],
                )
            if run_crawl and AnalysisLifecycleService.active_analysis_exists(
                corpus_pk, C.CRAWL_ANALYZER_TASK
            ):
                return payload_cls(
                    ok=False,
                    partial=False,
                    message="An authority crawl is already queued or running.",
                    analyses=[],
                )

            if run_enrichment:
                analyzer = EnrichmentService.get_or_create_analyzer(user.id)
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
                    analysis_input_data=enrichment_input,
                    request=info.context,
                    require_corpus_update=True,
                )
                if not res.ok:
                    return payload_cls(
                        ok=False,
                        partial=False,
                        message=res.error,
                        analyses=[],
                    )
                created.append(res.value)

            if run_crawl:
                analyzer = CrawlAuthoritiesService.get_or_create_analyzer(user.id)
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
                    if created:
                        # Partial success: the enrichment analysis was already
                        # dispatched and is now running. Return ok=True with the
                        # already-created row(s) and a non-fatal message so the
                        # caller surfaces the running job instead of treating the
                        # whole request as failed (and re-dispatching enrichment,
                        # double-running it).
                        return payload_cls(
                            ok=True,
                            partial=True,
                            message=(
                                "Enrichment started, but the authority crawl could "
                                f"not be dispatched: {res.error}"
                            ),
                            analyses=created,
                        )
                    return payload_cls(
                        ok=False,
                        partial=False,
                        message=res.error,
                        analyses=[],
                    )
                created.append(res.value)

        return payload_cls(
            ok=True,
            partial=False,
            message="SUCCESS",
            analyses=created,
        )

    return mutate(
        root,
        info,
        corpus_id,
        run_enrichment=run_enrichment,
        run_crawl=run_crawl,
        options=options,
    )


def m_run_corpus_enrichment(
    info: strawberry.Info,
    corpus_id: Annotated[
        strawberry.ID,
        strawberry.argument(
            name="corpusId", description="Global ID of the corpus to run on."
        ),
    ] = strawberry.UNSET,
    options: Annotated[
        RunEnrichmentOptionsInput | None,
        strawberry.argument(
            name="options",
            description="Optional tuning knobs for the dispatched analyzers.",
        ),
    ] = strawberry.UNSET,
    run_crawl: Annotated[
        bool | None,
        strawberry.argument(
            name="runCrawl",
            description="Dispatch the bounded authority-crawl analyzer.",
        ),
    ] = False,
    run_enrichment: Annotated[
        bool | None,
        strawberry.argument(
            name="runEnrichment",
            description="Dispatch the reference-enrichment analyzer.",
        ),
    ] = True,
) -> RunCorpusEnrichmentMutation | None:
    kwargs = strip_unset(
        {
            "corpus_id": corpus_id,
            "options": options,
            "run_crawl": run_crawl,
            "run_enrichment": run_enrichment,
        }
    )
    return _mutate_RunCorpusEnrichmentMutation(
        RunCorpusEnrichmentMutation, None, info, **kwargs
    )


def _mutate_RunAuthorityDiscoveryMutation(payload_cls, root, info, frontier_ids):
    """PORT: config/graphql/enrichment_mutations.py:389

    Port of RunAuthorityDiscoveryMutation.mutate
    """
    # @login_required — inlined (see _mutate_RunCorpusEnrichmentMutation).
    if not info.context.user.is_authenticated:
        raise PermissionDenied()
    user = info.context.user
    if not is_authority_admin(user):
        # Same opaque message whether the rows exist or the user lacks
        # access — the frontier is superuser-only, no existence oracle.
        return payload_cls(ok=False, message=DENIED, count=0)

    pks: list[int] = []
    for gid in frontier_ids:
        try:
            pks.append(int(from_global_id(gid)[1]))
        except (ValueError, TypeError, IndexError):
            continue
    pks = list(dict.fromkeys(pks))  # de-dupe, preserve order

    if not pks:
        return payload_cls(
            ok=False,
            message="No valid authority rows selected.",
            count=0,
        )

    # Bound the batch: discover_selected runs rows sequentially in one
    # Celery task, so an unbounded list could run a worker for an unbounded
    # time. Reject oversize batches instead of silently truncating; the
    # superuser can re-issue for the remainder.
    if len(pks) > C.AUTHORITY_DISCOVERY_MAX_BATCH:
        return payload_cls(
            ok=False,
            message=(
                "Too many authorities selected "
                f"(max {C.AUTHORITY_DISCOVERY_MAX_BATCH} per run)."
            ),
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
    return payload_cls(
        ok=True,
        message=f"Discovery started for {len(pks)} authorit{plural}.",
        count=len(pks),
    )


def m_run_authority_discovery(
    info: strawberry.Info,
    frontier_ids: Annotated[
        list[strawberry.ID],
        strawberry.argument(
            name="frontierIds",
            description="Global IDs of the AuthorityFrontier rows to run discovery on.",
        ),
    ] = strawberry.UNSET,
) -> RunAuthorityDiscoveryMutation | None:
    kwargs = strip_unset({"frontier_ids": frontier_ids})
    return _mutate_RunAuthorityDiscoveryMutation(
        RunAuthorityDiscoveryMutation, None, info, **kwargs
    )


MUTATION_FIELDS = {
    "run_corpus_enrichment": strawberry.field(
        resolver=m_run_corpus_enrichment,
        name="runCorpusEnrichment",
        description="Dispatch the enrichment and/or crawl analyzer on a corpus.\n\nThe caller must hold UPDATE on the corpus — both analyzers write\nreferences and/or publish authority documents into it.  At least one of\n``run_enrichment`` / ``run_crawl`` must be True.  On success every\ndispatched :class:`~opencontractserver.analyzer.models.Analysis` row is\nreturned; the rows are created synchronously even though the underlying\nCelery tasks are queued on transaction commit.",
    ),
    "run_authority_discovery": strawberry.field(
        resolver=m_run_authority_discovery,
        name="runAuthorityDiscovery",
        description="Run authority discovery on a hand-picked set of ``AuthorityFrontier`` rows.\n\nThe corpus-agnostic counterpart to :class:`RunCorpusEnrichmentMutation`'s\ncrawl: instead of seeding + dequeuing the whole frontier under a corpus\n``Analysis``, this ingests *exactly* the selected rows (depth 0, no\nrecursion), so the global Authority Sources monitor can drain a chosen\nsubset of the queue.\n\n**Superuser-only.** The ``AuthorityFrontier`` is a global, system-managed\nqueue with no per-object permissions — mirroring the ``authorityFrontier``\nquery gate, there is no corpus to check ``UPDATE`` against. The work is\nenqueued fire-and-forget; the monitor reflects each row's ``discovery_state``\nas it transitions.",
    ),
}
