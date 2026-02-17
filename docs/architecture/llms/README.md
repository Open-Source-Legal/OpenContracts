# OpenContracts LLM Framework

Last Updated: 2026-01-09

OpenContract's API for creating document and corpus agents.

## Philosophy

- **Extensible Framework Design**: Built on PydanticAI with a pluggable architecture for future framework adapters
- **Rich Responses**: Every interaction returns structured data with sources, metadata, and conversation tracking
- **Conversation Management**: Persistent conversations with automatic message storage and retrieval
- **Tool Integration**: Extensible tool system for document analysis and data retrieval
- **Type Safety**: Full type hints and structured responses throughout
- **Optimized Extraction**: Leverages pydantic_ai's native capabilities for reliable structured data extraction

## Quick Start

```python
from opencontractserver.llms import agents
# Assuming you have a document_id and corpus_id or objects
# from opencontractserver.corpuses.models import Corpus
# from opencontractserver.documents.models import Document
# document_obj = Document.objects.get(id=123)
# corpus_obj = Corpus.objects.get(id=1)

# Create a document agent
# Note: The `corpus` parameter is optional - use None for documents not in a corpus
agent = await agents.for_document(document=123, corpus=1) # Replace 1 with your actual corpus_id or object, or use None

# Chat with rich responses
response = await agent.chat("What are the key terms in this contract?")
print(f"Response: {response.content}")
print(f"Sources: {len(response.sources)} found")
print(f"Message ID: {response.llm_message_id}")

# Stream responses
async for chunk in agent.stream("Summarize the main obligations"):
    print(chunk.content, end="")

# NEW: Structured data extraction (one-shot, no conversation persistence)
from pydantic import BaseModel, Field

class ContractDates(BaseModel):
    effective_date: str = Field(description="Contract effective date")
    expiration_date: str = Field(description="Contract expiration date")

dates = await agent.structured_response(
    "Extract the contract dates",
    ContractDates
)
if dates:
    print(f"Effective: {dates.effective_date}")
    print(f"Expires: {dates.expiration_date}")

# NEW: Document agents now work without corpus!
# Perfect for analyzing standalone documents or one-off extractions
standalone_agent = await agents.for_document(document=456, corpus=None)
simple_result = await standalone_agent.structured_response(
    "What type of document is this?", 
    str
)
print(f"Document type: {simple_result}")
```

## Core Concepts

### High-Level APIs

The `opencontractserver.llms` module provides several high-level API entry points:

- **`agents`**: (`AgentAPI`) For creating and interacting with document and corpus agents. This is the most common entry point. Also provides convenience methods for structured data extraction.
- **`embeddings`**: (`EmbeddingAPI`) For generating text embeddings.
- **`vector_stores`**: (`VectorStoreAPI`) For creating and interacting with vector stores for similarity search.
- **`tools`**: (`ToolAPI`) For creating and managing `CoreTool` instances.

```python
from opencontractserver.llms import agents, embeddings, vector_stores, tools
from opencontractserver.llms.tools.tool_factory import CoreTool

# Example: Creating a tool using the ToolAPI
def my_custom_function(text: str) -> str:
    """A simple custom tool."""
    return f"Processed: {text}"

custom_tool = tools.create_from_function(
    func=my_custom_function,
    name="MyCustomTool",
    description="A demonstration tool."
)
# This custom_tool can then be passed to an agent.

# Example: Using AgentAPI convenience methods for structured extraction
result = await agents.get_structured_response_from_document(
    document=123,
    corpus=1,  # Or None for standalone documents
    prompt="Extract key contract terms",
    target_type=ContractTerms,
    framework=AgentFramework.PYDANTIC_AI,
    user_id=456  # Optional
)

# Or extract from an entire corpus
insights = await agents.get_structured_response_from_corpus(
    corpus=1,
    prompt="Analyze patterns across all contracts",
    target_type=CorpusInsights,
    framework=AgentFramework.PYDANTIC_AI
)
```

### Agents

Agents are the primary interface for interacting with documents and corpora. They provide:

- **Document Agents**: Work with individual documents (corpus optional; pass None for standalone documents).
- **Corpus Agents**: Work with collections of documents.
- **Framework Flexibility**: Built on PydanticAI with extensible architecture for custom framework adapters.
- **Conversation Persistence**: Automatic conversation management and message storage.
- **Structured Data Extraction**: One-shot typed data extraction without conversation persistence.
- **Nested Streaming**: Real-time visibility into child agent execution through stream observers.

#### Creating Agents

```python
from opencontractserver.llms import agents
from opencontractserver.llms.types import AgentFramework
# from opencontractserver.corpuses.models import Corpus # For corpus_obj
# from opencontractserver.documents.models import Document # For document_obj
# corpus_obj = Corpus.objects.get(id=1) # Example corpus
# document_obj = Document.objects.get(id=123) # Example document

# Document agent with default framework (PydanticAI)
# The `corpus` parameter is optional - can be None for standalone documents
agent = await agents.for_document(document=123, corpus=1) # Use actual document/corpus IDs or objects

# Document agent for standalone document (not in any corpus)
standalone_agent = await agents.for_document(document=123, corpus=None)
# Corpus-dependent tools are automatically filtered out - agent still works!

# Corpus agent with specific framework
agent = await agents.for_corpus(
    corpus=456, # Use actual corpus ID or object
    framework=AgentFramework.PYDANTIC_AI
)

# With custom configuration
# The `corpus` parameter is optional for document agents (use None for standalone).
agent = await agents.for_document(
    document=123, # Use actual document ID or object
    corpus=1,     # Use actual corpus ID or object
    user_id=789,
    system_prompt="You are a legal contract analyzer...",  # Note: Completely overrides default prompt
    model="gpt-4",
    temperature=0.1,
    tools=["load_md_summary", "get_notes_for_document_corpus"]
)

# Advanced: With stream observer for nested agent visibility
async def my_stream_observer(event):
    """Receives events from nested agent calls."""
    print(f"[Nested] {event.type}: {getattr(event, 'content', getattr(event, 'thought', ''))}")

agent = await agents.for_corpus(
    corpus=456,
    framework=AgentFramework.PYDANTIC_AI,
    stream_observer=my_stream_observer  # Will receive events from child document agents
)

# Advanced: Using existing conversation or preloaded messages
# from opencontractserver.conversations.models import Conversation, ChatMessage
# existing_conversation = Conversation.objects.aget(id=your_conversation_id)
# preloaded_messages = await ChatMessage.objects.filter(conversation_id=your_conversation_id).order_by('''created_at''')
# agent = await agents.for_document(
#     document=123,
#     corpus=1,
#     user_id=789,
#     conversation=existing_conversation, # Optionally pass an existing Conversation object
#     # loaded_messages=list(preloaded_messages), # Optionally pass preloaded messages
#     # override_conversation=True # Set to True to use only loaded_messages and ignore others from conversation object
# )

```

#### Agent Responses

All agent interactions return rich, structured responses with complete metadata:

```python
# UnifiedChatResponse structure
response = await agent.chat("What are the payment terms?")

response.content              # The LLM's response text
response.sources              # List of SourceNode objects with citations
response.user_message_id      # ID of stored user message (if persistence enabled)
response.llm_message_id       # ID of stored LLM response (if persistence enabled)  
response.metadata             # Additional response metadata (framework-specific)

# New, event-based streaming (>= v0.9)
# -----------------------------------
#
# The streaming API now yields a *typed* event union instead of a single
# response shape.  Each event has a ``type`` discriminator so it's trivial to
# branch logic without ``isinstance`` checks.
#
#     ThoughtEvent  – short messages about the agent's reasoning (e.g. tool call
#                     decisions, framework-specific "thinking" lines).
#     ContentEvent  – textual delta that forms part of the **final** answer.
#     SourceEvent   – a batch of SourceNode objects discovered mid-stream.
#     ApprovalNeededEvent – tool requires human approval before execution.
#     ApprovalResultEvent – approval decision has been recorded.
#     ResumeEvent   – execution is resuming after approval.
#     FinalEvent    – emitted once; contains the full answer, sources, usage…
#
# All events carry the legacy fields (``user_message_id``, ``llm_message_id``,
# ``content``/``is_complete``) so existing websocket code keeps working.
#
# Example:
# ```python
# async for ev in agent.stream("Analyze the liability clauses"):
#     if ev.type == "thought":
#         print(f"🤔 {ev.thought}")
#     elif ev.type == "content":
#         print(ev.content, end="")
#     elif ev.type == "sources":
#         print(f"\nFound {len(ev.sources)} sources so far…")
#     elif ev.type == "approval_needed":
#         print(f"⚠️ Tool '{ev.pending_tool_call['name']}' needs approval")
#     elif ev.type == "final":
#         print("\nDone! Total tokens:", ev.metadata.get("usage", {}).get("total_tokens"))
# ```
#
# Legacy (pre-v0.9) – UnifiedStreamResponse
# ----------------------------------------
#
# Legacy code using ``UnifiedStreamResponse`` can be updated to use the new event-based
# streaming. Your code can support both by simply checking ``hasattr(chunk, "type")``
# and falling back to the old attributes when the discriminator is absent.

# SourceNode structure (individual source)
for source in response.sources:
    source.annotation_id      # Database ID of the source annotation
    source.content           # Raw text content of the annotation
    source.similarity_score  # Relevance score (0.0 to 1.0)
    source.metadata         # Dict with document_id, corpus_id, page, annotation_label, etc.
    
    # Convenience method for serialization
    source_dict = source.to_dict()  # Returns flattened dict for storage/transmission

# Note: conversation_id is available via agent.get_conversation_id()
```

#### Structured Data Extraction

The framework provides a powerful **structured response API** for one-shot data extraction without conversation persistence. This is perfect for:
- Form filling and data extraction pipelines
- API endpoints that need structured output
- Batch processing where conversation context isn't needed
- Integration with external systems expecting specific data schemas

```python
from pydantic import BaseModel, Field
from typing import List, Optional

# Define your target schema
class ContractParty(BaseModel):
    name: str = Field(description="Full legal name")
    role: str = Field(description="Role (e.g., 'Buyer', 'Seller')")
    address: Optional[str] = Field(None, description="Address if mentioned")

class ContractAnalysis(BaseModel):
    title: str = Field(description="Contract title or type")
    parties: List[ContractParty] = Field(description="All parties")
    total_value: Optional[float] = Field(None, description="Total value")
    governing_law: Optional[str] = Field(None, description="Governing law")

# Extract structured data - no conversation persistence
result = await agent.structured_response(
    "Analyze this contract and extract key information",
    ContractAnalysis
)

if result:
    print(f"Contract: {result.title}")
    print(f"Value: ${result.total_value:,.2f}" if result.total_value else "No value specified")
    for party in result.parties:
        print(f"- {party.name} ({party.role})")
```

**Key Features:**

1. **Type Safety**: Supports `str`, `int`, `float`, `bool`, `List[T]`, and Pydantic models
2. **No Persistence**: Messages are not stored in the database (ephemeral)
3. **Error Handling**: Returns `None` on failure instead of raising exceptions
4. **Parameter Overrides**: Supports per-call customization:
   ```python
   result = await agent.structured_response(
       prompt="Extract payment terms",
       target_type=PaymentTerms,
       system_prompt="You are a financial analyst. Be precise.",
       model="gpt-4",
       temperature=0.1,
       max_tokens=1000
   )
   ```

5. **Default Verification Behavior**: The default system prompt includes verification steps to:
   - Ensure accurate extraction from the actual document content
   - Prevent placeholder values (e.g., "N/A", "Not Available") unless they actually appear in the document
   - Return `None` for missing data rather than inventing values
   - This behavior can be overridden with a custom `system_prompt`

6. **Extra Context Support**: Pass additional guidance via `extra_context`:
   ```python
   result = await agent.structured_response(
       prompt="Extract warranty terms",
       target_type=WarrantyTerms,
       extra_context="""
       This is a software license agreement.
       Warranties are typically in Section 7 or Exhibit C.
       Look for both express warranties and warranty disclaimers.
       """
   )
   ```

**Framework Support:**
- ✅ **PydanticAI**: Fully implemented with automatic output strategy selection
  - Uses pydantic_ai's native capabilities to choose the best extraction method
  - Automatically selects between tool calling, JSON mode, or prompted extraction based on the model
  - Simplified system prompts for better reliability and efficiency
- Note: Custom framework adapters can implement `_structured_response_raw()` to support structured extraction

**Best Practices:**

```python
# Always check for None (indicates extraction failure)
result = await agent.structured_response("Extract dates", DateInfo)
if result is None:
    # Handle extraction failure
    logger.warning("Failed to extract dates")
    return

