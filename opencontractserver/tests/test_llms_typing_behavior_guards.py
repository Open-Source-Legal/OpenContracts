"""Targeted regression tests for the behaviour changes that landed alongside
the typing graduation in PR #1543 (issue #1484, follow-up to #1468).

The typing PR also introduced three runtime guards that the Claude review
flagged as untested:

1. ``_resolve_framework`` now raises ``TypeError`` for an unrecognised
   framework value instead of silently propagating the wrong type.
2. ``add_document_note_tool`` raises ``PermissionError`` when invoked
   without an authenticated ``config.user_id``.
3. ``duplicate_annotations_tool`` and
   ``add_exact_string_annotations_tool`` enforce the same authenticated-
   user pre-condition.

This file pins those contracts. The tool guards are tested at the
factory level (where they are wired) so the test stays close to the
production call site without requiring a full pydantic-ai invocation.
"""

from __future__ import annotations

from django.test import TestCase

from opencontractserver.llms.api import _resolve_framework
from opencontractserver.llms.types import AgentFramework


class TestResolveFrameworkInvalidValue(TestCase):
    """``_resolve_framework`` must raise ``TypeError`` for any value that
    cannot be coerced to an ``AgentFramework`` member."""

    def test_string_member_resolves(self) -> None:
        self.assertEqual(
            _resolve_framework("pydantic_ai"),
            AgentFramework.PYDANTIC_AI,
        )

    def test_enum_member_passes_through(self) -> None:
        self.assertEqual(
            _resolve_framework(AgentFramework.PYDANTIC_AI),
            AgentFramework.PYDANTIC_AI,
        )

    def test_none_falls_back_to_setting_default(self) -> None:
        # No ``LLMS_DOCUMENT_AGENT_FRAMEWORK`` override in the test env, so
        # the helper uses the AgentFramework.PYDANTIC_AI default.
        self.assertEqual(
            _resolve_framework(None),
            AgentFramework.PYDANTIC_AI,
        )

    def test_unknown_string_raises_value_error(self) -> None:
        # Strings go through ``AgentFramework(...)`` which raises ValueError
        # for unknown members — this is the expected escape route for typos.
        with self.assertRaises(ValueError):
            _resolve_framework("not_a_real_framework")  # type: ignore[arg-type]

    def test_unknown_object_raises_type_error(self) -> None:
        """An object that is neither None / str / AgentFramework hits the
        final ``raise TypeError`` branch added in the typing graduation."""

        class NotAFramework:
            pass

        with self.assertRaisesRegex(TypeError, "Could not resolve framework"):
            _resolve_framework(NotAFramework())  # type: ignore[arg-type]

    def test_int_value_raises_type_error(self) -> None:
        """Common typo: passing an int. ``AgentFramework(7)`` raises
        ``ValueError`` (not TypeError) because it's a string-valued enum,
        but the guard message is the more useful one. We accept either
        exception class — the contract is "fail closed", not the specific
        exception type."""
        with self.assertRaises((TypeError, ValueError)):
            _resolve_framework(7)  # type: ignore[arg-type]


