import styled from "styled-components";
import { motion } from "framer-motion";
import {
  OS_LEGAL_COLORS,
  accentAlpha,
  navBlueAlpha,
  navIndigoAlpha,
} from "../assets/configurations/osLegalStyles";
import { MOBILE_VIEW_BREAKPOINT } from "../assets/configurations/constants";
import {
  CORPUS_COLORS,
  CORPUS_SHADOWS,
  CORPUS_TRANSITIONS,
} from "../components/corpuses/styles/corpusDesignTokens";

// ===============================================
// SIDEBAR NAVIGATION
// ===============================================
// Fill at least the visible area below the navbar so short tabs don't leave
// dead space, but never exceed it — the chat tray needs its input pinned at
// the bottom of the viewport, not pushed below it.
export const CorpusViewContainer = styled.div`
  display: flex;
  flex-direction: row;
  width: 100%;
  position: relative;
  flex: 1;
  align-items: stretch;
  min-height: calc(100vh - var(--oc-navbar-height, 4.5rem));
  min-height: calc(100dvh - var(--oc-navbar-height, 4.5rem));
`;

export const NavigationSidebar = styled(motion.div)<{ $isExpanded: boolean }>`
  position: relative;
  width: ${(props) => (props.$isExpanded ? "280px" : "80px")};
  background: linear-gradient(180deg, #ffffff 0%, #fafbfc 50%, #f8f9fa 100%);
  backdrop-filter: blur(10px);
  border-right: 1px solid ${OS_LEGAL_COLORS.border};
  box-shadow: ${(props) =>
    props.$isExpanded
      ? "2px 0 8px rgba(0, 0, 0, 0.06)"
      : "2px 0 4px rgba(0, 0, 0, 0.04)"};
  z-index: 100;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  flex-shrink: 0;

  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    position: fixed;
    left: 50%;
    bottom: 0;
    width: 100%;
    max-width: min(480px, 95vw);
    height: ${(props) => (props.$isExpanded ? "70vh" : "0")};
    max-height: min(600px, 70vh);
    border-right: none;
    border-top: 1px solid ${OS_LEGAL_COLORS.border};
    border-radius: 24px 24px 0 0;
    box-shadow: ${(props) =>
      props.$isExpanded ? "0 -8px 32px rgba(0, 0, 0, 0.12)" : "none"};
    transform: translate(
      -50%,
      ${(props) => (props.$isExpanded ? "0" : "100%")}
    );
    transition: transform 0.35s cubic-bezier(0.4, 0, 0.2, 1),
      height 0.35s cubic-bezier(0.4, 0, 0.2, 1);
    z-index: 200;
    background: linear-gradient(180deg, #ffffff 0%, #fafbfc 100%);
  }
`;

// Drag handle for bottom sheet
export const BottomSheetHandle = styled.div`
  display: none;

  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    display: flex;
    justify-content: center;
    padding: 0.75rem 0;
    cursor: grab;

    &::after {
      content: "";
      width: 40px;
      height: 4px;
      background: ${OS_LEGAL_COLORS.borderHover};
      border-radius: 2px;
      transition: background 0.2s ease;
    }

    &:active {
      cursor: grabbing;

      &::after {
        background: ${OS_LEGAL_COLORS.textMuted};
      }
    }
  }
`;

export const NavigationHeader = styled.div<{ $isExpanded: boolean }>`
  padding: 1.5rem;
  border-bottom: 1px solid ${OS_LEGAL_COLORS.border};
  background: white;
  display: flex;
  align-items: center;
  justify-content: ${(props) =>
    props.$isExpanded ? "space-between" : "center"};
  min-height: 72px;
  position: relative;
  gap: 0.75rem;

  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    padding: 0 1.5rem 1rem;
    min-height: auto;
  }
`;

