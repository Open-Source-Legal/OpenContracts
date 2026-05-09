import styled from "styled-components";
import { motion } from "framer-motion";
import { OS_LEGAL_COLORS } from "../../../assets/configurations/osLegalStyles";
import { POPOVER_Z_INDEX } from "../../../assets/configurations/constants";
import type { TimelineEntry } from "./types";

export const MessageContainer = styled(motion.div)<{
  $isAssistant: boolean;
  $isSelected?: boolean;
}>`
  display: flex;
  gap: 1rem;
  padding: 0.75rem 1.5rem;
  transition: all 0.2s ease-in-out;
  position: relative;
  cursor: ${(props) =>
    props.$isSelected !== undefined ? "pointer" : "default"};
  background: ${(props) =>
    props.$isSelected
      ? "rgba(92,124,157,0.05)"
      : props.$isAssistant
      ? "rgba(247, 249, 252, 0.3)"
      : "rgba(247, 248, 249, 0.15)"};

  ${(props) =>
    props.$isSelected &&
    `
    box-shadow: inset 4px 0 0 #5C7C9D;
  `}

  &:hover {
    background: ${(props) =>
      props.$isSelected
        ? "rgba(92,124,157,0.08)"
        : props.$isAssistant
        ? "rgba(247, 249, 252, 0.4)"
        : "rgba(247, 248, 249, 0.25)"};
  }

  /* Add responsive padding */
  @media (max-width: 768px) {
    padding: 0.5rem 1rem;
    gap: 0.75rem;
  }

  @media (max-width: 480px) {
    padding: 0.5rem 0.75rem;
    gap: 0.5rem;
  }
`;

export const Avatar = styled.div<{ $isAssistant: boolean }>`
  width: 2.5rem;
  height: 2.5rem;
  border-radius: ${(props) => (props.$isAssistant ? "16px" : "12px")};
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  background: ${(props) =>
    props.$isAssistant
      ? "linear-gradient(135deg, #2185d0 0%, #1678c2 100%)"
      : "linear-gradient(135deg, #2d3748 0%, #4a5568 100%)"};
  box-shadow: ${(props) =>
    props.$isAssistant
      ? "0 4px 12px rgba(33, 133, 208, 0.2)"
      : "0 4px 12px rgba(45, 55, 72, 0.2)"};
  color: ${(props) => (props.$isAssistant ? "white" : OS_LEGAL_COLORS.border)};
  transform: translateY(0);
  transition: all 0.2s ease;

  &:hover {
    transform: translateY(-1px);
    box-shadow: ${(props) =>
      props.$isAssistant
        ? "0 6px 16px rgba(33, 133, 208, 0.25)"
        : "0 6px 16px rgba(45, 55, 72, 0.25)"};
  }

  svg {
    width: 1.2rem;
    height: 1.2rem;
    filter: drop-shadow(0 2px 4px rgba(0, 0, 0, 0.1));
  }

  /* Adjust avatar size on mobile */
  @media (max-width: 480px) {
    width: 2rem;
    height: 2rem;
    border-radius: 10px;

    svg {
      width: 1rem;
      height: 1rem;
    }
  }
`;

export const ContentContainer = styled.div`
  flex: 1;
  min-width: 0;
`;

