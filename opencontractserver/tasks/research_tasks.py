"""Celery tasks for the deep-research agent.

``run_deep_research`` mirrors the shape of
:func:`opencontractserver.tasks.agent_tasks.run_agent_corpus_action` —
load the row, mark started, drive an async agent loop, persist results,
fire a notification.
"""

from __future__ import annotations

import asyncio
import logging
import traceback
from collections.abc import Sequence
from typing import Any, Callable, cast, get_args

from asgiref.sync import sync_to_async
from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
from django.conf import settings
from django.utils import timezone

from opencontractserver.annotations.models import Annotation
from opencontractserver.enrichment.finding_cards import (
    OBLIGATION_SCHEMA_MARKER,
    Applicability,
    Confidence,
    ObligationCard,
    ObligationSchema,
    RegimeCard,
)
from opencontractserver.llms.context_guardrails import CompactionConfig
from opencontractserver.research.constants import (
    DEEP_RESEARCH_COMPACTION_RATIO,
    DEEP_RESEARCH_MEMORY_TOOL_NAMES,
    DEEP_RESEARCH_READ_ONLY_TOOLS,
    DEEP_RESEARCH_RETRIEVAL_CLOSURE_TOOLS,
    RESEARCH_CITABLE_PASSAGE_MAX_HITS,
    RESEARCH_CITABLE_PASSAGE_PREVIEW_CHARS,
    RESEARCH_GROUP_SEARCH_MAX_K_PER_CORPUS,
    RESEARCH_GROUP_SEARCH_MAX_ROWS,
    RESEARCH_HEADER_ANCHOR_LABEL_VARIANTS,
    build_deep_research_system_prompt,
    build_step_budget_notice,
)
from opencontractserver.research.models import ResearchReport
from opencontractserver.research.services.research_reports import (
    ResearchCancelled,
    ResearchMemoryError,
    ResearchReportService,
    party_named_in_passages,
)
from opencontractserver.types.enums import JobStatus

logger = logging.getLogger(__name__)


SCRATCHPAD_TOOL_NAMES = {"record_finding", "finalize_report"}


#: Fields that make a finding a *card*. All-or-nothing: a half-filled card is
#: worse than a plain finding, because a consumer cannot tell an absent field
#: from an unestablished one.
_CARD_REQUIRED = ("as_of_date", "applicable_process", "authority_status", "confidence")

#: Accepted when the agent genuinely found nothing unresolved. The point is
#: that SOMETHING must be said: an empty list is indistinguishable from a field
#: nobody filled in, so "we looked and found none" and "we never looked" render
#: identically — the exact ambiguity the card exists to remove.
NOTHING_UNRESOLVED = "None identified in the public record."

#: Runtime copy of the ``Applicability`` literal, for validating tool input.
APPLICABILITY_VALUES = frozenset(get_args(Applicability))


def _build_obligation_card(
    *,
    obligation: str | None,
    applicability: str | None,
    applies_at: list[float] | None,
    responsible_party: str | None,
    preparer: str | None,
    submitter: str | None,
    recipient: str | None,
    certifier: str | None,
    approval_date: str | None,
    effective_date: str | None,
    service_request_date: str | None,
    application_date: str | None,
    commencement_date: str | None,
    form_reference: str | None,
    material: bool,
    deadline: str | None,
    confidence: str | None,
    unresolved_qualifications: list[str] | None,
    has_citations: bool,
    cited_passages: Sequence[str],
    schema: ObligationSchema,
) -> tuple[dict[str, Any] | None, str | None]:
    """Validate the project-readiness shape of a finding card.

    A regime card answers "what governed on date X" and is built around an
    interval. A readiness question — which requirements apply, which forms are
    needed, what is still unknown — has no interval, and forcing it through the
    regime shape pushed the substance back into prose.

    The gates below are the acceptance criteria expressed as code rather than
    as hope: an obligation with no obligor cannot be acted on; a PHASE_TRIGGERED
    obligation that does not say which ramp step it bites at has not actually
    been classified; and a material obligation with no citation is refused
    outright rather than allowed into a report that looks sourced.
    """
    if not obligation or not obligation.strip():
        return None, "an obligation card needs a non-empty 'obligation'."
    if not responsible_party or not responsible_party.strip():
        return None, (
            "an obligation card needs 'responsible_party' — who must do this "
            "(e.g. the interconnecting entity, the TSP, the DSP). An obligation "
            "with no obligor cannot be acted on."
        )

    normalised_applicability = (applicability or "").strip().upper().replace(" ", "_")
    if normalised_applicability not in APPLICABILITY_VALUES:
        return None, (
            "applicability must be one of "
            f"{', '.join(sorted(APPLICABILITY_VALUES))} (got {applicability!r}). "
            "Classify every obligation: 'it depends' is CONDITIONAL, 'only "
            "above a ramp step' is PHASE_TRIGGERED, 'the record does not say' "
            "is UNRESOLVED."
        )

    steps = [float(s) for s in (applies_at or []) if str(s).strip() != ""]
    # Membership is checked only when the corpus configures a scale. Without
    # one the card still has to say WHERE a phase-triggered obligation bites —
    # that requirement is what makes the classification mean anything — but
    # nothing constrains the values, because there is no list to constrain them
    # against. See ``ObligationSchema``.
    if schema.has_scale:
        unknown = [s for s in steps if s not in schema.threshold_steps]
        if unknown:
            return None, (
                f"applies_at {[_format_number(u) for u in unknown]} are not "
                f"{schema.threshold_label} steps under evaluation; use only "
                f"{[_format_number(s) for s in schema.threshold_steps]}"
                f"{(' ' + schema.threshold_unit) if schema.threshold_unit else ''}."
            )
    if normalised_applicability == "PHASE_TRIGGERED" and not steps:
        scale = schema.describe()
        return None, (
            "a PHASE_TRIGGERED obligation must say where it bites via "
            "applies_at"
            + (f" (the {scale})" if scale else "")
            + ". Without it 'phase-triggered' is a label, not a classification."
        )

    normalised_confidence = (confidence or "").strip().upper()
    if normalised_confidence not in {"HIGH", "MEDIUM", "LOW"}:
        return None, f"confidence must be HIGH, MEDIUM or LOW (got {confidence!r})."

    qualifications = [q.strip() for q in (unresolved_qualifications or []) if q.strip()]
    if not qualifications:
        return None, (
            "unresolved_qualifications cannot be empty on a finding card. State "
            "what the public record does not settle about this obligation — for "
            "a readiness question that is usually the fact the project has yet "
            f"to supply. If nothing is unresolved, say so: {NOTHING_UNRESOLVED!r}."
        )

    # The evidence gate. Refused at the door rather than filtered at
    # finalisation, so the agent is told immediately and can re-search — a card
    # silently dropped later reads to the model as if it had been accepted.
    if material and not has_citations:
        return None, (
            "a MATERIAL obligation needs at least one supporting_source_ids "
            "entry. Search for the language that imposes it and cite that "
            "annotation, or mark the card material=False if it is context "
            "rather than an obligation the project must discharge."
        )

    # The attribution check. A card naming an obligor its own evidence never
    # mentions is the misattribution reviewers actually catch, and it survives
    # every check above: the obligation is real, the citation is real, and only
    # the party is imported from somewhere else.
    #
    # MARKED, not refused. Refusing cost more than it bought. A refusal loses
    # the obligation outright — a run that found many requirements filed two —
    # and the agent, given a way out in prose, spent its remaining budget
    # guessing at it: "Not specified in cited passage", then the text of the
    # instruction itself pasted into the field as a party name. An obligation
    # whose obligor is inferred is worth recording and worth labelling; it is
    # not worth deleting, and no wording of a refusal makes a passage name a
    # party it does not name.
    obligor_grounded = not material or party_named_in_passages(
        responsible_party, cited_passages
    )

    return (
        ObligationCard(
            obligation=obligation.strip(),
            applicability=cast("Applicability", normalised_applicability),
            applies_at=sorted(set(steps)),
            threshold_unit=schema.threshold_unit,
            responsible_party=responsible_party.strip(),
            preparer=_clean(preparer),
            submitter=_clean(submitter),
            recipient=_clean(recipient),
            certifier=_clean(certifier),
            obligor_grounded=obligor_grounded,
            approval_date=_clean(approval_date),
            effective_date=_clean(effective_date),
            service_request_date=_clean(service_request_date),
            application_date=_clean(application_date),
            commencement_date=_clean(commencement_date),
            deadline=_clean(deadline),
            form_reference=_clean(form_reference),
            material=bool(material),
            confidence=cast("Confidence", normalised_confidence),
            unresolved_qualifications=qualifications,
        ).model_dump(),
        None,
    )


