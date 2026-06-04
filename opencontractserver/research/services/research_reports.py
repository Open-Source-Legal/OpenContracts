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
    MAX_RESEARCH_MEMORY_KEY_CHARS,
    MAX_RESEARCH_MEMORY_KEYS,
    MAX_RESEARCH_MEMORY_TOTAL_CHARS,
    MAX_RESEARCH_MEMORY_VALUE_CHARS,
    MAX_RESEARCH_PLAN_CHARS,
    MAX_RESEARCH_STEPS_CEILING,
    RESEARCH_MEMORY_PREVIEW_CHARS,
    RESEARCH_MEMORY_SEARCH_MAX_HITS,
    RESEARCH_RECOVERY_FINDINGS_DIGEST,
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


class ResearchMemoryError(Exception):
    """Base for anything the memory-write path rejects — both malformed input
    (empty key, unknown mode) and capacity violations.

    The agent-bound ``write_memory`` closure catches this base class and returns
    the message to the model as an operational error string (mirroring
    ``record_finding``'s bad-id handling) so the run continues — the agent is
    expected to fix the input, prune, or shorten and retry rather than crash the
    job. Catch the base when you only need "the write was rejected, tell the
    model"; catch :class:`ResearchMemoryLimitExceeded` specifically to
    distinguish a genuine cap violation from bad input.
    """


