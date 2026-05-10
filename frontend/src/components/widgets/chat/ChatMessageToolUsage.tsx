import React, {
  useCallback,
  useEffect,
  useId,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { createPortal } from "react-dom";
import { AnimatePresence } from "framer-motion";
import { Wrench } from "lucide-react";

import {
  POPOVER_GAP,
  POPOVER_MAX_HEIGHT,
  TOOL_UNKNOWN_LABEL,
} from "../../../assets/configurations/constants";

import {
  ToolBadge,
  ToolBadgeWrapper,
  ToolCallCard,
  ToolCallCodeBlock,
  ToolCallName,
  ToolCallResultBlock,
  ToolCallSection,
  ToolCallSectionLabel,
  ToolPopover,
  ToolPopoverBody,
  ToolPopoverHeader,
} from "./ChatMessage.styles";
import type { TimelineEntry } from "./types";

// Paired tool call info extracted from timeline for the tool usage popover
interface ToolCallInfo {
  /** Stable identifier for React keys (tool name + ordinal index) */
  id: string;
  tool: string;
  args?: Record<string, unknown>;
  result?: string;
}

/**
 * Extract paired tool call/result info from timeline entries.
 *
 * Uses a consumed-set approach: each tool_result is matched to the first
 * unconsumed tool_call with the same tool name, preventing incorrect pairing
 * when the same tool is called multiple times.
 *
 * **Ordering assumption**: The backend always emits a tool_result *after* its
 * corresponding tool_call in the timeline, so forward-only search is correct.
 */
export const extractToolCalls = (timeline: TimelineEntry[]): ToolCallInfo[] => {
  const calls: ToolCallInfo[] = [];
  // Track which tool_result indices have been consumed
  const consumedResults = new Set<number>();

  for (let i = 0; i < timeline.length; i++) {
    const entry = timeline[i];
    if (entry.type !== "tool_call") continue;

    const call: ToolCallInfo = {
      // Use timeline index for stable, unique React keys
      id: `${entry.tool ?? TOOL_UNKNOWN_LABEL}-${i}`,
      tool: entry.tool || TOOL_UNKNOWN_LABEL,
      args: entry.args,
    };

    // Find the first unconsumed tool_result with the same tool name
    for (let j = i + 1; j < timeline.length; j++) {
      if (
        !consumedResults.has(j) &&
        timeline[j].type === "tool_result" &&
        timeline[j].tool === entry.tool
      ) {
        call.result = timeline[j].result;
        consumedResults.add(j);
        break;
      }
    }
    calls.push(call);
  }
  return calls;
};

/**
 * Formats a snake_case tool name for display (e.g. "similarity_search" -> "Similarity Search").
 */
export const formatToolName = (name: string): string => {
  return name
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
};

/**
 * Displays a tool usage badge next to assistant messages. On hover, opens a
 * popover listing each tool call with its input arguments and output result.
 *
 * The popover is rendered via a portal to document.body to avoid clipping by
 * ancestor containers with overflow:hidden (ChatContainer, FlexColumnPanel).
 */
export const ToolUsageIndicator: React.FC<{
  timeline: TimelineEntry[];
}> = ({ timeline }) => {
  const toolCalls = useMemo(() => extractToolCalls(timeline), [timeline]);
  const [isOpen, setIsOpen] = useState(false);
  const closeTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const badgeRef = useRef<HTMLDivElement>(null);
  const baseId = useId();
  const [popoverStyle, setPopoverStyle] = useState<React.CSSProperties>({});

  // Cleanup timeout on unmount to prevent memory leaks
  useEffect(() => {
    return () => {
      if (closeTimeoutRef.current) {
        clearTimeout(closeTimeoutRef.current);
      }
    };
  }, []);

  const updatePopoverPosition = useCallback(() => {
    if (!badgeRef.current) return;
    const rect = badgeRef.current.getBoundingClientRect();
    const spaceBelow = window.innerHeight - rect.bottom - POPOVER_GAP;
    const openUpward = spaceBelow < POPOVER_MAX_HEIGHT && rect.top > spaceBelow;

    if (openUpward) {
      setPopoverStyle({
        bottom: window.innerHeight - rect.top + POPOVER_GAP,
        right: window.innerWidth - rect.right,
        top: undefined,
      });
    } else {
      setPopoverStyle({
        top: rect.bottom + POPOVER_GAP,
        right: window.innerWidth - rect.right,
        bottom: undefined,
      });
    }
  }, []);

  // Track position while popover is open (useLayoutEffect prevents flash at 0,0)
  useLayoutEffect(() => {
    if (!isOpen) return;
    updatePopoverPosition();
    window.addEventListener("scroll", updatePopoverPosition, true);
    window.addEventListener("resize", updatePopoverPosition);
    return () => {
      window.removeEventListener("scroll", updatePopoverPosition, true);
      window.removeEventListener("resize", updatePopoverPosition);
    };
  }, [isOpen, updatePopoverPosition]);

  if (toolCalls.length === 0) return null;

  const handleMouseEnter = () => {
    if (closeTimeoutRef.current) {
      clearTimeout(closeTimeoutRef.current);
      closeTimeoutRef.current = null;
    }
    setIsOpen(true);
  };

  const handleMouseLeave = () => {
    closeTimeoutRef.current = setTimeout(() => setIsOpen(false), 200);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      setIsOpen((prev) => !prev);
    } else if (e.key === "Escape" && isOpen) {
      setIsOpen(false);
    }
  };

  const popoverId = `tool-popover-${baseId}`;

  return (
    <>
      <ToolBadgeWrapper
        ref={badgeRef}
        onMouseEnter={handleMouseEnter}
        onMouseLeave={handleMouseLeave}
        onClick={(e: React.MouseEvent) => e.stopPropagation()}
      >
        <ToolBadge
          $isSelected={isOpen}
          role="button"
          tabIndex={0}
          aria-expanded={isOpen}
          aria-haspopup="dialog"
          aria-describedby={isOpen ? popoverId : undefined}
          onKeyDown={handleKeyDown}
        >
          <Wrench size={14} />
          {toolCalls.length} {toolCalls.length === 1 ? "tool" : "tools"} used
        </ToolBadge>
      </ToolBadgeWrapper>
      {createPortal(
        <AnimatePresence>
          {isOpen && (
            <ToolPopover
              key="tool-popover"
              id={popoverId}
              role="dialog"
              aria-label={`Tool usage details: ${toolCalls.length} ${
                toolCalls.length === 1 ? "call" : "calls"
              }`}
              style={popoverStyle}
              initial={{ opacity: 0, y: -4, scale: 0.98 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: -4, scale: 0.98 }}
              transition={{ duration: 0.15, ease: "easeOut" }}
              onMouseEnter={handleMouseEnter}
              onMouseLeave={handleMouseLeave}
            >
              <ToolPopoverHeader>
                <Wrench />
                Tool Usage ({toolCalls.length}{" "}
                {toolCalls.length === 1 ? "call" : "calls"})
              </ToolPopoverHeader>
              <ToolPopoverBody>
                {toolCalls.map((call) => (
                  <ToolCallCard key={call.id}>
                    <ToolCallName>
                      <Wrench />
                      {formatToolName(call.tool)}
                    </ToolCallName>
                    {call.args !== undefined && (
                      <ToolCallSection>
                        <ToolCallSectionLabel>Input</ToolCallSectionLabel>
                        <ToolCallCodeBlock>
                          {typeof call.args === "string"
                            ? call.args
                            : JSON.stringify(call.args, null, 2)}
                        </ToolCallCodeBlock>
                      </ToolCallSection>
                    )}
                    {call.result && (
                      <ToolCallSection>
                        <ToolCallSectionLabel>Output</ToolCallSectionLabel>
                        <ToolCallResultBlock>{call.result}</ToolCallResultBlock>
                      </ToolCallSection>
                    )}
                  </ToolCallCard>
                ))}
              </ToolPopoverBody>
            </ToolPopover>
          )}
        </AnimatePresence>,
        document.body
      )}
    </>
  );
};
