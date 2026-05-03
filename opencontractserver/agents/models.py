from django.contrib.auth import get_user_model
from django.db import models
from django.db.models import Q
from django.utils.text import slugify
from guardian.models import GroupObjectPermissionBase, UserObjectPermissionBase

from opencontractserver.shared.Managers import BaseVisibilityManager
from opencontractserver.shared.Models import BaseOCModel

User = get_user_model()


class AgentConfigurationQuerySet(models.QuerySet):
    """QuerySet with permission filtering for AgentConfiguration."""

    def visible_to_user(self, user, lightweight: bool = False):
        """
        Return agents visible to the user:
        - All active global agents (public)
        - Corpus agents for corpuses the user can access

        ``lightweight`` is accepted for parity with ``BaseVisibilityManager``
        but unused — agent rows are small and have no heavy prefetches.
        """
        from opencontractserver.corpuses.models import Corpus

        if not user or not user.is_authenticated:
            # Anonymous users see only active global agents
            return self.filter(scope="GLOBAL", is_active=True)

        if user.is_superuser:
            # Superusers see all agents
            return self.all()

        # Authenticated users see:
        # 1. All active global agents
        # 2. Corpus agents for corpuses they can access
        accessible_corpuses = Corpus.objects.visible_to_user(user)

        return self.filter(
            Q(scope="GLOBAL", is_active=True)
            | Q(scope="CORPUS", is_active=True, corpus__in=accessible_corpuses)
        ).distinct()


class AgentConfigurationManager(BaseVisibilityManager):
    """Manager for AgentConfiguration with permission filtering."""

    def get_queryset(self):
        return AgentConfigurationQuerySet(self.model, using=self._db)

    def visible_to_user(self, user=None, lightweight: bool = False):
        return self.get_queryset().visible_to_user(user, lightweight=lightweight)


class AgentConfiguration(BaseOCModel):
    """
    Defines a bot/agent that can participate in conversations.
    Can be scoped globally or to a specific corpus.
    """

    SCOPE_CHOICES = (
        ("GLOBAL", "Global"),
        ("CORPUS", "Corpus-specific"),
    )

    # Identity
    name = models.CharField(max_length=255, help_text="Display name for this agent")
    slug = models.SlugField(
        max_length=128,
        unique=True,
        null=True,
        blank=True,
        db_index=True,
        help_text="URL-friendly identifier for mentions (e.g., 'research-assistant')",
    )
    description = models.TextField(
        blank=True, help_text="Description of agent's purpose and capabilities"
    )

    # Behavior
    system_instructions = models.TextField(
        help_text="System prompt/instructions for this agent"
    )
    available_tools = models.JSONField(
        default=list,
        help_text="List of tool identifiers this agent can use (e.g., ['similarity_search', 'load_document_text'])",
    )
    permission_required_tools = models.JSONField(
        default=list,
        help_text="Subset of tools that require explicit user permission to use",
    )

    # Display
    badge_config = models.JSONField(
        default=dict,
        help_text="Visual config: {'icon': 'bot', 'color': '#4A90E2', 'label': 'AI Assistant'}",
    )
    avatar_url = models.URLField(
        blank=True,
        null=True,
        help_text="URL to agent's avatar image",
    )

    # Scope
    scope = models.CharField(
        max_length=10,
        choices=SCOPE_CHOICES,
        default="GLOBAL",
    )
    corpus = models.ForeignKey(
        "corpuses.Corpus",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="agents",
        help_text="Corpus this agent belongs to (if scope=CORPUS)",
    )

    # Metadata
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this agent is active and can be used",
    )

    objects = AgentConfigurationManager()  # type: ignore[misc]  # intentional manager override

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(scope="GLOBAL", corpus__isnull=True)
                    | Q(scope="CORPUS", corpus__isnull=False)
                ),
                name="agent_scope_corpus_consistency",
            )
        ]
        indexes = [
            models.Index(fields=["scope", "is_active"]),
            models.Index(fields=["corpus", "is_active"]),
        ]
        permissions = (
            ("permission_agentconfiguration", "permission agentconfiguration"),
            ("publish_agentconfiguration", "publish agentconfiguration"),
            ("create_agentconfiguration", "create agentconfiguration"),
            ("read_agentconfiguration", "read agentconfiguration"),
            ("update_agentconfiguration", "update agentconfiguration"),
            ("remove_agentconfiguration", "delete agentconfiguration"),
        )

    def __str__(self):
        if self.scope == "CORPUS":
            # CheckConstraint above enforces corpus__isnull=False when
            # scope == "CORPUS", so this narrows safely for type-checking.
            assert self.corpus is not None
            scope_label = f" ({self.corpus.title})"
        else:
            scope_label = " (Global)"
        return f"{self.name}{scope_label}"

    def save(self, *args, **kwargs):
        """Auto-generate slug from name if not provided."""
        if not self.slug:
            base_slug = slugify(self.name)
            # Ensure uniqueness by appending a number if needed
            slug = base_slug
            counter = 1
            while (
                AgentConfiguration.objects.filter(slug=slug)
                .exclude(pk=self.pk)
                .exists()
            ):
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)


class AgentConfigurationUserObjectPermission(UserObjectPermissionBase):
    """Permissions for AgentConfiguration objects at the user level."""

    content_object = models.ForeignKey("AgentConfiguration", on_delete=models.CASCADE)


class AgentConfigurationGroupObjectPermission(GroupObjectPermissionBase):
    """Permissions for AgentConfiguration objects at the group level."""

    content_object = models.ForeignKey("AgentConfiguration", on_delete=models.CASCADE)


