import styled, { css, keyframes } from "styled-components";
import { MOBILE_VIEW_BREAKPOINT } from "../../../../assets/configurations/constants";
import { accentAlpha } from "../../../../assets/configurations/osLegalStyles";
import { modalFooterBorder, modalFooterMobile } from "../sharedModalStyles";

// Breakpoints
const TABLET_BREAKPOINT = 1024;

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

    @media (max-width: ${TABLET_BREAKPOINT}px) {
      max-width: 95vw;
    }

    @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
      max-width: 100%;
      max-height: 95vh;
      border-radius: var(--oc-radius-lg) var(--oc-radius-lg) 0 0;
    }

    @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) and (orientation: landscape) {
      max-height: 100vh;
      border-radius: 0;
    }
  }

  .oc-modal-body {
    background: var(--oc-bg-surface);
    padding: var(--oc-spacing-lg);
    overflow: visible;

    @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
      padding: var(--oc-spacing-md);
      padding-bottom: calc(var(--oc-spacing-xl) + 80px);
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
export const HeaderIcon = styled.span`
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: var(--oc-radius-md);
  background: var(--oc-accent);
  color: white;
  margin-right: var(--oc-spacing-xs);

  svg {
    width: 15px;
    height: 15px;
  }
`;

export const SectionTitle = styled.h3`
  font-size: var(--oc-font-size-sm);
  font-weight: 500;
  color: var(--oc-fg-secondary);
  margin: 0 0 var(--oc-spacing-sm) 0;
  display: flex;
  align-items: center;
  gap: var(--oc-spacing-xs);

  svg {
    width: 14px;
    height: 14px;
  }

  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    font-size: var(--oc-font-size-xs);
    margin-bottom: var(--oc-spacing-xs);
  }
`;

export const FormField = styled.div`
  margin-bottom: var(--oc-spacing-md);

  &:last-child {
    margin-bottom: 0;
  }

  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    margin-bottom: var(--oc-spacing-sm);
  }

  .oc-input-wrapper,
  .oc-textarea-wrapper {
    width: 100%;
  }

  .oc-input-container--lg {
    min-height: 48px;
  }

  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    .oc-input,
    .oc-textarea {
      font-size: 16px; /* Prevent iOS zoom */
    }
  }
`;

// Two-column layout
export const FormRow = styled.div`
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--oc-spacing-md);

  @media (max-width: ${TABLET_BREAKPOINT}px) {
    grid-template-columns: 1fr;
  }
`;

// Drop zone for file upload
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
  min-height: 160px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--oc-spacing-lg);
  cursor: ${({ $hasFiles }) => ($hasFiles ? "default" : "pointer")};
  transition: all 0.2s ease;
  position: relative;
  overflow: hidden;

  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    min-height: 140px;
    padding: var(--oc-spacing-md);
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
    width: 36px;
    height: 36px;
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

// File list container
export const FileListContainer = styled.div`
  border-radius: var(--oc-radius-lg);
  border: 1px solid var(--oc-border-default);
  background: var(--oc-bg-surface);
  max-height: 280px;
  overflow-y: auto;
  padding: var(--oc-spacing-xs);

  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    max-height: 220px;
  }

  /* Custom scrollbar */
  &::-webkit-scrollbar {
    width: 6px;
  }

  &::-webkit-scrollbar-track {
    background: var(--oc-bg-subtle);
    border-radius: 3px;
  }

  &::-webkit-scrollbar-thumb {
    background: var(--oc-border-strong);
    border-radius: 3px;
  }

  &::-webkit-scrollbar-thumb:hover {
    background: var(--oc-fg-tertiary);
  }
`;

// File list item
export const FileItem = styled.div<{
  $selected?: boolean;
  $status?: "pending" | "uploading" | "success" | "failed";
}>`
  padding: var(--oc-spacing-xs) var(--oc-spacing-sm);
  margin: calc(var(--oc-spacing-xs) / 2) 0;
  border-radius: var(--oc-radius-md);
  cursor: pointer;
  transition: all 0.15s ease;
  display: flex;
  align-items: center;
  min-height: 44px;
  border: 1px solid transparent;

  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    padding: var(--oc-spacing-sm);
    min-height: 48px;
  }

  ${({ $selected }) =>
    $selected &&
    css`
      background: ${accentAlpha(0.08)};
      border-color: ${accentAlpha(0.25)};
    `}

  ${({ $status }) =>
    $status === "success" &&
    css`
      background: var(--oc-success-bg);
      border-color: var(--oc-success);
    `}

  ${({ $status }) =>
    $status === "failed" &&
    css`
      background: var(--oc-error-bg);
      border-color: var(--oc-error);
    `}

  &:hover {
    background: ${({ $selected }) =>
      $selected ? accentAlpha(0.12) : "var(--oc-bg-surface-hover)"};
  }
`;

export const FileItemContent = styled.div`
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: var(--oc-spacing-sm);
`;

export const FileItemIcon = styled.div<{
  $status?: "pending" | "uploading" | "success" | "failed";
}>`
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  color: ${({ $status }) =>
    $status === "success"
      ? "var(--oc-success)"
      : $status === "failed"
      ? "var(--oc-error)"
      : "var(--oc-fg-tertiary)"};

  svg {
    width: 18px;
    height: 18px;
  }
`;

export const FileItemDetails = styled.div`
  flex: 1;
  min-width: 0;

  .file-name {
    font-weight: 500;
    color: var(--oc-fg-primary);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    font-size: var(--oc-font-size-sm);

    @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
      font-size: var(--oc-font-size-sm);
    }
  }

  .file-meta {
    font-size: var(--oc-font-size-xs);
    color: var(--oc-fg-tertiary);
    margin-top: calc(var(--oc-spacing-xs) / 2);

    &.error {
      color: var(--oc-error);
    }

    &.success {
      color: var(--oc-success);
    }
  }
`;

