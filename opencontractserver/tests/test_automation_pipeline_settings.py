"""HTTP integration tests for the global pipeline automation capabilities."""

import io
import json
from datetime import timedelta
from typing import Any
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from graphql import parse, validate
from rest_framework.test import APIClient

from config.graphql import pipeline_settings_mutations
from config.graphql.schema import schema
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import PipelineSettings
from opencontractserver.users.models import AutomationCredential
from opencontractserver.users.services import automation_credentials as credentials

OPENAI = "opencontractserver.pipeline.embedders.openai_embedder.OpenAIEmbedder"
SIBLING = "opencontractserver.pipeline.parsers.text_parser.TextParser"
STORED_SECRET = "stored-component-secret-for-test"
READ = "{ pipelineSettings { componentSettings defaultLlm } }"
UPDATE = """
mutation($settings: GenericScalar) {
  updatePipelineSettings(componentSettings: $settings) {
    ok message pipelineSettings { componentSettings modified componentsWithSecrets }
  }
}
"""
REGISTRY = """
query {
  pipelineComponents {
    parsers { ...Component }
    embedders { ...Component }
    thumbnailers { ...Component }
    postProcessors { ...Component }
    rerankers { ...Component }
    enrichers { ...Component }
    llmProviders { ...Component }
    fileConverters { ...Component }
  }
  supportedMimeTypes { mimetype fileType label fullySupported stageCoverage { parser embedder thumbnailer } }
  convertibleExtensions
  pipelineSettings { componentsWithSecrets toolsWithSecrets parserKwargs componentSettings }
}
fragment Component on PipelineComponentType {
  className title componentType inputSchema enabled
  settingsSchema { name settingType pythonType required description default envVar hasValue currentValue }
}
"""


