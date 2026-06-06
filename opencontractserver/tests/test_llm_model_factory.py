"""LLM provider credentials: DB-singleton storage + model construction.

Covers the runtime-configurable LLM credential feature:

* Each shipped :class:`BaseLLMProvider` declares a ``Settings`` dataclass so
  its ``api_key`` (encrypted) / ``base_url`` land in the ``PipelineSettings``
  singleton and the System Settings UI — just like a parser or embedder.
* :func:`opencontractserver.llms.model_factory.build_agent_model` resolves a
  model spec **DB-wins / env-fallback**: a credentialed ``pydantic-ai`` model
  when the provider has DB creds, else the bare spec string (env credentials).

See issue: runtime LLM credential/endpoint configuration.
"""

from __future__ import annotations

from unittest import mock

from asgiref.sync import async_to_sync
from django.test import TestCase
from pydantic_ai.models import Model

from opencontractserver.documents.models import PipelineSettings
from opencontractserver.llms.model_factory import (
    abuild_agent_model,
    build_agent_model,
    invalidate_credential_cache,
)
from opencontractserver.pipeline.base.settings_schema import (
    get_secret_settings,
    get_settings_schema,
)
from opencontractserver.pipeline.llm_providers.anthropic_provider import (
    AnthropicProvider,
)
from opencontractserver.pipeline.llm_providers.google_provider import GoogleProvider
from opencontractserver.pipeline.llm_providers.ollama_provider import OllamaProvider
from opencontractserver.pipeline.llm_providers.openai_provider import OpenAIProvider
from opencontractserver.pipeline.registry import (
    get_llm_provider_by_key_cached,
    reset_registry,
)


class TestProviderSettingsSchema(TestCase):
    """Providers expose credential settings via the standard schema machinery."""

    def setUp(self):
        reset_registry()
        self.addCleanup(reset_registry)

    def test_anthropic_declares_secret_api_key_and_optional_base_url(self):
        schema = get_settings_schema(AnthropicProvider)
        self.assertEqual(schema["api_key"]["type"], "secret")
        self.assertEqual(schema["api_key"]["env_var"], "ANTHROPIC_API_KEY")
        self.assertFalse(schema["api_key"]["required"])  # env fallback allowed
        self.assertEqual(schema["base_url"]["type"], "optional")
        self.assertEqual(get_secret_settings(AnthropicProvider), ["api_key"])

    def test_openai_declares_api_key_and_base_url(self):
        schema = get_settings_schema(OpenAIProvider)
        self.assertEqual(schema["api_key"]["env_var"], "OPENAI_API_KEY")
        self.assertIn("base_url", schema)

    def test_google_declares_api_key_only(self):
        schema = get_settings_schema(GoogleProvider)
        self.assertEqual(schema["api_key"]["env_var"], "GEMINI_API_KEY")
        # AI-Studio takes no caller-supplied endpoint.
        self.assertNotIn("base_url", schema)

    def test_ollama_defaults_base_url_to_openai_compatible_endpoint(self):
        schema = get_settings_schema(OllamaProvider)
        self.assertEqual(schema["base_url"]["type"], "optional")
        self.assertEqual(schema["base_url"]["default"], "http://localhost:11434/v1")
        # api_key is optional (gateways only) — provider is requires_api_key=False.
        self.assertEqual(get_secret_settings(OllamaProvider), ["api_key"])

    def test_registry_surfaces_provider_settings_schema(self):
        """The registry definition carries the credential schema for the UI."""
        defn = get_llm_provider_by_key_cached("anthropic")
        assert defn is not None
        names = {entry["name"] for entry in defn.settings_schema}
        self.assertIn("api_key", names)
        self.assertIn("base_url", names)


