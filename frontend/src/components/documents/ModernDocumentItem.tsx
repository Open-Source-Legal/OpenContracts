import React, { useState, useRef, useEffect, useCallback } from "react";
import { Icon } from "semantic-ui-react";
import styled, { keyframes } from "styled-components";
import { useNavigate } from "react-router-dom";
import { useDraggable, useDroppable } from "@dnd-kit/core";
import { CSS } from "@dnd-kit/utilities";
import { Link2, ArrowRight, FileText, RotateCcw } from "lucide-react";
import { useMutation } from "@apollo/client";
import { toast } from "react-toastify";
import { navigateToDocument } from "../../utils/navigationUtils";
import { LoadingOverlay } from "../common/LoadingOverlay";
import { X } from "lucide-react";
import { FAILURE_COLORS } from "../../assets/configurations/constants";

import {
  editingDocument,
  viewingDocument,
  openedCorpus,
} from "../../graphql/cache";
import {
  AnnotationLabelType,
  DocumentType,
  DocumentProcessingStatus,
} from "../../types/graphql-api";
import {
  RETRY_DOCUMENT_PROCESSING,
  RetryDocumentProcessingOutputType,
  RetryDocumentProcessingInputType,
} from "../../graphql/mutations";
import { downloadFile } from "../../utils/files";
import fallback_doc_icon from "../../assets/images/defaults/default_doc_icon.jpg";
import { getPermissions } from "../../utils/transform";
import { PermissionTypes } from "../types";
import { ModernContextMenu, ContextMenuItem } from "./ModernContextMenu";
import { VersionBadge } from "./VersionBadge";
import { VersionHistoryPanel } from "./VersionHistoryPanel";

const spin = keyframes`
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
`;

// ===============================================
// CARD VIEW (Desktop)
// ===============================================
const CardContainer = styled.div<{ isLongPressing?: boolean }>`
  position: relative;
  background: white;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  overflow: visible;
  transition: all 0.2s ease;
  cursor: pointer;
  height: 200px;
  display: flex;
  flex-direction: column;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);

  &:hover {
    border-color: #cbd5e1;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
    transform: translateY(-2px);

    .action-overlay {
      opacity: 1;
    }
  }

  &.is-selected {
    border-color: #3b82f6;
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
    border-color: #94a3b8;
  }
`;

const CardPreview = styled.div`
  position: relative;
  height: 90px;
  background: #f8fafc;
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

const CardContent = styled.div`
  flex: 1;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-height: 0;
  overflow: visible;
`;

const CardTitle = styled.div`
  font-size: 0.875rem;
  font-weight: 600;
  color: #0f172a;
  line-height: 1.3;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
`;

const CardMeta = styled.div`
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.75rem;
  color: #64748b;
  margin-top: auto;
  overflow: visible;

  .meta-item {
    display: flex;
    align-items: center;
    gap: 3px;
  }
`;

const ActionOverlay = styled.div`
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

const CardCheckbox = styled.div`
  position: absolute;
  top: 8px;
  left: 8px;
  width: 20px;
  height: 20px;
  border-radius: 4px;
  background: white;
  border: 2px solid #cbd5e1;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  z-index: 10;
  transition: all 0.15s ease;

  &:hover {
    border-color: #3b82f6;
  }

  &.selected {
    background: #3b82f6;
    border-color: #3b82f6;

    .icon {
      color: white;
      font-size: 0.7rem;
    }
  }
`;

const FileTypeBadge = styled.div`
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
const VersionBadgeWrapper = styled.div`
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
const RelationshipBadgeContainer = styled.div`
  position: absolute;
  bottom: 8px;
  right: 8px;
  z-index: 5;
`;

const RelationshipBadge = styled.div`
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
    background: linear-gradient(135deg, #0d9488 0%, #0f766e 100%);
    transform: scale(1.05);
    box-shadow: 0 4px 12px rgba(20, 184, 166, 0.4);
  }
`;

const RelationshipPopup = styled.div`
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

const PopupHeader = styled.div`
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

