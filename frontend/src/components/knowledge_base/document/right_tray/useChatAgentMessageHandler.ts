/**
 * useChatAgentMessageHandler
 *
 * Wraps the WebSocket message dispatcher that routes incoming agent frames to
 * the appropriate stream handlers. Extracted from ChatTray's
 * `handleAgentMessage` (188-line switch over 10+ message types).
 *
 * The returned callback is the `onMessage` handler for `useWebSocketAuth`.
 * It is intentionally bound only to the `updateMessageApprovalStatus`
 * reference from the stream handlers — all other handler references are
 * stable useCallback returns, and approval state is read through
 * `pendingApprovalRef.current` (not the React state value), so the
 * WebSocket callback stays stable across renders.
 */

import { useCallback } from "react";
import type { Dispatch, RefObject, SetStateAction } from "react";
import { ChatMessageProps } from "../../../widgets/chat/ChatMessage";
import type {
  CompactionNotice,
  ContextStatus,
  MessageData,
} from "../../../chat/types";
import type { PendingApproval } from "../../../chat/types";
import type { UseChatStreamHandlersReturn } from "./useChatStreamHandlers";

export interface UseChatAgentMessageHandlerParams {
  /**
   * Ref mirroring the latest `pendingApproval` state. Read inside the
   * dispatcher closure so the callback stays stable while still reacting
   * to the most recent approval value.
   */
  pendingApprovalRef: RefObject<PendingApproval | null>;
  setPendingApproval: Dispatch<SetStateAction<PendingApproval | null>>;
  setShowApprovalModal: Dispatch<SetStateAction<boolean>>;
  setWsError: Dispatch<SetStateAction<string | null>>;
  setChat: Dispatch<SetStateAction<ChatMessageProps[]>>;
  setServerMessages: Dispatch<SetStateAction<ChatMessageProps[]>>;
  setContextStatus: Dispatch<SetStateAction<ContextStatus | null>>;
  /**
   * Compaction-notice setter. Cleared on `ASYNC_FINISH` here; the
   * complementary *write* path lives in `useChatStreamHandlers`'s
   * `appendThoughtToMessage`, which inspects thought entries for a
   * `compaction.notice` field and pushes new notices through this setter.
   */
  setCompactionNotice: Dispatch<SetStateAction<CompactionNotice | null>>;
  streamHandlers: UseChatStreamHandlersReturn;
}

