"""Initial schema for the llm_configs app.

Creates:
* ``RegisteredLLM`` — admin-curated, immutable version-chain rows.
* ``LLMSettings`` — singleton (pk=1) holding global LLM configuration.

The migration also seeds the empty ``LLMSettings`` singleton so callers can
unconditionally call ``LLMSettings.get_instance()`` after deploy. It does
*not* seed any ``RegisteredLLM`` rows; that happens in a Phase-2 follow-up
migration once the provider classes (``OpenAIProvider``, etc.) exist, so
the seeded ``provider_class_path`` is guaranteed to resolve.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

import opencontractserver.shared.fields


def create_llm_settings_singleton(apps, schema_editor):
    """Create the singleton LLMSettings row with all-default values."""
    LLMSettings = apps.get_model("llm_configs", "LLMSettings")
    if not LLMSettings.objects.exists():
        LLMSettings.objects.create(
            id=1,
            provider_settings={},
            encrypted_secrets=None,
            default_extract_llm=None,
        )


def reverse_create_singleton(apps, schema_editor):
    LLMSettings = apps.get_model("llm_configs", "LLMSettings")
    LLMSettings.objects.all().delete()


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # ----------------------------------------------------------------
        # RegisteredLLM
        # ----------------------------------------------------------------
        migrations.CreateModel(
            name="RegisteredLLM",
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
                ("backend_lock", models.BooleanField(db_index=True, default=False)),
                ("is_public", models.BooleanField(default=False)),
                ("created", models.DateTimeField(auto_now_add=True)),
                ("modified", models.DateTimeField(auto_now=True)),
                (
                    "provider_class_path",
                    models.CharField(
                        max_length=256,
                        help_text=(
                            "Full Python class path of the LLMProvider class "
                            "(e.g. 'opencontractserver.llms.providers.anthropic."
                            "AnthropicProvider')."
                        ),
                    ),
                ),
                (
                    "model_id",
                    models.CharField(
                        max_length=128,
                        help_text=(
                            "Provider-native model identifier "
                            "(e.g. 'gpt-4o-mini', 'claude-opus-4-7'). Combined "
                            "with the provider's pydantic-ai prefix to form "
                            "the model string passed to pydantic-ai (e.g. "
                            "'openai:gpt-4o-mini')."
                        ),
                    ),
                ),
                (
                    "display_name",
                    models.CharField(
                        max_length=256,
                        help_text=(
                            "Human-readable label shown in admin and column " "pickers."
                        ),
                    ),
                ),
                (
                    "is_enabled",
                    models.BooleanField(
                        default=True,
                        help_text=(
                            "If False, this version is greyed out in pickers "
                            "but still referenceable for historical "
                            "Datacells/Columns."
                        ),
                    ),
                ),
                (
                    "is_archived",
                    models.BooleanField(
                        default=False,
                        help_text=(
                            "If True, this version is hidden from pickers "
                            "entirely. Historical references survive via "
                            "PROTECT FKs."
                        ),
                    ),
                ),
                (
                    "context_window",
                    models.IntegerField(
                        blank=True,
                        null=True,
                        help_text=(
                            "Override for context window size (tokens). When "
                            "NULL, the resolver falls back to "
                            "opencontractserver.llms.context_guardrails."
                            "MODEL_CONTEXT_WINDOWS."
                        ),
                    ),
                ),
                (
                    "supports_structured_output",
                    models.BooleanField(
                        default=True,
                        help_text=(
                            "Whether this model supports pydantic-ai "
                            "structured output."
                        ),
                    ),
                ),
                (
                    "supports_tools",
                    models.BooleanField(
                        default=True,
                        help_text=(
                            "Whether this model supports tool/function calling."
                        ),
                    ),
                ),
                (
                    "max_output_tokens",
                    models.IntegerField(
                        blank=True,
                        null=True,
                        help_text=("Optional max_tokens cap to apply on every call."),
                    ),
                ),
                (
                    "temperature_default",
                    models.FloatField(
                        blank=True,
                        null=True,
                        help_text=(
                            "Optional default temperature. NULL means "
                            "callers/extractors use their own defaults "
                            "(e.g. EXTRACT_DEFAULT_TEMPERATURE)."
                        ),
                    ),
                ),
                (
                    "notes",
                    models.TextField(
                        blank=True,
                        default="",
                        help_text=(
                            "Operator notes (e.g. cost tier, deployment " "region)."
                        ),
                    ),
                ),
                (
                    "creator",
                    models.ForeignKey(
                        db_index=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "user_lock",
                    models.ForeignKey(
                        blank=True,
                        db_index=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="locked_registeredllm_objects",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "previous_version",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="next_version",
                        to="llm_configs.registeredllm",
                        help_text=(
                            "Set to the prior row when this row is the result "
                            "of an edit. Walk the chain backwards via a "
                            "recursive CTE on previous_version_id to recover "
                            "full version history. NULL on the original row "
                            "of a lineage."
                        ),
                    ),
                ),
            ],
            options={
                "verbose_name": "Registered LLM",
                "verbose_name_plural": "Registered LLMs",
                "permissions": (
                    ("permission_registeredllm", "permission registered llm"),
                    ("create_registeredllm", "create registered llm"),
                    ("read_registeredllm", "read registered llm"),
                    ("update_registeredllm", "update registered llm"),
                    ("remove_registeredllm", "delete registered llm"),
                    ("comment_registeredllm", "comment registered llm"),
                    ("publish_registeredllm", "publish registered llm"),
                ),
                "indexes": [
                    models.Index(
                        fields=["provider_class_path", "model_id"],
                        name="reg_llm_provider_model_idx",
                    ),
                    models.Index(
                        fields=["is_archived", "is_enabled"],
                        name="reg_llm_lifecycle_idx",
                    ),
                ],
            },
        ),
        # ----------------------------------------------------------------
        # LLMSettings
        # ----------------------------------------------------------------
        migrations.CreateModel(
            name="LLMSettings",
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
                    "encrypted_secrets",
                    models.BinaryField(
                        blank=True,
                        null=True,
                        help_text=(
                            "Encrypted storage for sensitive configuration "
                            "(API keys, credentials)"
                        ),
                    ),
                ),
                (
                    "provider_settings",
                    opencontractserver.shared.fields.NullableJSONField(
                        blank=True,
                        default=dict,
                        help_text=(
                            "Mapping of provider class paths to non-secret "
                            "configuration."
                        ),
                    ),
                ),
                ("modified", models.DateTimeField(auto_now=True, db_index=True)),
                (
                    "default_extract_llm",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="llm_configs.registeredllm",
                        help_text=(
                            "Default LLM for extract tasks (used when a Column "
                            "has no preferred_llm). NULL falls back to "
                            "constants.extraction.DEFAULT_EXTRACT_MODEL."
                        ),
                    ),
                ),
                (
                    "modified_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="llm_settings_modifications",
                        to=settings.AUTH_USER_MODEL,
                        help_text="User who last modified these settings.",
                    ),
                ),
            ],
            options={
                "verbose_name": "LLM Settings",
                "verbose_name_plural": "LLM Settings",
            },
        ),
        migrations.AddConstraint(
            model_name="llmsettings",
            constraint=models.CheckConstraint(
                condition=models.Q(("pk", 1)),
                name="llm_settings_singleton_pk",
            ),
        ),
        # Seed the singleton with all-default values so callers can rely on
        # LLMSettings.get_instance() returning a row immediately after
        # deploy. RegisteredLLM seeding deferred to Phase 2.
        migrations.RunPython(
            create_llm_settings_singleton,
            reverse_create_singleton,
        ),
    ]
