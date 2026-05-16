# Backfill any NULL agent slugs left by migration-context seeders that bypassed
# the model's ``save()`` override, then tighten the column to NOT NULL so a
# future seeder regression fails at the DB instead of crashing the UI.

from django.db import migrations, models
from django.utils.text import slugify


def backfill_missing_agent_slugs(apps, schema_editor):  # pragma: no cover
    """Populate ``slug`` for any AgentConfiguration row where it is NULL.

    Mirrors the ``0005`` backfill but covers agents created by later seeding
    migrations (``0010``, ``0011``) that used ``apps.get_model()`` — those
    historical model classes lacked the ``save()`` override that auto-builds
    slugs, leaving them NULL.
    """
    AgentConfiguration = apps.get_model("agents", "AgentConfiguration")

    for agent in AgentConfiguration.objects.filter(slug__isnull=True):
        base_slug = slugify(agent.name) if agent.name else "agent"
        slug = base_slug
        counter = 1
        # Uniqueness against all rows (including those already migrated).
        while (
            AgentConfiguration.objects.filter(slug=slug)
            .exclude(pk=agent.pk)
            .exists()
        ):
            slug = f"{base_slug}-{counter}"
            counter += 1
        agent.slug = slug
        agent.save(update_fields=["slug"])


def reverse_backfill(apps, schema_editor):  # pragma: no cover
    """No-op: we don't want to re-introduce NULL slugs on reverse."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("agents", "0012_update_corpus_agent_prompt"),
    ]

    operations = [
        # 1. Backfill any lingering NULL slugs so the AlterField below
        #    doesn't fail with an IntegrityError on existing deployments.
        migrations.RunPython(backfill_missing_agent_slugs, reverse_backfill),
        # 2. Tighten the column. ``blank=True`` is kept because the live
        #    ``save()`` override fills in the value before super().save();
        #    only the DB-level NOT NULL guarantee is new.
        migrations.AlterField(
            model_name="agentconfiguration",
            name="slug",
            field=models.SlugField(
                blank=True,
                db_index=True,
                help_text=(
                    "URL-friendly identifier for mentions "
                    "(e.g., 'research-assistant')"
                ),
                max_length=128,
                unique=True,
            ),
        ),
    ]
