import { motion } from "framer-motion";
import styled from "styled-components";
import { Button } from "@os-legal/ui";
import { color } from "../../../theme/colors";
import { MOBILE_VIEW_BREAKPOINT } from "../../../assets/configurations/constants";
import { OS_LEGAL_COLORS } from "../../../assets/configurations/osLegalStyles";
import {
  ConversationGrid,
  ChatInputContainer,
  ChatInput,
  SendButton,
  FilterContainer,
} from "../../knowledge_base/document/ChatContainers";

export const ConversationHeader = styled.div`
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1.25rem 1.5rem;
  border-bottom: 1px solid rgba(0, 0, 0, 0.08);
  background: rgba(255, 255, 255, 0.98);
  backdrop-filter: blur(8px);
  position: sticky;
  top: 0;
  z-index: 10;

  h2 {
    font-size: 1.5rem;
    font-weight: 600;
    color: #1a202c;
    margin: 0;
  }

  .actions {
    display: flex;
    gap: 0.75rem;
  }

  @media (max-width: 768px) {
    padding: 1rem;

    h2 {
      font-size: 1.25rem;
    }

    .actions button {
      padding: 0.5rem 0.75rem !important;
      font-size: 0.85rem !important;
    }
  }
`;

export const EnhancedConversationGrid = styled(ConversationGrid)`
  display: flex;
  flex-direction: column;
  gap: 0;
  padding: 0;
  width: 100%;
  overflow-y: auto;
  background: ${color.N2};
`;

export const EnhancedConversationCard = styled(motion.div)`
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 1rem 1.5rem;
  background: ${color.N1};
  border-bottom: 1px solid ${color.N4};
  cursor: pointer;
  transition: all 0.15s ease;
  position: relative;

  &:hover {
    background: ${color.G1};
  }

  &:active {
    background: ${color.G2};
  }
`;

export const ChatItemIcon = styled.div`
  width: 40px;
  height: 40px;
  border-radius: 10px;
  background: linear-gradient(135deg, ${color.B2} 0%, ${color.B3} 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;

  svg {
    width: 20px;
    height: 20px;
    color: ${color.B7};
  }
`;

export const ChatItemContent = styled.div`
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
`;

export const ChatItemTitle = styled.div`
  font-size: 0.9375rem;
  font-weight: 600;
  color: ${color.N10};
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
`;

export const ChatItemMeta = styled.div`
  display: flex;
  align-items: center;
  gap: 0.75rem;
  font-size: 0.8125rem;
  color: ${color.N6};
`;

export const MessageCountBadge = styled.div`
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 24px;
  height: 24px;
  padding: 0 8px;
  border-radius: 12px;
  background: ${color.B4};
  color: white;
  font-size: 0.75rem;
  font-weight: 600;
  flex-shrink: 0;
`;

export const EnhancedFilterContainer = styled(FilterContainer)`
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.75rem 1.5rem;
  background: ${color.N1};
  border-bottom: 1px solid ${color.N4};
  margin: 0;
  border-radius: 0;
  position: sticky;
  top: 0;
  z-index: 10;
`;

export const NewChatButton = styled(motion.button)`
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.5rem 1rem;
  border: none;
  border-radius: 6px;
  background: ${color.G6};
  color: white;
  font-size: 0.875rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
  white-space: nowrap;
  flex-shrink: 0;

  &:hover {
    background: ${color.G7};
  }

  svg {
    width: 16px;
    height: 16px;
  }

  @media (max-width: 480px) {
    padding: 0.5rem;
    span {
      display: none;
    }
  }
`;

export const ToolbarDivider = styled.div`
  width: 1px;
  height: 24px;
  background: ${color.N4};
  margin: 0 0.25rem;
  flex-shrink: 0;
`;

export const EmptyStateContainer = styled.div`
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 4rem 2rem;
  text-align: center;
  flex: 1;
  background: ${color.N2};
`;

export const EmptyStateIcon = styled.div`
  width: 80px;
  height: 80px;
  border-radius: 50%;
  background: linear-gradient(135deg, ${color.G1} 0%, ${color.G2} 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 1.5rem;

  svg {
    width: 36px;
    height: 36px;
    color: ${color.G6};
  }
`;

export const EmptyStateTitle = styled.h3`
  font-size: 1.25rem;
  font-weight: 700;
  margin: 0 0 0.5rem;
  color: ${color.N10};
  letter-spacing: -0.025em;
`;

export const EmptyStateDescription = styled.p`
  color: ${color.N7};
  max-width: 360px;
  margin: 0 0 1.5rem;
  font-size: 0.9375rem;
  line-height: 1.5;
`;

export const EmptyStateButton = styled(motion.button)`
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.75rem 1.5rem;
  border: none;
  border-radius: 8px;
  background: ${color.G6};
  color: white;
  font-size: 0.9375rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;

  &:hover {
    background: ${color.G7};
    transform: translateY(-1px);
  }

  svg {
    width: 18px;
    height: 18px;
  }
`;

