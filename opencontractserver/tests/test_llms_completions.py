"""Tests for the registry-backed one-shot completion helper.

These pin the contract that ``agenerate_text`` walks the same model-resolution
chain as the agent factory (per-call ``model`` → ``corpus_preferred`` →
install-wide default) and is provider-agnostic — i.e. it never hardcodes a
provider/model the way the deleted ``SimpleLLMClient`` did.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from django.test import SimpleTestCase, override_settings

from opencontractserver.llms.completions import agenerate_text


class AgenerateTextTests(SimpleTestCase):
    # NOTE: ``agenerate_text`` imports its collaborators (get_default_llm_spec,
    # abuild_agent_model, make_pydantic_ai_agent) lazily inside the function
    # body, so these tests patch them at their *source* modules. If any of those
    # imports is ever hoisted to module level, the patches must move to
    # ``opencontractserver.llms.completions.<name>`` or they'll stop intercepting.
    def _fake_agent(self, output) -> MagicMock:
        agent = MagicMock()
        result = MagicMock()
        result.output = output
        agent.run = AsyncMock(return_value=result)
        return agent

    async def test_max_tokens_forwarded(self) -> None:
        """A non-None max_tokens must be threaded into model_settings."""
        fake_agent = self._fake_agent("Title")

        with patch(
            "opencontractserver.pipeline.utils.get_default_llm_spec",
            return_value="openai:gpt-4o",
        ), patch(
            "opencontractserver.llms.model_factory.abuild_agent_model",
            new=AsyncMock(side_effect=lambda spec: spec),
        ), patch(
            "opencontractserver.llms.agents.pydantic_ai_factory.make_pydantic_ai_agent",
            return_value=fake_agent,
        ) as mock_make:
            await agenerate_text("prompt", max_tokens=256)

        _, kwargs = mock_make.call_args
        self.assertEqual(kwargs["model_settings"]["max_tokens"], 256)

    async def test_none_output_returns_empty_string(self) -> None:
        """A None model output collapses to "" so caller fallbacks fire."""
        fake_agent = self._fake_agent(None)

        with patch(
            "opencontractserver.pipeline.utils.get_default_llm_spec",
            return_value="openai:gpt-4o",
        ), patch(
            "opencontractserver.llms.model_factory.abuild_agent_model",
            new=AsyncMock(side_effect=lambda spec: spec),
        ), patch(
            "opencontractserver.llms.agents.pydantic_ai_factory.make_pydantic_ai_agent",
            return_value=fake_agent,
        ):
            result = await agenerate_text("prompt")

        self.assertEqual(result, "")

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

    # override_settings is load-bearing, not redundant: with settings_default
    # mocked to "", resolve_model_spec still reads settings.DEFAULT_LLM /
    # settings.OPENAI_MODEL directly in its fallback branch. Clearing both forces
    # the chain past them to _HARD_DEFAULT_MODEL — the path this test names.
    @override_settings(DEFAULT_LLM="", OPENAI_MODEL="")
    async def test_hard_fallback_when_everything_unset(self) -> None:
        """No explicit/corpus/settings default falls back to the hard default."""
        fake_agent = self._fake_agent("Title")

        with patch(
            "opencontractserver.pipeline.utils.get_default_llm_spec",
            return_value="",
        ), patch(
            "opencontractserver.llms.model_factory.abuild_agent_model",
            new=AsyncMock(side_effect=lambda spec: spec),
        ) as mock_build, patch(
            "opencontractserver.llms.agents.pydantic_ai_factory.make_pydantic_ai_agent",
            return_value=fake_agent,
        ):
            await agenerate_text("prompt", model=None, corpus_preferred=None)

        # _HARD_DEFAULT_MODEL "gpt-4o" → normalised to the openai provider.
        mock_build.assert_awaited_once_with("openai:gpt-4o")

    async def test_temperature_none_is_omitted(self) -> None:
        """temperature=None must not inject a temperature into model_settings."""
        fake_agent = self._fake_agent("Title")

        with patch(
            "opencontractserver.pipeline.utils.get_default_llm_spec",
            return_value="openai:gpt-4o",
        ), patch(
            "opencontractserver.llms.model_factory.abuild_agent_model",
            new=AsyncMock(side_effect=lambda spec: spec),
        ), patch(
            "opencontractserver.llms.agents.pydantic_ai_factory.make_pydantic_ai_agent",
            return_value=fake_agent,
        ) as mock_make:
            await agenerate_text("prompt", temperature=None)

        _, kwargs = mock_make.call_args
        self.assertNotIn("temperature", kwargs["model_settings"])
