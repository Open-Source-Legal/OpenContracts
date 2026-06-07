"""
Tests for the PipelineSettings singleton model and GraphQL endpoints.
"""

from dataclasses import dataclass, field
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase, override_settings
from graphene.test import Client

from config.graphql.schema import schema
from opencontractserver.documents.models import PipelineSettings

User = get_user_model()


class TestContext:
    """Mock context for GraphQL tests."""

    def __init__(self, user):
        self.user = user


class PipelineSettingsModelTestCase(TestCase):
    """Tests for the PipelineSettings model."""

    def setUp(self):
        from django.core.cache import cache

        # Clear cache to ensure clean state between tests
        cache.delete(PipelineSettings.CACHE_KEY)

        self.superuser = User.objects.create_superuser(
            username="ps_model_admin", password="admin", email="ps_model_admin@test.com"
        )
        self.regular_user = User.objects.create_user(
            username="ps_model_regular", password="regular"
        )

    def test_get_instance_creates_singleton(self):
        """Test that get_instance creates a singleton if it doesn't exist."""
        # Ensure no instance exists
        PipelineSettings.objects.all().delete()

        instance = PipelineSettings.get_instance()
        self.assertIsNotNone(instance)
        self.assertEqual(instance.pk, 1)

        # Getting instance again should return the same object
        instance2 = PipelineSettings.get_instance()
        self.assertEqual(instance.pk, instance2.pk)

    def test_cannot_create_second_instance(self):
        """Test that creating a second instance raises an error.

        The singleton is enforced at both application level (ValidationError
        in save()) and database level (CheckConstraint requiring pk=1).
        Depending on the pk assigned, either error may fire first.
        Uses a savepoint so IntegrityError doesn't abort the test transaction.
        """
        from django.db import transaction

        # Create the first instance
        PipelineSettings.get_instance()

        # Attempting to create a second instance should fail
        with self.assertRaises((ValidationError, IntegrityError)):
            with transaction.atomic():
                PipelineSettings.objects.create(
                    preferred_parsers={"test": "test"},
                )

    def test_cannot_delete_singleton(self):
        """Test that deleting the singleton raises ValidationError."""
        instance = PipelineSettings.get_instance()

        with self.assertRaises(ValidationError):
            instance.delete()

    @override_settings(
        PREFERRED_PARSERS={"application/pdf": "test.parser.TestParser"},
        PREFERRED_EMBEDDERS={"application/pdf": "test.embedder.TestEmbedder"},
        PARSER_KWARGS={"test.parser.TestParser": {"option1": True}},
        DEFAULT_EMBEDDER="test.embedder.DefaultEmbedder",
    )
    def test_get_preferred_parser_uses_db(self):
        """Test that get_preferred_parser returns DB values (populated from Django settings on creation)."""
        # Delete existing instance and create new one to pick up test settings.
        # Must invalidate cache because queryset.delete() bypasses model.delete()
        # and doesn't clear the cached singleton (populated during setUp by
        # personal corpus creation).
        PipelineSettings.objects.all().delete()
        PipelineSettings.clear_cache()
        instance = PipelineSettings.get_instance()

        # Initial DB values populated from Django settings via get_instance()
        self.assertEqual(
            instance.get_preferred_parser("application/pdf"),
            "test.parser.TestParser",
        )

        # Override with a new database value
        instance.preferred_parsers = {
            "application/pdf": "db.parser.DBParser",
        }
        instance.save()

        # Should use the updated database value
        self.assertEqual(
            instance.get_preferred_parser("application/pdf"),
            "db.parser.DBParser",
        )

        # Unlisted MIME type returns None
        self.assertIsNone(instance.get_preferred_parser("text/plain"))

    @override_settings(
        DEFAULT_EMBEDDER="test.embedder.DefaultEmbedder",
    )
    def test_get_default_embedder_uses_db(self):
        """Test that get_default_embedder returns DB values (populated from Django settings on creation)."""
        # Delete existing instance to test creation with settings.
        # Must invalidate cache because queryset.delete() bypasses model.delete()
        # and doesn't clear the cached singleton (populated during setUp by
        # personal corpus creation).
        PipelineSettings.objects.all().delete()
        PipelineSettings.clear_cache()
        instance = PipelineSettings.get_instance()

        # Initial DB value populated from Django settings via get_instance()
        self.assertEqual(
            instance.get_default_embedder(),
            "test.embedder.DefaultEmbedder",
        )

        # Override with a new database value
        instance.default_embedder = "db.embedder.NewDefault"
        instance.save()

        # Should use the updated database value
        self.assertEqual(instance.get_default_embedder(), "db.embedder.NewDefault")

    @override_settings(DEFAULT_LLM="")
    def test_get_default_llm_uses_db(self):
        """get_default_llm returns the stored DB value (empty by default)."""
        PipelineSettings.objects.all().delete()
        PipelineSettings.clear_cache()
        instance = PipelineSettings.get_instance()

        # Empty by default (no DEFAULT_LLM configured in the test settings).
        self.assertEqual(instance.get_default_llm(), "")

        # Override with a new database value
        instance.default_llm = "anthropic:claude-opus-4-6"
        instance.save()

        self.assertEqual(instance.get_default_llm(), "anthropic:claude-opus-4-6")

    def test_get_parser_kwargs_uses_db(self):
        """Test that get_parser_kwargs returns DB values."""
        PipelineSettings.objects.all().delete()
        instance = PipelineSettings.get_instance()

        # Set a value in the database
        instance.parser_kwargs = {
            "my.parser.TestParser": {"force_ocr": True, "timeout": 60},
        }
        instance.save()

        # Should use the database value
        kwargs = instance.get_parser_kwargs("my.parser.TestParser")
        self.assertEqual(kwargs["force_ocr"], True)
        self.assertEqual(kwargs["timeout"], 60)

    def test_get_parser_kwargs_merges_encrypted_secrets(self):
        """get_parser_kwargs overlays encrypted_secrets on top of plaintext kwargs.

        Regression test for issue #1515: a parser whose api_key lives only in
        encrypted_secrets must still receive the decrypted value at runtime.
        """
        PipelineSettings.objects.all().delete()
        instance = PipelineSettings.get_instance()

        parser_path = "my.parser.TestParser"
        instance.parser_kwargs = {
            parser_path: {"force_ocr": True, "timeout": 60},
        }
        instance.set_secrets({parser_path: {"api_key": "sk-real-key"}})
        instance.save()

        kwargs = instance.get_parser_kwargs(parser_path)
        self.assertEqual(kwargs["force_ocr"], True)
        self.assertEqual(kwargs["timeout"], 60)
        self.assertEqual(kwargs["api_key"], "sk-real-key")

    def test_get_parser_kwargs_secret_overrides_plaintext_placeholder(self):
        """Decrypted secret wins over an empty placeholder in parser_kwargs.

        Operators may leave ``api_key=""`` in parser_kwargs as a schema
        marker; the real key in encrypted_secrets must take precedence.
        """
        PipelineSettings.objects.all().delete()
        instance = PipelineSettings.get_instance()

        parser_path = "my.parser.TestParser"
        instance.parser_kwargs = {parser_path: {"api_key": "", "verbose": True}}
        instance.set_secrets({parser_path: {"api_key": "sk-real-key"}})
        instance.save()

        kwargs = instance.get_parser_kwargs(parser_path)
        self.assertEqual(kwargs["api_key"], "sk-real-key")
        self.assertEqual(kwargs["verbose"], True)

    def test_get_parser_kwargs_returns_secret_only_dict(self):
        """When parser_kwargs has no entry for the parser but secrets do,
        the secret-only dict is returned (regression for #1515)."""
        PipelineSettings.objects.all().delete()
        instance = PipelineSettings.get_instance()

        parser_path = "my.parser.TestParser"
        # Note: no parser_kwargs entry for parser_path at all
        instance.set_secrets({parser_path: {"api_key": "sk-real-key"}})
        instance.save()

        kwargs = instance.get_parser_kwargs(parser_path)
        self.assertEqual(kwargs, {"api_key": "sk-real-key"})

    def test_get_parser_kwargs_does_not_mutate_stored_dict(self):
        """Merging secrets must not leak decrypted values into self.parser_kwargs.

        Memory hygiene: a long-lived PipelineSettings reference should not
        retain decrypted secrets in the plaintext kwargs JSON field.
        """
        PipelineSettings.objects.all().delete()
        instance = PipelineSettings.get_instance()

        parser_path = "my.parser.TestParser"
        instance.parser_kwargs = {parser_path: {"verbose": True}}
        instance.set_secrets({parser_path: {"api_key": "sk-real-key"}})
        instance.save()

        instance.get_parser_kwargs(parser_path)
        self.assertNotIn("api_key", instance.parser_kwargs[parser_path])

    def test_get_parser_kwargs_no_data_returns_empty_dict(self):
        """No parser_kwargs and no secrets returns {}."""
        PipelineSettings.objects.all().delete()
        instance = PipelineSettings.get_instance()
        self.assertEqual(instance.get_parser_kwargs("anything"), {})

    def test_get_component_settings_merges_encrypted_secrets(self):
        """get_component_settings overlays encrypted_secrets on plaintext settings.

        Symmetric with get_parser_kwargs: the model-level component_settings
        getter must not silently drop secrets so that direct callers (and the
        ``get_full_component_settings`` wrapper) deliver decrypted values to
        consumers.
        """
        PipelineSettings.objects.all().delete()
        instance = PipelineSettings.get_instance()

        comp_path = "my.embedder.TestEmbedder"
        instance.component_settings = {
            comp_path: {"timeout": 30, "api_key": ""},
        }
        instance.set_secrets({comp_path: {"api_key": "sk-real-component-key"}})
        instance.save()

        merged = instance.get_component_settings(comp_path)
        # Plaintext kept, secret wins over empty placeholder
        self.assertEqual(merged["timeout"], 30)
        self.assertEqual(merged["api_key"], "sk-real-component-key")
        # Stored plaintext dict must not be mutated by the merge
        self.assertEqual(instance.component_settings[comp_path]["api_key"], "")

    def test_get_parser_kwargs_log_redaction_hides_secret(self):
        """The merged dict, after redact_sensitive_kwargs, must not leak the key.

        Defense-in-depth: even though doc_tasks logs the resolved kwargs,
        redact_sensitive_kwargs should mask any secret-looking field.
        """
        from opencontractserver.utils.logging import redact_sensitive_kwargs

        PipelineSettings.objects.all().delete()
        instance = PipelineSettings.get_instance()

        parser_path = "my.parser.TestParser"
        secret = "sk-very-real-and-distinctive-key-1515"
        instance.set_secrets({parser_path: {"api_key": secret}})
        instance.save()

        merged = instance.get_parser_kwargs(parser_path)
        redacted = redact_sensitive_kwargs(merged)
        self.assertEqual(redacted["api_key"], "***")
        self.assertNotIn(secret, repr(redacted))

    def test_get_preferred_thumbnailer(self):
        """Test that get_preferred_thumbnailer returns DB values."""
        PipelineSettings.objects.all().delete()
        instance = PipelineSettings.get_instance()

        # Initially should return None (no thumbnailer defaults)
        self.assertIsNone(instance.get_preferred_thumbnailer("application/pdf"))

        # Set a value in the database
        instance.preferred_thumbnailers = {
            "application/pdf": "my.thumbnailer.PdfThumb",
        }
        instance.save()

        # Now should use the database value
        self.assertEqual(
            instance.get_preferred_thumbnailer("application/pdf"),
            "my.thumbnailer.PdfThumb",
        )

    def test_get_preferred_enrichers(self):
        """get_preferred_enrichers returns the configured ordered chain."""
        PipelineSettings.objects.all().delete()
        instance = PipelineSettings.get_instance()

        # Default: no enrichers configured -> empty list.
        self.assertEqual(instance.get_preferred_enrichers("application/pdf"), [])

        # Configure an ordered enricher chain for PDFs.
        instance.preferred_enrichers = {
            "application/pdf": [
                "my.enrichers.First",
                "my.enrichers.Second",
            ],
        }
        instance.save()

        self.assertEqual(
            instance.get_preferred_enrichers("application/pdf"),
            ["my.enrichers.First", "my.enrichers.Second"],
        )
        # Unconfigured MIME types still return an empty list.
        self.assertEqual(instance.get_preferred_enrichers("text/plain"), [])

    def test_get_preferred_enrichers_ignores_misconfigured_non_list(self):
        """A non-list value (e.g. a bare string) is ignored, not iterated."""
        PipelineSettings.objects.all().delete()
        instance = PipelineSettings.get_instance()

        # An operator typo: a string instead of a list of class paths.
        instance.preferred_enrichers = {"application/pdf": "my.enrichers.First"}
        instance.save()

        # The string must NOT be returned (it would iterate as characters).
        self.assertEqual(instance.get_preferred_enrichers("application/pdf"), [])

    def test_modified_by_tracks_user(self):
        """Test that modified_by is updated when a user modifies settings."""
        instance = PipelineSettings.get_instance()

        instance.modified_by = self.superuser
        instance.preferred_parsers = {"test/mime": "test.parser.Parser"}
        instance.save()

        instance.refresh_from_db()
        self.assertEqual(instance.modified_by, self.superuser)