def _format_number(value: float) -> str:
    """``25.0`` -> ``25``. Threshold steps are usually whole, and an agent-facing
    message reading "25.0 MW" invites the model to echo the float back."""
    return str(int(value)) if float(value).is_integer() else str(value)


def _clean(value: str | None) -> str | None:
    """Blank-to-null, so an empty string never reads as a stated value."""
    cleaned = (value or "").strip()
    return cleaned or None


def _audit_default_toolset(
    report: ResearchReport, agent: Any, *, already_audited: frozenset[str] = frozenset()
) -> None:
    """Extend the audit log to the tools this module did not build.

    ``_audited`` covers the closures assembled here. It never covered the
    agent's DEFAULT toolset — ``similarity_search``, ``list_documents``,
    ``ask_document`` and the rest come from the corpus agent and are registered
    by the factory — so ``tool_call_log`` recorded roughly half of what a run
    did and the Run details tab presented that half as the whole.

    The cost of the gap was not cosmetic. Ten runs were read off that log as
    having retrieved only by exact phrase and never once by meaning, and a
    prompt was rewritten on the strength of it; the worker log showed those
    runs embedding query after query, which only ``similarity_search`` does.
    An instrument that cannot see a tool will report that the tool was never
    used.

    ``already_audited`` names the closures this module wrapped itself, and it is
    matched by NAME on purpose. The obvious guard — a marker attribute on the
    wrapper — does not hold: the closures are handed to the factory as caller
    tools and the factory re-wraps them, so the callable reachable at
    ``function_schema.function`` is the factory's wrapper, not ours, and it
    carries no marker. Every closure call was therefore logged twice, which
    would be cosmetic except that the step-budget counter reads the log length:
    a run at 27 real tool calls was being told "54 of 60 used" and pushed to
    finalize with half its budget unspent. The attribute check is kept as a
    second line of defence for anything that does survive.

    ``FunctionSchema.call`` resolves ``self.function`` at call time, so
    replacing it here intercepts every later invocation. Only coroutine
    functions are wrapped: the schema decided sync-vs-async at registration and
    handing it a coroutine where it expects a plain return would break the
    call. Everything in the agent toolset is async by policy (CLAUDE.md), so in
    practice this skips nothing — it is a guard against a future sync tool
    silently breaking every run.
    """
    import inspect

    toolset = getattr(
        getattr(agent, "pydantic_ai_agent", None), "_function_toolset", None
    )
    tools = getattr(toolset, "tools", None) or {}
    if not tools:
        logger.warning(
            "Deep research: could not reach the agent toolset to audit it. "
            "tool_call_log will cover this module's closures only — do not "
            "read tool usage off it."
        )
        return

    for name, tool in tools.items():
        if name in already_audited:
            continue
        schema = getattr(tool, "function_schema", None)
        fn = getattr(schema, "function", None)
        if fn is None or getattr(fn, "_research_audited", False):
            continue
        if not inspect.iscoroutinefunction(fn):
            logger.warning(
                "Deep research: tool %r is not async, so it is left unaudited.", name
            )
            continue
        wrapped = _audited(report, name, fn)
        wrapped._research_audited = True
        schema.function = wrapped  # type: ignore[union-attr]


def _load_obligation_schema(report: ResearchReport, corpus: Any) -> ObligationSchema:
    """Read the corpus's obligation-card configuration out of its CAML article.

    The thresholds an obligation attaches at belong to the SUBJECT, not to the
    software: a Texas interconnection study is evaluated at a 25/50/75/100 MW
    ramp, an employment-law review at 50 and 250 employees. Those steps used to
    be a constant in the card schema, which made the card useful for exactly one
    project and silently refused any value outside that one project's plan.

    Configured where the corpus already describes itself — its ``Readme.CAML``
    — rather than in a settings column nobody discovers. An unconfigured corpus
    gets the unconstrained schema, which is the correct default: no scale means
    no membership check, and the card is still required to say where a
    phase-triggered obligation bites.

    Read through ``CorpusDocumentService`` with the report CREATOR's
    permissions, and failure-tolerant: a corpus with no article, an unreadable
    one, or a malformed marker all degrade to the default rather than failing
    the run.
    """
    from opencontractserver.corpuses.caml_intelligence import parse_component_props
    from opencontractserver.corpuses.services import CorpusDocumentService
    from opencontractserver.corpuses.services.description_cache import read_caml_body

    try:
        article = CorpusDocumentService.get_corpus_caml_articles(
            report.creator, corpus
        ).first()
        if article is None:
            return ObligationSchema()
        props = parse_component_props(read_caml_body(article), OBLIGATION_SCHEMA_MARKER)
    except Exception:  # pragma: no cover - configuration must never break a run
        logger.warning(
            "Deep research: could not read the obligation schema from corpus %s; "
            "using the unconstrained default.",
            getattr(corpus, "pk", "?"),
            exc_info=True,
        )
        return ObligationSchema()
    return ObligationSchema.from_caml_props(props)


def _describe_group_scale(
    report: ResearchReport, corpus: Any, group: Any
) -> str | None:
    """How much of the group the anchor corpus actually is.

    The agent could not have known. Across twenty runs of a group-scoped
    question it called ``search_across_group`` exactly ZERO times: it searched
    the anchor corpus, got hits, and stopped. The anchor held 2 documents; the
    group held 354, including the corpus named in the question. Told only that
    a wider tool exists, a model with results in hand has no reason to reach
    for it — told that it is looking at 2 documents out of 354, it does.

    Counted through ``CorpusGroupService`` with the report CREATOR's
    permissions, so the number describes what this run may actually read and
    never advertises a corpus the caller cannot see.
    """
    if group is None:
        return None
    from opencontractserver.corpuses.services import CorpusGroupService

    visible = CorpusGroupService.get_group_corpora_visible_to_user(
        report.creator, group
    )
    members = list(visible)
    if not members:
        return None
    counts = {c.pk: c.get_documents().count() for c in members}
    total = sum(counts.values())
    anchor = counts.get(corpus.pk, 0)
    if not total:
        return None
    return (
        f"{len(members)} corpora holding {total} documents in total. This "
        f"anchor corpus holds {anchor} of them"
    )


def _cited_passage_texts(annotation_ids: Sequence[int]) -> list[str]:
    """Raw text of the annotations a finding cites, for the attribution gate.

    Queried by primary key without a visibility filter, which is correct here
    and nowhere else: these ids have already been checked against the run's
    ``retrieved_annotation_ids`` accumulator, so every one of them came back
    from a permission-filtered retrieval performed for this run's own creator
    earlier in the same run. An id the caller invented never reaches this
    function. ``ResearchReportService.finalize`` loads its provenance rows the
    same way, for the same reason.
    """
    if not annotation_ids:
        return []
    return [
        text
        for text in Annotation.objects.filter(pk__in=list(annotation_ids)).values_list(
            "raw_text", flat=True
        )
        if text
    ]