export const NavigationToggle = styled(motion.button)`
  width: 40px;
  height: 40px;
  border-radius: 12px;
  background: linear-gradient(
    135deg,
    rgba(255, 255, 255, 0.9) 0%,
    rgba(248, 250, 252, 0.9) 100%
  );
  border: 1px solid rgba(226, 232, 240, 0.6);
  color: ${OS_LEGAL_COLORS.textSecondary};
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.04), 0 1px 2px rgba(0, 0, 0, 0.06);
  position: relative;
  overflow: hidden;

  /* Ripple effect base */
  &::before {
    content: "";
    position: absolute;
    top: 50%;
    left: 50%;
    width: 0;
    height: 0;
    border-radius: 50%;
    background: radial-gradient(
      circle,
      ${navBlueAlpha(0.2)} 0%,
      transparent 70%
    );
    transform: translate(-50%, -50%);
    transition: width 0.4s, height 0.4s;
  }

  &:hover {
    background: linear-gradient(
      135deg,
      ${navBlueAlpha(0.1)} 0%,
      ${navIndigoAlpha(0.08)} 100%
    );
    border-color: ${navBlueAlpha(0.3)};
    color: ${OS_LEGAL_COLORS.primaryBlue};
    transform: translateY(-1px);
    box-shadow: 0 4px 6px ${navBlueAlpha(0.1)}, 0 2px 4px rgba(0, 0, 0, 0.06);

    &::before {
      width: 80px;
      height: 80px;
    }

    svg {
      transform: scale(1.1);
    }
  }

  &:active {
    transform: translateY(0);
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
  }

  svg {
    width: 20px;
    height: 20px;
    transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    z-index: 1;
  }
`;

export const NavigationItems = styled.div`
  flex: 1;
  padding: 1rem 0;
  overflow-y: auto;
  overflow-x: hidden;
  position: relative;

  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    padding: 0.5rem 0 2rem;
  }

  /* Fade effect at top and bottom */
  &::before,
  &::after {
    content: "";
    position: absolute;
    left: 0;
    right: 0;
    height: 20px;
    pointer-events: none;
    z-index: 1;
    opacity: 0;
    transition: opacity 0.3s ease;
  }

  &::before {
    top: 0;
    background: linear-gradient(
      180deg,
      rgba(255, 255, 255, 0.9) 0%,
      transparent 100%
    );
  }

  &::after {
    bottom: 0;
    background: linear-gradient(
      0deg,
      rgba(255, 255, 255, 0.9) 0%,
      transparent 100%
    );
  }

  /* Show fade when scrollable */
  &:hover::before,
  &:hover::after {
    opacity: 1;
  }

  /* Custom scrollbar styling */
  &::-webkit-scrollbar {
    width: 6px;
  }

  &::-webkit-scrollbar-track {
    background: transparent;
    margin: 8px 0;
  }

  &::-webkit-scrollbar-thumb {
    background: linear-gradient(
      180deg,
      rgba(226, 232, 240, 0.8) 0%,
      rgba(203, 213, 225, 0.8) 100%
    );
    border-radius: 3px;
    border: 1px solid rgba(255, 255, 255, 0.3);
    transition: all 0.2s ease;

    &:hover {
      background: linear-gradient(
        180deg,
        rgba(203, 213, 225, 0.9) 0%,
        rgba(148, 163, 184, 0.9) 100%
      );
      box-shadow: 0 0 0 1px ${navBlueAlpha(0.2)};
    }

    &:active {
      background: linear-gradient(
        180deg,
        rgba(148, 163, 184, 1) 0%,
        rgba(100, 116, 139, 1) 100%
      );
    }
  }

  /* Firefox scrollbar support */
  scrollbar-width: thin;
  scrollbar-color: rgba(203, 213, 225, 0.8) transparent;
`;

// Badge for count display on navigation items
export const NavItemBadge = styled.span<{
  $isActive: boolean;
  $isZero?: boolean;
}>`
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 22px;
  height: 22px;
  padding: 0 6px;
  border-radius: 11px;
  font-size: 0.6875rem;
  font-weight: 600;
  margin-left: auto;
  background: ${(props) =>
    props.$isZero
      ? "transparent"
      : props.$isActive
      ? CORPUS_COLORS.teal[700]
      : CORPUS_COLORS.slate[200]};
  color: ${(props) =>
    props.$isZero
      ? CORPUS_COLORS.slate[400]
      : props.$isActive
      ? CORPUS_COLORS.white
      : CORPUS_COLORS.slate[600]};
  border: ${(props) =>
    props.$isZero ? `1px dashed ${CORPUS_COLORS.slate[300]}` : "none"};
  transition: all ${CORPUS_TRANSITIONS.normal};
  box-shadow: ${(props) =>
    props.$isZero
      ? "none"
      : props.$isActive
      ? `0 2px 4px ${accentAlpha(0.25)}`
      : CORPUS_SHADOWS.sm};
`;

