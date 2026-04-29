"""Azure OpenAI provider definition."""

from opencontractserver.llms.providers.base import BaseLLMProvider, CredentialField


class AzureOpenAIProvider(BaseLLMProvider):
    key = "azure"
    title = "Azure OpenAI"
    description = "OpenAI models deployed on Azure (deployment name = model_name)."
    pydantic_ai_prefix = "azure"
    credential_schema = (
        CredentialField(
            name="api_key",
            label="API key",
            description="Azure OpenAI resource key.",
            is_secret=True,
            required=True,
        ),
        CredentialField(
            name="azure_endpoint",
            label="Endpoint",
            description="Resource endpoint, e.g. https://my-resource.openai.azure.com",
            is_secret=False,
            required=True,
        ),
        CredentialField(
            name="api_version",
            label="API version",
            description="e.g. 2024-08-01-preview",
            is_secret=False,
            required=True,
            default="2024-08-01-preview",
        ),
    )
    # Azure model_name is the deployment name; defaults are intentionally empty
    # because they're tenant-specific.
    default_models = ()

    def build_environment_overrides(self, credentials: dict) -> dict[str, str | None]:
        return {
            "AZURE_OPENAI_API_KEY": credentials.get("api_key") or None,
            "AZURE_OPENAI_ENDPOINT": credentials.get("azure_endpoint") or None,
            "OPENAI_API_VERSION": credentials.get("api_version") or None,
        }
