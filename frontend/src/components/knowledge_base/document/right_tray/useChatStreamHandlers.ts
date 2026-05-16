/**
 * useChatStreamHandlers
 *
 * Bundles the six chat-state mutators that ingest WebSocket frames and persist
 * complete messages into the ChatSourceAtom. Extracted from ChatTray so the
 * top-level composer stays thin; designed to be reusable from `CorpusChat` in
 * a follow-up PR (the same five stream functions exist there verbatim).
 *
 * The handlers close over React useState/useRef setters that are
 * referentially stable, so each useCallback dependency array stays empty (or
 * narrow to a single dispatcher), and the returned bundle is memoized to a
 * stable identity — so callers can include it in their own useCallback deps
 * without triggering rebinds on every render.
 */

import React, { useCallback, useMemo } from "react";
import {
  ChatMessageProps,
  TimelineEntry,
} from "../../../widgets/chat/ChatMessage";
import {
  ChatSourceState,
  mapWebSocketSourcesToChatMessageSources,
} from "../../../annotator/context/ChatSourceAtom";
import type {
  CompactionNotice,
  MessageData,
  WebSocketSources,
} from "../../../chat/types";
import {
  buildTimelineEntryFromAsyncThought,
  deriveTimelineEntryType,
} from "../../../widgets/chat/timelineEntryFactory";
import { CHAT_AUTOSCROLL_THRESHOLD_PX } from "../../../../assets/configurations/constants";
import type { PendingApproval } from "./ApprovalOverlay";

export interface UseChatStreamHandlersParams {
  setChat: React.Dispatch<React.SetStateAction<ChatMessageProps[]>>;
  setServerMessages: React.Dispatch<React.SetStateAction<ChatMessageProps[]>>;
  setChatSourceState: React.Dispatch<React.SetStateAction<ChatSourceState>>;
  setCompactionNotice: React.Dispatch<
    React.SetStateAction<CompactionNotice | null>
  >;
  setPendingApproval: React.Dispatch<
    React.SetStateAction<PendingApproval | null>
  >;
  messagesContainerRef: React.RefObject<HTMLDivElement>;
}

export interface UseChatStreamHandlersReturn {
  /** Update approval status of a message in both serverMessages and chat arrays. */
  updateMessageApprovalStatus: (
    messageId: string,
    status: "approved" | "rejected"
  ) => void;
  /**
   * Append a streaming token to the current assistant message (creating one if
   * none exists). Returns the message id that was appended to so callers can
   * correlate further frames.
   */
  appendStreamingTokenToChat: (
    token: string,
    overrideMessageId?: string
  ) => string;
  /**
   * Append an agent thought (or tool call/result) to the timeline of the
   * streaming assistant message so the user can watch reasoning unfold.
   */
  appendThoughtToMessage: (
    thoughtText: string,
    data: MessageData["data"] | undefined
  ) => void;
  /**
   * Finalize a partially-streamed response by replacing the matched chat entry
   * with the final content and storing sources in ChatSourceAtom.
   *
   * Note: timeline data is intentionally **not** accepted here. The streaming
   * path already accumulates timeline entries on the in-memory chat message
   * via `appendThoughtToMessage`; the persistence target (`ChatSourceAtom`)
   * does not store timelines, so a `timelineData` parameter at this seam
   * would be a no-op.
   */
  finalizeStreamingResponse: (
    content: string,
    sourcesData?: WebSocketSources[],
    overrideId?: string
  ) => void;
  /**
   * Persist a complete message (and its sources) into ChatSourceAtom. Called
   * both by the streaming-finish path and by the msgData hydration effect.
   *
   * Note: timeline data is intentionally **not** accepted here — the
   * `ChatSourceAtom` schema only persists content/sources/timestamp, so a
   * `timelineData` parameter at this seam would be a no-op. Timelines remain
   * on the in-memory `chat` array via `appendThoughtToMessage`.
   */
  handleCompleteMessage: (
    content: string,
    sourcesData?: WebSocketSources[],
    overrideId?: string,
    overrideCreatedAt?: string
  ) => void;
  /**
   * Merge additional sources arriving via ASYNC_SOURCES into the existing
   * ChatSourceAtom entry + local chat message so pins are clickable mid-stream.
   */
  mergeSourcesIntoMessage: (
    sourcesData: WebSocketSources[] | undefined,
    overrideId?: string
  ) => void;
}

