import React, { useState, useEffect, useRef } from "react";
import styled from "styled-components";
import { motion, AnimatePresence } from "framer-motion";
import {
  User,
  Bot,
  Pin,
  ChevronUp,
  ChevronDown,
  Clock,
  Zap,
  MessageSquare,
  Wrench,
  CheckCircle,
  Activity,
  Plus,
  XCircle,
  AlertCircle,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useSetAtom, useAtomValue } from "jotai";
import { chatSourcesAtom } from "../../annotator/context/ChatSourceAtom";
import { useMemo } from "react";
import { useCreateAnnotation } from "../../annotator/hooks/AnnotationHooks";
import { useCorpusState } from "../../annotator/context/CorpusAtom";
import { useSelectedDocument } from "../../annotator/context/DocumentAtom";
import {
  ServerTokenAnnotation,
  ServerSpanAnnotation,
} from "../../annotator/types/annotations";
import {
  MultipageAnnotationJson,
  SinglePageAnnotationJson,
  BoundingBox,
  SpanAnnotationJson,
} from "../../types";
import { AnnotationLabelType } from "../../../types/graphql-api";
import { TOOL_UNKNOWN_LABEL } from "../../../assets/configurations/constants";

// Timeline entry type based on the schema
export interface TimelineEntry {
  type:
    | "thought"
    | "content"
    | "tool_call"
    | "tool_result"
    | "sources"
    | "status";
  text?: string;
  tool?: string;
  args?: Record<string, unknown>;
  result?: string;
  count?: number;
  metadata?: Record<string, any>;
  msg?: string;
}

// Paired tool call info extracted from timeline for the tool usage popover
interface ToolCallInfo {
  /** Stable identifier for React keys (tool name + ordinal index) */
  id: string;
  tool: string;
  args?: Record<string, unknown>;
  result?: string;
}

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

const MessageContainer = styled(motion.div)<{
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

const Avatar = styled.div<{ $isAssistant: boolean }>`
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
  color: ${(props) => (props.$isAssistant ? "white" : "#e2e8f0")};
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

const ContentContainer = styled.div`
  flex: 1;
  min-width: 0;
`;

const MessageContent = styled.div<{ $isAssistant: boolean }>`
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
        : "linear-gradient(135deg, #e9ecef, #f1f3f5)"};
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
    border: 1px solid #dee2e6;
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

const SourcesContainer = styled.div`
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  margin-top: 0.75rem;
  transition: all 0.2s ease-in-out;
`;

const SourcePreviewContainer = styled.div`
  position: relative;
  background: rgba(255, 255, 255, 0.7);
  border-radius: 0.75rem;
  border: 1px solid rgba(92, 124, 157, 0.2);
  overflow: hidden;
  transition: all 0.2s ease-in-out;
`;

const SourcePreviewHeader = styled.div`
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

const SourcePreviewTitle = styled.div`
  font-size: 0.875rem;
  font-weight: 500;
  color: #5c7c9d;
  display: flex;
  align-items: center;
  gap: 0.5rem;
`;

const SourcePreviewContent = styled(motion.div)`
  padding: 0.75rem 1rem;
  font-size: 0.875rem;
  color: #4a5568;
  max-height: 300px;
  overflow-y: auto;
`;

const SourceList = styled.div`
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  padding: 0.25rem;
`;

const SourceChip = styled.div<{ $isSelected: boolean }>`
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

const SourceHeader = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
`;

const SourceTitle = styled.div<{ $isSelected: boolean }>`
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-weight: 500;
  color: ${(props) => (props.$isSelected ? "#2d3748" : "#4a5568")};
`;

const SourceText = styled(motion.div)<{ $isExpanded: boolean }>`
  font-size: 0.8125rem;
  color: #4a5568;
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

const ExpandButton = styled.button<{ $isExpanded: boolean }>`
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

// NEW styled components for annotation from source
const AnnotateButton = styled.button`
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

