from django.contrib import admin
from guardian.admin import GuardedModelAdmin

from opencontractserver.agents.models import AgentConfiguration


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
