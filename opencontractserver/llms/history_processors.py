"""pydantic-ai ``HistoryProcessor`` for in-run conversation compaction.

Installed by :func:`opencontractserver.llms.agents.pydantic_ai_factory.make_pydantic_ai_agent`
on every constructed ``pydantic_ai.Agent``. Runs before each model
request (see pydantic_ai/_agent_graph.py:521). When the cumulative
token estimate exceeds the configured threshold ratio, the processor:

- Truncates ``ToolReturnPart.content`` in older messages to
  ``in_run_tool_return_target_chars`` (preserving ``tool_call_id`` so
  the call/return correlation stays intact).
- Optionally strips ``ThinkingPart`` instances from older
  ``ModelResponse`` messages (rarely useful after the next loop
  iteration has committed).

The protected suffix — ``in_run_keep_recent_pairs`` most-recent
ModelResponse+ModelRequest pairs — is never modified. Returns the
message list unchanged when below threshold (cheap hot path).

Telemetry: every shrink logs an INFO line and invokes
``ctx.deps.on_in_run_shrink`` (if set) with an :class:`InRunShrinkEvent`.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, replace
from typing import Any

from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    ThinkingPart,
    ToolReturnPart,
)
from pydantic_ai.tools import RunContext

from opencontractserver.constants.context_guardrails import (
    IN_RUN_TRIM_NOTICE_MARKER,
)
from opencontractserver.llms.context_guardrails import (
    CompactionConfig,
    context_window_and_threshold,
    estimate_token_count,
)

logger = logging.getLogger(__name__)


# ``dataclasses.replace`` only works on stdlib ``@dataclass`` instances. We
# rely on it for ``ToolReturnPart`` / ``ModelRequest`` / ``ModelResponse``.
# If a future pydantic-ai release migrates any of these to ``BaseModel``,
# ``replace()`` would raise at runtime — and the outer ``try/except`` in
# ``shrink_old_artifacts_processor`` would silently swallow it, leaving the
# processor a no-op with no visible signal. Fail loudly at import time
# instead so the pydantic-ai bump that breaks the assumption is caught by
# CI rather than degrading silently in production.
for _msg_type in (ToolReturnPart, ModelRequest, ModelResponse):
    if not hasattr(_msg_type, "__dataclass_fields__"):
        raise RuntimeError(
            f"pydantic-ai message type {_msg_type.__name__} is no longer a "
            "stdlib @dataclass; dataclasses.replace() calls in "
            "history_processors.py will fail. Update the shrink helpers."
        )


@dataclass(frozen=True)
class InRunShrinkEvent:
    """Telemetry payload describing a single in-run shrink pass."""

    tokens_before: int
    tokens_after: int
    context_window: int
    tool_returns_shrunk: int
    thinking_parts_dropped: int


# Trim notice appended to truncated tool-return content. The stable
# marker substring (``in-run trim``) lives in ``constants.context_guardrails``
# (``IN_RUN_TRIM_NOTICE_MARKER``) so dashboards, log scrapers, and tests
# can recognise a shrunk return without coupling to this private template.
_TRIM_NOTICE_TEMPLATE = (
    "\n\n…[" + IN_RUN_TRIM_NOTICE_MARKER + ": {elided} chars elided]"
)


def _stringify_tool_content(content: Any) -> str:
    """Serialise (possibly non-string) tool-return content to a string.

    ``ToolReturnPart.content`` is typed ``Any`` — tools may return dicts or
    lists. We serialise those with ``json.dumps`` rather than ``str`` so the
    model receives valid JSON (double-quoted keys, ``true``/``null`` literals)
    instead of Python ``repr`` output it can misparse. ``default=str`` absorbs
    stray non-JSON-serialisable values (datetimes, Decimals); if ``json.dumps``
    still fails we fall back to ``str`` so the shrink/estimate never crashes on
    exotic content.

    Used by both the token estimator and the actual shrink, so the
    pre-shrink estimate and the post-shrink payload are serialised
    identically.
    """
    if isinstance(content, str):
        return content
    try:
        return json.dumps(content, default=str)
    except (TypeError, ValueError, RecursionError):
        # All three are genuinely reachable, not defensive padding:
        #   - TypeError: ``default=str`` only rescues non-serialisable *values*;
        #     a dict with a non-string/number key (e.g. a tuple) still raises.
        #   - ValueError: out-of-range floats (NaN/Infinity) with a strict
        #     encoder, etc.
        #   - RecursionError: a self-referential (circular) tool return.
        # The fallback intent is "never crash on exotic content", so str() it.
        return str(content)


def _estimate_total_tokens(messages: list[ModelMessage], system_prompt: str) -> int:
    """Cheap upper-bound token estimate for the messages + system prompt."""
    total = estimate_token_count(system_prompt or "")
    for msg in messages:
        for part in getattr(msg, "parts", []):
            content = getattr(part, "content", None)
            if content is not None:
                total += estimate_token_count(_stringify_tool_content(content))
    return total


def _resolve_config(ctx: Any) -> tuple[CompactionConfig, str, str]:
    """Pull the relevant fields off ``ctx.deps``.

    ``deps.compaction`` is the canonical attribute (matches
    :class:`PydanticAIDependencies`). Missing or wrong-typed values fall
    back to module defaults so the processor never crashes on a
    misconfigured stub.
    """
    deps = getattr(ctx, "deps", None)
    if deps is None:
        return CompactionConfig(), "", ""
    direct = getattr(deps, "compaction", None)
    cfg = direct if isinstance(direct, CompactionConfig) else CompactionConfig()
    model_name = getattr(deps, "model_name", "") or ""
    system_prompt = getattr(deps, "system_prompt", "") or ""
    return cfg, model_name, system_prompt


def _split_protected_suffix(
    messages: list[ModelMessage], keep_recent_pairs: int
) -> tuple[list[ModelMessage], list[ModelMessage]]:
    """Return ``(older, recent)`` such that ``older + recent == messages``.

    The split point is the ``keep_recent_pairs``-th most-recent
    ``ModelResponse`` (counted from the tail). Every message at or after
    that index — including any trailing ``ModelRequest`` — is in
    ``recent``. The terminology "pairs" reflects the normal pydantic-ai
    flow where each ``ModelResponse`` is followed by exactly one
    ``ModelRequest`` (the response's tool returns + the next user turn);
    in an atypical history where multiple ``ModelRequest`` messages
    follow a single ``ModelResponse``, all of them stay together in the
    recent suffix because the split anchor is the response boundary.
    """
    if keep_recent_pairs <= 0 or not messages:
        return list(messages), []

    # Walk from the tail counting ModelResponse boundaries.
    cutoff = len(messages)
    responses_seen = 0
    for idx in range(len(messages) - 1, -1, -1):
        if isinstance(messages[idx], ModelResponse):
            responses_seen += 1
            if responses_seen >= keep_recent_pairs:
                cutoff = idx
                break

    if responses_seen < keep_recent_pairs:
        # Fewer than ``keep_recent_pairs`` pairs exist — everything is recent.
        return [], list(messages)

    return list(messages[:cutoff]), list(messages[cutoff:])


def _shrink_tool_return_part(
    part: ToolReturnPart, target_chars: int
) -> tuple[ToolReturnPart, bool]:
    """Return ``(maybe_shrunk_part, was_shrunk)``.

    For non-string contents (dict/list), serialises first (see
    :func:`_stringify_tool_content`) so the truncation arithmetic is
    uniform; the shrunk copy carries the serialised, truncated form so the
    model sees a string.

    ``target_chars`` bounds the preserved *prefix*, not the final string:
    the returned content is up to ``target_chars`` plus the length of the
    appended trim notice (``_TRIM_NOTICE_TEMPLATE`` — ~40 chars plus the
    digits of the elided count). Callers setting a tight ceiling should
    budget for that overhead.
    """
    content = _stringify_tool_content(part.content)

    if len(content) <= target_chars:
        return part, False

    truncated = content[:target_chars] + _TRIM_NOTICE_TEMPLATE.format(
        elided=len(content) - target_chars
    )
    return replace(part, content=truncated), True


def _shrink_message(
    msg: ModelMessage,
    *,
    target_chars: int,
    drop_thinking: bool,
) -> tuple[ModelMessage, int, int]:
    """Return ``(new_msg, returns_shrunk_delta, thinking_dropped_delta)``."""
    returns_shrunk = 0
    thinking_dropped = 0

    if isinstance(msg, ModelRequest):
        new_parts: list[Any] = []
        changed = False
        for part in msg.parts:
            if isinstance(part, ToolReturnPart):
                new_part, was_shrunk = _shrink_tool_return_part(part, target_chars)
                new_parts.append(new_part)
                if was_shrunk:
                    returns_shrunk += 1
                    changed = True
            else:
                new_parts.append(part)
        if changed:
            return replace(msg, parts=new_parts), returns_shrunk, 0
        return msg, 0, 0

    if isinstance(msg, ModelResponse):
        if not drop_thinking:
            return msg, 0, 0
        resp_parts: list[Any] = []
        changed = False
        for resp_part in msg.parts:
            if isinstance(resp_part, ThinkingPart):
                thinking_dropped += 1
                changed = True
                continue
            resp_parts.append(resp_part)
        # Guard: never produce an empty ModelResponse — if dropping
        # thinking would leave zero parts, keep the message intact.
        # Rare in practice (most ModelResponses also have a TextPart
        # or ToolCallPart), but the structural invariant matters more
        # than a single shrink.
        if changed and not resp_parts:
            return msg, 0, 0
        if changed:
            return replace(msg, parts=resp_parts), 0, thinking_dropped
        return msg, 0, 0

    return msg, 0, 0


async def shrink_old_artifacts_processor(
    ctx: RunContext,
    messages: list[ModelMessage],
) -> list[ModelMessage]:
    """Threshold-gated in-run history shrink. See module docstring."""
    try:
        cfg, model_name, system_prompt = _resolve_config(ctx)

        if not cfg.in_run_enabled:
            return messages

        if not messages:
            return messages

        tokens_before = _estimate_total_tokens(messages, system_prompt)
        # ``threshold_ratio`` is shared by design with the outer
        # turn-level compaction (in ``MessageHistoryService``). A single
        # ratio keeps the kick-in point coherent across both layers — if
        # the outer pass already wants to compact persisted history,
        # the in-loop pass should also be willing to shrink older
        # tool returns. Do not split into two ratios without rethinking
        # both call sites together. ``context_window_and_threshold`` is
        # the single definition of that kick-in point, shared verbatim
        # with the turn-level compaction functions.
        context_window, threshold = context_window_and_threshold(
            model_name, cfg.threshold_ratio
        )

        if tokens_before <= threshold:
            return messages

        older, recent = _split_protected_suffix(messages, cfg.in_run_keep_recent_pairs)
        if not older:
            # Nothing to shrink — everything is in the protected suffix.
            # This is a structural condition, not a degraded state, so log
            # at INFO rather than WARNING to avoid alarming production log
            # monitors that page on WARNING+ from this module.
            logger.info(
                "[history_processors] over threshold (%d > %d) but no older "
                "messages outside protected suffix of %d pairs; skipping",
                tokens_before,
                threshold,
                cfg.in_run_keep_recent_pairs,
            )
            return messages

        shrunk_older: list[ModelMessage] = []
        tool_returns_shrunk = 0
        thinking_parts_dropped = 0
        for msg in older:
            new_msg, dr, dt = _shrink_message(
                msg,
                target_chars=cfg.in_run_tool_return_target_chars,
                drop_thinking=cfg.in_run_drop_thinking,
            )
            shrunk_older.append(new_msg)
            tool_returns_shrunk += dr
            thinking_parts_dropped += dt

        if tool_returns_shrunk == 0 and thinking_parts_dropped == 0:
            # Structurally uncompressible by this processor (the older
            # prefix's bulk lives in UserPromptPart / TextPart, which the
            # in-run shrink intentionally does not touch). Log at INFO so
            # production log monitors don't page on a benign condition;
            # turn-level compaction (MessageHistoryService) handles the
            # uncompressible content on the next turn boundary.
            logger.info(
                "[history_processors] over threshold (%d > %d) but found no "
                "ToolReturnPart or ThinkingPart to shrink in the older prefix "
                "(%d messages); UserPromptPart is not compacted by the in-run "
                "processor — returning unchanged",
                tokens_before,
                threshold,
                len(older),
            )
            return messages

        new_messages = shrunk_older + recent
        tokens_after = _estimate_total_tokens(new_messages, system_prompt)

        event = InRunShrinkEvent(
            tokens_before=tokens_before,
            tokens_after=tokens_after,
            context_window=context_window,
            tool_returns_shrunk=tool_returns_shrunk,
            thinking_parts_dropped=thinking_parts_dropped,
        )

        logger.info(
            "[history_processors] In-run shrink: %d tool returns shrunk, "
            "%d thinking parts dropped, tokens %d → %d (window %d)",
            event.tool_returns_shrunk,
            event.thinking_parts_dropped,
            event.tokens_before,
            event.tokens_after,
            event.context_window,
        )

        callback = getattr(getattr(ctx, "deps", None), "on_in_run_shrink", None)
        if callable(callback):
            try:
                callback(event)
            except Exception:
                logger.exception(
                    "[history_processors] on_in_run_shrink callback raised"
                )

        return new_messages

    except Exception:
        # Defensive: a bug in the processor must never break the agent run.
        # Log and return original messages unchanged.
        logger.exception("[history_processors] processor raised; returning unchanged")
        return messages
