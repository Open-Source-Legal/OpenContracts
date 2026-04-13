"""
Constants for the benchmark harness.

WARNING: This module is imported during app startup.
It MUST remain free of Django imports (models, apps, etc.) to avoid
AppRegistryNotReady errors during settings loading.
"""

# Default LLM identifier passed to the extraction agent when no explicit
# model is supplied.  Any string pydantic-ai accepts is valid.
BENCHMARK_DEFAULT_MODEL = "openai:gpt-4o-mini"

# Default top-k for the retrieval probe.
BENCHMARK_DEFAULT_TOP_K = 10

# Maximum character length for auto-generated benchmark Column names.
BENCHMARK_COLUMN_NAME_MAX_LEN = 128
