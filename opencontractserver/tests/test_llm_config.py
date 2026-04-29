"""Tests for the LLM configuration system.

Covers:
* ``LLMConfigSettings`` singleton + Fernet-encrypted credentials.
* ``LLMModel`` validation against the provider registry.
* ``config_service.resolve_model_for_column`` fallback chain & failure modes.
* GraphQL queries/mutations: superuser gating, secret invisibility,
  ``availableLlmModels`` filtering, default-model setter.
* Column FK round-trip.
"""

from __future__ import annotations

import json

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.test import TestCase
from graphene.test import Client

from config.graphql.schema import schema
from opencontractserver.extracts.models import Column, Fieldset
from opencontractserver.llms.config_service import (
    LLMNotConfiguredError,
    LLMUnavailableError,
    applied_environment,
    list_available_models,
    resolve_model_for_column,
)
from opencontractserver.llms.models import LLMConfigSettings, LLMModel

User = get_user_model()


class _Ctx:
    """Lightweight stand-in for ``info.context`` in graphene tests."""

    def __init__(self, user):
        self.user = user
        self.headers = {}
        self.META = {"REMOTE_ADDR": "127.0.0.1"}


def _reset_cache():
    cache.delete(LLMConfigSettings.CACHE_KEY)


class LLMConfigSettingsTests(TestCase):
    def setUp(self):
        _reset_cache()
        self.user = User.objects.create_superuser(
            username="llm_admin", password="x", email="llm@test.com"
        )

    def test_singleton_get_instance_creates_row(self):
        instance = LLMConfigSettings.get_instance()
        self.assertEqual(instance.pk, 1)
        # Calling again returns the same row (cached).
        self.assertIs(LLMConfigSettings.get_instance(), instance)

    def test_singleton_cannot_be_deleted(self):
        instance = LLMConfigSettings.get_instance()
        with self.assertRaises(ValidationError):
            instance.delete()

    def test_secret_round_trip(self):
        instance = LLMConfigSettings.get_instance(use_cache=False)
        instance.update_provider_secrets("openai", {"api_key": "sk-secret-1"})
        instance.save()

        # Reload from DB; bytes aren't readable as plaintext.
        reloaded = LLMConfigSettings.objects.get(pk=1)
        self.assertNotIn(b"sk-secret-1", bytes(reloaded.encrypted_secrets or b""))
        self.assertEqual(
            reloaded.get_provider_secrets("openai"), {"api_key": "sk-secret-1"}
        )

    def test_is_provider_configured_requires_required_fields(self):
        instance = LLMConfigSettings.get_instance(use_cache=False)
        # OpenAI requires api_key (declared in OpenAIProvider.credential_schema).
        self.assertFalse(instance.is_provider_configured("openai"))

        instance.update_provider_secrets("openai", {"api_key": "sk-x"})
        instance.save()

        # Re-read after save (cache invalidated).
        instance2 = LLMConfigSettings.get_instance(use_cache=False)
        self.assertTrue(instance2.is_provider_configured("openai"))

    def test_unknown_provider_is_never_configured(self):
        instance = LLMConfigSettings.get_instance(use_cache=False)
        self.assertFalse(instance.is_provider_configured("nonsense"))

    def test_full_provider_credentials_merges_config_and_secrets(self):
        instance = LLMConfigSettings.get_instance(use_cache=False)
        instance.update_provider_config("openai", {"organization": "org-123"})
        instance.update_provider_secrets("openai", {"api_key": "sk-x"})
        instance.save()

        merged = LLMConfigSettings.get_instance(use_cache=False).get_full_provider_credentials(
            "openai"
        )
        self.assertEqual(merged, {"organization": "org-123", "api_key": "sk-x"})


class LLMModelValidationTests(TestCase):
    def setUp(self):
        _reset_cache()

    def test_invalid_provider_key_rejected(self):
        with self.assertRaises(ValidationError):
            LLMModel(
                provider_key="not-a-real-provider",
                model_name="x",
                display_name="X",
            ).full_clean(exclude=["created_by"])

    def test_pydantic_ai_string_uses_provider_prefix(self):
        model = LLMModel.objects.create(
            provider_key="anthropic",
            model_name="claude-sonnet-4-6",
            display_name="Claude Sonnet 4.6",
        )
        self.assertEqual(model.pydantic_ai_string(), "anthropic:claude-sonnet-4-6")

    def test_unique_per_provider(self):
        LLMModel.objects.create(
            provider_key="openai", model_name="gpt-4o-mini", display_name="A"
        )
        with self.assertRaises(Exception):
            LLMModel.objects.create(
                provider_key="openai", model_name="gpt-4o-mini", display_name="B"
            )