const PopupContent = styled.div`
  padding: 12px 16px;
  max-height: 240px;
  overflow-y: auto;

  &::-webkit-scrollbar {
    width: 6px;
  }
  &::-webkit-scrollbar-track {
    background: #f1f5f9;
  }
  &::-webkit-scrollbar-thumb {
    background: #cbd5e1;
    border-radius: 3px;
  }
`;

const RelationshipItem = styled.div`
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 10px 0;
  border-bottom: 1px solid #f1f5f9;

  &:last-child {
    border-bottom: none;
    padding-bottom: 0;
  }

  &:first-child {
    padding-top: 0;
  }
`;

const RelationshipIcon = styled.div<{ $color?: string }>`
  width: 28px;
  height: 28px;
  border-radius: 6px;
  background: ${(props) => props.$color || "#f1f5f9"};
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;

  svg {
    width: 14px;
    height: 14px;
    color: ${(props) => (props.$color ? "white" : "#64748b")};
  }
`;

const RelationshipDetails = styled.div`
  flex: 1;
  min-width: 0;
`;

const RelationshipLabel = styled.div<{ $color?: string }>`
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  background: ${(props) => (props.$color ? `${props.$color}20` : "#f1f5f9")};
  color: ${(props) => props.$color || "#64748b"};
  border-radius: 4px;
  font-size: 0.6875rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.02em;
  margin-bottom: 4px;
`;

const LinkedDocTitle = styled.div`
  font-size: 0.8125rem;
  font-weight: 500;
  color: #0f172a;
  line-height: 1.3;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
`;

const RelationshipDirection = styled.div`
  font-size: 0.6875rem;
  color: #94a3b8;
  margin-top: 2px;
`;

// List view relationship badge (inline in meta)
const ListRelationshipBadge = styled.div`
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
    background: linear-gradient(135deg, #0d9488 0%, #0f766e 100%);
  }
`;

const ListRelationshipPopup = styled.div`
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
const ProcessingDeleteButton = styled.button`
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
const ListContainer = styled.div<{ isLongPressing?: boolean }>`
  position: relative;
  background: white;
  border: 1px solid #e2e8f0;
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
    border-color: #cbd5e1;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
  }

  &.is-selected {
    border-color: #3b82f6;
    background: #eff6ff;
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
    border-color: #94a3b8;
    background: #f8fafc;
  }
`;

const ListThumbnail = styled.div`
  position: relative;
  width: 56px;
  height: 56px;
  flex-shrink: 0;
  border-radius: 6px;
  overflow: hidden;
  background: #f8fafc;
  border: 1px solid #e2e8f0;

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

const ListContent = styled.div`
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
  overflow: visible;
`;

const ListTitle = styled.div`
  font-size: 0.875rem;
  font-weight: 600;
  color: #0f172a;
  line-height: 1.3;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
`;

const ListDescription = styled.div`
  font-size: 0.75rem;
  color: #64748b;
  line-height: 1.3;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
`;

const ListMeta = styled.div`
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.7rem;
  color: #94a3b8;
  overflow: visible;
  position: relative;

  .meta-item {
    display: flex;
    align-items: center;
    gap: 3px;
  }
`;

const ListActions = styled.div`
  display: flex;
  gap: 4px;
  flex-shrink: 0;
`;

const ListCheckbox = styled.div`
  width: 20px;
  height: 20px;
  flex-shrink: 0;
  border-radius: 4px;
  background: white;
  border: 2px solid #cbd5e1;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.15s ease;

  &:hover {
    border-color: #3b82f6;
  }

  &.selected {
    background: #3b82f6;
    border-color: #3b82f6;

    .icon {
      color: white;
      font-size: 0.7rem;
    }
  }
`;

// ===============================================
// PROCESSING FAILURE COMPONENTS
// ===============================================
const ThumbnailFailureOverlay = styled.div`
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: ${FAILURE_COLORS.BG_OVERLAY};
  z-index: 5;
  border-radius: inherit;
`;

const FailureIconCircle = styled.div<{ $size?: "small" | "large" }>`
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

const FailureBadge = styled.div`
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

const FailureDescription = styled.div`
  font-size: 0.75rem;
  color: ${FAILURE_COLORS.TEXT_DARK};
  line-height: 1.3;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