# --------------------------------------------------------------------------- #
# AgentActionResult - Stores results from agent-based corpus actions
# --------------------------------------------------------------------------- #


class AgentActionResultQuerySet(models.QuerySet):
    """QuerySet with permission filtering for AgentActionResult."""

    def visible_to_user(self, user, lightweight: bool = False):
        """
        Return results visible to the user based on corpus permissions.
        Users can see results for corpuses they have access to.

        ``lightweight`` is accepted for signature parity with
        ``BaseVisibilityManager`` and is unused for this model.
        """
        from opencontractserver.corpuses.models import Corpus

        if not user or not user.is_authenticated:
            # Anonymous users see results for public corpuses only
            return self.filter(corpus_action__corpus__is_public=True)

        if user.is_superuser:
            return self.all()

        # Users see results for corpuses they can access
        accessible_corpuses = Corpus.objects.visible_to_user(user)
        return self.filter(corpus_action__corpus__in=accessible_corpuses).distinct()


class AgentActionResultManager(BaseVisibilityManager):
    """Manager for AgentActionResult with permission filtering."""

    def get_queryset(self):
        return AgentActionResultQuerySet(self.model, using=self._db)

    def visible_to_user(self, user=None, lightweight: bool = False):
        return self.get_queryset().visible_to_user(user, lightweight=lightweight)


class AgentActionResult(BaseOCModel):
    """
    Stores results from agent-based corpus actions.
    One record per (corpus_action, document) execution.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        RUNNING = "running", "Running"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    corpus_action = models.ForeignKey(
        "corpuses.CorpusAction",
        on_delete=models.CASCADE,
        related_name="agent_results",
        help_text="The corpus action that triggered this execution",
    )
    document = models.ForeignKey(
        "documents.Document",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="agent_action_results",
        help_text="The document this action was run on (null for thread-based actions)",
    )
    conversation = models.ForeignKey(
        "conversations.Conversation",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="corpus_action_results",
        help_text="Conversation record containing the full agent interaction",
    )

    # Thread/message context (for NEW_THREAD and NEW_MESSAGE triggers)
    triggering_conversation = models.ForeignKey(
        "conversations.Conversation",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="triggered_agent_action_results",
        help_text="Thread that triggered this agent action (for thread-based triggers)",
    )
    triggering_message = models.ForeignKey(
        "conversations.ChatMessage",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="triggered_agent_action_results",
        help_text="Message that triggered this agent action (for NEW_MESSAGE trigger)",
    )

    # Execution tracking
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    # Results
    agent_response = models.TextField(
        blank=True,
        help_text="Final response content from the agent",
    )
    tools_executed = models.JSONField(
        default=list,
        blank=True,
        help_text="List of tools executed: [{name, args, result, timestamp}]",
    )
    error_message = models.TextField(
        blank=True,
        help_text="Error message if status is FAILED",
    )

    # Audit trail
    execution_metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional execution metadata (model used, token counts, etc.)",
    )

    # Manager (django-stubs flags re-declaring ``objects`` as overriding a
    # class variable; intentional manager override).
    objects = AgentActionResultManager()  # type: ignore[misc]

    class Meta:
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["corpus_action", "document"]),
            models.Index(fields=["status"]),
            models.Index(fields=["started_at"]),
            # Index for thread-based queries
            models.Index(fields=["corpus_action", "triggering_conversation"]),
        ]
        # Unique constraints: prevent duplicate executions
        # Separate constraints for document-based vs thread-based actions
        constraints = [
            # For document-based actions: one result per (corpus_action, document)
            models.UniqueConstraint(
                fields=["corpus_action", "document"],
                condition=models.Q(document__isnull=False),
                name="unique_corpus_action_document_result",
            ),
            # For thread-based actions: one result per (corpus_action, triggering_conversation, triggering_message)
            # Note: triggering_message may be null for NEW_THREAD trigger
            models.UniqueConstraint(
                fields=[
                    "corpus_action",
                    "triggering_conversation",
                    "triggering_message",
                ],
                condition=models.Q(triggering_conversation__isnull=False),
                name="unique_corpus_action_thread_result",
            ),
        ]
        permissions = (
            ("permission_agentactionresult", "permission agentactionresult"),
            ("publish_agentactionresult", "publish agentactionresult"),
            ("create_agentactionresult", "create agentactionresult"),
            ("read_agentactionresult", "read agentactionresult"),
            ("update_agentactionresult", "update agentactionresult"),
            ("remove_agentactionresult", "delete agentactionresult"),
        )

    def __str__(self):
        if self.document_id:
            target = f"doc:{self.document_id}"
        elif self.triggering_conversation_id:
            target = f"thread:{self.triggering_conversation_id}"
        else:
            target = "unknown"
        return (
            f"AgentActionResult({self.corpus_action.name} on {target}: {self.status})"
        )

    @property
    def duration_seconds(self) -> float | None:
        """Calculate execution duration in seconds."""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None


class AgentActionResultUserObjectPermission(UserObjectPermissionBase):
    """Permissions for AgentActionResult objects at the user level."""

    content_object = models.ForeignKey("AgentActionResult", on_delete=models.CASCADE)


class AgentActionResultGroupObjectPermission(GroupObjectPermissionBase):
    """Permissions for AgentActionResult objects at the group level."""

    content_object = models.ForeignKey("AgentActionResult", on_delete=models.CASCADE)
