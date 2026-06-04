"""OpenAI provider for pydantic-ai model routing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from opencontractserver.pipeline.base.llm_provider import (
    BaseLLMProvider,
    llm_api_key_field,
    llm_base_url_field,
)


class OpenAIProvider(BaseLLMProvider):
    """OpenAI's hosted GPT and o-series models."""

    title: str = "OpenAI"
    description: str = (
        "OpenAI's hosted GPT and o-series models. API credentials and endpoint "
        "are configurable live in System Settings; when unset they fall back to "
        "OPENAI_API_KEY in the process environment. Set a custom base URL to "
        "target an OpenAI-compatible gateway."
    )
    author: str = "OpenAI"

    @dataclass
    class Settings:
        api_key: str = llm_api_key_field("OPENAI_API_KEY")
        base_url: str = llm_base_url_field()

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
