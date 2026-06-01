# Data migration: seed the default global "Location Tagger" agent.

import logging

from django.conf import settings
from django.db import migrations

logger = logging.getLogger(__name__)

LOCATION_TAGGER_NAME = "Location Tagger"
LOCATION_TAGGER_SLUG = "location-tagger"

# Fallback used only if ``settings.DEFAULT_LOCATION_TAGGER_INSTRUCTIONS`` is
# ever removed/renamed. A migration is a point-in-time snapshot and must not
# hard-fail a fresh ``migrate`` just because a runtime setting moved, so we
# read the rich prompt from settings when present (the live source of truth)
# but degrade to this concise instruction set rather than raising
# ``AttributeError`` on a brand-new database.
_FALLBACK_INSTRUCTIONS = (
    "You are the Location Tagger. Find every country, U.S. state, and city "
    "mentioned in the document and create annotations for them using the "
    "add_annotations_from_exact_strings tool with the labels OC_COUNTRY, "
    "OC_STATE, and OC_CITY. Copy each place name verbatim into exact_string, "
    "and pass hints ({'country': ..., 'state': ...}) so the geocoder can "
    "disambiguate ambiguous names like 'Paris' or 'Springfield'."
)


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
        # No superuser exists yet (e.g. migrations run before the first
        # superuser is seeded). Log it so operators know to (re)create the
        # default agent — silence here previously hid the skip entirely.
        logger.warning(
            "Skipping Location Tagger default-agent creation: no superuser "
            "exists yet. Re-run this migration or create the agent manually "
            "after seeding a superuser."
        )
        return

    # Idempotency keys off the unique ``slug`` column (not ``name``) so a
    # future display-name change can't silently create a duplicate row.
    if AgentConfiguration.objects.filter(slug=LOCATION_TAGGER_SLUG).exists():
        return

    instructions = getattr(
        settings, "DEFAULT_LOCATION_TAGGER_INSTRUCTIONS", _FALLBACK_INSTRUCTIONS
    )
    # Identity check (``is``, not ``==``) is intentional: ``getattr`` returns the
    # exact ``_FALLBACK_INSTRUCTIONS`` object only when the setting is missing, so
    # this distinguishes "setting absent" from "setting happens to equal the
    # fallback text".
    if instructions is _FALLBACK_INSTRUCTIONS:
        # The rich production prompt lives in settings; if it is absent (e.g. a
        # stripped-down CI image) we still create a working agent, but with the
        # concise fallback. Surface it so operators can patch the prompt rather
        # than silently shipping the degraded instructions.
        logger.warning(
            "DEFAULT_LOCATION_TAGGER_INSTRUCTIONS is not configured; creating "
            "the Location Tagger agent with the concise fallback prompt. Update "
            "the agent's system_instructions once the setting is available."
        )

    AgentConfiguration.objects.create(
        name=LOCATION_TAGGER_NAME,
        slug=LOCATION_TAGGER_SLUG,
        description=(
            "Automatically geocodes place names in documents, creating "
            "OC_COUNTRY / OC_STATE / OC_CITY annotations with coordinates."
        ),
        system_instructions=instructions,
        available_tools=["add_annotations_from_exact_strings"],
        # Intentionally empty: this agent runs unattended as a corpus action and
        # its only tool writes annotations the user can review/delete afterwards
        # — there is no destructive or irreversible call to gate behind an
        # approval prompt.
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
    AgentConfiguration.objects.filter(slug=LOCATION_TAGGER_SLUG).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("agents", "0014_agentconfiguration_preferred_llm"),
    ]

    operations = [
        migrations.RunPython(create_location_tagger_agent, reverse_migration),
    ]
