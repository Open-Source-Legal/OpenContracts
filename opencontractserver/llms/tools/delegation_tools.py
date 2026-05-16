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
from opencontractserver.llms.exceptions import ToolConfirmationRequired
from opencontractserver.llms.tools.tool_factory import CoreTool, ToolMetadata

logger = logging.getLogger(__name__)


# Maximum number of approval cycles per delegation tool call.
# An "approval cycle" = sub-agent emits ApprovalNeededEvent -> user
# decides -> sub-agent resumes.  Each cycle counts once.  Bounded to
# prevent pathological loops (e.g. a malformed agent that keeps
# triggering approvals on the same tool indefinitely).
MAX_DELEGATION_APPROVAL_CYCLES = 8


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

    Sync context required: when ``document_id`` is set the function hits
    ``DocumentPath`` via the sync ORM (``.values_list(...).first()``).
    Call from a sync function or wrap the call in ``sync_to_async`` /
    ``database_sync_to_async`` when invoking from an async context —
    otherwise Django will raise ``SynchronousOnlyOperation`` deep in the
    ORM with a confusing traceback.  The lone caller today is
    ``_resolve_delegation_targets`` in the WebSocket consumer, which
    already wraps the lookup in ``database_sync_to_async``.

    Args:
        qs: Base queryset of ``AgentConfiguration`` rows (typically already
            permission-filtered via ``visible_to_user``).
        corpus_id: Active corpus id for the chat, or ``None``.
        document_id: Active document id for the chat, or ``None``.

    Returns:
        A queryset filtered to the agents valid for the given chat scope.
    """
    if not corpus_id and not document_id:
        return qs.filter(scope=AgentConfiguration.SCOPE_GLOBAL)

    if corpus_id:
        return qs.filter(
            Q(scope=AgentConfiguration.SCOPE_GLOBAL) | Q(corpus_id=corpus_id)
        )

    # document_id only — resolve its current corpus via DocumentPath.
    # The outer guard already ensures ``document_id`` is non-None here, but
    # use an explicit runtime check rather than ``assert``: assertions are
    # stripped under ``python -O`` and a stray ``None`` reaching the FK
    # lookup would raise an unhelpful ``TypeError`` deep in the sync ORM
    # thread.
    if document_id is None:  # pragma: no cover - defensive: outer guard above
        return qs.filter(scope=AgentConfiguration.SCOPE_GLOBAL)
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
        return qs.filter(
            Q(scope=AgentConfiguration.SCOPE_GLOBAL) | Q(corpus_id=doc_corpus_id)
        )
    return qs.filter(scope=AgentConfiguration.SCOPE_GLOBAL)


# ---------------------------------------------------------------------------
# StreamRelay + build_delegation_tool
# ---------------------------------------------------------------------------


@dataclass
class StreamRelay:
    """Bridge from a sub-agent's event stream back through the WebSocket.

    Constructed by the consumer (which owns the socket) inside a per-turn
    ``relay_factory`` and passed into the delegation tool body.  The tool body
    forwards sub-agent events through these callables; the consumer's factory
    is responsible for adding metadata enrichment (agent_id,
    parent_message_id, requesting_agent) before sending each frame.

    The conductor's ``parent_message_id`` is NOT carried on this dataclass:
    it is captured lazily by the consumer's relay closures via a shared
    one-slot box that is filled in once the conductor emits its first
    streamed event.  Persisting it on the dataclass would require either
    constructing the relay after that first event (defeating the per-turn
    factory pattern) or carrying stale ``None``/empty values, so the field
    was removed and the closures read the box directly.

    Attributes:
        agent: The ``AgentConfiguration`` of the sub-agent being invoked.
        pin: Whether the sub-agent's output should be rendered as a fully
            pinned message bubble (``True``) or only surfaced via the
            conductor's timeline as a tool_call / tool_result pair
            (``False``).
        on_token: Awaitable invoked with each ContentEvent delta.  Only
            called when ``pin`` is true.
        on_thought: Awaitable invoked with each ThoughtEvent — receives
            ``(thought_text, metadata_dict)``.
        on_approval: Awaitable invoked when the sub-agent emits an
            ApprovalNeededEvent; the consumer may return a value (e.g. the
            approval message id) but the tool body does not require one.
        on_finish: Awaitable invoked with the final concatenated text.  The
            consumer returns the persisted message id (or ``None``) so the
            tool body can echo it back to the conductor.
    """

    agent: AgentConfiguration
    pin: bool
    on_token: Callable[[str], Awaitable[None]]
    on_thought: Callable[[str, dict], Awaitable[None]]
    on_approval: Callable[[dict], Awaitable[Any]]
    on_finish: Callable[[str], Awaitable[int | None]]


def _slug_to_snake_case(slug: str) -> str:
    """Convert a kebab-case agent slug to snake_case for tool names.

    Two slugs differing only in their ``-`` vs ``_`` separator would map to
    the same snake-case tool name (e.g. ``my-agent`` and ``my_agent`` both
    become ``delegate_to_my_agent``).  This collision is guarded by the DB:
    ``AgentConfiguration.slug`` is ``SlugField(unique=True)``, and slugify
    normalizes to ``-`` so legacy ``_`` slugs cannot be created via the
    normal save() path.  The unique-constraint guarantee is the single
    source of truth here; no additional in-process check is needed.
    """
    return slug.replace("-", "_").lower()


def build_delegation_tool(
    agent: AgentConfiguration,
    *,
    relay_factory: Callable[[AgentConfiguration, bool], StreamRelay],
    user: Any,
    corpus: Any,
    document: Any,
) -> CoreTool:
    """Materialize a ``delegate_to_<slug>`` ``CoreTool`` for one target agent.

    When the conductor invokes this tool, the body:

      1. Re-checks visibility (race with concurrent re-permissioning).
      2. Builds a fresh sub-agent for ``agent`` via the same factory the
         consumer uses for the conductor (``agents.for_document`` /
         ``agents.for_corpus``). No conversation history is shared.
      3. Streams sub-agent events through ``relay_factory(agent, pin)``.
         The relay is always constructed; it internally short-circuits
         per-frame forwarding based on ``pin`` (e.g. unpinned delegations
         skip ``on_token`` / ``on_thought`` because the conductor's own
         ``tool_call`` / ``tool_result`` pair already surfaces them).
      4. Returns ``{"result": <final_text>, "pinned_message_id": <id_or_None>}``
         to the conductor LLM.

    Args:
        agent: The pre-resolved target ``AgentConfiguration`` (already
            verified visible to ``user`` at parse time).
        relay_factory: Per-turn callable supplied by the consumer that
            constructs a ``StreamRelay`` for each delegation invocation.
            The relay is always built; whether individual forwarders are
            no-ops is decided inside the relay based on the ``pin`` flag.
        user: The end user driving the conversation (used for re-check and
            sub-agent attribution).
        corpus: Active corpus for the chat, or ``None``.
        document: Active document for the chat, or ``None``.

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
        # Race guard #1: agent visible at parse time but possibly gone now.
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

        # Race guard #2: document/corpus access can be revoked mid-turn.
        # The ORM instances were captured at tool-build time (once per turn),
        # so a permission revocation between mention parse and tool fire
        # would otherwise still hand the sub-agent the stale objects. Re-
        # check visibility against the current state of the DB. Imports are
        # local to keep the module load surface minimal.
        if document is not None:
            from opencontractserver.documents.models import Document as _Document

            doc_accessible = await sync_to_async(
                lambda: _Document.objects.visible_to_user(user)
                .filter(pk=document.pk)
                .exists()
            )()
            if not doc_accessible:
                return {
                    "result": "Document is no longer accessible.",
                    "pinned_message_id": None,
                }
        if corpus is not None:
            from opencontractserver.corpuses.models import Corpus as _Corpus

            corpus_accessible = await sync_to_async(
                lambda: _Corpus.objects.visible_to_user(user)
                .filter(pk=corpus.pk)
                .exists()
            )()
            if not corpus_accessible:
                return {
                    "result": "Corpus is no longer accessible.",
                    "pinned_message_id": None,
                }

        relay = relay_factory(agent, pin)

        # Build the sub-agent using the same factory the conductor uses.
        # Local import avoids a circular dependency at module load time
        # (``api`` pulls in tools, which pulls in this module).
        from opencontractserver.llms import agents as agents_api

        user_id = getattr(user, "id", None) if user is not None else None

        # Build kwargs common to both factory calls. ``persist=False`` keeps
        # the sub-agent ephemeral so it does NOT spawn a parallel ChatMessage
        # stream on the parent conversation (spec: sub-agents are ephemeral
        # and surface back to the conductor turn). ``system_prompt`` honours
        # the selected ``AgentConfiguration``'s instructions; the underlying
        # ``api.for_*`` plumbs this through to pydantic-ai's ``instructions=``
        # kwarg (see CLAUDE.md pitfall #14 — ``system_prompt`` would be
        # dropped if passed directly to ``PydanticAIAgent``, but the API
        # layer here normalises it for us).
        common_kwargs: dict[str, Any] = {
            "user_id": user_id,
            "persist": False,
        }
        if agent.system_instructions:
            common_kwargs["system_prompt"] = agent.system_instructions

        try:
            if document is not None:
                sub_agent = await agents_api.for_document(
                    document=document,
                    corpus=corpus,
                    **common_kwargs,
                )
            elif corpus is not None:
                sub_agent = await agents_api.for_corpus(
                    corpus=corpus,
                    **common_kwargs,
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
        except (PermissionError, ToolConfirmationRequired):
            # Security exceptions propagate per the fault-tolerance contract
            # (CLAUDE.md pitfall #13 / pydantic_ai_tools.py:560).
            raise
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
        # around the call itself).  ``relay`` is non-Optional per the
        # tightened factory contract — short-circuiting based on ``pin``
        # alone is sufficient here.
        if pin:
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

        async def _drain_stream(stream_iter) -> tuple[bool, dict[str, Any] | None]:
            """Process events from one ``stream`` (or ``resume_with_approval``)
            iteration, forwarding through the relay and accumulating content.

            Returns:
                A tuple ``(needs_resume, approval_payload)``.  When
                ``needs_resume`` is True, the caller must invoke
                ``sub_agent.resume_with_approval(...)`` with the decision in
                ``approval_payload`` and drain its events too.  Otherwise the
                stream ran to its final event (or errored).
            """
            async for event in stream_iter:
                evt_type = getattr(event, "type", None)
                content = getattr(event, "content", "") or ""

                if evt_type == "content":
                    if content:
                        accumulated.append(content)
                        if pin:
                            await relay.on_token(content)
                elif evt_type == "thought":
                    thought_text = getattr(event, "thought", "") or content
                    await relay.on_thought(
                        thought_text,
                        dict(getattr(event, "metadata", {}) or {}),
                    )
                elif evt_type == "approval_needed":
                    pending = dict(getattr(event, "pending_tool_call", {}) or {})
                    # The consumer-side relay registers a future, emits
                    # ASYNC_APPROVAL_NEEDED with ``requesting_agent``
                    # attribution, and resolves the future when the user
                    # decides.  We bring the decision back into the sub-
                    # agent loop by re-driving ``resume_with_approval``.
                    decision = await relay.on_approval(pending)
                    if not isinstance(decision, dict):
                        decision = {"approved": False, "llm_message_id": None}
                    decision.setdefault(
                        "_sub_agent_msg_id",
                        getattr(event, "llm_message_id", None),
                    )
                    return True, decision
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
                    return False, {"_error": f"Sub-agent error: {err}"}
                # ``sources``, ``approval_result``, ``resume`` events are
                # not forwarded over the relay — the conductor doesn't need
                # them, and the relay's surface is intentionally minimal.
                # In particular SourceEvent is dropped because citations are
                # surfaced as part of the sub-agent's content stream and the
                # conductor only needs the synthesised final text.

            return False, None

        try:
            needs_resume, decision = await _drain_stream(sub_agent.stream(prompt))
            # Drive any approval-resume cycles inline so the conductor's
            # tool call only returns once the sub-agent has fully settled.
            # Bounded by MAX_DELEGATION_APPROVAL_CYCLES (module-level
            # constant) to prevent pathological loops.
            cycle_count = 0
            while needs_resume and cycle_count < MAX_DELEGATION_APPROVAL_CYCLES:
                # Defensive: ``_drain_stream`` returns ``needs_resume=False``
                # on every ``_error`` path today, so this branch is currently
                # unreachable. Kept so a future change that does return
                # ``(True, {"_error": ...})`` still short-circuits cleanly
                # instead of feeding a stale error into ``resume_with_approval``.
                if decision and decision.get("_error"):  # pragma: no cover
                    return {
                        "result": decision["_error"],
                        "pinned_message_id": None,
                    }
                cycle_count += 1
                msg_id = (decision or {}).get("_sub_agent_msg_id")
                approved = bool((decision or {}).get("approved", False))
                if msg_id is None:
                    # Approval cycle has no sub-agent message id to resume
                    # against, so we cannot drive ``resume_with_approval``
                    # for this turn.  Return a real failure to the
                    # conductor rather than breaking out and letting
                    # ``on_finish`` ship whatever ``accumulated`` text was
                    # collected so far — partial accumulation would look
                    # like a successful (but garbled) result to the LLM.
                    logger.warning(
                        "[delegate_to_%s] Approval cycle missing sub-agent "
                        "message id; aborting delegation.",
                        snake_slug,
                    )
                    return {
                        "result": (
                            f"Sub-agent @{agent_slug} could not be resumed: "
                            "the approval cycle was missing the sub-agent "
                            "message id."
                        ),
                        "pinned_message_id": None,
                    }
                try:
                    resume_iter = sub_agent.resume_with_approval(
                        msg_id, approved, stream=True
                    )
                except Exception as exc:
                    logger.warning(
                        "[delegate_to_%s] resume_with_approval failed: %s",
                        snake_slug,
                        exc,
                    )
                    return {
                        "result": f"Sub-agent error: {exc}",
                        "pinned_message_id": None,
                    }
                needs_resume, decision = await _drain_stream(resume_iter)
            if decision and decision.get("_error"):
                return {
                    "result": decision["_error"],
                    "pinned_message_id": None,
                }
            # If we exited the loop because the cycle limit was hit (rather
            # than the sub-agent naturally settling), surface that explicitly
            # to the conductor instead of returning the partial accumulated
            # text as if the run had succeeded.
            if needs_resume and cycle_count >= MAX_DELEGATION_APPROVAL_CYCLES:
                logger.warning(
                    "[delegate_to_%s] Exceeded approval cycle limit (%d); "
                    "aborting delegation.",
                    snake_slug,
                    MAX_DELEGATION_APPROVAL_CYCLES,
                )
                return {
                    "result": (
                        f"Sub-agent @{agent_slug} exceeded the approval "
                        f"cycle limit ({MAX_DELEGATION_APPROVAL_CYCLES}); "
                        "aborting delegation."
                    ),
                    "pinned_message_id": None,
                }
        except (PermissionError, ToolConfirmationRequired):
            # Security exceptions propagate per the fault-tolerance contract
            # (CLAUDE.md pitfall #13 / pydantic_ai_tools.py:560).
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
        if pin:
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