export const MessageContent = styled.div<{ $isAssistant: boolean }>`
  background: ${(props) =>
    props.$isAssistant
      ? "rgba(255, 255, 255, 0.7)"
      : "rgba(247, 248, 249, 0.5)"};
  backdrop-filter: blur(12px);
  border-radius: 1.25rem;
  padding: 1.25rem 1.5rem;
  color: ${(props) => (props.$isAssistant ? "#1a1f36" : "#2d3748")};
  font-size: 0.95rem;
  line-height: 1.6;
  position: relative;
  margin-bottom: 0.25rem;
  box-shadow: ${(props) =>
    props.$isAssistant
      ? "0 2px 8px rgba(23, 25, 35, 0.04)"
      : "0 1px 4px rgba(23, 25, 35, 0.03)"};
  border: 1px solid
    ${(props) =>
      props.$isAssistant
        ? "rgba(255, 255, 255, 0.5)"
        : "rgba(247, 248, 249, 0.3)"};
  overflow-wrap: break-word;
  word-break: break-word;

  &::before {
    content: "";
    position: absolute;
    top: 1rem;
    ${(props) => (props.$isAssistant ? "left" : "right")}: -0.5rem;
    width: 1rem;
    height: 1rem;
    background: ${(props) =>
      props.$isAssistant
        ? "linear-gradient(135deg, #f8f9fa, #ffffff)"
        : `linear-gradient(135deg, ${OS_LEGAL_COLORS.gray200}, ${OS_LEGAL_COLORS.surfaceLight})`};
    transform: rotate(45deg);
    border-radius: 0.125rem;
  }

  /* Add styles for markdown content */
  & > div {
    overflow-x: auto;
  }

  pre {
    background: rgba(247, 248, 249, 0.6);
    backdrop-filter: blur(8px);
    border-radius: 0.75rem;
    padding: 1.25rem;
    border: 1px solid rgba(226, 232, 240, 0.3);
  }

  code {
    color: #2b6cb0;
    background: rgba(43, 108, 176, 0.08);
    border-radius: 4px;
    padding: 0.2em 0.4em;
  }

  table {
    border-collapse: collapse;
    width: 100%;
    margin: 1rem 0;
  }

  th,
  td {
    border: 1px solid ${OS_LEGAL_COLORS.border};
    padding: 0.5rem;
  }

  th {
    background: rgba(0, 0, 0, 0.02);
  }

  /* Improve mobile readability */
  @media (max-width: 768px) {
    font-size: 0.9rem;
    padding: 0.875rem 1rem;

    pre {
      padding: 0.5rem;
      font-size: 0.8rem;
      max-width: 100%;
      overflow-x: auto;
      -webkit-overflow-scrolling: touch;
    }

    code {
      font-size: 0.85em;
    }

    table {
      display: block;
      max-width: 100%;
      overflow-x: auto;
      -webkit-overflow-scrolling: touch;
    }
  }

  /* Enhance mobile chat bubble appearance */
  @media (max-width: 480px) {
    border-radius: 0.875rem;
    padding: 0.75rem 0.875rem;

    &::before {
      display: none; /* Remove chat bubble arrow on very small screens */
    }
  }
`;

export const SourcesContainer = styled.div`
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  margin-top: 0.75rem;
  transition: all 0.2s ease-in-out;
`;

export const SourcePreviewContainer = styled.div`
  position: relative;
  background: rgba(255, 255, 255, 0.7);
  border-radius: 0.75rem;
  border: 1px solid rgba(92, 124, 157, 0.2);
  overflow: hidden;
  transition: all 0.2s ease-in-out;
`;

export const SourcePreviewHeader = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.75rem 1rem;
  background: rgba(92, 124, 157, 0.05);
  border-bottom: 1px solid rgba(92, 124, 157, 0.1);
  cursor: pointer;
  transition: all 0.2s ease-in-out;

  &:hover {
    background: rgba(92, 124, 157, 0.1);
  }
`;

export const SourcePreviewTitle = styled.div`
  font-size: 0.875rem;
  font-weight: 500;
  color: #5c7c9d;
  display: flex;
  align-items: center;
  gap: 0.5rem;
`;

export const SourcePreviewContent = styled(motion.div)`
  padding: 0.75rem 1rem;
  font-size: 0.875rem;
  color: #4a5568;
  max-height: 300px;
  overflow-y: auto;
`;

export const SourceList = styled.div`
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  padding: 0.25rem;
`;

export const SourceChip = styled.div<{ $isSelected: boolean }>`
  position: relative;
  overflow: visible;
  z-index: 5;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  padding: 0.75rem;
  background: ${(props) =>
    props.$isSelected
      ? "rgba(92, 124, 157, 0.15)"
      : "rgba(255, 255, 255, 0.7)"};
  border: 1px solid
    ${(props) =>
      props.$isSelected
        ? "rgba(92, 124, 157, 0.3)"
        : "rgba(92, 124, 157, 0.1)"};
  border-radius: 0.75rem;
  font-size: 0.875rem;
  cursor: pointer;
  transition: all 0.2s ease-in-out;

  &:hover {
    background: ${(props) =>
      props.$isSelected
        ? "rgba(92, 124, 157, 0.2)"
        : "rgba(255, 255, 255, 0.9)"};
    border-color: rgba(92, 124, 157, 0.3);
    transform: translateY(-1px);
    box-shadow: 0 2px 8px rgba(92, 124, 157, 0.1);
  }

  &:active {
    transform: translateY(0);
  }
