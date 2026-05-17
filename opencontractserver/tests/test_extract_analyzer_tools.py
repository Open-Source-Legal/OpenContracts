"""Tests for the extract & analyzer agent tools.

Covers the six new tools in
``opencontractserver.llms.tools.core_tools.extracts_and_analyzers``:

* ``list_fieldsets`` / ``alist_fieldsets``
* ``start_extract`` / ``astart_extract``
* ``list_recent_extracts`` / ``alist_recent_extracts``
* ``list_analyzers`` / ``alist_analyzers``
* ``start_analysis`` / ``astart_analysis``
* ``list_recent_analyses`` / ``alist_recent_analyses``

Validates permission gating, document-scope resolution, dispatch behaviour,
registry integration, and that the approval gate fires on the
``PydanticAIToolWrapper``.
"""

from __future__ import annotations

import inspect
from unittest.mock import MagicMock, patch

import pytest
from asgiref.sync import sync_to_async
from django.contrib.auth import get_user_model
from django.test import TransactionTestCase, override_settings

from opencontractserver.analyzer.models import Analysis, Analyzer
from opencontractserver.corpuses.models import (
    CorpusAction,
    CorpusActionTrigger,
)
from opencontractserver.documents.models import Document
from opencontractserver.extracts.models import Column, Extract, Fieldset
from opencontractserver.llms.exceptions import ToolConfirmationRequired
from opencontractserver.llms.tools.core_tools.extracts_and_analyzers import (
    alist_analyzers,
    alist_fieldsets,
    alist_recent_analyses,
    alist_recent_extracts,
    astart_analysis,
    astart_extract,
    list_analyzers,
    list_fieldsets,
    list_recent_analyses,
    list_recent_extracts,
    start_analysis,
    start_extract,
)
from opencontractserver.llms.tools.pydantic_ai_tools import (
    PydanticAIDependencies,
    PydanticAIToolWrapper,
)
from opencontractserver.llms.tools.tool_registry import ToolFunctionRegistry
from opencontractserver.tests.base import BaseFixtureTestCase
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()


# =========================================================================== #
# Helpers
# =========================================================================== #


def _make_fieldset(*, name: str, user, with_column: bool = True) -> Fieldset:
    fieldset = Fieldset.objects.create(
        name=name,
        description=f"{name} description",
        creator=user,
    )
    set_permissions_for_obj_to_user(user, fieldset, [PermissionTypes.CRUD])
    if with_column:
        col = Column.objects.create(
            fieldset=fieldset,
            name=f"{name} col",
            query="What is the answer?",
            output_type="str",
            creator=user,
        )
        set_permissions_for_obj_to_user(user, col, [PermissionTypes.CRUD])
    return fieldset


def _make_task_analyzer(*, user, analyzer_id: str = "noop.analyzer") -> Analyzer:
    analyzer = Analyzer.objects.create(
        id=analyzer_id,
        description="Test task-based analyzer",
        creator=user,
        task_name=f"tests.noop.{analyzer_id}",
    )
    set_permissions_for_obj_to_user(user, analyzer, [PermissionTypes.CRUD])
    return analyzer


# =========================================================================== #
# Registry integration
# =========================================================================== #


