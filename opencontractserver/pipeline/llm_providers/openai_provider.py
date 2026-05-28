"""OpenAI provider for pydantic-ai model routing."""

from __future__ import annotations

from typing import ClassVar

from opencontractserver.pipeline.base.llm_provider import BaseLLMProvider


class OpenAIProvider(BaseLLMProvider):
    """OpenAI's hosted GPT and o-series models."""

    title: str = "OpenAI"
    description: str = (
        "OpenAI's hosted GPT and o-series models. Resolves API credentials "
        "from OPENAI_API_KEY in the process environment."
    )
    author: str = "OpenAI"

    provider_key: ClassVar[str] = "openai"
    supported_models: ClassVar[tuple[str, ...]] = (
        "gpt-4o",
        "gpt-4o-mini",
        "gpt-4.1",
        "gpt-4.1-mini",
        "o3-mini",
        "o1",
        "o1-mini",
    )
    requires_api_key: ClassVar[bool] = True
