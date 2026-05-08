from __future__ import annotations

"""TimelineStreamMixin – build a reasoning timeline centrally.

Any agent adapter can inherit from this mix-in (in addition to
``CoreAgentBase``) and get a fully-featured ``stream`` implementation that:

1. Delegates to the adapter's private ``_stream_core`` coroutine which must
   yield ``UnifiedStreamEvent`` objects.
2. Collects these events via :class:`~opencontractserver.llms.agents.timeline_utils.TimelineBuilder`.
3. Injects the finished timeline into the *last* :class:`~opencontractserver.llms.agents.core_agents.FinalEvent`.

This guarantees that *every* framework yields a timeline without duplicate
book-keeping code.
"""

from collections.abc import AsyncGenerator
from typing import Any, cast

from .core_agents import FinalEvent, UnifiedStreamEvent
from .timeline_utils import TimelineBuilder

__all__ = ["TimelineStreamMixin"]


class TimelineStreamMixin:  # pylint: disable=too-few-public-methods
    """Mixin that adds automatic timeline construction to an agent."""

    # Adapters must override -------------------------------------------------
    async def _stream_core(  # noqa: D401
        self, message: str, **kwargs: Any
    ) -> AsyncGenerator[UnifiedStreamEvent]:
        """Yield events – to be implemented by concrete adapters."""
        raise NotImplementedError("_stream_core() must be implemented by adapter")
        # The unreachable yield turns this into an async generator so the
        # declared return type is honoured at runtime — concrete adapters
        # override this method with a real implementation.
        yield cast(UnifiedStreamEvent, None)

    # Public API -------------------------------------------------------------
    async def stream(
        self, message: str, **kwargs: Any
    ) -> AsyncGenerator[UnifiedStreamEvent]:
        """Wrapper that delegates to ``_stream_core`` and builds a timeline."""

        builder = TimelineBuilder()

        async for event in self._stream_core(message, **kwargs):
            # Keep building the timeline incrementally
            builder.add(event)

            # If this is the final chunk we make sure the timeline is present
            if isinstance(event, FinalEvent):
                meta = event.metadata or {}
                if "timeline" not in meta or not meta["timeline"]:
                    meta["timeline"] = builder.timeline
                event.metadata = meta  # ensure caller sees the injected timeline

                # ------------------------------------------------------------------
                # Persist to DB if the adapter exposes the helper – this removes
                # the need for each implementation to do the book-keeping.
                # ------------------------------------------------------------------
                finalise = getattr(self, "_finalise_llm_message", None)
                if callable(finalise):
                    try:
                        await finalise(
                            event.llm_message_id or 0,
                            event.accumulated_content or event.content,
                            event.sources,
                            meta.get("usage"),
                            meta["timeline"],
                        )
                    except Exception:  # pragma: no cover  – do *not* break streaming
                        # We log but continue yielding the event so the client
                        # still receives the answer even if persistence fails.
                        import logging

                        logging.getLogger(__name__).exception(
                            "Failed to persist LLM message with timeline"
                        )

            # Forward unchanged event to caller
            yield event