def _audited(report, name: str, fn):
    """Wrap a research closure so every call lands in ``tool_call_log``.

    ``ResearchReportService.append_tool_call`` existed, was tested, and was
    never called from anywhere — so every finished report carried an empty
    audit log and the Run details tab had nothing to show. Without it the only
    evidence of what a run did is the findings it happened to record, which
    says nothing about what it searched for and discarded.

    Arguments are summarised, not stored verbatim: a retrieval query is useful
    for reconstructing intent, a 600-char passage per hit is not, and the log
    is loaded whole by the UI.

    It is also where the step-budget notice is attached, because this is the
    one place every tool call passes through and the log it writes is the
    running count. A string result carries the notice as trailing text; a list
    result carries it as a trailing ``{"note": …}`` row, the same shape
    ``search_across_group`` already uses to say hits were dropped. Attaching it
    to strings alone would leave a retrieval-heavy run — exactly the kind that
    runs out of steps — never warned.
    """
    import functools

    @functools.wraps(fn)
    async def _wrapped(*args, **kwargs):
        started = timezone.now()
        try:
            result = await fn(*args, **kwargs)
        except Exception as exc:  # audit the failure, then let it propagate
            await sync_to_async(ResearchReportService.append_tool_call)(
                report,
                {
                    "tool": name,
                    "args": _summarise_args(args, kwargs),
                    "error": f"{type(exc).__name__}: {exc}"[:300],
                    "at": started.isoformat(),
                },
            )
            raise
        calls = await sync_to_async(ResearchReportService.append_tool_call)(
            report,
            {
                "tool": name,
                "args": _summarise_args(args, kwargs),
                "result": _summarise_result(result),
                "at": started.isoformat(),
            },
        )
        notice = build_step_budget_notice(calls, report.max_steps)
        if notice:
            if isinstance(result, str):
                return f"{result}\n\n{notice}"
            if isinstance(result, list):
                return [*result, {"note": notice}]
        return result

    # Marked here, not only by ``_audit_default_toolset``. The closures built
    # in this module are handed to the factory as caller tools and land in the
    # SAME resolved toolset the default-tool pass walks, so without a marker
    # set at creation they were wrapped a second time: every closure call wrote
    # two audit rows, and the step-budget counter — which reads the log length
    # — ran at double speed, so a notice claiming "47 of 60" arrived at 24.
    _wrapped._research_audited = True  # type: ignore[attr-defined]
    return _wrapped


def _summarise_args(args: tuple, kwargs: dict) -> dict:
    """Short, readable record of what a tool was asked for."""
    out: dict[str, Any] = {}
    for key, value in list(kwargs.items())[:6]:
        if isinstance(value, str):
            out[key] = value[:160]
        elif isinstance(value, (int, float, bool)) or value is None:
            out[key] = value
        elif isinstance(value, (list, tuple)):
            out[key] = f"[{len(value)} items]"
        else:
            out[key] = type(value).__name__
    if args:
        out["_positional"] = len(args)
    return out


def _summarise_result(result: Any) -> str:
    """Shape of what came back, never the payload itself."""
    if result is None:
        return "None"
    if isinstance(result, str):
        return result[:200]
    if isinstance(result, (list, tuple)):
        return f"{len(result)} row(s)"
    if isinstance(result, dict):
        return f"dict({', '.join(list(result)[:6])})"
    return type(result).__name__


def _build_finding_card(
    *,
    as_of_date: str | None,
    applicable_process: str | None,
    authority_status: str | None,
    effective_interval_start: str | None,
    effective_interval_end: str | None,
    primary_authority_effective_from: str | None,
    confidence: str | None,
    unresolved_qualifications: list[str] | None,
    obligation: str | None = None,
    applicability: str | None = None,
    applies_at: list[float] | None = None,
    responsible_party: str | None = None,
    preparer: str | None = None,
    submitter: str | None = None,
    recipient: str | None = None,
    certifier: str | None = None,
    approval_date: str | None = None,
    effective_date: str | None = None,
    service_request_date: str | None = None,
    application_date: str | None = None,
    commencement_date: str | None = None,
    form_reference: str | None = None,
    material: bool = True,
    deadline: str | None = None,
    has_citations: bool = False,
    cited_passages: Sequence[str],
    schema: ObligationSchema,
) -> tuple[dict[str, Any] | None, str | None]:
    """Validate the optional card half of a finding.

    Returns ``(card, error)``. ``(None, None)`` means the caller supplied no
    card fields, which is fine — most findings are ordinary supporting claims.

    ``cited_passages`` has no default on purpose. It is the evidence the
    attribution gate reads, and a default would let a caller skip that gate by
    forgetting an argument — the one failure mode a guard must not have.

    The anachronism check is the one worth having. A run once cited the revised
    Planning Guide (effective 2026-07-11) as the authority for 2026-07-10:
    defensible-sounding, because the newer version describes the transition,
    but a document that took effect after the day in question cannot be what
    governed it. Prose hid that; a dated field does not.
    """
    regime_fields = {
        "as_of_date": as_of_date,
        "applicable_process": applicable_process,
        "authority_status": authority_status,
        "effective_interval_start": effective_interval_start,
        "effective_interval_end": effective_interval_end,
    }
    obligation_fields = {
        "obligation": obligation,
        "applicability": applicability,
        "responsible_party": responsible_party,
        "form_reference": form_reference,
        "deadline": deadline,
    }
    wants_regime = any(v for v in regime_fields.values())
    wants_obligation = any(v for v in obligation_fields.values())

    if not wants_regime and not wants_obligation:
        # Not a card at all — an ordinary supporting finding.
        return None, None

    if wants_regime and wants_obligation:
        # The two answer different questions and render differently; a merged
        # card would have to be read twice to find out which one it is.
        return None, (
            "a finding card is either a REGIME card (as_of_date, "
            "applicable_process, authority_status, interval) or an OBLIGATION "
            "card (obligation, responsible_party, form_reference, deadline) — "
            "not both. Record them as separate findings."
        )

    if wants_obligation:
        return _build_obligation_card(
            obligation=obligation,
            applicability=applicability,
            applies_at=applies_at,
            responsible_party=responsible_party,
            preparer=preparer,
            submitter=submitter,
            recipient=recipient,
            certifier=certifier,
            approval_date=approval_date,
            effective_date=effective_date,
            service_request_date=service_request_date,
            application_date=application_date,
            commencement_date=commencement_date,
            form_reference=form_reference,
            material=material,
            deadline=deadline,
            confidence=confidence,
            unresolved_qualifications=unresolved_qualifications,
            has_citations=has_citations,
            cited_passages=cited_passages,
            schema=schema,
        )

    supplied = dict(regime_fields, confidence=confidence)
    missing = [k for k in _CARD_REQUIRED if not supplied.get(k)]
    if missing:
        return None, (
            f"a regime finding card needs {', '.join(_CARD_REQUIRED)}; missing "
            f"{', '.join(missing)}. Supply them all or none."
        )

    normalised_confidence = (confidence or "").strip().upper()
    if normalised_confidence not in {"HIGH", "MEDIUM", "LOW"}:
        return None, f"confidence must be HIGH, MEDIUM or LOW (got {confidence!r})."

    qualifications = [q.strip() for q in (unresolved_qualifications or []) if q.strip()]
    if not qualifications:
        return None, (
            "unresolved_qualifications cannot be empty on a finding card. State "
            "what the public record does not settle. If you genuinely found "
            f"nothing unresolved, say so explicitly: {NOTHING_UNRESOLVED!r}. An "
            "empty list is indistinguishable from a field nobody filled in."
        )

    if (
        effective_interval_start
        and effective_interval_end
        and effective_interval_end <= effective_interval_start
    ):
        return None, (
            f"effective_interval_end {effective_interval_end!r} must be after "
            f"start {effective_interval_start!r}; the end is EXCLUSIVE."
        )

    if primary_authority_effective_from and as_of_date:
        if primary_authority_effective_from > as_of_date:
            return None, (
                f"the cited authority takes effect "
                f"{primary_authority_effective_from}, after the {as_of_date} it "
                "is cited for. A document effective later cannot be what "
                "governed that day — search for the version in force then "
                "(the superseded one) and cite that instead."
            )

    # Built through the schema so the field list has exactly one definition
    # (opencontractserver/enrichment/finding_cards.py). The guard clauses above
    # stay because their MESSAGES are what let an agent recover; a pydantic
    # type error usually just gets retried verbatim.
    return (
        RegimeCard(
            # The ``missing`` guard above rejects any falsy required field, so
            # these are non-None by the time we get here.
            as_of_date=cast("str", as_of_date),
            applicable_process=cast("str", applicable_process),
            authority_status=cast("str", authority_status),
            effective_interval_start=effective_interval_start,
            effective_interval_end=effective_interval_end,
            primary_authority_effective_from=primary_authority_effective_from,
            confidence=cast("Confidence", normalised_confidence),
            unresolved_qualifications=qualifications,
        ).model_dump(),
        None,
    )


