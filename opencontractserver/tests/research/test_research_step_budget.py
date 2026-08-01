"""The step budget: telling the agent about it, and recording what it did.

A deep-research run is capped at ``request_limit = report.max_steps`` MODEL
REQUESTS as well as at a token budget. The step cap is the one the agent cannot
see and the one that bites: a run made exactly 60 of 60 permitted requests, was
cut off before it could call ``finalize_report``, and the salvage composition
that replaced its report body dropped two of the four ramp steps it had been
asked to walk. Both halves of the fix are pinned here — the notice that warns
the agent while it can still act, and the terminal reason that says which
budget ran out, since every non-finalize ending used to be recorded as the same
opaque ``budget_exhausted`` string.
"""

from __future__ import annotations

from asgiref.sync import async_to_sync
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from opencontractserver.corpuses.models import Corpus
from opencontractserver.research.constants import (
    DEEP_RESEARCH_STEP_BUDGET_FINAL_RATIO,
    DEEP_RESEARCH_STEP_BUDGET_WARN_RATIO,
    build_step_budget_notice,
)
from opencontractserver.research.models import ResearchReport
from opencontractserver.tasks.research_tasks import _audited, _terminal_reason


class _Response:
    """Minimal stand-in for ``UnifiedChatResponse`` — only metadata is read."""

    def __init__(self, metadata: dict | None):
        self.metadata = metadata


class StepBudgetNoticeTests(SimpleTestCase):
    def test_an_ordinary_run_is_never_nagged(self):
        self.assertIsNone(build_step_budget_notice(10, 60))

    def test_the_warning_lands_at_the_warn_ratio(self):
        at_warn = int(60 * DEEP_RESEARCH_STEP_BUDGET_WARN_RATIO)
        notice = build_step_budget_notice(at_warn, 60)
        assert notice is not None
        self.assertIn(f"{at_warn} of 60", notice)
        self.assertIn("Stop opening new lines of enquiry", notice)

    def test_the_hard_notice_says_to_finalize_now(self):
        at_final = int(60 * DEEP_RESEARCH_STEP_BUDGET_FINAL_RATIO)
        notice = build_step_budget_notice(at_final, 60)
        assert notice is not None
        self.assertIn("finalize_report NOW", notice)
        # It must say what is LOST, not just that a number is high: the agent
        # has no other way to weigh finalizing against one more search.
        self.assertIn("lost", notice)

    def test_the_hard_notice_leaves_room_to_act_on_it(self):
        # A notice that arrives with no requests left is not a warning, it is
        # an epitaph. Tool calls run a handful behind model requests, so the
        # final ratio must leave a real margin at the default budget.
        at_final = int(60 * DEEP_RESEARCH_STEP_BUDGET_FINAL_RATIO)
        self.assertGreaterEqual(60 - at_final, 8)

    def test_a_zero_budget_cannot_divide_by_zero(self):
        self.assertIsNone(build_step_budget_notice(3, 0))

    def test_known_gap_a_reasoning_only_run_gets_no_notice_at_all(self):
        # The notice is keyed on TOOL CALLS (what tool_call_log records), but
        # the hard cutoff (UsageLimits.request_limit) counts MODEL REQUESTS. A
        # request that only reasons makes no tool call, so a run that walks
        # straight into request_limit via reasoning-only requests never
        # crosses either ratio — it sees no warning at any point, including
        # the step immediately before the cutoff. This is a known, accepted
        # gap (see the DEEP_RESEARCH_STEP_BUDGET_* comment): pinned here so a
        # future change to the notice's counting basis is a deliberate one,
        # not a silent regression discovered in production.
        self.assertIsNone(build_step_budget_notice(0, 60))