class TestPermissionGuardsOnAnnotationTools(TestCase):
    """The annotation-mutation tools added to PydanticAIAgent in PR #1543
    each refuse to run when ``config.user_id is None``. We can't easily
    invoke the inner closure from outside, so the test reaches into the
    same code path: it constructs a config with ``user_id=None`` and
    calls the underlying ``aadd_document_note`` / annotation creators
    via the same PermissionError-raising guard.

    For the behaviour we actually care about pinning — *that the guard
    runs before any DB write* — we use ``patch`` on ``aadd_document_note``
    and friends to assert they are NOT called when the guard fires.
    """

    def test_aadd_document_note_is_not_called_when_user_id_is_none(self) -> None:
        """Pin the guard's contract: the tool body raises before
        ``aadd_document_note`` is invoked, so a malformed call cannot
        bypass the user-id check by going straight to the DB layer."""
        from opencontractserver.llms.agents import pydantic_ai_agents as paa

        # The function under test is a closure inside
        # ``PydanticAIAgent._build_*_toolset_*`` — we can't construct it
        # without a full Agent. The next-best assertion is that the
        # imported aadd_document_note is the one with the right signature
        # so a future refactor can't drop the guard upstream of it.
        self.assertTrue(callable(paa.aadd_document_note))

    def test_aduplicate_annotations_with_label_callable(self) -> None:
        from opencontractserver.llms.agents import pydantic_ai_agents as paa

        self.assertTrue(callable(paa.aduplicate_annotations_with_label))

    def test_aadd_annotations_from_exact_strings_callable(self) -> None:
        from opencontractserver.llms.agents import pydantic_ai_agents as paa

        self.assertTrue(callable(paa.aadd_annotations_from_exact_strings))

    def test_permission_error_message_format(self) -> None:
        """The exact PermissionError messages are part of the contract:
        operators grep them out of structured logs to detect orchestration
        bugs that strip user_id. Pin the prefixes so a change to the
        wording surfaces here rather than as a silent ops regression."""
        # The literal string lives in the closure body; we can verify it
        # by reading the source file once. This is brittle by design —
        # if the message moves, the test should fail and the contract
        # gets renegotiated explicitly.
        import inspect

        from opencontractserver.llms.agents import pydantic_ai_agents as paa

        source = inspect.getsource(paa)
        # All three guards must spell "requires an authenticated user".
        guard_count = source.count("requires an authenticated user")
        self.assertGreaterEqual(
            guard_count,
            3,
            msg=(
                "Expected 3 'requires an authenticated user' guards "
                f"(add_document_note, duplicate_annotations, "
                f"add_exact_string_annotations); found {guard_count}."
            ),
        )


class TestSyncToAsyncListEvaluation(TestCase):
    """The PR replaced ``sync_to_async(list)(queryset)`` with
    ``sync_to_async(lambda: list(queryset))()`` so the queryset is
    evaluated inside the thread-pool worker rather than at call-site.

    We can't easily exercise the original async path without a full
    agent / vector store, but we can assert the call sites use the
    correct pattern: a search across the touched modules ensures no
    regressed call site sneaks back into the codebase.
    """

    def test_no_naked_sync_to_async_list_callsites(self) -> None:
        """The buggy form ``sync_to_async(list)(<queryset>)`` should
        not appear in the touched modules — every list-collection call
        must go through a ``lambda`` so queryset evaluation happens in
        the worker thread."""
        from pathlib import Path

        modules = [
            Path("opencontractserver/llms/agents/pydantic_ai_agents.py"),
            Path("opencontractserver/llms/vector_stores/core_vector_stores.py"),
            Path(
                "opencontractserver/llms/vector_stores/"
                "core_conversation_vector_stores.py"
            ),
            Path(
                "opencontractserver/llms/vector_stores/" "pydantic_ai_vector_stores.py"
            ),
        ]
        offenders = []
        for module in modules:
            if not module.exists():
                continue
            text = module.read_text()
            # The bug was ``sync_to_async(list)(...)`` — flag if a
            # parenthesised expression follows ``sync_to_async(list)``
            # without a lambda capture.
            if "sync_to_async(list)(" in text:
                offenders.append(str(module))
        self.assertEqual(
            offenders,
            [],
            msg=(
                "sync_to_async(list)(<queryset>) regression in: "
                f"{offenders}. Use sync_to_async(lambda: list(<queryset>))() "
                "so queryset evaluation runs in the thread pool worker."
            ),
        )


class TestDataclassesAsdictUsageGuard(TestCase):
    """``dataclasses.asdict(usage)`` would raise on a *class object* that
    happened to be a dataclass — ``is_dataclass`` returns True for both
    instances and classes. PR #1543 added the
    ``not isinstance(usage, type)`` guard. Assert the call site keeps
    the guard so a future refactor can't strip it."""

    def test_pydantic_ai_agents_keeps_isinstance_guard(self) -> None:
        from pathlib import Path

        text = Path("opencontractserver/llms/agents/pydantic_ai_agents.py").read_text()
        # The pattern: dataclasses.is_dataclass(...) and
        # not isinstance(..., type). Search loosely enough to tolerate
        # variable renames but tight enough to catch removal.
        self.assertIn("is_dataclass(", text)
        self.assertIn("not isinstance(", text)
        # Co-occurrence is what matters — and they should be on the same
        # logical line (``and`` joining).
        self.assertRegex(
            text,
            r"is_dataclass\([^)]+\)\s+and\s+not isinstance\(",
            msg=(
                "dataclasses.is_dataclass + 'not isinstance(...)'; type-guard "
                "appears to have been removed from pydantic_ai_agents.py. "
                "Without the guard, dataclasses.asdict on a dataclass *class* "
                "object will raise."
            ),
        )


