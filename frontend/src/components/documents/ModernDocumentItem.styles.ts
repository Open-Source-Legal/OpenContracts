import styled, { keyframes } from "styled-components";
import { FAILURE_COLORS } from "../../assets/configurations/constants";
import { OS_LEGAL_COLORS } from "../../assets/configurations/osLegalStyles";

const spin = keyframes`
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
`;

// ===============================================
// CARD VIEW (Desktop)
// ===============================================
export const CardContainer = styled.div<{ isLongPressing?: boolean }>`
  position: relative;
  background: white;
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 8px;
  overflow: visible;
  transition: all 0.2s ease;
  cursor: pointer;
  height: 200px;
  display: flex;
  flex-direction: column;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);

  &:hover {
    border-color: ${OS_LEGAL_COLORS.borderHover};
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
    transform: translateY(-2px);

    .action-overlay {
      opacity: 1;
    }
  }

  &.is-selected {
    border-color: ${OS_LEGAL_COLORS.primaryBlue};
    box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.2);
  }

  &.backend-locked {
    pointer-events: none;
    opacity: 0.6;
  }

  &.failed {
    border-color: ${FAILURE_COLORS.BORDER_LIGHT};
  }

  &.long-pressing {
    transform: scale(0.98);
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.12);
    border-color: ${OS_LEGAL_COLORS.textMuted};
  }
`;

export const CardPreview = styled.div`
  position: relative;
  height: 90px;
  background: ${OS_LEGAL_COLORS.surfaceHover};
  overflow: hidden;
  border-radius: 7px 7px 0 0;

  img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }

  .fallback-icon {
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    width: 32px;
    height: 32px;
    opacity: 0.15;
  }
`;

export const CardContent = styled.div`
  flex: 1;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-height: 0;
  overflow: visible;
`;

export const CardTitle = styled.div`
  font-size: 0.875rem;
  font-weight: 600;
  color: ${OS_LEGAL_COLORS.textPrimary};
  line-height: 1.3;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
`;

export const CardMeta = styled.div`
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.75rem;
  color: ${OS_LEGAL_COLORS.textSecondary};
  margin-top: auto;
  overflow: visible;

  .meta-item {
    display: flex;
    align-items: center;
    gap: 3px;
  }
`;

export const ActionOverlay = styled.div`
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  padding: 8px;
  background: linear-gradient(to top, rgba(0, 0, 0, 0.7), transparent);
  display: flex;
  gap: 4px;
  justify-content: flex-end;
  opacity: 0;
  transition: opacity 0.2s ease;
`;

export const CardCheckbox = styled.div`
  position: absolute;
  top: 8px;
  left: 8px;
  width: 20px;
  height: 20px;
  border-radius: 4px;
  background: white;
  border: 2px solid ${OS_LEGAL_COLORS.borderHover};
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  z-index: 10;
  transition: all 0.15s ease;

  &:hover {
    border-color: ${OS_LEGAL_COLORS.primaryBlue};
  }

  &.selected {
    background: ${OS_LEGAL_COLORS.primaryBlue};
    border-color: ${OS_LEGAL_COLORS.primaryBlue};

    .icon {
      color: white;
      font-size: 0.7rem;
    }
  }
`;

export const FileTypeBadge = styled.div`
  position: absolute;
  top: 8px;
  right: 8px;
  padding: 2px 6px;
  background: rgba(15, 23, 42, 0.8);
  backdrop-filter: blur(4px);
  color: white;
  border-radius: 3px;
  font-size: 0.625rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
`;

// Positioned version badge that doesn't conflict with FileTypeBadge
export const VersionBadgeWrapper = styled.div`
  position: absolute;
  top: 8px;
  left: 32px; /* After the checkbox */

  /* Override the internal absolute positioning */
  > div {
    position: relative !important;
    top: auto !important;
    right: auto !important;
  }
`;

// Relationship badge positioned at bottom-right of card preview
export const RelationshipBadgeContainer = styled.div`
  position: absolute;
  bottom: 8px;
  right: 8px;
  z-index: 5;
`;

