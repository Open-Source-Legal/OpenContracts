"""Chat-facing tool for kicking off a deep-research job.

Lives outside ``core_tools/`` because it orchestrates across apps
(creates a ``ResearchReport`` row + enqueues a Celery task) — same
placement convention as :mod:`delegation_tools` and
:mod:`moderation_tools`.

The kickoff is exposed to the corpus chat agent as
``start_deep_research``. When the LLM calls it, the tool creates the
report, enqueues the long-running task, and returns a short
confirmation string so the chat turn can end gracefully.
"""

from __future__ import annotations

import logging

from asgiref.sync import sync_to_async

from opencontractserver.corpuses.models import Corpus
from opencontractserver.llms.tools.tool_factory import CoreTool
from opencontractserver.research.services.research_reports import (
    ConcurrentResearchInProgress,
    ResearchReportService,
)
from opencontractserver.types.enums import JobStatus

logger = logging.getLogger(__name__)


async def astart_deep_research(
    task_description: str,
    title: str | None = None,
    *,
    corpus_id: int,
    user_id: int,
    conversation_id: int | None = None,
) -> str:
    """Kick off a long-running deep-research job over the current corpus.

    Use this when the user asks for a thorough investigation that needs
    many tool calls and a written report (with citations). The research
    agent runs asynchronously — typical wall-clock is 5-30 minutes.

    Args:
        task_description: The natural-language research task the user
            wants you to investigate. Be specific; this becomes the
            agent's instructions.
        title: Optional short title for the report. Defaults to a
            slug derived from the task.
    """
    user, corpus = await sync_to_async(_load_user_and_corpus)(user_id, corpus_id)

    if user is None or corpus is None:
        return (
            "Error: could not start research — the corpus or user could not "
            "be resolved. Ask the user to retry from inside the corpus chat."
        )

    conversation = None
    originating_message = None
    if conversation_id is not None:
        conversation, originating_message = await sync_to_async(
            _load_conversation_context
        )(conversation_id, user_id)

    try:
        report = await sync_to_async(ResearchReportService.start)(
            user=user,
            corpus=corpus,
            prompt=task_description,
            title=title,
            conversation=conversation,
            originating_message=originating_message,
        )
    except ConcurrentResearchInProgress as exc:
        return f"Could not start: {exc}"
    except PermissionError as exc:
        return f"Could not start: {exc}"

    return (
        f"Deep research started for '{report.title}' (job #{report.pk}). "
        "I'll keep working on it — you'll get a notification (and a message "
        "back in this chat) when the report is ready. Typical wall-clock is "
        "5-30 minutes."
    )


def _load_user_and_corpus(user_id: int, corpus_id: int):
    from django.contrib.auth import get_user_model

    user = get_user_model().objects.filter(pk=user_id).first()
    corpus = Corpus.objects.filter(pk=corpus_id).first()
    return user, corpus


def _load_conversation_context(conversation_id: int, user_id: int):
    """Resolve the conversation + the most recent HUMAN message by the user.

    Returns ``(conversation, message)`` tuples — either may be ``None``.
    The originating message linkage is best-effort.
    """
    from opencontractserver.conversations.models import (
        ChatMessage,
        Conversation,
        MessageTypeChoices,
    )

    conversation = Conversation.objects.filter(pk=conversation_id).first()
    if conversation is None:
        return None, None
    message = (
        ChatMessage.objects.filter(
            conversation_id=conversation_id,
            creator_id=user_id,
            msg_type=MessageTypeChoices.HUMAN,
        )
        .order_by("-created")
        .first()
    )
    return conversation, message


async def acheck_deep_research_status(
    *,
    corpus_id: int,
    user_id: int,
) -> str:
    """Check the status of deep-research jobs on the current corpus.

    Use this when the user asks whether their research is finished, how a
    running research job is progressing, or wants the link to a completed
    report. Returns a short status summary (status, step progress, and the
    report link) for the user's most recent research jobs on this corpus.
    """
    return await sync_to_async(_summarize_recent_reports)(user_id, corpus_id)


def _summarize_recent_reports(user_id: int, corpus_id: int, limit: int = 5) -> str:
    """Build a compact, LLM-friendly status summary. Runs sync."""
    user, corpus = _load_user_and_corpus(user_id, corpus_id)
    if user is None or corpus is None:
        return (
            "Error: could not check research status — the corpus or user "
            "could not be resolved. Ask the user to retry from inside the "
            "corpus chat."
        )

    reports = ResearchReportService.list_recent_for_corpus(
        user=user, corpus=corpus, limit=limit
    )
    if not reports:
        return (
            "No deep-research jobs found for this corpus yet. Use the "
            "start_deep_research tool when the user asks for a thorough "
            "investigation or a written report."
        )

    lines = ["Deep-research jobs on this corpus (most recent first):"]
    for idx, report in enumerate(reports, start=1):
        status = report.status
        if status == JobStatus.RUNNING.value:
            detail = f" — in progress, step {report.step_count}/{report.max_steps}"
        elif status == JobStatus.QUEUED.value:
            detail = " — queued, waiting to start"
        else:
            secs = report.duration_seconds
            if secs is not None:
                # Mirror the frontend formatResearchDuration() helper: omit the
                # minutes segment when it would be "0m" so a sub-minute run reads
                # "42s", not "0m 42s". Keeps LLM-facing text aligned with the UI.
                mins, rem = divmod(int(secs), 60)
                human = f"{mins}m {rem}s" if mins > 0 else f"{rem}s"
                detail = f" — finished in {human}"
            else:
                detail = ""
        link = f"/research/{report.slug}" if report.slug else "(report link pending)"
        lines.append(f'{idx}. "{report.title}" [{status}]{detail}. Report: {link}')
    return "\n".join(lines)


# Public CoreTool entry — register or include in tool lists directly.
start_deep_research_tool: CoreTool = CoreTool.from_function(
    astart_deep_research,
    name="start_deep_research",
    description=(
        "Kick off a long-running, autonomous deep-research job over the "
        "current corpus. The research agent crawls the corpus with "
        "read-only retrieval tools, accumulates findings with citations, "
        "and writes a markdown report. Returns a job ID. The user will "
        "be notified via the notifications panel and a message in this "
        "chat when the report is ready (5-30 minutes typical). Use this "
        "ONLY when the user asks for a thorough multi-step investigation "
        "or a written research report — not for quick lookups."
    ),
    parameter_descriptions={
        "task_description": (
            "Full natural-language description of the research the user "
            "wants done. The deep-research agent uses this as its task "
            "instructions, so be specific."
        ),
        "title": "Optional short title for the report (defaults to a slug of the task).",
    },
    requires_corpus=True,
    requires_write_permission=True,
)


check_deep_research_status_tool: CoreTool = CoreTool.from_function(
    acheck_deep_research_status,
    name="check_deep_research_status",
    description=(
        "Check the status of deep-research jobs on the current corpus. Use "
        "this when the user asks whether their research is finished, how a "
        "running job is progressing, or wants the link to a completed "
        "report. Returns a short summary (status, step progress, and the "
        "report link) for the user's most recent research jobs on this "
        "corpus. Read-only — does not start anything."
    ),
    requires_corpus=True,
    requires_write_permission=False,
)
