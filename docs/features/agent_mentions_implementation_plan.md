# Agent Mentions in Conversations - Implementation Plan

**Issue Reference:** Extends #635 (Configurable Agent Profiles)
**Branch:** `feature/agent-mentions-in-conversations`
**Created:** 2025-11-29
**Status:** Complete
**Updated:** 2025-11-29

---

## Progress Summary

| Phase | Description | Status |
|-------|-------------|--------|
| Phase 0 | Default global agents + slug field | ✅ Complete |
| Phase 1 | Unified backend WebSocket consumer | ✅ Complete |
| Phase 2 | Shared useAgentChat() hook | ✅ Complete |
| Phase 3 | Agent mention parsing | ✅ Complete |
| Phase 4 | Agent autocomplete GraphQL | ✅ Complete |
| Phase 5 | Agent response generation | ✅ Complete |
| Phase 6 | AgentMentionPicker component | ✅ Complete |
| Phase 7 | Thread WebSocket + streaming | ✅ Complete |
| Phase 8 | Backend and frontend tests | ✅ Complete |

### Completed Work

**Phase 0:**
- Added `slug` field to `AgentConfiguration` model
- Created migration `0003_add_slug_field.py`
- Created migration `0004_ensure_default_agents.py`
- Default agents created: `default-document-agent`, `default-corpus-agent`

**Phase 1:**
- Created `config/websocket/consumers/unified_agent_conversation.py` (~500 lines)
- Updated `config/asgi.py` with new route `/ws/agent-chat/`
- All existing WebSocket tests pass (42 tests)

**Phase 2:**
- Created `frontend/src/hooks/useAgentChat.ts` (~550 lines)
- Added `getUnifiedAgentWebSocket()` to `get_websockets.ts`
- Frontend builds and lints successfully
- Hook provides unified interface for:
  - WebSocket connection management
  - Streaming message handling (ASYNC_START, ASYNC_CONTENT, ASYNC_FINISH, etc.)
  - Approval flow for permission-required tools
  - Source/timeline integration with ChatSourceAtom
  - Error handling

### Files Created/Modified

