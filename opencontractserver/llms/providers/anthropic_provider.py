"""Anthropic provider definition."""

from opencontractserver.llms.providers.base import BaseLLMProvider, CredentialField


class AnthropicProvider(BaseLLMProvider):
    key = "anthropic"
    title = "Anthropic"
    description = "Anthropic Claude models (Sonnet, Opus, Haiku)."
    pydantic_ai_prefix = "anthropic"
    credential_schema = (
        CredentialField(
            name="api_key",
            label="API key",
            description="Anthropic API key (sk-ant-…).",
            is_secret=True,
            required=True,
        ),
        CredentialField(
            name="base_url",
            label="Base URL (optional)",
            description="Override the Anthropic-compatible endpoint (proxies, gateways).",
            is_secret=False,
            required=False,
        ),
    )
    default_models = (
        "claude-opus-4-7",
        "claude-sonnet-4-6",
        "claude-haiku-4-5",
    )

    def build_environment_overrides(self, credentials: dict) -> dict[str, str | None]:
        return {
            "ANTHROPIC_API_KEY": credentials.get("api_key") or None,
            "ANTHROPIC_BASE_URL": credentials.get("base_url") or None,
        }
