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
