"""JSON-Schema and typing helpers for the *timeline* stored in ChatMessage.metadata.

Every streamed LLM reply now stores a `timeline` list under
`ChatMessage.data['timeline']` (see pydantic-ai and future adapters).

This module centralises the shape of those entries so that:

1. **Runtime validation** (optional): call ``jsonschema.validate(entry,
   TIMELINE_ENTRY_SCHEMA)`` if you need to assert a payload is correct.
2. **Static typing**: import ``TimelineEntry`` (a ``TypedDict``) for
   type-checking in editors / CI.
"""

from __future__ import annotations

from typing import Any, Literal, NotRequired, TypedDict

# ---------------------------------------------------------------------------
# JSON-Schema (Draft-2020-12)
# ---------------------------------------------------------------------------

TIMELINE_ENTRY_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "LLM-Stream Timeline Entry",
    "type": "object",
    "required": ["type"],
    "properties": {
        "type": {
            "type": "string",
            "enum": [
                "thought",
                "content",
                "tool_call",
                "tool_result",
                "sources",
                "status",
            ],
        },
        "text": {"type": "string"},
        "tool": {"type": "string"},
        "args": {},
        # Truncated tool output (max 500 chars). Present on tool_result entries
        # when the backend captures the tool's return value.
        "result": {"type": "string"},
        "count": {"type": "integer", "minimum": 0},
        "metadata": {"type": "object"},
        "msg": {"type": "string"},
    },
    "unevaluatedProperties": False,
}


# ---------------------------------------------------------------------------
# TypedDict for editors / mypy
# ---------------------------------------------------------------------------


class TimelineEntry(TypedDict, total=False):
    """A single element in the reasoning *timeline*.

    This mirrors ``TIMELINE_ENTRY_SCHEMA`` – keep both in sync!
    """

    type: Literal["thought", "content", "tool_call", "tool_result", "sources", "status"]
    text: NotRequired[str]
    tool: NotRequired[str]
    args: NotRequired[Any]
    result: NotRequired[str]  # Truncated tool output (tool_result entries only)
    count: NotRequired[int]
    metadata: NotRequired[dict[str, Any]]
    msg: NotRequired[str]
