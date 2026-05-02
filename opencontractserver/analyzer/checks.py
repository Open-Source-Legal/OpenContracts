from typing import Any

from django.core.checks import Warning, register


@register()
def check_unsynced_analyzers(app_configs: Any, **kwargs: Any) -> list[Warning]:
    """
    Check if there are doc_analyzer_task decorated functions
    that haven't been synced to the database.
    """
    warnings: list[Warning] = []

    try:
        from opencontractserver.analyzer.models import Analyzer
        from opencontractserver.utils.celery_tasks import (
            celery_app,
            get_doc_analyzer_task_by_name,
        )

        unsynced = []

        for task_name in celery_app.tasks.keys():
            analyzer_task = get_doc_analyzer_task_by_name(task_name)
            if analyzer_task is None:
                continue

            analyzer_id = task_name
            exists = (
                Analyzer.objects.filter(id=analyzer_id).exists()
                or Analyzer.objects.filter(task_name=task_name).exists()
            )

            if not exists:
                unsynced.append(task_name)

        if unsynced:
            warnings.append(
                Warning(
                    f"Found {len(unsynced)} unsynced doc_analyzer_task(s): "
                    f"{', '.join(unsynced[:3])}{'...' if len(unsynced) > 3 else ''}",
                    hint="Run 'python manage.py sync_doc_analyzers' or use the admin interface to sync.",
                    id="analyzer.W001",
                )
            )
    except Exception:
        # Don't fail the check if there are import issues
        pass

    return warnings
