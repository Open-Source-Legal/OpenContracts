import styled from "styled-components";
import {
  accentAlpha,
  OS_LEGAL_COLORS,
  OS_LEGAL_SPACING,
} from "../../../../assets/configurations/osLegalStyles";

export const HeaderButtonGroup = styled.div`
  display: flex;
  gap: 8px;
  align-items: center;
  flex-shrink: 0;
  min-width: 0;
`;

export const HeaderButton = styled.button<{
  $variant?: "primary" | "secondary";
}>`
  height: 36px;
  padding: 0 ${(props) => (props.$variant === "primary" ? "14px" : "10px")};
  background: ${(props) =>
    props.$variant === "primary"
      ? OS_LEGAL_COLORS.accentSurface
      : OS_LEGAL_COLORS.surface};
  color: ${(props) =>
    props.$variant === "primary"
      ? OS_LEGAL_COLORS.accent
      : OS_LEGAL_COLORS.textTertiary};
  border: 1px solid
    ${(props) =>
      props.$variant === "primary"
        ? OS_LEGAL_COLORS.accentMedium
        : OS_LEGAL_COLORS.border};
  border-radius: ${OS_LEGAL_SPACING.borderRadiusButton};
  font-size: ${(props) => (props.$variant === "primary" ? "13px" : "14px")};
  font-weight: ${(props) => (props.$variant === "primary" ? "600" : "500")};
  letter-spacing: 0;
  line-height: 1;
  cursor: pointer;
  transition: background 0.2s ease, border-color 0.2s ease, box-shadow 0.2s ease,
    transform 0.2s ease;
  display: flex;
  align-items: center;
  gap: ${(props) => (props.$variant === "primary" ? "8px" : "0")};
  box-shadow: ${(props) =>
    props.$variant === "primary"
      ? `0 1px 2px ${accentAlpha(0.12)}`
      : "0 1px 3px rgba(15, 23, 42, 0.06)"};
  position: relative;
  overflow: hidden;
  white-space: nowrap;

  &:hover {
    transform: translateY(-1px);
    background: ${(props) =>
      props.$variant === "primary"
        ? OS_LEGAL_COLORS.accentLight
        : OS_LEGAL_COLORS.surfaceHover};
    box-shadow: ${(props) =>
      props.$variant === "primary"
        ? `0 3px 8px ${accentAlpha(0.16)}`
        : "0 4px 10px rgba(15, 23, 42, 0.08)"};
    border-color: ${(props) =>
      props.$variant === "primary"
        ? OS_LEGAL_COLORS.accent
        : OS_LEGAL_COLORS.borderHover};
  }

  &:active {
    transform: translateY(0);
    box-shadow: ${(props) =>
      props.$variant === "primary"
        ? `0 1px 4px ${accentAlpha(0.12)}`
        : "inset 0 1px 2px rgba(15, 23, 42, 0.08)"};
  }

  svg {
    width: 18px;
    height: 18px;
    stroke-width: 2.5;
    flex-shrink: 0;
  }

  @media (max-width: 480px) {
    width: 36px;
    height: 36px;
    padding: 0;
    justify-content: center;
    gap: 0;

    .header-button-label--desktop {
      display: none;
    }

    svg {
      width: 17px;
      height: 17px;
    }
  }
`;

export const FloatingInputWrapper = styled.div<{ $panelOffset: number }>`
  position: absolute;
  bottom: 4rem; /* Increased from 2rem to give more space from bottom */
  left: 0;
  right: ${(props) => props.$panelOffset}px;
  display: flex;
  justify-content: center;
  pointer-events: none; /* allow clicks only on children */
  z-index: 850;

  @media (max-width: 768px) {
    /* On mobile, position below zoom controls with higher z-index to prevent covering */
    position: absolute;
    top: 80px; /* Below zoom controls */
    left: 1rem;
    right: auto; /* Don't constrain right side for collapsed state */
    bottom: auto;
    width: auto; /* Let child determine width */
    display: block;
    pointer-events: none;
    box-sizing: border-box;
    /* Fix Issue #1: Increase z-index above zoom controls (900) to prevent mobile tray from covering input */
    z-index: 950;
  }
`;

