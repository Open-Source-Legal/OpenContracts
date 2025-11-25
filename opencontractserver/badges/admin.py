from django.contrib import admin

from opencontractserver.badges.models import Badge, UserBadge


@admin.register(Badge)
class BadgeAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "badge_type",
        "corpus",
        "is_auto_awarded",
        "color",
        "created",
    )
    list_filter = ("badge_type", "is_auto_awarded", "created")
    search_fields = ("name", "description")
    readonly_fields = ("created", "modified")
    fieldsets = (
        (
            "Basic Information",
            {
                "fields": (
                    "name",
                    "description",
                    "icon",
                    "color",
                )
            },
        ),
        (
            "Configuration",
            {
                "fields": (
                    "badge_type",
                    "corpus",
                    "is_auto_awarded",
                    "criteria_config",
                )
            },
        ),
        (
            "Permissions",
            {"fields": ("creator", "is_public")},
        ),
        (
            "Timestamps",
            {
                "fields": ("created", "modified"),
                "classes": ("collapse",),
            },
        ),
    )


@admin.register(UserBadge)
class UserBadgeAdmin(admin.ModelAdmin):
    list_display = ("user", "badge", "corpus", "awarded_at", "awarded_by")
    list_filter = ("awarded_at", "badge__badge_type")
    search_fields = ("user__username", "badge__name")
    readonly_fields = ("awarded_at",)
    autocomplete_fields = ("user", "badge", "awarded_by", "corpus")
