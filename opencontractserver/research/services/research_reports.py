"""Service layer for :class:`ResearchReport`.

All ResearchReport mutations and lifecycle transitions go through this
class. Per CLAUDE.md rule 7, callers with user context (GraphQL,
Celery, chat tools) MUST NOT touch ``ResearchReport.objects`` directly.
"""

from __future__ import annotations

import logging
import re
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from opencontractserver.research.constants import (
    DEFAULT_MAX_STEPS_FALLBACK,
    MAX_RESEARCH_STEPS_CEILING,
)
from opencontractserver.research.models import ResearchReport
from opencontractserver.shared.services.base import BaseService
from opencontractserver.types.enums import JobStatus, PermissionTypes

logger = logging.getLogger(__name__)


class ResearchCancelled(Exception):
    """Raised inside the agent loop when the user has requested cancel.

    The Celery task boundary catches this and transitions the report to
    :class:`JobStatus.CANCELLED` while preserving any partial findings.
    """


class ConcurrentResearchInProgress(Exception):
    """Raised when a user tries to start a second concurrent job for the
    same corpus inside the concurrency-guard window."""


class ResearchReportService(BaseService):
    """Canonical entry point for ResearchReport CRUD + lifecycle."""

    # ------------------------------------------------------------------
    # Kickoff
    # ------------------------------------------------------------------
    @classmethod
    def start(
        cls,
        *,
        user: Any,
        corpus: Any,
        prompt: str,
        title: str | None = None,
        conversation: Any = None,
        originating_message: Any = None,
        max_steps: int | None = None,
        request: Any = None,
    ) -> ResearchReport:
        """Create a QUEUED ResearchReport and enqueue the Celery task.

        Raises:
            PermissionError: when ``user`` lacks READ on ``corpus``.
            ConcurrentResearchInProgress: when a non-terminal report for
                the same ``(user, corpus)`` exists inside the configured
                concurrency-guard window.
        """
        error = cls.require_permission(
            corpus, user, PermissionTypes.READ, request=request
        )
        if error:
            raise PermissionError(error)

        default_max_steps: int = getattr(
            settings, "DEEP_RESEARCH_DEFAULT_MAX_STEPS", DEFAULT_MAX_STEPS_FALLBACK
        )
        resolved_max_steps: int = (
            int(max_steps) if max_steps is not None else default_max_steps
        )
        # Hard ceiling so a user-supplied ``max_steps`` can't burn an
        # unbounded LLM budget. ``max(1, ...)`` keeps a floor so callers
        # can't queue a zero-budget run that would no-op immediately.
        resolved_max_steps = max(1, min(resolved_max_steps, MAX_RESEARCH_STEPS_CEILING))
        resolved_title = title or _derive_title_from_prompt(prompt)

        guard_seconds = getattr(
            settings, "DEEP_RESEARCH_CONCURRENCY_GUARD_SECONDS", 3600
        )
        cutoff = timezone.now() - timedelta(seconds=guard_seconds)
        active_states = (JobStatus.QUEUED.value, JobStatus.RUNNING.value)

        # Single atomic block + ``select_for_update`` so the
        # concurrency-guard check and the row insert are serialised
        # against concurrent ``start()`` calls for the same
        # ``(creator, corpus)`` — closes the TOCTOU window where two
        # requests can both pass ``.exists()`` before either creates a
        # row. The ``select_for_update`` here locks at most a single row
        # (the most recent active report for this user+corpus), so it is
        # cheap even on a hot corpus.
        with transaction.atomic():
            active_for_pair = (
                ResearchReport.objects.select_for_update()
                .filter(
                    creator=user,
                    corpus=corpus,
                    status__in=active_states,
                    created__gte=cutoff,
                )
                .order_by("-created")
                .first()
            )
            if active_for_pair is not None:
                raise ConcurrentResearchInProgress(
                    "You already have a research job queued or running on "
                    "this corpus. Wait for it to finish or cancel it before "
                    "starting another."
                )
            report = ResearchReport.objects.create(
                creator=user,
                corpus=corpus,
                prompt=prompt,
                title=resolved_title,
                status=JobStatus.QUEUED.value,
                max_steps=resolved_max_steps,
                conversation=conversation,
                originating_message=originating_message,
            )

            # Enqueue the Celery task. Local import keeps the service free
            # of a hard dependency on Celery / agent code at import time
            # (so a bare ``python manage.py shell`` can construct rows).
            from opencontractserver.tasks.research_tasks import run_deep_research

            transaction.on_commit(lambda: run_deep_research.delay(report.pk))

        cls.log_action("Started", report, user, corpus_id=corpus.pk)
        return report

    # ------------------------------------------------------------------
    # Lifecycle transitions
    # ------------------------------------------------------------------
    @classmethod
    def mark_started(cls, report: ResearchReport) -> None:
        now = timezone.now()
        report.status = JobStatus.RUNNING.value
        report.started_at = now
        report.last_progress_at = now
        report.error_message = ""
        report.save(
            update_fields=[
                "status",
                "started_at",
                "last_progress_at",
                "error_message",
                "modified",
            ]
        )

    @classmethod
    def mark_progress(cls, report: ResearchReport) -> None:
        report.last_progress_at = timezone.now()
        report.save(update_fields=["last_progress_at", "modified"])

    @classmethod
    def mark_completed(
        cls,
        report: ResearchReport,
        *,
        warnings: list[str] | None = None,
        model_usage: dict | None = None,
    ) -> None:
        report.status = JobStatus.COMPLETED.value
        report.completed_at = timezone.now()
        report.last_progress_at = report.completed_at
        if warnings:
            report.warnings = list(report.warnings or []) + warnings
        if model_usage:
            report.model_usage = {**(report.model_usage or {}), **model_usage}
        report.save(
            update_fields=[
                "status",
                "completed_at",
                "last_progress_at",
                "warnings",
                "model_usage",
                "modified",
            ]
        )

    @classmethod
    def mark_failed(cls, report: ResearchReport, error: str) -> None:
        report.status = JobStatus.FAILED.value
        report.completed_at = timezone.now()
        report.last_progress_at = report.completed_at
        report.error_message = (error or "")[:4000]
        report.save(
            update_fields=[
                "status",
                "completed_at",
                "last_progress_at",
                "error_message",
                "modified",
            ]
        )

    @classmethod
    def mark_cancelled(
        cls,
        report: ResearchReport,
        *,
        warning: str | None = None,
    ) -> None:
        report.status = JobStatus.CANCELLED.value
        report.completed_at = timezone.now()
        report.last_progress_at = report.completed_at
        update_fields = ["status", "completed_at", "last_progress_at", "modified"]
        if warning:
            # Append to the warnings JSON sidecar so the UI can surface
            # *why* the report stopped (e.g. soft-time-limit) without
            # losing partial findings to a misleading FAILED label.
            report.warnings = list(report.warnings or []) + [warning]
            update_fields.append("warnings")
        report.save(update_fields=update_fields)

    # ------------------------------------------------------------------
    # Scratchpad writes (called from agent-bound tool closures)
    # ------------------------------------------------------------------
    @classmethod
    def append_finding(cls, report: ResearchReport, finding: dict) -> None:
        """Append a structured finding and bump ``last_progress_at``.

        Refreshes the row first to avoid stomping a concurrent
        ``cancel_requested`` flip.
        """
        report.refresh_from_db(fields=["findings", "step_count", "cancel_requested"])
        findings = list(report.findings or [])
        findings.append(finding)
        report.findings = findings
        report.step_count = (report.step_count or 0) + 1
        report.last_progress_at = timezone.now()
        report.save(
            update_fields=[
                "findings",
                "step_count",
                "last_progress_at",
                "modified",
            ]
        )

    @classmethod
    def append_tool_call(cls, report: ResearchReport, entry: dict) -> None:
        """Append a tool-call audit entry. Cheap; does not bump progress."""
        report.refresh_from_db(fields=["tool_call_log"])
        log = list(report.tool_call_log or [])
        log.append(entry)
        report.tool_call_log = log
        report.save(update_fields=["tool_call_log", "modified"])

    # ------------------------------------------------------------------
    # Finalize (terminal write from inside the loop)
    # ------------------------------------------------------------------
    @classmethod
    def finalize(
        cls,
        report: ResearchReport,
        *,
        executive_summary: str,
        markdown_body: str,
        retrieved_annotation_ids: list[int],
        warnings: list[str] | None = None,
    ) -> None:
        """Render the final report and mark it COMPLETED.

        Composes ``executive_summary`` + ``markdown_body`` + a ``## Sources``
        footnote section. Citation post-processing converts placeholder
        ``<cite ids="1,2">claim</cite>`` spans into ``[^n]`` footnote
        markers and builds the structured ``citations`` table.

        ``retrieved_annotation_ids`` is the union of annotation IDs the
        retrieval tools surfaced during this run (the
        :attr:`PydanticAIDependencies.retrieved_annotation_ids` accumulator).
        Used to constrain the ``source_annotations`` M2M to the ones
        actually cited by ``arecord_finding`` (intersection).
        """
        from opencontractserver.annotations.models import Annotation

        # Collect every annotation_id cited by any finding (closed graph).
        cited_ids: set[int] = set()
        for finding in report.findings or []:
            for cid in finding.get("citations", []) or []:
                try:
                    cited_ids.add(int(cid))
                except (TypeError, ValueError):
                    continue

        # Intersect with what retrieval actually surfaced — defence in
        # depth against any closure leak. The arecord_finding tool already
        # rejects unknown ids, but we re-enforce here in case findings were
        # appended by some other path (tests, future bulk import, etc.).
        cited_ids &= set(retrieved_annotation_ids)

        # Build the citation table, ordered by first appearance in the body.
        rendered_body, citations = _render_citations(markdown_body, cited_ids)

        full_content_parts: list[str] = []
        if executive_summary:
            full_content_parts.append("## Executive Summary\n\n" + executive_summary)
        full_content_parts.append(rendered_body)
        if citations:
            sources_section = ["## Sources", ""]
            for entry in citations:
                sources_section.append(f"[^{entry['footnote']}]: {entry['display']}")
            full_content_parts.append("\n".join(sources_section))

        report.content = "\n\n".join(part for part in full_content_parts if part)
        report.citations = citations
        report.status = JobStatus.COMPLETED.value
        report.completed_at = timezone.now()
        report.last_progress_at = report.completed_at
        update_fields = [
            "content",
            "citations",
            "status",
            "completed_at",
            "last_progress_at",
            "modified",
        ]
        if warnings:
            # Append rather than replace so prior warnings from
            # ``append_finding`` / ``append_tool_call`` survive.
            report.warnings = list(report.warnings or []) + list(warnings)
            update_fields.append("warnings")
        report.save(update_fields=update_fields)

        # Populate M2M provenance links. Restrict to annotation IDs that
        # exist (defensive: agent could in principle cite a deleted row).
        if citations:
            annotation_ids = [c["annotation_id"] for c in citations]
            existing_annotations = Annotation.objects.filter(
                pk__in=annotation_ids
            ).select_related("document")
            report.source_annotations.set(existing_annotations)
            doc_ids = {
                ann.document_id for ann in existing_annotations if ann.document_id
            }
            if doc_ids:
                from opencontractserver.documents.models import Document

                report.source_documents.set(Document.objects.filter(pk__in=doc_ids))

    # ------------------------------------------------------------------
    # Cancel
    # ------------------------------------------------------------------
    @classmethod
    def request_cancel(cls, user: Any, report: ResearchReport) -> None:
        """Flip ``cancel_requested``. The running loop polls and exits."""
        if report.creator_id != getattr(user, "id", None) and not getattr(
            user, "is_superuser", False
        ):
            raise PermissionError(
                "Only the creator (or a superuser) can cancel a research report."
            )
        if report.is_terminal:
            return
        report.cancel_requested = True
        report.save(update_fields=["cancel_requested", "modified"])
        cls.log_action("CancelRequested", report, user)

    @classmethod
    def cancel_if_requested(cls, report: ResearchReport) -> bool:
        """Return True (and raise) when a cancel has been requested.

        Polled by the agent's scratchpad-tool closures between calls.
        """
        report.refresh_from_db(fields=["cancel_requested"])
        if report.cancel_requested:
            raise ResearchCancelled(f"Research report {report.pk} cancel requested")
        return False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _derive_title_from_prompt(prompt: str, limit: int = 80) -> str:
    """Fallback title — first non-trivial line of the prompt, truncated."""
    first_line = ""
    for line in (prompt or "").splitlines():
        candidate = line.strip().lstrip("#").strip()
        if candidate:
            first_line = candidate
            break
    if not first_line:
        return "Untitled Research Report"
    if len(first_line) <= limit:
        return first_line
    return first_line[: limit - 1].rstrip() + "…"