export const ChatContainer = styled.div`
  display: flex;
  flex-direction: column;
  height: 100%;
  width: 100%;
  overflow: hidden;
  background: ${OS_LEGAL_COLORS.surfaceHover};
  position: relative;
  margin: 0;
  padding: 0;
  border-radius: 0;
  flex: 1;
  min-height: 0; /* Important for flex children */
  max-height: 100%; /* Never exceed parent's height */

  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    /* Removed position: fixed to prevent covering parent navigation and bottom nav */
    /* Container now works as a normal flex child */
    height: 100%; /* Fill parent container */
    max-height: 100%; /* Don't exceed parent's height */
  }
`;

export const ConversationIndicator = styled.div`
  display: flex;
  flex-direction: column;
  height: 100%;
  width: 100%;
  overflow: hidden;
  position: relative;
  min-height: 0; /* Important for flex children to properly overflow */
  flex: 1;
  max-height: 100%; /* Never exceed parent's height */

  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    height: 100%; /* Fill parent container */
    max-height: 100%; /* Don't exceed parent's height */
  }
`;

export const ChatInputWrapper = styled.div`
  flex-shrink: 0;
  width: 100%;
  background: rgba(255, 255, 255, 0.98);
  backdrop-filter: blur(10px);
  border-top: 1px solid rgba(0, 0, 0, 0.08);
  box-shadow: 0 -2px 10px rgba(0, 0, 0, 0.04);
  position: sticky;
  bottom: 0;
  z-index: 50; /* Ensure it's above other content */

  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    position: sticky;
    bottom: 0; /* Back to bottom - FAB is now compact and out of the way */
    /* Ensure it stays at bottom even when keyboard appears */
    transform: translateZ(0); /* Force GPU acceleration */
  }
`;

export const ProcessingIndicator = styled(motion.div)`
  display: inline-flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.875rem 1.5rem;
  background: linear-gradient(135deg, #f0f7ff 0%, #e6f2ff 100%);
  color: ${OS_LEGAL_COLORS.primaryBlue};
  border-radius: 24px;
  font-weight: 500;
  font-size: 0.9375rem;
  position: relative;
  overflow: hidden;
  border: 1px solid #d4e3f4;
  box-shadow: 0 2px 8px rgba(74, 144, 226, 0.15);

  &::before {
    content: "";
    position: absolute;
    top: 0;
    left: -100%;
    width: 100%;
    height: 100%;
    background: linear-gradient(
      90deg,
      transparent 0%,
      rgba(74, 144, 226, 0.15) 50%,
      transparent 100%
    );
    animation: shimmer 2s infinite;
  }

  @keyframes shimmer {
    0% {
      left: -100%;
    }
    100% {
      left: 100%;
    }
  }

  .pulse-dot {
    width: 6px;
    height: 6px;
    background: ${OS_LEGAL_COLORS.primaryBlue};
    border-radius: 50%;
    animation: pulse 1.5s ease-in-out infinite;
    box-shadow: 0 0 4px rgba(74, 144, 226, 0.4);
  }

  @keyframes pulse {
    0%,
    100% {
      transform: scale(1);
      opacity: 0.8;
    }
    50% {
      transform: scale(1.5);
      opacity: 0.4;
    }
  }

  /* Loader color override */
  .ui.loader {
    &:after {
      border-color: ${OS_LEGAL_COLORS.primaryBlue} transparent transparent !important;
    }
  }
`;

export const EnhancedChatInputContainer = styled(ChatInputContainer)<{
  $disabled?: boolean;
}>`
  padding: 0.625rem 0.875rem;
  background: rgba(255, 255, 255, 0.98);
  backdrop-filter: blur(20px);
  border-top: 1px solid rgba(0, 0, 0, 0.05);
  box-shadow: 0 -4px 16px rgba(0, 0, 0, 0.04);
  flex-direction: column;
  align-items: stretch;
  gap: 0.5rem;

  /* When disabled (i.e. assistant is processing) */
  ${(props) =>
    props.$disabled &&
    `
      opacity: 0.6;        /* Visually indicate inactive state */
    `}

  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    padding: 0.5rem 0.75rem;
    gap: 0.5rem;
  }
`;

