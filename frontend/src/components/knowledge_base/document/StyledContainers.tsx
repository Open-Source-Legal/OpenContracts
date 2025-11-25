import { motion } from "framer-motion";
import { Button, Card, Segment } from "semantic-ui-react";
import styled, { keyframes, css } from "styled-components";

export const HeaderContainer = styled(Segment)`
  &&& {
    margin: 0 !important;
    border-radius: 0 !important;
    padding: 1.5rem 2rem !important;
    background: rgba(255, 255, 255, 0.9);
    backdrop-filter: blur(10px);
    border-bottom: 1px solid rgba(231, 234, 237, 0.7);
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.02);
    z-index: 100;
    position: relative;
    display: flex !important;
    align-items: center;
    justify-content: space-between;
    gap: 16px;

    /* Mobile-friendly header */
    @media (max-width: 768px) {
      padding: 1rem !important;

      h2 {
        font-size: 1.25rem;
      }
    }
  }
`;

export const MetadataRow = styled.div`
  display: flex;
  gap: 2rem;
  color: #6c757d;
  margin-top: 0.5rem;
  font-size: 0.9rem;

  span {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    transition: color 0.2s ease;
    &:hover {
      color: #2185d0;
    }

    svg {
      opacity: 0.7;
    }
  }

  /* Stack metadata on small screens */
  @media (max-width: 480px) {
    flex-wrap: wrap;
    gap: 0.75rem;

    span {
      font-size: 0.8rem;
    }
  }
`;

export const ContentArea = styled.div`
  display: flex;
  flex-direction: column;
  height: calc(100vh - 90px);
  background: white;
  position: relative;

  /* Stack layout on mobile */
  @media (max-width: 768px) {
    flex-direction: column;
  }
`;

export const TabsColumn = styled(Segment)<{ collapsed: boolean }>`
  &&& {
    margin: 0 !important;
    padding: 0.75rem 0 !important;
    border: none !important;
    border-right: 1px solid rgba(231, 234, 237, 0.7) !important;
    border-radius: 0 !important;
    background: rgba(250, 251, 252, 0.97) !important;
    backdrop-filter: blur(10px);
    width: ${(props) => (props.collapsed ? "72px" : "280px")};
    transition: all 0.4s cubic-bezier(0.16, 1, 0.3, 1);
    overflow: hidden;
    z-index: 90;
    box-shadow: 1px 0 2px rgba(0, 0, 0, 0.02);

    /* Subtle gradient background */
    background: linear-gradient(
      180deg,
      rgba(255, 255, 255, 0.97) 0%,
      rgba(249, 250, 251, 0.97) 100%
    ) !important;

    /* Mobile optimization */
    @media (max-width: 768px) {
      width: 100%;
      height: 56px;
      display: flex;
      overflow-x: auto;
      overflow-y: hidden;
      -webkit-overflow-scrolling: touch;
      white-space: nowrap;
      padding: 0.5rem !important;
      background: rgba(255, 255, 255, 0.95);
      backdrop-filter: blur(10px);
      border-bottom: 1px solid rgba(231, 234, 237, 0.7) !important;

      /* Hide scrollbar but keep functionality */
      scrollbar-width: none;
      &::-webkit-scrollbar {
        display: none;
      }

      /* Center icons when in mobile mode */
      display: flex;
      justify-content: space-around;
      align-items: center;
    }
  }
`;

// Enhanced icon color map with more subtle, professional colors
const iconColorMap: Record<string, string> = {
  summary: "#0891b2", // Cyan
  chat: "#7c3aed", // Violet
  notes: "#f59e0b", // Amber
  document: "#10b981", // Emerald
  relationships: "#3b82f6", // Blue
  annotations: "#ec4899", // Pink
  relations: "#8b5cf6", // Purple
  analyses: "#06b6d4", // Light Blue
  extracts: "#f97316", // Orange
  search: "#6366f1", // Indigo
  default: "#64748b", // Slate
};

interface TabButtonProps {
  $collapsed: boolean;
  $tabKey: string;
  $active?: boolean;
}

export const TabButton = styled(Button)<TabButtonProps>`
  &&& {
    width: 100%;
    text-align: ${(props) => (props.$collapsed ? "center" : "left")} !important;
    border-radius: 0 !important;
    margin: 0.25rem 0 !important;
    padding: ${(props) =>
      props.$collapsed ? "1.25rem 0.75rem" : "1.25rem 2rem"} !important;
    background: transparent !important;
    border: none !important;
    position: relative;
    transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);

    /* Increased icon sizes in both states */
    svg {
      transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
      width: ${(props) => (props.$collapsed ? "22px" : "28px")};
      height: ${(props) => (props.$collapsed ? "22px" : "28px")};
      color: ${(props) => iconColorMap[props.$tabKey] || iconColorMap.default};
      opacity: ${(props) => (props.$active ? 1 : 0.75)};
      flex-shrink: 0; /* Prevent icon from shrinking */
    }

    /* Improved text styling */
    span {
      font-size: 1rem; /* Slightly larger font */
      font-weight: 500;
      white-space: nowrap;
      opacity: ${(props) => (props.$collapsed ? 0 : 1)};
      transition: opacity 0.2s ease-in-out;
      color: ${(props) =>
        props.$active
          ? iconColorMap[props.$tabKey] || iconColorMap.default
          : "#64748b"};
      margin-left: 1rem; /* Increased spacing between icon and text */
    }

    /* Active state */
    ${(props) =>
      props.$active &&
      css`
        background: ${`${iconColorMap[props.$tabKey]}10`} !important;
        &::before {
          content: "";
          position: absolute;
          left: 0;
          top: 0;
          bottom: 0;
          width: 3px;
          background: ${iconColorMap[props.$tabKey] || iconColorMap.default};
          border-radius: 0 2px 2px 0;
        }
      `}

    /* Hover effects */
    &:hover {
      background: ${(props) =>
        props.$active
          ? `${iconColorMap[props.$tabKey]}15`
          : "rgba(0, 0, 0, 0.03)"} !important;

      svg {
        transform: ${(props) =>
          props.$collapsed ? "scale(1.2)" : "translateX(2px)"};
        opacity: 1;
      }
    }

    /* Mobile optimizations */
    @media (max-width: 768px) {
      padding: 0.75rem !important;
      margin: 0 0.25rem !important;
      border-radius: 8px !important;

      svg {
        width: 20px;
        height: 20px;
      }

      &:hover {
        transform: translateY(-2px);
      }
    }
  }
`;

