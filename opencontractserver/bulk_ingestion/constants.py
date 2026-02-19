"""
Constants for bulk ingestion operations.

All limits can be overridden via Django settings with the same name.
Example: settings.BULK_INGESTION_IMPORT_BATCH_SIZE = 500
"""

from django.conf import settings

# ============================================================================
# Batch sizes
# ============================================================================

# Documents per database import batch (bulk_create)
BULK_INGESTION_IMPORT_BATCH_SIZE = getattr(
    settings, "BULK_INGESTION_IMPORT_BATCH_SIZE", 200
)

# Documents per download batch
BULK_INGESTION_DOWNLOAD_BATCH_SIZE = getattr(
    settings, "BULK_INGESTION_DOWNLOAD_BATCH_SIZE", 500
)

# Documents per parsed-data import batch (save_parsed_data calls)
BULK_INGESTION_PARSE_BATCH_SIZE = getattr(
    settings, "BULK_INGESTION_PARSE_BATCH_SIZE", 50
)

# Permissions per bulk_create call
BULK_INGESTION_PERMISSION_BATCH_SIZE = getattr(
    settings, "BULK_INGESTION_PERMISSION_BATCH_SIZE", 500
)

# ============================================================================
# Backpressure / queue depth limits
# ============================================================================

# Maximum parsing queue depth before the dispatcher starts throttling
BULK_INGESTION_MAX_PARSE_QUEUE_DEPTH = getattr(
    settings, "BULK_INGESTION_MAX_PARSE_QUEUE_DEPTH", 1000
)

# Maximum embedding queue depth before throttling
BULK_INGESTION_MAX_EMBED_QUEUE_DEPTH = getattr(
    settings, "BULK_INGESTION_MAX_EMBED_QUEUE_DEPTH", 2000
)

# Delay (seconds) when queue is full - dispatcher re-checks after this
BULK_INGESTION_BACKPRESSURE_DELAY = getattr(
    settings, "BULK_INGESTION_BACKPRESSURE_DELAY", 15
)

# ============================================================================
# Download settings
# ============================================================================

# Maximum concurrent HTTP downloads per batch task
BULK_INGESTION_DOWNLOAD_CONCURRENCY = getattr(
    settings, "BULK_INGESTION_DOWNLOAD_CONCURRENCY", 10
)

# Request timeout for individual document download (seconds)
BULK_INGESTION_DOWNLOAD_TIMEOUT = getattr(
    settings, "BULK_INGESTION_DOWNLOAD_TIMEOUT", 120
)

# Maximum retries per individual download
BULK_INGESTION_DOWNLOAD_MAX_RETRIES = getattr(
    settings, "BULK_INGESTION_DOWNLOAD_MAX_RETRIES", 3
)

# Rate limit: minimum seconds between requests to same host
BULK_INGESTION_DOWNLOAD_RATE_LIMIT = getattr(
    settings, "BULK_INGESTION_DOWNLOAD_RATE_LIMIT", 0.1
)

# ============================================================================
# Celery queue names
# ============================================================================

QUEUE_BULK_ORCHESTRATE = "bulk_orchestrate"
QUEUE_BULK_DOWNLOAD = "bulk_download"
QUEUE_BULK_IMPORT = "bulk_import"
QUEUE_BULK_DISPATCH = "bulk_dispatch"
QUEUE_PARSING = "parsing"
QUEUE_EMBEDDING = "embedding"

# ============================================================================
# Progress checkpoint interval
# ============================================================================

# How often to write checkpoint data during batch operations
BULK_INGESTION_CHECKPOINT_INTERVAL = getattr(
    settings, "BULK_INGESTION_CHECKPOINT_INTERVAL", 100
)

# ============================================================================
# Staging directory
# ============================================================================

# Default staging prefix for temporary files during ingestion
BULK_INGESTION_STAGING_PREFIX = getattr(
    settings, "BULK_INGESTION_STAGING_PREFIX", "bulk_ingestion_staging"
)