@pytest.mark.django_db
class TestExtractAnalyzerRegistryIntegration(TransactionTestCase):
    """All six tools resolve via ToolFunctionRegistry, with the expected flags."""

    EXPECTED_TOOLS = {
        "list_fieldsets": {"approval": False, "write": False, "corpus": True},
        "start_extract": {"approval": True, "write": True, "corpus": True},
        "list_recent_extracts": {"approval": False, "write": False, "corpus": True},
        "list_analyzers": {"approval": False, "write": False, "corpus": True},
        "start_analysis": {"approval": True, "write": True, "corpus": True},
        "list_recent_analyses": {"approval": False, "write": False, "corpus": True},
    }

    def test_tools_registered_with_correct_flags(self):
        registry = ToolFunctionRegistry.get()
        for name, flags in self.EXPECTED_TOOLS.items():
            entry = registry.resolve(name)
            self.assertIsNotNone(entry, f"Tool {name!r} not in registry")
            assert entry is not None  # for type checker
            self.assertEqual(
                entry.definition.requires_approval,
                flags["approval"],
                f"{name} approval flag mismatch",
            )
            self.assertEqual(
                entry.definition.requires_write_permission,
                flags["write"],
                f"{name} write flag mismatch",
            )
            self.assertEqual(
                entry.definition.requires_corpus,
                flags["corpus"],
                f"{name} corpus flag mismatch",
            )

    def test_to_core_tool_returns_async_function(self):
        registry = ToolFunctionRegistry.get()
        for name in self.EXPECTED_TOOLS:
            core_tool = registry.to_core_tool(name)
            self.assertIsNotNone(core_tool, f"to_core_tool({name!r}) returned None")
            assert core_tool is not None
            self.assertTrue(
                inspect.iscoroutinefunction(core_tool.function),
                f"Tool {name!r} async_func must be async",
            )


# =========================================================================== #
# Discovery tools
# =========================================================================== #


