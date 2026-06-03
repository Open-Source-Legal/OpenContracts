"""Deep Research Report models.

A ``ResearchReport`` is a long-lived, autonomous research job: a Celery
worker drives a corpus-scoped PydanticAI agent with read-only retrieval
tools until it produces a Markdown report with grounded citations.

v1 is creator-only — no sharing, no ``is_public`` semantics. ``BaseOCModel``
gives us ``is_public`` for free; the manager simply ignores it for
visibility purposes.
"""

from __future__ import annotations

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import models
from django.db.models import Q
from django.utils.text import slugify

from opencontractserver.research.constants import DEFAULT_MAX_STEPS_FALLBACK
from opencontractserver.shared.Managers import BaseVisibilityManager
from opencontractserver.shared.Models import BaseOCModel
from opencontractserver.types.enums import JobStatus

User = get_user_model()


class ResearchReportQuerySet(models.QuerySet):
    """Creator-only visibility for v1.

    A future v2 will widen this to ``creator OR explicit guardian grant``
    intersected with corpus visibility — the manager shape mirrors
    :class:`opencontractserver.agents.models.AgentActionResultManager` so
    that widening is a localised change.
    """

    def visible_to_user(self, user, lightweight: bool = False):
        if user is None or not getattr(user, "is_authenticated", False):
            return self.none()
        # Superusers are computed like any other user (scoped admin access, 2026-05) — no blanket bypass.
        return self.filter(creator=user)


class ResearchReportManager(BaseVisibilityManager):
    """Manager exposing ``visible_to_user`` via the queryset above."""

    def get_queryset(self) -> ResearchReportQuerySet:
        return ResearchReportQuerySet(self.model, using=self._db)

    def visible_to_user(
        self,
        user=None,
        lightweight: bool = False,
        with_doc_label_annotations: bool = False,
    ) -> ResearchReportQuerySet:
        return self.get_queryset().visible_to_user(user, lightweight=lightweight)


class ResearchReport(BaseOCModel):
    """A long-running corpus-scoped research job and its final report.

    The lifecycle is driven by :class:`ResearchReportService` and the
    ``run_deep_research`` Celery task. Status transitions:

        QUEUED -> RUNNING -> COMPLETED | FAILED | CANCELLED

    ``content`` is the rendered Markdown report (footnote-style citations);
    the structured ``findings`` / ``citations`` / ``tool_call_log`` JSON
    sidecars hold the agent's working state and the verifiable provenance
    used to build the report.
    """

    # ------------------------------------------------------------------
    # Identity & scope
    # ------------------------------------------------------------------
    corpus = models.ForeignKey(
        "corpuses.Corpus",
        on_delete=models.CASCADE,
        related_name="research_reports",
    )
    title = models.CharField(max_length=255, default="Untitled Research Report")
    slug = models.SlugField(
        max_length=160,
        unique=True,
        blank=True,
        db_index=True,
    )
    prompt = models.TextField(help_text="The user's research task")

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    status = models.CharField(
        max_length=20,
        choices=[(status.value, status.name) for status in JobStatus],
        default=JobStatus.QUEUED.value,
        db_index=True,
    )
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    last_progress_at = models.DateTimeField(null=True, blank=True, db_index=True)
    error_message = models.TextField(blank=True)
    cancel_requested = models.BooleanField(default=False)

    # ------------------------------------------------------------------
    # Budget
    # ------------------------------------------------------------------
    max_steps = models.IntegerField(
        default=getattr(
            settings, "DEEP_RESEARCH_DEFAULT_MAX_STEPS", DEFAULT_MAX_STEPS_FALLBACK
        ),
    )
    step_count = models.IntegerField(default=0)

    # ------------------------------------------------------------------
    # Output
    # ------------------------------------------------------------------
    content = models.TextField(
        blank=True, help_text="Rendered final markdown report with footnote citations"
    )
    plan = models.TextField(
        blank=True,
        help_text=(
            "The agent's living high-level plan. Re-injected into the system "
            "prompt at the start of every run so the original task and "
            "strategy survive context compaction and worker restarts."
        ),
    )
    memory = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "Durable key->entry memory store the agent writes to offload "
            "content beyond the context window. Each entry is "
            "{content, updated_at}. Survives compaction and worker restarts."
        ),
    )
    findings = models.JSONField(
        default=list, blank=True, help_text="Structured scratchpad of agent findings"
    )
    citations = models.JSONField(
        default=list,
        blank=True,
        help_text="Ordered footnote table: [{footnote, annotation_id, document_id, page, raw_text, similarity_score}]",
    )
    tool_call_log = models.JSONField(
        default=list,
        blank=True,
        help_text="Per-step tool invocation summary",
    )
    model_usage = models.JSONField(
        default=dict, blank=True, help_text="Token counts, model/provider, est. cost"
    )
    warnings = models.JSONField(
        default=list,
        blank=True,
        help_text="Non-fatal warnings (e.g. ['budget_exhausted'])",
    )

    # ------------------------------------------------------------------
    # Provenance links
    # ------------------------------------------------------------------
    source_annotations = models.ManyToManyField(
        "annotations.Annotation",
        blank=True,
        related_name="cited_in_research_reports",
        help_text="Annotations cited in the final report",
    )
    source_documents = models.ManyToManyField(
        "documents.Document",
        blank=True,
        related_name="cited_in_research_reports",
        help_text="Documents touched (vector-search hits, summaries loaded, etc.)",
    )
    conversation = models.ForeignKey(
        "conversations.Conversation",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="research_reports",
        help_text="Chat conversation that kicked this off, if any",
    )
    originating_message = models.ForeignKey(
        "conversations.ChatMessage",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="triggered_research_reports",
        help_text="User chat message that triggered this run, if any",
    )

    objects = ResearchReportManager()  # type: ignore[misc]

    class Meta:
        ordering = ["-created"]
        indexes = [
            models.Index(fields=["corpus", "status"]),
            models.Index(fields=["creator", "-created"]),
            models.Index(fields=["status", "last_progress_at"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(max_steps__gt=0),
                name="research_report_max_steps_positive",
            ),
        ]

    def __str__(self) -> str:
        return f"ResearchReport({self.title!r}, status={self.status}, corpus={self.corpus_id})"

    # ------------------------------------------------------------------
    # Slug auto-generation (mirrors AgentConfiguration.save)
    # ------------------------------------------------------------------
    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.title) or "research-report"
            slug = base[:140]
            counter = 1
            while ResearchReport.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base[:140 - len(str(counter)) - 1]}-{counter}"
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)

    # ------------------------------------------------------------------
    # Derived properties
    # ------------------------------------------------------------------
    @property
    def duration_seconds(self) -> float | None:
        """Wall-clock run time, always derived from the timestamps — never stored.

        If this is ever converted to a stored field, any caller that sets
        ``started_at`` / ``completed_at`` directly (bypassing ``finalize()``)
        will need to set the stored field explicitly instead.
        """
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None

    @property
    def is_terminal(self) -> bool:
        return self.status in (
            JobStatus.COMPLETED.value,
            JobStatus.FAILED.value,
            JobStatus.CANCELLED.value,
        )