// Add a tooltip for mobile tabs
export const TabTooltip = styled.div`
  position: absolute;
  bottom: 100%;
  left: 50%;
  transform: translateX(-50%);
  background: rgba(0, 0, 0, 0.8);
  color: white;
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 12px;
  white-space: nowrap;
  pointer-events: none;
  opacity: 0;
  transition: opacity 0.2s ease;

  /* Only show on mobile */
  @media (min-width: 769px) {
    display: none;
  }
`;

export const MainContentArea = styled.div`
  flex: 1;
  overflow-y: auto;
  position: relative;
`;

export const SummaryContent = styled.div`
  max-width: 800px;
  margin: 0 auto;
  padding: 1rem;
  transition: all 0.3s ease;

  &.dimmed {
    opacity: 0.4;
    transform: scale(0.98);
    filter: blur(1px);
  }
`;

/**
 * Below is an updated SlidingPanel that is absolutely positioned on desktop
 * (so it does not take full screen height) and fixed only on mobile.
 * We also include a "ControlButtonGroupLeft" and "ControlButton" for a back button
 * at the top left inside the tray.
 *
 * Example usage:
 *   <SlidingPanel>
 *     <ControlButtonGroupLeft>
 *       <ControlButton onClick={() => closeSideTray()}>
 *         <ArrowLeft />
 *       </ControlButton>
 *     </ControlButtonGroupLeft>
 *     ... Right tray content ...
 *   </SlidingPanel>
 */

/**
 * ControlButtonGroupLeft
 *
 * Positions a set of buttons in the top-left corner of the right tray.
 */
export const ControlButtonGroupLeft = styled.div`
  position: absolute;
  left: -0.5rem; // Slightly closer to panel
  top: 50%;
  transform: translateY(-50%);
  z-index: 100;
`;

/**
 * ControlButton
 *
 * A small icon button for our tray, in this example, used to close the tray.
 */
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
  background: ${(props) => (props.$isConnected ? "#10B981" : "#EF4444")};

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

export const ControlButtonWrapper = styled.div`
  /* Desktop remains unchanged */
  @media (min-width: 769px) {
    position: absolute;
    left: -1.25rem;
    top: 50%;
    transform: translateY(-50%);
    width: 2.5rem;
    height: 6rem;
    z-index: 2001;
  }

  /* Mobile - Step 1: Perfect vertical center */
  @media (max-width: 768px) {
    position: fixed;
    top: 50%;
    transform: translateY(-50%);
    left: 0;
    width: 3rem;
    height: 3rem;
    z-index: 2001;
  }
`;

export const ControlButton = styled(motion.button)`
  position: absolute;
  width: 100%;
  height: 100%;
  border: none;
  background: transparent;
  cursor: pointer;
  transform-style: preserve-3d;
  overflow: visible;

  /* The tear in reality */
  &::before {
    content: "";
    position: absolute;
    inset: -1px;
    background: linear-gradient(
      90deg,
      rgba(0, 149, 255, 0.95) 0%,
      rgba(0, 149, 255, 0.2) 100%
    );
    clip-path: polygon(
      100% 0%,
      100% 100%,
      20% 100%,
      0% 85%,
      15% 50%,
      0% 15%,
      20% 0%
    );
    filter: blur(0.5px);
    transform: translateZ(1px);
    box-shadow: 0 0 20px rgba(0, 149, 255, 0.5), 0 0 40px rgba(0, 149, 255, 0.3),
      0 0 60px rgba(0, 149, 255, 0.1);
    animation: pulseGlow 4s ease-in-out infinite;
  }

  /* The energy ripple */
  &::after {
    content: "";
    position: absolute;
    inset: -1px;
    background: linear-gradient(
      90deg,
      rgba(255, 255, 255, 0.9) 0%,
      transparent 100%
    );
    clip-path: polygon(
      100% 0%,
      100% 100%,
      20% 100%,
      0% 85%,
      15% 50%,
      0% 15%,
      20% 0%
    );
    opacity: 0;
    transform: translateZ(2px);
    animation: energyRipple 3s ease-in-out infinite;
  }

  /* Inner glow */
  .inner-glow {
    position: absolute;
    inset: 0;
    background: radial-gradient(
      circle at right,
      rgba(0, 149, 255, 0.4) 0%,
      transparent 70%
    );
    clip-path: polygon(
      100% 0%,
      100% 100%,
      20% 100%,
      0% 85%,
      15% 50%,
      0% 15%,
      20% 0%
    );
    transform: translateZ(0.5px);
    mix-blend-mode: screen;
  }

  .arrow-wrapper {
    position: absolute;
    left: 0.5rem;
    top: 50%;
    transform: translateY(-50%) translateZ(3px);

    svg {
      width: 1.25rem;
      height: 1.25rem;
      color: white;
      filter: drop-shadow(0 0 8px rgba(0, 149, 255, 0.8));
      transition: all 0.3s ease;
    }
  }

  @keyframes pulseGlow {
    0%,
    100% {
      filter: blur(0.5px) brightness(1);
      transform: translateZ(1px);
    }
    50% {
      filter: blur(0.5px) brightness(1.3);
      transform: translateZ(1.5px);
    }
  }

  @keyframes energyRipple {
    0%,
    100% {
      opacity: 0;
      transform: translateX(0) translateZ(2px);
    }
    50% {
      opacity: 0.5;
      transform: translateX(-10px) translateZ(2px);
    }
  }

  /* Hover state intensifies everything */
  &:hover {
    &::before {
      animation: pulseGlow 2s ease-in-out infinite;
      filter: blur(0.5px) brightness(1.4);
      box-shadow: 0 0 30px rgba(0, 149, 255, 0.6),
        0 0 60px rgba(0, 149, 255, 0.4), 0 0 90px rgba(0, 149, 255, 0.2);
    }

    &::after {
      animation: energyRipple 1.5s ease-in-out infinite;
    }

    .arrow-wrapper svg {
      transform: translateX(-2px);
      filter: drop-shadow(0 0 12px rgba(0, 149, 255, 1));
    }
  }

  /* Mobile - LIQUID SMOOTH */
  @media (max-width: 768px) {
    width: 100%;
    height: 100%;
    padding: 0;
    margin: 0;
    border: none;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 0 12px 12px 0; // Softer curve

    /* Ethereal gradient blend */
    background: linear-gradient(
      to right,
      rgba(255, 255, 255, 0.99) 0%,
      rgba(255, 255, 255, 0.99) 50%,
      rgba(255, 255, 255, 0.95) 70%,
      rgba(255, 255, 255, 0.8) 85%,
      rgba(255, 255, 255, 0) 100%
    );

    /* Gossamer shadow */
    box-shadow: inset -12px 0 16px -8px rgba(0, 0, 0, 0.03),
      2px 0 12px -6px rgba(0, 0, 0, 0.06);

    .arrow-wrapper {
      width: 24px;
      height: 24px;
      display: flex;
      align-items: center;
      justify-content: center;
      margin-right: 0.75rem; // More space for fade
      opacity: 0.9; // Soften the arrow too

      svg {
        width: 20px;
        height: 20px;
        color: rgb(0, 149, 255);
        transform: rotate(180deg);
      }
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

export const ResizeHandle = styled(motion.div)<{ $isDragging: boolean }>`
  position: absolute;
  left: -12px;
  top: 50%;
  transform: translateY(-50%);
  width: 24px;
  height: 80px;
  cursor: ew-resize;
  z-index: 2001;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 16px;

  /* The handle track */
  &::before {
    content: "";
    position: absolute;
    left: 50%;
    top: 0;
    bottom: 0;
    width: 4px;
    transform: translateX(-50%);
    background: ${(props) =>
      props.$isDragging
        ? "linear-gradient(180deg, transparent, rgba(66, 153, 225, 0.3), transparent)"
        : "linear-gradient(180deg, transparent, rgba(226, 232, 240, 0.5), transparent)"};
    border-radius: 2px;
    transition: all 0.3s ease;
    box-shadow: ${(props) =>
      props.$isDragging ? "0 0 8px rgba(66, 153, 225, 0.3)" : "none"};
  }

  /* The grip dots */
  &::after {
    content: "";
    position: absolute;
    left: 50%;
    top: 50%;
    transform: translate(-50%, -50%);
    width: 4px;
    height: 24px;
    background-image: radial-gradient(
      circle,
      rgba(148, 163, 184, 0.4) 1px,
      transparent 1px
    );
    background-size: 4px 8px;
    opacity: ${(props) => (props.$isDragging ? 0 : 1)};
    transition: opacity 0.2s ease;
  }

  &:hover {
    &::before {
      background: linear-gradient(
        180deg,
        transparent,
        rgba(66, 153, 225, 0.2),
        transparent
      );
      width: 6px;
      box-shadow: 0 0 12px rgba(66, 153, 225, 0.2);
    }

    .settings-icon {
      opacity: 1;
      transform: scale(1);
    }
  }

  /* Hide on mobile */
  @media (max-width: 768px) {
    display: none;
  }
