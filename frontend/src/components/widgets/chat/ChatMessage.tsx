import React, { useEffect, useMemo, useState } from "react";
import {
  AlertCircle,
  Bot,
  CheckCircle,
  Clock,
  Pin,
  User,
  XCircle,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useSetAtom } from "jotai";

import { isSpanBasedFileType } from "../../../utils/files";
import { chatSourcesAtom } from "../../annotator/context/ChatSourceAtom";
import { useCreateAnnotation } from "../../annotator/hooks/AnnotationHooks";
import { useCorpusState } from "../../annotator/context/CorpusAtom";
import { useSelectedDocument } from "../../annotator/context/DocumentAtom";

import {
  ApprovalIndicator,
  Avatar,
  ContentContainer,
  MessageContainer,
  MessageContent,
  MessageHeader,
  SourceIndicator,
  TimelineIndicator,
  Timestamp,
  UserName,
} from "./ChatMessage.styles";
import { SourcePreview } from "./ChatMessageSourcePreview";
import { StreamingThoughtTicker, TimelinePreview } from "./ChatMessageTimeline";
import { ToolUsageIndicator } from "./ChatMessageToolUsage";

// Re-export named symbols for back-compat with existing importers
export { extractToolCalls, formatToolName } from "./ChatMessageToolUsage";
export { StreamingThoughtTicker } from "./ChatMessageTimeline";

// Timeline entry type — definition lives in `./types` so sibling style
// modules can import it without creating a `ChatMessage` ↔ styles cycle.
// Imported locally for use in `ChatMessageProps`, then re-exported so the
// public API of this module stays unchanged for existing importers.
import type { TimelineEntry } from "./types";
export type { TimelineEntry };

export interface ChatMessageProps {
  messageId?: string; // Optional because some messages (like streaming ones) might not have an ID yet
  user: string;
  content: string;
  timestamp: string;
  isAssistant: boolean;
  hasSources?: boolean;
  hasTimeline?: boolean;
  isSelected?: boolean;
  onSelect?: () => void;
  sources?: Array<{
    text: string;
    onClick?: () => void;
  }>;
  timeline?: TimelineEntry[];
  approvalStatus?: "approved" | "rejected" | "awaiting";
  isComplete?: boolean;
}

