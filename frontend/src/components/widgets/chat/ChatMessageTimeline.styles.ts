/**
 * Styled components for the chat reasoning timeline panel and its
 * mid-stream "now-thinking" ticker (sibling of ChatMessageTimeline.tsx).
 *
 * Split out of the original ChatMessage.styles.ts barrel so the styles live
 * next to the component that consumes them. The streaming ticker styles are
 * co-located here because they share the typeColor helper with the timeline
 * row icons — keeping them in the same module avoids a small cross-file
 * import for a single helper.
 */
import styled from "styled-components";
import { motion } from "framer-motion";

import {
  OS_LEGAL_COLORS,
  blackAlpha,
  coolGray400Alpha,
  primaryBlueAlpha,
  whiteAlpha,
} from "../../../assets/configurations/osLegalStyles";
import { agentChipPaletteCss } from "../../chat/agentChipStyles";
import type { TimelineEntry } from "./types";

// Timeline styled components
export const TimelineContainer = styled.div`
  position: relative;
  background: ${whiteAlpha(0.7)};
  border-radius: 0.75rem;
  border: 1px solid ${coolGray400Alpha(0.2)};
  overflow: hidden;
  transition: all 0.2s ease-in-out;
  margin-top: 0.75rem;
`;

export const TimelineHeader = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.5rem 0.75rem;
  background: ${coolGray400Alpha(0.05)};
  border-bottom: 1px solid ${coolGray400Alpha(0.1)};
  cursor: pointer;
  transition: all 0.2s ease-in-out;

  &:hover {
    background: ${coolGray400Alpha(0.1)};
  }
`;

export const TimelineTitle = styled.div`
  font-size: 0.8125rem;
  font-weight: 500;
  color: ${OS_LEGAL_COLORS.coolGray500};
  display: flex;
  align-items: center;
  gap: 0.375rem;
`;

export const TimelineContent = styled(motion.div)`
  padding: 0.5rem 0.75rem;
  font-size: 0.875rem;
  color: ${OS_LEGAL_COLORS.chatSourcePreviewText};
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
      props.$active ? primaryBlueAlpha(0.2) : coolGray400Alpha(0.2)};
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
    background: ${blackAlpha(0.02)};
    border-radius: 0.25rem;
  }
`;

// Per-entry-type accent colors. Distinct hues let users skim a long timeline
// and visually group "thoughts" vs "tool calls" vs "results". Kept inline as
// a tiny lookup rather than promoting niche shades to OS_LEGAL_COLORS.
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
      return OS_LEGAL_COLORS.chatSourceBlue;
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
  color: ${(props) =>
    props.$expanded
      ? OS_LEGAL_COLORS.coolGray800
      : OS_LEGAL_COLORS.coolGray600};
  font-size: 0.8125rem;
  display: flex;
  align-items: center;
  gap: 0.25rem;
  cursor: pointer;
  user-select: none;

  &::after {
    content: ${(props) => (props.$expanded ? '"▼"' : '"▶"')};
    font-size: 0.5rem;
    color: ${OS_LEGAL_COLORS.coolGray400};
    transition: transform 0.2s ease;
  }
`;

export const TimelineItemText = styled.div`
  color: ${OS_LEGAL_COLORS.coolGray600};
  font-size: 0.75rem;
  line-height: 1.5;
  word-break: break-word;
  padding-left: 0.25rem;
`;

export const TimelineItemArgs = styled.div`
  margin-top: 0.25rem;
  padding: 0.375rem;
  background: ${blackAlpha(0.02)};
  border-radius: 0.375rem;
  border: 1px solid ${blackAlpha(0.05)};
  font-family: "Monaco", "Menlo", "Ubuntu Mono", monospace;
  font-size: 0.7rem;
  color: ${OS_LEGAL_COLORS.coolGray700};
  overflow-x: auto;
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
  color: ${OS_LEGAL_COLORS.coolGray500};
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

/**
 * Inline chip surfaced in a TimelineItemTitle whenever a tool_call /
 * tool_result entry can be attributed to a sub-agent — either via an
 * explicit ``agentSlug`` field forwarded from the WebSocket frame
 * (StreamRelay, delegation_tools.py) OR derived from a
 * ``delegate_to_<snake_slug>`` tool name on the persisted timeline.
 *
 * Palette is shared via ``agentChipPaletteCss`` so the timeline chip stays
 * visually in lock-step with the bubble-header, approval-modal, and
 * markdown @-mention chips ("one shape for agent identity").
 */
export const TimelineAgentChip = styled.span`
  display: inline-flex;
  align-items: center;
  gap: 0.15rem;
  padding: 0.05rem 0.4rem;
  margin-left: 0.125rem;
  border-radius: 0.5rem;
  font-size: 0.7rem;
  font-weight: 600;
  line-height: 1.2;
  ${agentChipPaletteCss};
  letter-spacing: -0.01em;
  white-space: nowrap;
  vertical-align: middle;

  & > [aria-hidden="true"] {
    opacity: 0.75;
  }
`;
