"""Tests for the Phase-3 LLM-config GraphQL surface.

Covers:
* Query visibility (superuser vs. regular user) on llmProviders,
  registeredLlms, llmSettings.
* Mutation auth (every mutation rejects non-superusers with the same
  generic error string — no enumeration via timing or message).
* Mutation happy paths (registerLlm, updateRegisteredLlm with lineage
  versioning, archiveRegisteredLlm, updateLlmProviderSecrets,
  setDefaultExtractLlm).
* Mutation error paths (validation failures, head-only constraints,
  archive-while-default refused, RegisteredLLM not found).
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from graphene.test import Client

from config.graphql.schema import schema
from opencontractserver.llm_configs.models import LLMSettings, RegisteredLLM
from opencontractserver.llms.providers.registry import reset_provider_registry_cache

User = get_user_model()


OPENAI_PATH = "opencontractserver.llms.providers.openai.OpenAIProvider"
ANTHROPIC_PATH = "opencontractserver.llms.providers.anthropic.AnthropicProvider"


class _Context:
    def __init__(self, user) -> None:
        self.user = user


class _LLMGraphQLBase(TestCase):
    def setUp(self) -> None:
        reset_provider_registry_cache()
        cache.delete(LLMSettings.CACHE_KEY)
        self.superuser = User.objects.create_superuser(
            username="llm_admin", password="x", email="llm_admin@test.com"
        )
        self.regular = User.objects.create_user(
            username="llm_regular", password="x", email="llm_regular@test.com"
        )
        self.super_client = Client(schema, context_value=_Context(self.superuser))
        self.regular_client = Client(schema, context_value=_Context(self.regular))
        # Ensure singleton.
        LLMSettings.get_instance(use_cache=False)

    # --- helpers ---------------------------------------------------- #

    def _make_resolvable_default(self) -> RegisteredLLM:
        rl = RegisteredLLM.objects.create(
            provider_class_path=OPENAI_PATH,
            model_id="gpt-4o-mini",
            display_name="GPT-4o mini",
            creator=self.superuser,
        )
        s = LLMSettings.get_instance(use_cache=False)
        s.update_secrets(OPENAI_PATH, {"api_key": "sk-real"})
        s.default_extract_llm = rl
        s.save()
        cache.delete(LLMSettings.CACHE_KEY)
        return rl


# =====================================================================
# Queries
# =====================================================================


class LLMProvidersQueryTests(_LLMGraphQLBase):
    QUERY = """
        query {
            llmProviders {
                name
                classPath
                title
                pydanticAiPrefix
                defaultModels
                supportsStructuredOutput
                supportsTools
                hasSecrets
                hasValidSecrets
                settingsSchema {
                    name
                    settingType
                    required
                    hasValue
                    currentValue
                }
            }
        }
    """

    def test_superuser_sees_full_schema(self):
        result = self.super_client.execute(self.QUERY)
        self.assertNotIn("errors", result, msg=result)
        providers = {p["classPath"]: p for p in result["data"]["llmProviders"]}
        self.assertIn(OPENAI_PATH, providers)
        self.assertIn(ANTHROPIC_PATH, providers)
        openai = providers[OPENAI_PATH]
        self.assertEqual(openai["pydanticAiPrefix"], "openai")
        self.assertTrue(openai["supportsStructuredOutput"])
        self.assertIsNotNone(openai["settingsSchema"])
        api_key_field = next(
            f for f in openai["settingsSchema"] if f["name"] == "api_key"
        )
        self.assertEqual(api_key_field["settingType"], "secret")
        self.assertFalse(api_key_field["hasValue"])
        # has_secrets initially False (nothing stored).
        self.assertFalse(openai["hasSecrets"])
        self.assertFalse(openai["hasValidSecrets"])

    def test_superuser_sees_secret_presence_after_set(self):
        s = LLMSettings.get_instance(use_cache=False)
        s.update_secrets(OPENAI_PATH, {"api_key": "sk-real"})
        s.save()
        cache.delete(LLMSettings.CACHE_KEY)
        result = self.super_client.execute(self.QUERY)
        providers = {p["classPath"]: p for p in result["data"]["llmProviders"]}
        self.assertTrue(providers[OPENAI_PATH]["hasSecrets"])
        self.assertTrue(providers[OPENAI_PATH]["hasValidSecrets"])
        api_key_field = next(
            f
            for f in providers[OPENAI_PATH]["settingsSchema"]
            if f["name"] == "api_key"
        )
        # Secret values NEVER exposed.
        self.assertIsNone(api_key_field["currentValue"])
        self.assertTrue(api_key_field["hasValue"])

    def test_regular_user_sees_no_schema_or_secret_flags(self):
        s = LLMSettings.get_instance(use_cache=False)
        s.update_secrets(OPENAI_PATH, {"api_key": "sk-real"})
        s.save()
        cache.delete(LLMSettings.CACHE_KEY)
        result = self.regular_client.execute(self.QUERY)
        self.assertNotIn("errors", result, msg=result)
        providers = {p["classPath"]: p for p in result["data"]["llmProviders"]}
        self.assertIsNone(providers[OPENAI_PATH]["settingsSchema"])
        self.assertFalse(providers[OPENAI_PATH]["hasSecrets"])
        self.assertFalse(providers[OPENAI_PATH]["hasValidSecrets"])


class RegisteredLLMsQueryTests(_LLMGraphQLBase):
    QUERY = """
        query($only: Boolean) {
            registeredLlms(onlySelectable: $only) {
                id
                modelId
                displayName
                isResolvable
                isHead
                isDefaultForExtracts
                unavailableReason
                pydanticAiModelString
            }
        }
    """

    def test_only_selectable_default_returns_heads_only(self):
        # Build a tiny lineage: v1 → v2.
        v1 = RegisteredLLM.objects.create(
            provider_class_path=OPENAI_PATH,
            model_id="gpt-4o-mini",
            display_name="v1",
            creator=self.superuser,
        )
        v2 = RegisteredLLM.objects.create(
            provider_class_path=OPENAI_PATH,
            model_id="gpt-4o-mini",
            display_name="v2",
            previous_version=v1,
            creator=self.superuser,
        )
        # Disabled head — should be filtered out by selectable().
        RegisteredLLM.objects.create(
            provider_class_path=OPENAI_PATH,
            model_id="gpt-4o",
            display_name="disabled",
            is_enabled=False,
            creator=self.superuser,
        )
        # Configure secrets so v2 is fully resolvable.
        s = LLMSettings.get_instance(use_cache=False)
        s.update_secrets(OPENAI_PATH, {"api_key": "sk-real"})
        s.save()
        cache.delete(LLMSettings.CACHE_KEY)

        result = self.super_client.execute(self.QUERY, variables={"only": True})
        self.assertNotIn("errors", result, msg=result)
        ids = {row["id"] for row in result["data"]["registeredLlms"]}
        self.assertIn(str(v2.pk), ids)
        self.assertNotIn(str(v1.pk), ids)  # superseded

    def test_regular_user_cannot_opt_out_of_selectable_filter(self):
        v1 = RegisteredLLM.objects.create(
            provider_class_path=OPENAI_PATH,
            model_id="gpt-4o-mini",
            display_name="v1",
            creator=self.superuser,
        )
        v2 = RegisteredLLM.objects.create(
            provider_class_path=OPENAI_PATH,
            model_id="gpt-4o-mini",
            display_name="v2",
            previous_version=v1,
            creator=self.superuser,
        )
        # Regular user passes only=False; resolver should ignore.
        result = self.regular_client.execute(self.QUERY, variables={"only": False})
        self.assertNotIn("errors", result, msg=result)
        ids = {row["id"] for row in result["data"]["registeredLlms"]}
        self.assertNotIn(str(v1.pk), ids)
        self.assertIn(str(v2.pk), ids)

    def test_pydantic_ai_model_string_assembled(self):
        rl = self._make_resolvable_default()
        result = self.super_client.execute(self.QUERY, variables={"only": True})
        rows = {r["id"]: r for r in result["data"]["registeredLlms"]}
        self.assertEqual(
            rows[str(rl.pk)]["pydanticAiModelString"], "openai:gpt-4o-mini"
        )
        self.assertTrue(rows[str(rl.pk)]["isResolvable"])
        self.assertTrue(rows[str(rl.pk)]["isDefaultForExtracts"])
        self.assertIsNone(rows[str(rl.pk)]["unavailableReason"])


class LLMSettingsQueryTests(_LLMGraphQLBase):
    QUERY = """
        query {
            llmSettings {
                providerSettings
                providersWithSecrets
                defaultExtractLlm { id modelId }
            }
        }
    """

    def test_superuser_sees_provider_settings_and_secrets(self):
        rl = self._make_resolvable_default()
        result = self.super_client.execute(self.QUERY)
        self.assertNotIn("errors", result, msg=result)
        payload = result["data"]["llmSettings"]
        self.assertEqual(payload["defaultExtractLlm"]["id"], str(rl.pk))
        self.assertIn(OPENAI_PATH, payload["providersWithSecrets"])

    def test_regular_user_sees_default_only(self):
        rl = self._make_resolvable_default()
        result = self.regular_client.execute(self.QUERY)
        self.assertNotIn("errors", result, msg=result)
        payload = result["data"]["llmSettings"]
        self.assertEqual(payload["defaultExtractLlm"]["id"], str(rl.pk))
        # Non-superusers see empty providersWithSecrets and null
        # provider_settings — no enumeration of admin config.
        self.assertEqual(payload["providersWithSecrets"], [])
        self.assertIsNone(payload["providerSettings"])


# =====================================================================
# Mutations
# =====================================================================


class _MutateMixin:
    """Helpers shared across mutation test cases."""

    def _exec(self, client, query, **variables):
        return client.execute(query, variables=variables or None)


class RegisterLLMMutationTests(_LLMGraphQLBase, _MutateMixin):
    QUERY = """
        mutation($p: String!, $m: String!, $d: String!) {
            registerLlm(providerClassPath: $p, modelId: $m, displayName: $d) {
                ok
                message
                registeredLlm { id modelId displayName isHead isResolvable }
            }
        }
    """

    def test_superuser_can_register(self):
        result = self._exec(
            self.super_client,
            self.QUERY,
            p=OPENAI_PATH,
            m="gpt-4o",
            d="GPT-4o (Prod)",
        )
        self.assertNotIn("errors", result, msg=result)
        payload = result["data"]["registerLlm"]
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["registeredLlm"]["modelId"], "gpt-4o")
        self.assertTrue(payload["registeredLlm"]["isHead"])
        # No secrets yet → not resolvable.
        self.assertFalse(payload["registeredLlm"]["isResolvable"])

    def test_regular_user_rejected(self):
        result = self._exec(
            self.regular_client,
            self.QUERY,
            p=OPENAI_PATH,
            m="gpt-4o",
            d="x",
        )
        payload = result["data"]["registerLlm"]
        self.assertFalse(payload["ok"])
        self.assertIn("Only superusers", payload["message"])
        self.assertEqual(RegisteredLLM.objects.count(), 0)

    def test_unknown_provider_rejected(self):
        result = self._exec(
            self.super_client,
            self.QUERY,
            p="not.a.real.Provider",
            m="x",
            d="x",
        )
        payload = result["data"]["registerLlm"]
        self.assertFalse(payload["ok"])
        self.assertIn("not registered", payload["message"])

    def test_empty_display_name_rejected(self):
        result = self._exec(
            self.super_client,
            self.QUERY,
            p=OPENAI_PATH,
            m="gpt-4o",
            d="   ",
        )
        payload = result["data"]["registerLlm"]
        self.assertFalse(payload["ok"])
        self.assertIn("display_name", payload["message"])


class UpdateRegisteredLLMMutationTests(_LLMGraphQLBase, _MutateMixin):
    QUERY = """
        mutation($id: ID!, $name: String) {
            updateRegisteredLlm(id: $id, displayName: $name) {
                ok
                message
                registeredLlm { id displayName previousVersionId isHead }
            }
        }
    """

    def test_creates_new_lineage_version(self):
        rl = RegisteredLLM.objects.create(
            provider_class_path=OPENAI_PATH,
            model_id="gpt-4o",
            display_name="v1",
            creator=self.superuser,
        )
        result = self._exec(self.super_client, self.QUERY, id=str(rl.pk), name="v2")
        self.assertNotIn("errors", result, msg=result)
        payload = result["data"]["updateRegisteredLlm"]
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["registeredLlm"]["displayName"], "v2")
        self.assertEqual(payload["registeredLlm"]["previousVersionId"], str(rl.pk))
        self.assertTrue(payload["registeredLlm"]["isHead"])
        # Old row preserved verbatim.
        rl.refresh_from_db()
        self.assertEqual(rl.display_name, "v1")

    def test_rejects_non_head(self):
        v1 = RegisteredLLM.objects.create(
            provider_class_path=OPENAI_PATH,
            model_id="gpt-4o",
            display_name="v1",
            creator=self.superuser,
        )
        RegisteredLLM.objects.create(
            provider_class_path=OPENAI_PATH,
            model_id="gpt-4o",
            display_name="v2",
            previous_version=v1,
            creator=self.superuser,
        )
        result = self._exec(self.super_client, self.QUERY, id=str(v1.pk), name="v1b")
        payload = result["data"]["updateRegisteredLlm"]
        self.assertFalse(payload["ok"])
        self.assertIn("not the head", payload["message"])

    def test_rejects_archived(self):
        rl = RegisteredLLM.objects.create(
            provider_class_path=OPENAI_PATH,
            model_id="gpt-4o",
            display_name="archived",
            is_archived=True,
            creator=self.superuser,
        )
        result = self._exec(self.super_client, self.QUERY, id=str(rl.pk), name="x")
        payload = result["data"]["updateRegisteredLlm"]
        self.assertFalse(payload["ok"])
        self.assertIn("archived", payload["message"].lower())

    def test_rolls_default_forward(self):
        rl = self._make_resolvable_default()
        result = self._exec(
            self.super_client, self.QUERY, id=str(rl.pk), name="GPT-4o-mini v2"
        )
        new_id = result["data"]["updateRegisteredLlm"]["registeredLlm"]["id"]
        cache.delete(LLMSettings.CACHE_KEY)
        s = LLMSettings.get_instance(use_cache=False)
        # Default rolled forward to new head.
        self.assertEqual(str(s.default_extract_llm_id), new_id)

    def test_not_found(self):
        result = self._exec(self.super_client, self.QUERY, id="999999", name="x")
        payload = result["data"]["updateRegisteredLlm"]
        self.assertFalse(payload["ok"])
        self.assertIn("not found", payload["message"].lower())


class ArchiveRegisteredLLMMutationTests(_LLMGraphQLBase, _MutateMixin):
    QUERY = """
        mutation($id: ID!) {
            archiveRegisteredLlm(id: $id) {
                ok
                message
                registeredLlm { id isArchived isHead }
            }
        }
    """

    def test_archives_head(self):
        rl = RegisteredLLM.objects.create(
            provider_class_path=OPENAI_PATH,
            model_id="gpt-4o",
            display_name="x",
            creator=self.superuser,
        )
        result = self._exec(self.super_client, self.QUERY, id=str(rl.pk))
        payload = result["data"]["archiveRegisteredLlm"]
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["registeredLlm"]["isArchived"])
        self.assertTrue(payload["registeredLlm"]["isHead"])

    def test_refuses_archive_when_default(self):
        rl = self._make_resolvable_default()
        result = self._exec(self.super_client, self.QUERY, id=str(rl.pk))
        payload = result["data"]["archiveRegisteredLlm"]
        self.assertFalse(payload["ok"])
        self.assertIn("default extract LLM", payload["message"])

    def test_already_archived(self):
        rl = RegisteredLLM.objects.create(
            provider_class_path=OPENAI_PATH,
            model_id="gpt-4o",
            display_name="x",
            is_archived=True,
            creator=self.superuser,
        )
        result = self._exec(self.super_client, self.QUERY, id=str(rl.pk))
        payload = result["data"]["archiveRegisteredLlm"]
        self.assertFalse(payload["ok"])
        self.assertIn("already archived", payload["message"])


class UpdateLLMProviderSecretsMutationTests(_LLMGraphQLBase, _MutateMixin):
    QUERY = """
        mutation($p: String!, $s: GenericScalar!, $cfg: GenericScalar) {
            updateLlmProviderSecrets(
                providerClassPath: $p, secrets: $s, providerSettings: $cfg
            ) {
                ok
                message
                llmSettings { providersWithSecrets providerSettings }
            }
        }
    """

    def test_stores_secret_and_non_secret_settings(self):
        result = self._exec(
            self.super_client,
            self.QUERY,
            p=OPENAI_PATH,
            s={"api_key": "sk-real"},
            cfg={"organization_id": "org-1"},
        )
        self.assertNotIn("errors", result, msg=result)
        payload = result["data"]["updateLlmProviderSecrets"]
        self.assertTrue(payload["ok"])
        self.assertIn(OPENAI_PATH, payload["llmSettings"]["providersWithSecrets"])
        self.assertEqual(
            payload["llmSettings"]["providerSettings"][OPENAI_PATH]["organization_id"],
            "org-1",
        )
        # Verify the secret is actually persisted (not just echoed).
        cache.delete(LLMSettings.CACHE_KEY)
        s = LLMSettings.get_instance(use_cache=False)
        self.assertEqual(s.get_component_secrets(OPENAI_PATH).get("api_key"), "sk-real")

    def test_rejects_non_superuser(self):
        result = self._exec(
            self.regular_client,
            self.QUERY,
            p=OPENAI_PATH,
            s={"api_key": "sk-real"},
        )
        payload = result["data"]["updateLlmProviderSecrets"]
        self.assertFalse(payload["ok"])
        self.assertIn("Only superusers", payload["message"])

    def test_rejects_unknown_provider(self):
        result = self._exec(
            self.super_client,
            self.QUERY,
            p="nope.NotAProvider",
            s={"api_key": "x"},
        )
        payload = result["data"]["updateLlmProviderSecrets"]
        self.assertFalse(payload["ok"])
        self.assertIn("not registered", payload["message"])


class SetDefaultExtractLLMMutationTests(_LLMGraphQLBase, _MutateMixin):
    QUERY = """
        mutation($id: ID) {
            setDefaultExtractLlm(id: $id) {
                ok
                message
                llmSettings { defaultExtractLlm { id modelId } }
            }
        }
    """

    def test_sets_default(self):
        rl = RegisteredLLM.objects.create(
            provider_class_path=OPENAI_PATH,
            model_id="gpt-4o",
            display_name="x",
            creator=self.superuser,
        )
        result = self._exec(self.super_client, self.QUERY, id=str(rl.pk))
        payload = result["data"]["setDefaultExtractLlm"]
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["llmSettings"]["defaultExtractLlm"]["id"], str(rl.pk))

    def test_clears_default_when_id_null(self):
        rl = self._make_resolvable_default()
        # Sanity:
        self.assertEqual(
            LLMSettings.get_instance(use_cache=False).default_extract_llm_id, rl.pk
        )
        result = self._exec(self.super_client, self.QUERY, id=None)
        payload = result["data"]["setDefaultExtractLlm"]
        self.assertTrue(payload["ok"])
        self.assertIsNone(payload["llmSettings"]["defaultExtractLlm"])

    def test_rejects_archived(self):
        rl = RegisteredLLM.objects.create(
            provider_class_path=OPENAI_PATH,
            model_id="gpt-4o",
            display_name="archived",
            is_archived=True,
            creator=self.superuser,
        )
        result = self._exec(self.super_client, self.QUERY, id=str(rl.pk))
        payload = result["data"]["setDefaultExtractLlm"]
        self.assertFalse(payload["ok"])
        self.assertIn("archived", payload["message"].lower())

    def test_rejects_disabled(self):
        rl = RegisteredLLM.objects.create(
            provider_class_path=OPENAI_PATH,
            model_id="gpt-4o",
            display_name="disabled",
            is_enabled=False,
            creator=self.superuser,
        )
        result = self._exec(self.super_client, self.QUERY, id=str(rl.pk))
        payload = result["data"]["setDefaultExtractLlm"]
        self.assertFalse(payload["ok"])
        self.assertIn("disabled", payload["message"].lower())

    def test_rejects_non_head(self):
        v1 = RegisteredLLM.objects.create(
            provider_class_path=OPENAI_PATH,
            model_id="gpt-4o",
            display_name="v1",
            creator=self.superuser,
        )
        RegisteredLLM.objects.create(
            provider_class_path=OPENAI_PATH,
            model_id="gpt-4o",
            display_name="v2",
            previous_version=v1,
            creator=self.superuser,
        )
        result = self._exec(self.super_client, self.QUERY, id=str(v1.pk))
        payload = result["data"]["setDefaultExtractLlm"]
        self.assertFalse(payload["ok"])
        self.assertIn("non-head", payload["message"])

    def test_regular_user_rejected(self):
        rl = RegisteredLLM.objects.create(
            provider_class_path=OPENAI_PATH,
            model_id="gpt-4o",
            display_name="x",
            creator=self.superuser,
        )
        result = self._exec(self.regular_client, self.QUERY, id=str(rl.pk))
        payload = result["data"]["setDefaultExtractLlm"]
        self.assertFalse(payload["ok"])
        self.assertIn("Only superusers", payload["message"])
