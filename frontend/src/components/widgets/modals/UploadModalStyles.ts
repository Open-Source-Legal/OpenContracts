import styled, { css, keyframes } from "styled-components";
import { Modal } from "@os-legal/ui";
import { OS_LEGAL_COLORS } from "../../../assets/configurations/osLegalStyles";

// Breakpoints for responsive design
const breakpoints = {
  mobile: "480px",
  tablet: "768px",
  desktop: "1024px",
};

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
    box-shadow: 0 0 0 0 rgba(33, 133, 208, 0.4);
  }
  70% {
    box-shadow: 0 0 0 10px rgba(33, 133, 208, 0);
  }
  100% {
    box-shadow: 0 0 0 0 rgba(33, 133, 208, 0);
  }
`;

// Styled Modal with responsive sizing - wrapping @os-legal/ui Modal
export const StyledUploadModal = styled(Modal)`
  &.oc-modal {
    animation: ${fadeIn} 0.3s ease-out;
  }

  .oc-modal-content {
    width: 90% !important;
    max-width: 700px !important;
    margin: 1rem auto !important;
    border-radius: 12px !important;
    overflow: hidden;

    @media (max-width: ${breakpoints.mobile}) {
      width: 95% !important;
      margin: 0.5rem auto !important;
      max-height: 95vh;
    }

    @media (max-width: ${breakpoints.tablet}) {
      width: 95% !important;
    }
  }

  .oc-modal-header {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    color: white !important;
    padding: 1.25rem 1.5rem !important;
    font-size: 1.25rem !important;
    border-bottom: none !important;

    @media (max-width: ${breakpoints.mobile}) {
      padding: 1rem !important;
      font-size: 1.1rem !important;
    }
  }

  .oc-modal-body {
    padding: 1.5rem !important;

    @media (max-width: ${breakpoints.mobile}) {
      padding: 1rem !important;
    }
  }

  .oc-modal-footer {
    padding: 1rem 1.5rem !important;
    padding-top: var(--oc-spacing-lg) !important;
    background: #f8f9fa !important;
    border-top: 1px solid ${OS_LEGAL_COLORS.gray200} !important;
    display: flex;
    justify-content: flex-end;
    gap: 0.5rem;

    @media (max-width: ${breakpoints.mobile}) {
      padding: 0.75rem 1rem !important;
      display: flex;
      flex-direction: column;
      gap: 0.5rem;

      button {
        width: 100% !important;
        margin: 0 !important;
      }
    }
  }
`;

// Modal header with icon
export const ModalHeader = styled.div`
  display: flex;
  align-items: center;
  gap: 0.75rem;

  svg {
    font-size: 1.5rem;

    @media (max-width: ${breakpoints.mobile}) {
      font-size: 1.25rem;
    }
  }
`;

export const ModalHeaderContent = styled.div`
  display: flex;
  flex-direction: column;

  .title {
    font-weight: 600;
    font-size: 1.25rem;
    margin-bottom: 0.25rem;

    @media (max-width: ${breakpoints.mobile}) {
      font-size: 1.1rem;
    }
  }

  .subtitle {
    font-size: 0.875rem;
    opacity: 0.9;
    font-weight: 400;

    @media (max-width: ${breakpoints.mobile}) {
      font-size: 0.8rem;
    }
  }
`;

// Step indicator for multi-step upload
export const StepIndicator = styled.div`
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 1.5rem;
  padding: 0 1rem;

  @media (max-width: ${breakpoints.mobile}) {
    gap: 0.25rem;
    margin-bottom: 1rem;
  }
`;

export const Step = styled.div<{ $active?: boolean; $completed?: boolean }>`
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 1rem;
  border-radius: 20px;
  font-size: 0.875rem;
  font-weight: 500;
  transition: all 0.2s ease;

  @media (max-width: ${breakpoints.mobile}) {
    padding: 0.375rem 0.75rem;
    font-size: 0.75rem;
    gap: 0.25rem;
  }

  ${({ $active, $completed }) =>
    $active
      ? css`
          background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
          color: white;
        `
      : $completed
      ? css`
          background: #e8f5e9;
          color: #2e7d32;
        `
      : css`
          background: #f1f3f5;
          color: ${OS_LEGAL_COLORS.gray500};
        `}
`;

export const StepConnector = styled.div<{ $completed?: boolean }>`
  width: 30px;
  height: 2px;
  background: ${({ $completed }) => ($completed ? "#2e7d32" : "#dee2e6")};
  transition: background 0.2s ease;

  @media (max-width: ${breakpoints.mobile}) {
    width: 15px;
  }