`;

export const SourceHeader = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
`;

export const SourceTitle = styled.div<{ $isSelected: boolean }>`
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-weight: 500;
  color: ${(props) =>
    props.$isSelected
      ? OS_LEGAL_COLORS.textPrimary
      : OS_LEGAL_COLORS.textTertiary};
`;

export const SourceText = styled(motion.div)<{ $isExpanded: boolean }>`
  font-size: 0.8125rem;
  color: ${OS_LEGAL_COLORS.textTertiary};
  line-height: 1.5;
  position: relative;
  overflow: hidden;

  ${(props) =>
    !props.$isExpanded &&
    `
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
  `}
`;

export const ExpandButton = styled.button<{ $isExpanded: boolean }>`
  background: none;
  border: none;
  padding: 0.25rem;
  color: #5c7c9d;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 0.25rem;
  font-size: 0.75rem;
  font-weight: 500;
  transition: all 0.2s ease-in-out;

  &:hover {
    color: #4a6b8c;
  }

  svg {
    width: 14px;
    height: 14px;
    transition: transform 0.2s ease-in-out;
    transform: ${(props) =>
      props.$isExpanded ? "rotate(180deg)" : "rotate(0deg)"};
  }
`;

export const AnnotateButton = styled.button`
  background: none;
  border: none;
  padding: 0.25rem;
  color: #5c7c9d;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 0.25rem;
  font-size: 0.75rem;
  font-weight: 500;
  transition: all 0.2s ease-in-out;

  &:hover {
    color: #4a6b8c;
  }
`;

export const LabelMenu = styled.div`
  position: absolute;
  top: 2.2rem;
  right: 0.5rem;
  background: rgba(255, 255, 255, 0.98);
  backdrop-filter: blur(12px);
  border: 1px solid rgba(200, 200, 200, 0.8);
  border-radius: 0.5rem;
  padding: 0.5rem;
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  z-index: 2000;
`;

export const LabelButton = styled.button`
  border: none;
  background: transparent;
  padding: 0.4rem 0.75rem;
  font-size: 0.8125rem;
  border-radius: 0.375rem;
  text-align: left;
  cursor: pointer;
  transition: background 0.2s ease;

  &:hover {
    background: rgba(0, 0, 0, 0.05);
  }
`;

// Timeline styled components
export const TimelineContainer = styled.div`
  position: relative;
  background: rgba(255, 255, 255, 0.7);
  border-radius: 0.75rem;
  border: 1px solid rgba(156, 163, 175, 0.2);
  overflow: hidden;
  transition: all 0.2s ease-in-out;
  margin-top: 0.75rem;
`;

export const TimelineHeader = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.5rem 0.75rem;
  background: rgba(156, 163, 175, 0.05);
  border-bottom: 1px solid rgba(156, 163, 175, 0.1);
  cursor: pointer;
  transition: all 0.2s ease-in-out;

  &:hover {
    background: rgba(156, 163, 175, 0.1);
  }
`;

export const TimelineTitle = styled.div`
  font-size: 0.8125rem;
  font-weight: 500;
  color: #6b7280;
  display: flex;
  align-items: center;
  gap: 0.375rem;
`;

export const TimelineContent = styled(motion.div)`
  padding: 0.5rem 0.75rem;
  font-size: 0.875rem;
  color: #4a5568;
  max-height: 220px;
  overflow-y: auto;
  scroll-behavior: smooth;
  position: relative;
