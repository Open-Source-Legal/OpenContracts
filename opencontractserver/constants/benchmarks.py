"""
Constants for the benchmark harness.

WARNING: This module is imported during app startup.
It MUST remain free of Django imports (models, apps, etc.) to avoid
AppRegistryNotReady errors during settings loading.
"""

from opencontractserver.constants.extraction import DEFAULT_EXTRACT_MODEL

# Default LLM identifier passed to the extraction agent when no explicit
# model is supplied.  Re-exports the extraction default so benchmarks and
# production tasks always use the same fallback.
BENCHMARK_DEFAULT_MODEL = DEFAULT_EXTRACT_MODEL

# Default top-k for the retrieval probe.
BENCHMARK_DEFAULT_TOP_K = 10

# Maximum character length for auto-generated benchmark Column names.
BENCHMARK_COLUMN_NAME_MAX_LEN = 128
