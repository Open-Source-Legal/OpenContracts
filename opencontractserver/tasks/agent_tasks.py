"""
Celery tasks for agent response generation in threads.

When a user @mentions an agent in a chat message, these tasks handle:
1. Creating a placeholder response message
2. Building the agent with appropriate context
3. Generating the response with streaming updates via WebSocket
4. Updating the message with final content
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any, cast

from asgiref.sync import async_to_sync
from celery import shared_task
from channels.layers import get_channel_layer

from opencontractserver.conversations.models import (
    MessageStateChoices,
    MessageTypeChoices,
)

if TYPE_CHECKING:
    from opencontractserver.corpuses.models import CorpusAction
    from opencontractserver.documents.models import Document

logger = logging.getLogger(__name__)


def get_thread_channel_group(conversation_id: int) -> str:
    """Get the channel group name for a conversation/thread."""
    return f"thread_{conversation_id}"


def broadcast_to_thread(conversation_id: int, message_type: str, data: dict) -> None:
    """
    Broadcast a message to all WebSocket consumers watching a thread (sync version).

    Args:
        conversation_id: The conversation ID
        message_type: Type of message (e.g., 'agent.stream', 'agent.complete')
        data: Message payload
    """
    channel_layer = get_channel_layer()
    if not channel_layer:
        logger.warning("No channel layer configured - skipping WebSocket broadcast")
        return

    group_name = get_thread_channel_group(conversation_id)
    async_to_sync(channel_layer.group_send)(
        group_name,
        {
            "type": message_type.replace(".", "_"),  # Django Channels convention
            **data,
        },
    )


async def async_broadcast_to_thread(
    conversation_id: int, message_type: str, data: dict
) -> None:
    """
    Broadcast a message to all WebSocket consumers watching a thread (async version).

    Args:
        conversation_id: The conversation ID
        message_type: Type of message (e.g., 'agent.stream', 'agent.complete')
        data: Message payload
    """
    channel_layer = get_channel_layer()
    if not channel_layer:
        logger.warning("No channel layer configured - skipping WebSocket broadcast")
        return

    group_name = get_thread_channel_group(conversation_id)
    await channel_layer.group_send(
        group_name,
        {
            "type": message_type.replace(".", "_"),  # Django Channels convention
            **data,
        },
    )


@shared_task(bind=True, max_retries=3, default_retry_delay=5)
def generate_agent_response(
    self,
    source_message_id: int,
    agent_config_id: int,
    user_id: int,
) -> dict:
    """
    Generate an agent response to a message that mentioned the agent.

    This task:
    1. Creates a placeholder LLM message in 'in_progress' state
    2. Loads the agent configuration and builds the agent
    3. Gathers thread context (previous messages)
    4. Generates response using the agent
    5. Updates the message with final content
    6. Broadcasts updates via WebSocket

    Args:
        source_message_id: ID of the message that mentioned the agent
        agent_config_id: ID of the AgentConfiguration to use
        user_id: ID of the user who triggered the response

    Returns:
        dict with 'status', 'message_id', and optional 'error'
    """
    from django.contrib.auth import get_user_model

    from opencontractserver.agents.models import AgentConfiguration
    from opencontractserver.conversations.models import ChatMessage
    from opencontractserver.llms.agents.core_agents import (
        ContentEvent,
        FinalEvent,
        SourceEvent,
        ThoughtEvent,
    )
    from opencontractserver.llms.api import agents as agent_api

    User = get_user_model()

    response_message = None
    conversation_id = None

    try:
        # 1. Load entities
        user = User.objects.get(pk=user_id)
        source_message = ChatMessage.objects.select_related(
            "conversation", "conversation__chat_with_corpus"
        ).get(pk=source_message_id)
        agent_config = AgentConfiguration.objects.get(pk=agent_config_id)
        conversation = source_message.conversation
        conversation_id = conversation.pk
        corpus = conversation.chat_with_corpus

        logger.info(
            f"[AgentTask] Generating response for message {source_message_id} "
            f"with agent '{agent_config.name}' (id={agent_config_id})"
        )

        # 2. Create placeholder response message
        response_message = ChatMessage.objects.create(
            conversation=conversation,
            msg_type=MessageTypeChoices.LLM,
            agent_configuration=agent_config,
            content="",  # Will be filled during streaming
            parent_message=source_message,
            state=MessageStateChoices.IN_PROGRESS,
            creator=user,
        )

        # Broadcast start event
        broadcast_to_thread(
            conversation_id,
            "agent.stream_start",
            {
                "message_id": str(response_message.pk),
                "agent_id": str(agent_config_id),
                "agent_name": agent_config.name,
                "agent_slug": agent_config.slug,
            },
        )

        # 3. Get the user's message content
        user_message = source_message.content

        # 4. Generate response with streaming
        accumulated_content = ""
        sources_data: list[dict[str, Any]] = []
        timeline_data: list[dict[str, Any]] = []

        async def run_agent():
            nonlocal accumulated_content

            # Build the agent - for_corpus is async
            if corpus:
                agent = await agent_api.for_corpus(
                    corpus=corpus,
                    user_id=user.pk,
                    system_prompt=agent_config.system_instructions,
                    conversation=conversation,
                )
            else:
                # No corpus context - create a minimal agent
                # This shouldn't normally happen for thread agents
                logger.warning(
                    f"[AgentTask] No corpus found for conversation {conversation_id}"
                )
                agent = await agent_api.for_corpus(
                    corpus=1,  # Fallback - will need proper handling
                    user_id=user.pk,
                    system_prompt=agent_config.system_instructions,
                    conversation=conversation,
                )

            # Stream the agent response
            # Pass store_messages=False since we handle message persistence ourselves
            # (we already created response_message above with parent_message set)
            async for event in agent.stream(user_message, store_messages=False):
                if isinstance(event, ContentEvent):
                    # Token/content chunk
                    token = event.content
                    accumulated_content = event.accumulated_content or (
                        accumulated_content + token
                    )

                    # Broadcast token (use async version inside async context)
                    await async_broadcast_to_thread(
                        conversation_id,
                        "agent.stream_token",
                        {
                            "message_id": str(response_message.pk),
                            "token": token,
                        },
                    )

                elif isinstance(event, ThoughtEvent):
                    # Agent thinking/tool usage
                    thought = event.thought
                    metadata = event.metadata or {}
                    tool_name = metadata.get("tool_name")

                    if tool_name:
                        timeline_data.append(
                            {
                                "type": "tool_call",
                                "tool": tool_name,
                                "thought": thought,
                            }
                        )
                        await async_broadcast_to_thread(
                            conversation_id,
                            "agent.tool_call",
                            {
                                "message_id": str(response_message.pk),
                                "tool": tool_name,
                                "thought": thought,
                            },
                        )
                    else:
                        timeline_data.append(
                            {
                                "type": "thought",
                                "thought": thought,
                            }
                        )

                elif isinstance(event, SourceEvent):
                    # Sources discovered
                    if event.sources:
                        for source in event.sources:
                            sources_data.append(source.to_dict())

                elif isinstance(event, FinalEvent):
                    # Final event - use its content if we don't have accumulated
                    if event.content and not accumulated_content:
                        accumulated_content = event.content
                    if event.sources:
                        for source in event.sources:
                            if source.to_dict() not in sources_data:
                                sources_data.append(source.to_dict())

        # Run the async generator
        try:
            asyncio.run(run_agent())
        except Exception as agent_error:
            logger.exception(f"[AgentTask] Agent execution error: {agent_error}")
            # Only overwrite content if we have nothing useful
            if not accumulated_content.strip():
                accumulated_content = (
                    f"I encountered an error while processing: {str(agent_error)}"
                )
            else:
                # Append error notice to partial content
                accumulated_content += (
                    "\n\n---\n*Note: Response may be incomplete due to an error.*"
                )

        # 5. Update message with final content
        response_message.content = accumulated_content
        response_message.state = MessageStateChoices.COMPLETED
        response_message.data = {
            "sources": sources_data,
            "timeline": timeline_data,
        }
        response_message.save(update_fields=["content", "state", "data"])

        # Broadcast completion
        broadcast_to_thread(
            conversation_id,
            "agent.stream_complete",
            {
                "message_id": str(response_message.pk),
                "content": accumulated_content,
                "sources": sources_data,
                "timeline": timeline_data,
            },
        )

        logger.info(
            f"[AgentTask] Successfully generated response for message {source_message_id}"
        )

        return {
            "status": "success",
            "message_id": response_message.pk,
            "content_length": len(accumulated_content),
        }

    except User.DoesNotExist:
        logger.error(f"[AgentTask] User not found: {user_id}")
        return {"status": "error", "error": "User not found"}

    except ChatMessage.DoesNotExist:
        logger.error(f"[AgentTask] Source message not found: {source_message_id}")
        return {"status": "error", "error": "Source message not found"}

    except AgentConfiguration.DoesNotExist:
        logger.error(f"[AgentTask] Agent config not found: {agent_config_id}")
        return {"status": "error", "error": "Agent configuration not found"}

    except Exception as e:
        logger.exception(f"[AgentTask] Unexpected error: {e}")

        # Update message state to error if it was created
        if response_message:
            response_message.state = MessageStateChoices.ERROR
            response_message.content = f"Error generating response: {str(e)}"
            response_message.save(update_fields=["state", "content"])

            # Broadcast error
            if conversation_id:
                broadcast_to_thread(
                    conversation_id,
                    "agent.stream_error",
                    {
                        "message_id": str(response_message.pk),
                        "error": str(e),
                    },
                )

        # Retry on transient errors
        try:
            raise self.retry(exc=e)
        except self.MaxRetriesExceededError:
            return {"status": "error", "error": str(e)}


@shared_task
def trigger_agent_responses_for_message(message_id: int, user_id: int) -> dict:
    """
    Check a message for agent mentions and trigger responses for each.

    This is called after a message is created to handle @agent mentions.

    Args:
        message_id: ID of the newly created message
        user_id: ID of the user who created the message

    Returns:
        dict with 'agents_triggered' count and list of 'task_ids'
    """
    from opencontractserver.conversations.models import ChatMessage

    try:
        message = ChatMessage.objects.prefetch_related("mentioned_agents").get(
            pk=message_id
        )
    except ChatMessage.DoesNotExist:
        logger.error(f"[AgentTask] Message not found for trigger: {message_id}")
        return {"agents_triggered": 0, "task_ids": [], "error": "Message not found"}

    mentioned_agents = message.mentioned_agents.filter(is_active=True)

    if not mentioned_agents.exists():
        logger.debug(f"[AgentTask] No active agents mentioned in message {message_id}")
        return {"agents_triggered": 0, "task_ids": []}

    task_ids = []
    for agent in mentioned_agents:
        task = generate_agent_response.delay(
            source_message_id=message_id,
            agent_config_id=agent.pk,
            user_id=user_id,
        )
        task_ids.append(task.id)
        logger.info(
            f"[AgentTask] Triggered response task {task.id} for agent '{agent.name}'"
        )

    return {
        "agents_triggered": len(task_ids),
        "task_ids": task_ids,
    }


# --------------------------------------------------------------------------- #
# Agent-based Corpus Actions
# --------------------------------------------------------------------------- #


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def run_agent_corpus_action(
    self,
    corpus_action_id: int,
    document_id: int,
    user_id: int,
    execution_id: int | None = None,
    force: bool = False,
) -> dict:
    """
    Execute an agent-based corpus action on a single document.

    This task runs synchronously but internally uses asyncio to call
    the async agent API. It's triggered when a document is added or edited
    in a corpus that has an agent-based corpus action configured.

    Args:
        corpus_action_id: ID of the CorpusAction to execute
        document_id: ID of the Document to process
        user_id: ID of the User triggering the action
        execution_id: Optional ID of CorpusActionExecution record for tracking
        force: If True, re-run even if a completed result already exists

    Returns:
        dict with status information and result_id
    """
    import traceback

    from django.utils import timezone

    from opencontractserver.agents.models import AgentActionResult
    from opencontractserver.corpuses.models import CorpusActionExecution

    logger.info(
        f"[AgentCorpusAction] Starting: action={corpus_action_id}, "
        f"doc={document_id}, user={user_id}, execution={execution_id}"
    )

    # Mark execution as started if tracking
    execution = None
    if execution_id:
        try:
            execution = CorpusActionExecution.objects.get(id=execution_id)
            execution.mark_started()
        except CorpusActionExecution.DoesNotExist:
            logger.warning(f"[AgentCorpusAction] Execution {execution_id} not found")

    try:
        result = asyncio.run(
            _run_agent_corpus_action_async(
                corpus_action_id=corpus_action_id,
                document_id=document_id,
                user_id=user_id,
                force=force,
            )
        )

        # Mark execution as completed
        if execution:
            affected_objects = [{"type": "agent_result", "id": result.get("result_id")}]
            if result.get("conversation_id"):
                affected_objects.append(
                    {"type": "conversation", "id": result.get("conversation_id")}
                )
            execution.mark_completed(
                affected_objects=affected_objects,
                metadata={
                    "response_length": result.get("response_length"),
                    "status": result.get("status"),
                },
            )

            # Link to agent result
            if result.get("result_id"):
                execution.agent_result_id = result.get("result_id")
                execution.save(update_fields=["agent_result"])

        return result

    except Exception as exc:
        logger.error(
            f"[AgentCorpusAction] Failed: action={corpus_action_id}, "
            f"doc={document_id}, error={exc}",
            exc_info=True,
        )

        # Mark execution as failed
        if execution:
            execution.mark_failed(str(exc), traceback.format_exc())

        # Update result record with failure before retrying
        try:
            failure_record, _ = AgentActionResult.objects.get_or_create(
                corpus_action_id=corpus_action_id,
                document_id=document_id,
                defaults={
                    "creator_id": user_id,
                    "status": AgentActionResult.Status.FAILED,
                    "started_at": timezone.now(),
                },
            )
            failure_record.status = AgentActionResult.Status.FAILED
            failure_record.error_message = str(exc)[
                :1000
            ]  # Truncate to prevent DB bloat
            failure_record.completed_at = timezone.now()
            failure_record.save(
                update_fields=["status", "error_message", "completed_at"]
            )
        except Exception as e:
            logger.error(f"[AgentCorpusAction] Failed to mark result as failed: {e}")

        raise self.retry(exc=exc)


def _resolve_action_tools(action: CorpusAction, trigger: str) -> list[str]:
    """Resolve the tool list for an agent corpus action.

    Priority order:
    1. ``action.agent_config.available_tools`` (from linked agent config)
    2. Trigger-appropriate defaults from constants

    Note: ``action.pre_authorized_tools`` controls which tools skip approval
    gates — it does NOT restrict which tools are available to the agent.
    """
    from opencontractserver.constants.corpus_actions import DEFAULT_TOOLS_BY_TRIGGER

    tools: list[str] = []
    if action.agent_config:
        tools = action.agent_config.available_tools or []
    if not tools:
        tools = list(DEFAULT_TOOLS_BY_TRIGGER.get(trigger, []))

    # Warn when pre_authorized_tools references tools outside the resolved set.
    # This catches stale configs from before the semantics change where
    # pre_authorized_tools also controlled tool availability.
    if action.pre_authorized_tools:
        extra = set(action.pre_authorized_tools) - set(tools)
        if extra:
            logger.warning(
                "CorpusAction %s (id=%s) has pre_authorized_tools %s that are "
                "not in the resolved tool set. pre_authorized_tools now only "
                "controls approval gates, not tool availability.",
                action.name,
                action.id,
                sorted(extra),
            )

    return tools


def _build_document_action_system_prompt(
    action: CorpusAction,
    document: Document,
    tools: list[str],
) -> str:
    """Build a goal-oriented system prompt for automated document corpus actions.

    Combines:
    - Automation guardrails (MUST use tools, no conversation)
    - Execution context (trigger, document, corpus metadata)
    - The user's task_instructions
    - Optional supplementary guidance from agent_config.system_instructions

    SECURITY: All user-generated content (document title, corpus title,
    document description) is wrapped in <user_content> tags so the LLM can
    distinguish instructions from untrusted data.  See prompt_sanitization.py.
    """
    from opencontractserver.constants.corpus_actions import (
        MAX_DESCRIPTION_PREVIEW_LENGTH,
        TRIGGER_DESCRIPTIONS,
    )
    from opencontractserver.utils.prompt_sanitization import (
        UNTRUSTED_CONTENT_NOTICE,
        fence_user_content,
        warn_if_content_large,
    )

    trigger_desc = TRIGGER_DESCRIPTIONS.get(action.trigger, "triggered action in")
    tool_list = ", ".join(tools) if tools else "none"

    doc_title = document.title or "untitled"
    corpus_title = action.corpus.title or "untitled"
    warn_if_content_large(doc_title, context="document title")
    warn_if_content_large(corpus_title, context="corpus title")
    if document.description:
        warn_if_content_large(document.description, context="document description")

    parts = [
        "You are an automated corpus action agent. You execute tasks on documents "
        "without human interaction.",
        f"\n{UNTRUSTED_CONTENT_NOTICE}",
        "",
        "## Execution Context",
        f'- Action: "{action.name}"',
        f"- Document: {fence_user_content(doc_title, label='document title')} (ID: {document.id})",
        f"- Corpus: {fence_user_content(corpus_title, label='corpus title')}",
        f"- Trigger: Document {trigger_desc} the corpus",
        f"- Available tools: {tool_list}",
    ]

    # Inject current document metadata so the agent doesn't waste tool calls
    if document.description:
        desc = document.description[:MAX_DESCRIPTION_PREVIEW_LENGTH]
        if len(document.description) > MAX_DESCRIPTION_PREVIEW_LENGTH:
            desc += "..."
        parts.append(
            f"- Current description: {fence_user_content(desc, label='document description')}"
        )

    parts.extend(
        [
            "",
            "## Rules",
            "1. You MUST use tools to accomplish your task. Describing what you "
            "would do is NOT sufficient — call the tools.",
            "2. Do NOT ask clarifying questions. Execute the task as described.",
            "3. Ground all answers and outputs in actual document content "
            "loaded via tools. NEVER guess or fabricate document content.",
            "4. When the task requires writing or updating something, use the "
            "appropriate tool (e.g., update_document_description, "
            "update_document_summary, add_document_note).",
            "5. After completing your task, respond with a brief summary of "
            "actions taken.",
            "",
            "## Guidelines",
            "- Start by loading the document text so you have real content "
            "to work with. Use chunked reads for large documents.",
            "- Be responsive to what the task instructions ask for — whether "
            "that is summarization, analysis, annotation, classification, "
            "or any other document operation.",
            "- Use only the tools available to you. If the task requires a "
            "capability you lack, say so rather than improvising.",
            "",
            "## Task Instructions",
            action.task_instructions,
        ]
    )

    # Append supplementary guidance from agent config if present
    if action.agent_config and action.agent_config.system_instructions:
        parts.extend(
            [
                "",
                "## Additional Agent Guidance",
                action.agent_config.system_instructions,
            ]
        )

    return "\n".join(parts)


def _build_thread_action_system_prompt(
    action: CorpusAction,
    thread_context: dict,
    recent_messages: list[dict],
    tools: list[str],
    *,
    message_id: int | None = None,
    message_content: dict | None = None,
) -> str:
    """Build a goal-oriented system prompt for automated thread corpus actions.

    Combines:
    - Automation guardrails
    - Thread context (title, messages, triggering message)
    - The user's task_instructions
    - Optional supplementary guidance from agent_config.system_instructions

    SECURITY: All user-generated content (message bodies, titles, etc.)
    is wrapped in <user_content> tags so the LLM can distinguish
    instructions from untrusted data.  See prompt_sanitization.py.
    """
    from opencontractserver.utils.prompt_sanitization import (
        UNTRUSTED_CONTENT_NOTICE,
        fence_user_content,
        warn_if_content_large,
    )

    tool_list = ", ".join(tools) if tools else "none"

    warn_if_content_large(
        thread_context.get("title", "untitled"), context="thread title"
    )
    if thread_context.get("corpus_title"):
        warn_if_content_large(thread_context["corpus_title"], context="corpus title")

    parts = [
        "You are an automated corpus action agent. You execute moderation and "
        "response tasks on discussion threads without human interaction.",
        f"\n{UNTRUSTED_CONTENT_NOTICE}",
        "",
        "## Thread Context",
        f"- Thread ID: {thread_context.get('id', 'unknown')}",
        f"- Title: {fence_user_content(thread_context.get('title', 'untitled'), label='thread title')}",
        f"- Creator: {fence_user_content(thread_context.get('creator_username', 'unknown'), label='username')}",
        f"- Message count: {thread_context.get('message_count', 0)}",
        f"- Is locked: {thread_context.get('is_locked', False)}",
        f"- Is pinned: {thread_context.get('is_pinned', False)}",
    ]

    if thread_context.get("corpus_title"):
        parts.append(
            f"- Corpus: {fence_user_content(thread_context['corpus_title'], label='corpus title')}"
        )

    parts.append(f"- Available tools: {tool_list}")

    # Inject triggering message for NEW_MESSAGE triggers
    if message_id and message_content:
        raw_content = message_content.get("content", "")
        warn_if_content_large(raw_content, context="triggering message")
        parts.extend(
            [
                "",
                f"## Triggering Message (ID: {message_id})",
                f"- Author: {fence_user_content(message_content.get('creator_username', 'unknown'), label='username')}",
                f"- Content:\n{fence_user_content(raw_content, label='message body')}",
            ]
        )

    # Inject recent thread messages for context
    if recent_messages:
        from opencontractserver.constants.corpus_actions import (
            MAX_MESSAGE_PREVIEW_LENGTH,
        )

        parts.append("")
        parts.append("## Recent Thread Messages (most recent first)")
        for msg in recent_messages[:5]:
            warn_if_content_large(msg["content"], context="recent message")
            content_preview = (
                msg["content"][:MAX_MESSAGE_PREVIEW_LENGTH] + "..."
                if len(msg["content"]) > MAX_MESSAGE_PREVIEW_LENGTH
                else msg["content"]
            )
            parts.append(
                f"- [{fence_user_content(msg['creator_username'], label='username')}] (ID: {msg['id']}): "
                f"{fence_user_content(content_preview, label='message')}"
            )

    parts.extend(
        [
            "",
            "## Rules",
            "1. You MUST use tools to accomplish your task. Describing what you "
            "would do is NOT sufficient — call the tools.",
            "2. Do NOT ask clarifying questions. Execute the task as described.",
            "3. Ground your actions in the actual thread content provided above. "
            "Do not fabricate messages or user identities.",
            "4. Be responsive to the task instructions — whether that is "
            "moderation, summarization, automated replies, or other thread "
            "operations.",
            "5. After completing your task, respond with a brief summary of "
            "actions taken.",
            "",
            "## Task Instructions",
            action.task_instructions,
        ]
    )

    # Append supplementary guidance from agent config if present
    if action.agent_config and action.agent_config.system_instructions:
        parts.extend(
            [
                "",
                "## Additional Agent Guidance",
                action.agent_config.system_instructions,
            ]
        )

    return "\n".join(parts)


async def _run_agent_corpus_action_async(
    corpus_action_id: int,
    document_id: int,
    user_id: int,
    force: bool = False,
) -> dict:
    """Async implementation of agent corpus action execution."""
    from channels.db import database_sync_to_async
    from django.conf import settings
    from django.utils import timezone

    from opencontractserver.agents.models import AgentActionResult
    from opencontractserver.corpuses.models import CorpusAction
    from opencontractserver.documents.models import Document
    from opencontractserver.llms import agents

    # Load the action and document
    action = await CorpusAction.objects.select_related("agent_config", "corpus").aget(
        id=corpus_action_id
    )

    document = await Document.objects.aget(id=document_id)

    logger.info(
        f"[AgentCorpusAction] Executing '{action.name}' on document "
        f"'{document.title}' (id={document_id})"
    )

    # Create or claim result record using select_for_update for safety
    @database_sync_to_async
    def get_or_create_and_claim():
        from django.db import transaction

        # Wrap entire operation in transaction to prevent race conditions.
        # This ensures get/create and any subsequent lock/claim are atomic.
        with transaction.atomic():
            # Try to get existing record first with a lock
            existing = (
                AgentActionResult.objects.select_for_update()
                .filter(
                    corpus_action=action,
                    document=document,
                )
                .first()
            )

            if existing is None:
                # No existing record, create new one
                result = AgentActionResult.objects.create(
                    corpus_action=action,
                    document=document,
                    creator_id=user_id,
                    status=AgentActionResult.Status.RUNNING,
                    started_at=timezone.now(),
                )
                return result, "created"

            # Record exists and we hold the lock - try to claim it
            if force or existing.status not in [
                AgentActionResult.Status.RUNNING,
                AgentActionResult.Status.COMPLETED,
            ]:
                existing.status = AgentActionResult.Status.RUNNING
                existing.started_at = timezone.now()
                existing.error_message = ""
                existing.save(update_fields=["status", "started_at", "error_message"])
                return existing, "forced" if force else "claimed"

            return existing, f"already_{existing.status}"

    result, status = await get_or_create_and_claim()

    # Skip if we couldn't claim the record
    if status.startswith("already_"):
        logger.info(f"[AgentCorpusAction] {status} for doc {document_id}, skipping")
        return {"status": status, "result_id": result.id}

    try:
        # Resolve tools (Suggestion 5: defaults when none specified)
        tools = _resolve_action_tools(action, action.trigger)

        # Build goal-oriented system prompt (Suggestions 1 & 4)
        system_prompt = _build_document_action_system_prompt(action, document, tools)

        logger.debug(
            f"[AgentCorpusAction] Creating agent with tools={tools}, "
            f"instructions_length={len(action.task_instructions)}"
        )

        # Create agent with pre-authorization (skip approval gate).
        # restrict_tool_names limits the agent to ONLY the resolved tool
        # set, preventing tool overload from the ~17 default tools.
        # ``tools`` is a ``list[str]``; the API accepts any ToolType
        # (str | CoreTool | callable) but ``list`` is invariant, so cast.
        agent = await agents.for_document(
            document=document,
            corpus=action.corpus,
            user_id=user_id,
            system_prompt=system_prompt,
            tools=cast("list[Any]", tools),
            streaming=False,
            skip_approval_gate=True,
            restrict_tool_names=tools,
            corpus_action_id=corpus_action_id,
        )

        # Execute — the system prompt already contains task_instructions,
        # so we send a concise activation message rather than repeating them.
        logger.info(f"[AgentCorpusAction] Executing prompt for doc {document_id}")
        response = await agent.chat("Execute the task described in your instructions.")

        # Build execution metadata
        execution_metadata = {
            "model": getattr(settings, "LLMS_DEFAULT_MODEL", "unknown"),
            "tools_available": tools,
            "sources_count": len(response.sources) if response.sources else 0,
            "agent_config_id": action.agent_config_id,
            "agent_config_name": (
                action.agent_config.name if action.agent_config else None
            ),
        }

        # Update result with success
        result.status = AgentActionResult.Status.COMPLETED
        result.agent_response = response.content
        result.conversation_id = agent.get_conversation_id()
        result.completed_at = timezone.now()
        result.execution_metadata = execution_metadata

        @database_sync_to_async
        def save_result_completed():
            result.save()

        await save_result_completed()

        logger.info(
            f"[AgentCorpusAction] Completed: action={corpus_action_id}, "
            f"doc={document_id}, result={result.id}, "
            f"response_length={len(response.content)}"
        )

        return {
            "status": "completed",
            "result_id": result.id,
            "response_length": len(response.content),
            "conversation_id": agent.get_conversation_id(),
        }

    except Exception as e:
        # Update result with failure
        result.status = AgentActionResult.Status.FAILED
        # Truncate error message to prevent database bloat from long stack traces
        result.error_message = str(e)[:1000]
        result.completed_at = timezone.now()

        @database_sync_to_async
        def save_result_failed():
            result.save()

        await save_result_failed()

        logger.error(
            f"[AgentCorpusAction] Failed: action={corpus_action_id}, "
            f"doc={document_id}, error={e}",
            exc_info=True,
        )
        raise


# --------------------------------------------------------------------------- #
# Thread/Message Agent-based Corpus Actions
# --------------------------------------------------------------------------- #


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def run_agent_thread_action(
    self,
    corpus_action_id: int,
    conversation_id: int,
    message_id: int | None,
    user_id: int,
    execution_id: int | None = None,
) -> dict:
    """
    Execute an agent-based corpus action on a thread or message.

    This is the thread/message equivalent of run_agent_corpus_action.
    The agent receives context about the thread/message and can use
    moderation tools to take action.

    Args:
        corpus_action_id: ID of the CorpusAction to execute
        conversation_id: ID of the Conversation (thread) to process
        message_id: Optional ID of the specific message (for NEW_MESSAGE trigger)
        user_id: ID of the User (for audit trail)
        execution_id: Optional ID of CorpusActionExecution for tracking

    Returns:
        dict with status information
    """
    import traceback

    from opencontractserver.corpuses.models import CorpusActionExecution

    logger.info(
        f"[AgentThreadAction] Starting: action={corpus_action_id}, "
        f"conversation={conversation_id}, message={message_id}, user={user_id}"
    )

    # Mark execution as started
    execution = None
    if execution_id:
        try:
            execution = CorpusActionExecution.objects.get(id=execution_id)
            execution.mark_started()
        except CorpusActionExecution.DoesNotExist:
            logger.warning(f"[AgentThreadAction] Execution {execution_id} not found")

    try:
        result = asyncio.run(
            _run_agent_thread_action_async(
                corpus_action_id=corpus_action_id,
                conversation_id=conversation_id,
                message_id=message_id,
                user_id=user_id,
            )
        )

        if execution:
            affected_objects = [{"type": "agent_result", "id": result.get("result_id")}]
            if result.get("conversation_id"):
                affected_objects.append(
                    {"type": "conversation", "id": result.get("conversation_id")}
                )
            execution.mark_completed(
                affected_objects=affected_objects,
                metadata={
                    "response_length": result.get("response_length"),
                    "status": result.get("status"),
                },
            )

            # Link to agent result
            if result.get("result_id"):
                execution.agent_result_id = result.get("result_id")
                execution.save(update_fields=["agent_result"])

        return result

    except Exception as exc:
        logger.error(
            f"[AgentThreadAction] Failed: action={corpus_action_id}, "
            f"conversation={conversation_id}, error={exc}",
            exc_info=True,
        )

        if execution:
            execution.mark_failed(str(exc), traceback.format_exc())

        raise self.retry(exc=exc)


async def _run_agent_thread_action_async(
    corpus_action_id: int,
    conversation_id: int,
    message_id: int | None,
    user_id: int,
) -> dict:
    """Async implementation of agent thread action execution."""
    from channels.db import database_sync_to_async
    from django.conf import settings
    from django.utils import timezone

    from opencontractserver.agents.models import AgentActionResult
    from opencontractserver.conversations.models import ChatMessage, Conversation
    from opencontractserver.corpuses.models import CorpusAction
    from opencontractserver.llms import agents
    from opencontractserver.llms.tools.moderation_tools import (
        aget_message_content,
        aget_thread_context,
        aget_thread_messages,
    )

    # Load action and thread
    action = await CorpusAction.objects.select_related("agent_config", "corpus").aget(
        id=corpus_action_id
    )
    conversation = await Conversation.objects.aget(id=conversation_id)

    message = None
    if message_id:
        message = await ChatMessage.objects.aget(id=message_id)

    logger.info(
        f"[AgentThreadAction] Executing '{action.name}' on thread "
        f"'{conversation.title}' (id={conversation_id})"
    )

    # Gather thread context for prompt assembly
    thread_context = await aget_thread_context(conversation_id)
    thread_context["id"] = conversation_id
    recent_messages = await aget_thread_messages(conversation_id, limit=10)

    # Resolve message content if this is a NEW_MESSAGE trigger
    msg_content = None
    if message_id and message:
        msg_content = await aget_message_content(message_id)

    # Resolve tools (Suggestion 5: defaults when none specified)
    tools = _resolve_action_tools(action, action.trigger)

    # Ensure moderation tools are always available for thread actions
    from opencontractserver.llms.tools.tool_registry import (
        get_moderation_tool_names,
    )

    moderation_tools = get_moderation_tool_names()
    for tool in moderation_tools:
        if tool not in tools:
            tools.append(tool)

    # Build goal-oriented system prompt (Suggestions 1 & 4)
    system_prompt = _build_thread_action_system_prompt(
        action,
        thread_context,
        recent_messages,
        tools,
        message_id=message_id,
        message_content=msg_content,
    )

    # Create or claim result record
    @database_sync_to_async
    def get_or_create_result():
        from django.db import transaction

        # Wrap entire operation in transaction to prevent race conditions.
        # This ensures get_or_create and any subsequent lock/claim are atomic.
        with transaction.atomic():
            # Try to get existing record first with a lock
            existing = (
                AgentActionResult.objects.select_for_update()
                .filter(
                    corpus_action=action,
                    triggering_conversation=conversation,
                    triggering_message=message,
                )
                .first()
            )

            if existing is None:
                # No existing record, create new one
                result = AgentActionResult.objects.create(
                    corpus_action=action,
                    triggering_conversation=conversation,
                    triggering_message=message,
                    creator_id=user_id,
                    status=AgentActionResult.Status.RUNNING,
                    started_at=timezone.now(),
                )
                return result, "created"

            # Record exists and we hold the lock - try to claim it
            if existing.status not in [
                AgentActionResult.Status.RUNNING,
                AgentActionResult.Status.COMPLETED,
            ]:
                existing.status = AgentActionResult.Status.RUNNING
                existing.started_at = timezone.now()
                existing.error_message = ""
                existing.save(update_fields=["status", "started_at", "error_message"])
                return existing, "claimed"

            return existing, f"already_{existing.status}"

    result, status = await get_or_create_result()

    if status.startswith("already_"):
        logger.info(
            f"[AgentThreadAction] {status} for thread {conversation_id}, skipping"
        )
        return {"status": status, "result_id": result.id}

    try:
        logger.debug(
            f"[AgentThreadAction] Creating agent with tools={tools}, "
            f"instructions_length={len(action.task_instructions)}"
        )

        # Create agent with corpus context and moderation tools
        # Note: We use for_corpus since thread actions are corpus-scoped
        agent = await agents.for_corpus(
            corpus=action.corpus,
            user_id=user_id,
            system_prompt=system_prompt,
            tools=cast("list[Any]", tools),
            streaming=False,
            skip_approval_gate=True,
        )

        # Execute — the system prompt already contains task_instructions
        # and full thread context, so we send an activation message.
        logger.info(
            f"[AgentThreadAction] Executing prompt for thread {conversation_id}"
        )
        response = await agent.chat("Execute the task described in your instructions.")

        # Build execution metadata
        execution_metadata = {
            "model": getattr(settings, "LLMS_DEFAULT_MODEL", "unknown"),
            "tools_available": tools,
            "agent_config_id": action.agent_config_id,
            "agent_config_name": (
                action.agent_config.name if action.agent_config else None
            ),
            "thread_id": conversation_id,
            "message_id": message_id,
        }

        # Update result with success
        result.status = AgentActionResult.Status.COMPLETED
        result.agent_response = response.content
        result.conversation_id = agent.get_conversation_id()
        result.completed_at = timezone.now()
        result.execution_metadata = execution_metadata

        @database_sync_to_async
        def save_result_completed():
            result.save()

        await save_result_completed()

        logger.info(
            f"[AgentThreadAction] Completed: action={corpus_action_id}, "
            f"thread={conversation_id}, result={result.id}, "
            f"response_length={len(response.content)}"
        )

        return {
            "status": "completed",
            "result_id": result.id,
            "response_length": len(response.content),
            "conversation_id": agent.get_conversation_id(),
        }

    except Exception as e:
        result.status = AgentActionResult.Status.FAILED
        result.error_message = str(e)[:1000]
        result.completed_at = timezone.now()

        @database_sync_to_async
        def save_result_failed():
            result.save()

        await save_result_failed()

        logger.error(
            f"[AgentThreadAction] Failed: action={corpus_action_id}, "
            f"thread={conversation_id}, error={e}",
            exc_info=True,
        )
        raise