class TestEnabledComponents(TestCase):
    """Tests for the enabled_components field and helper methods."""

    def setUp(self):
        from django.core.cache import cache

        cache.delete(PipelineSettings.CACHE_KEY)

    def test_empty_list_means_all_enabled(self):
        """Empty enabled_components should treat all components as enabled."""
        instance = PipelineSettings.get_instance()
        instance.enabled_components = []
        instance.save()
        self.assertTrue(instance.is_component_enabled("any.component.path"))

    def test_non_empty_list_filters(self):
        """Non-empty list should only allow listed components."""
        instance = PipelineSettings.get_instance()
        instance.enabled_components = ["comp.A", "comp.B"]
        instance.save()
        self.assertTrue(instance.is_component_enabled("comp.A"))
        self.assertTrue(instance.is_component_enabled("comp.B"))
        self.assertFalse(instance.is_component_enabled("comp.C"))

    def test_get_enabled_components_returns_list(self):
        """get_enabled_components should return the stored list."""
        instance = PipelineSettings.get_instance()
        instance.enabled_components = ["comp.X"]
        instance.save()
        self.assertEqual(instance.get_enabled_components(), ["comp.X"])

    def test_null_enabled_components_treated_as_empty(self):
        """None/null in memory should behave same as empty list.

        The DB column has a NOT NULL constraint, so None cannot be persisted.
        However, the helper methods should still handle None gracefully at the
        Python level (e.g. if the field default hasn't been applied yet).
        """
        instance = PipelineSettings.get_instance()
        instance.enabled_components = None  # set in memory only
        self.assertTrue(instance.is_component_enabled("any.path"))
        self.assertEqual(instance.get_enabled_components(), [])


