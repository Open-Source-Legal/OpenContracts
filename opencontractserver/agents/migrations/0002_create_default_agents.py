# Generated manually for data migration

from django.conf import settings
from django.db import migrations


def create_default_agents(apps, schema_editor):
    """Create default global agents from settings."""
    AgentConfiguration = apps.get_model("agents", "AgentConfiguration")
    User = apps.get_model("users", "User")

    # Get first superuser or create a system user
    try:
        system_user = User.objects.filter(is_superuser=True).first()
        if not system_user:
            # If no superuser exists yet, skip creating default agents
            # They can be created manually or in a later migration
            return
    except Exception:
        # If User model doesn't exist or has issues, skip
        return

    # Document Agent
    AgentConfiguration.objects.create(
        name="Document Assistant",
        description="AI assistant for analyzing individual documents",
        system_instructions=settings.DEFAULT_DOCUMENT_AGENT_INSTRUCTIONS,
        available_tools=[
            "load_document_summary",
            "get_document_text_length",
            "similarity_search",
            "load_document_text",
            "search_exact_text",
            "get_document_notes",
        ],
        permission_required_tools=[],
        badge_config={
            "icon": "file-text",
            "color": "#4A90E2",
            "label": "Doc AI",
        },
        scope="GLOBAL",
        is_active=True,
        is_public=True,
        creator=system_user,
    )

    # Corpus Agent
    AgentConfiguration.objects.create(
        name="Corpus Assistant",
        description="AI assistant for analyzing collections of documents",
        system_instructions=settings.DEFAULT_CORPUS_AGENT_INSTRUCTIONS,
        available_tools=[
            "list_documents",
            "ask_document",
            "similarity_search",
        ],
        permission_required_tools=[],
        badge_config={
            "icon": "database",
            "color": "#8B5CF6",
            "label": "Corpus AI",
        },
        scope="GLOBAL",
        is_active=True,
        is_public=True,
        creator=system_user,
    )


def reverse_migration(apps, schema_editor):
    """Remove default agents."""
    AgentConfiguration = apps.get_model("agents", "AgentConfiguration")
    AgentConfiguration.objects.filter(
        name__in=["Document Assistant", "Corpus Assistant"]
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("agents", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(create_default_agents, reverse_migration),
    ]
