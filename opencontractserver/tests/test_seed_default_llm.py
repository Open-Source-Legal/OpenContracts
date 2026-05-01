"""Tests for the ``seed_default_llm`` management command.

Covers the operator-facing contract:

* Bootstraps an OpenAI default from the env-var-backed Django setting
  (``OPENAI_API_KEY``) when the deploy is fresh.
* Idempotent — re-running on an already-configured deploy is a no-op.
* ``--force`` creates a new lineage version pointing at the prior
  default (immutable history preserved).
* Adopts an existing matching head row instead of duplicating it.
* Refuses to run when no API key is available, no superuser exists, or
  the model string is malformed — surface every misconfiguration with a
  CommandError rather than a silent half-bootstrap.
* ``--dry-run`` prints intent without writing.
"""

from __future__ import annotations

from io import StringIO

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from opencontractserver.llm_configs.models import LLMSettings, RegisteredLLM
from opencontractserver.llms.providers.registry import reset_provider_registry_cache

User = get_user_model()


OPENAI_PATH = "opencontractserver.llms.providers.openai.OpenAIProvider"
ANTHROPIC_PATH = "opencontractserver.llms.providers.anthropic.AnthropicProvider"


@override_settings(OPENAI_API_KEY="sk-from-env")
class SeedDefaultLLMTests(TestCase):
    def setUp(self) -> None:
        reset_provider_registry_cache()
        cache.delete(LLMSettings.CACHE_KEY)
        self.superuser = User.objects.create_superuser(
            username="seed_admin",
            password="x",
            email="seed_admin@test.com",
        )

    def _call(self, *args: str) -> str:
        out = StringIO()
        call_command("seed_default_llm", *args, stdout=out)
        return out.getvalue()

    # ------------------------------------------------------------------ #
    # Happy paths
    # ------------------------------------------------------------------ #

    def test_bootstraps_from_env_on_fresh_deploy(self):
        self._call()  # uses defaults: model=DEFAULT_EXTRACT_MODEL, api_key=OPENAI_API_KEY

        cache.delete(LLMSettings.CACHE_KEY)
        s = LLMSettings.get_instance(use_cache=False)
        self.assertIsNotNone(s.default_extract_llm)
        rl = s.default_extract_llm
        self.assertEqual(rl.provider_class_path, OPENAI_PATH)
        self.assertEqual(rl.model_id, "gpt-4o-mini")
        self.assertEqual(rl.creator_id, self.superuser.id)
        # Secret round-trips through the mixin.
        self.assertEqual(
            s.get_component_secrets(OPENAI_PATH).get("api_key"), "sk-from-env"
        )
        # Resolver agrees the row is now usable.
        self.assertTrue(rl.is_resolvable(llm_settings=s))

    def test_explicit_api_key_overrides_env(self):
        self._call("--api-key", "sk-explicit")
        s = LLMSettings.get_instance(use_cache=False)
        self.assertEqual(
            s.get_component_secrets(OPENAI_PATH).get("api_key"), "sk-explicit"
        )

    def test_explicit_display_name(self):
        self._call("--display-name", "GPT-4o mini (Prod)")
        s = LLMSettings.get_instance(use_cache=False)
        self.assertEqual(s.default_extract_llm.display_name, "GPT-4o mini (Prod)")

    def test_explicit_model_string_routes_to_matching_provider(self):
        # Anthropic prefix → AnthropicProvider; api_key comes from --api-key.
        self._call(
            "--model",
            "anthropic:claude-opus-4-7",
            "--api-key",
            "ant-explicit",
        )
        s = LLMSettings.get_instance(use_cache=False)
        rl = s.default_extract_llm
        self.assertEqual(rl.provider_class_path, ANTHROPIC_PATH)
        self.assertEqual(rl.model_id, "claude-opus-4-7")
        self.assertEqual(
            s.get_component_secrets(ANTHROPIC_PATH).get("api_key"), "ant-explicit"
        )

    # ------------------------------------------------------------------ #
    # Idempotency / lineage
    # ------------------------------------------------------------------ #

    def test_rerun_without_force_is_noop(self):
        self._call()
        first = LLMSettings.get_instance(use_cache=False).default_extract_llm
        first_pk = first.pk

        out = self._call()
        self.assertIn("already set", out.lower())
        self.assertEqual(RegisteredLLM.objects.count(), 1)

        cache.delete(LLMSettings.CACHE_KEY)
        s = LLMSettings.get_instance(use_cache=False)
        self.assertEqual(s.default_extract_llm.pk, first_pk)

    def test_force_creates_new_lineage_version(self):
        self._call()
        v1 = LLMSettings.get_instance(use_cache=False).default_extract_llm

        self._call("--force", "--api-key", "sk-rotated")

        cache.delete(LLMSettings.CACHE_KEY)
        s = LLMSettings.get_instance(use_cache=False)
        v2 = s.default_extract_llm
        self.assertNotEqual(v2.pk, v1.pk)
        self.assertEqual(v2.previous_version_id, v1.pk)
        # Old row preserved, but no longer the head.
        self.assertTrue(RegisteredLLM.objects.filter(pk=v1.pk).exists())
        self.assertFalse(v1.is_head())
        self.assertTrue(v2.is_head())
        # Refreshed key is what the resolver hands out.
        self.assertEqual(
            s.get_component_secrets(OPENAI_PATH).get("api_key"), "sk-rotated"
        )

    def test_adopts_existing_matching_head_instead_of_duplicating(self):
        # Pre-create a head row matching the default model.
        existing = RegisteredLLM.objects.create(
            provider_class_path=OPENAI_PATH,
            model_id="gpt-4o-mini",
            display_name="Pre-existing GPT-4o mini",
            creator=self.superuser,
        )

        self._call()

        # Should not have created a second row; should have adopted the
        # existing one as the default.
        cache.delete(LLMSettings.CACHE_KEY)
        s = LLMSettings.get_instance(use_cache=False)
        self.assertEqual(s.default_extract_llm.pk, existing.pk)
        self.assertEqual(
            RegisteredLLM.objects.filter(
                provider_class_path=OPENAI_PATH, model_id="gpt-4o-mini"
            ).count(),
            1,
        )

    # ------------------------------------------------------------------ #
    # Errors
    # ------------------------------------------------------------------ #

    @override_settings(OPENAI_API_KEY="")
    def test_errors_when_no_api_key_available(self):
        with self.assertRaises(CommandError) as ctx:
            self._call()
        self.assertIn("No API key available", str(ctx.exception))

    def test_errors_on_malformed_model_string(self):
        with self.assertRaises(CommandError):
            self._call("--model", "no-colon-here")
        with self.assertRaises(CommandError):
            self._call("--model", ":missing-prefix")
        with self.assertRaises(CommandError):
            self._call("--model", "missing-modelid:")

    def test_errors_on_unknown_prefix(self):
        with self.assertRaises(CommandError) as ctx:
            self._call("--model", "nope:does-not-exist", "--api-key", "x")
        self.assertIn("No registered provider", str(ctx.exception))

    def test_errors_when_no_superuser(self):
        # Drop the superuser so the resolver has no creator to attribute to.
        self.superuser.delete()
        with self.assertRaises(CommandError) as ctx:
            self._call()
        self.assertIn("No superuser exists", str(ctx.exception))

    def test_explicit_creator_username(self):
        regular = User.objects.create_user(
            username="nonsuper", password="x", email="ns@test.com"
        )
        # Drop the superuser so we know the explicit override is what's used.
        self.superuser.delete()
        self._call("--creator-username", "nonsuper")
        s = LLMSettings.get_instance(use_cache=False)
        self.assertEqual(s.default_extract_llm.creator_id, regular.id)

    def test_errors_on_unknown_creator_username(self):
        with self.assertRaises(CommandError) as ctx:
            self._call("--creator-username", "no-such-user")
        self.assertIn("does not match any user", str(ctx.exception))

    # ------------------------------------------------------------------ #
    # Dry run
    # ------------------------------------------------------------------ #

    def test_dry_run_writes_nothing(self):
        out = self._call("--dry-run")
        self.assertIn("[dry-run]", out)
        # No RegisteredLLM created, no LLMSettings.default_extract_llm set,
        # no secrets persisted.
        self.assertEqual(RegisteredLLM.objects.count(), 0)
        s = LLMSettings.get_instance(use_cache=False)
        self.assertIsNone(s.default_extract_llm)
        self.assertEqual(s.get_component_secrets(OPENAI_PATH), {})
