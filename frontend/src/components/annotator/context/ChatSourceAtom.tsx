import { atom, useAtom } from "jotai";
import { useMemo } from "react";
import {
  TokenId,
  BoundingBox,
  MultipageAnnotationJson,
  SinglePageAnnotationJson,
} from "../../types";
import { WebSocketSources } from "../../chat/types";
import { TimelineEntry } from "../../widgets/chat/ChatMessage";

/**
 * A single pinned source in a message.
 * - For each page, we store token IDs and bounding boxes.
 * - Adjust or add optional fields (e.g., `text`) as needed for your features.
 */
export interface ChatMessageSource {
  id: string;
  page: number;
  label: string;
  label_id: number;
  annotation_id: number;
  rawText: string;
  tokensByPage: Record<number, TokenId[]>;
  boundsByPage: Record<number, BoundingBox>;
  startIndex?: number;
  endIndex?: number;
  isTextBased?: boolean;
  /** Document ID this source belongs to (for cross-document deep linking) */
  document_id?: number;
}

export interface ChatMessage {
  messageId: string;
  content: string;
  timestamp: string;
  sources: ChatMessageSource[];
  timeline?: TimelineEntry[];
}

export interface ChatSourceState {
  messages: ChatMessage[];
  selectedMessageId: string | null;
  selectedSourceIndex: number | null;
}

export const chatSourcesAtom = atom<ChatSourceState>({
  messages: [],
  selectedMessageId: null,
  selectedSourceIndex: null,
});

/**
 * Simple hook for reading/updating chat source state.
 */
export const useChatSourceState = () => {
  const [state, setState] = useAtom(chatSourcesAtom);

  // Memoize return object to prevent new object on every render
  return useMemo(
    () => ({
      messages: state.messages,
      selectedMessageId: state.selectedMessageId,
      selectedSourceIndex: state.selectedSourceIndex,
      setChatSourceState: setState,
    }),
    [
      state.messages,
      state.selectedMessageId,
      state.selectedSourceIndex,
      setState,
    ]
  );
};

type TextJson = { start: number; end: number; text?: string };

function isTextJson(obj: any): obj is TextJson {
  return typeof obj?.start === "number" && typeof obj?.end === "number";
}

/**
 * Maps incoming WebSocketSources into ChatMessageSource[]
 */
export function mapWebSocketSourcesToChatMessageSources(
  sourcesData: WebSocketSources[] | undefined,
  messageId: string
): ChatMessageSource[] {
  if (!sourcesData) return [];

  // Filter out invalid sources and map valid ones
  const mappedSources = sourcesData
    .map((src, index) => {
      try {
        if (!src || src.json === null || src.json === undefined) {
          console.warn(
            `Skipping invalid source at index ${index}: missing or null json property`
          );
          return null;
        }

        if (isTextJson(src.json)) {
          const { start, end, text = "" } = src.json;
          return {
            id: `${messageId}.${index}`,
            page: src.page ?? 0, // keep or set 0 if there's truly no pages in text docs
            label: src.label,
            label_id: src.label_id,
            annotation_id: src.annotation_id,
            rawText: src.rawText,
            tokensByPage: {},
            boundsByPage: {},
            startIndex: start,
            endIndex: end,
            isTextBased: true,
            document_id: src.document_id,
          };
        } else {
          const multiPageObj = src.json as MultipageAnnotationJson;

          // Safety check for multiPageObj
          if (!multiPageObj || typeof multiPageObj !== "object") {
            console.warn(
              `Skipping invalid source at index ${index}: json is not a valid object`
            );
            return null;
          }

          const tokensByPage: Record<number, TokenId[]> = {};
          const boundsByPage: Record<number, BoundingBox> = {};

          // Build per-page tokens/bounds
          for (const [pageKey, pageData] of Object.entries(multiPageObj)) {
            // Attempt a numeric parse
            const pageNum = parseInt(pageKey, 10);
            const data = pageData as SinglePageAnnotationJson;

            // Store the token data if any
            tokensByPage[pageNum] = data.tokensJsons ?? [];

            // Store bounding boxes if present
            if (data.bounds) {
              boundsByPage[pageNum] = data.bounds;
            }
          }

          // Combine rawText from all pages
          const combinedRawText = Object.values(multiPageObj)
            .map((data) => data.rawText || "")
            .join(" ");

          return {
            id: `${messageId}.${index}`,
            page: src.page, // keep source's page as is
            label: src.label,
            label_id: src.label_id,
            annotation_id: src.annotation_id,
            rawText: combinedRawText,
            tokensByPage,
            boundsByPage,
            startIndex: undefined,
            endIndex: undefined,
            isTextBased: false,
            document_id: src.document_id,
          };
        }
      } catch (error) {
        console.error(`Error processing source at index ${index}:`, error);
        return null;
      }
    })
    .filter((source): source is NonNullable<typeof source> => source !== null);

  return mappedSources;
}