| File | Action | Description |
|------|--------|-------------|
| `opencontractserver/agents/models.py` | Modified | Added `slug` field (lines 66-73) |
| `opencontractserver/agents/migrations/0003_add_slug_field.py` | Created | Migration for slug field |
| `opencontractserver/agents/migrations/0004_ensure_default_agents.py` | Created | Data migration for default agents |
| `config/websocket/consumers/unified_agent_conversation.py` | Created | Unified WebSocket consumer (~500 lines) |
| `config/asgi.py` | Modified | Added `/ws/agent-chat/` route |
| `frontend/src/hooks/useAgentChat.ts` | Created | Shared chat hook (~550 lines) |
| `frontend/src/components/chat/get_websockets.ts` | Modified | Added `getUnifiedAgentWebSocket()` |
| `docs/features/agent_mentions_implementation_plan.md` | Modified | Updated progress tracking |
| `opencontractserver/conversations/models.py` | Modified | Added `mentioned_agents` M2M field |
| `opencontractserver/conversations/migrations/0011_add_mentioned_agents_field.py` | Created | Migration for M2M field |
| `opencontractserver/utils/mention_parser.py` | Modified | Added agent URL pattern parsing |
| `config/graphql/queries.py` | Modified | Added `search_agents_for_mention` query |
| `config/graphql/graphene_types.py` | Modified | Added `slug` and `mention_format` to AgentConfigurationType |
| `opencontractserver/tasks/agent_tasks.py` | Created | Celery tasks for agent response generation |
| `config/websocket/consumers/thread_updates.py` | Created | Thread updates WebSocket consumer |
| `frontend/src/graphql/queries.ts` | Modified | Added `SEARCH_AGENTS_FOR_MENTION` query |
| `frontend/src/components/threads/hooks/useAgentMentionSearch.ts` | Created | Hook for agent mention search |
| `frontend/src/components/widgets/selectors/AgentMentionPicker.tsx` | Created | Agent mention picker component |
| `frontend/src/hooks/useThreadWebSocket.ts` | Removed (PR #1245) | Hook for thread updates WebSocket (removed as dead code; was never wired into thread components) |

**Phase 3:**
- Added `mentioned_agents` M2M field to `ChatMessage` model
- Created migration `0011_add_mentioned_agents_field.py`
- Updated `mention_parser.py` to parse agent URL patterns:
  - `/agents/{agentSlug}` for global agents
  - `/c/{userIdent}/{corpusIdent}/agents/{agentSlug}` for corpus-scoped agents
- Updated `link_message_to_resources()` to link mentioned agents

**Phase 4:**
- Added `search_agents_for_mention` GraphQL query for autocomplete
- Added `slug` field to `AgentConfigurationType` fields list
- Added `mention_format` computed field (returns `@agent:{slug}`)
- Query supports `text_search` (searches name, slug, description) and `corpus_id` filtering

**Phase 5:**
- Created `opencontractserver/tasks/agent_tasks.py` with Celery tasks:
  - `generate_agent_response()` - generates agent response with streaming
  - `trigger_agent_responses_for_message()` - triggers responses for all mentioned agents
- Created `config/websocket/consumers/thread_updates.py` - WebSocket consumer for thread updates
  - Clients subscribe with `conversation_id` to receive streaming updates
  - Broadcasts: AGENT_STREAM_START, AGENT_STREAM_TOKEN, AGENT_TOOL_CALL, AGENT_STREAM_COMPLETE, AGENT_STREAM_ERROR
- Added `/ws/thread-updates/` route to `config/asgi.py`

**Phase 6:**
- Created `SEARCH_AGENTS_FOR_MENTION` GraphQL query in `frontend/src/graphql/queries.ts`
  - With TypeScript types `SearchAgentsForMentionInput` and `SearchAgentsForMentionOutput`
- Created `useAgentMentionSearch` hook in `frontend/src/components/threads/hooks/useAgentMentionSearch.ts`
  - Debounced search (300ms)
  - Returns `AgentMentionResource` array with id, name, slug, scope, mentionFormat
- Created `AgentMentionPicker` component in `frontend/src/components/widgets/selectors/AgentMentionPicker.tsx`
  - Dropdown UI with search input
  - Separates global agents from corpus-scoped agents
  - Keyboard navigation (arrow keys, enter, escape)
  - Uses motion animations from framer-motion
  - Styled-components following existing selector patterns

**Phase 7:**
- Added `getThreadUpdatesWebSocket()` to `frontend/src/components/chat/get_websockets.ts`
  - Builds WebSocket URL for `/ws/thread-updates/` endpoint
  - Takes conversationId and optional token
- Created `useThreadWebSocket` hook in `frontend/src/hooks/useThreadWebSocket.ts` (removed in PR #1245 as dead code; was never integrated into thread components)
  - Subscribed to thread updates for agent mention streaming
  - Handles message types: AGENT_STREAM_START, AGENT_STREAM_TOKEN, AGENT_TOOL_CALL, AGENT_STREAM_COMPLETE, AGENT_STREAM_ERROR
  - Auto-reconnect with configurable delay
  - Heartbeat/ping-pong for connection health
  - Callbacks for streaming events (onStreamStart, onStreamToken, onToolCall, onStreamComplete, onError)
  - Returns connectionState, sessionId, streamingResponses Map

**Phase 8:**
- Added `AgentMentionParserTestCase` to `test_mention_parser.py` (6 tests):
  - `test_parse_global_agent_mention` - Parses `@agent:slug` format
  - `test_parse_corpus_scoped_agent_mention` - Parses `/c/user/corpus/agents/slug` format
  - `test_parse_multiple_agent_mentions` - Parses multiple agent mentions in content
  - `test_parse_mixed_mentions` - Parses agents with users and resources
  - `test_invalid_agent_url_not_parsed` - Invalid URLs are ignored
  - `test_empty_content_has_empty_agents` - Empty content returns empty list
- Added `AgentMentionLinkingTestCase` to `test_mention_parser.py` (7 tests):
  - `test_link_global_agent` - Links global agent by slug
  - `test_link_corpus_scoped_agent` - Links corpus-scoped agent
  - `test_link_multiple_agents` - Links multiple agents
  - `test_link_mixed_valid_and_invalid_agents` - Only valid agents linked
  - `test_nonexistent_agent_not_linked` - Non-existent slugs ignored
  - `test_inactive_agent_not_linked` - Inactive agents not linked
  - `test_wrong_corpus_agent_not_linked` - Wrong corpus agents ignored
- Added `TestSearchAgentsForMention` to `test_agents.py` (6 tests):
  - `test_search_agents_returns_global_agents` - Returns global agents
  - `test_search_agents_with_corpus_returns_corpus_and_global` - Filters by corpus
  - `test_search_agents_text_search_filters` - Text search works
  - `test_search_agents_excludes_inactive` - Inactive excluded
  - `test_search_agents_search_by_description` - Search by description
  - `test_search_agents_empty_query_returns_all_visible` - All visible returned

---

## Overview

This feature enables users to mention configured agents in thread conversations using `@agent:agent-slug` syntax. When an agent is mentioned, it will process the message and respond within the thread context.

**Key Architectural Decision:** Before adding agent mentions, we will first consolidate the existing WebSocket consumers and frontend chat components. This DRY refactoring:
1. Reduces code duplication (~4000 lines of similar frontend code)
2. Creates a unified agent consumer that naturally supports agent selection
3. Makes agent mentions trivial to implement afterward

### User Story

> As a corpus user, I want to mention a configured agent (like `@agent:research-assistant`) in a thread discussion so that the agent can respond to my question within the conversation context.

### Key Capabilities

1. **Agent Mention Autocomplete** - Users can type `@agent:` to see available agents for the current corpus
2. **Agent Invocation** - Mentioning an agent triggers that agent to generate a response
3. **Scoped Agent Visibility** - Only agents configured for the current corpus (+ global agents) appear in autocomplete
4. **Multi-Agent Support** - Multiple agents can be mentioned in a single message, each responding in sequence
5. **Context-Aware Responses** - Agents have access to the full thread context when generating responses

---

## Current State Analysis

### What Exists

1. **AgentConfiguration Model** (`opencontractserver/agents/models.py:53-146`)
   - GLOBAL and CORPUS scopes
   - `system_instructions`, `available_tools`, `permission_required_tools`
   - `badge_config` for visual display
   - `visible_to_user()` queryset method for permission filtering

2. **ChatMessage Model** (`opencontractserver/conversations/models.py:603-787`)
   - Already has `agent_configuration` FK (line 650-657) - **KEY INTEGRATION POINT**
   - `msg_type` choices: SYSTEM, HUMAN, LLM
   - `state` field for message lifecycle (in_progress, completed, error, etc.)

3. **Mention System**
   - `mention_parser.py` - Parses Markdown links for users, documents, annotations, corpuses
   - `ResourceMentionPicker.tsx` - Frontend autocomplete for corpus/document mentions
   - `MentionPicker.tsx` - Frontend autocomplete for user mentions

4. **Agent Execution Infrastructure**
   - `core_agents.py` - Framework-agnostic agent execution with streaming
   - WebSocket consumers for document/corpus conversations
   - `CoreCorpusAgentFactory` - Creates corpus-level agents

5. **Thread Mutations** (`conversation_mutations.py`)
   - `CreateThreadMutation`, `CreateThreadMessageMutation`, `ReplyToMessageMutation`
   - Already call `parse_mentions_from_content()` and `link_message_to_resources()`

### Code Duplication Problem (DRY Opportunity)

**Backend - Unified Consumer (DRY refactoring completed):**
- `unified_agent_conversation.py` - Handles all agent chat contexts (corpus, document, standalone)
- Legacy consumers (`corpus_conversation.py`, `document_conversation.py`, `standalone_document_conversation.py`) have been removed

**Frontend - Two Nearly Identical Components (~4000 lines):**
- `CorpusChat.tsx` (2064 lines) - Corpus-level chat UI
- `ChatTray.tsx` (2024 lines) - Document-level chat UI

Both share ~80% of their logic:
- WebSocket connection management
- Message streaming/accumulation
- Approval flow handling
- Source/timeline merging
- UI state management

### What's Missing

1. **Unified Agent Consumer** - Single consumer that accepts `agent_id` parameter
2. **Default Global Agents** - Pre-configured agents for corpus/document contexts
3. **Agent Mention Parsing** - No `@agent:` pattern in `mention_parser.py`
4. **Agent Autocomplete Query** - No `search_agents_for_mention` GraphQL resolver
5. **Shared Frontend Chat Hook** - No `useAgentChat()` to consolidate logic

---

## Revised Architecture

### Unified Agent Consumer Design

```
┌─────────────────────────────────────────────────────────────────┐
│                    UNIFIED AGENT CONSUMER                        │
├─────────────────────────────────────────────────────────────────┤
│  WebSocket Path: /ws/agent-chat/                                │
│                                                                  │
│  Query Parameters:                                               │
│    - corpus_id: Optional[str]   (GraphQL ID)                    │
│    - document_id: Optional[str] (GraphQL ID)                    │
│    - conversation_id: Optional[str] (GraphQL ID)                │
│    - agent_id: Optional[str]    (GraphQL ID, defaults to global)│
│                                                                  │
│  Agent Selection Logic:                                          │
│    if agent_id provided:                                         │
│        agent = AgentConfiguration.get(agent_id)                 │
│    elif document_id:                                             │
│        agent = get_default_document_agent()  # GLOBAL scope     │
│    elif corpus_id:                                               │
│        agent = get_default_corpus_agent()    # GLOBAL scope     │
│    else:                                                         │
│        raise Error("No context provided")                        │
└─────────────────────────────────────────────────────────────────┘
```

### Default Global Agents

Created via data migration:

```python
# Default Corpus Agent
AgentConfiguration.objects.create(
    name="Corpus Assistant",
    slug="default-corpus-agent",
    scope="GLOBAL",
    is_active=True,
    system_instructions=settings.DEFAULT_CORPUS_AGENT_INSTRUCTIONS,
    available_tools=["similarity_search", "get_document_summary"],
)

# Default Document Agent
AgentConfiguration.objects.create(
    name="Document Assistant",
    slug="default-document-agent",
    scope="GLOBAL",
    is_active=True,
    system_instructions=settings.DEFAULT_DOCUMENT_AGENT_INSTRUCTIONS,
    available_tools=["similarity_search", "load_document_text"],
)
```

### Frontend Shared Hook Design

```typescript
// useAgentChat.ts - ALL shared WebSocket/chat logic
export function useAgentChat(options: {
  corpusId?: string;
  documentId?: string;
  conversationId?: string;
  agentId?: string;  // Optional - uses default if not specified
}) {
  // WebSocket connection
  // Message state management
  // Streaming logic
  // Approval flow
  // Source/timeline handling

  return {
    messages,
    sendMessage,
    isConnected,
    isStreaming,
    pendingApproval,
    sendApprovalDecision,
    // ...
  };
}

// CorpusChat.tsx becomes ~200 lines (UI only)
// ChatTray.tsx becomes ~200 lines (UI only)
```

---

## Implementation Phases (DRY-First Approach)

> **Key Principle:** Complete DRY refactoring FIRST (Phases 0-2) before adding agent mention features (Phases 3-5). This reduces code complexity and makes agent mentions trivial to implement.

---

### Phase 0: Create Default Global Agents (Data Migration)

Create default agents that existing consumers will use. This is a prerequisite for the unified consumer.

#### 0.1 Data Migration

**File:** `opencontractserver/agents/migrations/XXXX_create_default_global_agents.py`

```python
from django.conf import settings
from django.db import migrations

DEFAULT_CORPUS_AGENT_INSTRUCTIONS = """
You are a helpful corpus assistant. You have access to all documents in this corpus
and can search for relevant information, summarize content, and answer questions
about the corpus contents.
"""

DEFAULT_DOCUMENT_AGENT_INSTRUCTIONS = """
You are a helpful document assistant. You have access to the full text and structure
of this document and can answer questions, extract information, and explain content.
"""

def create_default_agents(apps, schema_editor):
    AgentConfiguration = apps.get_model("agents", "AgentConfiguration")

    # Default Corpus Agent
    AgentConfiguration.objects.get_or_create(
        slug="default-corpus-agent",
        defaults={
            "name": "Corpus Assistant",
            "scope": "GLOBAL",
            "is_active": True,
            "system_instructions": DEFAULT_CORPUS_AGENT_INSTRUCTIONS,
            "available_tools": ["similarity_search", "get_document_summary"],
            "description": "Default assistant for corpus-level conversations",
        }
    )

    # Default Document Agent
    AgentConfiguration.objects.get_or_create(
        slug="default-document-agent",
        defaults={
            "name": "Document Assistant",
            "scope": "GLOBAL",
            "is_active": True,
            "system_instructions": DEFAULT_DOCUMENT_AGENT_INSTRUCTIONS,
            "available_tools": ["similarity_search", "load_document_text"],
            "description": "Default assistant for document-level conversations",
        }
    )

def remove_default_agents(apps, schema_editor):
    AgentConfiguration = apps.get_model("agents", "AgentConfiguration")
    AgentConfiguration.objects.filter(
        slug__in=["default-corpus-agent", "default-document-agent"]
    ).delete()

class Migration(migrations.Migration):
    dependencies = [
        ("agents", "XXXX_previous_migration"),  # Update with actual
    ]
    operations = [
        migrations.RunPython(create_default_agents, remove_default_agents),
    ]
```

#### 0.2 Add Slug Field to AgentConfiguration (if not exists)

**File:** `opencontractserver/agents/models.py`

```python
class AgentConfiguration(BaseOCModel):
    # Existing fields...

    slug = models.CharField(
        max_length=128,
        db_index=True,
        unique=True,  # Global uniqueness for now
        null=True,
        blank=True,
        help_text="URL-friendly identifier for mentions (e.g., 'research-assistant')"
    )
```

**Migration:** Create migration to add slug field.

---

### Phase 1: Backend DRY - Unified Agent Consumer

Replace three near-identical WebSocket consumers with a single unified consumer.

#### 1.1 Create Unified Agent Consumer

**File:** `config/websocket/consumers/unified_agent_conversation.py` (IMPLEMENTED)

```python
"""
Unified WebSocket consumer for all agent conversations.

Replaced the legacy corpus_conversation.py, document_conversation.py,
and standalone_document_conversation.py (all removed).
"""
import json
import logging
from typing import Optional
from channels.generic.websocket import AsyncWebsocketConsumer
from django.conf import settings

logger = logging.getLogger(__name__)


class UnifiedAgentConsumer(AsyncWebsocketConsumer):
    """
    Single WebSocket consumer for all agent chat contexts.

    Query Parameters:
        corpus_id: Optional GraphQL ID for corpus context
        document_id: Optional GraphQL ID for document context
        conversation_id: Optional GraphQL ID for existing conversation
        agent_id: Optional GraphQL ID for specific agent (uses default if omitted)

    Agent Selection:
        1. If agent_id provided → use that agent
        2. If document_id provided → use default-document-agent
        3. If corpus_id provided → use default-corpus-agent
        4. Otherwise → error
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.corpus_id: Optional[str] = None
        self.document_id: Optional[str] = None
        self.conversation_id: Optional[str] = None
        self.agent_id: Optional[str] = None
        self.agent = None
        self.room_group_name: Optional[str] = None

    async def connect(self):
        """Authenticate, extract context, and initialize agent."""
        # Extract query parameters
        query_string = self.scope.get("query_string", b"").decode()
        params = dict(p.split("=") for p in query_string.split("&") if "=" in p)

        self.corpus_id = params.get("corpus_id")
        self.document_id = params.get("document_id")
        self.conversation_id = params.get("conversation_id")
        self.agent_id = params.get("agent_id")

        # Authenticate
        user = self.scope.get("user")
        if not user or not user.is_authenticated:
            await self.close(code=4001)
            return

        # Validate context and permissions
        if not await self._validate_context(user):
            await self.close(code=4003)
            return

        # Resolve agent
        self.agent = await self._resolve_agent()
        if not self.agent:
            await self.close(code=4004)
            return

        # Set up room group
        self.room_group_name = self._get_room_group_name()
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)

        await self.accept()
        logger.info(f"Agent consumer connected: {self.room_group_name}")

    async def disconnect(self, close_code):
        if self.room_group_name:
            await self.channel_layer.group_discard(
                self.room_group_name, self.channel_name
            )

    async def receive(self, text_data):
        """Handle incoming chat messages."""
        data = json.loads(text_data)
        message_type = data.get("type")

        if message_type == "chat_message":
            await self._handle_chat_message(data)
        elif message_type == "approval":
            await self._handle_approval(data)
        elif message_type == "cancel":
            await self._handle_cancel(data)

    async def _validate_context(self, user) -> bool:
        """Validate user has access to the specified context."""
        from asgiref.sync import sync_to_async

        if self.corpus_id:
            from opencontractserver.corpuses.models import Corpus
            try:
                await sync_to_async(
                    Corpus.objects.visible_to_user(user).get
                )(pk=self._decode_id(self.corpus_id))
            except Corpus.DoesNotExist:
                return False

        if self.document_id:
            from opencontractserver.documents.models import Document
            try:
                await sync_to_async(
                    Document.objects.visible_to_user(user).get
                )(pk=self._decode_id(self.document_id))
            except Document.DoesNotExist:
                return False

        return True

    async def _resolve_agent(self):
        """Resolve which agent to use based on context."""
        from asgiref.sync import sync_to_async
        from opencontractserver.agents.models import AgentConfiguration

        # Priority 1: Explicit agent_id
        if self.agent_id:
            try:
                return await sync_to_async(
                    AgentConfiguration.objects.get
                )(pk=self._decode_id(self.agent_id), is_active=True)
            except AgentConfiguration.DoesNotExist:
                logger.error(f"Specified agent not found: {self.agent_id}")
                return None

        # Priority 2: Document context → default document agent
        if self.document_id:
            try:
                return await sync_to_async(
                    AgentConfiguration.objects.get
                )(slug="default-document-agent", is_active=True)
            except AgentConfiguration.DoesNotExist:
                logger.error("Default document agent not found")
                return None

        # Priority 3: Corpus context → default corpus agent
        if self.corpus_id:
            try:
                return await sync_to_async(
                    AgentConfiguration.objects.get
                )(slug="default-corpus-agent", is_active=True)
            except AgentConfiguration.DoesNotExist:
                logger.error("Default corpus agent not found")
                return None

        logger.error("No context provided for agent resolution")
        return None

    def _get_room_group_name(self) -> str:
        """Generate unique room group name based on context."""
        if self.conversation_id:
            return f"conversation_{self.conversation_id}"
        if self.document_id:
            return f"document_{self.document_id}_{self.scope['user'].id}"
        if self.corpus_id:
            return f"corpus_{self.corpus_id}_{self.scope['user'].id}"
        return f"agent_{self.agent.id}_{self.scope['user'].id}"

    def _decode_id(self, global_id: str) -> int:
        """Decode GraphQL global ID to database PK."""
        from graphene.relay import Node
        try:
            _, pk = Node.from_global_id(global_id)
            return int(pk)
        except:
            return int(global_id)  # Fallback to raw ID

    async def _handle_chat_message(self, data):
        """Process chat message and stream agent response."""
        from opencontractserver.llms import agents as agent_factory
        from asgiref.sync import sync_to_async

        message = data.get("message", "")
        user = self.scope["user"]

        # Build agent based on context
        if self.document_id:
            agent = await sync_to_async(agent_factory.for_document_sync)(
                document_pk=self._decode_id(self.document_id),
                user_id=user.id,
                corpus_pk=self._decode_id(self.corpus_id) if self.corpus_id else None,
                system_instructions=self.agent.system_instructions,
                tools=self.agent.available_tools,
            )
        elif self.corpus_id:
            agent = await sync_to_async(agent_factory.for_corpus_sync)(
                corpus=self._decode_id(self.corpus_id),
                user_id=user.id,
                system_instructions=self.agent.system_instructions,
                tools=self.agent.available_tools,
            )
        else:
            await self.send(json.dumps({
                "type": "ERROR",
                "error": "No valid context for agent",
            }))
            return

        # Send start event
        await self.send(json.dumps({
            "type": "ASYNC_START",
            "agent_name": self.agent.name,
            "agent_id": str(self.agent.pk),
        }))

        # Stream response
        try:
            async for event in agent.stream(message):
                if hasattr(event, 'content') and event.content:
                    await self.send(json.dumps({
                        "type": "ASYNC_CONTENT",
                        "content": event.content,
                    }))

                if hasattr(event, 'tool_call'):
                    await self.send(json.dumps({
                        "type": "TOOL_CALL",
                        "tool": event.tool_call.name,
                        "args": event.tool_call.args,
                    }))

                if hasattr(event, 'approval_needed') and event.approval_needed:
                    await self.send(json.dumps({
                        "type": "APPROVAL_NEEDED",
                        "tool": event.tool_name,
                        "args": event.tool_args,
                    }))

            # Send completion
            await self.send(json.dumps({
                "type": "ASYNC_FINISH",
            }))

        except Exception as e:
            logger.exception(f"Agent response error: {e}")
            await self.send(json.dumps({
                "type": "ERROR",
                "error": str(e),
            }))

    async def _handle_approval(self, data):
        """Handle tool approval decisions."""
        # Implementation depends on agent framework approval handling
        pass

    async def _handle_cancel(self, data):
        """Handle cancellation requests."""
        # Implementation for cancelling ongoing generation
        pass
```

#### 1.2 Update WebSocket Routing

**File:** `config/asgi.py` (update)

```python
# Replace three separate routes with one unified route
from config.websocket.consumers.unified_agent_conversation import UnifiedAgentConsumer

websocket_urlpatterns = [
    # NEW: Unified agent consumer
    re_path(r"ws/agent-chat/$", UnifiedAgentConsumer.as_asgi()),

    # DEPRECATED: Keep old routes for backwards compatibility during transition
    # These can be removed after frontend migration
    re_path(r"ws/corpus-chat/(?P<corpus_id>\d+)/$", UnifiedAgentConsumer.as_asgi()),
    re_path(r"ws/document-chat/(?P<document_id>\d+)/$", UnifiedAgentConsumer.as_asgi()),

    # ... other routes (threads, etc.)
]
```

#### 1.3 Old Consumers Removed

> **Status**: COMPLETED. The legacy consumers have been deleted. All agent chat
> now uses `UnifiedAgentConsumer` at `ws/agent-chat/`.

---

### Phase 2: Frontend DRY - Shared useAgentChat() Hook

Extract ~80% shared logic from CorpusChat.tsx and ChatTray.tsx into a single hook.

#### 2.1 Create useAgentChat Hook

**File:** `frontend/src/hooks/useAgentChat.ts` (NEW)

```typescript
/**
 * Unified hook for agent chat WebSocket connections.
 *
 * Replaces duplicated logic in:
 * - CorpusChat.tsx (corpus-level chat)
 * - ChatTray.tsx (document-level chat)
 *
 * Both components now become thin UI wrappers around this hook.
 */
import { useState, useEffect, useRef, useCallback } from "react";

export interface AgentChatOptions {
  corpusId?: string;
  documentId?: string;
  conversationId?: string;
  agentId?: string;  // Optional - uses default if not specified
}

export interface AgentMessage {
  id: string;
  content: string;
  role: "user" | "assistant";
  timestamp: Date;
  agentName?: string;
  agentId?: string;
  sources?: AgentSource[];
  isStreaming?: boolean;
}

export interface AgentSource {
  annotationId: string;
  documentId: string;
  text: string;
  relevance: number;
}

export interface ApprovalRequest {
  tool: string;
  args: Record<string, unknown>;
}

export function useAgentChat(options: AgentChatOptions) {
  const { corpusId, documentId, conversationId, agentId } = options;

  // Connection state
  const wsRef = useRef<WebSocket | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [connectionError, setConnectionError] = useState<string | null>(null);

  // Message state
  const [messages, setMessages] = useState<AgentMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamingContent, setStreamingContent] = useState("");

  // Approval flow
  const [pendingApproval, setPendingApproval] = useState<ApprovalRequest | null>(null);

  // Sources/timeline
  const [sources, setSources] = useState<AgentSource[]>([]);

  // Build WebSocket URL
  const wsUrl = useCallback(() => {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const params = new URLSearchParams();
    if (corpusId) params.set("corpus_id", corpusId);
    if (documentId) params.set("document_id", documentId);
    if (conversationId) params.set("conversation_id", conversationId);
    if (agentId) params.set("agent_id", agentId);
    return `${protocol}//${window.location.host}/ws/agent-chat/?${params}`;
  }, [corpusId, documentId, conversationId, agentId]);

  // Connect to WebSocket
  useEffect(() => {
    // Need at least corpus or document context
    if (!corpusId && !documentId) return;

    const ws = new WebSocket(wsUrl());
    wsRef.current = ws;

    ws.onopen = () => {
      setIsConnected(true);
      setConnectionError(null);
    };

    ws.onclose = (event) => {
      setIsConnected(false);
      if (event.code !== 1000) {
        setConnectionError(`Connection closed: ${event.code}`);
      }
    };

    ws.onerror = () => {
      setConnectionError("WebSocket error");
    };

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      handleMessage(data);
    };

    return () => {
      ws.close();
    };
  }, [corpusId, documentId, conversationId, agentId, wsUrl]);

  // Handle incoming WebSocket messages
  const handleMessage = useCallback((data: any) => {
    switch (data.type) {
      case "ASYNC_START":
        setIsStreaming(true);
        setStreamingContent("");
        break;

      case "ASYNC_CONTENT":
        setStreamingContent(prev => prev + data.content);
        break;

      case "ASYNC_FINISH":
        setIsStreaming(false);
        // Add completed message
        setMessages(prev => [...prev, {
          id: Date.now().toString(),
          content: streamingContent,
          role: "assistant",
          timestamp: new Date(),
          agentName: data.agent_name,
        }]);
        setStreamingContent("");
        break;

      case "APPROVAL_NEEDED":
        setPendingApproval({
          tool: data.tool,
          args: data.args,
        });
        break;

      case "SOURCES":
        setSources(data.sources);
        break;

      case "ERROR":
        setIsStreaming(false);
        setConnectionError(data.error);
        break;
    }
  }, [streamingContent]);

  // Send user message
  const sendMessage = useCallback((content: string) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      setConnectionError("Not connected");
      return;
    }

    // Add user message to state
    setMessages(prev => [...prev, {
      id: Date.now().toString(),
      content,
      role: "user",
      timestamp: new Date(),
    }]);

    // Send to WebSocket
    wsRef.current.send(JSON.stringify({
      type: "chat_message",
      message: content,
    }));
  }, []);

  // Send approval decision
  const sendApprovalDecision = useCallback((approved: boolean) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;

    wsRef.current.send(JSON.stringify({
      type: "approval",
      approved,
    }));
    setPendingApproval(null);
  }, []);

  // Cancel current generation
  const cancelGeneration = useCallback(() => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;

    wsRef.current.send(JSON.stringify({
      type: "cancel",
    }));
    setIsStreaming(false);
  }, []);

  // Clear messages
  const clearMessages = useCallback(() => {
    setMessages([]);
    setSources([]);
  }, []);

  return {
    // Connection
    isConnected,
    connectionError,

    // Messages
    messages,
    isStreaming,
    streamingContent,

    // Approval
    pendingApproval,
    sendApprovalDecision,

    // Sources
    sources,

    // Actions
    sendMessage,
    cancelGeneration,
    clearMessages,
  };
}
```

#### 2.2 Refactor CorpusChat.tsx

**File:** `frontend/src/components/corpuses/CorpusChat.tsx`

Reduce from ~2000 lines to ~200 lines (UI only):

```typescript
/**
 * Corpus-level chat component.
 *
 * Uses useAgentChat hook for all WebSocket/message logic.
 * This component only handles corpus-specific UI.
 */
