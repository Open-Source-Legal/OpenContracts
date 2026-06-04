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
from typing import Any, Callable, cast

from asgiref.sync import sync_to_async
from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
from django.conf import settings
from django.utils import timezone

from opencontractserver.research.constants import (
    DEEP_RESEARCH_MEMORY_TOOL_NAMES,
    DEEP_RESEARCH_READ_ONLY_TOOLS,
    build_deep_research_system_prompt,
)
from opencontractserver.research.models import ResearchReport
from opencontractserver.research.services.research_reports import (
    ResearchCancelled,
    ResearchMemoryError,
    ResearchReportService,
)
from opencontractserver.types.enums import JobStatus

logger = logging.getLogger(__name__)


SCRATCHPAD_TOOL_NAMES = {"record_finding", "finalize_report"}


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
            "corpus", "creator", "conversation"
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
    corpus_title = corpus.title or ""
    corpus_description = getattr(corpus, "description", None) or None

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
    )

    # Mutable container so the closures can read the live citation
    # accumulator on ``PydanticAIDependencies`` once the agent has been
    # built (the dependency instance is created inside the factory).
    deps_ref: dict[str, Any] = {"deps": None}

    async def record_finding(
        claim: str,
        supporting_source_ids: list[int],
        section: str = "Findings",
    ) -> str:
        """Append a structured finding to the working report.

        Every ``supporting_source_ids`` entry must be an annotation_id
        returned by a retrieval tool earlier in this run. Unknown IDs are
        rejected with an error string so the model can re-search.
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

        await sync_to_async(ResearchReportService.append_finding)(
            report,
            {
                "section": section,
                "claim": claim,
                "citations": list(supporting_source_ids),
                "created_at": timezone.now().isoformat(),
            },
        )
        await sync_to_async(ResearchReportService.cancel_if_requested)(report)
        return (
            f"Recorded finding under '{section}' with "
            f"{len(supporting_source_ids)} citation(s)."
        )

    async def finalize_report(
        executive_summary: str,
        markdown_body: str,
    ) -> str:
        """Render the final markdown report and end the run.

        ``markdown_body`` should use ``<cite ids="a,b">claim</cite>``
        placeholders for citations; the system converts those to footnote
        markers and builds the Sources section.
        """
        deps = deps_ref["deps"]
        retrieved = list(deps.retrieved_annotation_ids) if deps is not None else []
        await sync_to_async(ResearchReportService.finalize)(
            report,
            executive_summary=executive_summary,
            markdown_body=markdown_body,
            retrieved_annotation_ids=retrieved,
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

    # Tools the agent may call. Retrieval tools come from the corpus
    # agent's default toolset (filtered via ``restrict_tool_names``);
    # closures are appended so they take effect after wrapping.
    # ``list`` is invariant so the function-typed list needs a cast to the
    # wider ToolType list the API accepts.
    closure_tools = cast(
        "list[str | Any | Callable[..., Any]]",
        [
            record_finding,
            finalize_report,
            update_research_plan,
            get_research_plan,
            write_memory,
            read_memory,
            list_memory,
            search_memory,
            delete_memory,
        ],
    )
    restrict = (
        set(DEEP_RESEARCH_READ_ONLY_TOOLS)
        | SCRATCHPAD_TOOL_NAMES
        | DEEP_RESEARCH_MEMORY_TOOL_NAMES
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
    )

    # Now that the agent has been built, expose its deps instance to the
    # closures so they can validate citation IDs against the live
    # retrieved_annotation_ids accumulator. ``agent_deps`` is an internal
    # attribute on PydanticAI*Agent — fine for an in-process closure ref.
    deps_ref["deps"] = getattr(agent, "agent_deps", None)

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
        # Salvage path: budget exhausted without an explicit finalize.
        retrieved = (
            list(deps_ref["deps"].retrieved_annotation_ids)
            if deps_ref["deps"] is not None
            else []
        )
        salvage_body = _compose_salvage_body(report, response_text=response.content)
        await sync_to_async(ResearchReportService.finalize)(
            report,
            executive_summary=(
                "**Note:** the research budget was exhausted before the agent "
                "produced a final report. Below is a salvage composition built "
                "from the findings recorded so far."
            ),
            markdown_body=salvage_body,
            retrieved_annotation_ids=retrieved,
            warnings=["budget_exhausted"],
        )
        await sync_to_async(report.refresh_from_db)()

    return {
        "status": "completed",
        "report_id": report.pk,
        "citations": len(report.citations or []),
        "findings": len(report.findings or []),
        "warnings": list(report.warnings or []),
    }


def _compose_salvage_body(report: ResearchReport, *, response_text: str) -> str:
    """Build a minimal markdown body from recorded findings.

    Used when the agent never called ``finalize_report``. Concatenates
    findings by section and emits placeholder cite tags so the regular
    citation post-processor can still produce footnotes.
    """
    findings = list(report.findings or [])
    if not findings:
        if response_text:
            return response_text
        return "_No findings recorded before the research budget was exhausted._"

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
                parts.append(f'- <cite ids="{cites}">{claim}</cite>')
            else:
                parts.append(f"- {claim}")
    return "\n\n".join(parts)
