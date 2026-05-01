"""Tests for the chat-agent wiring of the LLM resolver (Phase 2b-chat).

Covers:
* :func:`_maybe_resolve_default_llm` (the helper both factory paths call):
  caller-pinned models pass through, ``llm_not_configured`` falls back to
  inputs unchanged, ``llm_unavailable`` re-raises.
* :func:`resolve_default_llm` is currently an alias for
  :func:`resolve_extract_llm` (single-source-of-truth contract).
* :func:`get_default_config` coerces a non-string ``model_name`` (Model
  object) to its string identifier so token-window helpers continue to
  work after Phase 2b plumbing.
* :class:`AgentConfig` exposes the new ``pydantic_ai_model`` field.

The actual ``PydanticAIAgent`` construction-site logic (prefer
``config.pydantic_ai_model`` over ``config.model_name``) is exercised
indirectly via the integration tests in ``test_pydantic_ai_agents.py``;
this file focuses on the resolver bridge.
"""

from __future__ import annotations

import asyncio

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase

from opencontractserver.llm_configs.models import LLMSettings, RegisteredLLM
from opencontractserver.llms.agents.agent_factory import _maybe_resolve_default_llm
from opencontractserver.llms.agents.core_agents import AgentConfig, get_default_config
from opencontractserver.llms.providers.registry import reset_provider_registry_cache
from opencontractserver.llms.resolution import (
    FAILURE_MODE_NOT_CONFIGURED,
    FAILURE_MODE_UNAVAILABLE,
    LLMUnavailableError,
    resolve_default_llm,
    resolve_extract_llm,
)

User = get_user_model()


OPENAI_PATH = "opencontractserver.llms.providers.openai.OpenAIProvider"


class ResolveDefaultLLMTests(TestCase):
    """``resolve_default_llm`` shares the LLMSettings.default_extract_llm
    field with ``resolve_extract_llm`` for now (Phase 2b). Verify the
    contract is identical so a future migration to a separate
    ``default_chat_llm`` field only needs to update one function.
    """

    def setUp(self) -> None:
        reset_provider_registry_cache()
        cache.delete(LLMSettings.CACHE_KEY)

    def test_alias_for_resolve_extract_llm_when_unset(self):
        # Both raise the same failure mode when no default is configured.
        with self.assertRaises(LLMUnavailableError) as ctx_default:
            resolve_default_llm()
        with self.assertRaises(LLMUnavailableError) as ctx_extract:
            resolve_extract_llm()
        self.assertEqual(
            ctx_default.exception.failure_mode,
            ctx_extract.exception.failure_mode,
        )
        self.assertEqual(
            ctx_default.exception.failure_mode, FAILURE_MODE_NOT_CONFIGURED
        )


class MaybeResolveDefaultLLMTests(TestCase):
    """The resolver-injection helper used by both UnifiedAgentFactory paths."""

    def setUp(self) -> None:
        reset_provider_registry_cache()
        cache.delete(LLMSettings.CACHE_KEY)
        self.user = User.objects.create_user(
            username="factory_creator",
            password="x",
            email="factory_creator@test.com",
        )
        self.settings = LLMSettings.get_instance(use_cache=False)

    def _run(self, model):
        return asyncio.get_event_loop().run_until_complete(
            _maybe_resolve_default_llm(model)
        )

    def _make_resolvable_default(self) -> RegisteredLLM:
        rl = RegisteredLLM.objects.create(
            provider_class_path=OPENAI_PATH,
            model_id="gpt-4o-mini",
            display_name="GPT-4o mini",
            creator=self.user,
        )
        self.settings.update_secrets(OPENAI_PATH, {"api_key": "sk-real"})
        self.settings.default_extract_llm = rl
        self.settings.save()
        cache.delete(LLMSettings.CACHE_KEY)
        return rl

    def test_caller_pinned_model_passes_through_untouched(self):
        # When the caller already specified a model (CLI / benchmark /
        # explicit-by-frontend), the helper must not touch it.
        result = self._run("openai:gpt-4o")
        self.assertEqual(result, ("openai:gpt-4o", None, None, None))

    def test_no_default_returns_inputs_unchanged(self):
        # llm_not_configured is the legacy-fallback path.
        result = self._run(None)
        self.assertEqual(result, (None, None, None, None))

    def test_resolves_when_default_configured(self):
        rl = self._make_resolvable_default()
        model_str, pydantic_ai_model, api_key, base_url = self._run(None)
        self.assertEqual(model_str, "openai:gpt-4o-mini")
        self.assertIsNotNone(pydantic_ai_model)
        # pydantic-ai exposes the model identifier as ``model_name``.
        self.assertEqual(getattr(pydantic_ai_model, "model_name", None), "gpt-4o-mini")
        self.assertEqual(api_key, "sk-real")
        self.assertIsNone(base_url)
        # Smoke: the registered row matches what we just made.
        self.assertEqual(self.settings.default_extract_llm_id, rl.pk)

    def test_unresolvable_default_propagates(self):
        # Admin set a default but it's broken (no api_key). Helper must
        # re-raise so the chat session aborts with the structured failure.
        rl = RegisteredLLM.objects.create(
            provider_class_path=OPENAI_PATH,
            model_id="gpt-4o-mini",
            display_name="Broken",
            creator=self.user,
        )
        self.settings.default_extract_llm = rl
        self.settings.save()
        cache.delete(LLMSettings.CACHE_KEY)
        with self.assertRaises(LLMUnavailableError) as ctx:
            self._run(None)
        self.assertEqual(ctx.exception.failure_mode, FAILURE_MODE_UNAVAILABLE)


class AgentConfigCoercionTests(TestCase):
    """``get_default_config`` must keep ``model_name`` as a string even
    when callers pass through pydantic-ai Model objects (legacy helpers
    like ``get_context_window_for_model`` and ``is_anthropic_model``
    require strings).
    """

    def test_pydantic_ai_model_field_exists_and_defaults_to_none(self):
        config = get_default_config()
        self.assertTrue(hasattr(config, "pydantic_ai_model"))
        self.assertIsNone(config.pydantic_ai_model)

    def test_pydantic_ai_model_field_accepts_arbitrary_objects(self):
        sentinel = object()
        config = get_default_config(pydantic_ai_model=sentinel)
        self.assertIs(config.pydantic_ai_model, sentinel)

    def test_string_model_name_passes_through_unchanged(self):
        config = get_default_config(model_name="openai:gpt-4o")
        self.assertEqual(config.model_name, "openai:gpt-4o")

    def test_non_string_model_name_coerced_to_model_name_attr(self):
        class FakeModel:
            model_name = "claude-opus-4-7"

        config = get_default_config(model_name=FakeModel())
        self.assertEqual(config.model_name, "claude-opus-4-7")

    def test_non_string_without_model_name_attr_falls_back_to_str(self):
        class WithoutAttr:
            def __str__(self) -> str:
                return "fallback-id"

        config = get_default_config(model_name=WithoutAttr())
        self.assertEqual(config.model_name, "fallback-id")


class AgentConfigPydanticAIModelFieldTests(TestCase):
    """Smoke test that the dataclass declaration itself is right."""

    def test_dataclass_field_default(self):
        config = AgentConfig()
        self.assertIsNone(config.pydantic_ai_model)

    def test_dataclass_field_set_explicitly(self):
        sentinel = object()
        config = AgentConfig(pydantic_ai_model=sentinel)
        self.assertIs(config.pydantic_ai_model, sentinel)
