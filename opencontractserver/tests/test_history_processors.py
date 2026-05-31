"""Unit tests for ``opencontractserver.llms.history_processors``.

Pure-unit (no DB, no LLM, no Django setup). Each test constructs a
fabricated pydantic-ai message list, runs the processor on it, and
asserts the resulting list has the expected shape.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    ThinkingPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

from opencontractserver.constants.context_guardrails import (
    IN_RUN_TRIM_NOTICE_MARKER,
)
from opencontractserver.llms.context_guardrails import CompactionConfig
from opencontractserver.llms.history_processors import (
    InRunShrinkEvent,
    shrink_old_artifacts_processor,
)


# A minimal stand-in for PydanticAIDependencies that only carries the
# fields the processor reads. Avoids importing the full pydantic model
# (which has many other required fields) into a pure-unit test.
@dataclass
class _FakeDeps:
    model_name: str = "claude-opus-4"
    system_prompt: str = ""
    compaction: CompactionConfig = field(default_factory=CompactionConfig)
    on_in_run_shrink: Any = None
    # Events captured by a default sink for easy assertion.
    events: list[InRunShrinkEvent] = field(default_factory=list)

    def __post_init__(self) -> None:
        # Default callback appends to ``events`` if the test didn't set one.
        if self.on_in_run_shrink is None:
            self.on_in_run_shrink = self.events.append


@dataclass
class _FakeRunContext:
    """Minimal RunContext stand-in. The processor only reads ``.deps``."""

    deps: Any


def _run(messages: list[ModelMessage], deps: _FakeDeps) -> list[ModelMessage]:
    """Helper to invoke the async processor synchronously."""
    ctx = _FakeRunContext(deps=deps)
    return asyncio.run(shrink_old_artifacts_processor(ctx, messages))  # type: ignore[arg-type]


def _make_pair(
    *,
    tool_call_id: str,
    tool_name: str,
    return_chars: int,
    thinking_chars: int = 0,
) -> tuple[ModelResponse, ModelRequest]:
    """Build a (ModelResponse-with-ToolCall, ModelRequest-with-ToolReturn) pair."""
    parts_resp: list[Any] = [TextPart(content="step")]
    if thinking_chars:
        parts_resp.append(ThinkingPart(content="t" * thinking_chars))
    parts_resp.append(
        ToolCallPart(
            tool_name=tool_name,
            args="{}",
            tool_call_id=tool_call_id,
        )
    )
    response = ModelResponse(parts=parts_resp)
    request = ModelRequest(
        parts=[
            ToolReturnPart(
                tool_name=tool_name,
                content="r" * return_chars,
                tool_call_id=tool_call_id,
            ),
        ]
    )
    return response, request


def test_under_threshold_returns_messages_unchanged():
    """When total tokens are below threshold, processor is a no-op."""
    resp, req = _make_pair(tool_call_id="A", tool_name="search", return_chars=200)
    messages: list[ModelMessage] = [
        ModelRequest(parts=[UserPromptPart(content="hi")]),
        resp,
        req,
        ModelResponse(parts=[TextPart(content="done")]),
        ModelRequest(parts=[UserPromptPart(content="continue")]),
    ]
    deps = _FakeDeps()
    result = _run(messages, deps)
    assert result is messages or list(result) == list(messages)
    assert deps.events == []


def test_over_threshold_shrinks_oldest_tool_return():
    """One ToolReturnPart far in the past is shrunk to target_chars."""
    # claude-opus-4 has a 200_000 token window. Build messages so total
    # exceeds 0.75 * 200_000 = 150_000 tokens estimated. A 600_000-char
    # tool return alone is ~600_000 / 3.5 = ~171_428 tokens.
    old_resp, old_req = _make_pair(
        tool_call_id="OLD", tool_name="load_document_text", return_chars=600_000
    )
    # Five recent pairs so the OLD pair is outside the protected suffix.
    recent_pairs: list[ModelMessage] = []
    for i in range(5):
        r1, r2 = _make_pair(tool_call_id=f"R{i}", tool_name="ping", return_chars=100)
        recent_pairs.extend([r1, r2])
    messages: list[ModelMessage] = [
        ModelRequest(parts=[UserPromptPart(content="start")]),
        old_resp,
        old_req,
        *recent_pairs,
        ModelResponse(parts=[TextPart(content="thinking")]),
        ModelRequest(parts=[UserPromptPart(content="continue")]),
    ]

    deps = _FakeDeps()
    result = _run(messages, deps)

    # OLD return is now ≤ target_chars + trim notice length.
    old_return_msg = result[2]
    assert isinstance(old_return_msg, ModelRequest)
    old_return_part = old_return_msg.parts[0]
    assert isinstance(old_return_part, ToolReturnPart)
    assert isinstance(old_return_part.content, str)
    assert len(old_return_part.content) < 5_000
    assert IN_RUN_TRIM_NOTICE_MARKER in old_return_part.content
    assert old_return_part.tool_call_id == "OLD"

    # A telemetry event was emitted exactly once.
    assert len(deps.events) == 1
    evt = deps.events[0]
    assert evt.tool_returns_shrunk == 1
    assert evt.tokens_before > evt.tokens_after
    assert evt.context_window == 200_000


def test_drops_older_thinking_parts():
    """ThinkingPart in older messages is dropped; recent ones survive."""
    old_resp, old_req = _make_pair(
        tool_call_id="OLD",
        tool_name="load_document_text",
        return_chars=600_000,
        thinking_chars=8_000,
    )
    recent_pairs: list[ModelMessage] = []
    for i in range(5):
        r1, r2 = _make_pair(
            tool_call_id=f"R{i}",
            tool_name="ping",
            return_chars=50,
            thinking_chars=200,  # recent ThinkingParts should survive
        )
        recent_pairs.extend([r1, r2])
    messages: list[ModelMessage] = [
        ModelRequest(parts=[UserPromptPart(content="start")]),
        old_resp,
        old_req,
        *recent_pairs,
        ModelResponse(parts=[TextPart(content="step")]),
        ModelRequest(parts=[UserPromptPart(content="continue")]),
    ]

    deps = _FakeDeps()
    result = _run(messages, deps)

    # Older ModelResponse no longer carries a ThinkingPart. Locate it by
    # the ToolCallPart's tool_call_id rather than positional index so the
    # assertion survives fixture reshuffles.
    old_resp_new = next(
        m
        for m in result
        if isinstance(m, ModelResponse)
        and any(
            isinstance(p, ToolCallPart) and p.tool_call_id == "OLD" for p in m.parts
        )
    )
    assert not any(isinstance(p, ThinkingPart) for p in old_resp_new.parts)
    # But ToolCallPart survives.
    assert any(isinstance(p, ToolCallPart) for p in old_resp_new.parts)

    # A recent ModelResponse still carries its ThinkingPart. Older
    # responses had theirs stripped, so the first surviving ThinkingPart
    # must live inside the protected ``keep_recent_pairs`` suffix —
    # whichever positional index that lands at as the fixture evolves.
    recent_resp = next(
        m
        for m in result
        if isinstance(m, ModelResponse)
        and any(isinstance(p, ThinkingPart) for p in m.parts)
    )
    assert any(isinstance(p, ThinkingPart) for p in recent_resp.parts)

    # Telemetry event reflects the drop.
    # Older prefix has 3 ModelResponses with ThinkingParts:
    # old_resp, R0-resp, R1-resp (all outside the keep_recent_pairs=4 window).
    assert len(deps.events) == 1
    assert deps.events[0].thinking_parts_dropped == 3
    # The 600k char old tool return was also shrunk in the same pass.
    assert deps.events[0].tool_returns_shrunk == 1


def test_preserves_tool_call_id_correlation():
    """Shrinking a return must not alter its tool_call_id or its
    ToolCallPart counterpart."""
    old_resp, old_req = _make_pair(
        tool_call_id="UNIQUE_ID_42",
        tool_name="similarity_search",
        return_chars=600_000,
    )
    recent_pairs: list[ModelMessage] = []
    for i in range(5):
        r1, r2 = _make_pair(tool_call_id=f"R{i}", tool_name="ping", return_chars=50)
        recent_pairs.extend([r1, r2])
    messages: list[ModelMessage] = [
        ModelRequest(parts=[UserPromptPart(content="start")]),
        old_resp,
        old_req,
        *recent_pairs,
        ModelResponse(parts=[TextPart(content="step")]),
        ModelRequest(parts=[UserPromptPart(content="continue")]),
    ]

    deps = _FakeDeps()
    result = _run(messages, deps)

    # ToolCallPart in the ModelResponse still references the same id.
    tool_call_part = next(p for p in result[1].parts if isinstance(p, ToolCallPart))
    assert tool_call_part.tool_call_id == "UNIQUE_ID_42"

    # ToolReturnPart still references the same id (just shrunk content).
    tool_return_part = result[2].parts[0]
    assert isinstance(tool_return_part, ToolReturnPart)
    assert tool_return_part.tool_call_id == "UNIQUE_ID_42"
    assert tool_return_part.tool_name == "similarity_search"


def test_last_message_is_modelrequest_invariant():
    """Processor must never touch the very last message (always a ModelRequest)."""
    old_resp, old_req = _make_pair(
        tool_call_id="OLD", tool_name="load_document_text", return_chars=600_000
    )
    recent_pairs: list[ModelMessage] = []
    for i in range(5):
        r1, r2 = _make_pair(tool_call_id=f"R{i}", tool_name="ping", return_chars=50)
        recent_pairs.extend([r1, r2])
    last = ModelRequest(parts=[UserPromptPart(content="LAST_SENTINEL")])
    messages: list[ModelMessage] = [
        ModelRequest(parts=[UserPromptPart(content="start")]),
        old_resp,
        old_req,
        *recent_pairs,
        ModelResponse(parts=[TextPart(content="step")]),
        last,
    ]

    deps = _FakeDeps()
    result = _run(messages, deps)

    assert isinstance(result[-1], ModelRequest)
    last_part = result[-1].parts[0]
    assert isinstance(last_part, UserPromptPart)
    assert last_part.content == "LAST_SENTINEL"


def test_history_shorter_than_keep_recent_pairs_is_noop():
    """3 messages with keep_recent_pairs=4: nothing is older → no-op."""
    old_resp, old_req = _make_pair(
        tool_call_id="A", tool_name="t", return_chars=600_000
    )
    messages: list[ModelMessage] = [
        old_resp,
        old_req,
        ModelRequest(parts=[UserPromptPart(content="continue")]),
    ]
    deps = _FakeDeps()  # default keep_recent_pairs=4
    result = _run(messages, deps)

    # Even though we're over threshold, nothing should be shrunk.
    old_return = result[1]
    assert isinstance(old_return, ModelRequest)
    assert isinstance(old_return.parts[0], ToolReturnPart)
    assert isinstance(old_return.parts[0].content, str)
    assert len(old_return.parts[0].content) == 600_000
    assert deps.events == []


def test_in_run_enabled_false_short_circuits():
    """When config.in_run_enabled is False, processor is a hard no-op."""
    old_resp, old_req = _make_pair(
        tool_call_id="A", tool_name="t", return_chars=600_000
    )
    recent_pairs: list[ModelMessage] = []
    for i in range(5):
        r1, r2 = _make_pair(tool_call_id=f"R{i}", tool_name="ping", return_chars=50)
        recent_pairs.extend([r1, r2])
    messages: list[ModelMessage] = [
        old_resp,
        old_req,
        *recent_pairs,
        ModelRequest(parts=[UserPromptPart(content="continue")]),
    ]
    deps = _FakeDeps(compaction=CompactionConfig(in_run_enabled=False))
    result = _run(messages, deps)

    old_return = result[1]
    assert isinstance(old_return.parts[0], ToolReturnPart)
    assert isinstance(old_return.parts[0].content, str)
    assert len(old_return.parts[0].content) == 600_000
    assert deps.events == []


def test_no_shrinkable_content_logs_info(caplog):
    """Over threshold but no ToolReturnPart/ThinkingPart → log + unchanged.

    Logged at INFO (not WARNING): the older prefix being all
    ``UserPromptPart`` is a structural condition the in-run processor
    intentionally does not handle (turn-level compaction picks it up
    instead), so it must not page on log monitors that alert at WARNING+.
    """
    # Stuff a giant UserPromptPart in an old message — we never shrink those.
    huge = ModelRequest(parts=[UserPromptPart(content="x" * 800_000)])
    recent_pairs: list[ModelMessage] = []
    for i in range(5):
        r1, r2 = _make_pair(tool_call_id=f"R{i}", tool_name="ping", return_chars=50)
        recent_pairs.extend([r1, r2])
    messages: list[ModelMessage] = [
        huge,
        *recent_pairs,
        ModelRequest(parts=[UserPromptPart(content="continue")]),
    ]
    deps = _FakeDeps()

    with caplog.at_level(
        logging.INFO, logger="opencontractserver.llms.history_processors"
    ):
        result = _run(messages, deps)

    assert result is messages or list(result) == list(messages)
    matching = [
        rec
        for rec in caplog.records
        if "no ToolReturnPart or ThinkingPart" in rec.message
    ]
    assert matching, "expected the unshrinkable-prefix log line"
    assert all(rec.levelno == logging.INFO for rec in matching), (
        "unshrinkable-prefix log line must be INFO, not WARNING — see "
        "history_processors.py for rationale"
    )
    assert deps.events == []


def test_deps_none_does_not_crash():
    """Running without deps falls back to module defaults."""
    messages: list[ModelMessage] = [
        ModelRequest(parts=[UserPromptPart(content="hi")]),
    ]
    ctx = _FakeRunContext(deps=None)
    result = asyncio.run(shrink_old_artifacts_processor(ctx, messages))  # type: ignore[arg-type]
    assert result == messages


def test_callback_receives_correct_event_shape():
    """on_in_run_shrink callback is called once with a fully-populated event."""
    old_resp, old_req = _make_pair(
        tool_call_id="A", tool_name="t", return_chars=600_000, thinking_chars=8_000
    )
    recent_pairs: list[ModelMessage] = []
    for i in range(5):
        r1, r2 = _make_pair(tool_call_id=f"R{i}", tool_name="ping", return_chars=50)
        recent_pairs.extend([r1, r2])
    messages: list[ModelMessage] = [
        ModelRequest(parts=[UserPromptPart(content="start")]),
        old_resp,
        old_req,
        *recent_pairs,
        ModelRequest(parts=[UserPromptPart(content="continue")]),
    ]

    captured: list[InRunShrinkEvent] = []
    deps = _FakeDeps(on_in_run_shrink=captured.append)
    _run(messages, deps)

    assert len(captured) == 1
    evt = captured[0]
    assert isinstance(evt, InRunShrinkEvent)
    assert evt.tool_returns_shrunk == 1
    assert evt.thinking_parts_dropped == 1
    assert evt.context_window == 200_000
    assert evt.tokens_before > evt.tokens_after > 0


def test_resolves_compaction_from_deps_compaction_field():
    """`_resolve_config` reads ``deps.compaction`` (the production field
    name on ``PydanticAIDependencies``). Pins the contract that the
    stub used elsewhere in this file mirrors production.
    """
    old_resp, old_req = _make_pair(
        tool_call_id="A", tool_name="t", return_chars=600_000
    )
    recent_pairs: list[ModelMessage] = []
    for i in range(5):
        r1, r2 = _make_pair(tool_call_id=f"R{i}", tool_name="ping", return_chars=50)
        recent_pairs.extend([r1, r2])
    messages: list[ModelMessage] = [
        old_resp,
        old_req,
        *recent_pairs,
        ModelRequest(parts=[UserPromptPart(content="continue")]),
    ]

    deps = _FakeDeps(compaction=CompactionConfig(in_run_enabled=False))
    result = _run(messages, deps)

    # in_run_enabled=False short-circuits — old tool return is untouched.
    old_return = result[1]
    assert isinstance(old_return, ModelRequest)
    old_part = old_return.parts[0]
    assert isinstance(old_part, ToolReturnPart)
    old_content = old_part.content
    assert isinstance(old_content, str)
    assert len(old_content) == 600_000
    assert deps.events == []


def test_callback_exception_does_not_propagate(caplog):
    """A raising ``on_in_run_shrink`` callback must not break the run.

    Pins the defensive contract on the callback seam: telemetry
    failures (e.g. websocket already closed, builder mid-teardown)
    must never bubble out of the processor — otherwise the outer
    ``try/except`` would turn the shrink into a silent no-op and
    the agent run would keep accumulating context.
    """
    old_resp, old_req = _make_pair(
        tool_call_id="A", tool_name="t", return_chars=600_000
    )
    recent_pairs: list[ModelMessage] = []
    for i in range(5):
        r1, r2 = _make_pair(tool_call_id=f"R{i}", tool_name="ping", return_chars=50)
        recent_pairs.extend([r1, r2])
    messages: list[ModelMessage] = [
        ModelRequest(parts=[UserPromptPart(content="start")]),
        old_resp,
        old_req,
        *recent_pairs,
        ModelRequest(parts=[UserPromptPart(content="continue")]),
    ]

    def _raises(_event: InRunShrinkEvent) -> None:
        raise RuntimeError("simulated telemetry sink failure")

    deps = _FakeDeps(on_in_run_shrink=_raises)

    with caplog.at_level(
        logging.ERROR, logger="opencontractserver.llms.history_processors"
    ):
        result = _run(messages, deps)

    # Shrink still applied to the old tool return — callback failure
    # must not undo the actual compaction work.
    old_return = result[2]
    assert isinstance(old_return, ModelRequest)
    old_part = old_return.parts[0]
    assert isinstance(old_part, ToolReturnPart)
    assert isinstance(old_part.content, str)
    assert len(old_part.content) < 5_000
    # And the failure surfaced via logger.exception, not by escaping.
    assert any(
        "on_in_run_shrink callback raised" in rec.message for rec in caplog.records
    )


def test_thinking_only_modelresponse_is_not_emptied():
    """A ModelResponse whose only part is a ThinkingPart survives the
    drop-thinking pass because of the empty-parts guard.

    The fixture deliberately places a *second*, shrinkable artifact in the
    older prefix (a large ``ToolReturnPart``). Without it the processor
    would hit the ``tool_returns_shrunk == 0 and thinking_parts_dropped ==
    0`` early-return and leave the whole list untouched — so the
    thinking-only response would survive simply because *nothing* ran, not
    because the guard fired. The big tool return forces the real shrink
    path: the processor does modify the older prefix this pass, and the
    guard is the reason the thinking-only ModelResponse alone is spared.
    """
    # An old ModelResponse with only a giant ThinkingPart.
    only_thinking = ModelResponse(parts=[ThinkingPart(content="t" * 600_000)])
    # A large, shrinkable tool return alongside it in the older prefix so
    # the processor has something to actually shrink this pass.
    big_return_req = ModelRequest(
        parts=[
            ToolReturnPart(
                tool_name="load_document_text",
                content="r" * 600_000,
                tool_call_id="BIG",
            )
        ]
    )
    recent_pairs: list[ModelMessage] = []
    for i in range(5):
        r1, r2 = _make_pair(tool_call_id=f"R{i}", tool_name="ping", return_chars=50)
        recent_pairs.extend([r1, r2])
    messages: list[ModelMessage] = [
        only_thinking,
        big_return_req,
        *recent_pairs,
        ModelRequest(parts=[UserPromptPart(content="continue")]),
    ]

    deps = _FakeDeps()
    result = _run(messages, deps)

    # (a) The thinking-only ModelResponse is left intact — the guard refused
    #     to strip its only part even though in_run_drop_thinking is on.
    first = result[0]
    assert isinstance(first, ModelResponse)
    assert len(first.parts) == 1
    assert isinstance(first.parts[0], ThinkingPart)

    # (b) The shrink genuinely ran this pass (not the no-op early return):
    #     the large sibling tool return WAS truncated.
    big_return = result[1]
    assert isinstance(big_return, ModelRequest)
    big_part = big_return.parts[0]
    assert isinstance(big_part, ToolReturnPart)
    assert isinstance(big_part.content, str)
    assert len(big_part.content) < 5_000
    assert IN_RUN_TRIM_NOTICE_MARKER in big_part.content
    assert big_part.tool_call_id == "BIG"

    # (c) Telemetry confirms the guard — not an early return — is why the
    #     ThinkingPart survived: a shrink event fired with the tool return
    #     counted but zero thinking parts dropped (the only droppable
    #     ThinkingPart was the one the guard protected).
    assert len(deps.events) == 1
    evt = deps.events[0]
    assert evt.tool_returns_shrunk == 1
    assert evt.thinking_parts_dropped == 0


def test_non_string_tool_return_serialized_as_json():
    """A structured (dict) ToolReturnPart is serialised with ``json.dumps``,
    not ``str()``, when shrunk.

    Tools may return dicts/lists. ``str()`` on those yields Python repr
    (single-quoted keys, ``True``/``None`` literals) the model can
    misparse; ``json.dumps`` yields valid JSON. This pins that the shrunk
    content is JSON-shaped.
    """
    # A structured return whose JSON serialisation alone exceeds the
    # threshold, so it is both the over-threshold trigger and the thing
    # that gets shrunk. ``True``/``None`` round-trip differently under
    # json.dumps ("true"/"null") vs str() ("True"/"None"), giving the
    # assertion a clean discriminator.
    big_payload = {
        "flag": True,
        "missing": None,
        "blob": "v" * 700_000,
    }
    old_resp = ModelResponse(
        parts=[
            TextPart(content="step"),
            ToolCallPart(tool_name="search", args="{}", tool_call_id="JSON"),
        ]
    )
    old_req = ModelRequest(
        parts=[
            ToolReturnPart(
                tool_name="search",
                content=big_payload,
                tool_call_id="JSON",
            )
        ]
    )
    recent_pairs: list[ModelMessage] = []
    for i in range(5):
        r1, r2 = _make_pair(tool_call_id=f"R{i}", tool_name="ping", return_chars=50)
        recent_pairs.extend([r1, r2])
    messages: list[ModelMessage] = [
        ModelRequest(parts=[UserPromptPart(content="start")]),
        old_resp,
        old_req,
        *recent_pairs,
        ModelRequest(parts=[UserPromptPart(content="continue")]),
    ]

    deps = _FakeDeps()
    result = _run(messages, deps)

    shrunk = result[2]
    assert isinstance(shrunk, ModelRequest)
    part = shrunk.parts[0]
    assert isinstance(part, ToolReturnPart)
    # Serialised to a string and truncated with the trim notice.
    assert isinstance(part.content, str)
    assert IN_RUN_TRIM_NOTICE_MARKER in part.content
    # JSON serialisation, not Python repr: object opens with ``{``, keys are
    # double-quoted, and there are no single-quoted Python-repr keys.
    assert part.content.startswith("{")
    assert '"flag"' in part.content
    assert "'flag'" not in part.content
    # The booleans/null are JSON tokens, never Python ``True``/``None``.
    assert "true" in part.content
    assert "True" not in part.content
    assert "null" in part.content  # JSON null, not Python None
    # Safe because the only non-JSON text spliced into the payload is the trim
    # notice (IN_RUN_TRIM_NOTICE_MARKER), whose template is fixed numeric/text
    # and contains no literal "None"; if that template ever changes to include
    # the word, tighten this to assert against the JSON prefix only.
    assert "None" not in part.content
    # tool_call_id correlation preserved across the serialise+shrink.
    assert part.tool_call_id == "JSON"
    assert deps.events and deps.events[0].tool_returns_shrunk == 1
