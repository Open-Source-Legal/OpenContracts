/**
 * Styled components for the chat source-preview list & per-source chip
 * (sibling of ChatMessageSourcePreview.tsx).
 *
 * Split out of the original ChatMessage.styles.ts barrel so the styles live
 * next to the component that consumes them.
 */
import styled from "styled-components";
import { motion } from "framer-motion";

import {
  OS_LEGAL_COLORS,
  blackAlpha,
  chatSourceBlueAlpha,
  whiteAlpha,
} from "../../../assets/configurations/osLegalStyles";
import { POPOVER_Z_INDEX } from "../../../assets/configurations/constants";

export const SourcePreviewContainer = styled.div`
  position: relative;
  background: ${whiteAlpha(0.7)};
  border-radius: 0.75rem;
  border: 1px solid ${chatSourceBlueAlpha(0.2)};
  overflow: hidden;
  transition: all 0.2s ease-in-out;
`;

export const SourcePreviewHeader = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.75rem 1rem;
  background: ${chatSourceBlueAlpha(0.05)};
  border-bottom: 1px solid ${chatSourceBlueAlpha(0.1)};
  cursor: pointer;
  transition: all 0.2s ease-in-out;

  &:hover {
    background: ${chatSourceBlueAlpha(0.1)};
  }
`;

export const SourcePreviewTitle = styled.div`
  font-size: 0.875rem;
  font-weight: 500;
  color: ${OS_LEGAL_COLORS.chatSourceBlue};
  display: flex;
  align-items: center;
  gap: 0.5rem;
`;

export const SourcePreviewContent = styled(motion.div)`
  padding: 0.75rem 1rem;
  font-size: 0.875rem;
  color: ${OS_LEGAL_COLORS.chatSourcePreviewText};
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
    props.$isSelected ? chatSourceBlueAlpha(0.15) : whiteAlpha(0.7)};
  border: 1px solid
    ${(props) =>
      props.$isSelected ? chatSourceBlueAlpha(0.3) : chatSourceBlueAlpha(0.1)};
  border-radius: 0.75rem;
  font-size: 0.875rem;
  cursor: pointer;
  transition: all 0.2s ease-in-out;

  &:hover {
    background: ${(props) =>
      props.$isSelected ? chatSourceBlueAlpha(0.2) : whiteAlpha(0.9)};
    border-color: ${chatSourceBlueAlpha(0.3)};
    transform: translateY(-1px);
    box-shadow: 0 2px 8px ${chatSourceBlueAlpha(0.1)};
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
  color: ${OS_LEGAL_COLORS.chatSourceBlue};
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 0.25rem;
  font-size: 0.75rem;
  font-weight: 500;
  transition: all 0.2s ease-in-out;

  &:hover {
    color: ${OS_LEGAL_COLORS.chatSourceBlueHover};
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
  color: ${OS_LEGAL_COLORS.chatSourceBlue};
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 0.25rem;
  font-size: 0.75rem;
  font-weight: 500;
  transition: all 0.2s ease-in-out;

  &:hover {
    color: ${OS_LEGAL_COLORS.chatSourceBlueHover};
  }
`;

export const LabelMenu = styled.div`
  position: absolute;
  top: 2.2rem;
  right: 0.5rem;
  background: ${whiteAlpha(0.98)};
  backdrop-filter: blur(12px);
  border: 1px solid rgba(200, 200, 200, 0.8);
  border-radius: 0.5rem;
  padding: 0.5rem;
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  z-index: ${POPOVER_Z_INDEX};
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
    background: ${blackAlpha(0.05)};
  }
`;
