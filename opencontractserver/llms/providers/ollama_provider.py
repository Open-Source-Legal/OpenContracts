"""Ollama / OpenAI-compatible local-LLM provider definition."""

from opencontractserver.llms.providers.base import BaseLLMProvider, CredentialField


class OllamaProvider(BaseLLMProvider):
    key = "ollama"
    title = "Ollama (local)"
    description = "Self-hosted models via the OpenAI-compatible Ollama server."
    # pydantic-ai talks to Ollama through its OpenAI-compatible endpoint.
    pydantic_ai_prefix = "openai"
    credential_schema = (
        CredentialField(
            name="base_url",
            label="Base URL",
            description="Ollama OpenAI-compatible URL, e.g. http://ollama:11434/v1",
            is_secret=False,
            required=True,
            default="http://ollama:11434/v1",
        ),
        CredentialField(
            name="api_key",
            label="API key (optional)",
            description="Most Ollama deployments don't require one; leave blank if so.",
            is_secret=True,
            required=False,
        ),
    )
    default_models = (
        "llama3.2",
        "qwen2.5",
        "mistral",
    )
    # Local models often don't reliably support structured output / tools — admins
    # can override these on the LLMModel row.
    supports_structured_output = False
    supports_tools = True

    def build_environment_overrides(self, credentials: dict) -> dict[str, str | None]:
        # Talks to Ollama via its OpenAI-compatible endpoint.
        return {
            "OPENAI_BASE_URL": credentials.get("base_url") or None,
            # Ollama doesn't validate the key, but pydantic-ai requires one.
            "OPENAI_API_KEY": credentials.get("api_key") or "ollama",
        }
