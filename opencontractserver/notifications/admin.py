from django.contrib import admin

from opencontractserver.notifications.models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    """Admin interface for Notification model."""

    list_display = (
        "id",
        "recipient",
        "notification_type",
        "is_read",
        "created_at",
        "actor",
    )
    list_filter = (
        "notification_type",
        "is_read",
        "created_at",
    )
    search_fields = (
        "recipient__username",
        "actor__username",
    )
    readonly_fields = (
        "created_at",
        "modified",
    )
    raw_id_fields = (
        "recipient",
        "actor",
        "message",
        "conversation",
    )
    date_hierarchy = "created_at"
    ordering = ("-created_at",)

    fieldsets = (
        (
            "Basic Information",
            {
                "fields": (
                    "recipient",
                    "notification_type",
                    "is_read",
                )
            },
        ),
        (
            "Related Objects",
            {
                "fields": (
                    "message",
                    "conversation",
                    "actor",
                )
            },
        ),
        (
            "Additional Data",
            {"fields": ("data",)},
        ),
        (
            "Timestamps",
            {
                "fields": (
                    "created_at",
                    "modified",
                )
            },
        ),
    )
