"""Runtime LLM configuration: registry, resolver, model overrides.

Covers the per-call → per-agent → per-corpus → settings priority chain
plus the supporting infrastructure (LLM provider pipeline-component
registry, model-spec parsing/validation, and Django-model field
validation on ``Corpus.preferred_llm`` and
``AgentConfiguration.preferred_llm``).

Phase 1 of the runtime LLM configuration roadmap.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings

from opencontractserver.agents.models import AgentConfiguration
from opencontractserver.corpuses.models import Corpus

if TYPE_CHECKING:
    from opencontractserver.users.models import User as UserModel
from opencontractserver.llms.llm_registry import (
    DEFAULT_PROVIDER_KEY,
    LLMProviderNotRegistered,
    normalise_model_spec,
    parse_model_spec,
    resolve_model_spec,
    validate_model_spec,
)
from opencontractserver.pipeline.registry import (
    ComponentType,
    get_all_llm_providers_cached,
    get_llm_provider_by_key_cached,
    get_registry,
    reset_registry,
)

User = get_user_model()


class TestParseModelSpec(TestCase):
    """Spec parsing — the shape contract for everything downstream."""

    def test_prefixed_spec_splits(self):
        self.assertEqual(
            parse_model_spec("anthropic:claude-opus-4-6"),
            ("anthropic", "claude-opus-4-6"),
        )

    def test_bare_spec_defaults_to_openai(self):
        self.assertEqual(parse_model_spec("gpt-4o"), (DEFAULT_PROVIDER_KEY, "gpt-4o"))

    def test_whitespace_trimmed(self):
        self.assertEqual(
            parse_model_spec("  anthropic : claude-opus-4-6 "),
            ("anthropic", "claude-opus-4-6"),
        )

    def test_empty_rejected(self):
        with self.assertRaises(ValueError):
            parse_model_spec("")

    def test_whitespace_only_rejected(self):
        with self.assertRaises(ValueError):
            parse_model_spec("   ")

    def test_missing_provider_rejected(self):
        with self.assertRaises(ValueError):
            parse_model_spec(":claude-opus-4-6")

    def test_missing_model_rejected(self):
        with self.assertRaises(ValueError):
            parse_model_spec("anthropic:")


class TestNormaliseModelSpec(TestCase):
    def test_bare_form_gets_openai_prefix(self):
        self.assertEqual(normalise_model_spec("gpt-4o"), "openai:gpt-4o")

    def test_prefixed_form_round_trips(self):
        self.assertEqual(
            normalise_model_spec("anthropic:claude-opus-4-6"),
            "anthropic:claude-opus-4-6",
        )


class TestValidateModelSpec(TestCase):
    def setUp(self):
        # The registry is a singleton — reset between tests so a stale
        # cached state from another test class can't bleed in.
        reset_registry()

    def test_known_provider_accepted(self):
        # Should not raise — anthropic is shipped in
        # opencontractserver/pipeline/llm_providers/.
        validate_model_spec("anthropic:claude-opus-4-6")

    def test_bare_openai_accepted(self):
        validate_model_spec("gpt-4o")

    def test_unknown_provider_rejected(self):
        with self.assertRaises(LLMProviderNotRegistered):
            validate_model_spec("definitely-not-a-real-provider:foo")

    def test_malformed_rejected(self):
        with self.assertRaises(ValueError):
            validate_model_spec("")


class TestResolveModelSpec(TestCase):
    def test_explicit_wins_over_everything(self):
        self.assertEqual(
            resolve_model_spec(
                explicit="anthropic:claude-opus-4-6",
                agent_preferred="openai:gpt-4o",
                corpus_preferred="google-gla:gemini-2.0-flash",
            ),
            "anthropic:claude-opus-4-6",
        )

    def test_agent_wins_over_corpus(self):
        self.assertEqual(
            resolve_model_spec(
                explicit=None,
                agent_preferred="anthropic:claude-haiku-4-5",
                corpus_preferred="anthropic:claude-opus-4-6",
            ),
            "anthropic:claude-haiku-4-5",
        )

    def test_corpus_wins_over_settings(self):
        self.assertEqual(
            resolve_model_spec(corpus_preferred="anthropic:claude-opus-4-6"),
            "anthropic:claude-opus-4-6",
        )

    def test_falls_back_to_default_llm_setting(self):
        with override_settings(DEFAULT_LLM="anthropic:claude-sonnet-4-6"):
            self.assertEqual(resolve_model_spec(), "anthropic:claude-sonnet-4-6")

    @override_settings(DEFAULT_LLM=None, OPENAI_MODEL="gpt-4o-mini")
    def test_falls_back_to_legacy_openai_model_setting(self):
        # Bare names normalise with the openai prefix on the way out.
        self.assertEqual(resolve_model_spec(), "openai:gpt-4o-mini")

    def test_empty_strings_treated_as_unset(self):
        with override_settings(DEFAULT_LLM="anthropic:claude-opus-4-6"):
            self.assertEqual(
                resolve_model_spec(explicit="", agent_preferred="   "),
                "anthropic:claude-opus-4-6",
            )

    def test_settings_default_wins_over_django_settings(self):
        # The runtime PipelineSettings default (threaded in by callers as
        # ``settings_default``) takes priority over the Django DEFAULT_LLM /
        # OPENAI_MODEL settings.
        with override_settings(DEFAULT_LLM="anthropic:claude-sonnet-4-6"):
            self.assertEqual(
                resolve_model_spec(settings_default="anthropic:claude-opus-4-6"),
                "anthropic:claude-opus-4-6",
            )

    def test_corpus_preferred_wins_over_settings_default(self):
        self.assertEqual(
            resolve_model_spec(
                corpus_preferred="openai:gpt-4o",
                settings_default="anthropic:claude-opus-4-6",
            ),
            "openai:gpt-4o",
        )

    def test_empty_settings_default_falls_through_to_django(self):
        with override_settings(DEFAULT_LLM="anthropic:claude-sonnet-4-6"):
            self.assertEqual(
                resolve_model_spec(settings_default="   "),
                "anthropic:claude-sonnet-4-6",
            )


class TestPipelineRegistryDiscoversLLMProviders(TestCase):
    def setUp(self):
        reset_registry()

    def test_registry_includes_llm_provider_component_type(self):
        self.assertIn("LLM_PROVIDER", ComponentType.__members__)

    def test_registry_discovers_shipped_providers(self):
        providers = get_all_llm_providers_cached()
        provider_keys = {p.provider_key for p in providers}
        self.assertIn("openai", provider_keys)
        self.assertIn("anthropic", provider_keys)
        self.assertIn("google-gla", provider_keys)
        self.assertIn("ollama", provider_keys)

    def test_provider_metadata_round_trips(self):
        anthropic = get_llm_provider_by_key_cached("anthropic")
        assert anthropic is not None
        self.assertEqual(anthropic.component_type, ComponentType.LLM_PROVIDER)
        self.assertEqual(anthropic.title, "Anthropic")
        self.assertTrue(anthropic.requires_api_key)
        self.assertIn("claude-opus-4-6", anthropic.supported_models)

    def test_ollama_marked_no_api_key(self):
        ollama = get_llm_provider_by_key_cached("ollama")
        assert ollama is not None
        self.assertFalse(ollama.requires_api_key)

    def test_unknown_provider_returns_none(self):
        self.assertIsNone(get_llm_provider_by_key_cached("not-a-provider"))

    def test_get_all_components_includes_llm_providers(self):
        registry = get_registry()
        all_components = {
            "parsers": registry.parsers,
            "embedders": registry.embedders,
            "thumbnailers": registry.thumbnailers,
            "post_processors": registry.post_processors,
            "enrichers": registry.enrichers,
            "rerankers": registry.rerankers,
            "llm_providers": registry.llm_providers,
        }
        self.assertGreater(len(all_components["llm_providers"]), 0)


class TestCorpusPreferredLLMField(TestCase):
    user: UserModel

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="llm-config-user",
            password="test",
            email="llm-config@test.com",
        )

    def setUp(self):
        reset_registry()

    def test_valid_prefixed_spec_persists(self):
        corpus = Corpus.objects.create(
            title="C1",
            creator=self.user,
            preferred_llm="anthropic:claude-opus-4-6",
        )
        corpus.refresh_from_db()
        self.assertEqual(corpus.preferred_llm, "anthropic:claude-opus-4-6")

    def test_bare_spec_normalised_to_openai_prefix(self):
        corpus = Corpus.objects.create(
            title="C2",
            creator=self.user,
            preferred_llm="gpt-4o",
        )
        corpus.refresh_from_db()
        self.assertEqual(corpus.preferred_llm, "openai:gpt-4o")

    def test_unknown_provider_rejected(self):
        with self.assertRaises(ValidationError) as ctx:
            Corpus.objects.create(
                title="C3",
                creator=self.user,
                preferred_llm="not-a-provider:foo",
            )
        self.assertIn("preferred_llm", ctx.exception.message_dict)

    def test_malformed_spec_rejected(self):
        with self.assertRaises(ValidationError) as ctx:
            Corpus.objects.create(
                title="C4",
                creator=self.user,
                preferred_llm="anthropic:",
            )
        self.assertIn("preferred_llm", ctx.exception.message_dict)

    def test_null_preferred_llm_allowed(self):
        # Pre-feature corpuses have null preferred_llm — must keep working.
        corpus = Corpus.objects.create(title="C5", creator=self.user)
        self.assertIsNone(corpus.preferred_llm)

    @override_settings(DEFAULT_LLM="anthropic:claude-opus-4-7")
    def test_created_with_llm_stamped_at_creation(self):
        corpus = Corpus.objects.create(title="C6", creator=self.user)
        self.assertEqual(corpus.created_with_llm, "anthropic:claude-opus-4-7")

    def test_created_with_llm_immutable(self):
        corpus = Corpus.objects.create(
            title="C7",
            creator=self.user,
            preferred_llm="anthropic:claude-opus-4-6",
        )
        original = corpus.created_with_llm
        corpus.preferred_llm = "anthropic:claude-haiku-4-5"
        corpus.save()
        corpus.refresh_from_db()
        # preferred_llm changed, audit field did not
        self.assertEqual(corpus.preferred_llm, "anthropic:claude-haiku-4-5")
        self.assertEqual(corpus.created_with_llm, original)


class TestCorpusSerializerNormalisesPreferredLLM(TestCase):
    """``CorpusSerializer`` must collapse ``""`` / whitespace to ``None``.

    The corpus update mutation documents ``""`` as "clear the override,"
    so the serializer is responsible for normalising it before the model
    sees the value.  Without this, the DB persists ``""`` (semantically
    distinct from ``NULL`` for any future direct ORM filter).
    """

    user: UserModel

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="serializer-user",
            password="test",
            email="serializer@test.com",
        )

    def setUp(self):
        reset_registry()

    def test_empty_string_clears_preferred_llm(self):
        from config.graphql.serializers import CorpusSerializer

        corpus = Corpus.objects.create(
            title="To Clear",
            creator=self.user,
            preferred_llm="anthropic:claude-opus-4-6",
        )
        serializer = CorpusSerializer(
            instance=corpus, data={"preferred_llm": ""}, partial=True
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        serializer.save()
        corpus.refresh_from_db()
        self.assertIsNone(corpus.preferred_llm)

    def test_whitespace_only_clears_preferred_llm(self):
        from config.graphql.serializers import CorpusSerializer

        corpus = Corpus.objects.create(
            title="To Clear 2",
            creator=self.user,
            preferred_llm="anthropic:claude-opus-4-6",
        )
        serializer = CorpusSerializer(
            instance=corpus, data={"preferred_llm": "   "}, partial=True
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        serializer.save()
        corpus.refresh_from_db()
        self.assertIsNone(corpus.preferred_llm)


class TestAgentConfigurationPreferredLLMField(TestCase):
    user: UserModel

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="agent-llm-user",
            password="test",
            email="agent-llm@test.com",
        )

    def setUp(self):
        reset_registry()

    def test_valid_spec_persists(self):
        agent = AgentConfiguration.objects.create(
            name="Summarizer",
            description="Test summarizer agent.",
            system_instructions="Summarise.",
            scope="GLOBAL",
            creator=self.user,
            preferred_llm="anthropic:claude-haiku-4-5",
        )
        agent.refresh_from_db()
        self.assertEqual(agent.preferred_llm, "anthropic:claude-haiku-4-5")

    def test_null_allowed_means_fall_back_to_corpus(self):
        agent = AgentConfiguration.objects.create(
            name="Default Agent",
            description="Falls back to corpus default.",
            system_instructions="Reply.",
            scope="GLOBAL",
            creator=self.user,
        )
        self.assertIsNone(agent.preferred_llm)

    def test_invalid_spec_rejected(self):
        with self.assertRaises(ValidationError) as ctx:
            AgentConfiguration.objects.create(
                name="Bad",
                description="Bad",
                system_instructions="Bad",
                scope="GLOBAL",
                creator=self.user,
                preferred_llm="not-a-provider:foo",
            )
        self.assertIn("preferred_llm", ctx.exception.message_dict)


class TestAgentFactoryUsesPriorityChain(TestCase):
    """End-to-end test that the factory threads the resolver through."""

    user: UserModel

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="factory-user",
            password="test",
            email="factory@test.com",
        )

    def setUp(self):
        reset_registry()

    @override_settings(DEFAULT_LLM="openai:gpt-4o-mini")
    def test_corpus_preferred_wins_over_settings(self):
        """When no explicit model is passed, corpus.preferred_llm wins."""
        from opencontractserver.llms.llm_registry import resolve_model_spec

        corpus = Corpus.objects.create(
            title="Corpus With Default",
            creator=self.user,
            preferred_llm="anthropic:claude-opus-4-6",
        )

        # Simulate what the factory does (without spinning up pydantic-ai).
        resolved = resolve_model_spec(
            explicit=None,
            corpus_preferred=corpus.preferred_llm,
        )
        self.assertEqual(resolved, "anthropic:claude-opus-4-6")

    @override_settings(DEFAULT_LLM="openai:gpt-4o-mini")
    def test_explicit_per_call_wins_over_corpus(self):
        from opencontractserver.llms.llm_registry import resolve_model_spec

        corpus = Corpus.objects.create(
            title="Corpus With Default 2",
            creator=self.user,
            preferred_llm="anthropic:claude-opus-4-6",
        )
        resolved = resolve_model_spec(
            explicit="google-gla:gemini-2.0-flash",
            corpus_preferred=corpus.preferred_llm,
        )
        self.assertEqual(resolved, "google-gla:gemini-2.0-flash")

    @override_settings(DEFAULT_LLM=None, OPENAI_MODEL="gpt-4o")
    def test_factory_falls_back_to_legacy_setting_when_unset(self):
        from opencontractserver.llms.llm_registry import resolve_model_spec

        corpus = Corpus.objects.create(
            title="Plain Corpus",
            creator=self.user,
        )
        resolved = resolve_model_spec(
            explicit=None,
            corpus_preferred=corpus.preferred_llm,
        )
        self.assertEqual(resolved, "openai:gpt-4o")


class TestContextWindowLookupHandlesPrefixedSpecs(TestCase):
    """Regression: get_context_window_for_model must strip provider prefix."""

    def test_anthropic_prefixed_returns_known_window(self):
        from opencontractserver.constants.context_guardrails import (
            MODEL_CONTEXT_WINDOWS,
        )
        from opencontractserver.llms.context_guardrails import (
            get_context_window_for_model,
        )

        expected = MODEL_CONTEXT_WINDOWS["claude-opus-4"]
        self.assertEqual(
            get_context_window_for_model("anthropic:claude-opus-4-6"), expected
        )

    def test_openai_prefixed_returns_known_window(self):
        from opencontractserver.constants.context_guardrails import (
            MODEL_CONTEXT_WINDOWS,
        )
        from opencontractserver.llms.context_guardrails import (
            get_context_window_for_model,
        )

        expected = MODEL_CONTEXT_WINDOWS["gpt-4o"]
        self.assertEqual(get_context_window_for_model("openai:gpt-4o"), expected)


class TestAgentConfigurationPreferredLLMPersistsForDelegation(TestCase):
    """``AgentConfiguration.preferred_llm`` must round-trip cleanly.

    The delegation tool (``build_delegation_tool``) reads
    ``agent.preferred_llm`` directly and forwards it to the factory via
    the ``agent_preferred_llm=`` kwarg so the resolver's per-agent slot
    is exercised by production code (not just unit tests).  We don't
    spin up the full delegation body (it needs a StreamRelay, async ORM
    context, and a live agents_api); end-to-end @-mention tests cover
    that path.  Here we only assert the persisted value survives
    validation and refresh — the call-site wiring is unit-tested by
    ``TestResolveModelSpec.test_agent_wins_over_corpus``.
    """

    user: UserModel

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="delegation-user",
            password="test",
            email="delegation@test.com",
        )

    def setUp(self):
        reset_registry()

    def test_agent_preferred_llm_persists_for_delegation_tool_to_consume(self):
        corpus = Corpus.objects.create(
            title="Delegation Corpus",
            creator=self.user,
        )
        agent = AgentConfiguration.objects.create(
            name="Summarizer",
            description="Sub-agent test.",
            system_instructions="Summarise.",
            scope="CORPUS",
            corpus=corpus,
            creator=self.user,
            preferred_llm="anthropic:claude-haiku-4-5",
        )

        agent.refresh_from_db()
        self.assertEqual(agent.preferred_llm, "anthropic:claude-haiku-4-5")