`;

export const ResizeHandleControl = styled(motion.button)`
  position: absolute;
  left: 50%;
  top: 50%;
  transform: translate(-50%, -50%) scale(0.9);
  width: 32px;
  height: 32px;
  border-radius: 50%;
  border: none;
  background: linear-gradient(
    135deg,
    rgba(255, 255, 255, 0.95),
    rgba(249, 250, 251, 0.9)
  );
  backdrop-filter: blur(10px);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  z-index: 10;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05), 0 1px 2px rgba(0, 0, 0, 0.08),
    inset 0 1px 2px rgba(255, 255, 255, 0.9);

  /* Start hidden */
  opacity: 0;

  ${ResizeHandle}:hover & {
    opacity: 1;
    transform: translate(-50%, -50%) scale(1);
  }

  /* Subtle ring */
  &::before {
    content: "";
    position: absolute;
    inset: -3px;
    border-radius: 50%;
    background: linear-gradient(135deg, transparent, rgba(66, 153, 225, 0.1));
    opacity: 0;
    transition: all 0.3s ease;
  }

  .settings-icon {
    width: 16px;
    height: 16px;
    color: #64748b;
    opacity: 0.7;
    transform: scale(0.9);
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    position: relative;
    z-index: 1;
  }

  &:hover {
    background: linear-gradient(
      135deg,
      rgba(255, 255, 255, 1),
      rgba(249, 250, 251, 0.95)
    );
    box-shadow: 0 4px 12px rgba(66, 153, 225, 0.15),
      0 1px 3px rgba(0, 0, 0, 0.08), inset 0 1px 3px rgba(255, 255, 255, 1);

    &::before {
      opacity: 1;
      transform: scale(1.1);
    }

    .settings-icon {
      color: #4299e1;
      opacity: 1;
      transform: scale(1) rotate(90deg);
    }
  }

  &:active {
    transform: scale(0.95);
  }
`;

export const ResizeHandleButton = styled(motion.button)`
  /* Legacy - no longer used */
  display: none;
`;

export const WidthControlBar = styled(motion.div)`
  position: absolute;
  left: 1rem;
  bottom: 1rem;
  display: flex;
  gap: 0.5rem;
  background: rgba(255, 255, 255, 0.95);
  backdrop-filter: blur(10px);
  padding: 0.5rem;
  border-radius: 12px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
  z-index: 2002;

  /* Hide on mobile */
  @media (max-width: 768px) {
    display: none;
  }
`;

export const WidthControlMenu = styled(motion.div)`
  position: absolute;
  top: 50%;
  left: 24px; /* Position it flowing from the handle */
  transform: translateY(-50%);
  background: rgba(255, 255, 255, 0.98);
  backdrop-filter: blur(16px);
  border-radius: 12px;
  padding: 0.5rem;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.08), 0 0 0 1px rgba(226, 232, 240, 0.3);
  z-index: 2003;
  overflow: hidden;
  min-width: 180px;

  /* Subtle connection to handle */
  &::before {
    content: "";
    position: absolute;
    left: -8px;
    top: 50%;
    transform: translateY(-50%);
    width: 8px;
    height: 32px;
    background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.98));
  }

  /* Hide on mobile */
  @media (max-width: 768px) {
    display: none;
  }
