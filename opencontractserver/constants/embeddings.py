# Constants for supported text embedding providers and their accounting contracts.

OPENAI_EMBEDDER_PATH = (
    "opencontractserver.pipeline.embedders.openai_embedder.OpenAIEmbedder"
)
OPENAI_API_BASE_URL = "https://api.openai.com/v1"
# Bump when the bounded adapter's request or usage-accounting contract changes.
OPENAI_ACCOUNTED_EMBEDDING_VERSION = "openai-text-embedding-v1"
MICROSERVICE_EMBEDDER_PATH = "opencontractserver.pipeline.embedders.sent_transformer_microservice.MicroserviceEmbedder"
MICROSERVICE_ACCOUNTED_EMBEDDING_VERSION = "self-hosted-text-embedding-v1"
MICROSERVICE_MODEL_REVISION_PATTERN = r"[A-Za-z0-9_.:/@-]{1,200}"

OPENAI_MODEL_DIMENSIONS: dict[str, int] = {
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "text-embedding-ada-002": 1536,
}

DEFAULT_OPENAI_EMBEDDING_MODEL = "text-embedding-3-small"
DEFAULT_OPENAI_EMBEDDING_DIMENSIONS = OPENAI_MODEL_DIMENSIONS[
    DEFAULT_OPENAI_EMBEDDING_MODEL
]

# Postgres regex for text with nothing to embed: exactly the characters
# Python's str.isspace() matches, which str.strip() removes and the embedding
# tasks therefore skip. Spelled out because Postgres' \s follows the database
# locale and may not match Unicode spaces such as NBSP.
BLANK_TEXT_SQL_PATTERN = (
    r"^[\u0009-\u000d\u001c-\u0020\u0085\u00a0\u1680\u2000-\u200a"
    r"\u2028\u2029\u202f\u205f\u3000]*$"
)
