"""Phase-1 tests for the llm_configs app.

Covers:
* ``LLMSettings`` singleton invariants (pk=1 enforced, deletion forbidden,
  ``get_instance`` cached + idempotent).
* ``EncryptedSecretsMixin`` round-trip via the ``LLMSettings`` instance —
  exercises the mixin extracted from PipelineSettings against a second
  host model so we know the abstraction holds.
* ``RegisteredLLM`` immutable version-chain: ``heads()`` and
  ``selectable()`` manager filters; ``is_resolvable()`` lifecycle gate;
  ``previous_version`` PROTECT semantics.
"""

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from opencontractserver.llm_configs.models import LLMSettings, RegisteredLLM

User = get_user_model()


class LLMSettingsSingletonTests(TestCase):
    def setUp(self):
        cache.delete(LLMSettings.CACHE_KEY)
        self.user = User.objects.create_user(
            username="llmcfg_user", password="x", email="llmcfg_user@test.com"
        )

    def test_get_instance_returns_singleton(self):
        first = LLMSettings.get_instance(use_cache=False)
        second = LLMSettings.get_instance(use_cache=False)
        self.assertEqual(first.pk, 1)
        self.assertEqual(second.pk, 1)
        self.assertEqual(LLMSettings.objects.count(), 1)

    def test_cannot_create_second_instance(self):
        LLMSettings.get_instance(use_cache=False)
        with self.assertRaises(ValidationError):
            LLMSettings(provider_settings={}).save()

    def test_cannot_delete_singleton(self):
        instance = LLMSettings.get_instance(use_cache=False)
        with self.assertRaises(ValidationError):
            instance.delete()

    def test_save_invalidates_cache(self):
        instance = LLMSettings.get_instance(use_cache=False)
        cache.set(LLMSettings.CACHE_KEY, "stale-sentinel", 300)
        instance.modified_by = self.user
        instance.save()
        self.assertIsNone(cache.get(LLMSettings.CACHE_KEY))


class LLMSettingsSecretsTests(TestCase):
    """Round-trip the EncryptedSecretsMixin against LLMSettings.

    PipelineSettings already has full coverage of the mixin behaviour;
    these tests assert the abstraction reused on a second host model
    behaves identically.
    """

    def setUp(self):
        cache.delete(LLMSettings.CACHE_KEY)
        self.instance = LLMSettings.get_instance(use_cache=False)

    def test_set_get_round_trip(self):
        secrets = {
            "providers.openai.OpenAIProvider": {"api_key": "sk-xxxx"},
            "providers.anthropic.AnthropicProvider": {"api_key": "ant-yyy"},
        }
        self.instance.set_secrets(secrets)
        self.instance.save()
        reloaded = LLMSettings.get_instance(use_cache=False)
        self.assertEqual(reloaded.get_secrets(), secrets)

    def test_update_secrets_merges_namespace(self):
        self.instance.set_secrets(
            {"providers.openai.OpenAIProvider": {"api_key": "sk-xxxx"}}
        )
        self.instance.update_secrets(
            "providers.openai.OpenAIProvider", {"organization_id": "org-1"}
        )
        bucket = self.instance.get_component_secrets("providers.openai.OpenAIProvider")
        self.assertEqual(bucket["api_key"], "sk-xxxx")
        self.assertEqual(bucket["organization_id"], "org-1")

    def test_delete_component_secrets_removes_bucket(self):
        self.instance.set_secrets(
            {
                "providers.openai.OpenAIProvider": {"api_key": "sk-xxxx"},
                "providers.anthropic.AnthropicProvider": {"api_key": "ant-yyy"},
            }
        )
        self.instance.delete_component_secrets("providers.openai.OpenAIProvider")
        remaining = self.instance.get_secrets()
        self.assertNotIn("providers.openai.OpenAIProvider", remaining)
        self.assertIn("providers.anthropic.AnthropicProvider", remaining)

    def test_has_valid_secrets_requires_non_empty_api_key(self):
        provider = "providers.openai.OpenAIProvider"
        self.assertFalse(self.instance.has_valid_secrets(provider))
        self.instance.update_secrets(provider, {"api_key": "   "})
        self.assertFalse(self.instance.has_valid_secrets(provider))
        self.instance.update_secrets(provider, {"api_key": "sk-real"})
        self.assertTrue(self.instance.has_valid_secrets(provider))

    def test_get_full_provider_settings_merges_secret_over_plaintext(self):
        provider = "providers.openai.OpenAIProvider"
        self.instance.provider_settings = {
            provider: {"base_url": "https://api.example.com", "api_key": "PLACEHOLDER"}
        }
        self.instance.update_secrets(provider, {"api_key": "sk-real"})
        merged = self.instance.get_full_provider_settings(provider)
        self.assertEqual(merged["base_url"], "https://api.example.com")
        self.assertEqual(merged["api_key"], "sk-real")  # secret wins on collision


class RegisteredLLMVersionChainTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="llmcfg_creator",
            password="x",
            email="llmcfg_creator@test.com",
        )

    def _make(self, **overrides) -> RegisteredLLM:
        kwargs = dict(
            provider_class_path="providers.openai.OpenAIProvider",
            model_id="gpt-4o-mini",
            display_name="GPT-4o mini",
            creator=self.user,
        )
        kwargs.update(overrides)
        return RegisteredLLM.objects.create(**kwargs)

    def test_heads_returns_only_terminal_rows(self):
        v1 = self._make(display_name="v1")
        v2 = self._make(display_name="v2", previous_version=v1)
        v3 = self._make(display_name="v3", previous_version=v2)

        heads = list(RegisteredLLM.objects.heads())
        head_ids = {row.pk for row in heads}
        self.assertEqual(head_ids, {v3.pk})
        self.assertEqual(v3.is_head(), True)
        self.assertEqual(v2.is_head(), False)
        self.assertEqual(v1.is_head(), False)

    def test_selectable_excludes_disabled_and_archived(self):
        head_ok = self._make(display_name="head-ok")
        head_disabled = self._make(display_name="head-disabled", is_enabled=False)
        head_archived = self._make(display_name="head-archived", is_archived=True)

        selectable_ids = {row.pk for row in RegisteredLLM.objects.selectable()}
        self.assertEqual(selectable_ids, {head_ok.pk})
        self.assertFalse(head_disabled.is_resolvable())
        self.assertFalse(head_archived.is_resolvable())
        self.assertTrue(head_ok.is_resolvable())

    def test_previous_version_protect_blocks_deletion_of_referenced_row(self):
        v1 = self._make(display_name="v1")
        self._make(display_name="v2", previous_version=v1)
        with self.assertRaises(Exception):
            with transaction.atomic():
                v1.delete()

    def test_default_extract_llm_protect(self):
        cache.delete(LLMSettings.CACHE_KEY)
        rl = self._make(display_name="default-candidate")
        s = LLMSettings.get_instance(use_cache=False)
        s.default_extract_llm = rl
        s.save()
        with self.assertRaises(Exception):
            with transaction.atomic():
                rl.delete()

    def test_singleton_check_constraint_at_db_level(self):
        cache.delete(LLMSettings.CACHE_KEY)
        LLMSettings.get_instance(use_cache=False)
        # Bypass the model-level guard to confirm the DB constraint also rejects pk!=1.
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                LLMSettings.objects.create(id=2)
