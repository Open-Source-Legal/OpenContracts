"""
Constants for zip file import security limits.

These limits protect against:
- Zip bombs (decompression bombs)
- Path traversal attacks
- Resource exhaustion
- Denial of service

All limits are overridable via a Django setting of the same name (and the
matching environment variable consumed in ``config/settings/base.py``).
Example: ``settings.ZIP_MAX_FILE_COUNT = 2000`` (or ``ZIP_MAX_FILE_COUNT=2000``
in the environment).

WHY THE ``get_*`` ACCESSORS — DO NOT re-introduce module-level
``getattr(settings, …)`` here:
``config/settings/base.py`` imports from ``opencontractserver.constants.*`` at
the very top of the file. Importing any ``constants`` submodule first executes
``constants/__init__.py``. If that import chain reaches *this* module while the
settings module is still mid-load, every ``getattr(settings, "ZIP_MAX_…", …)``
evaluated at import time would read a half-built settings object, silently fall
back to the default, and freeze there for the life of the process — so any
ConfigMap/env override would become permanently inert (the feature would be
dead in production no matter what the operator configured). Reading inside the
accessors defers the lookup until call time, after settings is fully
initialised, so ``@override_settings`` and env/deployment overrides are honoured
at runtime. This mirrors the sibling ``zip_export.py`` module, which is kept out
of the ``constants`` barrel for the same reason.
"""

from django.conf import settings

# --- Default limits ---------------------------------------------------------
# These ``DEFAULT_*`` values are the *only* hard-coded numbers. They are plain
# constants (no settings read) and are used as the fallback by the matching
# ``get_*`` accessor when the setting is unset.

# Maximum number of files allowed in a single zip.
DEFAULT_ZIP_MAX_FILE_COUNT = 1000

# Maximum total uncompressed size in bytes (500MB default).
DEFAULT_ZIP_MAX_TOTAL_SIZE_BYTES = 500 * 1024 * 1024

# Maximum size of a single file in bytes (100MB default).
# Files exceeding this limit are skipped with an error message.
DEFAULT_ZIP_MAX_SINGLE_FILE_SIZE_BYTES = 100 * 1024 * 1024

# Maximum compression ratio (uncompressed/compressed) before flagging as
# suspicious. Files exceeding this ratio trigger additional validation.
DEFAULT_ZIP_MAX_COMPRESSION_RATIO = 100

# Maximum folder depth (number of nested folders).
DEFAULT_ZIP_MAX_FOLDER_DEPTH = 20

# Maximum number of folders that can be created from a single zip.
DEFAULT_ZIP_MAX_FOLDER_COUNT = 500

# Maximum length of a single path component (folder or file name) in characters.
DEFAULT_ZIP_MAX_PATH_COMPONENT_LENGTH = 255

# Maximum total path length in characters.
DEFAULT_ZIP_MAX_PATH_LENGTH = 1024

# Maximum size of a single annotation sidecar JSON in bytes (50MB default).
# Sidecars are fully loaded into memory for JSON parsing; this limit
# prevents a single oversized sidecar from causing excessive memory usage.
DEFAULT_ZIP_MAX_SIDECAR_SIZE_BYTES = 50 * 1024 * 1024

# Batch size for document processing (log progress after N documents).
DEFAULT_ZIP_DOCUMENT_BATCH_SIZE = 50

# IDOR protection: bulk-upload job-id ↔ owner mapping in cache.
# At enqueue time we cache the (job_id → user_id) pair; the status
# resolver refuses to return progress for jobs the requester didn't
# enqueue. The 24-hour default is intentionally generous: a large
# zip can take many hours to process and the user must remain able
# to poll progress for the full lifetime of the job. Shortening this
# would silently turn legitimate "still processing" polls into
# opaque "not found" responses once the cache entry expired.
DEFAULT_BULK_UPLOAD_OWNER_CACHE_TTL_SECONDS = 24 * 60 * 60

# Cache key prefix for the IDOR owner mapping. Not settings-derived, so it is a
# plain constant — safe to bind at import.
BULK_UPLOAD_OWNER_CACHE_PREFIX = "bulk_upload_owner:"


# --- Lazy accessors ---------------------------------------------------------
# Call these at use time; never copy their result into a module-level constant.


def get_zip_max_file_count() -> int:
    """Maximum number of files allowed in a single import zip."""
    return getattr(settings, "ZIP_MAX_FILE_COUNT", DEFAULT_ZIP_MAX_FILE_COUNT)


def get_zip_max_total_size_bytes() -> int:
    """Maximum total uncompressed size (bytes) of a single import zip."""
    return getattr(
        settings, "ZIP_MAX_TOTAL_SIZE_BYTES", DEFAULT_ZIP_MAX_TOTAL_SIZE_BYTES
    )


def get_zip_max_single_file_size_bytes() -> int:
    """Maximum size (bytes) of any single file inside an import zip."""
    return getattr(
        settings,
        "ZIP_MAX_SINGLE_FILE_SIZE_BYTES",
        DEFAULT_ZIP_MAX_SINGLE_FILE_SIZE_BYTES,
    )


def get_zip_max_compression_ratio() -> int:
    """Compression ratio above which a zip entry is flagged as suspicious."""
    return getattr(
        settings, "ZIP_MAX_COMPRESSION_RATIO", DEFAULT_ZIP_MAX_COMPRESSION_RATIO
    )


def get_zip_max_folder_depth() -> int:
    """Maximum folder depth (nested folders) inside an import zip."""
    return getattr(settings, "ZIP_MAX_FOLDER_DEPTH", DEFAULT_ZIP_MAX_FOLDER_DEPTH)


def get_zip_max_folder_count() -> int:
    """Maximum number of folders created from a single import zip."""
    return getattr(settings, "ZIP_MAX_FOLDER_COUNT", DEFAULT_ZIP_MAX_FOLDER_COUNT)


def get_zip_max_path_component_length() -> int:
    """Maximum length (chars) of a single path component inside an import zip."""
    return getattr(
        settings,
        "ZIP_MAX_PATH_COMPONENT_LENGTH",
        DEFAULT_ZIP_MAX_PATH_COMPONENT_LENGTH,
    )


def get_zip_max_path_length() -> int:
    """Maximum total path length (chars) for any entry in an import zip."""
    return getattr(settings, "ZIP_MAX_PATH_LENGTH", DEFAULT_ZIP_MAX_PATH_LENGTH)


def get_zip_max_sidecar_size_bytes() -> int:
    """Maximum size (bytes) of a single annotation sidecar JSON."""
    return getattr(
        settings, "ZIP_MAX_SIDECAR_SIZE_BYTES", DEFAULT_ZIP_MAX_SIDECAR_SIZE_BYTES
    )


def get_zip_document_batch_size() -> int:
    """Number of documents to process per batch when draining a zip import."""
    return getattr(settings, "ZIP_DOCUMENT_BATCH_SIZE", DEFAULT_ZIP_DOCUMENT_BATCH_SIZE)


def get_bulk_upload_owner_cache_ttl_seconds() -> int:
    """TTL (seconds) for the bulk-upload job-id ↔ owner IDOR cache entry."""
    return getattr(
        settings,
        "BULK_UPLOAD_OWNER_CACHE_TTL_SECONDS",
        DEFAULT_BULK_UPLOAD_OWNER_CACHE_TTL_SECONDS,
    )