`;

/**
 * Styled button for toggling the width control menu.
 * Now removed as it's replaced by ResizeHandleButton
 */
export const WidthControlToggle = styled(motion.button).attrs({
  id: "width-control-toggle",
})`
  /* Legacy component - kept for backwards compatibility but hidden */
  display: none;
`;

export const WidthMenuItem = styled(motion.button)<{ $isActive: boolean }>`
  width: 100%;
  padding: 0.75rem 1rem;
  border: none;
  background: ${(props) =>
    props.$isActive
      ? "linear-gradient(135deg, rgba(66, 153, 225, 0.08), rgba(66, 153, 225, 0.05))"
      : "transparent"};
  color: ${(props) => (props.$isActive ? "#4299e1" : "#64748b")};
  border-radius: 8px;
  font-size: 0.875rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
  text-align: left;
  display: flex;
  align-items: center;
  justify-content: space-between;
  white-space: nowrap;
  position: relative;
  overflow: hidden;

  /* Subtle left accent for active state */
  &::before {
    content: "";
    position: absolute;
    left: 0;
    top: 50%;
    transform: translateY(-50%);
    width: 2px;
    height: ${(props) => (props.$isActive ? "60%" : "0")};
    background: #4299e1;
    border-radius: 1px;
    transition: height 0.2s ease;
  }

  &:hover {
    background: ${(props) =>
      props.$isActive
        ? "linear-gradient(135deg, rgba(66, 153, 225, 0.12), rgba(66, 153, 225, 0.08))"
        : "rgba(0, 0, 0, 0.02)"};
    color: ${(props) => (props.$isActive ? "#4299e1" : "#475569")};
    transform: translateX(2px);
  }

  &:active {
    transform: translateX(2px) scale(0.98);
  }

  .percentage {
    font-size: 0.75rem;
    opacity: 0.6;
    font-weight: 400;
  }
`;

export const MenuDivider = styled.div`
  height: 1px;
  background: rgba(226, 232, 240, 0.5);
  margin: 0.5rem 0;
`;

export const ChatIndicator = styled(motion.button)`
  position: fixed;
  right: 0;
  top: 50%;
  transform: translateY(-50%);
  width: 48px;
  height: 80px;
  background: #4299e1;
  border: none;
  border-radius: 24px 0 0 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  box-shadow: -4px 0 12px rgba(66, 153, 225, 0.2);
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  z-index: 1999;

  &::before {
    content: "";
    position: absolute;
    inset: 2px;
    right: 0;
    background: linear-gradient(135deg, #5ba3eb 0%, #4299e1 100%);
    border-radius: 22px 0 0 22px;
  }

  svg {
    width: 24px;
    height: 24px;
    color: white;
    position: relative;
    z-index: 1;
  }

  &:hover {
    width: 56px;
    box-shadow: -6px 0 20px rgba(66, 153, 225, 0.3);

    svg {
      transform: scale(1.1);
    }
  }

  /* Pulse animation */
  &::after {
    content: "";
    position: absolute;
    inset: -8px;
    right: -4px;
    background: #4299e1;
    border-radius: 28px 0 0 28px;
    opacity: 0;
    animation: chatPulse 2s ease-out infinite;
  }

  @keyframes chatPulse {
    0% {
      opacity: 0.4;
      transform: scale(1);
    }
    100% {
      opacity: 0;
      transform: scale(1.2);
    }
  }

  /* Adjust for mobile */
  @media (max-width: 768px) {
    right: 0;
    bottom: auto;
    top: 50%;
    transform: translateY(-50%);
    width: 56px;
    height: 56px;
    border-radius: 28px 0 0 28px;

    &::before {
      border-radius: 26px 0 0 26px;
    }

    &::after {
      border-radius: 32px 0 0 32px;
    }
  }
`;

export const WidthButton = styled(motion.button)<{ $isActive: boolean }>`
  padding: 0.5rem 1rem;
  border: none;
  background: ${(props) => (props.$isActive ? "#4299e1" : "transparent")};
  color: ${(props) => (props.$isActive ? "white" : "#4a5568")};
  border-radius: 8px;
  font-size: 0.875rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
  white-space: nowrap;

  &:hover {
    background: ${(props) =>
      props.$isActive ? "#3182ce" : "rgba(66, 153, 225, 0.1)"};
  }

  &:active {
    transform: scale(0.95);
  }
`;

export const AutoMinimizeToggle = styled(motion.button)<{ $isActive: boolean }>`
  padding: 0.5rem;
  border: none;
  background: ${(props) =>
    props.$isActive ? "rgba(72, 187, 120, 0.1)" : "transparent"};
  color: ${(props) => (props.$isActive ? "#38a169" : "#718096")};
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s ease;
  display: flex;
  align-items: center;
  justify-content: center;

  &:hover {
    background: ${(props) =>
      props.$isActive ? "rgba(72, 187, 120, 0.2)" : "rgba(0, 0, 0, 0.05)"};
  }

  svg {
    width: 18px;
    height: 18px;
  }
`;

export const ControlButtonGroup = styled.div`
  position: absolute;
  top: 1.5rem;
  right: 2rem;
  display: flex;
  gap: 0.75rem;
`;

export const RelationshipPanel = styled.div`
  padding: 1.5rem;
  height: 100%;
  overflow-y: auto;

  h3 {
    font-size: 1.25rem;
    font-weight: 500;
    color: #212529;
    margin-bottom: 1.5rem;
    display: flex;
    align-items: center;
    gap: 0.75rem;
  }
`;

export const RelationshipCard = styled(Card)`
  &&& {
    width: 100%;
    margin-bottom: 1rem !important;
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.02) !important;
    border: 1px solid rgba(231, 234, 237, 0.7) !important;
    transition: all 0.2s ease;

    &:hover {
      transform: translateY(-2px);
      box-shadow: 0 4px 8px rgba(0, 0, 0, 0.05) !important;
      border-color: #2185d0 !important;
    }

    .content {
      padding: 1.25rem !important;
    }
  }
