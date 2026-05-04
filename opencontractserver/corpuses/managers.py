"""
Custom managers and QuerySets for corpus models.

This module provides optimized query methods for CorpusActionExecution,
supporting efficient filtering, aggregation, and permission-aware queries.
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING, Any

from django.db import models
from django.utils import timezone

from opencontractserver.shared.Managers import BaseVisibilityManager

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser


class CorpusActionExecutionQuerySet(models.QuerySet):
    """Optimized querysets for action trail queries."""

    def for_corpus(self, corpus_id: int) -> CorpusActionExecutionQuerySet:
        """Get executions for a corpus, uses denormalized corpus field."""
        return self.filter(corpus_id=corpus_id)

    def for_document(self, document_id: int) -> CorpusActionExecutionQuerySet:
        """Get all action executions that affected a document."""
        return self.filter(document_id=document_id)

    def by_type(self, action_type: str) -> CorpusActionExecutionQuerySet:
        """Filter by action type (fieldset/analyzer/agent)."""
        return self.filter(action_type=action_type)

    def pending(self) -> CorpusActionExecutionQuerySet:
        """Get executions that haven't completed yet."""
        return self.filter(status__in=["queued", "running"])

    def failed(self) -> CorpusActionExecutionQuerySet:
        """Get failed executions for retry/monitoring."""
        return self.filter(status="failed")

    def recent(self, hours: int = 24) -> CorpusActionExecutionQuerySet:
        """Get recent executions within time window."""
        cutoff = timezone.now() - timedelta(hours=hours)
        return self.filter(queued_at__gte=cutoff)

    def with_stats(self) -> CorpusActionExecutionQuerySet:
        """Annotate with computed fields for display."""
        return self.annotate(
            duration=models.ExpressionWrapper(
                models.F("completed_at") - models.F("started_at"),
                output_field=models.DurationField(),
            ),
            wait_time=models.ExpressionWrapper(
                models.F("started_at") - models.F("queued_at"),
                output_field=models.DurationField(),
            ),
        )

    def summary_by_status(self) -> dict[str, int]:
        """
        Get execution count summary by status.

        Returns: {"queued": 5, "running": 2, "completed": 100, "failed": 3}
        """
        return dict(
            self.values("status")
            .annotate(count=models.Count("id"))
            .values_list("status", "count")
        )

    def summary_by_action(self) -> models.QuerySet[Any]:
        """
        Get execution stats grouped by action.

        Returns QuerySet with corpus_action_id, action_name, total, completed,
        failed, avg_duration.
        """
        return (
            self.values("corpus_action_id", "corpus_action__name")
            .annotate(
                total=models.Count("id"),
                completed=models.Count("id", filter=models.Q(status="completed")),
                failed=models.Count("id", filter=models.Q(status="failed")),
                avg_duration=models.Avg(
                    models.F("completed_at") - models.F("started_at"),
                    filter=models.Q(
                        completed_at__isnull=False, started_at__isnull=False
                    ),
                ),
            )
            .order_by("-total")
        )


class CorpusActionExecutionManager(BaseVisibilityManager):
    """
    Manager with permission-aware filtering.

    Inherits visible_to_user() from BaseVisibilityManager which provides:
    - Superusers see everything
    - Anonymous users see only public objects
    - Authenticated users see: public, objects they created, or objects with
      explicit permissions

    The custom QuerySet methods are exposed via get_queryset() which returns
    CorpusActionExecutionQuerySet, allowing chaining like:
        CorpusActionExecution.objects.visible_to_user(user).for_corpus(id).pending()
    """

    def get_queryset(self) -> CorpusActionExecutionQuerySet:
        return CorpusActionExecutionQuerySet(self.model, using=self._db)

    def for_corpus(self, corpus_id: int) -> CorpusActionExecutionQuerySet:
        return self.get_queryset().for_corpus(corpus_id)

    def for_document(self, document_id: int) -> CorpusActionExecutionQuerySet:
        return self.get_queryset().for_document(document_id)

    def by_type(self, action_type: str) -> CorpusActionExecutionQuerySet:
        return self.get_queryset().by_type(action_type)

    def pending(self) -> CorpusActionExecutionQuerySet:
        return self.get_queryset().pending()

    def failed(self) -> CorpusActionExecutionQuerySet:
        return self.get_queryset().failed()

    def recent(self, hours: int = 24) -> CorpusActionExecutionQuerySet:
        return self.get_queryset().recent(hours)

    def visible_to_user(
        self,
        user: AbstractBaseUser | None = None,
        lightweight: bool = False,
        with_doc_label_annotations: bool = False,
    ) -> CorpusActionExecutionQuerySet:
        """
        Override to return our custom QuerySet type while preserving permission
        logic.

        This allows chaining: .visible_to_user(user).for_corpus(id).pending()

        ``lightweight`` and ``with_doc_label_annotations`` are forwarded to
        ``BaseVisibilityManager`` for signature parity but have no effect on
        this model (no heavy prefetches involved).
        """
        # Get the base filtered queryset from parent
        base_qs = super().visible_to_user(user, lightweight=lightweight)
        # If base_qs is already our custom QuerySet type, return it directly
        # to avoid creating a subquery with pk__in
        if isinstance(base_qs, CorpusActionExecutionQuerySet):
            return base_qs
        # Otherwise, re-apply through our custom queryset to enable custom methods
        return self.get_queryset().filter(pk__in=base_qs.values("pk"))
