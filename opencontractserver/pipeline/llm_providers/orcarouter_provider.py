"""OrcaRouter provider for pydantic-ai model routing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from opencontractserver.pipeline.base.llm_provider import (
    BaseLLMProvider,
    llm_api_key_field,
    llm_base_url_field,
)

#: OrcaRouter's OpenAI-compatible endpoint. The gateway routes each request
#: to the best model for the job (``orcarouter/auto``) or to a specific model
#: (e.g. ``deepseek/deepseek-v4-pro``).
ORCAROUTER_DEFAULT_BASE_URL = "https://api.orcarouter.ai/v1"


class OrcaRouterProvider(BaseLLMProvider):
    """OrcaRouter — an OpenAI-compatible model routing gateway.

    OrcaRouter (https://www.orcarouter.ai) fronts dozens of hosted models
    behind one OpenAI-compatible endpoint, so ``orcarouter:`` model specs
    reuse the exact same pydantic-ai / OpenAI client path as the built-in
    OpenAI provider. API credentials and endpoint are configurable live in
    System Settings; when unset they fall back to ``ORCAROUTER_API_KEY`` in
    the process environment and the OrcaRouter default endpoint.
    """

    title: str = "OrcaRouter"
    description: str = (
        "OrcaRouter is an OpenAI-compatible model routing gateway "
        "(https://www.orcarouter.ai). It routes every request to the best "
        "model for the job — pick a router alias like orcarouter/auto or a "
        "specific hosted model. API credentials and endpoint are configurable "
        "live in System Settings; when unset they fall back to "
        "ORCAROUTER_API_KEY and the OrcaRouter default endpoint."
    )
    author: str = "OrcaRouter"

    @dataclass
    class Settings:
        api_key: str = llm_api_key_field("ORCAROUTER_API_KEY")
        base_url: str = llm_base_url_field(default=ORCAROUTER_DEFAULT_BASE_URL)

    provider_key: ClassVar[str] = "orcarouter"
    supported_models: ClassVar[tuple[str, ...]] = (
        "orcarouter/auto",
        "openai/gpt-5.5",
        "google/gemini-3.5-flash",
        "anthropic/claude-opus-4.8",
        "grok/grok-4.3",
        "deepseek/deepseek-v4-pro",
        "minimax/minimax-m2.7",
        "qwen/qwen3.7-max",
    )
    requires_api_key: ClassVar[bool] = True