`;

export const RelationshipType = styled.div`
  display: inline-block;
  font-size: 0.75rem;
  font-weight: 500;
  color: #2185d0;
  background: rgba(33, 133, 208, 0.1);
  padding: 0.25rem 0.75rem;
  border-radius: 1rem;
  margin-bottom: 0.75rem;
`;

// Add new shimmer animation with a more pronounced effect
const shimmerAnimation = keyframes`
  0% {
    background-position: -1000px 0;
  }
  50% {
    background-position: 0 0;
  }
  100% {
    background-position: 1000px 0;
  }
`;

// Enhanced base placeholder with better visual feedback
export const PlaceholderBase = styled.div`
  background: linear-gradient(
    90deg,
    #f0f0f0 0%,
    #f8f9fa 20%,
    #e9ecef 40%,
    #f8f9fa 60%,
    #f0f0f0 80%
  );
  background-size: 1000px 100%;
  animation: ${shimmerAnimation} 2.5s infinite ease-in-out;
  border-radius: 8px;
  position: relative;
  overflow: hidden;

  &::after {
    content: "";
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    background: linear-gradient(
      90deg,
      transparent,
      rgba(255, 255, 255, 0.4),
      transparent
    );
    transform: translateX(-100%);
    animation: shimmerOverlay 2.5s infinite;
  }
`;

const fadeIn = keyframes`
  from { opacity: 0; }
  to { opacity: 1; }
`;

export const PlaceholderItem = styled(PlaceholderBase)<{ delay: number }>`
  opacity: 0;
  animation: ${shimmerAnimation} 2.5s infinite ease-in-out,
    ${fadeIn} 0.5s forwards;
  animation-delay: ${(props) => props.delay}s;
`;

// Add new loading container for document viewer
export const DocumentLoadingContainer = styled.div`
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  text-align: center;
  width: 90%;
  max-width: 600px;

  .progress-text {
    color: #2185d0;
    font-size: 1.1rem;
    font-weight: 500;
    margin-top: 1rem;
    opacity: 0.9;
  }

  .progress-bar {
    width: 100%;
    height: 4px;
    background: #e9ecef;
    border-radius: 2px;
    overflow: hidden;
    margin-top: 0.5rem;

    .progress-fill {
      height: 100%;
      background: #2185d0;
      border-radius: 2px;
      transition: width 0.3s ease;
      position: relative;

      &::after {
        content: "";
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background: linear-gradient(
          90deg,
          transparent,
          rgba(255, 255, 255, 0.3),
          transparent
        );
        animation: progressPulse 1.5s infinite;
      }
    }
  }
`;

// Enhanced summary placeholder
export const SummaryPlaceholder = styled.div`
  padding: 2rem;
  max-width: 800px;
  margin: 0 auto;
  background: white;
  border-radius: 12px;
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.02);

  ${PlaceholderBase} {
    height: 24px;
    margin-bottom: 1.25rem;
    opacity: 0;
    animation: ${shimmerAnimation} 2.5s infinite ease-in-out,
      fadeIn 0.5s forwards;

    &:nth-child(1) {
      width: 60%;
      animation-delay: 0.1s;
    }
    &:nth-child(2) {
      width: 95%;
      animation-delay: 0.2s;
    }
    &:nth-child(3) {
      width: 85%;
      animation-delay: 0.3s;
    }
    &:nth-child(4) {
      width: 90%;
      animation-delay: 0.4s;
    }
    &:nth-child(5) {
      width: 75%;
      animation-delay: 0.5s;
    }
  }
`;

export const NotePlaceholder = styled(motion.div)`
  padding: 2rem;
  background: white;
  border-radius: 16px;
  margin-bottom: 1.5rem;
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.03);
  border: 1px solid rgba(231, 234, 237, 0.7);
  max-width: 700px;
  margin-left: auto;
  margin-right: auto;

  ${PlaceholderBase} {
    &.header {
      height: 24px;
      width: 40%;
      margin-bottom: 1.5rem;
    }

    &.content {
      height: 20px;
      margin-bottom: 1rem;

      &:last-child {
        margin-bottom: 0;
      }
      &:nth-child(2) {
        width: 95%;
      }
      &:nth-child(3) {
        width: 85%;
      }
    }
  }
`;

export const RelationshipPlaceholder = styled(motion.div)`
  padding: 2rem;
  background: white;
  border-radius: 16px;
  margin-bottom: 1.5rem;
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.03);
  border: 1px solid rgba(231, 234, 237, 0.7);
  max-width: 700px;
  margin-left: auto;
  margin-right: auto;

  ${PlaceholderBase} {
    &.type {
      height: 22px;
      width: 120px;
      margin-bottom: 1.5rem;
    }

    &.title {
      height: 24px;
      width: 80%;
      margin-bottom: 1rem;
    }

    &.meta {
      height: 18px;
      width: 50%;
    }
  }
`;

// Enhanced LoadingPlaceholders component
export const LoadingPlaceholders: React.FC<{
  type: "summary" | "notes" | "relationships";
}> = ({ type }) => {
  if (type === "summary") {
    return (
      <SummaryPlaceholder>
        {[...Array(5)].map((_, i) => (
          <PlaceholderItem key={i} delay={i * 0.1} />
        ))}
      </SummaryPlaceholder>
    );
  }

  return (
    <>
      {[...Array(3)].map((_, i) => {
        const Placeholder =
          type === "notes" ? NotePlaceholder : RelationshipPlaceholder;
        return (
          <Placeholder
            key={i}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{
              duration: 0.4,
              delay: i * 0.15,
              ease: [0.4, 0, 0.2, 1],
            }}
          >
            <PlaceholderBase
              className={type === "notes" ? "header" : "type"}
              style={{ animationDelay: `${i * 0.1}s` }}
            />
            {type === "notes" ? (
              <>
                <PlaceholderBase
                  className="content"
                  style={{ animationDelay: `${i * 0.1 + 0.1}s` }}
                />
                <PlaceholderBase
                  className="content"
                  style={{ animationDelay: `${i * 0.1 + 0.2}s` }}
                />
              </>
            ) : (
              <>
                <PlaceholderBase
                  className="title"
                  style={{ animationDelay: `${i * 0.1 + 0.1}s` }}
                />
                <PlaceholderBase
                  className="meta"
                  style={{ animationDelay: `${i * 0.1 + 0.2}s` }}
                />
              </>
            )}
          </Placeholder>
        );
      })}
    </>
  );
};

export const EmptyStateContainer = styled(motion.div)`
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 3rem 2rem;
  text-align: center;
  color: #6c757d;

  svg {
    color: #adb5bd;
    margin-bottom: 1.5rem;
    stroke-width: 1.5;
  }

  h3 {
    color: #495057;
    font-size: 1.25rem;
    font-weight: 500;
    margin-bottom: 0.5rem;
  }

  p {
    color: #868e96;
    font-size: 0.875rem;
    max-width: 280px;
    line-height: 1.5;
  }