def _send_completion_notification(
    report: ResearchReport, notification_type: str
) -> None:
    """Create + broadcast a notification for ``report``.

    Run sync — callers wrap in ``sync_to_async`` from async contexts.
    """
    from opencontractserver.notifications.models import Notification
    from opencontractserver.notifications.signals import (
        broadcast_notification_via_websocket,
    )

    notification = Notification.objects.create(
        recipient=report.creator,
        notification_type=notification_type,
        conversation=report.conversation,
        data={
            "report_id": str(report.pk),
            "report_slug": report.slug,
            "corpus_id": str(report.corpus_id),
            "title": report.title,
            "status": report.status,
        },
    )
    try:
        broadcast_notification_via_websocket(notification)
    except Exception:  # pragma: no cover - best-effort broadcast
        logger.exception("Failed to broadcast research notification")


def _insert_completion_chat_message(report: ResearchReport) -> None:
    """Drop a system ``ChatMessage`` into the originating conversation.

    No-op when the report wasn't kicked off from a chat. Run sync.
    """
    if not report.conversation_id:
        return
    from opencontractserver.conversations.models import (
        ChatMessage,
        MessageStateChoices,
        MessageTypeChoices,
    )

    status_label = {
        JobStatus.COMPLETED.value: "completed",
        JobStatus.FAILED.value: "failed",
        JobStatus.CANCELLED.value: "was cancelled",
    }.get(report.status, "finished")

    body = (
        f"Deep research **{status_label}**: *{report.title}*.\n\n"
        f"[Open report](/research/{report.slug})"
    )
    try:
        ChatMessage.objects.create(
            conversation_id=report.conversation_id,
            creator=report.creator,
            msg_type=MessageTypeChoices.SYSTEM,
            state=MessageStateChoices.COMPLETED,
            content=body,
            data={
                "research_report_id": str(report.pk),
                "research_report_slug": report.slug,
                "research_report_status": report.status,
            },
        )
    except Exception:  # pragma: no cover - chat insert is best-effort
        logger.exception("Failed to insert completion chat message")


# ---------------------------------------------------------------------------
# Celery entry point
# ---------------------------------------------------------------------------


def _resolve_time_limits() -> tuple[int, int]:
    return (
        getattr(settings, "DEEP_RESEARCH_SOFT_TIME_LIMIT", 60 * 30),
        getattr(settings, "DEEP_RESEARCH_HARD_TIME_LIMIT", 60 * 60),
    )


_SOFT_TIME_LIMIT, _HARD_TIME_LIMIT = _resolve_time_limits()


@shared_task(
    bind=True,
    max_retries=0,
    soft_time_limit=_SOFT_TIME_LIMIT,
    time_limit=_HARD_TIME_LIMIT,
)
def run_deep_research(self, research_report_id: int) -> dict:
    """Drive a long-running corpus-scoped research loop.

    Lifecycle: QUEUED -> RUNNING -> COMPLETED | FAILED | CANCELLED.
    On exception the row is marked FAILED with the exception text;
    cooperative cancellation transitions to CANCELLED while preserving
    partial findings. A notification + (optional) chat message land on
    every terminal state.
    """
    try:
        report = ResearchReport.objects.select_related(
            "corpus", "creator", "conversation", "corpus_group"
        ).get(pk=research_report_id)
    except ResearchReport.DoesNotExist:
        logger.warning("[DeepResearch] Report %s missing; skipping", research_report_id)
        return {"status": "missing", "report_id": research_report_id}

    if report.is_terminal:
        logger.info(
            "[DeepResearch] Report %s already terminal (%s); skipping",
            research_report_id,
            report.status,
        )
        return {"status": "skipped_terminal", "report_id": research_report_id}

    # A report already in RUNNING when a worker picks it up means a prior
    # worker died (or the task was redelivered) mid-run. Treat it as a resume:
    # preserve the original start time and tell the agent it is continuing.
    resuming = report.status == JobStatus.RUNNING.value
    if resuming:
        logger.info(
            "[DeepResearch] Report %s already RUNNING; resuming from durable "
            "plan/findings/memory",
            research_report_id,
        )
    ResearchReportService.mark_started(report, resuming=resuming)

    try:
        result = asyncio.run(_run_deep_research_async(report, resuming=resuming))
    except ResearchCancelled:
        ResearchReportService.mark_cancelled(report)
        _send_completion_notification(report, "RESEARCH_REPORT_CANCELLED")
        _insert_completion_chat_message(report)
        return {"status": "cancelled", "report_id": research_report_id}
    except SoftTimeLimitExceeded:
        # Celery's soft time limit fires before the hard kill; preserve
        # partial findings, surface as CANCELLED (not FAILED) so the user
        # sees a clean "we ran out of time" terminal rather than a stack
        # trace.
        logger.warning(
            "[DeepResearch] Report %s hit soft time limit; "
            "cancelling and preserving partial findings",
            research_report_id,
        )
        ResearchReportService.mark_cancelled(
            report,
            warning="Research stopped: exceeded the time budget for a "
            "single run. Partial findings (if any) are preserved.",
        )
        _send_completion_notification(report, "RESEARCH_REPORT_CANCELLED")
        _insert_completion_chat_message(report)
        return {"status": "cancelled_timeout", "report_id": research_report_id}
    except Exception as exc:
        logger.exception("[DeepResearch] Report %s failed", research_report_id)
        ResearchReportService.mark_failed(
            report,
            f"{type(exc).__name__}: {exc}\n\n{traceback.format_exc()[:2000]}",
        )
        _send_completion_notification(report, "RESEARCH_REPORT_FAILED")
        _insert_completion_chat_message(report)
        return {"status": "failed", "report_id": research_report_id, "error": str(exc)}

    _send_completion_notification(report, "RESEARCH_REPORT_COMPLETE")
    _insert_completion_chat_message(report)
    return result


@shared_task
def reap_stalled_research() -> dict:
    """Resume RUNNING reports whose progress clock has gone cold.

    A worker that dies mid-run leaves the row in RUNNING with a stale
    ``last_progress_at`` and no task in flight. This periodic reaper finds
    those and re-enqueues ``run_deep_research``; the resumed run rebuilds its
    context from the durable plan/findings/memory rather than starting over.
    The soft/hard time-limit path already produces a CANCELLED terminal, so a
    report that simply ran long is not eligible here — only ones with no
    progress past ``DEEP_RESEARCH_STUCK_THRESHOLD_SECONDS``.
    """
    stalled = ResearchReportService.list_stalled()
    resumed: list[int] = []
    # Single ``pk__in`` fetch rather than one ``get()`` per id: avoids an N+1
    # and is naturally robust to a report being deleted between ``list_stalled``
    # and here (it simply won't appear in the queryset).
    for report in ResearchReport.objects.filter(pk__in=stalled):
        if ResearchReportService.resume(report):
            resumed.append(report.pk)
    if resumed:
        logger.info("[DeepResearch] Reaped + resumed stalled reports: %s", resumed)
    elif stalled:
        # Stalled rows were found but all turned out terminal (resume() no-ops).
        # Log so the "reaper runs but nothing happens" case is diagnosable.
        logger.debug(
            "[DeepResearch] Found %d stalled report(s) but none were resumable "
            "(all terminal): %s",
            len(stalled),
            stalled,
        )
    return {"stalled": len(stalled), "resumed": resumed}


