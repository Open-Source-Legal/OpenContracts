"""Shared types and enums for the OpenContracts LLM framework."""

from enum import Enum
from typing import Any, Protocol


class AgentFramework(Enum):
    """Supported agent frameworks."""

    PYDANTIC_AI = "pydantic_ai"


# ------------------------------------------------------------------
# Side-channel streaming helper
# ------------------------------------------------------------------


class StreamObserver(Protocol):
    """Callable that receives live ``UnifiedStreamEvent`` objects.

    Framework adapters will call this observer *whenever* they emit a
    chunk, allowing the host application (e.g. WebSocket layer) to forward
    nested or cross-agent events in real time.

    .. important::
       Must be kept in sync with
       :class:`opencontractserver.types.protocols.StreamObserverProtocol`,
       which mirrors this contract for non-LLM consumers that cannot
       import the ``llms`` package without circular-import risk.
    """

    async def __call__(self, event: Any) -> None: ...