`;

export const AutoScrollIndicator = styled(motion.div)<{ $active: boolean }>`
  position: sticky;
  bottom: 0;
  left: 0;
  right: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.25rem;
  padding: 0.25rem 0.5rem;
  margin: 0 -0.75rem -0.5rem;
  background: ${(props) =>
    props.$active
      ? "linear-gradient(to top, rgba(255,255,255,0.95), rgba(255,255,255,0.8))"
      : "linear-gradient(to top, rgba(245,245,245,0.95), rgba(245,245,245,0.8))"};
  border-top: 1px solid
    ${(props) =>
      props.$active ? "rgba(59, 130, 246, 0.2)" : "rgba(156, 163, 175, 0.2)"};
  font-size: 0.7rem;
  color: ${(props) =>
    props.$active ? OS_LEGAL_COLORS.primaryBlue : OS_LEGAL_COLORS.textMuted};
  cursor: ${(props) => (props.$active ? "default" : "pointer")};
  transition: all 0.2s ease;

  svg {
    width: 12px;
    height: 12px;
    animation: ${(props) => (props.$active ? "bounce 2s infinite" : "none")};
  }

  @keyframes bounce {
    0%,
    100% {
      transform: translateY(0);
    }
    50% {
      transform: translateY(-3px);
    }
  }

  &:hover {
    background: ${(props) =>
      props.$active
        ? "linear-gradient(to top, rgba(255,255,255,1), rgba(255,255,255,0.9))"
        : "linear-gradient(to top, rgba(245,245,245,1), rgba(245,245,245,0.9))"};
  }
`;

export const TimelineList = styled.div`
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
`;

export const TimelineItem = styled.div<{ $type: TimelineEntry["type"] }>`
  display: flex;
  align-items: flex-start;
  gap: 0.375rem;
  padding: 0.25rem 0;
  background: transparent;
  border: none;
  border-radius: 0;
  transition: all 0.2s ease-in-out;

  &:hover {
    background: rgba(0, 0, 0, 0.02);
    border-radius: 0.25rem;
  }
`;

export const typeColor = (type: TimelineEntry["type"]) => {
  switch (type) {
    case "thought":
      return "#a855f7";
    case "tool_call":
      return OS_LEGAL_COLORS.primaryBlue;
    case "tool_result":
      return OS_LEGAL_COLORS.green;
    case "content":
      return "#f97316";
    case "sources":
      return "#5c7c9d";
    case "status":
      return OS_LEGAL_COLORS.textMuted;
    case "compaction":
      return OS_LEGAL_COLORS.primaryBlueHover;
    default:
      return OS_LEGAL_COLORS.textMuted;
  }
};

export const TimelineIcon = styled.div<{ $type: TimelineEntry["type"] }>`
  display: flex;
  align-items: center;
  justify-content: center;
  width: 1.25rem;
  height: 1.25rem;
  border-radius: 50%;
  flex-shrink: 0;
  background: transparent;
  color: ${(props) => typeColor(props.$type)};

  svg {
    width: 0.875rem;
    height: 0.875rem;
  }
`;

export const TimelineItemContent = styled.div`
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
`;

export const TimelineItemTitle = styled.div<{ $expanded?: boolean }>`
  font-weight: 500;
  color: ${(props) => (props.$expanded ? "#1f2937" : "#4b5563")};
  font-size: 0.8125rem;
  display: flex;
  align-items: center;
  gap: 0.25rem;
  cursor: pointer;
  user-select: none;

  &::after {
    content: ${(props) => (props.$expanded ? '"▼"' : '"▶"')};
    font-size: 0.5rem;
    color: #9ca3af;
    transition: transform 0.2s ease;
  }
`;

export const TimelineItemText = styled.div`
  color: #4b5563;
  font-size: 0.75rem;
  line-height: 1.5;
  word-break: break-word;
  padding-left: 0.25rem;
`;

export const TimelineItemArgs = styled.div`
  margin-top: 0.25rem;
  padding: 0.375rem;
  background: rgba(0, 0, 0, 0.02);
  border-radius: 0.375rem;
  border: 1px solid rgba(0, 0, 0, 0.05);
  font-family: "Monaco", "Menlo", "Ubuntu Mono", monospace;
  font-size: 0.7rem;
  color: #374151;
  overflow-x: auto;
`;

// Tool Usage Badge & Popover styled components
export const ToolBadgeWrapper = styled.div`
  display: inline-flex;