# Use specific prompts for better results
result = await agent.structured_response(
    "Extract the effective date and termination date from Section 3.1",
    ContractDates
)

# For simple types, be explicit about format
page_count = await agent.structured_response(
    "How many pages does this document have? Return only the number.",
    int
)
```

#### Source Structure

All sources returned by agents follow a standardized format that includes annotation metadata, similarity scores, and coordinate information via the `json` field:

```python
# Example source object structure (PDF document)
pdf_source = {
    "annotation_id": 123,
    "rawText": "This is the annotation content",
    "similarity_score": 0.85,
    "document_id": 456,
    "corpus_id": 789,
    "page": 2,
    "annotation_label": "Contract Clause",
    "json": {  # Full MultipageAnnotationJson for PDFs
        "0": {  # Page 0
            "bounds": {"top": 100.5, "bottom": 120.3, "left": 50.2, "right": 250.8},
            "tokensJsons": [
                {"pageIndex": 0, "tokenIndex": 10},
                {"pageIndex": 0, "tokenIndex": 11}
            ],
            "rawText": "annotation content"
        }
    }
}

# Example source object structure (text document)
text_source = {
    "annotation_id": -1,  # Negative ID for synthetic sources
    "rawText": "exact text match",
    "similarity_score": 1.0,
    "document_id": 456,
    "page": 1,
    "char_start": 1234,
    "char_end": 1250,
    "json": {"start": 1234, "end": 1250}  # Simple format for text files
}

# Sources are consistent across all contexts:
response = await agent.chat("What are the payment terms?")
for source in response.sources:
    print(f"Source: {source.annotation_id} (score: {source.similarity_score})")
    print(f"Content: {source.content}")
    print(f"Metadata: {source.metadata}")

    # Access the source as a dictionary (for serialization/storage)
    source_dict = source.to_dict()  # Automatically generates `json` field
```

**Key Source Features:**

- **Automatic `json` Field Generation**: `SourceNode.to_dict()` intelligently constructs the `json` field based on available metadata:
  - **PDF Sources**: Uses `annotation_json` from metadata → full `MultipageAnnotationJson` with token positions and bounding boxes
  - **Text Sources**: Uses `char_start`/`char_end` from metadata → simple `{start, end}` format
  - **Legacy Sources**: Passes through existing `json` field if present

- **Document Type Agnostic**: Tools store raw metadata (`annotation_json`, `char_start`, `char_end`); transformation happens automatically

- **Frontend Compatibility**: The `json` field format matches frontend TypeScript interfaces (`WebSocketSources`)

This format is used consistently in:
- Database storage (ChatMessage.data['sources'])
- WebSocket streaming (ASYNC_FINISH messages)
- API responses (UnifiedChatResponse.sources)
- Vector store search results
- Exact text search results

### Conversation Management

The framework provides sophisticated conversation management through the `CoreConversationManager`:

#### Persistent Conversations

```python
# Create agent with persistent conversation
# The `corpus` parameter is optional for document agents (use None for standalone).
agent = await agents.for_document(
    document=123, # Use actual document ID or object
    corpus=1,     # Use actual corpus ID or object
    user_id=456,  # Required for persistence
    conversation_id=789  # Optional: resume existing conversation
)

# Messages are automatically stored
response1 = await agent.chat("What is this document about?")
response2 = await agent.chat("Can you elaborate on section 2?")  # Context maintained

# Access conversation info
conversation_id = agent.get_conversation_id()
conversation_info = agent.get_conversation_info()
print(f"Conversation has {conversation_info['message_count']} messages")
```

#### Anonymous Conversations

```python
# Anonymous sessions - context maintained in memory only
# The `corpus` parameter is optional; standalone works for anonymous too.
agent = await agents.for_document(document=123, corpus=None)  # No user_id
response1 = await agent.chat("What is this document about?")
response2 = await agent.chat("Can you elaborate on section 2?")  # Context maintained in memory

# Anonymous conversations are session-only and not persisted
conversation_id = agent.get_conversation_id()  # Returns None for anonymous
conversation_info = agent.get_conversation_info()  # Returns basic info with no persistence

# Important: Anonymous conversations cannot be restored later
```

#### Message Storage Control

```python
# Control message storage per interaction
response = await agent.chat(
    "Sensitive query that shouldn't be stored",
    store_messages=False  # Skip database storage
)

# Manual message storage
user_msg_id = await agent.store_user_message("Custom user message")
llm_msg_id = await agent.store_llm_message("Custom LLM response")
```

### Tools

The framework provides a unified tool system that works across all supported frameworks. Core tools often have synchronous and asynchronous versions (e.g., `load_document_md_summary` and `aload_document_md_summary`).

#### Built-in Tools

```python
from opencontractserver.llms.tools import create_document_tools # Convenience function
from opencontractserver.llms.tools.core_tools import (
    load_document_md_summary, # Sync version
    aload_document_md_summary, # Async version
    get_notes_for_document_corpus,
    aget_notes_for_document_corpus, # Async version
    get_md_summary_token_length
)

# Use built-in tools by name (async versions preferred when available)
# The `corpus` parameter is optional for document agents (use None for standalone).
agent = await agents.for_document(
    document=123, # Use actual document ID or object
    corpus=1,     # Use actual corpus ID or object
    tools=["load_md_summary", "get_notes_for_document_corpus", "get_md_summary_token_length"]
)

# Or use CoreTool objects directly (e.g., from the convenience function)
# create_document_tools() provides a list of pre-configured CoreTool instances.
document_tools = create_document_tools()
agent = await agents.for_document(document=123, corpus=1, tools=document_tools) # Use actual document/corpus IDs
```

#### Custom Tools

```python
from opencontractserver.llms.tools.tool_factory import CoreTool # Can also use opencontractserver.llms.tools.create_from_function

def analyze_contract_risk(contract_text: str) -> str:
    """Analyze contract risk factors."""
    # Your custom analysis logic
    return "Risk analysis results..."

# Create CoreTool from function
risk_tool = CoreTool.from_function(
    analyze_contract_risk,
    description="Analyze contract risk factors"
)

# The `corpus` parameter is optional for document agents (use None for standalone).
agent = await agents.for_document(
    document=123, # Use actual document ID or object
    corpus=None,
    tools=[risk_tool]
)
```

#### Corpus-Dependent Tools

Some tools require a corpus context to function properly (e.g., tools that create notes or search across corpus documents). The framework provides automatic tool filtering for documents not in a corpus:

```python
from opencontractserver.llms.tools.tool_factory import CoreTool

def create_corpus_note(title: str, content: str, corpus_id: int) -> str:
    """Create a note within the corpus context."""
    # This tool needs a corpus to function
    return f"Created note '{title}' in corpus {corpus_id}"

# Mark tool as requiring corpus
corpus_tool = CoreTool.from_function(
    create_corpus_note,
    description="Create a note in the corpus",
    requires_corpus=True  # ← Corpus requirement flag
)

# For documents IN a corpus - tool is available
agent = await agents.for_document(
    document=123,
    corpus=456,  # Document is in this corpus
    tools=[corpus_tool]  # Tool will be included
)

# For documents NOT in a corpus - tool is automatically filtered out
agent = await agents.for_document(
    document=123,
    corpus=None,  # No corpus context
    tools=[corpus_tool]  # Tool will be skipped with info log
)
# Agent creation succeeds, corpus-dependent tools are gracefully omitted
```

**Key Features:**

- **Graceful Degradation**: Corpus-dependent tools are automatically filtered when `corpus=None`
- **Informative Logging**: Framework logs which tools are skipped and why
- **No Errors**: Agent creation never fails due to missing corpus - tools just adapt
- **Backward Compatibility**: Existing tools without `requires_corpus=True` work everywhere

**Built-in Tools with Corpus Requirements:**

Most built-in document tools work without corpus context, but some corpus-specific operations may require it:

```python
# These tools work with or without corpus
safe_tools = [
    "load_md_summary",           # Document summary access
    "get_md_summary_token_length", # Token counting
    "load_document_txt_extract"  # Raw text access
]

# These tools may require corpus context (marked with requires_corpus=True)
corpus_tools = [
    "get_notes_for_document_corpus",  # Notes tied to corpus context
    "add_document_note",              # Creating corpus-scoped notes
    # Framework handles filtering automatically
]

# Use both safely - framework filters as needed
agent = await agents.for_document(
    document=123,
    corpus=None,  # No corpus
    tools=safe_tools + corpus_tools  # Mixed tools - filtering handled automatically
)
```

#### Framework-Specific Tools

The framework automatically converts tools to the appropriate format:

```python
# CoreTool objects are automatically converted to framework-specific formats
# PydanticAI: CoreTool → PydanticAIToolWrapper

# Tools work seamlessly with the framework
# The `corpus` parameter is optional for document agents.
agent = await agents.for_document(
    document=123, # Use actual document ID or object
    corpus=None,  # Or pass a corpus ID/object when available
    framework=AgentFramework.PYDANTIC_AI,
    tools=["load_md_summary"]
)

#### Tool Approval & Human-in-the-Loop

Some tools might be *dangerous* (e.g. deleting data) or simply require legal review before execution. OpenContracts supports a **durable approval gate** that pauses the agent right before such a tool would run, persists all state, and lets a human approve or reject the call at a later time—even after a server restart.

##### Approval Flow Overview

When a tool requiring approval is called, the framework:

1. **Pauses execution** before running the tool
2. **Emits an `ApprovalNeededEvent`** with the pending tool call details
3. **Persists state** in the database with `state=AWAITING_APPROVAL`
4. **Waits for human decision** via `resume_with_approval()`

Upon approval/rejection:

1. **Emits `ApprovalResultEvent`** with the decision
2. If approved:
   - **Emits `ResumeEvent`** to signal continuation
   - **Executes the tool** with the original arguments
   - **Continues normal agent execution** (can call more tools)
3. If rejected:
   - **Emits final event** with rejection message
   - **Ends the conversation turn**

##### Flagging Tools for Approval

```python
from opencontractserver.llms import tools

async def delete_user_account(user_id: int) -> str:
    """Permanently delete a user (⚠ irreversible)."""
    # Dangerous operation implementation
    return f"Account {user_id} deleted"

# Mark tool as requiring approval
danger_tool = tools.from_function(
    delete_user_account,
    name="delete_user_account", 
    description="Delete a user – requires admin approval.",
    requires_approval=True,  # ← approval flag
)

agent = await agents.for_document(
    document=123, corpus=1,
    tools=[danger_tool]
)
```

##### Handling Approval Events

When the LLM attempts to call a flagged tool, the agent pauses and emits an `ApprovalNeededEvent`:

```python
from opencontractserver.llms.agents.core_agents import (
    ApprovalNeededEvent,
    ApprovalResultEvent,
    ResumeEvent
)

async for event in agent.stream("Delete user account 42"):
    match event.type:
        case "approval_needed":
            # Agent has paused, waiting for approval
            tool_call = event.pending_tool_call
            print(f"Tool '{tool_call['name']}' needs approval")
            print(f"Arguments: {tool_call['arguments']}")
            
            # Get human decision (via UI, CLI, etc.)
            approved = await get_user_decision()
            
            # Resume execution
            async for resume_event in agent.resume_with_approval(
                llm_message_id=event.llm_message_id,
                approved=approved
            ):
                # Handle approval result and continuation events
                match resume_event.type:
                    case "approval_result":
                        print(f"Decision: {resume_event.decision}")
                    case "resume":
                        print(f"Execution resuming...")
                    case "thought" | "content" | "sources" | "final":
                        # Normal event processing continues
                        pass
                 
        case "thought" | "content" | "sources" | "final":
            # Handle other events normally
            pass
```

##### New Event Types

The approval flow introduces two new event types:

| Event Type | Purpose | Key Fields | When Emitted |
|------------|---------|------------|--------------|
| `ApprovalResultEvent` | Confirms decision was recorded | `decision` ("approved"/"rejected"), `pending_tool_call` | Immediately after `resume_with_approval()` |
| `ResumeEvent` | Signals execution restart | Standard event fields | After approval, before tool execution |
| `ErrorEvent` | Error occurred during execution | `error`, `metadata`, `is_complete` (always True) | Unrecoverable errors (e.g., rate limits, API failures) |

##### Approval Event Structure

`ApprovalNeededEvent` contains:

| Field | Type | Description |
|-------|------|-------------|
| `type` | `"approval_needed"` | Event discriminator |
| `pending_tool_call` | `dict` | `{name, arguments, tool_call_id}` |
| `user_message_id` | `int` | Database message ID |
| `llm_message_id` | `int` | Database message ID (use for resume) |
| `metadata` | `dict` | Additional state information |

##### Resumption API

```python
# Resume execution after approval
# Returns an async generator of events
async for event in agent.resume_with_approval(
    llm_message_id=paused_message_id,
    approved=True
):
    # Process events (approval_result, resume, thought, content, etc.)
    if event.type == "final":
        print(f"Final answer: {event.accumulated_content}")

# Reject the tool execution
async for event in agent.resume_with_approval(
    llm_message_id=paused_message_id,
    approved=False
):
    # Will receive approval_result + final event with rejection message
    pass
```

**Multi-Tool Execution**: After approval, the agent continues its normal execution flow. It can:
- Process the tool result
- Call additional tools (including other approval-gated tools)
- Generate a final response incorporating all tool results

##### Implementation Details

###### State Validation

The `resume_with_approval()` method performs strict state validation before resuming execution:

```python
# Check message state
current_state = paused_msg.data.get("state")
if current_state != MessageState.AWAITING_APPROVAL:
    # Handle edge cases
    if current_state in [MessageState.COMPLETED, MessageState.CANCELLED]:
        # Message already processed - likely duplicate request
        return  # Empty generator, no error
    else:
        raise ValueError(f"Message is not awaiting approval (state: {current_state})")
```

**Validation Steps:**
1. Loads the paused `ChatMessage` from database by `llm_message_id`
2. Checks `data['state']` is exactly `AWAITING_APPROVAL`
3. Handles duplicate requests gracefully (returns empty generator if already processed)
4. Raises `ValueError` for invalid states

**Error Scenarios:**
- Message not found → `ValueError` raised
- Message not awaiting approval → `ValueError` raised (unless already completed/cancelled)
- Duplicate approval request → Silently returns (idempotent behavior)

###### Tool Execution Paths

When approved, the framework attempts to execute the tool using two fallback paths:

**Path 1: Agent Config Tools** (lines 909-945)
```python
# 1. Search config.tools for matching tool name
for tool in self.config.tools or []:
    if getattr(tool, "__name__", None) == tool_name:
        wrapper_fn = tool
        break

# 2. Execute if found
if wrapper_fn:
    result = await wrapper_fn(_EmptyCtx(), **tool_args)
    tool_executed = True
```

**Path 2: PydanticAI Registry** (fallback, lines 946-995)
```python
# 1. Look up tool in pydantic-ai agent's function registry
tool_obj = self.pydantic_ai_agent._function_tools.get(tool_name)

# 2. Extract underlying callable from tool object
for attr in ("function", "_wrapped_function", "callable_function"):
    candidate = getattr(tool_obj, attr, None)
    if callable(candidate):
        break

# 3. Execute the callable
result = await candidate(_EmptyCtx(), **tool_args)
```

**Empty Context Pattern:**
The framework creates a minimal context object with:
- `tool_call_id`: Preserved from the paused message
- `skip_approval_gate`: Set to `True` to prevent re-triggering approval

**Tool Argument Normalization:**
The method handles various argument formats:
```python
# String arguments (JSON or plain)
if isinstance(tool_args_raw, str):
    try:
        tool_args = json.loads(tool_args_raw)  # Try JSON parse
    except json.JSONDecodeError:
        # Fallback: wrap as parameter for known tools
        if tool_name == "update_document_summary":
            tool_args = {"new_content": tool_args_raw}
        else:
            tool_args = {"arg": tool_args_raw}

# Dict arguments (already normalized)
elif isinstance(tool_args_raw, dict):
    tool_args = tool_args_raw
```

###### Continuation Prompt Mechanism

After tool execution (approved path), the framework constructs a continuation prompt:

```python
# Build prompt with tool result
continuation_prompt = (
    f"The tool '{tool_name}' was executed with user approval and returned: "
    f"{json.dumps(tool_result, indent=2)}. "
    f"Please continue with your original task based on this result."
)

# Resume normal streaming
async for ev in self._stream_core(
    continuation_prompt,
    force_llm_id=resumed_llm_id,      # New message for resumed run
    force_user_msg_id=user_message_id  # Link to original user message
):
    yield ev
```

**Key Implementation Points:**
1. **New LLM Message**: Creates a fresh `ChatMessage` for the resumed run (`resumed_llm_id`)
2. **User Message Linking**: Finds the most recent `HUMAN` message in the conversation to link events properly
3. **Tool Result Injection**: Embeds the tool execution result in the continuation prompt
4. **History Preservation**: The tool result is also appended to message history as a `ToolReturnPart` (approved path only)

###### Rejection Path

When `approved=False`:

```python
# 1. Emit ApprovalResultEvent with decision="rejected"
yield ApprovalResultEvent(decision="rejected", ...)

# 2. Mark paused message as CANCELLED
await self.complete_message(
    paused_msg.id,
    paused_msg.content,
    metadata={
        "state": MessageState.CANCELLED,
        "approval_decision": "rejected"
    }
)

# 3. Emit final event and stop
yield FinalEvent(
    accumulated_content="Tool execution rejected by user.",
    metadata={"approval_decision": "rejected"}
)
return  # No further execution
```

**Rejection Characteristics:**
- No tool execution occurs
- Conversation turn ends immediately
- Paused message marked as `CANCELLED` in database
- Simple rejection message returned to caller

###### Event Sequence

**Approval Flow (approved=True):**
```
1. ApprovalResultEvent (decision="approved")
2. ResumeEvent (signals execution restart)
3. [Stream events from continuation...] (ThoughtEvent, ContentEvent, etc.)
4. FinalEvent (with approval_decision in metadata)
```

**Rejection Flow (approved=False):**
```
1. ApprovalResultEvent (decision="rejected")
2. FinalEvent (rejection message, conversation ends)
```

**Implementation Notes:**
- Approval state persists across server restarts (stored in database)
- Only PydanticAI agents support approval gating currently
- Custom framework adapters should implement approval handling in their `_stream_raw()` method
- Code paths: `tools/pydantic_ai_tools.py` (veto-gate), `agents/pydantic_ai_agents.py` (pause/resume)
- All events include `user_message_id` and `llm_message_id` for tracking

##### Nested Approval Gates (Corpus → Document Sub-Agents)

When a corpus agent delegates a question to a document sub-agent via
`ask_document`, the sub-agent may itself encounter tools that require
approval. These nested approval events propagate up to the corpus agent
and ultimately to the user through the following mechanism:

**Propagation Flow:**

```
User ──▶ CorpusAgent ──ask_document──▶ DocumentSubAgent
                                            │
                        ┌───────────────────┘
                        ▼
           Sub-agent tool requires approval
                        │
                        ▼
           ApprovalNeededEvent emitted in sub-agent stream
                        │
                        ▼
           ask_document_tool detects event, raises
           ToolConfirmationRequired with nested metadata
                        │
                        ▼
           Corpus agent pauses, surfaces to user via WebSocket
                        │
                        ▼
           User approves/rejects via frontend modal
                        │
                        ▼
           resume_with_approval() re-invokes ask_document
           with config._approval_bypass_allowed = True
                        │
                        ▼
           Sub-agent created with skip_approval_gate=True
           (tool executes without re-prompting)
```

**Metadata Preservation:**

The `ToolConfirmationRequired` exception carries sub-agent tool details
in `_`-prefixed keys for frontend display:

```python
raise ToolConfirmationRequired(
    tool_name="ask_document",
    tool_args={
        "document_id": document_id,
        "question": question,
        # Metadata for UI display (stripped before execution):
        "_sub_tool_name": "update_document_summary",
        "_sub_tool_arguments": {"new_content": "..."},
    },
)
```

The frontend (CorpusChat) unwraps these to show the actual sub-tool name
and arguments in the approval modal, rather than the generic
`ask_document` wrapper.

**Security: Approval Bypass Protection:**

The `skip_approval` mechanism uses `config._approval_bypass_allowed`
(a runtime flag on `AgentConfig`) rather than a function parameter, to
prevent LLM prompt injection from bypassing approval gates:

- Normal execution: `_approval_bypass_allowed` is `False` (default)
- Post-approval resume: `resume_with_approval()` sets it to `True` in a
  `try/finally` block, ensuring it is always reset
- The flag is read inside `ask_document_tool`'s closure and passed to
  `_agents_api.for_document(skip_approval_gate=bypass)`

**Defensive Handling:**

Malformed `approval_needed` events (missing `name`, non-dict
`pending_tool_call`, empty strings) are logged and skipped rather than
crashing the tool. The sub-agent stream continues normally.

**Key Files:**
- `agents/pydantic_ai_agents.py`: `ask_document_tool()` closure,
  `resume_with_approval()` bypass flag
- `frontend/src/components/corpuses/CorpusChat.tsx`: Sub-tool unwrapping
  in `ASYNC_APPROVAL_NEEDED` handler
- `tests/test_nested_approval_gates.py`: Comprehensive test suite
- The method always returns an async generator (even for rejection) for consistent API
```

### Nested Agent Streaming

The framework now supports **real-time visibility into nested agent execution** through the stream observer pattern. This is particularly powerful when corpus agents delegate work to document agents.

#### The Stream Observer Pattern

When a parent agent (e.g., corpus agent) calls a child agent (e.g., document agent via `ask_document` tool), the child's stream events can be forwarded to a configured observer:

```python
from opencontractserver.llms import agents
from opencontractserver.llms.types import StreamObserver

# Define your observer
async def websocket_forwarder(event):
    """Forward nested events to WebSocket clients."""
    await websocket.send_json({
        "type": event.type,
        "content": getattr(event, "content", ""),
        "thought": getattr(event, "thought", ""),
        "sources": [s.to_dict() for s in getattr(event, "sources", [])]
    })

# Create agent with observer
corpus_agent = await agents.for_corpus(
    corpus=corpus_id,
    user_id=user_id,
    stream_observer=websocket_forwarder
)

# When streaming, nested events bubble up automatically
async for event in corpus_agent.stream("Analyze payment terms across all contracts"):
    # Parent agent events
    if event.type == "thought" and "[ask_document]" in event.thought:
        # These are relayed child agent thoughts
        print(f"Child agent: {event.thought}")
    else:
        # Direct parent agent events
        print(f"Parent: {event.type} - {event.content}")
```

#### How It Works

1. **Configuration**: Set `stream_observer` in `AgentConfig` or pass it when creating agents
2. **Automatic Forwarding**: Framework adapters call the observer for every emitted event
3. **Child Agent Integration**: Tools like `ask_document` forward their stream to the observer
4. **WebSocket Ready**: Perfect for real-time UI updates showing nested reasoning

#### Example: Corpus Agent with Live Document Analysis

```python
# In your WebSocket handler
async def handle_corpus_query(websocket, corpus_id, query):
    # Create observer that forwards to WebSocket
    async def forward_to_client(event):
        await websocket.send_json({
            "event": event.type,
            "data": {
                "content": getattr(event, "content", ""),
                "thought": getattr(event, "thought", ""),
                "sources": [s.to_dict() for s in getattr(event, "sources", [])],
                "metadata": getattr(event, "metadata", {})
            }
        })
    
    # Create corpus agent with observer
    agent = await agents.for_corpus(
        corpus=corpus_id,
        stream_observer=forward_to_client
    )
    
    # Stream response - client sees EVERYTHING including nested calls
    async for event in agent.stream(query):
        # Parent events also go to client
        await forward_to_client(event)
