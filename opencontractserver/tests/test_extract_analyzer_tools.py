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
from django.test import TestCase, TransactionTestCase, override_settings

from opencontractserver.analyzer.models import Analysis, Analyzer
from opencontractserver.corpuses.models import (
    CorpusAction,
    CorpusActionTrigger,
)
from opencontractserver.documents.models import Document
from opencontractserver.extracts.models import Column, Extract, Fieldset
from opencontractserver.llms.exceptions import ToolConfirmationRequired
from opencontractserver.llms.tools.core_tools.extracts_and_analyzers import (
    _clamp_limit,
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
from opencontractserver.tests.base import TransactionFixtureTestCase
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()


# =========================================================================== #
# Helpers
# =========================================================================== #


def _make_fieldset(
    *,
    name: str,
    user,
    with_column: bool = True,
    manual_entry_only: bool = False,
) -> Fieldset:
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
            is_manual_entry=manual_entry_only,
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
# Internal helpers
# =========================================================================== #


@pytest.mark.parametrize(
    "limit,default,expected",
    [
        (None, 20, 20),
        (0, 20, 20),
        (-5, 20, 20),
        (5, 20, 5),
        (150, 20, 100),  # capped at MAX_LIST_LIMIT=100
        ("bad", 20, 20),
        ("7", 20, 7),  # numeric strings are accepted
    ],
)
def test_clamp_limit(limit, default, expected):
    """A misbehaving LLM can pass 0, negative, oversized, or non-numeric limits."""
    assert _clamp_limit(limit, default) == expected


# =========================================================================== #
# Registry integration
# =========================================================================== #


class TestExtractAnalyzerRegistryIntegration(TestCase):
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
class TestListFieldsets(TransactionFixtureTestCase):
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
        # Default discovery payload is the slim summary — the agent gets
        # column names but not the long-form ``query``/``instructions``
        # body, which can be many KB per fieldset.
        results = list_fieldsets(corpus_id=self.corpus.id, user_id=self.user.id)
        mine = next(r for r in results if r["name"] == "Mine")
        self.assertEqual(mine["column_count"], 1)
        self.assertEqual(mine["column_names"], ["Mine col"])
        self.assertNotIn("columns", mine)

        # Asking for the full payload returns the heavy detail inline.
        detailed = list_fieldsets(
            corpus_id=self.corpus.id,
            user_id=self.user.id,
            include_columns=True,
        )
        mine_detailed = next(r for r in detailed if r["name"] == "Mine")
        self.assertEqual(mine_detailed["columns"][0]["query"], "What is the answer?")
        self.assertEqual(mine_detailed["columns"][0]["output_type"], "str")
        self.assertNotIn("column_names", mine_detailed)

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

    def test_limit_caps_returned_row_count(self):
        """The ``limit`` parameter clamps how many fieldsets are returned.

        ``_clamp_limit`` has unit tests for value normalisation; this
        exercises the end-to-end path so a future regression that
        clamps but forgets to apply the slice gets caught.
        """
        # Two visible fieldsets exist in setUp ("Mine" + "Public"). Asking
        # for ``limit=1`` must surface exactly one of them.
        results = list_fieldsets(
            corpus_id=self.corpus.id, user_id=self.user.id, limit=1
        )
        self.assertEqual(len(results), 1)


@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
class TestListAnalyzers(TransactionFixtureTestCase):
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

    def test_oversized_input_schema_is_truncated(self):
        """Listing tool replaces unbounded analyzer ``input_schema``
        payloads with a placeholder so a misbehaving analyzer can't
        inflate every LLM call's context window."""

        from opencontractserver.constants.tools import (
            ANALYZER_INPUT_SCHEMA_MAX_INLINE_CHARS,
        )

        # A small schema rides through unchanged so the negative case
        # alone wouldn't prove the cap is conditional rather than
        # always-on.
        self.analyzer_mine.input_schema = {"type": "object", "properties": {}}
        self.analyzer_mine.save()

        # An oversized schema (just past the cap) gets the truncation
        # placeholder.
        huge_payload = {f"k_{i}": "x" * 100 for i in range(60)}
        self.analyzer_public.input_schema = huge_payload
        self.analyzer_public.save()

        results = {
            r["id"]: r
            for r in list_analyzers(corpus_id=self.corpus.id, user_id=self.user.id)
        }

        small = results["mine.analyzer"]["input_schema"]
        self.assertEqual(small, {"type": "object", "properties": {}})

        large = results["public.analyzer"]["input_schema"]
        self.assertIsInstance(large, dict)
        self.assertTrue(large.get("_truncated"))
        self.assertIn(
            str(ANALYZER_INPUT_SCHEMA_MAX_INLINE_CHARS),
            large.get("_reason", ""),
        )

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

    def test_limit_caps_returned_row_count(self):
        """The ``limit`` parameter clamps how many analyzers are returned."""
        # setUp creates two visible analyzers ("mine.analyzer",
        # "public.analyzer"). ``limit=1`` must surface exactly one.
        results = list_analyzers(
            corpus_id=self.corpus.id, user_id=self.user.id, limit=1
        )
        self.assertEqual(len(results), 1)


# =========================================================================== #
# Recent listings
# =========================================================================== #


@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
class TestListRecentExtracts(TransactionFixtureTestCase):
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

    def test_status_transitions(self):
        """All four ``_extract_status`` branches map to the right vocabulary.

        ``Extract`` has no ``status`` column — the agent-surface status
        is synthesised from ``started`` / ``finished`` / ``error``.
        Pre-existing coverage only pinned the default ``queued`` case;
        the other three are derived in exactly the same place so a typo
        in any one branch would silently misreport completion to a
        polling LLM. Mirrors ``TestListRecentAnalyses.test_status_is_normalised_lowercase``.
        """

        from django.utils import timezone

        from opencontractserver.constants.tools import (
            EXTRACT_STATUS_COMPLETED,
            EXTRACT_STATUS_FAILED,
            EXTRACT_STATUS_QUEUED,
            EXTRACT_STATUS_RUNNING,
        )

        # error > finished > started > queued — the branch order matters
        # because a failed extract is by definition both started and
        # finished, but the agent should see ``failed`` rather than
        # ``completed``.
        now = timezone.now()

        cases: list[tuple[dict, str]] = [
            ({"started": None, "finished": None, "error": ""}, EXTRACT_STATUS_QUEUED),
            ({"started": now, "finished": None, "error": ""}, EXTRACT_STATUS_RUNNING),
            (
                {"started": now, "finished": now, "error": ""},
                EXTRACT_STATUS_COMPLETED,
            ),
            (
                {"started": now, "finished": now, "error": "boom"},
                EXTRACT_STATUS_FAILED,
            ),
        ]

        for fields, expected in cases:
            self.extract_visible.started = fields["started"]
            self.extract_visible.finished = fields["finished"]
            self.extract_visible.error = fields["error"]
            self.extract_visible.save()

            results = list_recent_extracts(
                corpus_id=self.corpus.id, user_id=self.user.id
            )
            entry = next(r for r in results if r["name"] == "Visible Extract")
            self.assertEqual(
                entry["status"],
                expected,
                f"Expected status {expected!r} for fields {fields}, "
                f"got {entry['status']!r}",
            )

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
class TestListRecentAnalyses(TransactionFixtureTestCase):
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

    def test_status_is_normalised_lowercase(self):
        """The listing emits the same lowercase status vocabulary that
        ``start_analysis`` returns immediately after dispatch.

        Pre-fix the listing returned ``analysis.status`` verbatim
        (``"QUEUED"`` from ``JobStatus.QUEUED.value``) while
        ``start_analysis`` returned ``"queued"`` (the Extract constant).
        An LLM polling the listing right after dispatch saw the status
        appear to change without anything having happened.
        """

        from opencontractserver.types.enums import JobStatus

        # Force a deterministic status on the visible analysis so the
        # test doesn't depend on the post_save signal ordering.
        self.analysis_visible.status = JobStatus.RUNNING.value
        self.analysis_visible.save()

        results = list_recent_analyses(corpus_id=self.corpus.id, user_id=self.user.id)
        visible = next(r for r in results if r["id"] == self.analysis_visible.id)
        self.assertEqual(
            visible["status"],
            "running",
            "Listing must normalise model statuses to lowercase to match "
            "start_analysis's return vocabulary.",
        )

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
class TestStartExtract(TransactionFixtureTestCase):
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
            set(self.corpus._get_active_documents().values_list("id", flat=True)),
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
        with self.assertRaisesRegex(PermissionError, "authenticated user"):
            start_extract(
                corpus_id=self.corpus.id,
                fieldset_id=self.fieldset.id,
                user_id=None,  # type: ignore[arg-type]
            )

    def test_nonexistent_user_id_distinguished_from_unauthenticated(self):
        with self.assertRaisesRegex(PermissionError, "not found"):
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

    def test_manual_entry_only_fieldset_raises(self):
        manual_fs = _make_fieldset(
            name="ManualOnly", user=self.user, manual_entry_only=True
        )
        with self.assertRaises(ValueError):
            start_extract(
                corpus_id=self.corpus.id,
                fieldset_id=manual_fs.id,
                user_id=self.user.id,
            )

    def test_listing_shows_zero_columns_then_start_rejects(self):
        """``list_fieldsets`` surfaces auto-column count, ``start_extract`` enforces it.

        A fieldset whose only columns are ``is_manual_entry=True`` shows up
        in discovery with ``column_count=0`` (the listing prefetch filters
        them out) and an ``extractable=False`` flag so the LLM knows
        ``start_extract`` will reject it. ``start_extract`` raises
        ValueError. Documents the deliberate two-step contract: agents can
        see "empty" fieldsets but cannot dispatch them, and the listing
        tool surfaces that constraint up-front rather than only at dispatch.
        """
        manual_only = _make_fieldset(
            name="DiscoveryOnly", user=self.user, manual_entry_only=True
        )

        results = list_fieldsets(corpus_id=self.corpus.id, user_id=self.user.id)
        listed = next(r for r in results if r["id"] == manual_only.id)
        self.assertEqual(listed["column_count"], 0)
        self.assertEqual(listed["column_names"], [])
        self.assertFalse(
            listed["extractable"],
            "Zero-column fieldsets must be flagged extractable=False so the "
            "LLM can avoid an obvious failing dispatch.",
        )

        # A dispatchable fieldset must report extractable=True so the
        # flag is actually informative (the negative case alone would
        # leave the LLM unable to distinguish "no info" from "rejected").
        dispatchable = next(r for r in results if r["id"] == self.fieldset.id)
        self.assertTrue(dispatchable["extractable"])
        self.assertGreater(dispatchable["column_count"], 0)

        with self.assertRaises(ValueError):
            start_extract(
                corpus_id=self.corpus.id,
                fieldset_id=manual_only.id,
                user_id=self.user.id,
            )

    def test_doc_agent_outside_corpus_raises_value_error(self):
        # A document agent whose injected document_id is not a member of
        # the working corpus must fail loudly. Silently broadening scope
        # to the full corpus would let a single-doc agent dispatch a
        # corpus-wide run (potentially thousands of docs) without the
        # LLM realising — both an over-billing risk and a confusing
        # scope-leakage surprise for the user.
        outside_doc = Document.objects.create(
            title="Outside doc", creator=self.user, backend_lock=False
        )
        with self._patch_dispatch():
            with self.assertRaisesRegex(ValueError, r"is not part of corpus"):
                start_extract(
                    corpus_id=self.corpus.id,
                    fieldset_id=self.fieldset.id,
                    user_id=self.user.id,
                    document_id=outside_doc.id,
                )

    def test_cross_corpus_action_id_is_ignored(self):
        # A CorpusAction belonging to a different corpus must not be linked.
        from opencontractserver.corpuses.models import Corpus

        other_corpus = Corpus.objects.create(
            title="Other", creator=self.user, backend_lock=False
        )
        cross_action = CorpusAction.objects.create(
            corpus=other_corpus,
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
                corpus_action_id=cross_action.id,
            )

        extract = Extract.objects.get(pk=result["extract_id"])
        self.assertIsNone(extract.corpus_action_id)
        self.assertIsNone(result["corpus_action_id"])

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
class TestStartAnalysis(TransactionFixtureTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.analyzer = _make_task_analyzer(user=self.user)
        self.other_user = User.objects.create_user(username="other_user", password="pw")

    def _patch_process_analyzer(self):
        """Stub process_analyzer to avoid hitting real Celery tasks.

        ``start_analysis`` imports ``process_analyzer`` at module load time,
        so we patch it at the import site
        (``opencontractserver.llms.tools.core_tools.extracts_and_analyzers.process_analyzer``)
        rather than at its definition in ``corpus_tasks``. That is the
        correct Python mock target for an already-imported function.
        """

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
            "opencontractserver.llms.tools.core_tools."
            "extracts_and_analyzers.process_analyzer",
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
        expected_ids = sorted(
            self.corpus._get_active_documents().values_list("id", flat=True)
        )
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

    def test_corpus_action_id_links_analysis(self):
        action = CorpusAction.objects.create(
            corpus=self.corpus,
            analyzer=self.analyzer,
            creator=self.user,
            trigger=CorpusActionTrigger.ADD_DOCUMENT,
        )
        with self._patch_process_analyzer():
            result = start_analysis(
                corpus_id=self.corpus.id,
                analyzer_id=self.analyzer.id,
                user_id=self.user.id,
                corpus_action_id=action.id,
            )

        analysis = Analysis.objects.get(pk=result["analysis_id"])
        self.assertEqual(analysis.corpus_action_id, action.id)
        self.assertEqual(result["corpus_action_id"], action.id)

    def test_cross_corpus_action_id_is_ignored(self):
        from opencontractserver.corpuses.models import Corpus

        other_corpus = Corpus.objects.create(
            title="Other", creator=self.user, backend_lock=False
        )
        cross_action = CorpusAction.objects.create(
            corpus=other_corpus,
            analyzer=self.analyzer,
            creator=self.user,
            trigger=CorpusActionTrigger.ADD_DOCUMENT,
        )
        with self._patch_process_analyzer():
            result = start_analysis(
                corpus_id=self.corpus.id,
                analyzer_id=self.analyzer.id,
                user_id=self.user.id,
                corpus_action_id=cross_action.id,
            )

        analysis = Analysis.objects.get(pk=result["analysis_id"])
        self.assertIsNone(analysis.corpus_action_id)
        self.assertIsNone(result["corpus_action_id"])

    async def test_async_variant_dispatches(self):
        with self._patch_process_analyzer():
            result = await astart_analysis(
                corpus_id=self.corpus.id,
                analyzer_id=self.analyzer.id,
                user_id=self.user.id,
            )
        self.assertEqual(result["status"], "queued")

    def test_reserved_input_data_keys_are_stripped(self):
        """Adversarial keys cannot tunnel internal kwargs into the task.

        ``run_task_name_analyzer`` spreads ``analysis_input_data`` into the
        analyzer task call. A payload crafted to override
        ``analysis_id`` / ``user_id`` / scoping IDs would shadow the
        framework's own arguments — a privilege-escalation surface
        unique to the agent path (the human GraphQL path doesn't
        accept arbitrary input data from the client). The tool strips
        the reserved key set before dispatch and logs a warning.
        """

        with self._patch_process_analyzer() as mock_process:
            with self.assertLogs(
                "opencontractserver.llms.tools.core_tools.extracts_and_analyzers",
                level="WARNING",
            ) as logs:
                start_analysis(
                    corpus_id=self.corpus.id,
                    analyzer_id=self.analyzer.id,
                    user_id=self.user.id,
                    analysis_input_data={
                        "analysis_id": 999_999,  # reserved
                        "user_id": 0,  # reserved
                        "corpus_id": -1,  # reserved
                        "min_score": 0.7,  # legitimate analyzer param
                    },
                )

        passed_payload = mock_process.call_args.kwargs["analysis_input_data"]
        self.assertNotIn("analysis_id", passed_payload)
        self.assertNotIn("user_id", passed_payload)
        self.assertNotIn("corpus_id", passed_payload)
        # Legitimate analyzer parameters survive the strip.
        self.assertEqual(passed_payload.get("min_score"), 0.7)
        # The strip is observable so production traces can flag attempts.
        self.assertTrue(
            any("stripped reserved keys" in line for line in logs.output),
            f"Expected strip warning, got: {logs.output}",
        )

    def test_safe_input_data_passes_through_unchanged(self):
        """No reserved keys → payload is forwarded verbatim (no false strip)."""

        legitimate_payload = {"min_score": 0.5, "deep_scan": True}
        with self._patch_process_analyzer() as mock_process:
            start_analysis(
                corpus_id=self.corpus.id,
                analyzer_id=self.analyzer.id,
                user_id=self.user.id,
                analysis_input_data=dict(legitimate_payload),
            )
        self.assertEqual(
            mock_process.call_args.kwargs["analysis_input_data"],
            legitimate_payload,
        )


# =========================================================================== #
# Approval gate integration
# =========================================================================== #


@pytest.mark.django_db
class TestApprovalGate(TransactionTestCase):
    """Confirm that the PydanticAIToolWrapper fires the approval gate.

    Async methods need ``@pytest.mark.asyncio`` individually rather than at
    the class level: stacking the asyncio marker on a Django
    ``TransactionTestCase`` confuses pytest-django's collector (it tries to
    drive the test as a pytest-native coroutine while the base class wants
    to run it through Django's sync test loop). Method-level markers keep
    the existing Django setUp/tearDown semantics intact.
    """

    @pytest.mark.asyncio
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

    @pytest.mark.asyncio
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

    @pytest.mark.asyncio
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
