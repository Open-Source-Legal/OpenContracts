"""Ollama (local) provider for pydantic-ai model routing."""

from __future__ import annotations

from typing import ClassVar

from opencontractserver.pipeline.base.llm_provider import BaseLLMProvider


class OllamaProvider(BaseLLMProvider):
    """Local models served by an Ollama instance.

    Reads OLLAMA_BASE_URL from the environment when the default
    ``http://localhost:11434`` does not match the deployment.
    """

    title: str = "Ollama (local)"
    description: str = (
        "Local models served by an Ollama instance. Reads OLLAMA_BASE_URL "
        "from the environment when the default http://localhost:11434 is "
        "not appropriate. No API key required."
    )
    author: str = "Ollama"

    provider_key: ClassVar[str] = "ollama"
    supported_models: ClassVar[tuple[str, ...]] = (
        "llama3.3",
        "llama3.2",
        "qwen2.5",
        "mistral",
    )
    requires_api_key: ClassVar[bool] = False