class PipelineSettingsGraphQLTestCase(TestCase):
    """Tests for the PipelineSettings GraphQL endpoints."""

    def setUp(self):
        from django.core.cache import cache

        # Clear cache to ensure clean state between tests
        cache.delete(PipelineSettings.CACHE_KEY)

        self.superuser = User.objects.create_superuser(
            username="ps_test_admin", password="admin", email="ps_test_admin@test.com"
        )
        self.regular_user = User.objects.create_user(
            username="ps_test_regular", password="regular"
        )
        self.superuser_client = Client(
            schema, context_value=TestContext(self.superuser)
        )
        self.regular_client = Client(
            schema, context_value=TestContext(self.regular_user)
        )

        # Ensure the singleton exists
        PipelineSettings.get_instance()

    def test_query_pipeline_settings_as_regular_user(self):
        """Test that regular users can read pipeline settings."""
        query = """
            query {
                pipelineSettings {
                    preferredParsers
                    preferredEmbedders
                    preferredThumbnailers
                    parserKwargs
                    componentSettings
                    defaultEmbedder
                    modified
                }
            }
        """

        result = self.regular_client.execute(query)
        self.assertIsNone(result.get("errors"))
        self.assertIsNotNone(result["data"]["pipelineSettings"])

    def test_update_pipeline_settings_as_superuser(self):
        """Test that superusers can update pipeline settings."""
        mutation = """
            mutation UpdatePipelineSettings(
                $preferredParsers: GenericScalar
            ) {
                updatePipelineSettings(
                    preferredParsers: $preferredParsers
                ) {
                    ok
                    message
                    pipelineSettings {
                        preferredParsers
                    }
                }
            }
        """

        # Use a real parser that exists in the registry
        from opencontractserver.pipeline.registry import get_registry

        registry = get_registry()
        if registry.parsers:
            parser = registry.parsers[0]
            variables = {
                "preferredParsers": {
                    "application/pdf": parser.class_name,
                }
            }

            result = self.superuser_client.execute(mutation, variables=variables)
            self.assertIsNone(result.get("errors"))
            self.assertTrue(result["data"]["updatePipelineSettings"]["ok"])
            self.assertEqual(
                result["data"]["updatePipelineSettings"]["pipelineSettings"][
                    "preferredParsers"
                ]["application/pdf"],
                parser.class_name,
            )

    def test_update_pipeline_settings_as_regular_user_fails(self):
        """Test that regular users cannot update pipeline settings."""
        mutation = """
            mutation UpdatePipelineSettings(
                $preferredParsers: GenericScalar
            ) {
                updatePipelineSettings(
                    preferredParsers: $preferredParsers
                ) {
                    ok
                    message
                }
            }
        """

        variables = {
            "preferredParsers": {
                "application/pdf": "some.parser.TestParser",
            }
        }

        result = self.regular_client.execute(mutation, variables=variables)
        self.assertIsNone(result.get("errors"))
        self.assertFalse(result["data"]["updatePipelineSettings"]["ok"])
        self.assertIn(
            "superuser",
            result["data"]["updatePipelineSettings"]["message"].lower(),
        )

    def test_update_with_invalid_parser_fails(self):
        """Test that updating with an invalid parser class path fails."""
        mutation = """
            mutation UpdatePipelineSettings(
                $preferredParsers: GenericScalar
            ) {
                updatePipelineSettings(
                    preferredParsers: $preferredParsers
                ) {
                    ok
                    message
                }
            }
        """

        variables = {
            "preferredParsers": {
                "application/pdf": "nonexistent.parser.FakeParser",
            }
        }

        result = self.superuser_client.execute(mutation, variables=variables)
        self.assertIsNone(result.get("errors"))
        self.assertFalse(result["data"]["updatePipelineSettings"]["ok"])
        self.assertIn(
            "not found",
            result["data"]["updatePipelineSettings"]["message"].lower(),
        )

    def test_reset_pipeline_settings_as_superuser(self):
        """Test that superusers can reset pipeline settings to defaults."""
        mutation = """
            mutation {
                resetPipelineSettings {
                    ok
                    message
                    pipelineSettings {
                        preferredParsers
                    }
                }
            }
        """

        result = self.superuser_client.execute(mutation)
        self.assertIsNone(result.get("errors"))
        self.assertTrue(result["data"]["resetPipelineSettings"]["ok"])

    def test_reset_pipeline_settings_as_regular_user_fails(self):
        """Test that regular users cannot reset pipeline settings."""
        mutation = """
            mutation {
                resetPipelineSettings {
                    ok
                    message
                }
            }
        """

        result = self.regular_client.execute(mutation)
        self.assertIsNone(result.get("errors"))
        self.assertFalse(result["data"]["resetPipelineSettings"]["ok"])
        self.assertIn(
            "superuser",
            result["data"]["resetPipelineSettings"]["message"].lower(),
        )

    def test_update_parser_kwargs(self):
        """Test updating parser kwargs via GraphQL."""
        mutation = """
            mutation UpdatePipelineSettings(
                $parserKwargs: GenericScalar
            ) {
                updatePipelineSettings(
                    parserKwargs: $parserKwargs
                ) {
                    ok
                    message
                    pipelineSettings {
                        parserKwargs
                    }
                }
            }
        """

        variables = {
            "parserKwargs": {
                "some.parser.TestParser": {
                    "force_ocr": True,
                    "timeout": 120,
                }
            }
        }

        result = self.superuser_client.execute(mutation, variables=variables)
        self.assertIsNone(result.get("errors"))
        self.assertTrue(result["data"]["updatePipelineSettings"]["ok"])

        returned_kwargs = result["data"]["updatePipelineSettings"]["pipelineSettings"][
            "parserKwargs"
        ]
        self.assertEqual(returned_kwargs["some.parser.TestParser"]["force_ocr"], True)
        self.assertEqual(returned_kwargs["some.parser.TestParser"]["timeout"], 120)

    def test_update_default_embedder(self):
        """Test updating default embedder via GraphQL."""
        # Use a real embedder that exists in the registry
        from opencontractserver.pipeline.registry import get_registry

        registry = get_registry()
        if registry.embedders:
            embedder = registry.embedders[0]

            mutation = """
                mutation UpdatePipelineSettings(
                    $defaultEmbedder: String
                ) {
                    updatePipelineSettings(
                        defaultEmbedder: $defaultEmbedder
                    ) {
                        ok
                        message
                        pipelineSettings {
                            defaultEmbedder
                        }
                    }
                }
            """

            variables = {"defaultEmbedder": embedder.class_name}

            result = self.superuser_client.execute(mutation, variables=variables)
            self.assertIsNone(result.get("errors"))
            self.assertTrue(result["data"]["updatePipelineSettings"]["ok"])
            self.assertEqual(
                result["data"]["updatePipelineSettings"]["pipelineSettings"][
                    "defaultEmbedder"
                ],
                embedder.class_name,
            )

    def test_update_default_llm(self):
        """Setting the default LLM via GraphQL persists the normalised spec."""
        mutation = """
            mutation UpdatePipelineSettings($defaultLlm: String) {
                updatePipelineSettings(defaultLlm: $defaultLlm) {
                    ok
                    message
                    pipelineSettings {
                        defaultLlm
                    }
                }
            }
        """
        variables = {"defaultLlm": "anthropic:claude-opus-4-6"}
        result = self.superuser_client.execute(mutation, variables=variables)
        self.assertIsNone(result.get("errors"))
        self.assertTrue(
            result["data"]["updatePipelineSettings"]["ok"],
            msg=result["data"]["updatePipelineSettings"]["message"],
        )
        self.assertEqual(
            result["data"]["updatePipelineSettings"]["pipelineSettings"]["defaultLlm"],
            "anthropic:claude-opus-4-6",
        )
        # Persisted to the singleton.
        PipelineSettings.clear_cache()
        self.assertEqual(
            PipelineSettings.get_instance().get_default_llm(),
            "anthropic:claude-opus-4-6",
        )

    def test_update_default_llm_normalises_bare_spec(self):
        """A bare model name is stored with the default (openai) provider prefix."""
        mutation = """
            mutation UpdatePipelineSettings($defaultLlm: String) {
                updatePipelineSettings(defaultLlm: $defaultLlm) {
                    ok
                    pipelineSettings { defaultLlm }
                }
            }
        """
        result = self.superuser_client.execute(
            mutation, variables={"defaultLlm": "gpt-4o"}
        )
        self.assertIsNone(result.get("errors"))
        self.assertTrue(result["data"]["updatePipelineSettings"]["ok"])
        # "openai" is the documented default provider that normalise_model_spec
        # prepends to a bare model name (not coincidental) — see
        # opencontractserver.llms.llm_registry.normalise_model_spec.
        self.assertEqual(
            result["data"]["updatePipelineSettings"]["pipelineSettings"]["defaultLlm"],
            "openai:gpt-4o",
        )

    def test_update_default_llm_unknown_provider_fails(self):
        """An unregistered provider prefix is rejected with a clear message."""
        mutation = """
            mutation UpdatePipelineSettings($defaultLlm: String) {
                updatePipelineSettings(defaultLlm: $defaultLlm) {
                    ok
                    message
                    pipelineSettings { defaultLlm }
                }
            }
        """
        result = self.superuser_client.execute(
            mutation, variables={"defaultLlm": "bogus-provider:some-model"}
        )
        self.assertIsNone(result.get("errors"))
        self.assertFalse(result["data"]["updatePipelineSettings"]["ok"])
        self.assertIn(
            "not registered",
            result["data"]["updatePipelineSettings"]["message"].lower(),
        )

    def test_update_default_llm_clear_with_empty_string(self):
        """Empty string clears the override (falls back to the settings default)."""
        instance = PipelineSettings.get_instance()
        instance.default_llm = "anthropic:claude-opus-4-6"
        instance.save()
        PipelineSettings.clear_cache()

        mutation = """
            mutation UpdatePipelineSettings($defaultLlm: String) {
                updatePipelineSettings(defaultLlm: $defaultLlm) {
                    ok
                    pipelineSettings { defaultLlm }
                }
            }
        """
        result = self.superuser_client.execute(mutation, variables={"defaultLlm": ""})
        self.assertIsNone(result.get("errors"))
        self.assertTrue(result["data"]["updatePipelineSettings"]["ok"])
        self.assertEqual(
            result["data"]["updatePipelineSettings"]["pipelineSettings"]["defaultLlm"],
            "",
        )
        PipelineSettings.clear_cache()
        self.assertEqual(PipelineSettings.get_instance().get_default_llm(), "")

    def test_update_default_llm_as_regular_user_fails(self):
        """Non-superusers cannot change the default LLM."""
        mutation = """
            mutation UpdatePipelineSettings($defaultLlm: String) {
                updatePipelineSettings(defaultLlm: $defaultLlm) {
                    ok
                    message
                }
            }
        """
        result = self.regular_client.execute(
            mutation, variables={"defaultLlm": "anthropic:claude-opus-4-6"}
        )
        self.assertFalse(result["data"]["updatePipelineSettings"]["ok"])
        self.assertIn(
            "superuser",
            result["data"]["updatePipelineSettings"]["message"].lower(),
        )

    @override_settings(DEFAULT_LLM="")
    def test_reset_pipeline_settings_clears_default_llm(self):
        """Reset restores default_llm to the Django settings default (empty)."""
        instance = PipelineSettings.get_instance()
        instance.default_llm = "anthropic:claude-opus-4-6"
        instance.save()
        PipelineSettings.clear_cache()

        mutation = """
            mutation {
                resetPipelineSettings {
                    ok
                    pipelineSettings { defaultLlm }
                }
            }
        """
        result = self.superuser_client.execute(mutation)
        self.assertIsNone(result.get("errors"))
        self.assertTrue(result["data"]["resetPipelineSettings"]["ok"])
        self.assertEqual(
            result["data"]["resetPipelineSettings"]["pipelineSettings"]["defaultLlm"],
            "",
        )

    def _make_fake_secret_registry(self):
        """Build a mock registry containing a parser-class fake with a SECRET field.

        Returns ``(registry_mock, fake_class_name, secret_field_name)``. Tests
        patch ``opencontractserver.pipeline.registry.get_registry`` to return
        ``registry_mock`` so plaintext-secret rejection logic is exercised
        regardless of which real components are installed in the test image.
        """
        from opencontractserver.pipeline.base.settings_schema import (
            PipelineSetting,
            SettingType,
        )

        @dataclass
        class FakeSettings:
            api_key: str = field(
                default="",
                metadata={
                    "pipeline_setting": PipelineSetting(
                        setting_type=SettingType.SECRET,
                        required=True,
                        description="Fake secret for tests",
                    )
                },
            )

        class FakeSecretParser:
            Settings = FakeSettings

        fake_class_name = "fake.module.FakeSecretParser"
        fake_def = type(
            "FakeDef",
            (),
            {
                "component_class": FakeSecretParser,
                "class_name": fake_class_name,
            },
        )()

        registry_mock = type(
            "MockRegistry",
            (),
            {
                "get_by_class_name": lambda self, path: (
                    fake_def if path == fake_class_name else None
                ),
                "parsers": (fake_def,),
                "embedders": (),
                "thumbnailers": (),
                "post_processors": (),
            },
        )()

        return registry_mock, fake_class_name, "api_key"

    def test_update_parser_kwargs_rejects_plaintext_secret(self):
        """parser_kwargs must reject non-empty values for SECRET-typed fields."""
        registry_mock, fake_path, secret_field = self._make_fake_secret_registry()

        mutation = """
            mutation UpdatePipelineSettings($parserKwargs: GenericScalar) {
                updatePipelineSettings(parserKwargs: $parserKwargs) {
                    ok
                    message
                }
            }
        """
        variables = {
            "parserKwargs": {
                fake_path: {secret_field: "sk-real-secret-value"},
            }
        }

        with patch(
            "opencontractserver.pipeline.registry.get_registry",
            return_value=registry_mock,
        ):
            result = self.superuser_client.execute(mutation, variables=variables)

        self.assertIsNone(result.get("errors"))
        self.assertFalse(result["data"]["updatePipelineSettings"]["ok"])
        message = result["data"]["updatePipelineSettings"]["message"]
        self.assertIn(secret_field, message)
        self.assertIn("updateComponentSecrets", message)
        # And the secret value itself must not be echoed back
        self.assertNotIn("sk-real-secret-value", message)

    def test_update_parser_kwargs_allows_empty_secret_placeholder(self):
        """Empty-string placeholders for SECRET fields are allowed as schema markers."""
        registry_mock, fake_path, secret_field = self._make_fake_secret_registry()

        mutation = """
            mutation UpdatePipelineSettings($parserKwargs: GenericScalar) {
                updatePipelineSettings(parserKwargs: $parserKwargs) {
                    ok
                    message
                }
            }
        """
        variables = {
            "parserKwargs": {fake_path: {secret_field: ""}},
        }

        with patch(
            "opencontractserver.pipeline.registry.get_registry",
            return_value=registry_mock,
        ):
            result = self.superuser_client.execute(mutation, variables=variables)

        self.assertIsNone(result.get("errors"))
        self.assertTrue(
            result["data"]["updatePipelineSettings"]["ok"],
            msg=result["data"]["updatePipelineSettings"]["message"],
        )

    def test_update_parser_kwargs_rejects_non_dict_value(self):
        """parser_kwargs entries must be dicts; non-dict values produce a clear error."""
        mutation = """
            mutation UpdatePipelineSettings($parserKwargs: GenericScalar) {
                updatePipelineSettings(parserKwargs: $parserKwargs) {
                    ok
                    message
                }
            }
        """
        variables = {
            "parserKwargs": {"my.parser.P": "not-a-dict"},
        }

        result = self.superuser_client.execute(mutation, variables=variables)
        self.assertIsNone(result.get("errors"))
        self.assertFalse(result["data"]["updatePipelineSettings"]["ok"])
        message = result["data"]["updatePipelineSettings"]["message"]
        self.assertIn("my.parser.P", message)
        self.assertIn("must be dicts", message)

    def test_update_component_settings_rejects_plaintext_secret(self):
        """component_settings must also reject plaintext secrets (audit-siblings)."""
        registry_mock, fake_path, secret_field = self._make_fake_secret_registry()

        mutation = """
            mutation UpdatePipelineSettings($componentSettings: GenericScalar) {
                updatePipelineSettings(componentSettings: $componentSettings) {
                    ok
                    message
                }
            }
        """
        variables = {
            "componentSettings": {
                fake_path: {secret_field: "sk-leak-attempt"},
            }
        }

        with patch(
            "opencontractserver.pipeline.registry.get_registry",
            return_value=registry_mock,
        ):
            result = self.superuser_client.execute(mutation, variables=variables)

        self.assertIsNone(result.get("errors"))
        self.assertFalse(result["data"]["updatePipelineSettings"]["ok"])
        message = result["data"]["updatePipelineSettings"]["message"]
        self.assertIn(secret_field, message)
        self.assertIn("updateComponentSecrets", message)
        self.assertNotIn("sk-leak-attempt", message)


