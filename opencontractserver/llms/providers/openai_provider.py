"""OpenAI provider definition."""

from opencontractserver.llms.providers.base import BaseLLMProvider, CredentialField


class OpenAIProvider(BaseLLMProvider):
    key = "openai"
    title = "OpenAI"
    description = "OpenAI GPT models (gpt-4o, gpt-4.1, o-series, …)."
    pydantic_ai_prefix = "openai"
    credential_schema = (
        CredentialField(
            name="api_key",
            label="API key",
            description="OpenAI API key (sk-…).",
            is_secret=True,
            required=True,
        ),
        CredentialField(
            name="base_url",
            label="Base URL (optional)",
            description="Override the OpenAI-compatible endpoint (proxies, gateways).",
            is_secret=False,
            required=False,
        ),
        CredentialField(
            name="organization",
            label="Organization ID (optional)",
            description="OpenAI organization identifier, if your account requires one.",
            is_secret=False,
            required=False,
        ),
    )
    default_models = (
        "gpt-4o",
        "gpt-4o-mini",
        "gpt-4.1",
        "gpt-4.1-mini",
        "o4-mini",
    )

    def build_environment_overrides(self, credentials: dict) -> dict[str, str | None]:
        return {
            "OPENAI_API_KEY": credentials.get("api_key") or None,
            "OPENAI_BASE_URL": credentials.get("base_url") or None,
            "OPENAI_ORGANIZATION": credentials.get("organization") or None,
        }
