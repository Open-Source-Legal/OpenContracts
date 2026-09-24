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

#: Provider prefix of ``orcarouter:`` model specs.
ORCAROUTER_PROVIDER_KEY = "orcarouter"

#: Process-environment fallback for the OrcaRouter API key.
ORCAROUTER_API_KEY_ENV_VAR = "ORCAROUTER_API_KEY"

#: Inert key sent when none is configured. Passing ``None`` instead would let
#: the OpenAI client fall back to ``OPENAI_API_KEY`` and ship the install's
#: OpenAI secret to the OrcaRouter host.
ORCAROUTER_API_KEY_PLACEHOLDER = "orcarouter-api-key-not-set"


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
        api_key: str = llm_api_key_field(ORCAROUTER_API_KEY_ENV_VAR)
        base_url: str = llm_base_url_field(default=ORCAROUTER_DEFAULT_BASE_URL)

    provider_key: ClassVar[str] = ORCAROUTER_PROVIDER_KEY
    # Only the router alias is offered in the picker. Specific routed models
    # (``vendor/model``) remain selectable by typing the spec, but each one
    # offered here needs a verified MODEL_CONTEXT_WINDOWS entry (issue #2078).
    supported_models: ClassVar[tuple[str, ...]] = ("orcarouter/auto",)
    requires_api_key: ClassVar[bool] = True
