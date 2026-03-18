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