class EnabledComponentsMutationTestCase(TestCase):
    """Tests for enabled_components validation in UpdatePipelineSettingsMutation."""

    def setUp(self):
        from django.core.cache import cache

        self.superuser = User.objects.create_superuser(
            username="ps_ec_admin", password="admin", email="ps_ec_admin@test.com"
        )
        self.superuser_client = Client(
            schema, context_value=TestContext(self.superuser)
        )

        # Ensure the singleton exists and clear filetype default assignments.
        # This prevents validation conflicts when tests set enabled_components,
        # since the mutation rejects lists that omit assigned-default components.
        # use_cache=False bypasses stale cache entries from prior tests.
        instance = PipelineSettings.get_instance(use_cache=False)
        instance.preferred_parsers = {}
        instance.preferred_embedders = {}
        instance.preferred_thumbnailers = {}
        instance.default_embedder = ""
        instance.enabled_components = []
        instance.save()
        # save() may re-populate the cache; clear it so tests start fresh.
        cache.delete(PipelineSettings.CACHE_KEY)

    def tearDown(self):
        """Clear the PipelineSettings singleton cache after every test.

        The ``PipelineSettings`` singleton is cached in a process-global
        ``LocMemCache`` that is NOT transaction-aware. This class's ``setUp``
        sets ``default_embedder=""``; a rejection-path mutation under test
        then calls ``get_instance(use_cache=True)``, which caches the
        empty-embedder instance. The DB row rolls back on test teardown, but
        the cached Python object does not — so without this cleanup it
        poisons every later test class on the same xdist worker (agent /
        vector-store tests fail with "resolved no embedder_path").
        """
        from django.core.cache import cache

        cache.delete(PipelineSettings.CACHE_KEY)

    def _get_real_component_paths(self):
        """Return a dict with real component paths from the registry."""
        from opencontractserver.pipeline.registry import get_registry

        registry = get_registry()
        result = {}
        if registry.parsers:
            result["parser"] = registry.parsers[0].class_name
        if registry.embedders:
            result["embedder"] = registry.embedders[0].class_name
        if registry.thumbnailers:
            result["thumbnailer"] = registry.thumbnailers[0].class_name
        return result

    def test_set_enabled_components(self):
        """Setting enabled_components should store the list successfully."""
        from opencontractserver.pipeline.registry import get_registry

        registry = get_registry()
        # Include ALL registered components to avoid conflicts with filetype defaults
        component_list = [
            c.class_name
            for c in registry.parsers + registry.embedders + registry.thumbnailers
        ]
        if not component_list:
            self.skipTest("Need at least 1 registered component for this test")

        mutation = """
            mutation UpdatePipelineSettings($enabledComponents: [String]) {
                updatePipelineSettings(enabledComponents: $enabledComponents) {
                    ok
                    message
                    pipelineSettings {
                        enabledComponents
                    }
                }
            }
        """

        result = self.superuser_client.execute(
            mutation, variables={"enabledComponents": component_list}
        )
        self.assertIsNone(result.get("errors"))
        data = result["data"]["updatePipelineSettings"]
        self.assertTrue(data["ok"], data.get("message"))
        self.assertEqual(
            sorted(data["pipelineSettings"]["enabledComponents"]),
            sorted(component_list),
        )

        # Verify persisted to DB
        instance = PipelineSettings.get_instance(use_cache=False)
        self.assertEqual(sorted(instance.enabled_components), sorted(component_list))

    def test_cannot_disable_assigned_component(self):
        """A component assigned as a preferred parser cannot be removed from enabled_components."""
        components = self._get_real_component_paths()
        if "parser" not in components:
            self.skipTest("Need at least 1 registered parser for this test")

        parser_path = components["parser"]

        # First assign the parser as preferred for application/pdf
        assign_mutation = """
            mutation UpdatePipelineSettings($preferredParsers: GenericScalar) {
                updatePipelineSettings(preferredParsers: $preferredParsers) {
                    ok
                    message
                }
            }
        """
        result = self.superuser_client.execute(
            assign_mutation,
            variables={"preferredParsers": {"application/pdf": parser_path}},
        )
        self.assertTrue(result["data"]["updatePipelineSettings"]["ok"])

        # Now try to set enabled_components WITHOUT the assigned parser
        other_paths = [v for k, v in components.items() if k != "parser"]
        if not other_paths:
            # If the parser is the only component, use an empty enabled list
            # that should fail because the parser is assigned
            other_paths = []

        # Use a different real component (or empty list if none available).
        # The key point: the assigned parser is NOT in the list.
        enable_mutation = """
            mutation UpdatePipelineSettings($enabledComponents: [String]) {
                updatePipelineSettings(enabledComponents: $enabledComponents) {
                    ok
                    message
                }
            }
        """

        # If other_paths is empty, we need at least one component in the list
        # to make it non-empty (empty list means "all enabled" and would succeed).
        # We'll use whatever other components are available, or fabricate the
        # scenario by passing only a non-parser component.
        from opencontractserver.pipeline.registry import get_registry

        registry = get_registry()
        all_paths = [
            c.class_name
            for c in registry.parsers + registry.embedders + registry.thumbnailers
        ]
        enabled_without_parser = [p for p in all_paths if p != parser_path]

        if not enabled_without_parser:
            self.skipTest("Need at least 2 registered components to test disabling one")

        result = self.superuser_client.execute(
            enable_mutation,
            variables={"enabledComponents": enabled_without_parser},
        )
        self.assertIsNone(result.get("errors"))
        data = result["data"]["updatePipelineSettings"]
        self.assertFalse(data["ok"])
        self.assertIn("Cannot disable", data["message"])
        self.assertIn(parser_path, data["message"])

    def test_invalid_component_path_rejected(self):
        """Nonexistent component paths in enabled_components should be rejected."""
        mutation = """
            mutation UpdatePipelineSettings($enabledComponents: [String]) {
                updatePipelineSettings(enabledComponents: $enabledComponents) {
                    ok
                    message
                }
            }
        """

        result = self.superuser_client.execute(
            mutation,
            variables={"enabledComponents": ["nonexistent.module.FakeComponent"]},
        )
        self.assertIsNone(result.get("errors"))
        data = result["data"]["updatePipelineSettings"]
        self.assertFalse(data["ok"])
        self.assertIn("not found in registry", data["message"])

    def test_empty_enabled_components_always_succeeds(self):
        """Empty list (meaning 'all enabled') should always succeed regardless of assignments."""
        components = self._get_real_component_paths()

        # First assign a parser so there's an active assignment
        if "parser" in components:
            assign_mutation = """
                mutation UpdatePipelineSettings($preferredParsers: GenericScalar) {
                    updatePipelineSettings(preferredParsers: $preferredParsers) {
                        ok
                        message
                    }
                }
            """
            result = self.superuser_client.execute(
                assign_mutation,
                variables={
                    "preferredParsers": {"application/pdf": components["parser"]}
                },
            )
            self.assertTrue(result["data"]["updatePipelineSettings"]["ok"])

        # Now set enabled_components to empty list — should succeed
        mutation = """
            mutation UpdatePipelineSettings($enabledComponents: [String]) {
                updatePipelineSettings(enabledComponents: $enabledComponents) {
                    ok
                    message
                    pipelineSettings {
                        enabledComponents
                    }
                }
            }
        """

        result = self.superuser_client.execute(
            mutation, variables={"enabledComponents": []}
        )
        self.assertIsNone(result.get("errors"))
        data = result["data"]["updatePipelineSettings"]
        self.assertTrue(data["ok"], data.get("message"))
        self.assertEqual(data["pipelineSettings"]["enabledComponents"], [])

    def test_transition_from_all_enabled_to_explicit_list(self):
        """Simulate the frontend toggle: start with [] (all enabled), then
        disable one component by sending the full list minus that component.
        Verify the mutation succeeds and the query reflects the change."""
        from opencontractserver.pipeline.registry import get_registry

        registry = get_registry()
        all_paths = sorted(
            {
                c.class_name
                for c in registry.parsers + registry.embedders + registry.thumbnailers
            }
        )
        if len(all_paths) < 2:
            self.skipTest("Need at least 2 registered components")

        # Pick one component to disable (setUp already clears filetype defaults)
        target = all_paths[0]
        new_enabled = [p for p in all_paths if p != target]

        mutation = """
            mutation UpdatePipelineSettings($enabledComponents: [String]) {
                updatePipelineSettings(enabledComponents: $enabledComponents) {
                    ok
                    message
                    pipelineSettings {
                        enabledComponents
                    }
                }
            }
        """

        result = self.superuser_client.execute(
            mutation, variables={"enabledComponents": new_enabled}
        )
        self.assertIsNone(result.get("errors"))
        data = result["data"]["updatePipelineSettings"]
        self.assertTrue(data["ok"], data.get("message"))
        self.assertEqual(
            sorted(data["pipelineSettings"]["enabledComponents"]),
            sorted(new_enabled),
        )

        # Verify the disabled component is reflected in a query
        query = """
            query {
                pipelineComponents {
                    parsers { className enabled }
                    embedders { className enabled }
                    thumbnailers { className enabled }
                }
            }
        """
        query_result = self.superuser_client.execute(query)
        self.assertIsNone(query_result.get("errors"))
        components_data = query_result["data"]["pipelineComponents"]
        all_components = (
            components_data["parsers"]
            + components_data["embedders"]
            + components_data["thumbnailers"]
        )

        target_component = next(
            (c for c in all_components if c["className"] == target), None
        )
        self.assertIsNotNone(
            target_component,
            f"Disabled component {target} should still appear in query results",
        )
        assert target_component is not None
        self.assertFalse(
            target_component["enabled"],
            f"Component {target} should be disabled after transition",
        )

        # Verify all other components are still enabled
        for comp in all_components:
            if comp["className"] != target and comp["className"] in new_enabled:
                self.assertTrue(
                    comp["enabled"],
                    f"Component {comp['className']} should still be enabled",
                )

    def test_toggle_accepts_duplicates_in_enabled_list(self):
        """Verify that duplicate class names in enabled_components are accepted
        gracefully (the mutation deduplicates before storing)."""
        from opencontractserver.pipeline.registry import get_registry

        registry = get_registry()
        if not registry.parsers:
            self.skipTest("Need at least 1 registered parser")

        # setUp already clears filetype defaults to avoid "cannot disable assigned" errors
        path = registry.parsers[0].class_name
        mutation = """
            mutation UpdatePipelineSettings($enabledComponents: [String]) {
                updatePipelineSettings(enabledComponents: $enabledComponents) {
                    ok
                    message
                    pipelineSettings { enabledComponents }
                }
            }
        """
        result = self.superuser_client.execute(
            mutation, variables={"enabledComponents": [path, path]}
        )
        self.assertIsNone(result.get("errors"))
        data = result["data"]["updatePipelineSettings"]
        self.assertTrue(data["ok"], data.get("message"))

        stored = data["pipelineSettings"]["enabledComponents"]
        self.assertEqual(
            stored,
            [path],
            "Backend should deduplicate enabled_components before storing",
        )