export const RelationshipBadge = styled.div`
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  background: linear-gradient(135deg, #14b8a6 0%, #0d9488 100%);
  backdrop-filter: blur(4px);
  color: white;
  border-radius: 6px;
  font-size: 0.875rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s ease;
  box-shadow: 0 2px 8px rgba(20, 184, 166, 0.3);

  svg {
    width: 16px;
    height: 16px;
  }

  &:hover {
    background: linear-gradient(
      135deg,
      #0d9488 0%,
      ${OS_LEGAL_COLORS.accent} 100%
    );
    transform: scale(1.05);
    box-shadow: 0 4px 12px rgba(20, 184, 166, 0.4);
  }
`;

export const RelationshipPopup = styled.div`
  position: absolute;
  bottom: calc(100% + 12px);
  right: 0;
  min-width: 280px;
  max-width: 320px;
  background: white;
  border-radius: 12px;
  box-shadow: 0 8px 30px rgba(0, 0, 0, 0.2);
  padding: 0;
  z-index: 1000;
  opacity: 0;
  visibility: hidden;
  transform: translateY(8px);
  transition: all 0.2s ease;
  overflow: hidden;

  ${RelationshipBadgeContainer}:hover & {
    opacity: 1;
    visibility: visible;
    transform: translateY(0);
  }

  &::after {
    content: "";
    position: absolute;
    bottom: -6px;
    right: 16px;
    width: 12px;
    height: 12px;
    background: white;
    transform: rotate(45deg);
    box-shadow: 2px 2px 4px rgba(0, 0, 0, 0.05);
  }
`;

export const PopupHeader = styled.div`
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 16px;
  background: linear-gradient(135deg, #14b8a6 0%, #0d9488 100%);
  color: white;

  svg {
    width: 20px;
    height: 20px;
  }

  span {
    font-size: 0.9375rem;
    font-weight: 600;
  }
`;

export const PopupContent = styled.div`
  padding: 12px 16px;
  max-height: 240px;
  overflow-y: auto;

  &::-webkit-scrollbar {
    width: 6px;
  }
  &::-webkit-scrollbar-track {
    background: ${OS_LEGAL_COLORS.surfaceLight};
  }
  &::-webkit-scrollbar-thumb {
    background: ${OS_LEGAL_COLORS.borderHover};
    border-radius: 3px;
  }
`;

export const RelationshipItem = styled.div`
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 10px 0;
  border-bottom: 1px solid ${OS_LEGAL_COLORS.surfaceLight};

  &:last-child {
    border-bottom: none;
    padding-bottom: 0;
  }

  &:first-child {
    padding-top: 0;
  }
`;

export const RelationshipIcon = styled.div<{ $color?: string }>`
  width: 28px;
  height: 28px;
  border-radius: 6px;
  background: ${(props) => props.$color || OS_LEGAL_COLORS.surfaceLight};
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;

  svg {
    width: 14px;
    height: 14px;
    color: ${(props) =>
      props.$color ? "white" : OS_LEGAL_COLORS.textSecondary};
  }
`;

export const RelationshipDetails = styled.div`
  flex: 1;
  min-width: 0;
`;

export const RelationshipLabel = styled.div<{ $color?: string }>`
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  background: ${(props) =>
    props.$color ? `${props.$color}20` : OS_LEGAL_COLORS.surfaceLight};
  color: ${(props) => props.$color || OS_LEGAL_COLORS.textSecondary};
  border-radius: 4px;
  font-size: 0.6875rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.02em;
  margin-bottom: 4px;
`;

export const LinkedDocTitle = styled.div`
  font-size: 0.8125rem;
  font-weight: 500;
  color: ${OS_LEGAL_COLORS.textPrimary};
  line-height: 1.3;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
`;

export const RelationshipDirection = styled.div`
  font-size: 0.6875rem;
  color: ${OS_LEGAL_COLORS.textMuted};
  margin-top: 2px;
`;

