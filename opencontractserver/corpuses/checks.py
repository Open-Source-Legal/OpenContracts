"""
Django system checks for embedder configuration (Issue #437).

These checks run at startup to detect potentially dangerous configuration
changes that could cause search inconsistencies.
"""

import logging

from django.core.checks import Tags, Warning, register

logger = logging.getLogger(__name__)


@register(Tags.models)
def check_default_embedder_consistency(app_configs, **kwargs):
    """
    Warn if default embedder has changed since existing corpuses were created.

    When the default embedder changes, existing annotations retain embeddings
    from the old embedder while new annotations get the new one. Global search
    (which filters by embedder_path) will silently miss old content.

    This check queries the database for corpuses whose created_with_embedder
    differs from the current default embedder (from PipelineSettings) and
    issues a warning if found.
    """
    errors: list[Warning] = []

    try:
        # Only run this check when the database is available (not during
        # initial migration or table creation).
        from django.db import connection

        tables = connection.introspection.table_names()
        if "corpuses_corpus" not in tables:
            return errors

        # Check if the created_with_embedder column exists yet
        # (migration may not have run)
        columns = [
            col.name
            for col in connection.introspection.get_table_description(
                connection.cursor(), "corpuses_corpus"
            )
        ]
        if "created_with_embedder" not in columns:
            return errors

        # Also need PipelineSettings table to exist
        if "documents_pipelinesettings" not in tables:
            return errors

        from opencontractserver.corpuses.models import Corpus
        from opencontractserver.pipeline.utils import get_default_embedder_path

        current_default = get_default_embedder_path()
        if not current_default:
            errors.append(
                Warning(
                    "Default embedder is not configured in PipelineSettings.",
                    hint=(
                        "Set a default embedder via the Pipeline Settings admin UI, "
                        "the updatePipelineSettings GraphQL mutation, or run: "
                        "python manage.py migrate_pipeline_settings --sync-preferences"
                    ),
                    id="opencontracts.W001",
                )
            )
            return errors

        # Count corpuses created with a different embedder
        mismatched_count = (
            Corpus.objects.exclude(created_with_embedder__isnull=True)
            .exclude(created_with_embedder="")
            .exclude(created_with_embedder=current_default)
            .count()
        )

        if mismatched_count > 0:
            errors.append(
                Warning(
                    f"Default embedder has changed. {mismatched_count} corpus(es) were "
                    f"created with a different embedder than the current default "
                    f"({current_default}). Global search may return incomplete results "
                    f"for annotations in those corpuses.",
                    hint=(
                        "Corpus-scoped search uses each corpus's frozen "
                        "preferred_embedder and is unaffected. To fix global search, "
                        "consider re-embedding affected corpuses using the "
                        "reEmbedCorpus mutation, or update the default embedder in "
                        "Pipeline Settings."
                    ),
                    id="opencontracts.W002",
                )
            )

    except Exception as e:
        # Don't crash startup for a check failure, but make it visible
        logger.warning(f"Embedder consistency check skipped: {e}")

    return errors