import { useAgentChat } from "../../hooks/useAgentChat";
import { ChatUI } from "../shared/ChatUI";

interface CorpusChatProps {
  corpusId: string;
}

export function CorpusChat({ corpusId }: CorpusChatProps) {
  const chat = useAgentChat({ corpusId });

  return (
    <ChatUI
      messages={chat.messages}
      isStreaming={chat.isStreaming}
      streamingContent={chat.streamingContent}
      sources={chat.sources}
      pendingApproval={chat.pendingApproval}
      isConnected={chat.isConnected}
      connectionError={chat.connectionError}
      onSendMessage={chat.sendMessage}
      onApprovalDecision={chat.sendApprovalDecision}
      onCancel={chat.cancelGeneration}
      onClear={chat.clearMessages}
      placeholder="Ask about this corpus..."
    />
  );
}
```

#### 2.3 Refactor ChatTray.tsx (Document Chat)

**File:** `frontend/src/components/knowledge_base/document/right_tray/ChatTray.tsx`

Similar refactor to CorpusChat:

```typescript
/**
 * Document-level chat component (in right tray).
 *
 * Uses useAgentChat hook for all WebSocket/message logic.
 * This component only handles document-specific UI.
 */
import { useAgentChat } from "../../../../hooks/useAgentChat";
import { ChatUI } from "../../../shared/ChatUI";

