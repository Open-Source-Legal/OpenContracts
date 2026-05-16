/**
 * Styled components for the top-level ChatMessage container, avatar, bubble,
 * indicators (sources / timeline / approval), timestamp, and header.
 *
 * Sibling style modules co-locate the rest:
 *  - ChatMessageSourcePreview.styles.ts → source list & per-source chip styles
 *  - ChatMessageTimeline.styles.ts      → reasoning timeline & streaming ticker
 *  - ChatMessageToolUsage.styles.ts     → tool-usage badge & popover
 */
import styled from "styled-components";
import { motion } from "framer-motion";

import {
  OS_LEGAL_COLORS,
  chatSourceBlueAlpha,
  whiteAlpha,
} from "../../../assets/configurations/osLegalStyles";
import {
  SMALL_MOBILE_BREAKPOINT,
  TABLET_BREAKPOINT,
} from "../../../assets/configurations/constants";
import { agentChipPaletteCss } from "../../chat/agentChipStyles";

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
      ? chatSourceBlueAlpha(0.05)
      : props.$isAssistant
      ? "rgba(247, 249, 252, 0.3)"
      : "rgba(247, 248, 249, 0.15)"};

  ${(props) =>
    props.$isSelected &&
    `
    box-shadow: inset 4px 0 0 ${OS_LEGAL_COLORS.chatSourceBlue};
  `}

  &:hover {
    background: ${(props) =>
      props.$isSelected
        ? chatSourceBlueAlpha(0.08)
        : props.$isAssistant
        ? "rgba(247, 249, 252, 0.4)"
        : "rgba(247, 248, 249, 0.25)"};
  }

  /* Add responsive padding */
  @media (max-width: ${TABLET_BREAKPOINT}px) {
    padding: 0.5rem 1rem;
    gap: 0.75rem;
  }

  @media (max-width: ${SMALL_MOBILE_BREAKPOINT}px) {
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
      ? `linear-gradient(135deg, ${OS_LEGAL_COLORS.chatAvatarAssistantStart} 0%, ${OS_LEGAL_COLORS.chatAvatarAssistantEnd} 100%)`
      : `linear-gradient(135deg, ${OS_LEGAL_COLORS.chatMessageTextUser} 0%, ${OS_LEGAL_COLORS.chatSourcePreviewText} 100%)`};
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
  @media (max-width: ${SMALL_MOBILE_BREAKPOINT}px) {
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
    props.$isAssistant ? whiteAlpha(0.7) : "rgba(247, 248, 249, 0.5)"};
  backdrop-filter: blur(12px);
  border-radius: 1.25rem;
  padding: 1.25rem 1.5rem;
  color: ${(props) =>
    props.$isAssistant
      ? OS_LEGAL_COLORS.chatMessageTextAssistant
      : OS_LEGAL_COLORS.chatMessageTextUser};
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
      props.$isAssistant ? whiteAlpha(0.5) : "rgba(247, 248, 249, 0.3)"};
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
    color: ${OS_LEGAL_COLORS.chatCodeText};
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
  @media (max-width: ${TABLET_BREAKPOINT}px) {
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
  @media (max-width: ${SMALL_MOBILE_BREAKPOINT}px) {
    border-radius: 0.875rem;
    padding: 0.75rem 0.875rem;

    &::before {
      display: none; /* Remove chat bubble arrow on very small screens */
    }
  }
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
    props.$isSelected
      ? OS_LEGAL_COLORS.chatSourceBlue
      : chatSourceBlueAlpha(0.1)};
  color: ${(props) =>
    props.$isSelected ? "white" : OS_LEGAL_COLORS.chatSourceBlue};
  border-radius: 1rem;
  font-size: 0.8rem;
  font-weight: 500;
  transform: none;
  opacity: 1;
  transition: all 0.2s ease;
  cursor: pointer;
  backdrop-filter: blur(8px);
  border: 1px solid
    ${(props) => (props.$isSelected ? "transparent" : chatSourceBlueAlpha(0.2))};

  svg {
    width: 14px;
    height: 14px;
    transition: transform 0.2s ease;
  }

  &:hover {
    background: ${(props) =>
      props.$isSelected
        ? OS_LEGAL_COLORS.chatSourceBlueHover
        : chatSourceBlueAlpha(0.15)};
    transform: translateY(-1px);
    box-shadow: 0 2px 8px ${chatSourceBlueAlpha(0.15)};

    svg {
      transform: rotate(-15deg);
    }
  }

  @media (max-width: ${TABLET_BREAKPOINT}px) {
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
    props.$isSelected
      ? OS_LEGAL_COLORS.coolGray500
      : "rgba(156, 163, 175, 0.1)"};
  color: ${(props) =>
    props.$isSelected ? "white" : OS_LEGAL_COLORS.coolGray500};
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
      props.$isSelected
        ? OS_LEGAL_COLORS.coolGray600
        : "rgba(156, 163, 175, 0.15)"};
    transform: translateY(-1px);
    box-shadow: 0 2px 8px rgba(156, 163, 175, 0.15);

    svg {
      transform: rotate(-15deg);
    }
  }

  @media (max-width: ${TABLET_BREAKPOINT}px) {
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

  @media (max-width: ${TABLET_BREAKPOINT}px) {
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

  @media (max-width: ${SMALL_MOBILE_BREAKPOINT}px) {
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

  @media (max-width: ${SMALL_MOBILE_BREAKPOINT}px) {
    margin-bottom: 0.25rem;
    gap: 0.375rem;
  }
`;

export const UserName = styled.div`
  font-size: 0.875rem;
  font-weight: 600;
  color: ${OS_LEGAL_COLORS.chatUsernameText};
  padding-left: 0.25rem;
  letter-spacing: -0.01em;

  @media (max-width: ${SMALL_MOBILE_BREAKPOINT}px) {
    font-size: 0.8rem;
  }
`;

/**
 * Attribution chip rendered in the assistant bubble header when the
 * underlying ChatMessage has an `agentConfiguration` set — indicating
 * the response was authored by a pinned sub-agent (rich-mention agent
 * delegation, Issue #623 / #689) rather than the default conductor.
 *
 * Palette is shared via ``agentChipPaletteCss`` so the bubble-header,
 * timeline, approval-modal, and markdown @-mention chips all reference
 * one token set.
 */
export const SubAgentAttributionChip = styled.span`
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0.125rem 0.5rem;
  border-radius: 0.625rem;
  font-size: 0.75rem;
  font-weight: 500;
  line-height: 1.2;
  ${agentChipPaletteCss};
  letter-spacing: -0.01em;
  white-space: nowrap;

  /* Soft glyph marker — visually distinct from the @-prefix text */
  & > [aria-hidden="true"] {
    opacity: 0.75;
    font-weight: 600;
  }

  @media (max-width: ${SMALL_MOBILE_BREAKPOINT}px) {
    font-size: 0.7rem;
    padding: 0.1rem 0.4rem;
  }
`;
