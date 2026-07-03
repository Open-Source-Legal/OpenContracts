"""Tunables for the extraction pipeline.

Values mirror the production constants in OpenContracts
(``opencontractserver/constants/extraction.py`` and ``constants/llm.py``) so
the standalone service behaves like the battle-tested pipeline it was derived
from. See the README for the full mapping.
"""

from __future__ import annotations

# --- Model / agent -----------------------------------------------------------

#: Default model identifier (any string pydantic-ai accepts, e.g.
#: ``"openai:gpt-4o-mini"`` or ``"anthropic:claude-sonnet-5"``). Overridable
#: per-extract, per-engine, or via the ``OC_EXTRACT_MODEL`` env var.
DEFAULT_MODEL = "openai:gpt-4o-mini"

#: Env var consulted when no explicit model is configured.
MODEL_ENV_VAR = "OC_EXTRACT_MODEL"

#: Default sampling temperature for non-Anthropic models. Anthropic models are
#: forced to 0 — they tend to keep narrating instead of committing to the
#: structured output at higher temperatures (OpenContracts issue #1381).
DEFAULT_TEMPERATURE = 0.3

#: Hard cap on model requests per cell so a weak model cannot loop forever on
#: a hard or absent value. A capable model commits well within this budget.
REQUEST_LIMIT = 20

#: Structured-output validation retries before pydantic-ai gives up.
OUTPUT_RETRIES = 3

# --- Prompt construction ------------------------------------------------------

#: Documents whose text is at or below this many characters get their FULL
#: text injected into the prompt (fenced) so the agent can answer — and
#: confirm the ABSENCE of a value — in a single read instead of search-looping.
FULL_TEXT_CHAR_LIMIT = 24_000

#: Separator in ``match_text`` that turns it into few-shot example values.
FEW_SHOT_SEPARATOR = "|||"

# --- Retrieval ----------------------------------------------------------------

#: Default number of chunks returned by the ``search_document`` tool.
SEARCH_TOP_K = 8

#: Target chunk size (chars) for the retrieval index.
CHUNK_MAX_CHARS = 1_500

#: Default window for a ``read_document_text`` tool call when the model
#: doesn't ask for a size.
READ_WINDOW_DEFAULT_CHARS = 4_000

#: Max characters a single ``read_document_text`` tool call may return.
READ_WINDOW_MAX_CHARS = 8_000

#: BM25 term-frequency saturation / length-normalization parameters
#: (standard Robertson defaults).
BM25_K1 = 1.5
BM25_B = 0.75

#: Documents kept in the engine's per-document chunk/BM25-index LRU cache.
INDEX_CACHE_MAX_DOCS = 8

# --- Grounding (citation alignment) --------------------------------------------

#: Strings shorter than this aren't grounded (too ambiguous: "Yes", "42").
MIN_GROUNDABLE_LENGTH = 5

#: Cap on strings grounded per cell (protects against huge list extractions).
MAX_GROUNDABLE_STRINGS = 50

#: Skip fuzzy alignment when the document exceeds this many characters.
MAX_DOC_LENGTH_FOR_FUZZY = 200_000

#: Skip fuzzy alignment for extracted strings longer than this.
MAX_QUERY_LENGTH_FOR_FUZZY = 2_000

#: Minimum similarity ratio for a fuzzy alignment to count.
FUZZY_THRESHOLD = 0.75

#: Matching blocks within this many query-lengths of the anchor block
#: contribute to a fuzzy alignment.
FUZZY_BLOCK_WINDOW_FACTOR = 2

#: Max characters of source text stored per citation snippet.
SOURCE_SNIPPET_MAX_CHARS = 400

# --- Failure-mode classification (mirrors NONE_RESULT_* in OpenContracts) ------

#: Agent searched, decided the value is absent, and committed to null.
#: Legitimate signal about the document — NOT a pipeline failure.
NONE_RESULT_AGENT_COMMITTED = "agent_committed_none"

#: The run ended without the model ever calling the result tool.
NONE_RESULT_NO_FINAL = "no_final_response"

#: The run exhausted ``REQUEST_LIMIT`` before committing.
NONE_RESULT_USAGE_LIMIT = "usage_limit_exceeded"

#: The extraction raised an unexpected error.
NONE_RESULT_ERROR = "error"

# --- Runner / service -----------------------------------------------------------

#: Concurrent cell extractions per run.
DEFAULT_CONCURRENCY = 4

#: Default SQLite database path.
DEFAULT_DB_PATH = "oc_extract.db"

#: Default host/port for ``oc-extract serve``.
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8500

#: Max size of a single uploaded file. The service is single-tenant and
#: binds to localhost by default, but a cap keeps an oversized upload from
#: ballooning memory if it is ever exposed more widely.
MAX_UPLOAD_BYTES = 50 * 1024 * 1024
