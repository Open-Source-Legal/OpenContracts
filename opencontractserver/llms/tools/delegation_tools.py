"""Per-turn delegation tool factory for the rich-mention agent system.

Spec: ``docs/architecture/rich_mentions.md``

This module provides scope-aware filtering of ``AgentConfiguration`` rows for
chat delegation, and the per-turn tool factory used by the consumer to expose
available sub-agents to the orchestrator LLM as ``delegate_to_<slug>`` tools.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable
from dataclasses import dataclass
from typing import Any, Callable

from asgiref.sync import sync_to_async
from django.db.models import Q, QuerySet

from opencontractserver.agents.models import AgentConfiguration
from opencontractserver.documents.models import DocumentPath
from opencontractserver.llms.tools.tool_factory import CoreTool, ToolMetadata

logger = logging.getLogger(__name__)


def filter_by_scope(
    qs: QuerySet[AgentConfiguration],
    *,
    corpus_id: int | None,
    document_id: int | None,
) -> QuerySet[AgentConfiguration]:
    """Restrict an agent queryset to those usable in the current chat scope.

    Rules (matching the spec's scope matrix):
      - standalone doc chat (no corpus, no doc, OR a doc with no current
        corpus membership): GLOBAL agents only.
      - corpus chat: GLOBAL agents plus agents owned by that corpus.
      - doc-in-corpus chat: GLOBAL agents plus agents owned by the doc's
        active corpus.

    The Document <-> Corpus relation in this codebase is mediated by
    ``DocumentPath`` (no direct FK/M2M on ``Document``). We resolve the
    document's *current, non-deleted* path to determine its corpus.

    Args:
        qs: Base queryset of ``AgentConfiguration`` rows (typically already
            permission-filtered via ``visible_to_user``).
        corpus_id: Active corpus id for the chat, or ``None``.
        document_id: Active document id for the chat, or ``None``.

    Returns:
        A queryset filtered to the agents valid for the given chat scope.
    """
    if not corpus_id and not document_id:
        return qs.filter(scope="GLOBAL")

    if corpus_id:
        return qs.filter(Q(scope="GLOBAL") | Q(corpus_id=corpus_id))

    # document_id only — resolve its current corpus via DocumentPath.
    # The outer guard ensures ``document_id`` is non-None here; assert for
    # the type checker so the FK lookup receives ``int`` (not ``int | None``).
    assert document_id is not None
    doc_corpus_id = (
        DocumentPath.objects.filter(
            document_id=document_id,
            is_current=True,
            is_deleted=False,
        )
        .values_list("corpus_id", flat=True)
        .first()
    )
    if doc_corpus_id:
        return qs.filter(Q(scope="GLOBAL") | Q(corpus_id=doc_corpus_id))
    return qs.filter(scope="GLOBAL")


# ---------------------------------------------------------------------------
# StreamRelay + build_delegation_tool
# ---------------------------------------------------------------------------


@dataclass
class StreamRelay:
    """Bridge from a sub-agent's event stream back through the WebSocket.

    Constructed by the consumer (which owns the socket) inside a per-turn
    ``relay_factory`` and passed into the delegation tool body. The tool body
    forwards sub-agent events through these callables; the consumer's factory
    is responsible for adding metadata enrichment (agent_id,
    parent_message_id, requesting_agent) before sending each frame.

    Attributes:
        parent_message_id: Identifier of the conductor LLM message this
            sub-agent run is delegating *from*. The consumer uses this to
            attribute timeline entries and pinned bubbles back to the parent
            turn.
        agent: The ``AgentConfiguration`` of the sub-agent being invoked.
        pin: Whether the sub-agent's output should be rendered as a fully
            pinned message bubble (``True``) or only surfaced via the
            conductor's timeline as a tool_call / tool_result pair
            (``False``).
        on_token: Awaitable invoked with each ContentEvent delta. Only
            called when ``pin`` is true.
        on_thought: Awaitable invoked with each ThoughtEvent — receives
            ``(thought_text, metadata_dict)``.
        on_approval: Awaitable invoked when the sub-agent emits an
            ApprovalNeededEvent; the consumer may return a value (e.g. the
            approval message id) but the tool body does not require one.
        on_finish: Awaitable invoked with the final concatenated text. The
            consumer returns the persisted message id (or ``None``) so the
            tool body can echo it back to the conductor.
    """

    parent_message_id: str
    agent: AgentConfiguration
    pin: bool
    on_token: Callable[[str], Awaitable[None]]
    on_thought: Callable[[str, dict], Awaitable[None]]
    on_approval: Callable[[dict], Awaitable[Any]]
    on_finish: Callable[[str], Awaitable[int | None]]


def _slug_to_snake_case(slug: str) -> str:
    """Convert a kebab-case agent slug to snake_case for tool names."""
    return slug.replace("-", "_").lower()


def build_delegation_tool(
    agent: AgentConfiguration,
    *,
    relay_factory: Callable[[AgentConfiguration, bool], StreamRelay | None],
    user: Any,
    corpus: Any,
    document: Any,
    conversation: Any,
) -> CoreTool:
    """Materialize a ``delegate_to_<slug>`` ``CoreTool`` for one target agent.

    When the conductor invokes this tool, the body:

      1. Re-checks visibility (race with concurrent re-permissioning).
      2. Builds a fresh sub-agent for ``agent`` via the same factory the
         consumer uses for the conductor (``agents.for_document`` /
         ``agents.for_corpus``). No conversation history is shared.
      3. Streams sub-agent events through ``relay_factory(agent, pin)``
         (returned ``StreamRelay`` may be ``None`` when ``pin`` is false and
         the consumer chooses not to wire token-level forwarding).
      4. Returns ``{"result": <final_text>, "pinned_message_id": <id_or_None>}``
         to the conductor LLM.

    Args:
        agent: The pre-resolved target ``AgentConfiguration`` (already
            verified visible to ``user`` at parse time).
        relay_factory: Per-turn callable supplied by the consumer that
            constructs a ``StreamRelay`` (or returns ``None`` to opt out of
            relay-based event forwarding) for each delegation invocation.
        user: The end user driving the conversation (used for re-check and
            sub-agent attribution).
        corpus: Active corpus for the chat, or ``None``.
        document: Active document for the chat, or ``None``.
        conversation: Active conversation object (currently unused — sub
            agents run with no shared history per the spec — but kept on the
            signature so Task 7 can plumb it through if needed).

    Returns:
        A ``CoreTool`` whose ``function`` is an async coroutine accepting
        ``prompt: str`` and ``pin: bool`` and returning a dict.

    Spec: ``docs/architecture/rich_mentions.md``
    """

    snake_slug = _slug_to_snake_case(agent.slug or "")
    tool_name = f"delegate_to_{snake_slug}"
    description = (
        agent.description
        if agent.description
        else f"Delegate this turn to @{agent.slug}."
    )

    # Capture the agent id; we re-fetch on each invocation against the user's
    # visible queryset to guard against concurrent re-permissioning.
    agent_pk = agent.pk
    agent_slug = agent.slug

    async def _body(prompt: str, pin: bool = False) -> dict[str, Any]:
        # Race guard: visible at parse time but possibly gone now.
        still_visible = await sync_to_async(
            lambda: AgentConfiguration.objects.visible_to_user(user)
            .filter(pk=agent_pk, is_active=True)
            .exists()
        )()
        if not still_visible:
            return {
                "result": "Delegation target is no longer available.",
                "pinned_message_id": None,
            }

        relay = relay_factory(agent, pin)

        # Build the sub-agent using the same factory the conductor uses.
        # Local import avoids a circular dependency at module load time
        # (``api`` pulls in tools, which pulls in this module).
        from opencontractserver.llms import agents as agents_api

        user_id = getattr(user, "id", None) if user is not None else None

        try:
            if document is not None:
                sub_agent = await agents_api.for_document(
                    document=document,
                    corpus=corpus,
                    user_id=user_id,
                )
            elif corpus is not None:
                sub_agent = await agents_api.for_corpus(
                    corpus=corpus,
                    user_id=user_id,
                )
            else:
                # No doc/corpus context — by the scope matrix every chat
                # has at least one of these set, so reaching this branch
                # means the consumer wired the tool incorrectly. Fail soft
                # by reporting back to the LLM rather than crashing the
                # turn.
                logger.warning(
                    "[delegate_to_%s] Cannot start sub-agent: no document or "
                    "corpus context was provided.",
                    snake_slug,
                )
                return {
                    "result": (
                        "Sub-agent could not start: no document or corpus "
                        "context is available for delegation."
                    ),
                    "pinned_message_id": None,
                }
        except Exception as exc:  # operational: surface to LLM, don't crash
            logger.warning(
                "[delegate_to_%s] Failed to build sub-agent: %s", snake_slug, exc
            )
            return {
                "result": f"Could not start sub-agent @{agent_slug}: {exc}",
                "pinned_message_id": None,
            }

        # Announce delegation start when pinned (timeline-only case is
        # handled by the consumer via the tool_call/tool_result it emits
        # around the call itself).
        if pin and relay is not None:
            await relay.on_thought(
                f"Delegating to @{agent_slug}",
                {
                    "tool_name": tool_name,
                    "args": {"prompt": prompt, "pin": pin},
                    "agent_id": agent_pk,
                    "agent_slug": agent_slug,
                },
            )

        accumulated: list[str] = []
        try:
            async for event in sub_agent.stream(prompt):
                evt_type = getattr(event, "type", None)
                content = getattr(event, "content", "") or ""

                if evt_type == "content":
                    if content:
                        accumulated.append(content)
                        if pin and relay is not None:
                            await relay.on_token(content)
                elif evt_type == "thought":
                    if relay is not None:
                        thought_text = getattr(event, "thought", "") or content
                        await relay.on_thought(
                            thought_text,
                            dict(getattr(event, "metadata", {}) or {}),
                        )
                elif evt_type == "approval_needed":
                    if relay is not None:
                        pending = dict(getattr(event, "pending_tool_call", {}) or {})
                        await relay.on_approval(pending)
                elif evt_type == "final":
                    # Final event carries the full accumulated content; if
                    # we never saw a content delta (e.g. non-streaming
                    # framework path), use the final's accumulated_content
                    # as a fallback.
                    if not accumulated:
                        final_content = (
                            getattr(event, "accumulated_content", "") or content or ""
                        )
                        if final_content:
                            accumulated.append(final_content)
                elif evt_type == "error":
                    err = getattr(event, "error", "") or "unknown error"
                    logger.warning(
                        "[delegate_to_%s] Sub-agent emitted error: %s",
                        snake_slug,
                        err,
                    )
                    return {
                        "result": f"Sub-agent error: {err}",
                        "pinned_message_id": None,
                    }
                # ``sources``, ``approval_result``, ``resume`` events are
                # not forwarded over the relay — the conductor doesn't need
                # them, and the relay's surface is intentionally minimal.
        except PermissionError:
            # Security exceptions propagate per the fault-tolerance contract.
            raise
        except Exception as exc:  # operational
            logger.warning(
                "[delegate_to_%s] Sub-agent stream failed: %s", snake_slug, exc
            )
            return {
                "result": f"Sub-agent error: {exc}",
                "pinned_message_id": None,
            }

        final_text = "".join(accumulated)
        pinned_id: int | None = None
        if pin and relay is not None:
            try:
                pinned_id = await relay.on_finish(final_text)
            except Exception as exc:  # operational
                logger.warning("[delegate_to_%s] on_finish failed: %s", snake_slug, exc)

        return {"result": final_text, "pinned_message_id": pinned_id}

    metadata = ToolMetadata(
        name=tool_name,
        description=description,
        parameter_descriptions={
            "prompt": "The instruction to send to the sub-agent for this turn.",
            "pin": (
                "If true, the sub-agent's reply is rendered as a pinned "
                "message bubble attributed to it; if false the reply is "
                "only surfaced as a tool_call/tool_result in the conductor's "
                "reasoning timeline."
            ),
        },
    )

    return CoreTool(
        function=_body,
        metadata=metadata,
        requires_approval=False,
        requires_corpus=False,
        requires_write_permission=False,
    )