`;

export const EmptyState: React.FC<{
  icon: React.ReactNode;
  title: string;
  description: string;
}> = ({ icon, title, description }) => (
  <EmptyStateContainer
    initial={{ opacity: 0, y: 20 }}
    animate={{ opacity: 1, y: 0 }}
    transition={{ duration: 0.4, ease: [0.4, 0, 0.2, 1] }}
  >
    {icon}
    <h3>{title}</h3>
    <p>{description}</p>
  </EmptyStateContainer>
);

export const KnowledgeLayerContainer = styled.div`
  display: flex;
  height: 100%;
  width: 100%;
  position: relative;
  background: #fafbfc;

  @media (max-width: 768px) {
    flex-direction: column;
  }
`;

export const VersionHistorySidebar = styled.div<{
  collapsed?: boolean;
  $mobileVisible?: boolean;
}>`
  width: ${(props) => (props.collapsed ? "60px" : "320px")};
  background: white;
  border-right: 1px solid #e2e8f0;
  display: flex;
  flex-direction: column;
  transition: width 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  overflow: hidden;
  box-shadow: 2px 0 8px rgba(0, 0, 0, 0.04);

  @media (max-width: 768px) {
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    width: 100% !important;
    z-index: 10;
    display: ${(props) => (props.$mobileVisible ? "flex" : "none")};
    border-right: none;
    border-bottom: 1px solid #e2e8f0;
  }
`;

export const VersionHistoryHeader = styled.div`
  padding: 1.5rem;
  border-bottom: 1px solid #e2e8f0;
  background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
  position: relative;

  @media (max-width: 768px) {
    padding-top: 3.5rem;
  }

  h3 {
    margin: 0;
    font-size: 1.125rem;
    font-weight: 600;
    color: #1e293b;
    display: flex;
    align-items: center;
    gap: 0.5rem;

    svg {
      color: #3b82f6;
    }
  }

  .version-count {
    margin-top: 0.375rem;
    font-size: 0.875rem;
    color: #64748b;
  }
`;

export const MobileBackButton = styled.button`
  display: none;

  @media (max-width: 768px) {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    position: absolute;
    top: 1rem;
    right: 1rem;
    padding: 0.5rem 1rem;
    background: #eff6ff;
    border: 1px solid #3b82f6;
    border-radius: 8px;
    color: #3b82f6;
    font-size: 0.875rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s;

    &:hover {
      background: #3b82f6;
      color: white;
    }

    svg {
      width: 16px;
      height: 16px;
    }
  }
`;

export const VersionList = styled.div`
  flex: 1;
  overflow-y: auto;
  padding: 0.75rem;

  @media (max-width: 768px) {
    padding: 1rem;
  }

  /* Custom scrollbar */
  &::-webkit-scrollbar {
    width: 6px;
  }

  &::-webkit-scrollbar-track {
    background: #f1f5f9;
  }

  &::-webkit-scrollbar-thumb {
    background: #cbd5e1;
    border-radius: 3px;

    &:hover {
      background: #94a3b8;
    }
  }
`;

export const VersionItem = styled(motion.button)<{
  $isActive?: boolean;
  $isCurrent?: boolean;
}>`
  width: 100%;
  padding: 1rem;
  margin-bottom: 0.5rem;
  background: ${(props) =>
    props.$isActive ? "#eff6ff" : props.$isCurrent ? "#f0fdf4" : "white"};
  border: 1px solid
    ${(props) =>
      props.$isActive ? "#3b82f6" : props.$isCurrent ? "#10b981" : "#e2e8f0"};
  border-radius: 12px;
  text-align: left;
  cursor: pointer;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);

  &:hover {
    transform: translateX(4px);
    border-color: ${(props) => (props.$isActive ? "#3b82f6" : "#93c5fd")};
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
  }

  .version-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 0.5rem;

    .version-number {
      font-weight: 600;
      font-size: 0.875rem;
      color: ${(props) =>
        props.$isActive ? "#3b82f6" : props.$isCurrent ? "#10b981" : "#1e293b"};
    }

    .version-badge {
      padding: 0.125rem 0.5rem;
      border-radius: 9999px;
      font-size: 0.75rem;
      font-weight: 500;
      background: ${(props) =>
        props.$isActive ? "#3b82f6" : props.$isCurrent ? "#10b981" : "#e2e8f0"};
      color: ${(props) =>
        props.$isActive || props.$isCurrent ? "white" : "#64748b"};
    }
  }

  .version-meta {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
    font-size: 0.8125rem;
    color: #64748b;

    .meta-row {
      display: flex;
      align-items: center;
      gap: 0.375rem;

      svg {
        width: 12px;
        height: 12px;
      }
    }
  }
`;

export const KnowledgeContent = styled.div<{ $mobileVisible?: boolean }>`
  flex: 1;
  display: flex;
  flex-direction: column;
  background: white;
  margin: 1rem;
  border-radius: 16px;
  box-shadow: 0 4px 24px rgba(0, 0, 0, 0.06);
  overflow: hidden;

  @media (max-width: 768px) {
    margin: 0;
    border-radius: 0;
    display: ${(props) => (props.$mobileVisible !== false ? "flex" : "none")};
  }
