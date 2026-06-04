"""Anthropic provider for pydantic-ai model routing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from opencontractserver.pipeline.base.llm_provider import (
    BaseLLMProvider,
    llm_api_key_field,
    llm_base_url_field,
)


class AnthropicProvider(BaseLLMProvider):
    """Anthropic's Claude family (Opus, Sonnet, Haiku)."""

    title: str = "Anthropic"
    description: str = (
        "Anthropic's Claude family (Opus, Sonnet, Haiku). API credentials and "
        "endpoint are configurable live in System Settings; when unset they "
        "fall back to ANTHROPIC_API_KEY in the process environment."
    )
    author: str = "Anthropic"

    @dataclass
    class Settings:
        api_key: str = llm_api_key_field("ANTHROPIC_API_KEY")
        base_url: str = llm_base_url_field()

    provider_key: ClassVar[str] = "anthropic"
    supported_models: ClassVar[tuple[str, ...]] = (
        "claude-opus-4-7",
        "claude-opus-4-6",
        "claude-sonnet-4-6",
        "claude-haiku-4-5",
        "claude-3-7-sonnet-latest",
        "claude-3-5-sonnet-latest",
        "claude-3-5-haiku-latest",
    )
    requires_api_key: ClassVar[bool] = True