export const ZoomIndicator = styled.div`
  position: fixed;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  background: rgba(0, 0, 0, 0.8);
  color: white;
  padding: 12px 24px;
  border-radius: 8px;
  font-size: 18px;
  font-weight: 600;
  z-index: 2000;
  pointer-events: none;
  transition: opacity 0.2s ease-in-out;
`;

export const ContextBarContainer = styled.div`
  background: linear-gradient(
    90deg,
    rgba(102, 126, 234, 0.95) 0%,
    rgba(118, 75, 162, 0.95) 100%
  );
  backdrop-filter: blur(10px);
  color: white;
  padding: 8px 20px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-shrink: 0;
  border-bottom: 1px solid rgba(255, 255, 255, 0.15);
  box-shadow: 0 4px 12px rgba(102, 126, 234, 0.2);
  animation: slideDown 0.3s cubic-bezier(0.4, 0, 0.2, 1);

  @keyframes slideDown {
    from {
      opacity: 0;
      transform: translateY(-8px);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }
`;

export const ContextBarContent = styled.div`
  display: flex;
  align-items: center;
  gap: 12px;
  flex: 1;
  min-width: 0;
`;

export const ContextBarBadge = styled.div`
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  background: rgba(255, 255, 255, 0.2);
  border: 1px solid rgba(255, 255, 255, 0.3);
  border-radius: 20px;
  font-size: 13px;
  font-weight: 600;
  letter-spacing: 0.3px;
  flex-shrink: 0;

  svg,
  i {
    width: 16px;
    height: 16px;
    margin: 0 !important;
  }
`;

export const ContextBarLabel = styled.div`
  font-size: 14px;
  font-weight: 500;
  opacity: 0.95;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
`;

export const ContextBarStats = styled.div`
  display: flex;
  align-items: center;
  gap: 12px;
  margin-left: auto;
  margin-right: 12px;
`;

export const StatPill = styled.div`
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  background: rgba(255, 255, 255, 0.15);
  border-radius: 12px;
  font-size: 12px;
  font-weight: 600;

  svg,
  i {
    width: 14px;
    height: 14px;
    opacity: 0.9;
    margin: 0 !important;
  }
`;

export const CloseButton = styled.button`
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  padding: 0;
  background: rgba(255, 255, 255, 0.15);
  border: 1px solid rgba(255, 255, 255, 0.25);
  border-radius: 50%;
  color: white;
  cursor: pointer;
  transition: all 0.2s ease;
  flex-shrink: 0;

  &:hover {
    background: rgba(255, 255, 255, 0.25);
    border-color: rgba(255, 255, 255, 0.4);
    transform: scale(1.05);
  }

  &:active {
    transform: scale(0.95);
  }

  svg {
    width: 14px;
    height: 14px;
  }
`;

export const FlexColumnPanel = styled.div`
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  overflow: hidden;
`;

export const ExtractHeader = styled.div`
  padding: 1rem 1.5rem;
  border-bottom: 1px solid ${OS_LEGAL_COLORS.border};
  background: ${OS_LEGAL_COLORS.surfaceHover};
  display: flex;
  align-items: center;
  gap: 0.75rem;
`;

export const ExtractHeaderTitle = styled.div`
  font-weight: 600;
  font-size: 1rem;
  color: ${OS_LEGAL_COLORS.textPrimary};
`;

export const ExtractHeaderSubtitle = styled.div`
  font-size: 0.875rem;
  color: ${OS_LEGAL_COLORS.textSecondary};
`;

export const OverflowHiddenFill = styled.div`
  flex: 1;
  overflow: hidden;
`;

export const ScrollableFillPanel = styled.div`
  flex: 1;
  overflow: auto;
  padding: 0.5rem 0;
`;

export const SidebarHeader = styled.div`
  padding: 1rem 1.5rem;
  border-bottom: 1px solid ${OS_LEGAL_COLORS.border};
  background: ${OS_LEGAL_COLORS.surfaceHover};
  display: flex;
  align-items: center;
  gap: 0.75rem;
`;

export const SidebarHeaderContent = styled.div`
  flex: 1;
  min-width: 0;
`;

