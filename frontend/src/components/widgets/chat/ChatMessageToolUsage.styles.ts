/**
 * Styled components for the chat tool-usage badge & popover
 * (sibling of ChatMessageToolUsage.tsx).
 *
 * Split out of the original ChatMessage.styles.ts barrel so the styles live
 * next to the component that consumes them.
 */
import styled from "styled-components";
import { motion } from "framer-motion";

import {
  OS_LEGAL_COLORS,
  blackAlpha,
  greenAlpha,
  primaryBlueAlpha,
  whiteAlpha,
} from "../../../assets/configurations/osLegalStyles";
import {
  POPOVER_Z_INDEX,
  TABLET_BREAKPOINT,
} from "../../../assets/configurations/constants";

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
    props.$isSelected ? OS_LEGAL_COLORS.primaryBlue : primaryBlueAlpha(0.1)};
  color: ${(props) =>
    props.$isSelected ? "white" : OS_LEGAL_COLORS.primaryBlue};
  border-radius: 1rem;
  font-size: 0.8rem;
  font-weight: 500;
  cursor: pointer;
  backdrop-filter: blur(8px);
  border: 1px solid
    ${(props) => (props.$isSelected ? "transparent" : primaryBlueAlpha(0.2))};
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
        : primaryBlueAlpha(0.18)};
    transform: translateY(-1px);
    box-shadow: 0 2px 8px ${primaryBlueAlpha(0.15)};
  }

  @media (max-width: ${TABLET_BREAKPOINT}px) {
    padding: 0.25rem 0.5rem;
    font-size: 0.75rem;
  }
`;

export const ToolPopover = styled(motion.div)`
  position: fixed;
  z-index: ${POPOVER_Z_INDEX};
  min-width: 320px;
  max-width: 440px;
  background: ${whiteAlpha(0.98)};
  backdrop-filter: blur(16px);
  border: 1px solid ${primaryBlueAlpha(0.15)};
  border-radius: 0.75rem;
  box-shadow: 0 8px 32px ${blackAlpha(0.12)},
    0 2px 8px ${primaryBlueAlpha(0.08)};
  overflow: hidden;

  @media (max-width: ${TABLET_BREAKPOINT}px) {
    min-width: 260px;
    max-width: 320px;
  }
`;

export const ToolPopoverHeader = styled.div`
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.75rem 1rem;
  background: ${primaryBlueAlpha(0.05)};
  border-bottom: 1px solid ${primaryBlueAlpha(0.1)};
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
    border-color: ${primaryBlueAlpha(0.2)};
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
  background: ${blackAlpha(0.03)};
  border: 1px solid ${blackAlpha(0.06)};
  border-radius: 0.375rem;
  font-family: "Monaco", "Menlo", "Ubuntu Mono", monospace;
  font-size: 0.6875rem;
  color: ${OS_LEGAL_COLORS.coolGray700};
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
  background: ${greenAlpha(0.05)};
  border: 1px solid ${greenAlpha(0.15)};
  border-radius: 0.375rem;
  font-size: 0.75rem;
  color: ${OS_LEGAL_COLORS.successText};
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 120px;
  overflow-y: auto;
`;
