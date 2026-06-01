from django.conf import settings as django_settings
from django.db import migrations, models


def seed_default_llm(apps, schema_editor):
    """Seed the singleton's ``default_llm`` from Django settings if set.

    Intentionally a no-op when ``DEFAULT_LLM`` is not defined, so existing
    deployments keep falling back to the Django settings default until an
    operator opts in via the admin / pipeline settings UI.

    One-shot semantics: re-running ``migrate`` after a value has already been
    persisted will NOT re-seed it (the existing value is preserved by the
    ``not instance.default_llm`` guard). Operators changing the default LLM
    should update via the admin / pipeline settings UI, not by re-running
    this migration.
    """
    PipelineSettings = apps.get_model("documents", "PipelineSettings")
    initial = getattr(django_settings, "DEFAULT_LLM", "")
    if not initial:
        return
    # PipelineSettings is a singleton, but query by lowest PK rather than a
    # hardcoded ``pk=1`` so the seed still finds the row if the singleton was
    # ever recreated with a different PK (matches ``get_instance()`` semantics).
    instance = PipelineSettings.objects.order_by("pk").first()
    if instance is None:
        return
    # Only write if the operator hasn't already configured a default LLM.
    if not instance.default_llm:
        instance.default_llm = initial
        instance.save(update_fields=["default_llm"])


class Migration(migrations.Migration):

    dependencies = [
        ("documents", "0039_add_preferred_enrichers_to_pipeline_settings"),
    ]

    operations = [
        migrations.AddField(
            model_name="pipelinesettings",
            name="default_llm",
            field=models.CharField(
                blank=True,
                default="",
                help_text=(
                    "Default LLM model spec (pydantic-ai '{provider}:{model}' "
                    "form, e.g. 'anthropic:claude-opus-4-6') for agents when "
                    "no per-corpus or per-agent override is set. Empty string "
                    "falls back to the Django settings default."
                ),
                max_length=128,
            ),
        ),
        migrations.RunPython(seed_default_llm, migrations.RunPython.noop),
    ]