const LabelMenu = styled.div`
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

const LabelButton = styled.button`
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
// END new styled components

// Timeline styled components
const TimelineContainer = styled.div`
  position: relative;
  background: rgba(255, 255, 255, 0.7);
  border-radius: 0.75rem;
  border: 1px solid rgba(156, 163, 175, 0.2);
  overflow: hidden;
  transition: all 0.2s ease-in-out;
  margin-top: 0.75rem;
`;

const TimelineHeader = styled.div`
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

const TimelineTitle = styled.div`
  font-size: 0.8125rem;
  font-weight: 500;
  color: #6b7280;
  display: flex;
  align-items: center;
  gap: 0.375rem;
`;

const TimelineContent = styled(motion.div)`
  padding: 0.5rem 0.75rem;
  font-size: 0.875rem;
  color: #4a5568;
  max-height: 400px;
  overflow-y: auto;
  scroll-behavior: smooth;
  position: relative;
`;

const AutoScrollIndicator = styled(motion.div)<{ $active: boolean }>`
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
  color: ${(props) => (props.$active ? "#3b82f6" : "#9ca3af")};
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

const TimelineList = styled.div`
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
`;

const TimelineItem = styled.div<{ $type: TimelineEntry["type"] }>`
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

const TimelineIcon = styled.div<{ $type: TimelineEntry["type"] }>`
  display: flex;
  align-items: center;
  justify-content: center;
  width: 1.25rem;
  height: 1.25rem;
  border-radius: 50%;
  flex-shrink: 0;
  background: transparent;
  color: ${(props) => {
    switch (props.$type) {
      case "thought":
        return "#a855f7";
      case "tool_call":
        return "#3b82f6";
      case "tool_result":
        return "#22c55e";
      case "content":
        return "#f97316";
      case "sources":
        return "#5c7c9d";
      case "status":
        return "#9ca3af";
      default:
        return "#9ca3af";
    }
  }};

  svg {
    width: 0.875rem;
    height: 0.875rem;
  }
`;

const TimelineItemContent = styled.div`
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
`;

const TimelineItemTitle = styled.div<{ $expanded?: boolean }>`
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

const TimelineItemText = styled.div`
  color: #4b5563;
  font-size: 0.75rem;
  line-height: 1.5;
  word-break: break-word;
  padding-left: 0.25rem;
`;

const TimelineItemArgs = styled.div`
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
const ToolBadgeWrapper = styled.div`
  position: relative;
  display: inline-flex;
`;

const ToolBadge = styled.div<{ $isSelected?: boolean }>`
  display: flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.35rem 0.7rem;
  background: ${(props) =>
    props.$isSelected ? "#3b82f6" : "rgba(59, 130, 246, 0.1)"};
  color: ${(props) => (props.$isSelected ? "white" : "#3b82f6")};
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
      props.$isSelected ? "#2563eb" : "rgba(59, 130, 246, 0.18)"};
    transform: translateY(-1px);
    box-shadow: 0 2px 8px rgba(59, 130, 246, 0.15);
  }

  @media (max-width: 768px) {
    padding: 0.25rem 0.5rem;
    font-size: 0.75rem;
  }
`;

const ToolPopover = styled(motion.div)`
  position: absolute;
  top: calc(100% + 0.5rem);
  right: 0;
  z-index: 100;
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
    right: -1rem;
  }
`;

const ToolPopoverHeader = styled.div`
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.75rem 1rem;
  background: rgba(59, 130, 246, 0.05);
  border-bottom: 1px solid rgba(59, 130, 246, 0.1);
  font-size: 0.8125rem;
  font-weight: 600;
  color: #1e40af;

  svg {
    width: 16px;
    height: 16px;
  }
`;

const ToolPopoverBody = styled.div`
  max-height: 400px;
  overflow-y: auto;
  padding: 0.5rem;
`;

const ToolCallCard = styled.div`
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