class PipelineSettingsSecretsTestCase(TestCase):
    """Tests for encrypted secrets storage in PipelineSettings."""

    def setUp(self):
        from django.core.cache import cache

        # Clear cache to ensure clean state between tests
        cache.delete(PipelineSettings.CACHE_KEY)

        self.superuser = User.objects.create_superuser(
            username="ps_test_admin", password="admin", email="ps_test_admin@test.com"
        )
        self.regular_user = User.objects.create_user(
            username="ps_test_regular", password="regular"
        )
        self.superuser_client = Client(
            schema, context_value=TestContext(self.superuser)
        )
        self.regular_client = Client(
            schema, context_value=TestContext(self.regular_user)
        )
        PipelineSettings.objects.all().delete()

    def test_set_and_get_secrets(self):
        """Test basic encryption/decryption of secrets."""
        instance = PipelineSettings.get_instance()

        secrets = {
            "component.path.TestParser": {
                "api_key": "sk-test-12345",
                "secret_token": "tok-abcdef",
            }
        }

        instance.set_secrets(secrets)
        instance.save()

        # Retrieve and verify
        instance.refresh_from_db()
        retrieved = instance.get_secrets()

        self.assertEqual(
            retrieved["component.path.TestParser"]["api_key"], "sk-test-12345"
        )
        self.assertEqual(
            retrieved["component.path.TestParser"]["secret_token"], "tok-abcdef"
        )

    def test_update_secrets_merges_with_existing(self):
        """Test that update_secrets merges with existing secrets."""
        instance = PipelineSettings.get_instance()

        # Set initial secrets
        instance.set_secrets({"component.path.Parser1": {"key1": "value1"}})
        instance.save()

        # Update with new secret for same component
        instance.update_secrets("component.path.Parser1", {"key2": "value2"})
        instance.save()

        secrets = instance.get_secrets()
        self.assertEqual(secrets["component.path.Parser1"]["key1"], "value1")
        self.assertEqual(secrets["component.path.Parser1"]["key2"], "value2")

    def test_get_component_secrets(self):
        """Test getting secrets for a specific component."""
        instance = PipelineSettings.get_instance()

        instance.set_secrets(
            {
                "component.path.Parser1": {"api_key": "key1"},
                "component.path.Parser2": {"api_key": "key2"},
            }
        )
        instance.save()

        parser1_secrets = instance.get_component_secrets("component.path.Parser1")
        self.assertEqual(parser1_secrets["api_key"], "key1")

        # Non-existent component returns empty dict
        empty_secrets = instance.get_component_secrets("component.path.NonExistent")
        self.assertEqual(empty_secrets, {})

    def test_delete_component_secrets(self):
        """Test deleting secrets for a component."""
        instance = PipelineSettings.get_instance()

        instance.set_secrets(
            {
                "component.path.Parser1": {"api_key": "key1"},
                "component.path.Parser2": {"api_key": "key2"},
            }
        )
        instance.save()

        instance.delete_component_secrets("component.path.Parser1")
        instance.save()

        secrets = instance.get_secrets()
        self.assertNotIn("component.path.Parser1", secrets)
        self.assertIn("component.path.Parser2", secrets)

    def test_get_full_component_settings_merges_secrets(self):
        """Test that get_full_component_settings merges non-sensitive and secrets."""
        instance = PipelineSettings.get_instance()

        # Set non-sensitive settings
        instance.component_settings = {
            "component.path.TestParser": {"timeout": 60, "batch_size": 10}
        }

        # Set secrets
        instance.set_secrets(
            {"component.path.TestParser": {"api_key": "secret-key-123"}}
        )
        instance.save()

        full_settings = instance.get_full_component_settings(
            "component.path.TestParser"
        )

        self.assertEqual(full_settings["timeout"], 60)
        self.assertEqual(full_settings["batch_size"], 10)
        self.assertEqual(full_settings["api_key"], "secret-key-123")

    def test_encrypted_secrets_not_readable_as_plaintext(self):
        """Test that encrypted secrets are not stored as plaintext."""
        instance = PipelineSettings.get_instance()

        secret_value = "super-secret-api-key-12345"
        instance.set_secrets({"test.parser": {"api_key": secret_value}})
        instance.save()
        instance.refresh_from_db()

        # The encrypted_secrets field should contain binary data
        self.assertIsNotNone(instance.encrypted_secrets)
        assert instance.encrypted_secrets is not None

        # The secret value should NOT appear in the raw binary
        raw_bytes = bytes(instance.encrypted_secrets)
        self.assertNotIn(secret_value.encode(), raw_bytes)

    def test_update_component_secrets_mutation_as_superuser(self):
        """Test updating secrets via GraphQL mutation."""
        mutation = """
            mutation UpdateComponentSecrets(
                $componentPath: String!,
                $secrets: GenericScalar!
            ) {
                updateComponentSecrets(
                    componentPath: $componentPath,
                    secrets: $secrets
                ) {
                    ok
                    message
                    componentsWithSecrets
                }
            }
        """

        variables = {
            "componentPath": "test.parser.TestParser",
            "secrets": {"api_key": "test-key-123"},
        }

        result = self.superuser_client.execute(mutation, variables=variables)
        self.assertIsNone(result.get("errors"))
        self.assertTrue(result["data"]["updateComponentSecrets"]["ok"])
        self.assertIn(
            "test.parser.TestParser",
            result["data"]["updateComponentSecrets"]["componentsWithSecrets"],
        )

    def test_update_component_secrets_mutation_as_regular_user_fails(self):
        """Test that regular users cannot update secrets."""
        mutation = """
            mutation UpdateComponentSecrets(
                $componentPath: String!,
                $secrets: GenericScalar!
            ) {
                updateComponentSecrets(
                    componentPath: $componentPath,
                    secrets: $secrets
                ) {
                    ok
                    message
                }
            }
        """

        variables = {
            "componentPath": "test.parser.TestParser",
            "secrets": {"api_key": "test-key-123"},
        }

        result = self.regular_client.execute(mutation, variables=variables)
        self.assertIsNone(result.get("errors"))
        self.assertFalse(result["data"]["updateComponentSecrets"]["ok"])
        self.assertIn(
            "superuser",
            result["data"]["updateComponentSecrets"]["message"].lower(),
        )

    def test_delete_component_secrets_mutation(self):
        """Test deleting secrets via GraphQL mutation."""
        # First set some secrets
        instance = PipelineSettings.get_instance()
        instance.set_secrets({"test.parser.TestParser": {"api_key": "key"}})
        instance.save()

        mutation = """
            mutation DeleteComponentSecrets($componentPath: String!) {
                deleteComponentSecrets(componentPath: $componentPath) {
                    ok
                    message
                    componentsWithSecrets
                }
            }
        """

        variables = {"componentPath": "test.parser.TestParser"}

        result = self.superuser_client.execute(mutation, variables=variables)
        self.assertIsNone(result.get("errors"))
        self.assertTrue(result["data"]["deleteComponentSecrets"]["ok"])
        self.assertNotIn(
            "test.parser.TestParser",
            result["data"]["deleteComponentSecrets"]["componentsWithSecrets"],
        )

    def test_pipeline_settings_query_includes_components_with_secrets(self):
        """Test that the query returns list of components with secrets."""
        # Set some secrets
        instance = PipelineSettings.get_instance()
        instance.set_secrets(
            {
                "parser1.path": {"key": "value1"},
                "parser2.path": {"key": "value2"},
            }
        )
        instance.save()

        query = """
            query {
                pipelineSettings {
                    componentsWithSecrets
                }
            }
        """

        result = self.superuser_client.execute(query)
        self.assertIsNone(result.get("errors"))

        components = result["data"]["pipelineSettings"]["componentsWithSecrets"]
        self.assertIn("parser1.path", components)
        self.assertIn("parser2.path", components)


