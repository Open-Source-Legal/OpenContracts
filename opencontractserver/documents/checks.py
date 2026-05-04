"""
Django system checks for the documents app.

These checks run during startup (runserver, migrate, check) to warn about
common misconfigurations.
"""

import logging

from django.core.checks import Error, Warning, register

logger = logging.getLogger(__name__)


@register()
def check_pipeline_settings_populated(app_configs, **kwargs):
    """
    Warn if PipelineSettings exists but has empty preferences while
    Django settings define non-empty values.

    This catches the case where a user upgraded but forgot to run:
        python manage.py migrate_pipeline_settings --sync-preferences
    """
    errors: list[Error | Warning] = []

    try:
        from django.conf import settings as django_settings

        from opencontractserver.documents.models import PipelineSettings

        # Only check if the table exists and has a row
        if not PipelineSettings.objects.exists():
            return errors

        instance = PipelineSettings.get_instance(use_cache=False)

        # Check if DB preferences are all empty/default
        db_has_parsers = bool(instance.preferred_parsers)
        db_has_embedders = bool(instance.preferred_embedders)
        db_has_default_embedder = bool(instance.default_embedder)

        # Check if Django settings have values
        django_has_parsers = bool(getattr(django_settings, "PREFERRED_PARSERS", None))
        django_has_embedders = bool(
            getattr(django_settings, "PREFERRED_EMBEDDERS", None)
        )
        django_has_default_embedder = bool(
            getattr(django_settings, "DEFAULT_EMBEDDER", None)
        )

        django_configured = (
            django_has_parsers or django_has_embedders or django_has_default_embedder
        )
        db_empty = (
            not db_has_parsers and not db_has_embedders and not db_has_default_embedder
        )

        if django_configured and db_empty:
            errors.append(
                Warning(
                    "PipelineSettings has empty preferences but Django settings "
                    "define pipeline configuration.",
                    hint=(
                        "Run 'python manage.py migrate_pipeline_settings "
                        "--sync-preferences' to populate the database from "
                        "Django settings."
                    ),
                    id="documents.W001",
                )
            )

    except Exception:
        # Don't fail startup if check can't run (e.g., table doesn't exist yet)
        pass

    return errors


# Class paths of removed ModernBERT embedders
_REMOVED_MODERNBERT_PATHS = {
    "opencontractserver.pipeline.embedders.modern_bert_embedder.ModernBERTEmbedder",
    "opencontractserver.pipeline.embedders.minn_modern_bert_embedder.MinnModernBERTEmbedder",
}


@register()
def check_modernbert_references(app_configs, **kwargs):
    """
    Warn if PipelineSettings references removed ModernBERT embedder class paths.

    ModernBERT embedders were removed in this release. Users with existing
    references need to update their configuration to use an alternative.
    """
    errors: list[Error | Warning] = []

    try:
        from opencontractserver.documents.models import PipelineSettings

        if not PipelineSettings.objects.exists():
            return errors

        instance = PipelineSettings.get_instance(use_cache=False)

        found_refs = []

        # Check preferred_embedders
        for mime_type, path in (instance.preferred_embedders or {}).items():
            if path in _REMOVED_MODERNBERT_PATHS:
                found_refs.append(f"preferred_embedders[{mime_type}]")

        # Check default_embedder
        if instance.default_embedder in _REMOVED_MODERNBERT_PATHS:
            found_refs.append("default_embedder")

        if found_refs:
            errors.append(
                Warning(
                    "PipelineSettings references removed ModernBERT embedders: "
                    + ", ".join(found_refs),
                    hint=(
                        "ModernBERT embedders have been removed. Update your "
                        "pipeline settings to use an alternative embedder "
                        "(e.g., MicroserviceEmbedder, OpenAIEmbedder, "
                        "VoyageAIEmbedder). Use the Admin UI or run: "
                        "python manage.py migrate_pipeline_settings --list-components"
                    ),
                    id="documents.W002",
                )
            )

    except Exception:
        pass

    return errors