export const NavigationItem = styled(motion.button)<{
  $isActive: boolean;
  $isExpanded: boolean;
}>`
  width: 100%;
  display: flex;
  align-items: center;
  gap: ${(props) => (props.$isExpanded ? "0.75rem" : "0")};
  padding: ${(props) =>
    props.$isExpanded ? "0.875rem 1rem 0.875rem 1.5rem" : "0.875rem"};
  margin: ${(props) => (props.$isExpanded ? "0 0.5rem" : "0 0.25rem")};
  width: ${(props) =>
    props.$isExpanded ? "calc(100% - 1rem)" : "calc(100% - 0.5rem)"};
  border-radius: ${(props) => (props.$isExpanded ? "12px" : "10px")};
  background: ${(props) => {
    if (props.$isActive) {
      return `linear-gradient(
        135deg,
        ${navBlueAlpha(0.12)} 0%,
        ${navIndigoAlpha(0.08)} 100%
      )`;
    }
    return "transparent";
  }};
  border: 1px solid
    ${(props) => (props.$isActive ? navBlueAlpha(0.2) : "transparent")};
  color: ${(props) =>
    props.$isActive
      ? OS_LEGAL_COLORS.primaryBlue
      : OS_LEGAL_COLORS.textSecondary};
  font-weight: ${(props) => (props.$isActive ? "600" : "500")};
  font-size: 0.9375rem;
  cursor: pointer;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  position: relative;
  justify-content: ${(props) => (props.$isExpanded ? "flex-start" : "center")};
  overflow: hidden;
  min-height: ${(props) => (props.$isExpanded ? "48px" : "44px")};

  /* Active indicator bar */
  &::before {
    content: "";
    position: absolute;
    left: ${(props) => (props.$isExpanded ? "-0.5rem" : "50%")};
    top: ${(props) => (props.$isExpanded ? "50%" : "0")};
    width: ${(props) => (props.$isExpanded ? "4px" : "60%")};
    height: ${(props) => (props.$isExpanded ? "60%" : "2px")};
    background: linear-gradient(
      ${(props) => (props.$isExpanded ? "180deg" : "90deg")},
      ${OS_LEGAL_COLORS.navBlue} 0%,
      ${OS_LEGAL_COLORS.navIndigo} 100%
    );
    opacity: ${(props) => (props.$isActive ? "1" : "0")};
    transform: ${(props) =>
      props.$isExpanded ? "translateY(-50%)" : "translateX(-50%)"};
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    border-radius: 2px;
    box-shadow: ${(props) =>
      props.$isActive ? `0 0 8px ${navBlueAlpha(0.5)}` : "none"};
  }

  /* Hover background effect */
  &::after {
    content: "";
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: radial-gradient(
      circle at center,
      ${navBlueAlpha(0.08)} 0%,
      transparent 70%
    );
    opacity: 0;
    transition: opacity 0.3s ease;
    pointer-events: none;
  }

  &:hover {
    background: ${(props) => {
      if (props.$isActive) {
        return `linear-gradient(
          135deg,
          ${navBlueAlpha(0.16)} 0%,
          ${navIndigoAlpha(0.12)} 100%
        )`;
      }
      return `linear-gradient(
        135deg,
        rgba(226, 232, 240, 0.3) 0%,
        rgba(241, 245, 249, 0.2) 100%
      )`;
    }};
    border-color: ${(props) =>
      props.$isActive ? navBlueAlpha(0.3) : "rgba(226, 232, 240, 0.5)"};
    color: ${(props) =>
      props.$isActive
        ? OS_LEGAL_COLORS.primaryBlue
        : OS_LEGAL_COLORS.textTertiary};
    transform: ${(props) =>
      props.$isExpanded ? "translateX(2px)" : "scale(1.05)"};

    &::after {
      opacity: 1;
    }

    svg {
      transform: ${(props) =>
        props.$isActive ? "scale(1.15) rotate(-5deg)" : "scale(1.1)"};
      filter: ${(props) =>
        props.$isActive
          ? `drop-shadow(0 2px 4px ${navBlueAlpha(0.3)})`
          : "none"};
    }
  }

  &:active {
    transform: ${(props) =>
      props.$isExpanded ? "translateX(0)" : "scale(0.98)"};
  }

  svg {
    width: 20px;
    height: 20px;
    flex-shrink: 0;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    z-index: 1;
  }

  span {
    white-space: nowrap;
    opacity: ${(props) => (props.$isExpanded ? "1" : "0")};
    width: ${(props) => (props.$isExpanded ? "auto" : "0")};
    overflow: hidden;
    transition: opacity 0.3s ease, width 0.3s ease;
    z-index: 1;
  }

  /* Accessibility - focus visible */
  &:focus-visible {
    outline: 2px solid ${OS_LEGAL_COLORS.primaryBlue};
    outline-offset: 2px;
  }

  /* Respect reduced motion preferences */
  @media (prefers-reduced-motion: reduce) {
    transition: background-color 0.2s ease, color 0.2s ease;

    &:hover {
      transform: none;
    }

    svg {
      transition: none;
      transform: none !important;
    }
  }
`;