def _render_citations(
    markdown_body: str, allowed_annotation_ids: set[int]
) -> tuple[str, list[dict]]:
    """Convert ``<cite ids="...">claim</cite>`` placeholders into footnotes.

    Returns ``(rendered_markdown, citations_table)``. The citations table
    is ordered by first appearance; each entry has ``footnote``,
    ``annotation_id``, ``document_id``, ``page``, ``raw_text``,
    ``similarity_score``, and a ``display`` string suitable for the
    ``## Sources`` block.

    Citations referring to annotations not in ``allowed_annotation_ids``
    are silently dropped — the agent shouldn't have produced them
    (``arecord_finding`` validates), but we keep this defensive so a
    rogue finding never produces a broken markdown link.
    """
    from opencontractserver.annotations.models import Annotation

    pattern = re.compile(
        r"<cite\s+ids=\"([0-9,\s]+)\">(.*?)</cite>",
        flags=re.DOTALL | re.IGNORECASE,
    )

    # First pass: assign footnote numbers to unique (filtered) annotation ids
    # in order of appearance.
    footnote_for_id: dict[int, int] = {}
    next_footnote = 1
    for match in pattern.finditer(markdown_body):
        ids = _parse_ids(match.group(1))
        for ann_id in ids:
            if ann_id not in allowed_annotation_ids:
                continue
            if ann_id not in footnote_for_id:
                footnote_for_id[ann_id] = next_footnote
                next_footnote += 1

    # Fetch annotation metadata in one query for the Sources block.
    annotations_by_id = {
        ann.pk: ann
        for ann in Annotation.objects.filter(
            pk__in=footnote_for_id.keys()
        ).select_related("document")
    }

    def _replace(match: re.Match[str]) -> str:
        ids = _parse_ids(match.group(1))
        claim = match.group(2)
        markers: list[str] = []
        for ann_id in ids:
            if ann_id in footnote_for_id:
                markers.append(f"[^{footnote_for_id[ann_id]}]")
        if not markers:
            # All ids were filtered out — render the claim alone so the
            # reader still gets the prose without a dangling footnote.
            return claim
        return f"{claim}{''.join(markers)}"

    rendered = pattern.sub(_replace, markdown_body)

    citations: list[dict] = []
    for ann_id, footnote in sorted(footnote_for_id.items(), key=lambda kv: kv[1]):
        ann = annotations_by_id.get(ann_id)
        if ann is None:
            # Annotation was deleted between agent run and finalize.
            continue
        raw_text = (getattr(ann, "raw_text", "") or "")[:240]
        page = getattr(ann, "page", None)
        doc = getattr(ann, "document", None)
        doc_title = getattr(doc, "title", "") if doc else ""
        doc_id = getattr(doc, "id", None)
        display_parts = []
        if doc_title:
            display_parts.append(f"*{doc_title}*")
        if doc_id is not None:
            display_parts.append(f"(doc {doc_id})")
        if page is not None:
            display_parts.append(f"page {page}")
        display_parts.append(f"annotation {ann_id}")
        if raw_text:
            display_parts.append(f"— “{raw_text}”")
        citations.append(
            {
                "footnote": footnote,
                "annotation_id": ann_id,
                "document_id": doc_id,
                "page": page,
                "raw_text": raw_text,
                "display": " ".join(display_parts),
            }
        )

    return rendered, citations


def _parse_ids(group: str) -> list[int]:
    out: list[int] = []
    for token in (group or "").split(","):
        token = token.strip()
        if not token:
            continue
        try:
            out.append(int(token))
        except ValueError:
            continue
    return out
