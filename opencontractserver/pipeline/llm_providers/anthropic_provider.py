"""Anthropic provider for pydantic-ai model routing."""

from __future__ import annotations

from typing import ClassVar

from opencontractserver.pipeline.base.llm_provider import BaseLLMProvider


class AnthropicProvider(BaseLLMProvider):
    """Anthropic's Claude family (Opus, Sonnet, Haiku)."""

    title: str = "Anthropic"
    description: str = (
        "Anthropic's Claude family (Opus, Sonnet, Haiku). Resolves API "
        "credentials from ANTHROPIC_API_KEY in the process environment."
    )
    author: str = "Anthropic"

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
