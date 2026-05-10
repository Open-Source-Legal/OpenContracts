"""Clean PydanticAI implementation following PydanticAI patterns."""

import dataclasses
import json
import logging
from collections.abc import AsyncGenerator, Awaitable
from typing import Any, Callable, Optional, TypeVar, Union
from uuid import uuid4

from asgiref.sync import sync_to_async
from pydantic_ai import RunContext
from pydantic_ai.agent import Agent as PydanticAIAgent
from pydantic_ai.agent import (
    CallToolsNode,
    ModelRequestNode,
    UserPromptNode,
)
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    PartDeltaEvent,
    PartStartEvent,
    SystemPromptPart,
    TextPart,
    TextPartDelta,
    ToolCallPart,
    ToolCallPartDelta,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.toolsets import FunctionToolset
from pydantic_graph import End

from opencontractserver.constants.context_guardrails import (
    CHARS_PER_TOKEN_ESTIMATE,
    COMPACTION_SUMMARY_PREFIX,
    LARGE_IMPLICIT_CHUNK_WARN_RATIO,
    MIN_IMPLICIT_DOCUMENT_CHUNK_CHARS,
)
from opencontractserver.constants.llm import STRUCTURED_OUTPUT_RETRIES
from opencontractserver.conversations.models import Conversation
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.llms.agents.core_agents import (
    AgentConfig,
    ApprovalNeededEvent,
    ApprovalResultEvent,
    ContentEvent,
    CoreAgentBase,
    CoreConversationManager,
    CoreCorpusAgentFactory,
    CoreDocumentAgentFactory,
    CorpusAgentContext,
    DocumentAgentContext,
    ErrorEvent,
    FinalEvent,
    MessageState,
    ResumeEvent,
    SourceEvent,
    SourceNode,
    ThoughtEvent,
    UnifiedStreamEvent,
    get_default_config,
)
from opencontractserver.llms.agents.timeline_stream_mixin import TimelineStreamMixin
from opencontractserver.llms.context_guardrails import (
    cap_summary_length,
    compact_message_history,
    estimate_token_count,
    get_context_window_for_model,
    messages_to_proxies,
    strip_compaction_prefix,
)
from opencontractserver.llms.exceptions import ToolConfirmationRequired
from opencontractserver.llms.tools.core_tools import (
    AnnotationItem,
    aadd_annotations_from_exact_strings,
    aadd_document_note,
    aduplicate_annotations_with_label,
    aget_document_summary,
    aload_document_md_summary,
    aload_document_txt_extract,
    asearch_exact_text_as_sources,
    aupdate_corpus_description,
    aupdate_document_note,
    get_cached_txt_extract_length,
    is_txt_extract_cached,
)
from opencontractserver.llms.tools.pydantic_ai_tools import (
    PydanticAIDependencies,
    PydanticAIToolFactory,
)
from opencontractserver.llms.tools.tool_factory import (
    CoreTool,
    build_inject_params_for_context,
)
from opencontractserver.llms.vector_stores.pydantic_ai_vector_stores import (
    PydanticAIAnnotationVectorStore,
)
from opencontractserver.utils.embeddings import aget_embedder
from opencontractserver.utils.llm import is_anthropic_model
from opencontractserver.utils.prompt_sanitization import (
    UNTRUSTED_CONTENT_NOTICE,
    fence_user_content,
    warn_if_content_large,
)
from opencontractserver.utils.tools import deduplicate_tools, get_tool_name

from .pydantic_ai_factory import make_pydantic_ai_agent
from .timeline_schema import TimelineEntry
from .timeline_utils import TimelineBuilder

logger = logging.getLogger(__name__)

# Type variable for structured responses
T = TypeVar("T")


def _make_similarity_search_tool(vector_store: Any, default_k: int = 8) -> Callable:
    """Build the citation-capturing similarity_search tool for a vector store.

    ``default_k`` is the LLM-facing default when the model does not supply
    its own ``k`` argument. Wired through from ``AgentConfig.similarity_top_k``
    so callers controlling retrieval depth via the config field actually win
    when the model omits ``k``.
    """

    async def similarity_search(
        ctx: RunContext[PydanticAIDependencies],
        query: str,
        k: int = default_k,
        modalities: Optional[list[str]] = None,
    ) -> list[dict[str, Any]]:
        """Semantic vector search over the corpus annotations.

        Returns the top-k nearest annotations for ``query`` as a list of
        dicts with keys ``annotation_id``, ``content``, ``document_id``,
        ``corpus_id``, ``page``, ``similarity_score``, ``label``, and
        ``json``. Each real annotation's ID is captured into
        ``ctx.deps.retrieved_annotation_ids`` so the caller can later link
        citations to the owning object (e.g. ``Datacell.sources``).
        """
        results = await vector_store.similarity_search(
            query, k=k, modalities=modalities
        )
        for r in results:
            if not isinstance(r, dict):
                continue
            aid = r.get("annotation_id")
            # Real annotation PKs are positive ints; synthetic / ad-hoc
            # match IDs are negative and must not be persisted.
            if isinstance(aid, int) and aid > 0:
                ctx.deps.retrieved_annotation_ids.append(aid)
        return results

    return similarity_search


def _get_function_tools(agent: PydanticAIAgent) -> dict:
    """Return the function-tools dict from a pydantic-ai Agent.

    Uses only the public surface: ``Agent.toolsets`` (documented property
    that includes the auto-built function toolset for tools registered
    directly on the agent) and ``FunctionToolset.tools`` (public dict of
    tool name -> ``Tool``).
    """
    merged: dict = {}
    for toolset in agent.toolsets:
        if isinstance(toolset, FunctionToolset):
            merged.update(toolset.tools)
    return merged


@dataclasses.dataclass
class _HistoryResult:
    """Result of ``_get_message_history()`` with context metadata.

    Carries both the Pydantic-AI message list and token-level metrics
    that downstream code uses for context status reporting and
    compaction notifications.
    """

    messages: Optional[list[ModelMessage]]
    estimated_tokens: int = 0  # tokens going to model (after compaction)
    context_window: int = 0  # model's context window size
    was_compacted: bool = False  # whether compaction ran this turn
    tokens_before_compaction: int = 0  # 0 if no compaction


def _make_load_document_text_tool(
    agent_deps: "PydanticAIDependencies", doc_id: int
) -> Callable[..., Awaitable[dict[str, Any]]]:
    """Build the budget-aware ``load_document_text`` async closure.

    Module-level (not nested inside the agent factory) so unit tests can
    drive the closure directly with a stubbed cache instead of building
    a real ``DocumentAgentContext``. The returned coroutine captures
    ``agent_deps`` by reference, so an in-process mutation to
    ``agent_deps.turn_implicit_doc_text_chars`` is visible on the next
    call — the property the per-turn drift compensation relies on.

    The full design rationale (budget snapshot, per-turn tally, floor /
    warn-threshold semantics) lives at the call site in
    ``PydanticAIDocumentAgent.create``. This helper is the pure
    transformation; do not add side effects beyond the cache and the
    counter mutation.
    """

    async def load_document_text_tool(
        start: int | None = None,
        end: int | None = None,
        refresh: bool = False,
    ) -> dict[str, Any]:
        start_idx = 0 if start is None else max(0, int(start))

        # Populate the cache only when needed. Use the membership predicate
        # (``is_txt_extract_cached``) — NOT ``length == 0`` — so a genuinely
        # empty document doesn't trigger a redundant re-load on every call.
        if refresh or not is_txt_extract_cached(doc_id):
            # aload_document_txt_extract caches the full document text regardless
            # of the requested slice — the (0, 1) here is a cheap probe that
            # triggers that side-effect without loading any data we didn't ask for.
            # If the implementation is ever changed to cache only the requested
            # slice, get_cached_txt_extract_length would return 1 here and every
            # subsequent end_idx would be wrong.
            await aload_document_txt_extract(doc_id, 0, 1, refresh=refresh)
        total_chars = get_cached_txt_extract_length(doc_id)

        recommended = agent_deps.recommended_chunk_chars()
        window_chars = agent_deps.context_window_tokens * CHARS_PER_TOKEN_ESTIMATE
        warn_threshold = window_chars * LARGE_IMPLICIT_CHUNK_WARN_RATIO
        if (
            recommended > warn_threshold
            and not agent_deps.large_chunk_warning_emitted_this_turn
        ):
            logger.warning(
                "load_document_text: recommended chunk (%d chars) exceeds "
                "%.0f%% of model %s's context window (%d chars) — verify "
                "CHARS_PER_TOKEN_ESTIMATE still reflects the model's "
                "tokenisation density.",
                recommended,
                LARGE_IMPLICIT_CHUNK_WARN_RATIO * 100,
                agent_deps.model_name,
                int(window_chars),
            )
            agent_deps.large_chunk_warning_emitted_this_turn = True

        budget_after_in_turn_use = max(
            0, recommended - agent_deps.turn_implicit_doc_text_chars
        )
        budget_chars = max(budget_after_in_turn_use, MIN_IMPLICIT_DOCUMENT_CHUNK_CHARS)
        if end is None:
            end_idx = min(total_chars, start_idx + budget_chars)
        else:
            end_idx = max(start_idx, min(int(end), total_chars))

        text = await aload_document_txt_extract(
            doc_id, start_idx, end_idx, refresh=refresh
        )

        if end is None:
            agent_deps.turn_implicit_doc_text_chars += end_idx - start_idx

        chars_remaining = max(0, total_chars - end_idx)
        return {
            "text": text,
            "total_chars": total_chars,
            "returned_range": [start_idx, end_idx],
            "chars_remaining": chars_remaining,
            "suggested_next_start": end_idx if chars_remaining > 0 else None,
            "context_budget_chars": budget_chars,
            "budget_was_applied": end is None,
        }

    return load_document_text_tool


def _build_tools_from_registry(
    tool_names: list[str],
    *,
    document_id: int | None = None,
    corpus_id: int | None = None,
    user_id: int | None = None,
    corpus_action_id: int | None = None,
) -> list[Callable]:
    """Auto-build PydanticAI tools from the registry with context injection.

    For each tool name, resolves the async function and metadata from the
    registry, computes inject_params via build_inject_params_for_context(),
    and wraps with PydanticAIToolFactory.
    """
    from opencontractserver.llms.tools.tool_registry import ToolFunctionRegistry

    registry = ToolFunctionRegistry.get()
    tools: list[Callable] = []
    for name in tool_names:
        core_tool = registry.to_core_tool(name)
        if core_tool is None:
            logger.warning("Tool '%s' not found in registry, skipping auto-build", name)
            continue
        inject_params = build_inject_params_for_context(
            core_tool,
            document_id=document_id,
            corpus_id=corpus_id,
            user_id=user_id,
            corpus_action_id=corpus_action_id,
        )
        wrapped = PydanticAIToolFactory.create_tool(
            core_tool, inject_params=inject_params
        )
        tools.append(wrapped)
    return tools


def _to_source_node(raw: Any) -> SourceNode:
    """
    Convert an item coming from pydantic-ai (dict or BaseModel) to
    our framework-agnostic SourceNode.
    """
    if isinstance(raw, SourceNode):  # already normalised
        return raw

    if hasattr(raw, "model_dump"):
        raw = raw.model_dump()

    logger.info(f"[search_exact_text_tool] Raw source: {raw!r}")
    # raw is now a dict - handle both 'content' and 'rawText' keys
    # (SourceNode.to_dict() uses 'rawText' for frontend compatibility)
    content = raw.get("content") or raw.get("rawText", "")

    return SourceNode(
        annotation_id=int(raw.get("annotation_id", 0)),
        content=content,
        metadata=raw,
        similarity_score=raw.get("similarity_score", 1.0),
    )


def _extract_tool_result_summary(event: Any, tool_name: str) -> str:
    """Safely extract a human-readable summary from a tool result event.

    Returns a non-empty string suitable for inclusion in the timeline
    ``tool_result`` metadata.  Falls back to ``"Completed"`` if extraction
    fails or produces an empty value.

    Truncates at source using :data:`MAX_TOOL_RESULT_LENGTH` so large results
    (e.g. full ``ask_document`` answers) don't bloat ThoughtEvent metadata.
    """
    from .timeline_utils import MAX_TOOL_RESULT_LENGTH

    try:
        result_content = event.result.content
        summary = ""
        if isinstance(result_content, dict):
            # ask_document returns {"answer": ..., "sources": ..., "timeline": ...}
            summary = str(result_content.get("answer", ""))
        elif isinstance(result_content, str):
            summary = result_content
        elif result_content is not None:
            summary = str(result_content)

        if summary:
            if len(summary) > MAX_TOOL_RESULT_LENGTH:
                summary = summary[:MAX_TOOL_RESULT_LENGTH] + "..."
            return summary
    except Exception:
        logger.debug(
            "Could not extract tool result summary for %s", tool_name, exc_info=True
        )
    return "Completed"


# ---------------------------------------------------------------------------
# Pydantic‐AI base – now inherits TimelineStreamMixin for unified timeline.
# ---------------------------------------------------------------------------