`;

export const ToolBadge = styled.div<{ $isSelected?: boolean }>`
  display: flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.35rem 0.7rem;
  background: ${(props) =>
    props.$isSelected
      ? OS_LEGAL_COLORS.primaryBlue
      : "rgba(59, 130, 246, 0.1)"};
  color: ${(props) =>
    props.$isSelected ? "white" : OS_LEGAL_COLORS.primaryBlue};
  border-radius: 1rem;
  font-size: 0.8rem;
  font-weight: 500;
  cursor: pointer;
  backdrop-filter: blur(8px);
  border: 1px solid
    ${(props) =>
      props.$isSelected ? "transparent" : "rgba(59, 130, 246, 0.2)"};
  transition: all 0.2s ease;
  white-space: nowrap;

  svg {
    width: 14px;
    height: 14px;
    flex-shrink: 0;
  }

  &:hover {
    background: ${(props) =>
      props.$isSelected
        ? OS_LEGAL_COLORS.primaryBlueHover
        : "rgba(59, 130, 246, 0.18)"};
    transform: translateY(-1px);
    box-shadow: 0 2px 8px rgba(59, 130, 246, 0.15);
  }

  @media (max-width: 768px) {
    padding: 0.25rem 0.5rem;
    font-size: 0.75rem;
  }
`;

export const ToolPopover = styled(motion.div)`
  position: fixed;
  z-index: ${POPOVER_Z_INDEX};
  min-width: 320px;
  max-width: 440px;
  background: rgba(255, 255, 255, 0.98);
  backdrop-filter: blur(16px);
  border: 1px solid rgba(59, 130, 246, 0.15);
  border-radius: 0.75rem;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.12), 0 2px 8px rgba(59, 130, 246, 0.08);
  overflow: hidden;

  @media (max-width: 768px) {
    min-width: 260px;
    max-width: 320px;
  }
`;

export const ToolPopoverHeader = styled.div`
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.75rem 1rem;
  background: rgba(59, 130, 246, 0.05);
  border-bottom: 1px solid rgba(59, 130, 246, 0.1);
  font-size: 0.8125rem;
  font-weight: 600;
  color: ${OS_LEGAL_COLORS.blueDark};

  svg {
    width: 16px;
    height: 16px;
  }
`;

export const ToolPopoverBody = styled.div`
  max-height: 400px;
  overflow-y: auto;
  padding: 0.5rem;
`;

export const ToolCallCard = styled.div`
  padding: 0.625rem 0.75rem;
  border-radius: 0.5rem;
  background: rgba(248, 250, 252, 0.8);
  border: 1px solid rgba(226, 232, 240, 0.6);
  transition: all 0.15s ease;

  & + & {
    margin-top: 0.5rem;
  }

  &:hover {
    background: rgba(248, 250, 252, 1);
    border-color: rgba(59, 130, 246, 0.2);
  }
`;

export const ToolCallName = styled.div`
  display: flex;
  align-items: center;
  gap: 0.375rem;
  font-size: 0.8125rem;
  font-weight: 600;
  color: ${OS_LEGAL_COLORS.textPrimary};
  margin-bottom: 0.375rem;

  svg {
    width: 14px;
    height: 14px;
    color: ${OS_LEGAL_COLORS.primaryBlue};
  }
`;

export const ToolCallSection = styled.div`
  margin-top: 0.375rem;
`;

export const ToolCallSectionLabel = styled.div`
  font-size: 0.6875rem;
  font-weight: 500;
  color: ${OS_LEGAL_COLORS.textSecondary};
  text-transform: uppercase;
  letter-spacing: 0.03em;
  margin-bottom: 0.25rem;
`;

export const ToolCallCodeBlock = styled.pre`
  margin: 0;
  padding: 0.375rem 0.5rem;
  background: rgba(0, 0, 0, 0.03);
  border: 1px solid rgba(0, 0, 0, 0.06);
  border-radius: 0.375rem;
  font-family: "Monaco", "Menlo", "Ubuntu Mono", monospace;
  font-size: 0.6875rem;
  color: #374151;
  line-height: 1.5;
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 120px;
  overflow-y: auto;
