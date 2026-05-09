import React, { useEffect, useRef, useState } from "react";
import { AnimatePresence } from "framer-motion";
import {
  Activity,
  CheckCircle,
  ChevronDown,
  ChevronUp,
  Clock,
  MessageSquare,
  Minimize2,
  Pin,
  Wrench,
  Zap,
} from "lucide-react";

import {
  AutoScrollIndicator,
  StreamingPulseDot,
  StreamingThoughtIcon,
  StreamingThoughtText,
  StreamingThoughtTickerWrapper,
  TimelineContainer,
  TimelineContent,
  TimelineHeader,
  TimelineIcon,
  TimelineItem,
  TimelineItemArgs,
  TimelineItemContent,
  TimelineItemText,
  TimelineItemTitle,
  TimelineList,
  TimelineTitle,
} from "./ChatMessage.styles";
import type { TimelineEntry } from "./types";

// Helper function to get icon for timeline entry type
export const getTimelineIcon = (type: TimelineEntry["type"]) => {
  switch (type) {
    case "thought":
      return <Zap />;
    case "tool_call":
      return <Wrench />;
    case "tool_result":
      return <CheckCircle />;
    case "content":
      return <MessageSquare />;
    case "sources":
      return <Pin />;
    case "status":
      return <Activity />;
    case "compaction":
      return <Minimize2 />;
    default:
      return <Clock />;
  }
};

// Helper function to get title for timeline entry type
export const getTimelineTitle = (entry: TimelineEntry) => {
  switch (entry.type) {
    case "thought":
      return "Thinking";
    case "tool_call":
      return `Calling ${entry.tool || "Tool"}`;
    case "tool_result":
      return `${entry.tool || "Tool"} Result`;
    case "content":
      return "Generating Response";
    case "sources":
      return "Found Sources";
    case "status":
      return entry.msg || "Status Update";
    case "compaction":
      return "Context Compacted";
    default:
      return "Timeline Entry";
  }
};

// Separate component so each entry manages its own expand/collapse state
interface CollapsibleTimelineItemProps {
  entry: TimelineEntry;
  initiallyExpanded: boolean;
}

const CollapsibleTimelineItem: React.FC<CollapsibleTimelineItemProps> = ({
  entry,
  initiallyExpanded,
}) => {
  const [expanded, setExpanded] = useState(initiallyExpanded);

  // Keep local state in sync if parent decides to change initial expansion (e.g., when newest entry added)
  useEffect(() => {
    setExpanded(initiallyExpanded);
  }, [initiallyExpanded]);

  const handleToggle = (e: React.MouseEvent<HTMLDivElement>) => {
    // Prevent parent (TimelineHeader) toggle when clicking inside the list
    e.stopPropagation();
    setExpanded((prev) => !prev);
  };

  return (
    <TimelineItem
      $type={entry.type}
      onClick={handleToggle}
      style={{ cursor: "pointer" }}
    >
      <TimelineIcon $type={entry.type}>
        {getTimelineIcon(entry.type)}
      </TimelineIcon>
      <TimelineItemContent>
        <TimelineItemTitle $expanded={expanded}>
          {getTimelineTitle(entry)}
        </TimelineItemTitle>
        {expanded && (
          <>
            {entry.text && <TimelineItemText>{entry.text}</TimelineItemText>}
            {entry.args && (
              <TimelineItemArgs>
                <strong>Arguments:</strong>
                <pre>{JSON.stringify(entry.args, null, 2)}</pre>
              </TimelineItemArgs>
            )}
            {entry.count !== undefined && (
              <TimelineItemText>
                <strong>Count:</strong> {entry.count}
              </TimelineItemText>
            )}
          </>
        )}
      </TimelineItemContent>
    </TimelineItem>
  );
};

interface StreamingThoughtTickerProps {
  timeline: TimelineEntry[];
}

/**
 * Single-line "now-thinking" ticker shown while the assistant is streaming.
 * Renders only the most recent timeline entry (animated icon + truncated
 * title) and fades the previous one out as a new step arrives. When no
 * timeline entry has arrived yet (warm-up beat), renders a generic
 * "Thinking…" placeholder so there is always a visible activity cue while
 * the assistant is working — replaces the old standalone "AI Assistant is
 * thinking…" pill that floated under the messages.
 *
 * The full step-by-step list is still available after the message finalizes
 * via the existing collapsible TimelinePreview inside the message bubble.
 */
export const StreamingThoughtTicker: React.FC<StreamingThoughtTickerProps> = ({
  timeline,
}) => {
  const hasEntry = timeline.length > 0;
  const latest = hasEntry ? timeline[timeline.length - 1] : null;
  // Use a generic "thought"-typed placeholder so the icon and color match the
  // most common streaming state (sparkle/lightning) when no entry has landed.
  const displayType: TimelineEntry["type"] = latest?.type ?? "thought";
  const key = hasEntry
    ? `${timeline.length - 1}-${latest!.type}-${latest!.tool ?? ""}`
    : "warming-up";
  const title = latest ? getTimelineTitle(latest) : "Thinking";

  return (
    <StreamingThoughtTickerWrapper
      data-testid="streaming-thought-ticker"
      role="status"
      aria-live="polite"
      aria-label="Assistant is processing your request"
    >
      <StreamingThoughtIcon $type={displayType}>
        {getTimelineIcon(displayType)}
      </StreamingThoughtIcon>
      <AnimatePresence exitBeforeEnter initial={false}>
        <StreamingThoughtText
          key={key}
          initial={{ opacity: 0, y: 4 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -4 }}
          transition={{ duration: 0.25, ease: "easeOut" }}
        >
          {title}
        </StreamingThoughtText>
      </AnimatePresence>
      <StreamingPulseDot aria-hidden="true" />
    </StreamingThoughtTickerWrapper>
  );
};

