"""Initial migration for the LLM configuration system.

Creates ``LLMModel`` (admin-curated rows) and ``LLMConfigSettings`` (singleton),
then seeds the singleton with an empty config. The default-model FK is added in
a second ``CreateModel`` step so the ``LLMModel`` table exists when Django
generates the FK constraint.
"""

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion

import opencontractserver.shared.fields


def create_llm_config_settings_singleton(apps, schema_editor):
    """Idempotently create the LLMConfigSettings singleton row."""
    LLMConfigSettings = apps.get_model("llms", "LLMConfigSettings")
    if not LLMConfigSettings.objects.exists():
        LLMConfigSettings.objects.create(id=1, provider_configs={})


def reverse_create_singleton(apps, schema_editor):
    LLMConfigSettings = apps.get_model("llms", "LLMConfigSettings")
    LLMConfigSettings.objects.all().delete()


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="LLMModel",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "provider_key",
                    models.CharField(
                        db_index=True,
                        help_text=(
                            "Stable provider key, validated against the "
                            "LLMProviderRegistry."
                        ),
                        max_length=64,
                    ),
                ),
                (
                    "model_name",
                    models.CharField(
                        help_text="Provider's raw model identifier (e.g. 'gpt-4o-mini').",
                        max_length=255,
                    ),
                ),
                (
                    "display_name",
                    models.CharField(
                        help_text="Human label shown in the column editor.",
                        max_length=255,
                    ),
                ),
                ("description", models.TextField(blank=True, default="")),
                (
                    "is_enabled",
                    models.BooleanField(
                        db_index=True,
                        default=True,
                        help_text=(
                            "Disable to hide from column editors without deleting "
                            "the row."
                        ),
                    ),
                ),
                ("supports_vision", models.BooleanField(default=False)),
                ("supports_tools", models.BooleanField(default=True)),
                ("supports_structured_output", models.BooleanField(default=True)),
                (
                    "max_context_tokens",
                    models.PositiveIntegerField(blank=True, null=True),
                ),
                ("default_temperature", models.FloatField(default=0.3)),
                (
                    "extra_settings",
                    opencontractserver.shared.fields.NullableJSONField(
                        blank=True,
                        default=dict,
                        help_text=(
                            "Passthrough kwargs forwarded to pydantic-ai at "
                            "invocation time."
                        ),
                    ),
                ),
                ("created", models.DateTimeField(auto_now_add=True)),
                ("modified", models.DateTimeField(auto_now=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="llm_models_created",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "LLM Model",
                "verbose_name_plural": "LLM Models",
                "ordering": ("provider_key", "display_name"),
            },
        ),
        migrations.AddConstraint(
            model_name="llmmodel",
            constraint=models.UniqueConstraint(
                fields=("provider_key", "model_name"),
                name="llmmodel_unique_provider_model",
            ),
        ),
        migrations.CreateModel(
            name="LLMConfigSettings",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "provider_configs",
                    opencontractserver.shared.fields.NullableJSONField(
                        blank=True,
                        default=dict,
                        help_text=(
                            "Non-secret per-provider configuration, keyed by "
                            "provider key."
                        ),
                    ),
                ),
                (
                    "encrypted_secrets",
                    models.BinaryField(
                        blank=True,
                        null=True,
                        help_text=(
                            "Fernet-encrypted JSON: "
                            "{provider_key: {credential_field: value}}"
                        ),
                    ),
                ),
                ("modified", models.DateTimeField(auto_now=True, db_index=True)),
                (
                    "default_model",
                    models.ForeignKey(
                        blank=True,
                        help_text=(
                            "Fallback model when a Column has no preferred_llm_model."
                        ),
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="default_for_settings",
                        to="llms.llmmodel",
                    ),
                ),
                (
                    "modified_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="llm_config_settings_modifications",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "LLM Configuration Settings",
                "verbose_name_plural": "LLM Configuration Settings",
            },
        ),
        migrations.AddConstraint(
            model_name="llmconfigsettings",
            constraint=models.CheckConstraint(
                condition=models.Q(("pk", 1)),
                name="llm_config_settings_singleton_pk",
            ),
        ),
        migrations.RunPython(
            create_llm_config_settings_singleton,
            reverse_create_singleton,
        ),
    ]
