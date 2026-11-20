import { motion } from "framer-motion";
import styled from "styled-components";
import { OS_LEGAL_COLORS } from "../../../../assets/configurations/osLegalStyles";

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
  box-shadow:
    0 2px 8px rgba(0, 0, 0, 0.05),
    0 1px 2px rgba(0, 0, 0, 0.08),
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
    color: ${OS_LEGAL_COLORS.textSecondary};
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
    box-shadow:
      0 4px 12px rgba(66, 153, 225, 0.15),
      0 1px 3px rgba(0, 0, 0, 0.08),
      inset 0 1px 3px rgba(255, 255, 255, 1);

    &::before {
      opacity: 1;
      transform: scale(1.1);
    }

    .settings-icon {
      color: ${OS_LEGAL_COLORS.primaryBlue};
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
  box-shadow:
    0 8px 32px rgba(0, 0, 0, 0.08),
    0 0 0 1px rgba(226, 232, 240, 0.3);
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
  color: ${(props) =>
    props.$isActive
      ? OS_LEGAL_COLORS.primaryBlue
      : OS_LEGAL_COLORS.textSecondary};
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
    background: ${OS_LEGAL_COLORS.primaryBlue};
    border-radius: 1px;
    transition: height 0.2s ease;
  }

  &:hover {
    background: ${(props) =>
      props.$isActive
        ? "linear-gradient(135deg, rgba(66, 153, 225, 0.12), rgba(66, 153, 225, 0.08))"
        : "rgba(0, 0, 0, 0.02)"};
    color: ${(props) =>
      props.$isActive
        ? OS_LEGAL_COLORS.primaryBlue
        : OS_LEGAL_COLORS.textTertiary};
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

export const WidthButton = styled(motion.button)<{ $isActive: boolean }>`
  padding: 0.5rem 1rem;
  border: none;
  background: ${(props) =>
    props.$isActive ? OS_LEGAL_COLORS.primaryBlue : "transparent"};
  color: ${(props) =>
    props.$isActive ? "white" : OS_LEGAL_COLORS.textTertiary};
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