@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
class TestListFieldsets(BaseFixtureTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.other_user = User.objects.create_user(username="other_user", password="pw")

        # Fieldset visible to self.user (creator)
        self.fieldset_mine = _make_fieldset(name="Mine", user=self.user)

        # Fieldset created by other user, not shared - invisible to self.user
        self.fieldset_other = _make_fieldset(name="Other", user=self.other_user)

        # Public fieldset by other user - visible to self.user
        self.fieldset_public = _make_fieldset(name="Public", user=self.other_user)
        self.fieldset_public.is_public = True
        self.fieldset_public.save()

    def test_returns_only_visible_fieldsets(self):
        results = list_fieldsets(corpus_id=self.corpus.id, user_id=self.user.id)
        names = {r["name"] for r in results}
        self.assertIn("Mine", names)
        self.assertIn("Public", names)
        self.assertNotIn("Other", names)

    def test_returns_columns_with_metadata(self):
        results = list_fieldsets(corpus_id=self.corpus.id, user_id=self.user.id)
        mine = next(r for r in results if r["name"] == "Mine")
        self.assertEqual(mine["column_count"], 1)
        self.assertEqual(mine["columns"][0]["query"], "What is the answer?")
        self.assertEqual(mine["columns"][0]["output_type"], "str")

    def test_skips_fieldsets_pinned_to_other_corpus(self):
        # Pin "Mine" to a different corpus as its metadata schema
        from opencontractserver.corpuses.models import Corpus

        other_corpus = Corpus.objects.create(
            title="Other Corpus", creator=self.user, backend_lock=False
        )
        self.fieldset_mine.corpus = other_corpus
        self.fieldset_mine.save()

        results = list_fieldsets(corpus_id=self.corpus.id, user_id=self.user.id)
        names = {r["name"] for r in results}
        self.assertNotIn("Mine", names)

    def test_unknown_corpus_raises_value_error(self):
        with self.assertRaises(ValueError):
            list_fieldsets(corpus_id=999_999_999, user_id=self.user.id)

    async def test_async_variant_matches(self):
        # ``list_fieldsets`` is sync and touches the ORM, so it must be
        # called via ``sync_to_async`` from an async test method to avoid
        # ``SynchronousOnlyOperation``.
        sync_result = await sync_to_async(list_fieldsets, thread_sensitive=False)(
            corpus_id=self.corpus.id, user_id=self.user.id
        )
        async_result = await alist_fieldsets(
            corpus_id=self.corpus.id, user_id=self.user.id
        )
        self.assertEqual(
            {r["name"] for r in sync_result},
            {r["name"] for r in async_result},
        )


@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
class TestListAnalyzers(BaseFixtureTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.other_user = User.objects.create_user(username="other_user", password="pw")

        self.analyzer_mine = _make_task_analyzer(
            user=self.user, analyzer_id="mine.analyzer"
        )

        self.analyzer_public = _make_task_analyzer(
            user=self.other_user, analyzer_id="public.analyzer"
        )
        self.analyzer_public.is_public = True
        self.analyzer_public.save()

        self.analyzer_disabled = _make_task_analyzer(
            user=self.user, analyzer_id="disabled.analyzer"
        )
        self.analyzer_disabled.disabled = True
        self.analyzer_disabled.save()

        self.analyzer_other = _make_task_analyzer(
            user=self.other_user, analyzer_id="other.analyzer"
        )

    def test_returns_visible_non_disabled_analyzers(self):
        results = list_analyzers(corpus_id=self.corpus.id, user_id=self.user.id)
        ids = {r["id"] for r in results}
        self.assertIn("mine.analyzer", ids)
        self.assertIn("public.analyzer", ids)
        self.assertNotIn("disabled.analyzer", ids)
        self.assertNotIn("other.analyzer", ids)

    async def test_async_variant_matches(self):
        sync_ids = {
            r["id"]
            for r in await sync_to_async(list_analyzers, thread_sensitive=False)(
                corpus_id=self.corpus.id, user_id=self.user.id
            )
        }
        async_ids = {
            r["id"]
            for r in await alist_analyzers(
                corpus_id=self.corpus.id, user_id=self.user.id
            )
        }
        self.assertEqual(sync_ids, async_ids)


# =========================================================================== #
# Recent listings
# =========================================================================== #


@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
class TestListRecentExtracts(BaseFixtureTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.other_user = User.objects.create_user(username="other_user", password="pw")
        self.fieldset = _make_fieldset(name="FS", user=self.user)

        self.extract_visible = Extract.objects.create(
            corpus=self.corpus,
            name="Visible Extract",
            fieldset=self.fieldset,
            creator=self.user,
        )
        set_permissions_for_obj_to_user(
            self.user, self.extract_visible, [PermissionTypes.CRUD]
        )

        self.extract_other = Extract.objects.create(
            corpus=self.corpus,
            name="Other User Extract",
            fieldset=self.fieldset,
            creator=self.other_user,
        )
        set_permissions_for_obj_to_user(
            self.other_user, self.extract_other, [PermissionTypes.CRUD]
        )

    def test_visibility_filter(self):
        results = list_recent_extracts(corpus_id=self.corpus.id, user_id=self.user.id)
        names = {r["name"] for r in results}
        self.assertIn("Visible Extract", names)
        self.assertNotIn("Other User Extract", names)

    def test_status_field(self):
        results = list_recent_extracts(corpus_id=self.corpus.id, user_id=self.user.id)
        entry = next(r for r in results if r["name"] == "Visible Extract")
        self.assertEqual(entry["status"], "queued")

    async def test_async_variant_matches(self):
        sync_ids = {
            r["id"]
            for r in await sync_to_async(list_recent_extracts, thread_sensitive=False)(
                corpus_id=self.corpus.id, user_id=self.user.id
            )
        }
        async_ids = {
            r["id"]
            for r in await alist_recent_extracts(
                corpus_id=self.corpus.id, user_id=self.user.id
            )
        }
        self.assertEqual(sync_ids, async_ids)


@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
class TestListRecentAnalyses(BaseFixtureTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.other_user = User.objects.create_user(username="other_user", password="pw")
        self.analyzer = _make_task_analyzer(user=self.user)

        self.analysis_visible = Analysis.objects.create(
            analyzer=self.analyzer,
            analyzed_corpus=self.corpus,
            creator=self.user,
        )
        set_permissions_for_obj_to_user(
            self.user, self.analysis_visible, [PermissionTypes.CRUD]
        )

        self.analysis_other = Analysis.objects.create(
            analyzer=self.analyzer,
            analyzed_corpus=self.corpus,
            creator=self.other_user,
        )
        set_permissions_for_obj_to_user(
            self.other_user, self.analysis_other, [PermissionTypes.CRUD]
        )

    def test_visibility_filter(self):
        results = list_recent_analyses(corpus_id=self.corpus.id, user_id=self.user.id)
        ids = {r["id"] for r in results}
        self.assertIn(self.analysis_visible.id, ids)
        self.assertNotIn(self.analysis_other.id, ids)

    async def test_async_variant_matches(self):
        sync_ids = {
            r["id"]
            for r in await sync_to_async(list_recent_analyses, thread_sensitive=False)(
                corpus_id=self.corpus.id, user_id=self.user.id
            )
        }
        async_ids = {
            r["id"]
            for r in await alist_recent_analyses(
                corpus_id=self.corpus.id, user_id=self.user.id
            )
        }
        self.assertEqual(sync_ids, async_ids)


# =========================================================================== #
# start_extract
# =========================================================================== #


@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
class TestStartExtract(BaseFixtureTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.fieldset = _make_fieldset(name="FS", user=self.user)
        self.other_user = User.objects.create_user(username="other_user", password="pw")

    def _patch_dispatch(self):
        return patch(
            "opencontractserver.llms.tools.core_tools.extracts_and_analyzers."
            "run_extract"
        )

    def test_corpus_agent_scope_defaults_to_all_corpus_docs(self):
        with self._patch_dispatch() as mock_run:
            mock_run.s.return_value.apply_async.return_value = None
            result = start_extract(
                corpus_id=self.corpus.id,
                fieldset_id=self.fieldset.id,
                user_id=self.user.id,
            )

        extract = Extract.objects.get(pk=result["extract_id"])
        self.assertEqual(
            set(extract.documents.values_list("id", flat=True)),
            set(self.corpus.get_documents().values_list("id", flat=True)),
        )
        self.assertEqual(result["status"], "queued")
        self.assertEqual(result["fieldset_id"], self.fieldset.id)
        mock_run.s.assert_called_once()

    def test_doc_agent_scope_defaults_to_single_doc(self):
        with self._patch_dispatch() as mock_run:
            mock_run.s.return_value.apply_async.return_value = None
            result = start_extract(
                corpus_id=self.corpus.id,
                fieldset_id=self.fieldset.id,
                user_id=self.user.id,
                document_id=self.doc.id,
            )

        extract = Extract.objects.get(pk=result["extract_id"])
        self.assertEqual(
            list(extract.documents.values_list("id", flat=True)),
            [self.doc.id],
        )
        self.assertEqual(result["document_count"], 1)

    def test_requested_document_ids_intersect_with_corpus(self):
        outside_doc = Document.objects.create(
            title="Outside doc", creator=self.user, backend_lock=False
        )
        with self._patch_dispatch() as mock_run:
            mock_run.s.return_value.apply_async.return_value = None
            result = start_extract(
                corpus_id=self.corpus.id,
                fieldset_id=self.fieldset.id,
                user_id=self.user.id,
                document_ids=[self.doc.id, outside_doc.id],
            )

        extract = Extract.objects.get(pk=result["extract_id"])
        ids = set(extract.documents.values_list("id", flat=True))
        self.assertIn(self.doc.id, ids)
        self.assertNotIn(outside_doc.id, ids)

    def test_corpus_action_id_links_extract(self):
        action = CorpusAction.objects.create(
            corpus=self.corpus,
            fieldset=self.fieldset,
            creator=self.user,
            trigger=CorpusActionTrigger.ADD_DOCUMENT,
        )
        with self._patch_dispatch() as mock_run:
            mock_run.s.return_value.apply_async.return_value = None
            result = start_extract(
                corpus_id=self.corpus.id,
                fieldset_id=self.fieldset.id,
                user_id=self.user.id,
                corpus_action_id=action.id,
            )

        extract = Extract.objects.get(pk=result["extract_id"])
        self.assertEqual(extract.corpus_action_id, action.id)

    def test_user_must_be_authenticated(self):
        with self.assertRaises(PermissionError):
            start_extract(
                corpus_id=self.corpus.id,
                fieldset_id=self.fieldset.id,
                user_id=999_999_999,
            )

    def test_fieldset_not_visible_raises(self):
        private_fs = _make_fieldset(name="Private", user=self.other_user)
        with self.assertRaises(PermissionError):
            start_extract(
                corpus_id=self.corpus.id,
                fieldset_id=private_fs.id,
                user_id=self.user.id,
            )

    def test_corpus_without_update_perm_raises(self):
        # other_user has no perms on corpus
        with self.assertRaises(PermissionError):
            start_extract(
                corpus_id=self.corpus.id,
                fieldset_id=self.fieldset.id,
                user_id=self.other_user.id,
            )

    def test_fieldset_pinned_to_other_corpus_raises(self):
        from opencontractserver.corpuses.models import Corpus

        other_corpus = Corpus.objects.create(
            title="Schema Corpus", creator=self.user, backend_lock=False
        )
        self.fieldset.corpus = other_corpus
        self.fieldset.save()
        with self.assertRaises(PermissionError):
            start_extract(
                corpus_id=self.corpus.id,
                fieldset_id=self.fieldset.id,
                user_id=self.user.id,
            )

    def test_empty_fieldset_raises(self):
        empty_fs = _make_fieldset(name="Empty", user=self.user, with_column=False)
        with self.assertRaises(ValueError):
            start_extract(
                corpus_id=self.corpus.id,
                fieldset_id=empty_fs.id,
                user_id=self.user.id,
            )

    async def test_async_variant_dispatches(self):
        with self._patch_dispatch() as mock_run:
            mock_run.s.return_value.apply_async.return_value = None
            result = await astart_extract(
                corpus_id=self.corpus.id,
                fieldset_id=self.fieldset.id,
                user_id=self.user.id,
            )
        self.assertEqual(result["status"], "queued")


# =========================================================================== #
# start_analysis
# =========================================================================== #


@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
class TestStartAnalysis(BaseFixtureTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.analyzer = _make_task_analyzer(user=self.user)
        self.other_user = User.objects.create_user(username="other_user", password="pw")

    def _patch_process_analyzer(self):
        """Stub process_analyzer to avoid hitting real Celery tasks."""

        def fake_process_analyzer(
            user_id,
            analyzer,
            corpus_id,
            document_ids,
            corpus_action,
            analysis_input_data,
        ):
            analysis = Analysis.objects.create(
                analyzer=analyzer,
                analyzed_corpus_id=corpus_id,
                creator_id=user_id,
                corpus_action=corpus_action,
            )
            if document_ids:
                analysis.analyzed_documents.add(*document_ids)
            return analysis

        return patch(
            "opencontractserver.tasks.corpus_tasks.process_analyzer",
            side_effect=fake_process_analyzer,
        )

    def test_dispatches_via_process_analyzer(self):
        with self._patch_process_analyzer() as mock_process:
            result = start_analysis(
                corpus_id=self.corpus.id,
                analyzer_id=self.analyzer.id,
                user_id=self.user.id,
            )
        mock_process.assert_called_once()
        self.assertEqual(result["status"], "queued")
        self.assertEqual(result["analyzer_id"], self.analyzer.id)

    def test_doc_agent_scope_defaults_to_single_doc(self):
        with self._patch_process_analyzer() as mock_process:
            start_analysis(
                corpus_id=self.corpus.id,
                analyzer_id=self.analyzer.id,
                user_id=self.user.id,
                document_id=self.doc.id,
            )
        call_kwargs = mock_process.call_args.kwargs
        self.assertEqual(call_kwargs["document_ids"], [self.doc.id])

    def test_corpus_agent_scope_defaults_to_all_corpus_docs(self):
        expected_ids = sorted(self.corpus.get_documents().values_list("id", flat=True))
        with self._patch_process_analyzer() as mock_process:
            start_analysis(
                corpus_id=self.corpus.id,
                analyzer_id=self.analyzer.id,
                user_id=self.user.id,
            )
        call_kwargs = mock_process.call_args.kwargs
        self.assertEqual(sorted(call_kwargs["document_ids"]), expected_ids)

    def test_analyzer_not_visible_raises(self):
        private_analyzer = _make_task_analyzer(
            user=self.other_user, analyzer_id="hidden.analyzer"
        )
        with self.assertRaises(PermissionError):
            start_analysis(
                corpus_id=self.corpus.id,
                analyzer_id=private_analyzer.id,
                user_id=self.user.id,
            )

    def test_corpus_without_update_perm_raises(self):
        with self.assertRaises(PermissionError):
            start_analysis(
                corpus_id=self.corpus.id,
                analyzer_id=self.analyzer.id,
                user_id=self.other_user.id,
            )

    def test_disabled_analyzer_raises(self):
        self.analyzer.disabled = True
        self.analyzer.save()
        with self.assertRaises(ValueError):
            start_analysis(
                corpus_id=self.corpus.id,
                analyzer_id=self.analyzer.id,
                user_id=self.user.id,
            )

    def test_unknown_analyzer_raises_permission_error(self):
        with self.assertRaises(PermissionError):
            start_analysis(
                corpus_id=self.corpus.id,
                analyzer_id="does.not.exist",
                user_id=self.user.id,
            )

    async def test_async_variant_dispatches(self):
        with self._patch_process_analyzer():
            result = await astart_analysis(
                corpus_id=self.corpus.id,
                analyzer_id=self.analyzer.id,
                user_id=self.user.id,
            )
        self.assertEqual(result["status"], "queued")


# =========================================================================== #
# Approval gate integration
# =========================================================================== #


@pytest.mark.django_db
@pytest.mark.asyncio
class TestApprovalGate(TransactionTestCase):
    """Confirm that the PydanticAIToolWrapper fires the approval gate."""

    async def test_start_extract_requires_approval(self):
        registry = ToolFunctionRegistry.get()
        core_tool = registry.to_core_tool("start_extract")
        self.assertIsNotNone(core_tool)
        assert core_tool is not None
        self.assertTrue(core_tool.requires_approval)

        wrapper = PydanticAIToolWrapper(core_tool, inject_params={})
        callable_fn = wrapper.callable_function

        ctx = MagicMock()
        ctx.deps = PydanticAIDependencies(
            user_id=None, corpus_id=None, document_id=None, skip_approval_gate=False
        )
        ctx.tool_call_id = "test-call"

        # ``start_extract`` requires ``corpus_id``, ``fieldset_id``, and
        # ``user_id``; the wrapper inspects the underlying signature in
        # ``_maybe_raise`` and uses ``Signature.bind`` (not ``bind_partial``),
        # so all required kwargs must be supplied even though the test is
        # only checking that approval fires before execution.
        with self.assertRaises(ToolConfirmationRequired) as cm:
            await callable_fn(ctx, corpus_id=1, fieldset_id=1, user_id=1)
        self.assertEqual(cm.exception.tool_name, "start_extract")
        self.assertIn("fieldset_id", cm.exception.tool_args)

    async def test_start_analysis_requires_approval(self):
        registry = ToolFunctionRegistry.get()
        core_tool = registry.to_core_tool("start_analysis")
        self.assertIsNotNone(core_tool)
        assert core_tool is not None
        self.assertTrue(core_tool.requires_approval)

        wrapper = PydanticAIToolWrapper(core_tool, inject_params={})
        callable_fn = wrapper.callable_function

        ctx = MagicMock()
        ctx.deps = PydanticAIDependencies(
            user_id=None, corpus_id=None, document_id=None, skip_approval_gate=False
        )
        ctx.tool_call_id = "test-call"

        # ``start_analysis`` requires ``corpus_id``, ``analyzer_id``, and
        # ``user_id``; the wrapper inspects the underlying signature in
        # ``_maybe_raise`` and uses ``Signature.bind`` (not ``bind_partial``),
        # so all required kwargs must be supplied.
        with self.assertRaises(ToolConfirmationRequired) as cm:
            await callable_fn(ctx, corpus_id=1, analyzer_id="x.y", user_id=1)
        self.assertEqual(cm.exception.tool_name, "start_analysis")

    async def test_list_tools_do_not_require_approval(self):
        registry = ToolFunctionRegistry.get()
        for name in (
            "list_fieldsets",
            "list_analyzers",
            "list_recent_extracts",
            "list_recent_analyses",
        ):
            core_tool = registry.to_core_tool(name)
            self.assertIsNotNone(core_tool, f"{name} missing from registry")
            assert core_tool is not None
            self.assertFalse(
                core_tool.requires_approval,
                f"{name} should not require approval",
            )
