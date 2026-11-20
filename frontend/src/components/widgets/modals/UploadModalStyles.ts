import styled, { css, keyframes } from "styled-components";
import { MOBILE_VIEW_BREAKPOINT } from "../../../assets/configurations/constants";
import { accentAlpha } from "../../../assets/configurations/osLegalStyles";
import { modalFooterBorder, modalFooterMobile } from "./sharedModalStyles";

// Animation keyframes
const fadeIn = keyframes`
  from {
    opacity: 0;
    transform: translateY(-10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
`;

const pulse = keyframes`
  0% {
    box-shadow: 0 0 0 0 ${accentAlpha(0.3)};
  }
  70% {
    box-shadow: 0 0 0 10px ${accentAlpha(0)};
  }
  100% {
    box-shadow: 0 0 0 0 ${accentAlpha(0)};
  }
`;

// Modal wrapper with styling overrides for @os-legal/ui Modal
export const StyledModalWrapper = styled.div`
  .oc-modal-overlay {
    padding: var(--oc-spacing-md);

    @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
      padding: 0;
      align-items: flex-end;
    }
  }

  .oc-modal {
    width: 100%;
    max-width: 640px;
    overflow-y: auto;
    overflow-x: visible;
    animation: ${fadeIn} 0.25s ease-out;

    @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
      max-width: 100%;
      max-height: 95vh;
      border-radius: var(--oc-radius-lg) var(--oc-radius-lg) 0 0;
    }
  }

  .oc-modal-body {
    background: var(--oc-bg-surface);
    padding: var(--oc-spacing-lg);
    overflow: visible;

    @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
      padding: var(--oc-spacing-md);
      -webkit-overflow-scrolling: touch;
      overflow-y: auto;
    }
  }

  .oc-modal-footer {
    background: var(--oc-bg-surface);
    ${modalFooterBorder}
    ${modalFooterMobile}
  }
`;

// Header icon wrapper
// Uses calc() with spacing tokens to derive icon container and inner SVG sizes
export const HeaderIcon = styled.span`
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: calc(var(--oc-spacing-lg) + var(--oc-spacing-xs)); /* 28px */
  height: calc(var(--oc-spacing-lg) + var(--oc-spacing-xs)); /* 28px */
  border-radius: var(--oc-radius-md);
  background: var(--oc-accent);
  color: white;
  margin-right: var(--oc-spacing-xs);

  svg {
    width: var(--oc-font-size-md); /* 15px */
    height: var(--oc-font-size-md); /* 15px */
  }
`;

// Step indicator
export const StepIndicator = styled.div`
  display: flex;
  justify-content: center;
  align-items: center;
  gap: var(--oc-spacing-sm);
  margin-bottom: var(--oc-spacing-lg);

  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    gap: var(--oc-spacing-xs);
    margin-bottom: var(--oc-spacing-md);
  }
`;

export const Step = styled.div<{ $active?: boolean; $completed?: boolean }>`
  display: flex;
  align-items: center;
  gap: var(--oc-spacing-xs);
  padding: calc(var(--oc-spacing-xs) * 1.5) var(--oc-spacing-sm);
  border-radius: var(--oc-radius-full);
  font-size: var(--oc-font-size-xs);
  font-weight: 500;
  transition: all 0.2s ease;

  svg {
    width: 13px;
    height: 13px;
  }

  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    padding: var(--oc-spacing-xs);
    font-size: var(--oc-font-size-xs);

    svg {
      width: 11px;
      height: 11px;
    }
  }

  ${({ $active, $completed }) =>
    $active
      ? css`
          background: var(--oc-accent);
          color: white;
        `
      : $completed
        ? css`
            background: var(--oc-success-bg);
            color: var(--oc-success);
          `
        : css`
            background: var(--oc-bg-subtle);
            color: var(--oc-fg-tertiary);
          `}
`;

