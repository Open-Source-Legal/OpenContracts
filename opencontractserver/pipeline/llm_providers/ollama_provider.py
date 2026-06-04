"""Ollama (local) provider for pydantic-ai model routing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from opencontractserver.pipeline.base.llm_provider import (
    BaseLLMProvider,
    llm_api_key_field,
    llm_base_url_field,
)

# Ollama speaks the OpenAI-compatible API under the ``/v1`` path, so the
# default base URL points there rather than at the bare host:port.
OLLAMA_DEFAULT_BASE_URL = "http://localhost:11434/v1"


class OllamaProvider(BaseLLMProvider):
    """Local models served by an Ollama instance.

    The OpenAI-compatible endpoint is configurable live in System Settings
    (``base_url``); set it when the default ``http://localhost:11434/v1``
    does not match the deployment.
    """

    title: str = "Ollama (local)"
    description: str = (
        "Local models served by an Ollama instance via its OpenAI-compatible "
        "API. Set the base URL in System Settings to point at a remote host; "
        "an API key is only needed when Ollama sits behind an authenticating "
        "gateway."
    )
    author: str = "Ollama"

    @dataclass
    class Settings:
        base_url: str = llm_base_url_field(
            default=OLLAMA_DEFAULT_BASE_URL, env_var="OLLAMA_BASE_URL"
        )
        # Optional — only relevant when Ollama is fronted by an auth gateway.
        api_key: str = llm_api_key_field("OLLAMA_API_KEY")

    provider_key: ClassVar[str] = "ollama"
    supported_models: ClassVar[tuple[str, ...]] = (
        "llama3.3",
        "llama3.2",
        "qwen2.5",
        "mistral",
    )
    requires_api_key: ClassVar[bool] = False
