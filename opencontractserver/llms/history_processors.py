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

import dataclasses
import logging
from dataclasses import dataclass
from typing import Any

from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    ThinkingPart,
    ToolReturnPart,
)

from opencontractserver.llms.context_guardrails import (
    CompactionConfig,
    estimate_token_count,
    get_context_window_for_model,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class InRunShrinkEvent:
    """Telemetry payload describing a single in-run shrink pass."""

    tokens_before: int
    tokens_after: int
    context_window: int
    tool_returns_shrunk: int
    thinking_parts_dropped: int


# Trim notice appended to truncated tool-return content. Stable string so
# tests and the model can both recognise it.
_TRIM_NOTICE_TEMPLATE = "\n\n…[in-run trim: {elided} chars elided]"


def _estimate_total_tokens(messages: list[ModelMessage], system_prompt: str) -> int:
    """Cheap upper-bound token estimate for the messages + system prompt."""
    total = estimate_token_count(system_prompt or "")
    for msg in messages:
        for part in getattr(msg, "parts", []):
            content = getattr(part, "content", None)
            if isinstance(content, str):
                total += estimate_token_count(content)
            elif content is not None:
                # Tool returns can be non-string (lists/dicts); stringify
                # cheaply for estimation.
                total += estimate_token_count(str(content))
    return total


def _resolve_config(ctx: Any) -> tuple[CompactionConfig, str, str]:
    """Pull the relevant fields off ``ctx.deps`` with defensive fallbacks."""
    deps = getattr(ctx, "deps", None)
    cfg: CompactionConfig
    if deps is None:
        cfg = CompactionConfig()
        model_name = ""
        system_prompt = ""
    else:
        # ``config_compaction`` is the test-fake field name. Production
        # code path: ``deps.config.compaction``. Both supported.
        if hasattr(deps, "config_compaction"):
            cfg = getattr(deps, "config_compaction") or CompactionConfig()
        else:
            config = getattr(deps, "config", None)
            cfg = getattr(config, "compaction", None) or CompactionConfig()
        model_name = getattr(deps, "model_name", "") or ""
        system_prompt = getattr(deps, "system_prompt", "") or ""
    return cfg, model_name, system_prompt


def _split_protected_suffix(
    messages: list[ModelMessage], keep_recent_pairs: int
) -> tuple[list[ModelMessage], list[ModelMessage]]:
    """Return ``(older, recent)`` such that ``older + recent == messages``.

    ``recent`` contains the last ``keep_recent_pairs`` pairs of
    ModelResponse+ModelRequest plus any trailing leading ModelRequest
    (so the final ``ModelRequest`` invariant is preserved).
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
    """Return ``(maybe_shrunk_part, was_shrunk)``."""
    content = part.content
    if not isinstance(content, str):
        # Non-string returns (dict/list) — stringify length check only.
        content = str(content)
        if len(content) <= target_chars:
            return part, False
        # Coerce to string in the shrunk copy so the model sees a string.
        truncated = content[:target_chars] + _TRIM_NOTICE_TEMPLATE.format(
            elided=len(content) - target_chars
        )
        return (
            dataclasses.replace(part, content=truncated),
            True,
        )

    if len(content) <= target_chars:
        return part, False

    truncated = content[:target_chars] + _TRIM_NOTICE_TEMPLATE.format(
        elided=len(content) - target_chars
    )
    return dataclasses.replace(part, content=truncated), True


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
            return dataclasses.replace(msg, parts=new_parts), returns_shrunk, 0
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
        if changed:
            return dataclasses.replace(msg, parts=resp_parts), 0, thinking_dropped
        return msg, 0, 0

    return msg, 0, 0


async def shrink_old_artifacts_processor(
    ctx: Any,
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
        context_window = get_context_window_for_model(model_name)
        threshold = int(context_window * cfg.threshold_ratio)

        if tokens_before <= threshold:
            return messages

        older, recent = _split_protected_suffix(messages, cfg.in_run_keep_recent_pairs)
        if not older:
            # Nothing to shrink — everything is in the protected suffix.
            logger.warning(
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
            logger.warning(
                "[history_processors] over threshold (%d > %d) but found "
                "no ToolReturnPart or ThinkingPart to shrink in the older "
                "prefix (%d messages); returning unchanged",
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
            except Exception:  # pragma: no cover - defensive
                logger.exception(
                    "[history_processors] on_in_run_shrink callback raised"
                )

        return new_messages

    except Exception:
        # Defensive: a bug in the processor must never break the agent run.
        # Log and return original messages unchanged.
        logger.exception("[history_processors] processor raised; returning unchanged")
        return messages
