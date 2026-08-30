# Agent-Based Corpus Actions

## Overview

This document describes the third type of corpus action: agent-based actions that invoke an AI agent with a prompt and pre-authorized tools. This extends the existing corpus action system (which supports fieldsets and analyzers) to enable intelligent, automated document processing.

**Status**: Implemented in v3.0.0
**Last Updated**: 2026-01-09

## Use Cases

1. **Auto-update Document Summary**: When a document is added, analyze it and create/update the summary
2. **Auto-annotate Key Clauses**: Find and annotate specific clause types (indemnification, termination, etc.)
3. **Auto-tag Documents**: Analyze content and add appropriate tags/labels
4. **Extract Metadata**: Pull out key dates, parties, values into custom_meta
5. **Quality Checks**: Verify document completeness or flag issues

## Versioning Safety

**Critical**: All agent operations must respect the Document versioning architecture (see `docs/architecture/document_versioning.md`).

### Safe Operations (No Document Version Created)
| Tool/Operation | Target | Why Safe |
|---------------|--------|----------|
| `update_document_summary` | DocumentSummaryRevision | Separate append-only model |
| Update `description` | Document.description | Metadata field, no hash change |
| Update `title` | Document.title | Metadata field, no hash change |
| Update `custom_meta` | Document.custom_meta | JSON field, no hash change |
| Create annotations | Annotation model | Separate model |
| Create notes | Note model | Separate model |

### Unsafe Operations (Avoid in Corpus Actions)
- Uploading/replacing PDF file (changes `pdf_file_hash`)
- Any operation that modifies document content

---

## Model Implementation

### 1. CorpusAction Model Extension

The `CorpusAction` model has been extended to support agent-based actions.

**Source**: [`opencontractserver/corpuses/models.py`](../../opencontractserver/corpuses/models.py) (lines 830-942)

Key fields added:
- `agent_config` - ForeignKey to `AgentConfiguration`
- `task_instructions` - Task-specific prompt for the agent
- `pre_authorized_tools` - JSON list of tools pre-authorized to run without approval

Database constraint ensures exactly ONE of `fieldset`, `analyzer`, or `agent_config` is set.

### 2. AgentActionResult Model

Stores results from agent-based corpus actions.

**Source**: [`opencontractserver/agents/models.py`](../../opencontractserver/agents/models.py) (lines 223-379)

Key fields:
- `corpus_action` - ForeignKey to the triggering CorpusAction
- `document` - ForeignKey to the processed document (nullable for thread-based actions)
- `triggering_conversation` / `triggering_message` - For thread/message triggers
- `status` - Execution status (PENDING, RUNNING, COMPLETED, FAILED)
- `agent_response` - Final response content from the agent
- `execution_metadata` - JSON with model used, token counts, etc.

---

## Task Implementation

### Celery Tasks

**Source**: [`opencontractserver/tasks/agent_tasks.py`](../../opencontractserver/tasks/agent_tasks.py)

#### Document-based Actions: `run_agent_corpus_action`

- Celery task that executes agent-based corpus actions on documents
- Uses `asyncio.run()` to invoke async agent API
- Creates/updates `AgentActionResult` records for tracking
- Implements idempotency (skips already-completed or running tasks)
- Handles race conditions with `select_for_update()`
- Links to `CorpusActionExecution` for unified tracking

#### Thread-based Actions: `run_agent_thread_action`

- Handles `NEW_THREAD` and `NEW_MESSAGE` triggers
- Builds context from thread/message content
- Automatically includes moderation tools

### Integration with process_corpus_action

**Source**: [`opencontractserver/tasks/corpus_tasks.py`](../../opencontractserver/tasks/corpus_tasks.py) (lines 146-354)

The `process_corpus_action` task dispatches to the appropriate handler:
- `action.fieldset` → Fieldset extraction tasks
- `action.analyzer` → Analyzer tasks
- `action.agent_config` → `run_agent_corpus_action` or `run_agent_thread_action`

---

## Agent Factory Changes

### Skip Approval Gate Support

The agent factory (`opencontractserver/llms/api.py`) supports `skip_approval_gate` parameter for automated corpus actions. When enabled, all tools run without requiring user approval.

**Key Integration Points**:
- `agents.for_document()` - Pass `skip_approval_gate=True` for automated execution
- `agents.for_corpus()` - Same parameter for corpus-level agents

