"""
Celery tasks for agent memory curation.

When a conversation goes idle in a memory-enabled corpus, these tasks:
1. Summarise the conversation (privacy-preserving)
2. Feed the summary to a curation LLM that updates the corpus memory document
3. Mark the conversation as curated so it is not processed again
"""

from __future__ import annotations

import json
import logging
from datetime import timedelta

from asgiref.sync import async_to_sync
from celery import shared_task
from django.utils import timezone

from opencontractserver.constants.agent_memory import (
    MEMORY_CURATION_BATCH_LIMIT,
    MEMORY_CURATION_IDLE_MINUTES,
    MEMORY_CURATION_MAX_CONVERSATION_TOKENS,
    MEMORY_CURATION_MIN_MESSAGES,
    MEMORY_MAX_INSIGHTS_PER_CURATION,
    MEMORY_SUMMARISE_SYSTEM_PROMPT,
    MEMORY_SUMMARISE_USER_PROMPT,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Core curation task
# ---------------------------------------------------------------------------


@shared_task
def curate_corpus_memory(
    conversation_id: int,
) -> dict:
    """Reflect on a completed conversation and update corpus memory.

    This task:
    1. Loads the conversation and validates eligibility
    2. Generates a privacy-safe summary of the conversation
    3. Calls the curation LLM to propose memory updates
    4. Merges updates into the memory document
    5. Marks the conversation as curated

    Returns:
        Dict with curation outcome metadata.
    """
    return async_to_sync(_curate_corpus_memory_async)(conversation_id)


async def _curate_corpus_memory_async(conversation_id: int) -> dict:
    """Async implementation of corpus memory curation."""
    from channels.db import database_sync_to_async

    from opencontractserver.agents.memory import (
        build_curation_prompt,
        merge_curation_into_memory,
        read_memory_content,
        update_memory_content,
    )
    from opencontractserver.conversations.models import (
        Conversation,
        ConversationTypeChoices,
    )
    from opencontractserver.llms.agents.pydantic_ai_factory import (
        make_pydantic_ai_agent,
    )
    from opencontractserver.llms.context_guardrails import estimate_token_count

    # 1. Load conversation and validate
    try:
        conversation = await Conversation.objects.select_related(
            "chat_with_corpus", "chat_with_corpus__creator", "creator"
        ).aget(id=conversation_id)
    except Conversation.DoesNotExist:
        logger.warning("Conversation %s not found for curation", conversation_id)
        return {"status": "skipped", "reason": "conversation_not_found"}

    if conversation.memory_curated:
        return {"status": "skipped", "reason": "already_curated"}

    corpus = conversation.chat_with_corpus
    if not corpus or not corpus.memory_enabled:
        return {"status": "skipped", "reason": "memory_not_enabled"}

    # Only curate CHAT conversations (agent interactions), not threads
    if conversation.conversation_type != ConversationTypeChoices.CHAT:
        return {"status": "skipped", "reason": "not_chat_type"}

    # 2. Load messages and check minimum threshold BEFORE claiming.
    # This avoids permanently marking short conversations as curated,
    # which would prevent re-evaluation if more messages are added later.
    messages = await database_sync_to_async(
        lambda: list(
            conversation.chat_messages.filter(deleted_at__isnull=True)
            .order_by("created_at")
            .values_list("msg_type", "content", named=True)
        )
    )()

    if len(messages) < MEMORY_CURATION_MIN_MESSAGES:
        return {"status": "skipped", "reason": "too_few_messages"}

    # Atomically claim this conversation to prevent duplicate dispatches.
    # If another task already set memory_curated=True, updated will be 0.
    updated = await database_sync_to_async(
        lambda: Conversation.objects.filter(
            pk=conversation.pk, memory_curated=False
        ).update(memory_curated=True)
    )()
    if not updated:
        return {"status": "skipped", "reason": "already_claimed"}

    # Helper to release the claim on error so the task can be retried.
    # Defined immediately after the claim so all post-claim code can use it.
    async def _release_claim():
        await database_sync_to_async(
            lambda: Conversation.objects.filter(pk=conversation.pk).update(
                memory_curated=False
            )
        )()

    # 3. Build conversation text (truncated to budget)
    try:
        conversation_lines = []
        for msg in messages:
            role = (
                msg.msg_type.upper()
                if hasattr(msg.msg_type, "upper")
                else str(msg.msg_type)
            )
            content = msg.content or ""
            conversation_lines.append(f"[{role}]: {content}")

        conversation_text = "\n".join(conversation_lines)
        if (
            estimate_token_count(conversation_text)
            > MEMORY_CURATION_MAX_CONVERSATION_TOKENS
        ):
            # Pre-compute per-line token estimates to avoid O(n^2) re-scanning.
            line_tokens = [estimate_token_count(line) for line in conversation_lines]
            total_tokens = sum(line_tokens)
            # Drop lines from the beginning until budget is met.
            # Use an index cursor instead of list.pop(0) to avoid O(n^2).
            drop_idx = 0
            remaining = len(conversation_lines)
            while (
                total_tokens > MEMORY_CURATION_MAX_CONVERSATION_TOKENS
                and remaining > MEMORY_CURATION_MIN_MESSAGES
            ):
                total_tokens -= line_tokens[drop_idx]
                drop_idx += 1
                remaining -= 1
            conversation_lines = conversation_lines[drop_idx:]
            conversation_text = "[Earlier messages truncated]\n" + "\n".join(
                conversation_lines
            )
    except Exception:
        logger.warning(
            "Failed to build conversation text for curation of conversation %s",
            conversation_id,
            exc_info=True,
        )
        await _release_claim()
        return {"status": "error", "reason": "text_build_failed"}

    # 4. Stage 1: Summarise conversation (privacy firewall)
    from opencontractserver.llms.agents.core_agents import get_default_config

    try:
        model_name = get_default_config().model_name
    except Exception:
        logger.warning(
            "Failed to get default agent config for curation of conversation %s",
            conversation_id,
            exc_info=True,
        )
        await _release_claim()
        return {"status": "error", "reason": "config_failed"}

    summarise_agent = make_pydantic_ai_agent(
        model=model_name,
        instructions=MEMORY_SUMMARISE_SYSTEM_PROMPT,
    )

    try:
        summary_result = await summarise_agent.run(
            MEMORY_SUMMARISE_USER_PROMPT.format(conversation_text=conversation_text)
        )
        conversation_summary = str(summary_result.output)
    except Exception:
        logger.warning(
            "Failed to summarise conversation %s for curation",
            conversation_id,
            exc_info=True,
        )
        await _release_claim()
        return {"status": "error", "reason": "summarisation_failed"}

    # 5. Stage 2: Read current memory and curate
    current_memory = await read_memory_content(corpus)
    system_prompt, user_prompt = build_curation_prompt(
        current_memory=current_memory,
        conversation_text=conversation_summary,
        max_insights=MEMORY_MAX_INSIGHTS_PER_CURATION,
    )

    curation_agent = make_pydantic_ai_agent(
        model=model_name,
        instructions=system_prompt,
    )
    try:
        curation_result = await curation_agent.run(user_prompt)
        raw_output = str(curation_result.output)
    except Exception:
        logger.warning(
            "Failed to curate memory for conversation %s",
            conversation_id,
            exc_info=True,
        )
        await _release_claim()
        return {"status": "error", "reason": "curation_llm_failed"}

    # 6. Parse curation output and merge into memory
    try:
        # Try to parse as JSON
        curation_data = json.loads(raw_output)
        collection_patterns = curation_data.get("collection_patterns", [])
        query_patterns = curation_data.get("query_patterns", [])
        refinements = curation_data.get("refinements", [])

        updated_content = merge_curation_into_memory(
            current_content=current_memory,
            collection_patterns=collection_patterns,
            query_patterns=query_patterns,
            refinements=refinements,
        )
    except (json.JSONDecodeError, KeyError, TypeError):
        logger.warning(
            "Curation LLM returned non-JSON output for conversation %s, "
            "skipping merge",
            conversation_id,
        )
        await _release_claim()
        return {"status": "error", "reason": "invalid_curation_output"}

    # 7. Write updated memory
    # conversation.creator is NOT NULL in the DB, but we fall back to
    # corpus.creator as defense-in-depth in case the constraint changes.
    user = conversation.creator or corpus.creator
    try:
        await update_memory_content(corpus, updated_content, user)
    except Exception:
        logger.warning(
            "Failed to write updated memory for conversation %s",
            conversation_id,
            exc_info=True,
        )
        await _release_claim()
        raise

    logger.info(
        "Curated memory for corpus %s from conversation %s: "
        "+%d collection, +%d query, %d refinements",
        corpus.id,
        conversation_id,
        len(collection_patterns),
        len(query_patterns),
        len(refinements),
    )

    return {
        "status": "success",
        "conversation_id": conversation_id,
        "corpus_id": corpus.id,
        "new_collection_patterns": len(collection_patterns),
        "new_query_patterns": len(query_patterns),
        "refinements": len(refinements),
    }


# ---------------------------------------------------------------------------
# Periodic checker — finds idle conversations eligible for curation
# ---------------------------------------------------------------------------


@shared_task
def check_conversations_for_curation() -> dict:
    """Periodic task to find idle conversations ready for memory curation.

    Dispatches ``curate_corpus_memory`` for each eligible conversation.
    """
    from opencontractserver.conversations.models import (
        Conversation,
        ConversationTypeChoices,
    )

    cutoff = timezone.now() - timedelta(minutes=MEMORY_CURATION_IDLE_MINUTES)

    from django.db.models import Max

    eligible = (
        Conversation.objects.filter(
            memory_curated=False,
            conversation_type=ConversationTypeChoices.CHAT,
            chat_with_corpus__memory_enabled=True,
            chat_with_corpus__isnull=False,
        )
        .annotate(
            last_message_at=Max("chat_messages__created_at"),
        )
        .filter(
            # Only conversations with at least one message, idle since cutoff
            last_message_at__isnull=False,
            last_message_at__lt=cutoff,
        )
        .order_by("last_message_at")
        .values_list("id", flat=True)[:MEMORY_CURATION_BATCH_LIMIT]
    )

    dispatched = 0
    for conv_id in eligible:
        curate_corpus_memory.apply_async(args=[conv_id], queue="celery")
        dispatched += 1

    if dispatched:
        logger.info("Dispatched memory curation for %d idle conversations", dispatched)

    return {"dispatched": dispatched}