const ToolCallName = styled.div`
  display: flex;
  align-items: center;
  gap: 0.375rem;
  font-size: 0.8125rem;
  font-weight: 600;
  color: #1e293b;
  margin-bottom: 0.375rem;

  svg {
    width: 14px;
    height: 14px;
    color: #3b82f6;
  }
`;

const ToolCallSection = styled.div`
  margin-top: 0.375rem;
`;

const ToolCallSectionLabel = styled.div`
  font-size: 0.6875rem;
  font-weight: 500;
  color: #64748b;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  margin-bottom: 0.25rem;
`;

const ToolCallCodeBlock = styled.pre`
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
const ToolCallResultBlock = styled.div`
  margin: 0;
  padding: 0.375rem 0.5rem;
  background: rgba(34, 197, 94, 0.05);
  border: 1px solid rgba(34, 197, 94, 0.15);
  border-radius: 0.375rem;
  font-size: 0.75rem;
  color: #166534;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 120px;
  overflow-y: auto;
`;

interface SourceItemProps {
  messageId: string;
  text: string;
  index: number;
  isSelected: boolean;
  onClick: (e: React.MouseEvent<HTMLDivElement>) => void;
  availableLabels: AnnotationLabelType[];
  createAnnotation: (a: ServerTokenAnnotation | ServerSpanAnnotation) => void;
}

const SourceItem: React.FC<SourceItemProps> = ({
  messageId,
  text,
  index,
  isSelected,
  onClick,
  availableLabels,
  createAnnotation,
}) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const [labelMenuOpen, setLabelMenuOpen] = useState(false);

  const chatStateValue = useAtomValue(chatSourcesAtom);
  const { selectedDocument } = useSelectedDocument();

  // UI handlers
  const toggleExpand = (e: React.MouseEvent<HTMLButtonElement>) => {
    e.stopPropagation();
    setIsExpanded(!isExpanded);
  };

  const handleAnnotateClick = (e: React.MouseEvent<HTMLButtonElement>) => {
    e.stopPropagation();
    setLabelMenuOpen((prev) => !prev);
  };

  const handleLabelSelect = (label: any) => {
    const msg = chatStateValue.messages.find(
      (m: any) => m.messageId === messageId
    );
    if (!msg) return setLabelMenuOpen(false);
    const sourceData = msg.sources[index];
    if (!sourceData) return setLabelMenuOpen(false);

    try {
      if (selectedDocument?.fileType?.startsWith("text/")) {
        if (
          sourceData.startIndex === undefined ||
          sourceData.endIndex === undefined
        )
          return setLabelMenuOpen(false);
        const spanJson: SpanAnnotationJson = {
          start: sourceData.startIndex,
          end: sourceData.endIndex,
        };
        const newAnnot = new ServerSpanAnnotation(
          sourceData.page ?? 0,
          label,
          sourceData.rawText,
          false,
          spanJson,
          [],
          false,
          false,
          false
        );
        createAnnotation(newAnnot);
      } else {
        const mpJson: MultipageAnnotationJson = {};
        Object.entries(sourceData.boundsByPage).forEach(([pStr, bounds]) => {
          const pNum = parseInt(pStr, 10);
          mpJson[pNum] = {
            bounds: bounds as BoundingBox,
            tokensJsons: sourceData.tokensByPage[pNum] || [],
            rawText: sourceData.rawText,
          };
        });
        const firstPage = Number(Object.keys(mpJson)[0] || 0);
        const newAnnot = new ServerTokenAnnotation(
          firstPage,
          label,
          sourceData.rawText,
          false,
          mpJson,
          [],
          false,
          false,
          false
        );
        createAnnotation(newAnnot);
      }
    } catch (err) {
      /* eslint-disable no-console */
      console.error("Failed to create annotation from source", err);
    } finally {
      setLabelMenuOpen(false);
    }
  };

  return (
    <SourceChip
      $isSelected={isSelected}
      onClick={onClick}
      className="source-chip"
    >
      <SourceHeader>
        <SourceTitle $isSelected={isSelected}>
          <Pin size={12} /> Source {index + 1}
        </SourceTitle>
        <div style={{ display: "flex", gap: "0.25rem" }}>
          <AnnotateButton title="Annotate" onClick={handleAnnotateClick}>
            <Plus size={14} /> Annotate
          </AnnotateButton>
          <ExpandButton
            $isExpanded={isExpanded}
            onClick={toggleExpand}
            title={isExpanded ? "Show less" : "Show more"}
          >
            {isExpanded ? "Show less" : "Show more"}
            <ChevronDown />
          </ExpandButton>
        </div>
      </SourceHeader>
      {labelMenuOpen && (
        <LabelMenu>
          {availableLabels.map((lab) => (
            <LabelButton key={lab.id} onClick={() => handleLabelSelect(lab)}>
              <span
                style={{
                  marginRight: 6,
                  width: 8,
                  height: 8,
                  background: lab.color || "#1a75bc",
                  display: "inline-block",
                  borderRadius: 4,
                }}
              />
              {lab.text}
            </LabelButton>
          ))}
        </LabelMenu>
      )}
      <SourceText
        $isExpanded={isExpanded}
        initial={false}
        animate={{ height: isExpanded ? "auto" : "3em" }}
        transition={{ duration: 0.2 }}
      >
        {text}
      </SourceText>
    </SourceChip>
  );
};

interface SourcePreviewProps {
  messageId: string;
  sources: Array<{ text: string; onClick?: () => void }>;
  selectedIndex?: number;
  onSourceSelect: (index: number) => void;
  availableLabels: AnnotationLabelType[];
  createAnnotation: (a: ServerTokenAnnotation | ServerSpanAnnotation) => void;
}

const SourcePreview: React.FC<SourcePreviewProps> = ({
  messageId,
  sources,
  selectedIndex,
  onSourceSelect,
  availableLabels,
  createAnnotation,
}) => {
  const [isExpanded, setIsExpanded] = useState(false);

  const handleHeaderClick = (e: React.MouseEvent<HTMLDivElement>) => {
    e.stopPropagation();
    setIsExpanded(!isExpanded);
  };

  return (
    <SourcePreviewContainer
      className="source-preview-container"
      onClick={(e: React.MouseEvent<HTMLDivElement>) => e.stopPropagation()}
    >
      <SourcePreviewHeader onClick={handleHeaderClick}>
        <SourcePreviewTitle>
          <Pin size={14} />
          {sources.length} {sources.length === 1 ? "Source" : "Sources"}
        </SourcePreviewTitle>
        {isExpanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
      </SourcePreviewHeader>
      <AnimatePresence>
        {isExpanded && (
          <SourcePreviewContent
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
          >
            <SourceList>
              {sources.map((source, index) => (
                <SourceItem
                  key={index}
                  messageId={messageId}
                  text={source.text}
                  index={index}
                  isSelected={selectedIndex === index}
                  onClick={(e: React.MouseEvent<HTMLDivElement>) => {
                    e.stopPropagation();
                    onSourceSelect(index);
                    source.onClick?.();
                  }}
                  availableLabels={availableLabels}
                  createAnnotation={createAnnotation}
                />
              ))}
            </SourceList>
          </SourcePreviewContent>
        )}
      </AnimatePresence>
    </SourcePreviewContainer>
  );
};

// Helper function to get icon for timeline entry type
const getTimelineIcon = (type: TimelineEntry["type"]) => {
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
    default:
      return <Clock />;
  }
};

// Helper function to get title for timeline entry type
const getTimelineTitle = (entry: TimelineEntry) => {
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
    default:
      return "Timeline Entry";
  }
};

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
 */
const ToolUsageIndicator: React.FC<{
  timeline: TimelineEntry[];
}> = ({ timeline }) => {
  const toolCalls = useMemo(() => extractToolCalls(timeline), [timeline]);
  const [isOpen, setIsOpen] = useState(false);
  const closeTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Cleanup timeout on unmount to prevent memory leaks
  useEffect(() => {
    return () => {
      if (closeTimeoutRef.current) {
        clearTimeout(closeTimeoutRef.current);
      }
    };
  }, []);

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

  const popoverId = `tool-popover-${toolCalls.length}`;

  return (
    <ToolBadgeWrapper
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
      <AnimatePresence>
        {isOpen && (
          <ToolPopover
            id={popoverId}
            role="dialog"
            aria-label={`Tool usage details: ${toolCalls.length} ${
              toolCalls.length === 1 ? "call" : "calls"
            }`}
            initial={{ opacity: 0, y: -4, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -4, scale: 0.98 }}
            transition={{ duration: 0.15, ease: "easeOut" }}
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
      </AnimatePresence>
    </ToolBadgeWrapper>
  );
};

interface TimelinePreviewProps {
  timeline: TimelineEntry[];
  collapsed?: boolean;
  /**
   * When true, only the most recent entry will start expanded – previous ones start collapsed.
   * This is useful while the assistant is still streaming and we want a concise view.
   */
  expandLatestOnly?: boolean;
  onToggle?: () => void;
}

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

const TimelinePreview: React.FC<TimelinePreviewProps> = ({
  timeline,
  collapsed = true,
  expandLatestOnly = false,
  onToggle,
}) => {
  const [isExpanded, setIsExpanded] = useState(!collapsed);
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const [isNearBottom, setIsNearBottom] = useState(true);
  const prevTimelineLengthRef = useRef(timeline.length);

  /* Expansion state per entry ----------------------------------------- */
  const buildInitialExpandedStates = () =>
    timeline.map((_, idx) =>
      expandLatestOnly ? idx === timeline.length - 1 : true
    );

  const [expandedStates, setExpandedStates] = useState<boolean[]>(
    buildInitialExpandedStates()
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
      setTimeout(() => {
        if (scrollContainerRef.current) {
          scrollContainerRef.current.scrollTop =
            scrollContainerRef.current.scrollHeight;
        }
      }, 50);
    }

    prevTimelineLengthRef.current = timeline.length;
  }, [timeline.length, isNearBottom, isExpanded]);

  // Initial scroll to bottom when first expanded
  useEffect(() => {
    if (isExpanded && scrollContainerRef.current) {
      setTimeout(() => {
        scrollToBottom();
      }, 100);
    }
  }, [isExpanded]);

  // Sync header expansion with `collapsed` prop
  useEffect(() => {
    setIsExpanded(!collapsed);
  }, [collapsed]);

  // Maintain expandedStates length & default for newest entry while streaming
  useEffect(() => {
    setExpandedStates((prev) => {
      if (timeline.length > prev.length) {
        const additional = timeline.length - prev.length;
        const newStates = [...prev, ...Array(additional).fill(false)];

        if (expandLatestOnly) {
          newStates[newStates.length - 1] = true; // latest expanded
        }
        return newStates;
      }

      if (timeline.length < prev.length) {
        return prev.slice(0, timeline.length);
      }

      return prev;
    });
  }, [timeline.length, expandLatestOnly]);

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
                  // Re-sync when expandedStates updates
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

const SourceIndicator = styled.div<{ $isSelected?: boolean }>`
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