class PydanticAICoreAgent(CoreAgentBase, TimelineStreamMixin):
    """PydanticAI implementation of CoreAgentBase following PydanticAI patterns."""

    def __init__(
        self,
        config: AgentConfig,
        conversation_manager: CoreConversationManager,
        pydantic_ai_agent: PydanticAIAgent,
        agent_deps: PydanticAIDependencies,
    ):
        super().__init__(config, conversation_manager)
        self.pydantic_ai_agent = pydantic_ai_agent
        self.agent_deps = agent_deps

    @staticmethod
    def _apply_context_budget(
        agent_deps: Optional["PydanticAIDependencies"],
        config: "AgentConfig",
        history_result: _HistoryResult,
    ) -> None:
        """Pure transformation of an in-flight turn's context budget.

        Extracted as a static helper so unit tests can drive it directly
        with a constructed ``_HistoryResult`` instead of bypassing
        ``__init__`` on the agent — keeps the test surface stable as
        ``__init__`` evolves.

        ``turn_implicit_doc_text_chars`` is reset here even though it
        only tracks one tool's output (``load_document_text``); other
        heavy tools (vector search, annotation listing) still consume
        budget but are not deducted. The counter is therefore a
        *partial* correction that prevents two adjacent
        ``load_document_text`` calls from each handing back a full
        budget-sized slice — it is not a full per-turn accounting.
        """
        if agent_deps is None:
            return
        agent_deps.model_name = config.model_name
        # Use the history result's context_window when present; fall back to
        # the per-model registry only when it's missing (``0``). ``or`` would
        # conflate "missing" with a legitimate zero — fragile if pydantic-ai
        # ever populates 0 for a real model.
        agent_deps.context_window_tokens = (
            history_result.context_window
            if history_result.context_window > 0
            else get_context_window_for_model(config.model_name)
        )
        agent_deps.estimated_used_tokens = history_result.estimated_tokens
        agent_deps.compaction_threshold_ratio = config.compaction.threshold_ratio
        # Reset the per-turn tally of implicit-chunk characters. Without this
        # the counter would accumulate across turns and starve the budget on
        # long-running streaming sessions.
        agent_deps.turn_implicit_doc_text_chars = 0
        agent_deps.large_chunk_warning_emitted_this_turn = False

    def _refresh_context_budget(self, history_result: _HistoryResult) -> None:
        """Snapshot the per-turn context budget onto ``self.agent_deps``.

        Called once per turn after :meth:`_get_message_history` (or
        :meth:`_history_result_from_messages` when the caller passed an
        explicit message list) so budget-aware tools — e.g.
        ``load_document_text`` — can read the agent's remaining headroom
        from ``ctx.deps`` and self-size their return values.

        The snapshot reflects the state *entering* the turn — it does
        not update as tool returns accumulate within a single run.
        """
        self._apply_context_budget(self.agent_deps, self.config, history_result)

    @staticmethod
    def _history_result_from_messages(
        config: "AgentConfig", messages: Optional[list[ModelMessage]]
    ) -> _HistoryResult:
        """Build a ``_HistoryResult`` from an explicit Pydantic-AI message list.

        ``_get_message_history`` is the canonical path and reads from the
        DB; callers that pass an explicit ``message_history`` (notably
        :meth:`resume_with_approval`) skip it and would otherwise leave
        the budget snapshot stale on ``self.agent_deps``. This helper
        mirrors the token-estimation logic in ``_get_message_history``
        so the explicit-history path can refresh through the same
        ``_refresh_context_budget`` codepath.

        Static so unit tests can drive it directly with a constructed
        ``AgentConfig`` instead of bypassing ``__init__`` on the agent —
        keeps the test surface stable as ``__init__`` evolves.
        """
        system_text = config.system_prompt or ""
        if messages:

            def _part_text(part: Any) -> str:
                # ToolCallPart stores arguments in ``args``, not ``content``.
                # Falling back to ``args`` prevents material under-counting
                # when history contains tool calls with large argument payloads.
                content = (
                    getattr(part, "content", None) or getattr(part, "args", None) or ""
                )
                return content if isinstance(content, str) else str(content)

            msg_tokens = sum(
                estimate_token_count(
                    " ".join(_part_text(p) for p in getattr(m, "parts", []))
                )
                for m in messages
            )
        else:
            msg_tokens = 0
        return _HistoryResult(
            messages=messages,
            estimated_tokens=estimate_token_count(system_text) + msg_tokens,
            context_window=get_context_window_for_model(config.model_name),
        )

    async def _initialise_llm_message(self, user_text: str) -> tuple[int, int]:
        """Ensure messages are persisted exactly once per turn.

        CoreAgentBase.stream() has *already* written the HUMAN row before the
        adapter is entered.  Creating another one here would duplicate the
        message.  We therefore re-use the most recent HUMAN message in the
        active conversation when available and only insert a new row if – for
        some edge-case – the wrapper skipped persistence (e.g. store_messages
        was False or we are running via the low-level ``_chat_raw`` path).
        """

        # Try to reuse the last HUMAN message if it matches the current turn
        user_id: int | None = None
        if self.conversation_manager.conversation:
            history = await self.conversation_manager.get_conversation_messages()
            if history and history[-1].msg_type.upper() == "HUMAN":
                user_id = history[-1].id

        # Fallback: create the HUMAN message ourselves (rare code-paths)
        if user_id is None:
            user_id = await self.store_user_message(user_text)

        llm_id = await self.create_placeholder_message("LLM")
        return user_id, llm_id

    async def _finalise_llm_message(
        self,
        llm_id: int,
        final_content: str,
        sources: list[SourceNode],
        usage: dict[str, Any] | None,
        timeline: list[TimelineEntry],
    ) -> None:
        """Finalize LLM message with content, sources, and metadata."""
        logger.debug("[DIAGNOSTIC _finalise_llm_message] Called with:")
        logger.debug(f"[DIAGNOSTIC _finalise_llm_message]   llm_id: {llm_id}")
        logger.debug(
            f"[DIAGNOSTIC _finalise_llm_message]   final_content length: {len(final_content)}"
        )
        logger.debug(
            f"[DIAGNOSTIC _finalise_llm_message]   sources count: {len(sources)}"
        )
        if sources:
            logger.debug(
                f"[DIAGNOSTIC _finalise_llm_message]   First source: {sources[0].to_dict()}"
            )
        logger.debug(
            "[DIAGNOSTIC _finalise_llm_message]   About to call complete_message()..."
        )
        await self.complete_message(
            llm_id,
            final_content,
            sources=sources,
            metadata={"usage": usage, "framework": "pydantic_ai", "timeline": timeline},
        )
        logger.debug(
            "[DIAGNOSTIC _finalise_llm_message]   complete_message() returned successfully"
        )

    async def _get_message_history(self) -> _HistoryResult:
        """Convert OpenContracts ``ChatMessage`` history to Pydantic-AI format.

        Uses a **compact-once, read-cheaply** strategy:

        1. ``get_conversation_messages()`` already honours the persisted
           ``compacted_before_message_id`` bookmark — it only loads messages
           *after* the cutoff.  If a bookmark exists, the stored
           ``compaction_summary`` is prepended as a system message.

        2. After loading the (potentially already-trimmed) message list the
           method checks whether the *remaining* messages still exceed the
           context window.  If so it runs a fresh compaction pass, persists
           the new bookmark, and trims the list for *this* call.

        This means a long conversation pays the compaction cost exactly
        once per growth spurt, and every subsequent call is a cheap
        filtered read.

        Returns a :class:`_HistoryResult` carrying both the message list
        and token-level context metadata for status reporting.
        """
        raw_messages = await self.conversation_manager.get_conversation_messages()

        # Resolve the previously-persisted compaction summary (if any).
        conv = self.conversation_manager.conversation
        stored_summary = getattr(conv, "compaction_summary", "") or "" if conv else ""

        context_window = get_context_window_for_model(self.config.model_name)
        was_compacted = False
        tokens_before_compaction = 0

        if not raw_messages and not stored_summary:
            return _HistoryResult(
                messages=None,
                estimated_tokens=0,
                context_window=context_window,
            )

        # -----------------------------------------------------------------
        # Check whether a *new* compaction pass is needed on the messages
        # that survived the DB-level cutoff.
        # -----------------------------------------------------------------
        compaction_cfg = self.config.compaction

        if (
            compaction_cfg.enabled
            and len(raw_messages) > compaction_cfg.min_recent_messages
        ):
            proxies = messages_to_proxies(raw_messages)
            system_prompt_tokens = estimate_token_count(self.config.system_prompt or "")
            stored_summary_tokens = (
                estimate_token_count(stored_summary) if stored_summary else 0
            )

            result = compact_message_history(
                proxies,
                self.config.model_name,
                system_prompt_tokens=system_prompt_tokens,
                stored_summary_tokens=stored_summary_tokens,
                threshold_ratio=compaction_cfg.threshold_ratio,
                min_recent=compaction_cfg.min_recent_messages,
                max_recent=compaction_cfg.max_recent_messages,
            )

            if result.compacted:
                was_compacted = True
                tokens_before_compaction = result.estimated_tokens_before

                # Determine the cutoff message id — the last message that
                # will be folded into the summary.
                cutoff_idx = len(raw_messages) - result.preserved_count
                cutoff_msg = raw_messages[cutoff_idx - 1]

                # Merge old + new summary, stripping prefix to avoid
                # duplication, then re-adding once.
                if stored_summary:
                    old_body = strip_compaction_prefix(stored_summary).rstrip()
                    new_body = strip_compaction_prefix(result.summary)
                    merged_summary = cap_summary_length(
                        COMPACTION_SUMMARY_PREFIX + old_body + "\n\n" + new_body
                    )
                else:
                    merged_summary = cap_summary_length(result.summary)

                # Persist the bookmark so future calls skip these messages.
                # The in-memory trim MUST be inside the try block so that if
                # persistence fails we fall back to the full message list
                # (with the old stored_summary) rather than losing context.
                try:
                    await self.conversation_manager.persist_compaction(
                        summary=merged_summary,
                        cutoff_message_id=cutoff_msg.id,
                    )
                    stored_summary = merged_summary

                    # Trim the in-memory list for *this* call only on
                    # successful persistence.
                    raw_messages = raw_messages[-result.preserved_count :]

                    # Report the actual post-merge token count rather
                    # than CompactionResult.estimated_tokens_after, which
                    # only reflects the new summary (not the merged one).
                    actual_tokens_after = (
                        estimate_token_count(self.config.system_prompt or "")
                        + estimate_token_count(merged_summary)
                        + sum(
                            estimate_token_count(getattr(m, "content", "") or "")
                            for m in raw_messages
                        )
                    )

                    logger.info(
                        "Compacted conversation: removed %d messages, "
                        "keeping %d recent (tokens %d → %d)",
                        result.removed_count,
                        result.preserved_count,
                        result.estimated_tokens_before,
                        actual_tokens_after,
                    )
                except Exception:
                    logger.exception(
                        "Failed to persist compaction bookmark — "
                        "keeping full message list for this call"
                    )
                    # On persist failure, compaction didn't actually take effect
                    was_compacted = False
                    tokens_before_compaction = 0

        # -----------------------------------------------------------------
        # Build Pydantic-AI ModelMessage list
        # -----------------------------------------------------------------
        history: list[ModelMessage] = []

        # Prepend the compaction summary (persisted or freshly generated).
        if stored_summary:
            history.append(
                ModelRequest(parts=[SystemPromptPart(content=stored_summary)])
            )

        for msg in raw_messages:
            msg_type_upper = msg.msg_type.upper()
            content = msg.content

            # Skip any messages with no actual content
            if not content.strip():
                continue

            if msg_type_upper == "HUMAN":
                history.append(ModelRequest(parts=[UserPromptPart(content=content)]))
            elif msg_type_upper == "LLM":
                history.append(ModelResponse(parts=[TextPart(content=content)]))
            elif msg_type_upper == "SYSTEM":
                history.append(ModelRequest(parts=[SystemPromptPart(content=content)]))
            # else: skip unknown types

        # Compute final token estimate from the messages that will be sent
        final_system_tokens = estimate_token_count(
            (self.config.system_prompt or "") + stored_summary
        )
        final_msg_tokens = sum(
            estimate_token_count(
                " ".join(
                    getattr(part, "content", "") for part in getattr(msg, "parts", [])
                )
            )
            for msg in history
        )
        estimated_tokens = final_system_tokens + final_msg_tokens

        return _HistoryResult(
            messages=history or None,
            estimated_tokens=estimated_tokens,
            context_window=context_window,
            was_compacted=was_compacted,
            tokens_before_compaction=tokens_before_compaction,
        )

    def _build_structured_system_prompt(
        self, target_type: type[T], user_prompt: str
    ) -> str:
        """Build the system prompt for structured extraction runs.

        Subclasses may override this to include document or corpus context.
        The base implementation intentionally avoids any citation or
        conversational guidance to minimize iterations and enforce raw output.

        The wording explicitly tells the agent to commit to the final
        structured response after gathering information. Some models (notably
        Anthropic's Claude family) tend to keep narrating or invoking tools
        instead of producing the structured output unless told to stop. See
        issue #1381.
        """
        return (
            "You are in data extraction mode.\n"
            "Use available tools to locate the requested information.\n\n"
            "COMMIT-EARLY RULE:\n"
            "As soon as a tool result contains a confident answer to the "
            "question, you MUST stop calling tools and commit by calling "
            "the result tool with that value. Do not keep reading or "
            "searching to double-check, and do not exhaustively scan the "
            "document just because more bytes or chunks remain. Reading "
            "more is not the task; producing the structured answer is.\n\n"
            "TOOL SELECTION:\n"
            "Prefer `similarity_search` as the first step for any "
            "fact-finding question (titles, parties, dates, defined terms, "
            "specific clauses, etc.) — the search index is already chunked "
            "and ranked for retrieval. Reserve byte-range readers like "
            "`load_document_text` for whole-document tasks (summaries, "
            "exhaustive review) or as a fallback when search clearly "
            "misses. Do NOT walk a document end-to-end via sequential "
            "byte-range reads when search would answer the question.\n\n"
            "OUTPUT:\n"
            "Return ONLY the raw value matching the target type. "
            "No explanations, no citations, no extra words.\n\n"
            "SEARCH PROTOCOL (negative case only):\n"
            "If your searches do NOT surface the answer and you are about "
            "to conclude the information is absent, you MUST first issue "
            "at least 2-3 distinct search queries that approach the "
            "question from different angles (paraphrase, key terms, "
            "likely answer phrasings). A single failed search is NOT "
            "sufficient evidence that the information is missing. This "
            "rule only applies to giving up — once you have a confident "
            "answer, the COMMIT-EARLY RULE takes precedence and you "
            "commit immediately.\n\n"
            "Only return null/None after multiple search attempts have all "
            "failed to find relevant content."
        )

    async def _chat_raw(
        self, message: str, **kwargs
    ) -> tuple[str, list[SourceNode], dict]:
        """Low-level chat; returns content, sources, metadata (no DB ops)."""
        logger.info(f"[PydanticAI sync chat] Starting chat with message: {message!r}")

        history_result = await self._get_message_history()
        self._refresh_context_budget(history_result)
        message_history = history_result.messages

        # Prepare parameters for run(); include history only if available
        run_kwargs: dict[str, Any] = {"deps": self.agent_deps}
        if message_history:
            run_kwargs["message_history"] = message_history
        run_kwargs.update(kwargs)

        run_result = await self.pydantic_ai_agent.run(message, **run_kwargs)

        llm_response_content = str(run_result.output)
        sources = [
            self._normalise_source(s) for s in getattr(run_result, "sources", [])
        ]
        usage_data = _usage_to_dict(run_result.usage())

        return (
            llm_response_content,
            sources,
            {"usage": usage_data, "framework": "pydantic_ai"},
        )

    # NOTE: This method was previously called ``stream``.  It is now renamed
    # to ``_stream_core`` so that the TimelineStreamMixin can wrap it and take
    # care of collecting the reasoning timeline.

    async def _stream_core(
        self,
        message: str,
        **kwargs: Any,
    ) -> AsyncGenerator[UnifiedStreamEvent, None]:
        """Internal streaming generator – TimelineStreamMixin adds timeline.

        Accepts a small set of typed keyword arguments via ``**kwargs`` so
        the signature stays compatible with the mixin's contract while
        callers can still pass ``force_llm_id``/``force_user_msg_id``/etc.
        """

        force_llm_id: Optional[int] = kwargs.pop("force_llm_id", None)
        force_user_msg_id: Optional[int] = kwargs.pop("force_user_msg_id", None)
        initial_timeline: Optional[list[dict]] = kwargs.pop("initial_timeline", None)
        deps: Any = kwargs.pop("deps", None)
        message_history: Optional[list[Any]] = kwargs.pop("message_history", None)
        if kwargs:
            raise TypeError(
                f"_stream_core got unexpected keyword arguments: {sorted(kwargs)}"
            )

        logger.info(f"[PydanticAI stream] Starting stream with message: {message!r}")

        user_msg_id: int | None = force_user_msg_id
        llm_msg_id: int | None = force_llm_id

        # ------------------------------------------------------------------
        # Deduplicate message persistence
        # ------------------------------------------------------------------
        if self.conversation_manager.conversation and llm_msg_id is None:
            # Check if CoreAgentBase.stream() already created the placeholder
            history = await self.conversation_manager.get_conversation_messages()
            if (
                history
                and history[-1].msg_type.upper() == "LLM"
                and not history[-1].content
            ):
                llm_msg_id = history[-1].id
                # The corresponding HUMAN message should be right before it
                for prev in reversed(history[:-1]):
                    if prev.msg_type.upper() == "HUMAN":
                        user_msg_id = prev.id
                        break

            # If still none – fall back to helper that creates fresh rows
            if llm_msg_id is None:
                user_msg_id, llm_msg_id = await self._initialise_llm_message(message)

        accumulated_content: str = ""
        accumulated_sources: list[SourceNode] = []
        final_usage_data: dict[str, Any] | None = None

        # Re-hydrate the historical context for Pydantic-AI, if any exists.
        # Callers (e.g. resume_with_approval) may override via the explicit
        # ``message_history`` param; otherwise we load from the DB.
        effective_history: Optional[list[Any]]
        if message_history is not None:
            effective_history = message_history
            # Even though the caller bypassed the DB-driven
            # ``_get_message_history`` path, we still need to refresh the
            # full budget snapshot — not just the per-turn tally —
            # otherwise ``estimated_used_tokens`` (and the rest of the
            # snapshot fields) carry over stale values from the previous
            # turn, which would give ``recommended_chunk_chars()`` the
            # wrong baseline. Build a synthetic ``_HistoryResult`` from
            # the explicit messages and feed it through the same code
            # path the canonical caller uses.
            history_result = self._history_result_from_messages(
                self.config, message_history
            )
            self._refresh_context_budget(history_result)
            context_status = {
                "used_tokens": history_result.estimated_tokens,
                "context_window": history_result.context_window,
                "was_compacted": False,
                "tokens_before_compaction": 0,
            }
        else:
            history_result = await self._get_message_history()
            self._refresh_context_budget(history_result)
            effective_history = history_result.messages
            context_status = {
                "used_tokens": history_result.estimated_tokens,
                "context_window": history_result.context_window,
                "was_compacted": history_result.was_compacted,
                "tokens_before_compaction": history_result.tokens_before_compaction,
            }

        # CRITICAL FIX: Exclude the most recent HUMAN message from history since
        # pydantic_ai.iter() will automatically add the current `message` parameter.
        # This prevents duplicate consecutive user messages which violate OpenAI's API contract.
        if effective_history:
            # Remove the last message if it's a user prompt (HUMAN message)
            if effective_history and isinstance(effective_history[-1], ModelRequest):
                last_parts = effective_history[-1].parts
                if last_parts and isinstance(last_parts[0], UserPromptPart):
                    logger.debug(
                        f"[Session {self.session_id if hasattr(self, 'session_id') else 'N/A'}] "
                        "Removing duplicate user message from history to prevent API error"
                    )
                    effective_history = effective_history[:-1]

            # If history is now empty, set to None for pydantic_ai
            if not effective_history:
                effective_history = None

        stream_kwargs: dict[str, Any] = {"deps": deps or self.agent_deps}
        if effective_history:
            stream_kwargs["message_history"] = effective_history

        # Timeline builder – captures reasoning steps for persistence/UI
        builder = TimelineBuilder()

        # Allow callers (e.g. resume_with_approval) to inject pre-built
        # timeline entries so they appear in both the persisted DB record
        # and the FinalEvent sent to the frontend.
        if initial_timeline:
            for entry in initial_timeline:
                builder.add(entry)

        # Emit a compaction notification so the frontend can display it.
        if history_result is not None and history_result.was_compacted:
            compaction_evt = ThoughtEvent(
                thought=(
                    f"Conversation history compacted: "
                    f"{history_result.tokens_before_compaction:,} → "
                    f"{history_result.estimated_tokens:,} estimated tokens "
                    f"({history_result.context_window:,} token window)"
                ),
                user_message_id=user_msg_id,
                llm_message_id=llm_msg_id,
                metadata={
                    "compaction": {
                        "tokens_before": history_result.tokens_before_compaction,
                        "tokens_after": history_result.estimated_tokens,
                        "context_window": history_result.context_window,
                    }
                },
            )
            builder.add(compaction_evt)
            yield compaction_evt

        try:
            logger.debug(
                f"[DIAGNOSTIC] Entering pydantic_ai agent.iter() for message: {message!r}"
            )
            async with self.pydantic_ai_agent.iter(
                message, **stream_kwargs
            ) as agent_run:
                async for node in agent_run:
                    logger.debug(
                        f"[DIAGNOSTIC] Processing node type: {type(node).__name__}"
                    )

                    # ------------------------------------------------------------------
                    # USER PROMPT NODE – This is the very first node in the graph.
                    # ------------------------------------------------------------------
                    if isinstance(node, UserPromptNode):
                        event_obj = ThoughtEvent(
                            thought="Received user prompt; beginning reasoning cycle…",
                            user_message_id=user_msg_id,
                            llm_message_id=llm_msg_id,
                        )
                        builder.add(event_obj)
                        yield event_obj

                    # ------------------------------------------------------------------
                    # MODEL REQUEST NODE – We can stream raw model deltas from here.
                    # ------------------------------------------------------------------
                    elif isinstance(node, ModelRequestNode):
                        logger.debug(
                            "[DIAGNOSTIC] Entering ModelRequestNode - will stream model deltas"
                        )
                        event_obj = ThoughtEvent(
                            thought="Sending request to language model…",
                            user_message_id=user_msg_id,
                            llm_message_id=llm_msg_id,
                        )
                        builder.add(event_obj)
                        yield event_obj

                        try:
                            model_event_count = 0
                            async with node.stream(agent_run.ctx) as model_stream:
                                async for event in model_stream:
                                    model_event_count += 1
                                    logger.debug(
                                        f"[DIAGNOSTIC] Model stream event #{model_event_count}: {type(event).__name__}"
                                    )
                                    text, is_answer, meta = _event_to_text_and_meta(
                                        event
                                    )
                                    logger.debug(
                                        "[DIAGNOSTIC] _event_to_text_and_meta returned: "
                                        f"text={text!r}, is_answer={is_answer}, meta={meta}"
                                    )
                                    if text:
                                        if is_answer:
                                            accumulated_content += text
                                            logger.debug(
                                                f"[DIAGNOSTIC] Accumulated content now: {accumulated_content!r}"
                                            )
                                            # Content timeline now handled by TimelineStreamMixin

                                        # Merge any source nodes attached to event (unlikely here but future-proof)
                                        accumulated_sources.extend(
                                            [
                                                _to_source_node(s)
                                                for s in getattr(event, "sources", [])
                                            ]
                                        )
                                        # builder will record Sources automatically

                                        content_ev = ContentEvent(
                                            content=text,
                                            accumulated_content=accumulated_content,
                                            user_message_id=user_msg_id,
                                            llm_message_id=llm_msg_id,
                                            metadata=meta,
                                        )
                                        builder.add(content_ev)
                                        logger.debug(
                                            f"[DIAGNOSTIC] Yielding ContentEvent with text: {text!r}"
                                        )
                                        yield content_ev
                                    else:
                                        logger.debug(
                                            "[DIAGNOSTIC] No text extracted from event - skipping ContentEvent"
                                        )
                            logger.debug(
                                f"[DIAGNOSTIC] Exited ModelRequestNode stream - total events: "
                                f"{model_event_count}, accumulated_content length: "
                                f"{len(accumulated_content)}"
                            )
                        except Exception:
                            # Already handled by outer error handler – stop processing this node
                            raise

                    # ------------------------------------------------------------------
                    # CALL TOOLS NODE – Capture tool call & result events.
                    # ------------------------------------------------------------------
                    elif isinstance(node, CallToolsNode):
                        logger.debug(
                            "[DIAGNOSTIC] Entering CallToolsNode - will process tool calls"
                        )
                        event_obj = ThoughtEvent(
                            thought="Processing model response – may invoke tools…",
                            user_message_id=user_msg_id,
                            llm_message_id=llm_msg_id,
                        )
                        builder.add(event_obj)
                        yield event_obj

                        try:
                            tool_event_count = 0
                            logger.debug(
                                "[DIAGNOSTIC] About to start node.stream(agent_run.ctx) for CallToolsNode"
                            )
                            async with node.stream(agent_run.ctx) as tool_stream:
                                logger.debug(
                                    "[DIAGNOSTIC] Entered tool_stream context - starting iteration"
                                )
                                # ``[assignment]`` ignore — both this loop and
                                # the model_stream loop above reuse the name
                                # ``event``, but pydantic-ai infers different
                                # element types for the two streams. Removing
                                # the ignore would either require renaming the
                                # loop var (~30 reference sites in this branch)
                                # or a ``cast(Any, ...)`` that silently widens
                                # downstream usages of ``event.part`` /
                                # ``event.result`` and surfaces unrelated
                                # mypy errors. Kept narrow ([assignment] only)
                                # so the runtime kind-dispatch below is the
                                # type contract.
                                async for event in tool_stream:  # type: ignore[assignment]
                                    tool_event_count += 1
                                    logger.debug(
                                        f"[DIAGNOSTIC] Tool stream event #{tool_event_count}: "
                                        f"event_kind={event.event_kind}"
                                    )
                                    logger.debug(
                                        f"[DIAGNOSTIC] Event type: {type(event).__name__}"
                                    )

                                    if event.event_kind == "function_tool_call":
                                        logger.debug(
                                            "[DIAGNOSTIC] Processing function_tool_call event"
                                        )
                                        tool_name = event.part.tool_name
                                        tool_args = event.part.args
                                        tool_call_id = getattr(
                                            event.part, "tool_call_id", str(uuid4())
                                        )

                                        # Check if tool requires approval BEFORE pydantic-ai executes it
                                        if self._check_tool_requires_approval(
                                            tool_name
                                        ):
                                            # Log the exact format of tool_args for debugging
                                            logger.info(
                                                f"Tool '{tool_name}' requires approval. "
                                                f"Args type: {type(tool_args)}, value: {tool_args!r}"
                                            )

                                            # Ensure args are JSON-serializable
                                            if isinstance(tool_args, dict):
                                                serializable_args = tool_args
                                            elif hasattr(tool_args, "model_dump"):
                                                # Pydantic model
                                                serializable_args = (
                                                    tool_args.model_dump()
                                                )
                                            elif hasattr(tool_args, "__dict__"):
                                                # Regular object
                                                serializable_args = tool_args.__dict__
                                            else:
                                                # Fallback - store as string
                                                logger.warning(
                                                    f"Tool args not easily serializable: {type(tool_args)}"
                                                )
                                                serializable_args = str(tool_args)

                                            # Store state to DB
                                            await self.complete_message(
                                                llm_msg_id,
                                                content="Awaiting user approval for tool execution.",
                                                metadata={
                                                    "state": str(
                                                        MessageState.AWAITING_APPROVAL
                                                    ),
                                                    "pending_tool_call": {
                                                        "name": tool_name,
                                                        "arguments": serializable_args,
                                                        "tool_call_id": tool_call_id,
                                                    },
                                                    "framework": "pydantic_ai",
                                                    "timeline": builder.timeline,  # Preserve timeline so far
                                                },
                                            )

                                            # Emit approval event and stop streaming
                                            yield ApprovalNeededEvent(
                                                pending_tool_call={
                                                    "name": tool_name,
                                                    "arguments": tool_args,
                                                    "tool_call_id": tool_call_id,
                                                },
                                                user_message_id=user_msg_id,
                                                llm_message_id=llm_msg_id,
                                                metadata={
                                                    "state": str(
                                                        MessageState.AWAITING_APPROVAL
                                                    )
                                                },
                                            )
                                            return  # Exit the stream

                                        # If no approval needed, emit the tool call event normally
                                        logger.debug(
                                            f"[DIAGNOSTIC] Tool '{tool_name}' does not require "
                                            "approval - emitting ThoughtEvent"
                                        )
                                        tool_ev = ThoughtEvent(
                                            thought=f"Calling tool `{tool_name}` with args {event.part.args}",
                                            user_message_id=user_msg_id,
                                            llm_message_id=llm_msg_id,
                                            metadata={
                                                "tool_name": tool_name,
                                                "args": event.part.args,
                                            },
                                        )
                                        builder.add(tool_ev)
                                        yield tool_ev
                                        logger.debug(
                                            f"[DIAGNOSTIC] Finished processing function_tool_call "
                                            f"for '{tool_name}' - continuing iteration"
                                        )

                                    elif event.event_kind == "function_tool_result":
                                        logger.debug(
                                            "[DIAGNOSTIC] Processing function_tool_result event"
                                        )
                                        tool_name = event.result.tool_name
                                        logger.debug(
                                            f"[DIAGNOSTIC] Tool result received: tool_name={tool_name}"
                                        )
                                        # Capture vector-search results (our canonical source provider)
                                        if tool_name == "similarity_search":
                                            raw_sources = event.result.content
                                            logger.debug(
                                                f"[DIAGNOSTIC] similarity_search returned "
                                                f"{len(raw_sources) if isinstance(raw_sources, list) else 'non-list'} "
                                                "sources"
                                            )
                                            if isinstance(raw_sources, list):
                                                new_sources = [
                                                    _to_source_node(s)
                                                    for s in raw_sources
                                                ]
                                                accumulated_sources.extend(new_sources)
                                                logger.debug(
                                                    f"[DIAGNOSTIC] Accumulated {len(new_sources)} sources "
                                                    f"from similarity_search. Total accumulated_sources "
                                                    f"now: {len(accumulated_sources)}"
                                                )

                                                # Emit a dedicated SourceEvent so the client
                                                # can update citations in real-time.
                                                src_ev = SourceEvent(
                                                    sources=new_sources,
                                                    user_message_id=user_msg_id,
                                                    llm_message_id=llm_msg_id,
                                                )
                                                builder.add(src_ev)
                                                logger.debug(
                                                    f"[DIAGNOSTIC] Yielding SourceEvent with {len(new_sources)} sources"
                                                )
                                                yield src_ev

                                            # Emit tool_result entry for timeline
                                            tool_result_summary = (
                                                f"Found {len(raw_sources)} matching annotations"
                                                if isinstance(raw_sources, list)
                                                else "No results found"
                                            )
                                            tool_ev = ThoughtEvent(
                                                thought=f"Tool `{tool_name}` returned a result.",
                                                user_message_id=user_msg_id,
                                                llm_message_id=llm_msg_id,
                                                metadata={
                                                    "tool_name": tool_name,
                                                    "tool_result": tool_result_summary,
                                                },
                                            )
                                            builder.add(tool_ev)
                                            yield tool_ev

                                        # Capture exact text search results (similar to similarity_search)
                                        elif tool_name == "search_exact_text":
                                            raw_sources = event.result.content
                                            if (
                                                isinstance(raw_sources, list)
                                                and raw_sources
                                            ):
                                                new_sources = [
                                                    _to_source_node(s)
                                                    for s in raw_sources
                                                ]
                                                accumulated_sources.extend(new_sources)
                                                # Emit SourceEvent for real-time citation updates
                                                src_ev = SourceEvent(
                                                    sources=new_sources,
                                                    user_message_id=user_msg_id,
                                                    llm_message_id=llm_msg_id,
                                                )
                                                builder.add(src_ev)
                                                yield src_ev
                                            else:
                                                logger.warning(
                                                    "[search_exact_text] No sources to emit - "
                                                    f"raw_sources is {type(raw_sources)} with value: {raw_sources!r}"
                                                )

                                            # Emit tool_result entry for timeline
                                            tool_result_summary = (
                                                f"Found {len(raw_sources)} exact text matches"
                                                if isinstance(raw_sources, list)
                                                and raw_sources
                                                else "No results found"
                                            )
                                            tool_ev = ThoughtEvent(
                                                thought=f"Tool `{tool_name}` returned a result.",
                                                user_message_id=user_msg_id,
                                                llm_message_id=llm_msg_id,
                                                metadata={
                                                    "tool_name": tool_name,
                                                    "tool_result": tool_result_summary,
                                                },
                                            )
                                            builder.add(tool_ev)
                                            yield tool_ev

                                        # Special handling for nested document-agent responses
                                        elif tool_name == "ask_document":
                                            # The ask_document tool returns a dict with keys: answer, sources, timeline
                                            try:
                                                result_payload = event.result.content
                                                # Ensure we have a dict (pydantic may already return dict object)
                                                if isinstance(result_payload, str):
                                                    import json as _json

                                                    result_payload = _json.loads(
                                                        result_payload
                                                    )

                                                if isinstance(result_payload, dict):
                                                    # 1) Surface child sources immediately so UI can pin them
                                                    child_sources_raw = (
                                                        result_payload.get(
                                                            "sources", []
                                                        )
                                                    )
                                                    if child_sources_raw:
                                                        new_sources = [
                                                            _to_source_node(s)
                                                            for s in child_sources_raw
                                                        ]
                                                        accumulated_sources.extend(
                                                            new_sources
                                                        )
                                                        src_ev = SourceEvent(
                                                            sources=new_sources,
                                                            user_message_id=user_msg_id,
                                                            llm_message_id=llm_msg_id,
                                                        )
                                                        builder.add(src_ev)
                                                        yield src_ev

                                                    # 2) Relay child timeline entries as ThoughtEvents,
                                                    # prefixing with document context for clarity
                                                    child_tl = result_payload.get(
                                                        "timeline", []
                                                    )
                                                    for tl_entry in child_tl:
                                                        tl_text = (
                                                            tl_entry.get("thought")
                                                            or ""
                                                        )
                                                        if not tl_text:
                                                            continue
                                                        prefixed_text = (
                                                            f"[ask_document] {tl_text}"
                                                        )
                                                        tl_ev = ThoughtEvent(
                                                            thought=prefixed_text,
                                                            user_message_id=user_msg_id,
                                                            llm_message_id=llm_msg_id,
                                                            metadata={
                                                                "tool_name": tool_name,
                                                                **(
                                                                    tl_entry.get(
                                                                        "metadata"
                                                                    )
                                                                    or {}
                                                                ),
                                                            },
                                                        )
                                                        builder.add(tl_ev)
                                                        yield tl_ev

                                                    # 3) Append the child answer to accumulated_content
                                                    # so it is included in final answer.
                                                    answer_txt = result_payload.get(
                                                        "answer", ""
                                                    )
                                                    if answer_txt:
                                                        accumulated_content += (
                                                            answer_txt
                                                        )
                                                        content_ev = ContentEvent(
                                                            content=answer_txt,
                                                            accumulated_content=accumulated_content,
                                                            user_message_id=user_msg_id,
                                                            llm_message_id=llm_msg_id,
                                                            metadata={
                                                                "from": "ask_document"
                                                            },
                                                        )
                                                        builder.add(content_ev)
                                                        yield content_ev
                                            except (
                                                Exception
                                            ) as _inner_exc:  # noqa: BLE001 – defensive
                                                logger.warning(
                                                    "Failed to process ask_document result payload: %s",
                                                    _inner_exc,
                                                )

                                            # Always log completion of ask_document regardless of success
                                            tool_ev = ThoughtEvent(
                                                thought=f"Tool `{tool_name}` returned a result.",
                                                user_message_id=user_msg_id,
                                                llm_message_id=llm_msg_id,
                                                metadata={
                                                    "tool_name": tool_name,
                                                    "tool_result": _extract_tool_result_summary(
                                                        event, tool_name
                                                    ),
                                                },
                                            )
                                            builder.add(tool_ev)
                                            yield tool_ev

                                        else:
                                            # Let TimelineBuilder infer tool_result from metadata
                                            tool_ev = ThoughtEvent(
                                                thought=f"Tool `{tool_name}` returned a result.",
                                                user_message_id=user_msg_id,
                                                llm_message_id=llm_msg_id,
                                                metadata={
                                                    "tool_name": tool_name,
                                                    "tool_result": _extract_tool_result_summary(
                                                        event, tool_name
                                                    ),
                                                },
                                            )
                                            builder.add(tool_ev)
                                            yield tool_ev
                                        logger.debug(
                                            f"[DIAGNOSTIC] Finished processing event kind: {event.event_kind}"
                                        )
                                        logger.debug(
                                            "[DIAGNOSTIC] About to continue to next iteration of tool_stream"
                                        )
                                logger.debug(
                                    f"[DIAGNOSTIC] Exited tool_stream loop normally - "
                                    f"processed {tool_event_count} events total"
                                )
                        except ToolConfirmationRequired:
                            # Sub-agent approval gates must propagate so the
                            # outer ToolConfirmationRequired handler can pause
                            # the conversation and surface it to the user.
                            raise
                        except Exception as tool_exc:
                            # Already handled by outer error handler – stop processing this node
                            logger.debug(
                                f"[DIAGNOSTIC] EXCEPTION in CallToolsNode processing: "
                                f"{type(tool_exc).__name__}: {str(tool_exc)}"
                            )
                            logger.debug(
                                "[DIAGNOSTIC] Exception traceback:", exc_info=True
                            )
                            logger.debug(
                                "[DIAGNOSTIC] Breaking out of tool processing due to exception"
                            )
                            break

                    # ------------------------------------------------------------------
                    # END NODE – Execution graph is finished.
                    # ------------------------------------------------------------------
                    elif isinstance(node, End):
                        end_ev = ThoughtEvent(
                            thought="Run finished; aggregating final results…",
                            user_message_id=user_msg_id,
                            llm_message_id=llm_msg_id,
                        )
                        builder.add(end_ev)
                        yield end_ev

                # After exiting the for-loop, the agent_run is complete and contains the final result.
                logger.debug(
                    "[DIAGNOSTIC] Exited all nodes. Checking agent_run.result..."
                )
                if agent_run.result:
                    result_content = str(agent_run.result.output)
                    logger.debug(
                        f"[DIAGNOSTIC] agent_run.result.output: {result_content!r}"
                    )
                    # If we failed to stream tokens (e.g. provider buffered) or the
                    # final result is longer (more complete), prefer it.
                    if not accumulated_content or len(result_content) > len(
                        accumulated_content
                    ):
                        logger.debug(
                            "[DIAGNOSTIC] Using result_content as accumulated_content "
                            "(streamed content was empty or shorter)"
                        )
                        accumulated_content = result_content
                    final_usage_data = _usage_to_dict(agent_run.result.usage())
                    # builder will add run_finished status
                else:
                    logger.debug("[DIAGNOSTIC] No agent_run.result found!")

            # --------------------------------------------------------------
            # Build and inject the final timeline, then persist via helper
            # --------------------------------------------------------------

            logger.debug("[DIAGNOSTIC] About to persist message:")
            logger.debug(
                f"[DIAGNOSTIC]   accumulated_content length: {len(accumulated_content)}"
            )
            logger.debug(
                f"[DIAGNOSTIC]   accumulated_sources count: {len(accumulated_sources)}"
            )
            if accumulated_sources:
                logger.debug(
                    f"[DIAGNOSTIC]   First source: {accumulated_sources[0].to_dict()}"
                )

            final_event = FinalEvent(
                accumulated_content=accumulated_content,
                sources=accumulated_sources,
                metadata={
                    "usage": final_usage_data,
                    "framework": "pydantic_ai",
                    "context_status": context_status,
                },
                user_message_id=user_msg_id,
                llm_message_id=llm_msg_id,
                content=accumulated_content,
            )

            builder.add(final_event)

            # Inject timeline into metadata
            final_event.metadata["timeline"] = builder.timeline

            # Persist – this is idempotent even if CoreAgentBase finalises later
            if llm_msg_id is not None:
                try:
                    await self._finalise_llm_message(
                        llm_msg_id,
                        accumulated_content,
                        accumulated_sources,
                        final_usage_data,
                        builder.timeline,
                    )
                except Exception as _err:
                    logger.exception(
                        "Failed to persist LLM message with timeline: %s", _err
                    )

            # Emit to caller (frontend)
            yield final_event

        except ToolConfirmationRequired as e:
            # Legacy exception handler - kept as fallback
            # Note: Tool approval is now handled proactively in CallToolsNode processing
            # This handler remains for backward compatibility or edge cases where
            # ToolConfirmationRequired might still be raised from tool execution
            logger.warning(
                "[PydanticAI stream] ToolConfirmationRequired caught in outer handler - "
                "this should have been handled earlier. Tool: '%s'",
                e.tool_name,
            )

            if llm_msg_id is not None:
                await self.complete_message(
                    llm_msg_id,
                    content="Awaiting user approval for tool execution.",
                    metadata={
                        "state": str(MessageState.AWAITING_APPROVAL),
                        "pending_tool_call": {
                            "name": e.tool_name,
                            "arguments": e.tool_args,
                            "tool_call_id": e.tool_call_id,
                        },
                        "framework": "pydantic_ai",
                    },
                )

            # Emit explicit approval-needed event (non-final).
            yield ApprovalNeededEvent(
                pending_tool_call={
                    "name": e.tool_name,
                    "arguments": e.tool_args,
                    "tool_call_id": e.tool_call_id,
                },
                user_message_id=user_msg_id,
                llm_message_id=llm_msg_id,
                metadata={"state": str(MessageState.AWAITING_APPROVAL)},
            )
            return

        except Exception as e:
            # Mark the message as errored in the database
            if llm_msg_id:
                await self.mark_message_error(llm_msg_id, str(e))
            logger.exception(f"Error in PydanticAI stream: {e}")

            # Emit an ErrorEvent so consumers can handle it gracefully
            error_message = str(e)
            if "UsageLimitExceeded" in type(e).__name__:
                error_message = f"Usage limit exceeded: {error_message}"

            yield ErrorEvent(
                error=error_message,
                content=f"Error: {error_message}",
                user_message_id=user_msg_id,
                llm_message_id=llm_msg_id,
                metadata={
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                    "framework": "pydantic_ai",
                },
            )

    async def _structured_response_raw(
        self,
        prompt: str,
        target_type: type[T],
        *,
        model: Optional[str] = None,
        tools: Optional[list[Union["CoreTool", Callable, str]]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> Optional[T]:
        """PydanticAI implementation of structured response extraction.

        Creates a temporary agent with the target type as output schema.
        Leverages pydantic_ai's built-in output strategies for reliable extraction.
        """
        logger.info(
            f"Generating structured response for target_type='{getattr(target_type, '__name__', str(target_type))}'"
        )

        try:
            # Build model settings with overrides.
            # ``_prepare_pydantic_ai_model_settings`` returns ``None`` when
            # both temperature and max_tokens are unset on ``self.config``
            # (the helper signals "no settings to pass" rather than
            # returning an empty dict).  We need a mutable dict here so
            # the function-level ``temperature`` / ``max_tokens`` overrides
            # — and the Anthropic temperature-0 nudge below — have
            # somewhere to land.
            model_settings = _prepare_pydantic_ai_model_settings(self.config)
            if model_settings is None:
                model_settings = {}
            if temperature is not None:
                model_settings["temperature"] = temperature
            if max_tokens is not None:
                model_settings["max_tokens"] = max_tokens

            # Anthropic models tend to keep narrating / calling tools instead
            # of committing to the structured output when given any wiggle
            # room (issue #1381). Force temperature down to 0 unless the
            # caller explicitly asked for something else (function-level
            # temperature pin OR an explicit config.temperature).
            effective_model = model or self.config.model_name
            if (
                is_anthropic_model(effective_model)
                and temperature is None
                and self.config.temperature is None
            ):
                logger.info(
                    "Forcing temperature=0 for structured extraction with "
                    "Anthropic model %s (issue #1381).",
                    effective_model,
                )
                model_settings["temperature"] = 0

            # Seed tools from the main agent so the structured run has the same capabilities
            seeded_tools_dict = _get_function_tools(self.pydantic_ai_agent)
            seeded_tools = list(seeded_tools_dict.values())

            # Per-call tools take precedence over seeded tools.
            # If a per-call tool has the same name as a seeded tool, replace it.
            override_tools: list[Callable] = []

            if tools:
                from opencontractserver.llms.api import _resolve_tools

                resolved_core_tools = _resolve_tools(tools)
                override_tools = PydanticAIToolFactory.create_tools(resolved_core_tools)
            elif self.config.tools:
                # If caller did not pass tools but config has additional wrappers
                override_tools = list(self.config.tools)

            # Build the final tool list, preferring override tools over seeded
            final_tools = deduplicate_tools(
                seeded_tools, override_tools, context="Per-call"
            )

            # Build a dedicated system prompt for structured extraction via hook
            structured_system_prompt = self._build_structured_system_prompt(
                target_type, prompt
            )

            logger.info(f"Structured system prompt: {structured_system_prompt}")

            # Preserve the pre-issue-#1381 behaviour of passing
            # ``model_settings=None`` to ``PydanticAIAgent`` when nothing
            # ended up being set, so non-Anthropic structured runs without
            # caller pins are bit-identical to before.
            structured_agent = make_pydantic_ai_agent(
                model=effective_model,
                instructions=structured_system_prompt,
                output_type=target_type,
                deps_type=PydanticAIDependencies,
                tools=final_tools,
                model_settings=model_settings or None,
                # Give pydantic-ai room to retry the structured output when
                # the model fails to commit on the first pass (issue #1381).
                output_retries=STRUCTURED_OUTPUT_RETRIES,
            )

            # Include prior conversation context if available
            history_result = await self._get_message_history()
            self._refresh_context_budget(history_result)
            # Only pass kwargs that Agent.run() accepts; ignore extras like
            # similarity_top_k that callers may pass for their own bookkeeping.
            _run_accepted = {
                "deps",
                "model",
                "model_settings",
                "usage_limits",
                "usage",
                "message_history",
                "instructions",
                "output_type",
                "metadata",
                "infer_name",
                "toolsets",
                "builtin_tools",
            }
            run_kwargs = {
                "deps": self.agent_deps,
                **{k: v for k, v in kwargs.items() if k in _run_accepted},
            }
            if history_result.messages:
                run_kwargs["message_history"] = history_result.messages

            # Run the agent with the user's prompt and full dependencies
            run_result = await structured_agent.run(
                prompt,
                **run_kwargs,
            )

            # Extract the structured result
            return run_result.output

        except Exception as e:
            logger.warning(
                f"Pydantic-AI failed to generate a valid structured response: {e}"
            )
            # Log the problematic response if available
            if hasattr(e, "body") and e.body:
                logger.warning(f"Problematic LLM response body: {e.body}")
            return None

    async def resume_with_approval(
        self,
        llm_message_id: int,
        approved: bool,
        **kwargs,
    ) -> AsyncGenerator[UnifiedStreamEvent, None]:
        """Resume a paused run after an approval decision.

        Always yields a *stream* of events so callers can iterate via
        ``async for`` regardless of approval outcome.
        """

        from django.core.exceptions import ObjectDoesNotExist

        from opencontractserver.conversations.models import ChatMessage

        try:
            paused_msg = await ChatMessage.objects.aget(id=llm_message_id)
        except ObjectDoesNotExist:  # pragma: no cover – defensive guard
            raise ValueError(f"ChatMessage {llm_message_id} not found")

        current_state = paused_msg.data.get("state")
        # Handle both enum and string values for state comparison
        awaiting_state = MessageState.AWAITING_APPROVAL
        if hasattr(awaiting_state, "value"):
            awaiting_state = awaiting_state.value

        if current_state != awaiting_state and current_state != str(
            MessageState.AWAITING_APPROVAL
        ):
            logger.warning(
                f"Message {llm_message_id} is not awaiting approval. "
                f"Current state: {current_state}, data: {paused_msg.data}"
            )
            # Check if it was already processed (handle both enum values and strings)
            completed_states = [MessageState.COMPLETED, MessageState.CANCELLED]
            completed_values = [str(s) for s in completed_states]
            if hasattr(MessageState.COMPLETED, "value"):
                # MessageState is a string-constant class today; the guard
                # is there for any future migration to ``enum.Enum`` (whose
                # members would expose ``.value``).
                completed_values.extend(
                    [getattr(s, "value", str(s)) for s in completed_states]
                )

            if current_state in completed_values:
                logger.info("Message was already processed, likely a duplicate request")
                # Return empty generator to avoid error
                return
            raise ValueError(
                f"Message is not awaiting approval (state: {current_state})"
            )

        pending = paused_msg.data.get("pending_tool_call") or {}
        # Schema invariant: when a message is awaiting approval the
        # pending_tool_call payload always carries a "name" string. Warn if
        # missing so malformed persistence state surfaces in logs instead of
        # silently driving downstream lookups with an empty tool name.
        tool_name = str(pending.get("name") or "")
        if not tool_name:
            logger.warning(
                "pending_tool_call missing 'name' for paused message %s; "
                "downstream tool dispatch will fail",
                paused_msg.id,
            )
        tool_args_raw = pending.get("arguments", {})

        # Log the raw state for debugging
        logger.info(
            f"Resume approval for tool '{tool_name}': "
            f"raw args type={type(tool_args_raw)}, value={tool_args_raw!r}"
        )

        # Normalize tool_args to always be a dict
        if isinstance(tool_args_raw, str):
            # Try to parse as JSON first
            try:
                tool_args = json.loads(tool_args_raw)
                logger.info(f"Parsed JSON args: {tool_args}")
            except json.JSONDecodeError:
                # If not JSON, assume it's a single string argument
                # For update_document_summary, the parameter is 'new_content'
                if tool_name == "update_document_summary":
                    tool_args = {"new_content": tool_args_raw}
                    logger.info(f"String arg for update_document_summary: {tool_args}")
                elif tool_name == "update_document_description":
                    tool_args = {"new_description": tool_args_raw}
                    logger.info(
                        f"String arg for update_document_description: {tool_args}"
                    )
                else:
                    # Generic fallback for other tools
                    logger.warning(
                        f"Tool args is plain string for {tool_name}: {tool_args_raw}"
                    )
                    tool_args = {"arg": tool_args_raw}
        elif isinstance(tool_args_raw, dict):
            tool_args = tool_args_raw
            logger.info(f"Args already dict: {tool_args}")
        else:
            logger.error(f"Unexpected tool_args type: {type(tool_args_raw)}")
            tool_args = {}

        # Strip internal metadata keys (prefixed with _) that are not part
        # of the tool's actual function signature.  These are injected by
        # sub-agent approval propagation (e.g. _sub_tool_name) and are
        # only needed for UI display, not for execution.
        tool_args = {k: v for k, v in tool_args.items() if not k.startswith("_")}

        # Emit ApprovalResultEvent immediately so consumers are aware of decision
        yield ApprovalResultEvent(
            decision="approved" if approved else "rejected",
            pending_tool_call=pending,
            user_message_id=paused_msg.id,
            llm_message_id=paused_msg.id,
        )

        # Determine result based on decision
        if approved:
            # Locate tool by name among config.tools if available
            wrapper_fn = None
            for tool in self.config.tools or []:
                if getattr(tool, "__name__", None) == tool_name:
                    wrapper_fn = tool
                    logger.info(f"Found tool '{tool_name}' in config.tools: {tool}")
                    break

            # Helper stub ctx carrying call-id for wrappers that expect it.
            # _EmptyDeps must have user_id, document_id, corpus_id for _check_user_permissions
            class _EmptyDeps:  # noqa: D401 – simple placeholder for deps
                skip_approval_gate = True
                user_id = None
                document_id = None
                corpus_id = None

            class _EmptyCtx:  # noqa: D401 – simple placeholder
                tool_call_id = pending.get("tool_call_id")
                skip_approval_gate = True
                deps = _EmptyDeps()

            import inspect

            async def _maybe_await(call_result):  # noqa: D401 – small helper
                return (
                    await call_result
                    if inspect.isawaitable(call_result)
                    else call_result
                )

            # Signal post-approval context so closures (e.g. ask_document_tool)
            # can bypass sub-agent approval gates without exposing a parameter
            # that the LLM could abuse.
            self.config._approval_bypass_allowed = True

            # Try to execute the tool
            tool_executed = False

            try:
                if wrapper_fn is not None:
                    # Found in config.tools - these should be callable functions
                    logger.info(
                        f"Executing tool '{tool_name}' from config.tools with args: {tool_args}"
                    )
                    try:
                        result = await _maybe_await(
                            wrapper_fn(_EmptyCtx(), **tool_args)
                        )
                        tool_executed = True
                    except TypeError as e:
                        logger.error(f"TypeError calling tool from config: {e}")
                        # Don't retry here, fall through to registry lookup

                if not tool_executed:
                    # Resort to pydantic-ai registry – returns a public ``Tool``.
                    tool_obj = _get_function_tools(self.pydantic_ai_agent).get(
                        tool_name
                    )
                    if tool_obj is None:
                        raise ValueError(f"Tool '{tool_name}' not found for execution")

                    candidate = tool_obj.function
                    if not callable(candidate):
                        raise TypeError(
                            f"Tool '{tool_name}' has a non-callable function"
                        )

                    logger.info(
                        f"Executing tool '{tool_name}' via registry with args: {tool_args}"
                    )

                    # Final check to ensure tool_args is a dict
                    if not isinstance(tool_args, dict):
                        logger.error(
                            f"tool_args is not a dict at execution time! "
                            f"Type: {type(tool_args)}, Value: {tool_args!r}"
                        )
                        # Try to recover
                        if isinstance(tool_args, str):
                            # For known tools, use the correct parameter name
                            if tool_name == "update_document_summary":
                                tool_args = {"new_content": tool_args}
                            elif tool_name == "update_document_description":
                                tool_args = {"new_description": tool_args}
                            else:
                                tool_args = {"arg": tool_args}
                        else:
                            tool_args = {}

                    try:
                        result = await _maybe_await(candidate(_EmptyCtx(), **tool_args))
                    except TypeError as e:
                        # Log full details for debugging
                        logger.error(
                            f"TypeError calling tool {tool_name}: {e}\n"
                            f"Args: {tool_args}\n"
                            f"Candidate: {candidate}\n"
                            f"Tool obj: {tool_obj}"
                        )
                        raise
            finally:
                self.config._approval_bypass_allowed = False

            tool_result = {"result": result}
            status_str = "approved"

            # Detect empty or failed results and build appropriate guidance
            tool_succeeded = True
            failure_message = None

            # Check for annotation tools returning empty results
            if tool_name in ["add_exact_string_annotations", "duplicate_annotations"]:
                if isinstance(result, dict) and "annotation_ids" in result:
                    if not result["annotation_ids"]:
                        tool_succeeded = False
                        failure_message = (
                            "The exact text strings were not found in the document. "
                            "Please inform the user that no matching text was found and "
                            "suggest verifying the exact text or trying a different search approach."
                        )
            # Check for note creation failures
            elif tool_name == "add_document_note":
                if result is None or (
                    isinstance(result, dict) and not result.get("note_id")
                ):
                    tool_succeeded = False
                    failure_message = (
                        "Failed to create the note. Please inform the "
                        "user and ask if they'd like to try again."
                    )

        else:
            tool_result = {
                "status": "rejected",
                "reason": "User did not approve execution.",
            }
            status_str = "rejected"
            tool_succeeded = False  # Rejected = not successful
            failure_message = (
                "The user rejected this tool execution. "
                "Please inform the user and ask if they would like to try a different approach."
            )

        # Build native pydantic-ai history with ToolCallPart + ToolReturnPart
        # so the LLM sees a proper tool-call / tool-return pair when it resumes.
        # Without this the LLM receives a text continuation prompt and often
        # re-invokes the same tool, creating an infinite approval loop.
        #
        # NOTE: These entries are injected as *historical context*, not live
        # tool calls.  pydantic-ai's iter() treats message_history entries as
        # past state and does NOT re-evaluate requires_approval for them.
        # The actual tool execution has already completed above, so there is
        # no risk of re-triggering the approval gate here.
        tool_call_id = pending.get("tool_call_id") or str(uuid4())
        if approved:
            history_result = await self._get_message_history()
            self._refresh_context_budget(history_result)
            resume_history = list(history_result.messages or [])

            # 1) The LLM's original tool call (ModelResponse)
            tool_call_part = ToolCallPart(
                tool_name=tool_name,
                args=json.dumps(pending.get("arguments", {}), default=str),
                tool_call_id=tool_call_id,
            )
            resume_history.append(ModelResponse(parts=[tool_call_part]))

            # 2) The tool return (ModelRequest)
            tool_return_part = ToolReturnPart(
                tool_name=tool_name,
                content=json.dumps(tool_result, default=str),
                tool_call_id=tool_call_id,
            )
            resume_history.append(ModelRequest(parts=[tool_return_part]))

        # ------------------------------------------------------------------
        # Mark the original paused message as completed/rejected BEFORE any
        # further model calls so the frontend DB poll sees the new state.
        # ------------------------------------------------------------------

        new_state = MessageState.COMPLETED if approved else MessageState.CANCELLED
        new_state_str = str(new_state)

        try:
            await self.complete_message(
                paused_msg.id,
                paused_msg.content,
                metadata={
                    **paused_msg.data,
                    "state": new_state_str,
                    "approval_decision": status_str,
                    "message_id": str(paused_msg.id),
                },
            )
        except Exception as _e:  # pragma: no cover – non-critical
            logger.warning(
                "Failed to finalise paused message after approval decision: %s",
                _e,
            )

        # If rejected – emit client-facing event(s)
        if not approved:
            rejection_msg = "Tool execution rejected by user."
            yield FinalEvent(
                accumulated_content=rejection_msg,
                sources=[],
                metadata={
                    "approval_decision": status_str,
                    "message_id": str(paused_msg.id),
                },
                user_message_id=paused_msg.id,
                llm_message_id=paused_msg.id,
                content=rejection_msg,
            )
            return

        # If approved – continue via streaming and yield downstream events.
        else:
            # New placeholder LLM message to track resumed run
            resumed_llm_id = await self.create_placeholder_message("LLM")

            # ----------------------------------------------------------
            # Determine the *actual* user message that triggered the pause
            # so that downstream events carry the correct identifier.  We
            # simply pick the most recent HUMAN message in the same
            # conversation.
            # ----------------------------------------------------------
            user_message_id: int | None = None
            from opencontractserver.conversations.models import (  # local import to avoid cycles
                ChatMessage,
                MessageTypeChoices,
            )

            if paused_msg.conversation_id:
                async for _m in ChatMessage.objects.filter(
                    conversation_id=paused_msg.conversation_id,
                    msg_type=MessageTypeChoices.HUMAN,
                ).order_by("-created"):
                    user_message_id = _m.id
                    break

            if user_message_id is None:
                user_message_id = paused_msg.id  # Fallback to previous behaviour

            # Emit ResumeEvent so consumers can start a new spinner / pane
            yield ResumeEvent(
                user_message_id=user_message_id,
                llm_message_id=resumed_llm_id,
            )

            # ----------------------------------------------------------
            # Emit tool_call / tool_result ThoughtEvents so the frontend
            # adds them to this message's timeline in real-time, and
            # build initial_timeline entries for DB persistence.
            # ----------------------------------------------------------
            tool_args_str = json.dumps(pending.get("arguments", {}), default=str)
            tool_result_str = json.dumps(tool_result, default=str)

            # ThoughtEvent for tool_call
            yield ThoughtEvent(
                thought=f"Calling tool `{tool_name}` …",
                llm_message_id=resumed_llm_id,
                user_message_id=user_message_id,
                metadata={
                    "tool_name": tool_name,
                    "args": tool_args_str,
                    "message_id": str(resumed_llm_id),
                },
            )

            # ThoughtEvent for tool_result
            yield ThoughtEvent(
                thought=f"Tool `{tool_name}` returned result",
                llm_message_id=resumed_llm_id,
                user_message_id=user_message_id,
                metadata={
                    "tool_name": tool_name,
                    "result": tool_result_str[:500],
                    "message_id": str(resumed_llm_id),
                },
            )

            # Pre-built timeline entries for DB persistence (injected into
            # _stream_core's TimelineBuilder via initial_timeline kwarg)
            initial_timeline = [
                {
                    "type": "tool_call",
                    "tool": tool_name,
                    "args": tool_args_str,
                },
                {
                    "type": "tool_result",
                    "tool": tool_name,
                    "result": tool_result_str[:500],
                },
            ]

            # ----------------------------------------------
            # Run streaming continuation via _stream_core with native
            # tool-call/tool-return history so the LLM sees a completed
            # tool round-trip and can produce a natural follow-up.
            # ----------------------------------------------

            accumulated_content = ""

            if tool_succeeded:
                continuation_prompt = (
                    "The user approved the tool call. "
                    "Please summarise what was done and continue."
                )
            else:
                continuation_prompt = (
                    f"The tool '{tool_name}' was approved but did not succeed. "
                    f"\n\n{failure_message}\n\n"
                    "IMPORTANT: Do NOT retry the same tool call. Instead, inform the user "
                    "about what happened and wait for their guidance."
                )

            logger.info(
                f"Resuming with native tool history and prompt: {continuation_prompt}"
            )

            async for ev in self._stream_core(
                continuation_prompt,
                force_llm_id=resumed_llm_id,
                force_user_msg_id=user_message_id,
                deps=self.agent_deps,
                message_history=resume_history,
                initial_timeline=initial_timeline,
            ):
                if isinstance(ev, FinalEvent):
                    ev.metadata["approval_decision"] = status_str
                    accumulated_content = ev.accumulated_content or ev.content
                yield ev

            # Ensure DB message contains approval_decision (it may have been
            # missing in _stream_core's finalisation).
            try:
                await self.conversation_manager.update_message(
                    resumed_llm_id,
                    accumulated_content,
                    metadata={"approval_decision": status_str},
                )
            except Exception:  # pragma: no cover
                logger.exception("Failed to patch approval_decision on resumed msg")

            return

    def _check_tool_requires_approval(self, tool_name: str) -> bool:
        """Check if a tool requires approval before execution.

        Args:
            tool_name: Name of the tool to check

        Returns:
            True if the tool requires approval, False otherwise
        """
        # First check tools passed to the agent config
        if self.config.tools:
            for tool in self.config.tools:
                if hasattr(tool, "__name__") and tool.__name__ == tool_name:
                    # Check if it's a wrapped PydanticAI tool
                    if hasattr(tool, "__wrapped__"):
                        # Look for the core_tool attribute in the wrapper
                        wrapper = tool
                        while hasattr(wrapper, "__wrapped__"):
                            if hasattr(wrapper, "core_tool"):
                                return wrapper.core_tool.requires_approval
                            wrapper = wrapper.__wrapped__
                    # Check if the tool itself has a requires_approval attribute
                    if hasattr(tool, "requires_approval"):
                        return tool.requires_approval

        # Check tools registered with pydantic-ai agent. Tools registered as
        # plain async callables (our common case) carry their CoreTool on the
        # underlying function, not on the Tool object — pydantic-ai 1.x's
        # Tool.requires_approval defaults to False unless the caller passes it
        # in, so we must consult the function attribute first.
        function_tools = _get_function_tools(self.pydantic_ai_agent)
        if function_tools:
            tool_obj = function_tools.get(tool_name)
            if tool_obj is not None:
                func = tool_obj.function
                core_tool = getattr(func, "core_tool", None)
                if core_tool is not None and getattr(
                    core_tool, "requires_approval", False
                ):
                    return True
                if getattr(func, "requires_approval", False):
                    return True
                return tool_obj.requires_approval

        # Default to not requiring approval
        return False

    # Expose for CoreAgentBase wrapper
    _stream_raw = _stream_core


def _prepare_pydantic_ai_model_settings(
    config: AgentConfig,
) -> Optional[dict[str, Any]]:
    """Helper to construct model_settings dict for PydanticAI Agent."""
    model_settings = {}
    if config.temperature is not None:
        model_settings["temperature"] = config.temperature
    if config.max_tokens is not None:
        model_settings["max_tokens"] = config.max_tokens
    return model_settings if model_settings else None


class PydanticAIDocumentAgent(PydanticAICoreAgent):
    """PydanticAI document agent."""

    def __init__(
        self,
        context: DocumentAgentContext,
        conversation_manager: CoreConversationManager,
        pydantic_ai_agent: PydanticAIAgent,
        agent_deps: PydanticAIDependencies,
    ):
        super().__init__(
            context.config, conversation_manager, pydantic_ai_agent, agent_deps
        )
        self.context = context

    def _build_structured_system_prompt(
        self, target_type: type[T], user_prompt: str
    ) -> str:
        """Strict extraction prompt with document context and raw-only output."""
        document_title = self.context.document.title or "untitled"
        document_id = self.context.document.id
        warn_if_content_large(document_title, context="document title")
        fenced_title = fence_user_content(document_title, label="document title")
        return (
            f"{UNTRUSTED_CONTENT_NOTICE}\n\n"
            f"You are a data extraction specialist for document {fenced_title} (ID: {document_id}).\n\n"
            "EXTRACTION PROTOCOL:\n"
            "1. You have access to tools to analyze this document. Use them "
            "to find the requested information.\n"
            "2. TOOL SELECTION — prefer `similarity_search` as the FIRST "
            "step for fact-finding queries (titles, parties, dates, defined "
            "terms, specific clauses). The search index is already chunked "
            "and ranked over structural annotations, so it is the "
            "high-quality path. Reserve `load_document_text` for "
            "whole-document tasks (summaries, exhaustive review) or as a "
            "fallback when search clearly misses. Do NOT walk the document "
            "end-to-end via sequential byte-range reads when search would "
            "answer the question.\n"
            "3. COMMIT-EARLY — as soon as a tool result contains a "
            "confident answer, you MUST stop calling tools and commit by "
            "calling the result tool with that value. Do not keep reading "
            "or re-searching to double-check, and do not scan the rest of "
            "the document just because more chunks or bytes remain. "
            "Producing the structured answer is the task; reading more is "
            "not.\n"
            "4. NEGATIVE CASE — if and only if your searches do NOT "
            "surface the answer and you are about to conclude the "
            "information is absent, you MUST first issue at least 2-3 "
            "distinct search queries that approach the question from "
            "different angles (paraphrase the question, search for key "
            "terms, search for likely answer phrasings). A single failed "
            "search is NOT sufficient evidence that the information is "
            "missing — most legal documents need multiple targeted "
            "queries to surface a relevant span. This rule applies only "
            "to giving up; once you have a confident answer, rule #3 "
            "takes precedence and you commit immediately.\n"
            "5. Return ONLY the raw extracted value matching the target "
            "type.\n"
            "6. No explanations, no citations, no commentary – just the "
            "data.\n\n"
            "Only return null/None after multiple search attempts have all "
            "failed to find relevant content."
        )

    @classmethod
    async def create(
        cls,
        document: Union[str, int, Document],
        corpus: Union[str, int, Corpus, None],
        config: Optional[AgentConfig] = None,
        tools: Optional[list[Callable]] = None,
        *,
        conversation: Optional[Conversation] = None,
        **kwargs: Any,
    ) -> "PydanticAIDocumentAgent":
        """Create a Pydantic-AI document agent tied to a specific corpus."""
        if config is None:
            config = get_default_config()

        logger.debug(
            f"Creating Pydantic-AI document agent for document {document} and corpus {corpus}"
        )
        logger.debug(f"Config (type {type(config)}): {config}")
        # Provide explicit corpus (may be None for standalone) so the factory can pick the proper embedder
        context = await CoreDocumentAgentFactory.create_context(
            document, corpus, config
        )

        # Use the CoreConversationManager factory method
        conversation_manager = await CoreConversationManager.create_for_document(
            context.corpus,  # Optional[Corpus]
            context.document,
            user_id=config.user_id,
            config=config,
            override_conversation=conversation,
        )
        # Ensure the agent's config has the potentially newly created/loaded conversation
        config.conversation = conversation_manager.conversation
        # Resolve embedder_path asynchronously if not already set
        if config.embedder_path is None:
            corpus_id_for_embedder = (
                context.corpus.id if context.corpus is not None else None
            )
            if corpus_id_for_embedder:
                try:
                    _, resolved_embedder_path = await aget_embedder(
                        corpus_id=corpus_id_for_embedder
                    )
                    if resolved_embedder_path:
                        config.embedder_path = resolved_embedder_path
                        logger.debug(f"Derived embedder_path: {config.embedder_path}")
                except Exception as e:
                    logger.warning(
                        f"Error deriving embedder_path for corpus "
                        f"{corpus_id_for_embedder}: {e}"
                    )

        model_settings = _prepare_pydantic_ai_model_settings(config)

        # ------------------------------------------------------------------
        # Ensure a vector search tool is always available so that the agent
        # can reference the primary document and emit `sources`.
        # ------------------------------------------------------------------
        _vs_kwargs: dict[str, Any] = dict(
            user_id=config.user_id,
            corpus_id=context.corpus.id if context.corpus is not None else None,
            document_id=context.document.id,
            embedder_path=config.embedder_path,
        )
        if config.embedder_path:
            # embedder_path is resolved — constructor won't hit the ORM.
            vector_store = PydanticAIAnnotationVectorStore(**_vs_kwargs)
        else:
            # Fallback: run the sync constructor (which may do ORM calls)
            # in a thread so we don't raise SynchronousOnlyOperation.
            vector_store = await sync_to_async(PydanticAIAnnotationVectorStore)(
                **_vs_kwargs
            )

        # See ``_make_similarity_search_tool`` for the citation-accumulation
        # contract; the tool name remains ``similarity_search`` so existing
        # event handlers that match on the tool name continue to work.
        default_vs_tool: Callable = _make_similarity_search_tool(
            vector_store, default_k=config.similarity_top_k
        )

        # -----------------------------
        # Auto-build pure passthrough tools from registry
        # -----------------------------
        _corpus_id = context.corpus.id if context.corpus else None
        _read_tool_names = [
            "load_document_summary",
            "get_summary_token_length",
            # NOTE: load_document_text is built as a custom adaptive tool
            # below so it can size its return to the agent's remaining
            # context budget instead of the registry's static schema.
            "get_document_description",
            "get_document_summary_diff",
            "get_document_summary_versions",
        ]
        _write_tool_names = [
            "update_document_description",
            "update_document_summary",
        ]
        # Anonymous users (user_id is None) get read-only tools only
        _auto_tool_names = (
            _read_tool_names + _write_tool_names
            if config.user_id is not None
            else _read_tool_names
        )
        auto_built_tools = _build_tools_from_registry(
            _auto_tool_names,
            document_id=context.document.id,
            corpus_id=_corpus_id,
            user_id=config.user_id,
        )

        # Corpus-required passthrough tools (only available when corpus context exists)
        corpus_passthrough_tools = (
            _build_tools_from_registry(
                [
                    "search_document_notes",
                    "get_document_notes",
                ],
                document_id=context.document.id,
                corpus_id=_corpus_id,
                user_id=config.user_id,
            )
            if context.corpus is not None
            else []
        )

        # -----------------------------
        # Build the agent's dependency snapshot now so budget-aware custom
        # tools below can close over the same instance the agent will use
        # at runtime.  Per-turn fields (estimated_used_tokens, etc.) are
        # refreshed by ``_refresh_context_budget`` at the start of each
        # turn — the closures see the live values via shared reference.
        # -----------------------------
        agent_deps_instance = PydanticAIDependencies(
            user_id=config.user_id,
            corpus_id=_corpus_id,
            document_id=context.document.id,
            max_tool_output_chars=config.compaction.max_tool_output_chars,
            model_name=config.model_name,
            context_window_tokens=get_context_window_for_model(config.model_name),
            compaction_threshold_ratio=config.compaction.threshold_ratio,
            **kwargs,
        )
        agent_deps_instance.vector_store = vector_store

        # -----------------------------
        # Custom tools (unique logic, not pure passthroughs)
        # -----------------------------
        async def get_document_text_length_tool() -> int:
            """Get the total character length of the document's plain-text extract."""
            # ``aload_document_txt_extract`` always reads the *full* file
            # into the module's text-extract cache before returning a
            # slice, so a ``(0, 1)`` call costs one disk read but
            # populates the whole document — the cached length is then
            # the real total. The fallback below covers the cache-miss
            # edge case (e.g. a future cache backend that drops entries).
            await aload_document_txt_extract(context.document.id, 0, 1)
            cached_len = get_cached_txt_extract_length(context.document.id)
            if cached_len > 0:
                return cached_len
            # Fallback: load the full text if not cached
            full_text = await aload_document_txt_extract(context.document.id)
            return len(full_text)

        get_text_length_tool = PydanticAIToolFactory.from_function(
            get_document_text_length_tool,
            name="get_document_text_length",
            description="Get the total character length of the document's plain-text extract. Use this BEFORE loading text to plan your chunking strategy.",  # noqa: E501
        )

        # -----------------------------
        # Adaptive document-text reader.
        #
        # Closes over ``agent_deps_instance`` so each call can self-size
        # against the agent's *remaining* context budget — refreshed at
        # the start of every turn by ``_refresh_context_budget``.  This
        # replaces the static 5K-50K chunking guidance with a
        # budget-driven default: when the agent has plenty of headroom
        # the tool returns large slices (cutting tool-call counts on
        # whole-document tasks like summarisation); when headroom is
        # tight it returns smaller slices to avoid forcing compaction.
        #
        # The implicit chunk has a floor (``MIN_IMPLICIT_DOCUMENT_CHUNK_CHARS``,
        # see opencontractserver/constants/context_guardrails.py) so a
        # starved budget snapshot still hands back a useful slice.
        #
        # Multi-call drift: the budget snapshot is refreshed once per *turn*,
        # not once per *tool call*. Two ``load_document_text`` calls in a
        # single turn therefore see the same ``recommended_chunk_chars()``
        # — the second call cannot tell the first already consumed budget.
        # ``agent_deps_instance.turn_implicit_doc_text_chars`` accumulates
        # the implicit-chunk bytes already returned within the turn (callers
        # that pass an explicit ``end`` opt out — they have decided their
        # own size). That counter is folded into the budget so successive
        # implicit reads back off proportionally; it is reset to ``0`` by
        # ``_refresh_context_budget`` at the start of every turn.
        # -----------------------------

        # Built by ``_make_load_document_text_tool`` so the closure body
        # can be unit-tested directly without standing up a full
        # ``DocumentAgentContext``. The closure shares
        # ``agent_deps_instance`` by reference, so mutations to
        # ``turn_implicit_doc_text_chars`` are visible across calls.
        load_document_text_tool = _make_load_document_text_tool(
            agent_deps_instance, context.document.id
        )

        load_document_text_wrapped = PydanticAIToolFactory.from_function(
            load_document_text_tool,
            name="load_document_text",
            description=(
                "Load a slice of the document's plain-text extract. By "
                "default the slice is auto-sized to the agent's remaining "
                "context budget — pass no ``end`` for whole-document tasks "
                "(e.g. summarisation) to avoid making many small calls. "
                "Pass explicit ``start``/``end`` when targeting a known "
                "character range; explicit ``end`` calls bypass the "
                "per-turn budget tally, so use them only when you have a "
                "specific target window. Returns a dict with ``text``, "
                "``total_chars``, ``returned_range`` (``[start, end)`` — "
                "the exclusive end is reported), ``chars_remaining``, "
                "``suggested_next_start`` (use this — not "
                "``returned_range[1]`` — as the next ``start``), "
                "``context_budget_chars`` (the budget that *would* drive "
                "an implicit call right now), and ``budget_was_applied`` "
                "(``True`` when the slice was budget-driven, ``False`` "
                "when ``end`` was explicit). After reading, call "
                "``search_exact_text`` on key passages to create citations."
            ),
            parameter_descriptions={
                "start": "Inclusive start character index (default 0)",
                "end": (
                    "Exclusive end character index. If omitted, defaults "
                    "to a chunk sized for the remaining context budget."
                ),
                "refresh": "If true, refresh the cached content from disk",
            },
        )

        # -----------------------------
        # Context-budget introspection tool.
        # -----------------------------
        async def get_remaining_context_budget_tool() -> dict[str, Any]:
            """Return the agent's current context-window budget snapshot.

            Useful when planning multi-step reads: tells the agent how
            many tokens it has before compaction trips and what character
            chunk size that translates to (the same calculation
            ``load_document_text`` uses for its default ``end``). The
            snapshot is taken at the start of the turn — accumulating tool
            results within a turn can shrink the real budget, so apply a
            margin if you've already loaded large outputs.
            """
            return {
                "model_name": agent_deps_instance.model_name,
                "context_window_tokens": agent_deps_instance.context_window_tokens,
                "estimated_used_tokens": agent_deps_instance.estimated_used_tokens,
                "remaining_tokens_until_compaction": (
                    agent_deps_instance.remaining_tokens_until_compaction()
                ),
                "compaction_threshold_ratio": (
                    agent_deps_instance.compaction_threshold_ratio
                ),
                "recommended_chunk_chars": (
                    agent_deps_instance.recommended_chunk_chars()
                ),
            }

        get_remaining_context_budget_wrapped = PydanticAIToolFactory.from_function(
            get_remaining_context_budget_tool,
            name="get_remaining_context_budget",
            description=(
                "Inspect the agent's remaining context-window budget for "
                "this turn. Returns model name, total context window, "
                "estimated tokens already used, tokens left before "
                "compaction trips, and the recommended character chunk "
                "size for the next ``load_document_text`` call. Use this "
                "to plan multi-step reads — particularly for whole-"
                "document tasks where you want to maximise chunk size."
            ),
        )

        # -----------------------------
        # Near-passthrough tools (result transformation)
        # -----------------------------
        async def search_exact_text_tool(search_strings: list[str]) -> list[dict]:
            """Search for exact text matches and return source nodes with location information."""
            logger.info(
                f"[search_exact_text_tool] Called with search_strings: {search_strings}"
            )
            sources = await asearch_exact_text_as_sources(
                document_id=context.document.id,
                search_strings=search_strings,
                corpus_id=context.corpus.id if context.corpus else None,
            )
            logger.info(
                f"[search_exact_text_tool] Got {len(sources)} sources from asearch_exact_text_as_sources"
            )

            # Convert SourceNode objects to dicts in the SAME format as similarity_search
            # This ensures consistent handling by PydanticAI and our event system
            result = []
            for s in sources:
                result.append(
                    {
                        "annotation_id": s.annotation_id,
                        "content": s.content,  # Use 'content' not 'rawText' to match similarity_search format
                        "similarity_score": s.similarity_score,
                        **s.metadata,  # Flatten metadata fields to top level
                    }
                )

            logger.info(f"[search_exact_text_tool] Returning {len(result)} dicts")
            if result:
                logger.info(
                    f"[search_exact_text_tool] First dict keys: {list(result[0].keys())}"
                )
                logger.info(
                    f"[search_exact_text_tool] First source content: {result[0].get('content', 'MISSING')[:50]}..."
                )
            return result

        search_exact_text_wrapped = PydanticAIToolFactory.from_function(
            search_exact_text_tool,
            name="search_exact_text",
            description=(
                "Search for exact text matches in the document. Returns source nodes with page numbers "
                "and bounding boxes (for PDFs). Perfect match similarity score of 1.0."
            ),
            parameter_descriptions={
                "search_strings": "List of exact strings to find. All occurrences of each string will be returned.",
            },
        )

        # -----------------------------
        # Genuinely custom: get_document_summary has fallback logic
        # -----------------------------
        async def get_document_summary_tool(
            truncate_length: int | None = None,
            from_start: bool = True,
        ) -> str:
            """Return the latest summary content for this document (corpus-aware)."""
            if context.corpus is None:
                # Standalone mode: fall back to document-level markdown summary
                return await aload_document_md_summary(
                    context.document.id, truncate_length, from_start
                )
            return await aget_document_summary(
                document_id=context.document.id,
                corpus_id=context.corpus.id,
                truncate_length=truncate_length,
                from_start=from_start,
            )

        get_summary_content_wrapped = PydanticAIToolFactory.from_function(
            get_document_summary_tool,
            name="get_document_summary",
            description="Retrieve the latest markdown summary content for the current document.",
            parameter_descriptions={
                "truncate_length": "Optionally truncate to this many characters",
                "from_start": "If true, truncate from the beginning; otherwise from the end",
            },
            requires_corpus=True,
        )

        # -----------------------------
        # Near-passthrough note manipulation tools (result transformation)
        # -----------------------------

        async def add_document_note_tool(title: str, content: str) -> dict[str, int]:
            """Create a new note attached to this document and return its id."""
            if config.user_id is None:
                raise PermissionError(
                    "add_document_note requires an authenticated user"
                )
            note = await aadd_document_note(
                document_id=context.document.id,
                title=title,
                content=content,
                creator_id=config.user_id,
                corpus_id=context.corpus.id if context.corpus else None,
            )
            return {"note_id": note.id}

        async def update_document_note_tool(
            note_id: int, new_content: str
        ) -> dict[str, int | None]:
            """Version-up an existing note and return new version number."""
            rev = await aupdate_document_note(
                note_id=note_id,
                new_content=new_content,
                author_id=config.user_id,
            )
            version = rev.version if rev else None
            return {"version": version}

        add_note_tool_wrapped = PydanticAIToolFactory.from_function(
            add_document_note_tool,
            name="add_document_note",
            description="Create a new note attached to the current document in this corpus.",
            parameter_descriptions={
                "title": "Title of the note",
                "content": "Full markdown content of the note",
            },
            requires_approval=True,
            requires_corpus=True,
        )

        update_note_tool_wrapped = PydanticAIToolFactory.from_function(
            update_document_note_tool,
            name="update_document_note",
            description="Update an existing note's content, creating a new revision.",
            parameter_descriptions={
                "note_id": "ID of the note to update",
                "new_content": "New note content (markdown)",
            },
            requires_approval=True,
        )

        # -----------------------------
        # Annotation manipulation tools (write – require approval)
        # -----------------------------

        async def duplicate_annotations_tool(
            annotation_ids: list[int],
            new_label_text: str,
            label_type: str | None = None,
        ) -> dict[str, list[int]]:
            """Duplicate existing annotations in the current document with a new label.

            Args:
                annotation_ids: IDs of annotations to duplicate.
                new_label_text: Text for the new annotation label.
                label_type: Optional label type.

            Returns:
                Dict with key ``annotation_ids`` listing newly created IDs.
            """

            if config.user_id is None:
                raise PermissionError(
                    "duplicate_annotations_with_label requires an authenticated user"
                )
            new_ids = await aduplicate_annotations_with_label(
                annotation_ids,
                new_label_text=new_label_text,
                creator_id=config.user_id,
                label_type=label_type,
            )
            return {"annotation_ids": new_ids}

        from pydantic import BaseModel, Field

        class ExactStringEntry(BaseModel):
            """Structured entry for an exact‐string annotation request."""

            label_text: str = Field(..., description="Text of the annotation label")
            exact_string: str = Field(..., description="Exact string to annotate")

        async def add_exact_string_annotations_tool(
            entries: list[ExactStringEntry],
        ) -> dict[str, list[int]]:
            """Create annotations for *exact* string matches in the current document.

            Each *entry* provides ``label_text`` and ``exact_string``.  The tool
            automatically applies all entries to the current document & corpus.
            """

            # Accept both ExactStringEntry instances *and* plain dicts coming
            # back from the approval metadata.
            norm_entries: list[ExactStringEntry] = []
            for ent in entries:
                if isinstance(ent, ExactStringEntry):
                    norm_entries.append(ent)
                elif isinstance(ent, dict):
                    try:
                        norm_entries.append(ExactStringEntry(**ent))
                    except Exception as _exc:  # pragma: no cover – validation guard
                        raise ValueError(
                            "Invalid entry format for add_exact_string_annotations"
                        ) from _exc
                else:  # pragma: no cover – defensive
                    raise TypeError(
                        "Unsupported entry type for add_exact_string_annotations"
                    )

            items: list[AnnotationItem] = [
                AnnotationItem(
                    label_text=e.label_text,
                    exact_string=e.exact_string,
                )
                for e in norm_entries
            ]

            if config.user_id is None:
                raise PermissionError(
                    "add_exact_string_annotations requires an authenticated user"
                )
            if context.corpus is None:
                raise ValueError(
                    "add_exact_string_annotations requires the agent to be scoped to a corpus"
                )
            new_ids = await aadd_annotations_from_exact_strings(
                items,
                document_id=context.document.id,
                corpus_id=context.corpus.id,
                creator_id=config.user_id,
                corpus_action_id=config.corpus_action_id,
            )
            return {"annotation_ids": new_ids}

        duplicate_ann_tool_wrapped = PydanticAIToolFactory.from_function(
            duplicate_annotations_tool,
            name="duplicate_annotations",
            description="Duplicate existing annotations with a new label (requires approval).",
            parameter_descriptions={
                "annotation_ids": "List of source annotation IDs",
                "new_label_text": "Text for the new label",
                "label_type": "Optional label type override",
            },
            requires_approval=True,
            requires_corpus=True,
        )

        add_exact_ann_tool_wrapped = PydanticAIToolFactory.from_function(
            add_exact_string_annotations_tool,
            name="add_exact_string_annotations",
            description="Add annotations for exact string matches in the current document (requires approval).",
            parameter_descriptions={
                "entries": "List of objects with keys 'label_text' and 'exact_string'",
            },
            requires_approval=True,
            requires_corpus=True,
        )

        # Merge caller-supplied tools (if any) after the default ones so callers
        # can override behaviour/order if desired.
        # Build the list conditionally to avoid corpus-required tools in standalone mode.
        effective_tools: list[Callable] = [
            default_vs_tool,  # genuinely custom (vector store bound method)
            get_text_length_tool,  # genuinely custom (cache access)
            load_document_text_wrapped,  # adaptive: budget-aware chunk size
            get_remaining_context_budget_wrapped,  # context-budget introspection
            *auto_built_tools,  # registry-driven passthrough tools
            search_exact_text_wrapped,  # near-passthrough (result transform)
        ]

        if context.corpus is not None:
            # Only add corpus-dependent tools when corpus is available
            effective_tools.extend(corpus_passthrough_tools)
            effective_tools.append(
                get_summary_content_wrapped  # genuinely custom (fallback logic)
            )
            # Write tools only for authenticated users
            if config.user_id is not None:
                effective_tools.extend(
                    [
                        add_note_tool_wrapped,  # near-passthrough (result transform)
                        update_note_tool_wrapped,  # near-passthrough (result transform)
                        duplicate_ann_tool_wrapped,  # near-passthrough (result transform)
                        add_exact_ann_tool_wrapped,  # near-passthrough (complex normalization)
                    ]
                )
        restrict_tool_names: set[str] | None = kwargs.pop("restrict_tool_names", None)
        if restrict_tool_names is not None:
            # Restrict mode: only keep tools whose names appear in the
            # specified set.  This prevents tool overload when the caller
            # (e.g. corpus actions) specifies an exact tool set.  The
            # set uses original string names so runtime-context tools
            # (e.g. get_document_text_length) that aren't in FUNCTION_MAP
            # are still preserved.
            allowed = set(restrict_tool_names)
            before_count = len(effective_tools)
            effective_tools = [
                t for t in effective_tools if get_tool_name(t) in allowed
            ]
            # Now apply caller overrides (tools from registry) on top
            if tools:
                effective_tools = deduplicate_tools(
                    effective_tools, tools, context="Caller"
                )
            logger.info(
                "Restricted agent tools to %d (from %d defaults)",
                len(effective_tools),
                before_count,
            )
        elif tools:
            effective_tools = deduplicate_tools(
                effective_tools, tools, context="Caller"
            )

        tool_names = [get_tool_name(t) for t in effective_tools]
        logger.info(
            "Creating pydantic-ai agent: model=%s, tools=%s",
            config.model_name,
            tool_names,
        )
        logger.info(f"Created pydantic ai agent with context {config.system_prompt}")
        pydantic_ai_agent_instance = make_pydantic_ai_agent(
            model=config.model_name,
            instructions=config.system_prompt,
            deps_type=PydanticAIDependencies,
            tools=effective_tools,
            model_settings=model_settings,
        )

        return cls(
            context=context,
            conversation_manager=conversation_manager,
            pydantic_ai_agent=pydantic_ai_agent_instance,
            agent_deps=agent_deps_instance,
        )


class PydanticAICorpusAgent(PydanticAICoreAgent):
    """PydanticAI corpus agent."""

    def __init__(
        self,
        context: CorpusAgentContext,
        conversation_manager: CoreConversationManager,
        pydantic_ai_agent: PydanticAIAgent,
        agent_deps: PydanticAIDependencies,
    ):
        super().__init__(
            context.config, conversation_manager, pydantic_ai_agent, agent_deps
        )
        self.context = context

    def _build_structured_system_prompt(
        self, target_type: type[T], user_prompt: str
    ) -> str:
        """Strict extraction prompt with corpus context and raw-only output."""
        corpus_id = self.context.corpus.id
        corpus_title = self.context.corpus.title or "untitled"
        warn_if_content_large(corpus_title, context="corpus title")
        fenced_title = fence_user_content(corpus_title, label="corpus title")
        return (
            f"{UNTRUSTED_CONTENT_NOTICE}\n\n"
            f"You are a data extraction specialist for corpus {fenced_title} (ID: {corpus_id}).\n\n"
            "EXTRACTION PROTOCOL:\n"
            "1. You have access to tools to analyze this corpus. Use them "
            "to find the requested information.\n"
            "2. TOOL SELECTION — prefer `similarity_search` as the FIRST "
            "step for fact-finding queries. The search index is already "
            "chunked and ranked over structural annotations, so it is the "
            "high-quality retrieval path. Reserve byte-range readers and "
            "document-coordination tools for whole-corpus tasks "
            "(summaries, exhaustive review) or as a fallback when search "
            "clearly misses. Do NOT walk documents end-to-end via "
            "sequential byte-range reads when search would answer the "
            "question.\n"
            "3. COMMIT-EARLY — as soon as a tool result contains a "
            "confident answer, you MUST stop calling tools and commit by "
            "calling the result tool with that value. Do not keep reading "
            "or re-searching to double-check, and do not exhaustively "
            "scan additional documents just because more remain. "
            "Producing the structured answer is the task; reading more is "
            "not.\n"
            "4. NEGATIVE CASE — if and only if your searches do NOT "
            "surface the answer and you are about to conclude the "
            "information is absent, you MUST first issue at least 2-3 "
            "distinct search queries that approach the question from "
            "different angles (paraphrase the question, search for key "
            "terms, search for likely answer phrasings). A single failed "
            "search is NOT sufficient evidence that the information is "
            "missing — most legal corpora need multiple targeted "
            "queries to surface a relevant span. This rule applies only "
            "to giving up; once you have a confident answer, rule #3 "
            "takes precedence and you commit immediately.\n"
            "5. Return ONLY the raw extracted value matching the target "
            "type.\n"
            "6. No explanations, no citations, no commentary – just the "
            "data.\n\n"
            "Only return null/None after multiple search attempts have all "
            "failed to find relevant content."
        )

    @classmethod
    async def create(
        cls,
        corpus: Union[int, str, Corpus],
        config: Optional[AgentConfig] = None,
        tools: Optional[list[Callable]] = None,
        conversation: Optional[Conversation] = None,
        **kwargs,
    ) -> "PydanticAICorpusAgent":
        """Create a PydanticAI corpus agent using core functionality."""
        if config is None:
            config = get_default_config()

        if not isinstance(corpus, Corpus):  # Ensure corpus is loaded if ID is passed
            corpus_obj = await Corpus.objects.aget(id=corpus)
        else:
            corpus_obj = corpus

        context = await CoreCorpusAgentFactory.create_context(corpus_obj, config)

        # Use the CoreConversationManager factory method
        conversation_manager = await CoreConversationManager.create_for_corpus(
            corpus=corpus_obj,
            user_id=config.user_id,
            config=config,
            override_conversation=conversation,
        )
        # Ensure the agent's config has the potentially newly created/loaded conversation
        config.conversation = conversation_manager.conversation

        # Resolve embedder_path asynchronously if not already set
        if config.embedder_path is None and corpus_obj and corpus_obj.id:
            logger.debug(
                f"Attempting to derive embedder_path for corpus {corpus_obj.id} asynchronously."
            )
            try:
                _, resolved_embedder_path = await aget_embedder(corpus_id=corpus_obj.id)
                if resolved_embedder_path:
                    config.embedder_path = resolved_embedder_path
                    logger.debug(f"Derived embedder_path: {config.embedder_path}")
                else:
                    logger.warning(
                        f"Could not derive embedder_path for corpus {corpus_obj.id}."
                    )
            except Exception as e:
                logger.warning(
                    f"Error deriving embedder_path for corpus {corpus_obj.id}: {e}"
                )

        model_settings = _prepare_pydantic_ai_model_settings(config)

        # ------------------------------------------------------------------
        # Ensure a vector search tool is always available so that the agent
        # can reference the primary document and emit `sources`.
        # ------------------------------------------------------------------
        _vs_kwargs = dict(
            user_id=config.user_id,
            corpus_id=context.corpus.id,
            embedder_path=config.embedder_path,
        )
        if config.embedder_path:
            # embedder_path is resolved — constructor won't hit the ORM.
            vector_store = PydanticAIAnnotationVectorStore(**_vs_kwargs)
        else:
            # Fallback: run the sync constructor (which may do ORM calls)
            # in a thread so we don't raise SynchronousOnlyOperation.
            vector_store = await sync_to_async(PydanticAIAnnotationVectorStore)(
                **_vs_kwargs
            )

        # See ``_make_similarity_search_tool`` for the shared citation-capturing
        # closure used by both the document and corpus agent factories.
        default_vs_tool: Callable = _make_similarity_search_tool(
            vector_store, default_k=config.similarity_top_k
        )

        # -----------------------------
        # Auto-build passthrough tools from registry
        # -----------------------------
        corpus_auto_tools = _build_tools_from_registry(
            ["get_corpus_description"],
            corpus_id=context.corpus.id,
            user_id=config.user_id,
        )

        # Near-passthrough: update_corpus_description has result transformation
        async def update_corpus_description_tool(
            new_content: str,
        ) -> dict[str, int | None]:
            """Update the corpus description and return new version number (if changed)."""
            rev = await aupdate_corpus_description(
                corpus_id=context.corpus.id,
                new_content=new_content,
                author_id=config.user_id,
            )
            version = rev.version if rev else None
            return {"version": version}

        update_corpus_desc_tool_wrapped = PydanticAIToolFactory.from_function(
            update_corpus_description_tool,
            name="update_corpus_description",
            description="Update corpus description with new markdown text, creating a revision if changed.",
            parameter_descriptions={
                "new_content": "Full markdown content",
            },
            requires_corpus=True,
            requires_approval=True,
        )

        # -----------------------------
        # Document coordination tools – empower corpus agent to talk to per-document agents
        # -----------------------------

        from opencontractserver.llms import (
            agents as _agents_api,  # local import to avoid circulars
        )
        from opencontractserver.llms.types import AgentFramework as _AgentFramework

        async def list_documents_tool() -> list[dict[str, Any]]:
            """Return basic metadata for all documents in the current corpus.

            Each list entry contains ``document_id``, ``title`` and ``description`` so
            the coordinator LLM can decide which document-specific agent to consult.
            """
            return [
                {
                    "document_id": doc.id,
                    "title": doc.title,
                    "description": getattr(doc, "description", ""),
                }
                for doc in context.documents
            ]

        async def ask_document_tool(
            document_id: int,
            question: str,
        ) -> dict[str, Any]:
            """Ask a question to a **document-specific** agent inside this corpus.

            The call transparently streams the document agent so we can capture
            its *full* reasoning timeline (tool calls, vector-search citations…)
            and surface that back to the coordinator LLM.

            Args:
                document_id: ID of the target document (must belong to this corpus).
                question:   The natural-language question to forward.

            Returns:
                An object with keys:
                    answer (str)   – final assistant answer
                    sources (list) – flattened source dicts
                    timeline (list) – detailed reasoning/events emitted by the sub-agent
            """

            from pydantic import BaseModel, Field

            class DocAnswer(BaseModel):
                """Structured result returned by the `ask_document` tool."""

                answer: str = Field(description="The document agent's final answer")
                sources: list[dict] = Field(
                    default_factory=list,
                    description="Flattened citation objects produced by the document agent",
                )
                timeline: list[dict] = Field(
                    default_factory=list,
                    description="Event timeline (thoughts, tool calls, etc.) from the document agent run",
                )

            # Guard against cross-corpus leakage – return a structured error
            # payload instead of raising so the LLM can inform the user
            # gracefully (see issue #820).
            if document_id not in {d.id for d in context.documents}:
                available = [{"id": d.id, "title": d.title} for d in context.documents]
                logger.warning(
                    f"[ask_document] Document {document_id} not found in corpus documents. "
                    f"Available document IDs: {[d.id for d in context.documents]}"
                )
                return DocAnswer(
                    answer=(
                        f"Error: Document {document_id} does not belong to the "
                        f"current corpus. Available documents: {available}"
                    ),
                    sources=[],
                    timeline=[],
                ).model_dump()

            # The _approval_bypass_allowed flag is set by resume_with_approval()
            # when the user has already approved the sub-agent tool.  It is NOT
            # exposed as a function parameter to prevent LLM prompt injection.
            bypass = getattr(config, "_approval_bypass_allowed", False)

            doc_agent = await _agents_api.for_document(
                document=document_id,
                corpus=context.corpus.id,
                user_id=config.user_id,
                store_user_messages=False,
                store_llm_messages=False,
                framework=_AgentFramework.PYDANTIC_AI,
                skip_approval_gate=bypass,
            )

            # Side-channel observer from AgentConfig (set by WebSocket layer)
            observer_cb = getattr(config, "stream_observer", None)

            accumulated_answer: str = ""
            captured_sources: list[dict] = []
            captured_timeline: list[dict] = []

            async for ev in doc_agent.stream(question):
                # Capture content
                if getattr(ev, "type", "") == "content":
                    accumulated_answer += getattr(ev, "content", "")

                # ----------------------------------------------------------
                # Sub-agent approval gate: if the document agent's tool
                # requires approval, surface it to the corpus agent level so
                # the user is prompted.  We raise ToolConfirmationRequired
                # which the corpus agent's outer handler converts into an
                # ApprovalNeededEvent for the frontend.
                # ----------------------------------------------------------
                if getattr(ev, "type", "") == "approval_needed":
                    sub_tool = getattr(ev, "pending_tool_call", {})
                    sub_name = (
                        sub_tool.get("name") if isinstance(sub_tool, dict) else None
                    )
                    if not sub_name:
                        logger.warning(
                            "[ask_document] Received approval_needed event with "
                            "missing or malformed pending_tool_call: %r",
                            sub_tool,
                        )
                        continue
                    logger.info(
                        "[ask_document] Sub-agent requested approval for tool '%s' "
                        "– propagating to corpus agent level.",
                        sub_name,
                    )
                    raise ToolConfirmationRequired(
                        tool_name="ask_document",
                        tool_args={
                            "document_id": document_id,
                            "question": question,
                            # Preserve sub-agent tool details for the UI.
                            # Prefixed with _ so resume_with_approval strips
                            # them before calling the function.
                            "_sub_tool_name": sub_name,
                            "_sub_tool_arguments": sub_tool.get("arguments"),
                        },
                        tool_call_id=sub_tool.get("tool_call_id"),
                    )

                # Forward raw event upstream (side-channel)
                if callable(observer_cb):
                    try:
                        await observer_cb(ev)
                    except Exception:
                        logger.exception("stream_observer raised during ask_document")

                # Capture mid-stream sources
                if isinstance(ev, SourceEvent):
                    captured_sources.extend([s.to_dict() for s in ev.sources])

                # Capture timeline (thought events etc.)
                if isinstance(ev, ThoughtEvent):
                    captured_timeline.append(
                        {
                            "type": ev.type,
                            "thought": ev.thought,
                            "metadata": ev.metadata,
                        }
                    )

                if isinstance(ev, FinalEvent):
                    # Merge any final sources / timeline injected by the adapter
                    captured_sources = [
                        s.to_dict() for s in ev.sources
                    ] or captured_sources
                    if isinstance(ev.metadata, dict) and ev.metadata.get("timeline"):
                        captured_timeline = ev.metadata["timeline"]

            return DocAnswer(
                answer=accumulated_answer,
                sources=captured_sources,
                timeline=captured_timeline,
            ).model_dump()

        list_docs_tool_wrapped = PydanticAIToolFactory.from_function(
            list_documents_tool,
            name="list_documents",
            description="List all documents in the current corpus with basic metadata.",
            requires_corpus=True,
        )

        ask_doc_tool_wrapped = PydanticAIToolFactory.from_function(
            ask_document_tool,
            name="ask_document",
            description="Delegate a question to a document-specific agent and return its answer and sources.",
            parameter_descriptions={
                "document_id": "ID of the document to query (must be in this corpus)",
                "question": "The natural-language question to ask the document agent",
            },
            requires_corpus=True,
        )

        # Merge caller-supplied tools (if any) after the default ones so callers can
        # override behaviour/order if desired.
        effective_tools: list[Callable] = [
            default_vs_tool,
            *corpus_auto_tools,
            list_docs_tool_wrapped,
            ask_doc_tool_wrapped,
        ]
        # Write tools only for authenticated users
        if config.user_id is not None:
            effective_tools.append(update_corpus_desc_tool_wrapped)

        if tools:
            effective_tools = deduplicate_tools(
                effective_tools, tools, context="Caller"
            )

        pydantic_ai_agent_instance = make_pydantic_ai_agent(
            model=config.model_name,
            instructions=config.system_prompt,
            deps_type=PydanticAIDependencies,
            tools=effective_tools,
            model_settings=model_settings,
        )

        agent_deps_instance = PydanticAIDependencies(
            user_id=config.user_id,
            corpus_id=context.corpus.id,
            max_tool_output_chars=config.compaction.max_tool_output_chars,
            model_name=config.model_name,
            context_window_tokens=get_context_window_for_model(config.model_name),
            compaction_threshold_ratio=config.compaction.threshold_ratio,
            **kwargs,
        )

        agent_deps_instance.vector_store = vector_store

        return cls(
            context=context,
            conversation_manager=conversation_manager,
            pydantic_ai_agent=pydantic_ai_agent_instance,
            agent_deps=agent_deps_instance,
        )


# --------------------------------------------------------------------------- #
# helpers – rich‐event extraction                                            #
# --------------------------------------------------------------------------- #


def _event_to_text_and_meta(event: Any) -> tuple[str, bool, dict[str, Any]]:
    """Convert a *model* stream event (PartStart/Delta) to `(text, is_answer, meta)`.

    Args:
        event: The incoming event from `node.stream()`.

    Returns:
        text: ``str`` representation – empty if nothing user-visible.
        is_answer: ``True`` if this text counts towards the assistant's final
                   answer (i.e. *only* TextPart/Delta).
        meta: Any additional metadata extracted (e.g. tool name & args).
    """

    text: str = ""
    is_answer = False
    meta: dict[str, Any] = {}

    part: Any
    if isinstance(event, PartStartEvent):
        part = event.part
    elif isinstance(event, PartDeltaEvent):
        part = event.delta
    else:
        return text, is_answer, meta  # unsupported event

    # ------------------------------------------------------------------
    # Full parts
    # ------------------------------------------------------------------
    # ``part`` is the union of every full-part *and* delta-part class. Treat it
    # as ``Any`` for the dispatch below so mypy doesn't complain about each
    # ``isinstance`` narrowing into a sibling-incompatible class.
    inspected: Any = part
    if isinstance(inspected, TextPart):
        text = inspected.content
        is_answer = True
    elif isinstance(inspected, ToolCallPart):
        # Tool invocation text should not reach the user; surface via metadata only.
        meta = {"tool_name": inspected.tool_name, "args": inspected.args}
        text = ""  # suppress chatter
    elif isinstance(inspected, TextPartDelta):
        text = inspected.content_delta
        is_answer = True
    elif isinstance(inspected, ToolCallPartDelta):
        # Suppress incremental tool chatter as well
        meta = {
            "tool_name_delta": inspected.tool_name_delta,
            "args_delta": inspected.args_delta,
        }
        text = ""

    return text, is_answer, meta


def _usage_to_dict(usage: Any) -> Optional[dict[str, Any]]:
    """
    Convert a pydantic-ai ``Usage`` instance (or any other arbitrary object)
    into a plain ``dict`` that can be attached to message metadata.
    Falls back to ``vars()`` if no structured helper is available.
    """
    logger.info(f"[_usage_to_dict] Starting conversion of usage object: {usage!r}")

    if usage is None:  # noqa: D401 – early-exit guard
        logger.debug("[_usage_to_dict] Usage object is None, returning None")
        return None

    if hasattr(usage, "model_dump"):  # pydantic v2
        logger.info(
            "[_usage_to_dict] Found model_dump method, using pydantic v2 conversion"
        )
        result = usage.model_dump()
        logger.info(f"[_usage_to_dict] Pydantic v2 conversion result: {result!r}")
        return result

    if dataclasses.is_dataclass(usage) and not isinstance(
        usage, type
    ):  # dataclass instance
        logger.info("[_usage_to_dict] Object is a dataclass, using dataclasses.asdict")
        result = dataclasses.asdict(usage)
        logger.info(f"[_usage_to_dict] Dataclass conversion result: {result!r}")
        return result

    logger.warning(
        f"[_usage_to_dict] No conversion method found for usage object: {usage!r}"
    )
    return None