class ConfigServiceTests(TestCase):
    """Cover the resolve_model_for_column fallback chain."""

    def setUp(self):
        _reset_cache()
        self.user = User.objects.create_user(username="cs_user", password="x")
        self.fieldset = Fieldset.objects.create(
            name="fs", description="d", creator=self.user
        )
        self.column = Column.objects.create(
            name="col",
            fieldset=self.fieldset,
            query="What is X?",
            output_type="str",
            creator=self.user,
        )

    def _configure_openai(self):
        instance = LLMConfigSettings.get_instance(use_cache=False)
        instance.update_provider_secrets("openai", {"api_key": "sk-test"})
        instance.save()

    def test_no_default_no_preference_raises_not_configured(self):
        with self.assertRaises(LLMNotConfiguredError):
            resolve_model_for_column(self.column)

    def test_default_used_when_column_has_no_preference(self):
        self._configure_openai()
        model = LLMModel.objects.create(
            provider_key="openai",
            model_name="gpt-4o-mini",
            display_name="GPT-4o mini",
            default_temperature=0.4,
        )
        settings = LLMConfigSettings.get_instance(use_cache=False)
        settings.default_model = model
        settings.save()

        resolved = resolve_model_for_column(self.column)
        self.assertEqual(resolved.pydantic_ai_model_string, "openai:gpt-4o-mini")
        self.assertAlmostEqual(resolved.default_temperature, 0.4)
        self.assertEqual(resolved.environment_overrides["OPENAI_API_KEY"], "sk-test")

    def test_column_preference_overrides_default(self):
        self._configure_openai()
        cheap = LLMModel.objects.create(
            provider_key="openai", model_name="gpt-4o-mini", display_name="cheap"
        )
        big = LLMModel.objects.create(
            provider_key="openai", model_name="gpt-4o", display_name="big"
        )
        settings = LLMConfigSettings.get_instance(use_cache=False)
        settings.default_model = cheap
        settings.save()

        self.column.preferred_llm_model = big
        self.column.save()

        resolved = resolve_model_for_column(self.column)
        self.assertEqual(resolved.pydantic_ai_model_string, "openai:gpt-4o")

    def test_unavailable_model_raises_with_descriptive_message(self):
        # Provider not configured → model.is_available() == False.
        model = LLMModel.objects.create(
            provider_key="openai", model_name="gpt-4o-mini", display_name="GPT-4o mini"
        )
        self.column.preferred_llm_model = model
        self.column.save()

        with self.assertRaises(LLMUnavailableError) as ctx:
            resolve_model_for_column(self.column)
        msg = str(ctx.exception)
        self.assertIn("does not have credentials configured", msg)

    def test_disabled_model_is_unavailable(self):
        self._configure_openai()
        model = LLMModel.objects.create(
            provider_key="openai",
            model_name="gpt-4o-mini",
            display_name="x",
            is_enabled=False,
        )
        self.column.preferred_llm_model = model
        self.column.save()
        with self.assertRaises(LLMUnavailableError):
            resolve_model_for_column(self.column)

    def test_list_available_models_filters(self):
        self._configure_openai()
        live = LLMModel.objects.create(
            provider_key="openai",
            model_name="gpt-4o-mini",
            display_name="Live",
        )
        LLMModel.objects.create(
            provider_key="openai",
            model_name="gpt-4o",
            display_name="Disabled",
            is_enabled=False,
        )
        LLMModel.objects.create(
            provider_key="anthropic",
            model_name="claude-sonnet-4-6",
            display_name="Unconfigured",
        )

        available = list_available_models()
        self.assertEqual([m.id for m in available], [live.id])

    def test_applied_environment_restores_previous_values(self):
        import os

        os.environ.pop("OPENAI_API_KEY", None)
        with applied_environment({"OPENAI_API_KEY": "sk-test"}):
            self.assertEqual(os.environ["OPENAI_API_KEY"], "sk-test")
        self.assertNotIn("OPENAI_API_KEY", os.environ)

        os.environ["OPENAI_API_KEY"] = "sk-orig"
        try:
            with applied_environment({"OPENAI_API_KEY": "sk-test"}):
                self.assertEqual(os.environ["OPENAI_API_KEY"], "sk-test")
            self.assertEqual(os.environ["OPENAI_API_KEY"], "sk-orig")
        finally:
            os.environ.pop("OPENAI_API_KEY", None)