class ResearchMemoryLimitExceeded(ResearchMemoryError):
    """Raised when a numeric cap (per-key, per-value, total-store, or key-count)
    would be exceeded — a capacity violation, not malformed input."""


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
    # Reads
    # ------------------------------------------------------------------
    @classmethod
    def list_recent_for_corpus(
        cls,
        *,
        user: Any,
        corpus: Any,
        limit: int = 5,
        request: Any = None,
    ) -> list[ResearchReport]:
        """Return the user's most recent reports for ``corpus`` (newest first).

        Creator-only visibility is enforced by ``visible_to_user`` (via the
        shared ``filter_visible`` helper), so this is safe to expose to chat
        tools and other user-context callers. ``limit`` is clamped to a small
        ceiling so a caller cannot pull an unbounded list.
        """
        bounded = max(1, min(int(limit), 25))
        qs = (
            cls.filter_visible(ResearchReport, user, request=request)
            .filter(corpus=corpus)
            .order_by("-created")
        )
        return list(qs[:bounded])

    # ------------------------------------------------------------------
    # Lifecycle transitions
    # ------------------------------------------------------------------
    @classmethod
    def mark_started(cls, report: ResearchReport, *, resuming: bool = False) -> None:
        """Transition a report to RUNNING.

        On a resume (``resuming=True``, i.e. a worker picking up a report that
        was already RUNNING after a crash) the original ``started_at`` is
        preserved so wall-clock duration reflects the whole investigation, not
        just the final leg. ``error_message`` is still cleared — a prior
        transient error should not shadow a successful resume.
        """
        now = timezone.now()
        report.status = JobStatus.RUNNING.value
        if not (resuming and report.started_at):
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
    # Durable context management — plan + memory (called from tool closures)
    # ------------------------------------------------------------------
    # WHY a report-scoped store and not the existing Note / corpus-memory
    # mechanisms (DRY review, 2026-06): OpenContracts already has two durable
    # text stores — the ``Note`` model (annotations.models) with its
    # token-budgeted ``get_partial_note_content`` retrieval, and the
    # auto-curated ``Corpus.memory_document`` (agents.memory). Both are *shared
    # corpus state*: writing to either is visible to every user with corpus
    # READ and persists beyond the run. The deep-research agent is, by design,
    # strictly read-only over corpus state (see ``DEEP_RESEARCH_READ_ONLY_TOOLS``
    # — every write tool is excluded, and the system prompt forbids mutation).
    # Routing its half-formed working notes into Notes/corpus-memory would
    # leak an in-progress agent's scratchpad into shared, user-visible state
    # before the report is even finalized. So the agent's private working
    # memory lives here, on the report (creator-only visibility), and is the
    # one durable store it is allowed to *write*. It deliberately does NOT
    # reinvent corpus-level memory; it fills the orthogonal gap of private,
    # run-scoped memory that survives compaction + restart.
    @classmethod
    def update_plan(cls, report: ResearchReport, plan: str) -> str:
        """Replace the living plan, clamped to ``MAX_RESEARCH_PLAN_CHARS``.

        Returns the stored plan (post-clamp) so the caller can echo back what
        was actually persisted. Bumps ``last_progress_at`` — writing a plan is
        real forward progress and should reset the stalled-job clock.

        Refreshes the row first (mirroring ``write_memory``) so a concurrent
        ``cancel_requested`` flip is not stomped. Last-writer-wins semantics
        are intentional and safe: only one worker owns a report at a time, and
        the reaper's ``DEEP_RESEARCH_STUCK_THRESHOLD_SECONDS`` guard makes a
        two-worker plan race vanishingly unlikely — not worth a
        ``select_for_update`` on the hot write path.
        """
        report.refresh_from_db(fields=["cancel_requested"])
        clamped = _clamp_text(plan or "", MAX_RESEARCH_PLAN_CHARS)
        now = timezone.now()
        report.plan = clamped
        report.last_progress_at = now
        report.save(update_fields=["plan", "last_progress_at", "modified"])
        return clamped

    @classmethod
    def write_memory(
        cls,
        report: ResearchReport,
        key: str,
        content: str,
        *,
        mode: str = "replace",
    ) -> dict:
        """Create/overwrite/append a memory entry under ``key``.

        ``mode`` is ``"replace"`` (default) or ``"append"`` (concatenate with a
        newline onto any existing value). Enforces, in order: key length, value
        length, key-count, and total-store-size caps. A cap violation raises
        :class:`ResearchMemoryLimitExceeded`; malformed input (empty key,
        unknown mode) raises the :class:`ResearchMemoryError` base. The closure
        catches the base and surfaces the message to the model. Returns
        ``{key, bytes, keys}`` summarising the store.

        Refreshes the row first so a concurrent ``cancel_requested`` flip (or a
        memory write from a redelivered task) is not stomped. Last-writer-wins
        semantics are intentional here — only one worker owns a report at a
        time in the normal case, and the reaper's stuck-threshold guard makes a
        genuine two-worker race vanishingly unlikely — so we deliberately do
        NOT take a ``select_for_update`` on this hot write path.
        """
        key = (key or "").strip()
        if not key:
            raise ResearchMemoryError("Memory key must be non-empty.")
        if len(key) > MAX_RESEARCH_MEMORY_KEY_CHARS:
            raise ResearchMemoryLimitExceeded(
                f"Memory key too long ({len(key)} chars); max is "
                f"{MAX_RESEARCH_MEMORY_KEY_CHARS}. Use a short slug like "
                "'doc-1421-summary'."
            )
        if mode not in ("replace", "append"):
            raise ResearchMemoryError(
                f"Unknown memory mode {mode!r}; use 'replace' or 'append'."
            )

        report.refresh_from_db(fields=["memory", "cancel_requested"])
        store: dict[str, Any] = dict(report.memory or {})

        existing = store.get(key)
        prior_content = ""
        if isinstance(existing, dict):
            prior_content = str(existing.get("content", ""))
        if mode == "append" and prior_content:
            new_content = f"{prior_content}\n{content or ''}"
        else:
            new_content = content or ""

        if len(new_content) > MAX_RESEARCH_MEMORY_VALUE_CHARS:
            raise ResearchMemoryLimitExceeded(
                f"Memory value for '{key}' is {len(new_content)} chars; max per "
                f"entry is {MAX_RESEARCH_MEMORY_VALUE_CHARS}. Split it across "
                "several keys or summarise."
            )

        # Key-count cap only bites when introducing a NEW key.
        if key not in store and len(store) >= MAX_RESEARCH_MEMORY_KEYS:
            raise ResearchMemoryLimitExceeded(
                f"Memory store already holds {len(store)} keys (max "
                f"{MAX_RESEARCH_MEMORY_KEYS}). Delete or consolidate keys with "
                "delete_memory before adding more."
            )

        # Total-store cap, computed against the post-write state.
        projected_total = sum(
            len(str(v.get("content", "")))
            for k, v in store.items()
            if k != key and isinstance(v, dict)
        ) + len(new_content)
        if projected_total > MAX_RESEARCH_MEMORY_TOTAL_CHARS:
            raise ResearchMemoryLimitExceeded(
                f"Writing '{key}' would push the memory store to "
                f"{projected_total} chars (max {MAX_RESEARCH_MEMORY_TOTAL_CHARS}). "
                "Prune older keys with delete_memory first."
            )

        # One timestamp for both the entry's ``updated_at`` and the row's
        # ``last_progress_at`` so they agree exactly (two ``timezone.now()``
        # calls would drift microseconds apart).
        now = timezone.now()
        store[key] = {
            "content": new_content,
            "updated_at": now.isoformat(),
        }
        report.memory = store
        report.last_progress_at = now
        report.save(update_fields=["memory", "last_progress_at", "modified"])
        return {"key": key, "bytes": len(new_content), "keys": len(store)}

    @classmethod
    def delete_memory(cls, report: ResearchReport, key: str) -> bool:
        """Drop a memory entry. Returns True if a key was removed.

        Bumps ``last_progress_at`` on a successful delete: pruning keys to free
        room under the store caps is real forward progress, so an agent that is
        only deleting should not look stalled to the reaper.
        """
        report.refresh_from_db(fields=["memory"])
        store = dict(report.memory or {})
        if key not in store:
            return False
        del store[key]
        report.memory = store
        report.last_progress_at = timezone.now()
        report.save(update_fields=["memory", "last_progress_at", "modified"])
        return True

    @classmethod
    def read_memory(cls, report: ResearchReport, key: str) -> str | None:
        """Return the content stored under ``key`` (fresh read), or None."""
        report.refresh_from_db(fields=["memory"])
        entry = (report.memory or {}).get(key)
        if isinstance(entry, dict):
            return str(entry.get("content", ""))
        return None

    @classmethod
    def memory_index(cls, report: ResearchReport) -> list[dict]:
        """Return ``[{key, bytes, preview}]`` for every memory entry.

        Sorted by key for stable rendering in the prompt index. Does not
        refresh — callers that need freshness refresh first (the ``list_memory``
        tool closure satisfies this by calling ``refresh_from_db(["memory"])``
        immediately before this method).
        """
        out: list[dict] = []
        for key in sorted((report.memory or {}).keys()):
            entry = report.memory[key]
            content = str(entry.get("content", "")) if isinstance(entry, dict) else ""
            preview = content[:RESEARCH_MEMORY_PREVIEW_CHARS].replace("\n", " ")
            out.append({"key": key, "bytes": len(content), "preview": preview})
        return out

    @classmethod
    def search_memory(
        cls, report: ResearchReport, query: str, *, max_hits: int | None = None
    ) -> list[dict]:
        """Grep across memory entries AND recorded findings.

        Case-insensitive substring match, line-oriented (like ``grep``).
        Returns ``[{source, key, line}]`` where ``source`` is ``"memory"`` or
        ``"finding"``. Capped at ``max_hits`` (default
        ``RESEARCH_MEMORY_SEARCH_MAX_HITS``) so a broad query cannot dump the
        whole store back into context.
        """
        report.refresh_from_db(fields=["memory", "findings"])
        needle = (query or "").strip().lower()
        limit = max_hits or RESEARCH_MEMORY_SEARCH_MAX_HITS
        hits: list[dict] = []
        if not needle:
            return hits

        for key in sorted((report.memory or {}).keys()):
            entry = report.memory[key]
            content = str(entry.get("content", "")) if isinstance(entry, dict) else ""
            for line in content.splitlines():
                if needle in line.lower():
                    hits.append({"source": "memory", "key": key, "line": line.strip()})
                    if len(hits) >= limit:
                        return hits

        for idx, finding in enumerate(report.findings or []):
            claim = str((finding or {}).get("claim", ""))
            if needle in claim.lower():
                section = str((finding or {}).get("section", "Findings"))
                hits.append(
                    {"source": "finding", "key": section, "line": claim.strip()}
                )
                if len(hits) >= limit:
                    return hits
        return hits

    # ------------------------------------------------------------------
    # Recovery — rebuild the durable context surface for a (re)started run
    # ------------------------------------------------------------------
    @classmethod
    def build_recovery_digest(cls, report: ResearchReport) -> dict:
        """Assemble the plan / findings-digest / memory-index strings used to
        prime the system prompt at the start of a run.

        Always cheap and bounded: the findings digest is the tail
        (``RESEARCH_RECOVERY_FINDINGS_DIGEST`` most recent) rendered compactly,
        and the memory index is keys + sizes + short previews — never full
        contents. The agent pulls full memory on demand via ``read_memory`` /
        ``search_memory``.

        Reads from the in-memory ``report`` object and does NOT refresh from the
        DB. This is intentional for the only caller (task startup, where the row
        was just loaded). If a future mid-run caller needs freshness, it must
        call ``report.refresh_from_db()`` first — unlike ``search_memory``,
        which refreshes itself because it runs from a tool closure.
        """
        plan = (report.plan or "").strip()

        findings = list(report.findings or [])
        recent = findings[-RESEARCH_RECOVERY_FINDINGS_DIGEST:]
        digest_lines: list[str] = []
        if len(findings) > len(recent):
            digest_lines.append(
                f"_(showing the {len(recent)} most recent of "
                f"{len(findings)} findings — search_memory for the rest)_"
            )
        for finding in recent:
            section = str((finding or {}).get("section", "Findings"))
            claim = str((finding or {}).get("claim", "")).strip()
            cites = (finding or {}).get("citations") or []
            cite_str = (
                " [cites: " + ",".join(str(c) for c in cites) + "]" if cites else ""
            )
            digest_lines.append(f"- ({section}) {claim}{cite_str}")
        findings_digest = "\n".join(digest_lines)

        index = cls.memory_index(report)
        memory_lines = [
            f"- `{item['key']}` ({item['bytes']} chars): {item['preview']}"
            for item in index
        ]
        memory_index_str = "\n".join(memory_lines)

        return {
            "plan": plan,
            "findings_digest": findings_digest,
            "memory_index": memory_index_str,
            "is_resume": bool(plan or findings or index),
        }

    # ------------------------------------------------------------------
    # Resume — re-enqueue a stalled RUNNING report
    # ------------------------------------------------------------------
    @classmethod
    def list_stalled(cls, *, older_than_seconds: int | None = None) -> list[int]:
        """Return PKs of RUNNING reports whose ``last_progress_at`` is older
        than the stuck threshold (a crashed worker leaves the row RUNNING with
        no further progress). Used by the periodic reaper to resume them.
        """
        threshold = older_than_seconds
        if threshold is None:
            threshold = getattr(
                settings,
                "DEEP_RESEARCH_STUCK_THRESHOLD_SECONDS",
                getattr(settings, "DEEP_RESEARCH_SOFT_TIME_LIMIT", 1800) * 2,
            )
        cutoff = timezone.now() - timedelta(seconds=threshold)
        qs = ResearchReport.objects.filter(
            status=JobStatus.RUNNING.value,
            last_progress_at__lt=cutoff,
        ).values_list("pk", flat=True)
        return list(qs)

    @classmethod
    def resume(cls, report: ResearchReport) -> bool:
        """Re-enqueue ``run_deep_research`` for a stalled RUNNING report.

        No-op (returns False) for a terminal report. Does NOT mutate status —
        the task's ``mark_started(resuming=True)`` handles that — so a double
        resume is harmless: the second pickup sees the durable state and
        continues. Returns True when a task was enqueued.
        """
        if report.is_terminal:
            return False
        from opencontractserver.tasks.research_tasks import run_deep_research

        run_deep_research.delay(report.pk)
        cls.log_action("Resumed", report, report.creator)
        return True

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

        # Strip any hyperlinks the agent fabricated. It has no web tools, so
        # every URL it emits is invented (canonically ``https://example.com``);
        # the ``<cite>`` footnotes rendered above are the only sanctioned
        # attribution channel. Applied to both the body and the summary so no
        # fabricated link survives into the stored content (or the salvage
        # path, which also flows through here). See ``_strip_fabricated_links``.
        rendered_body = _strip_fabricated_links(rendered_body)
        clean_summary = _strip_fabricated_links(executive_summary or "")

        full_content_parts: list[str] = []
        # ``.strip()``: a summary that was nothing but a fabricated link reduces
        # to whitespace after stripping — skip the empty header in that case.
        if clean_summary.strip():
            full_content_parts.append("## Executive Summary\n\n" + clean_summary)
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

        # Single atomic block so the terminal content write and the M2M
        # provenance links commit together. Without this, a worker that
        # dies (or a soft-time-limit) between ``save()`` and the M2M
        # ``set()`` calls would leave a COMPLETED report whose content
        # cites footnotes that have no ``source_annotations`` /
        # ``source_documents`` rows behind them — content with empty
        # provenance. The block wraps only the writes; the content/citation
        # rendering above is pure computation and stays outside.
        with transaction.atomic():
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


