from django.conf import settings as django_settings
from django.db import migrations, models


def seed_default_reranker(apps, schema_editor):
    """Seed the singleton's ``default_reranker`` from Django settings if set.

    Intentionally a no-op when ``DEFAULT_RERANKER`` is not defined, so
    existing deployments keep reranking disabled until an operator opts in.

    One-shot semantics: re-running ``migrate`` after a value has already been
    persisted will NOT re-seed it (the existing value is preserved by the
    ``not instance.default_reranker`` guard). Operators changing rerankers
    should update via the admin / pipeline settings UI, not by re-running
    this migration.
    """
    PipelineSettings = apps.get_model("documents", "PipelineSettings")
    initial = getattr(django_settings, "DEFAULT_RERANKER", "")
    if not initial:
        return
    instance = PipelineSettings.objects.filter(pk=1).first()
    if instance is None:
        return
    # Only write if the operator hasn't already configured a reranker.
    if not instance.default_reranker:
        instance.default_reranker = initial
        instance.save(update_fields=["default_reranker"])


class Migration(migrations.Migration):

    dependencies = [
        ("documents", "0036_add_ingestion_source_and_lineage_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="pipelinesettings",
            name="default_reranker",
            field=models.CharField(
                blank=True,
                default="",
                help_text=(
                    "Default post-retrieval reranker class path. Empty "
                    "string disables reranking (first-stage vector / "
                    "hybrid search only)."
                ),
                max_length=512,
            ),
        ),
        migrations.RunPython(seed_default_reranker, migrations.RunPython.noop),
    ]