# ---------------------------------------------------------------------------
# Async loop
# ---------------------------------------------------------------------------


async def _run_deep_research_async(
    report: ResearchReport, *, resuming: bool = False
) -> dict:
    """Build the corpus agent and drive the loop.

    The scratchpad/plan/memory tool closures are bound to ``report`` here so
    they cannot escape this run. On ``resuming`` (or any run where prior
    durable state exists) the plan, a findings digest, and the memory index
    are folded into the system prompt so the agent recovers its bearings
    without re-deriving everything from scratch.
    """
    from pydantic_ai.usage import UsageLimits

    from opencontractserver.llms import agents

    corpus = report.corpus
    # Optional widening: when set, ``search_across_group`` fans retrieval over
    # the group's corpora that the report's CREATOR can read. Membership is
    # resolved per query inside the tool, so permissions are the caller's, not
    # the group owner's.
    group = report.corpus_group
    # Every corpus this run may draw a citable anchor from. Resolved once, with
    # the report CREATOR's permissions — never the group owner's — so a citation
    # can only ever come from something they may read.
    searchable_corpus_ids: list[int] = await sync_to_async(
        _resolve_searchable_corpus_ids
    )(report, corpus, group)
    corpus_title = corpus.title or ""
    corpus_description = getattr(corpus, "description", None) or None
    group_scale = await sync_to_async(_describe_group_scale)(report, corpus, group)
    obligation_schema = await sync_to_async(_load_obligation_schema)(report, corpus)

    # Rebuild the durable context surface (plan / findings digest / memory
    # index) and prime the system prompt with it. ``is_resume`` is True
    # whenever there is prior state to recover, even on a first delivery that
    # somehow has findings (defensive) — but we trust the task-level
    # ``resuming`` flag for the "you were interrupted" framing.
    digest = await sync_to_async(ResearchReportService.build_recovery_digest)(report)

    system_prompt = build_deep_research_system_prompt(
        task_description=report.prompt,
        corpus_title=corpus_title,
        corpus_description=corpus_description,
        max_steps=report.max_steps,
        plan=digest["plan"],
        findings_digest=digest["findings_digest"],
        memory_index=digest["memory_index"],
        resuming=resuming or digest["is_resume"],
        corpus_group_title=(group.title if group is not None else None),
        corpus_group_scale=group_scale,
        obligation_threshold_scale=obligation_schema.describe() or None,
    )

    # Mutable container so the closures can read the live citation
    # accumulator on ``PydanticAIDependencies`` once the agent has been
    # built (the dependency instance is created inside the factory).
    deps_ref: dict[str, Any] = {"deps": None}

    async def record_finding(
        claim: str,
        supporting_source_ids: list[int],
        section: str = "Findings",
        as_of_date: str | None = None,
        applicable_process: str | None = None,
        authority_status: str | None = None,
        effective_interval_start: str | None = None,
        effective_interval_end: str | None = None,
        primary_authority_effective_from: str | None = None,
        confidence: str | None = None,
        unresolved_qualifications: list[str] | None = None,
        obligation: str | None = None,
        applicability: str | None = None,
        applies_at: list[float] | None = None,
        responsible_party: str | None = None,
        preparer: str | None = None,
        submitter: str | None = None,
        recipient: str | None = None,
        certifier: str | None = None,
        approval_date: str | None = None,
        effective_date: str | None = None,
        service_request_date: str | None = None,
        application_date: str | None = None,
        commencement_date: str | None = None,
        form_reference: str | None = None,
        material: bool = True,
        deadline: str | None = None,
    ) -> str:
        """Append a structured finding to the working report.

        Every ``supporting_source_ids`` entry must be an annotation_id
        returned by a retrieval tool earlier in this run. Unknown IDs are
        rejected with an error string so the model can re-search.

        The optional arguments turn a finding into a **finding card** — the
        structured takeaway rendered above the report. Supply them when the
        claim is "process X governed over interval Y"; omit them for ordinary
        supporting findings. They travel together: give ``as_of_date``,
        ``applicable_process``, ``authority_status`` and ``confidence``
        together or none of them, because a half-filled card is worse than a
        plain finding.

        ``effective_interval_end`` is EXCLUSIVE. A process superseded on
        2026-07-11 has end "2026-07-11" and still governed all of 2026-07-10.

        ``unresolved_qualifications`` is required on a card and cannot be
        empty. Name what the public record does not settle; if you genuinely
        found nothing, say so explicitly. A blank list reads identically to a
        field nobody filled in.

        ``primary_authority_effective_from`` is the effective date of the
        document this card rests on. It must be on or before ``as_of_date``:
        a document that took effect after the day in question cannot be what
        governed it, even where the newer version describes the transition.
        Cite the superseded version instead.
        """
        deps = deps_ref["deps"]
        retrieved: set[int] = (
            set(deps.retrieved_annotation_ids) if deps is not None else set()
        )
        bad = [sid for sid in supporting_source_ids if sid not in retrieved]
        if bad:
            return (
                f"Error: source ids {bad} were not produced by any retrieval "
                "tool in this run. Issue a search query first so the IDs are "
                "captured, then re-call record_finding."
            )

        # Only an obligation-shaped call needs the passage text, so a plain
        # supporting finding still costs no extra query.
        cited_passages = (
            await sync_to_async(_cited_passage_texts)(supporting_source_ids)
            if (obligation or responsible_party)
            else []
        )

        card, card_error = _build_finding_card(
            as_of_date=as_of_date,
            applicable_process=applicable_process,
            authority_status=authority_status,
            effective_interval_start=effective_interval_start,
            effective_interval_end=effective_interval_end,
            primary_authority_effective_from=primary_authority_effective_from,
            confidence=confidence,
            unresolved_qualifications=unresolved_qualifications,
            obligation=obligation,
            applicability=applicability,
            applies_at=applies_at,
            responsible_party=responsible_party,
            preparer=preparer,
            submitter=submitter,
            recipient=recipient,
            certifier=certifier,
            approval_date=approval_date,
            effective_date=effective_date,
            service_request_date=service_request_date,
            application_date=application_date,
            commencement_date=commencement_date,
            form_reference=form_reference,
            material=material,
            deadline=deadline,
            has_citations=bool(supporting_source_ids),
            cited_passages=cited_passages,
            schema=obligation_schema,
        )
        if card_error:
            return f"Error: {card_error}"

        entry: dict[str, Any] = {
            "section": section,
            "claim": claim,
            "citations": list(supporting_source_ids),
            "created_at": timezone.now().isoformat(),
        }
        if card is not None:
            entry["card"] = card

        await sync_to_async(ResearchReportService.append_finding)(report, entry)
        await sync_to_async(ResearchReportService.cancel_if_requested)(report)
        shape = "finding card" if card is not None else "finding"
        return (
            f"Recorded {shape} under '{section}' with "
            f"{len(supporting_source_ids)} citation(s)."
        )

    async def find_citable_passages(
        phrase: str,
        document_id: int | None = None,
        limit: int = RESEARCH_CITABLE_PASSAGE_MAX_HITS,
    ) -> list[dict] | str:
        """Find corpus passages containing an exact phrase, ready to cite.

        Returns the real annotations whose text contains ``phrase``, tightest
        (most pinpoint) first. Every row carries a ``cite`` handle you can paste
        straight into the report body. Use this when you know the language you
        want but not its annotation id — it is far cheaper than re-searching for
        something citeable.

        On a group-scoped run this searches EVERY corpus in the group you
        may read, not just the anchor — so an anchor you can quote from a
        sibling corpus is reachable here, and a citation is not silently
        confined to the corpus the run started in.

        Pass ``document_id`` to search inside one document you have already
        identified, which is both faster and more precise than searching the
        whole corpus. ``limit`` is a MAXIMUM row count with a floor of 1 —
        passing 0 still returns a row, so use a more specific ``phrase`` rather
        than ``limit=0`` when you want nothing back. Section headers are never
        returned: the results are passages you can actually cite.
        """
        rows = await sync_to_async(_citable_passage_rows_across)(
            corpus_ids=searchable_corpus_ids,
            user=report.creator,
            phrase=phrase,
            document_id=document_id,
            limit=limit,
        )
        if not rows:
            # A miss returns guidance rather than ``[]`` — the model is most
            # likely to act on "try a shorter fragment" at exactly this moment,
            # and a bare empty list says nothing about what to do next. The
            # ``list[dict] | str`` return that implies is not a new shape for
            # the agent: ``PydanticAIToolWrapper`` already returns a plain
            # string from ANY tool on the operational-error path (issue #820),
            # whatever the tool's annotation says, and tool *outputs* are not
            # schema-validated the way inputs are.
            return (
                f"No corpus passage contains {phrase!r}. Try a shorter or "
                "differently-cased fragment, or use similarity_search."
            )
        # Register the anchors so record_finding / finalize accept them: this is
        # the same closed-citation-graph contract similarity_search satisfies by
        # appending to the accumulator.
        deps = deps_ref["deps"]
        if deps is not None:
            deps.retrieved_annotation_ids.extend(row["annotation_id"] for row in rows)
        return rows

    async def finalize_report(
        executive_summary: str,
        markdown_body: str,
    ) -> str:
        """Render the final markdown report and end the run.

        ``executive_summary`` is 2–4 sentences of top-line answer;
        ``markdown_body`` is the full report. They are DIFFERENT texts — do not
        pass the report as both — and neither should carry its own
        ``## Executive Summary`` or ``## Sources`` heading: the system adds
        those and renders the footnote table.

        Cite by writing the sentence and attaching ``<cite ids="1,2"/>`` after
        it; use ``<cite ids="1">…</cite>`` only to scope part of a sentence, and
        never restate the sentence inside the tag.
        """
        # Terminal, and enforced rather than merely documented. The prompt says
        # calling this ends the run, but nothing stopped a second call — and a
        # second call is not a no-op: it re-runs composition, so the stored
        # report becomes the LATER body while the warnings from both passes
        # accumulate. Observed live: one run finalized twice 25s apart and its
        # report carried each warning twice, with the two passes disagreeing
        # about how many sentences lost their citations (5, then 3). A reader
        # cannot tell that is one report composed twice rather than two
        # distinct problems.
        # The check and the composition run as ONE critical section
        # (``finalize_once`` holds the row lock across both). A plain
        # refresh-then-check was check-then-act: pydantic-ai can dispatch
        # parallel tool calls, so two finalize_report invocations could both
        # read RUNNING before either committed COMPLETED, and both compose —
        # reproducing the very double-composition this guard exists to stop.
        deps = deps_ref["deps"]
        retrieved = list(deps.retrieved_annotation_ids) if deps is not None else []
        finalized = await sync_to_async(ResearchReportService.finalize_once)(
            report,
            executive_summary=executive_summary,
            markdown_body=markdown_body,
            retrieved_annotation_ids=retrieved,
        )
        if not finalized:
            return (
                "Error: this report is already finalized and the run is over. "
                "Do not call finalize_report again — a second call would "
                "replace the report you just wrote."
            )
        return "Report finalized."

    # ------------------------------------------------------------------
    # Durable context-management closures (plan + memory)
    # ------------------------------------------------------------------
    async def update_research_plan(plan: str) -> str:
        """Replace your living high-level plan.

        The plan is re-injected at the top of the system prompt on every run,
        so it is the one note guaranteed to survive context compaction and a
        worker restart. Keep it current: restate the task, list sub-questions,
        track what is done and what is next.
        """
        stored = await sync_to_async(ResearchReportService.update_plan)(report, plan)
        await sync_to_async(ResearchReportService.cancel_if_requested)(report)
        return f"Plan updated ({len(stored)} chars stored)."

    async def get_research_plan() -> str:
        """Return your current saved plan (empty string if none yet)."""
        await sync_to_async(report.refresh_from_db)(fields=["plan"])
        return report.plan or "(no plan saved yet — call update_research_plan)"

    async def write_memory(key: str, content: str, mode: str = "replace") -> str:
        """Offload content to durable memory under ``key``.

        ``mode='replace'`` overwrites; ``mode='append'`` concatenates onto the
        existing value. Use this to remember quotes, per-document notes, and
        tallies that you do not want to lose to context compaction. Retrieve
        with read_memory / list_memory / search_memory.
        """
        try:
            result = await sync_to_async(ResearchReportService.write_memory)(
                report, key, content, mode=mode
            )
        except ResearchMemoryError as exc:
            return f"Error: {exc}"
        await sync_to_async(ResearchReportService.cancel_if_requested)(report)
        return (
            f"Wrote memory '{result['key']}' ({result['bytes']} chars; "
            f"{result['keys']} keys total)."
        )

    async def read_memory(key: str) -> str:
        """Return the full content stored under ``key``."""
        content = await sync_to_async(ResearchReportService.read_memory)(report, key)
        if content is None:
            return f"No memory entry under '{key}'. Use list_memory to see keys."
        return content

    async def list_memory() -> str:
        """List every memory key with its size and a short preview."""
        await sync_to_async(report.refresh_from_db)(fields=["memory"])
        index = await sync_to_async(ResearchReportService.memory_index)(report)
        if not index:
            return "Memory store is empty. Use write_memory to save notes."
        # Backtick-fence the key to match the system-prompt memory index
        # (build_recovery_digest renders ``- `key` (...)``) so the model sees
        # one consistent key format across the prompt and this tool's output.
        lines = [
            f"- `{item['key']}` ({item['bytes']} chars): {item['preview']}"
            for item in index
        ]
        return "Memory keys:\n" + "\n".join(lines)

    async def search_memory(query: str) -> str:
        """Grep across your memory entries and recorded findings (case-insensitive)."""
        hits = await sync_to_async(ResearchReportService.search_memory)(report, query)
        if not hits:
            return f"No matches for {query!r} in memory or findings."
        lines = [f"[{h['source']}:{h['key']}] {h['line']}" for h in hits]
        return f"Matches for {query!r}:\n" + "\n".join(lines)

    async def delete_memory(key: str) -> str:
        """Delete a memory entry to free room under the store caps."""
        removed = await sync_to_async(ResearchReportService.delete_memory)(report, key)
        # Match the other DB-write tools (update_research_plan/write_memory):
        # honour a cancellation request immediately after the write so a
        # cancelled job stops issuing further delete_memory calls.
        await sync_to_async(ResearchReportService.cancel_if_requested)(report)
        return f"Deleted memory '{key}'." if removed else f"No memory entry '{key}'."

    async def search_across_group(
        query: str,
        k: int = 3,
    ) -> list[dict] | str:
        """Search EVERY corpus in this run's Corpus Group, not just the anchor.

        Use this whenever the answer might live outside the anchor corpus —
        which, on a group-scoped run, is most of the time. ``similarity_search``
        cannot see past the anchor, so a question about a utility's own
        requirements, a statute, or a regulator's proceedings is usually
        unanswerable without this tool even when the anchor returns hits.

        Each hit carries an ``annotation_id`` registered as citable, exactly
        like ``similarity_search``, so IDs from here go straight into
        ``record_finding``.

        ``k`` is per corpus and capped, so prefer several narrow queries to one
        broad one.
        """
        if group is None:
            return (
                "Error: this run has no corpus group; use similarity_search "
                "over the anchor corpus instead."
            )
        from opencontractserver.llms.tools.core_tools.multi_corpus import (
            asearch_across_corpora,
        )

        payload = await asearch_across_corpora(
            query=query,
            corpus_group=group.slug,
            # Per corpus, so the caller's k multiplies by member count.
            k=max(1, min(int(k or 1), RESEARCH_GROUP_SEARCH_MAX_K_PER_CORPUS)),
            # The report's creator, never the group owner: retrieval is
            # permission-filtered per corpus inside the tool, so passing the
            # creator is what keeps a citation inside what they may read.
            user_id=report.creator_id,
        )

        deps = deps_ref["deps"]
        rows: list[dict] = []
        for corpus_entry in payload.get("results_by_corpus", []) or []:
            for hit in corpus_entry.get("results", []) or []:
                aid = hit.get("annotation_id")
                # Real annotation PKs are positive; synthetic match ids are
                # negative and must never enter the citation whitelist.
                if isinstance(aid, int) and aid > 0 and deps is not None:
                    deps.retrieved_annotation_ids.append(aid)
                rows.append(
                    {
                        "annotation_id": aid,
                        "corpus_title": corpus_entry.get("corpus_title"),
                        "document_title": hit.get("document_title"),
                        "canonical_key": hit.get("canonical_key"),
                        "authority_weight": hit.get("authority_weight"),
                        "effective_from": hit.get("effective_from"),
                        # Truncated like find_citable_passages. This tool fans
                        # over every visible corpus in the group, so full text
                        # per hit multiplies by the member count: the first
                        # cross-corpus run exhausted its token budget and
                        # finalised as a salvage composition. Use
                        # load_document_text on a specific hit when the full
                        # passage is actually needed.
                        "content": (hit.get("content") or "")[
                            :RESEARCH_CITABLE_PASSAGE_PREVIEW_CHARS
                        ],
                    }
                )
        if not rows:
            return f"No matches across the group for {query!r}."
        # Hard ceiling on one call's contribution to the history: a single
        # fan-out otherwise dominates every later model call.
        if len(rows) > RESEARCH_GROUP_SEARCH_MAX_ROWS:
            dropped = len(rows) - RESEARCH_GROUP_SEARCH_MAX_ROWS
            rows = rows[:RESEARCH_GROUP_SEARCH_MAX_ROWS]
            rows.append(
                {
                    "note": (
                        f"{dropped} further hit(s) omitted to protect the "
                        "context budget — narrow the query and search again."
                    )
                }
            )
        return rows

    # Tools the agent may call. Retrieval tools come from the corpus
    # agent's default toolset (filtered via ``restrict_tool_names``);
    # closures are appended so they take effect after wrapping.
    # ``list`` is invariant so the function-typed list needs a cast to the
    # wider ToolType list the API accepts.
    closure_specs: tuple[tuple[str, Any], ...] = (
        ("find_citable_passages", find_citable_passages),
        ("record_finding", record_finding),
        ("finalize_report", finalize_report),
        ("update_research_plan", update_research_plan),
        ("get_research_plan", get_research_plan),
        ("write_memory", write_memory),
        ("read_memory", read_memory),
        ("list_memory", list_memory),
        ("search_memory", search_memory),
        ("delete_memory", delete_memory),
        ("search_across_group", search_across_group),
    )
    closure_tools = cast(
        "list[str | Any | Callable[..., Any]]",
        [_audited(report, name, fn) for name, fn in closure_specs],
    )
    # Names this module has already wrapped. Passed to the default-toolset pass
    # by NAME because the factory re-wraps caller tools, so a marker attribute
    # on our wrapper is not reachable from the resolved toolset.
    closure_names = frozenset(name for name, _ in closure_specs)
    restrict = (
        set(DEEP_RESEARCH_READ_ONLY_TOOLS)
        | SCRATCHPAD_TOOL_NAMES
        | DEEP_RESEARCH_MEMORY_TOOL_NAMES
        | DEEP_RESEARCH_RETRIEVAL_CLOSURE_TOOLS
        | {"search_across_group"}
    )

    agent = await agents.for_corpus(
        corpus=corpus,
        user_id=report.creator_id,
        system_prompt=system_prompt,
        tools=closure_tools,
        streaming=False,
        skip_approval_gate=True,
        restrict_tool_names=restrict,
        similarity_top_k=getattr(settings, "DEEP_RESEARCH_SIMILARITY_TOP_K", 6),
        # Compact far earlier than a chat agent would. The message history is
        # resent on EVERY model call, so a research run's cumulative input
        # grows with the square of its tool calls: a 19-call run whose history
        # settled around 110k burned 2.1M cumulative tokens and died before
        # recording a single finding. Sized against the run's own budget rather
        # than the model's window — the default ratio of a 1M-window model puts
        # the trigger at 785k, which the run can never reach because it is
        # killed at its token cap first, so compaction would never once fire.
        compaction=CompactionConfig(
            threshold_ratio=DEEP_RESEARCH_COMPACTION_RATIO,
        ),
    )

    # Now that the agent has been built, expose its deps instance to the
    # closures so they can validate citation IDs against the live
    # retrieved_annotation_ids accumulator. ``agent_deps`` is an internal
    # attribute on PydanticAI*Agent — fine for an in-process closure ref.
    deps_ref["deps"] = getattr(agent, "agent_deps", None)

    _audit_default_toolset(report, agent, already_audited=closure_names)

    usage_limits = UsageLimits(
        request_limit=report.max_steps,
        request_tokens_limit=getattr(
            settings, "DEEP_RESEARCH_MAX_TOKENS_DEFAULT", 400_000
        ),
    )

    response = await agent.chat(
        "Execute the research task described in your instructions.",
        usage_limits=usage_limits,
    )

    # Refresh to see whether the agent actually called finalize_report.
    await sync_to_async(report.refresh_from_db)()

    if report.status != JobStatus.COMPLETED.value:
        # Salvage path: the run ended without an explicit finalize.
        retrieved = (
            list(deps_ref["deps"].retrieved_annotation_ids)
            if deps_ref["deps"] is not None
            else []
        )
        reason = _terminal_reason(response)
        salvage_body = _compose_salvage_body(report, response_text=response.content)
        # ``finalize_once``, not ``finalize``: the status check above is a
        # cheap early-out, not a guard. ``reap_stalled_research`` can have a
        # second worker on this same report, and it could reach a terminal
        # state between that check and this write — at which point a salvage
        # composition would overwrite the genuine outcome with a "the run
        # ended before the agent produced a final report" note. A refusal here
        # means the run has already ended some other way (finalized by the
        # other worker, cancelled, or failed), which is exactly the outcome we
        # want; the salvage is simply dropped.
        await sync_to_async(ResearchReportService.finalize_once)(
            report,
            executive_summary=(
                "**Note:** the run ended before the agent produced a final "
                f"report ({reason}). Below is a salvage composition built from "
                "the findings recorded so far."
            ),
            markdown_body=salvage_body,
            retrieved_annotation_ids=retrieved,
            # ``terminal_reason`` ONLY. The legacy ``budget_exhausted`` string
            # used to accompany it, and every warning is rendered verbatim to
            # the user (``ResearchReportDetail.tsx``) — so a run that simply
            # stopped, or blew the STEP budget, showed a chip claiming the
            # token budget was exhausted directly beside the reason saying
            # otherwise. Naming the ending is the whole point of this field;
            # keeping the string it replaced next to it re-creates the
            # ambiguity in the one surface a user actually reads.
            warnings=[f"terminal_reason: {reason}"],
        )
        await sync_to_async(report.refresh_from_db)()

    return {
        "status": "completed",
        "report_id": report.pk,
        "citations": len(report.citations or []),
        "findings": len(report.findings or []),
        "warnings": list(report.warnings or []),
    }