class TestBuildAgentModelEnvFallback(TestCase):
    """With no DB credentials configured, build_agent_model is a no-op passthrough."""

    def setUp(self):
        reset_registry()
        self.addCleanup(reset_registry)
        PipelineSettings.clear_cache()
        self.addCleanup(PipelineSettings.clear_cache)

    def test_no_db_creds_returns_bare_spec_string(self):
        # A fresh singleton has no provider creds → env fallback (string).
        self.assertEqual(
            build_agent_model("anthropic:claude-opus-4-6"),
            "anthropic:claude-opus-4-6",
        )

    def test_colonless_spec_returned_unchanged(self):
        # A colonless spec is NOT unparseable: parse_model_spec treats a bare
        # model name as the default ("openai") provider. With no DB credentials
        # configured for openai in this test, _get_db_credentials returns {},
        # so build_agent_model returns the spec verbatim — pydantic-ai resolves
        # it from the environment as before. (This exercises the
        # no-DB-creds → bare-string path, not a ValueError.)
        self.assertEqual(build_agent_model("gpt-4o"), "gpt-4o")

    def test_malformed_spec_returned_unchanged(self):
        # Resolver never raises on a bad spec — pydantic-ai surfaces the error.
        self.assertEqual(build_agent_model(""), "")

    def test_unknown_provider_returns_string(self):
        # Provider prefix not in the registry → no creds → bare string.
        self.assertEqual(
            build_agent_model("totally-unknown:foo"), "totally-unknown:foo"
        )


class TestBuildAgentModelDbWins(TestCase):
    """DB-configured credentials are threaded into model construction."""

    def setUp(self):
        reset_registry()
        self.addCleanup(reset_registry)
        PipelineSettings.clear_cache()
        self.addCleanup(PipelineSettings.clear_cache)
        openai_defn = get_llm_provider_by_key_cached("openai")
        assert openai_defn is not None
        self.openai_path = openai_defn.class_name

    def _configure_openai_creds(self, *, api_key="sk-db-key", base_url=None):
        instance = PipelineSettings.get_instance()
        instance.set_secrets({self.openai_path: {"api_key": api_key}})
        if base_url is not None:
            instance.component_settings = {self.openai_path: {"base_url": base_url}}
        # save() auto-invalidates the PipelineSettings cache, so no explicit
        # clear_cache() is needed here.
        instance.save()

    def test_db_creds_route_through_construct_model(self):
        """When DB creds exist, _construct_model is invoked with them."""
        self._configure_openai_creds(
            api_key="sk-db-key", base_url="http://gateway.local/v1"
        )
        sentinel = object()
        with mock.patch(
            "opencontractserver.llms.model_factory._construct_model",
            return_value=sentinel,
        ) as construct:
            result = build_agent_model("openai:gpt-4o")
        self.assertIs(result, sentinel)
        construct.assert_called_once()
        _provider_key, model_name, creds = construct.call_args.args
        self.assertEqual(model_name, "gpt-4o")
        self.assertEqual(creds["api_key"], "sk-db-key")
        self.assertEqual(creds["base_url"], "http://gateway.local/v1")

    def test_construct_failure_degrades_to_env_fallback(self):
        """A construction error must never break the chat path."""
        self._configure_openai_creds(api_key="sk-db-key")
        with mock.patch(
            "opencontractserver.llms.model_factory._construct_model",
            side_effect=RuntimeError("boom"),
        ):
            result = build_agent_model("openai:gpt-4o")
        self.assertEqual(result, "openai:gpt-4o")

    def test_db_creds_build_real_pydantic_ai_model(self):
        """End-to-end: a non-string credentialed pydantic-ai model is returned."""
        self._configure_openai_creds(
            api_key="sk-db-key", base_url="http://gateway.local/v1"
        )
        result = build_agent_model("openai:gpt-4o")
        # Assert against pydantic-ai's exported abstract base class, not a
        # class-name string: robust to a future rename of OpenAIChatModel.
        # (A Model instance is necessarily not the bare spec string.)
        self.assertIsInstance(result, Model)

    def test_abuild_agent_model_async_wrapper(self):
        self._configure_openai_creds(api_key="sk-db-key")
        result = async_to_sync(abuild_agent_model)("openai:gpt-4o")
        self.assertNotIsInstance(result, str)


