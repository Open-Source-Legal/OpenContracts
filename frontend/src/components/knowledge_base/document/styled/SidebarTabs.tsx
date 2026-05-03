import { motion } from "framer-motion";
import styled from "styled-components";
import { OS_LEGAL_COLORS } from "../../../../assets/configurations/osLegalStyles";

export const TabBadge = styled.span<{ $isActive: boolean }>`
  position: absolute;
  top: 8px;
  right: 8px;
  min-width: 18px;
  height: 18px;
  padding: 0 4px;
  background: ${(props) =>
    props.$isActive
      ? "rgba(255, 255, 255, 0.25)"
      : OS_LEGAL_COLORS.primaryBlue};
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
    border-bottom: 1px solid ${OS_LEGAL_COLORS.border};
    position: sticky;
    top: 0;
    z-index: 20;
  }
`;

export const MobileTab = styled.button<{ $active?: boolean }>`
  flex: 1;
  padding: 1rem;
  border: none;
  background: ${(props) =>
    props.$active ? OS_LEGAL_COLORS.blueSurface : "white"};
  color: ${(props) =>
    props.$active
      ? OS_LEGAL_COLORS.primaryBlue
      : OS_LEGAL_COLORS.textSecondary};
  font-weight: ${(props) => (props.$active ? "600" : "500")};
  font-size: 0.875rem;
  cursor: pointer;
  transition: all 0.2s;
  border-bottom: 2px solid
    ${(props) => (props.$active ? OS_LEGAL_COLORS.primaryBlue : "transparent")};
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;

  &:hover:not(:disabled) {
    background: ${(props) =>
      props.$active
        ? OS_LEGAL_COLORS.blueSurface
        : OS_LEGAL_COLORS.surfaceHover};
  }

  svg {
    width: 16px;
    height: 16px;
  }
`;

export const SidebarTabsContainer = styled.div<{ $panelOpen: boolean }>`
  position: ${(props) => (props.$panelOpen ? "absolute" : "fixed")};
  left: ${(props) => (props.$panelOpen ? "-48px" : "auto")};
  right: ${(props) => (props.$panelOpen ? "auto" : "0")};
  top: 50%;
  transform: translateY(-50%);
  display: flex;
  flex-direction: column;
  gap: 6px;
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
  width: ${(props) => (props.$panelOpen ? "44px" : "36px")};
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
  gap: 0.375rem;
  padding: 0.5rem 0.375rem;
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
    width: 18px;
    height: 18px;
    color: ${(props) =>
      props.$isActive ? "white" : OS_LEGAL_COLORS.textSecondary};
    transition: all 0.3s ease;
    position: relative;
    z-index: 1;
    flex-shrink: 0;
  }

  .tab-label {
    writing-mode: vertical-rl;
    text-orientation: mixed;
    font-size: 0.6875rem;
    font-weight: 600;
    letter-spacing: 0.05em;
    color: ${(props) =>
      props.$isActive ? "white" : OS_LEGAL_COLORS.textSecondary};
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
      color: ${(props) =>
        props.$isActive ? "white" : OS_LEGAL_COLORS.primaryBlue};
    }

    .tab-label {
      color: ${(props) =>
        props.$isActive ? "white" : OS_LEGAL_COLORS.primaryBlue};
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