The agent task implementation sets `skip_approval_gate=True` when invoking agents for corpus actions to enable fully automated execution.

---

## GraphQL API

### Mutations

**Source**: [`config/graphql/mutations.py`](../../config/graphql/mutations.py)

#### CreateCorpusAction

Extended to support agent-based actions:
- `agent_config_id` - ID of the agent configuration to use
- `task_instructions` - Task prompt for the agent
- `pre_authorized_tools` - List of tool names pre-authorized for execution
- `create_agent_inline` - Create a new corpus-scoped agent inline (for thread/message triggers)

#### UpdateCorpusAction

Supports updating all agent-specific fields including trigger type, agent config, and prompt.

### Types

**Source**: [`config/graphql/graphene_types.py`](../../config/graphql/graphene_types.py)

#### CorpusActionType (lines 1958-1979)

Exposes agent-related fields:
- `agent_config` - The linked AgentConfiguration
- `task_instructions` - Task prompt
- `pre_authorized_tools` - List of pre-authorized tool names

#### AgentActionResultType (lines 1982-2015)

Exposes execution results:
- `tools_executed` - List of tools executed with results
- `execution_metadata` - Model, tokens, timing info
- `duration_seconds` - Computed execution duration

### Queries

**Source**: [`config/graphql/queries.py`](../../config/graphql/queries.py) (lines 2477-2523)

`agent_action_results` - Query agent action results with filters:
- `corpus_action_id` - Filter by corpus action
- `document_id` - Filter by document
- `status` - Filter by execution status

Uses `AgentActionResult.objects.visible_to_user()` for permission filtering.

---

## Example Usage

### Creating an Auto-Summary Action

```graphql
mutation CreateAutoSummaryAction {
  create_corpus_action(
    corpusId: "Q29ycHVzVHlwZTox"
    trigger: "add_document"
    name: "Auto-Generate Summary"
    agentConfigId: "QWdlbnRDb25maWd1cmF0aW9uVHlwZTox"
    taskInstructions: """
      Analyze this document and create a comprehensive summary.

      1. Use load_document_text to read the full content
      2. Identify the document type, key parties, and main topics
      3. Use update_document_summary to save a 3-5 sentence summary

      Focus on: document purpose, key terms, important dates, and parties involved.
    """
    preAuthorizedTools: ["load_document_text", "load_document_summary", "update_document_summary"]
  ) {
    ok
    message
    obj {
      id
      name
      taskInstructions
      preAuthorizedTools
    }
  }
}
```

### Querying Action Results

```graphql
query GetActionResults($corpusActionId: ID!) {
  agent_action_results(corpusActionId: $corpusActionId) {
    edges {
      node {
        id
        document {
          id
          title
        }
        status
        agentResponse
        toolsExecuted
        startedAt
        completedAt
        errorMessage
      }
    }
  }
}
```

---

## Implementation Status

| Phase | Component | Status |
|-------|-----------|--------|
| 1 | CorpusAction model extension | ✅ Complete |
| 1 | AgentActionResult model | ✅ Complete |
| 1 | Database migrations | ✅ Complete |
| 2 | `skip_approval_gate` in agent factory | ✅ Complete |
| 2 | `run_agent_corpus_action` task | ✅ Complete |
| 2 | `run_agent_thread_action` task | ✅ Complete |
| 2 | Integration with `process_corpus_action` | ✅ Complete |
| 2 | Deferred action architecture | ✅ Complete |
| 3 | CreateCorpusAction mutation extended | ✅ Complete |
| 3 | UpdateCorpusAction mutation | ✅ Complete |
| 3 | AgentActionResultType | ✅ Complete |
| 3 | GraphQL queries for results | ✅ Complete |
| 4 | CorpusSettings UI for agent actions | ✅ Complete |
| 4 | Corpus agent management UI | ✅ Complete |
| 4 | Pre-authorized tools selector | ✅ Complete |
| 5 | Unit tests for models | ✅ Complete |
| 5 | Integration tests for task execution | ✅ Complete |
| 5 | Corpus document action tests | ✅ Complete |

### Key Source Files