interface ChatTrayProps {
  documentId: string;
  corpusId?: string;  // Optional corpus context
}

export function ChatTray({ documentId, corpusId }: ChatTrayProps) {
  const chat = useAgentChat({ documentId, corpusId });

  return (
    <ChatUI
      messages={chat.messages}
      isStreaming={chat.isStreaming}
      streamingContent={chat.streamingContent}
      sources={chat.sources}
      pendingApproval={chat.pendingApproval}
      isConnected={chat.isConnected}
      connectionError={chat.connectionError}
      onSendMessage={chat.sendMessage}
      onApprovalDecision={chat.sendApprovalDecision}
      onCancel={chat.cancelGeneration}
      onClear={chat.clearMessages}
      placeholder="Ask about this document..."
    />
  );
}
```

#### 2.4 Create Shared ChatUI Component

**File:** `frontend/src/components/shared/ChatUI.tsx` (NEW)

Extract shared chat UI elements:

```typescript
/**
 * Shared chat UI component used by both CorpusChat and ChatTray.
 */
import React, { useState, useRef, useEffect } from "react";
import styled from "styled-components";
import { AgentMessage, AgentSource, ApprovalRequest } from "../../hooks/useAgentChat";
import { MessageComposer } from "../threads/MessageComposer";
import { ApprovalDialog } from "./ApprovalDialog";
import { SourcesPanel } from "./SourcesPanel";
import { StreamingMessage } from "./StreamingMessage";

