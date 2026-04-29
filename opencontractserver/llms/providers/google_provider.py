"""Google Generative Language (Gemini) provider definition."""

from opencontractserver.llms.providers.base import BaseLLMProvider, CredentialField


class GoogleProvider(BaseLLMProvider):
    key = "google-gla"
    title = "Google (Generative Language)"
    description = "Google Gemini models via the Generative Language API."
    pydantic_ai_prefix = "google-gla"
    credential_schema = (
        CredentialField(
            name="api_key",
            label="API key",
            description="Google AI Studio API key.",
            is_secret=True,
            required=True,
        ),
    )
    default_models = (
        "gemini-2.5-pro",
        "gemini-2.5-flash",
        "gemini-1.5-pro",
    )

    def build_environment_overrides(self, credentials: dict) -> dict[str, str | None]:
        return {"GEMINI_API_KEY": credentials.get("api_key") or None}
