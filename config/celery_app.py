import os

from celery import Celery
from celery.signals import worker_process_init

# set the default Django settings module for the 'celery' program.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")

app = Celery("opencontractserver")

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
# - namespace='CELERY' means all celery-related configuration keys
#   should have a `CELERY_` prefix.
app.config_from_object("django.conf:settings", namespace="CELERY")

# Load task modules from all registered Django app configs.
app.autodiscover_tasks()


@worker_process_init.connect
def close_db_connections_on_worker_init(**kwargs):
    """Close database connections inherited from the parent (prefork) process.

    This handler is designed for the prefork pool (the default pool type used in
    production — see CELERY_MAX_TASKS_PER_CHILD and CELERY_WORKER_MAX_MEMORY_PER_CHILD
    in base settings). When Celery forks a worker child, it inherits the parent's DB
    connections. These inherited connections are invalid in the child and must be closed
    so Django opens fresh ones. Without this, stale inherited connections can cause
    errors and contribute to connection churn (TIME_WAIT accumulation).

    For other pool types (solo, threads, gevent/eventlet) this signal still fires
    but is harmless — closing connections that don't exist is a no-op.
    """
    from django.db import connections

    connections.close_all()