def _citable_passage_rows(
    *,
    corpus_id: int,
    user: Any,
    phrase: str,
    document_id: int | None,
    limit: int,
) -> list[dict]:
    """Shape ``AnnotationService.search_corpus_annotation_text`` hits for the LLM.

    Mirrors the ``similarity_search`` result shape (``annotation_id``,
    ``content``, ``document_id``, ``page``, ``label``) so the agent handles both
    retrieval tools identically, and adds the ready-to-paste ``cite`` handle
    that issue #2201 asks for — the point being that the agent attributes what
    it just read instead of re-hunting for something citeable. Sync; the closure
    wraps it in ``sync_to_async``.

    ``document_id`` can legitimately be ``None``: a structural annotation is
    shared across the documents of its ``structural_set`` rather than owned by
    one, so it has no single document to name. Such a row still carries a usable
    ``annotation_id``/``cite`` handle, so it is returned with an empty
    ``document_title`` rather than dropped. It is a rare shape here — the header
    labels most structural rows carry are excluded below — but the row builder
    must not assume a document is present.
    """
    from opencontractserver.annotations.services import AnnotationService

    annotations = AnnotationService.search_corpus_annotation_text(
        corpus_id=corpus_id,
        user=user,
        phrase=phrase,
        document_id=document_id,
        # Never offer a bare section header as a citable passage — that is the
        # #2180 failure this tool exists to make unnecessary. Keyed on the
        # LABEL, not Annotation.structural; see the constant's docstring. The
        # _VARIANTS spelling is what the SQL side needs: ``iexact`` folds case
        # but not separators, so passing the base set would let a label stored
        # as ``Section_Header`` through the filter while the warning path — which
        # does fold separators — still flagged it.
        exclude_label_texts=RESEARCH_HEADER_ANCHOR_LABEL_VARIANTS,
        # Clamp whatever the model asked for to [1, ceiling]. The ceiling stops
        # a common phrase dumping a corpus-worth of annotations into the
        # context; the floor is here rather than in the service because it is a
        # UX rule of THIS tool, not of annotation search — a model that omits
        # ``limit`` or sends 0 still gets its tightest anchor, and the only
        # empty result it ever sees is a genuine miss, which the caller answers
        # with guidance instead of a bare empty list. The service treats
        # ``limit`` as an ordinary cap and would honour the 0.
        limit=max(1, min(int(limit or 0), RESEARCH_CITABLE_PASSAGE_MAX_HITS)),
    )
    return [
        {
            "annotation_id": ann.pk,
            "cite": f'<cite ids="{ann.pk}"/>',
            "document_id": ann.document_id,
            "document_title": (
                getattr(ann.document, "title", "") if ann.document_id else ""
            ),
            "page": ann.page,
            "label": getattr(ann.annotation_label, "text", None),
            "content": (ann.raw_text or "")[:RESEARCH_CITABLE_PASSAGE_PREVIEW_CHARS],
        }
        for ann in annotations
    ]


