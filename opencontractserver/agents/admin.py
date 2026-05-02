from django.contrib import admin
from django.db.models import QuerySet
from django.http import HttpRequest
from django.utils.html import format_html
from guardian.admin import GuardedModelAdmin

from opencontractserver.agents.models import AgentActionResult, AgentConfiguration


@admin.register(AgentConfiguration)
class AgentConfigurationAdmin(GuardedModelAdmin):
    list_display = (
        "name",
        "scope",
        "corpus",
        "is_active",
        "creator",
        "created",
        "modified",
    )
    list_filter = ("scope", "is_active", "created", "modified")
    search_fields = ("name", "description")
    readonly_fields = ("created", "modified")
    fieldsets = (
        ("Identity", {"fields": ("name", "description")}),
        (
            "Behavior",
            {
                "fields": (
                    "system_instructions",
                    "available_tools",
                    "permission_required_tools",
                )
            },
        ),
        ("Display", {"fields": ("badge_config", "avatar_url")}),
        ("Scope", {"fields": ("scope", "corpus")}),
        ("Metadata", {"fields": ("is_active", "creator", "created", "modified")}),
    )


@admin.register(AgentActionResult)
class AgentActionResultAdmin(GuardedModelAdmin):
    """
    Admin for browsing agent action execution results.

    Provides rich filtering, search, and display for debugging
    and monitoring agent-based corpus actions.
    """

    list_display = [
        "id",
        "status_badge",
        "corpus_action_link",
        "document_link",
        "tools_count",
        "duration_display",
        "started_at",
        "creator",
    ]
    list_display_links = ["id", "status_badge"]
    list_filter = [
        "status",
        ("started_at", admin.DateFieldListFilter),
        ("completed_at", admin.DateFieldListFilter),
        "corpus_action__corpus",
    ]
    search_fields = [
        "id",
        "corpus_action__name",
        "corpus_action__corpus__title",
        "document__title",
        "agent_response",
        "error_message",
    ]
    raw_id_fields = [
        "corpus_action",
        "document",
        "conversation",
        "creator",
    ]
    readonly_fields = [
        "started_at",
        "completed_at",
        "duration_display",
        "tools_executed_display",
        "execution_metadata_display",
        "agent_response_display",
    ]
    date_hierarchy = "started_at"
    list_select_related = [
        "corpus_action",
        "corpus_action__corpus",
        "document",
        "creator",
    ]
    ordering = ["-started_at"]

    fieldsets = (
        (
            "Execution Info",
            {
                "fields": (
                    "corpus_action",
                    "document",
                    "conversation",
                    "creator",
                )
            },
        ),
        (
            "Status & Timing",
            {
                "fields": (
                    "status",
                    "started_at",
                    "completed_at",
                    "duration_display",
                )
            },
        ),
        (
            "Agent Response",
            {
                "fields": ("agent_response_display",),
            },
        ),
        (
            "Tools Executed",
            {
                "fields": ("tools_executed_display",),
                "classes": ("collapse",),
            },
        ),
        (
            "Error Details",
            {
                "fields": ("error_message",),
                "classes": ("collapse",),
            },
        ),
        (
            "Metadata",
            {
                "fields": ("execution_metadata_display",),
                "classes": ("collapse",),
            },
        ),
    )

    def status_badge(self, obj: AgentActionResult) -> str:
        """Display status as a colored badge."""
        colors = {
            "pending": "#6c757d",  # gray
            "running": "#007bff",  # blue
            "completed": "#28a745",  # green
            "failed": "#dc3545",  # red
        }
        color = colors.get(obj.status, "#6c757d")
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; '
            'border-radius: 3px; font-size: 11px; font-weight: bold;">{}</span>',
            color,
            obj.get_status_display(),
        )

    status_badge.short_description = "Status"
    status_badge.admin_order_field = "status"

    def corpus_action_link(self, obj: AgentActionResult) -> str:
        """Link to the corpus action in admin."""
        if obj.corpus_action:
            name = (
                obj.corpus_action.name[:25] + "..."
                if len(obj.corpus_action.name or "") > 25
                else obj.corpus_action.name
            )
            return format_html(
                '<a href="/admin/corpuses/corpusaction/{}/change/">{}</a>',
                obj.corpus_action_id,
                name or f"Action #{obj.corpus_action_id}",
            )
        return "-"

    corpus_action_link.short_description = "Corpus Action"

    def document_link(self, obj: AgentActionResult) -> str:
        """Link to the document in admin."""
        if obj.document:
            title = (
                obj.document.title[:30] + "..."
                if len(obj.document.title or "") > 30
                else obj.document.title
            )
            return format_html(
                '<a href="/admin/documents/document/{}/change/">{}</a>',
                obj.document_id,
                title or f"Doc #{obj.document_id}",
            )
        return "-"

    document_link.short_description = "Document"

    def tools_count(self, obj: AgentActionResult) -> str:
        """Display count of tools executed."""
        if obj.tools_executed:
            count = len(obj.tools_executed)
            return format_html(
                '<span style="background-color: #17a2b8; color: white; '
                'padding: 2px 6px; border-radius: 10px; font-size: 11px;">{}</span>',
                count,
            )
        return "0"

    tools_count.short_description = "Tools"

    def duration_display(self, obj: AgentActionResult) -> str:
        """Display execution duration."""
        duration = obj.duration_seconds
        if duration is not None:
            if duration < 1:
                return f"{duration * 1000:.0f}ms"
            elif duration < 60:
                return f"{duration:.1f}s"
            else:
                minutes = int(duration // 60)
                seconds = duration % 60
                return f"{minutes}m {seconds:.0f}s"
        return "-"

    duration_display.short_description = "Duration"

    def agent_response_display(self, obj: AgentActionResult) -> str:
        """Display agent response with formatting."""
        if obj.agent_response:
            # Truncate very long responses in admin
            response = obj.agent_response
            if len(response) > 5000:
                response = response[:5000] + "\n\n... [truncated]"
            return format_html("<pre style='white-space: pre-wrap;'>{}</pre>", response)
        return "No response"

    agent_response_display.short_description = "Agent Response"

    def tools_executed_display(self, obj: AgentActionResult) -> str:
        """Display tools executed as formatted JSON."""
        if obj.tools_executed:
            import json

            formatted = json.dumps(obj.tools_executed, indent=2)
            # Truncate if very large
            if len(formatted) > 10000:
                formatted = formatted[:10000] + "\n\n... [truncated]"
            return format_html("<pre>{}</pre>", formatted)
        return "None"

    tools_executed_display.short_description = "Tools Executed"

    def execution_metadata_display(self, obj: AgentActionResult) -> str:
        """Display execution metadata as formatted JSON."""
        if obj.execution_metadata:
            import json

            formatted = json.dumps(obj.execution_metadata, indent=2)
            return format_html("<pre>{}</pre>", formatted)
        return "None"

    execution_metadata_display.short_description = "Execution Metadata"

    def get_queryset(self, request: HttpRequest) -> QuerySet[AgentActionResult]:
        """Optimize queryset with select_related."""
        return (
            super()
            .get_queryset(request)
            .select_related(
                "corpus_action",
                "corpus_action__corpus",
                "document",
                "creator",
            )
        )
