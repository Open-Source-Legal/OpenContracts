"""``post_migrate`` convergence for the ``PipelineSettings`` singleton.

Mirrors ``opencontractserver/enrichment/_namespace_seed.py``, which solves the
same class of problem for the shipped ``AuthorityNamespace`` rows.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def _singleton_defaults() -> dict:
    """Field defaults for the singleton, sourced from Django settings.

    Kept in one place so this receiver and ``PipelineSettings.get_instance``
    cannot drift into seeding two different "default" rows.
    """
    from django.conf import settings as django_settings

    return {
        "preferred_parsers": getattr(django_settings, "PREFERRED_PARSERS", {}),
        "preferred_embedders": getattr(django_settings, "PREFERRED_EMBEDDERS", {}),
        "preferred_thumbnailers": {},  # No default in Django settings
        "preferred_enrichers": getattr(django_settings, "PREFERRED_ENRICHERS", {}),
        "parser_kwargs": getattr(django_settings, "PARSER_KWARGS", {}),
        "component_settings": getattr(django_settings, "PIPELINE_SETTINGS", {}),
        "default_embedder": getattr(django_settings, "DEFAULT_EMBEDDER", ""),
        "default_reranker": getattr(django_settings, "DEFAULT_RERANKER", ""),
        "default_file_converter": getattr(django_settings, "DEFAULT_FILE_CONVERTER", "")
        or "",
        # ``DEFAULT_LLM`` may be explicitly None (tests exercising the legacy
        # fallback); coerce so the NOT NULL column never receives null.
        "default_llm": getattr(django_settings, "DEFAULT_LLM", "") or "",
    }


def ensure_pipeline_settings_seeded(
    sender=None, *, apps=None, using=None, **kwargs
) -> None:
    """``post_migrate`` receiver that restores the ``PipelineSettings`` singleton.

    Migration ``0031_add_pipeline_settings`` seeds the singleton with a one-shot
    ``RunPython``, so the row it commits lives *outside* any test transaction.
    Django's ``flush`` — run on every ``TransactionTestCase`` teardown —
    truncates ``documents_pipelinesettings`` along with every other table, and
    with ``serialized_rollback`` disabled (the default) nothing restores it.
    Under ``pytest -n 4 --dist loadscope`` any ``TransactionTestCase`` that runs
    before an embedder-touching test on the same worker therefore leaves the
    install with NO singleton for the rest of that worker's session.

    That is worse than a missing row, because ``get_instance()`` re-creates it
    lazily: an ``async`` test under Django's ``TestCase`` reaches
    ``get_embedder`` -> ``get_default_embedder_path`` -> ``get_instance`` on the
    asgiref executor thread, which holds its OWN database connection. The
    executor's ``get_or_create(pk=1)`` cannot see the main thread's uncommitted
    row, so it issues a competing ``INSERT`` and blocks on the test
    transaction's lock — while the main thread is parked in
    ``AsyncToSync.__call__`` waiting for that very executor. Neither side can
    advance; the test hangs until ``pytest-timeout`` kills it at 600s, and
    because the hang leaves ``unittest.mock.patch`` decorators un-exited, it
    also fails every later test in the class that shares the patched target.

    Re-running the idempotent seed on every ``post_migrate`` converges the table
    again after each flush (and repairs reused/poisoned CI volumes at DB setup).
    It is a no-op on freshly-migrated and production databases.

    ``migrate`` emits ``post_migrate`` WITH an ``apps`` kwarg (the historical
    project state); ``flush`` emits it WITHOUT one
    (``django/core/management/commands/flush.py`` vs ``migrate.py``). The
    flush-path emission is precisely the one that has to re-seed, so — exactly
    like Django's own ``create_contenttypes`` / ``create_permissions``
    receivers — fall back to the global app registry when ``apps`` is absent
    rather than bailing.

    Connected with ``sender=DocumentsConfig`` so it fires exactly once per
    emission, after the ``documents`` app's tables exist.
    """
    if apps is None:
        from django.apps import apps as global_apps  # flush path: no apps kwarg

        apps = global_apps

    try:
        PipelineSettings = apps.get_model("documents", "PipelineSettings")
    except LookupError:  # pragma: no cover - app always installed
        return

    manager = PipelineSettings.objects
    if using is not None:
        manager = manager.using(using)

    # ``id=1`` is the singleton contract (see ``PipelineSettings.save``); passing
    # it explicitly keeps ``save()`` off its "already exists" guard.
    _instance, created = manager.get_or_create(id=1, defaults=_singleton_defaults())

    if created:
        logger.info(
            "Re-seeded the PipelineSettings singleton (row was absent — expected "
            "after a TransactionTestCase flush, unexpected in production)."
        )
        # A cached instance from before the truncation would mask the fresh row.
        try:
            from opencontractserver.documents.models import (
                PipelineSettings as RealPipelineSettings,
            )

            RealPipelineSettings.clear_cache()
        except Exception:  # pragma: no cover - cache backend optional
            logger.debug("Could not clear PipelineSettings cache after re-seed.")
