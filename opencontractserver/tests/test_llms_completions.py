"""Tests for the registry-backed one-shot completion helper.

These pin the contract that ``agenerate_text`` walks the same model-resolution
chain as the agent factory (per-call ``model`` → ``corpus_preferred`` →
install-wide default) and is provider-agnostic — i.e. it never hardcodes a
provider/model the way the deleted ``SimpleLLMClient`` did.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from django.test import SimpleTestCase

from opencontractserver.llms.completions import agenerate_text


class AgenerateTextTests(SimpleTestCase):
    def _fake_agent(self, output: str) -> MagicMock:
        agent = MagicMock()
        result = MagicMock()
        result.output = output
        agent.run = AsyncMock(return_value=result)
        return agent

    async def test_corpus_preferred_wins_over_settings_default(self) -> None:
        """corpus_preferred beats the install-wide default and is normalised."""
        fake_agent = self._fake_agent("  Short Title  ")

        with patch(
            "opencontractserver.pipeline.utils.get_default_llm_spec",
            return_value="openai:gpt-4o",
        ), patch(
            "opencontractserver.llms.model_factory.abuild_agent_model",
            new=AsyncMock(side_effect=lambda spec: f"BUILT::{spec}"),
        ) as mock_build, patch(
            "opencontractserver.llms.agents.pydantic_ai_factory.make_pydantic_ai_agent",
            return_value=fake_agent,
        ) as mock_make:
            title = await agenerate_text(
                "prompt text",
                instructions="be concise",
                corpus_preferred="anthropic:claude-haiku-4-5",
            )

        # Output is returned stripped.
        self.assertEqual(title, "Short Title")
        # The corpus model beat the settings default and flowed to the factory.
        mock_build.assert_awaited_once_with("anthropic:claude-haiku-4-5")
        args, kwargs = mock_make.call_args
        self.assertEqual(args[0], "BUILT::anthropic:claude-haiku-4-5")
        self.assertEqual(kwargs["instructions"], "be concise")
        self.assertEqual(kwargs["model_settings"]["temperature"], 0.7)
        fake_agent.run.assert_awaited_once_with("prompt text")

    async def test_falls_back_to_settings_default(self) -> None:
        """With no per-call model and no corpus_preferred, the settings default wins."""
        fake_agent = self._fake_agent("Title")

        with patch(
            "opencontractserver.pipeline.utils.get_default_llm_spec",
            return_value="anthropic:claude-opus-4-6",
        ), patch(
            "opencontractserver.llms.model_factory.abuild_agent_model",
            new=AsyncMock(side_effect=lambda spec: spec),
        ) as mock_build, patch(
            "opencontractserver.llms.agents.pydantic_ai_factory.make_pydantic_ai_agent",
            return_value=fake_agent,
        ):
            await agenerate_text("prompt", corpus_preferred=None)

        mock_build.assert_awaited_once_with("anthropic:claude-opus-4-6")

    async def test_explicit_model_wins_over_corpus(self) -> None:
        """An explicit per-call model overrides the corpus preference."""
        fake_agent = self._fake_agent("Title")

        with patch(
            "opencontractserver.pipeline.utils.get_default_llm_spec",
            return_value="openai:gpt-4o",
        ), patch(
            "opencontractserver.llms.model_factory.abuild_agent_model",
            new=AsyncMock(side_effect=lambda spec: spec),
        ) as mock_build, patch(
            "opencontractserver.llms.agents.pydantic_ai_factory.make_pydantic_ai_agent",
            return_value=fake_agent,
        ):
            await agenerate_text(
                "prompt",
                model="google-gla:gemini-1.5-pro",
                corpus_preferred="anthropic:claude-haiku-4-5",
            )

        mock_build.assert_awaited_once_with("google-gla:gemini-1.5-pro")