`;

// Drag and drop zone
export const DropZone = styled.div<{
  $isDragActive?: boolean;
  $hasFiles?: boolean;
}>`
  border: 2px dashed
    ${({ $isDragActive }) => ($isDragActive ? "#667eea" : "#dee2e6")};
  border-radius: 12px;
  background: ${({ $isDragActive }) =>
    $isDragActive
      ? "linear-gradient(135deg, rgba(102, 126, 234, 0.1) 0%, rgba(118, 75, 162, 0.1) 100%)"
      : OS_LEGAL_COLORS.surfaceHover};
  min-height: 250px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 2rem;
  cursor: ${({ $hasFiles }) => ($hasFiles ? "default" : "pointer")};
  transition: all 0.2s ease;
  position: relative;
  overflow: hidden;

  @media (max-width: ${breakpoints.mobile}) {
    min-height: 200px;
    padding: 1.5rem 1rem;
  }

  &:hover {
    border-color: ${({ $hasFiles }) => ($hasFiles ? "#dee2e6" : "#667eea")};
    background: ${({ $hasFiles }) =>
      $hasFiles
        ? "#fafbfc"
        : "linear-gradient(135deg, rgba(102, 126, 234, 0.05) 0%, rgba(118, 75, 162, 0.05) 100%)"};
  }

  ${({ $isDragActive }) =>
    $isDragActive &&
    css`
      animation: ${pulse} 1.5s infinite;
    `}
`;

export const DropZoneIcon = styled.div`
  font-size: 3rem;
  color: #667eea;
  margin-bottom: 1rem;
  opacity: 0.8;

  @media (max-width: ${breakpoints.mobile}) {
    font-size: 2.5rem;
    margin-bottom: 0.75rem;
  }
`;

export const DropZoneText = styled.div`
  text-align: center;

  .primary-text {
    font-size: 1.1rem;
    font-weight: 500;
    color: ${OS_LEGAL_COLORS.gray700};
    margin-bottom: 0.5rem;

    @media (max-width: ${breakpoints.mobile}) {
      font-size: 1rem;
    }
  }

  .secondary-text {
    font-size: 0.875rem;
    color: ${OS_LEGAL_COLORS.gray500};

    @media (max-width: ${breakpoints.mobile}) {
      font-size: 0.8rem;
    }
  }
`;

export const DropZoneButton = styled.button`
  margin-top: 1rem;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important;
  color: white !important;
  border-radius: 8px !important;
  padding: 0.875rem 1.5rem !important;
  font-weight: 500 !important;
  transition: all 0.2s ease !important;
  min-height: 44px; /* Touch target size */
  border: none;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;

  @media (max-width: ${breakpoints.mobile}) {
    width: 100%;
    padding: 1rem !important;
  }

  &:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
  }

  &:active {
    transform: translateY(0);
  }
`;

// File list container
export const FileListContainer = styled.div`
  border-radius: 12px;
  border: 1px solid ${OS_LEGAL_COLORS.gray200};
  max-height: 300px;
  overflow-y: auto;
  padding: 0.5rem;
  margin: 0;

  @media (max-width: ${breakpoints.mobile}) {
    max-height: 250px;
  }

  /* Custom scrollbar */
  &::-webkit-scrollbar {
    width: 6px;
  }

  &::-webkit-scrollbar-track {
    background: #f1f3f5;
    border-radius: 3px;
  }

  &::-webkit-scrollbar-thumb {
    background: #ced4da;
    border-radius: 3px;
  }

  &::-webkit-scrollbar-thumb:hover {
    background: #adb5bd;
  }
`;

// File list item
export const FileListItem = styled.li<{
  $selected?: boolean;
  $status?: string;
}>`
  list-style: none;
  padding: 0.875rem 1rem;
  margin: 0.25rem 0;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.15s ease;
  position: relative;
  display: flex;
  align-items: center;
  min-height: 56px; /* Touch target size */

  @media (max-width: ${breakpoints.mobile}) {
    padding: 1rem;
    min-height: 64px;
  }

  ${({ $selected }) =>
    $selected &&
    css`
      background: linear-gradient(
        135deg,
        rgba(102, 126, 234, 0.1) 0%,
        rgba(118, 75, 162, 0.1) 100%
      );
      border: 1px solid rgba(102, 126, 234, 0.3);
    `}

  ${({ $status }) =>
    $status === "SUCCESS" &&
    css`
      background: #e8f5e9;
      border: 1px solid #c8e6c9;
    `}

  ${({ $status }) =>
    $status === "FAILED" &&
    css`
      background: #ffebee;
      border: 1px solid ${OS_LEGAL_COLORS.dangerBorder};
    `}

  &:hover {
    background: ${({ $selected }) =>
      $selected ? "rgba(102, 126, 234, 0.15)" : OS_LEGAL_COLORS.gray50};
  }
`;

export const FileItemContent = styled.div`
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 0.75rem;
`;

export const FileItemIcon = styled.div<{ $status?: string }>`
  font-size: 1.5rem;
  color: ${({ $status }) =>
    $status === "SUCCESS"
      ? "#2e7d32"
      : $status === "FAILED"
      ? OS_LEGAL_COLORS.dangerText
      : "#667eea"};
  flex-shrink: 0;
`;

export const FileItemDetails = styled.div`
  flex: 1;
  min-width: 0;

  .file-name {
    font-weight: 500;
    color: #212529;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;

    @media (max-width: ${breakpoints.mobile}) {
      font-size: 0.9rem;
    }
  }

  .file-status {
    font-size: 0.75rem;
    color: ${OS_LEGAL_COLORS.gray500};
    margin-top: 0.25rem;

    &.error {
      color: #c62828;
    }

    &.success {
      color: #2e7d32;
    }
  }