```

#### Benefits

- **Complete Visibility**: See exactly what child agents are doing in real-time
- **Better UX**: Users see progress even during long-running nested operations
- **Debugging**: Full execution trace across agent boundaries
- **No Blocking**: Parent agent continues streaming while child executes

#### Implementation Details

The stream observer is implemented at the framework adapter level:

- **PydanticAI**: `ask_document_tool` explicitly forwards child events
- **CoreAgentBase**: `_emit_observer_event` helper ensures safe forwarding
- **Error Handling**: Observer exceptions are caught and logged, never breaking the stream

```python
# Inside ask_document_tool (simplified)
async for ev in doc_agent.stream(question):
    # Capture content for final response
    if ev.type == "content":
        accumulated_answer += ev.content
    
    # Forward ALL events to observer
    if callable(observer_cb):
        await observer_cb(ev)  # Real-time forwarding
    
    # Process sources, timeline, etc.
```

This pattern ensures that even deeply nested agent calls remain visible and debuggable, providing unprecedented transparency into complex multi-agent workflows.

### Streaming

All agents support streaming responses for real-time interaction. The framework now provides **event-based streaming** for rich, granular interaction visibility.

#### Event-Based Streaming (Recommended)

**PydanticAI agents** emit granular events that expose the agent's reasoning process:

```python
# Rich event streaming with PydanticAI
agent = await agents.for_document(
    document=123, corpus=1, 
    framework=AgentFramework.PYDANTIC_AI
)

async for event in agent.stream("What are the key contract terms?"):
    match event.type:
        case "thought":
            print(f"🤔 Agent thinking: {event.thought}")
            # event.metadata may contain tool info for tool-related thoughts
            
        case "content":
            print(event.content, end="", flush=True)
            # event.metadata contains tool details if content is from tool calls
            
        case "sources":
            print(f"\n📚 Found {len(event.sources)} relevant sources")
            for source in event.sources:
                print(f"  - {source.annotation_id}: {source.content[:50]}...")
                
        case "error":
            print(f"\n❌ Error: {event.error}")
            print(f"Error type: {event.metadata.get('error_type', 'Unknown')}")
            # Handle error gracefully - stream ends after error event
            break
                
        case "final":
            print(f"\n✅ Complete! Usage: {event.metadata.get('usage', {})}")
            print(f"Total sources: {len(event.sources)}")

# All events include message IDs for tracking
print(f"Conversation: {event.user_message_id} → {event.llm_message_id}")
```

**Example PydanticAI Event Sequence:**
```
🤔 Agent thinking: Received user prompt; beginning reasoning cycle…
🤔 Agent thinking: Sending request to language model…
🤔 Agent thinking: Processing model response – may invoke tools…
🤔 Agent thinking: Calling tool `similarity_search` with args {'query': 'key contract terms', 'k': 10}
📚 Found 5 relevant sources
🤔 Agent thinking: Tool `similarity_search` returned a result.
🤔 Agent thinking: Run finished; aggregating final results…
Based on the contract analysis, the key terms include...
✅ Complete! Usage: {'requests': 2, 'total_tokens': 1247}
```

#### Legacy Streaming (Backward Compatibility)

Legacy code using the traditional streaming approach can be updated to use event-based streaming:

```python
# Traditional streaming - still supported
async for chunk in agent.stream("Analyze liability clauses"):
    print(chunk.content, end="")
    
    # Access metadata during streaming
    if chunk.is_complete:
        print(f"\nSources: {len(chunk.sources)}")
        print(f"Message ID: {chunk.llm_message_id}")

# Detect streaming type at runtime
async for event in agent.stream("Your query"):
    if hasattr(event, 'type'):  # New event-based streaming
        handle_event_based_streaming(event)
    else:  # Legacy UnifiedStreamResponse
        handle_legacy_streaming(event)
```

#### Advanced Streaming Patterns

```python
# Stream with custom message storage control
async for event in agent.stream("Sensitive analysis", store_messages=False):
    # Process events without persisting to database
    if event.type == "content":
        secure_output_handler(event.content)

# Real-time UI updates with event metadata
async for event in agent.stream("Complex analysis"):
    if event.type == "thought":
        ui.show_thinking_indicator(event.thought)
        if "tool_name" in event.metadata:
            ui.show_tool_usage(event.metadata["tool_name"])
    elif event.type == "content":
        ui.append_content(event.content)
    elif event.type == "sources":
        ui.update_source_panel(event.sources)
```

### Embeddings

The framework provides sync embeddings APIs via `opencontractserver.llms.embeddings`:

```python
from opencontractserver.llms import embeddings

# Sync version (currently the only exposed API)
embedder_path, vector = embeddings.generate("Contract analysis text")
print(f"Using embedder: {embedder_path}")
print(f"Vector dimension: {len(vector)}")
print(f"Vector type: {type(vector)}")  # numpy.ndarray

# The embeddings integrate with the vector stores for document search

# Note: For async embedding generation, use the underlying utility directly:
from opencontractserver.utils.embeddings import generate_embeddings_from_text
embedder_path, vector = generate_embeddings_from_text("Contract analysis text")
```

### Vector Stores

Vector stores provide both sync and async search methods, accessible via `opencontractserver.llms.vector_stores`.

```python
from opencontractserver.llms import vector_stores
from opencontractserver.llms.vector_stores.core_vector_stores import VectorSearchQuery

# Create vector store (framework-specific store will be chosen based on config or default)
store = vector_stores.create(
    framework="pydantic_ai", # Or custom-defined framework, or omit for default
    user_id=123, # Optional, for user-specific data if applicable
    corpus_id=456 # Or document_id for document-specific vector store context
)

# Search annotations
query = VectorSearchQuery(
    query_text="payment obligations",
    similarity_top_k=10
)

# Async search (recommended)
results = await store.async_search(query)

# Sync search (for compatibility)
results = store.search(query)

for result in results:
    print(f"Score: {result.similarity_score}")
    print(f"Text: {result.annotation.raw_text[:100]}...")
```

## Architecture

The framework follows a layered architecture that separates concerns and enables framework flexibility:

```
┌─────────────────────────────────────────┐
│           API Layer                     │  ← api.py (agents, embeddings, vector_stores, tools)
├─────────────────────────────────────────┤
│        Framework Adapter Layer          │  ← agents/pydantic_ai_agents.py
│ (Implements CoreAgent for specific SDK) │     agents/pydantic_ai_agents.py
├─────────────────────────────────────────┤
│         Core Agent Protocol             │  ← agents/core_agents.py (Defines .chat, .stream)
│         & Unified Tool System           │  ← tools/ (CoreTool, UnifiedToolFactory)
├─────────────────────────────────────────┤
│         Core Business Logic             │  ← Framework-agnostic utils, config
│         & Conversation Management       │     conversations/ (CoreConversationManager)
├─────────────────────────────────────────┤
│      Django Models & Vector Stores      │  ← Your documents + annotation data & persistence
└─────────────────────────────────────────┘
```

### How It Works

1. **Beautiful API (`api.py`)**:
   - `agents.for_document(document=123, corpus=1)` provides the elegant entry point.
   - `agents.get_structured_response_from_document()` and `agents.get_structured_response_from_corpus()` provide convenience methods for one-shot structured extraction.
   - Handles parameter validation, type conversion, and defaults.
   - Routes to the appropriate factory based on framework choice.
   - Similar entry points exist for `embeddings`, `vector_stores`, and `tools`.

2. **Unified Factory (`agents/agent_factory.py`, `vector_stores/vector_store_factory.py`, etc.)**:
   - E.g., `UnifiedAgentFactory.create_document_agent()` orchestrates agent creation.
   - Converts string framework names to enums, resolves tools, creates contexts.
   - Delegates to framework-specific implementations.

3. **Framework Adapters** (e.g., `agents/pydantic_ai_agents.py`):
   - E.g., `PydanticAIDocumentAgent.create()` builds the actual LLM integration.
   - Creates vector stores, configures embeddings, sets up the underlying PydanticAI agent.
   - Returns a framework-specific agent that implements the `CoreAgent` protocol.

4. **CoreAgent Protocol (`agents/core_agents.py`)**:
   - The returned agent object (e.g., an instance of `PydanticAIDocumentAgent`) inherits from `CoreAgentBase`, which provides universal `chat()`, `stream()`, and `structured_response()` wrappers that handle all database persistence, approval gating, and message lifecycle management.
   - Framework adapters only implement low-level `_chat_raw()`, `_stream_raw()`, and `_structured_response_raw()` methods that return pure content without any database side-effects.
   - When you call `await agent.chat("Your query")`, the `CoreAgentBase` wrapper automatically handles user message storage, LLM placeholder creation, calling the adapter's `_chat_raw()` method, and completing the stored message with results.
   - The `structured_response()` method provides ephemeral, typed data extraction without any database persistence—perfect for one-shot extractions.
   - This architecture ensures that adapters cannot "forget" to persist conversations or handle approval flows—all database operations are centralized and automatic.
   - **Approval Flow**: When a tool requiring approval is called, the framework automatically pauses execution, emits `ApprovalNeededEvent`, and waits for `resume_with_approval()` to be called.
   - **Resume Capability**: The `resume_with_approval()` method allows continuation of paused executions, emitting `ApprovalResultEvent` and `ResumeEvent` before resuming normal agent flow.
   - PydanticAI agents provide granular event-based streaming that exposes the agent's execution graph in real-time.
   - The `_emit_observer_event()` helper enables stream observers to receive events from nested agent calls, providing complete visibility across agent boundaries.

5. **Conversation Management**:
   - `CoreConversationManager` handles message persistence and retrieval.
   - Automatically stores user and LLM messages with proper relationships.
   - Supports both persistent (database) and anonymous (memory-only) conversations.

6. **Tool System**:
   - `CoreTool` provides framework-agnostic tool definitions.
   - Framework-specific factories convert tools to appropriate formats.
   - Built-in tools (e.g., via `create_document_tools()`) for document analysis, note retrieval, and content access. Async versions of core tools are often available.

7. **Timeline Streaming System** (`TimelineStreamMixin`):
   - A mixin class that framework adapters can inherit to get automatic timeline construction
   - Wraps the adapter's `_stream_core()` method and intercepts all emitted events
   - Uses `TimelineBuilder` to incrementally build a reasoning timeline from stream events
   - Automatically injects the complete timeline into `FinalEvent.metadata['timeline']`
   - Persists the timeline to the database via `_finalise_llm_message()` helper
   - Ensures every framework produces consistent timeline structure without duplicate code
   - Timeline includes: thoughts, tool calls, tool results, source discoveries, and status markers
   - Used by PydanticAI adapters (`PydanticAICoreAgent` inherits from `TimelineStreamMixin`)

### Framework Support

#### LlamaIndex Integration

> **⚠️ Warning: LlamaIndex Support Removed**
> 
> LlamaIndex integration has been removed from the OpenContracts LLM framework. All agents now use PydanticAI as the underlying framework. If you need LlamaIndex support, you can implement a custom adapter by following the `CoreAgent` protocol in `agents/core_agents.py`.


#### PydanticAI Integration

```python
# PydanticAI agents use:
# - Modern async patterns with proper type safety
# - Execution graph streaming via agent.iter() for granular visibility
# - Rich event-based streaming (ThoughtEvent, ContentEvent, SourceEvent, FinalEvent)
# - Structured tool definitions with Pydantic models
# - Real-time tool call observation with arguments and results
# - Automatic output strategy selection (tool calling, JSON mode, or prompting)
# - Optimized structured extraction using pydantic_ai's native capabilities

from opencontractserver.llms.agents.pydantic_ai_agents import PydanticAIDocumentAgent
from opencontractserver.llms.vector_stores.pydantic_ai_vector_stores import PydanticAIAnnotationVectorStore

# Framework-specific features
# agent = await PydanticAIDocumentAgent.create(document_obj, corpus_obj, config, conversation_manager, tools)
# vector_search_tool = PydanticAIAnnotationVectorStore(...).create_vector_search_tool()

