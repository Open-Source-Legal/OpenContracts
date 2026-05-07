"""
Constants for zip file import security limits.

These limits protect against:
- Zip bombs (decompression bombs)
- Path traversal attacks
- Resource exhaustion
- Denial of service

All limits can be overridden via Django settings with the same name and via
the matching environment variable consumed in `config/settings/base.py`.
Example: settings.ZIP_MAX_FILE_COUNT = 2000  (or `ZIP_MAX_FILE_COUNT=2000`
in the environment).
"""

from django.conf import settings

# Maximum number of files allowed in a single zip
ZIP_MAX_FILE_COUNT = getattr(settings, "ZIP_MAX_FILE_COUNT", 1000)

# Maximum total uncompressed size in bytes (500MB default)
ZIP_MAX_TOTAL_SIZE_BYTES = getattr(
    settings, "ZIP_MAX_TOTAL_SIZE_BYTES", 500 * 1024 * 1024
)

# Maximum size of a single file in bytes (100MB default)
# Files exceeding this limit are skipped with an error message
ZIP_MAX_SINGLE_FILE_SIZE_BYTES = getattr(
    settings, "ZIP_MAX_SINGLE_FILE_SIZE_BYTES", 100 * 1024 * 1024
)

# Maximum compression ratio (uncompressed/compressed) before flagging as suspicious
# Files exceeding this ratio trigger additional validation
ZIP_MAX_COMPRESSION_RATIO = getattr(settings, "ZIP_MAX_COMPRESSION_RATIO", 100)

# Maximum folder depth (number of nested folders)
ZIP_MAX_FOLDER_DEPTH = getattr(settings, "ZIP_MAX_FOLDER_DEPTH", 20)

# Maximum number of folders that can be created from a single zip
ZIP_MAX_FOLDER_COUNT = getattr(settings, "ZIP_MAX_FOLDER_COUNT", 500)

# Maximum length of a single path component (folder or file name) in characters
ZIP_MAX_PATH_COMPONENT_LENGTH = getattr(settings, "ZIP_MAX_PATH_COMPONENT_LENGTH", 255)

# Maximum total path length in characters
ZIP_MAX_PATH_LENGTH = getattr(settings, "ZIP_MAX_PATH_LENGTH", 1024)

# Maximum size of a single annotation sidecar JSON in bytes (50MB default).
# Sidecars are fully loaded into memory for JSON parsing; this limit
# prevents a single oversized sidecar from causing excessive memory usage.
# Override via Django settings (ZIP_MAX_SIDECAR_SIZE_BYTES) or the
# matching environment variable consumed in config/settings/base.py.
ZIP_MAX_SIDECAR_SIZE_BYTES = getattr(
    settings, "ZIP_MAX_SIDECAR_SIZE_BYTES", 50 * 1024 * 1024
)

# Batch size for document processing (commit after N documents)
ZIP_DOCUMENT_BATCH_SIZE = getattr(settings, "ZIP_DOCUMENT_BATCH_SIZE", 50)

# IDOR protection: bulk-upload job-id ↔ owner mapping in cache.
# At enqueue time we cache the (job_id → user_id) pair; the status
# resolver refuses to return progress for jobs the requester didn't
# enqueue. The 24-hour default is intentionally generous: a large
# zip can take many hours to process and the user must remain able
# to poll progress for the full lifetime of the job. Shortening this
# would silently turn legitimate "still processing" polls into
# opaque "not found" responses once the cache entry expired.
BULK_UPLOAD_OWNER_CACHE_PREFIX = "bulk_upload_owner:"
BULK_UPLOAD_OWNER_CACHE_TTL_SECONDS = getattr(
    settings, "BULK_UPLOAD_OWNER_CACHE_TTL_SECONDS", 24 * 60 * 60
)