export const MainContentArea = styled.div`
  flex: 1;
  position: relative;
  display: flex;
  flex-direction: column;
  min-width: 0;

  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    margin-left: 0;
  }
`;

export const MobileMenuBackdrop = styled(motion.div)`
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.4);
  backdrop-filter: blur(8px);
  z-index: 190;
  display: none;
  -webkit-tap-highlight-color: transparent;

  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    display: block;
  }
`;

// Unified search bar wrapper with integrated back button
export const SearchBarWithNav = styled.div`
  display: flex;
  align-items: stretch;
  width: 100%;
  background: white;
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 12px;
  overflow: hidden;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
  transition: all 0.2s ease;

  &:focus-within {
    border-color: ${OS_LEGAL_COLORS.borderHover};
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.08);
  }
`;

// Integrated back button - no separate border, part of unified container
export const MobileBackButton = styled.button`
  display: none;
  padding: 0 0.875rem;
  min-width: auto;
  background: transparent;
  border: none;
  border-right: 1px solid ${OS_LEGAL_COLORS.border};
  color: ${OS_LEGAL_COLORS.textSecondary};
  transition: all 0.2s ease;
  cursor: pointer;
  flex-shrink: 0;

  &:hover {
    background: ${OS_LEGAL_COLORS.surfaceHover};
    color: ${OS_LEGAL_COLORS.textTertiary};
  }

  &:active {
    background: ${OS_LEGAL_COLORS.surfaceLight};
  }

  svg {
    width: 20px;
    height: 20px;
  }

  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    display: flex;
    align-items: center;
    justify-content: center;
  }
`;

// ===============================================
// TAB HEADER (shared with ExtractsTabContent)
// ===============================================
// Back navigation header for non-home tabs - CRISPY VERSION
export const TabNavigationHeader = styled.div`
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.875rem 1.25rem;
  background: white;
  border-bottom: 1px solid ${OS_LEGAL_COLORS.border};
  flex-shrink: 0;
  min-height: 56px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);

  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    padding: 0.625rem 1rem;
    min-height: 48px;
  }
`;

// Mobile kebab menu button for tab headers - only visible on mobile
export const MobileKebabButton = styled.button`
  display: none;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  padding: 0;
  background: transparent;
  border: none;
  border-radius: 6px;
  color: ${OS_LEGAL_COLORS.textSecondary};
  cursor: pointer;
  transition: all 0.15s ease;
  flex-shrink: 0;
  margin-left: auto;

  &:hover {
    background: ${OS_LEGAL_COLORS.successSurface};
    color: ${OS_LEGAL_COLORS.accent};
  }

  &:active {
    transform: scale(0.95);
  }

  svg {
    width: 20px;
    height: 20px;
  }

  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    display: flex;
  }
`;

