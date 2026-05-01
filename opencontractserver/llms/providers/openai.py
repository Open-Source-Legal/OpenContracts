"""OpenAI provider — covers OpenAI itself plus Azure / OpenAI-compatible
endpoints reachable via the same SDK shape (set ``base_url`` / use the
:class:`OpenAICompatibleProvider` subclass for fully self-hosted setups).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

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

    @classmethod
    def build_pydantic_ai_model(
        cls,
        *,
        model_id: str,
        api_key: str,
        base_url: Optional[str] = None,
        organization_id: Optional[str] = None,
    ) -> object:
        """Build a ``pydantic_ai.models.openai.OpenAIChatModel`` with an
        explicit ``OpenAIProvider(api_key=...)`` so the admin-configured
        key wins over whatever is in the env.
        """
        # Lazy imports — pydantic-ai 1.x exposes the right classes under
        # these module paths. Importing inside the method keeps the
        # base provider module loadable in environments that mock or
        # stub pydantic-ai (some test setups do).
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider as _PydAIOpenAIProvider

        provider_kwargs: dict = {"api_key": api_key}
        if base_url:
            provider_kwargs["base_url"] = base_url
        if organization_id:
            provider_kwargs["organization"] = organization_id

        return OpenAIChatModel(
            model_id, provider=_PydAIOpenAIProvider(**provider_kwargs)
        )
