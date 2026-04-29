"""LLM provider registry and concrete provider implementations.

Mirrors the shape of ``opencontractserver.pipeline.registry`` but targets LLM
providers (OpenAI, Anthropic, Google, …) instead of pipeline components. Each
provider is a small declarative class describing its display name, the
pydantic-ai model-string prefix it uses, and the credential fields it accepts
(api_key, api_base, organization, …).

Concrete providers in this package are auto-discovered on first registry
access — drop a new ``BaseLLMProvider`` subclass into a module under
``opencontractserver.llms.providers.*`` and it becomes available without
manual registration.
"""

from opencontractserver.llms.providers.base import (
    BaseLLMProvider,
    CredentialField,
    LLMProviderDefinition,
)
from opencontractserver.llms.providers.registry import (
    LLMProviderRegistry,
    get_provider,
    get_provider_registry,
)

__all__ = [
    "BaseLLMProvider",
    "CredentialField",
    "LLMProviderDefinition",
    "LLMProviderRegistry",
    "get_provider",
    "get_provider_registry",
]