export const StepConnector = styled.div<{ $completed?: boolean }>`
  width: 24px;
  height: 2px;
  background: ${({ $completed }) =>
    $completed ? "var(--oc-success)" : "var(--oc-border-default)"};
  transition: background 0.2s ease;

  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    width: 16px;
  }
`;

// Alert box for warning and info messages
export const AlertBox = styled.div<{ $variant: "warning" | "info" }>`
  border-radius: var(--oc-radius-md);
  padding: var(--oc-spacing-md);
  margin-bottom: var(--oc-spacing-md);
  display: flex;
  gap: var(--oc-spacing-sm);
  font-size: var(--oc-font-size-sm);
  line-height: 1.5;

  svg {
    flex-shrink: 0;
    width: 18px;
    height: 18px;
    /* Optical alignment: nudge icon down 2px to align with first line of text */
    margin-top: calc(var(--oc-spacing-xs) / 2);
  }

  ${({ $variant }) =>
    $variant === "warning"
      ? css`
          background: var(--oc-warning-surface);
          color: var(--oc-warning-text);
          border: 1px solid var(--oc-warning-border);
        `
      : css`
          background: var(--oc-info-surface);
          color: var(--oc-info-text);
          border: 1px solid var(--oc-info-border);
        `}

  &:last-child {
    margin-bottom: 0;
  }
`;

export const AlertTitle = styled.div`
  font-weight: 600;
  margin-bottom: calc(var(--oc-spacing-xs) / 2);
`;

export const AlertBody = styled.div`
  flex: 1;

  p {
    margin: calc(var(--oc-spacing-xs) / 2) 0 0 0;
  }

  ul {
    margin: calc(var(--oc-spacing-xs) / 2) 0 0 0;
    padding-left: var(--oc-spacing-md);
  }

  li {
    margin-bottom: calc(var(--oc-spacing-xs) / 2);

    &:last-child {
      margin-bottom: 0;
    }
  }
`;

// Drag and drop zone
export const DropZone = styled.div<{
  $isDragActive?: boolean;
  $hasFiles?: boolean;
}>`
  border: 1.5px dashed
    ${({ $isDragActive }) =>
      $isDragActive ? "var(--oc-accent)" : "var(--oc-border-default)"};
  border-radius: var(--oc-radius-lg);
  background: ${({ $isDragActive }) =>
    $isDragActive ? accentAlpha(0.05) : "var(--oc-bg-subtle)"};
  min-height: 200px; /* Drop zone minimum height — no clean token multiple */
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--oc-spacing-xl);
  cursor: ${({ $hasFiles }) => ($hasFiles ? "default" : "pointer")};
  transition: all 0.2s ease;
  position: relative;
  overflow: hidden;

  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    min-height: 160px; /* Mobile drop zone minimum height — no clean token multiple */
    padding: var(--oc-spacing-lg) var(--oc-spacing-md);
  }

  &:hover {
    border-color: ${({ $hasFiles }) =>
      $hasFiles ? "var(--oc-border-default)" : "var(--oc-accent)"};
    background: ${({ $hasFiles }) =>
      $hasFiles ? "var(--oc-bg-surface-hover)" : accentAlpha(0.03)};
  }

  ${({ $isDragActive }) =>
    $isDragActive &&
    css`
      animation: ${pulse} 1.5s infinite;
    `}
`;

export const DropZoneIcon = styled.div`
  color: var(--oc-accent);
  margin-bottom: var(--oc-spacing-sm);
  opacity: 0.6;

  svg {
    width: 40px;
    height: 40px;
  }

  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    svg {
      width: 32px;
      height: 32px;
    }
    margin-bottom: var(--oc-spacing-xs);
  }
`;

export const DropZoneText = styled.div`
  text-align: center;

  .primary-text {
    font-size: var(--oc-font-size-md);
    font-weight: 500;
    color: var(--oc-fg-primary);
    margin-bottom: var(--oc-spacing-xs);

    @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
      font-size: var(--oc-font-size-sm);
    }
  }

  .secondary-text {
    font-size: var(--oc-font-size-sm);
    color: var(--oc-fg-secondary);

    @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
      font-size: var(--oc-font-size-xs);
    }
  }
`;