export function useChatAgentMessageHandler({
  pendingApprovalRef,
  setPendingApproval,
  setShowApprovalModal,
  setWsError,
  setChat,
  setServerMessages,
  setContextStatus,
  setCompactionNotice,
  streamHandlers,
}: UseChatAgentMessageHandlerParams): (event: MessageEvent) => void {
  return useCallback(
    (event: MessageEvent) => {
      // Destructure inside the callback so the dep array can reference the
      // memoized bundle (one dep) instead of six individual handler refs.
      // ``streamHandlers`` is ``useMemo``-ed in its sibling hook, so this
      // callback only rebinds when the bundle identity actually changes.
      const {
        updateMessageApprovalStatus,
        appendStreamingTokenToChat,
        appendThoughtToMessage,
        mergeSourcesIntoMessage,
        finalizeStreamingResponse,
        handleCompleteMessage,
      } = streamHandlers;
      // Server-controlled approval-decision values flow through three frames
      // (top-level frame, ASYNC_APPROVAL_RESULT, ASYNC_FINISH). The wire type
      // is loosely typed as a string, so we validate it once at the dispatch
      // boundary rather than scattering ``as "approved" | "rejected"`` casts
      // through every branch — an unexpected value (e.g. a future "deferred"
      // or a typo) would otherwise propagate silently into
      // ``updateMessageApprovalStatus`` and the chat row's
      // ``approvalStatus`` field, both of which only model the two-state
      // shape.
      const asApprovalDecision = (v: unknown): "approved" | "rejected" | null =>
        v === "approved" || v === "rejected" ? v : null;

      try {
        const messageData: MessageData = JSON.parse(event.data);
        if (!messageData) return;
        const { type: msgType, content, data } = messageData;
        const currentApproval = pendingApprovalRef.current;

        if (data?.approval_decision && data?.message_id) {
          const decision = asApprovalDecision(data.approval_decision);
          if (decision !== null) {
            updateMessageApprovalStatus(data.message_id, decision);
          }
        }

        switch (msgType) {
          case "ASYNC_START":
            appendStreamingTokenToChat(content, data?.message_id);
            break;
          case "ASYNC_CONTENT":
            appendStreamingTokenToChat(content, data?.message_id);
            if (
              currentApproval &&
              data?.message_id === currentApproval.messageId
            ) {
              setPendingApproval(null);
              updateMessageApprovalStatus(
                currentApproval.messageId,
                "approved"
              );
            }
            break;
          case "ASYNC_THOUGHT":
            appendThoughtToMessage(content, data);
            break;
          case "ASYNC_SOURCES":
            mergeSourcesIntoMessage(data?.sources, data?.message_id);
            break;
          case "ASYNC_APPROVAL_NEEDED":
            // NOTE: No sub-tool unwrapping (_sub_tool_name) needed here.
            // ChatTray handles document-level chat which talks to a document
            // agent directly — it never goes through ask_document, so nested
            // sub-agent approvals don't occur. Sub-tool unwrapping is only
            // relevant in CorpusChat.
            if (data?.pending_tool_call && data?.message_id) {
              setPendingApproval({
                messageId: data.message_id,
                toolCall: data.pending_tool_call,
                // Rich-mention agent delegation: when the conductor
                // delegates to a sub-agent, the backend forwards the
                // sub-agent's identity here so the approval modal can
                // attribute the request to the right `@<slug>` chip.
                // ``data.requesting_agent`` is the canonical wire shape
                // (see ``components/chat/types.ts``).
                requestingAgent: data.requesting_agent ?? null,
              });
              setShowApprovalModal(true);

              setChat((prev) =>
                prev.map((msg) =>
                  msg.messageId === data.message_id
                    ? { ...msg, approvalStatus: "awaiting" as const }
                    : msg
                )
              );
              setServerMessages((prev) =>
                prev.map((msg) =>
                  msg.messageId === data.message_id
                    ? { ...msg, approvalStatus: "awaiting" as const }
                    : msg
                )
              );
            }
            break;
          case "ASYNC_APPROVAL_RESULT":
            if (
              currentApproval &&
              data?.message_id === currentApproval.messageId
            ) {
              setPendingApproval(null);
              setShowApprovalModal(false);
              const decision = asApprovalDecision(data?.decision);
              if (decision !== null) {
                updateMessageApprovalStatus(
                  currentApproval.messageId,
                  decision
                );
              }
            }
            break;
          case "ASYNC_RESUME":
            // Agent is resuming after approval.  Unlike CorpusChat (which has
            // an explicit isProcessing state), ChatTray derives its processing
            // indicator from message state (isAssistantResponding), so no
            // additional state update is needed here.
            break;
          case "ASYNC_FINISH":
            // Sub-agent persistence failure flag: backend sets
            // ``persistence_failed: true`` on ASYNC_FINISH when the pinned
            // sub-agent ``ChatMessage`` couldn't be written to the DB
            // (rich-mention agent delegation). Surface as a console
            // warning so developers see it; the bubble still renders for
            // this session but will be gone after reload. Follow-up:
            // promote to a non-blocking toast (tracked in PR description).
            if (
              (data as { persistence_failed?: boolean } | undefined)
                ?.persistence_failed
            ) {
              console.warn(
                "[ChatTray] Sub-agent reply rendered in-memory only — " +
                  "persistence failed; the bubble will be missing after reload.",
                { message_id: data?.message_id }
              );
            }
            // `data?.timeline` is intentionally not forwarded — the stream
            // handler's persistence target (ChatSourceAtom) does not store
            // timelines; thought entries are already accumulated on the
            // in-memory chat message via appendThoughtToMessage.
            finalizeStreamingResponse(content, data?.sources, data?.message_id);
            setCompactionNotice(null);
            if (data?.context_status) {
              setContextStatus(data.context_status as ContextStatus);
            }
            if (
              currentApproval &&
              data?.message_id === currentApproval.messageId
            ) {
              setPendingApproval(null);
              const finishDecision = asApprovalDecision(
                data?.approval_decision
              );
              if (finishDecision !== null) {
                updateMessageApprovalStatus(
                  currentApproval.messageId,
                  finishDecision
                );
              }
            }
            break;
          case "ASYNC_ERROR":
            // Set error state for the banner, but ALSO finalize the response
            // with the error content so it appears as a chat message.
            setWsError(data?.error || "Agent error");
            finalizeStreamingResponse(
              data?.error || "An unknown error occurred.",
              [],
              data?.message_id
            );
            break;
          case "SYNC_CONTENT": {
            setChat((prev) => [
              ...prev,
              {
                messageId: data?.message_id || `asst_${Date.now()}`,
                user: "Assistant",
                content: content,
                timestamp: new Date().toLocaleString(),
                isAssistant: true,
                isComplete: true,
              },
            ]);

            const sourcesToPass =
              data?.sources && Array.isArray(data.sources)
                ? data.sources
                : undefined;
            // `data?.timeline` is intentionally not forwarded — the stream
            // handler's persistence target (ChatSourceAtom) does not store
            // timelines; the SYNC_CONTENT chat append above already carries
            // the assistant message into the in-memory chat array.
            handleCompleteMessage(content, sourcesToPass, data?.message_id);
            break;
          }
          default:
            console.warn("Unknown message type:", msgType);
            break;
        }
      } catch (err) {
        console.error("Failed to parse WS message:", err);
      }
    },
    [
      pendingApprovalRef,
      setPendingApproval,
      setShowApprovalModal,
      setWsError,
      setChat,
      setServerMessages,
      setContextStatus,
      setCompactionNotice,
      streamHandlers,
    ]
  );
}
