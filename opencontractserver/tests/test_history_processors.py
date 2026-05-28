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
    config_compaction: CompactionConfig = field(default_factory=CompactionConfig)
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
    return asyncio.run(shrink_old_artifacts_processor(ctx, messages))


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
    assert "in-run trim" in old_return_part.content
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

    # Older ModelResponse no longer carries a ThinkingPart.
    old_resp_new = result[1]
    assert isinstance(old_resp_new, ModelResponse)
    assert not any(isinstance(p, ThinkingPart) for p in old_resp_new.parts)
    # But ToolCallPart survives.
    assert any(isinstance(p, ToolCallPart) for p in old_resp_new.parts)

    # A recent ModelResponse still carries its ThinkingPart.
    # With keep_recent_pairs=4 and messages structured as:
    #   [0]=start-req [1]=old-resp [2]=old-req
    #   [3]=R0-resp [4]=R0-req [5]=R1-resp [6]=R1-req   ← older prefix (0..6)
    #   [7]=R2-resp [8]=R2-req [9]=R3-resp [10]=R3-req
    #   [11]=R4-resp [12]=R4-req [13]=final-resp [14]=final-req  ← recent (7..14)
    # result[7] is R2-resp, the first ModelResponse inside the protected suffix.
    recent_resp = result[7]  # first ModelResponse in the protected recent suffix
    assert isinstance(recent_resp, ModelResponse)
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
    deps = _FakeDeps(config_compaction=CompactionConfig(in_run_enabled=False))
    result = _run(messages, deps)

    old_return = result[1]
    assert isinstance(old_return.parts[0], ToolReturnPart)
    assert isinstance(old_return.parts[0].content, str)
    assert len(old_return.parts[0].content) == 600_000
    assert deps.events == []


def test_no_shrinkable_content_logs_warning(caplog):
    """Over threshold but no ToolReturnPart/ThinkingPart → log + unchanged."""
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
        logging.WARNING, logger="opencontractserver.llms.history_processors"
    ):
        result = _run(messages, deps)

    assert result is messages or list(result) == list(messages)
    assert any(
        "no ToolReturnPart or ThinkingPart" in rec.message for rec in caplog.records
    )
    assert deps.events == []


def test_deps_none_does_not_crash():
    """Running without deps falls back to module defaults."""
    messages: list[ModelMessage] = [
        ModelRequest(parts=[UserPromptPart(content="hi")]),
    ]
    ctx = _FakeRunContext(deps=None)
    result = asyncio.run(shrink_old_artifacts_processor(ctx, messages))
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
    """When deps has a ``compaction`` field (production path), the
    processor reads its config from there instead of falling back to
    defaults."""
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

    # Build a stub that exposes ``compaction`` (production field name),
    # not ``config_compaction``. The CompactionConfig disables in-run
    # so we should see a hard no-op.
    @dataclass
    class _ProdDeps:
        compaction: CompactionConfig = field(
            default_factory=lambda: CompactionConfig(in_run_enabled=False)
        )
        model_name: str = "claude-opus-4"
        system_prompt: str = ""
        on_in_run_shrink: Any = None
        events: list[InRunShrinkEvent] = field(default_factory=list)

        def __post_init__(self) -> None:
            if self.on_in_run_shrink is None:
                self.on_in_run_shrink = self.events.append

    deps = _ProdDeps()
    ctx = _FakeRunContext(deps=deps)
    result = asyncio.run(shrink_old_artifacts_processor(ctx, messages))

    # in_run_enabled=False short-circuits — old tool return is untouched.
    old_return = result[1]
    assert isinstance(old_return, ModelRequest)
    old_part = old_return.parts[0]
    assert isinstance(old_part, ToolReturnPart)
    old_content = old_part.content
    assert isinstance(old_content, str)
    assert len(old_content) == 600_000
    assert deps.events == []


def test_thinking_only_modelresponse_is_not_emptied():
    """A ModelResponse with only ThinkingPart is left intact (no empty parts)."""
    # An old ModelResponse with only a giant ThinkingPart.
    only_thinking = ModelResponse(parts=[ThinkingPart(content="t" * 600_000)])
    # Pair it with a ModelRequest so the structure is valid.
    old_req = ModelRequest(
        parts=[UserPromptPart(content="paired with thinking-only response")]
    )
    recent_pairs: list[ModelMessage] = []
    for i in range(5):
        r1, r2 = _make_pair(tool_call_id=f"R{i}", tool_name="ping", return_chars=50)
        recent_pairs.extend([r1, r2])
    messages: list[ModelMessage] = [
        only_thinking,
        old_req,
        *recent_pairs,
        ModelRequest(parts=[UserPromptPart(content="continue")]),
    ]

    deps = _FakeDeps()
    result = _run(messages, deps)

    # The thinking-only ModelResponse is left intact (we didn't strip the
    # only thing it contained).
    first = result[0]
    assert isinstance(first, ModelResponse)
    assert len(first.parts) == 1
    assert isinstance(first.parts[0], ThinkingPart)