@register()
def check_configured_components_secrets(app_configs, **kwargs):
    """
    Warn if actively configured pipeline components are missing required secrets.

    Checks each component referenced in preferred_parsers, preferred_embedders,
    preferred_thumbnailers, and default_embedder against its settings schema.
    Reports any required secret fields that have no value stored.
    """
    errors: list[Error | Warning] = []

    try:
        from opencontractserver.documents.models import PipelineSettings
        from opencontractserver.pipeline.base.settings_schema import (
            get_secret_settings,
            get_settings_schema,
        )
        from opencontractserver.pipeline.registry import get_registry

        if not PipelineSettings.objects.exists():
            return errors

        instance = PipelineSettings.get_instance(use_cache=False)
        registry = get_registry()

        # Collect all actively configured component paths
        active_paths: set[str] = set()
        for mapping in (
            instance.preferred_parsers,
            instance.preferred_embedders,
            instance.preferred_thumbnailers,
        ):
            if mapping:
                active_paths.update(mapping.values())
        if instance.default_embedder:
            active_paths.add(instance.default_embedder)

        # Get stored secrets
        stored_secrets = instance.get_secrets()

        missing_components = []
        for component_path in sorted(active_paths):
            comp_def = registry.get_by_class_name(component_path)
            if not comp_def or not comp_def.component_class:
                continue

            # Get required secret field names
            schema = get_settings_schema(comp_def.component_class)
            secret_names = get_secret_settings(comp_def.component_class)
            required_secrets = [
                name
                for name in secret_names
                if schema.get(name, {}).get("required", False)
            ]

            if not required_secrets:
                continue

            # Check which required secrets are missing
            comp_secrets = stored_secrets.get(component_path, {})
            missing = [s for s in required_secrets if not comp_secrets.get(s)]
            if missing:
                missing_components.append(
                    f"{component_path} (missing: {', '.join(missing)})"
                )

        if missing_components:
            errors.append(
                Warning(
                    "Configured pipeline components are missing required secrets: "
                    + "; ".join(missing_components),
                    hint=(
                        "Configure secrets via the Pipeline Settings admin UI "
                        "or the updateComponentSecrets GraphQL mutation. "
                        "Components will fall back to environment variables or "
                        "defaults if available."
                    ),
                    id="documents.W003",
                )
            )

    except Exception:
        # Don't fail startup if check can't run
        pass

    return errors


@register()
def check_embedding_batch_size_configuration(app_configs, **kwargs):
    """
    Verify that EMBEDDING_API_BATCH_SIZE does not exceed
    MICROSERVICE_EMBEDDER_MAX_BATCH_SIZE.

    A misconfiguration here would cause silently truncated batches when
    embedding tasks run. Surfacing it as a Django system check provides a
    clear error message during startup (``manage.py check``, ``runserver``,
    ``migrate``) instead of an opaque import-time traceback.

    Note: ``app_configs`` is intentionally unused — this check validates
    global constants, not per-app configuration. Consistent with the other
    checks in this file.
    """
    from opencontractserver.constants.document_processing import (
        EMBEDDING_API_BATCH_SIZE,
        MICROSERVICE_EMBEDDER_MAX_BATCH_SIZE,
    )

    errors: list[Error | Warning] = []
    if EMBEDDING_API_BATCH_SIZE > MICROSERVICE_EMBEDDER_MAX_BATCH_SIZE:
        errors.append(
            Error(
                f"EMBEDDING_API_BATCH_SIZE ({EMBEDDING_API_BATCH_SIZE}) exceeds "
                f"MICROSERVICE_EMBEDDER_MAX_BATCH_SIZE ({MICROSERVICE_EMBEDDER_MAX_BATCH_SIZE}).",
                hint=(
                    "Lower EMBEDDING_API_BATCH_SIZE or raise "
                    "MICROSERVICE_EMBEDDER_MAX_BATCH_SIZE in "
                    "opencontractserver/constants/document_processing.py."
                ),
                id="documents.E001",
            )
        )
    return errors