class PipelineSettingsEdgeCasesTestCase(TestCase):
    """Tests for edge cases and error handling."""

    def setUp(self):
        from django.core.cache import cache

        # Clear cache to ensure clean state between tests
        cache.delete(PipelineSettings.CACHE_KEY)

        self.superuser = User.objects.create_superuser(
            username="ps_test_admin", password="admin", email="ps_test_admin@test.com"
        )
        self.superuser_client = Client(
            schema, context_value=TestContext(self.superuser)
        )
        PipelineSettings.objects.all().delete()

    def test_secrets_size_limit(self):
        """Test that oversized secrets are rejected."""
        instance = PipelineSettings.get_instance()

        # Create a secret payload that exceeds the 10KB limit
        large_value = "x" * 15000  # 15KB
        with self.assertRaises(ValueError) as context:
            instance.set_secrets({"test.parser": {"api_key": large_value}})

        self.assertIn("exceeds maximum size", str(context.exception))

    def test_invalid_component_path_format(self):
        """Test that invalid component paths are rejected."""
        mutation = """
            mutation UpdateComponentSecrets(
                $componentPath: String!,
                $secrets: GenericScalar!
            ) {
                updateComponentSecrets(
                    componentPath: $componentPath,
                    secrets: $secrets
                ) {
                    ok
                    message
                }
            }
        """

        # Test path with invalid characters
        variables = {
            "componentPath": "invalid path with spaces",
            "secrets": {"api_key": "test"},
        }
        result = self.superuser_client.execute(mutation, variables=variables)
        self.assertFalse(result["data"]["updateComponentSecrets"]["ok"])
        self.assertIn(
            "Invalid component path",
            result["data"]["updateComponentSecrets"]["message"],
        )

        # Test path that's too long
        variables = {
            "componentPath": "a" * 300 + ".module.Class",
            "secrets": {"api_key": "test"},
        }
        result = self.superuser_client.execute(mutation, variables=variables)
        self.assertFalse(result["data"]["updateComponentSecrets"]["ok"])
        self.assertIn(
            "exceeds maximum length",
            result["data"]["updateComponentSecrets"]["message"],
        )

    def test_invalid_secret_value_types(self):
        """Test that non-primitive secret values are rejected."""
        mutation = """
            mutation UpdateComponentSecrets(
                $componentPath: String!,
                $secrets: GenericScalar!
            ) {
                updateComponentSecrets(
                    componentPath: $componentPath,
                    secrets: $secrets
                ) {
                    ok
                    message
                }
            }
        """

        # Test nested dict (should be rejected)
        variables = {
            "componentPath": "valid.module.Class",
            "secrets": {"nested": {"key": "value"}},
        }
        result = self.superuser_client.execute(mutation, variables=variables)
        self.assertFalse(result["data"]["updateComponentSecrets"]["ok"])
        self.assertIn(
            "primitive type", result["data"]["updateComponentSecrets"]["message"]
        )

    def test_caching_invalidation_on_save(self):
        """Test that cache is invalidated when settings are saved."""
        from django.core.cache import cache

        instance = PipelineSettings.get_instance()

        # Verify cache is populated
        cached = cache.get(PipelineSettings.CACHE_KEY)
        self.assertIsNotNone(cached)

        # Modify and save
        instance.default_embedder = "new.embedder.Class"
        instance.save()

        # Cache should be invalidated
        cached_after_save = cache.get(PipelineSettings.CACHE_KEY)
        self.assertIsNone(cached_after_save)

        # Get instance again - should hit database
        new_instance = PipelineSettings.get_instance()
        self.assertEqual(new_instance.default_embedder, "new.embedder.Class")

    def test_bypass_cache_flag(self):
        """Test that use_cache=False bypasses the cache."""
        from django.core.cache import cache

        # Populate the cache by getting instance
        PipelineSettings.get_instance(use_cache=True)

        # Manually modify cache entry to test bypass
        cache.set(
            PipelineSettings.CACHE_KEY,
            "not_a_valid_instance",
            PipelineSettings._get_cache_ttl(),
        )

        # With use_cache=False, should get real instance from DB
        instance2 = PipelineSettings.get_instance(use_cache=False)
        self.assertIsInstance(instance2, PipelineSettings)

    def test_primitive_secret_types_accepted(self):
        """Test that all primitive types are accepted as secret values."""
        instance = PipelineSettings.get_instance()

        # All primitive types should work
        secrets = {
            "test.component": {
                "string_val": "test",
                "int_val": 42,
                "float_val": 3.14,
                "bool_val": True,
                "null_val": None,
            }
        }

        instance.set_secrets(secrets)
        instance.save()

        retrieved = instance.get_secrets()
        self.assertEqual(retrieved["test.component"]["string_val"], "test")
        self.assertEqual(retrieved["test.component"]["int_val"], 42)
        self.assertEqual(retrieved["test.component"]["float_val"], 3.14)
        self.assertEqual(retrieved["test.component"]["bool_val"], True)
        self.assertIsNone(retrieved["test.component"]["null_val"])

    def test_pbkdf2_encryption_uses_unique_salt(self):
        """Test that each encryption uses a unique salt."""
        instance = PipelineSettings.get_instance()

        # Encrypt same data twice
        instance.set_secrets({"test": {"key": "value"}})
        assert instance.encrypted_secrets is not None
        encrypted1 = bytes(instance.encrypted_secrets)

        instance.set_secrets({"test": {"key": "value"}})
        assert instance.encrypted_secrets is not None
        encrypted2 = bytes(instance.encrypted_secrets)

        # Salt is first 16 bytes - should be different each time
        salt1 = encrypted1[:16]
        salt2 = encrypted2[:16]
        self.assertNotEqual(salt1, salt2)

        # But decryption should still work
        decrypted = instance.get_secrets()
        self.assertEqual(decrypted["test"]["key"], "value")

    def test_secret_key_rotation_graceful_degradation(self):
        """Test that get_secrets returns {} when SECRET_KEY changes."""
        instance = PipelineSettings.get_instance()

        # Encrypt secrets with current SECRET_KEY
        instance.set_secrets({"test.parser": {"api_key": "secret-value"}})
        instance.save()
        instance.refresh_from_db()

        # Verify secrets are readable with original key
        self.assertEqual(
            instance.get_secrets()["test.parser"]["api_key"], "secret-value"
        )

        # Simulate SECRET_KEY rotation - secrets become unrecoverable
        with self.settings(SECRET_KEY="completely-different-secret-key-12345"):
            instance.refresh_from_db()
            result = instance.get_secrets()
            self.assertEqual(
                result, {}, "Should return empty dict when SECRET_KEY has changed"
            )