class TestProviderSecretStatusSurface(TestCase):
    """The GraphQL-facing schema reports api_key status without leaking it."""

    def setUp(self):
        reset_registry()
        self.addCleanup(reset_registry)
        PipelineSettings.clear_cache()
        self.addCleanup(PipelineSettings.clear_cache)
        anthropic_defn = get_llm_provider_by_key_cached("anthropic")
        assert anthropic_defn is not None
        self.anthropic_path = anthropic_defn.class_name

    def test_has_value_flips_after_setting_secret(self):
        instance = PipelineSettings.get_instance()
        schema = instance.get_component_schema(self.anthropic_path)
        self.assertFalse(schema["api_key"]["has_value"])

        instance.set_secrets({self.anthropic_path: {"api_key": "sk-secret"}})
        instance.save()

        schema = instance.get_component_schema(self.anthropic_path)
        self.assertTrue(schema["api_key"]["has_value"])
        # The value itself is never exposed.
        self.assertIsNone(schema["api_key"]["current_value"])


class TestCredentialCache(TestCase):
    """Resolved provider creds are memoized per ``PipelineSettings.modified``.

    Regression coverage for issue #1921: the per-build credential read must
    skip repeated Fernet/PBKDF2 decryption, yet a live key rotation (which
    bumps ``modified`` via ``save()``) must still take effect without a
    redeploy — preserving the live-configurability guarantee of issue #1897.
    """

    def setUp(self):
        reset_registry()
        self.addCleanup(reset_registry)
        PipelineSettings.clear_cache()
        self.addCleanup(PipelineSettings.clear_cache)
        # The memo is process-local and survives TestCase rollback; clear it
        # explicitly so the suite is isolated under the unittest runner too
        # (the conftest autouse fixture only applies under pytest).
        invalidate_credential_cache()
        self.addCleanup(invalidate_credential_cache)
        openai_defn = get_llm_provider_by_key_cached("openai")
        assert openai_defn is not None
        self.openai_path = openai_defn.class_name

    def _configure_openai_creds(self, *, api_key):
        instance = PipelineSettings.get_instance()
        instance.set_secrets({self.openai_path: {"api_key": api_key}})
        # save() bumps ``modified`` (auto_now) and clears the singleton cache.
        instance.save()

    def test_resolution_memoized_across_builds(self):
        """The second build for a provider reuses creds without re-decrypting."""
        self._configure_openai_creds(api_key="sk-db-key")
        with mock.patch.object(
            PipelineSettings,
            "get_secrets",
            autospec=True,
            side_effect=PipelineSettings.get_secrets,
        ) as get_secrets_spy:
            first = build_agent_model("openai:gpt-4o")
            second = build_agent_model("openai:gpt-4o")
        # The first build decrypts once — get_full_component_settings reads the
        # secret store twice (merged settings + secrets overlay) — and the
        # second build is served from the memo without touching the store.
        self.assertEqual(get_secrets_spy.call_count, 2)
        self.assertIsInstance(first, Model)
        self.assertIsInstance(second, Model)

    def test_rotated_key_takes_effect_without_redeploy(self):
        """A key rotation via save() busts the memo (preserves #1897)."""
        self._configure_openai_creds(api_key="sk-old")
        seen_keys: list[str | None] = []

        def _capture(provider_key, model_name, creds):
            seen_keys.append(creds.get("api_key"))
            return object()

        with mock.patch(
            "opencontractserver.llms.model_factory._construct_model",
            side_effect=_capture,
        ):
            build_agent_model("openai:gpt-4o")  # warms the memo with sk-old
            # Rotate exactly as a superuser would: System Settings → save().
            self._configure_openai_creds(api_key="sk-new")
            build_agent_model("openai:gpt-4o")

        self.assertEqual(seen_keys, ["sk-old", "sk-new"])

    def test_invalidate_credential_cache_forces_redecrypt(self):
        """The explicit purge re-decrypts on the next build (out-of-band path)."""
        self._configure_openai_creds(api_key="sk-db-key")
        with mock.patch.object(
            PipelineSettings,
            "get_secrets",
            autospec=True,
            side_effect=PipelineSettings.get_secrets,
        ) as get_secrets_spy:
            build_agent_model("openai:gpt-4o")  # 2 decrypt reads, then cached
            invalidate_credential_cache()
            build_agent_model("openai:gpt-4o")  # memo purged → 2 more reads
        self.assertEqual(get_secrets_spy.call_count, 4)