class TerminalReasonTests(SimpleTestCase):
    def test_a_step_limit_is_named_as_a_step_limit(self):
        reason = _terminal_reason(
            _Response(
                {"error": "The next request would exceed the request_limit of 60"}
            )
        )
        self.assertIn("step budget exhausted", reason)

    def test_a_token_limit_is_not_mistaken_for_a_step_limit(self):
        # ``request_tokens_limit`` contains ``request_``; checking the step
        # marker first would label every token overrun a step overrun.
        reason = _terminal_reason(
            _Response({"error": "Exceeded the request_tokens_limit of 400000"})
        )
        self.assertIn("token budget exhausted", reason)

    def test_an_agent_that_simply_stopped_says_so(self):
        self.assertIn(
            "stopped without calling finalize_report", _terminal_reason(_Response({}))
        )

    def test_any_other_failure_keeps_its_class_name(self):
        reason = _terminal_reason(
            _Response({"error": "connection reset", "error_type": "APIConnectionError"})
        )
        self.assertIn("APIConnectionError", reason)
        self.assertIn("connection reset", reason)


class AuditedNoticeDeliveryTests(TestCase):
    """The notice has to reach BOTH tool return shapes.

    The retrieval tools return lists of rows, not strings, and a
    retrieval-heavy run is precisely the kind that exhausts its step budget —
    attaching the notice to string returns alone would leave the run that most
    needs the warning as the one that never sees it.
    """

    def setUp(self):
        user = get_user_model().objects.create_user(username="gate", password="x")
        corpus = Corpus.objects.create(title="Rules", creator=user)
        # Small budget so the warn ratio is crossed in a handful of calls
        # rather than 39 of them.
        self.report = ResearchReport.objects.create(
            creator=user, corpus=corpus, prompt="what applies", max_steps=10
        )

    @staticmethod
    def _call(tool, times: int):
        """Invoke ``tool`` ``times`` times; return the last result."""
        result = None
        for _ in range(times):
            result = async_to_sync(tool)()
        return result

    def test_a_string_result_carries_the_notice_as_trailing_text(self):
        async def _tool() -> str:
            return "Recorded finding."

        wrapped = _audited(self.report, "record_finding", _tool)
        below = self._call(wrapped, 3)
        self.assertEqual(below, "Recorded finding.")

        # 0.65 * 10 -> the 7th call is the first at or above the warn ratio.
        crossed = self._call(wrapped, 4)
        self.assertTrue(crossed.startswith("Recorded finding."))
        self.assertIn("Step budget: 7 of 10 used", crossed)

    def test_a_list_result_carries_the_notice_as_a_trailing_row(self):
        async def _tool() -> list[dict]:
            return [{"annotation_id": 1, "content": "…"}]

        wrapped = _audited(self.report, "find_citable_passages", _tool)
        below = self._call(wrapped, 3)
        self.assertEqual(len(below), 1)

        crossed = self._call(wrapped, 4)
        self.assertEqual(len(crossed), 2)
        # The original rows are untouched and the notice is additive — a guard
        # that rewrote a retrieval row would be inventing evidence.
        self.assertEqual(crossed[0], {"annotation_id": 1, "content": "…"})
        self.assertIn("Step budget: 7 of 10 used", crossed[1]["note"])

    def test_every_call_is_audited_whatever_it_returns(self):
        async def _tool() -> list[dict]:
            return [{"annotation_id": 1}]

        wrapped = _audited(self.report, "find_citable_passages", _tool)
        self._call(wrapped, 5)
        self.report.refresh_from_db()
        self.assertEqual(len(self.report.tool_call_log), 5)


