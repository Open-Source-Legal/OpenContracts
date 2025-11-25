from django.contrib.auth import get_user_model
from django.db import models
from django.db.models import Q
from guardian.models import GroupObjectPermissionBase, UserObjectPermissionBase

from opencontractserver.shared.Managers import BaseVisibilityManager
from opencontractserver.shared.Models import BaseOCModel

User = get_user_model()


class AgentConfigurationQuerySet(models.QuerySet):
    """QuerySet with permission filtering for AgentConfiguration."""

    def visible_to_user(self, user):
        """
        Return agents visible to the user:
        - All active global agents (public)
        - Corpus agents for corpuses the user can access
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

    def visible_to_user(self, user):
        """Override to use AgentConfigurationQuerySet's visible_to_user method."""
        return self.get_queryset().visible_to_user(user)


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

    # Manager
    objects = AgentConfigurationManager()

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=(
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
        scope_label = (
            f" ({self.corpus.title})" if self.scope == "CORPUS" else " (Global)"
        )
        return f"{self.name}{scope_label}"


class AgentConfigurationUserObjectPermission(UserObjectPermissionBase):
    """Permissions for AgentConfiguration objects at the user level."""

    content_object = models.ForeignKey("AgentConfiguration", on_delete=models.CASCADE)


class AgentConfigurationGroupObjectPermission(GroupObjectPermissionBase):
    """Permissions for AgentConfiguration objects at the group level."""

    content_object = models.ForeignKey("AgentConfiguration", on_delete=models.CASCADE)
