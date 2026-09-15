"""Limits for readiness observations and embedding repair."""

from datetime import timedelta

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100
MAX_ERROR_LENGTH = 1000
MAX_TEXT_BYTES = 16 * 1024 * 1024
REPAIR_BATCH_SIZE = 100
REPAIR_SOFT_TIME_LIMIT = 9 * 60
REPAIR_TIME_LIMIT = 10 * 60
REPAIR_TIMEOUT = timedelta(minutes=15)