export const SidebarHeaderTitle = styled.div`
  font-weight: 600;
  font-size: 1rem;
  color: ${OS_LEGAL_COLORS.textPrimary};
  max-height: 8.4rem; /* ~6 lines at 1.4 line-height */
  overflow-y: auto;
  line-height: 1.4;

  /* Pretty scrollbar */
  &::-webkit-scrollbar {
    width: 4px;
  }
  &::-webkit-scrollbar-track {
    background: transparent;
  }
  &::-webkit-scrollbar-thumb {
    background: ${OS_LEGAL_COLORS.borderHover};
    border-radius: 2px;
  }
  &::-webkit-scrollbar-thumb:hover {
    background: ${OS_LEGAL_COLORS.textMuted};
  }

  /* Clean markdown rendering */
  p {
    margin: 0;
    line-height: 1.4;
  }

  strong,
  b {
    font-weight: 700;
  }

  em,
  i {
    font-style: italic;
  }

  code {
    background: ${OS_LEGAL_COLORS.border};
    padding: 0.125rem 0.375rem;
    border-radius: 3px;
    font-size: 0.875rem;
    font-family: monospace;
  }

  /* Don't let markdown break the layout */
  ul,
  ol,
  h1,
  h2,
  h3,
  h4,
  h5,
  h6 {
    display: none;
  }
`;

export const SidebarHeaderSubtitle = styled.div`
  font-size: 0.875rem;
  color: ${OS_LEGAL_COLORS.textSecondary};
  margin-top: 0.125rem;
`;

export const CompactAnnotationFeed = styled.div`
  height: 100%;
  overflow: hidden;

  /* Compact annotation cards for analysis view */
  .highlight-item {
    margin-bottom: 0.75rem !important;
    border-radius: 10px !important;
    background: white !important;
  }

  /* Clean up markdown in annotation cards */
  .annotation-content {
    p {
      margin: 0.25rem 0 !important;
      line-height: 1.5 !important;
    }

    ul,
    ol {
      margin: 0.5rem 0 !important;
      padding-left: 1.5rem !important;
    }

    li {
      margin: 0.25rem 0 !important;
    }

    h1,
    h2,
    h3,
    h4,
    h5,
    h6 {
      margin: 0.5rem 0 0.25rem 0 !important;
      font-size: 0.95rem !important;
      font-weight: 600 !important;
    }

    code {
      background: ${OS_LEGAL_COLORS.surfaceLight} !important;
      padding: 0.125rem 0.375rem !important;
      border-radius: 3px !important;
      font-size: 0.875rem !important;
    }

    pre {
      background: ${OS_LEGAL_COLORS.surfaceHover} !important;
      padding: 0.75rem !important;
      border-radius: 6px !important;
      overflow-x: auto !important;
      margin: 0.5rem 0 !important;
    }

    blockquote {
      border-left: 3px solid ${OS_LEGAL_COLORS.border} !important;
      padding-left: 1rem !important;
      margin: 0.5rem 0 !important;
      color: ${OS_LEGAL_COLORS.textSecondary} !important;
    }

    /* Compact spacing for analysis results */
    & > *:first-child {
      margin-top: 0 !important;
    }

    & > *:last-child {
      margin-bottom: 0 !important;
    }
  }

  /* Hide unnecessary metadata in compact view */
  .annotation-metadata {
    font-size: 0.8125rem !important;
    color: ${OS_LEGAL_COLORS.textMuted} !important;
  }

  /* Better page headers */
  .page-header {
    background: linear-gradient(to right, #fef3c7 0%, #fef9e7 100%) !important;
    border-left: 3px solid ${OS_LEGAL_COLORS.folderIcon} !important;
  }
`;

export const ExpandCollapseButton = styled.button`
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 6px;
  background: ${OS_LEGAL_COLORS.surface};
  color: ${OS_LEGAL_COLORS.textSecondary};
  font-size: 0.75rem;
  font-weight: 500;
  cursor: pointer;
  flex-shrink: 0;

  &:hover {
    background: ${OS_LEGAL_COLORS.surfaceHover};
  }
`;
