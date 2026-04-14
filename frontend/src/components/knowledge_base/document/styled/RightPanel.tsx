import { motion } from "framer-motion";
import styled from "styled-components";
import { OS_LEGAL_COLORS } from "../../../../assets/configurations/osLegalStyles";

interface ConnectionStatusProps {
  $isConnected: boolean;
}

export const ConnectionStatus = styled(motion.div)<ConnectionStatusProps>`
  position: absolute;
  right: 1rem;
  top: 50%;
  transform: translateY(-50%);
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: ${(props) =>
    props.$isConnected ? OS_LEGAL_COLORS.greenMedium : OS_LEGAL_COLORS.danger};

  /* Flash animation for disconnected state */
  animation: ${(props) =>
    !props.$isConnected ? "flashDisconnected 1s infinite" : "none"};

  @keyframes flashDisconnected {
    0%,
    100% {
      opacity: 1;
      transform: translateY(-50%) scale(1);
    }
    50% {
      opacity: 0.5;
      transform: translateY(-50%) scale(0.85);
    }
  }
`;

interface SlidingPanelProps {
  pushContent?: boolean;
  panelWidth: number; // percentage 0-100
}

export const SlidingPanel = styled(motion.div)<SlidingPanelProps>`
  /* Preserve existing base styling */
  position: absolute;
  top: 0;
  right: 0;
  z-index: 100001; /* Above UnifiedLabelSelector (100000) */

  width: ${(props) => props.panelWidth}%;
  height: 100%;

  /* Enhanced background and effects */
  background: rgba(255, 255, 255, 0.95);
  backdrop-filter: blur(12px);
  box-shadow: -4px 0 25px rgba(0, 0, 0, 0.05), -1px 0 2px rgba(0, 0, 0, 0.02);
  border-left: 1px solid rgba(226, 232, 240, 0.3);

  display: flex;
  flex-direction: column;
  overflow: visible; // Allow our button to breach containment
  transform-style: preserve-3d; // For that sweet 3D effect

  /* Fancy edge highlight */
  &::before {
    content: "";
    position: absolute;
    left: 0;
    top: 0;
    bottom: 0;
    width: 1px;
    background: linear-gradient(
      to bottom,
      transparent,
      rgba(26, 115, 232, 0.2),
      transparent
    );
    transform: translateX(-1px);
  }

  /* Mobile responsiveness preserved */
  @media (max-width: 768px) {
    position: fixed;
    inset: 0;
    width: 100%;
    height: 100%;
    padding-top: max(env(safe-area-inset-top), 1rem);
    background: white;
    overflow: visible !important; // CRUCIAL: Let the button breathe!
  }
`;
