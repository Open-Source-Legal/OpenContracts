"""Google Gemini provider for pydantic-ai model routing."""

from __future__ import annotations

from typing import ClassVar

from opencontractserver.pipeline.base.llm_provider import BaseLLMProvider


class GoogleProvider(BaseLLMProvider):
    """Google Gemini models via the Generative Language API (AI Studio)."""

    title: str = "Google Gemini"
    description: str = (
        "Google Gemini models via the Generative Language API (AI Studio). "
        "Resolves API credentials from GEMINI_API_KEY in the process "
        "environment."
    )
    author: str = "Google"

    # ``google-gla`` is pydantic-ai's prefix for the public AI-Studio
    # endpoint. Vertex AI lives under ``google-vertex`` and would be a
    # separate provider component.
    provider_key: ClassVar[str] = "google-gla"
    supported_models: ClassVar[tuple[str, ...]] = (
        "gemini-2.0-flash",
        "gemini-2.0-flash-lite",
        "gemini-1.5-pro",
        "gemini-1.5-flash",
    )
    requires_api_key: ClassVar[bool] = True