interface TimelinePreviewProps {
  timeline: TimelineEntry[];
  collapsed?: boolean;
  onToggle?: () => void;
}

export const TimelinePreview: React.FC<TimelinePreviewProps> = ({
  timeline,
  collapsed = true,
  onToggle,
}) => {
  const [isExpanded, setIsExpanded] = useState(!collapsed);
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const [isNearBottom, setIsNearBottom] = useState(true);
  const prevTimelineLengthRef = useRef(timeline.length);

  /* Expansion state per entry ----------------------------------------- */
  const [expandedStates, setExpandedStates] = useState<boolean[]>(() =>
    timeline.map(() => true)
  );

  // Calculate responsive threshold
  const getScrollThreshold = () => {
    const container = scrollContainerRef.current;
    if (!container) return 50;

    // Use 10% of container height or 100px (whichever is smaller) for desktop
    // 50px for mobile
    const isMobile = window.innerWidth <= 768;
    if (isMobile) return 50;

    const tenPercent = container.clientHeight * 0.1;
    return Math.min(tenPercent, 100);
  };

  // Check if scrolled near bottom
  const checkIfNearBottom = () => {
    const container = scrollContainerRef.current;
    if (!container) return true;

    const threshold = getScrollThreshold();
    const isNear =
      container.scrollHeight - container.scrollTop - container.clientHeight <=
      threshold;
    setIsNearBottom(isNear);
    return isNear;
  };

  // Handle scroll events to track user scrolling
  const handleScroll = () => {
    checkIfNearBottom();
  };

  // Scroll to bottom manually
  const scrollToBottom = () => {
    if (scrollContainerRef.current) {
      scrollContainerRef.current.scrollTop =
        scrollContainerRef.current.scrollHeight;
      setIsNearBottom(true);
    }
  };

  // Auto-scroll to bottom only when NEW entries are added (if near bottom)
  useEffect(() => {
    const hasNewEntries = timeline.length > prevTimelineLengthRef.current;

    if (
      hasNewEntries &&
      isNearBottom &&
      isExpanded &&
      scrollContainerRef.current
    ) {
      // Small delay to ensure DOM has updated
      const id = setTimeout(() => {
        if (scrollContainerRef.current) {
          scrollContainerRef.current.scrollTop =
            scrollContainerRef.current.scrollHeight;
        }
      }, 50);
      prevTimelineLengthRef.current = timeline.length;
      return () => clearTimeout(id);
    }

    prevTimelineLengthRef.current = timeline.length;
  }, [timeline.length, isNearBottom, isExpanded]);

  // Initial scroll to bottom when first expanded
  useEffect(() => {
    if (isExpanded && scrollContainerRef.current) {
      const id = setTimeout(() => {
        scrollToBottom();
      }, 100);
      return () => clearTimeout(id);
    }
  }, [isExpanded]);

  // Sync header expansion with `collapsed` prop
  useEffect(() => {
    setIsExpanded(!collapsed);
  }, [collapsed]);

  // Maintain expandedStates length when new entries arrive after the user has
  // opened the timeline post-completion (rare but possible — e.g. late server
  // backfill of source/timeline data).
  useEffect(() => {
    setExpandedStates((prev) => {
      if (timeline.length > prev.length) {
        const additional = timeline.length - prev.length;
        return [...prev, ...Array(additional).fill(true)];
      }

      if (timeline.length < prev.length) {
        return prev.slice(0, timeline.length);
      }

      return prev;
    });
  }, [timeline.length]);

  const handleHeaderClick = (e: React.MouseEvent<HTMLDivElement>) => {
    e.stopPropagation();
    const newVal = !isExpanded;
    setIsExpanded(newVal);
    onToggle?.();
  };

  return (
    <TimelineContainer
      className="timeline-container"
      data-testid="timeline-container"
      onClick={(e: React.MouseEvent<HTMLDivElement>) => e.stopPropagation()}
    >
      <TimelineHeader onClick={handleHeaderClick}>
        <TimelineTitle>
          <Clock size={14} />
          Timeline ({timeline.length} {timeline.length === 1 ? "step" : "steps"}
          )
        </TimelineTitle>
        {isExpanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
      </TimelineHeader>
      <AnimatePresence>
        {isExpanded && (
          <TimelineContent
            ref={scrollContainerRef}
            onScroll={handleScroll}
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
          >
            <TimelineList>
              {timeline.map((entry, index) => (
                <CollapsibleTimelineItem
                  key={index}
                  entry={entry}
                  initiallyExpanded={expandedStates[index]}
                />
              ))}
            </TimelineList>
            <AutoScrollIndicator
              $active={isNearBottom}
              onClick={!isNearBottom ? scrollToBottom : undefined}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.3 }}
            >
              <ChevronDown />
              {isNearBottom ? "Auto-scrolling" : "Scroll to bottom"}
            </AutoScrollIndicator>
          </TimelineContent>
        )}
      </AnimatePresence>
    </TimelineContainer>
  );
};