| Category | File |
|----------|------|
| **Models** | [`opencontractserver/corpuses/models.py`](../../opencontractserver/corpuses/models.py) - CorpusAction, CorpusActionExecution |
| **Models** | [`opencontractserver/agents/models.py`](../../opencontractserver/agents/models.py) - AgentActionResult |
| **Tasks** | [`opencontractserver/tasks/agent_tasks.py`](../../opencontractserver/tasks/agent_tasks.py) - Agent execution tasks |
| **Tasks** | [`opencontractserver/tasks/corpus_tasks.py`](../../opencontractserver/tasks/corpus_tasks.py) - Action dispatch |
| **Tasks** | [`opencontractserver/tasks/doc_tasks.py`](../../opencontractserver/tasks/doc_tasks.py) - Document unlock triggers |
| **GraphQL** | [`config/graphql/graphene_types.py`](../../config/graphql/graphene_types.py) - CorpusActionType, AgentActionResultType |
| **GraphQL** | [`config/graphql/mutations.py`](../../config/graphql/mutations.py) - CreateCorpusAction, UpdateCorpusAction |
| **GraphQL** | [`config/graphql/queries.py`](../../config/graphql/queries.py) - agent_action_results query |
| **Frontend** | [`frontend/src/components/corpuses/CorpusAgentManagement.tsx`](../../frontend/src/components/corpuses/CorpusAgentManagement.tsx) |
| **Tests** | [`opencontractserver/tests/test_agent_corpus_action_task.py`](../../opencontractserver/tests/test_agent_corpus_action_task.py) |
| **Tests** | [`opencontractserver/tests/test_corpus_document_actions.py`](../../opencontractserver/tests/test_corpus_document_actions.py) |

---

## Security Considerations

1. **Tool Pre-Authorization**: Only corpus owners can create actions with pre-authorized tools
2. **Permission Inheritance**: Actions inherit corpus permissions
3. **Audit Trail**: All executions are logged via AgentActionResult model
4. **Tool Filtering**: Public corpuses cannot use approval-gated tools (even if pre-authorized)
5. **Rate Limiting**: Celery task queue provides natural rate limiting; additional limits can be configured

---

## Deferred Action Architecture

### Problem

Corpus actions (including agent-based ones) need access to fully processed document content.
When a document is uploaded, it goes through a processing pipeline:

1. **Thumbnail extraction** - Generate preview image
2. **Document ingestion** - Parse PDF, extract text, create PAWLs layers
3. **Unlock document** - Set `backend_lock=False`, `processing_finished=now()`

If corpus actions fire immediately when a document is added to a corpus,
agent tools like `load_document_text` may fail because the document isn't fully parsed yet.

### Solution: Direct Invocation with DocumentPath as Source of Truth

We use direct invocation from the document lifecycle methods, with `DocumentPath` as the
source of truth for corpus membership (not the M2M relationship):

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        DOCUMENT UPLOAD FLOW                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Document Created                                                            │
│       │                                                                      │
│       ▼                                                                      │
│  backend_lock = True ──────────────────┐                                    │
│       │                                │                                    │
│       ▼                                │                                    │
│  add_document() / import_document()    │                                    │
│       │                                │                                    │
│       ▼                                │                                    │
│  Create DocumentPath                   │                                    │
│       │                                │                                    │
│       ▼                                │                                    │
│  Check backend_lock                    │                                    │
│       │                                │                                    │
│  ┌────┴────┐                          │                                    │
│  │         │                          │                                    │
│  ▼         ▼                          │                                    │
│ TRUE     FALSE                        │ Processing Pipeline                │
│  │         │                          │ (thumbnail, parse, embed)          │
│  │         ▼                          │         │                          │
│  │    process_corpus_action           │         │                          │
│  │    triggered directly              │         ▼                          │
│  │                                    └──► set_doc_lock_state(False)       │
│  │                                              │                          │
│  │                                              ▼                          │
│  │                                    Query DocumentPath for corpuses      │
│  │                                              │                          │
│  │                                              ▼                          │
│  └──────────────────────────────────────► process_corpus_action            │
│                                         for each corpus                     │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Why DocumentPath Instead of M2M?

