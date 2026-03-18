# Anonymous Ephemeral Chat — Design Spec

## Problem

When anonymous (not logged in) users chat with a public corpus:
1. **Timeline shows "0 steps"** — frontend receives timeline data via WebSocket but never stores it in message state
2. **Context bar shows "0%"** — backend returns `estimated_tokens=0` because `CoreConversationManager` has `conversation=None` and returns empty history
3. **No multi-turn conversation** — each message is independent; the LLM has no memory of prior exchanges in the session
4. **No compaction available** — anonymous users can't compact context, so they hit a hard wall with no guidance

## Solution

In-memory ephemeral conversation tracking on the backend, plus frontend fixes for timeline storage and a "context exhausted" UX.

**No DB changes. No migrations. No new models.** Everything is scoped to the WebSocket session lifetime.

---

## Backend Changes

### 1. CoreConversationManager — Ephemeral Message Buffer

**File**: `opencontractserver/llms/agents/core_agents.py`

When `conversation=None` (anonymous user):

- Add `_ephemeral_messages: list` field, initialized to `[]`
- Add `_ephemeral_token_estimate: int` field, initialized to `0`
- Add `_ephemeral_next_id: int` counter, initialized to `1` (for synthetic message IDs)

**Ephemeral message format**: Messages in the buffer must be duck-typed objects compatible with `_get_message_history()`, which accesses `.msg_type`, `.content`, and `.id` via attribute access (not dict keys). Use `types.SimpleNamespace` or a lightweight `@dataclass`:

```python
from types import SimpleNamespace

ephemeral_msg = SimpleNamespace(
    id=self._ephemeral_next_id,
    msg_type="HUMAN",      # or "AI" — matches ChatMessage.msg_type values
    content=text,
    created=timezone.now(),
)
```

**Method changes**:

| Method | Current (anonymous) | New (anonymous) |
|--------|-------------------|-----------------|
| `store_user_message()` | Returns `0` | Append ephemeral msg (`msg_type="HUMAN"`) to buffer, update token estimate, return synthetic ID |
| `complete_message()` | No-op | Append ephemeral msg (`msg_type="AI"`) to buffer, update token estimate |
| `update_message()` | No-op | Update matching message in buffer by synthetic ID, recalculate token estimate |
| `get_conversation_messages()` | Returns `[]` | Return `_ephemeral_messages` |
| `create_placeholder_message()` | Returns `0` | Return next synthetic ID |

**Critical: store_* config flags**: Currently, `create_for_corpus()` sets `config.store_user_messages = False` and `config.store_llm_messages = False` for anonymous users, which causes the caller (`CoreAgentBase.stream()`) to skip `store_user_message()` and `complete_message()` entirely. Fix: set both flags to `True` for ephemeral conversations — the methods will write to the in-memory buffer, not the DB, so this is safe. Alternatively, add a separate `config.ephemeral = True` flag and check it alongside the store flags in the stream pipeline.

**Token estimation**: Use existing `CHARS_PER_TOKEN_ESTIMATE` heuristic (len(text) / 3.5). Accumulate in `_ephemeral_token_estimate` on each append.

**Context status**: `_get_message_history()` in the agent will now receive real messages from the buffer (duck-typed with `.msg_type`, `.content`, `.id`), producing accurate `estimated_tokens` and `context_window` in `context_status`.

**Compaction**: Compaction is a no-op for ephemeral conversations. `_get_message_history()` may attempt the compaction path, but `persist_compaction()` already no-ops when `conversation` is None. No changes needed — just verify the path doesn't crash on ephemeral message objects.

**Context exhausted check**: Add a property `context_exhausted: bool` that returns `True` when `_ephemeral_token_estimate > context_window * 0.9`. The `context_window` value is obtained by calling `get_context_window_for_model(model_name)` from `opencontractserver/llms/context_guardrails.py` (NOT from `AgentConfig`, which doesn't have this field). The 10% headroom reserves space for the next response.

### 2. UnifiedAgentConsumer — Cutoff Check

**File**: `config/websocket/consumers/unified_agent_conversation.py`

In the `receive()` method, **after** `_initialize_agent()` has been called (the agent is lazily initialized on the first message) but **before** `_stream_agent_response()`:

```python
if self.agent and self.agent.conversation_manager.context_exhausted:
    await self._send_safe(
        msg_type="ASYNC_ERROR",
        content="This conversation has reached its context limit. Please start a new chat to continue.",
        data={
            "error_type": "CONTEXT_EXHAUSTED",
        },
    )
    return
```

**New `error_type` field**: The existing ASYNC_ERROR data payload (`{"error": ..., "message_id": ..., "metadata": ...}`) does not include an `error_type` field. Add `error_type` as a new optional field in the `data` dict. The frontend must check for this field to distinguish context exhaustion from other errors.

**Cleanup**: In-memory buffer freed automatically when WebSocket disconnects. No explicit cleanup needed.

---

## Frontend Changes

### 3. CorpusChat.tsx — Timeline Storage Fix

**File**: `frontend/src/components/corpuses/CorpusChat.tsx`

Note: `useAgentChat.ts` exists but is **not imported by any component** — CorpusChat has its own inline WebSocket handling with the same bugs. Fixes target CorpusChat directly.

**Bug 1 — `finalizeStreamingResponse` (~line 682)**:
Currently sets `hasTimeline` flag but never assigns the actual timeline data to the message object.

Fix: Add `timeline: timelineData` to the message update.

**Bug 2 — `handleCompleteMessage`**:
Accepts `timelineData` parameter but never applies it to the message state.

Fix: Add `timeline: timelineData || existingMsg.timeline` to the message update.

These fixes benefit all users — authenticated users get immediate timeline display without waiting for GraphQL refetch.

### 4. CorpusChat.tsx — Context Exhausted UX

**File**: `frontend/src/components/corpuses/CorpusChat.tsx`

In CorpusChat's own `onmessage` handler (~line 345), handle the `CONTEXT_EXHAUSTED` error type in the existing `ASYNC_ERROR` case (~line 437):

- Check `data?.error_type === "CONTEXT_EXHAUSTED"`
- Set a new `contextExhausted` state flag to `true`
- Display a banner above the chat input:
  - Text: "This conversation has reached its context limit."
  - Button: "Start New Chat" (calls existing `startNewChat()` which resets state + creates fresh WebSocket connection with a new empty buffer)
- Disable chat input and send button while `contextExhausted` is `true`

**Context meter**: No changes needed — it will now show real accumulation since the backend sends accurate `context_status` with each `ASYNC_FINISH`. CorpusChat has its own `contextStatus` state and `setContextStatus()` call that already handles this. Existing color thresholds (green/yellow/red) apply. No compaction banner for anonymous users since `was_compacted` is always `false`.

---

## Scope Boundaries

**In scope**:
- In-memory message buffer for anonymous sessions
- Accurate context tracking and multi-turn conversation
- Timeline display fix (benefits all users)
- Hard cutoff with "Start New Chat" UX

**Out of scope**:
- Persisting anonymous conversations to DB
- Anonymous conversation compaction
- Message count caps or TTLs
- Changes to authenticated user flow
