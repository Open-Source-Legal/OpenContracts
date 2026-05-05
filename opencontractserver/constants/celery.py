"""
Celery-related constants.
"""

# Maximum expected duration for any document-processing task (seconds).
# OpenContracts uses Redis as the Celery broker. Redis tracks unacknowledged
# messages with a *visibility timeout*: once a worker pulls a message, the
# broker considers it eligible for redelivery to a different worker after the
# timeout elapses, regardless of whether the original worker is still alive.
# With ``CELERY_TASK_ACKS_LATE = True``, any task that runs longer than this
# timeout will be redelivered while still executing — a guaranteed double
# execution even without a worker crash. The Celery default is 1 hour (3600s),
# which is shorter than worst-case ingest/parse/embed runs, so we raise it to
# 12 hours (longer than any expected document-processing job).
CELERY_REDIS_VISIBILITY_TIMEOUT_SECONDS = 12 * 60 * 60
