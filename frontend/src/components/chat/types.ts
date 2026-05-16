import { MultipageAnnotationJson } from "../types";
import { TimelineEntry } from "../widgets/chat/ChatMessage";

/**
 * Properties of source annotation data included in websocket messages.
 */
export interface WebSocketSources {
  page: number;
  json: { start: number; end: number } | MultipageAnnotationJson;
  annotation_id: number;
  label: string;
  label_id: number;
  rawText: string;
  /** Document ID this source belongs to (provided by backend SourceNode metadata) */
  document_id?: number;
}

/**
 * Full websocket message structure for chat streaming.
 * Covers async streaming (ASYNC_START/CONTENT/FINISH), synchronous messages,
 * agent thoughts, source citations, and approval gates.
 */
export interface MessageData {
  type:
    | "ASYNC_START"
    | "ASYNC_CONTENT"
    | "ASYNC_FINISH"
    | "SYNC_CONTENT"
    | "ASYNC_THOUGHT"
    | "ASYNC_SOURCES"
    | "ASYNC_APPROVAL_NEEDED"
    | "ASYNC_APPROVAL_RESULT"
    | "ASYNC_RESUME"
    | "ASYNC_ERROR";
  content: string;
  data?: {
    sources?: WebSocketSources[];
    timeline?: TimelineEntry[];
    message_id?: string;
    tool_name?: string;
    args?: Record<string, unknown>;
    tool_result?: string;
    pending_tool_call?: {
      name: string;
      arguments: Record<string, unknown>;
      tool_call_id?: string;
    };
    /** Approval decision echo from backend */
    decision?: string;
    /** Approval decision used in document chat flow */
    approval_decision?: string;
    /** Error description from backend */
    error?: string;
    /** Error type classification from backend (e.g. "CONTEXT_EXHAUSTED") */
    error_type?: string;
    /** Context status metadata (token usage, compaction info) */
    context_status?: ContextStatus;
    /** Context compaction notice */
    compaction?: {
      tokens_before: number;
      tokens_after: number;
      context_window: number;
    };
    /**
     * Rich-mention agent delegation (Task 13): when an ASYNC_THOUGHT frame
     * describes a tool_call / tool_result that handed off to a sub-agent,
     * the backend ``StreamRelay`` attaches the resolved ``AgentConfiguration``
     * id and slug so the frontend timeline can surface an ``@<slug>`` chip
     * instead of the raw ``delegate_to_<slug>`` tool name.
     */
    agent_id?: number | string;
    agent_slug?: string;
    /**
     * Rich-mention agent delegation (Task 14): when an ASYNC_APPROVAL_NEEDED
     * frame originates inside a sub-agent invocation (a pinned or unpinned
     * delegation), the backend (see ``unified_agent_conversation.py`` Task 7)
     * attaches the sub-agent's ``AgentConfiguration`` so the approval modal
     * can attribute the request to ``@<slug>`` instead of the conductor.
     * Absent on top-level approvals — modal falls back to ``Tool: <name>``.
     */
    requesting_agent?: {
      slug: string;
      name: string;
    } | null;
  };
}

/**
 * Context status metadata from the backend (token usage, compaction info).
 */
export interface ContextStatus {
  used_tokens: number;
  context_window: number;
  was_compacted: boolean;
  tokens_before_compaction: number;
}

/**
 * Notice shown to user when context window compaction occurs.
 */
export interface CompactionNotice {
  tokensBefore: number;
  tokensAfter: number;
  contextWindow: number;
}

/**
 * Shape of a pending approval surfaced to the user when an agent tool call
 * requires human confirmation. Shared between ``ChatTray`` (document chat) and
 * ``CorpusChat`` (corpus chat) so the approval modal/overlay component, the
 * attribution chip, and the chat-level state share one source of truth.
 *
 * ``requestingAgent`` is populated when the approval was raised inside a
 * sub-agent invocation (rich-mention agent delegation, Task 14). It is
 * ``undefined`` / ``null`` for top-level approvals, in which case the modal
 * falls back to rendering the plain ``Tool: <name>`` header.
 */
export interface PendingApproval {
  messageId: string;
  toolCall: {
    name: string;
    arguments?: Record<string, unknown>;
    tool_call_id?: string;
  };
  requestingAgent?: {
    slug: string;
    name: string;
  } | null;
}