// List view relationship badge (inline in meta)
export const ListRelationshipBadge = styled.div`
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  background: linear-gradient(135deg, #14b8a6 0%, #0d9488 100%);
  color: white;
  border-radius: 4px;
  font-size: 0.75rem;
  font-weight: 600;
  cursor: pointer;

  svg {
    width: 12px;
    height: 12px;
  }

  &:hover {
    background: linear-gradient(
      135deg,
      #0d9488 0%,
      ${OS_LEGAL_COLORS.accent} 100%
    );
  }
`;

export const ListRelationshipPopup = styled.div`
  position: absolute;
  bottom: calc(100% + 8px);
  left: 50%;
  transform: translateX(-50%);
  min-width: 280px;
  max-width: 320px;
  background: white;
  border-radius: 12px;
  box-shadow: 0 8px 30px rgba(0, 0, 0, 0.2);
  padding: 0;
  z-index: 1000;
  opacity: 0;
  visibility: hidden;
  transition: all 0.2s ease;
  overflow: hidden;

  ${ListRelationshipBadge}:hover & {
    opacity: 1;
    visibility: visible;
  }

  &::after {
    content: "";
    position: absolute;
    bottom: -6px;
    left: 50%;
    transform: translateX(-50%) rotate(45deg);
    width: 12px;
    height: 12px;
    background: white;
    box-shadow: 2px 2px 4px rgba(0, 0, 0, 0.05);
  }
`;

// Delete button that floats above the processing dimmer
export const ProcessingDeleteButton = styled.button`
  position: absolute;
  top: 6px;
  right: 6px;
  z-index: 1001; /* Above ProcessingDimmer (1000) and ListRelationshipPopup (1000) */
  pointer-events: auto;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  border: none;
  background: rgba(0, 0, 0, 0.5);
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  opacity: 0.6;
  transition: all 0.15s ease;
  padding: 0;

  svg {
    width: 14px;
    height: 14px;
  }

  &:hover {
    opacity: 1;
    background: ${FAILURE_COLORS.BORDER};
    transform: scale(1.1);
  }
`;

// ===============================================
// LIST VIEW (Mobile)
// ===============================================
export const ListContainer = styled.div<{ isLongPressing?: boolean }>`
  position: relative;
  background: white;
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 8px;
  padding: 12px;
  display: flex;
  gap: 12px;
  align-items: center;
  cursor: pointer;
  transition: all 0.2s ease;
  min-height: 80px;
  overflow: visible;

  &:hover {
    border-color: ${OS_LEGAL_COLORS.borderHover};
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
  }

  &.is-selected {
    border-color: ${OS_LEGAL_COLORS.primaryBlue};
    background: ${OS_LEGAL_COLORS.blueSurface};
  }

  &.backend-locked {
    pointer-events: none;
    opacity: 0.6;
  }

  &.failed {
    border-left: 3px solid ${FAILURE_COLORS.BORDER};
    background: ${FAILURE_COLORS.BG};

    &:hover {
      border-left: 3px solid ${FAILURE_COLORS.BORDER};
      background: ${FAILURE_COLORS.BG};
    }
  }

  &.long-pressing {
    transform: scale(0.99);
    box-shadow: 0 1px 4px rgba(0, 0, 0, 0.1);
    border-color: ${OS_LEGAL_COLORS.textMuted};
    background: ${OS_LEGAL_COLORS.surfaceHover};
  }
`;

export const ListThumbnail = styled.div`
  position: relative;
  width: 56px;
  height: 56px;
  flex-shrink: 0;
  border-radius: 6px;
  overflow: hidden;
  background: ${OS_LEGAL_COLORS.surfaceHover};
  border: 1px solid ${OS_LEGAL_COLORS.border};

  img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }

  .fallback-icon {
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    width: 24px;
    height: 24px;
    opacity: 0.2;
  }
`;

export const ListContent = styled.div`
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
  overflow: visible;
`;

