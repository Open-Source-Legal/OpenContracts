# Generated manually for data migration

from django.conf import settings
from django.db import migrations

LOCATION_TAGGER_NAME = "Location Tagger"
LOCATION_TAGGER_SLUG = "location-tagger"


def create_location_tagger_agent(apps, schema_editor):
    """Create the default global Location Tagger agent (idempotent).

    Mirrors ``0002_create_default_agents`` but is safe to run on databases that
    already have the agent (e.g. created manually). The historical model
    returned by ``apps.get_model`` does **not** run ``AgentConfiguration.save``,
    so the slug is set explicitly here — the live ``save()`` override that
    auto-generates slugs is unavailable in migrations and the slug column is
    unique / non-null.
    """
    AgentConfiguration = apps.get_model("agents", "AgentConfiguration")
    User = apps.get_model("users", "User")

    try:
        system_user = User.objects.filter(is_superuser=True).first()
    except Exception:  # pragma: no cover
        system_user = None

    if not system_user:  # pragma: no cover
        # No superuser exists yet; the agent can be created manually later.
        return

    if AgentConfiguration.objects.filter(
        scope="GLOBAL", name=LOCATION_TAGGER_NAME
    ).exists():
        return

    AgentConfiguration.objects.create(
        name=LOCATION_TAGGER_NAME,
        slug=LOCATION_TAGGER_SLUG,
        description=(
            "Automatically geocodes place names in documents, creating "
            "OC_COUNTRY / OC_STATE / OC_CITY annotations with coordinates."
        ),
        system_instructions=settings.DEFAULT_LOCATION_TAGGER_INSTRUCTIONS,
        available_tools=["add_annotations_from_exact_strings"],
        permission_required_tools=[],
        badge_config={
            "icon": "globe",
            "color": "#2E8B57",
            "label": "Location Tagger",
        },
        scope="GLOBAL",
        is_active=True,
        is_public=True,
        creator=system_user,
    )


def reverse_migration(apps, schema_editor):  # pragma: no cover
    """Remove the Location Tagger default agent."""
    AgentConfiguration = apps.get_model("agents", "AgentConfiguration")
    AgentConfiguration.objects.filter(
        scope="GLOBAL", name=LOCATION_TAGGER_NAME
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("agents", "0014_agentconfiguration_preferred_llm"),
    ]

    operations = [
        migrations.RunPython(create_location_tagger_agent, reverse_migration),
    ]