class DefaultToolsetAuditTests(TestCase):
    """The audit wrapper must actually reach the agent's default toolset.

    ``tool_call_log`` once covered only the closures ``research_tasks`` builds,
    so ``similarity_search`` was invisible and ten runs were read as never
    having searched by meaning. The wrapper reaches into pydantic-ai's
    ``Tool.function_schema.function`` seam, which a framework upgrade could
    move — and if it moves, the wrapper stops applying silently and the log
    goes back to reporting absences it cannot see. Assert that it took.
    """

    class _Schema:
        def __init__(self, fn):
            self.function = fn

    class _Tool:
        def __init__(self, fn):
            self.function_schema = DefaultToolsetAuditTests._Schema(fn)

    class _Toolset:
        def __init__(self, tools):
            self.tools = tools

    class _Agent:
        def __init__(self, toolset):
            self.pydantic_ai_agent = type("Inner", (), {"_function_toolset": toolset})()

    def setUp(self):
        user = get_user_model().objects.create_user(username="audit", password="x")
        corpus = Corpus.objects.create(title="Rules", creator=user)
        self.report = ResearchReport.objects.create(
            creator=user, corpus=corpus, prompt="what applies", max_steps=60
        )

    def test_an_async_default_tool_is_wrapped_and_logs_its_calls(self):
        from opencontractserver.tasks.research_tasks import _audit_default_toolset

        async def similarity_search(query: str) -> list[dict]:
            return [{"annotation_id": 1}]

        tool = self._Tool(similarity_search)
        _audit_default_toolset(
            self.report, self._Agent(self._Toolset({"similarity_search": tool}))
        )

        self.assertIsNot(tool.function_schema.function, similarity_search)
        async_to_sync(tool.function_schema.function)(query="ramp")

        self.report.refresh_from_db()
        self.assertEqual(
            [entry["tool"] for entry in self.report.tool_call_log],
            ["similarity_search"],
        )

    def test_wrapping_is_not_applied_twice(self):
        from opencontractserver.tasks.research_tasks import _audit_default_toolset

        async def list_documents() -> list[dict]:
            return []

        tool = self._Tool(list_documents)
        agent = self._Agent(self._Toolset({"list_documents": tool}))
        _audit_default_toolset(self.report, agent)
        once = tool.function_schema.function
        _audit_default_toolset(self.report, agent)
        self.assertIs(tool.function_schema.function, once)

    def test_a_closure_this_module_already_wrapped_is_not_wrapped_again(self):
        # The closures are handed to the factory as caller tools and land in
        # the SAME resolved toolset this pass walks. Without the marker set at
        # creation they were wrapped twice: every closure call wrote two audit
        # rows, and the step-budget counter reads the log length, so a notice
        # claiming "47 of 60" was arriving at 24 real calls.
        from opencontractserver.tasks.research_tasks import (
            _audit_default_toolset,
            _audited,
        )

        async def record_finding() -> str:
            return "Recorded."

        already = _audited(self.report, "record_finding", record_finding)
        tool = self._Tool(already)
        _audit_default_toolset(
            self.report,
            self._Agent(self._Toolset({"record_finding": tool})),
            already_audited=frozenset({"record_finding"}),
        )
        self.assertIs(tool.function_schema.function, already)

        async_to_sync(tool.function_schema.function)()
        self.report.refresh_from_db()
        self.assertEqual(len(self.report.tool_call_log), 1)

    def test_a_factory_rewrapped_closure_is_still_skipped_by_name(self):
        # The real failure. The factory re-wraps caller tools, so the callable
        # reachable at function_schema.function is ITS wrapper, not ours, and
        # carries no marker — the attribute check alone let every closure be
        # audited twice, and the step-budget counter reads the log length, so a
        # run at 27 real calls was told "54 of 60 used".
        from opencontractserver.tasks.research_tasks import (
            _audit_default_toolset,
            _audited,
        )

        async def record_finding() -> str:
            return "Recorded."

        ours = _audited(self.report, "record_finding", record_finding)

        async def factory_wrapper(*args, **kwargs):  # no marker, by construction
            return await ours(*args, **kwargs)

        tool = self._Tool(factory_wrapper)
        _audit_default_toolset(
            self.report,
            self._Agent(self._Toolset({"record_finding": tool})),
            already_audited=frozenset({"record_finding"}),
        )
        self.assertIs(tool.function_schema.function, factory_wrapper)

        async_to_sync(tool.function_schema.function)()
        self.report.refresh_from_db()
        self.assertEqual(len(self.report.tool_call_log), 1)

    def test_a_sync_tool_is_left_alone_rather_than_broken(self):
        # The schema fixed sync-vs-async at registration; handing it a
        # coroutine where it expects a plain return would break every call.
        from opencontractserver.tasks.research_tasks import _audit_default_toolset

        def legacy_sync_tool() -> str:
            return "ok"

        tool = self._Tool(legacy_sync_tool)
        _audit_default_toolset(
            self.report, self._Agent(self._Toolset({"legacy": tool}))
        )
        self.assertIs(tool.function_schema.function, legacy_sync_tool)
