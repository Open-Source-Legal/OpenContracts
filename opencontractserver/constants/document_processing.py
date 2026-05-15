"""
Constants for document processing pipeline.

WARNING: This module is imported from config/settings/base.py at startup.
It MUST remain free of Django imports (models, apps, etc.) to avoid
AppRegistryNotReady errors during settings loading.
"""

# MIME type for Markdown / CAML files.  Used in doc_tasks.py to skip
# ingestion and in the parser pipeline for type detection.
MARKDOWN_MIME_TYPE = "text/markdown"

# Title used for the corpus-level CAML article — the "Readme.CAML" Markdown
# document attached to a corpus that drives the citation-review tooling.
#
# The frontend stores the same string under the name ``CAML_ARTICLE_FILENAME``
# in ``frontend/src/assets/configurations/constants.ts`` because the
# frontend treats the article as a synthetic file the user opens from the
# document list (it sets ``Document.title = CAML_ARTICLE_FILENAME`` when
# creating the row).  The backend treats it as a *title* — it queries
# ``Document.objects.filter(title=CAML_ARTICLE_TITLE)``.  The two names
# refer to the same literal value (``"Readme.CAML"``) and MUST stay in
# sync; the rename divergence is intentional so each side reads naturally
# in its own context.
CAML_ARTICLE_TITLE = "Readme.CAML"

# MIME type for Microsoft Word (DOCX) documents.
DOCX_MIME_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)

# File types that are stored as txt_extract_file (plain text, no parsing needed).
# Shared between versioning.py and corpus models.py — single source of truth.
TEXT_MIMETYPES = {"text/plain", MARKDOWN_MIME_TYPE, "application/txt"}

# Maximum file upload size in bytes (5 GB).
# Used by Django's DATA_UPLOAD_MAX_MEMORY_SIZE setting.
MAX_FILE_UPLOAD_SIZE_BYTES = 5_242_880_000

# Default path prefix for documents uploaded without explicit path
# Used when generating document paths in corpus operations
DEFAULT_DOCUMENT_PATH_PREFIX = "/documents"

# Default batch size for embedding generation tasks
# Controls how many annotations are processed per Celery task to prevent queue flooding
EMBEDDING_BATCH_SIZE = 100

# Default sub-batch size used *within* a Celery task when calling
# ``embedder.embed_texts_batch()``. Kept separate from
# ``EMBEDDING_BATCH_SIZE`` (task-level grouping) because API limits may
# differ from task sizing. This is a global *fallback* — concrete
# embedders should override ``BaseEmbedder.api_batch_size`` with a value
# appropriate for their provider (OpenAI accepts up to 2048 inputs;
# the local microservice caps at MICROSERVICE_EMBEDDER_MAX_BATCH_SIZE).
# Must be <= MICROSERVICE_EMBEDDER_MAX_BATCH_SIZE for the microservice
# embedder; the system check in documents/checks.py validates this.
EMBEDDING_API_BATCH_SIZE = 50

# Maximum number of texts accepted by MicroserviceEmbedder.embed_texts_batch().
# Exceeding this raises ValueError rather than silently truncating.
MICROSERVICE_EMBEDDER_MAX_BATCH_SIZE = 100

# Validation that EMBEDDING_API_BATCH_SIZE <= MICROSERVICE_EMBEDDER_MAX_BATCH_SIZE
# is enforced via a Django system check in documents/checks.py (documents.E001)
# rather than a bare raise here, so misconfiguration surfaces as a clear Django
# check error during startup instead of an opaque import-time traceback.

# HTTP request timeout (seconds) for single-text embedding calls.
EMBEDDER_SINGLE_REQUEST_TIMEOUT_SECONDS = 30

# HTTP request timeout (seconds) for batch embedding calls.
# Larger than the single timeout because batches process multiple texts.
EMBEDDER_BATCH_REQUEST_TIMEOUT_SECONDS = 60

# Character-count guard for OpenAI embedding input. The hosted /embeddings
# endpoint caps input at 8192 tokens per text; truncating on the char side
# at ~4x the token budget (English averages ~4 chars/token) keeps us well
# under the cap for any realistic input. Mirrors the silent-tokenizer
# truncation that ``sentence-transformers`` applies locally so OpenAI users
# get the same robustness instead of a fatal 400 "maximum context length"
# from a long whole-document chunk. See ``OpenAIEmbedder._embed_text_impl``
# and ``OpenAIEmbedder.embed_texts_batch``.
OPENAI_EMBEDDER_MAX_INPUT_CHARS = 30_000

# HTTP request timeout (seconds) for reranker microservice calls.
# Reranking typically runs over tens of candidates (top_k * oversample), so
# a modest timeout is sufficient. Retrieval degrades gracefully to the
# first-stage ordering on reranker failure.
RERANKER_REQUEST_TIMEOUT_SECONDS = 30

# Maximum number of embedding batch tasks to queue in a single reembed_corpus run.
# For very large corpuses (millions of annotations), this prevents flooding the
# Celery queue. Remaining annotations will be logged but not queued; re-running
# the re-embed will pick up where it left off (idempotent via existing-embedding check).
MAX_REEMBED_TASKS_PER_RUN = 500

# Maximum length for filename/title truncation when generating document paths
MAX_FILENAME_LENGTH = 100

# Personal corpus defaults
PERSONAL_CORPUS_TITLE = "My Documents"
PERSONAL_CORPUS_DESCRIPTION = "Your personal document collection"