`;

// XSS safety note: Tool result and argument content is rendered as React text
// nodes (not via dangerouslySetInnerHTML), so HTML entities are auto-escaped.
// Content originates from backend agent tool execution, not user input.
export const ToolCallResultBlock = styled.div`
  margin: 0;
  padding: 0.375rem 0.5rem;
  background: rgba(34, 197, 94, 0.05);
  border: 1px solid rgba(34, 197, 94, 0.15);
  border-radius: 0.375rem;
  font-size: 0.75rem;
  color: ${OS_LEGAL_COLORS.successText};
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 120px;
  overflow-y: auto;
`;

// Streaming "now-thinking" ticker styled components
export const StreamingThoughtTickerWrapper = styled.div`
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.25rem 0;
  min-height: 1.5rem;
  font-size: 0.8125rem;
  line-height: 1.3;
  color: #6b7280;
  position: relative;
  overflow: hidden;
`;

/**
 * Soft-pulse + glow halo around the typed step icon. Signals "still working"
 * without changing the icon itself, so a tool_call still reads as a wrench,
 * a thought still reads as a lightning bolt, etc. The halo is the same
 * type-color the icon uses, faded down. Pure CSS keyframes (no JS timer).
 */
export const StreamingThoughtIcon = styled.div<{
  $type: TimelineEntry["type"];
}>`
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  width: 1rem;
  height: 1rem;
  color: ${(props) => typeColor(props.$type)};
  position: relative;

  svg {
    width: 0.875rem;
    height: 0.875rem;
    animation: streaming-icon-pulse 1.6s ease-in-out infinite;
  }

  &::after {
    content: "";
    position: absolute;
    inset: -0.25rem;
    border-radius: 50%;
    background: ${(props) => typeColor(props.$type)};
    opacity: 0.18;
    filter: blur(3px);
    animation: streaming-icon-halo 1.6s ease-in-out infinite;
    pointer-events: none;
  }

  @keyframes streaming-icon-pulse {
    0%,
    100% {
      transform: scale(1);
    }
    50% {
      transform: scale(1.08);
    }
  }
  @keyframes streaming-icon-halo {
    0%,
    100% {
      opacity: 0.12;
      transform: scale(0.85);
    }
    50% {
      opacity: 0.28;
      transform: scale(1.1);
    }
  }
`;

/**
 * A small breathing dot at the right edge of the ticker — the second
 * "still alive" cue that survives even when the icon pulse is subtle.
 */
export const StreamingPulseDot = styled.span`
  display: inline-block;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: ${OS_LEGAL_COLORS.primaryBlue};
  margin-left: 0.375rem;
  animation: streaming-pulse-dot 1.4s ease-in-out infinite;

  @keyframes streaming-pulse-dot {
    0%,
    100% {
      opacity: 0.35;
      transform: scale(1);
    }
    50% {
      opacity: 1;
      transform: scale(1.3);
    }
  }
`;

export const StreamingThoughtText = styled(motion.span)`
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  display: inline-block;
  max-width: 100%;
`;

export const SourceIndicator = styled.div<{ $isSelected?: boolean }>`
  position: absolute;
  right: 1rem;
  top: 1rem;
  z-index: 10;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.4rem 0.8rem;
  background: ${(props) =>
    props.$isSelected ? "#5C7C9D" : "rgba(92, 124, 157, 0.1)"};
  color: ${(props) => (props.$isSelected ? "white" : "#5C7C9D")};
  border-radius: 1rem;
  font-size: 0.8rem;
  font-weight: 500;
  transform: none;
  opacity: 1;
  transition: all 0.2s ease;
  cursor: pointer;
  backdrop-filter: blur(8px);
  border: 1px solid
    ${(props) =>
      props.$isSelected ? "transparent" : "rgba(92, 124, 157, 0.2)"};

  svg {
    width: 14px;
    height: 14px;
    transition: transform 0.2s ease;
  }

  &:hover {
    background: ${(props) =>
      props.$isSelected ? "#4A6B8C" : "rgba(92, 124, 157, 0.15)"};
    transform: translateY(-1px);
    box-shadow: 0 2px 8px rgba(92, 124, 157, 0.15);

    svg {
      transform: rotate(-15deg);
    }
  }

  @media (max-width: 768px) {
    padding: 0.3rem 0.6rem;
    font-size: 0.75rem;
  }