export const ChatMessage: React.FC<ChatMessageProps> = ({
  messageId,
  user,
  content,
  timestamp,
  isAssistant,
  sources = [],
  timeline = [],
  hasSources,
  hasTimeline,
  isSelected,
  onSelect,
  approvalStatus,
  isComplete = true,
}) => {
  const [selectedSourceIndex, setSelectedSourceIndex] = useState<
    number | undefined
  >();

  // Default presence checks if explicit flags not provided
  const effectiveHasSources = hasSources ?? sources.length > 0;
  const effectiveHasTimeline = hasTimeline ?? timeline.length > 0;

  const setChatState = useSetAtom(chatSourcesAtom);
  const createAnnotation = useCreateAnnotation();
  const { humanSpanLabels, humanTokenLabels } = useCorpusState();
  const { selectedDocument } = useSelectedDocument();
  const availableLabels = useMemo(() => {
    if (isSpanBasedFileType(selectedDocument?.fileType)) return humanSpanLabels;
    return humanTokenLabels;
  }, [selectedDocument, humanSpanLabels, humanTokenLabels]);

  const handleSourceSelect = (index: number) => {
    setSelectedSourceIndex(index === selectedSourceIndex ? undefined : index);
    if (messageId !== undefined) {
      setChatState((prev) => ({
        ...prev,
        selectedMessageId: messageId,
        selectedSourceIndex: index === prev.selectedSourceIndex ? null : index,
      }));
    }
  };

  const getApprovalIcon = (status: "approved" | "rejected" | "awaiting") => {
    switch (status) {
      case "approved":
        return <CheckCircle size={14} />;
      case "rejected":
        return <XCircle size={14} />;
      case "awaiting":
        return <AlertCircle size={14} />;
      default:
        return null;
    }
  };

  const getApprovalText = (status: "approved" | "rejected" | "awaiting") => {
    switch (status) {
      case "approved":
        return "Approved";
      case "rejected":
        return "Rejected";
      case "awaiting":
        return "Awaiting Approval";
      default:
        return "";
    }
  };

  // Check if any tools were actually used in the timeline
  const hasToolUsage = useMemo(
    () => timeline.some((e) => e.type === "tool_call"),
    [timeline]
  );

  // The streaming ticker is the in-flight cue while no actual content has
  // arrived yet — it covers both the "warming up before any timeline entry"
  // case (formerly handled by the standalone ProcessingIndicator pill) and
  // the "streaming with timeline entries but no text yet" case. As soon as
  // the assistant starts emitting content tokens, the bubble takes over so
  // the user sees the response accumulate. The bordered TimelinePreview
  // panel never renders mid-stream — it only appears post-completion as a
  // collapsible summary inside the bubble.
  const showTimelineOnly =
    isAssistant && !isComplete && content.trim().length === 0;

  // Local collapse state for timeline when message is COMPLETE.
  // For short timelines (<=2 steps) we default to expanded even after completion
  const [tlCollapsed, setTlCollapsed] = useState<boolean>(
    isComplete && timeline.length > 2
  );

  // When message transitions to complete, collapse timeline automatically only if long
  useEffect(() => {
    if (isComplete) {
      setTlCollapsed(timeline.length > 2);
    }
  }, [isComplete, timeline.length]);

  return (
    <MessageContainer
      $isAssistant={isAssistant}
      $isSelected={isSelected}
      onClick={onSelect}
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: "easeOut" }}
    >
      {effectiveHasTimeline && !hasToolUsage && (
        <TimelineIndicator $isSelected={isSelected}>
          <Clock size={14} />
          {timeline.length} {timeline.length === 1 ? "step" : "steps"}
        </TimelineIndicator>
      )}
      {effectiveHasSources && (
        <SourceIndicator
          $isSelected={isSelected}
          data-testid="source-indicator"
        >
          <Pin size={14} />
          {sources.length > 0
            ? `${sources.length} ${sources.length === 1 ? "source" : "sources"}`
            : "View sources"}
        </SourceIndicator>
      )}
      {approvalStatus && (
        <ApprovalIndicator $status={approvalStatus} $isSelected={isSelected}>
          {getApprovalIcon(approvalStatus)}
          {getApprovalText(approvalStatus)}
        </ApprovalIndicator>
      )}
      <Avatar $isAssistant={isAssistant}>
        {isAssistant ? <Bot /> : <User />}
      </Avatar>
      <ContentContainer>
        <MessageHeader>
          <UserName>{isAssistant ? "AI Assistant" : user}</UserName>
          {isAssistant && hasToolUsage && (
            <ToolUsageIndicator timeline={timeline} />
          )}
        </MessageHeader>
        {/* Standard message content bubble */}
        {!showTimelineOnly && (
          <MessageContent
            $isAssistant={isAssistant}
            data-testid="message-content"
          >
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
            {approvalStatus && (
              <div style={{ marginTop: "0.5rem" }}>
                {getApprovalIcon(approvalStatus)}{" "}
                {getApprovalText(approvalStatus)}
              </div>
            )}
            {/* Collapsible timeline appears once the message is complete.
                Mid-stream the bordered panel is suppressed — the inline
                StreamingThoughtTicker handles the in-flight cue, and the
                bubble shows the accumulating content. */}
            {effectiveHasTimeline && isComplete && (
              <TimelinePreview
                timeline={timeline}
                collapsed={tlCollapsed}
                onToggle={() => setTlCollapsed(!tlCollapsed)}
              />
            )}
            {/* Sources inside bubble */}
            {effectiveHasSources && sources.length > 0 && (
              <SourcePreview
                messageId={messageId || ""}
                sources={sources}
                selectedIndex={selectedSourceIndex}
                onSourceSelect={handleSourceSelect}
                availableLabels={availableLabels}
                createAnnotation={createAnnotation}
              />
            )}
          </MessageContent>
        )}
        {/* Streaming-only "now-thinking" ticker — shows the latest in-flight
            step on a single line with a subtle fade/sweep on each new step.
            Replaced the old expanded-while-streaming TimelinePreview panel,
            which dominated the viewport on multi-step responses. The full
            step list stays available once the message finalizes via the
            collapsible TimelinePreview rendered inside the message bubble. */}
        {showTimelineOnly && <StreamingThoughtTicker timeline={timeline} />}
        <Timestamp>{timestamp}</Timestamp>
      </ContentContainer>
    </MessageContainer>
  );
};