interface ChatUIProps {
  messages: AgentMessage[];
  isStreaming: boolean;
  streamingContent: string;
  sources: AgentSource[];
  pendingApproval: ApprovalRequest | null;
  isConnected: boolean;
  connectionError: string | null;
  onSendMessage: (content: string) => void;
  onApprovalDecision: (approved: boolean) => void;
  onCancel: () => void;
  onClear: () => void;
  placeholder?: string;
}

export function ChatUI({
  messages,
  isStreaming,
  streamingContent,
  sources,
  pendingApproval,
  isConnected,
  connectionError,
  onSendMessage,
  onApprovalDecision,
  onCancel,
  onClear,
  placeholder,
}: ChatUIProps) {
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Auto-scroll on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingContent]);

  return (
    <Container>
      {connectionError && (
        <ErrorBanner>{connectionError}</ErrorBanner>
      )}

      <MessagesContainer>
        {messages.map(message => (
          <MessageBubble key={message.id} role={message.role}>
            {message.content}
          </MessageBubble>
        ))}

        {isStreaming && (
          <StreamingMessage content={streamingContent} onCancel={onCancel} />
        )}

        <div ref={messagesEndRef} />
      </MessagesContainer>

      {sources.length > 0 && (
        <SourcesPanel sources={sources} />
      )}

      {pendingApproval && (
        <ApprovalDialog
          tool={pendingApproval.tool}
          args={pendingApproval.args}
          onDecision={onApprovalDecision}
        />
      )}

      <MessageComposer
        onSend={onSendMessage}
        disabled={!isConnected || isStreaming}
        placeholder={placeholder}
      />
    </Container>
  );
}

// Styled components...
const Container = styled.div`/* ... */`;
const MessagesContainer = styled.div`/* ... */`;
const MessageBubble = styled.div<{ role: string }>`/* ... */`;
const ErrorBanner = styled.div`/* ... */`;
```

---

### Phase 3: Agent Mention Support

Now that DRY refactoring is complete, adding agent mentions is straightforward.

#### 3.1 Add Slug Field to AgentConfiguration

**File:** `opencontractserver/agents/models.py`

```python
class AgentConfiguration(BaseOCModel):
    # Existing fields...

    slug = models.CharField(
        max_length=128,
        db_index=True,
        null=True,
        blank=True,
        help_text="URL-friendly identifier for mentions (e.g., 'research-assistant')"
    )

    class Meta:
        constraints = [
            # Existing constraints...
            models.UniqueConstraint(
                fields=["corpus", "slug"],
                name="unique_agent_slug_per_corpus",
                condition=Q(scope="CORPUS"),
            ),
            models.UniqueConstraint(
                fields=["slug"],
                name="unique_global_agent_slug",
                condition=Q(scope="GLOBAL"),
            ),
        ]
```

**Migration:** Create migration to add slug field with auto-generation from name.

#### 3.2 Extend Mention Parser for Agents

**File:** `opencontractserver/utils/mention_parser.py`

Add agent URL pattern parsing:

```python
def parse_mentions_from_content(markdown_content: str) -> dict[str, set[str]]:
    mentioned = {
        "users": set(),
        "documents": set(),
        "annotations": set(),
        "corpuses": set(),
        "agents": set(),  # NEW
    }

    # ... existing parsing ...

    # Agent: /agents/{agentSlug} or /c/{corpusIdent}/agents/{agentSlug}
    if path.startswith("/agents/"):
        parts = path.split("/")
        if len(parts) >= 3:
            agent_slug = parts[2]
            mentioned["agents"].add(agent_slug)
            logger.debug(f"Found agent mention: {agent_slug}")
```

#### 3.3 Add Mentioned Agents to ChatMessage

**File:** `opencontractserver/conversations/models.py`

Add M2M field for mentioned agents:

```python
class ChatMessage(BaseOCModel, HasEmbeddingMixin):
    # Existing fields...

    mentioned_agents = models.ManyToManyField(
        "agents.AgentConfiguration",
        related_name="mentioned_in_messages",
        blank=True,
        help_text="Agents mentioned in this message that should respond",
    )
```

**Migration:** Create migration for the new M2M field.

#### 3.4 Update link_message_to_resources

**File:** `opencontractserver/utils/mention_parser.py`

```python
@transaction.atomic
def link_message_to_resources(
    chat_message, mentioned_ids: dict[str, set[str]]
) -> dict[str, int]:
    # ... existing logic ...

    result = {
        "documents_linked": 0,
        "annotations_linked": 0,
        "users_mentioned": len(mentioned_ids.get("users", set())),
        "corpuses_mentioned": len(mentioned_ids.get("corpuses", set())),
        "agents_linked": 0,  # NEW
    }

    # Link agents (ManyToMany)
    if mentioned_ids.get("agents"):
        from opencontractserver.agents.models import AgentConfiguration

        # Get conversation's corpus for scoped agent lookup
        corpus = chat_message.conversation.chat_with_corpus

        # Find agents by slug - global OR matching corpus
        agent_slugs = list(mentioned_ids["agents"])
        if corpus:
            agents_qs = AgentConfiguration.objects.filter(
                Q(slug__in=agent_slugs, scope="GLOBAL", is_active=True) |
                Q(slug__in=agent_slugs, scope="CORPUS", corpus=corpus, is_active=True)
            )
        else:
            agents_qs = AgentConfiguration.objects.filter(
                slug__in=agent_slugs, scope="GLOBAL", is_active=True
            )

        chat_message.mentioned_agents.set(agents_qs)
        result["agents_linked"] = agents_qs.count()

    return result
```

---

### Phase 4: Backend - Agent Mention Autocomplete

#### 4.1 Add GraphQL Query for Agent Search

**File:** `config/graphql/queries.py`

```python
# Add to Query class
search_agents_for_mention = DjangoConnectionField(
    AgentConfigurationType,
    text_search=graphene.String(
        description="Search query to find agents by name or description"
    ),
    corpus_id=graphene.ID(
        description="Corpus ID to scope agent search (includes global + corpus agents)"
    ),
)