export const FileItemActions = styled.div`
  display: flex;
  align-items: center;
  gap: var(--oc-spacing-xs);
  flex-shrink: 0;
`;

// Edit section with two panels
export const EditSection = styled.div`
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--oc-spacing-lg);

  @media (max-width: ${TABLET_BREAKPOINT}px) {
    grid-template-columns: 1fr;
    gap: var(--oc-spacing-md);
  }
`;

export const EditPanel = styled.div`
  display: flex;
  flex-direction: column;
`;

export const EditPanelHeader = styled.h4`
  font-size: var(--oc-font-size-sm);
  font-weight: 500;
  color: var(--oc-fg-secondary);
  margin: 0 0 var(--oc-spacing-sm) 0;
  padding-bottom: var(--oc-spacing-xs);
  border-bottom: 1px solid var(--oc-border-default);
`;

// Step indicator
export const StepIndicatorContainer = styled.div`
  display: flex;
  justify-content: center;
  align-items: center;
  gap: var(--oc-spacing-sm);
  margin-bottom: var(--oc-spacing-md);

  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    gap: var(--oc-spacing-xs);
    margin-bottom: var(--oc-spacing-sm);
  }
`;

export const StepChip = styled.div<{
  $active?: boolean;
  $completed?: boolean;
}>`
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
    padding: var(--oc-spacing-xs) var(--oc-spacing-xs);
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

// Corpus selector card
export const CorpusCard = styled.div<{ $selected?: boolean }>`
  background: var(--oc-bg-surface);
  border-radius: var(--oc-radius-md);
  border: 1px solid
    ${({ $selected }) =>
      $selected ? "var(--oc-accent)" : "var(--oc-border-default)"};
  padding: var(--oc-spacing-sm) var(--oc-spacing-md);
  cursor: pointer;
  transition: all 0.15s ease;
  margin-bottom: var(--oc-spacing-xs);

  ${({ $selected }) =>
    $selected &&
    css`
      background: ${accentAlpha(0.04)};
      box-shadow: 0 0 0 1px ${accentAlpha(0.15)};
    `}

  &:hover {
    border-color: var(--oc-accent);
    background: ${({ $selected }) =>
      $selected ? accentAlpha(0.06) : "var(--oc-bg-subtle)"};
  }

  &:last-child {
    margin-bottom: 0;
  }
`;

export const CorpusCardHeader = styled.div`
  display: flex;
  align-items: center;
  gap: var(--oc-spacing-sm);
  margin-bottom: var(--oc-spacing-xs);
`;

export const CorpusCardIcon = styled.img`
  width: 32px;
  height: 32px;
  object-fit: contain;
  border-radius: var(--oc-radius-sm);
`;

export const CorpusCardTitle = styled.h4`
  font-size: var(--oc-font-size-md);
  font-weight: 600;
  color: var(--oc-fg-primary);
  margin: 0;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
`;

export const CorpusCardDescription = styled.p`
  font-size: var(--oc-font-size-sm);
  color: var(--oc-fg-secondary);
  margin: 0;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
`;

export const CorpusCardMeta = styled.div`
  display: flex;
  align-items: center;
  gap: var(--oc-spacing-md);
  margin-top: var(--oc-spacing-sm);
  font-size: var(--oc-font-size-xs);
  color: var(--oc-fg-tertiary);

  span {
    display: flex;
    align-items: center;
    gap: var(--oc-spacing-xs);
  }

  svg {
    width: 12px;
    height: 12px;
  }
`;

// Error message
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
    }

    .message {
      font-size: var(--oc-font-size-xs);
      color: var(--oc-fg-secondary);
    }
  }
`;

// Loading overlay
export const LoadingOverlay = styled.div<{ $visible: boolean }>`
  position: absolute;
  inset: 0;
  background: rgba(255, 255, 255, 0.85);
  backdrop-filter: blur(2px);
  display: ${(props) => (props.$visible ? "flex" : "none")};
  align-items: center;
  justify-content: center;
  z-index: 100;
  border-radius: var(--oc-radius-lg);
`;

// Empty state placeholder
export const EmptyState = styled.div`
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--oc-spacing-lg);
  text-align: center;
  color: var(--oc-fg-tertiary);

  svg {
    width: 32px;
    height: 32px;
    margin-bottom: var(--oc-spacing-sm);
    opacity: 0.4;
  }

  .title {
    font-size: var(--oc-font-size-sm);
    font-weight: 500;
    color: var(--oc-fg-secondary);
    margin-bottom: calc(var(--oc-spacing-xs) / 2);
  }

  .description {
    font-size: var(--oc-font-size-xs);
  }
`;

// Inline corpus item for bulk mode selector (simpler than CorpusCard)
export const InlineCorpusItem = styled.div<{ $selected?: boolean }>`
  padding: var(--oc-spacing-xs) var(--oc-spacing-sm);
  cursor: pointer;
  border-radius: var(--oc-radius-md);
  background: ${(props) =>
    props.$selected ? accentAlpha(0.08) : "transparent"};
  border: 1px solid
    ${(props) => (props.$selected ? "var(--oc-accent)" : "transparent")};
  margin-bottom: calc(var(--oc-spacing-xs) / 2);
  transition: all 0.15s ease;

  &:hover {
    background: ${(props) =>
      props.$selected ? accentAlpha(0.12) : "var(--oc-bg-subtle)"};
  }

  .corpus-title {
    font-size: var(--oc-font-size-sm);
    font-weight: 500;
    color: var(--oc-fg-primary);
  }
`;

// Container for corpus list with margin
export const CorpusListContainer = styled.div`
  margin-top: var(--oc-spacing-sm);
`;
