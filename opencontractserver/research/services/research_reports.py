"""Service layer for :class:`ResearchReport`.

All ResearchReport mutations and lifecycle transitions go through this
class. Per CLAUDE.md rule 7, callers with user context (GraphQL,
Celery, chat tools) MUST NOT touch ``ResearchReport.objects`` directly.
"""

from __future__ import annotations

import logging
import re
from datetime import timedelta
from difflib import SequenceMatcher
from typing import Any, NamedTuple

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
    RESEARCH_CITE_ECHO_THRESHOLD,
    RESEARCH_CLAIM_INVERSION_COVERAGE,
    RESEARCH_CLAIM_SUPPORT_MIN_COVERAGE,
    RESEARCH_CLAIM_SUPPORT_MIN_WORDS,
    RESEARCH_HEADER_ANCHOR_LABELS,
    RESEARCH_MEMORY_PREVIEW_CHARS,
    RESEARCH_MEMORY_SEARCH_MAX_HITS,
    RESEARCH_QUOTE_MATCH_THRESHOLD,
    RESEARCH_QUOTE_MAX_CHARS,
    RESEARCH_QUOTE_MIN_WORDS,
    RESEARCH_RECOVERY_FINDINGS_DIGEST,
    RESEARCH_SENTENCE_LOOKBACK_CHARS,
    RESEARCH_SUMMARY_DUPLICATE_PROBE_CHARS,
    RESEARCH_SUMMARY_DUPLICATE_THRESHOLD,
    RESEARCH_SUPPORT_MIN_TOKEN_CHARS,
    RESEARCH_SUPPORT_NEGATION_PREFIXES,
    RESEARCH_SUPPORT_NEGATION_TOKENS,
    RESEARCH_SUPPORT_STOPWORDS,
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

        Composes ONE document — ``## Executive Summary`` + ``executive_summary``
        + ``markdown_body`` — and runs the citation post-processors over it
        exactly once, then appends the rendered ``## Sources`` footnote section.
        Composing first is what keeps the pipeline honest: a ``<cite>`` tag the
        agent put in its summary is rendered rather than leaking raw into the
        stored content (issue #2200), and every guard below sees the whole
        document, not just the body.

        The pipeline, in order:

        - ``_sanitize_agent_markdown`` drops agent-authored ``## Executive
          Summary`` / ``## Sources`` headings and the hyperlinks the (web-less)
          agent invented — every URL it emits is fabricated, and the ``<cite>``
          footnotes are the only sanctioned attribution channel.
          ``_summary_duplicates_body`` then drops a summary that merely restates
          the body; together these stop the report rendering twice (#2200).
        - ``_verify_cite_spans`` collapses self-echoing cite spans, demotes
          quotes that are not verbatim in their cited annotation (issue #2189),
          and strips citations whose anchor does not support the sentence
          (issue #2201). Each rewrite is corrective *and* counted into a warning.
        - ``_render_citations`` converts the surviving ``<cite ids="1,2">claim
          </cite>`` / ``<cite ids="1,2"/>`` placeholders into ``[^n]`` markers
          and builds the structured ``citations`` table; a concise
          weak-citation warning is appended when any footnote anchors a
          section-header label (``_is_header_anchor``, issue #2180) —
          observational only, it never rewrites the prose.

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

        # Normalise the two agent-authored fragments, then compose ONE document
        # so every post-processor below runs over the whole report exactly once
        # (issue #2200). Both the normal and the salvage body flow through here.
        summary, summary_sections = _sanitize_agent_markdown(executive_summary or "")
        body, body_sections = _sanitize_agent_markdown(markdown_body or "")
        sections_stripped = summary_sections + body_sections
        if _summary_duplicates_body(summary, body):
            summary = ""

        document = "\n\n".join(
            part
            for part in (
                "## Executive Summary\n\n" + summary if summary else "",
                body,
            )
            if part
        )

        verified = _verify_cite_spans(document, cited_ids)
        rendered, citations = _render_citations(verified.markdown, cited_ids)

        full_content_parts: list[str] = [rendered]
        if citations:
            sources_section = ["## Sources", ""]
            for entry in citations:
                sources_section.append(f"[^{entry['footnote']}]: {entry['display']}")
            full_content_parts.append("\n".join(sources_section))

        report.content = "\n\n".join(
            part for part in full_content_parts if part.strip()
        )
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
        # Surface a weak-citation warning when any footnote resolves to a
        # section header / structural anchor rather than a supporting passage
        # (issue #2180). Observational only — it never rewrites the prose, it
        # just flags footnotes a reviewer (or future automated checker) should
        # double-check.
        extra_warnings: list[str] = list(warnings or [])

        # A COMPLETED report must never be silently blank. The agent can hand
        # finalize vacuous content — a body that was nothing but scaffolding or
        # a fabricated link, so ``_sanitize_agent_markdown`` reduced it to "" —
        # which the salvage path does not cover (it only catches "the agent
        # never called finalize"). Say so rather than storing an empty report
        # that looks like a successful run.
        if not (report.content or "").strip():
            extra_warnings.append(
                "The agent finalized with no report content; nothing survived "
                "composition. Re-run the research task."
            )

        header_footnotes = [
            c["footnote"] for c in citations if c.get("anchor_is_header")
        ]
        if header_footnotes:
            markers = ", ".join(f"[^{n}]" for n in header_footnotes)
            extra_warnings.append(
                _pluralize(
                    len(header_footnotes),
                    "citation anchors a section header rather than a supporting "
                    f"passage ({markers}); verify it points",
                    "citations anchor section headers rather than supporting "
                    f"passages ({markers}); verify they point",
                )
                + " at the operative language."
            )

        # Surface warnings for the two corrective guards. Both already rewrote
        # the stored content; the warning tells the reader what changed and why.
        if verified.quotes_demoted:
            extra_warnings.append(
                _pluralize(
                    verified.quotes_demoted,
                    "quoted passage did not match its cited source text and was",
                    "quoted passages did not match their cited source text and were",
                )
                + " converted to paraphrase (quotation marks removed); verify "
                "the wording against the source."
            )
        if verified.cites_dropped:
            extra_warnings.append(
                _pluralize(
                    verified.cites_dropped,
                    "sentence was not supported by the passage it cited, so its "
                    "citation was",
                    "sentences were not supported by the passages they cited, so "
                    "their citations were",
                )
                + " removed; the prose is retained as uncited analysis."
            )
        if verified.echoes_trimmed:
            extra_warnings.append(
                _pluralize(
                    verified.echoes_trimmed,
                    "citation restated the sentence before it and was",
                    "citations restated the sentences before them and were",
                )
                + " collapsed to a footnote; a small amount of text inside the "
                "tag went with the restatement."
            )
        if sections_stripped:
            extra_warnings.append(
                _pluralize(
                    sections_stripped,
                    "agent-authored Sources/References section was",
                    "agent-authored Sources/References sections were",
                )
                + " removed; the system renders the footnote table itself. "
                "Check nothing substantive was written under that heading."
            )

        if extra_warnings:
            # Append rather than replace so prior warnings from
            # ``append_finding`` / ``append_tool_call`` survive.
            report.warnings = list(report.warnings or []) + extra_warnings
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


def _pluralize(count: int, singular: str, plural: str) -> str:
    """``"1 citation anchors…"`` / ``"3 citations anchor…"``.

    The finalize warnings are read by humans in the report UI, so the grammar
    has to agree; this keeps the three warning builders from each re-deriving
    it.
    """
    return f"{count} {singular if count == 1 else plural}"


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


def _sanitize_agent_markdown(markdown: str) -> tuple[str, int]:
    """Normalise one agent-authored fragment before it joins the document.

    Strips the scaffolding ``finalize`` owns (see ``_strip_scaffold_headings``)
    and the hyperlinks the web-less agent invents (see
    ``_strip_fabricated_links``). Applied to the executive summary and the body
    alike so neither can smuggle either past the other's checks — and so a
    fragment that was *nothing but* a fabricated link reduces to "" and is
    dropped rather than leaving an empty section behind.

    Returns ``(cleaned, sections_stripped)``; the count feeds a warning so a
    whole dropped section is never silent, matching the other guards.
    """
    stripped, sections = _strip_scaffold_headings(markdown)
    return _strip_fabricated_links(stripped).strip(), sections


def _strip_scaffold_headings(markdown: str) -> tuple[str, int]:
    """Remove the report scaffolding the SYSTEM owns from agent-authored text.

    ``finalize`` writes the ``## Executive Summary`` header and renders the
    ``## Sources`` footnote table itself. An agent that writes its own copies
    produces the doubled document of issue #2200 — a full report, a stub
    "## Sources — (all claims are cited inline)" line, then the whole report
    again. A sources-flavoured heading takes its section with it (up to the next
    heading at the same or a shallower level); the executive-summary heading is
    dropped alone so the prose beneath it survives as the summary.

    Stripping is nesting-aware: a subsection *inside* the scaffolding section
    (``## Sources`` -> ``### By Document``) goes with it, rather than ending the
    skip and leaking orphaned scaffolding into the report — which is the very
    thing #2200 is about. A heading at the same or a shallower level ends the
    section, as it does in the markdown itself.

    Returns ``(cleaned, sections_stripped)``. Dropping a whole section is a much
    bigger blast radius than dropping a heading line, so the count is surfaced
    as a warning by ``finalize`` — consistent with the quote/claim-support
    guards, and it doubles as the signal for whether the prompt rule forbidding
    these headings is actually landing.
    """
    if not markdown:
        return "", 0
    kept: list[str] = []
    # Heading level of the scaffolding section currently being skipped, or None.
    skip_level: int | None = None
    sections = 0
    # The fence CHARACTER of the open block, or None outside one. CommonMark
    # closes a fence only on its own character, so a stray ``~~~`` inside a
    # backtick block is content, not a close. Tracking the character rather
    # than a bool keeps an unevenly-fenced body from suspending heading
    # detection for the rest of the document — which fails quiet (scaffolding
    # left unstripped), the hardest direction to notice.
    fence_char: str | None = None
    for line in markdown.splitlines():
        fence = _CODE_FENCE_RE.match(line)
        if fence:
            char = fence.group(1)[0]
            if fence_char is None:
                fence_char = char
            elif fence_char == char:
                fence_char = None
        heading = None if fence_char else _MD_HEADING_RE.match(line)
        if heading:
            level = len(heading.group(1))
            title = _normalize_label(heading.group(2))
            # A heading at the same or a shallower level closes the section;
            # a deeper one is nested inside it and keeps the skip running.
            if skip_level is not None and level <= skip_level:
                skip_level = None
            if skip_level is None:
                if title in _SCAFFOLD_SECTION_HEADINGS:
                    skip_level = level
                    sections += 1
                    continue
                if title in _SCAFFOLD_HEADING_LINES:
                    continue
        if skip_level is None:
            kept.append(line)
    return "\n".join(kept).strip(), sections


def _summary_duplicates_body(summary: str, body: str) -> bool:
    """True when ``summary`` is just a copy of ``body`` (issue #2200).

    The agent was observed passing the entire report as BOTH ``executive_summary``
    and ``markdown_body``, so the report rendered twice. Compares the summary's
    opening (``RESEARCH_SUMMARY_DUPLICATE_PROBE_CHARS``) against the body rather
    than diffing two multi-KB strings: a genuine copy always matches from its
    first sentence, and a real 2–4 sentence summary — written to abstract, not
    restate — does not.
    """
    body_norm = _normalize_for_quote_match(body)
    summary_norm = _normalize_for_quote_match(summary)
    if not summary_norm or not body_norm:
        return False
    probe = summary_norm[:RESEARCH_SUMMARY_DUPLICATE_PROBE_CHARS]
    return (
        _contiguous_coverage(probe, body_norm) >= RESEARCH_SUMMARY_DUPLICATE_THRESHOLD
    )


def _normalize_label(text: str | None) -> str:
    """Lowercase and collapse separator runs so ``"Section Header"``,
    ``"section_header"`` and ``"section-header"`` all compare equal."""
    return re.sub(r"[\s_\-]+", " ", (text or "").strip().lower())


# The header-label set, pre-normalised once so ``_is_header_anchor`` only has to
# normalise its single input per call.
_NORMALIZED_HEADER_ANCHOR_LABELS: frozenset[str] = frozenset(
    _normalize_label(label) for label in RESEARCH_HEADER_ANCHOR_LABELS
)


def _is_header_anchor(*, label_text: str | None) -> bool:
    """True when a citation anchor's annotation label denotes a section header
    / heading rather than an operative passage (issue #2180).

    Keyed on the annotation LABEL (``annotation_label.text``), matched case- and
    separator-insensitively against ``RESEARCH_HEADER_ANCHOR_LABELS`` — NOT on
    ``Annotation.structural``. ``structural`` marks the whole parser layout
    layer (body paragraphs, tables, sentence chunks, …), so keying on it would
    flag nearly every citation while missing the bookmark-derived OC_SECTION
    headers that are ``structural=False``. See the constant's docstring.
    """
    return _normalize_label(label_text) in _NORMALIZED_HEADER_ANCHOR_LABELS


# ---------------------------------------------------------------------------
# Cite-span verification (issues #2189, #2200, #2201)
# ---------------------------------------------------------------------------
# Double-quoted passages: straight ("...") or curly (“...”), including a
# mismatched pair (straight-open/curly-close or vice versa — LLM output
# sometimes smart-quotes only one side). The inner group excludes every
# double-quote glyph and newlines, so adjacent quotes (``"a" and "b"``) match
# separately and a quote never runs past its close; it is length-capped
# (``RESEARCH_QUOTE_MAX_CHARS``) so a lone unbalanced quote can't scan the whole
# body. Single quotes / apostrophes (including the curly ’ U+2019) are
# deliberately NOT matched — they collide with contractions and possessives.
_QUOTED_PASSAGE_RE = re.compile(rf'["“]([^"“”\n]{{1,{RESEARCH_QUOTE_MAX_CHARS}}})["”]')

# The cite placeholder, in both sanctioned forms — wrapping
# (``<cite ids="1,2">claim</cite>``) and the self-closing pure marker
# (``<cite ids="1,2"/>``, issue #2200) that attaches a footnote to the sentence
# it follows without restating it. ``group(2)`` is None for the marker form.
# Shared by the verifier and the renderer so both parse exactly one shape.
_CITE_SPAN_RE = re.compile(
    r'<cite\s+ids="([0-9,\s]+)"\s*(?:/>|>(.*?)</cite>)',
    flags=re.DOTALL | re.IGNORECASE,
)

# Sentence/line boundary used to recover the prose a self-closing marker
# decorates, and to compare a wrapping span against the prose before it.
# The trailing ``\s`` is required, not incidental: it is what stops a decimal
# ("the cap is 1.5 million") from reading as a sentence end. The ``(?<!\bno)``
# lookbehind carves out the citation-number abbreviation for the same reason
# ``_is_negated`` does (spelled out per-case because this regex, unlike the
# negation check, runs on RAW text rather than the casefolded stream) —
# without it "Exhibit No. 4 governs the term" splits at
# the reference and the claim seen by the support check is truncated to
# "4 governs the term", short enough to fall under the min-words floor and skip
# the check entirely. The word boundary keeps it to a standalone "no", so
# "casino." still ends a sentence.
_SENTENCE_BOUNDARY_RE = re.compile(r'(?<!\b[Nn][Oo])[.!?:;]["”’)\]]*\s|\n')

# A fenced code block delimiter (``` or ~~~). Heading detection is suspended
# inside a fence: a ``# Sources`` COMMENT in a quoted snippet is not a heading,
# and reading it as one used to swallow the rest of the block plus everything
# after it, leaving an unterminated fence behind.
_CODE_FENCE_RE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")

# A markdown ATX heading line, capturing its level (the run of ``#``) and its
# title text. The level is what makes section stripping nesting-aware.
_MD_HEADING_RE = re.compile(r"^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$")

# Headings the SYSTEM owns. ``finalize`` writes the executive-summary header and
# renders the Sources footnote table itself, so an agent-authored copy is
# scaffolding leaking into the document (issue #2200: a stub "## Sources — (all
# claims are cited inline)" line sat between two renderings of the report).
# A sources-flavoured heading takes its whole section with it (up to the next
# heading); the executive-summary heading is dropped on its own so the prose
# beneath it survives as the summary.
_SCAFFOLD_SECTION_HEADINGS: frozenset[str] = frozenset(
    {"sources", "source", "references", "citations", "footnotes", "bibliography"}
)
_SCAFFOLD_HEADING_LINES: frozenset[str] = frozenset({"executive summary"})

# Punctuation trimmed from token edges before a token is compared. Shared by
# ``_content_words`` and ``_is_negated`` so both agree on where a token ends.
_TOKEN_PUNCTUATION = "\"“”'’()[]{}.,;:!?*_`"


def _normalize_for_quote_match(text: str) -> str:
    """Casefold + collapse all whitespace runs to single spaces.

    Mirrors ``opencontractserver.utils.annotation_anchoring._norm`` so quote
    verification uses the same notion of "the same words" the anchor pipeline
    does: newline / indentation differences between a PDF's ``raw_text`` and a
    quoted passage don't count as a mismatch, and matching is case-insensitive
    (the fabrication risk is invented WORDS, not case).
    """
    return " ".join((text or "").casefold().split())


def _contiguous_coverage(needle_norm: str, haystack_norm: str) -> float:
    """Fraction of ``needle_norm`` covered by its longest run inside
    ``haystack_norm`` (both already whitespace-/case-normalized).

    ``difflib``'s longest-contiguous-block, expressed as coverage of the needle
    — a stricter test than ``SequenceMatcher.ratio()`` that a real run of the
    needle appears verbatim. Shared by quote verification (#2189) and the
    duplicate-summary / echoed-cite guards (#2200) so "is this text a copy of
    that text" means one thing everywhere.
    """
    if not needle_norm or not haystack_norm:
        return 0.0
    if needle_norm in haystack_norm:
        return 1.0
    matcher = SequenceMatcher(None, needle_norm, haystack_norm, autojunk=False)
    block = matcher.find_longest_match(0, len(needle_norm), 0, len(haystack_norm))
    return block.size / len(needle_norm)


def _quote_is_grounded(quote: str, candidates_norm: list[str]) -> bool:
    """True when ``quote`` is verbatim (modulo whitespace/case) in a candidate.

    ``candidates_norm`` are the pre-normalized ``raw_text`` values of the
    annotations a ``<cite>`` span cites. A quote shorter than
    ``RESEARCH_QUOTE_MIN_WORDS`` words is treated as grounded (not a passage
    claim — see the constant). Otherwise the quote must share a single
    contiguous run covering ``RESEARCH_QUOTE_MATCH_THRESHOLD`` of its length
    with some candidate (an exact substring scores 1.0; the fuzzy band tolerates
    a trailing-punctuation / whitespace / single-character drift).
    """
    q = _normalize_for_quote_match(quote)
    if len(q.split()) < RESEARCH_QUOTE_MIN_WORDS:
        return True
    return any(
        _contiguous_coverage(q, cand) >= RESEARCH_QUOTE_MATCH_THRESHOLD
        for cand in candidates_norm
        if cand
    )


def _content_words(text: str) -> set[str]:
    """Meaning-bearing tokens of ``text``: normalized, stopwords and tokens
    shorter than ``RESEARCH_SUPPORT_MIN_TOKEN_CHARS`` removed.

    Punctuation is trimmed but internal hyphens/slashes are kept, so
    ``fixed-price`` stays one distinctive term rather than dissolving into two
    common ones.
    """
    words: set[str] = set()
    for token in _normalize_for_quote_match(text).split():
        token = token.strip(_TOKEN_PUNCTUATION)
        if not token:
            continue
        # Digit-bearing tokens skip the length floor: "10", "5%" and "$5" are
        # short but are exactly the figures a report must not fabricate, and
        # dropping them left the ratio with no signal either way. See the
        # constant for why numeric *parity* is deliberately not enforced.
        if len(token) < RESEARCH_SUPPORT_MIN_TOKEN_CHARS and not any(
            ch.isdigit() for ch in token
        ):
            continue
        if token in RESEARCH_SUPPORT_STOPWORDS:
            continue
        words.add(token)
    return words


def _is_negated(text: str) -> bool:
    """True when ``text`` carries an explicit negation marker.

    Matches both a negating particle ("not", "without", …) and a negating
    prefix ("non-cancelable"), since contracts use the two interchangeably and a
    token-exact test would miss the whole prefixed family.

    One exception: "no" also spells the citation-number abbreviation ("Exhibit
    No. 4", "Schedule No. A-1"), which is not a negation at all. Reading it as
    one let a reference that appears on only one side of an otherwise
    near-verbatim restatement trip the inversion guard and strip a VALID
    citation.

    The discriminator is the abbreviating period on the token itself, not what
    follows it: bare "no" negates, "no." abbreviates. That covers lettered
    references ("No. A-1") as well as numeric ones, and — unlike looking ahead
    for a number — it does not swallow a genuine negation that happens to
    precede one ("no 30-day cure period").

    Deliberately keyed on the normalized token stream rather than
    ``_content_words``, so the stopword list (which contains "not") cannot hide
    a polarity marker from the inversion guard.
    """
    for raw in _normalize_for_quote_match(text).split():
        token = raw.strip(_TOKEN_PUNCTUATION)
        if token in RESEARCH_SUPPORT_NEGATION_TOKENS:
            # ``"." in raw`` rather than ``raw.endswith(".")`` so a bracketed
            # reference ("(No. 4)") is still recognised as the abbreviation.
            if token == "no" and "." in raw:
                continue
            return True
        if token.startswith(RESEARCH_SUPPORT_NEGATION_PREFIXES):
            return True
    return False


def _claim_is_supported(claim: str, candidates_norm: list[str]) -> bool:
    """True when the cited annotation(s) plausibly SAY what ``claim`` asserts
    (issue #2201) — the generalization of #2189's "is the quote verbatim".

    Deterministic lexical floor: at least ``RESEARCH_CLAIM_SUPPORT_MIN_COVERAGE``
    of the claim's content words must occur in the union of the cited anchors'
    text. Claims shorter than ``RESEARCH_CLAIM_SUPPORT_MIN_WORDS`` words are
    accepted unchecked — a fragment has too few content words for a ratio to
    mean anything. A checked claim with NO usable anchor text (textless anchor,
    deleted row, id that was never retrieved) is unsupported by construction.

    See the constants for the calibration and for what this deliberately does
    NOT catch (a well-anchored sentence carrying an invented tail).

    The polarity guard has two known limitations, both pinned by tests:

    * It treats the cited anchors as a union, matching the coverage check
      above. A span citing several anchors that disagree on polarity therefore
      satisfies parity whichever way the claim reads, so an inversion against
      one of them can pass. Making polarity per-candidate while coverage stays
      a union would be the inconsistency, not the fix.
    * It reads polarity off a fixed marker lexicon, so an anchor that negates
      lexically ("obligations *excluding* painting") reads as affirmative and a
      faithful claim restating it with "not" looks like an inversion. Above the
      coverage gate that costs a valid citation. The failure is one-directional
      — an over-strip, never a fabricated attribution — which is the right way
      round here, and the coverage gate keeps looser paraphrases clear of it.

    Both point at the same honest fix: the entailment call this function is the
    seam for. Widening the lexicon would only move the boundary, not remove it.
    """
    if len(claim.split()) < RESEARCH_CLAIM_SUPPORT_MIN_WORDS:
        return True
    claim_words = _content_words(claim)
    if not claim_words:
        return True
    anchor_words: set[str] = set()
    for cand in candidates_norm:
        anchor_words |= _content_words(cand)
    if not anchor_words:
        return False
    covered = len(claim_words & anchor_words) / len(claim_words)
    if covered < RESEARCH_CLAIM_SUPPORT_MIN_COVERAGE:
        return False

    # Polarity guard. Word overlap cannot see negation, so a claim that inverts
    # its anchor ("the tenant is NOT liable…" against "the tenant is liable…")
    # scores like a faithful paraphrase. When the claim otherwise reads as a
    # near-verbatim restatement, a disagreement about whether a negation marker
    # is present is a meaning inversion, not a rephrasing — see the constants.
    if covered >= RESEARCH_CLAIM_INVERSION_COVERAGE:
        if _is_negated(claim) != any(_is_negated(cand) for cand in candidates_norm):
            return False
    return True


def _preceding_claim(text: str) -> tuple[int, str]:
    """Return ``(start_offset, segment)`` for the sentence ``text`` ends on.

    ``segment`` is the last non-blank sentence/line of ``text`` and always runs
    to its end, so a caller can splice a rewritten version back in with
    ``text[:start_offset] + rewritten``. Used for both halves of the
    self-quoting fix (#2200): it is the prose a wrapping span may be echoing,
    and the sentence a self-closing ``<cite ids="…"/>`` marker decorates.
    Lookback is bounded by ``RESEARCH_SENTENCE_LOOKBACK_CHARS``.

    Known limitation: only ``No.`` is carved out of the boundary rule, so other
    legal abbreviations (``Inc.``, ``Corp.``, ``U.S.C.``, ``e.g.``) still split
    a sentence and hand the guards a truncated claim. That is deliberate rather
    than unfinished. ``No.`` is unambiguous — a reference identifier always
    follows it, so it is never a sentence end. ``Inc.``/``Corp.`` genuinely end
    sentences in filing prose ("...acquired by Karman Holdings Inc. The
    transaction closed..."), so suppressing the boundary there would MERGE two
    sentences into one claim. The two errors are not symmetric: truncation
    shortens the claim and fails open (the check is skipped or scores higher),
    whereas merging pads it with unrelated vocabulary and erodes the coverage
    margin toward a false strip — measured at 1.00 -> 0.40 for one unrelated
    preceding sentence, which stays above the floor but spends most of the
    headroom. Prefer the failing-open error until this uses real sentence
    segmentation.
    """
    head = text[-RESEARCH_SENTENCE_LOOKBACK_CHARS:]
    base = len(text) - len(head)
    start = 0
    last_nonblank = 0
    for match in _SENTENCE_BOUNDARY_RE.finditer(head):
        if head[start : match.end()].strip():
            last_nonblank = start
        start = match.end()
    if head[start:].strip():
        last_nonblank = start
    return base + last_nonblank, head[last_nonblank:]


def _strip_ungrounded_quotes(claim: str, candidates_norm: list[str]) -> tuple[str, int]:
    """Drop quotation marks around passages in ``claim`` that no cited
    annotation supports. Returns ``(cleaned_claim, downgraded_count)``.

    Only the quotation marks are removed — the prose is preserved — so an
    ungrounded "quote" degrades honestly to the agent's own paraphrase rather
    than masquerading as a verbatim citation (issue #2189).
    """
    downgraded = 0

    def _replace(match: re.Match[str]) -> str:
        nonlocal downgraded
        inner = match.group(1)
        if _quote_is_grounded(inner, candidates_norm):
            return match.group(0)
        downgraded += 1
        return inner

    return _QUOTED_PASSAGE_RE.sub(_replace, claim), downgraded


class CiteVerification(NamedTuple):
    """Outcome of :func:`_verify_cite_spans`."""

    markdown: str
    quotes_demoted: int
    cites_dropped: int
    echoes_trimmed: int


def _verify_cite_spans(
    markdown: str, allowed_annotation_ids: set[int]
) -> CiteVerification:
    """Walk every ``<cite>`` span once and enforce the three citation guards.

    Per span, against the ``raw_text`` of the annotation(s) it cites:

    1. **Echo collapse** (#2200) — a wrapping span whose inner text merely
       restates the prose immediately before it collapses to the self-closing
       marker form, so the claim renders once with a trailing footnote instead
       of twice. The threshold is a ratio over the INNER text, so any tail the
       span adds beyond the restatement shrinks it: on a typical sentence a
       tail of more than about a word already falls under
       ``RESEARCH_CITE_ECHO_THRESHOLD`` and the span is left intact. What can
       still be lost is bounded by that same ratio, and a collapse that is not
       total is counted (``echoes_trimmed``) so it is reported rather than
       silent.
    2. **Quote verification** (#2189) — a quoted passage that is not verbatim in
       the cited text loses its quotation marks (prose and footnote preserved),
       so a fabricated quote degrades honestly to paraphrase.
    3. **Claim support** (#2201) — a cited sentence whose anchor text does not
       support it loses the citation entirely; the prose survives as uncited
       analysis. See :func:`_claim_is_supported`.

    The "claim" a span asserts is its inner text, or — for a self-closing
    marker, and for a span collapsed by (1) — the sentence it follows, so the
    guards apply identically to both sanctioned cite forms. Returns the
    rewritten markdown plus the three counts ``finalize`` turns into warnings.

    A span whose cited ids yield NO usable text (textless anchor, deleted row,
    or an id retrieval never produced) is treated as ungrounded by both (2) and
    (3) rather than silently passing through — that is the "cited a real anchor
    but invented the content" hole these guards exist to close.

    The guards are independent, so one badly-anchored span can trip (2) and (3)
    both, and ``finalize`` will then warn about a demoted quote AND a removed
    citation for what reads as a single sentence. That is intended: the two
    remediations are different and both land in the output the reader sees. The
    quotation marks come off (so no fabricated verbatim survives) and the
    footnote comes off (so the sentence is not attributed) — reporting only one
    would leave the other edit unexplained.

    Known asymmetry across split markers: when the agent writes
    ``… <cite ids="1"/> <cite ids="2"/>`` instead of the combined
    ``<cite ids="1,2"/>`` the prompt asks for, the carried-forward claim feeds
    (3) but not (2) — the later marker's ``preceding`` is the blank gap between
    the tags, so quotes were already verified at the first marker against ITS
    anchors alone. This can only over-strip: a quote grounded in the second
    anchor but not the first is demoted to paraphrase (honest, and the warning
    tells the reader to check the wording). It cannot under-strip — a quote in
    NEITHER anchor is still demoted at the first marker, so nothing ungrounded
    reaches the reader through the split form. Unioning candidates across a run
    of adjacent markers would fix the strictness; it is not worth a lookahead
    pre-pass for a shape the prompt forbids.
    """
    spans = list(_CITE_SPAN_RE.finditer(markdown or ""))
    if not spans:
        return CiteVerification(markdown, 0, 0, 0)

    # Hydrate every cited, allowed annotation's text in ONE query (no N+1),
    # normalized once and cached by id. Ids outside ``allowed_annotation_ids``
    # are excluded here, so a span citing only such ids gets no candidates.
    all_ids: set[int] = {
        ann_id
        for match in spans
        for ann_id in _parse_ids(match.group(1))
        if ann_id in allowed_annotation_ids
    }
    norm_by_id: dict[int, str] = {}
    if all_ids:
        from opencontractserver.annotations.models import Annotation

        norm_by_id = {
            pk: _normalize_for_quote_match(raw or "")
            for pk, raw in Annotation.objects.filter(pk__in=all_ids).values_list(
                "pk", "raw_text"
            )
        }

    out: list[str] = []
    cursor = 0
    quotes_demoted = 0
    cites_dropped = 0
    echoes_trimmed = 0
    last_claim = ""

    for match in spans:
        out.append(markdown[cursor : match.start()])
        cursor = match.end()
        ids_raw = match.group(1)
        inner = match.group(2)  # None for the self-closing marker form
        candidates = [norm_by_id[i] for i in _parse_ids(ids_raw) if norm_by_id.get(i)]

        preceding_offset, preceding = _preceding_claim(out[-1])

        # (1) Echo collapse — inner text that just restates the prose before it.
        if inner:
            echo = _contiguous_coverage(
                _normalize_for_quote_match(inner),
                _normalize_for_quote_match(preceding),
            )
            if echo >= RESEARCH_CITE_ECHO_THRESHOLD:
                # A collapse below full coverage discards the uncovered
                # remainder along with the echo, so count it — every other
                # strip in this pipeline is reported, and this one should not
                # be the exception. Gated on the loss, not the collapse: an
                # exact echo (the observed shape, and 1.0 even when only
                # punctuation differs) loses nothing and stays silent.
                if echo < 1.0:
                    echoes_trimmed += 1
                inner = None

        # (2) Quote verification, applied to whichever text carries the claim.
        # For a marker, that text already sits in the emitted tail, so the
        # rewrite is spliced back into it.
        if inner is not None:
            inner, demoted = _strip_ungrounded_quotes(inner, candidates)
            claim = inner
        else:
            cleaned, demoted = _strip_ungrounded_quotes(preceding, candidates)
            if demoted and out:
                out[-1] = out[-1][:preceding_offset] + cleaned
            claim = cleaned
        quotes_demoted += demoted

        # The claim is the text immediately before the span, so consecutive
        # markers on one sentence (``… <cite ids="1"/> <cite ids="2"/>`` instead
        # of the combined ``<cite ids="1,2"/>`` the prompt asks for) leave the
        # later span nothing but the whitespace between the tags. Carry the
        # previous span's claim forward so the second anchor is checked against
        # the sentence it decorates rather than passing unchecked as a fragment.
        if not claim.strip():
            claim = last_claim
        last_claim = claim

        # (3) Claim support — an unsupported sentence keeps its prose, loses
        # its footnote. A marker with NO prose before it at all (the degenerate
        # case of one opening the document) yields an empty claim, which falls
        # under the min-words floor and is left alone: there is no sentence for
        # the anchor to misrepresent, so there is nothing to strip.
        if not _claim_is_supported(claim, candidates):
            cites_dropped += 1
            out.append(inner or "")
            continue

        out.append(
            f'<cite ids="{ids_raw}"/>'
            if inner is None
            else f'<cite ids="{ids_raw}">{inner}</cite>'
        )

    out.append(markdown[cursor:])
    return CiteVerification(
        "".join(out), quotes_demoted, cites_dropped, echoes_trimmed
    )


def _render_citations(
    markdown_body: str, allowed_annotation_ids: set[int]
) -> tuple[str, list[dict]]:
    """Convert ``<cite ids="...">claim</cite>`` and ``<cite ids="..."/>``
    placeholders into footnotes.

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

    # Shared with the verifier (_verify_cite_spans) so both parse the same cite
    # placeholder shape.
    pattern = _CITE_SPAN_RE

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
    # ``annotation_label`` is pulled so the weak-citation lint (#2180) can read
    # the anchor's label without an N+1.
    annotations_by_id = {
        ann.pk: ann
        for ann in Annotation.objects.filter(
            pk__in=footnote_for_id.keys()
        ).select_related("document", "annotation_label")
    }

    def _replace(match: re.Match[str]) -> str:
        ids = _parse_ids(match.group(1))
        # None for the self-closing marker form: the claim is the prose the
        # marker follows, which stays exactly where it is.
        claim = match.group(2) or ""
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
                # Flag anchors whose annotation label is a section header /
                # heading so finalize can surface a weak-citation warning and
                # any future automated citation-checking can key off it (#2180).
                "anchor_is_header": _is_header_anchor(
                    label_text=getattr(
                        getattr(ann, "annotation_label", None), "text", None
                    ),
                ),
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