# PydanticAI streaming produces rich UnifiedStreamEvent objects
async for event in pydantic_agent.stream("Analyze contract"):
    event.type                 # "thought", "content", "sources", or "final"
    event.metadata             # Rich metadata (tool names, args, usage, etc.)
    
    # Event-specific fields:
    if event.type == "thought":
        event.thought          # Agent's reasoning step
    elif event.type == "content":
        event.content          # Text delta for final answer
    elif event.type == "sources":
        event.sources          # List of SourceNode objects
    elif event.type == "final":
        event.accumulated_content  # Complete final answer
        event.sources              # All sources found
        event.metadata['usage']    # Token usage statistics

# Structured extraction leverages pydantic_ai's automatic strategy selection
# The framework automatically chooses the best method based on the model:
# - Tool calling for models like GPT-4
# - Native JSON mode where available
# - Prompted extraction as fallback
result = await agent.structured_response(
    "Extract contract dates",
    ContractDates  # pydantic_ai handles the output strategy
)
```

#### Framework Selection

Choose your framework based on your needs:

| Framework | Best For | Streaming Type | Structured Response | Visibility |
|-----------|----------|----------------|---------------------|------------|
| **PydanticAI** | Production use, all features | Event-based (thought/content/sources/final) | ✅ Optimized with automatic strategy selection | Full execution graph visibility |
| **Custom Adapters** | Specialized requirements | Implement in `_stream_raw()` | Implement in `_structured_response_raw()` | Depends on implementation |

```python
# Specify framework explicitly (PydanticAI is the default and recommended framework)
agent = await agents.for_document(
    document=123, corpus=1,
    framework=AgentFramework.PYDANTIC_AI
)

# Or set globally via Django settings
# LLMS_DEFAULT_AGENT_FRAMEWORK = "pydantic_ai"
```

## Agent Permission Model

The LLM framework implements a comprehensive permission system that ensures agents always execute with the calling user's permissions, never escalating privileges. This security model applies at multiple layers: consumer validation, agent factory filtering, and runtime tool execution.

### Permission Architecture Overview

The permission system operates on three key principles:

1. **User Context Inheritance**: Agents inherit and operate within the permissions of the user who invokes them
2. **Defense in Depth**: Multiple validation layers ensure permission checks cannot be bypassed
3. **Graceful Degradation**: Tools requiring unavailable permissions are filtered out rather than causing errors

### Tool Permission Flags

Every tool in the system can declare its permission requirements through three boolean flags:

```python
from opencontractserver.llms.tools.tool_factory import CoreTool

# Example tool with permission flags
dangerous_tool = CoreTool.from_function(
    my_function,
    name="delete_data",
    description="Delete data from the system",
    requires_corpus=True,          # Tool needs corpus context
    requires_approval=True,         # Tool needs user confirmation before execution
    requires_write_permission=True  # Tool performs write operations (NEW)
)
```

#### Permission Flag Definitions

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `requires_corpus` | `bool` | `False` | Tool requires a corpus context to function. Automatically filtered when `corpus=None`. |
| `requires_approval` | `bool` | `False` | Tool execution pauses for human approval before running. See "Tool Approval & Human-in-the-Loop" section. |
| `requires_write_permission` | `bool` | `False` | Tool performs write operations (create, update, delete). Filtered if user lacks WRITE permission on the corpus. |

### Permission Filtering Flow

The framework enforces permissions at three distinct layers, creating a defense-in-depth security model:

#### Layer 1: Consumer Validation (Entry Point)

**Location**: `opencontractserver/consumers/unified_agent_consumer.py`

The WebSocket consumer (or API endpoint) performs initial READ permission validation:

```python
# Consumer checks READ access before creating agent
if not user_has_permission_for_obj(user, corpus, "READ"):
    raise PermissionDenied("User lacks READ access to corpus")

# Similarly for documents
if not user_has_permission_for_obj(user, document, "READ"):
    raise PermissionDenied("User lacks READ access to document")
```

**Purpose**: Ensure the user can even access the document/corpus before creating an agent.

#### Layer 2: Agent Factory Filtering (Agent Creation)

**Location**: `opencontractserver/llms/agents/agent_factory.py`

When creating an agent, the factory filters out tools requiring WRITE permission if the user lacks it:

```python
# In UnifiedAgentFactory._filter_tools_by_write_permission()
def _user_has_write_permission(user_id: Optional[int], corpus: Optional[Corpus]) -> bool:
    """Check if user has WRITE permission for the corpus."""
    if not user_id or not corpus:
        return False

    user = User.objects.get(id=user_id)
    return user_has_permission_for_obj(user, corpus, "WRITE")

# Filter tools based on write permission
filtered_tools = []
for tool in tools:
    if getattr(tool, "requires_write_permission", False):
        if not _user_has_write_permission(user_id, corpus):
            logger.info(f"Filtering tool '{tool.name}' - user lacks WRITE permission")
            continue
    filtered_tools.append(tool)
```

**Purpose**: Prevent the agent from even seeing tools it shouldn't be allowed to use, reducing attack surface.

#### Layer 3: Runtime Validation (Tool Execution)

**Location**: `opencontractserver/llms/tools/pydantic_ai_tools.py`

Even if a tool somehow makes it to execution, the wrapper performs a final permission check:

```python
# In PydanticAIToolWrapper.__call__()
async def __call__(self, ctx: AgentContext, **kwargs):
    # Check permissions before execution
    await self._check_user_permissions(ctx)

    # Execute tool
    result = await self.core_tool.function(**kwargs)
    return result

async def _check_user_permissions(self, ctx: AgentContext):
    """Validate user permissions before tool execution."""
    if self.core_tool.requires_write_permission:
        user_id = ctx.config.user_id
        corpus = ctx.corpus

        if not user_id or not corpus:
            raise PermissionDenied("Write operation requires authenticated user and corpus")

        user = await User.objects.aget(id=user_id)
        if not await user_has_permission_for_obj(user, corpus, "WRITE"):
            raise PermissionDenied(f"User lacks WRITE permission for tool '{self.core_tool.name}'")
```

**Purpose**: Final safety check that catches any bypass attempts or edge cases, ensuring write operations never execute without proper permissions.

### Permission Enforcement by Tool Type

Different tools have different permission requirements based on their operations:

#### Read-Only Tools (No Special Permissions)

Tools that only read data don't require write permission:

```python
# Examples from opencontractserver/llms/tools/tool_registry.py
tools_registry = [
    CoreTool.from_function(
        load_document_md_summary,
        name="load_md_summary",
        description="Load markdown summary of the document",
        requires_corpus=False,
        requires_approval=False,
        requires_write_permission=False  # Read-only operation
    ),
    CoreTool.from_function(
        get_notes_for_document_corpus,
        name="get_notes_for_document_corpus",
        description="Retrieve notes for document",
        requires_corpus=True,
        requires_approval=False,
        requires_write_permission=False  # Read-only operation
    ),
]
```

These tools are available to users with READ permission.

#### Write Tools (Require WRITE Permission)

Tools that modify data require explicit write permission:

```python
# Examples from opencontractserver/llms/tools/tool_registry.py
tools_registry = [
    CoreTool.from_function(
        add_document_note,
        name="add_document_note",
        description="Create a new note for the document",
        requires_corpus=True,
        requires_approval=True,
        requires_write_permission=True  # Creates new data
    ),
    CoreTool.from_function(
        update_document_summary,
        name="update_document_summary",
        description="Update document summary",
        requires_corpus=True,
        requires_approval=True,
        requires_write_permission=True  # Modifies existing data
    ),
]
```

These tools are automatically filtered out for users with only READ permission.

### Security Guarantees

The permission model provides several critical security guarantees:

#### 1. No Privilege Escalation

Even if an agent's creator has higher permissions, the agent executes with the caller's permissions:

```python
# Scenario: Admin creates a shared agent, regular user calls it
# Admin has WRITE permission, regular user has READ only

# User invokes agent
agent = await agents.for_document(
    document=doc_id,
    corpus=corpus_id,
    user_id=regular_user_id  # ← Regular user's ID, not admin's
)

# Agent filters tools based on regular_user_id's permissions
# Write tools are automatically excluded, even though admin could use them
```

#### 2. Consistent Permission Checks

All three validation layers check the same permission rules using `user_has_permission_for_obj()` from `opencontractserver.utils.permissioning`:

```python
from opencontractserver.utils.permissioning import user_has_permission_for_obj

# Same check used at all three layers
has_write = user_has_permission_for_obj(user, corpus, "WRITE")
```

#### 3. Fail-Safe Defaults

Tools default to the most restrictive permission model:

- `requires_write_permission=False` by default (must explicitly opt-in)
- Tools without permission flags are treated as read-only
- Missing user context blocks all write operations

### Permission Model in Action

Here's a complete example showing how permissions flow through the system:

```python
from opencontractserver.llms import agents

# User with READ-only permission attempts to use agent
user_id = 123  # User with READ permission, no WRITE
corpus_id = 456

# Create agent for document
agent = await agents.for_document(
    document=789,
    corpus=corpus_id,
    user_id=user_id
)

# Agent creation succeeds, but write tools are filtered:
# ✅ Available: load_md_summary, get_notes_for_document_corpus, similarity_search
# ❌ Filtered: add_document_note, update_document_summary, duplicate_annotations

# User can query the agent
response = await agent.chat("What are the key contract terms?")
# ✅ Works - uses read-only tools (similarity_search, load_md_summary)

# User asks agent to create a note
response = await agent.chat("Create a note summarizing the payment terms")
# ✅ Request succeeds, but agent can't call add_document_note (not available)
# Agent responds: "I cannot create notes as that tool is not available"

# If write tool somehow executed (impossible due to multi-layer checks):
# ❌ Layer 3 validation raises PermissionDenied exception
```

### Key Implementation Files

Understanding the permission model requires familiarity with these key files:

| File | Purpose | Key Functions/Classes |
|------|---------|----------------------|
| `opencontractserver/llms/tools/tool_factory.py` | Core tool definition with permission flags | `CoreTool`, `requires_write_permission` flag |
| `opencontractserver/llms/tools/tool_registry.py` | Registry of all built-in tools with their permissions | `tools_registry` list with flag definitions |
| `opencontractserver/llms/agents/agent_factory.py` | Agent creation with tool filtering | `_filter_tools_by_write_permission()`, `_user_has_write_permission()` |
| `opencontractserver/llms/tools/pydantic_ai_tools.py` | Runtime permission validation wrapper | `PydanticAIToolWrapper`, `_check_user_permissions()` |
| `opencontractserver/utils/permissioning.py` | Core permission checking utilities | `user_has_permission_for_obj()` |
| `opencontractserver/consumers/unified_agent_consumer.py` | WebSocket consumer with entry validation | Initial READ permission checks |

### Best Practices for Tool Development

When creating custom tools, follow these guidelines:

#### 1. Always Declare Write Requirements

```python
# ❌ Bad - doesn't declare write requirement
custom_tool = CoreTool.from_function(
    delete_annotations,
    name="delete_annotations",
    description="Delete annotations"
    # Missing requires_write_permission=True
)

# ✅ Good - explicitly declares write requirement
custom_tool = CoreTool.from_function(
    delete_annotations,
    name="delete_annotations",
    description="Delete annotations",
    requires_write_permission=True  # ← Explicit declaration
)
```

#### 2. Combine Permission Flags Appropriately

Some tools need multiple permission checks:

```python
# Tool that writes data AND needs user confirmation
risky_tool = CoreTool.from_function(
    bulk_delete_notes,
    name="bulk_delete_notes",
    description="Delete multiple notes at once",
    requires_corpus=True,          # Needs corpus context
    requires_approval=True,         # Dangerous operation
    requires_write_permission=True  # Modifies data
)
```

#### 3. Document Permission Requirements

```python
def create_annotation(document_id: int, label: str, text: str) -> str:
    """Create a new annotation on the document.

    **Permission Requirements**:
    - User must have WRITE permission on the corpus
    - Tool requires corpus context (requires_corpus=True)
    - Does not require approval (low-risk operation)

    Args:
        document_id: ID of the document to annotate
        label: Annotation label
        text: Text content to annotate

    Returns:
        Success message with annotation ID
    """
    # Implementation
    pass
```

### Testing Permission Enforcement

When testing agents with permission-gated tools:

```python
import pytest
from opencontractserver.llms import agents