export const ListTitle = styled.div`
  font-size: 0.875rem;
  font-weight: 600;
  color: ${OS_LEGAL_COLORS.textPrimary};
  line-height: 1.3;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
`;

export const ListDescription = styled.div`
  font-size: 0.75rem;
  color: ${OS_LEGAL_COLORS.textSecondary};
  line-height: 1.3;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
`;

export const ListMeta = styled.div`
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.7rem;
  color: ${OS_LEGAL_COLORS.textMuted};
  overflow: visible;
  position: relative;

  .meta-item {
    display: flex;
    align-items: center;
    gap: 3px;
  }
`;

export const ListActions = styled.div`
  display: flex;
  gap: 4px;
  flex-shrink: 0;
`;

export const ListCheckbox = styled.div`
  width: 20px;
  height: 20px;
  flex-shrink: 0;
  border-radius: 4px;
  background: white;
  border: 2px solid ${OS_LEGAL_COLORS.borderHover};
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.15s ease;

  &:hover {
    border-color: ${OS_LEGAL_COLORS.primaryBlue};
  }

  &.selected {
    background: ${OS_LEGAL_COLORS.primaryBlue};
    border-color: ${OS_LEGAL_COLORS.primaryBlue};

    .icon {
      color: white;
      font-size: 0.7rem;
    }
  }
`;

// ===============================================
// PROCESSING FAILURE COMPONENTS
// ===============================================
export const ThumbnailFailureOverlay = styled.div`
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: ${FAILURE_COLORS.BG_OVERLAY};
  z-index: 5;
  border-radius: inherit;
`;

export const FailureIconCircle = styled.div<{ $size?: "small" | "large" }>`
  width: ${(props) => (props.$size === "small" ? "28px" : "40px")};
  height: ${(props) => (props.$size === "small" ? "28px" : "40px")};
  border-radius: 50%;
  background: ${FAILURE_COLORS.ICON_BG};
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  box-shadow: 0 2px 8px ${FAILURE_COLORS.SHADOW};

  .icon {
    margin: 0 !important;
    font-size: ${(props) => (props.$size === "small" ? "12px" : "18px")};
  }
`;

export const FailureBadge = styled.div`
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  background: ${FAILURE_COLORS.BG};
  color: ${FAILURE_COLORS.TEXT};
  border: 1px solid ${FAILURE_COLORS.BORDER_LIGHTER};
  border-radius: 4px;
  font-size: 0.6875rem;
  font-weight: 600;
  letter-spacing: 0.02em;
`;

export const FailureDescription = styled.div`
  font-size: 0.75rem;
  color: ${FAILURE_COLORS.TEXT_DARK};
  line-height: 1.3;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
`;

export const RetryButton = styled.button`
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 16px;
  border: 1px solid ${FAILURE_COLORS.BORDER};
  border-radius: 6px;
  background: white;
  color: ${FAILURE_COLORS.TEXT};
  font-size: 0.75rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s ease;
  white-space: nowrap;

  svg {
    width: 14px;
    height: 14px;
  }

  &:hover {
    background: ${FAILURE_COLORS.BORDER};
    color: white;
  }

  &:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
`;

// ===============================================
// SHARED COMPONENTS
// ===============================================
export const ActionButton = styled.button`
  width: 28px;
  height: 28px;
  border-radius: 4px;
  border: none;
  background: rgba(255, 255, 255, 0.9);
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.15s ease;
  color: ${OS_LEGAL_COLORS.textSecondary};

  &:hover {
    background: white;
    color: ${OS_LEGAL_COLORS.textPrimary};
    transform: scale(1.05);
  }

  &:active {
    transform: scale(0.95);
  }

  &.primary {
    background: ${OS_LEGAL_COLORS.primaryBlue};
    color: white;

    &:hover {
      background: ${OS_LEGAL_COLORS.primaryBlueHover};
    }
  }

  &:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .icon {
    margin: 0 !important;
    font-size: 12px;

    &.loading {
      animation: ${spin} 1s linear infinite;
    }
  }
`;