def _resolve_searchable_corpus_ids(report, corpus, group) -> list[int]:
    """Corpora this run may draw a citable anchor from.

    Resolved with the report CREATOR's permissions — never the group owner's —
    so a citation can only ever come from something they may read. Sync: the
    queryset is evaluated here and the caller wraps it.
    """
    if group is None:
        return [corpus.pk]
    from opencontractserver.corpuses.services import CorpusGroupService

    member_ids = list(
        CorpusGroupService.get_group_corpora_visible_to_user(report.creator, group)
        .order_by("pk")
        .values_list("pk", flat=True)
    )
    # Anchor first, de-duplicated: it is usually a member too.
    return list(dict.fromkeys([corpus.pk, *member_ids]))


def _citable_passage_rows_across(
    *,
    corpus_ids: list[int],
    user: Any,
    phrase: str,
    document_id: int | None,
    limit: int,
) -> list[dict]:
    """Citable anchors from every corpus the run may search, tightest first.

    ``find_citable_passages`` was scoped to the anchor corpus, so on a
    group-scoped run the agent could see a sibling corpus through
    ``search_across_group`` and still never obtain a quotable anchor from it —
    every citation it kept resolved to the anchor corpus by construction. That
    reads as "the group was not used" when the group was used and simply could
    not be cited.

    Each corpus is searched with the caller's own permissions (the underlying
    service filters per corpus), then results are merged shortest-passage-first
    so the tightest pinpoint wins regardless of which corpus produced it.
    """
    rows: list[dict] = []
    for corpus_id in corpus_ids:
        rows.extend(
            _citable_passage_rows(
                corpus_id=corpus_id,
                user=user,
                phrase=phrase,
                document_id=document_id,
                limit=limit,
            )
        )
    # "Tightest first" has to be re-established across the merged set: each
    # corpus ordered its own hits, and concatenating them would rank by corpus.
    rows.sort(key=lambda row: len(row.get("content") or ""))
    return rows[: max(1, min(int(limit or 0), RESEARCH_CITABLE_PASSAGE_MAX_HITS))]