# Maximum length for error message stored on Document.processing_error
MAX_PROCESSING_ERROR_LENGTH = 5000

# Maximum length for traceback stored on Document.processing_error_traceback
MAX_PROCESSING_TRACEBACK_LENGTH = 10000

# Maximum length for error message in GraphQL display (UI truncation)
MAX_PROCESSING_ERROR_DISPLAY_LENGTH = 500

# Maximum length for document title/description preview in notifications.
# Used when generating a short doc title for notification payloads.
NOTIFICATION_DOC_TITLE_MAX_LENGTH = 50

# Maximum length for error messages stored on WorkerDocumentUpload.error_message.
# Prevents unbounded exception strings from bloating the staging table.
MAX_UPLOAD_ERROR_MESSAGE_LENGTH = 2000

# Maximum number of worker document uploads returned by the GraphQL query resolver.
WORKER_UPLOADS_QUERY_LIMIT = 100

# ---------------------------------------------------------------------------
# Chunked document processing constants
# ---------------------------------------------------------------------------

# Maximum number of pages per chunk when splitting large documents for parsing.
# Each chunk is sent as an independent parsing request.
DEFAULT_MAX_PAGES_PER_CHUNK = 50

# Documents with fewer pages than this threshold are parsed as a single request.
DEFAULT_MIN_PAGES_FOR_CHUNKING = 75

# Maximum number of chunks to process concurrently via thread pool.
# Controls parallelism of HTTP requests to the parsing microservice.
DEFAULT_MAX_CONCURRENT_CHUNKS = 3

# Per-chunk retry limit (within the parser, before raising to Celery).
DEFAULT_CHUNK_RETRY_LIMIT = 1

# Maximum backoff sleep (seconds) between per-chunk retries.
# Caps the exponential backoff (5s * 2^attempt) so that increasing
# chunk_retry_limit doesn't block Celery workers excessively.
MAX_CHUNK_RETRY_BACKOFF_SECONDS = 30

# ---------------------------------------------------------------------------
# Path disambiguation constants
# ---------------------------------------------------------------------------

# Hard cap on numeric suffix attempts when disambiguating document paths.
# Prevents unbounded loops in _disambiguate_path() if a corpus has hundreds
# of documents sharing the same filename in the same folder.
MAX_PATH_DISAMBIGUATION_SUFFIX = 1000

# Maximum number of *retries* (after the initial attempt) when
# DocumentPath.objects.create() raises IntegrityError due to a TOCTOU race
# against the `unique_active_path_per_corpus` partial unique constraint.
# Each retry re-runs _disambiguate_path() with the losing path added to the
# in-memory occupied set, so a small number of retries is sufficient to
# resolve transient concurrent collisions even under heavy load.
#
# The total number of INSERT *attempts* is therefore MAX_PATH_CREATE_RETRIES + 1
# (the initial attempt plus this many retries).  All call sites use
# ``range(MAX_PATH_CREATE_RETRIES + 1)`` and log ``MAX_PATH_CREATE_RETRIES + 1``
# as the attempt ceiling to make this intent explicit.
MAX_PATH_CREATE_RETRIES = 5

# Human-readable prefix for path-uniqueness collision messages.
# Used in both user-facing error strings and log messages when
# _disambiguate_path() detects a naming conflict.
PATH_CONFLICT_MSG = "Path conflict"

# Text-chunker defaults used by SentenceChunker / SlidingWindowChunker
# (see opencontractserver/pipeline/parsers/text_chunkers.py).
DEFAULT_SENTENCE_CHUNKER_MODEL = "en_core_web_lg"
DEFAULT_SLIDING_WINDOW_SIZE = 1000
DEFAULT_SLIDING_WINDOW_OVERLAP = 200

# Hard cap on how far the word-boundary snapper in _split_long_span will
# walk past window_size looking for whitespace. Protects against pathological
# inputs (e.g. a 10MB log line with no spaces) that would otherwise make the
# inner scan O(n²) relative to the span length.
MAX_WORD_BOUNDARY_SCAN_CHARS = 512

# ---------------------------------------------------------------------------
# Privacy-filter PII detection client
# ---------------------------------------------------------------------------

# Chunk size for the privacy-filter detect endpoint. Set 10_000 chars under
# the service's default MAX_INPUT_CHARS (50_000) so an upstream cap bump
# doesn't immediately invalidate this constant.
PRIVACY_FILTER_CHUNK_SIZE = 40_000

# Overlap between consecutive chunks sent to the privacy filter. 500 chars
# is enough to capture full names, phone numbers, and addresses spanning a
# chunk boundary without exploding the request count.
PRIVACY_FILTER_CHUNK_OVERLAP = 500

# Batch size for ``Annotation.objects.bulk_create`` when persisting PII
# detections. Keeps the per-transaction insert size bounded so a document
# with thousands of hits doesn't ship a single oversized INSERT to Postgres.
PII_ANNOTATION_BULK_BATCH_SIZE = 200

# ---------------------------------------------------------------------------
# CAML article citation review tools
# ---------------------------------------------------------------------------

# Cap on candidates returned by ``apropose_caml_citation_match`` -- keeps the
# tool output bounded regardless of what the LLM passes for ``limit``.
CAML_CITATION_MAX_CANDIDATES = 25

# Window of surrounding text returned in ``aapply_caml_article_edit``'s preview
# so the approval modal can show "before/after" context without dumping the
# whole document.
CAML_EDIT_PREVIEW_RADIUS_CHARS = 80
