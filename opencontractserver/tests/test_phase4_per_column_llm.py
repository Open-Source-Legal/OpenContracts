"""Phase-4 tests: per-column LLM override + per-cell forensic trace.

Covers:
* :func:`resolve_extract_llm` honors ``column.preferred_llm`` over the
  singleton default.
* When ``column.preferred_llm`` is set but unresolvable, the resolver
  raises ``failure_mode="llm_unavailable"`` (no silent fallback to
  the singleton — explicit picks should fail loudly).
* When ``column.preferred_llm`` is None and no singleton default is
  set, raises ``failure_mode="llm_not_configured"`` (legacy fallback
  path preserved).
* GraphQL: ``ColumnType.preferred_llm`` and ``availableLlms`` resolvers.
* GraphQL: ``DatacellType.executed_llm`` resolver.
* Mutation: ``createColumn`` and ``updateColumnMutation`` accept
  ``preferred_llm_id``; reject archived/disabled/non-head targets.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from graphene.test import Client
from graphql_relay import to_global_id

from config.graphql.schema import schema
from opencontractserver.extracts.models import Column, Datacell, Fieldset
from opencontractserver.llm_configs.models import LLMSettings, RegisteredLLM
from opencontractserver.llms.providers.registry import reset_provider_registry_cache
from opencontractserver.llms.resolution import (
    FAILURE_MODE_NOT_CONFIGURED,
    FAILURE_MODE_UNAVAILABLE,
    LLMUnavailableError,
    resolve_extract_llm,
)

User = get_user_model()

OPENAI_PATH = "opencontractserver.llms.providers.openai.OpenAIProvider"
ANTHROPIC_PATH = "opencontractserver.llms.providers.anthropic.AnthropicProvider"


class _Context:
    def __init__(self, user) -> None:
        self.user = user


class _Phase4Base(TestCase):
    def setUp(self) -> None:
        reset_provider_registry_cache()
        cache.delete(LLMSettings.CACHE_KEY)
        self.user = User.objects.create_user(
            username="phase4_user",
            password="x",
            email="phase4_user@test.com",
            is_superuser=True,  # mutations require superuser
            is_staff=True,
        )
        self.fieldset = Fieldset.objects.create(
            name="fs1",
            description="d",
            creator=self.user,
        )
        self.settings = LLMSettings.get_instance(use_cache=False)
        self.settings.update_secrets(OPENAI_PATH, {"api_key": "sk-real"})
        self.settings.update_secrets(ANTHROPIC_PATH, {"api_key": "ant-real"})
        self.settings.save()
        cache.delete(LLMSettings.CACHE_KEY)

    def _make_llm(self, **overrides) -> RegisteredLLM:
        kwargs = dict(
            provider_class_path=OPENAI_PATH,
            model_id="gpt-4o-mini",
            display_name="GPT-4o mini",
            creator=self.user,
        )
        kwargs.update(overrides)
        return RegisteredLLM.objects.create(**kwargs)

    def _make_column(self, **overrides) -> Column:
        kwargs = dict(
            name="col",
            fieldset=self.fieldset,
            query="What is the answer?",
            output_type="str",
            creator=self.user,
        )
        kwargs.update(overrides)
        return Column.objects.create(**kwargs)


class ResolverPerColumnTests(_Phase4Base):
    def test_column_preferred_llm_wins_over_singleton_default(self):
        # Singleton default: openai
        default_llm = self._make_llm(model_id="gpt-4o-mini", display_name="default")
        self.settings.default_extract_llm = default_llm
        self.settings.save()
        cache.delete(LLMSettings.CACHE_KEY)
        # Column override: anthropic
        anthropic_llm = self._make_llm(
            provider_class_path=ANTHROPIC_PATH,
            model_id="claude-opus-4-7",
            display_name="anthropic-pref",
        )
        column = self._make_column(preferred_llm=anthropic_llm)

        resolved = resolve_extract_llm(column=column)
        self.assertEqual(resolved.registered_llm_id, anthropic_llm.pk)
        self.assertEqual(resolved.pydantic_ai_model_string, "anthropic:claude-opus-4-7")

    def test_no_column_override_falls_back_to_singleton_default(self):
        default_llm = self._make_llm()
        self.settings.default_extract_llm = default_llm
        self.settings.save()
        cache.delete(LLMSettings.CACHE_KEY)
        column = self._make_column()  # no preferred_llm

        resolved = resolve_extract_llm(column=column)
        self.assertEqual(resolved.registered_llm_id, default_llm.pk)

    def test_column_preferred_llm_raises_llm_unavailable_when_broken(self):
        # Column points at a row whose secrets have been cleared.
        broken_llm = self._make_llm(
            provider_class_path="some.unregistered.Provider",
            model_id="x",
            display_name="broken",
        )
        column = self._make_column(preferred_llm=broken_llm)

        with self.assertRaises(LLMUnavailableError) as ctx:
            resolve_extract_llm(column=column)
        # MUST be llm_unavailable (loud failure), NOT
        # llm_not_configured (legacy fallback) — explicit picks should
        # not be silently substituted.
        self.assertEqual(ctx.exception.failure_mode, FAILURE_MODE_UNAVAILABLE)

    def test_no_column_no_default_raises_llm_not_configured(self):
        # Singleton default is unset; column has no preferred_llm.
        column = self._make_column()
        with self.assertRaises(LLMUnavailableError) as ctx:
            resolve_extract_llm(column=column)
        self.assertEqual(ctx.exception.failure_mode, FAILURE_MODE_NOT_CONFIGURED)

    def test_no_column_argument_at_all_falls_back_to_default(self):
        # Pre-Phase-4 callers (don't pass column=) still work.
        default_llm = self._make_llm()
        self.settings.default_extract_llm = default_llm
        self.settings.save()
        cache.delete(LLMSettings.CACHE_KEY)
        resolved = resolve_extract_llm()
        self.assertEqual(resolved.registered_llm_id, default_llm.pk)


class ColumnGraphQLPickerTests(_Phase4Base):
    QUERY = """
        query($id: ID!) {
            node(id: $id) {
                ... on ColumnType {
                    id
                    preferredLlm { id modelId displayName }
                    availableLlms { id displayName isResolvable }
                }
            }
        }
    """

    def setUp(self) -> None:
        super().setUp()
        self.client = Client(schema, context_value=_Context(self.user))

    def test_preferred_llm_resolved(self):
        rl = self._make_llm()
        column = self._make_column(preferred_llm=rl)
        global_id = to_global_id("ColumnType", column.pk)
        result = self.client.execute(self.QUERY, variables={"id": global_id})
        self.assertNotIn("errors", result, msg=result)
        payload = result["data"]["node"]
        self.assertEqual(payload["preferredLlm"]["id"], str(rl.pk))
        self.assertEqual(payload["preferredLlm"]["modelId"], "gpt-4o-mini")

    def test_available_llms_returns_selectable_only(self):
        # Mix of selectable + non-selectable.
        self._make_llm(display_name="ok")
        self._make_llm(display_name="archived", is_archived=True)
        self._make_llm(display_name="disabled", is_enabled=False)
        v1 = self._make_llm(display_name="v1")
        # Supersede v1.
        self._make_llm(display_name="v2", previous_version=v1, model_id="gpt-4o")

        column = self._make_column()
        global_id = to_global_id("ColumnType", column.pk)
        result = self.client.execute(self.QUERY, variables={"id": global_id})
        self.assertNotIn("errors", result, msg=result)
        names = {row["displayName"] for row in result["data"]["node"]["availableLlms"]}
        self.assertIn("ok", names)
        self.assertIn("v2", names)
        self.assertNotIn("archived", names)
        self.assertNotIn("disabled", names)
        self.assertNotIn("v1", names)


class CreateColumnMutationTests(_Phase4Base):
    QUERY = """
        mutation($fs: ID!, $name: String!, $output: String!, $llm: ID) {
            createColumn(
                fieldsetId: $fs,
                name: $name,
                outputType: $output,
                query: "Q",
                preferredLlmId: $llm,
            ) {
                ok
                message
                obj { id preferredLlm { id displayName } }
            }
        }
    """

    def setUp(self) -> None:
        super().setUp()
        self.client = Client(schema, context_value=_Context(self.user))

    def _exec(self, **vars):
        vars.setdefault("fs", to_global_id("FieldsetType", self.fieldset.pk))
        vars.setdefault("name", "c")
        vars.setdefault("output", "str")
        return self.client.execute(self.QUERY, variables=vars)

    def test_creates_with_preferred_llm(self):
        rl = self._make_llm()
        result = self._exec(llm=str(rl.pk))
        payload = result["data"]["createColumn"]
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["obj"]["preferredLlm"]["id"], str(rl.pk))

    def test_creates_without_preferred_llm(self):
        result = self._exec()
        payload = result["data"]["createColumn"]
        self.assertTrue(payload["ok"])
        self.assertIsNone(payload["obj"]["preferredLlm"])

    def test_rejects_archived_target(self):
        rl = self._make_llm(is_archived=True)
        result = self._exec(llm=str(rl.pk))
        # Mutation surfaces validation errors via the GraphQL errors
        # array (it raises ValueError, not returning a structured ok
        # payload, which graphene catches and reports).
        self.assertIn("errors", result, msg=result)

    def test_rejects_disabled_target(self):
        rl = self._make_llm(is_enabled=False)
        result = self._exec(llm=str(rl.pk))
        self.assertIn("errors", result, msg=result)

    def test_rejects_non_head_target(self):
        v1 = self._make_llm(display_name="v1")
        self._make_llm(display_name="v2", previous_version=v1, model_id="gpt-4o")
        result = self._exec(llm=str(v1.pk))
        self.assertIn("errors", result, msg=result)


class UpdateColumnMutationTests(_Phase4Base):
    QUERY = """
        mutation($id: ID!, $llm: ID) {
            updateColumnMutation(id: $id, preferredLlmId: $llm) {
                ok
                message
                obj { id preferredLlm { id displayName } }
            }
        }
    """

    def setUp(self) -> None:
        super().setUp()
        self.client = Client(schema, context_value=_Context(self.user))

    def test_sets_preferred_llm(self):
        rl = self._make_llm()
        column = self._make_column()
        global_id = to_global_id("ColumnType", column.pk)
        result = self.client.execute(
            self.QUERY, variables={"id": global_id, "llm": str(rl.pk)}
        )
        payload = result["data"]["updateColumnMutation"]
        self.assertTrue(payload["ok"], msg=payload)
        column.refresh_from_db()
        self.assertEqual(column.preferred_llm_id, rl.pk)

    def test_clears_preferred_llm_with_zero_sentinel(self):
        rl = self._make_llm()
        column = self._make_column(preferred_llm=rl)
        global_id = to_global_id("ColumnType", column.pk)
        result = self.client.execute(
            self.QUERY, variables={"id": global_id, "llm": "0"}
        )
        payload = result["data"]["updateColumnMutation"]
        self.assertTrue(payload["ok"], msg=payload)
        column.refresh_from_db()
        self.assertIsNone(column.preferred_llm_id)


class DatacellExecutedLLMGraphQLTests(_Phase4Base):
    """Covers the new ``DatacellType.executed_llm`` resolver."""

    QUERY = """
        query($id: ID!) {
            node(id: $id) {
                ... on DatacellType {
                    id
                    executedLlm { id modelId displayName }
                }
            }
        }
    """

    def setUp(self) -> None:
        super().setUp()
        self.client = Client(schema, context_value=_Context(self.user))

    def test_executed_llm_resolves(self):
        rl = self._make_llm()
        column = self._make_column()
        # Minimum legal Datacell — has only the FKs that data_extract
        # actually requires.
        from opencontractserver.documents.models import Document

        document = Document.objects.create(
            title="doc1",
            description="x",
            creator=self.user,
        )
        cell = Datacell.objects.create(
            column=column,
            document=document,
            data_definition="x",
            executed_llm=rl,
            creator=self.user,
        )
        global_id = to_global_id("DatacellType", cell.pk)
        result = self.client.execute(self.QUERY, variables={"id": global_id})
        self.assertNotIn("errors", result, msg=result)
        payload = result["data"]["node"]
        self.assertEqual(payload["executedLlm"]["id"], str(rl.pk))
        self.assertEqual(payload["executedLlm"]["modelId"], "gpt-4o-mini")

    def test_executed_llm_null_when_unset(self):
        from opencontractserver.documents.models import Document

        column = self._make_column()
        document = Document.objects.create(
            title="doc1",
            description="x",
            creator=self.user,
        )
        cell = Datacell.objects.create(
            column=column,
            document=document,
            data_definition="x",
            creator=self.user,
        )
        global_id = to_global_id("DatacellType", cell.pk)
        result = self.client.execute(self.QUERY, variables={"id": global_id})
        self.assertNotIn("errors", result, msg=result)
        self.assertIsNone(result["data"]["node"]["executedLlm"])