`;

export const FileItemActions = styled.div`
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-shrink: 0;
`;

export const DeleteButton = styled.button`
  padding: 0.5rem !important;
  margin: 0 !important;
  background: transparent !important;
  color: ${OS_LEGAL_COLORS.gray500} !important;
  border-radius: 6px !important;
  min-width: 36px;
  min-height: 36px;
  display: flex !important;
  align-items: center;
  justify-content: center;
  border: none;
  cursor: pointer;

  @media (max-width: ${breakpoints.mobile}) {
    min-width: 44px;
    min-height: 44px;
  }

  &:hover {
    background: #ffebee !important;
    color: #c62828 !important;
  }
`;

// Form edit section (two-column on desktop)
export const EditSection = styled.div`
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1.5rem;

  @media (max-width: ${breakpoints.tablet}) {
    grid-template-columns: 1fr;
    gap: 1rem;
  }
`;

export const EditPanel = styled.div`
  display: flex;
  flex-direction: column;
`;

export const EditPanelHeader = styled.h4`
  font-size: 1rem;
  font-weight: 600;
  color: ${OS_LEGAL_COLORS.gray700};
  margin-bottom: 1rem;
  padding-bottom: 0.5rem;
  border-bottom: 2px solid #667eea;
`;

export const FormContainer = styled.div`
  border-radius: 12px;
  border: 1px solid ${OS_LEGAL_COLORS.gray200};
  padding: 1.5rem;
  height: 100%;
  background: #fff;

  @media (max-width: ${breakpoints.mobile}) {
    padding: 1rem;
  }
`;

// Progress indicator
export const UploadProgress = styled.div<{ $percent?: number }>`
  margin: 1rem 0;
  border-radius: 8px;
  overflow: hidden;
  background: ${OS_LEGAL_COLORS.gray200};
  height: 20px;
  position: relative;

  &::before {
    content: "${({ $percent }) => Math.round($percent ?? 0)}%";
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 0.75rem;
    font-weight: 600;
    color: ${({ $percent }) =>
      ($percent ?? 0) > 50 ? "#fff" : OS_LEGAL_COLORS.textTertiary};
    z-index: 1;
    line-height: 20px;
  }

  &::after {
    content: "";
    display: block;
    height: 100%;
    width: ${({ $percent }) => $percent ?? 0}%;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    border-radius: 8px;
    transition: width 0.3s ease;
  }
`;

// Action buttons
export const ActionButton = styled.button<{
  $variant?: "primary" | "secondary" | "danger";
}>`
  border-radius: 8px !important;
  font-weight: 500 !important;
  min-height: 44px;
  padding: 0.875rem 1.5rem !important;
  transition: all 0.2s ease !important;
  border: none;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;

  @media (max-width: ${breakpoints.mobile}) {
    width: 100%;
    padding: 1rem !important;
  }

  ${({ $variant }) =>
    $variant === "primary" &&
    css`
      background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important;
      color: white !important;

      &:hover:not(:disabled) {
        transform: translateY(-1px);
        box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
      }
    `}

  ${({ $variant }) =>
    $variant === "secondary" &&
    css`
      background: #f1f3f5 !important;
      color: ${OS_LEGAL_COLORS.gray700} !important;

      &:hover:not(:disabled) {
        background: ${OS_LEGAL_COLORS.gray200} !important;
      }
    `}

  ${({ $variant }) =>
    $variant === "danger" &&
    css`
      background: #ffebee !important;
      color: #c62828 !important;

      &:hover:not(:disabled) {
        background: #ffcdd2 !important;
      }
    `}

  &:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }
`;

export const FieldLabel = styled.label`
  display: block;
  font-weight: 500;
  color: ${OS_LEGAL_COLORS.gray700};
  margin-bottom: 0.5rem;
  font-size: 0.9375rem;

  .required {
    color: #e03131;
    margin-left: 0.25rem;
  }
`;

// Error message styling
export const ErrorMessage = styled.div`
  background: #ffebee;
  border: 1px solid ${OS_LEGAL_COLORS.dangerBorder};
  border-radius: 8px;
  padding: 1rem;
  margin-bottom: 1rem;
  display: flex;
  align-items: flex-start;
  gap: 0.75rem;

  .icon {
    color: #c62828;
    flex-shrink: 0;
  }

  .content {
    flex: 1;

    .header {
      font-weight: 600;
      color: #c62828;
      margin-bottom: 0.25rem;
    }

    .message {
      font-size: 0.875rem;
      color: #6e0000;
    }
  }
`;

// Mobile-specific action bar
export const MobileActionBar = styled.div`
  display: none;

  @media (max-width: ${breakpoints.mobile}) {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    padding: 1rem;
    background: #f8f9fa;
    border-top: 1px solid ${OS_LEGAL_COLORS.gray200};
  }
`;