export const BackNavButton = styled(motion.button)`
  display: flex;
  align-items: center;
  justify-content: center;
  background: ${OS_LEGAL_COLORS.surfaceHover};
  border: 1px solid ${OS_LEGAL_COLORS.border};
  color: ${OS_LEGAL_COLORS.textSecondary};
  cursor: pointer;
  padding: 0;
  width: 36px;
  height: 36px;
  border-radius: 10px;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
  flex-shrink: 0;

  &:hover {
    background: white;
    border-color: ${OS_LEGAL_COLORS.primaryBlue};
    color: ${OS_LEGAL_COLORS.primaryBlue};
    box-shadow: 0 2px 8px ${navBlueAlpha(0.15)};
  }

  &:active {
    transform: scale(0.95);
  }

  svg {
    width: 20px;
    height: 20px;
    stroke-width: 2.5;
  }

  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    width: 32px;
    height: 32px;

    svg {
      width: 18px;
      height: 18px;
    }
  }
`;

export const TabTitle = styled.h2`
  font-size: 1.5rem;
  font-weight: 800;
  color: ${OS_LEGAL_COLORS.textPrimary};
  margin: 0;
  flex: 1;
  letter-spacing: -0.025em;
  line-height: 1;

  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    font-size: 1.25rem;
  }
`;

export const SearchBarContainer = styled.div`
  flex: 1;
  display: flex;
  min-width: 0; /* Allows flex item to shrink below its content size */

  /* Override CreateAndSearchBar's internal styles to remove duplicate borders */
  > div {
    width: 100%;
    border: none !important;
    box-shadow: none !important;
    border-radius: 0 !important;

    /* Override the SearchInputWrapper max-width on mobile */
    > div:first-child {
      @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
        max-width: none;
        flex: 1;
      }
    }
  }
`;

// ===============================================
// NOTIFICATION BADGES
// ===============================================
// Compact badge for collapsed sidebar - slight overlap at corner.
// Teal (non-zero) / slate (zero) is intentional: these badges display entity
// counts (documents, annotations, analyses, etc.), not action-required items,
// so the teal design-token color is appropriate rather than a warning palette.
export const CollapsedBadge = styled.div<{ $isZero: boolean }>`
  position: absolute;
  top: -4px;
  right: -12px;
  min-width: 16px;
  height: 16px;
  padding: 0 4px;
  background: ${(props) =>
    props.$isZero ? CORPUS_COLORS.slate[400] : CORPUS_COLORS.teal[700]};
  color: ${CORPUS_COLORS.white};
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0.6rem;
  font-weight: 700;
  z-index: 2;
  box-shadow: ${CORPUS_SHADOWS.sm};
`;

// ===============================================
// CLEAN-VIEW (no-sidebar) LANDING WRAPPERS
// ===============================================
// Container for the clean landing view (no sidebar).
// Does NOT scroll — LandingContainer (inside CorpusLandingView) handles scrolling
// via overflow-y: auto.  This wrapper only provides flex layout so that the
// LandingContainer child can fill the available height.
//
// Height model:
//   CardLayout → CleanViewContainer → LandingContainer
//   - height: 100% + min-height: 0  → fills the flex parent while allowing
//     shrink, giving LandingContainer a bounded block size.
//   - overflow: hidden              → prevents this container from scrolling;
//     all scrolling happens inside LandingContainer's overflow-y: auto.
//   - max-height: 100dvh was removed because the flex ancestor chain already
//     constrains height, and the extra cap conflicted with LandingContainer's
//     own scroll container.
export const CleanViewContainer = styled.div`
  position: relative;
  display: flex;
  flex-direction: column;
  width: 100%;
  height: 100%;
  min-height: 0;
  overflow: hidden;
`;

// Wrapper for the "Simple View" exit button at the bottom of the sidebar
export const ExitPowerUserWrapper = styled.div`
  padding: 0.75rem;
  border-top: 1px solid ${CORPUS_COLORS.slate[200]};
  flex-shrink: 0;
`;