`;

export const KnowledgeHeader = styled.div`
  padding: 1.5rem 2rem;
  border-bottom: 1px solid #e2e8f0;
  background: linear-gradient(135deg, #ffffff 0%, #f8fafc 100%);

  @media (max-width: 768px) {
    padding: 1rem;
  }

  .header-content {
    display: flex;
    justify-content: space-between;
    align-items: center;

    @media (max-width: 768px) {
      flex-direction: column;
      align-items: stretch;
      gap: 1rem;
    }

    h2 {
      margin: 0;
      font-size: 1.5rem;
      font-weight: 600;
      color: #1e293b;
      display: flex;
      align-items: center;
      gap: 0.75rem;

      @media (max-width: 768px) {
        font-size: 1.25rem;
      }

      svg {
        color: #3b82f6;
      }
    }

    .header-actions {
      display: flex;
      gap: 0.75rem;

      @media (max-width: 768px) {
        justify-content: stretch;

        button {
          flex: 1;
          white-space: nowrap;
        }
      }
    }
  }

  .version-info {
    margin-top: 0.5rem;
    font-size: 0.875rem;
    color: #64748b;
    display: flex;
    align-items: center;
    gap: 1rem;

    @media (max-width: 768px) {
      flex-direction: column;
      align-items: flex-start;
      gap: 0.5rem;
      font-size: 0.8125rem;
    }

    .info-item {
      display: flex;
      align-items: center;
      gap: 0.375rem;

      svg {
        width: 14px;
        height: 14px;
      }
    }
  }
`;

export const KnowledgeBody = styled.div<{ $isEditing?: boolean }>`
  flex: 1;
  padding: 2rem;
  overflow-y: auto;
  background: ${(props) => (props.$isEditing ? "#f8fafc" : "white")};

  @media (max-width: 768px) {
    padding: 1rem;
  }

  .prose {
    max-width: 65ch;
    margin: 0 auto;

    @media (max-width: 768px) {
      max-width: 100%;
    }
  }
`;

export const EditModeToolbar = styled(motion.div)`
  position: sticky;
  top: 0;
  background: rgba(255, 255, 255, 0.95);
  backdrop-filter: blur(8px);
  border-bottom: 1px solid #e2e8f0;
  padding: 1rem 2rem;
  margin: -2rem -2rem 2rem -2rem;
  display: flex;
  justify-content: space-between;
  align-items: center;
  z-index: 10;

  @media (max-width: 768px) {
    padding: 0.75rem 1rem;
    margin: -1rem -1rem 1rem -1rem;
    flex-wrap: wrap;
    gap: 0.5rem;
  }

  .toolbar-left {
    display: flex;
    align-items: center;
    gap: 1rem;

    .edit-indicator {
      display: flex;
      align-items: center;
      gap: 0.5rem;
      padding: 0.375rem 0.75rem;
      background: #fef3c7;
      color: #d97706;
      border-radius: 8px;
      font-size: 0.875rem;
      font-weight: 500;

      @media (max-width: 768px) {
        font-size: 0.8125rem;
        padding: 0.25rem 0.5rem;
      }

      svg {
        width: 16px;
        height: 16px;
      }
    }
  }

  .toolbar-actions {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }
`;

export const EditToolbarCloseButton = styled.button`
  display: none; /* Hidden on desktop */

  @media (max-width: 768px) {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 32px;
    height: 32px;
    border-radius: 8px;
    border: 1px solid #e2e8f0;
    background: white;
    cursor: pointer;
    transition: all 0.2s ease;
    flex-shrink: 0;

    svg {
      width: 16px;
      height: 16px;
      color: #64748b;
    }

    &:hover {
      background: #f8fafc;
      border-color: #cbd5e1;

      svg {
        color: #475569;
      }
    }

    &:active {
      transform: scale(0.95);
    }
  }
`;

// Forward ref to allow cursor position management
export const MarkdownEditor = styled.textarea`
  width: 100%;
  min-height: 500px;
  padding: 1.5rem;
  background: white;
  border: 2px solid #e2e8f0;
  border-radius: 12px;
  font-family: "SF Mono", "Monaco", "Inconsolata", "Fira Code", monospace;
  font-size: 0.875rem;
  line-height: 1.6;
  resize: vertical;
  transition: border-color 0.2s;

  @media (max-width: 768px) {
    min-height: 300px;
    padding: 1rem;
    font-size: 0.8125rem;
  }

  &:focus {
    outline: none;
    border-color: #3b82f6;
    box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
  }
`;

export const CollapseSidebarButton = styled(motion.button)`
  position: absolute;
  top: 1rem;
  right: -12px;
  width: 24px;
  height: 24px;
  background: white;
  border: 1px solid #e2e8f0;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  z-index: 10;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
  transition: all 0.2s;

  &:hover {
    background: #f8fafc;
    transform: scale(1.1);
  }

  svg {
    width: 14px;
    height: 14px;
    color: #64748b;
  }

  @media (max-width: 768px) {
    display: none;
  }
`;

// Small count badge for sidebar tabs
export const TabBadge = styled.span<{ $isActive: boolean }>`
  position: absolute;
  top: 8px;
  right: 8px;
  min-width: 18px;
  height: 18px;
  padding: 0 4px;
  background: ${(props) =>
    props.$isActive ? "rgba(255, 255, 255, 0.25)" : "#3b82f6"};
  color: white;
  font-size: 10px;
  font-weight: 600;
  border-radius: 9px;
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 2;
  border: 1px solid
    ${(props) =>
      props.$isActive ? "rgba(255, 255, 255, 0.3)" : "rgba(59, 130, 246, 0.3)"};
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  transition: all 0.3s ease;
`;

export const MobileTabBar = styled.div`
  display: none;

  @media (max-width: 768px) {
    display: flex;
    background: white;
    border-bottom: 1px solid #e2e8f0;
    position: sticky;
    top: 0;
    z-index: 20;
  }
`;

export const MobileTab = styled.button<{ $active?: boolean }>`
  flex: 1;
  padding: 1rem;
  border: none;
  background: ${(props) => (props.$active ? "#eff6ff" : "white")};
  color: ${(props) => (props.$active ? "#3b82f6" : "#64748b")};
  font-weight: ${(props) => (props.$active ? "600" : "500")};
  font-size: 0.875rem;
  cursor: pointer;
  transition: all 0.2s;
  border-bottom: 2px solid
    ${(props) => (props.$active ? "#3b82f6" : "transparent")};
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;

  &:hover:not(:disabled) {
    background: ${(props) => (props.$active ? "#eff6ff" : "#f8fafc")};
  }

  svg {
    width: 16px;
    height: 16px;
  }
`;

/* Sidebar Tabs - positioned on the left edge of the sliding panel when open, right edge when closed */
export const SidebarTabsContainer = styled.div<{ $panelOpen: boolean }>`
  position: ${(props) => (props.$panelOpen ? "absolute" : "fixed")};
  left: ${(props) => (props.$panelOpen ? "-48px" : "auto")};
  right: ${(props) => (props.$panelOpen ? "auto" : "0")};
  top: 50%;
  transform: translateY(-50%);
  display: flex;
  flex-direction: column;
  gap: ${(props) => (props.$panelOpen ? "0" : "8px")};
  z-index: ${(props) => (props.$panelOpen ? "100002" : "1999")};

  @media (max-width: 768px) {
    /* Hide when panel is open (mobile tab bar is shown instead) */
    display: ${(props) => (props.$panelOpen ? "none" : "flex")};
  }
`;

export const SidebarTab = styled(motion.button)<{
  $isActive: boolean;
  $panelOpen: boolean;
}>`
  width: ${(props) => (props.$panelOpen ? "48px" : "40px")};
  height: ${(props) => (props.$panelOpen ? "120px" : "100px")};
  background: ${(props) =>
    props.$isActive
      ? "linear-gradient(90deg, rgba(66, 153, 225, 0.95) 0%, rgba(59, 130, 246, 0.95) 100%)"
      : "rgba(255, 255, 255, 0.95)"};
  backdrop-filter: blur(12px);
  border: 1px solid
    ${(props) =>
      props.$isActive ? "rgba(59, 130, 246, 0.3)" : "rgba(226, 232, 240, 0.3)"};
  border-right: ${(props) =>
    props.$panelOpen ? "none" : "1px solid rgba(226, 232, 240, 0.3)"};
  border-left: ${(props) =>
    props.$panelOpen ? "1px solid rgba(226, 232, 240, 0.3)" : "none"};
  border-radius: 12px 0 0 12px;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  padding: 0.75rem 0.5rem;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  box-shadow: ${(props) =>
    props.$isActive
      ? props.$panelOpen
        ? "4px 0 16px rgba(59, 130, 246, 0.25)"
        : "-4px 0 16px rgba(59, 130, 246, 0.25)"
      : props.$panelOpen
      ? "2px 0 8px rgba(0, 0, 0, 0.05)"
      : "-2px 0 8px rgba(0, 0, 0, 0.05)"};
  position: relative;
  overflow: hidden;

  /* Subtle gradient overlay */
  &::before {
    content: "";
    position: absolute;
    inset: 0;
    background: ${(props) =>
      props.$isActive
        ? "linear-gradient(180deg, rgba(255, 255, 255, 0.1) 0%, rgba(255, 255, 255, 0) 100%)"
        : "linear-gradient(180deg, rgba(255, 255, 255, 0.5) 0%, transparent 100%)"};
    opacity: ${(props) => (props.$isActive ? 1 : 0)};
    transition: opacity 0.3s ease;
  }

  svg {
    width: 20px;
    height: 20px;
    color: ${(props) => (props.$isActive ? "white" : "#64748b")};
    transition: all 0.3s ease;
    position: relative;
    z-index: 1;
    flex-shrink: 0;
  }

  .tab-label {
    writing-mode: vertical-rl;
    text-orientation: mixed;
    font-size: 0.75rem;
    font-weight: 600;
    letter-spacing: 0.05em;
    color: ${(props) => (props.$isActive ? "white" : "#64748b")};
    text-transform: uppercase;
    white-space: nowrap;
    position: relative;
    z-index: 1;
  }

  &:hover {
    transform: ${(props) => {
      // When panel is open, hover moves tab right (out from panel)
      // When panel is closed, hover moves tab left (out from screen edge)
      if (props.$panelOpen) {
        return props.$isActive ? "translateX(2px)" : "translateX(4px)";
      } else {
        return props.$isActive ? "translateX(-2px)" : "translateX(-4px)";
      }
    }};
    box-shadow: ${(props) =>
      props.$isActive
        ? props.$panelOpen
          ? "6px 0 24px rgba(59, 130, 246, 0.35)"
          : "-6px 0 24px rgba(59, 130, 246, 0.35)"
        : props.$panelOpen
        ? "4px 0 16px rgba(0, 0, 0, 0.08)"
        : "-4px 0 16px rgba(0, 0, 0, 0.08)"};
    background: ${(props) =>
      props.$isActive
        ? "linear-gradient(90deg, rgba(66, 153, 225, 1) 0%, rgba(59, 130, 246, 1) 100%)"
        : "rgba(248, 250, 252, 0.98)"};

    &::before {
      opacity: 1;
    }

    svg {
      transform: ${(props) => (props.$isActive ? "scale(1.1)" : "scale(1.05)")};
      color: ${(props) => (props.$isActive ? "white" : "#3b82f6")};
    }

    .tab-label {
      color: ${(props) => (props.$isActive ? "white" : "#3b82f6")};
    }
  }

  &:active {
    transform: ${(props) =>
      props.$panelOpen
        ? "translateX(2px) scale(0.98)"
        : "translateX(-2px) scale(0.98)"};
  }

  /* Active state indicator line */
  &::after {
    content: "";
    position: absolute;
    right: 0;
    top: 50%;
    transform: translateY(-50%);
    width: 3px;
    height: ${(props) => (props.$isActive ? "60%" : "0")};
    background: white;
    border-radius: 2px 0 0 2px;
    transition: height 0.3s ease;
  }

  /* First tab (top) */
  &:first-child {
    margin-bottom: 4px;
  }

  /* Second tab (bottom) */
  &:last-child {
    margin-top: 0;
  }

  /* Mobile: Icon-only tabs when panel is closed */
  @media (max-width: 768px) {
    width: 48px;
    height: 48px;
    border-radius: 12px;
    gap: 0;
    padding: 0.5rem;

    .tab-label {
      display: none;
    }

    svg {
      width: 24px;
      height: 24px;
    }
  }
`;