@override_settings(CELERY_TASK_ALWAYS_EAGER=False)
class AutomationPipelineSettingsTests(TestCase):
    client: APIClient

    def setUp(self):
        self.admin = get_user_model().objects.create_user(
            username="pipeline-admin", is_superuser=True
        )
        self.regular = get_user_model().objects.create_user(username="regular")
        self.corpus = Corpus.objects.create(title="Restricted", creator=self.admin)
        self.pipeline = PipelineSettings.get_instance(use_cache=False)
        self.pipeline.component_settings = {
            OPENAI: {"openai_embedding_dimensions": 768},
            SIBLING: {"keep_this_setting": True},
        }
        self.pipeline.parser_kwargs = {}
        self.pipeline.modified_by = None
        self.pipeline.set_secrets(
            {
                OPENAI: {"openai_api_key": STORED_SECRET},
                "tool:web_search": {"api_key": "stored-tool-secret"},
            }
        )
        self.pipeline.save()
        self.client = APIClient()
        self.authenticate()

    def authenticate(self, *, user=None, scopes=None, corpus_ids=None):
        credential, token = credentials.mint(
            user=user or self.admin,
            name="pipeline automation",
            scopes=(
                scopes
                if scopes is not None
                else ["pipeline:read", "pipeline:configure"]
            ),
            corpus_ids=corpus_ids,
            expires_at=timezone.now() + timedelta(days=1),
        )
        self.client.credentials(HTTP_AUTHORIZATION=f"Automation {token}")
        return credential, token

    def graphql(self, query, variables=None):
        # A typo must not masquerade as a successful security-denial test.
        self.assertEqual(validate(schema._schema, parse(query)), [])
        response = self.client.post(
            "/graphql/", {"query": query, "variables": variables or {}}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        return response.json()

    def data(self, query, variables=None):
        response = self.graphql(query, variables)
        self.assertNotIn("errors", response, response)
        return response["data"]

    def denied(self, query, variables=None, *, message=credentials.DENIED):
        response = self.graphql(query, variables)
        self.assertEqual(response["errors"][0]["message"], message)
        self.assertIsNone(response.get("data"))

    def test_cli_scoped_superuser_reads_schemas_updates_settings_and_reads_fresh_values(
        self,
    ):
        output = io.StringIO()
        call_command(
            "automation_credential",
            "mint",
            "--user",
            self.admin.username,
            "--name",
            "CLI pipeline",
            "--scope",
            "pipeline:read",
            "--scope",
            "pipeline:configure",
            "--all-corpuses",
            stdout=output,
        )
        token = json.loads(output.getvalue())["token"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Automation {token}")
        registry = self.data(REGISTRY)
        embedders = registry["pipelineComponents"]["embedders"]
        component = next(item for item in embedders if item["className"] == OPENAI)
        fields = {field["name"]: field for field in component["settingsSchema"]}
        self.assertEqual(fields["openai_embedding_dimensions"]["currentValue"], 768)
        self.assertEqual(fields["openai_api_key"]["settingType"], "secret")
        self.assertTrue(fields["openai_api_key"]["hasValue"])
        self.assertIsNone(fields["openai_api_key"]["currentValue"])
        self.assertTrue(
            any(
                item["mimetype"] == "application/pdf"
                for item in registry["supportedMimeTypes"]
            )
        )
        self.assertIsInstance(registry["convertibleExtensions"], list)
        self.assertEqual(
            registry["pipelineSettings"]["componentsWithSecrets"], [OPENAI]
        )
        self.assertEqual(
            registry["pipelineSettings"]["toolsWithSecrets"], ["tool:web_search"]
        )
        # REGISTRY warmed the real settings cache with the old value.
        with self.assertLogs(
            pipeline_settings_mutations.logger.name, level="INFO"
        ) as logs:
            result = self.data(
                UPDATE, {"settings": {OPENAI: {"openai_embedding_dimensions": 512}}}
            )["updatePipelineSettings"]
        self.assertTrue(result["ok"], result["message"])
        expected = {
            OPENAI: {"openai_embedding_dimensions": 512},
            SIBLING: {"keep_this_setting": True},
        }
        self.assertEqual(result["pipelineSettings"]["componentSettings"], expected)
        reread = self.data(READ)["pipelineSettings"]
        self.assertEqual(reread["componentSettings"], expected)
        self.pipeline.refresh_from_db()
        self.assertEqual(self.pipeline.modified_by_id, self.admin.pk)
        self.assertIn(f"updated by {self.admin.username}", "\n".join(logs.output))
        for secret in (STORED_SECRET, "stored-tool-secret", token):
            self.assertNotIn(secret, json.dumps([registry, result, reread]))
            self.assertNotIn(secret, "\n".join(logs.output))

    def test_read_and_configure_are_independent_and_old_scopes_gain_no_access(self):
        self.authenticate(scopes=["pipeline:read"])
        self.assertEqual(
            self.data(READ)["pipelineSettings"]["componentSettings"],
            self.pipeline.component_settings,
        )
        self.denied(
            UPDATE, {"settings": {OPENAI: {"openai_embedding_dimensions": 512}}}
        )
        self.authenticate(scopes=["pipeline:configure"])
        self.denied(READ)
        update = self.data(
            UPDATE, {"settings": {OPENAI: {"openai_embedding_dimensions": 512}}}
        )["updatePipelineSettings"]
        self.assertTrue(update["ok"], update["message"])
        self.assertEqual(
            update["pipelineSettings"]["componentSettings"][OPENAI][
                "openai_embedding_dimensions"
            ],
            512,
        )
        self.authenticate(scopes=["corpus:read", "ingestion:read"])
        self.denied(READ)
        self.denied(REGISTRY)
        self.denied(UPDATE)

    def test_all_pipeline_roots_require_superuser_and_explicit_all_corpus_access(self):
        operations = [
            READ,
            "{ pipelineComponents { embedders { className } } }",
            "{ supportedMimeTypes { mimetype } }",
            "{ convertibleExtensions }",
            UPDATE,
        ]
        restrictions: list[dict[str, Any]] = [
            {"user": self.regular},
            {"corpus_ids": [self.corpus.pk]},
            {"corpus_ids": []},
        ]
        for options in restrictions:
            self.authenticate(**options)
            for query in operations:
                with self.subTest(options=options, query=query):
                    self.denied(query)
        self.pipeline.refresh_from_db()
        self.assertIsNone(self.pipeline.modified_by_id)

    def test_secret_and_reset_roots_reject_mixed_mutations_before_any_resolver(self):
        denied_roots = [
            "resetPipelineSettings { ok }",
            f'updateComponentSecrets(componentPath: "{OPENAI}", secrets: {{openai_api_key: "inline"}}) {{ ok }}',
            f'deleteComponentSecrets(componentPath: "{OPENAI}") {{ ok }}',
            'updateToolSecrets(toolKey: "web_search", secrets: {api_key: "inline"}) { ok }',
            'deleteToolSecrets(toolKey: "web_search") { ok }',
        ]
        before = self.pipeline.encrypted_secrets
        assert before is not None
        with patch.object(
            pipeline_settings_mutations,
            "_mutate_UpdatePipelineSettingsMutation",
            wraps=pipeline_settings_mutations._mutate_UpdatePipelineSettingsMutation,
        ) as resolver:
            for field in denied_roots:
                with self.subTest(field=field):
                    self.denied("""mutation {
                      allowed: updatePipelineSettings(defaultLlm: "openai:gpt-4.1-mini") { ok }
                      ...Denied
                    } fragment Denied on Mutation { blocked: """ + field + " }")
            resolver.assert_not_called()
        self.pipeline.refresh_from_db()
        self.assertIsNone(self.pipeline.modified_by_id)
        assert self.pipeline.encrypted_secrets is not None
        self.assertEqual(bytes(self.pipeline.encrypted_secrets), bytes(before))

    def test_user_traversal_is_denied_in_queries_and_merged_mutation_fragments(self):
        self.denied(
            "{ allowed: pipelineSettings { componentSettings } forbidden: me { id } }"
        )
        self.denied("{ pipelineSettings { modifiedBy { ... on Node { id } } } }")
        with patch.object(
            pipeline_settings_mutations,
            "_mutate_UpdatePipelineSettingsMutation",
            wraps=pipeline_settings_mutations._mutate_UpdatePipelineSettingsMutation,
        ) as resolver:
            self.denied("""mutation {
              change: updatePipelineSettings(defaultLlm: "openai:gpt-4.1-mini") { ok }
              ...Again
            }
            fragment Again on Mutation {
              change: updatePipelineSettings(defaultLlm: "openai:gpt-4.1-mini") {
                pipelineSettings { ...UserLink }
              }
            }
            fragment UserLink on PipelineSettingsType { modifiedBy { id username } }
            """)
            resolver.assert_not_called()
        self.pipeline.refresh_from_db()
        self.assertIsNone(self.pipeline.modified_by_id)

    def test_existing_validation_still_rejects_inline_secrets_and_invalid_settings(
        self,
    ):
        before = self.pipeline.component_settings
        cases = [
            {"componentSettings": {OPENAI: {"openai_api_key": "inline-secret"}}},
            {"parserKwargs": {OPENAI: {"openai_api_key": "inline-secret"}}},
            {"componentSettings": {OPENAI: ["not a settings object"]}},
        ]
        query = """mutation($componentSettings: GenericScalar, $parserKwargs: GenericScalar) {
          updatePipelineSettings(componentSettings: $componentSettings, parserKwargs: $parserKwargs) {
            ok message pipelineSettings { componentSettings }
          }
        }"""
        for variables in cases:
            with self.subTest(variables=variables):
                result = self.data(query, variables)["updatePipelineSettings"]
                self.assertFalse(result["ok"], result)
                self.assertIsNone(result["pipelineSettings"])
                self.assertNotIn("inline-secret", json.dumps(result))
                self.pipeline.refresh_from_db()
                self.assertEqual(self.pipeline.component_settings, before)
                self.assertEqual(self.pipeline.parser_kwargs, {})
                self.assertIsNone(self.pipeline.modified_by_id)

    def test_revocation_expiry_and_inactive_principal_reject_reads_and_writes(self):
        for change in ("revoke", "expire", "deactivate"):
            credential, _ = self.authenticate()
            self.data(READ)
            if change == "revoke":
                credentials.revoke(credential.pk)
            elif change == "expire":
                AutomationCredential.objects.filter(pk=credential.pk).update(
                    expires_at=timezone.now() - timedelta(seconds=1)
                )
            else:
                get_user_model().objects.filter(pk=self.admin.pk).update(
                    is_active=False
                )
            with self.subTest(change=change):
                self.denied(READ, message=credentials.INVALID)
                self.denied(UPDATE, message=credentials.INVALID)
            get_user_model().objects.filter(pk=self.admin.pk).update(is_active=True)
        self.pipeline.refresh_from_db()
        self.assertIsNone(self.pipeline.modified_by_id)
