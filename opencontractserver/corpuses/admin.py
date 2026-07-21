from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from guardian.admin import GuardedModelAdmin

from opencontractserver.corpuses.models import (
    Corpus,
    CorpusAction,
    CorpusActionExecution,
    CorpusActionTemplate,
    CorpusCategory,
)
from opencontractserver.tasks.permissioning_tasks import make_corpus_public_task


@admin.register(Corpus)
class CorpusAdmin(GuardedModelAdmin):
    list_display_links = ["id", "title"]
    list_select_related = ("creator", "label_set")
    list_display = [
        "id",
        "display_icon",
        "is_public",
        "allow_comments",
        "title",
        "description",
        "backend_lock",
        "user_lock",
    ]
    search_fields = ["id", "title", "description", "creator__username"]
    list_filter = ("is_public", "created", "modified", "error", "backend_lock")
    actions = ["make_public"]
    raw_id_fields = ("creator", "user_lock", "label_set")
    date_hierarchy = "created"

    def display_icon(self, obj):
        if obj.icon:
            return mark_safe(f'<img src="{obj.icon.url}" width="50" height="50" />')
        return "No icon"

    display_icon.short_description = "Icon"  # type: ignore[attr-defined]

    def make_public(self, request, queryset):
        for corpus in queryset:
            make_corpus_public_task.si(corpus_id=corpus.pk).apply_async()
        self.message_user(
            request, f"Started making {queryset.count()} corpus(es) public."
        )

    make_public.short_description = "Make selected corpuses public"  # type: ignore[attr-defined]


@admin.register(CorpusCategory)
class CorpusCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "color", "icon", "sort_order", "created")
    list_editable = ("sort_order",)
    search_fields = ("name", "description")
    ordering = ("sort_order", "name")
    fieldsets = (
        (None, {"fields": ("name", "description")}),
        ("Appearance", {"fields": ("icon", "color", "sort_order")}),
    )


@admin.register(CorpusAction)
class CorpusActionAdmin(GuardedModelAdmin):
    list_display = ["id", "name", "corpus"]


@admin.register(CorpusActionTemplate)
class CorpusActionTemplateAdmin(admin.ModelAdmin):
    """Plain ModelAdmin (not GuardedModelAdmin) — CorpusActionTemplate has no
    django-guardian permission tables; it is a global/system-level model."""

    list_display = ["name", "trigger", "is_active", "sort_order", "disabled_on_clone"]
    list_filter = ["is_active", "trigger"]
    search_fields = ["name"]


@admin.register(CorpusActionExecution)
class CorpusActionExecutionAdmin(GuardedModelAdmin):
    """
    Admin for browsing corpus action execution trail.

    Provides rich filtering, search, and display of execution history
    for debugging and monitoring corpus actions.
    """

    list_display = [
        "id",
        "status_badge",
        "action_type",
        "corpus_action",
        "document_link",
        "corpus_link",
        "trigger",
        "duration_display",
        "queued_at",
    ]
    list_display_links = ["id", "status_badge"]
    list_filter = [
        "status",
        "action_type",
        "trigger",
        ("queued_at", admin.DateFieldListFilter),
        ("completed_at", admin.DateFieldListFilter),
        "corpus",
    ]
    search_fields = [
        "id",
        "corpus_action__name",
        "corpus__title",
        "document__title",
        "error_message",
    ]
    raw_id_fields = [
        "corpus_action",
        "document",
        "corpus",
        "creator",
        "agent_result",
        "extract",
        "analysis",
    ]
    readonly_fields = [
        "queued_at",
        "started_at",
        "completed_at",
        "duration_display",
        "wait_time_display",
        "affected_objects_display",
        "execution_metadata_display",
    ]
    date_hierarchy = "queued_at"
    list_select_related = ["corpus_action", "document", "corpus"]
    ordering = ["-queued_at"]

    fieldsets = (
        (
            "Execution Info",
            {
                "fields": (
                    "corpus_action",
                    "document",
                    "corpus",
                    "action_type",
                    "trigger",
                    "creator",
                )
            },
        ),
        (
            "Status & Timing",
            {
                "fields": (
                    "status",
                    "queued_at",
                    "started_at",
                    "completed_at",
                    "duration_display",
                    "wait_time_display",
                )
            },
        ),
        (
            "Results",
            {
                "fields": (
                    "affected_objects_display",
                    "agent_result",
                    "extract",
                    "analysis",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "Error Details",
            {
                "fields": ("error_message", "error_traceback"),
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

    def status_badge(self, obj):
        """Display status as a colored badge."""
        colors = {
            "queued": "#6c757d",  # gray
            "running": "#007bff",  # blue
            "completed": "#28a745",  # green
            "failed": "#dc3545",  # red
            "skipped": "#ffc107",  # yellow
        }
        color = colors.get(obj.status, "#6c757d")
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; '
            'border-radius: 3px; font-size: 11px; font-weight: bold;">{}</span>',
            color,
            obj.get_status_display(),
        )

    status_badge.short_description = "Status"  # type: ignore[attr-defined]
    status_badge.admin_order_field = "status"  # type: ignore[attr-defined]

    def document_link(self, obj):
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

    document_link.short_description = "Document"  # type: ignore[attr-defined]

    def corpus_link(self, obj):
        """Link to the corpus in admin."""
        if obj.corpus:
            title = (
                obj.corpus.title[:20] + "..."
                if len(obj.corpus.title or "") > 20
                else obj.corpus.title
            )
            return format_html(
                '<a href="/admin/corpuses/corpus/{}/change/">{}</a>',
                obj.corpus_id,
                title or f"Corpus #{obj.corpus_id}",
            )
        return "-"

    corpus_link.short_description = "Corpus"  # type: ignore[attr-defined]

    def duration_display(self, obj):
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

    duration_display.short_description = "Duration"  # type: ignore[attr-defined]

    def wait_time_display(self, obj):
        """Display queue wait time."""
        wait = obj.wait_time_seconds
        if wait is not None:
            if wait < 1:
                return f"{wait * 1000:.0f}ms"
            elif wait < 60:
                return f"{wait:.1f}s"
            else:
                minutes = int(wait // 60)
                seconds = wait % 60
                return f"{minutes}m {seconds:.0f}s"
        return "-"

    wait_time_display.short_description = "Wait Time"  # type: ignore[attr-defined]

    def affected_objects_display(self, obj):
        """Display affected objects as formatted JSON."""
        if obj.affected_objects:
            import json

            formatted = json.dumps(obj.affected_objects, indent=2)
            return format_html("<pre>{}</pre>", formatted)
        return "None"

    affected_objects_display.short_description = "Affected Objects"  # type: ignore[attr-defined]

    def execution_metadata_display(self, obj):
        """Display execution metadata as formatted JSON."""
        if obj.execution_metadata:
            import json

            formatted = json.dumps(obj.execution_metadata, indent=2)
            return format_html("<pre>{}</pre>", formatted)
        return "None"

    execution_metadata_display.short_description = "Execution Metadata"  # type: ignore[attr-defined]

    def get_queryset(self, request):
        """Optimize queryset with select_related."""
        return (
            super()
            .get_queryset(request)
            .select_related("corpus_action", "document", "corpus", "creator")
        )
