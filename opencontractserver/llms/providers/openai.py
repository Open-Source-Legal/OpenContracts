"""OpenAI provider — covers OpenAI itself plus Azure / OpenAI-compatible
endpoints reachable via the same SDK shape (set ``base_url`` / use the
:class:`OpenAICompatibleProvider` subclass for fully self-hosted setups).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from opencontractserver.llms.providers.base import BaseLLMProvider
from opencontractserver.pipeline.base.settings_schema import (
    PipelineSetting,
    SettingType,
)


class OpenAIProvider(BaseLLMProvider):
    title = "OpenAI"
    description = (
        "OpenAI / Azure OpenAI / OpenAI-API-compatible models accessed via "
        "pydantic-ai's openai integration."
    )
    pydantic_ai_prefix = "openai"
    default_models = (
        "gpt-4o",
        "gpt-4o-mini",
        "gpt-4-turbo",
        "gpt-3.5-turbo",
        "o1",
        "o1-mini",
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
                    description="OpenAI API key (sk-...).",
                    env_var="OPENAI_API_KEY",
                )
            },
        )
        base_url: str = field(
            default="",
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.OPTIONAL,
                    description=(
                        "Override base URL for self-hosted / Azure OpenAI / "
                        "compatible endpoints. Leave blank for api.openai.com."
                    ),
                )
            },
        )
        organization_id: str = field(
            default="",
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.OPTIONAL,
                    description=(
                        "Optional OpenAI organization ID (sets the "
                        "OpenAI-Organization request header)."
                    ),
                )
            },
        )
