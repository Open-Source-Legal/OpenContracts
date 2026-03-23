# Constants for embedding models used by the OpenAI embedder pipeline component.

OPENAI_MODEL_DIMENSIONS: dict[str, int] = {
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "text-embedding-ada-002": 1536,
}

DEFAULT_OPENAI_EMBEDDING_MODEL = "text-embedding-3-small"
DEFAULT_OPENAI_EMBEDDING_DIMENSIONS = OPENAI_MODEL_DIMENSIONS[
    DEFAULT_OPENAI_EMBEDDING_MODEL
]