class LLMConfigGraphQLTests(TestCase):
    def setUp(self):
        _reset_cache()
        self.client = Client(schema)
        self.admin = User.objects.create_superuser(
            username="g_admin", password="x", email="g_admin@x"
        )
        self.user = User.objects.create_user(username="g_user", password="x")

    def _exec(self, query, *, user, variables=None):
        return self.client.execute(
            query, variables=variables or {}, context_value=_Ctx(user)
        )

    def test_llm_providers_query_returns_registry(self):
        result = self._exec(
            "{ llmProviders { key title isConfigured } }", user=self.user
        )
        keys = [p["key"] for p in result["data"]["llmProviders"]]
        self.assertIn("openai", keys)
        self.assertIn("anthropic", keys)
        # Nothing configured yet.
        self.assertTrue(
            all(not p["isConfigured"] for p in result["data"]["llmProviders"])
        )

    def test_llm_config_settings_requires_superuser(self):
        result = self._exec("{ llmConfigSettings { modified } }", user=self.user)
        self.assertIsNotNone(result.get("errors"))

    def test_update_credentials_requires_superuser(self):
        mutation = """
            mutation($k: String!, $c: GenericScalar!) {
              updateLlmProviderCredentials(providerKey: $k, credentials: $c) {
                ok message
              }
            }
        """
        result = self._exec(
            mutation,
            user=self.user,
            variables={"k": "openai", "c": {"api_key": "sk-x"}},
        )
        ok = result["data"]["updateLlmProviderCredentials"]["ok"]
        self.assertFalse(ok)

    def test_update_credentials_rejects_unknown_field(self):
        mutation = """
            mutation($k: String!, $c: GenericScalar!) {
              updateLlmProviderCredentials(providerKey: $k, credentials: $c) {
                ok message
              }
            }
        """
        result = self._exec(
            mutation,
            user=self.admin,
            variables={"k": "openai", "c": {"hax_field": "bad"}},
        )
        payload = result["data"]["updateLlmProviderCredentials"]
        self.assertFalse(payload["ok"])
        self.assertIn("hax_field", payload["message"])

    def test_update_credentials_persists_and_marks_configured(self):
        mutation = """
            mutation($k: String!, $c: GenericScalar!) {
              updateLlmProviderCredentials(providerKey: $k, credentials: $c) {
                ok
              }
            }
        """
        self._exec(
            mutation,
            user=self.admin,
            variables={"k": "openai", "c": {"api_key": "sk-test"}},
        )

        # Re-query providers as a regular user — provider should now be configured.
        _reset_cache()
        result = self._exec(
            "{ llmProviders { key isConfigured } }", user=self.user
        )
        openai = next(
            p for p in result["data"]["llmProviders"] if p["key"] == "openai"
        )
        self.assertTrue(openai["isConfigured"])

        # Settings query never returns secret values, even to superuser.
        settings = self._exec(
            "{ llmConfigSettings { providerConfigs { providerKey isConfigured "
            "config secretFieldsSet } } }",
            user=self.admin,
        )
        entries = settings["data"]["llmConfigSettings"]["providerConfigs"]
        openai_entry = next(e for e in entries if e["providerKey"] == "openai")
        # Non-secret config is empty (we only set api_key).
        self.assertFalse(openai_entry["config"])
        # Secret field IS reported as set, but the value is not exposed.
        self.assertIn("api_key", openai_entry["secretFieldsSet"])
        # Confirm the raw GraphQL response never includes the literal value.
        self.assertNotIn("sk-test", json.dumps(settings))

    def test_create_and_set_default_llm_model(self):
        # Configure provider so the default's is_available will be True.
        self._exec(
            """
            mutation { updateLlmProviderCredentials(
              providerKey: "openai",
              credentials: {api_key: "sk-x"}
            ) { ok } }
            """,
            user=self.admin,
        )

        create = self._exec(
            """
            mutation {
              createLlmModel(
                providerKey: "openai",
                modelName: "gpt-4o-mini",
                displayName: "GPT-4o mini"
              ) { ok llmModel { id } }
            }
            """,
            user=self.admin,
        )
        model_id = create["data"]["createLlmModel"]["llmModel"]["id"]

        set_default = self._exec(
            """
            mutation($id: ID) {
              setDefaultLlmModel(id: $id) { ok }
            }
            """,
            user=self.admin,
            variables={"id": model_id},
        )
        self.assertTrue(set_default["data"]["setDefaultLlmModel"]["ok"])

        # availableLlmModels — visible to regular users.
        avail = self._exec(
            "{ availableLlmModels { id displayName isAvailable } }",
            user=self.user,
        )
        rows = avail["data"]["availableLlmModels"]
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["isAvailable"])


class ColumnPreferredLLMModelTests(TestCase):
    """End-to-end: column FK persists and GraphQL exposes it."""

    def setUp(self):
        _reset_cache()
        self.user = User.objects.create_user(username="col_user", password="x")
        self.fieldset = Fieldset.objects.create(
            name="fs", description="d", creator=self.user
        )
        self.model = LLMModel.objects.create(
            provider_key="openai", model_name="gpt-4o-mini", display_name="cheap"
        )

    def test_set_null_on_model_delete(self):
        column = Column.objects.create(
            name="c",
            fieldset=self.fieldset,
            query="?",
            output_type="str",
            preferred_llm_model=self.model,
            creator=self.user,
        )
        self.model.delete()
        column.refresh_from_db()
        self.assertIsNone(column.preferred_llm_model)