const TimelineIndicator = styled.div<{ $isSelected?: boolean }>`
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

const ApprovalIndicator = styled.div<{
  $status: "approved" | "rejected" | "awaiting";
  $isSelected?: boolean;
}>`
  position: absolute;
  right: ${(props) => (props.$isSelected ? "8rem" : "1rem")};
  top: ${(props) => (props.$isSelected ? "3.5rem" : "3.5rem")};
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
    if (props.$status === "approved") return "#059669";
    if (props.$status === "rejected") return "#dc2626";
    return "#f59e0b";
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

const Timestamp = styled.div`
  color: #868e96;
  font-size: 0.75rem;
  margin-top: 0.25rem;
  padding-left: 0.25rem;

  @media (max-width: 480px) {
    font-size: 0.7rem;
    margin-top: 0.125rem;
  }
`;

// Processing text - extracted for i18n readiness
const PROCESSING_TEXT = "Agent is thinking...";
const PROCESSING_ARIA_LABEL = "Agent is processing your request";

// Processing indicator for when agent is working but hasn't sent content yet
const ProcessingContainer = styled.div`
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 1.25rem 1.5rem;
  background: rgba(255, 255, 255, 0.7);
  backdrop-filter: blur(12px);
  border-radius: 1.25rem;
  border: 1px solid rgba(255, 255, 255, 0.5);
  box-shadow: 0 2px 8px rgba(23, 25, 35, 0.04);
  margin-bottom: 0.25rem;
  /* Fade to subtle static state after 30s to reduce visual noise on long processing */
  animation: processingFadeToSubtle 30s ease-out forwards;

  @keyframes processingFadeToSubtle {
    0%,
    90% {
      opacity: 1;
    }
    100% {
      opacity: 0.6;
    }
  }
`;

