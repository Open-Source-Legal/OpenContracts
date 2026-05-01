"""Phase-2a tests: provider registry + resolver.

Covers:
* :class:`LLMProviderRegistry` auto-discovery picks up the OpenAI and
  Anthropic providers shipped in :mod:`opencontractserver.llms.providers`,
  exposes them by class path, and skips the abstract base.
* :func:`is_resolvable` and :func:`unavailable_reason` correctly classify
  every failure mode (disabled, archived, unknown provider, missing
  secrets) and the happy path.
* :func:`resolve` materialises a :class:`ResolvedLLM` with the right
  pydantic-ai model string, decrypted api_key, and capability flags.
* :func:`resolve_extract_llm` walks ``LLMSettings.default_extract_llm``
  and raises :class:`LLMUnavailableError` on no-default deploys (so the
  caller can fall back to ``DEFAULT_EXTRACT_MODEL``).
* ``RegisteredLLM.is_resolvable()`` and ``unavailable_reason()`` delegate
  to the resolver — important to keep the contract single-sourced.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase

from opencontractserver.llm_configs.models import LLMSettings, RegisteredLLM
from opencontractserver.llms.providers.anthropic import AnthropicProvider
from opencontractserver.llms.providers.base import BaseLLMProvider
from opencontractserver.llms.providers.openai import OpenAIProvider
from opencontractserver.llms.providers.registry import (
    get_provider_registry,
    reset_provider_registry_cache,
)
from opencontractserver.llms.resolution import (
    FAILURE_MODE_NOT_CONFIGURED,
    FAILURE_MODE_UNAVAILABLE,
    LLMUnavailableError,
    ResolvedLLM,
    is_resolvable,
    resolve,
    resolve_extract_llm,
    unavailable_reason,
)

User = get_user_model()


OPENAI_PATH = "opencontractserver.llms.providers.openai.OpenAIProvider"
ANTHROPIC_PATH = "opencontractserver.llms.providers.anthropic.AnthropicProvider"


class ProviderRegistryTests(TestCase):
    def setUp(self) -> None:
        reset_provider_registry_cache()

    def test_discovers_shipped_providers(self):
        reg = get_provider_registry()
        self.assertIs(reg.get(OPENAI_PATH), OpenAIProvider)
        self.assertIs(reg.get(ANTHROPIC_PATH), AnthropicProvider)

    def test_skips_abstract_base(self):
        reg = get_provider_registry()
        self.assertNotIn(
            "opencontractserver.llms.providers.base.BaseLLMProvider",
            reg.class_paths(),
        )
        # Sanity: BaseLLMProvider is not in the discovered set.
        self.assertNotIn(BaseLLMProvider, reg.all())

    def test_lookup_returns_none_for_unknown(self):
        reg = get_provider_registry()
        self.assertIsNone(reg.get("nonexistent.module.NotAProvider"))

    def test_class_path_helper_matches_module_class(self):
        self.assertEqual(OpenAIProvider.class_path(), OPENAI_PATH)
        self.assertEqual(AnthropicProvider.class_path(), ANTHROPIC_PATH)

    def test_pydantic_ai_prefix_present(self):
        # Resolver builds "<prefix>:<model_id>" — empty prefix would
        # silently produce ":gpt-4o" which pydantic-ai would mishandle.
        for cls in (OpenAIProvider, AnthropicProvider):
            self.assertTrue(cls.pydantic_ai_prefix, msg=f"{cls} missing prefix")


class _ResolverFixtureMixin:
    """Shared fixture builder for resolver tests."""

    def setUp(self) -> None:  # type: ignore[override]
        reset_provider_registry_cache()
        cache.delete(LLMSettings.CACHE_KEY)
        self.user = User.objects.create_user(
            username="resolver_creator",
            password="x",
            email="resolver_creator@test.com",
        )
        self.settings = LLMSettings.get_instance(use_cache=False)

    def _make_rl(self, **overrides) -> RegisteredLLM:
        kwargs = dict(
            provider_class_path=OPENAI_PATH,
            model_id="gpt-4o-mini",
            display_name="GPT-4o mini",
            creator=self.user,
        )
        kwargs.update(overrides)
        return RegisteredLLM.objects.create(**kwargs)

    def _set_api_key(self, provider_path: str, value: str) -> None:
        self.settings.update_secrets(provider_path, {"api_key": value})
        self.settings.save()


class IsResolvableTests(_ResolverFixtureMixin, TestCase):
    def test_happy_path(self):
        rl = self._make_rl()
        self._set_api_key(OPENAI_PATH, "sk-real")
        self.assertTrue(is_resolvable(rl, llm_settings=self.settings))
        self.assertIsNone(unavailable_reason(rl, llm_settings=self.settings))

    def test_disabled_short_circuits(self):
        rl = self._make_rl(is_enabled=False)
        self._set_api_key(OPENAI_PATH, "sk-real")
        self.assertFalse(is_resolvable(rl, llm_settings=self.settings))
        self.assertEqual(
            unavailable_reason(rl, llm_settings=self.settings),
            "Disabled by an administrator.",
        )

    def test_archived_short_circuits(self):
        rl = self._make_rl(is_archived=True)
        self._set_api_key(OPENAI_PATH, "sk-real")
        self.assertFalse(is_resolvable(rl, llm_settings=self.settings))
        reason = unavailable_reason(rl, llm_settings=self.settings) or ""
        self.assertIn("Archived", reason)

    def test_unknown_provider_class_path(self):
        rl = self._make_rl(provider_class_path="nope.NotAProvider")
        # Even with secrets set under that key, the provider must be in code.
        self._set_api_key("nope.NotAProvider", "sk-real")
        self.assertFalse(is_resolvable(rl, llm_settings=self.settings))
        reason = unavailable_reason(rl, llm_settings=self.settings) or ""
        self.assertIn("not registered", reason)

    def test_missing_api_key(self):
        rl = self._make_rl()
        # No secrets set.
        self.assertFalse(is_resolvable(rl, llm_settings=self.settings))
        reason = unavailable_reason(rl, llm_settings=self.settings) or ""
        self.assertIn("No API key", reason)

    def test_whitespace_only_api_key_treated_as_missing(self):
        rl = self._make_rl()
        self._set_api_key(OPENAI_PATH, "   ")
        self.assertFalse(is_resolvable(rl, llm_settings=self.settings))


class ResolveTests(_ResolverFixtureMixin, TestCase):
    def test_resolve_returns_pydantic_ai_string(self):
        rl = self._make_rl(model_id="gpt-4o")
        self._set_api_key(OPENAI_PATH, "sk-real")
        resolved = resolve(rl)
        self.assertIsInstance(resolved, ResolvedLLM)
        self.assertEqual(resolved.pydantic_ai_model_string, "openai:gpt-4o")
        self.assertEqual(resolved.api_key, "sk-real")
        self.assertEqual(resolved.provider_class_path, OPENAI_PATH)
        self.assertEqual(resolved.registered_llm_id, rl.pk)

    def test_resolve_carries_capabilities_and_overrides(self):
        rl = self._make_rl(
            context_window=64_000,
            supports_structured_output=False,
            supports_tools=False,
            max_output_tokens=4096,
            temperature_default=0.1,
        )
        self._set_api_key(OPENAI_PATH, "sk-real")
        resolved = resolve(rl)
        self.assertEqual(resolved.context_window, 64_000)
        self.assertFalse(resolved.supports_structured_output)
        self.assertFalse(resolved.supports_tools)
        self.assertEqual(resolved.max_output_tokens, 4096)
        self.assertEqual(resolved.temperature_default, 0.1)

    def test_resolve_carries_optional_provider_kwargs(self):
        rl = self._make_rl()
        # Plaintext non-secret settings flow through alongside the api_key.
        self.settings.provider_settings = {
            OPENAI_PATH: {
                "base_url": "https://example.com/v1",
                "organization_id": "org-123",
            }
        }
        self.settings.save()
        self._set_api_key(OPENAI_PATH, "sk-real")
        resolved = resolve(rl)
        self.assertEqual(resolved.base_url, "https://example.com/v1")
        self.assertEqual(resolved.organization_id, "org-123")

    def test_resolve_raises_when_unresolvable(self):
        rl = self._make_rl()  # no secrets
        with self.assertRaises(LLMUnavailableError) as ctx:
            resolve(rl)
        self.assertEqual(ctx.exception.failure_mode, FAILURE_MODE_UNAVAILABLE)
        self.assertIn(rl.display_name, str(ctx.exception))

    def test_to_pydantic_ai_model_for_openai(self):
        """OpenAIProvider builds a pydantic-ai OpenAIChatModel with the
        admin-configured api_key baked in (so pydantic-ai uses *that*
        key, not whatever is in OPENAI_API_KEY in the worker's env)."""
        from pydantic_ai.models.openai import OpenAIChatModel

        rl = self._make_rl(model_id="gpt-4o")
        self._set_api_key(OPENAI_PATH, "sk-real")
        resolved = resolve(rl)
        m = resolved.to_pydantic_ai_model()
        self.assertIsInstance(m, OpenAIChatModel)
        # pydantic-ai exposes the model identifier as ``model_name``.
        self.assertEqual(getattr(m, "model_name", None), "gpt-4o")

    def test_to_pydantic_ai_model_for_anthropic(self):
        from pydantic_ai.models.anthropic import AnthropicModel

        rl = self._make_rl(
            provider_class_path=ANTHROPIC_PATH,
            model_id="claude-opus-4-7",
        )
        self._set_api_key(ANTHROPIC_PATH, "ant-real")
        resolved = resolve(rl)
        m = resolved.to_pydantic_ai_model()
        self.assertIsInstance(m, AnthropicModel)
        self.assertEqual(getattr(m, "model_name", None), "claude-opus-4-7")

    def test_to_pydantic_ai_model_raises_when_provider_deregistered(self):
        # Build a ResolvedLLM directly (bypassing resolve()) pointing at
        # an unknown provider. This exercises the defensive branch in
        # to_pydantic_ai_model() that handles "provider was registered
        # at resolution time but de-registered before call time".
        resolved = ResolvedLLM(
            registered_llm_id=999,
            provider_class_path="nope.NotAProvider",
            provider_title="Nope",
            pydantic_ai_model_string="nope:nope",
            api_key="x",
            base_url=None,
            organization_id=None,
            context_window=None,
            supports_structured_output=True,
            supports_tools=True,
            max_output_tokens=None,
            temperature_default=None,
        )
        with self.assertRaises(LLMUnavailableError) as ctx:
            resolved.to_pydantic_ai_model()
        self.assertEqual(ctx.exception.failure_mode, FAILURE_MODE_UNAVAILABLE)


class ResolveExtractLLMTests(_ResolverFixtureMixin, TestCase):
    def test_raises_when_no_default_set(self):
        # Fresh deploy: empty singleton, no default. Failure mode must be
        # ``llm_not_configured`` so callers (data_extract_tasks) know to
        # fall back to legacy DEFAULT_EXTRACT_MODEL rather than failing.
        with self.assertRaises(LLMUnavailableError) as ctx:
            resolve_extract_llm()
        self.assertEqual(ctx.exception.failure_mode, FAILURE_MODE_NOT_CONFIGURED)

    def test_resolves_default_when_configured(self):
        rl = self._make_rl()
        self._set_api_key(OPENAI_PATH, "sk-real")
        self.settings.default_extract_llm = rl
        self.settings.save()
        # Bust the cache so resolve_extract_llm sees the saved default.
        cache.delete(LLMSettings.CACHE_KEY)

        resolved = resolve_extract_llm()
        self.assertEqual(resolved.registered_llm_id, rl.pk)
        self.assertEqual(resolved.pydantic_ai_model_string, "openai:gpt-4o-mini")

    def test_raises_when_default_unresolvable(self):
        # Admin set a default but it's currently broken (no api_key).
        # Failure mode must be ``llm_unavailable`` (not
        # ``llm_not_configured``) so callers fail loudly rather than
        # silently substituting another model.
        rl = self._make_rl()  # no secrets configured
        self.settings.default_extract_llm = rl
        self.settings.save()
        cache.delete(LLMSettings.CACHE_KEY)
        with self.assertRaises(LLMUnavailableError) as ctx:
            resolve_extract_llm()
        self.assertEqual(ctx.exception.failure_mode, FAILURE_MODE_UNAVAILABLE)


class RegisteredLLMResolverDelegationTests(_ResolverFixtureMixin, TestCase):
    """``RegisteredLLM.is_resolvable()`` / ``unavailable_reason()`` must
    delegate to the resolver so the contract is single-sourced."""

    def test_model_method_matches_resolver(self):
        rl = self._make_rl()
        self._set_api_key(OPENAI_PATH, "sk-real")
        self.assertEqual(rl.is_resolvable(), is_resolvable(rl))
        self.assertIsNone(rl.unavailable_reason())

    def test_model_method_reports_missing_secret(self):
        rl = self._make_rl()
        self.assertFalse(rl.is_resolvable())
        self.assertIn("No API key", rl.unavailable_reason() or "")
