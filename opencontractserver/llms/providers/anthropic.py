"""Anthropic provider — Claude models accessed via pydantic-ai's anthropic
integration. Issue #1381 reliability fixes (forced ``temperature=0`` for
structured runs, ``output_retries=3``) live in
``opencontractserver.llms.agents.pydantic_ai_agents`` and apply automatically
when this provider's ``pydantic_ai_prefix`` matches.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from opencontractserver.llms.providers.base import BaseLLMProvider
from opencontractserver.pipeline.base.settings_schema import (
    PipelineSetting,
    SettingType,
)


class AnthropicProvider(BaseLLMProvider):
    title = "Anthropic"
    description = (
        "Anthropic Claude models (Claude Opus / Sonnet / Haiku) accessed via "
        "pydantic-ai's anthropic integration."
    )
    pydantic_ai_prefix = "anthropic"
    default_models = (
        "claude-opus-4-7",
        "claude-sonnet-4-6",
        "claude-haiku-4-5",
        "claude-3-5-sonnet-latest",
        "claude-3-5-haiku-latest",
    )
    supports_structured_output = True
    supports_tools = True

    @dataclass
    class Settings:
        api_key: str = field(
            default="",
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.SECRET,
                    required=True,
                    description="Anthropic API key.",
                    env_var="ANTHROPIC_API_KEY",
                )
            },
        )
        base_url: str = field(
            default="",
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.OPTIONAL,
                    description=(
                        "Override base URL (rare — leave blank for "
                        "api.anthropic.com)."
                    ),
                )
            },
        )

    @classmethod
    def build_pydantic_ai_model(
        cls,
        *,
        model_id: str,
        api_key: str,
        base_url: Optional[str] = None,
        organization_id: Optional[str] = None,
    ) -> object:
        """Build a ``pydantic_ai.models.anthropic.AnthropicModel`` with an
        explicit ``AnthropicProvider(api_key=...)`` so the
        admin-configured key wins over the env.

        ``organization_id`` is accepted for signature symmetry but
        ignored — Anthropic's API has no equivalent header.
        """
        from pydantic_ai.models.anthropic import AnthropicModel
        from pydantic_ai.providers.anthropic import (
            AnthropicProvider as _PydAIAnthropicProvider,
        )

        provider_kwargs: dict = {"api_key": api_key}
        if base_url:
            provider_kwargs["base_url"] = base_url
        # organization_id intentionally unused — Anthropic SDK has no analog.

        return AnthropicModel(
            model_id, provider=_PydAIAnthropicProvider(**provider_kwargs)
        )