class PipelineSettingsIntegrationTestCase(TestCase):
    """Integration tests: GraphQL mutation → DB → runtime component selection."""

    def setUp(self):
        from django.core.cache import cache

        cache.delete(PipelineSettings.CACHE_KEY)

        self.superuser = User.objects.create_superuser(
            username="ps_test_admin", password="admin", email="ps_test_admin@test.com"
        )
        self.superuser_client = Client(
            schema, context_value=TestContext(self.superuser)
        )
        PipelineSettings.objects.all().delete()

    def test_graphql_update_changes_runtime_parser_selection(self):
        """GraphQL mutation updates DB, which changes runtime parser selection."""
        from opencontractserver.pipeline.registry import get_registry

        registry = get_registry()
        if len(registry.parsers) < 2:
            self.skipTest("Need at least 2 registered parsers for this test")

        parser_a = registry.parsers[0]
        parser_b = registry.parsers[1]

        # Set initial parser via GraphQL
        mutation = """
            mutation UpdatePipelineSettings($preferredParsers: GenericScalar) {
                updatePipelineSettings(preferredParsers: $preferredParsers) {
                    ok
                    message
                }
            }
        """

        result = self.superuser_client.execute(
            mutation,
            variables={"preferredParsers": {"application/pdf": parser_a.class_name}},
        )
        self.assertTrue(result["data"]["updatePipelineSettings"]["ok"])

        # Verify runtime selection returns parser_a
        instance = PipelineSettings.get_instance(use_cache=False)
        self.assertEqual(
            instance.get_preferred_parser("application/pdf"),
            parser_a.class_name,
        )

        # Update to parser_b via GraphQL
        result = self.superuser_client.execute(
            mutation,
            variables={"preferredParsers": {"application/pdf": parser_b.class_name}},
        )
        self.assertTrue(result["data"]["updatePipelineSettings"]["ok"])

        # Verify runtime selection now returns parser_b
        instance = PipelineSettings.get_instance(use_cache=False)
        self.assertEqual(
            instance.get_preferred_parser("application/pdf"),
            parser_b.class_name,
        )

    def test_graphql_update_changes_runtime_embedder_selection(self):
        """GraphQL mutation updates default embedder used at runtime."""
        from opencontractserver.pipeline.registry import get_registry

        registry = get_registry()
        if not registry.embedders:
            self.skipTest("Need at least 1 registered embedder for this test")

        embedder = registry.embedders[0]

        mutation = """
            mutation UpdatePipelineSettings($defaultEmbedder: String) {
                updatePipelineSettings(defaultEmbedder: $defaultEmbedder) {
                    ok
                    message
                }
            }
        """

        result = self.superuser_client.execute(
            mutation,
            variables={"defaultEmbedder": embedder.class_name},
        )
        self.assertTrue(result["data"]["updatePipelineSettings"]["ok"])

        # Verify runtime selection returns the updated embedder
        instance = PipelineSettings.get_instance(use_cache=False)
        self.assertEqual(instance.get_default_embedder(), embedder.class_name)

    def test_reset_restores_django_defaults_for_runtime(self):
        """Reset mutation restores Django defaults, affecting runtime selection."""
        # Set custom parser
        instance = PipelineSettings.get_instance()
        instance.preferred_parsers = {"application/pdf": "custom.Parser"}
        instance.save()
        PipelineSettings.clear_cache()

        self.assertEqual(
            PipelineSettings.get_instance(use_cache=False).get_preferred_parser(
                "application/pdf"
            ),
            "custom.Parser",
        )

        # Reset via GraphQL
        mutation = """
            mutation {
                resetPipelineSettings {
                    ok
                    message
                }
            }
        """
        result = self.superuser_client.execute(mutation)
        self.assertTrue(result["data"]["resetPipelineSettings"]["ok"])

        # Runtime selection should now return Django default (or None)
        from django.conf import settings as django_settings

        expected = getattr(django_settings, "PREFERRED_PARSERS", {}).get(
            "application/pdf"
        )
        instance = PipelineSettings.get_instance(use_cache=False)
        self.assertEqual(
            instance.get_preferred_parser("application/pdf"),
            expected,
        )


class PipelineSettingsSystemCheckTestCase(TestCase):
    """Tests for the documents.W001 system check."""

    def setUp(self):
        from django.core.cache import cache

        cache.delete(PipelineSettings.CACHE_KEY)
        PipelineSettings.objects.all().delete()

    @override_settings(
        PREFERRED_PARSERS={"application/pdf": "some.parser.Parser"},
        PREFERRED_EMBEDDERS={},
        DEFAULT_EMBEDDER="",
    )
    def test_warns_when_db_empty_but_django_configured(self):
        """System check warns when DB preferences are empty but Django settings exist."""
        from opencontractserver.documents.checks import (
            check_pipeline_settings_populated,
        )

        # Create PipelineSettings with empty preferences
        PipelineSettings.objects.create(
            id=1,
            preferred_parsers={},
            preferred_embedders={},
            default_embedder="",
        )

        warnings = check_pipeline_settings_populated(None)
        self.assertEqual(len(warnings), 1)
        self.assertEqual(warnings[0].id, "documents.W001")
        self.assertIn("migrate_pipeline_settings", warnings[0].hint)

    @override_settings(
        PREFERRED_PARSERS={"application/pdf": "some.parser.Parser"},
    )
    def test_no_warning_when_db_has_preferences(self):
        """No warning when DB preferences are populated."""
        from opencontractserver.documents.checks import (
            check_pipeline_settings_populated,
        )

        PipelineSettings.objects.create(
            id=1,
            preferred_parsers={"application/pdf": "some.parser.Parser"},
        )

        warnings = check_pipeline_settings_populated(None)
        self.assertEqual(len(warnings), 0)

    @override_settings(
        PREFERRED_PARSERS={},
        PREFERRED_EMBEDDERS={},
        DEFAULT_EMBEDDER="",
    )
    def test_no_warning_when_both_empty(self):
        """No warning when both DB and Django settings are empty."""
        from opencontractserver.documents.checks import (
            check_pipeline_settings_populated,
        )

        PipelineSettings.objects.create(
            id=1,
            preferred_parsers={},
            preferred_embedders={},
            default_embedder="",
        )

        warnings = check_pipeline_settings_populated(None)
        self.assertEqual(len(warnings), 0)

    def test_no_warning_when_no_pipeline_settings_row(self):
        """No warning when PipelineSettings table is empty (pre-migration)."""
        from opencontractserver.documents.checks import (
            check_pipeline_settings_populated,
        )

        warnings = check_pipeline_settings_populated(None)
        self.assertEqual(len(warnings), 0)


class ModernBERTDetectionCheckTestCase(TestCase):
    """Tests for the documents.W002 system check (ModernBERT detection)."""

    def setUp(self):
        from django.core.cache import cache

        cache.delete(PipelineSettings.CACHE_KEY)
        PipelineSettings.objects.all().delete()

    def test_warns_when_modernbert_in_preferred_embedders(self):
        """System check warns when preferred_embedders references ModernBERT."""
        from opencontractserver.documents.checks import check_modernbert_references

        PipelineSettings.objects.create(
            id=1,
            preferred_embedders={
                "application/pdf": "opencontractserver.pipeline.embedders"
                ".modern_bert_embedder.ModernBERTEmbedder"
            },
        )

        warnings = check_modernbert_references(None)
        self.assertEqual(len(warnings), 1)
        self.assertEqual(warnings[0].id, "documents.W002")
        self.assertIn("ModernBERT", warnings[0].msg)

    def test_warns_when_modernbert_is_default_embedder(self):
        """System check warns when default_embedder is a ModernBERT path."""
        from opencontractserver.documents.checks import check_modernbert_references

        PipelineSettings.objects.create(
            id=1,
            default_embedder="opencontractserver.pipeline.embedders"
            ".minn_modern_bert_embedder.MinnModernBERTEmbedder",
        )

        warnings = check_modernbert_references(None)
        self.assertEqual(len(warnings), 1)
        self.assertEqual(warnings[0].id, "documents.W002")

    def test_no_warning_when_no_modernbert_references(self):
        """No warning when PipelineSettings doesn't reference ModernBERT."""
        from opencontractserver.documents.checks import check_modernbert_references

        PipelineSettings.objects.create(
            id=1,
            preferred_embedders={"application/pdf": "some.other.Embedder"},
            default_embedder="some.other.DefaultEmbedder",
        )

        warnings = check_modernbert_references(None)
        self.assertEqual(len(warnings), 0)

    def test_no_warning_when_no_pipeline_settings(self):
        """No warning when PipelineSettings table is empty."""
        from opencontractserver.documents.checks import check_modernbert_references

        warnings = check_modernbert_references(None)
        self.assertEqual(len(warnings), 0)


class CheckExceptionHandlingTestCase(TestCase):
    """Tests for exception handling in Django system checks."""

    def test_pipeline_settings_check_handles_exception(self):
        """check_pipeline_settings_populated returns [] when exception occurs."""
        from opencontractserver.documents.checks import (
            check_pipeline_settings_populated,
        )

        with patch.object(
            PipelineSettings.objects, "exists", side_effect=Exception("DB unavailable")
        ):
            warnings = check_pipeline_settings_populated(None)
            self.assertEqual(warnings, [])

    def test_modernbert_check_handles_exception(self):
        """check_modernbert_references returns [] when exception occurs."""
        from opencontractserver.documents.checks import check_modernbert_references

        with patch.object(
            PipelineSettings.objects, "exists", side_effect=Exception("DB unavailable")
        ):
            warnings = check_modernbert_references(None)
            self.assertEqual(warnings, [])


class JSONSizeValidationTestCase(TestCase):
    """Tests for JSON field size validation in mutations."""

    def setUp(self):
        from django.core.cache import cache

        cache.delete(PipelineSettings.CACHE_KEY)

        self.superuser = User.objects.create_superuser(
            username="ps_test_admin", password="admin", email="ps_test_admin@test.com"
        )
        self.superuser_client = Client(
            schema, context_value=TestContext(self.superuser)
        )
        PipelineSettings.objects.all().delete()
        PipelineSettings.get_instance()

    def test_oversized_parser_kwargs_rejected(self):
        """Test that oversized parser_kwargs are rejected."""
        mutation = """
            mutation UpdatePipelineSettings($parserKwargs: GenericScalar) {
                updatePipelineSettings(parserKwargs: $parserKwargs) {
                    ok
                    message
                }
            }
        """

        # Create a payload exceeding 10KB
        large_kwargs = {"some.parser.Path": {"data": "x" * 15000}}

        result = self.superuser_client.execute(
            mutation, variables={"parserKwargs": large_kwargs}
        )
        self.assertFalse(result["data"]["updatePipelineSettings"]["ok"])
        self.assertIn("exceeds", result["data"]["updatePipelineSettings"]["message"])

    def test_normal_sized_parser_kwargs_accepted(self):
        """Test that normal-sized parser_kwargs are accepted."""
        mutation = """
            mutation UpdatePipelineSettings($parserKwargs: GenericScalar) {
                updatePipelineSettings(parserKwargs: $parserKwargs) {
                    ok
                    message
                }
            }
        """

        normal_kwargs = {"some.parser.Path": {"force_ocr": True, "timeout": 60}}

        result = self.superuser_client.execute(
            mutation, variables={"parserKwargs": normal_kwargs}
        )
        self.assertTrue(result["data"]["updatePipelineSettings"]["ok"])