@graphql_ratelimit_dynamic(get_rate=get_user_tier_rate("READ_LIGHT"))
def resolve_search_agents_for_mention(
    self, info, text_search=None, corpus_id=None, **kwargs
):
    """
    Search agents for @ mention autocomplete.

    Returns:
    - All active global agents
    - Corpus-specific agents for the provided corpus (if user has access)

    SECURITY: Filters by visibility - users only see agents they can mention.
    """
    from opencontractserver.agents.models import AgentConfiguration

    user = info.context.user

    # Anonymous users cannot mention
    if user.is_anonymous:
        return AgentConfiguration.objects.none()

    # Build base queryset using visible_to_user
    qs = AgentConfiguration.objects.visible_to_user(user).filter(is_active=True)

    # If corpus_id provided, further filter to global + that corpus
    if corpus_id:
        _, corpus_pk = from_global_id(corpus_id)
        qs = qs.filter(
            Q(scope="GLOBAL") | Q(scope="CORPUS", corpus_id=corpus_pk)
        )

    # Apply text search
    if text_search:
        qs = qs.filter(
            Q(name__icontains=text_search) |
            Q(description__icontains=text_search) |
            Q(slug__icontains=text_search)
        )

    return qs.order_by("scope", "name")  # Global first, then corpus, alphabetical
```

#### 4.2 Update AgentConfigurationType for Mention Display

**File:** `config/graphql/graphene_types.py`

Ensure `slug` field is exposed and add mention format helper:

```python
class AgentConfigurationType(AnnotatePermissionsForReadMixin, DjangoObjectType):
    # Existing fields...

    mention_format = graphene.String(
        description="The @ mention format for this agent"
    )

    def resolve_mention_format(self, info):
        return f"@agent:{self.slug}"
```

---

### Phase 5: Backend - Agent Response Generation

#### 5.1 Create Agent Response Task

**File:** `opencontractserver/tasks/agent_tasks.py` (NEW)

```python
"""
Celery tasks for agent response generation in threads.
"""
import logging
from celery import shared_task
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

from opencontractserver.agents.models import AgentConfiguration
from opencontractserver.conversations.models import ChatMessage, Conversation

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def generate_agent_response(
    self,
    message_id: int,
    agent_config_id: int,
    user_id: int,
):
    """
    Generate an agent response to a message that mentioned the agent.

    This task:
    1. Creates a placeholder LLM message in 'in_progress' state
    2. Loads the agent configuration and builds the agent
    3. Gathers thread context (previous messages)
    4. Generates response using the agent
    5. Updates the message with final content
    6. Broadcasts updates via WebSocket
    """
    from django.contrib.auth import get_user_model
    from opencontractserver.llms import agents as agent_factory

    User = get_user_model()

    try:
        user = User.objects.get(pk=user_id)
        source_message = ChatMessage.objects.get(pk=message_id)
        agent_config = AgentConfiguration.objects.get(pk=agent_config_id)
        conversation = source_message.conversation
        corpus = conversation.chat_with_corpus

        if not corpus:
            logger.error(f"Cannot generate agent response: no corpus for conversation {conversation.pk}")
            return

        # Create placeholder message
        llm_message = ChatMessage.objects.create(
            conversation=conversation,
            msg_type="LLM",
            content="",
            state="in_progress",
            agent_configuration=agent_config,
            parent_message=source_message,  # Thread as reply
            creator=user,
        )

        # Broadcast start event
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f"thread_{conversation.pk}",
            {
                "type": "agent.response.start",
                "message_id": llm_message.pk,
                "agent_id": agent_config.pk,
                "agent_name": agent_config.name,
            }
        )

        # Build agent with custom system instructions
        agent = agent_factory.for_corpus_sync(
            corpus=corpus.pk,
            user_id=user_id,
            system_instructions=agent_config.system_instructions,
            tools=agent_config.available_tools,
        )

        # Build prompt with thread context
        thread_context = _build_thread_context(conversation, source_message)
        prompt = f"{thread_context}\n\nUser: {source_message.content}"

        # Generate response (streaming to WebSocket)
        full_response = ""
        sources = []

        for event in agent.stream_sync(prompt):
            if hasattr(event, 'content') and event.content:
                full_response += event.content
                # Broadcast content chunk
                async_to_sync(channel_layer.group_send)(
                    f"thread_{conversation.pk}",
                    {
                        "type": "agent.response.chunk",
                        "message_id": llm_message.pk,
                        "content": event.content,
                    }
                )

            if hasattr(event, 'sources') and event.sources:
                sources.extend(event.sources)

        # Update message with final content
        llm_message.content = full_response
        llm_message.state = "completed"
        llm_message.data = {
            "sources": [s.to_dict() for s in sources],
        }
        llm_message.save()

        # Link source annotations
        if sources:
            from opencontractserver.annotations.models import Annotation
            annotation_ids = [s.annotation_id for s in sources if s.annotation_id]
            llm_message.source_annotations.set(
                Annotation.objects.filter(pk__in=annotation_ids)
            )

        # Broadcast completion
        async_to_sync(channel_layer.group_send)(
            f"thread_{conversation.pk}",
            {
                "type": "agent.response.complete",
                "message_id": llm_message.pk,
                "content": full_response,
                "sources": [s.to_dict() for s in sources],
            }
        )

    except Exception as e:
        logger.exception(f"Agent response generation failed: {e}")
        # Update message to error state if it was created
        if 'llm_message' in locals():
            llm_message.state = "error"
            llm_message.data = {"error": str(e)}
            llm_message.save()

            # Broadcast error
            async_to_sync(channel_layer.group_send)(
                f"thread_{conversation.pk}",
                {
                    "type": "agent.response.error",
                    "message_id": llm_message.pk,
                    "error": str(e),
                }
            )
        raise


def _build_thread_context(conversation: Conversation, up_to_message: ChatMessage) -> str:
    """Build conversation context from thread messages."""
    messages = ChatMessage.objects.filter(
        conversation=conversation,
        deleted_at__isnull=True,
    ).exclude(pk=up_to_message.pk).order_by("created_at")[:20]  # Limit context

    context_parts = []
    for msg in messages:
        role = "Assistant" if msg.msg_type == "LLM" else "User"
        context_parts.append(f"{role}: {msg.content}")

    return "\n".join(context_parts)
```

#### 5.2 Update Thread Message Mutations to Trigger Agent Responses

**File:** `config/graphql/conversation_mutations.py`

Add agent response triggering after message creation:

```python
# In CreateThreadMessageMutation.mutate()

# After mention parsing:
if result.get("agents_linked", 0) > 0:
    from opencontractserver.tasks.agent_tasks import generate_agent_response

    # Trigger response for each mentioned agent
    for agent in chat_message.mentioned_agents.all():
        generate_agent_response.delay(
            message_id=chat_message.pk,
            agent_config_id=agent.pk,
            user_id=user.id,
        )
```

#### 5.3 Create Thread WebSocket Consumer

**File:** `config/websocket/consumers/thread_conversation.py` (NEW)

```python
"""
WebSocket consumer for thread conversations with agent responses.
"""
import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer

logger = logging.getLogger(__name__)


class ThreadConversationConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for real-time updates in thread conversations.

    Handles:
    - New messages in thread
    - Agent response streaming
    - Typing indicators
    """

    async def connect(self):
        self.conversation_id = self.scope["url_route"]["kwargs"]["conversation_id"]
        self.room_group_name = f"thread_{self.conversation_id}"

        # Verify user has access to conversation
        if not await self._user_can_access_conversation():
            await self.close(code=4003)
            return

        # Join room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    async def receive(self, text_data):
        """Handle incoming messages (e.g., typing indicators)."""
        data = json.loads(text_data)
        msg_type = data.get("type")

        if msg_type == "typing":
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "user.typing",
                    "user_id": self.scope["user"].id,
                    "username": self.scope["user"].username,
                }
            )

    # Event handlers for agent responses

    async def agent_response_start(self, event):
        await self.send(json.dumps({
            "type": "AGENT_RESPONSE_START",
            "message_id": event["message_id"],
            "agent_id": event["agent_id"],
            "agent_name": event["agent_name"],
        }))

    async def agent_response_chunk(self, event):
        await self.send(json.dumps({
            "type": "AGENT_RESPONSE_CHUNK",
            "message_id": event["message_id"],
            "content": event["content"],
        }))

    async def agent_response_complete(self, event):
        await self.send(json.dumps({
            "type": "AGENT_RESPONSE_COMPLETE",
            "message_id": event["message_id"],
            "content": event["content"],
            "sources": event.get("sources", []),
        }))

    async def agent_response_error(self, event):
        await self.send(json.dumps({
            "type": "AGENT_RESPONSE_ERROR",
            "message_id": event["message_id"],
            "error": event["error"],
        }))

    async def user_typing(self, event):
        await self.send(json.dumps({
            "type": "USER_TYPING",
            "user_id": event["user_id"],
            "username": event["username"],
        }))

    async def _user_can_access_conversation(self) -> bool:
        """Check if user has access to the conversation."""
        from opencontractserver.conversations.models import Conversation
        from asgiref.sync import sync_to_async

        user = self.scope.get("user")
        if not user or not user.is_authenticated:
            return False

        try:
            conversation = await sync_to_async(
                Conversation.objects.visible_to_user(user).get
            )(pk=self.conversation_id)
            return True
        except Conversation.DoesNotExist:
            return False
```

#### 5.4 Add WebSocket Routing

**File:** `config/asgi.py` (update)

```python
# Add to websocket_urlpatterns
from config.websocket.consumers.thread_conversation import ThreadConversationConsumer

websocket_urlpatterns = [
    # Existing routes...
    re_path(
        r"ws/threads/(?P<conversation_id>\d+)/$",
        ThreadConversationConsumer.as_asgi()
    ),
]
```

---

### Phase 6: Frontend - Agent Mention Picker

#### 6.1 Create AgentMentionPicker Component

**File:** `frontend/src/components/threads/AgentMentionPicker.tsx` (NEW)

```tsx
import React, { forwardRef, useEffect, useImperativeHandle, useState } from "react";
import styled from "styled-components";
import { Bot } from "lucide-react";
import { color } from "../../theme/colors";
import { spacing } from "../../theme/spacing";

// ... styled components similar to ResourceMentionPicker ...

export interface MentionAgent {
  id: string;
  slug: string;
  name: string;
  description: string;
  scope: "GLOBAL" | "CORPUS";
  badgeConfig: {
    icon?: string;
    color?: string;
    label?: string;
  };
}

export interface AgentMentionPickerProps {
  agents: MentionAgent[];
  onSelect: (agent: MentionAgent) => void;
  selectedIndex: number;
}

export const AgentMentionPicker = forwardRef<
  AgentMentionPickerRef,
  AgentMentionPickerProps
>(({ agents, onSelect, selectedIndex }, ref) => {
  // Implementation similar to ResourceMentionPicker
  // with agent-specific display (icon from badgeConfig, scope indicator)
});
```

#### 6.2 Create GraphQL Query for Agent Search

**File:** `frontend/src/graphql/queries.ts` (add)

```graphql
export const SEARCH_AGENTS_FOR_MENTION = gql`
  query SearchAgentsForMention($textSearch: String, $corpusId: ID) {
    searchAgentsForMention(textSearch: $textSearch, corpusId: $corpusId) {
      edges {
        node {
          id
          slug
          name
          description
          scope
          badgeConfig
          avatarUrl
          corpus {
            id
            title
          }
        }
      }
    }
  }
`;
```

#### 6.3 Create useAgentMentionSearch Hook

**File:** `frontend/src/hooks/useAgentMentionSearch.ts` (NEW)

```tsx
import { useQuery } from "@apollo/client";
import { useMemo } from "react";
import { SEARCH_AGENTS_FOR_MENTION } from "../graphql/queries";

export function useAgentMentionSearch(
  searchText: string,
  corpusId: string | null
) {
  const { data, loading, error } = useQuery(SEARCH_AGENTS_FOR_MENTION, {
    variables: { textSearch: searchText, corpusId },
    skip: searchText.length < 1,
    fetchPolicy: "cache-and-network",
  });

  const agents = useMemo(() => {
    if (!data?.searchAgentsForMention?.edges) return [];
    return data.searchAgentsForMention.edges.map((edge: any) => edge.node);
  }, [data]);

  return { agents, loading, error };
}
```

#### 6.4 Update UnifiedMentionPicker to Include Agents

**File:** `frontend/src/components/threads/MessageComposer.tsx` (update)

Extend the unified mention picker to support `@agent:` trigger:

```tsx
// In the mention extension configuration
const mentionSuggestion = {
  char: "@",
  items: async ({ query }: { query: string }) => {
    // Detect mention type from query
    if (query.startsWith("agent:")) {
      const searchText = query.slice(6); // Remove "agent:" prefix
      const agents = await fetchAgentsForMention(searchText, corpusId);
      return agents.map(a => ({ ...a, mentionType: "agent" }));
    }

    if (query.startsWith("corpus:") || query.startsWith("document:")) {
      // Existing resource mention logic
      return fetchResourcesForMention(query);
    }

    // Default: user mentions
    return fetchUsersForMention(query);
  },

  render: () => ({
    // Render appropriate picker based on mentionType
  }),
};
```

#### 6.5 Add Agent Mention Chip Rendering

**File:** `frontend/src/components/threads/MentionChip.tsx` (update)

Add agent mention rendering:

```tsx
export function MentionChip({ mention }: { mention: ParsedMention }) {
  if (mention.type === "agent") {
    return (
      <AgentChip
        href={`/agents/${mention.slug}`}
        color={mention.badgeConfig?.color || "#8B5CF6"}
      >
        <Bot size={12} />
        <span>{mention.name}</span>
      </AgentChip>
    );
  }
  // ... existing corpus/document chip rendering
}
```

---

### Phase 7: Frontend - Real-time Agent Responses

#### 7.1 Create Thread WebSocket Hook

**File:** `frontend/src/hooks/useThreadWebSocket.ts` (NEW — removed in PR #1245 as dead code; was never wired into thread components. See Issues #623, #697 for future real-time streaming work.)

```tsx
import { useEffect, useRef, useCallback, useState } from "react";
import { useAtomValue } from "jotai";
import { currentThreadIdAtom } from "../atoms/threadAtoms";

interface AgentResponseState {
  messageId: number;
  agentId: number;
  agentName: string;
  content: string;
  isComplete: boolean;
  error?: string;
}

export function useThreadWebSocket() {
  const threadId = useAtomValue(currentThreadIdAtom);
  const wsRef = useRef<WebSocket | null>(null);
  const [agentResponses, setAgentResponses] = useState<Map<number, AgentResponseState>>(new Map());

  useEffect(() => {
    if (!threadId) return;

    const wsUrl = `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/ws/threads/${threadId}/`;
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);

      switch (data.type) {
        case "AGENT_RESPONSE_START":
          setAgentResponses(prev => new Map(prev).set(data.message_id, {
            messageId: data.message_id,
            agentId: data.agent_id,
            agentName: data.agent_name,
            content: "",
            isComplete: false,
          }));
          break;

        case "AGENT_RESPONSE_CHUNK":
          setAgentResponses(prev => {
            const updated = new Map(prev);
            const existing = updated.get(data.message_id);
            if (existing) {
              updated.set(data.message_id, {
                ...existing,
                content: existing.content + data.content,
              });
            }
            return updated;
          });
          break;

        case "AGENT_RESPONSE_COMPLETE":
          setAgentResponses(prev => {
            const updated = new Map(prev);
            const existing = updated.get(data.message_id);
            if (existing) {
              updated.set(data.message_id, {
                ...existing,
                content: data.content,
                isComplete: true,
              });
            }
            return updated;
          });
          break;

        case "AGENT_RESPONSE_ERROR":
          setAgentResponses(prev => {
            const updated = new Map(prev);
            const existing = updated.get(data.message_id);
            if (existing) {
              updated.set(data.message_id, {
                ...existing,
                isComplete: true,
                error: data.error,
              });
            }
            return updated;
          });
          break;
      }
    };

    return () => {
      ws.close();
    };
  }, [threadId]);

  return { agentResponses };
}
```

#### 7.2 Update ThreadDetail to Show Streaming Responses

**File:** `frontend/src/components/threads/ThreadDetail.tsx` (update)

Integrate the WebSocket hook to display streaming agent responses:

```tsx
function ThreadDetail() {
  const { agentResponses } = useThreadWebSocket();

  // ... existing logic ...

  return (
    <div>
      {messages.map(message => (
        <MessageItem key={message.id} message={message} />
      ))}

      {/* Show streaming agent responses */}
      {Array.from(agentResponses.values())
        .filter(r => !r.isComplete)
        .map(response => (
          <StreamingAgentMessage
            key={response.messageId}
            agentName={response.agentName}
            content={response.content}
          />
        ))}
    </div>
  );
}
```

---

### Phase 8: Testing

#### 8.1 Backend Tests

**File:** `opencontractserver/tests/test_agent_mentions.py` (NEW)

```python
"""
Tests for agent mention parsing, autocomplete, and response generation.
"""

class AgentMentionParsingTests(TestCase):
    """Test agent mention parsing from markdown content."""

    def test_parse_agent_mention_from_markdown(self):
        """Test parsing @agent: mentions from markdown links."""
        pass

    def test_agent_mention_linked_to_message(self):
        """Test that mentioned agents are linked to ChatMessage."""
        pass


class AgentMentionAutocompleteTests(TestCase):
    """Test GraphQL agent search for mentions."""

    def test_search_returns_global_agents(self):
        """Global agents visible to all authenticated users."""
        pass

    def test_search_returns_corpus_agents_for_accessible_corpus(self):
        """Corpus agents only visible if user has corpus access."""
        pass

    def test_search_filters_inactive_agents(self):
        """Inactive agents not returned in search."""
        pass


class AgentResponseGenerationTests(TransactionTestCase):
    """Test agent response generation task."""

    def test_agent_response_created_for_mention(self):
        """Test that mentioning an agent triggers response generation."""
        pass

    def test_multiple_agents_respond_in_sequence(self):
        """Test that multiple mentioned agents each generate responses."""
        pass
```

#### 8.2 Frontend Tests

**File:** `frontend/tests/AgentMentionPicker.spec.tsx` (NEW)

```typescript
test.describe("AgentMentionPicker", () => {
  test("displays global and corpus agents", async () => {
    // ...
  });

  test("filters agents by search text", async () => {
    // ...
  });

  test("keyboard navigation works", async () => {
    // ...
  });

  test("selecting agent inserts mention link", async () => {
    // ...
  });
});
```

---

## Database Migrations Summary

1. **Migration 1:** Add `slug` field to `AgentConfiguration` (Phase 0)
2. **Migration 2:** Create default global agents via data migration (Phase 0)
3. **Migration 3:** Add `mentioned_agents` M2M field to `ChatMessage` (Phase 3)

---

## Security Considerations

1. **Agent Visibility** - Only show agents user has access to (via `visible_to_user()`)
2. **IDOR Prevention** - Use consistent error messages for agent lookups
3. **Rate Limiting** - Apply rate limits to agent response generation
4. **Tool Permissions** - Respect `permission_required_tools` for agent actions
5. **Context Isolation** - Agents only have access to thread/corpus they're mentioned in

---

## Performance Considerations

1. **Async Response Generation** - Use Celery tasks for non-blocking agent execution
2. **WebSocket Streaming** - Real-time updates without polling
3. **Query Optimization** - Prefetch agent data for mention display
4. **Context Limiting** - Limit thread context sent to agents (e.g., last 20 messages)

---

## Future Enhancements

1. **Agent Response Approval** - Require approval before agent responds
2. **Agent Collaboration** - Agents can mention other agents
3. **Agent Memory** - Persist agent memory across conversations
4. **Custom Agent Tools** - Per-corpus tool configurations
5. **Agent Analytics** - Track agent usage and response quality

---

## File Changes Summary

### New Files

| File | Description | Phase |
|------|-------------|-------|
| `config/websocket/consumers/unified_agent_conversation.py` | Unified agent WebSocket consumer | 1 |
| `frontend/src/hooks/useAgentChat.ts` | Shared hook for agent chat | 2 |
| `frontend/src/components/shared/ChatUI.tsx` | Shared chat UI component | 2 |
| `opencontractserver/tasks/agent_tasks.py` | Celery tasks for agent response generation | 5 |
| `config/websocket/consumers/thread_conversation.py` | WebSocket consumer for thread updates | 5 |
| `frontend/src/components/threads/AgentMentionPicker.tsx` | Agent autocomplete component | 6 |
| `frontend/src/hooks/useAgentMentionSearch.ts` | Hook for agent search queries | 6 |
| `frontend/src/hooks/useThreadWebSocket.ts` | Hook for thread WebSocket connection (removed in PR #1245) | 7 |
| `opencontractserver/tests/test_agent_mentions.py` | Backend tests | 8 |
| `frontend/tests/AgentMentionPicker.spec.tsx` | Frontend tests | 8 |

### Modified Files

| File | Changes | Phase |
|------|---------|-------|
| `opencontractserver/agents/models.py` | Add `slug` field | 0 |
| `opencontractserver/agents/migrations/` | Add default global agents | 0 |
| `config/asgi.py` | Add unified agent route, thread route | 1, 5 |
| `frontend/src/components/corpuses/CorpusChat.tsx` | Refactor to use `useAgentChat` | 2 |
| `frontend/src/components/knowledge_base/document/right_tray/ChatTray.tsx` | Refactor to use `useAgentChat` | 2 |
| `opencontractserver/conversations/models.py` | Add `mentioned_agents` M2M | 3 |
| `opencontractserver/utils/mention_parser.py` | Parse `@agent:` mentions | 3 |
| `config/graphql/queries.py` | Add `search_agents_for_mention` resolver | 4 |
| `config/graphql/graphene_types.py` | Add `mention_format` field | 4 |
| `config/graphql/conversation_mutations.py` | Trigger agent responses | 5 |
| `frontend/src/components/threads/MessageComposer.tsx` | Integrate agent mentions | 6 |
| `frontend/src/components/threads/MentionChip.tsx` | Render agent chips | 6 |
| `frontend/src/components/threads/ThreadDetail.tsx` | Show streaming responses | 7 |

---

## Implementation Order

> **DRY-First Approach:** Complete phases 0-2 before adding new features (phases 3-7)

### Stage 1: DRY Refactoring (Do First!)

1. **Phase 0** - Default global agents & slug field (data migration)
2. **Phase 1** - Unified backend WebSocket consumer (replaces 3 consumers)
3. **Phase 2** - Shared frontend `useAgentChat` hook (reduces ~4000 lines to ~400)

### Stage 2: Agent Mention Feature

4. **Phase 3** - Backend mention parsing (parser + M2M field)
5. **Phase 4** - Backend autocomplete (GraphQL query)
6. **Phase 5** - Backend response generation (Celery tasks + thread consumer)
7. **Phase 6** - Frontend mention picker (can parallel with Phase 5)
8. **Phase 7** - Frontend real-time responses
9. **Phase 8** - Testing (throughout development)

---

## Acceptance Criteria

### Stage 1: DRY Refactoring

- [ ] Default global agents (`default-corpus-agent`, `default-document-agent`) exist in database
- [ ] Unified WebSocket consumer handles corpus, document, and explicit agent contexts
- [ ] Existing corpus chat works with unified consumer + default corpus agent
- [ ] Existing document chat works with unified consumer + default document agent
- [ ] `useAgentChat` hook replaces duplicated WebSocket logic in frontend
- [ ] CorpusChat.tsx and ChatTray.tsx reduced to ~200 lines each (UI only)
- [ ] All existing chat functionality preserved (streaming, sources, approval flow)

### Stage 2: Agent Mentions

- [ ] User can type `@agent:` in thread composer and see autocomplete
- [ ] Autocomplete shows global agents + corpus-specific agents
- [ ] Selecting agent inserts markdown link in correct format
- [ ] Submitting message with agent mention triggers agent response
- [ ] Agent response appears in thread with streaming updates
- [ ] Agent badge/avatar displayed on response message
- [ ] Multiple agents can be mentioned and each responds
- [ ] Only active, accessible agents appear in autocomplete
- [ ] Agent responses link to relevant source annotations
- [ ] Error states handled gracefully (agent failure, timeout)