@pytest.mark.asyncio
async def test_write_permission_filtering(user_factory, corpus_factory, document_factory):
    # Create user with READ-only permission
    user = await user_factory.create()
    corpus = await corpus_factory.create()
    document = await document_factory.create(corpus=corpus)

    # Grant READ permission only
    await grant_permission(user, corpus, "READ")

    # Create agent with write tools
    agent = await agents.for_document(
        document=document.id,
        corpus=corpus.id,
        user_id=user.id,
        tools=["add_document_note", "update_document_summary"]  # Write tools
    )

    # Verify write tools were filtered
    available_tool_names = [t.name for t in agent.config.tools]
    assert "add_document_note" not in available_tool_names
    assert "update_document_summary" not in available_tool_names

    # Verify read-only tools still work
    response = await agent.chat("What is this document about?")
    assert response.content  # Should succeed with read-only tools
```

### Migration Notes for Existing Tools

If you have existing custom tools that perform write operations:

1. **Add the `requires_write_permission` flag**:
   ```python
   # Update your tool definition
   my_tool = CoreTool.from_function(
       my_function,
       name="my_tool",
       description="Tool description",
       requires_write_permission=True  # ← Add this line
   )
   ```

2. **Test with read-only users**: Verify that users without WRITE permission can still use your agent (without the write tool)

3. **Document the permission requirement**: Update your tool's docstring to note the WRITE permission requirement

---

## Advanced Usage

### Custom Configuration

```python
from opencontractserver.llms.agents.core_agents import AgentConfig

# Create custom configuration
config = AgentConfig(
    model="gpt-4-turbo",
    temperature=0.2,
    max_tokens=2000,
    system_prompt="You are an expert legal analyst...",  # Note: Completely replaces any default prompt
    embedder_path="sentence-transformers/all-MiniLM-L6-v2",
    tools=["load_md_summary", "get_notes_for_document_corpus"], # Ensure tools are appropriate for context
    verbose=True,
    stream_observer=my_observer_function  # Optional: receive nested agent events
)

# Important: Custom system_prompt behavior
# - For chat/stream: Adds context about document analysis
# - For structured_response: Default includes verification steps to prevent hallucination
# - Any custom system_prompt completely replaces these defaults

# The `corpus` parameter is optional for document agents (use None for standalone).
agent = await agents.for_document(document=123, corpus=None, config=config) # Or pass a corpus ID/object when available
```

### Conversation Patterns

#### Multi-turn Analysis

```python
# Persistent conversation for complex analysis
# The `corpus` parameter is optional for document agents (use None for standalone).
agent = await agents.for_document(
    document=123, # Use actual document ID or object
    corpus=1,     # Use actual corpus ID or object
    user_id=456,
    system_prompt="You are analyzing a legal contract. Build context across multiple questions."
)

# Build context over multiple interactions
overview = await agent.chat("Provide an overview of this contract")
risks = await agent.chat("What are the main risks for the buyer?")
recommendations = await agent.chat("Based on our discussion, what are your recommendations?")

# Access full conversation
info = agent.get_conversation_info()
print(f"Analyzed contract in {info['message_count']} messages")
```

#### Anonymous Sessions

```python
# Anonymous sessions - context maintained in memory only
# The `corpus` parameter is required for document agents.
agent = await agents.for_document(document=123, corpus=1)  # No storage, use actual document/corpus IDs
response1 = await agent.chat("What is this document about?")
response2 = await agent.chat("What are the key risks mentioned?")
response3 = await agent.chat("How do these risks compare?")
# Context flows between messages within the same session but is lost when session ends
```

#### Conversation Restoration

```python
# Resume a previous conversation
# The `corpus` parameter is optional for document agents (use None for standalone).
agent = await agents.for_document(
    document=123, # Use actual document ID or object
    corpus=1,     # Use actual corpus ID or object
    user_id=456,
    conversation_id=789  # Resume existing conversation
)

# Continue where you left off
response = await agent.chat("Following up on our previous discussion...")
```

### Advanced Tool Usage

#### Custom Tool Development

```python
from opencontractserver.llms.tools.tool_factory import CoreTool, ToolMetadata
from typing import List, Dict, Any

async def analyze_contract_clauses(document_id: int, clause_types: List[str]) -> Dict[str, Any]:
    """Analyze specific types of clauses in a contract.
    
    Args:
        document_id: The document to analyze
        clause_types: Types of clauses to look for (e.g., ['''payment''', '''termination'''])
    
    Returns:
        Dictionary with clause analysis results
    """
    # Your custom analysis logic here
    # Ensure this tool has access to the document_id context if needed,
    # or adapt it to receive necessary data directly.
    print(f"Analyzing document {document_id} for clauses: {clause_types}")
    return {
        "found_clauses": clause_types,
        "analysis": "Detailed analysis results...",
        "recommendations": ["Recommendation 1", "Recommendation 2"]
    }

# Create tool with rich metadata
clause_tool = CoreTool(
    function=analyze_contract_clauses, # This is an async function
    metadata=ToolMetadata(
        name="analyze_contract_clauses",
        description="Analyze specific types of clauses in a contract",
        parameter_descriptions={
            "document_id": "The ID of the document to analyze", # Agent context usually provides this
            "clause_types": "List of clause types to search for"
        }
    )
)

# Use in agent
# The `corpus` parameter is required for document agents.
agent = await agents.for_document(
    document=123, # Use actual document ID or object
    corpus=1,     # Use actual corpus ID or object
    tools=[clause_tool]
)
```

#### Tool Composition

```python
from opencontractserver.llms.tools import create_document_tools # Assuming this is already imported
# from opencontractserver.llms.tools.tool_factory import CoreTool # For custom_tools if defined elsewhere

# Assume clause_tool, risk_tool, compliance_tool are defined CoreTool instances
# For example:
# risk_tool = CoreTool.from_function(...)
# compliance_tool = CoreTool.from_function(...)

# Combine built-in and custom tools
standard_tools = create_document_tools()
# custom_tools = [clause_tool, risk_tool, compliance_tool] # Ensure these are defined

# The `corpus` parameter is required for document agents.
# agent = await agents.for_document(
#     document=123, # Use actual document ID or object
#     corpus=1,     # Use actual corpus ID or object
#     tools=standard_tools + custom_tools
# )
```

#### Tool Precedence and Overrides

When you pass tools to an agent, **caller-provided tools take precedence** over built-in defaults if there's a name conflict. This allows you to customize tool behavior without modifying the framework.

**When conflicts occur:**
- You pass a tool with `__name__` matching a default tool (e.g., `"update_document_description"`)
- The framework detects the duplicate and uses YOUR tool's configuration

**What gets overridden:**
- Tool description (affects LLM's understanding of the tool)
- `requires_approval` flag (enables/disables human-in-the-loop)
- `parameter_descriptions` (affects LLM parameter usage)
- The actual function implementation

**Example: Disabling approval for a tool**
```python
from opencontractserver.llms.tools.tool_factory import CoreTool
from opencontractserver.llms.tools.core_tools import update_document_description

# Create a version of update_document_description that doesn't require approval
no_approval_tool = CoreTool.from_function(
    update_document_description,
    name="update_document_description",  # Same name as default
    description="Update the document description (auto-approved)",
    requires_approval=False,  # Override the default's requires_approval=True
)

agent = await agents.for_document(
    document=123,
    corpus=1,
    tools=[no_approval_tool],  # Your tool replaces the default
)
# Now update_document_description won't pause for approval
```

**Precedence rules:**
1. Per-call `tools` parameter → highest priority
2. `AgentConfig.tools` → used if no per-call tools
3. Built-in defaults → lowest priority (replaced by above)

**Logging:** When a caller tool overrides a default, an INFO-level log is emitted:
```
Caller tool 'update_document_description' overrides default - using caller's configuration
```

**Security Considerations:**
- Only pass **trusted tools** via the `tools` parameter
- Overriding tools can **bypass `requires_approval` safeguards** that provide human-in-the-loop protection
- If tools originate from user-controlled configurations (e.g., stored in database), **validate them against an approved registry** before passing to agents
- The `deduplicate_tools()` utility in `opencontractserver/utils/tools.py` documents these security implications

### Vector Store Integration

#### Advanced Search

The `CoreAnnotationVectorStore` (which underlies framework-specific stores) allows for rich filtering in `VectorSearchQuery`.

```python
from opencontractserver.llms.vector_stores.core_vector_stores import (
    CoreAnnotationVectorStore, # Typically not instantiated directly by user, but via vector_stores.create()
    VectorSearchQuery
)
# from opencontractserver.llms import vector_stores # For vector_stores.create()

# Example: Creating a store instance (usually done via vector_stores.create())
# store = vector_stores.create(
#     user_id=123,
#     corpus_id=456,
#     embedder_path="sentence-transformers/all-MiniLM-L6-v2" # Handled by config
# )
# For demonstration, let's assume '''store''' is an instance of a CoreAnnotationVectorStore compatible store.

# Complex search with filters
# Available filters include Django ORM lookups on Annotation fields,
# and related fields like '''document__title''', '''annotation_label__name'''.
# Also supports: '''label_id''', '''annotation_type''', '''custom_metadata_filters''' (for JSONField queries),
# and '''text_content_filters'''.
query = VectorSearchQuery(
    query_text="payment obligations and penalties",
    similarity_top_k=20,
    filters={
        "annotation_label__name": "payment_clause", # Filter by label name
        "document__title__icontains": "service_agreement", # Filter by document title
        # "custom_metadata_filters": {"client_id": "XYZ"}, # Example for JSONField
        # "annotation_type": "TYPE_A" # Example for annotation type
    }
)

# results = await store.async_search(query) # Assuming store is available

# Process results
# for result in results:
#     annotation = result.annotation
#     print(f"Document: {annotation.document.title}")
#     print(f"Score: {result.similarity_score:.3f}")
#     print(f"Text: {annotation.raw_text[:200]}...")
#     print("---")
```

#### Framework-Specific Vector Stores

```python
# Custom vector stores can be implemented by extending CoreAnnotationVectorStore
# See opencontractserver/llms/vector_stores/core_vector_stores.py for the interface

# PydanticAI vector store
from opencontractserver.llms.vector_stores.pydantic_ai_vector_stores import PydanticAIAnnotationVectorStore

# pydantic_store = PydanticAIAnnotationVectorStore(
#     user_id=123, # Optional
#     corpus_id=456 # Or document_id
# )

# Both provide the same core functionality (search, async_search)
# with framework-specific optimizations and integration patterns.
# Typically created via opencontractserver.llms.vector_stores.create().
```

### Configuration Reference

The framework uses `AgentConfig` for comprehensive agent configuration. All fields have sensible defaults and can be customized as needed.

#### AgentConfig Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `user_id` | `Optional[int]` | `None` | User ID for conversation persistence; `None` for anonymous sessions |
| `model_name` | `str` | `"gpt-4o-mini"` | LLM model identifier (e.g., "gpt-4", "gpt-4-turbo") |
| `api_key` | `Optional[str]` | `None` | API key for LLM provider (defaults to Django settings) |
| `embedder_path` | `Optional[str]` | `None` | Embedding model path; auto-detected from corpus/document if not specified |
| `similarity_top_k` | `int` | `10` | Number of similar results to retrieve in vector searches |
| `streaming` | `bool` | `True` | Enable/disable streaming responses |
| `verbose` | `bool` | `True` | Enable verbose logging for debugging |
| `system_prompt` | `Optional[str]` | `None` | Custom system prompt; replaces default if provided |
| `temperature` | `float` | `0.7` | LLM temperature (0.0-2.0); lower = more deterministic |
| `max_tokens` | `Optional[int]` | `None` | Maximum tokens in response; `None` uses model default |
| `stream_update_freq` | `int` | `50` | Token interval for database updates during streaming |
| `stream_observer` | `Optional[Callable]` | `None` | Async callback for receiving nested agent events |
| `conversation` | `Optional[Conversation]` | `None` | Existing conversation object to resume |
| `conversation_id` | `Optional[int]` | `None` | ID of conversation to resume |
| `loaded_messages` | `Optional[list[ChatMessage]]` | `None` | Pre-loaded conversation messages |
| `store_user_messages` | `bool` | `True` | Whether to persist user messages to database |
| `store_llm_messages` | `bool` | `True` | Whether to persist LLM responses to database |
| `tools` | `list[Any]` | `[]` | List of tools available to the agent |

#### Usage Examples

```python
from opencontractserver.llms.agents.core_agents import get_default_config, AgentConfig