export const DropZoneButton = styled.button`
  margin-top: var(--oc-spacing-md);
  background: var(--oc-accent);
  color: white;
  border-radius: var(--oc-radius-md);
  padding: var(--oc-spacing-sm) var(--oc-spacing-lg);
  font-weight: 500;
  font-size: var(--oc-font-size-sm);
  transition: all 0.2s ease;
  min-height: 44px; /* WCAG 2.5.5 touch target minimum */
  border: none;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: var(--oc-spacing-xs);

  svg {
    width: 14px;
    height: 14px;
    flex-shrink: 0;
  }

  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    width: 100%;
    justify-content: center;
    padding: var(--oc-spacing-sm) var(--oc-spacing-md);
  }

  &:hover {
    background: var(--oc-accent-hover);
    box-shadow: 0 2px 8px ${accentAlpha(0.3)};
  }

  &:active {
    transform: translateY(0);
  }
`;

// Inline icon wrapper for footer buttons (e.g. "Start Import")
export const ButtonIcon = styled.span`
  display: inline-flex;
  align-items: center;
  margin-right: var(--oc-spacing-xs);

  svg {
    width: var(--oc-font-size-md);
    height: var(--oc-font-size-md);
  }
`;

// Progress indicator
export const UploadProgress = styled.div<{ $percent?: number }>`
  margin: var(--oc-spacing-md) 0;
  border-radius: var(--oc-radius-md);
  overflow: hidden;
  background: var(--oc-bg-subtle);
  height: 8px;
  position: relative;

  &::after {
    content: "";
    display: block;
    height: 100%;
    width: ${({ $percent }) => $percent ?? 0}%;
    background: var(--oc-accent);
    border-radius: var(--oc-radius-md);
    transition: width 0.3s ease;
  }
`;

export const ProgressLabel = styled.div`
  font-size: var(--oc-font-size-xs);
  color: var(--oc-fg-secondary);
  text-align: center;
  margin-top: var(--oc-spacing-xs);
  font-weight: 500;
`;

// Error message styling
export const ErrorMessage = styled.div`
  background: var(--oc-error-bg);
  border: 1px solid var(--oc-error);
  border-radius: var(--oc-radius-md);
  padding: var(--oc-spacing-sm) var(--oc-spacing-md);
  margin-bottom: var(--oc-spacing-md);
  display: flex;
  align-items: flex-start;
  gap: var(--oc-spacing-sm);

  svg {
    color: var(--oc-error);
    flex-shrink: 0;
    width: 16px;
    height: 16px;
  }

  .content {
    flex: 1;

    .header {
      font-weight: 600;
      color: var(--oc-error);
      font-size: var(--oc-font-size-xs);
      margin-bottom: calc(var(--oc-spacing-xs) / 2);
    }

    .message {
      font-size: var(--oc-font-size-xs);
      color: var(--oc-fg-secondary);
    }
  }
`;

// Spin animation for loader (used internally by SpinnerIcon)
const spinKeyframes = keyframes`
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
`;

export const SpinnerIcon = styled.div`
  color: var(--oc-accent);
  margin-bottom: var(--oc-spacing-md);

  svg {
    width: 40px;
    height: 40px;
    animation: ${spinKeyframes} 1s linear infinite;
  }
`;

export const ProgressContent = styled.div`
  text-align: center;
  padding: var(--oc-spacing-xl) var(--oc-spacing-lg);

  h3 {
    font-size: var(--oc-font-size-lg);
    font-weight: 600;
    color: var(--oc-fg-primary);
    margin: 0 0 var(--oc-spacing-xs) 0;
  }

  p {
    font-size: var(--oc-font-size-sm);
    color: var(--oc-fg-secondary);
    margin: 0 0 var(--oc-spacing-lg) 0;
  }
`;