#: How much of a provider error survives into the stored terminal reason. The
#: first clamp was 200 chars, which cut a 400 from OpenAI mid-sentence and
#: dropped the half that mattered: "...not supported for gpt-5.6-luna in
#: /v1/chat/completions. To use function tools," — the remedy was in the words
#: that got trimmed. An error message earns its length in its tail.
TERMINAL_REASON_MAX_CHARS = 600

#: Substrings pydantic-ai puts in a ``UsageLimitExceeded`` message. Checked
#: tokens-first, because ``request_tokens_limit`` contains ``request_`` too.
_TERMINAL_TOKEN_LIMIT_MARKER = "tokens_limit"
_TERMINAL_STEP_LIMIT_MARKER = "request_limit"


def _terminal_reason(response: Any) -> str:
    """Name what ended a run that never called ``finalize_report``.

    Every such run used to be recorded as the single warning
    ``budget_exhausted``, which reads as "ran out of context" and is what the
    string was taken to mean. It covers three unrelated endings — the token
    budget, the STEP budget (``request_limit = max_steps``), and an agent that
    simply stopped — and the report kept no evidence of which. A run that made
    exactly 60 of 60 permitted model requests was diagnosed as a context
    runaway on that basis, and the compaction ratio was tuned in response to a
    limit it cannot move.

    ``chat()`` swallows the framework exception and returns it as response
    metadata (it never raises, so there is no traceback in the worker log
    either); this reads it back out.
    """
    meta = getattr(response, "metadata", None) or {}
    error = str(meta.get("error") or "").strip()
    if not error:
        return "the agent stopped without calling finalize_report"
    if _TERMINAL_TOKEN_LIMIT_MARKER in error:
        return f"token budget exhausted — {error}"[:TERMINAL_REASON_MAX_CHARS]
    if _TERMINAL_STEP_LIMIT_MARKER in error:
        return f"step budget exhausted — {error}"[:TERMINAL_REASON_MAX_CHARS]
    error_type = str(meta.get("error_type") or "").strip()
    return f"{error_type or 'error'} — {error}"[:TERMINAL_REASON_MAX_CHARS]


def _compose_salvage_body(report: ResearchReport, *, response_text: str) -> str:
    """Build a minimal markdown body from recorded findings.

    Used when the agent never called ``finalize_report``. Concatenates
    findings by section and emits self-closing cite markers so the regular
    citation post-processor can still produce footnotes — the same placeholder
    form the system prompt asks the agent for, so salvage and normal bodies
    render identically.
    """
    findings = list(report.findings or [])
    if not findings:
        if response_text:
            return response_text
        # Names the ending generically, because this body is composed for every
        # non-finalize ending — not only a budget overrun. The executive summary
        # written alongside it carries the specific ``terminal_reason``; saying
        # "the budget was exhausted" here would contradict it for a run that
        # simply stopped, which is the ambiguity ``terminal_reason`` exists to
        # end.
        return "_The run ended before any findings were recorded._"

    by_section: dict[str, list[dict]] = {}
    for f in findings:
        section = f.get("section") or "Findings"
        by_section.setdefault(section, []).append(f)

    parts: list[str] = []
    for section, items in by_section.items():
        parts.append(f"## {section}")
        for item in items:
            claim = (item.get("claim") or "").strip()
            cites = ",".join(str(c) for c in (item.get("citations") or []) if c)
            if cites:
                parts.append(f'- {claim} <cite ids="{cites}"/>')
            else:
                parts.append(f"- {claim}")
    return "\n\n".join(parts)