# Start with defaults
config = get_default_config(
    user_id=123,  # Optional: enables persistence
    model_name="gpt-4-turbo",
    temperature=0.1
)

# Or create custom config from scratch
config = AgentConfig(
    user_id=456,
    model_name="gpt-4",
    temperature=0.2,
    max_tokens=2000,
    system_prompt="You are an expert legal analyst...",
    embedder_path="sentence-transformers/all-MiniLM-L6-v2",
    stream_update_freq=100,  # Update DB every 100 tokens
    tools=["load_md_summary", "similarity_search"],
    verbose=True
)

# Use config with agent
agent = await agents.for_document(document=123, corpus=1, config=config)

# Per-method overrides (don't affect config)
response = await agent.structured_response(
    "Extract dates",
    DateInfo,
    model="gpt-4",  # Override just for this call
    temperature=0.0
)
```

#### Advanced Configuration

```python
# Anonymous agent (no persistence)
anon_config = AgentConfig(
    user_id=None,  # No user = anonymous
    store_user_messages=False,
    store_llm_messages=False
)

# Stream observer for nested visibility
async def event_forwarder(event):
    await websocket.send_json({"type": event.type, "data": event.content})

nested_config = AgentConfig(
    stream_observer=event_forwarder,  # Receives all nested events
    stream_update_freq=25  # More frequent updates
)

# Resume existing conversation
resume_config = AgentConfig(
    user_id=123,
    conversation_id=789,  # Resume this conversation
    temperature=0.5
)
```

## Error Handling

The framework provides structured error handling with specific exception types:

```python
from opencontractserver.llms import agents
from opencontractserver.llms.agents.core_agents import AgentError
# from opencontractserver.documents.models import Document # For Document.DoesNotExist
# from opencontractserver.corpuses.models import Corpus # For Corpus.DoesNotExist

try:
    # The `corpus` parameter is required for document agents.
    agent = await agents.for_document(document=999999, corpus=999) # Assuming these don't exist
    # response = await agent.chat("Analyze this document")
except Document.DoesNotExist:
    print("Document not found")
# except Corpus.DoesNotExist:
#     print("Corpus not found")
except AgentError as e:
    print(f"Agent error: {e}")
except Exception as e:
    print(f"Unexpected error: {e}")

# Graceful handling of LLM errors (example with a hypothetical agent)
# try:
#     response = await agent.chat("Complex query that might fail")
# except Exception as e:
#     # Framework handles LLM errors gracefully
#     print(f"LLM error: {e}")
#     # Conversation state is preserved
```

### Common Error Patterns

```python
# from opencontractserver.documents.models import Document # For Document.DoesNotExist
# from opencontractserver.llms.agents.core_agents import FinalEvent, UnifiedStreamResponse # For streaming errors
# import logging # For logger
# logger = logging.getLogger(__name__)

# Handle missing documents/corpuses
# async def get_agent_for_doc(document_id, corpus_id):
#     try:
#         agent = await agents.for_document(document=document_id, corpus=corpus_id)
#         return agent
#     except Document.DoesNotExist:
#         return {"error": "Document not found"}
#     except Corpus.DoesNotExist:
#         return {"error": "Corpus not found"}


# Handle conversation errors
# async def process_chat(agent, user_message):
#     try:
#         response = await agent.chat(user_message)
#         return response
#     except Exception as e:
#         # Log error but preserve conversation
#         logger.error(f"Chat error: {e}")
#         return {"error": "Failed to process message", "conversation_id": agent.get_conversation_id()}

# Handle streaming errors
# async def stream_message_handler(agent, message):
#     try:
#         async for event in agent.stream(message):
#             yield event
#     except Exception as e:
#         # Send error event based on streaming type
#         if hasattr(agent, '_uses_event_streaming'):  # Event-based streaming
#             # Note: Errors are now handled internally by the framework and
#             # emitted as ErrorEvent objects. This try/except is only needed
#             # for truly unexpected errors outside the agent's control.
#             yield ErrorEvent(
#                 error=str(e),
#                 content=f"Error: {e}",
#                 metadata={"error": str(e), "error_type": type(e).__name__}
#             )
#         else:  # Legacy streaming
#             yield UnifiedStreamResponse(
#                 content=f"Error: {e}",
#                 is_complete=True,
#                 metadata={"error": str(e)}
#             )
```

## Performance Considerations

The framework is designed for production use with several performance optimizations:

### Database Optimization

- **Async ORM**: All database operations use Django's async ORM capabilities.
- **Prefetch Related**: Vector stores prefetch related objects to avoid N+1 queries.
- **Connection Pooling**: Efficient database connection management (handled by Django).
- **Bulk Operations**: Message storage uses bulk operations where possible.

```python
# Example of optimized queryset in CoreAnnotationVectorStore
# from opencontractserver.annotations.models import Annotation
# queryset = Annotation.objects.select_related(
#     '''document''', '''annotation_label'''
# ).prefetch_related(
#     '''document__doc_type''' # Example of prefetching deeper relation
# ).filter(...)
```

### Caching Strategy

- **Embedding Caching**: Vector embeddings can be cached to avoid recomputation (implementation specific, may depend on embedder).
- **Model Caching**: LLM models are cached and reused across requests (handled by the underlying framework).
- **Vector Store Caching**: Search results can be cached for repeated queries (application-level or via custom store decorators).

### Memory Management

- **Streaming Responses**: Large responses are streamed to avoid memory issues.
- **Lazy Loading**: Django models use lazy loading for related objects unless explicitly prefetched.
- **Context Windows**: Conversation context is managed within model limits by the agent implementations.

### Source Management

- **Consistent Serialization**: Sources use a unified format across database storage and WebSocket transmission to eliminate conversion overhead.
- **Metadata Flattening**: Source metadata is flattened to top-level fields for efficient access and reduced nesting.
- **Similarity Scores**: All sources include similarity scores for relevance ranking and filtering.
- **Lazy Source Loading**: Sources are only populated when complete responses are available (final streaming chunk).

### Concurrency

- **Async Throughout**: All core operations are async-compatible.
- **Connection Limits**: Proper database connection pooling prevents resource exhaustion.
- **Rate Limiting**: Consider implementing rate limiting at the application or API gateway level for external LLM APIs.

```python
# Example of concurrent agent usage
import asyncio

# async def analyze_documents_concurrently(document_corpus_pairs): # List of (doc_id, corpus_id) tuples
#     agents_list = []
#     for doc_id, corpus_id in document_corpus_pairs:
#         agent = await agents.for_document(document=doc_id, corpus=corpus_id)
#         agents_list.append(agent)
    
#     tasks = [
#         agent.chat("Summarize key points")
#         for agent in agents_list
#     ]
    
#     results = await asyncio.gather(*tasks)
#     return results
```

## Testing

The framework includes comprehensive test coverage:

```python
# Example test patterns
import pytest
from opencontractserver.llms import agents
from opencontractserver.llms.agents.core_agents import UnifiedChatResponse
# from opencontractserver.documents.models import Document # For test setup
# from opencontractserver.corpuses.models import Corpus # For test setup

@pytest.mark.asyncio
async def test_document_agent_chat(db, document_factory, corpus_factory): # Assuming db and factories for setup
    # test_corpus = await corpus_factory.create()
    # test_document = await document_factory.create(corpus=test_corpus)
    # agent = await agents.for_document(document=test_document.id, corpus=test_corpus.id)
    # response = await agent.chat("Test message")
    
    # assert isinstance(response, UnifiedChatResponse)
    # assert response.content
    # assert response.user_message_id
    # assert response.llm_message_id
    pass # Placeholder for actual test structure

@pytest.mark.asyncio
async def test_conversation_persistence(db, document_factory, corpus_factory, user_factory): # Assuming factories
    # test_user = await user_factory.create()
    # test_corpus = await corpus_factory.create()
    # test_document = await document_factory.create(corpus=test_corpus)
    # agent = await agents.for_document(
    #     document=test_document.id,
    #     corpus=test_corpus.id,
    #     user_id=test_user.id
    # )
    
    # response1 = await agent.chat("First message")
    # response2 = await agent.chat("Second message")
    
    # # Verify conversation continuity via agent method
    # assert agent.get_conversation_id() is not None
    
    # # Verify message storage
    # info = agent.get_conversation_info()
    # assert info is not None
    # assert info.get('''message_count''', 0) >= 4  # 2 user + 2 LLM messages
    pass # Placeholder for actual test structure

@pytest.mark.asyncio
async def test_structured_response(db, document_factory, corpus_factory): # Assuming factories
    # from pydantic import BaseModel, Field
    # 
    # class ContractDates(BaseModel):
    #     effective_date: str = Field(description="Effective date")
    #     expiration_date: str = Field(description="Expiration date")
    # 
    # test_corpus = await corpus_factory.create()
    # test_document = await document_factory.create(corpus=test_corpus)
    # agent = await agents.for_document(
    #     document=test_document.id,
    #     corpus=test_corpus.id
    # )
    # 
    # # Test structured extraction
    # result = await agent.structured_response(
    #     "Extract the contract dates",
    #     ContractDates
    # )
    # 
    # # Verify result
    # assert result is None or isinstance(result, ContractDates)
    # if result:
    #     assert result.effective_date  # Required field
    # 
    # # Verify no conversation persistence
    # assert agent.get_conversation_id() is None  # Anonymous agent
    pass # Placeholder for actual test structure