`;

export const TimelineIndicator = styled.div<{ $isSelected?: boolean }>`
  position: absolute;
  right: ${(props) => (props.$isSelected ? "8rem" : "1rem")};
  top: 1rem;
  z-index: 10;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.4rem 0.8rem;
  background: ${(props) =>
    props.$isSelected ? "#6B7280" : "rgba(156, 163, 175, 0.1)"};
  color: ${(props) => (props.$isSelected ? "white" : "#6B7280")};
  border-radius: 1rem;
  font-size: 0.8rem;
  font-weight: 500;
  transform: none;
  opacity: 1;
  transition: all 0.2s ease;
  cursor: pointer;
  backdrop-filter: blur(8px);
  border: 1px solid
    ${(props) =>
      props.$isSelected ? "transparent" : "rgba(156, 163, 175, 0.2)"};

  svg {
    width: 14px;
    height: 14px;
    transition: transform 0.2s ease;
  }

  &:hover {
    background: ${(props) =>
      props.$isSelected ? "#4B5563" : "rgba(156, 163, 175, 0.15)"};
    transform: translateY(-1px);
    box-shadow: 0 2px 8px rgba(156, 163, 175, 0.15);

    svg {
      transform: rotate(-15deg);
    }
  }

  @media (max-width: 768px) {
    padding: 0.3rem 0.6rem;
    font-size: 0.75rem;
    right: ${(props) => (props.$isSelected ? "6rem" : "1rem")};
  }
`;

export const ApprovalIndicator = styled.div<{
  $status: "approved" | "rejected" | "awaiting";
  $isSelected?: boolean;
}>`
  position: absolute;
  right: ${(props) => (props.$isSelected ? "8rem" : "1rem")};
  top: 3.5rem;
  z-index: 10;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.4rem 0.8rem;
  background: ${(props) => {
    if (props.$status === "approved") return "rgba(5, 150, 105, 0.1)";
    if (props.$status === "rejected") return "rgba(220, 38, 38, 0.1)";
    return "rgba(245, 158, 11, 0.1)";
  }};
  color: ${(props) => {
    if (props.$status === "approved") return OS_LEGAL_COLORS.greenDark;
    if (props.$status === "rejected") return OS_LEGAL_COLORS.danger;
    return OS_LEGAL_COLORS.folderIcon;
  }};
  border-radius: 1rem;
  font-size: 0.8rem;
  font-weight: 500;
  transform: none;
  opacity: 1;
  transition: all 0.2s ease;
  backdrop-filter: blur(8px);
  border: 1px solid
    ${(props) => {
      if (props.$status === "approved") return "rgba(5, 150, 105, 0.2)";
      if (props.$status === "rejected") return "rgba(220, 38, 38, 0.2)";
      return "rgba(245, 158, 11, 0.2)";
    }};

  svg {
    width: 14px;
    height: 14px;
  }

  @media (max-width: 768px) {
    padding: 0.3rem 0.6rem;
    font-size: 0.75rem;
    right: ${(props) => (props.$isSelected ? "6rem" : "1rem")};
  }
`;

export const Timestamp = styled.div`
  color: ${OS_LEGAL_COLORS.gray500};
  font-size: 0.75rem;
  margin-top: 0.25rem;
  padding-left: 0.25rem;

  @media (max-width: 480px) {
    font-size: 0.7rem;
    margin-top: 0.125rem;
  }
`;

export const MessageHeader = styled.div`
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.375rem;
  flex-wrap: wrap;

  @media (max-width: 480px) {
    margin-bottom: 0.25rem;
    gap: 0.375rem;
  }
`;

export const UserName = styled.div`
  font-size: 0.875rem;
  font-weight: 600;
  color: #1a1a1a;
  padding-left: 0.25rem;
  letter-spacing: -0.01em;

  @media (max-width: 480px) {
    font-size: 0.8rem;
  }
`;