const ProcessingDots = styled.div`
  display: flex;
  align-items: center;
  gap: 0.25rem;
`;

const ProcessingDot = styled.span<{ $delay: number }>`
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: linear-gradient(135deg, #2185d0 0%, #1678c2 100%);
  animation: processingBounce 1.4s ease-in-out infinite;
  animation-delay: ${(props) => props.$delay}s;
  will-change: transform, opacity;

  @keyframes processingBounce {
    0%,
    80%,
    100% {
      transform: scale(0.6);
      opacity: 0.4;
    }
    40% {
      transform: scale(1);
      opacity: 1;
    }
  }
`;

const ProcessingText = styled.span`
  font-size: 0.9rem;
  color: #5c7c9d;
  font-weight: 500;
`;

const ProcessingIndicator: React.FC = () => (
  <ProcessingContainer
    role="status"
    aria-live="polite"
    aria-label={PROCESSING_ARIA_LABEL}
    data-testid="processing-indicator"
  >
    <ProcessingDots aria-hidden="true">
      <ProcessingDot $delay={0} />
      <ProcessingDot $delay={0.2} />
      <ProcessingDot $delay={0.4} />
    </ProcessingDots>
    <ProcessingText>{PROCESSING_TEXT}</ProcessingText>
  </ProcessingContainer>
);