The document versioning architecture (Issue #654) introduced `DocumentPath` as the source
of truth for corpus-document relationships. The M2M relationship (`Corpus.documents`) has
been **completely removed** (Issue #835, migration `0039_remove_corpus_documents_m2m`).

Using DocumentPath ensures:
- `import_document()` works correctly (it creates DocumentPath but not M2M)
- Soft-deleted documents are properly excluded (`is_deleted=False`)
- Only current paths are considered (`is_current=True`)

### Implementation Details

#### Direct Trigger: add_document()

**Source**: [`opencontractserver/corpuses/models.py`](../../opencontractserver/corpuses/models.py) (lines 443-624)

The `Corpus.add_document()` method triggers corpus actions directly if the document is ready (`backend_lock=False`). If the document is still processing, actions are deferred to `set_doc_lock_state()`.

#### Direct Trigger: import_document()

**Source**: [`opencontractserver/documents/versioning.py`](../../opencontractserver/documents/versioning.py)

Same pattern as `add_document()` - triggers actions directly if document is ready.

#### Direct Trigger: set_doc_lock_state()

**Source**: [`opencontractserver/tasks/doc_tasks.py`](../../opencontractserver/tasks/doc_tasks.py) (lines 60-118)

When a document is unlocked (`locked=False`), this task:
1. Updates the document's `backend_lock` and `processing_finished` fields
2. Queries `DocumentPath` to find all corpuses the document belongs to
3. Triggers `process_corpus_action` for each corpus
4. Creates `DOCUMENT_PROCESSED` notifications for the document creator and corpus owners

### Behavior Matrix

| Scenario | add_document/import_document | set_doc_lock_state |
|----------|------------------------------|-------------------|
| New doc uploaded to corpus | Skipped (locked) | Triggers actions via DocumentPath |
| Existing processed doc added | Triggers immediately | N/A (already unlocked) |
| Doc in multiple corpuses | N/A | Triggers for ALL corpuses |
| Doc not in any corpus | N/A | No action (no DocumentPath records) |
| Soft-deleted doc | N/A | Ignored (is_deleted=True) |

### Idempotency Requirements

**Important**: Corpus actions SHOULD be designed to be idempotent. Due to the deferred execution
architecture, the same action may be triggered multiple times for the same document in edge cases:

1. Document added to corpus while still processing → triggers via `set_doc_lock_state`
2. Document later re-added or corpus action re-run → may trigger again

Most built-in corpus actions are idempotent by design:

- **Fieldset extractions**: Use `Extract.objects.get_or_create()`
- **Analyzers**: Create Analysis objects (tracked via CorpusAction)
- **Agent actions**: Use `AgentActionResult.objects.get_or_create()` - skips if already completed

**Recommendations for custom agent prompts**:

1. **Check before creating**: Use tools like `load_document_summary` to check if work already exists
2. **Update rather than duplicate**: Use `update_document_summary` which overwrites, not appends
3. **Idempotent annotations**: Agent should check for existing annotations before creating new ones

If stricter duplicate prevention is needed, actions can check for existing results before execution.

### Testing

#### Corpus Document Actions

**Source**: [`opencontractserver/tests/test_corpus_document_actions.py`](../../opencontractserver/tests/test_corpus_document_actions.py)

Tests covering the deferred action architecture:
- `test_add_document_triggers_actions_for_ready_doc` - Ready docs trigger immediately
- `test_add_document_skips_actions_for_locked_doc` - Locked docs deferred to set_doc_lock_state
- `test_set_doc_lock_state_triggers_actions_via_document_path` - DocumentPath used as source of truth
- `test_set_doc_lock_state_no_corpus_no_action` - Orphan docs ignored
- `test_set_doc_lock_state_triggers_for_multiple_corpuses` - Multi-corpus support
- `test_set_doc_lock_state_ignores_deleted_paths` - Soft-deleted paths excluded

#### Agent Corpus Action Task

**Source**: [`opencontractserver/tests/test_agent_corpus_action_task.py`](../../opencontractserver/tests/test_agent_corpus_action_task.py)

Tests covering agent task execution:
- `test_successful_execution_creates_result` - Result creation on success
- `test_skip_already_completed_result` - Idempotency for completed results
- `test_skip_already_running_result` - Race condition prevention
- `test_retry_failed_result` - Failed results can be retried
- `test_agent_failure_marks_result_failed` - Error handling
- `test_long_error_message_truncated` - Error message truncation
- `test_execution_tracking_on_success` - CorpusActionExecution integration

---

## Related Documentation

- [Corpus Actions Intro](../corpus_actions/intro_to_corpus_actions.md)
- [Document Versioning](./document_versioning.md)
- [Agent Framework](llms/README.md)
- [Permissioning Guide](../permissioning/consolidated_permissioning_guide.md)
