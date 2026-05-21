from django.conf import settings as django_settings
from django.db import migrations

import opencontractserver.shared.fields


def seed_preferred_enrichers(apps, schema_editor):
    """Seed the singleton's ``preferred_enrichers`` from Django settings if set.

    Intentionally a no-op when ``PREFERRED_ENRICHERS`` is empty or undefined,
    so existing deployments keep ingest-time enrichment disabled (opt-in)
    until an operator configures it.

    One-shot semantics: re-running ``migrate`` after a value has already been
    persisted will NOT re-seed it (the ``not instance.preferred_enrichers``
    guard preserves the existing value). Operators changing enrichers should
    update via the admin / pipeline settings UI, not by re-running this
    migration.
    """
    PipelineSettings = apps.get_model("documents", "PipelineSettings")
    initial = getattr(django_settings, "PREFERRED_ENRICHERS", {})
    if not initial:
        return
    # The singleton lives at pk=1. ``PipelineSettings.get_instance()`` is the
    # runtime accessor but is not safely callable here: it lives on the live
    # model, whereas migrations must use the historical model from
    # ``apps.get_model``. Querying pk=1 directly matches the preceding
    # pipeline-settings migrations (e.g. 0037/0038).
    instance = PipelineSettings.objects.filter(pk=1).first()
    if instance is None:
        return
    # Only write if the operator hasn't already configured enrichers.
    if not instance.preferred_enrichers:
        instance.preferred_enrichers = initial
        instance.save(update_fields=["preferred_enrichers"])


class Migration(migrations.Migration):

    dependencies = [
        ("documents", "0038_documentpath_visibility_compound_index"),
    ]

    operations = [
        migrations.AddField(
            model_name="pipelinesettings",
            name="preferred_enrichers",
            field=opencontractserver.shared.fields.NullableJSONField(
                blank=True,
                default=dict,
                help_text=(
                    "Mapping of MIME types to ordered lists of enricher class "
                    "paths (the enrichment chain run between parsing and "
                    "persistence)"
                ),
            ),
        ),
        migrations.RunPython(
            seed_preferred_enrichers,
            migrations.RunPython.noop,
        ),
    ]