export const MessagesArea = styled.div<{ $isProcessing?: boolean }>`
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 1.5rem;
  background: linear-gradient(
    to bottom,
    ${OS_LEGAL_COLORS.surfaceHover} 0%,
    #ffffff 100%
  );
  min-height: 0;
  max-height: 100%;
  position: relative;
  display: flex;
  flex-direction: column;
  transition: background 0.3s ease;

  ${(props) =>
    props.$isProcessing &&
    `
    background: linear-gradient(to bottom, #f0f7ff 0%, #f8fbff 100%);
    animation: subtleGlow 2s ease-in-out infinite;

    @keyframes subtleGlow {
      0%, 100% {
        background: linear-gradient(to bottom, #f0f7ff 0%, #f8fbff 100%);
      }
      50% {
        background: linear-gradient(to bottom, #e6f2ff 0%, #f0f7ff 100%);
      }
    }
  `}

  /* Custom scrollbar */
  &::-webkit-scrollbar {
    width: 8px;
  }

  &::-webkit-scrollbar-track {
    background: ${OS_LEGAL_COLORS.surfaceLight};
    border-radius: 4px;
  }

  &::-webkit-scrollbar-thumb {
    background: ${OS_LEGAL_COLORS.borderHover};
    border-radius: 4px;

    &:hover {
      background: ${OS_LEGAL_COLORS.textMuted};
    }
  }

  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    padding: 1rem;
  }
`;

export const InputRow = styled.div`
  display: flex;
  align-items: flex-end;
  gap: 0.5rem;
  width: 100%;
`;

export const EnhancedChatInput = styled(ChatInput)`
  background: ${OS_LEGAL_COLORS.surfaceHover};
  border: 2px solid ${OS_LEGAL_COLORS.border};
  border-radius: 12px;
  padding: 0.5rem 0.875rem;
  font-size: 0.9375rem;
  line-height: 1.4;
  transition: border-color 0.15s ease, background 0.15s ease,
    box-shadow 0.15s ease;
  flex: 1;
  min-height: 40px;
  max-height: 140px;
  overflow-y: auto;

  &:focus {
    background: white;
    border-color: #4299e1;
    box-shadow: 0 0 0 3px rgba(66, 153, 225, 0.1);
  }

  &:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }

  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    font-size: 0.875rem;
    padding: 0.5rem 0.75rem;
    min-height: 38px;
    max-height: 120px;
  }
`;

export const EnhancedSendButton = styled(SendButton)`
  width: 40px;
  height: 40px;
  border-radius: 10px;
  align-self: flex-end; /* Stay aligned to the bottom as input grows */
  flex-shrink: 0;

  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    width: 38px;
    height: 38px;
  }
`;

export const LatestMessageIndicator = styled(motion.div)`
  position: absolute;
  left: 0;
  width: 4px;
  height: 100%;
  background: linear-gradient(to bottom, #4299e1, #3182ce);
  border-radius: 0 4px 4px 0;
`;

export const NewMessageDot = styled(motion.div)`
  position: absolute;
  top: 1rem;
  right: 1rem;
  width: 12px;
  height: 12px;
  background: ${OS_LEGAL_COLORS.dangerBorderHover};
  border-radius: 50%;
  box-shadow: 0 0 0 4px rgba(239, 68, 68, 0.2);

  &::after {
    content: "";
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    background: ${OS_LEGAL_COLORS.dangerBorderHover};
    border-radius: 50%;
    animation: pulse 2s infinite;
  }

  @keyframes pulse {
    0% {
      transform: scale(1);
      opacity: 1;
    }
    50% {
      transform: scale(1.5);
      opacity: 0.3;
    }
    100% {
      transform: scale(1);
      opacity: 1;
    }
  }
`;

export const MessageWrapper = styled(motion.div)<{ isLatest?: boolean }>`
  position: relative;
  margin-bottom: 1.5rem;

  ${(props) =>
    props.isLatest &&
    `
    & > * {
      box-shadow: 0 4px 12px rgba(66, 153, 225, 0.15);
      border: 1px solid rgba(66, 153, 225, 0.2);
    }
  `}
`;

export const ChatNavigationHeader = styled.div`
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 1rem;
  background: white;
  border-bottom: 1px solid ${OS_LEGAL_COLORS.border};
  position: sticky;
  top: 0;
  z-index: 100; /* High z-index to ensure it's always visible */
  flex-shrink: 0; /* Prevent compression */

  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    position: -webkit-sticky; /* For Safari */
    position: sticky;
    padding: 0.75rem 1rem;
  }
`;

export const BackButton = styled(motion.button)`
  background: ${OS_LEGAL_COLORS.surfaceHover};
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 8px;
  padding: 0.5rem;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s ease;

  &:hover {
    background: ${OS_LEGAL_COLORS.border};
  }
`;

export const NavigationTitle = styled.span`
  flex: 1;
  font-size: 1.125rem;
  font-weight: 600;
  color: #1a202c;
`;

export const ContextExhaustedBanner = styled.div`
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.75rem;
  padding: 0.75rem 1rem;
  background: linear-gradient(
    135deg,
    ${OS_LEGAL_COLORS.warningSurface} 0%,
    #fef3c7 100%
  );
  border-top: 1px solid ${OS_LEGAL_COLORS.warningBorder};
  font-size: 0.8125rem;
  color: ${OS_LEGAL_COLORS.warningText};
  flex-shrink: 0;
`;

export const ContextExhaustedButton = styled(Button)`
  padding: 0.375rem 0.75rem;
  border: 1px solid ${OS_LEGAL_COLORS.warningBorder};
  border-radius: 6px;
  background: white;
  color: ${OS_LEGAL_COLORS.warningText};
  font-size: 0.8125rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s ease;
  white-space: nowrap;

  &:hover {
    background: ${OS_LEGAL_COLORS.warningSurface};
    border-color: ${OS_LEGAL_COLORS.warningText};
  }
`;