class PipelineSettingsSchemaMethodsTestCase(TestCase):
    """Tests for PipelineSettings component schema and validation methods."""

    def setUp(self):
        from django.core.cache import cache

        cache.delete(PipelineSettings.CACHE_KEY)
        PipelineSettings.objects.all().delete()

    def test_get_component_schema_returns_schema(self):
        """get_component_schema returns schema for a registered component."""
        from opencontractserver.pipeline.registry import get_registry

        instance = PipelineSettings.get_instance()
        registry = get_registry()

        # Find a component that has a Settings dataclass
        for comp in registry.parsers + registry.embedders:
            if comp.settings_schema:
                schema = instance.get_component_schema(comp.class_name)
                self.assertIsInstance(schema, dict)
                # Schema should have at least one setting
                if schema:
                    first_setting = next(iter(schema.values()))
                    self.assertIn("type", first_setting)
                break

    def test_get_component_schema_not_found_returns_empty(self):
        """get_component_schema returns empty dict for unknown components."""
        instance = PipelineSettings.get_instance()
        schema = instance.get_component_schema("nonexistent.module.FakeParser")
        self.assertEqual(schema, {})

    def test_get_component_schema_by_name(self):
        """get_component_schema looks up by simple name if full path fails."""
        from opencontractserver.pipeline.registry import get_registry

        instance = PipelineSettings.get_instance()
        registry = get_registry()

        if registry.parsers:
            parser = registry.parsers[0]
            # Look up by simple name
            schema = instance.get_component_schema(parser.name)
            # May or may not have settings, but should not raise
            self.assertIsInstance(schema, dict)

    def test_validate_all_components_returns_dict(self):
        """validate_all_components returns a dict of missing settings."""
        instance = PipelineSettings.get_instance()
        result = instance.validate_all_components()
        self.assertIsInstance(result, dict)
        # Each value should be a list of setting names
        for class_path, missing in result.items():
            self.assertIsInstance(class_path, str)
            self.assertIsInstance(missing, list)

    def test_get_all_component_schemas_returns_dict(self):
        """get_all_component_schemas returns schemas for all components."""
        instance = PipelineSettings.get_instance()
        schemas = instance.get_all_component_schemas()
        self.assertIsInstance(schemas, dict)
        # Each value should be a dict of setting schemas
        for class_path, comp_schema in schemas.items():
            self.assertIsInstance(class_path, str)
            self.assertIsInstance(comp_schema, dict)

    def test_get_component_schema_marks_secret_has_value(self):
        """get_component_schema sets has_value for secrets without exposing values."""
        from opencontractserver.pipeline.registry import get_registry

        instance = PipelineSettings.get_instance()
        registry = get_registry()

        # Find a component with secret settings
        for comp in registry.parsers + registry.embedders:
            if comp.settings_schema:
                schema_info = {s["name"]: s for s in comp.settings_schema}
                secret_settings = [
                    n for n, s in schema_info.items() if s.get("type") == "secret"
                ]
                if secret_settings:
                    # Set a secret value
                    instance.set_secrets(
                        {comp.class_name: {secret_settings[0]: "test-secret"}}
                    )
                    instance.save()

                    schema = instance.get_component_schema(comp.class_name)
                    if secret_settings[0] in schema:
                        self.assertTrue(schema[secret_settings[0]]["has_value"])
                        # Secret value must NOT be exposed
                        self.assertIsNone(schema[secret_settings[0]]["current_value"])
                    break


class RegistryGetByNameTestCase(TestCase):
    """Tests for PipelineComponentRegistry.get_by_name."""

    def test_get_by_name_finds_component(self):
        """get_by_name finds components by simple class name."""
        from opencontractserver.pipeline.registry import get_registry

        registry = get_registry()
        if registry.parsers:
            parser = registry.parsers[0]
            result = registry.get_by_name(parser.name)
            self.assertIsNotNone(result)
            assert result is not None
            self.assertEqual(result.name, parser.name)

    def test_get_by_name_returns_none_for_unknown(self):
        """get_by_name returns None for unknown component names."""
        from opencontractserver.pipeline.registry import get_registry

        registry = get_registry()
        result = registry.get_by_name("NonExistentComponent12345")
        self.assertIsNone(result)


class SingletonConstraintTestCase(TestCase):
    """Tests for the database-level singleton constraint on PipelineSettings."""

    def setUp(self):
        from django.core.cache import cache

        cache.delete(PipelineSettings.CACHE_KEY)
        PipelineSettings.objects.all().delete()

    def test_db_constraint_rejects_pk_not_one(self):
        """Database constraint prevents creating PipelineSettings with pk != 1."""
        from django.db import connection, transaction

        # Create the singleton with pk=1
        PipelineSettings.objects.create(id=1)

        # Attempt to insert with pk=2 via raw SQL (bypassing save() validation).
        # Wrapped in a savepoint so IntegrityError doesn't abort the test transaction.
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute(
                        "INSERT INTO documents_pipelinesettings (id, preferred_parsers, "
                        "preferred_embedders, preferred_thumbnailers, parser_kwargs, "
                        "component_settings, default_embedder, modified) "
                        "VALUES (2, '{}', '{}', '{}', '{}', '{}', '', NOW())"
                    )

    def test_db_constraint_allows_pk_one(self):
        """Database constraint allows the singleton with pk=1."""
        instance = PipelineSettings.objects.create(id=1)
        self.assertEqual(instance.pk, 1)


class MissingSecretsCheckTestCase(TestCase):
    """Tests for the documents.W003 system check (missing required secrets)."""

    def setUp(self):
        from django.core.cache import cache

        cache.delete(PipelineSettings.CACHE_KEY)
        PipelineSettings.objects.all().delete()

    def test_warns_when_configured_component_missing_required_secrets(self):
        """System check warns when an active component is missing required secrets."""
        from opencontractserver.documents.checks import (
            check_configured_components_secrets,
        )
        from opencontractserver.pipeline.base.settings_schema import (
            PipelineSetting,
            SettingType,
        )

        # Create a mock component class with a required secret
        @dataclass
        class MockSettings:
            api_key: str = field(
                default="",
                metadata={
                    "pipeline_setting": PipelineSetting(
                        setting_type=SettingType.SECRET,
                        required=True,
                        description="Required API key",
                    )
                },
            )

        class MockComponent:
            Settings = MockSettings

        # Create a mock registry component definition
        mock_comp_def = type(
            "MockDef",
            (),
            {"component_class": MockComponent, "class_name": "mock.MockComponent"},
        )()

        # Set up PipelineSettings with this component as the preferred parser
        PipelineSettings.objects.create(
            id=1,
            preferred_parsers={"application/pdf": "mock.MockComponent"},
        )

        # No secrets configured — should warn
        mock_registry = type(
            "MockRegistry",
            (),
            {"get_by_class_name": lambda self, path: mock_comp_def},
        )()

        with patch(
            "opencontractserver.pipeline.registry.get_registry",
            return_value=mock_registry,
        ):
            warnings = check_configured_components_secrets(None)

        self.assertEqual(len(warnings), 1)
        self.assertEqual(warnings[0].id, "documents.W003")
        self.assertIn("mock.MockComponent", warnings[0].msg)
        self.assertIn("api_key", warnings[0].msg)

    def test_no_warning_when_secrets_are_configured(self):
        """No warning when all required secrets are present."""
        from opencontractserver.documents.checks import (
            check_configured_components_secrets,
        )
        from opencontractserver.pipeline.base.settings_schema import (
            PipelineSetting,
            SettingType,
        )

        @dataclass
        class MockSettings:
            api_key: str = field(
                default="",
                metadata={
                    "pipeline_setting": PipelineSetting(
                        setting_type=SettingType.SECRET,
                        required=True,
                        description="Required API key",
                    )
                },
            )

        class MockComponent:
            Settings = MockSettings

        mock_comp_def = type(
            "MockDef",
            (),
            {"component_class": MockComponent, "class_name": "mock.MockComponent"},
        )()

        instance = PipelineSettings.objects.create(
            id=1,
            preferred_parsers={"application/pdf": "mock.MockComponent"},
        )

        # Configure the required secret
        instance.set_secrets({"mock.MockComponent": {"api_key": "sk-test-key"}})
        instance.save()

        mock_registry = type(
            "MockRegistry",
            (),
            {"get_by_class_name": lambda self, path: mock_comp_def},
        )()

        with patch(
            "opencontractserver.pipeline.registry.get_registry",
            return_value=mock_registry,
        ):
            warnings = check_configured_components_secrets(None)

        self.assertEqual(len(warnings), 0)

    def test_no_warning_when_component_has_no_required_secrets(self):
        """No warning for components with only optional secrets."""
        from opencontractserver.documents.checks import (
            check_configured_components_secrets,
        )
        from opencontractserver.pipeline.base.settings_schema import (
            PipelineSetting,
            SettingType,
        )

        @dataclass
        class MockSettings:
            api_key: str = field(
                default="",
                metadata={
                    "pipeline_setting": PipelineSetting(
                        setting_type=SettingType.SECRET,
                        required=False,
                        description="Optional API key",
                    )
                },
            )

        class MockComponent:
            Settings = MockSettings

        mock_comp_def = type(
            "MockDef",
            (),
            {"component_class": MockComponent, "class_name": "mock.MockComponent"},
        )()

        PipelineSettings.objects.create(
            id=1,
            preferred_parsers={"application/pdf": "mock.MockComponent"},
        )

        mock_registry = type(
            "MockRegistry",
            (),
            {"get_by_class_name": lambda self, path: mock_comp_def},
        )()

        with patch(
            "opencontractserver.pipeline.registry.get_registry",
            return_value=mock_registry,
        ):
            warnings = check_configured_components_secrets(None)

        self.assertEqual(len(warnings), 0)

    def test_no_warning_when_no_pipeline_settings(self):
        """No warning when PipelineSettings table is empty."""
        from opencontractserver.documents.checks import (
            check_configured_components_secrets,
        )

        warnings = check_configured_components_secrets(None)
        self.assertEqual(len(warnings), 0)

    def test_check_handles_exception(self):
        """check_configured_components_secrets returns [] when exception occurs."""
        from opencontractserver.documents.checks import (
            check_configured_components_secrets,
        )

        with patch.object(
            PipelineSettings.objects,
            "exists",
            side_effect=Exception("DB unavailable"),
        ):
            warnings = check_configured_components_secrets(None)
            self.assertEqual(warnings, [])