`;

const RetryButton = styled.button`
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
const ActionButton = styled.button`
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
  color: #64748b;

  &:hover {
    background: white;
    color: #0f172a;
    transform: scale(1.05);
  }

  &:active {
    transform: scale(0.95);
  }

  &.primary {
    background: #3b82f6;
    color: white;

    &:hover {
      background: #2563eb;
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

interface ModernDocumentItemProps {
  item: DocumentType;
  viewMode: "card" | "list";
  onShiftClick?: (document: DocumentType) => void;
  onClick?: (document: DocumentType) => void;
  removeFromCorpus?: (doc_ids: string[]) => void;
  /** Callback when user wants to link this document to another */
  onLinkToDocument?: (document: DocumentType) => void;
  /** Callback when a document is dropped onto this document (for creating relationships) */
  onDocumentDrop?: (sourceDocId: string, targetDocId: string) => void;
}

export const ModernDocumentItem: React.FC<ModernDocumentItemProps> = ({
  item,
  viewMode,
  onShiftClick,
  onClick,
  removeFromCorpus,
  onLinkToDocument,
  onDocumentDrop,
}) => {
  const navigate = useNavigate();
  const [isDownloading, setIsDownloading] = useState(false);
  const [contextMenu, setContextMenu] = useState<{
    x: number;
    y: number;
  } | null>(null);
  const [isLongPressing, setIsLongPressing] = useState(false);
  const [versionHistoryOpen, setVersionHistoryOpen] = useState(false);
  const longPressTimer = useRef<NodeJS.Timeout | null>(null);
  const longPressStartPos = useRef<{ x: number; y: number } | null>(null);

  const [retryProcessing, { loading: retryLoading }] = useMutation<
    RetryDocumentProcessingOutputType,
    RetryDocumentProcessingInputType
  >(RETRY_DOCUMENT_PROCESSING, {
    update: (cache, { data }) => {
      if (data?.retryDocumentProcessing?.ok) {
        // Optimistically set processing state — the Celery task updates the DB
        // asynchronously, so the mutation response still has the old values.
        cache.modify({
          id: cache.identify({ __typename: "DocumentType", id }),
          fields: {
            backendLock: () => true,
            processingStatus: () => "PENDING",
            processingError: () => null,
            canRetry: () => false,
          },
        });
      }
    },
  });

  // Draggable setup (documents can be dragged to folders)
  const {
    attributes,
    listeners,
    setNodeRef: setDraggableRef,
    transform,
    isDragging,
  } = useDraggable({
    id: `document-${item.id}`,
    data: {
      type: "document",
      documentId: item.id,
    },
  });

  // Droppable setup (documents can receive other documents for linking)
  const {
    setNodeRef: setDroppableRef,
    isOver,
    active,
  } = useDroppable({
    id: `document-drop-${item.id}`,
    data: {
      type: "document-drop-target",
      documentId: item.id,
    },
  });

  // Check if the active dragged item is a document (not a folder)
  const isDocumentDragOver =
    isOver && active?.data?.current?.type === "document";

  // Combine draggable and droppable refs
  const setNodeRef = (node: HTMLElement | null) => {
    setDraggableRef(node);
    setDroppableRef(node);
  };

  // Apply transform for drag preview + drop target highlight
  const style = transform
    ? {
        transform: CSS.Translate.toString(transform),
        opacity: isDragging ? 0.5 : 1,
      }
    : isDocumentDragOver
    ? {
        outline: "2px dashed #3b82f6",
        outlineOffset: "2px",
        background: "#eff6ff",
      }
    : undefined;

  const {
    id,
    icon,
    is_selected,
    title,
    description,
    pdfFile,
    backendLock,
    processingStatus,
    processingError,
    canRetry,
    isPublic,
    myPermissions,
    fileType,
    pageCount,
    // Version metadata fields
    hasVersionHistory,
    versionCount,
    isLatestVersion,
    canViewHistory,
    // Relationship data
    docRelationshipCount,
    allDocRelationships,
  } = item;

  const isFailed = processingStatus === DocumentProcessingStatus.FAILED;
  const isProcessing =
    processingStatus != null &&
    processingStatus !== DocumentProcessingStatus.FAILED &&
    backendLock;

  const handleRetry = useCallback(
    async (e: React.MouseEvent) => {
      e.stopPropagation();
      try {
        const result = await retryProcessing({
          variables: { documentId: id },
        });
        if (result.data?.retryDocumentProcessing?.ok) {
          toast.success("Document reprocessing has been queued");
        } else {
          toast.error(
            result.data?.retryDocumentProcessing?.message ||
              "Failed to retry processing"
          );
        }
      } catch (err) {
        console.error("Failed to retry document processing:", err);
        toast.error("Failed to retry document processing");
      }
    },
    [id, retryProcessing]
  );

  const handleClick = (event: React.MouseEvent) => {
    if (
      (event.target as HTMLElement).closest(".action-button") ||
      (event.target as HTMLElement).closest(".checkbox")
    ) {
      return;
    }

    if (isFailed) {
      return;
    }

    event.stopPropagation();
    if (event.shiftKey) {
      onShiftClick?.(item);
    } else {
      onClick?.(item);
    }
  };

  const handleCheckboxClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    onShiftClick?.(item);
  };

  const handleOpen = (e: React.MouseEvent) => {
    e.stopPropagation();
    const currentCorpus = openedCorpus();
    navigateToDocument(
      item as any,
      currentCorpus as any,
      navigate,
      window.location.pathname
    );
    onClick?.(item);
  };

  const handleView = (e: React.MouseEvent) => {
    e.stopPropagation();
    viewingDocument(item);
  };

  const handleEdit = (e: React.MouseEvent) => {
    e.stopPropagation();
    editingDocument(item);
  };

  const handleDownload = async (e: React.MouseEvent) => {
    e.stopPropagation();
    if (pdfFile && !isDownloading) {
      setIsDownloading(true);
      try {
        await downloadFile(pdfFile);
      } finally {
        setTimeout(() => setIsDownloading(false), 1000);
      }
    }
  };

  const handleRemoveFromCorpus = (e: React.MouseEvent) => {
    e.stopPropagation();
    removeFromCorpus?.([item.id]);
  };

  // Context menu handlers
  const handleContextMenu = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setContextMenu({ x: e.clientX, y: e.clientY });
  };

  // Long press handlers for mobile
  const handleTouchStart = (e: React.TouchEvent) => {
    const touch = e.touches[0];
    longPressStartPos.current = { x: touch.clientX, y: touch.clientY };
    setIsLongPressing(true);

    longPressTimer.current = setTimeout(() => {
      if (longPressStartPos.current) {
        setContextMenu({
          x: longPressStartPos.current.x,
          y: longPressStartPos.current.y,
        });
        setIsLongPressing(false);
        // Haptic feedback if available
        if (navigator.vibrate) {
          navigator.vibrate(50);
        }
      }
    }, 500); // 500ms long press
  };

  const handleTouchMove = (e: React.TouchEvent) => {
    // Cancel long press if finger moves too much
    if (longPressStartPos.current && longPressTimer.current) {
      const touch = e.touches[0];
      const deltaX = Math.abs(touch.clientX - longPressStartPos.current.x);
      const deltaY = Math.abs(touch.clientY - longPressStartPos.current.y);

      if (deltaX > 10 || deltaY > 10) {
        clearTimeout(longPressTimer.current);
        longPressTimer.current = null;
        longPressStartPos.current = null;
        setIsLongPressing(false);
      }
    }
  };

  const handleTouchEnd = () => {
    if (longPressTimer.current) {
      clearTimeout(longPressTimer.current);
      longPressTimer.current = null;
    }
    longPressStartPos.current = null;
    setIsLongPressing(false);
  };

  // Cleanup timer on unmount
  useEffect(() => {
    return () => {
      if (longPressTimer.current) {
        clearTimeout(longPressTimer.current);
      }
    };
  }, []);

  const my_permissions = getPermissions(myPermissions ?? []);
  const canEdit = my_permissions.includes(PermissionTypes.CAN_UPDATE);

  // Build context menu items. Order: primary action (Open) → view/download/edit
  // → linking/versioning → retry (failed only) → destructive (remove) → select.
  const contextMenuItems: ContextMenuItem[] = [
    {
      label: "Open Document",
      icon: "book",
      onClick: handleOpen,
      variant: "primary",
      disabled: backendLock,
      dividerAfter: true,
    },
    {
      label: "View Details",
      icon: "eye",
      onClick: handleView,
      disabled: backendLock,
    },
  ];

  if (pdfFile) {
    contextMenuItems.push({
      label: isDownloading ? "Downloading..." : "Download PDF",
      icon: isDownloading ? "spinner" : "download",
      onClick: handleDownload,
      disabled: backendLock || isDownloading,
    });
  }

  if (canEdit) {
    contextMenuItems.push({
      label: "Edit Document",
      icon: "edit",
      onClick: handleEdit,
      disabled: backendLock,
    });
  }

  // Add link to document option if handler provided
  if (onLinkToDocument) {
    contextMenuItems.push({
      label: "Link to Document...",
      icon: "linkify",
      onClick: (e) => {
        e.stopPropagation();
        onLinkToDocument(item);
      },
      disabled: backendLock,
    });
  }

  // Add version history option if document has history
  if (hasVersionHistory && canViewHistory) {
    contextMenuItems.push({
      label: "View Version History",
      icon: "code branch",
      onClick: (e) => {
        e.stopPropagation();
        setVersionHistoryOpen(true);
      },
      disabled: backendLock,
      dividerAfter: true,
    });
  }

  if (isFailed && canRetry) {
    contextMenuItems.push({
      label: retryLoading ? "Retrying..." : "Retry Processing",
      icon: "redo",
      onClick: handleRetry,
      disabled: retryLoading,
      dividerAfter: true,
    });
  }

  if (removeFromCorpus) {
    contextMenuItems.push({
      label: "Remove from Corpus",
      icon: "trash",
      onClick: handleRemoveFromCorpus,
      variant: "danger",
      disabled: backendLock,
      dividerAfter: contextMenuItems.length > 0,
    });
  }

  contextMenuItems.push({
    label: is_selected ? "Deselect" : "Select",
    icon: is_selected ? "check square outline" : "square outline",
    onClick: (e) => {
      e.stopPropagation();
      onShiftClick?.(item);
    },
  });

  const doc_label_objs =
    item?.docLabelAnnotations?.edges
      .map((edge) => edge?.node?.annotationLabel)
      .filter((lbl): lbl is AnnotationLabelType => !!lbl) ?? [];

  const renderThumbnail = (className?: string) => (
    <>
      {icon ? (
        <img src={icon} alt={title || "Document"} />
      ) : (
        <>
          <div
            style={{ width: "100%", height: "100%", background: "#f8fafc" }}
          />
          <img
            src={fallback_doc_icon}
            alt="Document"
            className={`fallback-icon ${className || ""}`}
          />
        </>
      )}
    </>
  );

  const renderActions = (inOverlay = false) => (
    <>
      <ActionButton
        className={`action-button ${inOverlay ? "primary" : ""}`}
        onClick={handleOpen}
        disabled={backendLock}
        title="Open"
      >
        <Icon name="book" />
      </ActionButton>

      {!inOverlay && (
        <>
          <ActionButton
            className="action-button"
            onClick={handleView}
            disabled={backendLock}
            title="View"
          >
            <Icon name="eye" />
          </ActionButton>

          {pdfFile && (
            <ActionButton
              className="action-button"
              onClick={handleDownload}
              disabled={backendLock || isDownloading}
              title="Download"
            >
              <Icon
                name={isDownloading ? "spinner" : "download"}
                className={isDownloading ? "loading" : ""}
              />
            </ActionButton>
          )}

          {canEdit && (
            <ActionButton
              className="action-button"
              onClick={handleEdit}
              disabled={backendLock}
              title="Edit"
            >
              <Icon name="edit" />
            </ActionButton>
          )}

          {removeFromCorpus && (
            <ActionButton
              className="action-button"
              onClick={handleRemoveFromCorpus}
              disabled={backendLock}
              title="Remove"
            >
              <Icon name="trash" />
            </ActionButton>
          )}
        </>
      )}
    </>
  );

  // CARD VIEW
  if (viewMode === "card") {
    return (
      <>
        <CardContainer
          ref={setNodeRef}
          className={`${is_selected ? "is-selected" : ""} ${
            isProcessing ? "backend-locked" : ""
          } ${isFailed ? "failed" : ""} ${
            isLongPressing ? "long-pressing" : ""
          }`}
          onClick={handleClick}
          onContextMenu={handleContextMenu}
          onTouchStart={handleTouchStart}
          onTouchMove={handleTouchMove}
          onTouchEnd={handleTouchEnd}
          style={style}
          {...attributes}
          {...listeners}
        >
          {isProcessing && (
            <LoadingOverlay
              active={true}
              inverted
              size="small"
              content="Processing..."
            />
          )}

          {isProcessing && removeFromCorpus && (
            <ProcessingDeleteButton
              onClick={handleRemoveFromCorpus}
              title="Remove processing document"
              aria-label="Remove processing document from corpus"
            >
              <X />
            </ProcessingDeleteButton>
          )}

          <CardCheckbox
            className={`checkbox ${is_selected ? "selected" : ""}`}
            onClick={handleCheckboxClick}
          >
            {is_selected && <Icon name="check" />}
          </CardCheckbox>

          <CardPreview>
            {renderThumbnail()}
            {isFailed && (
              <ThumbnailFailureOverlay
                role="alert"
                aria-label="Processing failed"
              >
                <FailureIconCircle $size="large" aria-hidden="true">
                  <Icon name="warning sign" />
                </FailureIconCircle>
              </ThumbnailFailureOverlay>
            )}
            {fileType && !isFailed && <FileTypeBadge>{fileType}</FileTypeBadge>}
            {(hasVersionHistory || (versionCount && versionCount > 1)) && (
              <VersionBadgeWrapper>
                <VersionBadge
                  versionNumber={versionCount || 1}
                  hasHistory={hasVersionHistory ?? false}
                  isLatest={isLatestVersion ?? true}
                  versionCount={versionCount || 1}
                  onClick={() => setVersionHistoryOpen(true)}
                />
              </VersionBadgeWrapper>
            )}
            {!!docRelationshipCount && docRelationshipCount > 0 && (
              <RelationshipBadgeContainer onClick={(e) => e.stopPropagation()}>
                <RelationshipBadge>
                  <Link2 />
                  {docRelationshipCount}
                </RelationshipBadge>
                <RelationshipPopup>
                  <PopupHeader>
                    <Link2 />
                    <span>
                      {docRelationshipCount} Linked Document
                      {docRelationshipCount !== 1 ? "s" : ""}
                    </span>
                  </PopupHeader>
                  <PopupContent>
                    {allDocRelationships && allDocRelationships.length > 0 ? (
                      allDocRelationships.map((rel) => {
                        const isSource = rel.sourceDocument?.id === id;
                        const linkedDoc = isSource
                          ? rel.targetDocument
                          : rel.sourceDocument;
                        const labelColor = rel.annotationLabel?.color;

                        return (
                          <RelationshipItem key={rel.id}>
                            <RelationshipIcon $color={labelColor || "#14b8a6"}>
                              <FileText />
                            </RelationshipIcon>
                            <RelationshipDetails>
                              {rel.annotationLabel?.text && (
                                <RelationshipLabel $color={labelColor}>
                                  {rel.annotationLabel.text}
                                </RelationshipLabel>
                              )}
                              <LinkedDocTitle>
                                {linkedDoc?.title || "Untitled Document"}
                              </LinkedDocTitle>
                              <RelationshipDirection>
                                {isSource ? (
                                  <>
                                    This doc <ArrowRight size={10} /> linked doc
                                  </>
                                ) : (
                                  <>
                                    Linked doc <ArrowRight size={10} /> this doc
                                  </>
                                )}
                              </RelationshipDirection>
                            </RelationshipDetails>
                          </RelationshipItem>
                        );
                      })
                    ) : (
                      <div style={{ color: "#94a3b8", fontSize: "0.75rem" }}>
                        Loading relationships...
                      </div>
                    )}
                  </PopupContent>
                </RelationshipPopup>
              </RelationshipBadgeContainer>
            )}
          </CardPreview>

          <CardContent>
            <CardTitle>{title || "Untitled Document"}</CardTitle>

            {isFailed ? (
              <CardMeta>
                <FailureBadge>Processing Failed</FailureBadge>
                {canRetry && (
                  <RetryButton
                    className="action-button"
                    onClick={handleRetry}
                    disabled={retryLoading}
                    aria-label="Retry processing this document"
                  >
                    <RotateCcw aria-hidden="true" />
                    {retryLoading ? "Retrying..." : "Retry"}
                  </RetryButton>
                )}
              </CardMeta>
            ) : (
              <CardMeta>
                {pageCount && (
                  <div className="meta-item">
                    <Icon name="file outline" />
                    {pageCount}p
                  </div>
                )}
                {isPublic && (
                  <div className="meta-item">
                    <Icon name="globe" />
                    Public
                  </div>
                )}
                {doc_label_objs.length > 0 && (
                  <div className="meta-item">
                    <Icon name="tag" />
                    {doc_label_objs.length}
                  </div>
                )}
              </CardMeta>
            )}
          </CardContent>

          {!isFailed && (
            <ActionOverlay className="action-overlay">
              {renderActions(true)}
            </ActionOverlay>
          )}
        </CardContainer>

        {contextMenu && (
          <ModernContextMenu
            x={contextMenu.x}
            y={contextMenu.y}
            items={contextMenuItems}
            onClose={() => setContextMenu(null)}
            title={title || "Document Actions"}
          />
        )}

        <VersionHistoryPanel
          documentId={id}
          corpusId={openedCorpus()?.id || ""}
          documentTitle={title || "Document"}
          isOpen={versionHistoryOpen}
          onClose={() => setVersionHistoryOpen(false)}
          onDownload={(_versionId) => {
            // Version download not yet implemented — requires a backend
            // endpoint that serves the file for a specific DocumentVersion.
          }}
        />
      </>
    );
  }

  // LIST VIEW
  return (
    <>
      <ListContainer
        ref={setNodeRef}
        className={`${is_selected ? "is-selected" : ""} ${
          isProcessing ? "backend-locked" : ""
        } ${isFailed ? "failed" : ""} ${isLongPressing ? "long-pressing" : ""}`}
        onClick={handleClick}
        onContextMenu={handleContextMenu}
        onTouchStart={handleTouchStart}
        onTouchMove={handleTouchMove}
        onTouchEnd={handleTouchEnd}
        style={style}
        {...attributes}
        {...listeners}
      >
        {isProcessing && (
          <LoadingOverlay
            active={true}
            inverted
            size="small"
            content="Processing..."
          />
        )}

        {isProcessing && removeFromCorpus && (
          <ProcessingDeleteButton
            onClick={handleRemoveFromCorpus}
            title="Remove processing document"
            aria-label="Remove processing document from corpus"
          >
            <X />
          </ProcessingDeleteButton>
        )}

        <ListCheckbox
          className={`checkbox ${is_selected ? "selected" : ""}`}
          onClick={handleCheckboxClick}
        >
          {is_selected && <Icon name="check" />}
        </ListCheckbox>

        <ListThumbnail>
          {renderThumbnail()}
          {isFailed && (
            <ThumbnailFailureOverlay>
              <FailureIconCircle $size="small" aria-hidden="true">
                <Icon name="warning sign" />
              </FailureIconCircle>
            </ThumbnailFailureOverlay>
          )}
        </ListThumbnail>

        <ListContent>
          <ListTitle>{title || "Untitled Document"}</ListTitle>
          {isFailed ? (
            <FailureDescription>
              {processingError || "Document processing failed"}
            </FailureDescription>
          ) : (
            description && <ListDescription>{description}</ListDescription>
          )}
          <ListMeta>
            {isFailed && <FailureBadge>Failed</FailureBadge>}
            {fileType && (
              <div className="meta-item">{fileType.toUpperCase()}</div>
            )}
            {pageCount && <div className="meta-item">{pageCount} pages</div>}
            {isPublic && (
              <div className="meta-item">
                <Icon name="globe" />
                Public
              </div>
            )}
            {(hasVersionHistory || (versionCount && versionCount > 1)) && (
              <div
                className="meta-item"
                style={{
                  cursor: hasVersionHistory ? "pointer" : "default",
                  color: isLatestVersion === false ? "#c2410c" : "#1d4ed8",
                }}
                onClick={
                  hasVersionHistory
                    ? (e) => {
                        e.stopPropagation();
                        setVersionHistoryOpen(true);
                      }
                    : undefined
                }
              >
                <Icon name="code branch" />v{versionCount || 1}
                {hasVersionHistory && ` (${versionCount} versions)`}
              </div>
            )}
            {!!docRelationshipCount && docRelationshipCount > 0 && (
              <ListRelationshipBadge onClick={(e) => e.stopPropagation()}>
                <Link2 />
                {docRelationshipCount}
                <ListRelationshipPopup>
                  <PopupHeader>
                    <Link2 />
                    <span>
                      {docRelationshipCount} Linked Document
                      {docRelationshipCount !== 1 ? "s" : ""}
                    </span>
                  </PopupHeader>
                  <PopupContent>
                    {allDocRelationships && allDocRelationships.length > 0 ? (
                      allDocRelationships.map((rel) => {
                        const isSource = rel.sourceDocument?.id === id;
                        const linkedDoc = isSource
                          ? rel.targetDocument
                          : rel.sourceDocument;
                        const labelColor = rel.annotationLabel?.color;

                        return (
                          <RelationshipItem key={rel.id}>
                            <RelationshipIcon $color={labelColor || "#14b8a6"}>
                              <FileText />
                            </RelationshipIcon>
                            <RelationshipDetails>
                              {rel.annotationLabel?.text && (
                                <RelationshipLabel $color={labelColor}>
                                  {rel.annotationLabel.text}
                                </RelationshipLabel>
                              )}
                              <LinkedDocTitle>
                                {linkedDoc?.title || "Untitled Document"}
                              </LinkedDocTitle>
                              <RelationshipDirection>
                                {isSource ? (
                                  <>
                                    This doc <ArrowRight size={10} /> linked doc
                                  </>
                                ) : (
                                  <>
                                    Linked doc <ArrowRight size={10} /> this doc
                                  </>
                                )}
                              </RelationshipDirection>
                            </RelationshipDetails>
                          </RelationshipItem>
                        );
                      })
                    ) : (
                      <div style={{ color: "#94a3b8", fontSize: "0.75rem" }}>
                        Loading relationships...
                      </div>
                    )}
                  </PopupContent>
                </ListRelationshipPopup>
              </ListRelationshipBadge>
            )}
          </ListMeta>
        </ListContent>

        <ListActions>
          {isFailed && canRetry ? (
            <RetryButton
              onClick={handleRetry}
              disabled={retryLoading}
              aria-label="Retry processing this document"
            >
              <RotateCcw aria-hidden="true" />
              {retryLoading ? "Retrying..." : "Retry"}
            </RetryButton>
          ) : !isFailed ? (
            renderActions()
          ) : null}
        </ListActions>
      </ListContainer>

      {contextMenu && (
        <ModernContextMenu
          x={contextMenu.x}
          y={contextMenu.y}
          items={contextMenuItems}
          onClose={() => setContextMenu(null)}
          title={title || "Document Actions"}
        />
      )}

      <VersionHistoryPanel
        documentId={id}
        corpusId={openedCorpus()?.id || ""}
        documentTitle={title || "Document"}
        isOpen={versionHistoryOpen}
        onClose={() => setVersionHistoryOpen(false)}
        onDownload={(_versionId) => {
          // Version download not yet implemented — requires a backend
          // endpoint that serves the file for a specific DocumentVersion.
        }}
      />
    </>
  );
};