export function useChatStreamHandlers({
  setChat,
  setServerMessages,
  setChatSourceState,
  setCompactionNotice,
  setPendingApproval,
  messagesContainerRef,
}: UseChatStreamHandlersParams): UseChatStreamHandlersReturn {
  const updateMessageApprovalStatus = useCallback(
    (messageId: string, status: "approved" | "rejected") => {
      setPendingApproval((current) => {
        if (current?.messageId === messageId) {
          return null;
        }
        return current;
      });

      setServerMessages((prev) =>
        prev.map((msg) => {
          if (msg.messageId === messageId) {
            return { ...msg, approvalStatus: status, isComplete: true };
          }
          return msg;
        })
      );

      setChat((prev) =>
        prev.map((msg) => {
          if (msg.messageId === messageId) {
            return { ...msg, approvalStatus: status, isComplete: true };
          }
          return msg;
        })
      );
    },
    [setPendingApproval, setServerMessages, setChat]
  );

  const handleCompleteMessage = useCallback(
    (
      content: string,
      sourcesData?: Array<WebSocketSources>,
      overrideId?: string,
      overrideCreatedAt?: string
    ): void => {
      if (!overrideId) {
        console.warn(
          "handleCompleteMessage called without an overrideId - sources may not display correctly"
        );
      }
      const messageId = overrideId ?? `msg_${Date.now()}`;
      const messageTimestamp = overrideCreatedAt
        ? new Date(overrideCreatedAt).toISOString()
        : new Date().toISOString();

      const mappedSources = mapWebSocketSourcesToChatMessageSources(
        sourcesData,
        messageId
      );

      setChatSourceState((prev) => {
        const existingIndex = prev.messages.findIndex(
          (m) => m.messageId === messageId
        );

        if (existingIndex !== -1) {
          const existingMsg = prev.messages[existingIndex];
          const updatedMsg = {
            ...existingMsg,
            content,
            timestamp: messageTimestamp,
            sources: mappedSources.length ? mappedSources : existingMsg.sources,
          } as typeof existingMsg;

          const updatedMessages = [...prev.messages];
          updatedMessages[existingIndex] = updatedMsg;

          return {
            ...prev,
            messages: updatedMessages,
          };
        } else {
          return {
            ...prev,
            messages: [
              ...prev.messages,
              {
                messageId,
                content,
                timestamp: messageTimestamp,
                sources: mappedSources,
              },
            ],
            selectedMessageId: overrideId ? prev.selectedMessageId : messageId,
          };
        }
      });
    },
    [setChatSourceState]
  );

  const appendStreamingTokenToChat = useCallback(
    (token: string, overrideMessageId?: string): string => {
      if (!token) return "";

      let messageId = "";
      setChat((prev) => {
        const lastMessage = prev[prev.length - 1];

        if (lastMessage && lastMessage.isAssistant) {
          messageId = lastMessage.messageId || "";
          const updatedLast = {
            ...lastMessage,
            content: lastMessage.content + token,
            isComplete: false,
          };
          return [...prev.slice(0, -1), updatedLast];
        } else {
          messageId =
            overrideMessageId ||
            `msg_${Date.now()}_${Math.random().toString(36).substring(2)}`;
          return [
            ...prev,
            {
              messageId,
              user: "Assistant",
              content: token,
              timestamp: new Date().toLocaleString(),
              isAssistant: true,
              hasTimeline: false,
              timeline: [],
              isComplete: false,
            },
          ];
        }
      });

      // Auto-scroll to bottom only if user hasn't scrolled up. This inline
      // scroll is the streaming-feel optimization — do not lift into a
      // useEffect.
      const container = messagesContainerRef.current;
      if (container) {
        const isScrolledUp =
          container.scrollTop <
          container.scrollHeight -
            container.clientHeight -
            CHAT_AUTOSCROLL_THRESHOLD_PX;
        if (!isScrolledUp) {
          setTimeout(
            () =>
              container.scrollTo({
                top: container.scrollHeight,
                behavior: "smooth",
              }),
            0
          );
        }
      }

      return messageId;
    },
    [setChat, messagesContainerRef]
  );

  const appendThoughtToMessage = useCallback(
    (thoughtText: string, data: MessageData["data"] | undefined): void => {
      const messageId = data?.message_id;
      if (!messageId || !thoughtText) return;

      const entryType = deriveTimelineEntryType(data);
      if (entryType === "compaction" && data?.compaction) {
        setCompactionNotice({
          tokensBefore: data.compaction.tokens_before,
          tokensAfter: data.compaction.tokens_after,
          contextWindow: data.compaction.context_window,
        });
      }
      // Shared factory forwards the rich-mention agent delegation hints
      // (``agent_id`` / ``agent_slug``) onto the timeline entry so the
      // renderer can swap the raw ``delegate_to_<slug>`` tool name for a
      // styled ``@<slug>`` chip. Inlining the projection here was the
      // pre-extraction state and silently dropped those fields.
      const newEntry: TimelineEntry = buildTimelineEntryFromAsyncThought(
        thoughtText,
        data,
        entryType
      );

      setChat((prev) => {
        const idx = prev.findIndex((m) => m.messageId === messageId);
        if (idx === -1) {
          return [
            ...prev,
            {
              messageId,
              user: "Assistant",
              content: "",
              timestamp: new Date().toLocaleString(),
              isAssistant: true,
              hasTimeline: true,
              timeline: [newEntry],
              isComplete: false,
            },
          ];
        }

        const msg = prev[idx];
        const timeline = msg.timeline
          ? [...msg.timeline, newEntry]
          : [newEntry];
        const updated = {
          ...msg,
          hasTimeline: true,
          timeline,
          isComplete: false,
        } as ChatMessageProps;

        return [...prev.slice(0, idx), updated, ...prev.slice(idx + 1)];
      });
    },
    [setChat, setCompactionNotice]
  );

  const finalizeStreamingResponse = useCallback(
    (
      content: string,
      sourcesData?: WebSocketSources[],
      overrideId?: string
    ): void => {
      let lastMsgId: string | undefined;
      setChat((prev) => {
        if (!prev.length) return prev;
        let updateIdx = prev.findIndex((m) => m.messageId === overrideId);
        if (updateIdx === -1) {
          const lastIdxRev = [...prev]
            .reverse()
            .findIndex((m) => m.isAssistant);
          if (lastIdxRev === -1) return prev;
          updateIdx = prev.length - 1 - lastIdxRev;
        }

        const updatedMessages = [...prev];
        const assistantMsg = updatedMessages[updateIdx];
        lastMsgId = assistantMsg.messageId;

        updatedMessages[updateIdx] = {
          ...assistantMsg,
          content,
          isComplete: true,
        };

        // Synchronous call inside the setChat updater — mirrors the original
        // ChatTray semantics. handleCompleteMessage writes to a different
        // atom (setChatSourceState) so it does not race with this setChat
        // return value. Both functions are stable useCallback refs.
        handleCompleteMessage(content, sourcesData, lastMsgId);

        return updatedMessages;
      });
    },
    [setChat, handleCompleteMessage]
  );

  const mergeSourcesIntoMessage = useCallback(
    (
      sourcesData: WebSocketSources[] | undefined,
      overrideId?: string
    ): void => {
      // Guard: skip empty updates so partial ASYNC_SOURCES frames don't
      // trigger needless re-renders.
      if (!sourcesData?.length || !overrideId) return;

      const mappedSources = mapWebSocketSourcesToChatMessageSources(
        sourcesData,
        overrideId
      );

      setChatSourceState((prev) => {
        const idx = prev.messages.findIndex((m) => m.messageId === overrideId);
        if (idx === -1) {
          return {
            ...prev,
            messages: [
              ...prev.messages,
              {
                messageId: overrideId,
                content: "",
                timestamp: new Date().toISOString(),
                sources: mappedSources,
                isComplete: false,
              },
            ],
          };
        }

        const existing = prev.messages[idx];
        const mergedSources = [
          ...existing.sources,
          ...mappedSources.filter(
            (ms) =>
              !existing.sources.some(
                (es) => es.annotation_id === ms.annotation_id
              )
          ),
        ];

        const updatedMessages = [...prev.messages];
        const mergedMsg = { ...existing, sources: mergedSources };
        updatedMessages[idx] = mergedMsg;

        return { ...prev, messages: updatedMessages };
      });

      setChat((prev) => {
        const idx = prev.findIndex((m) => m.messageId === overrideId);
        if (idx === -1) return prev;
        const msg = prev[idx];
        return [
          ...prev.slice(0, idx),
          { ...msg, hasSources: true },
          ...prev.slice(idx + 1),
        ];
      });
    },
    [setChatSourceState, setChat]
  );

  return useMemo(
    () => ({
      updateMessageApprovalStatus,
      appendStreamingTokenToChat,
      appendThoughtToMessage,
      finalizeStreamingResponse,
      handleCompleteMessage,
      mergeSourcesIntoMessage,
    }),
    [
      updateMessageApprovalStatus,
      appendStreamingTokenToChat,
      appendThoughtToMessage,
      finalizeStreamingResponse,
      handleCompleteMessage,
      mergeSourcesIntoMessage,
    ]
  );
}