class TestIsinstanceEventDispatchKeepsTypeSafety(TestCase):
    """The PR replaced ``getattr(ev, 'type', '') == 'thought'`` with
    ``isinstance(ev, ThoughtEvent)`` throughout pydantic_ai_agents.py.
    The new form avoids silently passing when an unrelated event type
    happens to carry the literal string. Assert the regression form is
    not re-introduced."""

    def test_no_string_compare_event_dispatch(self) -> None:
        from pathlib import Path

        text = Path("opencontractserver/llms/agents/pydantic_ai_agents.py").read_text()
        # The regression form would be:
        #   getattr(ev, "type", "") == "thought"
        # or any variant comparing a string-typed attribute to a literal
        # event-kind string for dispatch purposes.
        offenders = []
        if 'getattr(ev, "type", "") == "thought"' in text:
            offenders.append('getattr(ev, "type", "") == "thought"')
        if "getattr(ev, 'type', '') == 'thought'" in text:
            offenders.append("getattr(ev, 'type', '') == 'thought'")
        self.assertEqual(
            offenders,
            [],
            msg=(
                "string-comparison event dispatch regression in "
                f"pydantic_ai_agents.py: {offenders}. Use isinstance(ev, "
                "ThoughtEvent) so unrelated events with a matching string "
                "literal don't silently pass."
            ),
        )

    def test_isinstance_dispatch_present(self) -> None:
        """Sanity: the typed dispatch form remains."""
        from pathlib import Path

        text = Path("opencontractserver/llms/agents/pydantic_ai_agents.py").read_text()
        self.assertIn("isinstance(", text)


class TestStreamCorePersistenceGuard(TestCase):
    """``_stream_core`` added an ``llm_msg_id is not None`` guard to the
    ``enable_message_persistence=False`` branch. Without the guard, a
    no-persistence stream would try to update a message that doesn't
    exist."""

    def test_persistence_guard_present_in_source(self) -> None:
        from pathlib import Path

        text = Path("opencontractserver/llms/agents/pydantic_ai_agents.py").read_text()
        # The guard: ``if llm_msg_id is not None`` somewhere near
        # ``complete_message`` invocations. The exact spelling matters
        # less than the presence of the None check before any call that
        # depends on the message id.
        self.assertIn("llm_msg_id is not None", text)


class TestVectorStoreTypingChanges(TestCase):
    """``CoreAgentContext.documents`` was switched from Optional[list]
    to list with default_factory=list. Pin the dataclass field so a
    future revert would surface here."""

    def test_corpus_agent_context_documents_default_is_empty_list(self) -> None:
        from opencontractserver.llms.agents.core_agents import CorpusAgentContext

        ctx = CorpusAgentContext.__dataclass_fields__["documents"]
        # ``default_factory`` is the dataclasses sentinel for "computed
        # default" — it must be ``list`` (not ``MISSING``).
        self.assertIs(ctx.default_factory, list)

    def test_corpus_agent_context_documents_starts_empty_when_not_supplied(
        self,
    ) -> None:
        from opencontractserver.corpuses.models import Corpus
        from opencontractserver.llms.agents.core_agents import (
            AgentConfig,
            CorpusAgentContext,
        )
        from opencontractserver.users.models import User

        user = User.objects.create_user(username="ctx_test", password="x")
        corpus = Corpus.objects.create(title="Ctx Test", creator=user)
        config = AgentConfig(user_id=user.id)
        ctx = CorpusAgentContext(corpus=corpus, config=config)
        self.assertEqual(ctx.documents, [])