const MessageHeader = styled.div`
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

const UserName = styled.div`
  font-size: 0.875rem;
  font-weight: 600;
  color: #1a1a1a;
  padding-left: 0.25rem;
  letter-spacing: -0.01em;

  @media (max-width: 480px) {
    font-size: 0.8rem;
  }
`;

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
    if (selectedDocument?.fileType?.startsWith("text/")) return humanSpanLabels;
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

  const showTimelineOnly =
    isAssistant &&
    effectiveHasTimeline &&
    (!isComplete || content.trim().length === 0);

  // Show processing indicator when assistant message is incomplete with no content and no timeline
  const showProcessingIndicator =
    isAssistant &&
    !isComplete &&
    content.trim().length === 0 &&
    !effectiveHasTimeline;

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
          {sources.length > 0 ? `${sources.length} sources` : "View sources"}
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
        {/* Processing indicator - shown when agent is working but no content/timeline yet */}
        {showProcessingIndicator && <ProcessingIndicator />}
        {/* Standard message content bubble */}
        {!showTimelineOnly && !showProcessingIndicator && (
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
            {/* Collapsible timeline once message is complete */}
            {effectiveHasTimeline && (
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
        {/* Streaming timeline only (no bubble) */}
        {showTimelineOnly && (
          <TimelinePreview
            timeline={timeline}
            collapsed={false}
            expandLatestOnly={true}
          />
        )}
        <Timestamp>{timestamp}</Timestamp>
      </ContentContainer>
    </MessageContainer>
  );
};