```

## Contributing

The framework is designed for extensibility. Here's how to contribute:

### Adding Core Functionality

1. **Core Logic**: Add to `core_*.py` modules (e.g., `agents/core_agents.py`, `tools/core_tools.py`).
2. **Framework Adapters**: Create new adapter in `agents/` (see "Adding a New Framework" below).
3. **Tools**: Add to `tools/core_tools.py` for general tools, or within framework adapters for framework-specific tool handling. Ensure async versions are provided where appropriate.
4. **API**: Extend `api.py` for new high-level functionality if needed (e.g., new API classes like `AgentAPI`, `ToolAPI`).

### Adding a New Framework

To add support for a new LLM framework (e.g., LangChain, Haystack):

1. **Add Framework Enum**:
   ```python
   # In types.py
   class AgentFramework(Enum):
       PYDANTIC_AI = "pydantic_ai"
       LANGCHAIN = "langchain"  # New framework
   ```

2. **Implement Agent Adapters**:
   - Create `agents/langchain_agents.py`
   - Inside this file, define classes for your document and/or corpus agents. These classes **must** inherit from `CoreAgentBase` (from `opencontractserver.llms.agents.core_agents.py`).
   
   ```python
   # agents/langchain_agents.py
   from typing import AsyncGenerator, Type, TypeVar, Optional # For Python < 3.9, else from collections.abc import AsyncGenerator
   from opencontractserver.llms.agents.core_agents import (
       CoreAgentBase, SourceNode, AgentConfig, 
       UnifiedStreamEvent, ThoughtEvent, ContentEvent, FinalEvent
    )
   
   T = TypeVar("T")
    # from opencontractserver.documents.models import Document
    # from opencontractserver.corpuses.models import Corpus

    class LangChainDocumentAgent(CoreAgentBase):
        # def __init__(self, config: AgentConfig, conversation_manager: CoreConversationManager, underlying_agent: Any):
        #     super().__init__(config, conversation_manager)
        #     self.underlying_agent = underlying_agent
        pass # Simplified for brevity
        
        @classmethod
        async def create(
            cls, 
            # document: Document, 
            # corpus: Corpus, 
            config: AgentConfig, 
            conversation_manager: CoreConversationManager,
            tools: list = None
        ): # -> "LangChainDocumentAgent":
            # Initialize your LangChain agent here (e.g., langchain_agent = ...)
            # return cls(config, conversation_manager, langchain_agent)
            pass
        
        async def _chat_raw(self, message: str, **kwargs) -> tuple[str, list[SourceNode], dict]:
            # Implement raw chat using your framework (no DB operations)
            # Return tuple of (content, sources, metadata)
            # CoreAgentBase will handle all message storage automatically
            pass
        
        async def _stream_raw(self, message: str, **kwargs) -> AsyncGenerator[UnifiedStreamEvent, None]:
            # Implement raw streaming using your framework (no DB operations)
            # Yield UnifiedStreamEvent objects (ThoughtEvent, ContentEvent, etc.)
            # CoreAgentBase wrapper will handle message storage and incremental updates automatically
            # Call self._emit_observer_event(event) to forward events to any configured observer
            pass
        
        async def _structured_response_raw(
            self, 
            prompt: str, 
            target_type: Type[T],
            *,
            system_prompt: Optional[str] = None,
            model: Optional[str] = None,
            tools: Optional[list] = None,
            temperature: Optional[float] = None,
            max_tokens: Optional[int] = None,
            **kwargs
        ) -> Optional[T]:
            # Implement structured data extraction using your framework
            # Return instance of target_type or None on failure
            # No DB operations - this is ephemeral extraction
            pass
    ```

3. **Integrate into `UnifiedAgentFactory`**:
   ```python
   # In agents/agent_factory.py
   # elif framework == AgentFramework.LANGCHAIN:
   #     from opencontractserver.llms.agents.langchain_agents import LangChainDocumentAgent # Or CorpusAgent
   #     if for_document:
   #         return await LangChainDocumentAgent.create(
   #             document=document_obj, # Ensure document_obj and corpus_obj are passed
   #             corpus=corpus_obj,
   #             config=config,
   #             conversation_manager=conversation_manager,
   #             tools=framework_tools
   #         )
   #     else: # for_corpus
   #         # return await LangChainCorpusAgent.create(...)
   #         pass
   pass # Simplified
   ```

4. **Add Tool Support**:
   - Create `tools/langchain_tools.py` if needed.
   - Implement tool conversion from `CoreTool` to your framework's tool format.
   - Update `tools/tool_factory.py` (`UnifiedToolFactory`) to handle the new framework.

5. **Add Vector Store Support**:
   - Create `vector_stores/langchain_vector_stores.py`.
   - Implement adapter around `CoreAnnotationVectorStore` or a new core store if needed.
   - Update `vector_stores/vector_store_factory.py`.

6. **Testing**:
   - Create comprehensive tests following the patterns in existing test files (e.g., `test_pydantic_ai_agents.py`).
   - Test the public `chat()`, `stream()`, and `structured_response()` methods (which are provided by `CoreAgentBase`), conversation management, tool usage, and error handling.
   - Note that `_chat_raw()`, `_stream_raw()`, and `_structured_response_raw()` methods are internal implementation details and typically don't require separate testing—the public API tests exercise them indirectly.

By following these steps, you can extend the OpenContracts LLM framework to support new LLM technologies while maintaining the consistent, rich API with conversation management, source tracking, and structured responses.

### Code Style Guidelines

- **Type Hints**: All functions must have complete type hints.
- **Docstrings**: Use Google-style docstrings for all public methods.
- **Async/Await**: Use async patterns consistently throughout. Core functionalities should be async-first.
- **Error Handling**: Provide meaningful error messages and proper exception handling.
- **Testing**: Include comprehensive tests for all new functionality.

### Documentation Standards

- **API Documentation**: Document all public interfaces with examples.
- **Architecture Decisions**: Document significant design choices.
- **Migration Guides**: Provide migration paths for breaking changes.
- **Performance Notes**: Document performance characteristics and limitations.

### Event-Based Streaming Architecture

The framework's event-based streaming (available in PydanticAI) provides unprecedented visibility into agent execution:

```
User Query → PydanticAI Agent → Execution Graph Stream
                    ↓
┌─────────────────────────────────────────────────────┐
│ ThoughtEvent: "Received user prompt..."            │
├─────────────────────────────────────────────────────┤
│ ThoughtEvent: "Sending request to language model…" │
├─────────────────────────────────────────────────────┤
│ ContentEvent: "Based on the"                       │
│ ContentEvent: " contract analysis"                 │
│ ContentEvent: "..."                                │
├─────────────────────────────────────────────────────┤
│ ThoughtEvent: "Calling tool similarity_search(...)"│
│ SourceEvent: [SourceNode, SourceNode, ...]         │
│ ThoughtEvent: "Tool returned result"               │
├─────────────────────────────────────────────────────┤
│ FinalEvent: Complete answer + all sources + usage  │
└─────────────────────────────────────────────────────┘
                    ↓
           WebSocket Consumer
                    ↓
              Frontend UI
```

#### Event Types Detail

| Event Type | Purpose | Fields | When Emitted |
|------------|---------|--------|--------------|
| `ThoughtEvent` | Agent reasoning steps | `thought`, `metadata` | Execution graph transitions, tool decisions |
| `ContentEvent` | Answer content deltas | `content`, `accumulated_content`, `metadata` | Model text generation |
| `SourceEvent` | Source discovery | `sources`, `metadata` | Vector search results |
| `ApprovalNeededEvent` | Tool approval required | `pending_tool_call`, `metadata` | Flagged tool execution paused |
| `ApprovalResultEvent` | Approval decision recorded | `decision`, `pending_tool_call`, `metadata` | After resume_with_approval() called |
| `ResumeEvent` | Execution restarting | Standard event fields | After approval, before tool runs |
| `FinalEvent` | Complete results | `accumulated_content`, `sources`, `metadata` | End of execution |
| `ErrorEvent` | Error occurred during execution | `error`, `metadata` | Unrecoverable errors (e.g., rate limits, API failures) |

#### Implementation Benefits

- **Real-time Debugging**: See exactly where agents get stuck or make wrong decisions
- **Rich UI/UX**: Build sophisticated interfaces showing agent "thinking"
- **Performance Monitoring**: Track tool usage, token consumption, and execution time
- **Audit Trails**: Complete visibility into agent decision-making process

```python
# Example: Building a debug UI
async for event in agent.stream("Complex legal analysis"):
    timestamp = time.time()
    
    if event.type == "thought":
        debug_panel.add_thought(timestamp, event.thought, event.metadata)
    elif event.type == "content":
        answer_panel.append_text(event.content)
    elif event.type == "sources":
        source_panel.update_sources(event.sources)
    elif event.type == "approval_needed":
        # Human-in-the-loop: pause execution, request approval
        approval_panel.show_approval_request(
            tool_name=event.pending_tool_call["name"],
            tool_args=event.pending_tool_call["arguments"],
            message_id=event.llm_message_id
        )
        # UI triggers approval flow, which calls resume_with_approval()
    elif event.type == "final":
        debug_panel.add_summary(timestamp, event.metadata)
        performance_monitor.log_usage(event.metadata.get("usage", {}))
```

---

## Recent Improvements (v0.10+)

### Critical API Fixes
- **Fixed pydantic_ai Integration**: Corrected API usage to match pydantic_ai's actual interface
  - Changed `result_type` → `output_type` in Agent initialization
  - Changed `run_result.data` → `run_result.output` for accessing results
  - Framework now properly uses pydantic_ai's documented API

### Source Handling Enhancements
- **Automatic `json` Field Generation**: `SourceNode.to_dict()` now intelligently constructs coordinate information
  - **PDF Sources**: Automatically includes full `MultipageAnnotationJson` with token positions and bounding boxes from PlasmaPDF
  - **Text Sources**: Automatically generates simple `{start, end}` format from character positions
  - **Tool Simplification**: Tools only need to store raw metadata (`annotation_json`, `char_start`, `char_end`); transformation happens automatically
  - **Frontend Compatibility**: Ensures all sources have the `json` field required by frontend TypeScript interfaces
  - **Exact Text Search**: Fixed issue where exact text search sources weren't displaying in frontend
  - **Centralized Logic**: Single transformation point prevents duplication and ensures consistency across all source types

### Performance Optimizations
- **Simplified Structured Extraction**: Removed 200+ lines of complex prompt engineering
  - Leverages pydantic_ai's automatic output strategy selection
  - Framework automatically chooses between tool calling, JSON mode, or prompted extraction
  - Reduced token usage by eliminating repetitive instruction blocks
  - More reliable extraction with model-specific optimizations

### Code Quality Improvements
- **Cleaner Architecture**: Removed unnecessary complexity from structured extraction
- **Better Maintainability**: Aligned with pydantic_ai best practices
- **Future-proof Design**: Will automatically benefit from pydantic_ai improvements

### Migration Notes
If you were using the framework before these fixes, no changes are needed to your code. The improvements are internal optimizations that maintain the same public API while providing better reliability and performance. Sources now automatically include properly formatted coordinate information for both PDF and text documents.

---

This framework represents the evolution of OpenContracts' LLM capabilities, providing a foundation for sophisticated document analysis while maintaining simplicity and elegance in its API design.

---

### Standalone Document Agents (corpus=None)

Document agents now support a corpus-less mode by passing `corpus=None`.

- **When to use**: Analyze a single document outside any corpus context, or when a corpus has not (yet) been created.
- **Tool availability**: Tools marked with `requires_corpus=True` are automatically filtered out. Core tools like `load_document_md_summary`, `get_md_summary_token_length`, `load_document_txt_extract`, and vector search remain available.
- **Embedder selection**: If the document already has structural annotation embeddings, the framework prefers that embedder. Otherwise, it falls back to `settings.DEFAULT_EMBEDDER`.
- **Vector search**: Uses a document-level vector store (no `corpus_id` required) as long as an `embedder_path` is known.
- **Conversations**:
  - Authenticated users get normal conversation persistence and can resume later (via `conversation_id`).
  - Anonymous users create ephemeral sessions (no database writes, `get_conversation_id()` returns `None`).

Example:

```python
from opencontractserver.llms import agents

# Standalone document chat (no corpus) – corpus-dependent tools are filtered automatically
agent = await agents.for_document(document=123, corpus=None)

async for ev in agent.stream("Summarize the main points"):
    if ev.type == "content":
        print(ev.content, end="")
    elif ev.type == "final":
        print("\nDone. Sources:", len(ev.sources))
```

Notes:
- `get_document_summary` automatically falls back to loading the document’s markdown summary when no corpus is present.
- You can still supply custom tools; anything tagged `requires_corpus=True` is omitted gracefully.

---

### Default Tool Reference

| Tool Name | Short Description | Requires Approval | Requires Corpus |
|-----------|------------------|-------------------|-----------------|
| similarity_search | Semantic vector search for relevant passages in the **current document** | No | No (document-level store) |
| load_md_summary \| load_document_md_summary | Load markdown summary of the document | No | No |
| get_md_summary_token_length | Approximate token length of markdown summary | No | No |
| get_document_text_length | Get total character length of plain-text extract | No | No |
| load_document_text \| load_document_txt_extract | Load full or partial plain-text extract (params: start, end, refresh) | No | No |
| get_notes_for_document_corpus | Retrieve notes attached to document *within the active corpus* | No | Yes |
| get_note_content_token_length | Token length of a single note | No | Yes |
| get_partial_note_content | Slice a note's content (start/end) | No | Yes |
| search_document_notes | Search notes for a keyword | No | Yes |
| add_document_note | Create a new note for the document | **Yes** | Yes |
| update_document_note | Update an existing note (new revision) | **Yes** | Yes |
| duplicate_annotations | Duplicate annotations with a new label | **Yes** | Yes |
| add_exact_string_annotations | Add annotations for exact string matches | **Yes** | Yes |
| get_document_summary | Get latest markdown summary content | No | Yes |
| get_document_summary_versions | Version history of document summary | No | Yes |
| get_document_summary_diff | Unified diff between two summary versions | No | Yes |
| update_document_summary | Create / update document summary | **Yes** | Yes |
| get_corpus_description | Retrieve corpus markdown description | No | Yes (corpus agents) |
| update_corpus_description | Update corpus description | No | Yes |
| list_documents | List documents in the current corpus | No | Yes |
| ask_document | Ask a nested question to a document agent | No | Yes |

**Legend**  
• **Requires Approval**: Tool execution pauses until a human approves the call.  
• **Requires Corpus**: Tool is automatically filtered when `corpus=None`.

> **Note**: You can create your own tools with `CoreTool.from_function(...)` and set `requires_approval=True` or `requires_corpus=True` as needed. The framework will enforce approval gates and automatic corpus filtering for you.