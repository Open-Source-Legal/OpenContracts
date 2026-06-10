from typing import Callable, Optional

from config.celery_app import app as celery_app


def get_task_by_name(task_name) -> Optional[Callable]:
    """
    Try to get celery task function Callable by name
    """
    try:
        return celery_app.tasks.get(task_name)
    except Exception:
        return None


def get_doc_analyzer_task_by_name(task_name) -> Optional[Callable]:
    """
    Get celery task function Callable by name, only for tasks decorated with doc_analyzer_task
    """
    try:
        task = celery_app.tasks.get(task_name)
        if task and getattr(task, "is_doc_analyzer_task", False):
            return task
        return None
    except Exception:
        return None


def get_corpus_analyzer_task_by_name(task_name) -> Optional[Callable]:
    """
    Get celery task function Callable by name, only for tasks decorated with corpus_analyzer_task
    """
    try:
        task = celery_app.tasks.get(task_name)
        if task and getattr(task, "is_corpus_analyzer_task", False):
            return task
        return None
    except Exception:
        return None


def get_analyzer_task_by_name(task_name) -> Optional[Callable]:
    """
    Get celery task function Callable by name for either analyzer flavour
    (doc-scoped or corpus-scoped). Used by registration sync and system
    checks, which treat both identically; dispatch distinguishes them.
    """
    return get_doc_analyzer_task_by_name(task_name) or get_corpus_analyzer_task_by_name(
        task_name
    )