def _clamp_text(text: str, limit: int) -> str:
    """Truncate ``text`` to ``limit`` chars, keeping the head.

    The head of a plan is the task restatement + next steps — the part the
    agent most needs on recovery — so we drop the tail and append a marker
    rather than truncating from the front.
    """
    if len(text) <= limit:
        return text
    marker = "\n\n…[truncated]"
    keep = max(0, limit - len(marker))
    return text[:keep].rstrip() + marker


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


# Inline markdown link (optionally an image: ``![alt](src)``), capturing the
# label/alt text and the target. The target group stops at the first space,
# ``)`` or ``>`` so a trailing ``"title"`` and angle-bracket wrappers
# (``<https://…>``) are tolerated. Footnote markers/definitions (``[^1]`` /
# ``[^1]: …``) have no ``(target)`` and never match.
# Inline links only. The target group ``([^)\s>]+)`` stops at the first ``)``,
# so a parenthesised URL like ``Foo_(bar)`` is captured as ``Foo_(bar`` and the
# trailing ``)`` leaks through — academic here since the agent fabricates flat
# ``example.com`` URLs without parens.
_MARKDOWN_LINK_RE = re.compile(
    r"!?\[([^\]]*)\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)"
)

# A link target that resolves *outside* the SPA: an explicit ``scheme://``,
# a protocol-relative ``//host``, a ``mailto:``/``tel:``, or a bare domain
# (``example.com/…``). These are exactly the targets ``SafeMarkdown`` would
# turn into a live anchor. In-app relative paths (``/d/…``) and bare
# fragments (``#section``) are deliberately NOT matched.
_EXTERNAL_TARGET_RE = re.compile(
    r"""^(?:
        [a-z][a-z0-9+.\-]*://       # scheme://  (http, https, ftp, …)
        | //                        # protocol-relative  //host
        | mailto: | tel:            # non-web but still externally resolvable
        | [\w-]+(?:\.[\w-]{2,})+     # bare domain  example.com/… (TLD ≥2 chars,
                                    # so dotted prose like ``v1.0`` / ``section_a.2``
                                    # is not mistaken for a link target). Known
                                    # false positive: a relative ``name.ext``
                                    # path (``schema.json``, ``openapi.yaml``)
                                    # also matches — fine today since the agent
                                    # emits no legitimate relative-path links.
    )""",
    re.IGNORECASE | re.VERBOSE,
)


def _strip_fabricated_links(markdown: str) -> str:
    """Downgrade externally-resolvable markdown links the (web-less) agent
    invented to their plain label before storage, leaving the sanctioned
    ``<cite ids="…">`` tag, in-app relative links, and fragment anchors intact.

    Deliberate gap: only *inline* ``[text](url)`` links are matched, not
    reference-style ``[text][1]`` + ``[1]: url`` (the observed fabrication is the
    inline ``example.com`` placeholder); pinned by
    ``test_strip_fabricated_links_leaves_reference_style_links_unchanged``.
    """
    if not markdown:
        return markdown

    def _replace(match: re.Match[str]) -> str:
        label = match.group(1)
        target = match.group(2).strip()
        if _EXTERNAL_TARGET_RE.match(target):
            # Drop the fabricated URL (and any leading ``!`` image marker),
            # keep the human-readable label so the prose still reads cleanly.
            return label
        return match.group(0)

    return _MARKDOWN_LINK_RE.sub(_replace, markdown)


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
